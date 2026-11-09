"""Operatör mum grafiği: gün gün, vardiyalar arası değişim.

Her gün bir mumdur:
  açılış  = o gün operatörün çalıştığı İLK vardiyadaki değer
  kapanış = o gün operatörün çalıştığı SON vardiyadaki değer
  fitil   = o günün en düşük / en yüksek değeri (vardiya bazında)
Toplu görünümde (tüm operatörler) açılış ve kapanış operatörlerin o vardiyadaki ortalamasıdır;
fitil ise o gün tek bir operatörün o vardiyada gördüğü en düşük ve en yüksek değerdir.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPen

from . import tema
from .operator import OperatorSonuc

KISA_GUN = ("Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz")


@dataclass(frozen=True)
class Metrik:
    anahtar: str
    ad: str
    yuzde: bool          # True: oran (%), False: saat
    iyi_yon: int         # +1 artış iyi, -1 artış kötü, 0 yorumsuz
    al: Callable[[dict], Optional[float]]


METRIKLER: Tuple[Metrik, ...] = (
    Metrik("calisma", "Çalışma %", True, +1, lambda d: d.get("calisma")),
    Metrik("durus", "Duruş %", True, -1, lambda d: d.get("durus")),
    Metrik("mola", "Mola %", True, 0, lambda d: d.get("mola")),
    Metrik("bosta", "Boşta kalma (saat)", False, 0, lambda d: d.get("bosta_sn", 0.0) / 3600.0 if "bosta_sn" in d else None),
    Metrik("cakisan", "Çakışan duruş (saat)", False, -1, lambda d: d.get("cakisan_sn", 0.0) / 3600.0 if "cakisan_sn" in d else None),
)
METRIK = {m.anahtar: m for m in METRIKLER}


@dataclass
class Mum:
    gun: date
    acilis: float
    kapanis: float
    yuksek: float
    dusuk: float
    vardiya_sayisi: int


def mum_verisi(vardiya_sonuclari: Dict[int, Dict[str, OperatorSonuc]], operator: Optional[str], metrik: Metrik,
               operatorler: Optional[Iterable[str]] = None) -> List[Mum]:
    """vardiya_sonuclari: vardiya (1-3) -> {operatör -> sonuç} (her vardiya ayrı hesaplanmış).
    operator None ise toplu; operatorler toplu görünümde hangi operatörlerin sayılacağını sınırlar."""
    izinli = set(operatorler) if operatorler is not None else None
    # gün -> vardiya -> değerler
    gunluk: Dict[date, Dict[int, List[float]]] = {}
    for v, sonuclar in vardiya_sonuclari.items():
        for ad, r in sonuclar.items():
            if operator is not None and ad != operator:
                continue
            if operator is None and izinli is not None and ad not in izinli:
                continue
            for gun, d in r.gunler.items():
                x = metrik.al(d)
                if x is not None:
                    gunluk.setdefault(gun, {}).setdefault(v, []).append(x)
    mumlar = []
    for gun in sorted(gunluk):
        vard = gunluk[gun]
        sirali = sorted(vard)
        ort = {v: sum(vard[v]) / len(vard[v]) for v in sirali}
        tum = [x for v in sirali for x in vard[v]]
        mumlar.append(Mum(gun, ort[sirali[0]], ort[sirali[-1]], max(tum), min(tum), len(sirali)))
    return mumlar


def _tepe(deger: float, yuzde: bool) -> float:
    adim = (0.4 if deger > 0.6 else 0.2) if yuzde else (4.0 if deger > 2 else 1.0)
    return max(adim, math.ceil(deger / adim - 1e-9) * adim)


def _bicim(yuzde: bool) -> Callable[[float], str]:
    if yuzde:
        return lambda x: f"%{x * 100:.0f}"
    return lambda x: f"{x:.1f}".replace(".", ",")


def _renk(m: Mum, metrik: Metrik) -> QColor:
    fark = m.kapanis - m.acilis
    if abs(fark) < 1e-9:
        return tema.renk(tema.YAZI_SOLUK)
    artti = fark > 0
    if metrik.iyi_yon == 0:
        return tema.renk(tema.LACIVERT if artti else tema.TURUNCU)
    return tema.renk(tema.YESIL if (artti == (metrik.iyi_yon > 0)) else tema.KIRMIZI)


def aciklama(metrik: Metrik) -> str:
    if metrik.iyi_yon == 0:
        return "Lacivert: gün içinde arttı · Turuncu: azaldı"
    return "Yeşil: gün içinde iyileşti · Kırmızı: kötüleşti"


def mum_grafigi(p, rect, baslik: str, secili: List[Metrik], veri: Dict[str, List[Mum]]):
    """Seçili her ölçü için alt alta bir panel çizer."""
    w, h = rect.width(), rect.height()
    k = max(0.85, min(2.5, w / 820))
    p.setFont(tema.font(14 * k, True))
    p.setPen(tema.renk(tema.LACIVERT))
    p.drawText(QRectF(rect.left(), rect.top() + 4 * k, w, 24 * k), Qt.AlignCenter, baslik)
    if not secili:
        p.setFont(tema.font(11 * k))
        p.setPen(tema.renk(tema.YAZI_SOLUK))
        p.drawText(QRectF(rect.left(), rect.top() + 60 * k, w, 24 * k), Qt.AlignCenter, "Yukarıdan grafikte görmek istediğiniz ölçüleri işaretleyin.")
        return
    ust0 = rect.top() + 38 * k
    pay = (rect.bottom() - 8 * k - ust0) / len(secili)
    for i, metrik in enumerate(secili):
        ust = ust0 + i * pay + 26 * k
        alt = ust0 + (i + 1) * pay - 26 * k
        _panel(p, rect, k, ust, alt, metrik, veri.get(metrik.anahtar, []))


def _panel(p, rect, k, ust, alt, metrik: Metrik, mumlar: List[Mum]):
    sol, sag = rect.left() + 56 * k, rect.right() - 14 * k
    p.setFont(tema.font(10.5 * k, True))
    p.setPen(tema.renk(tema.LACIVERT))
    p.drawText(QRectF(sol, ust - 22 * k, sag - sol, 18 * k), Qt.AlignLeft | Qt.AlignVCenter, metrik.ad)
    p.setFont(tema.font(9.5 * k))
    p.setPen(tema.renk(tema.YAZI_SOLUK))
    p.drawText(QRectF(sol, ust - 22 * k, sag - sol, 18 * k), Qt.AlignRight | Qt.AlignVCenter, aciklama(metrik))
    if not mumlar:
        p.setPen(tema.renk(tema.YAZI_SOLUK))
        p.drawText(QRectF(sol, ust, sag - sol, alt - ust), Qt.AlignCenter, "Bu dönemde veri yok")
        return
    tepe = _tepe(max(m.yuksek for m in mumlar), metrik.yuzde)
    bicim = _bicim(metrik.yuzde)
    cizgi = QPen(tema.renk(tema.CIZGI))
    cizgi.setWidthF(1)
    for i in range(5):
        y = alt - (alt - ust) * i / 4
        p.setPen(cizgi)
        p.drawLine(int(sol), int(y), int(sag), int(y))
        p.setFont(tema.font(9 * k))
        p.setPen(tema.renk(tema.YAZI_SOLUK))
        p.drawText(QRectF(rect.left(), y - 8 * k, 50 * k, 16 * k), Qt.AlignRight | Qt.AlignVCenter, bicim(tepe * i / 4))

    def yy(v: float) -> float:
        return alt - (alt - ust) * max(0.0, min(1.0, v / tepe))

    genis = (sag - sol) / len(mumlar)
    gov = min(genis * 0.5, 34 * k)
    for gi, m in enumerate(mumlar):
        cx = sol + gi * genis + genis / 2
        renk = _renk(m, metrik)
        kalem = QPen(renk)
        kalem.setWidthF(1.6 * k)
        p.setPen(kalem)
        p.drawLine(int(cx), int(yy(m.yuksek)), int(cx), int(yy(m.dusuk)))
        y1, y2 = yy(max(m.acilis, m.kapanis)), yy(min(m.acilis, m.kapanis))
        p.fillRect(QRectF(cx - gov / 2, y1, gov, max(2.0 * k, y2 - y1)), renk)
        if genis >= 40 * k:
            p.setFont(tema.font(9 * k, True))
            p.setPen(tema.renk(tema.YAZI))
            p.drawText(QRectF(cx - genis / 2, yy(m.yuksek) - 16 * k, genis, 14 * k), Qt.AlignCenter, bicim(m.kapanis))
        p.setFont(tema.font(9.5 * k))
        p.setPen(tema.renk(tema.YAZI))
        etiket = m.gun.strftime("%d.%m") + (" " + KISA_GUN[m.gun.weekday()] if genis >= 48 * k else "")
        p.drawText(QRectF(cx - genis / 2, alt + 3 * k, genis, 16 * k), Qt.AlignCenter, etiket)
