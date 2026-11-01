// SentiLab Package view: the CPU-DRAM case (TAP-2.5D Fig. 5(a), fixture micro150-45mm), pinned. Pure data, no DOM.
// Every number below is copied from a pinned repository source; each block names its source. Nothing is inferred.
//
//   dies, sizes, powers, connections   sundai_tap/configs/sys_micro150_45mm.cfg (sha256 de6e3edb...: [chiplets])
//   halos                              docs/sentilab/references/micro150-tap25d-fig5a.json dies[].halo_mm
//   legality                           the same cfg's [sentilab] section; sundai_hotspot/tap_oracle.py:35 (0.5 mm
//                                      margin, halo included) and :359-410 (margin, lattice, halo overlap, body gap);
//                                      rotations from the pinned catalogue: CPU 0 or 90 degrees, DRAM 0 only
//   stack                              sundai_tap/passive_interposer.py:144-149 (layers 0-5) and :154-156 (spreader
//                                      2x the interposer, sink 2x the spreader); sundai_tap/util/hotspot.config
//                                      (t_spreader 1 mm, t_sink 6.9 mm, k 400). Cross-checked against the public
//                                      reference case sentilab-fea-reference-case@af66bcfc case.json "stack".
//   references                         the two reference layout files above; the gate-zero statistics as recorded for
//                                      the raw layout; the paper's published points (micro150-tap25d-fig5a.json
//                                      paper_reported and validation_points).
//
// Coordinates (one convention for the whole page): millimetres; origin at the interposer's lower-left corner on the
// interposer's bottom face; +x right and +y up in plan; +z up toward the cooler. Layers below the interposer have
// negative z. Die positions are CENTRES (the agent door's x_um, y_um), as in the reference files.

export const CASE_ID = "micro150-45mm";
export const CASE_TITLE = "CPU-DRAM 2.5D package (TAP-2.5D Fig. 5(a) case)";
export const INTERPOSER_MM = 45;

// The fixed die order of the agent door's compact layout: C0..C3 are TAP dies 0-3 (CPUs), D0..D3 are dies 4-7 (DRAMs).
export const DIES = Object.freeze([
  { id: "C0", tap_index: 0, kind: "CPU", w_mm: 8.25, h_mm: 9, power_w: 150, halo_mm: 0.18 },
  { id: "C1", tap_index: 1, kind: "CPU", w_mm: 8.25, h_mm: 9, power_w: 150, halo_mm: 0.18 },
  { id: "C2", tap_index: 2, kind: "CPU", w_mm: 8.25, h_mm: 9, power_w: 150, halo_mm: 0.18 },
  { id: "C3", tap_index: 3, kind: "CPU", w_mm: 8.25, h_mm: 9, power_w: 150, halo_mm: 0.18 },
  { id: "D0", tap_index: 4, kind: "DRAM", w_mm: 8.75, h_mm: 8.75, power_w: 20, halo_mm: 0.135 },
  { id: "D1", tap_index: 5, kind: "DRAM", w_mm: 8.75, h_mm: 8.75, power_w: 20, halo_mm: 0.135 },
  { id: "D2", tap_index: 6, kind: "DRAM", w_mm: 8.75, h_mm: 8.75, power_w: 20, halo_mm: 0.135 },
  { id: "D3", tap_index: 7, kind: "DRAM", w_mm: 8.75, h_mm: 8.75, power_w: 20, halo_mm: 0.135 },
].map((d) => Object.freeze(d)));
export const DIE_IDS = Object.freeze(DIES.map((d) => d.id));
export const dieById = (id) => DIES.find((d) => d.id === id) ?? null;

export const RULES = Object.freeze({
  lattice_mm: 0.5,                 // die centres on multiples of 0.5 mm
  body_gap_mm: 0.1,                // die bodies at least 0.1 mm apart along some axis
  edge_clearance_mm: 0.5,          // from each interposer edge to the die body PLUS its halo
  halos_overlap: false,            // halo rectangles may touch, never overlap
  rotations_deg: Object.freeze({ CPU: Object.freeze([0, 90]), DRAM: Object.freeze([0]) }),
});

// The model stack, bottom to top: the six LCF grid layers TAP writes (all 45 x 45 mm), then the spreader and sink of
// HotSpot's package (90 and 180 mm square; their grid covers only the central 45 mm). k is the configured layer
// default in W/(m K); the C4, interposer, microbump and chip layers also hold mixed regions (bump mixes, TSV composite,
// halos), which this page does not colour. z is in mm, with z = 0 at the interposer's bottom face.
export const STACK_LAYERS = Object.freeze([
  { level: "substrate", grid_layer: 0, name: "Substrate", t_mm: 0.2, side_mm: 45, k: 0.3, material: "organic substrate" },
  { level: "c4", grid_layer: 1, name: "C4 bumps + underfill", t_mm: 0.07, side_mm: 45, k: 1.6, material: "underfill with C4 copper (mix)" },
  { level: "interposer", grid_layer: 2, name: "Silicon interposer", t_mm: 0.11, side_mm: 45, k: 100, material: "silicon with TSVs (composite)" },
  { level: "ubump", grid_layer: 3, name: "Microbumps + underfill", t_mm: 0.01, side_mm: 45, k: 1.6, material: "underfill with microbumps (mix)" },
  { level: "chip", grid_layer: 4, name: "Chip layer", t_mm: 0.15, side_mm: 45, k: 100, material: "silicon dies (the only powered layer) in underfill" },
  { level: "tim", grid_layer: 5, name: "TIM", t_mm: 0.02, side_mm: 45, k: 4, material: "thermal interface material" },
  { level: "spreader", grid_layer: 6, name: "Heat spreader", t_mm: 1.0, side_mm: 90, k: 400, material: "copper" },
  { level: "sink", grid_layer: 7, name: "Heat sink base", t_mm: 6.9, side_mm: 180, k: 400, material: "copper; fins lumped into the convection coefficient" },
].map((l) => Object.freeze(l)));
export const LEVELS = Object.freeze(STACK_LAYERS.map((l) => l.level));
// z = 0 at the interposer's bottom face: the substrate and C4 layers sit below it.
export const Z_ORIGIN_LEVEL = "interposer";
export function trueZ() {
  const below = STACK_LAYERS.slice(0, LEVELS.indexOf(Z_ORIGIN_LEVEL)).reduce((s, l) => s + l.t_mm, 0);
  const out = new Map();
  let z = -below;
  for (const l of STACK_LAYERS) { out.set(l.level, { z0: round9(z), z1: round9(z + l.t_mm) }); z += l.t_mm; }
  return out;
}
const round9 = (v) => Math.round(v * 1e9) / 1e9;

// The reference panel: published and recorded points, each with its statistic and unit. Never mixed into the live
// board and never paired with another layout's geometry (the snapped layout has NO temperature here).
export const REFERENCES = Object.freeze({
  raw: Object.freeze({
    title: "Raw reconstruction (reference-only)",
    note: "Reconstructed from the published figure; off the 0.5 mm lattice, so it is not a legal candidate. Gate zero, HotSpot 6.0, grid 64.",
    stats: Object.freeze([
      Object.freeze({ stat: "Max chiplet-centre mean (the board metric), bound to this layout", value: 115.935, unit: "°C" }),
      Object.freeze({ stat: "Native all-block maximum", value: 115.93, unit: "°C" }),
      Object.freeze({ stat: "Active-layer peak (the guard: strictly below this)", value: 119.07, unit: "°C" }),
      Object.freeze({ stat: "Wire proxy, weighted-mean Manhattan (raw)", value: 9.38487, unit: "mm" }),
    ]),
  }),
  snapped: Object.freeze({
    title: "Legal snapped reference",
    note: "Raw centres rounded to the 0.5 mm lattice, no repair. Its temperature is not evaluated.",
    stats: Object.freeze([
      Object.freeze({ stat: "Max chiplet-centre mean", value: null, unit: "°C", text: "not evaluated" }),
      Object.freeze({ stat: "Wire proxy, weighted-mean Manhattan (snapped)", value: 9.5, unit: "mm" }),
    ]),
  }),
  published: Object.freeze({
    title: "Published points (paper, Fig. 5)",
    note: "The paper's own statistic: the maximum over every block temperature HotSpot prints. Routed wirelength is the paper's router, not the proxy above.",
    stats: Object.freeze([
      Object.freeze({ stat: "Original placement (a): peak", value: 115.94, unit: "°C" }),
      Object.freeze({ stat: "Original placement (a): routed wirelength", value: 67686, unit: "mm" }),
      Object.freeze({ stat: "TAP-2.5D placement (c): peak", value: 94.89, unit: "°C" }),
      Object.freeze({ stat: "TAP-2.5D placement (c): routed wirelength", value: 216064, unit: "mm" }),
    ]),
  }),
});
// The active-layer guard: a layout's active-layer peak must be strictly below this (the raw layout's own peak).
export const ACTIVE_LAYER_GUARD_C = 119.07;

// The evaluator identity of the gate-zero build: HotSpot 6.0 at upstream a7a3286e, its pinned binary, the configuration
// files both raw references share, grid 64 and the pinned centre mapping, sealed by build_sha256. Exactly the "id" of the
// one build in contracts/open-proposal-v1/builds.json (#85); temperature-label.mjs lists it on REPRODUCTION_TESTED, so
// the gate-zero statistics and the pinned raw reference's field read "simulated · reproduction-tested build". It names a
// build that reproduced two published reference temperatures in simulation, nothing about hardware. Temperatures are
// labelled by labelFor() of a VERIFIED identity only: this one is reviewed page code, bound to the raw reference's field
// by its pin (FIELD_PINS); a feed result never borrows it.
export const GATE_ZERO_EVALUATOR = "HotSpot-6.0:a7a3286e368867c26381e0a23e36b3e273bdeda9:binary_sha256:751b357f6b5af395a4447d6e3bfeef3a75eb447091798365a3db4f0e00618cc6:config_sha256:2a51fb6cf2b149b29d154371450f5924070fa0d5ab7ad170b7185b929ff9007b:grid:64x64:build_sha256:05a9d9cb9ba06a67123c1b4c9d3da14820429221e23b4882abc82cf49c1a0e74";

// The admitted field associations: the only fields this page draws. Each binds a bundled layout's exact geometry to the
// exact bytes of its field, to the rest of its result record and to the evaluator that produced it, reviewed here in page
// code (never in the data). The page recomputes all three digests with WebCrypto before drawing anything under a pin;
// without WebCrypto it draws no field (D14).
//   geometry_sha256  sha256 of canonical({ dies: [{ die, x_um, y_um, rot_deg } in the order C0..D3] }) (canonical.mjs)
//   field_sha256     sha256 of the UTF-8 text JSON.stringify(result.grid64), exactly as the fixture holds it (row0 top)
//   result_sha256    sha256 of source3d.mjs resultText(result): the rest of the result record in canonical form, so the
//                    field's orientation (row0) and every statistic shown with it (value_C, precision_K,
//                    native_all_block_max_C, active_layer_peak_C, the claim label) are bound to the pin, not just its cells
// The raw reference's field is layer 4 of the gate-zero output sample.grid.steady (sha256 499690b8...) for that layout,
// kelvin minus 273.15 at the file's 0.01 K; every cell was matched independently in review.
export const FIELD_PINS = Object.freeze([
  Object.freeze({
    layout_id: "ref-raw",
    geometry_sha256: "3d0f10d20d6876bff1dc46522261b544f893b75c19af2e6e90017eced6270399",
    field_sha256: "554ba34a2a2dce2de0c8f16d6d41c82cc297a26664d812ab5a617195649fee3e",
    result_sha256: "25331e9f0b093f96fe1ad617d7fdaf971c89736880901cb47a4c41bc066accb9",
    evaluator_identity: GATE_ZERO_EVALUATOR,
  }),
]);
