import os
from datetime import date, datetime

import pytest

from vardiya import veritabani as vt, ice_aktar as ia
from vardiya.hesap import (HesapAyar, bol, statu_bul, vardiya_bul, topla, gunluk_hesapla, donem_hesapla, hesapla,
                           CALISIYOR, DURUS, MOLA)

ORNEK = os.environ.get("VARDIYA_ORNEK", "/tmp/claude-0/x/in/v.xlsm")


def dt(s):
    return datetime.strptime(s, "%d.%m.%Y %H:%M:%S")


# ----------------------------------------------------------------- küçük birim testleri
def test_statu():
    assert statu_bul("Çalışma") == CALISIYOR
    assert statu_bul("ÇAY MOLASI") == MOLA and statu_bul("Yemek Molası") == MOLA
    assert statu_bul("SETUP") == DURUS and statu_bul("Çalışmıyor") == DURUS


def test_vardiya():
    assert [vardiya_bul(h) for h in (0, 7, 8, 15, 16, 23)] == [1, 1, 2, 2, 3, 3]


def test_bolme_gece_yarisi_ve_sinir():
    p = bol(dt("03.11.2026 23:55:26"), dt("04.11.2026 00:00:51"))
    assert [(g.isoformat(), v, round(s)) for g, v, s in p] == [("2026-11-03", 3, 274), ("2026-11-04", 1, 51)]
    p = bol(dt("03.11.2026 15:58:00"), dt("03.11.2026 16:02:00"))
    assert [(v, s) for _, v, s in p] == [(2, 120.0), (3, 120.0)]
    # Excel usulu: tamamı başladığı vardiyaya
    p = bol(dt("03.11.2026 15:58:00"), dt("03.11.2026 16:02:00"), bolme=False)
    assert [(v, s) for _, v, s in p] == [(2, 240.0)]


def test_uzun_kayit_gunlere_dagilir():
    p = bol(dt("26.10.2026 10:00:00"), dt("28.10.2026 10:00:00"))
    assert abs(sum(s for _, _, s in p) - 48 * 3600) < 1e-6
    assert {g.isoformat() for g, _, _ in p} == {"2026-10-26", "2026-10-27", "2026-10-28"}


def test_cakisan_kayitlar_bir_kez_sayilir():
    a = HesapAyar()
    kay = [("IM1", "Çalışmıyor", dt("03.11.2026 10:00:00"), dt("03.11.2026 11:00:00")),
           ("IM1", "ÇAY MOLASI", dt("03.11.2026 10:00:00"), dt("03.11.2026 10:10:00")),
           ("IM1", "Kurulum", dt("03.11.2026 10:10:00"), dt("03.11.2026 11:00:00")),
           ("IM1", "Çalışma", dt("03.11.2026 10:50:00"), dt("03.11.2026 11:10:00"))]
    c, d, m = topla(kay, a)[(date(2026, 11, 3), 2)]["IM1"]
    assert (round(c * 60), round(d * 60), round(m * 60)) == (20, 40, 10)   # 11:10'a kadar toplam 70 dk
    # Excel usulünde aynı veri çift sayılırdı
    c, d, m = topla(kay, HesapAyar(cakisma_coz=False))[(date(2026, 11, 3), 2)]["IM1"]
    assert round(d * 60) == 110


def test_net_sure_ve_esik():
    a = HesapAyar()
    assert abs(a.net_saat - 7.3333333) < 1e-6 and abs(a.mola_saat - 2 / 3) < 1e-9
    # 7,33 saatin %60'ı = 4,4 saat: 4,5 saat çalışan geçerli, 4,3 saat çalışan geçersiz
    kay = [("IM1", "Çalışma", dt("03.11.2026 08:00:00"), dt("03.11.2026 12:30:00")),
           ("IM2", "Çalışma", dt("03.11.2026 08:00:00"), dt("03.11.2026 12:18:00"))]
    g = gunluk_hesapla(topla(kay, a), a)[(date(2026, 11, 3), 2)]
    assert g.sayi == 1 and "IM1" in g.makineler


def test_bos_vardiya_ortalamaya_girmez():
    a = HesapAyar()
    # 1. gün: 2. vardiyada 1 makine tam çalışmış; 2. gün hiç kayıt yok -> ortalama yalnızca 1. günden
    kay = [("IM1", "Çalışma", dt("03.11.2026 08:00:00"), dt("03.11.2026 15:20:00"))]
    s = hesapla(kay, [date(2026, 11, 3), date(2026, 11, 4)], a)
    assert s.vardiyalar[2].gun_sayisi == 1 and s.vardiyalar[2].makine_sayisi == 1
    assert date(2026, 11, 4) in s.verisiz_gunler
    assert s.vardiyalar[1].calisma is None


def test_haftalik_makine_sayisi_gunluk_ortalama():
    a = HesapAyar()
    kay = []
    # 1. gün: IM1 ve IM2 çalışıyor; 2. gün: IM3 ve IM4 ve IM5 çalışıyor -> farklı makineler, ortalama sayı 2,5
    for m in ("IM1", "IM2"):
        kay.append((m, "Çalışma", dt("03.11.2026 08:00:00"), dt("03.11.2026 15:20:00")))
    for m in ("IM3", "IM4", "IM5"):
        kay.append((m, "Çalışma", dt("04.11.2026 08:00:00"), dt("04.11.2026 15:20:00")))
    s = hesapla(kay, [date(2026, 11, 3), date(2026, 11, 4)], a)
    assert s.vardiyalar[2].makine_sayisi == 2.5
    assert len(s.hucreler) == 5  # dönem kuralıyla bu 5 makine elenirdi (her biri 1 günde)


# ----------------------------------------------------------------- Excel sonuçlarıyla karşılaştırma
@pytest.fixture(scope="module")
def kayitlar(tmp_path_factory):
    if not os.path.exists(ORNEK):
        pytest.skip("örnek Excel yok")
    con = vt.ac(str(tmp_path_factory.mktemp("db") / "t.db"))
    ia.aktar(con, ORNEK)
    return vt.kayitlari_getir(con, date(2026, 10, 1), date(2026, 11, 30))


GUN = date(2026, 11, 3)


def test_excel_03_11_calisma_birebir(kayitlar):
    """Excel (Sayfa2, gün=3): 87,97 / 94,52 / 84,69 ve genel 89,06; makine sayıları 12 / 9 / 10"""
    a = HesapAyar(bolme=False, cakisma_coz=False, net_saat_zorla=7.33)
    s = hesapla(kayitlar, [GUN], a)
    v = s.vardiyalar
    assert v[1].calisma == pytest.approx(0.87965916325602544, abs=1e-4)
    assert v[2].calisma == pytest.approx(0.94515154194667617, abs=1e-4)
    assert v[3].calisma == pytest.approx(0.84687077080491124, abs=1e-4)
    assert s.genel[0] == pytest.approx(0.89056049200253762, abs=1e-4)
    assert [v[i].makine_sayisi for i in (1, 2, 3)] == [12, 9, 10]
    # tek hücre: IM21 1. vardiya = %101,2469
    assert s.hucreler["IM21"][1][0] == pytest.approx(1.0124690010610886, abs=1e-4)
    assert s.makine_ort["IM21"][0] == pytest.approx(0.9445788742357637, abs=1e-4)


def test_excel_03_11_durus_ve_mola_siniflandirmasi(kayitlar):
    """Excel'in genel duruş / mola sayfalarındaki (eski paydalı) sonuçlar aynen yeniden üretilebiliyor:
    bu, Tip -> Statü sınıflandırmasının ve süre toplamlarının doğru olduğunu gösterir."""
    a = HesapAyar(bolme=False, cakisma_coz=False, net_saat_zorla=7.33)
    tp = topla(kayitlar, a)
    gv = gunluk_hesapla(tp, a)
    sayi = {v: gv[(GUN, v)].sayi for v in (1, 2, 3)}
    durus = {v: sum(m[1] for m in tp[(GUN, v)].values()) / 7.33 / sayi[v] for v in (1, 2, 3)}
    assert durus[1] == pytest.approx(0.31926801955434286, abs=1e-4)
    assert durus[2] == pytest.approx(0.29837560844154754, abs=1e-4)
    assert durus[3] == pytest.approx(0.3069285015916326, abs=1e-4)
    kap = {1: 0.67, 2: 0.67, 3: 0.64}
    mola = {v: sum(m[2] for m in tp[(GUN, v)].values()) / kap[v] / sayi[v] for v in (1, 2, 3)}
    assert mola[1] == pytest.approx(0.3379049543946932, abs=5e-4)
    assert mola[2] == pytest.approx(0.19038220932375155, abs=5e-4)
    assert mola[3] == pytest.approx(0.40438294270833336, abs=5e-4)


def test_bolme_acik_oldugunda_fark_cok_kucuk(kayitlar):
    s0 = hesapla(kayitlar, [GUN], HesapAyar(bolme=False, cakisma_coz=False, net_saat_zorla=7.33))
    s1 = hesapla(kayitlar, [GUN], HesapAyar(bolme=True, cakisma_coz=True, net_saat_zorla=7.33))
    for v in (1, 2, 3):
        assert abs(s0.vardiyalar[v].calisma - s1.vardiyalar[v].calisma) < 0.01


def test_durus_artik_asiri_yazmiyor(kayitlar):
    """Eski sistemde en uzun kayıt (119,5 sa) tek vardiyaya yazılıyordu; yeni sistemde hiçbir vardiyada
    bir makinenin toplam süresi vardiya uzunluğunu (8 sa) aşamaz."""
    a = HesapAyar()
    tp = topla(kayitlar, a)
    en_cok = max(sum(x) for gun_v in tp.values() for x in gun_v.values())
    assert en_cok <= 8.0 + 1e-6
    eski = max(sum(x) for gun_v in topla(kayitlar, HesapAyar(bolme=False, cakisma_coz=False)).values() for x in gun_v.values())
    assert eski > 8.0


def test_yalnizca_onceki_gunden_uzayan_kayit_gunu_kayitsiz_sayilir():
    a = HesapAyar()
    kay = [("IM1", "Çalışma", dt("03.11.2026 08:00:00"), dt("03.11.2026 15:20:00")),
           ("IM1", "Çalışmıyor", dt("03.11.2026 23:55:00"), dt("04.11.2026 00:10:00"))]
    s = hesapla(kay, [date(2026, 11, 3), date(2026, 11, 4)], a, veri_gunleri={date(2026, 11, 3)})
    assert s.verisiz_gunler == [date(2026, 11, 4)]
    assert all(g != date(2026, 11, 4) for g, _ in s.bos_vardiyalar)


def test_donem_kurali_makine_donem_boyunca_sayilir():
    from datetime import datetime, date
    from vardiya import hesap as h
    # IM1 iki gün %100, IM2 bir gün %100 bir gün 0 (dönem ort. %50 -> sayılmaz), IM3 bir gün %100 bir gün %30 (ort. %65 -> sayılır)
    def kayit(m, gun, saat):
        b = datetime(2026, 11, gun, 8, 0)
        return (m, "Çalışma", b, b.replace(hour=8, minute=0) + __import__("datetime").timedelta(hours=saat))
    k = [kayit("IM1", 2, 7.34), kayit("IM1", 3, 7.34), kayit("IM2", 2, 7.34), kayit("IM2", 3, 0.1),
         kayit("IM3", 2, 7.34), kayit("IM3", 3, 2.2), kayit("IM2", 3, 0.1)]
    gunler = [date(2026, 11, 2), date(2026, 11, 3)]
    gun = h.hesapla(k, gunler, h.HesapAyar(kural="gunluk"))
    don = h.hesapla(k, gunler, h.HesapAyar(kural="donem"))
    assert gun.vardiyalar[2].gunluk_sayilar == {date(2026, 11, 2): 3, date(2026, 11, 3): 1}
    assert "IM2" in gun.hucreler                            # günlük kuralda IM2 iyi günüyle sayılır
    assert don.vardiyalar[2].makine_sayisi == 2.0           # dönem kuralında IM1 ve IM3; IM2 ortalaması %50
    assert "IM2" not in don.hucreler
    assert abs(don.hucreler["IM3"][2][0] - (1.0 + 0.2998) / 2) < 5e-3


def test_ortalama_yontemleri():
    """2 gün: 1. gün 80/80/80, 2. gün 75/90/40 (eşik %60: 3. vardiya atılır)."""
    from datetime import date, datetime, timedelta
    from vardiya.hesap import HesapAyar, hesapla
    net = HesapAyar().net_saat
    kayit = []
    for gun, oranlar in ((3, (0.80, 0.80, 0.80)), (4, (0.75, 0.90, 0.40))):
        for v, o in enumerate(oranlar):
            b = datetime(2026, 11, gun, v * 8, 0)
            kayit.append(("IM21", "Çalışma", b, b + timedelta(hours=net * o)))
    gunler = [date(2026, 11, 3), date(2026, 11, 4)]
    def ort(y):
        return hesapla(kayit, gunler, HesapAyar(yontem=y)).makine_ort["IM21"][0]
    assert abs(ort("vardiya") - (0.775 + 0.85 + 0.80) / 3) < 1e-6
    assert abs(ort("gun") - (0.80 + 0.825) / 2) < 1e-6
    assert abs(ort("hucre") - (0.80 * 3 + 0.75 + 0.90) / 5) < 1e-6


def test_esik_alti_makine_gorunur_ama_sayilmaz():
    from datetime import date, datetime, timedelta
    from vardiya.hesap import HesapAyar, hesapla
    net = HesapAyar().net_saat
    b = datetime(2026, 11, 3, 8, 0)
    kayit = [("IM21", "Çalışma", b, b + timedelta(hours=net * 0.9)), ("IM22", "Çalışma", b, b + timedelta(hours=net * 0.4))]
    r = hesapla(kayit, [date(2026, 11, 3)], HesapAyar())
    assert "IM22" not in r.makine_ort and abs(r.esik_alti["IM22"][0] - 0.4) < 1e-6
    assert "IM21" not in r.esik_alti and abs(r.genel[0] - 0.9) < 1e-6
