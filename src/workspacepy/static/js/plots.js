/* Gráficas en <canvas> sin dependencias: línea, histograma, barras e imagen (mapa de color). */
"use strict";

const Plots = (() => {
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim() || "#888";
  const SERIES = ["#2f7dd1", "#e0782b", "#2ea36b", "#c2453f", "#8b5fc7", "#b58b00", "#17a2b8", "#d6579b"];

  function niceTicks(lo, hi, n = 6) {
    if (!(hi > lo)) { const d = Math.abs(lo) || 1; lo -= d / 2; hi += d / 2; }
    const span = hi - lo, raw = span / n, pow = Math.pow(10, Math.floor(Math.log10(raw)));
    const f = raw / pow, step = (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * pow;
    const a = Math.floor(lo / step) * step, b = Math.ceil(hi / step) * step, ticks = [];
    for (let v = a; v <= b + step / 2; v += step) ticks.push(Math.abs(v) < step * 1e-9 ? 0 : v);
    return { a, b, ticks };
  }
  const tickLabel = (v) => Fmt.num(v);

  function setup(canvas) {
    const dpr = window.devicePixelRatio || 1, r = canvas.getBoundingClientRect();
    canvas.width = Math.max(10, Math.round(r.width * dpr));
    canvas.height = Math.max(10, Math.round(r.height * dpr));
    const g = canvas.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, r.width, r.height);
    g.font = "11px " + css("--mono");
    return { g, w: r.width, h: r.height };
  }

  function frame(g, w, h, xr, yr, xlabel, margin) {
    const m = margin || { l: 58, r: 14, t: 12, b: 30 };
    const pw = w - m.l - m.r, ph = h - m.t - m.b;
    const X = (v) => m.l + ((v - xr.a) / (xr.b - xr.a)) * pw;
    const Y = (v) => m.t + ph - ((v - yr.a) / (yr.b - yr.a)) * ph;
    g.strokeStyle = css("--grid"); g.fillStyle = css("--muted"); g.lineWidth = 1;
    g.textAlign = "right"; g.textBaseline = "middle";
    for (const t of yr.ticks) { const y = Math.round(Y(t)) + .5; g.beginPath(); g.moveTo(m.l, y); g.lineTo(m.l + pw, y); g.stroke(); g.fillText(tickLabel(t), m.l - 6, y); }
    g.textAlign = "center"; g.textBaseline = "top";
    for (const t of xr.ticks) { const x = Math.round(X(t)) + .5; g.beginPath(); g.moveTo(x, m.t); g.lineTo(x, m.t + ph); g.stroke(); g.fillText(tickLabel(t), x, m.t + ph + 6); }
    g.strokeStyle = css("--border"); g.strokeRect(m.l + .5, m.t + .5, pw, ph);
    if (xlabel) { g.fillStyle = css("--muted"); g.textAlign = "right"; g.fillText(xlabel, m.l + pw, m.t + ph + 18); }
    return { X, Y, m, pw, ph };
  }

  function extent(arrs) {
    let lo = Infinity, hi = -Infinity;
    for (const a of arrs) for (const v of a) if (v !== null && Number.isFinite(v)) { if (v < lo) lo = v; if (v > hi) hi = v; }
    return Number.isFinite(lo) ? [lo, hi] : [0, 1];
  }

  function legend(g, w, names, m) {
    if (names.length < 2) return;
    let x = w - m.r - 6; g.textAlign = "right"; g.textBaseline = "middle";
    names.slice().reverse().forEach((n, i) => {
      const idx = names.length - 1 - i, tw = g.measureText(n).width;
      g.fillStyle = css("--text"); g.fillText(n, x, m.t + 10);
      g.fillStyle = SERIES[idx % SERIES.length]; g.fillRect(x - tw - 16, m.t + 6, 10, 8);
      x -= tw + 26;
    });
  }

  function line(canvas, d) {
    const { g, w, h } = setup(canvas);
    const xs = d.series.map((s) => s.x), ys = d.series.map((s) => s.y);
    const [xlo, xhi] = extent(xs), [ylo, yhi] = extent(ys);
    const xr = niceTicks(xlo, xhi), yr = niceTicks(ylo, yhi);
    const f = frame(g, w, h, xr, yr, d.xlabel);
    g.save(); g.beginPath(); g.rect(f.m.l, f.m.t, f.pw, f.ph); g.clip();
    d.series.forEach((s, i) => {
      g.strokeStyle = SERIES[i % SERIES.length]; g.lineWidth = 1.6; g.beginPath();
      let pen = false;
      for (let k = 0; k < s.x.length; k++) {
        const v = s.y[k];
        if (v === null) { pen = false; continue; }
        const px = f.X(s.x[k]), py = f.Y(v);
        if (!pen) { g.moveTo(px, py); pen = true; } else g.lineTo(px, py);
      }
      g.stroke();
      if (s.x.length <= 60) {
        g.fillStyle = SERIES[i % SERIES.length];
        for (let k = 0; k < s.x.length; k++) if (s.y[k] !== null) { g.beginPath(); g.arc(f.X(s.x[k]), f.Y(s.y[k]), 2.4, 0, 6.2832); g.fill(); }
      }
    });
    g.restore();
    legend(g, w, d.series.map((s) => s.name), f.m);
    if (d.truncated_series) note(g, w, h, "se muestran solo las primeras columnas");
  }

  function hist(canvas, d) {
    const { g, w, h } = setup(canvas);
    if (!d.counts.length) return note(g, w, h, "sin datos finitos");
    const xr = niceTicks(d.edges[0], d.edges[d.edges.length - 1]), yr = niceTicks(0, Math.max(...d.counts));
    yr.a = 0;
    const f = frame(g, w, h, xr, yr, "valor");
    g.fillStyle = SERIES[0]; g.strokeStyle = css("--panel");
    d.counts.forEach((c, i) => {
      const x0 = f.X(d.edges[i]), x1 = f.X(d.edges[i + 1]), y = f.Y(c);
      g.fillRect(x0, y, Math.max(1, x1 - x0), f.Y(0) - y); g.strokeRect(x0, y, Math.max(1, x1 - x0), f.Y(0) - y);
    });
    g.fillStyle = css("--muted"); g.textAlign = "left"; g.fillText("n = " + d.n, f.m.l + 6, f.m.t + 8);
  }

  function bar(canvas, d) {
    const { g, w, h } = setup(canvas);
    const [lo, hi] = extent(d.series.map((s) => s.y)), n = d.labels.length, k = d.series.length;
    const yr = niceTicks(Math.min(0, lo), Math.max(0, hi)), xr = { a: -0.5, b: n - 0.5, ticks: [] };
    const step = Math.max(1, Math.ceil(n / 12)); for (let i = 0; i < n; i += step) xr.ticks.push(i);
    const f = frame(g, w, h, xr, yr, "índice");
    const bw = (f.pw / n) * 0.8 / k, y0 = f.Y(0);
    d.series.forEach((s, j) => {
      g.fillStyle = SERIES[j % SERIES.length];
      s.y.forEach((v, i) => {
        if (v === null) return;
        const x = f.X(i - 0.4) + j * bw, y = f.Y(v);
        g.fillRect(x, Math.min(y, y0), Math.max(1, bw - 1), Math.abs(y0 - y));
      });
    });
    legend(g, w, d.series.map((s) => s.name), f.m);
    if (d.truncated) note(g, w, h, "gráfica recortada (primeras filas/columnas)");
  }

  /* mapa de color tipo viridis (interpolación entre paradas) */
  const STOPS = [[68, 1, 84], [59, 82, 139], [33, 145, 140], [94, 201, 98], [253, 231, 37]];
  function colormap(t) {
    t = Math.max(0, Math.min(1, t)) * (STOPS.length - 1);
    const i = Math.min(STOPS.length - 2, Math.floor(t)), u = t - i, a = STOPS[i], b = STOPS[i + 1];
    return [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u];
  }

  function image(canvas, d) {
    const { g, w, h } = setup(canvas);
    const bar = 16, pad = { l: 8, r: 64, t: 8, b: 8 };
    const aw = w - pad.l - pad.r, ah = h - pad.t - pad.b;
    const sc = Math.min(aw / d.cols, ah / d.rows), iw = d.cols * sc, ih = d.rows * sc;
    const off = document.createElement("canvas"); off.width = d.cols; off.height = d.rows;
    const og = off.getContext("2d"), img = og.createImageData(d.cols, d.rows);
    const span = d.vmax - d.vmin || 1;
    for (let i = 0; i < d.data.length; i++) {
      const v = d.data[i], c = v === null ? [128, 128, 128] : colormap((v - d.vmin) / span);
      img.data[i * 4] = c[0]; img.data[i * 4 + 1] = c[1]; img.data[i * 4 + 2] = c[2]; img.data[i * 4 + 3] = 255;
    }
    og.putImageData(img, 0, 0);
    g.imageSmoothingEnabled = false;
    g.drawImage(off, pad.l, pad.t, iw, ih);
    const bx = pad.l + iw + 10;
    for (let y = 0; y < ih; y++) { const c = colormap(1 - y / ih); g.fillStyle = `rgb(${c[0]|0},${c[1]|0},${c[2]|0})`; g.fillRect(bx, pad.t + y, bar, 1); }
    g.fillStyle = css("--muted"); g.textAlign = "left"; g.textBaseline = "middle";
    g.fillText(tickLabel(d.vmax), bx + bar + 4, pad.t + 6);
    g.fillText(tickLabel(d.vmin), bx + bar + 4, pad.t + ih - 6);
    if (d.step[0] > 1 || d.step[1] > 1) note(g, w, h, `submuestreado ${d.step[0]}×${d.step[1]}`);
  }

  function note(g, w, h, text) {
    g.fillStyle = css("--muted"); g.textAlign = "center"; g.textBaseline = "middle";
    g.fillText(text, w / 2, h - 8);
  }

  function draw(canvas, d) {
    ({ line, hist, bar, image })[d.kind](canvas, d);
  }
  return { draw };
})();
