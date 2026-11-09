"""Dönem (gün) seçimi: hızlı düğmeler + tarih aralığı + gün gün işaretleme (Excel'deki dilimleyicinin yerine)."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QDoubleSpinBox, QFrame, QHBoxLayout,
                               QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget)

from . import tema


def qd(d: date) -> QDate:
    return QDate(d.year, d.month, d.day)


def pd(q: QDate) -> date:
    return date(q.year(), q.month(), q.day())


def hafta_basi(d: date) -> date:
    return d - timedelta(days=d.weekday())


def ay_sonu(d: date) -> date:
    ilk = d.replace(day=28) + timedelta(days=4)
    return ilk - timedelta(days=ilk.day)


class GunlerDialog(QDialog):
    """Seçilen aralıktaki günleri tek tek işaretleme (verisi olmayan günler gri)."""

    def __init__(self, parent, gunler: List[date], isaretli: set, kapsam: Dict[date, int]):
        super().__init__(parent)
        self.setWindowTitle("Günleri seç")
        self.setMinimumWidth(340)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Hesaba girecek günleri işaretleyin.\nKaydı olmayan günler (tatil / hafta sonu) hesaba girmez."))
        self.liste = QListWidget()
        for g in gunler:
            n = kapsam.get(g, 0)
            adi = f"{g.strftime('%d.%m.%Y')}  {tema.GUNLER[g.weekday()]}"
            oge = QListWidgetItem(adi + (f"   ({n} kayıt)" if n else "   (kayıt yok)"))
            if n:
                oge.setFlags(oge.flags() | Qt.ItemIsUserCheckable)
                oge.setCheckState(Qt.Checked if g in isaretli else Qt.Unchecked)
            else:
                oge.setFlags(Qt.NoItemFlags)
                oge.setForeground(Qt.gray)
            oge.setData(Qt.UserRole, g)
            self.liste.addItem(oge)
        lay.addWidget(self.liste)
        alt = QHBoxLayout()
        b1, b2 = QPushButton("Tümünü işaretle"), QPushButton("Hiçbirini")
        b1.clicked.connect(lambda: self._hepsi(Qt.Checked))
        b2.clicked.connect(lambda: self._hepsi(Qt.Unchecked))
        alt.addWidget(b1)
        alt.addWidget(b2)
        alt.addStretch()
        lay.addLayout(alt)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Tamam")
        bb.button(QDialogButtonBox.Cancel).setText("Vazgeç")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _hepsi(self, durum):
        for i in range(self.liste.count()):
            o = self.liste.item(i)
            if o.flags() & Qt.ItemIsUserCheckable:
                o.setCheckState(durum)

    def secilenler(self) -> set:
        return {self.liste.item(i).data(Qt.UserRole) for i in range(self.liste.count())
                if self.liste.item(i).checkState() == Qt.Checked}


class DonemCubugu(QFrame):
    degisti = Signal()
    esik_degisti = Signal(float)
    kural_degisti = Signal(str)

    def __init__(self, kapsam_getir, esik: float, parent: Optional[QWidget] = None, kural: str = "gunluk"):
        super().__init__(parent)
        self.setObjectName("Kart")
        self._kapsam_getir = kapsam_getir
        self._kapsam: Dict[date, int] = {}
        self._isaretli: set = set()
        self._ilk: Optional[date] = None
        self._son: Optional[date] = None
        self._bloke = False
        self._bilinen: set = set()

        dis = QVBoxLayout(self)
        dis.setContentsMargins(14, 10, 14, 10)
        dis.setSpacing(8)
        lay = QHBoxLayout()
        lay.setSpacing(8)
        lay2 = QHBoxLayout()
        lay2.setSpacing(8)
        dis.addLayout(lay)
        dis.addLayout(lay2)
        lay.addWidget(self._etiket("Dönem"))
        self.grup = QButtonGroup(self)
        self.grup.setExclusive(True)
        self.hizli = {}
        for ad in ("Son 7 Gün", "Dün", "Bu Hafta", "Geçen Hafta", "Bu Ay", "Geçen Ay", "Tümü"):
            b = QPushButton(ad)
            b.setObjectName("Hizli")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.grup.addButton(b)
            self.hizli[ad] = b
            b.clicked.connect(lambda _=False, a=ad: self._hizli_sec(a))
            lay.addWidget(b)
        lay.addStretch(1)
        lay.addWidget(self._etiket("Eşik"))
        self.esik = QDoubleSpinBox()
        self.esik.setRange(0, 100)
        self.esik.setDecimals(0)
        self.esik.setSuffix(" %")
        self.esik.setValue(round(esik * 100))
        self.esik.setFixedWidth(90)
        self.esik.setButtonSymbols(QDoubleSpinBox.PlusMinus)
        self.esik.setToolTip("Bir makinenin o gün o vardiyada sayılması için gereken en düşük çalışma oranı")
        self.esik.editingFinished.connect(lambda: self.esik_degisti.emit(self.esik.value() / 100.0))
        lay.addWidget(self.esik)
        lay.addWidget(self._etiket("Kural"))
        self.kural = QComboBox()
        for anahtar, ad in tema.KURALLAR:
            self.kural.addItem(ad, anahtar)
        self.kural.setToolTip("\n\n".join(tema.KURAL_ACIKLAMA.values()))
        self.kural.setCurrentIndex(max(0, self.kural.findData(kural)))
        self.kural.activated.connect(lambda _=0: self.kural_degisti.emit(self.kural.currentData()))
        lay.addWidget(self.kural)
        lay2.addWidget(self._etiket("Tarih aralığı"))
        self.bas = QDateEdit()
        self.bit = QDateEdit()
        for e in (self.bas, self.bit):
            e.setCalendarPopup(True)
            e.setDisplayFormat("dd.MM.yyyy")
            e.setFixedWidth(132)
            e.dateChanged.connect(self._tarih_elle)
        lay2.addWidget(self.bas)
        lay2.addWidget(QLabel("–"))
        lay2.addWidget(self.bit)
        self.gunler_btn = QPushButton("Günleri işaretle…")
        self.gunler_btn.setObjectName("Hizli")
        self.gunler_btn.clicked.connect(self._gunler_ac)
        lay2.addWidget(self.gunler_btn)
        self.bilgi = QLabel("")
        self.bilgi.setObjectName("AltBaslik")
        lay2.addWidget(self.bilgi, 1)

    @staticmethod
    def _etiket(t):
        l = QLabel(t)
        l.setObjectName("KartBaslik")
        return l

    # ------------------------------------------------------------ dışarı
    def gunler(self) -> List[date]:
        return sorted(g for g in self._isaretli if self._kapsam.get(g))

    def aralik(self):
        return self._ilk, self._son

    def kapsam(self) -> Dict[date, int]:
        return self._kapsam

    def veri_yenilendi(self, ilk_secim: bool = False):
        self._kapsam = self._kapsam_getir()
        if not self._kapsam:
            self._ilk = self._son = None
            self._isaretli = set()
            self._bilgi_yaz()
            return
        if ilk_secim or self._ilk is None:
            self._hizli_sec("Son 7 Gün", sinyal=False)
        else:
            self._aralik_uygula(self._ilk, self._son, koru=True)

    # ------------------------------------------------------------ içeride
    def _bugun_referans(self) -> date:
        return max(self._kapsam) if self._kapsam else date.today()

    def _hizli_sec(self, ad: str, sinyal: bool = True):
        son_veri = self._bugun_referans()
        bugun = date.today()
        if ad == "Son 7 Gün":
            ilk, son = son_veri - timedelta(days=6), son_veri
        elif ad == "Dün":
            ilk = son = bugun - timedelta(days=1)
        elif ad == "Bu Hafta":
            ilk, son = hafta_basi(bugun), hafta_basi(bugun) + timedelta(days=6)
        elif ad == "Geçen Hafta":
            ilk = hafta_basi(bugun) - timedelta(days=7)
            son = ilk + timedelta(days=6)
        elif ad == "Bu Ay":
            ilk, son = bugun.replace(day=1), ay_sonu(bugun)
        elif ad == "Geçen Ay":
            son = bugun.replace(day=1) - timedelta(days=1)
            ilk = son.replace(day=1)
        else:  # Tümü
            ilk, son = min(self._kapsam), max(self._kapsam)
        self.hizli[ad].setChecked(True)
        self._aralik_uygula(ilk, son, sinyal=sinyal)

    def _aralik_uygula(self, ilk: date, son: date, koru: bool = False, sinyal: bool = True):
        self._ilk, self._son = ilk, son
        self._bloke = True
        self.bas.setDate(qd(ilk))
        self.bit.setDate(qd(son))
        self._bloke = False
        gunler = [ilk + timedelta(days=i) for i in range((son - ilk).days + 1)]
        if koru:
            self._isaretli = {g for g in gunler if self._kapsam.get(g) and (g in self._isaretli or g not in self._bilinen)}
        else:
            self._isaretli = {g for g in gunler if self._kapsam.get(g)}
        self._bilinen = set(gunler)
        self._bilgi_yaz()
        if sinyal:
            self.degisti.emit()

    def _tarih_elle(self):
        if self._bloke:
            return
        ilk, son = pd(self.bas.date()), pd(self.bit.date())
        if son < ilk:
            son = ilk
        for b in self.hizli.values():
            b.setAutoExclusive(False)
            b.setChecked(False)
            b.setAutoExclusive(True)
        self._aralik_uygula(ilk, son)

    def _gunler_ac(self):
        if self._ilk is None:
            return
        gunler = [self._ilk + timedelta(days=i) for i in range((self._son - self._ilk).days + 1)]
        d = GunlerDialog(self, gunler, self._isaretli, self._kapsam)
        if d.exec():
            self._isaretli = d.secilenler()
            self._bilgi_yaz()
            self.degisti.emit()

    def _bilgi_yaz(self):
        if self._ilk is None:
            self.bilgi.setText("Henüz veri yok")
            return
        tum = [self._ilk + timedelta(days=i) for i in range((self._son - self._ilk).days + 1)]
        verisiz = [g for g in tum if not self._kapsam.get(g)]
        metin = f"{len(self.gunler())} gün hesaba giriyor"
        if verisiz:
            metin += f"  ·  {len(verisiz)} gün kayıtsız"
        self.bilgi.setText(metin)
