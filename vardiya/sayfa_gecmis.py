"""Geçmiş sayfası: arşive kaydedilen raporlar."""
from __future__ import annotations

import os
import tempfile

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView, QMessageBox, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from . import veritabani as vt
from .sayfa_ortak import etiket, kart, tablo_menusu


class GecmisSayfasi(QWidget):
    def __init__(self, ana):
        super().__init__()
        self.ana = ana
        kok = QVBoxLayout(self)
        kok.setContentsMargins(26, 22, 26, 22)
        kok.setSpacing(14)
        kok.addWidget(etiket("Geçmiş", "Baslik"))
        kok.addWidget(etiket("Raporlar sayfasında 'Arşive Kaydet' dediğiniz raporlar burada saklanır. "
                             "Eski bir günün ya da haftanın rakamlarına bakmak için Performans sayfasında tarihi seçmeniz de yeter; "
                             "veriler silinmez.", "AltBaslik"))
        k = kart()
        self.tablo = QTableWidget(0, 5)
        self.tablo.setHorizontalHeaderLabels(["Rapor", "Tür", "Dönem", "Kaydedilme", ""])
        self.tablo.verticalHeader().hide()
        self.tablo.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tablo.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tablo.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tablo.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1, 2, 3, 4):
            self.tablo.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.tablo.doubleClicked.connect(lambda _: self.ac())
        tablo_menusu(self.tablo)
        k.layout().addWidget(self.tablo)
        kok.addWidget(k, 1)
        alt = QHBoxLayout()
        self.b_ac = QPushButton("PDF'i Aç")
        self.b_ac.setObjectName("Ana")
        self.b_kaydet = QPushButton("PDF Olarak Kaydet…")
        self.b_sil = QPushButton("Sil")
        self.b_sil.setObjectName("Tehlike")
        for b in (self.b_ac, self.b_kaydet):
            alt.addWidget(b)
        alt.addStretch()
        alt.addWidget(self.b_sil)
        kok.addLayout(alt)
        self.b_ac.clicked.connect(self.ac)
        self.b_kaydet.clicked.connect(self.kaydet)
        self.b_sil.clicked.connect(self.sil)
        self.yenile()

    def yenile(self):
        liste = vt.arsiv_liste(self.ana.con)
        self.tablo.setRowCount(len(liste))
        for i, r in enumerate(liste):
            tr = lambda iso: f"{iso[8:10]}.{iso[5:7]}.{iso[:4]}"  # noqa: E731
            ilk, son = tr(r["ilk_gun"]), tr(r["son_gun"])
            donem = ilk if ilk == son else f"{ilk} – {son}"
            kayit = f"{tr(r['olusturma'][:10])} {r['olusturma'][11:16]}"
            for j, t in enumerate((r["ad"], r["tur"], donem, kayit, "PDF var" if r["pdf_var"] else "")):
                it = QTableWidgetItem(t)
                if j == 0:
                    it.setData(Qt.UserRole, r["id"])
                self.tablo.setItem(i, j, it)
        var = bool(liste)
        for b in (self.b_ac, self.b_kaydet, self.b_sil):
            b.setEnabled(var)

    def _secili(self):
        s = self.tablo.currentRow()
        if s < 0:
            return None
        return vt.arsiv_getir(self.ana.con, self.tablo.item(s, 0).data(Qt.UserRole))

    def ac(self):
        r = self._secili()
        if not r or not r["pdf"]:
            return
        yol = os.path.join(tempfile.gettempdir(), f"vardiya_rapor_{r['id']}.pdf")
        with open(yol, "wb") as f:
            f.write(r["pdf"])
        QDesktopServices.openUrl(QUrl.fromLocalFile(yol))

    def kaydet(self):
        r = self._secili()
        if not r or not r["pdf"]:
            return
        yol, _ = QFileDialog.getSaveFileName(self, "PDF olarak kaydet", r["ad"] + ".pdf", "PDF (*.pdf)")
        if yol:
            with open(yol, "wb") as f:
                f.write(r["pdf"])
            self.ana.mesaj(f"Kaydedildi: {yol}")

    def sil(self):
        r = self._secili()
        if not r:
            return
        if QMessageBox.question(self, "Sil", f"'{r['ad']}' arşivden silinsin mi?") == QMessageBox.Yes:
            vt.arsiv_sil(self.ana.con, r["id"])
            self.yenile()
