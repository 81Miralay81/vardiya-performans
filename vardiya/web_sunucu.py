"""Exe'nin içindeki web sunucusu: program açıkken iç ağdaki herkes tarayıcıdan aynı veriyi ve raporları görür.

Kalıp Takip'teki gibi: sunucu exe'yi çalıştıran bilgisayarda (senin bilgisayarında) çalışır; Cormind çekimi ve Outlook
okuması da o bilgisayarda yapılır. Hesaplar exe ile aynı ortak hizmetten (servis.py) gelir.

Qt ile çizim (rapor sayfaları, PDF, sabit tablo) ve Outlook ana iş parçacığında yapılmalıdır; istekler bunları Gui.calistir
ile ana iş parçacığına gönderip sonucu bekler. Veri tabanı okumaları her istekte ayrı bağlantıyla, istek iş parçacığında yapılır.
"""
from __future__ import annotations

import json
import mimetypes
import os
import socket
import threading
import time
import traceback
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional
from urllib.parse import parse_qs, urlparse

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, Qt, Signal, Slot

from . import tema, veritabani as vt

VARSAYILAN_PORT = 8090


class Gui(QObject):
    """Bir işlevi ana (arayüz) iş parçacığında çalıştırır ve sonucunu bekler."""
    _istek = Signal(object)

    def __init__(self):
        super().__init__()
        self._istek.connect(self._calis, Qt.QueuedConnection)

    @Slot(object)
    def _calis(self, is_):
        fn, kutu, olay = is_
        try:
            kutu["sonuc"] = fn()
        except Exception as ex:  # noqa: BLE001
            kutu["hata"] = ex
            kutu["iz"] = traceback.format_exc()
        finally:
            olay.set()

    def calistir(self, fn: Callable, zaman_asimi: float = 300.0):
        kutu, olay = {}, threading.Event()
        self._istek.emit((fn, kutu, olay))
        if not olay.wait(zaman_asimi):
            raise TimeoutError("İşlem zaman aşımına uğradı")
        if "hata" in kutu:
            raise kutu["hata"]
        return kutu.get("sonuc")


def _png(img) -> bytes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def _tarih(q: dict, ad: str, varsayilan: date) -> date:
    try:
        return date.fromisoformat(q.get(ad, [""])[0])
    except ValueError:
        return varsayilan


class Sunucu:
    def __init__(self, db_yolu: str, port: int = VARSAYILAN_PORT, yenilendi: Optional[Callable[[], None]] = None):
        self.db_yolu, self.port = db_yolu, port
        self.gui = Gui()
        self.yenilendi = yenilendi                      # Cormind çekimi bitince exe penceresini yenilemek için
        self.httpd: Optional[ThreadingHTTPServer] = None
        self.cekim = {"durum": "bos", "metin": "", "yuzde": 0, "dur": False}
        self._kilit = threading.Lock()

    # -------------------------------------------------------------- yaşam döngüsü
    def baslat(self) -> str:
        sunucu = self

        class Isleyici(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_a):                 # konsol yok; sessiz
                pass

            def do_GET(self):  # noqa: N802
                sunucu._isle(self, "GET")

            def do_POST(self):  # noqa: N802
                sunucu._isle(self, "POST")

        self.httpd = ThreadingHTTPServer(("0.0.0.0", self.port), Isleyici)
        self.httpd.daemon_threads = True
        threading.Thread(target=self.httpd.serve_forever, name="web-sunucu", daemon=True).start()
        return self.adres()

    def durdur(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None

    def adres(self) -> str:
        return f"http://{yerel_ip()}:{self.port}"

    # -------------------------------------------------------------- yanıt yardımcıları
    @staticmethod
    def _gonder(h, govde: bytes, tur: str = "application/json; charset=utf-8", kod: int = 200, ek: Optional[dict] = None):
        h.send_response(kod)
        h.send_header("Content-Type", tur)
        h.send_header("Content-Length", str(len(govde)))
        h.send_header("Cache-Control", "no-store")
        for k, v in (ek or {}).items():
            h.send_header(k, v)
        h.end_headers()
        h.wfile.write(govde)

    def _json(self, h, veri, kod: int = 200):
        self._gonder(h, json.dumps(veri, ensure_ascii=False, default=lambda o: o.isoformat() if hasattr(o, "isoformat") else str(o)).encode("utf-8"),
                     kod=kod)

    def _con(self):
        return vt.ac(self.db_yolu)

    # -------------------------------------------------------------- yönlendirme
    def _isle(self, h, yontem: str):
        u = urlparse(h.path)
        q = parse_qs(u.query)
        yol = u.path.rstrip("/") or "/"
        try:
            if yol == "/":
                return self._dosya(h, "uygulama.html")
            if yol.startswith("/s/"):
                return self._dosya(h, yol[3:])
            if yol == "/logo.png":
                return self._gonder(h, open(tema.kaynak_yolu("assets", "logo.png"), "rb").read(), "image/png")
            if yol == "/api/oturum":
                return self.api_oturum(h)
            if yol == "/api/giris" and yontem == "POST":
                return self.api_giris(h)
            if yol == "/api/cikis":
                return self.api_cikis(h)
            if yol.startswith("/api/"):
                durum = self._yetki_denetle(h, yol)
                if durum:
                    return self._json(h, {"hata": durum[1], "giris_gerekli": durum[0] == 401}, durum[0])
            f = {"/api/durum": self.api_durum, "/api/performans": self.api_performans, "/api/tablo.png": self.api_tablo,
                 "/api/rapor/bilgi": self.api_rapor_bilgi, "/api/rapor/sayfa.png": self.api_rapor_sayfa,
                 "/api/rapor.pdf": self.api_rapor_pdf, "/api/operator": self.api_operator, "/api/operator/ayrinti": self.api_operator_ayrinti, "/api/operator/cakisma": self.api_operator_cakisma, "/api/duran": self.api_duran, "/api/kirilim": self.api_kirilim,
                 "/api/kayitlar": self.api_kayitlar, "/api/personel": self.api_personel,
                 "/api/kirilim/operator": self.api_kirilim_operator, "/api/personel/hafta": self.api_personel_hafta, "/api/personel/kart": self.api_personel_kart, "/api/personel/foto": self.api_personel_foto, "/api/cormind/cek": self.api_cek, "/api/cormind/durum": self.api_cek_durum,
                 "/api/cormind/durdur": self.api_cek_durdur, "/api/outlook": self.api_outlook}.get(yol)
            if f is None:
                return self._gonder(h, b"Bulunamadi", "text/plain; charset=utf-8", 404)
            if yontem == "POST":
                n = int(h.headers.get("Content-Length") or 0)
                govde = h.rfile.read(n) if n else b""
                try:
                    q.update({k: [str(v)] for k, v in json.loads(govde or b"{}").items()})
                except ValueError:
                    pass
            return f(h, q)
        except BrokenPipeError:
            return None
        except Exception as ex:  # noqa: BLE001
            try:
                self._json(h, {"hata": f"{type(ex).__name__}: {ex}"}, 500)
            except Exception:  # noqa: BLE001
                pass

    # -------------------------------------------------------------- kullanıcı oturumu (Ayarlar'da kullanıcı varsa zorunlu)
    YETKI = {"/api/performans": "performans", "/api/tablo.png": "performans", "/api/kirilim": "performans", "/api/kirilim/operator": "performans", "/api/duran": "performans",
             "/api/rapor/bilgi": "rapor", "/api/rapor/sayfa.png": "rapor", "/api/rapor.pdf": "rapor", "/api/outlook": "rapor",
             "/api/operator": "operator", "/api/operator/ayrinti": "operator", "/api/operator/cakisma": "operator",
             "/api/kayitlar": "kayitlar", "/api/personel": "personel", "/api/personel/hafta": "personel",
             "/api/personel/kart": "personel", "/api/personel/foto": "personel_kimlik", "/api/cormind/cek": "veri", "/api/cormind/durum": "veri", "/api/cormind/durdur": "veri"}
    OTURUM_SN = 12 * 3600

    def _oturumlar(self) -> dict:
        if not hasattr(self, "_oturum"):
            self._oturum = {}
        return self._oturum

    def _sistem_acik(self) -> bool:
        """Kullanıcı sistemi açık mı (10 sn önbellek; her istekte veri tabanına gitmesin)."""
        import time as _t
        on = getattr(self, "_sistem_onbellek", None)
        if on and _t.time() - on[0] < 10:
            return on[1]
        from . import kullanici as ku
        con = self._con()
        try:
            v = ku.var_mi(con)
        finally:
            con.close()
        self._sistem_onbellek = (_t.time(), v)
        return v

    def _oturum_kullanici(self, h) -> Optional[dict]:
        import time as _t
        from http.cookies import SimpleCookie
        c = SimpleCookie()
        try:
            c.load(h.headers.get("Cookie") or "")
        except Exception:  # noqa: BLE001
            return None
        j = c.get("vp_oturum")
        if not j:
            return None
        o = self._oturumlar().get(j.value)
        if not o or _t.time() - o[1] > self.OTURUM_SN:
            return None
        from . import kullanici as ku
        con = self._con()
        try:
            k = ku.getir(con, o[0])
        finally:
            con.close()
        if not k or not k["aktif"]:
            return None
        self._oturumlar()[j.value] = (o[0], _t.time())
        return k

    def _yetki_denetle(self, h, yol: str):
        if not self._sistem_acik():
            if yol.startswith("/api/personel"):          # personel verisi tarayıcıda yalnızca kullanıcı girişiyle
                return 403, "Personel Durum tarayıcıda yalnızca kullanıcı girişi açıkken görünür"
            return None
        k = self._oturum_kullanici(h)
        if not k:
            return 401, "Giriş gerekli"
        from . import kullanici as ku
        gerek = self.YETKI.get(yol)
        if gerek and not ku.yetkili(k, gerek):
            return 403, "Bu sayfayı görme yetkiniz yok"
        return None

    def api_oturum(self, h):
        if not self._sistem_acik():
            return self._json(h, {"gerekli": False})
        k = self._oturum_kullanici(h)
        if not k:
            return self._json(h, {"gerekli": True})
        return self._json(h, {"gerekli": True, "ad": k["ad"], "yonetici": k["yonetici"], "yetkiler": k["yetkiler"]})

    def api_giris(self, h):
        import secrets
        import time as _t
        from . import kullanici as ku
        n = int(h.headers.get("Content-Length") or 0)
        try:
            v = json.loads(h.rfile.read(n) or b"{}") if n else {}
        except ValueError:
            v = {}
        con = self._con()
        try:
            k = ku.dogrula(con, str(v.get("ad") or ""), str(v.get("sifre") or ""))
        finally:
            con.close()
        if not k:
            _t.sleep(1.0)                               # deneme-yanılmayı yavaşlatır
            return self._json(h, {"hata": "Kullanıcı adı ya da şifre hatalı"}, 401)
        j = secrets.token_urlsafe(32)
        self._oturumlar()[j] = (k["ad"], _t.time())
        govde = json.dumps({"tamam": True}).encode()
        self._gonder(h, govde, ek={"Set-Cookie": f"vp_oturum={j}; HttpOnly; SameSite=Strict; Path=/"})

    def api_cikis(self, h):
        from http.cookies import SimpleCookie
        c = SimpleCookie()
        try:
            c.load(h.headers.get("Cookie") or "")
            if c.get("vp_oturum"):
                self._oturumlar().pop(c["vp_oturum"].value, None)
        except Exception:  # noqa: BLE001
            pass
        self._gonder(h, b'{"tamam": true}', ek={"Set-Cookie": "vp_oturum=; Max-Age=0; Path=/"})

    def _dosya(self, h, ad: str):
        ad = os.path.normpath(ad).replace("\\", "/")
        if ad.startswith("..") or ad.startswith("/"):
            return self._gonder(h, b"", "text/plain", 403)
        yol = tema.kaynak_yolu("assets", "web", ad)
        if not os.path.isfile(yol):
            return self._gonder(h, b"Bulunamadi", "text/plain; charset=utf-8", 404)
        tur = mimetypes.guess_type(yol)[0] or "application/octet-stream"
        if tur.startswith("text/") or tur.endswith("javascript"):
            tur += "; charset=utf-8"
        self._gonder(h, open(yol, "rb").read(), tur)

    # -------------------------------------------------------------- API
    def _aralik(self, q, con) -> tuple:
        kap = vt.gun_kapsami(con)
        son_gun = max(kap) if kap else date.today()
        son = _tarih(q, "son", son_gun)
        ilk = _tarih(q, "ilk", son - timedelta(days=6))
        if son < ilk:
            ilk, son = son, ilk
        return ilk, son

    def api_durum(self, h, q):
        from .surum import SURUM
        con = self._con()
        try:
            kap = vt.gun_kapsami(con)
            a = vt.ayar_oku(con)
            self._json(h, {"surum": SURUM, "kapsam_ilk": min(kap) if kap else None, "kapsam_son": max(kap) if kap else None,
                           "makineler": a.get("makineler", []), "kayit_sayisi": sum(kap.values()), "adres": self.adres(),
                           "cekim": self.cekim["durum"]})
        finally:
            con.close()

    def api_performans(self, h, q):
        from . import servis
        con = self._con()
        try:
            ilk, son = self._aralik(q, con)
            veri = servis.performans_verisi(con, vt.ayar_oku(con), ilk, son)
        finally:
            con.close()
        self._json(h, veri)

    def api_tablo(self, h, q):
        """Senin sabit Excel görünümlü tablon: exe'deki çizimin aynısı, resim olarak."""
        from . import cizim, servis
        con = self._con()
        try:
            ilk, son = self._aralik(q, con)
            a = vt.ayar_oku(con)
            d = servis.donem_verisi(con, a, ilk, son)
        finally:
            con.close()
        if not d["sonuc"]:
            return self._gonder(h, b"", "image/png", 204)
        s = d["sonuc"]
        tum = list(a.get("makineler", [])) + sorted(m for m in s.hucreler if m not in a.get("makineler", []))
        img = self.gui.calistir(lambda: cizim.tablo_resmi(s, tum, 0, 660, 30, 1.0))
        self._gonder(h, _png(img), "image/png")

    def _rapor(self, q):
        from . import servis
        duzen = q.get("duzen", ["makine"])[0]
        duzen = duzen if duzen in servis.DUZENLER else "makine"
        try:
            tur = max(0, min(3, int(q.get("tur", ["3"])[0])))
        except ValueError:
            tur = 3
        con = self._con()
        try:
            ilk, son = self._aralik(q, con)
            r, bilgi = servis.rapor_verisi(con, vt.ayar_oku(con), duzen, ilk, son, tur)
        finally:
            con.close()
        return r, bilgi

    def api_rapor_bilgi(self, h, q):
        from . import cizim
        r, bilgi = self._rapor(q)
        sayfa = self.gui.calistir(lambda: cizim.sayfa_sayisi(dict(r, yer_tutucu=False))) if r else 0
        self._json(h, {"var": r is not None, "baslik": r["baslik"] if r else "", "sayfa": sayfa, "gun": len(bilgi["gunler"]),
                       "kot_sayisi": bilgi["kot_sayisi"], "yatan": bilgi["yatan"], "seflar": bilgi["seflar"]})

    def api_rapor_sayfa(self, h, q):
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor, QImage, QPainter
        from . import cizim
        r, _b = self._rapor(q)
        if r is None:
            return self._gonder(h, b"", "image/png", 204)
        try:
            i = int(q.get("i", ["0"])[0])
        except ValueError:
            i = 0
        try:
            gen = max(600, min(3000, int(q.get("g", ["1800"])[0])))
        except ValueError:
            gen = 1800

        def ciz():
            r2 = dict(r, yer_tutucu=False)
            yuk = int(gen * 297 / 420)                  # A3 yatay
            img = QImage(gen, yuk, QImage.Format_ARGB32)
            img.fill(QColor("white"))
            p = QPainter(img)
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setRenderHint(QPainter.SmoothPixmapTransform, True)
            cizim.sayfa_ciz(p, QRectF(0, 0, gen, yuk), r2, max(0, min(i, cizim.sayfa_sayisi(r2) - 1)))
            p.end()
            return img
        self._gonder(h, _png(self.gui.calistir(ciz)), "image/png")

    def api_rapor_pdf(self, h, q):
        from .sayfa_rapor import pdf_yaz
        r, _b = self._rapor(q)
        if r is None:
            return self._json(h, {"hata": "Seçilen günlerde veri yok"}, 404)

        def yaz():
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QIODevice.WriteOnly)
            pdf_yaz(buf, r)
            buf.close()
            return bytes(ba)
        veri = self.gui.calistir(yaz)
        ad = "".join(c if c.isalnum() or c in " .-_" else "_" for c in r["baslik"]).strip() or "rapor"
        from urllib.parse import quote
        self._gonder(h, veri, "application/pdf", ek={"Content-Disposition": f"inline; filename*=UTF-8''{quote(ad)}.pdf"})

    def _operatorler(self, q):
        """Operatör sekmesindeki hesap (exe ile aynı): (ilk, son, {ad: OperatorSonuc})."""
        from datetime import datetime
        from .operator import operator_adi, operator_dogrula, operatorleri_hesapla
        from . import servis
        con = self._con()
        try:
            ilk, son = self._aralik(q, con)
            a = vt.ayar_oku(con)
            gunler = servis.gunler(ilk, son)
            alt = datetime(ilk.year, ilk.month, ilk.day)
            ust = datetime(son.year, son.month, son.day) + timedelta(days=1)
            kayit = operator_dogrula(vt.kayitlari_getir_operatorlu(con, ilk, son, kirp=False), alt, ust)
            from .operator_vardiya import bagla
            kayit = bagla(con, kayit, ilk, son, a)
            haric = vt.haric_personel(con)
            if haric:
                kayit = [k for k in kayit if __import__("vardiya.operator_vardiya", fromlist=["x"]).temel_ad(operator_adi(k[0])) not in haric]
            try:
                v = int(q.get("vardiya", ["0"])[0])
            except ValueError:
                v = 0
            tum = operatorleri_hesapla(kayit, gunler, servis.hesap_ayari(a), {v} if v else None,
                                       list(a.get("operator_haric_durus") or []))
        finally:
            con.close()
        return ilk, son, tum

    def api_operator_ayrinti(self, h, q):
        """Exe'deki operatör ayrıntı penceresi: makineler, günler, duruş nedenleri ve tıklanan sütunun listesi."""
        ad = (q.get("ad") or [""])[0]
        ilk, son, tum = self._operatorler(q)
        r = tum.get(ad)
        if r is None:
            return self._json(h, {"hata": f"{ad} bu dönemde bulunamadı."}, 404)
        GUN = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]

        def ep(e):
            return {"bas": f"{e.bas:%d.%m.%Y %H:%M:%S}", "bit": f"{e.bit:%d.%m.%Y %H:%M:%S}", "sn": round(e.sn),
                    "duruslar": [[m, t] for m, t in e.duruslar], "calisanlar": list(e.calisanlar), "setup": e.setup_var}
        self._json(h, {
            "ad": r.ad, "ilk": ilk, "son": son,
            "makineler": [{"makine": m, "calisma": round(v["calisma"]), "durus": round(v["durus"]), "mola": round(v["mola"])}
                          for m, v in sorted(r.makineler.items())],
            "gunler": [{"gun": f"{g:%d.%m.%Y} {GUN[g.weekday()]}", "kisa": f"{g:%d.%m} {GUN[g.weekday()]}",
                        "calisma": v["calisma"], "durus": v["durus"], "molada_calisma": v["molada_calisma"], "makine": v["makine"], "bosta_sn": round(v.get("bosta_sn", 0)),
                        "cakisan_sn": round(v.get("cakisan_sn", 0)), "birim": int(v["birim"])} for g, v in sorted(r.gunler.items())],
            "nedenler": sorted(([t, round(sn)] for t, sn in r.durus_tipleri.items()), key=lambda x: -x[1]),
            "durus_sn": round(r.durus_sn),
            "makine_durus": {m: {t: round(x) for t, x in d.items()} for m, d in r.makine_durus.items()},
            "makine_gun": [[m, f"{g:%d.%m} {GUN[g.weekday()]}", round(v["calisma"]), round(v["durus"]), round(v["mola"])]
                           for (m, g), v in sorted(r.makine_gun.items(), key=lambda x: (x[0][1], x[0][0]))],
            "gun_iso": [g.isoformat() for g in sorted(r.gunler)],
            "cakisma": [ep(e) for e in r.cakismalar[:5000]], "bosta": [ep(e) for e in r.bosta_listesi[:5000]],
            "plansiz": [ep(e) for e in r.plansiz_listesi[:5000]]})

    def api_operator_cakisma(self, h, q):
        """Bir günün çakışan duruşları (zaman çizelgesi için): makineler, duruş blokları ve çakışmalar."""
        ad = (q.get("ad") or [""])[0]
        try:
            gun = date.fromisoformat((q.get("gun") or [""])[0])
        except ValueError:
            return self._json(h, {"hata": "gün geçersiz"}, 400)
        _ilk, _son, tum = self._operatorler(q)
        r = tum.get(ad)
        if r is None:
            return self._json(h, {"hata": f"{ad} bu dönemde bulunamadı."}, 404)
        f = "%Y-%m-%d %H:%M:%S"
        cak = [e for e in r.cakismalar if e.bas.date() == gun]
        makineler = sorted({m for e in cak for m, _t in e.duruslar} | {m for e in cak for m in e.calisanlar})
        bloklar = {m: [[a.strftime(f), b.strftime(f), d, tp] for a, b, d, tp, g, _v in r.parcalar.get(m, []) if g == gun] for m in makineler}
        self._json(h, {"ad": ad, "gun": gun.isoformat(), "makineler": makineler, "bloklar": bloklar,
                       "cakismalar": [{"bas": e.bas.strftime(f), "bit": e.bit.strftime(f), "sn": round(e.sn), "duruslar": [[m, t] for m, t in e.duruslar],
                                       "calisanlar": list(e.calisanlar), "setup": e.setup_var} for e in cak]})

    def api_operator(self, h, q):
        ilk, son, tum = self._operatorler(q)

        def hm(sn):
            dk = int(round((sn or 0) / 60))
            return f"{dk // 60}:{dk % 60:02d}"
        satirlar = []
        for ad, r in sorted(tum.items(), key=lambda x: -(x[1].durus_orani or 0)):
            satirlar.append({"ad": ad, "makine": r.makine_sayisi, "makineler": sorted(r.makineler), "gun": r.gun_sayisi or len(r.gunler),
                             "calisma": r.calisma_orani, "durus": r.durus_orani, "molada_calisma": r.molada_calisma_orani, "bosta": r.bosta_orani,
                             "bosta_s": hm(r.hepsi_calisirken_sn), "cakisan_s": hm(r.cakisan_sn), "plansiz_s": hm(r.plansiz_sn),
                             "belgesiz_s": hm(r.belgesiz_sn), "ayar_kayip_s": hm(r.setup_kayip_sn), "ort_makine": r.ort_makine,
                             "en_cok": [(t, hm(sn)) for t, sn in sorted(r.durus_tipleri.items(), key=lambda x: -x[1])[:3]]})
        from .operator import AYRINTI_ACIKLAMA, SUTUN_ACIKLAMA
        self._json(h, {"ilk": ilk, "son": son, "satirlar": satirlar, "aciklama": SUTUN_ACIKLAMA, "ayrinti_aciklama": AYRINTI_ACIKLAMA})

    def api_kirilim(self, h, q):
        """Performans 3. kırılım: bir makinenin bir duruş türünün vardiya ve operatör dağılımı."""
        from .kirilim import durus_kirilimi
        con = self._con()
        try:
            ilk, son = self._aralik(q, con)
            k = durus_kirilimi(con, ilk, son, (q.get("makine") or [""])[0], (q.get("tip") or [""])[0])
        finally:
            con.close()
        self._json(h, {"vardiya": [[a, round(x, 4)] for a, x in k["vardiya"]], "operator": [[a, round(x, 4)] for a, x in k["operator"]]})

    def api_kirilim_operator(self, h, q):
        """Performans 4. ve 5. kırılım: bir operatörün (ya da 'Operatör yok') bir duruş türünde makineye ve zamana göre
        dağılımı, zaman çizelgesi için o makinelerin kayıtları. Dönem kayıtları 2 dk önbellekte (her tıklamada yeniden okunmaz)."""
        import time as _t
        from .kirilim import donem_kayitlari, operator_ayrinti
        con = self._con()
        try:
            ilk, son = self._aralik(q, con)
            on = getattr(self, "_donem_onbellek", None)
            if on and on[0] == (ilk, son) and _t.time() - on[1] < 120:
                kayit = on[2]
            else:
                kayit = donem_kayitlari(con, ilk, son)
                self._donem_onbellek = ((ilk, son), _t.time(), kayit)
        finally:
            con.close()
        v = operator_ayrinti(kayit, ilk, son, (q.get("tip") or [""])[0], (q.get("op") or [""])[0])
        ms = lambda d: d.strftime("%Y-%m-%d %H:%M:%S")  # noqa: E731  (tarayıcı yerel saat olarak okur)
        from .hesap import durus_adi
        self._json(h, {"ilk": ilk.isoformat(), "son": son.isoformat(),
                       "makine": [[m, round(x, 4)] for m, x in v["makine"]],
                       "gun": [[g.isoformat(), [round(x, 4) for x in l]] for g, l in v["gun"]],
                       "bloklar": {m: [[ms(a), ms(b), (durus_adi(t, a, b) if st == "Duruş" else st), st, op, 1 if vu else 0]
                                       for a, b, t, st, op, vu in lst] for m, lst in v["bloklar"].items()}})

    def api_duran(self, h, q):
        from . import operatorlu_durus, servis
        con = self._con()
        try:
            ilk, son = self._aralik(q, con)
            satirlar = operatorlu_durus.hesapla(con, servis.gunler(ilk, son))
        finally:
            con.close()
        self._json(h, {"ilk": ilk, "son": son, "satirlar": [
            {"makine": m, "operator": op, "saat": round(top, 2), "nedenler": sorted(((t, round(sa, 2)) for t, sa in d.items()), key=lambda x: -x[1])}
            for top, m, op, d in satirlar]})

    # -------------------------------------------------------------- personel durum (yalnızca yetkili kullanıcı)
    def _pv_temel(self, con, ilk, son):
        from . import personel_veri as pv
        ayar = vt.ayar_oku(con)
        gl, oz = pv.donem_hesabi(con, ilk, son, ayar)
        return ayar, gl, oz, pv.personel(con), pv.izin_adlari(con)

    def api_personel(self, h, q):
        from . import personel_veri as pv
        bugun = date.today()
        ilk = _tarih(q, "ilk", date(bugun.year, bugun.month, 1))
        son = _tarih(q, "son", bugun - timedelta(days=1))
        con = self._con()
        try:
            ayar, gl, oz, kisi, izin_ad = self._pv_temel(con, ilk, son)
            kap = pv.kapsam(con)
        finally:
            con.close()
        bv = pv.baskin_vardiya(gl)
        satir = []
        for sid, o in oz.items():
            p = kisi.get(sid, {})
            satir.append({"sid": sid, "ad": pv.tr_baslik(p.get("ad") or sid), "pozisyon": pv.tr_baslik(p.get("pozisyon") or ""),
                          "vardiya": bv.get(sid, ""), "lider": pv.lider_mi(p), "cikis": p.get("cikis_tarih") or "",
                          "lider_tur": pv.lider_turu(ayar, sid) if pv.lider_mi(p) else "",
                          "planli": o.planli, "geldi": o.geldi, "gelmedi": o.gelmedi, "eksik": o.eksik, "izinli": o.izinli,
                          "izin_saat": o.izin_saat, "izin": {pv.izin_kisa(izin_ad, k): n for k, n in o.izin_tur.items()},
                          "gec_adet": o.gec_adet, "gec_dk": o.gec_dk, "erken_adet": o.erken_adet, "erken_dk": o.erken_dk,
                          "fazla_dk": o.fazla_dk, "tatil": o.tatil_calisti,
                          "devam": None if o.devam is None else round(o.devam, 4)})
        satir.sort(key=lambda r: r["ad"])
        liste = pv.devam_gun_listeleri(gl, kisi, izin_ad, [r["sid"] for r in satir])
        return self._json(h, {"satir": satir, "liste": liste, "kapsam": list(kap), "ilk": ilk.isoformat(), "son": son.isoformat(),
                              "tolerans": ayar.get("pv_tolerans_dk", pv.VARSAYILAN_TOLERANS_DK),
                              "fazla_en_az": ayar.get("pv_fazla_en_az_dk", pv.VARSAYILAN_FAZLA_EN_AZ_DK)})

    def api_personel_hafta(self, h, q):
        from . import personel_veri as pv
        bugun = date.today()
        pzt = _tarih(q, "pzt", bugun - timedelta(days=bugun.weekday()))
        pzt = pzt - timedelta(days=pzt.weekday())
        con = self._con()
        try:
            ayar, gl, _oz, kisi, izin_ad = self._pv_temel(con, pzt, pzt + timedelta(days=6))
            lider = pv.hafta_grup_liderleri(con, pzt, ayar)
        finally:
            con.close()
        bv = pv.baskin_vardiya(gl)
        gm: dict = {}
        for g in gl:
            gm.setdefault(g.sicilid, {})[g.gun] = g
        sira = {"1": 0, "2": 1, "3": 2, "G": 3}
        satir = []
        for sid in sorted([s for s in gm if not kisi.get(s, {}).get("cikis_tarih")], key=lambda s: (sira.get(bv.get(s, ""), 9), not pv.lider_mi(kisi.get(s, {})), str(kisi.get(s, {}).get("ad", "")))):
            gunler = []
            for i in range(7):
                g = gm[sid].get(pzt + timedelta(days=i))
                if g is None:
                    gunler.append(None)
                    continue
                m, r = pv.gun_yazi(g, izin_ad, bugun)
                gunler.append({"m": m, "r": r, "i": pv.gun_ipucu(g, izin_ad)})
            p = kisi.get(sid, {})
            satir.append({"sid": sid, "ad": pv.tr_baslik(p.get("ad") or sid), "vardiya": bv.get(sid, ""), "lider": pv.lider_mi(p),
                          "lider_tur": pv.lider_turu(ayar, sid) if pv.lider_mi(p) else "",
                          "cikis": p.get("cikis_tarih") or "", "gun": gunler})
        return self._json(h, {"pzt": pzt.isoformat(), "satir": satir,
                              "lider": {k: [pv.tr_baslik(x) for x in v] for k, v in lider.items()}, "vardiya_ad": pv.VARDIYA_AD})

    def api_personel_kart(self, h, q):
        from . import kullanici as ku, personel_veri as pv
        bugun = date.today()
        sid = int(q.get("sid", ["0"])[0] or 0)
        ilk = _tarih(q, "ilk", date(bugun.year, bugun.month, 1))
        son = _tarih(q, "son", bugun - timedelta(days=1))
        ay = _tarih(q, "ay", date(son.year, son.month, 1)).replace(day=1)
        ay_son = date(ay.year + (ay.month == 12), ay.month % 12 + 1, 1) - timedelta(days=1)
        con = self._con()
        try:
            _ayar, gl_donem, oz, kisi, izin_ad = self._pv_temel(con, ilk, son)
            ayar2 = vt.ayar_oku(con)
            gl_ay, _ = pv.donem_hesabi(con, ay, ay_son, ayar2)
        finally:
            con.close()
        p = kisi.get(sid)
        if not p:
            return self._json(h, {"hata": "personel bulunamadı"}, 404)
        o = oz.get(sid)
        takvim = []
        for g in gl_ay:
            if g.sicilid == sid:
                m, r = pv.gun_yazi(g, izin_ad, bugun)
                takvim.append({"gun": g.gun.isoformat(), "m": m, "r": r, "i": pv.gun_ipucu(g, izin_ad),
                               "gec": g.gec_dk, "erken": g.erken_dk, "fazla": g.fazla_dk if g.durum == pv.GELDI else 0})
        k = self._oturum_kullanici(h)
        con = self._con()
        try:
            b = pv.bakiyeler(con).get(sid) or {}
        finally:
            con.close()
        kimlik = ku.yetkili(k, "personel_kimlik")
        return self._json(h, {"sid": sid, "kimlik": kimlik, "ad": pv.tr_baslik(p.get("ad") or ""), "sicilno": p.get("sicilno") or "",
                              "giris": str(b.get("giris_tarih") or p.get("giris_tarih") or "")[:10], "kidem": b.get("kidem"),
                              "telefon": (p.get("telefon") or "") if kimlik else "",
                              "izin": None if (not b or not kimlik) else {k2: b.get(k2) for k2 in ("hak", "kullanilan", "devir", "kalan", "guncel")},
                              "izin_satir": pv.izin_satirlari(b) if kimlik else [],
                              "pozisyon": pv.tr_baslik(p.get("pozisyon") or ""), "yaka": pv.tr_baslik(p.get("yaka") or ""),
                              "periyot": p.get("periyot") or "", "cikis": p.get("cikis_tarih") or "",
                              "foto": bool(p.get("foto")) and ku.yetkili(k, "personel_kimlik"),
                              "ozet": None if not o else {"planli": o.planli, "geldi": o.geldi, "gelmedi": o.gelmedi, "eksik": o.eksik,
                                                          "izinli": o.izinli, "gec_adet": o.gec_adet, "gec_dk": o.gec_dk,
                                                          "erken_adet": o.erken_adet, "erken_dk": o.erken_dk, "fazla_dk": o.fazla_dk,
                                                          "tatil": o.tatil_calisti, "devam": o.devam,
                                                          "izin": {izin_ad.get(kk, kk): n for kk, n in o.izin_tur.items()}},
                              "gorsel": pv.kart_ozeti([g for g in gl_donem if g.sicilid == sid], o, oz, izin_ad),
                              "ay": ay.isoformat(), "takvim": takvim})

    def api_personel_foto(self, h, q):
        import base64
        from . import personel_veri as pv
        sid = int(q.get("sid", ["0"])[0] or 0)
        con = self._con()
        try:
            p = pv.personel(con).get(sid) or {}
        finally:
            con.close()
        try:
            veri = base64.b64decode(p.get("foto") or "")
        except Exception:  # noqa: BLE001
            veri = b""
        if not veri:
            return self._json(h, {"hata": "fotoğraf yok"}, 404)
        self._gonder(h, veri, "image/jpeg")

    def api_kayitlar(self, h, q):
        from datetime import datetime
        from .hesap import bozuk_indeksler, statu_bul
        con = self._con()
        try:
            ilk, son = self._aralik(q, con)
            makine = q.get("makine", [""])[0]
            bozuk = q.get("bozuk", ["0"])[0] == "1"
            kolon = "makine, tip, baslangic, bitis, operator, is_emri, urun_kodu, urun_adi"
            if bozuk:
                rows = vt.aralik_satirlari(con, kolon, ilk, son, "makine = ?" if makine else "", (makine,) if makine else ()).fetchall()
                liste = [(r["makine"], r["tip"], vt.zaman(r["baslangic"]), vt.zaman(r["bitis"])) for r in rows]
                sec = bozuk_indeksler(liste)
                rows = [r for i, r in enumerate(rows) if i in sec]
            else:
                kosul, arg = "baslangic >= ? AND baslangic < ?", [ilk.strftime("%Y-%m-%d 00:00:00"), (son + timedelta(days=1)).strftime("%Y-%m-%d 00:00:00")]
                if makine:
                    kosul += " AND makine = ?"
                    arg.append(makine)
                rows = con.execute(f"SELECT {kolon} FROM kayit WHERE {kosul} ORDER BY baslangic DESC LIMIT 3001", arg).fetchall()
        finally:
            con.close()
        cikti = []
        for r in rows[:3000]:
            b, e = vt.zaman(r["baslangic"]), vt.zaman(r["bitis"])
            sn = max(0, int((e - b).total_seconds()))
            cikti.append([r["makine"], r["tip"], statu_bul(r["tip"]), r["baslangic"], r["bitis"],
                          f"{sn // 3600}:{sn % 3600 // 60:02d}:{sn % 60:02d}", r["operator"] or "", r["is_emri"] or "", r["urun_kodu"] or ""])
        self._json(h, {"satirlar": cikti, "fazla": len(rows) > 3000})

    # -------------------------------------------------------------- Cormind çekimi (senin bilgisayarında)
    def api_cek(self, h, q):
        import base64
        from PySide6.QtCore import QSettings
        from . import cormind
        with self._kilit:
            if self.cekim["durum"] == "calisiyor":
                return self._json(h, {"hata": "Zaten bir çekim sürüyor"}, 409)
            ayar = QSettings("Teknorot", "VardiyaPerformans")
            kul = str(ayar.value("cormind/kullanici", "") or "")
            try:
                sifre = base64.b64decode(str(ayar.value("cormind/sifre", "") or "")).decode("utf8")
            except Exception:  # noqa: BLE001
                sifre = ""
            if not kul or not sifre:
                return self._json(h, {"hata": "Cormind kullanıcı adı ve şifresi bu bilgisayarda kayıtlı değil. Bir kez programdan "
                                              "(Veri Aktar) girip çekim yapın; sonra web'den de çekilebilir."}, 400)
            con = self._con()
            try:
                ilk, son = self._aralik(q, con)
                a = vt.ayar_oku(con)
            finally:
                con.close()
            self.cekim = {"durum": "calisiyor", "metin": "Cormind'e bağlanılıyor…", "yuzde": 0, "dur": False,
                          "ilk": ilk.isoformat(), "son": son.isoformat(), "baslangic": time.time()}
        adres = a.get("cormind_adres", cormind.VARSAYILAN_ADRES)
        idler = a.get("cormind_makine_idleri") or cormind.VARSAYILAN_MAKINE_IDLERI

        def adim(b):
            n = b.get("parca_sayisi") or 1
            i = b.get("parca") or 1
            kayit, toplam = b.get("kayit") or 0, b.get("toplam") or 0
            ic = (kayit / toplam) if toplam else 0
            self.cekim["yuzde"] = int(100 * ((i - 1) + ic) / n)
            a_, s_ = b.get("ilk"), b.get("son")
            ara = f"{a_:%d.%m.%Y} – {s_:%d.%m.%Y}" if hasattr(a_, "strftime") and hasattr(s_, "strftime") else ""
            self.cekim["metin"] = (f"Adım {i}/{n} · {ara} · {kayit:,} / {toplam:,} kayıt".replace(",", ".")
                                   + (f" · şu ana kadar {b.get('kaydedilen'):,} kayıt kaydedildi".replace(",", ".") if b.get("kaydedilen") else ""))

        def calis():
            con = vt.ac(self.db_yolu)
            try:
                r = cormind.cek(con, adres, kul, sifre, ilk, son, idler, adim=adim, iptal=lambda: self.cekim["dur"], uzanan=True)
                self.cekim.update(durum="bitti", yuzde=100,
                                  metin=(("DURDURULDU: " if r.get("durduruldu") else "") + f"{r['toplam']:,} kayıt alındı ve kaydedildi.".replace(",", ".")))
                if self.yenilendi:
                    try:
                        self.gui.calistir(self.yenilendi, 120)
                    except Exception:  # noqa: BLE001
                        pass
            except Exception as ex:  # noqa: BLE001
                self.cekim.update(durum="hata", metin=f"Hata: {ex}")
            finally:
                con.close()
        threading.Thread(target=calis, name="web-cormind", daemon=True).start()
        self._json(h, {"tamam": True})

    def api_cek_durum(self, h, q):
        self._json(h, {k: v for k, v in self.cekim.items() if k != "dur"})

    def api_cek_durdur(self, h, q):
        self.cekim["dur"] = True
        self._json(h, {"tamam": True})

    # -------------------------------------------------------------- Outlook (senin bilgisayarındaki Outlook)
    def api_outlook(self, h, q):
        import sys
        from . import outlook, servis
        if sys.platform != "win32":
            return self._json(h, {"hata": "Outlook yalnızca Windows'ta okunabilir"}, 400)
        con = self._con()
        try:
            ilk, son = self._aralik(q, con)
        finally:
            con.close()
        if not self.gui.calistir(outlook.acik_mi, 30):
            try:
                self.gui.calistir(outlook.baslat, 30)
            except Exception as ex:  # noqa: BLE001
                return self._json(h, {"hata": str(ex)}, 500)
            return self._json(h, {"bilgi": "Outlook kapalıydı, sunucu bilgisayarında açılıyor. Posta kutusu yüklenince (yaklaşık "
                                           "20–30 saniye) tekrar basın."})

        def al():
            c = vt.ac(self.db_yolu)
            try:
                return servis.outlook_kot_al(c, ilk, son)
            finally:
                c.close()
        try:
            r = self.gui.calistir(al, 600)
        except RuntimeError as ex:
            return self._json(h, {"hata": str(ex)}, 500)
        if not r["mail"]:
            return self._json(h, {"bilgi": f"{ilk:%d.%m.%Y} – {son:%d.%m.%Y} arasında, göndereni '{r['gonderen']}' ve konusunda "
                                           f"'{r['konu']}' geçen mail bulunamadı."})
        self._json(h, {"bilgi": servis.outlook_ozet(r) + (("\n" + r["uyari"]) if r["uyari"] else "")})


def yerel_ip() -> str:
    """Bu bilgisayarın iç ağdaki IP adresi (ör. 192.168.x.x). Dışarıya hiçbir şey gönderilmez: yalnızca hangi ağ
    kartının kullanılacağı sorulur. Bulunamazsa bilgisayar adı döner."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
        finally:
            s.close()
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    try:
        ipler = [i for i in socket.gethostbyname_ex(socket.gethostname())[2] if not i.startswith("127.")]
        if ipler:
            return sorted(ipler, key=lambda i: (not i.startswith("192.168."), not i.startswith("10."), i))[0]
    except OSError:
        pass
    return socket.gethostname()


_SUNUCU: Optional[Sunucu] = None


def baslat(db_yolu: str, port: int = VARSAYILAN_PORT, yenilendi: Optional[Callable[[], None]] = None) -> Optional[str]:
    """Sunucuyu başlatır; adresini döndürür. Port kullanımdaysa (ör. program ikinci kez açıldıysa) None."""
    global _SUNUCU
    if _SUNUCU is not None:
        return _SUNUCU.adres()
    s = Sunucu(db_yolu, port, yenilendi)
    try:
        adres = s.baslat()
    except OSError:
        return None
    _SUNUCU = s
    return adres


def durdur():
    global _SUNUCU
    if _SUNUCU is not None:
        _SUNUCU.durdur()
        _SUNUCU = None


def ayarda_acik() -> bool:
    """Bu bilgisayarda sunucu açık mı? (Ayar bilgisayara özel: veri tabanı NAS'ta ortak olduğu için oraya yazılmaz.)"""
    from PySide6.QtCore import QSettings
    return str(QSettings("Teknorot", "VardiyaPerformans").value("web/acik", "0")) == "1"


def ayar_port() -> int:
    from PySide6.QtCore import QSettings
    try:
        return int(QSettings("Teknorot", "VardiyaPerformans").value("web/port", VARSAYILAN_PORT))
    except (TypeError, ValueError):
        return VARSAYILAN_PORT


def etkin() -> Optional[Sunucu]:
    return _SUNUCU
