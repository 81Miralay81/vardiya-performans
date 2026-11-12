"""Yapay zekâ (Gemini) bağlantısı: mail metinlerini KOT formuna döktürür. Anahtar kullanıcının bilgisayarında saklanır."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import List

VARSAYILAN_MODEL = "gemini-3.8-flash"
ADRES = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def sor(anahtar: str, istem: str, model: str = VARSAYILAN_MODEL, zaman_asimi: int = 90) -> str:
    """Gemini'ye metin gönderir, yanıt metnini döndürür. Hata olursa Türkçe açıklamalı RuntimeError verir."""
    if not anahtar:
        raise RuntimeError("Yapay zekâ anahtarı girilmemiş (Ayarlar sayfası).")
    govde = json.dumps({"contents": [{"parts": [{"text": istem}]}], "generationConfig": {"temperature": 0}}).encode("utf8")
    istek = urllib.request.Request(ADRES.format(model=model or VARSAYILAN_MODEL), data=govde, method="POST",
                                   headers={"Content-Type": "application/json", "x-goog-api-key": anahtar})
    try:
        with urllib.request.urlopen(istek, timeout=zaman_asimi) as y:
            veri = json.loads(y.read().decode("utf8"))
    except urllib.error.HTTPError as ex:
        ayrinti = ""
        try:
            ayrinti = json.loads(ex.read().decode("utf8")).get("error", {}).get("message", "")
        except Exception:  # noqa: BLE001
            pass
        ne = {400: "İstek kabul edilmedi (anahtar ya da model adı hatalı olabilir).", 401: "Anahtar geçersiz.", 403: "Erişim reddedildi (anahtar yetkisi ya da şirket ağı engeli).",
              404: "Model bulunamadı; Ayarlar'daki model adını denetleyin.", 429: "Kullanım sınırı aşıldı; biraz sonra yeniden deneyin."}.get(ex.code, "Sunucu hatası.")
        raise RuntimeError(f"Yapay zekâ yanıt vermedi: {ne} (HTTP {ex.code}) {ayrinti}".strip()) from ex
    except Exception as ex:  # noqa: BLE001
        raise RuntimeError(f"Yapay zekâ servisine ulaşılamadı; şirket ağı engelliyor olabilir.\n({ex})") from ex
    try:
        return "".join(p.get("text", "") for p in veri["candidates"][0]["content"]["parts"])
    except Exception as ex:  # noqa: BLE001
        raise RuntimeError("Yapay zekâ boş ya da beklenmeyen bir yanıt verdi.") from ex


def kot_istemi(mailler: List, kurallar: str) -> str:
    """mailler: outlook.Mail listesi. Her mail numaralı ve tarih/saatiyle verilir; imza ve kişi adları gönderilmez."""
    s = ["Aşağıda numaralı e-postalar var. Her birini kurallara göre KOT formuna dönüştür.",
         "GRUP LIDERI alanına her zaman \"-\" yaz. TARIH, SAAT ve KONU alanlarını e-postanın başlığındaki değerlerden al.", "",
         kurallar, "", "E-POSTALAR"]
    for i, m in enumerate(mailler, 1):
        s += [f"--- E-POSTA {i} | TARIH: {m.zaman:%d.%m.%Y} | SAAT: {m.zaman:%H:%M} | KONU: {m.konu} ---", m.metin, ""]
    return "\n".join(s)


# --------------------------------------------------------------------------- yerel ayarlar (bu bilgisayarda, ortak veri tabanında değil)
def ayar_oku() -> dict:
    import base64
    from PySide6.QtCore import QSettings
    a = QSettings("Teknorot", "VardiyaPerformans")
    try:
        anahtar = base64.b64decode(a.value("yapay/anahtar", "") or "").decode("utf8")
    except Exception:  # noqa: BLE001
        anahtar = ""
    return {"anahtar": anahtar, "model": a.value("yapay/model", VARSAYILAN_MODEL) or VARSAYILAN_MODEL,
            "gonderen": a.value("kot/gonderen", "Kalip Uretim"), "konu": a.value("kot/konu", "OEE") or "OEE"}


def ayar_yaz(anahtar: str, model: str, gonderen: str, konu: str) -> None:
    import base64
    from PySide6.QtCore import QSettings
    a = QSettings("Teknorot", "VardiyaPerformans")
    a.setValue("yapay/anahtar", base64.b64encode((anahtar or "").strip().encode("utf8")).decode())
    a.setValue("yapay/model", (model or "").strip() or VARSAYILAN_MODEL)
    a.setValue("kot/gonderen", (gonderen or "").strip())
    a.setValue("kot/konu", (konu or "").strip() or "OEE")
