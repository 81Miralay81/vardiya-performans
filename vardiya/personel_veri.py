"""Personel veri: giriş-çıkış sisteminin sayfasının getirdiği yanıtlardan yalnızca gerekli bilgiler ayıklanır ve ortak veri
tabanına yazılır; personel devam hesapları (gelme-gelmeme, geç gelme, erken çıkma, fazla çalışma, izin) buradan yapılır.

Saklanan: kişi (sicil, ad, pozisyon, yaka, bölüm, vardiya düzeni, işe giriş, cep telefonu, fotoğraf), gün gün plan ve
gerçek giriş-çıkış, izin türleri, yıllık izin bakiyesi. Saklanmayan: adres, e-posta, doğum tarihi, kan grubu, kart no,
yetkiler, giriş kayıt izleme, oturum ve anahtar bilgileri, firmanın tüm personel listesi. Tanınmayan yanıt hiç yazılmaz.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

BICIM = "%Y-%m-%d %H:%M:%S"
GUN_ANAHTAR = re.compile(r"^y(\d{4})x(\d{2})x(\d{2})$")
SAAT_ARALIK = re.compile(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})")
FARK = re.compile(r"(-?\d+)U(-?\d+)")
GRUP_LIDERI = "GRUP LİDERİ"

VARSAYILAN_TOLERANS_DK = 5           # geç gelme / erken çıkma toleransı (Ayarlar)
VARSAYILAN_FAZLA_EN_AZ_DK = 30       # vardiya bitişinden sonra en az bu kadar kalınırsa fazla çalışma sayılır (Ayarlar)

SEMA = """
CREATE TABLE IF NOT EXISTS pv_personel (
    sicilid INTEGER PRIMARY KEY, sicilno TEXT, ad TEXT, pozisyon TEXT, yaka TEXT, bolum TEXT, periyot TEXT,
    giris_tarih TEXT, telefon TEXT, foto TEXT, guncel TEXT);
CREATE TABLE IF NOT EXISTS pv_gun (
    sicilid INTEGER NOT NULL, gun TEXT NOT NULL, plan TEXT, plan_kod TEXT, izin_kod TEXT, giris TEXT, cikis TEXT,
    g_dk INTEGER, e_dk INTEGER, renk TEXT, gercek INTEGER NOT NULL DEFAULT 0, guncel TEXT,
    PRIMARY KEY (sicilid, gun)) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS pv_gun_gun ON pv_gun(gun);
CREATE TABLE IF NOT EXISTS pv_izin_tur (kod TEXT NOT NULL, ad TEXT NOT NULL, saatlik INTEGER, ucretli INTEGER,
    PRIMARY KEY (kod, ad)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS pv_bakiye (
    sicilid INTEGER PRIMARY KEY, yil INTEGER, hak REAL, kullanilan REAL, planlanan REAL, devir REAL, kalan REAL,
    kidem INTEGER, giris_tarih TEXT, guncel TEXT);
"""

# Sistemin izin türleri listesi gelmeden önce de anlamlı ad gösterilsin diye (liste gelince veri tabanındaki geçer)
BILINEN_IZINLER = {"01": "Yıllık izin / Raporlu ödenmeyen", "02": "Ücretli izin", "04": "Babalık izni", "05": "Ölüm izni",
                   "06": "Evlilik izni", "07": "Raporlu ödenen", "09": "Habersiz gelmeme", "13": "Görev izni", "14": "Süt izni",
                   "15": "Vizite izni", "16": "Özel gereksinimli çocuk izni", "17": "Sünnet izni",
                   "19": "Doğum sonrası ücretsiz izin", "21": "Ücretsiz izin", "CUMA": "Cuma izni"}


def kur(con) -> None:
    con.executescript(SEMA)


def _simdi() -> str:
    return datetime.now().strftime(BICIM)


# ====================================================================== hücre çözümleme
@dataclass
class Hucre:
    plan: str = ""
    plan_kod: str = ""
    izin_kod: str = ""
    giris: str = ""
    cikis: str = ""
    g_dk: Optional[int] = None         # giriş - plan başlangıç (eksi: erken geldi)
    e_dk: Optional[int] = None         # plan bitiş - çıkış (eksi: geç çıktı / fazla kaldı)
    renk: str = ""
    gercek: bool = False               # Planlanan + Gerçekleşen görünümünden mi


def _saat(s: str) -> str:
    s = (s or "").strip()
    return s if re.fullmatch(r"\d{1,2}:\d{2}", s) else ""


def hucre_coz(deger) -> Optional[Hucre]:
    """Pivot hücresi: '08:00-16:00<br>0800-1600 21<br>07:43 13:18<br>…<br>-17U162,green,0_2_59' (gerçekleşen) ya da
    '?BY 08:00-18:00,white,-55_2_59' (yalnızca planlanan). Boş / sayı hücreleri None."""
    if not isinstance(deger, str) or not deger.strip():
        return None
    s = deger.strip()
    if "<br>" in s:
        p = s.split("<br>")
        kuyruk = p[-1].split(",")
        h = Hucre(plan=p[0].lstrip("?").strip(), gercek=True)
        kodlar = p[1].split() if len(p) > 1 else []
        h.plan_kod = kodlar[0] if kodlar else ""
        h.izin_kod = kodlar[1] if len(kodlar) > 1 else ""
        if len(p) > 2:
            sa = p[2].split()
            h.giris = _saat(sa[0]) if sa else ""
            h.cikis = _saat(sa[1]) if len(sa) > 1 else ""
        m = FARK.search(kuyruk[0]) if kuyruk else None
        if m:
            h.g_dk, h.e_dk = int(m.group(1)), int(m.group(2))
        h.renk = kuyruk[1].strip() if len(kuyruk) > 1 else ""
        return h
    parca = s.split(",")
    return Hucre(plan=parca[0].lstrip("?").strip(), renk=parca[1].strip() if len(parca) > 1 else "")


def plan_bilgi(plan: str) -> Tuple[str, Optional[Tuple[int, int]], Optional[Tuple[int, int]]]:
    """('1'|'2'|'3'|'G'|'D'|'T', başlangıç (sa,dk), bitiş). T: hafta tatili / cumartesi (çalışma günü değil)."""
    p = (plan or "").replace("(CUMA)", "").strip()
    pk = p.lower()
    if "tatil" in pk or "cumartesi" in pk:
        return "T", None, None
    m = SAAT_ARALIK.search(p)
    if not m:
        return "D", None, None
    a, b = (int(m.group(1)), int(m.group(2))), (int(m.group(3)), int(m.group(4)))
    tur = {(8, 16): "1", (16, 24): "2", (16, 0): "2", (24, 8): "3", (0, 8): "3", (8, 18): "G"}.get((a[0], b[0]), "D")
    return tur, a, b


VARDIYA_AD = {"1": "1. vardiya 08–16", "2": "2. vardiya 16–24", "3": "3. vardiya 24–08", "G": "Gündüz 08–18", "D": "Diğer"}


def plan_kisa(plan: str) -> str:
    p = (plan or "").replace("(CUMA)", "").strip()
    m = SAAT_ARALIK.search(p)
    if m and "tatil" not in p.lower():
        return f"{int(m.group(1)):02d}–{int(m.group(3)):02d}"
    if "tatil" in p.lower():
        return "HT"
    if "cumartesi" in p.lower():
        return "Cmt"
    return p[:10]


# ====================================================================== yanıtları tanıma ve kaydetme
def _liste(metin: str):
    try:
        v = json.loads(metin)
    except (ValueError, TypeError):
        return None
    return v if isinstance(v, list) and v and isinstance(v[0], dict) else None


def isle(con, metin: str) -> Optional[str]:
    """Sistem yanıtını tanır ve yalnızca gerekli alanları kaydeder. Dönüş: kısa açıklama (tanınmadıysa None)."""
    v = _liste(metin)
    if v is None:
        return None
    k = v[0]
    kur(con)
    if "ysicilid" in k and any(GUN_ANAHTAR.match(a) for a in k):
        kisi = [r for r in v if not str(r.get("ysicilid", "")).startswith("m")]
        return _tapivot(con, kisi) if kisi else None
    if "kod" in k and "ad" in k and "saatlikizin" in k:
        return _izin_tur(con, [(r.get("kod"), r.get("ad"), r.get("saatlikizin"), r.get("ucretli")) for r in v])
    if "izinID" in k and "Aciklama" in k and "Kod" in k:
        return _izin_tur(con, [(r.get("Kod"), r.get("Aciklama"), None, None) for r in v])
    if "SicilID" in k and "Kalan" in k and "Hak" in k:
        return _bakiye(con, v)
    if "fotoimage" in k and "adsoyad" in k and "sicilno" in k and "adres" in k:
        return _kisi_ayrinti(con, v)
    if "adsoyad" in k and "sicilno" in k and "pozisyonad" in k and "mesaiperiyoduad" in k:
        return _kisi_listesi(con, v)
    return None


def _tapivot(con, satirlar: List[dict]) -> str:
    simdi = _simdi()
    gun_say, gunler = 0, set()
    for r in satirlar:
        try:
            sid = int(r["ysicilid"])
        except (KeyError, TypeError, ValueError):
            continue
        con.execute("INSERT INTO pv_personel(sicilid, sicilno, ad, pozisyon, yaka, bolum, guncel) VALUES(?,?,?,?,?,?,?) "
                    "ON CONFLICT(sicilid) DO UPDATE SET sicilno=COALESCE(NULLIF(excluded.sicilno, ''), sicilno), ad=excluded.ad, "
                    "pozisyon=COALESCE(excluded.pozisyon, pozisyon), yaka=COALESCE(excluded.yaka, yaka), "
                    "bolum=COALESCE(excluded.bolum, bolum), guncel=excluded.guncel",
                    (sid, str(r.get("ysicilno") or ""), str(r.get("ypersonel") or "").strip(), r.get("ypozisyonad"),
                     r.get("yyakaad"), r.get("ybolumad"), simdi))
        for a, d in r.items():
            m = GUN_ANAHTAR.match(a)
            if not m:
                continue
            h = hucre_coz(d)
            if h is None:
                continue
            g = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
            gunler.add(g)
            gun_say += 1
            if h.gercek:
                con.execute("INSERT OR REPLACE INTO pv_gun(sicilid, gun, plan, plan_kod, izin_kod, giris, cikis, g_dk, e_dk, renk, "
                            "gercek, guncel) VALUES(?,?,?,?,?,?,?,?,?,?,1,?)",
                            (sid, g, h.plan, h.plan_kod, h.izin_kod, h.giris, h.cikis, h.g_dk, h.e_dk, h.renk, simdi))
            else:                                   # yalnız plan: gerçekleşen kayıt varsa üzerine yazılmaz
                con.execute("INSERT INTO pv_gun(sicilid, gun, plan, renk, gercek, guncel) VALUES(?,?,?,?,0,?) "
                            "ON CONFLICT(sicilid, gun) DO UPDATE SET plan=excluded.plan, renk=excluded.renk, guncel=excluded.guncel "
                            "WHERE pv_gun.gercek = 0", (sid, g, h.plan, h.renk, simdi))
    con.commit()
    if not gunler:
        return f"{len(satirlar)} kişi (gün verisi yok)"
    a, b = min(gunler), max(gunler)
    return f"{len(satirlar)} kişi · {gun_say} gün kaydedildi ({_tr(a)} – {_tr(b)})"


def _tr(iso: str) -> str:
    return ".".join(reversed(iso.split("-")))


def _izin_tur(con, liste) -> Optional[str]:
    n = 0
    for kod, ad, saatlik, ucretli in liste:
        kod, ad = str(kod or "").strip(), str(ad or "").strip()
        if not kod or kod == "---" or not ad:
            continue
        con.execute("INSERT INTO pv_izin_tur(kod, ad, saatlik, ucretli) VALUES(?,?,?,?) ON CONFLICT(kod, ad) DO UPDATE SET "
                    "saatlik=COALESCE(excluded.saatlik, pv_izin_tur.saatlik), ucretli=COALESCE(excluded.ucretli, pv_izin_tur.ucretli)",
                    (kod, ad, None if saatlik is None else int(bool(saatlik)), None if ucretli is None else int(bool(ucretli))))
        n += 1
    con.commit()
    return f"{n} izin türü" if n else None


def _bakiye(con, v) -> str:
    simdi, n = _simdi(), 0
    for r in v:
        try:
            sid = int(r["SicilID"])
        except (KeyError, TypeError, ValueError):
            continue
        con.execute("INSERT OR REPLACE INTO pv_bakiye(sicilid, yil, hak, kullanilan, planlanan, devir, kalan, kidem, giris_tarih, guncel) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (sid, r.get("Yil"), r.get("Hak"), r.get("KullanilanYillikIzin"), r.get("PlanlananIzin"), r.get("IzinDevir"),
                     r.get("Kalan"), r.get("Kidem"), str(r.get("GirisTarih") or "")[:10], simdi))
        con.execute("UPDATE pv_personel SET giris_tarih=? WHERE sicilid=? AND (giris_tarih IS NULL OR giris_tarih='')",
                    (str(r.get("GirisTarih") or "")[:10], sid))
        n += 1
    con.commit()
    ad = v[0].get("Ad", "") + " " + v[0].get("Soyad", "") if n == 1 else f"{n} kişi"
    return f"izin bakiyesi: {ad.strip()} (kalan {v[0].get('Kalan')})" if n == 1 else f"izin bakiyesi: {ad}"


def _kisi_listesi(con, v) -> str:
    simdi, n = _simdi(), 0
    for r in v:
        try:
            sid = int(r["id"])
        except (KeyError, TypeError, ValueError):
            continue
        con.execute("INSERT INTO pv_personel(sicilid, sicilno, ad, pozisyon, yaka, bolum, periyot, telefon, guncel) "
                    "VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(sicilid) DO UPDATE SET sicilno=excluded.sicilno, ad=excluded.ad, "
                    "pozisyon=excluded.pozisyon, yaka=excluded.yaka, bolum=excluded.bolum, periyot=excluded.periyot, "
                    "telefon=excluded.telefon, guncel=excluded.guncel",
                    (sid, str(r.get("sicilno") or ""), str(r.get("adsoyad") or "").strip(), r.get("pozisyonad"), r.get("yakaad"),
                     r.get("bolumad"), r.get("mesaiperiyoduad"), str(r.get("ceptelefon") or "").strip(), simdi))
        n += 1
    con.commit()
    return f"personel listesi: {n} kişi"


def _kisi_ayrinti(con, v) -> Optional[str]:
    """Kişi ayrıntısından yalnızca fotoğraf, cep telefonu ve işe giriş tarihi (yalnız listede olan personel için)."""
    n = 0
    for r in v:
        try:
            sid = int(r["id"])
        except (KeyError, TypeError, ValueError):
            continue
        if not con.execute("SELECT 1 FROM pv_personel WHERE sicilid=?", (sid,)).fetchone():
            continue
        foto = r.get("fotoimage") if isinstance(r.get("fotoimage"), str) and len(r.get("fotoimage")) > 100 else None
        con.execute("UPDATE pv_personel SET foto=COALESCE(?, foto), telefon=COALESCE(NULLIF(?, ''), telefon), "
                    "giris_tarih=COALESCE(NULLIF(?, ''), giris_tarih), periyot=COALESCE(NULLIF(?, ''), periyot) WHERE sicilid=?",
                    (foto, str(r.get("ceptelefon") or "").strip(), str(r.get("giristarih") or "")[:10],
                     str(r.get("mesaiperiyoduad") or ""), sid))
        n += 1
    con.commit()
    return f"kişi kartı: {v[0].get('adsoyad', '')}" if n else None


# ====================================================================== okuma
def izin_adlari(con) -> Dict[str, str]:
    kur(con)
    ad = dict(BILINEN_IZINLER)
    grup: Dict[str, List[str]] = defaultdict(list)
    for r in con.execute("SELECT kod, ad FROM pv_izin_tur ORDER BY ad"):
        grup[r[0]].append(r[1])
    for kod, adlar in grup.items():
        ad[kod] = " / ".join(dict.fromkeys(adlar))
    return ad


def personel(con) -> Dict[int, dict]:
    kur(con)
    return {r["sicilid"]: dict(r) for r in con.execute("SELECT * FROM pv_personel ORDER BY ad")}


def bakiyeler(con) -> Dict[int, dict]:
    kur(con)
    return {r["sicilid"]: dict(r) for r in con.execute("SELECT * FROM pv_bakiye")}


def gunler(con, ilk: date, son: date) -> List[dict]:
    kur(con)
    return [dict(r) for r in con.execute("SELECT * FROM pv_gun WHERE gun BETWEEN ? AND ? ORDER BY sicilid, gun",
                                         (ilk.isoformat(), son.isoformat()))]


def kapsam(con) -> Tuple[Optional[str], Optional[str], int]:
    kur(con)
    r = con.execute("SELECT MIN(gun), MAX(gun), COUNT(DISTINCT sicilid) FROM pv_gun WHERE gercek=1").fetchone()
    return r[0], r[1], r[2] or 0


# ====================================================================== sınıflandırma
GELDI, GELMEDI, EKSIK, IZIN_TAM, IZIN_SAAT, TATIL, TATIL_CALISTI, PLAN, RESMI = (
    "geldi", "gelmedi", "eksik", "izin_tam", "izin_saat", "tatil", "tatil_calisti", "plan", "resmi")
SABIT_TATILLER = {(1, 1), (4, 23), (5, 1), (5, 19), (7, 15), (8, 30), (10, 29)}   # dini bayramlar veriden anlaşılır
BAYRAM_ORAN = 0.6          # o gün planlı çalışanların en az bu kadarı kayıtsızsa gün resmi tatil / bayram sayılır

DURUM_AD = {GELDI: "Geldi", GELMEDI: "Gelmedi (izinsiz)", EKSIK: "Eksik kart kaydı", IZIN_TAM: "İzinli", IZIN_SAAT: "Saatlik izinli",
            TATIL: "Hafta tatili", TATIL_CALISTI: "Tatilde çalıştı", PLAN: "Planlı", RESMI: "Resmi tatil / bayram"}


def _dk(s: str) -> Optional[int]:
    if not s:
        return None
    h, m = s.split(":")
    return int(h) * 60 + int(m)


@dataclass
class Gun:
    sicilid: int
    gun: date
    plan: str
    vardiya: str
    durum: str
    giris: str = ""
    cikis: str = ""
    izin_kod: str = ""
    gec_dk: int = 0
    erken_dk: int = 0
    fazla_dk: int = 0
    calisma_dk: int = 0


def siniflandir(r: dict, bugun: date, tolerans: int = VARSAYILAN_TOLERANS_DK, fazla_en_az: int = VARSAYILAN_FAZLA_EN_AZ_DK) -> Gun:
    g = date.fromisoformat(r["gun"])
    tur, _a, _b = plan_bilgi(r.get("plan") or "")
    giris, cikis, izin = r.get("giris") or "", r.get("cikis") or "", (r.get("izin_kod") or "").strip()
    gd, ed = r.get("g_dk"), r.get("e_dk")
    sonuc = Gun(r["sicilid"], g, r.get("plan") or "", tur, PLAN, giris, cikis, izin)
    a, b = _dk(giris), _dk(cikis)
    if a is not None and b is not None:
        sonuc.calisma_dk = (b - a) % (24 * 60)
    if g >= bugun or not r.get("gercek"):
        return sonuc                                   # bugün ve sonrası / yalnız plan: henüz kesin değil
    if izin:
        sonuc.durum = IZIN_TAM if a is None and b is None else IZIN_SAAT
        return sonuc
    if tur == "T":
        sonuc.durum = TATIL_CALISTI if (a is not None and b is not None) else TATIL
        if sonuc.durum == TATIL_CALISTI:
            sonuc.fazla_dk = sonuc.calisma_dk
        return sonuc
    if a is None and b is None:
        sonuc.durum = GELMEDI
        return sonuc
    if a is None or b is None:
        sonuc.durum = EKSIK
        return sonuc
    sonuc.durum = GELDI
    if gd is not None and gd > tolerans:
        sonuc.gec_dk = gd
    if ed is not None and ed > tolerans:
        sonuc.erken_dk = ed
    if ed is not None and -ed >= fazla_en_az:
        sonuc.fazla_dk = -ed
    return sonuc


@dataclass
class Ozet:
    sicilid: int
    planli: int = 0
    geldi: int = 0
    gelmedi: int = 0
    eksik: int = 0
    izinli: int = 0
    izin_saat: int = 0
    gec_adet: int = 0
    gec_dk: int = 0
    erken_adet: int = 0
    erken_dk: int = 0
    fazla_dk: int = 0
    tatil_calisti: int = 0
    izin_tur: Dict[str, int] = field(default_factory=dict)

    @property
    def devam(self) -> Optional[float]:
        payda = self.planli - self.izinli
        return None if payda <= 0 else max(0.0, min(1.0, (payda - self.gelmedi) / payda))


def ozetle(gunler_: Iterable[Gun]) -> Dict[int, Ozet]:
    oz: Dict[int, Ozet] = {}
    for g in gunler_:
        o = oz.setdefault(g.sicilid, Ozet(g.sicilid))
        if g.durum == PLAN:
            continue
        if g.durum not in (TATIL, TATIL_CALISTI, RESMI):
            o.planli += 1
        if g.durum in (GELDI, IZIN_SAAT, EKSIK):
            o.geldi += 1
        o.gelmedi += g.durum == GELMEDI
        o.eksik += g.durum == EKSIK
        o.izinli += g.durum == IZIN_TAM
        o.izin_saat += g.durum == IZIN_SAAT
        o.tatil_calisti += g.durum == TATIL_CALISTI
        if g.durum in (IZIN_TAM, IZIN_SAAT) and g.izin_kod:
            o.izin_tur[g.izin_kod] = o.izin_tur.get(g.izin_kod, 0) + 1
        if g.gec_dk:
            o.gec_adet += 1
            o.gec_dk += g.gec_dk
        if g.erken_dk:
            o.erken_adet += 1
            o.erken_dk += g.erken_dk
        o.fazla_dk += g.fazla_dk
    return oz


def donem_hesabi(con, ilk: date, son: date, ayar: Optional[dict] = None, bugun: Optional[date] = None):
    """(günler: List[Gun], özet: {sicilid: Ozet}) — Ayarlar'daki tolerans ve fazla çalışma sınırıyla."""
    ayar = ayar or {}
    tol = int(ayar.get("pv_tolerans_dk", VARSAYILAN_TOLERANS_DK))
    fz = int(ayar.get("pv_fazla_en_az_dk", VARSAYILAN_FAZLA_EN_AZ_DK))
    bugun = bugun or date.today()
    gl = resmi_tatilleri_ayir([siniflandir(r, bugun, tol, fz) for r in gunler(con, ilk, son)])
    return gl, ozetle(gl)


def resmi_tatilleri_ayir(gl: List[Gun]) -> List[Gun]:
    """Resmi tatil ve bayram günleri planda çalışma günü görünür ama kimse kart basmaz: o gün planlı çalışanların çoğu
    kayıtsızsa (ya da sabit resmi tatilse) 'gelmedi' sayılmaz; o gün çalışan 'tatilde çalıştı' olur."""
    gun_say: Dict[date, List[int]] = defaultdict(lambda: [0, 0])
    for g in gl:
        if g.durum in (GELDI, GELMEDI, EKSIK):
            gun_say[g.gun][0] += 1
            gun_say[g.gun][1] += g.durum == GELMEDI
    tatil = {d for d, (n, k) in gun_say.items() if (n >= 5 and k / n >= BAYRAM_ORAN) or ((d.month, d.day) in SABIT_TATILLER and k)}
    for g in gl:
        if g.gun in tatil:
            if g.durum == GELMEDI:
                g.durum = RESMI
            elif g.durum in (GELDI, EKSIK) and g.giris and g.cikis:
                g.durum, g.gec_dk, g.erken_dk, g.fazla_dk = TATIL_CALISTI, 0, 0, g.calisma_dk
    return gl


def tr_baslik(s: str) -> str:
    """Türkçe büyük/küçük harfe uygun 'Baş Harfler Büyük' (KALIP -> Kalıp, İBRAHİM -> İbrahim)."""
    def kelime(k: str) -> str:
        if not k:
            return k
        kucuk = k.replace("I", "ı").replace("İ", "i").lower()
        ilk = kucuk[0]
        ilk = "I" if ilk == "ı" else ("İ" if ilk == "i" else ilk.upper())
        return ilk + kucuk[1:]
    return " ".join("-".join(kelime(p) for p in w.split("-")) for w in str(s or "").split(" "))


def hafta_grup_liderleri(con, pazartesi: date, ayar: Optional[dict] = None) -> Dict[str, List[str]]:
    """O haftanın grup liderleri vardiyalarına göre: en çok planlandıkları vardiya. Ayarlar'daki elle düzeltme önceliklidir."""
    duz = ((ayar or {}).get("pv_grup_lider") or {}).get(pazartesi.isoformat())
    if duz:
        return {k: list(v) for k, v in duz.items()}
    kisiler = {sid: p for sid, p in personel(con).items() if GRUP_LIDERI in str(p.get("pozisyon") or "").upper()}
    sayac: Dict[int, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in gunler(con, pazartesi, pazartesi + timedelta(days=6)):
        if r["sicilid"] in kisiler:
            tur = plan_bilgi(r.get("plan") or "")[0]
            if tur in ("1", "2", "3", "G"):
                sayac[r["sicilid"]][tur] += 1
    sonuc: Dict[str, List[str]] = {"1": [], "2": [], "3": [], "G": []}
    for sid, s in sayac.items():
        v = max(s.items(), key=lambda x: x[1])[0]
        sonuc[v].append(kisiler[sid]["ad"])
    for v in sonuc:
        sonuc[v].sort()
    return sonuc


def sure_yaz(dk: int) -> str:
    dk = int(round(dk or 0))
    if dk < 60:
        return f"{dk} dk"
    return f"{dk // 60} sa {dk % 60:02d} dk" if dk % 60 else f"{dk // 60} sa"
