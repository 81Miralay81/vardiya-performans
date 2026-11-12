"""Raporlar sayfası: günlük / haftalık / aylık raporları A3 olarak hazırlar (PDF, yazdırma, resim, arşiv)."""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta
from typing import List, Optional

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMarginsF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (QGuiApplication, QImage, QKeySequence, QPageLayout, QPageSize, QPainter, QPdfWriter, QPixmap,
                           QShortcut)
from PySide6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFileDialog, QFrame,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox,
                               QStackedWidget, QVBoxLayout, QWidget)

from . import cizim, tema, veritabani as vt
from .donem import ay_sonu, hafta_basi, pd, qd
from .hesap import VARDIYALAR, cormind_hesabi, hesapla
from .kot import idari_icerik, kot_coz, metne_cevir
from .sayfa_ortak import SefCombo, etiket, kart, resim_menusu

TURLER = ("Günlük", "Haftalık", "Aylık", "Özel aralık")


def pdf_yaz(hedef, r: dict):
    """hedef: dosya yolu (str) ya da QIODevice."""
    w = QPdfWriter(hedef)
    w.setPageLayout(QPageLayout(QPageSize(QPageSize.A3), QPageLayout.Landscape, QMarginsF(0, 0, 0, 0)))
    w.setResolution(150)
    w.setTitle(r["baslik"])
    p = QPainter(w)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    r2 = dict(r, yer_tutucu=False)
    for i in range(cizim.sayfa_sayisi(r2)):
        if i:
            w.newPage()
        cizim.sayfa_ciz(p, QRectF(0, 0, w.width(), w.height()), r2, i)
    p.end()


class MetinDialog(QDialog):
    """Çok satırlı metin girişi (KOT yapıştırma ve rapor metnini düzenleme)."""

    def __init__(self, parent, baslik: str, aciklama: str, metin: str = "", ek_dugme: str = ""):
        super().__init__(parent)
        self.setWindowTitle(baslik)
        self.resize(820, 600)
        self.ek = False
        l = QVBoxLayout(self)
        l.addWidget(etiket(aciklama, "AltBaslik"))
        self.kutu = QPlainTextEdit()
        self.kutu.setPlainText(metin)
        l.addWidget(self.kutu, 1)
        d = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        d.button(QDialogButtonBox.Ok).setText("Tamam")
        d.button(QDialogButtonBox.Cancel).setText("Vazgeç")
        if ek_dugme:
            b = d.addButton(ek_dugme, QDialogButtonBox.ResetRole)
            b.clicked.connect(self._ek)
        d.accepted.connect(self.accept)
        d.rejected.connect(self.reject)
        l.addWidget(d)

    def _ek(self):
        self.ek = True
        self.accept()

    def metin(self) -> str:
        return self.kutu.toPlainText()


def pdf_bayt(r: dict) -> bytes:
    tampon = QBuffer()
    tampon.open(QIODevice.WriteOnly)
    pdf_yaz(tampon, r)
    tampon.close()
    return bytes(tampon.data())


def sonuc_ozeti(s) -> dict:
    return {
        "gunler": [g.isoformat() for g in s.gunler],
        "vardiyalar": {str(v): {"calisma": o.calisma, "durus": o.durus, "mola": o.mola, "makine": o.makine_sayisi,
                                "gun": o.gun_sayisi} for v, o in s.vardiyalar.items()},
        "genel": list(s.genel),
        "makineler": {m: list(x) for m, x in s.makine_ort.items()},
    }


class RaporSayfasi(QWidget):
    def __init__(self, ana):
        super().__init__()
        self.ana = ana
        self.setAcceptDrops(True)
        self._r: Optional[dict] = None
        self._gorsel: Optional[QImage] = None
        self._anahtar = ""
        self._gunler: List[date] = []
        self._varsayilan_yapildi = False
        self._zamanlayici = QTimer(self)
        self._zamanlayici.setSingleShot(True)
        self._zamanlayici.setInterval(120)
        self._zamanlayici.timeout.connect(self._yenile_simdi)

        kok = QHBoxLayout(self)
        kok.setContentsMargins(26, 18, 26, 18)
        kok.setSpacing(14)

        # ------------------------------------------------ sol panel
        panel = kart(kenar=16)
        panel.setFixedWidth(330)
        pl = panel.layout()
        pl.setSpacing(10)
        pl.addWidget(etiket("Raporlar", "Baslik"))
        pl.addWidget(etiket("A3 yatay çıktı için hazırlanır.", "AltBaslik"))

        pl.addWidget(etiket("RAPOR DÜZENİ", "KartBaslik"))
        satir = QHBoxLayout()
        self.duzen_grup = QButtonGroup(self)
        self.b_makine, self.b_vardiya, self.b_idari = QPushButton("Makine"), QPushButton("Vardiya"), QPushButton("İdari")
        self.b_makine.setToolTip("Makine bazlı rapor")
        self.b_vardiya.setToolTip("Vardiya bazlı rapor")
        self.b_idari.setToolTip("İdari rapor: grup lideri bildirimlerinden (KOT) değerlendirme metni, tablolar ve beş grafik (3 sayfa)")
        for b, anahtar in ((self.b_makine, "makine"), (self.b_vardiya, "vardiya"), (self.b_idari, "idari")):
            b.setObjectName("Hizli")
            b.setCheckable(True)
            b.setProperty("duzen", anahtar)
            self.duzen_grup.addButton(b)
            satir.addWidget(b)
            b.clicked.connect(self._degisti)
        self.b_makine.setChecked(True)
        pl.addLayout(satir)

        pl.addWidget(etiket("DÖNEM", "KartBaslik"))
        self.tur = QComboBox()
        self.tur.addItems(TURLER)
        self.tur.currentIndexChanged.connect(self._tur_degisti)
        pl.addWidget(self.tur)
        self.yigin = QStackedWidget()
        ref = self.ana.son_veri_gunu()
        self.gun_sec = QDateEdit(qd(ref))
        self.gun_sec.setCalendarPopup(True)
        self.gun_sec.setDisplayFormat("dd.MM.yyyy")
        self.yigin.addWidget(self.gun_sec)
        h = QWidget()
        hl = QHBoxLayout(h)
        hl.setContentsMargins(0, 0, 0, 0)
        self.hafta = QSpinBox()
        self.hafta.setRange(1, 53)
        self.hafta.setPrefix("Hafta ")
        self.hafta.setButtonSymbols(QSpinBox.PlusMinus)
        self.hafta_yil = QSpinBox()
        self.hafta_yil.setRange(2020, 2100)
        self.hafta_yil.setButtonSymbols(QSpinBox.PlusMinus)
        iso = ref.isocalendar()
        self.hafta.setValue(iso[1])
        self.hafta_yil.setValue(iso[0])
        hl.addWidget(self.hafta)
        hl.addWidget(self.hafta_yil)
        self.yigin.addWidget(h)
        a = QWidget()
        al = QHBoxLayout(a)
        al.setContentsMargins(0, 0, 0, 0)
        self.ay = QComboBox()
        self.ay.addItems(tema.AYLAR)
        self.ay.setCurrentIndex(ref.month - 1)
        self.ay_yil = QSpinBox()
        self.ay_yil.setRange(2020, 2100)
        self.ay_yil.setButtonSymbols(QSpinBox.PlusMinus)
        self.ay_yil.setValue(ref.year)
        al.addWidget(self.ay)
        al.addWidget(self.ay_yil)
        self.yigin.addWidget(a)
        o = QWidget()
        ol = QHBoxLayout(o)
        ol.setContentsMargins(0, 0, 0, 0)
        self.o_bas, self.o_bit = QDateEdit(qd(ref - timedelta(days=6))), QDateEdit(qd(ref))
        for e in (self.o_bas, self.o_bit):
            e.setCalendarPopup(True)
            e.setDisplayFormat("dd.MM.yyyy")
            ol.addWidget(e)
        self.yigin.addWidget(o)
        pl.addWidget(self.yigin)
        for w in (self.gun_sec, self.o_bas, self.o_bit):
            w.dateChanged.connect(self._degisti)
        for w in (self.hafta, self.hafta_yil, self.ay_yil):
            w.valueChanged.connect(self._degisti)
        self.ay.currentIndexChanged.connect(self._degisti)

        pl.addWidget(etiket("BAŞLIK", "KartBaslik"))
        self.baslik = QLineEdit()
        self.baslik.editingFinished.connect(self._zamanla)
        pl.addWidget(self.baslik)

        pl.addWidget(etiket("GRUP LİDERLERİ", "KartBaslik"))
        self.combolar = {}
        for v in VARDIYALAR:
            sat = QHBoxLayout()
            sat.addWidget(QLabel(f"{v}. Vardiya"), 1)
            c = SefCombo(ana, v, lambda: self._gunler)
            self.combolar[v] = c
            sat.addWidget(c, 2)
            pl.addLayout(sat)

        self.gorsel_kutu = QWidget()
        gl = QVBoxLayout(self.gorsel_kutu)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(6)
        gl.addWidget(etiket("CORMIND DURUŞ GRAFİĞİ", "KartBaslik"))
        self.gorsel_durum = etiket("Henüz eklenmedi", "AltBaslik")
        gl.addWidget(self.gorsel_durum)
        self.b_yapistir = QPushButton("Panodan Yapıştır (Ctrl+V)")
        self.b_dosya = QPushButton("Dosyadan…")
        self.b_kaldir = QPushButton("Kaldır")
        self.b_kaldir.setObjectName("Tehlike")
        gl.addWidget(self.b_yapistir)
        g1 = QHBoxLayout()
        g1.addWidget(self.b_dosya)
        g1.addWidget(self.b_kaldir)
        gl.addLayout(g1)
        self.b_yapistir.clicked.connect(self.panodan_yapistir)
        self.b_dosya.clicked.connect(self.gorsel_dosya)
        self.b_kaldir.clicked.connect(self.gorsel_kaldir)
        QShortcut(QKeySequence.Paste, self, activated=self._ctrl_v)
        pl.addWidget(self.gorsel_kutu)

        self.idari_kutu = QWidget()
        il = QVBoxLayout(self.idari_kutu)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(6)
        il.addWidget(etiket("GRUP LİDERİ BİLDİRİMLERİ (KOT)", "KartBaslik"))
        self.kot_durum = etiket("", "AltBaslik")
        il.addWidget(self.kot_durum)
        self.b_kot = QPushButton("KOT Yapıştır…")
        self.b_metin = QPushButton("Metni Düzenle")
        self.b_kot_sil = QPushButton("KOT'ları Sil")
        self.b_kot_sil.setToolTip("Seçili dönemin KOT kayıtlarını siler")
        self.b_kot_sil.setObjectName("Tehlike")
        il.addWidget(self.b_kot)
        i1 = QHBoxLayout()
        i1.addWidget(self.b_metin)
        i1.addWidget(self.b_kot_sil)
        il.addLayout(i1)
        self.b_kot.clicked.connect(self.kot_yapistir)
        self.b_metin.clicked.connect(self.metni_duzenle)
        self.b_kot_sil.clicked.connect(self.kot_sil)
        self.idari_kutu.hide()
        pl.addWidget(self.idari_kutu)
        pl.addStretch(1)

        self.b_pdf = QPushButton("PDF Kaydet (A3)")
        self.b_pdf.setObjectName("Ana")
        self.b_yaz = QPushButton("Yazdır…")
        self.b_resim = QPushButton("Resmi Kopyala")
        self.b_arsiv = QPushButton("Arşive Kaydet")
        self.b_arsiv.setObjectName("Lacivert")
        self.b_pdf.clicked.connect(self.pdf_kaydet)
        self.b_yaz.clicked.connect(self.yazdir)
        self.b_resim.clicked.connect(self.resim_kopyala)
        self.b_arsiv.clicked.connect(self.arsive_kaydet)
        pl.addWidget(self.b_pdf)
        sat = QHBoxLayout()
        sat.addWidget(self.b_yaz)
        sat.addWidget(self.b_resim)
        pl.addLayout(sat)
        pl.addWidget(self.b_arsiv)
        kok.addWidget(panel)

        # ------------------------------------------------ önizleme
        self.onizleme = QLabel()
        self.onizleme.setAlignment(Qt.AlignCenter)
        self.onizleme.setStyleSheet("background: transparent;")
        resim_menusu(self.onizleme, self._rapor_resmi)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(self.onizleme)
        sc.setStyleSheet("QScrollArea { background: #DDE1EA; border: 1px solid #D9DEE8; border-radius: 10px; }")
        self.sc = sc
        kok.addWidget(sc, 1)
        self._tur_degisti()

    # ------------------------------------------------ dönem
    def _donem(self):
        t = self.tur.currentIndex()
        if t == 0:
            d = pd(self.gun_sec.date())
            return d, d
        if t == 1:
            try:
                ilk = date.fromisocalendar(self.hafta_yil.value(), self.hafta.value(), 1)
            except ValueError:
                ilk = date.today()
            return ilk, ilk + timedelta(days=6)
        if t == 2:
            ilk = date(self.ay_yil.value(), self.ay.currentIndex() + 1, 1)
            return ilk, ay_sonu(ilk)
        a, b = pd(self.o_bas.date()), pd(self.o_bit.date())
        return (a, b) if a <= b else (b, a)

    def _oneri_baslik(self, ilk, son):
        t = self.tur.currentIndex()
        makine = self.b_makine.isChecked()
        son_ek = "PERFORMANS VE DURUŞ GRAFİKLERİ" if makine else ("VARDİYA BAZLI GRAFİKLERİ" if t == 0 else "VARDİYA GRAFİKLERİ")
        if self.b_idari.isChecked():
            if t == 0:
                return f"{ilk.day}.{ilk.month}.{ilk.year} GÜNLÜK OEE VE DURUŞ ÖZET RAPORU"
            if t == 1:
                return f"{ilk.isocalendar()[1]}. HAFTA OEE VE DURUŞ ÖZET RAPORU"
            if t == 2:
                return f"{tema.tr_buyuk(tema.AYLAR[ilk.month - 1])} {ilk.year} OEE VE DURUŞ ÖZET RAPORU"
            return f"{ilk:%d.%m.%Y} - {son:%d.%m.%Y} OEE VE DURUŞ ÖZET RAPORU"
        if t == 0:
            on = f"{ilk.day}.{ilk.month}.{ilk.year}"
        elif t == 1:
            on = f"{ilk.isocalendar()[1]}. HAFTA"
        elif t == 2:
            on = f"{tema.tr_buyuk(tema.AYLAR[ilk.month - 1])} {ilk.year}"
        else:
            on = f"{ilk:%d.%m.%Y} - {son:%d.%m.%Y}"
        return f"{on} CNC İŞLEME {son_ek}"

    def _tur_degisti(self):
        self.yigin.setCurrentIndex(self.tur.currentIndex())
        self._degisti()

    def _degisti(self, *_):
        ilk, son = self._donem()
        self.baslik.setText(self._oneri_baslik(ilk, son))
        self.gorsel_kutu.setVisible(self.b_makine.isChecked())
        self.idari_kutu.setVisible(self.b_idari.isChecked())
        self._yukle_gorsel()
        self._zamanla()

    def _zamanla(self):
        self._zamanlayici.start()

    # ------------------------------------------------ hesap ve önizleme
    def _rapor_hazirla(self) -> Optional[dict]:
        ilk, son = self._donem()
        kap = self.ana.kapsam()
        gunler = [ilk + timedelta(days=i) for i in range((son - ilk).days + 1)]
        self._gunler = [g for g in gunler if kap.get(g)]
        if not self._gunler:
            for v in VARDIYALAR:
                self.combolar[v].yenile("")
            return None
        kayit = vt.kayitlari_getir(self.ana.con, ilk, son)
        sonuc = hesapla(kayit, gunler, self.ana.hesap_ayar(), set(kap))
        seflar = vt.sef_getir(self.ana.con, self._gunler, self.ana.ayar)
        for v in VARDIYALAR:
            self.combolar[v].yenile(seflar.get(v, ""))
        donem = f"{ilk:%d.%m.%Y}" if ilk == son else f"{ilk:%d.%m.%Y} – {son:%d.%m.%Y}"
        duzen = "makine" if self.b_makine.isChecked() else ("idari" if self.b_idari.isChecked() else "vardiya")
        ek = {}
        cm = cormind_hesabi(kayit, self._gunler, self.ana.ayar["makineler"], self.ana.hesap_ayar())
        if duzen == "idari":
            ayar = self.ana.hesap_ayar()
            kotlar = vt.kot_getir(self.ana.con, ilk, son)
            icerik = idari_icerik(kotlar, cm, {m: v[0] for m, v in sonuc.makine_ort.items()})
            ozel = vt.metin_oku(self.ana.con, self._metin_anahtar(ilk, son))
            ek = dict(idari=icerik, idari_metin=ozel if ozel is not None else metne_cevir(icerik),
                      mola_pay=100.0 * ayar.mola_saat / ayar.net_saat)
            self.kot_durum.setText(
                (f"Bu dönemde {len(kotlar)} KOT kaydı, {sum(len(k.tezgahlar) for k in kotlar)} tezgâh açıklaması var."
                 if kotlar else "Bu dönem için KOT kaydı yok. Copilot'tan aldığınız KOT bloklarını yapıştırın.")
                + (" Metin elle düzenlenmiş." if ozel is not None else ""))
        return dict(
            baslik=self.baslik.text().strip() or self._oneri_baslik(ilk, son), donem=donem,
            duzen=duzen, sonuc=sonuc, makineler=self.ana.ayar["makineler"], **ek,
            seflar=seflar, gorsel=self._gorsel if self.b_makine.isChecked() else None,
            bos_goster=self.ana.ayar.get("idle_makineleri_goster", False), esik=self.ana.ayar["esik"],
            net_saat=self.ana.hesap_ayar().net_saat, yer_tutucu=True,
            alt_sag=f"Oluşturma: {datetime.now():%d.%m.%Y %H:%M}", ilk=ilk, son=son,
            cormind=cm)

    def yenile(self):
        self._varsayilan_tarihler()
        self._degisti()

    def _varsayilan_tarihler(self):
        """İlk açılışta tarihler son veri gününe ayarlanır (sonra kullanıcının seçimine dokunulmaz)."""
        if self._varsayilan_yapildi or not self.ana.kapsam():
            return
        self._varsayilan_yapildi = True
        ref = self.ana.son_veri_gunu()
        iso = ref.isocalendar()
        widgets = (self.gun_sec, self.o_bas, self.o_bit, self.hafta, self.hafta_yil, self.ay, self.ay_yil)
        for w in widgets:
            w.blockSignals(True)
        self.gun_sec.setDate(qd(ref))
        self.o_bas.setDate(qd(ref - timedelta(days=6)))
        self.o_bit.setDate(qd(ref))
        self.hafta.setValue(iso[1])
        self.hafta_yil.setValue(iso[0])
        self.ay.setCurrentIndex(ref.month - 1)
        self.ay_yil.setValue(ref.year)
        for w in widgets:
            w.blockSignals(False)

    def _yenile_simdi(self):
        self._r = self._rapor_hazirla()
        self._boya()

    def _boya(self):
        if not self._r:
            self.onizleme.setPixmap(QPixmap())
            self.onizleme.setText("Seçilen dönemde kayıt yok.\nBaşka bir gün ya da hafta seçin; veri yoksa önce Veri Aktar sayfasından yükleyin.")
            self.onizleme.setStyleSheet("background: transparent; color: #6B7285; font-size: 15px;")
            return
        self.onizleme.setStyleSheet("background: transparent;")
        genislik = max(600, self.sc.viewport().width() - 24)
        dpr = self.devicePixelRatioF()
        img = cizim.rapor_resmi(self._r, int(genislik * dpr))
        pm = QPixmap.fromImage(img)
        pm.setDevicePixelRatio(dpr)
        self.onizleme.setText("")
        self.onizleme.setPixmap(pm)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._r:
            self._zamanla()

    # ------------------------------------------------ idari rapor: KOT ve metin
    @staticmethod
    def _metin_anahtar(ilk, son) -> str:
        return f"idari|{ilk.isoformat()}|{son.isoformat()}"

    def kot_yapistir(self):
        d = MetinDialog(self, "KOT yapıştır",
                        "Copilot'tan aldığınız KOT bloklarını (=== KOT === ... === SON ===) buraya yapıştırın. Birden çok blok birlikte "
                        "yapıştırılabilir; aynı KOT NO ikinci kez sayılmaz, güncellenir. Kayıtlar kendi tarihine göre saklanır.",
                        QGuiApplication.clipboard().text() if "KOT" in (QGuiApplication.clipboard().text() or "") else "")
        if not d.exec():
            return
        kotlar = kot_coz(d.metin())
        if not kotlar:
            QMessageBox.information(self, "KOT yapıştır", "Metinde okunabilir bir KOT bloğu bulunamadı.\n"
                                    "Blok '=== KOT ===' satırıyla başlamalı ve 'TARIH: GG.AA.YYYY' içermelidir.")
            return
        yeni, guncel = vt.kot_yaz(self.ana.con, kotlar)
        gunler = sorted({k.tarih for k in kotlar})
        self.ana.mesaj(f"{len(kotlar)} KOT okundu: {yeni} yeni, {guncel} güncellendi · {gunler[0]:%d.%m.%Y} – {gunler[-1]:%d.%m.%Y} · "
                       f"{sum(len(k.tezgahlar) for k in kotlar)} tezgâh açıklaması")
        self._yenile_simdi()

    def metni_duzenle(self):
        r = self._hazir()
        if not r or r.get("duzen") != "idari":
            return
        d = MetinDialog(self, "Rapor metnini düzenle",
                        "Raporun ilk sayfasındaki metin. BÜYÜK HARFLE yazılan satır başlık, '-' ile başlayan satır madde olur. "
                        "Tablolar ve rakamlar program tarafından hesaplanır, buradan değişmez.",
                        r["idari_metin"], "Otomatik metne dön")
        if not d.exec():
            return
        vt.metin_yaz(self.ana.con, self._metin_anahtar(r["ilk"], r["son"]), None if d.ek else d.metin())
        self.ana.mesaj("Otomatik metne dönüldü." if d.ek else "Rapor metni kaydedildi.")
        self._yenile_simdi()

    def kot_sil(self):
        ilk, son = self._donem()
        if QMessageBox.question(self, "KOT kayıtlarını sil", f"{ilk:%d.%m.%Y} – {son:%d.%m.%Y} arasındaki KOT kayıtları silinsin mi?") != QMessageBox.Yes:
            return
        n = vt.kot_sil(self.ana.con, ilk, son)
        self.ana.mesaj(f"{n} KOT kaydı silindi.")
        self._yenile_simdi()

    # ------------------------------------------------ Cormind görüntüsü
    def _gorsel_anahtar(self) -> str:
        ilk, son = self._donem()
        return f"cormind|{ilk.isoformat()}|{son.isoformat()}"

    def _yukle_gorsel(self):
        self._anahtar = self._gorsel_anahtar()
        veri = vt.gorsel_oku(self.ana.con, self._anahtar)
        self._gorsel = QImage.fromData(veri) if veri else None
        self._gorsel_durum_yaz()

    def _gorsel_durum_yaz(self):
        if self._gorsel is not None and not self._gorsel.isNull():
            self.gorsel_durum.setText(f"Yapıştırdığınız görüntü kullanılıyor ({self._gorsel.width()}×{self._gorsel.height()} piksel). Programın çizdiğine dönmek için Kaldır'a basın.")
        else:
            self.gorsel_durum.setText("Program kendi çiziyor (Cormind hesabıyla). İsterseniz kendi görüntünüzü yapıştırabilirsiniz; o zaman o kullanılır.")
        self.b_kaldir.setEnabled(self._gorsel is not None)

    def _gorsel_ayarla(self, img: QImage):
        if img.isNull():
            QMessageBox.information(self, "Cormind görüntüsü", "Görüntü okunamadı.")
            return
        tampon = QBuffer()
        tampon.open(QIODevice.WriteOnly)
        img.save(tampon, "PNG")
        vt.gorsel_yaz(self.ana.con, self._anahtar, bytes(tampon.data()))
        self._gorsel = img
        self._gorsel_durum_yaz()
        self._zamanla()

    def _ctrl_v(self):
        if self.isVisible() and self.b_makine.isChecked() and not isinstance(QApplication.focusWidget(), QLineEdit):
            self.panodan_yapistir(sessiz=True)

    def panodan_yapistir(self, sessiz=False):
        img = QGuiApplication.clipboard().image()
        if img.isNull():
            if not sessiz:
                QMessageBox.information(self, "Panodan yapıştır", "Panoda resim yok. Cormind grafiğini kopyaladıktan sonra tekrar deneyin.")
            return
        self._gorsel_ayarla(img)

    def gorsel_dosya(self):
        yol, _ = QFileDialog.getOpenFileName(self, "Görüntü seç", "", "Resim (*.png *.jpg *.jpeg *.bmp)")
        if yol:
            self._gorsel_ayarla(QImage(yol))

    def gorsel_kaldir(self):
        vt.gorsel_sil(self.ana.con, self._anahtar)
        self._gorsel = None
        self._gorsel_durum_yaz()
        self._zamanla()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() or e.mimeData().hasImage():
            e.acceptProposedAction()

    def dropEvent(self, e):
        if not self.b_makine.isChecked():
            return
        if e.mimeData().hasUrls():
            for u in e.mimeData().urls():
                img = QImage(u.toLocalFile())
                if not img.isNull():
                    self._gorsel_ayarla(img)
                    return
        elif e.mimeData().hasImage():
            self._gorsel_ayarla(e.mimeData().imageData())

    # ------------------------------------------------ çıktılar
    def _hazir(self) -> Optional[dict]:
        if not self._r:
            self._r = self._rapor_hazirla()
        if not self._r:
            QMessageBox.information(self, "Rapor", "Seçilen dönemde kayıt yok.")
        return self._r

    def _dosya_adi(self, r):
        return re.sub(r'[\\/:*?"<>|]', "-", r["baslik"])

    def pdf_kaydet(self):
        r = self._hazir()
        if not r:
            return
        yol, _ = QFileDialog.getSaveFileName(self, "PDF olarak kaydet", self._dosya_adi(r) + ".pdf", "PDF (*.pdf)")
        if yol:
            pdf_yaz(yol, r)
            self.ana.mesaj(f"PDF kaydedildi: {yol}")

    def yazdir(self):
        r = self._hazir()
        if not r:
            return
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        yz = QPrinter(QPrinter.HighResolution)
        yz.setPageLayout(QPageLayout(QPageSize(QPageSize.A3), QPageLayout.Landscape, QMarginsF(0, 0, 0, 0)))
        yz.setDocName(r["baslik"])
        if QPrintDialog(yz, self).exec():
            p = QPainter(yz)
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setRenderHint(QPainter.SmoothPixmapTransform, True)
            r2 = dict(r, yer_tutucu=False)
            for i in range(cizim.sayfa_sayisi(r2)):
                if i:
                    yz.newPage()
                cizim.sayfa_ciz(p, QRectF(0, 0, yz.width(), yz.height()), r2, i)
            p.end()

    def _rapor_resmi(self):
        r = self._hazir()
        return cizim.rapor_resmi(dict(r, yer_tutucu=False), 2400) if r else None

    def resim_kopyala(self):
        r = self._hazir()
        if not r:
            return
        img = cizim.rapor_resmi(dict(r, yer_tutucu=False), 2400)
        QGuiApplication.clipboard().setImage(img)
        self.ana.mesaj("Rapor resim olarak panoya kopyalandı.")

    def arsive_kaydet(self):
        r = self._hazir()
        if not r:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            pdf = pdf_bayt(r)
            tur = f"{ {'makine': 'Makine bazlı', 'vardiya': 'Vardiya bazlı', 'idari': 'İdari rapor'}[r['duzen']] } · {TURLER[self.tur.currentIndex()]}"
            vt.arsiv_kaydet(self.ana.con, r["baslik"], tur, r["ilk"].isoformat(), r["son"].isoformat(),
                            json.dumps({"esik": r["esik"], "net_saat": r["net_saat"], "seflar": r["seflar"]}, ensure_ascii=False),
                            json.dumps(sonuc_ozeti(r["sonuc"]), ensure_ascii=False), pdf)
        finally:
            QApplication.restoreOverrideCursor()
        self.ana.mesaj("Rapor arşive kaydedildi (Geçmiş sayfasından tekrar açabilirsiniz).")
        self.ana.arsiv_degisti()
