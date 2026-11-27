"""Çekim kaydı: otomatik ve elle yapılan her veri çekiminin sonucu (yalnızca programda görünür, web'de YOK).

Her satır: zaman, bilgisayar, tür (Cormind / Personel; otomatik / elle), tarih aralığı, sonuç (tamam / eksik / hata),
kısa özet ve ayrıntı. Son 90 gün tutulur. Sağlık özeti: son başarılı çekimler, eksik günler, tekrarlayan uyarılar.
"""
from __future__ import annotations

import json
import socket
from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple

TAMAM, EKSIK, HATA = "tamam", "eksik", "hata"
SONUC_YAZI = {TAMAM: "✓ tamam", EKSIK: "⚠ eksik", HATA: "✗ hata"}
SONUC_RENK = {TAMAM: "#3e9b2a", EKSIK: "#d99a00", HATA: "#d64541"}
SAKLA_GUN = 90

SEMA = """CREATE TABLE IF NOT EXISTS cekim_kaydi (id INTEGER PRIMARY KEY AUTOINCREMENT, zaman TEXT NOT NULL, pc TEXT,
    tur TEXT NOT NULL, ilk TEXT, son TEXT, sonuc TEXT NOT NULL, ozet TEXT, ayrinti TEXT)"""


def _hazirla(con):
    con.execute(SEMA)


def yaz(con, tur: str, ilk: Optional[date], son: Optional[date], sonuc: str, ozet: str, ayrinti=None) -> None:
    """Bir çekimin sonucunu yazar. Hata verirse sessizce geçer (kayıt tutmak çekimi asla bozmaz)."""
    try:
        _hazirla(con)
        con.execute("INSERT INTO cekim_kaydi (zaman, pc, tur, ilk, son, sonuc, ozet, ayrinti) VALUES (?,?,?,?,?,?,?,?)",
                    (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), socket.gethostname(), tur,
                     ilk.isoformat() if ilk else None, son.isoformat() if son else None, sonuc, (ozet or "")[:1000],
                     ayrinti if isinstance(ayrinti, str) or ayrinti is None else json.dumps(ayrinti, ensure_ascii=False, default=str)[:20000]))
        con.execute("DELETE FROM cekim_kaydi WHERE zaman < ?", ((datetime.now() - timedelta(days=SAKLA_GUN)).strftime("%Y-%m-%d"),))
        con.commit()
    except Exception:  # noqa: BLE001
        pass


def liste(con, adet: int = 500) -> List[dict]:
    try:
        _hazirla(con)
        cur = con.execute("SELECT id, zaman, pc, tur, ilk, son, sonuc, ozet, ayrinti FROM cekim_kaydi ORDER BY zaman DESC, id DESC LIMIT ?", (adet,))
        ad = [c[0] for c in cur.description]
        return [dict(zip(ad, r)) for r in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []


# ---------------------------------------------------------------- sonuçtan sınıflandırma
def cormind_sonucu(r: dict) -> Tuple[str, str]:
    """Cormind çekim sonucu sözlüğü → (sonuç, özet)."""
    from .cormind import dogrulama_yazi
    parca = [f"{r.get('toplam', 0):,} kayıt".replace(",", ".")]
    sonuc = TAMAM
    if r.get("durduruldu"):
        sonuc = EKSIK
        parca.append(f"durduruldu ({r.get('biten_parca')}/{r.get('parca_sayisi')} ay)")
    if r.get("dar_sorgu"):
        sonuc = EKSIK
        parca.append("geniş sorgu kabul edilmedi (uzanan duruşlar eksik olabilir)")
    if r.get("kesildi"):
        sonuc = EKSIK
        parca.append("çok kayıt geldiği için sınırda kesildi")
    if not r.get("toplam"):
        sonuc = EKSIK
        parca.append("hiç kayıt gelmedi")
    d = r.get("dogrulama")
    if d:
        parca.append(dogrulama_yazi(d))
        if d.get("hata"):
            sonuc = EKSIK
    return sonuc, " · ".join(parca)


def personel_sonucu(basarili: bool, metin: str) -> str:
    if not basarili:
        return HATA
    m = metin or ""
    if "EKSİK" in m or "personel 0/" in m or "atlandı" in m or "alınamadı" in m:
        return EKSIK
    return TAMAM


# ---------------------------------------------------------------- sağlık özeti
def saglik(con) -> List[Tuple[str, str, str]]:
    """[(başlık, sonuç, açıklama)] — Veri Aktar'ın üstündeki kutular."""
    kayit = liste(con, 400)
    sonuc = []

    def son_basarili(onek):
        for k in kayit:
            if k["tur"].startswith(onek) and k["sonuc"] in (TAMAM, EKSIK):
                return k
        return None

    def son_herhangi(onek):
        return next((k for k in kayit if k["tur"].startswith(onek)), None)

    for onek, ad in (("Cormind", "Cormind"), ("Personel", "Personel verisi")):
        k, h = son_basarili(onek), son_herhangi(onek)
        if h is None:
            sonuc.append((ad, EKSIK, "henüz kayıtlı çekim yok"))
            continue
        z = datetime.strptime(h["zaman"], "%Y-%m-%d %H:%M:%S")
        yas = (datetime.now() - z).total_seconds() / 3600
        durum = h["sonuc"]
        acik = f"son çekim {z:%d.%m %H:%M} · {SONUC_YAZI[durum]}"
        if k is not None and k is not h:
            acik += f" · son başarılı {k['zaman'][8:10]}.{k['zaman'][5:7]} {k['zaman'][11:16]}"
        if yas > 30:
            durum = HATA if durum != TAMAM or yas > 50 else EKSIK
            acik += f" · {int(yas)} saattir yeni çekim yok"
        sonuc.append((ad, durum, acik))
    # tekrarlayan uyarı: aynı türde art arda eksik / hata
    for onek, ad in (("Cormind", "Cormind"), ("Personel", "Personel verisi")):
        art = 0
        for k in kayit:
            if not k["tur"].startswith(onek):
                continue
            if k["sonuc"] == TAMAM:
                break
            art += 1
        if art >= 2:
            sonuc.append((f"{ad} uyarısı", HATA, f"son {art} çekim tamam değil — ayrıntıya bakın"))
    # Cormind'de eksik gün (dün dahil son 7 gün)
    try:
        from . import veritabani as vt
        kap = set(vt.gun_kapsami(con))
        bugun = date.today()
        eksik = [bugun - timedelta(days=i) for i in range(1, 8) if (bugun - timedelta(days=i)) not in kap]
        if eksik:
            sonuc.append(("Cormind eksik gün", HATA, "verisi olmayan gün: " + ", ".join(f"{g:%d.%m}" for g in sorted(eksik))))
    except Exception:  # noqa: BLE001
        pass
    return sonuc
