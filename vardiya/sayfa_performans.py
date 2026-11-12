"""Performans sayfası (programın kendi çizimi; tarayıcı motoru kullanılmaz, açılışı yavaşlatmaz).

Makine sütunları hep %100'dür (çalışma + duruş); sıfırın altında mola hakkı gösterilir (mola yapılan / molada çalışılan).
Sütunun çalışma ya da duruş kısmına tıklayınca altta o makinenin duruşları büyükten küçüğe, mola kısmına tıklayınca
vardiya bazlı mola pastaları açılır. 'Cormind rapor sistemi' düğmesi Cormind'in kendi hesabını ayrı bir bölümde gösterir."""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QToolTip, QVBoxLayout, QWidget

from . import cizim, tema
from .hesap import VARDIYALAR, cormind_hesabi, durus_dokumu
from .sayfa_ortak import CizimWidget, etiket, kart


class TikliCizim(CizimWidget):
    """Çizim alanı: çizim sırasında bildirilen bölgelere tıklamayı ve üzerine gelince bilgi kutusunu destekler."""
    tiklandi = Signal(object, object)          # (anahtar, kısım)

    def __init__(self, cizici: Callable, min_h: int, min_w: int = 200):
        super().__init__(None, min_h, min_w, kopya_resim=lambda: self.resim(2.0))
        self._asil = cizici
        self._kayit = False
        self.bolgeler: List[tuple] = []          # (QRectF, anahtar, kısım)
        self.ipucu: Optional[Callable[[object, object], str]] = None
        self.cizici = self._ciz
        self.setMouseTracking(True)

    def _ciz(self, p, rect):
        self._asil(p, rect, self.bolgeler if self._kayit else None)

    def paintEvent(self, e):
        self.bolgeler = []
        self._kayit = True
        try:
            super().paintEvent(e)
        finally:
            self._kayit = False

    def _bul(self, nokta):
        for r, anahtar, kisim in self.bolgeler:
            if r.contains(nokta):
                return anahtar, kisim
        return None

    def mouseMoveEvent(self, e):
        b = self._bul(e.position())
        self.setCursor(Qt.PointingHandCursor if b else Qt.ArrowCursor)
        if b and self.ipucu:
            QToolTip.showText(e.globalPosition().toPoint(), self.ipucu(*b), self)
        else:
            QToolTip.hideText()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            b = self._bul(e.position())
            if b:
                self.tiklandi.emit(*b)
        super().mouseReleaseEvent(e)


class _Kutu(QFrame):
    def __init__(self, baslik: str):
        super().__init__()
        self.setObjectName("Kart")
        l = QVBoxLayout(self)
        l.setContentsMargins(16, 10, 16, 10)
        l.setSpacing(1)
        l.addWidget(etiket(baslik, "KartBaslik"))
        self.d = QLabel("-")
        self.d.setObjectName("KartDeger")
        self.a = etiket("", "AltBaslik")
        self.a.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.s = QLabel("")
        self.s.setStyleSheet(f"color: {tema.YESIL}; font-weight: 700;")
        for w in (self.d, self.a, self.s):
            l.addWidget(w)


def _kart_baslikli(baslik: str, alt: str = ""):
    k = kart(kenar=12)
    sat = QHBoxLayout()
    b = QLabel(baslik)
    b.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {tema.LACIVERT};")
    a = etiket(alt, "AltBaslik")
    a.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    a.setMinimumWidth(40)
    sat.addWidget(b)
    sat.addWidget(a, 1)
    k.layout().addLayout(sat)
    return k, b, a, sat


class PerformansSayfasi(QWidget):
    def __init__(self, ana):
        super().__init__()
        self.ana = ana
        self.web = None                      # eski (web tabanlı) sürümle uyum: artık kullanılmıyor
        self._secili: Optional[str] = None
        self._mod = "durus"
        self._dokum: Dict[str, Dict[str, float]] = {}
        self._cormind: Dict[str, dict] = {}
        self._mola_pay, self._mola_dk = 9.09, 40.0
        dis = QVBoxLayout(self)
        dis.setContentsMargins(26, 22, 26, 22)
        dis.setSpacing(0)
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

        # ---------------------------------------------------------------- özet kutuları
        ust = QHBoxLayout()
        ust.setSpacing(12)
        self.k_genel = _Kutu("GENEL ORTALAMA (ÇALIŞMA)")
        ust.addWidget(self.k_genel, 5)
        self.k_v = {}
        for v in VARDIYALAR:
            self.k_v[v] = _Kutu(f"{v}. VARDİYA")
            ust.addWidget(self.k_v[v], 4)
        kok.addLayout(ust)

        # ---------------------------------------------------------------- tablo + grafikler
        orta = QHBoxLayout()
        orta.setSpacing(12)
        kt = kart(kenar=8)
        self.tablo = TikliCizim(self._tablo_ciz, 300, 320)
        self.tablo.setFixedWidth(330)
        self.tablo.tiklandi.connect(lambda m, _k: self._sec(m, "durus"))
        kt.layout().addWidget(self.tablo)
        kt.layout().addStretch(1)
        orta.addWidget(kt, 0)
        sag = QVBoxLayout()
        sag.setSpacing(12)
        kv, _b, self.donem_etiketi, _s = _kart_baslikli("Vardiya bazlı çalışma oranı")
        self.g_vardiya = CizimWidget(self._vardiya_ciz, 230, 300, kopya_resim=lambda: self.g_vardiya.resim(2.0))
        kv.layout().addWidget(self.g_vardiya)
        sag.addWidget(kv)
        km, _b, _a, sat = _kart_baslikli("Makine bazlı performans",
                                         "sütunun çalışma ya da duruş kısmına tıklayın: duruşlar · mola kısmına tıklayın: vardiya bazlı mola")
        self.b_cormind = QPushButton("Cormind rapor sistemi")
        self.b_cormind.setObjectName("Lacivert")
        self.b_cormind.setCheckable(True)
        self.b_cormind.toggled.connect(self._cormind_goster)
        sat.addWidget(self.b_cormind)
        self.g_makine = TikliCizim(self._makine_ciz, 400, 300)
        self.g_makine.tiklandi.connect(self._sec)
        self.g_makine.ipucu = self._makine_ipucu
        km.layout().addWidget(self.g_makine)
        sag.addWidget(km, 1)
        orta.addLayout(sag, 1)
        kok.addLayout(orta)

        # ---------------------------------------------------------------- ayrıntı
        kd, self.d_baslik, self.d_alt, _s = _kart_baslikli("Ayrıntı", "yukarıdaki grafikte bir makineye tıklayın")
        self.g_detay = CizimWidget(self._detay_ciz, 340, 300, kopya_resim=lambda: self.g_detay.resim(2.0))
        kd.layout().addWidget(self.g_detay)
        self.k_detay = kd
        kok.addWidget(kd)

        # ---------------------------------------------------------------- Cormind rapor sistemi
        kc, _b, self.c_alt, _s = _kart_baslikli("Cormind rapor sistemi")
        kc.layout().addWidget(etiket(
            "Bu bölüm Cormind'in kendi hesabıdır ve yukarıdaki hesaptan bağımsızdır: eşik ve hesap yöntemi uygulanmaz. Cormind çalışma süresini "
            "toplamaz; duruşları net süreye (her 480 dakikanın 440'ı) böler, mola hakkını düşer ve OEE = 100 − toplam der. Kaydı olmayan süre "
            "çalışılmış sayılır; hiç kaydı olmayan makine %100 görünür.", "AltBaslik"))
        self.g_oee = CizimWidget(lambda p, r: cizim.cormind_oee_grafigi(p, r, self._cormind, "OEE Grafiği (Cormind)"), 300, 300,
                                 kopya_resim=lambda: self.g_oee.resim(2.0))
        self.g_zaman = CizimWidget(lambda p, r: cizim.cormind_durus_grafigi(p, r, self._cormind, "Zaman Dağılım Grafiği (Cormind)"), 470, 300,
                                   kopya_resim=lambda: self.g_zaman.resim(2.0))
        kc.layout().addWidget(self.g_oee)
        kc.layout().addWidget(self.g_zaman)
        kc.hide()
        self.k_cormind = kc
        kok.addWidget(kc)
        kok.addStretch(1)
        self._sc = sc

    # ------------------------------------------------------------------ çizim
    def _makineler(self) -> List[str]:
        s = self.ana.sonuc
        temel = list(self.ana.ayar.get("makineler", []))
        return temel + (sorted(m for m in s.hucreler if m not in temel) if s else [])

    def _tablo_ciz(self, p, rect, bolgeler):
        s = self.ana.sonuc
        if not s:
            return
        tum = self._makineler()
        cizim.tablo_ciz(p, rect, s, tum, 0, 1.22)
        if bolgeler is not None:
            sh = rect.height() / (len(tum) + 4)
            for i, m in enumerate(tum):
                if s.makine_ort.get(m, (None,))[0] is not None or m in s.esik_alti:
                    bolgeler.append((QRectF(rect.left(), rect.top() + sh * (i + 4), rect.width(), sh), m, "durus"))

    def _vardiya_ciz(self, p, rect):
        if self.ana.sonuc:
            cizim.vardiya_grafigi(p, rect, self.ana.sonuc, self.ana.seflar or {}, 0, "", arka=False)

    def _makine_ciz(self, p, rect, bolgeler):
        if self.ana.sonuc:
            cizim.genel_performans_grafigi(p, rect, self.ana.sonuc, self.ana.ayar.get("makineler", []), self._mola_pay, None,
                                           bolgeler=bolgeler, secili=self._secili)

    def _degerler(self, m: str):
        """(çalışma, mola, eşik altı mı) ya da None."""
        s = self.ana.sonuc
        ort = s.makine_ort.get(m) if s else None
        if ort and ort[0] is not None:
            return max(0.0, min(1.0, ort[0])), max(0.0, min(1.0, ort[2] or 0.0)), False
        if s and m in s.esik_alti:
            e = s.esik_alti[m]
            return max(0.0, min(1.0, e[0])), max(0.0, min(1.0, e[2])), True
        return None

    def _makine_ipucu(self, m, _kisim) -> str:
        d = self._degerler(m)
        if not d:
            return m
        c, mo, alti = d
        dk = self._mola_dk
        return (f"<b>{m}</b>" + (f" · <span style='color:#ffb3ad'>eşik altı: hesaba girmez</span>" if alti else "")
                + f"<br>Çalışma: <b>{tema.yuzde(c, 1)}</b><br>Duruş: <b>{tema.yuzde(1 - c, 1)}</b>"
                + f"<br>Mola yapılan: <b>{tema.yuzde(mo, 0)}</b> · günde ort. {mo * dk:.0f} dk"
                + f"<br>Molada çalışılan: <b>{tema.yuzde(1 - mo, 0)}</b> · günde ort. {(1 - mo) * dk:.0f} dk")

    def _detay_ciz(self, p, rect):
        m = self._secili
        s = self.ana.sonuc
        if not m or not s:
            return
        if self._mod == "mola":
            hucre = s.hucreler.get(m, {})
            veri = [(f"{v}. VARDİYA", (self.ana.seflar or {}).get(v, ""), hucre[v][2]) for v in VARDIYALAR if v in hucre]
            cizim.mola_pasta_grafigi(p, rect, veri, self._mola_dk)
        else:
            liste = sorted(((t, x) for t, x in self._dokum.get(m, {}).items() if x > 0.004), key=lambda x: -x[1])
            cizim.durus_dokum_grafigi(p, rect, liste)

    # ------------------------------------------------------------------ davranış
    def _sec(self, makine, kisim):
        self._secili, self._mod = makine, kisim
        self._detay_yaz()
        for w in (self.g_makine, self.g_detay):
            w.update()
        self._sc.ensureWidgetVisible(self.k_detay, 0, 30)

    def _detay_yaz(self):
        m = self._secili
        if not m:
            self.d_baslik.setText("Ayrıntı")
            self.d_alt.setText("yukarıdaki grafikte bir makineye tıklayın")
            return
        d = self._degerler(m)
        if self._mod == "mola":
            self.d_baslik.setText(f"{m} – vardiya bazlı mola dağılımı")
            self.d_alt.setText(f"pastanın tamamı mola hakkı (günde {self._mola_dk:.0f} dk) · turuncu: mola yapılan · mor: molada çalışılan")
        else:
            top = sum(self._dokum.get(m, {}).values())
            self.d_baslik.setText(f"{m} – duruşlar (büyükten küçüğe)")
            self.d_alt.setText((f"toplam duruş {cizim._saat_dk(top)} saat" + (f" · çalışma {tema.yuzde(d[0], 1)}" if d else "")
                                + " · mola kısmına tıklarsanız vardiya bazlı mola açılır") if top else "bu dönemde duruş kaydı yok")

    def _cormind_goster(self, acik: bool):
        self.k_cormind.setVisible(acik)
        self.b_cormind.setText("Cormind rapor sistemini gizle" if acik else "Cormind rapor sistemi")
        if acik:
            self.g_oee.update()
            self.g_zaman.update()
            self._sc.ensureWidgetVisible(self.k_cormind, 0, 60)

    def yenile(self):
        s, ayar = self.ana.sonuc, self.ana.hesap_ayar()
        self._mola_pay = 100.0 * ayar.mola_saat / ayar.net_saat
        self._mola_dk = ayar.mola_saat * 60.0
        gunler = self.ana.donem_gunleri()
        kayit = getattr(self.ana, "kayit", []) or []
        self._dokum = durus_dokumu(kayit, gunler) if s else {}
        self._cormind = cormind_hesabi(kayit, gunler, self.ana.ayar.get("makineler", []), ayar) if s else {}
        if self._secili and (not s or self._degerler(self._secili) is None):
            self._secili = None
        if not s:
            self.k_genel.d.setText("-")
            self.k_genel.a.setText("Önce Veri Aktar sayfasından veri yükleyin" if not self.ana.kapsam() else "Gün seçilmedi")
            for v in VARDIYALAR:
                for w, t in ((self.k_v[v].d, "-"), (self.k_v[v].a, ""), (self.k_v[v].s, "")):
                    w.setText(t)
            self.donem_etiketi.setText("")
            self.c_alt.setText("")
        else:
            yontem = dict(tema.YONTEMLER).get(ayar.yontem, "").lower()
            self.k_genel.d.setText(tema.yuzde(s.genel[0]) if s.genel[0] is not None else "-")
            self.k_genel.a.setText(f"{s.hesap_gunu()} gün · eşik %{ayar.esik * 100:.0f} · {yontem}")
            for v in VARDIYALAR:
                o = s.vardiyalar[v]
                self.k_v[v].d.setText(tema.yuzde(o.calisma) if o.calisma is not None else "-")
                self.k_v[v].a.setText((f"{tema.sayi(o.makine_sayisi, 1)} makine · " if o.makine_sayisi is not None else "") + f"{o.gun_sayisi} gün")
                self.k_v[v].s.setText((self.ana.seflar or {}).get(v, ""))
            donem = f"{min(gunler):%d.%m.%Y} – {max(gunler):%d.%m.%Y}" if gunler else ""
            self.donem_etiketi.setText(donem)
            self.c_alt.setText(f"{donem} · {len(self._cormind)} makine")
        self.tablo.setFixedHeight(max(300, (len(self._makineler()) + 4) * 20) if s else 300)
        self._detay_yaz()
        for w in (self.tablo, self.g_vardiya, self.g_makine, self.g_detay, self.g_oee, self.g_zaman):
            w.update()
