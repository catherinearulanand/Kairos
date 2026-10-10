// DOM helpers, formatters and motion utilities. Nothing builds HTML from strings: every value from
// the data (headlines, source names) goes in as a text node.

export const SVGNS = "http://www.w3.org/2000/svg";

export function h(tag, props, ...kids) {
  const node = document.createElement(tag);
  apply(node, props);
  append(node, kids);
  return node;
}

export function s(tag, props, ...kids) {
  const node = document.createElementNS(SVGNS, tag);
  apply(node, props);
  append(node, kids);
  return node;
}

function apply(node, props) {
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === "class") node.setAttribute("class", v);
    else if (k === "text") node.textContent = v;
    else if (k === "on") for (const [ev, fn] of Object.entries(v)) node.addEventListener(ev, fn);
    else if (k === "dataset") Object.assign(node.dataset, v);
    else node.setAttribute(k, v === true ? "" : String(v));
  }
}

function append(node, kids) {
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    node.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
}

export function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); return node; }

export const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// ---- formatting -------------------------------------------------------------------------

const IST = "Asia/Kolkata";
const dFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: IST });
const dyFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: IST });
const dtFmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: IST });

const toDate = (v) => (v instanceof Date ? v : new Date(/^\d{4}-\d{2}-\d{2}$/.test(v) ? v + "T00:00:00+05:30" : v));

export const fmt = {
  num(v, d = 1) { return v == null || Number.isNaN(v) ? "n/a" : v.toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d }); },
  int(v) { return v == null ? "n/a" : Math.round(v).toLocaleString("en-IN"); },
  pct(v, d = 1) { return v == null ? "n/a" : `${fmt.num(v, d)}%`; },
  signed(v, d = 1) { return v == null ? "n/a" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${fmt.num(Math.abs(v), d)}`; },
  inr(v, d = 2) { return v == null ? "n/a" : `₹${fmt.num(v, d)}`; },
  day(v) { return dFmt.format(toDate(v)); },
  dayYear(v) { return dyFmt.format(toDate(v)); },
  dateTime(v) { return `${dtFmt.format(toDate(v))} IST`; },
  short(hash, n = 12) { return hash ? `${hash.slice(0, n)}…` : "n/a"; },
};

/** Percent change between the last two points, only if they are adjacent weeks with a nonzero base. */
export function weekOverWeek(points) {
  if (!points || points.length < 2) return null;
  const [a, b] = points.slice(-2);
  const gap = (Date.parse(b.week) - Date.parse(a.week)) / 864e5;
  if (gap !== 7 || !a.value) return null;
  return 100 * (b.value / a.value - 1);
}

/** ▲ / ▼ + magnitude, neutral ink: direction is the glyph, never a traffic-light colour. */
export function deltaNode(pct, suffix = "") {
  if (pct == null) return h("span", { class: "delta na", text: "n/a" });
  const glyph = pct > 0.005 ? "▲" : pct < -0.005 ? "▼" : "▬";
  return h("span", { class: "delta" }, h("span", { class: "g", "aria-hidden": "true", text: glyph }),
    `${fmt.num(Math.abs(pct), 1)}%${suffix}`);
}

// ---- motion -----------------------------------------------------------------------------

/** Roll a number from its current text value to a new one. Honours reduced motion. */
export function tween(node, to, format, duration = 420) {
  const from = Number(node.dataset.v);
  node.dataset.v = String(to);
  if (reducedMotion() || !Number.isFinite(from) || from === to) { node.textContent = format(to); return; }
  const t0 = performance.now();
  const ease = (t) => 1 - Math.pow(1 - t, 4);
  const step = (now) => {
    const t = Math.min(1, (now - t0) / duration);
    node.textContent = format(from + (to - from) * ease(t));
    if (t < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

/** Draw a path from start to end. */
export function drawIn(path, duration = 700, delay = 0) {
  if (reducedMotion() || !path.getTotalLength || !path.animate) return;
  const len = path.getTotalLength();
  path.animate([{ strokeDasharray: len, strokeDashoffset: len }, { strokeDasharray: len, strokeDashoffset: 0 }],
    { duration, delay, easing: "cubic-bezier(0.25, 1, 0.5, 1)", fill: "backwards" });
}

export function fadeIn(node, duration = 260, delay = 0) {
  if (reducedMotion() || !node.animate) return;
  node.animate([{ opacity: 0 }, { opacity: 1 }], { duration, delay, easing: "ease-out", fill: "backwards" });
}

export function toast(message) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.dataset.on = "true";
  clearTimeout(toast.t);
  toast.t = setTimeout(() => { el.dataset.on = "false"; }, 1800);
}

export async function copyText(text, what = "Copied") {
  try { await navigator.clipboard.writeText(text); toast(`${what} to clipboard`); }
  catch { toast("Copy blocked by the browser"); }
}

// ---- icons ------------------------------------------------------------------------------

const ICONS = {
  chevron: "M4 6l4 4 4-4",
  close: "M4 4l8 8M12 4l-8 8",
  sun: "M8 3V1.5M8 14.5V13M3 8H1.5M14.5 8H13M4.5 4.5l-1-1M12.5 12.5l-1-1M11.5 4.5l1-1M3.5 12.5l1-1M8 5.2a2.8 2.8 0 100 5.6 2.8 2.8 0 000-5.6z",
  moon: "M13.5 9.5A5.5 5.5 0 116.5 2.5a4.5 4.5 0 007 7z",
  arrow: "M3 8h10M9 4l4 4-4 4",
  external: "M6 3H3v10h10v-3M9 3h4v4M13 3L7 9",
};

export function icon(name, size = 16) {
  return s("svg", { viewBox: "0 0 16 16", width: size, height: size, "aria-hidden": "true", focusable: "false",
    fill: "none", stroke: "currentColor", "stroke-width": "1.6", "stroke-linecap": "round", "stroke-linejoin": "round" },
  s("path", { d: ICONS[name] }));
}

export function safeUrl(url) {
  try { const u = new URL(url); return u.protocol === "https:" || u.protocol === "http:" ? u.href : null; }
  catch { return null; }
}
