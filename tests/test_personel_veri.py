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
    assert pv.siniflandir(_r(giris="07:43"), b).durum == pv.GELDI      # tek okutma gelmiş sayılır
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


def test_turler_ve_cikis():
    con = _con()
    r = pv.tani_ve_kaydet(con, json.dumps([{"ysicilid": 7, "ypersonel": "X", "y2026x10x05": "08:00-16:00<br>0800-1600<br>08:00 16:00<br>a<br>b<br>0U0,white,0"},
                                           {"ysicilid": 8, "ypersonel": "Y", "y2026x10x31": 0}]))
    assert r["tur"] == "giris_cikis" and r["ilk"] == "2026-10-05" and r["son"] == "2026-10-31"
    assert pv.tani_ve_kaydet(con, json.dumps([{"ysicilid": 7, "ypersonel": "X", "y2026x10x05": "?BY 08:00-18:00,white,x"}]))["tur"] == "plan"
    liste = [{"id": 7, "adsoyad": "X", "sicilno": "1", "pozisyonad": "P", "mesaiperiyoduad": "TEC", "cikistarih": None},
             {"id": 9, "adsoyad": "Z", "sicilno": "3", "pozisyonad": "P", "mesaiperiyoduad": "TEC", "cikistarih": "2026-09-30T00:00:00"}]
    assert pv.tani_ve_kaydet(con, json.dumps(liste))["tur"] == "liste_hepsi"
    assert pv.tani_ve_kaydet(con, json.dumps(liste[1:]))["tur"] == "liste_cikan"
    assert pv.personel(con)[9]["cikis_tarih"] == "2026-09-30"
    assert pv.aktif_siciller(con) == [7, 8]
    b = pv.tani_ve_kaydet(con, json.dumps([{"SicilID": 7, "Ad": "X", "Soyad": "", "Hak": 1, "Kalan": 2, "GirisTarih": ""}]))
    assert b["tur"] == "bakiye" and b["sid"] == 7


def test_sablon_degistirme():
    u, ok = pv.tarih_degistir("a?bas=2026-10-01&bit=2026-10-31", date(2026, 10, 1), date(2026, 10, 31), date(2026, 2, 1), date(2026, 2, 28))
    assert ok and u == "a?bas=2026-02-01&bit=2026-02-28"
    u, ok = pv.tarih_degistir("a?x=1", date(2026, 10, 1), date(2026, 10, 31), date(2026, 2, 1), date(2026, 2, 28))
    assert not ok
    assert pv.kimlik_degistir("id=5729&k=15729", 5729, 1) == ("id=1&k=15729", True)
    assert len(pv.aylar(date(2026, 1, 1), date(2026, 11, 19))) == 11


def test_sablon_kasim_zinciri():
    # 31.10 -> 19.11 yazıldıktan sonra 'son+1' (01.11) yeniden değiştirilmemeli
    u, ok = pv.tarih_degistir('{"bas":"01.10.2026","bit":"31.10.2026"}', date(2026, 10, 1), date(2026, 10, 31), date(2026, 11, 1), date(2026, 11, 19))
    assert ok and u == '{"bas":"01.11.2026","bit":"19.11.2026"}'
    u, ok = pv.tarih_degistir("b=2026-10-01&e=2026-11-01", date(2026, 10, 1), date(2026, 10, 31), date(2026, 2, 1), date(2026, 2, 28))
    assert ok and u == "b=2026-02-01&e=2026-03-01"


def test_cekim_saati_hedef():
    from datetime import datetime
    from vardiya.oto_cekim import OtoCekim
    assert OtoCekim.pv_saat_coz("17:30") == (17, 30) and OtoCekim.pv_saat_coz("bozuk") == (20, 0)
    assert OtoCekim.pv_hedef(datetime(2026, 11, 23, 17, 29), (17, 30)) == date(2026, 11, 21)
    assert OtoCekim.pv_hedef(datetime(2026, 11, 23, 17, 30), (17, 30)) == date(2026, 11, 22)


def test_yetki_eski_kayit_acilir_yeni_kayit_aynen_kalir():
    import sqlite3
    from vardiya import kullanici as ku
    assert set(ku.etkin_yetkiler(["performans", "rapor"])) >= {"calisma", "durus", "mola", "gecmis", "excel", "grup_lideri"}
    assert ku.etkin_yetkiler(["performans", ku.SURUM_ISARET]) == ["performans"]
    assert ku.etkin_yetkiler([]) == []
    con = sqlite3.connect(":memory:"); con.row_factory = sqlite3.Row
    ku.kaydet(con, "yonet", "1234", [], True)
    ku.kaydet(con, "ali", "1234", ["personel_veri"], False)
    a = [u for u in ku.liste(con) if u["ad"] == "ali"][0]
    assert a["yetkiler"] == ["personel_veri"]
    assert ku.yetkili(a, "personel_veri") and not ku.yetkili(a, "veri") and not ku.yetkili(a, "excel")


def test_kart_ozeti_listeler_ve_cubuk_orani():
    from datetime import date
    from vardiya import personel_veri as pv
    g = [pv.Gun(1, date(2026, 11, 2), "0800-1600", "2", pv.GELDI, "08:10", "16:00", gec_dk=10),
         pv.Gun(1, date(2026, 11, 3), "0800-1600", "2", pv.GELMEDI),
         pv.Gun(1, date(2026, 11, 4), "", "", pv.IZIN_TAM, izin_kod="01"),
         pv.Gun(2, date(2026, 11, 2), "0800-1600", "2", pv.GELDI, "08:20", "16:00", gec_dk=20)]
    oz = pv.ozetle(g)
    v = pv.kart_ozeti([x for x in g if x.sicilid == 1], oz[1], oz, {"01": "Yıllık İzin"})
    assert [s["gun"] for s in v["listeler"]["gelmedi"]] == ["2026-11-03"]
    assert v["listeler"]["izin"][0]["aciklama"] == "Yıllık İzin"
    assert abs(v["cubuk"][0]["oran"] - 0.5) < 1e-9          # 10 dk geç, bölümde en çok 20 dk
    assert [k["deger"] for k in v["kutular"]] == [1, 1, 1, 1, 0]          # geldi, gelmedi, izin, geç, erken
    assert [s["gun"] for s in v["listeler"]["gec"]] == ["2026-11-02"]
    assert pv.kart_ozeti([], None, oz, {}) is None


def test_eksik_liste_kaydedilmez_ve_saatli_kayit_korunur():
    import sqlite3
    from vardiya import personel_veri as pv
    con = sqlite3.connect(":memory:"); con.row_factory = sqlite3.Row
    iyi = [{"ysicilid": 100 + i, "ysicilno": str(i), "ypersonel": f"K{i}", "ypozisyonad": "P",
            **{f"y2026x10x{g:02d}": "08:00-16:00<br>0800-1600<br>07:50 16:05<br>a<br>b<br>-10U-5,white,0" for g in range(1, 31)}}
           for i in range(3)]
    import json
    r = pv.tani_ve_kaydet(con, json.dumps(iyi))
    assert r["tur"] == "giris_cikis"
    bozuk = [{"ysicilid": 100 + i, "ysicilno": str(i), "ypersonel": f"K{i}", "ypozisyonad": "P",
              **{f"y2026x10x{g:02d}": "08:00-16:00<br>0800-1600 01,white,0" for g in range(1, 31)}} for i in range(3)]
    r = pv.tani_ve_kaydet(con, json.dumps(bozuk))          # iki satırlı (sınırı aşmış) hücreler gerçekleşen sayılmaz
    assert r["tur"] == "plan"
    bos = [{"ysicilid": 100 + i, "ysicilno": str(i), "ypersonel": f"K{i}", "ypozisyonad": "P",
            **{f"y2026x10x{g:02d}": "08:00-16:00<br>0800-1600<br><br>-0U0,green,0" for g in range(1, 31)}} for i in range(3)]
    r = pv.tani_ve_kaydet(con, json.dumps(bos))            # saatsiz gerçekleşen liste: eksik, kaydedilmez
    assert r["tur"] == "eksik_liste"
    assert con.execute("SELECT giris FROM pv_gun WHERE sicilid=100 AND gun='2026-10-05'").fetchone()[0] == "07:50"
    # tek tük saatsiz hücre (ör. gerçekten izinli gün) eski saatli kaydı silmez
    tek = [{"ysicilid": 100, "ysicilno": "0", "ypersonel": "K0", "ypozisyonad": "P", "y2026x10x05": "08:00-16:00<br>0800-1600 01<br>,white,0"}]
    pv.tani_ve_kaydet(con, json.dumps(tek))
    assert con.execute("SELECT giris FROM pv_gun WHERE sicilid=100 AND gun='2026-10-05'").fetchone()[0] == "07:50"


def test_iki_vakit_otomatik_plan():
    from datetime import datetime
    from vardiya.oto_cekim import OtoCekim
    p = lambda s, ss=None, sa=None, st=date(2026, 11, 22): OtoCekim.pv_plan(s, (8, 29), (20, 0), ss, sa, st, date(2026, 7, 1))  # noqa: E731
    assert p(datetime(2026, 11, 24, 8, 0)) is None
    assert p(datetime(2026, 11, 24, 8, 30)) == ("sabah", date(2026, 11, 23), date(2026, 11, 24))
    assert p(datetime(2026, 11, 24, 12, 0), ss=date(2026, 11, 24)) is None
    assert p(datetime(2026, 11, 24, 20, 0), ss=date(2026, 11, 24)) == ("aksam", date(2026, 11, 23), date(2026, 11, 23))
    assert p(datetime(2026, 11, 24, 21, 0), ss=date(2026, 11, 24), sa=date(2026, 11, 24)) is None
    # program birkaç gün kapalı kaldıysa arada kalan günler de çekilir, 01.07.2026'dan eskiye gidilmez
    assert p(datetime(2026, 11, 24, 9, 0), st=date(2026, 11, 19))[1] == date(2026, 11, 20)
    assert p(datetime(2026, 7, 3, 9, 0), st=None)[1] == date(2026, 7, 1)
