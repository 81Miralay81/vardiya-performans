"""Veri Aktar sayfası: Cormind Excel dosyasını yükler, veri durumunu gösterir."""
from __future__ import annotations

import os
import base64
import sqlite3
from datetime import date, timedelta

from PySide6.QtCore import QDate, QSettings, QThread, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QApplication, QDateEdit, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView, QAbstractItemView)

from . import cormind, ice_aktar, tema, veritabani as vt
from .sayfa_ortak import etiket, kart, tablo_menusu


class BirakAlani(QFrame):
    def __init__(self, ac_fn, yukle_fn):
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("Kart")
        self.setStyleSheet(f"QFrame#Kart {{ border: 2px dashed {tema.CIZGI}; background: #FAFBFD; }}")
        self.yukle_fn = yukle_fn
        l = QVBoxLayout(self)
        l.setContentsMargins(24, 28, 24, 28)
        l.setAlignment(Qt.AlignCenter)
        b = etiket("Cormind'den aldığınız Excel dosyasını buraya sürükleyin", "KartDeger", kelime=False)
        b.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {tema.LACIVERT};")
        b.setAlignment(Qt.AlignCenter)
        a = etiket("ya da düğmeye basıp dosyayı seçin (.xls, .xlsx, .xlsm veya .csv)", "AltBaslik", kelime=False)
        a.setAlignment(Qt.AlignCenter)
        self.btn = QPushButton("Excel dosyası seç…")
        self.btn.setObjectName("Ana")
        self.btn.setMinimumHeight(40)
        self.btn.setMinimumWidth(220)
        self.btn.clicked.connect(ac_fn)
        l.addWidget(b)
        l.addWidget(a)
        l.addSpacing(8)
        l.addWidget(self.btn, 0, Qt.AlignCenter)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        yollar = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if yollar:
            self.yukle_fn(yollar)


class CormindIs(QThread):
    """Cormind'den çekme işi arka planda yürür (pencere donmaz). Kendi veritabanı bağlantısını açar."""
    bitti = Signal(dict)
    hata = Signal(str)
    adim = Signal(dict)

    def __init__(self, db_yolu, adres, kullanici, sifre, ilk, son, idler, parent=None, uzanan=True):
        super().__init__(parent)
        self.a = (db_yolu, adres, kullanici, sifre, ilk, son, idler)
        self._dur = False
        self.uzanan = uzanan

    def durdur(self):
        self._dur = True

    def run(self):
        db_yolu, adres, kullanici, sifre, ilk, son, idler = self.a
        try:
            con = vt.ac(db_yolu)
            try:
                self.bitti.emit(cormind.cek(con, adres, kullanici, sifre, ilk, son, idler, adim=self.adim.emit, iptal=lambda: self._dur, uzanan=self.uzanan))
            finally:
                con.close()
        except cormind.CormindHata as e:
            self.hata.emit(str(e))
        except Exception as e:  # noqa: BLE001
            self.hata.emit(f"Beklenmeyen hata: {type(e).__name__}: {e}")


class CormindKarti(QFrame):
    """Cormind'e doğrudan bağlanıp seçilen günlerin verisini çeker. Kullanıcı adı/şifre yalnızca bu bilgisayarda saklanır."""

    def __init__(self, ana):
        super().__init__()
        self.ana = ana
        self.setObjectName("Kart")
        self._is = None
        self._ayar = QSettings("Teknorot", "VardiyaPerformans")
        l = QVBoxLayout(self)
        l.setContentsMargins(16, 12, 16, 12)
        l.setSpacing(8)
        l.addWidget(etiket("CORMIND'DEN DOĞRUDAN ÇEK", "KartBaslik"))
        l.addWidget(etiket("Excel indirmeden, seçtiğiniz günlerin makine hareketlerini Cormind'den alır. Aynı kayıt tekrar gelirse çoğalmaz. "
                           "Kullanıcı adı ve şifre yalnızca bu bilgisayarda saklanır, veritabanına yazılmaz.", "AltBaslik"))
        s1 = QHBoxLayout()
        s1.setSpacing(8)
        self.adres = QLineEdit(ana.ayar.get("cormind_adres", cormind.VARSAYILAN_ADRES))
        self.adres.setMinimumWidth(190)
        self.kullanici = QLineEdit(self._ayar.value("cormind/kullanici", ""))
        self.kullanici.setPlaceholderText("Kullanıcı adı")
        self.sifre = QLineEdit(self._sifre_oku())
        self.sifre.setPlaceholderText("Şifre")
        self.sifre.setEchoMode(QLineEdit.Password)
        for etk, w in (("Adres", self.adres), ("Kullanıcı", self.kullanici), ("Şifre", self.sifre)):
            s1.addWidget(etiket(etk, "KartBaslik", kelime=False))
            s1.addWidget(w, 1)
        l.addLayout(s1)
        s2 = QHBoxLayout()
        s2.setSpacing(8)
        self.bas, self.bit = QDateEdit(), QDateEdit()
        for e in (self.bas, self.bit):
            e.setCalendarPopup(True)
            e.setDisplayFormat("dd.MM.yyyy")
            e.setFixedWidth(132)
        dun = date.today() - timedelta(days=1)
        self.bas.setDate(QDate(dun.year, dun.month, dun.day))
        self.bit.setDate(QDate(dun.year, dun.month, dun.day))
        self.btn = QPushButton("Cormind'den çek")
        self.btn.setObjectName("Ana")
        self.btn.clicked.connect(self.cek)
        s2.addWidget(etiket("Tarih aralığı", "KartBaslik", kelime=False))
        s2.addWidget(self.bas)
        s2.addWidget(QLabel("–"))
        s2.addWidget(self.bit)
        s2.addWidget(self.btn)
        self.b_dur = QPushButton("Durdur")
        self.b_dur.setObjectName("Tehlike")
        self.b_dur.setToolTip("Sıradaki aya geçmeden durur; o ana kadar çekilenler kayıtlı kalır")
        self.b_dur.clicked.connect(self._durdur)
        self.b_dur.hide()
        s2.addWidget(self.b_dur)
        s2.addStretch(1)
        l.addLayout(s2)
        from PySide6.QtWidgets import QCheckBox
        self.uzanan = QCheckBox("Önceden başlayıp seçilen günlere uzanan duruşları da getir (en çok 90 gün geriye bakar)")
        self.uzanan.setToolTip("Günlerce süren 'İŞ EMRİ PLAN YOK' gibi duruşlar seçilen günlerden önce başlamış olabilir.\n"
                               "İşaretliyken Cormind'e ikinci, sınırlı bir sorgu daha gönderilir. Çekim yavaşlarsa işareti kaldırın.")
        self.uzanan.setChecked(str(self._ayar.value("cormind/uzanan", "1")) != "0")
        l.addWidget(self.uzanan)
        l.addWidget(etiket("Bir aydan uzun aralık ay ay çekilir (Cormind toplu çekime izin vermiyor); her ay bitince kaydedilir.", "AltBaslik"))
        from PySide6.QtWidgets import QProgressBar
        self.cubuk = QProgressBar()
        self.cubuk.setTextVisible(True)
        self.cubuk.setFixedHeight(18)
        self.cubuk.hide()
        l.addWidget(self.cubuk)
        self.durum = etiket("", "AltBaslik")
        self.durum.hide()
        l.addWidget(self.durum)

    def _sifre_oku(self) -> str:
        try:
            return base64.b64decode(self._ayar.value("cormind/sifre", "")).decode("utf8")
        except Exception:  # noqa: BLE001
            return ""

    def cek(self):
        if self._is is not None and self._is.isRunning():
            return
        k, s = self.kullanici.text().strip(), self.sifre.text()
        if not k or not s:
            self._yaz("Kullanıcı adı ve şifre girin.", hata=True)
            return
        ilk = date(self.bas.date().year(), self.bas.date().month(), self.bas.date().day())
        son = date(self.bit.date().year(), self.bit.date().month(), self.bit.date().day())
        if son < ilk:
            ilk, son = son, ilk
        self._ayar.setValue("cormind/kullanici", k)
        self._ayar.setValue("cormind/sifre", base64.b64encode(s.encode("utf8")).decode())
        vt.ayar_yaz(self.ana.con, "cormind_adres", self.adres.text().strip())
        self.btn.setEnabled(False)
        self.b_dur.setEnabled(True)
        self.b_dur.show()
        self.cubuk.setRange(0, 0)               # belirsiz: bağlanıyor
        self.cubuk.setFormat("Bağlanılıyor…")
        self.cubuk.show()
        self._yaz("Cormind'e bağlanılıyor…")
        idler = self.ana.ayar.get("cormind_makine_idleri") or cormind.VARSAYILAN_MAKINE_IDLERI
        self._ayar.setValue("cormind/uzanan", "1" if self.uzanan.isChecked() else "0")
        self._is = CormindIs(self.ana.db_yolu, self.adres.text(), k, s, ilk, son, idler, self, self.uzanan.isChecked())
        self._is.bitti.connect(self._bitti)
        self._is.adim.connect(self._adim)
        self._is.hata.connect(lambda m: self._son(m, hata=True))
        self._is.start()

    def _durdur(self):
        if self._is is not None and self._is.isRunning():
            self._is.durdur()
            self.b_dur.setEnabled(False)
            self._yaz("Durduruluyor: şu anki ay bitince durulacak, çekilenler kayıtlı kalacak…")

    def _adim(self, b: dict):
        """Çekim ilerlemesi: hangi parça, hangi aşama, kaç kayıt."""
        n, i = b["parca_sayisi"], b["parca"]
        if b["asama"] == "baglaniyor":
            return
        ad = (f"{cormind.AY_ADLARI[b['ilk'].month - 1]} {b['ilk'].year}" if n > 1 else f"{b['ilk']:%d.%m.%Y} – {b['son']:%d.%m.%Y}")
        say = lambda x: f"{x:,}".replace(",", ".")
        pay = (b["kayit"] / b["toplam"]) if b["toplam"] else (1.0 if b["asama"] == "kaydedildi" else 0.0)
        self.cubuk.setRange(0, 1000)
        self.cubuk.setValue(int(1000 * ((i - 1) + min(1.0, pay)) / max(1, n)))
        self.cubuk.setFormat(f"{i}/{n}  ·  %p%" if n > 1 else "%p%")
        if b["asama"] == "cekiliyor":
            ayrinti = (f"{say(b['kayit'])} / {say(b['toplam'])} kayıt alındı" if b["toplam"] else "Cormind'den yanıt bekleniyor…")
            metin = f"{ad} çekiliyor: {ayrinti}"
        else:
            metin = f"{ad} kaydedildi: {say(b['kayit'])} kayıt"
        if n > 1:
            metin = f"Adım {i}/{n} · " + metin + f"  ·  şu ana kadar toplam {say(b['kaydedilen'])} kayıt kaydedildi"
        self._yaz(metin)

    def _bitti(self, r: dict):
        tip = ", ".join(f"{ad}: {n}" for ad, n in list(r["tipler"].items())[:12])
        metin = ((f"DURDURULDU: {r['biten_parca']}/{r['parca_sayisi']} ay çekildi. " if r.get("durduruldu") else "")
                 + (f"{r['parca_sayisi']} ay sırayla çekildi. " if r.get("parca_sayisi", 1) > 1 and not r.get("durduruldu") else "")
                 + f"{r['toplam']} kayıt alındı ve kaydedildi"
                 + (f" (seçilen günlerde daha önce kayıtlı olan {r['silinen']} kayıt Cormind'dekiyle değiştirildi)" if r.get("silinen") else "")
                 + (f"; {r['atlanan']} kayıt atlandı" if r["atlanan"] else "") + f".\nTip dağılımı: {tip}"
                 + ("\nUYARI: Cormind geniş sorguyu kabul etmedi; yalnızca seçilen günlerde BAŞLAYAN kayıtlar alındı. "
                    "Daha önce başlayıp bu günlere uzanan uzun duruşlar eksik olabilir." if r.get("dar_sorgu") else "")
                 + ("\nUYARI: Beklenenden çok kayıt geldiği için çekim sınırda durduruldu; daha kısa bir tarih aralığı seçin." if r.get("kesildi") else ""))
        if r["yeni_makineler"]:
            metin += "\nMakine listesine eklendi: " + ", ".join(r["yeni_makineler"])
        self._son(metin)
        self.ana.ayar = vt.ayar_oku(self.ana.con)
        self.ana.veri_yenilendi()

    def _son(self, metin: str, hata: bool = False):
        self.btn.setEnabled(True)
        self.b_dur.hide()
        self.cubuk.hide()
        self._yaz(metin, hata)

    def _yaz(self, metin: str, hata: bool = False):
        self.durum.setObjectName("Uyari" if hata else "Basari")
        self.durum.setStyle(self.durum.style())
        self.durum.setText(metin)
        self.durum.show()


class VeriSayfasi(QWidget):
    def __init__(self, ana):
        super().__init__()
        self.ana = ana
        kok = QVBoxLayout(self)
        kok.setContentsMargins(26, 22, 26, 22)
        kok.setSpacing(14)
        kok.addWidget(etiket("Veri Aktar", "Baslik"))
        kok.addWidget(etiket("Veriyi Cormind'den doğrudan çekin ya da Excel listesini yükleyin. Aynı gün ve aynı kayıt tekrar gelirse çoğalmaz; "
                             "formül hatası olan satırlar atlanır.", "AltBaslik"))
        self.cormind = CormindKarti(ana)
        kok.addWidget(self.cormind)
        self.alan = BirakAlani(self.dosya_sec, self.yukle)
        kok.addWidget(self.alan)
        self.sonuc = QLabel("")
        self.sonuc.setWordWrap(True)
        self.sonuc.hide()
        kok.addWidget(self.sonuc)
        self.uyari = QLabel("")
        self.uyari.setObjectName("Uyari")
        self.uyari.setWordWrap(True)
        self.uyari.hide()
        kok.addWidget(self.uyari)

        alt = QHBoxLayout()
        alt.setSpacing(14)
        sol = kart()
        sol.layout().addWidget(etiket("Veri durumu (gün gün)", "KartBaslik"))
        self.gun_tablo = self._tablo(["Tarih", "Gün", "Kayıt"])
        sol.layout().addWidget(self.gun_tablo)
        sag = kart()
        sag.layout().addWidget(etiket("Son aktarımlar", "KartBaslik"))
        self.gecmis_tablo = self._tablo(["Zaman", "Dosya", "Yeni", "Güncel", "Aynı", "Atlanan"])
        sag.layout().addWidget(self.gecmis_tablo)
        alt.addWidget(sol, 2)
        alt.addWidget(sag, 3)
        kok.addLayout(alt, 1)
        self.yenile()

    @staticmethod
    def _tablo(basliklar):
        t = QTableWidget(0, len(basliklar))
        t.setHorizontalHeaderLabels(basliklar)
        t.verticalHeader().hide()
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionMode(QAbstractItemView.NoSelection)
        t.horizontalHeader().setStretchLastSection(True)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        tablo_menusu(t)
        return t

    def dosya_sec(self):
        yollar, _ = QFileDialog.getOpenFileNames(self, "Cormind dosyasını seç", "",
                                                 "Excel / CSV (*.xls *.xlsx *.xlsm *.csv);;Tüm dosyalar (*.*)")
        if yollar:
            self.yukle(yollar)

    def yukle(self, yollar):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        mesajlar, atlanan, yeni_m, hatalar = [], [], [], []
        try:
            for y in yollar:
                try:
                    s = ice_aktar.aktar(self.ana.con, y)
                    mesajlar.append(f"{s.dosya}: {s.ozet()}")
                    atlanan += [(s.dosya, no, neden) for no, neden in s.atlanan]
                    yeni_m += s.yeni_makineler
                except Exception as ex:  # noqa: BLE001 - kullanıcıya gösterilir
                    hatalar.append(f"{os.path.basename(y)}: {ex}")
        finally:
            QApplication.restoreOverrideCursor()
        self.ana.veri_yenilendi()
        if mesajlar:
            self.sonuc.setObjectName("Basari")
            self.sonuc.setText("\n".join(mesajlar))
            self.sonuc.setStyle(self.sonuc.style())
            self.sonuc.show()
        else:
            self.sonuc.hide()
        notlar = list(hatalar)
        if atlanan:
            ornek = ", ".join(f"satır {no} ({neden})" for _, no, neden in atlanan[:6])
            notlar.append(f"{len(atlanan)} hatalı satır hesaba alınmadı: {ornek}" + (" …" if len(atlanan) > 6 else ""))
        if yeni_m:
            notlar.append("Makine listesine eklendi: " + ", ".join(sorted(set(yeni_m))))
        self.uyari.setText("\n".join(notlar))
        self.uyari.setVisible(bool(notlar))
        self.yenile()

    def yenile(self):
        kap = self.ana.kapsam()
        self.gun_tablo.setRowCount(0)
        if kap:
            ilk, son = min(kap), max(kap)
            gunler = [ilk + timedelta(days=i) for i in range((son - ilk).days + 1)]
            self.gun_tablo.setRowCount(len(gunler))
            for i, g in enumerate(reversed(gunler)):
                n = kap.get(g, 0)
                for j, t in enumerate((tema.tarih(g), tema.GUNLER[g.weekday()], str(n) if n else "kayıt yok")):
                    it = QTableWidgetItem(t)
                    if not n:
                        it.setForeground(QColor("#9AA3B8"))
                    if j == 2:
                        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self.gun_tablo.setItem(i, j, it)
        gec = vt.aktarim_gecmisi(self.ana.con, 12)
        self.gecmis_tablo.setRowCount(len(gec))
        for i, g in enumerate(gec):
            for j, t in enumerate((g["zaman"][5:16].replace("-", "."), g["dosya"] or "", g["yeni"], g["guncellenen"], g["ayni"], g["atlanan"])):
                it = QTableWidgetItem(str(t))
                if j >= 2:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.gecmis_tablo.setItem(i, j, it)
