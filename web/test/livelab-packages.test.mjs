// node --test test/livelab-packages.test.mjs (from web/)
// Carter (22:13Z): "since it's open source when packages are ready with all stuff post them too. Maybe make a page for
// that and put a button there somewhere in the front page". /sentilab/packages/ lists every accepted layout whose
// replay matched, coolest first, reading every page of the public results feed through the Live Lab's gate; each row
// downloads the same package the Live Lab builds (live/package-export.mjs). The front page links to it and to /docs/.
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

const P = await import(pathToFileURL(join(HERE, "..", "public", "sentilab", "live", "package-export.mjs")).href);
const PAGE = pathToFileURL(join(HERE, "..", "public", "sentilab", "packages", "packages.mjs")).href;
const walk = (el, out = []) => { if (!el) return out; out.push(el); for (const c of el.children ?? []) if (c instanceof El) walk(c, out); return out; };
// Three pages of results: accepted and replay-matched (keep), refused, unreproduced, and accepted without a matching
// replay (all three left out), across every page.
function feed(allow = null) {
  const base = doc("results.json").items[0];
  const run = (hex, seq, status, value, replay = "reproduced", wire = 10) => ({ ...base, id: `open-0000beef-${"0".repeat(28)}${hex}`, short_id: hex, label: `unknown · ${hex}`,
    seq, arrival: 100 + seq, status, wire_proxy_mm: wire,
    result: status === "rejected" ? null : { ...base.result, max_chiplet_centre_cell_mean_C: value, verification: { ...base.result.verification, replay } } });
  const pages = [
    [run("a001", 1, "reproduced", 110.25, "reproduced", 9.5), run("b002", 2, "rejected", null)],
    [run("c003", 3, "not_reproduced", 90, "not_reproduced"), run("d004", 4, "reproduced", 98.5, "reproduced", 12)],
    [run("e005", 5, "cross_checked", 105, "reproduced", 11), run("f006", 6, "reproduced", 80, "pending")],
  ];
  const asked = [];
  const answer = (url) => {
    const after = Number(url.searchParams.get("after") ?? 0);
    if (url.pathname === "/sentilab/packages/licensed-runs.json") return allow;
    if (url.pathname === "/api/open/v1/door/results") {
      asked.push(after);
      const i = after === 0 ? 0 : after === 2 ? 1 : after === 4 ? 2 : 3;
      const items = pages[i] ?? [];
      return { schema: "sentilab-door-results/1", items, next_after: items.length ? items.at(-1).seq : after, has_more: i < 2, metric: base.metric, label: "simulated, not silicon" };
    }
    if (url.pathname === "/api/open/v1/door/events") {
      const r = pages.flat().find((x) => x.arrival === after + 1);
      return { schema: "sentilab-door-events/1", events: r ? [{ seq: r.arrival, at: "2026-11-01T21:30:00Z", kind: "run", class: "unknown", label: r.label, run_id: r.id, short_id: r.short_id, state: "queued" }] : [],
        next_after: after + 1, has_more: false };
    }
    return null;
  };
  return { answer, asked, pages };
}
async function openPage(t, tag, allow = null) {
  const f = feed(allow);
  const dom = installPage(t, f.answer);
  location.href = "https://sentilab.aidenid.com/sentilab/packages/";
  const mod = await import(`${PAGE}?t=${tag}`);
  await mod.ready;
  return { f, dom, mod };
}
const items = () => walk(document.getElementById("packageList")).filter((el) => el.tag === "li");

test("packages page: every page of the feed is read; only accepted, replay-matched layouts are listed, coolest first", async (t) => {
  const { f } = await openPage(t, "list");
  assert.deepEqual(f.asked, [0, 2, 4], "every page, from the start");
  const rows = items().map((el) => el.textContent);
  assert.equal(rows.length, 3);
  assert.match(rows[0], /visit d004.*highest chiplet-centre average 98\.50 °C · simulated · wire proxy 12 mm.*replay matched.*submitted /);
  assert.match(rows[1], /visit e005/); assert.match(rows[2], /visit a001/);
  for (const hex of ["b002", "c003", "f006"]) assert.equal(rows.some((r) => r.includes(hex)), false, `${hex} is not listed`);
  assert.equal(/unvalidated/i.test(rows.join(" ")), false);
  assert.match(document.getElementById("feedState").textContent, /Every page read · 3 listed/);
  // The allowlist is empty here (Terms v1): every accepted layout is view only, and nothing downloads.
  assert.equal(walk(document.getElementById("packageList")).some((el) => el.tag === "button"), false, "no download button");
  assert.equal(rows.every((r) => r.includes("View only: shown under the door’s terms, not licensed for redistribution")), true);
  assert.equal(document.getElementById("allJson").disabled, true); assert.equal(document.getElementById("allCsv").disabled, true);
});

const licensedIds = ["d004", "a001"].map((hex) => `open-0000beef-${"0".repeat(28)}${hex}`);
const allow = { schema: "sentilab-licensed-runs/1", items: licensedIds.map((run_id) => ({ run_id, visit: null, owner_role: "team", licence: "CC BY 4.0", confirmed_by: "the team", confirmed_at: "2026-11-01T22:30:00Z" })) };
test("packages page: licensed rows download exactly their per-run package; Download all holds only licensed ones; the rest are view only", async (t) => {
  const { f } = await openPage(t, "downloads", allow);
  const blobs = [];
  const saved = { create: URL.createObjectURL, revoke: URL.revokeObjectURL };
  URL.createObjectURL = (blob) => { blobs.push(blob); return `blob:test/${blobs.length}`; };
  URL.revokeObjectURL = () => {};
  t.after(() => { URL.createObjectURL = saved.create; URL.revokeObjectURL = saved.revoke; });
  const raws = f.pages.flat();
  const without = (pkg) => ({ ...pkg, source: { ...pkg.source, generated_at: null } });
  const licences = P.readLicences(allow);
  const expected = (hex) => { const raw = raws.find((r) => r.short_id === hex); return without(P.engineerPackage(raw,
    { licence: licences.get(raw.id), submittedAt: "2026-11-01T21:30:00Z", pageUrl: "https://sentilab.aidenid.com/sentilab/packages/", generatedAt: null })); };
  const texts = items().map((el) => el.textContent);
  assert.match(texts[0], /visit d004.*licensed CC BY 4\.0/); assert.match(texts[1], /visit e005.*View only: shown under the door’s terms, not licensed for redistribution/);
  assert.equal(walk(items()[1]).some((el) => el.tag === "button"), false, "the unlicensed row has no download");
  walk(items()[0]).find((el) => el.tag === "button").click();
  const one = JSON.parse(await blobs[0].text());
  assert.deepEqual(without(one), expected("d004"), "the row's package is the per-run package");
  assert.equal(walk(document.body).filter((el) => el.tag === "a").at(-1).getAttribute("download"), P.packageName(raws.find((r) => r.short_id === "d004")));
  document.getElementById("allJson").click();
  const all = JSON.parse(await blobs[1].text());
  assert.equal(all.schema, "sentilab-engineer-packages/1");
  assert.deepEqual(all.packages.map(without), ["d004", "a001"].map(expected), "Download all: the licensed packages, coolest first");
  assert.equal(all.packages[0].licence, "CC BY 4.0");
  document.getElementById("allCsv").click();
  const csv = (await blobs[2].text()).trim().split("\n");
  assert.equal(csv.length, 1 + 1 + 2, "header, the reference row, one row per licensed layout");
  assert.match(csv[2], /^1,d004,/);
});

test("front page: the header links to Packages and Docs, and so does the footer", () => {
  const html = readFileSync(join(HERE, "..", "public", "sentilab", "live", "index.html"), "utf8");
  const nav = html.match(/<nav aria-label="Main">([\s\S]*?)<\/nav>/)[1];
  assert.match(nav, /<a class="nav-item" href="\/sentilab\/packages\/">Packages<\/a>/);
  assert.match(nav, /<a class="nav-item" href="\/docs\/">Docs<\/a>/);
  const footer = html.match(/<footer>([\s\S]*?)<\/footer>/)[1];
  assert.match(footer, /href="\/sentilab\/packages\/">Packages</); assert.match(footer, /href="\/docs\/">Docs</);
  const page = readFileSync(join(HERE, "..", "public", "sentilab", "packages", "index.html"), "utf8");
  assert.match(page, /<h1 id="pageTitle">Packages: every accepted layout, ready for engineers<\/h1>/);
  assert.match(page, /Simulated, not measured on real chips\. Each package lists what is not claimed\./);
  assert.match(page, /href="\/docs\/"/);
  assert.match(page, /<p class="licence-note" id="licenceNote">Downloads are offered only for layouts their owners have licensed for redistribution\./);
  assert.equal(/<script(?![^>]*\bsrc=)/.test(page) || /\sstyle=/.test(page), false, "no inline script or style (CSP)");
});
