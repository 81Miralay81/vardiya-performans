from datetime import date, datetime

from vardiya import veritabani as vt
from vardiya.oto_cekim import eksik_aralik, son_tam_gun


def _aktarim(con, zaman, ilk, son):
    con.execute("INSERT INTO aktarim(zaman, dosya, toplam, yeni, guncellenen, ayni, atlanan) VALUES(?,?,0,0,0,0,0)",
                (zaman, f"Cormind ({ilk}–{son})"))
    con.commit()


def test_bugun_cekilmez_ve_yarim_gun_yeniden_cekilir(tmp_path):
    con = vt.ac(str(tmp_path / "o.db"))
    _aktarim(con, "2026-11-19 08:27:00", "18.11.2026", "19.11.2026")    # 19.11 yarım, 18.11 tam
    assert son_tam_gun(con) == date(2026, 11, 18)
    assert eksik_aralik(con, date(2026, 11, 19)) is None                # bugün (19.11) çekilmez
    assert eksik_aralik(con, date(2026, 11, 20)) == (date(2026, 11, 19), date(2026, 11, 19))
    assert eksik_aralik(con, date(2026, 11, 23)) == (date(2026, 11, 19), date(2026, 11, 22))


def test_gece_yarisindan_hemen_sonra_cekilen_gun_tam_sayilmaz(tmp_path):
    con = vt.ac(str(tmp_path / "o2.db"))
    _aktarim(con, "2026-11-20 00:10:00", "19.11.2026", "19.11.2026")    # gün biteli 10 dk: kapanmamış kayıt olabilir
    assert son_tam_gun(con) is None or son_tam_gun(con) < date(2026, 11, 19)
    _aktarim(con, "2026-11-20 01:00:00", "19.11.2026", "19.11.2026")
    assert son_tam_gun(con) == date(2026, 11, 19)
    assert eksik_aralik(con, date(2026, 11, 20)) is None


def test_gecmis_yoksa_son_veri_gununden_baslar(tmp_path):
    con = vt.ac(str(tmp_path / "o3.db"))
    vt.kayit_yaz(con, [("IM21", datetime(2026, 11, 17, 8), datetime(2026, 11, 17, 9), "A", "Çalışma", "", "", "")])
    assert eksik_aralik(con, date(2026, 11, 19)) == (date(2026, 11, 17), date(2026, 11, 18))
