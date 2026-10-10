// Derived readings. All numbers come from the API; nothing here recomputes a rule.

import { weekOverWeek } from "./util.js";

export const RULES = {
  R1: { name: "Search share vs price", role: "Headline" },
  R2: { name: "Recent reviews vs displayed rating", role: "Context" },
  R3: { name: "Ad activity", role: "Context" },
};

export const STATUS = {
  fired: { label: "Fired", cls: "chip-fired" },
  not_fired: { label: "Not fired", cls: "chip-ok" },
  insufficient: { label: "Insufficient data", cls: "chip-na" },
};

export const SENSORS = {
  search_share: { name: "Search share", engine: "google_trends" },
  price: { name: "Price", engine: "google_finance" },
  app_reviews: { name: "App reviews", engine: "google_play_product" },
  ads: { name: "Ad creatives", engine: "google_ads_transparency_center" },
  news: { name: "News flow", engine: "google_news" },
};

export function series(e, sensor, metric, window = null) {
  return e.signals.find((x) => x.sensor === sensor && x.metric === metric && (!window || x.dims.window === window)) || null;
}

const last = (a) => (a && a.points.length ? a.points[a.points.length - 1] : null);

export function readings(e) {
  const price = series(e, "price", "close");
  const share = series(e, "search_share", "share");
  const mean = series(e, "app_reviews", "recent_mean");
  const shown = series(e, "app_reviews", "displayed_rating");
  const adsRecent = series(e, "ads", "active_creatives", "recent");
  const adsPrior = series(e, "ads", "active_creatives", "prior");
  const news = series(e, "news", "article");

  const out = {
    price: price && { series: price, last: last(price), wow: weekOverWeek(price.points) },
    share: share && { series: share, last: last(share), wow: weekOverWeek(share.points) },
    news: { series: news, headlines: e.headlines.length, lastWeek: last(news) },
    reviews: null, ads: null,
  };
  if (mean && shown) {
    const m = last(mean), d = last(shown);
    out.reviews = { mean: m, shown: d, gap: m.value - d.value, n: m.sample_n,
      from: m.dims.sample_start, to: m.dims.sample_end };
  }
  const ar = last(adsRecent), ap = last(adsPrior);
  if (ar) {
    const capped = ar.dims.at_cap === "true" || (ap && ap.dims.at_cap === "true");
    const adjacent = ap && ap.dims.end_date === ar.dims.start_date;
    out.ads = { recent: ar, prior: ap, capped, recentCapped: ar.dims.at_cap === "true",
      ratio: !capped && adjacent && ap.value > 0 ? ar.value / ap.value : null };
  }
  return out;
}

export function alertFor(e, rule) { return e.alerts.find((a) => a.rule_id === rule) || null; }

export function captureIndex(e) {
  const map = new Map();
  for (const c of e.captures) map.set(c.capture_id, c);
  return map;
}

export function latestCapture(data) {
  let best = null;
  for (const e of data.entities) for (const c of e.captures) if (!best || c.captured_at > best) best = c.captured_at;
  return best;
}

export const entityById = (data, id) => data.entities.find((e) => e.entity_id === id) || null;
