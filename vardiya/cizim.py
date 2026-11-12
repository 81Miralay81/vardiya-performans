"""Grafik, tablo ve A3 rapor çizimi. Hepsi QPainter ile; ekranda, panoda ve PDF'de aynı kod kullanılır."""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QLinearGradient, QPainter, QPen, QPixmap

from . import tema
from .hesap import DonemSonuc, VARDIYALAR
from .tema import font, renk, yuzde

AL = Qt.AlignLeft | Qt.AlignVCenter
ORTA = Qt.AlignCenter
SAG = Qt.AlignRight | Qt.AlignVCenter


def olcek(rect: QRectF, ref_w: float = 900.0, ref_h: float = 420.0) -> float:
    return max(0.85, min(3.5, min(rect.width() / ref_w, rect.height() / ref_h * 1.5)))


def _yaz(p: QPainter, rect: QRectF, metin: str, px: float, kalin=False, hiza=ORTA, renk_=tema.YAZI):
    p.setFont(font(px, kalin))
    p.setPen(QColor(renk_))
    p.drawText(rect, int(hiza), metin)


def _yaz_sigdir(p: QPainter, rect: QRectF, metin: str, px: float, kalin=False, hiza=ORTA, renk_=tema.YAZI, min_px: float = 12):
    """Metin kutuya sığmıyorsa yazı tipini küçültür."""
    from PySide6.QtGui import QFontMetrics
    boyut = px
    while boyut > min_px and QFontMetrics(font(boyut, kalin)).horizontalAdvance(metin) > rect.width():
        boyut -= 1
    _yaz(p, rect, metin, boyut, kalin, hiza, renk_)


def _nice_max(v: float) -> float:
    for adim in (0.1, 0.2, 0.25, 0.5, 1.0):
        pass
    tavan = max(v * 1.18, 0.1)
    import math
    mag = 10 ** math.floor(math.log10(tavan))
    for m in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if m * mag >= tavan:
            return m * mag
    return tavan


def _deger_listesi(sonuc: DonemSonuc, secim: int, makineler: List[str], bos_goster: bool):
    sirali = [m for m in makineler if m in sonuc.makine_ort]
    sirali += sorted(m for m in sonuc.makine_ort if m not in makineler)
    cikti = []
    for m in (makineler if bos_goster else sirali):
        v = sonuc.makine_ort.get(m, (None, None, None))[secim]
        if v is not None or bos_goster:
            cikti.append((m, v))
    if not bos_goster:
        cikti += [(m, sonuc.makine_ort[m][secim]) for m in sirali if m not in makineler and (m, sonuc.makine_ort[m][secim]) not in cikti]
    return cikti


# ============================================================ makine bazlı grafik
def makine_grafigi(p: QPainter, rect: QRectF, sonuc: DonemSonuc, makineler: List[str], secim: int = 0,
                   baslik: Optional[str] = None, bos_goster: bool = False, arka: bool = True):
    s = olcek(rect)
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    if arka:
        p.fillRect(rect, QColor("white"))
    ad = tema.METRIKLER[secim]
    baslik = baslik if baslik is not None else f"Makine Bazlı {ad} Oranı"
    sol, sag, ust, alt = 56 * s, 78 * s, (44 if baslik else 18) * s, 54 * s
    if baslik:
        _yaz(p, QRectF(rect.left(), rect.top() + 6 * s, rect.width(), 30 * s), baslik, 19 * s, True, ORTA, tema.LACIVERT)
    veri = _deger_listesi(sonuc, secim, makineler, bos_goster)
    alan = QRectF(rect.left() + sol, rect.top() + ust, rect.width() - sol - sag, rect.height() - ust - alt)
    if not veri:
        _yaz(p, rect, "Seçilen dönemde gösterilecek veri yok", 16 * s, False, ORTA, tema.YAZI_SOLUK)
        p.restore()
        return
    genel = sonuc.genel[secim]
    deger_max = max([v or 0 for _, v in veri] + [genel or 0])
    ymax = 1.1 if secim == 0 else _nice_max(deger_max)
    adim = 0.1 if ymax <= 1.15 else (0.1 if ymax <= 0.6 else 0.2)
    if secim != 0:
        adim = ymax / 5
    # ızgara ve eksen
    k = 0.0
    while k <= ymax + 1e-9:
        y = alan.bottom() - alan.height() * k / ymax
        p.setPen(QPen(QColor("#E3E7EF"), max(1, s)))
        p.drawLine(QPointF(alan.left(), y), QPointF(alan.right(), y))
        _yaz(p, QRectF(rect.left(), y - 10 * s, sol - 8 * s, 20 * s), f"{k * 100:.0f}%", 11 * s, False, SAG, tema.YAZI_SOLUK)
        k += adim
    n = len(veri)
    slot = alan.width() / n
    genislik = min(slot * 0.62, 46 * s)
    dondur = slot < 40 * s
    for i, (m, v) in enumerate(veri):
        cx = alan.left() + slot * (i + 0.5)
        if v is not None:
            h = alan.height() * min(v, ymax) / ymax
            br = QRectF(cx - genislik / 2, alan.bottom() - h, genislik, h)
            g = QLinearGradient(br.topLeft(), br.bottomLeft())
            ana = QColor(tema.METRIK_RENK[secim])
            g.setColorAt(0, ana.lighter(150))
            g.setColorAt(1, ana)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(g))
            p.drawRoundedRect(br, 2 * s, 2 * s) if h > 4 * s else p.drawRect(br)
            _yaz(p, QRectF(cx - slot / 2, br.top() - 20 * s, slot, 18 * s), yuzde(v, 0), (11 if not dondur else 10) * s, True, ORTA, tema.YAZI)
        # makine adı
        if dondur:
            p.save()
            p.translate(cx + 4 * s, alan.bottom() + 8 * s)
            p.rotate(60)
            _yaz(p, QRectF(0, -8 * s, 60 * s, 16 * s), m, 11 * s, False, AL, tema.YAZI)
            p.restore()
        else:
            _yaz(p, QRectF(cx - slot / 2, alan.bottom() + 6 * s, slot, 20 * s), m, 12 * s, True, ORTA, tema.YAZI)
    p.setPen(QPen(QColor("#9AA3B8"), max(1, s)))
    p.drawLine(alan.bottomLeft(), alan.bottomRight())
    # genel ortalama çizgisi
    if genel is not None:
        y = alan.bottom() - alan.height() * min(genel, ymax) / ymax
        pen = QPen(QColor(tema.TURUNCU), 2.4 * s)
        p.setPen(pen)
        p.drawLine(QPointF(alan.left(), y), QPointF(alan.right(), y))
        _yaz(p, QRectF(alan.right() + 4 * s, y - 20 * s, sag - 4 * s, 40 * s), f"Genel\n{yuzde(genel)}", 11 * s, True, AL, tema.TURUNCU)
    p.restore()


# ============================================================ vardiya bazlı grafik
def vardiya_grafigi(p: QPainter, rect: QRectF, sonuc: DonemSonuc, seflar: Dict[int, str], secim: int = 0,
                    baslik: Optional[str] = None, arka: bool = True):
    s = olcek(rect, 600, 420)
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    if arka:
        p.fillRect(rect, QColor("white"))
    ad = tema.METRIKLER[secim]
    baslik = baslik if baslik is not None else f"Vardiya Bazlı {ad} Oranı"
    sol, sag, ust, alt = 56 * s, 70 * s, (44 if baslik else 18) * s, 62 * s
    if baslik:
        _yaz(p, QRectF(rect.left(), rect.top() + 6 * s, rect.width(), 30 * s), baslik, 19 * s, True, ORTA, tema.LACIVERT)
    alan = QRectF(rect.left() + sol, rect.top() + ust, rect.width() - sol - sag, rect.height() - ust - alt)
    vals = [getattr(sonuc.vardiyalar[v], ("calisma", "durus", "mola")[secim]) for v in VARDIYALAR]
    genel = sonuc.genel[secim]
    tavan = max([x or 0 for x in vals] + [genel or 0])
    ymax = 1.1 if secim == 0 else _nice_max(tavan)
    adim = 0.1 if secim == 0 else ymax / 5
    k = 0.0
    while k <= ymax + 1e-9:
        y = alan.bottom() - alan.height() * k / ymax
        p.setPen(QPen(QColor("#E3E7EF"), max(1, s)))
        p.drawLine(QPointF(alan.left(), y), QPointF(alan.right(), y))
        _yaz(p, QRectF(rect.left(), y - 10 * s, sol - 8 * s, 20 * s), f"{k * 100:.0f}%", 11 * s, False, SAG, tema.YAZI_SOLUK)
        k += adim
    slot = alan.width() / 3
    gen = min(slot * 0.55, 150 * s)
    for i, v in enumerate(VARDIYALAR):
        cx = alan.left() + slot * (i + 0.5)
        deger = vals[i]
        if deger is not None:
            h = alan.height() * min(deger, ymax) / ymax
            br = QRectF(cx - gen / 2, alan.bottom() - h, gen, h)
            g = QLinearGradient(br.topLeft(), br.bottomLeft())
            ana = QColor(tema.METRIK_RENK[secim])
            g.setColorAt(0, ana.lighter(155))
            g.setColorAt(1, ana)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(g))
            p.drawRoundedRect(br, 3 * s, 3 * s)
            _yaz(p, QRectF(cx - slot / 2, br.top() - 26 * s, slot, 24 * s), yuzde(deger), 16 * s, True, ORTA, tema.YAZI)
            _yaz(p, br.adjusted(0, 0, 0, 0), f"{sonuc.vardiyalar[v].gun_sayisi} gün", 11 * s, False, Qt.AlignHCenter | Qt.AlignBottom,
                 "#FFFFFF")
        else:
            _yaz(p, QRectF(cx - slot / 2, alan.bottom() - 40 * s, slot, 24 * s), "veri yok", 13 * s, False, ORTA, tema.YAZI_SOLUK)
        etiket = f"{v}.VARDİYA"
        _yaz(p, QRectF(cx - slot / 2, alan.bottom() + 6 * s, slot, 22 * s), etiket, 13 * s, True, ORTA, tema.YAZI)
        sef = seflar.get(v, "")
        if sef:
            _yaz(p, QRectF(cx - slot / 2, alan.bottom() + 28 * s, slot, 22 * s), tema.tr_buyuk(sef), 13 * s, True, ORTA, tema.YESIL)
    p.setPen(QPen(QColor("#9AA3B8"), max(1, s)))
    p.drawLine(alan.bottomLeft(), alan.bottomRight())
    if genel is not None:
        y = alan.bottom() - alan.height() * min(genel, ymax) / ymax
        p.setPen(QPen(QColor(tema.TURUNCU), 2.6 * s))
        p.drawLine(QPointF(alan.left(), y), QPointF(alan.right(), y))
        _yaz(p, QRectF(alan.right() + 4 * s, y - 22 * s, sag - 4 * s, 44 * s), f"Genel\n{yuzde(genel)}", 12 * s, True, AL, tema.TURUNCU)
    p.restore()


# ============================================================ Excel görünümlü tablo
def tablo_yukseklik_orani(satir_sayisi: int) -> float:
    return (satir_sayisi + 4) / 4.4


def tablo_ciz(p: QPainter, rect: QRectF, sonuc: DonemSonuc, makineler: List[str], secim: int = 0, yazi_carpani: float = 1.0):
    """Excel'deki U2:Y35 tablosunun aynısı (çalışma günü, makine sayıları, ortalamalar, makine satırları)."""
    tum = list(makineler) + sorted(m for m in sonuc.hucreler if m not in makineler)
    satir_n = len(tum) + 4
    sh = rect.height() / satir_n
    s = max(0.5, min(sh / 24.0, rect.width() / 345.0))
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    w1, w2 = rect.width() * 0.22, rect.width() * 0.2
    w3 = (rect.width() - w1 - w2) / 3
    xs = [rect.left(), rect.left() + w1, rect.left() + w1 + w2]
    xs += [xs[2] + w3, xs[2] + 2 * w3, rect.right()]

    def hucre(c0, c1, r0, r1, dolgu, metin, px=12, kalin=False, yazi=tema.YAZI, hiza=ORTA):
        r = QRectF(xs[c0], rect.top() + sh * r0, xs[c1] - xs[c0], sh * (r1 - r0))
        p.setPen(QPen(QColor("#FFFFFF"), max(0.8, s * 1.2)))
        p.setBrush(QColor(dolgu))
        p.drawRect(r)
        if metin:
            _yaz_sigdir(p, r.adjusted(4 * s, 0, -4 * s, 0), metin, px * s * yazi_carpani, kalin, hiza, yazi, min_px=6)

    gun = sonuc.hesap_gunu()
    hucre(0, 2, 0, 2, tema.XL_SEFTALI, f"Çalışma Gün    {gun}", 14, True, "#FFFFFF")
    hucre(2, 5, 0, 1, "#000000", "TOPLAM MAKİNE SAYISI", 12, True, "#FFFFFF")
    for i, v in enumerate(VARDIYALAR):
        ms = sonuc.vardiyalar[v].makine_sayisi
        hucre(2 + i, 3 + i, 1, 2, "#000000", str(tema.yuvarla(ms)) if ms is not None else "-", 16, True, "#FFFFFF")
    hucre(0, 2, 2, 3, tema.XL_KIRMIZI, "Makine Adı  ORTALAMA", 10.5, True, "#FFFFFF")
    for i, v in enumerate(VARDIYALAR):
        hucre(2 + i, 3 + i, 2, 3, tema.XL_SARI, f"{v}.Vardiya", 10.5, True)
    # genel ortalama satırı
    hucre(0, 1, 3, 4, tema.XL_TURUNCU, "Gnl Ortlma", 11)
    genel = sonuc.genel[secim]
    hucre(1, 2, 3, 4, tema.XL_TURUNCU if genel is not None else tema.XL_GRI, yuzde(genel, 0) if genel is not None else "", 11, False, hiza=SAG)
    for i, v in enumerate(VARDIYALAR):
        d = getattr(sonuc.vardiyalar[v], ("calisma", "durus", "mola")[secim])
        hucre(2 + i, 3 + i, 3, 4, tema.XL_YESIL if d is not None else tema.XL_GRI, yuzde(d) if d is not None else "", 11, True)
    # makine satırları
    for r, m in enumerate(tum):
        row = 4 + r
        ort = sonuc.makine_ort.get(m, (None, None, None))[secim]
        dolu = ort is not None
        hucre(0, 1, row, row + 1, tema.XL_YESIL if dolu else tema.XL_GRI, m, 11, False, hiza=AL)
        hucre(1, 2, row, row + 1, tema.XL_YESIL if dolu else tema.XL_GRI, yuzde(ort, 0) if dolu else "", 11, False, hiza=SAG)
        for i, v in enumerate(VARDIYALAR):
            h = sonuc.hucreler.get(m, {}).get(v)
            deg = h[secim] if h else None
            hucre(2 + i, 3 + i, row, row + 1, tema.XL_TURUNCU if deg is not None else tema.XL_GRI,
                  yuzde(deg) if deg is not None else "", 11, False, hiza=SAG)
    p.restore()


def tablo_resmi(sonuc, makineler, secim=0, genislik=660, satir=30, yazi_carpani=1.0) -> QImage:
    n = len(makineler) + 4
    yuk = int(genislik * tablo_yukseklik_orani(len(makineler)) / 1.45)
    yuk = int(n * satir)
    img = QImage(genislik, yuk, QImage.Format_ARGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    tablo_ciz(p, QRectF(0, 0, genislik, yuk), sonuc, makineler, secim, yazi_carpani)
    p.end()
    return img


# ============================================================ Cormind zaman dağılım grafiği (rapor için)
def cormind_durus_grafigi(p: QPainter, rect: QRectF, cm: Dict[str, dict], baslik: Optional[str] = "Zaman Dağılım Grafiği (Cormind)",
                          limit: float = 15.0):
    """cm: hesap.cormind_hesabi çıktısı. Her makinede duruş türleri üst üste, mola süresi (eksi ise) sıfırın altında."""
    s = olcek(rect)
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    if baslik:
        _yaz(p, QRectF(rect.left(), rect.top() + 4 * s, rect.width(), 28 * s), baslik, 19 * s, True, ORTA, tema.LACIVERT)
    makineler = list(cm)
    if not makineler:
        _yaz(p, rect, "Seçilen dönemde gösterilecek veri yok", 16 * s, False, ORTA, tema.YAZI_SOLUK)
        p.restore()
        return
    toplam: Dict[str, float] = {}
    for v in cm.values():
        for t, x in v["durus"].items():
            toplam[t] = toplam.get(t, 0.0) + x
    turler = sorted(toplam, key=lambda t: -toplam[t])
    # gösterge (altta, satır satır)
    gosterge = [(t, tema.durus_rengi(t)) for t in turler] + [("Mola Süresi", tema.MOLA_RENK)]
    p.setFont(font(11 * s))
    fm = p.fontMetrics()
    satirlar, satir, gen = [], [], 0.0
    azami = rect.width() - 40 * s
    for ad, renk_ in gosterge:
        w = fm.horizontalAdvance(ad) + 34 * s
        if satir and gen + w > azami:
            satirlar.append((satir, gen))
            satir, gen = [], 0.0
        satir.append((ad, renk_, w))
        gen += w
    if satir:
        satirlar.append((satir, gen))
    gos_h = len(satirlar) * 20 * s + 6 * s
    sol, sag, ust, alt = 56 * s, 78 * s, (40 if baslik else 16) * s, 52 * s + gos_h
    alan = QRectF(rect.left() + sol, rect.top() + ust, rect.width() - sol - sag, rect.height() - ust - alt)
    ust_yigin = max([sum(max(0.0, x) for x in v["durus"].values()) + max(0.0, v["mola"]) for v in cm.values()] + [limit + 5])
    en_alt = min([v["mola"] for v in cm.values()] + [0.0])
    import math
    ymin = math.floor(en_alt / 10.0) * 10.0
    ymax = math.ceil((ust_yigin + 6) / 10.0) * 10.0
    adim = 10.0 if (ymax - ymin) <= 80 else 20.0

    def yy(v: float) -> float:
        return alan.bottom() - alan.height() * (v - ymin) / (ymax - ymin)

    k = ymin
    while k <= ymax + 1e-9:
        p.setPen(QPen(QColor("#E3E7EF"), max(1, s)))
        p.drawLine(QPointF(alan.left(), yy(k)), QPointF(alan.right(), yy(k)))
        _yaz(p, QRectF(rect.left(), yy(k) - 10 * s, sol - 8 * s, 20 * s), f"{k:.0f}%", 11 * s, False, SAG, tema.YAZI_SOLUK)
        k += adim
    n = len(makineler)
    slot = alan.width() / n
    genislik = min(slot * 0.64, 46 * s)
    dondur = slot < 40 * s

    def parca(cx, a, u, renk_, eksi=False):
        r_ = QRectF(cx - genislik / 2, yy(u), genislik, yy(a) - yy(u))
        if r_.height() < 0.4:
            return
        g = QLinearGradient(r_.topLeft(), r_.topRight())
        ana = QColor(renk_)
        g.setColorAt(0, ana.lighter(118))
        g.setColorAt(1, ana.darker(108))
        p.setPen(QPen(QColor("white"), max(0.6, 0.8 * s)))
        p.setBrush(QBrush(g))
        p.drawRect(r_)
        if r_.height() >= 15 * s and genislik >= 20 * s:
            acik = ana.lightness() > 150
            _yaz(p, r_, ("-" if eksi else "") + f"{u - a:.0f}%", 9.5 * s, True, ORTA, "#101320" if acik else "#FFFFFF")

    for i, m in enumerate(makineler):
        v = cm[m]
        cx = alan.left() + slot * (i + 0.5)
        yigin = 0.0
        for t in turler:
            x = v["durus"].get(t, 0.0)
            if x > 0:
                parca(cx, yigin, yigin + x, tema.durus_rengi(t))
                yigin += x
        if v["mola"] >= 0:
            parca(cx, yigin, yigin + v["mola"], tema.MOLA_RENK)
            yigin += v["mola"]
        else:
            parca(cx, v["mola"], 0.0, tema.MOLA_RENK, eksi=True)
        _yaz(p, QRectF(cx - slot / 2, yy(yigin) - 18 * s, slot, 16 * s), f"{v['toplam']:.0f}%", (10.5 if not dondur else 9.5) * s, True, ORTA, tema.YAZI)
        if dondur:
            p.save()
            p.translate(cx + 4 * s, alan.bottom() + 8 * s)
            p.rotate(60)
            _yaz(p, QRectF(0, -8 * s, 60 * s, 16 * s), m, 11 * s, False, AL, tema.YAZI)
            p.restore()
        else:
            _yaz(p, QRectF(cx - slot / 2, alan.bottom() + 6 * s, slot, 20 * s), m, 12 * s, True, ORTA, tema.YAZI)
    p.setPen(QPen(QColor("#9AA3B8"), max(1, 1.4 * s)))
    p.drawLine(QPointF(alan.left(), yy(0)), QPointF(alan.right(), yy(0)))
    p.setPen(QPen(QColor(tema.YESIL), 2.4 * s))
    p.drawLine(QPointF(alan.left(), yy(limit)), QPointF(alan.right(), yy(limit)))
    _yaz(p, QRectF(alan.right() + 4 * s, yy(limit) - 20 * s, sag - 4 * s, 40 * s), f"Limit\n%{limit:.0f}", 11 * s, True, AL, tema.YESIL)
    # gösterge
    gy = rect.bottom() - gos_h + 2 * s
    for satir, gen in satirlar:
        gx = rect.center().x() - gen / 2
        for ad, renk_, w in satir:
            p.fillRect(QRectF(gx, gy + 4 * s, 12 * s, 10 * s), QColor(renk_))
            _yaz(p, QRectF(gx + 17 * s, gy, w, 18 * s), ad, 11 * s, False, AL, tema.YAZI)
            gx += w
        gy += 20 * s
    p.restore()


# ============================================================ özet tablosu (vardiya raporunda)
def ozet_tablo(p: QPainter, rect: QRectF, sonuc: DonemSonuc, seflar: Dict[int, str]):
    s = olcek(rect, 600, 150)
    p.save()
    p.setRenderHint(QPainter.TextAntialiasing, True)
    basliklar = ["Vardiya", "Grup Lideri", "Makine", "Çalışma", "Duruş", "Mola", "Gün"]
    oran = [1.1, 1.5, 0.9, 1.1, 1.1, 1.1, 0.8]
    top = sum(oran)
    sat = rect.height() / 5
    xs = [rect.left()]
    for o in oran:
        xs.append(xs[-1] + rect.width() * o / top)

    def satir(i, hucreler, dolgu, yazi, kalin=False):
        for j, t in enumerate(hucreler):
            r = QRectF(xs[j], rect.top() + sat * i, xs[j + 1] - xs[j], sat)
            p.setPen(QPen(QColor("#FFFFFF"), max(1, s)))
            p.setBrush(QColor(dolgu))
            p.drawRect(r)
            _yaz(p, r.adjusted(6 * s, 0, -6 * s, 0), t, 12.5 * s, kalin, AL if j < 2 else ORTA, yazi)

    satir(0, basliklar, tema.LACIVERT, "#FFFFFF", True)
    for i, v in enumerate(VARDIYALAR, start=1):
        oz = sonuc.vardiyalar[v]
        ms = tema.sayi(oz.makine_sayisi) if oz.makine_sayisi is not None else "-"
        satir(i, [f"{v}.Vardiya", seflar.get(v, ""), ms, yuzde(oz.calisma), yuzde(oz.durus), yuzde(oz.mola), str(oz.gun_sayisi)],
              "#F4F6FB" if i % 2 else "#FFFFFF", tema.YAZI, False)
    g = sonuc.genel
    satir(4, ["Genel", "", "", yuzde(g[0]), yuzde(g[1]), yuzde(g[2]), ""], "#E6F0D8", tema.YAZI, True)
    p.restore()


# ============================================================ A3 rapor sayfası
def rapor_ciz(p: QPainter, rect: QRectF, r: dict):
    """r: baslik, donem (metin), duzen ('makine'|'vardiya'), sonuc, makineler, seflar, gorsel (QImage|None),
    bos_goster, esik, net_saat, yer_tutucu (bool: ekranda boş alanı göster)"""
    p.save()
    p.fillRect(rect, QColor("white"))
    W, H = rect.width(), rect.height()
    k = W / 1600.0
    kenar = 36 * k
    ic = rect.adjusted(kenar, kenar, -kenar, -kenar)
    # başlık bandı
    lg = tema.logo()
    ust_h = 96 * k
    if not lg.isNull():
        lh = 70 * k
        lw = lh * lg.width() / lg.height()
        p.drawPixmap(QRectF(ic.left(), ic.top() + 6 * k, lw, lh), lg, QRectF(lg.rect()))
    _yaz_sigdir(p, QRectF(ic.left() + 330 * k, ic.top(), ic.width() - 400 * k, 56 * k), r["baslik"], 30 * k, True, ORTA, tema.LACIVERT, 14 * k)
    _yaz(p, QRectF(ic.left() + 330 * k, ic.top() + 50 * k, ic.width() - 400 * k, 34 * k), r["donem"], 18 * k, False, ORTA, tema.YAZI_SOLUK)
    p.setPen(QPen(QColor(tema.YESIL), 4 * k))
    p.drawLine(QPointF(ic.left(), ic.top() + ust_h), QPointF(ic.right(), ic.top() + ust_h))
    govde = QRectF(ic.left(), ic.top() + ust_h + 18 * k, ic.width(), ic.height() - ust_h - 18 * k - 50 * k)
    sonuc, makineler = r["sonuc"], r["makineler"]
    if r["duzen"] == "makine":
        ust_yuk = govde.height() * 0.42
        cerceve = QRectF(govde.left(), govde.top(), govde.width(), ust_yuk)
        makine_grafigi(p, cerceve, sonuc, makineler, 0, "Makine Bazlı Performans (Çalışma) Oranı", r.get("bos_goster", False), arka=False)
        alt = QRectF(govde.left(), govde.top() + ust_yuk + 14 * k, govde.width(), govde.height() - ust_yuk - 14 * k)
        gorsel = r.get("gorsel")
        if gorsel is not None and not gorsel.isNull():
            oran = min(alt.width() / gorsel.width(), alt.height() / gorsel.height())
            w, h = gorsel.width() * oran, gorsel.height() * oran
            p.drawImage(QRectF(alt.center().x() - w / 2, alt.top(), w, h), gorsel)
        elif r.get("cormind"):
            cormind_durus_grafigi(p, alt, r["cormind"])
        elif r.get("yer_tutucu"):
            p.setPen(QPen(QColor("#B8BFD0"), 2 * k, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(alt.adjusted(2, 2, -2, -2), 10 * k, 10 * k)
            _yaz(p, alt, "Cormind 'Zaman Dağılım Grafiği' görüntüsü buraya yapıştırılır", 20 * k, False, ORTA, "#9AA3B8")
    else:
        sol = QRectF(govde.left(), govde.top(), govde.width() * 0.60, govde.height())
        sag = QRectF(sol.right() + 30 * k, govde.top(), govde.width() - sol.width() - 30 * k, govde.height())
        grafik_h = sol.height() * 0.66
        vardiya_grafigi(p, QRectF(sol.left(), sol.top(), sol.width(), grafik_h), sonuc, r["seflar"], 0,
                        "Vardiya Bazlı Performans (Çalışma) Oranı", arka=False)
        ozet_tablo(p, QRectF(sol.left(), sol.top() + grafik_h + 24 * k, sol.width(), sol.height() - grafik_h - 24 * k), sonuc, r["seflar"])
        tablo_ciz(p, sag, sonuc, makineler, 0)
    # alt bilgi
    notlar = []
    notlar.append(f"Eşik: %{r['esik'] * 100:.0f}  ·  Net vardiya süresi: {tema.sayi(r['net_saat'], 2)} saat")
    if sonuc.verisiz_gunler:
        notlar.append("Kaydı olmayan gün: " + ", ".join(d.strftime("%d.%m") for d in sonuc.verisiz_gunler))
    eksik = [f"{d.strftime('%d.%m')} {v}.v" for d, v in sonuc.bos_vardiyalar]
    if eksik and len(eksik) <= 6:
        notlar.append("Ortalamaya girmeyen vardiya: " + ", ".join(eksik))
    _yaz(p, QRectF(ic.left(), ic.bottom() - 40 * k, ic.width() * 0.8, 36 * k), "  |  ".join(notlar), 13 * k, False, AL, tema.YAZI_SOLUK)
    _yaz(p, QRectF(ic.right() - 520 * k, ic.bottom() - 40 * k, 520 * k, 36 * k), r.get("alt_sag", ""), 13 * k, False, SAG, tema.YAZI_SOLUK)
    p.restore()


# ============================================================ idari rapor
def cormind_oee_grafigi(p: QPainter, rect: QRectF, cm: Dict[str, dict], baslik: Optional[str] = "OEE Grafiği (Cormind)", limit: float = 85.0):
    s = olcek(rect)
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    if baslik:
        _yaz(p, QRectF(rect.left(), rect.top() + 4 * s, rect.width(), 28 * s), baslik, 19 * s, True, ORTA, tema.LACIVERT)
    makineler = list(cm)
    if not makineler:
        _yaz(p, rect, "Seçilen dönemde gösterilecek veri yok", 16 * s, False, ORTA, tema.YAZI_SOLUK)
        p.restore()
        return
    sol, sag, ust, alt = 56 * s, 78 * s, (44 if baslik else 18) * s, 54 * s
    alan = QRectF(rect.left() + sol, rect.top() + ust, rect.width() - sol - sag, rect.height() - ust - alt)
    ymax = 110.0
    for k in range(0, 111, 10):
        y = alan.bottom() - alan.height() * k / ymax
        p.setPen(QPen(QColor("#E3E7EF"), max(1, s)))
        p.drawLine(QPointF(alan.left(), y), QPointF(alan.right(), y))
        _yaz(p, QRectF(rect.left(), y - 10 * s, sol - 8 * s, 20 * s), f"{k}%", 11 * s, False, SAG, tema.YAZI_SOLUK)
    slot = alan.width() / len(makineler)
    genislik = min(slot * 0.62, 46 * s)
    dondur = slot < 40 * s
    for i, m in enumerate(makineler):
        v = cm[m]["oee"]
        cx = alan.left() + slot * (i + 0.5)
        h = alan.height() * v / ymax
        br = QRectF(cx - genislik / 2, alan.bottom() - h, genislik, h)
        if h > 0.5:
            g = QLinearGradient(br.topLeft(), br.bottomLeft())
            ana = QColor("#16695F")
            g.setColorAt(0, ana.lighter(140))
            g.setColorAt(1, ana)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(g))
            p.drawRoundedRect(br, 2 * s, 2 * s) if h > 4 * s else p.drawRect(br)
        _yaz(p, QRectF(cx - slot / 2, br.top() - 20 * s, slot, 18 * s), f"{v:.0f}%", (11 if not dondur else 9.5) * s, True, ORTA, tema.YAZI)
        if dondur:
            p.save()
            p.translate(cx + 4 * s, alan.bottom() + 8 * s)
            p.rotate(60)
            _yaz(p, QRectF(0, -8 * s, 60 * s, 16 * s), m, 11 * s, False, AL, tema.YAZI)
            p.restore()
        else:
            _yaz(p, QRectF(cx - slot / 2, alan.bottom() + 6 * s, slot, 20 * s), m, 12 * s, True, ORTA, tema.YAZI)
    p.setPen(QPen(QColor("#9AA3B8"), max(1, s)))
    p.drawLine(alan.bottomLeft(), alan.bottomRight())
    y = alan.bottom() - alan.height() * limit / ymax
    p.setPen(QPen(QColor("#E0B400"), 2.4 * s))
    p.drawLine(QPointF(alan.left(), y), QPointF(alan.right(), y))
    _yaz(p, QRectF(alan.right() + 4 * s, y - 20 * s, sag - 4 * s, 40 * s), f"Limit\n%{limit:.0f}", 11 * s, True, AL, "#B08D00")
    p.restore()


def genel_performans_grafigi(p: QPainter, rect: QRectF, sonuc: DonemSonuc, makineler: List[str], mola_pay: float,
                             baslik: Optional[str] = "Genel Performans: Çalışma, Duruş ve Mola",
                             bolgeler: Optional[list] = None, secili: Optional[str] = None):
    # bolgeler verilirse her sütunun tıklanabilir alanları eklenir: (QRectF, makine, "durus" | "mola")
    """Bizim hesabımız: her sütun %100 (yeşil çalışma + kırmızı duruş); sıfırın altında mola hakkı
    (turuncu: mola yapılan, mor: molada çalışılan). Eşik altı makineler soluk çizilir ve hesaba girmez."""
    s = olcek(rect)
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    if baslik:
        _yaz(p, QRectF(rect.left(), rect.top() + 4 * s, rect.width(), 28 * s), baslik, 19 * s, True, ORTA, tema.LACIVERT)
    sirali = list(makineler) + sorted(m for m in sonuc.hucreler if m not in makineler)
    veri = []
    for m in sirali:
        ort = sonuc.makine_ort.get(m)
        if ort and ort[0] is not None:
            veri.append((m, max(0.0, min(1.0, ort[0])), max(0.0, min(1.0, ort[2] or 0.0)), False))
        elif m in sonuc.esik_alti:
            e = sonuc.esik_alti[m]
            veri.append((m, max(0.0, min(1.0, e[0])), max(0.0, min(1.0, e[2])), True))
    gos_h = 24 * s
    sol, sag, ust, alt = 56 * s, 78 * s, (44 if baslik else 18) * s, 34 * s + gos_h
    alan = QRectF(rect.left() + sol, rect.top() + ust, rect.width() - sol - sag, rect.height() - ust - alt)
    if not veri:
        _yaz(p, rect, "Seçilen dönemde gösterilecek veri yok", 16 * s, False, ORTA, tema.YAZI_SOLUK)
        p.restore()
        return
    ymin, ymax = -(mola_pay + 2.0), 108.0

    # Mola bölümü okunabilsin diye sıfırın altına grafiğin beşte biri ayrılır (yüzdeleri içine yazılır).
    alt_h = alan.height() * 0.20
    sifir_y = alan.bottom() - alt_h

    def yy(v: float) -> float:
        if v >= 0:
            return sifir_y - (sifir_y - alan.top()) * v / ymax
        return sifir_y + alt_h * v / ymin

    for k in range(0, 101, 10):
        p.setPen(QPen(QColor("#E3E7EF"), max(1, s)))
        p.drawLine(QPointF(alan.left(), yy(k)), QPointF(alan.right(), yy(k)))
        _yaz(p, QRectF(rect.left(), yy(k) - 10 * s, sol - 8 * s, 20 * s), f"{k}%", 11 * s, False, SAG, tema.YAZI_SOLUK)
    _yaz(p, QRectF(rect.left(), yy(-mola_pay) - 10 * s, sol - 8 * s, 20 * s), f"-{mola_pay:.0f}%", 11 * s, False, SAG, tema.YAZI_SOLUK)
    slot = alan.width() / len(veri)
    genislik = min(slot * 0.62, 46 * s)
    YESIL_, KIRMIZI_, TURUNCU_, MOR_ = "#5E9B2A", "#D64541", "#F28C28", tema.MOLA_RENK

    def parca(cx, a, u, renk_, soluk, yazi):
        r_ = QRectF(cx - genislik / 2, yy(u), genislik, yy(a) - yy(u))
        if r_.height() < 0.4:
            return
        ana = QColor(renk_)
        if soluk:
            ana = ana.lighter(165)
        g = QLinearGradient(r_.topLeft(), r_.topRight())
        g.setColorAt(0, ana.lighter(115))
        g.setColorAt(1, ana.darker(106))
        p.setPen(QPen(QColor("white"), max(0.6, 0.8 * s)))
        p.setBrush(QBrush(g))
        p.drawRect(r_)
        if soluk:
            p.setBrush(QBrush(QColor(90, 98, 120, 110), Qt.BDiagPattern))
            p.setPen(Qt.NoPen)
            p.drawRect(r_)
        if yazi and r_.height() >= 11 * s and genislik >= 20 * s:
            _yaz(p, r_, yazi, (10 if r_.height() >= 14 * s else 8.5) * s, True, ORTA, "#2B3040" if soluk else "#FFFFFF")

    for i, (m, c, mo, alti) in enumerate(veri):
        cx = alan.left() + slot * (i + 0.5)
        if m == secili:
            p.fillRect(QRectF(cx - slot / 2, alan.top(), slot, alan.height()), QColor(36, 26, 140, 22))
        if bolgeler is not None:
            bolgeler.append((QRectF(cx - slot / 2, alan.top(), slot, yy(0) - alan.top()), m, "durus"))
            bolgeler.append((QRectF(cx - slot / 2, yy(0), slot, alan.bottom() - yy(0) + 24 * s), m, "mola"))
        parca(cx, 0, c * 100, YESIL_, alti, f"{c * 100:.0f}%")
        parca(cx, c * 100, 100, KIRMIZI_, alti, f"{(1 - c) * 100:.0f}%")
        parca(cx, -mo * mola_pay, 0, TURUNCU_, alti, f"{mo * 100:.0f}%")
        parca(cx, -mola_pay, -mo * mola_pay, MOR_, alti, f"{(1 - mo) * 100:.0f}%")
        if alti:
            _yaz(p, QRectF(cx - slot / 2, yy(100) - 18 * s, slot, 16 * s), "eşik altı", 9 * s, False, ORTA, tema.YAZI_SOLUK)
        _yaz(p, QRectF(cx - slot / 2, alan.bottom() + 4 * s, slot, 20 * s), m, (12 if slot > 44 * s else 10) * s, True, ORTA, tema.YAZI)
    p.setPen(QPen(QColor("#9AA3B8"), max(1, 1.4 * s)))
    p.drawLine(QPointF(alan.left(), yy(0)), QPointF(alan.right(), yy(0)))
    genel = sonuc.genel[0]
    if genel is not None:
        y = yy(genel * 100)
        p.setPen(QPen(QColor(tema.TURUNCU), 2.4 * s))
        p.drawLine(QPointF(alan.left(), y), QPointF(alan.right(), y))
        _yaz(p, QRectF(alan.right() + 4 * s, y - 20 * s, sag - 4 * s, 40 * s), f"Genel\n{yuzde(genel)}", 11 * s, True, AL, tema.TURUNCU)
    gosterge = [("Çalışma", YESIL_), ("Duruş", KIRMIZI_), ("Mola yapılan", TURUNCU_), ("Molada çalışılan", MOR_)]
    p.setFont(font(11 * s))
    fm = p.fontMetrics()
    genler = [fm.horizontalAdvance(a) + 36 * s for a, _ in gosterge]
    gx = rect.center().x() - sum(genler) / 2
    gy = rect.bottom() - gos_h + 2 * s
    for (ad, renk_), w in zip(gosterge, genler):
        p.fillRect(QRectF(gx, gy + 4 * s, 12 * s, 10 * s), QColor(renk_))
        _yaz(p, QRectF(gx + 17 * s, gy, w, 18 * s), ad, 11 * s, False, AL, tema.YAZI)
        gx += w
    p.restore()


def _iki_satir(ad: str, sinir: int = 13) -> str:
    if len(ad) <= sinir or not any(c in ad for c in " -"):
        return ad
    orta, en = len(ad) / 2, -1
    for i, c in enumerate(ad):
        if c in " -" and (en < 0 or abs(i - orta) < abs(en - orta)):
            en = i
    return ad[:en + (1 if ad[en] == "-" else 0)] + "\n" + ad[en + 1:]


def _saat_dk(saat: float) -> str:
    dk = int(round(saat * 60))
    return f"{dk // 60}:{dk % 60:02d}"


def durus_dokum_grafigi(p: QPainter, rect: QRectF, liste: List[tuple], baslik: Optional[str] = None):
    """liste: [(duruş türü, saat)] büyükten küçüğe. Her tür kendi renginde; üstünde süre ve duruş içindeki payı."""
    s = olcek(rect)
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    if baslik:
        _yaz(p, QRectF(rect.left(), rect.top() + 4 * s, rect.width(), 26 * s), baslik, 16 * s, True, ORTA, tema.LACIVERT)
    if not liste:
        _yaz(p, rect, "Bu dönemde duruş kaydı yok", 15 * s, False, ORTA, tema.YAZI_SOLUK)
        p.restore()
        return
    toplam = sum(x[1] for x in liste) or 1.0
    cok = len(liste) > 12
    sol, sag, ust, alt = 60 * s, 20 * s, (62 if baslik else 40) * s, (74 if cok else 46) * s
    alan = QRectF(rect.left() + sol, rect.top() + ust, rect.width() - sol - sag, rect.height() - ust - alt)
    import math
    ymax = max(0.5, math.ceil(liste[0][1] * 1.05 * 2) / 2)
    adim = ymax / 4
    for i in range(5):
        k = adim * i
        y = alan.bottom() - alan.height() * k / ymax
        p.setPen(QPen(QColor("#E3E7EF"), max(1, s)))
        p.drawLine(QPointF(alan.left(), y), QPointF(alan.right(), y))
        _yaz(p, QRectF(rect.left(), y - 10 * s, sol - 8 * s, 20 * s), (f"{k:.1f}".replace(".", ",") if ymax < 8 else f"{k:.0f}") + " sa", 11 * s, False, SAG, tema.YAZI_SOLUK)
    slot = alan.width() / len(liste)
    genislik = min(slot * 0.56, 64 * s)
    for i, (tip, saat) in enumerate(liste):
        cx = alan.left() + slot * (i + 0.5)
        h = max(2.0, alan.height() * saat / ymax)
        br = QRectF(cx - genislik / 2, alan.bottom() - h, genislik, h)
        ana = QColor(tema.durus_rengi(tip))
        g = QLinearGradient(br.topLeft(), br.bottomLeft())
        g.setColorAt(0, ana.lighter(125))
        g.setColorAt(1, ana)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawRoundedRect(br, 3 * s, 3 * s) if h > 6 * s else p.drawRect(br)
        _yaz(p, QRectF(cx - slot / 2, br.top() - 34 * s, slot, 32 * s), f"{_saat_dk(saat)}\n{yuzde(saat / toplam, 0)}", 11 * s, True, ORTA, tema.YAZI)
        if cok:
            p.save()
            p.translate(cx - 4 * s, alan.bottom() + 8 * s)
            p.rotate(32)
            _yaz(p, QRectF(0, -8 * s, 200 * s, 16 * s), tip, 10.5 * s, False, AL, tema.YAZI)
            p.restore()
        else:
            _yaz(p, QRectF(cx - slot / 2, alan.bottom() + 4 * s, slot, 36 * s), _iki_satir(tip), 11 * s, True, ORTA, tema.YAZI)
    p.setPen(QPen(QColor("#9AA3B8"), max(1, s)))
    p.drawLine(alan.bottomLeft(), alan.bottomRight())
    p.restore()


def mola_pasta_grafigi(p: QPainter, rect: QRectF, vardiyalar: List[tuple], mola_dk: float):
    """vardiyalar: [(başlık, grup lideri, mola oranı 0-1)]. Pastanın tamamı mola hakkıdır:
    turuncu mola yapılan, mor molada çalışılan süre."""
    s = olcek(rect)
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    if not vardiyalar:
        _yaz(p, rect, "Bu makine için vardiya bazlı mola verisi yok", 15 * s, False, ORTA, tema.YAZI_SOLUK)
        p.restore()
        return
    TURUNCU_, MOR_ = "#F28C28", tema.MOLA_RENK
    n = len(vardiyalar)
    hucre = rect.width() / n
    for i, (ad, sef, oran) in enumerate(vardiyalar):
        oran = max(0.0, min(1.0, oran))
        kutu = QRectF(rect.left() + i * hucre, rect.top(), hucre, rect.height())
        _yaz(p, QRectF(kutu.left(), kutu.top() + 2 * s, hucre, 22 * s), ad, 14 * s, True, ORTA, tema.LACIVERT)
        if sef:
            _yaz(p, QRectF(kutu.left(), kutu.top() + 24 * s, hucre, 18 * s), sef, 11.5 * s, True, ORTA, tema.YESIL)
        cap = min(hucre * 0.50, kutu.height() - 124 * s)
        daire = QRectF(kutu.center().x() - cap / 2, kutu.top() + 52 * s, cap, cap)
        p.setPen(QPen(QColor("white"), 2 * s))
        yapilan = int(round(360 * 16 * oran))
        p.setBrush(QColor(TURUNCU_))
        p.drawPie(daire, 90 * 16, -yapilan)
        p.setBrush(QColor(MOR_))
        p.drawPie(daire, 90 * 16 - yapilan, -(360 * 16 - yapilan))
        p.setBrush(QColor("white"))
        p.setPen(Qt.NoPen)
        ic = daire.adjusted(cap * 0.27, cap * 0.27, -cap * 0.27, -cap * 0.27)
        p.drawEllipse(ic)
        _yaz(p, ic, f"{oran * 100:.0f}%", 15 * s, True, ORTA, TURUNCU_)
        y = daire.bottom() + 12 * s
        for metin, renk_ in ((f"Mola yapılan: {oran * 100:.0f}% · günde ort. {oran * mola_dk:.0f} dk", TURUNCU_),
                             (f"Molada çalışılan: {(1 - oran) * 100:.0f}% · günde ort. {(1 - oran) * mola_dk:.0f} dk", MOR_)):
            p.setFont(font(11.5 * s))
            w = p.fontMetrics().horizontalAdvance(metin) + 20 * s
            x = kutu.center().x() - w / 2
            p.fillRect(QRectF(x, y + 5 * s, 12 * s, 10 * s), QColor(renk_))
            _yaz(p, QRectF(x + 18 * s, y, w, 20 * s), metin, 11.5 * s, False, AL, tema.YAZI)
            y += 22 * s
    p.restore()


def _html_kacis(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _html_ciz(p: QPainter, rect: QRectF, html: str, k: float, taban_px: float = 15.0):
    """HTML'i kutuya sığdırarak çizer (sığmazsa küçültür)."""
    from PySide6.QtGui import QTextDocument
    doc = QTextDocument()
    f = font(taban_px)
    doc.setDefaultFont(f)
    doc.setDocumentMargin(0)
    olcek_ = k
    for _ in range(12):
        doc.setTextWidth(rect.width() / olcek_)
        doc.setHtml(html)
        if doc.size().height() * olcek_ <= rect.height() or olcek_ < 0.35 * k:
            break
        olcek_ *= 0.92
    p.save()
    p.translate(rect.left(), rect.top())
    p.scale(olcek_, olcek_)
    doc.drawContents(p, QRectF(0, 0, rect.width() / olcek_, rect.height() / olcek_))
    p.restore()


IDARI_SAYFA = 4
_DURUM_RENK = {"Kritik düşük": "#D64541", "Düşük": "#F28C28", "Orta": "#E0B400", "Hedefte": "#5E9B2A"}


def _idari_basligi(p: QPainter, rect: QRectF, r: dict, sayfa: int):
    W = rect.width()
    k = W / 1600.0
    kenar = 36 * k
    ic = rect.adjusted(kenar, kenar, -kenar, -kenar)
    lg = tema.logo()
    ust_h = 96 * k
    if not lg.isNull():
        lh = 70 * k
        lw = lh * lg.width() / lg.height()
        p.drawPixmap(QRectF(ic.left(), ic.top() + 6 * k, lw, lh), lg, QRectF(lg.rect()))
    _yaz_sigdir(p, QRectF(ic.left() + 330 * k, ic.top(), ic.width() - 400 * k, 56 * k), r["baslik"], 30 * k, True, ORTA, tema.LACIVERT, 14 * k)
    _yaz(p, QRectF(ic.left() + 330 * k, ic.top() + 50 * k, ic.width() - 400 * k, 34 * k), r["donem"], 18 * k, False, ORTA, tema.YAZI_SOLUK)
    p.setPen(QPen(QColor(tema.YESIL), 4 * k))
    p.drawLine(QPointF(ic.left(), ic.top() + ust_h), QPointF(ic.right(), ic.top() + ust_h))
    _yaz(p, QRectF(ic.left(), ic.bottom() - 36 * k, ic.width() * 0.7, 32 * k),
         f"Eşik: %{r['esik'] * 100:.0f}  ·  Net vardiya süresi: {tema.sayi(r['net_saat'], 2)} saat",
         12.5 * k, False, AL, tema.YAZI_SOLUK)
    _yaz(p, QRectF(ic.right() - 520 * k, ic.bottom() - 36 * k, 520 * k, 32 * k), f"{r.get('alt_sag', '')}  ·  Sayfa {sayfa + 1}/{IDARI_SAYFA}",
         12.5 * k, False, SAG, tema.YAZI_SOLUK)
    govde = QRectF(ic.left(), ic.top() + ust_h + 16 * k, ic.width(), ic.height() - ust_h - 16 * k - 44 * k)
    return govde, k


def idari_ciz(p: QPainter, rect: QRectF, r: dict, sayfa: int = 0):
    """İdari rapor: 1. sayfa değerlendirme metni ve tablolar, 2-4. sayfalar grafikler."""
    p.save()
    p.fillRect(rect, QColor("white"))
    govde, k = _idari_basligi(p, rect, r, sayfa)
    cm, sonuc, makineler = r.get("cormind") or {}, r["sonuc"], r["makineler"]
    bosluk = 16 * k
    if sayfa == 0:
        ic = r["idari"]
        sol = QRectF(govde.left(), govde.top(), govde.width() * 0.50, govde.height())
        sag = QRectF(sol.right() + 28 * k, govde.top(), govde.width() - sol.width() - 28 * k, govde.height())
        # sol: düzenlenebilir metin
        h = []
        for satir in (r.get("idari_metin") or "").split("\n"):
            t = satir.strip()
            if not t:
                h.append("<div style='font-size:6px'>&nbsp;</div>")
            elif t == tema.tr_buyuk(t) and len(t) > 3 and not t.startswith("-"):
                h.append(f"<div style='color:{tema.LACIVERT};font-weight:700;font-size:17px;margin-top:6px'>{_html_kacis(t)}</div>")
            elif t[:1].isdigit() and t[1:3] in (". ", ") "):
                h.append(f"<div style='font-weight:700;margin-top:4px'>{_html_kacis(t)}</div>")
            elif t.startswith("-"):
                h.append(f"<div style='margin-left:18px'>• {_html_kacis(t.lstrip('- '))}</div>")
            else:
                h.append(f"<div>{_html_kacis(t)}</div>")
        _html_ciz(p, sol, "".join(h), k)
        # sağ: tablolar
        th = f"background:{tema.LACIVERT};color:white;font-weight:700;padding:4px 6px"
        td = "padding:3px 6px;border-bottom:1px solid #D9DEE8"
        t = [f"<div style='color:{tema.LACIVERT};font-weight:700;font-size:17px'>TEZGÂH PERFORMANS DEĞERLERİ</div>",
             "<table width='100%' cellspacing='0' cellpadding='0'>",
             f"<tr><td style='{th}'>Tezgâh</td><td style='{th}' align='right'>OEE (Cormind)</td><td style='{th}' align='right'>Çalışma</td>"
             f"<td style='{th}'>Başlıca kayıp</td><td style='{th}'>Durum</td></tr>"]
        for x in ic["perf"][:16]:
            cal = yuzde(x["calisma"], 1) if x["calisma"] is not None else "–"
            t.append(f"<tr><td style='{td}'><b>{_html_kacis(x['tezgah'])}</b></td><td style='{td}' align='right'>%{x['oee']:.1f}</td>"
                     f"<td style='{td}' align='right'>{cal}</td><td style='{td}'>{_html_kacis(x['kayip'])}</td>"
                     f"<td style='{td};color:{_DURUM_RENK.get(x['durum'], tema.YAZI)}'><b>● {x['durum']}</b></td></tr>")
        if ic.get("oee_ort") is not None:
            t.append(f"<tr><td style='{td};background:#EEF3E6'><b>Ortalama</b></td><td style='{td};background:#EEF3E6' align='right'><b>%{ic['oee_ort']:.1f}</b></td>"
                     f"<td style='{td};background:#EEF3E6' align='right'><b>{yuzde(sonuc.genel[0], 1) if sonuc.genel[0] is not None else '–'}</b></td>"
                     f"<td style='{td};background:#EEF3E6' colspan='2'>kaydı olan tezgâhların ortalaması · limit %{ic['limit']:.0f}</td></tr>")
        t.append("</table>")
        if ic["tezgah_tablo"]:
            t += [f"<div style='color:{tema.LACIVERT};font-weight:700;font-size:17px;margin-top:14px'>TEZGÂH BAZLI BİLDİRİM ÖZETİ</div>",
                  "<table width='100%' cellspacing='0' cellpadding='0'>",
                  f"<tr><td style='{th}'>Tezgâh</td><td style='{th}'>Kayıt</td><td style='{th}'>En çok tekrarlayan</td><td style='{th}'>Açıklama</td></tr>"]
            for x in ic["tezgah_tablo"][:14]:
                ac = x["aciklama"] if len(x["aciklama"]) <= 190 else x["aciklama"][:187] + "…"
                t.append(f"<tr><td style='{td}'><b>{_html_kacis(x['tezgah'])}</b></td><td style='{td}'>{x['kayit']} vardiya</td>"
                         f"<td style='{td}'>{_html_kacis(x['kategori'])}</td><td style='{td}'>{_html_kacis(ac)}</td></tr>")
            t.append("</table>")
        _html_ciz(p, sag, "".join(t), k, 14.0)
    elif sayfa == 1:
        yari = (govde.height() - bosluk) / 2
        cormind_oee_grafigi(p, QRectF(govde.left(), govde.top(), govde.width(), yari), cm)
        genel_performans_grafigi(p, QRectF(govde.left(), govde.top() + yari + bosluk, govde.width(), yari), sonuc, makineler, r.get("mola_pay", 9.09))
    elif sayfa == 2:
        cormind_durus_grafigi(p, govde, cm)
    else:
        sol = QRectF(govde.left(), govde.top(), govde.width() * 0.56, govde.height() * 0.78)
        vardiya_grafigi(p, sol, sonuc, r["seflar"], 0, "Vardiya Bazlı Performans (Çalışma) Oranı", arka=False)
        tum = list(makineler) + sorted(m for m in sonuc.hucreler if m not in makineler)
        tw = min(govde.width() - sol.width() - 50 * k, govde.height() * 0.70)
        tablo_ciz(p, QRectF(govde.right() - tw, govde.top(), tw, govde.height()), sonuc, tum, 0)
    p.restore()


def sayfa_sayisi(r: dict) -> int:
    return IDARI_SAYFA if r.get("duzen") == "idari" else 1


def sayfa_ciz(p: QPainter, rect: QRectF, r: dict, sayfa: int = 0):
    if r.get("duzen") == "idari":
        idari_ciz(p, rect, r, sayfa)
    else:
        rapor_ciz(p, rect, r)


def rapor_resmi(r: dict, genislik: int = 1400) -> QImage:
    h = int(genislik * 297 / 420)
    n = sayfa_sayisi(r)
    ara = int(genislik * 0.012) if n > 1 else 0
    img = QImage(genislik, h * n + ara * (n - 1), QImage.Format_ARGB32)
    img.fill(QColor("#DDE1EA") if n > 1 else QColor("white"))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    for i in range(n):
        sayfa_ciz(p, QRectF(0, i * (h + ara), genislik, h), r, i)
    p.end()
    return img
