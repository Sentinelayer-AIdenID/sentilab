// node --test test/livelab-focus.test.mjs (from web/)
// Root (04927b9 P2, restated 23:19Z): the proposals timeline was rebuilt every second, so a keyboard-focused proposal,
// or its package action, was removed on the next tick and focus was lost. Rows are now stable per FULL run id and
// updated in place; a hide still clears a declared name on the next render; a new run adds a row and replaces none.
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
  addEventListener(type, fn) { ((this.listeners ??= {})[type] ??= []).push(fn); } removeEventListener() {} focus() {} showModal() {} close() {} remove() {}
  click() { for (const fn of this.listeners?.click ?? []) fn({ type: "click", target: this }); }
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
  const on = (target) => (type, fn) => { ((target.listeners ??= {})[type] ??= []).push(fn); };
  // The page wires every [data-modal] button through querySelectorAll: one stands in for "Expand the door atlas".
  const atlasButton = new El("button"); atlasButton.dataset.modal = "atlas";
  const doc = { hidden: false, visibilityState: "visible", activeElement: null, body: new El("body"),
    getElementById: (id) => { if (!ids.has(id)) ids.set(id, new El(id)); return ids.get(id); }, querySelector: () => null,
    querySelectorAll: (sel) => (sel === "[data-modal]" ? [atlasButton] : []),
    createElement: (tag) => new El(tag), createElementNS: (_, tag) => new El(tag), removeEventListener() {} };
  doc.addEventListener = on(doc);
  define("document", doc);
  const win = { removeEventListener() {}, devicePixelRatio: 1 };
  win.addEventListener = on(win);
  define("window", win);
  define("location", { hostname: "sentilab.aidenid.com", search: "", pathname: "/sentilab/live/" });
  define("matchMedia", (q) => ({ matches: /reduced-motion/.test(String(q)) ? reduced : true, addEventListener() {} }));
  define("sessionStorage", { getItem: () => "yes", setItem() {} });
  define("ResizeObserver", class { observe() {} disconnect() {} });
  define("requestAnimationFrame", (f) => setTimeout(() => f(Date.now()), 16));
  define("cancelAnimationFrame", (id) => clearTimeout(id));
  define("fetch", async (input) => {
    const url = new URL(String(input), "https://sentilab.aidenid.com");
    const body = answer(url);
    if (body === "hang") return new Promise(() => {});   // a read that never answers
    if (body === "network") throw new TypeError("network error");
    if (body === undefined) return new Response("{}", { status: 502 });
    return body === null ? new Response("{}", { status: 404 }) : new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
  });
  t.after(() => { for (const [name, desc] of saved) { if (desc) Object.defineProperty(globalThis, name, desc); else delete globalThis[name]; } });
  const fire = (target, type, extra = {}) => { for (const fn of target.listeners?.[type] ?? []) fn({ type, ...extra }); };
  return { atlasButton, fire: (where, type, extra) => fire(where === "window" ? win : doc, type, extra), page: () => { const out = { text: [], attrs: [], html: [] }; for (const el of ids.values()) dump(el, out); return out; },
    part: (id) => (ids.has(id) ? dump(ids.get(id)) : { text: [], attrs: [], html: [] }) };
}
const settle = async () => { for (let i = 0; i < 25; i += 1) await new Promise((r) => setImmediate(r)); };

const walk = (el, out = []) => { if (!el) return out; out.push(el); for (const c of el.children ?? []) if (c instanceof El) walk(c, out); return out; };
const NOW = Date.parse("2026-11-01T20:00:00Z");
const settleFor = async (t, ms, step = 500) => { for (let k = 0; k < ms / step; k += 1) { t.mock.timers.tick(step); await settle(); } };
// The door as recorded (nine runs), then runs proposed live: add() puts a run's records in the events feed (each with
// its own time) and its row in the results feed; arrive() records a visitor's arrival; declare() publishes a declaration
// on /visitors that carries that arrival's seq.
function door() {
  const base = doc("events.json"), results = doc("results.json"), board = doc("board.json");
  const events = [], items = [], decls = [];
  let seq = base.next_after, rseq = results.next_after;
  const state = { hidden: false, hang: false, answered: 0 };
  // A run's result row carries its own queued record's seq as `arrival`, as the door's does (that orders the results).
  const add = (hex, states, { at, visitArrival = null, held = false } = {}) => {
    const id = `open-0000${hex}-${"0".repeat(28)}${hex}`, status = states.at(-1), first = seq + 1;
    for (const st of states) { seq += 1; events.push({ seq, held, at: new Date(at).toISOString(), kind: "run", class: "unknown", label: `unknown · ${hex}`, run_id: id, short_id: hex, state: st, ...(visitArrival ? { visit_arrival: visitArrival } : {}) }); }
    rseq += 1;
    items.push({ ...results.items[0], held, id, short_id: hex, label: `unknown · ${hex}`, class: "unknown", arrival: first, seq: rseq, status,
      ...(status === "rejected" ? { codes: ["margin"], reason: null, result: null, summary: "rejected" } : {}) });
  };
  // A proposal the page cannot read yet (its records exist, but the page reads them later).
  const release = () => { for (const x of [...events, ...items]) x.held = false; };
  const strip = (x) => { const { held, ...rest } = x; return rest; };
  const arrive = (hex, at) => { seq += 1; events.push({ seq, at: new Date(at).toISOString(), kind: "arrival", class: "declared_agent", label: `declared_agent · ${hex}`, purpose: "place-chiplets", short_id: hex }); return seq; };
  const declare = (arrival, name, hex) => { seq += 1; decls.push({ seq, arrival, name, hex }); };
  const proto = doc("visitors-declarations.json").items.find((i) => i.event_kind === "declaration" && i.declaration);
  const answer = (url) => {
    if (state.hang) return "hang";   // every read from now on never answers
    state.answered += 1;
    const after = Number(url.searchParams.get("after") ?? 0);
    if (url.pathname === "/api/open/v1/door/results") {
      if (after < results.next_after) return results;
      const page = items.filter((i) => i.seq > after && !i.held).map(strip);
      return { ...results, items: page, next_after: page.length ? page.at(-1).seq : after, has_more: false };
    }
    if (url.pathname === "/api/open/v1/door/events") {
      if (after < base.next_after) return base;
      const ready = events.filter((e) => !e.held), cut = events.find((e) => e.held)?.seq ?? Infinity;
      const page = ready.filter((e) => e.seq > after && e.seq < cut).map(strip);
      return { ...base, events: page, next_after: page.length ? page.at(-1).seq : after, has_more: false };
    }
    if (url.pathname === "/api/open/v1/door/board") return board;
    if (url.pathname === "/api/open/v1/door/visitors") {
      const list = decls.map((d) => (state.hidden
        ? { seq: d.seq, at: new Date(NOW).toISOString(), class: "declared_agent", purpose: "place-chiplets", short_id: d.hex, label: `declared_agent · ${d.hex}`, event_kind: "declaration", hidden: "operator_hidden", declaration: null }
        : { ...proto, seq: d.seq, at: new Date(NOW).toISOString(), class: "declared_agent", purpose: "place-chiplets", short_id: d.hex, label: `declared_agent · ${d.hex}`, event_kind: "declaration",
          arrival: d.arrival, declaration: { ...proto.declaration, name: d.name, reason: "testing the door" } }));
      const through = Math.max(seq, ...decls.map((d) => d.seq));
      return { schema: "sentilab-door-visitors/1", items: list.filter((i) => i.seq > after), next_after: through, has_more: false, counts: { through_seq: through } };
    }
    return null;
  };
  return { answer, add, arrive, declare, release, state };
}
let lastPage = null;
async function open(t, tag) {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"], now: NOW });
  const d = door();
  lastPage = installPage(t, d.answer);
  await import(`${LIVE}?proposals=${tag}`);
  await settleFor(t, 4000);
  return d;
}
const rows = () => walk(document.getElementById("proposalList")).filter((el) => el.tag === "button" && /^proposal\b/.test(el.className));
const text = (el) => el.textContent;



// Root (04927b9 P2): the timeline must not lose keyboard focus. These checks use a DOM that knows focus: focus() makes
// an element document.activeElement, and removing the focused element from the tree (its parent's children are
// replaced without it) moves focus back to the body, as a browser does.
const LICENSED = "/sentilab/packages/licensed-runs.json";
const allowlist = (...ids) => ({ schema: "sentilab-licensed-runs/1", items: ids.map((run_id) => ({ run_id, visit: null, owner_role: "team", licence: "CC BY 4.0", confirmed_by: "the team", confirmed_at: "2026-11-01T22:30:00Z" })) });
function focusAware(t) {
  const proto = Object.getPrototypeOf(document.body);
  const saved = { focus: proto.focus, replace: proto.replaceChildren };
  const inTree = (nodes, target) => nodes.some((n) => n === target || (n?.children && inTree(n.children, target)));
  proto.focus = function focus() { document.activeElement = this; };
  proto.replaceChildren = function replaceChildren(...nodes) {
    const before = this.children, active = document.activeElement;
    saved.replace.apply(this, nodes);
    if (active && active !== document.body && inTree(before, active) && !inTree(this.children, active)) document.activeElement = document.body;
  };
  t.after(() => { proto.focus = saved.focus; proto.replaceChildren = saved.replace; });
}
async function openWith(t, tag, allow = null) {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"], now: NOW });
  const d = door();
  installPage(t, (url) => (url.pathname === LICENSED ? allow : d.answer(url)));
  focusAware(t);
  await import(`${LIVE}?focus=${tag}`);
  await settleFor(t, 4000);
  return d;
}
const RAW = () => doc("results.json");
const packButton = () => walk(document.getElementById("proposalList")).find((el) => el.tag === "button" && /\bengineer-package\b/.test(el.className));

test("focus: a keyboard-focused proposal is the same node, and still focused, after three clock ticks", async (t) => {
  await openWith(t, "row");
  const target = rows()[1];
  target.focus();
  assert.equal(document.activeElement, target);
  await settleFor(t, 3000, 1000);
  assert.equal(rows()[1], target, "the same node, not a rebuilt one");
  assert.equal(document.activeElement, target, "focus kept");
});

test("focus: the package action is the same node, and still focused, after three clock ticks", async (t) => {
  const followed = RAW().items.find((x) => x.short_id === "5cb8");
  await openWith(t, "pack", allowlist(followed.id));
  const pack = packButton();
  assert.ok(pack, "the selected, licensed proposal has its package action");
  pack.focus();
  await settleFor(t, 3000, 1000);
  assert.equal(packButton(), pack, "the same node");
  assert.equal(document.activeElement, pack, "focus kept");
});

test("focus: a hide still clears the row's declared name on the next render, in the same row", async (t) => {
  const d = await openWith(t, "hide");
  const arrival = d.arrive("9f8c", Date.now());
  d.declare(arrival, "Visitor Gamma", "9f8c");
  d.add("9f8c", ["queued", "evaluating", "evaluated", "replaying", "reproduced"], { at: Date.now(), visitArrival: arrival });
  await settleFor(t, 6000);
  const row = rows().find((el) => el.textContent.includes("9f8c"));
  assert.match(row.textContent, /Visitor Gamma · self-declared, not verified/);
  row.focus();
  d.state.hidden = true;
  await settleFor(t, 5000);
  assert.equal(rows().find((el) => el.textContent.includes("9f8c")), row, "the same row");
  assert.equal(row.textContent.includes("Visitor Gamma"), false, "the name is gone");
  assert.equal(document.activeElement, row, "and focus stayed on it");
});

test("focus: a new run adds its row without replacing the others, and focus stays", async (t) => {
  const d = await openWith(t, "add");
  const before = rows();
  before[2].focus();
  d.add("a7a7", ["queued", "evaluating", "evaluated", "replaying", "reproduced"], { at: Date.now() });
  await settleFor(t, 5000);
  const after = rows();
  assert.equal(after.length, before.length + 1);
  assert.match(after[0].textContent, /visit a7a7/, "the new run on top");
  assert.deepEqual(after.slice(1), before, "every earlier row is the same node");
  assert.equal(document.activeElement, before[2], "focus stays on the same row");
});
