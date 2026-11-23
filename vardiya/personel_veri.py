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


_KURULU: set = set()                 # şeması kurulmuş bağlantılar (her okumada yeniden kurulup kilit beklenmesin)


def kur(con) -> None:
    if id(con) in _KURULU:
        return
    if con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name IN "
                   "('pv_personel','pv_gun','pv_izin_tur','pv_bakiye')").fetchone()[0] < 4:
        con.executescript(SEMA)          # yalnızca tablolar yoksa yazar (yazma kilidi gerektirir)
    kol = {r[1] for r in con.execute("PRAGMA table_info(pv_personel)")}
    if "cikis_tarih" not in kol:                      # işten çıkış tarihi (sonradan eklendi)
        con.execute("ALTER TABLE pv_personel ADD COLUMN cikis_tarih TEXT")
        con.commit()
    # Eksik (sınırı aşmış) listeden yanlış okunmuş günler: izin kodu yerine 'Ödenmeyen,green,-55_2_59' gibi kuyruk yazısı.
    # Bunlar gerçekleşen sayılmaz; doğru liste yeniden çekilince üzerine yazılır.
    if con.execute("SELECT 1 FROM pv_gun WHERE gercek=1 AND izin_kod LIKE '%,%' LIMIT 1").fetchone():
        con.execute("UPDATE pv_gun SET gercek=0, izin_kod='' WHERE gercek=1 AND izin_kod LIKE '%,%'")
        con.commit()
    _KURULU.add(id(con))


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
    if "<br>" in s and len(s.split("<br>")) >= 3:     # iki satırlı hücre: eksik (sınırı aşmış) liste, gerçekleşen sayılmaz
        p = s.split("<br>")
        kuyruk = p[-1].split(",")
        h = Hucre(plan=p[0].lstrip("?").strip(), gercek=True)
        kodlar = p[1].split() if len(p) > 1 else []
        h.plan_kod = kodlar[0] if kodlar else ""
        h.izin_kod = kodlar[1] if len(kodlar) > 1 and "," not in kodlar[1] else ""
        if len(p) > 2:
            sa = p[2].split()
            h.giris = _saat(sa[0]) if sa else ""
            h.cikis = _saat(sa[1]) if len(sa) > 1 else ""
        m = FARK.search(kuyruk[0]) if kuyruk else None
        if m:
            h.g_dk, h.e_dk = int(m.group(1)), int(m.group(2))
        h.renk = kuyruk[1].strip() if len(kuyruk) > 1 else ""
        return h
    parca = s.split("<br>")[0].split(",")
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
    r = tani_ve_kaydet(con, metin)
    return r["aciklama"] if r else None


def tani_ve_kaydet(con, metin: str) -> Optional[dict]:
    """{'aciklama', 'tur', ...}. tur: giris_cikis (ilk, son) · plan · izin_tur · bakiye (sid) · kisi_karti (sid) ·
    liste_aktif · liste_cikan. Tanınmayan yanıt (ör. firmanın tüm personel listesi) hiç yazılmaz: None."""
    v = _liste(metin)
    if v is None:
        return None
    k = v[0]
    kur(con)
    if "ysicilid" in k and any(GUN_ANAHTAR.match(a) for a in k):
        kisi = [r for r in v if not str(r.get("ysicilid", "")).startswith("m")]
        if not kisi:
            return None
        gunler_ = sorted({f"{m.group(1)}-{m.group(2)}-{m.group(3)}" for r in kisi for a in r if (m := GUN_ANAHTAR.match(a))})
        gercek = any((h := hucre_coz(d)) is not None and h.gercek for r in kisi for a, d in r.items() if GUN_ANAHTAR.match(a))
        if gercek and eksik_liste_mi(kisi):
            return {"aciklama": f"EKSİK LİSTE: {len(kisi)} kişi, {len(gunler_)} gün, ama geçmiş günlerde giriş-çıkış saati yok "
                                "(büyük olasılıkla sayfanın görüntüleme sınırı aşıldı). Kaydedilmedi, eldeki veri korunuyor.",
                    "tur": "eksik_liste", "ilk": gunler_[0] if gunler_ else None, "son": gunler_[-1] if gunler_ else None}
        return {"aciklama": _tapivot(con, kisi), "tur": "giris_cikis" if gercek else "plan",
                "ilk": gunler_[0] if gunler_ else None, "son": gunler_[-1] if gunler_ else None}
    if "kod" in k and "ad" in k and "saatlikizin" in k:
        a = _izin_tur(con, [(r.get("kod"), r.get("ad"), r.get("saatlikizin"), r.get("ucretli")) for r in v])
        return {"aciklama": a, "tur": "izin_tur"} if a else None
    if "izinID" in k and "Aciklama" in k and "Kod" in k:
        a = _izin_tur(con, [(r.get("Kod"), r.get("Aciklama"), None, None) for r in v])
        return {"aciklama": a, "tur": "izin_tur"} if a else None
    if "SicilID" in k and "Kalan" in k and "Hak" in k:
        return {"aciklama": _bakiye(con, v), "tur": "bakiye", "sid": k.get("SicilID") if len(v) == 1 else None}
    if "fotoimage" in k and "adsoyad" in k and "sicilno" in k and "adres" in k:
        a = _kisi_ayrinti(con, v)
        return {"aciklama": a, "tur": "kisi_karti", "sid": k.get("id") if len(v) == 1 else None} if a else None
    if "adsoyad" in k and "sicilno" in k and "pozisyonad" in k and "mesaiperiyoduad" in k:
        cikan = any(r.get("cikistarih") for r in v)
        aktif = any(not r.get("cikistarih") for r in v)
        return {"aciklama": _kisi_listesi(con, v), "tur": "liste_cikan" if cikan and not aktif else ("liste_hepsi" if cikan else "liste_aktif")}
    return None


def eksik_liste_mi(satirlar: List[dict], bugun: Optional[date] = None) -> bool:
    """Planlanan + Gerçekleşen listesi geçmiş günler için giriş-çıkış saati içermiyorsa (sayfa çok büyük listede saatleri
    göndermiyor: 'Görüntüleme sınırı aşımı') eksiktir; kaydedilirse doğru verinin üzerine yazar."""
    bugun = (bugun or date.today()).isoformat()
    toplam = saatli = 0
    for r in satirlar:
        for a, d in r.items():
            m = GUN_ANAHTAR.match(a)
            if not m or f"{m.group(1)}-{m.group(2)}-{m.group(3)}" >= bugun:
                continue
            h = hucre_coz(d)
            if h is None or not h.gercek:
                continue
            toplam += 1
            saatli += bool(h.giris or h.cikis)
    return toplam >= 30 and saatli < toplam * 0.05


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
            if h.gercek:                          # saatsiz yeni kayıt, saatli eski kaydın üzerine yazmaz
                con.execute("INSERT INTO pv_gun(sicilid, gun, plan, plan_kod, izin_kod, giris, cikis, g_dk, e_dk, renk, "
                            "gercek, guncel) VALUES(?,?,?,?,?,?,?,?,?,?,1,?) "
                            "ON CONFLICT(sicilid, gun) DO UPDATE SET plan=excluded.plan, plan_kod=excluded.plan_kod, "
                            "izin_kod=excluded.izin_kod, giris=excluded.giris, cikis=excluded.cikis, g_dk=excluded.g_dk, "
                            "e_dk=excluded.e_dk, renk=excluded.renk, gercek=1, guncel=excluded.guncel "
                            "WHERE NOT ((COALESCE(excluded.giris,'') = '' AND COALESCE(excluded.cikis,'') = '') "
                            "AND (COALESCE(pv_gun.giris,'') <> '' OR COALESCE(pv_gun.cikis,'') <> ''))",
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
        cikis = str(r.get("cikistarih") or "")[:10] or None
        con.execute("INSERT INTO pv_personel(sicilid, sicilno, ad, pozisyon, yaka, bolum, periyot, telefon, cikis_tarih, guncel) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(sicilid) DO UPDATE SET sicilno=excluded.sicilno, ad=excluded.ad, "
                    "pozisyon=excluded.pozisyon, yaka=excluded.yaka, bolum=excluded.bolum, periyot=excluded.periyot, "
                    "telefon=excluded.telefon, cikis_tarih=excluded.cikis_tarih, guncel=excluded.guncel",
                    (sid, str(r.get("sicilno") or ""), str(r.get("adsoyad") or "").strip(), r.get("pozisyonad"), r.get("yakaad"),
                     r.get("bolumad"), r.get("mesaiperiyoduad"), str(r.get("ceptelefon") or "").strip(), cikis, simdi))
        n += 1
    con.commit()
    c = sum(1 for r in v if r.get("cikistarih"))
    return f"personel listesi: {n} kişi" + (f" ({c} işten çıkmış)" if c else "")


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


# ====================================================================== istek şablonları (otomatik çekim)
def _tarih_bicimleri(d: date) -> List[str]:
    return list(dict.fromkeys([d.isoformat(), d.strftime("%d.%m.%Y"), d.strftime("%Y%m%d"), d.strftime("%d/%m/%Y"),
                               d.strftime("%Y/%m/%d"), d.strftime("%m/%d/%Y"), d.strftime("%d-%m-%Y"), d.strftime("%Y.%m.%d")]))


def tarih_degistir(metin: str, eski_ilk: date, eski_son: date, yeni_ilk: date, yeni_son: date) -> Tuple[str, bool]:
    """İstek adresinde/gövdesinde dönem başlangıç ve bitiş tarihlerini (hangi biçimde yazılmışsa) yenileriyle değiştirir.
    Bitiş tarihi 'hariç' yazılmış olabilir (son + 1 gün). Değiştirmeler birbirini etkilemesin diye önce yer tutucu konur.
    Dönüş: (yeni metin, tarihler bulundu mu)."""
    from urllib.parse import quote
    if not metin:
        return metin, False
    sonuc, yer = metin, {}

    def degistir(eski: date, yeni: date, ad: str) -> bool:
        nonlocal sonuc
        for be, by in zip(_tarih_bicimleri(eski), _tarih_bicimleri(yeni)):
            for a, b in ((be, by), (quote(be, safe=""), quote(by, safe=""))):
                if a in sonuc:
                    tutucu = f"\x00{ad}\x00"
                    sonuc = sonuc.replace(a, tutucu)
                    yer[tutucu] = b
                    return True
        return False
    ilk_ok = degistir(eski_ilk, yeni_ilk, "ilk")
    son_ok = eski_ilk != eski_son and degistir(eski_son, yeni_son, "son")
    if not son_ok and eski_ilk != eski_son:
        son_ok = degistir(eski_son + timedelta(days=1), yeni_son + timedelta(days=1), "son1")
    for t, v in yer.items():
        sonuc = sonuc.replace(t, v)
    return sonuc, (ilk_ok and son_ok) or (eski_ilk == eski_son and ilk_ok)


def kimlik_degistir(metin: str, eski: int, yeni: int) -> Tuple[str, bool]:
    """İstekte kişi numarasını (tam sayı olarak geçtiği yerlerde) değiştirir."""
    if not metin:
        return metin, False
    desen = re.compile(r"(?<![0-9])" + re.escape(str(eski)) + r"(?![0-9])")
    yeni_metin, n = desen.subn(str(yeni), metin)
    return yeni_metin, n > 0


def aylar(ilk: date, son: date) -> List[Tuple[date, date]]:
    """[ilk, son] aralığını ay ay böler."""
    sonuc = []
    a = date(ilk.year, ilk.month, 1)
    while a <= son:
        sonraki = date(a.year + (a.month == 12), a.month % 12 + 1, 1)
        sonuc.append((max(a, ilk), min(sonraki - timedelta(days=1), son)))
        a = sonraki
    return sonuc


def aktif_siciller(con) -> List[int]:
    kur(con)
    return [r[0] for r in con.execute("SELECT sicilid FROM pv_personel WHERE cikis_tarih IS NULL OR cikis_tarih = '' ORDER BY ad")]


# ====================================================================== ortak gösterim (exe ve tarayıcı)
RENK = {"1": "#DDEBF7", "2": "#FCE4D6", "3": "#E2D9F3", "G": "#F1F6E8", "D": "#F4F4F4",
        IZIN_TAM: "#C6EFCE", IZIN_SAAT: "#C6EFCE", GELMEDI: "#FFC7CE", EKSIK: "#F8CBAD",
        TATIL: "#EDEDED", TATIL_CALISTI: "#D9E1F2", "gec": "#FFEB9C"}


_KISA = (("yıllık", "Yıllık"), ("raporlu ödenmeyen", "Rapor"), ("raporlu ödenen", "Rapor (ücretli)"), ("rapor", "Rapor"),
         ("habersiz", "Habersiz"), ("ücretsiz", "Ücretsiz"), ("ücretli", "Ücretli"), ("babalık", "Babalık"), ("ölüm", "Ölüm"),
         ("evlilik", "Evlilik"), ("görev", "Görev"), ("süt", "Süt"), ("vizite", "Vizite"), ("sünnet", "Sünnet"),
         ("doğum", "Doğum"), ("mazeret", "Mazeret"), ("cuma", "Cuma"), ("arge", "Ar-Ge"))


def izin_kisa(izin_ad: Dict[str, str], kod: str) -> str:
    """Kısa izin adı: 'Yıllık', 'Rapor', 'Ücretsiz'… Aynı kodu paylaşan türler (01: Yıllık izin / Raporlu ödenmeyen)
    'Yıllık / Rapor' olur."""
    ad = izin_ad.get(kod) or BILINEN_IZINLER.get(kod) or f"İzin {kod}"
    sonuc = []
    for parca in (x.strip() for x in ad.split(" / ") if x.strip()):
        k = parca.replace("I", "ı").replace("İ", "i").lower()
        kisa = next((v for a, v in _KISA if a in k), parca)
        if kisa not in sonuc:
            sonuc.append(kisa)
    return " / ".join(sonuc) or ad


def gun_yazi(g: Gun, izin_ad: Dict[str, str], bugun: date) -> Tuple[str, str]:
    """Bir günün hücre yazısı (iki satır) ve renk kodu."""
    kisa = plan_kisa(g.plan)
    saat = f"{g.giris or '--:--'}–{g.cikis or '--:--'}" if (g.giris or g.cikis) else ""
    if g.durum == IZIN_TAM:
        return izin_kisa(izin_ad, g.izin_kod), RENK[IZIN_TAM]
    if g.durum == IZIN_SAAT:
        return f"{kisa}\n{saat} (izinli)", RENK[IZIN_SAAT]
    if g.durum == GELMEDI:
        return f"{kisa}\ngelmedi", RENK[GELMEDI]
    if g.durum == EKSIK:
        return f"{kisa}\n{saat} eksik", RENK[EKSIK]
    if g.durum == TATIL:
        return kisa, RENK[TATIL]
    if g.durum == RESMI:
        return "Resmi tatil", RENK[TATIL]
    if g.durum == TATIL_CALISTI:
        return f"{kisa} · çalıştı\n{saat}", RENK[TATIL_CALISTI]
    if g.durum == GELDI:
        return f"{kisa}\n{saat}", (RENK["gec"] if (g.gec_dk or g.erken_dk) else RENK.get(g.vardiya, "#FFFFFF"))
    return (kisa + (f"\n{saat}" if saat else "")), ("#FFFFFF" if g.gun >= bugun else RENK.get(g.vardiya, "#FFFFFF"))


def gun_ipucu(g: Gun, izin_ad: Dict[str, str]) -> str:
    p = [f"{g.gun:%d.%m.%Y} · plan: {g.plan}", DURUM_AD.get(g.durum, g.durum)]
    if g.giris or g.cikis:
        p.append(f"giriş {g.giris or '-'} · çıkış {g.cikis or '-'}")
    if g.izin_kod:
        p.append(f"izin: {izin_ad.get(g.izin_kod, g.izin_kod)} ({g.izin_kod})")
    if g.gec_dk:
        p.append(f"geç gelme: {sure_yaz(g.gec_dk)}")
    if g.erken_dk:
        p.append(f"erken çıkma: {sure_yaz(g.erken_dk)}")
    if g.fazla_dk:
        p.append(f"fazla çalışma: {sure_yaz(g.fazla_dk)}")
    return "\n".join(p)


def baskin_vardiya(gl: Iterable[Gun]) -> Dict[int, str]:
    say: Dict[int, Dict[str, int]] = {}
    for g in gl:
        if g.vardiya in ("1", "2", "3", "G"):
            d = say.setdefault(g.sicilid, {})
            d[g.vardiya] = d.get(g.vardiya, 0) + 1
    return {sid: max(d.items(), key=lambda x: x[1])[0] for sid, d in say.items()}


def lider_mi(kisi: dict) -> bool:
    return GRUP_LIDERI in str((kisi or {}).get("pozisyon") or "").upper()


def tumunu_sil(con) -> int:
    """Programın kendi veri tabanındaki tüm personel verisini siler (sistemdeki kayıtlara dokunmaz). Dönüş: silinen gün sayısı."""
    kur(con)
    n = con.execute("SELECT COUNT(*) FROM pv_gun").fetchone()[0]
    for t in ("pv_gun", "pv_personel", "pv_bakiye", "pv_izin_tur"):
        con.execute(f"DELETE FROM {t}")
    con.commit()
    return n


def _b64_coz(v: str):
    """(çözülmüş metin, yeniden kodlayıcı) ya da None. Standart / URL'ye uygun base64, dolgulu ya da dolgusuz."""
    import base64
    import binascii
    for urlsafe in (False, True):
        try:
            ham = v + "=" * (-len(v) % 4)
            b = base64.urlsafe_b64decode(ham) if urlsafe else base64.b64decode(ham, validate=True)
            t = b.decode("utf-8")
        except (binascii.Error, ValueError, UnicodeDecodeError):
            continue
        dolgu = v.endswith("=")

        def kodla(x: str, u=urlsafe, d=dolgu) -> str:
            e = (base64.urlsafe_b64encode if u else base64.b64encode)(x.encode("utf-8")).decode()
            return e if d else e.rstrip("=")
        return t, kodla
    return None


def tarih_degistir_derin(url: str, eski_ilk: date, eski_son: date, yeni_ilk: date, yeni_son: date) -> Tuple[str, bool, str]:
    """Önce düz metinde, olmazsa sorgu alanlarının içinde (URL çözülmüş, 'ÖNEK!' sonrası, base64 çözülmüş) tarih arar.
    Dönüş: (yeni adres, bulundu mu, nasıl bulunduğu — tanı kaydı için, değer yazmadan)."""
    from urllib.parse import parse_qsl, quote, unquote, urlsplit, urlunsplit
    yeni, ok = tarih_degistir(url, eski_ilk, eski_son, yeni_ilk, yeni_son)
    if ok:
        return yeni, True, "adreste düz"
    try:
        p = urlsplit(url)
        alanlar = parse_qsl(p.query, keep_blank_values=True)
    except ValueError:
        return url, False, "adres çözülemedi"
    notlar = []
    for i, (ad, deger) in enumerate(alanlar):
        adaylar = [("", deger, None)]
        if "!" in deger:
            on, _, arka = deger.partition("!")
            adaylar.append((on + "!", arka, None))
        for on, govde, _ in list(adaylar):
            c = _b64_coz(govde)
            if c:
                adaylar.append((on, c[0], c[1]))
        for on, govde, kodla in adaylar:
            g2, ok2 = tarih_degistir(govde, eski_ilk, eski_son, yeni_ilk, yeni_son)
            if ok2:
                alanlar[i] = (ad, on + (kodla(g2) if kodla else g2))
                q = "&".join(f"{quote(a, safe='')}={quote(d, safe='!*()~-_.')}" for a, d in alanlar)
                return urlunsplit((p.scheme, p.netloc, p.path, q, p.fragment)), True, \
                    f"'{ad}' alanında" + (" base64 içinde" if kodla else "")
        on = deger.split("!")[0] + "!" if "!" in deger else ""
        notlar.append(f"'{ad}': {('ön ek ' + repr(on) + ' + ') if on else ''}{len(deger)} karakter"
                      + (", base64 çözüldü ama tarih yok" if any(k for _, _, k in adaylar) else ", base64 değil"))
    return url, False, "; ".join(notlar) or "sorgu alanı yok"


# ====================================================================== personel kartı: görsel dönem özeti (exe ve tarayıcı)
GUN_AD = ("Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz")
SERIT_RENK = {"geldi": "#3e9b2a", "gec": "#e0a100", "gelmedi": "#d64541", "eksik": "#e0702a", "izin": "#2a7fd1",
              "tatil": "#c9cdd6", "tatil_calisti": "#7b4fa8", "plan": "#eef0f4"}
SERIT_AD = (("geldi", "geldi"), ("gec", "geç / erken"), ("gelmedi", "gelmedi"), ("eksik", "eksik kart"),
            ("izin", "izin"), ("tatil", "tatil"), ("tatil_calisti", "tatilde çalıştı"))


def devam_rengi(devam: Optional[float]) -> str:
    if devam is None:
        return "#c9cdd6"
    return "#3e9b2a" if devam >= 0.95 else "#e0a100" if devam >= 0.85 else "#d64541"


def _serit_turu(g: Gun) -> str:
    if g.durum == GELDI:
        return "gec" if (g.gec_dk or g.erken_dk) else "geldi"
    return {GELMEDI: "gelmedi", EKSIK: "eksik", IZIN_TAM: "izin", IZIN_SAAT: "izin", TATIL: "tatil", RESMI: "tatil",
            TATIL_CALISTI: "tatil_calisti"}.get(g.durum, "plan")


def _gun_satiri(g: Gun, izin_ad: Dict[str, str]) -> dict:
    acik = []
    if g.izin_kod:
        acik.append(izin_ad.get(g.izin_kod, f"İzin {g.izin_kod}") + (" (saatlik)" if g.durum == IZIN_SAAT else ""))
    if g.durum == GELMEDI:
        acik.append("habersiz / kayıtsız gelmedi")
    if g.durum == EKSIK:
        acik.append("yalnızca " + ("giriş" if g.giris else "çıkış") + " kaydı var")
    if g.durum == RESMI:
        acik.append("resmi tatil")
    if g.gec_dk:
        acik.append(f"{sure_yaz(g.gec_dk)} geç")
    if g.erken_dk:
        acik.append(f"{sure_yaz(g.erken_dk)} erken çıktı")
    if g.fazla_dk:
        acik.append(f"+{sure_yaz(g.fazla_dk)} fazla")
    return {"gun": g.gun.isoformat(), "tarih": f"{g.gun:%d.%m.%Y} {GUN_AD[g.gun.weekday()]}", "plan": plan_kisa(g.plan) or g.plan or "-",
            "saat": (f"{g.giris or '--:--'} – {g.cikis or '--:--'}" if (g.giris or g.cikis) else "-"),
            "aciklama": ", ".join(acik), "tur": _serit_turu(g)}


def kart_ozeti(gunler_: Iterable[Gun], o: Optional[Ozet], tum: Dict[int, Ozet], izin_ad: Dict[str, str]) -> Optional[dict]:
    """Personel kartındaki görsel özetin verisi. Çubuklar bölümdeki en yüksek değere göre oranlanır (0-1)."""
    if o is None:
        return None
    gl = sorted((g for g in gunler_ if g.durum != PLAN), key=lambda g: g.gun)
    tum = tum or {}

    def en(f) -> float:
        return max([f(x) for x in tum.values()] + [f(o), 0]) or 0

    cubuk = []
    for ad, deger, metin, renk in (
            ("Geç gelme", o.gec_dk, f"{o.gec_adet} kez · {sure_yaz(o.gec_dk)}", "#e0a100"),
            ("Erken çıkma", o.erken_dk, f"{o.erken_adet} kez · {sure_yaz(o.erken_dk)}", "#e0702a"),
            ("Fazla çalışma", o.fazla_dk, sure_yaz(o.fazla_dk), "#150958"),
            ("Tatilde çalıştı", o.tatil_calisti, f"{o.tatil_calisti} gün", "#7b4fa8")):
        alan = {"Geç gelme": lambda x: x.gec_dk, "Erken çıkma": lambda x: x.erken_dk,
                "Fazla çalışma": lambda x: x.fazla_dk, "Tatilde çalıştı": lambda x: x.tatil_calisti}[ad]
        m = en(alan)
        cubuk.append({"ad": ad, "metin": metin, "oran": (deger / m) if m else 0.0, "renk": renk})
    listeler = {"geldi": [], "gelmedi": [], "eksik": [], "izin": []}
    for g in gl:
        s = _gun_satiri(g, izin_ad)
        if g.durum in (GELDI, IZIN_SAAT, EKSIK):
            listeler["geldi"].append(s)
        if g.durum == GELMEDI:
            listeler["gelmedi"].append(s)
        if g.durum == EKSIK:
            listeler["eksik"].append(s)
        if g.durum in (IZIN_TAM, IZIN_SAAT):
            listeler["izin"].append(s)
    return {"devam": o.devam, "devam_renk": devam_rengi(o.devam), "planli": o.planli,
            "kutular": [{"k": "geldi", "ad": "Geldi", "deger": o.geldi, "ek": f" / {o.planli}", "renk": "#3e9b2a", "zemin": "#eef8ec"},
                        {"k": "gelmedi", "ad": "Gelmedi", "deger": o.gelmedi, "ek": "", "renk": "#d64541", "zemin": "#fdeeee"},
                        {"k": "eksik", "ad": "Eksik kart", "deger": o.eksik, "ek": "", "renk": "#e0a100", "zemin": "#fdf6e3"},
                        {"k": "izin", "ad": "İzinli gün", "deger": len(listeler["izin"]), "ek": "", "renk": "#2a7fd1", "zemin": "#e9f2fc"}],
            "cubuk": cubuk,
            "serit": [{"gun": g.gun.isoformat(), "tur": _serit_turu(g), "renk": SERIT_RENK[_serit_turu(g)],
                       "ipucu": gun_ipucu(g, izin_ad)} for g in gl],
            "izinler": [{"ad": izin_kisa(izin_ad, k), "gun": n} for k, n in sorted(o.izin_tur.items(), key=lambda x: -x[1])],
            "listeler": listeler}
