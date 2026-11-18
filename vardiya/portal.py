"""Web portal sunucusu (Qt gerektirmez): cmd'den başlatılır, ağdaki herkes tarayıcıdan IP:port ile açar.

Yalnızca standart kütüphane + mevcut hesap/veri tabanı modüllerini kullanır. Her istek kendi SQLite bağlantısını açar.
İsteğe bağlı parola: VARDIYA_PAROLA ortam değişkeni verilirse tarayıcı parola ister (kullanıcı adı önemsiz).
"""
from __future__ import annotations

import base64
import hmac
import json
import mimetypes
import os
import re
import socket
import sys
import tempfile
import threading
import time
import traceback
from collections import OrderedDict
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Dict, Optional
from urllib.parse import parse_qs, unquote, urlparse

from . import veritabani as vt
from .hesap import HesapAyar, bozuk_indeksler, cormind_hesabi, durus_dokumu, hesapla
from .surum import SURUM

AZAMI_YUKLEME = 200 * 1024 * 1024
AZAMI_GUN = 800


class Hata(Exception):
    def __init__(self, mesaj: str, kod: int = 400):
        super().__init__(mesaj)
        self.kod = kod


class Ikili:
    def __init__(self, veri: bytes, tur: str):
        self.veri, self.tur = veri, tur


def kaynak_klasoru() -> str:
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _json_varsayilan(o):
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    if is_dataclass(o) and not isinstance(o, type):
        return asdict(o)
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    if isinstance(o, float):
        return None
    return str(o)


def _tarih(s) -> date:
    try:
        return date.fromisoformat(str(s))
    except ValueError:
        raise Hata(f"Geçersiz tarih: {s!r}")


def _json(govde: bytes) -> dict:
    try:
        v = json.loads(govde.decode("utf-8") or "{}")
    except ValueError:
        raise Hata("Geçersiz JSON")
    if not isinstance(v, dict):
        raise Hata("JSON nesnesi bekleniyor")
    return v


# ---------------------------------------------------------------------------------------------- durum
class Portal:
    def __init__(self, db_yolu: str):
        self.db_yolu = db_yolu
        self.kilit = threading.Lock()
        self.onbellek: "OrderedDict[tuple, dict]" = OrderedDict()
        self.is_: dict = {"calisiyor": False}          # Cormind çekim işi
        self.iptal = threading.Event()
        self.parola = os.environ.get("VARDIYA_PAROLA", "")

    def db_imzasi(self):
        try:
            s = os.stat(self.db_yolu)
            return s.st_mtime_ns, s.st_size
        except OSError:
            return (0, 0)


def hesap_ayar(a: dict) -> HesapAyar:
    return HesapAyar(esik=a["esik"], vardiya_dk=a["vardiya_dk"], yemek_dk=a["yemek_dk"], cay_dk=a["cay_dk"],
                     kural="gunluk", yontem=a.get("hesap_yontemi", "vardiya"))


def _donem(con, q: dict):
    if not q.get("ilk") or not q.get("son"):
        raise Hata("ilk ve son tarih gerekli")
    ilk, son = _tarih(q["ilk"]), _tarih(q["son"])
    if son < ilk or (son - ilk).days > AZAMI_GUN:
        raise Hata("Tarih aralığı geçersiz")
    haric = {_tarih(x) for x in q.get("haric", "").split(",") if x}
    tum = [ilk + timedelta(days=i) for i in range((son - ilk).days + 1)]
    kapsam = vt.gun_kapsami(con)
    secili = [g for g in tum if g not in haric]
    gunler = sorted(set(secili) | {g for g in tum if not kapsam.get(g)})
    return ilk, son, secili, gunler, kapsam, vt.ayar_oku(con)


def _sonuc_json(s) -> dict:
    return {
        "genel": list(s.genel),
        "vardiyalar": {str(v): {"gun_sayisi": o.gun_sayisi, "makine_sayisi": o.makine_sayisi, "calisma": o.calisma,
                                "durus": o.durus, "mola": o.mola,
                                "gunluk_sayilar": {d.isoformat(): n for d, n in o.gunluk_sayilar.items()}}
                       for v, o in s.vardiyalar.items()},
        "hucreler": {m: {str(v): list(t) for v, t in h.items()} for m, h in s.hucreler.items()},
        "makine_ort": {m: list(t) for m, t in s.makine_ort.items()},
        "verisiz_gunler": [d.isoformat() for d in s.verisiz_gunler],
        "bos_vardiyalar": [[d.isoformat(), v] for d, v in s.bos_vardiyalar],
        "esik_alti": {m: list(t) for m, t in s.esik_alti.items()},
        "bozuk": s.bozuk_kayit,
        "hesap_gunu": s.hesap_gunu(),
    }


# ---------------------------------------------------------------------------------------------- uç noktalar
def r_durum(P: Portal, con, q, g):
    kapsam = vt.gun_kapsami(con)
    return {"surum": SURUM, "ayar": vt.ayar_oku(con), "kapsam": {d.isoformat(): n for d, n in kapsam.items()},
            "toplam_kayit": con.execute("SELECT COUNT(*) FROM kayit").fetchone()[0],
            "tipler": [r[0] for r in con.execute("SELECT DISTINCT tip FROM kayit ORDER BY tip")],
            "makineler_kayitta": vt.makineler_kayitta(con), "parola": bool(P.parola)}


def r_hesap(P: Portal, con, q, g):
    ilk, son, secili, gunler, kapsam, ayar = _donem(con, q)
    anahtar = (P.db_imzasi(), ilk, son, tuple(secili), json.dumps(ayar, sort_keys=True, ensure_ascii=False))
    with P.kilit:
        if anahtar in P.onbellek:
            P.onbellek.move_to_end(anahtar)
            return P.onbellek[anahtar]
    seflar = vt.sef_getir(con, secili, ayar)
    if not secili:
        sonuc = {"bos": True, "seflar": {str(k): v for k, v in seflar.items()}, "secili": [], "ayar": ayar}
    else:
        kayit = vt.kayitlari_getir(con, min(gunler), max(gunler))
        ha = hesap_ayar(ayar)
        s = hesapla(kayit, gunler, ha, set(kapsam))
        sonuc = _sonuc_json(s)
        sonuc.update({
            "bos": False, "secili": [d.isoformat() for d in secili], "ayar": ayar,
            "seflar": {str(k): v for k, v in seflar.items()},
            "durus": durus_dokumu(kayit, secili),
            "cormind": cormind_hesabi(kayit, secili, ayar["makineler"], ha),
            "kayit_sayisi": len(kayit),
        })
    with P.kilit:
        P.onbellek[anahtar] = sonuc
        while len(P.onbellek) > 12:
            P.onbellek.popitem(last=False)
    return sonuc


def r_operator(P: Portal, con, q, g):
    from .operator import operatorleri_hesapla
    ilk, son, secili, gunler, kapsam, ayar = _donem(con, q)
    if not secili:
        return {"operatorler": []}
    kayit = vt.kayitlari_getir_operatorlu(con, min(gunler), max(gunler))
    sonuc = operatorleri_hesapla(kayit, secili, hesap_ayar(ayar), None, ayar.get("operator_haric_durus", []))
    cikti = []
    for ad, r in sonuc.items():
        cikti.append({
            "ad": ad, "makine_sayisi": r.makine_sayisi, "calisma": r.calisma_orani, "durus": r.durus_orani, "mola": r.mola_orani,
            "calisma_sn": r.calisma_sn, "durus_sn": r.durus_sn, "mola_sn": r.mola_sn, "cakisan_sn": r.cakisan_sn,
            "setup_sn": r.setup_sn, "setup_kayip_sn": r.setup_kayip_sn, "bosta_sn": r.hepsi_calisirken_sn,
            "bosta_orani": r.bosta_orani, "aktif_sn": r.aktif_sn, "plansiz_sn": r.plansiz_sn, "belgesiz_sn": r.belgesiz_sn,
            "haric_sn": r.haric_sn, "en_uzun_durus_sn": r.en_uzun_durus_sn, "durus_adedi": r.durus_adedi,
            "mola_asimi_sn": r.mola_asimi_sn, "ort_makine": r.ort_makine, "durus_tipleri": r.durus_tipleri,
            "makineler": r.makineler, "gunler": {d.isoformat(): v for d, v in r.gunler.items()}, "gun_sayisi": r.gun_sayisi,
        })
    cikti.sort(key=lambda x: -(x["calisma"] or 0))
    return {"operatorler": cikti}


def r_yukle(P: Portal, con, q, g):
    from .ice_aktar import aktar
    ad = os.path.basename(unquote(q.get("ad", "dosya.xlsx"))) or "dosya.xlsx"
    ext = os.path.splitext(ad)[1].lower()
    if ext not in (".xlsx", ".xlsm", ".xls", ".html", ".htm"):
        raise Hata("Desteklenen dosya türleri: .xlsx, .xlsm, .xls, .html")
    if not g:
        raise Hata("Dosya boş")
    klasor = tempfile.mkdtemp(prefix="vardiya_yukle_")
    yol = os.path.join(klasor, "yuklenen" + ext)
    try:
        with open(yol, "wb") as f:
            f.write(g)
        s = aktar(con, yol)
    finally:
        try:
            os.remove(yol)
            os.rmdir(klasor)
        except OSError:
            pass
    with P.kilit:
        P.onbellek.clear()
    return {"dosya": ad, "ozet": s.ozet(), "toplam": s.toplam, "yeni": s.yeni, "guncellenen": s.guncellenen, "ayni": s.ayni,
            "atlanan": [[n, str(m)] for n, m in s.atlanan[:25]], "atlanan_sayisi": len(s.atlanan),
            "ilk_gun": s.ilk_gun, "son_gun": s.son_gun, "yeni_makineler": s.yeni_makineler}


def _ayar_temizle(k: str, v):
    if k == "esik":
        v = float(v)
        if not 0.05 <= v <= 1.0:
            raise Hata("Eşik %5 ile %100 arasında olmalı")
        return v
    if k in ("vardiya_dk", "yemek_dk", "cay_dk"):
        v = int(v)
        if not 0 <= v <= 1440:
            raise Hata(f"{k} 0-1440 arasında olmalı")
        return v
    if k == "hesap_kurali":
        if v not in ("gunluk", "donem"):
            raise Hata("Geçersiz hesap kuralı")
        return v
    if k == "hesap_yontemi":
        if v not in ("vardiya", "gun", "hucre"):
            raise Hata("Geçersiz hesap yöntemi")
        return v
    if k in ("makineler", "sefler", "operator_haric_durus"):
        if not isinstance(v, list):
            raise Hata(f"{k} liste olmalı")
        sonuc = []
        for x in v:
            x = str(x).strip()
            if x and x not in sonuc:
                sonuc.append(x)
        return sonuc
    if k == "cormind_makine_idleri":
        return [int(x) for x in v]
    if k == "vardiya_sef":
        return {str(i): str((v or {}).get(str(i), "")).strip() for i in (1, 2, 3)}
    if k == "cormind_adres":
        v = str(v).strip()
        if not v.startswith(("http://", "https://")):
            raise Hata("Cormind adresi http:// ile başlamalı")
        return v.rstrip("/")
    if k == "idle_makineleri_goster":
        return bool(v)
    raise KeyError(k)


def r_ayar_yaz(P: Portal, con, q, g):
    veri = _json(g)
    yazilan = []
    for k, v in veri.items():
        try:
            temiz = _ayar_temizle(k, v)
        except KeyError:
            continue
        except (TypeError, ValueError):
            raise Hata(f"Geçersiz değer: {k}")
        vt.ayar_yaz(con, k, temiz)
        yazilan.append(k)
    with P.kilit:
        P.onbellek.clear()
    return {"yazilan": yazilan, "ayar": vt.ayar_oku(con)}


def r_sef(P: Portal, con, q, g):
    v = _json(g)
    gunler = [_tarih(x) for x in v.get("gunler", [])]
    vardiya = int(v.get("vardiya", 0))
    sef = str(v.get("sef", "")).strip()
    if vardiya not in (1, 2, 3) or not sef or not gunler:
        raise Hata("gunler, vardiya (1-3) ve sef gerekli")
    vt.sef_ata(con, gunler, vardiya, sef)
    with P.kilit:
        P.onbellek.clear()
    return {"tamam": True}


def r_kayitlar(P: Portal, con, q, g):
    ilk, son = _tarih(q.get("ilk")), _tarih(q.get("son"))
    kos, par = ["baslangic < ?", "bitis >= ?"], [(son + timedelta(days=1)).strftime("%Y-%m-%d 00:00:00"), ilk.strftime("%Y-%m-%d 00:00:00")]
    if q.get("makine"):
        kos.append("makine = ?")
        par.append(q["makine"])
    if q.get("tip"):
        kos.append("tip = ?")
        par.append(q["tip"])
    satir = con.execute("SELECT rowid AS no, makine, tip, baslangic, bitis, operator, is_emri, urun_kodu, urun_adi FROM kayit WHERE "
                        + " AND ".join(kos) + " ORDER BY baslangic, makine", par).fetchall()
    liste = [(r["makine"], r["tip"], datetime.strptime(r["baslangic"], vt.BICIM), datetime.strptime(r["bitis"], vt.BICIM)) for r in satir]
    bozuk = bozuk_indeksler(liste)
    secilen = [i for i in range(len(satir)) if (i in bozuk or q.get("bozuk") != "1")]
    limit = max(1, min(int(q.get("limit", 500)), 3000))
    return {"toplam": len(secilen), "bozuk_sayisi": len(bozuk), "gosterilen": min(limit, len(secilen)),
            "satirlar": [dict(satir[i], bozuk=i in bozuk) for i in secilen[:limit]]}


def r_kayit_sil(P: Portal, con, q, g):
    nolar = [int(x) for x in _json(g).get("nolar", [])]
    if not nolar:
        raise Hata("Silinecek kayıt seçilmedi")
    con.executemany("DELETE FROM kayit WHERE rowid = ?", [(n,) for n in nolar])
    con.commit()
    with P.kilit:
        P.onbellek.clear()
    return {"silinen": len(nolar)}


def r_gecmis(P: Portal, con, q, g):
    return {"aktarim": vt.aktarim_gecmisi(con, 50), "arsiv": vt.arsiv_liste(con)}


def r_arsiv_yaz(P: Portal, con, q, g):
    v = _json(g)
    html = str(v.get("html", ""))
    if not html or len(html) > 30_000_000:
        raise Hata("Rapor içeriği boş ya da çok büyük")
    ad = str(v.get("ad") or "Rapor").strip()[:120]
    i = vt.arsiv_kaydet(con, ad, "web-" + str(v.get("tur", "rapor"))[:20], str(v.get("ilk", "")), str(v.get("son", "")),
                        "{}", json.dumps({"web_html": html}, ensure_ascii=False))
    return {"id": i}


def r_arsiv_ac(P: Portal, con, q, g):
    r = vt.arsiv_getir(con, int(q.get("id", 0)))
    if not r:
        raise Hata("Arşiv kaydı bulunamadı", 404)
    try:
        html = json.loads(r["sonuc_json"] or "{}").get("web_html")
    except ValueError:
        html = None
    if r.get("pdf"):
        return Ikili(bytes(r["pdf"]), "application/pdf")
    if not html:
        raise Hata("Bu kayıt masaüstü programda oluşturulmuş; web portalda açılamaz (PDF'i yoksa)", 404)
    return Ikili(html.encode("utf-8"), "text/html; charset=utf-8")


def r_arsiv_sil(P: Portal, con, q, g):
    vt.arsiv_sil(con, int(_json(g).get("id", 0)))
    return {"tamam": True}


def r_gorsel_oku(P: Portal, con, q, g):
    png = vt.gorsel_oku(con, "web_" + re.sub(r"[^\w.-]", "", q.get("anahtar", "cormind"))[:60])
    if not png:
        raise Hata("Görsel yok", 404)
    return Ikili(bytes(png), "image/png")


def r_gorsel_yaz(P: Portal, con, q, g):
    if not g.startswith(b"\x89PNG"):
        raise Hata("Yalnızca PNG görsel kabul edilir")
    vt.gorsel_yaz(con, "web_" + re.sub(r"[^\w.-]", "", q.get("anahtar", "cormind"))[:60], g)
    return {"tamam": True}


def r_gorsel_sil(P: Portal, con, q, g):
    vt.gorsel_sil(con, "web_" + re.sub(r"[^\w.-]", "", q.get("anahtar", "cormind"))[:60])
    return {"tamam": True}


def r_kot_yaz(P: Portal, con, q, g):
    from .kot import kot_coz
    metin = str(_json(g).get("metin", ""))
    kotlar = kot_coz(metin)
    if not kotlar:
        raise Hata("Metinde KOT kaydı bulunamadı (=== KOT === ... === SON === biçimi bekleniyor)")
    yeni, guncel = vt.kot_yaz(con, kotlar)
    return {"yeni": yeni, "guncellenen": guncel}


def r_kot_getir(P: Portal, con, q, g):
    ilk, son = _tarih(q.get("ilk")), _tarih(q.get("son"))
    return {"kotlar": [asdict(k) for k in vt.kot_getir(con, ilk, son)]}


def r_kot_sil(P: Portal, con, q, g):
    v = _json(g)
    return {"silinen": vt.kot_sil(con, _tarih(v.get("ilk")), _tarih(v.get("son")))}


def r_idari(P: Portal, con, q, g):
    from .kot import idari_icerik, metne_cevir
    ilk, son, secili, gunler, kapsam, ayar = _donem(con, q)
    if not secili:
        raise Hata("Dönemde seçili gün yok")
    kayit = vt.kayitlari_getir(con, min(gunler), max(gunler))
    ha = hesap_ayar(ayar)
    cm = cormind_hesabi(kayit, secili, ayar["makineler"], ha)
    s = hesapla(kayit, gunler, ha, set(kapsam))
    calisma = {m: (s.makine_ort.get(m) or (None,))[0] for m in ayar["makineler"]}
    ic = idari_icerik(vt.kot_getir(con, ilk, son), cm, calisma)
    return {"ic": ic, "metin": metne_cevir(ic)}


# ---------------------------------------------------------------------------------------------- Cormind çekimi (arka plan)
def r_cormind_baslat(P: Portal, con, q, g):
    from . import cormind
    v = _json(g)
    ilk, son = _tarih(v.get("ilk")), _tarih(v.get("son"))
    kullanici, sifre = str(v.get("kullanici", "")).strip(), str(v.get("sifre", ""))
    if son < ilk or not kullanici or not sifre:
        raise Hata("Kullanıcı, parola ve geçerli tarih aralığı gerekli")
    ayar = vt.ayar_oku(con)
    with P.kilit:
        if P.is_.get("calisiyor"):
            raise Hata("Bir çekim zaten sürüyor")
        P.iptal.clear()
        P.is_ = {"calisiyor": True, "bilgi": {}, "bitti": False, "hata": None, "sonuc": None}

    def calis():
        con2 = vt.ac(P.db_yolu)
        try:
            def adim(b: dict):
                with P.kilit:
                    P.is_["bilgi"] = {k: (x.isoformat() if isinstance(x, date) else x) for k, x in b.items()}

            sonuc = cormind.cek(con2, ayar["cormind_adres"], kullanici, sifre, ilk, son, ayar["cormind_makine_idleri"],
                                adim=adim, iptal=P.iptal.is_set)
            with P.kilit:
                P.is_["sonuc"] = json.loads(json.dumps(sonuc, default=_json_varsayilan))
        except Exception as ex:  # noqa: BLE001
            with P.kilit:
                P.is_["hata"] = str(ex) or ex.__class__.__name__
        finally:
            con2.close()
            with P.kilit:
                P.is_["calisiyor"], P.is_["bitti"] = False, True
                P.onbellek.clear()

    threading.Thread(target=calis, daemon=True).start()
    return {"basladi": True}


def r_cormind_durum(P: Portal, con, q, g):
    with P.kilit:
        return json.loads(json.dumps(P.is_, default=_json_varsayilan))


def r_cormind_durdur(P: Portal, con, q, g):
    P.iptal.set()
    return {"tamam": True}


ROTALAR: Dict[tuple, Callable] = {
    ("GET", "/api/durum"): r_durum, ("GET", "/api/hesap"): r_hesap, ("GET", "/api/operator"): r_operator,
    ("POST", "/api/yukle"): r_yukle, ("POST", "/api/ayar"): r_ayar_yaz, ("POST", "/api/sef"): r_sef,
    ("GET", "/api/kayitlar"): r_kayitlar, ("POST", "/api/kayit_sil"): r_kayit_sil, ("GET", "/api/gecmis"): r_gecmis,
    ("POST", "/api/arsiv"): r_arsiv_yaz, ("GET", "/api/arsiv"): r_arsiv_ac, ("POST", "/api/arsiv_sil"): r_arsiv_sil,
    ("GET", "/api/gorsel"): r_gorsel_oku, ("POST", "/api/gorsel"): r_gorsel_yaz, ("POST", "/api/gorsel_sil"): r_gorsel_sil,
    ("POST", "/api/kot"): r_kot_yaz, ("GET", "/api/kot"): r_kot_getir, ("POST", "/api/kot_sil"): r_kot_sil,
    ("GET", "/api/idari"): r_idari,
    ("POST", "/api/cormind/baslat"): r_cormind_baslat, ("GET", "/api/cormind/durum"): r_cormind_durum,
    ("POST", "/api/cormind/durdur"): r_cormind_durdur,
}

_STATIK = re.compile(r"^[\w.-]+$")


class Isleyici(BaseHTTPRequestHandler):
    server_version = "VardiyaPortal/" + SURUM
    protocol_version = "HTTP/1.1"
    portal: Portal = None  # type: ignore

    def log_message(self, bicim, *a):  # noqa: D401
        if os.environ.get("VARDIYA_ERISIM_KAYDI") == "1":
            sys.stderr.write("%s %s\n" % (self.address_string(), bicim % a))

    def _gonder(self, kod: int, veri: bytes, tur: str, ek: Optional[dict] = None):
        self.send_response(kod)
        self.send_header("Content-Type", tur)
        self.send_header("Content-Length", str(len(veri)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (ek or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(veri)

    def _json_gonder(self, kod: int, nesne):
        self._gonder(kod, json.dumps(nesne, ensure_ascii=False, default=_json_varsayilan).encode("utf-8"),
                     "application/json; charset=utf-8")

    def _yetkili(self) -> bool:
        parola = self.portal.parola
        if not parola:
            return True
        b = self.headers.get("Authorization", "")
        if b.startswith("Basic "):
            try:
                _kul, _, p = base64.b64decode(b[6:]).decode("utf-8").partition(":")
                return hmac.compare_digest(p.encode("utf-8"), parola.encode("utf-8"))
            except Exception:  # noqa: BLE001
                return False
        return False

    def _statik(self, yol: str):
        ad = "index.html" if yol in ("/", "") else yol[len("/static/"):]
        if not _STATIK.match(ad):
            return self._json_gonder(404, {"hata": "Bulunamadı"})
        kok = kaynak_klasoru()
        for klasor in (("assets", "portal"), ("assets", "web"), ("assets",)):
            f = os.path.join(kok, *klasor, ad)
            if os.path.isfile(f):
                tur = mimetypes.guess_type(f)[0] or "application/octet-stream"
                if tur.startswith("text/") or tur in ("application/javascript",):
                    tur += "; charset=utf-8"
                with open(f, "rb") as fh:
                    return self._gonder(200, fh.read(), tur)
        return self._json_gonder(404, {"hata": "Bulunamadı"})

    def _isle(self):
        try:
            if not self._yetkili():
                return self._gonder(401, b"Parola gerekli", "text/plain; charset=utf-8",
                                    {"WWW-Authenticate": 'Basic realm="Vardiya Performans"'})
            u = urlparse(self.path)
            yol = u.path
            if self.command in ("GET", "HEAD") and (yol == "/" or yol.startswith("/static/")):
                return self._statik(yol)
            fn = ROTALAR.get((self.command if self.command != "HEAD" else "GET", yol))
            if not fn:
                return self._json_gonder(404, {"hata": "Böyle bir adres yok"})
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            n = int(self.headers.get("Content-Length") or 0)
            if n > AZAMI_YUKLEME:
                return self._json_gonder(413, {"hata": "Dosya çok büyük"})
            govde = self.rfile.read(n) if n else b""
            con = vt.ac(self.portal.db_yolu)
            try:
                sonuc = fn(self.portal, con, q, govde)
            finally:
                con.close()
            if isinstance(sonuc, Ikili):
                return self._gonder(200, sonuc.veri, sonuc.tur)
            return self._json_gonder(200, sonuc)
        except Hata as h:
            return self._json_gonder(h.kod, {"hata": str(h)})
        except (BrokenPipeError, ConnectionResetError):
            return None
        except Exception as ex:  # noqa: BLE001
            sys.stderr.write(traceback.format_exc())
            try:
                return self._json_gonder(500, {"hata": f"Sunucu hatası: {ex}"})
            except Exception:  # noqa: BLE001
                return None

    do_GET = do_POST = do_HEAD = _isle


def yerel_adresler() -> list:
    ipler = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))                  # paket gönderilmez; yalnızca çıkış arayüzünü seçtirir
        ipler.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip not in ipler and not ip.startswith("127."):
                ipler.append(ip)
    except OSError:
        pass
    return ipler


class _Sunucu(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError)):    # tarayıcı bağlantıyı kapattı: sorun değil
            return
        super().handle_error(request, client_address)


def sunucu_kur(db_yolu: str, port: int = 8443, ev: str = "0.0.0.0") -> ThreadingHTTPServer:
    vt.ac(db_yolu).close()                                # dosya/şema hazır olsun
    P = Portal(db_yolu)
    sinif = type("PortalIsleyici", (Isleyici,), {"portal": P})
    srv = _Sunucu((ev, port), sinif)
    srv.daemon_threads = True
    srv.portal = P  # type: ignore[attr-defined]
    return srv


def baslat(db_yolu: str, port: int = 8443, ev: str = "0.0.0.0") -> int:
    try:
        srv = sunucu_kur(db_yolu, port, ev)
    except OSError as ex:
        print(f"HATA: {ev}:{port} açılamadı ({ex}). Port başka bir programda kullanılıyor olabilir; --port ile başka bir sayı verin.")
        return 1
    print(f"Vardiya Performans web portalı {SURUM}")
    print(f"Veri tabanı: {os.path.abspath(db_yolu)}")
    print("Tarayıcıdan şu adreslerden açın (aynı ağdaki herkes):")
    for ip in yerel_adresler():
        print(f"   http://{ip}:{port}")
    print(f"   http://localhost:{port}   (bu bilgisayarda)")
    if srv.portal.parola:  # type: ignore[attr-defined]
        print("Parola koruması açık (VARDIYA_PAROLA).")
    print("Kapatmak için Ctrl+C. Diğer bilgisayarlar açamazsa Windows Güvenlik Duvarı'nda bu port'a izin verin.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nKapatıldı.")
    finally:
        srv.server_close()
    return 0
