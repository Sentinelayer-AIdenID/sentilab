// node --test test/livelab-names.test.mjs (from web/)
// Carter (push 4): a visitor that declares its name is shown by that name. Only through the exact relation the door
// publishes: a declaration on /visitors carries `arrival`, the seq of the arrival event from the same pass. The names
// map is built at render time from the current, ok and fresh visitors window; a hide or a failed read clears it on the
// next render. Never joined by short id. Runs carry no exact link to a visitor today, so a run shows a name only when
// its run record carries visit_arrival (an optional path, tested with a fixture; nothing sends it yet).
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

const walk = (el, out = []) => { if (!el) return out; out.push(el); for (const c of el.children ?? []) if (c instanceof El) walk(c, out); return out; };
const rows = () => walk(document.getElementById("visitorList")).filter((el) => el.className === "rec-row");
const rowOf = (seq) => rows().find((el) => el.getAttribute("title") === `seq ${seq}`);
const textOf = (el) => (el ? el.textContent : "");
const NOW = Date.parse("2026-11-01T18:40:00Z");
const NOTE = "self-declared, not verified";

// Two visitors that share the short id 82ea (seq 99 and seq 100). The declaration for the OLDER arrival is the
// NEWER declaration, so any join by short id or by order would swap the names.
function door({ runVisit = null, declare = null } = {}) {
  const base = doc("events.json"), results = doc("results.json"), board = doc("board.json");
  const proto = doc("visitors-declarations.json").items.find((i) => i.event_kind === "declaration" && i.declaration);
  const arrival = (seq, ago) => ({ seq, at: new Date(NOW - ago).toISOString(), kind: "arrival", class: "declared_agent", label: "declared_agent · 82ea",
    purpose: "place-chiplets", short_id: "82ea" });
  const runs = runVisit === null ? base.events : base.events.map((e) => (e.kind === "run" && e.short_id === "5cb8" ? { ...e, visit_arrival: runVisit } : e));
  const events = { ...base, events: [...runs, arrival(99, 4000), arrival(100, 2000)], next_after: 100 };
  const state = { hidden: false, fail: false };
  const decl = (seq, arrivalSeq, name, short = "82ea", cls = "declared_agent") => (state.hidden
    ? { seq, at: new Date(NOW - 1000).toISOString(), class: cls, purpose: "place-chiplets", short_id: short, label: `${cls} · ${short}`, event_kind: "declaration", hidden: "operator_hidden", declaration: null }
    : { ...proto, seq, at: new Date(NOW - 1000).toISOString(), class: cls, purpose: "place-chiplets", short_id: short, label: `${cls} · ${short}`, event_kind: "declaration", arrival: arrivalSeq,
      declaration: { ...proto.declaration, name, reason: "testing the door" } });
  const visitors = () => {
    const items = [decl(101, 100, "Visitor Beta"), decl(102, 99, "Visitor Alpha"), ...(declare ? [decl(103, declare.arrival, declare.name, declare.short, "unknown")] : [])];
    return { schema: "sentilab-door-visitors/1", items, next_after: 103, has_more: false, counts: { through_seq: 103 } };
  };
  const answer = (url) => {
    const after = Number(url.searchParams.get("after") ?? 0);
    if (url.pathname === "/api/open/v1/door/results") return after >= results.next_after ? { ...results, items: [], has_more: false } : results;
    if (url.pathname === "/api/open/v1/door/events") return after >= events.next_after ? { ...events, events: [], has_more: false } : events;
    if (url.pathname === "/api/open/v1/door/board") return board;
    if (url.pathname === "/api/open/v1/door/visitors") { if (state.fail) return undefined; const v = visitors(); return after >= v.next_after ? { ...v, items: [], has_more: false } : v; }
    return null;
  };
  return { answer, state };
}
async function open(t, tag, opts) {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"], now: NOW });
  const d = door(opts);
  const dom = installPage(t, d.answer);
  await import(`${LIVE}?names=${tag}`);
  for (let k = 0; k < 6; k += 1) { t.mock.timers.tick(500); await settle(); }
  return { dom, state: d.state };
}
const runSide = (dom) => ["runList", "modelTitle", "modelSub", "modelCap", "atlasSvg", "mobileRuns", "eventTitle", "eventSubtitle"]
  .flatMap((id) => dom.part(id).text).join(" ");

test("names: an arrival is named through its declaration's exact arrival seq, on the card, the strip and its record row", async (t) => {
  const { dom } = await open(t, "named");
  const card = textOf(document.getElementById("arrivalCard"));
  assert.equal(document.getElementById("arrivalCard").hidden, false, "seq 100 holds the card");
  assert.match(card, /Visitor Beta · self-declared, not verified · visit 82ea/);
  assert.match(textOf(document.getElementById("arrivalStrip")), /Visitor Alpha · self-declared, not verified · visit 82ea/);
  assert.match(textOf(rowOf(99)), /Visitor Alpha · self-declared, not verified · visit 82ea/);
  assert.match(textOf(rowOf(100)), /Visitor Beta · self-declared, not verified · visit 82ea/);
  // The name never goes into an attribute (title, aria-label, data): text nodes only.
  for (const id of ["arrivalCard", "arrivalStrip", "visitorList"]) assert.equal(dom.part(id).attrs.join(" ").includes("Visitor "), false, id);
});

test("names: two arrivals sharing a short id never swap names", async (t) => {
  const { dom } = await open(t, "swap");
  const card = dom.part("arrivalCard").text.join(" "), strip = dom.part("arrivalStrip").text.join(" ");
  assert.match(card, /Visitor Beta/); assert.equal(card.includes("Visitor Alpha"), false, "the card (seq 100) is not seq 99's visitor");
  assert.match(strip, /Visitor Alpha/); assert.equal(strip.includes("Visitor Beta"), false, "the strip item (seq 99) is not seq 100's visitor");
  assert.equal(textOf(rowOf(99)).includes("Visitor Beta"), false); assert.equal(textOf(rowOf(100)).includes("Visitor Alpha"), false);
});

test("names: a hide clears the name on the next render", async (t) => {
  const { dom, state } = await open(t, "hide");
  assert.match(dom.part("arrivalStrip").text.join(" "), /Visitor Alpha/);
  state.hidden = true;
  for (let k = 0; k < 10; k += 1) { t.mock.timers.tick(500); await settle(); }
  const page = dom.page().text.join(" ");
  assert.equal(page.includes("Visitor Alpha"), false, "hidden: no name anywhere");
  assert.equal(page.includes("Visitor Beta"), false, "hidden: no name anywhere");
  assert.match(dom.part("arrivalStrip").text.join(" "), /visit 82ea/, "the visit id stays");
});

test("names: a failed read clears every name", async (t) => {
  const { dom, state } = await open(t, "fail");
  assert.match(textOf(document.getElementById("arrivalCard")), /Visitor Beta · self-declared, not verified/);
  state.fail = true;
  for (let k = 0; k < 10; k += 1) { t.mock.timers.tick(500); await settle(); }
  const page = dom.page().text.join(" ");
  assert.equal(page.includes("Visitor Alpha") || page.includes("Visitor Beta"), false, "a failed read leaves no name on the page");
});

test("names: a run never shows a name without visit_arrival, even when its visitor's arrival is named", async (t) => {
  const { dom } = await open(t, "norun", { declare: { arrival: 83, name: "Visitor Gamma", short: "5cb8" } });
  assert.match(textOf(rowOf(83)), /Visitor Gamma · self-declared, not verified · visit 5cb8/, "the arrival itself is named");
  assert.equal(runSide(dom).includes("Visitor Gamma"), false, "no run, step avatar, title or caption carries the name");
  assert.match(dom.part("runList").text.join(" "), /The layout from visit 5cb8/, "the run keeps its visit id");
});

test("names: a run record that carries visit_arrival is titled by that arrival's name (fixture only; nothing sends it yet)", async (t) => {
  const { dom, state } = await open(t, "visit", { runVisit: 83, declare: { arrival: 83, name: "Visitor Gamma", short: "5cb8" } });
  const rail = textOf(document.getElementById("runList"));
  assert.match(rail, /Visitor Gamma's layout/);
  assert.match(rail, /self-declared, not verified/);
  state.hidden = true;
  for (let k = 0; k < 10; k += 1) { t.mock.timers.tick(500); await settle(); }
  assert.equal(runSide(dom).includes("Visitor Gamma"), false, "a hide clears the run's name");
  assert.match(dom.part("runList").text.join(" "), /The layout from visit 5cb8/);
});
