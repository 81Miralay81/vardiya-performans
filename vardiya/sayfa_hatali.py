"""Hatalı Duruşlar sayfası (Performans altında, Çalışma sayfası gibi dönem çubuğuyla).

Hatalı duruş: Ayarlar'da seçilen duruşlar (ör. İŞ EMRİ PLAN YOK) sürerken makinede operatör kayıtlı ya da iş (ürün kodu)
görünmesi. Doğru olan kısım gösterilmez; yalnızca bu durumların süresi.

Kırılım sırası (her seviye bir öncekine tıklayınca altta açılır, aynı yere yeniden tıklamak kapatır):
  1. Makine bazlı hatalı duruş süresi.
  2. Seçili makine: vardiyaya göre | duruş adına göre.
  3. Seçilen vardiya / duruş: operatöre göre | işe (ürün koduna) göre.
  4. Seçilen operatör / iş: zaman çizelgesi (gant), o hatalı duruşlar kırmızı taralı çerçeveli; altında olay listesi.
Veri okuma arka planda yapılır (pencere donmaz, bekleme kartı görünür). Kurallar hatali_durus.py'dedir.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel, QPushButton, QScrollArea, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from . import bekleme, cizim, cizim_ek, hatali_durus as hd, tema
from .sayfa_ortak import etiket
from .sayfa_performans import TikliCizim, _kart_baslikli

KUTU = (("toplam", "Toplam hatalı duruş", "#D64541"), ("adet", "Olay sayısı", "#2B3A8F"),
        (hd.TUR_OPERATOR, hd.TUR_AD[hd.TUR_OPERATOR], hd.TUR_RENK[hd.TUR_OPERATOR]),
        (hd.TUR_IS, hd.TUR_AD[hd.TUR_IS], hd.TUR_RENK[hd.TUR_IS]), ("makine", "Makine", "#3E9B2A"))


def _sa(saat: float) -> str:
    return f"{cizim._saat_dk(saat)} sa"


def _kapat_dugmesi(satir, fn):
    b = QPushButton("✕")
    b.setToolTip("Kapat")
    b.setFixedSize(28, 26)
    b.setCursor(Qt.PointingHandCursor)
    b.clicked.connect(fn)
    satir.addWidget(b)


class HataliSayfasi(QWidget):
    def __init__(self, ana):
        super().__init__()
        self.ana = ana
        self._olaylar: List[hd.Olay] = []
        self._donem: Optional[Tuple[date, date]] = None
        self._makine: Optional[str] = None
        self._s1: Optional[Tuple[str, str]] = None         # 2. seviye seçimi: ("vardiya", "1. Vardiya") | ("durus", ad)
        self._s2: Optional[Tuple[str, str]] = None         # 3. seviye seçimi: (TUR_OPERATOR, ad) | (TUR_IS, ürün kodu)
        self._liste: List[hd.Olay] = []
        self._is_no = 0
        dis = QVBoxLayout(self)
        dis.setContentsMargins(26, 22, 26, 22)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        ic = QWidget()
        kok = QVBoxLayout(ic)
        kok.setContentsMargins(0, 0, 8, 8)
        kok.setSpacing(12)
        sc.setWidget(ic)
        dis.addWidget(sc)
        self._sc = sc

        self.aciklama = etiket("", "AltBaslik")
        kok.addWidget(self.aciklama)

        # ------------------------------------------------ özet kutuları
        ust = QHBoxLayout()
        ust.setSpacing(10)
        self.kutu = {}
        for k, ad, renk in KUTU:
            f = QFrame()
            f.setObjectName("HKutu")
            f.setStyleSheet(f"QFrame#HKutu {{ background:{tema.KART}; border:1px solid {tema.CIZGI}; border-left:6px solid {renk}; border-radius:12px; }}")
            fl = QVBoxLayout(f)
            fl.setContentsMargins(14, 10, 12, 10)
            fl.setSpacing(2)
            d = QLabel("-")
            d.setStyleSheet(f"font-size:24px; font-weight:800; color:{renk}; background:transparent; border:none;")
            b = QLabel(ad)
            b.setStyleSheet(f"font-size:12px; font-weight:600; color:{tema.YAZI_SOLUK}; background:transparent; border:none;")
            fl.addWidget(d)
            fl.addWidget(b)
            self.kutu[k] = d
            ust.addWidget(f, 1)
        kok.addLayout(ust)

        # ------------------------------------------------ 1. makine
        k1, _b, self.m_alt, _s = _kart_baslikli("Makine bazlı hatalı duruşlar", "bir makineye tıklayın")
        self.g_makine = TikliCizim(lambda p, r, b: cizim_ek.kirilim_grafigi(
            p, r, [(m, x, "#D64541") for m, x in hd.makineye_gore(self._olaylar)], None, b, "makine", self._makine), 300, 320)
        self.g_makine.tiklandi.connect(lambda a, _k: self._makine_sec(a))
        self.g_makine.ipucu = lambda a, _k: self._makine_ipucu(a)
        k1.layout().addWidget(self.g_makine)
        kok.addWidget(k1)

        # ------------------------------------------------ 2. vardiya | duruş adı
        k2, self.k2_baslik, self.k2_alt, s2 = _kart_baslikli("Kırılım", "")
        self.g_v = self._grafik(lambda: [(a, x, tema.LACIVERT) for a, x in hd.vardiyaya_gore(self._makine_olaylari())],
                                "Vardiyaya göre (tıklayın)", "vardiya", 1)
        self.g_d = self._grafik(lambda: [(a, x, tema.durus_rengi(a)) for a, x in hd.durusa_gore(self._makine_olaylari())],
                                "Duruş adına göre (tıklayın)", "durus", 1)
        k2.layout().addLayout(self._ikili(self.g_v, self.g_d))
        _kapat_dugmesi(s2, self._makine_kapat)
        k2.hide()
        self.k2 = k2
        kok.addWidget(k2)

        # ------------------------------------------------ 3. operatör | iş
        k3, self.k3_baslik, self.k3_alt, s3 = _kart_baslikli("Kırılım", "")
        self.g_op = self._grafik(lambda: [(a, x, hd.TUR_RENK[hd.TUR_OPERATOR]) for a, x in hd.operatore_gore(self._s1_olaylari())],
                                 "Operatör var · operatöre göre (tıklayın)", hd.TUR_OPERATOR, 2)
        self.g_is = self._grafik(lambda: [(a, x, hd.TUR_RENK[hd.TUR_IS]) for a, x in hd.ise_gore(self._s1_olaylari())],
                                 "Operatör yok · iş var · ürün koduna göre (tıklayın)", hd.TUR_IS, 2)
        k3.layout().addLayout(self._ikili(self.g_op, self.g_is))
        _kapat_dugmesi(s3, self._s1_kapat)
        k3.hide()
        self.k3 = k3
        kok.addWidget(k3)

        # ------------------------------------------------ 4. zaman çizelgesi + olay listesi
        from .zaman_cizelgesi import ZamanCizelgesi
        k4, self.z_baslik, self.z_alt, s4 = _kart_baslikli("Zaman çizelgesi", "")
        self.zc = ZamanCizelgesi()
        k4.layout().addWidget(self.zc)
        self.tablo = QTableWidget()
        self.tablo.setColumnCount(8)
        self.tablo.setHorizontalHeaderLabels(["Tarih", "Vardiya", "Duruş", "Başlangıç", "Bitiş", "Süre", "Operatör", "Ürün kodu · iş emri"])
        self.tablo.verticalHeader().hide()
        self.tablo.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tablo.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tablo.setAlternatingRowColors(True)
        self.tablo.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tablo.horizontalHeader().setStretchLastSection(True)
        self.tablo.setMinimumHeight(160)
        self.tablo.setMaximumHeight(260)
        self.tablo.cellDoubleClicked.connect(self._olaya_git)
        k4.layout().addWidget(etiket("Olaylar · satıra çift tıklayın: çizelge o olaya yakınlaşır", "AltBaslik"))
        k4.layout().addWidget(self.tablo)
        _kapat_dugmesi(s4, self._s2_kapat)
        k4.hide()
        self.k4 = k4
        kok.addWidget(k4)
        kok.addStretch(1)

    # ---------------------------------------------------------------- yardımcılar
    @staticmethod
    def _ikili(sol, sag) -> QHBoxLayout:
        sat = QHBoxLayout()
        sat.setSpacing(12)
        sat.addWidget(sol, 1)
        sat.addWidget(sag, 1)
        return sat

    def _grafik(self, veri, baslik: str, tur: str, seviye: int) -> TikliCizim:
        def secili():
            s = self._s1 if seviye == 1 else self._s2
            return s[1] if s and s[0] == tur else None
        g = TikliCizim(lambda p, r, b: cizim_ek.kirilim_grafigi(p, r, veri(), baslik, b, tur, secili()), 300, 300)
        g.tiklandi.connect(lambda a, _k: (self._s1_sec if seviye == 1 else self._s2_sec)(tur, a))
        return g

    def _makine_olaylari(self) -> List[hd.Olay]:
        return [o for o in self._olaylar if o.makine == self._makine]

    def _s1_olaylari(self) -> List[hd.Olay]:
        lst = self._makine_olaylari()
        if not self._s1:
            return lst
        tur, d = self._s1
        if tur == "vardiya":
            v = int(str(d).split(".")[0])
            return [o for o in lst if hd.olay_vardiyada(o, v)]
        return [o for o in lst if o.tip == d]

    def _s2_olaylari(self) -> List[hd.Olay]:
        lst = self._s1_olaylari()
        if not self._s2:
            return lst
        tur, d = self._s2
        if tur == hd.TUR_OPERATOR:
            return [o for o in lst if o.tur == hd.TUR_OPERATOR and o.operator == d]
        return [o for o in lst if o.tur == hd.TUR_IS and o.is_ad == d]

    @staticmethod
    def _s_yazi(s) -> str:
        if not s:
            return ""
        tur, d = s
        return {"vardiya": "", "durus": "", hd.TUR_OPERATOR: "operatör ", hd.TUR_IS: "iş "}.get(tur, "") + str(d)

    def _makine_ipucu(self, m) -> str:
        lst = [o for o in self._olaylar if o.makine == m]
        op = sum(o.saat for o in lst if o.tur == hd.TUR_OPERATOR)
        is_ = sum(o.saat for o in lst if o.tur == hd.TUR_IS)
        return (f"<b>{m}</b><br>{len(lst)} hatalı duruş · {_sa(op + is_)}<br>{hd.TUR_AD[hd.TUR_OPERATOR]}: {_sa(op)}"
                f"<br>{hd.TUR_AD[hd.TUR_IS]}: {_sa(is_)}<br><span style='color:#8a90a2'>tıklayın: kırılım</span>")

    def _ciz(self):
        for g in (self.g_makine, self.g_v, self.g_d, self.g_op, self.g_is):
            g.update()

    # ---------------------------------------------------------------- seviyeler
    def _makine_sec(self, m):
        if m == self._makine and self.k2.isVisible():
            self._makine_kapat()
            return
        self._makine, self._s1, self._s2 = m, None, None
        lst = self._makine_olaylari()
        self.k2_baslik.setText(f"{m} · hatalı duruşlar")
        self.k2_alt.setText(f"{len(lst)} olay · {_sa(sum(o.saat for o in lst))} · vardiyaya ya da duruşa tıklayın: altta operatör ve iş kırılımı")
        self.k3.hide()
        self.k4.hide()
        self.k2.show()
        self._ciz()
        bekleme.kaydir(self._sc, self.k2)

    def _makine_kapat(self):
        self._makine, self._s1, self._s2 = None, None, None
        for k in (self.k2, self.k3, self.k4):
            k.hide()
        self._ciz()

    def _s1_sec(self, tur, deger):
        if self._s1 == (tur, deger) and self.k3.isVisible():
            self._s1_kapat()
            return
        self._s1, self._s2 = (tur, deger), None
        lst = self._s1_olaylari()
        self.k3_baslik.setText(f"{self._makine} · {self._s_yazi(self._s1)}")
        op = sum(o.saat for o in lst if o.tur == hd.TUR_OPERATOR)
        is_ = sum(o.saat for o in lst if o.tur == hd.TUR_IS)
        self.k3_alt.setText(f"{len(lst)} olay · operatör var {_sa(op)} · operatör yok, iş var {_sa(is_)} · bir sütuna tıklayın: zaman çizelgesi")
        self.k4.hide()
        self.k3.show()
        self._ciz()
        bekleme.kaydir(self._sc, self.k3)

    def _s1_kapat(self):
        self._s1, self._s2 = None, None
        self.k3.hide()
        self.k4.hide()
        self._ciz()

    def _s2_sec(self, tur, deger):
        if self._s2 == (tur, deger) and self.k4.isVisible():
            self._s2_kapat()
            return
        self._s2 = (tur, deger)
        self._ciz()
        self._liste_yaz()
        self._gantt_yaz()

    def _s2_kapat(self):
        self._s2 = None
        self.k4.hide()
        self._ciz()

    # ---------------------------------------------------------------- 4. seviye
    def _liste_yaz(self):
        lst = self._s2_olaylari()
        t = self.tablo
        t.setSortingEnabled(False)
        t.setRowCount(len(lst))
        for i, o in enumerate(lst):
            dk = int(round(o.saat * 60))
            deg = [f"{o.bas:%d.%m.%Y}", f"{o.vardiya}. vardiya", o.tip, f"{o.bas:%H:%M}",
                   f"{o.bit:%d.%m %H:%M}" if o.bit.date() != o.bas.date() else f"{o.bit:%H:%M}", f"{dk // 60}:{dk % 60:02d}",
                   o.operator or "-", " · ".join(x for x in (o.urun, o.is_emri) if x) or "-"]
            for j, x in enumerate(deg):
                it = QTableWidgetItem(x)
                if j == 0:
                    it.setData(Qt.UserRole, i)
                t.setItem(i, j, it)
        self._liste = lst

    def _gantt_yaz(self, gorunum: Optional[Tuple[datetime, datetime]] = None):
        if not self._makine or not self._donem:
            return
        ilk, son = self._donem
        m, lst = self._makine, self._s2_olaylari()
        self._is_no += 1
        no = self._is_no
        yazi = f"{m} · {self._s_yazi(self._s1)} · {self._s_yazi(self._s2)}"

        def bitti(sonuc):
            if no != self._is_no:
                return                                      # bu arada başka seçim yapıldı
            if isinstance(sonuc, Exception):
                self.z_alt.setText(f"Zaman çizelgesi okunamadı: {sonuc}")
                return
            t0 = datetime(ilk.year, ilk.month, ilk.day)
            t1 = datetime(son.year, son.month, son.day) + timedelta(days=1)
            gor = gorunum
            if gor is None and lst:                         # ilk açılışta seçili olayların olduğu aralığa yakınlaş
                a, b = min(o.bas for o in lst), max(o.bit for o in lst)
                pay = max(timedelta(hours=1), (b - a) * 0.08)
                gor = (max(t0, a - pay), min(t1, b + pay))
            self.z_baslik.setText(f"{yazi} · zaman çizelgesi")
            self.z_alt.setText(f"{len(lst)} olay · {_sa(sum(o.saat for o in lst))} · kırmızı taralı çerçeve: hatalı duruş · tekerlek: yakınlaştır")
            self.zc.ayarla([m], sonuc, t0, t1, "#F2A7A3", "hatalı duruş", gor)
            self.k4.show()
            bekleme.kaydir(self._sc, self.k4)
        bekleme.arka_planda(self, self.ana.db_yolu, "Zaman çizelgesi hazırlanıyor",
                            f"{m} makinesinin {ilk:%d.%m} – {son:%d.%m} kayıtları okunuyor",
                            lambda con: hd.zaman_bloklari(con, m, ilk, son, lst), bitti)

    def _olaya_git(self, satir, _sutun):
        it = self.tablo.item(satir, 0)
        if it is None or it.data(Qt.UserRole) is None:
            return
        o = self._liste[int(it.data(Qt.UserRole))]
        pay = max(timedelta(minutes=30), (o.bit - o.bas) * 0.5)
        self.zc.cizelge.gorunum((o.bas - pay).timestamp(), (o.bit + pay).timestamp())
        bekleme.kaydir(self._sc, self.k4)

    # ---------------------------------------------------------------- dönem
    def yenile(self):
        gunler = self.ana.donem_gunleri()
        ayar = self.ana.ayar
        turler = hd.kontrol_turleri(ayar)
        esik = ayar.get("hatali_durus_en_az_dk", hd.VARSAYILAN_EN_AZ_DK)
        self.aciklama.setText(
            "Kontrol edilen duruşlar: " + (", ".join(turler) if turler else "— Ayarlar > Duruşlar kartında seçin —")
            + f". Bu duruşlar sürerken makinede operatör kayıtlıysa (mor) ya da iş / ürün kodu görünüyorsa (turuncu) o süre burada "
            f"gösterilir; doğru olan kısım gösterilmez. {esik} dk'dan kısa olanlar listelenmez.")
        if not gunler or not turler:
            self._donem = None
            self._olaylar_geldi([])
            return
        self._donem = (min(gunler), max(gunler))
        ilk, son = self._donem
        makineler = ayar.get("makineler") or None
        self._is_no += 1
        no = self._is_no

        def bitti(sonuc):
            if no != self._is_no:
                return
            if isinstance(sonuc, Exception):
                self.aciklama.setText(f"Hatalı duruşlar okunamadı: {sonuc}")
                sonuc = []
            self._olaylar_geldi(sonuc)
        bekleme.arka_planda(self, self.ana.db_yolu, "Hatalı duruşlar hazırlanıyor",
                            f"{ilk:%d.%m.%Y} – {son:%d.%m.%Y} arasındaki kayıtlar kontrol ediliyor",
                            lambda con: hd.tespit(con, ilk, son, ayar, makineler), bitti)

    def _olaylar_geldi(self, lst):
        self._olaylar = lst
        op = sum(o.saat for o in lst if o.tur == hd.TUR_OPERATOR)
        is_ = sum(o.saat for o in lst if o.tur == hd.TUR_IS)
        self.kutu["toplam"].setText(_sa(op + is_))
        self.kutu["adet"].setText(str(len(lst)))
        self.kutu[hd.TUR_OPERATOR].setText(_sa(op))
        self.kutu[hd.TUR_IS].setText(_sa(is_))
        self.kutu["makine"].setText(str(len({o.makine for o in lst})))
        self.m_alt.setText("bir makineye tıklayın: vardiya ve duruş kırılımı" if lst else "seçili dönemde hatalı duruş yok")
        if self._makine and not any(o.makine == self._makine for o in lst):
            self._makine_kapat()
        elif self._makine:
            m = self._makine
            self._makine = None
            self._makine_sec(m)
        self._ciz()
