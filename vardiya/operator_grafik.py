"""Operatör sütun grafikleri (Performans sayfasındaki makine grafiğiyle aynı görünüm).

Tüm operatörler: her operatör bir sütun, turuncu çizgi hepsinin ortalaması.
Tek operatör: her gün bir sütun, turuncu çizgi o operatörün dönem ortalaması.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen

from . import cizim, tema
from .cizim import AL, ORTA, SAG, _nice_max, _yaz
from .operator import OperatorSonuc

KISA_GUN = ("Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz")


@dataclass(frozen=True)
class Metrik:
    anahtar: str
    ad: str
    yuzde: bool                                         # True: oran, False: saat
    renk: str
    toplu: Callable[[OperatorSonuc], Optional[float]]   # dönem değeri (operatör başına)
    gun: Optional[Callable[[dict], Optional[float]]]    # günlük değer; None: gün gün hesaplanmıyor


def _saat(sn_alani: str):
    return lambda r: getattr(r, sn_alani) / 3600.0


METRIKLER: Tuple[Metrik, ...] = (
    Metrik("calisma", "Çalışma %", True, tema.LACIVERT, lambda r: r.calisma_orani, lambda d: d.get("calisma")),
    Metrik("durus", "Duruş %", True, tema.KIRMIZI, lambda r: r.durus_orani, lambda d: d.get("durus")),
    Metrik("mola", "Mola %", True, "#7B4FA8", lambda r: r.mola_orani, lambda d: d.get("mola")),
    Metrik("bosta", "Boşta kalma (saat)", False, tema.YESIL, _saat("hepsi_calisirken_sn"),
           lambda d: d["bosta_sn"] / 3600.0 if "bosta_sn" in d else None),
    Metrik("bosta_yuzde", "Boşta %", True, "#3E7A1A", lambda r: r.bosta_orani, None),
    Metrik("cakisan", "Çakışan duruş (saat)", False, tema.TURUNCU, _saat("cakisan_sn"),
           lambda d: d["cakisan_sn"] / 3600.0 if "cakisan_sn" in d else None),
    Metrik("ayar", "Ayar kaybı (saat)", False, "#2A7F9E", _saat("setup_kayip_sn"), None),
    Metrik("plansiz", "İş emri yok (saat)", False, "#8A5A2B", _saat("plansiz_sn"), None),
    Metrik("belgesiz", "Belgesiz duruş (saat)", False, "#6B7285", _saat("belgesiz_sn"), None),
)
METRIK = {m.anahtar: m for m in METRIKLER}


def toplu_veri(sonuclar: Dict[str, OperatorSonuc], metrik: Metrik) -> Tuple[List[Tuple[str, float]], Optional[float]]:
    """(operatör, değer) çoktan aza sıralı, ve hepsinin ortalaması."""
    liste = [(ad, v) for ad, r in sonuclar.items() if (v := metrik.toplu(r)) is not None]
    liste.sort(key=lambda x: (-x[1], x[0]))
    return liste, (sum(v for _, v in liste) / len(liste) if liste else None)


def gun_veri(r: OperatorSonuc, metrik: Metrik) -> Optional[Tuple[List[Tuple[date, float]], Optional[float]]]:
    """Tek operatörün gün gün değerleri ve dönem ortalaması; ölçü gün gün hesaplanmıyorsa None."""
    if metrik.gun is None:
        return None
    liste = [(g, v) for g in sorted(r.gunler) if (v := metrik.gun(r.gunler[g])) is not None]
    return liste, (sum(v for _, v in liste) / len(liste) if liste else None)


def _iki_satir(ad: str) -> str:
    if " " in ad:
        i = ad.rfind(" ")
        return ad[:i] + "\n" + ad[i + 1:]
    return ad


def _biçim(yuzde: bool, deger: float, ymax: float = 10.0) -> str:
    if yuzde:
        return f"{deger * 100:.0f}%"
    return f"{int(round(deger * 3600)) // 3600}:{int(round(deger * 3600)) % 3600 // 60:02d}"


def grafik_ciz(p: QPainter, rect: QRectF, baslik: str, secili: List[Metrik], sonuclar: Dict[str, OperatorSonuc],
               operator: Optional[str]):
    """Seçili her ölçü için alt alta bir sütun grafiği çizer."""
    if cizim._web(p, rect, "operator_grafik", locals()):
        return
    s = max(0.85, min(3.0, rect.width() / 900.0))
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    _yaz(p, QRectF(rect.left(), rect.top() + 6 * s, rect.width(), 30 * s), baslik, 19 * s, True, ORTA, tema.LACIVERT)
    if not secili:
        _yaz(p, QRectF(rect.left(), rect.top() + 70 * s, rect.width(), 30 * s),
             "Yukarıdan grafikte görmek istediğiniz ölçüleri işaretleyin.", 14 * s, False, ORTA, tema.YAZI_SOLUK)
        p.restore()
        return
    ust0 = rect.top() + 44 * s
    pay = (rect.bottom() - ust0) / len(secili)
    for i, m in enumerate(secili):
        _panel(p, QRectF(rect.left(), ust0 + i * pay, rect.width(), pay), s, m, sonuclar, operator)
    p.restore()


def _panel(p, rect: QRectF, s: float, m: Metrik, sonuclar, operator: Optional[str]):
    sol, sag, ust, alt = 56 * s, 78 * s, 34 * s, 52 * s
    if operator is None:
        veri, genel = toplu_veri(sonuclar, m)
        etiketler = [_iki_satir(ad) for ad, _ in veri]
        ad_genel = "Genel"
        baslik = f"{m.ad} – operatör bazlı"
    else:
        r = sonuclar.get(operator)
        gv = gun_veri(r, m) if r else None
        if gv is None:
            _yaz(p, rect, f"{m.ad}: bu ölçü gün gün hesaplanmıyor. 'Tüm operatörler' seçilince görünür.", 13 * s, False, ORTA, tema.YAZI_SOLUK)
            return
        liste, genel = gv
        veri = [(g.strftime("%d.%m"), v) for g, v in liste]
        etiketler = [f"{g.strftime('%d.%m')}\n{KISA_GUN[g.weekday()]}" for g, _ in liste]
        ad_genel = "Ort."
        baslik = f"{m.ad} – gün gün"
    _yaz(p, QRectF(rect.left() + sol, rect.top() + 4 * s, rect.width() - sol - sag, 22 * s), baslik, 13 * s, True, AL, tema.LACIVERT)
    alan = QRectF(rect.left() + sol, rect.top() + ust, rect.width() - sol - sag, rect.height() - ust - alt)
    if not veri:
        _yaz(p, alan, "Seçilen dönemde veri yok", 13 * s, False, ORTA, tema.YAZI_SOLUK)
        return
    vmax = max([v for _, v in veri] + [genel or 0.0])
    ymax = 1.1 if (m.yuzde and vmax <= 1.05) else _nice_max(vmax)
    adim = ymax / 5 if ymax > 1.15 or not m.yuzde else 0.1
    k = 0.0
    while k <= ymax + 1e-9:
        y = alan.bottom() - alan.height() * k / ymax
        p.setPen(QPen(QColor("#E3E7EF"), max(1, s)))
        p.drawLine(QPointF(alan.left(), y), QPointF(alan.right(), y))
        yazi = f"{k * 100:.0f}%" if m.yuzde else (f"{k:.0f}" if ymax >= 5 else f"{k:.1f}".replace(".", ","))
        _yaz(p, QRectF(rect.left(), y - 10 * s, sol - 8 * s, 20 * s), yazi, 11 * s, False, SAG, tema.YAZI_SOLUK)
        k += adim
    n = len(veri)
    slot = alan.width() / n
    gen = min(slot * 0.62, 46 * s)
    ana = QColor(m.renk)
    for i, ((_, v), et) in enumerate(zip(veri, etiketler)):
        cx = alan.left() + slot * (i + 0.5)
        h = alan.height() * min(v, ymax) / ymax
        br = QRectF(cx - gen / 2, alan.bottom() - h, gen, h)
        g = QLinearGradient(br.topLeft(), br.bottomLeft())
        g.setColorAt(0, ana.lighter(150))
        g.setColorAt(1, ana)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawRoundedRect(br, 2 * s, 2 * s) if h > 4 * s else p.drawRect(br)
        _yaz(p, QRectF(cx - slot / 2, br.top() - 20 * s, slot, 18 * s), _biçim(m.yuzde, v), 11 * s, True, ORTA, tema.YAZI)
        _yaz(p, QRectF(cx - slot / 2, alan.bottom() + 4 * s, slot, 34 * s), et, (11 if slot > 60 * s else 10) * s, True, ORTA, tema.YAZI)
    p.setPen(QPen(QColor("#9AA3B8"), max(1, s)))
    p.drawLine(alan.bottomLeft(), alan.bottomRight())
    if genel is not None:
        y = alan.bottom() - alan.height() * min(genel, ymax) / ymax
        p.setPen(QPen(QColor(tema.TURUNCU), 2.4 * s))
        p.drawLine(QPointF(alan.left(), y), QPointF(alan.right(), y))
        _yaz(p, QRectF(alan.right() + 4 * s, y - 20 * s, sag - 4 * s, 40 * s), f"{ad_genel}\n{_biçim(m.yuzde, genel)}", 11 * s, True, AL, tema.TURUNCU)
