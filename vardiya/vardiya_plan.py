"""Vardiya planı: personel sistemine haftalık vardiya yazma kuralları (ekran: sayfa_plan.py).

Kullanıcının kuralı (27.11):
  1. vardiya (00–08) → 24:00-08:00 · 2. vardiya (08–16) → 08:00-16:00 · 3. vardiya (16–24) → 16:00-24:00
  Cuma: yalnızca 2. vardiyaya "(CUMA) 08:00-16:00" (Cuma namazı). Cumartesi normal çalışma günü.
  Pazar: 2. → Hafta Tatili 08 · 3. → Hafta Tatili 16 · 1. → Hafta Tatili 24.
  Haftalık dönüş geriye: 3 → 2 → 1 → 3 ("döner" işaretli kişiler; "sabit" olanlar aynı kalır).
Beyaz yaka planlamaya girmez. Elle yapılan değişiklik her zaman önceliklidir.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

# personel sistemindeki mesai numaraları (Vardiya Plan ekranındaki "Mesailer" listesi, 27.11.2026)
MESAI: Dict[str, int] = {
    "08:00-16:00": 5, "16:00-24:00": 6, "24:00-08:00": 7, "(CUMA) 08:00-16:00": 17,
    "Hafta Tatili 08": 8, "Hafta Tatili 16": 9, "Hafta Tatili 24": 10,
    "BY 08:00-18:00": 1, "BY Cumartesi": 2, "BY Hafta Tatili": 3, "Istanbul 09:00-18:00": 4,
    "MY 08:00-18:00": 11, "MY Cumartesi": 12, "MY Hafta Tatili": 13,
    "Kautek 08:00-18:00": 14, "Kautek Cumartesi": 15, "Kautek Hafta Tatili": 16,
    "(CUMA) BY 08:00-18:00": 18, "(CUMA) MY 08:00-18:00": 19,
}
SECILEBILIR = ["24:00-08:00", "08:00-16:00", "16:00-24:00", "(CUMA) 08:00-16:00", "Hafta Tatili 24", "Hafta Tatili 08", "Hafta Tatili 16"]

VARDIYA_AD = {1: "1. vardiya (00–08)", 2: "2. vardiya (08–16)", 3: "3. vardiya (16–24)"}
GUN_AD = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
DONUS = {3: 2, 2: 1, 1: 3}

_KURAL = {
    1: ["24:00-08:00"] * 6 + ["Hafta Tatili 24"],
    2: ["08:00-16:00"] * 4 + ["(CUMA) 08:00-16:00", "08:00-16:00", "Hafta Tatili 08"],
    3: ["16:00-24:00"] * 6 + ["Hafta Tatili 16"],
}
_VARDIYASI = {"24:00-08:00": 1, "08:00-16:00": 2, "(CUMA) 08:00-16:00": 2, "16:00-24:00": 3}


def hafta_basi(g: date) -> date:
    return g - timedelta(days=g.weekday())


def gunler(pzt: date) -> List[date]:
    return [pzt + timedelta(days=i) for i in range(7)]


def kural(vardiya: int) -> List[str]:
    """Haftalık vardiya → Pazartesi..Pazar mesai adları."""
    return list(_KURAL[vardiya])


def hucre_ad(s) -> str:
    """Personel sistemindeki plan hücresi ("08:00-16:00,white,-55_2_59" ya da "*16:00-24:00") → mesai adı."""
    s = str(s or "").split("<br>")[0].split(",")[0].strip()
    return s.lstrip("*?").strip()


def vardiya_tahmin(adlar: List[str]) -> Optional[int]:
    """Bir haftanın mesai adlarından kişinin vardiyası (Pzt–Cmt çoğunluğu); bulunamazsa None."""
    say: Dict[int, int] = {}
    for a in adlar[:6]:
        v = _VARDIYASI.get(a)
        if v:
            say[v] = say.get(v, 0) + 1
    if not say:
        return None
    v, n = max(say.items(), key=lambda x: x[1])
    return v if n >= 3 else None


def dondur(v: Optional[int]) -> Optional[int]:
    return DONUS.get(v) if v else None


def plan_satirlari(cevap: list, pzt: date) -> List[dict]:
    """Personel sisteminin haftalık plan yanıtı → [{sicilid, ad, sicilno, gun: [7 ad]}] (özet satırları atlanır)."""
    sonuc = []
    for r in cevap or []:
        try:
            sid = int(r.get("ysicilid"))
        except (TypeError, ValueError):
            continue                                     # "m17" gibi vardiya sayım satırları
        gun = [hucre_ad(r.get(f"y{g.year}x{g.month:02d}x{g.day:02d}")) for g in gunler(pzt)]
        sonuc.append({"sicilid": sid, "ad": str(r.get("ypersonel") or "").strip(), "sicilno": str(r.get("ysicilno") or ""), "gun": gun})
    return sonuc


def hedef(secim: Optional[int], mevcut: List[str], elle: Dict[int, str]) -> List[str]:
    """Bir kişinin yazılacak haftası: seçim yoksa mevcut korunur; elle değiştirilen gün her zaman önceliklidir."""
    h = kural(secim) if secim else list(mevcut)
    for i, a in elle.items():
        h[i] = a
    return h


def degisiklikler(pzt: date, kisi: dict, secim: Optional[int], elle: Dict[int, str]) -> List[Tuple[date, str, str]]:
    """[(gün, eski, yeni)] — yalnızca farklı olan günler."""
    h = hedef(secim, kisi["gun"], elle)
    return [(g, e, y) for g, e, y in zip(gunler(pzt), kisi["gun"], h) if y and y != e]
