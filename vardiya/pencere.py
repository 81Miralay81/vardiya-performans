"""Ana pencere: sol menü + sayfalar + üstte dönem çubuğu."""
from __future__ import annotations

import os
from datetime import date, timedelta
from typing import List, Optional

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from . import tema, teshis, veritabani as vt
from .donem import DonemCubugu
from .hesap import HesapAyar, hesapla
from .sayfa_analiz import AnalizSayfasi
from .sayfa_ayar import AyarSayfasi
from .sayfa_gecmis import GecmisSayfasi
from .sayfa_kayitlar import KayitlarSayfasi
from .sayfa_operator import OperatorSayfasi
from .sayfa_performans import PerformansSayfasi
from .sayfa_rapor import RaporSayfasi
from .sayfa_veri import VeriSayfasi
from .surum import SURUM
from . import guncelleme

MENU = (("veri", "Veri Aktar"), ("kayitlar", "Kayıtlar"), ("performans", "Performans"), ("calisma", "Çalışma"), ("durus", "Genel Duruş"), ("mola", "Mola"),
        ("operator", "Operatör"), ("rapor", "Raporlar"), ("gecmis", "Geçmiş"), ("ayar", "Ayarlar"))
DONEMLI = {"performans", "calisma", "durus", "mola", "operator"}


class AnaPencere(QMainWindow):
    def __init__(self, db_yolu: str):
        super().__init__()
        self.db_yolu = db_yolu
        teshis.adim(f"veri tabanı açılıyor: {db_yolu}")
        self.con = vt.ac(db_yolu)
        teshis.adim("veri tabanı açıldı")
        self.ayar = vt.ayar_oku(self.con)
        teshis.adim("ayarlar okundu")
        self.sonuc = None
        self.kayit = []
        self.seflar = {}
        self.setWindowTitle("Vardiya Performans")
        self.setWindowIcon(QIcon(tema.kaynak_yolu("assets", "uygulama.ico")))
        self.resize(1500, 920)
        self.setMinimumSize(1180, 700)

        zemin = QWidget()
        zemin.setObjectName("Zemin")
        self.setCentralWidget(zemin)
        kok = QHBoxLayout(zemin)
        kok.setContentsMargins(0, 0, 0, 0)
        kok.setSpacing(0)

        # ------------------------------------------------ sol menü
        yan = QFrame()
        yan.setObjectName("Yan")
        yan.setFixedWidth(232)
        yl = QVBoxLayout(yan)
        yl.setContentsMargins(14, 16, 14, 14)
        yl.setSpacing(4)
        lg = QLabel()
        pm = tema.logo()
        if not pm.isNull():
            lg.setPixmap(pm.scaledToWidth(196, Qt.SmoothTransformation))
        lg.setAlignment(Qt.AlignCenter)
        yl.addWidget(lg)
        ad = QLabel("Vardiya Performans")
        ad.setAlignment(Qt.AlignCenter)
        ad.setStyleSheet(f"font-weight:700; color:{tema.LACIVERT}; font-size:14px; padding:6px 0 14px 0;")
        yl.addWidget(ad)
        self.grup = QButtonGroup(self)
        self.grup.setExclusive(True)
        self.menu = {}
        for anahtar, etiket_ in MENU:
            b = QPushButton(etiket_)
            b.setObjectName("Menu")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, a=anahtar: self.sayfa_ac(a))
            self.grup.addButton(b)
            self.menu[anahtar] = b
            yl.addWidget(b)
        yl.addStretch(1)
        self.alt_bilgi = QLabel("")
        self.alt_bilgi.setObjectName("AltBaslik")
        self.alt_bilgi.setWordWrap(True)
        yl.addWidget(self.alt_bilgi)
        yl.addWidget(QLabel(f"Sürüm {SURUM}"))
        self.gunc_btn = QPushButton("Güncellemeyi denetle")
        self.gunc_btn.setObjectName("Hizli")
        self.gunc_btn.setCursor(Qt.PointingHandCursor)
        self.gunc_btn.clicked.connect(lambda: self._guncelleme_baslat(elle=True))
        yl.addWidget(self.gunc_btn)
        self.gunc_durum = QLabel("")
        self.gunc_durum.setObjectName("AltBaslik")
        self.gunc_durum.setWordWrap(True)
        yl.addWidget(self.gunc_durum)
        kok.addWidget(yan)

        # ------------------------------------------------ sağ taraf
        sag = QVBoxLayout()
        sag.setContentsMargins(26, 18, 26, 10)
        sag.setSpacing(10)
        self.donem = DonemCubugu(lambda: vt.gun_kapsami(self.con), self.ayar["esik"], kural=self.ayar.get("hesap_kurali", "gunluk"),
                                 yontem=self.ayar.get("hesap_yontemi", "vardiya"))
        self.donem.yontem_degisti.connect(self._yontem_degisti)
        self.donem.degisti.connect(self.yenile)
        self.donem.esik_degisti.connect(self._esik_degisti)
        self.donem.kural_degisti.connect(self._kural_degisti)
        sag.addWidget(self.donem)
        self.yigin = QStackedWidget()
        self.sayfalar = {
            "veri": VeriSayfasi(self),
            "kayitlar": KayitlarSayfasi(self),
            "performans": PerformansSayfasi(self),
            "calisma": AnalizSayfasi(self, 0),
            "durus": AnalizSayfasi(self, 1),
            "mola": AnalizSayfasi(self, 2),
            "operator": OperatorSayfasi(self),
            "rapor": RaporSayfasi(self),
            "gecmis": GecmisSayfasi(self),
            "ayar": AyarSayfasi(self),
        }
        self.sira = [a for a, _ in MENU]
        for a in self.sira:
            self.yigin.addWidget(self.sayfalar[a])
        sag.addWidget(self.yigin, 1)
        self.mesaj_etiketi = QLabel("")
        self.mesaj_etiketi.setObjectName("Basari")
        self.mesaj_etiketi.hide()
        sag.addWidget(self.mesaj_etiketi)
        kok.addLayout(sag, 1)
        # sayfaların kendi kenar boşlukları var; çubuk ile aynı hizaya getirmek için sağ kenarı daralt
        for a in self.sira:
            self.sayfalar[a].layout().setContentsMargins(0, 8, 0, 4)

        self._mesaj_zamanlayici = QTimer(self)
        self._mesaj_zamanlayici.setSingleShot(True)
        self._mesaj_zamanlayici.timeout.connect(self.mesaj_etiketi.hide)

        self.donem.veri_yenilendi(ilk_secim=True)
        self.yenile()
        self.sayfa_ac("performans" if self.kapsam() else "veri")
        self._guncelleme = None
        if guncelleme.calisan_exe() and not os.environ.get("VARDIYA_GUNCELLEME_YOK"):
            QTimer.singleShot(2500, lambda: self._guncelleme_baslat(elle=False))

    def _guncelleme_baslat(self, elle: bool = False):
        exe = guncelleme.calisan_exe()
        if not exe:
            self.gunc_durum.setText("Güncelleme yalnızca kurulu (exe) programda çalışır")
            return
        if self._guncelleme is not None and self._guncelleme.isRunning():
            return
        self.gunc_durum.setText("")
        self._gunc_elle = elle
        self._guncelleme = guncelleme.GuncellemeKontrol(exe, self)
        self._guncelleme.durum.connect(self.gunc_durum.setText)
        self._guncelleme.hazir.connect(lambda surum, dosya: self._guncelleme_hazir(exe, surum, dosya))
        self._guncelleme.start()

    def _guncelleme_hazir(self, exe: str, surum: str, dosya: str):
        """Yeni sürüm var: açılışta yalnızca sol altta yazar; düğmeye basılınca indirme sayfasını açmayı önerir."""
        self.gunc_durum.setText(f"Yeni sürüm var: {surum}")
        if not getattr(self, "_gunc_elle", False):
            return
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtWidgets import QMessageBox
        kutu = QMessageBox(self)
        kutu.setIcon(QMessageBox.Information)
        kutu.setWindowTitle("Yeni sürüm")
        kutu.setText(f"Programın yeni sürümü var: {surum}\nŞu anki sürüm: {SURUM}")
        kutu.setInformativeText("İndirme sayfasında en üstteki derlemeye girip alttaki 'VardiyaPerformans' dosyasını indirin. "
                                "İçinden çıkan VardiyaPerformans.exe dosyasını eskisinin üstüne yazın; VardiyaPerformans.db dosyasına dokunmayın.")
        ac = kutu.addButton("İndirme sayfasını aç", QMessageBox.AcceptRole)
        kutu.addButton("Sonra", QMessageBox.RejectRole)
        kutu.exec()
        if kutu.clickedButton() is ac:
            QDesktopServices.openUrl(QUrl(guncelleme.INDIRME_SAYFASI))

    # ------------------------------------------------ API (sayfalar kullanır)
    def kapsam(self):
        return self.donem.kapsam()

    def son_veri_gunu(self) -> date:
        k = self.kapsam()
        return max(k) if k else date.today()

    def donem_gunleri(self) -> List[date]:
        return self.donem.gunler()

    def hesap_ayar(self) -> HesapAyar:
        a = self.ayar
        return HesapAyar(esik=a["esik"], vardiya_dk=a["vardiya_dk"], yemek_dk=a["yemek_dk"], cay_dk=a["cay_dk"],
                          kural="gunluk", yontem=a.get("hesap_yontemi", "vardiya"))

    def mesaj(self, metin: str):
        self.mesaj_etiketi.setText(metin)
        self.mesaj_etiketi.show()
        self._mesaj_zamanlayici.start(7000)

    def sayfa_ac(self, anahtar: str):
        self.menu[anahtar].setChecked(True)
        self.yigin.setCurrentIndex(self.sira.index(anahtar))
        self.donem.setVisible(anahtar in DONEMLI)
        s = self.sayfalar[anahtar]
        if hasattr(s, "yenile"):
            import time as _t
            t0 = _t.perf_counter()
            s.yenile()
            if _t.perf_counter() - t0 >= 1.0:           # yavaş açılan sayfa teşhis kaydına düşer
                teshis.adim(f"'{anahtar}' sayfası {_t.perf_counter() - t0:.1f} sn sürdü")

    def sef_ata(self, vardiya: int, ad: str, gunler: List[date]):
        if not gunler or not ad:
            return
        vt.sef_ata(self.con, gunler, vardiya, ad)
        self.seflar = vt.sef_getir(self.con, self.donem.gunler(), self.ayar)
        for a in ("performans", "calisma", "durus", "mola"):
            self.sayfalar[a].yenile()
        self.sayfalar["rapor"]._zamanla()

    def veri_yenilendi(self):
        self.donem.veri_yenilendi()
        self.yenile()

    def arsiv_degisti(self):
        self.sayfalar["gecmis"].yenile()

    def ayar_degisti(self):
        self.ayar = vt.ayar_oku(self.con)
        self.donem.esik.setValue(round(self.ayar["esik"] * 100))
        self.donem.yontem.setCurrentIndex(max(0, self.donem.yontem.findData(self.ayar.get("hesap_yontemi", "vardiya"))))
        self.donem.yontem_yaz()
        self.yenile()

    def _yontem_degisti(self, yontem: str):
        if yontem == self.ayar.get("hesap_yontemi"):
            return
        vt.ayar_yaz(self.con, "hesap_yontemi", yontem)
        self.ayar["hesap_yontemi"] = yontem
        self.yenile()
        self.sayfalar["ayar"].yenile()
        self.mesaj("Hesap yöntemi: " + dict(tema.YONTEMLER)[yontem])

    def _kural_degisti(self, kural: str):
        if kural == self.ayar.get("hesap_kurali"):
            return
        vt.ayar_yaz(self.con, "hesap_kurali", kural)
        self.ayar["hesap_kurali"] = kural
        self.yenile()
        self.sayfalar["ayar"].yenile()
        self.mesaj({"gunluk": "Günlük kural uygulanıyor.", "donem": "Dönem kuralı (Excel gibi) uygulanıyor."}[kural])

    def _esik_degisti(self, deger: float):
        if abs(deger - self.ayar["esik"]) < 1e-9:
            return
        vt.ayar_yaz(self.con, "esik", deger)
        self.ayar["esik"] = deger
        self.yenile()
        self.sayfalar["ayar"].yenile()

    def yenile(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            secili = self.donem.gunler()
            ilk, son = self.donem.aralik()
            if not secili:
                self.sonuc, self.seflar, self.kayit = None, {}, []
            else:
                tum = [ilk + timedelta(days=i) for i in range((son - ilk).days + 1)]
                kapsam = self.kapsam()
                gunler = sorted(set(secili) | {g for g in tum if not kapsam.get(g)})
                kayit = vt.kayitlari_getir(self.con, min(gunler), max(gunler))
                self.kayit = kayit
                self.sonuc = hesapla(kayit, gunler, self.hesap_ayar(), set(kapsam))
                self.seflar = vt.sef_getir(self.con, secili, self.ayar)
            k = self.kapsam()
            if k:
                n = self.con.execute("SELECT COUNT(*) FROM kayit").fetchone()[0]
                self.alt_bilgi.setText(f"Veri: {n:,} kayıt\n{min(k):%d.%m.%Y} – {max(k):%d.%m.%Y}".replace(",", "."))
            else:
                self.alt_bilgi.setText("Henüz veri yok")
        finally:
            QApplication.restoreOverrideCursor()
        for a in ("performans", "calisma", "durus", "mola", "operator"):
            self.sayfalar[a].yenile()
        self.sayfalar["veri"].yenile()
        if hasattr(self, "sayfalar") and self.yigin.currentWidget() is self.sayfalar["rapor"]:
            self.sayfalar["rapor"].yenile()
