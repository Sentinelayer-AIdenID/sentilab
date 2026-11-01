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
//   seq      optional arrival sequence (a non-negative integer); otherwise arrival is the order first seen
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
import { DIE_IDS, dieById, RULES } from "./case-cpu-dram.mjs";
import { readBodyCapped, MAX_API_BYTES } from "../view-core.mjs";
import { strictJson } from "../runs-list.mjs";

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
    const r = normalizeResult(raw.result, layout.status);
    if (r.refused) layout.result_refused = r.refused;
    else layout.result = r.result;
  }
  return { layout };
}

// A result -> { result: { metric: { id, value, precision_K }, grid (Float32Array, row 0 at y = 0, or null), label,
// distinct: [{ key, name, value }] } } or { refused: code }.
export function normalizeResult(raw, status) {
  if (!isObj(raw)) return { refused: "result_malformed" };
  if (!SCORED.includes(status)) return { refused: "result_not_scored_state" };
  if (raw.label !== RESULT_LABEL) return { refused: "result_label_unknown" };
  if (raw.metric_id !== BOARD_METRIC.id) return { refused: "metric_unknown" };
  const { min, max } = BOUNDS.temp_c;
  const inTemp = (v) => num(v) && v >= min && v <= max;
  if (!inTemp(raw.value_C)) return { refused: "metric_value" };
  if (!num(raw.precision_K) || raw.precision_K <= 0 || raw.precision_K > 1) return { refused: "precision_missing" };
  let grid = null;
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
  }
  const distinct = [];
  for (const [key, name] of Object.entries(DISTINCT_FIELDS)) {
    if (raw[key] === undefined || raw[key] === null) continue;
    if (!inTemp(raw[key])) return { refused: "distinct_value" };
    distinct.push({ key, name, value: raw[key] });
  }
  return { result: { metric: { id: BOARD_METRIC.id, value: raw.value_C, precision_K: raw.precision_K }, grid, label: RESULT_LABEL, distinct } };
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
// A later record for the same id updates its status and result (a layout arrives queued, then gets scored); its
// place in the arrival order never changes. With seq on every layout, seq orders them.
export function mergeArrivals(current, incoming) {
  const byId = new Map(current.map((l) => [l.id, l]));
  const order = current.map((l) => l.id);
  for (const l of incoming) {
    if (!byId.has(l.id)) order.push(l.id);
    byId.set(l.id, l);
  }
  const out = order.map((id) => byId.get(id));
  if (out.every((l) => l.seq !== null)) out.sort((a, b) => a.seq - b.seq);
  return out;
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
export async function fetchDoorResults(after = null, { fetchImpl = (...a) => fetch(...a) } = {}) {
  const query = after === null || after === undefined || after === "" ? "" : `?${new URLSearchParams({ after: String(after) })}`;
  let r;
  try {
    r = await fetchImpl(`${DOOR_RESULTS_PATH}${query}`, { method: "GET", cache: "no-store", redirect: "error", headers: { accept: "application/json" } });
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
export const POLL_MS = 3000;
export const BACKOFF_MS = 5000;
export const LIVE_FRESH_MS = 12000;
export function createDoorFeed({ onChange = () => {}, fetchImpl = (...a) => fetch(...a), now = () => Date.now(), fetchResults = fetchDoorResults } = {}) {
  const state = { layouts: [], cursor: null, connected: null, lastOkAt: null, error: "", env: null, refused: {}, polls: 0 };
  let timer = null, stopped = true;
  async function pollOnce() {
    let delay = POLL_MS;
    for (let page = 0; page < 8; page += 1) {
      const got = await fetchResults(state.cursor, { fetchImpl });
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
    onChange(state);
    return delay;
  }
  async function tick() {
    if (stopped) return;
    if (typeof document !== "undefined" && document.hidden) { schedule(BACKOFF_MS); return; }
    schedule(await pollOnce());
  }
  const schedule = (ms) => { clearTimeout(timer); if (!stopped) timer = setTimeout(tick, ms); };
  return {
    state, pollOnce,
    start() { if (!stopped) return; stopped = false; tick(); },
    stop() { stopped = true; clearTimeout(timer); },
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
