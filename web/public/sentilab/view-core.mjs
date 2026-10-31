// Browser port of the SentiLab view-envelope reference (VIEW ENVELOPE v0.5; reference view-envelope.mjs by
// pocket-forge, sha256 54b24823...). The view half follows the reference line for line: the same input checks in
// the same order (raw size, parse, iterative structure, canonical size measured without serializing), and only then
// the duplicate and conflict policy, the hash, chain and signature checks, and the projectable prefix. Rejected input
// never reaches canonical(), a hash or a signature check. The core's writer (makeChain) is not ported: the page never
// signs anything.
// The only changes are the platform calls: WebCrypto replaces node:crypto (so hashing and verify are async), a UTF-8
// byte counter replaces Buffer.byteLength, and keys are raw 32-byte Ed25519 public keys instead of Node KeyObjects.
// web/test/sentilab-parity.test.mjs runs this file and the reference over every v0.5 vector and compares results.
import { canonical } from "./canonical.mjs";
import { project } from "./evidence-projection.mjs";

export const VERSION = "view-envelope/0.5";
export const ALG = "ed25519";
const KIB = 1024;
export const MAX_LINE_BYTES = 64 * KIB;
export const MAX_API_LINES = 256;
export const MAX_API_BYTES = 4 * KIB * KIB;
export const MAX_FILE_BYTES = 64 * KIB * KIB;
const MAX_CANONICAL_BYTES = 64 * KIB;
const MAX_DEPTH = 8;
const MAX_STRING = 512;
const MAX_ENTRIES = 64;
const POLL_OK_MS = 5_000;
const PROGRESS_MS = 60_000;
const CAPPED_FIELDS = ["geometry", "center_temps", "artifact_hashes"];
const HEX64 = /^[0-9a-f]{64}$/;
const HEX128 = /^[0-9a-f]{128}$/;
// Input-check codes that mean "too big". Every other input-check code means "malformed".
const OVERSIZE = (code) => ["line_too_large", "too_deep", "string_too_long", "too_large"].includes(code) || code.startsWith("too_many_entries:");

// ---- Instrumentation, as in the reference. Every parse, canonical(), envelope hash and signature verification goes
// through these counters, so a test can prove that rejected input never reaches them. ----
export const counters = { parse: 0, canonical: 0, hash: 0, verify: 0 };
export function resetCounters() {
  for (const key of Object.keys(counters)) counters[key] = 0;
}
const parseLine = (line) => { counters.parse += 1; return JSON.parse(line); };
const canon = (value) => { counters.canonical += 1; return canonical(value); };

const encoder = new TextEncoder();
const hex = (buf) => Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, "0")).join("");
export const fromHex = (h) => Uint8Array.from(String(h).match(/../g) ?? [], (x) => parseInt(x, 16));
export async function sha256Hex(data) {
  return hex(await crypto.subtle.digest("SHA-256", typeof data === "string" ? encoder.encode(data) : data));
}

// The UTF-8 byte length of a string, as Buffer.byteLength and TextEncoder count it (a lone surrogate becomes U+FFFD,
// 3 bytes). It allocates nothing. With a limit it may stop early: the result is exact up to the limit, and some
// number above the limit once the string is longer.
export function utf8Length(text, limit = Infinity) {
  if (text.length > limit) return text.length;   // every UTF-16 unit is at least one byte
  let bytes = 0;
  for (let i = 0; i < text.length; i += 1) {
    const unit = text.charCodeAt(i);
    if (unit < 0x80) bytes += 1;
    else if (unit < 0x800) bytes += 2;
    else if (unit >= 0xd800 && unit <= 0xdbff && i + 1 < text.length && (text.charCodeAt(i + 1) & 0xfc00) === 0xdc00) { bytes += 4; i += 1; }
    else bytes += 3;
    if (bytes > limit) return bytes;
  }
  return bytes;
}

const isPlainObject = (x) => x !== null && typeof x === "object" && !Array.isArray(x) && [Object.prototype, null].includes(Object.getPrototypeOf(x));

// prev_hash of the first envelope. runId is the run the view requested, never one read from the file.
export function genesis(runId) {
  return sha256Hex(`sentilab-view-genesis:${runId}`);
}

// hash = sha256(canonical(envelope without "sig" and without "hash")), lowercase hex.
// Call it only on input that passed the input checks.
export function hashEnvelope(env) {
  counters.hash += 1;
  const { sig, hash, ...covered } = env;
  return sha256Hex(canon(covered));
}

// key_sha256 is sha256 of the raw 32-byte Ed25519 public key.
export function keySha256(raw) {
  return sha256Hex(raw);
}

// ---- Step 1 (raw size) for transports. Nothing here parses. ----
export function splitLines(text) {
  if (text === "") return [];
  const lines = text.split("\n");
  if (lines.at(-1) === "") lines.pop();
  return lines;
}
// An API response over 256 lines or 4 MiB is a transport error: drop it, keep the prefix, count the poll as failed.
export function parseApiResponse(text) {
  if (typeof text !== "string") return { ok: false, reason: "not_text" };
  if (utf8Length(text, MAX_API_BYTES) > MAX_API_BYTES) return { ok: false, reason: "response_too_large" };
  const lines = splitLines(text);
  if (lines.length > MAX_API_LINES) return { ok: false, reason: "too_many_lines" };
  return { ok: true, lines };
}
export function readReplayFile(text) {
  if (typeof text !== "string") return { ok: false, reason: "not_text" };
  if (utf8Length(text, MAX_FILE_BYTES) > MAX_FILE_BYTES) return { ok: false, reason: "file_too_large" };
  return { ok: true, lines: splitLines(text) };
}

// ---- Raw bytes (page side; provisional until contracts/view-envelope-v0.6/paging.mjs publishes its bytes->rows
// function, which this must then mirror exactly). The page never decodes a whole response or file: the default
// TextDecoder strips a leading BOM, which would make the same row verify differently here and in node. Instead the raw
// bytes are split on LF (0x0A) only, and each row is decoded on its own, strictly, with any BOM kept. A row that isn't
// valid UTF-8 is one malformed row ("invalid_utf8"); a row that starts with a BOM keeps U+FEFF, so it doesn't parse
// ("not_json"). Either way the rest of the page continues. ----
const strictUtf8 = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true });
const asBytes = (data) => (data instanceof Uint8Array ? data : new Uint8Array(data));
// Rows of a raw body: split on 0x0A only; a trailing LF doesn't make a row; a blank row in the middle does.
export function splitRows(data) {
  const bytes = asBytes(data);
  const rows = [];
  let from = 0;
  for (let i = 0; i < bytes.length; i += 1) {
    if (bytes[i] === 0x0a) { rows.push(bytes.subarray(from, i)); from = i + 1; }
  }
  if (from < bytes.length) rows.push(bytes.subarray(from));
  return rows;
}
// Step 1 for raw bodies: an API response over 4 MiB or 256 rows, or a replay file over 64 MiB, is refused unparsed.
export function parseApiBytes(data) {
  const bytes = asBytes(data);
  if (bytes.length > MAX_API_BYTES) return { ok: false, reason: "response_too_large" };
  const rows = splitRows(bytes);
  if (rows.length > MAX_API_LINES) return { ok: false, reason: "too_many_lines" };
  return { ok: true, rows };
}
export function readReplayBytes(data) {
  const bytes = asBytes(data);
  if (bytes.length > MAX_FILE_BYTES) return { ok: false, reason: "file_too_large" };
  return { ok: true, rows: splitRows(bytes) };
}
// Steps 1 to 4 for one raw row: the raw size first (an oversize row is never decoded), then strict decoding, then
// checkLine(). Returns checkLine()'s shape, plus the decoded text (null if the row was never decoded).
export function checkRowBytes(row) {
  if (row.length > MAX_LINE_BYTES) return { ...rejection(["line_too_large"]), value: undefined, text: null };
  let text;
  try { text = strictUtf8.decode(row); } catch { return { ...rejection(["invalid_utf8"]), value: undefined, text: null }; }
  return { ...checkLine(text), text };
}
export function checkRows(rows) {
  return rows.map((row) => checkRowBytes(row));
}

// Browser transport (not in the reference): read a fetch Response body as raw bytes, but stop once it passes maxBytes,
// so an oversize response is never fully read, split or parsed. Returns { ok: true, bytes } or { ok: false, reason }.
export async function readBodyCapped(response, maxBytes, reason) {
  if (!response.body) {
    const bytes = new Uint8Array(await response.arrayBuffer());
    return bytes.length > maxBytes ? { ok: false, reason } : { ok: true, bytes };
  }
  const reader = response.body.getReader();
  const chunks = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > maxBytes) {
      reader.cancel().catch(() => {});
      return { ok: false, reason };
    }
    chunks.push(value);
  }
  const all = new Uint8Array(size);
  let at = 0;
  for (const chunk of chunks) { all.set(chunk, at); at += chunk.byteLength; }
  return { ok: true, bytes: all };
}

// ---- Step 3 (structure). Iterative, with an explicit stack; never recursive, never canonical(). ----
function scanString(s, reasons) {
  let points = 0;
  let lone = false;
  for (let i = 0; i < s.length; i += 1) {
    const unit = s.charCodeAt(i);
    if (unit >= 0xd800 && unit <= 0xdbff && i + 1 < s.length && s.charCodeAt(i + 1) >= 0xdc00 && s.charCodeAt(i + 1) <= 0xdfff) i += 1;
    else if (unit >= 0xd800 && unit <= 0xdfff) lone = true;
    points += 1;
  }
  if (lone) reasons.add("lone_surrogate");
  if (points > MAX_STRING) reasons.add("string_too_long");
}

function schemaReasons(env, reasons) {
  if (!isPlainObject(env)) { reasons.add("schema:envelope"); return; }
  const isString = (x) => typeof x === "string";
  if (!isString(env.v)) reasons.add("schema:v");
  const event = env.event;
  if (!isPlainObject(event)) reasons.add("schema:event");
  else {
    if (!isString(event.event_id)) reasons.add("schema:event.event_id");
    if (!Number.isSafeInteger(event.seq) || event.seq < 1) reasons.add("schema:event.seq");
    if (!isString(event.type)) reasons.add("schema:event.type");
    if (!isString(event.actor_role)) reasons.add("schema:event.actor_role");
    if (!isPlainObject(event.body)) reasons.add("schema:event.body");
  }
  if (!isString(env.ts)) reasons.add("schema:ts");
  if (!isPlainObject(env.actor)) reasons.add("schema:actor");
  if (!isPlainObject(env.run) || !isString(env.run.run_id)) reasons.add("schema:run");
  if (!isString(env.prev_hash) || !HEX64.test(env.prev_hash)) reasons.add("schema:prev_hash");
  if (!isString(env.hash) || !HEX64.test(env.hash)) reasons.add("schema:hash");
  const sig = env.sig;
  if (!isPlainObject(sig)) reasons.add("schema:sig");
  else {
    if (!isString(sig.key_id)) reasons.add("schema:sig.key_id");
    if (sig.alg !== ALG) reasons.add("schema:sig.alg");
    if (!isString(sig.value) || !HEX128.test(sig.value)) reasons.add("schema:sig.value");
  }
  if (Object.hasOwn(env, "values") && !isPlainObject(env.values)) reasons.add("schema:values");
}

function structureReasons(env) {
  const reasons = new Set();
  // The envelope is level 1; only objects and arrays count as levels.
  const stack = [[env, 1]];
  while (stack.length > 0) {
    const [item, depth] = stack.pop();
    if (typeof item === "string") scanString(item, reasons);
    else if (typeof item === "number") { if (!Number.isFinite(item)) reasons.add("non_finite_number"); }
    else if (item === null || typeof item === "boolean") continue;
    else if (Array.isArray(item) || isPlainObject(item)) {
      if (depth > MAX_DEPTH) reasons.add("too_deep");
      else if (Array.isArray(item)) for (const child of item) stack.push([child, depth + 1]);
      else for (const key of Object.keys(item)) { scanString(key, reasons); stack.push([item[key], depth + 1]); }
    } else reasons.add("invalid_value"); // undefined, functions, BigInt, symbols, class instances
  }
  const values = isPlainObject(env) && isPlainObject(env.values) ? env.values : {};
  for (const field of CAPPED_FIELDS) {
    const value = values[field];
    const entries = Array.isArray(value) ? value.length : isPlainObject(value) ? Object.keys(value).length : 0;
    if (entries > MAX_ENTRIES) reasons.add(`too_many_entries:${field}`);
  }
  schemaReasons(env, reasons);
  return reasons;
}

// ---- Step 4 (canonical size), measured without calling canonical(): the byte length of canonical(value), computed
// iteratively and stopping once it passes the limit. ----
function jsonSize(root, limit) {
  let total = 0;
  const stack = [root];
  while (stack.length > 0) {
    const item = stack.pop();
    if (Array.isArray(item)) {
      total += 2 + Math.max(0, item.length - 1);
      if (total > limit) return total;
      for (const child of item) stack.push(child);
    } else if (item !== null && typeof item === "object") {
      const keys = Object.keys(item);
      total += 2 + Math.max(0, keys.length - 1);
      for (const key of keys) {
        total += utf8Length(JSON.stringify(key)) + 1;
        stack.push(item[key]);
      }
    } else if (typeof item === "bigint") total += String(item).length;
    else total += utf8Length(JSON.stringify(item) ?? "null");
    if (total > limit) return total;
  }
  return total;
}

// The byte length of canonical(value), without calling canonical().
export function canonicalSize(value) {
  return jsonSize(value, Infinity);
}

const rejection = (reasons) => {
  const list = [...reasons].sort();
  return { ok: false, status: list.some((code) => !OVERSIZE(code)) ? "malformed" : "oversize", reasons: list };
};

// Steps 3 and 4 for an already-parsed envelope. Nothing here parses, calls canonical() or hashes.
export function checkEnvelope(env) {
  const reasons = structureReasons(env);
  if (reasons.size === 0 && jsonSize(env, MAX_CANONICAL_BYTES) > MAX_CANONICAL_BYTES) reasons.add("too_large");
  return reasons.size === 0 ? { ok: true, status: null, reasons: [] } : rejection(reasons);
}

// Steps 1 to 4 for one JSONL line, in order. A line that fails step 1 is never parsed.
export function checkLine(line) {
  if (typeof line !== "string") return { ...rejection(["not_json"]), value: undefined };
  if (utf8Length(line, MAX_LINE_BYTES) > MAX_LINE_BYTES) return { ...rejection(["line_too_large"]), value: undefined };
  let value;
  try { value = parseLine(line); } catch { return { ...rejection(["not_json"]), value: undefined }; }
  return { ...checkEnvelope(value), value };
}

// Steps 1 to 4 for every line. The page keeps these results, so a live feed parses each new line once.
export function checkLines(lines) {
  return (Array.isArray(lines) ? lines : []).map((line) => checkLine(line));
}

// The live view's accumulator (page side, not in the reference): every raw row received, in stream order, with its
// input-check result. Cursor paging fetches each physical row of the run's stream exactly once, so every row is kept:
// a repeated row is a real row of the stream (the verifier treats an identical envelope as a duplicate and keeps a
// repeated rejected row as its own row, as the reference does). Each distinct decodable row is checked once.
// Past maxRows it stops accepting and says so.
export function liveFeed(maxRows = Infinity) {
  const checked = new Map();
  const items = [];
  let truncated = false;
  let repeats = 0;
  return {
    items,
    add(rows) {
      let added = 0;
      for (const row of rows) {
        if (items.length >= maxRows) { truncated = true; break; }
        let item = null;
        if (row.length <= MAX_LINE_BYTES) {
          let text = null;
          try { text = strictUtf8.decode(row); } catch { text = null; }
          if (text !== null && checked.has(text)) { item = checked.get(text); repeats += 1; }
        }
        if (item === null) {
          item = checkRowBytes(row);
          if (item.text !== null) checked.set(item.text, item);
        }
        items.push(item);
        added += 1;
      }
      return added;
    },
    get truncated() { return truncated; },
    get repeats() { return repeats; },   // byte-identical rows seen again
  };
}

// ---- Live paging (rule 4 as the producer serves it; PROVISIONAL until contracts/view-envelope-v0.6 publishes its
// reference reducer, which this must then be replaced by). GET /api/view/events?run_id=<id>&cursor=<n>&limit=256.
// The cursor counts the physical JSONL rows already consumed, malformed rows and duplicates included; the response
// headers x-next-cursor and x-has-more carry the paging state. Paging by seq is never used: it can't deliver a late
// envelope at a seq the view already has.
// pagingStart() is the state at cursor 0. applyPage(state, response) is pure: response is { status, bytes,
// nextCursor, hasMore } (bytes: the raw body, or null when it passed the 4 MiB cap while being read and was not read
// further). It returns { state, rows, more, failure }: rows are the raw rows to keep (empty unless the page is
// accepted), and failure is null or one of:
//   "paging_unsupported"  400, 404 or 501 to the cursor request. Terminal: the view is never LIVE in this state.
//   "stream_replaced"     409 or 416, or 0 rows with x-next-cursor below the cursor asked for (the log was truncated
//                         or replaced). Terminal: never reset automatically; only a reload starts again from 0.
//   "paging_error"        x-next-cursor missing, not an integer, backwards, or not the cursor plus the rows sent.
//   "over_cap"            over 256 lines or 4 MiB; dropped before parsing.
//   "http_error"          any other status that isn't 200.
// A failed page keeps nothing and leaves the cursor where it was, so the verified prefix is unchanged. ----
export const TERMINAL_PAGING = Object.freeze(["paging_unsupported", "stream_replaced"]);
export function pagingStart() {
  return { cursor: 0, terminal: null };
}
export function applyPage(state, response) {
  const fail = (failure, terminal = false) => ({ state: terminal ? { ...state, terminal: failure } : state, rows: [], more: false, failure });
  if (state.terminal) return fail(state.terminal, true);
  const { status, bytes, nextCursor, hasMore } = response;
  if (status === 400 || status === 404 || status === 501) return fail("paging_unsupported", true);
  if (status === 409 || status === 416) return fail("stream_replaced", true);
  if (status !== 200) return fail("http_error");
  if (bytes === null) return fail("over_cap");
  const caps = parseApiBytes(bytes);
  if (!caps.ok) return fail("over_cap");
  if (typeof nextCursor !== "string" || !/^[0-9]{1,15}$/.test(nextCursor)) return fail("paging_error");
  const next = Number(nextCursor);
  if (caps.rows.length === 0 && next < state.cursor) return fail("stream_replaced", true);
  if (next !== state.cursor + caps.rows.length) return fail("paging_error");
  return { state: { ...state, cursor: next }, rows: caps.rows, more: hasMore === "true" && caps.rows.length > 0, failure: null };
}

// ---- The view. ----
const lookup = (keys, keyId) => {
  if (keys instanceof Map) return keys.get(keyId);
  return isPlainObject(keys) && Object.hasOwn(keys, keyId) ? keys[keyId] : undefined;
};
// Fields read from rejected input, for display and ordering only. Reading a field is not hashing.
const readSeq = (value) => (isPlainObject(value) && isPlainObject(value.event) && Number.isSafeInteger(value.event.seq) && value.event.seq >= 1 ? value.event.seq : null);
const readEventId = (value) => {
  const id = isPlainObject(value) && isPlainObject(value.event) ? value.event.event_id : undefined;
  if (typeof id !== "string") return null;
  const reasons = new Set();
  scanString(id, reasons);
  return reasons.size === 0 ? id : null;
};
const readHash = (value) => (isPlainObject(value) && typeof value.hash === "string" && HEX64.test(value.hash) ? value.hash : null);

// Steps 1 to 5 for JSONL: a string (split into lines) or an array of lines. Transport caps are checked first,
// by parseApiResponse() or readReplayFile().
export function verifyJsonl(input, options) {
  const lines = typeof input === "string" ? splitLines(input) : Array.isArray(input) ? input : [];
  return verifyChecked(checkLines(lines), options);
}

// Steps 3 to 5 for envelopes that are already parsed.
export function verifyChain(envelopes, options) {
  const list = Array.isArray(envelopes) ? envelopes : [];
  return verifyChecked(list.map((value) => ({ ...checkEnvelope(value), value })), options);
}

// Imported keys are cached per raw key, so a long feed imports each key once.
const imported = new Map();
function importKey(raw) {
  const id = hex(raw);
  if (!imported.has(id)) {
    imported.set(id, crypto.subtle.importKey("raw", raw, { name: "Ed25519" }, false, ["verify"]).catch(() => null));
  }
  return imported.get(id);
}

async function chainReasons(row, prevSeq, prevHashes, runId, pins, keys) {
  const env = row.env;
  const reasons = [];
  if (env.v !== VERSION) reasons.push("bad_version");
  if (env.run.run_id !== runId) reasons.push("run_mismatch");
  if (env.event.seq !== prevSeq + 1) reasons.push("seq_gap");
  for (const code of ["seq_conflict", "event_id_conflict"]) if (row.conflicts.has(code)) reasons.push(code);
  if (!prevHashes.has(env.prev_hash)) reasons.push("prev_hash_mismatch");
  // Step 5: the hash is recomputed from the content, and the signature is checked against it.
  const actual = await hashEnvelope(env);
  if (actual !== env.hash) reasons.push("hash_mismatch");
  const pin = pins.find((p) => p.key_id === env.sig.key_id);
  const key = lookup(keys, env.sig.key_id);
  if (!pin) reasons.push("key_not_pinned");
  else if (!key) reasons.push("key_unavailable");
  else {
    let keyHash = null;
    try { keyHash = key instanceof Uint8Array && key.length === 32 ? await keySha256(key) : null; } catch { keyHash = null; }
    if (keyHash !== pin.key_sha256) reasons.push("key_hash_mismatch");
    else {
      const cryptoKey = await importKey(key);
      if (cryptoKey === null) reasons.push("ed25519_unsupported");   // browser only: this browser has no WebCrypto Ed25519
      else {
        counters.verify += 1;
        if (!(await crypto.subtle.verify({ name: "Ed25519" }, cryptoKey, fromHex(env.sig.value), encoder.encode(actual)))) reasons.push("bad_sig");
      }
    }
  }
  return reasons;
}

// items: checkLine()/checkEnvelope() results, each { ok, status, reasons, value }.
// runId: the run the view requested. pins: [{ key_id, key_sha256 }], from the deployed page only.
// keys: Map or object of key_id -> raw public key (Uint8Array), from anywhere (GET /api/view/key, a manifest);
// a key is used only if its hash matches the pin for that key_id.
// Beyond the reference's result, this returns for the page: `ordered` (per row, the envelope for a row that passed
// the input checks, null for a rejected row), `meta` (per row, its position in the input and its readable stored
// hash), `prefix` (the prefix's length in rows) and `duplicates` (copies ignored). None of them changes a verdict.
export async function verifyChecked(items, { runId, pins = [], keys = {} } = {}) {
  if (typeof runId !== "string") throw new TypeError("verifying needs the run_id the view requested");
  const rows = [];
  const seen = new Set();
  let duplicates = 0;
  items.forEach((item, index) => {
    if (!item.ok) {
      rows.push({ index, passed: false, value: null, seq: readSeq(item.value), event_id: readEventId(item.value), storedHash: readHash(item.value), status: item.status, reasons: item.reasons });
      return;
    }
    const env = item.value;
    // Duplicates: identical canonical bytes, sig and hash included. One copy counts; the others are ignored.
    const bytes = canon(env);
    if (seen.has(bytes)) { duplicates += 1; return; }
    seen.add(bytes);
    rows.push({ index, passed: true, env, seq: env.event.seq, event_id: env.event.event_id, storedHash: env.hash, conflicts: new Set() });
  });

  // Conflicts: different envelopes in the same run sharing a seq or an event_id. Every one involved is flagged.
  const flag = (keyOf, code) => {
    const groups = new Map();
    for (const row of rows) if (row.passed) {
      const groupKey = keyOf(row);
      if (!groups.has(groupKey)) groups.set(groupKey, []);
      groups.get(groupKey).push(row);
    }
    for (const group of groups.values()) if (group.length > 1) for (const row of group) row.conflicts.add(code);
  };
  flag((row) => JSON.stringify([row.env.run.run_id, row.seq]), "seq_conflict");
  flag((row) => JSON.stringify([row.env.run.run_id, row.event_id]), "event_id_conflict");

  // Order by seq. At one seq, rejected rows come first, then envelopes by stored hash, so delivery order
  // never matters. Rows whose seq can't be read come last.
  const compare = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
  rows.sort((a, b) => (a.seq ?? Infinity) - (b.seq ?? Infinity) || Number(a.passed) - Number(b.passed) ||
    (a.passed ? compare(a.storedHash, b.storedHash) : 0) || a.index - b.index);

  // Chain checks, one seq at a time. prev_hash must be the stored hash of an envelope at the previous seq.
  let prevSeq = 0;
  let prevHashes = new Set([await genesis(runId)]);
  for (let i = 0; i < rows.length && rows[i].seq !== null;) {
    let j = i;
    while (j < rows.length && rows[j].seq === rows[i].seq) j += 1;
    const group = rows.slice(i, j);
    for (const row of group) if (row.passed) {
      row.reasons = await chainReasons(row, prevSeq, prevHashes, runId, pins, keys);
      row.status = row.reasons.length === 0 ? "verified" : "unverified";
    }
    prevSeq = rows[i].seq;
    prevHashes = new Set(group.map((row) => row.storedHash).filter(Boolean));
    i = j;
  }

  // Rule 1: the projectable prefix is the leading run of verified rows. It stops at the first rejected,
  // unverified or conflicting row, so it ends before the earliest conflict. K is its last seq, 0 if none.
  const prefixRows = [];
  for (const row of rows) {
    if (row.status !== "verified") break;
    prefixRows.push(row);
  }
  const inPrefix = new Set(prefixRows);
  const prefixEnd = prefixRows.length === 0 ? 0 : prefixRows.at(-1).seq;
  const frozen = prefixRows.length < rows.length;
  // If project() throws, the result is an error state, not a throw.
  let projection = null;
  let projectionError = null;
  try {
    projection = project(prefixRows.map((row) => row.env.event));
  } catch {
    projectionError = "project_threw";
  }
  return {
    rows: rows.map((row) => ({ seq: row.seq, event_id: row.event_id, status: row.status, reasons: row.reasons, projected: inPrefix.has(row) })),
    chain_ok: rows.every((row) => row.status === "verified"),
    prefix_end: prefixEnd,
    frozen,
    label: frozen ? `chain broken after seq ${prefixEnd}; board frozen at seq ${prefixEnd}` : null,
    projection,
    projection_error: projectionError,
    ordered: rows.map((row) => (row.passed ? row.env : null)),
    meta: rows.map((row) => ({ index: row.index, hash: row.storedHash })),
    prefix: prefixRows.length,
    duplicates,
  };
}

// ---- Rule 5. Client-clock times only, never ts. ----
// LIVE: the source is the API, a poll succeeded within 5 s, and the projectable prefix K grew within 60 s.
// "Within" is inclusive, and a time later than nowMs never counts.
export function mode(sourceKind, lastPollOkMs, lastProgressMs, nowMs) {
  if (sourceKind === "file") return "REPLAY";
  if (sourceKind !== "api") throw new TypeError(`unknown source kind: ${sourceKind}`);
  const within = (t, limit) => Number.isFinite(t) && Number.isFinite(nowMs) && t <= nowMs && nowMs - t <= limit;
  return within(lastPollOkMs, POLL_OK_MS) && within(lastProgressMs, PROGRESS_MS) ? "LIVE" : "STALE";
}
// The label shows how long ago K last grew, in whole seconds, and never claims completeness.
export function modeLabel(sourceKind, lastPollOkMs, lastProgressMs, nowMs) {
  const current = mode(sourceKind, lastPollOkMs, lastProgressMs, nowMs);
  return current === "LIVE" ? `LIVE · progress ${Math.floor((nowMs - lastProgressMs) / 1000)} s ago` : current;
}

// Feed it every poll. ok: the response passed the transport caps and was read. K: the projectable prefix after it.
// received: how many lines arrived; it is deliberately unused, because arrivals that don't grow K (duplicates,
// unverified envelopes, envelopes after a break) must never refresh LIVE.
// Rule 5 as v0.6 words it (stricter than the v0.5 reference tracker, which only looks at growth): LIVE also needs K
// not below the highest value it has reached. When K falls, because a late conflict or break cut the prefix, LIVE ends
// at once and the label is "STALE · chain broken"; it stays so until K is back at its highest value.
export const CHAIN_BROKEN_LABEL = "STALE · chain broken";
export function progressTracker() {
  let highK = 0;
  let currentK = 0;
  let lastPollOkMs = null;
  let lastProgressMs = null;
  const fell = () => currentK < highK;
  return {
    poll({ nowMs, ok, K = currentK, received = 0 }) {
      if (!ok) return;
      lastPollOkMs = nowMs;
      currentK = K;
      const grew = K > highK;
      if (grew) {
        highK = K;
        lastProgressMs = nowMs;
      }
    },
    mode: (sourceKind, nowMs) => (sourceKind === "api" && fell() ? "STALE" : mode(sourceKind, lastPollOkMs, lastProgressMs, nowMs)),
    label: (sourceKind, nowMs) => (sourceKind === "api" && fell() ? CHAIN_BROKEN_LABEL : modeLabel(sourceKind, lastPollOkMs, lastProgressMs, nowMs)),
    state: () => ({ K: highK, current_K: currentK, last_poll_ok_ms: lastPollOkMs, last_progress_ms: lastProgressMs }),
  };
}

// ── Keys (view side) ──────────────────────────────────────────────────────────────────────────────────────────
// GET /api/view/key is not specified beyond "may serve the key". Accepted shapes: { key_id, public_key } or
// { keys: [...] } or an array of those, where public_key is the raw 32-byte Ed25519 key as 64 hex characters.
// The result only offers keys; verifying uses one only if its sha256 matches the page's pin.
export function parseKeyResponse(doc) {
  const items = Array.isArray(doc) ? doc : isPlainObject(doc) && Array.isArray(doc.keys) ? doc.keys : isPlainObject(doc) ? [doc] : [];
  const keys = {};
  for (const item of items) {
    if (!isPlainObject(item) || typeof item.key_id !== "string" || typeof item.public_key !== "string") continue;
    if (!HEX64.test(item.public_key)) continue;
    keys[item.key_id] = fromHex(item.public_key);
  }
  return keys;
}

// Test key derivation for the ?pins=test mode, by the vectors' rule: the Ed25519 key whose 32-byte seed is
// sha256(seedText). WebCrypto has no raw private import, so the seed goes in the fixed PKCS#8 wrapper and the
// public half is read back from the JWK export. Anyone can derive this key; it is never a production pin.
const PKCS8_ED25519_PREFIX = Uint8Array.from([0x30, 0x2e, 0x02, 0x01, 0x00, 0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x70, 0x04, 0x22, 0x04, 0x20]);
export async function publicKeyFromSeedText(seedText) {
  const seed = new Uint8Array(await crypto.subtle.digest("SHA-256", encoder.encode(seedText)));
  const pkcs8 = new Uint8Array(PKCS8_ED25519_PREFIX.length + 32);
  pkcs8.set(PKCS8_ED25519_PREFIX);
  pkcs8.set(seed, PKCS8_ED25519_PREFIX.length);
  const key = await crypto.subtle.importKey("pkcs8", pkcs8, { name: "Ed25519" }, true, ["sign"]);
  const jwk = await crypto.subtle.exportKey("jwk", key);
  const b64 = jwk.x.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (jwk.x.length % 4)) % 4);
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
}
