import { h, clear, fmt, deltaNode, icon, toast } from "./util.js";
import { loadDashboard } from "./api.js";
import { readings, entityById, latestCapture } from "./model.js";
import { sparkline } from "./charts.js";
import { closeInspector, inspectorOpen } from "./inspector.js";
import { initPalette } from "./palette.js";
import { renderWatchlist } from "./views/watchlist.js";
import { renderCompany } from "./views/company.js";
import { renderAlerts } from "./views/alerts.js";
import { renderLedger } from "./views/ledger.js";

const $ = (id) => document.getElementById(id);
const main = $("main");
let data = null;
let cleanup = null;
let lastCompany = null;

// ---- routing ----------------------------------------------------------------------------

function route() {
  const parts = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  return { view: parts[0] || "watchlist", id: parts.length > 1 ? decodeURIComponent(parts.slice(1).join("/")) : null };
}

function render({ focus = false } = {}) {
  cleanup && cleanup();
  cleanup = null;
  closeInspector();
  if (!data) return;
  const { view, id } = route();
  let title = "Watchlist";
  if (!data.entities.length && view !== "ledger") {
    main.replaceChildren(h("div", { class: "page" }, h("div", { class: "panel" }, h("div", { class: "empty" }, h("h2", { text: "No companies configured" }),
      h("p", {}, "Add an entity to ", h("code", { text: "watchlist.yaml" }), ", run a snapshot, then refresh.")))));
  } else if (view === "company") {
    const entity = entityById(data, id) || data.entities[0];
    lastCompany = entity.entity_id;
    cleanup = renderCompany(main, data, entity);
    title = entity.name;
  } else if (view === "alerts") { renderAlerts(main, data, id); title = "Rule evaluations"; }
  else if (view === "ledger") { renderLedger(main, data); title = "Credit ledger"; }
  else { renderWatchlist(main, data); }
  document.title = `${title} · Kairos`;
  main.setAttribute("aria-busy", "false");
  chrome();
  if (focus) main.focus({ preventScroll: true });
  window.scrollTo({ top: 0 });
}

// ---- chrome -----------------------------------------------------------------------------

function chrome() {
  const { view } = route();
  const current = (v) => (view === v || (v === "watchlist" && !["company", "alerts", "ledger"].includes(view)) ? "page" : null);
  const companyHref = `#/company/${lastCompany || data?.entities[0]?.entity_id || ""}`;
  clear($("nav")).append(
    h("a", { href: "#/watchlist", "aria-current": current("watchlist"), text: "Watchlist" }),
    h("a", { href: companyHref, "aria-current": current("company"), text: "Company" }),
    h("a", { href: "#/alerts", "aria-current": current("alerts"), text: "Rules" }),
    h("a", { href: "#/ledger", "aria-current": current("ledger"), text: "Ledger" }));

  const src = $("source");
  if (data) {
    src.dataset.mode = data.source.mode;
    const last = latestCapture(data);
    clear(src).append(h("span", { class: "dot", "aria-hidden": "true" }),
      h("span", { text: data.source.label }));
    src.title = last ? `Latest capture ${fmt.dateTime(last)}` : data.source.label;
  }

  const strip = clear($("strip"));
  if (!data || !data.entities.length) return;
  const active = view === "company" ? lastCompany : null;
  data.entities.forEach((e) => {
    const r = readings(e);
    strip.append(h("a", { class: "strip-item", href: `#/company/${e.entity_id}`, "aria-current": e.entity_id === active ? "page" : null, title: e.name },
      h("span", { class: "strip-tick", text: e.nse_ticker.split(":")[0] }),
      h("span", { class: "strip-px num", text: r.price ? fmt.inr(r.price.last.value) : "n/a" }),
      r.price ? deltaNode(r.price.wow) : null,
      r.price ? sparkline(r.price.series.points.slice(-20).map((p) => p.value), { w: 56, h: 18, animate: false }) : null));
  });
}

function setTheme(theme, persist = true) {
  document.documentElement.dataset.theme = theme;
  if (persist) { try { localStorage.setItem("kairos-theme", theme); } catch { /* storage blocked */ } }
  const btn = $("theme");
  clear(btn).append(icon(theme === "dark" ? "sun" : "moon"));
  btn.setAttribute("aria-label", theme === "dark" ? "Switch to light theme" : "Switch to dark theme");
}

// ---- states -----------------------------------------------------------------------------

function skeleton() {
  const block = (w, hh) => { const d = h("div", { class: "skel", "aria-hidden": "true" }); d.style.width = w; d.style.height = hh; return d; };
  main.replaceChildren(h("div", { class: "page" },
    h("div", { class: "page-head" }, h("div", {}, block("260px", "30px"), block("340px", "16px"))),
    h("div", { class: "grid" }, h("div", { class: "col-8" }, block("100%", "420px")), h("div", { class: "col-4" }, block("100%", "420px"))),
    block("100%", "240px")));
}

function failure(err) {
  const offline = location.protocol === "file:";
  main.setAttribute("aria-busy", "false");
  main.replaceChildren(h("div", { class: "page" }, h("div", { class: "panel" }, h("div", { class: "empty" },
    h("h2", { text: offline ? "Open Kairos through its local server" : "Can't reach the Kairos server" }),
    h("p", {}, "Start it with ", h("code", { text: "python -m kairos.web" }), ", then open the address it prints.",
      h("br"), h("span", { class: "insp-sub", text: err && err.message ? err.message : "" })),
    h("p", {}, h("button", { class: "btn", type: "button", on: { click: () => boot() } }, "Try again"))))));
}

// ---- data -------------------------------------------------------------------------------

async function boot() {
  skeleton();
  main.setAttribute("aria-busy", "true");
  try { data = await loadDashboard(); } catch (err) { data = null; failure(err); return; }
  render();
}

async function refresh() {
  const btn = $("refresh");
  btn.dataset.busy = "true"; btn.disabled = true;
  try { data = await loadDashboard(); render(); toast("Stored data re-read"); }
  catch (err) { toast(`Refresh failed: ${err.message}`); }
  finally { btn.dataset.busy = "false"; btn.disabled = false; }
}

// ---- wiring -----------------------------------------------------------------------------

setTheme(document.documentElement.dataset.theme || "light", false);
$("theme").addEventListener("click", () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
$("refresh").addEventListener("click", refresh);
$("scrim").addEventListener("click", closeInspector);
window.addEventListener("hashchange", () => render({ focus: true }));
document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && inspectorOpen() && !$("palette").open) closeInspector();
});

initPalette(() => {
  const go = (hash) => () => { location.hash = hash; };
  const cmds = [
    { label: "Go to Watchlist", hint: "view", run: go("#/watchlist") },
    { label: "Go to Rule evaluations", hint: "view", run: go("#/alerts") },
    { label: "Go to Credit ledger", hint: "view", run: go("#/ledger") },
    { label: document.documentElement.dataset.theme === "dark" ? "Switch to light theme" : "Switch to dark theme", hint: "action", run: () => $("theme").click() },
    { label: "Refresh stored data", hint: "action", run: refresh },
  ];
  for (const e of data ? data.entities : []) {
    cmds.push({ label: `Open ${e.name}`, hint: e.nse_ticker, run: go(`#/company/${e.entity_id}`) });
    for (const a of e.alerts.filter((x) => x.status === "fired")) cmds.push({ label: `Fired: ${e.name}, ${a.rule_id}`, hint: "alert", run: go(`#/alerts/${a.alert_id}`) });
  }
  return cmds;
});

boot();
