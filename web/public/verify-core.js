// Offline flight-record verifier: the same checks as controller.FlightRecord.verify, in the browser.
// It hashes each entry with Python's canonical JSON, json.dumps(sort_keys=True, separators=(",", ":"),
// ensure_ascii=True), and checks every Ed25519 signature with WebCrypto. Nothing is sent anywhere.
//
// JSON.parse would turn 93.0 into 93 and change the hash, so parseRaw keeps every number's exact source
// text. The server writes JSON with Python, so that text is already Python's repr of the value.

import servicePins from "./trust-pins.json" with { type: "json" };

class RawNumber {
  constructor(text) { this.text = text; }
}

export function parseRaw(text) {
  let i = 0;
  const fail = (what) => { throw new SyntaxError(`${what} at offset ${i}`); };
  const ws = () => { while (i < text.length && " \t\n\r".includes(text[i])) i += 1; };
  function value() {
    ws();
    const c = text[i];
    if (c === "{") {
      i += 1; const obj = Object.create(null); ws();
      if (text[i] === "}") { i += 1; return obj; }
      for (;;) {
        ws(); if (text[i] !== "\"") fail("expected key");
        const k = string(); ws(); if (text[i] !== ":") fail("expected :"); i += 1;
        if (Object.prototype.hasOwnProperty.call(obj, k)) fail(`duplicate key ${k}`);
        obj[k] = value(); ws();
        if (text[i] === ",") { i += 1; continue; }
        if (text[i] === "}") { i += 1; return obj; }
        fail("expected , or }");
      }
    }
    if (c === "[") {
      i += 1; const arr = []; ws();
      if (text[i] === "]") { i += 1; return arr; }
      for (;;) {
        arr.push(value()); ws();
        if (text[i] === ",") { i += 1; continue; }
        if (text[i] === "]") { i += 1; return arr; }
        fail("expected , or ]");
      }
    }
    if (c === "\"") return string();
    if (text.startsWith("true", i)) { i += 4; return true; }
    if (text.startsWith("false", i)) { i += 5; return false; }
    if (text.startsWith("null", i)) { i += 4; return null; }
    const m = /^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/.exec(text.slice(i, i + 64));
    if (!m) fail("unexpected token");
    i += m[0].length;
    return new RawNumber(m[0]);
  }
  function string() {
    i += 1; let out = "";
    for (;;) {
      if (i >= text.length) fail("unterminated string");
      const c = text[i];
      if (c === "\"") { i += 1; return out; }
      if (c === "\\") {
        const e = text[i + 1];
        const simple = { "\"": "\"", "\\": "\\", "/": "/", b: "\b", f: "\f", n: "\n", r: "\r", t: "\t" };
        if (e in simple) { out += simple[e]; i += 2; continue; }
        if (e === "u" && /^[0-9a-fA-F]{4}$/.test(text.slice(i + 2, i + 6))) {
          out += String.fromCharCode(parseInt(text.slice(i + 2, i + 6), 16)); i += 6; continue;
        }
        fail("bad escape");
      }
      if (c < " ") fail("control character in string");
      out += c; i += 1;
    }
  }
  const v = value(); ws();
  if (i !== text.length) fail("trailing data");
  return v;
}

const SHORT = { "\"": "\\\"", "\\": "\\\\", "\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t" };

function pyString(s) {
  let out = "\"";
  for (let k = 0; k < s.length; k += 1) {
    const ch = s[k];
    const code = s.charCodeAt(k);
    if (SHORT[ch]) out += SHORT[ch];
    else if (code < 0x20 || code > 0x7e) out += "\\u" + code.toString(16).padStart(4, "0");
    else out += ch;
  }
  return out + "\"";
}

function compareCodePoints(a, b) {
  let i = 0; let j = 0;
  while (i < a.length && j < b.length) {
    const left = a.codePointAt(i); const right = b.codePointAt(j);
    if (left !== right) return left - right;
    i += left > 0xffff ? 2 : 1;
    j += right > 0xffff ? 2 : 1;
  }
  return a.length - b.length;
}

// Python's json.dumps(value, sort_keys=True, separators=(",", ":")): keys sorted by code point.
export function canonical(v) {
  if (v === null) return "null";
  if (v === true) return "true";
  if (v === false) return "false";
  if (v instanceof RawNumber) {
    if (/^-?(?:nan|inf)/i.test(v.text)) throw new Error("non-finite number");
    return v.text;
  }
  if (typeof v === "string") return pyString(v);
  if (Array.isArray(v)) return "[" + v.map(canonical).join(",") + "]";
  if (typeof v === "object") {
    const keys = Object.keys(v).sort(compareCodePoints);
    return "{" + keys.map((k) => pyString(k) + ":" + canonical(v[k])).join(",") + "}";
  }
  throw new Error(`cannot canonicalize ${typeof v}`);
}

const hex = (buf) => Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, "0")).join("");
const fromHex = (h) => Uint8Array.from(h.match(/../g).map((x) => parseInt(x, 16)));
function fromB64(s) {
  // Match Python's strict decoding for signatures: alphabet and required padding,
  // with no whitespace (atob itself silently accepts whitespace/missing padding).
  if (typeof s !== "string" || /[^A-Za-z0-9+/=]/.test(s)
    || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(s)) {
    throw new TypeError("signature is not base64");
  }
  return Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
}
const num = (v) => (v instanceof RawNumber ? Number(v.text) : v);
const isInt = (v) => v instanceof RawNumber && /^-?(?:0|[1-9]\d*)$/.test(v.text);

export async function sha256Hex(text) {
  return hex(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)));
}

// Mirrors FlightRecord.verify. Returns {ok, checked, reason, finalHash}; reason names the first failure.
export async function verifyRecord(events, publicKeyHex, subtle = crypto.subtle) {
  const bad = (reason, checked = 0) => ({ ok: false, checked, reason, finalHash: null });
  if (!Array.isArray(events) || events.length < 2) return bad("a record needs at least two events");
  if (typeof publicKeyHex !== "string" || !/^[0-9a-f]{64}$/.test(publicKeyHex)) return bad("public key is not 32-byte hex");
  if (events[events.length - 1]?.event !== "run_closed") return bad("the record is not closed (last event is not run_closed)");
  let key;
  try {
    key = await subtle.importKey("raw", fromHex(publicKeyHex), { name: "Ed25519" }, false, ["verify"]);
  } catch (e) {
    return bad(`this browser cannot verify Ed25519 signatures (${e.name || e})`);
  }
  const want = ["event", "hash", "payload", "previous_hash", "sequence", "signature", "timestamp"];
  let prev = "0".repeat(64);
  for (let seq = 0; seq < events.length; seq += 1) {
    const e = events[seq];
    if (!e || typeof e !== "object" || Array.isArray(e)) return bad(`entry ${seq} is not an object`, seq);
    if (Object.keys(e).sort().join() !== want.join()) return bad(`entry ${seq} has unexpected fields`, seq);
    if (!isInt(e.sequence) || num(e.sequence) !== seq) return bad(`entry ${seq} has the wrong sequence number`, seq);
    if (e.previous_hash !== prev) return bad(`entry ${seq} does not chain to the previous hash`, seq);
    if (!(e.timestamp instanceof RawNumber) || !Number.isFinite(num(e.timestamp))) return bad(`entry ${seq} has a bad timestamp`, seq);
    if (typeof e.event !== "string" || !e.event) return bad(`entry ${seq} has no event name`, seq);
    if (!e.payload || typeof e.payload !== "object" || Array.isArray(e.payload)) return bad(`entry ${seq} payload is not an object`, seq);
    if (typeof e.hash !== "string" || !/^[0-9a-f]{64}$/.test(e.hash)) return bad(`entry ${seq} hash is malformed`, seq);
    const body = { sequence: e.sequence, previous_hash: e.previous_hash, timestamp: e.timestamp, event: e.event, payload: e.payload };
    if ((await sha256Hex(canonical(body))) !== e.hash) return bad(`entry ${seq} (${e.event}) content does not match its hash`, seq);
    let sig;
    try { sig = fromB64(e.signature); } catch { return bad(`entry ${seq} signature is not base64`, seq); }
    if (!(await subtle.verify({ name: "Ed25519" }, key, sig, fromHex(e.hash)))) return bad(`entry ${seq} (${e.event}) signature is invalid`, seq);
    prev = e.hash;
  }
  const closing = events[events.length - 1];
  if (!isInt(closing.payload.event_count) || num(closing.payload.event_count) !== events.length) return bad("closing event_count does not match", events.length);
  if (closing.payload.final_hash !== closing.previous_hash) return bad("closing final_hash does not match", events.length);
  return { ok: true, checked: events.length, reason: "", finalHash: closing.hash };
}

// Reviewed service roots only, shared with sundai_controller/trust.py.
// No production public root was supplied: empty pins deliberately authenticate
// nothing. Add a key_id to rotate; remove it to revoke. Historical records use
// current-time expiry too. Never populate this map from an uploaded document.
export const PINNED_SERVICE_KEYS = Object.freeze(Object.fromEntries(
  servicePins.map(({ key_id, public_key_hex }) => [key_id, public_key_hex])));
const CERTIFICATE_VERSION = "sentilab.lane-certificate.v1";

export async function verifyChain(events, certificate, pins = PINNED_SERVICE_KEYS,
  { runId, laneId, now = Date.now() / 1000 } = {}) {
  const bad = (reason) => ({ ok: false, reason });
  try {
    const fields = ["expires_at", "key_id", "lane_id", "lane_public_key", "run_id", "signature", "version"];
    if (!certificate || typeof certificate !== "object" || Array.isArray(certificate)
      || Object.keys(certificate).sort().join() !== fields.join()
      || certificate.version !== CERTIFICATE_VERSION
      || !["key_id", "run_id", "lane_id", "signature"].every((k) => typeof certificate[k] === "string" && certificate[k])
      || typeof certificate.lane_public_key !== "string" || !/^[0-9a-f]{64}$/.test(certificate.lane_public_key)
      || !isInt(certificate.expires_at) || !Number.isSafeInteger(num(certificate.expires_at))
      || num(certificate.expires_at) <= 0) return bad("malformed service certificate");
    const root = Object.hasOwn(pins, certificate.key_id) ? pins[certificate.key_id] : null;
    if (typeof root !== "string" || !/^[0-9a-f]{64}$/.test(root)) return bad("unknown service key_id");
    const key = await crypto.subtle.importKey("raw", fromHex(root), { name: "Ed25519" }, false, ["verify"]);
    const { signature, ...body } = certificate;
    if (!(await crypto.subtle.verify({ name: "Ed25519" }, key, fromB64(signature),
      new TextEncoder().encode(canonical(body))))) return bad("invalid service certificate signature");
    if (!Number.isFinite(now) || now < 0 || now >= num(certificate.expires_at)) return bad("service certificate expired");
    if ((runId !== undefined && certificate.run_id !== runId)
      || (laneId !== undefined && certificate.lane_id !== laneId)) return bad("service certificate scope mismatch");
    const verified = await verifyRecord(events, certificate.lane_public_key);
    if (!verified.ok) return verified;
    const bindings = events.filter((e) => e.event === "lane_identity_bound");
    if (bindings.length !== 1 || bindings[0].payload.lane_id !== certificate.lane_id
      || bindings[0].payload.agent_id !== `${certificate.run_id}:${certificate.lane_id}`) {
      return bad("service certificate does not match the signed run/lane binding");
    }
    if (!events.every((e) => num(e.timestamp) >= 0 && num(e.timestamp) < num(certificate.expires_at))) {
      return bad("record timestamp outside certificate validity");
    }
    return verified;
  } catch {
    return bad("invalid service certificate");
  }
}

async function originVerdict(events, publicKey, certificate, pins, scope, integrity) {
  if (certificate === undefined || Object.keys(pins).length === 0
    || (certificate && typeof certificate.key_id === "string" && !Object.hasOwn(pins, certificate.key_id))) return { integrity, authentic: false, origin: "unanchored",
    originReason: Object.keys(pins).length ? "integrity only, unanchored"
      : "integrity only, unanchored; service trust pins unconfigured", scientificValidity: "not checked" };
  const chain = await verifyChain(events, certificate, pins, scope);
  const authentic = integrity && chain.ok && certificate.lane_public_key === publicKey;
  return { integrity, authentic, origin: authentic ? "authentic" : "invalid",
    originReason: authentic ? "" : chain.reason || "record key or integrity mismatch", scientificValidity: "not checked" };
}

// The experiment is exactly these four lanes; a run missing one (or carrying an extra) is not a valid run, even if
// every record present verifies.
export const LANE_IDS = ["random", "simulated_annealing", "ucb1", "signal_portfolio"];

// Facts read from a VERIFIED record's signed events, never from the unsigned summary around it.
// lane_identity_bound signs which lane this record is; the lane's best is where the controller's lane_best can
// only be: the initialized pool (baseline + shared samples) or a committed proposal's temperature.
function signedFacts(events) {
  const evaluations = events.filter((e) => e.event === "oracle_result").length;
  const baseline = events.find((e) => e.event === "baseline");
  const bound = events.find((e) => e.event === "lane_identity_bound");
  const samples = baseline && Array.isArray(baseline.payload.shared_initial_samples)
    ? baseline.payload.shared_initial_samples.map((s) => (s && typeof s.design_hash === "string" ? s.design_hash : "?")).sort()
    : null;
  // bestIds: the evaluator identity behind every temperature the best is taken from, in record order. The page labels
  // the best by all of them (temperature-label.mjs, the most cautious state wins).
  const temps = [], bestIds = [];
  const solverOf = (thermal) => (thermal && typeof thermal === "object" && typeof thermal.solver_version === "string" ? thermal.solver_version : undefined);
  const take = (v, ids) => { const n = num(v); if (typeof n === "number" && Number.isFinite(n)) { temps.push(n); bestIds.push(...ids); } };
  if (baseline) {
    take(baseline.payload.thermal && baseline.payload.thermal.maximum_temperature_c, [solverOf(baseline.payload.thermal)]);
    for (const sample of baseline.payload.shared_initial_samples || []) take(sample && sample.thermal && sample.thermal.maximum_temperature_c, [solverOf(sample && sample.thermal)]);
  }
  // A committed temperature carries the identity of the oracle result it reports: one EARLIER in the record with the same
  // proposal id, the same candidate hash and the same finite temperature, joined by event order and exact match. No such
  // result: it names none (unvalidated). Several that name different evaluators: unvalidated, plus every one of them (the
  // most cautious wins). A later result never relabels an earlier commitment.
  const measured = [];
  for (const e of events) {
    if (e.event === "oracle_result") {
      measured.push({ proposal: e.payload.proposal_id, candidate: e.payload.candidate_hash,
        temp: num(e.payload.thermal && e.payload.thermal.maximum_temperature_c), id: solverOf(e.payload.thermal) });
    } else if (e.event === "proposal_committed") {
      const t = num(e.payload.temperature_c);
      const reports = (m) => typeof m.proposal === "string" && m.proposal === e.payload.proposal_id &&
        typeof m.candidate === "string" && m.candidate === e.payload.candidate_hash &&
        typeof t === "number" && Number.isFinite(t) && m.temp === t;
      const ids = [...new Set(measured.filter(reports).map((m) => m.id))];
      take(e.payload.temperature_c, ids.length === 1 ? ids : [undefined, ...ids]);
    }
  }
  return {
    evaluations,
    pool: samples ? samples.join(",") : null,
    laneId: bound && typeof bound.payload.lane_id === "string" ? bound.payload.lane_id : null,
    agentId: bound && typeof bound.payload.agent_id === "string" ? bound.payload.agent_id : null,
    best: temps.length ? Math.min(...temps) : null,
    bestIds,
  };
}

// A verified record proves only what it signs. The file's label for a lane must be the lane the record signed.
function bindLabel(verdict, facts, label) {
  if (!verdict.ok) return verdict;
  if (facts.laneId === null) return { ...verdict, ok: false, reason: "the record does not sign its lane id" };
  if (label !== undefined && facts.laneId !== label) {
    return { ...verdict, ok: false, reason: `the record signs lane "${facts.laneId}", but the file labels it "${label}"` };
  }
  return verdict;
}

// Any file a user may drop: a whole run (verifyRun) or one lane's record artifact, as the TFL-08 leaderboard
// publishes ({lane_id, run_id, record_public_key, events}). A single lane cannot prove the run-level properties
// (all four lanes, equal budgets, one pool), so those are reported as not checked rather than passed.
export async function verifyDocument(text, pins = PINNED_SERVICE_KEYS) {
  const doc = parseRaw(text);
  const result = doc.result && typeof doc.result === "object" ? doc.result : doc;
  if (result.lane_results) return { kind: "run", ...(await verifyRunDoc(doc, pins)) };
  if (Array.isArray(doc.events) && typeof doc.record_public_key === "string") {
    const checked = await verifyRecord(doc.events, doc.record_public_key);
    const facts = checked.ok ? signedFacts(doc.events) : { evaluations: null, pool: null, laneId: null, agentId: null, best: null, bestIds: [] };
    const verdict = bindLabel(checked, facts, typeof doc.lane_id === "string" ? doc.lane_id : undefined);
    const origin = await originVerdict(doc.events, doc.record_public_key, doc.record_certificate, pins,
      { runId: doc.run_id, laneId: doc.lane_id }, verdict.ok);
    const lane = { laneId: facts.laneId || "lane", agentId: facts.agentId, publicKey: doc.record_public_key,
      evaluations: facts.evaluations, claimedEvaluations: facts.evaluations, best: facts.best, bestIds: facts.bestIds,
      claimedValid: undefined, pool: facts.pool, ...verdict, ...origin };
    return { kind: "lane", runId: typeof doc.run_id === "string" ? doc.run_id : null, runIdUnsigned: !origin.authentic,
      lanes: [lane], missing: [], extra: [], laneSet: null, recordsValid: verdict.ok, equalCounts: null,
      samePool: null, countsMatchClaims: true, bestMatchesClaims: true, authentic: origin.authentic,
      scientificValidity: "not checked", allValid: verdict.ok && origin.authentic };
  }
  throw new Error("this file is neither a run nor a lane record");
}

// A whole run: a GET /api/runs/{id} response, its `result`, or a raw run_four_lanes() dict.
export async function verifyRun(runText, pins = PINNED_SERVICE_KEYS) {
  return verifyRunDoc(parseRaw(runText), pins);
}

async function verifyRunDoc(doc, pins) {
  const result = doc.result && typeof doc.result === "object" ? doc.result : doc;
  const lanes = result.lane_results;
  if (!lanes || typeof lanes !== "object" || Array.isArray(lanes)) throw new Error("no lane_results in this file");
  const present = Object.keys(lanes);
  const missing = LANE_IDS.filter((id) => !present.includes(id));
  const extra = present.filter((id) => !LANE_IDS.includes(id));
  // run_four_lanes signs agent_id = "<run_id>:<lane_id>", so every lane must have been signed for THIS run:
  // a lane spliced in from another run (same seed, same pool) carries its own run's id and cannot match.
  const runId = typeof result.run_id === "string" ? result.run_id : null;
  // An API response (a document wrapping `result`) must name the run it serves, as a string equal to the run the
  // lanes were signed for; a present but malformed id (null, a number, false, an object) is a mismatch, never
  // "no id". A raw run_four_lanes() dict carries no id at all and is bound by its run_id alone.
  const envelope = doc.result && typeof doc.result === "object";
  const runIdMatchesDoc = "id" in doc ? typeof doc.id === "string" && runId !== null && doc.id === runId : !envelope;
  const out = [];
  for (const laneId of present) {
    const lane = lanes[laneId];
    const checked = await verifyRecord(lane.record, lane.record_public_key);
    const facts = checked.ok ? signedFacts(lane.record) : { evaluations: null, pool: null, laneId: null, agentId: null, best: null, bestIds: [] };
    let verdict = bindLabel(checked, facts, laneId);
    if (verdict.ok && (runId === null || facts.agentId !== `${runId}:${laneId}`)) {
      verdict = { ...verdict, ok: false,
        reason: `the record signs agent "${facts.agentId}", not "${runId}:${laneId}": a lane from another run?` };
    }
    const origin = await originVerdict(lane.record, lane.record_public_key, lane.record_certificate, pins,
      { runId, laneId }, verdict.ok);
    out.push({
      laneId,
      agentId: facts.agentId,
      publicKey: lane.record_public_key,
      evaluations: facts.evaluations,
      claimedEvaluations: num(lane.evaluation_count),
      best: facts.best,
      bestIds: facts.bestIds,
      claimedBest: num(lane.best_temperature_c),
      claimedValid: lane.record_valid,
      pool: facts.pool,
      ...verdict,
      ...origin,
    });
  }
  const recordsValid = out.length > 0 && out.every((l) => l.ok);
  const authentic = out.length > 0 && out.every((l) => l.authentic);
  const laneSet = missing.length === 0 && extra.length === 0;
  const counts = new Set(out.map((l) => l.evaluations));
  const equalCounts = recordsValid && counts.size === 1 && out[0].evaluations > 0;
  const pools = new Set(out.map((l) => l.pool));
  const samePool = recordsValid && pools.size === 1 && out[0].pool !== null;
  const countsMatchClaims = out.every((l) => l.evaluations === l.claimedEvaluations);
  const bestMatchesClaims = out.every((l) => l.best !== null && l.best === l.claimedBest);
  return {
    runId, lanes: out, missing, extra,
    laneSet, recordsValid, equalCounts, samePool, countsMatchClaims, bestMatchesClaims, runIdMatchesDoc,
    authentic, scientificValidity: "not checked",
    allValid: authentic && laneSet && recordsValid && equalCounts && samePool && countsMatchClaims && bestMatchesClaims && runIdMatchesDoc,
  };
}
