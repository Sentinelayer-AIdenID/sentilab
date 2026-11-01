// SentiLab Live Lab: the page's state, derived only from what the door API and the lab-runs list reported. Pure apart
// from the three fetch helpers (which never throw), so the node tests drive it with recorded API answers
// (web/test/fixtures/livelab). The DOM controller (live.mjs) draws what these functions return and decides nothing.
//
// Sources, all same-origin, read-only GETs through the site's /api proxy:
//   the door feed  ../package/source3d.mjs createDoorFeed(): results (runs and their layouts) and events (arrivals,
//                  refused attempts, run state changes), with its own validation, paging, cursor and epoch rules. This
//                  module adds one thing to an event: the server's own time `at`, read only when it is a strict UTC
//                  timestamp (else null), so the page can say when a record was observed.
//   the board      GET /api/open/v1/door/board: the door (open or closed), the scorer, the queue and the compute budget.
//   lab runs       GET /api/view/runs (../runs-list.mjs): how many lab runs are listed, by status.
// Nothing here invents a value: no clock-driven movement, no random numbers, no sample records. A field the feeds do not
// carry (presence, identity, a page route) is reported as unknown, never guessed.
import { normalizeEvents, fetchDoorResults, LIVE_FRESH_MS, BOARD_METRIC, readScorer, statusLine, hostEnv, DOOR_EVENTS_PATH }
  from "../package/source3d.mjs";
import { stateLine, summaryLine, eventLine, codeWords } from "../package/status.mjs";
import { formatTemp } from "../package/temps.mjs";
import { dieRects } from "../package/model.mjs";
import { INTERPOSER_MM } from "../package/case-cpu-dram.mjs";
import { readBodyCapped, MAX_API_BYTES } from "../view-core.mjs";
import { strictJson, fetchRunsList } from "../runs-list.mjs";

export const BOARD_PATH = "/api/open/v1/door/board";
export const BOARD_SCHEMA = "sentilab-door-board/1";
export const BOARD_POLL_MS = 15000;
export const RUNS_POLL_MS = 30000;
const isObj = (x) => x !== null && typeof x === "object" && !Array.isArray(x);
const count = (n) => Number.isSafeInteger(n) && n >= 0;
const num = (x) => typeof x === "number" && Number.isFinite(x);
const CODE = /^[a-z][a-z0-9_]{0,47}$/;
// The server's timestamp on an event: ISO 8601 UTC with optional fraction, e.g. 2026-11-01T15:21:02.558110Z.
const AT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,9})?Z$/;
export const readAt = (x) => (typeof x === "string" && AT.test(x) && Number.isFinite(Date.parse(x)) ? x : null);

// ── fetching (never throws: { ok: true, ... } or { ok: false, error }) ───────────────────────────────────────────
async function getJson(path, { fetchImpl = (...a) => fetch(...a), signal = undefined, cap = MAX_API_BYTES } = {}) {
  let r;
  try {
    r = await fetchImpl(path, { method: "GET", cache: "no-store", redirect: "error", headers: { accept: "application/json" }, signal });
  } catch {
    return { ok: false, error: "unreachable" };
  }
  if (r.status !== 200) { r.body?.cancel?.().catch?.(() => {}); return { ok: false, error: `answered ${r.status}` }; }
  try {
    const body = await readBodyCapped(r, cap, "too_large");
    if (!body.ok) return { ok: false, error: "answer too large" };
    return { ok: true, doc: strictJson(body.bytes) };
  } catch {
    return { ok: false, error: "answer is not JSON" };
  }
}

// The events page, as source3d.mjs normalizes it, with each kept event's server time attached (by seq). Same rules as
// source3d's own events fetch: the integer cursor only, no redirect, at most 4 MiB, and a cursor that goes backwards is
// an error. createDoorFeed({ fetchEvents: fetchEventsTimed }) uses it in place of fetchDoorEvents.
export function normalizeEventsTimed(doc) {
  const page = normalizeEvents(doc);
  if (!page) return null;
  const at = new Map();
  for (const raw of Array.isArray(doc.events) ? doc.events.slice(0, 500) : []) if (isObj(raw) && count(raw.seq)) at.set(raw.seq, readAt(raw.at));
  return { ...page, events: page.events.map((e) => ({ ...e, at: at.get(e.seq) ?? null })) };
}
export async function fetchEventsTimed(after = 0, { fetchImpl, signal } = {}) {
  const cursor = count(after) ? after : 0;
  const got = await getJson(`${DOOR_EVENTS_PATH}?after=${cursor}`, { fetchImpl, signal });
  if (!got.ok) return got;
  const page = normalizeEventsTimed(got.doc);
  if (!page) return { ok: false, error: "answer is not a door events page" };
  if (page.next_after < cursor) return { ok: false, error: "the cursor went backwards" };
  return { ok: true, ...page };
}
export { fetchDoorResults };

// The board -> the four facts this page shows, each from its own field, or null for a field that is missing or
// malformed (shown as unavailable). Not a board at all -> null.
export function normalizeBoard(doc) {
  if (!isObj(doc) || doc.schema !== BOARD_SCHEMA) return null;
  const d = doc.door, q = doc.queue, g = doc.grant;
  const door = isObj(d) && typeof d.open === "boolean"
    ? { open: d.open, codes: Array.isArray(d.codes) ? d.codes.filter((c) => typeof c === "string" && CODE.test(c)).slice(0, 4) : [] } : null;
  const queue = isObj(q) && [q.length, q.max, q.active, q.parallel].every(count) ? { length: q.length, max: q.max, active: q.active, parallel: q.parallel } : null;
  const budget = isObj(g) && [g.cpu_s_cap, g.cpu_s_charged, g.cpu_s_remaining, g.cpu_s_reserved].every((v) => num(v) && v >= 0)
    ? { cap_s: g.cpu_s_cap, charged_s: g.cpu_s_charged, remaining_s: g.cpu_s_remaining, reserved_s: g.cpu_s_reserved } : null;
  return { door, scorer: readScorer(doc.scorer), queue, budget };
}
export async function fetchBoard({ fetchImpl, signal } = {}) {
  const got = await getJson(BOARD_PATH, { fetchImpl, signal });
  if (!got.ok) return got;
  const board = normalizeBoard(got.doc);
  return board ? { ok: true, board } : { ok: false, error: "answer is not a door board" };
}

// Lab runs: only the count and the statuses this page knows; nothing else from an entry is shown.
const RUN_STATUSES = Object.freeze(["running", "finished", "stopped"]);
export function summarizeLabRuns(list) {
  const byStatus = Object.fromEntries(RUN_STATUSES.map((s) => [s, 0]));
  let other = 0;
  for (const r of list) if (RUN_STATUSES.includes(r.status)) byStatus[r.status] += 1; else other += 1;
  return { total: list.length, byStatus, other };
}
export async function fetchLabRuns({ fetchImpl = (...a) => fetch(...a) } = {}) {
  try { return { ok: true, runs: summarizeLabRuns(await fetchRunsList(fetchImpl)) }; }
  catch (e) { return { ok: false, error: String(e?.message ?? e).slice(0, 120) }; }
}

// ── the connection state: the badge never says LIVE unless the door feed's last good answer is fresh ─────────────
// connecting  no answer yet
// live        the last poll answered, within LIVE_FRESH_MS, and there are records
// empty       the last poll answered, within LIVE_FRESH_MS, and the door has no records yet
// stale       there were good answers, but the last poll failed or the last good answer is older than LIVE_FRESH_MS
// error       no good answer ever: the feed is unreachable or answered with an error
// The word follows the shared rule (source3d.mjs statusLine): live data on a staging host or this machine is "staging".
export function feedStatus(feed, { nowMs = Date.now(), hostname = "" } = {}) {
  const s = feed ?? {};
  const fresh = s.lastOkAt !== null && s.lastOkAt !== undefined && nowMs - s.lastOkAt <= LIVE_FRESH_MS;
  const ageS = s.lastOkAt == null ? null : Math.max(0, Math.round((nowMs - s.lastOkAt) / 1000));
  if (s.connected === true && fresh) {
    const records = (s.layouts?.length ?? 0) + (s.events?.length ?? 0);
    const word = statusLine({ source: "api", feed: s, hostname, nowMs });   // "live" or "staging"; never "replay" here
    return { state: records ? "live" : "empty", word: records ? word.toUpperCase() : "NO RECORDS YET", host: hostEnv(hostname), ageS, error: "" };
  }
  if (s.connected === null || s.connected === undefined) return { state: "connecting", word: "CONNECTING", host: hostEnv(hostname), ageS, error: "" };
  if (s.lastOkAt != null) return { state: "stale", word: "STALE", host: hostEnv(hostname), ageS, error: s.error || "no fresh answer" };
  return { state: "error", word: "NOT CONNECTED", host: hostEnv(hostname), ageS, error: s.error || "no answer" };
}

// ── runs: the experiments rail and the selected run ──────────────────────────────────────────────────────────────
// Newest arrival first. The page's own key is the run id; it is never shown (the label is the run's only name).
export const runsNewestFirst = (layouts) => [...(layouts ?? [])].reverse();
// The run shown: the one selected while it is still in the feed, else the newest run with a score, else the newest.
export function pickRun(layouts, selectedId) {
  const list = layouts ?? [];
  return list.find((l) => l.id === selectedId) ?? [...list].reverse().find((l) => l.result) ?? list.at(-1) ?? null;
}
// What the result panel shows for one run. Bound to this run's own record: when the run changes, every value here
// changes with it (one object in, one view out); a run without a result in a scored state shows why there is none.
// at: a replay cursor at one of this run's records ({ kind: "run", run_id, state, seq, at }). A record carries a state
// and a time, never a value or a check, so as of that record the view shows only its state; the run's latest result
// and checks stay apart under `latest`, labelled as the latest, never as the state at the cursor.
export function runView(L, { at = null } = {}) {
  if (!L) return null;
  const cursor = at && at.kind === "run" && at.run_id === L.id ? at : null;
  const latest = latestOf(L);
  if (cursor) {
    const word = STATE_WORDS[cursor.state] ?? cursor.state.replace(/_/g, " ");
    return {
      id: L.id, label: L.label, cls: L.cls, short: L.short, status: cursor.state, seq: cursor.seq ?? null, arrival: L.arrival,
      state: word, summary: null, metric: null, metricName: BOARD_METRIC.name, metricDefinition: BOARD_METRIC.definition,
      none: `state at this record: ${word.toLowerCase()} · a record carries no value`,
      diagnostic: false, claim: null, evaluator: null, distinct: [], verification: null, replay: null, guard: null,
      atRecord: { state: cursor.state, seq: cursor.seq ?? null, at: cursor.at ?? null },
      latest, field: fieldOverlay(null),
    };
  }
  return { ...latest, id: L.id, label: L.label, cls: L.cls, short: L.short, arrival: L.arrival, summary: summaryLine(L), atRecord: null, latest: null, field: fieldOverlay(L) };
}
const STATE_WORDS = Object.freeze({ queued: "Queued", held: "Held", evaluating: "Evaluating", evaluated: "Evaluated", replaying: "Replaying",
  reproduced: "Reproduced", not_reproduced: "Not reproduced", cross_checked: "Cross-checked", failed: "Failed", cancelled: "Cancelled",
  expired: "Expired", rejected: "Rejected" });
// The run's latest record and result, as the results feed has it now.
function latestOf(L) {
  const r = L.result;
  const metric = r ? formatTemp(r.metric.value, r.label, { digits: 2 }) : null;
  const none = metric ? null : L.result_refused ? `score not shown · ${L.result_refused.replace(/_/g, " ")}` : stateLine(L) ? `not scored · ${stateLine(L)}` : "not scored";
  return {
    status: L.status, seq: L.seq, state: stateLine(L) ?? L.status, metric, metricName: BOARD_METRIC.name, metricDefinition: BOARD_METRIC.definition, none,
    diagnostic: Boolean(r?.diagnostic), claim: r ? r.claim : null,
    evaluator: r?.evaluator ?? null, distinct: r ? r.distinct.map((d) => ({ ...d, text: formatTemp(d.value, r.label, { digits: 2 }) })) : [],
    verification: r?.verification ?? null, replay: r?.replay ?? null, guard: r?.guard ?? null,
  };
}
// The heat overlay: only a verified field whose association to this exact layout was checked (source3d.mjs
// verifyPinnedFields). A door-feed result is always "unassociated" (the feed is unsigned) and carries no grid, so today
// the overlay is unavailable for every live run, and the page says so instead of colouring anything.
export function fieldOverlay(L) {
  const r = L?.result;
  if (r && r.field_state === "verified" && r.grid && r.field_key) return { available: true, key: r.field_key, reason: "" };
  if (!L) return { available: false, key: null, reason: "Field overlay unavailable: a record carries no field" };
  if (!r) return { available: false, key: null, reason: "Field overlay unavailable: this run has no result" };
  return { available: false, key: null, reason: "Field overlay unavailable: the door feed carries a scalar result, no temperature field for this layout" };
}
// The receipt: what the feed says this run's result was checked for, as the feed reports it (never verified here).
export function receiptOf(L) {
  if (!L) return null;
  const r = L.result;
  return {
    run: L.label, status: L.status, record_seq: L.seq, arrival: L.arrival, contract_summary: L.summary,
    codes: L.codes, reason: L.reason,
    result: r ? {
      metric_id: r.metric.id, value_C: r.metric.value, precision_K: r.metric.precision_K, temperature_label: r.label.state,
      claim: r.claim, diagnostic: r.diagnostic, field: r.field_state, evaluator_named_by_feed: r.evaluator,
      distinct: Object.fromEntries(r.distinct.map((d) => [d.key, d.value])), active_guard: r.guard, verification: r.verification, replay: r.replay,
    } : null,
    result_refused: L.result_refused,
  };
}
export function verificationWords(v) {
  if (!v) return "";
  const replay = v.replay === "reproduced"
    ? `replay reproduced${v.distinct_execution ? " in a distinct process" : ""}${v.receipts_bound ? ", receipts bound" : ""}`
    : `replay not reproduced${v.replay_code ? ` (${codeWords(v.replay_code)})` : ""}`;
  return `${replay}; not claimed: ${v.not_claimed.join(", ") || "nothing listed"}`;
}

// ── the door atlas: stations bound to the door's own records ─────────────────────────────────────────────────────
// Each station is a record type the door actually emits. A run sits at its last reported state (a task state); an
// arrival or a refused attempt is counted where it was observed. Nothing moves between stations on the page's own
// clock: a dot changes station only when a new record says so.
export const STATIONS = Object.freeze([
  { id: "door", n: "01", name: "Door", what: "arrival records" },
  { id: "submit", n: "02", name: "Submit", what: "refused or rejected attempts" },
  { id: "queue", n: "03", name: "Queue", what: "runs queued or held" },
  { id: "simulate", n: "04", name: "Simulator", what: "runs evaluating" },
  { id: "replay", n: "05", name: "Replay", what: "runs evaluated or replaying" },
  { id: "board", n: "06", name: "Board", what: "runs reproduced, not reproduced or cross-checked" },
]);
const STATION_OF = Object.freeze({ queued: "queue", held: "queue", evaluating: "simulate", evaluated: "replay", replaying: "replay",
  reproduced: "board", not_reproduced: "board", cross_checked: "board" });
export const stationOf = (status) => STATION_OF[status] ?? null;   // rejected, failed, cancelled, expired: out of the flow
export function atlas(layouts, events) {
  const runs = new Map(STATIONS.map((s) => [s.id, []]));
  const out = [];
  for (const L of layouts ?? []) {
    const st = stationOf(L.status);
    if (st) runs.get(st).push({ id: L.id, label: L.label, cls: L.cls, status: L.status });
    else out.push({ id: L.id, label: L.label, status: L.status });
  }
  const ev = events ?? [];
  const counts = Object.fromEntries(STATIONS.map((s) => [s.id, runs.get(s.id).length]));
  counts.door = ev.filter((e) => e.kind === "arrival").length;
  counts.submit = ev.filter((e) => e.kind === "attempt").length;
  return { stations: STATIONS.map((s) => ({ ...s, count: counts[s.id], runs: runs.get(s.id) })), out };
}

// ── follow the work: keyed on the full run id ────────────────────────────────────────────────────────────────────
// A label (class · 4-hex short id) can repeat across distinct runs and visitors, so nothing is merged on it:
//   runs   one row per full run id (results and run records): its submission (the run's first record, in a creation
//          state: queued, held or rejected; the run's own "location") and its task (its newest state). A run's later
//          state changes are the scorer's work, not a move. sameLabel counts the other runs in view with its label.
//   door   arrivals and refused attempts carry no run id: they are counted per label as a qualified group, never
//          attached to a run, and never presented as one visitor's history.
//   anonymous  arrivals without a token (no short id), counted by class.
const CREATION = Object.freeze(["queued", "held", "rejected"]);
export function followWork(events, layouts) {
  const runs = new Map(), door = new Map(), anonymous = new Map();
  for (const e of [...(events ?? [])].sort((x, y) => x.seq - y.seq)) {
    if (e.kind === "run") {
      const r = runs.get(e.run_id) ?? { run_id: e.run_id, label: e.label, cls: e.cls, short: e.short, submitted: null, task: null, records: 0, sameLabel: 0 };
      if (r.records === 0 && CREATION.includes(e.state)) r.submitted = { seq: e.seq, at: e.at ?? null, state: e.state };
      r.records += 1;
      r.task = { seq: e.seq, at: e.at ?? null, state: e.state };
      runs.set(e.run_id, r);
    } else if (e.short === null) {
      const a = anonymous.get(e.cls) ?? { cls: e.cls, count: 0, lastAt: null, lastSeq: -1 };
      a.count += 1; a.lastSeq = e.seq; a.lastAt = e.at ?? null;
      anonymous.set(e.cls, a);
    } else {
      const d = door.get(e.label) ?? { label: e.label, cls: e.cls, short: e.short, arrivals: 0, attempts: 0, last: null };
      if (e.kind === "arrival") d.arrivals += 1; else d.attempts += 1;
      d.last = { seq: e.seq, at: e.at ?? null, kind: e.kind, line: eventLine(e) };
      door.set(e.label, d);
    }
  }
  // A run in the results list with no record in the newest window still has its state, from the results feed.
  for (const L of layouts ?? []) {
    if (runs.has(L.id)) continue;
    runs.set(L.id, { run_id: L.id, label: L.label, cls: L.cls, short: L.short, submitted: null, task: { seq: L.seq ?? -1, at: null, state: L.status }, records: 0, sameLabel: 0 });
  }
  const list = [...runs.values()];
  for (const r of list) r.sameLabel = list.filter((x) => x.label === r.label && x.run_id !== r.run_id).length;
  return {
    runs: list.sort((a, b) => (b.task?.seq ?? -1) - (a.task?.seq ?? -1)),
    door: [...door.values()].sort((a, b) => b.last.seq - a.last.seq),
    anonymous: [...anonymous.values()].sort((a, b) => b.lastSeq - a.lastSeq),
  };
}
// The flight record's trails: consecutive records of one full run id, as [seq, seq] pairs. Never across run ids, and
// never from a door record (which has no run id) to a run.
export function traceLinks(events) {
  const last = new Map(), links = [];
  for (const e of [...(events ?? [])].sort((x, y) => x.seq - y.seq)) {
    if (e.kind !== "run") continue;
    if (last.has(e.run_id)) links.push([last.get(e.run_id), e.seq]);
    last.set(e.run_id, e.seq);
  }
  return links;
}

// ── the 2D fallback: the Package view's own 2D renderer (render.mjs), for a browser without WebGL2 ─────────────────
// The selected run's dies as render.mjs chiplets, exactly as the Package view's 2D path builds them (no temperature).
export const KIND_FILL_2D = Object.freeze({ CPU: "#9c86c8", DRAM: "#6f93b4" });
export const FOOTPRINT_2D = Object.freeze({
  substrate: Object.freeze({ x0: -1.5, y0: -1.5, x1: INTERPOSER_MM + 1.5, y1: INTERPOSER_MM + 1.5 }),
  interposer: Object.freeze({ x0: 0, y0: 0, x1: INTERPOSER_MM, y1: INTERPOSER_MM }),
});
export function chiplets2d(L) {
  const rects = dieRects(L?.dies);
  return rects ? rects.map((r) => ({ id: r.id, x: r.x0, y: r.y0, w: r.w, h: r.h, layer: 0, kind: "die", temp: null, temp_state: null, color: KIND_FILL_2D[r.kind] })) : [];
}
// Which view controls work with the renderer in use: explode, orbit and the camera reset are the 3D view's only.
export function viewControls(renderer) {
  const on = renderer === "3d";
  return { explode: on, orbit: on, reset: on, renderer };
}

// ── the flight record: the newest records the feed kept, in seq order, on three lanes ─────────────────────────────
export const LANES = Object.freeze(["arrival", "attempt", "run"]);
export function traceModel(events) {
  const list = [...(events ?? [])].sort((a, b) => a.seq - b.seq);
  const n = list.length;
  const points = list.map((e, i) => ({ seq: e.seq, at: e.at ?? null, kind: e.kind, lane: LANES.indexOf(e.kind), x: n <= 1 ? 0.5 : i / (n - 1),
    label: e.label, line: eventLine(e), state: e.state ?? null, run_id: e.run_id ?? null, outcome: e.outcome ?? null }));
  return { points, first: points[0] ?? null, last: points.at(-1) ?? null };
}
// "15:21:02Z" from a server timestamp; "time not recorded" for none.
export const hms = (at) => (at ? `${at.slice(11, 19)}Z` : "time not recorded");

// ── replay: an explicit selection over the records already received, with their original times ───────────────────
// cursor: an index into traceModel(events).points, or null for live (follow the newest).
export function clampCursor(cursor, n) {
  if (cursor === null || cursor === undefined || n === 0) return null;
  return Math.max(0, Math.min(n - 1, Math.trunc(cursor)));
}
