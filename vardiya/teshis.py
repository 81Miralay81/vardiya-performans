"""Teşhis: açılış adımlarının süre kaydı, donma bekçisi ve sunucu (ağ klasörü) hız ölçümü.

Kayıt dosyası her zaman bu bilgisayarın kendi diskine yazılır (ağ klasörü takılsa bile yazılabilsin diye);
her satır yazılır yazılmaz diske işlenir, böylece program donarsa son satır nerede kaldığını gösterir.
Bu modül yalnızca Python'un kendi kütüphanesini kullanır; main.py'de her şeyden önce içe aktarılır.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import threading
import time
import traceback
from datetime import datetime
from typing import Callable, List, Optional

_T0 = time.perf_counter()
_SON = _T0
_KILIT = threading.Lock()
_DOSYA = None
_NABIZ = time.monotonic()
_BEKCI_ACIK = False


def kayit_klasoru() -> str:
    kok = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    yol = os.path.join(kok, "VardiyaPerformans")
    os.makedirs(yol, exist_ok=True)
    return yol


def kayit_yolu() -> str:
    return os.path.join(kayit_klasoru(), "acilis_kaydi.txt")


def _yaz(satir: str):
    global _DOSYA
    with _KILIT:
        try:
            if _DOSYA is None:
                yol = kayit_yolu()
                if os.path.exists(yol) and os.path.getsize(yol) > 400_000:      # şişmesin: eskiyi bir kez yedekle
                    os.replace(yol, yol + ".eski")
                _DOSYA = open(yol, "a", encoding="utf-8")
            _DOSYA.write(satir + "\n")
            _DOSYA.flush()
            os.fsync(_DOSYA.fileno())
        except Exception:  # noqa: BLE001  (teşhis hiçbir zaman programı düşürmemeli)
            pass


def adim(ad: str):
    """Bir açılış adımının bittiğini kaydeder: saat, baştan beri geçen süre, bu adımın süresi."""
    global _SON
    simdi = time.perf_counter()
    _yaz(f"{datetime.now():%H:%M:%S}  toplam {simdi - _T0:7.2f} sn   bu adım {simdi - _SON:7.2f} sn   {ad}")
    _SON = simdi


def ag_yolu_mu(yol: str) -> bool:
    yol = os.path.abspath(yol)
    if yol.startswith("\\\\"):
        return True
    if sys.platform == "win32" and len(yol) > 1 and yol[1] == ":":
        try:
            import ctypes
            return ctypes.windll.kernel32.GetDriveTypeW(yol[:3]) == 4          # 4: ağ sürücüsü
        except Exception:  # noqa: BLE001
            return False
    return False


def _surec_baslangici(pid: Optional[int] = None):
    """(başlangıç zamanı (epoch sn), exe yolu) — yalnızca Windows; bulunamazsa (None, None)."""
    if sys.platform != "win32":
        return None, None
    try:
        import ctypes
        from ctypes import wintypes
        k = ctypes.windll.kernel32
        k.OpenProcess.restype = wintypes.HANDLE
        k.GetCurrentProcess.restype = wintypes.HANDLE
        h = k.GetCurrentProcess() if pid is None else k.OpenProcess(0x1000, False, pid)   # sınırlı sorgu izni
        if not h:
            return None, None
        c, e, kr, u = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
        tamam = k.GetProcessTimes(wintypes.HANDLE(h), ctypes.byref(c), ctypes.byref(e), ctypes.byref(kr), ctypes.byref(u))
        ad = None
        tampon = ctypes.create_unicode_buffer(1024)
        boy = wintypes.DWORD(1024)
        if k.QueryFullProcessImageNameW(wintypes.HANDLE(h), 0, tampon, ctypes.byref(boy)):
            ad = tampon.value
        if pid is not None:
            k.CloseHandle(wintypes.HANDLE(h))
        if not tamam:
            return None, ad
        return ((c.dwHighDateTime << 32) + c.dwLowDateTime) / 1e7 - 11644473600.0, ad
    except Exception:  # noqa: BLE001
        return None, None


def baslat(surum: str = ""):
    """Açılış kaydının başlığını yazar; exe'ye tıklanmasından programın çalışmaya başlamasına kadar geçen süreyi de hesaplar."""
    exe = sys.executable if getattr(sys, "frozen", False) else os.path.abspath(sys.argv[0])
    _yaz("")
    _yaz("=" * 78)
    _yaz(f"AÇILIŞ  {datetime.now():%d.%m.%Y %H:%M:%S}   sürüm {surum}   bilgisayar {os.environ.get('COMPUTERNAME', '?')}")
    _yaz(f"Program dosyası: {exe}")
    _yaz(f"Konum: {'AĞ KLASÖRÜ (sunucu)' if ag_yolu_mu(exe) else 'bu bilgisayarın diski'}")
    try:
        _yaz(f"Dosya boyutu: {os.path.getsize(exe) / 1e6:.1f} MB")
    except OSError:
        pass
    gecici = getattr(sys, "_MEIPASS", None)
    if gecici:
        _yaz(f"Geçici açılma klasörü: {gecici}")
    # tek dosyalı exe iki süreçtir: ilki (ana) paketi diske açar, ikincisi programı çalıştırır
    kendi, _ = _surec_baslangici()
    ana, ana_ad = _surec_baslangici(os.getppid()) if gecici else (None, None)
    simdi = time.time()
    if ana and ana_ad and os.path.basename(ana_ad).lower() == os.path.basename(exe).lower():
        _yaz(f"ÖN AŞAMA (exe'nin sunucudan okunup geçici klasöre açılması + virüs taraması): {max(0.0, (kendi or simdi) - ana):.1f} sn")
        if kendi:
            _yaz(f"Programın çalışmaya başlaması (kütüphanelerin yüklenmesi): {max(0.0, simdi - kendi):.1f} sn")
    elif kendi:
        _yaz(f"Tıklamadan programın çalışmaya başlamasına kadar: {max(0.0, simdi - kendi):.1f} sn")
    _yaz("-" * 78)


# --- donma bekçisi -------------------------------------------------------------------------------

def nabiz():
    """Ekran iş parçacığı düzenli çağırır; çağrı kesilirse bekçi donmayı kaydeder."""
    global _NABIZ
    _NABIZ = time.monotonic()


def bekci_baslat(esik_sn: float = 4.0):
    """Arka planda izler: ekran esik_sn'den uzun yanıt vermezse o anda hangi satırda beklediğini kayda yazar."""
    global _BEKCI_ACIK
    if _BEKCI_ACIK:
        return
    _BEKCI_ACIK = True
    ana_kimlik = threading.main_thread().ident
    nabiz()

    def dongu():
        son_yazilan = 0.0
        donuk = False
        while True:
            time.sleep(1.0)
            gecikme = time.monotonic() - _NABIZ
            if gecikme >= esik_sn:
                if gecikme - son_yazilan >= (esik_sn if not donuk else 15.0):
                    donuk = True
                    son_yazilan = gecikme
                    cerceve = sys._current_frames().get(ana_kimlik)  # noqa: SLF001
                    yigin = "".join(traceback.format_stack(cerceve)[-8:]) if cerceve else "  (bilinmiyor)\n"
                    _yaz(f"{datetime.now():%H:%M:%S}  DONMA: ekran {gecikme:.0f} saniyedir yanıt vermiyor. Beklediği yer:\n{yigin.rstrip()}")
            elif donuk:
                _yaz(f"{datetime.now():%H:%M:%S}  DONMA BİTTİ: ekran yeniden yanıt veriyor (yaklaşık {son_yazilan:.0f} sn sürdü)")
                donuk = False
                son_yazilan = 0.0

    threading.Thread(target=dongu, name="teshis-bekci", daemon=True).start()


def kaydi_oku(son_bayt: int = 60_000) -> str:
    try:
        with open(kayit_yolu(), "r", encoding="utf-8", errors="replace") as f:
            f.seek(0, os.SEEK_END)
            boy = f.tell()
            f.seek(max(0, boy - son_bayt))
            return f.read()
    except OSError:
        return "(henüz kayıt yok)"


# --- sunucu ölçümü -------------------------------------------------------------------------------

def _olc(islem: Callable):
    t = time.perf_counter()
    try:
        sonuc = islem()
        return time.perf_counter() - t, sonuc, None
    except Exception as ex:  # noqa: BLE001
        return time.perf_counter() - t, None, ex


def _dosya_oku(yol: str, iptal: Optional[Callable[[], bool]] = None, blok: int = 1 << 20):
    """Dosyayı baştan sona okur: (bayt, ilk blok süresi, en yavaş blok süresi)."""
    toplam, ilk, enyavas = 0, None, 0.0
    with open(yol, "rb", buffering=0) as f:
        while True:
            t = time.perf_counter()
            veri = f.read(blok)
            d = time.perf_counter() - t
            if not veri:
                break
            toplam += len(veri)
            ilk = d if ilk is None else ilk
            enyavas = max(enyavas, d)
            if iptal and iptal():
                break
    return toplam, ilk or 0.0, enyavas


def sunucu_olcumu(klasor: str, ilerleme: Optional[Callable[[str], None]] = None,
                  iptal: Optional[Callable[[], bool]] = None) -> str:
    """Verilen klasörde (sunucudaki program klasörü) okuma, yazma ve veri tabanı sürelerini ölçer; metin rapor döndürür.
    Hiçbir kaydı değiştirmez: yalnızca okur, bir deneme dosyası yazıp siler ve veri tabanı kilidini alıp hemen bırakır."""
    s: List[str] = []

    def yaz(m: str):
        s.append(m)
        if ilerleme:
            ilerleme(m)

    def durdu() -> bool:
        return bool(iptal and iptal())

    yaz(f"SUNUCU ÖLÇÜMÜ  {datetime.now():%d.%m.%Y %H:%M:%S}   bilgisayar {os.environ.get('COMPUTERNAME', '?')}")
    yaz(f"Klasör: {klasor}")
    yaz(f"Konum: {'ağ klasörü (sunucu)' if ag_yolu_mu(klasor) else 'bu bilgisayarın diski'}")
    yaz("")

    # 1) klasöre erişim ve içindekiler
    d, adlar, hata = _olc(lambda: sorted(os.listdir(klasor)))
    if hata:
        yaz(f"1) Klasöre ERİŞİLEMEDİ ({d:.2f} sn): {hata}")
        return "\n".join(s)
    yaz(f"1) Klasör listesi: {d:.2f} sn, {len(adlar)} öğe")
    exeler, dbler = [], []
    for ad in adlar:
        yol = os.path.join(klasor, ad)
        try:
            if os.path.isdir(yol):
                yaz(f"     [klasör] {ad}")
            else:
                boy = os.path.getsize(yol)
                degisim = datetime.fromtimestamp(os.path.getmtime(yol))
                yaz(f"     {ad}   {boy / 1e6:.2f} MB   {degisim:%d.%m.%Y %H:%M}")
                if ad.lower().endswith(".exe"):
                    exeler.append((yol, boy))
                if ad.lower().endswith(".db"):
                    dbler.append((yol, boy))
        except OSError as ex:
            yaz(f"     {ad}   (okunamadı: {ex})")
    if any(a.lower() == "_internal" for a in adlar):
        yaz("     NOT: '_internal' klasörü 1.0.42'den kalmadır; artık gerekmez, silinebilir.")
    yaz("")

    # 2) program dosyasını sunucudan okuma hızı
    if not exeler:
        yaz("2) Bu klasörde .exe yok; okuma hızı ölçülemedi.")
    for yol, boy in exeler:
        if durdu():
            break
        d, sonuc, hata = _olc(lambda y=yol: _dosya_oku(y, iptal))
        if hata:
            yaz(f"2) {os.path.basename(yol)} OKUNAMADI ({d:.1f} sn): {hata}")
            continue
        okunan, ilk, enyavas = sonuc
        hiz = okunan / 1e6 / d if d > 0 else 0
        yaz(f"2) {os.path.basename(yol)} baştan sona okuma: {d:.1f} sn  ({okunan / 1e6:.1f} MB, ortalama {hiz:.1f} MB/sn)")
        yaz(f"     ilk 1 MB: {ilk:.2f} sn   en yavaş 1 MB: {enyavas:.2f} sn")
        d2, sonuc2, hata2 = _olc(lambda y=yol: _dosya_oku(y, iptal))
        if not hata2 and d2 > 0:
            yaz(f"     ikinci okuma: {d2:.1f} sn  ({sonuc2[0] / 1e6 / d2:.1f} MB/sn)")
        if hiz and hiz < 5:
            yaz("     DEĞERLENDİRME: okuma çok yavaş (5 MB/sn altı). Açılıştaki bekleme büyük olasılıkla buradan.")
        elif ilk > 3:
            yaz("     DEĞERLENDİRME: dosya açılırken uzun bekliyor (ilk blok). Virüs koruması dosyayı açılışta tarıyor olabilir.")
    yaz("")

    # 3) küçük dosya yazma / silme
    if not durdu():
        deneme = os.path.join(klasor, f"_teshis_{os.getpid()}.tmp")

        def yaz_sil():
            with open(deneme, "wb") as f:
                f.write(b"x" * 65536)
                f.flush()
                os.fsync(f.fileno())
            os.remove(deneme)

        d, _, hata = _olc(yaz_sil)
        yaz(f"3) Deneme dosyası yaz + sil: {d:.2f} sn" + (f"   HATA: {hata}" if hata else ""))
        yaz("")

    # 4) veri tabanı
    if not dbler:
        yaz("4) Bu klasörde veri tabanı (.db) yok.")
    for yol, boy in dbler:
        if durdu():
            break
        ad = os.path.basename(yol)
        yaz(f"4) Veri tabanı: {ad}  ({boy / 1e6:.1f} MB)")
        for ek in ("-journal", "-wal", "-shm"):
            if os.path.exists(yol + ek):
                yaz(f"     UYARI: '{ad}{ek}' dosyası duruyor: yarım kalmış bir yazma ya da veri tabanını açık tutan başka bir program var.")
        d, sonuc, hata = _olc(lambda y=yol: _dosya_oku(y, iptal))
        if hata:
            yaz(f"     dosya okuma HATASI: {hata}")
        elif d > 0:
            yaz(f"     dosyayı baştan sona okuma: {d:.1f} sn  ({sonuc[0] / 1e6 / d:.1f} MB/sn)")
        con = None
        try:
            d, con, hata = _olc(lambda y=yol: sqlite3.connect(y, timeout=10))
            yaz(f"     bağlanma: {d:.2f} sn" + (f"   HATA: {hata}" if hata else ""))
            if con is not None:
                d, v, hata = _olc(lambda: con.execute("PRAGMA journal_mode").fetchone()[0])
                yaz(f"     günlük kipi: {v}  ({d:.2f} sn)" + (f"   HATA: {hata}" if hata else ""))
                d, v, hata = _olc(lambda: [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")])
                yaz(f"     tablo listesi: {d:.2f} sn" + (f"   HATA: {hata}" if hata else f"  ({len(v)} tablo)"))
                for tablo in (v or []):
                    if durdu():
                        break
                    d, n, hata = _olc(lambda t=tablo: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0])
                    if hata or d >= 0.5 or (n or 0) >= 1000:
                        yaz(f"     '{tablo}' satır sayımı: {d:.2f} sn" + (f"   HATA: {hata}" if hata else f"  ({n} satır)"))
                if "kayit" in (v or []):                 # kayıt sürelerinin dağılımı: çok uzun kayıtlar hesabı yavaşlatır
                    try:
                        sure = "(julianday(bitis) - julianday(baslangic))"
                        d, r, hata = _olc(lambda: con.execute(
                            f"SELECT COUNT(*), SUM({sure} > 1), SUM({sure} > 7), SUM({sure} > 30), SUM({sure} > 90), MAX({sure}), "
                            "MIN(baslangic), MAX(bitis) FROM kayit").fetchone())
                        if not hata and r and r[0]:
                            yaz(f"     KAYIT SÜRELERİ ({d:.2f} sn): toplam {r[0]} kayıt, {r[6]} – {r[7]}")
                            yaz(f"       1 günden uzun: {r[1] or 0}   1 haftadan uzun: {r[2] or 0}   30 günden uzun: {r[3] or 0}   "
                                f"90 günden uzun: {r[4] or 0}   en uzun: {r[5] or 0:.1f} gün")
                            if (r[2] or 0) > 200:
                                yaz("       DEĞERLENDİRME: bir haftadan uzun süren çok sayıda kayıt var. 1.0.46 ve öncesinde hesabı dakikalarca "
                                    "kilitleyen buydu (1.0.47 bunları yalnızca seçili günler kadar işler).")
                            for x in con.execute(f"SELECT makine, tip, baslangic, bitis, {sure} FROM kayit ORDER BY {sure} DESC LIMIT 10"):
                                yaz(f"       {x[0]:8} {x[2]} – {x[3]}  {x[4]:7.1f} gün  {x[1]}")
                            for x in con.execute(f"SELECT tip, COUNT(*), SUM({sure}) FROM kayit WHERE {sure} > 7 GROUP BY tip ORDER BY 2 DESC LIMIT 8"):
                                yaz(f"       1 haftadan uzun, tür '{x[0]}': {x[1]} kayıt, toplam {x[2]:.0f} gün")
                    except Exception as ex:  # noqa: BLE001
                        yaz(f"     kayıt süreleri okunamadı: {ex}")
                d, _, hata = _olc(lambda: (con.execute("BEGIN IMMEDIATE"), con.execute("ROLLBACK")))
                yaz(f"     yazma kilidi al + bırak: {d:.2f} sn" + (f"   HATA: {hata}" if hata else ""))
                if hata and "locked" in str(hata).lower():
                    yaz("     DEĞERLENDİRME: veri tabanı KİLİTLİ. Başka bir bilgisayarda program açık ve yazma yapıyor ya da takılı kalmış olabilir.")
                elif d > 3:
                    yaz("     DEĞERLENDİRME: kilit almak uzun sürüyor; ağ klasöründe dosya kilidi yavaş çalışıyor.")
        finally:
            if con is not None:
                try:
                    con.close()
                except Exception:  # noqa: BLE001
                    pass
        yaz("")

    # 5) bu bilgisayarın geçici klasörü (tek dosyalı exe her açılışta buraya açılır)
    if not durdu():
        import tempfile
        gecici = tempfile.gettempdir()
        deneme = os.path.join(gecici, f"_teshis_{os.getpid()}.tmp")

        def yerel():
            with open(deneme, "wb") as f:
                for _ in range(40):
                    f.write(b"\0" * (1 << 20))
                f.flush()
                os.fsync(f.fileno())
            os.remove(deneme)

        d, _, hata = _olc(yerel)
        yaz(f"5) Bu bilgisayarın geçici klasörüne 40 MB yaz + sil: {d:.1f} sn" + (f"   HATA: {hata}" if hata else ""))
        yaz(f"     ({gecici})")
        try:
            kalinti = [a for a in os.listdir(gecici) if a.startswith("_MEI")]
            if len(kalinti) > 1:
                yaz(f"     NOT: geçici klasörde {len(kalinti)} adet '_MEI…' kalıntısı var (düzgün kapanmamış eski açılışlar); silinebilir.")
        except OSError:
            pass
    yaz("")
    yaz("ÖLÇÜM DURDURULDU" if durdu() else "ÖLÇÜM BİTTİ")
    return "\n".join(s)
