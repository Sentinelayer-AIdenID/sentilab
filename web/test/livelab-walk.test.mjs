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
  assert.deepEqual(seen.map((s) => s.slice(1)), [["queue", "Playback · Waiting in line"], ["simulate", "Playback · Simulating"], ["replay", "Playback · Re-checking (replay)"],
    ["replay", "Playback · Re-checking (replay)"], ["board", "Playback · Accepted · replay matched"]]);
  assert.deepEqual(seen.map((s) => s[0]), ["0", "1", "2", "3", "4"], "five positions, in the records' order");
  assert.deepEqual(captions(), [], "then it rests at its real latest step");
});

test("walk: with reduced motion the run jumps straight to its latest step", async (t) => {
  const seen = await live(t, "reduced", ["queued", "evaluating", "evaluated", "replaying", "reproduced"], { reduced: true });
  assert.deepEqual(seen, [], "no walk");
});

test("walk: no step is shown that is not in the run's records", async (t) => {
  const seen = await live(t, "skip", ["queued", "evaluating", "reproduced"]);
  assert.deepEqual(seen.map((s) => s.slice(1)), [["queue", "Playback · Waiting in line"], ["simulate", "Playback · Simulating"], ["board", "Playback · Accepted · replay matched"]]);
  assert.equal(seen.some((s) => s[1] === "replay"), false, "the run recorded no replay step, so none is shown");
});

test("walk: a run whose records arrive a poll before its result still walks every recorded step once it can be drawn", async (t) => {
  const seen = await live(t, "lag", ["queued", "evaluating", "evaluated", "replaying", "reproduced"], { resultsLag: true });
  assert.deepEqual(seen.map((s) => s[0]), ["0", "1", "2", "3", "4"], "from its first recorded step, in order");
  assert.deepEqual(captions(), []);
});

// Carter (19:33Z): "When ChatGPT finishes and proposes I need to see it at the top in the 3d space. It should say new
// proposal". A run that arrives live and becomes the followed run shows "New proposal" over the model for 15 s; the run
// followed at load never does.
test("new proposal: a run that arrives live puts 'New proposal' over the model, then it clears", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"], now: NOW });
  const d = door(["queued", "evaluating", "evaluated", "replaying", "reproduced"]);
  installPage(t, d.answer);
  await import(`${LIVE}?walk=newproposal`);
  const badge = () => document.getElementById("newProposal");
  for (let k = 0; k < 8; k += 1) { t.mock.timers.tick(500); await settle(); }
  assert.equal(badge().hidden, true, "the run followed at load is not new");
  d.phase.live = true;
  let shown = false;
  for (let k = 0; k < 40; k += 1) { t.mock.timers.tick(100); await settle(); if (badge().hidden === false) shown = true; }
  assert.equal(shown, true, "a run that arrives live shows the badge");
  for (let k = 0; k < 40; k += 1) { t.mock.timers.tick(500); await settle(); }
  assert.equal(badge().hidden, true, "and it clears after about 15 s");
});

// Root's +1 review of 0ba078e (three P2s). A walk is a playback of records already received: anything that stops
// motion stops it at once and shows the latest state, a late timer does nothing, an open expanded atlas follows it,
// and the station counts always show the live state, never the replayed stage.
async function walking(t, tag, opts = {}) {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"], now: NOW });
  const d = door(["queued", "evaluating", "evaluated", "replaying", "reproduced"]);
  const dom = installPage(t, d.answer, opts);
  await import(`${LIVE}?walk=${tag}`);
  for (let k = 0; k < 8; k += 1) { t.mock.timers.tick(500); await settle(); }
  d.phase.live = true;
  for (let k = 0; k < 40 && !captions().length; k += 1) { t.mock.timers.tick(100); await settle(); }
  assert.equal(captions().length, 1, "a walk is playing");
  return dom;
}
const counts = (svg) => walk(svg).filter((el) => el.tag === "text" && el.getAttribute("class") === "st-count").map((el) => el.textContent);
const settleFor = async (t, ms) => { for (let k = 0; k < ms / 100; k += 1) { t.mock.timers.tick(100); await settle(); } };

for (const [control, act] of [
  ["Pause all motion", () => document.getElementById("motionToggle").click()],
  ["a hidden tab", (dom) => { document.hidden = true; document.visibilityState = "hidden"; dom.fire("document", "visibilitychange"); }],
  ["pagehide", (dom) => dom.fire("window", "pagehide", { persisted: false })],
]) {
  test(`walk: ${control} stops an active walk at once and shows the latest state; a late timer does nothing`, async (t) => {
    const dom = await walking(t, `stop-${control.split(" ")[1] ?? control}`);
    const live = counts(document.getElementById("atlasSvg"));
    act(dom);
    await settle();
    assert.deepEqual(captions(), [], "no playback once stopped");
    assert.deepEqual(counts(document.getElementById("atlasSvg")), live, "the latest state");
    const drawn = dump(document.getElementById("atlasSvg")).attrs.join(" ");
    await settleFor(t, 4000);
    assert.deepEqual(captions(), [], "a late timer callback does nothing");
    assert.equal(dump(document.getElementById("atlasSvg")).attrs.join(" "), drawn, "nothing redrawn by a stale walk");
  });
}

test("walk: an open expanded atlas plays back with the small one, step for step", async (t) => {
  const dom = await walking(t, "expanded");
  dom.atlasButton.click();
  const modalSteps = () => walk(document.getElementById("modalBody")).filter((el) => el.tag === "text" && el.getAttribute("class") === "atlas-step")
    .map((el) => el.getAttribute("data-step"));
  for (let k = 0; k < 3; k += 1) {
    await settleFor(t, 700);
    assert.deepEqual(modalSteps(), captions().map((c) => c[0]), `the expanded map shows the same step as the small one (${k})`);
  }
  assert.ok(captions().length === 1, "still mid-walk");
});

test("walk: station counts during a walk equal the live state, and the playback is labelled as one", async (t) => {
  await walking(t, "counts");
  const during = counts(document.getElementById("atlasSvg"));
  const caption = captions()[0][2];
  await settleFor(t, 5000);
  assert.deepEqual(captions(), [], "the walk has ended");
  assert.deepEqual(during, counts(document.getElementById("atlasSvg")), "the counts never showed the replayed stage");
  assert.match(caption, /^Playback · /, "the walking caption says it is a playback");
  assert.match(document.getElementById("mapLegend").textContent, /plays them back/, "the legend describes the playback");
});

// A newer poll during a walk ends it at once; the ended walk's timer must never advance the next walk (root's "guard
// late callbacks"). Run A walks; while it is still on its steps, the next poll brings run B's whole life. Every step of
// B stays up for its full time: a stale timer from A would advance B early and run two timer chains at once.
test("walk: a newer poll ends a walk at once, and the ended walk's timer never advances the next one", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"], now: NOW });
  const base = doc("events.json"), results = doc("results.json"), board = doc("board.json");
  const run = (hex, n) => ({ id: `open-0000${hex}-${"0".repeat(28)}${hex}`, item: { ...results.items[0], id: `open-0000${hex}-${"0".repeat(28)}${hex}`, short_id: hex,
    label: `unknown · ${hex}`, class: "unknown", arrival: 0, seq: results.next_after + n } });
  const A = run("beef", 1), B = run("cafe", 2);
  const recs = (r, from) => ["queued", "evaluating", "evaluated", "replaying", "reproduced"].map((state, i) => ({ seq: from + i, at: new Date(NOW + i * 100).toISOString(),
    kind: "run", class: "unknown", label: r.item.label, run_id: r.id, short_id: r.item.short_id, state }));
  const phase = { a: false, b: false };
  installPage(t, (url) => {
    const after = Number(url.searchParams.get("after") ?? 0);
    if (url.pathname === "/api/open/v1/door/results") {
      const items = [...(phase.a ? [A.item] : []), ...(phase.b ? [B.item] : [])].filter((i) => i.seq > Math.max(after, results.next_after - 1) && after >= results.next_after);
      if (after < results.next_after) return results;
      return { ...results, items, next_after: items.length ? items.at(-1).seq : after, has_more: false };
    }
    if (url.pathname === "/api/open/v1/door/events") {
      if (after < base.next_after) return base;
      const events = [...(phase.a ? recs(A, 100) : []), ...(phase.b ? recs(B, 110) : [])].filter((e) => e.seq > after);
      return { ...base, events, next_after: events.length ? events.at(-1).seq : after, has_more: false };
    }
    if (url.pathname === "/api/open/v1/door/board") return board;
    return null;
  });
  await import(`${LIVE}?walk=late`);
  for (let k = 0; k < 8; k += 1) { t.mock.timers.tick(500); await settle(); }
  phase.a = true;
  for (let k = 0; k < 40 && !captions().length; k += 1) { t.mock.timers.tick(100); await settle(); }
  assert.equal(captions().length, 1, "run A is playing back");
  phase.b = true;
  const timeline = [];
  for (let k = 0; k < 90; k += 1) {
    t.mock.timers.tick(100); await settle();
    const c = captions();
    timeline.push(c.length === 1 ? c[0][0] : c.length ? "many" : "-");
  }
  assert.equal(timeline.includes("many"), false, "never two playbacks at once: the newer poll ended A");
  // B's steps: the indices after the first time the timeline restarts at 0.
  const restart = timeline.findIndex((x, i) => i > 0 && x === "0" && timeline[i - 1] !== "0");
  assert.ok(restart > 0, `B's playback started: ${timeline.join(" ")}`);
  const runs = [];
  for (const x of timeline.slice(restart)) { if (runs.length && runs.at(-1)[0] === x) runs.at(-1)[1] += 1; else runs.push([x, 1]); }
  const steps = runs.filter(([x]) => x !== "-");
  assert.deepEqual(steps.map(([x]) => x), ["0", "1", "2", "3", "4"], `B shows each of its steps once, in order: ${timeline.slice(restart).join(" ")}`);
  for (const [x, n] of steps.slice(0, 4)) assert.ok(n >= 6, `step ${x} stays up its full time (${n * 100} ms): ${timeline.slice(restart).join(" ")}`);
});

// Root's review of 2aab3e2 (two ordinary P2s): the first proposal after an empty start shows the badge, and a shown badge
// ends at its own deadline even when later reads never answer.
function emptyStart(states) {
  const d = door(states), res0 = doc("results.json");
  const item = { ...res0.items[0], id: ID, short_id: "beef", label: "unknown · beef", class: "unknown", arrival: 99, seq: res0.next_after + 1 };
  const state = { hang: false };
  const answer = (url) => {
    if (state.hang) return "hang";
    if (url.pathname === "/api/open/v1/door/results") {
      const after = Number(url.searchParams.get("after") ?? 0);
      if (!d.phase.live) return { ...res0, items: [], next_after: 0, has_more: false };
      return after < item.seq ? { ...res0, items: [item], next_after: item.seq, has_more: false } : { ...res0, items: [], next_after: after, has_more: false };
    }
    return d.answer(url);
  };
  return { d, answer, state };
}

test("new proposal: the first proposal after an empty start shows the badge", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"], now: NOW });
  const { d, answer } = emptyStart(["queued", "evaluating", "evaluated", "replaying", "reproduced"]);
  installPage(t, answer);
  await import(`${LIVE}?walk=np-empty`);
  const badge = () => document.getElementById("newProposal");
  for (let k = 0; k < 8; k += 1) { t.mock.timers.tick(500); await settle(); }
  assert.equal(badge().hidden, true, "nothing new at an empty start");
  d.phase.live = true;
  let shown = false;
  for (let k = 0; k < 40; k += 1) { t.mock.timers.tick(100); await settle(); if (badge().hidden === false) shown = true; }
  assert.equal(shown, true, "the first proposal after an empty start is new");
});

test("new proposal: a shown badge ends at its deadline even when later reads never answer", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"], now: NOW });
  const { d, answer, state } = emptyStart(["queued", "evaluating", "evaluated", "replaying", "reproduced"]);
  installPage(t, answer);
  await import(`${LIVE}?walk=np-hang`);
  const badge = () => document.getElementById("newProposal");
  for (let k = 0; k < 8; k += 1) { t.mock.timers.tick(500); await settle(); }
  d.phase.live = true;
  for (let k = 0; k < 40 && badge().hidden; k += 1) { t.mock.timers.tick(100); await settle(); }
  assert.equal(badge().hidden, false, "the badge is up");
  state.hang = true;
  for (let k = 0; k < 40; k += 1) { t.mock.timers.tick(500); await settle(); }
  assert.equal(badge().hidden, true, "it ends at its deadline, with every read hanging");
});

// Root (0c97bbd P2): a row of figures is capped at six, playbacks included. With six runs playing back at once, a
// station had no slot left for its live figures, but slice(-0) kept every one of them: nine existing runs and six new
// ones drew fifteen figures at Board. Now no row ever draws more than six; "+N" accounts for every live run not drawn
// at its station (a run playing back elsewhere is one of them); the counts stay the live state.
test("walk: six runs playing back at once never draw more than six figures a row; +N and the counts stay the live state", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"], now: NOW });
  const base = doc("events.json"), results = doc("results.json"), board = doc("board.json");
  assert.equal(results.items.length, 9, "nine existing runs");
  const fresh = Array.from({ length: 6 }, (_, k) => {
    const hex = `aa0${k}`, id = `open-0000${hex}-${"0".repeat(28)}${hex}`;
    return { id, item: { ...results.items[0], id, short_id: hex, label: `unknown · ${hex}`, class: "unknown", arrival: 0, seq: results.next_after + 1 + k } };
  });
  const recs = fresh.flatMap((r, k) => ["queued", "evaluating", "evaluated", "replaying", "reproduced"].map((state, i) => ({ seq: 100 + k * 5 + i,
    at: new Date(NOW + k * 500 + i * 100).toISOString(), kind: "run", class: "unknown", label: r.item.label, run_id: r.id, short_id: r.item.short_id, state })));
  const later = { ...base, events: recs, next_after: recs.at(-1).seq, has_more: false };
  const items = fresh.map((r) => r.item);
  const phase = { live: false };
  installPage(t, (url) => {
    const after = Number(url.searchParams.get("after") ?? 0);
    if (url.pathname === "/api/open/v1/door/results") {
      if (after < results.next_after) return results;
      return phase.live && after < items.at(-1).seq ? { ...results, items, next_after: items.at(-1).seq, has_more: false } : { ...results, items: [], next_after: after, has_more: false };
    }
    if (url.pathname === "/api/open/v1/door/events") {
      if (after < base.next_after) return base;
      return phase.live && after < later.next_after ? later : { ...base, events: [], next_after: after, has_more: false };
    }
    if (url.pathname === "/api/open/v1/door/board") return board;
    return null;
  });
  await import(`${LIVE}?walk=six`);
  for (let k = 0; k < 8; k += 1) { t.mock.timers.tick(500); await settle(); }
  phase.live = true;
  for (let k = 0; k < 40 && captions().length < 6; k += 1) { t.mock.timers.tick(100); await settle(); }
  assert.equal(captions().length, 6, "six playbacks at once");
  // Each figure and each "+N" belongs to the station nearest to where it is drawn (STATION_XY in live.mjs).
  const XY = [[56, 34], [150, 22], [244, 34], [258, 108], [150, 128], [42, 108]], NAMES = ["door", "submit", "queue", "simulate", "replay", "board"];
  const near = (x, y) => NAMES[XY.map(([sx, sy]) => (sx - x) ** 2 + (sy - y) ** 2).reduce((best, d, i, all) => (d < all[best] ? i : best), 0)];
  const look = () => {
    const els = walk(document.getElementById("atlasSvg"));
    const figures = els.filter((el) => el.tag === "svg" && /\batlas-av\b/.test(el.getAttribute("class") ?? ""))
      .map((el) => ({ at: near(Number(el.getAttribute("x")) + Number(el.getAttribute("width")) / 2, Number(el.getAttribute("y")) + Number(el.getAttribute("height")) / 2 - 19),
        playback: /\bplayback\b/.test(el.getAttribute("class")) }));
    const more = Object.fromEntries(els.filter((el) => el.tag === "text" && el.getAttribute("class") === "atlas-more")
      .map((el) => [near(Number(el.getAttribute("x")) - 38, Number(el.getAttribute("y")) - 22), Number(el.textContent.replace("+", ""))]));
    return { figures, more, counts: counts(document.getElementById("atlasSvg")) };
  };
  const views = [];
  for (let k = 0; k < 45; k += 1) { views.push(look()); t.mock.timers.tick(100); await settle(); }
  assert.deepEqual(captions(), [], "the playbacks have ended");
  const rest = look();
  assert.equal(rest.counts[5], "15", "Board holds all fifteen runs live");
  views.push(rest);
  for (const [i, v] of views.entries()) {
    for (const name of NAMES) {
      const row = v.figures.filter((f) => f.at === name);
      assert.ok(row.length <= 6, `view ${i}: ${name} draws ${row.length} figures`);
    }
    assert.deepEqual(v.counts, rest.counts, `view ${i}: the counts are the live state`);
    // Every run is live at Board: the figures drawn there plus its +N are all fifteen (a run playing back elsewhere is
    // one of Board's +N); every other station counts 0 live runs and shows no +N.
    const atBoard = v.figures.filter((f) => f.at === "board").length;
    assert.equal(atBoard + (v.more.board ?? 0), 15, `view ${i}: Board's figures and +N account for every live run (${atBoard} + ${v.more.board ?? 0})`);
    for (const name of ["queue", "simulate", "replay"]) assert.equal(v.more[name] ?? 0, 0, `view ${i}: no +N at ${name}`);
  }
  assert.ok(views.some((v) => v.figures.filter((f) => f.at === "board" && f.playback).length === 6), "all six played back to Board together");
});
