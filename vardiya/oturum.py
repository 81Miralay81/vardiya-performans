"""Açık programlar ve "tüm açık programları kapat" (güncelleme öncesi; yalnızca exe, tarayıcıda yok).

Her açık program ortak veri tabanına (NAS) yarım dakikada bir "buradayım" yazar (oturum tablosu). Ayarlar'daki düğme
veri tabanına bir kapatma isteği yazar; isteği gören diğer programlar kullanıcıya 60 saniyelik geri sayım gösterip
kapanır. İsteği veren bilgisayar ve istekten sonra açılan programlar kapanmaz. Veri tabanı işleri arka planda yapılır,
ağ diski yavaş olsa da pencere donmaz.
"""
from __future__ import annotations

import getpass
import json
import socket
import threading
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

from PySide6.QtCore import QObject, QTimer, Signal

from . import veritabani as vt

ARALIK_SN = 30
GERI_SAYIM_SN = 60
BICIM = "%Y-%m-%d %H:%M:%S"
SEMA = ("CREATE TABLE IF NOT EXISTS oturum (kimlik TEXT PRIMARY KEY, pc TEXT, kullanici TEXT, surum TEXT, "
        "baslangic TEXT, son TEXT)")


def _pc() -> str:
    try:
        return socket.gethostname()
    except OSError:
        return "?"


def _kullanici() -> str:
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001
        return ""


def acik_programlar(con) -> List[dict]:
    """Son iki dakikada "buradayım" yazan programlar."""
    con.execute(SEMA)
    sinir = (datetime.now() - timedelta(seconds=ARALIK_SN * 4)).strftime(BICIM)
    return [dict(r) for r in con.execute("SELECT kimlik, pc, kullanici, surum, baslangic, son FROM oturum WHERE son >= ? "
                                         "ORDER BY pc", (sinir,))]


def kapat_iste(con, kimlik: str) -> None:
    vt.ayar_yaz(con, "kapat_istegi", {"zaman": datetime.now().strftime(BICIM), "kimlik": kimlik, "pc": _pc()})


class Oturum(QObject):
    kapat_istendi = Signal(str)            # isteyen bilgisayarın adı

    def __init__(self, db_yolu: str, parent=None):
        super().__init__(parent)
        from .surum import SURUM
        self.db_yolu = db_yolu
        self.kimlik = uuid.uuid4().hex
        self.baslangic = datetime.now().strftime(BICIM)
        self.surum = SURUM
        self._dur = threading.Event()
        self._istek: Optional[str] = None
        self._bildirildi = False
        threading.Thread(target=self._dongu, name="oturum", daemon=True).start()
        self._bak = QTimer(self)               # arka plan iş parçacığının bulduğu isteği pencere tarafında işler
        self._bak.timeout.connect(self._isteg_bak)
        self._bak.start(2000)

    def _dongu(self):
        con = None
        while not self._dur.is_set():
            try:
                if con is None:
                    con = vt.ac(self.db_yolu)
                    con.execute(SEMA)
                simdi = datetime.now().strftime(BICIM)
                con.execute("INSERT INTO oturum(kimlik, pc, kullanici, surum, baslangic, son) VALUES(?,?,?,?,?,?) "
                            "ON CONFLICT(kimlik) DO UPDATE SET son=excluded.son",
                            (self.kimlik, _pc(), _kullanici(), self.surum, self.baslangic, simdi))
                eski = (datetime.now() - timedelta(days=1)).strftime(BICIM)
                con.execute("DELETE FROM oturum WHERE son < ?", (eski,))
                con.commit()
                r = con.execute("SELECT deger FROM ayar WHERE anahtar='kapat_istegi'").fetchone()
                if r:
                    d = json.loads(r[0])
                    if d.get("zaman", "") > self.baslangic and d.get("kimlik") != self.kimlik:
                        self._istek = d.get("pc") or "?"
            except Exception:  # noqa: BLE001  (ağ kesintisi vb.: bir sonraki turda yeniden denenir)
                try:
                    if con is not None:
                        con.close()
                except Exception:  # noqa: BLE001
                    pass
                con = None
            self._dur.wait(ARALIK_SN)
        try:
            if con is None:
                con = vt.ac(self.db_yolu)
            con.execute("DELETE FROM oturum WHERE kimlik=?", (self.kimlik,))
            con.commit()
            con.close()
        except Exception:  # noqa: BLE001
            pass

    def _isteg_bak(self):
        if self._istek and not self._bildirildi:
            self._bildirildi = True
            self.kapat_istendi.emit(self._istek)

    def bitir(self):
        self._dur.set()


def kapanis_uyarisi(pencere, kimden: str):
    """60 saniyelik geri sayımla programı kapatır ("Şimdi kapat" düğmesiyle hemen)."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QPushButton
    kutu = QMessageBox(pencere)
    kutu.setWindowTitle("Program kapatılıyor")
    kutu.setIcon(QMessageBox.Warning)
    kutu.setWindowModality(Qt.NonModal)
    b = kutu.addButton("Şimdi kapat", QMessageBox.AcceptRole)
    kalan = [GERI_SAYIM_SN]

    def yaz():
        kutu.setText(f"Program güncelleneceği için {kimden} bilgisayarından kapatma isteği geldi.\n\n"
                     f"Vardiya Performans {kalan[0]} saniye sonra kapanacak. Güncelleme bitince yeniden açabilirsiniz.")

    def kapat():
        try:
            pencere.close()
        finally:
            QApplication.quit()

    def tik():
        kalan[0] -= 1
        if kalan[0] <= 0:
            zaman.stop()
            kapat()
        else:
            yaz()
    zaman = QTimer(kutu)
    zaman.timeout.connect(tik)
    b.clicked.connect(kapat)
    yaz()
    kutu.show()
    kutu.raise_()
    zaman.start(1000)
    pencere._kapanis_kutusu = kutu
