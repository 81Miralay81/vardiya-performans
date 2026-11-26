"""Bekleme göstergesi: uzun süren her işte pencerenin ortasında küçük, modern bir kart çıkar.

Ne yapıldığı (başlık), neden beklendiği (ayrıntı) ve geçen süre yazar; dönen halka işin sürdüğünü gösterir.
- arka_planda(...): iş ayrı iş parçacığında (kendi okuma bağlantısıyla) yapılır; pencere donmaz, halka döner.
- bekle(...): kısa ve ekran iş parçacığında yapılması gereken işler için (kart iş başlamadan çizilir).
Çok kısa işlerde (≈0,25 sn) kart hiç görünmez; göz kırpması olmasın.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QApplication, QFrame, QGraphicsDropShadowEffect, QWidget

from . import tema

GECIKME_MS = 250


class _Kart(QFrame):
    def __init__(self, ust: QWidget):
        super().__init__(ust)
        self.setObjectName("BeklemeKarti")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setFixedSize(440, 104)
        self.setStyleSheet("QFrame#BeklemeKarti { background: white; border: 1px solid #dfe3ee; border-radius: 14px; }")
        g = QGraphicsDropShadowEffect(self)
        g.setBlurRadius(28)
        g.setOffset(0, 6)
        g.setColor(QColor(21, 9, 88, 60))
        self.setGraphicsEffect(g)
        self.baslik, self.ayrinti = "", ""
        self._t0 = time.monotonic()
        self._aci = 0
        self._zaman = QTimer(self)
        self._zaman.timeout.connect(self._tik)
        self.hide()

    def basla(self, baslik: str, ayrinti: str):
        self.baslik, self.ayrinti = baslik, ayrinti
        self._t0 = time.monotonic()
        self._yerlestir()
        self.show()
        self.raise_()
        self._zaman.start(33)
        self.repaint()

    def dur(self):
        self._zaman.stop()
        self.hide()

    def _yerlestir(self):
        p = self.parentWidget()
        if p is not None:
            self.move((p.width() - self.width()) // 2, max(20, int(p.height() * 0.38) - self.height() // 2))

    def _tik(self):
        self._aci = (self._aci + 12) % 360
        self._yerlestir()
        self.update()

    def paintEvent(self, e):  # noqa: N802
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(22, 26, 44, 44)
        p.setPen(QPen(QColor("#E6E9F4"), 5))
        p.drawEllipse(r)
        p.setPen(QPen(QColor(tema.YESIL), 5, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(r, int(-self._aci * 16), 100 * 16)
        f = QFont(tema.FONT_AILESI, 11)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(tema.LACIVERT))
        p.drawText(QRectF(84, 16, self.width() - 100, 24), Qt.AlignLeft | Qt.AlignVCenter, self.baslik)
        f = QFont(tema.FONT_AILESI, 9)
        p.setFont(f)
        p.setPen(QColor("#6b7285"))
        gecen = int(time.monotonic() - self._t0)
        alt = (self.ayrinti + "\n" if self.ayrinti else "") + f"geçen süre: {gecen} sn · lütfen bekleyin"
        p.drawText(QRectF(84, 42, self.width() - 100, 40), Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, alt)
        p.end()


def _kart(widget: QWidget) -> Optional[_Kart]:
    w = widget.window() if widget is not None else None
    if w is None:
        return None
    k = getattr(w, "_bekleme_karti", None)
    if k is None:
        k = _Kart(w)
        w._bekleme_karti = k
        w._bekleme_sayac = 0
    return k


class Bekleme:
    """Tek bir bekleme: başlat → bitir. Aynı pencerede iç içe beklemeler tek kartta gösterilir."""

    def __init__(self, widget: QWidget, baslik: str, ayrinti: str = "", gecikme_ms: int = GECIKME_MS):
        self._k = _kart(widget)
        self._bitti = False
        self._baslik, self._ayrinti = baslik, ayrinti
        if self._k is None:
            return
        w = self._k.parentWidget()
        w._bekleme_sayac = getattr(w, "_bekleme_sayac", 0) + 1
        if gecikme_ms <= 0:
            self._goster()
        else:
            QTimer.singleShot(gecikme_ms, self._goster)

    def _goster(self):
        if not self._bitti and self._k is not None:
            self._k.basla(self._baslik, self._ayrinti)

    def bitir(self):
        if self._bitti or self._k is None:
            return
        self._bitti = True
        w = self._k.parentWidget()
        w._bekleme_sayac = max(0, getattr(w, "_bekleme_sayac", 1) - 1)
        if w._bekleme_sayac == 0:
            self._k.dur()


@contextmanager
def bekle(widget: QWidget, baslik: str, ayrinti: str = ""):
    """Ekran iş parçacığında yapılan iş: kart hemen çizilir, iş bitince kapanır."""
    b = Bekleme(widget, baslik, ayrinti, gecikme_ms=0)
    QApplication.processEvents()
    QApplication.setOverrideCursor(Qt.WaitCursor)
    try:
        yield b
    finally:
        QApplication.restoreOverrideCursor()
        b.bitir()


class _Is(QThread):
    bitti = Signal(object)

    def __init__(self, db_yolu: Optional[str], fn: Callable, parent=None):
        super().__init__(parent)
        self.db_yolu, self.fn = db_yolu, fn

    def run(self):
        try:
            if self.db_yolu:
                from . import veritabani as vt
                con, kilit = vt.okuma_baglantisi(self.db_yolu)
                with kilit:
                    sonuc = self.fn(con)
            else:
                sonuc = self.fn(None)
        except Exception as e:  # noqa: BLE001
            sonuc = e
        self.bitti.emit(sonuc)


class _Tasiyici(QObject):
    """Çalışan işleri çöpe gitmesin diye tutar."""
    isler: list = []


def arka_planda(widget: QWidget, db_yolu: Optional[str], baslik: str, ayrinti: str, fn: Callable[[Any], Any],
                bitince: Callable[[Any], None]) -> _Is:
    """fn(con) ayrı iş parçacığında (sürekli açık okuma bağlantısıyla) çalışır; bitince bitince(sonuç ya da Exception)
    ekran iş parçacığında çağrılır. Bu sırada pencere donmaz, bekleme kartı görünür."""
    b = Bekleme(widget, baslik, ayrinti)
    is_ = _Is(db_yolu, fn)
    _Tasiyici.isler.append(is_)

    def _son(sonuc):
        b.bitir()
        try:
            bitince(sonuc)
        finally:
            if is_ in _Tasiyici.isler:
                _Tasiyici.isler.remove(is_)
    is_.bitti.connect(_son)
    is_.finished.connect(is_.deleteLater)
    is_.start()
    return is_


def kaydir(sc, widget: QWidget, pay: int = 30, sure_ms: int = 380):
    """Kaydırma alanını yeni açılan bölüme yumuşakça kaydırır (birden zıplamaz)."""
    from PySide6.QtCore import QEasingCurve, QPropertyAnimation
    if sc is None or widget is None:
        return
    QApplication.processEvents()
    bar = sc.verticalScrollBar()
    try:
        y = widget.mapTo(sc.widget(), widget.rect().topLeft()).y() - pay
    except Exception:  # noqa: BLE001
        sc.ensureWidgetVisible(widget, 0, pay)
        return
    hedef = max(bar.minimum(), min(bar.maximum(), y))
    if abs(hedef - bar.value()) < 4:
        return
    a = QPropertyAnimation(bar, b"value", sc)
    a.setDuration(sure_ms)
    a.setStartValue(bar.value())
    a.setEndValue(hedef)
    a.setEasingCurve(QEasingCurve.OutCubic)
    a.start(QPropertyAnimation.DeleteWhenStopped)
