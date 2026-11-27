"""Vardiya Planla: mavi yaka personelin haftalık vardiyasını hazırlayıp personel sistemine yazar.

Yetki: "plan" (Ayarlar > Kullanıcılar; yönetici her zaman görür). Yalnızca programda, web'de yok.
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

from . import vardiya_plan as vp
from .sayfa_ortak import etiket, kart

RENK = {"24:00-08:00": "#E3E0F5", "08:00-16:00": "#DDEBFA", "(CUMA) 08:00-16:00": "#CFE2F8", "16:00-24:00": "#FBE8D3"}
RENK_TATIL = "#5f6f86"
YESIL, KIRMIZI, TURUNCU = "#3e9b2a", "#d64541", "#e0702a"
SEMA = """CREATE TABLE IF NOT EXISTS plan_gecmis (id INTEGER PRIMARY KEY AUTOINCREMENT, parti TEXT NOT NULL, zaman TEXT NOT NULL,
    kullanici TEXT, sicilid INTEGER NOT NULL, ad TEXT, gun TEXT NOT NULL, eski TEXT, yeni TEXT, sonuc TEXT)"""


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
        c.execute(SEMA)
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
        from . import personel_pencere as pp
        for w in pp.acik_pencereler():
            if not w.otomatik:
                return w
        return None

    def _pencere_gerek(self) -> Optional[object]:
        w = self._pencere()
        if w is None:
            if QMessageBox.question(self, "Personel Veri penceresi", "Personel sistemine bağlanmak için Personel Veri penceresi açık ve "
                                    "giriş yapılmış olmalı.\n\nŞimdi açılsın mı? (Açılınca giriş yapıp burada yeniden deneyin.)") == QMessageBox.Yes:
                from . import personel_pencere as pp
                self._pv = pp.ac(self.ana.db_yolu, self)
        return w

    def _beyazlar(self) -> set:
        try:
            return {r[0] for r in self.ana.con.execute("SELECT sicilid FROM pv_personel WHERE upper(coalesce(yaka,'')) LIKE '%BEYAZ%'")}
        except Exception:  # noqa: BLE001
            return set()

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
        cagri = f"window.__vpPlanOku ? window.__vpPlanOku(@ID, {json.dumps(_gun_api(pzt))}, {json.dumps(_gun_api(pzt + timedelta(days=6)))}) : ''"

        def gelen(durum, metin):
            try:
                d = json.loads(metin) if durum == 200 else None
            except ValueError:
                d = None
            if not isinstance(d, list) or (d and isinstance(d[0], dict) and d[0].get("sunucucevap") == "basarisiz"):
                bitince(None, f"okunamadı ({durum}: {str(metin)[:120]})")
                return
            bitince(d, "")
        w.plan_istek(cagri, gelen)

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
            gecen = {k["sicilid"]: vp.vardiya_tahmin(k["gun"]) for k in vp.plan_satirlari(d, onceki)}
            donus = self._donus()
            n = 0
            for k in self.kisiler:
                v = gecen.get(k["sicilid"])
                if not v:
                    continue
                if dondur and donus.get(str(k["sicilid"]), "doner") == "doner":
                    v = vp.dondur(v)
                self.secim[k["sicilid"]] = v
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
        parti = datetime.now().strftime("%Y%m%d%H%M%S") + ("-geri" if tur == "geri" else "")
        kul = (getattr(self.ana, "kullanici", None) or {}).get("ad", "")
        con = self._con()
        sira = list(isler)
        hatali = []
        self._mesgul(True)

        def sonraki():
            if not sira:
                con.commit()
                self.durum.setText(f"{len(isler)} gün gönderildi{', ' + str(len(hatali)) + ' istek hata verdi' if hatali else ''}; "
                                   "personel sisteminden yeniden okunup kontrol ediliyor…")
                QTimer.singleShot(800, lambda: self._dogrula(isler, parti))
                return
            x = sira.pop(0)
            self.durum.setText(f"Gönderiliyor {len(isler) - len(sira)}/{len(isler)}: {x['ad']} {x['gun']:%d.%m} → {x['yeni']}")
            ekstra = json.dumps([{"sicilid": x["sid"], "tarih": x["gun"].isoformat()}])
            cagri = (f"window.__vpPlanYaz ? window.__vpPlanYaz(@ID, {json.dumps(_gun_api(self.pzt))}, "
                     f"{json.dumps(_gun_api(self.pzt + timedelta(days=6)))}, {vp.MESAI[x['yeni']]}, {json.dumps(ekstra)}) : ''")

            def gelen(durum, metin, x=x):
                ok = durum == 200 and "basarisiz" not in (metin or "")[:300]
                if not ok:
                    hatali.append(x)
                con.execute("INSERT INTO plan_gecmis (parti, zaman, kullanici, sicilid, ad, gun, eski, yeni, sonuc) VALUES (?,?,?,?,?,?,?,?,?)",
                            (parti, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), kul, x["sid"], x["ad"], x["gun"].isoformat(),
                             x["eski"], x["yeni"], "gonderildi" if ok else f"istek hatası {durum}"))
                QTimer.singleShot(150, sonraki)
            w.plan_istek(cagri, gelen)
        sonraki()

    def _dogrula(self, isler: List[dict], parti: str):
        def bitti(d, hata):
            self._mesgul(False)
            if d is None:
                self.durum.setText("Gönderildi ama doğrulama için okunamadı: " + hata + " · \"Personel sisteminden oku\" ile yeniden bakın.")
                return
            ham = {}
            for r in d:
                try:
                    ham[int(r.get("ysicilid"))] = r
                except (TypeError, ValueError):
                    pass
            ok = hata_ = 0
            con = self._con()
            for x in isler:
                g = x["gun"]
                deger = str((ham.get(x["sid"]) or {}).get(f"y{g.year}x{g.month:02d}x{g.day:02d}") or "")
                ilk = deger.split("<br>")[0].split(",")[0].strip()
                kayitli = bool(ilk) and not ilk.startswith("*") and vp.hucre_ad(ilk) == x["yeni"]
                j = (g - self.pzt).days
                self.sonuc[(x["sid"], j)] = "ok" if kayitli else "hata"
                ok, hata_ = ok + kayitli, hata_ + (not kayitli)
                con.execute("UPDATE plan_gecmis SET sonuc=? WHERE parti=? AND sicilid=? AND gun=?",
                            ("doğrulandı" if kayitli else f"kaydedilmedi (sistemde: {ilk or 'boş'})", parti, x["sid"], g.isoformat()))
            con.commit()
            beyaz = self._beyazlar()
            yeni = {k["sicilid"]: k for k in vp.plan_satirlari(d, self.pzt) if k["sicilid"] not in beyaz}
            for k in self.kisiler:
                if k["sicilid"] in yeni:
                    k["gun"] = yeni[k["sicilid"]]["gun"]
            for i in range(len(self.kisiler)):
                self._gunleri_ciz(i)
            self.durum.setText(f"Kontrol: {ok} gün kayıtlı (yeşil)" + (f", {hata_} gün KAYDEDİLEMEDİ (kırmızı) — o günlere tekrar bakın" if hata_ else "")
                               + f" · {datetime.now():%H:%M}")
        self._oku_hafta(self.pzt, bitti)

    def _geri_al(self):
        con = self._con()
        r = con.execute("SELECT parti FROM plan_gecmis WHERE parti NOT LIKE '%-geri' ORDER BY id DESC LIMIT 1").fetchone()
        if not r:
            self.durum.setText("Geri alınacak gönderim yok.")
            return
        satir = con.execute("SELECT sicilid, ad, gun, eski, yeni FROM plan_gecmis WHERE parti=? AND sonuc NOT LIKE 'istek hatası%'", (r[0],)).fetchall()
        isler, atla = [], []
        for sid, ad, gun, eski, yeni in satir:
            g = date.fromisoformat(gun)
            if vp.hafta_basi(g) != self.pzt:
                continue
            (isler if eski in vp.MESAI else atla).append({"sid": sid, "ad": ad, "gun": g, "eski": yeni, "yeni": eski})
        if not isler:
            self.durum.setText("Son gönderim bu haftaya ait değil ya da geri alınacak gün yok (önce o haftaya gidin).")
            return
        metin = f"Son gönderim ({r[0][6:8]}.{r[0][4:6]} {r[0][8:10]}:{r[0][10:12]}) geri alınsın mı? {len(isler)} gün eski haline döner."
        if atla:
            metin += f"\n\n{len(atla)} günün eski hali programın tanımadığı bir mesai ({', '.join(sorted({x['yeni'] for x in atla}))}); onları elle düzeltin."
        if QMessageBox.question(self, "Geri al", metin) == QMessageBox.Yes:
            self._gonder(isler, "geri")
