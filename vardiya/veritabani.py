"""SQLite veri tabanı: kayıtlar, ayarlar, şef atamaları, arşiv, yapıştırılan görseller."""
from __future__ import annotations

import json
import os
import sqlite3
import re
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

BICIM = "%Y-%m-%d %H:%M:%S"

VARSAYILAN_MAKINELER = [
    "IM21", "IM22", "IM23", "IM24", "IM25", "IM26", "IM27", "IM28", "IM29", "IM30",
    "IM50", "IM52", "IM53", "IM54", "IM55", "IM56", "IM57", "IM58", "IM59", "IM60",
    "IM61", "IM62", "IM65", "IM66", "IM67", "IM68", "IM69", "IM84", "IM85",
]

VARSAYILAN_AYAR = {
    "esik": 0.60,
    "hesap_kurali": "gunluk",
    "hesap_yontemi": "vardiya",
    "operator_haric_durus": [],
    "hatali_durus_turleri": [],                # Ayarlar: bu duruşlarda operatör ve iş (ürün kodu) olmamalı; varsa hatalı duruş
    "hatali_durus_en_az_dk": 5,                # bundan kısa hatalı duruşlar listelenmez
    "cormind_adres": "http://192.168.0.39",
    "cormind_makine_idleri": [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 18, 19, 20, 21, 22, 23, 24, 25, 26, 28, 29, 30, 31, 32, 33, 34, 35, 80, 15],
    "vardiya_dk": 480,
    "yemek_dk": 30,
    "cay_dk": 10,
    "makineler": VARSAYILAN_MAKINELER,
    "sefler": ["Güryay", "Bülent", "Serhat"],
    "vardiya_sef": {"1": "Güryay", "2": "Bülent", "3": "Serhat"},
    "idle_makineleri_goster": False,          # eski ayar (artık kullanılmıyor; calismayanlari_gizle)
    "calismayanlari_gizle": True,
}

SEMA = """
CREATE TABLE IF NOT EXISTS kayit (
    makine    TEXT NOT NULL,
    baslangic TEXT NOT NULL,
    bitis     TEXT NOT NULL,
    operator  TEXT,
    tip       TEXT NOT NULL DEFAULT '',
    is_emri   TEXT,
    urun_adi  TEXT,
    urun_kodu TEXT,
    PRIMARY KEY (makine, baslangic, tip)
);
CREATE INDEX IF NOT EXISTS ix_kayit_bas ON kayit (baslangic);
-- 1 günden uzun kayıtlar için küçük ayrı dizin: aralığa önceden uzanan kayıtlar tüm tablo taranmadan bulunur
CREATE INDEX IF NOT EXISTS ix_kayit_uzun ON kayit (baslangic) WHERE julianday(bitis) - julianday(baslangic) > 1;
-- gün başına kayıt sayısı özeti (takvimdeki 'verisi olan günler'): tüm tabloyu saymamak için
CREATE TABLE IF NOT EXISTS gun_ozet (gun TEXT PRIMARY KEY, kayit INTEGER NOT NULL);
-- kayıtlarda geçen makine / operatör / duruş türü adları: listeler için tüm tabloyu (ağ üzerinden) taramamak için
CREATE TABLE IF NOT EXISTS sozluk (tur TEXT NOT NULL, deger TEXT NOT NULL, PRIMARY KEY (tur, deger)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS ayar (anahtar TEXT PRIMARY KEY, deger TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sef_atama (
    tarih   TEXT NOT NULL,
    vardiya INTEGER NOT NULL,
    sef     TEXT NOT NULL,
    PRIMARY KEY (tarih, vardiya)
);
CREATE TABLE IF NOT EXISTS aktarim (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zaman TEXT NOT NULL,
    dosya TEXT,
    toplam INTEGER, yeni INTEGER, guncellenen INTEGER, ayni INTEGER, atlanan INTEGER,
    ilk_gun TEXT, son_gun TEXT
);
CREATE TABLE IF NOT EXISTS arsiv (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ad TEXT NOT NULL,
    tur TEXT NOT NULL,
    olusturma TEXT NOT NULL,
    ilk_gun TEXT, son_gun TEXT,
    ayar_json TEXT, sonuc_json TEXT,
    pdf BLOB
);
CREATE TABLE IF NOT EXISTS kot (
    no      TEXT PRIMARY KEY,
    tarih   TEXT NOT NULL,
    saat    TEXT,
    vardiya INTEGER,
    veri    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS metin (anahtar TEXT PRIMARY KEY, icerik TEXT NOT NULL);
-- gece doğrulaması (hatalı duruşlar): yalnızca kontrol edilen duruşları olan tezgâhlar için Cormind'den alınır.
-- Yalnızca operatör adı, makine, iş emri ve zamanlar saklanır (e-posta, şifre vb. hiçbir kullanıcı bilgisi alınmaz).
CREATE TABLE IF NOT EXISTS cm_oturum (makine TEXT NOT NULL, operator TEXT NOT NULL, bas TEXT NOT NULL, bit TEXT,
    PRIMARY KEY (makine, bas, operator));
CREATE TABLE IF NOT EXISTS cm_is_durum (gun TEXT NOT NULL, makine TEXT NOT NULL, is_emri TEXT NOT NULL,
    makinede INTEGER NOT NULL, degisme TEXT, kontrol TEXT NOT NULL, PRIMARY KEY (gun, makine, is_emri));
CREATE TABLE IF NOT EXISTS cm_dogrulama (gun TEXT NOT NULL, makine TEXT NOT NULL, zaman TEXT NOT NULL,
    PRIMARY KEY (gun, makine));
CREATE TABLE IF NOT EXISTS gorsel (
    anahtar TEXT PRIMARY KEY,
    png BLOB NOT NULL,
    zaman TEXT NOT NULL
);
"""


def ac(yol: str) -> sqlite3.Connection:
    """Veri tabanını açar (yoksa oluşturur). Ağ klasöründe çalışması için varsayılan günlük kipi kullanılır."""
    klasor = os.path.dirname(os.path.abspath(yol))
    os.makedirs(klasor, exist_ok=True)
    con = sqlite3.connect(yol, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA cache_size = -65536")            # 64 MB önbellek: aynı sayfalar ağdan tekrar okunmasın
    con.executescript(SEMA)
    con.commit()
    if con.execute("SELECT 1 FROM gun_ozet LIMIT 1").fetchone() is None and con.execute("SELECT 1 FROM kayit LIMIT 1").fetchone():
        gun_ozet_yenile(con)                             # ilk kez: bir defalık tam sayım
    return con


def gun_ozet_yenile(con: sqlite3.Connection, ilk: Optional[str] = None, son: Optional[str] = None) -> None:
    """gun_ozet tablosunu [ilk, son] günleri için (verilmezse tamamen) kayıt tablosundan yeniden sayar."""
    if ilk is None:
        con.execute("DELETE FROM gun_ozet")
        con.execute("INSERT INTO gun_ozet SELECT substr(baslangic,1,10), COUNT(*) FROM kayit GROUP BY 1")
    else:
        ilk, son = ilk[:10], (son or ilk)[:10]
        con.execute("DELETE FROM gun_ozet WHERE gun BETWEEN ? AND ?", (ilk, son))
        con.execute("INSERT INTO gun_ozet SELECT substr(baslangic,1,10), COUNT(*) FROM kayit "
                    "WHERE baslangic >= ? AND baslangic < ? GROUP BY 1", (ilk, son + " 99"))
    con.commit()


HATALI_EK = " (hatalı)"         # hariç tutulan duruş türünde operatör ya da iş (ürün kodu) varsa: hariç tutulmaz, bu ekle görünür
_IS_VAR = ("((operator IS NOT NULL AND trim(operator) <> '') OR "
           "(urun_kodu IS NOT NULL AND trim(urun_kodu) NOT IN ('', '-')))")


def haric_duruslar(con: sqlite3.Connection) -> List[str]:
    """Ayarlar'da 'raporlardan ve hesaptan hariç tutulacak' diye seçilen duruş türleri."""
    try:
        r = con.execute("SELECT deger FROM ayar WHERE anahtar = 'operator_haric_durus'").fetchone()
        return [str(x) for x in (json.loads(r[0]) if r and r[0] else []) if x]
    except (sqlite3.Error, ValueError, TypeError):
        return []


def aralik_satirlari(con: sqlite3.Connection, kolonlar: str, ilk: date, son: date, ek: str = "", ek_arg: tuple = (),
                     hatali_etiket: bool = False):
    """[ilk, son] günlerine değen kayıtlar; tüm tablo taranmaz. Aralıkta (ya da bir gün önce) başlayanlar başlangıç dizininden,
    daha önce başlayıp içeri uzanan uzun kayıtlar küçük 'uzun kayıt' dizininden okunur.
    hatali_etiket: hariç tutulan bir duruş türünde makinede operatör ya da iş (ürün kodu) görünüyorsa tür adına
    HATALI_EK eklenir; böylece o kayıt hariç tutulmaz, normal duruş gibi hesaba ve raporlara girer (Kayıtlar ekranı ham kalır)."""
    bas = ilk.strftime("%Y-%m-%d 00:00:00")
    bit = (son + timedelta(days=1)).strftime("%Y-%m-%d 00:00:00")
    once = (ilk - timedelta(days=1)).strftime("%Y-%m-%d 00:00:00")
    ek = f" AND ({ek})" if ek else ""
    sec, sec_arg = kolonlar, ()
    haric = haric_duruslar(con) if hatali_etiket else []
    if haric and re.search(r"\btip\b", kolonlar):
        yer = ", ".join("?" * len(haric))
        sec = re.sub(r"\btip\b", f"CASE WHEN tip IN ({yer}) AND baslangic >= ? AND {_IS_VAR} THEN tip || '{HATALI_EK}' ELSE tip END AS tip",
                     kolonlar, count=1)
        sec_arg = tuple(haric) + (bas,)         # aralıktan önce açılmış kaydın operatör / iş bilgisi eskidir: hariç kalır
    return con.execute(
        f"SELECT {sec} FROM kayit WHERE baslangic >= ? AND baslangic < ? AND bitis >= ?{ek} "
        f"UNION ALL SELECT {sec} FROM kayit WHERE julianday(bitis) - julianday(baslangic) > 1 "
        f"AND baslangic < ? AND bitis >= ?{ek}",
        sec_arg + (once, bit, bas) + tuple(ek_arg) + sec_arg + (once, bas) + tuple(ek_arg))


# ------------------------------------------------------------------ ayarlar
def ayar_oku(con: sqlite3.Connection) -> dict:
    sonuc = json.loads(json.dumps(VARSAYILAN_AYAR))
    for r in con.execute("SELECT anahtar, deger FROM ayar"):
        try:
            sonuc[r["anahtar"]] = json.loads(r["deger"])
        except ValueError:
            pass
    return sonuc


GECMISSIZ = {"kapat_istegi"}               # sık değişen, geçmişe yazılmayan ayarlar


def ayar_yaz(con: sqlite3.Connection, anahtar: str, deger) -> None:
    yeni = json.dumps(deger, ensure_ascii=False)
    if anahtar not in GECMISSIZ:
        try:                                    # değişiklik geçmişi: kim (bilgisayar, sürüm), ne zaman, eski -> yeni
            r = con.execute("SELECT deger FROM ayar WHERE anahtar=?", (anahtar,)).fetchone()
            eski = r[0] if r else None
            if eski != yeni:
                import socket
                from .surum import SURUM
                con.execute("CREATE TABLE IF NOT EXISTS ayar_gecmis (zaman TEXT, pc TEXT, surum TEXT, anahtar TEXT, eski TEXT, yeni TEXT)")
                con.execute("INSERT INTO ayar_gecmis VALUES(?,?,?,?,?,?)", (datetime.now().strftime(BICIM), socket.gethostname(), SURUM,
                                                                           anahtar, eski, yeni))
        except Exception:  # noqa: BLE001  (geçmiş yazılamasa da ayar kaydedilir)
            pass
    con.execute(
        "INSERT INTO ayar(anahtar, deger) VALUES(?, ?) ON CONFLICT(anahtar) DO UPDATE SET deger=excluded.deger",
        (anahtar, yeni),
    )
    con.commit()


def son_dolu_ayar(con: sqlite3.Connection, anahtar: str):
    """Ayar geçmişinde bu anahtarın boş olmayan son değeri (yoksa None)."""
    try:
        for r in con.execute("SELECT yeni, eski FROM ayar_gecmis WHERE anahtar=? ORDER BY zaman DESC", (anahtar,)):
            for v in (r[0], r[1]):
                if v and json.loads(v):
                    return json.loads(v)
    except Exception:  # noqa: BLE001
        pass
    return None


# ------------------------------------------------------------------ kayıtlar
def kayit_yaz(con: sqlite3.Connection, satirlar: Iterable[tuple]) -> Tuple[int, int, int]:
    """satirlar: (makine, başlangıç dt, bitiş dt, operatör, tip, iş emri, ürün adı, ürün kodu)
    Dönüş: (yeni, güncellenen, aynı). Anahtar = makine + başlangıç + tip; aynı kayıt tekrar gelirse çoğalmaz.
    """
    satirlar = list(satirlar)
    if not satirlar:
        return 0, 0, 0
    ilk = min(s[1] for s in satirlar).strftime(BICIM)
    son = max(s[1] for s in satirlar).strftime(BICIM)
    mevcut = {}
    for r in con.execute(
        "SELECT makine, baslangic, bitis, operator, tip, is_emri, urun_adi, urun_kodu FROM kayit "
        "WHERE baslangic BETWEEN ? AND ?", (ilk, son)
    ):
        mevcut[(r["makine"], r["baslangic"], r["tip"])] = (r["bitis"], r["operator"], r["is_emri"], r["urun_adi"], r["urun_kodu"])

    yeni = guncel = ayni = 0
    yazilacak = {}
    for makine, bas, bit, op, tip, emri, urun, kod in satirlar:
        anahtar = (makine, bas.strftime(BICIM), tip or "")
        deger = (bit.strftime(BICIM), op, emri, urun, kod)
        if anahtar not in yazilacak and anahtar in mevcut:
            if mevcut[anahtar] == deger:
                ayni += 1
                continue
            guncel += 1
        elif anahtar in yazilacak:
            pass  # dosya içinde tekrar: sonuncusu geçerli, sayıma eklenmez
        else:
            yeni += 1
        yazilacak[anahtar] = deger
    con.executemany(
        "INSERT INTO kayit(makine, baslangic, tip, bitis, operator, is_emri, urun_adi, urun_kodu) VALUES(?,?,?,?,?,?,?,?) "
        "ON CONFLICT(makine, baslangic, tip) DO UPDATE SET bitis=excluded.bitis, operator=excluded.operator, "
        "is_emri=excluded.is_emri, urun_adi=excluded.urun_adi, urun_kodu=excluded.urun_kodu",
        [(k[0], k[1], k[2]) + v for k, v in yazilacak.items()],
    )
    con.commit()
    gun_ozet_yenile(con, ilk, son)
    _sozluge_ekle(con, ((s[0], s[3], s[4]) for s in satirlar))
    return yeni, guncel, ayni


def _sozluge_ekle(con: sqlite3.Connection, uclu) -> None:
    ekle = set()
    for makine, op, tip in uclu:
        if makine:
            ekle.add(("makine", makine))
        if op:
            ekle.add(("operator", op))
        if tip:
            ekle.add(("tip", tip))
    con.executemany("INSERT OR IGNORE INTO sozluk(tur, deger) VALUES(?,?)", sorted(ekle))
    con.commit()


def sozluk_hazir(con: sqlite3.Connection) -> bool:
    return con.execute("SELECT 1 FROM sozluk WHERE tur='_hazir'").fetchone() is not None


def sozluk_doldur(con: sqlite3.Connection) -> None:
    """Bir defalık: kayıtları ay ay (en yeni aydan geriye) tarayıp sözlüğü doldurur; sonra kayit_yaz güncel tutar.
    Her ay ayrı okunup hemen kaydedilir: yarıda kalırsa bir sonraki açılışta kaldığı aydan sürer, veri tabanı uzun süre
    kilitlenmez ve listeler en son aylardan başlayarak hemen dolmaya başlar."""
    if sozluk_hazir(con):
        return
    r = con.execute("SELECT MIN(gun), MAX(gun) FROM gun_ozet").fetchone()
    if r and r[0]:
        bitmis = {x[0] for x in con.execute("SELECT deger FROM sozluk WHERE tur='_ay'")}
        y, a = int(r[1][:4]), int(r[1][5:7])
        en_eski = r[0][:7]
        while f"{y:04d}-{a:02d}" >= en_eski:
            ay = f"{y:04d}-{a:02d}"
            if ay not in bitmis:
                sy, sa = (y + 1, 1) if a == 12 else (y, a + 1)
                _sozluge_ekle(con, con.execute("SELECT DISTINCT makine, operator, tip FROM kayit WHERE baslangic >= ? "
                                               "AND baslangic < ?", (ay + "-01", f"{sy:04d}-{sa:02d}-01")))
                con.execute("INSERT OR IGNORE INTO sozluk(tur, deger) VALUES('_ay', ?)", (ay,))
                con.commit()
            y, a = (y - 1, 12) if a == 1 else (y, a - 1)
    con.execute("INSERT OR IGNORE INTO sozluk(tur, deger) VALUES('_hazir', '1')")
    con.execute("DELETE FROM sozluk WHERE tur='_ay'")
    con.commit()


_SOZLUK_IS = None


_OKUMA: dict = {}
_OKUMA_KILIT = None


def okuma_baglantisi(yol: str):
    """Ayrıntı (kırılım) hesapları için arka planda tek, sürekli açık okuma bağlantısı: her tıklamada ağ diskinden yeni
    bağlantı açılıp önbellek soğuk başlamasın, şema yeniden denetlenmesin. (bağlantı, kilit) döner; kilitle kullanın."""
    import threading
    global _OKUMA_KILIT
    if _OKUMA_KILIT is None:
        _OKUMA_KILIT = threading.Lock()
    c = _OKUMA.get(yol)
    if c is None:
        c = sqlite3.connect(yol, timeout=30, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA cache_size = -65536")
        _OKUMA[yol] = c
    return c, _OKUMA_KILIT


def sozluk_arkada_doldur(yol: str) -> None:
    """Sözlüğü arka planda (kendi bağlantısıyla) hazırlar; program bu sırada donmadan kullanılabilir.
    Zaten çalışıyorsa ya da hazırsa bir şey yapmaz."""
    import threading
    global _SOZLUK_IS
    if _SOZLUK_IS is not None and _SOZLUK_IS.is_alive():
        return

    def _is():
        try:
            c = ac(yol)
            try:
                sozluk_doldur(c)
            finally:
                c.close()
        except Exception:  # noqa: BLE001  (yarım kalırsa bir sonraki çağrıda kaldığı yerden sürer)
            pass
    _SOZLUK_IS = threading.Thread(target=_is, name="sozluk", daemon=True)
    _SOZLUK_IS.start()


def sozluk_degerleri(con: sqlite3.Connection, tur: str) -> List[str]:
    """Sözlükteki adlar. Asla tüm tabloyu taramaz: sözlük henüz hazırlanıyorsa o ana kadar bulunanlar döner."""
    return [r[0] for r in con.execute("SELECT deger FROM sozluk WHERE tur=? ORDER BY deger", (tur,))]


def toplam_kayit(con: sqlite3.Connection) -> int:
    return con.execute("SELECT COALESCE(SUM(kayit), 0) FROM gun_ozet").fetchone()[0]


def _kirp(bas_s: str, bit_s: str, alt: datetime, ust: datetime) -> Tuple[datetime, datetime]:
    """Kaydı istenen aralığa kırpar. Aylarca süren (ya da hiç kapatılmamış) bir kayıt, yalnızca seçili günler için
    gerekirken baştan sona vardiya vardiya bölünmesin diye: binlerce böyle kayıt hesabı dakikalarca kilitliyordu."""
    bas, bit = zaman(bas_s), zaman(bit_s)
    return (alt if bas < alt else bas), (ust if bit > ust else bit)


def zaman(s: str) -> datetime:
    """'2026-11-12 08:15:30' -> datetime; strptime'dan çok daha hızlı (binlerce kayıtta fark eder)."""
    try:
        return datetime(int(s[0:4]), int(s[5:7]), int(s[8:10]), int(s[11:13]), int(s[14:16]), int(s[17:19]))
    except (ValueError, IndexError, TypeError):
        return datetime.strptime(s, BICIM)


def kayitlari_getir(con: sqlite3.Connection, ilk: date, son: date, kirp: bool = True) -> List[Tuple[str, str, datetime, datetime]]:
    """[ilk, son] günlerine değen kayıtlar (önceki günden başlayıp içeri uzayanlar dahil).
    kirp: kayıtların aralık dışına taşan kısmı atılır (sonuç aynıdır, hesap çok hızlanır)."""
    bas = ilk.strftime("%Y-%m-%d 00:00:00")
    bit = (son + timedelta(days=1)).strftime("%Y-%m-%d 00:00:00")
    alt, ust = datetime(ilk.year, ilk.month, ilk.day), datetime(son.year, son.month, son.day) + timedelta(days=1)
    sonuc = []
    for r in aralik_satirlari(con, "makine, tip, baslangic, bitis", ilk, son, hatali_etiket=True):
        if kirp:
            b0, b1 = _kirp(r["baslangic"], r["bitis"], alt, ust)
        else:
            b0, b1 = zaman(r["baslangic"]), zaman(r["bitis"])
        sonuc.append((r["makine"], r["tip"], b0, b1))
    return sonuc


def kayitlari_getir_operatorlu(con: sqlite3.Connection, ilk: date, son: date, kirp: bool = True):
    """[ilk, son] günlerine değen kayıtlar, operatör adıyla: (operatör, makine, tip, başlangıç, bitiş)."""
    bas = ilk.strftime("%Y-%m-%d 00:00:00")
    bit = (son + timedelta(days=1)).strftime("%Y-%m-%d 00:00:00")
    alt, ust = datetime(ilk.year, ilk.month, ilk.day), datetime(son.year, son.month, son.day) + timedelta(days=1)
    sonuc = []
    for r in aralik_satirlari(con, "operator, makine, tip, baslangic, bitis", ilk, son, hatali_etiket=True):
        if kirp:
            b0, b1 = _kirp(r["baslangic"], r["bitis"], alt, ust)
        else:
            b0, b1 = zaman(r["baslangic"]), zaman(r["bitis"])
        sonuc.append((r["operator"] or "", r["makine"], r["tip"], b0, b1))
    return sonuc


def gun_kapsami(con: sqlite3.Connection) -> Dict[date, int]:
    """Başlangıç gününe göre kayıt sayısı (takvimde 'verisi olan günler' için); küçük özet tablodan okunur."""
    return {date.fromisoformat(r[0]): r[1] for r in con.execute("SELECT gun, kayit FROM gun_ozet WHERE kayit > 0 ORDER BY gun")}


def makineler_kayitta(con: sqlite3.Connection) -> List[str]:
    return sozluk_degerleri(con, "makine")


def aktarim_kaydet(con, dosya, toplam, yeni, guncel, ayni, atlanan, ilk_gun, son_gun):
    con.execute(
        "INSERT INTO aktarim(zaman, dosya, toplam, yeni, guncellenen, ayni, atlanan, ilk_gun, son_gun) VALUES(?,?,?,?,?,?,?,?,?)",
        (datetime.now().strftime(BICIM), dosya, toplam, yeni, guncel, ayni, atlanan, ilk_gun, son_gun),
    )
    con.commit()


def aktarim_gecmisi(con, limit=30):
    return [dict(r) for r in con.execute("SELECT * FROM aktarim ORDER BY id DESC LIMIT ?", (limit,))]


# ------------------------------------------------------------------ şefler
def sef_getir(con: sqlite3.Connection, gunler: List[date], ayar: dict) -> Dict[int, str]:
    """Her vardiya için şef adı. Dönemde birden fazla şef çalıştıysa 'A / B' biçiminde döner."""
    varsayilan = ayar.get("vardiya_sef", {})
    sonuc: Dict[int, List[str]] = {1: [], 2: [], 3: []}
    atanan = {}
    if gunler:
        for r in con.execute(
            "SELECT tarih, vardiya, sef FROM sef_atama WHERE tarih BETWEEN ? AND ?",
            (min(gunler).isoformat(), max(gunler).isoformat()),
        ):
            atanan[(r["tarih"], r["vardiya"])] = r["sef"]
    try:                                                   # personel vardiya listesindeki CNC grup liderleri öncelikli
        from .personel_veri import cnc_liderleri
        pv_lider = cnc_liderleri(con, gunler or [], ayar) if gunler else {}
    except Exception:  # noqa: BLE001
        pv_lider = {}
    for g in gunler or [None]:
        for v in (1, 2, 3):
            adlar = pv_lider.get((g, v)) if g else None
            if not adlar:
                ad = atanan.get((g.isoformat(), v)) if g else None
                adlar = [ad or varsayilan.get(str(v), "")]
            for ad in adlar:
                if ad and ad not in sonuc[v]:
                    sonuc[v].append(ad)
    return {v: " / ".join(x) for v, x in sonuc.items()}


def sef_ata(con: sqlite3.Connection, gunler: List[date], vardiya: int, sef: str) -> None:
    for g in gunler:
        con.execute(
            "INSERT INTO sef_atama(tarih, vardiya, sef) VALUES(?,?,?) "
            "ON CONFLICT(tarih, vardiya) DO UPDATE SET sef=excluded.sef",
            (g.isoformat(), vardiya, sef),
        )
    con.commit()


# ------------------------------------------------------------------ görseller (Cormind ekran görüntüsü)
def gorsel_yaz(con, anahtar: str, png: bytes) -> None:
    con.execute(
        "INSERT INTO gorsel(anahtar, png, zaman) VALUES(?,?,?) ON CONFLICT(anahtar) DO UPDATE SET png=excluded.png, zaman=excluded.zaman",
        (anahtar, png, datetime.now().strftime(BICIM)),
    )
    con.commit()


def gorsel_oku(con, anahtar: str) -> Optional[bytes]:
    r = con.execute("SELECT png FROM gorsel WHERE anahtar=?", (anahtar,)).fetchone()
    return bytes(r["png"]) if r else None


def gorsel_sil(con, anahtar: str) -> None:
    con.execute("DELETE FROM gorsel WHERE anahtar=?", (anahtar,))
    con.commit()


# ------------------------------------------------------------------ arşiv
def arsiv_kaydet(con, ad, tur, ilk_gun, son_gun, ayar_json, sonuc_json, pdf: Optional[bytes] = None) -> int:
    cur = con.execute(
        "INSERT INTO arsiv(ad, tur, olusturma, ilk_gun, son_gun, ayar_json, sonuc_json, pdf) VALUES(?,?,?,?,?,?,?,?)",
        (ad, tur, datetime.now().strftime(BICIM), ilk_gun, son_gun, ayar_json, sonuc_json, pdf),
    )
    con.commit()
    return cur.lastrowid


def arsiv_liste(con) -> List[dict]:
    return [dict(r) for r in con.execute(
        "SELECT id, ad, tur, olusturma, ilk_gun, son_gun, (pdf IS NOT NULL) AS pdf_var FROM arsiv ORDER BY id DESC")]


def arsiv_getir(con, id_: int) -> Optional[dict]:
    r = con.execute("SELECT * FROM arsiv WHERE id=?", (id_,)).fetchone()
    return dict(r) if r else None


def arsiv_sil(con, id_: int) -> None:
    con.execute("DELETE FROM arsiv WHERE id=?", (id_,))
    con.commit()


# ------------------------------------------------------------------ KOT kayıtları (grup lideri bildirimleri)
def kot_yaz(con, kotlar) -> Tuple[int, int]:
    """KOT kayıtlarını saklar; aynı KOT NO varsa günceller. (yeni, güncellenen) döner."""
    from dataclasses import asdict
    yeni = guncel = 0
    for k in kotlar:
        var = con.execute("SELECT 1 FROM kot WHERE no=?", (k.no,)).fetchone()
        d = asdict(k)
        d["tarih"] = k.tarih.isoformat()
        con.execute("INSERT INTO kot(no, tarih, saat, vardiya, veri) VALUES(?,?,?,?,?) "
                    "ON CONFLICT(no) DO UPDATE SET tarih=excluded.tarih, saat=excluded.saat, vardiya=excluded.vardiya, veri=excluded.veri",
                    (k.no, d["tarih"], k.saat, k.vardiya, json.dumps(d, ensure_ascii=False)))
        if var:
            guncel += 1
        else:
            yeni += 1
    con.commit()
    return yeni, guncel


def kot_getir(con, ilk: date, son: date) -> list:
    from .kot import Kot, KotTezgah
    sonuc = []
    for r in con.execute("SELECT veri FROM kot WHERE tarih BETWEEN ? AND ? ORDER BY tarih, saat", (ilk.isoformat(), son.isoformat())):
        d = json.loads(r["veri"])
        tz = [KotTezgah(**t) for t in d.pop("tezgahlar", [])]
        d["tarih"] = date.fromisoformat(d["tarih"])
        sonuc.append(Kot(tezgahlar=tz, **d))
    return sonuc


def kot_sil(con, ilk: date, son: date) -> int:
    n = con.execute("DELETE FROM kot WHERE tarih BETWEEN ? AND ?", (ilk.isoformat(), son.isoformat())).rowcount
    con.commit()
    return n


def metin_oku(con, anahtar: str) -> Optional[str]:
    r = con.execute("SELECT icerik FROM metin WHERE anahtar=?", (anahtar,)).fetchone()
    return r["icerik"] if r else None


def metin_yaz(con, anahtar: str, icerik: Optional[str]) -> None:
    if icerik is None:
        con.execute("DELETE FROM metin WHERE anahtar=?", (anahtar,))
    else:
        con.execute("INSERT INTO metin(anahtar, icerik) VALUES(?,?) ON CONFLICT(anahtar) DO UPDATE SET icerik=excluded.icerik", (anahtar, icerik))
    con.commit()


def personel_listesi(con: sqlite3.Connection) -> List[str]:
    """Kayıtlarda geçen tüm personel (operatör) adları, alfabetik."""
    from .operator import operator_adi                 # '-' gibi harfsiz değerler personel sayılmaz
    return sorted({ad for r in sozluk_degerleri(con, "operator") if (ad := operator_adi(r))},
                  key=lambda s: s.casefold())


def haric_personel(con: sqlite3.Connection) -> set:
    """Ayarlar'da hariç tutulan personel (Operatör sekmesine ve 'operatör varken duran makine' uyarısına girmez)."""
    return set(ayar_oku(con).get("haric_personel") or [])
