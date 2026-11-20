from datetime import date, datetime

from vardiya import veritabani as vt
from vardiya.kirilim import OPERATOR_YOK, durus_kirilimi, supheli_molalar, supheli_ozet

MS = {"2": {"yemek": ["12:30", "13:00"]}}


def d(h, m, s=0):
    return datetime(2026, 11, 18, h, m, s)


def test_duruştan_molaya_sonra_mola_saatinde_calisma_supheli():
    k = [("Ali", "IM21", "Kısa Duruş", d(12, 0), d(12, 30)),
         ("Ali", "IM21", "YEMEK MOLASI", d(12, 30), d(12, 36)),
         ("Ali", "IM21", "Çalışma", d(12, 36), d(13, 30))]
    e = supheli_molalar(k, [date(2026, 11, 18)], MS)
    assert len(e) == 1 and e[0].makine == "IM21" and e[0].vardiya == 2 and e[0].tur == "Yemek"
    assert e[0].sn == 24 * 60 and e[0].operator == "Ali"
    assert e[0].bloklar[0][0] == d(12, 0) and e[0].bloklar[-1][1] == d(13, 30)    # 30 dk öncesi ve sonrası
    oz = supheli_ozet(e, k, [date(2026, 11, 18)])
    assert oz["IM21"][2]["adet"] == 1 and round(oz["IM21"][2]["dk_gun"]) == 24


def test_calisan_makine_calismaya_devam_ederse_supheli_degil():
    k = [("Ali", "IM21", "Çalışma", d(12, 0), d(12, 30)),
         ("Ali", "IM21", "YEMEK MOLASI", d(12, 30), d(12, 30, 3)),     # birkaç saniyelik mola kaydı
         ("Ali", "IM21", "Çalışma", d(12, 30, 3), d(13, 30))]
    assert supheli_molalar(k, [date(2026, 11, 18)], MS) == []


def test_mola_saati_bittikten_sonra_calisma_supheli_degil():
    k = [("Ali", "IM21", "YEMEK MOLASI", d(12, 30), d(13, 0)),
         ("Ali", "IM21", "Çalışma", d(13, 0), d(13, 30))]
    assert supheli_molalar(k, [date(2026, 11, 18)], MS) == []
    assert supheli_molalar(k, [date(2026, 11, 18)], {}) == []        # mola saati yazılmamış: hiç aranmaz


def test_durus_kirilimi_vardiya_ve_operator(tmp_path):
    con = vt.ac(str(tmp_path / "k.db"))
    vt.kayit_yaz(con, [("IM21", d(7, 0), d(9, 0), "Ali Veli", "Kısa Duruş", "", "", ""),     # 1 sa 1. vardiya, 1 sa 2. vardiya
                       ("IM21", d(10, 0), d(10, 30), "", "Kısa Duruş", "", "", ""),           # operatörsüz
                       ("IM21", d(11, 0), d(12, 0), "Can", "Kurulum", "", "", "")])
    k = durus_kirilimi(con, date(2026, 11, 18), date(2026, 11, 18), "IM21", "Kısa Duruş")
    v = dict(k["vardiya"])
    assert round(v["1. Vardiya"], 2) == 1.0 and round(v["2. Vardiya"], 2) == 1.5 and v["3. Vardiya"] == 0
    o = dict(k["operator"])
    assert round(o["Ali Veli"], 2) == 1.0 and round(o[OPERATOR_YOK], 2) == 1.5    # 2. vardiyada Ali kayıt başlatmadı
    assert k["operator"][-1][0] == OPERATOR_YOK


def test_en_kisa_mola_altindaki_olay_sayilmaz():
    k = [("Ali", "IM21", "Kısa Duruş", d(12, 20), d(12, 30)),           # duruştayken mola saati geldi
         ("Ali", "IM21", "YEMEK MOLASI", d(12, 30), d(12, 30, 20)),     # 20 sn otomatik mola kaydı
         ("Ali", "IM21", "Çalışma", d(12, 30, 20), d(13, 30))]
    assert supheli_molalar(k, [date(2026, 11, 18)], MS, 2) == []          # 2 dk altı: sayılmaz
    assert len(supheli_molalar(k, [date(2026, 11, 18)], MS, 0)) == 1      # sınır 0: sayılır


def test_art_arda_mola_kayitlari_tek_mola_sayilir():
    k = [("Ali", "IM21", "ÇAY MOLASI", d(12, 30), d(12, 31, 30)),
         ("Ali", "IM21", "YEMEK MOLASI", d(12, 31, 30), d(12, 33)),
         ("Ali", "IM21", "Çalışma", d(12, 33), d(13, 30))]
    assert len(supheli_molalar(k, [date(2026, 11, 18)], MS, 2.5)) == 1    # 1,5 + 1,5 = 3 dk mola


def test_alt_sinir_calisma_suresine_de_uygulanir():
    k = [("Ali", "IM21", "YEMEK MOLASI", d(12, 30), d(12, 58, 30)),      # 28,5 dk gerçek mola
         ("Ali", "IM21", "Çalışma", d(12, 58, 30), d(13, 30))]          # mola bitimine 1,5 dk kala çalışma
    assert supheli_molalar(k, [date(2026, 11, 18)], MS, 2) == []          # 1,5 dk < 2 dk: sayılmaz
    assert len(supheli_molalar(k, [date(2026, 11, 18)], MS, 1)) == 1
