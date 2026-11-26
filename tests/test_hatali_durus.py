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


def test_eski_acik_kayit_hatali_sayilmaz(tmp_path):
    con = vt.ac(str(tmp_path / "e.db"))
    con.executemany("INSERT INTO kayit(makine, baslangic, bitis, operator, tip, is_emri, urun_kodu) VALUES(?,?,?,?,?,?,?)",
                    [("IM24", "2026-08-26 11:14:21", "2026-11-26 10:00:00", "Tuncay Ayvaz", "İŞ EMRİ PLAN YOK", "53", "ATS-MUHTELIF"),
                     ("IM85", "2026-11-25 07:40:46", "2026-11-26 03:00:00", "Sabit Efe", "İŞ EMRİ PLAN YOK", "54", "DK1167-5")])
    con.commit()
    ayar = {"operator_haric_durus": ["İŞ EMRİ PLAN YOK"]}
    o = hd.tespit(con, date(2026, 11, 25), date(2026, 11, 26), ayar)
    assert [(x.makine, x.bit.strftime("%d %H:%M")) for x in o] == [("IM85", "26 00:00")]   # IM24 eski; IM85 yalnızca açıldığı gün
    vt.ayar_yaz(con, "operator_haric_durus", ["İŞ EMRİ PLAN YOK"])
    tip = {m: t for m, t, _a, _b in vt.kayitlari_getir(con, date(2026, 11, 25), date(2026, 11, 25))}
    assert tip["IM24"] == "İŞ EMRİ PLAN YOK" and tip["IM85"].endswith(vt.HATALI_EK)


def test_gece_dogrulamasi_gercek_sureler(tmp_path):
    """Doğrulanan günde: kayıttaki operatör gerçekte çıkmışsa sayılmaz; iş atıldığı ana kadar sayılır."""
    con = _db(tmp_path)
    con.executemany("INSERT INTO cm_oturum (makine, operator, bas, bit) VALUES (?,?,?,?)",
                    [("IM1", "Ali Veli", "2026-11-25 11:50:00", "2026-11-25 12:20:00"),      # 12:20'de çıkmış
                     ("IM1", "Ayşe Kaya", "2026-11-25 09:00:00", "2026-11-25 09:30:00")])    # kayıtta yok ama makinede
    con.executemany("INSERT INTO cm_is_durum (gun, makine, is_emri, makinede, degisme, kontrol) VALUES (?,?,?,?,?,?)",
                    [("2026-11-25", "IM1", "54", 0, "2026-11-25 12:40:00", "x"),             # 12:40'ta atılmış
                     ("2026-11-25", "IM1", "55", 1, "2026-11-25 13:03:00", "x")])            # hâlâ makinede
    con.execute("INSERT INTO cm_dogrulama (gun, makine, zaman) VALUES ('2026-11-25', 'IM1', 'x')")
    con.commit()
    ayar = {"hatali_durus_turleri": ["Çalışmıyor"], "operator_haric_durus": ["İŞ EMRİ PLAN YOK"], "hatali_durus_en_az_dk": 5}
    o = hd.tespit(con, date(2026, 11, 25), date(2026, 11, 25), ayar)
    ozet = [(x.bas.strftime("%H:%M"), x.bit.strftime("%H:%M"), x.operator, x.tur, x.kaynak) for x in o]
    assert ozet == [("09:00", "09:30", "Ayşe Kaya", "operator", "gercek"),
                    ("11:50", "12:00", "Ali Veli", "operator", "gercek"),
                    ("12:00", "12:20", "Ali Veli", "operator", "gercek"),
                    ("12:20", "12:40", "", "is", "gercek"),
                    ("13:03", "14:00", "", "is", "gercek")]
    # doğrulama kapalıyken eski kural
    assert len(hd.tespit(con, date(2026, 11, 25), date(2026, 11, 25), ayar, dogrula=False)) == 2


def test_is_atilma_zamani_kesin_degil(tmp_path):
    con = _db(tmp_path)
    con.execute("INSERT INTO cm_is_durum VALUES ('2026-11-25', 'IM1', '55', 0, '2026-11-26 10:00:00', 'x')")   # başka yerde, sonra değişmiş
    con.execute("INSERT INTO cm_is_durum VALUES ('2026-11-25', 'IM1', '54', 0, '2026-11-25 11:00:00', 'x')")   # duruştan önce atılmış
    con.execute("INSERT INTO cm_dogrulama VALUES ('2026-11-25', 'IM1', 'x')")
    con.commit()
    ayar = {"hatali_durus_turleri": ["Çalışmıyor"], "operator_haric_durus": ["İŞ EMRİ PLAN YOK"]}
    o = hd.tespit(con, date(2026, 11, 25), date(2026, 11, 25), ayar)
    assert [(x.bas.strftime("%H:%M"), x.not_) for x in o] == [("13:03", "iş atılma zamanı kesin değil")]


def test_dogrulama_cek_yalniz_isaretli_tezgahlar(tmp_path, monkeypatch):
    from vardiya import cormind
    con = _db(tmp_path)
    con.execute("INSERT INTO kayit(makine, baslangic, bitis, operator, tip) VALUES ('IM2','2026-11-25 08:00:00','2026-11-25 10:00:00','','Çalışma')")
    con.commit()
    vt.ayar_yaz(con, "hatali_durus_turleri", ["Çalışmıyor"])
    sorulan = []

    class Sahte:
        def _graphql(self, model, kosul):
            sorulan.append((model, kosul["where"]))
            if model == "OperatorWork":
                return {"entities": [{"start": int(datetime(2026, 11, 25, 10, 0).timestamp() * 1000) - 3 * 3600 * 1000 + 3 * 3600 * 1000,
                                      "end": None, "operator": {"user": {"first_name": "Ali", "last_name": "Veli", "email": "x@y"}}}]}
            return {"entities": [{"code": "55", "current_machine_id": 7, "updated_at": "2026-11-25T10:03:00.000Z"}]}
    monkeypatch.setattr(cormind.time, "sleep", lambda s: None)
    r = cormind.dogrulama_cek(con, Sahte(), date(2026, 11, 25), date(2026, 11, 25), {"IM1": 7, "IM2": 8})
    assert r["makine"] == 1 and r["is"] == 1 and not r["hata"]
    assert all("8" not in w.split("=")[1][:3] for m, w in sorulan if m == "OperatorWork")       # IM2'ye sorgu yok
    assert con.execute("SELECT makinede FROM cm_is_durum WHERE is_emri='55'").fetchone()[0] == 1
    assert con.execute("SELECT operator FROM cm_oturum").fetchone()[0] == "Ali Veli"
    assert "email" not in str(con.execute("SELECT * FROM cm_oturum").fetchall())
