"""Ayarlar sayfası: eşik, süreler, makine listesi, grup liderleri."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QPushButton, QScrollArea, QSpinBox, QVBoxLayout,
                               QWidget)

from . import tema, veritabani as vt
from .hesap import HesapAyar, VARDIYALAR
from .sayfa_ortak import etiket, kart


def _liste_duzenleyici(baslik: str, aciklama: str, duzenlenebilir=True):
    k = kart()
    k.layout().addWidget(etiket(baslik, "KartBaslik"))
    if aciklama:
        k.layout().addWidget(etiket(aciklama, "AltBaslik"))
    lst = QListWidget()
    lst.setMinimumHeight(180)
    k.layout().addWidget(lst)
    return k, lst


class AyarSayfasi(QWidget):
    def __init__(self, ana):
        super().__init__()
        self.ana = ana
        dis = QVBoxLayout(self)
        dis.setContentsMargins(26, 22, 26, 22)
        dis.setSpacing(12)
        ust = QHBoxLayout()
        sol = QVBoxLayout()
        sol.addWidget(etiket("Ayarlar", "Baslik"))
        sol.addWidget(etiket("Değişiklikler 'Kaydet' deyince geçerli olur; tüm hesaplar yeni ayarla yenilenir.", "AltBaslik"))
        ust.addLayout(sol, 1)
        self.b_kaydet = QPushButton("Kaydet")
        self.b_kaydet.setObjectName("Ana")
        self.b_kaydet.setMinimumWidth(140)
        self.b_kaydet.clicked.connect(self.kaydet)
        ust.addWidget(self.b_kaydet, 0, Qt.AlignTop)
        dis.addLayout(ust)

        sc = QScrollArea()
        sc.setWidgetResizable(True)
        icerik = QWidget()
        ic = QVBoxLayout(icerik)
        ic.setContentsMargins(0, 0, 8, 0)
        ic.setSpacing(12)
        sc.setWidget(icerik)
        dis.addWidget(sc, 1)

        # ------------------------------------------------ hesap kuralları
        k = kart()
        k.layout().addWidget(etiket("HESAP KURALLARI", "KartBaslik"))
        f = QFormLayout()
        f.setLabelAlignment(Qt.AlignLeft)
        self.esik = QDoubleSpinBox()
        self.esik.setRange(0, 100)
        self.esik.setDecimals(0)
        self.esik.setSuffix(" %")
        self.esik.setToolTip("Bir makine, o gün o vardiyada bu orana ulaşmadıysa sayılmaz")
        self.vardiya_dk = QSpinBox()
        self.vardiya_dk.setRange(60, 1440)
        self.vardiya_dk.setSuffix(" dk")
        self.yemek_dk = QSpinBox()
        self.yemek_dk.setRange(0, 240)
        self.yemek_dk.setSuffix(" dk")
        self.cay_dk = QSpinBox()
        self.cay_dk.setRange(0, 240)
        self.cay_dk.setSuffix(" dk")
        self.net = QLabel("")
        self.net.setObjectName("AltBaslik")
        self.kural = QComboBox()
        for anahtar, ad in tema.KURALLAR:
            self.kural.addItem(ad, anahtar)
        self.kural_aciklama = etiket("", "AltBaslik")
        self.kural.currentIndexChanged.connect(lambda _=0: self.kural_aciklama.setText(tema.KURAL_ACIKLAMA[self.kural.currentData()]))
        self.kural.setParent(self); self.kural.hide()
        self.kural_aciklama.setParent(self); self.kural_aciklama.hide()
        self.yontem = QComboBox()
        for anahtar, ad in tema.YONTEMLER:
            self.yontem.addItem(ad, anahtar)
        self.yontem_aciklama = etiket("", "AltBaslik")
        self.yontem.setParent(self); self.yontem.hide()
        self.yontem_aciklama.setText("Hesap yöntemi, üstteki dönem çubuğundan seçilir (Performans, Çalışma, Genel Duruş ve Mola sayfalarında görünür).")
        f.addRow("Hesap yöntemi", self.yontem_aciklama)
        f.addRow("Eşik (makine sayılması için en az)", self.esik)
        f.addRow("Vardiya uzunluğu", self.vardiya_dk)
        f.addRow("Yemek molası (her vardiyada 1 kez)", self.yemek_dk)
        f.addRow("Çay molası", self.cay_dk)
        f.addRow("Net çalışma süresi", self.net)
        for w in (self.esik, self.vardiya_dk, self.yemek_dk, self.cay_dk):
            w.setMaximumWidth(150)
            w.setButtonSymbols(QAbstractSpinBox.PlusMinus)
        for w in (self.vardiya_dk, self.yemek_dk, self.cay_dk):
            w.valueChanged.connect(self._net_yaz)
        k.layout().addLayout(f)
        self.idle = QCheckBox("Çalışmayan makineleri de makine grafiğinde göster")
        k.layout().addWidget(self.idle)
        ic.addWidget(k)

        # ------------------------------------------------ makineler + şefler
        satir = QHBoxLayout()
        satir.setSpacing(12)
        km, self.mak_liste = _liste_duzenleyici("MAKİNELER", "Tabloda bu sırayla görünür. Veride yeni bir makine çıkarsa otomatik eklenir.")
        self.mak_ekle = QLineEdit()
        self.mak_ekle.setPlaceholderText("Yeni makine adı (örn. IM90)")
        self.mak_ekle.returnPressed.connect(self._mak_ekle)
        km.layout().addWidget(self.mak_ekle)
        s1 = QHBoxLayout()
        for ad, fn in (("Ekle", self._mak_ekle), ("Sil", lambda: self._sil(self.mak_liste)), ("Yukarı", lambda: self._tasi(self.mak_liste, -1)),
                       ("Aşağı", lambda: self._tasi(self.mak_liste, 1))):
            b = QPushButton(ad)
            b.clicked.connect(fn)
            s1.addWidget(b)
        km.layout().addLayout(s1)
        satir.addWidget(km, 1)

        ks, self.sef_liste = _liste_duzenleyici("GRUP LİDERLERİ", "Adı değiştirmek için çift tıklayın. Raporlarda ve vardiya kutularında bu liste çıkar.")
        self.sef_liste.itemDoubleClicked.connect(self._sef_adlandir)
        self.sef_ekle = QLineEdit()
        self.sef_ekle.setPlaceholderText("Yeni grup lideri adı")
        self.sef_ekle.returnPressed.connect(self._sef_ekle)
        ks.layout().addWidget(self.sef_ekle)
        s2 = QHBoxLayout()
        for ad, fn in (("Ekle", self._sef_ekle), ("Sil", lambda: self._sil(self.sef_liste))):
            b = QPushButton(ad)
            b.clicked.connect(fn)
            s2.addWidget(b)
        ks.layout().addLayout(s2)
        ks.layout().addWidget(etiket("VARSAYILAN VARDİYA LİDERLERİ", "KartBaslik"))
        ff = QFormLayout()
        self.varsayilan = {}
        for v in VARDIYALAR:
            c = QComboBox()
            self.varsayilan[v] = c
            ff.addRow(f"{v}. Vardiya", c)
        ks.layout().addLayout(ff)
        ks.layout().addWidget(etiket("Belirli günlerde farklı kişi için Performans / Raporlar sayfasındaki vardiya kutusundan seçin.", "AltBaslik"))
        satir.addWidget(ks, 1)
        ic.addLayout(satir)

        # ------------------------------------------------ veri tabanı
        kd = kart()
        kd.layout().addWidget(etiket("VERİ TABANI", "KartBaslik"))
        self.db_yolu = etiket("", "AltBaslik")
        self.db_yolu.setTextInteractionFlags(Qt.TextSelectableByMouse)
        kd.layout().addWidget(self.db_yolu)
        b = QPushButton("Klasörü Aç")
        b.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self.ana.db_yolu))))
        bt = QPushButton("Teşhis (açılış kaydı, sunucu ölçümü)…")
        bt.setToolTip("Program geç açılıyor ya da donuyorsa: açılışın hangi adımda beklediğini ve sunucudan okuma hızını gösterir.")

        def _teshis():
            from .teshis_pencere import TeshisPenceresi
            TeshisPenceresi(self).exec()

        bt.clicked.connect(_teshis)
        bs = QHBoxLayout()
        bs.addWidget(b)
        bs.addWidget(bt)
        bs.addStretch(1)
        kd.layout().addLayout(bs)
        from PySide6.QtCore import QSettings
        gs = QHBoxLayout()
        gs.addWidget(QLabel("Grafik görünümü"))
        self.grafik = QComboBox()
        self.grafik.addItem("3B, hareketli (web grafik motoru)", "1")
        self.grafik.addItem("Sade, hızlı (programın kendi çizimi)", "0")
        ayarlar = QSettings("Teknorot", "VardiyaPerformans")
        self.grafik.setCurrentIndex(0 if str(ayarlar.value("grafik/web", "1")) != "0" else 1)

        def _grafik(_i):
            s = QSettings("Teknorot", "VardiyaPerformans")
            s.setValue("grafik/web", self.grafik.currentData())
            s.sync()
            from . import web
            simdi = web.WEB_VAR
            istenen = self.grafik.currentData() != "0"
            self.b_yeniden.setVisible(simdi != istenen)
            self.grafik_not.setText("Değişiklik için programı yeniden başlatın." if simdi != istenen
                                    else "Raporlar ve hesaplar iki görünümde de aynıdır.")

        def _yeniden_baslat():
            import sys
            from PySide6.QtCore import QProcess
            from PySide6.QtWidgets import QApplication as _App
            if getattr(sys, "frozen", False):
                QProcess.startDetached(sys.executable, sys.argv[1:])
            else:
                QProcess.startDetached(sys.executable, sys.argv)
            _App.quit()

        self.grafik.activated.connect(_grafik)
        gs.addWidget(self.grafik)
        self.b_yeniden = QPushButton("Programı yeniden başlat")
        self.b_yeniden.setObjectName("Ana")
        self.b_yeniden.clicked.connect(_yeniden_baslat)
        self.b_yeniden.hide()
        gs.addWidget(self.b_yeniden)
        from . import web as _web
        self.grafik_not = QLabel(("Şu an: 3B web grafik açık. " if _web.WEB_VAR else "Şu an: sade grafik açık. ")
                                 + "Raporlar ve hesaplar iki görünümde de aynıdır.")
        self.grafik_not.setObjectName("AltBaslik")
        gs.addWidget(self.grafik_not, 1)
        kd.layout().addLayout(gs)

        # ------------------------------------------------ personel listesi
        from PySide6.QtWidgets import QListWidget, QListWidgetItem
        kp = kart()
        kp.layout().addWidget(etiket("PERSONEL LİSTESİ", "KartBaslik"))
        kp.layout().addWidget(etiket("Kayıtlarda geçen tüm personel. İşaretini kaldırdığın kişiler Operatör sekmesine ve "
                                     "Performans'taki 'operatör varken duran makineler' listesine girmez (ör. grup lideri, ayarcı).",
                                     "AltBaslik"))
        self.personel = QListWidget()
        self.personel.setMinimumHeight(220)
        self.personel.setStyleSheet("QListWidget::item { padding: 3px; }")
        self.personel.itemChanged.connect(self._personel_degisti)
        kp.layout().addWidget(self.personel)
        self.personel_bilgi = etiket("", "AltBaslik")
        kp.layout().addWidget(self.personel_bilgi)
        self._QListWidgetItem = QListWidgetItem
        kp.layout().addWidget(etiket("OPERATÖR VARKEN DURAN MAKİNELER: GÖSTERİLECEK DURUŞ TÜRLERİ", "KartBaslik"))
        kp.layout().addWidget(etiket("Operatör sekmesindeki bu listede yalnızca işaretli duruş türleri sayılır ve gösterilir.",
                                     "AltBaslik"))
        self.op_turler = QListWidget()
        self.op_turler.setMinimumHeight(200)
        self.op_turler.setStyleSheet("QListWidget::item { padding: 3px; }")
        self.op_turler.itemChanged.connect(self._op_tur_degisti)
        kp.layout().addWidget(self.op_turler)
        ic.addWidget(kp)
        ic.addWidget(kd)

        # ------------------------------------------------ Outlook ve yapay zekâ (idari rapor)
        from PySide6.QtWidgets import QFormLayout as _QF, QLineEdit as _QL
        from . import yapay
        ky = kart()
        ky.layout().addWidget(etiket("OUTLOOK VE YAPAY ZEKÂ (İDARİ RAPOR)", "KartBaslik"))
        ky.layout().addWidget(etiket(
            "İdari raporda 'Outlook'tan Al' düğmesi, aşağıdaki gönderen ve konuya uyan mailleri Outlook'tan okur. Anahtar girilmişse mail "
            "metinleri (imza ve kişi adları çıkarılarak) Google Gemini'ye gönderilip KOT formuna döktürülür; anahtar yoksa ya da servise "
            "ulaşılamazsa program kendi algoritmasıyla ayırır. Bu ayarlar yalnızca bu bilgisayarda saklanır.", "AltBaslik"))
        fy = _QF()
        self.y_gonderen, self.y_konu, self.y_anahtar, self.y_model, self.y_alicilar = _QL(), _QL(), _QL(), _QL(), _QL()
        self.y_alicilar.setPlaceholderText("ad@sirket.com; ad2@sirket.com  (noktalı virgülle ayırın)")
        self.y_anahtar.setEchoMode(_QL.Password)
        self.y_anahtar.setPlaceholderText("Gemini API anahtarı (boş bırakılırsa yapay zekâ kullanılmaz)")
        fy.addRow("Mail göndereni", self.y_gonderen)
        fy.addRow("Mail konusunda geçen", self.y_konu)
        fy.addRow("Gemini anahtarı", self.y_anahtar)
        fy.addRow("Model adı", self.y_model)
        fy.addRow("İdari rapor alıcıları", self.y_alicilar)
        ky.layout().addLayout(fy)
        ys = QHBoxLayout()
        by, bd = QPushButton("Bu Ayarları Kaydet"), QPushButton("Bağlantıyı Dene")
        self.y_durum = etiket("", "AltBaslik")
        ys.addWidget(by)
        ys.addWidget(bd)
        ys.addWidget(self.y_durum, 1)
        ky.layout().addLayout(ys)
        ya = yapay.ayar_oku()
        self.y_gonderen.setText(ya["gonderen"]); self.y_konu.setText(ya["konu"]); self.y_anahtar.setText(ya["anahtar"]); self.y_model.setText(ya["model"]); self.y_alicilar.setText(ya["alicilar"])

        def _y_kaydet():
            yapay.ayar_yaz(self.y_anahtar.text(), self.y_model.text(), self.y_gonderen.text(), self.y_konu.text(), self.y_alicilar.text())
            self.y_durum.setText("Kaydedildi.")

        def _y_dene():
            _y_kaydet()
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                yanit = yapay.sor(self.y_anahtar.text().strip(), "Yalnızca TAMAM yaz.", self.y_model.text().strip(), 30)
                self.y_durum.setText("Bağlantı çalışıyor. Yanıt: " + yanit.strip()[:40])
            except RuntimeError as ex:
                self.y_durum.setText(str(ex))
            finally:
                QApplication.restoreOverrideCursor()

        by.clicked.connect(_y_kaydet)
        bd.clicked.connect(_y_dene)
        ic.addWidget(ky)
        ic.addStretch(1)
        self.yenile()

    # ------------------------------------------------ liste işlemleri
    @staticmethod
    def _ekle(liste: QListWidget, metin: str, duzenlenebilir=False):
        o = QListWidgetItem(metin)
        liste.addItem(o)

    def _mak_ekle(self):
        ad = self.mak_ekle.text().strip().upper()
        if ad and ad not in self._adlar(self.mak_liste):
            self._ekle(self.mak_liste, ad)
        self.mak_ekle.clear()

    def _sef_ekle(self):
        ad = self.sef_ekle.text().strip()
        if ad and ad not in self._adlar(self.sef_liste):
            self._ekle(self.sef_liste, ad)
            self._varsayilan_doldur()
        self.sef_ekle.clear()

    def _sef_adlandir(self, oge):
        yeni, ok = QInputDialog.getText(self, "Grup lideri adı", "Yeni ad:", text=oge.text())
        if ok and yeni.strip():
            oge.setText(yeni.strip())
            self._varsayilan_doldur()

    def _sil(self, liste):
        for o in liste.selectedItems():
            liste.takeItem(liste.row(o))
        self._varsayilan_doldur()

    @staticmethod
    def _tasi(liste, yon):
        r = liste.currentRow()
        y = r + yon
        if r < 0 or not 0 <= y < liste.count():
            return
        o = liste.takeItem(r)
        liste.insertItem(y, o)
        liste.setCurrentRow(y)

    @staticmethod
    def _adlar(liste):
        return [liste.item(i).text() for i in range(liste.count())]

    def _varsayilan_doldur(self, secili=None):
        adlar = self._adlar(self.sef_liste)
        for v, c in self.varsayilan.items():
            onceki = (secili or {}).get(v, c.currentText())
            c.clear()
            c.addItems(adlar)
            if onceki in adlar:
                c.setCurrentText(onceki)

    def _net_yaz(self):
        a = HesapAyar(vardiya_dk=self.vardiya_dk.value(), yemek_dk=self.yemek_dk.value(), cay_dk=self.cay_dk.value())
        self.net.setText(f"{tema.sayi(a.net_saat, 2)} saat   ·   mola kapasitesi {self.yemek_dk.value() + self.cay_dk.value()} dk")

    # ------------------------------------------------ oku / yaz
    def _personel_doldur(self):
        from . import veritabani as vt
        haric = vt.haric_personel(self.ana.con)
        self.personel.blockSignals(True)
        self.personel.clear()
        adlar = vt.personel_listesi(self.ana.con)
        for ad in adlar:
            it = self._QListWidgetItem(ad)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked if ad in haric else Qt.Checked)
            self.personel.addItem(it)
        self.personel.blockSignals(False)
        self.personel_bilgi.setText(f"{len(adlar)} kişi · {len(haric & set(adlar))} kişi hariç tutuluyor")

    def _op_tur_doldur(self):
        from .operatorlu_durus import durus_turleri
        haric = set(self.ana.ayar.get("op_durus_haric") or [])
        self.op_turler.blockSignals(True)
        self.op_turler.clear()
        for ad in durus_turleri(self.ana.con):
            it = self._QListWidgetItem(ad)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked if ad in haric else Qt.Checked)
            self.op_turler.addItem(it)
        self.op_turler.blockSignals(False)

    def _op_tur_degisti(self, _it):
        haric = sorted(self.op_turler.item(i).text() for i in range(self.op_turler.count())
                       if self.op_turler.item(i).checkState() == Qt.Unchecked)
        vt.ayar_yaz(self.ana.con, "op_durus_haric", haric)
        self.ana.ayar = vt.ayar_oku(self.ana.con)

    def _personel_degisti(self, _it):
        from . import veritabani as vt
        haric = sorted(self.personel.item(i).text() for i in range(self.personel.count())
                       if self.personel.item(i).checkState() == Qt.Unchecked)
        vt.ayar_yaz(self.ana.con, "haric_personel", haric)
        self.ana.ayar = vt.ayar_oku(self.ana.con)
        self.personel_bilgi.setText(f"{self.personel.count()} kişi · {len(haric)} kişi hariç tutuluyor")

    def yenile(self):
        self._personel_doldur()
        self._op_tur_doldur()
        a = self.ana.ayar
        self.esik.setValue(round(a["esik"] * 100))
        self.kural.setCurrentIndex(max(0, self.kural.findData(a.get("hesap_kurali", "gunluk"))))
        self.kural_aciklama.setText(tema.KURAL_ACIKLAMA[self.kural.currentData()])
        self.yontem.setCurrentIndex(max(0, self.yontem.findData(a.get("hesap_yontemi", "vardiya"))))
        self.yontem.currentIndexChanged.emit(self.yontem.currentIndex())
        self.vardiya_dk.setValue(a["vardiya_dk"])
        self.yemek_dk.setValue(a["yemek_dk"])
        self.cay_dk.setValue(a["cay_dk"])
        self.idle.setChecked(bool(a.get("idle_makineleri_goster")))
        self.mak_liste.clear()
        for m in a["makineler"]:
            self._ekle(self.mak_liste, m)
        self.sef_liste.clear()
        for s in a["sefler"]:
            self._ekle(self.sef_liste, s)
        self._varsayilan_doldur({v: a["vardiya_sef"].get(str(v), "") for v in VARDIYALAR})
        self.db_yolu.setText(self.ana.db_yolu)
        self._net_yaz()

    def kaydet(self):
        con = self.ana.con
        vt.ayar_yaz(con, "esik", self.esik.value() / 100.0)
        vt.ayar_yaz(con, "vardiya_dk", self.vardiya_dk.value())
        vt.ayar_yaz(con, "yemek_dk", self.yemek_dk.value())
        vt.ayar_yaz(con, "cay_dk", self.cay_dk.value())
        vt.ayar_yaz(con, "idle_makineleri_goster", self.idle.isChecked())
        vt.ayar_yaz(con, "makineler", self._adlar(self.mak_liste))
        vt.ayar_yaz(con, "sefler", self._adlar(self.sef_liste))
        vt.ayar_yaz(con, "vardiya_sef", {str(v): c.currentText() for v, c in self.varsayilan.items()})
        self.ana.ayar_degisti()
        self.ana.mesaj("Ayarlar kaydedildi, hesaplar yenilendi.")
