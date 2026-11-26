"""Hatalı Duruşlar sayfası (Performans altında, Çalışma sayfası gibi dönem çubuğuyla).

Kırılım sırası:
  1. Makine bazlı hatalı duruş süresi (tek grafik) — makineye tıklayın.
  2. Seçili makine: vardiyaya göre | "Operatör var" (operatöre göre) | "Operatör yok · iş var" (ürün koduna göre),
     altında duruş adına göre ve zamana (güne) göre — bir sütuna tıklamak süzgeç olur (yeniden tıklayınca kalkar).
  3. Süzgece uyan olayların listesi — satıra çift tıklayın: zaman çizelgesi o olaya yakınlaşır.
  4. Zaman çizelgesi (gant): makinenin tüm kayıtları; süzgece uyan hatalı duruşlar kırmızı taralı çerçeveli.
Kurallar ve tanımlar hatali_durus.py'dedir; seçimler Ayarlar > Duruşlar kartındadır.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel, QPushButton, QScrollArea, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from . import cizim, cizim_ek, hatali_durus as hd, tema
from .sayfa_ortak import etiket, kart
from .sayfa_performans import TikliCizim, _kart_baslikli

KUTU = (("toplam", "Toplam hatalı duruş", "#D64541"), ("adet", "Olay sayısı", "#2B3A8F"),
        (hd.TUR_OPERATOR, hd.TUR_AD[hd.TUR_OPERATOR], hd.TUR_RENK[hd.TUR_OPERATOR]),
        (hd.TUR_IS, hd.TUR_AD[hd.TUR_IS], hd.TUR_RENK[hd.TUR_IS]), ("makine", "Makine", "#3E9B2A"))


def _acik(renk: str, t: float) -> str:
    r, g, b = (int(renk[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(int(x + (255 - x) * t) for x in (r, g, b))


def _sa(saat: float) -> str:
    return f"{cizim._saat_dk(saat)} sa"


class HataliSayfasi(QWidget):
    def __init__(self, ana):
        super().__init__()
        self.ana = ana
        self._olaylar: List[hd.Olay] = []
        self._donem: Optional[Tuple[date, date]] = None
        self._makine: Optional[str] = None
        self._suzgec: Optional[Tuple[str, str]] = None       # (tür, değer): vardiya / operator / is / durus / gun
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

        # ------------------------------------------------ özet kutuları (renkli)
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

        # ------------------------------------------------ 1. makine bazlı
        k1, _b, self.m_alt, _s = _kart_baslikli("Makine bazlı hatalı duruşlar", "bir makineye tıklayın")
        self.g_makine = TikliCizim(lambda p, r, b: cizim_ek.kirilim_grafigi(
            p, r, [(m, x, "#D64541") for m, x in hd.makineye_gore(self._olaylar)], None, b, "makine", self._makine), 300, 320)
        self.g_makine.tiklandi.connect(lambda a, _k: self._makine_sec(a))
        self.g_makine.ipucu = lambda a, _k: self._makine_ipucu(a)
        k1.layout().addWidget(self.g_makine)
        kok.addWidget(k1)

        # ------------------------------------------------ 2. makine kırılımı
        k2, self.k_baslik, self.k_alt, s2 = _kart_baslikli("Kırılım", "")
        self.g_v = self._grafik(lambda: [(a, x, tema.LACIVERT) for a, x in hd.vardiyaya_gore(self._makine_olaylari())],
                                "Vardiyaya göre", "vardiya")
        self.g_d = self._grafik(lambda: [(a, x, tema.durus_rengi(a)) for a, x in hd.durusa_gore(self._makine_olaylari())],
                                "Duruş adına göre", "durus")
        self.g_op = self._grafik(lambda: [(a, x, hd.TUR_RENK[hd.TUR_OPERATOR]) for a, x in hd.operatore_gore(self._makine_olaylari())],
                                 "Operatör var (operatöre göre)", hd.TUR_OPERATOR)
        self.g_is = self._grafik(lambda: [(a, x, hd.TUR_RENK[hd.TUR_IS]) for a, x in hd.ise_gore(self._makine_olaylari())],
                                 "Operatör yok · iş var (ürün koduna göre)", hd.TUR_IS)
        self.g_gun = TikliCizim(lambda p, r, b: cizim_ek.zaman_grafigi(
            p, r, hd.gune_gore(self._makine_olaylari(), *self._donem) if self._donem else [], "gun", "Zamana göre (güne tıklayın)",
            b, self._suzgec[1] if self._suzgec and self._suzgec[0] == "gun" else None, "#D64541"), 280, 320)
        self.g_gun.tiklandi.connect(lambda a, _k: self._suz("gun", a))
        for sol, sag in ((self.g_v, self.g_d), (self.g_op, self.g_is)):        # ikişer yan yana
            sat = QHBoxLayout()
            sat.setSpacing(12)
            sat.addWidget(sol, 1)
            sat.addWidget(sag, 1)
            k2.layout().addLayout(sat)
        k2.layout().addWidget(self.g_gun)
        b_k = QPushButton("✕")
        b_k.setToolTip("Kapat")
        b_k.setFixedSize(28, 26)
        b_k.clicked.connect(self._makine_kapat)
        s2.addWidget(b_k)
        k2.hide()
        self.k_kirilim = k2
        kok.addWidget(k2)

        # ------------------------------------------------ 3. olay listesi
        k3, self.l_baslik, self.l_alt, s3 = _kart_baslikli("Hatalı duruş listesi", "")
        self.b_suz = QPushButton("Süzgeci kaldır")
        self.b_suz.setObjectName("Hizli")
        self.b_suz.clicked.connect(lambda: self._suz(None, None))
        s3.addWidget(self.b_suz)
        self.tablo = QTableWidget()
        self.tablo.setColumnCount(9)
        self.tablo.setHorizontalHeaderLabels(["Tarih", "Vardiya", "Duruş", "Başlangıç", "Bitiş", "Süre", "Hata türü", "Operatör",
                                              "Ürün kodu · iş emri"])
        self.tablo.verticalHeader().hide()
        self.tablo.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tablo.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tablo.setAlternatingRowColors(True)
        self.tablo.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tablo.horizontalHeader().setStretchLastSection(True)
        self.tablo.setMinimumHeight(220)
        self.tablo.setMaximumHeight(320)
        self.tablo.cellDoubleClicked.connect(self._olaya_git)
        k3.layout().addWidget(self.tablo)
        k3.hide()
        self.k_liste = k3
        kok.addWidget(k3)

        # ------------------------------------------------ 4. zaman çizelgesi
        from .zaman_cizelgesi import ZamanCizelgesi
        k4, self.z_baslik, self.z_alt, s4 = _kart_baslikli("Zaman çizelgesi", "")
        self.zc = ZamanCizelgesi()
        k4.layout().addWidget(self.zc)
        b_z = QPushButton("✕")
        b_z.setToolTip("Kapat")
        b_z.setFixedSize(28, 26)
        b_z.clicked.connect(lambda: self.k_gantt.hide())
        s4.addWidget(b_z)
        k4.hide()
        self.k_gantt = k4
        kok.addWidget(k4)
        kok.addStretch(1)

    # ---------------------------------------------------------------- yardımcılar
    def _grafik(self, veri, baslik: str, tur: str) -> TikliCizim:
        g = TikliCizim(lambda p, r, b: cizim_ek.kirilim_grafigi(
            p, r, veri(), baslik, b, tur, self._suzgec[1] if self._suzgec and self._suzgec[0] == tur else None), 300, 300)
        g.tiklandi.connect(lambda a, _k, t=tur: self._suz(t, a))
        return g

    def _makine_olaylari(self) -> List[hd.Olay]:
        return [o for o in self._olaylar if o.makine == self._makine]

    def _suzulmus(self) -> List[hd.Olay]:
        lst = self._makine_olaylari()
        if not self._suzgec:
            return lst
        tur, d = self._suzgec
        if tur == "vardiya":
            v = int(str(d).split(".")[0])
            return [o for o in lst if hd.olay_vardiyada(o, v)]
        if tur == hd.TUR_OPERATOR:
            return [o for o in lst if o.tur == hd.TUR_OPERATOR and o.operator == d]
        if tur == hd.TUR_IS:
            return [o for o in lst if o.tur == hd.TUR_IS and o.is_ad == d]
        if tur == "durus":
            return [o for o in lst if o.tip == d]
        if tur == "gun":
            g = date.fromisoformat(str(d)[:10])
            g0 = datetime(g.year, g.month, g.day)
            return [o for o in lst if o.bas < g0 + timedelta(days=1) and o.bit > g0]
        return lst

    def _makine_ipucu(self, m) -> str:
        lst = [o for o in self._olaylar if o.makine == m]
        op = sum(o.saat for o in lst if o.tur == hd.TUR_OPERATOR)
        is_ = sum(o.saat for o in lst if o.tur == hd.TUR_IS)
        return (f"<b>{m}</b><br>{len(lst)} hatalı duruş · {_sa(op + is_)}<br>{hd.TUR_AD[hd.TUR_OPERATOR]}: {_sa(op)}"
                f"<br>{hd.TUR_AD[hd.TUR_IS]}: {_sa(is_)}<br><span style='color:#8a90a2'>tıklayın: kırılım</span>")

    # ---------------------------------------------------------------- davranış
    def _makine_sec(self, m):
        if m == self._makine and self.k_kirilim.isVisible():
            self._makine_kapat()
            return
        self._makine, self._suzgec = m, None
        lst = self._makine_olaylari()
        self.k_baslik.setText(f"{m} · hatalı duruşlar")
        self.k_alt.setText(f"{len(lst)} olay · {_sa(sum(o.saat for o in lst))} · bir sütuna tıklayın: liste ve zaman çizelgesi o seçime "
                           "göre süzülür (yeniden tıklayınca kalkar)")
        self.k_kirilim.show()
        self.k_liste.show()
        self._liste_yaz()
        self._gantt_yaz()
        self._ciz()
        self._sc.ensureWidgetVisible(self.k_kirilim, 0, 30)

    def _makine_kapat(self):
        self._makine, self._suzgec = None, None
        for k in (self.k_kirilim, self.k_liste, self.k_gantt):
            k.hide()
        self.g_makine.update()

    def _suz(self, tur, deger):
        if tur is None or (self._suzgec == (tur, deger)):
            self._suzgec = None
        else:
            self._suzgec = (tur, deger)
        self._liste_yaz()
        self._gantt_yaz()
        self._ciz()
        if self._suzgec:
            self._sc.ensureWidgetVisible(self.k_liste, 0, 30)

    def _ciz(self):
        for g in (self.g_makine, self.g_v, self.g_op, self.g_is, self.g_d, self.g_gun):
            g.update()

    def _suzgec_yazi(self) -> str:
        if not self._suzgec:
            return "süzgeç yok (makinenin tüm hatalı duruşları)"
        tur, d = self._suzgec
        ad = {"vardiya": "vardiya", hd.TUR_OPERATOR: "operatör", hd.TUR_IS: "operatörsüz iş", "durus": "duruş", "gun": "gün"}[tur]
        if tur == "gun":
            d = date.fromisoformat(str(d)[:10]).strftime("%d.%m.%Y")
        return f"süzgeç: {ad} = {d}"

    def _liste_yaz(self):
        lst = self._suzulmus()
        self.l_baslik.setText(f"{self._makine} · hatalı duruş listesi")
        self.l_alt.setText(f"{len(lst)} olay · {_sa(sum(o.saat for o in lst))} · {self._suzgec_yazi()} · satıra çift tıklayın: "
                           "zaman çizelgesi o olaya yakınlaşır")
        self.b_suz.setVisible(bool(self._suzgec))
        t = self.tablo
        t.setSortingEnabled(False)
        t.setRowCount(len(lst))
        for i, o in enumerate(lst):
            dk = int(round(o.saat * 60))
            deg = [f"{o.bas:%d.%m.%Y}", f"{o.vardiya}. vardiya", o.tip, f"{o.bas:%H:%M}", f"{o.bit:%d.%m %H:%M}" if o.bit.date() != o.bas.date()
                   else f"{o.bit:%H:%M}", f"{dk // 60}:{dk % 60:02d}", hd.TUR_AD[o.tur], o.operator or "-",
                   " · ".join(x for x in (o.urun, o.is_emri) if x) or "-"]
            for j, x in enumerate(deg):
                it = QTableWidgetItem(x)
                if j == 0:
                    it.setData(Qt.UserRole, i)
                if j == 6:
                    it.setForeground(Qt.white)
                    it.setBackground(_q(hd.TUR_RENK[o.tur]))
                t.setItem(i, j, it)
        self._liste = lst

    def _gantt_yaz(self, gorunum: Optional[Tuple[datetime, datetime]] = None):
        if not self._makine or not self._donem:
            return
        ilk, son = self._donem
        lst = self._suzulmus()
        try:
            bloklar = hd.zaman_bloklari(self.ana.con, self._makine, ilk, son, lst)
        except Exception as e:  # noqa: BLE001
            self.z_alt.setText(f"Zaman çizelgesi okunamadı: {e}")
            return
        t0 = datetime(ilk.year, ilk.month, ilk.day)
        t1 = datetime(son.year, son.month, son.day) + timedelta(days=1)
        if gorunum is None and self._suzgec and self._suzgec[0] == "gun":
            g = date.fromisoformat(str(self._suzgec[1])[:10])
            gorunum = (datetime(g.year, g.month, g.day), datetime(g.year, g.month, g.day) + timedelta(days=1))
        self.z_baslik.setText(f"{self._makine} · zaman çizelgesi")
        self.z_alt.setText(f"{self._suzgec_yazi()} · kırmızı taralı çerçeve: hatalı duruş · yakınlaştırınca çerçeve de büyür")
        self.zc.ayarla([self._makine], bloklar, t0, t1, "#F2A7A3", "hatalı duruş", gorunum)
        self.k_gantt.show()

    def _olaya_git(self, satir, _sutun):
        it = self.tablo.item(satir, 0)
        if it is None or it.data(Qt.UserRole) is None:
            return
        o = self._liste[int(it.data(Qt.UserRole))]
        pay = max(timedelta(minutes=30), (o.bit - o.bas) * 0.5)
        self._gantt_yaz((o.bas - pay, o.bit + pay))
        self._sc.ensureWidgetVisible(self.k_gantt, 0, 30)

    # ---------------------------------------------------------------- dönem
    def yenile(self):
        gunler = self.ana.donem_gunleri()
        ayar = self.ana.ayar
        turler = hd.kontrol_turleri(ayar)
        esik = ayar.get("hatali_durus_en_az_dk", hd.VARSAYILAN_EN_AZ_DK)
        self.aciklama.setText(
            "Kontrol edilen duruşlar: " + (", ".join(turler) if turler else "— Ayarlar > Duruşlar kartında seçin —")
            + f". Bu duruşlarda makinede operatör ve iş (ürün kodu) olmamalı; varsa hatalı sayılır. {esik} dk'dan kısa olanlar "
            "listelenmez. Mor: duruş sırasında operatör kayıtlı · turuncu: operatör yok ama iş var.")
        if not gunler or not turler:
            self._olaylar, self._donem = [], None
        else:
            self._donem = (min(gunler), max(gunler))
            try:
                self._olaylar = hd.tespit(self.ana.con, self._donem[0], self._donem[1], ayar, ayar.get("makineler") or None)
            except Exception as e:  # noqa: BLE001
                self._olaylar = []
                self.aciklama.setText(f"Hatalı duruşlar okunamadı: {e}")
        lst = self._olaylar
        op = sum(o.saat for o in lst if o.tur == hd.TUR_OPERATOR)
        is_ = sum(o.saat for o in lst if o.tur == hd.TUR_IS)
        self.kutu["toplam"].setText(_sa(op + is_))
        self.kutu["adet"].setText(str(len(lst)))
        self.kutu[hd.TUR_OPERATOR].setText(_sa(op))
        self.kutu[hd.TUR_IS].setText(_sa(is_))
        self.kutu["makine"].setText(str(len({o.makine for o in lst})))
        self.m_alt.setText("bir makineye tıklayın: vardiya, operatör ve iş kırılımı" if lst else "seçili dönemde hatalı duruş yok")
        if self._makine and not any(o.makine == self._makine for o in lst):
            self._makine_kapat()
        elif self._makine:
            self._suzgec = None
            self._liste_yaz()
            self._gantt_yaz()
        self._ciz()


def _q(renk: str):
    from PySide6.QtGui import QColor
    return QColor(renk)
