"""Excel dışa aktarma (tablo + özet)."""
from __future__ import annotations

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from .hesap import VARDIYALAR
from . import tema

METRIK = ("Çalışma", "Duruş", "Mola")
ALAN = ("calisma", "durus", "mola")


def excel_yaz(yol, sonuc, makineler, secim, seflar, ayar):
    wb = Workbook()
    ws = wb.active
    ws.title = METRIK[secim]
    kalin = Font(bold=True)
    lac = PatternFill("solid", fgColor="150958")
    beyaz = Font(bold=True, color="FFFFFF")
    ws.append([f"{METRIK[secim]} oranı  ·  {sonuc.gunler[0]:%d.%m.%Y} - {sonuc.gunler[-1]:%d.%m.%Y}  ·  eşik %{ayar['esik'] * 100:.0f}"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([])
    ws.append(["Vardiya", "Grup Lideri", "Makine (ort.)", METRIK[secim], "Ortalamaya giren gün"])
    for c in ws[3]:
        c.fill, c.font = lac, beyaz
    for v in VARDIYALAR:
        oz = sonuc.vardiyalar[v]
        d = getattr(oz, ALAN[secim])
        ws.append([f"{v}.Vardiya", seflar.get(v, ""), round(oz.makine_sayisi, 2) if oz.makine_sayisi is not None else None,
                   d, oz.gun_sayisi])
        ws.cell(ws.max_row, 4).number_format = "0.00%"
    ws.append(["Genel", "", "", sonuc.genel[secim], ""])
    ws.cell(ws.max_row, 4).number_format = "0.00%"
    for c in ws[ws.max_row]:
        c.font = kalin
    ws.append([])
    ws.append(["Makine", "ORTALAMA", "1.Vardiya", "2.Vardiya", "3.Vardiya"])
    bas = ws.max_row
    for c in ws[bas]:
        c.fill, c.font = lac, beyaz
    tum = list(makineler) + sorted(m for m in sonuc.hucreler if m not in makineler)
    for m in tum:
        ort = sonuc.makine_ort.get(m, (None, None, None))[secim]
        satir = [m, ort]
        for v in VARDIYALAR:
            h = sonuc.hucreler.get(m, {}).get(v)
            satir.append(h[secim] if h else None)
        ws.append(satir)
        for j in range(2, 6):
            ws.cell(ws.max_row, j).number_format = "0.00%"
    ws.column_dimensions["A"].width = 16
    for col in "BCDE":
        ws.column_dimensions[col].width = 20
    # kullanılan günler
    ws2 = wb.create_sheet("Günler")
    ws2.append(["Gün", "1.Vardiya makine", "2.Vardiya makine", "3.Vardiya makine"])
    for c in ws2[1]:
        c.fill, c.font = lac, beyaz
    for g in sonuc.gunler:
        ws2.append([g.strftime("%d.%m.%Y")] + [sonuc.vardiyalar[v].gunluk_sayilar.get(g, "yok") for v in VARDIYALAR])
    ws2.column_dimensions["A"].width = 14
    for col in "BCD":
        ws2.column_dimensions[col].width = 20
    wb.save(yol)
