"""Hatalı duruşlar: makinede "kimse yok, iş yok" demesi gereken duruşlar (Ayarlar'da seçilir, ör. İŞ EMRİ PLAN YOK,
ÇALIŞMIYOR) sürerken makinede bir operatör kayıtlı görünüyorsa ya da üzerinde iş (ürün kodu) varsa o duruş hatalıdır.

İki tür hata ayrı tutulur:
  - "operator": duruş sırasında makinede operatör kayıtlı (iş de olabilir),
  - "is":       operatör yok ama makinede iş (ürün kodu) görünüyor.
Ayarlar'daki alt eşikten (varsayılan 5 dk) kısa olaylar listeye ve grafiklere girmez.
Raporlardan hariç tutulan duruş türleri de kontrol edilir: onlarda operatör ya da iş varsa hariç tutulmaz, burada görünür.
Kayıttaki operatör / iş bilgisi kaydın açıldığı ana aittir: seçilen aralıktan önce açılmış (ör. aylardır süren) kayıtlar
hatalı sayılmaz; aralıkta açılan kayıt da yalnızca açıldığı gün içinde sayılır.

Gece doğrulaması (cormind.dogrulama_cek): duruş kaydındaki operatör / iş bilgisi kaydın açıldığı ana aittir, sonradan
güncellenmez. Doğrulanan günlerde gerçek durum kullanılır:
  - operatör: Cormind'deki operatör giriş-çıkış kaydı (cm_oturum) duruşla çakıştığı kadar,
  - iş: işin makineden atıldığı an (iş hâlâ makinede değilse işin son değişme zamanı) gelene kadar.
Doğrulanmamış günlerde (gece kontrolü yapılmamış) eski kural geçerlidir: duruş kaydındaki bilgi.
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
    kaynak: str = "kayit"          # "kayit": duruş kaydındaki bilgi · "gercek": gece doğrulamasıyla (giriş-çıkış / iş atılma)
    not_: str = ""                 # ör. "iş atılma zamanı kesin değil"

    @property
    def kaynak_yazi(self) -> str:
        y = "giriş-çıkış ve iş kontrolüyle doğrulandı" if self.kaynak == "gercek" else "duruş kaydındaki bilgi (doğrulanmadı)"
        return y + (f" · {self.not_}" if self.not_ else "")

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


def _adaylar(con, ilk: date, son: date, ayar: dict, makineler=None) -> List[tuple]:
    """Kontrol edilen türlerdeki, aralıkta açılmış, alt eşikten uzun duruşlar (operatör / iş olsun olmasın):
    [(makine, tip, bas, bit, operator, urun, is_emri, urun_adi)]. Süre açıldığı günün sonunda kesilir."""
    from . import veritabani as vt
    from .operator import operator_adi
    turler = kontrol_turleri(ayar)
    if not turler:
        return []
    en_az = float(ayar.get("hatali_durus_en_az_dk", VARSAYILAN_EN_AZ_DK)) * 60.0
    mset = set(makineler) if makineler else None
    alt = datetime(ilk.year, ilk.month, ilk.day)
    ust = datetime(son.year, son.month, son.day) + timedelta(days=1)
    yer = ", ".join("?" * len(turler))
    sonuc = []
    for r in vt.aralik_satirlari(con, "makine, tip, baslangic, bitis, operator, urun_kodu, is_emri, urun_adi", ilk, son,
                                 f"tip IN ({yer})", tuple(turler)):
        if mset is not None and r["makine"] not in mset:
            continue
        a0 = vt.zaman(r["baslangic"])
        if a0 < alt:
            continue                                     # aralıktan önce açılmış kayıt: üstündeki operatör / iş eski bilgidir
        gun_sonu = datetime(a0.year, a0.month, a0.day) + timedelta(days=1)
        b = min(vt.zaman(r["bitis"]), ust, gun_sonu)     # yalnızca açıldığı gün sayılır (ertesi günlere taşınmaz)
        if (b - a0).total_seconds() < max(1.0, en_az):
            continue
        sonuc.append((r["makine"], r["tip"], a0, b, operator_adi(r["operator"]), _urun(r["urun_kodu"]), _urun(r["is_emri"]),
                      " ".join(str(r["urun_adi"] or "").split())))
    return sonuc


class _Dogrulama:
    """Gece doğrulamasının kayıtları: hangi makine-gün doğrulandı, gerçek operatör oturumları, işlerin son durumu."""

    def __init__(self, con, ilk: date, son: date):
        self.gunler: set = set()
        self.oturum: Dict[str, List[Tuple[datetime, Optional[datetime], str]]] = {}
        self.is_durum: Dict[Tuple[str, str, str], Tuple[int, Optional[datetime]]] = {}
        g1, g2 = ilk.isoformat(), son.isoformat()
        try:
            for r in con.execute("SELECT gun, makine FROM cm_dogrulama WHERE gun >= ? AND gun <= ?", (g1, g2)):
                self.gunler.add((r[0], r[1]))
            if not self.gunler:
                return
            alt = (datetime(ilk.year, ilk.month, ilk.day) - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
            ust = (datetime(son.year, son.month, son.day) + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
            for r in con.execute("SELECT makine, operator, bas, bit FROM cm_oturum WHERE bas < ? AND (bit IS NULL OR bit > ?)", (ust, alt)):
                self.oturum.setdefault(r[0], []).append((_z(r[2]), _z(r[3]), r[1]))
            for r in con.execute("SELECT gun, makine, is_emri, makinede, degisme FROM cm_is_durum WHERE gun >= ? AND gun <= ?", (g1, g2)):
                self.is_durum[(r[0], r[1], r[2])] = (int(r[3] or 0), _z(r[4]))
        except Exception:  # noqa: BLE001  (eski veri tabanı: tablolar yok)
            self.gunler = set()
        for lst in self.oturum.values():
            lst.sort(key=lambda x: x[0])

    def var_mi(self, gun: date, makine: str) -> bool:
        return (gun.isoformat(), makine) in self.gunler

    def operatorler(self, makine: str, a: datetime, b: datetime, simdi: datetime) -> List[Tuple[datetime, datetime, str]]:
        lst = self.oturum.get(makine) or []
        sonuc = []
        for i, (x, y, ad) in enumerate(lst):
            if y is None:                                # hâlâ açık: sonraki oturuma (yoksa şimdiye) kadar
                y = next((z[0] for z in lst[i + 1:] if z[0] > x), simdi)
            x2, y2 = max(a, x), min(b, y)
            if y2 > x2:
                sonuc.append((x2, y2, ad))
        return sonuc

    def is_araligi(self, gun: date, makine: str, is_emri: str, a: datetime, b: datetime):
        """(bitiş, not) — iş [a, bitiş) arasında makinede; None: o duruşta iş yoktu."""
        d = self.is_durum.get((gun.isoformat(), makine, is_emri))
        if d is None:
            return b, "iş bilgisi doğrulanamadı"
        makinede, degisme = d
        if makinede:
            return b, ""
        if degisme is None:
            return b, "iş atılma zamanı kesin değil"
        if degisme <= a:
            return None                                  # iş duruş başlamadan atılmış: kayıttaki iş eski bilgi
        if degisme < b:
            return degisme, ""
        return b, "iş atılma zamanı kesin değil"


def _z(s) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.strptime(str(s)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _gercek_parcalar(dog: _Dogrulama, k: tuple, simdi: datetime) -> List[Tuple[datetime, datetime, str, bool, str]]:
    """Bir duruşun gerçekten hatalı olan parçaları: [(bas, bit, operatör, iş var mı, not)]."""
    mk, _tip, a, b, _op, urun, emri, _uadi = k
    ops = dog.operatorler(mk, a, b, simdi)
    is_bit, is_not = None, ""
    if urun or emri:
        r = dog.is_araligi(a.date(), mk, emri or urun, a, b)
        if r is not None:
            is_bit, is_not = r
    sinir = sorted({a, b} | {x for x, _, _ in ops} | {y for _, y, _ in ops} | ({is_bit} if is_bit else set()))
    parcalar: List[list] = []
    for x, y in zip(sinir, sinir[1:]):
        if y <= x:
            continue
        ad = next((o for p, q, o in ops if p <= x and y <= q), "")
        is_var = is_bit is not None and y <= is_bit
        if not ad and not is_var:
            continue
        if parcalar and parcalar[-1][1] == x and parcalar[-1][2] == ad and parcalar[-1][3] == is_var:
            parcalar[-1][1] = y
        else:
            parcalar.append([x, y, ad, is_var, is_not if is_var else ""])
    return [tuple(p) for p in parcalar]


def tespit(con, ilk: date, son: date, ayar: Optional[dict] = None, makineler: Optional[Iterable[str]] = None,
           dogrula: bool = True) -> List[Olay]:
    """Seçili günlerdeki hatalı duruşlar (alt eşikten kısalar atılır). Gece doğrulaması yapılmış makine-günlerde gerçek
    operatör giriş-çıkışı ve işin atılma zamanı kullanılır; yapılmamışlarda duruş kaydındaki bilgi."""
    from . import veritabani as vt
    ayar = ayar if ayar is not None else vt.ayar_oku(con)
    adaylar = _adaylar(con, ilk, son, ayar, makineler)
    if not adaylar:
        return []
    en_az = max(1.0, float(ayar.get("hatali_durus_en_az_dk", VARSAYILAN_EN_AZ_DK)) * 60.0)
    dog = _Dogrulama(con, ilk, son) if dogrula else None
    simdi = datetime.now().replace(microsecond=0)
    sonuc: List[Olay] = []
    for k in adaylar:
        mk, tip, a, b, op, urun, emri, uadi = k
        if dog is not None and dog.var_mi(a.date(), mk):
            for x, y, ad, is_var, not_ in _gercek_parcalar(dog, k, simdi):
                if (y - x).total_seconds() >= en_az:
                    sonuc.append(Olay(mk, tip, x, y, ad, urun if is_var else "", emri if is_var else "", uadi, "gercek", not_))
            continue
        if not op and not urun:
            continue                                     # olması gereken: kimse yok, iş yok
        sonuc.append(Olay(mk, tip, a, b, op, urun, emri, uadi))
    sonuc.sort(key=lambda o: (o.makine, o.bas))
    return sonuc


def dogrulanacak_makineler(con, ilk: date, son: date, ayar: Optional[dict] = None) -> Dict[str, List[str]]:
    """Gece doğrulamasında bakılacak tezgâhlar: yalnızca kontrol edilen duruşları olanlar → {makine: [iş emri, ...]}."""
    from . import veritabani as vt
    ayar = ayar if ayar is not None else vt.ayar_oku(con)
    d: Dict[str, List[str]] = {}
    for mk, _tip, _a, _b, _op, urun, emri, _u in _adaylar(con, ilk, son, ayar):
        lst = d.setdefault(mk, [])
        k = emri or urun
        if k and k not in lst:
            lst.append(k)
    return d


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
