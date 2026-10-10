// Hand-rolled SVG charts. No dependencies, so the terminal works offline and every pixel is
// accounted for. Colours come from CSS classes (theme-aware); CSP forbids inline styles.

import { s, h, fmt, drawIn, fadeIn, reducedMotion } from "./util.js";

const MARGIN = { l: 56, r: 56, t: 14, b: 28 };

function niceStep(raw) {
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * mag >= raw) return m * mag;
  return 10 * mag;
}

/** A scale with exactly `intervals` equal steps so left and right gridlines line up. */
export function axisScale(values, intervals = 4) {
  let lo = Math.min(...values), hi = Math.max(...values);
  const pad = (hi - lo) * 0.1 || Math.abs(hi) * 0.05 || 1;
  lo -= pad; hi += pad;
  let step = niceStep((hi - lo) / intervals);
  let start = Math.floor(lo / step) * step;
  while (start + intervals * step < hi) { step = niceStep(step * 1.01); start = Math.floor(lo / step) * step; }
  const ticks = Array.from({ length: intervals + 1 }, (_, i) => start + i * step);
  return { min: ticks[0], max: ticks[intervals], ticks };
}

const nearest = (arr, t) => {
  let best = 0;
  for (let i = 1; i < arr.length; i++) if (Math.abs(arr[i] - t) < Math.abs(arr[best] - t)) best = i;
  return best;
};

/**
 * Dual-axis time series. cfg = {height, series:[{key,label,axis,cls,fmt,points:[{t,v,id}]}],
 * bands:[{from,to,cls,label}], summary, onReadout(info), onPick(key, point)}.
 */
export function lineChart(host, cfg) {
  const state = { idx: -1, animate: true };
  host.classList.add("chart");
  host.setAttribute("tabindex", "0");
  host.setAttribute("role", "group");
  host.setAttribute("aria-label", `${cfg.summary}. Use the left and right arrow keys to move through weeks.`);
  const tip = h("div", { class: "tip", "aria-hidden": "true" });
  let svg = null;
  let times = [];

  function draw() {
    const W = Math.max(320, Math.floor(host.clientWidth));
    const H = cfg.height;
    const plot = { x0: MARGIN.l, x1: W - MARGIN.r, y0: MARGIN.t, y1: H - MARGIN.b };
    const all = cfg.series.flatMap((x) => x.points.map((p) => p.t));
    const t0 = Math.min(...all), t1 = Math.max(...all);
    const xs = (t) => plot.x0 + ((t - t0) / (t1 - t0 || 1)) * (plot.x1 - plot.x0);
    const scales = {};
    for (const ax of ["l", "r"]) {
      const vals = cfg.series.filter((x) => x.axis === ax).flatMap((x) => x.points.map((p) => p.v));
      if (vals.length) scales[ax] = axisScale(vals);
    }
    const ys = (ax, v) => plot.y1 - ((v - scales[ax].min) / (scales[ax].max - scales[ax].min)) * (plot.y1 - plot.y0);

    const g = s("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, "aria-hidden": "true", focusable: "false" });

    for (const b of cfg.bands || []) {
      const x0 = Math.max(plot.x0, xs(b.from)), x1 = Math.min(plot.x1, xs(b.to));
      if (x1 <= x0) continue;
      const room = x1 - x0 - 12;                 // pick the longest label that fits, or none
      const label = [b.label, b.short].find((t) => t && t.length * 6.2 <= room);
      const band = s("g", {}, s("rect", { class: b.cls, x: x0, y: plot.y0, width: x1 - x0, height: plot.y1 - plot.y0 }),
        label ? s("text", { class: "band-label", x: x0 + 6, y: plot.y0 + 13, text: label }) : null);
      if (state.animate) fadeIn(band, 400, 150);
      g.append(band);
    }

    const left = scales.l || scales.r;
    left.ticks.forEach((tick, i) => {
      const y = plot.y1 - (i / (left.ticks.length - 1)) * (plot.y1 - plot.y0);
      g.append(s("line", { class: i === 0 ? "axis" : "gl", x1: plot.x0, x2: plot.x1, y1: y, y2: y }));
      const lf = cfg.series.find((x) => x.axis === (scales.l ? "l" : "r"));
      g.append(s("text", { x: plot.x0 - 8, y: y + 4, "text-anchor": "end", class: scales.l ? "tl-a" : "tl-b", text: lf.axisFmt(tick) }));
      if (scales.l && scales.r) {
        const rf = cfg.series.find((x) => x.axis === "r");
        g.append(s("text", { x: plot.x1 + 8, y: y + 4, class: "tl-b", text: rf.axisFmt(scales.r.ticks[i]) }));
      }
    });

    const span = plot.x1 - plot.x0;
    const labelTimes = [...new Set(cfg.series[0].points.map((p) => p.t))];
    const every = Math.ceil(labelTimes.length / Math.max(2, Math.floor(span / 70)));
    labelTimes.forEach((t, i) => {
      if ((labelTimes.length - 1 - i) % every !== 0) return;
      g.append(s("text", { x: xs(t), y: H - 8, "text-anchor": "middle", text: fmt.day(new Date(t)) }));
    });

    const paths = [];
    for (const ser of cfg.series) {
      const ax = ser.axis;
      const d = ser.points.map((p, i) => `${i ? "L" : "M"}${xs(p.t).toFixed(1)},${ys(ax, p.v).toFixed(1)}`).join("");
      const path = s("path", { class: `ln ${ser.cls}`, d });
      g.append(path); paths.push(path);
      const lp = ser.points[ser.points.length - 1];
      const dot = s("circle", { class: `dot ${ser.cls}`, cx: xs(lp.t), cy: ys(ax, lp.v), r: 4 });
      g.append(dot);
      if (state.animate) { drawIn(path, 760); fadeIn(dot, 200, 700); }
    }

    const xhair = s("line", { class: "xhair", y1: plot.y0, y2: plot.y1, visibility: "hidden" });
    const hdots = cfg.series.map((x) => s("circle", { class: `dot ${x.cls}`, r: 4.5, visibility: "hidden" }));
    g.append(xhair, ...hdots);
    const overlay = s("rect", { x: plot.x0, y: plot.y0, width: plot.x1 - plot.x0, height: plot.y1 - plot.y0, fill: "transparent" });
    g.append(overlay);

    times = [...new Set(cfg.series[0].points.map((p) => p.t))];
    const pointAt = (ser, t) => {
      const i = nearest(ser.points.map((p) => p.t), t);
      return Math.abs(ser.points[i].t - t) <= 4 * 864e5 ? ser.points[i] : null;
    };

    function show(i, clientY) {
      state.idx = i;
      const t = times[i];
      const x = xs(t);
      xhair.setAttribute("x1", x); xhair.setAttribute("x2", x); xhair.setAttribute("visibility", "visible");
      const items = [];
      cfg.series.forEach((ser, k) => {
        const p = pointAt(ser, t);
        if (p) { hdots[k].setAttribute("cx", x); hdots[k].setAttribute("cy", ys(ser.axis, p.v)); hdots[k].setAttribute("visibility", "visible"); }
        else hdots[k].setAttribute("visibility", "hidden");
        items.push({ key: ser.key, label: ser.label, cls: ser.cls, value: p ? ser.fmt(p.v) : "no reading", point: p });
      });
      cfg.onReadout && cfg.onReadout({ t, items });
      tip.replaceChildren(h("div", { class: "t-when", text: `Week of ${fmt.dayYear(new Date(t))}` }),
        ...items.map((it) => h("div", { class: "t-row" }, h("span", { text: it.label }), h("span", { text: it.value }))));
      tip.dataset.on = "true";
      const tw = 170;
      tip.style.left = `${x + 14 + tw > W ? x - 14 - tw : x + 14}px`;
      tip.style.top = `${plot.y0 + 8}px`;
    }
    function hide() {
      state.idx = -1;
      xhair.setAttribute("visibility", "hidden");
      hdots.forEach((d) => d.setAttribute("visibility", "hidden"));
      tip.dataset.on = "false";
      cfg.onReadout && cfg.onReadout(null);
    }
    const indexAt = (ev) => {
      const r = overlay.getBoundingClientRect();
      const t = t0 + ((ev.clientX - r.left) / r.width) * (t1 - t0);
      return nearest(times, t);
    };
    overlay.addEventListener("pointermove", (ev) => show(indexAt(ev), ev.clientY));
    overlay.addEventListener("pointerleave", hide);
    overlay.addEventListener("click", (ev) => {
      const i = indexAt(ev), t = times[i];
      const r = overlay.getBoundingClientRect();
      const py = ev.clientY - r.top + plot.y0;
      let best = null;
      for (const ser of cfg.series) {
        const p = pointAt(ser, t);
        if (!p) continue;
        const dy = Math.abs(ys(ser.axis, p.v) - py);
        if (!best || dy < best.dy) best = { ser, p, dy };
      }
      if (best) cfg.onPick && cfg.onPick(best.ser.key, best.p);
    });
    host.onkeydown = (ev) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End", "Enter", "Escape"].includes(ev.key)) return;
      ev.preventDefault();
      let i = state.idx < 0 ? times.length - 1 : state.idx;
      if (ev.key === "ArrowLeft") i = Math.max(0, i - 1);
      if (ev.key === "ArrowRight") i = Math.min(times.length - 1, i + 1);
      if (ev.key === "Home") i = 0;
      if (ev.key === "End") i = times.length - 1;
      if (ev.key === "Escape") return hide();
      if (ev.key === "Enter") {
        const p = pointAt(cfg.series[0], times[i]);
        if (p) cfg.onPick && cfg.onPick(cfg.series[0].key, p);
        return;
      }
      show(i);
    };
    host.onblur = hide;

    svg && svg.remove();
    svg = g;
    host.prepend(svg);
    if (!tip.isConnected) host.append(tip);
  }

  draw();
  let raf = 0, lastW = host.clientWidth;
  const ro = new ResizeObserver(() => {
    if (Math.abs(host.clientWidth - lastW) < 2) return;
    lastW = host.clientWidth;
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(() => { state.animate = false; draw(); });
  });
  ro.observe(host);
  return { destroy() { ro.disconnect(); cancelAnimationFrame(raf); } };
}

export function sparkline(values, { w = 84, h: hh = 24, cls = "", dot = true, animate = true } = {}) {
  const pts = values.filter((v) => v != null);
  const svg = s("svg", { class: "spark", viewBox: `0 0 ${w} ${hh}`, width: w, height: hh, "aria-hidden": "true", focusable: "false" });
  if (pts.length < 2) return svg;
  const lo = Math.min(...pts), hi = Math.max(...pts), rng = hi - lo || 1;
  const x = (i) => 2 + (i / (pts.length - 1)) * (w - 4);
  const y = (v) => hh - 3 - ((v - lo) / rng) * (hh - 6);
  const path = s("path", { class: cls, d: pts.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("") });
  svg.append(path);
  if (dot) svg.append(s("circle", { class: cls, cx: x(pts.length - 1), cy: y(pts[pts.length - 1]), r: 2 }));
  if (animate) drawIn(path, 600);
  return svg;
}

/** Share change (x) against price return (y), one point per week, with R1's firing zones. */
export function divergenceMap(host, { history, thresholds, onPick }) {
  host.classList.add("chart", "map");
  const W = Math.max(260, Math.floor(host.clientWidth)), H = 292;
  const M = { l: 46, r: 10, t: 10, b: 38 };
  const evald = history.filter((p) => p.status !== "insufficient");
  const ts = thresholds.share_change_pct, tp = thresholds.price_return_pct;
  const X = Math.max(ts * 1.4, ...evald.map((p) => Math.abs(p.share_change)), 0) * 1.1;
  const Y = Math.max(tp * 1.5, ...evald.map((p) => Math.abs(p.price_return)), 0) * 1.1;
  const xs = (v) => M.l + ((v + X) / (2 * X)) * (W - M.l - M.r);
  const ys = (v) => M.t + ((Y - v) / (2 * Y)) * (H - M.t - M.b);
  const svg = s("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": `Divergence map: ${evald.length} evaluable weeks of search share change against price return; ${evald.filter((p) => p.status === "fired").length} fired.` });
  svg.append(
    s("rect", { class: "zone", x: M.l, y: M.t, width: xs(-ts) - M.l, height: ys(tp) - M.t }),
    s("rect", { class: "zone", x: xs(ts), y: ys(-tp), width: W - M.r - xs(ts), height: H - M.b - ys(-tp) }),
    s("text", { class: "zone-label", x: M.l + 6, y: M.t + 15, text: "R1 fires" }),
    s("text", { class: "zone-label", x: W - M.r - 6, y: H - M.b - 8, "text-anchor": "end", text: "R1 fires" }),
    s("line", { class: "zero", x1: xs(0), x2: xs(0), y1: M.t, y2: H - M.b }),
    s("line", { class: "zero", x1: M.l, x2: W - M.r, y1: ys(0), y2: ys(0) }),
  );
  for (const v of [-ts, ts]) svg.append(s("line", { class: "thr", x1: xs(v), x2: xs(v), y1: M.t, y2: H - M.b }));
  for (const v of [-tp, tp]) svg.append(s("line", { class: "thr", x1: M.l, x2: W - M.r, y1: ys(v), y2: ys(v) }));
  for (const v of [-ts, 0, ts]) svg.append(s("text", { x: xs(v), y: H - M.b + 14, "text-anchor": "middle", text: v === 0 ? "0" : fmt.signed(v, 0) }));
  for (const v of [-tp, 0, tp]) svg.append(s("text", { x: M.l - 6, y: ys(v) + 4, "text-anchor": "end", text: v === 0 ? "0" : fmt.signed(v, 0) }));
  svg.append(
    s("text", { class: "axis-title", x: (M.l + W - M.r) / 2, y: H - 6, "text-anchor": "middle", text: "Search share change, 4 weeks vs prior 8 (%)" }),
    s("text", { class: "axis-title", transform: `translate(12 ${(M.t + H - M.b) / 2}) rotate(-90)`, "text-anchor": "middle", text: "Price return, 4 weeks (%)" }),
  );

  const tip = h("div", { class: "tip", "aria-hidden": "true" });
  const dots = [];
  evald.forEach((p, i) => {
    const c = s("circle", { class: `pt ${p.status === "fired" ? "fired" : ""}`, cx: xs(p.share_change), cy: ys(p.price_return), r: 3.2 });
    c.addEventListener("pointerenter", () => {
      tip.replaceChildren(h("div", { class: "t-when", text: `Week of ${fmt.dayYear(p.week)}` }),
        h("div", { class: "t-row" }, h("span", { text: "Search share" }), h("span", { text: `${fmt.signed(p.share_change)}%` })),
        h("div", { class: "t-row" }, h("span", { text: "Price" }), h("span", { text: `${fmt.signed(p.price_return)}%` })));
      const px = xs(p.share_change), py = ys(p.price_return);
      tip.style.left = `${px + 160 > W ? px - 164 : px + 10}px`;
      tip.style.top = `${Math.max(4, py - 30)}px`;
      tip.dataset.on = "true";
    });
    c.addEventListener("pointerleave", () => { tip.dataset.on = "false"; });
    dots.push(c); svg.append(c);
    if (!reducedMotion() && c.animate) c.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 260, delay: 120 + i * 9, easing: "ease-out", fill: "backwards" });
  });
  const cur = evald[evald.length - 1];
  if (cur) {
    const cx = xs(cur.share_change), cy = ys(cur.price_return);
    const ring = s("circle", { class: "ring", cx, cy, r: 8 });
    svg.append(ring, s("circle", { class: "now", cx, cy, r: 5 }));
    if (!reducedMotion() && ring.animate) ring.animate([{ transform: "scale(0.4)", opacity: 0.9 }, { transform: "scale(1.6)", opacity: 0 }],
      { duration: 1100, delay: 700, iterations: 2, easing: "cubic-bezier(0.25, 1, 0.5, 1)", fill: "backwards" });
  }
  host.replaceChildren(svg, tip);
  return { current: cur };
}

/** One tick per week: tall and red where the rule fired, short grey where it did not, hollow where it could not run. */
export function tickStrip(host, history) {
  const W = Math.max(240, Math.floor(host.clientWidth)), H = 30;
  const n = history.length, gap = 2, bw = Math.max(2, (W - gap * (n - 1)) / n);
  const svg = s("svg", { class: "ticks", width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": `Weekly R1 results: ${history.filter((p) => p.status === "fired").length} fired, ${history.filter((p) => p.status === "not_fired").length} not fired, ${history.filter((p) => p.status === "insufficient").length} without enough data.` });
  history.forEach((p, i) => {
    const hh = p.status === "fired" ? H : 11;
    const r = s("rect", { class: p.status === "fired" ? "fired" : p.status === "insufficient" ? "na" : "", x: i * (bw + gap), y: H - hh, width: bw, height: hh, rx: 1 },
      s("title", { text: `Week of ${fmt.dayYear(p.week)}: ${p.status.replace("_", " ")}` }));
    if (!reducedMotion() && r.animate) r.animate([{ transform: "scaleY(0)" }, { transform: "none" }], { duration: 300, delay: i * 7, easing: "cubic-bezier(0.25, 1, 0.5, 1)", fill: "backwards" });
    svg.append(r);
  });
  host.replaceChildren(svg);
}
