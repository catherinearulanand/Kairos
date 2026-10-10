import { h, icon, fmt, toast } from "../util.js";
import { RULES, STATUS, SENSORS, captureIndex } from "../model.js";
import { openInspector } from "../inspector.js";

export function chip(status, { short = false } = {}) {
  const m = STATUS[status] || STATUS.insufficient;
  const label = short && status === "insufficient" ? "No data" : m.label;
  return h("span", { class: `chip ${m.cls}`, title: m.label }, status === "fired" ? h("i") : null, label);
}

export function openEvidence(entity, ids, title, subtitle) {
  const idx = captureIndex(entity);
  const caps = [...new Set(ids)].map((id) => idx.get(id)).filter(Boolean);
  if (!caps.length) { toast("No stored capture is recorded for this number"); return; }
  openInspector({ entityId: entity.entity_id, captures: caps, title, subtitle });
}

const winDate = (v) => (/^\d{8}$/.test(v) ? fmt.dayYear(`${v.slice(0, 4)}-${v.slice(4, 6)}-${v.slice(6)}`) : /T/.test(v) ? fmt.dateTime(v) : fmt.dayYear(v));
const WIN_LABEL = { search_recent: "Search, recent window", search_baseline: "Search, baseline window", price: "Price window",
  reviews: "Review sample", recent: "Ads, recent 14 days", prior: "Ads, prior 14 days" };

function cell(c) {
  const v = c.value;
  const value = c.unit === "pct" ? `${fmt.signed(v)}%` : c.unit === "stars" ? fmt.signed(v, 2) : c.unit === "x" ? `${fmt.num(v, 2)}×` : c.unit === "bool" ? (v ? "Yes" : "No") : fmt.num(v, 2);
  const test = { "abs>": "|x| >", "<": "<", ">=": "≥", "==": "=" }[c.op] || c.op;
  const thr = c.unit === "pct" ? `${c.threshold}%` : c.unit === "bool" ? "Yes" : c.unit === "x" ? `${c.threshold}×` : String(c.threshold);
  return [value, test, thr];
}

export function alertItem(alert, entity, { showEntity = false, open = false } = {}) {
  const rule = RULES[alert.rule_id];
  const id = `alert-${alert.alert_id.replace(/[^\w-]/g, "_")}`;
  const detail = h("div", { class: "alert-detail", id: `${id}-d`, "data-open": String(open) }, h("div", {}, detailBody(alert, entity)));
  const head = h("button", { class: "alert-head", type: "button", "aria-expanded": String(open), "aria-controls": `${id}-d`,
    on: { click: () => { const on = head.getAttribute("aria-expanded") !== "true"; head.setAttribute("aria-expanded", String(on)); detail.dataset.open = String(on); } } },
  h("span", { class: "what" }, chip(alert.status), h("span", { class: "rule-id", text: `${alert.rule_id} · ${rule.role}` })),
  h("span", {}, h("div", { class: "alert-title", text: showEntity ? `${entity.name}: ${rule.name}` : rule.name }),
    h("div", { class: "alert-sentence", text: alert.sentence })),
  h("span", { class: "caret" }, icon("chevron")));
  return h("li", { id, "data-alert": alert.alert_id }, head, detail);
}

function detailBody(alert, entity) {
  const idx = captureIndex(entity);
  const out = [];
  if (alert.reason) out.push(h("p", { class: "alert-sentence" }, h("b", { text: "Why not evaluated: " }), alert.reason));
  if (alert.conditions.length) {
    out.push(h("table", { class: "conds" },
      h("thead", {}, h("tr", {}, h("th", { text: "Condition" }), h("th", { class: "r", text: "Value" }), h("th", { class: "r", text: "Test" }), h("th", { class: "r", text: "Threshold" }), h("th", { class: "r", text: "Met" }))),
      h("tbody", {}, alert.conditions.map((c) => { const [v, t, th] = cell(c);
        return h("tr", {}, h("td", { text: c.name }), h("td", { class: "r num", text: v }), h("td", { class: "r num", text: t }), h("td", { class: "r num", text: th }),
          h("td", { class: "r" }, h("span", { class: `pass ${c.passed ? "y" : "n"}`, text: c.passed ? "Yes" : "No" }))); }))));
  }
  if (alert.base_rate) out.push(h("p", { class: "alert-sentence", text: `Base rate: this rule was true in ${alert.base_rate.n} of the ${alert.base_rate.m} weeks it could be evaluated in this capture.` }));
  const wins = Object.entries(alert.windows || {});
  if (wins.length) out.push(h("dl", { class: "kv" }, wins.flatMap(([k, [a, b]]) => [h("dt", { text: WIN_LABEL[k] || k }), h("dd", { class: "num", text: `${winDate(a)} to ${winDate(b)}` })])));
  if (alert.llm_context) out.push(h("p", { class: "model-note" }, h("b", { text: "Model-written" }), alert.llm_context));
  if (alert.evidence_capture_ids.length) {
    out.push(h("div", {}, h("div", { class: "insp-sub", text: "Evidence (stored SerpApi responses)" }),
      h("div", { class: "evidence-links" }, alert.evidence_capture_ids.map((cid) => {
        const c = idx.get(cid);
        const label = c ? `${SENSORS[c.sensor]?.name || c.sensor}${c.role ? ` · ${c.role}` : ""}` : cid;
        return h("button", { class: "ev-btn", type: "button", on: { click: () => openEvidence(entity, [cid, ...alert.evidence_capture_ids.filter((x) => x !== cid)], `${alert.rule_id} evidence`, `${entity.name}, ${alert.as_of}`) } }, label, icon("arrow", 12));
      }))));
  }
  return h("div", { class: "alert-detail-in" }, out);
}
