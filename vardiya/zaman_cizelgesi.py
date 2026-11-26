"""Zaman çizelgesi (gank): makine satırları, kayıt blokları. Fare tekerleği yakınlaştırır, sağ tuş / orta tuşla sürükleme
kaydırır, sol tuşla alan seçmek o aralığa yakınlaştırır; Ay / Hafta / Gün / Saat düğmeleri ve ◀ ▶ ile gezilir."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QToolTip, QVBoxLayout, QWidget

from . import tema
from .hesap import CALISIYOR, MOLA

GUNLER = ("Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz")
RENK_CALISMA, RENK_DURUS, RENK_MOLA = "#B7DE9C", "#A7C7EE", "#D3D7E0"
VURGU = "#D64541"                     # seçili ayrıntının kırmızı taralı çerçevesi
SATIR_H = 38.0
EN_KUCUK_SN = 15 * 60


def _sn(t: datetime) -> float:
    return t.timestamp()


class Cizelge(QWidget):
    araligi_degisti = Signal(float, float)

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(160)
        self.setMouseTracking(True)
        self.satirlar: List[str] = []
        self.bloklar: Dict[str, list] = {}          # makine -> [(a, b, tip, statü, operatör, vurgu)]
        self.renk = "#F28C28"
        self.t0 = self.t1 = self.v0 = self.v1 = 0.0
        self.isaret: Optional[Tuple[float, float]] = None   # vurgulu aralık (ör. seçilen gün / vardiya)
        self._surukle = None
        self._secim = None

    # ------------------------------------------------------------ veri
    def ayarla(self, satirlar: List[str], bloklar: Dict[str, list], t0: datetime, t1: datetime, renk: str,
               gorunum: Optional[Tuple[datetime, datetime]] = None, isaret: Optional[Tuple[datetime, datetime]] = None):
        self.satirlar, self.bloklar, self.renk = satirlar, bloklar, renk
        self.t0, self.t1 = _sn(t0), _sn(t1)
        self.v0, self.v1 = (_sn(gorunum[0]), _sn(gorunum[1])) if gorunum else (self.t0, self.t1)
        self.isaret = (_sn(isaret[0]), _sn(isaret[1])) if isaret else None
        self.setMinimumHeight(int(60 + SATIR_H * max(1, len(satirlar))))
        self._yayinla()

    def gorunum(self, v0: float, v1: float):
        w = max(EN_KUCUK_SN, min(v1 - v0, self.t1 - self.t0))
        v0 = min(max(v0, self.t0), self.t1 - w)
        self.v0, self.v1 = v0, v0 + w
        self._yayinla()

    def genislik_ayarla(self, sn: float):
        orta = (self.v0 + self.v1) / 2
        self.gorunum(orta - sn / 2, orta + sn / 2)

    def kaydir(self, oran: float):
        w = self.v1 - self.v0
        self.gorunum(self.v0 + w * oran, self.v1 + w * oran)

    def tumu(self):
        self.gorunum(self.t0, self.t1)

    def _yayinla(self):
        self.update()
        self.araligi_degisti.emit(self.v0, self.v1)

    # ------------------------------------------------------------ geometri
    def _alan(self) -> QRectF:
        return QRectF(90, 30, max(10, self.width() - 100), max(10, self.height() - 44))

    def _x(self, t: float) -> float:
        a = self._alan()
        return a.left() + a.width() * (t - self.v0) / max(1.0, self.v1 - self.v0)

    def _t(self, x: float) -> float:
        a = self._alan()
        return self.v0 + (x - a.left()) / max(1.0, a.width()) * (self.v1 - self.v0)

    # ------------------------------------------------------------ çizim
    def paintEvent(self, _):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QColor("white"))
        a = self._alan()
        if not self.satirlar:
            p.setPen(QColor(tema.YAZI_SOLUK))
            p.drawText(self.rect(), Qt.AlignCenter, "Kayıt yok")
            return
        p.fillRect(QRectF(a.left(), 0, a.width(), a.top() - 2), QColor("#F5F6FA"))      # zaman ekseni bandı
        self._eksen(p, a)
        sh = min(SATIR_H, a.height() / len(self.satirlar))
        f = QFont(tema.FONT_AILESI, 9)
        f.setBold(True)
        cerceve: List[QRectF] = []
        for i, m in enumerate(self.satirlar):
            y = a.top() + i * sh
            if i % 2:
                p.fillRect(QRectF(0, y, self.width(), sh), QColor("#FAFBFD"))
            etk = QRectF(4, y + 6, 80, sh - 12)                                       # makine adı: yuvarlak etiket
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#EEF0FA"))
            p.drawRoundedRect(etk, 6, 6)
            p.setFont(f)
            p.setPen(QColor(tema.LACIVERT))
            p.drawText(etk.adjusted(6, 0, -4, 0), Qt.AlignVCenter | Qt.AlignLeft, m)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#F1F3F8"))
            p.drawRoundedRect(QRectF(a.left(), y + 7, a.width(), sh - 14), 4, 4)
            satir_cerceve: List[List[float]] = []
            for b0, b1, tip, st, op, vurgu in self.bloklar.get(m, []):
                x0, x1 = self._x(_sn(b0)), self._x(_sn(b1))
                if x1 < a.left() or x0 > a.right():
                    continue
                x0, x1 = max(x0, a.left()), min(x1, a.right())
                renk = QColor(self.renk if vurgu else (RENK_CALISMA if st == CALISIYOR else RENK_MOLA if st == MOLA else RENK_DURUS))
                if not vurgu and self.isaret is not None:
                    renk.setAlpha(150)
                r = QRectF(x0, y + 7, max(1.0, x1 - x0), sh - 14)
                p.setBrush(renk)
                if r.width() > 4:
                    p.drawRoundedRect(r, 3, 3)
                else:
                    p.fillRect(r, renk)
                if vurgu:                                                              # yan yana vurgular tek çerçeve olur
                    if satir_cerceve and x0 - satir_cerceve[-1][1] <= 2:
                        satir_cerceve[-1][1] = max(satir_cerceve[-1][1], x1)
                    else:
                        satir_cerceve.append([x0, x1])
            for x0, x1 in satir_cerceve:
                w = max(8.0, x1 - x0)
                cx = (x0 + x1) / 2
                cerceve.append(QRectF(cx - w / 2, y + 3, w, sh - 6))
        for r in cerceve:                                    # kırmızı taralı, yarı saydam: altındaki kayıtlar görünür
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(214, 69, 65, 28))
            p.drawRoundedRect(r, 4, 4)
            p.setBrush(QBrush(QColor(214, 69, 65, 120), Qt.BDiagPattern))
            p.drawRoundedRect(r, 4, 4)
            p.setPen(QPen(QColor(VURGU), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r, 4, 4)
        if self.isaret:
            x0, x1 = self._x(self.isaret[0]), self._x(self.isaret[1])
            p.setPen(QPen(QColor(tema.LACIVERT), 1.5, Qt.DashLine))
            p.setBrush(QColor(21, 9, 88, 14))
            p.drawRoundedRect(QRectF(max(x0, a.left()), a.top(), max(2, min(x1, a.right()) - max(x0, a.left())), len(self.satirlar) * sh), 4, 4)
        if self._secim:
            x0, x1 = sorted(self._secim)
            p.setPen(QPen(QColor(tema.LACIVERT), 1))
            p.setBrush(QColor(21, 9, 88, 40))
            p.drawRect(QRectF(x0, a.top(), x1 - x0, len(self.satirlar) * sh))
        p.end()

    def _eksen(self, p: QPainter, a: QRectF):
        w = self.v1 - self.v0
        adimlar = [(900, "%H:%M"), (1800, "%H:%M"), (3600, "%H:%M"), (7200, "%H:%M"), (14400, "%H:%M"), (28800, "%H:%M"),
                   (86400, "gun"), (2 * 86400, "gun"), (7 * 86400, "gun"), (14 * 86400, "gun")]
        adim, bic = next(((s, b) for s, b in adimlar if w / s <= max(4, a.width() / 90)), (30 * 86400, "gun"))
        bas = datetime.fromtimestamp(self.v0)
        if adim >= 86400:
            t = datetime(bas.year, bas.month, bas.day)
        else:
            t = bas.replace(minute=0, second=0, microsecond=0)
        p.setFont(QFont(tema.FONT_AILESI, 8))
        while _sn(t) <= self.v1:
            x = self._x(_sn(t))
            if x >= a.left() - 1:
                gun_basi = t.hour == 0 and t.minute == 0
                p.setPen(QPen(QColor("#AEB6C6" if gun_basi else "#E3E7EF"), 1))
                p.drawLine(QPointF(x, a.top() - 4), QPointF(x, a.bottom()))
                metin = (f"{GUNLER[t.weekday()]} {t:%d.%m}" if bic == "gun" else
                         (f"{GUNLER[t.weekday()]} {t:%d.%m}" if gun_basi else t.strftime(bic)))
                fk = QFont(tema.FONT_AILESI, 8)
                fk.setBold(gun_basi)
                p.setFont(fk)
                p.setPen(QColor(tema.LACIVERT if gun_basi else tema.YAZI_SOLUK))
                p.drawText(QRectF(x + 4, 4, 140, 20), Qt.AlignLeft | Qt.AlignVCenter, metin)
            t += timedelta(seconds=adim)

    # ------------------------------------------------------------ fare
    def wheelEvent(self, e):  # noqa: N802
        t = self._t(e.position().x())
        k = 0.8 if e.angleDelta().y() > 0 else 1.25
        w = max(EN_KUCUK_SN, (self.v1 - self.v0) * k)
        oran = (t - self.v0) / max(1.0, self.v1 - self.v0)
        self.gorunum(t - w * oran, t + w * (1 - oran))

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() in (Qt.RightButton, Qt.MiddleButton):
            self._surukle = (e.position().x(), self.v0, self.v1)
            self.setCursor(Qt.ClosedHandCursor)
        elif e.button() == Qt.LeftButton:
            self._secim = [e.position().x(), e.position().x()]

    def mouseMoveEvent(self, e):  # noqa: N802
        if self._surukle:
            x0, v0, v1 = self._surukle
            dt = (x0 - e.position().x()) / max(1.0, self._alan().width()) * (v1 - v0)
            self.gorunum(v0 + dt, v1 + dt)
            return
        if self._secim:
            self._secim[1] = e.position().x()
            self.update()
            return
        b = self._blok_bul(e.position())
        if b:
            m, (b0, b1, tip, _st, op, _v) = b
            sure = int((b1 - b0).total_seconds() // 60)
            QToolTip.showText(e.globalPosition().toPoint(), f"<b>{m} · {tip}</b><br>{b0:%d.%m %H:%M} – {b1:%d.%m %H:%M} "
                                                             f"({sure // 60} sa {sure % 60:02d} dk)<br>{op}", self)
        else:
            QToolTip.hideText()

    def mouseReleaseEvent(self, e):  # noqa: N802
        if self._surukle:
            self._surukle = None
            self.setCursor(Qt.ArrowCursor)
            return
        if self._secim:
            x0, x1 = sorted(self._secim)
            self._secim = None
            if x1 - x0 > 6:
                self.gorunum(self._t(x0), self._t(x1))
            else:
                self.update()

    def _blok_bul(self, pt):
        a = self._alan()
        if not self.satirlar or not a.contains(pt):
            return None
        sh = min(SATIR_H, a.height() / len(self.satirlar))
        i = int((pt.y() - a.top()) // sh)
        if not 0 <= i < len(self.satirlar):
            return None
        t = datetime.fromtimestamp(self._t(pt.x()))
        m = self.satirlar[i]
        for blok in self.bloklar.get(m, []):
            if blok[0] <= t < blok[1]:
                return m, blok
        return None


class ZamanCizelgesi(QWidget):
    """Araç çubuğu + çizelge."""

    def __init__(self):
        super().__init__()
        l = QVBoxLayout(self)
        l.setContentsMargins(0, 0, 0, 0)
        ust = QHBoxLayout()
        self.cizelge = Cizelge()
        for ad, sn in (("Ay", 30 * 86400), ("Hafta", 7 * 86400), ("Gün", 86400), ("Saat", 3600)):
            b = QPushButton(ad)
            b.setObjectName("Hizli")
            b.clicked.connect(lambda _=False, s=sn: self.cizelge.genislik_ayarla(s))
            ust.addWidget(b)
        for ad, oran in (("◀", -0.8), ("▶", 0.8)):
            b = QPushButton(ad)
            b.setObjectName("Hizli")
            b.clicked.connect(lambda _=False, o=oran: self.cizelge.kaydir(o))
            ust.addWidget(b)
        b = QPushButton("Tümünü göster")
        b.setObjectName("Hizli")
        b.clicked.connect(self.cizelge.tumu)
        ust.addWidget(b)
        self.aralik = QLabel("")
        self.aralik.setObjectName("KartBaslik")
        ust.addWidget(self.aralik)
        ust.addStretch(1)
        ip = QLabel("tekerlek: yakınlaştır · sol tuşla alan seç: o aralığa yakınlaş · sağ tuşla sürükle: kaydır · bloğun üzerine gelin: ayrıntı")
        ip.setObjectName("AltBaslik")
        ust.addWidget(ip)
        l.addLayout(ust)
        l.addWidget(self.cizelge, 1)
        lej = QLabel("")
        lej.setObjectName("AltBaslik")
        self.lejant = lej
        l.addWidget(lej)
        self.cizelge.araligi_degisti.connect(
            lambda a, b: self.aralik.setText(f"{datetime.fromtimestamp(a):%d.%m.%Y %H:%M} – {datetime.fromtimestamp(b):%d.%m.%Y %H:%M}"))

    def ayarla(self, satirlar, bloklar, t0, t1, renk, tip, gorunum=None, isaret=None):
        self.cizelge.ayarla(satirlar, bloklar, t0, t1, renk, gorunum, isaret)
        self.lejant.setText(f"<span style='color:{renk}'>■</span> {tip} (seçili)  "
                            f"<span style='color:{VURGU}'>▧</span> kırmızı taralı çerçeve: seçili ayrıntı  "
                            f"<span style='color:{RENK_DURUS}'>■</span> diğer duruşlar  "
                            f"<span style='color:{RENK_MOLA}'>■</span> mola  <span style='color:{RENK_CALISMA}'>■</span> çalışma")
        self.lejant.setTextFormat(Qt.RichText)
