// node --test test/livelab-door.test.mjs (from web/)
// Carter (20:05Z): "When you guys arrive at the door and declaring I see the entity presented ... I need to see it [on the] door
// atlas ... that agent is at the door then once it chooses ... the animation of it moving to ... simulating ... And
// when it submits as well." Root (20:08Z): visitors show at Door and move only through their observed actions: a
// declared intent alone is not a simulation; entering the Simulator needs the run's own evaluating record; full ids
// and the exact same-pass link (visit_arrival) only; any slowed playback is called a playback.
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


// Each figure belongs to the station nearest to where it is drawn (STATION_XY in live.mjs; a row sits 19 below).
const XY = [[56, 34], [150, 22], [244, 34], [258, 108], [150, 128], [42, 108]], NAMES = ["door", "submit", "queue", "simulate", "replay", "board"];
const near = (x, y) => NAMES[XY.map(([sx, sy]) => (sx - x) ** 2 + (sy - y) ** 2).reduce((best, dd, i, all) => (dd < all[best] ? i : best), 0)];
const atlasEls = () => walk(document.getElementById("atlasSvg"));
const figures = () => atlasEls().filter((el) => el.tag === "svg" && /\batlas-av\b/.test(el.getAttribute("class") ?? ""))
  .map((el) => ({ at: near(Number(el.getAttribute("x")) + Number(el.getAttribute("width")) / 2, Number(el.getAttribute("y")) + Number(el.getAttribute("height")) / 2 - 19),
    guest: /\bguest\b/.test(el.getAttribute("class")) }));
const captions = () => atlasEls().filter((el) => el.tag === "text" && el.getAttribute("class") === "atlas-step")
  .map((el) => [el.getAttribute("data-step"), el.getAttribute("data-station"), el.textContent]);
const guestLabel = () => atlasEls().filter((el) => el.tag === "text" && el.getAttribute("class") === "atlas-guest").map((el) => el.textContent).join(" | ");
const more = (name) => { const el = atlasEls().find((x) => x.tag === "text" && x.getAttribute("class") === "atlas-more" && near(Number(x.getAttribute("x")) - 38, Number(x.getAttribute("y")) - 22) === name); return el ? el.textContent : null; };
const FIVE = ["queued", "evaluating", "evaluated", "replaying", "reproduced"];
async function watch(t, ms) {
  const seen = [];
  for (let k = 0; k < ms / 100; k += 1) {
    t.mock.timers.tick(100); await settle();
    for (const c of captions()) if (!seen.some((s) => s[0] === c[0])) seen.push(c);
  }
  return seen;
}

test("door: a live arrival appears at Door, with its visit id", async (t) => {
  const d = await open(t, "arrive");
  assert.equal(figures().filter((f) => f.guest).length, 0, "the recorded arrivals are hours old: nobody at the door");
  d.arrive("9f8c", Date.now());
  await settleFor(t, 4000);
  const guests = figures().filter((f) => f.guest);
  assert.equal(guests.length, 1); assert.equal(guests[0].at, "door");
  assert.match(guestLabel(), /visit 9f8c/);
});

test("door: with visit_arrival the visitor's figure walks from Door to Submit, then only the run's recorded steps", async (t) => {
  const d = await open(t, "linked");
  const arrival = d.arrive("9f8c", Date.now());
  d.declare(arrival, "Visitor Gamma", "9f8c");
  await settleFor(t, 4000);
  assert.match(guestLabel(), /Visitor Gamma · self-declared, not verified/, "its declared name, through declaration.arrival");
  d.add("9f8c", FIVE, { at: Date.now(), visitArrival: arrival });
  const seen = await watch(t, 9000);
  assert.deepEqual(seen.map((s) => s.slice(1)), [["door", "Playback · At the door"], ["submit", "Playback · Submission accepted"], ["queue", "Playback · Waiting in line"],
    ["simulate", "Playback · Simulating"], ["replay", "Playback · Re-checking (replay)"], ["replay", "Playback · Re-checking (replay)"], ["board", "Playback · Accepted · replay matched"]]);
  assert.equal(figures().filter((f) => f.guest).length, 0, "the visitor's figure is the run's now: it is not also left at the door");
});

test("door: without visit_arrival the visitor stays at Door and the run walks from its own first step", async (t) => {
  const d = await open(t, "unlinked");
  d.arrive("9f8c", Date.now());
  await settleFor(t, 4000);
  d.add("9f8c", FIVE, { at: Date.now() });
  const views = [];
  const seen = [];
  for (let k = 0; k < 90; k += 1) {
    t.mock.timers.tick(100); await settle();
    views.push(figures().filter((f) => f.guest).map((f) => f.at).join(","));
    for (const c of captions()) if (!seen.some((s) => s[0] === c[0])) seen.push(c);
  }
  assert.equal(seen[0]?.[1], "queue", "the run starts at its own first step");
  assert.equal(seen.some((s) => s[1] === "door" || s[1] === "submit"), false);
  assert.ok(views.every((v) => v === "door"), "the visitor stays at Door the whole time");
});

test("door: a visitor that only declared stays at Door: no mark, no solver station", async (t) => {
  const d = await open(t, "declared");
  const arrival = d.arrive("9f8c", Date.now());
  d.declare(arrival, "Visitor Gamma", "9f8c");
  const seen = await watch(t, 20000);
  assert.deepEqual(seen, [], "nothing walks");
  const guests = figures().filter((f) => f.guest);
  assert.equal(guests.length, 1); assert.equal(guests[0].at, "door");
  assert.match(guestLabel(), /Visitor Gamma · self-declared, not verified/);
  assert.equal(rows().some((el) => el.textContent.includes("9f8c")), false, "no proposal, so no accepted mark");
});

test("door: the cap holds at Door (six figures, +N for the rest) and the Door count stays the live count", async (t) => {
  const base = doc("events.json");
  const d = await open(t, "cap");
  for (let k = 0; k < 9; k += 1) d.arrive(`ab${String(k).padStart(2, "0")}`, Date.now());
  await settleFor(t, 4000);
  const atDoor = figures().filter((f) => f.at === "door");
  assert.equal(atDoor.length, 6); assert.equal(more("door"), "+3");
  const window = [...base.events.map((e) => e.kind), ...Array(9).fill("arrival")].slice(-40);
  const doorCount = atlasEls().filter((el) => el.tag === "text" && el.getAttribute("class") === "st-count")[0].textContent;
  assert.equal(doorCount, String(window.filter((k) => k === "arrival").length), "the Door count is the arrivals in the newest records, as before");
});

// Root (26000ae P2): a Door figure must age out on the page's clock even when reads hang. Before, clock ticks redrew the
// maps only when names changed, so with every read hanging a visitor stayed at the Door past its 15 minutes (root's
// witness: age 924,000 ms, guest count still 1). Now the 1 s clock recomputes the Door's visitors and redraws both maps
// (and the expanded table) when that set changes, with no network answer at all.
test("door: with every read hanging, a visitor ages out of the Door on the clock, on the small and the expanded map", async (t) => {
  const d = await open(t, "expiry");
  d.arrive("9f8c", Date.now());
  await settleFor(t, 4000);
  const bigEls = () => walk(document.getElementById("modalBody"));
  const bigGuests = () => bigEls().filter((el) => el.tag === "svg" && /\bguest\b/.test(el.getAttribute("class") ?? "")).length;
  const doorCount = (els) => els.filter((el) => el.tag === "text" && el.getAttribute("class") === "st-count")[0]?.textContent;
  const tableDoor = () => bigEls().filter((el) => el.tag === "td").map((el) => el.textContent)[1];
  assert.equal(figures().filter((f) => f.guest).length, 1, "the visitor is at the Door");
  lastPage.atlasButton.click();
  assert.equal(bigGuests(), 1, "and on the expanded map");
  d.state.hang = true;
  const answered = d.state.answered;
  await settleFor(t, 14 * 60000, 1000);
  assert.equal(figures().filter((f) => f.guest).length, 1, "still inside its 15 minutes");
  await settleFor(t, 70000, 1000);
  assert.equal(d.state.answered, answered, "no read answered while it aged out");
  assert.equal(figures().filter((f) => f.guest).length, 0, "gone from the small map");
  assert.equal(bigGuests(), 0, "gone from the expanded map");
  assert.equal(guestLabel(), "", "no visit label left at the Door");
  assert.equal(tableDoor(), `${doorCount(atlasEls())} · arrival records`, "the expanded table was redrawn with the maps (the Door's live count)");
  assert.equal(doorCount(bigEls()), doorCount(atlasEls()));
});

// Root (d9f3846, 23:26Z): every drawAtlas wrote one shared Door key. Opening the expanded atlas just after a visitor's
// 15 minutes (age 900,500 ms) and before the next clock tick, with every read hung, drew zero there and wrote the empty
// key, so the clock then saw "nothing changed" and the small map kept the visitor. Each map now keeps its own key.
test("door: an expanded-only draw just past the cutoff never leaves the small map stale", async (t) => {
  const d = await open(t, "interleave");
  const at = Date.now();
  d.arrive("9f8c", at);
  await settleFor(t, 4000);
  assert.equal(figures().filter((f) => f.guest).length, 1, "the visitor is at the Door");
  d.state.hang = true;
  // To 500 ms before age 900,500 in whole seconds, then the last half second: between two clock ticks.
  await settleFor(t, at + 900000 - Date.now(), 1000);
  await settleFor(t, 500, 500);
  assert.equal(Date.now() - at, 900500, "age 900,500 ms, just past the inclusive 15-minute cutoff");
  assert.equal(figures().filter((f) => f.guest).length, 1, "the last tick (age 900,000) still held it");
  lastPage.atlasButton.click();
  const bigGuests = () => walk(document.getElementById("modalBody")).filter((el) => el.tag === "svg" && /\bguest\b/.test(el.getAttribute("class") ?? "")).length;
  assert.equal(bigGuests(), 0, "the expanded map, drawn now, has none");
  await settleFor(t, 3000, 1000);
  assert.equal(figures().filter((f) => f.guest).length, 0, "the small map catches up on the next tick");
  assert.equal(bigGuests(), 0);
});
