// node --test test/livelab-proposals.test.mjs (from web/)
// Carter (19:59Z): a timeline of the proposed runs, newest at top, with when each was proposed ("just now", "1 min
// ago"), "New proposal" on the ones that just arrived, a check mark once the door received it, and who proposed it.
// Root (20:01Z): the time is the run's own submission time; the check mark means "Submission accepted" (the door's intake
// accepted it: a queued record), with the evaluation's outcome on its own line; a proposal refused at intake gets the
// refusal mark and reason instead; a name only through the run record's exact visit_arrival, never a short id.
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

test("proposals: one row per run, newest at top, each with its submission time (its first record's own time)", async (t) => {
  const d = await open(t, "order");
  assert.equal(rows().length, 9, "the nine runs held at the first read");
  d.add("a001", ["queued", "evaluating", "evaluated", "replaying", "reproduced"], { at: Date.now() });
  await settleFor(t, 60000);
  d.add("b002", ["queued", "evaluating", "evaluated", "replaying", "reproduced"], { at: Date.now() });
  await settleFor(t, 4000);
  let r = rows().map(text);
  assert.match(r[0], /^Proposal from visit b002.*just now/); assert.match(r[1], /^Proposal from visit a001.*1 min ago/);
  // c003 is proposed now, but the page reads it two minutes later: its row says when it was proposed.
  d.add("c003", ["queued", "evaluating", "evaluated", "replaying", "reproduced"], { at: Date.now(), held: true });
  await settleFor(t, 120000, 1000);
  d.release();
  await settleFor(t, 4000);
  r = rows().map(text);
  assert.equal(r.length, 12);
  assert.match(r[0], /^Proposal from visit c003/, "newest at top"); assert.match(r[1], /^Proposal from visit b002/); assert.match(r[2], /^Proposal from visit a001/);
  assert.match(r[0], /2 min ago/, "the submission time, never the time the page read it");
  await settleFor(t, 10 * 60000, 1000);
  r = rows().map(text);
  assert.match(r[0], /12 min ago/, "relative times follow the clock"); assert.match(r[2], /13 min ago/);
});

test("proposals: the check mark means the door's intake received it; a proposal refused at intake shows the refusal and its reason", async (t) => {
  const d = await open(t, "marks");
  d.add("d004", ["queued", "evaluating", "evaluated", "replaying", "reproduced"], { at: Date.now() });
  d.add("e005", ["rejected"], { at: Date.now() });
  await settleFor(t, 4000);
  const byShort = (hex) => rows().find((el) => text(el).includes(`visit ${hex}`));
  const received = (el) => walk(el).some((x) => x.tag === "small" && x.className === "proposal-received");
  assert.ok(received(byShort("d004")), "a queued proposal is received"); assert.match(text(byShort("d004")), /Submission accepted.*(Simulating|Accepted)/);
  assert.equal(received(byShort("e005")), false, "refused at intake: no check mark");
  assert.match(text(byShort("e005")), /Refused · /, "the refusal and its reason");
  assert.ok(walk(byShort("e005")).some((x) => x.tag === "svg" && /refused/.test(x.getAttribute("class") ?? "")), "the refusal mark");
  for (const el of rows().filter((x) => !text(x).includes("e005"))) assert.ok(received(el), `received: ${text(el)}`);
});

test("proposals: New proposal only on runs that arrived live, and it ends after 15 minutes", async (t) => {
  const d = await open(t, "badge");
  assert.equal(rows().some((el) => text(el).includes("New proposal")), false, "never on runs held at the first read");
  d.add("f006", ["queued", "evaluating", "evaluated", "replaying", "reproduced"], { at: Date.now() });
  await settleFor(t, 4000);
  assert.match(text(rows()[0]), /Proposal from visit f006.*New proposal/);
  assert.equal(rows().filter((el) => text(el).includes("New proposal")).length, 1);
  await settleFor(t, 15 * 60000, 1000);
  assert.equal(rows().some((el) => text(el).includes("New proposal")), false, "it ends at its deadline");
});

test("proposals: a declared name only through the run record's visit_arrival, and a hide removes it", async (t) => {
  const d = await open(t, "names");
  const arrival = d.arrive("9f8c", Date.now());
  d.declare(arrival, "Visitor Gamma", "9f8c");
  d.add("9f8c", ["queued", "evaluating", "evaluated", "replaying", "reproduced"], { at: Date.now(), visitArrival: arrival });
  d.add("9f8d", ["queued", "evaluating", "evaluated", "replaying", "reproduced"], { at: Date.now() });
  await settleFor(t, 6000);
  const named = rows().find((el) => text(el).includes("9f8c"));
  assert.match(text(named), /Visitor Gamma · self-declared, not verified · visit 9f8c/);
  assert.equal(rows().filter((el) => text(el).includes("Visitor Gamma")).length, 1, "no other row carries the name");
  assert.match(text(rows().find((el) => text(el).includes("9f8d"))), /^Proposal from visit 9f8d/);
  d.state.hidden = true;
  await settleFor(t, 5000);
  assert.equal(rows().some((el) => text(el).includes("Visitor Gamma")), false, "a hide removes the name from the timeline");
  assert.match(text(rows().find((el) => text(el).includes("9f8c"))), /Proposal from visit 9f8c/);
});

// Review (23:38Z): a row that is not new must not print "null". Native replaceChildren turns a null child into the text
// "null" (the recording DOM does the same), so an absent badge is left out, never passed as null.
test("proposals: a row without the New proposal badge never shows the word null", async (t) => {
  await open(t, "no-null");
  const list = document.getElementById("proposalList");
  const all = walk(list).flatMap((el) => (el.children ?? []).filter((c) => !(c && typeof c === "object" && "tag" in c)).map((c) => c.text));
  assert.ok(rows().length > 0, "rows are listed");
  assert.equal(all.some((s) => s === "null"), false, "no text node is the word null");
  assert.equal(rows().some((el) => /null/.test(el.textContent)), false, "no row reads null");
});
