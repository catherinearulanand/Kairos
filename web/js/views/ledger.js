import { h, fmt } from "../util.js";
import { reducedMotion } from "../util.js";

export function renderLedger(root, data) {
  const rows = [...data.ledger].sort((a, b) => b.credits - a.credits || a.engine.localeCompare(b.engine));
  const total = rows.reduce((t, r) => ({ calls: t.calls + r.calls, credits: t.credits + r.credits, free: t.free + r.free }), { calls: 0, credits: 0, free: 0 });
  const max = Math.max(1, ...rows.map((r) => r.credits));

  const bars = [];
  const body = h("tbody", {}, rows.map((r) => {
    const fill = h("i");
    fill.style.width = `${(100 * r.credits) / max}%`;
    bars.push(fill);
    return h("tr", {},
      h("td", { class: "mono", text: r.engine }), h("td", { class: "mono", text: r.key_label || "n/a" }),
      h("td", { class: "r num", text: fmt.int(r.calls) }), h("td", { class: "r num", text: fmt.int(r.credits) }), h("td", { class: "r num", text: fmt.int(r.free) }),
      h("td", {}, h("div", { class: "bar-cell" }, h("div", { class: "bar" }, fill))));
  }));

  root.replaceChildren(h("div", { class: "page", "data-enter": "" },
    h("div", { class: "page-head" }, h("div", {}, h("h1", { text: "Credit ledger" }),
      h("div", { class: "meta" }, h("span", { text: data.source.mode === "demo" ? "Ledger of the committed demo captures" : "Ledger of stored live captures" }),
        h("span", { class: "sep" }), h("span", { text: "One row per engine and key label. Reused or cached requests cost nothing." })))),
    h("section", { class: "panel", "aria-label": "SerpApi usage" },
      rows.length ? h("div", { class: "tbl-wrap" }, h("table", { class: "tbl" },
        h("thead", {}, h("tr", {}, ["Engine", "Key", "Paid calls", "Credits", "Free", "Share of credits"].map((t, i) => h("th", { class: i >= 2 && i <= 4 ? "r" : "", text: t })))),
        body,
        h("tfoot", {}, h("tr", {}, h("td", { class: "name", text: "Total" }), h("td"), h("td", { class: "r num name", text: fmt.int(total.calls) }),
          h("td", { class: "r num name", text: fmt.int(total.credits) }), h("td", { class: "r num name", text: fmt.int(total.free) }), h("td")))))
        : h("div", { class: "empty" }, h("h2", { text: "No calls recorded" }), h("p", {}, "Run ", h("code", { text: "kairos snapshot --entity NYKAA --dry-run" }), " to see the planned cost before spending any credits.")))));

  if (!reducedMotion()) bars.forEach((b, i) => b.animate([{ transform: "scaleX(0)" }, { transform: "none" }], { duration: 520, delay: 80 + i * 40, easing: "cubic-bezier(0.16, 1, 0.3, 1)", fill: "backwards" }));
}
