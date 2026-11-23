"""GEÇİCİ geliştirici bağlantısı (köprü). İş bitince bu dosya ve Ayarlar'daki kartı tamamen kaldırılacak.

Nasıl çalışır: kullanıcının GitHub hesabındaki ÖZEL 'vp-kopru' deposu aracıdır. Geliştirici (Claude) komut dosyasını
komut/<bilgisayar>.json olarak yazar; program açıkken birkaç saniyede bir bakar, yeni komutu çalıştırır ve sonucu
sonuc/<bilgisayar>/<no>.json olarak yazar.

Sınırlar:
- Yalnızca kullanıcı Ayarlar'dan açınca çalışır; SURE_SAAT sonra kendiliğinden kapanır; açıkken ana pencerede görünür.
- Erişim anahtarı yalnızca bu bilgisayarda (QSettings) durur; hiçbir yere gönderilmez, kayıtlara yazılmaz.
- Yalnızca aşağıdaki KOMUTLAR çalışır: bilgisayarda komut çalıştırma, dosya okuma/yazma YOKTUR. Veri tabanı yalnızca
  okunur (salt okunur bağlantı, SELECT). Personel sisteminin şifresi ve oturum bilgisi hiçbir komutla alınamaz.
"""
from __future__ import annotations

import base64
import json
import os
import socket
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from typing import Optional

from PySide6.QtCore import QObject, QSettings, QTimer, Signal

DEPO = "81Miralay81/vp-kopru"
API = f"https://api.github.com/repos/{DEPO}/contents/"
SURE_SAAT = 8
ARALIK_SN = 6
_AYAR = ("Teknorot", "VardiyaPerformans")


def bilgisayar() -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in (socket.gethostname() or "pc"))[:40]


def jeton_oku() -> str:
    try:
        return base64.b64decode(str(QSettings(*_AYAR).value("kopru/jeton", "") or "")).decode("utf8").strip()
    except Exception:  # noqa: BLE001
        return ""


def jeton_yaz(j: str) -> None:
    QSettings(*_AYAR).setValue("kopru/jeton", base64.b64encode(j.strip().encode("utf8")).decode("ascii") if j.strip() else "")


def bitis() -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(QSettings(*_AYAR).value("kopru/bitis", "") or ""))
    except ValueError:
        return None


def acik_mi() -> bool:
    b = bitis()
    return bool(b and b > datetime.now() and jeton_oku())


def _istek(yontem: str, yol: str, govde: Optional[dict] = None) -> dict:
    j = jeton_oku()
    veri = json.dumps(govde).encode("utf8") if govde is not None else None
    r = urllib.request.Request(API + yol, data=veri, method=yontem, headers={
        "User-Agent": "VardiyaPerformans-kopru", "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {j}", "X-GitHub-Api-Version": "2022-11-28",
        **({"Content-Type": "application/json"} if veri else {})})
    with urllib.request.urlopen(r, timeout=20) as y:
        return json.loads(y.read().decode("utf8") or "{}")


def _dosya_yaz(yol: str, icerik: bytes, mesaj: str) -> None:
    sha = None
    try:
        sha = _istek("GET", yol).get("sha")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
    _istek("PUT", yol, {"message": mesaj, "content": base64.b64encode(icerik).decode("ascii"), **({"sha": sha} if sha else {})})


class Kopru(QObject):
    """Ana pencereye bağlanır; komutlar ana iş parçacığında çalışır, ağ işleri arka planda."""
    durum_degisti = Signal(str)
    _komut_geldi = Signal(dict)
    _hata = Signal(str)

    def __init__(self, ana):
        super().__init__(ana)
        self.ana = ana
        self.pc = bilgisayar()
        self.durum = ""
        self._mesgul = False
        self._son_id = str(QSettings(*_AYAR).value("kopru/son_id", "") or "")
        self._komut_geldi.connect(self._calistir)
        self._hata.connect(lambda m: self._yaz(f"bağlantı hatası: {m}"))
        self.zaman = QTimer(self)
        self.zaman.timeout.connect(self._tik)
        self.zaman.start(ARALIK_SN * 1000)
        QTimer.singleShot(1500, self._tik)

    # ------------------------------------------------ açma / kapatma
    def ac(self, jeton: str = "") -> None:
        if jeton:
            jeton_yaz(jeton)
        QSettings(*_AYAR).setValue("kopru/bitis", (datetime.now() + timedelta(hours=SURE_SAAT)).isoformat(timespec="seconds"))
        self._yaz("açılıyor…")
        self._tik()

    def kapat(self, anahtari_sil: bool = False) -> None:
        QSettings(*_AYAR).setValue("kopru/bitis", "")
        if anahtari_sil:
            jeton_yaz("")
        self._yaz("")

    def _yaz(self, metin: str) -> None:
        b = bitis()
        if acik_mi():
            self.durum = f"Geliştirici bağlantısı AÇIK ({b:%H:%M}'e kadar) · {metin}" if metin else f"Geliştirici bağlantısı AÇIK ({b:%H:%M}'e kadar)"
        else:
            self.durum = metin
        self.durum_degisti.emit(self.durum)

    # ------------------------------------------------ komut yoklama (arka planda)
    def _tik(self) -> None:
        if not acik_mi():
            if bitis() and bitis() <= datetime.now():
                QSettings(*_AYAR).setValue("kopru/bitis", "")
                self._yaz("süre doldu, bağlantı kapandı")
            return
        if self._mesgul:
            return
        self._mesgul = True

        def is_():
            try:
                d = _istek("GET", f"komut/{self.pc}.json")
                k = json.loads(base64.b64decode(d.get("content", "")).decode("utf8") or "{}")
                if isinstance(k, dict) and str(k.get("id", "")) and str(k.get("id")) != self._son_id:
                    self._komut_geldi.emit(k)
                else:
                    self._yazilacak = "bekliyor"
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    self._yazilacak = "bekliyor (henüz komut yok)"
                else:
                    self._hata.emit(f"HTTP {e.code} (anahtarın 'vp-kopru' deposuna okuma-yazma izni olmalı)")
            except Exception as e:  # noqa: BLE001
                self._hata.emit(f"{type(e).__name__}: {e}")
            finally:
                self._mesgul = False
        self._yazilacak = None
        threading.Thread(target=is_, daemon=True).start()
        QTimer.singleShot(3000, lambda: self._yazilacak and self._yaz(self._yazilacak))

    def _sonuc_gonder(self, kid: str, sonuc: dict, ekler: Optional[dict] = None) -> None:
        def is_():
            try:
                for ad, icerik in (ekler or {}).items():
                    _dosya_yaz(f"sonuc/{self.pc}/{kid}_{ad}", icerik, f"sonuc {kid} {ad}")
                _dosya_yaz(f"sonuc/{self.pc}/{kid}.json", json.dumps(sonuc, ensure_ascii=False, indent=1, default=str).encode("utf8"),
                           f"sonuc {kid}")
            except Exception as e:  # noqa: BLE001
                self._hata.emit(f"sonuç gönderilemedi: {type(e).__name__}: {e}")
        threading.Thread(target=is_, daemon=True).start()

    # ------------------------------------------------ komutlar (ana iş parçacığı)
    def _calistir(self, k: dict) -> None:
        kid, tur, arg = str(k.get("id")), str(k.get("tur") or ""), k.get("arg") or {}
        self._son_id = kid
        QSettings(*_AYAR).setValue("kopru/son_id", kid)
        self._yaz(f"komut {kid}: {tur}")
        try:
            from . import teshis
            teshis.adim(f"geliştirici bağlantısı: komut {kid} ({tur})")
        except Exception:  # noqa: BLE001
            pass
        f = getattr(self, "_k_" + tur, None)
        if f is None:
            self._sonuc_gonder(kid, {"id": kid, "hata": f"bilinmeyen komut: {tur}", "komutlar": KOMUTLAR})
            return
        try:
            f(kid, arg)
        except Exception as e:  # noqa: BLE001
            import traceback
            self._sonuc_gonder(kid, {"id": kid, "tur": tur, "hata": f"{type(e).__name__}: {e}", "iz": traceback.format_exc()[-3000:]})

    def _bitti(self, kid: str, tur: str, veri, ekler: Optional[dict] = None) -> None:
        self._sonuc_gonder(kid, {"id": kid, "tur": tur, "zaman": datetime.now().isoformat(timespec="seconds"), "sonuc": veri}, ekler)
        self._yaz(f"komut {kid} ({tur}) tamam")

    def _pv(self):
        from . import personel_pencere as pp
        acik = [w for w in list(pp._PENCERELER) if w.isVisible() or w.otomatik]
        return acik[0] if acik else None

    def _k_durum(self, kid, arg):
        from . import surum
        pv = self._pv()
        oto = getattr(getattr(self.ana, "oto", None), "durum", "")
        self._bitti(kid, "durum", {"surum": getattr(surum, "SURUM", "?"), "pc": self.pc, "db": getattr(self.ana, "db_yolu", ""),
                                   "kullanici": (getattr(self.ana, "kullanici", None) or {}).get("ad"),
                                   "personel_penceresi": bool(pv), "otomatik_cekim": oto,
                                   "sayfa": self.ana.sira[self.ana.yigin.currentIndex()] if hasattr(self.ana, "sira") else ""})

    def _k_tani(self, kid, arg):
        from . import teshis
        n = int(arg.get("satir", 300))
        try:
            with open(teshis.kayit_yolu(), encoding="utf8", errors="replace") as fh:
                acilis = fh.read().splitlines()[-n:]
        except OSError:
            acilis = []
        pv = self._pv()
        self._bitti(kid, "tani", {"personel_veri": (pv._tani[-n:] if pv else None), "acilis_kaydi": acilis})

    def _k_ekran(self, kid, arg):
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        hedef = self._pv() if arg.get("pencere") == "personel" else self.ana
        if hedef is None:
            self._bitti(kid, "ekran", {"hata": "personel penceresi açık değil"})
            return
        pm = hedef.grab()
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        pm.save(buf, "PNG")
        self._bitti(kid, "ekran", {"dosya": f"{kid}_ekran.png", "boyut": [pm.width(), pm.height()]}, {"ekran.png": bytes(ba)})

    def _k_sayfa_ac(self, kid, arg):
        self.ana.sayfa_ac(str(arg.get("sayfa", "performans")))
        self._bitti(kid, "sayfa_ac", "tamam")

    def _k_pv_ac(self, kid, arg):
        pv = self._pv()
        if pv is None:
            from . import personel_pencere
            s = self.ana.sayfalar.get("personel")
            self._pv_ref = personel_pencere.ac(self.ana.db_yolu, self.ana, kapaninca=(s.yenile if s is not None else None))
        self._bitti(kid, "pv_ac", "açıldı" if pv is None else "zaten açık")

    def _k_pv_js(self, kid, arg):
        pv = self._pv()
        if pv is None:
            self._bitti(kid, "pv_js", {"hata": "personel penceresi açık değil (önce pv_ac)"})
            return
        kod = str(arg.get("kod", ""))
        sar = "(function(){ try { var __s = (function(){ " + kod + " })(); return JSON.stringify(__s === undefined ? null : __s); } " \
              "catch(e) { return JSON.stringify({hata: String(e)}); } })();"
        pv.sayfa.runJavaScript(sar, 0, lambda r: self._bitti(kid, "pv_js", (r or "")[:300000]))

    def _k_pv_cek(self, kid, arg):
        from datetime import date
        pv = self._pv()
        if pv is None:
            self._bitti(kid, "pv_cek", {"hata": "personel penceresi açık değil (önce pv_ac)"})
            return
        ilk, son = date.fromisoformat(arg["ilk"]), date.fromisoformat(arg["son"])
        pv.donem_cek(ilk, son, lambda ok, n, a: pv.tani(f"geliştirici çekimi bitti: {a}"))
        self._bitti(kid, "pv_cek", f"başlatıldı {ilk} – {son}")

    def _k_pv_form(self, kid, arg):
        pv = self._pv()
        if pv is None:
            self._bitti(kid, "pv_form", {"hata": "personel penceresi açık değil (önce pv_ac)"})
            return
        sid = [int(x) for x in arg.get("siciller", [])]
        pv._form_baslat(sid, lambda e: pv.tani(f"geliştirici izin formu denemesi bitti, eksik: {e}"))
        self._bitti(kid, "pv_form", f"başlatıldı: {len(sid)} kişi")

    def _k_sql(self, kid, arg):
        sorgu = str(arg.get("sorgu", "")).strip()
        if not sorgu.lower().startswith(("select", "with", "pragma table_info")):
            self._bitti(kid, "sql", {"hata": "yalnızca okuma sorguları (SELECT)"})
            return
        yol = os.path.abspath(self.ana.db_yolu)
        con = sqlite3.connect(f"file:{yol}?mode=ro", uri=True, timeout=10)
        try:
            con.execute("PRAGMA query_only = 1")
            cur = con.execute(sorgu)
            ad = [c[0] for c in cur.description or []]
            satir = cur.fetchmany(int(arg.get("en_cok", 500)))
        finally:
            con.close()
        satir = [[(f"<{len(x)} bayt>" if isinstance(x, (bytes, str)) and len(x) > 400 else x) for x in r] for r in satir]
        self._bitti(kid, "sql", {"sutun": ad, "satir": satir})

    def _k_ayar(self, kid, arg):
        a = dict(getattr(self.ana, "ayar", {}) or {})
        self._bitti(kid, "ayar", {k: v for k, v in a.items() if "sifre" not in k.lower() and "jeton" not in k.lower()})

    def _k_kapat(self, kid, arg):
        self._bitti(kid, "kapat", "bağlantı kapatıldı")
        QTimer.singleShot(3000, lambda: self.kapat())


KOMUTLAR = ["durum", "tani", "ekran {pencere: ana|personel}", "sayfa_ac {sayfa}", "pv_ac", "pv_js {kod}", "pv_cek {ilk, son}",
            "pv_form {siciller}", "sql {sorgu}", "ayar", "kapat"]
