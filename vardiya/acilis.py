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
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(460, 230)
        kok = QVBoxLayout(self)
        kok.setContentsMargins(8, 8, 8, 8)
        kutu = QFrame()
        kutu.setStyleSheet("QFrame#Kutu { background: white; border: 1px solid #d9deea; border-radius: 14px; }")
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
        self.cubuk.setValue(yuzde)
        self.yazi.setText(metin)
        QApplication.processEvents()
