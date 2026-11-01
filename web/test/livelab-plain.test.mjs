// node --test web/test/livelab-plain.test.mjs (from the repository root) or node --test test/livelab-plain.test.mjs (from web/)
// Carter (#58250): the Live Lab must read in plain words. Its visible text, rendered from the recorded feeds, holds no
// UTC stamps ("17:08:46Z"), no raw visitor-class codes (declared_agent and the rest) and no "seq " numbers; titles and
// tooltips may keep them. "unvalidated" and "self-declared, not verified" stay exactly as they are.
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

const UTC = /\b\d{1,2}:\d{2}(:\d{2})?(\.\d+)?Z\b/;
const CODES = /(?<![\w-])(declared_agent|verified_agent|signed_agent|crawler_claimed|likely_human|automation)(?![\w-])/;

test("the page reads in plain words: no UTC stamps, no class codes, no seq numbers in its visible text", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "setInterval", "Date"], now: Date.parse("2026-11-01T15:30:00Z") });
  const results = doc("results.json"), events = doc("events.json"), board = doc("board.json"), visitors = doc("visitors-declarations.json");
  const dom = installPage(t, (url) => {
    const after = Number(url.searchParams.get("after") ?? 0);
    if (url.pathname === "/api/open/v1/door/results") return after >= results.next_after ? { ...results, items: [], has_more: false } : results;
    if (url.pathname === "/api/open/v1/door/events") return after >= events.next_after ? { ...events, events: [], has_more: false } : events;
    if (url.pathname === "/api/open/v1/door/board") return board;
    if (url.pathname === "/api/open/v1/door/visitors") return after >= visitors.next_after ? { ...visitors, items: [], has_more: false } : visitors;
    return null;
  });
  await import(`${LIVE}?plain=1`);
  for (let k = 0; k < 8; k += 1) { t.mock.timers.tick(1000); await settle(); }
  const text = dom.page().text;
  const all = text.join(" | ");
  assert.ok(all.includes("Run 5cb8"), "the page rendered the recorded runs");
  const stamps = text.filter((s) => UTC.test(s));
  assert.deepEqual(stamps, [], "no UTC time stamps in visible text");
  const codes = text.filter((s) => CODES.test(s));
  assert.deepEqual(codes, [], "no raw visitor-class codes in visible text");
  const seqs = text.filter((s) => /\bseq /.test(s));
  assert.deepEqual(seqs, [], "no seq numbers in visible text");
  // Carter (18:15Z): each temperature reads "simulated" (not a repeated "unvalidated"), and one line at the top says
  // what that means.
  assert.equal(document.getElementById("tempLine").textContent,
    "Every temperature here comes from a published heat model. It is simulated, not measured on real chips.");
  const temps = [];
  const visit = (el) => {
    const own = el.children.filter((c) => !(c instanceof El)).map((c) => c.text).join("");
    if (/\d+(\.\d+)? °C/.test(own) || el.id === "metricValue") temps.push(el);
    for (const c of el.children) if (c instanceof El && c.tag !== "title") visit(c);
  };
  for (const id of ["runList", "mobileRuns", "metricValue", "modelCap", "visitorList", "declList"]) visit(document.getElementById(id));
  assert.ok(temps.length >= 3, `temperatures found: ${temps.length}`);
  for (const el of temps) assert.match(el.textContent, /simulated/, `every temperature carries "simulated": ${el.textContent}`);
  assert.equal(text.some((x) => /\bunvalidated\b/.test(x)), false, "no repeated unvalidated in visible text");
  assert.ok(all.includes("self-declared, not verified"), "the declaration label stays");
});
