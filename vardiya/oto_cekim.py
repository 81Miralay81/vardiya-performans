"""Cormind'den otomatik çekim (yalnızca ayarda açık olan bilgisayarda, program açık kaldıkça).

Kural: yalnızca BİTMİŞ günler çekilir; bugün hiçbir zaman otomatik çekilmez (tabloda yarım gün olmasın).
Hangi günlerin tam olduğu aktarım geçmişinden çıkarılır: bir gün, bitişinden en az YARIM_SAAT sonra çekildiyse tamdır.
Ne zaman: program açılınca bir kez, program açık kaldıysa her gece GECE_SAATI'nde. Tam olmayan ilk günden düne kadar
olan aralık çekilir. Çekim hata verirse YENIDEN_DK dakika sonra yeniden denenir.
"""
from __future__ import annotations

import base64
import re
from datetime import date, datetime, timedelta
from typing import Optional, Tuple

from PySide6.QtCore import QObject, QSettings, QTimer, Signal

from . import veritabani as vt

GECE_SAATI = 1                             # her gece 01:00
PV_SAATI = "20:00"                         # personel verisi varsayılan çekim saati (Ayarlar'dan değişir; dünün düzeltmeleri ertesi gün 18:00'e kadar yapılır)
YENIDEN_DK = 30
YARIM_SAAT = timedelta(minutes=30)         # Cormind gün sonu kayıtlarını kapatsın diye beklenen pay
EN_GERI_GUN = 62                           # hiç geçmiş yoksa ya da çok eskiyse en fazla bu kadar geri gidilir
_ARALIK = re.compile(r"Cormind \((\d{2}\.\d{2}\.\d{4})[–-](\d{2}\.\d{2}\.\d{4})\)")


def ayarda_acik() -> bool:
    return str(QSettings("Teknorot", "VardiyaPerformans").value("oto/acik", "0")) == "1"


def son_tam_gun(con) -> Optional[date]:
    """Aktarım geçmişine göre tam (gün bittikten sonra) çekilmiş en son gün."""
    en: Optional[date] = None
    for r in con.execute("SELECT zaman, dosya FROM aktarim WHERE dosya LIKE 'Cormind (%' ORDER BY id DESC LIMIT 400"):
        m = _ARALIK.search(r["dosya"] or "")
        if not m:
            continue
        try:
            ilk = datetime.strptime(m.group(1), "%d.%m.%Y").date()
            son = datetime.strptime(m.group(2), "%d.%m.%Y").date()
            zaman = datetime.strptime(r["zaman"], vt.BICIM)
        except ValueError:
            continue
        tam = min(son, (zaman - YARIM_SAAT).date() - timedelta(days=1))   # o çekimde bitmiş olan son gün
        if tam >= ilk and (en is None or tam > en):
            en = tam
    return en


def eksik_aralik(con, bugun: Optional[date] = None) -> Optional[Tuple[date, date]]:
    """Çekilmesi gereken (ilk, son) aralığı; son her zaman dündür. Eksik yoksa None."""
    bugun = bugun or date.today()
    dun = bugun - timedelta(days=1)
    tam = son_tam_gun(con)
    if tam is not None:
        ilk = tam + timedelta(days=1)
    else:                                         # geçmiş yok: veri tabanındaki son günden (yarım olabilir) başla
        r = con.execute("SELECT MAX(gun) FROM gun_ozet WHERE kayit > 0").fetchone()
        ilk = date.fromisoformat(r[0]) if r and r[0] else dun
    ilk = max(ilk, dun - timedelta(days=EN_GERI_GUN))
    if ilk > dun:
        return None
    return ilk, dun


class OtoCekim(QObject):
    """Ana pencereye bağlı zamanlayıcı. Durum metni Ayarlar sayfasında görünür."""
    durum_degisti = Signal(str)

    def __init__(self, ana):
        super().__init__(ana)
        self.ana = ana
        self.durum = "Kapalı"
        self._is = None
        self._gece_yapilan: Optional[date] = None     # bu gece 01:00 çekimi yapıldı mı
        self._yeniden: Optional[datetime] = None      # hata sonrası yeniden deneme zamanı
        self._cm_durum = "Kapalı"
        self._pv_durum = ""
        self._pv_pencere = None
        self._pv_yeniden: Optional[datetime] = None
        self.saat = QTimer(self)                      # dakikada bir saate bakar (bilgisayar uykudan uyansa da kaçırmaz)
        self.saat.timeout.connect(self._saat_geldi)
        self.ayarla(acilis=True)

    def ayarla(self, acilis: bool = False):
        """Açılışta ve ayar değişince çağrılır."""
        self.saat.stop()
        if not ayarda_acik():
            self._yaz("Kapalı")
            return
        simdi = datetime.now()
        if simdi.hour >= GECE_SAATI:                  # bugünün gece çekimi zamanı geçti: açılış çekimi onun yerine geçer
            self._gece_yapilan = simdi.date()
        self.saat.start(60 * 1000)
        self._yaz(f"Açık · açılışta ve her gece {GECE_SAATI:02d}:00'da eksik günler çekilir (bugün çekilmez)")
        QTimer.singleShot(15000 if acilis else 2000, self.kontrol)
        QTimer.singleShot(45000 if acilis else 5000, self.pv_kontrol)

    def _saat_geldi(self):
        simdi = datetime.now()
        if self._pv_yeniden is None or simdi >= self._pv_yeniden:
            self.pv_kontrol()
        if self._yeniden is not None and simdi >= self._yeniden:
            self._yeniden = None
            self.kontrol()
        elif simdi.hour >= GECE_SAATI and self._gece_yapilan != simdi.date():
            self._gece_yapilan = simdi.date()
            self.kontrol()

    def _yaz(self, metin: str):
        self._cm_durum = metin
        self._yayinla()

    def _pv_yaz(self, metin: str):
        self._pv_durum = metin
        self._yayinla()

    def _yayinla(self):
        self.durum = "Cormind: " + self._cm_durum + (f"\nPersonel veri: {self._pv_durum}" if self._pv_durum else "")
        self.durum_degisti.emit(self.durum)

    # ------------------------------------------------ personel verisi (her akşam 20:00, dünü)
    @staticmethod
    def pv_saat_coz(metin) -> tuple:
        try:
            h, m = str(metin or PV_SAATI).split(":")
            h, m = int(h), int(m)
            if 0 <= h < 24 and 0 <= m < 60:
                return h, m
        except (ValueError, AttributeError):
            pass
        return 20, 0

    def pv_saati(self) -> tuple:
        return self.pv_saat_coz((getattr(self.ana, "ayar", {}) or {}).get("pv_cekim_saati", PV_SAATI))

    @classmethod
    def pv_hedef(cls, simdi: Optional[datetime] = None, saat: tuple = (20, 0)) -> date:
        """Çekim saati geçtiyse dün, geçmediyse önceki gün (her zaman bir gün geriden)."""
        simdi = simdi or datetime.now()
        return simdi.date() - timedelta(days=1 if (simdi.hour, simdi.minute) >= tuple(saat) else 2)

    @staticmethod
    def pv_son_tam() -> Optional[date]:
        try:
            return date.fromisoformat(str(QSettings("Teknorot", "VardiyaPerformans").value("pveri/son_tam", "") or ""))
        except ValueError:
            return None

    def pv_kontrol(self):
        if not ayarda_acik() or self._pv_pencere is not None:
            return
        from .personel_pencere import ERTELENDI, elle_acik_mi, kimlik_oku, otomatik_calistir, sablon_oku
        if elle_acik_mi():                                # kullanıcı Personel Veri penceresini kullanıyor: bitince denenir
            return
        if not sablon_oku("giris_cikis") or not all(kimlik_oku()):
            self._pv_yaz("hazır değil (Personel Veri penceresinde giriş yapıp bir ayı bir kez elle listeleyin)")
            return
        saat = self.pv_saati()
        saat_y = f"{saat[0]:02d}:{saat[1]:02d}"
        hedef = self.pv_hedef(saat=saat)
        son_tam = self.pv_son_tam()
        if son_tam is not None and son_tam >= hedef:
            if not self._pv_durum:
                self._pv_yaz(f"{son_tam:%d.%m.%Y} dahil tam · sıradaki: {saat_y}")
            return
        ay1 = date(hedef.year, hedef.month, 1)
        ilk = ay1 if son_tam is None else min(son_tam + timedelta(days=1), ay1)
        ilk = max(ilk, hedef - timedelta(days=EN_GERI_GUN))
        self._pv_yaz(f"çekiliyor: {ilk:%d.%m.%Y} – {hedef:%d.%m.%Y} …")

        def bitti(basarili: bool, metin: str, h=hedef):
            from . import teshis
            self._pv_pencere = None
            teshis.adim(f"personel veri otomatik çekim: {metin}")
            if basarili:
                QSettings("Teknorot", "VardiyaPerformans").setValue("pveri/son_tam", h.isoformat())
                self._pv_yeniden = None
                self._pv_yaz(f"son çekim {datetime.now():%d.%m.%Y %H:%M}: {metin} · sıradaki: {saat_y}")
                try:
                    s = self.ana.sayfalar.get("personel")
                    if s is not None and s.isVisible():
                        s.yenile()
                except Exception:  # noqa: BLE001
                    pass
            elif metin.startswith(ERTELENDI):
                self._pv_yeniden = None
                self._pv_yaz(f"{metin} · sıradaki: {saat_y}")
            else:
                bugun = datetime.now().date()
                if getattr(self, "_pv_hata_gun", None) != bugun:
                    self._pv_hata_gun, self._pv_hata_sayi = bugun, 0
                self._pv_hata_sayi += 1
                if self._pv_hata_sayi >= 3:              # aynı gün 3 başarısız denemeden sonra ertesi güne kadar bekle
                    self._pv_yeniden = datetime.combine(bugun + timedelta(days=1), datetime.min.time())
                    self._pv_yaz(f"hata ({datetime.now():%d.%m %H:%M}): {metin} · bugün 3 kez denendi, yarın yeniden denenecek")
                else:
                    self._pv_yeniden = datetime.now() + timedelta(minutes=YENIDEN_DK)
                    self._pv_yaz(f"hata ({datetime.now():%d.%m %H:%M}): {metin} · {self._pv_yeniden:%H:%M}'de yeniden denenecek")
        self._pv_pencere = otomatik_calistir(self.ana.db_yolu, ilk, hedef, self.ana, bitti) or None

    def _baska_cekim_var(self) -> bool:
        if self._is is not None and self._is.isRunning():
            return True
        try:
            k = self.ana.sayfalar["veri"].cormind
            if k._is is not None and k._is.isRunning():
                return True
        except Exception:  # noqa: BLE001
            pass
        try:
            from . import web_sunucu
            s = web_sunucu.etkin()
            if s is not None and s.cekim.get("durum") == "calisiyor":
                return True
        except Exception:  # noqa: BLE001
            pass
        return False

    def _sonraki(self) -> str:
        return f"sıradaki: gece {GECE_SAATI:02d}:00"

    def kontrol(self):
        if not ayarda_acik():
            return
        if self._baska_cekim_var():
            self._yeniden = datetime.now() + timedelta(minutes=5)
            return
        aralik = eksik_aralik(self.ana.con)
        simdi = datetime.now()
        if aralik is None:
            self._yaz(f"Açık · veriler dün dahil tam (kontrol {simdi:%d.%m %H:%M}) · {self._sonraki()}")
            return
        ayar = QSettings("Teknorot", "VardiyaPerformans")
        kul = str(ayar.value("cormind/kullanici", "") or "")
        try:
            sifre = base64.b64decode(str(ayar.value("cormind/sifre", "") or "")).decode("utf8")
        except Exception:  # noqa: BLE001
            sifre = ""
        if not kul or not sifre:
            self._yaz("Cormind kullanıcı adı ve şifresi bu bilgisayarda kayıtlı değil: Veri Aktar'dan bir kez elle çekim yapın.")
            return
        from . import cormind
        from .sayfa_veri import CormindIs
        a = self.ana.ayar
        ilk, son = aralik
        self._yaz(f"Çekiliyor: {ilk:%d.%m.%Y} – {son:%d.%m.%Y} …")
        self._is = CormindIs(self.ana.db_yolu, a.get("cormind_adres", cormind.VARSAYILAN_ADRES), kul, sifre, ilk, son,
                             a.get("cormind_makine_idleri") or cormind.VARSAYILAN_MAKINE_IDLERI, self, True)
        self._is.bitti.connect(lambda r, i=ilk, s=son: self._bitti(r, i, s))
        self._is.hata.connect(self._hata)
        self._is.start()

    def _hata(self, m: str):
        self._yeniden = datetime.now() + timedelta(minutes=YENIDEN_DK)
        self._yaz(f"Son otomatik çekim hata verdi ({datetime.now():%d.%m %H:%M}): {m} · {self._yeniden:%H:%M}'de yeniden denenecek")

    def _bitti(self, r: dict, ilk: date, son: date):
        from . import teshis
        adet = f"{r.get('toplam', 0):,}".replace(",", ".")
        metin = (f"Son otomatik çekim {datetime.now():%d.%m.%Y %H:%M}: {ilk:%d.%m.%Y} – {son:%d.%m.%Y}, {adet} kayıt · "
                 + self._sonraki())
        teshis.adim(metin)
        self._yaz(metin)
        try:
            self.ana.veri_yenilendi()
        except Exception:  # noqa: BLE001
            pass
