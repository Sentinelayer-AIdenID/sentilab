// Offline flight-record verifier: the same checks as controller.FlightRecord.verify, in the browser.
// It hashes each entry with Python's canonical JSON, json.dumps(sort_keys=True, separators=(",", ":"),
// ensure_ascii=True), and checks every Ed25519 signature with WebCrypto. Nothing is sent anywhere.
//
// JSON.parse would turn 93.0 into 93 and change the hash, so parseRaw keeps every number's exact source
// text. The server writes JSON with Python, so that text is already Python's repr of the value.

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
    const keys = Object.keys(v).sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
    return "{" + keys.map((k) => pyString(k) + ":" + canonical(v[k])).join(",") + "}";
  }
  throw new Error(`cannot canonicalize ${typeof v}`);
}

const hex = (buf) => Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, "0")).join("");
const fromHex = (h) => Uint8Array.from(h.match(/../g).map((x) => parseInt(x, 16)));
const fromB64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
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
  const temps = [];
  const take = (v) => { const n = num(v); if (typeof n === "number" && Number.isFinite(n)) temps.push(n); };
  if (baseline) {
    take(baseline.payload.thermal && baseline.payload.thermal.maximum_temperature_c);
    for (const sample of baseline.payload.shared_initial_samples || []) take(sample && sample.thermal && sample.thermal.maximum_temperature_c);
  }
  for (const e of events) if (e.event === "proposal_committed") take(e.payload.temperature_c);
  return {
    evaluations,
    pool: samples ? samples.join(",") : null,
    laneId: bound && typeof bound.payload.lane_id === "string" ? bound.payload.lane_id : null,
    agentId: bound && typeof bound.payload.agent_id === "string" ? bound.payload.agent_id : null,
    best: temps.length ? Math.min(...temps) : null,
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
export async function verifyDocument(text) {
  const doc = parseRaw(text);
  const result = doc.result && typeof doc.result === "object" ? doc.result : doc;
  if (result.lane_results) return { kind: "run", ...(await verifyRunDoc(doc)) };
  if (Array.isArray(doc.events) && typeof doc.record_public_key === "string") {
    const checked = await verifyRecord(doc.events, doc.record_public_key);
    const facts = checked.ok ? signedFacts(doc.events) : { evaluations: null, pool: null, laneId: null, agentId: null, best: null };
    const verdict = bindLabel(checked, facts, typeof doc.lane_id === "string" ? doc.lane_id : undefined);
    const lane = { laneId: facts.laneId || "lane", agentId: facts.agentId, publicKey: doc.record_public_key,
      evaluations: facts.evaluations, claimedEvaluations: facts.evaluations, best: facts.best,
      claimedValid: undefined, pool: facts.pool, ...verdict };
    return { kind: "lane", runId: typeof doc.run_id === "string" ? doc.run_id : null, runIdUnsigned: true,
      lanes: [lane], missing: [], extra: [], laneSet: null, recordsValid: verdict.ok, equalCounts: null,
      samePool: null, countsMatchClaims: true, bestMatchesClaims: true, allValid: verdict.ok };
  }
  throw new Error("this file is neither a run nor a lane record");
}

// A whole run: a GET /api/runs/{id} response, its `result`, or a raw run_four_lanes() dict.
export async function verifyRun(runText) {
  return verifyRunDoc(parseRaw(runText));
}

async function verifyRunDoc(doc) {
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
    const facts = checked.ok ? signedFacts(lane.record) : { evaluations: null, pool: null, laneId: null, agentId: null, best: null };
    let verdict = bindLabel(checked, facts, laneId);
    if (verdict.ok && (runId === null || facts.agentId !== `${runId}:${laneId}`)) {
      verdict = { ...verdict, ok: false,
        reason: `the record signs agent "${facts.agentId}", not "${runId}:${laneId}": a lane from another run?` };
    }
    out.push({
      laneId,
      agentId: facts.agentId,
      publicKey: lane.record_public_key,
      evaluations: facts.evaluations,
      claimedEvaluations: num(lane.evaluation_count),
      best: facts.best,
      claimedBest: num(lane.best_temperature_c),
      claimedValid: lane.record_valid,
      pool: facts.pool,
      ...verdict,
    });
  }
  const recordsValid = out.length > 0 && out.every((l) => l.ok);
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
    allValid: laneSet && recordsValid && equalCounts && samePool && countsMatchClaims && bestMatchesClaims && runIdMatchesDoc,
  };
}
