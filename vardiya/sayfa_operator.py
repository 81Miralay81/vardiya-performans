"""Operatör sayfası: operatör bazında performans, duruş, makineler arası çakışan duruşlar."""
from __future__ import annotations

from typing import Dict, List

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout,
                               QHeaderView, QLabel, QMessageBox, QPushButton, QTableWidget, QTabWidget, QVBoxLayout, QWidget)

from . import tema, veritabani as vt
from .operator import OperatorSonuc, operator_adi, operatorleri_hesapla
from .sayfa_kayitlar import _Oge
from .sayfa_ortak import CizimWidget, etiket, kart, tablo_menusu

BASLIKLAR = ["Operatör", "Makine", "Gün", "Kayıtlı süre", "Çalışma %", "Duruş %", "Mola %", "Toplam duruş", "Çakışan duruş",
             "Ayar kaybı", "Boşta süre", "Boşta %", "Belgesiz duruş", "En uzun duruş", "Duruş adedi", "Ort. makine"]
BASLIK_ACIKLAMA = {
    "Kayıtlı süre": "Operatörün makinelerinde kayıtlı olduğu toplam süre (çalışma + duruş + mola, saat:dakika)",
    "Toplam duruş": "Operatörün makinelerindeki duruşların toplamı (mola hariç)",
    "Çakışan duruş": "Aynı anda en az iki makinenin birlikte durduğu süre. Tıklayınca liste açılır.",
    "Ayar kaybı": "Operatör bir makinede SETUP/Kurulum yaparken öbür makinelerinde biriken duruş süresi. Tıklayınca liste açılır.",
    "Boşta süre": "Operatörün molada olmayan TÜM makineleri aynı anda çalışırken geçen süre: yapacak işi yok, boşta. Tıklayınca liste açılır.",
    "Boşta %": "Boşta süre, operatörün aktif olduğu süreye oranı",
    "Belgesiz duruş": "Duruş nedeni girilmemiş süre (Belgelenmemiş Duruş)",
    "En uzun duruş": "Tek seferdeki en uzun duruş",
    "Duruş adedi": "Duruş sayısı",
    "Ort. makine": "Operatör çalışırken aynı anda ortalama kaç makineye bakıyor",
}
CAKISMA, AYAR_KAYBI, BOSTA, DURUS_SUTUN, CALISMA_SUTUN = 8, 9, 10, 5, 4
ACIKLAMA = (
    "ORANLAR (Çalışma %, Duruş %, Mola %)\\n"
    "Operatörün çalıştığı her makine ve vardiya için net süre (varsayılan 7,33 saat) esas alınır. Operatör o makinede vardiyanın "
    "yalnızca bir kısmında kayıtlıysa payı o oranda küçülür. Oran önce her gün için ayrı hesaplanır, seçtiğiniz dönemin (hafta, ay) "
    "değeri günlerin ortalamasıdır; dönemin toplamı bölünmez. Çalışma ile duruş birlikte %100'ü aşabilir, çünkü net süreye göre "
    "hesaplanır (mola hariç).\\n\\n"
    "TOPLAM DURUŞ\\nOperatörün makinelerindeki duruşların toplamı (mola sayılmaz). İki makinesi birlikte duruyorsa ikisi de toplanır.\\n\\n"
    "ÇAKIŞAN DURUŞ\\nOperatörün aynı anda en az iki makinesinin duruşta olduğu süre (saat olarak bir kez sayılır). Üç makineden biri duruyor, "
    "ikisi çalışıyorsa çakışma sayılmaz. Sayıya tıklayınca çakışmaların listesi açılır.\\n\\n"
    "AYAR SIRASINDA DİĞER MAKİNE KAYBI\\nOperatör bir makinede SETUP ya da Kurulum duruşundayken, öbür makinelerinde biriken duruş süresi.\\n\\n"
    "TÜM MAKİNELER ÇALIŞIRKEN\\nOperatörün molada olmayan bütün makineleri aynı anda çalışırken geçen süre.\\n\\n"
    "BELGELENMEMİŞ DURUŞ\\nDuruş nedeni girilmemiş süre. EN UZUN DURUŞ: tek seferdeki en uzun duruş. "
    "AYNI ANDA ORT. MAKİNE: operatör çalışırken ortalama kaç makineye birden bakıyor.\\n\\n"
    "Mola kaydındaki makineler o sırada 'aktif' sayılmaz. Operatör adı boş olan kayıtlar listeye girmez.")


KISA_GUN = ('Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt', 'Paz')
ASGARI_SN = 3600     # bundan az kayıtlı süresi olan operatörler (oranları anlamsız çıkar) listeye alınmaz


def hm(sn: float) -> str:
    sn = int(round(sn))
    return f"{sn // 3600}:{sn % 3600 // 60:02d}"


def _tablo(basliklar: List[str]) -> QTableWidget:
    t = QTableWidget(0, len(basliklar))
    t.setHorizontalHeaderLabels(basliklar)
    t.verticalHeader().hide()
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    t.horizontalHeader().setStretchLastSection(True)
    tablo_menusu(t)
    return t


def _hucre(metin: str, anahtar=None, sag: bool = False) -> _Oge:
    o = _Oge(metin)
    o.setData(Qt.UserRole, metin if anahtar is None else anahtar)
    if sag:
        o.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return o


def _doldur(t: QTableWidget, satirlar: List[List[tuple]], genislik=None):
    """satirlar: her hücre (metin, sıralama anahtarı, sağa yaslı)"""
    t.setSortingEnabled(False)
    t.setRowCount(len(satirlar))
    for i, s in enumerate(satirlar):
        for j, (m, a, sag) in enumerate(s):
            t.setItem(i, j, _hucre(m, a, sag))
    if genislik:
        for i, g in enumerate(genislik):
            t.setColumnWidth(i, g)
    t.setSortingEnabled(True)


def gun_grafigi(p, rect, r: OperatorSonuc):
    """Üstte gün gün çalışma / duruş yüzdesi, altta gün gün boşta ve çakışan duruş (saat)."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QPen
    gunler = sorted(r.gunler)
    if not gunler:
        return
    w, h = rect.width(), rect.height()
    k = max(0.85, min(2.5, w / 760))
    p.setFont(tema.font(14 * k, True))
    p.setPen(tema.renk(tema.LACIVERT))
    p.drawText(QRectF(rect.left(), rect.top() + 4 * k, w, 24 * k), Qt.AlignCenter, f"{r.ad} – gün gün")

    def panel(ust, alt, baslik, seriler, tepe, bicim):
        sol, sag = rect.left() + 56 * k, rect.right() - 14 * k
        p.setFont(tema.font(10.5 * k, True))
        p.setPen(tema.renk(tema.YAZI_SOLUK))
        p.drawText(QRectF(sol, ust - 18 * k, sag - sol, 16 * k), Qt.AlignLeft | Qt.AlignVCenter, baslik)
        cizgi = QPen(tema.renk(tema.CIZGI)); cizgi.setWidthF(1)
        for i in range(5):
            y = alt - (alt - ust) * i / 4
            p.setPen(cizgi)
            p.drawLine(int(sol), int(y), int(sag), int(y))
            p.setFont(tema.font(9 * k))
            p.setPen(tema.renk(tema.YAZI_SOLUK))
            p.drawText(QRectF(rect.left(), y - 8 * k, 50 * k, 16 * k), Qt.AlignRight | Qt.AlignVCenter, bicim(tepe * i / 4))
        genis = (sag - sol) / len(gunler)
        kal = genis * 0.7 / len(seriler)
        for gi, g in enumerate(gunler):
            x0 = sol + gi * genis + genis * 0.15
            for si, (ad, renk, deger_fn) in enumerate(seriler):
                v = deger_fn(r.gunler[g])
                bh = (alt - ust) * min(1.0, v / tepe) if tepe else 0
                p.fillRect(QRectF(x0 + si * kal, alt - bh, kal * 0.9, bh), tema.renk(renk))
                p.setFont(tema.font(9 * k, True))
                p.setPen(tema.renk(tema.YAZI))
                p.drawText(QRectF(x0 + si * kal - 10 * k, alt - bh - 16 * k, kal * 0.9 + 20 * k, 14 * k), Qt.AlignCenter, bicim(v))
            p.setFont(tema.font(9.5 * k))
            p.setPen(tema.renk(tema.YAZI))
            p.drawText(QRectF(sol + gi * genis, alt + 3 * k, genis, 16 * k), Qt.AlignCenter,
                       g.strftime("%d.%m") + " " + KISA_GUN[g.weekday()])
        # gösterge
        gx = sag
        for ad, renk, _ in reversed(seriler):
            p.setFont(tema.font(9.5 * k))
            gen = p.fontMetrics().horizontalAdvance(ad) + 22 * k
            gx -= gen
            p.fillRect(QRectF(gx, ust - 14 * k, 10 * k, 10 * k), tema.renk(renk))
            p.setPen(tema.renk(tema.YAZI))
            p.drawText(QRectF(gx + 14 * k, ust - 18 * k, gen, 16 * k), Qt.AlignLeft | Qt.AlignVCenter, ad)

    pay = h - 40 * k
    ust1, alt1 = rect.top() + 56 * k, rect.top() + 40 * k + pay * 0.42
    en = max([r.gunler[g]["calisma"] for g in gunler] + [r.gunler[g]["durus"] for g in gunler] + [1.0])
    tepe1 = max(1.0, round(en * 4) / 4) if en > 1.0 else 1.0
    panel(ust1, alt1, "Çalışma ve duruş oranı (net 7,33 saate göre)",
          [("Çalışma", tema.LACIVERT, lambda d: d["calisma"]), ("Duruş", tema.KIRMIZI, lambda d: d["durus"])],
          tepe1, lambda x: f"%{x * 100:.0f}")
    ust2, alt2 = alt1 + 52 * k, rect.bottom() - 28 * k
    en2 = max([r.gunler[g].get("bosta_sn", 0) / 3600 for g in gunler] + [r.gunler[g].get("cakisan_sn", 0) / 3600 for g in gunler] + [1.0])
    tepe2 = float(-(-en2 // 2) * 2)
    panel(ust2, alt2, "Boşta kaldığı ve çakışan duruş süresi (saat)",
          [("Boşta", tema.YESIL, lambda d: d.get("bosta_sn", 0) / 3600), ("Çakışan duruş", tema.TURUNCU, lambda d: d.get("cakisan_sn", 0) / 3600)],
          tepe2, lambda x: f"{x:.1f}".replace(".", ","))


class CakismaDialog(QDialog):
    """Bir operatörün çakışan duruşları: hangi makineler aynı anda hangi duruşta."""

    def __init__(self, parent, r: OperatorSonuc, sadece_ayar: bool = False, bosta: bool = False):
        super().__init__(parent)
        self.r = r
        self.bosta = bosta
        self.setWindowTitle(f"{'Boşta kaldığı zamanlar' if bosta else 'Çakışan duruşlar'} – {r.ad}")
        self.resize(1000, 600)
        l = QVBoxLayout(self)
        if bosta:
            l.addWidget(etiket(f"{r.ad}: molada olmayan tüm makineleri aynı anda çalışırken geçen zamanlar (boşta).", "AltBaslik"))
        else:
            l.addWidget(etiket(f"{r.ad}: aynı anda en az iki makinesi duruşta olan zamanlar. Üç makineden biri durup ikisi çalışıyorsa "
                               "çakışma sayılmaz.", "AltBaslik"))
        f = QHBoxLayout()
        self.min_sure = QComboBox()
        for ad, sn in (("Tümü", 0), ("1 dakikadan uzun", 60), ("5 dakikadan uzun", 300), ("15 dakikadan uzun", 900)):
            self.min_sure.addItem(ad, sn)
        self.min_sure.setCurrentIndex(2 if bosta else 1)
        self.ayar = QCheckBox("Yalnız ayar (setup) içerenler")
        self.ayar.setChecked(sadece_ayar)
        self.ayar.setVisible(not bosta)
        f.addWidget(etiket("Süre", "KartBaslik", kelime=False))
        f.addWidget(self.min_sure)
        f.addWidget(self.ayar)
        f.addStretch(1)
        self.ozet = etiket("", "AltBaslik", kelime=False)
        f.addWidget(self.ozet)
        l.addLayout(f)
        self.tablo = _tablo(["Başlangıç", "Bitiş", "Süre", "Çalışan makineler"] if bosta else
                            ["Başlangıç", "Bitiş", "Süre", "Duruşta olan makineler", "O sırada çalışan makineler", "Ayar var"])
        l.addWidget(self.tablo, 1)
        self.min_sure.currentIndexChanged.connect(self.doldur)
        self.ayar.toggled.connect(self.doldur)
        self.doldur()

    def doldur(self):
        asgari = self.min_sure.currentData()
        kaynak = self.r.bosta_listesi if self.bosta else self.r.cakismalar
        liste = [e for e in kaynak if e.sn >= asgari and (self.bosta or not self.ayar.isChecked() or e.setup_var)]
        satirlar = []
        for e in liste[:5000]:
            if self.bosta:
                satirlar.append([
                    (e.bas.strftime("%d.%m.%Y %H:%M:%S"), e.bas.timestamp(), False),
                    (e.bit.strftime("%d.%m.%Y %H:%M:%S"), e.bit.timestamp(), False),
                    (f"{int(e.sn // 60)} dk {int(e.sn % 60):02d} sn", e.sn, True),
                    (", ".join(e.calisanlar), None, False)])
                continue
            satirlar.append([
                (e.bas.strftime("%d.%m.%Y %H:%M:%S"), e.bas.timestamp(), False),
                (e.bit.strftime("%d.%m.%Y %H:%M:%S"), e.bit.timestamp(), False),
                (f"{int(e.sn // 60)} dk {int(e.sn % 60):02d} sn", e.sn, True),
                ("   ".join(f"{m}: {tip}" for m, tip in e.duruslar), None, False),
                (", ".join(e.calisanlar) or "-", None, False),
                ("Evet" if e.setup_var else "", None, False)])
        _doldur(self.tablo, satirlar, (150, 150, 100, 380, 200))
        self.tablo.sortByColumn(2, Qt.DescendingOrder)
        toplam = sum(e.sn for e in liste)
        self.ozet.setText(f"{len(liste)} {'kayıt' if self.bosta else 'çakışma'} · toplam {hm(toplam)} (saat:dakika)")


class DetayDialog(QDialog):
    """Bir operatörün makine, gün ve duruş nedeni dökümü."""

    def __init__(self, parent, r: OperatorSonuc):
        super().__init__(parent)
        self.setWindowTitle(f"Operatör ayrıntısı – {r.ad}")
        self.resize(820, 560)
        l = QVBoxLayout(self)
        sekme = QTabWidget()
        l.addWidget(sekme)
        t1 = _tablo(["Makine", "Çalışma", "Duruş", "Mola", "Çalışma payı"])
        _doldur(t1, [[(m, m, False), (hm(v["calisma"]), v["calisma"], True), (hm(v["durus"]), v["durus"], True),
                      (hm(v["mola"]), v["mola"], True),
                      (tema.yuzde(v["calisma"] / max(1, v["calisma"] + v["durus"] + v["mola"]), 1),
                       v["calisma"] / max(1, v["calisma"] + v["durus"] + v["mola"]), True)]
                     for m, v in sorted(r.makineler.items())], (110, 100, 100, 100))
        sekme.addTab(t1, "Makineler")
        t2 = _tablo(["Gün", "Çalışma %", "Duruş %", "Mola %", "Boşta", "Çakışan duruş", "Makine-vardiya"])
        _doldur(t2, [[(g.strftime("%d.%m.%Y") + " " + KISA_GUN[g.weekday()], g.toordinal(), False),
                      (tema.yuzde(v["calisma"], 1), v["calisma"], True), (tema.yuzde(v["durus"], 1), v["durus"], True),
                      (tema.yuzde(v["mola"], 1), v["mola"], True),
                      (hm(v.get("bosta_sn", 0)), v.get("bosta_sn", 0), True), (hm(v.get("cakisan_sn", 0)), v.get("cakisan_sn", 0), True),
                      (str(int(v["birim"])), v["birim"], True)]
                     for g, v in sorted(r.gunler.items())], (160, 100, 100, 100, 90, 110))
        sekme.addTab(t2, "Günler")
        self.grafik = CizimWidget(lambda p, rect: gun_grafigi(p, rect, r), 300, 400,
                                  kopya_resim=lambda: self.grafik.resim(2.0))
        sekme.addTab(self.grafik, "Gün gün grafik")
        t3 = _tablo(["Duruş nedeni", "Süre", "Payı"])
        top = max(1.0, r.durus_sn)
        _doldur(t3, [[(tip, tip, False), (hm(sn), sn, True), (tema.yuzde(sn / top, 1), sn, True)]
                     for tip, sn in sorted(r.durus_tipleri.items(), key=lambda x: -x[1])], (300, 100))
        t3.sortByColumn(1, Qt.DescendingOrder)
        sekme.addTab(t3, "Duruş nedenleri")


class OperatorSayfasi(QWidget):
    def __init__(self, ana):
        super().__init__()
        self.ana = ana
        self._sonuc: Dict[str, OperatorSonuc] = {}
        self._kisa: List[str] = []
        self._kirli = True
        kok = QVBoxLayout(self)
        kok.setContentsMargins(26, 22, 26, 22)
        kok.setSpacing(12)
        ust = QHBoxLayout()
        sol = QVBoxLayout()
        sol.addWidget(etiket("Operatör", "Baslik"))
        sol.addWidget(etiket("Kayıttaki operatörler, baktıkları makineler ve duruşları. Dönem, üstteki seçime göre; oranlar gün gün "
                             "hesaplanıp ortalaması alınır. Sayıya tıklayınca ayrıntı açılır.", "AltBaslik"))
        ust.addLayout(sol, 1)
        self.b_bilgi = QPushButton("Nasıl hesaplanıyor?")
        self.b_excel = QPushButton("Excel'e Aktar")
        self.b_bilgi.clicked.connect(self.bilgi_goster)
        self.b_excel.clicked.connect(self.excele_aktar)
        for b in (self.b_bilgi, self.b_excel):
            ust.addWidget(b, 0, Qt.AlignTop)
        kok.addLayout(ust)
        gl = QHBoxLayout()
        gl.addWidget(etiket("Görünüm", "KartBaslik", kelime=False))
        self.gorunum = QComboBox()
        for ad, v in (("Tüm vardiyalar", 0), ("1. vardiya", 1), ("2. vardiya", 2), ("3. vardiya", 3), ("Vardiya karşılaştırması", 4)):
            self.gorunum.addItem(ad, v)
        self.gorunum.activated.connect(lambda _=0: self.yenile())
        gl.addWidget(self.gorunum)
        self.ozet = etiket("", "AltBaslik", kelime=False)
        gl.addSpacing(12)
        gl.addWidget(self.ozet, 1)
        kok.addLayout(gl)
        self.kars = _tablo(["Operatör"] + [f"{v}.V {m}" for v in (1, 2, 3) for m in ("Çalışma", "Duruş", "Boşta")])
        self.kars.hide()
        kok.addWidget(self.kars, 1)
        self.tablo = _tablo(BASLIKLAR)
        self.tablo.setSortingEnabled(True)
        self.tablo.cellClicked.connect(self._tiklandi)
        self.tablo.cellDoubleClicked.connect(self._cift_tik)
        kok.addWidget(self.tablo, 1)

    # ------------------------------------------------------------------
    def showEvent(self, e):
        super().showEvent(e)
        if self._kirli:
            self.yenile()

    def yenile(self):
        if not self.isVisible():
            self._kirli = True
            return
        self._kirli = False
        gunler = self.ana.donem_gunleri()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            gorunum = self.gorunum.currentData()
            self.kars.setVisible(gorunum == 4)
            self.tablo.setVisible(gorunum != 4)
            if gunler:
                kayit = vt.kayitlari_getir_operatorlu(self.ana.con, min(gunler), max(gunler))
                ayar = self.ana.hesap_ayar()
                operatorsuz = sum(1 for k in kayit if not operator_adi(k[0]))
                if gorunum == 4:
                    self._karsilastir(kayit, gunler, ayar)
                    self._sonuc = {}
                else:
                    tum = operatorleri_hesapla(kayit, gunler, ayar, {gorunum} if gorunum else None)
                    esik = ASGARI_SN if not gorunum else ASGARI_SN / 3
                    self._kisa = sorted(ad for ad, r in tum.items() if r.calisma_sn + r.durus_sn + r.mola_sn < esik)
                    self._sonuc = {ad: r for ad, r in tum.items() if ad not in self._kisa}
            else:
                self._sonuc, operatorsuz, self._kisa = {}, 0, []
                self.kars.setRowCount(0)
            if gorunum != 4:
                self._tabloyu_doldur()
        finally:
            QApplication.restoreOverrideCursor()
        if gorunum == 4:
            self.ozet.setText(f"{self.kars.rowCount()} operatör · 1.V = 1. vardiya (00-08), 2.V = 08-16, 3.V = 16-24 · çalışma ve duruş yüzde, boşta saat:dakika")
            return
        if not self._sonuc:
            self.ozet.setText("Seçilen dönemde operatörlü kayıt yok.")
            return
        en = max(self._sonuc.values(), key=lambda r: r.durus_orani)
        metin = (f"{len(self._sonuc)} operatör · {len(gunler)} gün · en yüksek duruş: {en.ad} ({tema.yuzde(en.durus_orani, 1)})")
        if operatorsuz:
            metin += f" · operatör adı olmayan {operatorsuz} kayıt dışarıda"
        if self._kisa:
            metin += f" · kayıtlı süresi 1 saatten az olduğu için listede yok: {', '.join(self._kisa)}"
        self.ozet.setText(metin)

    def _karsilastir(self, kayit, gunler, ayar):
        sonuclar = {v: operatorleri_hesapla(kayit, gunler, ayar, {v}) for v in (1, 2, 3)}
        adlar = sorted({ad for d in sonuclar.values() for ad, r in d.items() if r.calisma_sn + r.durus_sn + r.mola_sn >= ASGARI_SN / 3})
        satirlar = []
        for ad in adlar:
            s = [(ad, ad, False)]
            for v in (1, 2, 3):
                r = sonuclar[v].get(ad)
                if r and r.calisma_sn + r.durus_sn + r.mola_sn >= ASGARI_SN / 3:
                    s += [(tema.yuzde(r.calisma_orani, 1), r.calisma_orani, True), (tema.yuzde(r.durus_orani, 1), r.durus_orani, True),
                          (hm(r.hepsi_calisirken_sn), r.hepsi_calisirken_sn, True)]
                else:
                    s += [("", -1.0, True)] * 3
            satirlar.append(s)
        _doldur(self.kars, satirlar, (170,) + (105, 95, 95) * 3)
        for i in range(self.kars.rowCount()):
            for v in range(3):
                for off, renk in ((0, "#E8F4D8"), (1, "#FBE3E0")):
                    it = self.kars.item(i, 1 + v * 3 + off)
                    if it and it.text():
                        it.setBackground(QColor(renk))
        self.kars.sortByColumn(0, Qt.AscendingOrder)

    def _tabloyu_doldur(self):
        satirlar = []
        for r in self._sonuc.values():
            kayitli = r.calisma_sn + r.durus_sn + r.mola_sn
            s = [(r.ad, r.ad, False), (str(r.makine_sayisi), r.makine_sayisi, True), (str(r.gun_sayisi), r.gun_sayisi, True),
                 (hm(kayitli), kayitli, True),
                 (tema.yuzde(r.calisma_orani, 1), r.calisma_orani, True), (tema.yuzde(r.durus_orani, 1), r.durus_orani, True),
                 (tema.yuzde(r.mola_orani, 1), r.mola_orani, True),
                 (hm(r.durus_sn), r.durus_sn, True), (hm(r.cakisan_sn), r.cakisan_sn, True),
                 (hm(r.setup_kayip_sn), r.setup_kayip_sn, True), (hm(r.hepsi_calisirken_sn), r.hepsi_calisirken_sn, True),
                 (tema.yuzde(r.bosta_orani, 1) if r.bosta_orani is not None else "", r.bosta_orani or 0.0, True),
                 (hm(r.belgesiz_sn), r.belgesiz_sn, True), (hm(r.en_uzun_durus_sn), r.en_uzun_durus_sn, True),
                 (str(r.durus_adedi), r.durus_adedi, True), (f"{r.ort_makine:.1f}".replace(".", ","), r.ort_makine, True)]
            satirlar.append(s)
        _doldur(self.tablo, satirlar, (170, 70, 50, 100, 105, 95, 85, 115, 120, 95, 100, 80, 135, 120, 110))
        for i in range(self.tablo.rowCount()):
            for j in (CAKISMA, AYAR_KAYBI, BOSTA):
                it = self.tablo.item(i, j)
                if it:
                    f = QFont(it.font())
                    f.setUnderline(True)
                    it.setFont(f)
                    it.setForeground(QColor(tema.LACIVERT))
                    it.setToolTip("Tıklayın: hangi makineler aynı anda hangi duruşta")
            d = self.tablo.item(i, DURUS_SUTUN)
            if d:
                d.setBackground(QColor("#FBE3E0"))
            c = self.tablo.item(i, CALISMA_SUTUN)
            if c:
                c.setBackground(QColor("#E8F4D8"))
        for j, ad in enumerate(BASLIKLAR):
            h = self.tablo.horizontalHeaderItem(j)
            if h and ad in BASLIK_ACIKLAMA:
                h.setToolTip(BASLIK_ACIKLAMA[ad])
        self.tablo.sortByColumn(DURUS_SUTUN, Qt.DescendingOrder)   # en çok duruştan en aza
        self.tablo.horizontalHeader().setSortIndicator(DURUS_SUTUN, Qt.DescendingOrder)

    def _sonuc_al(self, satir: int):
        it = self.tablo.item(satir, 0)
        return self._sonuc.get(it.text()) if it else None

    def _tiklandi(self, satir: int, sutun: int):
        if sutun not in (CAKISMA, AYAR_KAYBI, BOSTA):
            return
        r = self._sonuc_al(satir)
        if r:
            CakismaDialog(self, r, sadece_ayar=(sutun == AYAR_KAYBI), bosta=(sutun == BOSTA)).exec()

    def _cift_tik(self, satir: int, sutun: int):
        if sutun in (CAKISMA, AYAR_KAYBI, BOSTA):
            return
        r = self._sonuc_al(satir)
        if r:
            DetayDialog(self, r).exec()

    def bilgi_goster(self):
        kutu = QMessageBox(self)
        kutu.setWindowTitle("Nasıl hesaplanıyor?")
        kutu.setText(ACIKLAMA.replace("\\n", "\n"))
        kutu.setStandardButtons(QMessageBox.Ok)
        kutu.button(QMessageBox.Ok).setText("Tamam")
        kutu.exec()

    def excele_aktar(self):
        if not self._sonuc:
            self.ana.mesaj("Aktarılacak operatör yok.")
            return
        gunler = self.ana.donem_gunleri()
        yol, _ = QFileDialog.getSaveFileName(self, "Excel olarak kaydet",
                                             f"Operator {min(gunler):%d.%m.%Y}-{max(gunler):%d.%m.%Y}.xlsx", "Excel (*.xlsx)")
        if not yol:
            return
        from openpyxl import Workbook
        wb = Workbook(write_only=True)
        ws = wb.create_sheet("Operatörler")
        ws.append(BASLIKLAR[:3] + ["Kayıtlı süre (saat)", "Çalışma", "Duruş", "Mola", "Toplam duruş (saat)", "Çakışan duruş (saat)",
                                   "Ayar sırasında diğer makine kaybı (saat)", "Boşta (saat)", "Boşta %",
                                   "Belgelenmemiş duruş (saat)", "En uzun duruş (saat)", "Duruş adedi", "Aynı anda ort. makine"])
        for r in sorted(self._sonuc.values(), key=lambda x: -x.durus_orani):
            ws.append([r.ad, r.makine_sayisi, r.gun_sayisi, (r.calisma_sn + r.durus_sn + r.mola_sn) / 3600, r.calisma_orani, r.durus_orani, r.mola_orani,
                       r.durus_sn / 3600, r.cakisan_sn / 3600, r.setup_kayip_sn / 3600, r.hepsi_calisirken_sn / 3600, r.bosta_orani,
                       r.belgesiz_sn / 3600, r.en_uzun_durus_sn / 3600, r.durus_adedi, r.ort_makine])
        ws2 = wb.create_sheet("Çakışan duruşlar")
        ws2.append(["Operatör", "Başlangıç", "Bitiş", "Süre (dk)", "Duruşta olan makineler", "Çalışan makineler", "Ayar var"])
        for r in self._sonuc.values():
            for e in r.cakismalar:
                ws2.append([r.ad, e.bas, e.bit, e.sn / 60, "; ".join(f"{m}: {t}" for m, t in e.duruslar),
                            ", ".join(e.calisanlar), "Evet" if e.setup_var else ""])
        wb.save(yol)
        self.ana.mesaj(f"Kaydedildi: {yol}")
