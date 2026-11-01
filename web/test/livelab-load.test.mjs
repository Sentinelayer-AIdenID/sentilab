// node --test web/test/livelab-load.test.mjs
// The Live Lab page loaded whole (web/public/sentilab/live/live.mjs) in a minimal stand-in DOM, with node's fake timers,
// and left open past 30 s. Every request it makes is recorded. It must poll the door (results, events, board) and must
// never ask /api/view/runs: that route answered production in about 4.3 s per call (warden's measurement, 16:29Z), and
// a room scanning one QR code within 30 s would stack those calls on the one API replica the live demo shares.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const FIX = join(HERE, "fixtures", "livelab");
const LIVE = pathToFileURL(join(HERE, "..", "public", "sentilab", "live", "live.mjs")).href;

// An element that accepts anything: every property read is another such element (or what was stored on it), every call
// returns one, and it reads as 0 or "" when the page does arithmetic or text with it.
function anything() {
  const store = Object.create(null);
  const handler = {
    get(_, prop) {
      if (prop === Symbol.toPrimitive) return () => 0;
      if (prop === Symbol.iterator) return function* none() {};
      if (prop === "then") return undefined;          // never a thenable
      if (prop in store) return store[prop];
      return anything();
    },
    set(_, prop, value) { store[prop] = value; return true; },
    has(_, prop) { return prop in store; },
    apply() { return anything(); },
    construct() { return anything(); },
  };
  return new Proxy(function stub() {}, handler);
}

function installPage(t, requests) {
  const saved = new Map();
  const listeners = { window: new Map(), document: new Map() };
  const on = (where) => (type, fn) => { const list = listeners[where].get(type) ?? []; list.push(fn); listeners[where].set(type, list); };
  const define = (name, value) => { saved.set(name, Object.getOwnPropertyDescriptor(globalThis, name)); Object.defineProperty(globalThis, name, { value, configurable: true, writable: true }); };
  const ids = new Map();
  const element = (tag = "") => {
    const el = anything();
    if (tag === "canvas") el.getContext = (kind) => (kind === "2d" ? anything() : null);   // no WebGL2: the 2D path
    return el;
  };
  define("document", {
    hidden: false, visibilityState: "visible", activeElement: null, body: anything(),
    getElementById: (id) => { if (!ids.has(id)) ids.set(id, element(id === "packageCanvas" || id === "packageCanvas2d" ? "canvas" : "")); return ids.get(id); },
    querySelector: () => null, querySelectorAll: () => [], createElement: (tag) => element(tag), createElementNS: () => element(),
    addEventListener: on("document"), removeEventListener() {},
  });
  define("window", { addEventListener: on("window"), removeEventListener() {}, devicePixelRatio: 1 });
  define("location", { hostname: "sentilab.aidenid.com", search: "", pathname: "/sentilab/live/" });
  define("matchMedia", () => ({ matches: true, addEventListener() {} }));     // reduced motion: no entrance, no easing
  define("sessionStorage", { getItem: () => "yes", setItem() {} });
  define("ResizeObserver", class { observe() {} disconnect() {} });
  define("Node", class {});
  define("requestAnimationFrame", (f) => setTimeout(() => f(Date.now()), 16));
  define("cancelAnimationFrame", (id) => clearTimeout(id));
  const answers = { "/api/open/v1/door/results": "results.json", "/api/open/v1/door/events": "events.json", "/api/open/v1/door/board": "board.json",
    "/api/open/v1/door/visitors": "visitors-staging.json", "/api/view/runs": "view_runs.json" };
  define("fetch", async (input, init = {}) => {
    const url = new URL(String(input), "https://sentilab.aidenid.com");
    requests.push({ path: url.pathname, method: init.method ?? "GET" });
    const name = answers[url.pathname];
    if (!name) return new Response("not found", { status: 404 });
    let body = readFileSync(join(FIX, name));
    const after = Number(url.searchParams.get("after") ?? 0);
    if (name === "visitors-staging.json" && after >= JSON.parse(body.toString("utf8")).next_after) body = Buffer.from(JSON.stringify({ ...JSON.parse(body.toString("utf8")), items: [], has_more: false }));
    if (name === "results.json" || name === "events.json") {
      const d = JSON.parse(body.toString("utf8"));
      if (after >= d.next_after) body = Buffer.from(JSON.stringify({ ...d, [name === "results.json" ? "items" : "events"]: [], has_more: false }));
    }
    return new Response(body, { status: 200, headers: { "content-type": "application/json" } });
  });
  t.after(() => {
    for (const [name, desc] of saved) {
      if (desc) Object.defineProperty(globalThis, name, desc);
      else delete globalThis[name];
    }
  });
  return { fire: (where, type, event = {}) => { for (const fn of listeners[where].get(type) ?? []) fn({ type, ...event }); } };
}
const settle = async () => { for (let i = 0; i < 25; i += 1) await new Promise((r) => setImmediate(r)); };

test("loading Live Lab and leaving it open past 30 s never asks /api/view/runs (and still polls the door)", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"], now: Date.parse("2026-11-01T16:30:00Z") });
  const requests = [];
  installPage(t, requests);
  await import(`${LIVE}?load=1`);
  await settle();
  for (let s = 0; s < 40; s += 1) { t.mock.timers.tick(1000); await settle(); }   // 40 s of the page's own clock
  const paths = requests.map((r) => r.path);
  assert.ok(paths.filter((p) => p === "/api/open/v1/door/results").length >= 5, `the page loaded and kept polling the door: ${paths.length} requests`);
  assert.ok(paths.includes("/api/open/v1/door/events") && paths.includes("/api/open/v1/door/board"), "events and board too");
  assert.deepEqual(paths.filter((p) => p === "/api/view/runs"), [], "no request to /api/view/runs, at load or later");
  assert.ok(requests.every((r) => r.method === "GET"), "read-only");
  assert.deepEqual([...new Set(paths)].sort(), ["/api/open/v1/door/board", "/api/open/v1/door/events", "/api/open/v1/door/results", "/api/open/v1/door/visitors"],
    "the door's read-only feeds are the only requests");
});

// Warden's P1-1: pagehide stops the feed and the timers; a page restored from the back/forward cache (pageshow with
// persisted true) must start them again, or it shows the door as stopped although nothing is wrong.
test("P1-1: after pagehide, a back/forward-cache restore (pageshow, persisted) resumes polling", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"], now: Date.parse("2026-11-01T16:40:00Z") });
  const requests = [];
  const page = installPage(t, requests);
  await import(`${LIVE}?load=bfcache`);
  await settle();
  for (let s = 0; s < 4; s += 1) { t.mock.timers.tick(1000); await settle(); }
  assert.ok(requests.some((r) => r.path === "/api/open/v1/door/results"), "polling before the page is hidden");
  page.fire("window", "pagehide", { persisted: true });
  await settle();
  const atHide = requests.length;
  for (let s = 0; s < 20; s += 1) { t.mock.timers.tick(1000); await settle(); }
  assert.equal(requests.length, atHide, "nothing is requested while the page sits in the back/forward cache");
  page.fire("window", "pageshow", { persisted: true });
  await settle();
  for (let s = 0; s < 16; s += 1) { t.mock.timers.tick(1000); await settle(); }
  const after = requests.slice(atHide).map((r) => r.path);
  assert.ok(after.filter((p) => p === "/api/open/v1/door/results").length >= 3, `the door feed resumes: ${after.join(", ")}`);
  assert.ok(after.includes("/api/open/v1/door/events") && after.includes("/api/open/v1/door/board"), "events and board resume too");
});

// P1-2(b) on the whole page: a backlog of result pages is fetched spaced out, never as a burst, and a 503 with
// Retry-After stops every request until it has passed.
test("P1-2(b): a backlog is spaced out, and a 503 with Retry-After silences the page until it passes", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"], now: Date.parse("2026-11-01T16:45:00Z") });
  const requests = [];
  installPage(t, requests);
  // A backlog: results answer 8 pages (has_more), then a 503 with Retry-After: 30 for everything for 10 s.
  const real = globalThis.fetch;
  let page = 0, downUntil = 0;
  globalThis.fetch = async (input, init = {}) => {
    const url = new URL(String(input), "https://sentilab.aidenid.com");
    if (downUntil && Date.now() < downUntil) {
      requests.push({ path: url.pathname, method: init.method ?? "GET", at: Date.now(), down: true });
      return new Response("{}", { status: 503, headers: { "retry-after": "30" } });
    }
    if (url.pathname === "/api/open/v1/door/results" && page < 8) {
      page += 1;
      requests.push({ path: url.pathname, method: "GET", at: Date.now() });
      const d = JSON.parse(readFileSync(join(FIX, "results.json"), "utf8"));
      return new Response(JSON.stringify({ ...d, items: [], next_after: page, has_more: page < 8 }), { status: 200 });
    }
    const r = await real(input, init);
    requests.at(-1).at = Date.now();
    return r;
  };
  await import(`${LIVE}?load=backoff`);
  for (let k = 0; k < 120; k += 1) { t.mock.timers.tick(100); await settle(); }       // 12 s
  const backlog = requests.filter((r) => r.path === "/api/open/v1/door/results").slice(0, 8).map((r) => r.at);
  assert.equal(backlog.length, 8);
  const gaps = backlog.slice(1).map((v, i) => v - backlog[i]);
  assert.ok(gaps.every((g) => g >= 300), `backlog pages spaced at least 300 ms apart: ${gaps}`);
  // Now the API answers 503 with Retry-After: 30. After the first refusal, nothing for 30 s.
  downUntil = Date.now() + 10000;
  for (let k = 0; k < 60; k += 1) { t.mock.timers.tick(100); await settle(); }        // up to the first 503
  const firstDown = requests.find((r) => r.down);
  assert.ok(firstDown, "the page met the 503");
  const n = requests.length;
  for (let k = 0; k < 280; k += 1) { t.mock.timers.tick(100); await settle(); }       // 28 s more
  const during = requests.slice(n).filter((r) => r.at - firstDown.at < 30000);
  assert.deepEqual(during.map((r) => r.path), [], "no request before Retry-After has passed");
  for (let k = 0; k < 300; k += 1) { t.mock.timers.tick(100); await settle(); }       // 30 s more: it resumes
  assert.ok(requests.slice(n).some((r) => r.path === "/api/open/v1/door/results" && !r.down), "polling resumes after Retry-After");
});
