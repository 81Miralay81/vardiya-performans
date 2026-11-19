"""Exe ve web sürümünün ortak hizmetleri: dönem hesabı, Performans verisi, rapor verisi, Outlook'tan KOT alma.

Arayüzden bağımsızdır (Qt penceresi kullanmaz); exe sayfaları da web sunucusu da aynı işlevleri çağırır, böylece iki sürümde
rakamlar ve kurallar birebir aynı olur.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from . import tema, veritabani as vt
from .hesap import VARDIYALAR, HesapAyar, cormind_hesabi, durus_dokumu, hesapla, tr_kucuk, yatan_makineler
from .kot import idari_icerik, metne_cevir

DUZENLER = ("makine", "vardiya", "idari")
TURLER = ("Günlük", "Haftalık", "Aylık", "Özel aralık")


def hesap_ayari(a: dict) -> HesapAyar:
    return HesapAyar(esik=a["esik"], vardiya_dk=a["vardiya_dk"], yemek_dk=a["yemek_dk"], cay_dk=a["cay_dk"],
                     kural="gunluk", yontem=a.get("hesap_yontemi", "vardiya"),
                     haric=frozenset(tr_kucuk(x) for x in (a.get("operator_haric_durus") or [])))


def gunler(ilk: date, son: date) -> List[date]:
    return [ilk + timedelta(days=i) for i in range((son - ilk).days + 1)]


def donem_verisi(con, a: dict, ilk: date, son: date) -> dict:
    """Seçilen aralığın hesabı (exe'deki dönem çubuğuyla aynı kural): yalnızca bu günlerin kayıtları okunur."""
    kap = vt.gun_kapsami(con)
    tum = gunler(ilk, son)
    secili = [g for g in tum if kap.get(g)]
    if not secili:
        return dict(ilk=ilk, son=son, kapsam=kap, secili=[], gunler=tum, kayit=[], sonuc=None, seflar={})
    kayit = vt.kayitlari_getir(con, ilk, son)
    sonuc = hesapla(kayit, tum, hesap_ayari(a), set(kap))
    return dict(ilk=ilk, son=son, kapsam=kap, secili=secili, gunler=tum, kayit=kayit, sonuc=sonuc,
                seflar=vt.sef_getir(con, secili, a))


def degerler(sonuc, m: str) -> Optional[Tuple[float, float, bool]]:
    """(çalışma, mola, eşik altı mı) ya da None."""
    ort = sonuc.makine_ort.get(m) if sonuc else None
    if ort and ort[0] is not None:
        return max(0.0, min(1.0, ort[0])), max(0.0, min(1.0, ort[2] or 0.0)), False
    if sonuc and m in sonuc.esik_alti:
        e = sonuc.esik_alti[m]
        return max(0.0, min(1.0, e[0])), max(0.0, min(1.0, e[2])), True
    return None


def performans_verisi(con, a: dict, ilk: date, son: date) -> dict:
    """Performans sayfasının bütün verisi; grafikler web_secenek ile (exe'deki 3B grafiklerin aynısı)."""
    from . import web_secenek as ws
    d = donem_verisi(con, a, ilk, son)
    s, ayar = d["sonuc"], hesap_ayari(a)
    mola_pay = 100.0 * ayar.mola_saat / ayar.net_saat
    mola_dk = ayar.mola_saat * 60.0
    sonuc = {"ilk": ilk.isoformat(), "son": son.isoformat(), "veri_var": bool(s),
             "kapsam_ilk": min(d["kapsam"]).isoformat() if d["kapsam"] else None,
             "kapsam_son": max(d["kapsam"]).isoformat() if d["kapsam"] else None}
    if not s:
        return sonuc
    makineler = a.get("makineler", [])
    dokum = durus_dokumu(d["kayit"], d["gunler"], ayar.haric)
    cm = cormind_hesabi(d["kayit"], d["gunler"], makineler, ayar)
    yontem = dict(tema.YONTEMLER).get(ayar.yontem, "").lower()
    sonuc["kartlar"] = {
        "genel": {"deger": tema.yuzde(s.genel[0]) if s.genel[0] is not None else "-",
                  "alt": f"{s.hesap_gunu()} gün · eşik %{ayar.esik * 100:.0f} · {yontem}"},
        "vardiyalar": [{"ad": f"{v}. VARDİYA", "deger": tema.yuzde(s.vardiyalar[v].calisma) if s.vardiyalar[v].calisma is not None else "-",
                        "alt": (f"{tema.sayi(s.vardiyalar[v].makine_sayisi, 1)} makine · " if s.vardiyalar[v].makine_sayisi is not None else "")
                        + f"{s.vardiyalar[v].gun_sayisi} gün", "sef": d["seflar"].get(v, "")} for v in VARDIYALAR]}
    sonuc["grafik"] = {
        "vardiya": ws.vardiya_grafigi(dict(sonuc=s, seflar=d["seflar"], secim=0, baslik="")),
        "genel": ws.genel_performans_grafigi(dict(sonuc=s, makineler=makineler, mola_pay=mola_pay, baslik=None)),
        "oee": ws.cormind_oee_grafigi(dict(cm=cm, baslik="OEE Grafiği (Cormind)", limit=85.0)),
        "zaman": ws.cormind_durus_grafigi(dict(cm=cm, baslik="Zaman Dağılım Grafiği (Cormind)", limit=15.0)),
    }
    sonuc["dokum"] = {m: sorted(((t, round(x, 4)) for t, x in v.items() if x > 0.004), key=lambda x: -x[1]) for m, v in dokum.items()}
    sonuc["mola"] = {m: [(f"{v}. VARDİYA", d["seflar"].get(v, ""), h[v][2]) for v in VARDIYALAR if v in h] for m, h in s.hucreler.items()}
    sonuc["mola_dk"] = mola_dk
    sonuc["degerler"] = {m: degerler(s, m) for m in set(s.makine_ort) | set(s.esik_alti)}
    sonuc["bozuk"] = s.bozuk_kayit
    return sonuc


# ------------------------------------------------------------------ raporlar
def oneri_baslik(duzen: str, tur: int, ilk: date, son: date) -> str:
    if duzen == "idari":
        if tur == 0:
            return f"{ilk.day}.{ilk.month}.{ilk.year} GÜNLÜK OEE VE DURUŞ ÖZET RAPORU"
        if tur == 1:
            return f"{ilk.isocalendar()[1]}. HAFTA OEE VE DURUŞ ÖZET RAPORU"
        if tur == 2:
            return f"{tema.tr_buyuk(tema.AYLAR[ilk.month - 1])} {ilk.year} OEE VE DURUŞ ÖZET RAPORU"
        return f"{ilk:%d.%m.%Y} - {son:%d.%m.%Y} OEE VE DURUŞ ÖZET RAPORU"
    son_ek = "PERFORMANS VE DURUŞ GRAFİKLERİ" if duzen == "makine" else ("VARDİYA BAZLI GRAFİKLERİ" if tur == 0 else "VARDİYA GRAFİKLERİ")
    if tur == 0:
        on = f"{ilk.day}.{ilk.month}.{ilk.year}"
    elif tur == 1:
        on = f"{ilk.isocalendar()[1]}. HAFTA"
    elif tur == 2:
        on = f"{tema.tr_buyuk(tema.AYLAR[ilk.month - 1])} {ilk.year}"
    else:
        on = f"{ilk:%d.%m.%Y} - {son:%d.%m.%Y}"
    return f"{on} CNC İŞLEME {son_ek}"


def metin_anahtar(ilk: date, son: date) -> str:
    return f"idari|{ilk.isoformat()}|{son.isoformat()}"


def rapor_verisi(con, a: dict, duzen: str, ilk: date, son: date, tur: int = 3, baslik: Optional[str] = None,
                 gorsel=None) -> Tuple[Optional[dict], dict]:
    """Rapor çizimine giden sözlük ve arayüz için bilgi (gün listesi, şefler, KOT durumu). Veri yoksa (None, bilgi)."""
    kap = vt.gun_kapsami(con)
    tum = gunler(ilk, son)
    veri_gunleri = [g for g in tum if kap.get(g)]
    bilgi = {"gunler": veri_gunleri, "seflar": {}, "kot_sayisi": 0, "tezgah_sayisi": 0, "metin_elle": False, "yatan": []}
    if not veri_gunleri:
        return None, bilgi
    ayar = hesap_ayari(a)
    kayit = vt.kayitlari_getir(con, ilk, son)
    sonuc = hesapla(kayit, tum, ayar, set(kap))
    seflar = vt.sef_getir(con, veri_gunleri, a)
    bilgi["seflar"] = seflar
    donem = f"{ilk:%d.%m.%Y}" if ilk == son else f"{ilk:%d.%m.%Y} – {son:%d.%m.%Y}"
    makineler = a["makineler"]
    cm = cormind_hesabi(kayit, veri_gunleri, makineler, ayar)
    ek = {}
    if duzen == "idari":
        import dataclasses
        yatan = yatan_makineler(cm, sonuc)            # idari rapor yalnızca çalışan makinelerle (yatanlar hiçbir bölümde yok)
        cm = {m: v for m, v in cm.items() if m not in yatan}
        kotlar = vt.kot_getir(con, ilk, son)
        icerik = idari_icerik(kotlar, cm, {m: v[0] for m, v in sonuc.makine_ort.items() if m not in yatan})
        ozel = vt.metin_oku(con, metin_anahtar(ilk, son))
        sonuc = dataclasses.replace(                  # grafik ve tablolarda da yatan makine görünmesin
            sonuc, makine_ort={m: v for m, v in sonuc.makine_ort.items() if m not in yatan},
            esik_alti={m: v for m, v in sonuc.esik_alti.items() if m not in yatan},
            hucreler={m: v for m, v in sonuc.hucreler.items() if m not in yatan})
        makineler = [m for m in makineler if m not in yatan]
        ek = dict(idari=icerik, idari_metin=ozel if ozel is not None else metne_cevir(icerik),
                  mola_pay=100.0 * ayar.mola_saat / ayar.net_saat, yatan=sorted(yatan))
        bilgi.update(kot_sayisi=len(kotlar), tezgah_sayisi=sum(len(k.tezgahlar) for k in kotlar), metin_elle=ozel is not None,
                     yatan=sorted(yatan))
    r = dict(baslik=baslik or oneri_baslik(duzen, tur, ilk, son), donem=donem, duzen=duzen, sonuc=sonuc, makineler=makineler,
             seflar=seflar, gorsel=gorsel if duzen == "makine" else None, bos_goster=a.get("idle_makineleri_goster", False),
             esik=a["esik"], net_saat=ayar.net_saat, yer_tutucu=True, alt_sag=f"Oluşturma: {datetime.now():%d.%m.%Y %H:%M}",
             ilk=ilk, son=son, cormind=cm, **ek)
    return r, bilgi


# ------------------------------------------------------------------ Outlook'tan KOT
def outlook_kot_al(con, ilk: date, son: date) -> dict:
    """Seçili dönemin OEE maillerini Outlook'tan okuyup KOT kaydına çevirir (yapay zekâ anahtarı varsa onunla, yoksa ve
    yapay zekânın vermediği maillerde program algoritmasıyla). Hata olursa RuntimeError."""
    from . import outlook, yapay
    from .kot import KOT_KURALLARI, kot_coz, maili_coz
    ya = yapay.ayar_oku()
    mailler = outlook.mailleri_getir(ilk, son, ya["gonderen"], ya["konu"])
    sonuc = {"mail": len(mailler), "yz": 0, "kot": 0, "yeni": 0, "guncel": 0, "bos": 0, "uyari": "",
             "gonderen": ya["gonderen"], "konu": ya["konu"]}
    if not mailler:
        return sonuc
    kotlar = {}
    if ya["anahtar"]:
        try:
            yanit = yapay.sor(ya["anahtar"], yapay.kot_istemi(mailler, KOT_KURALLARI), ya["model"])
            for k in kot_coz(yanit):
                es = [m for m in mailler if m.zaman.date() == k.tarih and f"{m.zaman:%H:%M}" == k.saat]
                if es and k.tezgahlar:                 # yalnızca gerçek bir maille eşleşen kayıt alınır
                    k.no, k.lider, k.konu = f"{es[0].zaman:%Y-%m%d-%H%M}", es[0].imza_adi, es[0].konu.strip()
                    kotlar[k.no] = k
        except RuntimeError as ex:
            sonuc["uyari"] = f"Yapay zekâ kullanılamadı, program kendi algoritmasıyla ayırdı: {ex}"
    sonuc["yz"] = len(kotlar)
    for m in mailler:                                  # yapay zekânın vermediği mailler: program algoritması
        no = f"{m.zaman:%Y-%m%d-%H%M}"
        if no not in kotlar:
            k = maili_coz(m.zaman, m.konu, m.metin, m.imza_adi)
            if k:
                kotlar[no] = k
            else:
                sonuc["bos"] += 1
    sonuc["yeni"], sonuc["guncel"] = vt.kot_yaz(con, kotlar.values())
    sonuc["kot"] = len(kotlar)
    return sonuc


def outlook_ozet(r: dict) -> str:
    ozet = (f"{r['mail']} mail okundu. {r['yz']} tanesi yapay zekâ ile, {r['kot'] - r['yz']} tanesi program algoritmasıyla KOT'a "
            f"çevrildi ({r['yeni']} yeni, {r['guncel']} güncellendi).")
    if r["bos"]:
        ozet += f" {r['bos']} mailde makine kodu bulunamadığı için kayıt oluşmadı."
    return ozet
