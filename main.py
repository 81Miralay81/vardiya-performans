"""Vardiya Performans — başlatıcı."""
import os
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from vardiya import tema
from vardiya.pencere import AnaPencere


def uygulama_klasoru() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def kendini_sina() -> int:
    """Derlenen exe'nin sağlam olup olmadığını denetler (ekran açmadan): tüm sayfalar, içe aktarma, PDF."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["VARDIYA_GUNCELLEME_YOK"] = "1"
    bayrak = "--disable-gpu" + (" --no-sandbox" if hasattr(os, "geteuid") and os.geteuid() == 0 else "")
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", bayrak)
    import tempfile
    import time
    from datetime import datetime, timedelta
    from openpyxl import Workbook
    app = QApplication(sys.argv)
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
    # web tabanlı Performans sayfası gerçekten çizdi mi
    perf = w.sayfalar["performans"]
    if perf.web is None:
        from vardiya.sayfa_performans import WEB_HATA
        print("HATA: web grafik bileşeni yüklenemedi:", WEB_HATA)
        return 4
    w.sayfa_ac("performans")
    durum = {}
    bitis = time.time() + 60
    while time.time() < bitis and not durum.get("tamam"):
        perf.web.page().runJavaScript(
            "JSON.stringify([window.__cizildi||0, document.querySelectorAll('canvas').length, (typeof V!=='undefined'&&V)?V.makineler.length:0])",
            lambda r: durum.update(son=r, tamam=bool(r) and __import__("json").loads(r)[0] >= 1 and __import__("json").loads(r)[1] >= 2 and __import__("json").loads(r)[2] >= 2))
        t = time.time() + 0.5
        while time.time() < t:
            app.processEvents()
            time.sleep(0.02)
    if not durum.get("tamam"):
        print("HATA: web grafik sayfası çizilmedi:", durum.get("son"))
        return 5
    print("WEB TAMAM", durum.get("son"))
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
    print("TAMAM", tema.yuzde(w.sonuc.genel[0]), len(pdf), "bayt PDF")
    return 0


def main() -> int:
    if "--kendini-sina" in sys.argv:
        return kendini_sina()
    app = QApplication(sys.argv)
    app.setApplicationName("Vardiya Performans")
    app.setStyleSheet(tema.STIL)
    app.setWindowIcon(QIcon(tema.kaynak_yolu("assets", "uygulama.ico")))
    # veri tabanı programın yanında durur (birden çok kişi aynı klasörden açabilir)
    yol = os.environ.get("VARDIYA_DB") or os.path.join(uygulama_klasoru(), "VardiyaPerformans.db")
    try:
        pencere = AnaPencere(yol)
    except Exception as ex:  # noqa: BLE001
        QMessageBox.critical(None, "Vardiya Performans", f"Veri tabanı açılamadı:\n{yol}\n\n{ex}")
        return 1
    pencere.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
