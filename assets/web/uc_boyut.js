// Sütun grafiklerini üç boyutlu kutulara çevirir (ön yüz, yan yüz, üst yüz) ve açılışta tabandan yükselterek gösterir.
// Python tarafındaki seçenekler değişmez: her "bar" serisi aynı verilerle "custom" seriye dönüştürülür.
// Yığılmış sütunlar (stack), eksi değerler (mola), eşik altı (taralı), etiketler, bilgi kutusu ve tıklama korunur.
(function () {
  function hex(c) {
    if (!c) return '#888888';
    if (typeof c === 'object' && c.colorStops) return hex(c.colorStops[Math.min(1, c.colorStops.length - 1)].color);
    if (typeof c !== 'string') return '#888888';
    if (c.charAt(0) === '#' && c.length === 4) c = '#' + c[1] + c[1] + c[2] + c[2] + c[3] + c[3];
    return c;
  }
  function karis(c, oran) {            // oran > 0 açar (beyaza), < 0 koyulaştırır (siyaha)
    c = hex(c); if (c.charAt(0) !== '#') return c;
    var r = parseInt(c.substr(1, 2), 16), g = parseInt(c.substr(3, 2), 16), b = parseInt(c.substr(5, 2), 16);
    var h = oran > 0 ? 255 : 0, k = Math.abs(oran);
    r = Math.round(r + (h - r) * k); g = Math.round(g + (h - g) * k); b = Math.round(b + (h - b) * k);
    return 'rgb(' + r + ',' + g + ',' + b + ')';
  }
  function deger(d) { return (d !== null && typeof d === 'object') ? d.value : d; }

  function kutu(params, api) {
    var i = api.value(0), alt = api.value(1), ust = api.value(2);
    if (alt === ust || alt == null || ust == null || isNaN(alt) || isNaN(ust)) return null;
    var veri = api.veriler[params.dataIndex] || {};
    var pA = api.coord([i, alt]), pU = api.coord([i, ust]), p0 = api.coord([i, 0]);
    var slot = api.size([1, 0])[0];
    var w = Math.min(slot * 0.56, api.azami || 46);
    var d = Math.max(3, Math.min(w * 0.32, 13));            // derinlik
    var x0 = pA[0] - w / 2 - d / 2;
    var yUst = Math.min(pA[1], pU[1]), yAlt = Math.max(pA[1], pU[1]);
    var renk = hex((veri.itemStyle && veri.itemStyle.color) || api.renk);
    var soluk = !!(veri.itemStyle && veri.itemStyle.decal);
    var cocuk = [
      {type: 'polygon', shape: {points: [[x0 + w, yUst], [x0 + w + d, yUst - d], [x0 + w + d, yAlt - d], [x0 + w, yAlt]]},
       style: {fill: karis(renk, -0.28)}},
      {type: 'rect', shape: {x: x0, y: yUst, width: w, height: Math.max(0.5, yAlt - yUst)},
       style: {fill: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
         {offset: 0, color: karis(renk, 0.30)}, {offset: 0.45, color: renk}, {offset: 1, color: karis(renk, -0.12)}])}},
      {type: 'polygon', shape: {points: [[x0, yUst], [x0 + d, yUst - d], [x0 + w + d, yUst - d], [x0 + w, yUst]]},
       style: {fill: karis(renk, 0.38)}}
    ];
    if (soluk) {                                             // eşik altı: taralı desen
      var cizgi = [];
      for (var k = -yAlt; k < w + (yAlt - yUst); k += 6) {
        cizgi.push({type: 'line', shape: {x1: x0 + k, y1: yAlt, x2: x0 + k + (yAlt - yUst), y2: yUst},
                    style: {stroke: 'rgba(80,90,120,0.45)', lineWidth: 1}});
      }
      cocuk.push({type: 'group', children: cizgi, clipPath: {type: 'rect', shape: {x: x0, y: yUst, width: w, height: yAlt - yUst}}});
    }
    if (veri.secili) {
      cocuk.push({type: 'rect', shape: {x: x0 - 1, y: yUst - 1, width: w + 2, height: yAlt - yUst + 2},
                  style: {fill: 'none', stroke: '#150958', lineWidth: 2}});
    }
    var et = veri.label || {}, se = api.etiket || {};
    var goster = et.show !== undefined ? et.show : se.show;
    var yazi = et.formatter !== undefined ? et.formatter : (se.formatter || null);
    if (goster && yazi !== null && yazi !== '' && yazi !== undefined) {
      if (typeof yazi === 'string' && yazi.indexOf('{c}') >= 0) yazi = yazi.replace('{c}', ust - alt);
      var ust_mu = (et.position || se.position) === 'top';
      cocuk.push({type: 'text', z2: 10, style: {
        text: String(yazi), x: x0 + w / 2 + (ust_mu ? d / 2 : 0), y: ust_mu ? yUst - d - 3 : (yUst + yAlt) / 2,
        align: 'center', verticalAlign: ust_mu ? 'bottom' : 'middle',
        fill: ust_mu ? (se.color || '#1b1e2b') : '#ffffff', font: '700 ' + (se.fontSize || 11) + 'px "Segoe UI", sans-serif',
        lineHeight: (se.fontSize || 11) + 3,
        textShadowColor: ust_mu ? 'transparent' : 'rgba(0,0,0,0.25)', textShadowBlur: ust_mu ? 0 : 2}});
    }
    return {type: 'group', children: cocuk, originX: pA[0], originY: p0[1],
            enterFrom: {scaleY: 0, style: {opacity: 0.4}}, enterAnimation: {duration: 900, delay: api.gecikme * params.dataIndex}};
  }

  window.ucBoyut = function (o) {
    if (!o || !o.series || o.ucBoyutYok) return o;
    var kume = {};
    o.series = o.series.map(function (s) {
      if (s.type !== 'bar') return s;
      var xi = s.xAxisIndex || 0, anahtar = (s.stack || ('_' + Math.random())) + '|' + xi;
      var k = kume[anahtar] || (kume[anahtar] = {art: [], eks: []});
      var veriler = [], data = [];
      (s.data || []).forEach(function (d, i) {
        var v = deger(d);
        var nesne = (d !== null && typeof d === 'object') ? d : {};
        veriler.push(nesne);
        if (v == null || isNaN(v)) { data.push({value: [i, null, null]}); return; }
        var dizi = v >= 0 ? k.art : k.eks, taban = dizi[i] || 0;
        dizi[i] = taban + v;
        var yeni = {};
        for (var a in nesne) if (a !== 'value' && a !== 'label' && a !== 'itemStyle') yeni[a] = nesne[a];
        yeni.value = [i, taban, taban + v];
        if (nesne.itemStyle && nesne.itemStyle.borderWidth) nesne.secili = true;
        data.push(yeni);
      });
      var renk = s.color || (s.itemStyle && s.itemStyle.color);
      var etiket = s.label || {};
      var gecikme = Math.min(40, 700 / Math.max(1, data.length));
      var yeniSeri = {
        type: 'custom', name: s.name, xAxisIndex: xi, yAxisIndex: s.yAxisIndex || 0, data: data, z: s.z,
        color: hex(renk), silent: s.silent, tooltip: s.tooltip, markLine: s.markLine, encode: {x: 0, y: [1, 2]},
        renderItem: function (params, api) {
          api.veriler = veriler; api.renk = renk; api.etiket = etiket; api.azami = s.barMaxWidth; api.gecikme = gecikme;
          return kutu(params, api);
        }
      };
      return yeniSeri;
    });
    o.animationDuration = 900;
    o.animationEasing = 'cubicOut';
    o.animationDurationUpdate = 700;
    o.animationEasingUpdate = 'cubicInOut';
    return o;
  };
})();
