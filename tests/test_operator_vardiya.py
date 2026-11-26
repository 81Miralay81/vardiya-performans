import sqlite3
from datetime import date, datetime

from vardiya import operator_vardiya as ov, personel_veri as pv


def _con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    pv.kur(con)
    con.execute("INSERT INTO pv_personel(sicilid, sicilno, ad) VALUES(1,'100','AHMET YILMAZ'),(2,'200','MEHMET KAYA')")
    for g in ("2026-11-24", "2026-11-25"):
        con.execute("INSERT INTO pv_gun(sicilid, gun, plan, gercek) VALUES(1,?,'08:00-16:00',1)", (g,))
        con.execute("INSERT INTO pv_gun(sicilid, gun, plan, gercek) VALUES(2,?,'24:00-08:00',1)", (g,))
    return con


def test_kendi_vardiyasi_mesai_ve_disari():
    con = _con()
    t = lambda h, m=0, d=24: datetime(2026, 11, d, h, m)  # noqa: E731
    kayit = [("Ahmet Yılmaz", "IM1", "ÇALIŞIYOR", t(8), t(16)),             # kendi vardiyası
             ("ahmet yilmaz", "IM1", "ÇALIŞIYOR", t(16, 0, 25), t(16, 10, 25)),  # 10 dk taşma: yarım saat esneme içinde -> kendi
             ("Ahmet Yılmaz", "IM6", "ÇALIŞIYOR", t(7, 35, 25), t(8, 0, 25)),    # 25 dk erken giriş: esneme içinde -> kendi
             ("Ahmet Yılmaz", "IM2", "ÇALIŞIYOR", t(17), t(19)),            # 2 sa başka vardiya -> mesai
             ("Mehmet Kaya", "IM3", "ÇALIŞIYOR", t(0, 0, 25), t(8, 0, 25)),  # 24-08 (24.11 planı) -> 25.11 00-08 kendi
             ("Veli Dış", "IM4", "ÇALIŞIYOR", t(9), t(10)),                  # personel listesinde yok
             ("", "IM5", "ÇALIŞIYOR", t(9), t(10))]
    s = ov.vardiyaya_bagla(kayit, ov.Eslestirici(con, date(2026, 11, 24), date(2026, 11, 25), {"pv_fazla_en_az_dk": 30}))
    ops = [(r[0], r[1], r[3].hour) for r in s]
    assert ("Ahmet Yılmaz", "IM1", 8) in ops
    assert ("ahmet yilmaz", "IM1", 16) in ops                                  # 25.11'deki 10 dk (esneme içinde)
    assert ("Ahmet Yılmaz", "IM6", 7) in ops                                   # yarım saat önce giriş mesai değil
    assert ("Ahmet Yılmaz (mesai)", "IM2", 17) in ops
    assert ("Mehmet Kaya", "IM3", 0) in ops
    assert ("Veli Dış (kalıphane dışı)", "IM4", 9) in ops
    assert ov.temel_ad("Ahmet Yılmaz (mesai)") == "Ahmet Yılmaz"


def test_esneme_disi_mesai():
    con = _con()
    t = lambda h, m=0: datetime(2026, 11, 24, h, m)  # noqa: E731
    kayit = [("Ahmet Yılmaz", "IM1", "ÇALIŞIYOR", t(8), t(17))]                 # 16:30'dan sonrası esneme dışı -> mesai
    s = ov.vardiyaya_bagla(kayit, ov.Eslestirici(con, date(2026, 11, 24), date(2026, 11, 24), {"pv_fazla_en_az_dk": 30}))
    assert [(r[0], r[3].strftime("%H:%M"), r[4].strftime("%H:%M")) for r in s if r[0].endswith("(mesai)")] == [("Ahmet Yılmaz (mesai)", "16:30", "17:00")]


def test_kayan_cikis_onceki_gune_tasinir():
    satir = [{"sicilid": 1, "gun": "2026-11-25", "plan": "16:00-24:00", "giris": None, "cikis": None, "e_dk": 0, "gercek": 1},
             {"sicilid": 1, "gun": "2026-11-26", "plan": "16:00-24:00", "giris": None, "cikis": "00:06", "e_dk": 1434, "gercek": 1}]
    pv.kayan_cikislari_duzelt(satir)
    assert satir[0]["cikis"] == "00:06" and satir[0]["e_dk"] == -6 and satir[1]["cikis"] is None and satir[1]["e_dk"] == 0
    g = pv.siniflandir(satir[0], date(2026, 11, 27))
    assert g.durum == pv.GELDI and g.fazla_dk == 0 and g.erken_dk == 0
    s2 = [{"sicilid": 1, "gun": "2026-11-25", "plan": "24:00-08:00", "giris": "23:55", "cikis": "08:02", "gercek": 1},
          {"sicilid": 1, "gun": "2026-11-26", "plan": "00:00-08:00", "giris": None, "cikis": "03:00", "gercek": 1}]
    pv.kayan_cikislari_duzelt(s2)
    assert s2[1]["cikis"] == "03:00"                                           # önceki gün gece yarısı bitmiyor: dokunma


def test_elle_eslestirme_ve_veri_olmayan_gun():
    con = _con()
    es = ov.Eslestirici(con, date(2026, 11, 24), date(2026, 11, 25), {"op_eslestirme": {"A. YILMAZ": "1", "Başka Biri": ""}})
    assert es.sicil("a. yılmaz") == 1 and es.sicil("Başka Biri") == -1
    k = [("Ahmet Yılmaz", "IM1", "ÇALIŞIYOR", datetime(2026, 6, 1, 20), datetime(2026, 6, 1, 22))]
    assert ov.vardiyaya_bagla(k, es)[0][0] == "Ahmet Yılmaz"                 # personel verisi olmayan gün: dokunulmaz


def test_cnc_liderleri_mekanik_haric_ve_vardiya_eslemesi():
    con = _con()
    con.execute("INSERT INTO pv_personel(sicilid, sicilno, ad, pozisyon) VALUES(3,'300','GÜRYAY GÜNDÜZALP','Grup Lideri-Kalıphane'),"
                "(4,'400','BÜLENT GÜNGÖR','Grup Lideri-Kalıphane')")
    con.execute("INSERT INTO pv_gun(sicilid, gun, plan, gercek) VALUES(3,'2026-11-24','08:00-16:00',1),(4,'2026-11-24','24:00-08:00',1)")
    d = pv.cnc_liderleri(con, [date(2026, 11, 24), date(2026, 11, 25)], {})
    assert d[(date(2026, 11, 24), 2)] == ["Güryay Gündüzalp"]
    assert d[(date(2026, 11, 25), 1)] == ["Bülent Güngör"]                    # 24–08 ertesi günün 1. vardiyası
    d = pv.cnc_liderleri(con, [date(2026, 11, 24)], {"pv_lider_tur": {"3": "Mekanik"}})
    assert (date(2026, 11, 24), 2) not in d                                    # mekanik lider Performans'ta yok


def test_tek_okutma_uyarisi():
    r = {"sicilid": 1, "gun": "2026-11-25", "plan": "16:00-24:00", "giris": None, "cikis": "00:06", "e_dk": -6, "gercek": 1}
    g = pv.siniflandir(r, date(2026, 11, 27))
    assert pv.okutma_eksik(g) == "giriş" and pv.okutma_yazi(g) == "⚠ girişte kart okutulmamış"
    m, renk = pv.gun_yazi(g, {}, date(2026, 11, 27))
    assert "giriş okutulmadı" in m and renk == pv.RENK["okutma"]
    assert "kontrol edin" in pv.gun_ipucu(g, {})
    assert pv.ozetle([g])[1].okutma == 1
    g2 = pv.siniflandir(dict(r, giris="15:50"), date(2026, 11, 27))
    assert pv.okutma_eksik(g2) == "" and pv.ozetle([g2])[1].okutma == 0
