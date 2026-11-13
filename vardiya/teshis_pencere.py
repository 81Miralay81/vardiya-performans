"""Teşhis penceresi: açılış kaydını gösterir, sunucudaki program klasörünün hızını ölçer."""
from __future__ import annotations

import os
import threading

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QVBoxLayout)

from . import teshis

SUNUCU_KLASORU = r"\\KALIPNAS2019\kaliphanenas\OMUR\vardiyaperformans"


class TeshisPenceresi(QDialog):
    def __init__(self, ust=None, klasor: str = ""):
        super().__init__(ust)
        self.setWindowTitle("Teşhis – açılış kaydı ve sunucu ölçümü")
        self.resize(1000, 680)
        self._satirlar = []
        self._kilit = threading.Lock()
        self._is = None
        self._dur = False
        d = QVBoxLayout(self)
        d.addWidget(QLabel("Ölçülecek klasör (sunucudaki program klasörü). Ölçüm hiçbir kaydı değiştirmez; "
                           "program dosyasını ve veri tabanını okur, süreleri yazar."))
        s = QHBoxLayout()
        self.klasor = QLineEdit(klasor or SUNUCU_KLASORU)
        b_sec = QPushButton("Klasör Seç…")
        b_sec.clicked.connect(self._sec)
        self.b_olc = QPushButton("Sunucuyu Ölç")
        self.b_olc.setObjectName("Birincil")
        self.b_olc.clicked.connect(self._olc)
        self.b_dur = QPushButton("Durdur")
        self.b_dur.setEnabled(False)
        self.b_dur.clicked.connect(self._durdur)
        s.addWidget(self.klasor, 1)
        for b in (b_sec, self.b_olc, self.b_dur):
            s.addWidget(b)
        d.addLayout(s)
        self.metin = QPlainTextEdit()
        self.metin.setReadOnly(True)
        f = QFont("Consolas")
        f.setStyleHint(QFont.Monospace)
        f.setPointSize(10)
        self.metin.setFont(f)
        self.metin.setLineWrapMode(QPlainTextEdit.NoWrap)
        d.addWidget(self.metin, 1)
        a = QHBoxLayout()
        b_kayit = QPushButton("Açılış Kaydını Göster")
        b_kayit.clicked.connect(self._kayit)
        b_kop = QPushButton("Tümünü Kopyala")
        b_kop.clicked.connect(lambda: QApplication.clipboard().setText(self.metin.toPlainText()))
        b_kl = QPushButton("Kayıt Klasörünü Aç")
        b_kl.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(teshis.kayit_klasoru())))
        b_kapat = QPushButton("Kapat")
        b_kapat.clicked.connect(self.close)
        for b in (b_kayit, b_kop, b_kl):
            a.addWidget(b)
        a.addStretch(1)
        a.addWidget(b_kapat)
        d.addLayout(a)
        self.zaman = QTimer(self)
        self.zaman.setInterval(200)
        self.zaman.timeout.connect(self._aktar)
        self._kayit()

    def _sec(self):
        k = QFileDialog.getExistingDirectory(self, "Ölçülecek klasör", self.klasor.text())
        if k:
            self.klasor.setText(os.path.normpath(k))

    def _kayit(self):
        self.metin.setPlainText("AÇILIŞ KAYDI (" + teshis.kayit_yolu() + ")\n" + teshis.kaydi_oku())
        self.metin.verticalScrollBar().setValue(self.metin.verticalScrollBar().maximum())

    def _olc(self):
        if self._is and self._is.is_alive():
            return
        klasor = self.klasor.text().strip()
        self.metin.setPlainText("")
        self._dur = False
        self.b_olc.setEnabled(False)
        self.b_dur.setEnabled(True)

        def ekle(m):
            with self._kilit:
                self._satirlar.append(m)

        def calis():
            try:
                rapor = teshis.sunucu_olcumu(klasor, ekle, lambda: self._dur)
                yol = os.path.join(teshis.kayit_klasoru(), "sunucu_olcumu.txt")
                with open(yol, "a", encoding="utf-8") as f:
                    f.write(rapor + "\n\n")
                ekle("")
                ekle("Rapor ayrıca şuraya kaydedildi: " + yol)
            except Exception as ex:  # noqa: BLE001
                ekle(f"ÖLÇÜM HATASI: {ex}")

        self._is = threading.Thread(target=calis, name="teshis-olcum", daemon=True)
        self._is.start()
        self.zaman.start()

    def _durdur(self):
        self._dur = True

    def _aktar(self):
        with self._kilit:
            yeni, self._satirlar = self._satirlar, []
        for m in yeni:
            self.metin.appendPlainText(m)
        if self._is and not self._is.is_alive() and not yeni:
            self.zaman.stop()
            self.b_olc.setEnabled(True)
            self.b_dur.setEnabled(False)

    def closeEvent(self, e):
        self._dur = True
        super().closeEvent(e)
