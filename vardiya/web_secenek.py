"""Programın grafiklerinin ECharts karşılıkları. Her yapıcı, cizim'deki aynı adlı işlevin parametrelerini (sözlük) alır
ve bir ECharts seçeneği döndürür. Veri ve hesap cizim ile birebir aynıdır; yalnızca görünüm değişir."""
from __future__ import annotations

from typing import Dict, List, Optional

from . import tema
from .hesap import VARDIYALAR

LACIVERT, YAZI, SOLUK, CIZGI = tema.LACIVERT, "#1b1e2b", "#6b7285", "#e3e7ef"
YESIL_, KIRMIZI_, TURUNCU_, MOR_ = "#5E9B2A", "#D64541", "#F28C28", tema.MOLA_RENK


def _ac(renk: str, oran: float) -> str:
    renk = renk.lstrip("#")
    r, g, b = (int(renk[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % tuple(int(x + (255 - x) * oran) for x in (r, g, b))


def _gecis(renk: str, soluk: bool = False) -> dict:
    """Hafif üç boyut hissi: soldan sağa açıktan koyuya geçiş."""
    ana = _ac(renk, 0.55) if soluk else renk
    return {"type": "linear", "x": 0, "y": 0, "x2": 1, "y2": 0,
            "colorStops": [{"offset": 0, "color": _ac(ana, 0.28)}, {"offset": 0.55, "color": ana}, {"offset": 1, "color": _ac(ana, -0.0) if False else ana}]}


def _golge() -> dict:
    return {"shadowBlur": 6, "shadowColor": "rgba(21,9,88,0.18)", "shadowOffsetX": 2, "shadowOffsetY": 2}


TARALI = {"symbol": "rect", "dashArrayX": [1, 0], "dashArrayY": [2, 4], "rotation": -0.785, "color": "rgba(80,90,120,0.35)"}


def _baslik(metin: Optional[str], boy: int = 17) -> dict:
    if not metin:
        return {"show": False}
    return {"text": metin, "left": "center", "top": 4, "textStyle": {"color": LACIVERT, "fontSize": boy, "fontWeight": 700}}


def _eksen_y(**ek) -> dict:
    d = {"type": "value", "axisLabel": {"color": SOLUK, "formatter": "{value}%"}, "splitLine": {"lineStyle": {"color": CIZGI}}}
    d.update(ek)
    return d


def _eksen_x(adlar: List[str], **ek) -> dict:
    d = {"type": "category", "data": adlar, "axisTick": {"show": False}, "axisLine": {"lineStyle": {"color": "#9AA3B8"}},
         "axisLabel": {"color": YAZI, "fontWeight": 600, "interval": 0, "rotate": 45 if len(adlar) > 18 else 0, "fontSize": 11}}
    d.update(ek)
    return d


def _ipucu() -> dict:
    return {"trigger": "item", "ozel": True, "backgroundColor": "rgba(255,255,255,0.97)", "borderColor": CIZGI,
            "textStyle": {"color": YAZI, "fontSize": 12}, "extraCssText": "box-shadow:0 6px 18px rgba(21,9,88,.15);border-radius:8px;"}


def _yuzde(x: Optional[float], b: int = 1) -> str:
    return "-" if x is None else tema.yuzde(x, b)


def _bos(metin: str = "Seçilen dönemde gösterilecek veri yok") -> dict:
    return {"title": {"text": metin, "left": "center", "top": "middle", "textStyle": {"color": SOLUK, "fontSize": 15, "fontWeight": 400}},
            "xAxis": {"show": False}, "yAxis": {"show": False}, "series": []}


def _ort_cizgisi(deger: float, ad: str, renk: str = TURUNCU_) -> dict:
    return {"symbol": "none", "silent": True, "data": [{"yAxis": round(deger, 2)}],
            "lineStyle": {"color": renk, "width": 2.4, "type": "solid"},
            "label": {"formatter": ad, "color": renk, "fontWeight": 700, "position": "end"}}


# ------------------------------------------------------------------ vardiya
def vardiya_grafigi(a: dict) -> dict:
    sonuc, seflar, secim = a["sonuc"], a.get("seflar") or {}, a.get("secim", 0)
    ad = tema.METRIKLER[secim]
    baslik = a.get("baslik")
    baslik = baslik if baslik is not None else f"Vardiya Bazlı {ad} Oranı"
    renk = tema.METRIK_RENK[secim]
    adlar, veri = [], []
    for v in VARDIYALAR:
        o = sonuc.vardiyalar[v]
        x = getattr(o, ("calisma", "durus", "mola")[secim])
        sef = seflar.get(v, "")
        adlar.append(f"{v}.VARDİYA" + (f"\n{tema.tr_buyuk(sef)}" if sef else ""))
        veri.append({"value": None if x is None else round(x * 100, 2), "tip": f"<b>{v}. vardiya</b><br>{ad}: <b>{_yuzde(x, 2)}</b><br>{o.gun_sayisi} gün",
                     "label": {"show": x is not None, "formatter": _yuzde(x, 2) + f"\n{o.gun_sayisi} gün"}})
    genel = sonuc.genel[secim]
    seri = {"type": "bar", "name": ad, "data": veri, "barMaxWidth": 90, "itemStyle": dict(_golge(), color=_gecis(renk), borderRadius=[6, 6, 0, 0]),
            "label": {"position": "top", "color": YAZI, "fontWeight": 700, "fontSize": 14}}
    if genel is not None:
        seri["markLine"] = _ort_cizgisi(genel * 100, f"Genel\n{_yuzde(genel)}")
    return {"title": _baslik(baslik), "tooltip": _ipucu(), "grid": {"left": 50, "right": 70, "top": 46 if baslik else 18, "bottom": 50},
            "xAxis": _eksen_x(adlar, axisLabel={"color": YAZI, "fontWeight": 700, "fontSize": 12, "lineHeight": 18}),
            "yAxis": _eksen_y(max=110 if secim == 0 else None, interval=10 if secim == 0 else None), "series": [seri]}


# ------------------------------------------------------------------ makine (Çalışma sayfası)
def makine_grafigi(a: dict) -> dict:
    from .cizim import _deger_listesi
    sonuc, secim = a["sonuc"], a.get("secim", 0)
    ad = tema.METRIKLER[secim]
    baslik = a.get("baslik")
    baslik = baslik if baslik is not None else f"Makine Bazlı {ad} Oranı"
    veri = _deger_listesi(sonuc, secim, a.get("makineler") or [], a.get("bos_goster", False))
    if not veri:
        return _bos()
    renk = tema.METRIK_RENK[secim]
    d = [{"value": None if v is None else round(v * 100, 2), "anahtar": m, "tip": f"<b>{m}</b><br>{ad}: <b>{_yuzde(v, 2)}</b>",
          "label": {"formatter": _yuzde(v, 0)}} for m, v in veri]
    seri = {"type": "bar", "name": ad, "data": d, "barMaxWidth": 46, "itemStyle": dict(_golge(), color=_gecis(renk), borderRadius=[4, 4, 0, 0]),
            "label": {"show": True, "position": "top", "color": YAZI, "fontWeight": 700, "fontSize": 11}}
    genel = sonuc.genel[secim]
    if genel is not None:
        seri["markLine"] = _ort_cizgisi(genel * 100, f"Genel\n{_yuzde(genel)}")
    return {"title": _baslik(baslik), "tooltip": _ipucu(), "grid": {"left": 50, "right": 76, "top": 46 if baslik else 18, "bottom": 56},
            "xAxis": _eksen_x([m for m, _ in veri]), "yAxis": _eksen_y(max=110 if secim == 0 else None, interval=10 if secim == 0 else None),
            "series": [seri]}


# ------------------------------------------------------------------ genel performans (Performans sayfası ve idari rapor)
def genel_performans_grafigi(a: dict) -> dict:
    sonuc, makineler, mola_pay = a["sonuc"], a.get("makineler") or [], float(a.get("mola_pay") or 9.0)
    baslik, secili = a.get("baslik"), a.get("secili")
    sirali = list(makineler) + sorted(m for m in sonuc.hucreler if m not in makineler)
    veri = []
    for m in sirali:
        ort = sonuc.makine_ort.get(m)
        if ort and ort[0] is not None:
            veri.append((m, max(0.0, min(1.0, ort[0])), max(0.0, min(1.0, ort[2] or 0.0)), False))
        elif m in sonuc.esik_alti:
            e = sonuc.esik_alti[m]
            veri.append((m, max(0.0, min(1.0, e[0])), max(0.0, min(1.0, e[2])), True))
    if not veri:
        return _bos()
    hak = int(round(mola_pay))
    seriler = {"Çalışma": [], "Duruş": [], "Mola yapılan": [], "Molada çalışılan": []}
    for m, ca, mo, alti in veri:
        yapilan = min(hak, int(round(mo * mola_pay)))
        tip = (f"<b>{m}</b>" + (" <span style='color:#8a90a2'>(eşik altı, hesaba girmez)</span>" if alti else "")
               + f"<br>Çalışma: <b>{_yuzde(ca)}</b><br>Duruş: <b>{_yuzde(1 - ca)}</b>"
               + f"<br>Mola yapılan: <b>{yapilan}%</b> · molada çalışılan: <b>{hak - yapilan}%</b> (mola hakkı %{hak})"
               + "<br><span style='color:#8a90a2'>tıklayın: " + "duruş dökümü / vardiya bazlı mola</span>")
        ortak = {"anahtar": m, "tip": tip}
        sinir = {"borderColor": LACIVERT, "borderWidth": 2} if m == secili else {}

        def oge(deger, renk, kisim, yazi, _alti=alti, _sinir=sinir):
            st = dict(color=_gecis(renk, _alti), **_sinir)
            if _alti:
                st["decal"] = TARALI
            return dict(ortak, value=round(deger, 3), kisim=kisim, itemStyle=st,
                        label={"show": bool(yazi), "formatter": yazi})
        seriler["Çalışma"].append(oge(ca * 100, YESIL_, "durus", f"{ca * 100:.0f}%" if ca >= 0.12 else ""))
        seriler["Duruş"].append(oge((1 - ca) * 100, KIRMIZI_, "durus", f"{(1 - ca) * 100:.0f}%" if (1 - ca) >= 0.12 else ""))
        seriler["Mola yapılan"].append(oge(-mo * mola_pay, TURUNCU_, "mola", f"{yapilan}%" if mo >= 0.15 else ""))
        seriler["Molada çalışılan"].append(oge(-(1 - mo) * mola_pay, MOR_, "mola", f"{hak - yapilan}%" if mo <= 0.85 else ""))
    renkler = {"Çalışma": YESIL_, "Duruş": KIRMIZI_, "Mola yapılan": TURUNCU_, "Molada çalışılan": MOR_}
    seri = [{"type": "bar", "name": ad, "stack": "s", "data": d, "barMaxWidth": 46, "color": renkler[ad],
             "itemStyle": _golge(), "label": {"position": "inside", "color": "#fff", "fontWeight": 700, "fontSize": 10},
             "emphasis": {"focus": "none", "itemStyle": {"shadowBlur": 12, "shadowColor": "rgba(21,9,88,0.35)"}}} for ad, d in seriler.items()]
    import math
    alt = -10 * max(1, math.ceil((mola_pay + 0.5) / 10))     # eksen 0'dan onar onar: ..., 10%, 0%, -10%
    return {"title": _baslik(baslik), "tooltip": _ipucu(),
            "legend": {"bottom": 0, "itemWidth": 14, "itemHeight": 10, "textStyle": {"color": SOLUK}},
            "grid": {"left": 50, "right": 30, "top": 46 if baslik else 16, "bottom": 70},
            "xAxis": _eksen_x([v[0] for v in veri], axisLine={"onZero": True, "lineStyle": {"color": "#9AA3B8"}}, position="bottom"),
            "yAxis": _eksen_y(min=alt, max=110, interval=10,
                              axisLabel={"color": SOLUK, "formatter": "{value}%"}),
            "series": seri}


# ------------------------------------------------------------------ Cormind
def cormind_oee_grafigi(a: dict) -> dict:
    cm, baslik, limit = a["cm"], a.get("baslik"), a.get("limit", 85.0)
    if not cm:
        return _bos()
    d = [{"value": round(v["oee"], 1), "anahtar": m, "tip": f"<b>{m}</b><br>OEE: <b>{v['oee']:.1f}%</b>".replace(".", ","),
          "label": {"formatter": f"{v['oee']:.0f}%"}} for m, v in cm.items()]
    seri = {"type": "bar", "name": "OEE", "data": d, "barMaxWidth": 46,
            "itemStyle": dict(_golge(), color={"type": "linear", "x": 0, "y": 0, "x2": 0, "y2": 1,
                                               "colorStops": [{"offset": 0, "color": "#2aa392"}, {"offset": 1, "color": "#16695F"}]},
                              borderRadius=[4, 4, 0, 0]),
            "label": {"show": True, "position": "top", "color": YAZI, "fontWeight": 700, "fontSize": 11},
            "markLine": _ort_cizgisi(limit, f"Limit\n%{limit:.0f}", "#E0B400")}
    return {"title": _baslik(baslik), "tooltip": _ipucu(), "grid": {"left": 50, "right": 70, "top": 46 if baslik else 18, "bottom": 56},
            "xAxis": _eksen_x(list(cm)), "yAxis": _eksen_y(min=0, max=110, interval=10), "series": [seri]}


def cormind_durus_grafigi(a: dict) -> dict:
    cm, baslik, limit = a["cm"], a.get("baslik"), a.get("limit", 15.0)
    if not cm:
        return _bos()
    makineler = list(cm)
    toplam: Dict[str, float] = {}
    for v in cm.values():
        for t, x in v["durus"].items():
            toplam[t] = toplam.get(t, 0.0) + x
    turler = sorted(toplam, key=lambda t: -toplam[t])
    seri = []
    for t in turler:
        d = []
        for m in makineler:
            x = cm[m]["durus"].get(t, 0.0)
            d.append({"value": round(x, 2) if x else None, "anahtar": m,
                      "tip": f"<b>{m}</b><br>{t}: <b>{x:.1f}%</b><br>Toplam: {cm[m]['toplam']:.0f}% · OEE {cm[m]['oee']:.0f}%".replace(".", ","),
                      "label": {"show": (6 if len(makineler) > 20 else 4) <= x < 95, "formatter": f"{x:.0f}%"}})
        seri.append({"type": "bar", "name": t, "stack": "s", "data": d, "barMaxWidth": 46, "color": tema.durus_rengi(t),
                     "itemStyle": {"borderColor": "rgba(255,255,255,0.6)", "borderWidth": 0.5},
                     "label": {"position": "inside", "color": "#fff", "fontWeight": 700, "fontSize": 9 if len(makineler) > 20 else 10}})
    seri.append({"type": "bar", "name": "Mola Süresi", "stack": "s", "color": MOR_, "barMaxWidth": 46,
                 "data": [{"value": round(cm[m]["mola"], 2), "anahtar": m, "tip": f"<b>{m}</b><br>Mola süresi: <b>{cm[m]['mola']:.1f}%</b>".replace(".", ","),
                           "label": {"show": cm[m]["mola"] <= -3, "formatter": f"{cm[m]['mola']:.0f}%"}} for m in makineler],
                 "label": {"position": "inside", "color": "#fff", "fontWeight": 700, "fontSize": 10}})
    seri.append({"type": "scatter", "name": "_toplam", "silent": True, "symbolSize": 0, "tooltip": {"show": False}, "z": 5,
                 "data": [{"value": [m, round(sum(cm[m]["durus"].values()), 2)], "label": {"formatter": f"{cm[m]['toplam']:.0f}%"}} for m in makineler],
                 "label": {"show": True, "position": "top", "distance": 4, "color": YAZI, "fontWeight": 700, "fontSize": 11}})
    seri[0]["markLine"] = _ort_cizgisi(limit, f"Limit\n%{limit:.0f}", "#3e9b2a")
    tavan = max(110.0, max(v["toplam"] for v in cm.values()) + 8)
    return {"title": _baslik(baslik), "tooltip": _ipucu(),
            "legend": {"bottom": 0, "type": "plain", "data": turler + ["Mola Süresi"], "itemWidth": 14, "itemHeight": 10,
                       "textStyle": {"color": SOLUK, "fontSize": 11}},
            "grid": {"left": 50, "right": 70, "top": 46 if baslik else 18, "bottom": 56 + 22 * (1 + len(turler) // 7)},
            "xAxis": _eksen_x(makineler), "yAxis": _eksen_y(min=-10, max=round(tavan / 10) * 10, interval=20), "series": seri}


# ------------------------------------------------------------------ ayrıntı
def durus_dokum_grafigi(a: dict) -> dict:
    liste, baslik = a.get("liste") or [], a.get("baslik")
    if not liste:
        return _bos("Bu dönemde duruş kaydı yok")
    from .cizim import _iki_satir, _saat_dk
    toplam = sum(x[1] for x in liste) or 1.0
    d = [{"value": round(sa, 3), "itemStyle": dict(_golge(), color=_gecis(tema.durus_rengi(t)), borderRadius=[4, 4, 0, 0]),
          "tip": f"<b>{t}</b><br>{_saat_dk(sa)} saat · duruşların {sa / toplam * 100:.0f}%'i",
          "label": {"formatter": f"{_saat_dk(sa)} sa\n{sa / toplam * 100:.0f}%"}} for t, sa in liste]
    return {"title": _baslik(baslik, 15), "tooltip": _ipucu(), "grid": {"left": 56, "right": 20, "top": 56 if baslik else 34, "bottom": 70},
            "xAxis": _eksen_x([_iki_satir(t) for t, _ in liste], axisLabel={"color": YAZI, "fontWeight": 600, "interval": 0, "fontSize": 11, "lineHeight": 14}),
            "yAxis": {"type": "value", "axisLabel": {"color": SOLUK, "formatter": "{value} sa"}, "splitLine": {"lineStyle": {"color": CIZGI}}},
            "series": [{"type": "bar", "data": d, "barMaxWidth": 60, "label": {"show": True, "position": "top", "color": YAZI, "fontWeight": 700, "fontSize": 11}}]}


def mola_pasta_grafigi(a: dict) -> dict:
    vardiyalar, mola_dk = a.get("vardiyalar") or [], float(a.get("mola_dk") or 40.0)
    if not vardiyalar:
        return _bos("Bu makine için vardiya bazlı mola verisi yok")
    n = len(vardiyalar)
    seri, baslik = [], []
    for i, (ad, sef, oran) in enumerate(vardiyalar):
        oran = max(0.0, min(1.0, oran))
        x = f"{(i + 0.5) * 100 / n:.1f}%"
        baslik.append({"text": ad, "subtext": tema.tr_buyuk(sef) if sef else "", "left": x, "top": 4, "textAlign": "center",
                       "textStyle": {"color": LACIVERT, "fontSize": 14, "fontWeight": 700}, "subtextStyle": {"color": tema.YESIL, "fontWeight": 700}})
        seri.append({"type": "pie", "center": [x, "58%"], "radius": ["34%", "64%"], "avoidLabelOverlap": True,
                     "itemStyle": {"borderColor": "#fff", "borderWidth": 2, **_golge()},
                     "label": {"formatter": "{b}\n{c} dk", "color": YAZI, "fontWeight": 600},
                     "data": [{"name": "Mola yapılan", "value": round(oran * mola_dk), "itemStyle": {"color": TURUNCU_},
                               "tip": f"<b>{ad}</b><br>Mola yapılan: <b>{oran * mola_dk:.0f} dk</b> ({oran * 100:.0f}%)"},
                              {"name": "Molada çalışılan", "value": round((1 - oran) * mola_dk), "itemStyle": {"color": MOR_},
                               "tip": f"<b>{ad}</b><br>Molada çalışılan: <b>{(1 - oran) * mola_dk:.0f} dk</b> ({(1 - oran) * 100:.0f}%)"}]})
    return {"title": baslik, "tooltip": _ipucu(), "series": seri}


# ------------------------------------------------------------------ operatör
def operator_grafik(a: dict) -> dict:
    from .operator_grafik import KISA_GUN, _biçim, gun_veri, toplu_veri
    baslik, secili, sonuclar, operator = a.get("baslik"), a.get("secili") or [], a.get("sonuclar") or {}, a.get("operator")
    if not secili:
        return _bos("Yukarıdan grafikte görmek istediğiniz ölçüleri işaretleyin.")
    n = len(secili)
    ust0, pay = 8.0, 92.0 / n
    grids, xs, ys, seriler, basliklar = [], [], [], [], [_baslik(baslik)]
    for i, m in enumerate(secili):
        if operator is None:
            veri, genel = toplu_veri(sonuclar, m)
            adlar, ad_genel, alt = [ad for ad, _ in veri], "Genel", f"{m.ad} – operatör bazlı"
        else:
            r = sonuclar.get(operator)
            gv = gun_veri(r, m) if r else None
            if gv is None:
                veri, genel, adlar = [], None, []
                alt = f"{m.ad}: bu ölçü gün gün hesaplanmıyor"
            else:
                veri, genel = gv
                adlar = [f"{g:%d.%m}\n{KISA_GUN[g.weekday()]}" for g, _ in veri]
                alt = f"{m.ad} – gün gün"
            ad_genel = "Ort."
        ust = ust0 + i * pay
        grids.append({"left": 56, "right": 78, "top": f"{ust + 5:.1f}%", "height": f"{pay - 13:.1f}%"})
        basliklar.append({"text": alt, "left": 56, "top": f"{ust + 0.5:.1f}%", "textStyle": {"color": LACIVERT, "fontSize": 13, "fontWeight": 700}})
        xs.append(dict(_eksen_x(adlar), gridIndex=i))
        ys.append(dict(_eksen_y() if m.yuzde else {"type": "value", "axisLabel": {"color": SOLUK}, "splitLine": {"lineStyle": {"color": CIZGI}}}, gridIndex=i))
        d = [{"value": round(v * 100, 2) if m.yuzde else round(v, 3), "tip": f"<b>{x if isinstance(x, str) else ''}</b>{m.ad}: <b>{_biçim(m.yuzde, v)}</b>",
              "label": {"formatter": _biçim(m.yuzde, v)}} for x, v in veri]
        s = {"type": "bar", "name": m.ad, "xAxisIndex": i, "yAxisIndex": i, "data": d, "barMaxWidth": 46,
             "itemStyle": dict(_golge(), color=_gecis(m.renk), borderRadius=[3, 3, 0, 0]),
             "label": {"show": True, "position": "top", "color": YAZI, "fontWeight": 700, "fontSize": 11}}
        if genel is not None:
            s["markLine"] = _ort_cizgisi(genel * 100 if m.yuzde else genel, f"{ad_genel}\n{_biçim(m.yuzde, genel)}")
        seriler.append(s)
    return {"title": basliklar, "tooltip": _ipucu(), "grid": grids, "xAxis": xs, "yAxis": ys, "series": seriler}


YAPICILAR = {
    "vardiya_grafigi": vardiya_grafigi,
    "makine_grafigi": makine_grafigi,
    "genel_performans_grafigi": genel_performans_grafigi,
    "cormind_oee_grafigi": cormind_oee_grafigi,
    "cormind_durus_grafigi": cormind_durus_grafigi,
    "durus_dokum_grafigi": durus_dokum_grafigi,
    "mola_pasta_grafigi": mola_pasta_grafigi,
    "operator_grafik": operator_grafik,
}
