// The lab pages' heartbeat (AGENT-DOOR Amendment 4 rev 2, section 4.3): while a page is visible, it tells the door once
// a minute that one tab is open on it. It counts tabs, not people.
//
//   POST /api/open/v1/door/here  {"page": <one of PAGES>, "tab": <32 hex>}
//
// The tab id is 128 random bits made when the page starts, held in this module's memory only: never a cookie, never in
// storage, so it can't link one visit to another. The request carries no cookie and no Referer. Nothing is sent while
// the page is hidden, and never more than once per INTERVAL_MS. Errors are ignored: a heartbeat never breaks a page.
// A page shows HERE_LINE wherever it shows these counts, and labels them ACTIVE_LABEL, never "people".
//
//   import { startHeartbeat } from "/sentilab/here.mjs";
//   const heartbeat = startHeartbeat("live");            // heartbeat.stop() ends it
//
// Standalone: the pages import it when their own owners wire it in.

export const PAGES = Object.freeze(["wall", "package3d", "live", "board", "results"]);
export const HERE_PATH = "/api/open/v1/door/here";
export const INTERVAL_MS = 60000;
export const ACTIVE_LABEL = "active tabs (last 2 min)";
// The agreed page text, checked clause by clause against the API's presence code (app/door/presence.py), and one sentence
// for the limiter that ships: the platform's rate-limit binding (web/src/door/door.js HERE_LIMITER).
export const HERE_LINE = "We count active tabs, not people. While a tab is open, we keep its random id, its page, a guess at its type and the time it last checked in. Inactive entries are removed by a scheduled cleanup after the two-minute window. We keep a keyed digest of the tab id until the next cleanup after 00:00 UTC, so we don't count that tab twice today. Restarting the API clears these records. Our hosting provider's network logs may record IP addresses. To limit heartbeats, we pass your network address prefix to our hosting provider's rate-limit service, which counts them in one-minute windows; we keep no copy, and the provider's own policy governs how long its service keeps those counts.";

// 128 random bits as 32 lower-case hex.
export function newTabId(random = globalThis.crypto) {
  return Array.from(random.getRandomValues(new Uint8Array(16)), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

// Start the heartbeat for one page. The options exist for tests; a page passes only its name.
export function startHeartbeat(page, { doc = globalThis.document, send = globalThis.fetch?.bind(globalThis), timers = globalThis,
  now = () => Date.now(), random = globalThis.crypto, intervalMs = INTERVAL_MS } = {}) {
  if (!PAGES.includes(page)) throw new Error("not a lab page");
  const tab = newTabId(random);
  let last = -Infinity;
  let timer = null;
  let stopped = false;
  const visible = () => doc.visibilityState === "visible";
  const beat = () => {
    last = now();
    try {
      Promise.resolve(send(HERE_PATH, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ page, tab }),
        credentials: "omit", cache: "no-store", referrerPolicy: "no-referrer" })).catch(() => undefined);
    } catch { /* never breaks the page */ }
  };
  // The next heartbeat, at least INTERVAL_MS after the last one, and only while visible.
  const schedule = () => {
    if (timer !== null) timers.clearTimeout(timer);
    timer = null;
    if (stopped || !visible()) return;
    timer = timers.setTimeout(() => {
      timer = null;
      if (stopped || !visible()) return;
      beat();
      schedule();
    }, Math.max(0, last + intervalMs - now()));
  };
  doc.addEventListener("visibilitychange", schedule);
  schedule();
  return Object.freeze({
    tab,
    stop() {
      stopped = true;
      if (timer !== null) timers.clearTimeout(timer);
      timer = null;
      doc.removeEventListener("visibilitychange", schedule);
    },
  });
}
