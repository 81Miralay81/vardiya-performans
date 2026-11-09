"""Ayarlar sayfası: eşik, süreler, makine listesi, grup liderleri."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QAbstractSpinBox, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QPushButton, QScrollArea, QSpinBox, QVBoxLayout,
                               QWidget)

from . import tema, veritabani as vt
from .hesap import HesapAyar, VARDIYALAR
from .sayfa_ortak import etiket, kart


def _liste_duzenleyici(baslik: str, aciklama: str, duzenlenebilir=True):
    k = kart()
    k.layout().addWidget(etiket(baslik, "KartBaslik"))
    if aciklama:
        k.layout().addWidget(etiket(aciklama, "AltBaslik"))
    lst = QListWidget()
    lst.setMinimumHeight(180)
    k.layout().addWidget(lst)
    return k, lst


class AyarSayfasi(QWidget):
    def __init__(self, ana):
        super().__init__()
        self.ana = ana
        dis = QVBoxLayout(self)
        dis.setContentsMargins(26, 22, 26, 22)
        dis.setSpacing(12)
        ust = QHBoxLayout()
        sol = QVBoxLayout()
        sol.addWidget(etiket("Ayarlar", "Baslik"))
        sol.addWidget(etiket("Değişiklikler 'Kaydet' deyince geçerli olur; tüm hesaplar yeni ayarla yenilenir.", "AltBaslik"))
        ust.addLayout(sol, 1)
        self.b_kaydet = QPushButton("Kaydet")
        self.b_kaydet.setObjectName("Ana")
        self.b_kaydet.setMinimumWidth(140)
        self.b_kaydet.clicked.connect(self.kaydet)
        ust.addWidget(self.b_kaydet, 0, Qt.AlignTop)
        dis.addLayout(ust)

        sc = QScrollArea()
        sc.setWidgetResizable(True)
        icerik = QWidget()
        ic = QVBoxLayout(icerik)
        ic.setContentsMargins(0, 0, 8, 0)
        ic.setSpacing(12)
        sc.setWidget(icerik)
        dis.addWidget(sc, 1)

        # ------------------------------------------------ hesap kuralları
        k = kart()
        k.layout().addWidget(etiket("HESAP KURALLARI", "KartBaslik"))
        f = QFormLayout()
        f.setLabelAlignment(Qt.AlignLeft)
        self.esik = QDoubleSpinBox()
        self.esik.setRange(0, 100)
        self.esik.setDecimals(0)
        self.esik.setSuffix(" %")
        self.esik.setToolTip("Bir makine, o gün o vardiyada bu orana ulaşmadıysa sayılmaz")
        self.vardiya_dk = QSpinBox()
        self.vardiya_dk.setRange(60, 1440)
        self.vardiya_dk.setSuffix(" dk")
        self.yemek_dk = QSpinBox()
        self.yemek_dk.setRange(0, 240)
        self.yemek_dk.setSuffix(" dk")
        self.cay_dk = QSpinBox()
        self.cay_dk.setRange(0, 240)
        self.cay_dk.setSuffix(" dk")
        self.net = QLabel("")
        self.net.setObjectName("AltBaslik")
        f.addRow("Eşik (makine sayılması için en az)", self.esik)
        f.addRow("Vardiya uzunluğu", self.vardiya_dk)
        f.addRow("Yemek molası (her vardiyada 1 kez)", self.yemek_dk)
        f.addRow("Çay molası", self.cay_dk)
        f.addRow("Net çalışma süresi", self.net)
        for w in (self.esik, self.vardiya_dk, self.yemek_dk, self.cay_dk):
            w.setMaximumWidth(150)
            w.setButtonSymbols(QAbstractSpinBox.PlusMinus)
        for w in (self.vardiya_dk, self.yemek_dk, self.cay_dk):
            w.valueChanged.connect(self._net_yaz)
        k.layout().addLayout(f)
        self.idle = QCheckBox("Çalışmayan makineleri de makine grafiğinde göster")
        k.layout().addWidget(self.idle)
        ic.addWidget(k)

        # ------------------------------------------------ makineler + şefler
        satir = QHBoxLayout()
        satir.setSpacing(12)
        km, self.mak_liste = _liste_duzenleyici("MAKİNELER", "Tabloda bu sırayla görünür. Veride yeni bir makine çıkarsa otomatik eklenir.")
        self.mak_ekle = QLineEdit()
        self.mak_ekle.setPlaceholderText("Yeni makine adı (örn. IM90)")
        self.mak_ekle.returnPressed.connect(self._mak_ekle)
        km.layout().addWidget(self.mak_ekle)
        s1 = QHBoxLayout()
        for ad, fn in (("Ekle", self._mak_ekle), ("Sil", lambda: self._sil(self.mak_liste)), ("Yukarı", lambda: self._tasi(self.mak_liste, -1)),
                       ("Aşağı", lambda: self._tasi(self.mak_liste, 1))):
            b = QPushButton(ad)
            b.clicked.connect(fn)
            s1.addWidget(b)
        km.layout().addLayout(s1)
        satir.addWidget(km, 1)

        ks, self.sef_liste = _liste_duzenleyici("GRUP LİDERLERİ", "Adı değiştirmek için çift tıklayın. Raporlarda ve vardiya kutularında bu liste çıkar.")
        self.sef_liste.itemDoubleClicked.connect(self._sef_adlandir)
        self.sef_ekle = QLineEdit()
        self.sef_ekle.setPlaceholderText("Yeni grup lideri adı")
        self.sef_ekle.returnPressed.connect(self._sef_ekle)
        ks.layout().addWidget(self.sef_ekle)
        s2 = QHBoxLayout()
        for ad, fn in (("Ekle", self._sef_ekle), ("Sil", lambda: self._sil(self.sef_liste))):
            b = QPushButton(ad)
            b.clicked.connect(fn)
            s2.addWidget(b)
        ks.layout().addLayout(s2)
        ks.layout().addWidget(etiket("VARSAYILAN VARDİYA LİDERLERİ", "KartBaslik"))
        ff = QFormLayout()
        self.varsayilan = {}
        for v in VARDIYALAR:
            c = QComboBox()
            self.varsayilan[v] = c
            ff.addRow(f"{v}. Vardiya", c)
        ks.layout().addLayout(ff)
        ks.layout().addWidget(etiket("Belirli günlerde farklı kişi için Performans / Raporlar sayfasındaki vardiya kutusundan seçin.", "AltBaslik"))
        satir.addWidget(ks, 1)
        ic.addLayout(satir)

        # ------------------------------------------------ veri tabanı
        kd = kart()
        kd.layout().addWidget(etiket("VERİ TABANI", "KartBaslik"))
        self.db_yolu = etiket("", "AltBaslik")
        self.db_yolu.setTextInteractionFlags(Qt.TextSelectableByMouse)
        kd.layout().addWidget(self.db_yolu)
        b = QPushButton("Klasörü Aç")
        b.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self.ana.db_yolu))))
        kd.layout().addWidget(b, 0, Qt.AlignLeft)
        ic.addWidget(kd)
        ic.addStretch(1)
        self.yenile()

    # ------------------------------------------------ liste işlemleri
    @staticmethod
    def _ekle(liste: QListWidget, metin: str, duzenlenebilir=False):
        o = QListWidgetItem(metin)
        liste.addItem(o)

    def _mak_ekle(self):
        ad = self.mak_ekle.text().strip().upper()
        if ad and ad not in self._adlar(self.mak_liste):
            self._ekle(self.mak_liste, ad)
        self.mak_ekle.clear()

    def _sef_ekle(self):
        ad = self.sef_ekle.text().strip()
        if ad and ad not in self._adlar(self.sef_liste):
            self._ekle(self.sef_liste, ad)
            self._varsayilan_doldur()
        self.sef_ekle.clear()

    def _sef_adlandir(self, oge):
        yeni, ok = QInputDialog.getText(self, "Grup lideri adı", "Yeni ad:", text=oge.text())
        if ok and yeni.strip():
            oge.setText(yeni.strip())
            self._varsayilan_doldur()

    def _sil(self, liste):
        for o in liste.selectedItems():
            liste.takeItem(liste.row(o))
        self._varsayilan_doldur()

    @staticmethod
    def _tasi(liste, yon):
        r = liste.currentRow()
        y = r + yon
        if r < 0 or not 0 <= y < liste.count():
            return
        o = liste.takeItem(r)
        liste.insertItem(y, o)
        liste.setCurrentRow(y)

    @staticmethod
    def _adlar(liste):
        return [liste.item(i).text() for i in range(liste.count())]

    def _varsayilan_doldur(self, secili=None):
        adlar = self._adlar(self.sef_liste)
        for v, c in self.varsayilan.items():
            onceki = (secili or {}).get(v, c.currentText())
            c.clear()
            c.addItems(adlar)
            if onceki in adlar:
                c.setCurrentText(onceki)

    def _net_yaz(self):
        a = HesapAyar(vardiya_dk=self.vardiya_dk.value(), yemek_dk=self.yemek_dk.value(), cay_dk=self.cay_dk.value())
        self.net.setText(f"{tema.sayi(a.net_saat, 2)} saat   ·   mola kapasitesi {self.yemek_dk.value() + self.cay_dk.value()} dk")

    # ------------------------------------------------ oku / yaz
    def yenile(self):
        a = self.ana.ayar
        self.esik.setValue(round(a["esik"] * 100))
        self.vardiya_dk.setValue(a["vardiya_dk"])
        self.yemek_dk.setValue(a["yemek_dk"])
        self.cay_dk.setValue(a["cay_dk"])
        self.idle.setChecked(bool(a.get("idle_makineleri_goster")))
        self.mak_liste.clear()
        for m in a["makineler"]:
            self._ekle(self.mak_liste, m)
        self.sef_liste.clear()
        for s in a["sefler"]:
            self._ekle(self.sef_liste, s)
        self._varsayilan_doldur({v: a["vardiya_sef"].get(str(v), "") for v in VARDIYALAR})
        self.db_yolu.setText(self.ana.db_yolu)
        self._net_yaz()

    def kaydet(self):
        con = self.ana.con
        vt.ayar_yaz(con, "esik", self.esik.value() / 100.0)
        vt.ayar_yaz(con, "vardiya_dk", self.vardiya_dk.value())
        vt.ayar_yaz(con, "yemek_dk", self.yemek_dk.value())
        vt.ayar_yaz(con, "cay_dk", self.cay_dk.value())
        vt.ayar_yaz(con, "idle_makineleri_goster", self.idle.isChecked())
        vt.ayar_yaz(con, "makineler", self._adlar(self.mak_liste))
        vt.ayar_yaz(con, "sefler", self._adlar(self.sef_liste))
        vt.ayar_yaz(con, "vardiya_sef", {str(v): c.currentText() for v, c in self.varsayilan.items()})
        self.ana.ayar_degisti()
        self.ana.mesaj("Ayarlar kaydedildi, hesaplar yenilendi.")
