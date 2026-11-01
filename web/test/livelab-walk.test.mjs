// node --test test/livelab-walk.test.mjs (from web/)
// Carter (19:1xZ, run 70de: queued -> reproduced within 3 s, inside one poll; Aneta: "we see you guys coming but we do
// not see bots move"): when one poll brings several new step records for one run, its avatar on the step map walks
// through each recorded step in order, about 700 ms apiece, with each step's plain word, then rests at its real latest
// step. Only records the run has (never an invented step); reduced motion or a hidden tab jumps at once; runs loaded
// from history never walk.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const FIX = join(HERE, "fixtures", "livelab");
const doc = (name) => JSON.parse(readFileSync(join(FIX, name), "utf8"));
const LIVE = pathToFileURL(join(HERE, "..", "public", "sentilab", "live", "live.mjs")).href;

// ── the whole page in a small recording DOM ─────────────────────────────────────────────────────────────────────
function anything() {
  const store = Object.create(null);
  return new Proxy(function stub() {}, {
    get(_, p) { if (p === Symbol.toPrimitive) return () => 0; if (p === Symbol.iterator) return function* none() {}; if (p === "then") return undefined; return p in store ? store[p] : anything(); },
    set(_, p, v) { store[p] = v; return true; }, apply: () => anything(), construct: () => anything(),
  });
}
class FakeNode {}
class El extends FakeNode {
  constructor(tag) {
    super();
    Object.assign(this, { tag, children: [], attrs: new Map(), html: null, dataset: {}, style: {}, hidden: false, disabled: false, value: "", className: "", width: 0, height: 0 });
    const set = new Set();
    this.classList = { add: (...c) => c.forEach((x) => set.add(x)), remove: (...c) => c.forEach((x) => set.delete(x)), contains: (c) => set.has(c),
      toggle: (c, on) => { const v = on ?? !set.has(c); if (v) set.add(c); else set.delete(c); return v; } };
  }
  append(...nodes) { for (const n of nodes) this.children.push(n instanceof El ? n : { text: String(n) }); }
  replaceChildren(...nodes) { this.children = []; this.html = null; this.append(...nodes); }
  set textContent(v) { this.children = [{ text: String(v) }]; this.html = null; }
  get textContent() { return this.children.map((c) => (c instanceof El ? c.textContent : c.text)).join(""); }
  set innerHTML(v) { this.children = []; this.html = String(v); }
  get innerHTML() { return this.html ?? ""; }
  setAttribute(k, v) { this.attrs.set(k, String(v)); }
  getAttribute(k) { return this.attrs.get(k) ?? null; }
  removeAttribute(k) { this.attrs.delete(k); }
  addEventListener() {} removeEventListener() {} focus() {} showModal() {} close() {} remove() {}
  querySelector() { return new El("stub"); }
  querySelectorAll() { return []; }
  getBoundingClientRect() { return { width: 800, height: 400, left: 0, top: 0, right: 800, bottom: 400 }; }
  getContext(kind) { return kind === "2d" ? anything() : null; }   // no WebGL2: the 2D path
  get offsetParent() { return null; }
  get clientWidth() { return 800; }
  get clientHeight() { return 84; }
}
// Every string the page put into the DOM reachable from its static elements: text, attributes, markup, data.
function dump(el, out = { text: [], attrs: [], html: [] }) {
  for (const [k, v] of el.attrs) out.attrs.push(`${k}=${v}`);
  for (const v of Object.values(el.dataset)) out.attrs.push(String(v));
  if (typeof el.title === "string") out.attrs.push(el.title);
  if (el.html) out.html.push(el.html);
  for (const c of el.children) { if (c instanceof El) { if (c.tag !== "title") dump(c, out); } else out.text.push(c.text); }
  return out;
}
function installPage(t, answer, { reduced = false } = {}) {
  const saved = new Map();
  const define = (name, value) => { saved.set(name, Object.getOwnPropertyDescriptor(globalThis, name)); Object.defineProperty(globalThis, name, { value, configurable: true, writable: true }); };
  const ids = new Map();
  define("Node", FakeNode);
  define("document", { hidden: false, visibilityState: "visible", activeElement: null, body: new El("body"),
    getElementById: (id) => { if (!ids.has(id)) ids.set(id, new El(id)); return ids.get(id); }, querySelector: () => null, querySelectorAll: () => [],
    createElement: (tag) => new El(tag), createElementNS: (_, tag) => new El(tag), addEventListener() {}, removeEventListener() {} });
  define("window", { addEventListener() {}, removeEventListener() {}, devicePixelRatio: 1 });
  define("location", { hostname: "sentilab.aidenid.com", search: "", pathname: "/sentilab/live/" });
  define("matchMedia", (q) => ({ matches: /reduced-motion/.test(String(q)) ? reduced : true, addEventListener() {} }));
  define("sessionStorage", { getItem: () => "yes", setItem() {} });
  define("ResizeObserver", class { observe() {} disconnect() {} });
  define("requestAnimationFrame", (f) => setTimeout(() => f(Date.now()), 16));
  define("cancelAnimationFrame", (id) => clearTimeout(id));
  define("fetch", async (input) => {
    const url = new URL(String(input), "https://sentilab.aidenid.com");
    const body = answer(url);
    if (body === "network") throw new TypeError("network error");
    if (body === undefined) return new Response("{}", { status: 502 });
    return body === null ? new Response("{}", { status: 404 }) : new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
  });
  t.after(() => { for (const [name, desc] of saved) { if (desc) Object.defineProperty(globalThis, name, desc); else delete globalThis[name]; } });
  return { page: () => { const out = { text: [], attrs: [], html: [] }; for (const el of ids.values()) dump(el, out); return out; },
    part: (id) => (ids.has(id) ? dump(ids.get(id)) : { text: [], attrs: [], html: [] }) };
}
const settle = async () => { for (let i = 0; i < 25; i += 1) await new Promise((r) => setImmediate(r)); };

const walk = (el, out = []) => { if (!el) return out; out.push(el); for (const c of el.children ?? []) if (c instanceof El) walk(c, out); return out; };
const NOW = Date.parse("2026-11-01T19:10:30Z");
const ID = "open-0000beef-0000000000000000000000000000beef";
// The door as recorded, then one poll that brings a new run's whole life at once (Carter, 19:1xZ: run 70de went
// queued -> reproduced in 3 s, inside one poll).
function door(states, { resultsLag = false } = {}) {
  const base = doc("events.json"), results = doc("results.json"), board = doc("board.json");
  const item = { ...results.items[0], id: ID, short_id: "beef", label: "unknown · beef", class: "unknown", arrival: 99, seq: results.next_after + 1 };
  const recs = states.map((state, i) => ({ seq: 100 + i, at: new Date(NOW - 3000 + i * 600).toISOString(), kind: "run", class: "unknown", label: "unknown · beef",
    run_id: ID, short_id: "beef", state }));
  const later = { ...base, events: [{ seq: 99, at: new Date(NOW - 4000).toISOString(), kind: "arrival", class: "unknown", label: "unknown · beef", purpose: "place-chiplets", short_id: "beef" }, ...recs],
    next_after: 100 + states.length - 1, has_more: false };
  const phase = { live: false, results: !resultsLag };
  const answer = (url) => {
    const after = Number(url.searchParams.get("after") ?? 0);
    if (url.pathname === "/api/open/v1/door/results") {
      if (after < results.next_after) return results;
      return phase.live && phase.results && after < item.seq ? { ...results, items: [item], next_after: item.seq, has_more: false } : { ...results, items: [], next_after: Math.max(after, results.next_after), has_more: false };
    }
    if (url.pathname === "/api/open/v1/door/events") {
      if (after < base.next_after) return base;
      return phase.live && after < later.next_after ? later : { ...base, events: [], next_after: Math.max(after, base.next_after), has_more: false };
    }
    if (url.pathname === "/api/open/v1/door/board") return board;
    return null;
  };
  return { answer, phase };
}
// What the step map shows for the new run, tick by tick: [step index, station, word] each time it changes.
function captions() {
  return walk(document.getElementById("atlasSvg")).filter((el) => el.tag === "text" && el.getAttribute("class") === "atlas-step")
    .map((el) => [el.getAttribute("data-step"), el.getAttribute("data-station"), el.textContent]);
}
async function live(t, tag, states, { reduced = false, resultsLag = false } = {}) {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"], now: NOW });
  const d = door(states, { resultsLag });
  installPage(t, d.answer, { reduced });
  await import(`${LIVE}?walk=${tag}`);
  for (let k = 0; k < 8; k += 1) { t.mock.timers.tick(500); await settle(); }
  assert.deepEqual(captions(), [], "runs loaded from history never walk");
  d.phase.live = true;
  const seen = [];
  if (resultsLag) { for (let k = 0; k < 40; k += 1) { t.mock.timers.tick(100); await settle(); } assert.deepEqual(captions(), [], "nothing to draw yet"); d.phase.results = true; }
  for (let k = 0; k < 80; k += 1) {
    t.mock.timers.tick(100); await settle();
    for (const c of captions()) if (!seen.some((s) => s[0] === c[0])) seen.push(c);
  }
  return seen;
}

test("walk: a run whose five step records arrive in one poll walks through each recorded step in order, then rests", async (t) => {
  const seen = await live(t, "five", ["queued", "evaluating", "evaluated", "replaying", "reproduced"]);
  assert.deepEqual(seen.map((s) => s.slice(1)), [["queue", "Waiting in line"], ["simulate", "Simulating"], ["replay", "Re-checking (replay)"],
    ["replay", "Re-checking (replay)"], ["board", "Accepted · replay matched"]]);
  assert.deepEqual(seen.map((s) => s[0]), ["0", "1", "2", "3", "4"], "five positions, in the records' order");
  assert.deepEqual(captions(), [], "then it rests at its real latest step");
});

test("walk: with reduced motion the run jumps straight to its latest step", async (t) => {
  const seen = await live(t, "reduced", ["queued", "evaluating", "evaluated", "replaying", "reproduced"], { reduced: true });
  assert.deepEqual(seen, [], "no walk");
});

test("walk: no step is shown that is not in the run's records", async (t) => {
  const seen = await live(t, "skip", ["queued", "evaluating", "reproduced"]);
  assert.deepEqual(seen.map((s) => s.slice(1)), [["queue", "Waiting in line"], ["simulate", "Simulating"], ["board", "Accepted · replay matched"]]);
  assert.equal(seen.some((s) => s[1] === "replay"), false, "the run recorded no replay step, so none is shown");
});

test("walk: a run whose records arrive a poll before its result still walks every recorded step once it can be drawn", async (t) => {
  const seen = await live(t, "lag", ["queued", "evaluating", "evaluated", "replaying", "reproduced"], { resultsLag: true });
  assert.deepEqual(seen.map((s) => s[0]), ["0", "1", "2", "3", "4"], "from its first recorded step, in order");
  assert.deepEqual(captions(), []);
});
