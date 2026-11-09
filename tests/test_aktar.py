import csv
from datetime import date, datetime

import openpyxl

from vardiya import veritabani as vt, ice_aktar as ia


def _xlsx(yol, satirlar, baslik=True):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sayfa1"
    if baslik:
        ws.append(["Makine Adı", "Operatör", "Tip", "İş Emri", "Ürün Adı", "Ürün Kodu", "Süre (saat)",
                   "Başlangıç Tarihi", "Bitiş Tarihi", "vardiya", "Statü", "gün", "sure"])
    for s in satirlar:
        ws.append(s)
    wb.save(yol)


def test_metin_tarih_hatali_satir_tekrar(tmp_path):
    f = tmp_path / "a.xlsx"
    _xlsx(f, [
        ["IM21", "A", "Çalışma", "1", "K", "DK1", 0.1, "03.11.2026 08:00:00", "03.11.2026 09:00:00", "2.Vardiya", "Çalışıyor", 3, 1],
        ["IM21", "A", "Kısa Duruş", "1", "K", "DK1", 0.1, "03.11.2026 09:00:00", "03.11.2026 09:10:00", "2.Vardiya", "Duruş", 3, "#DEĞER!"],
        ["IM22", "A", "Çalışma", "1", "K", "DK1", 0.1, "#DEĞER!", "03.11.2026 09:10:00", "", "", "", ""],
        ["IM22", "A", "Çalışma", "1", "K", "DK1", 0.1, datetime(2026, 11, 3, 8, 0), datetime(2026, 11, 3, 9, 30), "", "", "", ""],
        [None, None, None, None, None, None, None, None, None],
        ["IM23", "A", "Çalışma", "1", "K", "DK1", 0.1, "03.11.2026 10:00:00", "03.11.2026 09:00:00"],
    ])
    con = vt.ac(str(tmp_path / "t.db"))
    s = ia.aktar(con, str(f))
    assert (s.toplam, s.yeni, len(s.atlanan)) == (5, 3, 2)   # tarihi hatalı + bitişi başlangıçtan önce atlanır
    # aynı dosya tekrar: hiçbir şey çoğalmaz
    s2 = ia.aktar(con, str(f))
    assert (s2.yeni, s2.guncellenen, s2.ayni) == (0, 0, 3)
    assert con.execute("SELECT COUNT(*) FROM kayit").fetchone()[0] == 3
    assert "IM21" in vt.ayar_oku(con)["makineler"]


def test_acik_kayit_guncellenir(tmp_path):
    con = vt.ac(str(tmp_path / "t.db"))
    f1, f2 = tmp_path / "1.xlsx", tmp_path / "2.xlsx"
    _xlsx(f1, [["IM21", "A", "Çalışma", "1", "K", "D", 0, "03.11.2026 08:00:00", "03.11.2026 08:30:00"]])
    _xlsx(f2, [["IM21", "A", "Çalışma", "1", "K", "D", 0, "03.11.2026 08:00:00", "03.11.2026 09:30:00"]])
    ia.aktar(con, str(f1))
    s = ia.aktar(con, str(f2))
    assert (s.yeni, s.guncellenen) == (0, 1)
    assert con.execute("SELECT bitis FROM kayit").fetchone()[0].endswith("09:30:00")


def test_ayni_saniyede_iki_tip_korunur(tmp_path):
    con = vt.ac(str(tmp_path / "t.db"))
    f = tmp_path / "a.xlsx"
    _xlsx(f, [["IM21", "A", "YEMEK MOLASI", "1", "K", "D", 0, "03.11.2026 20:30:00", "03.11.2026 20:30:00"],
              ["IM21", "A", "Çalışma", "1", "K", "D", 0, "03.11.2026 20:30:00", "03.11.2026 21:30:00"]])
    s = ia.aktar(con, str(f))
    assert s.yeni == 2


def test_csv_ve_basliksiz_dosya_hatasi(tmp_path):
    f = tmp_path / "a.csv"
    with open(f, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Makine Adı", "Operatör", "Tip", "İş Emri", "Ürün Adı", "Ürün Kodu", "Süre (saat)", "Başlangıç Tarihi", "Bitiş Tarihi"])
        w.writerow(["IM21", "A", "Çalışma", "1", "K", "D", "0,1", "03.11.2026 08:00:00", "03.11.2026 09:00:00"])
    con = vt.ac(str(tmp_path / "t.db"))
    assert ia.aktar(con, str(f)).yeni == 1
    g = tmp_path / "b.xlsx"
    _xlsx(g, [["a", "b"]], baslik=False)
    try:
        ia.aktar(con, str(g))
        assert False
    except ValueError:
        pass


def test_eski_xls_ve_html(tmp_path):
    import pytest
    baslik = ["Makine Adı", "Operatör", "Tip", "İş Emri", "Ürün Adı", "Ürün Kodu", "Süre (saat)", "Başlangıç Tarihi", "Bitiş Tarihi"]
    satir = ["IM21", "A", "Çalışma", "1", "K", "DK1", 0.1, "03.11.2026 08:00:00", "03.11.2026 09:00:00"]
    # Cormind bazen .xls adıyla HTML tablo verir
    h = tmp_path / "b.xls"
    h.write_text("<html><body><table><tr>" + "".join(f"<th>{x}</th>" for x in baslik) + "</tr><tr>"
                 + "".join(f"<td>{x}</td>" for x in satir) + "</tr></table></body></html>", encoding="utf8")
    con = vt.ac(str(tmp_path / "h.db"))
    assert ia.aktar(con, str(h)).yeni == 1
    xlwt = pytest.importorskip("xlwt")
    wb = xlwt.Workbook()
    ws = wb.add_sheet("Sayfa1")
    for j, x in enumerate(baslik):
        ws.write(0, j, x)
    for j, x in enumerate(satir):
        ws.write(1, j, x)
    ws.write(2, 0, "IM22"); ws.write(2, 2, "Çalışma")
    ws.write(2, 7, datetime(2026, 11, 3, 8, 0), xlwt.easyxf(num_format_str="DD.MM.YYYY HH:MM:SS"))
    ws.write(2, 8, datetime(2026, 11, 3, 9, 0), xlwt.easyxf(num_format_str="DD.MM.YYYY HH:MM:SS"))
    f = tmp_path / "c.xls"
    wb.save(str(f))
    con2 = vt.ac(str(tmp_path / "x.db"))
    s = ia.aktar(con2, str(f))
    assert s.yeni == 2 and not s.atlanan
