"""Web grafikleri (yalnızca web'li exe'de): ECharts ile canlı ekran grafikleri ve rapor/PDF için resim.

Web motoru yoksa (web'siz exe) WEB_VAR False olur ve program kendi çizimini kullanır.
Ekran: sayfa_ortak.CizimWidget çizim kodunu "kayıt" kipinde çalıştırır, hangi grafiğin hangi veriyle çizileceğini
öğrenir ve bunu web_secenek ile ECharts seçeneğine çevirip WebGorunum'de gösterir.
Rapor/PDF: cizim.sayfa_ciz içinde grafikler Ressam ile resme çevrilip sayfaya basılır.
"""
from __future__ import annotations

import base64
import json
import os
from typing import Optional

from PySide6.QtCore import QByteArray, QEventLoop, QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QImage

try:
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
    from PySide6.QtWebEngineWidgets import QWebEngineView
    WEB_VAR = os.environ.get("VARDIYA_WEB_YOK") != "1"
except Exception:  # noqa: BLE001
    QWebEngineView = None  # type: ignore
    QWebEnginePage = object  # type: ignore
    WEB_VAR = False


def _adres() -> QUrl:
    from . import tema
    return QUrl.fromLocalFile(tema.kaynak_yolu("assets", "web", "grafik.html"))


if WEB_VAR:
    class _Sayfa(QWebEnginePage):
        tik = Signal(object, object)
        hazir = Signal()

        def javaScriptConsoleMessage(self, _seviye, mesaj, _satir, _kaynak):  # noqa: N802
            if mesaj.startswith("TIK|"):
                try:
                    d = json.loads(mesaj[4:])
                    self.tik.emit(d.get("anahtar"), d.get("kisim"))
                except Exception:  # noqa: BLE001
                    pass
            elif mesaj.startswith("HAZIR|"):
                self.hazir.emit()

    class WebGorunum(QWebEngineView):
        """Tek bir ECharts grafiği. goster(seçenek) son seçeneği sayfa hazır olunca uygular."""
        tiklandi = Signal(object, object)

        def __init__(self, ust=None):
            super().__init__(ust)
            self._sayfa = _Sayfa(self)
            self.setPage(self._sayfa)
            self._sayfa.setBackgroundColor(QColor("white"))
            self._hazir, self._bekleyen, self._son = False, None, None
            self._sayfa.hazir.connect(self._hazir_oldu)
            self._sayfa.tik.connect(self.tiklandi)
            self.setContextMenuPolicy(self.contextMenuPolicy().NoContextMenu)
            self.load(_adres())

        def _hazir_oldu(self):
            self._hazir = True
            if self._bekleyen is not None:
                s, self._bekleyen = self._bekleyen, None
                self._uygula(s)

        def goster(self, secenek: dict):
            metin = json.dumps(secenek, ensure_ascii=False, default=float)
            if metin == self._son:
                return
            self._son = metin
            if self._hazir:
                self._uygula(metin)
            else:
                self._bekleyen = metin

        def _uygula(self, metin: str):
            self._sayfa.runJavaScript(f"window.goster({metin});")

    class Ressam(QObject):
        """Görünmeyen bir sayfada grafikleri PNG'ye çevirir (rapor, PDF, yazdırma, resim kopyalama)."""
        _tek: Optional["Ressam"] = None

        def __init__(self):
            super().__init__()
            self._sayfa = _Sayfa(self)
            self._hazir = False
            self._sayfa.hazir.connect(lambda: setattr(self, "_hazir", True))
            self._sayfa.load(_adres())
            self._onbellek: dict = {}

        @classmethod
        def tek(cls) -> "Ressam":
            if cls._tek is None:
                cls._tek = Ressam()
            return cls._tek

        def _bekle(self, kosul, sn: float) -> bool:
            if kosul():
                return True
            dongu = QEventLoop()
            zaman = QTimer()
            zaman.setSingleShot(True)
            zaman.timeout.connect(dongu.quit)
            kontrol = QTimer()
            kontrol.timeout.connect(lambda: kosul() and dongu.quit())
            kontrol.start(20)
            zaman.start(int(sn * 1000))
            dongu.exec()
            kontrol.stop()
            return kosul()

        def resim(self, secenek: dict, w: int, h: int, oran: float) -> Optional[QImage]:
            metin = json.dumps(secenek, ensure_ascii=False, default=float)
            anahtar = (metin, w, h, round(oran, 2))
            if anahtar in self._onbellek:
                return self._onbellek[anahtar]
            if not self._bekle(lambda: self._hazir, 20):
                return None
            sonuc = {}
            self._sayfa.runJavaScript(f"window.resim({metin}, {int(w)}, {int(h)}, {oran:.3f});", 0,
                                      lambda v: sonuc.setdefault("v", v))
            if not self._bekle(lambda: "v" in sonuc, 20) or not isinstance(sonuc.get("v"), str):
                return None
            veri = sonuc["v"].split(",", 1)[-1]
            img = QImage.fromData(QByteArray(base64.b64decode(veri)), "PNG")
            if img.isNull():
                return None
            if len(self._onbellek) > 60:
                self._onbellek.clear()
            self._onbellek[anahtar] = img
            return img
else:
    WebGorunum = None  # type: ignore
    Ressam = None  # type: ignore


def rapor_resmi_ciz(ad: str, parametre: dict, w: float, h: float) -> Optional[QImage]:
    """cizim'in rapor kipinde çağırdığı işlev: grafiği web ile resme çevirir; desteklenmiyorsa None (kendi çizim)."""
    if not WEB_VAR:
        return None
    from . import web_secenek
    from .cizim import olcek
    from PySide6.QtCore import QRectF
    yapici = web_secenek.YAPICILAR.get(ad)
    if yapici is None:
        return None
    s = max(1.0, olcek(QRectF(0, 0, w, h)))
    cw, ch = max(200, int(w / s)), max(120, int(h / s))
    try:
        secenek = yapici(dict(parametre, _rapor=True))
    except Exception:  # noqa: BLE001
        return None
    if secenek is None:
        return None
    return Ressam.tek().resim(secenek, cw, ch, min(4.0, w / cw))


def kur() -> None:
    """Uygulama nesnesi kurulduktan sonra çağrılır: web varsa rapor ve PDF grafikleri web ile çizilir."""
    if WEB_VAR:
        from . import cizim
        cizim._WEB_CIZICI = rapor_resmi_ciz
