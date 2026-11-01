// node --test web/test/package3d-source.test.mjs
// The agent-door adapter (web/public/sentilab/package/source3d.mjs): the bundled replay's schema and provenance, the
// legality of its layouts under the case's rules, what the adapter keeps and refuses (unknown fields and free text never
// pass), the one API seam and its poller. The API's own contract, against #81's recorded responses, is in
// package3d-feed.test.mjs; this file reads those recordings too where it needs an API page.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import * as door from "../public/sentilab/package/source3d.mjs";
import { DIE_IDS, DIES, RULES, INTERPOSER_MM } from "../public/sentilab/package/case-cpu-dram.mjs";
import { dieRects } from "../public/sentilab/package/model.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const repo = join(here, "..", "..");
const FIXTURE = join(repo, "web", "public", "sentilab", "package", "door-fixture.json");
const fixtureText = readFileSync(FIXTURE, "utf8");
const fixtureDoc = JSON.parse(fixtureText);
const ref = JSON.parse(readFileSync(join(repo, "docs/sentilab/references/micro150-tap25d-fig5a.json"), "utf8"));
const snap = JSON.parse(readFileSync(join(repo, "docs/sentilab/references/micro150-tap25d-fig5a-snap0p5.json"), "utf8"));
const respond = (body, status = 200) => new Response(typeof body === "string" ? body : JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const fileFetch = async () => respond(fixtureText);
const DIES8 = (rot = () => 0) => DIE_IDS.map((die, i) => ({ die, x_um: [18000, 27000, 27000, 18000, 8500, 36500, 36500, 8500][i], y_um: [17500, 17500, 27500, 27500, 17500, 17500, 27500, 27500][i], rot_deg: rot(i) }));
const GOOD = () => ({ id: "open-1a2b3c4d-00112233445566778899aabbccddeeff", label: "declared_agent · 3fa2", status: "queued", dies: DIES8() });
const RESULT = () => ({ metric_id: "max_chiplet_centre_cell_mean_C", value_C: 101.235, precision_K: 0.01, label: "simulated, not silicon", row0: "bottom", grid64: Array.from({ length: 4096 }, (_, k) => 50 + (k % 64)) });
// #81's recorded responses (package3d-feed.test.mjs says how they were made).
const API = JSON.parse(readFileSync(join(here, "door-api-d1b09d12.json"), "utf8")).responses;
const page = (name) => structuredClone(API[name].body);

// ── the case's placement rules, ported from sundai_hotspot/tap_oracle.py:359-410 (margin with halo, lattice, halo
//    overlap, minimum body gap), to check the fixture's layouts the same way the oracle does ──
function violations(layout) {
  const rects = dieRects(layout.dies), found = [];
  const m = RULES.edge_clearance_mm, S = INTERPOSER_MM, eps = 1e-9;
  const haloRect = (r) => [r.x0 - r.halo, r.y0 - r.halo, r.x1 + r.halo, r.y1 + r.halo];
  rects.forEach((r, i) => {
    const h = haloRect(r);
    if (Math.max(m - h[0], m - h[1], h[2] - (S - m), h[3] - (S - m)) > eps) found.push(`margin:${i}`);
    const off = Math.max(Math.abs(r.cx / RULES.lattice_mm - Math.round(r.cx / RULES.lattice_mm)), Math.abs(r.cy / RULES.lattice_mm - Math.round(r.cy / RULES.lattice_mm)));
    if (off > eps) found.push(`lattice:${i}`);
  });
  rects.forEach((a, i) => rects.slice(0, i).forEach((b, j) => {
    const A = haloRect(a), B = haloRect(b);
    if (!(A[2] <= B[0] || B[2] <= A[0] || A[3] <= B[1] || B[3] <= A[1])) found.push(`halo_overlap:${j},${i}`);
    const gap = Math.max(b.x0 - a.x1, a.x0 - b.x1, b.y0 - a.y1, a.y0 - b.y1);
    if (gap < RULES.body_gap_mm - eps) found.push(`min_spacing:${j},${i}`);
  }));
  return found;
}

// ── the fixture ──
test("the fixture: schema, order, labels and statuses; nothing refused", async () => {
  const feed = await door.loadFixture({ fetchImpl: fileFetch });
  assert.deepEqual(feed.refused, {});
  assert.deepEqual(feed.layouts.map((l) => [l.id, l.label, l.status]), [
    ["ref-raw", "reference-only · 6e54", "reference"],
    ["ref-snapped", "reference · ecfc", "reference"],
    ["example-537d", "example · 537d", "example"],
    ["example-2431", "example · 2431", "example"],
  ]);
  assert.equal(fixtureDoc.schema, door.REPLAY_SCHEMA);
  assert.equal(door.REPLAY_SCHEMA, "sentilab-package-replay/1", "page-owned: the retired sentilab-door-layouts/1 is no feed shape");
  assert.equal(fixtureDoc.fixture, true);
  // Short ids: the first 4 hex of the references' identity hashes, and of each example's compact layout string.
  assert.ok(ref.raw_annotations.identity.content_sha256.startsWith("6e54"));
  assert.ok(snap.identity.content_sha256.startsWith("ecfc"));
  const { createHash } = await import("node:crypto");
  for (const [id, compact] of Object.entries(fixtureDoc.provenance.compact)) {
    assert.equal(id, `example-${createHash("sha256").update(compact).digest("hex").slice(0, 4)}`);
    const steps = compact.split(",").map((s) => s.split(".").map(Number));
    const l = feed.layouts.find((x) => x.id === id);
    assert.deepEqual(l.dies.map((d) => [d.x_um / 500, d.y_um / 500, d.rot_deg / 90]), steps, "the compact form maps x*500, y*500, 90*r");
  }
  await assert.rejects(door.loadFixture({ fetchImpl: async () => respond({ ...fixtureDoc, fixture: false }) }), /not a door fixture/);
});

test("the fixture's references are the pinned reference files' centres, exactly; the snapped one has no temperature", async () => {
  const { layouts } = await door.loadFixture({ fetchImpl: fileFetch });
  // Compared in micrometres: the files' four-decimal millimetres are whole tenths of a micrometre.
  const um = (pairs) => pairs.map(([x, y]) => [Math.round(x * 10000) / 10, Math.round(y * 10000) / 10]);
  assert.deepEqual(layouts[0].dies.map((d) => [d.x_um, d.y_um]), um(ref.raw.centers_mm));
  assert.deepEqual(layouts[1].dies.map((d) => [d.x_um, d.y_um]), um(snap.centers_mm));
  assert.ok(layouts.every((l) => l.dies.every((d) => d.rot_deg === 0) || l.id === "example-2431"));
  assert.equal(layouts[1].result, null, "not evaluated: no invented snapped temperature");
  assert.equal(layouts[2].result, null);
  assert.equal(layouts[3].result, null);
});

test("legality: the snapped reference and both examples pass the oracle's rules; the raw reference fails only the lattice", async () => {
  const { layouts } = await door.loadFixture({ fetchImpl: fileFetch });
  assert.deepEqual(violations(layouts[0]), DIE_IDS.map((_, i) => `lattice:${i}`), "the reference file's own finding: 8 lattice misses, nothing else");
  assert.deepEqual(ref.raw.violations_without_center_lattice, []);
  for (const l of layouts.slice(1)) assert.deepEqual(violations(l), [], l.id);
  // Rotations: the catalogue only (CPU 0 or 90, DRAM 0); example-2431 turns its CPUs.
  assert.deepEqual(layouts[3].dies.map((d) => d.rot_deg), [90, 90, 90, 90, 0, 0, 0, 0]);
  // The check catches what it should (negative controls).
  const moved = structuredClone(layouts[1]);
  moved.dies[0].x_um = 4000;
  assert.ok(violations(moved).includes("margin:0") || violations(moved).some((v) => v.startsWith("halo_overlap")), "a die pushed into the edge band fails");
  const near = structuredClone(layouts[1]);
  near.dies[1].x_um = 26500;
  assert.ok(violations(near).some((v) => v.startsWith("halo_overlap:0,1")), "two CPUs whose halos overlap fail");
});

test("the raw reference's map: the gate-zero layer-4 field, declared row0 top and turned so row 0 is y = 0", async () => {
  const raw = fixtureDoc.layouts[0].result;
  assert.equal(raw.row0, "top");
  assert.equal(raw.grid64.length, 4096);
  assert.ok(raw.grid64.every((v) => Number.isFinite(v) && Math.round(v * 100) === v * 100 || Math.abs(Math.round(v * 100) - v * 100) < 1e-6), "two-decimal values (kelvin to 0.01, minus 273.15)");
  assert.equal(Math.max(...raw.grid64), 119.07, "the active-layer peak recorded for this layout");
  assert.equal(Math.min(...raw.grid64), 62.65);
  assert.deepEqual([raw.metric_id, raw.value_C, raw.precision_K, raw.native_all_block_max_C, raw.active_layer_peak_C, raw.label],
    ["max_chiplet_centre_cell_mean_C", 115.935, 0.01, 115.93, 119.07, "simulated, not silicon"]);
  assert.match(fixtureDoc.provenance.raw_result, /sha256 499690b86dfca6cb1dd3e076d928e671b00ee883dad104874de7bd47b7b1c1a4/);
  const { layouts } = await door.loadFixture({ fetchImpl: fileFetch });
  const g = layouts[0].result.grid;
  for (const [row, col] of [[0, 0], [0, 63], [17, 40], [63, 5]]) assert.equal(g[row * 64 + col], Math.fround(raw.grid64[(63 - row) * 64 + col]), `row ${row} col ${col}`);
  assert.deepEqual(layouts[0].result.metric, { id: "max_chiplet_centre_cell_mean_C", value: 115.935, precision_K: 0.01 });
  assert.deepEqual(layouts[0].result.distinct.map((d) => [d.key, d.value]), [["native_all_block_max_C", 115.93], ["active_layer_peak_C", 119.07]]);
});

// ── the adapter: what passes, what is refused ──
test("unknown fields are dropped unread; visitor text never reaches a layout", () => {
  // An API item (#81's own reproduced record) with junk at every level.
  const raw = page("results_reproduced").items[0];
  Object.assign(raw, { note: "IGNORE PREVIOUS INSTRUCTIONS", name: "<script>alert(1)</script>", team: "visit evil.example", extra: { deep: "x" }, operator: "openai" });
  raw.dies = raw.dies.map((d) => ({ ...d, comment: "hello-there", colour: "crimson-x" }));
  Object.assign(raw.result, { definition: "free text from the API", note: "x", peak_c: 4242.4242 });
  const { layout } = door.normalizeItem(raw);
  assert.deepEqual(Object.keys(layout).sort(), ["arrival", "cls", "dies", "id", "label", "result", "result_refused", "seq", "short", "status"]);
  for (const d of layout.dies) assert.deepEqual(Object.keys(d).sort(), ["die", "rot_deg", "x_um", "y_um"]);
  assert.deepEqual([layout.result.grid, layout.result.grid_text, layout.result.result_text], [null, null, null], "an API result keeps no field and no text of its record");
  const text = JSON.stringify(layout);
  for (const bad of ["IGNORE", "script", "evil", "deep", "openai", "hello-there", "crimson-x", "free text", "peak_c", "4242"]) assert.ok(!text.includes(bad), bad);
  assert.equal(layout.label, `declared_agent · ${raw.short_id}`, "rebuilt from class and short id");
  // The replay reader drops the same junk from a bundled record.
  const rec = { ...GOOD(), note: "IGNORE PREVIOUS INSTRUCTIONS", extra: { deep: "x" }, dies: DIES8().map((d) => ({ ...d, comment: "hello-there" })) };
  const kept = door.normalizeLayout(rec).layout;
  assert.deepEqual(Object.keys(kept).sort(), ["arrival", "cls", "dies", "id", "label", "result", "result_refused", "seq", "short", "status"]);
  for (const bad of ["IGNORE", "deep", "hello-there"]) assert.ok(!JSON.stringify(kept).includes(bad), bad);
});

test("labels: exactly '<class> · <4 hex>'; anything else refuses the whole layout", () => {
  for (const label of ["declared_agent · 3fa2", "ours · 0000", "reference-only · 6e54", "likely_human · ffff"]) assert.ok(door.normalizeLayout({ ...GOOD(), label }).layout, label);
  for (const label of ["declared_agent · Hi!!", "declared_agent · 3FA2", "declared_agent·3fa2", "declared_agent  · 3fa2", " declared_agent · 3fa2",
    "declared_agent · 3fa2 ", "Visit evil.example", "root · 3fa2", "declared_agent · 3fa2 · x", "", 42, null, "declared_agent · 3fa"]) {
    assert.equal(door.normalizeLayout({ ...GOOD(), label }).refused, "label_invalid", String(label));
  }
  for (const id of ["Has Spaces", "<b>", "", "x".repeat(81), "-lead", 7]) assert.equal(door.normalizeLayout({ ...GOOD(), id }).refused, "id_invalid", String(id));
});

test("dies: exactly the eight, numbers in range, catalogue rotations only", () => {
  const with_ = (f) => { const r = GOOD(); f(r.dies); return door.normalizeLayout(r).refused; };
  assert.equal(with_((d) => d.pop()), "dies_count");
  assert.equal(with_((d) => d.push({ ...d[0] })), "dies_count");
  assert.equal(with_((d) => { d[7] = { ...d[0] }; }), "die_duplicate");
  assert.equal(with_((d) => { d[0].die = "C4"; }), "die_unknown");
  assert.equal(with_((d) => { d[0].x_um = NaN; }), "coord_not_number");
  assert.equal(with_((d) => { d[0].y_um = "17500"; }), "coord_not_number");
  assert.equal(with_((d) => { d[0].x_um = Infinity; }), "coord_not_number");
  assert.equal(with_((d) => { d[0].x_um = 1e12; }), "coord_out_of_range");
  assert.equal(with_((d) => { d[0].y_um = -1e6; }), "coord_out_of_range");
  assert.equal(with_((d) => { d[0].rot_deg = 180; }), "rotation_not_allowed");
  assert.equal(with_((d) => { d[4].rot_deg = 90; }), "rotation_not_allowed", "DRAM 0 only");
  assert.equal(with_((d) => { d[1].rot_deg = 90; }), undefined, "CPU 90 is allowed");
  const shuffled = GOOD();
  shuffled.dies.reverse();
  assert.deepEqual(door.normalizeLayout(shuffled).layout.dies.map((d) => d.die), DIE_IDS, "kept in the fixed order");
  assert.equal(door.normalizeLayout({ ...GOOD(), hidden: true }).refused, "hidden");
  assert.equal(door.normalizeLayout("x").refused, "not_an_object");
});

test("statuses: the contract's lifecycle; 'reference' and 'example' only in the bundled replay", () => {
  for (const status of [...door.STATUSES, ...door.FIXTURE_STATUSES]) assert.ok(door.normalizeLayout({ ...GOOD(), status }).layout, status);
  assert.equal(door.normalizeLayout({ ...GOOD(), status: "won" }).refused, "status_unknown");
  const item = page("results_queued_page2").items[0];
  for (const status of door.STATUSES) assert.ok(door.normalizeItem({ ...item, status }).layout, status);
  for (const status of door.FIXTURE_STATUSES) assert.equal(door.normalizeItem({ ...item, status }).refused, "status_unknown", `${status}: never from the API`);
});

test("replay results: the frozen board metric only, a declared grid orientation, a scored state; a bad result drops the map, not the layout", () => {
  const scored = (result, status = "reference") => door.normalizeLayout({ ...GOOD(), status, result });
  const ok = scored(RESULT()).layout;
  assert.deepEqual(ok.result.metric, { id: "max_chiplet_centre_cell_mean_C", value: 101.235, precision_K: 0.01 });
  assert.equal(ok.result.field_state, "pending", "a bundled field waits for its pin check");
  assert.equal(ok.result.grid[5], 55, "row0 bottom: kept as given");
  const top = scored({ ...RESULT(), row0: "top" }).layout;
  assert.equal(top.result.grid[0], RESULT().grid64[63 * 64], "row0 top: turned so row 0 is y = 0");
  const refusal = (r, status) => scored(r, status).layout.result_refused;
  assert.equal(refusal({ ...RESULT(), metric_id: "peak_c" }), "metric_unknown");
  assert.equal(refusal({ ...RESULT(), metric_id: "active_layer_peak_C" }), "metric_unknown", "never another statistic as the board metric");
  assert.equal(refusal({ ...RESULT(), value_C: "115" }), "metric_value");
  assert.equal(refusal({ ...RESULT(), precision_K: undefined }), "precision_missing");
  assert.equal(refusal({ ...RESULT(), label: "preview, not the scorer" }), "result_label_unknown");
  assert.equal(refusal({ ...RESULT(), row0: undefined }), "grid_orientation_missing");
  assert.equal(refusal({ ...RESULT(), grid64: RESULT().grid64.slice(1) }), "grid_size");
  assert.equal(refusal({ ...RESULT(), grid64: RESULT().grid64.map((v, k) => (k === 77 ? NaN : v)) }), "grid_value");
  assert.equal(refusal({ ...RESULT(), active_layer_peak_C: 1e9 }), "distinct_value");
  for (const status of ["queued", "evaluating", "failed", "rejected"]) assert.equal(refusal(RESULT(), status), "result_not_scored_state", status);
  const noGrid = scored({ ...RESULT(), grid64: undefined, row0: undefined }).layout;
  assert.deepEqual([noGrid.result.grid, noGrid.result.field_state], [null, "unassociated"], "a value without a map");
  assert.ok(scored({ ...RESULT(), metric_id: "x" }).layout, "the layout itself still draws");
});

test("normalizeReplay and normalizeResults: caps, duplicate ids, and what is not one", () => {
  const many = { layouts: Array.from({ length: 520 }, (_, i) => ({ ...GOOD(), id: `l${i}` })) };
  const f = door.normalizeReplay(many);
  assert.equal(f.layouts.length, door.BOUNDS.layouts);
  assert.equal(f.refused.over_cap, 20);
  const dup = door.normalizeReplay({ layouts: [GOOD(), GOOD()] });
  assert.deepEqual([dup.layouts.length, dup.refused], [1, { id_duplicate: 1 }]);
  assert.deepEqual(door.normalizeReplay([1, 2]).refused, { not_a_replay: 1 });
  const results = page("results_reproduced");
  results.items.push(structuredClone(results.items[0]));
  assert.deepEqual(door.normalizeResults(results).refused, { id_duplicate: 1 }, "one run twice on a page is drawn once");
  for (const edit of [{ schema: "sentilab-door-layouts/1" }, { next_after: -1 }, { next_after: 1.5 }, { next_after: "18" }, { has_more: "no" },
    { items: {} }, { metric: null }]) {
    assert.equal(door.normalizeResults({ ...page("results_reproduced"), ...edit }), null, JSON.stringify(edit));
  }
  assert.equal(door.normalizeEvents({ ...page("events_all"), next_after: 2 ** 53 }), null, "past the API's own cursor range");
});

test("mergeArrivals: first arrival keeps its place; a later record updates status and result", () => {
  const a = door.normalizeLayout({ ...GOOD(), id: "a" }).layout, b = door.normalizeLayout({ ...GOOD(), id: "b" }).layout;
  const a2 = door.normalizeLayout({ ...GOOD(), id: "a", status: "evaluated", result: RESULT() }).layout;
  const merged = door.mergeArrivals(door.mergeArrivals([], [a, b]), [a2]);
  assert.deepEqual(merged.map((l) => [l.id, l.status]), [["a", "evaluated"], ["b", "queued"]]);
  const s1 = door.normalizeLayout({ ...GOOD(), id: "s1", seq: 9 }).layout, s2 = door.normalizeLayout({ ...GOOD(), id: "s2", seq: 3 }).layout;
  assert.deepEqual(door.mergeArrivals([s1], [s2]).map((l) => l.id), ["s1", "s2"], "seq is a record version: order is first arrival");
});

// ── the seam ──
test("the poller: results then events, page by page; a failure keeps the cursors and backs off; then it resumes", async () => {
  // #81's recorded pages, in the order the poller asks for them.
  const script = [page("results_queued_page1"), page("results_queued_page2"), page("events_page"), page("events_all"),
    503, page("results_reproduced"), page("events_all")];
  const seen = [];
  let t = 1000;
  const fetchImpl = async (url) => { seen.push(url); const next = script.shift(); return typeof next === "number" ? respond("down", next) : respond(next); };
  const changes = [];
  const feed = door.createDoorFeed({ fetchImpl, now: () => t, onChange: (s) => changes.push({ connected: s.connected, n: s.layouts.length, cursor: s.cursor, events: s.eventsCursor }) });
  assert.equal(await feed.pollOnce(), door.POLL_MS);
  assert.deepEqual(seen, ["/api/open/v1/door/results?after=0", "/api/open/v1/door/results?after=4", "/api/open/v1/door/events?after=0", "/api/open/v1/door/events?after=3"]);
  assert.deepEqual(changes.at(-1), { connected: true, n: 3, cursor: 5, events: 41 });
  t = 5000;
  assert.equal(await feed.pollOnce(), door.BACKOFF_MS);
  assert.deepEqual(changes.at(-1), { connected: false, n: 3, cursor: 5, events: 41 }, "a failure keeps the layouts and the cursors");
  assert.equal(feed.state.error, "answered 503");
  assert.equal(door.statusLine({ source: "api", feed: feed.state, hostname: "sentilab.aidenid.com", nowMs: 5000 }), "replay", "a feed that stopped answering is not live");
  t = 9000;
  await feed.pollOnce();
  assert.deepEqual(seen.slice(-2), ["/api/open/v1/door/results?after=5", "/api/open/v1/door/events?after=41"], "resumes from the last good cursors");
  assert.deepEqual(feed.state.layouts.map((l) => l.status), ["reproduced", "reproduced", "reproduced"]);
  assert.equal(feed.state.events.length, door.BOUNDS.events);
  assert.equal(door.statusLine({ source: "api", feed: feed.state, hostname: "sentilab.aidenid.com", nowMs: 9000 }), "live");
  assert.equal(door.statusLine({ source: "api", feed: feed.state, hostname: "staging.sentilab.aidenid.com", nowMs: 9000 }), "staging", "the staging host");
  assert.equal(door.statusLine({ source: "api", feed: feed.state, hostname: "127.0.0.1", nowMs: 9000 }), "staging", "this machine");
  assert.equal(door.statusLine({ source: "api", feed: feed.state, hostname: "sentilab.aidenid.com", nowMs: 9000 + door.LIVE_FRESH_MS + 1 }), "replay", "stale is not live");
  assert.equal(door.statusLine({ source: "fixture", feed: feed.state, hostname: "sentilab.aidenid.com", nowMs: 9000 }), "replay");
});

test("the page modules talk to the API only through the seam, by GET", () => {
  const dir = join(repo, "web", "public", "sentilab", "package");
  for (const f of ["door.mjs", "render3d.mjs", "model.mjs", "case-cpu-dram.mjs"]) {
    const src = readFileSync(join(dir, f), "utf8");
    assert.doesNotMatch(src, /\bfetch\s*\(/, `${f} never fetches`);
    assert.doesNotMatch(src, /new (WebSocket|EventSource|XMLHttpRequest)|sendBeacon\(/, `${f}: polling only`);
  }
  const src = readFileSync(join(dir, "source3d.mjs"), "utf8");
  assert.equal(src.match(/fetchImpl\(`/g)?.length, 1, "one call site for the API");
  assert.match(src, /r = await fetchImpl\(`\$\{path\}\?after=\$\{cursor\}`, \{ method: "GET",/);
  assert.doesNotMatch(src, /method:\s*"(POST|PUT|PATCH|DELETE)"/);
  assert.doesNotMatch(src, /new (WebSocket|EventSource|XMLHttpRequest)|sendBeacon\(/);
});
