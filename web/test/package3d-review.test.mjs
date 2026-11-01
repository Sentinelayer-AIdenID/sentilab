// node --test web/test/package3d-review.test.mjs
// PR #78 review (root, at 4e04718): the six independent controls, rebuilt as failing-first tests, plus a test per fix.
//   C1, C2, C3  R1  a door result is not drawable on payload shape; temperatures carry the shared label; D14
//   C4, C5      R2  a live answer after stop() changes nothing; an older record never replaces a newer one
//   C6          R3  a field is identified by its content, never by its score
//   R4              a field shows only with its own geometry: hard cuts, hidden while dies move, never blended
//   R5              a lost renderer is released (frames, listeners) and rebuilt on restore
// And root's focused review at 35323889: P2 (the R1 remainder: the pin covers the orientation and every statistic shown,
// root's two metadata-only controls) and P3 (an explode step queued before a context loss).
// Each module is imported inside its test, so on a tree without a fix only that test fails, with its own message.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash, webcrypto } from "node:crypto";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const PKG = join(here, "..", "public", "sentilab", "package");
const mod = (name) => import(pathToFileURL(join(PKG, name)).href);
const src = (name) => readFileSync(join(PKG, name), "utf8");
const labels = () => import(pathToFileURL(join(here, "..", "public", "temperature-label.mjs")).href);
const FIXTURE = JSON.parse(readFileSync(join(PKG, "door-fixture.json"), "utf8"));
const sha256 = (text) => createHash("sha256").update(text, "utf8").digest("hex");
const DIES = () => ["C0", "C1", "C2", "C3", "D0", "D1", "D2", "D3"].map((die, i) =>
  ({ die, x_um: [18000, 27000, 27000, 18000, 8500, 36500, 36500, 8500][i], y_um: [17500, 17500, 27500, 27500, 17500, 17500, 27500, 27500][i], rot_deg: 0 }));
const grid = (f) => Array.from({ length: 4096 }, (_, k) => f(k));
const counted = () => {
  const c = { digests: 0 };
  return { c, subtle: { digest: (alg, bytes) => { c.digests += 1; return webcrypto.subtle.digest(alg, bytes); } } };
};

// ── R1 ────────────────────────────────────────────────────────────────────────────────────────────────────────────
// C1: a synthetic scored API row with a 4,096-value field, a withdrawn HotSpot 7 identity and invalid signature,
// producer, model and geometry hashes, read where WebCrypto is absent. Before the fix it came back drawable, with only
// metric, grid, label and distinct kept and no hash or signature checked.
const C1_ROW = () => ({
  id: "open-1a2b3c4d-00112233445566778899aabbccddeeff", label: "declared_agent · 3fa2", status: "evaluated", seq: 4, dies: DIES(),
  result: { metric_id: "max_chiplet_centre_cell_mean_C", value_C: 101.23, precision_K: 0.01, label: "simulated, not silicon",
    row0: "bottom", grid64: grid((k) => 60 + (k % 50)), evaluator: "HotSpot-7:f18831e48cef5d62580585cca0d7fab6c71bc3cc:grid:64x64",
    signature: "A".repeat(86), producer_sha256: "0".repeat(64), model_sha256: "1".repeat(64), geometry_sha256: "2".repeat(64) },
});
test("C1 (R1): an unsigned door result with a plausible field is not drawable; its field is unassociated and not kept", async () => {
  const door = await mod("source3d.mjs");
  const { layouts } = door.normalizeFeed({ schema: door.FEED_SCHEMA, layouts: [C1_ROW()] }, { source: "api" });
  const r = layouts[0].result;
  assert.equal(r.field_state, "unassociated", "the door feed is unsigned: no admitted association");
  assert.equal(r.grid, null, "an unassociated field is not kept, so it can never be drawn");
  assert.equal(r.diagnostic, true, "its value is a qualified diagnostic");
  assert.equal(typeof door.verifyPinnedFields, "function");
  const { c, subtle } = counted();
  const checked = await door.verifyPinnedFields(layouts, { subtle });
  assert.equal(checked[0].result.field_state, "unassociated", "no pin admits it");
  assert.equal(c.digests, 0, "nothing in the payload is taken as provenance");
  const none = await door.verifyPinnedFields(layouts, { subtle: null });
  assert.equal(none[0].result.grid, null, "without WebCrypto either");
  // The payload's claims are not carried: neither its hashes, its signature nor its claimed evaluator.
  const kept = JSON.stringify({ ...r, grid: null });
  for (const claim of ["AAAA", "0000000000", "1111111111", "2222222222", "HotSpot-7"]) assert.ok(!kept.includes(claim), claim);
});

// C2: the label rule gives "withdrawn" for that identity, while the door kept only its generic claim string. Now every
// temperature carries a shared LABELS object; a value without a verified identity is labelFor(undefined), "unvalidated"
// (PL-6: never the artifact's claim), which shows the notice; and no text is made from a temperature without one.
test("C2 (R1): the result's temperatures carry a shared label, never the generic claim alone (PL-2, PL-6)", async () => {
  const { LABELS, labelFor } = await labels();
  assert.equal(labelFor(C1_ROW().result.evaluator), LABELS.withdrawn, "the rule itself, for that claimed identity");
  const door = await mod("source3d.mjs");
  const r = door.normalizeLayout(C1_ROW()).layout.result;
  assert.equal(r.label, LABELS.unvalidated, "an unverified identity: labelFor(undefined)");
  assert.ok(r.label.notice, "and the page shows the shared notice");
  assert.equal(r.claim, "simulated, not silicon", "the scorer's claim stays beside it, not instead of it");
  const { formatTemp, tempNode } = await mod("temps.mjs");
  assert.deepEqual({ ...formatTemp(115.935, LABELS.unvalidated, { digits: 2 }) },
    { text: "115.94 °C", qualifier: "unvalidated", title: LABELS.unvalidated.title, state: "unvalidated", notice: true });
  assert.equal(formatTemp(119.065, LABELS.withdrawn, { digits: 2 }).text, "119.07 °C", "half up, display only");
  assert.throws(() => formatTemp(101.23, "simulated, not silicon"), /LABELS/, "a claim string is not a label");
  assert.throws(() => formatTemp(101.23, { ...LABELS.accepted }), /LABELS/, "a label of the right shape is not a label");
  assert.throws(() => formatTemp(NaN, LABELS.unvalidated), /finite/);
  const h = (tag, props, ...kids) => ({ tag, props, kids: kids.flat() });
  const node = tempNode(h, 101.23, LABELS.unvalidated, { digits: 2 });
  assert.equal(node.props.class, "t s-unvalidated");
  assert.deepEqual([node.kids[0], node.kids[2].tag, node.kids[2].kids[0]], ["101.23 °C", "em", "unvalidated"], "value and qualifier in one element");
  // The door makes temperature text only through temps.mjs, always with a label.
  const d = src("door.mjs");
  assert.match(d, /import \{ formatTemp, tempNode \} from "\.\/temps\.mjs";/);
  assert.doesNotMatch(d, /formatTemp\([^,()]+\)/, "no one-argument formatTemp");
  assert.doesNotMatch(src("model.mjs"), /export function formatTemp/, "no label-free formatter left");
  assert.match(d, /\$\("wnotice"\)\.textContent = \$\("wnotice"\)\.hidden \? "" : NOTICE;/, "the notice text is the shared constant");
});

// C3 (R1, D14): the bundled raw reference's map is the one admitted association (a pin in reviewed page code). It is
// drawn only after WebCrypto recomputes both digests; without WebCrypto no result field is drawn.
test("C3 (R1, D14): the pinned field is drawn only after both digests check out; without WebCrypto, never", async () => {
  const door = await mod("source3d.mjs");
  const { FIELD_PINS, GATE_ZERO_EVALUATOR } = await mod("case-cpu-dram.mjs");
  const { LABELS, labelFor } = await labels();
  const fixture = door.normalizeFeed(FIXTURE, { source: "fixture" }).layouts;
  assert.equal(fixture[0].result.field_state, "pending");
  const noCrypto = await door.verifyPinnedFields(fixture, { subtle: null });
  assert.equal(noCrypto[0].result.field_state, "file_check_unavailable");
  assert.equal(noCrypto[0].result.grid, null);
  const { c, subtle } = counted();
  const ok = await door.verifyPinnedFields(fixture, { subtle });
  assert.equal(c.digests, 3, "geometry, field and the rest of the result record, recomputed here");
  const raw = ok[0].result;
  assert.equal(raw.field_state, "verified");
  assert.equal(raw.field_key, FIELD_PINS[0].field_sha256);
  assert.equal(raw.field_key, sha256(JSON.stringify(FIXTURE.layouts[0].result.grid64)), "the pin covers the field's exact text");
  assert.equal(raw.label, labelFor(GATE_ZERO_EVALUATOR));
  assert.equal(raw.label, LABELS.unvalidated, "HotSpot 6.0 is not on the accepted list: unvalidated, with the notice");
  assert.equal(raw.diagnostic, false);
  assert.ok(ok.slice(1).every((L) => L.result === null), "the snapped reference and the examples have no result");
  // A changed cell or a moved die breaks the association: no field is drawn.
  const cell = structuredClone(FIXTURE);
  cell.layouts[0].result.grid64[2000] += 0.01;
  assert.equal((await door.verifyPinnedFields(door.normalizeFeed(cell, { source: "fixture" }).layouts, { subtle: webcrypto.subtle }))[0].result.field_state, "mismatch");
  const moved = structuredClone(FIXTURE);
  moved.layouts[0].dies[0].x_um += 1;
  const m = (await door.verifyPinnedFields(door.normalizeFeed(moved, { source: "fixture" }).layouts, { subtle: webcrypto.subtle }))[0].result;
  assert.deepEqual([m.field_state, m.grid, m.field_key], ["mismatch", null, null]);
  // The door draws only a verified field, and draws no result at all without WebCrypto.
  const d = src("door.mjs");
  assert.match(d, /r\.field_state === "verified" && r\.grid && r\.field_key && !D\.noCrypto \? fieldTexels\(r\.grid, r\.field_key\) : null/);
  assert.match(d, /const resultShown = \(L\) => Boolean\(L\?\.result\) && !D\.noCrypto;/);
  assert.match(d, /verifyPinnedFields\(fixture\.layouts, \{ subtle: globalThis\.crypto\?\.subtle \?\? null \}\)/);
});

// ── R1 remainder (root's focused review at 35323889, P2) ─────────────────────────────────────────────────────────
// A passed pin check lent the pinned identity to metadata it never checked: the field's orientation (row0) and the
// statistics shown with it. Root's two metadata-only controls, against the unchanged production pin and fixture. At
// 35323889 both came back "verified" and not diagnostic; the pin must refuse both (no map, the values diagnostic,
// labelFor(undefined)).
async function pinnedRaw(edit) {
  const door = await mod("source3d.mjs");
  const doc = structuredClone(FIXTURE);
  edit(doc.layouts[0].result);
  const layouts = door.normalizeFeed(doc, { source: "fixture" }).layouts;
  return { pending: layouts[0].result, checked: (await door.verifyPinnedFields(layouts, { subtle: webcrypto.subtle }))[0].result };
}
const f32sha = (g) => createHash("sha256").update(Buffer.from(g.buffer, g.byteOffset, g.byteLength)).digest("hex");
test("P2 control 1 (R1): flipping only row0, top to bottom, is not admitted by the same pin", async () => {
  const { LABELS } = await labels();
  const top = await pinnedRaw(() => {});
  const flip = await pinnedRaw((r) => { r.row0 = "bottom"; });
  // The control can fail: the flip reflects the normalized field (root's numbers: 452 cells, these byte digests) while
  // the field's text, and so field_sha256, stays the same.
  assert.equal(top.pending.grid.filter((v, i) => v !== flip.pending.grid[i]).length, 452);
  assert.deepEqual([f32sha(top.pending.grid), f32sha(flip.pending.grid)],
    ["a14dad70de1a7f0101ee9d6d64a8d11bf9a01d78db659982ddf10a4f5bfb2efc", "512b2f62f9e09589a3f4ec19860c0234eee3aad73028615097294b906f9691aa"]);
  assert.equal(top.checked.field_state, "verified", "the unchanged fixture still verifies");
  assert.notEqual(flip.checked.field_state, "verified", "an orientation the pin did not check is not admitted");
  assert.equal(flip.checked.field_state, "mismatch");
  assert.deepEqual([flip.checked.grid, flip.checked.field_key, flip.checked.diagnostic], [null, null, true], "no map; the value is diagnostic");
  assert.equal(flip.checked.label, LABELS.unvalidated, "and labelled without the pinned evaluator");
});
test("P2 control 2 (R1): changing only value_C and active_layer_peak_C is not admitted by the same pin", async () => {
  const { LABELS } = await labels();
  const edited = await pinnedRaw((r) => { r.value_C = 100; r.active_layer_peak_C = 101; });
  assert.deepEqual([edited.pending.metric.value, edited.pending.distinct.find((d) => d.key === "active_layer_peak_C").value], [100, 101], "the control reaches the shown values");
  assert.notEqual(edited.checked.field_state, "verified", "statistics the pin did not check are not admitted");
  assert.equal(edited.checked.field_state, "mismatch");
  assert.deepEqual([edited.checked.grid, edited.checked.field_key, edited.checked.diagnostic], [null, null, true], "no map; the values are diagnostic");
  assert.equal(edited.checked.label, LABELS.unvalidated);
  // Every other number shown with a pinned result is bound too: the native maximum and the precision.
  for (const edit of [(r) => { r.native_all_block_max_C = 99; }, (r) => { r.precision_K = 0.1; }, (r) => { delete r.native_all_block_max_C; }]) {
    assert.equal((await pinnedRaw(edit)).checked.field_state, "mismatch", String(edit));
  }
});

// ── R2 ────────────────────────────────────────────────────────────────────────────────────────────────────────────
// C4: start(), stop(), then the pending response resolves. Before the fix one callback still published the API row.
test("C4 (R2): a live answer that arrives after stop() changes nothing and calls nobody", async () => {
  const door = await mod("source3d.mjs");
  let resolve, seenSignal = null;
  const pending = new Promise((r) => { resolve = r; });
  const calls = [];
  const feed = door.createDoorFeed({
    onChange: (state) => calls.push(state.layouts.length),
    fetchResults: (_cursor, { signal } = {}) => { seenSignal = signal ?? null; return pending; },
  });
  feed.start();
  feed.stop();
  resolve({ ok: true, layouts: [door.normalizeLayout(C1_ROW()).layout], refused: {}, next: "c9", env: "production", more: false });
  for (let i = 0; i < 5; i += 1) await new Promise((r) => setImmediate(r));
  assert.deepEqual(calls, [], "no callback after stop");
  assert.deepEqual([feed.state.layouts.length, feed.state.cursor, feed.state.connected, feed.state.polls], [0, null, null, 0], "the state is untouched");
  assert.ok(seenSignal && seenSignal.aborted, "the request in flight was aborted");
  // And the door ignores any callback for a source that is no longer selected (replay after live).
  assert.match(src("door.mjs"), /function onFeed\(state\) \{\n    if \(D\.source !== "api"\) return;/);
});

// C5: an older record never replaces a newer one (before the fix a supplied older queued record replaced a scored one).
test("C5 (R2): an older version never replaces a newer record; arrival order holds", async () => {
  const door = await mod("source3d.mjs");
  const scored = door.normalizeLayout({ ...C1_ROW(), id: "a", seq: 7 }).layout;
  const older = door.normalizeLayout({ ...C1_ROW(), id: "a", seq: 3, status: "queued", result: null }).layout;
  const unversioned = door.normalizeLayout({ ...C1_ROW(), id: "a", seq: undefined, status: "queued", result: null }).layout;
  const newer = door.normalizeLayout({ ...C1_ROW(), id: "a", seq: 9, status: "reproduced" }).layout;
  const b = door.normalizeLayout({ ...C1_ROW(), id: "b", seq: 1, status: "queued", result: null }).layout;
  assert.equal(door.mergeArrivals([scored], [older])[0].status, "evaluated");
  assert.equal(door.mergeArrivals([scored], [unversioned])[0].status, "evaluated");
  assert.equal(door.mergeArrivals([scored], [newer])[0].status, "reproduced");
  assert.deepEqual(door.mergeArrivals([scored, b], [newer]).map((l) => l.id), ["a", "b"], "a newer version keeps its place");
  assert.deepEqual(door.mergeArrivals([b], [scored]).map((l) => l.id), ["b", "a"], "order is first arrival, never the version");
});

// ── R3 ────────────────────────────────────────────────────────────────────────────────────────────────────────────
// C6: two different texel arrays under the same key, through the exact setField of render3d.mjs in an isolated VM with
// mock textures. Before the fix the texture kept the first array.
function extractSetField() {
  const s = src("render3d.mjs");
  const start = s.indexOf("  function setField(f");
  assert.ok(start > 0, "render3d.mjs defines setField");
  const end = s.indexOf("\n  }\n", start);
  return s.slice(start, end + 4);
}
test("C6 (R3): the renderer replaces the texture whenever the field's content differs, whatever the key says", async () => {
  const { fieldTexels } = await mod("model.mjs");
  // Mock textures and state for this renderer's setField (and, for a failing-first run, for the earlier two-texture one).
  const mk = () => ({ image: { data: new Uint8Array(64 * 64 * 4) }, needsUpdate: false });
  const tex = mk(), texA = mk(), texB = mk();
  const ctx = { F: { key: null, sum: null, front: "A", has: { A: 0, B: 0 }, fadeStart: null, from: 0, to: 0 }, tex, texA, texB,
    U: { hasA: { value: 0 }, hasB: { value: 0 }, t: { value: 0 } }, performance: { now: () => 0 }, kick: () => {}, TypeError, Number };
  const setField = vm.runInNewContext(`(() => { ${extractSetField()}; return setField; })()`, ctx);
  const a = fieldTexels(Float32Array.from(grid((k) => 50 + (k % 64))), "k");
  const b = fieldTexels(Float32Array.from(grid((k) => 120 - (k % 64))), "k");
  const digest = (bytes) => sha256(Buffer.from(bytes).toString("hex"));
  setField(a);
  setField(b);
  assert.notEqual(digest(a.texels), digest(b.texels), "two different fields under one key");
  assert.ok([tex, texA, texB].some((t) => digest(t.image.data) === digest(b.texels)), "the second field reached a texture");
  assert.equal(digest(tex.image.data), digest(b.texels), "the one texture now holds the second field");
});
test("R3: the door keys every field cache by the verified content identity, never by the score", async () => {
  const door = await mod("source3d.mjs");
  // Two results with the same id and the same score but different fields get different keys.
  const mk = (bump) => {
    const doc = structuredClone(FIXTURE);
    doc.layouts = [doc.layouts[0]];
    doc.layouts[0].result.grid64[100] += bump;
    return door.normalizeFeed(doc, { source: "fixture" }).layouts;
  };
  const pin = (layouts) => [{ layout_id: "ref-raw", geometry_sha256: sha256(door.geometryText(layouts[0])), field_sha256: sha256(layouts[0].result.grid_text),
    result_sha256: sha256(layouts[0].result.result_text), evaluator_identity: "x" }];
  const one = mk(0), two = mk(0.01);
  const k1 = (await door.verifyPinnedFields(one, { subtle: webcrypto.subtle, pins: pin(one) }))[0].result.field_key;
  const k2 = (await door.verifyPinnedFields(two, { subtle: webcrypto.subtle, pins: pin(two) }))[0].result.field_key;
  assert.equal(one[0].result.metric.value, two[0].result.metric.value, "the same score");
  assert.notEqual(k1, k2, "different fields, different identities");
  const d = src("door.mjs");
  assert.doesNotMatch(d, /fieldTexels\([^)]*metric\.value/, "no field key from a score");
  assert.match(d, /const key = `\$\{f\.key\}:\$\{f\.sum\}`;/, "the 2D field cache keys by content identity");
  assert.match(d, /\$\{r\.field_state\}\|\$\{r\.field_key\}\|/, "the arrival tile redraws when its field changes");
});

// ── R4 ────────────────────────────────────────────────────────────────────────────────────────────────────────────
test("R4: no frame blends two fields; a field shows only when its dies are at rest (hard cuts, PL-20, D17)", async () => {
  const { dieGliding, fieldVisible } = await mod("model.mjs");
  const die = { from: { cx: 10, cy: 10, rot: 0 }, to: { cx: 30, cy: 10, rot: 90 }, start: 1000 };
  const still = { from: { cx: 10, cy: 10, rot: 0 }, to: { cx: 10, cy: 10, rot: 0 }, start: 1000 };
  assert.equal(dieGliding(die, 1000, 900), true);
  assert.equal(dieGliding(die, 1899, 900), true);
  assert.equal(dieGliding(die, 1900, 900), false, "arrived");
  assert.equal(dieGliding(still, 1000, 900), false, "no move, no glide");
  assert.equal(fieldVisible({ hasField: true, gliding: true }), false, "hidden while the dies move");
  assert.equal(fieldVisible({ hasField: true, gliding: false }), true, "shown at once when they arrive");
  assert.equal(fieldVisible({ hasField: false, gliding: false }), false);
  const r3 = src("render3d.mjs");
  const fs = r3.slice(r3.indexOf("const FIELD_FS"), r3.indexOf("const fieldMaterial"));
  assert.match(fs, /uniform sampler2D map;/);
  assert.doesNotMatch(fs, /mapA|mapB|mix\(|uniform float t;/, "one field, never a blend");
  assert.doesNotMatch(r3, /FADE_MS|fadeStart/);
  assert.match(r3, /U\.has\.value = fieldVisible\(\{ hasField: F\.key !== null, gliding \}\) \? 1 : 0;/);
  assert.match(src("door.mjs"), /D\.current\?\.field && !fr\.active \?/, "the 2D view draws the field only with the dies at rest");
});

// ── R5 ────────────────────────────────────────────────────────────────────────────────────────────────────────────
test("R5: the renderer's listeners all go through one AbortController; dispose stops frames, orbit and listeners", () => {
  const r3 = src("render3d.mjs");
  assert.deepEqual(r3.match(/canvas\.addEventListener\(/g), ["canvas.addEventListener("], "only inside on()");
  assert.match(r3, /const on = \(type, fn, opts = \{\}\) => canvas\.addEventListener\(type, fn, \{ \.\.\.opts, signal: ac\.signal \}\);/);
  for (const ev of ["pointerdown", "pointermove", "pointerup", "pointercancel", "wheel", "keydown", "webglcontextlost"]) assert.match(r3, new RegExp(`on\\("${ev}"`), ev);
  const dispose = r3.slice(r3.indexOf("    dispose() {"), r3.indexOf("renderer.dispose();"));
  for (const step of ["ac.abort();", "autoOrbit = false;", "cancelAnimationFrame(S.raf)", "live3d.count -= 1;", "if (S.disposed) return null;"]) assert.ok(dispose.includes(step), step);
  assert.match(r3, /const kick = \(\) => \{ if \(!S\.raf && !S\.disposed && !S\.lost\)/, "a lost or disposed view schedules no frame");
});
test("R5: on context loss the owner disposes the view, falls back to 2D, and rebuilds 3D on restore", () => {
  for (const [file, holder] of [["door.mjs", "D"], ["package.js", "S"]]) {
    const s = src(file);
    const lost = s.slice(s.indexOf("function onContextLost() {"), s.indexOf("function onContextLost() {") + 600);
    assert.ok(lost.includes(`const old = ${holder}.v3;`) && lost.includes("old?.dispose();"), `${file}: disposes the old view`);
    assert.ok(lost.includes(`addEventListener("webglcontextrestored"`) && lost.includes("{ once: true }"), `${file}: rebuilds on restore`);
    assert.ok(lost.includes(`setRenderer("2d"`), `${file}: falls back to 2D`);
  }
  assert.doesNotMatch(src("door.mjs"), /onContextLost: \(\) => \{ D\.v3Failed = true/, "a lost context no longer disables 3D for good");
});

// P3 (root's focused review at 35323889, R5 follow-up): an explode step queued before a context loss ran after the view
// was released and threw reading setDoor of null. The exact onContextLost and setExplode of door.mjs, in an isolated VM
// with a scripted frame queue.
function doorFn(name) {
  const s = src("door.mjs");
  const start = s.indexOf(`  function ${name}(`);
  assert.ok(start > 0, `door.mjs defines ${name}`);
  return s.slice(start, s.indexOf("\n  }\n", start) + 4);
}
function explodeRig({ cancelWorks = true } = {}) {
  const frames = new Map();
  let nextId = 1;
  const calls = { setDoor: 0, fit: 0, dispose: 0 };
  const view = { setDoor: () => { calls.setDoor += 1; }, fit: () => { calls.fit += 1; }, dispose: () => { calls.dispose += 1; } };
  const D = { v3: view, current: { model: {}, field: null, L: {} }, explode: 0, explodeAnim: null, lost: false, want: "3d" };
  const ctx = {
    D, REDUCED: false, EXPLODE_MS: 800, Math, performance: { now: () => 0 },
    requestAnimationFrame: (fn) => { const id = nextId; nextId += 1; frames.set(id, fn); return id; },
    cancelAnimationFrame: (id) => { if (cancelWorks) frames.delete(id); },
    displayFor: () => [], notScoredText: () => "", renderDom: () => {}, setRenderer: () => {},
    $: () => ({ addEventListener: () => {} }),
  };
  const fns = vm.runInNewContext(`(() => { ${doorFn("onContextLost")}\n${doorFn("setExplode")}\n return { onContextLost, setExplode }; })()`, ctx);
  const runFrames = (now) => { const queued = [...frames.values()]; frames.clear(); for (const fn of queued) fn(now); };
  return { D, calls, frames, runFrames, ...fns };
}
test("P3 (R5): an explode step queued before a context loss never reaches the released view", () => {
  const a = explodeRig();
  a.setExplode(true);
  a.runFrames(100);
  assert.deepEqual([a.calls.setDoor, a.frames.size], [1, 1], "one step drawn, the next one queued");
  a.onContextLost();
  assert.equal(a.calls.dispose, 1);
  assert.deepEqual([a.frames.size, a.D.explodeAnim], [0, null], "the context loss cancels the queued step");
  assert.doesNotThrow(() => a.runFrames(200));
  // A step the browser already dispatched (too late to cancel) stops before it dereferences the view.
  const b = explodeRig({ cancelWorks: false });
  b.setExplode(true);
  b.onContextLost();
  assert.doesNotThrow(() => b.runFrames(100), "the queued step finds no view");
  assert.deepEqual([b.calls.setDoor, b.frames.size], [0, 0], "nothing reached the released view and no step follows");
});
