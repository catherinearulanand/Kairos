// Evidence inspector: the stored SerpApi response behind any number, with its provenance and an
// independent byte check done in the browser.

import { h, clear, fmt, icon, copyText } from "./util.js";
import { loadCapture, sha256Hex } from "./api.js";
import { SENSORS } from "./model.js";

const root = () => document.getElementById("inspector");
const scrim = () => document.getElementById("scrim");
let returnFocus = null;
let session = 0;

const FRAGMENT = {
  google_trends: (d) => ({ search_parameters: d.search_parameters, interest_over_time: { timeline_data: d.interest_over_time?.timeline_data?.slice(-6) } }),
  google_finance: (d) => ({ summary: d.summary, graph: d.graph?.slice(-5) }),
  google_play_product: (d) => ({ product_info: d.product_info, reviews: d.reviews?.slice(0, 5) }),
  google_ads_transparency_center: (d) => ({ search_information: d.search_information, ad_creatives: d.ad_creatives?.slice(0, 3) }),
  google_news: (d) => ({ news_results: d.news_results?.slice(0, 4) }),
};

export function openInspector({ entityId, captures, title, subtitle }) {
  const el = root();
  returnFocus = document.activeElement;
  const mine = ++session;
  let active = 0;

  const close = h("button", { class: "btn btn-icon", type: "button", "aria-label": "Close evidence inspector", on: { click: closeInspector } }, icon("close"));
  const body = h("div", { class: "insp-body" });
  const tabs = h("div", { class: "insp-tabs", role: "tablist", "aria-label": "Captures behind this number" });

  const renderCapture = (i) => {
    active = i;
    [...tabs.children].forEach((b, k) => b.setAttribute("aria-selected", String(k === i)));
    renderBody(body, entityId, captures[i], () => mine === session);
  };
  captures.forEach((c, i) => tabs.append(h("button", { role: "tab", type: "button", "aria-selected": "false", on: { click: () => renderCapture(i) } },
    c.role ? `${c.role}` : SENSORS[c.sensor]?.name || c.sensor)));

  clear(el).append(
    h("div", { class: "insp-head" },
      h("div", {}, h("div", { class: "insp-title", text: title || "Evidence" }), subtitle ? h("div", { class: "insp-sub", text: subtitle }) : null),
      close),
    ...(captures.length > 1 ? [tabs] : []),
    body);
  renderCapture(0);

  el.dataset.open = "true";
  el.removeAttribute("inert");
  el.setAttribute("aria-hidden", "false");
  scrim().hidden = false;
  requestAnimationFrame(() => { scrim().dataset.on = "true"; close.focus({ preventScroll: true }); });
}

export function closeInspector() {
  const el = root();
  if (el.dataset.open !== "true") return;
  session++;
  el.dataset.open = "false";
  el.setAttribute("inert", "");
  el.setAttribute("aria-hidden", "true");
  scrim().dataset.on = "false";
  setTimeout(() => { if (el.dataset.open !== "true") scrim().hidden = true; }, 260);
  if (returnFocus && returnFocus.isConnected) returnFocus.focus({ preventScroll: true });
}

export const inspectorOpen = () => root().dataset.open === "true";

function renderBody(body, entityId, c, current) {
  const recorded = c.fixture_sha256 || c.raw_sha256;
  const verifyBox = h("div", { class: "verify", "data-state": "working", "aria-live": "polite" },
    h("div", { class: "verify-row" }, h("span", { class: "vtext", text: "Re-hashing the stored file…" })),
    h("div", { class: "verify-track" }, h("i")),
    h("small", { class: "vnote", text: "Computed here, in your browser, from the exact bytes the local API serves." }));
  const treeHost = h("div", { class: "tree-host" }, h("div", { class: "skel sk-tree", "aria-hidden": "true" }));

  const params = Object.entries(c.params || {}).map(([k, v]) => h("div", {}, h("span", { class: "mono", text: `${k}=` }), h("span", { class: "mono", text: String(v) })));

  clear(body).append(
    h("section", {},
      h("h3", { text: "Request" }),
      h("dl", { class: "kv" },
        h("dt", { text: "Sensor" }), h("dd", { text: SENSORS[c.sensor]?.name || c.sensor || "n/a" }),
        h("dt", { text: "Engine" }), h("dd", { class: "mono", text: c.engine }),
        h("dt", { text: "Parameters" }), h("dd", {}, ...params),
        h("dt", { text: "Captured" }), h("dd", { text: fmt.dateTime(c.captured_at) }),
        h("dt", { text: "Credits" }), h("dd", { text: c.credits_charged ? `${c.credits_charged} charged (key ${c.key_label || "n/a"})` : `0 (${c.serpapi_cached ? "served from SerpApi cache" : "reused stored capture"})` }),
        h("dt", { text: "File" }), h("dd", { class: "mono", text: c.path }))),
    h("section", {},
      h("h3", { text: "Integrity" }),
      verifyBox,
      h("dl", { class: "kv" },
        h("dt", { text: c.fixture_sha256 ? "Fixture SHA-256" : "SHA-256" }),
        h("dd", {}, h("span", { class: "hash", text: recorded }), copyBtn(recorded, "Hash")),
        c.fixture_sha256 && c.raw_sha256 && c.fixture_sha256 !== c.raw_sha256
          ? [h("dt", { text: "Original" }), h("dd", {}, h("span", { class: "hash", text: c.raw_sha256 }),
            h("div", { class: "insp-sub", text: "Hash of the response before reviewer names and profile links were removed. Differs on purpose." }))]
          : null)),
    h("section", {}, h("h3", { text: "Response" }), treeHost));

  loadCapture(entityId, c.capture_id).then(async ({ bytes }) => {
    const computed = await sha256Hex(bytes);
    if (!current()) return;
    const ok = computed === recorded;
    verifyBox.dataset.state = ok ? "ok" : "bad";
    verifyBox.querySelector(".vtext").textContent = ok ? "Bytes match the recorded SHA-256" : "Bytes do NOT match the recorded SHA-256";
    verifyBox.querySelector(".vnote").textContent = ok ? `Computed ${fmt.short(computed, 16)} in your browser. These hashes check local bytes, not the provider.`
      : "Do not trust numbers drawn from this file until it is re-captured.";
    const data = JSON.parse(new TextDecoder().decode(bytes));
    renderTree(treeHost, data, c.engine);
  }).catch((err) => {
    if (!current()) return;
    verifyBox.dataset.state = "bad";
    verifyBox.querySelector(".vtext").textContent = "Could not verify this capture";
    verifyBox.querySelector(".vnote").textContent = err.message;
    clear(treeHost).append(h("p", { class: "insp-sub", text: "The file is not shown because it did not pass verification." }));
  });
}

function copyBtn(text, what) {
  return h("button", { class: "copy", type: "button", on: { click: () => copyText(text, what) } }, "Copy");
}

// ---- JSON tree --------------------------------------------------------------------------

function renderTree(host, data, engine) {
  let full = false;
  const frag = FRAGMENT[engine] ? FRAGMENT[engine](data) : null;
  const holder = h("div", { class: "tree" });
  const label = h("span", { class: "insp-sub" });
  const toggle = h("button", { class: "link-btn", type: "button", on: { click: () => { full = !full; paint(); } } });
  const copy = h("button", { class: "copy", type: "button", on: { click: () => copyText(JSON.stringify(full || !frag ? data : frag, null, 2), "JSON") } }, "Copy JSON");
  const paint = () => {
    const value = full || !frag ? data : frag;
    label.textContent = full || !frag ? "Full response" : "The fields Kairos reads";
    toggle.textContent = !frag ? "" : full ? "Show only the fields Kairos reads" : "Show full response";
    clear(holder).append(h("ul", {}, ...entries(value).map(([k, v]) => treeNode(k, v, full || !frag ? 0 : 2))));
  };
  clear(host).append(h("div", { class: "tree-bar" }, label, h("span", {}, toggle, copy)), holder);
  paint();
}

const entries = (v) => (Array.isArray(v) ? v.map((x, i) => [i, x]) : Object.entries(v));
const PAGE = 40;

function treeNode(key, val, openDepth) {
  const li = h("li");
  const k = h("span", { class: "k", text: `${key}: ` });
  if (val === null || typeof val !== "object") {
    const text = typeof val === "string" ? JSON.stringify(val.length > 300 ? val.slice(0, 300) + "…" : val) : String(val);
    li.append(h("span", { class: "tg" }), k, h("span", { class: val === null ? "z" : typeof val === "string" ? "s" : "n", text }));
    return li;
  }
  const all = entries(val);
  const kids = h("ul");
  let shown = 0;
  const more = () => {
    kids.querySelector(":scope > li.more-row")?.remove();
    for (const [ck, cv] of all.slice(shown, shown + PAGE)) kids.append(treeNode(ck, cv, openDepth - 1));
    shown = Math.min(all.length, shown + PAGE);
    if (shown < all.length) kids.append(h("li", { class: "more-row" }, h("button", { class: "more", type: "button", on: { click: more } }, `… ${all.length - shown} more`)));
  };
  const tg = h("button", { class: "tg", type: "button", "aria-expanded": "false", "aria-label": `Toggle ${key}` }, "▸");
  const setOpen = (open) => {
    tg.setAttribute("aria-expanded", String(open));
    tg.textContent = open ? "▾" : "▸";
    if (open && !shown) more();
    kids.hidden = !open;
  };
  tg.addEventListener("click", () => setOpen(tg.getAttribute("aria-expanded") !== "true"));
  li.append(tg, k, h("span", { class: "z", text: Array.isArray(val) ? `[${all.length}]` : `{${all.length}}` }), kids);
  setOpen(openDepth > 0 && all.length > 0);
  return li;
}
