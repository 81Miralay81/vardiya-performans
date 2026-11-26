"""Ana pencere: sol menü + sayfalar + üstte dönem çubuğu."""
from __future__ import annotations

import os
from datetime import date, timedelta
from typing import List, Optional

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from . import acilis, tema, teshis, veritabani as vt
from .donem import DonemCubugu
from .hesap import HesapAyar, hesapla
from .sayfa_analiz import AnalizSayfasi
from .sayfa_ayar import AyarSayfasi
from .sayfa_gecmis import GecmisSayfasi
from .sayfa_kayitlar import KayitlarSayfasi
from .sayfa_operator import OperatorSayfasi
from .sayfa_performans import PerformansSayfasi
from .sayfa_hatali import HataliSayfasi
from .sayfa_personel import PersonelSayfasi
from .sayfa_rapor import RaporSayfasi
from .sayfa_veri import VeriSayfasi
from .surum import SURUM
from . import guncelleme

MENU = (("veri", "Veri Aktar"), ("kayitlar", "Kayıtlar"), ("performans", "Performans"), ("hatali", "Hatalı Duruşlar"), ("calisma", "Çalışma"), ("durus", "Genel Duruş"), ("mola", "Mola"),
        ("operator", "Operatör"), ("personel", "Personel Durum"), ("rapor", "Raporlar"), ("gecmis", "Geçmiş"), ("ayar", "Ayarlar"))
DONEMLI = {"performans", "hatali", "calisma", "durus", "mola", "operator"}


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
        self.kullanici = None                       # giriş yapan kullanıcı (kullanıcı sistemi kapalıysa None)
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
        self.k_etiket = QLabel("")
        self.k_etiket.setObjectName("AltBaslik")
        self.k_etiket.setWordWrap(True)
        yl.addWidget(self.k_etiket)
        self.kopru_etiket = QLabel("")            # GEÇİCİ geliştirici bağlantısı açıkken görünür
        self.kopru_etiket.setWordWrap(True)
        self.kopru_etiket.setStyleSheet("color:#fff; background:#c0392b; border-radius:6px; padding:5px; font-weight:600;")
        self.kopru_etiket.hide()
        yl.addWidget(self.kopru_etiket)
        self.k_cikis = QPushButton("Çıkış yap")
        self.k_cikis.setObjectName("Hizli")
        self.k_cikis.setCursor(Qt.PointingHandCursor)
        self.k_cikis.clicked.connect(self.cikis)
        self.k_cikis.hide()
        yl.addWidget(self.k_cikis)
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
        acilis.ilerle(60, "Sayfalar hazırlanıyor")
        self.sayfalar = {
            "veri": VeriSayfasi(self),
            "kayitlar": KayitlarSayfasi(self),
            "performans": PerformansSayfasi(self),
            "hatali": HataliSayfasi(self),
            "calisma": AnalizSayfasi(self, 0),
            "durus": AnalizSayfasi(self, 1),
            "mola": AnalizSayfasi(self, 2),
            "operator": OperatorSayfasi(self),
            "personel": PersonelSayfasi(self),
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

        acilis.ilerle(72, "Kayıtlı veriler okunuyor")
        self.donem.veri_yenilendi(ilk_secim=True)
        acilis.ilerle(80, "Son 7 günün hesabı yapılıyor")
        self.yenile()
        acilis.ilerle(90, "Grafikler hazırlanıyor")
        self.sayfa_ac("performans" if self.kapsam() else "veri")
        from .kopru import Kopru                        # GEÇİCİ geliştirici bağlantısı (yalnızca Ayarlar'dan açılınca çalışır)
        self.kopru = Kopru(self)
        self.kopru.durum_degisti.connect(lambda m: (self.kopru_etiket.setText(m), self.kopru_etiket.setVisible(bool(m))))
        if hasattr(self.sayfalar.get("ayar"), "kopru_durum"):
            self.kopru.durum_degisti.connect(self.sayfalar["ayar"].kopru_durum.setText)
        from .oto_cekim import OtoCekim                 # otomatik Cormind çekimi (yalnızca ayarda açık bilgisayarda)
        self.oto = OtoCekim(self)
        self.sayfalar["ayar"].oto_bagla(self.oto)
        from .oturum import Oturum, kapanis_uyarisi       # açık programlar / güncelleme için uzaktan kapatma
        self.oturum = Oturum(self.db_yolu, self)
        self.oturum.kapat_istendi.connect(lambda pc: kapanis_uyarisi(self, pc))
        self._guncelleme = None
        if guncelleme.calisan_exe() and not os.environ.get("VARDIYA_GUNCELLEME_YOK"):
            QTimer.singleShot(2500, lambda: self._guncelleme_baslat(elle=False))

    # ------------------------------------------------ kullanıcı girişi ve yetkiler
    def yetkili(self, anahtar: str) -> bool:
        from .kullanici import yetkili
        return yetkili(self.kullanici, anahtar)

    def menu_izinli(self, sayfa: str) -> bool:
        """Menüdeki bir ekran bu kullanıcıya açık mı (Veri Aktar: Cormind ya da personel verisi çekme yetkisinden biri yeter)."""
        from .kullanici import MENU_YETKI
        if sayfa == "veri":
            return self.yetkili("veri") or self.yetkili("personel_veri")
        return self.yetkili(MENU_YETKI.get(sayfa, sayfa))

    def giris(self) -> bool:
        """Kullanıcı sistemi açıksa giriş ister. False: vazgeçildi (program kapanır)."""
        from . import kullanici as ku
        if not ku.var_mi(self.con):
            self.kullanici = None
        else:
            k = ku.giris_penceresi(self.con, None)
            if not k:
                return False
            self.kullanici = k
            teshis.adim(f"giriş: {k['ad']}")
        self.yetki_uygula()
        return True

    def yetki_uygula(self):
        for a, b in self.menu.items():
            b.setVisible(self.menu_izinli(a))
        if self.kullanici:
            self.k_etiket.setText(f"Kullanıcı: {self.kullanici['ad']}" + (" (yönetici)" if self.kullanici.get("yonetici") else ""))
            self.k_cikis.show()
        else:
            self.k_etiket.setText("")
            self.k_cikis.hide()
        izinli = [a for a in self.sira if self.menu_izinli(a)]   # pencere henüz gösterilmemiş olabilir: isVisible kullanılmaz
        for a in self.sira:
            self.sayfalar[a].setEnabled(a in izinli)
        acik = self.sira[self.yigin.currentIndex()]
        if acik not in izinli:
            if izinli:
                self.sayfa_ac(izinli[0])
            else:
                self.menu[acik].setChecked(False)
        for sf in self.sayfalar.values():                 # sayfaların içindeki özellikler (Excel, personel verisi çekme…)
            if hasattr(sf, "yetki_uygula"):
                try:
                    sf.yetki_uygula(self.yetkili)
                except Exception as ex:  # noqa: BLE001
                    teshis.adim(f"yetki uygulanamadı: {type(sf).__name__}: {ex}")
        if hasattr(self.sayfalar.get("ayar"), "kullanici_yenile"):
            self.sayfalar["ayar"].kullanici_yenile()

    def cikis(self):
        from . import kullanici as ku
        ku.cikis_yap(self.con)
        self.hide()
        if not self.giris():
            QApplication.quit()
            return
        self.show()

    def closeEvent(self, e):
        try:
            self.oturum.bitir()
        except Exception:  # noqa: BLE001
            pass
        super().closeEvent(e)

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
        from .servis import hesap_ayari
        return hesap_ayari(self.ayar)

    def mesaj(self, metin: str):
        self.mesaj_etiketi.setText(metin)
        self.mesaj_etiketi.show()
        self._mesaj_zamanlayici.start(7000)

    def sayfa_ac(self, anahtar: str):
        if not self.menu_izinli(anahtar):
            return
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
        import time as _t
        from .bekleme import Bekleme
        QApplication.setOverrideCursor(Qt.WaitCursor)
        bekle, t0, n_kayit = None, _t.perf_counter(), 0
        bk = Bekleme(self, "Dönem hesaplanıyor", "seçilen günlerin kayıtları okunup vardiya hesabı yapılıyor", gecikme_ms=0) \
            if self.isVisible() and (self.donem.aralik()[1] - self.donem.aralik()[0]).days <= 31 else None
        if bk:
            QApplication.processEvents()
        try:
            secili = self.donem.gunler()
            ilk, son = self.donem.aralik()
            if not secili:
                self.sonuc, self.seflar, self.kayit = None, {}, []
            else:
                gun_sayisi = (son - ilk).days + 1
                if gun_sayisi > 31 and self.isVisible():          # 1 aydan uzun dönem: uyar ve ilerlemeyi göster
                    bekle = acilis.BeklemePenceresi(
                        self, "Grafikler hazırlanıyor, lütfen bekleyin…",
                        f"Seçilen aralık {gun_sayisi} gün ({ilk:%d.%m.%Y} – {son:%d.%m.%Y}). Bir aydan uzun aralıklarda "
                        "hesap ve grafiklerin çizimi uzun sürebilir.")
                    bekle.adim(5, "Kayıtlar veri tabanından okunuyor…")
                tum = [ilk + timedelta(days=i) for i in range((son - ilk).days + 1)]
                kapsam = self.kapsam()
                gunler = sorted(set(secili) | {g for g in tum if not kapsam.get(g)})
                kayit = vt.kayitlari_getir(self.con, min(gunler), max(gunler))
                n_kayit = len(kayit)
                if bekle:
                    tahmin = acilis.hiz_oku() * n_kayit / 1000.0
                    bekle.adim(30, f"{n_kayit:,} kayıt hesaplanıyor · tahmini kalan süre: yaklaşık {acilis.sure_yazisi(tahmin)}".replace(",", "."))
                self.kayit = kayit
                self.sonuc = hesapla(kayit, gunler, self.hesap_ayar(), set(kapsam))
                self.donem.uyari_yaz(self.sonuc.bozuk_kayit)
                self.seflar = vt.sef_getir(self.con, secili, self.ayar)
                if bekle:
                    gecen = _t.perf_counter() - t0
                    bekle.adim(65, f"Grafikler çiziliyor · tahmini kalan süre: yaklaşık "
                                   f"{acilis.sure_yazisi(max(1.0, acilis.hiz_oku() * n_kayit / 1000.0 - gecen))}")
            k = self.kapsam()
            if k:
                n = vt.toplam_kayit(self.con)
                self.alt_bilgi.setText(f"Veri: {n:,} kayıt\n{min(k):%d.%m.%Y} – {max(k):%d.%m.%Y}".replace(",", "."))
            else:
                self.alt_bilgi.setText("Henüz veri yok")
        finally:
            QApplication.restoreOverrideCursor()
            if bk:
                bk.bitir()
        # Yalnızca o an açık olan sayfa yenilenir; diğerleri açıldıklarında (sayfa_ac) kendileri yenilenir.
        acik = self.yigin.currentWidget()
        for a in ("performans", "hatali", "calisma", "durus", "mola", "operator"):
            if self.sayfalar[a] is acik:
                self.sayfalar[a].yenile()
        self.sayfalar["veri"].yenile()
        if hasattr(self, "sayfalar") and self.yigin.currentWidget() is self.sayfalar["rapor"]:
            self.sayfalar["rapor"].yenile()
        if bekle:
            bekle.adim(100, "Hazır")
            bekle.close()
        acilis.hiz_yaz(n_kayit, _t.perf_counter() - t0)
