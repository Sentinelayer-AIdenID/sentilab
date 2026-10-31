// Reference implementation of the SentiLab view envelope (DRAFT v0.4, pocket-forge).
// Plain Node ESM, no dependencies. It imports aneta's canonical() and project() (CONTRACT v0.2)
// instead of copying them, so the hashes and the status here are hers.
import { createHash, sign, verify } from "node:crypto";
import { canonical } from "../contract-0.2/resultcheck.mjs";
import { project } from "../contract-0.2/evidence-projection.mjs";

export const VERSION = "view-envelope/0.4";
export const ALG = "ed25519";
const MAX_BYTES = 64 * 1024;
const MAX_ENTRIES = 64;
const MAX_STRING = 512;
const MAX_DEPTH = 8;
const POLL_OK_MS = 5_000;
const ARRIVAL_MS = 60_000;
const CAPPED_FIELDS = ["geometry", "center_temps", "artifact_hashes"];
const ROLES = new Set(["lab", "core", "acceptance_gate"]);
const BOARD_OUTCOMES = new Set(["accepted", "non_improving_current", "within_margin"]);
const SIG_HEX = /^[0-9a-f]{128}$/;

const sha256 = (text) => createHash("sha256").update(text, "utf8").digest("hex");
const isObject = (x) => x !== null && typeof x === "object" && !Array.isArray(x);
// Characters are Unicode code points, so an astral character counts once.
const charCount = (s) => (s.length <= MAX_STRING ? s.length : [...s].length);

// prev_hash of the first envelope. runId is the run the view requested, never one read from the file.
export function genesis(runId) {
  return sha256(`sentilab-view-genesis:${runId}`);
}

// hash = sha256(canonical(envelope without "sig" and without "hash")), lowercase hex.
export function hashEnvelope(env) {
  const { sig, hash, ...covered } = env;
  return sha256(canonical(covered));
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
  const value = sign(null, Buffer.from(hash, "utf8"), privateKey).toString("hex");
  return { ...rest, hash, sig: { key_id: keyId, alg: ALG, value } };
}

// values appear only on node.create of a candidate or measurement, and on verify.add.
const carriesValues = (event) =>
  event.type === "verify.add" || (event.type === "node.create" && ["candidate", "measurement"].includes(event.body?.kind));

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
      if (Buffer.byteLength(canonical(env), "utf8") > MAX_BYTES) reasons.add("too_large");
    } catch {
      reasons.add("malformed");
    }
  }
  return { ok: reasons.size === 0, reasons: [...reasons].sort() };
}

function hasUndefined(root) {
  const stack = [root];
  while (stack.length > 0) {
    const item = stack.pop();
    if (item === undefined) return true;
    if (item !== null && typeof item === "object") for (const child of Object.values(item)) stack.push(child);
  }
  return false;
}

// What the core refuses on append, before signing. null when the envelope may be appended.
function appendRefusal(env, nextSeq) {
  const { event, actor } = env;
  if (event.seq !== nextSeq) return `seq ${event.seq} where ${nextSeq} is next`;
  if (Object.hasOwn(env, "values")) {
    if (env.values === undefined || env.values === null) return "absent values are omitted, never undefined or null";
    if (!carriesValues(event)) return `${event.type} can't carry values`;
  }
  if (hasUndefined(env)) return "absent fields are omitted, never undefined";
  if (!ROLES.has(event.actor_role)) return `actor_role ${event.actor_role} is not lab, core or acceptance_gate`;
  if ((actor?.lab === "gate") !== (event.actor_role === "acceptance_gate")) return "actor.lab gate goes with actor_role acceptance_gate";
  if (event.type === "lifecycle.transition" && BOARD_OUTCOMES.has(event.body?.to) && event.actor_role !== "acceptance_gate") {
    return `only the gate writes ${event.body.to}`;
  }
  return null;
}

// The core's writer. entries: [{ event, ts, actor }]; values: { [event_id]: values }; key: { key_id, privateKey }.
// Builds the envelopes in seq order. With appendChecks (the default) it refuses what the core must refuse:
// a seq that isn't 1, 2, 3, ..., undefined or null where a field should be absent, values on an event that
// can't carry them, a role the contract doesn't allow, and anything over a cap.
// appendChecks: false simulates a faulty writer, and is used only to build the negative vectors.
export function makeChain(run, entries, values, key, { appendChecks = true } = {}) {
  const ordered = [...entries].sort((a, b) => a.event.seq - b.event.seq);
  const envelopes = [];
  let prevHash = genesis(run.run_id);
  ordered.forEach(({ event, ts, actor }, index) => {
    // Copies, so later changes to the inputs can't reach a signed envelope.
    const env = structuredClone({ v: VERSION, event, ts, actor, run });
    if (values && Object.hasOwn(values, event.event_id)) env.values = structuredClone(values[event.event_id]);
    if (appendChecks) {
      const refusal = appendRefusal(env, index + 1);
      if (refusal) throw new Error(`append refused: ${refusal}`);
    }
    env.prev_hash = prevHash;
    const signed = signEnvelope(env, key.privateKey, key.key_id);
    if (appendChecks) {
      const caps = checkCaps(signed);
      if (!caps.ok) throw new Error(`append refused: ${caps.reasons.join(", ")}`);
    }
    envelopes.push(signed);
    prevHash = signed.hash;
  });
  return envelopes;
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

// runId: the run the view requested. pins: [{ key_id, key_sha256 }] from the deployed page.
// keys: Map or object of key_id -> public KeyObject, from anywhere (GET /api/view/key, a manifest);
// a key is used only if its hash matches the pin for that key_id.
// Every envelope gets a row, in seq order (stable for equal seq). Only the projectable prefix reaches
// project(); every row after it is shown but never projected, even if it verifies on its own.
export function verifyChain(envelopes, { runId, pins = [], keys = {} } = {}) {
  if (typeof runId !== "string") throw new TypeError("verifyChain needs the run_id the view requested");
  const list = Array.isArray(envelopes) ? envelopes : [];
  const seqOf = (env) => (wellFormed(env) ? env.event.seq : Infinity);
  const ordered = list.map((env, index) => ({ env, index }))
    .sort((a, b) => seqOf(a.env) - seqOf(b.env) || a.index - b.index)
    .map(({ env }) => env);

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
    if (env.prev_hash !== (prev === null ? genesis(runId) : prev.hash)) reasons.push("prev_hash_mismatch");
    let actual = null;
    try { actual = hashEnvelope(env); } catch { reasons.push("malformed"); }
    if (actual !== null && actual !== env.hash) reasons.push("hash_mismatch");

    const pin = pins.find((p) => p.key_id === env.sig.key_id);
    const key = lookup(keys, env.sig.key_id);
    let keyOk = false;
    if (!pin) reasons.push("key_not_pinned");
    else if (!key) reasons.push("key_unavailable");
    else {
      let keyHash = null;
      try { keyHash = key.asymmetricKeyType === "ed25519" ? keySha256(key) : null; } catch { keyHash = null; }
      if (keyHash !== pin.key_sha256) reasons.push("key_hash_mismatch");
      else keyOk = true;
    }
    if (env.sig.alg !== ALG) reasons.push("bad_alg");
    else if (keyOk && actual !== null) {
      // The signature is checked over the hash recomputed from the content.
      const sigOk = SIG_HEX.test(env.sig.value) && verify(null, Buffer.from(actual, "utf8"), key, Buffer.from(env.sig.value, "hex"));
      if (!sigOk) reasons.push("bad_sig");
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
