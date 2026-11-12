"""KOT kayıtları: grup liderlerinin OEE maillerinin (Copilot'un forma döktüğü) çözümlenmesi ve idari rapor metni.

Çözümleme satır sonlarına bağlı değildir: metin tek satıra yapışmış olsa da etiketlere göre ayrılır."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, Iterable, List, Optional

KATEGORILER = ("SETUP", "ARIZA", "PLANLAMA", "KALIP KONTROL", "REVIZYON", "MALZEME-TAKIM", "ELEMAN", "KALITE", "DIGER")
KATEGORI_AD = {"SETUP": "Setup / bağlama", "ARIZA": "Arıza", "PLANLAMA": "Planlama / iş bitimi", "KALIP KONTROL": "Kalıp kontrol",
               "REVIZYON": "Revizyon / tamir", "MALZEME-TAKIM": "Malzeme / takım", "ELEMAN": "Eleman", "KALITE": "Kalite",
               "DIGER": "Diğer"}
ONERI = {
    "SETUP": "Setup ve bağlama süreleri yüksek: bağlama aparatları ve sıfırlama düzenekleri önceden hazırlanmalı, tekrar eden bağlamalar için standart aparat kullanılmalı.",
    "ARIZA": "Arıza duruşları için önleyici bakım kontrolleri planlanmalı; tekrarlayan arızalarda kök neden bakım ekibiyle incelenmeli.",
    "PLANLAMA": "İş bitimi sonrası tezgâhların beklememesi için sıradaki iş emri ve programı vardiya tesliminden önce hazır olmalı.",
    "KALIP KONTROL": "Kalıp kontrol ve onay beklemeleri kısaltılmalı; kontrol sonucu aynı vardiya içinde tezgâha iletilmeli.",
    "REVIZYON": "Revizyon ve tamir işleri tezgâh yükünü artırıyor: revizyon işleri ayrı planlanmalı, parça uyumsuzlukları tasarım ve montajla birlikte giderilmeli.",
    "MALZEME-TAKIM": "Malzeme ve kesici takım beklemeleri için stok ve hazırlık takibi yapılmalı.",
    "ELEMAN": "Eleman eksikliğinden kaynaklı duruşlar için vardiya görevlendirmesi gözden geçirilmeli.",
    "KALITE": "Kalite kaynaklı duruşlarda uygunsuzluğun nedeni kayıt altına alınıp tekrarı önlenmeli.",
    "DIGER": "Sınıflandırılamayan açıklamalar grup liderleriyle netleştirilmeli.",
}
_TR = str.maketrans("ÇĞİÖŞÜçğıöşüâîû", "CGIOSUcgiosuaiu")


def _duz(s: str) -> str:
    return s.translate(_TR).upper()


@dataclass
class KotTezgah:
    tezgah: str
    kod: str = ""
    olay_saati: str = ""
    kategori: str = "DIGER"
    neden: str = ""
    aciklama: str = ""
    aksiyon: str = ""


@dataclass
class Kot:
    no: str
    tarih: date
    saat: str = ""
    vardiya: int = 0
    konu: str = ""
    lider: str = ""
    tezgahlar: List[KotTezgah] = field(default_factory=list)
    sonuc: str = ""
    durum: str = "ACIK"


def vardiya_bul(saat: str) -> int:
    m = re.match(r"\s*(\d{1,2})[:.](\d{2})", saat or "")
    if not m:
        return 0
    h = int(m.group(1))
    return 1 if h < 8 else (2 if h < 16 else 3)


def _temiz(s: str) -> str:
    s = re.sub(r"【[^】]*】", "", s or "")          # Copilot kaynak işaretleri
    s = s.replace("**", "").strip(" \t\r\n•-–|")
    return "" if s in ("", "-") else re.sub(r"\s+", " ", s)


def _kategori(s: str) -> str:
    d = re.sub(r"[^A-Z]", "", _duz(s))
    for k in KATEGORILER:
        if re.sub(r"[^A-Z]", "", k) == d:
            return k
    for k in KATEGORILER:
        if re.sub(r"[^A-Z]", "", k) in d:
            return k
    return "DIGER"


_UST = ("KOT NO", "TARIH", "SAAT", "VARDIYA", "KONU", "GRUP LIDERI")
_ALAN = ("KOD", "OLAY SAATI", "KATEGORI", "NEDEN", "ACIKLAMA", "AKSIYON")


def _etiket_bol(metin: str, etiketler) -> Dict[str, str]:
    """'ETIKET: değer ETIKET2: değer' biçimindeki metni, etiket sırasına bağlı kalmadan ayırır."""
    duz = _duz(metin)
    yerler = []
    for e in etiketler:
        for m in re.finditer(r"(?<![A-Z])" + re.escape(e).replace(r"\ ", r"\s+") + r"\s*:", duz):
            yerler.append((m.start(), m.end(), e))
    yerler.sort()
    sonuc: Dict[str, str] = {}
    for i, (bas, bit, e) in enumerate(yerler):
        son = yerler[i + 1][0] if i + 1 < len(yerler) else len(metin)
        sonuc.setdefault(e, _temiz(metin[bit:son]))
    return sonuc


def kot_coz(metin: str) -> List[Kot]:
    """Yapıştırılan metindeki bütün KOT bloklarını çözer. Tarihi okunamayan blok atlanır."""
    kotlar: List[Kot] = []
    for blok in re.split(r"=+\s*KOT\s*=+", metin or "")[1:]:
        blok = re.split(r"=+\s*SON\s*=+", blok)[0]
        duz = _duz(blok)
        m_t = re.search(r"-+\s*TEZGAHLAR\s*-+", duz)
        m_s = re.search(r"-+\s*SONUC\s*-+", duz)
        ust = blok[:m_t.start()] if m_t else blok
        orta = blok[m_t.end():(m_s.start() if m_s else len(blok))] if m_t else ""
        alt = blok[m_s.end():] if m_s else ""
        u = _etiket_bol(ust, _UST)
        m = re.search(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", u.get("TARIH", ""))
        if not m:
            continue
        try:
            gun = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            continue
        saat = (re.search(r"\d{1,2}[:.]\d{2}", u.get("SAAT", "")) or re.search(r"$", "")).group(0).replace(".", ":")
        k = Kot(no=u.get("KOT NO") or f"{gun:%Y-%m%d}-{saat.replace(':', '') or '0000'}", tarih=gun, saat=saat,
                vardiya=vardiya_bul(saat), konu=u.get("KONU", ""), lider=u.get("GRUP LIDERI", ""))
        # tezgâh satırları: "TEZGAH:" (ya da yanlışlıkla "TEZGAHLAR:") ile başlar
        orta_duz = _duz(orta)
        baslar = [mm for mm in re.finditer(r"TEZGAH(?:LAR)?\s*:", orta_duz)]
        for i, mm in enumerate(baslar):
            parca = orta[mm.end():(baslar[i + 1].start() if i + 1 < len(baslar) else len(orta))]
            ilk = parca.split("|")[0]
            mk = re.search(r"[A-Za-zİıiI]{1,3}\s?\d{2,3}", ilk)
            if not mk:
                continue
            a = _etiket_bol(parca, _ALAN)
            k.tezgahlar.append(KotTezgah(
                tezgah=_duz(mk.group(0)).replace(" ", ""), kod=a.get("KOD", ""), olay_saati=a.get("OLAY SAATI", ""),
                kategori=_kategori(a.get("KATEGORI", "")), neden=a.get("NEDEN", ""), aciklama=a.get("ACIKLAMA", ""),
                aksiyon=a.get("AKSIYON", "")))
        md = re.search(r"DURUM\s*:\s*([A-Z]+)", _duz(alt))
        k.sonuc = _temiz(alt[:re.search(r"DURUM\s*:", _duz(alt)).start()] if md else alt)
        if md:
            d = md.group(1)
            k.durum = "TAMAMLANDI" if d.startswith("TAMAM") else ("DEVAM" if d.startswith("DEVAM") else "ACIK")
        kotlar.append(k)
    return kotlar


# --------------------------------------------------------------------------- idari rapor içeriği
def durum_bul(oee: Optional[float], limit: float = 85.0) -> str:
    if oee is None:
        return ""
    if oee < 50:
        return "Kritik düşük"
    if oee < 65:
        return "Düşük"
    if oee < limit:
        return "Orta"
    return "Hedefte"


def idari_icerik(kotlar: Iterable[Kot], cormind: Dict[str, dict], calisma: Dict[str, Optional[float]], limit: float = 85.0) -> dict:
    """Rapor için özet, kök nedenler, tablolar ve öneriler. Rakamlar programın hesabından gelir; metin KOT kayıtlarından.

    cormind: hesap.cormind_hesabi çıktısı;  calisma: makine -> bizim çalışma oranımız (0-1) ya da None."""
    kotlar = sorted(kotlar, key=lambda k: (k.tarih, k.saat))
    satirlar = [(k, t) for k in kotlar for t in k.tezgahlar]
    say: Dict[str, int] = {}
    for _k, t in satirlar:
        say[t.kategori] = say.get(t.kategori, 0) + 1
    toplam = sum(say.values())
    sirali = sorted(say, key=lambda c: (-say[c], KATEGORILER.index(c)))
    pay = {c: (100.0 * say[c] / toplam if toplam else 0.0) for c in sirali}
    # özet
    if toplam:
        parca = ", ".join(f"%{pay[c]:.0f} {KATEGORI_AD[c].lower()}" for c in sirali[:3])
        ozet = (f"Dönemde grup liderlerinden {len(kotlar)} bildirim geldi; {len({t.tezgah for _k, t in satirlar})} tezgâh için "
                f"{toplam} açıklama yapıldı. Bildirilen OEE kayıplarının dağılımı: {parca}.")
    else:
        ozet = "Bu dönem için grup liderlerinden gelen KOT kaydı yok. Aşağıdaki değerler yalnızca Cormind verisinden hesaplanmıştır."
    # kök nedenler: kategori -> [(tezgah, tarih, vardiya, açıklama)]
    kok = []
    for c in sirali:
        maddeler = [f"{t.tezgah} ({k.tarih:%d.%m} {k.vardiya}.v): {t.aciklama or t.neden}" for k, t in satirlar if t.kategori == c]
        kok.append({"kategori": c, "ad": KATEGORI_AD[c], "pay": pay[c], "adet": say[c], "maddeler": maddeler})
    # tezgâh bazlı özet
    tezgah: Dict[str, dict] = {}
    for k, t in satirlar:
        x = tezgah.setdefault(t.tezgah, {"vardiyalar": set(), "kat": {}, "aciklama": []})
        x["vardiyalar"].add((k.tarih, k.vardiya))
        x["kat"][t.kategori] = x["kat"].get(t.kategori, 0) + 1
        metin = t.aciklama or t.neden
        if metin and metin not in x["aciklama"]:
            x["aciklama"].append(metin)
    tezgah_tablo = []
    for m, x in sorted(tezgah.items(), key=lambda kv: (-len(kv[1]["vardiyalar"]), kv[0])):
        en = sorted(x["kat"], key=lambda c: (-x["kat"][c], KATEGORILER.index(c)))
        tezgah_tablo.append({"tezgah": m, "kayit": len(x["vardiyalar"]), "kategori": " / ".join(KATEGORI_AD[c] for c in en[:2]),
                             "aciklama": " ".join(x["aciklama"])})
    # performans tablosu: bildirim gelen ya da hedefin altında kalan tezgâhlar, OEE'ye göre düşükten yükseğe
    perf = []
    for m, v in cormind.items():
        notlu = m in tezgah
        if not notlu and v["oee"] >= limit:
            continue
        if not notlu and not v["durus"]:
            continue
        if notlu:
            en = sorted(tezgah[m]["kat"], key=lambda c: (-tezgah[m]["kat"][c], KATEGORILER.index(c)))
            kayip = KATEGORI_AD[en[0]]
        else:
            kayip = max(v["durus"], key=lambda t: v["durus"][t]) if v["durus"] else ""
        perf.append({"tezgah": m, "oee": v["oee"], "calisma": calisma.get(m), "kayip": kayip, "durum": durum_bul(v["oee"], limit),
                     "notlu": notlu})
    perf.sort(key=lambda x: (x["oee"], x["tezgah"]))
    oneriler = []
    for c in sirali[:4]:
        tz = sorted({t.tezgah for _k, t in satirlar if t.kategori == c})
        oneriler.append(f"{KATEGORI_AD[c]} ({', '.join(tz)}): {ONERI[c]}")
    for k, t in satirlar:
        if t.aksiyon:
            oneriler.append(f"{t.tezgah}: {t.aksiyon}")
    oee_deg = [v["oee"] for v in cormind.values() if v["durus"]]
    return {"ozet": ozet, "kok": kok, "tezgah_tablo": tezgah_tablo, "perf": perf, "oneriler": oneriler,
            "oee_ort": (sum(oee_deg) / len(oee_deg) if oee_deg else None), "kot_sayisi": len(kotlar), "limit": limit}


def metne_cevir(ic: dict) -> str:
    """Düzenlenebilir düz metin: özet, kök nedenler ve öneriler."""
    s = ["ÖZET", ic["ozet"], ""]
    if ic["kok"]:
        s.append("ÖNE ÇIKAN KÖK NEDENLER")
        for i, k in enumerate(ic["kok"], 1):
            s.append(f"{i}. {k['ad']} (%{k['pay']:.0f}, {k['adet']} açıklama)")
            s += [f"   - {m}" for m in k["maddeler"]]
        s.append("")
    if ic["oneriler"]:
        s.append("İYİLEŞTİRME VE AKSİYON ÖNERİLERİ")
        s += [f"- {o}" for o in ic["oneriler"]]
    return "\n".join(s).strip()
