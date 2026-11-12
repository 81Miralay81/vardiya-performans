"""Outlook'tan grup lideri maillerini okur (yalnızca Windows, klasik masaüstü Outlook).

Mail gönderilmez, silinmez, değiştirilmez: yalnızca okunur."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import List

_TR = str.maketrans("ÇĞİÖŞÜçğıöşüâîû", "CGIOSUcgiosuaiu")
_KAPANIS = re.compile(r"^\s*(bilgilerinize|saygılarımla|saygilarimla|best regards|iyi çalışmalar|iyi calismalar)\b", re.I)


def _duz(s: str) -> str:
    return (s or "").translate(_TR).upper()


@dataclass
class Mail:
    zaman: datetime
    konu: str
    gonderen: str
    metin: str          # kapanış ve imzadan önceki kısım
    imza_adi: str = ""  # imzadaki kişi adı (bulunabildiyse)


def metni_ayir(govde: str):
    """Mail gövdesini (asıl metin, imzadaki ad) olarak ayırır; imza ve yasal uyarı atılır."""
    satirlar = [s.rstrip() for s in (govde or "").replace("\r", "").split("\n")]
    kes = len(satirlar)
    for i, s in enumerate(satirlar):
        if _KAPANIS.match(s):
            kes = i
            break
    ad = ""
    for s in satirlar[kes:]:
        t = s.strip().strip(",")
        if not t or _KAPANIS.match(t) or t.lower().startswith(("best regards", "saygı")):
            continue
        # ad satırı: 2-4 kelime, rakam ve @ yok
        if 2 <= len(t.split()) <= 4 and not re.search(r"[\d@:/]", t):
            ad = t
        break
    metin = "\n".join(s for s in satirlar[:kes]).strip()
    return re.sub(r"\n{3,}", "\n\n", metin), ad


def mailleri_getir(ilk: date, son: date, gonderen: str = "Kalip Uretim", konu: str = "OEE", azami: int = 200) -> List[Mail]:
    """[ilk, son] günlerinde gelen, göndereni ve konusu süzgece uyan mailler (eskiden yeniye).
    Bütün posta klasörlerine bakılır. Outlook yoksa ya da açılamıyorsa RuntimeError verir."""
    try:
        import win32com.client  # type: ignore
    except Exception as ex:  # noqa: BLE001
        raise RuntimeError("Outlook bağlantısı yalnızca Windows'ta, klasik masaüstü Outlook kuruluyken çalışır.") from ex
    try:
        ns = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
    except Exception as ex:  # noqa: BLE001
        raise RuntimeError(f"Outlook açılamadı. Klasik masaüstü Outlook kurulu ve açık olmalı.\n({ex})") from ex
    g_duz, k_duz = _duz(gonderen).strip(), _duz(konu).strip()
    bulunan, gorulen = [], set()

    def klasor_tara(klasor, derinlik=0):
        try:
            if getattr(klasor, "DefaultItemType", 0) != 0:      # 0 = posta
                return
            ogeler = klasor.Items
            ogeler.Sort("[ReceivedTime]", True)                 # yeniden eskiye
            o = ogeler.GetFirst()
            sayac = 0
            while o is not None and sayac < 5000:
                sayac += 1
                try:
                    z = o.ReceivedTime
                    gun = date(z.year, z.month, z.day)
                    if gun < ilk:
                        break
                    if gun <= son and getattr(o, "Class", 0) == 43:      # 43 = e-posta
                        if k_duz in _duz(o.Subject) and (not g_duz or g_duz in _duz(o.SenderName) or g_duz in _duz(getattr(o, "SentOnBehalfOfName", ""))):
                            kimlik = getattr(o, "EntryID", None) or (str(z), o.Subject)
                            if kimlik not in gorulen:
                                gorulen.add(kimlik)
                                metin, ad = metni_ayir(o.Body)
                                bulunan.append(Mail(datetime(z.year, z.month, z.day, z.hour, z.minute), o.Subject or "", o.SenderName or "", metin, ad))
                except Exception:  # noqa: BLE001  (okunamayan tek öğe atlanır)
                    pass
                o = ogeler.GetNext()
        except Exception:  # noqa: BLE001
            pass
        if derinlik < 6:
            try:
                for alt in klasor.Folders:
                    klasor_tara(alt, derinlik + 1)
            except Exception:  # noqa: BLE001
                pass

    try:
        for depo in ns.Folders:
            klasor_tara(depo)
    except Exception as ex:  # noqa: BLE001
        raise RuntimeError(f"Outlook klasörleri okunamadı.\n({ex})") from ex
    # aynı mail birden çok klasörde olabilir (ör. Gelen Kutusu ve arama klasörü): zaman + konu ile tekilleştir
    tek = {}
    for m in bulunan:
        tek.setdefault((m.zaman, m.konu.strip()), m)
    return sorted(tek.values(), key=lambda m: m.zaman)[:azami]
