from datetime import date, datetime

from vardiya.operator import operatorleri_hesapla


def t(h, m=0):
    return datetime(2026, 11, 9, h, m)


def test_cakisma_ve_setup_kaybi():
    A = "Ali Veli"
    k = [
        (A, "M1", "Çalışma", t(8), t(9)), (A, "M1", "SETUP", t(9), t(10)), (A, "M1", "Çalışma", t(10), t(12)),
        (A, "M2", "Çalışma", t(8), t(9, 30)), (A, "M2", "Kısa Duruş", t(9, 30), t(10, 30)), (A, "M2", "Çalışma", t(10, 30), t(12)),
        (A, "M3", "Çalışma", t(8), t(12)),
    ]
    r = operatorleri_hesapla(k, [date(2026, 11, 9)])[A]
    assert r.makine_sayisi == 3
    assert r.durus_sn == 7200 and r.setup_sn == 3600
    assert r.cakisan_sn == 1800                       # yalnız 09:30-10:00'da iki makine birlikte duruyor
    assert r.setup_kayip_sn == 1800                   # setup sırasında M2'de biriken duruş
    assert r.hepsi_calisirken_sn == 9000              # 08-09 ve 10:30-12:00
    assert len(r.cakismalar) == 1
    e = r.cakismalar[0]
    assert dict(e.duruslar) == {"M1": "SETUP", "M2": "Kısa Duruş"} and e.calisanlar == ("M3",) and e.setup_var
    assert r.durus_adedi == 2 and r.en_uzun_durus_sn == 3600
    assert r.aktif_sn == 4 * 3600 and abs(r.bosta_orani - 9000 / 14400) < 1e-9
    assert [(e.bas, e.bit) for e in r.bosta_listesi] == [(t(8), t(9)), (t(10, 30), t(12))]
    g = r.gunler[date(2026, 11, 9)]
    assert g["bosta_sn"] == 9000 and g["cakisan_sn"] == 1800


def test_tek_makine_durus_cakisma_sayilmaz():
    A = "Ali"
    k = [(A, "M1", "Kısa Duruş", t(8), t(9)), (A, "M2", "Çalışma", t(8), t(9)), (A, "M3", "Çalışma", t(8), t(9))]
    r = operatorleri_hesapla(k, [date(2026, 11, 9)])[A]
    assert r.cakisan_sn == 0 and r.hepsi_calisirken_sn == 0 and not r.cakismalar


def test_oranlar_gun_gun_ortalanir():
    A = "Ali"
    g1, g2 = date(2026, 11, 9), date(2026, 11, 10)
    # 1. gün: tüm vardiya çalışma (480 dk, net'in %109'u); 2. gün: yarım vardiya çalışma + yarım duruş
    k = [(A, "M1", "Çalışma", datetime(2026, 11, 9, 8), datetime(2026, 11, 9, 16)),
         (A, "M1", "Çalışma", datetime(2026, 11, 10, 8), datetime(2026, 11, 10, 12)),
         (A, "M1", "Kısa Duruş", datetime(2026, 11, 10, 12), datetime(2026, 11, 10, 16))]
    r = operatorleri_hesapla(k, [g1, g2])[A]
    net = 440 * 60
    assert abs(r.gunler[g2]["calisma"] - 4 * 3600 / net) < 1e-9
    assert abs(r.gunler[g2]["durus"] - 4 * 3600 / net) < 1e-9
    assert r.gun_sayisi == 2
    assert abs(r.durus_orani - (0 + 4 * 3600 / net) / 2) < 1e-9


def test_operatorsuz_kayit_atlanir_ve_secili_gun_disi():
    k = [("", "M1", "Çalışma", t(8), t(9)), ("A", "M1", "Çalışma", t(8), t(9))]
    assert list(operatorleri_hesapla(k, [date(2026, 11, 9)])) == ["A"]
    assert operatorleri_hesapla(k, [date(2026, 11, 8)]) == {}


def test_vardiya_suzgeci():
    A = "Ali"
    k = [(A, "M1", "Çalışma", t(6), t(7)), (A, "M1", "Kısa Duruş", t(9), t(10)), (A, "M1", "Çalışma", t(10), t(11))]
    g = [date(2026, 11, 9)]
    assert operatorleri_hesapla(k, g, vardiyalar={1})[A].durus_sn == 0
    assert operatorleri_hesapla(k, g, vardiyalar={2})[A].durus_sn == 3600
    assert A not in operatorleri_hesapla(k, g, vardiyalar={3})
