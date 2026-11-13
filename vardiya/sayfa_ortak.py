"""Sayfalarda ortak kullanılan küçük bileşenler."""
from __future__ import annotations

from typing import Callable, List, Optional

from PySide6.QtCore import QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QMenu, QSizePolicy, QTableWidget,
                               QVBoxLayout, QWidget)


def _mesaj(w: QWidget, metin: str):
    pencere = w.window()
    if hasattr(pencere, "mesaj"):
        pencere.mesaj(metin)


def resim_menusu(w: QWidget, resim_fn: Callable[[], Optional[QImage]], metin_fn: Optional[Callable[[], str]] = None):
    """Bileşene sağ tık menüsü ekler: Resim olarak kopyala / Resmi kaydet (/ Metin olarak kopyala)."""
    w.setContextMenuPolicy(Qt.CustomContextMenu)

    def ac(konum):
        m = QMenu(w)
        a_kopya = m.addAction("Resim olarak kopyala")
        a_kaydet = m.addAction("Resmi dosyaya kaydet…")
        a_metin = m.addAction("Metin olarak kopyala (Excel'e yapıştırılır)") if metin_fn else None
        secilen = m.exec(w.mapToGlobal(konum))
        if secilen is None:
            return
        if secilen is a_metin:
            QGuiApplication.clipboard().setText(metin_fn())
            _mesaj(w, "Tablo metin olarak panoya kopyalandı. Excel'de Ctrl+V ile yapıştırabilirsiniz.")
            return
        img = resim_fn()
        if img is None or img.isNull():
            return
        if secilen is a_kopya:
            QGuiApplication.clipboard().setImage(img)
            _mesaj(w, "Resim olarak panoya kopyalandı. İstediğiniz yere Ctrl+V ile yapıştırabilirsiniz.")
        elif secilen is a_kaydet:
            yol, _ = QFileDialog.getSaveFileName(w, "Resmi kaydet", "resim.png", "PNG resim (*.png)")
            if yol:
                img.save(yol, "PNG")
                _mesaj(w, f"Kaydedildi: {yol}")

    w.customContextMenuRequested.connect(ac)


def tablo_menusu(t: QTableWidget):
    """QTableWidget için sağ tık kopyalama (görünen tablo resmi + tüm satırlar metin)."""
    def metin():
        satirlar = ["\t".join((t.horizontalHeaderItem(c).text() if t.horizontalHeaderItem(c) else "") for c in range(t.columnCount()))]
        for r in range(t.rowCount()):
            satirlar.append("\t".join((t.item(r, c).text() if t.item(r, c) else "") for c in range(t.columnCount())))
        return "\n".join(satirlar)

    resim_menusu(t, lambda: t.grab().toImage(), metin)


class CizimWidget(QWidget):
    """cizici(p, rect) çağrılabilirini boyar; ekran, pano ve PDF aynı kodu kullanır.
    Web'li exe'de: çizilen grafik web görünümüyle (canlı, üzerine gelince bilgi, tıklama) gösterilir;
    web karşılığı olmayan içerik (ör. sabit tablo) programın kendi çizimiyle kalır."""

    def __init__(self, cizici: Optional[Callable] = None, min_h: int = 200, min_w: int = 200,
                 kopya_resim: Optional[Callable[[], Optional[QImage]]] = None):
        super().__init__()
        self.cizici = cizici
        self.setMinimumSize(min_w, min_h)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._web = None
        self._web_aktif = False
        self._web_planli = False
        self._web_bos = False                   # son denemede web karşılığı yoktu (ör. sabit tablo)
        self._buyuk = None
        resim_menusu(self, kopya_resim or self.resim)
        from PySide6.QtWidgets import QToolButton
        self.b_buyut = QToolButton(self)        # büyüteç: grafiği tam ekran açar, tekrar basınca küçülür
        self.b_buyut.setText("🔍")
        self.b_buyut.setToolTip("Büyüt (tam ekran)")
        self.b_buyut.setCursor(Qt.PointingHandCursor)
        self.b_buyut.setFixedSize(30, 28)
        self.b_buyut.setStyleSheet("QToolButton { background: rgba(255,255,255,0.92); border: 1px solid #c9cedb; border-radius: 6px;"
                                   " font-size: 14px; } QToolButton:hover { border-color: #150958; background: #eef1fa; }")
        self.b_buyut.clicked.connect(self.buyut)

    def resim(self, olcek: float = 2.0) -> QImage:
        """Bileşenin içeriğini yüksek çözünürlükte resim olarak çizer."""
        from . import cizim
        w, h = max(1, int(self.width() * olcek)), max(1, int(self.height() * olcek))
        img = QImage(w, h, QImage.Format_ARGB32)
        img.fill(QColor("white"))
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        if self.cizici:
            with cizim.rapor_kipi():
                self.cizici(p, QRectF(0, 0, w, h))
        p.end()
        return img

    # ---------------------------------------------------------------- web
    def update(self, *a):  # noqa: D401  (sayfalar veri değişince update() çağırır)
        super().update(*a)
        self._web_planla()

    def showEvent(self, e):
        super().showEvent(e)
        self._web_planla()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._web is not None:
            self._web.setGeometry(self.rect())
        self.b_buyut.move(self.width() - self.b_buyut.width() - 6, 6)
        self.b_buyut.raise_()

    def buyut(self):
        """Grafiği tam ekran pencerede açar; pencerenin düğmesine ya da Esc'e basınca kapanır."""
        if self._buyuk is not None:                  # büyük penceredeki düğme: küçült
            self._buyuk.close()
            return
        from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QVBoxLayout
        d = QDialog(self.window())
        d.setWindowTitle("Grafik")
        l = QVBoxLayout(d)
        l.setContentsMargins(10, 8, 10, 10)
        ust = QHBoxLayout()
        ust.addStretch(1)
        b = QPushButton("🔍  Küçült")
        b.setObjectName("Ana")
        b.clicked.connect(d.close)
        ust.addWidget(b)
        l.addLayout(ust)
        buyuk = CizimWidget(self.cizici, 300, 300)
        buyuk._buyuk = d                             # büyük kopyadaki büyüteç düğmesi pencereyi kapatır
        buyuk.b_buyut.setToolTip("Küçült")
        l.addWidget(buyuk, 1)
        d.showMaximized()
        buyuk.update()
        d.exec()

    def _web_planla(self):
        from . import web
        if web.WEB_VAR and not self._web_planli:
            self._web_planli = True
            QTimer.singleShot(0, self._web_yenile)

    def _web_yenile(self):
        from . import cizim, web, web_secenek
        self._web_planli = False
        if not self.isVisible() or not self.cizici:
            return
        kayit: list = []
        img = QImage(4, 4, QImage.Format_ARGB32)
        p = QPainter(img)
        cizim._KAYIT = kayit
        try:
            self.cizici(p, QRectF(self.rect()))
        except Exception:  # noqa: BLE001
            kayit = []
        finally:
            cizim._KAYIT = None
            p.end()
        secenek = None
        if kayit:
            ad, prm, _alan = kayit[0]
            try:
                secenek = web_secenek.YAPICILAR[ad](prm)
            except Exception:  # noqa: BLE001  (web karşılığı çizilemezse kendi çizim)
                secenek = None
        self._web_bos = secenek is None
        if secenek is None:
            if self._web_aktif:
                self._web.hide()
                self._web_aktif = False
                super().update()
            return
        if self._web is None:
            self._web = web.WebGorunum(self)
            if hasattr(self, "tiklandi"):
                self._web.tiklandi.connect(lambda a, k: self.tiklandi.emit(a, k))
        self._web.setGeometry(self.rect())
        self._web.show()
        self.b_buyut.raise_()                       # büyüteç web görünümünün üstünde kalsın
        self._web_aktif = True
        self._web.goster(secenek)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QColor("white"))
        if self.cizici and not self._web_aktif:
            self.cizici(p, QRectF(self.rect()))
        p.end()
        if not self._web_bos:
            self._web_planla()


def kart(layout_cls=QVBoxLayout, kenar: int = 14) -> QFrame:
    f = QFrame()
    f.setObjectName("Kart")
    l = layout_cls(f)
    l.setContentsMargins(kenar, kenar, kenar, kenar)
    l.setSpacing(8)
    return f


def etiket(metin: str, ad: str = "", kelime: bool = True) -> QLabel:
    l = QLabel(metin)
    if ad:
        l.setObjectName(ad)
    l.setWordWrap(kelime)
    return l


class SefCombo(QComboBox):
    """Bir vardiyanın grup lideri: listeden seçilir; seçilen tüm günlere uygulanır."""

    def __init__(self, ana, vardiya: int, gunler_fn: Callable[[], List]):
        super().__init__()
        self.ana, self.vardiya, self.gunler_fn = ana, vardiya, gunler_fn
        self._bloke = False
        self.activated.connect(self._secildi)
        self.setMinimumWidth(130)
        self.setToolTip("Bu vardiyanın grup liderini seçin (seçili günlerin hepsine uygulanır)")

    def yenile(self, mevcut: str):
        self._bloke = True
        self.clear()
        adlar = list(self.ana.ayar.get("sefler", []))
        if mevcut and mevcut not in adlar:
            adlar.insert(0, mevcut)       # "A / B" gibi karışık durum
        self.addItems(adlar)
        if mevcut:
            self.setCurrentText(mevcut)
        else:
            self.setCurrentIndex(-1)
        self._bloke = False

    def _secildi(self, _):
        if self._bloke:
            return
        self.ana.sef_ata(self.vardiya, self.currentText(), self.gunler_fn())
