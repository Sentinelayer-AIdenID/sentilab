// SentiLab Package view: the ONE place this page gets verified data. It wraps view-core.mjs (VIEW ENVELOPE v0.4
// today) and hands package.js a small, version-neutral result. Moving to v0.5 means changing this file only:
// the imports, verifyRun(), the live poll's parsing and the mode rule.
//
// The trust rules are the Lab view's, unchanged:
//   - pins come only from view-pins.js (the deployed page), never from a replay file, its manifest or the API;
//   - ?pins=test (keys anyone can derive) is honoured only on a local server, exactly as lab.js does;
//   - only the projectable prefix (verified, in-run, unbroken from seq 1) is returned for drawing.
import { verifyChain, parseJsonl, parseFeedBody, parseKeyResponse, publicKeyFromSeedText, sha256Hex, VERSION } from "../view-core.mjs";
import { VIEW_PINS } from "../view-pins.js";

export const CONTRACT_VERSION = VERSION;
export const DEMO = Object.freeze({ url: "../demo-run.jsonl", runId: "demo-8c-0001", label: "demo-run.jsonl · bundled interface fixture" });
// The Lab view's rule (lab.js TEST_PIN_HOSTS): anyone can derive the test keys, so a public host must never accept
// them; there they would let a forged file show as verified on our domain.
export const TEST_PIN_HOSTS = Object.freeze(["localhost", "127.0.0.1", "[::1]"]);
export const TEST_KEY_NAMES = Object.freeze(["core"]);
export const testPinsAllowed = (hostname) => TEST_PIN_HOSTS.includes(String(hostname));
export const LIVE_POLL_MS = 1000;
export const LIVE_BACKOFF_MS = 5000;
const MAX_ENVELOPES = 20000;

const isObj = (x) => x !== null && typeof x === "object" && !Array.isArray(x);

// Plain words for the reason codes, most serious first (the Lab view's list).
export const REASONS = Object.freeze([
  ["hash_mismatch", "content does not match its hash"],
  ["bad_sig", "bad signature"],
  ["prev_hash_mismatch", "prev_hash break"],
  ["seq_gap", "seq gap"],
  ["seq_repeat", "seq repeat"],
  ["run_mismatch", "envelope from another run"],
  ["malformed", "malformed envelope"],
  ["bad_version", "unknown envelope version"],
  ["bad_alg", "unknown signature algorithm"],
  ["key_hash_mismatch", "served key does not match the pin"],
  ["key_unavailable", "pinned key not served"],
  ["key_not_pinned", "no pinned key"],
  ["ed25519_unsupported", "this browser cannot check Ed25519"],
]);
const REASON_TEXT = new Map(REASONS);
const REASON_RANK = new Map(REASONS.map(([code], i) => [code, i]));
export const reasonText = (code) => REASON_TEXT.get(code) ?? String(code);
const KEY_REASONS = new Set(["key_not_pinned", "key_unavailable", "key_hash_mismatch", "ed25519_unsupported", "bad_alg", "bad_version"]);

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
    // The core may serve the key; verifyChain uses it only if its sha256 matches a pin.
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
    return { keys: parseKeyResponse(await r.json()), note: "pinned key fetched from /api/view/key and checked against the pin" };
  } catch {
    return { keys: {}, note: "pinned key not served (/api/view/key unreachable)" };
  }
}

// ── parsing ─────────────────────────────────────────────────────────────────────────────────────────────────
export const parseReplay = (text) => parseJsonl(text);

// A file the user opened carries no request, so the view checks it against the run its lowest-seq envelope names
// (the Lab view's rule) and says so on screen.
export function runIdFromFile(envelopes) {
  const first = envelopes.filter((e) => isObj(e?.event) && Number.isSafeInteger(e.event.seq) && isObj(e.run) && typeof e.run.run_id === "string")
    .sort((a, b) => a.event.seq - b.event.seq)[0];
  return first ? first.run.run_id : "";
}

// A seeded drill is declared by the core in the withdrawal itself. Over-labelling a drill is the safe error, so any
// well-formed envelope counts, verified or not (the Lab view's rule).
export function isDrill(envelopes) {
  return envelopes.some((env) => isObj(env) && isObj(env.event) && env.event.type === "withdraw" &&
    isObj(env.event.body) && typeof env.event.body.reason === "string" && /^\s*drill\b/i.test(env.event.body.reason));
}

// ── verification ────────────────────────────────────────────────────────────────────────────────────────────
// The version-neutral result package.js and the tests use:
//   ordered          every envelope, in the verifier's row order (seq order)
//   rows             one per envelope: { seq, event_id, status, reasons, oversize, projected }
//   prefixEnvelopes  ONLY the projectable prefix; the scene is built from these and nothing else
//   prefixEnd (K), frozen, label ("chain broken after seq K; board frozen at seq K"), chainOk, verified, total
//   projection       project() over the prefix (the verifier's), projectionError
//   firstBreak       the first row after the prefix, with plain-word reasons
export async function verifyRun(envelopes, { runId, trust }) {
  const v = await verifyChain(envelopes, { runId, pins: trust.pins, keys: trust.keys });
  const prefixEnvelopes = v.ordered.slice(0, v.prefix);
  const after = v.rows[v.prefix] ?? null;
  return {
    runId,
    ordered: v.ordered,
    rows: v.rows,
    prefixEnvelopes,
    prefixCount: v.prefix,
    prefixEnd: v.prefix_end,
    frozen: v.frozen,
    label: v.label,
    chainOk: v.chain_ok,
    total: v.rows.length,
    verified: v.rows.filter((r) => r.status === "verified").length,
    projection: v.projection,
    projectionError: v.projection_error,
    firstBreak: after ? {
      seq: after.seq, status: after.status, oversize: [...after.oversize], reasons: [...after.reasons],
      text: after.oversize.length ? after.oversize.map((r) => `oversize: ${r}`).join(", ") : after.reasons.map(reasonText).join(", "),
      keyOnly: after.oversize.length === 0 && after.reasons.length > 0 && after.reasons.every((r) => ["key_not_pinned", "key_unavailable", "ed25519_unsupported"].includes(r)),
    } : null,
  };
}

// The chain badge: how many rows verified, and the reasons for the rest, most serious first.
export function chainSummary(rows) {
  const total = rows.length;
  const verified = rows.filter((r) => r.status === "verified").length;
  const byCode = new Map();
  for (const row of rows) {
    for (const code of row.reasons) {
      if (!byCode.has(code)) byCode.set(code, { code, count: 0, firstSeq: row.seq });
      byCode.get(code).count += 1;
    }
  }
  const reasons = [...byCode.values()].sort((a, b) => (REASON_RANK.get(a.code) ?? 99) - (REASON_RANK.get(b.code) ?? 99));
  const phrases = reasons.slice(0, 2).map((r) => (KEY_REASONS.has(r.code) || r.firstSeq == null
    ? reasonText(r.code) : `${reasonText(r.code)} at seq ${r.firstSeq}${r.count > 1 ? ` (+${r.count - 1})` : ""}`));
  return { total, verified, ok: total > 0 && verified === total, phrases };
}

// ── mode (VIEW ENVELOPE v0.6 rule 5): client clock only, never ts ────────────────────────────────────────────
// The same rule as the contract's reference, paging.mjs liveLabel() over the v0.5 progressTracker():
//   1. the latest poll failed: "STALE · transport", at once;
//   2. K (the projectable prefix) is below the highest value it has reached: a late conflict or break froze the
//      board at an earlier seq, so "STALE · chain broken", AT ONCE, even if K grew moments before. LIVE never sits
//      next to a board that just froze;
//   3. otherwise LIVE when a poll succeeded within 5 s and K grew (rose above its high) within 60 s, both
//      inclusive; else STALE (including before the first page).
// Arrivals that don't grow K (duplicates, unverified envelopes, envelopes after a break or conflict) never refresh
// LIVE. After a drop, LIVE returns only when K is back at its high and its last growth is within 60 s.
export const POLL_OK_MS = 5_000;
export const PROGRESS_MS = 60_000;
export const STALE_REASONS = Object.freeze({ transport: "transport", chain_broken: "chain broken" });
export function createProgress() {
  return { K: 0, highK: 0, lastPollOk: null, lastProgress: null, failure: null };
}
// Feed it every poll of the event feed: ok (the page arrived and was read) and K after it.
export function recordPoll(progress, { nowMs, ok, K = progress.K, failure = "transport" }) {
  if (!ok) { progress.failure = failure; return progress; }
  progress.failure = null;
  progress.lastPollOk = nowMs;
  progress.K = K;
  if (K > progress.highK) { progress.highK = K; progress.lastProgress = nowMs; }
  return progress;
}
export function liveMode(progress, nowMs) {
  if (progress.failure) {
    const reason = STALE_REASONS[progress.failure] ?? String(progress.failure);
    return { mode: "STALE", reason, label: `STALE · ${reason}` };
  }
  if (progress.K < progress.highK) return { mode: "STALE", reason: STALE_REASONS.chain_broken, label: `STALE · ${STALE_REASONS.chain_broken}` };
  const within = (t, limit) => Number.isFinite(t) && Number.isFinite(nowMs) && t <= nowMs && nowMs - t <= limit;
  if (within(progress.lastPollOk, POLL_OK_MS) && within(progress.lastProgress, PROGRESS_MS)) {
    return { mode: "LIVE", reason: null, label: `LIVE · progress ${Math.floor((nowMs - progress.lastProgress) / 1000)} s ago` };
  }
  return { mode: "STALE", reason: null, label: "STALE" };
}
// { mode, reason, label } for the header. A replay file is always REPLAY.
export function modeNow(kind, live, nowMs) {
  if (kind === "file") return { mode: "REPLAY", reason: null, label: "REPLAY" };
  return liveMode(live?.progress ?? createProgress(), nowMs);
}

// ── live feed: GET /api/view/runs, then GET /api/view/events?run_id=&after= ──────────────────────────────────
// The Lab view's poller, reduced. onChange() is called after every poll; the caller re-reads feed.state.
export function createLiveFeed({ trust, runId = null, onChange }) {
  const state = {
    runs: null, runsAt: 0, runId, envelopes: [], seen: new Set(), verification: null,
    progress: createProgress(), connected: null, error: "", truncated: false,
  };
  let timer = null, stopped = true;
  const schedule = (ms) => { clearTimeout(timer); if (!stopped) timer = setTimeout(poll, ms); };
  async function poll() {
    if (stopped) return;
    if (typeof document !== "undefined" && document.hidden) return schedule(LIVE_BACKOFF_MS);
    try {
      if (!state.runs || !state.runId || Date.now() - state.runsAt > 15000) {
        const r = await fetch("/api/view/runs", { cache: "no-store" });
        if (!r.ok) throw new Error(`/api/view/runs answered ${r.status}`);
        const doc = await r.json();
        state.runs = (Array.isArray(doc) ? doc : isObj(doc) && Array.isArray(doc.runs) ? doc.runs : [])
          .filter((x) => isObj(x) && typeof x.run_id === "string" && x.run_id.length <= 128).slice(0, 200);
        state.runsAt = Date.now();
        state.progress.failure = null;
        state.connected = true;
        if (!state.runId && state.runs.length) state.runId = state.runs[0].run_id;
        if (!state.runId) { onChange(); return schedule(LIVE_BACKOFF_MS); }
      }
      const after = state.envelopes.reduce((m, e) => (isObj(e?.event) && Number.isSafeInteger(e.event.seq) ? Math.max(m, e.event.seq) : m), 0);
      const r = await fetch(`/api/view/events?run_id=${encodeURIComponent(state.runId)}&after=${after}`, { cache: "no-store" });
      if (!r.ok) throw new Error(`/api/view/events answered ${r.status}`);
      const incoming = parseFeedBody(await r.text());
      state.connected = true;
      state.error = "";
      let added = 0;
      for (const env of incoming) {
        if (state.envelopes.length >= MAX_ENVELOPES) { state.truncated = true; break; }
        const key = JSON.stringify(env);
        if (state.seen.has(key)) continue;
        state.seen.add(key);
        state.envelopes.push(env);
        added += 1;
      }
      if (added) state.verification = await verifyRun(state.envelopes, { runId: state.runId, trust });
      // Rule 5 progress: K after this page. Only a rise above K's high is progress; a drop is "chain broken".
      recordPoll(state.progress, { nowMs: Date.now(), ok: true, K: state.verification?.prefixEnd ?? 0 });
      onChange();
      schedule(LIVE_POLL_MS);
    } catch (error) {
      state.connected = false;
      state.error = String(error?.message ?? error);
      recordPoll(state.progress, { nowMs: Date.now(), ok: false, failure: "transport" });
      onChange();
      schedule(LIVE_BACKOFF_MS);
    }
  }
  return {
    state,
    start() { if (!stopped) return; stopped = false; poll(); },
    stop() { stopped = true; clearTimeout(timer); },
    poke() { if (!stopped) { clearTimeout(timer); poll(); } },
  };
}
