"""Performans sayfası: web tabanlı (ECharts) üç boyutlu grafikler.

Makine sütunları hep %100'dür (çalışma + duruş); sıfırın altında mola hakkı gösterilir
(mola yapılan / molada çalışılan). Sütuna tıklayınca altta o makinenin duruşları ya da
vardiya bazlı mola dağılımı açılır."""
from __future__ import annotations

import json
from typing import Optional

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QUrl, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QVBoxLayout, QWidget

from . import tema
from .cizim import tablo_resmi
from .hesap import durus_dokumu

try:                                    # web bileşeni yoksa program yine açılsın
    from PySide6.QtWebEngineWidgets import QWebEngineView
    WEB_VAR, WEB_HATA = True, ""
except Exception as ex:                 # noqa: BLE001
    QWebEngineView = None
    WEB_VAR, WEB_HATA = False, str(ex)


def performans_verisi(ana) -> dict:
    """Sayfanın çizeceği veriyi (JSON'a çevrilebilir sözlük) hazırlar."""
    sonuc, ayar = ana.sonuc, ana.hesap_ayar()
    mola_pay = 100.0 * ayar.mola_saat / ayar.net_saat
    veri = {"genel": None, "aciklama": "", "donem": "", "vardiyalar": [], "makineler": [],
            "molaDk": round(ayar.mola_saat * 60), "molaPay": mola_pay, "tablo": "", "tabloMakineler": []}
    for v in (1, 2, 3):
        veri["vardiyalar"].append({"v": v, "calisma": None, "makine": None, "gun": 0, "sef": (ana.seflar or {}).get(v, "")})
    if not sonuc:
        return veri
    gunler = ana.donem_gunleri()
    veri["genel"] = sonuc.genel[0]
    kural = {"gunluk": "günlük kural", "donem": "dönem kuralı"}.get(ayar.kural, ayar.kural)
    veri["aciklama"] = f"{sonuc.hesap_gunu()} gün · eşik %{round(ayar.esik * 100)} · {kural}"
    if gunler:
        veri["donem"] = f"{min(gunler):%d.%m.%Y} – {max(gunler):%d.%m.%Y}"
    for i, v in enumerate((1, 2, 3)):
        o = sonuc.vardiyalar.get(v)
        if o:
            veri["vardiyalar"][i].update(calisma=o.calisma, makine=o.makine_sayisi, gun=o.gun_sayisi)
    # tablo: Çalışma sayfasındaki sabit tablonun aynısı (aynı çizim kodu), resim olarak
    tum = list(ana.ayar.get("makineler", [])) + sorted(m for m in sonuc.hucreler if m not in ana.ayar.get("makineler", []))
    ba = QByteArray()
    tampon = QBuffer(ba)
    tampon.open(QIODevice.WriteOnly)
    tablo_resmi(sonuc, tum, 0, 660, satir=40, yazi_carpani=1.22).save(tampon, "PNG")
    veri["tablo"] = "data:image/png;base64," + bytes(ba.toBase64()).decode("ascii")
    veri["tabloMakineler"] = tum
    dokum = durus_dokumu(getattr(ana, "kayit", []) or [], gunler)
    sirali = [m for m in ana.ayar.get("makineler", []) if m in sonuc.makine_ort]
    sirali += sorted(m for m in sonuc.makine_ort if m not in sirali)
    for m in sirali:
        c, _d, mo = sonuc.makine_ort[m]
        if c is None:
            continue
        hucre = sonuc.hucreler.get(m, {})
        veri["makineler"].append({
            "ad": m, "calisma": max(0.0, min(1.0, c)), "mola": max(0.0, min(1.0, mo or 0.0)),
            "v": [hucre[v][0] if v in hucre else None for v in (1, 2, 3)],
            "molaV": [hucre[v][2] if v in hucre else None for v in (1, 2, 3)],
            "durus": {t: round(s, 4) for t, s in dokum.get(m, {}).items()},
        })
    return veri


class PerformansSayfasi(QWidget):
    def __init__(self, ana):
        super().__init__()
        self.ana = ana
        self._hazir = False
        self._bekleyen: Optional[str] = None
        kok = QVBoxLayout(self)
        kok.setContentsMargins(26, 22, 26, 22)
        kok.setSpacing(0)
        if not WEB_VAR:
            self.web = None
            uyari = QLabel("Grafik bileşeni yüklenemedi; bu sayfa gösterilemiyor.\n'Çalışma' sayfası aynı bilgileri içerir.\n\n" + WEB_HATA)
            uyari.setObjectName("AltBaslik")
            uyari.setAlignment(Qt.AlignCenter)
            uyari.setWordWrap(True)
            kok.addWidget(uyari, 1)
            return
        self.web = QWebEngineView()
        self.web.setContextMenuPolicy(Qt.CustomContextMenu)
        self.web.customContextMenuRequested.connect(self._menu)
        self.web.page().setBackgroundColor(Qt.transparent)
        self.web.loadFinished.connect(self._yuklendi)
        self.web.load(QUrl.fromLocalFile(tema.kaynak_yolu("assets", "web", "performans.html")))
        kok.addWidget(self.web, 1)

    def _yuklendi(self, tamam: bool):
        self._hazir = bool(tamam)
        if self._hazir and self._bekleyen is not None:
            self._gonder(self._bekleyen)
            self._bekleyen = None

    def _gonder(self, js_veri: str):
        self.web.page().runJavaScript(f"window.guncelle({js_veri});")

    def yenile(self):
        if self.web is None:
            return
        js_veri = json.dumps(performans_verisi(self.ana), ensure_ascii=False)
        if self._hazir:
            self._gonder(js_veri)
        else:
            self._bekleyen = js_veri

    def _menu(self, nokta):
        m = QMenu(self)
        a = QAction("Görünen kısmı resim olarak kopyala", m)
        a.triggered.connect(lambda: (QApplication.clipboard().setPixmap(self.web.grab()), self.ana.mesaj("Resim panoya kopyalandı.")))
        m.addAction(a)
        m.exec(self.web.mapToGlobal(nokta))
