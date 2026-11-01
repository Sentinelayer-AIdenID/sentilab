// node --test test/livelab-package.test.mjs (from web/)
// Carter (22:08Z): "package the good results and ship to engineers". A "Package for engineers" download on the
// selected accepted proposal, and "Download top layouts" for the coolest accepted ones, built in the page from the
// public results feed's own rows, copied exactly, with no claim the feed does not make.
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
let lastDom = null;
const installedText = () => lastDom.page().text.join(" ");
async function open(t, tag) {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"], now: NOW });
  const d = door();
  lastDom = installPage(t, d.answer);
  await import(`${LIVE}?proposals=${tag}`);
  await settleFor(t, 4000);
  return d;
}
const rows = () => walk(document.getElementById("proposalList")).filter((el) => el.tag === "button" && /^proposal\b/.test(el.className));
const text = (el) => el.textContent;


const P = await import(pathToFileURL(join(HERE, "..", "public", "sentilab", "live", "package-export.mjs")).href);
const RAW = () => doc("results.json");
const VENDORS = /\b(openai|chatgpt|gpt-?\d|claude|anthropic|gemini|copilot|mistral|llama)\b/i;

test("package: every field is copied from the feed's own row exactly, including not_claimed", () => {
  const raw = RAW().items[0];
  const pkg = P.engineerPackage(raw, { submittedAt: "2026-11-01T10:18:42.328Z", pageUrl: "https://sentilab.aidenid.com/sentilab/live/", generatedAt: "2026-11-01T22:20:00.000Z" });
  assert.equal(pkg.schema, "sentilab-engineer-package/1");
  assert.equal(pkg.run_id, raw.id); assert.equal(pkg.visit, raw.short_id); assert.equal(pkg.submitted_at, "2026-11-01T10:18:42.328Z");
  const compact = [...raw.dies].sort((a, b) => a.die - b.die).map((d) => `${d.x_um / 500}.${d.y_um / 500}.${d.rot_deg / 90}`).join(",");
  assert.equal(pkg.layout.compact, compact, "the door's compact l= string for the same dies");
  assert.deepEqual(pkg.layout.dies, raw.dies.map((d) => ({ die: d.die, x_um: d.x_um, y_um: d.y_um, rot_deg: d.rot_deg })), "the dies as the feed gives them");
  assert.equal(pkg.case.interposer_mm, 45); assert.equal(pkg.case.dies.length, 8);
  assert.deepEqual(pkg.case.dies[0], { id: "C0", kind: "CPU", w_mm: 8.25, h_mm: 9, power_w: 150, halo_mm: 0.18 });
  assert.equal(pkg.geometry_sha256, raw.geometry_sha256); assert.equal(pkg.wire_proxy_mm, raw.wire_proxy_mm);
  for (const k of ["metric", "max_chiplet_centre_cell_mean_C", "per_die_C", "active_layer_peak_C", "active_guard", "replay"]) assert.deepEqual(pkg.result[k], raw.result[k], k);
  assert.deepEqual(pkg.verification, raw.result.verification);
  assert.deepEqual(pkg.verification.not_claimed, ["beat", "margin", "routed wire", "source acceptance"]);
  assert.deepEqual(pkg.evaluator, raw.result.evaluator);
  assert.deepEqual(pkg.labels, { label: raw.result.label, temperature_label: raw.result.temperature_label }, "the feed's own labels, as given");
  assert.deepEqual(pkg.source, { page: "https://sentilab.aidenid.com/sentilab/live/", feed: "/api/open/v1/door/results", generated_at: "2026-11-01T22:20:00.000Z" });
  assert.match(pkg.readme, /simulated, not measured on silicon/);
  assert.equal(/\b(beat|beats|margin|better|best|validated)\b/i.test(pkg.readme), false, "the readme adds no claim");
  assert.equal(P.packageName(raw), "sentilab-79d3-e724279d.json", "the run id's own part, never the door part every run shares");
});

test("package: refused, unreproduced or unscored runs get no package", () => {
  const ok = RAW().items[0];
  assert.equal(P.packageable(ok), true);
  assert.equal(P.packageable({ ...ok, status: "rejected", result: null }), false);
  assert.equal(P.packageable({ ...ok, status: "not_reproduced", result: { ...ok.result, verification: { ...ok.result.verification, replay: "not_reproduced" } } }), false);
  assert.equal(P.packageable({ ...ok, result: { ...ok.result, verification: { ...ok.result.verification, replay: "pending" } } }), false);
  assert.equal(P.packageable({ ...ok, status: "evaluated" }), false);
  assert.equal(P.packageable(null), false);
});

test("package: top layouts are the accepted, replay-matched ones, coolest first, at most N, with a CSV row each and the reference marked", () => {
  const items = RAW().items;
  const extra = { ...items[0], id: "open-0000dead-0000000000000000000000000000dead", short_id: "dead", seq: 999, status: "not_reproduced",
    result: { ...items[0].result, max_chiplet_centre_cell_mean_C: 50, verification: { ...items[0].result.verification, replay: "not_reproduced" } } };
  const all = P.topLayouts([...items, extra], 10);
  assert.equal(all.length, 9, "every accepted one (fewer than 10), never the unreproduced one");
  const values = all.map((x) => x.result.max_chiplet_centre_cell_mean_C);
  assert.deepEqual(values, [...values].sort((a, b) => a - b), "coolest first");
  assert.equal(P.topLayouts(items, 3).length, 3);
  const { json, csv } = P.topBundle([...items, extra], { pageUrl: "https://sentilab.aidenid.com/sentilab/live/", generatedAt: "2026-11-01T22:20:00.000Z" });
  assert.equal(json.schema, "sentilab-top-layouts/1");
  assert.deepEqual(json.reference, { layout: "raw", value_C: 115.935 });
  assert.deepEqual(json.layouts.map((x) => x.rank), [1, 2, 3, 4, 5, 6, 7, 8, 9]);
  assert.deepEqual(json.layouts.map((x) => x.wire_proxy_mm), all.map((x) => x.wire_proxy_mm), "wire proxy alongside");
  const lines = csv.trim().split("\n");
  assert.equal(lines[0], "rank,visit,run_id,max_chiplet_centre_cell_mean_C,wire_proxy_mm,replay,geometry_sha256,layout");
  assert.match(lines[1], /^reference \(for comparison only\),,raw,115\.935,/);
  assert.equal(lines.length, 2 + 9);
  assert.ok(lines[2].startsWith(`1,${all[0].short_id},${all[0].id},${all[0].result.max_chiplet_centre_cell_mean_C},${all[0].wire_proxy_mm},reproduced,`));
  assert.ok(lines[2].endsWith(`"${P.compactLayout(all[0].dies)}"`), "the compact layout, quoted");
  assert.equal(/\b(beat|beats|margin|better)\b/i.test(json.readme), false);
});

test("package: the selected accepted proposal downloads its exact package; refused and unreproduced ones get no button", async (t) => {
  const d = await open(t, "page");
  const blobs = [];
  const saved = { create: URL.createObjectURL, revoke: URL.revokeObjectURL };
  URL.createObjectURL = (blob) => { blobs.push(blob); return `blob:test/${blobs.length}`; };
  URL.revokeObjectURL = () => {};
  t.after(() => { URL.createObjectURL = saved.create; URL.revokeObjectURL = saved.revoke; });
  const pkgButtons = () => walk(document.getElementById("proposalList")).filter((el) => el.tag === "button" && /\bengineer-package\b/.test(el.className));
  assert.equal(document.getElementById("packageButton").hidden, false, "the followed run is accepted and replay-matched");
  assert.equal(pkgButtons().length, 1, "one button, on the selected row");
  pkgButtons()[0].click();
  await settle();
  assert.equal(blobs.length, 1);
  const pkg = JSON.parse(await blobs[0].text());
  const raw = RAW().items.find((x) => x.id === pkg.run_id);
  assert.ok(raw, "a run from the feed");
  assert.deepEqual(pkg.verification, raw.result.verification);
  const anchors = walk(document.body).filter((el) => el.tag === "a" && el.getAttribute("download"));
  assert.equal(anchors.at(-1).getAttribute("download"), P.packageName(raw));
  document.getElementById("topLayouts").click();
  await settle();
  assert.equal(blobs.length, 3, "top layouts: a JSON and a CSV");
  assert.equal(JSON.parse(await blobs[1].text()).schema, "sentilab-top-layouts/1");
  assert.match(await blobs[2].text(), /^rank,visit,run_id/);
  assert.deepEqual(walk(document.body).filter((el) => el.tag === "a").slice(-2).map((a) => a.getAttribute("download")), ["sentilab-top-layouts.json", "sentilab-top-layouts.csv"]);
  // A refused proposal and one whose replay did not match: no package.
  d.add("e005", ["rejected"], { at: Date.now() });
  d.add("e006", ["queued", "evaluating", "evaluated", "replaying", "not_reproduced"], { at: Date.now() });
  await settleFor(t, 4000);
  for (const hex of ["e005", "e006"]) {
    rows().find((el) => el.textContent.includes(`visit ${hex}`)).click();
    await settle();
    assert.equal(document.getElementById("packageButton").hidden, true, `${hex}: no package button on the model`);
    assert.equal(pkgButtons().length, 0, `${hex}: no package button on the row`);
  }
});

test("package: nothing on the page says unvalidated or names a vendor", async (t) => {
  const d = await open(t, "words");
  void d;
  const page = installedText();
  assert.equal(/unvalidated/i.test(page), false, "no visible unvalidated");
  assert.equal(VENDORS.test(page), false, "no vendor names");
});
