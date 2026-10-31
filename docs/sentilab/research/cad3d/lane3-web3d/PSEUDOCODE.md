# Package 3D: module pseudocode

Lane 3 (web 3D + live simulation). Companion to ARCHITECTURE.md. Grounded in `origin/main` at
`46791be360555d0e24b4ad5f906abafb71f07118` (verbatim excerpts: `evidence/repo-01-code-excerpts-46791be.md`).

This is pseudocode for review. Nothing here is implemented or pushed. It follows the house style of
`web/public/sentilab/package/*.mjs`: plain ES modules, named exports, pure functions over plain objects,
`Object.freeze` constants, `{ ok, ... } | { ok: false, error }` results, refusals listed rather than drawn,
and DOM text through `textContent` / the CSSOM only (package.js:22-35).

## 0. Files and who may import what

```
web/public/sentilab/package3d/
  index.html        page shell (notice slot, legend, canvas, part list, fallback slot); no inline code
  package3d.js      page controller (the only module that touches the DOM broadly)
  model.mjs         PURE  parts.json + verified scene + solver stack -> RenderModel
  explode.mjs       PURE  offsets(t);  + a tiny animation driver
  section.mjs       PURE  sectionAt(model, plane) -> rectangles (3D caps AND the 2D fallback)
  interconnect.mjs  PURE  instanced arrays (sampled), highlight sets
  field.mjs         PURE  field refs from the prefix, artifact checks, scale, texels
  temps.mjs         PURE  the label-rule binding (wraps ../../temperature-label.mjs)
  stream.mjs        live/replay client for field artifacts (fetch injectable, Node-testable)
  twin.mjs          PURE  RenderModel -> agent JSON
  labels.mjs        DOM   label layer (CSSOM transforms), uses PURE cullLabels()
  fallback2d.mjs    DOM   SVG cross-section from section.mjs
  mat4.mjs          PURE  perspective, lookAt, multiply, invert, project/unproject (column-major Float32Array)
  camera.mjs        PURE  orbit state + pointer/touch/keyboard reducers (the DOM wiring is 30 lines in render3d)
  gl.mjs            WebGL2 helpers: context, programs, buffers, RGBA8 textures, context-loss rebuild
  shaders.mjs       GLSL ES 3.00 sources as strings (compiled by WebGL, never by JavaScript eval)
  render3d.mjs      the renderer: draws a RenderModel; the ONLY module that talks to WebGL
scripts/
  sentilab-scene.mjs  gains `export3d` (CLI half of SLAB-026's CLI+MCP; sentilab-scene.mjs:6-7)
  lib/glb.mjs         dependency-free, deterministic GLB writer (Node only)
```

Recommended stack (ARCHITECTURE.md section 2): our own WebGL2 renderer, the 3D sibling of the hand-written
Canvas 2D renderer (render.mjs:1-9). No third-party runtime code. Appendix A shows the drop-in three.js adapter
if the reviewers choose the library instead; only `render3d.mjs` (and its helpers) would change.

Import rules (enforced by a static test, see ACCEPTANCE.md A-12):

- PURE modules import only other PURE modules, `../package/scene.mjs`, `../package/playhead.mjs`,
  `../evidence-projection.mjs`, `../lab-model.mjs`, `../view-core.mjs` (hash/caps helpers) and
  `../../temperature-label.mjs`. No DOM, no clock, no randomness, no WebGL.
- Only `render3d.mjs` and `gl.mjs` touch WebGL. (Under the three.js alternative: only `render3d.mjs` imports the
  vendored copy, by a relative path; no bare `"three"` specifier, because an import map would need an inline
  script, which the CSP refuses; csp.js:7.)
- Only `temps.mjs` formats a temperature as text. Nothing else may call `toFixed` on a temperature or write
  `°C` (static test).
- `package3d.js` gets verified data only through `../package/source.mjs` (the Package view's one adapter,
  source.mjs:1-12) and never computes status itself (VIEW-ENVELOPE v0.5 rule 1).

## 1. Scene loader: `model.mjs` (parts.json -> RenderModel)

Assumed input (the anatomy lane owns the real schema; open questions in ARCHITECTURE.md section 12):

```
parts.json = {
  schema: "sentilab-parts/0.1", units: "mm" | "µm" | "m", frame: "lower-left-mm, z up",
  parts: [{
    id, name, parent,                 // parent: another part id, or "package"
    stack_order,                      // integer; same parent + same stack_order = side by side
    thickness,                        // in `units`
    lateral: { w, h } | { fit: "interposer" | "substrate", margin } | { from: "evidence" },
    material: { name, k_W_mK?, cp_J_m3K?, source? },
    connects_to: [{ to, via?, kind }], // kind: "c4" | "ubump" | "tsv" | "rdl" | "bga" | "tim" | "bond"
    kind: "layer" | "die" | "hbm" | "array" | "lid" | "sink" | "fill",
    array?: { pitch, diameter, height, count?, region },   // interconnect arrays, parametric
    solver_layer?: 0..15 | null,      // which solver layer this part is lumped into; null = not modelled
    source: "<citation for nominal values>"
  }]
}
```

```js
// model.mjs (PURE)
import { readGeometry, SUPPORTED_UNITS, BOUNDS, STACK } from "../package/scene.mjs";

export const MODEL_VERSION = "sentilab-model3d/0.1";
// Every number in the model carries where it came from. The info panel prints the tag beside each value.
export const PROVENANCE = Object.freeze({
  evidence: "from a verified envelope (values.geometry, J, centre temperatures)",
  solver: "from a solver artifact whose hash a verified envelope signs",
  nominal: "nominal value from the parts list, with its citation",
  schematic: "drawing constant (spacing, minimum visible thickness, colours)",
});
export const DRAW = Object.freeze({          // schematic constants, declared on screen
  min_visible_mm: 0.25,                      // thinner layers are thickened, and the view says so
  explode_gap_frac: 0.18,                    // gap per level, as a fraction of the model's lateral span
  hbm_inner_gap_frac: 0.04,
});
const LENGTH_TO_MM = Object.freeze({ mm: 1, m: 1000, "µm": 1e-3, "μm": 1e-3, um: 1e-3 });

// All or nothing, like scene.mjs readGeometry (scene.mjs:105-132): one bad part refuses the whole list,
// because a package missing a part is a picture that never existed.
export function readParts(json) {
  if (!isObj(json) || json.schema !== "sentilab-parts/0.1") return refuse("schema", "not sentilab-parts/0.1");
  const k = LENGTH_TO_MM[json.units];
  if (!k) return refuse("unit_not_supported", `length unit ${json.units}`);
  const ids = new Set(); const parts = [];
  for (const p of json.parts ?? []) {
    if (typeof p?.id !== "string" || ids.has(p.id)) return refuse("malformed", `part id ${p?.id}`);
    if (!Number.isInteger(p.stack_order) || !(p.thickness > 0)) return refuse("malformed", `${p.id}: stack_order/thickness`);
    const t = p.thickness * k;
    if (!(t > 0 && t <= BOUNDS.size_mm.max)) return refuse("out_of_range", `${p.id}: thickness ${t} mm`);
    // Chiplet footprints come ONLY from verified evidence: a die or HBM template with its own lateral size
    // is refused, so the parts list can never move or resize a chiplet the evidence placed.
    if ((p.kind === "die" || p.kind === "hbm") && p.lateral?.from !== "evidence") return refuse("malformed", `${p.id}: chiplet footprint must come from evidence`);
    // lateral: explicit (nominal), fitted to another part (nominal rule), or from evidence (chiplets)
    parts.push(Object.freeze({ ...normalise(p, k), provenance: p.lateral?.from === "evidence" ? "evidence" : "nominal" }));
    ids.add(p.id);
  }
  for (const p of parts) for (const c of p.connects_to) if (!ids.has(c.to) || (c.via && !ids.has(c.via))) return refuse("malformed", `${p.id}: connects_to ${c.to}`);
  if (hasParentCycle(parts)) return refuse("malformed", "parent cycle");
  return { parts: Object.freeze(parts), error: null };
}

// stack: the solver's layer table from a verified field artifact (field.mjs checkFieldArtifact), or null.
// layout: one track's layout from the verified scene (scene.mjs buildScene: chiplets with x, y, w, h, temp).
export function buildModel({ parts, layout, footprint, stack = null }) {
  const errors = [];
  // 1. Chiplets: footprints ONLY from the verified layout (evidence). The template part (kind "die" / "hbm",
  //    lateral.from "evidence") gives thickness and material; HBM by the scene's id rule (scene.mjs isHbm).
  const dies = (layout?.chiplets ?? []).map((c) => box({
    id: c.id, kind: /^hbm/i.test(c.id) ? "hbm" : "die",
    x0: c.x, y0: c.y, x1: c.x + c.w, y1: c.y + c.h,
    xy: "evidence", template: templateFor(parts, c.id),
  }));
  // 2. Layers fitted to the footprint (scene.mjs runFrame footprint: interposer, substrate) or explicit.
  // 3. Thickness: the solver layer's thickness when the part maps to a solver layer AND a verified stack is
  //    present (provenance "solver"); else the part's nominal thickness ("nominal").
  // 4. Levels: group by (parent, stack_order); assembled z0 of a level = max z1 of the level below.
  // 5. Display thickness = max(true, DRAW.min_visible_mm); record `thickened: true` where clamped.
  // 6. Arrays (bumps, TSVs, balls) stay parametric here; interconnect.mjs samples them.
  const levels = levelsOf(parts, dies);
  const boxes = placeLevels(levels, { stack, footprint, errors });
  return Object.freeze({
    v: MODEL_VERSION,
    units: "mm", frame: "lower-left-mm, z up",
    boxes,                                    // [{ id, kind, level, parent, x0,y0,x1,y1, z0,z1, z0_true,z1_true, thickened, prov: {xy, z, material}, solver_layer }]
    arrays: arraysOf(parts, boxes),           // parametric interconnect arrays
    links: linksOf(parts),                    // typed connects_to edges
    levels: levels.map((l) => l.key),         // explode order, bottom to top
    bounds: boundsOf(boxes),
    notes: notesOf(boxes),                    // e.g. "thin layers thickened for visibility" when any clamp is active
    errors,
  });
}
```

## 2. Explode controller: `explode.mjs`

```js
// PURE: the offset of every box at explode amount t in [0, 1]. Level k moves up by t * gap * k; parts in an
// HBM stack also separate internally. Spacing is schematic and the view labels it "exploded; spacing not to
// scale". Nothing about t is evidence, so t never comes from data.
export function explodedZ(model, t) {
  const gap = DRAW.explode_gap_frac * Math.max(model.bounds.x1 - model.bounds.x0, model.bounds.y1 - model.bounds.y0);
  const out = new Map();
  for (const b of model.boxes) {
    const k = model.levels.indexOf(b.level);
    const inner = b.parent_kind === "hbm" ? t * DRAW.hbm_inner_gap_frac * gap * b.inner_index : 0;
    out.set(b.id, t * gap * k + inner);
  }
  return out;
}

// Driver: eases t toward a target over 600 ms (render.mjs easeInOut), or jumps when reduced motion is on.
// It only asks for frames while moving (render on demand, as package.js requestDraw does: package.js:235-237).
export function createExplodeController({ reduced, onFrame, now = () => performance.now() }) {
  let from = 0, to = 0, start = 0, raf = 0;
  const value = (ms) => (reduced || from === to ? to : from + (to - from) * easeInOut(Math.min(1, (ms - start) / 600)));
  const tick = () => { raf = 0; const v = value(now()); onFrame(v); if (v !== to) raf = requestAnimationFrame(tick); };
  return {
    set(target) { from = value(now()); to = clamp01(target); start = now(); if (!raf) raf = requestAnimationFrame(tick); },
    get: () => value(now()),
  };
}
```

## 3. Section planes: `section.mjs` (shared by the 3D cutaway and the 2D fallback)

```js
// PURE. Every part is an axis-aligned box, so a section by an axis-aligned plane is exact: each box the plane
// crosses gives one rectangle (the other horizontal extent x [z0, z1]). The 3D view draws these as flat caps
// on the cut; the no-WebGL fallback draws the very same rectangles as SVG. One function, two outputs, so they
// can't disagree.
export function sectionAt(model, { axis /* "x" | "y" */, at /* mm */, explodeZ = null }) {
  const rects = [];
  for (const b of model.boxes) {
    const [lo, hi] = axis === "x" ? [b.x0, b.x1] : [b.y0, b.y1];
    if (!(at >= lo && at <= hi)) continue;
    const [u0, u1] = axis === "x" ? [b.y0, b.y1] : [b.x0, b.x1];
    const dz = explodeZ?.get(b.id) ?? 0;
    rects.push({ id: b.id, kind: b.kind, u0, u1, z0: b.z0 + dz, z1: b.z1 + dz, thickened: b.thickened, prov: b.prov });
  }
  // Arrays crossing the plane: the bump columns the plane actually cuts (from pitch and region), not a texture.
  return { axis, at, rects: rects.sort(byZThenU), arrays: arrayCuts(model, axis, at) };
}
```

## 4. Interconnect overlay: `interconnect.mjs`

```js
// PURE. Bumps, TSVs and balls are drawn as instances of one low-poly mesh per array. Real microbump counts can
// be hundreds of thousands; a phone can't draw them and a viewer can't read them. So arrays are SAMPLED on a
// regular lattice (every k-th site in both directions), deterministically, and the view always says
// "1 of k^2 sites drawn; count N (nominal)". The sampled count respects the budget.
export const BUDGET = Object.freeze({ phone: 6000, desktop: 60000 });

export function interconnectArrays(model, { budget }) {
  const out = [];
  let left = budget;
  for (const [i, a] of model.arrays.entries()) {
    const sites = latticeSites(a);                 // from pitch and region; count = a.count ?? sites.length
    const share = Math.max(1, Math.floor(left / (model.arrays.length - i)));   // even split of what's left
    const k = Math.max(1, Math.ceil(Math.sqrt(sites.length / share)));         // every k-th row and column
    const drawn = sites.filter((s) => s.i % k === 0 && s.j % k === 0);
    left -= drawn.length;
    out.push({ id: a.id, kind: a.kind, via_of: a.via_of, radius: a.diameter / 2, height: a.height,
      z0: a.z0, positions: drawn.map((s) => [s.x, s.y]), sampled_every: k, count: a.count ?? sites.length,
      count_prov: a.count != null ? "nominal" : "derived from pitch and region" });
  }
  return out;
}

// What lights up when a part is picked: the part, every part it connects to, and the interconnect between.
export function highlightSet(model, partId) {
  const ids = new Set([partId]);
  for (const l of model.links) {
    if (l.from === partId || l.to === partId) { ids.add(l.from); ids.add(l.to); if (l.via) ids.add(l.via); }
  }
  return ids;
}

// PURE picking: a camera ray against axis-aligned boxes (slab test) and sampled array sites. Exact for this
// geometry, testable in node, and independent of the renderer.
export function pick(model, { origin, dir }, explodeZ) { /* nearest positive t over boxes, then arrays */ }
```

## 5. Label-rule binding: `temps.mjs`

```js
// The ONE place a temperature becomes text in the 3D view. It wraps the site's one label rule
// (temperature-label.mjs) and refuses to format a value without a label produced by that rule.
import { LABELS, labelFor, labelForAll, evaluatorIds, envelopeEvaluator, needsNotice, NOTICE } from "../../temperature-label.mjs";

const RULE_LABELS = new Set(Object.values(LABELS));          // identity, not shape: a look-alike object fails

// A field's label comes from the verified ENVELOPE's semantics.evaluator_version, never from the artifact's
// own claim (field.mjs refuses a mismatch before this is called).
export const fieldLabel = (measurementEnv, ids) => labelFor(envelopeEvaluator(measurementEnv, ids));
// The legend is an axis: derived from every value that set the scale (temperature-label.mjs:17-19).
export const legendLabel = (identities) => labelForAll(identities);

// valueC: a finite number in °C (already converted by scene.mjs rules). label: one of LABELS.
// Returns { text, qualifier, title, state } for one DOM unit; there is no way to get the number alone.
export function formatTemp(valueC, label, { digits = 1 } = {}) {
  if (!RULE_LABELS.has(label)) throw new TypeError("a temperature needs its label (temperature-label.mjs)");
  if (typeof valueC !== "number" || !Number.isFinite(valueC)) throw new TypeError("not a finite temperature");
  return Object.freeze({ text: `${valueC.toFixed(digits)} °C`, qualifier: label.short, title: label.title, state: label.state });
}

// DOM unit: value and qualifier in ONE element, so no layout, crop or copy can separate them.
export function tempNode(h, valueC, label) {
  const t = formatTemp(valueC, label);
  return h("span", { class: `t s-${t.state}`, title: t.title }, t.text, " ", h("em", { class: "q" }, t.qualifier));
}

// Pixel-level state, for screenshots that crop the DOM away: withdrawn fields are hatched, unvalidated
// fields are stippled, illustrative and accepted are plain. The shader reads this uniform.
export const PATTERN = Object.freeze({ withdrawn: 2, unvalidated: 1, illustrative: 0, accepted: 0 });
export const patternFor = (label) => PATTERN[label.state] ?? PATTERN.unvalidated;

// The page notice: the prefix's own rule (package.js:280-283), plus envelopes that carry a field. NOTE:
// temperature-label.mjs hasTemperature() checks only J and center_temps; a measurement that carried only
// values.field would be missed. That module must learn values.field (with a test) before fields ship.
export const pageNotice = (prefixEnvelopes) => needsNotice(prefixEnvelopes);
export { NOTICE };
```

## 6. Thermal field: `field.mjs` (refs, artifact checks, scale, texels) and the texture updater

Proposed artifact (`sentilab-field/0.1`, produced by the core from HotSpot's grid output; see ARCHITECTURE.md
section 5). The envelope that signs it carries a small typed pointer:
`values.field = { sha256, format: "sentilab-field/0.1", rows, cols, layers, unit }`.

```js
// field.mjs (PURE except checkFieldArtifact's hashing, which uses WebCrypto via view-core.mjs sha256Hex)
import { sha256Hex } from "../view-core.mjs";
import { heatColor, BOUNDS } from "../package/scene.mjs";

export const FIELD_FORMAT = "sentilab-field/0.1";
export const FIELD_CAPS = Object.freeze({ max_bytes: 4 * 1024 * 1024, max_rows: 128, max_cols: 128, max_layers: 16 });
const HEX64 = /^[0-9a-f]{64}$/;

// The allowlist: ONLY fields named by measurement node.create envelopes inside the verified projectable
// prefix, that project() applied. Nothing after K, nothing rejected, nothing from a file's manifest.
export function fieldRefs(prefixEnvelopes, projection) {
  const rejected = new Set((projection?.rejected ?? []).map((r) => r.event_id));
  const refs = new Map();                                      // sha256 -> ref
  for (const env of prefixEnvelopes) {
    const { type, body, seq, event_id } = env.event;
    if (type !== "node.create" || body?.kind !== "measurement" || rejected.has(event_id)) continue;
    const f = env.values?.field;
    if (!isObj(f) || !HEX64.test(f.sha256) || f.format !== FIELD_FORMAT) continue;
    refs.set(f.sha256, Object.freeze({ sha256: f.sha256, seq, measurement: body.id, run_id: env.run.run_id,
      evaluator: body.semantics?.evaluator_version, rows: f.rows, cols: f.cols, layers: f.layers, unit: f.unit, env }));
  }
  return refs;
}

// bytes: the raw artifact body (already capped by readBodyCapped). ref: from fieldRefs. In this order, and
// nothing is decoded before the hash matches:
//   1 size cap; 2 sha256(bytes) === ref.sha256; 3 strict UTF-8 + JSON (runs-list.mjs strictJson);
//   4 format; 5 binding equals the ENVELOPE (run_id, measurement, evaluator_version); 6 dims equal the
//   envelope's pointer and the caps; 7 every value finite, unit supported, inside BOUNDS after conversion;
//   8 layer table well-formed (index, name, thickness_m > 0). Any failure: { ok: false, error }, nothing drawn.
export async function checkFieldArtifact(bytes, ref) {
  if (!(bytes instanceof Uint8Array) || bytes.length > FIELD_CAPS.max_bytes) return no("too_large");
  if ((await sha256Hex(bytes)) !== ref.sha256) return no("hash_mismatch");
  let doc; try { doc = strictJson(bytes); } catch { return no("malformed"); }
  if (doc?.format !== FIELD_FORMAT) return no("format");
  const b = doc.binding ?? {};
  if (b.run_id !== ref.run_id || b.measurement !== ref.measurement || b.evaluator_version !== ref.evaluator) return no("binding_mismatch");
  const { rows, cols } = doc.grid ?? {};
  if (rows !== ref.rows || cols !== ref.cols || doc.layers?.length !== ref.layers || doc.values?.length !== ref.layers) return no("dims");
  if (rows > FIELD_CAPS.max_rows || cols > FIELD_CAPS.max_cols || ref.layers > FIELD_CAPS.max_layers) return no("dims");
  const toC = doc.unit === "K" ? (v) => v - 273.15 : doc.unit === "°C" || doc.unit === "C" ? (v) => v : null;
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
  return { ok: true, field: Object.freeze({ ref, grid: { rows, cols, extent_mm: doc.grid.extent_mm, row0: doc.grid.row0 }, layers }) };
}

// One fixed scale per run over every accepted field value (all layers), rounded out to 5 degrees and at
// least 10 wide: scene.mjs runFrame's rule (scene.mjs:226-229). A live run only widens it (playhead.mjs
// widenFrame). It is never rescaled per frame.
export function fieldScale(fields) { /* min/max over field.layers[].c; same rounding as runFrame */ }

// The colour table for one scale, built from the SAME function the 2D views and the legend use (scene.mjs
// heatColor) at each bin centre. Built once per scale (the scale is fixed per run and only widens live).
// Calling heatColor() per cell is far too slow for fields (about 45 ms for 8 x 32 x 32 on a desktop: it re-parses
// its stops every call); the table maps 8 x 64 x 64 in about 0.2 ms and stays within 1/255 per channel of
// heatColor() (evidence/extra-05). A node test pins that bound.
export const LUT_BINS = 1024;
export function colourLut(scale) {
  const lut = new Uint8Array(LUT_BINS * 4);
  for (let i = 0; i < LUT_BINS; i += 1) {
    const t = scale.min + ((i + 0.5) / LUT_BINS) * (scale.max - scale.min);
    lut.set([...rgb(heatColor(t, scale)), 255], i * 4);
  }
  return Object.freeze({ scale, lut });
}

// RGBA8 texels for one layer, row order as declared by the artifact (grid.row0). The bytes are what the GPU
// shows, so a node test can check them directly. Nearest filtering only: one flat colour per solver cell, no
// interpolation, so the grid's real resolution stays visible (requirement V13). Values outside the scale clamp
// to its ends, as heatColor() does.
export function fieldTexels(field, layerIndex, { scale, lut }) {
  const { rows, cols, row0 } = field.grid;
  const out = new Uint8Array(rows * cols * 4);
  const c = field.layers[layerIndex].c;
  const k = LUT_BINS / (scale.max - scale.min);
  for (let r = 0; r < rows; r += 1) for (let q = 0; q < cols; q += 1) {
    const src = (row0 === "top" ? rows - 1 - r : r) * cols + q;     // texture row 0 = lowest y (lower-left frame)
    const b = Math.min(LUT_BINS - 1, Math.max(0, Math.floor((c[src] - scale.min) * k)));
    out.set(lut.subarray(b * 4, b * 4 + 4), (r * cols + q) * 4);
  }
  return out;
}
```

Texture updater (in `gl.mjs` / `render3d.mjs`):

```js
// One RGBA8 texture per solver layer, NEAREST filtering, no mipmaps. RGBA8 needs no float-texture or
// float-filtering extension, so every WebGL2 device shows the same thing, and the bytes are exactly the
// texels a node test already checked. The colours are sRGB values written straight to an sRGB canvas by an
// unlit shader, so the pixel equals the legend's colour (no lighting, no tone mapping, no colour conversion).
export function createFieldTextures(gl, requestRender) {
  const slots = new Map();                                   // layer -> { tex, rows, cols }
  return {
    set(layer, texels, rows, cols) {
      let s = slots.get(layer);
      if (!s || s.rows !== rows || s.cols !== cols) {
        if (s) gl.deleteTexture(s.tex);
        const tex = gl.createTexture();
        gl.bindTexture(gl.TEXTURE_2D, tex);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
        gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
        gl.texStorage2D(gl.TEXTURE_2D, 1, gl.RGBA8, cols, rows);  // immutable storage, one level
        s = { tex, rows, cols }; slots.set(layer, s);
      }
      gl.bindTexture(gl.TEXTURE_2D, s.tex);
      gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, 0, cols, rows, gl.RGBA, gl.UNSIGNED_BYTE, texels);
      requestRender();
    },
    clear(layer) { const s = slots.get(layer); if (s) gl.deleteTexture(s.tex); slots.delete(layer); requestRender(); },
    // After webglcontextrestored every GL object is gone: the renderer calls set() again from the cached,
    // already-checked texels. Nothing is refetched or re-verified to redraw.
    drop() { slots.clear(); },
  };
}
```

Field-sheet fragment shader (in `shaders.mjs`; GLSL ES 3.00, compiled by WebGL, not by JavaScript):

```glsl
#version 300 es
precision highp float;
uniform sampler2D uField;       // RGBA8, NEAREST: one flat colour per solver cell
uniform int uPattern;           // temps.mjs patternFor(label): 0 none, 1 stipple (unvalidated), 2 hatch (withdrawn)
uniform vec4 uClip;             // section plane (xyz normal, w offset); w = 1e9 when off
in vec2 vUv; in vec3 vWorld;
out vec4 color;
void main() {
  if (dot(uClip.xyz, vWorld) > uClip.w) discard;            // cutaway
  vec3 c = texture(uField, vUv).rgb;                          // unlit: the legend's colour, unchanged
  vec2 p = gl_FragCoord.xy;                                   // screen space, so the pattern survives any zoom
  if (uPattern == 2 && mod(p.x + p.y, 10.0) < 2.0) c = vec3(0.06);            // hatch: withdrawn
  if (uPattern == 1 && mod(p.x, 8.0) < 1.5 && mod(p.y, 8.0) < 1.5) c = vec3(0.06);  // stipple: unvalidated
  color = vec4(c, 1.0);
}
```

## 7. Playback / stream client: `stream.mjs`

```js
// Fields for the playhead, from replay or live, with reconnect and backpressure. The envelope feed itself is
// the Package view's (source.mjs createLiveFeed: 1 s polls, 16 pages a poll, 5 s back-off, terminal states,
// pauses while the tab is hidden; source.mjs:190-258). This module only fetches the ARTIFACTS that the
// verified prefix names, and never decides LIVE/STALE: the label is source.mjs liveModeOf().
import { readBodyCapped } from "../view-core.mjs";
import { fieldRefs, checkFieldArtifact, FIELD_CAPS } from "./field.mjs";

export function createFieldFeed({ fetchImpl = (...a) => fetch(...a), onChange = () => {}, now = () => Date.now(),
                                   artifactUrl = (h) => `/api/view/artifacts/${h}`, maxInFlight = 2, cacheBytes = 32 << 20 }) {
  let allow = new Map();               // sha256 -> ref, rebuilt on every verification change
  const cache = new Map();             // sha256 -> { field } | { error }, LRU by insertion; immutable content
  const inflight = new Map();          // sha256 -> AbortController
  const retry = new Map();             // sha256 -> { attempts, at }
  let want = null;                     // the sha256 the playhead needs now (latest wins)

  // Every verification change (poll, replay load, K drop) goes through here, like playhead.mjs reconcile().
  function adopt(verification) {
    allow = fieldRefs(verification.prefixEnvelopes, verification.projection);
    for (const [h, ctl] of inflight) if (!allow.has(h)) { ctl.abort(); inflight.delete(h); }   // left the prefix
    for (const h of cache.keys()) if (!allow.has(h)) cache.delete(h);                         // K dropped: forget it
    onChange();
  }

  // The field to show at seq: the ref attached to the measurement that metricFor() picks for the shown layout's
  // J (the scene already carries it: layout.metric.measurement, with layout.metric.state "valid" | "stale").
  // A stale pick is still shown, desaturated and tagged STALE, as the 2D view does (render.mjs:8).
  function request(seq, pickRef) {
    const ref = pickRef(allow, seq);                    // pure chooser: (allow, seq) -> ref | null
    want = ref?.sha256 ?? null;
    if (!want || cache.has(want) || inflight.has(want)) return status(ref);
    pump();
    return status(ref);
  }

  // Backpressure: at most maxInFlight fetches; while following the live edge only `want` and the next newer ref
  // are fetched (intermediate frames are skipped and stay reachable in replay); a playhead move aborts fetches
  // nobody wants any more.
  function pump() {
    for (const [h, ctl] of inflight) if (h !== want) { ctl.abort(); inflight.delete(h); }
    if (!want || inflight.size >= maxInFlight || cache.has(want)) return;
    const r = retry.get(want);
    if (r && now() < r.at) return void setTimeout(pump, r.at - now());
    fetchOne(want);
  }

  async function fetchOne(h) {
    const ref = allow.get(h); if (!ref) return;          // never fetch a hash the prefix doesn't name
    const ctl = new AbortController(); inflight.set(h, ctl);
    try {
      const res = await fetchImpl(artifactUrl(h), { signal: ctl.signal, cache: "force-cache" });   // immutable
      if (res.status !== 200) throw new Error(`http_${res.status}`);
      const body = await readBodyCapped(res, FIELD_CAPS.max_bytes, "too_large");
      if (!body.ok) throw new Error(body.reason);
      const checked = await checkFieldArtifact(body.bytes, ref);
      cache.set(h, checked.ok ? { field: checked.field } : { error: checked.error });   // a refusal is cached too
      retry.delete(h);
    } catch (e) {
      if (ctl.signal.aborted) return;
      // Transport problems retry with back-off (1, 2, 4 ... 30 s, 5 attempts), then "field unavailable".
      const n = (retry.get(h)?.attempts ?? 0) + 1;
      retry.set(h, { attempts: n, at: now() + Math.min(30_000, 1000 * 2 ** (n - 1)) });
      if (n >= 5) cache.set(h, { error: "unavailable" });
    } finally { inflight.delete(h); trim(); onChange(); pump(); }
  }

  // LRU by insertion order: drop the oldest checked fields until the cache's Float32 bytes fit cacheBytes. The
  // field the playhead wants is never evicted.
  function trim() { /* while (bytesOf(cache) > cacheBytes) delete the oldest key !== want */ }

  // What the page shows. A field older than the playhead is stamped "as of seq S" and never presented as current.
  function status(ref) {
    if (!ref) return { kind: "none" };
    const got = cache.get(ref.sha256);
    if (got?.field) return { kind: "field", field: got.field, asOf: ref.seq };
    if (got?.error) return { kind: "refused", error: got.error, asOf: ref.seq };
    return { kind: "loading", asOf: ref.seq };
  }
  return { adopt, request, status };
}

// Solve status for the live view, from the verified lifecycle only (evidence-projection.mjs TRANSITIONS):
//   candidate in simulation_pending and the feed LIVE        -> "solving (since seq S)"
//   candidate in simulation_pending and the feed STALE/ENDED -> "solve status unknown (feed STALE · reason)"
//   never "solving" from anything but the verified prefix plus the live label.
export function solveStatus(scene, mode /* source.mjs liveModeOf(): { mode, reason } */) { /* ... */ }

// Optional doorbell (later; needs an API route): an EventSource whose messages carry NO data the page uses. A
// message only pokes the poller (source.mjs feed.poke(), source.mjs:256). It never counts as progress, never
// changes the label, and if it errors or closes, polling simply continues at 1 s.
export function createDoorbell({ url, feed }) {
  if (typeof EventSource !== "function") return { close() {} };
  const es = new EventSource(url);
  es.addEventListener("append", () => feed.poke());
  return { close: () => es.close() };
}
```

Replay frame packs need no new signed file: the timeline is the verified prefix itself (seq -> `values.field`
refs), so a replay bundle is `<bundle>.jsonl` plus the artifacts it names (served at
`/api/replay/<bundle>/artifacts/<sha256>` or as static files), each checked by `checkFieldArtifact`.

## 8. Label layer: `labels.mjs`

```js
// Our own DOM layer (no third-party label renderer). Each label is a <div> positioned by a per-property CSSOM
// write (el.style.transform). Never cssText, insertRule or style="": CSP3 gates the first two on 'unsafe-eval'
// and the CSP refuses the third (evidence/web-06 (d)); ACCEPTANCE A-08 confirms it in a real browser.
export function createLabelLayer(container, { compact }) {
  const els = new Map();
  return {
    // items: [{ id, text, anchor: [x, y, z] (mm, exploded), priority, kind }], all strings from our model.
    // project: (xyz) -> { x, y, visible } in CSS px (render3d.project).
    update(items, project) {
      const placed = cullLabels(items.map((it) => ({ ...it, ...project(it.anchor) })).filter((p) => p.visible),
                                { max: compact ? 6 : 24, pad: 4 });       // PURE: priority order, no overlaps
      for (const [id, el] of els) if (!placed.some((p) => p.id === id)) { el.remove(); els.delete(id); }
      for (const p of placed) {
        let el = els.get(p.id);
        if (!el) { el = document.createElement("div"); el.className = `lbl3 k-${p.kind}`; el.setAttribute("aria-hidden", "true"); container.append(el); els.set(p.id, el); }
        el.textContent = p.text;                                             // text only, never innerHTML
        el.style.transform = `translate(${Math.round(p.x)}px, ${Math.round(p.y)}px)`;
      }
    },
  };
}
// Labels never carry temperature numbers; temperatures appear only in the legend, the readout and the info
// panel, through temps.mjs tempNode(). The part list (DOM buttons) is the accessible version of the labels.
```

## 9. Renderer: `render3d.mjs` + `gl.mjs` + `mat4.mjs` + `camera.mjs` (our own WebGL2)

Everything in a package is an axis-aligned box, a short cylinder (bump, TSV, ball) or a flat sheet. So the
renderer needs exactly three programs: instanced lit boxes/cylinders, unlit field sheets (above), and lines
(edges, leader lines, the section outline). All three take the same clip-plane uniform.

```js
// render3d.mjs
import { perspective, lookAt, multiply, invert, projectPoint, unprojectRay } from "./mat4.mjs";
import { orbitView } from "./camera.mjs";
import { createGl, program, staticBuffer, dynamicBuffer, createFieldTextures } from "./gl.mjs";
import { BOX_VS, LIT_FS, SHEET_VS, SHEET_FS, LINE_VS, LINE_FS } from "./shaders.mjs";

export function createRenderer3d(canvas, { dprCap = 2, onContextLost, onContextRestored }) {
  const gl = canvas.getContext("webgl2", { antialias: true, alpha: false, depth: true, powerPreference: "default" });
  if (!gl) return null;                                        // no WebGL2 -> fallback2d.mjs (section.mjs rectangles)
  let state = null;                                            // every GL object; rebuilt from `model` after a loss
  let model = null, offsets = new Map(), plane = null, highlight = new Set(), view = null, cachedTexels = new Map();
  canvas.addEventListener("webglcontextlost", (e) => { e.preventDefault(); state = null; onContextLost(); });
  canvas.addEventListener("webglcontextrestored", () => { build(); for (const [L, t] of cachedTexels) state.fields.set(L, ...t); onContextRestored(); requestRender(); });

  function build() {
    state = {
      lit: program(gl, BOX_VS, LIT_FS), sheet: program(gl, SHEET_VS, SHEET_FS), line: program(gl, LINE_VS, LINE_FS),
      unitBox: staticBuffer(gl, UNIT_BOX), unitCyl: staticBuffer(gl, unitCylinder(8)),   // 8 sides: ~32 triangles
      boxes: dynamicBuffer(gl), arrays: new Map(), fields: createFieldTextures(gl, requestRender),
    };
    if (model) upload(model);
  }
  // Per-instance attributes: translate (vec3), scale (vec3), colour (vec3), flags (highlight, dim, thickened).
  // ALL boxes of the model are ONE instanced draw; each interconnect array is one more; sheets one per layer.
  function upload(m) {
    state.boxes.set(boxInstances(m, offsets, highlight));        // PURE packer: Float32Array, testable in node
    for (const a of m.drawnArrays) state.arrays.set(a.id, dynamicBuffer(gl, arrayInstances(a, offsets)));
  }

  let queued = false;
  function requestRender() { if (queued) return; queued = true; requestAnimationFrame(frame); }   // render on demand
  function frame() {
    queued = false;
    if (!state || !model) return;
    const w = Math.round(canvas.clientWidth * Math.min(dprCap, devicePixelRatio || 1));
    const h = Math.round(canvas.clientHeight * Math.min(dprCap, devicePixelRatio || 1));
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
    gl.viewport(0, 0, w, h);
    const vp = multiply(perspective(35, w / h, view.near, view.far), lookAt(view.eye, view.target, [0, 0, 1]));
    gl.enable(gl.DEPTH_TEST); gl.clearColor(0.063, 0.098, 0.118, 1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    drawLit(vp);              // 1 call for all boxes + 1 per drawn interconnect array
    drawSheets(vp);           // 1 call per solver layer with a field, unlit, pattern by label state
    drawLines(vp);            // edges, connection leaders, section outline
    drawTransparentLid(vp);   // last, sorted, low alpha, outline: never hides the field
    stats.calls = ...; stats.triangles = ...;
  }

  return {
    setModel(m) { model = m; if (state) upload(m); requestRender(); },
    setView(v) { view = v; requestRender(); },                    // from camera.mjs orbitView(state)
    setExplode(map) { offsets = map; if (state) upload(model); requestRender(); },
    setSection(p) { plane = p; requestRender(); },               // caps come from section.mjs, drawn as lit quads
    setField(layer, texels, rows, cols) { cachedTexels.set(layer, [texels, rows, cols]); state?.fields.set(layer, texels, rows, cols); },
    clearField(layer) { cachedTexels.delete(layer); state?.fields.clear(layer); },
    setHighlight(ids) { highlight = ids; if (state) upload(model); requestRender(); },
    project: (xyz) => projectPoint(currentVp(), xyz, canvas.clientWidth, canvas.clientHeight),   // labels.mjs
    ray: (px, py) => unprojectRay(invert(currentVp()), px, py, canvas.clientWidth, canvas.clientHeight), // pick()
    stats: Object.seal({ calls: 0, triangles: 0 }),
    requestRender,
    init() { build(); return this; },
  };
}
```

```js
// camera.mjs (PURE): orbit about a target with azimuth, elevation and distance; pinch and wheel zoom; two-finger
// pan; keyboard. Reducers take the previous state and an input and return the next state, so a node test can
// replay a gesture. Elevation is clamped (no flipping under the package); reduced motion turns off inertia.
export const initialOrbit = (bounds) => ({ target: centreOf(bounds), azimuth: -45, elevation: 35.26, distance: fitDistance(bounds) });
export function onPointer(orbit, gesture /* { kind: "rotate" | "pan" | "pinch", dx, dy, scale } */) { /* ... */ }
export function onKey(orbit, key) { /* arrows rotate 15°, +/- zoom, 0 home */ }
export function orbitView(orbit) { /* -> { eye, target, near, far } */ }
```

```js
// gl.mjs: program() compiles and links GLSL from strings with the WebGL API; on failure it throws with the info
// log (a broken shader is a bug, never a blank or half-drawn scene: the page shows the 2D fallback instead).
// No JavaScript is generated or evaluated, so 'unsafe-eval' is never needed.
export function program(gl, vs, fs) { /* createShader, shaderSource, compileShader, getShaderParameter, link */ }
```

## 10. Agent JSON export: `twin.mjs` and `scripts/sentilab-scene.mjs export3d`

```js
// twin.mjs (PURE): the same RenderModel the page draws, as data. No pixels, no view-only state.
export const TWIN_VERSION = "sentilab-twin/0.1";
export function twinOf(model, { run = null, at = null, fields = [], partsSha256, labelOf }) {
  return {
    v: TWIN_VERSION,
    units: { length: "mm", temperature: "°C" }, frame: model.frame,
    provenance: PROVENANCE,                                   // what each tag means
    parts: model.boxes.map((b) => ({ id: b.id, kind: b.kind, level: b.level, parent: b.parent,
      box_mm: [b.x0, b.y0, b.z0_true, b.x1, b.y1, b.z1_true], prov: b.prov, solver_layer: b.solver_layer })),
    arrays: model.arrays.map(({ id, kind, pitch, diameter, height, count, region }) => ({ id, kind, pitch, diameter, height, count, region })),
    links: model.links,
    solver_layers: model.stack?.layers ?? null,               // thickness, resistivity, heat capacity, source hash
    evidence: { run, at, parts_sha256: partsSha256 },
    fields: fields.map((f) => ({ sha256: f.ref.sha256, measurement: f.ref.measurement, seq: f.ref.seq,
      grid: { rows: f.grid.rows, cols: f.grid.cols, extent_mm: f.grid.extent_mm },
      label: labelOf(f) /* LABELS[state].text: the twin carries the same qualifier the page shows */ })),
    notes: model.notes,
  };
}
```

```js
// scripts/sentilab-scene.mjs (new subcommand; same verifier path as `build`, sentilab-scene.mjs:1-17):
//   node scripts/sentilab-scene.mjs export3d <replay.jsonl> --parts <parts.json> --out <dir> [--at <seq>] [--artifacts <dir>] [--strict]
// Writes <dir>/twin.json (canonical JSON: sorted keys, LF) and <dir>/twin.glb (scripts/lib/glb.mjs), both
// byte-reproducible: the same inputs give the same bytes (test). Fields are included only when their artifacts
// are given AND pass checkFieldArtifact against the verified prefix.
//
// scripts/lib/glb.mjs: glTF 2.0 binary with one node per part (node.name = part id, node.extras = { prov,
// solver_layer }), positions in METRES with Y up as glTF requires, Float32 positions/normals, Uint32 indices,
// 4-byte-aligned chunks, no textures, no compression (no decoder WebAssembly needed by anyone reading it).
```

## 11. Page controller sketch: `package3d.js`

```js
import { DEMO, setupTrust, fetchReplayBytes, verifyReplayFile, createLiveFeed, modeNow, runStatusOf } from "../package/source.mjs";
import { sceneAt, runFrame } from "../package/scene.mjs";
import { reconcile } from "../package/playhead.mjs";
import { readParts, buildModel } from "./model.mjs";
import { createFieldFeed, solveStatus } from "./stream.mjs";
import { fieldTexels, fieldScale, colourLut } from "./field.mjs";
import { tempNode, fieldLabel, legendLabel, patternFor, pageNotice, NOTICE } from "./temps.mjs";

// 1. Trust and verification exactly as package.js (package.js:616-632). No WebCrypto -> nothing drawn.
// 2. parts.json: fetched from our origin, checked by readParts, its sha256 shown in the info panel.
// 3. On every verification change: reconcile() (playhead), fieldFeed.adopt(verification), rebuild the model
//    for the selected track, notice = pageNotice(prefix).
// 4. WebGL2? -> render3d (lazy import of the vendored copy); else fallback2d. Context lost -> fallback2d.
// 5. Legend: fixed field scale for the run, legendLabel(all identities behind it), ticks from scaleTicks();
//    colourLut(scale) rebuilt only when the scale changes (a live run widening it).
// 6. Live: header label from modeNow()/liveModeOf(), unchanged rules (v0.6.2 rule 5); "as of seq K" stamp on
//    the field; solveStatus() chip.
// 7. Test hook, read-only (as package.js:634): window.__package3d.facts() -> { seq, prefix, mode, fieldAsOf,
//    fieldState, drawCalls, triangles, fallback, labelStates }.
```

## Appendix A: the three.js alternative behind the same interface

Only if the reviewers choose the library (ARCHITECTURE.md section 2). Facts from `evidence/web-01` and
`evidence/extra-02`: three@0.187.0 (MIT) ships no minified builds since r186; `build/three.module.js` imports
only `./three.core.js` (relative), so the two files load without an import map; every addon imports the bare
specifier `'three'`, so addons are NOT used; `three.core.js` holds one comment that fails our public-names test.

```
web/public/vendor/three-0.187.0/
  three.module.js   sha256 104f56145899722094556490d787aae0617cc2fc3382f31df02d724ea1aee341   (byte-identical)
  three.core.js     sha256 613e370f76638fdef83926642bf256dc9615684922de1ce1f63a8583e5d78578   (byte-identical)
  LICENSE           MIT, byte-identical to the tag r187 file
  VENDOR.json       { tarball, dist.integrity, gitHead 7e89746a687bb88271253698fa108b1dd59825d0, files: { name: sha256 } }
web/test/vendor-pins.test.mjs   recompute sha256 of every vendored file; compare with VENDOR.json
web/test/public-names.test.mjs  one narrow exception: vendor/three-0.187.0/three.core.js, exactly one hit, at the
                                pinned file hash (or: a reproducible minify step that keeps the @license header)
```

```js
// render3d.mjs, three.js variant: same exported shape as section 9, so package3d.js doesn't change.
export async function createRenderer3d(canvas, { dprCap = 2, onContextLost, onContextRestored }) {
  if (!canvas.getContext("webgl2")) return null;                       // -> fallback2d.mjs
  const THREE = await import("../../vendor/three-0.187.0/three.module.js");   // lazy, after verification
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(dprCap, devicePixelRatio || 1));
  renderer.localClippingEnabled = true;                                 // section plane via material.clippingPlanes
  canvas.addEventListener("webglcontextlost", (e) => { e.preventDefault(); onContextLost(); });
  canvas.addEventListener("webglcontextrestored", () => onContextRestored());
  const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(35, 1, 0.1, 5000);
  // Boxes: one InstancedMesh(BoxGeometry, MeshLambertMaterial) with setMatrixAt / setColorAt per part.
  // Arrays: one InstancedMesh(CylinderGeometry(r, r, h, 8)) each.
  // Field sheets: PlaneGeometry + MeshBasicMaterial({ map, toneMapped: false }) with a DataTexture(texels, cols,
  //   rows, RGBAFormat, UnsignedByteType), NearestFilter, no mipmaps, colorSpace SRGBColorSpace, needsUpdate on
  //   each verified field; the hatch/stipple pattern via onBeforeCompile or a ShaderMaterial.
  // Picking stays ours (interconnect.mjs pick) so it is renderer-independent; camera stays ours (camera.mjs).
  // stats: renderer.info.render.calls / .triangles.
}
```
