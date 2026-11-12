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


def tablo_ciz(p: QPainter, rect: QRectF, sonuc: DonemSonuc, makineler: List[str], secim: int = 0):
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
            _yaz(p, r.adjusted(5 * s, 0, -5 * s, 0), metin, px * s, kalin, hiza, yazi)

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


def tablo_resmi(sonuc, makineler, secim=0, genislik=660) -> QImage:
    n = len(makineler) + 4
    yuk = int(genislik * tablo_yukseklik_orani(len(makineler)) / 1.45)
    yuk = int(n * 30)
    img = QImage(genislik, yuk, QImage.Format_ARGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    tablo_ciz(p, QRectF(0, 0, genislik, yuk), sonuc, makineler, secim)
    p.end()
    return img


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
        ust_yuk = govde.height() * 0.50
        cerceve = QRectF(govde.left(), govde.top(), govde.width(), ust_yuk)
        makine_grafigi(p, cerceve, sonuc, makineler, 0, "Makine Bazlı Performans (Çalışma) Oranı", r.get("bos_goster", False), arka=False)
        alt = QRectF(govde.left(), govde.top() + ust_yuk + 14 * k, govde.width(), govde.height() - ust_yuk - 14 * k)
        gorsel = r.get("gorsel")
        if gorsel is not None and not gorsel.isNull():
            oran = min(alt.width() / gorsel.width(), alt.height() / gorsel.height())
            w, h = gorsel.width() * oran, gorsel.height() * oran
            p.drawImage(QRectF(alt.center().x() - w / 2, alt.top(), w, h), gorsel)
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


def rapor_resmi(r: dict, genislik: int = 1400) -> QImage:
    h = int(genislik * 297 / 420)
    img = QImage(genislik, h, QImage.Format_ARGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    rapor_ciz(p, QRectF(0, 0, genislik, h), r)
    p.end()
    return img
