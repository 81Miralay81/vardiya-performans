"""Personel Durum sayfası (yalnızca exe): personel verisinden devam özeti, haftalık vardiya listesi, sıralamalar ve
personel kartı. Fotoğraf (varsa) yalnızca 'Personel kimlik bilgileri' yetkisi olan kullanıcıya gösterilir."""
from __future__ import annotations

import base64
from datetime import date, timedelta
from typing import Dict, List, Optional

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
                               QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from . import personel_veri as pv, tema, veritabani as vt
from .sayfa_ortak import etiket, kart, tablo_menusu
from .takvim import AralikSecici

GUNLER = ("Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz")
AYLAR = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")
RENK = pv.RENK


def _sayi(v, metin: Optional[str] = None) -> QTableWidgetItem:
    """Sayıya göre sıralanan tablo hücresi."""
    it = QTableWidgetItem()
    it.setData(Qt.EditRole, v if v is not None else -1)
    it.setData(Qt.DisplayRole, metin if metin is not None else ("" if v is None else v))
    it.setTextAlignment(Qt.AlignCenter)
    return it



def _bos_profil(g: int, y: int) -> QPixmap:
    """Fotoğrafı olmayan personel için gri, boş profil resmi (baş ve omuz silueti)."""
    from PySide6.QtGui import QPainter, QColor, QPainterPath
    pm = QPixmap(g, y)
    pm.fill(QColor("#e4e8f0"))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#b8c0d0"))
    r = g * 0.22
    p.drawEllipse(int(g / 2 - r), int(y * 0.40 - r * 1.1), int(r * 2), int(r * 2))
    yol = QPainterPath()
    yol.addRoundedRect(g * 0.16, y * 0.62, g * 0.68, y * 0.45, g * 0.3, g * 0.3)
    p.drawPath(yol)
    p.end()
    return pm

class _SiraliHucre(QTableWidgetItem):
    def __init__(self, metin: str, anahtar):
        super().__init__(metin)
        self._k = anahtar
        self.setTextAlignment(Qt.AlignCenter)

    def __lt__(self, o):  # noqa: D105
        return self._k < getattr(o, "_k", 0)


def _hucre(metin: str, anahtar) -> QTableWidgetItem:
    return _SiraliHucre(metin, anahtar)


def _hucre_kisi(ad: str, sid: int) -> QTableWidgetItem:
    it = QTableWidgetItem(ad)
    it.setData(Qt.UserRole, sid)
    f = it.font()
    f.setBold(True)
    it.setFont(f)
    return it


class CubukListesi(QWidget):
    """Yatay çubuklarla en çoklar listesi; çubuğa tıklayınca personel kartı açılır."""
    tiklandi = Signal(int)

    def __init__(self, baslik: str, renk: str):
        super().__init__()
        self.baslik, self.renk = baslik, renk
        self.veri: List[tuple] = []            # (sicilid, ad, değer, yazı, [(pay, renk)] | None)
        self.setMinimumHeight(250)
        self.setMouseTracking(True)
        self._bolge: List[tuple] = []

    def ayarla(self, veri: List[tuple]):
        self.veri = veri[:10]
        self.setMinimumHeight(60 + 24 * max(3, len(self.veri)))
        self.update()

    def paintEvent(self, _):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect()
        p.setPen(QColor(tema.LACIVERT))
        f = QFont(tema.FONT_AILESI, 10)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(8, 4, r.width() - 16, 22), Qt.AlignLeft | Qt.AlignVCenter, self.baslik)
        p.setFont(QFont(tema.FONT_AILESI, 9))
        self._bolge = []
        if not self.veri:
            p.setPen(QColor(tema.YAZI_SOLUK))
            p.drawText(QRectF(8, 34, r.width() - 16, 22), Qt.AlignLeft, "Seçilen dönemde yok")
            return
        enb = max(v[2] for v in self.veri) or 1
        ad_w = 150
        yazi_w = min(250, int(r.width() * 0.3))
        cubuk_w = max(40, r.width() - ad_w - yazi_w - 24)
        for i, (sid, ad, deger, yazi, parcalar) in enumerate(self.veri):
            y = 34 + i * 24
            p.setPen(QColor(tema.YAZI))
            p.drawText(QRectF(8, y, ad_w - 6, 20), Qt.AlignLeft | Qt.AlignVCenter, pv.tr_baslik(ad))
            w = cubuk_w * deger / enb
            x = 8 + ad_w
            if parcalar:
                top = sum(a for a, _ in parcalar) or 1
                for pay, rk in parcalar:
                    pw = w * pay / top
                    p.fillRect(QRectF(x, y + 3, pw, 14), QColor(rk))
                    x += pw
            else:
                p.fillRect(QRectF(x, y + 3, w, 14), QColor(self.renk))
                x += w
            p.setPen(QColor(tema.YAZI_SOLUK))
            p.drawText(QRectF(x + 6, y, r.width() - x - 10, 20), Qt.AlignLeft | Qt.AlignVCenter, yazi)
            self._bolge.append((QRectF(0, y, r.width(), 22), sid))
        p.end()

    def mousePressEvent(self, e):  # noqa: N802
        for b, sid in self._bolge:
            if b.contains(e.position()):
                self.tiklandi.emit(sid)
                return

    def mouseMoveEvent(self, e):  # noqa: N802
        self.setCursor(Qt.PointingHandCursor if any(b.contains(e.position()) for b, _ in self._bolge) else Qt.ArrowCursor)


class PersonelSayfasi(QWidget):
    def __init__(self, ana):
        super().__init__()
        self.ana = ana
        self._gunler: List[pv.Gun] = []
        self._ozet: Dict[int, pv.Ozet] = {}
        self._kisi: Dict[int, dict] = {}
        self._gizli: set = set()            # beyaz yaka görme yetkisi yoksa gizlenen siciller
        self._bakiye: Dict[int, dict] = {}
        self._izin_ad: Dict[str, str] = {}
        bugun = date.today()
        self._hafta = bugun - timedelta(days=bugun.weekday())
        self._kart_ay = date(bugun.year, bugun.month, 1)
        kok = QVBoxLayout(self)
        kok.setContentsMargins(26, 22, 26, 22)
        kok.setSpacing(10)
        kok.addWidget(etiket("Personel Durum", "Baslik"))
        self.alt = etiket("", "AltBaslik")
        kok.addWidget(self.alt)
        ust = QHBoxLayout()
        ust.addWidget(QLabel("Dönem"))
        self.aralik = AralikSecici()
        ilk = date(bugun.year, bugun.month, 1)
        self.aralik.goster(ilk, max(ilk, bugun - timedelta(days=1)))
        self.aralik.secildi.connect(lambda *_: (self._kisayol_temizle(), self.yenile()))
        ust.addWidget(self.aralik)
        from PySide6.QtWidgets import QButtonGroup
        self._kisayollar = QButtonGroup(self)
        self._kisayollar.setExclusive(True)
        kisa = QHBoxLayout()
        kisa.addWidget(QLabel("Hızlı seçim"))
        for kod, ad in (("dun", "Dün"), ("bh", "Bu hafta"), ("gh", "Geçen hafta"), ("ba", "Bu ay"), ("ga", "Geçen ay"), ("by", "Bu yıl")):
            b = QPushButton(ad)
            b.setObjectName("Hizli")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=kod: self._kisayol(k))
            self._kisayollar.addButton(b)
            kisa.addWidget(b)
        kisa.addStretch(1)
        ust.addWidget(QLabel("Vardiya"))
        self.f_vardiya = QComboBox()
        self.f_vardiya.addItem("Tümü", "")
        for k in pv.VARDIYA_SIRA:
            self.f_vardiya.addItem(pv.VARDIYA_AD[k], k)
        self.f_vardiya.currentIndexChanged.connect(lambda *_: self._ciz())
        ust.addWidget(self.f_vardiya)
        ust.addWidget(QLabel("Pozisyon"))
        self.f_poz = QComboBox()
        self.f_poz.setMinimumWidth(220)
        self.aralik.setMinimumWidth(240)
        self.f_poz.currentIndexChanged.connect(lambda *_: self._ciz())
        ust.addWidget(self.f_poz)
        from PySide6.QtWidgets import QCheckBox
        self.f_ayrilan = QCheckBox("Ayrılanları göster")   # ayrılanlar sayılara, ortalamalara, vardiya listesine ve sıralamalara girmez
        self.f_ayrilan.setToolTip("İşten ayrılan personel listede ve Excel'de görünür; ama personel sayısına, devam oranına, toplamlara, "
                                  "vardiya listesine ve sıralamalara hiçbir zaman girmez (sıralamalarda ayrı listede).")
        self.f_ayrilan.toggled.connect(lambda *_: self._ciz())
        ust.addWidget(self.f_ayrilan)
        ust.addStretch(1)
        b_al = QPushButton("Personel verisini al")
        b_al.setToolTip("Personel veri ekranı program içinde açılır; listelediğiniz ay kaydedilir.")
        b_al.clicked.connect(self._veri_al)
        self._b_al = b_al
        b_xl = QPushButton("Excel'e aktar")
        b_xl.clicked.connect(self._excel)
        self._b_xl = b_xl
        kisa.addWidget(b_al)
        kisa.addWidget(b_xl)
        kok.addLayout(ust)
        kok.addLayout(kisa)

        self.sekme = QTabWidget()
        self.sekme.setDocumentMode(True)
        self.sekme.addTab(self._devam_sekmesi(), "Devam özeti")
        self.sekme.addTab(self._vardiya_sekmesi(), "Vardiya listesi")
        self.sekme.addTab(self._sira_sekmesi(), "Sıralamalar")
        self.sekme.addTab(self._kart_sekmesi(), "Personel kartı")
        self.sekme.setStyleSheet(f"QTabBar::tab {{ padding: 8px 18px; font-weight: 600; color: {tema.YAZI_SOLUK}; }}"
                                 f"QTabBar::tab:selected {{ color: white; background: {tema.LACIVERT}; border-radius: 6px 6px 0 0; }}")
        kok.addWidget(self.sekme, 1)

    # ================================================================ sekmeler
    def _devam_sekmesi(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 10, 0, 0)
        self.kpi_satir = QHBoxLayout()
        self.kpi = {}
        self.kpi_kart = {}
        for k, ad in (("kisi", "personel"), ("devam", "devam oranı"), ("gelmedi", "izinsiz gelmeme (gün)"),
                      ("gec", "geç gelme"), ("erken", "erken çıkma"), ("fazla", "fazla çalışma"), ("izin", "izinli gün")):
            c = QFrame()
            c.setObjectName("KpiKart")
            cl = QVBoxLayout(c)
            cl.setContentsMargins(14, 10, 12, 10)
            cl.setSpacing(2)
            d = QLabel("-")
            b = QLabel(ad + "  ▾")
            cl.addWidget(d)
            cl.addWidget(b)
            c.setCursor(Qt.PointingHandCursor)
            c.setToolTip("Tıklayın: altta grafik ve ayrıntı (yeniden tıklayınca kapanır)" if k == "devam"
                         else "Tıklayın: altta liste (yeniden tıklayınca kapanır)")
            c.mousePressEvent = (lambda _e, k=k: self._kpi_tik(k))
            self.kpi[k] = d
            self.kpi_kart[k] = (c, d, b)
            self.kpi_satir.addWidget(c)
        l.addLayout(self.kpi_satir)
        self._kpi_secili = ""
        self._dilim_secili = ""
        self.kpi_panel = QFrame()                    # kutuya tıklanınca altta açılan bölüm
        self.kpi_panel.setObjectName("KpiPanel")
        pl = QVBoxLayout(self.kpi_panel)
        pl.setContentsMargins(16, 14, 16, 14)
        pl.setSpacing(10)
        self.kpi_grafik = QWidget()                  # yalnızca devam oranında: halka + renkli dilim kutuları
        gl_ = QHBoxLayout(self.kpi_grafik)
        gl_.setContentsMargins(0, 0, 0, 0)
        gl_.setSpacing(22)
        self.pasta = _Pasta([], None)
        self.pasta.tiklandi.connect(self._dilim_sec)
        gl_.addWidget(self.pasta)
        sag = QVBoxLayout()
        sag.setSpacing(10)
        self.dilim_kutu = {}
        satir = QHBoxLayout()
        satir.setSpacing(10)
        for k, ad in (("geldi", "Geldi"), ("gelmedi", "İzinsiz gelmedi"), ("izin", "İzinli (tam gün)")):
            f = QFrame()
            f.setObjectName("DilimKutu")
            fl = QVBoxLayout(f)
            fl.setContentsMargins(14, 10, 14, 10)
            fl.setSpacing(1)
            a, v, y = QLabel(ad), QLabel("-"), QLabel("")
            for x in (a, v, y):
                fl.addWidget(x)
            f.setCursor(Qt.PointingHandCursor)
            f.mousePressEvent = (lambda _e, k=k: self._dilim_sec(k))
            self.dilim_kutu[k] = (f, a, v, y)
            satir.addWidget(f, 1)
        sag.addStretch(1)
        sag.addLayout(satir)
        self.devam_formul = QLabel("")
        self.devam_formul.setStyleSheet(f"color:{tema.YAZI_SOLUK}; font-size:12px; background:#f5f6fa; border-radius:8px; padding:8px 12px;")
        sag.addWidget(self.devam_formul)
        ip = QLabel("Dilime ya da kutuya tıklayın: ayrıntısı aşağıda listelenir")
        ip.setStyleSheet(f"color:{tema.YAZI_SOLUK}; font-size:11px;")
        sag.addWidget(ip)
        sag.addStretch(1)
        gl_.addLayout(sag, 1)
        pl.addWidget(self.kpi_grafik)
        self.kpi_panel_baslik = QLabel("")
        self.kpi_panel_baslik.setStyleSheet(f"font-weight:700; font-size:13px; color:{tema.LACIVERT};")
        pl.addWidget(self.kpi_panel_baslik)
        self.kpi_tablo = QTableWidget()
        self._tablo_ayar(self.kpi_tablo)
        self.kpi_tablo.setMaximumHeight(320)
        self.kpi_tablo.cellDoubleClicked.connect(lambda r, _c: self._kart_ac(self.kpi_tablo.item(r, 0).data(Qt.UserRole))
                                                 if self.kpi_tablo.item(r, 0) else None)
        pl.addWidget(self.kpi_tablo)
        self.kpi_panel.hide()
        l.addWidget(self.kpi_panel)
        self._kpi_stil()
        self.t_devam = QTableWidget()
        self.t_devam.setColumnCount(11)
        self.t_devam.setHorizontalHeaderLabels(["Personel", "Pozisyon", "Vardiya", "Planlı gün", "Geldi", "Gelmedi\n(izinsiz)",
                                                "İzinli gün", "Geç gelme\nadet / süre", "Erken çıkma\nadet / süre",
                                                "Fazla çalışma", "Tatilde\nçalıştı"])
        self._tablo_ayar(self.t_devam)
        self.t_devam.cellDoubleClicked.connect(lambda r, _c: self._kart_ac(self.t_devam.item(r, 0).data(Qt.UserRole)))
        self.t_devam.cellClicked.connect(lambda r, _c: self._kart_sec(self.t_devam.item(r, 0).data(Qt.UserRole)))
        l.addWidget(self.t_devam, 1)
        not_ = etiket("", "AltBaslik")
        self.devam_not = not_
        l.addWidget(not_)
        return w

    def _vardiya_sekmesi(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 10, 0, 0)
        ust = QHBoxLayout()
        b1, b2, b3 = QPushButton("◀"), QPushButton("Bu hafta"), QPushButton("▶")
        b1.clicked.connect(lambda: self._hafta_git(-7))
        b2.clicked.connect(lambda: self._hafta_git(0))
        b3.clicked.connect(lambda: self._hafta_git(7))
        self.hafta_et = etiket("", "KartBaslik", kelime=False)
        for x in (b1, b2, b3, self.hafta_et):
            ust.addWidget(x)
        ust.addStretch(1)
        l.addLayout(ust)
        l.addWidget(etiket("Bu haftanın grup liderleri (hücreye çift tıklayıp düzeltebilirsiniz; adları virgülle ayırın)", "KartBaslik"))
        self.t_lider = QTableWidget(1, 4)
        self.t_lider.setHorizontalHeaderLabels([pv.VARDIYA_AD[k] for k in pv.VARDIYA_SIRA])
        self.t_lider.verticalHeader().hide()
        self.t_lider.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.t_lider.setFixedHeight(64)
        self.t_lider.itemChanged.connect(self._lider_degisti)
        l.addWidget(self.t_lider)
        tur = QHBoxLayout()                    # grup lideri türü: Performans'ta yalnızca CNC liderleri görünür
        tur.addWidget(etiket("Grup lideri türü (Performans'ta yalnızca CNC liderleri görünür):", "AltBaslik"))
        self.lider_tur_kutu = QHBoxLayout()
        tur.addLayout(self.lider_tur_kutu)
        tur.addStretch(1)
        l.addLayout(tur)
        self.t_vardiya = QTableWidget()
        self.t_vardiya.setColumnCount(8)
        self.t_vardiya.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.t_vardiya.verticalHeader().hide()
        self.t_vardiya.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.t_vardiya.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.t_vardiya.cellDoubleClicked.connect(lambda r, _c: self._kart_ac(self.t_vardiya.item(r, 0).data(Qt.UserRole))
                                                 if self.t_vardiya.item(r, 0) and self.t_vardiya.item(r, 0).data(Qt.UserRole) else None)
        tablo_menusu(self.t_vardiya)
        l.addWidget(self.t_vardiya, 1)
        lej = QHBoxLayout()
        for ad, rk in (("1. vardiya", RENK["3"]), ("2. vardiya", RENK["1"]), ("3. vardiya", RENK["2"]), ("gündüz", RENK["G"]),
                       ("tek okutma", RENK["okutma"]),
                       ("izinli", RENK[pv.IZIN_TAM]), ("geç / erken", RENK["gec"]), ("gelmedi", RENK[pv.GELMEDI]),
                       ("hafta tatili", RENK[pv.TATIL]), ("tatilde çalıştı", RENK[pv.TATIL_CALISTI])):
            e = QLabel(f"  {ad}  ")
            e.setStyleSheet(f"background:{rk}; border:1px solid #d9dee8; border-radius:3px; padding:2px;")
            lej.addWidget(e)
        lej.addWidget(QLabel("  ★ grup lideri · satıra çift tıklayın: personel kartı"))
        lej.addStretch(1)
        l.addLayout(lej)
        return w

    def _sira_sekmesi(self) -> QWidget:
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        w = QWidget()
        g = QGridLayout(w)
        g.setContentsMargins(0, 10, 0, 0)
        g.setSpacing(12)
        self.siralar = {}
        for i, (k, ad, rk) in enumerate((("gelmedi", "En çok izinsiz gelmeyen (gün)", tema.KIRMIZI),
                                         ("gec", "En çok geç gelen (adet · toplam süre)", tema.TURUNCU),
                                         ("izin", "En çok izin kullanan (gün, türe göre)", tema.YESIL),
                                         ("fazla", "En çok fazla çalışan (saat)", tema.LACIVERT),
                                         ("erken", "En çok erken çıkan (adet · toplam süre)", "#D35400"),
                                         ("tatil", "Tatilde en çok çalışan (gün)", "#4472C4"))):
            c = kart()
            cl = CubukListesi(ad, rk)
            cl.tiklandi.connect(self._kart_ac)
            c.layout().addWidget(cl)
            self.siralar[k] = cl
            g.addWidget(c, i // 2, i % 2)
        self.sira_lej = etiket("", "AltBaslik")
        g.addWidget(self.sira_lej, 3, 0, 1, 2)
        ka = kart()
        self.sira_ayrilan = QLabel("")
        self.sira_ayrilan.setTextFormat(Qt.RichText)
        self.sira_ayrilan.setWordWrap(True)
        ka.layout().addWidget(self.sira_ayrilan)
        g.addWidget(ka, 4, 0, 1, 2)
        g.setRowStretch(5, 1)
        sc.setWidget(w)
        return sc

    def _kart_sekmesi(self) -> QWidget:
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 10, 0, 0)
        ust = QHBoxLayout()
        ust.addWidget(QLabel("Personel"))
        self.k_kisi = QComboBox()
        self.k_kisi.setMinimumWidth(260)
        self.k_kisi.currentIndexChanged.connect(lambda *_: self._kart_ciz())
        ust.addWidget(self.k_kisi)
        ust.addStretch(1)
        l.addLayout(ust)
        sat = QHBoxLayout()
        k1 = kart(QHBoxLayout)
        self.k_foto = QLabel()
        self.k_foto.setFixedSize(130, 160)
        self.k_foto.setAlignment(Qt.AlignCenter)
        self.k_foto.setStyleSheet("background:#e4e8f0; border-radius:8px; color:#6b7285;")
        k1.layout().addWidget(self.k_foto, 0, Qt.AlignTop)
        self.k_bilgi = QLabel()
        self.k_bilgi.setTextFormat(Qt.RichText)
        self.k_bilgi.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.k_bilgi.setTextInteractionFlags(Qt.TextSelectableByMouse)
        k1.layout().addWidget(self.k_bilgi, 1)
        sat.addWidget(k1, 3)
        k2 = kart()
        k2.layout().addWidget(etiket("Seçili dönem özeti", "KartBaslik"))
        from .ozet_gorsel import OzetGorsel
        self.k_ozet = OzetGorsel()
        self.k_ozet.kutu_tiklandi.connect(self._ozet_liste)
        k2.layout().addWidget(self.k_ozet)
        k2.layout().addStretch(1)
        sat.addWidget(k2, 3)
        l.addLayout(sat)
        self.k_liste_kart = kart()                 # özet kutusuna tıklanınca: o günlerin listesi
        self.k_liste_baslik = etiket("", "KartBaslik", kelime=False)
        self.k_liste_kart.layout().addWidget(self.k_liste_baslik)
        self.k_liste = QTableWidget(0, 4)
        self.k_liste.setHorizontalHeaderLabels(["Tarih", "Vardiya", "Giriş – çıkış", "Açıklama"])
        self.k_liste.verticalHeader().hide()
        self.k_liste.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.k_liste.horizontalHeader().setStretchLastSection(True)
        self.k_liste.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.k_liste.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.k_liste.cellClicked.connect(self._ozet_liste_tik)
        self.k_liste_kart.layout().addWidget(self.k_liste)
        self.k_liste_kart.hide()
        l.addWidget(self.k_liste_kart)
        self._kart_veri = None
        k3 = kart()
        ust2 = QHBoxLayout()
        b1, b3 = QPushButton("◀"), QPushButton("▶")
        b1.clicked.connect(lambda: self._kart_ay_git(-1))
        b3.clicked.connect(lambda: self._kart_ay_git(1))
        self.k_ay = etiket("", "KartBaslik", kelime=False)
        for x in (b1, self.k_ay, b3):
            ust2.addWidget(x)
        ust2.addStretch(1)
        k3.layout().addLayout(ust2)
        self.k_takvim = QTableWidget(6, 7)
        self.k_takvim.setHorizontalHeaderLabels(list(GUNLER))
        self.k_takvim.verticalHeader().hide()
        self.k_takvim.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.k_takvim.verticalHeader().setDefaultSectionSize(58)
        self.k_takvim.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.k_takvim.setWordWrap(True)
        self.k_takvim.setMinimumHeight(6 * 58 + 34)
        k3.layout().addWidget(self.k_takvim)
        l.addWidget(k3)
        l.addStretch(1)
        sc.setWidget(w)
        return sc

    @staticmethod
    def _tablo_ayar(t: QTableWidget):
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSortingEnabled(True)
        t.verticalHeader().hide()
        t.setAlternatingRowColors(True)
        h = t.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeToContents)
        h.setStretchLastSection(True)
        tablo_menusu(t)

    # ================================================================ dönem kısayolları
    @staticmethod
    def kisayol_araligi(kod: str, bugun: Optional[date] = None):
        """Bugün henüz bitmediği için 'bu' dönemler dünde biter."""
        bugun = bugun or date.today()
        dun = bugun - timedelta(days=1)
        pzt = bugun - timedelta(days=bugun.weekday())
        ay1 = date(bugun.year, bugun.month, 1)
        if kod == "dun":
            return dun, dun
        if kod == "bh":
            return pzt, max(pzt, dun)
        if kod == "gh":
            return pzt - timedelta(days=7), pzt - timedelta(days=1)
        if kod == "ba":
            return ay1, max(ay1, dun)
        if kod == "ga":
            son = ay1 - timedelta(days=1)
            return date(son.year, son.month, 1), son
        if kod == "by":
            y1 = date(bugun.year, 1, 1)
            return y1, max(y1, dun)
        raise ValueError(kod)

    def _kisayol(self, kod: str):
        self.aralik.goster(*self.kisayol_araligi(kod))
        self.yenile()

    def _kisayol_temizle(self):
        self._kisayollar.setExclusive(False)
        for b in self._kisayollar.buttons():
            b.setChecked(False)
        self._kisayollar.setExclusive(True)

    # ================================================================ veri
    def yetki_uygula(self, yetkili):
        from PySide6.QtWidgets import QAbstractItemView
        self._b_al.setVisible(yetkili("personel_veri"))
        self._b_xl.setVisible(yetkili("excel"))
        self.t_lider.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
                                     if yetkili("grup_lideri") else QAbstractItemView.NoEditTriggers)
        if getattr(self, "_kisi", None):
            self._kart_ciz()

    def _yetki(self, anahtar: str) -> bool:
        f = getattr(self.ana, "yetkili", None)
        return True if f is None else f(anahtar)

    def yenile(self):
        con = self.ana.con
        ilk, son = self.aralik.aralik()
        try:
            gl, _ = pv.donem_hesabi(con, ilk, son, self.ana.ayar)
            self._gunler, self._ozet, self._kisi, self._gizli = pv.yaka_suz(gl, pv.personel(con), self._yetki("personel_beyaz"))
            self._bakiye = pv.bakiyeler(con)
            self._izin_ad = pv.izin_adlari(con)
            a, b, n = pv.kapsam(con)
            if self._gizli:
                n = len(self._kisi)
        except Exception as e:  # noqa: BLE001
            self.alt.setText(f"Personel verisi okunamadı: {e}")
            return
        self._kart_ay = date(son.year, son.month, 1)
        if a:
            self.alt.setText(f"Personel verisi: {pv._tr(a)} – {pv._tr(b)} · {n} kişi · geç gelme / erken çıkma toleransı "
                             f"{self.ana.ayar.get('pv_tolerans_dk', pv.VARSAYILAN_TOLERANS_DK)} dk")
        else:
            self.alt.setText("Henüz personel verisi yok: 'Personel verisini al' ile giriş yapıp Planlanan + Gerçekleşen ekranında ayı listeleyin.")
        poz = sorted({str(p.get("pozisyon") or "") for p in self._kisi.values() if p.get("pozisyon")})
        secili = self.f_poz.currentData()
        self.f_poz.blockSignals(True)
        self.f_poz.clear()
        self.f_poz.addItem("Tümü", "")
        for p in poz:
            self.f_poz.addItem(pv.tr_baslik(p), p)
        i = self.f_poz.findData(secili)
        self.f_poz.setCurrentIndex(max(0, i))
        self.f_poz.blockSignals(False)
        self._ciz()

    def _baskin_vardiya(self) -> Dict[int, str]:
        say: Dict[int, Dict[str, int]] = {}
        for g in self._gunler:
            if g.vardiya in ("1", "2", "3", "G"):
                d = say.setdefault(g.sicilid, {})
                d[g.vardiya] = d.get(g.vardiya, 0) + 1
        return {sid: max(d.items(), key=lambda x: x[1])[0] for sid, d in say.items()}

    def _secili_kisiler(self, hepsi: bool = False) -> List[int]:
        v, pz = self.f_vardiya.currentData(), self.f_poz.currentData()
        bv = self._baskin_vardiya()
        sonuc = []
        for sid in self._ozet:
            p = self._kisi.get(sid, {})
            if v and bv.get(sid) != v:
                continue
            if pz and str(p.get("pozisyon") or "") != pz:
                continue
            if p.get("cikis_tarih") and not (hepsi or self.f_ayrilan.isChecked()):
                continue
            sonuc.append(sid)
        return sorted(sonuc, key=lambda s: str(self._kisi.get(s, {}).get("ad", "")))

    def _izin_kisa(self, kod: str) -> str:
        return pv.izin_kisa(self._izin_ad, kod)

    def _ad(self, sid: int) -> str:
        return str(self._kisi.get(sid, {}).get("ad") or sid)

    def _cikis(self, sid: int) -> str:
        return str(self._kisi.get(sid, {}).get("cikis_tarih") or "")

    def _gorunen_ad(self, sid: int) -> str:
        c = self._cikis(sid)
        return (pv.tr_baslik(self._ad(sid)) + (f" ★ {pv.lider_turu(self.ana.ayar, sid)}" if self._lider_mi(sid) else "")
                + (f" · ayrıldı {pv._tr(c)}" if c else ""))

    def _lider_mi(self, sid: int) -> bool:
        return pv.lider_mi(self._kisi.get(sid, {}))

    def _ciz(self):
        kisiler = self._secili_kisiler()
        self._devam_ciz(kisiler)
        self._lider_tur_ciz()
        self._vardiya_ciz()
        self._sira_ciz(kisiler)
        sec = self.k_kisi.currentData()
        self.k_kisi.blockSignals(True)
        self.k_kisi.clear()
        for sid in sorted(self._kisi, key=lambda s: self._ad(s)):
            self.k_kisi.addItem(pv.tr_baslik(self._ad(sid)) + (" (ayrıldı)" if self._cikis(sid) else ""), sid)
        self.k_kisi.setCurrentIndex(max(0, self.k_kisi.findData(sec)))
        self.k_kisi.blockSignals(False)
        self._kart_ciz()

    # ---------------------------------------------------------------- devam özeti
    def _devam_ciz(self, kisiler: List[int]):
        t = self.t_devam
        t.setSortingEnabled(False)
        t.setRowCount(len(kisiler))
        bv = self._baskin_vardiya()
        top = pv.Ozet(0)
        for i, sid in enumerate(kisiler):
            o, p = self._ozet[sid], self._kisi.get(sid, {})
            for a in () if self._cikis(sid) else ("planli", "geldi", "gelmedi", "eksik", "izinli", "gec_adet", "gec_dk", "erken_adet", "erken_dk", "fazla_dk",
                      "tatil_calisti"):
                setattr(top, a, getattr(top, a) + getattr(o, a))
            it0 = _hucre_kisi(self._gorunen_ad(sid), sid)
            if self._cikis(sid):
                it0.setForeground(QColor(tema.YAZI_SOLUK))
                it0.setToolTip(f"İşten çıkış: {pv._tr(self._cikis(sid))}")
            t.setItem(i, 0, it0)
            t.setItem(i, 1, QTableWidgetItem(pv.tr_baslik(p.get("pozisyon") or "")))
            t.setItem(i, 2, _hucre(pv.VARDIYA_KISA.get(bv.get(sid), "-"),
                                   bv.get(sid, "Z")))
            t.setItem(i, 3, _sayi(o.planli))
            it = _sayi(o.geldi, f"{o.geldi}  ⚠{o.okutma}" if o.okutma else str(o.geldi))
            if o.okutma:
                it.setBackground(QColor(RENK["okutma"]))
                it.setToolTip(f"{o.okutma} gün tek kart okutması (girişte ya da çıkışta okutmamış) — kontrol edin:\n" + "\n".join(
                    f"{g.gun:%d.%m.%Y}: {pv.okutma_yazi(g)}" for g in self._gunler if g.sicilid == sid and pv.okutma_eksik(g)))
            t.setItem(i, 4, it)
            it = _sayi(o.gelmedi)
            if o.gelmedi:
                it.setBackground(QColor(RENK[pv.GELMEDI]))
            t.setItem(i, 5, it)
            it = _sayi(o.izinli, f"{o.izinli}" + (f" (+{o.izin_saat} saatlik)" if o.izin_saat else ""))
            it.setToolTip(", ".join(f"{self._izin_ad.get(k, k)}: {n}" for k, n in sorted(o.izin_tur.items())))
            t.setItem(i, 6, it)
            it = _hucre(f"{o.gec_adet} / {pv.sure_yaz(o.gec_dk)}" if o.gec_adet else "0", o.gec_dk)
            if o.gec_adet >= 3:
                it.setBackground(QColor(RENK["gec"]))
            t.setItem(i, 7, it)
            t.setItem(i, 8, _hucre(f"{o.erken_adet} / {pv.sure_yaz(o.erken_dk)}" if o.erken_adet else "0", o.erken_dk))
            t.setItem(i, 9, _hucre(pv.sure_yaz(o.fazla_dk) if o.fazla_dk else "0", o.fazla_dk))
            t.setItem(i, 10, _sayi(o.tatil_calisti))
        t.setSortingEnabled(True)
        dv = top.devam if top.planli else None
        self.kpi["kisi"].setText(str(len([s for s in kisiler if not self._cikis(s)])))
        self.kpi["devam"].setText("-" if dv is None else f"%{dv * 100:.1f}".replace(".", ","))
        self.kpi["gelmedi"].setText(str(top.gelmedi))
        self.kpi["gec"].setText(str(top.gec_adet))
        self.kpi["erken"].setText(str(top.erken_adet))
        self.kpi["fazla"].setText(f"{top.fazla_dk // 60} sa")
        self.kpi["izin"].setText(str(top.izinli))
        if self._kpi_secili and self.kpi_panel.isVisible():
            self._kpi_panel_doldur()
        tol = self.ana.ayar.get("pv_tolerans_dk", pv.VARSAYILAN_TOLERANS_DK)
        fz = self.ana.ayar.get("pv_fazla_en_az_dk", pv.VARSAYILAN_FAZLA_EN_AZ_DK)
        self.devam_not.setText(f"Geç gelme / erken çıkma: {tol} dk tolerans. Fazla çalışma: vardiya bitişinden en az {fz} dk sonra çıkış "
                               "ve tatil günü çalışması. İzinli günlerdeki geç gelme ve erken çıkma izinli sayılır. Gelmedi: planlı gün, kart "
                               "kaydı yok, izin yok. Satıra çift "
                               "tıklayın: personel kartı.")

    # ---------------------------------------------------------------- devam özeti: kutulara tıklanınca liste / grafik
    def _kpi_listeleri(self):
        sids = [s for s in self._secili_kisiler() if not self._cikis(s)]
        return sids, pv.devam_gun_listeleri(self._gunler, self._kisi, self._izin_ad, sids)

    def _kpi_stil(self):
        for k, (c, d, b) in self.kpi_kart.items():
            rk = KPI_RENK[k]
            if k == self._kpi_secili:
                c.setStyleSheet(f"QFrame#KpiKart {{ background:{_acik(rk, .86)}; border:2px solid {rk}; border-left:6px solid {rk}; border-radius:12px; }}")
            else:
                c.setStyleSheet(f"QFrame#KpiKart {{ background:{tema.KART}; border:1px solid {tema.CIZGI}; border-left:6px solid {rk}; border-radius:12px; }}"
                                f"QFrame#KpiKart:hover {{ background:{_acik(rk, .93)}; }}")
            d.setStyleSheet(f"font-size:26px; font-weight:800; color:{rk}; background:transparent; border:none;")
            b.setStyleSheet(f"font-size:12px; font-weight:600; color:{tema.YAZI_SOLUK}; background:transparent; border:none;")
        self.kpi_panel.setStyleSheet(f"QFrame#KpiPanel {{ background:{tema.KART}; border:1px solid {tema.CIZGI}; border-radius:14px; }}")
        for k, (f, a, v, y) in self.dilim_kutu.items():
            rk = DILIM_RENK[k]
            sec = k == self._dilim_secili
            f.setStyleSheet(f"QFrame#DilimKutu {{ background:{_acik(rk, .80 if sec else .90)}; border:{2 if sec else 1}px solid {rk if sec else _acik(rk, .6)}; "
                            f"border-left:6px solid {rk}; border-radius:12px; }} QFrame#DilimKutu:hover {{ background:{_acik(rk, .82)}; }}")
            a.setStyleSheet(f"font-size:12px; font-weight:700; color:{rk}; background:transparent; border:none;")
            v.setStyleSheet(f"font-size:24px; font-weight:800; color:{tema.YAZI}; background:transparent; border:none;")
            y.setStyleSheet(f"font-size:12px; color:{tema.YAZI_SOLUK}; background:transparent; border:none;")

    def _kpi_tik(self, k: str):
        self._kpi_secili = "" if self._kpi_secili == k else k
        self._dilim_secili = ""
        self._kpi_stil()
        if not self._kpi_secili:
            self.kpi_panel.hide()
            return
        self._kpi_panel_doldur()
        self.kpi_panel.show()

    def _kpi_panel_doldur(self):
        k = self._kpi_secili
        devam = k == "devam"
        self.kpi_grafik.setVisible(devam)
        if devam:
            self._devam_grafik()
            liste = {"geldi": "kisi", "gelmedi": "gelmedi", "izin": "izin"}.get(self._dilim_secili)
            self.kpi_panel_baslik.setVisible(bool(liste))
            self.kpi_tablo.setVisible(bool(liste))
            if liste:
                self._kpi_doldur(self.kpi_tablo, self.kpi_panel_baslik, liste)
        else:
            self.kpi_panel_baslik.show()
            self.kpi_tablo.show()
            self._kpi_doldur(self.kpi_tablo, self.kpi_panel_baslik, k)

    def _dilim_sec(self, k: str):
        self._dilim_secili = "" if self._dilim_secili == k else k
        self._kpi_stil()
        self._kpi_panel_doldur()

    def _kpi_doldur(self, t, baslik, k: str):
        sids, lst = self._kpi_listeleri()
        bv = self._baskin_vardiya()
        if k == "kisi":
            bas = ["Personel", "Pozisyon", "Vardiya", "Planlı", "Geldi", "Gelmedi", "İzinli", "Devam"]
            satir = []
            for sid in sids:
                o = self._ozet[sid]
                satir.append((sid, [pv.tr_baslik(self._ad(sid)), pv.tr_baslik(self._kisi.get(sid, {}).get("pozisyon") or ""),
                                    pv.VARDIYA_KISA.get(bv.get(sid), "-"),
                                    str(o.planli), str(o.geldi), str(o.gelmedi), str(o.izinli),
                                    "-" if o.devam is None else f"%{o.devam * 100:.1f}".replace(".", ",")]))
            baslik.setText(f"Personel listesi: {len(sids)} kişi  ·  satıra çift tıklayın: personel kartı")
        else:
            ad, kol = {"gelmedi": ("İzinsiz gelmeme", "Durum"), "gec": ("Geç gelme", "Geç"), "erken": ("Erken çıkma", "Erken"),
                       "fazla": ("Fazla çalışma (her gün ayrı)", "Fazla çalışma"), "izin": ("İzinli günler (tam gün + saatlik)", "İzin türü")}[k]
            bas = ["Personel", "Tarih", "Planlanan", "Giriş – çıkış", kol]
            rows = lst.get(k, [])
            satir = [(r["sid"], [r["ad"], r["tarih"], r["plan"], r["saat"], r["deger"]]) for r in rows]
            top = sum(r["dk"] for r in rows)
            baslik.setText(f"{ad}: {len(rows)} gün · {len({r['sid'] for r in rows})} kişi" + (f" · toplam {pv.sure_yaz(top)}" if top else "")
                           + "  ·  satıra çift tıklayın: personel kartı")
        t.setSortingEnabled(False)
        t.clear()
        t.setColumnCount(len(bas))
        t.setHorizontalHeaderLabels(bas)
        t.setRowCount(len(satir))
        for i, (sid, deg) in enumerate(satir):
            for j, x in enumerate(deg):
                it = QTableWidgetItem(x)
                if j == 0:
                    it.setData(Qt.UserRole, sid)
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                t.setItem(i, j, it)
        t.resizeColumnsToContents()
        t.setSortingEnabled(True)

    def _devam_grafik(self):
        sids, _lst = self._kpi_listeleri()
        planli = gelmedi = izinli = 0
        for sid in sids:
            o = self._ozet[sid]
            planli += o.planli
            gelmedi += o.gelmedi
            izinli += o.izinli
        geldi = max(0, planli - izinli - gelmedi)
        payda = planli - izinli
        oran = geldi / payda if payda > 0 else None
        deg = {"geldi": geldi, "gelmedi": gelmedi, "izin": izinli}
        toplam = sum(deg.values()) or 1
        self.pasta.dilim = [(k, "", deg[k], DILIM_RENK[k]) for k in ("geldi", "gelmedi", "izin")]
        self.pasta.oran, self.pasta.secili = oran, self._dilim_secili
        self.pasta.update()
        for k, (_f, _a, v, y) in self.dilim_kutu.items():
            v.setText(f"{deg[k]} gün")
            y.setText(f"%{deg[k] / toplam * 100:.1f}".replace(".", ",") + " · tıklayın: ayrıntı")
        yz = "-" if oran is None else f"%{oran * 100:.1f}".replace(".", ",")
        self.devam_formul.setText(f"Devam oranı = gelinen gün ÷ (planlı gün − izinli gün)   ·   {yz} = {geldi} ÷ ({planli} − {izinli})")

    # ---------------------------------------------------------------- vardiya listesi
    def _hafta_git(self, gun: int):
        bugun = date.today()
        self._hafta = (bugun - timedelta(days=bugun.weekday())) if gun == 0 else self._hafta + timedelta(days=gun)
        self._vardiya_ciz()

    def _vardiya_ciz(self):
        h0 = self._hafta
        con = self.ana.con
        self.hafta_et.setText(f"Hafta: {h0:%d.%m.%Y} – {h0 + timedelta(days=6):%d.%m.%Y}")
        try:
            gl, _ = pv.donem_hesabi(con, h0, h0 + timedelta(days=6), self.ana.ayar)
            liderler = pv.hafta_grup_liderleri(con, h0, self.ana.ayar)
            gizli = getattr(self, "_gizli", set())
            if gizli:
                tum = pv.personel(con)
                gl = [g for g in gl if g.sicilid not in gizli]
                liderler = {k: pv.ad_suz(v, tum, gizli) for k, v in liderler.items()}
        except Exception:  # noqa: BLE001
            gl, liderler = [], {}
        self.t_lider.blockSignals(True)
        for j, k in enumerate(pv.VARDIYA_SIRA):
            self.t_lider.setItem(0, j, QTableWidgetItem(", ".join(pv.tr_baslik(x) for x in liderler.get(k, []))))
        self.t_lider.blockSignals(False)
        v, pz = self.f_vardiya.currentData(), self.f_poz.currentData()
        kisi: Dict[int, Dict[date, pv.Gun]] = {}
        say: Dict[int, Dict[str, int]] = {}
        for g in gl:
            kisi.setdefault(g.sicilid, {})[g.gun] = g
            if g.vardiya in ("1", "2", "3", "G"):
                say.setdefault(g.sicilid, {}).setdefault(g.vardiya, 0)
                say[g.sicilid][g.vardiya] += 1
        bask = {sid: (max(d.items(), key=lambda x: x[1])[0] if d else "Z") for sid, d in say.items()}
        satirlar = []
        for sid in kisi:
            if self._cikis(sid):
                continue                                   # ayrılan personel vardiya listesinde yok
            if v and bask.get(sid) != v:
                continue
            if pz and str(self._kisi.get(sid, {}).get("pozisyon") or "") != pz:
                continue
            satirlar.append(sid)
        sira = {k: i for i, k in enumerate(pv.VARDIYA_SIRA)}
        satirlar.sort(key=lambda s: (sira.get(bask.get(s, "Z"), 9), not self._lider_mi(s), self._ad(s)))
        t = self.t_vardiya
        t.clearSpans()
        t.clearContents()
        t.setHorizontalHeaderLabels(["Personel"] + [f"{GUNLER[i]} {(h0 + timedelta(days=i)).day}" for i in range(7)])
        # vardiya başlık satırları ile
        satir_listesi: List[Optional[int]] = []
        onceki = None
        for sid in satirlar:
            b = bask.get(sid, "Z")
            if b != onceki:
                satir_listesi.append(None if b == "Z" else -int(sira.get(b, 9)) - 1)
                onceki = b
            satir_listesi.append(sid)
        t.setRowCount(len(satir_listesi))
        bugun = date.today()
        for i, sid in enumerate(satir_listesi):
            if sid is None or sid < 0:
                ad = "Diğer" if sid is None else pv.VARDIYA_AD[pv.VARDIYA_SIRA[-sid - 1]]
                it = QTableWidgetItem(ad)
                f = it.font()
                f.setBold(True)
                it.setFont(f)
                it.setForeground(QColor("white"))
                it.setBackground(QColor(tema.LACIVERT))
                t.setItem(i, 0, it)
                t.setSpan(i, 0, 1, 8)
                t.setRowHeight(i, 26)
                continue
            t.setItem(i, 0, _hucre_kisi(self._gorunen_ad(sid), sid))
            for j in range(7):
                g = kisi[sid].get(h0 + timedelta(days=j))
                if g is None:
                    t.setItem(i, j + 1, QTableWidgetItem(""))
                    continue
                metin, renk = self._gun_yazi(g, bugun)
                it = QTableWidgetItem(metin)
                it.setTextAlignment(Qt.AlignCenter)
                it.setBackground(QColor(renk))
                it.setToolTip(self._gun_ipucu(g))
                t.setItem(i, j + 1, it)
            t.setRowHeight(i, 40)

    def _gun_yazi(self, g: pv.Gun, bugun: date):
        return pv.gun_yazi(g, self._izin_ad, bugun)

    def _gun_ipucu(self, g: pv.Gun) -> str:
        return pv.gun_ipucu(g, self._izin_ad)

    def _lider_tur_ciz(self):
        while self.lider_tur_kutu.count():
            w = self.lider_tur_kutu.takeAt(0).widget()
            if w is not None:
                w.hide()                    # silinene kadar sayfanın sol üstünde boş kutu gibi görünmesin
                w.setParent(None)
                w.deleteLater()
        duzenle = self._yetki("grup_lideri")
        for sid in sorted((s for s in self._kisi if self._lider_mi(s) and not self._cikis(s)), key=self._ad):
            self.lider_tur_kutu.addWidget(QLabel(pv.tr_baslik(self._ad(sid)) + ":"))
            c = QComboBox()
            c.addItems(list(pv.LIDER_TURLERI))
            c.setCurrentText(pv.lider_turu(self.ana.ayar, sid))
            c.setEnabled(duzenle)
            c.currentTextChanged.connect(lambda t, s=sid: self._lider_tur_degisti(s, t))
            self.lider_tur_kutu.addWidget(c)

    def _lider_tur_degisti(self, sid: int, tur: str):
        d = dict(self.ana.ayar.get("pv_lider_tur") or {})
        d[str(sid)] = tur
        vt.ayar_yaz(self.ana.con, "pv_lider_tur", d)
        self.ana.ayar["pv_lider_tur"] = d
        self._vardiya_ciz()

    def _lider_degisti(self, _it):
        duz = dict(self.ana.ayar.get("pv_grup_lider") or {})
        duz[self._hafta.isoformat()] = {k: [x.strip() for x in (self.t_lider.item(0, j).text() if self.t_lider.item(0, j) else "")
                                            .split(",") if x.strip()] for j, k in enumerate(pv.VARDIYA_SIRA)}
        vt.ayar_yaz(self.ana.con, "pv_grup_lider", duz)
        self.ana.ayar["pv_grup_lider"] = duz

    # ---------------------------------------------------------------- sıralamalar
    def _sira_ciz(self, kisiler: List[int]):
        ayrilan = [s for s in self._secili_kisiler(hepsi=True) if self._cikis(s)]
        self.sira_ayrilan.setText("<b>Ayrılan personel</b> (sıralamalara ve ortalamalara girmez)<br>" + ("<br>".join(
            f"{pv.tr_baslik(self._ad(s))} · ayrıldı {pv._tr(self._cikis(s))} · planlı {self._ozet[s].planli}, geldi {self._ozet[s].geldi}, "
            f"gelmedi {self._ozet[s].gelmedi}, izinli {self._ozet[s].izinli}" for s in ayrilan) if ayrilan else "Seçili dönemde yok"))
        kisiler = [s for s in kisiler if not self._cikis(s)]
        oz = [self._ozet[s] for s in kisiler]
        izin_renk = {}
        palet = [tema.YESIL, "#7A5AA6", tema.YESIL_ACIK, "#4472C4", "#C55A11", "#8B96A3", "#12A37A"]

        def rk(k):
            if k not in izin_renk:
                izin_renk[k] = palet[len(izin_renk) % len(palet)]
            return izin_renk[k]

        def lst(fn, yazi, filtre=lambda o: True, parca=None):
            v = sorted((o for o in oz if fn(o) > 0 and filtre(o)), key=lambda o: -fn(o))
            return [(o.sicilid, self._ad(o.sicilid), fn(o), yazi(o), parca(o) if parca else None) for o in v]
        self.siralar["gelmedi"].ayarla(lst(lambda o: o.gelmedi, lambda o: f"{o.gelmedi} gün"))
        self.siralar["gec"].ayarla(lst(lambda o: o.gec_adet, lambda o: f"{o.gec_adet} · {pv.sure_yaz(o.gec_dk)}"))
        self.siralar["izin"].ayarla(lst(lambda o: o.izinli + o.izin_saat,
                                        lambda o: f"{o.izinli + o.izin_saat} (" + ", ".join(
                                            f"{self._izin_kisa(k).lower()} {n}" for k, n in sorted(o.izin_tur.items(), key=lambda x: -x[1])) + ")",
                                        parca=lambda o: [(n, rk(k)) for k, n in sorted(o.izin_tur.items())]))
        self.siralar["fazla"].ayarla(lst(lambda o: o.fazla_dk, lambda o: pv.sure_yaz(o.fazla_dk)))
        self.siralar["erken"].ayarla(lst(lambda o: o.erken_adet, lambda o: f"{o.erken_adet} · {pv.sure_yaz(o.erken_dk)}"))
        self.siralar["tatil"].ayarla(lst(lambda o: o.tatil_calisti, lambda o: f"{o.tatil_calisti} gün"))
        self.sira_lej.setText("İzin renkleri: " + " · ".join(f"<span style='color:{r}'>■</span> {self._izin_ad.get(k, k)} ({k})"
                                                             for k, r in izin_renk.items()) if izin_renk else "")
        self.sira_lej.setTextFormat(Qt.RichText)

    # ---------------------------------------------------------------- personel kartı
    def _kart_sec(self, sid):
        if sid is not None:
            self.k_kisi.setCurrentIndex(max(0, self.k_kisi.findData(sid)))

    def _kart_ac(self, sid):
        if sid is None:
            return
        self._kart_sec(sid)
        self.sekme.setCurrentIndex(3)

    def _kart_ay_git(self, n: int):
        y, a = self._kart_ay.year, self._kart_ay.month + n
        while a < 1:
            y, a = y - 1, a + 12
        while a > 12:
            y, a = y + 1, a - 12
        self._kart_ay = date(y, a, 1)
        self._kart_ciz()

    def _kart_ciz(self):
        sid = self.k_kisi.currentData()
        p = self._kisi.get(sid) if sid is not None else None
        if not p:
            self.k_bilgi.setText("Personel seçin")
            self.k_ozet.ayarla(None)
            self.k_liste_kart.hide()
            self.k_foto.clear()
            return
        kimlik = self._yetki("personel_kimlik")
        self.k_foto.setVisible(kimlik)
        pm = QPixmap()
        if kimlik and p.get("foto"):
            try:
                pm.loadFromData(base64.b64decode(p["foto"]))
            except Exception:  # noqa: BLE001
                pm = QPixmap()
        if kimlik:
            self.k_foto.setPixmap(pm.scaled(130, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation) if not pm.isNull()
                                  else _bos_profil(130, 160))
        else:
            self.k_foto.clear()
        satir = [("Ad Soyad", f"<b>{pv.tr_baslik(p.get('ad') or '')}</b>"), ("Sicil no", p.get("sicilno") or "-"),
                 ("Pozisyon", pv.tr_baslik(p.get("pozisyon") or "-")), ("Yaka", pv.tr_baslik(p.get("yaka") or "-"))]
        if p.get("periyot"):
            satir.append(("Vardiya düzeni", p.get("periyot")))
        if p.get("cikis_tarih"):
            satir.append(("İşten çıkış", f"<b style='color:{tema.KIRMIZI}'>{pv._tr(p['cikis_tarih'])}</b>"))
        b = self._bakiye.get(sid) or {}
        giris = b.get("giris_tarih") or p.get("giris_tarih") or ""
        if giris:
            satir.append(("İşe giriş / kıdem", pv._tr(str(giris)[:10]) + (f" · {b['kidem']} yıl" if b.get("kidem") is not None else "")))
        if kimlik and p.get("telefon"):
            satir.append(("Cep telefonu", p.get("telefon")))
        if not kimlik:
            pass                                       # fotoğraf, telefon ve yıllık izin tek yetkide (Personel kimlik bilgileri)
        elif pv.izin_satirlari(b):
            satir.extend(pv.izin_satirlari(b))
        else:
            satir.append(("Yıllık izin", "<span style='color:#6b7285'>henüz alınmadı (otomatik çekimde gelecek)</span>"))
        if not giris:
            satir.append(("İşe giriş / kıdem", "<span style='color:#6b7285'>henüz alınmadı</span>"))
        self.k_bilgi.setText("<table cellpadding='3'>" + "".join(
            f"<tr><td style='color:#6b7285;padding-right:14px'>{a}</td><td>{d}</td></tr>" for a, d in satir) + "</table>")
        self._kart_veri = pv.kart_ozeti([g for g in self._gunler if g.sicilid == sid], self._ozet.get(sid), self._ozet, self._izin_ad)
        secili = self.k_ozet.secili if getattr(self, "_kart_sid", None) == sid else ""
        self._kart_sid = sid
        self.k_ozet.ayarla(self._kart_veri, secili)
        self._ozet_liste(secili)
        self._takvim_ciz(sid)

    def _ozet_liste(self, anahtar: str):
        """Özet kutusuna tıklanınca o günler aşağıda listelenir (aynı kutuya yeniden tıklanınca kapanır)."""
        v = self._kart_veri
        if not anahtar or not v:
            self.k_liste_kart.hide()
            return
        kutu = next((k for k in v["kutular"] if k["k"] == anahtar), {})
        ad = kutu.get("ad", anahtar)
        satirlar = v["listeler"].get(anahtar) or []
        self.k_liste_baslik.setText(f"{ad}: {len(satirlar)} gün" + (f" · toplam {kutu['sure']}" if kutu.get("sure") and satirlar else "") + ("  ·  satıra tıklayın: takvim o aya gider" if satirlar else "  ·  bu dönemde yok"))
        t = self.k_liste
        t.setRowCount(len(satirlar))
        for i, s in enumerate(satirlar):
            for j, x in enumerate((s["tarih"], s["plan"], s["saat"], s["aciklama"])):
                it = QTableWidgetItem(x)
                if j == 0:
                    it.setData(Qt.UserRole, s["gun"])
                    it.setForeground(QColor(pv.SERIT_RENK.get(s["tur"], "#1f2433")) if s["tur"] not in ("geldi", "plan") else QColor("#1f2433"))
                t.setItem(i, j, it)
        t.setFixedHeight(min(34 + 30 * max(len(satirlar), 1), 34 + 30 * 12))
        self.k_liste_kart.show()

    def _ozet_liste_tik(self, r, _c):
        it = self.k_liste.item(r, 0)
        if not it or not it.data(Qt.UserRole):
            return
        g = date.fromisoformat(it.data(Qt.UserRole))
        self._kart_ay = date(g.year, g.month, 1)
        self._takvim_ciz(self.k_kisi.currentData())

    def _takvim_ciz(self, sid):
        a0 = self._kart_ay
        son = (date(a0.year + (a0.month == 12), a0.month % 12 + 1, 1) - timedelta(days=1))
        self.k_ay.setText(f"{AYLAR[a0.month - 1]} {a0.year} · gün gün")
        try:
            gl, _ = pv.donem_hesabi(self.ana.con, a0, son, self.ana.ayar)
        except Exception:  # noqa: BLE001
            gl = []
        gm = {g.gun: g for g in gl if g.sicilid == sid and sid not in getattr(self, "_gizli", set())}
        t = self.k_takvim
        t.clearContents()
        bas = a0.weekday()
        bugun = date.today()
        for i in range(42):
            r, c = divmod(i, 7)
            gun_no = i - bas + 1
            if gun_no < 1 or gun_no > son.day:
                t.setItem(r, c, QTableWidgetItem(""))
                continue
            gun = date(a0.year, a0.month, gun_no)
            g = gm.get(gun)
            if g is None:
                it = QTableWidgetItem(f"{gun_no}")
            else:
                metin, renk = self._gun_yazi(g, bugun)
                ek = []
                if g.gec_dk:
                    ek.append(f"{g.gec_dk} dk geç")
                if g.erken_dk:
                    ek.append(f"{g.erken_dk} dk erken")
                if g.fazla_dk and g.durum == pv.GELDI:
                    ek.append(f"+{pv.sure_yaz(g.fazla_dk)}")
                it = QTableWidgetItem(f"{gun_no}  " + metin.replace("\n", " · ") + ("\n" + ", ".join(ek) if ek else ""))
                it.setBackground(QColor(renk))
                it.setToolTip(self._gun_ipucu(g))
            it.setTextAlignment(Qt.AlignLeft | Qt.AlignTop)
            t.setItem(r, c, it)

    # ================================================================ diğer
    def _veri_al(self):
        from . import personel_pencere
        self._pv_penceresi = personel_pencere.ac(self.ana.db_yolu, self, kapaninca=self.yenile)

    def _excel(self):
        yol, _ = QFileDialog.getSaveFileName(self, "Excel'e aktar", "personel_durum.xlsx", "Excel (*.xlsx)")
        if not yol:
            return
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        wb = Workbook()
        for ad, t in (("Devam özeti", self.t_devam), ("Vardiya listesi", self.t_vardiya)):
            ws = wb.active if ad == "Devam özeti" else wb.create_sheet(ad)
            ws.title = ad
            ws.append([(t.horizontalHeaderItem(c).text() if t.horizontalHeaderItem(c) else "").replace("\n", " ")
                       for c in range(t.columnCount())])
            for c in ws[1]:
                c.font = Font(bold=True, color="FFFFFF")
                c.fill = PatternFill("solid", fgColor=tema.LACIVERT.lstrip("#"))
            for r in range(t.rowCount()):
                satir = []
                for c in range(t.columnCount()):
                    it = t.item(r, c)
                    v = it.data(Qt.DisplayRole) if it else ""
                    satir.append(v.replace("\n", " ") if isinstance(v, str) else v)
                ws.append(satir)
                for c in range(t.columnCount()):
                    it = t.item(r, c)
                    if it and it.background().style() != Qt.NoBrush:
                        ws.cell(row=r + 2, column=c + 1).fill = PatternFill("solid", fgColor=it.background().color().name().lstrip("#"))
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = max(10, min(40, max(len(str(c.value or "")) for c in col) + 2))
        try:
            wb.save(yol)
            self.ana.mesaj(f"Excel dosyası kaydedildi: {yol}")
        except OSError as e:
            self.ana.mesaj(f"Kaydedilemedi: {e}")



KPI_RENK = {"kisi": "#2b3a8f", "devam": "#3e9b2a", "gelmedi": "#d64541", "gec": "#d99a00", "erken": "#e0702a",
            "fazla": "#7b4fa8", "izin": "#2a7fd1"}
DILIM_RENK = {"geldi": "#3e9b2a", "gelmedi": "#d64541", "izin": "#2a7fd1"}


def _acik(renk: str, t: float) -> str:
    """Rengi beyazla karıştırır (t=0 aynı renk, t=1 beyaz)."""
    r, g, b = (int(renk[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(int(x + (255 - x) * t) for x in (r, g, b))


class _Pasta(QWidget):
    """Devam oranı halkası; dilime tıklanınca tiklandi(anahtar). Seçili dilim öne çıkar, diğerleri soluklaşır."""
    tiklandi = Signal(str)
    BOY = 250

    def __init__(self, dilim, oran, parent=None):
        super().__init__(parent)
        self.dilim, self.oran, self.secili = dilim, oran, ""
        self.setFixedSize(self.BOY, self.BOY)
        self.setCursor(Qt.PointingHandCursor)
        self._acilar = []

    def paintEvent(self, _e):  # noqa: N802
        import math
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        B = self.BOY
        m = B / 2
        top = sum(x[2] for x in self.dilim) or 1
        a = 90.0
        self._acilar = []
        p.setPen(QPen(QColor("#eef0f5"), 34, Qt.SolidLine, Qt.FlatCap))
        p.drawEllipse(QRectF(30, 30, B - 60, B - 60))
        bosluk = 1.6 if sum(1 for x in self.dilim if x[2] > 0) > 1 else 0
        for k, _ad, n, rk in self.dilim:
            span = 360.0 * n / top
            if span <= 0:
                continue
            sec = self.secili == k
            renk = QColor(rk) if (not self.secili or sec) else QColor(_acik(rk, .55))
            kal = 42 if sec else 34
            p.setPen(QPen(renk, kal, Qt.SolidLine, Qt.FlatCap))
            ciz = max(span - bosluk, 0.6)
            p.drawArc(QRectF(30, 30, B - 60, B - 60), int((a - bosluk / 2) * 16), int(-ciz * 16))
            self._acilar.append((k, a - span, a))
            a -= span
        p.setPen(QColor(tema.LACIVERT))
        f = QFont(self.font())
        f.setPixelSize(30)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(0, m - 26, B, 40), Qt.AlignCenter, "-" if self.oran is None else f"%{self.oran * 100:.1f}".replace(".", ","))
        f.setPixelSize(12)
        f.setBold(False)
        p.setFont(f)
        p.setPen(QColor(tema.YAZI_SOLUK))
        p.drawText(QRectF(0, m + 12, B, 20), Qt.AlignCenter, "devam oranı")
        _ = math

    def mousePressEvent(self, e):  # noqa: N802
        import math
        m = self.BOY / 2
        x, y = e.position().x() - m, m - e.position().y()
        if not (m - 70 <= math.hypot(x, y) <= m - 5):
            return
        aci = math.degrees(math.atan2(y, x))
        for k, a0, a1 in self._acilar:
            for t in (aci, aci - 360, aci + 360):
                if a0 <= t <= a1:
                    self.tiklandi.emit(k)
                    return
