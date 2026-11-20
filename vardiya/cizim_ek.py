"""Ayrıntı pencerelerinin çizimleri (QPainter): kırılım sütunları, makine bazlı yığılmış sütunlar, boşta/çakışan sütunları,
çakışma ve şüpheli mola zaman çizelgeleri. bolgeler listesi verilirse tıklanabilir alanlar (QRectF, anahtar, kısım) eklenir."""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import List, Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen

from . import tema
from .cizim import AL, ORTA, SAG, _iki_satir, _saat_dk, _web, _yaz, olcek

YESIL_, KIRMIZI_, TURUNCU_, GRI_ = "#5E9B2A", "#D64541", "#F28C28", "#B0B4C0"
DURUM_RENK = {"Çalışıyor": YESIL_, "Duruş": KIRMIZI_, "Mola": TURUNCU_}


def _sutun(p, r: QRectF, renk: str, s: float, yuvarlak: bool = True):
    ana = QColor(renk)
    g = QLinearGradient(r.topLeft(), r.topRight())
    g.setColorAt(0, ana.lighter(118))
    g.setColorAt(0.55, ana)
    g.setColorAt(1, ana.darker(110))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(g))
    if yuvarlak and r.height() > 6 * s:
        p.drawRoundedRect(r, 3 * s, 3 * s)
    else:
        p.drawRect(r)


def etiket_iki_satir(ad: str) -> str:
    """Kişi adı gibi etiketleri ilk boşluktan ikiye böler (yan yana sütunlarda adlar üst üste binmesin)."""
    return ad.replace(" ", "\n", 1) if len(ad) > 9 and " " in ad else ad


def kirilim_grafigi(p: QPainter, rect: QRectF, liste: List[tuple], baslik: Optional[str] = None):
    """liste: [(ad, saat, renk)]. Üstte süre ve toplam içindeki payı (Performans 3. kırılım)."""
    if _web(p, rect, "kirilim_grafigi", locals()):
        return
    s = olcek(rect, 520, 340)
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    if baslik:
        _yaz(p, QRectF(rect.left(), rect.top() + 2 * s, rect.width(), 24 * s), baslik, 14 * s, True, ORTA, tema.LACIVERT)
    toplam = sum(x[1] for x in liste) or 0.0
    if not liste or toplam <= 0:
        _yaz(p, rect, "Kayıt yok", 14 * s, False, ORTA, tema.YAZI_SOLUK)
        p.restore()
        return
    sol, sag, ust, alt = 52 * s, 14 * s, (64 if baslik else 40) * s, 44 * s
    alan = QRectF(rect.left() + sol, rect.top() + ust, rect.width() - sol - sag, rect.height() - ust - alt)
    ymax = max(0.5, math.ceil(max(x[1] for x in liste) * 1.08 * 2) / 2)
    for i in range(5):
        y = alan.bottom() - alan.height() * i / 4
        p.setPen(QPen(QColor("#E3E7EF"), max(1, s)))
        p.drawLine(QPointF(alan.left(), y), QPointF(alan.right(), y))
        k = ymax * i / 4
        _yaz(p, QRectF(rect.left(), y - 9 * s, sol - 6 * s, 18 * s), (f"{k:.1f}".replace(".", ",") if ymax < 8 else f"{k:.0f}") + " sa",
             10 * s, False, SAG, tema.YAZI_SOLUK)
    slot = alan.width() / len(liste)
    gen = min(slot * 0.58, 70 * s)
    for i, (ad, saat, renk) in enumerate(liste):
        cx = alan.left() + slot * (i + 0.5)
        h = max(2.0, alan.height() * saat / ymax)
        _sutun(p, QRectF(cx - gen / 2, alan.bottom() - h, gen, h), renk, s)
        _yaz(p, QRectF(cx - slot / 2, alan.bottom() - h - 32 * s, slot, 30 * s), f"{_saat_dk(saat)} sa\n%{saat / toplam * 100:.0f}",
             10.5 * s, True, ORTA, tema.YAZI)
        _yaz(p, QRectF(cx - slot / 2, alan.bottom() + 3 * s, slot, 34 * s), etiket_iki_satir(ad), (10.5 if slot > 80 * s else 9.5) * s,
             True, ORTA, tema.YAZI)
    p.setPen(QPen(QColor("#9AA3B8"), max(1, s)))
    p.drawLine(alan.bottomLeft(), alan.bottomRight())
    p.restore()


def yigin_grafigi(p: QPainter, rect: QRectF, liste: List[tuple], baslik: Optional[str] = None, alt_baslik: str = "",
                  bolgeler: Optional[list] = None, secili: Optional[str] = None):
    """liste: [(anahtar, etiket, çalışma 0-1, duruş 0-1, bilgi)]. Her sütun %100: altta yeşil çalışma, üstte kırmızı duruş."""
    s = olcek(rect, 900, 380)
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    if baslik:
        _yaz(p, QRectF(rect.left(), rect.top() + 2 * s, rect.width(), 26 * s), baslik, 16 * s, True, ORTA, tema.LACIVERT)
    if alt_baslik:
        _yaz(p, QRectF(rect.left() + 56 * s, rect.top() + 30 * s, rect.width(), 18 * s), alt_baslik, 11 * s, False, AL, tema.YAZI_SOLUK)
    if not liste:
        _yaz(p, rect, "Kayıt yok", 14 * s, False, ORTA, tema.YAZI_SOLUK)
        p.restore()
        return
    sol, sag, ust, alt = 56 * s, 16 * s, 70 * s, 40 * s
    alan = QRectF(rect.left() + sol, rect.top() + ust, rect.width() - sol - sag, rect.height() - ust - alt)
    for k in range(0, 101, 25):
        y = alan.bottom() - alan.height() * k / 100
        p.setPen(QPen(QColor("#E3E7EF"), max(1, s)))
        p.drawLine(QPointF(alan.left(), y), QPointF(alan.right(), y))
        _yaz(p, QRectF(rect.left(), y - 9 * s, sol - 6 * s, 18 * s), f"%{k}", 10 * s, False, SAG, tema.YAZI_SOLUK)
    # gösterge
    gx = alan.right()
    for ad, renk in (("Duruş", KIRMIZI_), ("Çalışma", YESIL_)):
        p.setFont(tema.font(10.5 * s))
        w = p.fontMetrics().horizontalAdvance(ad) + 24 * s
        gx -= w
        p.fillRect(QRectF(gx, rect.top() + 34 * s, 11 * s, 10 * s), QColor(renk))
        _yaz(p, QRectF(gx + 15 * s, rect.top() + 30 * s, w, 18 * s), ad, 10.5 * s, False, AL, tema.YAZI)
    slot = alan.width() / len(liste)
    gen = min(slot * 0.6, 80 * s)
    for i, (anahtar, etiket, c, d, _bilgi) in enumerate(liste):
        cx = alan.left() + slot * (i + 0.5)
        top = (c + d) or 1.0
        cp, dp = c / top, d / top
        yc = alan.bottom() - alan.height() * cp
        if anahtar == secili:
            p.fillRect(QRectF(cx - slot / 2, alan.top(), slot, alan.height()), QColor(36, 26, 140, 22))
        r1 = QRectF(cx - gen / 2, yc, gen, alan.bottom() - yc)
        r2 = QRectF(cx - gen / 2, alan.top(), gen, yc - alan.top())
        if r1.height() > 0.5:
            _sutun(p, r1, YESIL_, s, False)
        if r2.height() > 0.5:
            _sutun(p, r2, KIRMIZI_, s, False)
        if r1.height() >= 14 * s:
            _yaz(p, r1, f"%{cp * 100:.0f}", 11 * s, True, ORTA, "#FFFFFF")
        if r2.height() >= 14 * s:
            _yaz(p, r2, f"%{dp * 100:.0f}", 10 * s, True, ORTA, "#FFFFFF")
        _yaz(p, QRectF(cx - slot / 2, alan.bottom() + 4 * s, slot, 32 * s), etiket, (11 if slot > 50 * s else 9.5) * s, True, ORTA, tema.YAZI)
        if bolgeler is not None:
            bolgeler.append((QRectF(cx - slot / 2, alan.top(), slot, alan.height() + 34 * s), anahtar, "makine"))
    p.setPen(QPen(QColor("#9AA3B8"), max(1, s)))
    p.drawLine(alan.bottomLeft(), alan.bottomRight())
    p.restore()


def bosta_cakisan_grafigi(p: QPainter, rect: QRectF, gunler: List[tuple], baslik: str = "Boşta kaldığı ve çakışan duruş süresi (saat)",
                          bolgeler: Optional[list] = None):
    """gunler: [(gün, etiket, boşta saat, çakışan saat)]. Çakışan sütununa tıklanınca o günün çakışma penceresi açılır."""
    s = olcek(rect, 900, 300)
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    _yaz(p, QRectF(rect.left() + 56 * s, rect.top() + 4 * s, rect.width(), 20 * s), baslik, 12 * s, True, AL, tema.LACIVERT)
    _yaz(p, QRectF(rect.left() + 56 * s, rect.top() + 22 * s, rect.width(), 16 * s),
         "turuncu sütuna (çakışan duruş) tıklayın: o günün çakışan duruşları", 10 * s, False, AL, tema.YAZI_SOLUK)
    if not gunler:
        p.restore()
        return
    sol, sag, ust, alt = 56 * s, 16 * s, 58 * s, 30 * s
    alan = QRectF(rect.left() + sol, rect.top() + ust, rect.width() - sol - sag, rect.height() - ust - alt)
    en = max([g[2] for g in gunler] + [g[3] for g in gunler] + [1.0])
    tepe = float(-(-en // 2) * 2)
    for i in range(5):
        y = alan.bottom() - alan.height() * i / 4
        p.setPen(QPen(QColor("#E3E7EF"), max(1, s)))
        p.drawLine(QPointF(alan.left(), y), QPointF(alan.right(), y))
        _yaz(p, QRectF(rect.left(), y - 9 * s, sol - 6 * s, 18 * s), f"{tepe * i / 4:.1f}".replace(".", ","), 10 * s, False, SAG, tema.YAZI_SOLUK)
    gx = alan.right()
    for ad, renk in (("Çakışan duruş", TURUNCU_), ("Boşta", YESIL_)):
        p.setFont(tema.font(10.5 * s))
        w = p.fontMetrics().horizontalAdvance(ad) + 24 * s
        gx -= w
        p.fillRect(QRectF(gx, rect.top() + 8 * s, 11 * s, 10 * s), QColor(renk))
        _yaz(p, QRectF(gx + 15 * s, rect.top() + 4 * s, w, 18 * s), ad, 10.5 * s, False, AL, tema.YAZI)
    slot = alan.width() / len(gunler)
    gen = min(slot * 0.34, 60 * s)
    for i, (gun, etiket, bosta, cak) in enumerate(gunler):
        cx = alan.left() + slot * (i + 0.5)
        for j, (deger, renk) in enumerate(((bosta, YESIL_), (cak, TURUNCU_))):
            h = alan.height() * min(1.0, deger / tepe) if tepe else 0
            r = QRectF(cx - gen - 2 * s + j * (gen + 4 * s), alan.bottom() - h, gen, h)
            if h > 0.5:
                _sutun(p, r, renk, s)
            _yaz(p, QRectF(r.left() - 12 * s, alan.bottom() - h - 17 * s, gen + 24 * s, 15 * s), f"{deger:.1f}".replace(".", ","),
                 10 * s, True, ORTA, tema.YAZI)
            if j == 1 and bolgeler is not None and cak > 0:
                bolgeler.append((QRectF(r.left() - 4 * s, alan.top(), gen + 8 * s, alan.height()), gun, "cakisma"))
        _yaz(p, QRectF(cx - slot / 2, alan.bottom() + 4 * s, slot, 18 * s), etiket, 10 * s, False, ORTA, tema.YAZI)
    p.setPen(QPen(QColor("#9AA3B8"), max(1, s)))
    p.drawLine(alan.bottomLeft(), alan.bottomRight())
    p.restore()


def _zaman_ekseni(p, x0: float, x1: float, y: float, t0: datetime, t1: datetime, s: float, adim_dk: int):
    toplam = (t1 - t0).total_seconds() or 1.0
    t = t0.replace(second=0, microsecond=0)
    t += timedelta(minutes=(-t.minute) % adim_dk)
    while t <= t1:
        x = x0 + (x1 - x0) * (t - t0).total_seconds() / toplam
        p.setPen(QPen(QColor("#E3E7EF"), max(1, s)))
        p.drawLine(QPointF(x, y - 4 * s), QPointF(x, y))
        _yaz(p, QRectF(x - 24 * s, y + 1 * s, 48 * s, 14 * s), f"{t:%H:%M}", 9.5 * s, False, ORTA, tema.YAZI_SOLUK)
        t += timedelta(minutes=adim_dk)


def _tarali(p, r: QRectF, renk: str, s: float):
    p.save()
    p.setClipRect(r)
    p.setPen(QPen(QColor(renk), max(1, 1.3 * s)))
    k = -r.height()
    while k < r.width():
        p.drawLine(QPointF(r.left() + k, r.bottom()), QPointF(r.left() + k + r.height(), r.top()))
        k += 6 * s
    p.restore()
    p.setPen(QPen(QColor(renk), max(1, 1.4 * s)))
    p.setBrush(Qt.NoBrush)
    p.drawRect(r)


def cakisma_cizelgesi(p: QPainter, rect: QRectF, makineler: List[str], bloklar: dict, cakismalar: List[tuple],
                      t0: datetime, t1: datetime, vurgu: Optional[str] = None):
    """Bir günün çakışmaları. bloklar: makine -> [(baş, bit, durum, tür)]; cakismalar: [(no, baş, bit)].
    Her makine bir satır: açık yeşil zemin çalışma, renkli blok duruş (adıyla), kırmızı tarama çakışan aralık."""
    s = olcek(rect, 1100, 120 + 60 * max(1, len(makineler)))
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    sol, sag, ust, alt = 90 * s, 16 * s, 34 * s, 26 * s
    x0, x1 = rect.left() + sol, rect.right() - sag
    toplam = (t1 - t0).total_seconds() or 1.0

    def xx(t):
        return x0 + (x1 - x0) * max(0.0, min(1.0, (t - t0).total_seconds() / toplam))
    n = max(1, len(makineler))
    sh = (rect.height() - ust - alt) / n
    son_x = -1e9
    for no, a, b in cakismalar:                         # çakışma sütunları (arkada); numara yer varsa yazılır
        if b <= t0 or a >= t1:
            continue
        r = QRectF(xx(a), rect.top() + ust - 6 * s, max(1.5, xx(b) - xx(a)), sh * n + 6 * s)
        p.fillRect(r, QColor(192, 57, 43, 70 if no == vurgu else 30))
        if no == vurgu:
            p.setPen(QPen(QColor("#C0392B"), max(1, 2 * s)))
            p.setBrush(Qt.NoBrush)
            p.drawRect(r)
        cx = (xx(a) + xx(b)) / 2
        if cx - son_x >= 22 * s or no == vurgu:
            _yaz(p, QRectF(cx - 20 * s, rect.top() + 6 * s, 40 * s, 20 * s), f"{no}", 13 * s, True, ORTA, "#C0392B")
            son_x = cx
    for i, m in enumerate(makineler):
        y = rect.top() + ust + i * sh
        sat = QRectF(x0, y + sh * 0.2, x1 - x0, sh * 0.6)
        _yaz(p, QRectF(rect.left(), y, sol - 10 * s, sh), m, 13 * s, True, SAG, tema.YAZI)
        p.fillRect(sat, QColor("#EEF0F5"))
        for a, b, durum, tur in bloklar.get(m, []):
            if b <= t0 or a >= t1:
                continue
            r = QRectF(xx(a), sat.top(), max(1.0, xx(b) - xx(a)), sat.height())
            if durum == "Çalışıyor":
                p.fillRect(r, QColor("#D6EBC6"))
            elif durum == "Mola":
                p.fillRect(r, QColor("#FBD3A8"))
            else:
                p.fillRect(r, QColor(tema.durus_rengi(tur)))
                p.setFont(tema.font(9.5 * s, True))
                ad = tur
                fm = p.fontMetrics()
                if fm.horizontalAdvance(ad) > r.width() - 4 * s:
                    ad = fm.elidedText(ad, Qt.ElideRight, int(r.width() - 4 * s))
                if r.width() > 18 * s:
                    _yaz(p, r, ad, 9.5 * s, True, ORTA, "#FFFFFF")
        for _no, a, b in cakismalar:
            for c0, c1, durum, _t in bloklar.get(m, []):
                if durum == "Duruş" and c0 < b and a < c1:
                    _tarali(p, QRectF(xx(max(a, c0)), sat.top(), max(1.5, xx(min(b, c1)) - xx(max(a, c0))), sat.height()), "#C0392B", s)
    adim = 60 if toplam > 6 * 3600 else 30 if toplam > 2 * 3600 else 10 if toplam > 3600 else 5 if toplam > 1200 else 1
    _zaman_ekseni(p, x0, x1, rect.bottom() - alt + 6 * s, t0, t1, s, adim)
    p.restore()


def supheli_cizelgesi(p: QPainter, rect: QRectF, olaylar: list):
    """Şüpheli molalar: her olay bir satır; mola saatinin 30 dk öncesi ve sonrası. Kesik çerçeve mola saati,
    turuncu mola, yeşil çalışma, kırmızı duruş; mola saati içinde başlayan çalışma kırmızı taralı."""
    s = olcek(rect, 1100, 110 * max(1, len(olaylar)))
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    if not olaylar:
        _yaz(p, rect, "Bu vardiyada şüpheli mola yok", 14 * s, False, ORTA, tema.YAZI_SOLUK)
        p.restore()
        return
    sol, sag = 200 * s, 16 * s
    sh = rect.height() / len(olaylar)
    x0, x1 = rect.left() + sol, rect.right() - sag
    for i, e in enumerate(olaylar):
        y = rect.top() + i * sh
        t0, t1 = e.pb - timedelta(minutes=30), e.ps + timedelta(minutes=30)
        toplam = (t1 - t0).total_seconds()

        def xx(t, _t0=t0, _top=toplam):
            return x0 + (x1 - x0) * max(0.0, min(1.0, (t - _t0).total_seconds() / _top))
        sat = QRectF(x0, y + sh * 0.30, x1 - x0, sh * 0.38)
        _yaz(p, QRectF(rect.left(), y + sh * 0.22, sol - 12 * s, sh * 0.5),
             f"{e.makine} · {e.vardiya}. V · {e.operator}\n{e.gun:%d.%m.%Y} {e.tur.lower()} molası", 11 * s, True, SAG, tema.YAZI)
        p.fillRect(QRectF(xx(e.pb), y + sh * 0.18, xx(e.ps) - xx(e.pb), sh * 0.62), QColor("#EEF0F7"))
        p.fillRect(sat, QColor("#F4F5F8"))
        for a, b, durum, tur in e.bloklar:
            r = QRectF(xx(a), sat.top(), max(1.0, xx(b) - xx(a)), sat.height())
            p.fillRect(r, QColor(DURUM_RENK.get(durum, KIRMIZI_)))
            if r.width() > 46 * s:
                dk = (b - a).total_seconds() / 60
                ad = "Çalışma" if durum == "Çalışıyor" else ("Mola" if durum == "Mola" else tur)
                p.setFont(tema.font(9.5 * s, True))
                ad = p.fontMetrics().elidedText(ad, Qt.ElideRight, int(r.width() - 4 * s))
                _yaz(p, r, f"{ad}\n{dk:.0f} dk", 9.5 * s, True, ORTA, "#FFFFFF")
        sr = QRectF(xx(max(e.cb, e.pb)), sat.top(), max(1.5, xx(min(e.cs, e.ps)) - xx(max(e.cb, e.pb))), sat.height())
        _tarali(p, sr, "#C0392B", s)
        _yaz(p, QRectF(sr.left() - 140 * s, y + sh * 0.02, sr.width() + 280 * s, sh * 0.18),
             f"⚠ mola saatinde çalışma {e.sn / 60:.0f} dk", 10.5 * s, True, ORTA, "#C0392B")
        p.setPen(QPen(QColor(tema.LACIVERT), max(1, 1.5 * s), Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(xx(e.pb), y + sh * 0.20, xx(e.ps) - xx(e.pb), sh * 0.58))
        _zaman_ekseni(p, x0, x1, y + sh * 0.84, t0, t1, s, 10)
    p.restore()
