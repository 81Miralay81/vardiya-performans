"""Kullanıcılar ve sayfa yetkileri (exe ve tarayıcı aynı kullanıcıları kullanır).

Hiç kullanıcı yokken program eskisi gibi girişsiz açılır. Ayarlar'da ilk kullanıcı (yönetici) açıldığı anda giriş
zorunlu olur. Şifreler açık saklanmaz: rastgele tuz + PBKDF2-SHA256 özeti. "Beni hatırla" bu bilgisayarda rastgele bir
jeton tutar (veri tabanında yalnızca jetonun özeti durur).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime
from typing import Dict, List, Optional

BICIM = "%Y-%m-%d %H:%M:%S"
TUR = 200_000

# Ekranlar (menüde görünen sayfalar) ve özellikler (sayfaların içindeki işlemler). Her biri kullanıcıya ayrı ayrı açılıp kapatılır.
EKRANLAR = (("performans", "Performans"), ("calisma", "Çalışma"), ("durus", "Genel Duruş"), ("mola", "Mola"),
            ("operator", "Operatör"), ("personel", "Personel Durum"), ("rapor", "Raporlar"), ("gecmis", "Geçmiş"),
            ("kayitlar", "Kayıtlar"), ("veri", "Veri Aktar: Cormind'den veri çekme"),
            ("plan", "Vardiya Planla: personel sistemine vardiya yazma (program ve web)"), ("ayar", "Ayarlar"))
OZELLIKLER = (("personel_veri", "Personel verisi çekme (Personel Veri penceresi)"),
              ("personel_kimlik", "Personel kimlik bilgileri (fotoğraf, telefon, yıllık izin)"),
              ("personel_beyaz", "Beyaz yaka personeli görme (Personel Durum: liste, kart, sıralamalar)"),
              ("grup_lideri", "Grup liderini düzeltme (Vardiya listesi)"),
              ("excel", "Excel'e aktarma"))
SAYFALAR = EKRANLAR + OZELLIKLER
MENU_YETKI = {"performans": "performans", "hatali": "performans", "calisma": "calisma", "durus": "durus", "mola": "mola",
              "operator": "operator", "personel": "personel", "rapor": "rapor", "gecmis": "gecmis", "kayitlar": "kayitlar",
              "veri": "veri", "plan": "plan", "ayar": "ayar"}
SURUM_ISARET = "_v2"     # bu işaret yoksa yetkiler eski (gruplu) düzende kaydedilmiştir
_ESKI_ACILIM = {"performans": ("calisma", "durus", "mola"), "rapor": ("gecmis",), "veri": ("personel_veri",)}


def etkin_yetkiler(ham: List[str]) -> List[str]:
    """Eski düzende kaydedilmiş yetkileri yeni ayrıntılı düzene açar (eski kullanıcılar bir şey kaybetmesin)."""
    y = set(ham or [])
    if SURUM_ISARET not in y:
        for k, ekler in _ESKI_ACILIM.items():
            if k in y:
                y.update(ekler)
        if y:
            y.update(("excel", "grup_lideri"))
    y.discard(SURUM_ISARET)
    return sorted(y)


SEMA = """
CREATE TABLE IF NOT EXISTS kullanici (ad TEXT PRIMARY KEY COLLATE NOCASE, tuz TEXT NOT NULL, ozet TEXT NOT NULL,
    yetkiler TEXT NOT NULL DEFAULT '[]', yonetici INTEGER NOT NULL DEFAULT 0, aktif INTEGER NOT NULL DEFAULT 1,
    olusturma TEXT, son_giris TEXT);
CREATE TABLE IF NOT EXISTS kullanici_jeton (ozet TEXT PRIMARY KEY, ad TEXT NOT NULL, olusturma TEXT);
"""


def kur(con) -> None:
    con.executescript(SEMA)


def _ozet(sifre: str, tuz: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", sifre.encode("utf-8"), bytes.fromhex(tuz), TUR).hex()


def _satir(r) -> dict:
    d = dict(r)
    try:
        d["yetkiler"] = etkin_yetkiler(list(json.loads(d.get("yetkiler") or "[]")))
    except ValueError:
        d["yetkiler"] = []
    d.pop("tuz", None)
    d.pop("ozet", None)
    d["yonetici"] = bool(d.get("yonetici"))
    d["aktif"] = bool(d.get("aktif"))
    return d


def var_mi(con) -> bool:
    kur(con)
    return con.execute("SELECT 1 FROM kullanici WHERE aktif=1 LIMIT 1").fetchone() is not None


def liste(con) -> List[dict]:
    kur(con)
    return [_satir(r) for r in con.execute("SELECT * FROM kullanici ORDER BY ad")]


def getir(con, ad: str) -> Optional[dict]:
    kur(con)
    r = con.execute("SELECT * FROM kullanici WHERE ad=?", (ad,)).fetchone()
    return _satir(r) if r else None


def kaydet(con, ad: str, sifre: Optional[str], yetkiler: List[str], yonetici: bool, aktif: bool = True,
           eski_ad: Optional[str] = None) -> None:
    """Yeni kullanıcı ya da düzenleme (sifre None/boş: değişmez). Son etkin yönetici kaldırılamaz."""
    kur(con)
    ad = ad.strip()
    if not ad:
        raise ValueError("Kullanıcı adı boş olamaz")
    mevcut = con.execute("SELECT * FROM kullanici WHERE ad=?", (eski_ad or ad,)).fetchone()
    if mevcut is None and not sifre:
        raise ValueError("Yeni kullanıcı için şifre gerekli")
    if mevcut is None and not var_mi(con):
        yonetici, aktif = True, True                       # ilk kullanıcı her zaman yönetici
    if mevcut is not None and bool(mevcut["yonetici"]) and bool(mevcut["aktif"]) and not (yonetici and aktif) and _yonetici_sayisi(con) <= 1:
        raise ValueError("Son yöneticinin yöneticiliği kaldırılamaz")
    if eski_ad and eski_ad.lower() != ad.lower() and con.execute("SELECT 1 FROM kullanici WHERE ad=?", (ad,)).fetchone():
        raise ValueError("Bu kullanıcı adı zaten var")
    if mevcut is None and con.execute("SELECT 1 FROM kullanici WHERE ad=?", (ad,)).fetchone():
        raise ValueError("Bu kullanıcı adı zaten var")
    yet = json.dumps(sorted(set(yetkiler) | {SURUM_ISARET}), ensure_ascii=False)
    if mevcut is None:
        tuz = secrets.token_hex(16)
        con.execute("INSERT INTO kullanici(ad, tuz, ozet, yetkiler, yonetici, aktif, olusturma) VALUES(?,?,?,?,?,?,?)",
                    (ad, tuz, _ozet(sifre, tuz), yet, int(yonetici), int(aktif), datetime.now().strftime(BICIM)))
    else:
        con.execute("UPDATE kullanici SET ad=?, yetkiler=?, yonetici=?, aktif=? WHERE ad=?",
                    (ad, yet, int(yonetici), int(aktif), mevcut["ad"]))
        con.execute("UPDATE kullanici_jeton SET ad=? WHERE ad=?", (ad, mevcut["ad"]))
        if sifre:
            tuz = secrets.token_hex(16)
            con.execute("UPDATE kullanici SET tuz=?, ozet=? WHERE ad=?", (tuz, _ozet(sifre, tuz), ad))
            con.execute("DELETE FROM kullanici_jeton WHERE ad=?", (ad,))       # şifre değişince hatırlanan girişler biter
        if not aktif:
            con.execute("DELETE FROM kullanici_jeton WHERE ad=?", (ad,))
    con.commit()


def _yonetici_sayisi(con) -> int:
    return con.execute("SELECT COUNT(*) FROM kullanici WHERE yonetici=1 AND aktif=1").fetchone()[0]


def sil(con, ad: str) -> None:
    kur(con)
    r = con.execute("SELECT * FROM kullanici WHERE ad=?", (ad,)).fetchone()
    if r is None:
        return
    if r["yonetici"] and r["aktif"] and _yonetici_sayisi(con) <= 1 and con.execute("SELECT COUNT(*) FROM kullanici").fetchone()[0] > 1:
        raise ValueError("Son yönetici silinemez")
    con.execute("DELETE FROM kullanici WHERE ad=?", (ad,))
    con.execute("DELETE FROM kullanici_jeton WHERE ad=?", (ad,))
    con.commit()


def dogrula(con, ad: str, sifre: str) -> Optional[dict]:
    kur(con)
    r = con.execute("SELECT * FROM kullanici WHERE ad=? AND aktif=1", ((ad or "").strip(),)).fetchone()
    if r is None or not sifre:
        _ozet(sifre or "x", "00" * 16)                      # süre farkından kullanıcı adı anlaşılmasın
        return None
    if not hmac.compare_digest(_ozet(sifre, r["tuz"]), r["ozet"]):
        return None
    con.execute("UPDATE kullanici SET son_giris=? WHERE ad=?", (datetime.now().strftime(BICIM), r["ad"]))
    con.commit()
    return _satir(r)


def jeton_olustur(con, ad: str) -> str:
    kur(con)
    j = secrets.token_urlsafe(32)
    con.execute("INSERT INTO kullanici_jeton(ozet, ad, olusturma) VALUES(?,?,?)",
                (hashlib.sha256(j.encode()).hexdigest(), ad, datetime.now().strftime(BICIM)))
    con.commit()
    return j


def jeton_dogrula(con, jeton: str) -> Optional[dict]:
    if not jeton:
        return None
    kur(con)
    r = con.execute("SELECT k.* FROM kullanici_jeton j JOIN kullanici k ON k.ad = j.ad WHERE j.ozet=? AND k.aktif=1",
                    (hashlib.sha256(jeton.encode()).hexdigest(),)).fetchone()
    return _satir(r) if r else None


def jeton_sil(con, jeton: str) -> None:
    if jeton:
        kur(con)
        con.execute("DELETE FROM kullanici_jeton WHERE ozet=?", (hashlib.sha256(jeton.encode()).hexdigest(),))
        con.commit()


def yetkili(kullanici: Optional[dict], anahtar: str) -> bool:
    """kullanici None: kullanıcı sistemi kapalı (herkes her şeyi görür)."""
    if kullanici is None:
        return True
    return bool(kullanici.get("yonetici")) or anahtar in (kullanici.get("yetkiler") or [])


# ====================================================================== arayüz (exe)
def giris_penceresi(con, parent=None) -> Optional[dict]:
    """Kayıtlı jeton geçerliyse doğrudan; değilse giriş penceresi. None: vazgeçildi."""
    from PySide6.QtCore import QSettings, Qt
    from PySide6.QtWidgets import QCheckBox, QDialog, QFormLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout
    from . import tema
    ayar = QSettings("Teknorot", "VardiyaPerformans")
    k = jeton_dogrula(con, str(ayar.value("giris/jeton", "") or ""))
    if k:
        return k
    d = QDialog(parent)
    d.setWindowTitle("Vardiya Performans – Giriş")
    d.setMinimumWidth(380)
    l = QVBoxLayout(d)
    lg = QLabel()
    pm = tema.logo()
    if not pm.isNull():
        lg.setPixmap(pm.scaledToWidth(200, Qt.SmoothTransformation))
    lg.setAlignment(Qt.AlignCenter)
    l.addWidget(lg)
    f = QFormLayout()
    ad = QLineEdit(str(ayar.value("giris/son_ad", "") or ""))
    sifre = QLineEdit()
    sifre.setEchoMode(QLineEdit.Password)
    f.addRow("Kullanıcı adı", ad)
    f.addRow("Şifre", sifre)
    l.addLayout(f)
    hatirla = QCheckBox("Bu bilgisayarda beni hatırla")
    l.addWidget(hatirla)
    hata = QLabel("")
    hata.setStyleSheet(f"color:{tema.KIRMIZI}")
    l.addWidget(hata)
    b = QPushButton("Giriş")
    b.setObjectName("Ana")
    b.setDefault(True)
    l.addWidget(b)
    sonuc = {}

    def dene():
        u = dogrula(con, ad.text(), sifre.text())
        if not u:
            hata.setText("Kullanıcı adı ya da şifre hatalı")
            sifre.clear()
            sifre.setFocus()
            return
        ayar.setValue("giris/son_ad", u["ad"])
        if hatirla.isChecked():
            ayar.setValue("giris/jeton", jeton_olustur(con, u["ad"]))
        sonuc["k"] = u
        d.accept()
    b.clicked.connect(dene)
    (sifre if ad.text() else ad).setFocus()
    d.exec()
    return sonuc.get("k")


def cikis_yap(con) -> None:
    from PySide6.QtCore import QSettings
    ayar = QSettings("Teknorot", "VardiyaPerformans")
    jeton_sil(con, str(ayar.value("giris/jeton", "") or ""))
    ayar.remove("giris/jeton")


class KullaniciPenceresi:
    """Ekle / düzenle penceresi (yalnızca yönetici)."""

    @staticmethod
    def ac(con, parent, mevcut: Optional[dict] = None) -> bool:
        from PySide6.QtWidgets import (QCheckBox, QDialog, QFormLayout, QGroupBox, QLabel, QLineEdit, QMessageBox,
                                       QPushButton, QVBoxLayout, QHBoxLayout)
        d = QDialog(parent)
        d.setWindowTitle("Kullanıcı düzenle" if mevcut else "Yeni kullanıcı")
        d.setMinimumWidth(720)
        l = QVBoxLayout(d)
        f = QFormLayout()
        ad = QLineEdit(mevcut["ad"] if mevcut else "")
        s1, s2 = QLineEdit(), QLineEdit()
        for s in (s1, s2):
            s.setEchoMode(QLineEdit.Password)
        if mevcut:
            s1.setPlaceholderText("değiştirmek için yazın")
        f.addRow("Kullanıcı adı", ad)
        f.addRow("Şifre", s1)
        f.addRow("Şifre (tekrar)", s2)
        l.addLayout(f)
        yon = QCheckBox("Yönetici (her şeyi görür, kullanıcıları yönetir)")
        ilk = not var_mi(con)
        yon.setChecked(bool(mevcut and mevcut["yonetici"]) or ilk)
        yon.setEnabled(not ilk)
        aktif = QCheckBox("Etkin")
        aktif.setChecked(bool(mevcut["aktif"]) if mevcut else True)
        l.addWidget(yon)
        from PySide6.QtWidgets import QGridLayout, QWidget
        g = QWidget()
        gl = QHBoxLayout(g)
        gl.setContentsMargins(0, 0, 0, 0)
        kutular = {}
        for baslik, liste_ in (("Görebileceği ekranlar", EKRANLAR), ("Kullanabileceği özellikler", OZELLIKLER)):
            kutu = QGroupBox(baslik)
            kl = QGridLayout(kutu)
            for i, (k, a) in enumerate(liste_):
                c = QCheckBox(a)
                c.setChecked(bool(mevcut and k in mevcut["yetkiler"]) or (not mevcut and k in ("performans", "operator")))
                kutular[k] = c
                kl.addWidget(c, i, 0)
            sat_ = QHBoxLayout()
            for metin, deger in (("Tümünü seç", True), ("Hiçbiri", False)):
                b = QPushButton(metin)
                b.clicked.connect(lambda _=False, d_=deger, l_=liste_: [kutular[x].setChecked(d_) for x, _a in l_])
                sat_.addWidget(b)
            sat_.addStretch(1)
            kl.addLayout(sat_, len(liste_), 0)
            kl.setRowStretch(len(liste_) + 1, 1)
            gl.addWidget(kutu, 1)
        l.addWidget(g)
        not_ = QLabel("Personel verisi çekme verilen kişide 'Veri Aktar' ekranı açılır; Cormind çekme yetkisi yoksa o ekranda yalnızca personel bölümü görünür.")
        not_.setWordWrap(True)
        l.addWidget(not_)
        yon.toggled.connect(lambda v: g.setEnabled(not v))
        g.setEnabled(not yon.isChecked())
        l.addWidget(aktif)
        if ilk:
            l.addWidget(QLabel("İlk kullanıcı yönetici olur. Kaydedince program girişte kullanıcı adı ve şifre sorar."))
        sat = QHBoxLayout()
        sat.addStretch(1)
        iptal, tamam = QPushButton("Vazgeç"), QPushButton("Kaydet")
        tamam.setObjectName("Ana")
        sat.addWidget(iptal)
        sat.addWidget(tamam)
        l.addLayout(sat)
        iptal.clicked.connect(d.reject)

        def kaydet_():
            if s1.text() != s2.text():
                QMessageBox.warning(d, "Kullanıcı", "Şifreler aynı değil")
                return
            if s1.text() and len(s1.text()) < 4:
                QMessageBox.warning(d, "Kullanıcı", "Şifre en az 4 karakter olmalı")
                return
            try:
                kaydet(con, ad.text(), s1.text() or None, [k for k, c in kutular.items() if c.isChecked()], yon.isChecked(),
                       aktif.isChecked(), eski_ad=mevcut["ad"] if mevcut else None)
            except ValueError as e:
                QMessageBox.warning(d, "Kullanıcı", str(e))
                return
            d.accept()
        tamam.clicked.connect(kaydet_)
        return d.exec() == QDialog.Accepted
