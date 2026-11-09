"""Veri Aktar sayfası: Cormind Excel dosyasını yükler, veri durumunu gösterir."""
from __future__ import annotations

import os
from datetime import timedelta

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView, QAbstractItemView)

from . import ice_aktar, tema, veritabani as vt
from .sayfa_ortak import etiket, kart, tablo_menusu


class BirakAlani(QFrame):
    def __init__(self, ac_fn, yukle_fn):
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("Kart")
        self.setStyleSheet(f"QFrame#Kart {{ border: 2px dashed {tema.CIZGI}; background: #FAFBFD; }}")
        self.yukle_fn = yukle_fn
        l = QVBoxLayout(self)
        l.setContentsMargins(24, 28, 24, 28)
        l.setAlignment(Qt.AlignCenter)
        b = etiket("Cormind'den aldığınız Excel dosyasını buraya sürükleyin", "KartDeger", kelime=False)
        b.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {tema.LACIVERT};")
        b.setAlignment(Qt.AlignCenter)
        a = etiket("ya da düğmeye basıp dosyayı seçin (.xls, .xlsx, .xlsm veya .csv)", "AltBaslik", kelime=False)
        a.setAlignment(Qt.AlignCenter)
        self.btn = QPushButton("Excel dosyası seç…")
        self.btn.setObjectName("Ana")
        self.btn.setMinimumHeight(40)
        self.btn.setMinimumWidth(220)
        self.btn.clicked.connect(ac_fn)
        l.addWidget(b)
        l.addWidget(a)
        l.addSpacing(8)
        l.addWidget(self.btn, 0, Qt.AlignCenter)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        yollar = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if yollar:
            self.yukle_fn(yollar)


class VeriSayfasi(QWidget):
    def __init__(self, ana):
        super().__init__()
        self.ana = ana
        kok = QVBoxLayout(self)
        kok.setContentsMargins(26, 22, 26, 22)
        kok.setSpacing(14)
        kok.addWidget(etiket("Veri Aktar", "Baslik"))
        kok.addWidget(etiket("Cormind'den aldığınız Excel listesini yükleyin. Aynı gün ve aynı kayıt tekrar gelirse çoğalmaz; "
                             "formül hatası olan satırlar atlanır.", "AltBaslik"))
        self.alan = BirakAlani(self.dosya_sec, self.yukle)
        kok.addWidget(self.alan)
        self.sonuc = QLabel("")
        self.sonuc.setWordWrap(True)
        self.sonuc.hide()
        kok.addWidget(self.sonuc)
        self.uyari = QLabel("")
        self.uyari.setObjectName("Uyari")
        self.uyari.setWordWrap(True)
        self.uyari.hide()
        kok.addWidget(self.uyari)

        alt = QHBoxLayout()
        alt.setSpacing(14)
        sol = kart()
        sol.layout().addWidget(etiket("Veri durumu (gün gün)", "KartBaslik"))
        self.gun_tablo = self._tablo(["Tarih", "Gün", "Kayıt"])
        sol.layout().addWidget(self.gun_tablo)
        sag = kart()
        sag.layout().addWidget(etiket("Son aktarımlar", "KartBaslik"))
        self.gecmis_tablo = self._tablo(["Zaman", "Dosya", "Yeni", "Güncel", "Aynı", "Atlanan"])
        sag.layout().addWidget(self.gecmis_tablo)
        alt.addWidget(sol, 2)
        alt.addWidget(sag, 3)
        kok.addLayout(alt, 1)
        self.yenile()

    @staticmethod
    def _tablo(basliklar):
        t = QTableWidget(0, len(basliklar))
        t.setHorizontalHeaderLabels(basliklar)
        t.verticalHeader().hide()
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionMode(QAbstractItemView.NoSelection)
        t.horizontalHeader().setStretchLastSection(True)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        tablo_menusu(t)
        return t

    def dosya_sec(self):
        yollar, _ = QFileDialog.getOpenFileNames(self, "Cormind dosyasını seç", "",
                                                 "Excel / CSV (*.xls *.xlsx *.xlsm *.csv);;Tüm dosyalar (*.*)")
        if yollar:
            self.yukle(yollar)

    def yukle(self, yollar):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        mesajlar, atlanan, yeni_m, hatalar = [], [], [], []
        try:
            for y in yollar:
                try:
                    s = ice_aktar.aktar(self.ana.con, y)
                    mesajlar.append(f"{s.dosya}: {s.ozet()}")
                    atlanan += [(s.dosya, no, neden) for no, neden in s.atlanan]
                    yeni_m += s.yeni_makineler
                except Exception as ex:  # noqa: BLE001 - kullanıcıya gösterilir
                    hatalar.append(f"{os.path.basename(y)}: {ex}")
        finally:
            QApplication.restoreOverrideCursor()
        self.ana.veri_yenilendi()
        if mesajlar:
            self.sonuc.setObjectName("Basari")
            self.sonuc.setText("\n".join(mesajlar))
            self.sonuc.setStyle(self.sonuc.style())
            self.sonuc.show()
        else:
            self.sonuc.hide()
        notlar = list(hatalar)
        if atlanan:
            ornek = ", ".join(f"satır {no} ({neden})" for _, no, neden in atlanan[:6])
            notlar.append(f"{len(atlanan)} hatalı satır hesaba alınmadı: {ornek}" + (" …" if len(atlanan) > 6 else ""))
        if yeni_m:
            notlar.append("Makine listesine eklendi: " + ", ".join(sorted(set(yeni_m))))
        self.uyari.setText("\n".join(notlar))
        self.uyari.setVisible(bool(notlar))
        self.yenile()

    def yenile(self):
        kap = self.ana.kapsam()
        self.gun_tablo.setRowCount(0)
        if kap:
            ilk, son = min(kap), max(kap)
            gunler = [ilk + timedelta(days=i) for i in range((son - ilk).days + 1)]
            self.gun_tablo.setRowCount(len(gunler))
            for i, g in enumerate(reversed(gunler)):
                n = kap.get(g, 0)
                for j, t in enumerate((tema.tarih(g), tema.GUNLER[g.weekday()], str(n) if n else "kayıt yok")):
                    it = QTableWidgetItem(t)
                    if not n:
                        it.setForeground(QColor("#9AA3B8"))
                    if j == 2:
                        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self.gun_tablo.setItem(i, j, it)
        gec = vt.aktarim_gecmisi(self.ana.con, 12)
        self.gecmis_tablo.setRowCount(len(gec))
        for i, g in enumerate(gec):
            for j, t in enumerate((g["zaman"][5:16].replace("-", "."), g["dosya"] or "", g["yeni"], g["guncellenen"], g["ayni"], g["atlanan"])):
                it = QTableWidgetItem(str(t))
                if j >= 2:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.gecmis_tablo.setItem(i, j, it)
