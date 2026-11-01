// node --test test/livelab-arrivals.test.mjs (from web/)
// Carter (#58250) and warden (18:07Z): a new arrival is something a person sees. At the top of "Follow the work" a card
// slides in with the aquarium's avatar (AIdenID live-aquarium Character, ported) and one plain sentence, with the visit
// id visible ("visit 82ea", aneta), holds about 10 s and settles into a strip of recent arrivals. Today's classes never
// claim agent versus crawler (root, 18:11Z): a declared class reads "an automated visitor that says what it is". Cards
// come from arrival records only: no declaration text ever reaches one.
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
function installPage(t, answer) {
  const saved = new Map();
  const define = (name, value) => { saved.set(name, Object.getOwnPropertyDescriptor(globalThis, name)); Object.defineProperty(globalThis, name, { value, configurable: true, writable: true }); };
  const ids = new Map();
  define("Node", FakeNode);
  define("document", { hidden: false, visibilityState: "visible", activeElement: null, body: new El("body"),
    getElementById: (id) => { if (!ids.has(id)) ids.set(id, new El(id)); return ids.get(id); }, querySelector: () => null, querySelectorAll: () => [],
    createElement: (tag) => new El(tag), createElementNS: (_, tag) => new El(tag), addEventListener() {}, removeEventListener() {} });
  define("window", { addEventListener() {}, removeEventListener() {}, devicePixelRatio: 1 });
  define("location", { hostname: "sentilab.aidenid.com", search: "", pathname: "/sentilab/live/" });
  define("matchMedia", () => ({ matches: true, addEventListener() {} }));
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


const CODES = /(?<![\w-])(declared_agent|verified_agent|signed_agent|crawler_claimed|likely_human|automation)(?![\w-])/;
const walk = (el, out = []) => { if (!el) return out; out.push(el); for (const c of el.children ?? []) if (c instanceof El) walk(c, out); return out; };

test("a new arrival slides in as an avatar with a plain sentence and its visit id, then settles into the strip", async (t) => {
  const NOW = Date.parse("2026-11-01T18:20:00Z");
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"], now: NOW });
  const results = doc("results.json"), board = doc("board.json"), visitors = doc("visitors-declarations.json");
  const base = doc("events.json");
  const arrival = { seq: 99, at: new Date(NOW - 2000).toISOString(), kind: "arrival", class: "declared_agent", label: "declared_agent \u00b7 82ea",
    purpose: "place-chiplets", short_id: "82ea" };
  const events = { ...base, events: [...base.events, arrival], next_after: 99 };
  const dom = installPage(t, (url) => {
    const after = Number(url.searchParams.get("after") ?? 0);
    if (url.pathname === "/api/open/v1/door/results") return after >= results.next_after ? { ...results, items: [], has_more: false } : results;
    if (url.pathname === "/api/open/v1/door/events") return after >= events.next_after ? { ...events, events: [], has_more: false } : events;
    if (url.pathname === "/api/open/v1/door/board") return board;
    if (url.pathname === "/api/open/v1/door/visitors") return after >= visitors.next_after ? { ...visitors, items: [], has_more: false } : visitors;
    return null;
  });
  await import(`${LIVE}?arrivals=1`);
  for (let k = 0; k < 4; k += 1) { t.mock.timers.tick(500); await settle(); }
  const card = document.getElementById("arrivalCard");
  assert.equal(card.hidden, false, "the newest arrival holds the card");
  const cardText = dom.part("arrivalCard").text.join(" ");
  assert.match(cardText, /An automated visitor that says what it is arrived · here to place chiplets · just now/);
  assert.match(cardText, /visit 82ea/, "the visit id is visible");
  assert.equal(/AI agent/.test(cardText), false, "a declared class never claims to be an AI agent");
  assert.equal(CODES.test(cardText), false, "no class code");
  assert.ok(walk(card).some((el) => el.tag === "svg"), "an avatar is drawn");
  // About 10 s later the card has settled into the strip, still with its visit id.
  for (let k = 0; k < 24; k += 1) { t.mock.timers.tick(500); await settle(); }
  assert.equal(card.hidden, true, "the card settled");
  const strip = dom.part("arrivalStrip").text.join(" ");
  assert.match(strip, /visit 82ea/, "the strip keeps the visit id");
  assert.equal(CODES.test(strip), false);
  // No declared text on any card or strip item (cards come from arrivals, never from declarations).
  const area = [...dom.part("arrivals").text, ...dom.part("arrivals").attrs].join(" ");
  for (const text of ["Ortho Placer", "Testing whether spreading", "Newest Declarer"]) assert.equal(area.includes(text), false, `no declared text: ${text}`);
});
