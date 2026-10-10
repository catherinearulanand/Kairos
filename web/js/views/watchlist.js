import { h, fmt, deltaNode, fadeIn } from "../util.js";
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
  root.replaceChildren(h("div", { class: "page", "data-enter": "" },
    h("div", { class: "page-head" },
      h("div", {}, h("h1", { text: "Watchlist" }),
        h("div", { class: "meta" },
          h("span", { text: `${data.entities.length} companies` }), h("span", { class: "sep" }),
          h("span", { text: `${fired} of ${data.entities.flatMap((e) => e.alerts).length} rule evaluations fired` }),
          last ? [h("span", { class: "sep" }), h("span", { text: `Latest capture ${fmt.dateTime(last)}` })] : null))),
    h("p", { class: "alert-sentence", text: "Search share from Google Trends against the share price from Google Finance, with app-review, ad and news context. Open a company, then any number, to see the stored SerpApi response behind it." }),
    h("section", { class: "panel", "aria-label": "Tracked companies" },
      h("div", { class: "tbl-wrap" }, h("table", { class: "tbl" }, h("thead", {}, head), tbody)))));
}
