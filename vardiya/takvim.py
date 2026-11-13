"""Tarih kutuları için takvim: ay ve yıl başlıkta iki açılır listeden seçilir (Qt'nin dar yıl kutusu yerine)."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate
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
