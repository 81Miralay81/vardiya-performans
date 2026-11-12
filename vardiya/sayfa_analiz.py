"""Performans / Genel Duruş / Mola sayfaları (aynı yapı, farklı ölçü)."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from . import cizim, tema
from .hesap import VARDIYALAR
from .sayfa_ortak import CizimWidget, SefCombo, etiket, kart

BASLIK = ("Performans", "Genel Duruş", "Mola")
ALT = ("Makine ve vardiya bazında çalışma oranı: bir makine, o gün o vardiyada eşiği geçtiyse sayılır.",
       "Aynı makineler için duruş oranı (çalışmayan süre / net vardiya süresi).",
       "Aynı makineler için mola oranı (yemek + çay molası kapasitesine göre).")
OLCU = ("calisma", "durus", "mola")


class Kpi(QFrame):
    def __init__(self, baslik: str, combo: SefCombo = None):
        super().__init__()
        self.setObjectName("Kart")
        l = QVBoxLayout(self)
        l.setContentsMargins(16, 12, 16, 12)
        l.setSpacing(2)
        self.b = etiket(baslik, "KartBaslik")
        self.d = QLabel("-")
        self.d.setObjectName("KartDeger")
        self.a = etiket("", "AltBaslik")
        l.addWidget(self.b)
        l.addWidget(self.d)
        l.addWidget(self.a)
        self.combo = combo
        if combo:
            l.addWidget(combo)


class AnalizSayfasi(QWidget):
    def __init__(self, ana, secim: int):
        super().__init__()
        self.ana, self.secim = ana, secim
        kok = QVBoxLayout(self)
        kok.setContentsMargins(26, 18, 26, 18)
        kok.setSpacing(12)

        ust = QHBoxLayout()
        sol = QVBoxLayout()
        sol.addWidget(etiket(BASLIK[secim], "Baslik"))
        self.alt_etiket = etiket(ALT[secim], "AltBaslik")
        sol.addWidget(self.alt_etiket)
        ust.addLayout(sol, 1)
        self.b_excel = QPushButton("Excel'e Aktar")
        self.b_rapor = QPushButton("Rapor Hazırla")
        self.b_rapor.setObjectName("Lacivert")
        self.b_excel.clicked.connect(self.excele_aktar)
        self.b_rapor.clicked.connect(lambda: ana.sayfa_ac("rapor"))
        for b in (self.b_excel, self.b_rapor):
            ust.addWidget(b, 0, Qt.AlignTop)
        kok.addLayout(ust)

        # özet kartları
        kr = QHBoxLayout()
        kr.setSpacing(12)
        self.k_genel = Kpi(f"GENEL ORTALAMA ({tema.METRIKLER[secim].upper()})")
        kr.addWidget(self.k_genel)
        self.k_v = {}
        self.combolar = {}
        for v in VARDIYALAR:
            c = SefCombo(ana, v, ana.donem_gunleri)
            self.combolar[v] = c
            k = Kpi(f"{v}. VARDİYA", c)
            self.k_v[v] = k
            kr.addWidget(k)
        kok.addLayout(kr)

        self.uyari = QLabel("")
        self.uyari.setObjectName("Uyari")
        self.uyari.setWordWrap(True)
        self.uyari.hide()
        kok.addWidget(self.uyari)

        orta = QHBoxLayout()
        orta.setSpacing(12)
        # sol: Excel görünümlü tablo
        self.tablo_w = CizimWidget(self._tablo_ciz, 300, 360, kopya_resim=self._tablo_resmi)
        self.tablo_w.setSizePolicy(self.tablo_w.sizePolicy().horizontalPolicy(), self.tablo_w.sizePolicy().verticalPolicy())
        self.tablo_w.setFixedWidth(400)
        sc = QScrollArea()
        sc.setWidgetResizable(False)
        sc.setWidget(self.tablo_w)
        sc.setFixedWidth(424)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        orta.addWidget(sc)
        # sağ: iki grafik
        sag = QVBoxLayout()
        sag.setSpacing(12)
        self.g_vardiya = CizimWidget(self._vardiya_ciz, 220, 300)
        self.g_makine = CizimWidget(self._makine_ciz, 240, 300)
        for g in (self.g_vardiya, self.g_makine):
            f = kart(kenar=6)
            f.layout().addWidget(g)
            sag.addWidget(f, 1)
        orta.addLayout(sag, 1)
        kok.addLayout(orta, 1)
        self.tablo_scroll = sc

    # ---------------------------------------------------------------- çizimler
    def _tablo_ciz(self, p, rect):
        s = self.ana.sonuc
        if s:
            cizim.tablo_ciz(p, rect, s, self.ana.ayar["makineler"], self.secim)

    def _vardiya_ciz(self, p, rect):
        s = self.ana.sonuc
        if s:
            cizim.vardiya_grafigi(p, rect, s, self.ana.seflar, self.secim)

    def _makine_ciz(self, p, rect):
        s = self.ana.sonuc
        if s:
            cizim.makine_grafigi(p, rect, s, self.ana.ayar["makineler"], self.secim, bos_goster=self.ana.ayar.get("idle_makineleri_goster", False))

    # ---------------------------------------------------------------- yenile
    def yenile(self):
        s = self.ana.sonuc
        olcu = OLCU[self.secim]
        if self.secim == 0:
            self.alt_etiket.setText(ALT[0])
        if not s:
            self.k_genel.d.setText("-")
            self.k_genel.a.setText("Önce Veri Aktar sayfasından dosya yükleyin" if not self.ana.kapsam() else "Gün seçilmedi")
            for v in VARDIYALAR:
                self.k_v[v].d.setText("-")
                self.k_v[v].a.setText("")
                self.combolar[v].yenile("")
            self.uyari.hide()
            self._tazele()
            return
        g = s.genel[self.secim]
        gun = s.hesap_gunu()
        self.k_genel.d.setText(tema.yuzde(g) if g is not None else "-")
        kural = dict(tema.YONTEMLER).get(self.ana.ayar.get("hesap_yontemi", "vardiya"), "").lower()
        self.k_genel.a.setText(f"{gun} gün · eşik %{self.ana.ayar['esik'] * 100:.0f} · {kural}")
        for v in VARDIYALAR:
            oz = s.vardiyalar[v]
            d = getattr(oz, olcu)
            self.k_v[v].d.setText(tema.yuzde(d) if d is not None else "veri yok")
            ms = f"{tema.sayi(oz.makine_sayisi)} makine · " if oz.makine_sayisi is not None else ""
            self.k_v[v].a.setText(f"{ms}{oz.gun_sayisi} gün")
            self.combolar[v].yenile(self.ana.seflar.get(v, ""))
        notlar = []
        gun_bos = {}
        for d, v in s.bos_vardiyalar:
            gun_bos.setdefault(d, []).append(v)
        bos = [f"{d.strftime('%d.%m')} " + ("tüm vardiyalar" if len(vs) == 3 else ", ".join(f"{v}.vardiya" for v in vs))
               for d, vs in sorted(gun_bos.items())]
        if bos:
            notlar.append("Ortalamaya girmeyen günler/vardiyalar (hiçbir makine eşiği geçemedi: tatil, kapalı vardiya): " + " · ".join(bos[:8]) + (" …" if len(bos) > 8 else ""))
        self.uyari.setText("\n".join(notlar))
        self.uyari.setVisible(bool(notlar))
        self._tazele()

    def _tazele(self):
        n = len(self.ana.ayar["makineler"])
        if self.ana.sonuc:
            n = max(n, len(set(self.ana.ayar["makineler"]) | set(self.ana.sonuc.hucreler)))
        self.tablo_w.setFixedHeight(max(360, (n + 4) * 26))
        for w in (self.tablo_w, self.g_vardiya, self.g_makine):
            w.update()

    # ---------------------------------------------------------------- işlemler
    def _tablo_resmi(self):
        if not self.ana.sonuc:
            return None
        return cizim.tablo_resmi(self.ana.sonuc, self.ana.ayar["makineler"], self.secim, 700)

    def excele_aktar(self):
        s = self.ana.sonuc
        if not s:
            return
        ilk, son = s.gunler[0], s.gunler[-1]
        ad = f"{BASLIK[self.secim]} {ilk:%d.%m.%Y}-{son:%d.%m.%Y}.xlsx"
        yol, _ = QFileDialog.getSaveFileName(self, "Excel olarak kaydet", ad, "Excel (*.xlsx)")
        if not yol:
            return
        from .disa_aktar import excel_yaz
        excel_yaz(yol, s, self.ana.ayar["makineler"], self.secim, self.ana.seflar, self.ana.ayar)
        self.ana.mesaj(f"Kaydedildi: {yol}")
