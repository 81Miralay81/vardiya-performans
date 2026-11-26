"""Operatörü kendi vardiyasına bağlama (Cormind makine kayıtları + personel verisindeki vardiya planı).

Makine kayıtlarında operatörün yalnızca ADI yazar. Ad personel listesiyle eşleştirilir (büyük/küçük harf ve Türkçe karakter
farkı gözetilmez; Ayarlar'daki elle eşleştirme önceliklidir). Eşleşen kişinin o günkü planlı vardiya saatleri dışında kalan
kayıt parçaları:
  - aynı gün aynı vardiya diliminde toplam süre mesai eşiğini (Ayarlar > Personel veri > fazla çalışma en az) geçiyorsa
    "<ad> (mesai)" adıyla ayrı listelenir,
  - geçmiyorsa (vardiya devri gibi kısa taşmalar) o parça operatörsüz sayılır.
Personel listesinde bulunmayan operatör "<ad> (kalıphane dışı)" olarak işaretlenir.
Personel verisi olmayan günlerde (ör. kaynakta veri başlamadan önce) kayıtlara dokunulmaz.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

MESAI = " (mesai)"
DISARI = " (kalıphane dışı)"
_TR = str.maketrans("ÇĞİIÖŞÜçğıiöşüÂâÎîÛû", "CGIIOSUCGIIOSUAAIIUU")


def ad_anahtar(ad: str) -> str:
    """Eşleştirme anahtarı: büyük harf, Türkçe karakterler sadeleşmiş, tek boşluk."""
    return " ".join((ad or "").translate(_TR).upper().split())


def _kisa_anahtar(ad: str) -> str:
    p = ad_anahtar(ad).split()
    return f"{p[0]} {p[-1]}" if len(p) >= 2 else (p[0] if p else "")


def temel_ad(op: str) -> str:
    """Etiketsiz operatör adı ('Ali Veli (mesai)' -> 'Ali Veli')."""
    for e in (MESAI, DISARI):
        if op.endswith(e):
            return op[: -len(e)]
    return op


def plan_penceresi(gun: date, plan: str) -> Optional[Tuple[datetime, datetime]]:
    """Planlı vardiyanın saat aralığı. '24:00-08:00' o günün gece yarısında başlar (ertesi gün 00–08)."""
    from .personel_veri import plan_bilgi
    tur, a, b = plan_bilgi(plan or "")
    if not a or not b or tur in ("T",):
        return None
    t0 = datetime(gun.year, gun.month, gun.day) + timedelta(hours=a[0], minutes=a[1])
    t1 = datetime(gun.year, gun.month, gun.day) + timedelta(hours=b[0], minutes=b[1])
    if t1 <= t0:
        t1 += timedelta(days=1)
    return t0, t1


class Eslestirici:
    """Operatör adı -> personel sicil kimliği; kişi -> gün -> planlı vardiya penceresi."""

    def __init__(self, con, ilk: date, son: date, ayar: Optional[dict] = None):
        from . import personel_veri as pv
        ayar = ayar or {}
        self.esik_sn = 60.0 * float(ayar.get("pv_fazla_en_az_dk", pv.VARSAYILAN_FAZLA_EN_AZ_DK))
        self.kisiler = pv.personel(con)
        self.tam: Dict[str, int] = {}
        self.kisa: Dict[str, List[int]] = defaultdict(list)
        for sid, p in self.kisiler.items():
            self.tam[ad_anahtar(p.get("ad") or "")] = sid
            self.kisa[_kisa_anahtar(p.get("ad") or "")].append(sid)
        self.elle = {ad_anahtar(k): v for k, v in (ayar.get("op_eslestirme") or {}).items()}
        self.pencere: Dict[int, Dict[date, Optional[Tuple[datetime, datetime]]]] = defaultdict(dict)
        self.veri_gunleri: set = set()
        for r in pv.gunler(con, ilk - timedelta(days=1), son):
            g = date.fromisoformat(r["gun"]) if isinstance(r["gun"], str) else r["gun"]
            self.pencere[r["sicilid"]][g] = plan_penceresi(g, r.get("plan") or "")
            self.veri_gunleri.add(g)

    def sicil(self, ad: str) -> Optional[int]:
        """Eşleşen kişi; elle eşleştirmede boş değer 'kalıphane dışı' demektir (-1)."""
        k = ad_anahtar(ad)
        if k in self.elle:
            try:
                return int(self.elle[k]) if str(self.elle[k]).strip() else -1
            except ValueError:
                return -1
        if k in self.tam:
            return self.tam[k]
        aday = self.kisa.get(_kisa_anahtar(ad), [])
        return aday[0] if len(aday) == 1 else None

    def kendi_mi(self, sid: int, t0: datetime, t1: datetime) -> bool:
        """[t0, t1) kişinin planlı vardiya penceresi içinde mi (önceki günün gece vardiyası dahil)."""
        for g in (t0.date(), t0.date() - timedelta(days=1)):
            p = self.pencere.get(sid, {}).get(g)
            if p and p[0] <= t0 and t1 <= p[1]:
                return True
        return False


def _dilimle(a: datetime, b: datetime, sinirlar: List[datetime]):
    noktalar = sorted({a, b} | {s for s in sinirlar if a < s < b})
    for i in range(len(noktalar) - 1):
        yield noktalar[i], noktalar[i + 1]


def vardiyaya_bagla(kayit: Iterable[Tuple[str, str, str, datetime, datetime]], es: Eslestirici) -> List[Tuple[str, str, str, datetime, datetime]]:
    """Kayıtlardaki operatörü kendi vardiyasına bağlar (açıklama modülün başında)."""
    kayit = list(kayit)
    from .operator import operator_adi
    parca: List[Tuple[str, str, str, datetime, datetime, Optional[int], bool]] = []   # (op, m, tip, a, b, sid, kendi)
    yabanci_sure: Dict[Tuple[int, date, int], float] = defaultdict(float)
    for op, m, tip, a, b in kayit:
        ad = operator_adi(op)
        if not ad or b <= a:
            parca.append((op, m, tip, a, b, None, True))
            continue
        sid = es.sicil(ad)
        if sid is None or sid < 0:
            parca.append((ad + DISARI, m, tip, a, b, None, True))
            continue
        if a.date() not in es.veri_gunleri and (a - timedelta(days=1)).date() not in es.veri_gunleri:
            parca.append((op, m, tip, a, b, None, True))             # personel verisi yok: dokunma
            continue
        sinir = []
        for g in (a.date() - timedelta(days=1), a.date(), b.date()):
            p = es.pencere.get(sid, {}).get(g)
            if p:
                sinir += [p[0], p[1]]
            gun0 = datetime(g.year, g.month, g.day)
            sinir += [gun0 + timedelta(hours=h) for h in (0, 8, 16, 24)]
        for x, y in _dilimle(a, b, sinir):
            kendi = es.kendi_mi(sid, x, y)
            parca.append((ad, m, tip, x, y, sid, kendi))
            if not kendi:
                yabanci_sure[(sid, x.date(), x.hour // 8 + 1)] += (y - x).total_seconds()
    sonuc = []
    for op, m, tip, a, b, sid, kendi in parca:
        if sid is None or kendi:
            sonuc.append((op, m, tip, a, b))
        elif yabanci_sure[(sid, a.date(), a.hour // 8 + 1)] >= es.esik_sn:
            sonuc.append((op + MESAI, m, tip, a, b))
        else:
            sonuc.append(("", m, tip, a, b))
    return sonuc


def bagla(con, kayit, ilk: date, son: date, ayar: Optional[dict] = None):
    """Kolay çağrı: personel verisi yoksa ya da bir hata olursa kayıtlar olduğu gibi döner."""
    try:
        es = Eslestirici(con, ilk, son, ayar)
        if not es.kisiler:
            return list(kayit)
        return vardiyaya_bagla(kayit, es)
    except Exception:  # noqa: BLE001
        return list(kayit)


def eslesmeyenler(con, kayit, ayar: Optional[dict] = None) -> List[str]:
    """Personel listesiyle eşleşmeyen operatör adları (Ayarlar'daki elle eşleştirme tablosu için)."""
    from .operator import operator_adi
    try:
        es = Eslestirici(con, date.today(), date.today(), ayar)
    except Exception:  # noqa: BLE001
        return []
    adlar = sorted({operator_adi(k[0]) for k in kayit if operator_adi(k[0])})
    return [a for a in adlar if es.sicil(a) is None]
