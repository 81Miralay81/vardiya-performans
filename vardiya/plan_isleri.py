"""Vardiya planı işleri (ekran iş parçacığında): personel sisteminden haftayı okuma, gönderme ve doğrulama.

Programdaki Vardiya Planla ekranı (sayfa_plan.py) ve web (web_sunucu.py → PlanKoprusu) aynı işleri kullanır.
Okuma/yazma açık (elle açılmış) Personel Veri penceresinin sayfası üzerinden yapılır.
"""
from __future__ import annotations

import json
import threading
from datetime import date, datetime, timedelta
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import QObject, Qt, QTimer, Signal

from . import vardiya_plan as vp

SEMA = """CREATE TABLE IF NOT EXISTS plan_gecmis (id INTEGER PRIMARY KEY AUTOINCREMENT, parti TEXT NOT NULL, zaman TEXT NOT NULL,
    kullanici TEXT, sicilid INTEGER NOT NULL, ad TEXT, gun TEXT NOT NULL, eski TEXT, yeni TEXT, sonuc TEXT)"""
BAGLANTI_YOK = "Personel sistemine bağlantı yok: programda Personel Veri penceresini açıp giriş yapın."


def _gun_api(g: date) -> str:
    return f"{g:%d-%m-%Y}"


def pencere():
    """Kullanıcının açtığı (otomatik olmayan) Personel Veri penceresi; yoksa None."""
    from . import personel_pencere as pp
    for w in pp.acik_pencereler():
        if not w.otomatik:
            return w
    return None


def beyazlar(con) -> set:
    try:
        return {r[0] for r in con.execute("SELECT sicilid FROM pv_personel WHERE upper(coalesce(yaka,'')) LIKE '%BEYAZ%'")}
    except Exception:  # noqa: BLE001
        return set()


def oku(w, pzt: date, bitince: Callable[[Optional[list], str], None]):
    """Haftanın planı (ham satırlar) → bitince(liste | None, hata)."""
    cagri = f"window.__vpPlanOku ? window.__vpPlanOku(@ID, {json.dumps(_gun_api(pzt))}, {json.dumps(_gun_api(pzt + timedelta(days=6)))}) : ''"

    def gelen(durum, metin):
        try:
            d = json.loads(metin) if durum == 200 else None
        except ValueError:
            d = None
        if not isinstance(d, list) or (d and isinstance(d[0], dict) and d[0].get("sunucucevap") == "basarisiz"):
            bitince(None, f"okunamadı ({durum}: {str(metin)[:120]})")
            return
        bitince(d, "")
    w.plan_istek(cagri, gelen)


def kisiler(con, d: list, pzt: date) -> List[dict]:
    b = beyazlar(con)
    return [k for k in vp.plan_satirlari(d, pzt) if k["sicilid"] not in b]


def gonder(w, con, pzt: date, isler: List[dict], kullanici: str, adim: Callable[[str], None],
           bitince: Callable[[Dict[tuple, str], Optional[List[dict]], str], None], geri: bool = False):
    """isler: [{sid, ad, gun(date), eski, yeni}] sırayla gönderilir, sonra hafta yeniden okunup doğrulanır.
    bitince({(sid, gün no): "ok"|"hata"}, yeni kişi listesi | None, özet metni)."""
    con.execute(SEMA)
    parti = datetime.now().strftime("%Y%m%d%H%M%S") + ("-geri" if geri else "")
    sira = list(isler)
    hatali: List[dict] = []

    def sonraki():
        if not sira:
            con.commit()
            adim(f"{len(isler)} gün gönderildi; personel sisteminden yeniden okunup kontrol ediliyor…")
            QTimer.singleShot(800, dogrula)
            return
        x = sira.pop(0)
        adim(f"Gönderiliyor {len(isler) - len(sira)}/{len(isler)}: {x['ad']} {x['gun']:%d.%m} → {x['yeni']}")
        ekstra = json.dumps([{"sicilid": x["sid"], "tarih": x["gun"].isoformat()}])
        cagri = (f"window.__vpPlanYaz ? window.__vpPlanYaz(@ID, {json.dumps(_gun_api(pzt))}, "
                 f"{json.dumps(_gun_api(pzt + timedelta(days=6)))}, {vp.MESAI[x['yeni']]}, {json.dumps(ekstra)}) : ''")

        def gelen(durum, metin, x=x):
            ok = durum == 200 and "basarisiz" not in (metin or "")[:300]
            if not ok:
                hatali.append(x)
            con.execute("INSERT INTO plan_gecmis (parti, zaman, kullanici, sicilid, ad, gun, eski, yeni, sonuc) VALUES (?,?,?,?,?,?,?,?,?)",
                        (parti, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), kullanici, x["sid"], x["ad"], x["gun"].isoformat(),
                         x["eski"], x["yeni"], "gonderildi" if ok else f"istek hatası {durum}"))
            QTimer.singleShot(150, sonraki)
        w.plan_istek(cagri, gelen)

    def dogrula():
        def bitti(d, hata):
            if d is None:
                bitince({}, None, "Gönderildi ama doğrulama için okunamadı: " + hata)
                return
            ham = {}
            for r in d:
                try:
                    ham[int(r.get("ysicilid"))] = r
                except (TypeError, ValueError):
                    pass
            sonuc: Dict[tuple, str] = {}
            ok = hata_ = 0
            for x in isler:
                g = x["gun"]
                deger = str((ham.get(x["sid"]) or {}).get(f"y{g.year}x{g.month:02d}x{g.day:02d}") or "")
                ilk = deger.split("<br>")[0].split(",")[0].strip()
                kayitli = bool(ilk) and not ilk.startswith("*") and vp.hucre_ad(ilk) == x["yeni"]
                sonuc[(x["sid"], (g - pzt).days)] = "ok" if kayitli else "hata"
                ok, hata_ = ok + kayitli, hata_ + (not kayitli)
                con.execute("UPDATE plan_gecmis SET sonuc=? WHERE parti=? AND sicilid=? AND gun=?",
                            ("doğrulandı" if kayitli else f"kaydedilmedi (sistemde: {ilk or 'boş'})", parti, x["sid"], g.isoformat()))
            con.commit()
            ozet = f"Kontrol: {ok} gün kayıtlı (yeşil)" + (f", {hata_} gün KAYDEDİLEMEDİ (kırmızı)" if hata_ else "") + f" · {datetime.now():%H:%M}"
            bitince(sonuc, kisiler(con, d, pzt), ozet)
        oku(w, pzt, bitti)
    sonraki()


def geri_al_isleri(con, pzt: date) -> tuple:
    """Son gönderimin bu haftaya ait günleri için geri alma işleri: (isler, tanınmayanlar, parti) ya da ([], [], None)."""
    con.execute(SEMA)
    r = con.execute("SELECT parti FROM plan_gecmis WHERE parti NOT LIKE '%-geri' ORDER BY id DESC LIMIT 1").fetchone()
    if not r:
        return [], [], None
    isler, atla = [], []
    for sid, ad, gun, eski, yeni in con.execute("SELECT sicilid, ad, gun, eski, yeni FROM plan_gecmis WHERE parti=? AND sonuc NOT LIKE 'istek hatası%'", (r[0],)):
        g = date.fromisoformat(gun)
        if vp.hafta_basi(g) != pzt:
            continue
        (isler if eski in vp.MESAI else atla).append({"sid": sid, "ad": ad, "gun": g, "eski": yeni, "yeni": eski})
    return isler, atla, r[0]


def aktarim(gecen: List[dict], donus: Dict[str, str], dondur: bool) -> Dict[int, int]:
    """Geçen haftanın satırlarından bu haftanın seçimi {sicilid: vardiya}."""
    out = {}
    for k in gecen:
        v = vp.vardiya_tahmin(k["gun"])
        if not v:
            continue
        if dondur and donus.get(str(k["sicilid"]), "doner") == "doner":
            v = vp.dondur(v)
        out[k["sicilid"]] = v
    return out


class PlanKoprusu(QObject):
    """Web isteklerini (başka iş parçacığı) ekran iş parçacığındaki plan işlerine taşır ve sonucu bekler."""
    _is = Signal(object)

    def __init__(self, db_yolu: str):
        super().__init__()
        self.db_yolu = db_yolu
        self._is.connect(self._yap, Qt.QueuedConnection)

    def calistir(self, tur: str, arg: dict, sure_sn: int = 300) -> dict:
        ev, kutu = threading.Event(), {}
        self._is.emit((tur, arg, ev, kutu))
        if not ev.wait(sure_sn):
            return {"hata": "zaman aşımı: personel sistemi yanıt vermedi"}
        return kutu.get("sonuc") or {"hata": "sonuç yok"}

    def _yap(self, paket):
        tur, arg, ev, kutu = paket

        def bitir(x):
            kutu["sonuc"] = x
            ev.set()
        try:
            from . import veritabani as vt
            w = pencere()
            if w is None:
                bitir({"hata": BAGLANTI_YOK})
                return
            con = vt.ac(self.db_yolu)
            pzt = date.fromisoformat(arg["pzt"])
            if tur == "oku":
                hedef = pzt - timedelta(days=7) if arg.get("onceki") else pzt

                def okundu(d, hata):
                    if d is None:
                        bitir({"hata": hata})
                        return
                    bitir({"kisiler": kisiler(con, d, hedef)})
                oku(w, hedef, okundu)
            elif tur == "gonder":
                isler = [dict(x, gun=date.fromisoformat(x["gun"])) for x in arg["isler"] if x.get("yeni") in vp.MESAI]
                if not isler:
                    bitir({"hata": "gönderilecek gün yok"})
                    return
                gonder(w, con, pzt, isler, arg.get("kullanici", ""), lambda _m: None,
                       lambda s, yeni, ozet: bitir({"sonuc": [[k[0], k[1], v] for k, v in s.items()], "kisiler": yeni, "ozet": ozet}),
                       geri=bool(arg.get("geri")))
            else:
                bitir({"hata": "bilinmeyen iş"})
        except Exception as e:  # noqa: BLE001
            bitir({"hata": str(e)})
