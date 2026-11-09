"""Sayfalarda ortak kullanılan küçük bileşenler."""
from __future__ import annotations

from typing import Callable, List, Optional

from PySide6.QtCore import QRectF, QSize, Qt
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
    """cizici(p, rect) çağrılabilirini boyar; ekran, pano ve PDF aynı kodu kullanır."""

    def __init__(self, cizici: Optional[Callable] = None, min_h: int = 200, min_w: int = 200,
                 kopya_resim: Optional[Callable[[], Optional[QImage]]] = None):
        super().__init__()
        self.cizici = cizici
        self.setMinimumSize(min_w, min_h)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        resim_menusu(self, kopya_resim or self.resim)

    def resim(self, olcek: float = 2.0) -> QImage:
        """Bileşenin içeriğini yüksek çözünürlükte resim olarak çizer."""
        w, h = max(1, int(self.width() * olcek)), max(1, int(self.height() * olcek))
        img = QImage(w, h, QImage.Format_ARGB32)
        img.fill(QColor("white"))
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, True)
        if self.cizici:
            self.cizici(p, QRectF(0, 0, w, h))
        p.end()
        return img

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QColor("white"))
        if self.cizici:
            self.cizici(p, QRectF(self.rect()))
        p.end()


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
