"""Personel kartı: görsel dönem özeti (devam halkası, tıklanabilir kutular, bölüme göre çubuklar, gün gün şerit).

Veri personel_veri.kart_ozeti'nden gelir; tarayıcıdaki kart aynı veriyi kullanır.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QToolTip, QWidget

from . import personel_veri as pv

YAZI, SOLUK, ZEMIN = QColor("#1f2433"), QColor("#6b7285"), QColor("#eef0f4")


class OzetGorsel(QWidget):
    kutu_tiklandi = Signal(str)          # "geldi" / "gelmedi" / "izin" (aynısına yeniden tıklanınca "")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.veri: Optional[dict] = None
        self.secili = ""
        self._kutular = []               # (QRectF, anahtar)
        self._kareler = []               # (QRectF, ipucu, gun)
        self.setMouseTracking(True)
        self.setMinimumHeight(300)

    def ayarla(self, veri: Optional[dict], secili: str = ""):
        self.veri, self.secili = veri, secili
        self.update()

    def _yaz(self, p, r, metin, boy, kalin=False, renk=YAZI, hiza=Qt.AlignLeft | Qt.AlignVCenter):
        f = QFont(self.font())
        f.setPixelSize(int(boy))
        f.setBold(kalin)
        p.setFont(f)
        p.setPen(renk)
        p.drawText(r, int(hiza), metin)

    def paintEvent(self, _e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w = self.width()
        self._kutular, self._kareler = [], []
        v = self.veri
        if not v:
            self._yaz(p, QRectF(0, 0, w, 40), "Seçili dönemde kayıt yok", 13, renk=SOLUK)
            return
        # --- devam halkası
        R = 104.0
        hr = QRectF(8, 6, R, R)
        p.setPen(QPen(ZEMIN, 12, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(hr, 0, 360 * 16)
        if v["devam"] is not None:
            p.setPen(QPen(QColor(v["devam_renk"]), 12, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(hr, 90 * 16, -int(360 * 16 * max(0.0, min(1.0, v["devam"]))))
        dv = "-" if v["devam"] is None else f"%{v['devam'] * 100:.0f}" if v["devam"] in (0, 1) else f"%{v['devam'] * 100:.1f}".replace(".", ",")
        self._yaz(p, QRectF(hr.left(), hr.top() + R * 0.28, R, 30), dv, 22, True, QColor("#150958"), Qt.AlignCenter)
        self._yaz(p, QRectF(hr.left(), hr.top() + R * 0.56, R, 18), "devam", 11, False, SOLUK, Qt.AlignCenter)
        # --- kutular (tıklanabilir)
        x0 = hr.right() + 16
        n = len(v["kutular"])
        sutun = n if (w - x0 - 6 * (n - 1)) / n >= 104 else 1    # dar alanda kutular alt alta dizilir
        kg = (w - x0 - 6 * (sutun - 1)) / sutun
        satir_ = (n + sutun - 1) // sutun
        kh = 62.0 if satir_ == 1 else min(50.0, (R + 10 - 6 * (satir_ - 1)) / satir_)
        ky = hr.center().y() - (satir_ * kh + 6 * (satir_ - 1)) / 2
        for i, k in enumerate(v["kutular"]):
            sat_, sut_ = divmod(i, sutun)
            r = QRectF(x0 + sut_ * (kg + 6), ky + sat_ * (kh + 6), kg, kh)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(k["zemin"]))
            p.drawRoundedRect(r, 9, 9)
            p.setBrush(QColor(k["renk"]))
            p.drawRoundedRect(QRectF(r.left(), r.top(), 4, r.height()), 2, 2)
            if self.secili == k["k"]:
                p.setPen(QPen(QColor("#150958"), 2.2))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 9, 9)
            sayi = str(k["deger"])
            renk = QColor(k["renk"]) if (k["k"] == "gelmedi" and k["deger"]) else YAZI
            if satir_ == 1:                                  # yan yana: ad üstte, sayı altta
                self._yaz(p, QRectF(r.left() + 11, r.top() + 6, r.width() - 14, 16), k["ad"], 11, renk=SOLUK)
                self._yaz(p, QRectF(r.left() + 11, r.top() + 23, r.width() - 14, 28), sayi + k["ek"], 20, True, renk)
            else:                                            # alt alta: ad solda, sayı sağda, tek satır
                self._yaz(p, QRectF(r.left() + 11, r.top(), r.width() * 0.5, r.height()), k["ad"], 12, renk=SOLUK)
                self._yaz(p, QRectF(r.left(), r.top(), r.width() - 10, r.height()), sayi + k["ek"], 18, True, renk,
                          Qt.AlignRight | Qt.AlignVCenter)
            self._kutular.append((r, k["k"]))
        # --- çubuklar (bölümde en yüksek değere göre)
        y = hr.bottom() + 14
        etk, sag = 104.0, 112.0
        for c in v["cubuk"]:
            self._yaz(p, QRectF(0, y, etk, 18), c["ad"], 12)
            yol = QRectF(etk + 6, y + 5, w - etk - sag - 12, 8)
            p.setPen(Qt.NoPen)
            p.setBrush(ZEMIN)
            p.drawRoundedRect(yol, 4, 4)
            if c["oran"] > 0:
                p.setBrush(QColor(c["renk"]))
                p.drawRoundedRect(QRectF(yol.left(), yol.top(), max(8.0, yol.width() * c["oran"]), yol.height()), 4, 4)
            self._yaz(p, QRectF(w - sag, y, sag, 18), c["metin"], 12, True, YAZI, Qt.AlignRight | Qt.AlignVCenter)
            y += 22
        self._yaz(p, QRectF(0, y - 2, w, 14), "çubuk boyu: bölümde bu konuda en yüksek değere sahip kişiye göre", 10, renk=SOLUK)
        y += 16
        # --- gün gün şerit
        kare = v["serit"]
        if kare:
            seciliGun = {s["gun"] for s in (v["listeler"].get(self.secili) or [])}
            n = len(kare)
            adim = min(18.0, (w - 2) / max(n, 1))
            kw = max(3.0, adim - 3)
            for i, s in enumerate(kare):
                r = QRectF(1 + i * adim, y, kw, 22)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(s["renk"]))
                p.drawRoundedRect(r, 3, 3)
                if s["gun"] in seciliGun:
                    p.setPen(QPen(QColor("#150958"), 2))
                    p.setBrush(Qt.NoBrush)
                    p.drawRoundedRect(r.adjusted(-1, -1, 1, 1), 3, 3)
                self._kareler.append((r, s["ipucu"], s["gun"]))
            y += 28
            self._yaz(p, QRectF(0, y, 60, 14), "Gün gün:", 10.5, renk=SOLUK)
            x = 58
            turler = {s["tur"] for s in kare}
            for k, ad in pv.SERIT_AD:
                if k not in turler:
                    continue
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(pv.SERIT_RENK[k]))
                p.drawRoundedRect(QRectF(x, y + 2, 10, 10), 2, 2)
                fw = 14 + len(ad) * 6.2
                self._yaz(p, QRectF(x + 13, y, fw, 14), ad, 10.5, renk=SOLUK)
                x += fw + 12
            y += 20
        # --- izin etiketleri
        self._yaz(p, QRectF(0, y, 60, 22), "İzinler:", 12)
        x = 54.0
        if not v["izinler"]:
            self._yaz(p, QRectF(x, y, 80, 22), "yok", 12, renk=SOLUK)
        for iz in v["izinler"]:
            metin = f"{iz['ad']} {iz['gun']} gün"
            fw = 18 + len(metin) * 6.6
            if x + fw > w:
                y += 26
                x = 54.0
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#e7f0fb"))
            p.drawRoundedRect(QRectF(x, y + 1, fw, 20), 10, 10)
            self._yaz(p, QRectF(x, y + 1, fw, 20), metin, 11.5, True, QColor("#1f5fa8"), Qt.AlignCenter)
            x += fw + 6
        y += 26
        if abs(self.minimumHeight() - y) > 2:
            self.setMinimumHeight(int(y))

    def mouseMoveEvent(self, e):  # noqa: N802
        pt = QPointF(e.position())
        for r, ipucu, _g in self._kareler:
            if r.adjusted(-1, -2, 1, 2).contains(pt):
                QToolTip.showText(e.globalPosition().toPoint(), ipucu, self)
                return
        for r, _k in self._kutular:
            if r.contains(pt):
                self.setCursor(Qt.PointingHandCursor)
                QToolTip.showText(e.globalPosition().toPoint(), "tıklayın: bu günleri aşağıda listeler", self)
                return
        self.unsetCursor()
        QToolTip.hideText()

    def mousePressEvent(self, e):  # noqa: N802
        pt = QPointF(e.position())
        for r, k in self._kutular:
            if r.contains(pt):
                self.secili = "" if self.secili == k else k
                self.update()
                self.kutu_tiklandi.emit(self.secili)
                return
