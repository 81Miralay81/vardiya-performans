"""Operatör varken duran makineler: üzerinde operatör kayıtlıyken duruşta (mola hariç) geçen süre.

Süre yalnızca seçili günlere düşen kısımdır ve çakışan kayıtlar iki kez sayılmaz (aynı zaman aralığı bir kez sayılır).
Hangi duruş türlerinin bu listede gösterileceği ve hangi personelin hariç tutulacağı Ayarlar'dan seçilir.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QFrame, QHeaderView, QTableWidget, QTableWidgetItem

from . import veritabani as vt
from .hesap import DURUS, durus_adi, statu_bul
from .operator import operator_adi
from .sayfa_ortak import etiket, kart, tablo_menusu


def _birlesim(araliklar: List[Tuple[datetime, datetime]]) -> float:
    """Çakışan aralıkların birleşiminin toplam süresi (saat)."""
    toplam, son_bas, son_bit = 0.0, None, None
    for bas, bit in sorted(araliklar):
        if son_bit is None or bas > son_bit:
            if son_bit is not None:
                toplam += (son_bit - son_bas).total_seconds()
            son_bas, son_bit = bas, bit
        elif bit > son_bit:
            son_bit = bit
    if son_bit is not None:
        toplam += (son_bit - son_bas).total_seconds()
    return toplam / 3600.0


def _gunlere_kirp(bas: datetime, bit: datetime, gunler: Iterable[date]) -> List[Tuple[datetime, datetime]]:
    parcalar = []
    g = bas.date()
    while datetime(g.year, g.month, g.day) < bit:
        if g in gunler:
            g0 = datetime(g.year, g.month, g.day)
            a, b = max(bas, g0), min(bit, g0 + timedelta(days=1))
            if b > a:
                parcalar.append((a, b))
        g += timedelta(days=1)
    return parcalar


def hesapla(con, gunler: List[date]) -> List[tuple]:
    """[(toplam saat, makine, operatör, {duruş türü: saat})] çoktan aza; yarım saatten kısa olanlar alınmaz."""
    if not gunler:
        return []
    ayar = vt.ayar_oku(con)
    haric_kisi = set(ayar.get("haric_personel") or [])
    haric_tur = set(ayar.get("op_durus_haric") or [])
    gset = set(gunler)
    aralik: Dict[tuple, List[tuple]] = {}
    tur_aralik: Dict[tuple, Dict[str, List[tuple]]] = {}
    for op, m, tip, bas, bit in vt.kayitlari_getir_operatorlu(con, min(gunler), max(gunler)):
        op = operator_adi(op)
        if not op or op in haric_kisi or statu_bul(tip) != DURUS:
            continue
        ad = durus_adi(tip, bas, bit)
        if ad in haric_tur or tip in haric_tur:
            continue
        for a, b in _gunlere_kirp(bas, bit, gset):
            aralik.setdefault((m, op), []).append((a, b))
            tur_aralik.setdefault((m, op), {}).setdefault(ad, []).append((a, b))
    sonuc = []
    for anahtar, liste in aralik.items():
        top = _birlesim(liste)
        if top >= 0.5:
            turler = {ad: _birlesim(l) for ad, l in tur_aralik[anahtar].items()}
            sonuc.append((top, anahtar[0], anahtar[1], turler))
    sonuc.sort(key=lambda x: -x[0])
    return sonuc


def durus_turleri(con) -> List[str]:
    """Kayıtlarda geçen duruş türleri (mola ve çalışma hariç), alfabetik."""
    return sorted({r[0] for r in con.execute("SELECT DISTINCT tip FROM kayit") if r[0] and statu_bul(r[0]) == DURUS},
                  key=lambda s: s.casefold())


def _saat(sa: float) -> str:
    dk = int(round(sa * 60))
    return f"{dk // 60}:{dk % 60:02d}"


class OperatorluDurusKarti(QFrame):
    def __init__(self):
        super().__init__()
        k = kart(kenar=12)
        self.setLayout(k.layout())
        self.setObjectName("Kart")
        l = self.layout()
        l.addWidget(etiket("OPERATÖR VARKEN DURAN MAKİNELER", "KartBaslik"))
        self.alt = etiket("", "AltBaslik")
        l.addWidget(self.alt)
        self.tablo = QTableWidget(0, 4)
        self.tablo.setHorizontalHeaderLabels(["Makine", "Operatör", "Duruşta geçen süre", "Duruş nedenleri"])
        self.tablo.verticalHeader().setVisible(False)
        self.tablo.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tablo.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tablo.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        for i, g in enumerate((90, 220, 175)):
            self.tablo.setColumnWidth(i, g)
        self.tablo.setMinimumHeight(220)
        tablo_menusu(self.tablo)
        l.addWidget(self.tablo)

    def yenile(self, con, gunler: List[date]):
        satirlar = hesapla(con, gunler)
        self.tablo.setRowCount(len(satirlar))
        for i, (top, m, op, d) in enumerate(satirlar):
            nedenler = ", ".join(f"{ad} {_saat(sa)}" for ad, sa in sorted(d.items(), key=lambda x: -x[1])[:5])
            for j, metin in enumerate((m, op, f"{_saat(top)} saat", nedenler)):
                it = QTableWidgetItem(metin)
                if j == 2:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tablo.setItem(i, j, it)
        if gunler:
            ara = f"{min(gunler):%d.%m.%Y} – {max(gunler):%d.%m.%Y}"
            self.alt.setText((f"{ara} · {len(satirlar)} makine-operatör · yalnızca seçili günler · çakışan süreler bir kez sayılır · "
                              "gösterilecek duruş türleri ve hariç personel Ayarlar'dan seçilir") if satirlar
                             else f"{ara} · operatör kayıtlıyken duruşta bekleyen makine yok")
        else:
            self.alt.setText("Gün seçilmedi")
