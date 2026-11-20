"""Meyer (MEWARE PDKS) — DENEME aşaması: Meyer programın içinde açılır, sayfanın kendi getirdiği veriler yakalanır.

Giriş Meyer'in kendi giriş ekranından yapılır (kullanıcı adı ve şifre isterse bu bilgisayarda saklanır ve forma
otomatik doldurulur; şifreleme işini Meyer'in kendi sayfası yapar, program şifre çözmez, captcha aşmaz).
Sayfanın Meyer sunucusundan aldığı yanıtlar (TAPIVOT vb.) yerel klasöre JSON olarak kaydedilir. Giriş yanıtı ve
oturum anahtarı hiçbir zaman kaydedilmez. Bu aşamanın amacı verinin biçimini görmek; sonra kayıt ve otomatik çekim gelecek.
"""
from __future__ import annotations

import base64
import json
import os
import time
from typing import Optional

from PySide6.QtCore import QSettings, QUrl, Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton, QSplitter, QVBoxLayout,
                               QWidget)

ADRES = "https://meyer.teknorot.com/"
_AYAR = ("Teknorot", "VardiyaPerformans")

# Sayfaya en başta eklenen betik: XMLHttpRequest ve fetch yanıtlarını programa iletir (giriş yanıtı hariç).
_YAKALA = r"""
(function(){
  if (window.__vpYakala) return; window.__vpYakala = true;
  function gonder(url, metin){
    try {
      if (!url || url.indexOf('/api/') < 0) return;
      var yol = url.split('?')[0];
      if (/login|token|auth/i.test(yol)) return;                 // giriş / oturum yanıtları kaydedilmez
      if (!metin || metin.length < 2 || metin.indexOf('tokenid') >= 0) return;
      var parca = 200000, n = Math.ceil(metin.length / parca), kimlik = Date.now() + '_' + Math.random().toString(36).slice(2, 7);
      for (var i = 0; i < n; i++) console.log('VPMEYER|' + kimlik + '|' + i + '|' + n + '|' + yol + '|' + metin.substr(i * parca, parca));
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

# Giriş formunu doldurur (AngularJS'in görmesi için input/change olayları da tetiklenir).
_DOLDUR = r"""
(function(k, s){
  var sifre = document.querySelector('input[type=password]');
  if (!sifre) return 'form yok';
  var tum = Array.prototype.slice.call(document.querySelectorAll('input'));
  var ad = null;
  for (var i = tum.indexOf(sifre) - 1; i >= 0; i--) { var t = (tum[i].type || 'text').toLowerCase(); if (t === 'text' || t === 'email') { ad = tum[i]; break; } }
  function yaz(e, v){ if (!e) return; e.focus(); e.value = v; e.dispatchEvent(new Event('input', {bubbles: true})); e.dispatchEvent(new Event('change', {bubbles: true})); }
  yaz(ad, k); yaz(sifre, s);
  var dug = Array.prototype.slice.call(document.querySelectorAll('button, input[type=submit], a')).filter(function(b){ return /giri/i.test(b.textContent || b.value || ''); })[0];
  if (dug) { setTimeout(function(){ dug.click(); }, 300); return 'dolduruldu'; }
  return 'buton yok';
})(%s, %s);
"""


def klasor() -> str:
    from . import teshis
    k = os.path.join(teshis.kayit_klasoru(), "meyer_yakalanan")
    os.makedirs(k, exist_ok=True)
    return k


def kimlik_oku():
    a = QSettings(*_AYAR)
    k = str(a.value("meyer/kullanici", "") or "")
    try:
        s = base64.b64decode(str(a.value("meyer/sifre", "") or "")).decode("utf8")
    except Exception:  # noqa: BLE001
        s = ""
    return k, s


def kimlik_yaz(k: str, s: str):
    a = QSettings(*_AYAR)
    a.setValue("meyer/kullanici", k)
    a.setValue("meyer/sifre", base64.b64encode(s.encode("utf8")).decode())
    a.sync()


def ozet(metin: str) -> str:
    """Yakalanan yanıtın kısa tarifi: kaç satır, hangi alanlar, kişi bazlı mı, giriş-çıkış saati var mı."""
    try:
        v = json.loads(metin)
    except ValueError:
        return f"{len(metin)} karakter (JSON değil)"
    if isinstance(v, list) and v and isinstance(v[0], dict):
        alanlar = list(v[0].keys())
        gun = [a for a in alanlar if a.startswith("y20")]
        kisi = any(isinstance(x.get("ypersonel"), str) and not str(x.get("ysicilid", "")).startswith("m") for x in v)
        saat = any(":" in str(x.get(g, "")) and any(c.isdigit() for c in str(x.get(g, ""))) for x in v[:20] for g in gun)
        return (f"{len(v)} satır · {len(gun)} gün sütunu" + (f" ({gun[0][1:].replace('x', '-')} … {gun[-1][1:].replace('x', '-')})" if gun else "")
                + (" · KİŞİ BAZLI" if kisi else " · vardiya sayıları") + (" · saat içeriyor" if saat else ""))
    return f"{type(v).__name__}"


_PROFIL = None


def _profil(QWebEngineProfile, QWebEngineScript):
    """Tek, kalıcı tarayıcı profili (oturum çerezleri bu bilgisayarda kalır; pencere her açıldığında yeniden giriş gerekmez)."""
    global _PROFIL
    if _PROFIL is None:
        from PySide6.QtWidgets import QApplication
        p = QWebEngineProfile("vp_meyer", QApplication.instance())
        p.setPersistentStoragePath(os.path.abspath(os.path.join(klasor(), "..", "meyer_tarayici")))
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


class MeyerPenceresi(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Meyer (PDKS) – deneme")
        from .sayfa_operator import _buyuk_pencere
        _buyuk_pencere(self, 0.92)
        self._parcalar: dict = {}
        self._sayac = 0
        l = QVBoxLayout(self)
        ust = QHBoxLayout()
        k, s = kimlik_oku()
        self.kul = QLineEdit(k)
        self.kul.setPlaceholderText("Meyer kullanıcı adı")
        self.sif = QLineEdit(s)
        self.sif.setPlaceholderText("Meyer şifresi")
        self.sif.setEchoMode(QLineEdit.Password)
        b_gir = QPushButton("Kaydet ve giriş yap")
        b_gir.setObjectName("Ana")
        b_gir.setToolTip("Kullanıcı adı ve şifre yalnızca bu bilgisayarda saklanır; Meyer'in giriş formuna doldurulur.")
        b_gir.clicked.connect(self._giris)
        b_kl = QPushButton("Kayıt klasörünü aç")
        b_kl.clicked.connect(lambda: os.startfile(klasor()) if hasattr(os, "startfile") else None)
        for w in (QLabel("Kullanıcı"), self.kul, QLabel("Şifre"), self.sif, b_gir, b_kl):
            ust.addWidget(w)
        l.addLayout(ust)
        self.bilgi = QLabel("Meyer'e giriş yapın; sonra PDKS ekranında 'Planlanan + Gerçekleşen'i açın, tarih aralığını seçin ve listeyi "
                            "aşağı kaydırın. Sayfanın getirdiği her veri sağdaki listede görünür ve kayıt klasörüne yazılır.")
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
                if mesaj.startswith("VPMEYER|"):
                    ust_._parca(mesaj)
        self.web = QWebEngineView()
        self.sayfa = _Sayfa(self.profil, self.web)
        self.web.setPage(self.sayfa)
        self.web.load(QUrl(ADRES))
        bol.addWidget(self.web)
        sag = QWidget()
        sl = QVBoxLayout(sag)
        sl.setContentsMargins(6, 0, 0, 0)
        sl.addWidget(QLabel("Yakalanan veriler"))
        self.liste = QListWidget()
        sl.addWidget(self.liste)
        bol.addWidget(sag)
        bol.setSizes([1300, 380])
        l.addWidget(bol, 1)

    def closeEvent(self, e):  # noqa: N802
        try:
            self.web.setPage(None)
            self.sayfa.deleteLater()
        except Exception:  # noqa: BLE001
            pass
        super().closeEvent(e)

    def _giris(self):
        k, s = self.kul.text().strip(), self.sif.text()
        kimlik_yaz(k, s)
        js = _DOLDUR % (json.dumps(k), json.dumps(s))
        self.sayfa.runJavaScript(js, 0, lambda r: self.bilgi.setText(
            "Giriş formu dolduruldu ve gönderildi. Ekranda doğrulama (captcha) çıkarsa onu siz tamamlayın." if r == "dolduruldu"
            else "Giriş formu bulunamadı: Meyer'in giriş ekranı açıkken basın (zaten giriş yaptıysanız gerek yok)."))

    def _parca(self, mesaj: str):
        try:
            _, kimlik, i, n, yol, parca = mesaj.split("|", 5)
            i, n = int(i), int(n)
        except ValueError:
            return
        d = self._parcalar.setdefault(kimlik, [None] * n)
        d[i] = parca
        if any(x is None for x in d):
            return
        metin = "".join(self._parcalar.pop(kimlik))
        self._sayac += 1
        ad = yol.rstrip("/").split("/")[-1] or "yanit"
        dosya = os.path.join(klasor(), f"{time.strftime('%Y%m%d_%H%M%S')}_{self._sayac:03d}_{ad}.json")
        try:
            with open(dosya, "w", encoding="utf-8") as f:
                f.write(metin)
        except OSError:
            dosya = "(yazılamadı)"
        self.liste.insertItem(0, f"{self._sayac}. {ad}: {ozet(metin)}")
        self.liste.item(0).setToolTip(dosya)


def ac(parent=None) -> Optional[MeyerPenceresi]:
    d = MeyerPenceresi(parent)
    d.setAttribute(Qt.WA_DeleteOnClose)
    d.show()
    return d
