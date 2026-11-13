import pytest
import json
import pytest
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
            if '"machine_id" = ' in c["where"]:      # makinenin aralıktan önceki son kaydı: bu örnekte yok
                assert "2026-11-09T00:00:00+03:00" in c["where"] and c["limit"] == 1
                return self._yaz({"data": {"entities": [], "count": 0}})
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
    """Çalışmıyor (-1) nedenleri ayrı listeden: 1 İŞ EMRİ PLAN YOK, 2 MAKİNA ARIZASI (arıza tablosundaki 1 = Kısa Duruş ile karışmaz)."""
    from datetime import datetime
    adlar = {1: "Kısa Duruş", 12: "Başka"}
    assert cormind.tip_adi({"type": -1, "entity_type": 1}, adlar) == "İŞ EMRİ PLAN YOK"
    assert cormind.tip_adi({"type": -1, "entity_type": 2}, adlar) == "MAKİNA ARIZASI"
    assert cormind.tip_adi({"type": 1, "entity_type": 1}, adlar) == "Kısa Duruş"
    assert cormind.tip_adi({"type": -1, "entity_type": None}, adlar) == "Çalışmıyor"
    assert cormind.tip_adi({"type": -1, "entity_type": 99}, adlar) == "Çalışmıyor"
    k = {"type": -1, "entity_type": 1, "started_at": "2026-10-20T05:00:00.000Z", "ended_at": None, "machine": {"id": 1, "name": "IM24"}}
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
    w = gorulen[1]                                  # makine başına aralıktan önceki son kayıt (yaşı ne olursa olsun)
    assert '"machine_id" = 5' in w and '"started_at" < \'2026-11-02T00:00:00+03:00\'' in w and ">=" not in w
    assert not i.dar_sorgu and not i.kesildi

    class D(cormind.Istemci):                      # ikinci sorgu reddedilirse birincinin sonucu kalır
        def _graphql(self, model, kosul):
            if '"machine_id" = ' in kosul["where"]:
                raise cormind.CormindHata("kabul edilmedi")
            return {"entities": [{"id": 1}], "count": 1}

    d = D("http://x")
    assert d.hareketler(date(2026, 11, 2), date(2026, 11, 7), [5]) == [{"id": 1}] and d.dar_sorgu

    class Cok(cormind.Istemci):                    # hep dolu sayfa dönen sunucu: sınırda durulur
        AZAMI_KAYIT = 6000
        SAYFA_ARASI_SN = 0
        n = 0
        def _graphql(self, model, kosul):
            Cok.n += 1
            return {"entities": [{"id": k} for k in range(kosul["limit"])], "count": 10 ** 9}

    c = Cok("http://x")
    c.hareketler(date(2026, 11, 2), date(2026, 11, 7), [5])
    assert c.kesildi and 2 <= Cok.n <= 16      # iki sorgu da kayıt sınırında durur


def test_kapatilmamis_eski_kayit_sonraki_kayitla_biter():
    ham = [{"machine_id": 1, "started_at": "2026-10-20T05:00:00.000Z", "ended_at": None},
           {"machine_id": 1, "started_at": "2026-10-21T05:00:00.000Z", "ended_at": "2026-10-21T06:00:00.000Z"},
           {"machine_id": 1, "started_at": "2026-11-01T05:00:00.000Z", "ended_at": None},
           {"machine_id": 2, "started_at": "2026-10-01T05:00:00.000Z", "ended_at": None}]
    r = cormind.suren_kayitlari_kapat(ham)
    assert r[0]["ended_at"] == "2026-10-21T05:00:00.000Z"       # eski, kapatılmamış: sonraki kayıtla biter
    assert r[2]["ended_at"] is None and r[3]["ended_at"] is None   # makinenin son kaydı: hâlâ sürüyor


def test_aylara_bol():
    from datetime import date
    assert cormind.aylara_bol(date(2026, 11, 2), date(2026, 11, 8)) == [(date(2026, 11, 2), date(2026, 11, 8))]
    assert cormind.aylara_bol(date(2026, 11, 1), date(2026, 11, 30)) == [(date(2026, 11, 1), date(2026, 11, 30))]
    p = cormind.aylara_bol(date(2025, 11, 15), date(2026, 2, 10))
    assert p == [(date(2025, 11, 15), date(2025, 11, 30)), (date(2025, 12, 1), date(2025, 12, 31)),
                 (date(2026, 1, 1), date(2026, 1, 31)), (date(2026, 2, 1), date(2026, 2, 10))]
    assert len(cormind.aylara_bol(date(2025, 11, 13), date(2026, 11, 12))) == 13


def test_ay_ay_cekim_ilerleme_ve_suren_kayit(tmp_path, monkeypatch):
    """Uzun aralık ay ay çekilir, her adım bildirilir; bir ayda süren kayıt sonraki ayın ilk kaydıyla biter; durdurulabilir."""
    from datetime import date
    istekler = []

    def sahte_hareketler(self, ilk, son, idler, ilerleme=None, uzanan=True):
        istekler.append((ilk, son, uzanan))
        self.dar_sorgu = self.kesildi = False
        if ilerleme:
            ilerleme(1, 1)
        if ilk.month == 9:      # Eylül: kayıt sürüyor (bitişi yok)
            return [_kayit(1, "IM21", -1, None, "2026-09-10T05:00:00.000Z", None)]
        if ilk.month == 10:     # Ekim: aynı makinede yeni kayıt 5 Ekim 11:00'de (TR) başlıyor
            return [_kayit(2, "IM21", 0, None, "2026-10-05T08:00:00.000Z", "2026-10-05T09:00:00.000Z")]
        return []

    monkeypatch.setattr(cormind.Istemci, "giris", lambda self, k, s: None)
    monkeypatch.setattr(cormind.Istemci, "ariza_adlari", lambda self: {})
    monkeypatch.setattr(cormind.Istemci, "hareketler", sahte_hareketler)
    con = vt.ac(str(tmp_path / "a.db"))
    adimlar = []
    r = cormind.cek(con, "http://x", "u", "p", date(2026, 9, 1), date(2026, 11, 5), [5], adim=adimlar.append, parca_arasi_sn=0)
    assert [(a, b) for a, b, _ in istekler] == [(date(2026, 9, 1), date(2026, 9, 30)), (date(2026, 10, 1), date(2026, 10, 31)), (date(2026, 11, 1), date(2026, 11, 5))]
    assert [u for _, _, u in istekler] == [True, False, False]          # eskiye bakan sorgu yalnızca ilk ayda
    assert r["parca_sayisi"] == 3 and r["biten_parca"] == 3 and r["toplam"] == 2 and not r["durduruldu"]
    assert adimlar[0]["asama"] == "baglaniyor" and adimlar[-1]["asama"] == "kaydedildi" and adimlar[-1]["parca"] == 3
    satir = con.execute("SELECT bitis FROM kayit WHERE makine='IM21' AND tip='Çalışmıyor'").fetchone()
    assert satir["bitis"] == "2026-10-05 11:00:00"                       # süren kayıt, sonraki ayın ilk kaydıyla bitti
    istekler.clear()
    r2 = cormind.cek(con, "http://x", "u", "p", date(2026, 9, 1), date(2026, 11, 5), [5], iptal=lambda: len(istekler) >= 1, parca_arasi_sn=0)
    assert r2["durduruldu"] and r2["biten_parca"] == 1 and len(istekler) == 1


# ------------------------------------------------------------ uyarlamalı sayfalama
class _Saat:
    """Sahte zaman: istek süreleri gerçekten beklenmeden ölçülür."""
    def __init__(self):
        self.t = 0.0

    def perf_counter(self):
        return self.t

    def sleep(self, sn):
        self.t += sn

    def monotonic(self):
        return self.t


def _sahte(N, sure, tavan=None, hata=None, sayac=None):
    """N kayıtlık sahte Cormind. sure(limit, offset) -> sn; tavan: sunucunun sayfa sınırı;
    hata(limit, offset, deneme) -> True ise o istek hata verir."""
    saat = _Saat()

    class S(cormind.Istemci):
        def _graphql(self, model, c):
            lim, off = c["limit"], c["offset"]
            self.istekler.append((lim, off))
            if hata and hata(lim, off, len(self.istekler)):
                saat.t += 1.0
                raise cormind.CormindHata("zaman aşımı")
            ger = min(lim, tavan) if tavan else lim
            saat.t += sure(ger, off)
            return {"entities": [{"id": i} for i in range(off, min(N, off + ger))], "count": N}

    s = S("http://x")
    s.istekler, s.kesildi = [], False
    return s, saat


def _cek(s, saat, monkeypatch):
    monkeypatch.setattr(cormind.time, "perf_counter", saat.perf_counter)
    monkeypatch.setattr(cormind.time, "sleep", saat.sleep)
    return s._sayfala("w", None)


def _tam(r, N):
    return [x["id"] for x in r] == list(range(N))          # eksiksiz ve tekrarsız, sırayla


def test_baslangic_2000(monkeypatch):
    s, saat = _sahte(5000, lambda n, o: 1.0)
    r = _cek(s, saat, monkeypatch)
    assert s.istekler[0] == (2000, 0) and _tam(r, 5000)


def test_hizli_2000_kucukmez_ve_buyuk_sayfa_daha_iyi_degilse_2000de_kalir(monkeypatch):
    # büyük sayfa aynı kayıt/sn veriyor (süre kayıtla orantılı): 3000 denenir, vazgeçilir, 2000'de kalınır
    s, saat = _sahte(40000, lambda n, o: n / 2000.0)
    r = _cek(s, saat, monkeypatch)
    boy = [x["boyut"] for x in s.sayfa_gecmisi]
    assert _tam(r, 40000) and min(boy) == 2000 and boy.count(3000) <= 2 and 5000 not in boy
    assert boy[-3:-1] == [2000, 2000] and 4 in s._yasak


def test_buyuk_sayfa_yalnizca_gercekten_hizliysa_secilir(monkeypatch):
    # sabit istek gideri baskın: büyük sayfa kayıt/sn olarak çok daha iyi -> 3000, sonra 5000
    s, saat = _sahte(60000, lambda n, o: 2.0 + n / 20000.0)
    r = _cek(s, saat, monkeypatch)
    boy = [x["boyut"] for x in s.sayfa_gecmisi]
    assert _tam(r, 60000) and 5000 in boy and boy[-2] == 5000


def test_tek_yavas_istek_kuculmeye_neden_olmaz(monkeypatch):
    yavas = {4000}                                          # yalnızca bu offset'teki istek çok yavaş
    s, saat = _sahte(16000, lambda n, o: 30.0 if o in yavas else 0.5)
    s.DENEME_ONCESI = 99                                    # büyümeyi kapat: yalnızca küçülme davranışı sınanır
    r = _cek(s, saat, monkeypatch)
    assert _tam(r, 16000) and all(x["boyut"] == 2000 for x in s.sayfa_gecmisi)


def test_art_arda_yavas_isteklerde_kuculur(monkeypatch):
    s, saat = _sahte(16000, lambda n, o: 20.0 if n >= 2000 else 1.0)
    s.DENEME_ONCESI = 99
    r = _cek(s, saat, monkeypatch)
    assert _tam(r, 16000) and any(x["boyut"] == 1000 for x in s.sayfa_gecmisi)


def test_hatada_ayni_offset_yeniden_denenir(monkeypatch):
    s, saat = _sahte(6000, lambda n, o: 0.5, hata=lambda lim, off, k: k == 2)   # ikinci istek bir kez hata verir
    r = _cek(s, saat, monkeypatch)
    assert s.istekler[1][1] == s.istekler[2][1] == 2000 and _tam(r, 6000)
    assert len(s.sayfa_gecmisi) == 3                        # başarısız istek sayfa sayılmaz


def test_tekrarlanan_hatada_kuculur_ve_kayip_olmaz(monkeypatch):
    s, saat = _sahte(7000, lambda n, o: 0.5, hata=lambda lim, off, k: lim >= 2000 and off == 2000)
    r = _cek(s, saat, monkeypatch)
    assert _tam(r, 7000) and any(lim == 1000 and off == 2000 for lim, off in s.istekler)


def test_en_kucuk_boyutta_da_hata_verirse_durur(monkeypatch):
    s, saat = _sahte(3000, lambda n, o: 0.5, hata=lambda lim, off, k: True)
    with pytest.raises(cormind.CormindHata):
        _cek(s, saat, monkeypatch)


def test_sunucu_sayfayi_kisaltirsa_kayip_olmaz(monkeypatch):
    s, saat = _sahte(12345, lambda n, o: 0.5, tavan=1000)
    r = _cek(s, saat, monkeypatch)
    assert _tam(r, 12345) and s.sayfa_gecmisi[1]["boyut"] == 1000


def test_son_sayfa_eksik_ve_toplam_dogru(monkeypatch):
    s, saat = _sahte(4567, lambda n, o: 0.5)
    r = _cek(s, saat, monkeypatch)
    assert _tam(r, 4567) and [x["adet"] for x in s.sayfa_gecmisi] == [2000, 2000, 567]


def test_kayit_siniri(monkeypatch):
    s, saat = _sahte(10 ** 6, lambda n, o: 0.5)
    r = _cek(s, saat, monkeypatch)
    assert len(r) == cormind.Istemci.AZAMI_KAYIT and s.kesildi and _tam(r, cormind.Istemci.AZAMI_KAYIT)


def test_bitis_end_alanindan():
    """Cormind çoğu kayıtta ended_at'i boş bırakıp 'end' (milisaniye) alanını dolduruyor."""
    from datetime import datetime
    k = {"started_at": "2025-04-29T13:00:57.540Z", "ended_at": None, "end": "1745931657541"}
    assert cormind.bitis_zamani(k) == datetime(2025, 4, 29, 16, 0, 57)
    ham = [dict(k, machine_id=1), {"machine_id": 1, "started_at": "2025-05-01T05:00:00.000Z", "ended_at": None, "end": None}]
    r = cormind.suren_kayitlari_kapat(ham)
    assert r[0]["ended_at"] is None and cormind.bitis_zamani(r[0]) == datetime(2025, 4, 29, 16, 0, 57)   # end'i olan dokunulmaz
