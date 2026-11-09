"""Renkler, yazı tipi ve biçimlendirme yardımcıları (Teknorot kurumsal renkleri)."""
from __future__ import annotations

import math
import os
import sys

from PySide6.QtGui import QColor, QFont, QPixmap

LACIVERT = "#150958"      # logodaki lacivert
YESIL = "#5E9B2A"         # logodaki yeşil
YESIL_ACIK = "#B2D234"
ZEMIN = "#F2F4F8"
KART = "#FFFFFF"
CIZGI = "#D9DEE8"
YAZI = "#1B1E2B"
YAZI_SOLUK = "#6B7285"
TURUNCU = "#F28C28"
KIRMIZI = "#C0392B"
MOR = "#7A5AA6"

# Excel'deki rapor tablosunun renkleri (yazıcıdan çıkan görünüm korunur)
XL_SEFTALI = "#F4B183"
XL_YESIL = "#92D050"
XL_TURUNCU = "#FFC000"
XL_GRI = "#D9D9D9"
XL_SARI = "#FFFF00"
XL_KIRMIZI = "#FF0000"

METRIKLER = ("Çalışma", "Duruş", "Mola")
METRIK_RENK = (LACIVERT, KIRMIZI, MOR)

FONT_AILESI = "Segoe UI" if sys.platform.startswith("win") else "DejaVu Sans"


def kaynak_yolu(*parcalar: str) -> str:
    """Geliştirmede proje klasörü, PyInstaller exe'sinde gömülü klasör."""
    taban = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(taban, *parcalar)


def logo() -> QPixmap:
    return QPixmap(kaynak_yolu("assets", "logo.png"))


def font(px: float, kalin: bool = False) -> QFont:
    f = QFont(FONT_AILESI)
    f.setPixelSize(max(6, int(round(px))))
    f.setBold(kalin)
    return f


def renk(h: str, alfa: int = 255) -> QColor:
    c = QColor(h)
    c.setAlpha(alfa)
    return c


# ----------------------------------------------------------------- biçim
def yuzde(x, basamak: int = 2) -> str:
    if x is None:
        return ""
    return f"{x * 100:.{basamak}f}".replace(".", ",") + "%"


def sayi(x, basamak: int = 1) -> str:
    if x is None:
        return ""
    return f"{x:.{basamak}f}".replace(".", ",")


def yuvarla(x) -> int:
    return int(math.floor(x + 0.5))


def tr_buyuk(s: str) -> str:
    return s.replace("i", "İ").replace("ı", "I").upper()


AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
GUNLER = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


def tarih(d) -> str:
    return d.strftime("%d.%m.%Y")


STIL = f"""
* {{ font-family: "{FONT_AILESI}"; font-size: 13px; color: {YAZI}; }}
QMainWindow, QWidget#Zemin {{ background: {ZEMIN}; }}
QFrame#Kart {{ background: {KART}; border: 1px solid {CIZGI}; border-radius: 10px; }}
QFrame#Yan {{ background: {KART}; border-right: 1px solid {CIZGI}; }}
QLabel#Baslik {{ font-size: 22px; font-weight: 700; color: {LACIVERT}; }}
QLabel#AltBaslik {{ font-size: 13px; color: {YAZI_SOLUK}; }}
QLabel#KartBaslik {{ font-size: 12px; color: {YAZI_SOLUK}; font-weight: 600; }}
QLabel#KartDeger {{ font-size: 26px; font-weight: 700; color: {LACIVERT}; }}
QLabel#Uyari {{ color: #8A5A00; background: #FFF4D6; border: 1px solid #F2D58A; border-radius: 6px; padding: 6px 10px; }}
QLabel#Basari {{ color: #20520A; background: #E8F4D8; border: 1px solid #B9DB8F; border-radius: 6px; padding: 6px 10px; }}
QPushButton {{ background: {KART}; border: 1px solid {CIZGI}; border-radius: 8px; padding: 8px 16px; font-weight: 600; }}
QPushButton:hover {{ border-color: {YESIL}; }}
QPushButton:pressed {{ background: #EAF3DD; }}
QPushButton#Ana {{ background: {YESIL}; color: white; border: 1px solid {YESIL}; }}
QPushButton#Ana:hover {{ background: #4E8620; }}
QPushButton#Lacivert {{ background: {LACIVERT}; color: white; border: 1px solid {LACIVERT}; }}
QPushButton#Lacivert:hover {{ background: #241680; }}
QPushButton#Tehlike {{ color: {KIRMIZI}; }}
QPushButton:disabled {{ color: #A5AABB; background: #F5F6FA; }}
QPushButton#Hizli {{ padding: 6px 12px; font-weight: 500; }}
QPushButton#Hizli:checked {{ background: {LACIVERT}; color: white; border-color: {LACIVERT}; }}
QPushButton#Menu {{ text-align: left; border: none; border-radius: 8px; padding: 12px 16px; font-size: 14px;
                     font-weight: 600; background: transparent; color: {YAZI}; }}
QPushButton#Menu:hover {{ background: #EEF1F7; }}
QPushButton#Menu:checked {{ background: {LACIVERT}; color: white; }}
QDateEdit, QDoubleSpinBox, QSpinBox, QComboBox, QLineEdit {{ background: white; border: 1px solid {CIZGI}; border-radius: 6px;
                     padding: 5px 8px; min-height: 22px; }}
QDateEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus, QLineEdit:focus {{ border-color: {YESIL}; }}
QTableWidget {{ background: white; border: 1px solid {CIZGI}; border-radius: 8px; gridline-color: #EBEEF4; }}
QHeaderView::section {{ background: #F5F7FB; border: none; border-bottom: 1px solid {CIZGI}; padding: 6px; font-weight: 600; }}
QListWidget {{ background: white; border: 1px solid {CIZGI}; border-radius: 8px; }}
QListWidget::item {{ padding: 5px 8px; }}
QListWidget::item:selected {{ background: #E3E7F5; color: {YAZI}; }}
QScrollArea {{ border: none; background: transparent; }}
QToolTip {{ background: {LACIVERT}; color: white; border: none; padding: 6px; }}
"""


KURALLAR = (("gunluk", "Günlük kural"), ("donem", "Dönem kuralı (Excel gibi)"))
KURAL_ACIKLAMA = {
    "gunluk": (
        "GÜNLÜK KURAL: %60 eşiği her gün ve her vardiya için ayrı uygulanır. Bir makine, o gün o vardiyada net sürenin "
        "en az %60'ını çalıştıysa o günün ortalamasına girer; çalışmadıysa o gün sayılmaz. Haftalık ya da aylık "
        "sonuç, günlük sonuçların ortalamasıdır ve makine sayısı günden güne değişir. Zayıf geçen günler makineyi "
        "ortalamadan çıkardığı için rakamlar daha yüksek çıkar."),
    "donem": (
        "DÖNEM KURALI (eski Excel gibi): Bir makinenin dönem boyunca toplam çalışma süresi, net süre ile kayıtlı gün "
        "sayısının çarpımına bölünür. Çalışmadığı günler 0 sayılır. Bu oran %60'ı geçen makine tüm dönem boyunca "
        "sayılır; makine sayısı dönem boyunca sabittir. Zayıf günler ortalamayı düşürür. Rakamlar eski Excel'inizle "
        "karşılaştırılabilir."),
}
