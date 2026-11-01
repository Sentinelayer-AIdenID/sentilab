// node --test web/test/package3d-model.test.mjs
// The Package view's RenderModel (web/public/sentilab/package/model.mjs) and the pinned CPU-DRAM case: die-to-scene
// coordinates (centres, rotation, units), the true and displayed stack, the view transforms, and the fixed colour scale.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { buildRenderModel, geometryKey, displayBoxes, dieFootprint, dieRects, umToMm, formatTemp, formatThickness, fieldTexels, scaleIndex,
  scaleColor, scaleFraction, heatLut, SCALE, LUT_SIZE, VIEW, MODEL_VERSION, cellCentre, viewNotes } from "../public/sentilab/package/model.mjs";
import { DIES, DIE_IDS, STACK_LAYERS, LEVELS, RULES, INTERPOSER_MM, trueZ, REFERENCES, ACTIVE_LAYER_GUARD_C } from "../public/sentilab/package/case-cpu-dram.mjs";
import { heatColor, HEAT_STOPS } from "../public/sentilab/package/scene.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const repo = join(here, "..", "..");
const json = (rel) => JSON.parse(readFileSync(join(repo, rel), "utf8"));
const close = (a, b, eps = 1e-9) => assert.ok(Math.abs(a - b) <= eps, `${a} vs ${b}`);
const layout = (dies, extra = {}) => ({ id: "t", label: "example · 0000", dies, ...extra });
const centred = (pairs, rot = () => 0) => DIE_IDS.map((die, i) => ({ die, x_um: pairs[i][0] * 1000, y_um: pairs[i][1] * 1000, rot_deg: rot(i) }));
const SNAP = [[18, 17.5], [27, 17.5], [27, 27.5], [18, 27.5], [8.5, 17.5], [36.5, 17.5], [36.5, 27.5], [8.5, 27.5]];

// ── the case, against the repository's pinned sources ──
test("the case's dies, powers, footprints and halos are the pinned config's and the reference file's", () => {
  const cfg = readFileSync(join(repo, "sundai_tap/configs/sys_micro150_45mm.cfg"), "utf8");
  const row = (key) => cfg.match(new RegExp(`^${key}\\s*=\\s*(.+)$`, "m"))[1].split(",").map((v) => Number(v.trim()));
  assert.deepEqual(DIES.map((d) => d.w_mm), row("widths"));
  assert.deepEqual(DIES.map((d) => d.h_mm), row("heights"));
  assert.deepEqual(DIES.map((d) => d.power_w), row("powers"));
  assert.equal(Number(cfg.match(/^intp_size\s*=\s*(\d+)/m)[1]), INTERPOSER_MM);
  assert.equal(Number(cfg.match(/^center_lattice_mm\s*=\s*([\d.]+)/m)[1]), RULES.lattice_mm);
  assert.equal(Number(cfg.match(/^min_die_gap_mm\s*=\s*([\d.]+)/m)[1]), RULES.body_gap_mm);
  const ref = json("docs/sentilab/references/micro150-tap25d-fig5a.json");
  assert.deepEqual(DIES.map((d) => d.halo_mm), ref.dies.map((d) => d.halo_mm));
  assert.deepEqual(DIE_IDS, ["C0", "C1", "C2", "C3", "D0", "D1", "D2", "D3"], "the agent door's fixed order");
  assert.deepEqual(DIES.map((d) => d.kind), ["CPU", "CPU", "CPU", "CPU", "DRAM", "DRAM", "DRAM", "DRAM"]);
  assert.deepEqual(RULES.rotations_deg, { CPU: [0, 90], DRAM: [0] }, "the catalogue: CPU 0 or 90, DRAM 0 only");
  // The published and recorded reference points, one statistic each.
  assert.equal(ACTIVE_LAYER_GUARD_C, 119.07);
  assert.deepEqual(REFERENCES.raw.stats.map((s) => s.value), [115.935, 115.93, 119.07, 9.38487]);
  assert.deepEqual(REFERENCES.snapped.stats.map((s) => s.value), [null, 9.5], "the snapped layout has no temperature");
  assert.equal(ref.paper_reported.original.peak_temperature_c, REFERENCES.published.stats[0].value);
  assert.equal(ref.validation_points.find((p) => p.panel === "c").peak_temperature_c, REFERENCES.published.stats[2].value);
});

test("the model stack is TAP's generated stack and matches the public reference case's z ranges", () => {
  // sundai_tap/passive_interposer.py writes the six layers' thicknesses in metres; hotspot.config the spreader and sink.
  const py = readFileSync(join(repo, "sundai_tap/passive_interposer.py"), "utf8");
  const lcf = [...py.matchAll(/# Layer (\d): [^\\]*\\n\d\\nY\\n[YN]\\n[^\\]+\\n[^\\]+\\n([^\\]+)\\n/g)].map((m) => [Number(m[1]), Number(m[2])]);
  assert.equal(lcf.length, 6, "six LCF layers");
  for (const [i, t] of lcf) close(STACK_LAYERS[i].t_mm, t * 1000, 1e-12);
  const hs = readFileSync(join(repo, "sundai_tap/util/hotspot.config"), "utf8");
  close(STACK_LAYERS[6].t_mm, Number(hs.match(/-t_spreader\s+([\d.e-]+)/)[1]) * 1000, 1e-12);
  close(STACK_LAYERS[7].t_mm, Number(hs.match(/-t_sink\s+([\d.e-]+)/)[1]) * 1000, 1e-12);
  assert.deepEqual(STACK_LAYERS.map((l) => l.side_mm), [45, 45, 45, 45, 45, 45, 90, 180], "spreader 2x, sink 4x the interposer");
  assert.deepEqual(LEVELS, ["substrate", "c4", "interposer", "ubump", "chip", "tim", "spreader", "sink"]);
  // sentilab-fea-reference-case@af66bcfc case.json stack z (substrate bottom = 0, metres), shifted so z = 0 is the
  // interposer's bottom face: the same eight ranges.
  const fea = [[0, 0.0002], [0.0002, 0.00027], [0.00027, 0.00038], [0.00038, 0.00039], [0.00039, 0.00054], [0.00054, 0.00056], [0.00056, 0.00156], [0.00156, 0.00846]];
  const z = trueZ();
  LEVELS.forEach((lv, i) => { close(z.get(lv).z0, (fea[i][0] - 0.00027) * 1000, 1e-9); close(z.get(lv).z1, (fea[i][1] - 0.00027) * 1000, 1e-9); });
  assert.equal(z.get("interposer").z0, 0, "z = 0 at the interposer's bottom face");
});

// ── die to scene: centres, rotation, units ──
test("µm to mm happens once, and a die centre maps to its footprint's lower-left and upper-right", () => {
  assert.equal(umToMm(17500), 17.5);
  const r = dieRects(centred(SNAP));
  assert.deepEqual(r.map((d) => d.id), DIE_IDS);
  // C0 centred at (18, 17.5) mm, 8.25 x 9 mm: lower-left (13.875, 13), upper-right (22.125, 22).
  assert.deepEqual([r[0].cx, r[0].cy, r[0].x0, r[0].y0, r[0].x1, r[0].y1], [18, 17.5, 13.875, 13, 22.125, 22]);
  // D0 centred at (8.5, 17.5), 8.75 x 8.75.
  assert.deepEqual([r[4].x0, r[4].y0, r[4].x1, r[4].y1], [4.125, 13.125, 12.875, 21.875]);
  // The raw reference's centres give the reference file's own lower-left corners, to within half the difference between
  // the decoded outline (lower_left_mm's source, sizes such as 8.2497 x 9.0008) and the catalogue footprint drawn here.
  const ref = json("docs/sentilab/references/micro150-tap25d-fig5a.json");
  const raw = dieRects(ref.raw.centers_mm.map(([x, y], i) => ({ die: DIE_IDS[i], x_um: Math.round(x * 10000) / 10, y_um: Math.round(y * 10000) / 10, rot_deg: 0 })));
  raw.forEach((d, i) => {
    const tol = (k) => Math.abs(ref.raw.footprints_mm[i][k] - ref.raw.decoded_size_mm[i][k]) / 2 + 1e-4;
    close(d.x0, ref.raw.lower_left_mm[i][0], tol(0)); close(d.y0, ref.raw.lower_left_mm[i][1], tol(1));
  });
});

test("a quarter turn swaps the footprint about the same centre; only catalogue rotations are drawn", () => {
  assert.deepEqual(dieFootprint("C0", 0), { w: 8.25, h: 9, turned: false });
  assert.deepEqual(dieFootprint("C1", 90), { w: 9, h: 8.25, turned: true });
  assert.deepEqual(dieFootprint("D2", 0), { w: 8.75, h: 8.75, turned: false });
  for (const [die, rot] of [["D0", 90], ["C0", 180], ["C0", 270], ["C0", 45], ["C0", -90], ["X9", 0]]) assert.equal(dieFootprint(die, rot), null, `${die} ${rot}`);
  const turned = dieRects(centred(SNAP, (i) => (i < 4 ? 90 : 0)));
  assert.deepEqual([turned[0].x0, turned[0].y0, turned[0].x1, turned[0].y1], [13.5, 13.375, 22.5, 21.625], "9 x 8.25 about (18, 17.5)");
  assert.equal(dieRects(centred(SNAP, (i) => (i === 5 ? 90 : 0))), null, "a turned DRAM is not drawn");
  assert.equal(dieRects(centred(SNAP).slice(0, 7)), null, "seven dies are not a layout");
});

// ── the RenderModel ──
test("buildRenderModel: one content kind, deep-frozen, every die and layer as a box in mm", () => {
  const { model, error } = buildRenderModel({ kind: "model", layout: layout(centred(SNAP)) });
  assert.equal(error, null);
  assert.equal(model.v, MODEL_VERSION);
  assert.equal(model.units, "mm");
  assert.ok(Object.isFrozen(model) && Object.isFrozen(model.boxes) && Object.isFrozen(model.boxes[0]), "deep-frozen");
  assert.throws(() => { "use strict"; model.boxes[0].x0 = 5; }, TypeError);
  assert.deepEqual(model.boxes.filter((b) => b.type === "layer").map((b) => b.level), LEVELS);
  for (const b of model.boxes.filter((b) => b.type === "layer")) assert.deepEqual([b.x0, b.y0, b.x1, b.y1], [0, 0, 45, 45], "the grid's 45 mm square");
  assert.deepEqual(model.outlines.map((o) => [o.level, o.x1 - o.x0]), [["spreader", 90], ["sink", 180]], "the full parts, outlined, centred on the interposer");
  const dies = model.boxes.filter((b) => b.type === "die");
  assert.deepEqual(dies.map((d) => d.die), DIE_IDS);
  const chip = trueZ().get("chip");
  for (const d of dies) assert.deepEqual([d.z0, d.z1], [chip.z0, chip.z1], "dies fill the chip layer");
  assert.deepEqual(model.halos.map((h) => +(h.x1 - h.x0 - (dies.find((d) => d.die === h.die).x1 - dies.find((d) => d.die === h.die).x0)).toFixed(6)), [0.36, 0.36, 0.36, 0.36, 0.27, 0.27, 0.27, 0.27], "halo rings 0.18 and 0.135 mm wide");
  assert.equal(buildRenderModel({ kind: "model", layout: layout(centred(SNAP)), chiplets: [] }).error.startsWith("mixed_content"), true);
  assert.equal(buildRenderModel({ kind: "result", layout: layout(centred(SNAP)), footprint: {}, chiplets: [] }).error.startsWith("mixed_content"), true);
  assert.equal(buildRenderModel({ kind: "anatomy" }).error, "malformed: kind");
  assert.match(buildRenderModel({ kind: "model", layout: layout(centred(SNAP, () => 180)) }).error, /catalogue rotations/);
});

test("the result kind (lab runs): chiplets on the schematic stack, colours as given, lid outlined", () => {
  const footprint = { substrate: { x0: -5.5, y0: -5.5, x1: 25.5, y1: 25.5 }, interposer: { x0: -1.5, y0: -1.5, x1: 21.5, y1: 21.5 } };
  const { model } = buildRenderModel({ kind: "result", footprint, chiplets: [{ id: "CPU0", x: 0, y: 0, w: 10, h: 8, layer: 0, kind: "die", fill: "#ec994f", alpha: 1, overlap: false, temp: 90.1, state: "valid" }] });
  const c = model.boxes.find((b) => b.type === "chiplet");
  assert.deepEqual([c.x0, c.y0, c.x1, c.y1, c.z0, c.z1, c.fill], [0, 0, 10, 8, 1, 3, "#ec994f"]);
  assert.equal(model.outlines[0].id, "outline:lid");
  assert.match(model.notes[0], /^Schematic stack/);
});

test("ids, roles and the geometry preimage: TAP chiplet ids, canonical and sorted, blind to view state", () => {
  const { model } = buildRenderModel({ kind: "model", layout: layout(centred(SNAP)) });
  const dies = model.boxes.filter((b) => b.type === "die");
  assert.deepEqual(dies.map((d) => [d.id, d.die, d.role]), DIE_IDS.map((die, i) => [`tap-chiplet-${i}`, die, i < 4 ? "compute" : "memory_dram_block"]));
  const pre = JSON.parse(model.geometry_key);
  assert.equal(pre.v, "sentilab-geometry/1");
  const ids = pre.instances.map((x) => x.id);
  assert.deepEqual(ids, [...ids].sort(), "sorted by id");
  assert.equal(new Set(ids).size, ids.length);
  assert.equal(ids.length, model.boxes.length + model.outlines.length + model.halos.length);
  assert.deepEqual(Object.keys(pre.instances[0]).sort(), ["array", "box", "drawn", "id", "parent", "type", "variants"]);
  // The same layout gives the same key whatever order its dies arrive in; a moved die changes it; view state never does.
  const shuffled = buildRenderModel({ kind: "model", layout: layout([...centred(SNAP)].reverse()) }).model;
  assert.equal(shuffled.geometry_key, model.geometry_key);
  const moved = buildRenderModel({ kind: "model", layout: layout(centred(SNAP.map(([x, y], i) => (i === 0 ? [x, y - 0.5] : [x, y])))) }).model;
  assert.notEqual(moved.geometry_key, model.geometry_key);
  displayBoxes(model, { explode: 1 });
  assert.equal(geometryKey(model), model.geometry_key);
  assert.throws(() => geometryKey({ boxes: [{ id: "a" }, { id: "a" }], outlines: [], halos: [], frame: {} }), /duplicate ids/);
});

// ── view transforms ──
test("displayBoxes: thin layers x10 restacked from the interposer's bottom face, cooling stack lifted, underfill recessed; the model is untouched", () => {
  const { model } = buildRenderModel({ kind: "model", layout: layout(centred(SNAP)) });
  const before = JSON.stringify(model);
  const d = displayBoxes(model);
  assert.equal(JSON.stringify(model), before, "the model never changes");
  const z = (id) => [d.get(id).z0, d.get(id).z1];
  assert.deepEqual(z("layer:substrate"), [-2.7, -0.7]);
  assert.deepEqual(z("layer:c4"), [-0.7, 0]);
  assert.deepEqual(z("layer:interposer"), [0, 1.1]);
  assert.deepEqual(z("layer:ubump"), [1.1, 1.2]);
  assert.deepEqual(z("tap-chiplet-0"), [1.2, 2.7], "dies: the chip layer, x10");
  assert.deepEqual(z("layer:chip"), [1.2, +(1.2 + 1.5 * (1 - VIEW.FILL_RECESS)).toFixed(6)], "the underfill drawn lower than the dies");
  assert.deepEqual(z("layer:tim"), [2.7 + VIEW.LIFT_MM, 2.9 + VIEW.LIFT_MM]);
  assert.deepEqual(z("layer:spreader"), [2.9 + VIEW.LIFT_MM, 3.9 + VIEW.LIFT_MM], "1 mm: true thickness");
  assert.deepEqual(z("layer:sink"), [3.9 + VIEW.LIFT_MM, +(10.8 + VIEW.LIFT_MM).toFixed(6)], "6.9 mm: true thickness");
  for (const id of ["tap-chiplet-0", "layer:sink"]) assert.deepEqual([d.get(id).x0, d.get(id).y0, d.get(id).x1, d.get(id).y1], (() => { const b = model.boxes.find((x) => x.id === id); return [b.x0, b.y0, b.x1, b.y1]; })(), "x and y never change");
  // True thickness: every layer as the model has it.
  const t = displayBoxes(model, { thin: false, lift: 0 });
  for (const l of STACK_LAYERS) close(t.get(`layer:${l.level}`).z1 - t.get(`layer:${l.level}`).z0, l.t_mm * (l.level === "chip" ? 1 - VIEW.FILL_RECESS : 1), 1e-6);
  // Explode: level k rises by 0.18 x span x k.
  const e = displayBoxes(model, { explode: 1 });
  close(e.get("layer:c4").z0 - d.get("layer:c4").z0, VIEW.EXPLODE_GAP_FRAC * 45, 1e-6);
  close(e.get("layer:sink").z0 - d.get("layer:sink").z0, VIEW.EXPLODE_GAP_FRAC * 45 * 7, 1e-6);
  assert.deepEqual(viewNotes({ explode: 1 }).at(-1), "exploded · spacing not to scale");
});

// ── the colour scale: fixed endpoints ──
test("the colour scale has fixed endpoints (45 and 125 °C), the site's ramp, and clamps outside", () => {
  assert.deepEqual([SCALE.min, SCALE.max, SCALE.unit], [45, 125, "°C"]);
  assert.equal(SCALE.stat, "active-layer temperature field (°C)");
  assert.equal(scaleIndex(45), 0);
  assert.equal(scaleIndex(125), LUT_SIZE - 1);
  assert.equal(scaleIndex(20), 0, "below clamps");
  assert.equal(scaleIndex(400), LUT_SIZE - 1, "above clamps");
  assert.equal(scaleColor(45), HEAT_STOPS[0]);
  assert.equal(scaleColor(125), HEAT_STOPS.at(-1));
  for (const c of [50, 62.65, 85, 94.89, 115.935, 119.07]) assert.equal(scaleColor(c), heatColor(SCALE.min + (scaleIndex(c) / (LUT_SIZE - 1)) * (SCALE.max - SCALE.min), SCALE), `${c}`);
  assert.equal(heatLut().length, LUT_SIZE * 3);
  assert.equal(scaleFraction(85), 0.5);
  assert.equal(scaleFraction(ACTIVE_LAYER_GUARD_C), (119.07 - 45) / 80);
  // The same temperature is the same colour whatever else is in the field: the endpoints never come from the data.
  const cool = new Float32Array(4096).fill(60), hot = new Float32Array(4096).fill(200);
  hot[0] = 60;
  const a = fieldTexels(cool), b = fieldTexels(hot);
  assert.deepEqual([...a.texels.subarray(0, 4)], [...b.texels.subarray(0, 4)]);
  assert.deepEqual([b.above, b.below, a.above, a.below], [4095, 0, 0, 0], "clamped cells are counted");
});

test("fieldTexels keeps the grid's order: texel k is cell k (row 0 = y 0, column 0 = x 0)", () => {
  const g = new Float32Array(4096).fill(45);
  g[0] = 125; g[63] = 85; g[64 * 63] = 105;
  const { texels } = fieldTexels(g);
  const rgb = (k) => `#${[...texels.subarray(k * 4, k * 4 + 3)].map((v) => v.toString(16).padStart(2, "0")).join("")}`;
  assert.equal(rgb(0), scaleColor(125));
  assert.equal(rgb(63), scaleColor(85));
  assert.equal(rgb(64 * 63), scaleColor(105));
  assert.equal(rgb(1), scaleColor(45));
  assert.equal(fieldTexels(new Float32Array(10)), null);
  assert.deepEqual(cellCentre(0, 0), { x: 0.351563, y: 0.351563 });
  assert.deepEqual(cellCentre(63, 63), { x: 44.648438, y: 44.648438 });
});

test("formatTemp: one way to text, rounded half up to 0.01 °C for display only", () => {
  assert.equal(formatTemp(115.935), "115.94 °C");
  assert.equal(formatTemp(119.065), "119.07 °C");
  assert.equal(formatTemp(94.885), "94.89 °C");
  assert.equal(formatTemp(45), "45.00 °C");
  assert.equal(formatTemp(NaN), "-");
  assert.equal(formatTemp(undefined), "-");
  assert.equal(formatThickness(0.01), "10 µm");
  assert.equal(formatThickness(6.9), "6.9 mm");
});
