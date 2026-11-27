"""Vardiya Planla: mavi yaka personelin haftalık vardiyasını hazırlayıp personel sistemine yazar.

Yetki: "plan" (Ayarlar > Kullanıcılar; yönetici her zaman görür). Web'de de aynı yetkiyle açılır (uygulama.html #s-plan).
Okuma ve yazma açık Personel Veri penceresinin sayfası üzerinden yapılır (oturum ve şifreleme sayfada kalır).
Gönderdikten sonra hafta personel sisteminden yeniden okunur: başında "*" kalmayan ve istenen mesaiyi gösteren gün
kaydedilmiş sayılır (yeşil); olmayan kırmızı kalır. Her gönderim "plan_gecmis" tablosuna yazılır; "Geri al" son
gönderimi eski haline döndürür.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel,
                               QMenu, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from . import plan_isleri as pi, vardiya_plan as vp
from .sayfa_ortak import etiket, kart

RENK = {"24:00-08:00": "#E3E0F5", "08:00-16:00": "#DDEBFA", "(CUMA) 08:00-16:00": "#CFE2F8", "16:00-24:00": "#FBE8D3"}
RENK_TATIL = "#5f6f86"
YESIL, KIRMIZI, TURUNCU = "#3e9b2a", "#d64541", "#e0702a"


def _gun_api(g: date) -> str:
    return f"{g:%d-%m-%Y}"


class PlanSayfasi(QWidget):
    def __init__(self, ana):
        super().__init__()
        self.ana = ana
        self.pzt = vp.hafta_basi(date.today() + timedelta(days=7))
        self.kisiler: List[dict] = []
        self.secim: Dict[int, Optional[int]] = {}
        self.elle: Dict[int, Dict[int, str]] = {}
        self.sonuc: Dict[tuple, str] = {}            # (sicilid, gün no) → "ok" | "hata"
        self.gonderilen: set = set()                 # bu ekranda gönderilip henüz doğrulanmayan hücreler
        self._is = False
        kok = QVBoxLayout(self)
        kok.setContentsMargins(24, 20, 24, 20)
        kok.addWidget(etiket("Vardiya Planla", "Baslik"))
        kok.addWidget(etiket("Mavi yaka personelin haftalık vardiyası. Değişiklikler önce burada hazırlanır; yalnızca işaretli "
                             "satırlar personel sistemine gönderilir. Gönderdikten sonra hafta yeniden okunur: kaydedilen gün yeşil, "
                             "kaydedilemeyen kırmızı görünür.", "AltBaslik"))
        ust = kart(QHBoxLayout)
        self.b_geri = QPushButton("◀")
        self.b_ileri = QPushButton("▶")
        self.l_hafta = QLabel()
        self.l_hafta.setStyleSheet("font-weight:700; font-size:15px; color:#150958; padding:0 8px;")
        self.b_geri.clicked.connect(lambda: self._hafta(-7))
        self.b_ileri.clicked.connect(lambda: self._hafta(7))
        for w in (self.b_geri, self.l_hafta, self.b_ileri):
            ust.layout().addWidget(w)
        ust.layout().addStretch(1)
        self.b_oku = QPushButton("Personel sisteminden oku")
        self.b_don = QPushButton("Geçen haftadan döndürerek aktar (3→2→1)")
        self.b_aynen = QPushButton("Döndürmeden aktar")
        self.b_gonder = QPushButton("Personel sistemine gönder")
        self.b_gonder.setObjectName("Birincil")
        self.b_geri_al = QPushButton("Son gönderimi geri al")
        self.b_oku.clicked.connect(self.oku)
        self.b_don.clicked.connect(lambda: self._aktar(True))
        self.b_aynen.clicked.connect(lambda: self._aktar(False))
        self.b_gonder.clicked.connect(self._gonder_sor)
        self.b_geri_al.clicked.connect(self._geri_al)
        for b in (self.b_oku, self.b_don, self.b_aynen, self.b_gonder, self.b_geri_al):
            ust.layout().addWidget(b)
        kok.addWidget(ust)
        self.durum = etiket("", "AltBaslik")
        kok.addWidget(self.durum)
        k = kart()
        self.tablo = QTableWidget(0, 11)
        self.tablo.setHorizontalHeaderLabels(["✓", "Personel", "Dönüş", "Bu hafta"] + vp.GUN_AD)
        self.tablo.verticalHeader().setVisible(False)
        self.tablo.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tablo.setSelectionMode(QAbstractItemView.NoSelection)
        h = self.tablo.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.Stretch)
        for i, w in ((0, 34), (1, 200), (2, 90), (3, 170)):
            h.setSectionResizeMode(i, QHeaderView.Fixed)
            self.tablo.setColumnWidth(i, w)
        self.tablo.verticalHeader().setDefaultSectionSize(34)
        self.tablo.cellClicked.connect(self._hucre_tik)
        k.layout().addWidget(self.tablo)
        k.layout().addWidget(etiket("Bir güne tıklayın: o günü başka mesaiye çevirin ya da kurala döndürün. Turuncu: gönderilince "
                                    "değişecek · yeşil: personel sisteminde kayıtlı (doğrulandı) · kırmızı: kaydedilemedi.", "AltBaslik"))
        kok.addWidget(k, 1)
        self._hafta(0)

    # ------------------------------------------------------------------ yardımcılar
    def _con(self):
        c = self.ana.con
        c.execute(pi.SEMA)
        return c

    def _donus(self) -> Dict[str, str]:
        from . import veritabani as vt
        return dict(vt.ayar_oku(self.ana.con).get("plan_donus") or {})

    def _donus_yaz(self, sid: int, deger: str):
        from . import veritabani as vt
        d = self._donus()
        d[str(sid)] = deger
        vt.ayar_yaz(self.ana.con, "plan_donus", d)

    def _pencere(self):
        return pi.pencere()

    def _pencere_gerek(self) -> Optional[object]:
        w = self._pencere()
        if w is None:
            if QMessageBox.question(self, "Personel Veri penceresi", "Personel sistemine bağlanmak için Personel Veri penceresi açık ve "
                                    "giriş yapılmış olmalı.\n\nŞimdi açılsın mı? (Açılınca giriş yapıp burada yeniden deneyin.)") == QMessageBox.Yes:
                from . import personel_pencere as pp
                self._pv = pp.ac(self.ana.db_yolu, self)
        return w

    def _beyazlar(self) -> set:
        return pi.beyazlar(self.ana.con)

    def _mesgul(self, e: bool, metin: str = ""):
        self._is = e
        for b in (self.b_oku, self.b_don, self.b_aynen, self.b_gonder, self.b_geri_al, self.b_geri, self.b_ileri):
            b.setEnabled(not e)
        if metin:
            self.durum.setText(metin)

    def _hafta(self, gun: int):
        if self._is:
            return
        self.pzt += timedelta(days=gun)
        self.l_hafta.setText(f"{self.pzt:%d.%m.%Y} – {self.pzt + timedelta(days=6):%d.%m.%Y}")
        self.kisiler, self.secim, self.elle, self.sonuc = [], {}, {}, {}
        self._ciz()
        self.durum.setText("Haftayı görmek için \"Personel sisteminden oku\"ya basın.")

    # ------------------------------------------------------------------ okuma
    def _oku_hafta(self, pzt: date, bitince):
        w = self._pencere_gerek()
        if w is None:
            self._mesgul(False, "Personel Veri penceresi açık değil.")
            return
        pi.oku(w, pzt, bitince)

    def oku(self):
        self._mesgul(True, "Personel sisteminden okunuyor…")

        def bitti(d, hata):
            self._mesgul(False)
            if d is None:
                self.durum.setText("Okunamadı: " + hata)
                return
            beyaz = self._beyazlar()
            self.kisiler = [k for k in vp.plan_satirlari(d, self.pzt) if k["sicilid"] not in beyaz]
            self.ham = {int(r["ysicilid"]): r for r in d if str(r.get("ysicilid", "")).isdigit()}
            self.secim = {k["sicilid"]: None for k in self.kisiler}
            self.elle, self.sonuc = {}, {}
            self._ciz()
            self.durum.setText(f"{len(self.kisiler)} kişi okundu ({datetime.now():%H:%M}). Değiştirmek istediğiniz kişinin "
                               "\"Bu hafta\" seçimini yapın, satırını işaretleyip gönderin.")
        self._oku_hafta(self.pzt, bitti)

    def _aktar(self, dondur: bool):
        if not self.kisiler:
            self.durum.setText("Önce bu haftayı okuyun.")
            return
        self._mesgul(True, "Geçen hafta okunuyor…")
        onceki = self.pzt - timedelta(days=7)

        def bitti(d, hata):
            self._mesgul(False)
            if d is None:
                self.durum.setText("Geçen hafta okunamadı: " + hata)
                return
            yeni = pi.aktarim(vp.plan_satirlari(d, onceki), self._donus(), dondur)
            n = 0
            for k in self.kisiler:
                if k["sicilid"] in yeni:
                    self.secim[k["sicilid"]] = yeni[k["sicilid"]]
                    n += 1
            self._ciz()
            self.durum.setText(f"{n} kişinin vardiyası geçen haftadan {'döndürülerek ' if dondur else ''}aktarıldı (henüz gönderilmedi). "
                               "Elle değiştirdiğiniz günler korunur.")
        self._oku_hafta(onceki, bitti)

    # ------------------------------------------------------------------ çizim
    def _ciz(self):
        t = self.tablo
        t.setRowCount(len(self.kisiler))
        donus = self._donus()
        for i, k in enumerate(self.kisiler):
            sid = k["sicilid"]
            cb = QCheckBox()
            cb.setProperty("sid", sid)
            w = QWidget()
            l = QHBoxLayout(w)
            l.setContentsMargins(8, 0, 0, 0)
            l.addWidget(cb)
            t.setCellWidget(i, 0, w)
            gecmis = vp.vardiya_tahmin(k["gun"])
            it = QTableWidgetItem(f"{k['ad']}\n{k['sicilno']}" + (f" · şu an {gecmis}. vardiya" if gecmis else ""))
            t.setItem(i, 1, it)
            dc = QComboBox()
            dc.addItems(["döner", "sabit"])
            dc.setCurrentIndex(1 if donus.get(str(sid)) == "sabit" else 0)
            dc.currentIndexChanged.connect(lambda ix, s=sid: self._donus_yaz(s, "sabit" if ix == 1 else "doner"))
            t.setCellWidget(i, 2, dc)
            vc = QComboBox()
            vc.addItems(["değiştirme", vp.VARDIYA_AD[1], vp.VARDIYA_AD[2], vp.VARDIYA_AD[3]])
            vc.setCurrentIndex(self.secim.get(sid) or 0)
            vc.currentIndexChanged.connect(lambda ix, s=sid: self._secim(s, ix or None))
            t.setCellWidget(i, 3, vc)
            self._gunleri_ciz(i)
        t.resizeRowsToContents()

    def _gunleri_ciz(self, i: int):
        k = self.kisiler[i]
        sid = k["sicilid"]
        h = vp.hedef(self.secim.get(sid), k["gun"], self.elle.get(sid, {}))
        for j in range(7):
            yeni, eski = h[j], k["gun"][j]
            it = QTableWidgetItem(yeni or "-")
            it.setTextAlignment(Qt.AlignCenter)
            tatil = yeni.startswith("Hafta Tatili")
            it.setBackground(QColor(RENK_TATIL if tatil else RENK.get(yeni, "#F1F2F6")))
            it.setForeground(QColor("white" if tatil else "#1f2433"))
            s = self.sonuc.get((sid, j))
            ipucu = f"personel sisteminde: {eski or '-'}"
            if s == "ok":
                it.setBackground(QColor("#D9F2CF"))
                it.setForeground(QColor(YESIL))
                ipucu += " · kayıtlı (doğrulandı)"
            elif s == "hata":
                it.setBackground(QColor("#F9D6D5"))
                it.setForeground(QColor(KIRMIZI))
                ipucu += " · KAYDEDİLEMEDİ"
            elif yeni != eski:
                f = it.font()
                f.setBold(True)
                it.setFont(f)
                it.setBackground(QColor("#FFC999"))
                it.setForeground(QColor("#9a4300"))
                ipucu += f" → {yeni} (gönderilince değişecek)"
            it.setToolTip(ipucu)
            self.tablo.setItem(i, 4 + j, it)

    def _secim(self, sid: int, v: Optional[int]):
        self.secim[sid] = v
        for (s, j) in list(self.sonuc):
            if s == sid:
                del self.sonuc[(s, j)]
        i = next(n for n, k in enumerate(self.kisiler) if k["sicilid"] == sid)
        self._gunleri_ciz(i)

    def _hucre_tik(self, r: int, c: int):
        if c < 4 or r >= len(self.kisiler):
            return
        sid, j = self.kisiler[r]["sicilid"], c - 4
        m = QMenu(self)
        for ad in vp.SECILEBILIR:
            m.addAction(ad).setData(ad)
        m.addSeparator()
        m.addAction("Kurala döndür (elle değişikliği kaldır)").setData("")
        a = m.exec(self.tablo.viewport().mapToGlobal(self.tablo.visualItemRect(self.tablo.item(r, c)).bottomLeft()))
        if a is None:
            return
        d = self.elle.setdefault(sid, {})
        if a.data():
            d[j] = a.data()
        else:
            d.pop(j, None)
        self.sonuc.pop((sid, j), None)
        self._gunleri_ciz(r)

    # ------------------------------------------------------------------ gönderme
    def _isaretli(self) -> List[int]:
        out = []
        for i in range(self.tablo.rowCount()):
            w = self.tablo.cellWidget(i, 0)
            cb = w.findChild(QCheckBox) if w else None
            if cb is not None and cb.isChecked():
                out.append(int(cb.property("sid")))
        return out

    def _gonder_sor(self):
        isaret = self._isaretli()
        if not isaret:
            self.durum.setText("Göndermek için önce kişilerin satırını işaretleyin (✓).")
            return
        isler = []
        for k in self.kisiler:
            if k["sicilid"] in isaret:
                for g, e, y in vp.degisiklikler(self.pzt, k, self.secim.get(k["sicilid"]), self.elle.get(k["sicilid"], {})):
                    if y not in vp.MESAI:
                        continue
                    isler.append({"sid": k["sicilid"], "ad": k["ad"], "gun": g, "eski": e, "yeni": y})
        if not isler:
            self.durum.setText("İşaretli kişilerde değişecek gün yok.")
            return
        d = QDialog(self)
        d.setWindowTitle("Personel sistemine gönderilecek")
        l = QVBoxLayout(d)
        kisi = len({x["sid"] for x in isler})
        l.addWidget(QLabel(f"<b>{kisi} kişi · {len(isler)} gün</b> · hafta {self.pzt:%d.%m.%Y} – {self.pzt + timedelta(days=6):%d.%m.%Y}"))
        t = QTableWidget(len(isler), 5)
        t.setHorizontalHeaderLabels(["✓", "Personel", "Gün", "Şu anki", "Yeni"])
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for i, x in enumerate(isler):
            c = QTableWidgetItem()
            c.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            c.setCheckState(Qt.Checked)
            t.setItem(i, 0, c)
            t.setItem(i, 1, QTableWidgetItem(x["ad"]))
            t.setItem(i, 2, QTableWidgetItem(f"{vp.GUN_AD[x['gun'].weekday()]} {x['gun']:%d.%m}"))
            e = QTableWidgetItem(x["eski"] or "-")
            e.setForeground(QColor("#8a90a2"))
            t.setItem(i, 3, e)
            y = QTableWidgetItem(x["yeni"])
            y.setForeground(QColor(TURUNCU))
            t.setItem(i, 4, y)
        t.setMinimumSize(620, min(420, 60 + 30 * len(isler)))
        l.addWidget(t)
        l.addWidget(etiket("Gönderdikten sonra hafta personel sisteminden yeniden okunur ve her gün kontrol edilir. Eski hali kaydedilir; "
                           "\"Son gönderimi geri al\" ile eski haline döner."))
        bl = QHBoxLayout()
        bl.addStretch(1)
        v = QPushButton("Vazgeç")
        g = QPushButton(f"Gönder ({len(isler)} gün)")
        g.setObjectName("Birincil")
        v.clicked.connect(d.reject)
        g.clicked.connect(d.accept)
        bl.addWidget(v)
        bl.addWidget(g)
        l.addLayout(bl)
        if d.exec() != QDialog.Accepted:
            return
        secili = [x for i, x in enumerate(isler) if t.item(i, 0).checkState() == Qt.Checked]
        if secili:
            self._gonder(secili, "gonderim")

    def _gonder(self, isler: List[dict], tur: str):
        w = self._pencere_gerek()
        if w is None:
            return
        kul = (getattr(self.ana, "kullanici", None) or {}).get("ad", "")
        self._mesgul(True)

        def bitti(sonuc, yeni, ozet):
            self._mesgul(False, ozet)
            self.sonuc.update(sonuc)
            if yeni:
                d = {k["sicilid"]: k for k in yeni}
                for k in self.kisiler:
                    if k["sicilid"] in d:
                        k["gun"] = d[k["sicilid"]]["gun"]
            for i in range(len(self.kisiler)):
                self._gunleri_ciz(i)
        pi.gonder(w, self._con(), self.pzt, isler, kul + " (program)", self.durum.setText, bitti, geri=(tur == "geri"))

    def _geri_al(self):
        isler, atla, parti = pi.geri_al_isleri(self._con(), self.pzt)
        if not parti:
            self.durum.setText("Geri alınacak gönderim yok.")
            return
        if not isler:
            self.durum.setText("Son gönderim bu haftaya ait değil ya da geri alınacak gün yok (önce o haftaya gidin).")
            return
        metin = f"Son gönderim ({parti[6:8]}.{parti[4:6]} {parti[8:10]}:{parti[10:12]}) geri alınsın mı? {len(isler)} gün eski haline döner."
        if atla:
            metin += f"\n\n{len(atla)} günün eski hali programın tanımadığı bir mesai ({', '.join(sorted({x['yeni'] for x in atla}))}); onları elle düzeltin."
        if QMessageBox.question(self, "Geri al", metin) == QMessageBox.Yes:
            self._gonder(isler, "geri")
