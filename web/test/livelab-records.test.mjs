// node --test test/livelab-records.test.mjs (from web/)
// Carter (18:26Z): every door record stays on the page, newest first, and older ones load as you ask (the events
// feed's own paging, one spaced page at a time), several records of one visit each on their own row; the aquarium's
// populations as tabs; its own labels ("Likely human", "Unresolved"); and every run's real outcome from the results
// feed (a refused run says why, in plain words, the raw code only in a tooltip).
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
  addEventListener(type, fn) { (this.listeners ??= {})[type] = [...(this.listeners?.[type] ?? []), fn]; }
  click() { for (const fn of this.listeners?.click ?? []) fn({ type: "click", target: this }); }
  removeEventListener() {} focus() {} showModal() {} close() {} remove() {}
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
const CLASSES = ["likely_human", "unknown", "declared_agent", "automation", "crawler_claimed", "verified_agent"];
// 450 door records: arrivals of every class, several per visit (the same short id), ascending seq 1..450.
function history() {
  const out = [];
  for (let seq = 1; seq <= 450; seq += 1) {
    const cls = CLASSES[seq % CLASSES.length], short = (Math.floor(seq / 3) % 4096).toString(16).padStart(4, "0");
    out.push({ seq, at: new Date(Date.parse("2026-11-01T10:00:00Z") + seq * 60000).toISOString(), kind: "arrival", class: cls, label: `${cls} \u00b7 ${short}`,
      purpose: "place-chiplets", short_id: short });
  }
  return out;
}
function world(t, { results = doc("results.json") } = {}) {
  const events = history();
  const asked = [];
  const dom = installPage(t, (url) => {
    if (url.pathname === "/api/open/v1/door/events") {
      const after = Number(url.searchParams.get("after") ?? 0), limit = Math.min(200, Number(url.searchParams.get("limit") ?? 200));
      asked.push(after);
      const rest = events.filter((e) => e.seq > after), page = rest.slice(0, limit);
      return { schema: "sentilab-door-events/1", events: page, next_after: page.length ? page.at(-1).seq : after, has_more: rest.length > limit,
        scorer: { state: "up", since: 1793528287 } };
    }
    const after = Number(url.searchParams.get("after") ?? 0);
    if (url.pathname === "/api/open/v1/door/results") return after >= results.next_after ? { ...results, items: [], has_more: false } : results;
    if (url.pathname === "/api/open/v1/door/board") return doc("board.json");
    return null;
  });
  return { dom, asked };
}
const rows = () => walk(document.getElementById("visitorList")).filter((el) => el.className === "rec-row");
const button = (pred) => walk(document.getElementById("visitorList")).find((el) => el.tag === "button" && pred(el));

test("every record stays: older pages load on request, with no gap and no duplicate", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"], now: Date.parse("2026-11-01T18:00:00Z") });
  world(t);
  await import(`${LIVE}?records=paging`);
  for (let k = 0; k < 30; k += 1) { t.mock.timers.tick(200); await settle(); }
  const first = rows().length;
  assert.ok(first >= 40, `the newest records are listed: ${first}`);
  for (let i = 0; i < 6; i += 1) {
    const more = button((el) => el.attrs.get("id") === "recordMore");
    assert.ok(more, "a Show earlier records button");
    more.click();
    for (let k = 0; k < 20; k += 1) { t.mock.timers.tick(200); await settle(); }
  }
  const seqs = rows().map((el) => Number(el.attrs.get("title")?.replace("seq ", "")));
  assert.equal(seqs.length, 450, "all 450 records, one row each (several per visit)");
  assert.equal(new Set(seqs).size, 450, "no duplicate");
  assert.deepEqual([...seqs].sort((a, b) => a - b), Array.from({ length: 450 }, (_, i) => i + 1), "no gap");
  assert.ok(seqs.every((v, i) => i === 0 || v < seqs[i - 1]), "newest first");
  assert.match(button((el) => el.attrs.get("id") === "recordMore").textContent, /That is every record/);
});

test("population tabs filter the records; the aquarium's labels; a refused run says why", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"], now: Date.parse("2026-11-01T18:00:00Z") });
  const base = doc("results.json");
  const refused = { ...base.items[0], id: "open-0000beef-0000000000000000000000000000beef", short_id: "beef", label: "unknown \u00b7 beef", status: "rejected",
    codes: ["margin"], reason: null, result: null, summary: "rejected", arrival: 400, seq: 401 };
  const results = { ...base, items: [...base.items, refused], next_after: 401 };
  world(t, { results });
  await import(`${LIVE}?records=tabs`);
  for (let k = 0; k < 30; k += 1) { t.mock.timers.tick(200); await settle(); }
  const text = () => walk(document.getElementById("visitorList")).filter((el) => !(el.tag === "title")).flatMap((el) => el.children.filter((c) => !(c instanceof El)).map((c) => c.text)).join(" | ");
  assert.match(text(), /A likely human arrived/, "Likely human, in a sentence");
  assert.match(text(), /An unresolved visitor arrived/, "Unresolved, in a sentence");
  assert.match(text(), /Unresolved/, "the Unresolved label");
  // People tab: only likely humans.
  button((el) => el.dataset?.tab === "human").click();
  await settle();
  const people = rows().map((el) => el.textContent);
  assert.ok(people.length > 0 && people.every((r) => /A likely human/.test(r)), "the People tab shows only likely humans");
  button((el) => el.dataset?.tab === "bot").click();
  await settle();
  assert.ok(rows().every((el) => /An automation bot/.test(el.textContent)), "the Bots tab shows only automation");
  button((el) => el.dataset?.tab === "all").click();
  await settle();
  // The refused run: its reason in plain words, the raw code only in a title.
  const outcome = walk(document.getElementById("runList")).find((el) => el.className === "outcome refused");
  assert.ok(outcome, "the refused run's card says Refused");
  assert.match(outcome.textContent, /Refused · too close to the interposer edge/);
  assert.equal(/\bmargin\b/.test(outcome.textContent), false, "no raw code in the text");
  assert.equal(outcome.attrs.get("title"), "margin", "the raw code in the tooltip");
  // An accepted run says so, with its statistic and its replay.
  assert.match(text(), /Accepted · highest chiplet-centre average [0-9.]+ °C · simulated · replay matched/);
});
