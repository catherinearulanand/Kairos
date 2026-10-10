import { h, clear } from "../util.js";
import { RULES, STATUS } from "../model.js";
import { alertItem } from "./shared.js";

const filter = { status: "all", rule: "all", entity: "all" };

export function renderAlerts(root, data, focusId) {
  const all = data.entities.flatMap((e) => e.alerts.map((a) => ({ a, e })));
  const list = h("ul", { class: "alerts" });
  const tally = h("p", { class: "tally", "aria-live": "polite" });

  const seg = (key, label, options) => h("div", { class: "filters" }, h("span", { class: "tally", text: label }),
    h("div", { class: "seg", role: "group", "aria-label": label },
      options.map(([value, text]) => h("button", { type: "button", "aria-pressed": String(filter[key] === value), on: { click: (ev) => {
        filter[key] = value;
        [...ev.currentTarget.parentElement.children].forEach((b) => b.setAttribute("aria-pressed", String(b === ev.currentTarget)));
        paint();
      } } }, text))));

  function paint() {
    const shown = all.filter(({ a, e }) => (filter.status === "all" || a.status === filter.status)
      && (filter.rule === "all" || a.rule_id === filter.rule) && (filter.entity === "all" || e.entity_id === filter.entity));
    const count = (s) => shown.filter(({ a }) => a.status === s).length;
    clear(tally).append(h("b", { class: "num", text: String(shown.length) }), " shown: ",
      h("b", { class: "num", text: String(count("fired")) }), " fired · ", h("b", { class: "num", text: String(count("not_fired")) }), " not fired · ",
      h("b", { class: "num", text: String(count("insufficient")) }), " without enough data");
    clear(list);
    if (!shown.length) { list.append(h("li", { class: "empty" }, h("h2", { text: "Nothing matches these filters" }), h("p", { text: "Clear a filter to see every evaluation." }))); return; }
    shown.forEach(({ a, e }) => list.append(alertItem(a, e, { showEntity: true, open: a.alert_id === focusId })));
    const target = focusId && list.querySelector(`[data-alert="${CSS.escape(focusId)}"]`);
    if (target) requestAnimationFrame(() => target.scrollIntoView({ block: "center" }));
  }

  root.replaceChildren(h("div", { class: "page", "data-enter": "" },
    h("div", { class: "page-head" }, h("div", {}, h("p", { class: "eyebrow", text: "The research desk / deterministic analysis" }), h("h1", { text: "Reading the signals." }),
      h("div", { class: "meta" }, h("span", { text: "Every rule, for every company, whether it fired or not. A rule without enough data says so and does not default to false." })))),
    h("div", { class: "filters" },
      seg("status", "Status", [["all", "All"], ...Object.entries(STATUS).map(([k, v]) => [k, v.label])]),
      seg("rule", "Rule", [["all", "All"], ...Object.entries(RULES).map(([k]) => [k, k])]),
      seg("entity", "Company", [["all", "All"], ...data.entities.map((e) => [e.entity_id, e.nse_ticker.split(":")[0]])])),
    tally,
    h("section", { class: "panel", "aria-label": "Rule evaluations" }, list)));
  paint();
}
