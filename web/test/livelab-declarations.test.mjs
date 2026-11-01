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
  // Each declaration event stands on its own, by seq (root's P2: no join by label). bySeq is only this test's index.
  const bySeqMap = new Map(page.items.map((x) => [x.seq, x]));
  const by = { get: (label) => [...bySeqMap.values()].filter((x) => x.label === label && x.kind === "declaration").sort((a, b) => b.seq - a.seq)[0] };
  const list = M.declarationList(page.items);
  assert.deepEqual(list.map((d) => d.seq), [109, 108, 107, 106, 105, 104, 103, 102, 101], "every declaration event, newest first, one entry each");
  assert.equal(list.find((d) => d.seq === 101).view.name, "An older name", "an older declaration is its own entry");
  assert.deepEqual(M.declarationView(by.get("unknown · 5cb8")), { kind: "declared", name: "Ortho Placer",
    reason: "Testing whether spreading the DRAM out cools the CPUs", source: "direct", note: NOTE, seq: 102 });
  // Hidden: the tombstone, and nothing else.
  assert.deepEqual(M.declarationView(by.get("unknown · c991")), { kind: "hidden", text: HIDDEN, seq: 103 });
  // A hidden row that wrongly still carries text shows none of it.
  const leaky = M.declarationList(M.normalizeVisitors({ ...doc("visitors-declarations.json"), items: [{ seq: 7, at: null, class: "unknown", purpose: null,
    short_id: "abcd", label: "unknown · abcd", event_kind: "declaration", declaration: { name: "leak", reason: "leak" }, hidden: "abuse" }] }).items);
  assert.deepEqual(leaky[0].view, { kind: "hidden", text: HIDDEN, seq: 7 });
  assert.equal(JSON.stringify(leaky).includes("leak"), false, "a hidden entry carries none of the text");
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
    if (body === undefined) return new Response("{}", { status: 502 });
    return body === null ? new Response("{}", { status: 404 }) : new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
  });
  t.after(() => { for (const [name, desc] of saved) { if (desc) Object.defineProperty(globalThis, name, desc); else delete globalThis[name]; } });
  return { page: () => { const out = { text: [], attrs: [], html: [] }; for (const el of ids.values()) dump(el, out); return out; },
    part: (id) => (ids.has(id) ? dump(ids.get(id)) : { text: [], attrs: [], html: [] }) };
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
  assert.ok(text.includes("An older name"), "an older declaration is its own entry in the list (no collapsing by pass)");
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
  assert.ok(text.includes("No run here"), "a declaration is listed whether or not its pass has a run (it is never joined to one)");
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
  assert.ok(after.includes("An older name"), "the older declaration, a separate event the operator did not hide, stays as its own entry");
  assert.ok(page.text.filter((s) => s.includes(HIDDEN)).length >= 2, "the hidden entry now reads hidden by the operator (and seq 103 still does)");
});

// Root's P2 (17:18Z): a class and a 4-hex short id can be shared by unrelated runs, so a declaration is never joined
// to a run, a card or a row by label or short id. Declarations are their own list, by event seq, newest first.
test("root's P2: declarations are a separate list by seq; two runs sharing a label never carry one", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"], now: Date.parse("2026-11-01T17:20:00Z") });
  const results = doc("results.json"), events = doc("events.json"), board = doc("board.json");
  // A second run with the same label as 5cb8 (a 16-bit collision), but its own full run id.
  const twin = { ...results.items.find((x) => x.short_id === "5cb8"), id: "open-0000beef-0000000000000000000000000000beef", arrival: 90, seq: 94 };
  const res = { ...results, items: [...results.items, twin], next_after: 94 };
  let visitors = { ...doc("visitors-declarations.json") };
  visitors.items = visitors.items.filter((x) => x.seq !== 101);             // one declaration for that label: seq 102
  const dom = installPage(t, (url) => {
    const after = Number(url.searchParams.get("after") ?? 0);
    if (url.pathname === "/api/open/v1/door/results") return after >= res.next_after ? { ...res, items: [], has_more: false } : res;
    if (url.pathname === "/api/open/v1/door/events") return after >= events.next_after ? { ...events, events: [], has_more: false } : events;
    if (url.pathname === "/api/open/v1/door/board") return board;
    if (url.pathname === "/api/open/v1/door/visitors") return after >= visitors.next_after ? { ...visitors, items: [], has_more: false } : visitors;
    return null;
  });
  await import(`${LIVE}?declarations=separate`);
  for (let k = 0; k < 6; k += 1) { t.mock.timers.tick(1000); await settle(); }
  const part = (id) => { const out = dom.part(id); return [...out.text, ...out.attrs, ...out.html].join("\n"); };
  const runsRail = part("runList") + part("mobileRuns") + part("visitorList") + part("modelTitle") + part("modelSub");
  assert.equal(runsRail.includes("Ortho Placer"), false, "no run row, card or title carries the declaration");
  assert.equal(runsRail.includes(NOTE), false, "nor its label");
  const list = dom.part("declList").text.join("\n");
  assert.equal(list.split("Ortho Placer").length - 1, 1, "the declaration appears once, in the declarations list");
  assert.ok(list.includes(NOTE));
  assert.ok(list.includes("Testing whether spreading the DRAM out cools the CPUs"));
  // Newest first, by seq: 106 (mixed scripts) before 105 before 102.
  const order = ["Ωmega", "Spreads the DRAM dies to the corners", "Ortho Placer"].map((s) => list.indexOf(s));
  assert.ok(order.every((i) => i >= 0) && order[0] < order[1] && order[1] < order[2], `newest first: ${order}`);
  // Hide seq 102: only that entry changes.
  const before = list;
  visitors = { ...visitors, items: visitors.items.map((x) => (x.seq === 102 ? { seq: 102, at: x.at, class: x.class, purpose: x.purpose, short_id: x.short_id,
    label: x.label, event_kind: "declaration", declaration: null, hidden: "privacy" } : x)) };
  for (let k = 0; k < 6; k += 1) { t.mock.timers.tick(1000); await settle(); }
  const afterList = dom.part("declList").text.join("\n");
  assert.equal(afterList.includes("Ortho Placer"), false, "the hidden entry's text is gone");
  assert.ok(afterList.includes(HIDDEN), "and reads hidden by the operator");
  for (const s of ["Ωmega 智能体 агент مرحبا 🧪", N64, "<img src=x onerror=alert(1)>"]) assert.ok(before.includes(s) && afterList.includes(s), `other entries unchanged: ${s.slice(0, 12)}`);
  assert.equal(part("runList").includes(HIDDEN) || part("visitorList").includes(HIDDEN), false, "the hide does not touch any run");
});

// Root's P2 (17:21Z): a row without a declaration must not print the word "null" (native append turns null into text).
test("no run row, card or list prints a literal null", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"], now: Date.parse("2026-11-01T17:26:00Z") });
  const results = doc("results.json"), events = doc("events.json"), board = doc("board.json"), visitors = doc("visitors-declarations.json");
  const dom = installPage(t, (url) => {
    const after = Number(url.searchParams.get("after") ?? 0);
    if (url.pathname === "/api/open/v1/door/results") return after >= results.next_after ? { ...results, items: [], has_more: false } : results;
    if (url.pathname === "/api/open/v1/door/events") return after >= events.next_after ? { ...events, events: [], has_more: false } : events;
    if (url.pathname === "/api/open/v1/door/board") return board;
    if (url.pathname === "/api/open/v1/door/visitors") return after >= visitors.next_after ? { ...visitors, items: [], has_more: false } : visitors;
    return null;
  });
  await import(`${LIVE}?declarations=nonull`);
  for (let k = 0; k < 6; k += 1) { t.mock.timers.tick(1000); await settle(); }
  for (const id of ["runList", "mobileRuns", "visitorList", "declList", "modelTitle", "modelSub", "metricValue", "metricDescription", "eventTitle"]) {
    const bad = dom.part(id).text.filter((s) => /\bnull\b|\bundefined\b/.test(s));
    assert.deepEqual(bad, [], `#${id} has no literal null or undefined`);
  }
});

// Root's P2 (17:23Z): a bounded recent window with exact boundaries. Reading from after=0 for a fixed number of pages
// silently missed the newest declarations once the history passed 2,000 arrivals.
function history(n, { declareAt = n, hiddenAt = null } = {}) {
  const items = [];
  for (let seq = 1; seq <= n; seq += 1) {
    const base = { seq, at: "2026-11-01T17:00:00Z", class: "unknown", purpose: null, short_id: (seq % 65536).toString(16).padStart(4, "0").slice(-4), event_kind: "passive_arrival", declaration: null };
    base.label = `unknown · ${base.short_id}`;
    if (seq === declareAt) Object.assign(base, { event_kind: "declaration", declaration: { notice_version: "sentilab-public-visitor/1", name: "Newest Declarer", reason: "Arrived as record 2001", source: "direct" } });
    if (seq === hiddenAt) Object.assign(base, { event_kind: "declaration", declaration: null, hidden: "spam" });
    items.push(base);
  }
  return items;
}
function pagedVisitors(itemsRef, asked) {
  return async (url) => {
    const u = new URL(String(url), "https://x");
    asked.push(u.search);
    const after = Number(u.searchParams.get("after")), limit = Number(u.searchParams.get("limit") ?? 100);
    const rest = itemsRef().filter((x) => x.seq > after);
    const page = rest.slice(0, limit);
    const all = itemsRef();
    return new Response(JSON.stringify({ schema: "sentilab-door-visitors/1", items: page, next_after: page.length ? page.at(-1).seq : after,
      has_more: rest.length > limit, counts: { through_seq: all.at(-1).seq } }), { status: 200 });
  };
}

test("root's P2: the visitors window is the latest records, read to its end; the newest declaration is shown", async () => {
  let items = history(2001);
  const asked = [];
  const fetchImpl = pagedVisitors(() => items, asked);
  const got = await M.fetchVisitorsWindow({ fetchImpl, latest: 0 });
  assert.equal(got.ok, true);
  assert.equal(got.partial, false, "read to the end of the window");
  assert.deepEqual(M.declarationList(got.items).map((d) => d.seq), [2001]);
  assert.equal(M.declarationList(got.items)[0].view.name, "Newest Declarer", "the newest declaration (seq 2001) is in the list");
  assert.ok(got.from === 1000 && got.through === 2001, `the window is the latest records: from ${got.from} through ${got.through}`);
  // With a known latest seq the first request already starts at the window, rounded down to a multiple of 100 so tabs
  // ask for the same URLs (and share the proxy's micro-cache); rounding only widens the window.
  asked.length = 0;
  await M.fetchVisitorsWindow({ fetchImpl, latest: 2001 });
  assert.match(asked[0], /after=1000(&|$)/, `starts at latest - 1000, rounded down: ${asked[0]}`);
  assert.deepEqual([2001, 2050, 2099, 1099, 999, 0, -5].map(M.visitorsWindowStart), [1000, 1000, 1000, 0, 0, 0, 0]);
  // A hide inside the window reaches the next read.
  items = history(2001, { hiddenAt: 2001 });
  const hidden = await M.fetchVisitorsWindow({ fetchImpl, latest: 2001 });
  assert.deepEqual(M.declarationList(hidden.items).map((d) => d.view.kind), ["hidden"]);
  // A page cap with has_more still true is an explicit partial read, never a plain ok.
  items = history(2001);
  const capped = await M.fetchVisitorsWindow({ fetchImpl, latest: 2001, maxPages: 1 });
  assert.equal(capped.ok, true);
  assert.equal(capped.partial, true, "has_more at the cap: partial");
  // A failed page is an error, not a short list.
  const failing = await M.fetchVisitorsWindow({ fetchImpl: async () => new Response("{}", { status: 502 }), latest: 2001 });
  assert.deepEqual([failing.ok, failing.error], [false, "answered 502"]);
});

test("the declarations list says when it is partial or unavailable", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"], now: Date.parse("2026-11-01T17:30:00Z") });
  const results = doc("results.json"), events = doc("events.json"), board = doc("board.json");
  let mode = "error";
  const dom = installPage(t, (url) => {
    const after = Number(url.searchParams.get("after") ?? 0);
    if (url.pathname === "/api/open/v1/door/results") return after >= results.next_after ? { ...results, items: [], has_more: false } : results;
    if (url.pathname === "/api/open/v1/door/events") return after >= events.next_after ? { ...events, events: [], has_more: false } : events;
    if (url.pathname === "/api/open/v1/door/board") return board;
    if (url.pathname === "/api/open/v1/door/visitors") return mode === "error" ? undefined : { schema: "sentilab-door-visitors/1", items: history(3).filter((x) => x.seq > after).slice(0, 1),
      next_after: Math.min(3, after + 1), has_more: after + 1 < 3, counts: { through_seq: 3 } };
    return null;
  });
  await import(`${LIVE}?declarations=states`);
  for (let k = 0; k < 6; k += 1) { t.mock.timers.tick(1000); await settle(); }
  assert.match(dom.part("declList").text.join(" "), /unavailable/i, "a failing feed reads unavailable, not an empty list");
});
