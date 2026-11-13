"""Tarih kutuları için takvim: ay ve yıl başlıkta iki açılır listeden seçilir (Qt'nin dar yıl kutusu yerine)."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QCalendarWidget, QComboBox, QDateEdit, QToolButton, QWidget

AYLAR = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")
ILK_YIL = 2020


class Takvim(QCalendarWidget):
    def __init__(self, ust=None):
        super().__init__(ust)
        self.setGridVisible(False)
        self.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        cubuk = self.findChild(QWidget, "qt_calendar_navigationbar")
        self.ay, self.yil = QComboBox(), QComboBox()
        self.ay.addItems(AYLAR)
        for y in range(ILK_YIL, date.today().year + 2):
            self.yil.addItem(str(y), y)
        stil = "QComboBox { background: white; color: #1d1d4f; font-weight: 600; padding: 2px 8px; min-height: 22px; }"
        for c in (self.ay, self.yil):
            c.setStyleSheet(stil)
            c.setMaxVisibleItems(14)
        self.ay.setMinimumWidth(96)
        self.yil.setMinimumWidth(78)
        if cubuk is not None and cubuk.layout() is not None:
            for ad in ("qt_calendar_monthbutton", "qt_calendar_yearbutton", "qt_calendar_yearedit"):
                w = cubuk.findChild(QWidget, ad)
                if w is not None:
                    w.hide()
                    w.setMaximumWidth(0)
            ly = cubuk.layout()
            onceki = cubuk.findChild(QToolButton, "qt_calendar_prevmonth")
            i = ly.indexOf(onceki) + 1 if onceki is not None else 0
            ly.insertWidget(i, self.ay)
            ly.insertWidget(i + 1, self.yil)
        self.ay.activated.connect(self._sec)
        self.yil.activated.connect(self._sec)
        self.currentPageChanged.connect(self._goster)
        self._goster(self.yearShown(), self.monthShown())

    def _sec(self, *_):
        self.setCurrentPage(int(self.yil.currentData()), self.ay.currentIndex() + 1)

    def _goster(self, yil: int, ay: int):
        i = self.yil.findData(yil)
        if i < 0:
            self.yil.addItem(str(yil), yil)
            i = self.yil.count() - 1
        self.yil.setCurrentIndex(i)
        self.ay.setCurrentIndex(ay - 1)


class TarihKutusu(QDateEdit):
    """Takvimi açılır ay/yıl listeli tarih kutusu."""
    def __init__(self, *a):
        super().__init__(*a)
        self.setCalendarPopup(True)
        self.setCalendarWidget(Takvim(self))
        if not a:
            self.setDate(QDate.currentDate())


class AralikSecici(QWidget):
    """Tek takvimden tarih aralığı: ilk tıklama başlangıç, ikinci tıklama bitiş. Seçim bitince bir kez 'secildi' yayar.
    Böylece başlangıç değişir değişmez (bitiş seçilmeden) hesap başlamaz."""
    from PySide6.QtCore import Signal as _Signal
    secildi = _Signal(object, object)            # (ilk: date, son: date)

    def __init__(self, ust=None):
        from PySide6.QtWidgets import QHBoxLayout, QPushButton
        super().__init__(ust)
        self._ilk = self._son = date.today()
        self._bekleyen = None
        l = QHBoxLayout(self)
        l.setContentsMargins(0, 0, 0, 0)
        self.dugme = QPushButton()
        self.dugme.setMinimumWidth(230)
        self.dugme.setCursor(Qt.PointingHandCursor)
        self.dugme.setToolTip("Tıklayın: takvimde önce başlangıç, sonra bitiş gününe tıklayın")
        self.dugme.setStyleSheet("QPushButton { text-align: left; padding: 5px 12px; background: white; border: 1px solid #c9cedb;"
                                 " border-radius: 6px; color: #1b1e2b; } QPushButton:hover { border-color: #150958; }")
        self.dugme.clicked.connect(self._ac)
        l.addWidget(self.dugme)
        self._yaz()

    def aralik(self):
        return self._ilk, self._son

    def goster(self, ilk: date, son: date):
        """Dışarıdan aralığı gösterir (sinyal yaymaz)."""
        self._ilk, self._son = ilk, son
        self._yaz()

    def _yaz(self):
        self.dugme.setText(f"📅  {self._ilk:%d.%m.%Y}  –  {self._son:%d.%m.%Y}")

    def _ac(self):
        from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout
        self._bekleyen = None
        p = QFrame(self, Qt.Popup)
        p.setStyleSheet("QFrame { background: white; border: 1px solid #c9cedb; border-radius: 8px; }")
        d = QVBoxLayout(p)
        d.setContentsMargins(10, 8, 10, 10)
        self._ipucu = QLabel("Başlangıç gününe tıklayın")
        self._ipucu.setStyleSheet("border: 0; color: #150958; font-weight: 700; font-size: 13px;")
        d.addWidget(self._ipucu)
        self._takvim = Takvim(p)
        self._takvim.setMinimumSize(320, 250)
        self._takvim.setSelectedDate(QDate(self._ilk.year, self._ilk.month, self._ilk.day))
        self._takvim.clicked.connect(self._tik)
        d.addWidget(self._takvim)
        self._boya(self._ilk, self._son)
        self._pencere = p
        p.move(self.dugme.mapToGlobal(self.dugme.rect().bottomLeft()))
        p.show()

    def _boya(self, ilk: Optional[date], son: Optional[date]):
        from PySide6.QtGui import QColor, QTextCharFormat
        t = self._takvim
        t.setDateTextFormat(QDate(), QTextCharFormat())          # önceki boyamayı temizle
        if ilk is None:
            return
        son = son or ilk
        f = QTextCharFormat()
        f.setBackground(QColor("#dfe7f7"))
        uc = QTextCharFormat()
        uc.setBackground(QColor("#150958"))
        uc.setForeground(QColor("white"))
        g = ilk
        while g <= son and (son - ilk).days <= 800:
            t.setDateTextFormat(QDate(g.year, g.month, g.day), uc if g in (ilk, son) else f)
            g += timedelta(days=1)

    def _tik(self, q: QDate):
        g = date(q.year(), q.month(), q.day())
        if self._bekleyen is None:
            self._bekleyen = g
            self._boya(g, g)
            self._ipucu.setText(f"Başlangıç {g:%d.%m.%Y} · şimdi bitiş gününe tıklayın")
            return
        ilk, son = sorted((self._bekleyen, g))
        self._bekleyen = None
        self._ilk, self._son = ilk, son
        self._yaz()
        self._pencere.close()
        self.secildi.emit(ilk, son)
