// Browser port of the SentiLab view-envelope reference (VIEW ENVELOPE v0.4; reference view-envelope.mjs by
// pocket-forge, sha256 ee37a2f4...). The logic follows the reference line for line. The only changes are the
// platform calls: WebCrypto replaces node:crypto (so hashing and verify are async), TextEncoder replaces
// Buffer.byteLength, and keys are raw 32-byte Ed25519 public keys instead of Node KeyObjects.
// web/test/sentilab-parity.test.mjs runs this file and the reference over the same vectors and compares results.
import { canonical } from "./canonical.mjs";
import { project } from "./evidence-projection.mjs";

export const VERSION = "view-envelope/0.4";
export const ALG = "ed25519";
const MAX_BYTES = 64 * 1024;
const MAX_ENTRIES = 64;
const MAX_STRING = 512;
const MAX_DEPTH = 8;
const POLL_OK_MS = 5_000;
const ARRIVAL_MS = 60_000;
const CAPPED_FIELDS = ["geometry", "center_temps", "artifact_hashes"];
const SIG_HEX = /^[0-9a-f]{128}$/;

const utf8 = (text) => new TextEncoder().encode(text);
const hex = (buf) => Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, "0")).join("");
export const fromHex = (h) => Uint8Array.from(String(h).match(/../g) ?? [], (x) => parseInt(x, 16));
export async function sha256Hex(data) {
  return hex(await crypto.subtle.digest("SHA-256", typeof data === "string" ? utf8(data) : data));
}
const isObject = (x) => x !== null && typeof x === "object" && !Array.isArray(x);
// Characters are Unicode code points, so an astral character counts once.
const charCount = (s) => (s.length <= MAX_STRING ? s.length : [...s].length);

// prev_hash of the first envelope. runId is the run the view requested, never one read from the file.
export function genesis(runId) {
  return sha256Hex(`sentilab-view-genesis:${runId}`);
}

// hash = sha256(canonical(envelope without "sig" and without "hash")), lowercase hex.
export function hashEnvelope(env) {
  const { sig, hash, ...covered } = env;
  return sha256Hex(canonical(covered));
}

// key_sha256 is sha256 of the raw 32-byte Ed25519 public key.
export function keySha256(raw) {
  return sha256Hex(raw);
}

// Size caps. Returns { ok, reasons } where reasons are cap codes, sorted.
export function checkCaps(env) {
  const reasons = new Set();
  // Iterative walk first, so a deep envelope can't overflow the stack. The envelope is level 1 and,
  // as in ResultCheck's depth limit, an object or array below level 8 is too deep.
  // Every string (object keys included) and every number is checked.
  const stack = [[env, 1]];
  while (stack.length > 0) {
    const [item, depth] = stack.pop();
    if (typeof item === "string") {
      if (charCount(item) > MAX_STRING) reasons.add("string_too_long");
    } else if (typeof item === "number") {
      if (!Number.isFinite(item)) reasons.add("non_finite_number");
    } else if (item !== null && typeof item === "object") {
      if (depth > MAX_DEPTH) reasons.add("too_deep");
      else if (Array.isArray(item)) for (const child of item) stack.push([child, depth + 1]);
      else for (const key of Object.keys(item)) stack.push([key, depth + 1], [item[key], depth + 1]);
    }
  }
  const values = isObject(env) && isObject(env.values) ? env.values : {};
  for (const field of CAPPED_FIELDS) {
    const value = values[field];
    const entries = Array.isArray(value) ? value.length : isObject(value) ? Object.keys(value).length : 0;
    if (entries > MAX_ENTRIES) reasons.add(`too_many_entries:${field}`);
  }
  // The 64 KiB covers the whole envelope, sig and hash included. canonical() is recursive, so it runs
  // only on an envelope that passed the depth cap.
  if (!reasons.has("too_deep")) {
    try {
      if (utf8(canonical(env)).length > MAX_BYTES) reasons.add("too_large");
    } catch {
      reasons.add("malformed");
    }
  }
  return { ok: reasons.size === 0, reasons: [...reasons].sort() };
}

const wellFormed = (env) =>
  isObject(env) && isObject(env.event) && Number.isSafeInteger(env.event.seq) && env.event.seq >= 1 &&
  isObject(env.run) && typeof env.run.run_id === "string" &&
  typeof env.prev_hash === "string" && typeof env.hash === "string" &&
  isObject(env.sig) && typeof env.sig.key_id === "string" && typeof env.sig.value === "string";

const lookup = (keys, keyId) => {
  if (keys instanceof Map) return keys.get(keyId);
  return isObject(keys) && Object.hasOwn(keys, keyId) ? keys[keyId] : undefined;
};

// Imported keys are cached per raw key, so a long feed imports each key once.
const imported = new Map();
function importKey(raw) {
  const id = hex(raw);
  if (!imported.has(id)) {
    imported.set(id, crypto.subtle.importKey("raw", raw, { name: "Ed25519" }, false, ["verify"]).catch(() => null));
  }
  return imported.get(id);
}

// runId: the run the view requested. pins: [{ key_id, key_sha256 }], from the deployed page only.
// keys: Map or object of key_id -> raw public key (Uint8Array), from anywhere (GET /api/view/key, a manifest);
// a key is used only if its hash matches the pin for that key_id.
// Every envelope gets a row, in seq order (stable for equal seq). Only the projectable prefix reaches
// project(); every row after it is shown but never projected, even if it verifies on its own.
// Beyond the reference's result, this also returns `ordered` (the envelopes in row order) and `prefix` (the
// prefix's length in rows) for the page; neither changes any verdict.
export async function verifyChain(envelopes, { runId, pins = [], keys = {} } = {}) {
  if (typeof runId !== "string") throw new TypeError("verifyChain needs the run_id the view requested");
  const list = Array.isArray(envelopes) ? envelopes : [];
  const seqOf = (env) => (wellFormed(env) ? env.event.seq : Infinity);
  const ordered = list.map((env, index) => ({ env, index }))
    .sort((a, b) => seqOf(a.env) - seqOf(b.env) || a.index - b.index)
    .map(({ env }) => env);

  const genesisHash = await genesis(runId);
  const rows = [];
  let prev = null;
  for (const env of ordered) {
    const oversize = checkCaps(env).reasons;
    if (!wellFormed(env)) {
      rows.push({ seq: isObject(env?.event) ? env.event.seq ?? null : null, event_id: isObject(env?.event) ? env.event.event_id ?? null : null, status: "unverified", reasons: ["malformed"], oversize });
      prev = env;
      continue;
    }
    const reasons = [];
    const { seq } = env.event;
    if (env.v !== VERSION) reasons.push("bad_version");
    if (env.run.run_id !== runId) reasons.push("run_mismatch");
    if (prev === null ? seq !== 1 : wellFormed(prev) && seq !== prev.event.seq + 1) {
      reasons.push(prev !== null && seq === prev.event.seq ? "seq_repeat" : "seq_gap");
    }
    if (env.prev_hash !== (prev === null ? genesisHash : prev.hash)) reasons.push("prev_hash_mismatch");
    let actual = null;
    try { actual = await hashEnvelope(env); } catch { reasons.push("malformed"); }
    if (actual !== null && actual !== env.hash) reasons.push("hash_mismatch");

    const pin = pins.find((p) => p.key_id === env.sig.key_id);
    const key = lookup(keys, env.sig.key_id);
    let keyOk = false;
    if (!pin) reasons.push("key_not_pinned");
    else if (!key) reasons.push("key_unavailable");
    else {
      let keyHash = null;
      try { keyHash = key instanceof Uint8Array && key.length === 32 ? await keySha256(key) : null; } catch { keyHash = null; }
      if (keyHash !== pin.key_sha256) reasons.push("key_hash_mismatch");
      else keyOk = true;
    }
    if (env.sig.alg !== ALG) reasons.push("bad_alg");
    else if (keyOk && actual !== null) {
      // The signature is checked over the hash recomputed from the content.
      const cryptoKey = await importKey(key);
      if (cryptoKey === null) reasons.push("ed25519_unsupported");   // browser-only: no WebCrypto Ed25519
      else {
        const sigOk = SIG_HEX.test(env.sig.value) &&
          (await crypto.subtle.verify({ name: "Ed25519" }, cryptoKey, fromHex(env.sig.value), utf8(actual)));
        if (!sigOk) reasons.push("bad_sig");
      }
    }
    rows.push({ seq, event_id: env.event.event_id ?? null, status: reasons.length === 0 ? "verified" : "unverified", reasons, oversize });
    prev = env;
  }

  // Rule 1: the projectable prefix is the leading run of rows that are verified and not oversize. A verified
  // row is already in the requested run, with seq one more than the row before it (1 first) and prev_hash
  // exact (genesis first). K is the prefix's last seq, 0 if none, and the board is project() over it.
  let prefixLength = 0;
  while (prefixLength < rows.length && rows[prefixLength].status === "verified" && rows[prefixLength].oversize.length === 0) prefixLength += 1;
  rows.forEach((row, i) => { row.projected = i < prefixLength; });
  const prefixEnd = prefixLength === 0 ? 0 : rows[prefixLength - 1].seq;
  const frozen = prefixLength < rows.length;
  // If project() throws, the result is an error state, not a throw.
  let projection = null;
  let projectionError = null;
  try {
    projection = project(ordered.slice(0, prefixLength).map((env) => env.event));
  } catch {
    projectionError = "project_threw";
  }
  return {
    rows,
    chain_ok: rows.every((row) => row.status === "verified"),
    prefix_end: prefixEnd,
    frozen,
    label: frozen ? `chain broken after seq ${prefixEnd}; board frozen at seq ${prefixEnd}` : null,
    projection,
    projection_error: projectionError,
    ordered,
    prefix: prefixLength,
  };
}

// Rule 5. Client-clock times only, never ts. sourceKind is "api" or "file". lastPollOkMs is when the last
// poll succeeded; lastVerifiedArrivalMs is when the last verified envelope arrived; either may be null.
// "Within" is inclusive. A time later than nowMs isn't a past poll or arrival, so it never counts.
export function mode(sourceKind, lastPollOkMs, lastVerifiedArrivalMs, nowMs) {
  if (sourceKind === "file") return "REPLAY";
  if (sourceKind !== "api") throw new TypeError(`unknown source kind: ${sourceKind}`);
  const within = (t, limit) => Number.isFinite(t) && Number.isFinite(nowMs) && t <= nowMs && nowMs - t <= limit;
  return within(lastPollOkMs, POLL_OK_MS) && within(lastVerifiedArrivalMs, ARRIVAL_MS) ? "LIVE" : "STALE";
}

// ── Parsing (view side; not in the reference) ─────────────────────────────────────────────────────────────────
// A JSONL line longer than this is not parsed at all: it is far over the 64 KiB cap, and parsing it would cost
// the page. It becomes one placeholder.
export const MAX_LINE_CHARS = 1024 * 1024;

// JSONL text -> array of envelopes. A line that doesn't parse, or is far too large, becomes an object that is
// not a well-formed envelope, so verifyChain shows it as one malformed, unverified row (never dropped).
export function parseJsonl(text) {
  const out = [];
  String(text).split(/\r?\n/).forEach((line, index) => {
    if (!line.trim()) return;
    if (line.length > MAX_LINE_CHARS) { out.push({ unparsed: { line: index + 1, reason: "line_too_large" } }); return; }
    try {
      out.push(JSON.parse(line));
    } catch {
      out.push({ unparsed: { line: index + 1, reason: "not_json" } });
    }
  });
  return out;
}

// A live-API response: a JSON array of envelopes, { envelopes: [...] }, or JSONL. Anything else is no envelopes.
export function parseFeedBody(text) {
  const trimmed = String(text).trim();
  if (!trimmed) return [];
  if (trimmed.startsWith("[")) {
    try { const list = JSON.parse(trimmed); return Array.isArray(list) ? list : []; } catch { return parseJsonl(trimmed); }
  }
  if (trimmed.startsWith("{") && !trimmed.includes("\n")) {
    try {
      const doc = JSON.parse(trimmed);
      if (Array.isArray(doc.envelopes)) return doc.envelopes;
      if (isObject(doc.event)) return [doc];
      return [];
    } catch { return parseJsonl(trimmed); }
  }
  return parseJsonl(trimmed);
}

// ── Keys (view side) ──────────────────────────────────────────────────────────────────────────────────────────
// GET /api/view/key is not specified beyond "may serve the key". Accepted shapes: { key_id, public_key } or
// { keys: [...] } or an array of those, where public_key is the raw 32-byte Ed25519 key as 64 hex characters.
// The result only offers keys; verifyChain uses one only if its sha256 matches the page's pin.
export function parseKeyResponse(doc) {
  const items = Array.isArray(doc) ? doc : isObject(doc) && Array.isArray(doc.keys) ? doc.keys : isObject(doc) ? [doc] : [];
  const keys = {};
  for (const item of items) {
    if (!isObject(item) || typeof item.key_id !== "string" || typeof item.public_key !== "string") continue;
    if (!/^[0-9a-f]{64}$/.test(item.public_key)) continue;
    keys[item.key_id] = fromHex(item.public_key);
  }
  return keys;
}

// Test key derivation for the ?pins=test mode, by the vectors' rule: the Ed25519 key whose 32-byte seed is
// sha256(seedText). WebCrypto has no raw private import, so the seed goes in the fixed PKCS#8 wrapper and the
// public half is read back from the JWK export. Anyone can derive this key; it is never a production pin.
const PKCS8_ED25519_PREFIX = Uint8Array.from([0x30, 0x2e, 0x02, 0x01, 0x00, 0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x70, 0x04, 0x22, 0x04, 0x20]);
export async function publicKeyFromSeedText(seedText) {
  const seed = new Uint8Array(await crypto.subtle.digest("SHA-256", utf8(seedText)));
  const pkcs8 = new Uint8Array(PKCS8_ED25519_PREFIX.length + 32);
  pkcs8.set(PKCS8_ED25519_PREFIX);
  pkcs8.set(seed, PKCS8_ED25519_PREFIX.length);
  const key = await crypto.subtle.importKey("pkcs8", pkcs8, { name: "Ed25519" }, true, ["sign"]);
  const jwk = await crypto.subtle.exportKey("jwk", key);
  const b64 = jwk.x.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (jwk.x.length % 4)) % 4);
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
}
