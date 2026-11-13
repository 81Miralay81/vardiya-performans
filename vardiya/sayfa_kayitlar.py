"""Kayıtlar sayfası: veritabanındaki ham makine hareketlerini tablo olarak gösterir (süz, sırala, kopyala, Excel'e aktar)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QDateEdit, QFileDialog, QHBoxLayout, QHeaderView,
                               QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .takvim import TarihKutusu
from . import tema, veritabani as vt
from .hesap import statu_bul, vardiya_bul
from .sayfa_ortak import etiket, kart, tablo_menusu

BASLIKLAR = ["Makine", "Tip", "Durum", "Vardiya", "Başlangıç", "Bitiş", "Süre", "Operatör", "İş Emri", "Ürün Kodu", "Ürün Adı"]
EN_FAZLA = 30000
DURUM_RENK = {"Çalışıyor": "#E8F4D8", "Mola": "#EDE6F5", "Duruş": "#FBE3E0"}


class _Oge(QTableWidgetItem):
    """Sayısal / tarihsel sütunların doğru sıralanması için gizli sıralama anahtarı kullanır."""

    def __lt__(self, other):
        a, b = self.data(Qt.UserRole), other.data(Qt.UserRole)
        if a is not None and b is not None:
            return a < b
        return super().__lt__(other)


def _sure(sn: float) -> str:
    sn = int(round(sn))
    return f"{sn // 3600:02d}:{sn % 3600 // 60:02d}:{sn % 60:02d}"


class KayitlarSayfasi(QWidget):
    def __init__(self, ana):
        super().__init__()
        self.ana = ana
        self._satirlar = []
        kok = QVBoxLayout(self)
        kok.setContentsMargins(26, 22, 26, 22)
        kok.setSpacing(12)
        ust = QHBoxLayout()
        sol = QVBoxLayout()
        sol.addWidget(etiket("Kayıtlar", "Baslik"))
        sol.addWidget(etiket("Veritabanındaki ham makine hareketleri. Sütun başlığına tıklayarak sıralayın; sağ tıklayarak kopyalayın.", "AltBaslik"))
        ust.addLayout(sol, 1)
        self.b_excel = QPushButton("Excel'e Aktar")
        self.b_excel.clicked.connect(self.excele_aktar)
        ust.addWidget(self.b_excel, 0, Qt.AlignTop)
        kok.addLayout(ust)

        f = kart(QHBoxLayout, 12)
        self.bas, self.bit = TarihKutusu(), TarihKutusu()
        for e in (self.bas, self.bit):
            e.setCalendarPopup(True)
            e.setDisplayFormat("dd.MM.yyyy")
            e.setFixedWidth(132)
        self.makine = QComboBox()
        self.tip = QComboBox()
        self.durum = QComboBox()
        self.durum.addItems(["Tümü", "Çalışıyor", "Mola", "Duruş"])
        self.vardiya = QComboBox()
        self.vardiya.addItems(["Tümü", "1. vardiya", "2. vardiya", "3. vardiya"])
        for ad, w in (("Tarih", self.bas), ("–", self.bit), ("Makine", self.makine), ("Tip", self.tip),
                      ("Durum", self.durum), ("Vardiya", self.vardiya)):
            f.layout().addWidget(etiket(ad, "KartBaslik", kelime=False))
            f.layout().addWidget(w)
        f.layout().addStretch(1)
        self.b_getir = QPushButton("Listele")
        self.b_getir.setObjectName("Ana")
        self.b_getir.clicked.connect(self.listele)
        f.layout().addWidget(self.b_getir)
        kok.addWidget(f)
        self.bilgi = etiket("", "AltBaslik")
        kok.addWidget(self.bilgi)

        self.tablo = QTableWidget(0, len(BASLIKLAR))
        self.tablo.setHorizontalHeaderLabels(BASLIKLAR)
        self.tablo.verticalHeader().hide()
        self.tablo.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tablo.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tablo.setAlternatingRowColors(False)
        self.tablo.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.tablo.horizontalHeader().setStretchLastSection(True)
        for i, g in enumerate((70, 170, 80, 80, 165, 165, 80, 150, 95, 130)):
            self.tablo.setColumnWidth(i, g)
        tablo_menusu(self.tablo)
        kok.addWidget(self.tablo, 1)
        self._ilk_kez = True

    # ------------------------------------------------------------------ veri
    def yenile(self):
        kap = self.ana.kapsam()
        if self._ilk_kez and kap:
            son = max(kap)
            self.bas.setDate(QDate(son.year, son.month, son.day))
            self.bit.setDate(QDate(son.year, son.month, son.day))
            self._ilk_kez = False
        ay = self.ana.ayar
        onceki_m, onceki_t = self.makine.currentText(), self.tip.currentText()
        self.makine.clear()
        self.makine.addItems(["Tümü"] + list(ay["makineler"]))
        tipler = [r[0] for r in self.ana.con.execute("SELECT DISTINCT tip FROM kayit ORDER BY tip")]
        self.tip.clear()
        self.tip.addItems(["Tümü"] + [t for t in tipler if t])
        if onceki_m:
            self.makine.setCurrentText(onceki_m)
        if onceki_t:
            self.tip.setCurrentText(onceki_t)
        self.listele()

    def _tarih(self, e: QDateEdit) -> date:
        q = e.date()
        return date(q.year(), q.month(), q.day())

    def listele(self):
        ilk, son = self._tarih(self.bas), self._tarih(self.bit)
        if son < ilk:
            ilk, son = son, ilk
        kosul = ["baslangic >= ?", "baslangic < ?"]
        arg = [ilk.strftime("%Y-%m-%d 00:00:00"), (son + timedelta(days=1)).strftime("%Y-%m-%d 00:00:00")]
        if self.makine.currentIndex() > 0:
            kosul.append("makine = ?")
            arg.append(self.makine.currentText())
        if self.tip.currentIndex() > 0:
            kosul.append("tip = ?")
            arg.append(self.tip.currentText())
        rows = self.ana.con.execute(
            "SELECT makine, tip, baslangic, bitis, operator, is_emri, urun_kodu, urun_adi FROM kayit WHERE "
            + " AND ".join(kosul) + " ORDER BY baslangic DESC, makine", arg).fetchall()
        v_sec = self.vardiya.currentIndex()
        d_sec = self.durum.currentText()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.tablo.setSortingEnabled(False)
            self.tablo.setRowCount(0)
            gosterilen, cal_sn, diger = [], 0.0, 0.0
            toplam_uygun = 0
            for r in rows:
                bas = datetime.strptime(r["baslangic"], vt.BICIM)
                bit = datetime.strptime(r["bitis"], vt.BICIM)
                v = vardiya_bul(bas.hour)
                durum = statu_bul(r["tip"])
                if (v_sec and v != v_sec) or (d_sec != "Tümü" and durum != d_sec):
                    continue
                toplam_uygun += 1
                sn = max(0.0, (bit - bas).total_seconds())
                if durum == "Çalışıyor":
                    cal_sn += sn
                else:
                    diger += sn
                if len(gosterilen) < EN_FAZLA:
                    gosterilen.append((r, bas, bit, v, durum, sn))
            self.tablo.setRowCount(len(gosterilen))
            for i, (r, bas, bit, v, durum, sn) in enumerate(gosterilen):
                degerler = [(r["makine"], r["makine"]), (r["tip"], r["tip"]), (durum, durum), (f"{v}", v),
                            (bas.strftime("%d.%m.%Y %H:%M:%S"), bas.timestamp()), (bit.strftime("%d.%m.%Y %H:%M:%S"), bit.timestamp()),
                            (_sure(sn), sn), (r["operator"] or "", r["operator"] or ""), (r["is_emri"] or "", r["is_emri"] or ""),
                            (r["urun_kodu"] or "", r["urun_kodu"] or ""), (r["urun_adi"] or "", r["urun_adi"] or "")]
                for j, (metin, anahtar) in enumerate(degerler):
                    it = _Oge(metin)
                    it.setData(Qt.UserRole, anahtar)
                    if j == 2:
                        it.setBackground(QColor(DURUM_RENK[durum]))
                    if j in (3, 6):
                        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self.tablo.setItem(i, j, it)
            self.tablo.setSortingEnabled(True)
            self.tablo.horizontalHeader().setSortIndicator(4, Qt.DescendingOrder)
        finally:
            QApplication.restoreOverrideCursor()
        self._satirlar = gosterilen
        metin = (f"{toplam_uygun:,} kayıt".replace(",", ".") + f" · çalışma {_sure(cal_sn)} · diğer {_sure(diger)} (saat:dakika:saniye)")
        if toplam_uygun > EN_FAZLA:
            metin += f" · ilk {EN_FAZLA:,} kayıt gösteriliyor, aralığı daraltın".replace(",", ".")
        self.bilgi.setText(metin)

    def excele_aktar(self):
        if not self._satirlar:
            self.ana.mesaj("Aktarılacak kayıt yok.")
            return
        yol, _ = QFileDialog.getSaveFileName(self, "Excel olarak kaydet",
                                             f"Kayitlar {self._tarih(self.bas):%d.%m.%Y}-{self._tarih(self.bit):%d.%m.%Y}.xlsx",
                                             "Excel (*.xlsx)")
        if not yol:
            return
        from openpyxl import Workbook
        wb = Workbook(write_only=True)
        ws = wb.create_sheet("Kayıtlar")
        ws.append(BASLIKLAR)
        for r, bas, bit, v, durum, sn in self._satirlar:
            ws.append([r["makine"], r["tip"], durum, v, bas, bit, sn / 86400.0, r["operator"], r["is_emri"], r["urun_kodu"], r["urun_adi"]])
        wb.save(yol)
        self.ana.mesaj(f"Kaydedildi: {yol}")
