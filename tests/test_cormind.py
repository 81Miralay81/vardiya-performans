import json
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

from vardiya import cormind, veritabani as vt


def _kayit(i, makine, tip, et, bas, bit):
    return {"id": i, "machine_id": 9, "operator_id": 82, "type": tip, "entity_type": et,
            "started_at": bas, "ended_at": bit, "machine": {"id": 9, "name": makine},
            "operator": {"user": {"first_name": "Ali", "last_name": "Veli"}},
            "goods": {"code": "54524896", "extra": {"erp": {"DESCRIPTION": "KALIP", "PART_NO": "DK1"}}}}


VERI = [
    _kayit(1, "IM21", 0, None, "2026-11-09T05:00:00.000Z", "2026-11-09T05:30:00.500Z"),   # 08:00-08:30 TR
    _kayit(2, "IM21", 1, 7, "2026-11-09T05:30:00.500Z", "2026-11-09T05:40:00.000Z"),
    _kayit(3, "IM22", 1, None, "2026-11-09T06:00:00.000Z", "2026-11-09T06:10:00.000Z"),
    _kayit(4, "IM22", 0, None, "2026-11-09T06:10:00.000Z", None),                            # sürüyor: şimdiye kadar sayılır
]


class Sahte(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _yaz(self, d, cerez=False):
        b = json.dumps(d).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        if cerez:
            self.send_header("Set-Cookie", "panel=abc; Path=/; HttpOnly")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        govde = self.rfile.read(n).decode()
        if self.path == "/panel/login":
            f = parse_qs(govde)
            if f.get("username") == ["u"] and f.get("password") == ["p"] and f.get("react") == ["true"]:
                return self._yaz({"ok": True}, cerez=True)
            return self._yaz({"ok": False})
        if self.path.startswith("/panel/api/graphql"):
            if "panel=abc" not in (self.headers.get("Cookie") or ""):
                return self._yaz({"errors": [{"message": "yetkisiz"}]})
            q = json.loads(govde)["variables"]
            if q["model"] == "FailureType":
                return self._yaz({"data": {"entities": [{"id": 7, "name": "ÇAY MOLASI"}], "count": 1}})
            c = q["condition"]
            assert "2026-11-09T00:00:00+03:00" in c["where"] and "IN (5,6)" in c["where"]
            if "ended_at" in c["where"]:                # döneme uzanan eski kayıt sorgusu: bu örnekte yok
                assert "2026-11-09T00:00:00+03:00" in c["where"]
                return self._yaz({"data": {"entities": [], "count": 0}})
            parca = VERI[c["offset"]:c["offset"] + c["limit"]]
            return self._yaz({"data": {"entities": parca, "count": len(VERI)}})
        self.send_response(404)
        self.end_headers()


def _sunucu():
    s = HTTPServer(("127.0.0.1", 0), Sahte)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, f"http://127.0.0.1:{s.server_port}"


def test_zaman_turkiye_saatine_cevrilir():
    assert cormind.tr_zaman("2026-11-09T21:30:00.900Z").isoformat() == "2026-11-10T00:30:00"


def test_cek_yazar_ve_tekrarda_cogalmaz(tmp_path):
    s, adres = _sunucu()
    try:
        con = vt.ac(str(tmp_path / "c.db"))
        r = cormind.cek(con, adres, "u", "p", date(2026, 11, 9), date(2026, 11, 9), [5, 6])
        assert (r["toplam"], r["yeni"], r["atlanan"]) == (4, 4, 0)
        assert r["tipler"] == {"Çalışma": 2, "ÇAY MOLASI": 1, "Belgelenmemiş Duruş": 1} and not r["dar_sorgu"]
        satir = con.execute("SELECT * FROM kayit WHERE makine='IM21' AND tip='Çalışma'").fetchone()
        assert satir["baslangic"] == "2026-11-09 08:00:00" and satir["operator"] == "Ali Veli"
        assert satir["is_emri"] == "54524896" and satir["urun_kodu"] == "DK1"
        r2 = cormind.cek(con, adres, "u", "p", date(2026, 11, 9), date(2026, 11, 9), [5, 6])
        assert (r2["yeni"], r2["silinen"]) == (4, 4)           # aynı günler silinip yeniden yazılır, çoğalmaz
        assert con.execute("SELECT COUNT(*) FROM kayit").fetchone()[0] == 4
    finally:
        s.shutdown()


def test_sabit_tipler():
    adlar = {7: "Kısa Duruş"}
    assert cormind.tip_adi({"type": 105}, adlar) == "YEMEK MOLASI"
    assert cormind.tip_adi({"type": 106}, adlar) == "ÇAY MOLASI"
    assert cormind.tip_adi({"type": 1, "entity_type": 7}, adlar) == "Kısa Duruş"
    assert cormind.tip_adi({"type": 1, "entity_type": 9}, adlar) == "Arıza 9"
    assert cormind.tip_adi({"type": 1}, adlar) == "Belgelenmemiş Duruş"
    assert cormind.tip_adi({"type": -1}, adlar) == "Çalışmıyor"


def test_yanlis_sifre(tmp_path):
    import pytest
    s, adres = _sunucu()
    try:
        with pytest.raises(cormind.CormindHata):
            cormind.Istemci(adres).giris("u", "yanlis")
    finally:
        s.shutdown()


def test_calismiyor_nedenli_ve_suren_kayit():
    """Çalışmıyor (-1) durumuna neden girilmişse nedenin adı kullanılır; süren kayıt 'şimdi'ye kadar sayılır."""
    from datetime import datetime
    adlar = {12: "İŞ EMRİ PLAN YOK"}
    assert cormind.tip_adi({"type": -1, "entity_type": 12}, adlar) == "İŞ EMRİ PLAN YOK"
    assert cormind.tip_adi({"type": -1, "entity_type": None}, adlar) == "Çalışmıyor"
    assert cormind.tip_adi({"type": -1, "entity_type": 99}, adlar) == "Çalışmıyor"
    k = {"type": -1, "entity_type": 12, "started_at": "2026-10-20T05:00:00.000Z", "ended_at": None, "machine": {"id": 1, "name": "IM24"}}
    assert cormind.kayit_satiri(k, {}, adlar) is None
    s = cormind.kayit_satiri(k, {}, adlar, datetime(2026, 11, 12, 10, 0))
    assert s[0] == "IM24" and s[1] == datetime(2026, 10, 20, 8, 0) and s[2] == datetime(2026, 11, 12, 10, 0) and s[4] == "İŞ EMRİ PLAN YOK"


def test_iki_sinirli_sorgu():
    """Önce dönemde başlayanlar; sonra ayrı ve geriye doğru sınırlı sorguyla döneme uzananlar. Sonsuza kadar sayfalanmaz."""
    from datetime import date
    gorulen = []

    class I(cormind.Istemci):
        def _graphql(self, model, kosul):
            gorulen.append(kosul["where"])
            return {"entities": [], "count": 0}

    i = I("http://x")
    i.hareketler(date(2026, 11, 2), date(2026, 11, 7), [5])
    assert len(gorulen) == 2 and "ended_at" not in gorulen[0] and '"started_at" >= \'2026-11-02T00:00:00+03:00\'' in gorulen[0]
    w = gorulen[1]
    assert '"started_at" >= \'2026-08-04T00:00:00+03:00\'' in w and '"started_at" < \'2026-11-02T00:00:00+03:00\'' in w and "IS NULL" in w
    assert not i.dar_sorgu and not i.kesildi

    class D(cormind.Istemci):                      # ikinci sorgu reddedilirse birincinin sonucu kalır
        def _graphql(self, model, kosul):
            if "ended_at" in kosul["where"]:
                raise cormind.CormindHata("kabul edilmedi")
            return {"entities": [{"id": 1}], "count": 1}

    d = D("http://x")
    assert d.hareketler(date(2026, 11, 2), date(2026, 11, 7), [5]) == [{"id": 1}] and d.dar_sorgu

    class Cok(cormind.Istemci):                    # hep dolu sayfa dönen sunucu: sınırda durulur
        AZAMI_SAYFA = 3
        n = 0
        def _graphql(self, model, kosul):
            Cok.n += 1
            return {"entities": [{"id": k} for k in range(kosul["limit"])], "count": 10 ** 9}

    c = Cok("http://x")
    c.hareketler(date(2026, 11, 2), date(2026, 11, 7), [5])
    assert c.kesildi and Cok.n == 6


def test_kapatilmamis_eski_kayit_sonraki_kayitla_biter():
    ham = [{"machine_id": 1, "started_at": "2026-10-20T05:00:00.000Z", "ended_at": None},
           {"machine_id": 1, "started_at": "2026-10-21T05:00:00.000Z", "ended_at": "2026-10-21T06:00:00.000Z"},
           {"machine_id": 1, "started_at": "2026-11-01T05:00:00.000Z", "ended_at": None},
           {"machine_id": 2, "started_at": "2026-10-01T05:00:00.000Z", "ended_at": None}]
    r = cormind.suren_kayitlari_kapat(ham)
    assert r[0]["ended_at"] == "2026-10-21T05:00:00.000Z"       # eski, kapatılmamış: sonraki kayıtla biter
    assert r[2]["ended_at"] is None and r[3]["ended_at"] is None   # makinenin son kaydı: hâlâ sürüyor
