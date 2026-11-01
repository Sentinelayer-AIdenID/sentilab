// SentiLab Package view: the RenderModel, the one boundary between data and drawing. Pure: no DOM, no clock, no
// randomness, so node tests run it. The 3D renderer (render3d.mjs) and the 2D fallback both draw from what this module
// returns, and neither decides anything: every position, size, colour and label is fixed here.
//
// A RenderModel is deep-frozen and holds exactly one content kind:
//   model    the CPU-DRAM case's model stack (case-cpu-dram.mjs) with one agent-door layout's eight dies, halos and the
//            edge clearance band, all true size in mm (assembled coordinates);
//   result   one lab run's chiplets (scene.mjs layouts, lower-left x, y, w, h in mm) on the Package view's schematic
//            stack (scene.mjs STACK): heights are drawing constants, not measurements.
// Its original primitives are boxes (layers, dies, halos, chiplets), outlines (box edges only) and one field sheet
// (the chip layer's 64 x 64 temperature grid, set separately with fieldTexels()). View transforms (thin-layer
// thickening, the lifted cooling stack, explode) never touch the model: displayBoxes() returns a new Map.
//
// Coordinates: mm; origin at the interposer's lower-left corner on its bottom face; +x right, +y up in plan; +z up
// toward the cooler. Agent-door positions arrive in micrometres; umToMm() is the only unit conversion on the page.
import { DIES, DIE_IDS, dieById, RULES, STACK_LAYERS, LEVELS, INTERPOSER_MM, CASE_ID, trueZ } from "./case-cpu-dram.mjs";
import { STACK, HEAT_STOPS, heatColor } from "./scene.mjs";
import { canonical } from "../canonical.mjs";

export const MODEL_VERSION = "sentilab-model3d/1";
export const KINDS = Object.freeze(["model", "result"]);
// The exact banner of the model kind (the CAD/3D spec's content kinds table).
export const MODEL_BANNER = "Our model · the layers and blocks our thermal solver actually simulates, with its simplifications. Not the real package.";
export const umToMm = (um) => um / 1000;
// A layer thickness as text: micrometres below 1 mm, else millimetres (the stack table and the 3D layer callouts).
export const formatThickness = (mm) => (mm < 1 ? `${Math.round(mm * 1000)} µm` : `${mm} mm`);

export function deepFreeze(o) {
  if (o && typeof o === "object" && !Object.isFrozen(o)) { Object.freeze(o); for (const v of Object.values(o)) deepFreeze(v); }
  return o;
}
const r6 = (v) => Math.round(v * 1e6) / 1e6 + 0;   // + 0: never -0

// ── dies: centre + rotation -> footprint ─────────────────────────────────────────────────────────────────────────
// A quarter turn swaps the footprint (w <-> h); it is not a transform. Only the catalogue's rotations are drawn:
// CPU 0 or 90 degrees, DRAM 0. Anything else returns null (the adapter refuses such a layout before it gets here).
export function dieFootprint(dieId, rotDeg) {
  const d = dieById(dieId);
  if (!d || !RULES.rotations_deg[d.kind].includes(rotDeg)) return null;
  const turned = rotDeg === 90 || rotDeg === 270;
  return { w: turned ? d.h_mm : d.w_mm, h: turned ? d.w_mm : d.h_mm, turned };
}
// dies: [{ die, x_um, y_um, rot_deg }] (centres, micrometres) -> rects in mm, in the fixed die order C0..D3.
export function dieRects(dies) {
  const byId = new Map((dies ?? []).map((d) => [d.die, d]));
  const out = [];
  for (const id of DIE_IDS) {
    const d = byId.get(id);
    if (!d) return null;
    const fp = dieFootprint(id, d.rot_deg);
    if (!fp) return null;
    const cx = umToMm(d.x_um), cy = umToMm(d.y_um);
    const spec = dieById(id);
    out.push({
      id, tap_index: spec.tap_index, kind: spec.kind, power_w: spec.power_w, halo: spec.halo_mm, rot_deg: d.rot_deg, turned: fp.turned,
      cx, cy, w: fp.w, h: fp.h, x0: r6(cx - fp.w / 2), y0: r6(cy - fp.h / 2), x1: r6(cx + fp.w / 2), y1: r6(cy + fp.h / 2),
    });
  }
  return out;
}

// ── the colour scale: fixed endpoints, one ramp ──────────────────────────────────────────────────────────────────
// One fixed scale for every layout, so the same colour is the same temperature on every arrival and a new arrival
// never recolours an old one. 45 °C is the model's ambient (nothing in this steady state is cooler); 125 °C clears
// the 119.07 °C active-grid guard. Values outside clamp to the ends and are counted, never hidden. The ramp is the
// Package and Lab views' (scene.mjs HEAT_STOPS), sampled into a 1024-entry table; the map is drawn unlit and
// nearest-neighbour, one flat colour per grid cell, with nothing interpolated between cells.
export const SCALE = Object.freeze({ min: 45, max: 125, unit: "°C", stat: "active-layer temperature field (°C)", ticks: Object.freeze([45, 65, 85, 105, 125]) });

// A door temperature becomes text only through temps.mjs formatTemp(valueC, label), with its shared label (PL-2).
export const LUT_SIZE = 1024;
export const GRID = 64;
const hexRgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
let lut = null;
export function heatLut() {
  if (lut) return lut;
  const t = new Uint8Array(LUT_SIZE * 3);
  for (let i = 0; i < LUT_SIZE; i += 1) {
    const rgb = hexRgb(heatColor(SCALE.min + (i / (LUT_SIZE - 1)) * (SCALE.max - SCALE.min), SCALE));
    t.set(rgb, i * 3);
  }
  lut = t;
  return t;
}
// A temperature (°C) -> its LUT index, clamped. NaN never reaches here (the adapter refuses non-finite grids).
export function scaleIndex(c) {
  const f = (c - SCALE.min) / (SCALE.max - SCALE.min);
  return Math.max(0, Math.min(LUT_SIZE - 1, Math.round(f * (LUT_SIZE - 1))));
}
export function scaleColor(c) {
  const i = scaleIndex(c) * 3, t = heatLut();
  return `#${[t[i], t[i + 1], t[i + 2]].map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}
// Fraction along the colour bar (0 at SCALE.min, 1 at SCALE.max), clamped: the legend's tick and marker positions.
export const scaleFraction = (c) => Math.max(0, Math.min(1, (c - SCALE.min) / (SCALE.max - SCALE.min)));
export const SCALE_STOPS = HEAT_STOPS;

// grid: 4096 temperatures in °C, row-major, row 0 at y = 0 (the interposer's lower edge), column 0 at x = 0.
// Returns RGBA texels in the same order (texture row 0 = the bottom row) and how many cells the fixed scale clamped.
// No statistic is computed from the field here: the numbers the page shows are the scorer's (source3d.mjs).
export function fieldTexels(grid, key = null) {
  const n = GRID * GRID;
  if (!grid || grid.length !== n) return null;
  const t = heatLut(), out = new Uint8Array(n * 4);
  let above = 0, below = 0;
  for (let k = 0; k < n; k += 1) {
    const c = grid[k];
    if (c > SCALE.max) above += 1;
    if (c < SCALE.min) below += 1;
    const i = scaleIndex(c) * 3;
    out[k * 4] = t[i]; out[k * 4 + 1] = t[i + 1]; out[k * 4 + 2] = t[i + 2]; out[k * 4 + 3] = 255;
  }
  return { texels: out, above, below, key, sum: texelSum(out) };
}
// FNV-1a over the texel bytes: with the key (the field's verified sha256), the identity the renderer compares, so a
// different field can never keep the old texture even if a caller reused a key.
export function texelSum(bytes) {
  let h = 0x811c9dc5;
  for (let i = 0; i < bytes.length; i += 1) { h ^= bytes[i]; h = Math.imul(h, 0x01000193) >>> 0; }
  return h;
}
// Field changes are hard cuts (PL-20, D17), and a field shows only with the geometry it was computed for. While any die
// is still gliding to its new place (view-only motion), no field shows; when the dies arrive, the layout's own field
// shows at once. Nothing is ever blended between two fields.
// die: { from: { cx, cy, rot }, to: { cx, cy, rot }, start } (render3d.mjs keeps one per die).
export const dieGliding = (die, now, glideMs) => now - die.start < glideMs &&
  (die.from.cx !== die.to.cx || die.from.cy !== die.to.cy || die.from.rot !== die.to.rot);
export const fieldVisible = ({ hasField, gliding }) => Boolean(hasField) && !gliding;

// The centre of grid cell (row, col) in mm (row 0 at y = 0): one cell is 45/64 mm.
export const cellCentre = (row, col) => ({ x: r6((col + 0.5) * (INTERPOSER_MM / GRID)), y: r6((row + 0.5) * (INTERPOSER_MM / GRID)) });

// ── the model kind: the CPU-DRAM stack with one layout ───────────────────────────────────────────────────────────
const CITE = Object.freeze({
  layer: "sundai_tap/passive_interposer.py:144-149 (LCF layers 0-5, 45 mm square)",
  cooler: "sundai_tap/passive_interposer.py:154-156 and util/hotspot.config (t_spreader 1 mm, t_sink 6.9 mm)",
  die: "agent-door layout centre and rotation; footprint from sys_micro150_45mm.cfg (a quarter turn swaps it)",
  halo: "micro150-tap25d-fig5a.json dies[].halo_mm",
  edge: "tap_oracle.py:35 and :369-378: 0.5 mm from each edge to the die body plus its halo",
});

// layout: a normalized agent-door layout (source3d.mjs): { id, label, dies: [{ die, x_um, y_um, rot_deg }], ... }.
// Returns { model, error }.
export function buildRenderModel({ kind, layout = null, footprint = null, chiplets = null } = {}) {
  if (!KINDS.includes(kind)) return { model: null, error: "malformed: kind" };
  if (kind === "model" && (footprint || chiplets)) return { model: null, error: "mixed_content: one content kind per model" };
  if (kind === "result" && layout) return { model: null, error: "mixed_content: one content kind per model" };
  return kind === "model" ? modelKind(layout) : resultKind(footprint, chiplets);
}

function modelKind(layout) {
  const rects = dieRects(layout?.dies);
  if (!rects) return { model: null, error: "malformed: a layout needs the eight dies C0..D3 with catalogue rotations" };
  const z = trueZ();
  const S = INTERPOSER_MM;
  const boxes = [], outlines = [];
  for (const l of STACK_LAYERS) {
    const { z0, z1 } = z.get(l.level);
    // Every grid layer is the interposer's 45 mm square; the spreader and sink are wider, and their grid covers only
    // that central square: the central square is drawn as a box, the rest as the outline of the full part.
    boxes.push({ id: `layer:${l.level}`, type: "layer", level: l.level, x0: 0, y0: 0, x1: S, y1: S, z0, z1,
      basis: l.side_mm === S ? CITE.layer : `${CITE.cooler}; central ${S} mm grid extent of a ${l.side_mm} mm part` });
    if (l.side_mm !== S) {
      const m = (l.side_mm - S) / 2;
      outlines.push({ id: `outline:${l.level}`, type: "outline", level: l.level, x0: -m, y0: -m, x1: S + m, y1: S + m, z0, z1,
        basis: `${CITE.cooler}; full ${l.side_mm} mm part, outside the grid (unmeasured)` });
    }
  }
  const chip = z.get("chip");
  // Die boxes carry the TAP chiplet ids (tap-chiplet-<i>, i = the config's die index) and roles; `die` is the agent
  // door's name for the same die (C0..D3), the one the page shows.
  for (const r of rects) {
    boxes.push({ id: `tap-chiplet-${r.tap_index}`, type: "die", level: "chip", die: r.id, role: r.kind === "CPU" ? "compute" : "memory_dram_block",
      kind: r.kind, power_w: r.power_w, rot_deg: r.rot_deg,
      cx: r.cx, cy: r.cy, x0: r.x0, y0: r.y0, x1: r.x1, y1: r.y1, z0: chip.z0, z1: chip.z1, basis: CITE.die });
  }
  const halos = rects.map((r) => ({ id: `tap-chiplet-${r.tap_index}/halo`, type: "halo", level: "chip", die: r.id, halo_mm: r.halo,
    x0: r6(r.x0 - r.halo), y0: r6(r.y0 - r.halo), x1: r6(r.x1 + r.halo), y1: r6(r.y1 + r.halo), z0: chip.z0, z1: chip.z1, basis: CITE.halo }));
  const e = RULES.edge_clearance_mm;
  const model = {
    v: MODEL_VERSION, kind: "model", case_id: CASE_ID,
    status_text: MODEL_BANNER,
    layout: layout.label ?? null,
    units: "mm",
    frame: { interposer_mm: S, origin: "interposer lower-left corner, bottom face", z_up: "toward the cooler" },
    boxes, outlines, halos,
    overlays: { edge_band_mm: e, lattice_mm: RULES.lattice_mm, edge_basis: CITE.edge },
    levels: LEVELS,
    bounds: { x0: 0, y0: 0, x1: S, y1: S, z0: z.get("substrate").z0, z1: z.get("sink").z1 },
    notes: [
      "Spreader (90 mm) and sink (180 mm): their grid covers the central 45 mm, drawn as boxes; the rest is an outline, unmeasured.",
      "Halos are microbump rings around each die; the edge band is the 0.5 mm clearance a die keeps with its halo.",
    ],
    not_drawn: [{ id: "fill", type: "region", reason: "underfill, bump-mix and halo regions of layers 1-4 are not coloured separately" }],
  };
  model.geometry_key = geometryKey(model);
  return { model: deepFreeze(model), error: null };
}

// The geometry preimage: canonical JSON of { v, frame, instances }, one record per drawn box, outline and halo, sorted
// by id; duplicate ids are refused. No view state enters it, so a view transform can never change it.
export function geometryKey(model) {
  const parts = [...model.boxes, ...model.outlines, ...model.halos];
  const ids = parts.map((b) => b.id);
  if (new Set(ids).size !== ids.length) throw new Error("duplicate ids");
  const instances = parts.map((b) => ({ id: b.id, type: b.type, parent: null, variants: ["all"], drawn: true,
    box: { x0: b.x0, y0: b.y0, z0: b.z0, x1: b.x1, y1: b.y1, z1: b.z1 }, array: null }))
    .sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  return canonical({ v: "sentilab-geometry/1", frame: model.frame, instances });
}

// The result kind: a lab run's chiplets on the schematic stack. footprint: scene.mjs runFrame().footprint;
// chiplets: TrackAnimation frame chiplets ({ id, x, y, w, h, layer, kind, fill, alpha, grow, overlap, temp, state }).
function resultKind(footprint, chiplets) {
  if (!footprint || !Array.isArray(chiplets)) return { model: null, error: "malformed: a result needs a footprint and chiplets" };
  const S = STACK.substrate_mm, I = STACK.interposer_mm;
  // z = 0 at the interposer's bottom face here too: the substrate sits below it.
  const boxes = [
    { id: "layer:substrate", type: "layer", level: "substrate", ...footprint.substrate, z0: -S, z1: 0, basis: "schematic constant (scene.mjs STACK)" },
    { id: "layer:interposer", type: "layer", level: "interposer", ...footprint.interposer, z0: 0, z1: I, basis: "schematic constant (scene.mjs STACK)" },
  ];
  for (const c of chiplets) {
    const z0 = I + c.layer * STACK.die_mm;
    const h = (c.kind === "hbm" ? STACK.hbm_mm : STACK.die_mm) * (c.grow ?? 1);
    boxes.push({ id: `chiplet:${c.id}`, type: "chiplet", level: "chip", chiplet: c.id, kind: c.kind, fill: c.fill, alpha: c.alpha,
      overlap: Boolean(c.overlap), temp: c.temp ?? null, state: c.state ?? null,
      x0: c.x, y0: c.y, x1: c.x + c.w, y1: c.y + c.h, z0, z1: z0 + h, basis: "footprint from the verified evidence; height schematic" });
  }
  const lidTop = I + Math.max(STACK.die_mm, STACK.hbm_mm) + STACK.lid_clearance_mm + STACK.lid_mm;
  const sub = footprint.substrate;
  const outlines = [{ id: "outline:lid", type: "outline", level: "lid", x0: sub.x0 + 1.2, y0: sub.y0 + 1.2, x1: sub.x1 - 1.2, y1: sub.y1 - 1.2, z0: 0, z1: lidTop, basis: "schematic outline, cut away" }];
  const model = {
    v: MODEL_VERSION, kind: "result", status_text: "Result · schematic stack",
    units: "mm", frame: { origin: "interposer lower-left of the drawing frame", z_up: "toward the lid" },
    boxes, outlines, halos: [], overlays: null,
    levels: ["substrate", "interposer", "chip", "lid"],
    bounds: { x0: sub.x0, y0: sub.y0, x1: sub.x1, y1: sub.y1, z0: -S, z1: lidTop },
    notes: ["Schematic stack: substrate, interposer, heights and lid are drawing constants, not to scale. Footprints are from the evidence, in mm, to scale."],
    not_drawn: [],
  };
  model.geometry_key = geometryKey(model);
  return { model: deepFreeze(model), error: null };
}

// ── view transforms: a NEW Map of display boxes; the model is never written ─────────────────────────────────────
// thin   layers under 1 mm (substrate to TIM) drawn THIN_Z times thicker; the spreader and sink keep their thickness.
//        Every display z restacks from the bottom, so thickened layers never overlap. x and y never change.
// lift   0..1: the TIM, spreader and sink rise LIFT_MM above the chip layer so the dies and map stay in view.
// explode 0..1: every level k rises by t * EXPLODE_GAP_FRAC * span * k (spacing schematic).
// The underfill between the dies (the chip layer's slab) is drawn FILL_RECESS of the layer lower than the dies, so the
// dies read as blocks; in the model the dies and the fill are one 150 µm layer.
export const VIEW = Object.freeze({ THIN_Z: 10, THIN_BELOW_MM: 1, LIFT_MM: 8, EXPLODE_GAP_FRAC: 0.18, FILL_RECESS: 0.35, LIFTED: Object.freeze(["tim", "spreader", "sink"]) });

export function displayBoxes(model, { thin = true, lift = 1, explode = 0 } = {}) {
  const out = new Map();
  if (!model) return out;
  if (model.kind === "result") {
    for (const b of [...model.boxes, ...model.outlines]) out.set(b.id, { x0: b.x0, y0: b.y0, x1: b.x1, y1: b.y1, z0: b.z0, z1: b.z1, thickened: false });
    return out;
  }
  // Display z per level, restacked bottom to top from the true bottom.
  const levelZ = new Map();
  const span = Math.max(model.bounds.x1 - model.bounds.x0, model.bounds.y1 - model.bounds.y0);
  const order = model.levels;
  const tOf = (level) => STACK_LAYERS.find((l) => l.level === level).t_mm;
  const factor = (level) => (thin && tOf(level) < VIEW.THIN_BELOW_MM ? VIEW.THIN_Z : 1);
  // The interposer's bottom face stays at display z = 0: the (thickened) layers below it sit at negative z.
  let z = -order.slice(0, order.indexOf("interposer")).reduce((s, lv) => s + tOf(lv) * factor(lv), 0);
  order.forEach((level, k) => {
    const t = tOf(level) * factor(level);
    let dz = explode * VIEW.EXPLODE_GAP_FRAC * span * k;
    if (VIEW.LIFTED.includes(level)) dz += lift * VIEW.LIFT_MM;
    levelZ.set(level, { z0: r6(z + dz), z1: r6(z + t + dz), thickened: factor(level) !== 1 });
    z += t;
  });
  const chip = levelZ.get("chip");
  const fillTop = r6(chip.z0 + (chip.z1 - chip.z0) * (1 - VIEW.FILL_RECESS));
  for (const b of [...model.boxes, ...model.outlines, ...model.halos]) {
    const lz = levelZ.get(b.level);
    const z1 = b.id === "layer:chip" ? fillTop : lz.z1;
    out.set(b.id, { x0: b.x0, y0: b.y0, x1: b.x1, y1: b.y1, z0: lz.z0, z1, thickened: lz.thickened });
  }
  out.set("level:chip", { ...chip, fill_z1: fillTop });
  return out;
}
// The words the page shows for the view transforms in use (the chips under the canvas).
export function viewNotes({ thin = true, lift = 1, explode = 0 } = {}) {
  const notes = [];
  if (thin) notes.push(`thin layers thickened for visibility: under ${VIEW.THIN_BELOW_MM} mm drawn ×${VIEW.THIN_Z} in z; spreader and sink true`);
  if (lift > 0) notes.push("TIM, spreader and sink lifted for view");
  if (explode > 0) notes.push("exploded · spacing not to scale");
  return notes;
}

// The scene's frame for the camera fit: the drawn package (45 mm square) and its display height.
export function displayBounds(model, display) {
  let x0 = Infinity, y0 = Infinity, z0 = Infinity, x1 = -Infinity, y1 = -Infinity, z1 = -Infinity;
  for (const b of model.boxes) {
    const d = display.get(b.id);
    if (!d) continue;
    x0 = Math.min(x0, d.x0); y0 = Math.min(y0, d.y0); z0 = Math.min(z0, d.z0);
    x1 = Math.max(x1, d.x1); y1 = Math.max(y1, d.y1); z1 = Math.max(z1, d.z1);
  }
  return { x0, y0, z0, x1, y1, z1 };
}
