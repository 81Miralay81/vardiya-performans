import json
import sqlite3
from datetime import date

from vardiya import personel_veri as pv


def _con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    pv.kur(con)
    return con


def test_hucre_gerceklesen():
    h = pv.hucre_coz("08:00-16:00<br>0800-1600 21<br>07:43 13:18<br>00:00-00:00<br>00:00+00:00<br>-17U162,green,0_2_59")
    assert h.gercek and h.plan == "08:00-16:00" and h.izin_kod == "21"
    assert (h.giris, h.cikis, h.g_dk, h.e_dk, h.renk) == ("07:43", "13:18", -17, 162, "green")
    h = pv.hucre_coz("Hafta Tatili 08<br>HT08<br>__:__ __:__<br>00:00-00:00<br>00:00+00:00<br>0U0,blue,0_2_59")
    assert h.giris == "" and h.cikis == "" and h.izin_kod == ""


def test_hucre_plan():
    h = pv.hucre_coz("?BY 08:00-18:00,white,-55_2_59")
    assert not h.gercek and h.plan == "BY 08:00-18:00"
    assert pv.hucre_coz(0) is None and pv.hucre_coz(None) is None


def test_plan_bilgi():
    assert pv.plan_bilgi("(CUMA) 08:00-16:00")[0] == "1"
    assert pv.plan_bilgi("16:00-24:00")[0] == "2"
    assert pv.plan_bilgi("24:00-08:00 Uzun Çalışma")[0] == "3"
    assert pv.plan_bilgi("BY 08:00-18:00")[0] == "G"
    assert pv.plan_bilgi("BY Cumartesi")[0] == "T"
    assert pv.plan_bilgi("Hafta Tatili 24")[0] == "T"


def _r(**k):
    r = dict(sicilid=1, gun="2026-10-05", plan="08:00-16:00", izin_kod="", giris="", cikis="", g_dk=0, e_dk=0, gercek=1)
    r.update(k)
    return r


def test_siniflandir():
    b = date(2026, 11, 20)
    g = pv.siniflandir(_r(giris="08:19", cikis="16:03", g_dk=19, e_dk=-3), b)
    assert g.durum == pv.GELDI and g.gec_dk == 19 and g.erken_dk == 0 and g.fazla_dk == 0
    g = pv.siniflandir(_r(giris="07:42", cikis="20:06", g_dk=-18, e_dk=-246), b)
    assert g.fazla_dk == 246 and g.gec_dk == 0
    g = pv.siniflandir(_r(giris="07:43", cikis="13:18", g_dk=-17, e_dk=162), b)
    assert g.erken_dk == 162
    assert pv.siniflandir(_r(), b).durum == pv.GELMEDI
    assert pv.siniflandir(_r(izin_kod="01"), b).durum == pv.IZIN_TAM
    g = pv.siniflandir(_r(izin_kod="21", giris="07:43", cikis="13:18", e_dk=162), b)
    assert g.durum == pv.IZIN_SAAT and g.erken_dk == 0          # izinli erken çıkış sayılmaz
    assert pv.siniflandir(_r(plan="Hafta Tatili 08"), b).durum == pv.TATIL
    g = pv.siniflandir(_r(plan="Hafta Tatili 08", giris="07:29", cikis="16:03"), b)
    assert g.durum == pv.TATIL_CALISTI and g.fazla_dk == 514
    assert pv.siniflandir(_r(giris="07:43"), b).durum == pv.EKSIK
    assert pv.siniflandir(_r(gun="2026-11-20"), b).durum == pv.PLAN          # bugün kesin değil
    assert pv.siniflandir(_r(giris="08:04", cikis="16:00", g_dk=4), b).gec_dk == 0     # 5 dk tolerans


def test_isle_ve_ozet():
    con = _con()
    satir = {"ysicilid": 7, "ysicilno": "123", "ypersonel": "DENEME KİŞİ", "ypozisyonad": "GRUP LİDERİ-KALIPHANE", "yyakaad": "MAVI YAKA",
             "ybolumad": "KALIPHANE",
             "y2026x10x05": "08:00-16:00<br>0800-1600<br>08:19 16:03<br>00:00-00:00<br>00:00+00:00<br>19U-3,white,0_2_59",
             "y2026x10x06": "08:00-16:00<br>0800-1600<br>__:__ __:__<br>00:00-00:00<br>00:00+00:00<br>0U0,orange,0_2_59",
             "y2026x10x07": "08:00-16:00<br>0800-1600 01<br>__:__ __:__<br>00:00-00:00<br>00:00+00:00<br>0U0,green,0_2_59",
             "yplanlanan": "24:00"}
    sayim = {"ysicilid": "m5", "ypersonel": "08:00-16:00", "y2026x10x05": 20}
    assert "1 kişi" in pv.isle(con, json.dumps([sayim, satir]))
    # yalnız plan yanıtı gerçekleşeni ezmez
    pv.isle(con, json.dumps([{"ysicilid": 7, "ypersonel": "DENEME KİŞİ", "y2026x10x05": "?BY 08:00-18:00,white,-55_2_59"}]))
    gl, oz = pv.donem_hesabi(con, date(2026, 10, 1), date(2026, 10, 31), bugun=date(2026, 11, 20))
    o = oz[7]
    assert (o.planli, o.geldi, o.gelmedi, o.izinli, o.gec_adet, o.gec_dk) == (3, 1, 1, 1, 1, 19)
    assert o.izin_tur == {"01": 1} and abs(o.devam - 0.5) < 1e-9
    assert pv.hafta_grup_liderleri(con, date(2026, 10, 5)) == {"1": ["DENEME KİŞİ"], "2": [], "3": [], "G": []}


def test_isle_filtre():
    con = _con()
    assert pv.isle(con, json.dumps([{"ID": 1, "AdSoyad": "X", "LoginName": "1"}])) is None      # tüm firma listesi
    assert pv.isle(con, json.dumps([{"deger": "AIzaXXXX", "islemsonuc": 1}])) is None
    assert pv.isle(con, "[]") is None and pv.isle(con, "bozuk") is None
    assert pv.isle(con, json.dumps([{"izinID": 3, "Aciklama": "Yıllık İzin", "Kod": "01"},
                                      {"izinID": 2, "Aciklama": "Raporlu Ödenmeyen", "Kod": "01"}])) == "2 izin türü"
    assert pv.izin_adlari(con)["01"] == "Raporlu Ödenmeyen / Yıllık İzin"
    # kişi ayrıntısı: listede olmayan kişi yazılmaz; olanın yalnız foto/telefonu alınır, adres saklanmaz
    ayr = [{"id": 9, "adsoyad": "A B", "sicilno": "5", "adres": "GİZLİ", "fotoimage": "x" * 200, "ceptelefon": "555"}]
    assert pv.isle(con, json.dumps(ayr)) is None
    con.execute("INSERT INTO pv_personel(sicilid, ad) VALUES(9, 'A B')")
    assert pv.isle(con, json.dumps(ayr))
    r = con.execute("SELECT * FROM pv_personel WHERE sicilid=9").fetchone()
    assert r["telefon"] == "555" and len(r["foto"]) == 200 and "GİZLİ" not in str(dict(r))
    b = [{"SicilID": 9, "Ad": "A", "Soyad": "B", "Hak": 18.0, "KullanilanYillikIzin": 2.0, "PlanlananIzin": 0, "IzinDevir": 45.0,
          "Kalan": 61.0, "Kidem": 4, "Yil": 2026, "GirisTarih": "2022-09-21T00:00:00"}]
    assert "kalan 61" in pv.isle(con, json.dumps(b))
    assert pv.bakiyeler(con)[9]["kalan"] == 61.0
