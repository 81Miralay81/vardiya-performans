"""Vardiya performans hesap motoru (arayüzden bağımsız).

Excel'deki mantığın yeni kuralları:
  * Kayıtlar vardiya sınırlarında (00:00 / 08:00 / 16:00) bölünür; her parça kendi
    gün ve vardiyasına yazılır.
  * %60 (eşik) kuralı her gün, her vardiya için ayrı ayrı uygulanır.
  * Haftalık / aylık değerler, günlük değerlerin ortalamasıdır.
  * Verisi olmayan gün ya da vardiya ortalamaya girmez.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

VARDIYALAR = (1, 2, 3)
VARDIYA_ADI = {1: "1.Vardiya", 2: "2.Vardiya", 3: "3.Vardiya"}

CALISIYOR, DURUS, MOLA = "Çalışıyor", "Duruş", "Mola"


# --------------------------------------------------------------------------- yardımcılar
def tr_kucuk(s: str) -> str:
    """Türkçe'ye uygun küçük harf (İ/I sorunu olmadan karşılaştırma için)."""
    return (s or "").replace("İ", "i").replace("I", "ı").lower().strip()


_MOLA_TIPLERI = {tr_kucuk("ÇAY MOLASI"), tr_kucuk("YEMEK MOLASI")}
_CALISMA = tr_kucuk("Çalışma")


def statu_bul(tip: str) -> str:
    """Excel K sütunu: Çalışma -> Çalışıyor, çay/yemek molası -> Mola, kalan her şey -> Duruş."""
    t = tr_kucuk(tip)
    if t == _CALISMA:
        return CALISIYOR
    if t in _MOLA_TIPLERI:
        return MOLA
    return DURUS


def vardiya_bul(saat: int) -> int:
    """00-07 -> 1, 08-15 -> 2, 16-23 -> 3 (Excel J sütunuyla aynı)."""
    return 1 if saat < 8 else (2 if saat < 16 else 3)


def bol(baslangic: datetime, bitis: datetime, bolme: bool = True) -> List[Tuple[date, int, float]]:
    """Bir kaydı (gün, vardiya, saniye) parçalarına ayırır.

    bolme=False: Excel'deki gibi tamamı başladığı gün/vardiyaya yazılır (karşılaştırma testi için).
    """
    if bitis <= baslangic:
        return [(baslangic.date(), vardiya_bul(baslangic.hour), 0.0)]
    if not bolme:
        return [(baslangic.date(), vardiya_bul(baslangic.hour), (bitis - baslangic).total_seconds())]
    parcalar = []
    cur = baslangic
    while cur < bitis:
        h = cur.hour
        if h < 8:
            sonraki = cur.replace(hour=8, minute=0, second=0, microsecond=0)
            v = 1
        elif h < 16:
            sonraki = cur.replace(hour=16, minute=0, second=0, microsecond=0)
            v = 2
        else:
            sonraki = (cur + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            v = 3
        son = min(sonraki, bitis)
        parcalar.append((cur.date(), v, (son - cur).total_seconds()))
        cur = son
    return parcalar


# --------------------------------------------------------------------------- ayarlar
@dataclass
class HesapAyar:
    esik: float = 0.60          # %60 kuralı
    vardiya_dk: int = 480       # vardiya uzunluğu
    yemek_dk: int = 30          # günde bir kez, her vardiyada
    cay_dk: int = 10
    bolme: bool = True          # kayıtları vardiya sınırlarında böl
    cakisma_coz: bool = True    # aynı anda birden fazla kayıt varsa bir kez say (Çalışma > Mola > Duruş)
    net_saat_zorla: Optional[float] = None   # yalnızca testlerde (örn. Excel'deki 7,33)

    @property
    def net_saat(self) -> float:
        if self.net_saat_zorla is not None:
            return self.net_saat_zorla
        return (self.vardiya_dk - self.yemek_dk - self.cay_dk) / 60.0

    @property
    def mola_saat(self) -> float:
        return (self.yemek_dk + self.cay_dk) / 60.0


# --------------------------------------------------------------------------- günlük toplama
# (gün, vardiya) -> makine -> [çalışma_saat, duruş_saat, mola_saat]
Toplam = Dict[Tuple[date, int], Dict[str, List[float]]]


_ONCELIK = {0: 0, 2: 1, 1: 2}   # çalışma > mola > duruş


def _supurge(satirlar):
    """Bir makinenin kayıtlarında çakışmayı çözer: her an için en öncelikli tek kayıt kalır.
    satirlar: (başlangıç, bitiş, idx) -> [(t0, t1, idx), ...]"""
    satirlar = sorted((r for r in satirlar if r[1] > r[0]), key=lambda r: r[0])
    zaman = sorted({r[0] for r in satirlar} | {r[1] for r in satirlar})
    aktif, i, cikti = [], 0, []
    for k in range(len(zaman) - 1):
        t0, t1 = zaman[k], zaman[k + 1]
        while i < len(satirlar) and satirlar[i][0] <= t0:
            aktif.append(satirlar[i])
            i += 1
        aktif = [r for r in aktif if r[1] > t0]
        if aktif:
            en = min(aktif, key=lambda r: _ONCELIK[r[2]])
            cikti.append((t0, t1, en[2]))
    return cikti


def topla(kayitlar: Iterable[Tuple[str, str, datetime, datetime]], ayar: HesapAyar) -> Toplam:
    """kayitlar: (makine, tip, başlangıç, bitiş)"""
    sonuc: Toplam = {}
    idx = {CALISIYOR: 0, DURUS: 1, MOLA: 2}

    def ekle(makine, i, bas, bit, bolme):
        for gun, v, sn in bol(bas, bit, bolme):
            m = sonuc.setdefault((gun, v), {}).setdefault(makine, [0.0, 0.0, 0.0])
            m[i] += sn / 3600.0

    if not ayar.cakisma_coz:                       # Excel usulü: her kayıt olduğu gibi toplanır
        for makine, tip, bas, bit in kayitlar:
            ekle(makine, idx[statu_bul(tip)], bas, bit, ayar.bolme)
        return sonuc

    makineye = {}
    for makine, tip, bas, bit in kayitlar:
        i = idx[statu_bul(tip)]
        if bit <= bas:                             # süresiz kayıt: yalnızca "bu vardiyada veri var" işareti
            sonuc.setdefault((bas.date(), vardiya_bul(bas.hour)), {}).setdefault(makine, [0.0, 0.0, 0.0])
        else:
            makineye.setdefault(makine, []).append((bas, bit, i))
    for makine, liste in makineye.items():
        for t0, t1, i in _supurge(liste):
            ekle(makine, i, t0, t1, ayar.bolme)
    return sonuc


# --------------------------------------------------------------------------- günlük sonuç
@dataclass
class GunVardiya:
    gun: date
    vardiya: int
    makineler: Dict[str, Tuple[float, float, float]] = field(default_factory=dict)  # geçerli makineler: çalışma%, duruş%, mola%
    sayi: int = 0
    calisma: Optional[float] = None   # vardiya ortalaması (en çok %100)
    durus: Optional[float] = None
    mola: Optional[float] = None


def gunluk_hesapla(toplam: Toplam, ayar: HesapAyar) -> Dict[Tuple[date, int], GunVardiya]:
    net, mola_kap = ayar.net_saat, ayar.mola_saat
    sonuc = {}
    for (gun, v), makineler in toplam.items():
        gv = GunVardiya(gun, v)
        for m, (c, d, mo) in makineler.items():
            oran = c / net
            if c > 0 and oran >= ayar.esik:
                gv.makineler[m] = (oran, d / net, mo / mola_kap)
        gv.sayi = len(gv.makineler)
        if gv.sayi:
            ort = sum(x[0] for x in gv.makineler.values()) / gv.sayi
            gv.calisma = min(1.0, ort)
            gv.durus = sum(x[1] for x in gv.makineler.values()) / gv.sayi
            gv.mola = sum(x[2] for x in gv.makineler.values()) / gv.sayi
        sonuc[(gun, v)] = gv
    return sonuc


# --------------------------------------------------------------------------- dönem sonucu
@dataclass
class VardiyaOzet:
    vardiya: int
    gun_sayisi: int = 0                 # ortalamaya giren gün sayısı
    makine_sayisi: Optional[float] = None
    calisma: Optional[float] = None
    durus: Optional[float] = None
    mola: Optional[float] = None
    gunler: List[date] = field(default_factory=list)
    gunluk_sayilar: Dict[date, int] = field(default_factory=dict)


@dataclass
class DonemSonuc:
    gunler: List[date]
    vardiyalar: Dict[int, VardiyaOzet]
    # makine -> vardiya -> (çalışma, duruş, mola) ; yalnızca geçerli günleri olan hücreler
    hucreler: Dict[str, Dict[int, Tuple[float, float, float]]]
    makine_ort: Dict[str, Tuple[Optional[float], Optional[float], Optional[float]]]
    genel: Tuple[Optional[float], Optional[float], Optional[float]]
    verisiz_gunler: List[date]          # seçilen aralıkta hiç kaydı olmayan günler
    bos_vardiyalar: List[Tuple[date, int]]  # kaydı olup hiçbir makinenin eşiği geçemediği / kaydı olmayan vardiyalar

    def hesap_gunu(self) -> int:
        """En az bir vardiyasıyla ortalamaya giren gün sayısı (tablodaki 'Çalışma Gün')."""
        return len({g for o in self.vardiyalar.values() for g in o.gunler})


def _ort(xs: List[float]) -> Optional[float]:
    return sum(xs) / len(xs) if xs else None


def donem_hesapla(gunluk: Dict[Tuple[date, int], GunVardiya], gunler: List[date],
                  veri_gunleri: Optional[set] = None) -> DonemSonuc:
    """veri_gunleri: kaydı o gün başlayan günler. Verilirse, yalnızca önceki günden uzayan kayıtlarla görünen
    günler (tatil, hafta sonu) 'kayıtsız' sayılır."""
    gunler = sorted(set(gunler))
    kayitli_gunler = set(veri_gunleri) if veri_gunleri is not None else {g for (g, _v) in gunluk.keys()}
    vardiyalar: Dict[int, VardiyaOzet] = {}
    makine_hucre: Dict[str, Dict[int, List[Tuple[float, float, float]]]] = {}
    bos: List[Tuple[date, int]] = []

    for v in VARDIYALAR:
        oz = VardiyaOzet(v)
        c, d, mo, s = [], [], [], []
        for g in gunler:
            if g not in kayitli_gunler:
                continue                    # hiç kaydı olmayan gün (tatil vb.): ayrıca "verisiz" olarak bildirilir
            gv = gunluk.get((g, v))
            if gv is None or gv.sayi == 0:
                bos.append((g, v))
                continue
            oz.gunler.append(g)
            oz.gunluk_sayilar[g] = gv.sayi
            c.append(gv.calisma)
            d.append(gv.durus)
            mo.append(gv.mola)
            s.append(gv.sayi)
            for m, deger in gv.makineler.items():
                makine_hucre.setdefault(m, {}).setdefault(v, []).append(deger)
        oz.gun_sayisi = len(c)
        oz.calisma, oz.durus, oz.mola = _ort(c), _ort(d), _ort(mo)
        oz.makine_sayisi = _ort(s)
        vardiyalar[v] = oz

    hucreler: Dict[str, Dict[int, Tuple[float, float, float]]] = {}
    makine_ort = {}
    for m, vd in makine_hucre.items():
        hucreler[m] = {}
        for v, liste in vd.items():
            hucreler[m][v] = (
                sum(x[0] for x in liste) / len(liste),
                sum(x[1] for x in liste) / len(liste),
                sum(x[2] for x in liste) / len(liste),
            )
        cs = [x[0] for x in hucreler[m].values()]
        ds = [x[1] for x in hucreler[m].values()]
        ms = [x[2] for x in hucreler[m].values()]
        c_ort = _ort(cs)
        makine_ort[m] = (min(1.0, c_ort) if c_ort is not None else None, _ort(ds), _ort(ms))

    vc = [o.calisma for o in vardiyalar.values() if o.calisma is not None]
    vd_ = [o.durus for o in vardiyalar.values() if o.durus is not None]
    vm = [o.mola for o in vardiyalar.values() if o.mola is not None]
    genel_c = _ort(vc)
    genel = (min(1.0, genel_c) if genel_c is not None else None, _ort(vd_), _ort(vm))

    verisiz = [g for g in gunler if g not in kayitli_gunler]
    return DonemSonuc(gunler, vardiyalar, hucreler, makine_ort, genel, verisiz, bos)


# --------------------------------------------------------------------------- kısayol
def hesapla(kayitlar, gunler: List[date], ayar: Optional[HesapAyar] = None, veri_gunleri: Optional[set] = None) -> DonemSonuc:
    ayar = ayar or HesapAyar()
    gunluk = gunluk_hesapla(topla(kayitlar, ayar), ayar)
    return donem_hesapla(gunluk, gunler, veri_gunleri)
