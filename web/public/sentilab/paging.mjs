// Browser port of contracts/view-envelope-v0.6.2/paging.mjs (DRAFT v0.6.2, rules 4 and 5; reference sha256
// 43fb20fa..., text a5a04e9c...): live paging by a physical-row cursor, bound by a cursor hash, and the mode label. The
// logic follows the reference line for line. The only changes are the platform calls: SHA-256 comes from WebCrypto,
// so cursorHash(), step(), verifyBytes(), verifyReplayBytes() and verifyRows() are async; v0.5 verification and
// modeLabel() come from ./view-core.mjs (the browser port of the v0.5 reference) instead of the node reference; and the
// empty-log hash is the SHA-256 of nothing, written out, so initialState() stays synchronous. The server side
// (logRowsFromFile, servePage) is not ported: the page is only a client. web/test/sentilab-parity.test.mjs runs the
// reference's paging scenarios (C1-C6, C8-C17) and label cases through this file and compares every trace and label.
// Pure: no clock, network, randomness or shared state. Every input is an argument, and states are never mutated.
// Rows are raw bytes (Uint8Array) throughout; text appears only when a row is handed to v0.5 verification.
import { checkLine, modeLabel, verifyJsonl, sha256Hex } from "./view-core.mjs";

export const MAX_LIMIT = 256;
const MAX_PAGE_LINES = 256;
const MAX_PAGE_BYTES = 4 * 1024 * 1024;
const MAX_LINE_BYTES = 64 * 1024;
const MAX_FILE_BYTES = 64 * 1024 * 1024;
const LF = 0x0a;
const UNSUPPORTED = [400, 404, 501];
const COUNT = /^(0|[1-9][0-9]*)$/;
// The reason a failed poll shows after "STALE · ".
export const REASON_TEXT = { transport: "transport", paging_error: "paging error", stream_replaced: "stream replaced", row_too_large: "row too large", paging_unsupported: "paging unsupported" };

// SHA-256, lowercase hex, over the raw bytes of each row followed by one LF (that is, over joinRows(rows)).
export function cursorHash(rows) {
  return sha256Hex(joinRows(rows));
}
// cursorHash([]): the SHA-256 of nothing.
const EMPTY_CURSOR_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";

// Bytes to rows (rule 4): each row is decoded on its own as strict UTF-8, keeping any BOM.
// Returns the text, or null when the row isn't valid UTF-8.
const strictDecoder = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true });
export function rowText(row) {
  try {
    return strictDecoder.decode(row);
  } catch {
    return null;
  }
}

// A body is rows, each followed by LF. A trailing LF doesn't start a row; a blank line in the middle is a row.
function countLines(body) {
  let lines = 0;
  for (let i = 0; i < body.length; i += 1) if (body[i] === LF) lines += 1;
  return body.length > 0 && body[body.length - 1] !== LF ? lines + 1 : lines;
}
export function splitRows(body) {
  const rows = [];
  let start = 0;
  for (let i = 0; i < body.length; i += 1) {
    if (body[i] === LF) {
      rows.push(body.slice(start, i));
      start = i + 1;
    }
  }
  if (start < body.length) rows.push(body.slice(start));
  return rows;
}
export function joinRows(rows) {
  const body = new Uint8Array(rows.reduce((total, row) => total + row.length + 1, 0));
  let at = 0;
  for (const row of rows) {
    body.set(row, at);
    body[at + row.length] = LF;
    at += row.length + 1;
  }
  return body;
}

const header = (headers, name) => {
  if (!headers || typeof headers !== "object") return undefined;
  if (typeof headers.get === "function") return headers.get(name) ?? undefined;
  const key = Object.keys(headers).find((k) => k.toLowerCase() === name);
  return key === undefined ? undefined : headers[key];
};

// ---- The client. ----
// rows: every accepted raw row; cursor: how many rows were accepted; cursor_hash: their hash; has_more: the last
// page's x-has-more; last_ok_ms: client time of the last valid page; failure: why the latest poll failed, or null;
// degraded: "stream_replaced", "row_too_large" or "paging_unsupported" once one happens. Each is terminal: the
// client stops polling and the state stays until a manual reload (a new initialState).
// The mode inputs (rule 5) live here too: caught_up turns true at the first valid page with no more to fetch (the
// client has reached the end of the log once); catching_up says the last valid page arrived before that point, so
// its rows are history; high_k is the highest K reached; last_progress_ms is when K last grew after catch-up.
export function initialState(runId, { limit = MAX_LIMIT } = {}) {
  if (!Number.isSafeInteger(limit) || limit < 1 || limit > MAX_LIMIT) throw new RangeError("limit must be 1 to 256");
  return {
    run_id: runId, limit, rows: [], cursor: 0, cursor_hash: EMPTY_CURSOR_HASH, has_more: true, last_ok_ms: null, failure: null, degraded: null,
    caught_up: false, catching_up: false, high_k: 0, last_progress_ms: null,
  };
}

// The next request, or null in a terminal state. cursor_hash is sent with every cursor above 0. There is never a
// seq parameter.
export function request(state) {
  if (state.degraded) return null;
  const req = { cursor: state.cursor, limit: state.limit };
  if (state.cursor > 0) req.cursor_hash = state.cursor_hash;
  return req;
}

// One response to request(state). response: { status, headers, bodyBytes } or null for a failed transport.
// Returns { state, outcome, newRows }. outcome is ok, transport, paging_error, stream_replaced, row_too_large or
// paging_unsupported.
// A failed poll changes only failure (and degraded): no rows from it are kept, and the cursor never resets.
export async function step(state, response, nowMs) {
  if (state.degraded) return { state, outcome: state.degraded, newRows: [] };
  const fail = (reason, extra = {}) => ({ state: { ...state, ...extra, failure: reason }, outcome: reason, newRows: [] });
  const status = response?.status;
  if (status === 409) return fail("stream_replaced", { degraded: "stream_replaced" });
  // 413: the next row can never be paged. Terminal, so the same cursor is never asked for again.
  if (status === 413) return fail("row_too_large", { degraded: "row_too_large" });
  if (UNSUPPORTED.includes(status)) return fail("paging_unsupported", { degraded: "paging_unsupported" });
  if (status !== 200 || !(response.bodyBytes instanceof Uint8Array)) return fail("transport");
  // The v0.5 response caps, before anything is split or decoded.
  const body = response.bodyBytes;
  if (body.length > MAX_PAGE_BYTES || countLines(body) > MAX_PAGE_LINES) return fail("transport");
  // A conforming server ends every row with LF, so a non-empty body that doesn't end with LF is a paging error.
  if (body.length > 0 && body[body.length - 1] !== LF) return fail("paging_error");
  const rows = splitRows(body);
  const nextText = header(response.headers, "x-next-cursor");
  const next = typeof nextText === "string" && COUNT.test(nextText) ? Number(nextText) : NaN;
  if (!Number.isSafeInteger(next)) return fail("paging_error");
  if (next !== state.cursor + rows.length) return fail("paging_error");
  if (rows.length > state.limit) return fail("paging_error");
  // The client's own hash of every row it would now hold, over raw bytes.
  const combined = [...state.rows, ...rows];
  const ownHash = await cursorHash(combined);
  if (header(response.headers, "x-cursor-hash") !== ownHash) return fail("paging_error");
  // An empty page never asks for more, so a bad x-has-more can't make the client spin.
  const hasMore = header(response.headers, "x-has-more") === "true" && rows.length > 0;
  return {
    state: {
      ...state, rows: combined, cursor: next, cursor_hash: ownHash, has_more: hasMore, last_ok_ms: nowMs, failure: null,
      // Catching up is not progress: every page up to and including the first one with no more to fetch is history.
      catching_up: !state.caught_up, caught_up: state.caught_up || !hasMore,
    },
    outcome: "ok",
    newRows: rows,
  };
}

// ---- Verification over raw rows: rule 4's bytes-to-rows step, then v0.5's checks, unchanged. ----
const isPlainObject = (x) => x !== null && typeof x === "object" && !Array.isArray(x) && [Object.prototype, null].includes(Object.getPrototypeOf(x));
// v0.5's rule for a rejected row whose seq can be read.
const readSeq = (value) => (isPlainObject(value) && isPlainObject(value.event) && Number.isSafeInteger(value.event.seq) && value.event.seq >= 1 ? value.event.seq : null);

// v0.5 verification takes text. A row that isn't valid UTF-8 has no text, so it goes in as a stand-in that v0.5
// rejects without parsing anything real: an empty line (not_json, seq unreadable) when the row is at most 64 KiB,
// or a line of the row's raw length (line_too_large) when it is over, since raw size is checked first. v0.5 lists
// rows whose seq can't be read last, in input order; the empty-line stand-ins are found there and relabelled
// invalid_utf8. A row starting with a BOM keeps its text and is rejected by v0.5 as not_json.
// (The browser result also carries view-core's page fields, ordered, meta, prefix and duplicates; relabelling changes
// only rows, so they stay aligned with it.)
export async function verifyBytes(rows, options) {
  const invalid = new Set();
  const lines = rows.map((row, i) => {
    const text = rowText(row);
    if (text !== null) return text;
    if (row.length > MAX_LINE_BYTES) return "x".repeat(row.length);
    invalid.add(i);
    return "";
  });
  const verification = await verifyJsonl(lines, options);
  if (invalid.size === 0) return verification;
  const unreadable = lines.flatMap((line, i) => {
    if (invalid.has(i)) return [i];
    const checked = checkLine(line);
    return !checked.ok && readSeq(checked.value) === null ? [i] : [];
  });
  let next = 0;
  const relabelled = verification.rows.map((row) => {
    if (row.seq !== null) return row;
    const input = unreadable[next++];
    return invalid.has(input) ? { ...row, status: "malformed", reasons: ["invalid_utf8"] } : row;
  });
  if (next !== unreadable.length) throw new Error("internal: unreadable rows didn't line up with v0.5's output");
  return { ...verification, rows: relabelled };
}

// A replay file under the same rule: at most 64 MiB raw, split on LF, each row decoded on its own.
export async function verifyReplayBytes(fileBytes, options) {
  if (!(fileBytes instanceof Uint8Array) || fileBytes.length > MAX_FILE_BYTES) return { ok: false, reason: "file_too_large" };
  return { ok: true, verification: await verifyBytes(splitRows(fileBytes), options) };
}

// Re-runs the full v0.5 verification over every row the client holds. options: { pins, keys, runId? }.
// frozen is true when anything follows the projectable prefix.
export async function verifyRows(state, options = {}) {
  const verification = await verifyBytes(state.rows, { ...options, runId: options.runId ?? state.run_id });
  return { verification, K: verification.prefix_end, frozen: verification.frozen };
}

// Progress (rule 5). Call after verifying each valid page, with the K it gives. Rows from catch-up pages raise the
// high-water mark but never count as growth: the first load of a long log is history, not activity. After
// catch-up, K rising above its highest value is progress.
export function track(state, K, nowMs) {
  if (state.catching_up) return { ...state, high_k: Math.max(state.high_k, K) };
  if (K > state.high_k) return { ...state, high_k: K, last_progress_ms: nowMs };
  return state;
}

// The mode label (rule 5). K is the projectable prefix now, frozen says whether anything follows it, and runStatus
// is the run's status from GET /api/view/runs ("running" or "finished"; anything else counts as running).
// The board is frozen in either of two ways, and both give "STALE · chain broken" at once: K fell below its
// highest value (a late conflict or break at an earlier seq), or a refused row sits after the prefix while K stays
// put. LIVE never shows while the board is frozen.
// A finished run shows "ENDED · run finished" instead of LIVE or STALE, but integrity problems win: a terminal state
// (stream replaced, row too large, paging unsupported) keeps its label, then a frozen board shows chain broken. Only
// a passing failure (transport, paging error) on a finished run stays ENDED, since nothing new is expected.
// For a running run, a failed latest poll shows STALE with its reason, then a frozen board shows chain broken, and
// otherwise v0.5's mode rule decides: LIVE needs a valid cursor page within 5 s and growth after catch-up within 60 s.
export function liveLabel(state, nowMs, K, frozen, runStatus = "running") {
  if (runStatus === "finished") {
    if (state.degraded) return `STALE · ${REASON_TEXT[state.degraded]}`;
    return K < state.high_k || frozen ? "STALE · chain broken" : "ENDED · run finished";
  }
  if (state.failure) return `STALE · ${REASON_TEXT[state.failure]}`;
  if (K < state.high_k) return "STALE · chain broken";
  if (frozen) return "STALE · chain broken";
  return modeLabel("api", state.last_ok_ms, state.last_progress_ms, nowMs);
}
