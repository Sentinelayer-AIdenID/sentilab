# Package 3D: consolidated pseudocode

**Companion to SPEC.md v0.2 (2026-10-31). For review; nothing here is implemented.** It consolidates lane 3's
module pseudocode (L3:PSEUDOCODE.md at `253ee4f7`) with the three content kinds, the quantity and id rules, and the
result binding from SPEC.md. Every integration point cites origin/main at `d25046256b4a712b529977f31e10b7e32248a9c0`
as `path:line`. Where this file and lane 3 differ, SPEC.md §6.8 says why.

House style, taken from the Package view: plain ES modules with named exports; pure functions over plain objects;
`Object.freeze` constants; results shaped `{ value, error }` or `{ ok: true, ... } | { ok: false, error }`; refusals
listed, never drawn; DOM text through `textContent`; no inline style (web/public/sentilab/package/package.js:21-35 and
render.mjs:1-9 show the pattern; this page writes per CSSOM property, never `cssText`).

## 0. Files, import rules and frozen operation names

```
web/public/sentilab/package3d/
  index.html          shell: notice slot, banners, figure#p3d-figure (the export boundary: canvas or SVG fallback, DOM
                      chips, legend, source line: SPEC.md §6.5), part tree, detail panel
  package3d.js        page controller (the only module that touches the DOM broadly)
  package3d.css
  quantity.mjs        PURE  quantities, bases, unit conversion (the ONLY lengths conversion in the page)
  ids.mjs             PURE  id grammar, stability checks
  anatomy.mjs         PURE  readAnatomy(), readAssembly()
  modelstack.mjs      PURE  readModelStack(), readLayouts(), fixtureFor(), standsForIndex()
  results.mjs         PURE  resultView(), STATISTICS, receiptCompleteness(), matchReference()
  model.mjs           PURE  buildRenderModel() -> one frozen RenderModel of one content kind
  view.mjs            PURE  displayBoxes(): readable thickening + explode offsets (view transform only)
  explode.mjs         PURE  explodeOffsets(); plus the tiny animation driver (rAF only there)
  section.mjs         PURE  sectionAt() -> rectangles for 3D caps AND the SVG fallback
  interconnect.mjs    PURE  instanceBudget(), interconnectArrays() (sampled), highlightSet()
  pick.mjs            PURE  pick() ray-box, cellAt()
  flows.mjs           PURE  overlayFor(model, { kind }) -> paths + legend + qualifier
  temps.mjs           PURE  formatTemp(), tempNode(), TEMP_PATTERN, findBareTemperatures()
  field.mjs           PURE* fieldRefs(), checkFieldArtifact() (*hashing via WebCrypto), fieldScale(), colourLut(), fieldTexels()
  stream.mjs          createFieldFeed(), solveStatus(), createDoorbell()   (fetch injectable; node-testable)
  twin.mjs            PURE  twinOf(), twinMarkdown()
  labels.mjs          DOM   createLabelLayer() (per-property CSSOM)
  fallback2d.mjs      DOM   renderSectionSvg()
  mat4.mjs camera.mjs PURE  matrices, orbit reducers
  gl.mjs shaders.mjs render3d.mjs   WebGL2 only here
  pins.mjs            GENERATED: sha256 of each data file (written by scripts/package3d.mjs data)
  data/anatomy.json  data/assembly-typ-1c4m.json  data/model-stack.json  data/layouts.json
web/public/agents/package3d/
  index.md index.json anatomy.json anatomy.md model-<fixture>.json model-<fixture>.md results.md replays/*.json [anatomy.glb]
docs/sentilab/package3d/            reviewed sources: anatomy-overlay.json, assembly-typ-1c4m.src.json, model-stack.src.json
scripts/package3d.mjs               subcommands: data | twin | export3d | check
scripts/lib/glb.mjs                 deterministic GLB writer (Node only)
scripts/package3d-browser-check.mjs Playwright checks against the local Worker
sundai_hotspot/test_package3d_model_stack.py   Python check of the model manifest (runs TAP's floorplan writer only)
web/test/package3d-*.test.mjs       node tests (CI runs web/test/*.test.mjs: .github/workflows/ci.yml:30)
```

Import rules (static test, AC-02):

- PURE modules import only PURE modules of this folder and: `../package/scene.mjs`, `../package/playhead.mjs`,
  `../evidence-projection.mjs`, `../lab-model.mjs`, `../view-core.mjs`, `../canonical.mjs`, `../runs-list.mjs`,
  `../../temperature-label.mjs`. No DOM, no clock, no randomness, no WebGL.
- Only `render3d.mjs` and `gl.mjs` call WebGL. Only `temps.mjs` turns a temperature into text. No `toFixed(` on a
  temperature and no `°C` outside `temps.mjs`.
- `package3d.js` gets verified data only through `../package/source.mjs` (source.mjs:1-12) and never computes
  LIVE or STALE itself (source.mjs:172-182).

Frozen operation names (W0.1): `geometryPreimage`, `readAnatomy`, `readAssembly`, `readModelStack`, `readLayouts`,
`fixtureFor`, `inputsVerification`, `standsForIndex`, `resultView`, `signedInputsOf`, `receiptCompleteness`,
`matchReference`, `buildRenderModel`, `displayBoxes`, `explodeOffsets`, `sectionAt`, `interconnectArrays`,
`instanceBudget`, `pick`, `overlayFor`, `formatTemp`, `tempNode`, `serializeLabel`, `resolveLabel`,
`resolveValueLabel`, `findBareTemperatures`, `fieldRefs`, `checkFieldArtifact`, `associateField`, `fieldScale`,
`colourLut`, `fieldTexels`, `createFieldFeed`, `solveStatus`, `twinOf`, `readTwin`, `twinMarkdown`, `writeGlb`; CLI
`scripts/package3d.mjs data|twin|export3d|check`.

## 1. `quantity.mjs`: quantities, bases, units

```js
// quantity.mjs (PURE). Every number in the room is a quantity with a basis (SPEC.md §5.0-5.1). Lengths are converted
// to mm HERE and nowhere else in the page (PL-13); the GLB writer converts mm to m once, in Node.
export const BASES = Object.freeze(["sourced", "derived", "model", "evidence", "render_hint", "unknown"]);
export const UNITS = Object.freeze(["um", "mm", "m", "mm2", "GB", "count", "fraction", "W", "W/cm2", "A", "A/us", "V",
  "mF", "nF/mm2", "uOhm", "bit", "Gbit/s", "GT/s", "GB/s", "TB/s", "pJ/bit", "W/(m*K)", "K*mm2/W", "K/W", "W/(m2*K)",
  "J/(m3*K)", "m*K/W"]);                                       // no temperature unit, by design (PL-4)
const LENGTH_TO_MM = Object.freeze({ um: 1e-3, mm: 1, m: 1e3 });
const tidy = (v) => Math.round(v * 1e9) / 1e9;               // the same rounding as scene.mjs:100

// q: one quantity object; ctx: { path, facts (the manifest's fact table), allowed (bases allowed in this file) }.
// Returns { quantity, error } with error = { code, path, detail } using SPEC.md §5.1's refusal codes.
export function readQuantity(q, { path, facts, allowed = BASES }) {
  if (!isObj(q) || !BASES.includes(q.basis) || !allowed.includes(q.basis)) return fail("malformed", path, "basis");
  if (!UNITS.includes(q.unit)) return fail("unit_not_supported", path, String(q.unit));
  for (const k of ["value", "min", "max"]) if (q[k] !== null && !(typeof q[k] === "number" && Number.isFinite(q[k]))) return fail("not_finite", path, k);
  if (q.basis === "unknown" && (q.value !== null || q.min !== null || q.max !== null)) return fail("malformed", path, "unknown carries a number");
  if (q.basis === "render_hint" && (q.value === null || !nonEmpty(q.hint_basis))) return fail("malformed", path, "render hint needs value and basis");
  if (q.basis === "sourced" && (!q.facts?.length || [q.value, q.min, q.max].every((v) => v === null))) return fail("malformed", path, "sourced needs facts and a number");
  if (q.basis === "derived" && (!q.facts?.length || !nonEmpty(q.derivation) || q.value === null)) return fail("malformed", path, "derived needs inputs and arithmetic");
  if (q.basis === "model" && !nonEmpty(q.model_ref)) return fail("malformed", path, "model needs file:line");
  for (const f of q.facts ?? []) if (!Object.hasOwn(facts ?? {}, f)) return fail("fact_unknown", path, f);
  const lo = q.min ?? -Infinity, hi = q.max ?? Infinity;
  if (lo > hi || (q.value !== null && (q.value < lo || q.value > hi))) return fail("range_order", path, "min <= value <= max");
  if (q.display !== undefined) {                 // a sourced range's display representative (SPEC.md §5.0; A#57218 item 5)
    const d = q.display;
    if (q.basis !== "sourced" || q.value !== null || !isObj(d) || d.basis !== "render_hint" || !(typeof d.value === "number" && Number.isFinite(d.value)) || !nonEmpty(d.derivation))
      return fail("malformed", path, "display: a sourced range (value null) with a finite render-hint value and its derivation");
    if (d.value < lo || d.value > hi) return fail("range_order", path, "display inside [min, max]");
  }
  for (const t of [q.derivation, q.hint_basis, q.note, q.display?.derivation]) if (t && findBareTemperatures(t).length) return fail("bare_temperature", path, t);
  return { quantity: Object.freeze({ ...q, facts: Object.freeze([...(q.facts ?? [])]) }), error: null };
}

// The number to DRAW, in mm, for a length quantity, with the basis the drawing carries (A#57218 item 5):
//   a value (sourced, derived, model, evidence, render_hint) -> drawn at it, with its own basis;
//   a sourced range with value null and a display            -> drawn at display.value, basis "render_hint", with
//                                                               display.derivation (the range itself stays data);
//   anything else (unknown; a range without a display)       -> { mm: null, basis: "unknown" }: the instance is undrawn.
// It never invents a representative: no midpoint, no bound.
export function drawnMm(q) {
  const k = LENGTH_TO_MM[q.unit];
  if (k === undefined) throw new TypeError(`not a length: ${q.unit}`);
  if (q.value !== null) return { mm: tidy(q.value * k), basis: q.basis, derivation: q.basis === "render_hint" ? q.hint_basis : null };
  if (q.display) return { mm: tidy(q.display.value * k), basis: "render_hint", derivation: q.display.derivation };
  return { mm: null, basis: "unknown", derivation: null };
}

// The detail panel's text for one quantity. No temperatures can reach here (no temperature unit exists).
//   sourced     "100 µm · sourced [pkg-021, thm-029]"        derived  "≈ 5.5 K·mm²/W · derived (720 µm / 130 W/(m·K))"
//   render_hint "not sourced · drawn at 1.000 mm (display only: <hint_basis>)"
//   sourced range "20–50 µm · sourced [<facts>] · drawn at 35 µm (display only: <display.derivation>)"   (value stays null)
//   unknown     "unknown"                                    model    "150 µm · model (sundai_tap/passive_interposer.py:148)"
export function describeQuantity(q, { digits = 3 } = {}) { /* returns { text, basis, chip } */ }
```

## 2. `ids.mjs` and `anatomy.mjs`: the anatomy readers

```js
// ids.mjs (PURE)
import { canonical } from "../canonical.mjs";                    // web/public/sentilab/canonical.mjs:4-10
import { drawnMm } from "./quantity.mjs";
export const INSTANCE_ID = /^[a-z0-9][a-z0-9-]{0,39}(\/[a-z][a-z0-9_]{0,47}#[0-9]{1,4})+$/;
export const typeOfId = (id) => id.slice(id.lastIndexOf("/") + 1).split("#")[0];
export const parentOfId = (id) => (id.split("/").length > 2 ? id.slice(0, id.lastIndexOf("/")) : null);
// Stability across builds: every id of the previous release is still present or listed in retired_ids, and no retired
// id is back in use (PL-11). previous: the last released assembly (or null on the first release).
export function idStability(previous, next) { /* -> { ok, missing: [...], reused: [...] } */ }

// The frozen preimage of geometry_sha256 and of every RenderModel's geometry_key (SPEC.md §5.0; A#57218 item 3).
// One record per instance, drawn or not, sorted by stable id; parent and box kept; no view state is a parameter, so
// none can enter. Callers refuse duplicate ids first, so the order is total. A new shape needs a new version string.
export const GEOMETRY_VERSION = "sentilab-geometry/1";
const byId = (a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);   // ids are ASCII (INSTANCE_ID): code-unit = byte order
const arrayGeometry = (a) => ({ class: a.class, region: { x0: a.region.x0, x1: a.region.x1, y0: a.region.y0, y1: a.region.y1 },
  lattice: a.lattice, pitch_mm: drawnMm(a.pitch).mm, diameter_mm: drawnMm(a.diameter).mm, height_mm: drawnMm(a.height).mm });
export function geometryPreimage(frame, instances) {
  const rows = instances.map((i) => ({
    id: i.id, type: i.type, parent: i.parent ?? null, variants: [...i.variants].sort(), drawn: i.drawn === true,
    box: i.drawn === true ? { x0: i.box.x0, x1: i.box.x1, y0: i.box.y0, y1: i.box.y1, z0: i.box.z0, z1: i.box.z1 } : null,
    array: i.drawn === true && i.array ? arrayGeometry(i.array) : null }));
  return canonical({ v: GEOMETRY_VERSION, frame, instances: rows.sort(byId) });   // geometry_sha256 = sha256(UTF-8 of this)
}
```

```js
// anatomy.mjs (PURE). All or nothing, like scene.mjs readGeometry (web/public/sentilab/package/scene.mjs:105-132).
import { readQuantity, drawnMm } from "./quantity.mjs";
import { findBareTemperatures } from "./temps.mjs";
import { INSTANCE_ID, typeOfId, geometryPreimage } from "./ids.mjs";
import { sha256Hex } from "../view-core.mjs";                     // web/public/sentilab/view-core.mjs:44

export const ANATOMY_SCHEMA = "sentilab-anatomy/1";
export const ASSEMBLY_SCHEMA = "sentilab-assembly/1";
export const ANATOMY_STATUS = "Typical anatomy · a representative reconstruction from public sources. Not any manufacturer's CAD. Not silicon-validated. Arrangement schematic; unknown values are marked.";
const ANATOMY_BASES = Object.freeze(["sourced", "derived", "render_hint", "unknown"]);   // no model, no evidence (X2)
const MODEL_KEYS = /(^|_)(our_model|in_our_model|solver_layer)(_|$)/;                   // lane-1 model fields must be gone (X5)

// json: the parsed anatomy.json. Returns { anatomy, error }. Refuses: wrong schema/content/status text, any string or
// key with a bare temperature (PL-4), any model-valued key (X5), any quantity failing readQuantity, any fact whose
// source is missing, any type edge or flow step naming an unknown part type, a parent_type cycle.
export function readAnatomy(json) {
  if (json?.schema !== ANATOMY_SCHEMA || json.content !== "anatomy" || json.status_text !== ANATOMY_STATUS) return no("schema");
  const temps = scanStrings(json, (s) => findBareTemperatures(s));     // strings AND keys
  if (temps.length) return no("bare_temperature", temps[0]);
  if (scanKeys(json, (k) => MODEL_KEYS.test(k)).length) return no("malformed", "model field in anatomy");
  // ... readQuantity over every thickness/footprint/count/k/interconnect/electrical/share with allowed: ANATOMY_BASES
  // ... resolve facts -> sources, edges -> part types, flow steps -> part types; parent_type acyclic
  return { anatomy: deepFreeze(json), error: null };
}

// json: the parsed assembly; anatomy: from readAnatomy. Async only because it recomputes geometry_sha256.
// Refuses: id grammar or duplicates, parent not an ancestor path, type unknown, a drawn box inverted or disagreeing
// with its quantities (sourced value or range, or render hint), a box, basis or array on an undrawn instance, an
// undrawn instance whose every dimension is drawable, a drawn child outside its nearest drawn ancestor's footprint,
// an edge whose type_edge is not in anatomy.type_edges, geometry_sha256 mismatch, a retired id in use.
export async function readAssembly(json, anatomy) {
  if (json?.schema !== ASSEMBLY_SCHEMA || json.content !== "anatomy") return no("schema");
  if (json.anatomy_sha256 !== anatomy.sha256) return no("binding_mismatch", "assembly built for another anatomy");
  const ids = new Set();
  for (const inst of json.instances) {
    if (!INSTANCE_ID.test(inst.id) || ids.has(inst.id) || typeOfId(inst.id) !== inst.type) return no("malformed", inst.id);
    if (json.retired_ids.includes(inst.id)) return no("id_reused", inst.id);
    const pt = anatomy.part_types[inst.type]; if (!pt) return no("dangling", inst.type);
    const dim = (k) => drawnMm(inst.dims?.[k] ?? (k === "t" ? pt.thickness : pt.footprint[k]));
    if (inst.drawn === false) {                        // UNDRAWN (SPEC.md §5.3): identity, parent, edges, null dims; no box
      if ("box" in inst || "basis" in inst || "array" in inst) return no("malformed", `${inst.id}: undrawn part with a box`);
      if (["w", "h", "t"].every((k) => dim(k).mm !== null)) return no("malformed", `${inst.id}: a drawable part is drawn`);
    } else if (inst.drawn === true) {                  // DRAWN: an assembled box that agrees with its quantities
      if (!(inst.box?.x0 < inst.box.x1 && inst.box.y0 < inst.box.y1 && inst.box.z0 < inst.box.z1)) return no("malformed", `${inst.id}: box`);
      const t = dim("t");
      if (t.mm === null || Math.abs((inst.box.z1 - inst.box.z0) - t.mm) > 1e-6) return no("malformed", `${inst.id}: drawn thickness`);
      if (inst.basis.thickness !== t.basis) return no("malformed", `${inst.id}: thickness drawn as ${t.basis}`);   // a range's representative is render_hint
      // ... the same for footprint w/h (value and basis) when the instance's basis.footprint is sourced/derived/render_hint
    } else return no("malformed", `${inst.id}: drawn must be true or false`);
    ids.add(inst.id);
  }
  // ... parents exist and are path prefixes; a drawn child lies inside its nearest DRAWN ancestor's footprint; edges
  //     resolve, and an edge may name an undrawn instance (its connections are kept)
  const geometry = geometryPreimage(json.frame, json.instances);    // sorted by id: source order never matters (AC-14)
  if ((await sha256Hex(new TextEncoder().encode(geometry))) !== json.geometry_sha256) return no("hash_mismatch", "geometry_sha256");
  return { assembly: deepFreeze(json), error: null };
}
```

## 3. `modelstack.mjs`: the model manifest and reference layouts

```js
// modelstack.mjs (PURE)
export const MODEL_STACK_SCHEMA = "sentilab-model-stack/1";
export const LAYOUTS_SCHEMA = "sentilab-layouts/1";
export const MODEL_STATUS = "Our model · the layers and blocks our thermal solver actually simulates, with its simplifications. Not the real package.";

// Refuses: not exactly grid layers 0..7 in order; an LCF layer without lcf_index or an appended layer with one; a
// layer material missing from materials_as_coded; k_W_per_mK !== 1 / resistivity (within 1e-9 relative); any
// boundary.temperature_inputs entry with rendered !== false; any bare temperature string (PL-4); a fixture whose
// dies' chiplet_id is not tap-chiplet-<index> (sundai_hotspot/tap_oracle.py:311); spreader_mm !== 2 * interposer_mm
// or sink_mm !== 2 * spreader_mm (sundai_tap/passive_interposer.py:154-155); a stands_for type unknown to the anatomy.
export function readModelStack(json, { anatomyTypes = null } = {}) { /* -> { stack, error } */ }

// Layouts: refuses a kind other than raw|snap0p5, mismatched array lengths, a fixture_id not in the stack, a
// frame_mm different from the fixture's interposer_mm. The content_sha256 is NOT recomputed here (Python-canonical:
// SPEC.md §5.0); scripts/package3d.mjs data recomputes it at build time with verify-core.js parseRaw/canonical.
export function readLayouts(json, stack) { /* -> { layouts, error } */ }

// The manifest fixture whose id equals the run's signed family (sentilab_core/conductor.py:116): REFERENCE CONTEXT ONLY
// (family_match). It does not say the run used this configuration; inputsVerification() decides that (SPEC.md §5.6;
// A#57218 item 6).
export const fixtureFor = (stack, family) => stack.fixtures.find((f) => f.fixture_id === family) ?? null;

// run_inputs_verified. signed: what the VERIFIED measurement envelope signs about its inputs, read by results.mjs:
//   { named: env.event.body.record.input_hashes ({ file name: sha256 }) | null, list: env.values.artifact_hashes | null,
//     flags: the signed model-selecting solver flags (P5) | null }
// Today, by code reading (conductor.py:337-347): named and list present, flags null -> not verified. Nothing is assumed.
export function inputsVerification(fixture, signed) {
  const inputs_evidence = isObj(signed?.named) ? "named_map" : Array.isArray(signed?.list) && signed.list.length ? "unnamed_list" : "absent";
  const flags_evidence = isObj(signed?.flags) ? "signed" : "absent";
  if (!fixture || inputs_evidence !== "named_map") return { inputs_evidence, flags_evidence, run_inputs_verified: false, input_differences: null };
  const want = fixture.expected_inputs, differences = [];                 // every expected input different or unsigned
  for (const name of ["samplelayers.lcf", "new_hotspot.config"]) if (signed.named[name] !== want[name]) differences.push(name);
  for (const [flag, value] of Object.entries(want.solver_flags)) if (signed.flags?.[flag] !== value) differences.push(flag);
  return { inputs_evidence, flags_evidence, run_inputs_verified: differences.length === 0, input_differences: differences };
}

// part type -> [{ grid_index, name }]: the inverse of stands_for, for the anatomy panel's "In our model" line.
export function standsForIndex(stack) { /* -> Map<typeId, Array<{ grid_index, name }>> */ }
```

## 4. `results.mjs`: values bound to receipts

```js
// results.mjs (PURE). Builds sentilab-result/1 (SPEC.md §5.6) for one track's layout at the playhead, from the
// verified prefix only. It never computes status: lifecycle and validity come from scene.mjs (which runs project()),
// labels from temperature-label.mjs, the mode from source.mjs.
import { labelFor } from "../../temperature-label.mjs";           // web/public/temperature-label.mjs:38-53, :84
import { serializeLabel } from "./temps.mjs";                      // labels leave as records (SPEC.md §7 PL-2)
import { fixtureFor, inputsVerification } from "./modelstack.mjs";

export const STATISTICS = Object.freeze({
  chip_layer_grid_max: "J: the chip layer's grid maximum (-grid_map_mode max)",
  chiplet_centre: "chiplet-centre temperature, as the producer defines it",
  field_cell: "one cell of a verified field, on one solver layer",
  all_layers_grid_max: "peak over all solver layers",
  chiplet_unit_native: "the solver's native per-unit temperature",
  tap_selector: "TAP's own run_hotspot selector",
  wire_proxy_weighted_manhattan: "wire proxy: connectivity-weighted Manhattan centre distance (not routed)",
  routed_wire_open_router: "routed wire length from the open router",
});
// metric_id -> statistic. Unknown metric ids map to null and the value is refused ("statistic_unknown"), never guessed.
const BY_METRIC = Object.freeze({ "peak-chip-c": "chip_layer_grid_max", "weighted-manhattan-mm": "wire_proxy_weighted_manhattan" });

// The receipt of an applied node.create in the prefix: { seq, event_id, hash } (the envelope hash covers values:
// contracts/view-envelope-v0.5/VIEW-ENVELOPE.md:31). A rejected create lends nothing (temperature-label.mjs:122-136).
export function receiptOf(prefixEnvelopes, rejected, nodeId) { /* -> { seq, event_id, hash } | null */ }

// The verified measurement's signed statements about its inputs (SPEC.md §5.6): { named, list, flags }. named =
// env.event.body.record.input_hashes ({ file name: sha256 }: conductor.py:337-341), list = env.values.artifact_hashes
// (:346), flags = the signed model-selecting solver flags (none today: P5). From the verified prefix only.
export function signedInputsOf(verification, measurementNode) { /* -> { named, list, flags } */ }

// inputs:
//   verification  source.mjs normalize() result (source.mjs:82-106): prefixEnvelopes, prefixCount, projection, total, frozen
//   scene         scene.mjs sceneAt() at the playhead (scene.mjs:540-544); layout = scene.tracks[i].layout (scene.mjs:387-411)
//   ids           temperature-label.mjs evaluatorIds(prefixEnvelopes, projection.rejected) (temperature-label.mjs:127-136)
//   mode          source.mjs modeNow()/liveModeOf() (source.mjs:172-182)
//   stack, layouts from readModelStack/readLayouts; fieldStatus from stream.mjs (or null)
export function resultView({ verification, scene, track, ids, mode, stack, layouts, fieldStatus = null }) {
  const L = scene?.tracks.find((t) => t.track === track)?.layout ?? null;
  const run = scene?.run ?? null;
  const fixture = fixtureFor(stack, run?.family);                               // REFERENCE context only (family_match)
  const inputs = inputsVerification(fixture, signedInputsOf(verification, L?.metric?.measurement ?? null));   // A#57218 item 6
  const values = [], refused = [];
  if (L?.J) {
    const m = L.metric?.measurement ?? (L.ref.kind === "measurement" ? L.ref.id : null);
    const identity = ids.get(m);
    const statistic = BY_METRIC[metricIdOf(verification, m)] ?? null;           // semantics.metric_id (conductor.py:342)
    if (!statistic) refused.push({ node: m, field: "J", code: "statistic_unknown", detail: String(metricIdOf(verification, m)) });
    else values.push(freezeValue({ quantity: "J", statistic, value: L.J.value, unit: "degC", declared_unit: L.J.declared_unit,
      association: { layer: 4, scope: "chip layer, all cells" }, measurement: { node: m, receipt: receiptOf(verification.prefixEnvelopes, verification.projection?.rejected, m) },
      evaluator_identity: identity ?? null, label: serializeLabel(labelFor(identity)), validity: L.metric.state, as_of_seq: seqOf(verification, m) }));
  }
  if (L?.W) { /* statistic from L.W.metric_id ("weighted-manhattan-mm" -> wire_proxy_weighted_manhattan); unit "mm"; label null */ }
  for (const c of L?.chiplets ?? []) if (c.temp !== null) { /* chiplet_centre, association { chiplet: c.id }, label of L.temps_from.measurement */ }
  for (const e of scene?.errors ?? []) refused.push({ node: e.node, field: e.field, code: e.code, detail: e.detail ?? "" });
  return Object.freeze({
    schema: "sentilab-result/1", content: "result", status_text: RESULT_STATUS,
    run: { run_id: run?.run_id ?? verification.runId, family: run?.family ?? null, arm: run?.arm ?? null, seed: run?.seed ?? null },
    prefix: { K: verification.prefixEnd ?? 0, total: verification.total, frozen: verification.frozen, mode: mode.mode, mode_label: mode.label, at_seq: scene?.at.seq ?? 0 },
    layout: L && !L.geometry_error ? layoutBlock(L, fixture, layouts, verification) : null,
    model: { family: run?.family ?? null,
             family_match: run?.family == null ? "family_absent" : fixture ? "match" : "no_match",   // reference context; binds nothing
             reference: fixture ? { fixture_id: fixture.fixture_id, model_stack_sha256: stack.sha256 } : null,
             ...inputs,                                                                            // run_inputs_verified and its evidence
             stack_basis: inputs.run_inputs_verified ? "run_inputs" : "schematic" },
    values, field: fieldStatus, receipt_completeness: receiptCompleteness(verification, L), refused,
  });
}
// A value's label is the SERIALIZED record of the rule's own object (temps.mjs serializeLabel). Object identity is never
// relied on outside this process: every reader recomputes and compares it (temps.mjs resolveLabel, SPEC.md §7 PL-2).

// What today's receipts bind (SPEC.md §5.6): evaluator identity and signed geometry yes; inputs as an unnamed list
// (conductor.py:346); no argv; the power trace only inside the unnamed list; no field.
export function receiptCompleteness(verification, L) { /* -> { evaluator_identity, geometry_signed, input_hashes, argv, power_trace, field } */ }

// Numeric match of a signed layout to a reviewed reference (never a JavaScript re-hash of Python-canonical JSON).
// chiplets: layout chiplets (lower-left x, y, w, h in mm); returns { variant_id, content_sha256, max_abs_diff_mm } or null.
export function matchReference(chiplets, fixture, layouts, { tolMm = 1e-6 } = {}) {
  if (!fixture) return null;
  for (const lay of layouts.layouts.filter((l) => l.fixture_id === fixture.fixture_id)) {
    // die i of the fixture is chiplet tap-chiplet-<i>; centre = (x + w/2, y + h/2); rotated iff (w, h) is the turned footprint
    // max |Δ| over all centres and footprints; all within tolMm -> match
  }
  return null;
}
```

## 5. `model.mjs`: one RenderModel per content kind, deep-frozen

```js
// model.mjs (PURE). The renderer, the SVG fallback and the twin all draw from this; none of them decides anything.
import { drawnMm } from "./quantity.mjs";
import { STACK, readGeometry } from "../package/scene.mjs";   // schematic constants (scene.mjs:23-35) for an unknown family
import { standsForIndex } from "./modelstack.mjs";

export const MODEL_VERSION = "sentilab-model3d/1";
export const KINDS = Object.freeze(["anatomy", "model", "result"]);

// Exactly one of the three inputs, matching `kind`; anything else is refused (X1). Returns { model, error }.
//   anatomy: { anatomy, assembly, variant }                       -> boxes from the assembly (assembled, mm)
//   model:   { stack, fixtureId, layoutId, layouts }              -> the 8 grid layers + the layout's dies, halos, edge strips
//   result:  { stack, result }                                    -> the run's signed geometry on its fixture's stack
export function buildRenderModel({ kind, anatomy = null, assembly = null, variant = "lidded", stack = null, fixtureId = null,
                                   layoutId = null, layouts = null, result = null }) {
  if (!KINDS.includes(kind)) return no("malformed", "kind");
  const given = { anatomy: Boolean(anatomy || assembly), model: Boolean(layoutId || fixtureId) && !result, result: Boolean(result) };
  if (Object.entries(given).some(([k, on]) => on && k !== kind)) return no("mixed_content", "one content kind per model");   // X1
  const out = kind === "anatomy" ? anatomyBoxes(anatomy, assembly, variant)
    : kind === "model" ? modelBoxes(stack, fixtureId, layoutId, layouts)
    : resultBoxes(stack, result);
  if (out.error) return out;
  return { model: deepFreeze({
    v: MODEL_VERSION, kind,
    status_text: out.status_text,                    // the mode banner, verbatim (SPEC.md §3)
    units: "mm", frame: out.frame,
    boxes: out.boxes,                                // DRAWN instances only: [{ id, type, parent, level, inner_index, x0..z1, basis: {position, footprint, thickness} }]
    arrays: out.arrays,                              // parametric interconnect arrays (anatomy) or none
    links: out.links,                                // instance edges (anatomy), netlist links (model, result); a link with an undrawn end is listed, not drawn
    levels: out.levels,                              // explode order, bottom to top
    bounds: boundsOf(out.boxes),                     // over drawn boxes only: an undrawn part never widens the view
    notes: out.notes,                                // e.g. "spreader 90 mm and sink 180 mm drawn as outlines"
    not_drawn: out.not_drawn,                        // UNDRAWN instances (SPEC.md §5.3): [{ id, type, parent, label, dims, reason: "size unknown and no render hint" }];
                                                     // the part tree, panel, links and twin use them; bounds, pick(), sectionAt() and fields never do
    geometry_key: out.geometry_key,                  // geometryPreimage(frame, this model's instances, drawn and not): the frozen
                                                     // preimage of SPEC.md §5.0, for the immutability test (AC-12)
  }), error: null };
}

// result kind: chiplet footprints ONLY from the signed geometry (layout.chiplets, from scene.mjs readGeometry,
// scene.mjs:107-132), in every case. Only when result.model.run_inputs_verified: interposer = [0, fixture.interposer_mm]^2
// and layer thicknesses from the model stack (the run's own verified inputs). Otherwise the Package view's schematic
// rule (interposer = extent + 1.5 mm, scene.mjs:239-244; heights from STACK) with every such box basis "render_hint"
// and the note "this run's layer inputs are not verified; schematic stack" (plus "no model for family <f>" when
// family_match is not "match"). NEVER a thickness from the anatomy, and NEVER the family's current manifest without
// verified inputs (X3, X4; A#57218 item 6).
function resultBoxes(stack, result) { /* ... */ }

// model kind: grid layers 0..5 as interposer-sized slabs (lcf), layer 4 split into Chiplet_i (silicon), halo strips
// (Ubump_*, width fixture.dies[i].halo_mm), edge strips (Edge_*, width 0.5 mm: TAP_MARGIN_MM, tap_oracle.py:35) and the
// whitespace fill; layer 3 the same footprints in the bump mix; 6 (spreader) and 7 (sink) as outlines of 2x and 4x the
// interposer with their grid extent (the interposer) marked. Every box basis "model" with its cite.
function modelBoxes(stack, fixtureId, layoutId, layouts) { /* ... */ }

// Deep freeze: every nested object and array. A later write throws in strict mode (modules are strict).
export function deepFreeze(o) { if (o && typeof o === "object" && !Object.isFrozen(o)) { Object.freeze(o); for (const v of Object.values(o)) deepFreeze(v); } return o; }
```

## 6. `view.mjs`, `explode.mjs`, `section.mjs`: view transforms only

```js
// view.mjs (PURE). The only place display geometry exists. It reads the frozen model and returns a NEW Map; it never
// writes to the model (PL-12). The assembled box stays the truth for lengths, picks and field lookups.
export const DRAW = Object.freeze({ min_visible_mm: 0.25, explode_gap_frac: 0.18, inner_gap_frac: 0.04 });   // L3:PSEUDOCODE §1 DRAW

// viewState: { explodeT (0..1), readable (bool) }. Returns Map<id, { x0, x1, y0, y1, z0, z1, thickened, dz }>.
export function displayBoxes(model, { explodeT = 0, readable = true } = {}) {
  const out = new Map();
  // 1. readable: per level (bottom to top), display thickness = max(true, DRAW.min_visible_mm); each level's display z0
  //    = the display top of the level below (restack), so thickened layers never overlap. x and y are untouched.
  // 2. explode: dz = explodeOffsets(model, explodeT).get(id); applied after the restack.
  // 3. thickened: true where the clamp acted (drives the chip "thin layers thickened for visibility").
  return out;
}
```

```js
// explode.mjs (PURE except the driver). Level k rises by t * gap * k; parts inside a die stack (HBM internals) also
// separate by inner_gap * inner_index. Spacing is schematic: the page shows "exploded · spacing not to scale" when t > 0.
export function explodeOffsets(model, t) {
  const span = Math.max(model.bounds.x1 - model.bounds.x0, model.bounds.y1 - model.bounds.y0);
  const gap = DRAW.explode_gap_frac * span, out = new Map();
  for (const b of model.boxes) out.set(b.id, t * gap * model.levels.indexOf(b.level) + t * DRAW.inner_gap_frac * gap * (b.inner_index ?? 0));
  return out;
}
// Driver: eases t over 600 ms with render.mjs easeInOut (web/public/sentilab/package/render.mjs:19); jumps when
// reduced motion is on (the media query, as package.js:17). Frames only while moving (as package.js:243).
export function createExplodeController({ reduced, onFrame, now = () => performance.now() }) { /* L3:PSEUDOCODE §2, unchanged */ }
```

```js
// section.mjs (PURE). The 3D caps and the SVG fallback come from this one call, so they cannot disagree.
// plane: { axis: "x" | "y", at: mm } in ASSEMBLED coordinates; display: the Map from displayBoxes (for z only).
export function sectionAt(model, plane, display) {
  const rects = [];
  for (const b of model.boxes) {
    const [lo, hi] = plane.axis === "x" ? [b.x0, b.x1] : [b.y0, b.y1];
    if (!(plane.at >= lo && plane.at <= hi)) continue;
    const [u0, u1] = plane.axis === "x" ? [b.y0, b.y1] : [b.x0, b.x1];
    const d = display.get(b.id);
    rects.push({ id: b.id, type: b.type, u0, u1, z0: d.z0, z1: d.z1, thickened: d.thickened, basis: b.basis });
  }
  return { plane, rects: rects.sort(byZThenU), arrays: arrayCuts(model, plane, display) };
}
```

## 7. `interconnect.mjs`, `pick.mjs`, `flows.mjs`

```js
// interconnect.mjs (PURE). Arrays are sampled on a regular lattice (every k-th site in both directions),
// deterministically, and the view says "1 of k² sites drawn · N total (basis)" (L3:ARCHITECTURE §4.5).
export const TRIS_PER_INSTANCE = 28;            // closed 8-sided cylinder: 16 side + 2 x 6 cap triangles
// The instance budget follows from the triangle budget (AC-34, D4), not from a fixed count.
export function instanceBudget({ triangleBudget, otherTriangles }) {
  return Math.max(0, Math.floor((triangleBudget - otherTriangles) / TRIS_PER_INSTANCE));
}
export function interconnectArrays(model, { budget }) { /* L3:PSEUDOCODE §4, with count_basis from the array's count quantity */ }
// The part, every part it connects to (undrawn ones too, for the part tree and panel), and the interconnect between
// them (L3:PSEUDOCODE §4). The renderer highlights only the drawn members.
export function highlightSet(model, id) { /* -> Set<id> */ }
```

```js
// pick.mjs (PURE). ray: { origin, dir } in display space (render3d.ray()). Slab test against the display boxes of DRAWN
// instances (model.boxes; an undrawn part has no box and is never returned); returns the nearest instance id, or null.
// cellAt maps a hit on a field sheet back to (layer, row, col) using x and y only, which explode and readable never
// change.
export function pick(model, display, ray) { /* -> id | null */ }
export function cellAt(fieldGrid, gridIndex, x, y) { /* -> { layer, row, col } | null, honouring grid.row0 */ }
```

```js
// flows.mjs (PURE). Overlays per content kind (SPEC.md §4.3). Paths run through instance centroids in DISPLAY space;
// a step on an undrawn part adds no point (no invented centroid) and its legend line reads "passes through <label> ·
// not drawn".
export const QUALIFIER = Object.freeze({
  anatomy: "Typical path through the parts. Not a solved heat flux, not a routed wire, not a measured bandwidth.",
  model: "Model structure: conduction paths and inputs as configured. Not results.",
});
// kind: "heat" | "power" | "signal". Returns { paths: [{ id, points, arrow }], legend: [text], qualifier } or, in the
// result kind, { paths: [], legend, qualifier: null } for heat (no arrows in Results: PL-14) and the model's netlist and
// power inputs for signal and power.
export function overlayFor(model, { kind, anatomy = null, stack = null, fixture = null, display }) { /* ... */ }
```

## 8. `temps.mjs`: the one place a temperature becomes text

```js
// temps.mjs (PURE). Wraps the site's one label rule (web/public/temperature-label.mjs:38-85).
import { LABELS, labelFor, labelForAll, envelopeEvaluator, needsNotice, NOTICE } from "../../temperature-label.mjs";

const RULE_LABELS = new Set(Object.values(LABELS));            // identity, not shape: a look-alike object fails

// valueC: finite °C (already converted by scene.mjs rules, scene.mjs:134-145). label: one of LABELS.
export function formatTemp(valueC, label, { digits = 1 } = {}) {
  if (!RULE_LABELS.has(label)) throw new TypeError("a temperature needs its label (temperature-label.mjs)");
  if (typeof valueC !== "number" || !Number.isFinite(valueC)) throw new TypeError("not a finite temperature");
  return Object.freeze({ text: `${valueC.toFixed(digits)} °C`, qualifier: label.short, title: label.title, state: label.state });
}
// One DOM unit holds the value and its qualifier, so no layout, crop or copy separates them (L3:PSEUDOCODE §5).
export function tempNode(h, valueC, label) {
  const t = formatTemp(valueC, label);
  return h("span", { class: `t s-${t.state}`, title: t.title }, t.text, " ", h("em", { class: "q" }, t.qualifier));
}

// Labels as data (SPEC.md §7 PL-2). Object identity cannot survive a JSON round trip, so a label leaves this process
// as a plain record and comes back only through resolveLabel(). The exact algorithm:
//   Serialize S1 identity = evaluatorIds(prefixEnvelopes, rejected).get(measurement node) ?? null, over the VERIFIED
//               prefix (a rejected create lends nothing: temperature-label.mjs:122-136)
//             S2 record = serializeLabel(labelFor(identity)): exactly { state, text, short, title }, copied from the
//               rule's own frozen object (notice is not serialized: it follows from state)
//             S3 the value carries evaluator_identity = identity and label = record; a twin is written as
//               canonical(twin) + LF (canonical.mjs:4-10: keys sorted, arrays kept in order, no whitespace), UTF-8
//   Resolve   R1 bytes -> strictJson (fatal UTF-8, BOM refused: runs-list.mjs:11) -> schema checks (readTwin; the
//               page and the CLI hold the value in memory and start at R2)
//             R2 identity = the VERIFIED identity where the caller has one (page, CLI: evaluatorIds() over the verified
//               prefix), which must equal value.evaluator_identity; otherwise the recorded value.evaluator_identity
//               (twin reader: the twin's identities are verified by re-running export3d on its pinned replay, AC-36)
//             R3 expected = labelFor(identity)
//             R4 label_mismatch unless the record is a plain object whose sorted keys are exactly short, state, text,
//               title and whose four values are strings === expected's (no trimming, case folding or normalisation)
//             R5 return expected: the canonical frozen LABELS object, the only thing formatTemp() accepts
export const LABEL_KEYS = Object.freeze(["short", "state", "text", "title"]);          // sorted, as canonical() writes them
export function serializeLabel(label) {
  if (!RULE_LABELS.has(label)) throw new TypeError("label not from the rule");
  return Object.freeze({ state: label.state, text: label.text, short: label.short, title: label.title });
}
export function resolveLabel(record, identity) {
  const expected = labelFor(identity);
  const ok = record !== null && typeof record === "object" && !Array.isArray(record)
    && Object.keys(record).sort().join(",") === LABEL_KEYS.join(",")
    && LABEL_KEYS.every((k) => typeof record[k] === "string" && record[k] === expected[k]);
  return ok ? { label: expected, error: null } : { label: null, error: { code: "label_mismatch", detail: `expected ${expected.state}` } };
}
// A result value's label. verified: the caller's verified identity for value.measurement.node, with null for "verified:
// no identity" (pass `ids.get(node) ?? null`); omit it only in the twin reader. Any disagreement is label_mismatch.
export function resolveValueLabel(value, { verified } = {}) {
  const recorded = value.evaluator_identity ?? null;
  if (verified !== undefined && verified !== recorded) return { label: null, error: { code: "label_mismatch", detail: "evaluator identity" } };
  return resolveLabel(value.label, recorded);
}
export const PATTERN = Object.freeze({ withdrawn: 2, unvalidated: 1, illustrative: 0, accepted: 0 });
export const patternFor = (label) => PATTERN[label.state] ?? PATTERN.unvalidated;
export const fieldLabel = (env, ids) => labelFor(envelopeEvaluator(env, ids));   // temperature-label.mjs:156-161
export const legendLabel = (identities) => labelForAll(identities);               // temperature-label.mjs:72-80
export { needsNotice, NOTICE };

// The scanner used by every static check and by the readers (PL-4, AC-03). A temperature is a number followed by a
// temperature unit. A bare "C" or "K" counts unless it is part of a resistance or conductivity unit (K/W, K*mm2/W,
// K·mm²/W, m·K) or glued to a word ("C4"). The producer writes Celsius as "C" (sentilab_core/conductor.py:344), so a
// bare "C" must count. The pattern is case-insensitive, so thousands are written in full in served copy ("10,000" and
// "300,000", never "10K" or "300k"): either abbreviation is flagged, which is the safe direction.
export const TEMP_PATTERN = /(?<![\w.])[-−]?\d+(?:[.,]\d+)?\s*(?:[°º]\s*[CF]|℃|℉|deg\s*[CF]\b|(?:kelvin|celsius)\b|[CK](?![\w*·/^)\]]))/giu;
export const TEMP_KEY = /\d+\s*(?:C|K|degC|degK)\b|_\d+C\b/i;
// text -> [{ index, match }]; [] when clean. Used for strings; keys are checked with TEMP_KEY by the readers.
export function findBareTemperatures(text) { return [...String(text).matchAll(TEMP_PATTERN)].map((m) => ({ index: m.index, match: m[0] })); }
```

Negative controls for the scanner (AC-03), synthetic values chosen to match no real datum: caught: `47 C`,
`300.5 K`, `61 °C`, `99°C`, `-12 degC`, `0.7 K rise`, `12 kelvin`, `33 ºC`, `0.04 °C·cm²/W` (a resistance written
with °C must be normalised to K·mm²/W), `silicon_85C` and `silicon_at_100C` (keys); clean: `4 K*mm2/W`, `0.039 K/W`,
`5 K·mm²/W`, `117.5 W/(m*K)`, `C4 bumps`, `4 C4 rows`, `10,000-30,000`, `seq 12`, `2,778 W/(m²·K)`, `HBM3E 12-high`,
`L4 chip layer`. (Checked in Node 22 against this exact pattern while writing this spec; the build's test re-runs it.)

## 9. `field.mjs`: refs, artifact checks, scale, texels (used in production only after P1-P4)

```js
// field.mjs (PURE except hashing, which uses WebCrypto through view-core.mjs sha256Hex, view-core.mjs:44).
import { sha256Hex } from "../view-core.mjs";
import { strictJson } from "../runs-list.mjs";                       // runs-list.mjs:11 (fatal UTF-8, BOM kept -> refused)
import { heatColor, BOUNDS } from "../package/scene.mjs";            // scene.mjs:269-275, :92-98
import { rgb } from "../package/render.mjs";                         // render.mjs:24

export const FIELD_FORMAT = "sentilab-field/0.1";
export const FIELD_CAPS = Object.freeze({ max_bytes: 4 * 1024 * 1024, max_rows: 128, max_cols: 128, max_layers: 16 });
const HEX64 = /^[0-9a-f]{64}$/;
const INPUT_SOURCES = Object.freeze(["samplelayers.lcf", "new_hotspot.config", "sample.ptrace"]);

// The allowlist: ONLY fields named by measurement node.create envelopes inside the verified projectable prefix that
// project() applied. Nothing after K, nothing rejected, nothing from a file manifest (L3:PSEUDOCODE §6, unchanged).
export function fieldRefs(prefixEnvelopes, projection) { /* -> Map<sha256, ref> with ref.artifact_hashes = env.values.artifact_hashes */ }

// bytes: the raw body, already capped by readBodyCapped (view-core.mjs:108). In this order; nothing is decoded
// before the hash matches. Any failure: { ok: false, error }, nothing drawn, previous texture bytes untouched.
export async function checkFieldArtifact(bytes, ref, { stack = null } = {}) {
  if (!(bytes instanceof Uint8Array) || bytes.length > FIELD_CAPS.max_bytes) return no("too_large");
  if ((await sha256Hex(bytes)) !== ref.sha256) return no("hash_mismatch");
  let doc; try { doc = strictJson(bytes); } catch { return no("malformed"); }
  if (doc?.format !== FIELD_FORMAT) return no("format");
  const b = doc.binding ?? {};
  if (b.run_id !== ref.run_id || b.measurement !== ref.measurement || b.evaluator_version !== ref.evaluator) return no("binding_mismatch");
  // (+) every INPUT source the artifact names must be a hash the signed envelope already lists (SPEC.md §5.7).
  const signed = new Set(Array.isArray(ref.artifact_hashes) ? ref.artifact_hashes : []);
  for (const name of INPUT_SOURCES) if (!HEX64.test(doc.sources?.[name] ?? "") || !signed.has(doc.sources[name])) return no("binding_mismatch", `source ${name}`);
  const { rows, cols, row0 } = doc.grid ?? {};
  if (rows !== ref.rows || cols !== ref.cols || doc.layers?.length !== ref.layers || doc.values?.length !== ref.layers) return no("dims");
  if (rows > FIELD_CAPS.max_rows || cols > FIELD_CAPS.max_cols || ref.layers > FIELD_CAPS.max_layers || !["top", "bottom"].includes(row0)) return no("dims");
  const toC = doc.unit === "K" ? (v) => v - 273.15 : doc.unit === "°C" || doc.unit === "C" ? (v) => v : null;   // as scene.mjs:88-89
  if (!toC) return no("unit_not_supported");
  const layers = [];
  for (let L = 0; L < ref.layers; L += 1) {
    const raw = doc.values[L];
    if (!Array.isArray(raw) || raw.length !== rows * cols) return no("dims");
    const c = new Float32Array(rows * cols);
    for (let i = 0; i < raw.length; i += 1) {
      const v = typeof raw[i] === "number" ? toC(raw[i]) : NaN;
      if (!Number.isFinite(v) || v < BOUNDS.temperature_c.min || v > BOUNDS.temperature_c.max) return no("out_of_range");
      c[i] = v;
    }
    layers.push(Object.freeze({ index: L, name: String(doc.layers[L].name), thickness_m: doc.layers[L].thickness_m, c }));
  }
  // Not a refusal: a layer table that differs from the model manifest is listed (the artifact is the authority).
  const differs = stack ? compareLayerTable(doc.layers, stack.layers) : [];
  return { ok: true, field: Object.freeze({ ref, grid: Object.freeze({ rows, cols, extent_mm: doc.grid.extent_mm, row0 }), layers, differs }) };
}

// Validity is not association (SPEC.md §5.7; A#57218 item 6). A field that passed checkFieldArtifact is drawn
// ("verified") only when its association holds; otherwise it is "unassociated" with its reasons, nothing is drawn, no
// scale comes from it and no number is exported, while its existence and receipt are listed.
export function associateField(field, result) {
  const reasons = [];
  if (!result.model.run_inputs_verified) reasons.push("run_inputs_unverified");
  return reasons.length ? { status: "unassociated", reasons } : { status: "verified", reasons: [] };
}

// One fixed scale per run over every accepted field value, rounded out to 5 and at least 10 wide (the rule runFrame
// applies, scene.mjs:230-233); live runs only widen it (playhead.mjs:28-38).
export function fieldScale(fields, previous = null) { /* ... */ }
// 1,024-entry table built from heatColor() at bin centres; within 1/255 per channel (L3:evidence/extra-05).
export function colourLut(scale) { /* L3:PSEUDOCODE §6, unchanged */ }
// RGBA8 texels for one layer in the declared row order; NEAREST only (L3:PSEUDOCODE §6, unchanged).
export function fieldTexels(field, layerIndex, { scale, lut }) { /* ... */ }
```

## 10. `stream.mjs`: field feed, solve status, doorbell

```js
// stream.mjs. Fetches only the ARTIFACTS the verified prefix names, with backpressure and back-off; never decides
// LIVE or STALE (source.mjs liveModeOf, source.mjs:172-177, does). L3:PSEUDOCODE §7 with three changes:
//   - adopt() also aborts every in-flight fetch and drops the cache on a mode switch (dispose(), PL-12/§6.7);
//   - a response that arrives for a hash no longer wanted is discarded by hash, never shown (stale fetch);
//   - artifactUrl defaults to the P3 route and the feed reports { kind: "absent" } while that route does not exist
//     (production until P1-P4), so the page says "No field in this run's receipts" instead of retrying forever.
import { readBodyCapped } from "../view-core.mjs";
import { fieldRefs, checkFieldArtifact, FIELD_CAPS } from "./field.mjs";

export function createFieldFeed({ fetchImpl = (...a) => fetch(...a), onChange = () => {}, now = () => Date.now(),
                                   artifactUrl = (h) => `/api/view/artifacts/${h}`, enabled = false, maxInFlight = 2,
                                   cacheBytes = 32 << 20, stack = null }) {
  /* adopt(verification), request(seq, pickRef), status(ref), dispose()  (L3:PSEUDOCODE §7); status(ref) is one of
     loading | verified | unassociated (with reasons, from associateField) | refused (with its error) | unavailable */
}

// Solve status from the verified lifecycle only (evidence-projection.mjs:11-12 lists simulation_pending):
//   candidate simulation_pending and mode LIVE  -> { text: "solving (since seq S)" }
//   candidate simulation_pending and not LIVE   -> { text: `solve status unknown (feed ${mode.label})` }
//   anything else                                -> null
export function solveStatus(scene, mode) { /* ... */ }

// Optional doorbell (W15, needs P10): messages only call feed.poke() (source.mjs:256). Never data, progress or LIVE.
export function createDoorbell({ url, feed }) { /* L3:PSEUDOCODE §7, unchanged */ }
```

## 11. `twin.mjs`, `scripts/lib/glb.mjs`, `scripts/package3d.mjs`

```js
// twin.mjs (PURE). The same RenderModel and result view the page draws, as data (PL-22). No pixels, no view state.
import { canonical } from "../canonical.mjs";
import { formatTemp, resolveValueLabel } from "./temps.mjs";
export const TWIN_SCHEMA = "sentilab-twin/1";
export const VIEW_TRANSFORMS = "Explode, readable thickening and section are view transforms. Every coordinate here is assembled.";

// model: from buildRenderModel; ctx: { builtFrom: [{ path, sha256, commit? }], anatomy?, stack?, fixture?, layout?,
// result?, omitted: [...], derivatives: [...] }. Throws if any degC value's label record differs from
// serializeLabel(labelFor(value.evaluator_identity)) (PL-2), and if static content (anatomy, model) contains a bare
// temperature (PL-4).
export function twinOf(model, ctx) {
  const data = model.kind === "anatomy" ? anatomyData(model, ctx) : model.kind === "model" ? modelData(model, ctx) : ctx.result;
  const twin = { schema: TWIN_SCHEMA, content: model.kind, status_text: model.status_text, built_from: ctx.builtFrom,
    frame: model.frame, view_transforms: VIEW_TRANSFORMS, data, labels: labelsUsed(data), omitted: ctx.omitted, derivatives: ctx.derivatives ?? [] };
  assertTwinLabels(twin);                      // every { unit: "degC" } value: resolveValueLabel(v) succeeds (temps.mjs R1-R5)
  return twin;
}
// Byte-reproducible text: canonical key order (canonical.mjs:4-10), one trailing LF.
export const twinJsonText = (twin) => `${canonical(twin)}\n`;
// The reader: bytes -> strictJson -> schema (sentilab-twin/1, SPEC.md §5.8) -> resolveValueLabel(v) for every degC
// value (temps.mjs R1-R5, without a verified identity). All or nothing: one label_mismatch refuses the twin.
export function readTwin(bytes) { /* -> { twin, error } */ }
// Markdown from a twin returned by readTwin(); the CLI and the dialog run result -> twinJsonText -> bytes -> readTwin ->
// twinMarkdown. Same banner, qualifiers and label texts; tables for instances, layers and values; a temperature cell
// always reads "<value> °C <short>" through formatTemp(v.value, resolveValueLabel(v).label) (the only formatter).
export function twinMarkdown(twin) { /* deterministic; LF only */ }
```

```js
// scripts/lib/glb.mjs (Node only). Deterministic glTF 2.0 binary: one node per DRAWN box (arrays as their region boxes),
// node.name = instance id, node.extras = { instance_id, type, basis }; positions in metres with +Y up. This is the ONE
// place lengths leave mm (PL-13): [x, y, z]_mm -> [x / 1000, z / 1000, -y / 1000]_m. Float32 positions and normals,
// Uint32 indices, 4-byte aligned chunks, no textures, no compression, no extensions (L3:PSEUDOCODE §10).
export function writeGlb(model) { /* -> Uint8Array; the caller records its sha256 in twin.derivatives */ }
```

```js
// scripts/package3d.mjs (Node 22). Same verifier path for results as scripts/sentilab-scene.mjs (the v0.5 reference
// verifier behind the v0.6.1 bytes-to-rows rule, scripts/sentilab-scene.mjs:23-28). Exit codes as that CLI:
// 0 ok; 1 usage or input error; with --strict, 2 broken prefix, 3 refused values (sentilab-scene.mjs:15-16).
//
//   node scripts/package3d.mjs data   [--check]   L1 parts.json (pinned) + docs/sentilab/package3d/* -> web/public/sentilab/package3d/data/*, pins.mjs
//   node scripts/package3d.mjs twin   [--check]   data -> web/public/agents/package3d/* (+ replays/*.json for the bundled replays)
//   node scripts/package3d.mjs export3d <replay.jsonl> --out <dir> [--run <id>] [--pins test] [--at <seq>] [--artifacts <dir>] [--strict]
//   node scripts/package3d.mjs check              every --check above, plus the scanners (W5), without writing
//
// data: (1) refuse unless sha256(parts.json) equals the pinned value; (2) apply the overlay; (3) refuse any bare
// temperature, model field or non-generic name (D1 policy); (3b) quantity preservation: every served quantity's value,
// min and max equal lane 1's typical, min and max (null stays null: no midpoint in value), and a lane-1 render hint
// lands only in a render_hint quantity or a range's display (A#57218 item 5); (4) number-preservation: every number in a served claim
// occurs in the lane-1 fact's claim or value (AC-40); (5) layouts: for each reference, parse with verify-core.js
// parseRaw (keeps number text, web/public/verify-core.js:5-6, :14), recompute sha256(canonical(identity.canonical))
// with verify-core.js canonical (:103, Python's json.dumps(sort_keys=True, separators=(",", ":"))) and refuse on any
// mismatch with identity.content_sha256; (6) write files with LF and canonical key order; (7) write pins.mjs.
// --check: rebuild in memory and compare bytes with the committed files (the tap_references --check pattern,
// docs/sentilab/references/README.md:37-39).
```

## 12. DOM and GL modules (deltas from lane 3)

- `labels.mjs`: lane 3's `createLabelLayer` (L3:PSEUDOCODE §8) with one change: the transform is set per property
  (`el.style.transform = …`), never `cssText`; labels are `aria-hidden`, the part tree is the accessible route.
- `fallback2d.mjs`: `renderSectionSvg(svg, sectionAt(...), { describe })`: one `<rect>` per section rectangle,
  `<title>` text from the same `describeQuantity()` strings the panel uses; SVG attributes only, no `style=""`.
- `render3d.mjs`, `gl.mjs`, `shaders.mjs`, `mat4.mjs`, `camera.mjs`: lane 3's (L3:PSEUDOCODE §9) with:
  `dispose()` deletes every program, buffer and texture and returns the counts; `stats` adds `glObjects`;
  `setModel()` takes a frozen RenderModel plus the display Map from `displayBoxes()` (the renderer never computes
  offsets); the drawing buffer is capped (`dprCap = 2`, and on phones also at most 1,000,000 pixels: D4).

## 13. `package3d.js`: the page controller

```js
import { DEMO, setupTrust, fetchReplayBytes, verifyReplayFile, createLiveFeed, modeNow, runStatusOf } from "../package/source.mjs";
                                                       // source.mjs:20, :35, :135, :126, :205, :179, :184
import { sceneAt, runFrame } from "../package/scene.mjs"; // scene.mjs:540, :221
import { reconcile } from "../package/playhead.mjs";      // playhead.mjs:43
import { evaluatorIds } from "../../temperature-label.mjs"; // temperature-label.mjs:127
import { tempNode, needsNotice, NOTICE, legendLabel, patternFor } from "./temps.mjs";
import { readAnatomy, readAssembly } from "./anatomy.mjs";
import { readModelStack, readLayouts, fixtureFor, standsForIndex } from "./modelstack.mjs";
import { resultView } from "./results.mjs";
import { buildRenderModel } from "./model.mjs";
import { displayBoxes } from "./view.mjs";
import { sectionAt } from "./section.mjs";
import { overlayFor } from "./flows.mjs";
import { twinOf, twinJsonText } from "./twin.mjs";
import { PINS } from "./pins.mjs";

// 1. Static data: fetch data/*.json (same origin), check sha256 against PINS when crypto.subtle exists; without it,
//    draw Anatomy and Model with the chip "file check unavailable here (needs a secure connection)" (D14).
// 2. Mode switch: dispose the renderer's GL objects and the field feed, rebuild ONE RenderModel for the new kind (X1).
// 3. Results: exactly the Package view's trust and adapter path (package.js:644-660): no crypto.subtle -> nothing drawn;
//    setupTrust(); the demo replay by default, ?src=live for live; every verification change -> reconcile()
//    (playhead.mjs:43-56), resultView(), field feed adopt() (when enabled), rebuild the result RenderModel.
// 4. Notice: needsNotice(v.prefixEnvelopes) as package.js:297-300; the slot is the exact existing markup.
// 5. Header: modeNow()/liveModeOf() only; refreshed every second on the client clock as package.js:637.
// 6. Every temperature through tempNode(h, v.value, label) with label = resolveValueLabel(v, { verified:
//    ids.get(v.measurement.node) ?? null }).label (temps.mjs R2-R5; a mismatch refuses the value); every quantity
//    through describeQuantity(); never toFixed() elsewhere.
// 7. WebGL2 available -> lazy import("./render3d.mjs") after the first model is built; else fallback2d. Context lost ->
//    fallback2d at once; restored -> rebuild from the cached model and texels (no refetch, no re-verify).
// 7b. The figure (SPEC.md §6.5): the chips, the legend and the source line are DOM children of figure#p3d-figure,
//    positioned inside its box; any image of the view is of the figure; no module of the room calls toDataURL or
//    toBlob (no canvas-only export).
// 8. Read-only test hook, as package.js:662:
Object.defineProperty(window, "__package3d", { value: Object.freeze({ facts: () => ({
  kind: S.kind, seq: S.result?.prefix.at_seq ?? 0, mode: S.result?.prefix.mode ?? null, shown: S.shownIds(),
  chips: S.chipTexts(), values: S.valueTexts(), labelStates: S.labelStates(), fieldAsOf: S.field?.as_of_seq ?? null,
  drawCalls: S.stats.calls, triangles: S.stats.triangles, glObjects: S.stats.glObjects, fallback: S.fallback,
  figure: S.figureFacts(),                             // { rect, chips, legend, source }: the figure's DOM texts and boxes (AC-05)
  geometryKey: S.model?.geometry_key ?? null }) }) });
```

## 14. Python: `sundai_hotspot/test_package3d_model_stack.py`

```python
# Checks web/public/sentilab/package3d/data/model-stack.json against the generator, for every fixture in it.
# Runs TAP's floorplan writer only (PassiveInterposer.gen_flp, sundai_tap/passive_interposer.py:20-165); a process spy
# asserts that no HotSpot binary is executed (sundai_hotspot/tap_oracle.py:39 names it).
def test_layers_match_generator(tmp_path):
    for fixture in manifest["fixtures"]:
        layout = raw_reference_centres(fixture)                       # docs/sentilab/references/*.json, raw section
        files = write_floorplans(fixture["config"]["path"], layout, tmp_path)   # gen_flp into tmp_path; no solver
        lcf = parse_lcf(files["samplelayers.lcf"])                    # 6 layers: thickness, resistivity, heat capacity
        assert_layers_equal(manifest["layers"][:6], lcf, rel=1e-12)
        units = parse_flp(files["sampleL4_ChipLayer.flp"])            # Chiplet_i, Ubump_i (halos), Edge_i, fill
        assert_halos_equal(fixture["dies"], units)                     # halo_mm per die from Ubump widths
        cfg = parse_config(files["new_hotspot.config"])               # s_spreader, s_sink, r_convec rewritten
        assert cfg["s_spreader"] == 2 * fixture["interposer_mm"] / 1000 and cfg["s_sink"] == 2 * cfg["s_spreader"]
        assert cfg["model_secondary"] == 0                             # bottom adiabatic (sundai_tap/util/hotspot.config:48)
        want = fixture["expected_inputs"]                             # what run_inputs_verified compares (SPEC.md §5.4, §5.6)
        assert sha256(files["samplelayers.lcf"]) == want["samplelayers.lcf"] and sha256(files["new_hotspot.config"]) == want["new_hotspot.config"]
        assert want["solver_flags"] == {"-model_type": "grid", "-detailed_3D": "on", "-grid_map_mode": "max"}   # tap_oracle_worker.py:362-369
    assert sha256(config_bytes) == fixture["config"]["sha256"]        # the pinned config files
```

## 15. Test files and what they cover

| File | Covers |
|---|---|
| `web/test/package3d-quantity.test.mjs` | AC-10, AC-13 (lengths), AC-14 (grammar) |
| `web/test/package3d-data.test.mjs` | AC-03, AC-08, AC-11 (data side), AC-16 (Node side: pins), AC-17, AC-29, AC-30, AC-40; `scripts/package3d.mjs check` |
| `web/test/package3d-model.test.mjs` | AC-08, AC-11 (undrawn parts: bounds, pick, section), AC-12, AC-13, AC-15 |
| `web/test/package3d-labels.test.mjs` | AC-01, AC-02, AC-05 (static: no `toDataURL`/`toBlob`), AC-06, AC-07 |
| `web/test/package3d-results.test.mjs` | AC-18, AC-19, AC-23, AC-24, AC-25, AC-26, AC-41 (driving source.mjs's poller with injected fetch, as the Package view's live tests do) |
| `web/test/package3d-field.test.mjs` | AC-20, AC-21, AC-22, AC-41 (association) |
| `web/test/package3d-twin.test.mjs` | AC-06 (result → JSON bytes → `readTwin` → markdown, and every altered identity, state and text), AC-36, AC-37 |
| existing `worker-csp.test.mjs`, `worker-boot.mjs`, `temperature-label.test.mjs`, `public-names.test.mjs`, `control-bytes.test.mjs` | AC-27, AC-28 (the page added to their lists) |
| `sundai_hotspot/test_package3d_model_stack.py` | AC-16 |
| `scripts/package3d-browser-check.mjs` (manual or a later CI job; needs Playwright) | AC-04, AC-05, AC-09, AC-11, AC-12, AC-27, AC-31 to AC-35 |
