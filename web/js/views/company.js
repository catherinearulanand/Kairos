import { h, clear, fmt, deltaNode, fadeIn, safeUrl, icon } from "../util.js";
import { readings, alertFor, RULES, SENSORS } from "../model.js";
import { lineChart, sparkline, divergenceMap, tickStrip } from "../charts.js";
import { chip, alertItem, openEvidence } from "./shared.js";

let range = 26;
const RANGES = [12, 26, 52];

export function renderCompany(root, data, entity) {
  const r = readings(entity);
  const r1 = alertFor(entity, "R1");
  const page = h("div", { class: "page", "data-enter": "" });
  const statusNotes = Object.entries(entity.collection_status || {}).filter(([, o]) => o.status !== "ok");

  const rangeSeg = h("div", { class: "seg", role: "group", "aria-label": "Chart range" },
    RANGES.map((n) => h("button", { type: "button", "aria-pressed": String(n === range), on: { click: () => { range = n; syncRange(); drawMain(); } } }, `${n}W`)));
  const syncRange = () => [...rangeSeg.children].forEach((b, i) => b.setAttribute("aria-pressed", String(RANGES[i] === range)));

  page.append(
    h("div", { class: "page-head" },
      h("div", {}, h("p", { class: "eyebrow", text: `Company file / ${entity.entity_id} / India` }), h("h1", { text: entity.name }),
        h("div", { class: "meta" },
          h("span", { class: "tag", text: entity.nse_ticker }),
          h("span", { class: "sep" }),
          h("span", { text: `${entity.sensors.length} of 5 sensors reporting` }),
          h("span", { class: "sep" }),
          h("span", { text: entity.verified_by ? `Identifiers verified by ${entity.verified_by}` : "Identifiers not yet verified" }))),
      h("div", { class: "head-actions" }, rangeSeg)),
    ...statusNotes.map(([sid, o]) => h("div", { class: "notice", role: "note" }, h("span", {}, h("b", { text: `${SENSORS[sid]?.name || sid}: ` }), `latest collection ${o.status} at ${fmt.dateTime(o.started_at)}. Readings below come from an earlier successful capture.`))));

  // ---- main chart --------------------------------------------------------------------
  const readout = h("div", { class: "readout", "aria-live": "off" });
  const legend = h("div", { class: "legend" });
  const chartHost = h("div");
  const chartPanel = h("section", { class: "panel chart-panel col-8", "aria-label": "Price against search share" },
    h("div", { class: "panel-head" }, h("h2", { class: "panel-title", text: "Price vs search share" }),
      h("span", { class: "panel-meta", text: "Weekly. Search share is a relative index across the tracked brand basket." })),
    readout, legend, chartHost,
    h("p", { class: "chart-hint", text: "Hover or use the arrow keys to read a week. Click a point to open the SerpApi response behind it." }));

  let chart = null;
  const seriesFor = () => {
    const out = [];
    if (r.price) out.push({ key: "price", label: "Price", axis: "l", cls: "a", fmt: (v) => fmt.inr(v), axisFmt: (v) => fmt.num(v, 0), points: r.price.series.points });
    if (r.share) out.push({ key: "share", label: "Search share", axis: "r", cls: "b", fmt: (v) => fmt.pct(v), axisFmt: (v) => `${fmt.num(v, 0)}%`, points: r.share.series.points });
    return out.map((sx) => ({ ...sx, points: sx.points.slice(-range).map((p) => ({ t: Date.parse(p.week), v: p.value, id: p.capture_id, week: p.week })) }));
  };

  function setReadout(info) {
    const ser = seriesFor();
    const items = info ? info.items : ser.map((sx) => { const p = sx.points[sx.points.length - 1]; return { label: sx.label, cls: sx.cls, value: sx.fmt(p.v) }; });
    const when = info ? `Week of ${fmt.dayYear(new Date(info.t))}` : `Latest week: ${fmt.dayYear(ser[0].points[ser[0].points.length - 1].week)}`;
    clear(readout).append(h("span", { class: "when", text: when }),
      ...items.map((it) => h("span", { class: "item" }, h("span", { text: it.label }), h("span", { class: "val", text: it.value }))));
  }

  function drawMain() {
    chart && chart.destroy();
    const ser = seriesFor();
    clear(legend);
    clear(chartHost);
    if (!ser.length) {
      chartHost.append(h("div", { class: "empty" }, h("h2", { text: "No weekly series yet" }), h("p", { text: "Run a snapshot to capture Google Trends and Google Finance for this company." })));
      return;
    }
    ser.forEach((sx) => legend.append(h("button", { class: "legend-btn", type: "button", title: "Open the latest capture", on: { click: () => openEvidence(entity, [sx.points[sx.points.length - 1].id], `${sx.label}, latest capture`, entity.name) } },
      h("span", { class: `swatch ${sx.cls}` }), `${sx.label} (${sx.axis === "l" ? "left axis" : "right axis"})`)));
    const bands = [];
    if (r1 && r1.windows.search_recent && range >= 12) {
      bands.push({ from: Date.parse(r1.windows.search_baseline[0]), to: Date.parse(r1.windows.search_recent[0]), cls: "band-baseline", label: "Baseline, 8 weeks", short: "Baseline" });
      bands.push({ from: Date.parse(r1.windows.search_recent[0]), to: Date.parse(r1.as_of), cls: "band-recent", label: "Recent, 4 weeks", short: "Recent" });
    }
    chart = lineChart(chartHost, { height: 330, series: ser, bands, summary: `${entity.name} price and search share, last ${range} weeks`,
      onReadout: setReadout, onPick: (key, p) => openEvidence(entity, [p.id], `${ser.find((x) => x.key === key).label}, week of ${fmt.dayYear(p.week)}`, entity.name) });
    setReadout(null);
  }

  // ---- R1 panel ---------------------------------------------------------------------
  const mapHost = h("div");
  const ticksHost = h("div");
  const r1Panel = h("section", { class: "panel r1-panel col-4", "aria-label": "Headline rule R1" },
    h("div", { class: "panel-head" }, h("h2", { class: "panel-title", text: "R1: search share vs price" }), r1 ? chip(r1.status) : null),
    h("div", { class: "panel-body stack" },
      r1 ? h("p", { class: "alert-sentence", text: r1.sentence }) : h("p", { class: "alert-sentence", text: "R1 has not been evaluated for this company." }),
      entity.r1_history.length ? [
        h("div", {}, h("div", { class: "insp-sub", text: "Every week of this capture, plotted against the firing zones" }), mapHost),
        h("div", {}, h("div", { class: "insp-sub", text: r1 && r1.base_rate ? `Base rate: true in ${r1.base_rate.n} of ${r1.base_rate.m} evaluable weeks` : "Base rate unavailable" }), ticksHost),
      ] : null),
    h("div", { class: "panel-foot", text: "Thresholds live in rules.yaml and are starting heuristics. R1 reports a divergence; it does not predict prices." }));

  const gridTop = h("div", { class: "grid" }, chartPanel, r1Panel);
  page.append(gridTop);

  // ---- instruments ------------------------------------------------------------------
  page.append(instruments(entity, r));

  // ---- alerts + headlines -----------------------------------------------------------
  const alertsList = h("ul", { class: "alerts" }, entity.alerts.map((a) => alertItem(a, entity, { open: a.status === "fired" })));
  const heads = entity.headlines.slice(0, 10);
  page.append(h("div", { class: "grid" },
    h("section", { class: "panel col-7", "aria-label": "Rule evaluations" },
      h("div", { class: "panel-head" }, h("h2", { class: "panel-title", text: "Rule evaluations" }),
        h("span", { class: "panel-meta", text: `${entity.alerts.filter((a) => a.status === "fired").length} fired of ${entity.alerts.length}` })), alertsList),
    h("section", { class: "panel col-5", "aria-label": "News headlines" },
      h("div", { class: "panel-head" }, h("h2", { class: "panel-title", text: "Headlines" }), h("span", { class: "panel-meta", text: "Context only, never a signal" })),
      heads.length ? h("ul", { class: "headlines" }, heads.map((n) => { const url = safeUrl(n.link);
        return h("li", {}, url ? h("a", { href: url, target: "_blank", rel: "noopener noreferrer", text: n.title }) : h("span", { text: n.title }),
          h("div", { class: "by", text: `${n.source || "Unknown source"} · ${fmt.day(n.observed_at)}` })); }))
        : h("div", { class: "empty" }, h("p", { text: "No headlines captured." })))));

  root.replaceChildren(page);
  drawMain();
  if (entity.r1_history.length) {
    divergenceMap(mapHost, { history: entity.r1_history, thresholds: data.rules.R1 });
    tickStrip(ticksHost, entity.r1_history);
  }
  return () => chart && chart.destroy();
}

function instruments(entity, r) {
  const rows = [];
  const add = (name, proxy, latest, change, trend, basis, captured, ids, title) => rows.push({ name, proxy, latest, change, trend, basis, captured, ids, title });

  if (r.share) add("Search share", r.share.series.label, h("span", { class: "num", text: fmt.pct(r.share.last.value) }),
    deltaNode(r.share.wow, " wk/wk"), sparkline(r.share.series.points.slice(-26).map((p) => p.value), { cls: "b" }),
    `Week of ${fmt.day(r.share.last.week)} · 52 weekly values, one capture`, r.share.last.captured_at, [r.share.last.capture_id], "Search share");
  if (r.price) add("Price", r.price.series.label, h("span", { class: "num", text: fmt.inr(r.price.last.value) }),
    deltaNode(r.price.wow, " wk/wk"), sparkline(r.price.series.points.slice(-26).map((p) => p.value)),
    `Week of ${fmt.day(r.price.last.week)} · last close of the week`, r.price.last.captured_at, [r.price.last.capture_id], "Price");
  if (r.reviews) add("App reviews", "Recent review sample against the store's displayed rating", h("span", { class: "num", text: `${fmt.num(r.reviews.mean.value, 2)} ★` }),
    h("span", { class: "delta" }, `${fmt.signed(r.reviews.gap, 2)} vs ${fmt.num(r.reviews.shown.value, 1)} shown`),
    h("span", { class: "insp-sub", text: "Point in time" }),
    `n=${fmt.int(r.reviews.n)} · ${fmt.day(r.reviews.from)} to ${fmt.day(r.reviews.to)}`, r.reviews.mean.captured_at,
    [r.reviews.mean.capture_id, r.reviews.shown.capture_id], "App reviews");
  if (r.ads) add("Ad creatives", "Active creatives in two 14-day windows (a proxy for activity)",
    h("span", { class: "num", text: `${r.ads.recentCapped ? "≥" : ""}${fmt.int(r.ads.recent.value)}` }),
    h("span", { class: "delta" }, r.ads.ratio != null ? `${fmt.num(r.ads.ratio, 2)}× prior` : r.ads.capped ? "Count limit reached" : "No comparison"),
    h("span", { class: "insp-sub", text: "Two windows" }),
    `${fmt.dayYear(`${r.ads.recent.dims.start_date.slice(0, 4)}-${r.ads.recent.dims.start_date.slice(4, 6)}-${r.ads.recent.dims.start_date.slice(6)}`)} onward`,
    r.ads.recent.captured_at, [r.ads.recent.capture_id, r.ads.prior && r.ads.prior.capture_id].filter(Boolean), "Ad creatives");
  if (r.news.lastWeek || r.news.headlines) add("News flow", SENSORS.news.engine + ": headlines for context", h("span", { class: "num", text: r.news.lastWeek ? fmt.int(r.news.lastWeek.value) : "n/a" }),
    h("span", { class: "delta na", text: "per week" }), r.news.series ? sparkline(r.news.series.points.map((p) => p.value), { w: 84 }) : h("span", { class: "insp-sub", text: "n/a" }),
    `${r.news.headlines} headlines in the capture`, (entity.headlines[0] || {}).captured_at, entity.headlines[0] ? [entity.headlines[0].capture_id] : [], "News flow");

  const body = h("tbody", {}, rows.map((x, i) => {
    const tr = h("tr", {},
      h("td", { class: "inst" }, h("span", { class: "name", text: x.name }), h("span", { class: "sub proxy", text: x.proxy })),
      h("td", { class: "r" }, x.latest), h("td", { class: "r" }, x.change), h("td", {}, x.trend),
      h("td", {}, h("span", { class: "sub", text: x.basis })),
      h("td", { class: "r" }, h("span", { class: "sub", text: x.captured ? fmt.dateTime(x.captured) : "n/a" })),
      h("td", { class: "r" }, h("button", { class: "ev-btn", type: "button", "aria-label": `Open evidence for ${x.name}`, on: { click: () => openEvidence(entity, x.ids, `${x.title}, latest capture`, entity.name) } }, "Inspect", icon("arrow", 12))));
    fadeIn(tr, 240, 120 + i * 40);
    return tr;
  }));
  return h("section", { class: "panel", "aria-label": "Sensors" },
    h("div", { class: "panel-head" }, h("h2", { class: "panel-title", text: "Sensors" }), h("span", { class: "panel-meta", text: "Latest reading from each SerpApi engine" })),
    h("div", { class: "tbl-wrap" }, h("table", { class: "tbl" },
      h("thead", {}, h("tr", {}, ["Sensor", "Latest", "Change", "26 weeks", "Basis", "Captured", ""].map((t, i) => h("th", { class: i === 1 || i === 2 || i >= 5 ? "r" : "", text: t })))),
      body)));
}
