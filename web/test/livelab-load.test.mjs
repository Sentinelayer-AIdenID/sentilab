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
    addEventListener() {}, removeEventListener() {},
  });
  define("window", { addEventListener() {}, removeEventListener() {}, devicePixelRatio: 1 });
  define("location", { hostname: "sentilab.aidenid.com", search: "", pathname: "/sentilab/live/" });
  define("matchMedia", () => ({ matches: true, addEventListener() {} }));     // reduced motion: no entrance, no easing
  define("sessionStorage", { getItem: () => "yes", setItem() {} });
  define("ResizeObserver", class { observe() {} disconnect() {} });
  define("Node", class {});
  define("requestAnimationFrame", (f) => setTimeout(() => f(Date.now()), 16));
  define("cancelAnimationFrame", (id) => clearTimeout(id));
  const answers = { "/api/open/v1/door/results": "results.json", "/api/open/v1/door/events": "events.json", "/api/open/v1/door/board": "board.json",
    "/api/view/runs": "view_runs.json" };
  define("fetch", async (input, init = {}) => {
    const url = new URL(String(input), "https://sentilab.aidenid.com");
    requests.push({ path: url.pathname, method: init.method ?? "GET" });
    const name = answers[url.pathname];
    if (!name) return new Response("not found", { status: 404 });
    let body = readFileSync(join(FIX, name));
    const after = Number(url.searchParams.get("after") ?? 0);
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
  assert.deepEqual([...new Set(paths)].sort(), ["/api/open/v1/door/board", "/api/open/v1/door/events", "/api/open/v1/door/results"],
    "the door's three feeds are the only requests");
});
