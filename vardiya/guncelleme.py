"""Otomatik güncelleme: GitHub'daki 'guncel' sürümünü denetler, yenisi varsa indirir, kapanınca yerine koyup yeniden açar.

Not: depo özel (private) ise anonim erişim 404 verir; bu durumda denetim sessizce atlanır.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from typing import Callable, Optional, Tuple

from PySide6.QtCore import QThread, Signal

from .surum import SURUM

DEPO = "81Miralay81/vardiya-performans"
ETIKET = "guncel"
API = f"https://api.github.com/repos/{DEPO}/releases/tags/{ETIKET}"
EXE_ADI = "VardiyaPerformans.exe"
YENI_UZANTI = ".yeni"


def surum_dizisi(s: str) -> Tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", s or ""))


def daha_yeni(aday: str, mevcut: str) -> bool:
    a, m = surum_dizisi(aday), surum_dizisi(mevcut)
    return bool(a) and a > m


def release_coz(veri: dict) -> Optional[Tuple[str, str]]:
    """GitHub release JSON'undan (sürüm, indirme adresi) çıkarır."""
    govde = veri.get("body") or ""
    m = re.search(r"SURUM=([0-9][0-9.]*)", govde)
    if not m:
        return None
    for varlik in veri.get("assets", []):
        if varlik.get("name") == EXE_ADI and varlik.get("browser_download_url"):
            return m.group(1), varlik["browser_download_url"]
    return None


def son_surum(zaman_asimi: float = 6.0) -> Optional[Tuple[str, str]]:
    istek = urllib.request.Request(API, headers={"User-Agent": "VardiyaPerformans", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(istek, timeout=zaman_asimi) as r:
        return release_coz(json.load(r))


def indir(url: str, hedef: str, ilerleme: Optional[Callable[[int, int], None]] = None) -> None:
    gecici = hedef + ".part"
    istek = urllib.request.Request(url, headers={"User-Agent": "VardiyaPerformans"})
    with urllib.request.urlopen(istek, timeout=30) as r, open(gecici, "wb") as f:
        toplam = int(r.headers.get("Content-Length") or 0)
        okunan = 0
        while True:
            parca = r.read(1 << 20)
            if not parca:
                break
            f.write(parca)
            okunan += len(parca)
            if ilerleme:
                ilerleme(okunan, toplam)
    with open(gecici, "rb") as f:
        bas = f.read(2)
    if bas != b"MZ" or os.path.getsize(gecici) < 5_000_000:
        os.remove(gecici)
        raise ValueError("İndirilen dosya geçerli bir program değil")
    os.replace(gecici, hedef)


def bat_icerigi(yeni: str, exe: str) -> str:
    """Program kapanınca yeni dosyayı eskisinin yerine koyar (başkası açıksa ~1 dk dener) ve programı yeniden açar."""
    return (
        "@echo off\r\n"
        "set n=0\r\n"
        ":dene\r\n"
        "timeout /t 2 /nobreak >nul\r\n"
        f'move /Y "{yeni}" "{exe}" >nul 2>&1\r\n'
        "if errorlevel 1 (\r\n"
        "  set /a n+=1\r\n"
        "  if %n% lss 30 goto dene\r\n"
        ")\r\n"
        f'start "" "{exe}"\r\n'
        'del "%~f0"\r\n'
    )


def uygula(yeni: str, exe: str) -> None:
    bat = os.path.join(tempfile.gettempdir(), "vardiya_guncelle.bat")
    with open(bat, "w", encoding="cp1254", errors="replace", newline="") as f:
        f.write(bat_icerigi(yeni, exe))
    bayrak = 0x08000000 | 0x00000008  # CREATE_NO_WINDOW | DETACHED_PROCESS
    subprocess.Popen(["cmd", "/c", bat], creationflags=bayrak, close_fds=True)


def calisan_exe() -> Optional[str]:
    """Yalnızca derlenmiş Windows exe'sinde güncelleme yapılır."""
    if getattr(sys, "frozen", False) and sys.platform.startswith("win"):
        return sys.executable
    return None


class GuncellemeKontrol(QThread):
    """Arka planda sürümü denetler; yenisi varsa indirir ve hazir(sürüm, dosya) sinyalini yollar."""
    hazir = Signal(str, str)

    def __init__(self, exe: str, parent=None):
        super().__init__(parent)
        self.exe = exe

    def run(self):
        try:
            yeni = self.exe + YENI_UZANTI
            iz = yeni + ".surum"
            if os.path.exists(yeni) and os.path.exists(iz):      # daha önce indirilmiş, uygulanamamış
                s = open(iz, encoding="utf8").read().strip()
                if daha_yeni(s, SURUM):
                    self.hazir.emit(s, yeni)
                    return
            bilgi = son_surum()
            if not bilgi or not daha_yeni(bilgi[0], SURUM):
                return
            indir(bilgi[1], yeni)
            with open(iz, "w", encoding="utf8") as f:
                f.write(bilgi[0])
            self.hazir.emit(bilgi[0], yeni)
        except Exception:  # noqa: BLE001 - ağ yok / depo özel / dosya kilitli: sessizce geç
            return
