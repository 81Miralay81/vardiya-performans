"""Vardiya performans hesap motoru (arayüzden bağımsız).

Excel'deki mantığın yeni kuralları:
  * Kayıtlar vardiya sınırlarında (00:00 / 08:00 / 16:00) bölünür; her parça kendi
    gün ve vardiyasına yazılır.
  * %60 (eşik) kuralı her gün, her vardiya için ayrı ayrı uygulanır.
  * Haftalık / aylık değerler, günlük değerlerin ortalamasıdır.
  * Verisi olmayan gün ya da vardiya ortalamaya girmez.
"""
from __future__ import annotations

import bisect

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
    kural: str = "gunluk"       # "gunluk": %60 her gün ayrı | "donem": Excel gibi, dönem ortalamasına göre
    yontem: str = "vardiya"     # ortalama yöntemi (günlük kuralda): "vardiya" | "gun" | "hucre"

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
    ham: Dict[str, Tuple[float, float, float]] = field(default_factory=dict)        # eşiğe bakmadan tüm makineler
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
            gv.ham[m] = (oran, d / net, mo / mola_kap)
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
    # kaydı olduğu halde hiçbir vardiyada eşiği geçemeyen makineler: ham ortalama (çalışma, duruş, mola). Hesaba girmez.
    esik_alti: Dict[str, Tuple[float, float, float]] = field(default_factory=dict)
    bozuk_kayit: int = 0                # hesaba alınmayan bozuk (çakışan) uzun çalışma kaydı sayısı

    def hesap_gunu(self) -> int:
        """En az bir vardiyasıyla ortalamaya giren gün sayısı (tablodaki 'Çalışma Gün')."""
        return len({g for o in self.vardiyalar.values() for g in o.gunler})


def _ort(xs: List[float]) -> Optional[float]:
    return sum(xs) / len(xs) if xs else None


def _donem_kurali(gunluk, gunler: List[date], kayitli_gunler: set, esik: float) -> DonemSonuc:
    """Excel'deki gibi: bir makinenin vardiya ortalaması = dönemdeki toplamı / (net süre x kayıtlı gün sayısı).
    Kaydı olmayan ya da çalışmadığı günler 0 sayılır. Ortalaması eşiği geçen makine dönem boyunca sayılır."""
    gunler = sorted(set(gunler))
    gecerli_gunler = [g for g in gunler if g in kayitli_gunler]
    n = len(gecerli_gunler)
    vardiyalar: Dict[int, VardiyaOzet] = {}
    hucreler: Dict[str, Dict[int, Tuple[float, float, float]]] = {}
    bos: List[Tuple[date, int]] = []
    for v in VARDIYALAR:
        oz = VardiyaOzet(v)
        toplam: Dict[str, List[float]] = {}
        for g in gecerli_gunler:
            gv = gunluk.get((g, v))
            if gv is None:
                continue
            for m, (c, d, mo) in gv.ham.items():
                t = toplam.setdefault(m, [0.0, 0.0, 0.0])
                t[0] += c
                t[1] += d
                t[2] += mo
        gecerli = {}
        for m, t in toplam.items():
            if n and t[0] > 0 and t[0] / n >= esik:
                gecerli[m] = (t[0] / n, t[1] / n, t[2] / n)
        for m, deger in gecerli.items():
            hucreler.setdefault(m, {})[v] = deger
        if gecerli:
            oz.gun_sayisi = n
            oz.gunler = list(gecerli_gunler)
            oz.makine_sayisi = float(len(gecerli))
            c_ort = sum(x[0] for x in gecerli.values()) / len(gecerli)
            oz.calisma = min(1.0, c_ort)
            oz.durus = sum(x[1] for x in gecerli.values()) / len(gecerli)
            oz.mola = sum(x[2] for x in gecerli.values()) / len(gecerli)
            for g in gecerli_gunler:
                gv = gunluk.get((g, v))
                oz.gunluk_sayilar[g] = sum(1 for m in gecerli if gv and m in gv.makineler)
        else:
            bos.extend((g, v) for g in gecerli_gunler)
        vardiyalar[v] = oz
    makine_ort = {}
    for m, vd in hucreler.items():
        c_ort = _ort([x[0] for x in vd.values()])
        makine_ort[m] = (min(1.0, c_ort) if c_ort is not None else None,
                         _ort([x[1] for x in vd.values()]), _ort([x[2] for x in vd.values()]))
    vc = [o.calisma for o in vardiyalar.values() if o.calisma is not None]
    vd_ = [o.durus for o in vardiyalar.values() if o.durus is not None]
    vm = [o.mola for o in vardiyalar.values() if o.mola is not None]
    genel_c = _ort(vc)
    genel = (min(1.0, genel_c) if genel_c is not None else None, _ort(vd_), _ort(vm))
    verisiz = [g for g in gunler if g not in kayitli_gunler]
    return DonemSonuc(gunler, vardiyalar, hucreler, makine_ort, genel, verisiz, bos)


def _esik_alti(gunluk, gunler, kayitli_gunler, sayilan) -> Dict[str, Tuple[float, float, float]]:
    """Seçili günlerde kaydı olup hesaba hiç girmeyen makinelerin ham (eşiksiz) ortalaması."""
    top: Dict[str, List[float]] = {}
    for (g, _v), gv in gunluk.items():
        if g not in kayitli_gunler or g not in gunler:
            continue
        for m, (c, d, mo) in gv.ham.items():
            if m in sayilan or (c + d + mo) <= 0:
                continue
            t = top.setdefault(m, [0.0, 0.0, 0.0, 0])
            t[0] += c; t[1] += d; t[2] += mo; t[3] += 1
    return {m: (t[0] / t[3], t[1] / t[3], t[2] / t[3]) for m, t in top.items() if t[3]}


YONTEMLER = ("vardiya", "gun", "hucre")


def donem_hesapla(gunluk: Dict[Tuple[date, int], GunVardiya], gunler: List[date],
                  veri_gunleri: Optional[set] = None, kural: str = "gunluk", esik: float = 0.60,
                  yontem: str = "vardiya") -> DonemSonuc:
    """veri_gunleri: kaydı o gün başlayan günler. Verilirse, yalnızca önceki günden uzayan kayıtlarla görünen
    günler (tatil, hafta sonu) 'kayıtsız' sayılır."""
    gunler = sorted(set(gunler))
    kayitli_gunler = set(veri_gunleri) if veri_gunleri is not None else {g for (g, _v) in gunluk.keys()}
    if kural == "donem":
        r = _donem_kurali(gunluk, gunler, kayitli_gunler, esik)
        r.esik_alti = _esik_alti(gunluk, set(gunler), kayitli_gunler, set(r.makine_ort))
        return r
    if yontem not in YONTEMLER:
        yontem = "vardiya"
    vardiyalar: Dict[int, VardiyaOzet] = {}
    makine_hucre: Dict[str, Dict[int, List[Tuple[float, float, float]]]] = {}
    makine_gun: Dict[str, Dict[date, List[Tuple[float, float, float]]]] = {}
    gun_ozet: Dict[date, List[Tuple[float, float, float]]] = {}
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
            gun_ozet.setdefault(g, []).append((gv.calisma, gv.durus, gv.mola))
            for m, deger in gv.makineler.items():
                makine_hucre.setdefault(m, {}).setdefault(v, []).append(deger)
                makine_gun.setdefault(m, {}).setdefault(g, []).append(deger)
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
        if yontem == "gun":          # önce her günün (sayılan vardiyalarının) ortalaması, sonra günlerin ortalaması
            parca = [tuple(sum(x[i] for x in l) / len(l) for i in range(3)) for l in makine_gun[m].values()]
        elif yontem == "hucre":      # sayılan bütün vardiyalar eşit ağırlıkla (süre toplamı)
            parca = [x for l in vd.values() for x in l]
        else:                        # önce her vardiyanın ortalaması, sonra üç vardiyanın ortalaması
            parca = list(hucreler[m].values())
        c_ort = _ort([x[0] for x in parca])
        makine_ort[m] = (min(1.0, c_ort) if c_ort is not None else None, _ort([x[1] for x in parca]), _ort([x[2] for x in parca]))

    if yontem == "gun":
        parca = [tuple(sum(x[i] for x in l) / len(l) for i in range(3)) for l in gun_ozet.values()]
    elif yontem == "hucre":
        parca = [x for vd in makine_hucre.values() for l in vd.values() for x in l]
    else:
        parca = [(o.calisma, o.durus, o.mola) for o in vardiyalar.values() if o.calisma is not None]
    genel_c = _ort([x[0] for x in parca])
    genel = (min(1.0, genel_c) if genel_c is not None else None, _ort([x[1] for x in parca]), _ort([x[2] for x in parca]))

    verisiz = [g for g in gunler if g not in kayitli_gunler]
    return DonemSonuc(gunler, vardiyalar, hucreler, makine_ort, genel, verisiz, bos,
                      _esik_alti(gunluk, set(gunler), kayitli_gunler, set(makine_ort)))


# --------------------------------------------------------------------------- kısayol
BOZUK_UZUN_SAAT = 8.0      # bundan uzun bir çalışma kaydı...
BOZUK_CAKISMA_DK = 30.0    # ...aynı makinenin başka kayıtlarıyla bundan fazla çakışıyorsa bozuktur


def bozuk_kayitlari_ayikla(kayitlar) -> Tuple[list, int]:
    kayitlar = list(kayitlar)
    bozuk = bozuk_indeksler(kayitlar)
    if not bozuk:
        return kayitlar, 0
    return [k for i, k in enumerate(kayitlar) if i not in bozuk], len(bozuk)


def bozuk_indeksler(kayitlar) -> set:
    """Bozuk (çakışan) uzun çalışma kayıtlarını ayıklar.
    Cormind'de bir makine aynı anda tek durumdadır. Saatlerce süren bir çalışma kaydı aynı makinenin duruş, mola ya da
    başka çalışma kayıtlarıyla yarım saatten fazla çakışıyorsa (ör. bitişi boş gelip günlerce uzatılmış kayıt) o kayıt
    gerçek değildir. Hesaba alınırsa çakışma çözümünde çalışma öncelikli olduğu için bütün duruşları siler ve makine
    %100 çalışıyor görünür. Bu yüzden atılır; o sürenin gerçek kayıtları yoksa grafik boş kalır."""
    kayitlar = list(kayitlar)
    makineye: Dict[str, list] = {}
    for i, (m, tip, bas, bit) in enumerate(kayitlar):
        makineye.setdefault(m, []).append((bas, bit, i, statu_bul(tip) == CALISIYOR))
    bozuk = set()
    uzun = timedelta(hours=BOZUK_UZUN_SAAT)
    for liste in makineye.values():
        liste.sort(key=lambda r: r[0])
        baslar = [r[0] for r in liste]
        for bas, bit, i, calisma in liste:
            if not calisma or bit - bas <= uzun:
                continue
            cak = 0.0
            for bas2, bit2, j, _c in liste[bisect.bisect_left(baslar, bas - timedelta(days=60)):bisect.bisect_right(baslar, bit)]:
                if j == i or j in bozuk:
                    continue
                o = (min(bit, bit2) - max(bas, bas2)).total_seconds()
                if o > 0:
                    cak += o
                    if cak > BOZUK_CAKISMA_DK * 60:
                        bozuk.add(i)
                        break
    return bozuk


def hesapla(kayitlar, gunler: List[date], ayar: Optional[HesapAyar] = None, veri_gunleri: Optional[set] = None) -> DonemSonuc:
    ayar = ayar or HesapAyar()
    kayitlar, bozuk = bozuk_kayitlari_ayikla(kayitlar)
    gunluk = gunluk_hesapla(topla(kayitlar, ayar), ayar)
    sonuc = donem_hesapla(gunluk, gunler, veri_gunleri, ayar.kural, ayar.esik, ayar.yontem)
    sonuc.bozuk_kayit = bozuk
    return sonuc


def durus_dokumu(kayitlar: Iterable[Tuple[str, str, datetime, datetime]], gunler: Iterable[date]) -> Dict[str, Dict[str, float]]:
    """makine -> duruş türü -> saat. Yalnızca seçili günlere düşen kısım sayılır; mola ve çalışma girmez."""
    gset = set(gunler)
    sonuc: Dict[str, Dict[str, float]] = {}
    for makine, tip, bas, bit in kayitlar:
        if statu_bul(tip) != DURUS:
            continue
        for gun, _v, sn in bol(bas, bit, True):
            if gun in gset and sn > 0:
                m = sonuc.setdefault(makine, {})
                ad = durus_adi(tip, bas, bit)
                m[ad] = m.get(ad, 0.0) + sn / 3600.0
    return sonuc


KAYIT_YOK = "Kayıt Yok"            # uzun olduğu halde "Kısa Duruş" adıyla gelmiş, gerçek adı bilinmeyen kayıt
CALISMIYOR = "Çalışmıyor"          # dönemde hiç kaydı olmayan makine
KISA_DURUS = "Kısa Duruş"
KISA_DURUS_AZAMI_DK = 30.0         # bundan uzun bir kayıt "Kısa Duruş" olamaz (kısa duruş birkaç dakikalık duruştur)


def durus_adi(tip: str, bas: datetime, bit: datetime) -> str:
    """Gösterilecek duruş adı. Uzun bir kayıt hiçbir zaman 'Kısa Duruş' adıyla gösterilmez."""
    ad = tip or "Belirtilmemiş"
    if tr_kucuk(ad) == tr_kucuk(KISA_DURUS) and (bit - bas).total_seconds() / 60.0 > KISA_DURUS_AZAMI_DK:
        return CALISMIYOR                  # nedeni bilinmeyen uzun duruş "Çalışmıyor" sayılır
    return ad


def cormind_hesabi(kayitlar: Iterable[Tuple[str, str, datetime, datetime]], gunler: Iterable[date], makineler: Iterable[str],
                   ayar: Optional[HesapAyar] = None) -> Dict[str, dict]:
    """Cormind'in kendi rapor mantığı (bizim hesaptan bağımsız; eşik ve hesap yöntemi uygulanmaz).

    Temel süre = seçili sürenin net kısmı (her 480 dakikanın 440'ı). Her duruş = dakikası / temel süre.
    'Mola Süresi' = (kaydedilen mola - mola hakkı) / temel süre (mola girilmediyse eksi çıkar).
    Toplam = duruşlar + mola süresi;  OEE = 100 - toplam (0 ile 100 arasında).
    Çalışma kayıtları hiç toplanmaz: kaydı olmayan süre çalışılmış sayılır.
    Dönemde HİÇ kaydı olmayan makine çalışmamış sayılır: tamamı 'Çalışmıyor' duruşu, OEE 0.
    Dönen değerler yüzde (0-100 ölçeğinde)."""
    ayar = ayar or HesapAyar()
    gset = set(gunler)
    sure_dk = len(gset) * 1440.0
    net_dk = sure_dk * (ayar.net_saat * 60.0) / ayar.vardiya_dk
    hak_dk = sure_dk * (ayar.mola_saat * 60.0) / ayar.vardiya_dk
    durus: Dict[str, Dict[str, float]] = {}
    mola: Dict[str, float] = {}
    gorulen: set = set()                       # dönemde herhangi bir kaydı (çalışma dahil) olan makineler
    for makine, tip, bas, bit in kayitlar:
        st = statu_bul(tip)
        dk = sum(sn for gun, _v, sn in bol(bas, bit, True) if gun in gset) / 60.0
        if dk <= 0:
            continue
        gorulen.add(makine)
        if st == CALISIYOR:
            continue
        if st == MOLA:
            mola[makine] = mola.get(makine, 0.0) + dk
        else:
            d = durus.setdefault(makine, {})
            ad = durus_adi(tip, bas, bit)
            d[ad] = d.get(ad, 0.0) + dk
    sirali = list(makineler) + sorted(m for m in set(durus) | set(mola) if m not in set(makineler))
    sonuc: Dict[str, dict] = {}
    if net_dk <= 0:
        return sonuc
    for m in sirali:
        d = {t: 100.0 * dk / net_dk for t, dk in durus.get(m, {}).items()}
        mo = 100.0 * (mola.get(m, 0.0) - hak_dk) / net_dk
        if m not in gorulen:                   # hiç kaydı yok: çalışmadı (Cormind'deki %109 duruş + eksi %9 mola görünümü)
            d = {CALISMIYOR: 100.0 * sure_dk / net_dk}
        toplam = sum(d.values()) + mo
        sonuc[m] = {"durus": d, "mola": mo, "toplam": toplam, "oee": max(0.0, min(100.0, 100.0 - toplam))}
    return sonuc
