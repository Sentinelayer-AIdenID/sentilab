// SentiLab Package view: the agent-door feed. The ONE place the 3D view gets CPU-DRAM layouts, from a static fixture
// today and, later, from the API through the Worker's read-only /api/* proxy (polling only: the Worker strips
// upgrade, so there are no WebSockets). Pure apart from fetchDoorResults() and the poller; the node tests drive both
// with a scripted fetch and clock.
//
// What a layout may say, and nothing more (every other field is dropped unread):
//   id       [a-z0-9][a-z0-9._-]{0,79}: a key only, never shown
//   label    "<class> · <short>": class from CLASSES, short = 4 lowercase hex. Rebuilt here from those two parts; a
//            label that is anything else refuses the layout. This is the only name the page shows: never free text.
//   dies     exactly C0, C1, C2, C3, D0, D1, D2, D3, each { die, x_um, y_um, rot_deg }: the die CENTRE in micrometres
//            (origin at the interposer's lower-left corner), and a catalogue rotation (CPU 0 or 90, DRAM 0)
//   status   a contract lifecycle state (STATUSES); "reference" and "example" only in a fixture
//   seq      optional record version (a non-negative integer that grows with every change to the record): an older
//            version never replaces a newer one. Arrival order is the order each id is first seen.
//   result   optional, from the scorer: { metric_id, value_C, precision_K, label, grid64?, row0?,
//            native_all_block_max_C?, active_layer_peak_C? }
//            metric_id    exactly "max_chiplet_centre_cell_mean_C" (BOARD_METRIC): the one frozen statistic of the
//                         board and of the 3D caption; value_C is its value in °C and precision_K its grid precision.
//                         The page shows the API's value and never recomputes it from the grid.
//            label        "simulated, not silicon": the scorer's claim label; any other label is not drawn
//            grid64       4096 temperatures in °C, row-major, 64 x 64 over the 45 mm chip layer: the active-layer
//                         temperature field, drawn as the colour map
//            row0         "bottom" (row 0 at y = 0) or "top" (row 0 at y = 45 mm): required with grid64, never guessed
//            native_all_block_max_C, active_layer_peak_C: distinct statistics, shown apart under their own names and
//                         never as the board metric
// A layout that breaks a rule is refused whole (never drawn, counted with its reason code). A result that breaks a
// rule is dropped and the layout drawn without a map or value, with the reason. Nothing visitor-written can reach
// the page; any other field (a definition, a note, a name) is dropped unread.
//
// Payload shape is not provenance (CAD/3D freeze section 5.7, PL-2, PL-6, D14). A result's FIELD is drawn only when an
// admitted association binds it: a pin in reviewed page code (case-cpu-dram.mjs FIELD_PINS) whose geometry and field
// digests the page recomputes with WebCrypto (verifyPinnedFields). The door feed is unsigned, so an API result's field
// is always "unassociated": never drawn, never kept; its scalar value stays as a qualified diagnostic. Every
// temperature carries a shared label (temperature-label.mjs LABELS), resolved by labelFor() from a VERIFIED evaluator
// identity, never from the payload's claim: with none, labelFor(undefined) is "unvalidated".
import { DIE_IDS, dieById, RULES, FIELD_PINS } from "./case-cpu-dram.mjs";
import { readBodyCapped, MAX_API_BYTES } from "../view-core.mjs";
import { strictJson } from "../runs-list.mjs";
import { canonical } from "../canonical.mjs";
import { labelFor } from "../../temperature-label.mjs";

export const FEED_SCHEMA = "sentilab-door-layouts/1";
export const CLASSES = Object.freeze(["reference-only", "reference", "example", "ours", "verified_agent", "signed_agent",
  "declared_agent", "crawler_claimed", "automation", "likely_human", "unknown"]);
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
export const RESULT_LABEL = "simulated, not silicon";
export const GRID_CELLS = 64 * 64;
export const BOUNDS = Object.freeze({
  // A centre may sit off the interposer by half its width (a refused or out-of-frame proposal still draws); past
  // that it can't be a layout of this case at all.
  centre_um: Object.freeze({ min: -22500, max: 67500 }),   // half an interposer (22.5 mm) beyond each edge, in µm
  temp_c: Object.freeze({ min: -50, max: 500 }),
  layouts: 500,
});
const ID = /^[a-z0-9][a-z0-9._-]{0,79}$/;
const SHORT = /^[0-9a-f]{4}$/;
const isObj = (x) => x !== null && typeof x === "object" && !Array.isArray(x);
const num = (x) => typeof x === "number" && Number.isFinite(x);

// "<class> · <short>": the separator is " · " (U+00B7 between spaces); nothing before, between or after.
export function parseLabel(label) {
  if (typeof label !== "string" || label.length > 40) return null;
  const parts = label.split(" · ");
  if (parts.length !== 2 || !CLASSES.includes(parts[0]) || !SHORT.test(parts[1])) return null;
  return { cls: parts[0], short: parts[1] };
}
export const labelText = (cls, short) => `${cls} · ${short}`;

// One raw layout -> { layout } or { refused: code }. source: "fixture" | "api".
export function normalizeLayout(raw, { source = "api" } = {}) {
  if (!isObj(raw)) return { refused: "not_an_object" };
  if (raw.hidden === true) return { refused: "hidden" };
  if (typeof raw.id !== "string" || !ID.test(raw.id)) return { refused: "id_invalid" };
  const lab = parseLabel(raw.label);
  if (!lab) return { refused: "label_invalid" };
  const statuses = source === "fixture" ? [...STATUSES, ...FIXTURE_STATUSES] : STATUSES;
  if (!statuses.includes(raw.status)) return { refused: "status_unknown" };
  if (!Array.isArray(raw.dies) || raw.dies.length !== DIE_IDS.length) return { refused: "dies_count" };
  const seen = new Map();
  for (const d of raw.dies) {
    if (!isObj(d) || typeof d.die !== "string" || !DIE_IDS.includes(d.die)) return { refused: "die_unknown" };
    if (seen.has(d.die)) return { refused: "die_duplicate" };
    if (![d.x_um, d.y_um, d.rot_deg].every(num)) return { refused: "coord_not_number" };
    const { min, max } = BOUNDS.centre_um;
    if (d.x_um < min || d.x_um > max || d.y_um < min || d.y_um > max) return { refused: "coord_out_of_range" };
    if (!RULES.rotations_deg[dieById(d.die).kind].includes(d.rot_deg)) return { refused: "rotation_not_allowed" };
    seen.set(d.die, { die: d.die, x_um: d.x_um, y_um: d.y_um, rot_deg: d.rot_deg });
  }
  const layout = {
    id: raw.id, cls: lab.cls, short: lab.short, label: labelText(lab.cls, lab.short), status: raw.status,
    seq: Number.isSafeInteger(raw.seq) && raw.seq >= 0 ? raw.seq : null,
    dies: DIE_IDS.map((id) => seen.get(id)),
    result: null, result_refused: null,
  };
  if (raw.result !== undefined && raw.result !== null) {
    const r = normalizeResult(raw.result, layout.status, { source });
    if (r.refused) layout.result_refused = r.refused;
    else layout.result = r.result;
  }
  return { layout };
}

// A result -> { result } or { refused: code }. result:
//   metric       { id, value, precision_K }: the scorer's value of the board metric
//   label        a temperature-label.mjs LABELS object for every temperature of this result (PL-2): labelFor() of the
//                verified evaluator identity; until verifyPinnedFields() admits an association, labelFor(undefined)
//   claim        the scorer's claim label ("simulated, not silicon"), shown beside the shared label, never instead of it
//   field_state  "unassociated" (API: unsigned feed; or no pin), "pending" (bundled, awaiting the pin check), and after
//                verifyPinnedFields(): "verified", "mismatch" or "file_check_unavailable"
//   grid         the field (Float32Array, row 0 at y = 0) ONLY while pending or verified; otherwise null, not kept
//   field_key    the verified field's sha256 (its content identity), else null
//   diagnostic   true while no association is admitted: the value is shown qualified, as a diagnostic
//   distinct     [{ key, name, value }] statistics shown apart, by name
export function normalizeResult(raw, status, { source = "api" } = {}) {
  if (!isObj(raw)) return { refused: "result_malformed" };
  if (!SCORED.includes(status)) return { refused: "result_not_scored_state" };
  if (raw.label !== RESULT_LABEL) return { refused: "result_label_unknown" };
  if (raw.metric_id !== BOARD_METRIC.id) return { refused: "metric_unknown" };
  const { min, max } = BOUNDS.temp_c;
  const inTemp = (v) => num(v) && v >= min && v <= max;
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
  // The door feed is unsigned: an API field is unassociated, never kept. A bundled field waits for its pin check.
  const pending = source === "fixture" && grid !== null;
  return { result: { metric: { id: BOARD_METRIC.id, value: raw.value_C, precision_K: raw.precision_K }, claim: RESULT_LABEL,
    label: labelFor(undefined), field_state: pending ? "pending" : "unassociated", grid: pending ? grid : null,
    grid_text: pending ? gridText : null, field_key: null, diagnostic: true, distinct } };
}

// ── the admitted associations: pinned fields, rechecked with WebCrypto before anything is drawn ─────────────────────
// layouts: normalized layouts. subtle: globalThis.crypto.subtle, or null where WebCrypto is unavailable (D14: then no
// result field is drawn). Returns new layouts; a result's field is drawable only when field_state is "verified".
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
      const [geometry, field] = await Promise.all([sha256(geometryText(L)), sha256(r.grid_text)]);
      if (geometry === pin.geometry_sha256 && field === pin.field_sha256) { state = "verified"; key = field; label = labelFor(pin.evaluator_identity); }
      else state = "mismatch";
    }
    const verified = state === "verified";
    out.push({ ...L, result: { ...r, field_state: state, grid: verified ? r.grid : null, grid_text: null, field_key: key, label,
      diagnostic: !verified } });
  }
  return out;
}

// A document ({ layouts: [...], next?, env? }) -> { layouts, refused: { code: count }, next, env }.
export function normalizeFeed(doc, { source = "api" } = {}) {
  const refused = {};
  const count = (code) => { refused[code] = (refused[code] ?? 0) + 1; };
  const list = isObj(doc) && Array.isArray(doc.layouts) ? doc.layouts : null;
  if (!list) return { layouts: [], refused: { not_a_feed: 1 }, next: null, env: null };
  const layouts = [], ids = new Set();
  for (const raw of list.slice(0, BOUNDS.layouts)) {
    const n = normalizeLayout(raw, { source });
    if (n.refused) { count(n.refused); continue; }
    if (ids.has(n.layout.id)) { count("id_duplicate"); continue; }
    ids.add(n.layout.id);
    layouts.push(n.layout);
  }
  if (list.length > BOUNDS.layouts) refused.over_cap = list.length - BOUNDS.layouts;
  const next = typeof doc.next === "string" && doc.next.length <= 128 && /^[A-Za-z0-9._:-]*$/.test(doc.next) ? doc.next : null;
  const env = doc.env === "staging" || doc.env === "production" ? doc.env : null;
  return { layouts, refused, next, env };
}

// ── the arrival list: merge by id, keep the order of first arrival ───────────────────────────────────────────────
// A later record for the same id updates its status and result (a layout arrives queued, then gets scored); its place
// in the arrival order never changes. A record never replaces a newer one: when the held record has a version (seq),
// the incoming one must have a version at least as new, else it is a stale or replayed answer and is dropped.
export const isOlder = (incoming, held) => Number.isSafeInteger(held.seq) && !(Number.isSafeInteger(incoming.seq) && incoming.seq >= held.seq);
export function mergeArrivals(current, incoming) {
  const byId = new Map(current.map((l) => [l.id, l]));
  const order = current.map((l) => l.id);
  for (const l of incoming) {
    const held = byId.get(l.id);
    if (!held) { order.push(l.id); byId.set(l.id, l); continue; }
    if (!isOlder(l, held)) byId.set(l.id, l);
  }
  return order.map((id) => byId.get(id));
}

// ── the fixture ──────────────────────────────────────────────────────────────────────────────────────────────────
export const FIXTURE_URL = new URL("./door-fixture.json", import.meta.url).href;
export async function loadFixture({ fetchImpl = (...a) => fetch(...a), url = FIXTURE_URL } = {}) {
  const r = await fetchImpl(url, { cache: "no-store" });
  if (r.status !== 200) throw new Error(`the fixture answered ${r.status}`);
  const body = await readBodyCapped(r, MAX_API_BYTES, "too_large");
  if (!body.ok) throw new Error("the fixture is over 4 MiB");
  const doc = strictJson(body.bytes);
  if (!isObj(doc) || doc.schema !== FEED_SCHEMA || doc.fixture !== true) throw new Error("not a door fixture");
  return normalizeFeed(doc, { source: "fixture" });
}

// ── the API seam ─────────────────────────────────────────────────────────────────────────────────────────────────
// THE one function the API lane wires: GET /api/open/v1/door/results?after=<cursor>, through the Worker's read-only
// /api/* proxy. `after` is the opaque cursor of the previous answer's `next` (null for the first call). It sends
// nothing but the cursor, follows no redirect, reads at most 4 MiB, and never throws: it returns
// { ok: true, layouts, refused, next, env, more } or { ok: false, error }.
export const DOOR_RESULTS_PATH = "/api/open/v1/door/results";
export async function fetchDoorResults(after = null, { fetchImpl = (...a) => fetch(...a), signal = undefined } = {}) {
  const query = after === null || after === undefined || after === "" ? "" : `?${new URLSearchParams({ after: String(after) })}`;
  let r;
  try {
    r = await fetchImpl(`${DOOR_RESULTS_PATH}${query}`, { method: "GET", cache: "no-store", redirect: "error", headers: { accept: "application/json" }, signal });
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
  if (!isObj(doc) || doc.schema !== FEED_SCHEMA) return { ok: false, error: "answer is not a door feed" };
  const feed = normalizeFeed(doc, { source: "api" });
  return { ok: true, ...feed, more: doc.more === true };
}

// ── the poller ───────────────────────────────────────────────────────────────────────────────────────────────────
// Every POLL_MS after a good answer (at once while `more` is true, up to 8 pages), BACKOFF_MS after a failure, and
// paused while the tab is hidden. onChange(state) after every poll. The cursor only moves on a good answer.
// stop() ends the epoch: it aborts the request in flight, and an answer that still arrives for an ended epoch is
// discarded before it touches the state or calls onChange. start() begins a new epoch.
export const POLL_MS = 3000;
export const BACKOFF_MS = 5000;
export const LIVE_FRESH_MS = 12000;
export function createDoorFeed({ onChange = () => {}, fetchImpl = (...a) => fetch(...a), now = () => Date.now(), fetchResults = fetchDoorResults } = {}) {
  const state = { layouts: [], cursor: null, connected: null, lastOkAt: null, error: "", env: null, refused: {}, polls: 0 };
  let timer = null, stopped = true, epoch = 0, controller = null;
  async function pollOnce() {
    const mine = epoch;
    let delay = POLL_MS;
    for (let page = 0; page < 8; page += 1) {
      controller = typeof AbortController === "function" ? new AbortController() : null;
      const got = await fetchResults(state.cursor, { fetchImpl, signal: controller?.signal });
      if (mine !== epoch) return null;            // stopped (or restarted) while waiting: discard, change nothing
      state.polls += 1;
      if (!got.ok) { state.connected = false; state.error = got.error; delay = BACKOFF_MS; break; }
      state.connected = true;
      state.error = "";
      state.lastOkAt = now();
      state.env = got.env ?? state.env;
      for (const [k, v] of Object.entries(got.refused)) state.refused[k] = (state.refused[k] ?? 0) + v;
      state.layouts = mergeArrivals(state.layouts, got.layouts);
      if (got.next !== null) state.cursor = got.next;
      if (!got.more || got.next === null) break;
    }
    if (mine !== epoch) return null;
    onChange(state);
    return delay;
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
// a staging host or an API that says it is staging is "staging". Anything else (the fixture, a replay, a feed that
// stopped answering) is "replay".
export function hostEnv(hostname) {
  const h = String(hostname ?? "");
  return h.startsWith("staging.") || ["localhost", "127.0.0.1", "[::1]"].includes(h) ? "staging" : "production";
}
export function statusLine({ source, feed = null, hostname = "", nowMs = Date.now() }) {
  if (source !== "api" || !feed || feed.connected !== true || feed.lastOkAt === null || nowMs - feed.lastOkAt > LIVE_FRESH_MS) return "replay";
  return feed.env === "staging" || hostEnv(hostname) === "staging" ? "staging" : "live";
}
