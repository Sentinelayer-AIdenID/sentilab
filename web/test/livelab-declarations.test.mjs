// node --test web/test/livelab-declarations.test.mjs
// Live Lab shows a run's self-declared visitor text (the door's /visitors feed, docs/sentilab/DOOR-VISITORS.md) as
// untrusted public text: textContent only, clipped to the API's limits (64 and 160 code points), never in an attribute,
// a link or markup, always labelled "self-declared, not verified"; a hidden declaration reads "hidden by the operator"
// and nothing else; and a hide reaches a tab that is already open (each poll re-reads the whole window and replaces it).
// Fixtures: visitors-staging.json (staging's recorded answer, the real shape) and visitors-declarations.json (synthetic
// declarations written to the documented schema; see capture.json).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import * as M from "../public/sentilab/live/live-model.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const FIX = join(HERE, "fixtures", "livelab");
const doc = (name) => JSON.parse(readFileSync(join(FIX, name), "utf8"));
const LIVE = pathToFileURL(join(HERE, "..", "public", "sentilab", "live", "live.mjs")).href;
const NOTE = "self-declared, not verified";
const HIDDEN = "hidden by the operator";
const N64 = doc("visitors-declarations.json").items.find((x) => x.seq === 105).declaration.name;

test("the visitors feed is read strictly: the real staging answer, and the synthetic declarations", () => {
  const real = M.normalizeVisitors(doc("visitors-staging.json"));
  assert.ok(real, "staging's answer is a visitors page");
  assert.equal(real.items.length, 41);
  assert.equal(real.items.filter((x) => x.declaration || x.hidden).length, 0);
  assert.equal(M.normalizeVisitors({ ...doc("visitors-staging.json"), schema: "sentilab-door-visitors/2" }), null);
  const page = M.normalizeVisitors(doc("visitors-declarations.json"));
  const bad = M.normalizeVisitors({ ...doc("visitors-declarations.json"), items: [{ seq: 1, class: "unknown", short_id: "abcd", label: "forged label", event_kind: "declaration",
    declaration: { name: "x", reason: "y" } }] });
  assert.equal(bad.items.length, 0, "an item whose label is not rebuilt from its class and short id is dropped");
  const by = M.declarationsByLabel(page.items);
  // The newest declaration event per label wins: 5cb8 declared twice.
  assert.equal(by.get("unknown · 5cb8").seq, 102);
  assert.deepEqual(M.declarationView(by.get("unknown · 5cb8")), { kind: "declared", name: "Ortho Placer",
    reason: "Testing whether spreading the DRAM out cools the CPUs", source: "direct", note: NOTE, seq: 102 });
  // Hidden: the tombstone, and nothing else.
  assert.deepEqual(M.declarationView(by.get("unknown · c991")), { kind: "hidden", text: HIDDEN, seq: 103 });
  // A hidden row that wrongly still carries text shows none of it.
  const leaky = M.declarationsByLabel(M.normalizeVisitors({ ...doc("visitors-declarations.json"), items: [{ seq: 7, at: null, class: "unknown", purpose: null,
    short_id: "abcd", label: "unknown · abcd", event_kind: "declaration", declaration: { name: "leak", reason: "leak" }, hidden: "abuse" }] }).items);
  assert.deepEqual(M.declarationView(leaky.get("unknown · abcd")), { kind: "hidden", text: HIDDEN, seq: 7 });
  // HTML-looking text stays a plain string (the DOM path renders it with textContent).
  const html = M.declarationView(by.get("unknown · c2c7"));
  assert.equal(html.name, "<img src=x onerror=alert(1)>");
  assert.equal(html.reason, "</p><script>alert(\"x\")</script> & 'quotes' \"too\"");
  // 64 code points kept whole; a 65th is clipped; 160 for the reason.
  assert.equal(Array.from(N64).length, 64);
  assert.equal(M.declarationView(by.get("declared_agent · ccd6")).name, N64);
  assert.equal(Array.from(M.declarationView(by.get("declared_agent · ccd6")).reason).length, 160);
  const over = M.declarationView(by.get("unknown · babd"));
  assert.equal(over.name, N64, "a 65-code-point name is clipped to 64");
  assert.equal(over.source, null, "a source outside the API's five categories is not shown (never as a link)");
  // Mixed scripts survive, clipped by code points, never splitting a surrogate pair.
  const mixed = M.declarationView(by.get("declared_agent · a1a0"));
  assert.equal(mixed.name, "Ωmega 智能体 агент مرحبا 🧪");
  assert.equal(mixed.source, "senti");
  assert.equal(M.clipCodePoints("🧪🧪🧪", 2), "🧪🧪");
  assert.equal(M.clipCodePoints("a̐bc", 2), "a̐");
  // A bidi override (refused by the API) is not displayed at all.
  assert.deepEqual(M.declarationView(by.get("unknown · e14a")), { kind: "unreadable", text: "self-declared text not shown: characters this page does not display", seq: 108 });
});

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
  for (const c of el.children) { if (c instanceof El) dump(c, out); else out.text.push(c.text); }
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
    return body === null ? new Response("{}", { status: 404 }) : new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
  });
  t.after(() => { for (const [name, desc] of saved) { if (desc) Object.defineProperty(globalThis, name, desc); else delete globalThis[name]; } });
  return { page: () => { const out = { text: [], attrs: [], html: [] }; for (const el of ids.values()) dump(el, out); return out; } };
}
const settle = async () => { for (let i = 0; i < 25; i += 1) await new Promise((r) => setImmediate(r)); };

test("an open tab shows the declarations as inert text, and a hide reaches it on the next poll", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"], now: Date.parse("2026-11-01T16:50:00Z") });
  let visitors = doc("visitors-declarations.json");
  const results = doc("results.json"), events = doc("events.json"), board = doc("board.json");
  const asked = [];
  const dom = installPage(t, (url) => {
    asked.push(url.pathname + url.search);
    const after = Number(url.searchParams.get("after") ?? 0);
    if (url.pathname === "/api/open/v1/door/results") return after >= results.next_after ? { ...results, items: [], has_more: false } : results;
    if (url.pathname === "/api/open/v1/door/events") return after >= events.next_after ? { ...events, events: [], has_more: false } : events;
    if (url.pathname === "/api/open/v1/door/board") return board;
    if (url.pathname === "/api/open/v1/door/visitors") return after >= visitors.next_after ? { ...visitors, items: [], has_more: false } : visitors;
    return null;
  });
  await import(`${LIVE}?declarations=1`);
  for (let k = 0; k < 6; k += 1) { t.mock.timers.tick(1000); await settle(); }
  let page = dom.page();
  const text = page.text.join("\n");
  // Visible: the selected run (5cb8) and its row show the newest declaration, labelled.
  assert.ok(text.includes("Ortho Placer"), "the declared name is on the page");
  assert.ok(text.includes("Testing whether spreading the DRAM out cools the CPUs"), "and the reason");
  assert.ok(text.includes(NOTE), `labelled "${NOTE}"`);
  assert.equal(text.includes("An older name"), false, "an older declaration of the same pass is not shown");
  // Hidden: the tombstone only.
  assert.ok(text.includes(HIDDEN));
  // HTML-looking text is text: present as text, never as markup or in an attribute.
  assert.ok(text.includes("<img src=x onerror=alert(1)>"));
  assert.equal(page.html.some((h) => h.includes("onerror") || h.includes("<script")), false, "no declaration in any markup");
  const declared = doc("visitors-declarations.json").items.filter((x) => x.declaration).flatMap((x) => [x.declaration.name, x.declaration.reason]).filter((v) => v.length > 3);
  for (const v of declared) assert.equal(page.attrs.some((a) => a.includes(v)), false, `never in an attribute, title or aria label: ${v.slice(0, 20)}`);
  // Clipped and refused text, unknown sources and a pass without a run never appear.
  assert.ok(text.includes(N64));
  assert.equal(text.includes(`${N64}Z`), false, "the 65th code point is clipped");
  assert.equal(text.includes("Ωmega 智能体 агент مرحبا 🧪"), true, "mixed scripts shown as written");
  assert.equal(text.includes("gnp.exe"), false, "a bidi override is not displayed");
  assert.equal(text.includes("example.invalid"), false, "an unknown source is not displayed");
  assert.equal(text.includes("No run here"), false, "a declaration with no run in the results is not shown");
  // The visitors feed is read from the start each poll (after=0): the whole window, replaced.
  assert.ok(asked.filter((a) => a.startsWith("/api/open/v1/door/visitors")).every((a) => /[?&]after=0(&|$)/.test(a)), asked.filter((a) => a.includes("visitors")).join(" "));
  // The operator hides seq 102 in place: same seq, a tombstone, the cursor does not move.
  visitors = { ...visitors, items: visitors.items.map((x) => (x.seq === 102 ? { seq: 102, at: x.at, class: x.class, purpose: x.purpose, short_id: x.short_id,
    label: x.label, event_kind: "declaration", declaration: null, hidden: "abuse" } : x)) };
  for (let k = 0; k < 6; k += 1) { t.mock.timers.tick(1000); await settle(); }
  page = dom.page();
  const after = [...page.text, ...page.attrs, ...page.html].join("\n");
  assert.equal(after.includes("Ortho Placer"), false, "the hidden name is gone from the whole DOM");
  assert.equal(after.includes("Testing whether spreading the DRAM out cools the CPUs"), false, "and its reason");
  assert.equal(after.includes("An older name"), false, "and the older declaration does not take its place");
  assert.ok(page.text.filter((s) => s.includes(HIDDEN)).length >= 2, "the run now reads hidden by the operator");
});
