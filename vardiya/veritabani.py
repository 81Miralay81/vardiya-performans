"""SQLite veri tabanı: kayıtlar, ayarlar, şef atamaları, arşiv, yapıştırılan görseller."""
from __future__ import annotations

import json
import os
import sqlite3
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
    "vardiya_dk": 480,
    "yemek_dk": 30,
    "cay_dk": 10,
    "makineler": VARSAYILAN_MAKINELER,
    "sefler": ["Güryay", "Bülent", "Serhat"],
    "vardiya_sef": {"1": "Güryay", "2": "Bülent", "3": "Serhat"},
    "idle_makineleri_goster": False,
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
    con = sqlite3.connect(yol, timeout=30)
    con.row_factory = sqlite3.Row
    con.executescript(SEMA)
    con.commit()
    return con


# ------------------------------------------------------------------ ayarlar
def ayar_oku(con: sqlite3.Connection) -> dict:
    sonuc = json.loads(json.dumps(VARSAYILAN_AYAR))
    for r in con.execute("SELECT anahtar, deger FROM ayar"):
        try:
            sonuc[r["anahtar"]] = json.loads(r["deger"])
        except ValueError:
            pass
    return sonuc


def ayar_yaz(con: sqlite3.Connection, anahtar: str, deger) -> None:
    con.execute(
        "INSERT INTO ayar(anahtar, deger) VALUES(?, ?) ON CONFLICT(anahtar) DO UPDATE SET deger=excluded.deger",
        (anahtar, json.dumps(deger, ensure_ascii=False)),
    )
    con.commit()


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
    return yeni, guncel, ayni


def kayitlari_getir(con: sqlite3.Connection, ilk: date, son: date) -> List[Tuple[str, str, datetime, datetime]]:
    """[ilk, son] günlerine değen kayıtlar (önceki günden başlayıp içeri uzayanlar dahil)."""
    bas = ilk.strftime("%Y-%m-%d 00:00:00")
    bit = (son + timedelta(days=1)).strftime("%Y-%m-%d 00:00:00")
    sonuc = []
    for r in con.execute(
        "SELECT makine, tip, baslangic, bitis FROM kayit WHERE baslangic < ? AND bitis >= ?", (bit, bas)
    ):
        sonuc.append((r["makine"], r["tip"], datetime.strptime(r["baslangic"], BICIM), datetime.strptime(r["bitis"], BICIM)))
    return sonuc


def gun_kapsami(con: sqlite3.Connection) -> Dict[date, int]:
    """Başlangıç gününe göre kayıt sayısı (takvimde 'verisi olan günler' için)."""
    return {
        datetime.strptime(r[0], "%Y-%m-%d").date(): r[1]
        for r in con.execute("SELECT substr(baslangic,1,10) g, COUNT(*) FROM kayit GROUP BY g ORDER BY g")
    }


def makineler_kayitta(con: sqlite3.Connection) -> List[str]:
    return [r[0] for r in con.execute("SELECT DISTINCT makine FROM kayit ORDER BY makine")]


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
    for g in gunler or [None]:
        for v in (1, 2, 3):
            ad = atanan.get((g.isoformat(), v)) if g else None
            ad = ad or varsayilan.get(str(v), "")
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
