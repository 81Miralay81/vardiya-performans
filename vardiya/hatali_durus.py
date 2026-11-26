"""Hatalı duruşlar: makinede "kimse yok, iş yok" demesi gereken duruşlar (Ayarlar'da seçilir, ör. İŞ EMRİ PLAN YOK,
ÇALIŞMIYOR) sürerken makinede bir operatör kayıtlı görünüyorsa ya da üzerinde iş (ürün kodu) varsa o duruş hatalıdır.

İki tür hata ayrı tutulur:
  - "operator": duruş sırasında makinede operatör kayıtlı (iş de olabilir),
  - "is":       operatör yok ama makinede iş (ürün kodu) görünüyor.
Ayarlar'daki alt eşikten (varsayılan 5 dk) kısa olaylar listeye ve grafiklere girmez.
Raporlardan hariç tutulan duruş türleri de kontrol edilir: onlarda operatör ya da iş varsa hariç tutulmaz, burada görünür.
Kayıttaki operatör / iş bilgisi kaydın açıldığı ana aittir: seçilen aralıktan önce açılmış (ör. aylardır süren) kayıtlar
hatalı sayılmaz; aralıkta açılan kayıt da yalnızca açıldığı gün içinde sayılır.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from .hesap import bol

TUR_OPERATOR = "operator"
TUR_IS = "is"
TUR_AD = {TUR_OPERATOR: "Operatör var", TUR_IS: "Operatör yok · iş var"}
TUR_RENK = {TUR_OPERATOR: "#7B4FA8", TUR_IS: "#E0702A"}
VARSAYILAN_EN_AZ_DK = 5


@dataclass
class Olay:
    makine: str
    tip: str
    bas: datetime
    bit: datetime
    operator: str
    urun: str
    is_emri: str
    urun_adi: str

    @property
    def tur(self) -> str:
        return TUR_OPERATOR if self.operator else TUR_IS

    @property
    def saat(self) -> float:
        return max(0.0, (self.bit - self.bas).total_seconds() / 3600.0)

    @property
    def vardiya(self) -> int:
        return 1 if self.bas.hour < 8 else (2 if self.bas.hour < 16 else 3)

    @property
    def is_ad(self) -> str:
        """Operatörsüz işte gösterilecek ad: ürün kodu (yoksa iş emri)."""
        return self.urun or self.is_emri or "iş"


def kontrol_turleri(ayar: Optional[dict]) -> List[str]:
    a = ayar or {}
    return sorted(set(a.get("hatali_durus_turleri") or []) | set(a.get("operator_haric_durus") or []), key=str.casefold)


def _urun(s) -> str:
    s = " ".join(str(s or "").split())
    return "" if s in ("", "-") else s


def tespit(con, ilk: date, son: date, ayar: Optional[dict] = None, makineler: Optional[Iterable[str]] = None) -> List[Olay]:
    """Seçili günlerdeki hatalı duruşlar (kayıtlar gün sınırında kırpılır, alt eşikten kısalar atılır)."""
    from . import veritabani as vt
    from .operator import operator_adi
    ayar = ayar if ayar is not None else vt.ayar_oku(con)
    turler = kontrol_turleri(ayar)
    if not turler:
        return []
    en_az = float(ayar.get("hatali_durus_en_az_dk", VARSAYILAN_EN_AZ_DK)) * 60.0
    mset = set(makineler) if makineler else None
    alt = datetime(ilk.year, ilk.month, ilk.day)
    ust = datetime(son.year, son.month, son.day) + timedelta(days=1)
    yer = ", ".join("?" * len(turler))
    sonuc: List[Olay] = []
    for r in vt.aralik_satirlari(con, "makine, tip, baslangic, bitis, operator, urun_kodu, is_emri, urun_adi", ilk, son,
                                 f"tip IN ({yer})", tuple(turler)):
        if mset is not None and r["makine"] not in mset:
            continue
        op, urun = operator_adi(r["operator"]), _urun(r["urun_kodu"])
        if not op and not urun:
            continue                                     # olması gereken: kimse yok, iş yok
        a0 = vt.zaman(r["baslangic"])
        if a0 < alt:
            continue                                     # aralıktan önce açılmış kayıt: üstündeki operatör / iş eski bilgidir
        gun_sonu = datetime(a0.year, a0.month, a0.day) + timedelta(days=1)
        a, b = a0, min(vt.zaman(r["bitis"]), ust, gun_sonu)   # yalnızca açıldığı gün sayılır (ertesi günlere taşınmaz)
        if (b - a).total_seconds() < max(1.0, en_az):
            continue
        sonuc.append(Olay(r["makine"], r["tip"], a, b, op, urun, _urun(r["is_emri"]), " ".join(str(r["urun_adi"] or "").split())))
    sonuc.sort(key=lambda o: (o.makine, o.bas))
    return sonuc


# ---------------------------------------------------------------- kırılımlar (grafiklerin verisi)
def _topla(olaylar: Iterable[Olay], anahtar) -> Dict[str, float]:
    d: Dict[str, float] = {}
    for o in olaylar:
        k = anahtar(o)
        d[k] = d.get(k, 0.0) + o.saat
    return d


def sirala(d: Dict[str, float]) -> List[Tuple[str, float]]:
    return sorted(d.items(), key=lambda x: (-x[1], x[0]))


def makineye_gore(olaylar: Iterable[Olay]) -> List[Tuple[str, float]]:
    return sirala(_topla(olaylar, lambda o: o.makine))


def vardiyaya_gore(olaylar: Iterable[Olay]) -> List[Tuple[str, float]]:
    """Süre vardiya sınırlarında bölünür (Performans'taki gibi)."""
    v = {1: 0.0, 2: 0.0, 3: 0.0}
    for o in olaylar:
        for _g, vv, sn in bol(o.bas, o.bit, True):
            v[vv] += sn / 3600.0
    return [(f"{k}. Vardiya", v[k]) for k in (1, 2, 3)]


def olay_vardiyada(o: Olay, v: int) -> bool:
    return any(vv == v and sn > 0 for _g, vv, sn in bol(o.bas, o.bit, True))


def operatore_gore(olaylar: Iterable[Olay]) -> List[Tuple[str, float]]:
    return sirala(_topla((o for o in olaylar if o.tur == TUR_OPERATOR), lambda o: o.operator))


def ise_gore(olaylar: Iterable[Olay]) -> List[Tuple[str, float]]:
    return sirala(_topla((o for o in olaylar if o.tur == TUR_IS), lambda o: o.is_ad))


def durusa_gore(olaylar: Iterable[Olay]) -> List[Tuple[str, float]]:
    return sirala(_topla(olaylar, lambda o: o.tip))


def gune_gore(olaylar: Iterable[Olay], ilk: date, son: date) -> List[Tuple[date, List[float]]]:
    """[(gün, [1., 2., 3. vardiya saat])] — zaman grafiği (gün / vardiya / gün × vardiya) için."""
    gunler = [ilk + timedelta(days=i) for i in range((son - ilk).days + 1)]
    d: Dict[Tuple[date, int], float] = {}
    for o in olaylar:
        for g, v, sn in bol(o.bas, o.bit, True):
            d[(g, v)] = d.get((g, v), 0.0) + sn / 3600.0
    return [(g, [d.get((g, v), 0.0) for v in (1, 2, 3)]) for g in gunler]


def zaman_bloklari(con, makine: str, ilk: date, son: date, vurgu: Iterable[Olay]) -> Dict[str, list]:
    """Zaman çizelgesi için makinenin tüm kayıtları; hatalı olaylara denk gelen bloklar vurgulu (kırmızı taralı çerçeve)."""
    from . import veritabani as vt
    from .hesap import CALISIYOR, statu_bul
    from .operator import operator_adi
    alt = datetime(ilk.year, ilk.month, ilk.day)
    ust = datetime(son.year, son.month, son.day) + timedelta(days=1)
    vset = [(o.bas, o.bit) for o in vurgu if o.makine == makine]
    bloklar = []
    for r in vt.aralik_satirlari(con, "makine, tip, baslangic, bitis, operator, urun_kodu", ilk, son, "makine = ?", (makine,)):
        a0 = vt.zaman(r["baslangic"])
        if a0 < alt:
            continue                                     # aralıktan önce açılmış kayıt: üstündeki operatör / iş eski bilgidir
        gun_sonu = datetime(a0.year, a0.month, a0.day) + timedelta(days=1)
        a, b = a0, min(vt.zaman(r["bitis"]), ust, gun_sonu)   # yalnızca açıldığı gün sayılır (ertesi günlere taşınmaz)
        if b <= a:
            continue
        op = operator_adi(r["operator"])
        urun = _urun(r["urun_kodu"])
        bilgi = (op or "operatör yok") + (f" · iş: {urun}" if urun else "")
        hatali = any(a < y and x < b for x, y in vset) and r["tip"] and statu_bul(r["tip"]) != CALISIYOR
        bloklar.append((a, b, r["tip"], statu_bul(r["tip"]), bilgi, bool(hatali)))
    bloklar.sort(key=lambda x: x[0])
    return {makine: bloklar}
