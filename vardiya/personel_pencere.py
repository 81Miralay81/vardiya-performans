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
_YAKALA = r"""
(function(){
  if (window.__vpYakala) return; window.__vpYakala = true;
  function gonder(url, metin){
    try {
      if (!url || url.indexOf('/api/') < 0) return;
      var yol = url.split('?')[0];
      if (/login|token|auth|captcha|sifre|password/i.test(yol)) return;
      if (!metin || metin.length < 3 || metin.charAt(0) !== '[' || metin.indexOf('tokenid') >= 0) return;
      var parca = 200000, n = Math.ceil(metin.length / parca), kimlik = Date.now() + '_' + Math.random().toString(36).slice(2, 7);
      for (var i = 0; i < n; i++) console.log('VPPV|' + kimlik + '|' + i + '|' + n + '|' + metin.substr(i * parca, parca));
    } catch(e) {}
  }
  var ac = XMLHttpRequest.prototype.open, yolla = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(m, u){ this.__vpUrl = u; return ac.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function(){
    var x = this;
    x.addEventListener('load', function(){ try { if (!x.responseType || x.responseType === 'text') gonder(x.__vpUrl, x.responseText); } catch(e) {} });
    return yolla.apply(this, arguments);
  };
  if (window.fetch) {
    var f = window.fetch;
    window.fetch = function(){
      var u = (arguments[0] && arguments[0].url) || String(arguments[0]);
      return f.apply(this, arguments).then(function(r){ try { r.clone().text().then(function(t){ gonder(u, t); }); } catch(e) {} return r; });
    };
  }
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


class _Kaydedici(QObject):
    """Yanıtları arka planda (kendi bağlantısıyla) veri tabanına yazar; ağ diski yavaş olsa da pencere donmaz."""
    sonuc = Signal(str, bool)            # açıklama, kişi bazlı giriş-çıkış verisi mi

    def __init__(self, db_yolu: str):
        super().__init__()
        self._q: "queue.Queue[Optional[str]]" = queue.Queue()
        self._db = db_yolu
        threading.Thread(target=self._calis, name="pv-kayit", daemon=True).start()

    def ekle(self, metin: str):
        self._q.put(metin)

    def bitir(self):
        self._q.put(None)

    def _calis(self):
        from . import personel_veri as pv, veritabani as vt
        con = None
        while True:
            metin = self._q.get()
            if metin is None:
                break
            try:
                if con is None:
                    con = vt.ac(self._db)
                aciklama = pv.isle(con, metin)
                if aciklama:
                    self.sonuc.emit(aciklama, "gün kaydedildi" in aciklama)
            except Exception as e:  # noqa: BLE001
                self.sonuc.emit(f"kaydedilemedi: {e}", False)
                con = None
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
    def __init__(self, db_yolu: str, parent=None, kapaninca: Optional[Callable[[], None]] = None):
        super().__init__(parent)
        self.setWindowTitle("Personel Veri")
        from .sayfa_operator import _buyuk_pencere
        _buyuk_pencere(self, 0.92)
        eski_kayitlari_sil()
        self._kapaninca = kapaninca
        self._parcalar: dict = {}
        self._son_veri = 0.0
        self._kaydir_bas = 0.0
        self._son_giris_denemesi = 0.0
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
        self.bilgi = QLabel("Giriş yapın; sonra 'Planlanan + Gerçekleşen' ekranını açıp ayı seçin ve listeleyin. Program listeyi kendisi "
                            "en alta kaydırır ve gelen veriyi kaydeder; ay ay tekrarlayabilirsiniz.")
        self.bilgi.setWordWrap(True)
        self.bilgi.setObjectName("AltBaslik")
        l.addWidget(self.bilgi)
        bol = QSplitter(Qt.Horizontal)
        try:
            from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineScript
            from PySide6.QtWebEngineWidgets import QWebEngineView
        except Exception as e:  # noqa: BLE001
            l.addWidget(QLabel(f"Tarayıcı motoru yüklenemedi: {e}"))
            return
        self.profil = _profil(QWebEngineProfile, QWebEngineScript)
        ust_ = self

        class _Sayfa(QWebEnginePage):
            def javaScriptConsoleMessage(self, _seviye, mesaj, _satir, _kaynak):  # noqa: N802
                if mesaj.startswith(ONEK):
                    ust_._parca(mesaj)
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

    def _kaydedildi(self, aciklama: str, kisi_verisi: bool):
        self.liste.insertItem(0, f"{time.strftime('%H:%M:%S')}  {aciklama}")
        if kisi_verisi:
            self._son_veri = time.time()
            if not self._kaydir_zaman.isActive():
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
            self.bilgi.setText("Liste tamamlandı ve kaydedildi. Başka bir ay seçip tekrar listeleyebilirsiniz.")
            return
        self.sayfa.runJavaScript(_KAYDIR)

    def closeEvent(self, e):  # noqa: N802
        try:
            self._giris_zaman.stop()
            self._kaydir_zaman.stop()
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
