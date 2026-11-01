// SentiLab Package view: the agent-door feed. The ONE place the 3D view gets CPU-DRAM layouts: the bundled replay
// (door-fixture.json, page-owned: the raw and snapped references and two synthetic examples) and, live, the agent door
// API through the Worker's read-only /api/* proxy (polling only: the Worker strips upgrade, so there are no
// WebSockets). Pure apart from the fetches and the poller; the node tests drive both with a scripted fetch and clock.
//
// The live contract is the API's own shape (AGENT-DOOR Amendment 3; sentilab PR #81). The page adapts to it; the
// page-side `sentilab-door-layouts/1` is retired:
//   GET /api/open/v1/door/results?after=<n>  `sentilab-door-results/1` = { items, next_after, has_more, metric, label,
//                                            scorer }: the runs that changed after version n, paged by next_after while
//                                            has_more is true
//   GET /api/open/v1/door/events?after=<n>   `sentilab-door-events/1` = { events, next_after, has_more, scorer }: the
//                                            arrivals (agents at the door, refused attempts, each run's state changes)
// From an item the page reads this, and nothing more (every other field is dropped unread, `operator` included if an
// older build still sends it):
//   id       the run id, open-<8 hex>-<32 hex>: a key only, never shown
//   label    rebuilt here from `class` (API_CLASSES) and `short_id` (4 lowercase hex) and checked against the item's own
//            label: the only name the page shows, never free text
//   status   a state of the open-proposal contract (STATUSES); `arrival` (the door's admission order) and `seq` (the
//            record's version: an older version never replaces a newer one)
//   dies     exactly 8 contract dies { die: 0..7, x_um, y_um, rot_deg }: die i is TAP die i (C0..C3, then D0..D3), its
//            centre in micrometres from the interposer's lower-left corner, a catalogue rotation (CPU 0 or 90, DRAM 0)
//   result   null, or the scorer's: the value under result.metric_id (exactly BOARD_METRIC) with its metric's
//            precision_K, native_all_block_max_C and active_layer_peak_C (distinct statistics, shown apart by name),
//            active_guard, evaluator, temperature_label, verification and replay. Never its grid64 (below).
// From an event: seq, kind, the label rebuilt from class and short_id, and for an attempt its outcome and codes, for a
// run its id, state and codes. Scorer events move the cursor only.
// A record that breaks a rule is refused whole (never drawn, counted with its reason code). A result that breaks a rule
// is dropped and the layout drawn without a value, with the reason.
//
// Payload shape is not provenance (CAD/3D freeze section 5.7, PL-2, PL-6, D14; root's PR78 R1; Amendment 3). The door
// feed is unsigned, so no map is drawn from any feed result, even when it carries a grid64, until an admitted
// association exists (P5): the grid is never read, the result's field is "unassociated" and its value a qualified
// diagnostic. Every temperature carries a shared label (temperature-label.mjs LABELS). A feed result's is labelForAll()
// over the evaluator identity the feed names and no verified one, so it is never more than "unvalidated" (a withdrawn
// identity stays withdrawn), and the API's own temperature_label can only make it more cautious. The one map the page
// draws is the bundled raw reference's, admitted by a pin in reviewed page code (case-cpu-dram.mjs FIELD_PINS) whose
// geometry, field and result-record digests the page recomputes with WebCrypto (verifyPinnedFields): the record digest
// covers the field's orientation and every statistic shown with it, so a pin admits nothing it did not check.
import { DIES, DIE_IDS, dieById, RULES, FIELD_PINS, ACTIVE_LAYER_GUARD_C } from "./case-cpu-dram.mjs";
import { readBodyCapped, MAX_API_BYTES } from "../view-core.mjs";
import { strictJson } from "../runs-list.mjs";
import { canonical } from "../canonical.mjs";
import { labelFor, labelForAll, LABELS } from "../../temperature-label.mjs";

export const RESULTS_SCHEMA = "sentilab-door-results/1";
export const EVENTS_SCHEMA = "sentilab-door-events/1";
export const REPLAY_SCHEMA = "sentilab-package-replay/1";
// The classes a door record may carry (#81 app/door/policy.py CLASSES); the bundled replay adds the page's own three.
export const API_CLASSES = Object.freeze(["verified_agent", "signed_agent", "declared_agent", "crawler_claimed", "automation",
  "likely_human", "unknown", "ours"]);
export const CLASSES = Object.freeze(["reference-only", "reference", "example", ...API_CLASSES]);
// The open-proposal contract's lifecycle (open_proposals/contract/states.py LIFECYCLE), unchanged.
export const STATUSES = Object.freeze(["rejected", "queued", "held", "evaluating", "evaluated", "failed", "replaying",
  "reproduced", "not_reproduced", "cross_checked", "cancelled", "expired"]);
export const FIXTURE_STATUSES = Object.freeze(["reference", "example"]);
// States whose result is a score that stands (a failed run's numbers are never drawn).
export const SCORED = Object.freeze(["evaluated", "replaying", "reproduced", "not_reproduced", "cross_checked", "reference"]);
// The board's one frozen statistic (the score, the replay, the board and the 3D caption all use it).
export const BOARD_METRIC = Object.freeze({
  id: "max_chiplet_centre_cell_mean_C",
  name: "Max chiplet-centre mean",
  definition: "For each of the 8 chiplets, the mean of its 1, 2 or 4 central HotSpot 6.0 grid-64 cells; then the maximum over the chiplets.",
  unit: "°C",
});
// Statistics a result may also carry. Each is shown under its own name, never as the board metric.
export const DISTINCT_FIELDS = Object.freeze({
  native_all_block_max_C: "Native all-block maximum",
  active_layer_peak_C: "Active-layer peak",
});
// The page's claim text, and the API's result label (#81 RESULT_LABEL): a feed result under any other label is not read.
export const RESULT_LABEL = "simulated, not silicon";
export const FEED_RESULT_LABEL = "simulated, not silicon; HotSpot 6.0, grid 64; max_chiplet_centre_cell_mean_C";
export const GRID_CELLS = 64 * 64;
export const BOUNDS = Object.freeze({
  // A centre may sit off the interposer by half its width (a refused or out-of-frame proposal still draws); past
  // that it can't be a layout of this case at all.
  centre_um: Object.freeze({ min: -22500, max: 67500 }),   // half an interposer (22.5 mm) beyond each edge, in µm
  temp_c: Object.freeze({ min: -50, max: 500 }),
  layouts: 500,
  events: 40,                                                // the arrivals kept, newest last
});
const ID = /^[a-z0-9][a-z0-9._-]{0,79}$/;
const RUN_ID = /^open-[0-9a-f]{8}-[0-9a-f]{32}$/;
const SHORT = /^[0-9a-f]{4}$/;
const HEX64 = /^[0-9a-f]{64}$/;
const CODE = /^[a-z][a-z0-9_]{0,47}$/;
const isObj = (x) => x !== null && typeof x === "object" && !Array.isArray(x);
const num = (x) => typeof x === "number" && Number.isFinite(x);
const count = (n) => Number.isSafeInteger(n) && n >= 0;
const inTemp = (v) => num(v) && v >= BOUNDS.temp_c.min && v <= BOUNDS.temp_c.max;

// "<class> · <short>": the separator is " · " (U+00B7 between spaces); nothing before, between or after.
export function parseLabel(label) {
  if (typeof label !== "string" || label.length > 40) return null;
  const parts = label.split(" · ");
  if (parts.length !== 2 || !CLASSES.includes(parts[0]) || !SHORT.test(parts[1])) return null;
  return { cls: parts[0], short: parts[1] };
}
export const labelText = (cls, short) => `${cls} · ${short}`;

// Eight dies -> { dies } in C0..D3 order, or { refused: code }. key: "die" names them (the replay: "C0"), "index" numbers
// them (the API: TAP die i, 0..7).
function readDies(list, key) {
  if (!Array.isArray(list) || list.length !== DIE_IDS.length) return { refused: "dies_count" };
  const seen = new Map();
  for (const d of list) {
    if (!isObj(d)) return { refused: "die_unknown" };
    const id = key === "index" ? (Number.isInteger(d.die) ? DIES.find((x) => x.tap_index === d.die)?.id : undefined)
      : typeof d.die === "string" && DIE_IDS.includes(d.die) ? d.die : undefined;
    if (!id) return { refused: "die_unknown" };
    if (seen.has(id)) return { refused: "die_duplicate" };
    if (![d.x_um, d.y_um, d.rot_deg].every(num)) return { refused: "coord_not_number" };
    const { min, max } = BOUNDS.centre_um;
    if (d.x_um < min || d.x_um > max || d.y_um < min || d.y_um > max) return { refused: "coord_out_of_range" };
    if (!RULES.rotations_deg[dieById(id).kind].includes(d.rot_deg)) return { refused: "rotation_not_allowed" };
    seen.set(id, { die: id, x_um: d.x_um, y_um: d.y_um, rot_deg: d.rot_deg });
  }
  return { dies: DIE_IDS.map((id) => seen.get(id)) };
}

// ── the API: one results item ────────────────────────────────────────────────────────────────────────────────────
// One raw item -> { layout } or { refused: code }.
export function normalizeItem(raw) {
  if (!isObj(raw)) return { refused: "not_an_object" };
  if (raw.hidden === true) return { refused: "hidden" };
  if (typeof raw.id !== "string" || !RUN_ID.test(raw.id)) return { refused: "id_invalid" };
  if (!API_CLASSES.includes(raw.class) || typeof raw.short_id !== "string" || !SHORT.test(raw.short_id)) return { refused: "label_invalid" };
  const label = labelText(raw.class, raw.short_id);
  if (raw.label !== label) return { refused: "label_invalid" };
  if (!STATUSES.includes(raw.status)) return { refused: "status_unknown" };
  const dies = readDies(raw.dies, "index");
  if (dies.refused) return dies;
  const layout = {
    id: raw.id, cls: raw.class, short: raw.short_id, label, status: raw.status,
    seq: count(raw.seq) ? raw.seq : null, arrival: count(raw.arrival) ? raw.arrival : null,
    dies: dies.dies, result: null, result_refused: null,
  };
  if (raw.result !== undefined && raw.result !== null) {
    const r = normalizeItemResult(raw.result, layout.status);
    if (r.refused) layout.result_refused = r.refused;
    else layout.result = r.result;
  }
  return { layout };
}

// The evaluator a feed result names, spelled as the API's identity string (#81 EVALUATOR_IDENTITY) only so the label
// rule can read it; never taken as verified. null when it names none the page can read.
export const evaluatorIdentity = (ev) => (isObj(ev) && typeof ev.binary_sha256 === "string" && HEX64.test(ev.binary_sha256) && ev.grid === 64
  ? `hotspot6:${ev.binary_sha256}:grid:64x64` : null);
// A feed result's label: the most cautious of the identity it names and none verified (labelForAll), so an unverified
// identity is never more than "unvalidated"; the API's own temperature_label may only make it more cautious. rule: the
// label rule (the tests pass one with their own lists).
export function feedLabel(identity, apiLabel, rule = { labelForAll }) {
  const label = rule.labelForAll([identity ?? undefined, undefined]);
  return apiLabel === LABELS.withdrawn.state ? LABELS.withdrawn : label;
}
const VERIFICATION_FLAGS = ["distinct_execution", "receipts_bound", "binding_ok", "active_guard_ok", "candidate"];
const CPU = ["measured", "unknown_charged_conservatively"];
const NOT_CLAIMED = ["beat", "margin", "routed wire", "source acceptance"];

// A feed result -> { result } or { refused: code }. result:
//   metric        { id, value, precision_K }: the scorer's value of the board metric; the page never recomputes it
//   label         a temperature-label.mjs LABELS object for every temperature of this result (feedLabel)
//   claim         "simulated, not silicon", shown beside the shared label, never instead of it
//   evaluator     the identity the feed names (evaluatorIdentity), shown as named, never checked here; or null
//   field_state   always "unassociated": the feed is unsigned, so no map; grid, grid_text, result_text, field_key null
//   diagnostic    always true: the value is shown qualified, as a diagnostic
//   distinct      [{ key, name, value }] native_all_block_max_C and active_layer_peak_C, shown apart, by name
//   guard         { limit_C, ok }: the active-layer guard as the feed states it (strictly below 119.07 °C)
//   verification  { replay, replay_code, distinct_execution, receipts_bound, binding_ok, active_guard_ok, cpu,
//                   candidate, not_claimed }: what the feed says the result was checked for, and what it is not
//   replay        { fresh_process, match, receipts_bound, code }
export function normalizeItemResult(raw, status) {
  if (!isObj(raw)) return { refused: "result_malformed" };
  if (!SCORED.includes(status)) return { refused: "result_not_scored_state" };
  if (raw.label !== FEED_RESULT_LABEL) return { refused: "result_label_unknown" };
  if (raw.metric_id !== BOARD_METRIC.id || !isObj(raw.metric) || raw.metric.metric_id !== BOARD_METRIC.id) return { refused: "metric_unknown" };
  const value = raw[raw.metric_id];
  if (!inTemp(value)) return { refused: "metric_value" };
  const precision = raw.metric.precision_K;
  if (!num(precision) || precision <= 0 || precision > 1) return { refused: "precision_missing" };
  const distinct = [];
  for (const [key, name] of Object.entries(DISTINCT_FIELDS)) {
    if (!inTemp(raw[key])) return { refused: "distinct_value" };
    distinct.push({ key, name, value: raw[key] });
  }
  const g = raw.active_guard;
  if (!isObj(g) || g.field !== "active_layer_peak_C" || g.rule !== "strictly below" || g.limit_C !== ACTIVE_LAYER_GUARD_C || typeof g.ok !== "boolean") return { refused: "guard_unknown" };
  if (g.ok !== (raw.active_layer_peak_C < g.limit_C)) return { refused: "guard_inconsistent" };
  const v = raw.verification;
  if (!isObj(v) || (v.replay !== "reproduced" && v.replay !== "not_reproduced") || !CPU.includes(v.cpu)
    || !VERIFICATION_FLAGS.every((k) => typeof v[k] === "boolean") || !(v.replay_code === null || (typeof v.replay_code === "string" && CODE.test(v.replay_code)))
    || !Array.isArray(v.not_claimed) || !v.not_claimed.every((x) => NOT_CLAIMED.includes(x))) return { refused: "verification_malformed" };
  const p = raw.replay;
  if (!isObj(p) || !["fresh_process", "match", "receipts_bound"].every((k) => typeof p[k] === "boolean")
    || !(p.code === null || (typeof p.code === "string" && CODE.test(p.code)))) return { refused: "replay_malformed" };
  const evaluator = evaluatorIdentity(raw.evaluator);
  return { result: {
    metric: { id: BOARD_METRIC.id, value, precision_K: precision }, claim: RESULT_LABEL, label: feedLabel(evaluator, raw.temperature_label), evaluator,
    field_state: "unassociated", grid: null, grid_text: null, result_text: null, field_key: null, diagnostic: true, distinct,
    guard: { limit_C: g.limit_C, ok: g.ok },
    verification: { replay: v.replay, replay_code: v.replay_code, cpu: v.cpu, ...Object.fromEntries(VERIFICATION_FLAGS.map((k) => [k, v[k]])), not_claimed: [...v.not_claimed] },
    replay: { fresh_process: p.fresh_process, match: p.match, receipts_bound: p.receipts_bound, code: p.code },
  } };
}

// A results page -> { layouts, refused: { code: count }, next_after, has_more }, or null when it is not one.
export function normalizeResults(doc) {
  if (!isObj(doc) || doc.schema !== RESULTS_SCHEMA || !Array.isArray(doc.items) || !count(doc.next_after) || typeof doc.has_more !== "boolean"
    || !isObj(doc.metric) || doc.metric.metric_id !== BOARD_METRIC.id) return null;
  const refused = {};
  const layouts = [], ids = new Set();
  for (const raw of doc.items.slice(0, BOUNDS.layouts)) {
    const n = normalizeItem(raw);
    if (n.refused) { refused[n.refused] = (refused[n.refused] ?? 0) + 1; continue; }
    if (ids.has(n.layout.id)) { refused.id_duplicate = (refused.id_duplicate ?? 0) + 1; continue; }
    ids.add(n.layout.id);
    layouts.push(n.layout);
  }
  if (doc.items.length > BOUNDS.layouts) refused.over_cap = doc.items.length - BOUNDS.layouts;
  return { layouts, refused, next_after: doc.next_after, has_more: doc.has_more };
}

// ── the API: one event (the arrivals) ────────────────────────────────────────────────────────────────────────────
// -> { event }, { skip: true } for a scorer event (it moves the cursor only), or { refused: code }.
// event: { seq, kind: "arrival" | "attempt" | "run", cls, short (null for an arrival without a token), label,
//          outcome ("rejected" | "refused", attempts), run_id and state (runs), codes (attempts and runs) }
export function normalizeEvent(raw) {
  if (!isObj(raw) || !count(raw.seq)) return { refused: "event_malformed" };
  if (raw.kind === "scorer") return { skip: true };
  if (!["arrival", "attempt", "run"].includes(raw.kind)) return { refused: "event_kind_unknown" };
  if (!API_CLASSES.includes(raw.class)) return { refused: "label_invalid" };
  const short = raw.short_id;              // null only for an arrival that carried no token
  if (short === null ? raw.kind !== "arrival" : typeof short !== "string" || !SHORT.test(short)) return { refused: "label_invalid" };
  const label = short === null ? raw.class : labelText(raw.class, short);
  if (raw.label !== label) return { refused: "label_invalid" };
  const event = { seq: raw.seq, kind: raw.kind, cls: raw.class, short, label };
  const codes = () => (Array.isArray(raw.codes) ? raw.codes.filter((c) => typeof c === "string" && CODE.test(c)).slice(0, 4) : []);
  if (raw.kind === "attempt") {
    if (raw.outcome !== "rejected" && raw.outcome !== "refused") return { refused: "event_malformed" };
    Object.assign(event, { outcome: raw.outcome, codes: codes() });
  }
  if (raw.kind === "run") {
    if (typeof raw.run_id !== "string" || !RUN_ID.test(raw.run_id) || !STATUSES.includes(raw.state)) return { refused: "event_malformed" };
    Object.assign(event, { run_id: raw.run_id, state: raw.state, codes: codes() });
  }
  return { event };
}
// An events page -> { events, refused, next_after, has_more }, or null when it is not one.
export function normalizeEvents(doc) {
  if (!isObj(doc) || doc.schema !== EVENTS_SCHEMA || !Array.isArray(doc.events) || !count(doc.next_after) || typeof doc.has_more !== "boolean") return null;
  const refused = {}, events = [];
  for (const raw of doc.events.slice(0, 500)) {
    const n = normalizeEvent(raw);
    if (n.refused) refused[n.refused] = (refused[n.refused] ?? 0) + 1;
    else if (n.event) events.push(n.event);
  }
  return { events, refused, next_after: doc.next_after, has_more: doc.has_more };
}
// Keep each event once (by seq), in seq order, the newest BOUNDS.events.
export function mergeEvents(current, incoming) {
  const bySeq = new Map(current.map((e) => [e.seq, e]));
  for (const e of incoming) if (!bySeq.has(e.seq)) bySeq.set(e.seq, e);
  return [...bySeq.values()].sort((a, b) => a.seq - b.seq).slice(-BOUNDS.events);
}

// ── the bundled replay (page-owned records: the references and the synthetic examples) ──────────────────────────
// A replay record is the page's own layout: { id, label "<class> · <short>", status, dies: [{ die: "C0", x_um, y_um,
// rot_deg }], result? }. Its result: { metric_id, value_C, precision_K, label, grid64?, row0?, native_all_block_max_C?,
// active_layer_peak_C? }, row0 "bottom" or "top" required with grid64, never guessed. A bundled field waits for its
// pin check (verifyPinnedFields); without a pin it is unassociated and not kept.
export function normalizeLayout(raw) {
  if (!isObj(raw)) return { refused: "not_an_object" };
  if (raw.hidden === true) return { refused: "hidden" };
  if (typeof raw.id !== "string" || !ID.test(raw.id)) return { refused: "id_invalid" };
  const lab = parseLabel(raw.label);
  if (!lab) return { refused: "label_invalid" };
  if (![...STATUSES, ...FIXTURE_STATUSES].includes(raw.status)) return { refused: "status_unknown" };
  const dies = readDies(raw.dies, "die");
  if (dies.refused) return dies;
  const layout = {
    id: raw.id, cls: lab.cls, short: lab.short, label: labelText(lab.cls, lab.short), status: raw.status,
    seq: count(raw.seq) ? raw.seq : null, arrival: null, dies: dies.dies, result: null, result_refused: null,
  };
  if (raw.result !== undefined && raw.result !== null) {
    const r = normalizeResult(raw.result, layout.status);
    if (r.refused) layout.result_refused = r.refused;
    else layout.result = r.result;
  }
  return { layout };
}

// A replay result -> { result } or { refused: code }. As a feed result's (normalizeItemResult), with:
//   field_state  "pending" (a field, awaiting the pin check) or "unassociated" (no field); after verifyPinnedFields():
//                "verified", "mismatch" or "file_check_unavailable"
//   grid         the field (Float32Array, row 0 at y = 0) ONLY while pending or verified; otherwise null, not kept
//   grid_text, result_text  while pending only: the texts a pin's field_sha256 and result_sha256 cover (resultText)
//   field_key    the verified field's sha256 (its content identity), else null
//   evaluator, guard, verification, replay  null: a bundled record names its evaluator through its pin only
export function normalizeResult(raw, status) {
  if (!isObj(raw)) return { refused: "result_malformed" };
  if (!SCORED.includes(status)) return { refused: "result_not_scored_state" };
  if (raw.label !== RESULT_LABEL) return { refused: "result_label_unknown" };
  if (raw.metric_id !== BOARD_METRIC.id) return { refused: "metric_unknown" };
  if (!inTemp(raw.value_C)) return { refused: "metric_value" };
  if (!num(raw.precision_K) || raw.precision_K <= 0 || raw.precision_K > 1) return { refused: "precision_missing" };
  let grid = null, gridText = null;
  if (raw.grid64 !== undefined && raw.grid64 !== null) {
    if (raw.row0 !== "bottom" && raw.row0 !== "top") return { refused: "grid_orientation_missing" };
    const g = raw.grid64;
    if (!Array.isArray(g) || g.length !== GRID_CELLS) return { refused: "grid_size" };
    grid = new Float32Array(GRID_CELLS);
    for (let row = 0; row < 64; row += 1) {
      const from = raw.row0 === "bottom" ? row : 63 - row;     // our row 0 is always y = 0
      for (let col = 0; col < 64; col += 1) {
        const v = g[from * 64 + col];
        if (!inTemp(v)) return { refused: "grid_value" };
        grid[row * 64 + col] = v;
      }
    }
    gridText = JSON.stringify(g);   // the exact text a pin's field_sha256 covers
  }
  const distinct = [];
  for (const [key, name] of Object.entries(DISTINCT_FIELDS)) {
    if (raw[key] === undefined || raw[key] === null) continue;
    if (!inTemp(raw[key])) return { refused: "distinct_value" };
    distinct.push({ key, name, value: raw[key] });
  }
  const pending = grid !== null;
  return { result: { metric: { id: BOARD_METRIC.id, value: raw.value_C, precision_K: raw.precision_K }, claim: RESULT_LABEL,
    label: labelFor(undefined), evaluator: null, field_state: pending ? "pending" : "unassociated", grid: pending ? grid : null,
    grid_text: pending ? gridText : null, result_text: pending ? resultText(raw) : null, field_key: null, diagnostic: true, distinct,
    guard: null, verification: null, replay: null } };
}

// The rest of a result record, exactly as bundled: every field but grid64 (its orientation row0, the value, precision
// and claim label, the distinct statistics, and anything else in it), in canonical form. A pin's result_sha256 covers
// this text, so a pinned result's orientation and every number shown with it are checked, not just its field.
export const resultText = (raw) => canonical(Object.fromEntries(Object.entries(raw).filter(([key]) => key !== "grid64")));

// ── the admitted associations: pinned fields, rechecked with WebCrypto before anything is drawn ─────────────────────
// layouts: normalized layouts. subtle: globalThis.crypto.subtle, or null where WebCrypto is unavailable (D14: then no
// result field is drawn). Returns new layouts; a result's field is drawable only when field_state is "verified". Only a
// bundled result is ever "pending": a feed result is unassociated from the start and never reaches a pin.
const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
export const geometryText = (layout) => canonical({ dies: layout.dies.map(({ die, x_um, y_um, rot_deg }) => ({ die, x_um, y_um, rot_deg })) });
export async function verifyPinnedFields(layouts, { subtle = globalThis.crypto?.subtle ?? null, pins = FIELD_PINS } = {}) {
  const sha256 = async (text) => hex(await subtle.digest("SHA-256", new TextEncoder().encode(text)));
  const out = [];
  for (const L of layouts) {
    const r = L.result;
    if (!r || r.field_state !== "pending") { out.push(L); continue; }
    const pin = pins.find((p) => p.layout_id === L.id) ?? null;
    let state = "unassociated", key = null, label = labelFor(undefined);
    if (pin && !subtle) state = "file_check_unavailable";
    else if (pin) {
      const [geometry, field, record] = await Promise.all([sha256(geometryText(L)), sha256(r.grid_text), sha256(r.result_text)]);
      if (geometry === pin.geometry_sha256 && field === pin.field_sha256 && record === pin.result_sha256) { state = "verified"; key = field; label = labelFor(pin.evaluator_identity); }
      else state = "mismatch";
    }
    const verified = state === "verified";
    out.push({ ...L, result: { ...r, field_state: state, grid: verified ? r.grid : null, grid_text: null, result_text: null, field_key: key, label,
      diagnostic: !verified } });
  }
  return out;
}

// A replay document ({ schema: REPLAY_SCHEMA, fixture: true, layouts: [...] }) -> { layouts, refused: { code: count } }.
export function normalizeReplay(doc) {
  const refused = {};
  const list = isObj(doc) && Array.isArray(doc.layouts) ? doc.layouts : null;
  if (!list) return { layouts: [], refused: { not_a_replay: 1 } };
  const layouts = [], ids = new Set();
  for (const raw of list.slice(0, BOUNDS.layouts)) {
    const n = normalizeLayout(raw);
    if (n.refused) { refused[n.refused] = (refused[n.refused] ?? 0) + 1; continue; }
    if (ids.has(n.layout.id)) { refused.id_duplicate = (refused.id_duplicate ?? 0) + 1; continue; }
    ids.add(n.layout.id);
    layouts.push(n.layout);
  }
  if (list.length > BOUNDS.layouts) refused.over_cap = list.length - BOUNDS.layouts;
  return { layouts, refused };
}

// ── the arrival list: merge by id ────────────────────────────────────────────────────────────────────────────────
// A later record for the same id updates its status and result (a layout arrives queued, then gets scored). A record
// never replaces a newer one: when the held record has a version (seq), the incoming one must have a version at least
// as new, else it is a stale or replayed answer and is dropped. Order: the door's admission order (arrival) when every
// record has one, else the order each id was first seen (the replay).
export const isOlder = (incoming, held) => Number.isSafeInteger(held.seq) && !(Number.isSafeInteger(incoming.seq) && incoming.seq >= held.seq);
export function mergeArrivals(current, incoming) {
  const byId = new Map(current.map((l) => [l.id, l]));
  const order = current.map((l) => l.id);
  for (const l of incoming) {
    const held = byId.get(l.id);
    if (!held) { order.push(l.id); byId.set(l.id, l); continue; }
    if (!isOlder(l, held)) byId.set(l.id, l);
  }
  const list = order.map((id) => byId.get(id));
  if (!list.every((l) => count(l.arrival))) return list;
  return list.map((l, i) => [l, i]).sort((a, b) => a[0].arrival - b[0].arrival || a[1] - b[1]).map(([l]) => l);
}

// ── the bundled replay file ──────────────────────────────────────────────────────────────────────────────────────
export const FIXTURE_URL = new URL("./door-fixture.json", import.meta.url).href;
export async function loadFixture({ fetchImpl = (...a) => fetch(...a), url = FIXTURE_URL } = {}) {
  const r = await fetchImpl(url, { cache: "no-store" });
  if (r.status !== 200) throw new Error(`the fixture answered ${r.status}`);
  const body = await readBodyCapped(r, MAX_API_BYTES, "too_large");
  if (!body.ok) throw new Error("the fixture is over 4 MiB");
  const doc = strictJson(body.bytes);
  if (!isObj(doc) || doc.schema !== REPLAY_SCHEMA || doc.fixture !== true) throw new Error("not a door fixture");
  return normalizeReplay(doc);
}

// ── the API seam ─────────────────────────────────────────────────────────────────────────────────────────────────
// The two GETs the page makes, through the Worker's read-only /api/* proxy, each with the integer cursor and nothing
// else. They follow no redirect, read at most 4 MiB, and never throw: { ok: true, ...page } or { ok: false, error }.
export const DOOR_RESULTS_PATH = "/api/open/v1/door/results";
export const DOOR_EVENTS_PATH = "/api/open/v1/door/events";
async function getPage(path, after, normalize, what, { fetchImpl = (...a) => fetch(...a), signal = undefined } = {}) {
  const cursor = count(after) ? after : 0;
  let r;
  try {
    r = await fetchImpl(`${path}?after=${cursor}`, { method: "GET", cache: "no-store", redirect: "error", headers: { accept: "application/json" }, signal });
  } catch {
    return { ok: false, error: "unreachable" };
  }
  if (r.status !== 200) { r.body?.cancel?.().catch?.(() => {}); return { ok: false, error: `answered ${r.status}` }; }
  let doc;
  try {
    const body = await readBodyCapped(r, MAX_API_BYTES, "too_large");
    if (!body.ok) return { ok: false, error: "answer over 4 MiB" };
    doc = strictJson(body.bytes);
  } catch {
    return { ok: false, error: "answer is not JSON" };
  }
  const page = normalize(doc);
  if (!page) return { ok: false, error: `answer is not a door ${what} page` };
  if (page.next_after < cursor) return { ok: false, error: "the cursor went backwards" };
  return { ok: true, ...page };
}
export const fetchDoorResults = (after = 0, opts = {}) => getPage(DOOR_RESULTS_PATH, after, normalizeResults, "results", opts);
export const fetchDoorEvents = (after = 0, opts = {}) => getPage(DOOR_EVENTS_PATH, after, normalizeEvents, "events", opts);

// ── the poller ───────────────────────────────────────────────────────────────────────────────────────────────────
// Every POLL_MS after a good answer, BACKOFF_MS after a failure, paused while the tab is hidden. Each poll reads the
// results, then the events, each page by page while has_more (up to MAX_PAGES); a poll is good only when both answer.
// onChange(state) after every poll. A cursor only moves on a good page. stop() ends the epoch: it aborts the request in
// flight, and an answer that still arrives for an ended epoch is discarded before it touches the state or calls
// onChange. start() begins a new epoch.
export const POLL_MS = 3000;
export const BACKOFF_MS = 5000;
export const LIVE_FRESH_MS = 12000;
export const MAX_PAGES = 8;
export function createDoorFeed({ onChange = () => {}, fetchImpl = (...a) => fetch(...a), now = () => Date.now(),
  fetchResults = fetchDoorResults, fetchEvents = fetchDoorEvents } = {}) {
  const state = { layouts: [], cursor: 0, events: [], eventsCursor: 0, connected: null, lastOkAt: null, error: "", refused: {}, polls: 0 };
  let timer = null, stopped = true, epoch = 0, controller = null;
  const tally = (refused) => { for (const [k, v] of Object.entries(refused)) state.refused[k] = (state.refused[k] ?? 0) + v; };
  // Pages of one feed until has_more is false; false when a page failed (the error is in state.error), null when stopped.
  async function drain(mine, fetchPage, cursorKey, take) {
    for (let page = 0; page < MAX_PAGES; page += 1) {
      controller = typeof AbortController === "function" ? new AbortController() : null;
      const got = await fetchPage(state[cursorKey], { fetchImpl, signal: controller?.signal });
      if (mine !== epoch) return null;            // stopped (or restarted) while waiting: discard, change nothing
      state.polls += 1;
      if (!got.ok) { state.error = got.error; return false; }
      tally(got.refused);
      take(got);
      const moved = got.next_after > state[cursorKey];
      state[cursorKey] = got.next_after;
      if (!got.has_more || !moved) break;
    }
    return true;
  }
  async function pollOnce() {
    const mine = epoch;
    const results = await drain(mine, fetchResults, "cursor", (got) => { state.layouts = mergeArrivals(state.layouts, got.layouts); });
    if (results === null) return null;
    const events = results ? await drain(mine, fetchEvents, "eventsCursor", (got) => { state.events = mergeEvents(state.events, got.events); }) : false;
    if (events === null || mine !== epoch) return null;
    const ok = results && events;
    state.connected = ok;
    if (ok) { state.error = ""; state.lastOkAt = now(); }
    onChange(state);
    return ok ? POLL_MS : BACKOFF_MS;
  }
  async function tick() {
    if (stopped) return;
    if (typeof document !== "undefined" && document.hidden) { schedule(BACKOFF_MS); return; }
    const mine = epoch, delay = await pollOnce();
    if (mine === epoch && delay !== null) schedule(delay);
  }
  const schedule = (ms) => { clearTimeout(timer); if (!stopped) timer = setTimeout(tick, ms); };
  return {
    state, pollOnce,
    get epoch() { return epoch; },
    start() { if (!stopped) return; stopped = false; epoch += 1; tick(); },
    stop() { stopped = true; epoch += 1; clearTimeout(timer); controller?.abort(); controller = null; },
  };
}

// The status line: "replay", "staging" or "live". Live data counts as live only while the last good answer is fresh;
// on a staging host (staging.*, or this machine) it is "staging". Anything else (the fixture, a replay, a feed that
// stopped answering) is "replay".
export function hostEnv(hostname) {
  const h = String(hostname ?? "");
  return h.startsWith("staging.") || ["localhost", "127.0.0.1", "[::1]"].includes(h) ? "staging" : "production";
}
export function statusLine({ source, feed = null, hostname = "", nowMs = Date.now() }) {
  if (source !== "api" || !feed || feed.connected !== true || feed.lastOkAt === null || nowMs - feed.lastOkAt > LIVE_FRESH_MS) return "replay";
  return hostEnv(hostname) === "staging" ? "staging" : "live";
}
