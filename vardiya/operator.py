"""Operatör analizi (arayüzden bağımsız).

Her operatör için, kayıtlardaki makinelerinde geçirdiği süre incelenir:
  * Çalışma / duruş / mola oranı: operatörün çalıştığı her (gün, vardiya, makine) parçası için net süre (7,33 saat)
    esas alınır; operatör o makinede vardiyanın yalnızca bir kısmında kayıtlıysa payı o oranda küçülür.
    Oran önce her gün için ayrı hesaplanır, dönem değeri günlerin ortalamasıdır (toplam süre bölünmez).
  * Çakışan duruş: operatörün aynı anda en az iki makinesinin duruşta olduğu süre (duvar saati).
    Üç makineden biri duruyor, ikisi çalışıyorsa çakışma sayılmaz.
  * Ayar (setup) kaybı: operatör bir makinede SETUP / Kurulum duruşundayken, öbür makinelerinde biriken duruş (makine-saniye).
  * Hepsi çalışırken: operatörün molada olmayan tüm makineleri aynı anda çalışıyorken geçen süre.
Mola kaydındaki makineler o anda "aktif" sayılmaz (operatör molada).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from .hesap import CALISIYOR, DURUS, MOLA, HesapAyar, statu_bul, tr_kucuk

_ONCELIK = {CALISIYOR: 0, MOLA: 1, DURUS: 2}
VARDIYA_SN = 8 * 3600


def operator_adi(s: Optional[str]) -> str:
    """Boşlukları düzeltir; harf içermeyen adlar ('-' gibi) operatör sayılmaz."""
    ad = " ".join((s or "").split())
    return ad if any(c.isalpha() for c in ad) else ""


PLANSIZ = tr_kucuk("İŞ EMRİ PLAN YOK")


def plansiz_mi(tip: str) -> bool:
    return PLANSIZ in tr_kucuk(tip)


def setup_mi(tip: str) -> bool:
    t = tr_kucuk(tip)
    return "setup" in t or "kurulum" in t


def _vardiya_parcala(bas: datetime, bit: datetime):
    """[bas, bit) aralığını 00:00 / 08:00 / 16:00 sınırlarında böler -> (başlangıç, bitiş, gün, vardiya)."""
    cur = bas
    while cur < bit:
        v = 1 if cur.hour < 8 else (2 if cur.hour < 16 else 3)
        sinir_saat = {1: 8, 2: 16, 3: 24}[v]
        sinir = datetime(cur.year, cur.month, cur.day) + timedelta(hours=sinir_saat)
        son = min(bit, sinir)
        yield cur, son, cur.date(), v
        cur = son


@dataclass
class Episode:
    bas: datetime
    bit: datetime
    duruslar: Tuple[Tuple[str, str], ...]      # (makine, tip) duruşta olanlar
    calisanlar: Tuple[str, ...]
    setup_var: bool

    @property
    def sn(self) -> float:
        return (self.bit - self.bas).total_seconds()


@dataclass
class OperatorSonuc:
    ad: str
    makineler: Dict[str, Dict[str, float]] = field(default_factory=dict)   # makine -> {calisma, durus, mola} saniye
    gunler: Dict[date, Dict[str, float]] = field(default_factory=dict)     # gün -> {calisma, durus, mola oranları, makine}
    calisma_orani: Optional[float] = None
    durus_orani: Optional[float] = None
    mola_orani: Optional[float] = None
    calisma_sn: float = 0.0
    durus_sn: float = 0.0
    mola_sn: float = 0.0
    cakisan_sn: float = 0.0
    setup_sn: float = 0.0               # setup duruşunda geçen toplam (makine-saniye)
    setup_kayip_sn: float = 0.0         # setup sırasında diğer makinelerdeki duruş (makine-saniye)
    hepsi_calisirken_sn: float = 0.0   # "boşta": tüm makineleri çalışıyor, operatörün yapacak işi yok
    aktif_sn: float = 0.0              # en az bir makinesinin çalışıp/durduğu (molada olmadığı) süre
    bosta_listesi: List["Episode"] = field(default_factory=list)
    plansiz_sn: float = 0.0            # "İŞ EMRİ PLAN YOK" duruşunda, operatör makinede tanımlıyken geçen süre
    plansiz_listesi: List["Episode"] = field(default_factory=list)
    belgesiz_sn: float = 0.0            # "Belgelenmemiş Duruş"
    en_uzun_durus_sn: float = 0.0
    durus_adedi: int = 0
    mola_asimi_sn: float = 0.0
    ort_makine: float = 0.0             # aynı anda ortalama aktif makine
    durus_tipleri: Dict[str, float] = field(default_factory=dict)
    cakismalar: List[Episode] = field(default_factory=list)
    gun_sayisi: int = 0

    @property
    def makine_sayisi(self) -> int:
        return len(self.makineler)

    @property
    def bosta_orani(self) -> Optional[float]:
        return self.hepsi_calisirken_sn / self.aktif_sn if self.aktif_sn else None


def _makine_parcalari(kayitlar: List[Tuple[str, datetime, datetime]]):
    """Tek makinenin kayıtlarında çakışmayı çözer -> [(t0, t1, durum, tip)] (Çalışma > Mola > Duruş)."""
    liste = sorted((r for r in kayitlar if r[2] > r[1]), key=lambda r: r[1])
    zaman = sorted({r[1] for r in liste} | {r[2] for r in liste})
    aktif, i, cikti = [], 0, []
    for k in range(len(zaman) - 1):
        t0, t1 = zaman[k], zaman[k + 1]
        while i < len(liste) and liste[i][1] <= t0:
            aktif.append(liste[i])
            i += 1
        aktif = [r for r in aktif if r[2] > t0]
        if aktif:
            en = min(aktif, key=lambda r: _ONCELIK[statu_bul(r[0])])
            durum, tip = statu_bul(en[0]), en[0]
            if cikti and cikti[-1][1] == t0 and cikti[-1][2] == durum and cikti[-1][3] == tip:
                cikti[-1] = (cikti[-1][0], t1, durum, tip)
            else:
                cikti.append((t0, t1, durum, tip))
    return cikti


def _bir_operator(ad: str, kayitlar: List[Tuple[str, str, datetime, datetime]], gunler: set, ayar: HesapAyar,
                  vardiyalar: Optional[set] = None) -> OperatorSonuc:
    sonuc = OperatorSonuc(ad)
    net_sn, mola_kap = ayar.net_saat * 3600.0, ayar.mola_saat * 3600.0
    makineye: Dict[str, list] = {}
    for makine, tip, bas, bit in kayitlar:
        makineye.setdefault(makine, []).append((tip, bas, bit))

    # makine başına ayrık parçalar; gün/vardiya sınırında bölünüp seçili günlerle sınırlanır
    parcalar: Dict[str, list] = {}
    for makine, liste in makineye.items():
        kes = []
        for t0, t1, durum, tip in _makine_parcalari(liste):
            for a, b, gun, v in _vardiya_parcala(t0, t1):
                if gun in gunler and (vardiyalar is None or v in vardiyalar):
                    kes.append((a, b, durum, tip, gun, v))
        if kes:
            parcalar[makine] = kes
    if not parcalar:
        return sonuc

    # (gün, vardiya, makine) birimleri
    birim: Dict[Tuple[date, int, str], Dict[str, float]] = {}
    for makine, kes in parcalar.items():
        mk = sonuc.makineler.setdefault(makine, {"calisma": 0.0, "durus": 0.0, "mola": 0.0})
        onceki = None
        for a, b, durum, tip, gun, v in kes:
            sn = (b - a).total_seconds()
            u = birim.setdefault((gun, v, makine), {"kayit": 0.0, "calisma": 0.0, "durus": 0.0, "mola": 0.0})
            u["kayit"] += sn
            anahtar = {CALISIYOR: "calisma", DURUS: "durus", MOLA: "mola"}[durum]
            u[anahtar] += sn
            mk[anahtar] += sn
            if durum == DURUS:
                sonuc.durus_tipleri[tip] = sonuc.durus_tipleri.get(tip, 0.0) + sn
                if tr_kucuk(tip) == tr_kucuk("Belgelenmemiş Duruş"):
                    sonuc.belgesiz_sn += sn
                if setup_mi(tip):
                    sonuc.setup_sn += sn
                if plansiz_mi(tip):
                    sonuc.plansiz_sn += sn
                    son = sonuc.plansiz_listesi[-1] if sonuc.plansiz_listesi else None
                    if son and son.duruslar[0][0] == makine and son.bit == a:
                        son.bit = b
                    else:
                        sonuc.plansiz_listesi.append(Episode(a, b, ((makine, tip),), (), False))
                # ardışık parçalar (vardiya sınırında bölünmüş) tek duruş sayılır
                if onceki and onceki[0] == tip and onceki[1] == a:
                    onceki = (tip, b, onceki[2] + sn)
                else:
                    sonuc.durus_adedi += 1
                    onceki = (tip, b, sn)
                sonuc.en_uzun_durus_sn = max(sonuc.en_uzun_durus_sn, onceki[2])
            else:
                onceki = None
    sonuc.calisma_sn = sum(m["calisma"] for m in sonuc.makineler.values())
    sonuc.durus_sn = sum(m["durus"] for m in sonuc.makineler.values())
    sonuc.mola_sn = sum(m["mola"] for m in sonuc.makineler.values())

    # günlük oranlar: önce her gün ayrı, sonra günlerin ortalaması
    gun_toplam: Dict[date, List[float]] = {}
    for (gun, v, makine), u in birim.items():
        pay = min(1.0, u["kayit"] / VARDIYA_SN)
        if pay <= 0:
            continue
        g = gun_toplam.setdefault(gun, [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        g[0] += u["calisma"]; g[1] += u["durus"]; g[2] += u["mola"]
        g[3] += net_sn * pay; g[4] += mola_kap * pay
        g[5] += 1
        sonuc.mola_asimi_sn += max(0.0, u["mola"] - mola_kap)
    cs, ds, ms = [], [], []
    for gun, g in sorted(gun_toplam.items()):
        c, d, m = g[0] / g[3], g[1] / g[3], (g[2] / g[4] if g[4] else 0.0)
        sonuc.gunler[gun] = {"calisma": c, "durus": d, "mola": m, "birim": g[5]}
        cs.append(c); ds.append(d); ms.append(m)
    sonuc.gun_sayisi = len(gun_toplam)
    sonuc.calisma_orani = min(1.0, sum(cs) / len(cs))
    sonuc.durus_orani = sum(ds) / len(ds)
    sonuc.mola_orani = sum(ms) / len(ms)

    # --- aynı anda süpürme: makineler arası çakışma, setup kaybı, hepsi çalışırken
    sinirlar = sorted({p[0] for k in parcalar.values() for p in k} | {p[1] for k in parcalar.values() for p in k})
    imlec = {m: 0 for m in parcalar}
    onceki_ep: Optional[Episode] = None
    onceki_bosta: Optional[Episode] = None
    gun_ek: Dict[date, Dict[str, float]] = {}
    agirlik = toplam_agirlik = 0.0
    for i in range(len(sinirlar) - 1):
        t0, t1 = sinirlar[i], sinirlar[i + 1]
        sn = (t1 - t0).total_seconds()
        calisan, duran = [], []
        for m, kes in parcalar.items():
            j = imlec[m]
            while j < len(kes) and kes[j][1] <= t0:
                j += 1
            imlec[m] = j
            if j < len(kes) and kes[j][0] <= t0 < kes[j][1]:
                durum, tip = kes[j][2], kes[j][3]
                if durum == CALISIYOR:
                    calisan.append(m)
                elif durum == DURUS:
                    duran.append((m, tip))
        n_aktif = len(calisan) + len(duran)
        ek = gun_ek.setdefault(t0.date(), {"bosta_sn": 0.0, "cakisan_sn": 0.0})
        if n_aktif:
            agirlik += n_aktif * sn
            toplam_agirlik += sn
            sonuc.aktif_sn += sn
            if not duran:
                sonuc.hepsi_calisirken_sn += sn
                ek["bosta_sn"] += sn
                if onceki_bosta and onceki_bosta.bit == t0:
                    onceki_bosta.bit = t1
                    onceki_bosta.calisanlar = tuple(sorted(set(onceki_bosta.calisanlar) | set(calisan)))
                else:
                    onceki_bosta = Episode(t0, t1, (), tuple(sorted(calisan)), False)
                    sonuc.bosta_listesi.append(onceki_bosta)
            else:
                onceki_bosta = None
        else:
            onceki_bosta = None
        setup_say = sum(1 for _, tip in duran if setup_mi(tip))
        if setup_say:
            sonuc.setup_kayip_sn += (len(duran) - setup_say) * sn
        if len(duran) >= 2:
            sonuc.cakisan_sn += sn
            ek["cakisan_sn"] += sn
            anahtar = tuple(sorted(duran))
            if onceki_ep and onceki_ep.bit == t0 and onceki_ep.duruslar == anahtar:
                onceki_ep.bit = t1
                onceki_ep.calisanlar = tuple(sorted(set(onceki_ep.calisanlar) | set(calisan)))
            else:
                onceki_ep = Episode(t0, t1, anahtar, tuple(sorted(calisan)), bool(setup_say))
                sonuc.cakismalar.append(onceki_ep)
        else:
            onceki_ep = None
    sonuc.ort_makine = agirlik / toplam_agirlik if toplam_agirlik else 0.0
    for gun, ek in gun_ek.items():
        if gun in sonuc.gunler:
            sonuc.gunler[gun].update(ek)
    return sonuc


def operatorleri_hesapla(kayitlar: Iterable[Tuple[str, str, str, datetime, datetime]], gunler: List[date],
                         ayar: Optional[HesapAyar] = None, vardiyalar: Optional[set] = None) -> Dict[str, OperatorSonuc]:
    """kayitlar: (operatör, makine, tip, başlangıç, bitiş). Operatörü boş kayıtlar atlanır."""
    ayar = ayar or HesapAyar()
    gruplar: Dict[str, list] = {}
    for op, makine, tip, bas, bit in kayitlar:
        ad = operator_adi(op)
        if ad:
            gruplar.setdefault(ad, []).append((makine, tip, bas, bit))
    gset = set(gunler)
    sonuc = {}
    for ad, liste in gruplar.items():
        r = _bir_operator(ad, liste, gset, ayar, vardiyalar)
        if r.makineler:
            sonuc[ad] = r
    return sonuc
