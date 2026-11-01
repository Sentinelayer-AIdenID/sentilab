// node --test test/livelab-package.test.mjs (from web/)
// Carter (22:08Z): "package the good results and ship to engineers". Terms v1 (the terms review, 22:16Z): the door's
// terms grant evaluation, keeping the evidence and public display, not redistribution; so a package exists only for a
// run on the licence allowlist (web/public/sentilab/packages/licensed-runs.json, by full run id), shipped empty. Every
// other accepted run is view only. A package copies the public results feed's own row exactly and adds no claim.
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
async function open(t, tag, allow = null) {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"], now: NOW });
  const d = door();
  lastDom = installPage(t, (url) => (url.pathname === "/sentilab/packages/licensed-runs.json" ? allow : d.answer(url)));
  await import(`${LIVE}?proposals=${tag}`);
  await settleFor(t, 4000);
  return d;
}
const rows = () => walk(document.getElementById("proposalList")).filter((el) => el.tag === "button" && /^proposal\b/.test(el.className));
const text = (el) => el.textContent;


const P = await import(pathToFileURL(join(HERE, "..", "public", "sentilab", "live", "package-export.mjs")).href);
const W = await import(pathToFileURL(join(HERE, "..", "public", "sentilab", "live", "words.mjs")).href);
const RAW = () => doc("results.json");
const VENDORS = /\b(openai|chatgpt|gpt-?\d|claude|anthropic|gemini|copilot|mistral|llama)\b/i;
const entry = (id, extra = {}) => ({ run_id: id, visit: null, owner_role: "team", licence: "CC BY 4.0", confirmed_by: "the team", confirmed_at: "2026-11-01T22:30:00Z", ...extra });
const allowlist = (...ids) => ({ schema: "sentilab-licensed-runs/1", items: ids.map((id) => entry(id)) });

test("package: every field is copied from the feed's own row exactly, including not_claimed, and it carries its licence", () => {
  const raw = RAW().items[0];
  const pkg = P.engineerPackage(raw, { licence: entry(raw.id), submittedAt: "2026-11-01T10:18:42.328Z", pageUrl: "https://sentilab.aidenid.com/sentilab/live/", generatedAt: "2026-11-01T22:20:00.000Z" });
  assert.equal(pkg.schema, "sentilab-engineer-package/1");
  assert.equal(pkg.licence, "CC BY 4.0"); assert.equal(pkg.owner_role, "team");
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
  assert.equal(P.packageName(raw), "sentilab-79d3-e724279d.json", "the run id's own part, never the door part every run shares");
});

test("package: the README carries each required point and the licence line from the allowlist", () => {
  const raw = RAW().items[0];
  const readme = P.engineerPackage(raw, { licence: entry(raw.id) }).readme;
  for (const point of ["highest chiplet-centre average", "HotSpot 6.0", "grid 64", "simulated", "no warranty",
    "+1.39%", "HotSpot 7.0 reads very differently on the same inputs",
    "proxy computed from chip-to-chip distances, not routed wire",
    "not a manufacturing design", "not an optimum", "not checked on hardware",
    "route it", "run your own thermal model", "Licence: CC BY 4.0"]) assert.ok(readme.includes(point), `the README says: ${point}`);
  assert.equal(/\b(beat|beats|margin|better|best|validated)\b/i.test(readme), false, "the readme adds no claim");
});

test("package: ready only once the fresh replay matched; downloadable only for a run on the allowlist, by its full run id", () => {
  const ok = RAW().items[0];
  assert.equal(P.packageable(ok), true);
  assert.equal(P.packageable({ ...ok, status: "rejected", result: null }), false);
  assert.equal(P.packageable({ ...ok, status: "not_reproduced", result: { ...ok.result, verification: { ...ok.result.verification, replay: "not_reproduced" } } }), false);
  assert.equal(P.packageable({ ...ok, result: { ...ok.result, verification: { ...ok.result.verification, replay: "pending" } } }), false, "never at replay pending");
  assert.equal(P.packageable({ ...ok, result: { ...ok.result, replay: { ...ok.result.replay, match: false } } }), false);
  assert.equal(P.packageable({ ...ok, status: "evaluated" }), false);
  assert.equal(P.downloadable(ok, new Map()), false, "an empty allowlist: no download");
  assert.equal(P.downloadable(ok, P.readLicences(allowlist(ok.id))), true);
  assert.equal(P.downloadable(ok, P.readLicences({ schema: "sentilab-licensed-runs/1", items: [entry(ok.short_id), entry(`open-e4fde196-${"0".repeat(32)}`)] })), false, "never by short id or another run");
  assert.equal(P.readLicences({ schema: "sentilab-licensed-runs/1", items: [entry(ok.short_id)] }).size, 0);
  assert.equal(P.readLicences({ schema: "other", items: [entry(ok.id)] }).size, 0);
  assert.equal(P.readLicences(null).size, 0);
  const shipped = JSON.parse(readFileSync(join(HERE, "..", "public", "sentilab", "packages", "licensed-runs.json"), "utf8"));
  assert.deepEqual(shipped, { schema: "sentilab-licensed-runs/1", items: [] }, "the allowlist ships empty");
});

test("package: top layouts are the licensed, replay-matched ones, coolest first, with a CSV row each and the reference marked", () => {
  const items = RAW().items;
  const all = P.topLayouts(items, 10);
  const values = all.map((x) => x.result.max_chiplet_centre_cell_mean_C);
  assert.equal(all.length, 9); assert.deepEqual(values, [...values].sort((a, b) => a - b), "coolest first");
  const none = P.topBundle(items, {});
  assert.deepEqual(none.json.layouts, [], "an empty allowlist: nothing to download");
  assert.equal(none.csv.trim().split("\n").length, 1, "only the header");
  const licences = P.readLicences(allowlist(...items.map((x) => x.id)));
  const { json, csv } = P.topBundle(items, { licences, n: 5, pageUrl: "https://sentilab.aidenid.com/sentilab/live/", generatedAt: "2026-11-01T22:20:00.000Z" });
  assert.equal(json.layouts.length, 5, "top N");
  assert.deepEqual(json.reference, { layout: "raw", value_C: 115.935 });
  assert.deepEqual(json.layouts.map((x) => x.licence), Array(5).fill("CC BY 4.0"));
  const lines = csv.trim().split("\n");
  assert.equal(lines[0], "rank,visit,run_id,max_chiplet_centre_cell_mean_C,wire_proxy_mm,replay,licence,geometry_sha256,layout");
  assert.match(lines[1], /^reference \(for comparison only\),,raw,115\.935,/);
  assert.equal(lines.length, 2 + 5);
  assert.ok(lines[2].startsWith(`1,${all[0].short_id},${all[0].id},${all[0].result.max_chiplet_centre_cell_mean_C},${all[0].wire_proxy_mm},reproduced,CC BY 4.0,`));
  assert.ok(lines[2].endsWith(`"${P.compactLayout(all[0].dies)}"`), "the compact layout, quoted");
  const one = P.topBundle(items, { licences: P.readLicences(allowlist(items[3].id)) });
  assert.deepEqual(one.json.layouts.map((x) => x.run_id), [items[3].id], "only licensed runs");
});

function stubDownloads(t) {
  const blobs = [];
  const saved = { create: URL.createObjectURL, revoke: URL.revokeObjectURL };
  URL.createObjectURL = (blob) => { blobs.push(blob); return `blob:test/${blobs.length}`; };
  URL.revokeObjectURL = () => {};
  t.after(() => { URL.createObjectURL = saved.create; URL.revokeObjectURL = saved.revoke; });
  return blobs;
}
const pkgButtons = () => walk(document.getElementById("proposalList")).filter((el) => el.tag === "button" && /\bengineer-package\b/.test(el.className));
const viewOnly = () => walk(document.getElementById("proposalList")).filter((el) => el.className === "view-only").map((el) => el.textContent);

test("package page: with an empty allowlist there is no download anywhere; the selected accepted proposal is view only", async (t) => {
  await open(t, "empty");
  const blobs = stubDownloads(t);
  assert.equal(document.getElementById("packageButton").hidden, true, "no package on the model");
  assert.equal(pkgButtons().length, 0, "no package on the timeline");
  assert.equal(document.getElementById("topLayouts").hidden, true, "no top layouts download");
  assert.deepEqual(viewOnly(), ["View only: shown under the door’s terms, not licensed for redistribution"]);
  document.getElementById("packageButton").click(); document.getElementById("topLayouts").click();
  await settle();
  assert.equal(blobs.length, 0, "nothing downloads");
});

test("package page: an allowlisted run gets its package with its licence; an accepted run not on the list is view only", async (t) => {
  const followed = RAW().items.find((x) => x.short_id === "5cb8");
  await open(t, "licensed", allowlist(followed.id));
  const blobs = stubDownloads(t);
  assert.equal(document.getElementById("packageButton").hidden, false);
  assert.equal(pkgButtons().length, 1);
  pkgButtons()[0].click();
  await settle();
  const pkg = JSON.parse(await blobs[0].text());
  assert.equal(pkg.run_id, followed.id); assert.equal(pkg.licence, "CC BY 4.0"); assert.equal(pkg.owner_role, "team");
  assert.match(pkg.readme, /Licence: CC BY 4\.0/);
  assert.equal(walk(document.body).filter((el) => el.tag === "a" && el.getAttribute("download")).at(-1).getAttribute("download"), P.packageName(followed));
  document.getElementById("topLayouts").click();
  await settle();
  assert.deepEqual(JSON.parse(await blobs[1].text()).layouts.map((x) => x.run_id), [followed.id], "top layouts: licensed runs only");
  assert.equal((await blobs[2].text()).trim().split("\n").length, 3, "CSV: header, reference, the one licensed layout");
  // Another accepted run, not on the list: view only.
  rows().find((el) => el.textContent.includes("visit c991")).click();
  await settle();
  assert.equal(document.getElementById("packageButton").hidden, true);
  assert.equal(pkgButtons().length, 0);
  assert.deepEqual(viewOnly(), [W.PACKAGE.viewOnly]);
});

test("package: nothing on the page says unvalidated or names a vendor", async (t) => {
  await open(t, "words");
  const page = installedText();
  assert.equal(/unvalidated/i.test(page), false, "no visible unvalidated");
  assert.equal(VENDORS.test(page), false, "no vendor names");
});

// Review (22:45Z), P2 1: a feed still saying has_more at the page cap is an error, never a complete read.
test("pages: a feed still saying has_more at the cap rejects as incomplete; a finished feed resolves", async () => {
  const forever = async (after) => ({ schema: "sentilab-door-results/1", items: [], next_after: after + 1, has_more: true });
  const seen = [];
  await assert.rejects(P.readPages(forever, (doc) => seen.push(doc.next_after), 3), /pagination limit reached; results incomplete/);
  assert.deepEqual(seen, [1, 2, 3], "it read exactly the cap's pages first");
  const two = async (after) => ({ schema: "sentilab-door-results/1", items: [], next_after: after + 1, has_more: after < 1 });
  await P.readPages(two, () => {}, 3);
  assert.equal(P.RESULTS_MAX_PAGES, 200);
});

// Review (22:45Z), P2 2: a licence entry counts only with who confirmed it and when; otherwise it fails closed.
test("licences: an entry without confirmed_by or a well-formed confirmed_at is ignored", () => {
  const id = RAW().items[0].id;
  const list = (extra) => ({ schema: "sentilab-licensed-runs/1", items: [entry(id, extra)] });
  assert.equal(P.readLicences(list({})).size, 1, "a complete entry counts");
  assert.equal(P.readLicences(list({ confirmed_by: undefined })).size, 0, "no confirmed_by");
  assert.equal(P.readLicences(list({ confirmed_by: "" })).size, 0, "empty confirmed_by");
  assert.equal(P.readLicences(list({ confirmed_at: undefined })).size, 0, "no confirmed_at");
  assert.equal(P.readLicences(list({ confirmed_at: "yesterday" })).size, 0, "a confirmed_at that is not a UTC timestamp");
});
