"""Web portal sunucusu: gerçek HTTP istekleriyle uçtan uca sınama (Qt gerekmez)."""
import http.client
import io
import json
import threading
from datetime import datetime, timedelta

import pytest

openpyxl = pytest.importorskip("openpyxl")

from vardiya import portal  # noqa: E402

KOT = ("=== KOT === KOT NO: 2026-1104-0900 TARIH: 04.11.2026 SAAT: 09:00 --- TEZGAHLAR --- "
       "TEZGAH: IM21 | KATEGORI: SETUP | NEDEN: Deneme | ACIKLAMA: Deneme kaydı. | AKSIYON: - --- SONUC --- Deneme. DURUM: ACIK === SON ===")


def _xlsx() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Makine Adı", "Operatör", "Tip", "İş Emri", "Ürün Adı", "Ürün Kodu", "Süre (saat)", "Başlangıç Tarihi", "Bitiş Tarihi"])
    for gun in (3, 4):
        for m in ("IM21", "IM22"):
            b = datetime(2026, 11, gun, 8, 0)
            ws.append([m, "Ali", "Çalışma", "1", "K", "D", 0, b.strftime("%d.%m.%Y %H:%M:%S"), (b + timedelta(hours=7, minutes=20)).strftime("%d.%m.%Y %H:%M:%S")])
            d = b + timedelta(hours=7, minutes=20)
            ws.append([m, "Ali", "TEMİZLİK", "1", "K", "D", 0, d.strftime("%d.%m.%Y %H:%M:%S"), (d + timedelta(minutes=30)).strftime("%d.%m.%Y %H:%M:%S")])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture(scope="module")
def sunucu(tmp_path_factory):
    db = str(tmp_path_factory.mktemp("portal") / "deneme.db")
    srv = portal.sunucu_kur(db, 0, "127.0.0.1")
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv
    srv.shutdown()
    srv.server_close()


def istek(srv, yontem, yol, govde=None, baslik=None):
    c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=20)
    if isinstance(govde, (dict, list)):
        govde = json.dumps(govde).encode("utf-8")
        baslik = {"Content-Type": "application/json", **(baslik or {})}
    c.request(yontem, yol, body=govde, headers=baslik or {})
    r = c.getresponse()
    veri = r.read()
    c.close()
    tur = r.getheader("Content-Type", "")
    return r.status, (json.loads(veri) if tur.startswith("application/json") else veri)


def test_bos_veri_tabani_durumu(sunucu):
    kod, d = istek(sunucu, "GET", "/api/durum")
    assert kod == 200 and d["toplam_kayit"] == 0 and d["ayar"]["esik"] == 0.6 and d["kapsam"] == {}


def test_statik_ve_bilinmeyen(sunucu):
    kod, veri = istek(sunucu, "GET", "/")
    assert kod == 200 and b"Vardiya Performans" in veri
    assert istek(sunucu, "GET", "/static/echarts.min.js")[0] == 200
    assert istek(sunucu, "GET", "/static/../main_web.py")[0] == 404
    assert istek(sunucu, "GET", "/api/yok")[0] == 404


def test_yukle_ve_hesap(sunucu):
    kod, d = istek(sunucu, "POST", "/api/yukle?ad=deneme.xlsx", _xlsx())
    assert kod == 200 and d["yeni"] == 8 and d["atlanan_sayisi"] == 0, d
    kod, d2 = istek(sunucu, "POST", "/api/yukle?ad=deneme.xlsx", _xlsx())      # aynı dosya: çoğalmaz
    assert d2["yeni"] == 0 and d2["ayni"] == 8
    kod, d = istek(sunucu, "GET", "/api/durum")
    assert d["toplam_kayit"] == 8 and set(d["kapsam"]) == {"2026-11-03", "2026-11-04"}
    kod, h = istek(sunucu, "GET", "/api/hesap?ilk=2026-11-03&son=2026-11-04")
    assert kod == 200 and not h["bos"]
    assert 0.9 < h["genel"][0] <= 1.0 and h["hesap_gunu"] == 2
    assert set(h["makine_ort"]) >= {"IM21", "IM22"} and "TEMİZLİK" in json.dumps(h["durus"], ensure_ascii=False)
    assert h["cormind"]["IM21"]["oee"] <= 100 and h["verisiz_gunler"] == []


def test_hesap_gun_haric_ve_verisiz(sunucu):
    kod, h = istek(sunucu, "GET", "/api/hesap?ilk=2026-11-03&son=2026-11-05&haric=2026-11-03")
    assert kod == 200 and h["secili"] == ["2026-11-04", "2026-11-05"] and h["verisiz_gunler"] == ["2026-11-05"]
    kod, h = istek(sunucu, "GET", "/api/hesap?ilk=2026-11-03&son=2026-11-03&haric=2026-11-03")
    assert h["bos"] is True
    assert istek(sunucu, "GET", "/api/hesap?ilk=2026-11-05&son=2026-11-03")[0] == 400
    assert istek(sunucu, "GET", "/api/hesap?ilk=abc&son=2026-11-03")[0] == 400


def test_operator(sunucu):
    kod, d = istek(sunucu, "GET", "/api/operator?ilk=2026-11-03&son=2026-11-04")
    assert kod == 200 and d["operatorler"] and d["operatorler"][0]["ad"] == "Ali" and d["operatorler"][0]["makine_sayisi"] == 2


def test_kayitlar_ve_silme(sunucu):
    kod, d = istek(sunucu, "GET", "/api/kayitlar?ilk=2026-11-03&son=2026-11-04&makine=IM21")
    assert kod == 200 and d["toplam"] == 4 and d["satirlar"][0]["makine"] == "IM21"
    nolar = [d["satirlar"][0]["no"]]
    kod, s = istek(sunucu, "POST", "/api/kayit_sil", {"nolar": nolar})
    assert kod == 200 and s["silinen"] == 1
    assert istek(sunucu, "GET", "/api/kayitlar?ilk=2026-11-03&son=2026-11-04&makine=IM21")[1]["toplam"] == 3
    assert istek(sunucu, "POST", "/api/kayit_sil", {"nolar": []})[0] == 400


def test_ayar_dogrulama(sunucu):
    kod, d = istek(sunucu, "POST", "/api/ayar", {"esik": 0.7, "sefler": ["A", "A", " B "], "bilinmeyen": 1})
    assert kod == 200 and d["yazilan"] == ["esik", "sefler"] and d["ayar"]["sefler"] == ["A", "B"]
    assert istek(sunucu, "POST", "/api/ayar", {"esik": 5})[0] == 400
    assert istek(sunucu, "POST", "/api/ayar", {"hesap_yontemi": "x"})[0] == 400
    istek(sunucu, "POST", "/api/ayar", {"esik": 0.6})


def test_sef_kot_idari(sunucu):
    assert istek(sunucu, "POST", "/api/sef", {"gunler": ["2026-11-03"], "vardiya": 2, "sef": "Deneme Şef"})[0] == 200
    h = istek(sunucu, "GET", "/api/hesap?ilk=2026-11-03&son=2026-11-03")[1]
    assert h["seflar"]["2"] == "Deneme Şef"
    assert istek(sunucu, "POST", "/api/sef", {"gunler": [], "vardiya": 2, "sef": "x"})[0] == 400
    assert istek(sunucu, "POST", "/api/kot", {"metin": "kot yok"})[0] == 400
    kod, d = istek(sunucu, "POST", "/api/kot", {"metin": KOT})
    assert kod == 200 and d["yeni"] == 1
    kod, d = istek(sunucu, "GET", "/api/kot?ilk=2026-11-01&son=2026-11-30")
    assert d["kotlar"][0]["no"] == "2026-1104-0900" and d["kotlar"][0]["tezgahlar"][0]["tezgah"] == "IM21"
    kod, d = istek(sunucu, "GET", "/api/idari?ilk=2026-11-03&son=2026-11-04")
    assert kod == 200 and isinstance(d["metin"], str) and d["metin"]


def test_arsiv_ve_gorsel(sunucu):
    kod, d = istek(sunucu, "POST", "/api/arsiv", {"ad": "Deneme", "tur": "gunluk", "ilk": "2026-11-03", "son": "2026-11-03", "html": "<p>rapor</p>"})
    assert kod == 200
    kod, g = istek(sunucu, "GET", "/api/gecmis")
    assert g["aktarim"] and g["arsiv"][0]["ad"] == "Deneme" and g["arsiv"][0]["tur"] == "web-gunluk"
    kod, html = istek(sunucu, "GET", f"/api/arsiv?id={d['id']}")
    assert kod == 200 and html == b"<p>rapor</p>"
    assert istek(sunucu, "POST", "/api/arsiv_sil", {"id": d["id"]})[0] == 200
    assert istek(sunucu, "GET", "/api/gorsel?anahtar=cormind")[0] == 404
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 20
    assert istek(sunucu, "POST", "/api/gorsel?anahtar=cormind", png)[0] == 200
    assert istek(sunucu, "GET", "/api/gorsel?anahtar=cormind")[1] == png
    assert istek(sunucu, "POST", "/api/gorsel", b"degil png")[0] == 400


def test_yukle_gecersiz(sunucu):
    assert istek(sunucu, "POST", "/api/yukle?ad=virus.exe", b"MZ")[0] == 400
    assert istek(sunucu, "POST", "/api/yukle?ad=bos.xlsx", b"")[0] == 400


def test_parola(tmp_path, monkeypatch):
    monkeypatch.setenv("VARDIYA_PAROLA", "gizli")
    srv = portal.sunucu_kur(str(tmp_path / "p.db"), 0, "127.0.0.1")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        assert istek(srv, "GET", "/api/durum")[0] == 401
        import base64
        iyi = {"Authorization": "Basic " + base64.b64encode(b"x:gizli").decode()}
        kotu = {"Authorization": "Basic " + base64.b64encode(b"x:yanlis").decode()}
        assert istek(srv, "GET", "/api/durum", baslik=iyi)[0] == 200
        assert istek(srv, "GET", "/api/durum", baslik=kotu)[0] == 401
    finally:
        srv.shutdown()
        srv.server_close()
