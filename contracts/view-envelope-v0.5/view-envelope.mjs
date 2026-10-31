// Reference implementation of the SentiLab view envelope (DRAFT v0.5, pocket-forge).
// Plain Node ESM, no dependencies. It imports aneta's canonical() and project() (CONTRACT v0.2)
// instead of copying them, so the hashes and the status here are hers.
import { createHash, sign, verify } from "node:crypto";
import { canonical } from "../contract-0.2/resultcheck.mjs";
import { project } from "../contract-0.2/evidence-projection.mjs";

export const VERSION = "view-envelope/0.5";
const ALG = "ed25519";
const KIB = 1024;
const MAX_LINE_BYTES = 64 * KIB;
const MAX_API_LINES = 256;
const MAX_API_BYTES = 4 * KIB * KIB;
const MAX_FILE_BYTES = 64 * KIB * KIB;
const MAX_CANONICAL_BYTES = 64 * KIB;
const MAX_DEPTH = 8;
const MAX_STRING = 512;
const MAX_ENTRIES = 64;
const POLL_OK_MS = 5_000;
const PROGRESS_MS = 60_000;
const CAPPED_FIELDS = ["geometry", "center_temps", "artifact_hashes"];
const ROLES = new Set(["lab", "core", "acceptance_gate"]);
const BOARD_OUTCOMES = new Set(["accepted", "non_improving_current", "within_margin"]);
const HEX64 = /^[0-9a-f]{64}$/;
const HEX128 = /^[0-9a-f]{128}$/;
// Input-check codes that mean "too big". Every other input-check code means "malformed".
const OVERSIZE = (code) => ["line_too_large", "too_deep", "string_too_long", "too_large"].includes(code) || code.startsWith("too_many_entries:");

// ---- Instrumentation. Every parse, canonical(), envelope hash, signature and verification goes through
// these counters, so a test can prove that rejected input never reaches them. ----
export const counters = { parse: 0, canonical: 0, hash: 0, sign: 0, verify: 0 };
export function resetCounters() {
  for (const key of Object.keys(counters)) counters[key] = 0;
}
const parseLine = (line) => { counters.parse += 1; return JSON.parse(line); };
const canon = (value) => { counters.canonical += 1; return canonical(value); };
const sha256 = (text) => createHash("sha256").update(text, "utf8").digest("hex");
const signHash = (hash, privateKey) => { counters.sign += 1; return sign(null, Buffer.from(hash, "utf8"), privateKey).toString("hex"); };
const verifyHash = (hash, publicKey, value) => { counters.verify += 1; return verify(null, Buffer.from(hash, "utf8"), publicKey, Buffer.from(value, "hex")); };

const isPlainObject = (x) => x !== null && typeof x === "object" && !Array.isArray(x) && [Object.prototype, null].includes(Object.getPrototypeOf(x));

// prev_hash of the first envelope. runId is the run the view requested, never one read from the file.
export function genesis(runId) {
  return sha256(`sentilab-view-genesis:${runId}`);
}

// hash = sha256(canonical(envelope without "sig" and without "hash")), lowercase hex.
// Call it only on input that passed the input checks.
export function hashEnvelope(env) {
  counters.hash += 1;
  const { sig, hash, ...covered } = env;
  return sha256(canon(covered));
}

// key_sha256 is sha256 of the raw 32-byte Ed25519 public key. Node has no raw export, so this
// exports the SPKI DER (a fixed 12-byte header, then the 32 key bytes) and takes the last 32 bytes.
export function rawPublicKey(publicKey) {
  const der = publicKey.export({ type: "spki", format: "der" });
  return der.subarray(der.length - 32);
}
export function keySha256(publicKey) {
  return createHash("sha256").update(rawPublicKey(publicKey)).digest("hex");
}

// sig is Ed25519 over the 64 hex characters of the hash, as UTF-8. sig.value is lowercase hex, 128 characters.
export function signEnvelope(env, privateKey, keyId) {
  const { sig, hash: oldHash, ...rest } = env;
  const hash = hashEnvelope(rest);
  return { ...rest, hash, sig: { key_id: keyId, alg: ALG, value: signHash(hash, privateKey) } };
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
  if (Buffer.byteLength(text, "utf8") > MAX_API_BYTES) return { ok: false, reason: "response_too_large" };
  const lines = splitLines(text);
  if (lines.length > MAX_API_LINES) return { ok: false, reason: "too_many_lines" };
  return { ok: true, lines };
}
export function readReplayFile(text) {
  if (typeof text !== "string") return { ok: false, reason: "not_text" };
  if (Buffer.byteLength(text, "utf8") > MAX_FILE_BYTES) return { ok: false, reason: "file_too_large" };
  return { ok: true, lines: splitLines(text) };
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

// ---- Step 4 (canonical size), measured without calling canonical(): the byte length of canonical(value),
// computed iteratively and stopping once it passes the limit. It equals Buffer.byteLength(canonical(value))
// for anything canonical() can serialize, and also gives the length of the JSON line the core will write. ----
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
        total += Buffer.byteLength(JSON.stringify(key), "utf8") + 1;
        stack.push(item[key]);
      }
    } else if (typeof item === "bigint") total += String(item).length;
    else total += Buffer.byteLength(JSON.stringify(item) ?? "null", "utf8");
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
  if (Buffer.byteLength(line, "utf8") > MAX_LINE_BYTES) return { ...rejection(["line_too_large"]), value: undefined };
  let value;
  try { value = parseLine(line); } catch { return { ...rejection(["not_json"]), value: undefined }; }
  return { ...checkEnvelope(value), value };
}

// ---- The core. ----
// values appear only on node.create of a candidate or measurement, and on verify.add.
const carriesValues = (event) =>
  event.type === "verify.add" || (event.type === "node.create" && ["candidate", "measurement"].includes(event.body?.kind));

// The core's own append rules, checked after the input checks and before hashing.
function appendRule(env) {
  const { event, actor } = env;
  if (Object.hasOwn(env, "values") && !carriesValues(event)) return "values_not_allowed";
  if (!ROLES.has(event.actor_role)) return "bad_actor_role";
  if ((actor.lab === "gate") !== (event.actor_role === "acceptance_gate")) return "gate_role_mismatch";
  if (event.type === "lifecycle.transition" && BOARD_OUTCOMES.has(event.body.to) && event.actor_role !== "acceptance_gate") return "board_outcome_not_gate";
  return null;
}

const refuse = (seq, status, reasons) => {
  throw Object.assign(new Error(`append refused at seq ${seq}: ${status} (${reasons.join(", ")})`), { seq, status, reasons });
};

// The core's writer. entries: [{ event, ts, actor }]; values: { [event_id]: values }; key: { key_id, privateKey }.
// Builds the envelopes in seq order. For each entry, before anything is hashed or signed, it runs the input
// checks on the line it would write (step 1: line size; step 2, parsing, has no counterpart because the core
// holds objects; step 3: structure; step 4: canonical size), then its append rules, then the duplicate and
// conflict policy. A byte-identical retransmission is a no-op. Refusals throw an Error with .status and .reasons.
// appendChecks: false simulates a faulty writer that skips all of this; it is used only for negative vectors.
export function makeChain(run, entries, values, key, { appendChecks = true } = {}) {
  const ordered = [...entries].sort((a, b) => a.event?.seq - b.event?.seq);
  if (!appendChecks) return faultyChain(run, ordered, values, key);
  const envelopes = [];
  const bySeq = new Map();
  const seqOfEventId = new Map();
  let prevHash = genesis(run.run_id);
  let lastSeq = 0;
  for (const { event, ts, actor } of ordered) {
    const seq = event?.seq;
    // The line as it will be written: placeholders of the final length stand in for hash and sig.
    const candidate = { v: VERSION, event, ts, actor, run };
    if (values && event && Object.hasOwn(values, event.event_id)) candidate.values = values[event.event_id];
    Object.assign(candidate, { prev_hash: prevHash, hash: "0".repeat(64), sig: { key_id: key.key_id, alg: ALG, value: "0".repeat(128) } });

    if (jsonSize(candidate, MAX_LINE_BYTES) > MAX_LINE_BYTES) refuse(seq, "oversize", ["line_too_large"]);
    const checked = checkEnvelope(candidate);
    if (!checked.ok) refuse(seq, checked.status, checked.reasons);
    const rule = appendRule(candidate);
    if (rule) refuse(seq, "refused", [rule]);

    const existing = bySeq.get(seq);
    if (existing) {
      // Same seq again: identical content is a retransmission and does nothing; anything else conflicts.
      if (hashEnvelope({ ...candidate, prev_hash: existing.prev_hash }) === existing.hash) continue;
      refuse(seq, "refused", existing.event.event_id === event.event_id ? ["event_id_conflict", "seq_conflict"] : ["seq_conflict"]);
    }
    if (seqOfEventId.has(event.event_id)) refuse(seq, "refused", ["event_id_conflict"]);
    if (seq !== lastSeq + 1) refuse(seq, "refused", ["seq_gap"]);

    // Only now: copy, hash and sign. Copies, so later changes to the inputs can't reach a signed envelope.
    const { hash: placeholderHash, sig: placeholderSig, ...content } = candidate;
    const signed = signEnvelope(structuredClone(content), key.privateKey, key.key_id);
    envelopes.push(signed);
    bySeq.set(seq, signed);
    seqOfEventId.set(event.event_id, seq);
    prevHash = signed.hash;
    lastSeq = seq;
  }
  return envelopes;
}

function faultyChain(run, ordered, values, key) {
  let prevHash = genesis(run.run_id);
  return ordered.map(({ event, ts, actor }) => {
    const env = structuredClone({ v: VERSION, event, ts, actor, run });
    if (values && Object.hasOwn(values, event.event_id)) env.values = structuredClone(values[event.event_id]);
    env.prev_hash = prevHash;
    const signed = signEnvelope(env, key.privateKey, key.key_id);
    prevHash = signed.hash;
    return signed;
  });
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
  return verifyItems(lines.map((line) => checkLine(line)), options);
}

// Steps 3 to 5 for envelopes that are already parsed.
export function verifyChain(envelopes, options) {
  const list = Array.isArray(envelopes) ? envelopes : [];
  return verifyItems(list.map((value) => ({ ...checkEnvelope(value), value })), options);
}

function chainReasons(row, prevSeq, prevHashes, runId, pins, keys) {
  const env = row.env;
  const reasons = [];
  if (env.v !== VERSION) reasons.push("bad_version");
  if (env.run.run_id !== runId) reasons.push("run_mismatch");
  if (env.event.seq !== prevSeq + 1) reasons.push("seq_gap");
  for (const code of ["seq_conflict", "event_id_conflict"]) if (row.conflicts.has(code)) reasons.push(code);
  if (!prevHashes.has(env.prev_hash)) reasons.push("prev_hash_mismatch");
  // Step 5: the hash is recomputed from the content, and the signature is checked against it.
  const actual = hashEnvelope(env);
  if (actual !== env.hash) reasons.push("hash_mismatch");
  const pin = pins.find((p) => p.key_id === env.sig.key_id);
  const key = lookup(keys, env.sig.key_id);
  if (!pin) reasons.push("key_not_pinned");
  else if (!key) reasons.push("key_unavailable");
  else {
    let keyHash = null;
    try { keyHash = key.asymmetricKeyType === "ed25519" ? keySha256(key) : null; } catch { keyHash = null; }
    if (keyHash !== pin.key_sha256) reasons.push("key_hash_mismatch");
    else if (!verifyHash(actual, key, env.sig.value)) reasons.push("bad_sig");
  }
  return reasons;
}

// runId: the run the view requested. pins: [{ key_id, key_sha256 }] from the deployed page.
// keys: Map or object of key_id -> public KeyObject, from anywhere; a key is used only if its hash matches its pin.
function verifyItems(items, { runId, pins = [], keys = {} } = {}) {
  if (typeof runId !== "string") throw new TypeError("verifying needs the run_id the view requested");
  const rows = [];
  const seen = new Set();
  items.forEach((item, index) => {
    if (!item.ok) {
      rows.push({ index, passed: false, seq: readSeq(item.value), event_id: readEventId(item.value), storedHash: readHash(item.value), status: item.status, reasons: item.reasons });
      return;
    }
    const env = item.value;
    // Duplicates: identical canonical bytes, sig and hash included. One copy counts; the others are ignored.
    const bytes = canon(env);
    if (seen.has(bytes)) return;
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
  let prevHashes = new Set([genesis(runId)]);
  for (let i = 0; i < rows.length && rows[i].seq !== null;) {
    let j = i;
    while (j < rows.length && rows[j].seq === rows[i].seq) j += 1;
    const group = rows.slice(i, j);
    for (const row of group) if (row.passed) {
      row.reasons = chainReasons(row, prevSeq, prevHashes, runId, pins, keys);
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

// Feed it every poll. ok: the response passed the transport caps and was read. K: the projectable prefix
// after it. received: how many lines arrived; it is deliberately unused, because arrivals that don't grow
// K (duplicates, unverified envelopes, envelopes after a break) must never refresh LIVE.
export function progressTracker() {
  let highK = 0;
  let lastPollOkMs = null;
  let lastProgressMs = null;
  return {
    poll({ nowMs, ok, K = highK, received = 0 }) {
      if (!ok) return;
      lastPollOkMs = nowMs;
      const grew = K > highK;
      if (grew) {
        highK = K;
        lastProgressMs = nowMs;
      }
    },
    mode: (sourceKind, nowMs) => mode(sourceKind, lastPollOkMs, lastProgressMs, nowMs),
    label: (sourceKind, nowMs) => modeLabel(sourceKind, lastPollOkMs, lastProgressMs, nowMs),
    state: () => ({ K: highK, last_poll_ok_ms: lastPollOkMs, last_progress_ms: lastProgressMs }),
  };
}
