from datetime import date, datetime

from vardiya import hatali_durus as hd, veritabani as vt
from vardiya.hesap import HesapAyar, hesapla


def _db(tmp_path):
    con = vt.ac(str(tmp_path / "t.db"))
    ek = [("IM1", "2026-11-25 08:00:00", "2026-11-25 12:00:00", "", "İŞ EMRİ PLAN YOK", "", "-"),          # olması gereken
          ("IM1", "2026-11-25 12:00:00", "2026-11-25 13:00:00", "Ali Veli", "İŞ EMRİ PLAN YOK", "54", "DK-1"),  # operatör var
          ("IM1", "2026-11-25 13:00:00", "2026-11-25 13:03:00", "", "İŞ EMRİ PLAN YOK", "54", "DK-1"),      # 3 dk: eşik altı
          ("IM1", "2026-11-25 13:03:00", "2026-11-25 14:00:00", "", "Çalışmıyor", "55", "CNC-MANUEL"),       # operatör yok, iş var
          ("IM1", "2026-11-25 14:00:00", "2026-11-25 16:00:00", "Ali Veli", "Çalışma", "55", "CNC-MANUEL")]
    con.executemany("INSERT INTO kayit(makine, baslangic, bitis, operator, tip, is_emri, urun_kodu) VALUES(?,?,?,?,?,?,?)", ek)
    con.commit()
    return con


def test_tespit_ve_esik(tmp_path):
    con = _db(tmp_path)
    ayar = {"hatali_durus_turleri": ["Çalışmıyor"], "operator_haric_durus": ["İŞ EMRİ PLAN YOK"], "hatali_durus_en_az_dk": 5}
    o = hd.tespit(con, date(2026, 11, 25), date(2026, 11, 25), ayar)
    assert [(x.tip, x.tur, round(x.saat * 60)) for x in o] == [("İŞ EMRİ PLAN YOK", "operator", 60), ("Çalışmıyor", "is", 57)]
    assert hd.operatore_gore(o) == [("Ali Veli", 1.0)] and hd.ise_gore(o)[0][0] == "CNC-MANUEL"
    assert hd.vardiyaya_gore(o)[1][1] > 1.9
    b = hd.zaman_bloklari(con, "IM1", date(2026, 11, 25), date(2026, 11, 25), o)["IM1"]
    assert [x[5] for x in b] == [False, True, False, True, False]      # 3 dk (eşik altı) vurgulanmaz
    assert hd.tespit(con, date(2026, 11, 25), date(2026, 11, 25), {}) == []


def test_haric_durus_isli_kisim_haric_tutulmaz(tmp_path):
    con = _db(tmp_path)
    vt.ayar_yaz(con, "operator_haric_durus", ["İŞ EMRİ PLAN YOK"])
    k = vt.kayitlari_getir(con, date(2026, 11, 25), date(2026, 11, 25))
    tipler = sorted({t for _m, t, _a, _b in k})
    assert "İŞ EMRİ PLAN YOK" in tipler and "İŞ EMRİ PLAN YOK" + vt.HATALI_EK in tipler
    s = hesapla(k, [date(2026, 11, 25)], HesapAyar(esik=0.01, haric=frozenset({"iş emri plan yok"})), {date(2026, 11, 25)})
    c, d, _m = s.hucreler["IM1"][2]
    assert d > 0                                                     # işli / operatörlü kısım duruş sayılır
    ham = vt.aralik_satirlari(con, "tip", date(2026, 11, 25), date(2026, 11, 25)).fetchall()
    assert all(not r[0].endswith(vt.HATALI_EK) for r in ham)          # Kayıtlar ekranı ham kalır
