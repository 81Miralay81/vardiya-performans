from datetime import date

from vardiya import cekim_kaydi as ck, veritabani as vt


def test_kayit_ve_saglik(tmp_path):
    con = vt.ac(str(tmp_path / "c.db"))
    s, oz = ck.cormind_sonucu({"toplam": 1819, "dogrulama": {"makine": 15, "oturum": 54, "is": 19, "hata": ""}})
    assert s == ck.TAMAM and "15 tezgâh" in oz
    ck.yaz(con, "Cormind · otomatik", date(2026, 11, 26), date(2026, 11, 26), s, oz, {"toplam": 1819})
    ck.yaz(con, "Personel · otomatik (sabah)", date(2026, 11, 26), date(2026, 11, 27),
           ck.personel_sonucu(True, "1/1 ay, personel 0/1 istek"), "personel 0/1 istek")
    l = ck.liste(con)
    assert len(l) == 2 and l[0]["sonuc"] == ck.EKSIK
    basliklar = [b for b, _d, _a in ck.saglik(con)]
    assert "Cormind" in basliklar and "Personel verisi" in basliklar
    assert ck.personel_sonucu(False, "x") == ck.HATA
    assert ck.cormind_sonucu({"toplam": 0})[0] == ck.EKSIK
