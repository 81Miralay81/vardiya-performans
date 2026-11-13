"""Vardiya Performans — başlatıcı."""
import os
import sys

from vardiya import teshis                     # her şeyden önce: açılış süreleri buradan ölçülür
from vardiya.surum import SURUM

_KAYITLI = "--kendini-sina" not in sys.argv
if _KAYITLI:
    teshis.baslat(SURUM)

from PySide6.QtGui import QIcon  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

if _KAYITLI:
    teshis.adim("ekran kütüphanesi (Qt) yüklendi")

from vardiya import web  # noqa: E402  (web'li exe'de web motoru uygulama nesnesinden önce yüklenmeli)
from vardiya import tema  # noqa: E402
from vardiya.pencere import AnaPencere  # noqa: E402

if _KAYITLI:
    teshis.adim("program modülleri yüklendi")


def uygulama_klasoru() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def kendini_sina() -> int:
    """Derlenen exe'nin sağlam olup olmadığını denetler (ekran açmadan): tüm sayfalar, içe aktarma, PDF."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["VARDIYA_GUNCELLEME_YOK"] = "1"
    import tempfile
    import time
    from datetime import datetime, timedelta
    from openpyxl import Workbook
    app = QApplication(sys.argv)
    web.kur()
    app.setStyleSheet(tema.STIL)
    klasor = tempfile.mkdtemp()
    w = AnaPencere(os.path.join(klasor, "deneme.db"))
    w.show()
    for a in w.sira:                                   # boş veri tabanıyla tüm sayfalar
        w.sayfa_ac(a)
        app.processEvents()
        w.grab()
    xl = os.path.join(klasor, "deneme.xlsx")
    wb = Workbook()
    ws = wb.active
    ws.append(["Makine Adı", "Operatör", "Tip", "İş Emri", "Ürün Adı", "Ürün Kodu", "Süre (saat)", "Başlangıç Tarihi", "Bitiş Tarihi"])
    for gun in (3, 4):
        for m in ("IM21", "IM22"):
            b = datetime(2026, 11, gun, 8, 0)
            ws.append([m, "A", "Çalışma", "1", "K", "D", 0, b.strftime("%d.%m.%Y %H:%M:%S"), (b + timedelta(hours=7, minutes=20)).strftime("%d.%m.%Y %H:%M:%S")])
    wb.save(xl)
    w.sayfalar["veri"].yukle([xl])
    for a in w.sira:
        w.sayfa_ac(a)
        app.processEvents()
        w.grab()
    if not w.sonuc or w.sonuc.genel[0] is None:
        print("HATA: hesap sonucu boş")
        return 2
    # Performans sayfası (programın kendi çizimi): tıklama bölgeleri oluşuyor ve ayrıntı açılıyor mu
    perf = w.sayfalar["performans"]
    w.sayfa_ac("performans")
    for _ in range(5):
        app.processEvents()
    perf.g_makine.grab()
    perf.tablo.grab()
    if not web.WEB_VAR and len(perf.g_makine.bolgeler) < 4:
        print("HATA: Performans grafiğinde tıklama bölgeleri oluşmadı:", len(perf.g_makine.bolgeler))
        return 4
    ilk = perf.g_makine.bolgeler[0][1] if perf.g_makine.bolgeler else next(iter(w.sonuc.makine_ort))
    perf._sec(ilk, "durus")
    perf.g_detay.grab()
    perf._sec(ilk, "mola")
    perf.g_detay.grab()
    perf.b_cormind.setChecked(True)
    app.processEvents()
    perf.g_oee.grab()
    perf.g_zaman.grab()
    print("PERFORMANS TAMAM", len(perf.g_makine.bolgeler), "bolge")
    from vardiya.sayfa_rapor import pdf_bayt
    w.sayfa_ac("rapor")
    w.sayfalar["rapor"]._yenile_simdi()
    pdf = pdf_bayt(w.sayfalar["rapor"]._r)
    if not pdf.startswith(b"%PDF"):
        print("HATA: PDF üretilemedi")
        return 3
    # idari rapor: KOT çözümleme ve 3 sayfalık PDF
    from vardiya import veritabani as vt
    from vardiya.kot import kot_coz
    vt.kot_yaz(w.con, kot_coz("=== KOT === KOT NO: 2026-1104-0900 TARIH: 04.11.2026 SAAT: 09:00 --- TEZGAHLAR --- "
                             "TEZGAH: IM21 | KATEGORI: SETUP | NEDEN: Deneme | ACIKLAMA: Deneme kaydı. | AKSIYON: - --- SONUC --- Deneme. DURUM: ACIK === SON ==="))
    rp = w.sayfalar["rapor"]
    rp.b_idari.click()
    rp._yenile_simdi()
    ipdf = pdf_bayt(rp._r)
    if rp._r.get("duzen") != "idari" or not rp._r["idari"]["kok"] or not ipdf.startswith(b"%PDF"):
        print("HATA: idari rapor üretilemedi")
        return 6
    print("IDARI TAMAM", len(ipdf), "bayt")
    if web.WEB_VAR:                                    # web'li exe: web motoru grafik çizebiliyor mu
        img = web.rapor_resmi_ciz("genel_performans_grafigi", dict(sonuc=w.sonuc, makineler=w.ayar.get("makineler", []),
                                                                   mola_pay=9.0, baslik="Deneme"), 1800, 800)
        if img is None or img.isNull():
            print("HATA: web grafiği çizilemedi")
            return 8
        print("WEB TAMAM", img.width(), "x", img.height())
    if sys.platform == "win32":                       # Outlook bağlantı kütüphanesi exe'ye girmiş mi (Outlook'un kendisi açılmaz)
        try:
            import win32com.client  # noqa: F401
            import win32timezone  # noqa: F401
            print("OUTLOOK KUTUPHANESI TAMAM")
        except Exception as ex:  # noqa: BLE001
            print("HATA: Outlook bağlantı kütüphanesi yok:", ex)
            return 7
    print("TAMAM", tema.yuzde(w.sonuc.genel[0]), len(pdf), "bayt PDF")
    return 0


def main() -> int:
    if "--kendini-sina" in sys.argv:
        return kendini_sina()
    if "--teshis" in sys.argv:                       # yalnızca teşhis penceresi (ana pencere ve veri tabanı açılmaz)
        app = QApplication(sys.argv)
        app.setStyleSheet(tema.STIL)
        from vardiya.teshis_pencere import TeshisPenceresi
        TeshisPenceresi().exec()
        return 0
    app = QApplication(sys.argv)
    web.kur()
    teshis.adim("uygulama nesnesi kuruldu" + (" (web grafikli)" if web.WEB_VAR else ""))
    app.setApplicationName("Vardiya Performans")
    app.setStyleSheet(tema.STIL)
    app.setWindowIcon(QIcon(tema.kaynak_yolu("assets", "uygulama.ico")))
    # veri tabanı programın yanında durur (birden çok kişi aynı klasörden açabilir)
    yol = os.environ.get("VARDIYA_DB") or os.path.join(uygulama_klasoru(), "VardiyaPerformans.db")
    try:
        pencere = AnaPencere(yol)
    except Exception as ex:  # noqa: BLE001
        teshis.adim(f"HATA: veri tabanı açılamadı: {ex}")
        QMessageBox.critical(None, "Vardiya Performans", f"Veri tabanı açılamadı:\n{yol}\n\n{ex}")
        return 1
    teshis.adim("ana pencere kuruldu")
    pencere.show()
    from PySide6.QtCore import QTimer
    nabiz = QTimer()
    nabiz.setInterval(500)
    nabiz.timeout.connect(teshis.nabiz)
    nabiz.start()
    teshis.bekci_baslat()
    QTimer.singleShot(0, lambda: teshis.adim("pencere ekranda, program kullanıma hazır"))
    kod = app.exec()
    teshis.adim("program kapatıldı")
    return kod


if __name__ == "__main__":
    sys.exit(main())
