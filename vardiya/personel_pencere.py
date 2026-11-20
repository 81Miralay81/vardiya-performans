"""Personel Veri: personel giriş-çıkış sistemi program içinde açılır, sayfanın kendi getirdiği yanıtlardan yalnızca
gerekli bilgiler ayıklanıp ortak veri tabanına yazılır (pv.isle). Ham yanıt diske yazılmaz.

Giriş sistemin kendi giriş ekranından yapılır: kullanıcı adı ve şifre (isterse) bu bilgisayarda saklanır ve forma
otomatik doldurulur; şifreleme işini sayfanın kendisi yapar, program şifre çözmez, doğrulama kodunu (captcha) aşmaz.
Giriş yanıtı ve oturum bilgisi hiçbir zaman işlenmez. Ekranlarda ve dosya adlarında sistemin adı geçmez ("Personel Veri").
"""
from __future__ import annotations

import base64
import json
import os
import queue
import shutil
import threading
import time
from typing import Callable, Optional

from PySide6.QtCore import QObject, QSettings, QTimer, QUrl, Qt, Signal
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton, QSplitter, QVBoxLayout,
                               QWidget)

ADRES = "https://meyer.teknorot.com/"
_AYAR = ("Teknorot", "VardiyaPerformans")
ONEK = "VPPV|"

# Sayfaya en başta eklenen betik: XMLHttpRequest ve fetch yanıtlarını programa iletir (giriş / oturum yanıtları hariç).
# Otomatik çekim için isteğin adresi ve gövdesi de iletilir; istek başlıkları (oturum bilgisi) yalnızca sayfanın içinde
# tutulur ve programa hiç geçmez. __vpTekrar, öğrenilmiş bir isteği sayfanın kendi oturumuyla yeniden gönderir.
_YAKALA = r"""
(function(){
  if (window.__vpYakala) return; window.__vpYakala = true;
  window.__vpB = {};
  function gonder(meta, metin){
    try {
      var url = meta.u || '';
      if (!url || url.indexOf('/api/') < 0) return;
      var yol = url.split('?')[0];
      if (/login|token|auth|captcha|sifre|password/i.test(yol)) return;
      if (!metin || metin.length < 3 || metin.charAt(0) !== '[' || metin.indexOf('tokenid') >= 0) return;
      var tum = JSON.stringify(meta) + '\u0001' + metin;
      var parca = 200000, n = Math.ceil(tum.length / parca), kimlik = Date.now() + '_' + Math.random().toString(36).slice(2, 7);
      for (var i = 0; i < n; i++) console.log('VPPV|' + kimlik + '|' + i + '|' + n + '|' + tum.substr(i * parca, parca));
    } catch(e) {}
  }
  var ac = XMLHttpRequest.prototype.open, yolla = XMLHttpRequest.prototype.send, baslik = XMLHttpRequest.prototype.setRequestHeader;
  XMLHttpRequest.prototype.open = function(m, u){ this.__vpM = {m: m, u: u}; return ac.apply(this, arguments); };
  XMLHttpRequest.prototype.setRequestHeader = function(k, v){ try { if (!/^content-length$/i.test(k)) window.__vpB[k] = v; } catch(e) {} return baslik.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function(b){
    var x = this; x.__vpGovde = (typeof b === 'string') ? b : null;
    x.addEventListener('load', function(){
      try {
        if (!x.responseType || x.responseType === 'text') gonder({m: (x.__vpM || {}).m, u: (x.__vpM || {}).u, b: x.__vpGovde, r: x.__vpTekrar || ''}, x.responseText);
      } catch(e) {}
      if (x.__vpTekrar) console.log('VPPVT|' + x.__vpTekrar + '|' + x.status);
    });
    return yolla.apply(this, arguments);
  };
  if (window.fetch) {
    var f = window.fetch;
    window.fetch = function(){
      var a0 = arguments[0], o = arguments[1] || {};
      var u = (a0 && a0.url) || String(a0);
      try { var h = o.headers || {}; if (h.forEach) h.forEach(function(v, k){ window.__vpB[k] = v; }); else for (var k in h) window.__vpB[k] = h[k]; } catch(e) {}
      var meta = {m: o.method || 'GET', u: u, b: (typeof o.body === 'string') ? o.body : null, r: ''};
      return f.apply(this, arguments).then(function(r){ try { r.clone().text().then(function(t){ gonder(meta, t); }); } catch(e) {} return r; });
    };
  }
  window.__vpTekrar = function(id, m, u, b){
    var x = new XMLHttpRequest(); x.__vpTekrar = id; x.open(m || 'GET', u, true);
    for (var k in window.__vpB) { try { x.setRequestHeader(k, window.__vpB[k]); } catch(e) {} }
    x.onerror = function(){ console.log('VPPVT|' + id + '|0'); };
    x.send(b == null ? null : b); return true;
  };
  window.__vpDurum = function(){
    var e = document.querySelector('input[type=password]');
    return {hazir: Object.keys(window.__vpB).length > 0, giris: !!(e && e.offsetParent !== null)};
  };
})();
"""

# Giriş formu görünüyorsa doldurup gönderir. Alanlar, sayfanın çerçevesinin (AngularJS) görmesi için doğal değer
# atayıcısıyla doldurulur; düğme Türkçe büyük harfle ("GİRİŞ") yazılmış olsa da bulunur, bulunamazsa Enter gönderilir.
_DOLDUR = r"""
(function(k, s){
  var sifre = Array.prototype.slice.call(document.querySelectorAll('input[type=password]')).filter(function(e){ return e.offsetParent !== null; })[0];
  if (!sifre) return 'form yok';
  var tum = Array.prototype.slice.call(document.querySelectorAll('input')).filter(function(e){ return e.offsetParent !== null; });
  var ad = null;
  for (var i = tum.indexOf(sifre) - 1; i >= 0; i--) { var t = (tum[i].type || 'text').toLowerCase(); if (t === 'text' || t === 'email' || t === 'tel' || t === 'number') { ad = tum[i]; break; } }
  var ata = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  function yaz(e, v){ if (!e) return; e.focus(); ata.call(e, v);
    ['input', 'change', 'keyup', 'blur'].forEach(function(o){ e.dispatchEvent(new Event(o, {bubbles: true})); }); }
  yaz(ad, k); yaz(sifre, s);
  function metin(b){ return ((b.textContent || '') + ' ' + (b.value || '')).toLocaleLowerCase('tr-TR').replace(/\s+/g, ' '); }
  var aday = Array.prototype.slice.call(document.querySelectorAll('button, input[type=submit], input[type=button], a'))
    .filter(function(b){ return b.offsetParent !== null && /giri[şs]/.test(metin(b)); });
  setTimeout(function(){
    if (aday.length) { aday[0].click(); return; }
    var f = sifre.form; if (f && f.requestSubmit) { f.requestSubmit(); return; }
    ['keydown', 'keypress', 'keyup'].forEach(function(o){ sifre.dispatchEvent(new KeyboardEvent(o, {key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true})); });
  }, 400);
  return aday.length ? 'dolduruldu' : 'enter';
})(%s, %s);
"""

_GIRIS_VAR = "(function(){ var e = document.querySelector('input[type=password]'); return !!(e && e.offsetParent !== null); })();"

# Kaydırılabilir listeleri en alta indirir (pivot tablo parça parça yüklenir). Dönüş: kaydırılan bir şey oldu mu.
_KAYDIR = r"""
(function(){
  var oldu = false;
  Array.prototype.slice.call(document.querySelectorAll('*')).forEach(function(el){
    if (el.scrollHeight > el.clientHeight + 30 && el.clientHeight > 80) {
      var oy = getComputedStyle(el).overflowY;
      if (oy === 'auto' || oy === 'scroll') { var once = el.scrollTop; el.scrollTop = el.scrollHeight; if (el.scrollTop !== once) oldu = true; }
    }
  });
  var y = window.scrollY; window.scrollTo(0, document.body.scrollHeight); if (window.scrollY !== y) oldu = true;
  return oldu;
})();
"""


def _kok() -> str:
    from . import teshis
    return teshis.kayit_klasoru()


def eski_kayitlari_sil() -> None:
    """Deneme sürümünün ham yanıt klasörü (kişisel veri içerebilir) artık kullanılmıyor."""
    for ad in ("meyer_yakalanan", "meyer_tarayici"):      # eski sürümlerin klasörleri (adı değişti)
        yol = os.path.join(_kok(), ad)
        if os.path.isdir(yol):
            shutil.rmtree(yol, ignore_errors=True)


def kimlik_oku():
    a = QSettings(*_AYAR)
    k = str(a.value("pveri/kullanici", "") or "")
    try:
        s = base64.b64decode(str(a.value("pveri/sifre", "") or "")).decode("utf8")
    except Exception:  # noqa: BLE001
        s = ""
    return k, s


def kimlik_yaz(k: str, s: str):
    a = QSettings(*_AYAR)
    a.setValue("pveri/kullanici", k)
    a.setValue("pveri/sifre", base64.b64encode(s.encode("utf8")).decode())
    a.sync()


SABLON_TURLERI = {"giris_cikis": "Giriş-çıkış listesi (Planlanan + Gerçekleşen)", "liste_aktif": "Personel listesi (aktif)",
                  "liste_cikan": "İşten çıkanlar listesi", "bakiye": "İzin bakiyesi (izin formu)", "kisi_karti": "Kişi kartı (fotoğraf)"}


def sablon_oku(tur: str) -> Optional[dict]:
    """Öğrenilmiş istek (yalnızca adres ve gövde; oturum bilgisi değil). Yalnızca bu bilgisayarda saklanır."""
    try:
        v = json.loads(str(QSettings(*_AYAR).value(f"pveri/sablon/{tur}", "") or "null"))
        return v if isinstance(v, dict) and v.get("u") else None
    except ValueError:
        return None


def sablon_yaz(tur: str, v: dict) -> None:
    QSettings(*_AYAR).setValue(f"pveri/sablon/{tur}", json.dumps(v, ensure_ascii=False))


class _Kaydedici(QObject):
    """Yanıtları arka planda (kendi bağlantısıyla) veri tabanına yazar; ağ diski yavaş olsa da pencere donmaz."""
    sonuc = Signal(str, str, str)            # açıklama, tür, istek bilgisi (JSON: m, u, b, r + tanıma sonucu)

    def __init__(self, db_yolu: str):
        super().__init__()
        self._q: "queue.Queue[Optional[str]]" = queue.Queue()
        self._db = db_yolu
        self.bekleyen = 0
        threading.Thread(target=self._calis, name="pv-kayit", daemon=True).start()

    def ekle(self, metin: str):
        self.bekleyen += 1
        self._q.put(metin)

    def bitir(self):
        self._q.put(None)

    def _calis(self):
        from . import personel_veri as pv, veritabani as vt
        con = None
        while True:
            tum = self._q.get()
            if tum is None:
                break
            try:
                meta_s, _, metin = tum.partition("\u0001")
                try:
                    meta = json.loads(meta_s)
                except ValueError:
                    meta, metin = {}, tum
                if con is None:
                    con = vt.ac(self._db)
                r = pv.tani_ve_kaydet(con, metin)
                if r and r.get("aciklama"):
                    meta.update({k: v for k, v in r.items() if k != "aciklama"})
                    self.sonuc.emit(r["aciklama"], r.get("tur") or "", json.dumps(meta, ensure_ascii=False))
            except Exception as e:  # noqa: BLE001
                self.sonuc.emit(f"kaydedilemedi: {e}", "", "{}")
                con = None
            finally:
                self.bekleyen -= 1
        if con is not None:
            con.close()


_PROFIL = None


def _profil(QWebEngineProfile, QWebEngineScript):
    """Tek, kalıcı tarayıcı profili (oturum bu bilgisayarda kalır; pencere her açıldığında yeniden giriş gerekmez)."""
    global _PROFIL
    if _PROFIL is None:
        from PySide6.QtWidgets import QApplication
        p = QWebEngineProfile("vp_personel", QApplication.instance())
        p.setPersistentStoragePath(os.path.abspath(os.path.join(_kok(), "personel_tarayici")))
        p.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
        betik = QWebEngineScript()
        betik.setName("vp_yakala")
        betik.setSourceCode(_YAKALA)
        betik.setInjectionPoint(QWebEngineScript.DocumentCreation)
        betik.setWorldId(QWebEngineScript.MainWorld)
        betik.setRunsOnSubFrames(True)
        p.scripts().insert(betik)
        _PROFIL = p
    return _PROFIL


class PersonelVeriPenceresi(QDialog):
    """Elle kullanım (görünür pencere) ya da otomatik çekim (otomatik=True: pencere gösterilmez, iş bitince kapanır)."""

    def __init__(self, db_yolu: str, parent=None, kapaninca: Optional[Callable[[], None]] = None, otomatik: bool = False,
                 bitince: Optional[Callable[[bool, str], None]] = None):
        super().__init__(parent)
        self.setWindowTitle("Personel Veri")
        from .sayfa_operator import _buyuk_pencere
        _buyuk_pencere(self, 0.92)
        eski_kayitlari_sil()
        self.db_yolu = db_yolu
        self.otomatik = otomatik
        self._bitince = bitince
        self._kapaninca = kapaninca
        self._parcalar: dict = {}
        self._son_veri = 0.0
        self._kaydir_bas = 0.0
        self._son_giris_denemesi = 0.0
        self._gorevler: list = []
        self._gorev_id = 0
        self._gorev_bekle: Optional[int] = None
        self._gorev_zaman = 0.0
        self._gorev_bitti_fn: Optional[Callable[[int, int], None]] = None
        self._gorev_say = [0, 0]                       # başarılı, toplam
        self.kaydedici = _Kaydedici(db_yolu)
        self.kaydedici.sonuc.connect(self._kaydedildi)
        l = QVBoxLayout(self)
        ust = QHBoxLayout()
        k, s = kimlik_oku()
        self.kul = QLineEdit(k)
        self.kul.setPlaceholderText("Kullanıcı adı")
        self.sif = QLineEdit(s)
        self.sif.setPlaceholderText("Şifre")
        self.sif.setEchoMode(QLineEdit.Password)
        b_gir = QPushButton("Kaydet ve giriş yap")
        b_gir.setObjectName("Ana")
        b_gir.setToolTip("Kullanıcı adı ve şifre yalnızca bu bilgisayarda saklanır; giriş ekranı açılınca otomatik doldurulur.")
        b_gir.clicked.connect(self._giris_dugmesi)
        self.b_al = QPushButton("Listeyi sonuna kadar al")
        self.b_al.setToolTip("Açık listeyi en alta kadar kaydırır; parça parça gelen tüm satırlar kaydedilir.")
        self.b_al.clicked.connect(self._kaydirma_baslat)
        for w in (QLabel("Kullanıcı"), self.kul, QLabel("Şifre"), self.sif, b_gir, self.b_al):
            ust.addWidget(w)
        l.addLayout(ust)
        ust2 = QHBoxLayout()
        from PySide6.QtWidgets import QComboBox
        from datetime import date as _d
        self.yil = QComboBox()
        for y in range(_d.today().year, _d.today().year - 4, -1):
            self.yil.addItem(str(y), y)
        self.b_yil = QPushButton("Seçili yılı ay ay al")
        self.b_yil.setToolTip("Bir ayı elle listeledikten sonra program aynı listeyi seçili yılın her ayı için kendisi alır.")
        self.b_yil.clicked.connect(self._yil_al)
        self.b_kisi = QPushButton("Tüm personel bilgilerini güncelle")
        self.b_kisi.setToolTip("Personel listesi, işten çıkanlar, izin bakiyesi, kıdem ve fotoğraf herkes için sırayla alınır "
                               "(izin formunu ve kişi kartını bir kez açmış olmanız yeterli; hiçbir şey kaydedilmez, yalnızca okunur).")
        self.b_kisi.clicked.connect(self._personel_al)
        for w in (QLabel("Yıl"), self.yil, self.b_yil, self.b_kisi):
            ust2.addWidget(w)
        ust2.addStretch(1)
        l.addLayout(ust2)
        self.sablon_et = QLabel("")
        self.sablon_et.setObjectName("AltBaslik")
        self.sablon_et.setWordWrap(True)
        l.addWidget(self.sablon_et)
        self.bilgi = QLabel("Giriş yapın; sonra 'Planlanan + Gerçekleşen' ekranını açıp bir ayı listeleyin. Program o isteği öğrenir: "
                            "sonra 'Seçili yılı ay ay al' ile bütün yılı kendisi alır ve her akşam 20:00'de dünü kendisi çeker. "
                            "İzin formunu ve kişi kartını herhangi bir kişi için bir kez açarsanız tüm personelin bilgileri de alınır.")
        self.bilgi.setWordWrap(True)
        self.bilgi.setObjectName("AltBaslik")
        l.addWidget(self.bilgi)
        self._sablon_yaz()
        bol = QSplitter(Qt.Horizontal)
        try:
            from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineScript
            from PySide6.QtWebEngineWidgets import QWebEngineView
        except Exception as e:  # noqa: BLE001
            l.addWidget(QLabel(f"Tarayıcı motoru yüklenemedi: {e}"))
            if bitince:
                QTimer.singleShot(0, lambda: self._otomatik_bitir(False, f"tarayıcı motoru yok: {e}"))
            return
        self.profil = _profil(QWebEngineProfile, QWebEngineScript)
        ust_ = self

        class _Sayfa(QWebEnginePage):
            def javaScriptConsoleMessage(self, _seviye, mesaj, _satir, _kaynak):  # noqa: N802
                if mesaj.startswith(ONEK):
                    ust_._parca(mesaj)
                elif mesaj.startswith("VPPVT|"):
                    ust_._gorev_yanit(mesaj)
        self.web = QWebEngineView()
        self.sayfa = _Sayfa(self.profil, self.web)
        self.web.setPage(self.sayfa)
        self.web.loadFinished.connect(lambda _ok: self._giris_bekle())
        self.web.load(QUrl(ADRES))
        bol.addWidget(self.web)
        sag = QWidget()
        sl = QVBoxLayout(sag)
        sl.setContentsMargins(6, 0, 0, 0)
        sl.addWidget(QLabel("Kaydedilenler"))
        self.liste = QListWidget()
        sl.addWidget(self.liste)
        bol.addWidget(sag)
        bol.setSizes([1300, 380])
        l.addWidget(bol, 1)
        self._giris_zaman = QTimer(self)                 # giriş ekranı sayfa açıldıktan biraz sonra çizilir: yoklayarak bekle
        self._giris_zaman.timeout.connect(self._giris_yokla)
        self._giris_kalan = 0
        self._kaydir_zaman = QTimer(self)
        self._kaydir_zaman.timeout.connect(self._kaydir_tik)
        self._is_zaman = QTimer(self)                    # sıradaki tekrar isteği / zaman aşımı denetimi
        self._is_zaman.timeout.connect(self._gorev_tik)
        if otomatik:
            self._oto_bas = time.time()
            self._oto_zaman = QTimer(self)
            self._oto_zaman.timeout.connect(self._oto_hazir_mi)
            self._oto_zaman.start(2000)

    # ------------------------------------------------------------ öğrenilen istekler
    def _sablon_yaz(self):
        p = []
        for t, ad in SABLON_TURLERI.items():
            p.append(("✓ " if sablon_oku(t) else "✗ ") + ad)
        self.sablon_et.setText("Otomatik çekim için öğrenilenler: " + " · ".join(p))

    def _sablon_kaydet(self, tur: str, meta: dict):
        if tur not in SABLON_TURLERI or meta.get("r") or not meta.get("u"):
            return                                   # programın kendi tekrar istekleri şablonu değiştirmez
        v = {"m": meta.get("m") or "GET", "u": meta["u"], "b": meta.get("b")}
        if tur == "giris_cikis":
            if not meta.get("ilk") or not meta.get("son"):
                return
            v.update(ilk=meta["ilk"], son=meta["son"])
        if tur in ("bakiye", "kisi_karti"):
            if meta.get("sid") is None:
                return
            v["sid"] = int(meta["sid"])
        sablon_yaz(tur, v)
        self._sablon_yaz()

    # ------------------------------------------------------------ giriş
    def _giris_bekle(self):
        if all(kimlik_oku()):
            self._giris_kalan = 20
            self._giris_zaman.start(1500)

    def _giris_yokla(self):
        self._giris_kalan -= 1
        if self._giris_kalan <= 0:
            self._giris_zaman.stop()
            return
        if time.time() - self._son_giris_denemesi < 45:  # başarısız girişte durmadan tekrar denemesin
            return

        def sonuc(var):
            if var:
                self._giris_zaman.stop()
                self._doldur()
        self.sayfa.runJavaScript(_GIRIS_VAR, 0, sonuc)

    def _giris_dugmesi(self):
        kimlik_yaz(self.kul.text().strip(), self.sif.text())
        self._son_giris_denemesi = 0.0
        self._doldur()

    def _doldur(self):
        k, s = kimlik_oku()
        if not k or not s:
            self.bilgi.setText("Önce kullanıcı adı ve şifreyi yazıp 'Kaydet ve giriş yap'a basın.")
            return
        self._son_giris_denemesi = time.time()
        self.sayfa.runJavaScript(_DOLDUR % (json.dumps(k), json.dumps(s)), 0, lambda r: self.bilgi.setText(
            "Giriş bilgileri dolduruldu ve gönderildi. Doğrulama kodu (captcha) çıkarsa onu siz tamamlayın." if r in ("dolduruldu", "enter")
            else "Giriş ekranı açık değil (zaten giriş yapılmış olabilir)."))

    # ------------------------------------------------------------ yakalama ve kayıt
    def _parca(self, mesaj: str):
        try:
            _, kimlik, i, n, parca = mesaj.split("|", 4)
            i, n = int(i), int(n)
        except ValueError:
            return
        d = self._parcalar.setdefault(kimlik, [None] * n)
        d[i] = parca
        if any(x is None for x in d):
            return
        self.kaydedici.ekle("".join(self._parcalar.pop(kimlik)))

    def _kaydedildi(self, aciklama: str, tur: str, meta_s: str):
        try:
            meta = json.loads(meta_s)
        except ValueError:
            meta = {}
        self.liste.insertItem(0, f"{time.strftime('%H:%M:%S')}  {aciklama}")
        self._sablon_kaydet(tur, meta)
        if tur == "giris_cikis" and not meta.get("r"):
            self._son_veri = time.time()
            if not self._kaydir_zaman.isActive() and not self._gorevler:
                self._kaydirma_baslat()

    def _kaydirma_baslat(self):
        self._kaydir_bas = time.time()
        self._son_veri = max(self._son_veri, time.time())
        self.b_al.setEnabled(False)
        self.bilgi.setText("Liste en alta kadar kaydırılıyor; gelen tüm satırlar kaydediliyor…")
        self._kaydir_zaman.start(900)

    def _kaydir_tik(self):
        if time.time() - self._son_veri > 6 or time.time() - self._kaydir_bas > 180:
            self._kaydir_zaman.stop()
            self.b_al.setEnabled(True)
            self.bilgi.setText("Liste tamamlandı ve kaydedildi. 'Seçili yılı ay ay al' ile diğer ayları program kendisi alabilir.")
            return
        self.sayfa.runJavaScript(_KAYDIR)

    # ------------------------------------------------------------ tekrar istekleri (otomatik çekim)
    def _gorev_baslat(self, gorevler: list, bitince: Callable[[int, int], None]):
        """gorevler: [(etiket, m, u, b)] sırayla, sayfanın kendi oturumuyla gönderilir."""
        self._gorevler = list(gorevler)
        self._gorev_say = [0, len(gorevler)]
        self._gorev_bitti_fn = bitince
        self._gorev_bekle = None
        for b in (self.b_yil, self.b_kisi):
            b.setEnabled(False)
        self._is_zaman.start(400)

    def _gorev_tik(self):
        if self._gorev_bekle is not None:
            if time.time() - self._gorev_zaman > 45:          # yanıt gelmedi: sıradakine geç
                self._gorev_bekle = None
            return
        if not self._gorevler:
            if self.kaydedici.bekleyen > 0 and time.time() - self._gorev_zaman < 120:
                return                                           # son yanıtların kaydı bitsin
            self._is_zaman.stop()
            for b in (self.b_yil, self.b_kisi):
                b.setEnabled(True)
            fn, self._gorev_bitti_fn = self._gorev_bitti_fn, None
            if fn:
                fn(*self._gorev_say)
            return
        etiket, m, u, b = self._gorevler.pop(0)
        self._gorev_id += 1
        self._gorev_bekle = self._gorev_id
        self._gorev_zaman = time.time()
        sira = self._gorev_say[1] - len(self._gorevler)
        self.bilgi.setText(f"Alınıyor ({sira}/{self._gorev_say[1]}): {etiket}")
        self.sayfa.runJavaScript(f"window.__vpTekrar && window.__vpTekrar({self._gorev_id}, {json.dumps(m)}, {json.dumps(u)}, {json.dumps(b)});")

    def _gorev_yanit(self, mesaj: str):
        try:
            _, gid, durum = mesaj.split("|", 2)
            gid, durum = int(gid), int(durum)
        except ValueError:
            return
        if gid == self._gorev_bekle:
            if 200 <= durum < 300:
                self._gorev_say[0] += 1
            self._gorev_bekle = None
            self._gorev_zaman = time.time()

    def _hazir(self, fn: Callable[[bool, bool], None]):
        def coz(d):
            try:
                d = json.loads(d) if isinstance(d, str) else (d or {})
            except ValueError:
                d = {}
            fn(bool(d.get("hazir")), bool(d.get("giris")))
        self.sayfa.runJavaScript("JSON.stringify(window.__vpDurum ? window.__vpDurum() : {hazir: false, giris: false})", 0, coz)

    def ay_gorevleri(self, ilk, son) -> tuple:
        """[ilk, son] için ay ay giriş-çıkış istekleri. Dönüş: (görevler, hata metni)."""
        from datetime import date as _d
        from . import personel_veri as pv
        s = sablon_oku("giris_cikis")
        if not s:
            return [], "Önce 'Planlanan + Gerçekleşen' ekranında bir ayı elle listeleyin (program isteği öğrensin)."
        e_ilk, e_son = _d.fromisoformat(s["ilk"]), _d.fromisoformat(s["son"])
        gorevler = []
        for a, b in pv.aylar(ilk, son):
            u, ok1 = pv.tarih_degistir(s["u"], e_ilk, e_son, a, b)
            g, ok2 = pv.tarih_degistir(s.get("b") or "", e_ilk, e_son, a, b)
            if not (ok1 or ok2):
                return [], ("Öğrenilen istekte tarih bulunamadı; bu liste otomatik alınamıyor. Ayları elle listeleyebilirsiniz.")
            gorevler.append((f"giriş-çıkış {a:%d.%m.%Y} – {b:%d.%m.%Y}", s["m"], u, g if s.get("b") is not None else None))
        return gorevler, ""

    def personel_gorevleri(self) -> list:
        from . import personel_veri as pv, veritabani as vt
        gorevler = []
        for t, ad in (("liste_aktif", "personel listesi"), ("liste_cikan", "işten çıkanlar")):
            s = sablon_oku(t)
            if s:
                gorevler.append((ad, s["m"], s["u"], s.get("b")))
        con = vt.ac(self.db_yolu)
        try:
            ad = {sid: p.get("ad") for sid, p in pv.personel(con).items()}
            siciller = pv.aktif_siciller(con)
        finally:
            con.close()
        for t, etiket in (("bakiye", "izin bakiyesi"), ("kisi_karti", "kişi kartı")):
            s = sablon_oku(t)
            if not s:
                continue
            for sid in siciller:
                u, ok1 = pv.kimlik_degistir(s["u"], s["sid"], sid)
                g, ok2 = pv.kimlik_degistir(s.get("b") or "", s["sid"], sid)
                if ok1 or ok2:
                    gorevler.append((f"{etiket}: {pv.tr_baslik(ad.get(sid) or str(sid))}", s["m"], u, g if s.get("b") is not None else None))
        return gorevler

    def _yil_al(self):
        from datetime import date as _d, timedelta as _td
        y = self.yil.currentData()
        son = min(_d(y, 12, 31), _d.today() - _td(days=1))
        if son < _d(y, 1, 1):
            return

        def basla(hazir, giris):
            if not hazir or giris:
                self.bilgi.setText("Önce giriş yapın (oturum açıkken program istekleri sayfanın kendi oturumuyla gönderir).")
                return
            gorevler, hata = self.ay_gorevleri(_d(y, 1, 1), son)
            if hata:
                self.bilgi.setText(hata)
                return
            self._gorev_baslat(gorevler, lambda ok, n: self.bilgi.setText(
                f"{y} yılı alındı: {ok}/{n} ay kaydedildi. Aynı gün ikinci kez gelirse çoğalmaz, yenisiyle güncellenir."))
        self._hazir(basla)

    def _personel_al(self):
        def basla(hazir, giris):
            if not hazir or giris:
                self.bilgi.setText("Önce giriş yapın.")
                return
            g = self.personel_gorevleri()
            if not g:
                self.bilgi.setText("Önce Sicil ekranını, izin formunu ve kişi kartını bir kez açın (program istekleri öğrensin).")
                return
            self._gorev_baslat(g, lambda ok, n: self.bilgi.setText(f"Personel bilgileri güncellendi: {ok}/{n} istek."))
        self._hazir(basla)

    # ------------------------------------------------------------ otomatik çekim (her akşam)
    def _oto_hazir_mi(self):
        if time.time() - self._oto_bas > 150:
            self._oto_zaman.stop()
            self._otomatik_bitir(False, "giriş yapılamadı (şifre ya da doğrulama kodu gerekiyor olabilir; pencereyi bir kez elle açın)")
            return

        def sonuc(hazir, giris):
            if hazir and not giris and self._oto_zaman.isActive():
                self._oto_zaman.stop()
                QTimer.singleShot(3000, self._oto_calis)
        self._hazir(sonuc)

    def _oto_calis(self):
        from datetime import date as _d
        ilk, son = self._oto_aralik
        gorevler, hata = self.ay_gorevleri(ilk, son) if ilk <= son else ([], "")
        if hata:
            self._otomatik_bitir(False, hata)
            return
        n_ay = len(gorevler)
        gorevler += self.personel_gorevleri()

        def bitti(ok, n):
            self._otomatik_bitir(ok > 0 or n == 0, f"{ilk:%d.%m.%Y} – {son:%d.%m.%Y} ({n_ay} ay listesi) ve personel bilgileri: "
                                                   f"{ok}/{n} istek başarılı")
        self._gorev_baslat(gorevler, bitti)

    def _otomatik_bitir(self, basarili: bool, metin: str):
        fn, self._bitince = self._bitince, None
        if fn:
            fn(basarili, metin)
        self.close()

    def closeEvent(self, e):  # noqa: N802
        try:
            self._giris_zaman.stop()
            self._kaydir_zaman.stop()
            self._is_zaman.stop()
            self.kaydedici.bitir()
            self.web.setPage(None)
            self.sayfa.deleteLater()
        except Exception:  # noqa: BLE001
            pass
        if self._kapaninca:
            QTimer.singleShot(500, self._kapaninca)
        super().closeEvent(e)


def ac(db_yolu: str, parent=None, kapaninca: Optional[Callable[[], None]] = None) -> PersonelVeriPenceresi:
    d = PersonelVeriPenceresi(db_yolu, parent, kapaninca)
    d.setAttribute(Qt.WA_DeleteOnClose)
    d.show()
    return d


def otomatik_calistir(db_yolu: str, ilk, son, parent, bitince: Callable[[bool, str], None]) -> Optional[PersonelVeriPenceresi]:
    """Görünmez pencereyle: giriş (kayıtlı şifreyle), [ilk, son] ay ay giriş-çıkış listesi ve tüm personel bilgileri."""
    if not all(kimlik_oku()):
        bitince(False, "kullanıcı adı ve şifre bu bilgisayarda kayıtlı değil")
        return None
    if not sablon_oku("giris_cikis"):
        bitince(False, "henüz öğrenilmiş liste yok (Personel Veri penceresinde bir ayı bir kez elle listeleyin)")
        return None
    d = PersonelVeriPenceresi(db_yolu, parent, otomatik=True, bitince=bitince)
    d._oto_aralik = (ilk, son)
    d.setAttribute(Qt.WA_DeleteOnClose)
    return d
