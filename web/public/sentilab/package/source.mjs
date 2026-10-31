// SentiLab Package view: the ONE place this page gets verified data. It uses the shared view code, exactly as the
// Lab view (lab.js) does, and hands package.js a small, version-neutral result:
//   - replay files: paging.mjs verifyReplayBytes() (VIEW ENVELOPE v0.6 bytes-to-rows, then the v0.5 browser core:
//     input checks before any hashing, duplicates and conflicts, the projectable prefix);
//   - live: the v0.6 cursor reducer from paging.mjs (initialState / request / step, cursor + cursor_hash, the 409, 413
//     and paging-unsupported terminal states), verifyRows() over every row held, and rule 5's label from liveLabel()
//     over view-core's progressTracker(): "LIVE · progress N s ago", "STALE · chain broken", "STALE · <reason>".
//     There is no seq paging anywhere.
// The trust rules are the Lab view's, unchanged:
//   - pins come only from view-pins.js (the deployed page), never from a replay file, its manifest or the API;
//   - ?pins=test (keys anyone can derive) is honoured only on a local server, exactly as lab.js does;
//   - only the projectable prefix (verified, in-run, unbroken from seq 1, before any conflict) is handed on for drawing.
import { VIEW_PINS } from "../view-pins.js";
import { checkLine, readBodyCapped, progressTracker, parseKeyResponse, publicKeyFromSeedText, sha256Hex, VERSION, MAX_LINE_BYTES, MAX_FILE_BYTES, MAX_API_BYTES } from "../view-core.mjs";
import { initialState, request as pageRequest, step as pageStep, verifyRows, verifyReplayBytes, splitRows, rowText, liveLabel, REASON_TEXT, MAX_LIMIT } from "../paging.mjs";
import { reasonText, chainSummary, isDrill as anyDrill, isRejected } from "../lab-model.mjs";

export const CONTRACT_VERSION = `${VERSION} (live paging: view-envelope/0.6.1)`;
export const DEMO = Object.freeze({ url: "../demo-run.jsonl", runId: "demo-8c-0001", label: "demo-run.jsonl · bundled interface fixture" });
// The Lab view's rule (lab.js TEST_PIN_HOSTS): anyone can derive the test keys, so a public host must never accept
// them; there they would let a forged file show as verified on our domain.
export const TEST_PIN_HOSTS = Object.freeze(["localhost", "127.0.0.1", "[::1]"]);
export const TEST_KEY_NAMES = Object.freeze(["core"]);
export const testPinsAllowed = (hostname) => TEST_PIN_HOSTS.includes(String(hostname));
export { MAX_FILE_BYTES, reasonText, chainSummary };
const MAX_SMALL_JSON = 256 * 1024;              // /api/view/runs and /api/view/key are small; a bigger answer is refused
const MAX_PAGES_PER_POLL = 16;                  // as the reference client loop and lab.js
export const LIVE_POLL_MS = 1000;
export const LIVE_BACKOFF_MS = 5000;

const isObj = (x) => x !== null && typeof x === "object" && !Array.isArray(x);
const strictJson = (bytes) => JSON.parse(new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(bytes));
const encoder = new TextEncoder();

// ── trust ───────────────────────────────────────────────────────────────────────────────────────────────────
// Returns { pins, keys, testMode, note }. `fetchKey` is only called for the production pin path.
export async function setupTrust({ hostname, wantsTest, fetchKey = defaultFetchKey } = {}) {
  if (wantsTest && testPinsAllowed(hostname)) {
    const pins = [], keys = {};
    try {
      for (const name of TEST_KEY_NAMES) {
        const raw = await publicKeyFromSeedText(`sentilab-view-test-key:${name}`);
        pins.push({ key_id: name, key_sha256: await sha256Hex(raw) });
        keys[name] = raw;
      }
      return { pins, keys, testMode: true, note: "TEST KEYS: derived in this page from a public seed rule; anyone can sign with them" };
    } catch {
      return { pins: [], keys: {}, testMode: true, note: "TEST KEYS requested, but this browser cannot derive Ed25519 keys" };
    }
  }
  const pins = VIEW_PINS.map((p) => ({ key_id: p.key_id, key_sha256: p.key_sha256 }));
  let keys = {}, note;
  if (pins.length === 0) note = "no production key is pinned in this page yet, so no envelope can verify";
  else {
    // The core may serve the key; verification uses it only if its sha256 matches a pin.
    const got = await fetchKey();
    keys = got.keys;
    note = got.note;
  }
  if (wantsTest) note = `TEST KEYS are only honoured on a local server; ${note}`;
  return { pins, keys, testMode: false, note };
}

async function defaultFetchKey() {
  try {
    const r = await fetch("/api/view/key", { cache: "no-store" });
    if (!r.ok) return { keys: {}, note: `pinned key not served (/api/view/key answered ${r.status})` };
    const body = await readBodyCapped(r, MAX_SMALL_JSON, "too_large");
    if (!body.ok) return { keys: {}, note: "pinned key not read (/api/view/key answered with more than 256 KiB)" };
    return { keys: parseKeyResponse(strictJson(body.bytes)), note: "pinned key fetched from /api/view/key and checked against the pin" };
  } catch {
    return { keys: {}, note: "pinned key not served (/api/view/key unreachable)" };
  }
}
const optionsFor = (runId, trust) => ({ runId, pins: trust.pins, keys: trust.keys });

// ── verification result, version-neutral for package.js and the tests ────────────────────────────────────────
//   ordered          per row, the envelope (null for a row rejected by the input checks), in the verifier's order
//   rows             per row: { seq, event_id, status, reasons, projected }
//   prefixEnvelopes  ONLY the projectable prefix; the scene is built from these and nothing else
//   prefixEnd (K), frozen, label ("chain broken after seq K; board frozen at seq K"), chainOk, verified, total
//   projection       project() over the prefix (the verifier's), projectionError
//   firstBreak       the first row after the prefix, with plain-word reasons
export function normalize(v, runId) {
  const after = v.rows[v.prefix] ?? null;
  return {
    runId,
    ordered: v.ordered,
    rows: v.rows,
    prefixEnvelopes: v.ordered.slice(0, v.prefix),
    prefixCount: v.prefix,
    prefixEnd: v.prefix_end,
    frozen: v.frozen,
    label: v.label,
    chainOk: v.chain_ok,
    total: v.rows.length,
    verified: v.rows.filter((r) => r.status === "verified").length,
    duplicates: v.duplicates ?? 0,
    inputIndex: (v.meta ?? []).map((m) => m.index),      // per row, its position in the input (duplicates dropped)
    projection: v.projection,
    projectionError: v.projection_error,
    firstBreak: after ? {
      seq: after.seq, status: after.status, reasons: [...after.reasons], rejected: isRejected(after),
      text: after.reasons.map(reasonText).join(", "),
      keyOnly: !isRejected(after) && after.reasons.length > 0 && after.reasons.every((r) => ["key_not_pinned", "key_unavailable", "ed25519_unsupported"].includes(r)),
    } : null,
  };
}

// Any well-formed withdraw whose reason starts "drill" (the Lab view's rule; over-labelling a drill is the safe error).
export const isDrill = (verification) => anyDrill((verification?.ordered ?? []).filter(Boolean));

// ── replay files ────────────────────────────────────────────────────────────────────────────────────────────
// A file the user opened carries no request, so the view checks it against the run named by the lowest-seq row that
// passes the input checks (read, never hashed), and says so on screen. The Lab view's rule.
export function runIdFromRows(rows) {
  let first = null;
  for (const row of rows) {
    const text = row.length <= MAX_LINE_BYTES ? rowText(row) : null;
    const checked = text === null ? null : checkLine(text);
    if (checked?.ok && (first === null || checked.value.event.seq < first.event.seq)) first = checked.value;
  }
  return first ? first.run.run_id : "";
}

// bytes: the file's raw bytes (never decoded whole). Returns { ok, runId, runIdFrom, verification } or
// { ok: false, error }. Over 64 MiB, nothing is split or decoded.
export async function verifyReplayFile(bytes, { runId = null, trust }) {
  if (!(bytes instanceof Uint8Array) || bytes.length > MAX_FILE_BYTES) return { ok: false, error: `the file is over the ${MAX_FILE_BYTES / (1024 * 1024)} MiB replay cap, so it was not read` };
  let runIdFrom = "requested";
  if (!runId) { runId = runIdFromRows(splitRows(bytes)); runIdFrom = "file"; }
  const r = await verifyReplayBytes(bytes, optionsFor(runId, trust));
  if (!r.ok) return { ok: false, error: r.reason };
  return { ok: true, runId, runIdFrom, verification: normalize(r.verification, runId) };
}
// Fetch a replay file as raw bytes, stopping past the 64 MiB cap (the Lab view rule: never read or decode it whole).
export async function fetchReplayBytes(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`${url} answered ${r.status}`);
  const body = await readBodyCapped(r, MAX_FILE_BYTES, "file_too_large");
  if (!body.ok) throw new Error(`${url} is over the ${MAX_FILE_BYTES / (1024 * 1024)} MiB replay cap, so it was not read`);
  return body.bytes;
}
// Text or a list of envelopes as a replay file (tests and the CLI's cross-check): each envelope one JSONL row.
export const replayBytes = (input) => encoder.encode(typeof input === "string" ? input : `${input.map((e) => JSON.stringify(e)).join("\n")}\n`);

// ── live: the v0.6 cursor reducer, one page at a time ────────────────────────────────────────────────────────
// A live run's state: the paging state (rows, cursor, cursor_hash, failure, degraded), the rule 5 progress tracker,
// and the normalized verification of every row held. Pure apart from the tracker, which is the shared one.
export function createLive(runId, { limit = MAX_LIMIT } = {}) {
  return { runId, paging: initialState(runId, { limit }), tracker: progressTracker(), verification: null };
}
// The next request ({ cursor, limit, cursor_hash? }), or null in a terminal state (409, 413, paging unsupported).
export const liveRequest = (live) => pageRequest(live.paging);
// One response to liveRequest(live). A valid page re-verifies every row held when rows arrived (a late conflict at an
// old seq still reaches the view and shrinks K), and feeds the tracker; a failed poll keeps nothing.
export async function applyPage(live, response, nowMs, trust) {
  const result = await pageStep(live.paging, response, nowMs);
  live.paging = result.state;
  if (result.outcome === "ok") {
    if (result.newRows.length > 0 || live.verification === null) {
      live.verification = normalize((await verifyRows(live.paging, optionsFor(live.runId, trust))).verification, live.runId);
    }
    live.tracker.poll({ nowMs, ok: true, K: live.verification.prefixEnd, received: result.newRows.length });
  } else {
    live.tracker.poll({ nowMs, ok: false });
  }
  return { outcome: result.outcome, newRows: result.newRows.length };
}
// Rule 5's label (v0.6.1), from paging.mjs liveLabel(): a failed latest poll shows its reason; a frozen board (anything
// after the prefix, including K cut back below its high) is "STALE · chain broken" at once; otherwise the tracker
// decides (LIVE · progress N s ago, or STALE).
export function liveModeOf(live, nowMs) {
  // frozen: anything follows the projectable prefix (v0.6.1 rule 5): LIVE never shows next to a frozen board.
  const label = liveLabel(live.paging, live.tracker, nowMs, live.verification?.prefixEnd ?? 0, live.verification?.frozen ?? false);
  const mode = label.startsWith("LIVE") ? "LIVE" : "STALE";
  const reason = mode === "STALE" && label.includes(" · ") ? label.slice(label.indexOf(" · ") + 3) : null;
  return { mode, reason, label };
}
// { mode, reason, label } for the header. A replay file is always REPLAY; live before any run is STALE.
export function modeNow(kind, live, nowMs) {
  if (kind === "file") return { mode: "REPLAY", reason: null, label: "REPLAY" };
  return live ? liveModeOf(live, nowMs) : { mode: "STALE", reason: null, label: "STALE" };
}
export { REASON_TEXT };

// The browser poller: GET /api/view/runs, then GET /api/view/events?run_id=&cursor=&limit=[&cursor_hash=], draining up
// to 16 pages a poll while x-has-more is true, then every 1 s from the last cursor. Terminal states stop it for good;
// only a reload (a new feed) starts over from cursor 0. onChange() is called after every poll.
async function fetchPage(runId, req) {
  const query = new URLSearchParams({ run_id: runId, cursor: String(req.cursor), limit: String(req.limit) });
  if (req.cursor_hash !== undefined) query.set("cursor_hash", req.cursor_hash);
  let r;
  try { r = await fetch(`/api/view/events?${query}`, { cache: "no-store" }); } catch { return null; }   // transport
  if (r.status !== 200) { r.body?.cancel().catch(() => {}); return { status: r.status, headers: r.headers, bodyBytes: new Uint8Array(0) }; }
  // Raw bytes, never decoded whole; reading stops past 4 MiB, and a body that isn't read whole fails as transport.
  const body = await readBodyCapped(r, MAX_API_BYTES, "response_too_large").catch(() => ({ ok: false }));
  return { status: 200, headers: r.headers, bodyBytes: body.ok ? body.bytes : null };
}

export function createLiveFeed({ trust, runId = null, onChange }) {
  const state = { runs: null, runsAt: 0, runId, live: runId ? createLive(runId) : null, connected: null, error: "" };
  let timer = null, stopped = true;
  const schedule = (ms) => { clearTimeout(timer); if (!stopped) timer = setTimeout(poll, ms); };
  async function poll() {
    if (stopped) return;
    if (state.live?.paging.degraded) { onChange(); return; }   // stopped for good; a reload starts over
    if (typeof document !== "undefined" && document.hidden) return schedule(LIVE_BACKOFF_MS);
    try {
      if (!state.runs || !state.runId || Date.now() - state.runsAt > 15000) {
        const r = await fetch("/api/view/runs", { cache: "no-store" });
        if (!r.ok) throw new Error(`/api/view/runs answered ${r.status}`);
        const body = await readBodyCapped(r, MAX_SMALL_JSON, "too_large");
        if (!body.ok) throw new Error("/api/view/runs answered with more than 256 KiB");
        const doc = strictJson(body.bytes);
        state.runs = (Array.isArray(doc) ? doc : isObj(doc) && Array.isArray(doc.runs) ? doc.runs : [])
          .filter((x) => isObj(x) && typeof x.run_id === "string" && x.run_id.length <= 128).slice(0, 200);
        state.runsAt = Date.now();
        state.connected = true;
        if (!state.runId && state.runs.length) state.runId = state.runs[0].run_id;
        if (state.runId && !state.live) state.live = createLive(state.runId);
        if (!state.runId) { onChange(); return schedule(LIVE_BACKOFF_MS); }
      }
    } catch (error) {
      state.connected = false;
      state.error = String(error?.message ?? error);
      onChange();
      return schedule(LIVE_BACKOFF_MS);
    }
    const live = state.live;
    let outcome = "ok";
    for (let pages = 0; pages < MAX_PAGES_PER_POLL; pages += 1) {
      const req = liveRequest(live);
      if (req === null) break;                        // terminal: request() sends nothing more
      const response = await fetchPage(live.runId, req);
      ({ outcome } = await applyPage(live, response, Date.now(), trust));
      if (outcome !== "ok" || !live.paging.has_more) break;
    }
    state.connected = outcome !== "transport";
    state.error = outcome === "ok" ? "" : REASON_TEXT[outcome] ?? outcome;
    onChange();
    if (!live.paging.degraded) schedule(outcome !== "ok" ? LIVE_BACKOFF_MS : live.paging.has_more ? 0 : LIVE_POLL_MS);
  }
  return {
    state,
    start() { if (!stopped) return; stopped = false; poll(); },
    stop() { stopped = true; clearTimeout(timer); },
    poke() { if (!stopped) { clearTimeout(timer); poll(); } },
  };
}
