"""Cormind Excel/CSV dosyasını okur. Hatalı satırlar atlanır, tekrar eden kayıt çoğalmaz."""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple

from . import veritabani as vt
from .hesap import tr_kucuk

SUTUNLAR = {
    "makine": ("makine adı", "makine adi", "makine"),
    "operator": ("operatör", "operator"),
    "tip": ("tip",),
    "is_emri": ("iş emri", "is emri"),
    "urun_adi": ("ürün adı", "urun adi"),
    "urun_kodu": ("ürün kodu", "urun kodu"),
    "bas": ("başlangıç tarihi", "baslangic tarihi", "başlangıç", "baslangic"),
    "bit": ("bitiş tarihi", "bitis tarihi", "bitiş", "bitis"),
}
SIRA = ["makine", "operator", "tip", "is_emri", "urun_adi", "urun_kodu", "sure", "bas", "bit"]  # A..I (başlık yoksa)

TARIH_BICIMLERI = ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S",
                   "%Y-%m-%dT%H:%M:%S", "%d.%m.%Y")


def tarih_oku(v) -> Optional[datetime]:
    """Tarih hücresi: gerçek tarih, Excel seri numarası ya da 'gg.aa.yyyy ss:dd:ss' metni olabilir."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.replace(microsecond=0)
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day)
    if isinstance(v, (int, float)):
        if 20000 < v < 80000:
            return (datetime(1899, 12, 30) + timedelta(days=float(v))).replace(microsecond=0)
        return None
    if isinstance(v, str):
        s = v.strip()
        if not s or s.startswith("#"):
            return None
        for b in TARIH_BICIMLERI:
            try:
                return datetime.strptime(s, b)
            except ValueError:
                continue
    return None


def _metin(v) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return "" if v.strip().startswith("#") else v.strip()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


@dataclass
class AktarimSonuc:
    dosya: str
    toplam: int = 0
    yeni: int = 0
    guncellenen: int = 0
    ayni: int = 0
    atlanan: List[Tuple[int, str]] = field(default_factory=list)
    ilk_gun: Optional[date] = None
    son_gun: Optional[date] = None
    yeni_makineler: List[str] = field(default_factory=list)
    gunler: dict = field(default_factory=dict)  # gün -> kayıt sayısı (dosyadaki)

    def ozet(self) -> str:
        return (f"{self.toplam} satır okundu: {self.yeni} yeni, {self.guncellenen} güncellendi, "
                f"{self.ayni} zaten vardı, {len(self.atlanan)} hatalı satır atlandı.")


def _satirlar(yol: str):
    """(satır_no, hücre listesi) üretir; başlık satırını bulup yalnızca veri satırlarını döndürür."""
    uzanti = os.path.splitext(yol)[1].lower()
    if uzanti == ".csv":
        ham = open(yol, "rb").read()
        for kod in ("utf-8-sig", "cp1254"):
            try:
                metin = ham.decode(kod)
                break
            except UnicodeDecodeError:
                continue
        ayrac = ";" if metin.count(";") >= metin.count(",") else ","
        kaynak = [list(r) for r in csv.reader(metin.splitlines(), delimiter=ayrac)]
        yield from _baslik_ve_veri(enumerate(kaynak, start=1))
        return
    from openpyxl import load_workbook
    wb = load_workbook(yol, read_only=True, data_only=True)
    try:
        adaylar = sorted(wb.worksheets, key=lambda w: 0 if tr_kucuk(w.title) == "sayfa1" else 1)
        for ws in adaylar:
            sonuc = list(_baslik_ve_veri(enumerate(ws.iter_rows(values_only=True), start=1), sessiz=True))
            if sonuc:
                yield from sonuc
                return
    finally:
        wb.close()


def _baslik_ve_veri(satirlar, sessiz=False):
    harita = None
    for no, hucre in satirlar:
        hucre = list(hucre)
        if harita is None:
            adlar = [tr_kucuk(_metin(h)) for h in hucre]
            if any(a in SUTUNLAR["bas"] for a in adlar) and any(a in SUTUNLAR["makine"] for a in adlar):
                harita = {}
                for anahtar, secenekler in SUTUNLAR.items():
                    for i, a in enumerate(adlar):
                        if a in secenekler:
                            harita[anahtar] = i
                            break
            continue
        yield no, hucre, harita
    if harita is None and not sessiz:
        return


def oku(yol: str) -> Tuple[list, AktarimSonuc]:
    """Dosyayı okur, geçerli satırları (veri tabanına yazmadan) döndürür."""
    sonuc = AktarimSonuc(dosya=os.path.basename(yol))
    gecerli = []
    gorulen_baslik = False
    for no, hucre, harita in _satirlar(yol):
        gorulen_baslik = True

        def al(anahtar):
            i = harita.get(anahtar)
            return hucre[i] if i is not None and i < len(hucre) else None

        makine = _metin(al("makine"))
        bas = tarih_oku(al("bas"))
        bit = tarih_oku(al("bit"))
        if not makine and bas is None and bit is None:
            continue  # tamamen boş satır
        sonuc.toplam += 1
        if not makine:
            sonuc.atlanan.append((no, "makine adı boş"))
            continue
        if bas is None or bit is None:
            sonuc.atlanan.append((no, "tarih okunamadı / hatalı"))
            continue
        if bit < bas:
            sonuc.atlanan.append((no, "bitiş başlangıçtan önce"))
            continue
        gecerli.append((makine, bas, bit, _metin(al("operator")), _metin(al("tip")), _metin(al("is_emri")),
                        _metin(al("urun_adi")), _metin(al("urun_kodu"))))
    if not gorulen_baslik and not gecerli:
        raise ValueError("Dosyada 'Makine Adı' ve 'Başlangıç Tarihi' başlıklı bir liste bulunamadı.")
    return gecerli, sonuc


def aktar(con, yol: str) -> AktarimSonuc:
    gecerli, sonuc = oku(yol)
    if gecerli:
        sonuc.yeni, sonuc.guncellenen, sonuc.ayni = vt.kayit_yaz(con, gecerli)
        gunler = {}
        for s in gecerli:
            gunler[s[1].date()] = gunler.get(s[1].date(), 0) + 1
        sonuc.gunler = gunler
        sonuc.ilk_gun, sonuc.son_gun = min(gunler), max(gunler)
        # listede olmayan makineleri ayarlara ekle
        ayar = vt.ayar_oku(con)
        bilinen = set(ayar["makineler"])
        yeni_m = sorted({s[0] for s in gecerli} - bilinen)
        if yeni_m:
            ayar["makineler"] = list(ayar["makineler"]) + yeni_m
            vt.ayar_yaz(con, "makineler", ayar["makineler"])
            sonuc.yeni_makineler = yeni_m
    vt.aktarim_kaydet(con, sonuc.dosya, sonuc.toplam, sonuc.yeni, sonuc.guncellenen, sonuc.ayni, len(sonuc.atlanan),
                      sonuc.ilk_gun.isoformat() if sonuc.ilk_gun else None,
                      sonuc.son_gun.isoformat() if sonuc.son_gun else None)
    return sonuc
