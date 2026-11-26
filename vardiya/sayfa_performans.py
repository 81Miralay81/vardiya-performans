"""Performans sayfası (programın kendi çizimi; tarayıcı motoru kullanılmaz, açılışı yavaşlatmaz).

Makine sütunları hep %100'dür (çalışma + duruş); sıfırın altında mola hakkı gösterilir (mola yapılan / molada çalışılan).
Sütunun çalışma ya da duruş kısmına tıklayınca altta o makinenin duruşları büyükten küçüğe, mola kısmına tıklayınca
vardiya bazlı mola pastaları açılır. Bir duruşa tıklayınca o duruşun vardiya ve operatör kırılımı (3. kırılım), şüpheli
molası olan makinenin altındaki ⚠ işaretine ya da pastaya tıklayınca şüpheli molaların zaman çizelgesi açılır. 'Cormind rapor sistemi' düğmesi Cormind'in kendi hesabını ayrı bir bölümde gösterir."""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

from PySide6.QtCore import QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QToolTip, QVBoxLayout, QWidget

from . import cizim, cizim_ek, tema
from .hesap import VARDIYALAR, calismayan_makineler, cormind_hesabi, durus_dokumu
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


class _KirilimIs(QThread):
    """3. kırılım hesabı arka planda (kendi veri tabanı bağlantısıyla): ağ diskinde pencere donmasın."""
    bitti = Signal(object, object, object)       # (makine, duruş, sonuç)

    def __init__(self, db_yolu, ilk, son, makine, tip, parent=None):
        super().__init__(parent)
        self.a = (db_yolu, ilk, son, makine, tip)

    def run(self):
        from . import veritabani as vt
        from .kirilim import durus_kirilimi
        db_yolu, ilk, son, makine, tip = self.a
        try:
            con, kilit = vt.okuma_baglantisi(db_yolu)       # sürekli açık okuma bağlantısı (önbellek sıcak kalır)
            with kilit:
                k = durus_kirilimi(con, ilk, son, makine, tip)
        except Exception as e:  # noqa: BLE001
            k = {"hata": str(e)}
        self.bitti.emit(makine, tip, k)


class _DonemKayitIs(QThread):
    """Dönemin tüm makinelerdeki kayıtları (operatör doğrulanmış) arka planda, sürekli açık okuma bağlantısıyla."""
    bitti = Signal(object, object)               # ((ilk, son), kayıtlar | hata metni)

    def __init__(self, db_yolu, ilk, son, parent=None):
        super().__init__(parent)
        self.a = (db_yolu, ilk, son)

    def run(self):
        from . import veritabani as vt
        from .kirilim import donem_kayitlari
        db_yolu, ilk, son = self.a
        try:
            con, kilit = vt.okuma_baglantisi(db_yolu)
            with kilit:
                k = donem_kayitlari(con, ilk, son)
        except Exception as e:  # noqa: BLE001
            k = str(e)
        self.bitti.emit((ilk, son), k)


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
        self._tip: Optional[str] = None          # 3. kırılımda seçili duruş
        self._kirilim: Dict[str, list] = {}
        self._supheli: Dict[str, dict] = {}       # makine -> vardiya -> {dk_gun, adet, olaylar}
        self._sup_v: Optional[int] = None
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
        self.g_detay = TikliCizim(self._detay_ciz, 360, 300)
        self.g_detay.tiklandi.connect(self._detay_tik)
        kd.layout().addWidget(self.g_detay)
        self.k_detay = kd
        b_kapat = QPushButton("✕")
        b_kapat.setToolTip("Ayrıntıyı kapat")
        b_kapat.setFixedSize(28, 26)
        b_kapat.setCursor(Qt.PointingHandCursor)
        b_kapat.clicked.connect(self._detay_kapat)
        _s.addWidget(b_kapat)
        kd.hide()                               # bir makineye tıklanana kadar gizli
        kok.addWidget(kd)

        # ---------------------------------------------------------------- 3. kırılım: duruşun vardiya / operatör dağılımı
        kk, self.k_baslik, self.k_alt, _s = _kart_baslikli("Kırılım", "")
        ikili = QHBoxLayout()
        ikili.setSpacing(12)
        self.g_kv = CizimWidget(lambda p, r: cizim_ek.kirilim_grafigi(p, r, self._kirilim.get("vardiya", []), "Vardiyaya göre"), 320, 260,
                                kopya_resim=lambda: self.g_kv.resim(2.0))
        self.g_ko = TikliCizim(lambda p, r, b: cizim_ek.kirilim_grafigi(p, r, self._kirilim.get("operator", []), "Operatöre göre (tıklayın)",
                                                                        b, "operator", self._op), 260, 320)
        self.g_ko.tiklandi.connect(lambda a, k: self._op_tik(a))
        ikili.addWidget(self.g_kv, 1)
        ikili.addWidget(self.g_ko, 1)
        kk.layout().addLayout(ikili)
        b_k = QPushButton("✕")
        b_k.setToolTip("Kırılımı kapat")
        b_k.setFixedSize(28, 26)
        b_k.clicked.connect(self._kirilim_kapat)
        _s.addWidget(b_k)
        kk.hide()
        self.k_kirilim = kk
        kok.addWidget(kk)

        # ---------------------------------------------------------------- 4. seviye: seçili operatörün bu duruşu (makine / zaman)
        self._op = None
        self._op_veri: dict = {}
        self._oz_mod = "gun"
        self._om_secili = None
        self._oz_secili = None
        ko, self.o_baslik, self.o_alt, _s = _kart_baslikli("Operatör", "")
        ikili = QHBoxLayout()
        ikili.setSpacing(12)
        self.g_om = TikliCizim(lambda p, r, b: cizim_ek.kirilim_grafigi(p, r, [(m, x, tema.durus_rengi(self._tip or ""))
                                                                              for m, x in self._op_veri.get("makine", [])],
                                                                         "Makineye göre (tıklayın)", b, "om_makine", self._om_secili), 260, 320)
        self.g_om.tiklandi.connect(lambda a, k: self._cizelge_ac("makine", a))
        sag = QVBoxLayout()
        from PySide6.QtWidgets import QButtonGroup
        mod_s = QHBoxLayout()
        mod_s.addWidget(etiket("Zamana göre:", "AltBaslik"))
        self._oz_grup = QButtonGroup(self)
        for kod, ad in (("gun", "Gün"), ("vardiya", "Vardiya"), ("gunv", "Gün × vardiya")):
            b = QPushButton(ad)
            b.setObjectName("Hizli")
            b.setCheckable(True)
            b.setChecked(kod == "gun")
            b.clicked.connect(lambda _=False, k=kod: self._oz_mod_sec(k))
            self._oz_grup.addButton(b)
            mod_s.addWidget(b)
        mod_s.addStretch(1)
        sag.addLayout(mod_s)
        self.g_oz = TikliCizim(lambda p, r, b: cizim_ek.zaman_grafigi(p, r, self._op_veri.get("gun", []), self._oz_mod, "Zamana göre (tıklayın)",
                                                                      b, self._oz_secili, tema.durus_rengi(self._tip or "")), 260, 320)
        self.g_oz.tiklandi.connect(lambda a, k: self._cizelge_ac(k, a))
        sag.addWidget(self.g_oz, 1)
        ikili.addWidget(self.g_om, 1)
        ikili.addLayout(sag, 1)
        ko.layout().addLayout(ikili)
        b_o = QPushButton("✕")
        b_o.setToolTip("Kapat")
        b_o.setFixedSize(28, 26)
        b_o.clicked.connect(self._op_kapat)
        _s.addWidget(b_o)
        ko.hide()
        self.k_op = ko
        kok.addWidget(ko)

        # ---------------------------------------------------------------- 5. seviye: zaman çizelgesi (gank)
        from .zaman_cizelgesi import ZamanCizelgesi
        kg, self.z_baslik, self.z_alt, _s = _kart_baslikli("Zaman çizelgesi", "")
        self.zc = ZamanCizelgesi()
        kg.layout().addWidget(self.zc)
        b_z = QPushButton("✕")
        b_z.setToolTip("Kapat")
        b_z.setFixedSize(28, 26)
        b_z.clicked.connect(lambda: self.k_gantt.hide())
        _s.addWidget(b_z)
        kg.hide()
        self.k_gantt = kg
        kok.addWidget(kg)

        # ---------------------------------------------------------------- şüpheli mola zaman çizelgesi
        ks, self.s_baslik, self.s_alt, _s = _kart_baslikli("Şüpheli molalar", "")
        self.g_sup = CizimWidget(lambda p, r: cizim_ek.supheli_cizelgesi(p, r, self._sup_olaylar()), 220, 300,
                                 kopya_resim=lambda: self.g_sup.resim(2.0))
        ks.layout().addWidget(self.g_sup)
        b_s = QPushButton("✕")
        b_s.setToolTip("Kapat")
        b_s.setFixedSize(28, 26)
        b_s.clicked.connect(self._supheli_kapat)
        _s.addWidget(b_s)
        ks.hide()
        self.k_supheli = ks
        kok.addWidget(ks)


        # ---------------------------------------------------------------- Cormind rapor sistemi
        kc, _b, self.c_alt, _s = _kart_baslikli("Cormind rapor sistemi")
        kc.layout().addWidget(etiket(
            "Bu bölüm Cormind'in kendi hesabıdır ve yukarıdaki hesaptan bağımsızdır: eşik ve hesap yöntemi uygulanmaz. Cormind çalışma süresini "
            "toplamaz; duruşları net süreye (her 480 dakikanın 440'ı) böler, mola hakkını düşer ve OEE = 100 − toplam der. Kaydı olmayan süre "
            "çalışılmış sayılır. Dönemde hiç kaydı olmayan makine çalışmamış sayılır: OEE %0, duruş %100 ('Çalışmıyor'). Uzun bir kayıt 'Kısa Duruş' adıyla gösterilmez.", "AltBaslik"))
        self.kilavuz = False                    # makineleri ayıran ince dikey çizgiler (onaylanınca açılacak)

        def _s(r):                              # iki grafik aynı ölçekte çizilir: makineler alt alta aynı hizada
            return cizim.olcek(QRectF(0, 0, r.width(), 300))

        self.g_oee = CizimWidget(lambda p, r: cizim.cormind_oee_grafigi(p, r, self._cormind, "OEE Grafiği (Cormind)", s=_s(r), kilavuz=self.kilavuz), 300, 300,
                                 kopya_resim=lambda: self.g_oee.resim(2.0))
        self.g_zaman = CizimWidget(lambda p, r: cizim.cormind_durus_grafigi(p, r, self._cormind, "Zaman Dağılım Grafiği (Cormind)", s=_s(r), kilavuz=self.kilavuz), 470, 300,
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
                                           bolgeler=bolgeler, secili=self._secili, supheli=set(self._supheli) or None,
                                           gizli=calismayan_makineler(self.ana.sonuc) if self.ana.ayar.get("calismayanlari_gizle", True) else None,
                                           bos_goster=not self.ana.ayar.get("calismayanlari_gizle", True))

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
        if _kisim == "supheli":
            vs = self._supheli.get(m, {})
            return (f"<b>{m}</b> · <span style='color:#ffb3ad'>⚠ şüpheli mola</span><br>"
                    + "<br>".join(f"{v}. vardiya: {x['adet']} olay" for v, x in sorted(vs.items()))
                    + "<br>tıklayın: mola pastası ve zaman çizelgesi")
        d = self._degerler(m)
        if not d:
            return m
        c, mo, alti = d
        dk = self._mola_dk
        return (f"<b>{m}</b>" + (f" · <span style='color:#ffb3ad'>eşik altı: hesaba girmez</span>" if alti else "")
                + f"<br>Çalışma: <b>{tema.yuzde(c, 1)}</b><br>Duruş: <b>{tema.yuzde(1 - c, 1)}</b>"
                + f"<br>Mola yapılan: günde ort. <b>{mo * dk:.0f} dk</b> ({dk:.0f} dk içinden)"
                + f"<br>Molada çalışılan: günde ort. <b>{(1 - mo) * dk:.0f} dk</b>")

    def _detay_ciz(self, p, rect, bolgeler=None):
        m = self._secili
        s = self.ana.sonuc
        if not m or not s:
            return
        if self._mod == "mola":
            from .servis import mola_pastasi
            cizim.mola_pasta_grafigi(p, rect, mola_pastasi(s, self.ana.seflar or {}, self._supheli, m), self._mola_dk, bolgeler=bolgeler)
        else:
            liste = sorted(((t, x) for t, x in self._dokum.get(m, {}).items() if x > 0.004), key=lambda x: -x[1])
            cizim.durus_dokum_grafigi(p, rect, liste, bolgeler=bolgeler, secili=self._tip)

    # ------------------------------------------------------------------ 3. kırılım ve şüpheli mola
    def _detay_tik(self, anahtar, kisim):
        if kisim == "tip" and self._mod != "mola":
            self._kirilim_ac(anahtar)
        elif kisim == "pasta" and self._mod == "mola":
            try:
                v = int(str(anahtar).split(".")[0])
            except ValueError:
                return
            self._supheli_ac(v)

    def _kirilim_ac(self, tip: str):
        m = self._secili
        if not m or not tip:
            return
        if self._tip == tip and self.k_kirilim.isVisible():      # aynı duruşa ikinci tıklama kapatır
            self._kirilim_kapat()
            return
        gunler = self.ana.donem_gunleri()
        if not gunler:
            return
        self._op_kapat()                            # yeni duruş: 4.-5. seviye kapanır
        self._tip = tip
        self._kirilim = {}
        anahtar = (min(gunler), max(gunler), m, tip)
        onbellek = getattr(self, "_kirilim_bellek", None)
        if onbellek is None or onbellek.get("_donem") != (min(gunler), max(gunler)):
            onbellek = self._kirilim_bellek = {"_donem": (min(gunler), max(gunler))}
        self.k_baslik.setText(f"{m} · {tip} – vardiya ve operatör kırılımı")
        self.k_alt.setText("hesaplanıyor…")
        self.k_kirilim.show()
        for w in (self.g_detay, self.g_kv, self.g_ko):
            w.update()
        self._sc.ensureWidgetVisible(self.k_kirilim, 0, 30)
        if anahtar in onbellek:                         # aynı dönemde daha önce hesaplandı: anında
            self._kirilim_geldi(m, tip, onbellek[anahtar])
            return
        is_ = _KirilimIs(self.ana.db_yolu, min(gunler), max(gunler), m, tip, self)
        is_.bitti.connect(self._kirilim_geldi)
        is_.finished.connect(is_.deleteLater)
        self._kirilim_is = is_
        is_.start()

    def _kirilim_geldi(self, m, tip, k):
        if m != self._secili or tip != self._tip or not self.k_kirilim.isVisible():
            return                                  # bu arada başka makine / duruş seçildi
        if "hata" in k:
            self.k_alt.setText(f"Hesaplanamadı: {k['hata']}")
            return
        gunler = self.ana.donem_gunleri()
        if gunler and getattr(self, "_kirilim_bellek", None) is not None:
            self._kirilim_bellek[(min(gunler), max(gunler), m, tip)] = k
        from .kirilim import OPERATOR_YOK
        renk = tema.durus_rengi(tip)
        self._kirilim = {"vardiya": [(a, x, tema.LACIVERT) for a, x in k["vardiya"]],
                         "operator": [(a, x, "#B0B4C0" if a == OPERATOR_YOK else renk) for a, x in k["operator"]]}
        top = sum(x for _a, x in k["vardiya"])
        self.k_alt.setText(f"toplam {cizim._saat_dk(top)} saat · gri: duruş sürerken makinede operatör kayıtlı değil · "
                           "aynı duruşa yeniden tıklarsanız kapanır")
        for w in (self.g_kv, self.g_ko):
            w.update()

    def _kirilim_kapat(self):
        self._tip = None
        if hasattr(self, "k_kirilim"):
            self.k_kirilim.hide()
            self.g_detay.update()
        self._op_kapat()

    # ---------------------------------------------------------------- 4. seviye: operatör ayrıntısı
    def _op_kapat(self):
        self._op = None
        self._om_secili = self._oz_secili = None
        if hasattr(self, "k_op"):
            self.k_op.hide()
            self.k_gantt.hide()
            self.g_ko.update()

    def _op_tik(self, ad):
        if not ad or not self._tip:
            return
        if ad == self._op and self.k_op.isVisible():               # aynı operatöre ikinci tıklama kapatır
            self._op_kapat()
            return
        gunler = self.ana.donem_gunleri()
        if not gunler:
            return
        from .kirilim import OPERATOR_YOK
        self._tek_makine = None
        if ad == OPERATOR_YOK and self._secili:              # operatörsüz: bu makinede mi, tüm makinelerde mi?
            from PySide6.QtWidgets import QMessageBox
            k = QMessageBox(self)
            k.setWindowTitle("Operatör yok")
            k.setText(f"'{self._tip}' duruşunun operatörsüz kısmı nasıl gösterilsin?")
            b_bu = k.addButton(f"Bu makinede ({self._secili}) · zaman çizelgesi", QMessageBox.AcceptRole)
            b_tum = k.addButton("Tüm makinelerde · kırılım", QMessageBox.ActionRole)
            k.addButton("Vazgeç", QMessageBox.RejectRole)
            k.exec()
            if k.clickedButton() is b_bu:
                self._tek_makine = self._secili
            elif k.clickedButton() is not b_tum:
                return
        self._op = ad
        self._om_secili = self._oz_secili = None
        self._op_veri = {}
        self.k_gantt.hide()
        self.o_baslik.setText(f"{ad} · {self._tip}")
        self.o_alt.setText("hesaplanıyor…")
        self.k_op.setVisible(not self._tek_makine)
        for w in (self.g_ko, self.g_om, self.g_oz):
            w.update()
        self._sc.ensureWidgetVisible(self.k_op, 0, 30)
        anahtar = (min(gunler), max(gunler))
        bellek = getattr(self, "_donem_kayit", None)
        if bellek and bellek[0] == anahtar:
            self._op_hesapla(bellek[1])
            return
        is_ = _DonemKayitIs(self.ana.db_yolu, anahtar[0], anahtar[1], self)
        is_.bitti.connect(self._donem_kayit_geldi)
        is_.finished.connect(is_.deleteLater)
        self._donem_is = is_
        is_.start()

    def _donem_kayit_geldi(self, anahtar, kayit):
        if isinstance(kayit, str):
            self.o_alt.setText(f"Hesaplanamadı: {kayit}")
            return
        self._donem_kayit = (anahtar, kayit)
        gunler = self.ana.donem_gunleri()
        if gunler and (min(gunler), max(gunler)) == anahtar and self._op:
            self._op_hesapla(kayit)

    def _op_hesapla(self, kayit):
        from .kirilim import operator_ayrinti
        gunler = self.ana.donem_gunleri()
        self._op_veri = operator_ayrinti(kayit, min(gunler), max(gunler), self._tip, self._op)
        tek = getattr(self, "_tek_makine", None)
        if tek:                                                  # yalnızca bu makine: doğrudan zaman çizelgesi
            self._op_veri["makine"] = [(m, x) for m, x in self._op_veri["makine"] if m == tek]
            self._op_veri["bloklar"] = {m: v for m, v in self._op_veri["bloklar"].items() if m == tek}
            if self._op_veri["makine"]:
                self._cizelge_ac("om_makine", tek)
                self.z_alt.setText(f"{tek} · operatörsüz '{self._tip}' kırmızı taralı çerçeveli · tüm dönem · tekerlekle yakınlaştırın")
            return
        top = sum(x for _m, x in self._op_veri["makine"])
        self.o_alt.setText(f"toplam {cizim._saat_dk(top)} saat · {len(self._op_veri['makine'])} makine · makine ya da zaman çubuğuna tıklayın: "
                           "zaman çizelgesi · aynı operatöre yeniden tıklarsanız kapanır")
        for w in (self.g_om, self.g_oz):
            w.update()

    def _oz_mod_sec(self, kod: str):
        self._oz_mod = kod
        self._oz_secili = None
        self.g_oz.update()

    # ---------------------------------------------------------------- 5. seviye: zaman çizelgesi
    def _cizelge_ac(self, kisim, anahtar):
        from datetime import datetime as _dt, timedelta as _td
        from .kirilim import VARDIYA_SAAT
        v = self._op_veri
        if not v or not v.get("makine"):
            return
        gunler = self.ana.donem_gunleri()
        t0 = _dt(min(gunler).year, min(gunler).month, min(gunler).day)
        t1 = _dt(max(gunler).year, max(gunler).month, max(gunler).day) + _td(days=1)
        satirlar = [m for m, _x in v["makine"]]
        bloklar = v["bloklar"]
        gorunum, baslik = None, ""
        if kisim == "om_makine":
            self._om_secili, self._oz_secili = anahtar, None
            satirlar = [anahtar] + [m for m in satirlar if m != anahtar]
            baslik = f"{anahtar} seçili · tüm dönem"
        elif kisim == "oz_gun":
            self._oz_secili, self._om_secili = anahtar, None
            g = _dt.fromisoformat(anahtar)
            gorunum, baslik = (g, g + _td(days=1)), f"{g:%d.%m.%Y}"
        elif kisim == "oz_gunv":
            self._oz_secili, self._om_secili = anahtar, None
            gi, vv = anahtar.split("|")
            g = _dt.fromisoformat(gi)
            h0, h1 = VARDIYA_SAAT[int(vv)]
            gorunum, baslik = (g + _td(hours=h0), g + _td(hours=h1)), f"{g:%d.%m.%Y} · {vv}. vardiya"
        elif kisim == "oz_vardiya":
            self._oz_secili, self._om_secili = anahtar, None
            h0, h1 = VARDIYA_SAAT[int(anahtar)]
            bloklar = {m: [(a, b, t, st, op, vu and h0 <= a.hour < h1) for a, b, t, st, op, vu in lst] for m, lst in bloklar.items()}
            baslik = f"yalnızca {anahtar}. vardiya vurgulu · tüm dönem"
        else:
            return
        for w in (self.g_om, self.g_oz):
            w.update()
        self.z_baslik.setText(f"{self._op} · {self._tip} · zaman çizelgesi")
        self.z_alt.setText(baslik + " · satırlar: bu duruşun görüldüğü makineler")
        self.zc.ayarla(satirlar, bloklar, t0, t1, tema.durus_rengi(self._tip or ""), self._tip or "", gorunum)
        self.k_gantt.show()
        self._sc.ensureWidgetVisible(self.k_gantt, 0, 30)

    def _sup_olaylar(self) -> list:
        if not self._secili or self._sup_v is None:
            return []
        return self._supheli.get(self._secili, {}).get(self._sup_v, {}).get("olaylar", [])

    def _supheli_ac(self, v: Optional[int] = None):
        m = self._secili
        vs = self._supheli.get(m or "", {})
        if v is None:
            v = min(vs) if vs else None
        if v is None or v not in vs:
            self._supheli_kapat()
            return
        self._sup_v = v
        n = len(vs[v]["olaylar"])
        self.s_baslik.setText(f"{m} · {v}. vardiya – şüpheli molalar ({n})")
        self.s_alt.setText("mola saatinin 30 dk öncesi ve sonrası · kesik çerçeve: Ayarlar'daki mola saati · turuncu: mola · "
                           "yeşil: çalışma · kırmızı: duruş · kırmızı tarama: mola saatinde başlayan çalışma")
        self.g_sup.setFixedHeight(max(220, 112 * n))
        self.k_supheli.show()
        self.g_sup.update()
        self._sc.ensureWidgetVisible(self.k_supheli, 0, 30)

    def _supheli_kapat(self):
        self._sup_v = None
        if hasattr(self, "k_supheli"):
            self.k_supheli.hide()

    # ------------------------------------------------------------------ davranış
    def _detay_kapat(self):
        self._secili = None
        self.k_detay.hide()
        self._kirilim_kapat()
        self._supheli_kapat()
        self.g_makine.update()

    def _sec(self, makine, kisim):
        supheli = kisim == "supheli"
        if supheli:
            kisim = "mola"                      # ⚠: mola pastası + şüpheli zaman çizelgesi
        if not supheli and self._secili == makine and getattr(self, "_mod", None) == kisim and self.k_detay.isVisible():
            self._detay_kapat()                 # aynı yere ikinci tıklama kapatır
            return
        if self._secili != makine or self._mod != kisim:
            self._kirilim_kapat()               # başka makine / bölüm: 3. kırılım duruşa tıklanana kadar açılmaz
            self._supheli_kapat()
        self._secili, self._mod = makine, kisim
        self.k_detay.show()
        if supheli:
            self._supheli_ac()
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
            self.d_alt.setText(f"pastanın tamamı mola hakkı (günde {self._mola_dk:.0f} dk) · turuncu: mola yapılan · mor: molada çalışılan"
                               + (" · kırmızı: şüpheli çalışma (pastaya tıklayın: zaman çizelgesi)" if self._supheli.get(m) else ""))
        else:
            top = sum(self._dokum.get(m, {}).values())
            self.d_baslik.setText(f"{m} – duruşlar (büyükten küçüğe)")
            self.d_alt.setText((f"toplam duruş {cizim._saat_dk(top)} saat" + (f" · çalışma {tema.yuzde(d[0], 1)}" if d else "")
                                + " · bir duruşa tıklayın: vardiya ve operatör kırılımı") if top else "bu dönemde duruş kaydı yok")

    def _cormind_goster(self, acik: bool):
        self.k_cormind.setVisible(acik)
        self.b_cormind.setText("Cormind rapor sistemini gizle" if acik else "Cormind rapor sistemi")
        if acik:
            self.g_oee.update()
            self.g_zaman.update()
            self._sc.ensureWidgetVisible(self.k_cormind, 0, 60)

    def showEvent(self, e):
        super().showEvent(e)
        if not getattr(self, "_isitildi", False):     # ayrıntı grafiklerinin tarayıcı motorunu önceden kur (ilk tıklama donmasın)
            self._isitildi = True
            QTimer.singleShot(1500, lambda: [w.web_hazirla() for w in (self.g_detay, self.g_kv, self.g_ko)])

    def yenile(self):
        self._kirilim_bellek = None                 # yeni veri / dönem: kırılım önbelleği sıfırlanır
        self._donem_kayit = None
        s, ayar = self.ana.sonuc, self.ana.hesap_ayar()
        self._mola_pay = 100.0 * ayar.mola_saat / ayar.net_saat
        self._mola_dk = ayar.mola_saat * 60.0
        gunler = self.ana.donem_gunleri()
        kayit = getattr(self.ana, "kayit", []) or []
        self._dokum = durus_dokumu(kayit, gunler, ayar.haric) if s else {}
        self._cormind = cormind_hesabi(kayit, gunler, self.ana.ayar.get("makineler", []), ayar) if s else {}
        try:
            from .servis import supheli_hesabi
            self._supheli = supheli_hesabi(self.ana.con, self.ana.ayar, sorted(gunler)) if s else {}
        except Exception as e:  # noqa: BLE001  (şüpheli mola hesabı ana sayfayı hiçbir zaman bozmasın; hata teşhis kaydına)
            self._supheli = {}
            try:
                from . import teshis
                import traceback
                teshis.adim(f"HATA: şüpheli mola hesabı: {type(e).__name__}: {e} | {traceback.format_exc(limit=3)}")
            except Exception:  # noqa: BLE001
                pass
        self._kirilim_kapat()
        self._supheli_kapat()
        if self._secili and (not s or self._degerler(self._secili) is None):
            self._secili = None
        if not self._secili:
            self.k_detay.hide()
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
