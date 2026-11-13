"""Açılış penceresi: program hazırlanırken ne yapıldığını ve ilerlemeyi gösterir.

İki aşama vardır. İlki exe'nin kendini geçici klasöre açtığı aşamadır; o sırada Python henüz çalışmaz, pencereyi
exe'nin başlatıcısı gösterir (assets/acilis.png, altında açılan dosyaların adları akar). Python çalışmaya başlayınca
o pencere kapanır ve yerine bu pencere ilerleme çubuğuyla gelir.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QProgressBar, QVBoxLayout, QWidget

from . import tema


def baslatici_yazisi(metin: str) -> None:
    """Exe başlatıcısının penceresindeki yazıyı değiştirir (yalnızca derlenmiş exe'de vardır)."""
    try:
        import pyi_splash  # type: ignore
        pyi_splash.update_text(metin)
    except Exception:  # noqa: BLE001
        pass


def baslatici_kapat() -> None:
    try:
        import pyi_splash  # type: ignore
        pyi_splash.close()
    except Exception:  # noqa: BLE001
        pass


class AcilisPenceresi(QWidget):
    def __init__(self):
        super().__init__(None, Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setFixedSize(460, 230)                # saydam köşe yok: bazı bilgisayarlarda siyah görünüyordu
        self.setStyleSheet("AcilisPenceresi { background: white; }")
        self.setAutoFillBackground(True)
        kok = QVBoxLayout(self)
        kok.setContentsMargins(0, 0, 0, 0)
        kutu = QFrame()
        kutu.setStyleSheet("QFrame#Kutu { background: white; border: 1px solid #c9cedb; }")
        kutu.setObjectName("Kutu")
        kok.addWidget(kutu)
        d = QVBoxLayout(kutu)
        d.setContentsMargins(26, 20, 26, 20)
        d.setSpacing(8)
        logo = QLabel()
        pm = tema.logo()
        if not pm.isNull():
            logo.setPixmap(pm.scaledToHeight(46, Qt.SmoothTransformation))
        d.addWidget(logo, 0, Qt.AlignLeft)
        b = QLabel("Vardiya Performans açılıyor, lütfen bekleyin…")
        b.setStyleSheet(f"color: {tema.LACIVERT}; font-size: 15px; font-weight: 700;")
        d.addWidget(b)
        self.yazi = QLabel("Başlatılıyor")
        self.yazi.setStyleSheet("color: #6b7285; font-size: 12px;")
        d.addWidget(self.yazi)
        self.cubuk = QProgressBar()
        self.cubuk.setRange(0, 100)
        self.cubuk.setTextVisible(False)
        self.cubuk.setFixedHeight(10)
        self.cubuk.setStyleSheet("QProgressBar { background: #e6e9f2; border: 0; border-radius: 5px; }"
                                 f"QProgressBar::chunk {{ background: {tema.YESIL}; border-radius: 5px; }}")
        d.addWidget(self.cubuk)
        d.addStretch(1)
        ekran = QApplication.primaryScreen()
        if ekran is not None:
            g = ekran.availableGeometry()
            self.move(g.center().x() - self.width() // 2, g.center().y() - self.height() // 2)

    def adim(self, yuzde: int, metin: str) -> None:
        global _ETKIN
        _ETKIN = self
        self.cubuk.setValue(yuzde)
        self.yazi.setText(metin)
        QApplication.processEvents()


_ETKIN: "AcilisPenceresi | None" = None


def ilerle(yuzde: int, metin: str) -> None:
    """Ana pencere kurulurken açılış penceresindeki adımı ilerletir (açılış penceresi yoksa bir şey yapmaz)."""
    if _ETKIN is not None and _ETKIN.isVisible():
        _ETKIN.adim(yuzde, metin)


def bitir() -> None:
    global _ETKIN
    if _ETKIN is not None:
        _ETKIN.close()
    _ETKIN = None


class BeklemePenceresi(QWidget):
    """Uzun işlerde (1 aydan uzun dönem, çok kayıt) ne yapıldığını, ilerlemeyi ve tahmini kalan süreyi gösterir.
    Tahmin, bu bilgisayarda önceki hesapların ölçülen hızından (1000 kayıt başına saniye) çıkarılır."""

    def __init__(self, ust, baslik: str, aciklama: str):
        super().__init__(ust, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setFixedSize(470, 170)
        self.setStyleSheet("BeklemePenceresi { background: white; border: 1px solid #c9cedb; }")
        self.setAutoFillBackground(True)
        d = QVBoxLayout(self)
        d.setContentsMargins(24, 18, 24, 18)
        b = QLabel(baslik)
        b.setStyleSheet(f"color: {tema.LACIVERT}; font-size: 15px; font-weight: 700;")
        d.addWidget(b)
        a = QLabel(aciklama)
        a.setWordWrap(True)
        a.setStyleSheet("color: #6b7285; font-size: 12px;")
        d.addWidget(a)
        self.yazi = QLabel("")
        self.yazi.setStyleSheet(f"color: {tema.LACIVERT}; font-size: 12px; font-weight: 600;")
        d.addWidget(self.yazi)
        self.cubuk = QProgressBar()
        self.cubuk.setRange(0, 100)
        self.cubuk.setTextVisible(False)
        self.cubuk.setFixedHeight(10)
        self.cubuk.setStyleSheet("QProgressBar { background: #e6e9f2; border: 0; border-radius: 5px; }"
                                 f"QProgressBar::chunk {{ background: {tema.YESIL}; border-radius: 5px; }}")
        d.addWidget(self.cubuk)
        if ust is not None:
            g = ust.frameGeometry()
            self.move(g.center().x() - self.width() // 2, g.center().y() - self.height() // 2)
        self.show()
        QApplication.processEvents()

    def adim(self, yuzde: int, metin: str) -> None:
        self.cubuk.setValue(yuzde)
        self.yazi.setText(metin)
        self.repaint()
        QApplication.processEvents()


def hiz_oku() -> float:
    """Bu bilgisayarda 1000 kaydın hesap ve çizim süresi (sn); ilk kez çalışıyorsa varsayılan."""
    from PySide6.QtCore import QSettings
    try:
        return max(0.05, float(QSettings("Teknorot", "VardiyaPerformans").value("hiz/bin_kayit_sn", 0.6)))
    except (TypeError, ValueError):
        return 0.6


def hiz_yaz(kayit: int, sn: float) -> None:
    if kayit < 5000:
        return
    from PySide6.QtCore import QSettings
    yeni = sn / (kayit / 1000.0)
    eski = hiz_oku()
    QSettings("Teknorot", "VardiyaPerformans").setValue("hiz/bin_kayit_sn", round(0.6 * yeni + 0.4 * eski, 4))


def sure_yazisi(sn: float) -> str:
    sn = max(1, int(round(sn)))
    return f"{sn} sn" if sn < 60 else f"{sn // 60} dk {sn % 60:02d} sn"
