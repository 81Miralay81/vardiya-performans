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
from datetime import timedelta
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
  function baslikUygun(k){ return !/^(content-length|x-signalr|x-requested-with$)/i.test(k); }
  XMLHttpRequest.prototype.setRequestHeader = function(k, v){ try { if (baslikUygun(k)) { (this.__vpH = this.__vpH || {})[k] = v; } } catch(e) {} return baslik.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function(b){
    var x = this; x.__vpGovde = (typeof b === 'string') ? b : null;
    x.addEventListener('load', function(){
      try {
        var uu = (x.__vpM || {}).u || '';
        if (!x.__vpTekrar && x.__vpH && x.status >= 200 && x.status < 300 && uu.indexOf('/api/') >= 0 && !/signalr|negotiate/i.test(uu)) window.__vpB = x.__vpH;
      } catch(e) {}
      try {
        if (!x.responseType || x.responseType === 'text') gonder({m: (x.__vpM || {}).m, u: (x.__vpM || {}).u, b: x.__vpGovde, r: x.__vpTekrar || '', s: location.hash}, x.responseText);
      } catch(e) {}
      if (x.__vpTekrar) { var t = ''; try { t = x.responseText || ''; } catch(e) {} console.log('VPPVT|' + x.__vpTekrar + '|' + x.status + '|' + t.length + '|' + t.charAt(0)); }
    });
    return yolla.apply(this, arguments);
  };
  if (window.fetch) {
    var f = window.fetch;
    window.fetch = function(){
      var a0 = arguments[0], o = arguments[1] || {};
      var u = (a0 && a0.url) || String(a0);
      try { if (u.indexOf('/api/') >= 0 && !/signalr|negotiate/i.test(u)) { var h = o.headers || {}, y = {}; if (h.forEach) h.forEach(function(v, k){ if (baslikUygun(k)) y[k] = v; }); else for (var k in h) if (baslikUygun(k)) y[k] = h[k]; if (Object.keys(y).length) window.__vpB = y; } } catch(e) {}
      var meta = {m: o.method || 'GET', u: u, b: (typeof o.body === 'string') ? o.body : null, r: '', s: location.hash};
      return f.apply(this, arguments).then(function(r){ try { r.clone().text().then(function(t){ gonder(meta, t); }); } catch(e) {} return r; });
    };
  }
  window.__vpTekrar = function(id, m, u, b){
    var x = new XMLHttpRequest(); x.__vpTekrar = id; x.open(m || 'GET', u, true);
    var tipVar = false;
    for (var k in window.__vpB) { try { x.setRequestHeader(k, window.__vpB[k]); if (/^content-type$/i.test(k)) tipVar = true; } catch(e) {} }
    if (b != null && !tipVar) { try { x.setRequestHeader('Content-Type', 'application/json;charset=UTF-8'); } catch(e) {} }
    x.onerror = function(){ console.log('VPPVT|' + id + '|0'); };
    x.send(b == null ? null : b); return true;
  };
  window.__vpDurum = function(){
    var e = document.querySelector('input[type=password]');
    return {hazir: Object.keys(window.__vpB).length > 0, giris: !!(e && e.offsetParent !== null), basliklar: Object.keys(window.__vpB)};
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

# Ekran yolu (istekte tarih okunamıyorsa): Pdks Pivot ekranındaki iki tarih kutusuna dönemi yazar ve
# 'Planlanan + Gerçekleşen' düğmesine basar; sayfa isteği kendisi oluşturur, program yanıtı yakalar.
_EKRAN_DONEM = r"""
(function(bas, bit, sayfa){
  if (sayfa && location.hash !== sayfa) { location.hash = sayfa; return JSON.stringify({git: 1}); }
  var gor = function(e){ return e && document.body.contains(e) && e.offsetParent !== null; };
  var kutu = (window.__vpKutu || []).filter(gor);
  if (kutu.length < 2) {
    kutu = Array.prototype.slice.call(document.querySelectorAll('input')).filter(function(e){
      return gor(e) && /^\d{2}[-.\/]\d{2}[-.\/]\d{4}$/.test((e.value || '').trim()); });
    if (kutu.length >= 2) window.__vpKutu = kutu.slice(0, 2);
  }
  var dug = Array.prototype.slice.call(document.querySelectorAll('button, a, input[type=button]')).filter(function(b){
    return b.offsetParent !== null && /planlanan\s*\+\s*gerçekleşen/.test(((b.textContent || b.value || '') + '').toLocaleLowerCase('tr-TR')); });
  dug.sort(function(a, b){ return (a.textContent || '').length - (b.textContent || '').length; });
  if (kutu.length < 2 || !dug.length) return JSON.stringify({kutu: kutu.length, dugme: dug.length});
  var ayr = window.__vpAyrac || (kutu[0].value.trim().charAt(2)) || '-'; if (!/[-.\/]/.test(ayr)) ayr = '-'; window.__vpAyrac = ayr;
  var ata = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  var kapat = function(){ try { document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', keyCode: 27, which: 27, bubbles: true}));
      document.body.dispatchEvent(new MouseEvent('mousedown', {bubbles: true})); document.body.click(); } catch(err) {} };
  var yaz = function(e, v){
    ata.call(e, v);
    ['input', 'change', 'keyup'].forEach(function(o){ e.dispatchEvent(new Event(o, {bubbles: true})); });
    try { if (window.angular) { var c = angular.element(e).controller('ngModel'); if (c) { c.$setViewValue(v); c.$render(); var sc = angular.element(e).scope(); if (sc && !sc.$$phase && !(sc.$root && sc.$root.$$phase)) sc.$apply(); } } } catch(err) {}
    try { if (window.jQuery) { var j = jQuery(e); if (j.datepicker) { try { j.datepicker('update', v); } catch(e2) {} } j.val(v).trigger('change'); } } catch(err) {}
    if (e.value !== v) ata.call(e, v);
    try { e.dispatchEvent(new Event('blur', {bubbles: true})); } catch(err) {}
  };
  var v1 = bas.replace(/-/g, ayr), v2 = bit.replace(/-/g, ayr);
  yaz(kutu[0], v1); kapat();
  setTimeout(function(){
    yaz(kutu[1], v2); kapat();
    setTimeout(function(){
      if (kutu[0].value !== v1) yaz(kutu[0], v1);
      if (kutu[1].value !== v2) yaz(kutu[1], v2);
      kapat();
      setTimeout(function(){
        console.log('VPPVE|' + kutu[0].value + '|' + kutu[1].value);
        dug[0].click();
      }, 500);
    }, 900);
  }, 900);
  return JSON.stringify({kutu: kutu.length, dugme: dug.length, ayrac: ayr});
})(%s, %s, %s);
"""

import weakref
_PENCERELER = weakref.WeakSet()       # açık Personel Veri pencereleri (elle ve otomatik)
ERTELENDI = "ertelendi"               # otomatik çekim, kullanıcı pencereyi açtığı için durduruldu (hata sayılmaz)


def elle_acik_mi() -> bool:
    """Kullanıcının açtığı (görünür) bir Personel Veri penceresi var mı."""
    return any(not w.otomatik for w in list(_PENCERELER))


EKRAN_YANIT_SN = 90     # ekran yolunda bir ayın listesinin gelmesi için en uzun bekleme (büyük listeler yavaş gelebilir)

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


# Öğrenme sırası (ekranlar): 1) Sicil Liste · Hepsi  2) İzin Talep Formu (bir kişi, kaydetmeden)  3) Pdks Pivot · Planlanan + Gerçekleşen
SABLON_TURLERI = {"liste_hepsi": "1. Sicil Liste · Hepsi (personel listesi ve ayrılanlar)",
                  "bakiye": "2. İzin Talep Formu (bir kişi seçip açın, kaydetmeyin): izin hakkı",
                  "kisi_karti": "2. (aynı adımda gelir) kişi kartı: fotoğraf, işe giriş",
                  "giris_cikis": "3. Pdks Pivot · Planlanan + Gerçekleşen (bir ay listeleyin)",
                  "liste_aktif": "Sicil Liste · Aktifler", "liste_cikan": "Sicil Liste · İşten Çıkanlar"}
ADIMLAR = ("liste_hepsi", "bakiye", "kisi_karti", "giris_cikis")


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
        _PENCERELER.add(self)
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
        self._tani: list = []
        self._gorev_etiket = ""
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
        from PySide6.QtWidgets import QCheckBox
        self.ogren = QCheckBox("1) Öğren")
        self.ogren.setToolTip("İşaretliyken sizin ekranda yaptığınız listelemeler 'öğrenilir' (program isteği kaydeder). "
                              "Öğrendikten sonra işareti kaldırıp '2) Otomatik çek' ile deneyin.")
        self.ogren.setChecked(True)
        self.ogren.toggled.connect(lambda v: self.tani("Öğrenme " + ("açık: ekranda listelediğiniz istekler kaydedilecek" if v else "kapalı")))
        self.b_yil = QPushButton("2) Otomatik çek (seçili yıl, ay ay)")
        self.b_yil.setObjectName("Ana")
        self.b_yil.setToolTip("Öğrenilen istekle seçili yılın her ayını (düne kadar) program kendisi alır; ardından personel listeleri "
                              "ve (öğrenildiyse) izin bakiyeleri. Ekranda hiçbir şeye tıklamaz.")
        self.b_yil.clicked.connect(self._yil_al)
        b_sifirla = QPushButton("Öğrenilenleri sıfırla")
        b_sifirla.clicked.connect(self._sifirla)
        b_tani = QPushButton("Tanı kaydını kaydet")
        b_tani.setToolTip("Bu penceredeki adımların kaydı (oturum ve şifre bilgisi içermez) bir dosyaya yazılır; bana gönderebilirsiniz.")
        b_tani.clicked.connect(self._tani_kaydet)
        for w in (self.ogren, QLabel("   Yıl"), self.yil, self.b_yil):
            ust2.addWidget(w)
        ust2.addStretch(1)
        ust2.addWidget(b_sifirla)
        ust2.addWidget(b_tani)
        l.addLayout(ust2)
        self.sablon_et = QLabel("")
        self.sablon_et.setObjectName("AltBaslik")
        self.sablon_et.setWordWrap(True)
        l.addWidget(self.sablon_et)
        self.bilgi = QLabel("Giriş yapın. '1) Öğren' işaretliyken sırayla: Sicil Liste'de 'Hepsi' sekmesi · bir kişiyi seçip İzin Talep Formu'nu "
                            "açın ve Kapat (kaydetmeyin) · Pdks Pivot'ta 'Planlanan + Gerçekleşen' ile bir ay listeleyin. Üç adım ✓ olunca "
                            "'1) Öğren' işaretini kaldırıp '2) Otomatik çek' ile deneyin.")
        self.bilgi.setWordWrap(True)
        self.bilgi.setObjectName("AltBaslik")
        l.addWidget(self.bilgi)
        self._sablon_yaz()
        bol = QSplitter(Qt.Horizontal)
        try:
            from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineScript
            from PySide6.QtWebEngineWidgets import QWebEngineView
        except Exception as e:  # noqa: BLE001
            hata_m = str(e)
            l.addWidget(QLabel(f"Tarayıcı motoru yüklenemedi: {hata_m}"))
            if bitince:
                QTimer.singleShot(0, lambda: self._otomatik_bitir(False, f"tarayıcı motoru yok: {hata_m}"))
            return
        self.profil = _profil(QWebEngineProfile, QWebEngineScript)
        ust_ = self

        class _Sayfa(QWebEnginePage):
            def javaScriptConsoleMessage(self, _seviye, mesaj, _satir, _kaynak):  # noqa: N802
                if mesaj.startswith(ONEK):
                    ust_._parca(mesaj)
                elif mesaj.startswith("VPPVT|"):
                    ust_._gorev_yanit(mesaj)
                elif mesaj.startswith("VPPVE|"):
                    ust_._ekran_yazildi(mesaj)
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
        for t in ADIMLAR:
            ok = bool(sablon_oku(t)) or (t == "liste_hepsi" and bool(sablon_oku("liste_aktif")))
            p.append(("✓ " if ok else "✗ ") + SABLON_TURLERI[t])
        ek = [SABLON_TURLERI[t] for t in ("liste_aktif", "liste_cikan") if sablon_oku(t)]
        self.sablon_et.setText("Öğrenme adımları (1) Öğren işaretliyken sırayla açın):  " + "   ".join(p)
                               + (f"   (ayrıca öğrenilen: {', '.join(ek)})" if ek else ""))

    # ------------------------------------------------------------ tanı kaydı (oturum / şifre bilgisi içermez)
    def tani(self, metin: str):
        satir = f"{time.strftime('%H:%M:%S')}  {metin}"
        self._tani.append(satir)
        self.liste.insertItem(0, satir) if hasattr(self, "liste") else None
        try:
            from . import teshis
            teshis.adim("personel veri: " + metin)
        except Exception:  # noqa: BLE001
            pass

    def _tani_kaydet(self):
        yol = os.path.join(_kok(), "personel_veri_tani.txt")
        try:
            with open(yol, "w", encoding="utf-8") as f:
                f.write("\n".join(self._tani))
            self.bilgi.setText(f"Tanı kaydı yazıldı: {yol}")
            if hasattr(os, "startfile"):
                os.startfile(_kok())
        except OSError as e:
            self.bilgi.setText(f"Yazılamadı: {e}")

    def _sifirla(self):
        for t in SABLON_TURLERI:
            QSettings(*_AYAR).remove(f"pveri/sablon/{t}")
        QSettings(*_AYAR).remove("pveri/son_tam")
        self.ogren.setChecked(True)
        self._sablon_yaz()
        self.tani("Öğrenilenler sıfırlandı")

    @staticmethod
    def _yol(u: str) -> str:
        """Tanı kaydı için yalnızca adresin yolu (sorgu değerleri yazılmaz)."""
        from urllib.parse import urlparse
        try:
            p = urlparse(u)
            return p.path + (f" (+{len(p.query.split('&'))} sorgu alanı)" if p.query else "")
        except Exception:  # noqa: BLE001
            return "?"

    def _sablon_kaydet(self, tur: str, meta: dict):
        if tur not in SABLON_TURLERI or meta.get("r") or not meta.get("u"):
            return                                   # programın kendi tekrar istekleri şablonu değiştirmez
        if not self.ogren.isChecked():
            return
        v = {"m": meta.get("m") or "GET", "u": meta["u"], "b": meta.get("b")}
        ek = ""
        if tur == "giris_cikis":
            if not meta.get("ilk") or not meta.get("son"):
                return
            v.update(ilk=meta["ilk"], son=meta["son"])
            from datetime import date as _d
            from . import personel_veri as pv
            a, b = _d.fromisoformat(meta["ilk"]), _d.fromisoformat(meta["son"])
            _, ok_u, nasil = pv.tarih_degistir_derin(v["u"], a, b, a, b)
            _, ok_b = pv.tarih_degistir(v["b"] or "", a, b, a, b)
            v["sayfa"] = meta.get("s") or ""
            ek = (f" · dönem {a:%d.%m.%Y}–{b:%d.%m.%Y} · tarih "
                  + (nasil if ok_u else "gövdede" if ok_b else f"istekte okunamadı ({nasil}) → otomatik çekim ekran yoluyla yapılacak")
                  + (f" · ekran {v['sayfa']}" if v["sayfa"] else ""))
        if tur in ("bakiye", "kisi_karti"):
            if meta.get("sid") is None:
                return
            v["sid"] = int(meta["sid"])
        sablon_yaz(tur, v)
        self.tani(f"öğrenildi: {SABLON_TURLERI[tur]} · {v['m']} {self._yol(v['u'])}" + (" · gövdeli" if v["b"] else "") + ek)
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
        self.tani(("otomatik yanıt kaydedildi: " if meta.get("r") else "kaydedildi: ") + aciklama)
        self._sablon_kaydet(tur, meta)
        if tur == "giris_cikis" and not meta.get("r"):
            self._ekran_yanit(meta)
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
        self.b_yil.setEnabled(False)
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
            self.b_yil.setEnabled(True)
            fn, self._gorev_bitti_fn = self._gorev_bitti_fn, None
            if fn:
                fn(*self._gorev_say)
            return
        etiket, m, u, b = self._gorevler.pop(0)
        self._gorev_etiket = etiket
        self._gorev_id += 1
        self._gorev_bekle = self._gorev_id
        self._gorev_zaman = time.time()
        sira = self._gorev_say[1] - len(self._gorevler)
        self.bilgi.setText(f"Alınıyor ({sira}/{self._gorev_say[1]}): {etiket}")
        self.sayfa.runJavaScript(f"window.__vpTekrar && window.__vpTekrar({self._gorev_id}, {json.dumps(m)}, {json.dumps(u)}, {json.dumps(b)});")

    def _gorev_yanit(self, mesaj: str):
        try:
            p = mesaj.split("|")
            gid, durum = int(p[1]), int(p[2])
            uz, ilk = (int(p[3]) if len(p) > 3 and p[3] else 0), (p[4] if len(p) > 4 else "")
        except (ValueError, IndexError):
            return
        if gid == self._gorev_bekle:
            yorum = ("tamam" if 200 <= durum < 300 and ilk == "[" else
                     "yanıt liste değil" if 200 <= durum < 300 else
                     "oturum bilgisi istekle gitmedi (yetkisiz)" if durum in (401, 403) else
                     "bağlantı hatası" if durum == 0 else "sunucu hatası")
            self.tani(f"otomatik istek: {self._gorev_etiket} → durum {durum}, {uz} bayt · {yorum}")
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
            self._son_basliklar = list(d.get("basliklar") or [])
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
            u, ok1, _n = pv.tarih_degistir_derin(s["u"], e_ilk, e_son, a, b)
            g, ok2 = pv.tarih_degistir(s.get("b") or "", e_ilk, e_son, a, b)
            if not (ok1 or ok2):
                return [], "TARIH_YOK"
            gorevler.append((f"giriş-çıkış {a:%d.%m.%Y} – {b:%d.%m.%Y}", s["m"], u, g if s.get("b") is not None else None))
        return gorevler, ""

    def personel_gorevleri(self) -> list:
        """Personel listesi ve işten çıkanlar; izin bakiyesi öğrenildiyse (deneme) her aktif kişi için."""
        from . import personel_veri as pv, veritabani as vt
        gorevler = []
        for t, ad in (("liste_hepsi", "personel listesi (hepsi)"), ("liste_aktif", "personel listesi (aktifler)"),
                      ("liste_cikan", "işten çıkanlar")):
            s = sablon_oku(t)
            if s:
                gorevler.append((ad, s["m"], s["u"], s.get("b")))
        sablonlar = [(t, e, sablon_oku(t)) for t, e in (("bakiye", "izin bakiyesi"), ("kisi_karti", "kişi kartı"))]
        sablonlar = [(t, e, x) for t, e, x in sablonlar if x and x.get("sid") is not None]
        if sablonlar:
            con = vt.ac(self.db_yolu)
            try:
                ad = {sid: p.get("ad") for sid, p in pv.personel(con).items()}
                siciller = pv.aktif_siciller(con)
            finally:
                con.close()
            for _t, etiket, s in sablonlar:
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
            self.tani(f"otomatik çekim isteği: {y} · oturum hazır: {'evet' if hazir and not giris else 'hayır'}"
                      + (" (giriş ekranı açık)" if giris else "")
                      + f" · sayfanın istek başlık adları: {', '.join(getattr(self, '_son_basliklar', [])) or 'yok'}")
            if not hazir or giris:
                self.bilgi.setText("Önce giriş yapın (oturum açıkken program istekleri sayfanın kendi oturumuyla gönderir).")
                return
            def bitti(ok, n, aciklama):
                m = f"Otomatik çekim bitti ({y}): {aciklama}. Aynı gün ikinci kez gelirse çoğalmaz, yenisiyle güncellenir."
                self.tani(m)
                self.bilgi.setText(m + " Sorun varsa 'Tanı kaydını kaydet' ile dosyayı bana gönderin.")
            self.donem_cek(_d(y, 1, 1), son, bitti)
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
        ilk, son = self._oto_aralik

        def bitti(ok, n, aciklama):
            self._otomatik_bitir(ok > 0 or n == 0, f"{ilk:%d.%m.%Y} – {son:%d.%m.%Y}: {aciklama}")
        self.donem_cek(ilk, son, bitti)

    # ------------------------------------------------------------ birleşik akış: aylar (istekle ya da ekran yoluyla) + personel
    def donem_cek(self, ilk, son, bitti: Callable[[int, int, str], None]):
        if getattr(self, "_cekim_suruyor", False):
            self.tani("bir çekim zaten sürüyor; yenisi başlatılmadı")
            self.bilgi.setText("Bir çekim zaten sürüyor, bitmesini bekleyin.")
            return
        self._cekim_suruyor = True
        ilk_bitti = bitti

        def bitti(ok, n, aciklama):  # noqa: F811
            self._cekim_suruyor = False
            ilk_bitti(ok, n, aciklama)
        gorevler, hata = self.ay_gorevleri(ilk, son) if ilk <= son else ([], "")
        if hata and hata != "TARIH_YOK":
            self.tani("durdu: " + hata)
            bitti(0, 1, hata)
            return
        pers = self.personel_gorevleri()

        def personel_sonra(ok_ay, n_ay, yol):
            def son_(ok, n):
                bitti(ok_ay + ok, n_ay + n, f"{ok_ay}/{n_ay} ay ({yol}), personel {ok}/{n} istek")
            if pers:
                self._gorev_baslat(pers, son_)
            else:
                son_(0, 0)
        if hata == "TARIH_YOK":
            from . import personel_veri as pv
            aylar = pv.aylar(ilk, son)
            self.tani(f"istekte tarih okunamadığı için {len(aylar)} ay ekran yoluyla alınacak (tarih kutuları + 'Planlanan + Gerçekleşen')")
            self._ekran_baslat(aylar, lambda ok, n: personel_sonra(ok, n, "ekran yoluyla"))
        else:
            self.tani(f"{len(gorevler)} ay istekle, {len(pers)} personel isteği gönderilecek")
            self._gorev_baslat(gorevler, lambda ok, n: personel_sonra(ok, n, "istekle"))

    def _ekran_baslat(self, aylar: list, bitince: Callable[[int, int], None]):
        self._ekran_aylar = list(aylar)
        self._ekran_say = [0, len(aylar)]
        self._ekran_bitince = bitince
        self._ekran_bekle = None
        self._ekran_deneme = 0          # bu ay için kaçıncı deneme (yanıt gelmezse bir kez daha)
        self._ekran_bulunamadi = 0      # tarih kutusu art arda bulunamayan deneme sayısı
        self._ekran_zaman = time.time()
        self.b_yil.setEnabled(False)
        s = sablon_oku("giris_cikis") or {}
        self._ekran_sayfa = s.get("sayfa") or "#!/pdkspiv"
        self.tani(f"ekran yolu: {self._ekran_sayfa} ekranına gidiliyor")
        self.sayfa.runJavaScript(f"window.__vpKutu = null; if (location.hash !== {json.dumps(self._ekran_sayfa)}) location.hash = {json.dumps(self._ekran_sayfa)};")
        if not hasattr(self, "_ekran_zamanlayici"):
            self._ekran_zamanlayici = QTimer(self)
            self._ekran_zamanlayici.timeout.connect(self._ekran_tik)
        self._ekran_zamanlayici.stop()
        self._ekran_bos_kadar = time.time() + 10    # ekranın yüklenmesi için bekleme
        self._ekran_zamanlayici.start(800)

    def _ekran_bitir(self, neden: str = ""):
        self._ekran_zamanlayici.stop()
        self._ekran_bekle = None
        self.b_yil.setEnabled(True)
        if neden:
            self.tani("ekran yolu durdu: " + neden)
        fn, self._ekran_bitince = self._ekran_bitince, None
        if fn:
            fn(*self._ekran_say)

    def _ekran_tik(self):
        if time.time() < getattr(self, "_ekran_bos_kadar", 0) or getattr(self, "_ekran_js", False):
            return
        if self._ekran_bekle is not None:
            if time.time() - self._ekran_zaman > EKRAN_YANIT_SN:
                a, b = self._ekran_bekle
                self._ekran_bekle = None
                if self._ekran_deneme < 2:
                    self.tani(f"ekran yolu: {a:%m.%Y} için {EKRAN_YANIT_SN} sn yanıt gelmedi, ekran yeniden açılıp bir kez daha denenecek")
                    self._ekran_aylar.insert(0, (a, b))
                    self.sayfa.runJavaScript(f"window.__vpKutu = null; location.hash = '#!/'; setTimeout(function(){{ location.hash = {json.dumps(self._ekran_sayfa)}; }}, 3000);")
                    self._ekran_bos_kadar = time.time() + 20
                else:
                    self.tani(f"ekran yolu: {a:%m.%Y} için yanıt gelmedi, bu ay atlandı")
                    self._ekran_deneme = 0
            return
        if not self._ekran_aylar:
            self._ekran_bitir()
            return
        a, b = self._ekran_aylar[0]
        self._ekran_js = True
        sira = self._ekran_say[1] - len(self._ekran_aylar) + 1
        self.bilgi.setText(f"Ekran yoluyla alınıyor ({sira}/{self._ekran_say[1]}): {a:%d.%m.%Y} – {b:%d.%m.%Y}")

        def sonuc(r, a=a, b=b, sira=sira):
            self._ekran_js = False
            try:
                d = json.loads(r) if isinstance(r, str) else {}
            except ValueError:
                d = {}
            if d.get("git"):
                self.tani(f"ekran yolu {a:%m.%Y}: sayfa başka ekrandaydı, {self._ekran_sayfa} ekranına dönülüyor")
                self._ekran_bos_kadar = time.time() + 10
                self._ekran_bulunamadi += 1
            elif not d.get("kutu") or d.get("kutu", 0) < 2 or not d.get("dugme"):
                self._ekran_bulunamadi += 1
                self.tani(f"ekran yolu {a:%m.%Y}: tarih kutusu {d.get('kutu', 0)}, 'Planlanan + Gerçekleşen' düğmesi {d.get('dugme', 0)}"
                          " → ekran yeniden açılıyor")
                self.sayfa.runJavaScript(f"window.__vpKutu = null; location.hash = '#!/'; setTimeout(function(){{ location.hash = {json.dumps(self._ekran_sayfa)}; }}, 3000);")
                self._ekran_bos_kadar = time.time() + 15
            else:
                self._ekran_bulunamadi = 0
                self._ekran_aylar.pop(0)
                self._ekran_deneme += 1
                self._ekran_bekle = (a, b)
                self._ekran_zaman = time.time()
                self._ekran_log = sira == 1 or self._ekran_deneme > 1
            if self._ekran_bulunamadi >= 10:
                self._ekran_bitir("tarih kutuları ya da düğme bulunamıyor (ekran değişmiş olabilir). "
                                  "Pivot ekranını açık bırakıp yeniden deneyin.")
        self.sayfa.runJavaScript(_EKRAN_DONEM % (json.dumps(f"{a:%d-%m-%Y}"), json.dumps(f"{b:%d-%m-%Y}"),
                                                 json.dumps(self._ekran_sayfa)), 0, sonuc)

    def _ekran_yanit(self, meta: dict):
        """Ekran yolunda beklenen ayın listesi geldi mi (gelen dönem beklenenle örtüşüyorsa)."""
        if getattr(self, "_ekran_bekle", None) is None or not meta.get("ilk"):
            return
        from datetime import date as _d
        a, b = self._ekran_bekle
        gi, gs = _d.fromisoformat(meta["ilk"]), _d.fromisoformat(meta["son"])
        if gi <= a and gs >= min(b, _d.today()) - timedelta(days=0) or (gi == a):
            self._ekran_say[0] += 1
            self.tani(f"ekran yolu {a:%m.%Y}: alındı ({gi:%d.%m} – {gs:%d.%m})")
            self._ekran_bekle = None
            self._ekran_deneme = 0
            atla = [x for x in self._ekran_aylar if x[0] >= gi and min(x[1], _d.today() - timedelta(days=1)) <= gs]
            if atla:                                       # gelen liste sonraki ayları da içeriyor: onları yeniden isteme
                self._ekran_aylar = [x for x in self._ekran_aylar if x not in atla]
                self._ekran_say[0] += len(atla)
                self.tani(f"ekran yolu: gelen liste {len(atla)} ayı daha kapsıyor ({atla[0][0]:%m.%Y} – {atla[-1][0]:%m.%Y}), onlar yeniden istenmeyecek")
        else:
            self.tani(f"ekran yolu {a:%m.%Y}: gelen dönem farklı ({gi:%d.%m.%Y} – {gs:%d.%m.%Y}); tarih kutuları değişmemiş olabilir")

    def _ekran_yazildi(self, mesaj: str):
        p = mesaj.split("|")
        if getattr(self, "_ekran_log", True) and self._ekran_bekle:
            self.tani(f"ekran yolu {self._ekran_bekle[0]:%m.%Y}: kutularda okunan {p[1] if len(p) > 1 else '?'} / {p[2] if len(p) > 2 else '?'}; düğmeye basıldı")

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
            if hasattr(self, "_ekran_zamanlayici"):
                self._ekran_zamanlayici.stop()
            self._ekran_bitince = None
            self.kaydedici.bitir()
            self.web.setPage(None)
            self.sayfa.deleteLater()
        except Exception:  # noqa: BLE001
            pass
        if self._kapaninca:
            QTimer.singleShot(500, self._kapaninca)
        super().closeEvent(e)


def ac(db_yolu: str, parent=None, kapaninca: Optional[Callable[[], None]] = None) -> PersonelVeriPenceresi:
    for w in list(_PENCERELER):                   # arka planda süren otomatik çekim, iki sayfa birbirine karışmasın diye durur
        if w.otomatik:
            try:
                w._otomatik_bitir(False, ERTELENDI + ": pencere elle açıldı, otomatik çekim sonra yeniden denenecek")
            except Exception:  # noqa: BLE001
                pass
    d = PersonelVeriPenceresi(db_yolu, parent, kapaninca)
    d.setAttribute(Qt.WA_DeleteOnClose)
    d.show()
    return d


def otomatik_calistir(db_yolu: str, ilk, son, parent, bitince: Callable[[bool, str], None]) -> Optional[PersonelVeriPenceresi]:
    """Görünmez pencereyle: giriş (kayıtlı şifreyle), [ilk, son] ay ay giriş-çıkış listesi ve personel listesi."""
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
