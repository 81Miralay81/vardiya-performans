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
        # mola saatleri: şüpheli mola (mola saatinde moladan çıkıp çalışmaya geçen makine) yalnızca bu aralıklarda aranır
        from PySide6.QtCore import QRegularExpression
        from PySide6.QtGui import QRegularExpressionValidator
        from PySide6.QtWidgets import QGridLayout
        mw = QWidget()
        mg = QGridLayout(mw)
        mg.setContentsMargins(0, 0, 0, 0)
        mg.setHorizontalSpacing(8)
        for j, b in enumerate(("", "Çay başlangıç", "Çay bitiş", "Yemek başlangıç", "Yemek bitiş")):
            if b:
                mg.addWidget(etiket(b, "AltBaslik", kelime=False), 0, j)
        dogrula = QRegularExpressionValidator(QRegularExpression(r"^$|^([01]?\d|2[0-4]):[0-5]\d$"))
        self.mola_saat = {}
        for i, v in enumerate(VARDIYALAR):
            mg.addWidget(etiket(f"{v}. vardiya ({(v - 1) * 8:02d}–{v * 8:02d})", kelime=False), i + 1, 0)
            for j, anahtar in enumerate(("cay_bas", "cay_bit", "yemek_bas", "yemek_bit")):
                e = QLineEdit()
                e.setPlaceholderText("ss:dd")
                e.setValidator(dogrula)
                e.setMaximumWidth(90)
                e.setToolTip("Saat:dakika, ör. 12:40. O vardiyada bu mola yoksa boş bırakın.")
                self.mola_saat[(v, anahtar)] = e
                mg.addWidget(e, i + 1, j + 1)
        mg.setColumnStretch(5, 1)
        f.addRow("Mola saatleri (şüpheli mola için)", mw)
        self.sup_min = QDoubleSpinBox()
        self.sup_min.setRange(0, 30)
        self.sup_min.setDecimals(1)
        self.sup_min.setSingleStep(0.5)
        self.sup_min.setSuffix(" dk")
        self.sup_min.setMaximumWidth(150)
        self.sup_min.setButtonSymbols(QAbstractSpinBox.PlusMinus)
        self.sup_min.setToolTip("Alt sınır: makine çalışmaya geçmeden önce bundan kısa süre molada kaldıysa ya da mola saatindeki "
                                "çalışma bundan kısa sürdüyse şüpheli sayılmaz. Cormind'in mola saati gelince yazdığı birkaç saniyelik "
                                "otomatik mola kayıtlarını ve mola bitimine birkaç dakika kala başlayan çalışmaları ayıklar.")
        f.addRow("Şüpheli mola: alt sınır (mola ve çalışma)", self.sup_min)
        f.addRow("", etiket("Şüpheli mola: mola saati içinde makine moladan çıkıp çalışmaya geçerse (ör. duruştaki tezgahın mola saatinde "
                            "çalıştırılması) Performans'ta makinenin altında ⚠ çıkar. Mola saatinde zaten çalışıp çalışmaya devam eden "
                            "makine şüpheli sayılmaz. Makine alt sınırdan kısa molada kaldıysa ya da mola saatindeki çalışma alt sınırdan kısa sürdüyse de sayılmaz. "
                            "Saatleri yazıp Kaydet'e basın.", "AltBaslik"))
        for w in (self.esik, self.vardiya_dk, self.yemek_dk, self.cay_dk):
            w.setMaximumWidth(150)
            w.setButtonSymbols(QAbstractSpinBox.PlusMinus)
        for w in (self.vardiya_dk, self.yemek_dk, self.cay_dk):
            w.valueChanged.connect(self._net_yaz)
        k.layout().addLayout(f)
        self.gizle = QCheckBox("Çalışmayan makineleri grafiklerde ve raporlarda gösterme")
        self.gizle.setToolTip("İşaretli: seçili dönemde hiç çalışmayan makineler (çalışma payı %1'in altında, ör. tamamı İŞ EMRİ PLAN YOK, "
                              "ya da hiç kaydı olmayan) Performans, Çalışma sayfası ve makine raporu grafiklerinde çıkmaz.\n"
                              "İşaretsiz: Ayarlar'daki makine listesinin tamamı görünür; kaydı olmayan makine boş sütun olur.\n"
                              "Cormind rapor sistemi bu seçenekten etkilenmez.")
        k.layout().addWidget(self.gizle)
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

        # ------------------------------------------------ tarayıcıdan erişim (bu bilgisayara özel)

        from . import web_sunucu
        ws = QHBoxLayout()
        self.web_acik = QCheckBox("Tarayıcıdan erişim (bu bilgisayar sunucu olur)")
        self.web_acik.setChecked(web_sunucu.etkin() is not None or web_sunucu.ayarda_acik())
        self.web_port = QSpinBox()
        self.web_port.setRange(1024, 65535)
        self.web_port.setValue(web_sunucu.ayar_port())
        self.web_port.setPrefix("Port: ")
        self.web_not = QLabel()
        self.web_not.setObjectName("AltBaslik")
        self.web_not.setTextInteractionFlags(Qt.TextSelectableByMouse)

        def _web_yaz():
            s = web_sunucu.etkin()
            if s:
                self.web_not.setText(f"Açık · diğer bilgisayarlar: {s.adres()}   ·   bu bilgisayar: http://localhost:{s.port}")
            elif self.web_acik.isChecked():
                self.web_not.setText(f"Port {self.web_port.value()} kullanımda, sunucu başlatılamadı. Başka bir port seçin.")
            else:
                self.web_not.setText("Kapalı. Açınca iç ağdaki bilgisayarlar programı tarayıcıdan açabilir.")

        def _web_degisti(*_):
            s = QSettings("Teknorot", "VardiyaPerformans")
            s.setValue("web/acik", "1" if self.web_acik.isChecked() else "0")
            s.setValue("web/port", self.web_port.value())
            s.sync()
            web_sunucu.durdur()
            if self.web_acik.isChecked():
                web_sunucu.baslat(self.ana.db_yolu, self.web_port.value(), self.ana.veri_yenilendi)
            _web_yaz()

        self.web_acik.toggled.connect(_web_degisti)
        self.web_port.editingFinished.connect(lambda: self.web_acik.isChecked() and _web_degisti())
        ws.addWidget(self.web_acik)
        ws.addWidget(self.web_port)
        ws.addWidget(self.web_not, 1)
        kd.layout().addLayout(ws)
        _web_yaz()

        # ------------------------------------------------ otomatik Cormind çekimi (bu bilgisayara özel)
        from . import oto_cekim
        os_ = QHBoxLayout()
        self.oto_acik = QCheckBox("Cormind'den otomatik çek (bu bilgisayar)")
        self.oto_acik.setToolTip("Program açılınca ve açık kaldıysa her gece 01:00'de, son tam çekilen günden düne kadar eksik "
                                 "günler Cormind'den çekilir. Bugün hiçbir zaman otomatik çekilmez (tabloda yarım gün olmasın). "
                                 "Yalnızca bu kutunun işaretli olduğu bilgisayar çeker.")
        self.oto_acik.setChecked(oto_cekim.ayarda_acik())
        self.oto_not = QLabel("Kapalı")
        self.oto_not.setObjectName("AltBaslik")
        self.oto_not.setWordWrap(True)

        def _oto_degisti(acik):
            s = QSettings("Teknorot", "VardiyaPerformans")
            s.setValue("oto/acik", "1" if acik else "0")
            s.sync()
            if getattr(self, "_oto", None) is not None:
                self._oto.ayarla()
        self.oto_acik.toggled.connect(_oto_degisti)
        os_.addWidget(self.oto_acik)
        os_.addWidget(self.oto_not, 1)
        kd.layout().addLayout(os_)

        # ------------------------------------------------ açık programlar: güncelleme öncesi herkesi kapat (yalnızca exe)
        ks_ = QHBoxLayout()
        self.b_hepsini_kapat = QPushButton("Tüm açık programları kapat")
        self.b_hepsini_kapat.setObjectName("Lacivert")
        self.b_hepsini_kapat.setToolTip("Güncelleme öncesi: bu program diğer bütün bilgisayarlarda 60 saniyelik uyarıyla kapanır. "
                                        "Bu bilgisayardaki program kapanmaz.")
        self.b_hepsini_kapat.clicked.connect(self._hepsini_kapat)
        b_yen = QPushButton("Yenile")
        b_yen.setToolTip("Açık programlar listesini yenile")
        b_yen.clicked.connect(self._acik_yaz)
        self.acik_not = QLabel("")
        self.acik_not.setObjectName("AltBaslik")
        self.acik_not.setWordWrap(True)
        ks_.addWidget(self.b_hepsini_kapat)
        ks_.addWidget(b_yen)
        ks_.addWidget(self.acik_not, 1)
        kd.layout().addLayout(ks_)

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
        self.personel_bilgi.setText(f"{len(adlar)} kişi · {len(haric & set(adlar))} kişi hariç tutuluyor"
                                    + ("" if vt.sozluk_hazir(self.ana.con) else
                                       " · liste hazırlanıyor (eski kayıtlar taranıyor), birazdan tamamlanır…"))

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
        gorunen = {self.op_turler.item(i).text() for i in range(self.op_turler.count())}
        haric = sorted((set(self.ana.ayar.get("op_durus_haric") or []) - gorunen)      # listede (henüz) olmayanlar korunur
                       | {self.op_turler.item(i).text() for i in range(self.op_turler.count())
                          if self.op_turler.item(i).checkState() == Qt.Unchecked})
        vt.ayar_yaz(self.ana.con, "op_durus_haric", haric)
        self.ana.ayar = vt.ayar_oku(self.ana.con)

    def _personel_degisti(self, _it):
        from . import veritabani as vt
        gorunen = {self.personel.item(i).text() for i in range(self.personel.count())}
        haric = sorted((vt.haric_personel(self.ana.con) - gorunen)                     # listede (henüz) olmayanlar korunur
                       | {self.personel.item(i).text() for i in range(self.personel.count())
                          if self.personel.item(i).checkState() == Qt.Unchecked})
        vt.ayar_yaz(self.ana.con, "haric_personel", haric)
        self.ana.ayar = vt.ayar_oku(self.ana.con)
        self.personel_bilgi.setText(f"{self.personel.count()} kişi · {len(haric)} kişi hariç tutuluyor")

    def _acik_liste(self):
        from .oturum import acik_programlar
        kendi = getattr(getattr(self.ana, "oturum", None), "kimlik", None)
        try:
            return [x for x in acik_programlar(self.ana.con) if x["kimlik"] != kendi]
        except Exception:  # noqa: BLE001
            return []

    def _acik_yaz(self):
        l = self._acik_liste()
        if not l:
            self.acik_not.setText("Şu an başka bilgisayarda açık program görünmüyor (liste yarım dakikada bir güncellenir).")
        else:
            self.acik_not.setText(f"Başka bilgisayarlarda açık: {len(l)} · "
                                  + ", ".join(f"{x['pc']}{' (' + x['kullanici'] + ')' if x['kullanici'] else ''} · {x['surum']}" for x in l))

    def _hepsini_kapat(self):
        from PySide6.QtWidgets import QMessageBox
        from .oturum import GERI_SAYIM_SN, kapat_iste
        l = self._acik_liste()
        ad = ", ".join(x["pc"] for x in l) if l else "şu an görünen yok"
        if QMessageBox.question(self, "Tüm açık programları kapat",
                                f"Vardiya Performans diğer bütün bilgisayarlarda {GERI_SAYIM_SN} saniyelik uyarıyla kapanacak "
                                f"(açık: {ad}). Bu bilgisayardaki program kapanmaz.\n\nDevam edilsin mi?") != QMessageBox.Yes:
            return
        kapat_iste(self.ana.con, getattr(getattr(self.ana, "oturum", None), "kimlik", ""))
        self.acik_not.setText(f"Kapatma isteği gönderildi. Açık programlar yarım dakika içinde isteği görüp {GERI_SAYIM_SN} sn sonra "
                              "kapanır; yaklaşık 1,5 dakika sonra exe'yi değiştirebilirsiniz. 'Yenile' ile kontrol edin.")

    def showEvent(self, e):
        super().showEvent(e)
        self._acik_yaz()
        if getattr(self, "_listeler_kirli", True):     # personel ve duruş türü listeleri yalnızca sayfa açılınca okunur
            self._listeler_kirli = False
            self._personel_doldur()
            self._op_tur_doldur()
            self._sozluk_bekle()

    def oto_bagla(self, oto):
        self._oto = oto
        self.oto_not.setText(oto.durum)
        oto.durum_degisti.connect(self.oto_not.setText)

    def _sozluk_bekle(self):
        """Ad sözlüğü arka planda hazırlanıyorsa listeleri birkaç saniyede bir tazeler (sayfa hiç donmaz)."""
        from PySide6.QtCore import QTimer
        if vt.sozluk_hazir(self.ana.con) or getattr(self, "_sozluk_zamanlayici", None):
            return
        vt.sozluk_arkada_doldur(self.ana.db_yolu)

        def _tik():
            hazir = vt.sozluk_hazir(self.ana.con)
            if self.isVisible():
                self._personel_doldur()
                self._op_tur_doldur()
            else:
                self._listeler_kirli = True
            if hazir:
                self._sozluk_zamanlayici.stop()
                self._sozluk_zamanlayici = None
            else:
                vt.sozluk_arkada_doldur(self.ana.db_yolu)   # yarıda kaldıysa kaldığı yerden sürdür
        self._sozluk_zamanlayici = QTimer(self)
        self._sozluk_zamanlayici.timeout.connect(_tik)
        self._sozluk_zamanlayici.start(4000)

    def yenile(self):
        self._listeler_kirli = True
        if self.isVisible():
            self._listeler_kirli = False
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
        from .kirilim import VARSAYILAN_EN_KISA_MOLA_DK
        self.sup_min.setValue(float(a.get("supheli_en_kisa_mola_dk", VARSAYILAN_EN_KISA_MOLA_DK)))
        ms = a.get("mola_saatleri") or {}
        for (v, anahtar), e in self.mola_saat.items():
            tur, uc = anahtar.split("_")
            ab = (ms.get(str(v)) or {}).get(tur) or ["", ""]
            e.setText(ab[0] if uc == "bas" else ab[1])
        self.gizle.setChecked(bool(a.get("calismayanlari_gizle", True)))
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
        ms = {}
        for v in VARDIYALAR:
            for tur in ("cay", "yemek"):
                b, s = self.mola_saat[(v, tur + "_bas")].text().strip(), self.mola_saat[(v, tur + "_bit")].text().strip()
                if b and s:
                    ms.setdefault(str(v), {})[tur] = [b, s]
        vt.ayar_yaz(con, "mola_saatleri", ms)
        vt.ayar_yaz(con, "supheli_en_kisa_mola_dk", self.sup_min.value())
        vt.ayar_yaz(con, "calismayanlari_gizle", self.gizle.isChecked())
        vt.ayar_yaz(con, "makineler", self._adlar(self.mak_liste))
        vt.ayar_yaz(con, "sefler", self._adlar(self.sef_liste))
        vt.ayar_yaz(con, "vardiya_sef", {str(v): c.currentText() for v, c in self.varsayilan.items()})
        self.ana.ayar_degisti()
        self.ana.mesaj("Ayarlar kaydedildi, hesaplar yenilendi.")
