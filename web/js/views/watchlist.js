import { h, s, fmt, deltaNode, fadeIn } from "../util.js";
import { readings, alertFor, latestCapture } from "../model.js";
import { sparkline } from "../charts.js";
import { chip } from "./shared.js";

let sort = { key: "name", dir: 1 };

export function renderWatchlist(root, data) {
  const rows = data.entities.map((e) => ({ e, r: readings(e) }));
  const fired = data.entities.flatMap((e) => e.alerts).filter((a) => a.status === "fired").length;

  const COLS = [
    { key: "name", label: "Company", get: (x) => x.e.name },
    { key: "price", label: "Price", right: true, get: (x) => x.r.price?.last.value ?? -Infinity },
    { key: "pw", label: "Week", right: true, get: (x) => x.r.price?.wow ?? -Infinity },
    { key: "share", label: "Search share", right: true, get: (x) => x.r.share?.last.value ?? -Infinity },
    { key: "sw", label: "Week", right: true, get: (x) => x.r.share?.wow ?? -Infinity },
    { key: "gap", label: "Review gap", right: true, get: (x) => x.r.reviews?.gap ?? Infinity },
    { key: "ads", label: "Ad creatives", right: true, get: (x) => x.r.ads?.recent.value ?? -Infinity },
    { key: "trend", label: "Price, 26 wk", nosort: true },
    { key: "r1", label: "R1", get: (x) => alertFor(x.e, "R1")?.status || "" },
    { key: "r2", label: "R2", get: (x) => alertFor(x.e, "R2")?.status || "" },
    { key: "r3", label: "R3", get: (x) => alertFor(x.e, "R3")?.status || "" },
  ];

  const tbody = h("tbody");
  const head = h("tr");

  function paint(animate) {
    const col = COLS.find((c) => c.key === sort.key);
    const sorted = [...rows].sort((a, b) => { const x = col.get(a), y = col.get(b); return (x < y ? -1 : x > y ? 1 : 0) * sort.dir; });
    tbody.replaceChildren(...sorted.map(({ e, r }, i) => {
      const href = `#/company/${e.entity_id}`;
      const tr = h("tr", { "data-href": href, on: { click: (ev) => { if (!ev.target.closest("a")) location.hash = href; } } },
        h("td", {}, h("a", { class: "name", href, text: e.name }), h("span", { class: "sub mono", text: e.nse_ticker })),
        h("td", { class: "r num", text: r.price ? fmt.inr(r.price.last.value) : "n/a" }),
        h("td", { class: "r" }, r.price ? deltaNode(r.price.wow) : h("span", { class: "delta na", text: "n/a" })),
        h("td", { class: "r num", text: r.share ? fmt.pct(r.share.last.value) : "n/a" }),
        h("td", { class: "r" }, r.share ? deltaNode(r.share.wow) : h("span", { class: "delta na", text: "n/a" })),
        h("td", { class: "r num", text: r.reviews ? `${fmt.signed(r.reviews.gap, 2)} ★` : "n/a" }),
        h("td", { class: "r num", text: r.ads ? `${r.ads.recentCapped ? "≥" : ""}${fmt.int(r.ads.recent.value)}` : "n/a" }),
        h("td", {}, r.price ? sparkline(r.price.series.points.slice(-26).map((p) => p.value), { animate }) : null),
        ...["R1", "R2", "R3"].map((id) => { const a = alertFor(e, id); return h("td", {}, a ? chip(a.status, { short: true }) : null); }));
      if (animate) fadeIn(tr, 240, 60 + i * 50);
      return tr;
    }));
    head.replaceChildren(...COLS.map((c) => {
      const th = h("th", { class: c.right ? "r" : "", scope: "col", "aria-sort": c.key === sort.key ? (sort.dir === 1 ? "ascending" : "descending") : null });
      th.append(c.nosort ? c.label : h("button", { type: "button", on: { click: () => { sort = { key: c.key, dir: sort.key === c.key ? -sort.dir : 1 }; paint(false); } } },
        c.label, h("span", { class: "sort", "aria-hidden": "true", text: c.key === sort.key && sort.dir === -1 ? "▼" : "▲" })));
      return th;
    }));
  }
  paint(true);

  const last = latestCapture(data);
  const contextFlags = data.entities.flatMap((e) => e.alerts).filter((a) => a.role === "context" && a.status === "fired").length;
  const engines = new Set(data.entities.flatMap((e) => e.sensors)).size;
  const stat = (n, label) => h("div", { class: "observatory-stat" }, h("strong", { text: String(n).padStart(2, "0") }), h("span", { text: label }));
  const orbital = s("svg", { viewBox: "0 0 360 190", "aria-hidden": "true", focusable: "false" },
    s("path", { class: "orbit-axis", d: "M20 95H340M180 12V178" }),
    ...[36, 59, 82].map((r) => s("circle", { class: "orbit", cx: 180, cy: 95, r })),
    s("ellipse", { class: "orbit", cx: 180, cy: 95, rx: 145, ry: 36, transform: "rotate(-22 180 95)" }),
    s("path", { class: "orbit-signal", d: "M25 148L85 126L135 119L180 95L221 72L277 64L335 25M25 148L85 126L135 119L180 95L226 106L280 136L335 144" }),
    ...[[180, 95], [277, 64], [280, 136]].map(([cx, cy]) => s("circle", { class: "orbit-dot", cx, cy, r: 3 })),
    s("text", { class: "orbit-label", x: 283, y: 52, text: "BEHAVIOUR" }),
    s("text", { class: "orbit-label", x: 286, y: 157, text: "PRICE" }));
  const cards = rows.map(({ e, r }, i) => h("a", { class: "company-card", href: `#/company/${e.entity_id}`, "aria-label": `Explore ${e.name}` },
    h("div", { class: "card-top" }, h("span", { class: "card-index", text: `${String(i + 1).padStart(2, "0")} / COMPANY FILE` }), h("span", { class: "card-arrow", "aria-hidden": "true", text: "↗" })),
    h("h3", { text: e.name }), h("div", { class: "card-ticker", text: e.nse_ticker }),
    h("div", { class: "card-reading" }, h("span", { class: "card-price", text: r.price ? fmt.inr(r.price.last.value) : "No price reading" }), r.price ? deltaNode(r.price.wow, " wk/wk") : null),
    h("div", { class: "card-chart", "aria-label": "Weekly closing prices, last 26 weeks" }, r.price ? sparkline(r.price.series.points.slice(-26).map((p) => p.value), { w: 300, h: 46, animate: false }) : null),
    h("div", { class: "card-foot" }, h("span", { text: `SEARCH SHARE ${r.share ? fmt.pct(r.share.last.value) : "n/a"}` }), chip(alertFor(e, "R1")?.status || "insufficient", { short: true }))));

  root.replaceChildren(h("div", { class: "page watch-page", "data-enter": "" },
    h("section", { class: "hero", "aria-label": "The alternative data observatory" },
      h("div", {}, h("p", { class: "eyebrow", text: "Independent signals / Indian equities" }),
        h("h1", {}, "Beyond", h("br"), h("em", { text: "the ticker." })),
        h("p", { class: "hero-copy", text: "Markets tell one story. People tell another. Follow the searches, reviews and ad activity behind listed companies—and inspect the evidence for yourself." }),
        h("div", { class: "hero-note" }, h("span", { class: "index-square", "aria-hidden": "true", text: "↗" }), h("span", { class: "eyebrow", text: "Five lenses. Every number sourced." }))),
      h("div", { class: "observatory" },
        h("div", { class: "observatory-top" }, h("span", { text: "K / THE OBSERVATORY" }), h("span", { text: "SIGNAL ≠ PRICE" })), orbital,
        h("div", { class: "observatory-bottom" }, stat(data.entities.length, "Companies"), stat(engines, "Sensors"), stat(contextFlags, "Context flags")))),
    h("section", { "aria-label": "Company files" },
      h("div", { class: "section-label" }, h("h2", { text: "01 / The company files" }), h("span", { text: "Weekly close · open a file to investigate" })),
      h("div", { class: "company-grid" }, cards)),
    h("section", { "aria-label": "Tracked companies" },
      h("div", { class: "section-label" }, h("h2", { text: "02 / The comparative view" }), h("span", { text: `${fired} of ${data.entities.flatMap((e) => e.alerts).length} rule evaluations fired` })),
      h("div", { class: "panel" }, h("div", { class: "tbl-wrap" }, h("table", { class: "tbl" }, h("thead", {}, head), tbody)))),
    h("p", { class: "section-stamp", text: last ? `LATEST CAPTURE / ${fmt.dateTime(last)} · STORED OBSERVATIONS, NOT LIVE QUOTES` : "NO CAPTURES YET" })));
}
