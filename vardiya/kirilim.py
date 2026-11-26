"""Ayrıntı kırılımları (exe ve tarayıcı aynı hesabı kullanır).

- durus_kirilimi: bir makinenin bir duruş türünün vardiyalara ve operatörlere göre dağılımı (Performans 3. kırılım).
- supheli_molalar: mola saatinde makine moladan çıkıp çalışmaya geçmiş mi (Performans > mola > şüpheli mola).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from .hesap import CALISIYOR, DURUS, MOLA, bol, durus_adi, statu_bul, tr_kucuk
from .operator import operator_adi, operator_dogrula

OPERATOR_YOK = "Operatör yok"
MOLA_TURLERI = (("cay", "Çay"), ("yemek", "Yemek"))
CEVRE = timedelta(minutes=30)          # zaman çizelgesinde mola saatinin öncesi ve sonrası
BOSLUK = timedelta(minutes=2)          # moladan çalışmaya geçişte iki kayıt arasında kabul edilen en uzun boşluk
EN_AZ_SUPHELI_SN = 60                  # mola saatindeki çalışma bundan kısaysa (birkaç saniyelik sinyal) sayılmaz
KISA_MOLA = timedelta(seconds=60)      # çalışırken araya giren bu kadar kısa mola kaydı: makine zaten çalışıyordur (şüpheli değil)


# ---------------------------------------------------------------- Performans: duruşun vardiya / operatör kırılımı
def durus_kirilimi(con, ilk: date, son: date, makine: str, tip: str) -> Dict[str, List[Tuple[str, float]]]:
    """{'vardiya': [(ad, saat)], 'operator': [(ad, saat)]}. Toplam, Performans'taki duruş dökümüyle aynıdır:
    seçili günlere düşen kısım sayılır; operatör adı yalnızca operatörün o vardiyada makinede bulunduğu kısımda kalır."""
    from . import veritabani as vt
    alt = datetime(ilk.year, ilk.month, ilk.day)
    ust = datetime(son.year, son.month, son.day) + timedelta(days=1)
    ham = []
    for r in vt.aralik_satirlari(con, "operator, makine, tip, baslangic, bitis", ilk, son, "makine = ?", (makine,)):
        ham.append((r["operator"], r["makine"], r["tip"], vt.zaman(r["baslangic"]), vt.zaman(r["bitis"])))
    gset = {ilk + timedelta(days=i) for i in range((son - ilk).days + 1)}
    vard: Dict[int, float] = {1: 0.0, 2: 0.0, 3: 0.0}
    ops: Dict[str, float] = {}
    from .operator_vardiya import bagla
    for op, m, t, a, b in bagla(con, operator_dogrula(ham, alt, ust), ilk, son, vt.ayar_oku(con)):
        if statu_bul(t) != DURUS or durus_adi(t, a, b) != tip:
            continue
        for gun, v, sn in bol(a, b, True):
            if gun in gset and sn > 0:
                vard[v] += sn / 3600.0
                ad = operator_adi(op) or OPERATOR_YOK
                ops[ad] = ops.get(ad, 0.0) + sn / 3600.0
    oplar = sorted(((a, s) for a, s in ops.items() if a != OPERATOR_YOK), key=lambda x: -x[1])
    if ops.get(OPERATOR_YOK):
        oplar.append((OPERATOR_YOK, ops[OPERATOR_YOK]))          # gri çubuk hep en sonda
    return {"vardiya": [(f"{v}. Vardiya", vard[v]) for v in (1, 2, 3)], "operator": oplar}


# ---------------------------------------------------------------- şüpheli mola
def _saat(s: str) -> Optional[Tuple[int, int]]:
    try:
        h, m = str(s).strip().split(":")
        h, m = int(h), int(m)
        if 0 <= h <= 24 and 0 <= m < 60:
            return h, m
    except (ValueError, AttributeError):
        pass
    return None


def mola_pencereleri(mola_saatleri: dict, gunler: Iterable[date]) -> List[Tuple[date, int, str, datetime, datetime]]:
    """Ayarlar'daki mola saatlerinden seçili günlerin mola aralıkları: (gün, vardiya, tür adı, başlangıç, bitiş)."""
    sonuc = []
    for gun in sorted(set(gunler)):
        g0 = datetime(gun.year, gun.month, gun.day)
        for v in (1, 2, 3):
            vs = (mola_saatleri or {}).get(str(v)) or {}
            for anahtar, ad in MOLA_TURLERI:
                ab = vs.get(anahtar) or []
                if len(ab) != 2:
                    continue
                a, b = _saat(ab[0]), _saat(ab[1])
                if not a or not b:
                    continue
                bas = g0 + timedelta(hours=a[0], minutes=a[1])
                bit = g0 + timedelta(hours=b[0], minutes=b[1])
                if bit <= bas:
                    bit += timedelta(days=1)
                sonuc.append((gun, v, ad, bas, bit))
    return sonuc


@dataclass
class SupheliMola:
    makine: str
    gun: date
    vardiya: int
    tur: str                     # Çay / Yemek
    pb: datetime                 # mola saati (Ayarlar)
    ps: datetime
    mb: datetime                 # mola kaydı
    ms: datetime
    cb: datetime                 # moladan sonra başlayan çalışma
    cs: datetime
    operator: str
    bloklar: List[Tuple[datetime, datetime, str, str]] = field(default_factory=list)   # (baş, bit, durum, tür) ±30 dk

    @property
    def sn(self) -> float:
        return max(0.0, (min(self.cs, self.ps) - max(self.cb, self.pb)).total_seconds())

    def sozluk(self) -> dict:
        f = "%Y-%m-%d %H:%M:%S"
        return {"makine": self.makine, "gun": self.gun.isoformat(), "vardiya": self.vardiya, "tur": self.tur,
                "pb": self.pb.strftime(f), "ps": self.ps.strftime(f), "mb": self.mb.strftime(f), "ms": self.ms.strftime(f),
                "cb": self.cb.strftime(f), "cs": self.cs.strftime(f), "operator": self.operator, "sn": round(self.sn),
                "bloklar": [[a.strftime(f), b.strftime(f), d, t] for a, b, d, t in self.bloklar]}


VARSAYILAN_EN_KISA_MOLA_DK = 2.0      # Ayarlar'da değiştirilir: makine bundan kısa molada kaldıysa olay sayılmaz


def supheli_molalar(kayitlar: Iterable[Tuple[str, str, str, datetime, datetime]], gunler: Iterable[date],
                    mola_saatleri: dict, en_kisa_mola_dk: float = VARSAYILAN_EN_KISA_MOLA_DK) -> List[SupheliMola]:
    """kayitlar: (operatör, makine, tür, başlangıç, bitiş). Şüpheli: mola saati içinde makine bir MOLA kaydındayken
    (duruşta iken otomatik molaya geçmiş ya da çalışmayı bitirip molaya alınmış) moladan çıkıp mola saati bitmeden
    ÇALIŞMAYA geçmesi. Mola saatinde zaten çalışan ve çalışmaya devam eden makine şüpheli değildir.
    en_kisa_mola_dk (alt sınır): makine çalışmaya geçmeden önce en az bu kadar molada kalmış olmalı (Cormind'in mola saati
    gelince birkaç saniyeliğine yazdığı otomatik mola kayıtları sayılmaz) ve mola saatindeki çalışma da en az bu kadar
    sürmüş olmalı (mola bitimine birkaç dakika kala başlayan çalışma sayılmaz). Art arda gelen mola kayıtları tek mola sayılır."""
    en_kisa = timedelta(minutes=max(0.0, float(en_kisa_mola_dk or 0)))
    pencereler = mola_pencereleri(mola_saatleri, gunler)
    if not pencereler:
        return []
    makineye: Dict[str, list] = {}
    for op, m, t, a, b in kayitlar:
        if b > a:
            makineye.setdefault(m, []).append((a, b, t, op))
    sonuc: List[SupheliMola] = []
    for m, liste in makineye.items():
        liste.sort(key=lambda x: (x[0], x[1]))
        for i, (a, b, t, op) in enumerate(liste):
            if statu_bul(t) != MOLA:
                continue
            for gun, v, tur, pb, ps in pencereler:
                if not (pb < b and a < ps) or not (pb <= b < ps):     # mola kaydı, mola saati içinde bitmeli
                    continue
                sonraki = None
                for j in range(i + 1, len(liste)):
                    x = liste[j]
                    if x[0] >= b - BOSLUK and x[0] > a:
                        sonraki = x
                        break
                if sonraki is None or statu_bul(sonraki[2]) != CALISIYOR:
                    continue
                cb, cs = sonraki[0], sonraki[1]
                if not (cb - b <= BOSLUK and pb <= cb < ps):
                    continue
                onceki = next((x for x in reversed(liste[:i]) if x[1] >= a - BOSLUK and x[0] < a), None)
                if onceki is not None and statu_bul(onceki[2]) == CALISIYOR and b - a < KISA_MOLA:
                    continue                    # çalışan makine çalışmaya devam ediyor: arada birkaç saniyelik mola kaydı
                mola_bas = a                    # art arda mola kayıtları: molanın gerçek başlangıcı
                for x in reversed(liste[:i]):
                    if statu_bul(x[2]) == MOLA and x[1] >= mola_bas - BOSLUK and x[0] < mola_bas:
                        mola_bas = x[0]
                    elif x[1] > mola_bas - BOSLUK:
                        break
                if b - max(mola_bas, pb - CEVRE) < en_kisa:
                    continue                    # makine gerçekten molada kalmadı (birkaç saniyelik otomatik mola kaydı)
                if (min(cs, ps) - cb).total_seconds() < max(EN_AZ_SUPHELI_SN, en_kisa.total_seconds()):
                    continue                    # mola saatindeki çalışma da alt sınırdan kısaysa sayılmaz
                g0, g1 = pb - CEVRE, ps + CEVRE
                bloklar = [(max(x[0], g0), min(x[1], g1), statu_bul(x[2]), x[2]) for x in liste if x[0] < g1 and x[1] > g0]
                sonuc.append(SupheliMola(m, gun, v, tur, pb, ps, a, b, cb, cs,
                                         operator_adi(sonraki[3]) or operator_adi(op) or OPERATOR_YOK, bloklar))
                break
    sonuc.sort(key=lambda e: (e.makine, e.cb))
    return sonuc


def supheli_ozet(olaylar: List[SupheliMola], kayitlar: Iterable[Tuple[str, str, str, datetime, datetime]],
                 gunler: Iterable[date]) -> Dict[str, Dict[int, dict]]:
    """makine -> vardiya -> {'dk_gun': günde ortalama şüpheli dakika, 'adet', 'olaylar': [SupheliMola]}.
    Günlük ortalama, mola pastasıyla aynı ölçekte olsun diye makinenin o vardiyada kaydı olan gün sayısına bölünür."""
    gset = set(gunler)
    gun_say: Dict[Tuple[str, int], set] = {}
    for _op, m, _t, a, b in kayitlar:
        for g, v, sn in bol(a, b, True):
            if g in gset and sn > 0:
                gun_say.setdefault((m, v), set()).add(g)
    ozet: Dict[str, Dict[int, dict]] = {}
    for e in olaylar:
        d = ozet.setdefault(e.makine, {}).setdefault(e.vardiya, {"sn": 0.0, "adet": 0, "olaylar": []})
        d["sn"] += e.sn
        d["adet"] += 1
        d["olaylar"].append(e)
    for m, vs in ozet.items():
        for v, d in vs.items():
            n = max(1, len(gun_say.get((m, v), ())))
            d["dk_gun"] = d["sn"] / 60.0 / n
    return ozet


# ---------------------------------------------------------------- Performans 4.-5. seviye: operatör ayrıntısı + zaman çizelgesi
VARDIYA_SAAT = {1: (0, 8), 2: (8, 16), 3: (16, 24)}


def donem_kayitlari(con, ilk: date, son: date) -> List[Tuple[str, str, str, datetime, datetime]]:
    """Dönemin tüm makinelerdeki kayıtları, operatör adı doğrulanmış (operatör yoksa '')."""
    from . import veritabani as vt
    alt = datetime(ilk.year, ilk.month, ilk.day)
    ust = datetime(son.year, son.month, son.day) + timedelta(days=1)
    ham = [(r["operator"], r["makine"], r["tip"], vt.zaman(r["baslangic"]), vt.zaman(r["bitis"]))
           for r in vt.aralik_satirlari(con, "operator, makine, tip, baslangic, bitis", ilk, son)]
    from .operator_vardiya import bagla
    dogru = bagla(con, operator_dogrula(ham, alt, ust), ilk, son, vt.ayar_oku(con))
    return [(operator_adi(op) or "", m, t, max(a, alt), min(b, ust)) for op, m, t, a, b in dogru if b > alt and a < ust]


def operator_ayrinti(kayit: List[Tuple[str, str, str, datetime, datetime]], ilk: date, son: date, tip: str, operator: str) -> dict:
    """Bir operatörün (ya da 'Operatör yok') bir duruş türündeki süresi: makineye göre, gün ve vardiyaya göre; zaman
    çizelgesi için o makinelerin tüm kayıtları (vurgu: bu operatör + bu duruş). Saatler seçili günlere düşen kısımdır."""
    gset = {ilk + timedelta(days=i) for i in range((son - ilk).days + 1)}

    def eslesir(op: str, t: str, a: datetime, b: datetime) -> bool:
        return statu_bul(t) == DURUS and durus_adi(t, a, b) == tip and (op or OPERATOR_YOK) == operator
    makine: Dict[str, float] = {}
    gun_v: Dict[Tuple[date, int], float] = {}
    for op, m, t, a, b in kayit:
        if not eslesir(op, t, a, b):
            continue
        for g, v, sn in bol(a, b, True):
            if g in gset and sn > 0:
                makine[m] = makine.get(m, 0.0) + sn / 3600.0
                gun_v[(g, v)] = gun_v.get((g, v), 0.0) + sn / 3600.0
    sira = sorted(makine, key=lambda x: -makine[x])
    msatir = set(sira)
    bloklar: Dict[str, list] = {m: [] for m in sira}
    for op, m, t, a, b in kayit:
        if m in msatir and b > a:
            bloklar[m].append((a, b, t, statu_bul(t), op or OPERATOR_YOK, eslesir(op, t, a, b)))
    for m in bloklar:
        bloklar[m].sort(key=lambda x: x[0])
    return {"makine": [(m, makine[m]) for m in sira],
            "gun": [(g, [gun_v.get((g, v), 0.0) for v in (1, 2, 3)]) for g in sorted(gset)],
            "bloklar": bloklar}
