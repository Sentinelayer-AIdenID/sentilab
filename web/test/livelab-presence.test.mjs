// node --test test/livelab-presence.test.mjs (from web/)
// Carter (20:13Z): when a proposal is selected, say whether its agent is still here. Exact only: through the run
// record's visit_arrival, "the agent" is that pass (its arrival, its declarations, and every run with the same
// visit_arrival); without it, only the run's own records, worded as such. It is last recorded activity, not presence
// detection, and the tooltip says so.
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
  const state = { hidden: false };
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
async function open(t, tag) {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"], now: NOW });
  const d = door();
  installPage(t, d.answer);
  await import(`${LIVE}?proposals=${tag}`);
  await settleFor(t, 4000);
  return d;
}
const rows = () => walk(document.getElementById("proposalList")).filter((el) => el.tag === "button" && /^proposal\b/.test(el.className));
const text = (el) => el.textContent;


const presence = () => document.getElementById("modelPresence");
const selectedRow = () => rows().find((el) => /\bselected\b/.test(el.className));
const TITLE = "Last recorded activity, not presence detection";
const FIVE = ["queued", "evaluating", "evaluated", "replaying", "reproduced"];

test("presence: through visit_arrival, the selected proposal's agent is still here while its last activity is under 10 minutes old, then no longer present", async (t) => {
  const d = await open(t, "bound");
  const arrival = d.arrive("9f8c", Date.now());
  d.declare(arrival, "Visitor Gamma", "9f8c");
  d.add("9f8c", FIVE, { at: Date.now(), visitArrival: arrival });
  await settleFor(t, 6000);
  assert.match(presence().textContent, /^Agent still here · last active just now$/);
  assert.equal(presence().getAttribute("title"), TITLE, "the tooltip says what it is");
  assert.match(selectedRow().textContent, /Agent still here · last active just now/, "on the selected timeline row too");
  await settleFor(t, 9 * 60000, 1000);
  assert.match(presence().textContent, /^Agent still here · last active 9 min ago$/);
  await settleFor(t, 2 * 60000, 1000);
  assert.match(presence().textContent, /^Agent no longer present · last active 11 min ago$/);
  assert.match(selectedRow().textContent, /Agent no longer present · last active 11 min ago/);
});

test("presence: a later run of the same pass (same visit_arrival) is that agent's activity too", async (t) => {
  const d = await open(t, "again");
  const arrival = d.arrive("9f8c", Date.now());
  d.add("9f8c", FIVE, { at: Date.now(), visitArrival: arrival });
  await settleFor(t, 6000);
  const first = rows()[0];
  first.click();
  await settleFor(t, 12 * 60000, 1000);
  assert.match(presence().textContent, /^Agent no longer present · last active 12 min ago$/);
  d.add("9f8d", FIVE, { at: Date.now(), visitArrival: arrival });
  await settleFor(t, 6000);
  assert.match(presence().textContent, /^Agent still here · last active just now$/, "the same pass proposed again just now");
});

test("presence: without visit_arrival only the run's own records count, worded as such", async (t) => {
  const d = await open(t, "unbound");
  d.arrive("9f8c", Date.now());
  d.add("9f8c", FIVE, { at: Date.now() });
  await settleFor(t, 6000);
  assert.match(presence().textContent, /^This run’s last record: just now$/);
  await settleFor(t, 3 * 60000, 1000);
  assert.match(presence().textContent, /^This run’s last record: 3 min ago$/);
  assert.equal(/Agent (still here|no longer present)/.test(presence().textContent + selectedRow().textContent), false, "no claim about an agent without the exact link");
  assert.equal(presence().getAttribute("title"), TITLE);
});
