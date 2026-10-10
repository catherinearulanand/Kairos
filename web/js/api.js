export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

async function failure(res) {
  let msg = `${res.status} ${res.statusText}`;
  try { msg = (await res.json()).error || msg; } catch { /* body was not JSON */ }
  return new ApiError(msg, res.status);
}

export async function loadDashboard() {
  const res = await fetch("/api/dashboard", { cache: "no-store" });
  if (!res.ok) throw await failure(res);
  return res.json();
}

/** The stored bytes of one capture. The server refuses to send bytes whose hash does not match. */
export async function loadCapture(entityId, captureId) {
  const res = await fetch(`/api/capture/${encodeURIComponent(entityId)}/${encodeURIComponent(captureId)}`, { cache: "no-store" });
  if (!res.ok) throw await failure(res);
  return { bytes: await res.arrayBuffer(), expected: res.headers.get("X-Kairos-Expected-Sha256") };
}

export async function sha256Hex(bytes) {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
