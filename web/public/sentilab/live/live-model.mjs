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
// Nothing here invents a value: no clock-driven movement, no random numbers, no sample records. A field the feeds do not
// carry (presence, identity, a page route) is reported as unknown, never guessed.
import { normalizeEvents, fetchDoorResults, LIVE_FRESH_MS, BOARD_METRIC, readScorer, statusLine, hostEnv, DOOR_EVENTS_PATH }
  from "../package/source3d.mjs";
import { stateLine, summaryLine, eventLine, codeWords, reasonWords } from "../package/status.mjs";
import { formatTemp } from "../package/temps.mjs";
import { dieRects } from "../package/model.mjs";
import { INTERPOSER_MM } from "../package/case-cpu-dram.mjs";
import * as W from "./words.mjs";
import { readBodyCapped, MAX_API_BYTES } from "../view-core.mjs";
import { strictJson } from "../runs-list.mjs";

export const BOARD_PATH = "/api/open/v1/door/board";
export const BOARD_SCHEMA = "sentilab-door-board/1";
export const BOARD_POLL_MS = 15000;
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
  const extra = new Map();
  const ID = /^[a-z][a-z0-9_.-]{0,47}$/, NAME = /^[A-Za-z0-9][A-Za-z0-9 ._&+-]{0,39}$/;
  for (const raw of Array.isArray(doc.events) ? doc.events.slice(0, 500) : []) {
    if (!isObj(raw) || !count(raw.seq)) continue;
    at.set(raw.seq, readAt(raw.at));
    // A run record may one day carry visit_arrival (the exact arrival seq of the visit that sent it). Nothing sends it
    // yet; when present it is the only way a run is ever shown with a visitor's declared name.
    if (raw.kind === "run" && count(raw.visit_arrival)) extra.set(raw.seq, { visitArrival: raw.visit_arrival });
    if (raw.kind !== "arrival") continue;
    // An arrival's chosen purpose, and (when a feed carries them, checked by the door against the registry) the
    // operator's name, the service's name and the verification level: each read only in its exact shape.
    const x = {};
    if (typeof raw.purpose === "string" && ID.test(raw.purpose)) x.purpose = raw.purpose;
    // The door publishes these as operator_name and service_name (app/door/service.py); either spelling is read.
    const operatorName = raw.operator_name ?? raw.operatorName, serviceName = raw.service_name ?? raw.serviceName;
    if (typeof operatorName === "string" && NAME.test(operatorName)) x.operatorName = operatorName;
    if (typeof serviceName === "string" && NAME.test(serviceName)) x.serviceName = serviceName;
    if (["signature", "network", "claimed", "inferred", "unverified"].includes(raw.verification)) x.verification = raw.verification;
    if (["training_crawler", "search_crawler", "ai_assistant", "ai_agent", "preview_bot", "monitor", "automation", "unknown", "human"].includes(raw.category)) x.category = raw.category;
    extra.set(raw.seq, x);
  }
  return { ...page, events: page.events.map((e) => ({ ...e, at: at.get(e.seq) ?? null, ...(extra.get(e.seq) ?? {}) })) };
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

// ── the request gate: every request the page makes goes through it (review item P1-2(b)) ────────────────────────────
// Spacing: at least GAP_MS, plus up to GAP_JITTER_MS, between two requests, so a backlog of pages (the feed drains up
// to 8 pages per feed per poll) never bursts. Backoff: after a 429 or 503 nothing is sent before the answer's
// Retry-After (seconds or an HTTP date) has passed; after those, after a 500, 502 or 504 and after a failed
// connection, an exponential backoff from BACKOFF_BASE_MS, doubling up to BACKOFF_MAX_MS, holds too. Other answers
// (a 404 from a route this API does not have, say) are the asking feed's business, not a reason to silence the page. Each wait is stretched by a random factor of up to
// 1 + JITTER, so many pages that failed together do not retry together. A good answer resets the backoff. The jitter
// comes from crypto.getRandomValues: network timing only, never anything the page shows.
export const GATE = Object.freeze({ GAP_MS: 300, GAP_JITTER_MS: 200, BACKOFF_BASE_MS: 5000, BACKOFF_MAX_MS: 60000, JITTER: 0.5 });
const cryptoRandom = () => globalThis.crypto.getRandomValues(new Uint32Array(1))[0] / 4294967296;
// Retry-After -> milliseconds from now, or null when absent or unreadable.
export function retryAfterMs(value, nowMs) {
  if (value === null || value === undefined) return null;
  const v = String(value).trim();
  if (/^\d{1,7}$/.test(v)) return Number(v) * 1000;
  const at = Date.parse(v);
  return Number.isFinite(at) ? Math.max(0, at - nowMs) : null;
}
function abortableSleep(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) { reject(signal.reason ?? new Error("aborted")); return; }
    const id = setTimeout(resolve, ms);
    signal?.addEventListener?.("abort", () => { clearTimeout(id); reject(signal.reason ?? new Error("aborted")); }, { once: true });
  });
}
export function createGate({ fetchImpl = (...a) => fetch(...a), now = () => Date.now(), random = cryptoRandom, sleep = abortableSleep } = {}) {
  // Two deadlines, kept apart so neither can shorten the other: nextAt, the spacing slot the last launch reserved, and
  // embargoUntil, the backoff a 429/503 (its Retry-After) or a failure set. Only a later, longer embargo replaces one.
  let nextAt = -Infinity, embargoUntil = -Infinity, embargoSetAt = -Infinity, failures = 0;
  // Slots are taken one caller at a time (a promise chain): a caller waits for the one before it, then sleeps and
  // rechecks both deadlines until they have passed (a 429 may arrive while it sleeps). Then, in one synchronous step
  // with no await in between, it reserves its slot and calls fetch (review item, dispatch): no microtask can delay the
  // real dispatch past its reservation, so spacing holds where fetch is called and an already-reserved request
  // cannot cross a 429 taken in after it. The turn is released at once; the answer is awaited outside it. An aborted
  // caller gives its turn up at once.
  let turn = Promise.resolve();
  async function dispatch(url, init) {
    const signal = init.signal;
    const before = turn;
    let release;
    turn = new Promise((resolve) => { release = resolve; });
    try {
      await before;
      for (;;) {
        if (signal?.aborted) throw signal.reason ?? new Error("aborted");
        const wait = Math.max(nextAt, embargoUntil) - now();
        if (wait <= 0) break;
        await sleep(wait, signal);
      }
      const startedAt = now();
      nextAt = startedAt + GATE.GAP_MS + random() * GATE.GAP_JITTER_MS;
      let answer;
      try { answer = Promise.resolve(fetchImpl(url, init)); } catch (e) { answer = Promise.reject(e); }
      answer.catch(() => {});                          // handled by the caller; never an unhandled rejection here
      return { startedAt, answer };
    } finally {
      release();
    }
  }
  const backoff = (retryMs) => {
    failures += 1;
    const base = Math.max(retryMs ?? 0, Math.min(GATE.BACKOFF_MAX_MS, GATE.BACKOFF_BASE_MS * 2 ** (failures - 1)));
    const until = now() + base * (1 + random() * GATE.JITTER);
    if (until > embargoUntil) embargoUntil = until;
    embargoSetAt = now();
  };
  async function gated(url, init = {}) {
    const { startedAt, answer } = await dispatch(url, init);
    let r;
    try { r = await answer; } catch (e) { if (!init.signal?.aborted) backoff(null); throw e; }
    if (r.status === 429 || r.status === 503) backoff(retryAfterMs(r.headers?.get?.("retry-after"), now()));
    else if (r.status === 500 || r.status === 502 || r.status === 504) backoff(null);
    // A success resets the backoff count only when it started after the last embargo was set; it never lifts an
    // embargo (that ends only with time), so an earlier request answering late cannot undo a 429.
    else if (r.status === 200 && startedAt >= embargoSetAt) failures = 0;
    return r;
  }
  return { fetch: gated, get failures() { return failures; }, get nextAt() { return Math.max(nextAt, embargoUntil); } };
}

// ── self-declared visitor text: the door's /visitors feed (docs/sentilab/DOOR-VISITORS.md) ──────────────────────────
// A visitor that opts in declares a name (at most 64 code points), a reason (160) and a source category. It is public,
// self-reported display data: never an identity, never instructions. This page shows it in its own list, one entry per
// declaration event (declarationList), as plain text clipped to those limits, labelled "self-declared, not verified";
// a hidden declaration reads "hidden by the operator" and nothing else. It is never attached to a run. A hide keeps its seq and does not
// move the feed's cursor, so every poll reads the whole window again from the start and replaces what the page holds
// (fetchVisitorsWindow): a hide reaches a tab that is already open on its next poll.
export const VISITORS_PATH = "/api/open/v1/door/visitors";
export const VISITORS_SCHEMA = "sentilab-door-visitors/1";
export const VISITORS_POLL_MS = 3000;
export const VISITORS_SLOW_MS = 60000;           // after a 404: an API without the feed is asked again a minute later
export const VISITORS_FRESH_MS = 10000;          // declarations older than this are no longer shown (a hide may be missed)
export const VISITORS_MAX_PAGES = 4;             // a restart at the real window, then up to 3 pages of 500
export const DECLARATION_LIMITS = Object.freeze({ name: 64, reason: 160 });
export const DECLARED_NOTE = "self-declared, not verified";
export const HIDDEN_TEXT = "hidden by the operator";
export const UNREADABLE_TEXT = "self-declared text not shown: characters this page does not display";
const SOURCES = Object.freeze(["moltbook", "senti", "github", "direct", "other"]);
const HIDE_REASONS = Object.freeze(["privacy", "abuse", "spam", "other"]);
const EVENT_KINDS = Object.freeze(["passive_arrival", "declaration", "legacy_unclassified"]);
const VISITOR_CLASSES = Object.freeze(["verified_agent", "signed_agent", "declared_agent", "crawler_claimed", "automation", "likely_human", "unknown", "ours"]);
// Characters the API refuses and this page will not display either: controls, bidi and zero-width formatting, other
// default-ignorables, line and paragraph separators, private use, and lone surrogates (code points, so a surrogate
// pair, an emoji, is not one).
const UNSHOWABLE = /[\u0000-\u001f\u007f-\u009f\u00ad\u034f\u061c\u115f\u1160\u17b4\u17b5\u180b-\u180f\u200b-\u200f\u2028-\u202e\u2060-\u206f\u3164\ud800-\udfff\ue000-\uf8ff\ufe00-\ufe0f\ufeff\uffa0\ufff0-\ufffb\u{1bca0}-\u{1bca3}\u{1d173}-\u{1d17a}\u{e0000}-\u{e0fff}\u{f0000}-\u{10ffff}]/u;
export const clipCodePoints = (s, n) => Array.from(String(s)).slice(0, n).join("");
const showable = (s) => typeof s === "string" && !UNSHOWABLE.test(s);

// A visitors page -> { items, next_after, has_more }, or null when it is not one. item: { seq, at, cls, short, label,
// kind, hidden (a reason code) or null, declaration: { name, reason, source } or null }. A hidden row never carries
// text here, even if an answer wrongly sends some. An item whose label is not its class and short id rebuilt is dropped.
export function normalizeVisitors(doc) {
  if (!isObj(doc) || doc.schema !== VISITORS_SCHEMA || !Array.isArray(doc.items) || !count(doc.next_after) || typeof doc.has_more !== "boolean") return null;
  const items = [];
  for (const raw of doc.items.slice(0, 500)) {
    if (!isObj(raw) || !count(raw.seq) || !VISITOR_CLASSES.includes(raw.class) || !EVENT_KINDS.includes(raw.event_kind)) continue;
    const short = raw.short_id === null || raw.short_id === undefined ? null : typeof raw.short_id === "string" && /^[0-9a-f]{4}$/.test(raw.short_id) ? raw.short_id : undefined;
    if (short === undefined || raw.label !== (short === null ? raw.class : `${raw.class} · ${short}`)) continue;
    const hidden = raw.hidden === undefined || raw.hidden === null ? null : HIDE_REASONS.includes(raw.hidden) ? raw.hidden : "other";
    let declaration = null;
    if (!hidden && raw.event_kind === "declaration" && isObj(raw.declaration)) {
      const d = raw.declaration;
      declaration = { name: typeof d.name === "string" ? d.name : "", reason: typeof d.reason === "string" ? d.reason : "", source: SOURCES.includes(d.source) ? d.source : null };
    }
    // arrival: the seq of the arrival event from the same pass (the door's exact relation), on a shown declaration only.
    const arrival = declaration && count(raw.arrival) ? raw.arrival : null;
    items.push({ seq: raw.seq, at: readAt(raw.at), cls: raw.class, short, label: raw.label, kind: raw.event_kind, hidden, declaration, arrival });
  }
  const through = isObj(doc.counts) && count(doc.counts.through_seq) ? doc.counts.through_seq : null;
  return { items, next_after: doc.next_after, has_more: doc.has_more, through };
}
// The declarations as their own list: every declaration event (shown or hidden), newest first by its event seq, at
// most `max`. Root's rule (#103 P2): a class and a 4-hex short id can be shared by unrelated runs and passes, so a
// declaration is never joined to a run, a card or a row by label or short id. Each event stands alone; an older
// declaration is its own entry, and hiding one changes only its own entry.
export function declarationList(items, { max = 20 } = {}) {
  return (items ?? []).filter((x) => x.kind === "declaration").sort((a, b) => b.seq - a.seq).slice(0, max)
    .map((x) => ({ seq: x.seq, at: x.at, view: declarationView(x) }));
}
// What the page shows for one declaration event: { kind: "declared", name, reason, source, note, seq },
// { kind: "hidden", text, seq }, { kind: "unreadable", text, seq }, or null.
export function declarationView(item) {
  if (!item) return null;
  if (item.hidden) return { kind: "hidden", text: HIDDEN_TEXT, seq: item.seq };
  const d = item.declaration;
  if (!d) return null;
  if (!showable(d.name) || !showable(d.reason)) return { kind: "unreadable", text: UNREADABLE_TEXT, seq: item.seq };
  return { kind: "declared", name: clipCodePoints(d.name, DECLARATION_LIMITS.name), reason: clipCodePoints(d.reason, DECLARATION_LIMITS.reason),
    source: d.source, note: DECLARED_NOTE, seq: item.seq };
}
// The window: the latest VISITORS_WINDOW door records (seqs are shared by every door record, so the window holds the
// arrivals among them), read to its end on every poll and replacing what the page held, so a hide reaches an open tab
// on its next poll (root's P2: no fixed page count from the start, which silently missed the newest declarations once
// the history grew). The start is rounded down to a multiple of VISITORS_ROUND, so tabs ask for the same URLs and share
// the proxy's 2 s micro-cache; rounding only widens the window. latest: the newest seq the page knows (the events
// cursor, or the last read's through_seq); when the first page shows the window starts later than that, the read
// restarts there once. Returns { ok, partial, items, from, through } or { ok: false, error }: a page cap reached with
// more to read is partial, never a plain ok, and a failed page is an error, never a shorter list.
export const VISITORS_WINDOW = 1000;
export const VISITORS_ROUND = 100;
export const visitorsWindowStart = (latest) => Math.floor(Math.max(0, (Number.isSafeInteger(latest) ? latest : 0) - VISITORS_WINDOW) / VISITORS_ROUND) * VISITORS_ROUND;
export async function fetchVisitorsWindow({ fetchImpl, signal, latest = 0, maxPages = VISITORS_MAX_PAGES } = {}) {
  let from = visitorsWindowStart(latest), after = from, items = [], through = null, restarted = false;
  for (let page = 0; page < maxPages; page += 1) {
    const got = await getJson(`${VISITORS_PATH}?after=${after}&limit=500`, { fetchImpl, signal });
    if (!got.ok) return { ok: false, error: got.error };
    const p = normalizeVisitors(got.doc);
    if (!p) return { ok: false, error: "answer is not a door visitors page" };
    if (through === null && p.through !== null) {
      through = p.through;
      const exact = visitorsWindowStart(through);
      if (!restarted && exact > from) { from = exact; after = exact; items = []; restarted = true; continue; }
    }
    items.push(...p.items);
    if (!p.has_more) return { ok: true, partial: false, items, from, through: through ?? p.next_after };
    if (p.next_after <= after) return { ok: false, error: "the visitors cursor did not move" };
    after = p.next_after;
  }
  return { ok: true, partial: true, items, from, through };
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
// The run the model follows while the viewer hasn't picked one: the newest run that has a layout, whatever its
// state, so an agent's new submission is on the model at once (Carter, 18:38Z: "the middle thing moves if an agent
// did something"); its result fills in when the door has one. Without any layout, the same run pickRun shows.
export function followedRun(layouts) {
  const list = layouts ?? [];
  return [...list].reverse().find((l) => Array.isArray(l.dies) && l.dies.length > 0) ?? pickRun(list, null);
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
// ── copy: a run is titled by its short id; its class is a separate line (a class is a guess at the visitor's type) ──
// A run is titled by the visit id it came from, so a person can match it by eye to that visit; never a name (a
// shared 4-hex visit id is not proof of who made a layout).
export const runTitle = (L) => W.layoutFrom(L.short);
// The names visitors gave, built at render time and never stored: event seq -> declared name. Only from a visitors
// read that succeeded and is fresh; otherwise empty, so a hide or a failed or stale read clears every name on the
// next render. Exact relations only (never a label or a short id): each shown declaration names its own event, and
// the newest shown declaration that carries `arrival` names that arrival event.
export function declaredNames(decl, nowMs = Date.now()) {
  const names = new Map();
  if (!decl || decl.ok !== true || !decl.at || nowMs - decl.at > VISITORS_FRESH_MS) return names;
  const nameOf = (x) => { const v = declarationView(x); return v?.kind === "declared" && v.name !== "" ? v.name : null; };
  const newest = new Map();
  for (const x of decl.items ?? []) {
    if (x.kind !== "declaration" || x.hidden || !x.declaration) continue;
    const own = nameOf(x);
    if (own !== null) names.set(x.seq, own);
    if (count(x.arrival) && !(newest.get(x.arrival)?.seq > x.seq)) newest.set(x.arrival, x);
  }
  for (const [arrival, x] of newest) { const n = nameOf(x); if (n !== null) names.set(arrival, n); else names.delete(arrival); }
  return names;
}
// A run's declared name: only through its own run records' visit_arrival (keyed on the full run id), else null.
export function runName(L, events, names) {
  if (!L || !names?.size) return null;
  const rec = [...(events ?? [])].filter((e) => e.kind === "run" && e.run_id === L.id && count(e.visitArrival)).sort((a, b) => b.seq - a.seq)[0];
  return rec ? names.get(rec.visitArrival) ?? null : null;
}
export const visitorType = (cls) => W.visitorType(cls);
// A record's title: a run record by its run's short id, a door record by its visitor's short id and type, an arrival
// without a token by its class.
export function recordTitle(p) {
  const [cls, short] = String(p.label).split(" · ");
  if (p.kind === "run") return p.state && W.RUN_STATE[p.state] ? `${W.layoutFrom(short)} ${W.RUN_STATE[p.state]}` : `Run ${short ?? ""} ${p.line}`.replace("  ", " ");
  const verb = p.kind === "arrival" ? (p.line === "sent a self-described declaration" ? W.TEXT.declared : W.TEXT.arrived) : p.line;
  return `${W.visitorSubject(cls)} ${verb}${short ? ` · visit ${short}` : ""}`;
}

// The arrivals, newest first (the door's arrival records only; never joined to a declaration or a run).
export function arrivalsOf(events, max = 12) {
  return [...(events ?? [])].filter((e) => e.kind === "arrival").sort((a, b) => b.seq - a.seq).slice(0, max)
    .map((e) => ({ seq: e.seq, at: e.at ?? null, cls: e.cls, short: e.short, purpose: e.purpose ?? null, declaration: e.event_kind === "declaration",
      operatorName: e.operatorName ?? null, serviceName: e.serviceName ?? null, verification: e.verification ?? null, category: e.category ?? null }));
}
// ── every door record: older pages on request, merged by seq (no gap, no duplicate) ─────────────────────────────────
// The events feed pages ascending from `after` (at most 200 a page). To go back from the oldest record held, ask for
// the range that ends just before it: after = oldest - 1 - limit. Its first `limit` answers cover that whole range,
// so nothing between two pages is skipped; whatever the page also returns at or past the oldest is already held.
export const RECORDS_PAGE = 200;
export const olderPage = (oldest, limit = RECORDS_PAGE) => ({ after: Math.max(0, oldest - 1 - limit), limit });
export async function fetchEventsPage(after, { fetchImpl, signal, limit = RECORDS_PAGE } = {}) {
  const got = await getJson(`${DOOR_EVENTS_PATH}?after=${after}&limit=${limit}`, { fetchImpl, signal });
  if (!got.ok) return got;
  const page = normalizeEventsTimed(got.doc);
  return page ? { ok: true, ...page } : { ok: false, error: "answer is not a door events page" };
}
export function mergeRecords(held, events) {
  const out = new Map(held);
  for (const e of events ?? []) if (!out.has(e.seq)) out.set(e.seq, e);
  return out;
}
// One record as a plain sentence (no class code, no seq): who did what.
export function recordSentence(e) {
  if (e.kind === "run") return `${W.layoutFrom(e.short)} ${W.RUN_STATE[e.state] ?? e.state.replace(/_/g, " ")}`;
  const who = W.CATEGORY?.[e.category] ?? W.visitorSubject(e.cls);
  const visit = e.short ? ` · visit ${e.short}` : "";
  if (e.kind === "attempt") return `${who} tried to submit a layout · refused: ${(e.codes ?? []).map(codeWords).join(", ") || "no reason given"}${visit}`;
  return `${who} ${e.event_kind === "declaration" ? W.TEXT.declared : W.TEXT.arrived}${visit}`;
}
// Every run's real outcome, from the results feed's own status, codes and reason, in plain words; the raw codes go in
// the title only. Accepted means scored by the simulator; the replay part says whether a fresh run matched.
export function runOutcome(L) {
  const r = L.result;
  const codes = [...(L.codes ?? []), ...(L.reason ? [L.reason] : [])];
  const title = codes.length ? codes.join(", ") : "";
  const why = (L.codes ?? []).map(codeWords).concat(L.reason ? [reasonWords(L.reason)] : []).join(", ");
  const temp = r ? `${W.METRIC_NAME.toLowerCase()} ${formatTemp(r.metric.value, r.label, { digits: 2 }).text} · simulated` : null;
  const replay = r?.verification?.replay === "reproduced" ? "replay matched" : r?.verification?.replay === "not_reproduced" ? "replay did not match" : "replay pending";
  // The step comes from the run's own state (root, f9cc6ab P2): "Accepted" only once the required result check has
  // finished; before that the page says which step the run is at.
  switch (L.status) {
    case "reproduced": case "cross_checked":
      return { kind: "accepted", text: temp ? `Accepted · ${temp} · ${replay}` : "Accepted · no temperature in the record", title };
    case "evaluated": case "replaying":
      return { kind: "waiting", text: temp ? `Re-checking (replay) · ${temp}` : "Re-checking (replay)", title };
    case "held": return { kind: "waiting", text: "Held", title };
    case "not_reproduced":
      return { kind: "accepted", text: temp ? `Scored · ${temp} · replay did not match` : "Scored · replay did not match", title };
    case "rejected": return { kind: "refused", text: `Refused · ${why || "no reason given"}`, title };
    case "failed": return { kind: "refused", text: `Could not be simulated · ${why || "no reason given"}`, title };
    case "cancelled": case "expired": return { kind: "refused", text: `Stopped · ${why || L.status}`, title };
    case "evaluating": return { kind: "waiting", text: "Simulating", title };
    case "queued": return { kind: "waiting", text: L.position ? `Waiting in line · number ${L.position}` : "Waiting in line", title };
    default: return { kind: "waiting", text: String(L.status ?? "unknown").replace(/_/g, " "), title };
  }
}
// "15:21:02Z" from a server timestamp; "time not recorded" for none.
export const hms = (at) => (at ? `${at.slice(11, 19)}Z` : "time not recorded");

// ── replay: an explicit selection over the records already received, with their original times ───────────────────
// The cursor is a record's seq (review item P2-1), never a position in the newest-40 window: when new records arrive
// and the window moves, a paused cursor stays on its record. cursorIndex finds it in the window; a record that has
// left the window falls to the nearest kept record after it (the newest when none is after it).
export function cursorIndex(points, seq) {
  if (seq === null || seq === undefined || !points?.length) return null;
  const exact = points.findIndex((p) => p.seq === seq);
  if (exact >= 0) return exact;
  const next = points.findIndex((p) => p.seq > seq);
  return next >= 0 ? next : points.length - 1;
}
// clampCursor: an index into traceModel(events).points, or null for live (follow the newest).
export function clampCursor(cursor, n) {
  if (cursor === null || cursor === undefined || n === 0) return null;
  return Math.max(0, Math.min(n - 1, Math.trunc(cursor)));
}
