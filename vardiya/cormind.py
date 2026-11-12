"""Cormind'e doğrudan bağlanıp makine hareketlerini çeker (Excel indirmeye gerek kalmaz).

Giriş: POST <adres>/panel/login (form: username, password, react=true) -> 'panel' çerezi.
Veri : GraphQL 'Entities' sorusu, model 'MachineAction', koşul olarak SQL 'where' cümlesi.
Tarih ve saatler Cormind'de UTC gelir; Türkiye saati (+03:00) olarak kaydedilir.
"""
from __future__ import annotations

import http.cookiejar
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Tuple

TR = timezone(timedelta(hours=3))
SORU = ("query Entities($model: Model!, $condition: Condition) {\n"
        "  entities(model: $model, condition: $condition)\n"
        "  count(model: $model, condition: $condition)\n}")
VARSAYILAN_ADRES = "http://192.168.0.39"
# Cormind'deki CNC makinelerinin numaraları (sayfanın kendi sorgusundaki liste)
VARSAYILAN_MAKINE_IDLERI = [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 18, 19, 20, 21, 22, 23, 24, 25, 26, 28, 29, 30, 31, 32,
                            33, 34, 35, 80, 15]
SAYFA = 2000


class CormindHata(Exception):
    pass


def tr_zaman(iso: Optional[str]) -> Optional[datetime]:
    """'2026-11-09T12:04:18.162Z' (UTC) -> Türkiye saatiyle, saniyeye yuvarlanmadan kesilmiş, saat dilimsiz datetime."""
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(TR).replace(tzinfo=None, microsecond=0)


def _ad(d: Optional[dict], *alanlar) -> str:
    if not isinstance(d, dict):
        return ""
    for a in alanlar:
        v = d.get(a)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


# Sabit durum numaraları. Excel çıktısıyla aynı güne ait sayılar karşılaştırılarak doğrulandı:
# 105 = YEMEK MOLASI (62), 106 = ÇAY MOLASI (47), 6 = Kalite Kontrol (41), -1 = Çalışmıyor, 5 = Kurulum.
SABIT_TIPLER = {0: "Çalışma", -1: "Çalışmıyor", 5: "Kurulum", 6: "Kalite Kontrol",
                105: "YEMEK MOLASI", 106: "ÇAY MOLASI"}


def tip_adi(kayit: dict, ariza_adlari: Dict[int, str]) -> str:
    """Duruş (type 1): arıza türünün adı, yoksa 'Belgelenmemiş Duruş'. Diğerleri sabit tablodan; bilinmeyen 'Tip n'."""
    t = kayit.get("type")
    et = kayit.get("entity_type")
    if t == 1:
        if et is None:
            return "Belgelenmemiş Duruş"
        ad = ariza_adlari.get(int(et), "")
        return ad or f"Arıza {int(et)}"
    if t == -1 and et is not None:
        # "Çalışmıyor" durumuna neden girilmişse (ör. İŞ EMRİ PLAN YOK) Cormind onu nedenin adıyla gösterir
        try:
            ad = ariza_adlari.get(int(et), "")
        except (TypeError, ValueError):
            ad = ""
        if ad:
            return ad
    return SABIT_TIPLER.get(t, f"Tip {t}")


def kayit_satiri(k: dict, makine_adlari: Dict[int, str], ariza_adlari: Dict[int, str],
                 simdi: Optional[datetime] = None) -> Optional[tuple]:
    """Cormind kaydı -> veritabanı satırı (makine, başlangıç, bitiş, operatör, tip, iş emri, ürün adı, ürün kodu).
    simdi verilirse sürmekte olan (bitişi olmayan) kayıt o ana kadar sürmüş sayılır; verilmezse alınmaz."""
    bas, bit = tr_zaman(k.get("started_at")), tr_zaman(k.get("ended_at"))
    if bit is None and bas is not None and simdi is not None and not k.get("ended_at") and simdi > bas:
        bit = simdi
    if bas is None or bit is None or bit < bas:
        return None
    mk = k.get("machine") if isinstance(k.get("machine"), dict) else {}
    makine = _ad(mk, "name", "code") or makine_adlari.get(k.get("machine_id"), "")
    if not makine:
        return None
    op = k.get("operator") if isinstance(k.get("operator"), dict) else {}
    kul = op.get("user") if isinstance(op.get("user"), dict) else {}
    operator = (f"{kul.get('first_name') or ''} {kul.get('last_name') or ''}".strip()) or _ad(op, "name")
    g = k.get("goods") if isinstance(k.get("goods"), dict) else {}
    erp = ((g.get("extra") or {}).get("erp") or {}) if isinstance(g.get("extra"), dict) else {}
    emri = str(g.get("code") or erp.get("OPERATION_ID") or "")
    urun_adi = _ad(erp, "DESCRIPTION") or _ad(g, "name")
    urun_kodu = _ad(erp, "PART_NO")
    return (makine, bas, bit, operator, tip_adi(k, ariza_adlari), emri, urun_adi, urun_kodu)


class Istemci:
    def __init__(self, adres: str = VARSAYILAN_ADRES, zaman_asimi: float = 30.0):
        adres = adres.strip().rstrip("/")
        if not adres.startswith("http"):
            adres = "http://" + adres
        self.adres = adres
        self.zaman_asimi = zaman_asimi
        self.cerez = http.cookiejar.CookieJar()
        self.acici = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cerez))
        self.acici.addheaders = [("User-Agent", "VardiyaPerformans")]
        self._graphql_adresi: Optional[str] = None

    def _istek(self, url: str, veri: bytes, tur: str) -> dict:
        r = urllib.request.Request(url, data=veri, headers={"Content-Type": tur, "Accept": "application/json"})
        try:
            with self.acici.open(r, timeout=self.zaman_asimi) as y:
                govde = y.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            raise CormindHata(f"Cormind HTTP {e.code} döndürdü ({url})") from e
        except (urllib.error.URLError, OSError) as e:
            raise CormindHata(f"Cormind'e ulaşılamadı ({self.adres}): {getattr(e, 'reason', e)}") from e
        try:
            return json.loads(govde)
        except ValueError as e:
            raise CormindHata("Cormind beklenmeyen bir cevap verdi (JSON değil)") from e

    def giris(self, kullanici: str, sifre: str) -> None:
        veri = urllib.parse.urlencode({"username": kullanici, "password": sifre, "react": "true"}).encode()
        self._istek(self.adres + "/panel/login", veri, "application/x-www-form-urlencoded")
        if not any(c.name == "panel" for c in self.cerez):
            raise CormindHata("Giriş başarısız: kullanıcı adı ya da şifre hatalı olabilir")

    def _graphql(self, model: str, condition: dict) -> dict:
        govde = json.dumps({"operationName": "Entities", "query": SORU,
                            "variables": {"model": model, "condition": condition}}).encode()
        adaylar = [self._graphql_adresi] if self._graphql_adresi else [
            self.adres + "/panel/api/graphql?Entities", self.adres + "/panel/api/graphql", self.adres + "/panel/api"]
        son_hata = None
        for url in adaylar:
            try:
                cevap = self._istek(url, govde, "application/json")
            except CormindHata as e:
                son_hata = e
                continue
            if cevap.get("errors") and not cevap.get("data"):
                son_hata = CormindHata("Cormind hata verdi: " + str(cevap["errors"][0].get("message", ""))[:200])
                continue
            if isinstance(cevap.get("data"), dict) and "entities" in cevap["data"]:
                self._graphql_adresi = url
                return cevap["data"]
        raise son_hata or CormindHata("Cormind veri adresi bulunamadı")

    def ariza_adlari(self) -> Dict[int, str]:
        """Arıza (duruş/mola) türlerinin numara -> ad listesi; alınamazsa boş döner."""
        try:
            d = self._graphql("FailureType", {"limit": 1000, "offset": 0})
        except CormindHata:
            return {}
        sonuc = {}
        for x in d.get("entities", []):
            if x.get("id") is None:
                continue
            ad = _ad(x, "name", "title", "label", "text", "display_name", "description")
            if not ad:      # ad başka bir alandaysa: renk/tarih/kod olmayan ilk anlamlı metin
                for k, v in x.items():
                    if isinstance(v, str) and v.strip() and not any(z in k for z in ("color", "_at", "code", "uuid", "icon")):
                        ad = v.strip()
                        break
            sonuc[int(x["id"])] = ad
        return sonuc

    GERIYE_GUN = 90        # dönemden önce başlayan kayıtlar için en fazla ne kadar geriye bakılır
    AZAMI_SAYFA = 40       # tek sorguda en fazla sayfa (40 x 2000 kayıt); aşılırsa durulur
    SAYFA_ARASI_SN = 0.3

    def _sayfala(self, where: str, ilerleme, onceki: int = 0) -> List[dict]:
        sonuc: List[dict] = []
        offset, toplam = 0, 0
        for _ in range(self.AZAMI_SAYFA):
            d = self._graphql("MachineAction", {"where": where, "relations": ["goods", "operator", "operator.user", "machine"],
                                                "order": {"start": "ASC"}, "limit": SAYFA, "offset": offset})
            parca = d.get("entities") or []
            toplam = int(d.get("count") or toplam or 0)
            sonuc += parca
            offset += SAYFA
            if ilerleme:
                ilerleme(onceki + len(sonuc), onceki + toplam)
            if len(parca) < SAYFA or (toplam and len(sonuc) >= toplam):
                return sonuc
            time.sleep(self.SAYFA_ARASI_SN)     # sunucuyu yormamak için sayfalar arasında kısa bekleme
        self.kesildi = True                      # beklenenden çok kayıt: sunucuyu yormamak için duruldu
        return sonuc

    def hareketler(self, ilk: date, son: date, makine_idleri: List[int],
                   ilerleme: Optional[Callable[[int, int], None]] = None, uzanan: bool = True) -> List[dict]:
        """Önce seçilen günlerde BAŞLAYAN kayıtlar (hızlı sorgu). Sonra, ayrı ve sınırlı bir sorguyla, en çok
        GERIYE_GUN gün önce başlayıp döneme uzanan ya da hâlâ süren kayıtlar. İkinci sorgu başarısız olursa
        birincinin sonucu yine kullanılır (dar_sorgu = True)."""
        bas = datetime(ilk.year, ilk.month, ilk.day, tzinfo=TR)
        bit = datetime(son.year, son.month, son.day, tzinfo=TR) + timedelta(days=1)
        geri = bas - timedelta(days=self.GERIYE_GUN)
        mk = (f" AND \"MachineAction\".\"machine_id\" IN ({','.join(str(int(i)) for i in makine_idleri)})" if makine_idleri else "")
        where_dar = (f"\"MachineAction\".\"started_at\" >= '{bas.isoformat()}' AND \"MachineAction\".\"started_at\" < '{bit.isoformat()}'" + mk)
        where_uzanan = (f"\"MachineAction\".\"started_at\" >= '{geri.isoformat()}' AND \"MachineAction\".\"started_at\" < '{bas.isoformat()}'"
                        f" AND (\"MachineAction\".\"ended_at\" >= '{bas.isoformat()}' OR \"MachineAction\".\"ended_at\" IS NULL)" + mk)
        self.dar_sorgu, self.kesildi = False, False
        sonuc = self._sayfala(where_dar, ilerleme)
        if not uzanan:
            return sonuc
        try:
            sonuc = self._sayfala(where_uzanan, ilerleme, len(sonuc)) + sonuc
        except CormindHata:
            self.dar_sorgu = True
        return sonuc


def suren_kayitlari_kapat(ham: List[dict]) -> List[dict]:
    """Bitişi olmayan kayıt, aynı makinenin sonraki kaydı başladığında bitmiş sayılır (kapatılmamış eski kayıtlar
    günlerce sürmüş gibi görünmesin). Makinenin en son kaydıysa bitişsiz kalır (çekim anına kadar sürüyor)."""
    makineye: Dict[object, List[dict]] = {}
    for k in ham:
        makineye.setdefault(k.get("machine_id") or (k.get("machine") or {}).get("id"), []).append(k)
    for liste in makineye.values():
        liste.sort(key=lambda k: k.get("started_at") or "")
        for i, k in enumerate(liste[:-1]):
            if not k.get("ended_at"):
                sonraki = next((x.get("started_at") for x in liste[i + 1:] if (x.get("started_at") or "") > (k.get("started_at") or "")), None)
                if sonraki:
                    k["ended_at"] = sonraki
    return ham


AY_ADLARI = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")
BICIM = "%Y-%m-%d %H:%M:%S"


def aylara_bol(ilk: date, son: date, azami_gun: int = 31) -> List[Tuple[date, date]]:
    """Aralık azami_gun'den uzunsa takvim aylarına bölünür (Cormind uzun aralığı tek seferde vermiyor)."""
    if (son - ilk).days < azami_gun:
        return [(ilk, son)]
    parcalar, bas = [], ilk
    while bas <= son:
        ay_sonu = (date(bas.year + (bas.month == 12), bas.month % 12 + 1, 1) - timedelta(days=1))
        bit = min(son, ay_sonu)
        parcalar.append((bas, bit))
        bas = bit + timedelta(days=1)
    return parcalar


def _parca_cek(con, ist: "Istemci", ariza: Dict[int, str], ilk: date, son: date, makine_idleri: List[int],
               ilerleme, uzanan: bool) -> dict:
    """Bir parçayı (en çok bir ay) çekip yazar. Süren (bitişi olmayan) kayıtlar parça sonuna ya da şimdiye kadar yazılır
    ve 'acik' olarak bildirilir; çağıran sonraki parçaya göre bitişlerini düzeltir."""
    from . import veritabani as vt
    ham = suren_kayitlari_kapat(ist.hareketler(ilk, son, makine_idleri, ilerleme, uzanan))
    makine_adlari: Dict[int, str] = {}
    satirlar, atlanan = [], 0
    tipler: Dict[str, int] = {}
    simdi = datetime.now(TR).replace(tzinfo=None, microsecond=0)
    parca_sonu = min(simdi, datetime(son.year, son.month, son.day) + timedelta(days=1))
    acik: Dict[str, Tuple[datetime, str]] = {}
    ilk_bas: Dict[str, datetime] = {}
    for k in ham:
        s = kayit_satiri(k, makine_adlari, ariza, parca_sonu)
        if s is None:
            atlanan += 1
            continue
        satirlar.append(s)
        tipler[s[4]] = tipler.get(s[4], 0) + 1
        if s[1] >= datetime(ilk.year, ilk.month, ilk.day) and (s[0] not in ilk_bas or s[1] < ilk_bas[s[0]]):
            ilk_bas[s[0]] = s[1]
        if not k.get("ended_at"):
            acik[s[0]] = (s[1], s[4] or "")
    # O günlerin eski kayıtları (Excel'den ya da önceki çekimden) silinip Cormind'dekiyle değiştirilir:
    # saniye yuvarlama farkından çift kayıt oluşmasın, düzeltilmiş tip adları eskilerin yerine geçsin.
    silinen = 0
    if satirlar:
        aralik = (ilk.strftime("%Y-%m-%d 00:00:00"), (son + timedelta(days=1)).strftime("%Y-%m-%d 00:00:00"))
        silinen = con.execute("SELECT COUNT(*) FROM kayit WHERE baslangic >= ? AND baslangic < ?", aralik).fetchone()[0]
        con.execute("DELETE FROM kayit WHERE baslangic >= ? AND baslangic < ?", aralik)
        con.commit()
    # aynı makine + başlangıçlı eski satır başka bir tip adıyla duruyorsa (ör. önceden "Çalışmıyor" diye alınmış) çift sayılmasın
    con.executemany("DELETE FROM kayit WHERE makine=? AND baslangic=? AND tip<>?", [(s[0], s[1].strftime(BICIM), s[4] or "") for s in satirlar])
    con.commit()
    yeni, guncel, ayni = vt.kayit_yaz(con, satirlar)
    ilk_g = min((s[1] for s in satirlar), default=None)
    son_g = max((s[1] for s in satirlar), default=None)
    vt.aktarim_kaydet(con, f"Cormind ({ilk:%d.%m.%Y}–{son:%d.%m.%Y})", len(ham), yeni, guncel, ayni, atlanan,
                      ilk_g.strftime("%Y-%m-%d") if ilk_g else None, son_g.strftime("%Y-%m-%d") if son_g else None)
    return {"toplam": len(ham), "yeni": yeni, "guncel": guncel, "ayni": ayni, "atlanan": atlanan, "silinen": silinen,
            "tipler": tipler, "makineler": {s[0] for s in satirlar}, "acik": acik, "ilk_bas": ilk_bas, "parca_sonu": parca_sonu}


def cek(con, adres: str, kullanici: str, sifre: str, ilk: date, son: date, makine_idleri: List[int],
        ilerleme: Optional[Callable[[int, int], None]] = None, adim: Optional[Callable[[dict], None]] = None,
        iptal: Optional[Callable[[], bool]] = None, parca_arasi_sn: float = 1.0, uzanan: bool = True) -> dict:
    """Cormind'den çekip veritabanına yazar. Bir aydan uzun aralık ay ay çekilir; her ay bitince kaydedilir.
    adim(bilgi): ilerleme bildirimi (parca, parca_sayisi, ilk, son, asama, kayit, toplam, kaydedilen).
    iptal(): True dönerse sıradaki parçaya geçilmez. Dönüş: sayılar ve tip dağılımı."""
    from . import veritabani as vt

    def bildir(**b):
        if adim:
            adim(b)

    parcalar = aylara_bol(ilk, son)
    n = len(parcalar)
    bildir(parca=0, parca_sayisi=n, ilk=ilk, son=son, asama="baglaniyor", kayit=0, toplam=0, kaydedilen=0)
    ist = Istemci(adres)
    ist.giris(kullanici, sifre)
    ariza = ist.ariza_adlari()
    t = {"toplam": 0, "yeni": 0, "guncel": 0, "ayni": 0, "atlanan": 0, "silinen": 0}
    tipler: Dict[str, int] = {}
    makineler: set = set()
    acik: Dict[str, Tuple[datetime, str]] = {}
    dar = kesildi = durduruldu = False
    biten = 0
    for i, (p_ilk, p_son) in enumerate(parcalar):
        if iptal and iptal():
            durduruldu = True
            break
        if i:
            time.sleep(parca_arasi_sn)

        def sayfa_ilerleme(kayit, toplam, _i=i, _a=p_ilk, _b=p_son):
            if ilerleme:
                ilerleme(kayit, toplam)
            bildir(parca=_i + 1, parca_sayisi=n, ilk=_a, son=_b, asama="cekiliyor", kayit=kayit, toplam=toplam, kaydedilen=t["toplam"])

        bildir(parca=i + 1, parca_sayisi=n, ilk=p_ilk, son=p_son, asama="cekiliyor", kayit=0, toplam=0, kaydedilen=t["toplam"])
        r = _parca_cek(con, ist, ariza, p_ilk, p_son, makine_idleri, sayfa_ilerleme, uzanan=(uzanan and i == 0))
        dar, kesildi = dar or ist.dar_sorgu, kesildi or ist.kesildi
        # önceki parçadan süren kayıtlar: bu parçada o makinenin ilk kaydı başladığında biter; yoksa bu parçanın sonuna uzar
        for m, (bas, tip) in list(acik.items()):
            bitis = r["ilk_bas"].get(m)
            con.execute("UPDATE kayit SET bitis=? WHERE makine=? AND baslangic=? AND tip=?",
                        ((bitis or r["parca_sonu"]).strftime(BICIM), m, bas.strftime(BICIM), tip))
            if bitis:
                del acik[m]
        con.commit()
        acik.update(r["acik"])
        for k in t:
            t[k] += r[k]
        for ad, sayi in r["tipler"].items():
            tipler[ad] = tipler.get(ad, 0) + sayi
        makineler |= r["makineler"]
        biten = i + 1
        bildir(parca=i + 1, parca_sayisi=n, ilk=p_ilk, son=p_son, asama="kaydedildi", kayit=r["toplam"], toplam=r["toplam"], kaydedilen=t["toplam"])
    ay = vt.ayar_oku(con)
    bilinen = set(ay["makineler"])
    eklenen = sorted(makineler - bilinen)
    if eklenen:
        vt.ayar_yaz(con, "makineler", sorted(bilinen | set(eklenen)))
    return dict(t, tipler=dict(sorted(tipler.items(), key=lambda x: -x[1])), yeni_makineler=eklenen, dar_sorgu=dar, kesildi=kesildi,
                parca_sayisi=n, biten_parca=biten, durduruldu=durduruldu)
