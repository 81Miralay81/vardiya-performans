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


def test_is_emri_plan_yok_takibi():
    A = "Ali"
    k = [(A, "M1", "Çalışma", t(8), t(9)), (A, "M1", "İŞ EMRİ PLAN YOK", t(9), t(11)), (A, "M2", "iş emri plan yok", t(9), t(10))]
    r = operatorleri_hesapla(k, [date(2026, 11, 9)])[A]
    assert r.plansiz_sn == 3 * 3600
    assert sorted((e.duruslar[0][0], e.sn) for e in r.plansiz_listesi) == [("M1", 7200), ("M2", 3600)]


def test_haric_tutulan_durus_hesaptan_cikar():
    A = "Ali"
    # 08-12 çalışma, 12-16 "İŞ EMRİ PLAN YOK": hariç tutulunca oranlar yalnız çalışılan süreye göre çıkar
    k = [(A, "M1", "Çalışma", t(8), t(12)), (A, "M1", "İŞ EMRİ PLAN YOK", t(12), t(16))]
    g = [date(2026, 11, 9)]
    r0 = operatorleri_hesapla(k, g)[A]
    r1 = operatorleri_hesapla(k, g, haric_duruslar=["iş emri plan yok"])[A]
    net = 440 * 60
    assert abs(r0.durus_orani - 4 * 3600 / net) < 1e-9
    assert r1.durus_sn == 0 and r1.durus_orani == 0
    assert r1.haric_sn == 4 * 3600 and r1.haric_tipleri == {"İŞ EMRİ PLAN YOK": 4 * 3600}
    assert abs(r1.gunler[g[0]]["calisma"] - 4 * 3600 / (net * 0.5)) < 1e-9     # pay yarıya düştü (dönem değeri %100'de kesilir)
    assert r1.plansiz_sn == 4 * 3600                                  # hariç olsa da izlenir
    # yalnızca hariç tutulan süreden oluşan operatör listeden düşer
    assert operatorleri_hesapla([(A, "M1", "İŞ EMRİ PLAN YOK", t(8), t(16))], g, haric_duruslar=["İŞ EMRİ PLAN YOK"]) == {}


def test_haric_durus_cakisma_ve_bosta_saymaz():
    A = "Ali"
    k = [(A, "M1", "Çalışma", t(8), t(10)), (A, "M2", "Çalışma", t(8), t(10)),
         (A, "M3", "İŞ EMRİ PLAN YOK", t(8), t(10))]
    g = [date(2026, 11, 9)]
    assert operatorleri_hesapla(k, g)[A].hepsi_calisirken_sn == 0            # M3 duruşta: boşta değil
    r = operatorleri_hesapla(k, g, haric_duruslar=["İŞ EMRİ PLAN YOK"])[A]
    assert r.hepsi_calisirken_sn == 7200                                       # M3 hesap dışı: M1+M2 çalışıyor


def test_grafik_verisi():
    from datetime import date as _d
    from vardiya.operator import OperatorSonuc
    from vardiya.operator_grafik import METRIK, gun_veri, toplu_veri
    def r(ad, c, d):
        o = OperatorSonuc(ad)
        o.calisma_orani, o.durus_orani = c, d
        o.gunler[_d(2026, 11, 2)] = {"calisma": c, "durus": d, "mola": 0.2, "birim": 1}
        o.gunler[_d(2026, 11, 3)] = {"calisma": c / 2, "durus": d, "mola": 0.2, "birim": 1}
        return o
    sonuc = {"A": r("A", 0.5, 0.3), "B": r("B", 0.9, 0.1)}
    liste, genel = toplu_veri(sonuc, METRIK["calisma"])
    assert [a for a, _ in liste] == ["B", "A"] and abs(genel - 0.7) < 1e-9
    gunler, ort = gun_veri(sonuc["A"], METRIK["calisma"])
    assert [round(v, 2) for _, v in gunler] == [0.5, 0.25] and abs(ort - 0.375) < 1e-9
    assert gun_veri(sonuc["A"], METRIK["ayar"]) is None
