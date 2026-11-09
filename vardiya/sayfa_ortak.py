"""Sayfalarda ortak kullanılan küçük bileşenler."""
from __future__ import annotations

from typing import Callable, List, Optional

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget)


class CizimWidget(QWidget):
    """cizici(p, rect) çağrılabilirini boyar; ekran, pano ve PDF aynı kodu kullanır."""

    def __init__(self, cizici: Optional[Callable] = None, min_h: int = 200, min_w: int = 200):
        super().__init__()
        self.cizici = cizici
        self.setMinimumSize(min_w, min_h)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

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
