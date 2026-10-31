// Live paging for the SentiLab view (DRAFT v0.6, rule 4): a physical-row cursor bound by a cursor hash.
// Pure: no clock, network, randomness or shared state. Every input is an argument, and states are never mutated.
// Rows are raw bytes (Uint8Array) throughout; text appears only when a row is handed to v0.5 verification.
// The envelope format and every verification rule are v0.5's, imported, not copied.
import { createHash } from "node:crypto";
import { checkLine, verifyJsonl } from "../view-envelope-v0.5/view-envelope.mjs";

export const MAX_LIMIT = 256;
const MAX_PAGE_LINES = 256;
const MAX_PAGE_BYTES = 4 * 1024 * 1024;
const MAX_LINE_BYTES = 64 * 1024;
const MAX_FILE_BYTES = 64 * 1024 * 1024;
const LF = 0x0a;
const LF_BYTES = new Uint8Array([LF]);
const UNSUPPORTED = [400, 404, 501];
const COUNT = /^(0|[1-9][0-9]*)$/;
// The reason a failed poll shows after "STALE · ".
export const REASON_TEXT = { transport: "transport", paging_error: "paging error", stream_replaced: "stream replaced", paging_unsupported: "paging unsupported" };

// SHA-256, lowercase hex, over the raw bytes of each row followed by one LF.
export function cursorHash(rows) {
  const hash = createHash("sha256");
  for (const row of rows) {
    hash.update(row);
    hash.update(LF_BYTES);
  }
  return hash.digest("hex");
}

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
// degraded: "stream_replaced" or "paging_unsupported" once either happens, and it stays until a manual reload.
export function initialState(runId, { limit = MAX_LIMIT } = {}) {
  if (!Number.isSafeInteger(limit) || limit < 1 || limit > MAX_LIMIT) throw new RangeError("limit must be 1 to 256");
  return { run_id: runId, limit, rows: [], cursor: 0, cursor_hash: cursorHash([]), has_more: true, last_ok_ms: null, failure: null, degraded: null };
}

// The next request. cursor_hash is sent with every cursor above 0. There is never a seq parameter.
export function request(state) {
  const req = { cursor: state.cursor, limit: state.limit };
  if (state.cursor > 0) req.cursor_hash = state.cursor_hash;
  return req;
}

// One response to request(state). response: { status, headers, bodyBytes } or null for a failed transport.
// Returns { state, outcome, newRows }. outcome is ok, transport, paging_error, stream_replaced or paging_unsupported.
// A failed poll changes only failure (and degraded): no rows from it are kept, and the cursor never resets.
export function step(state, response, nowMs) {
  if (state.degraded) return { state, outcome: state.degraded, newRows: [] };
  const fail = (reason, extra = {}) => ({ state: { ...state, ...extra, failure: reason }, outcome: reason, newRows: [] });
  const status = response?.status;
  if (status === 409) return fail("stream_replaced", { degraded: "stream_replaced" });
  if (UNSUPPORTED.includes(status)) return fail("paging_unsupported", { degraded: "paging_unsupported" });
  if (status !== 200 || !(response.bodyBytes instanceof Uint8Array)) return fail("transport");
  // The v0.5 response caps, before anything is split or decoded.
  const body = response.bodyBytes;
  if (body.length > MAX_PAGE_BYTES || countLines(body) > MAX_PAGE_LINES) return fail("transport");
  const rows = splitRows(body);
  const nextText = header(response.headers, "x-next-cursor");
  const next = typeof nextText === "string" && COUNT.test(nextText) ? Number(nextText) : NaN;
  if (!Number.isSafeInteger(next)) return fail("paging_error");
  if (next !== state.cursor + rows.length) return fail("paging_error");
  // The client's own hash of every row it would now hold, over raw bytes.
  const combined = [...state.rows, ...rows];
  const ownHash = cursorHash(combined);
  if (header(response.headers, "x-cursor-hash") !== ownHash) return fail("paging_error");
  return {
    state: {
      ...state, rows: combined, cursor: next, cursor_hash: ownHash,
      // An empty page never asks for more, so a bad x-has-more can't make the client spin.
      has_more: header(response.headers, "x-has-more") === "true" && rows.length > 0,
      last_ok_ms: nowMs, failure: null,
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
export function verifyBytes(rows, options) {
  const invalid = new Set();
  const lines = rows.map((row, i) => {
    const text = rowText(row);
    if (text !== null) return text;
    if (row.length > MAX_LINE_BYTES) return "x".repeat(row.length);
    invalid.add(i);
    return "";
  });
  const verification = verifyJsonl(lines, options);
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
export function verifyReplayBytes(fileBytes, options) {
  if (!(fileBytes instanceof Uint8Array) || fileBytes.length > MAX_FILE_BYTES) return { ok: false, reason: "file_too_large" };
  return { ok: true, verification: verifyBytes(splitRows(fileBytes), options) };
}

// Re-runs the full v0.5 verification over every row the client holds. options: { pins, keys, runId? }.
export function verifyRows(state, options = {}) {
  const verification = verifyBytes(state.rows, { ...options, runId: options.runId ?? state.run_id });
  return { verification, K: verification.prefix_end };
}

// The mode label (rule 5). K is the projectable prefix now. A failed latest poll shows STALE with its reason.
// Otherwise, K below the highest value it has reached means a late conflict or break froze the board at an
// earlier seq: "STALE · chain broken", at once. Otherwise the v0.5 progress tracker decides (fed only with valid
// pages, so LIVE needs a valid cursor page within 5 s and growth of K within 60 s).
export function liveLabel(state, tracker, nowMs, K) {
  if (state.failure) return `STALE · ${REASON_TEXT[state.failure]}`;
  if (K < tracker.state().K) return "STALE · chain broken";
  return tracker.label("api", nowMs);
}

// ---- The reference server, for conformance. log: the run's raw rows in append order. ----
export function servePage(log, { cursor, limit, cursor_hash: claimed } = {}) {
  const reply = (status, headers = {}, rows = []) => ({ status, headers, bodyBytes: joinRows(rows) });
  if (!Number.isSafeInteger(cursor) || cursor < 0 || !Number.isSafeInteger(limit) || limit < 1 || limit > MAX_LIMIT) return reply(400);
  if (cursor > log.length) return reply(409);
  if (cursor > 0 && claimed !== cursorHash(log.slice(0, cursor))) return reply(409);
  // Up to `limit` rows within the 4 MiB cap. A row too big for any page is still sent alone.
  const rows = [];
  let size = 0;
  for (let i = cursor; i < Math.min(log.length, cursor + limit); i += 1) {
    if (rows.length > 0 && size + log[i].length + 1 > MAX_PAGE_BYTES) break;
    rows.push(log[i]);
    size += log[i].length + 1;
  }
  const next = cursor + rows.length;
  return reply(200, { "x-next-cursor": String(next), "x-has-more": String(next < log.length), "x-cursor-hash": cursorHash(log.slice(0, next)) }, rows);
}
