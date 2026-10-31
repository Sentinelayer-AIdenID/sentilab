// SentiLab Package view: the scene model. Pure functions, no DOM, no clock, no randomness, so the same verified
// prefix gives the same scene in node (scripts/sentilab-scene.mjs) and in the browser (package.js).
//
// Input is ONLY the projectable prefix (VIEW ENVELOPE rule 1): the unbroken run of verified, non-oversize envelopes
// from seq 1, as the verifier returns it. Status (lifecycle, validity, support sets, acceptance) is never computed
// here: it is read from the contract's project() over that prefix. Geometry, temperatures, J and W are the display-only
// `values` of envelopes in the prefix that project() applied. Nothing after the prefix can move or colour anything.
//
// Everything drawn comes from our own data: chiplet footprints from values.geometry, colours from values.center_temps
// on one fixed scale per run (a run without centre temperatures draws its chiplets uncoloured; J is the measurement's
// value and never colours a chiplet), J and W from the measurement both views pick (lab-model.mjs metricFor, the
// one rule). The vertical stack (substrate, interposer, die heights, lid) is schematic: nominal
// constants below, declared as such in the scene and on screen.
import { project } from "../evidence-projection.mjs";
import { metricFor, tempUnit } from "../lab-model.mjs";

export const SCENE_VERSION = "sentilab-scene/0.1";
export const TEMP_BASIS = "chiplet-centre temperatures from the solver; not a field";

// Schematic stack. These heights are drawing constants, not measurements and not to scale. Only the chiplet
// footprints (x, y, w, h) come from the evidence. The interposer is the bounding extent of the run's geometry plus
// a margin; the substrate is the interposer plus a margin.
export const STACK = Object.freeze({
  label: "schematic stack",
  note: "Layer heights are nominal drawing constants, not from the run and not to scale. Chiplet footprints are from the evidence, to scale.",
  units: "mm",
  substrate_mm: 2.6,
  interposer_mm: 1.0,
  die_mm: 2.0,
  hbm_mm: 3.6,          // memory stacks drawn taller, by chiplet id prefix "HBM"
  lid_clearance_mm: 1.6,
  lid_mm: 0.6,
  interposer_margin_mm: 1.5,
  substrate_margin_mm: 4,
});

// Tracks: the board, then one per lab. Names and colours are the Lab view's (lab-model.mjs LABS).
export const TRACK_ORDER = Object.freeze(["board", "lab-a", "lab-b", "lab-c", "lab-d", "baseline-sa"]);
export const LAB_TRACKS = Object.freeze(TRACK_ORDER.slice(1));
export const TRACKS = Object.freeze({
  board: { name: "Board", color: "#e7c48f" },
  "lab-a": { name: "Lab A", color: "#8aa9dd" },
  "lab-b": { name: "Lab B", color: "#88d9d0" },
  "lab-c": { name: "Lab C", color: "#a5d5aa" },
  "lab-d": { name: "Lab D", color: "#e6a36a" },
  "baseline-sa": { name: "Baseline (SA)", color: "#c9b2e8" },
  gate: { name: "AcceptanceGate", color: "#e7c48f" },
  core: { name: "Core", color: "#a9bcc2" },
});
export const trackName = (lab) => (typeof lab === "string" && Object.hasOwn(TRACKS, lab) ? TRACKS[lab].name : "Other");

// The heat ramp: the Lab view's stops, so both views colour a value the same way.
export const HEAT_STOPS = Object.freeze(["#112a48", "#236b91", "#56b6ba", "#dfd376", "#ec994f", "#e45138"]);

const isObj = (x) => x !== null && typeof x === "object" && !Array.isArray(x);
const finite = (x) => typeof x === "number" && Number.isFinite(x);
const str = (x) => (typeof x === "string" ? x : null);
const isHbm = (id) => /^hbm/i.test(id);

// ── the prefix guard ─────────────────────────────────────────────────────────────────────────────────────────
// buildScene trusts its caller to pass the verified prefix, and checks the one thing it can check without keys:
// the envelopes must be well-formed and run seq 1, 2, 3 ... with no gap or repeat. It keeps only that leading run,
// so an envelope from after a dropped event can never reach the scene even if a caller passes it.
export function contiguousPrefix(envelopes) {
  const list = (Array.isArray(envelopes) ? envelopes : [])
    .filter((env) => isObj(env) && isObj(env.event) && Number.isSafeInteger(env.event.seq))
    .map((env, index) => ({ env, index }))
    .sort((a, b) => a.env.event.seq - b.env.event.seq || a.index - b.index)
    .map(({ env }) => env);
  const out = [];
  for (const env of list) {
    if (env.event.seq !== out.length + 1) break;
    out.push(env);
  }
  return out;
}

// ── units and bounds ─────────────────────────────────────────────────────────────────────────────────────────
// Every length is placed in mm and every temperature coloured in °C. Only the units below are converted; a missing
// or unsupported unit is REFUSED: the value is never placed, coloured or exported as a number, and the scene lists
// it in `errors` with the unit as declared. Centre temperatures carry no unit of their own, so they are read in the
// unit of the same measurement's J (the only temperature unit an envelope declares). Producers spell Celsius "°C"
// (older signed rows) or "C" (newer rows): both are °C (lab-model.mjs tempUnit, the Lab view's rule).
export const SUPPORTED_UNITS = Object.freeze({
  length: Object.freeze({ canonical: "mm", accepted: Object.freeze(["mm", "m", "µm", "μm", "um"]), declared_in: "values.units" }),
  temperature: Object.freeze({ canonical: "°C", accepted: Object.freeze(["°C", "C", "K"]), declared_in: "values.J.unit (centre temperatures use their measurement's J unit)" }),
});
const LENGTH_TO_MM = Object.freeze({ mm: null, m: (v) => v * 1000, "µm": (v) => v / 1000, "μm": (v) => v / 1000, um: (v) => v / 1000 });
const TEMP_TO_C = Object.freeze({ "°C": null, K: (v) => v - 273.15 });
// Representable ranges, after conversion. A finite value outside them is an `out_of_range` scene error (distinct
// from chain validity): it is never drawn, never widens the scale or footprint, and never reaches an export.
export const BOUNDS = Object.freeze({
  temperature_c: Object.freeze({ min: -273.15, max: 2000 }),
  size_mm: Object.freeze({ above: 0, max: 1000 }),
  coordinate_mm: Object.freeze({ min: -1000, max: 1000 }),
  layer: Object.freeze({ min: 0, max: 16 }),
  W_abs_max: 1e12,
});
// Converted values are rounded to 1e-9 so a conversion can't print float noise; declared-canonical values are untouched.
const tidy = (v) => Math.round(v * 1e9) / 1e9;
const numText = (v) => (typeof v === "number" ? (Number.isFinite(v) && Math.abs(v) < 1e6 ? String(v) : v.toPrecision(4)) : typeof v);
const unitText = (u) => (typeof u === "string" ? (u.length > 24 ? `${u.slice(0, 24)}…` : u) : null);
const inRange = (v, lo, hi) => Number.isFinite(v) && v >= lo && v <= hi;

// values.geometry -> rects in mm, or a refusal. All or nothing: a layout with one bad chiplet is not drawn at all,
// because a package missing a chiplet would be a picture that never existed.
export function readGeometry(values) {
  if (!isObj(values) || values.geometry === undefined) return { rects: [], error: null };
  const unit = values.units;
  const fail = (code, detail) => ({ rects: [], error: { field: "geometry", code, unit: unitText(unit), detail } });
  const g = values.geometry;
  if (!Array.isArray(g)) return fail("malformed", "geometry is not a list");
  if (g.length === 0) return { rects: [], error: null };
  if (typeof unit !== "string") return fail("unit_missing", "no length unit declared (values.units)");
  if (!Object.hasOwn(LENGTH_TO_MM, unit)) return fail("unit_not_supported", `length unit "${unitText(unit)}" is not one of ${SUPPORTED_UNITS.length.accepted.join(", ")}`);
  const conv = LENGTH_TO_MM[unit];
  const { size_mm: S, coordinate_mm: C, layer: L } = BOUNDS;
  const rects = [], ids = new Set();
  for (const e of g) {
    if (!isObj(e) || typeof e.id !== "string" || ![e.xLL, e.yLL, e.w, e.h].every((n) => typeof n === "number")) return fail("malformed", "a geometry entry is not { id, xLL, yLL, w, h }");
    if (ids.has(e.id)) return fail("malformed", `chiplet ${e.id} appears twice`);
    ids.add(e.id);
    const [x, y, w, h] = [e.xLL, e.yLL, e.w, e.h].map((n) => (conv ? tidy(conv(n)) : n));
    if (![x, y, w, h].every(Number.isFinite)) return fail("out_of_range", `${e.id}: a length is not finite`);
    if (!(w > S.above && w <= S.max && h > S.above && h <= S.max)) return fail("out_of_range", `${e.id}: size ${numText(w)} x ${numText(h)} mm is outside 0 < size <= ${S.max} mm`);
    if (!inRange(x, C.min, C.max) || !inRange(y, C.min, C.max)) return fail("out_of_range", `${e.id}: position (${numText(x)}, ${numText(y)}) mm is outside ${C.min} to ${C.max} mm`);
    if (!Number.isFinite(x + w) || !Number.isFinite(y + h)) return fail("out_of_range", `${e.id}: an edge is not finite`);
    if (e.layer !== undefined && !(Number.isInteger(e.layer) && e.layer >= L.min && e.layer <= L.max)) return fail("out_of_range", `${e.id}: layer must be an integer ${L.min} to ${L.max}`);
    rects.push({ id: e.id, x, y, w, h, layer: e.layer ?? 0 });
  }
  return { rects, error: null };
}

// A temperature in a declared unit -> °C, or a refusal.
function toCelsius(v, unit, what) {
  if (typeof v !== "number") return { error: { code: "malformed", detail: `${what}: not a number` } };
  if (typeof unit !== "string") return { error: { code: "unit_missing", detail: `${what}: no temperature unit declared (values.J.unit)` } };
  const u = tempUnit(unit);
  if (!Object.hasOwn(TEMP_TO_C, u)) return { error: { code: "unit_not_supported", detail: `temperature unit "${unitText(unit)}" is not one of ${SUPPORTED_UNITS.temperature.accepted.join(", ")}` } };
  const conv = TEMP_TO_C[u];
  const c = conv ? tidy(conv(v)) : v;
  const { min, max } = BOUNDS.temperature_c;
  if (!inRange(c, min, max)) return { error: { code: "out_of_range", detail: `${what}: ${numText(v)} ${unitText(unit)} is outside ${min} to ${max} °C` } };
  return { c };
}

// values.center_temps -> { chiplet: °C }, or a refusal (all or nothing, in the measurement's J unit).
export function readTemps(values) {
  if (!isObj(values) || values.center_temps === undefined) return { temps: null, error: null };
  const unit = isObj(values.J) ? values.J.unit : undefined;
  const fail = (code, detail) => ({ temps: null, error: { field: "center_temps", code, unit: unitText(unit), detail } });
  if (!isObj(values.center_temps)) return fail("malformed", "center_temps is not an object");
  const entries = Object.entries(values.center_temps);
  if (entries.length === 0) return { temps: null, error: null };
  const out = {};
  for (const [k, v] of entries) {
    const r = toCelsius(v, unit, k);
    if (r.error) return fail(r.error.code, r.error.detail);
    out[k] = r.c;
  }
  return { temps: out, error: null };
}

// values.J -> { value (°C), unit: "°C", declared_unit }, or a refusal. values.W -> its display value, or a refusal.
export function readJ(values) {
  if (!isObj(values) || values.J === undefined) return { J: null, error: null };
  const J = values.J;
  if (!isObj(J)) return { J: null, error: { field: "J", code: "malformed", unit: null, detail: "J is not { value, unit }" } };
  const r = toCelsius(J.value, J.unit, "J");
  if (r.error) return { J: null, error: { field: "J", unit: unitText(J.unit), ...r.error } };
  return { J: { value: r.c, unit: SUPPORTED_UNITS.temperature.canonical, declared_unit: J.unit }, error: null };
}
export function readW(values) {
  if (!isObj(values) || values.W === undefined) return { W: null, error: null };
  const W = values.W;
  if (!isObj(W) || typeof W.value !== "number") return { W: null, error: { field: "W", code: "malformed", unit: null, detail: "W is not { value, metric_id }" } };
  if (!Number.isFinite(W.value) || Math.abs(W.value) > BOUNDS.W_abs_max) return { W: null, error: { field: "W", code: "out_of_range", unit: null, detail: `W ${numText(W.value)} is outside ±${BOUNDS.W_abs_max}` } };
  return { W: { value: W.value, metric_id: str(W.metric_id) ?? "" }, error: null };
}

// The events project() applied: the prefix minus the ones it rejected.
function appliedEvents(prefix, projection) {
  const rejected = new Set((projection?.rejected ?? []).map((r) => r.event_id));
  return prefix.filter((env) => !rejected.has(env.event.event_id));
}

// Measurements whose temperatures can colour a chiplet: node.create of a measurement with center_temps.
const measurementCreates = (applied) => applied.filter((env) => env.event.type === "node.create" && isObj(env.event.body) &&
  env.event.body.kind === "measurement" && isObj(env.values));

// ── the run's layout span: ONE definition for both views ─────────────────────────────────────────────────────
// The occupied span of the run's layouts: max − min of every chiplet extent (x to x + w, y to y + h) in the geometry
// project() applied in the prefix, placed in mm. Refused geometry (unit, range, shape) is not counted. The Package
// view (its footprint and legend) and the Lab view (its legend) both use it, and spanText() is the one label.
export function layoutSpan(prefixEnvelopes, projection = null) {
  const prefix = contiguousPrefix(prefixEnvelopes);
  const proj = projection && prefix.length === (prefixEnvelopes?.length ?? 0) ? projection : project(prefix.map((env) => env.event));
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const env of appliedEvents(prefix, proj)) {
    if (env.event.type !== "node.create" || !isObj(env.values)) continue;
    for (const r of readGeometry(env.values).rects) {
      x0 = Math.min(x0, r.x); y0 = Math.min(y0, r.y); x1 = Math.max(x1, r.x + r.w); y1 = Math.max(y1, r.y + r.h);
    }
  }
  return x0 !== Infinity && [x0, y0, x1, y1].every(Number.isFinite) ? { x0, y0, x1, y1 } : null;
}
// "layouts span W × H mm", to 0.1 mm; null when there is no span.
export const spanText = (span) => (span ? `layouts span ${(span.x1 - span.x0).toFixed(1)} × ${(span.y1 - span.y0).toFixed(1)} mm` : null);

// ── run frame: one colour scale and one footprint per run ────────────────────────────────────────────────────
// The colour scale covers every chiplet-centre temperature in the run's prefix, rounded out to 5 degrees and at
// least 10 degrees wide (the Lab view's rule). The footprint is the run's layout span (layoutSpan) plus margins.
// A replay computes this once from the whole prefix, so neither changes while the playhead moves.
export function runFrame(prefixEnvelopes, projection = null) {
  const prefix = contiguousPrefix(prefixEnvelopes);
  const proj = projection && prefix.length === (prefixEnvelopes?.length ?? 0) ? projection : project(prefix.map((env) => env.event));
  const applied = appliedEvents(prefix, proj);
  // Only accepted values count: normalised to °C and mm, inside the bounds. Refused values never move the frame.
  let lo = Infinity, hi = -Infinity;
  for (const env of measurementCreates(applied)) {
    const { temps } = readTemps(env.values);
    if (!temps) continue;
    for (const v of Object.values(temps)) { if (v < lo) lo = v; if (v > hi) hi = v; }
  }
  let scale = null;
  if (lo !== Infinity) {
    let min = Math.floor(lo / 5) * 5, max = Math.ceil(hi / 5) * 5;
    if (max - min < 10) { const mid = (min + max) / 2; min = Math.floor((mid - 5) / 5) * 5; max = min + 10; }
    scale = { min, max, unit: SUPPORTED_UNITS.temperature.canonical, fixed: true, basis: TEMP_BASIS };
  }
  const extent = layoutSpan(prefix, proj);
  let footprint = null;
  if (extent) {
    const { x0, y0, x1, y1 } = extent;
    const m = STACK.interposer_margin_mm, s = STACK.substrate_margin_mm;
    footprint = {
      extent: { x0, y0, x1, y1 },
      interposer: { x0: x0 - m, y0: y0 - m, x1: x1 + m, y1: y1 + m },
      substrate: { x0: x0 - m - s, y0: y0 - m - s, x1: x1 + m + s, y1: y1 + m + s },
      rule: `interposer = bounding extent of the run's geometry + ${m} mm; substrate = interposer + ${s} mm`,
    };
  }
  return { scale, footprint };
}

// The package stack as declared geometry: footprints from the run, heights from the schematic constants.
export function stackOf(footprint) {
  const S = STACK.substrate_mm, I = STACK.interposer_mm, top = S + I + Math.max(STACK.die_mm, STACK.hbm_mm) + STACK.lid_clearance_mm + STACK.lid_mm;
  return {
    label: STACK.label,
    schematic: true,
    note: STACK.note,
    units: STACK.units,
    constants: Object.fromEntries(Object.entries(STACK).filter(([, v]) => typeof v === "number")),
    layers: [
      { layer: "substrate", z0: 0, z1: S, footprint: footprint ? { ...footprint.substrate } : null, from: "schematic constant; footprint = interposer + margin" },
      { layer: "interposer", z0: S, z1: S + I, footprint: footprint ? { ...footprint.interposer } : null, from: "schematic constant; footprint = extent of the run's geometry + margin" },
      { layer: "chiplets", z0: S + I, z1_die: S + I + STACK.die_mm, z1_hbm: S + I + STACK.hbm_mm, footprint: null, from: "footprints from values.geometry (evidence); heights schematic, HBM taller" },
      { layer: "lid", z0: S, z1: top, footprint: null, outline_only: true, from: "schematic outline, cut away" },
    ],
  };
}

// Colour for a centre temperature on the run's fixed scale. Values outside the scale clamp to its ends.
export function heatColor(t, scale) {
  if (!finite(t) || !scale) return null;
  const stops = HEAT_STOPS.map((h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)));
  const f0 = Math.max(0, Math.min(1, (t - scale.min) / ((scale.max - scale.min) || 1))) * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(f0)), f = f0 - i, a = stops[i], b = stops[i + 1];
  return `#${[0, 1, 2].map((k) => Math.round(a[k] + (b[k] - a[k]) * f).toString(16).padStart(2, "0")).join("")}`;
}

// Legend ticks: the smallest round step that gives at most MAX_TICKS ticks. The count is computed, not looped to,
// so any finite scale terminates; a non-finite or empty scale has no ticks.
export const MAX_TICKS = 12;
const TICK_STEPS = [5, 10, 25, 50, 100, 250, 500, 1000];
export function scaleTicks(scale) {
  if (!scale || !Number.isFinite(scale.min) || !Number.isFinite(scale.max) || !(scale.max > scale.min)) return [];
  const range = scale.max - scale.min;
  if (!Number.isFinite(range)) return [];
  const step = TICK_STEPS.find((s) => range / s <= MAX_TICKS - 1) ?? 10 ** Math.ceil(Math.log10(range / (MAX_TICKS - 1)));
  const n = Math.max(0, Math.min(MAX_TICKS - 1, Math.floor(range / step + 1e-9)));
  return Array.from({ length: n + 1 }, (_, i) => scale.min + i * step);
}

// ── the scene ───────────────────────────────────────────────────────────────────────────────────────────────
// buildScene(prefixEnvelopes, projection, { frame }) describes the state at the END of prefixEnvelopes:
//   tracks   the board (accepted candidate, or the initial layout before any acceptance) and each lab's current
//            candidate, with chiplets (footprint, centre temperature, colour), J, W and where the temperatures came from;
//   timeline every move (parent layout -> candidate layout, per chiplet id, with seq and ts), acceptance, gate
//            outcome, measurement arrival and withdrawal in the prefix;
//   scale, footprint, stack: fixed per run when `frame` (from runFrame over the whole prefix) is passed.
// projection must be project() over exactly these envelopes (the verifier returns it); null computes it here.
export function buildScene(prefixEnvelopes, projection = null, { frame = null } = {}) {
  const prefix = contiguousPrefix(prefixEnvelopes);
  // A caller that passed anything beyond the contiguous prefix gets a projection recomputed over what was kept.
  const proj = projection && prefix.length === (prefixEnvelopes?.length ?? 0) ? projection : project(prefix.map((env) => env.event));
  const applied = appliedEvents(prefix, proj);
  const { scale, footprint } = frame ?? runFrame(prefix, proj);
  const nodes = proj?.nodes ?? {};

  // Display links from applied events only.
  const created = new Map(), sets = new Map(), accepts = new Map(), withdrawals = new Map();
  for (const env of applied) {
    const { type, body } = env.event;
    if (!isObj(body)) continue;
    if (type === "node.create" && typeof body.id === "string" && !created.has(body.id)) {
      created.set(body.id, { seq: env.event.seq, ts: str(env.ts), lab: str(env.actor?.lab), kind: str(body.kind), values: isObj(env.values) ? env.values : null });
    } else if (type === "support.add" && typeof body.node === "string" && Array.isArray(body.members)) {
      if (!sets.has(body.node)) sets.set(body.node, []);
      sets.get(body.node).push({ set_id: String(body.set_id), members: body.members.filter((m) => typeof m === "string"), seq: env.event.seq });
    } else if (type === "lifecycle.transition" && body.to === "accepted" && typeof body.node === "string") {
      accepts.set(body.node, { seq: env.event.seq, ts: str(env.ts) });
    } else if (type === "withdraw" && typeof body.node === "string") {
      withdrawals.set(body.node, { seq: env.event.seq, ts: str(env.ts), reason: str(body.reason) ?? "" });
    }
  }

  // The measurement whose temperatures a candidate shows: the first member that declares temperatures in the first
  // support set project() calls valid; with no valid set, the first one found, shown as stale. (The Lab view's rule.)
  // A pick whose temperatures are refused (unit or range) stays the pick, shown as refused: never silently swapped.
  const declaresTemps = (values) => isObj(values) && isObj(values.center_temps) && Object.keys(values.center_temps).length > 0;
  const measurementFor = (id) => {
    const status = nodes[id]?.support_status ?? {};
    const list = sets.get(id) ?? [];
    const pick = (onlyValid) => {
      for (const set of list) {
        if (onlyValid && status[set.set_id] !== "valid") continue;
        for (const m of set.members) {
          const made = created.get(m);
          if (made?.kind !== "measurement" || !declaresTemps(made.values)) continue;
          const read = readTemps(made.values);
          return { id: m, set_id: set.set_id, set_status: status[set.set_id] ?? "broken", validity: nodes[m]?.validity ?? "unverified", values: made.values, temps: read.temps, error: read.error };
        }
      }
      return null;
    };
    return pick(true) ?? pick(false);
  };

  const ref = (id) => {
    const made = created.get(id);
    return { kind: nodes[id]?.kind ?? made?.kind ?? null, id, lab: made?.lab ?? null, seq: made?.seq ?? null, ts: made?.ts ?? null };
  };
  const rectsOf = (id) => readGeometry(created.get(id)?.values);

  const layoutOf = (id) => {
    const node = nodes[id];
    const made = created.get(id);
    if (!node || !made) return null;
    const { rects, error: geometryError } = rectsOf(id);
    const ownRead = node.kind === "measurement" && declaresTemps(made.values) ? readTemps(made.values) : null;
    const own = ownRead ? { id, set_id: null, set_status: null, validity: node.validity, values: made.values, temps: ownRead.temps, error: ownRead.error } : null;
    const source = own ?? measurementFor(id);
    const tempsValid = source ? (own ? own.validity === "valid" : source.set_status === "valid") : false;
    const tempState = source ? (source.error ? "refused" : tempsValid ? "valid" : "stale") : null;
    const chiplets = rects.map((r) => {
      const t = source?.temps && Object.hasOwn(source.temps, r.id) ? source.temps[r.id] : null;
      return {
        id: r.id, x: r.x, y: r.y, w: r.w, h: r.h, layer: r.layer, kind: isHbm(r.id) ? "hbm" : "die",
        temp: t, temp_state: t === null ? null : tempState, color: t === null ? null : heatColor(t, scale),
      };
    });
    const overlaps = [];
    for (let i = 0; i < rects.length; i += 1) {
      for (let j = i + 1; j < rects.length; j += 1) {
        const a = rects[i], b = rects[j];
        if (a.layer !== b.layer) continue;
        const ox0 = Math.max(a.x, b.x), oy0 = Math.max(a.y, b.y), ox1 = Math.min(a.x + a.w, b.x + b.w), oy1 = Math.min(a.y + a.h, b.y + b.h);
        if (ox1 > ox0 && oy1 > oy0) overlaps.push({ a: a.id, b: b.id, x0: ox0, y0: oy0, x1: ox1, y1: oy1 });
      }
    }
    // J and W: from the measurement metricFor() picks (lab-model.mjs, the Lab view's rule): a measurement's own, or a
    // candidate's supporting measurement's. It needs no centre temperatures and is never painted onto a chiplet. A J
    // that is there but can't be read (unit, range, shape) is refused with its reason, never shown as a number.
    const metric = metricFor(id, { nodes, sets, created });
    const readMetric = readJ(metric?.values ?? (node.kind === "measurement" ? made.values : null));
    const J = readMetric.J, W = readW(metric?.values).W;
    const firstSet = (sets.get(id) ?? [])[0]?.set_id ?? null;
    // Measured: a measurement (such as the core's initial layout), or a candidate with a measurement in any support
    // set (with or without J). Only a candidate with no measurement at all is still awaiting simulation.
    const measured = node.kind === "measurement" || (sets.get(id) ?? []).some((set) => set.members.some((m) => created.get(m)?.kind === "measurement"));
    return {
      ref: ref(id),
      lifecycle: node.kind === "candidate" ? node.lifecycle : null,
      validity: node.validity,
      support_status: { ...node.support_status },
      units: SUPPORTED_UNITS.length.canonical,
      declared_units: str(made.values?.units),
      scenario_id: str(made.values?.scenario_id) ?? str(source?.values?.scenario_id) ?? str(metric?.values?.scenario_id),
      chiplets, overlaps,
      // A refused field is never placed or coloured; the reason is shown on screen and listed in scene.errors.
      geometry_error: geometryError ? { code: geometryError.code, unit: geometryError.unit, detail: geometryError.detail } : null,
      temps_error: source?.error ? { code: source.error.code, unit: source.error.unit, detail: source.error.detail, measurement: source.id } : null,
      temps_from: source ? {
        measurement: source.id, set_id: source.set_id, set_status: source.set_status, validity: source.validity, state: tempState,
        via_alternative: !own && source.set_status === "valid" && firstSet !== null && source.set_id !== firstSet,
        broken_sets: Object.entries(node.support_status).filter(([, st]) => st === "broken").map(([k]) => k),
      } : null,
      J, W,
      J_error: readMetric.error ? { code: readMetric.error.code, unit: readMetric.error.unit, detail: readMetric.error.detail, measurement: metric?.id ?? id } : null,
      metric: metric ? {
        measurement: metric.id, set_id: metric.set_id, validity: metric.validity,
        state: metric.validity === "valid" && (metric.set_id === null || metric.set_status === "valid") ? "valid" : "stale",
      } : null,
      measured,
    };
  };

  // The initial layout: the earliest measurement in the prefix that carries its own geometry (the core's start).
  const initialId = [...created.entries()].filter(([id, m]) => m.kind === "measurement" && nodes[id] && rectsOf(id).rects.length > 0)
    .sort((a, b) => a[1].seq - b[1].seq)[0]?.[0] ?? null;

  // Board: the accepted candidate accepted last (by seq); before any acceptance, the initial layout.
  const acceptedIds = [...accepts.keys()].filter((id) => nodes[id]?.kind === "candidate" && nodes[id].lifecycle === "accepted")
    .sort((a, b) => accepts.get(b).seq - accepts.get(a).seq);
  const boardId = acceptedIds[0] ?? null;
  const boardTrack = {
    track: "board", name: TRACKS.board.name, color: TRACKS.board.color,
    showing: boardId ? "accepted" : initialId ? "initial" : null,
    accepted: boardId ? { candidate: boardId, lab: created.get(boardId)?.lab ?? null, seq: accepts.get(boardId).seq, ts: accepts.get(boardId).ts } : null,
    layout: boardId ? layoutOf(boardId) : initialId ? layoutOf(initialId) : null,
    history: [...accepts.keys()].filter((id) => nodes[id]?.kind === "candidate").sort((a, b) => accepts.get(a).seq - accepts.get(b).seq),
  };

  // Lab tracks: each lab's latest candidate (by seq).
  const candidatesBy = new Map(LAB_TRACKS.map((lab) => [lab, []]));
  for (const [id, m] of [...created.entries()].sort((a, b) => a[1].seq - b[1].seq)) {
    if (m.kind === "candidate" && nodes[id] && candidatesBy.has(m.lab)) candidatesBy.get(m.lab).push(id);
  }
  const labTracks = LAB_TRACKS.map((lab) => {
    const ids = candidatesBy.get(lab);
    const current = ids[ids.length - 1] ?? null;
    return { track: lab, name: TRACKS[lab].name, color: TRACKS[lab].color, layout: current ? layoutOf(current) : null, history: ids, on_board: current !== null && current === boardId };
  });

  // ── timeline ──
  const place = (r) => ({ x: r.x, y: r.y, w: r.w, h: r.h, layer: r.layer });
  const moveChiplets = (fromId, toId) => {
    const from = fromId ? rectsOf(fromId).rects : [];
    const to = rectsOf(toId).rects;
    const ids = [...new Set([...from.map((r) => r.id), ...to.map((r) => r.id)])];
    return ids.map((cid) => {
      const a = from.find((r) => r.id === cid) ?? null, b = to.find((r) => r.id === cid) ?? null;
      return { id: cid, from: a ? place(a) : null, to: b ? place(b) : null,
        moved: !a || !b || a.x !== b.x || a.y !== b.y || a.w !== b.w || a.h !== b.h || a.layer !== b.layer };
    });
  };
  const timeline = [];
  const lastShown = new Map();          // track -> node id it showed before this event
  let boardShown = null;
  for (const env of applied) {
    const { type, body } = env.event;
    if (!isObj(body)) continue;
    const seq = env.event.seq, ts = str(env.ts);
    if (type === "node.create" && body.id === initialId) {
      timeline.push({ seq, ts, kind: "initial", track: "board", node: initialId });
      boardShown = initialId;
      for (const lab of LAB_TRACKS) if (!lastShown.has(lab)) lastShown.set(lab, initialId);
    } else if (type === "node.create" && body.kind === "candidate" && typeof body.id === "string" && nodes[body.id] && candidatesBy.has(str(env.actor?.lab)) && rectsOf(body.id).rects.length > 0) {
      const lab = env.actor.lab;
      const fromId = lastShown.get(lab) ?? null;
      timeline.push({ seq, ts, kind: "move", track: lab, from: fromId ? ref(fromId) : null, to: ref(body.id), chiplets: moveChiplets(fromId, body.id) });
      lastShown.set(lab, body.id);
    } else if (type === "lifecycle.transition" && typeof body.node === "string" && nodes[body.node]?.kind === "candidate") {
      const lab = created.get(body.node)?.lab ?? null;
      if (body.to === "accepted") {
        timeline.push({ seq, ts, kind: "move", track: "board", from: boardShown ? ref(boardShown) : null, to: ref(body.node), chiplets: moveChiplets(boardShown, body.node) });
        timeline.push({ seq, ts, kind: "accept", track: "board", candidate: body.node, lab });
        boardShown = body.node;
      } else if (["non_improving_current", "within_margin"].includes(body.to)) {
        timeline.push({ seq, ts, kind: "gate", candidate: body.node, lab, outcome: body.to });
      } else if (["rejected_schema", "rejected_constraints", "failed_run", "reproduction_failed", "cancelled", "non_improving", "tie", "inconclusive"].includes(body.to)) {
        timeline.push({ seq, ts, kind: "out", candidate: body.node, lab, outcome: body.to });
      }
    } else if (type === "support.add" && typeof body.node === "string" && nodes[body.node]?.kind === "candidate" && Array.isArray(body.members)) {
      const m = body.members.find((x) => typeof x === "string" && created.get(x)?.kind === "measurement" && readTemps(created.get(x).values).temps);
      if (m) timeline.push({ seq, ts, kind: "measured", candidate: body.node, lab: created.get(body.node)?.lab ?? null, measurement: m, set_id: String(body.set_id) });
    } else if (type === "withdraw" && typeof body.node === "string") {
      const reason = str(body.reason) ?? "";
      timeline.push({ seq, ts, kind: "withdraw", node: body.node, reason, drill: /^\s*drill\b/i.test(reason),
        affected: Object.keys(nodes).filter((id) => (nodes[id].stale_because ?? []).includes(body.node)).sort() });
    }
  }

  // The drill summary, straight from project(): withdrawn, went stale, and still valid on another support set.
  const ids = Object.keys(nodes).sort();
  const withdrawn = ids.filter((id) => nodes[id].validity === "withdrawn");
  const drill = withdrawn.length === 0 ? null : {
    withdrawn: withdrawn.map((id) => ({ node: id, seq: withdrawals.get(id)?.seq ?? null, ts: withdrawals.get(id)?.ts ?? null, reason: withdrawals.get(id)?.reason ?? "" })),
    stale: ids.filter((id) => nodes[id].validity === "stale").map((id) => ({ node: id, because: [...nodes[id].stale_because] })),
    survived: ids.filter((id) => nodes[id].validity === "valid" && Object.values(nodes[id].support_status).includes("broken") && Object.values(nodes[id].support_status).includes("valid")),
  };

  // Value errors: every applied node.create's values, field by field. Distinct from chain validity: the envelope
  // verified, but a value in it can't be placed or coloured, so it isn't.
  const errors = [];
  for (const env of applied) {
    const { type, body } = env.event;
    if (type !== "node.create" || !isObj(body) || !isObj(env.values) || !created.has(body.id) || created.get(body.id).seq !== env.event.seq) continue;
    for (const read of [readGeometry(env.values), readTemps(env.values), readJ(env.values), readW(env.values)]) {
      if (read.error) errors.push({ seq: env.event.seq, node: body.id, field: read.error.field, code: read.error.code, unit: read.error.unit ?? null, detail: read.error.detail });
    }
  }

  const last = prefix[prefix.length - 1] ?? null;
  const first = prefix[0] ?? null;
  return {
    v: SCENE_VERSION,
    basis: {
      temps: TEMP_BASIS,
      stack: `${STACK.label}: ${STACK.note}`,
      moves: "A move goes from the layout the track showed before (a lab's previous candidate, else the initial layout; for the board, the previous accepted candidate, else the initial layout) to the new candidate.",
      source: "Only the verified projectable prefix; status from project() over it; geometry and temperatures are display values from the same envelopes.",
      units: "Lengths are placed in mm and temperatures coloured in °C. Only the supported units are converted; a missing or unsupported unit, or a value outside the bounds, is refused: listed in errors and never placed, coloured or exported as a number.",
    },
    run: first && isObj(first.run) ? { run_id: str(first.run.run_id), arm: str(first.run.arm), family: str(first.run.family), seed: finite(first.run.seed) ? first.run.seed : null } : null,
    at: { seq: last ? last.event.seq : 0, ts: last ? str(last.ts) : null, count: prefix.length },
    units: { length: SUPPORTED_UNITS.length.canonical, temperature: SUPPORTED_UNITS.temperature.canonical, supported: SUPPORTED_UNITS },
    bounds: BOUNDS,
    scale,
    footprint,
    stack: stackOf(footprint),
    initial: initialId,
    board: boardTrack.accepted ? { ...boardTrack.accepted } : null,
    tracks: [boardTrack, ...labTracks],
    timeline,
    drill,
    rejected: (proj?.rejected ?? []).map((r) => ({ event_id: r.event_id, code: r.code })),
    errors,
  };
}

// The scene after the first `count` envelopes of the prefix, on the run's fixed frame. The page calls this as the
// playhead moves; the CLI's --at uses it too.
export function sceneAt(prefixEnvelopes, count, frame) {
  const prefix = contiguousPrefix(prefixEnvelopes);
  const slice = prefix.slice(0, Math.max(0, Math.min(prefix.length, count)));
  return buildScene(slice, project(slice.map((env) => env.event)), { frame: frame ?? runFrame(prefix) });
}

// A short line for a timeline event, for captions and scrubber titles. name(id) shortens ids for display (the page
// passes lab-model.mjs shortId and keeps the full line in the title); the default keeps them whole (the CLI).
export function describeEvent(e, name = (id) => id) {
  const who = (lab) => trackName(lab);
  switch (e.kind) {
    case "initial": return `seq ${e.seq} · initial layout ${name(e.node)} (core measurement)`;
    case "move": return e.track === "board"
      ? `seq ${e.seq} · board moves to ${name(e.to.id)}${e.from ? ` from ${name(e.from.id)}` : ""}`
      : `seq ${e.seq} · ${who(e.track)} proposes ${name(e.to.id)}${e.from ? ` (from ${name(e.from.id)})` : ""}`;
    case "accept": return `seq ${e.seq} · AcceptanceGate accepts ${name(e.candidate)} (${who(e.lab)})`;
    case "gate": return `seq ${e.seq} · AcceptanceGate: ${name(e.candidate)} ${e.outcome}`;
    case "out": return `seq ${e.seq} · ${name(e.candidate)} ${e.outcome}`;
    case "measured": return `seq ${e.seq} · ${name(e.candidate)} gets temperatures from ${name(e.measurement)}`;
    case "withdraw": return `seq ${e.seq} · ${name(e.node)} withdrawn${e.reason ? ` (${e.reason})` : ""}`;
    default: return `seq ${e.seq}`;
  }
}

// Why a verified value was refused (scene.errors, temps_error and J_error codes). Refused values are never placed,
// coloured or shown as a number.
const REFUSAL = { unit_not_supported: "unit not supported", unit_missing: "unit missing", out_of_range: "value out of range", malformed: "malformed value" };
export const refusalText = (e) => `${REFUSAL[e.code] ?? e.code}${e.unit ? ` ("${e.unit}")` : ""}`;
const NO_TEMPS = { rejected_schema: "not simulated (schema rejected)", rejected_constraints: "not simulated (failed the constraint check)", failed_run: "simulation failed", cancelled: "cancelled" };

// Where a layout's values come from, for the inspector line under J: { j_state, parts: [{ text, state }] }, state ""
// or a CSS class ("stale", "alt"). J and W come from the measurement metricFor() picks, the centre temperatures from
// the one measurementFor() picks, and the two can differ (a current J beside withdrawn older temperatures). So:
//   - one measurement supplies J, W and the temperatures, all drawn: one part, "values from" it;
//   - otherwise J and the temperatures get a part each, each labelled and styled by its own source's state. Neither
//     borrows the other's: a stale temperature source never makes J stale, nor the reverse;
//   - an absent or refused J says so, with the reason; only a candidate with no measurement at all is "awaiting".
// j_state is J's own state, for the J figure. name(id) shortens ids for display (the page passes shortId).
export function describeSource(L, name = (id) => id) {
  if (!L) return { j_state: "", parts: [] };
  const m = L.metric, t = L.temps_from;
  const j_state = m?.state === "stale" ? "stale" : "";
  const temps = (word) => {
    if (t.state === "refused") return { text: `temperatures from ${name(t.measurement)} not drawn · ${refusalText(L.temps_error)}`, state: "stale" };
    if (t.state === "stale") return { text: `${word} from ${name(t.measurement)} · STALE (${t.validity})`, state: "stale" };
    if (t.via_alternative) return { text: `${word} via ${name(t.measurement)} (set ${t.set_id}) · set ${t.broken_sets.join(", ")} broken`, state: "alt" };
    return { text: t.set_id ? `${word} from ${name(t.measurement)} · support set ${t.set_id}` : `${word} from ${name(t.measurement)} (its own)`, state: "" };
  };
  if (m && t && L.J && t.state !== "refused" && m.measurement === t.measurement) return { j_state, parts: [temps("values")] };
  if (!m && !t && !L.measured) return { j_state, parts: [{ text: `no temperatures · ${NO_TEMPS[L.lifecycle] ?? "awaiting simulation"}`, state: "" }] };
  const j = L.J_error ? { text: `J refused · ${refusalText(L.J_error)}${m && m.set_id !== null ? ` · from ${name(m.measurement)}` : ""}`, state: "stale" }
    : m ? { text: `${m.set_id === null ? "J: its own value" : `J from ${name(m.measurement)}`}${m.state === "stale" ? ` · STALE (${m.validity})` : ""}`, state: j_state }
    : { text: "measured, but no J in the verified data", state: "" };
  return { j_state, parts: [j, t ? temps("temperatures") : { text: "no per-chiplet temperatures", state: "" }] };
}
