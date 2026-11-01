// SentiLab Package view: a door record's state in plain words, and the scorer chip. Pure, no DOM (the node tests run
// it). Everything here reads only what the door API reported (source3d.mjs): a run's state, its queue position, its
// codes and reason, the contract's summary, and the API's scorer snapshot. Nothing is derived from the page's animation.
// Codes and reasons come from fixed vocabularies (the contract's reason codes, #81's own reasons); source3d.mjs keeps
// only [a-z0-9_] identifiers, and one without words here reads as itself with spaces. Never visitor text.
import { LIVE_FRESH_MS } from "./source3d.mjs";

// The contract's codes (contracts/open-proposal-v1/reason-codes.json) that a run or a refused attempt can carry. Where
// the door Worker words a code (sentilab PR #82, web/src/door/render.js CODE_TEXT), these are its exact words, so the
// page and the door's own pages say the same thing.
export const WORKER_CODE_WORDS = Object.freeze({
  margin: "too close to the interposer edge (die plus halo)", halo_overlap: "halos overlap", min_spacing: "dies closer than 0.1 mm",
  rotation_not_allowed: "rotation not allowed for this die", out_of_frame: "centre outside the 45 mm frame", die_count: "not eight dies",
  die_order: "dies out of order", lattice: "centre off the 0.5 mm lattice", schema_invalid: "not in the layout format",
  unknown_field: "a field the layout does not have", queue_full: "the scorer's queue is full",
  idempotency_conflict: "an earlier request with this link and layout already stands, so this one was not queued again",
});
export const CODE_WORDS = Object.freeze({
  ...WORKER_CODE_WORDS,
  keepout: "inside a keep-out area", geometry_hash_mismatch: "the geometry does not match its hash",
  not_open_yet: "submissions are not open yet", manifest_closed: "submissions are closed", terms_not_accepted: "the challenge terms were not accepted",
  rate_limited: "too many requests, try again later", budget_exhausted: "the CPU budget is used up",
  timeout: "the simulation ran out of time", stopped: "the simulation was stopped at its CPU cutoff", oracle_error: "the scorer returned an error",
  grant_expired: "the compute grant ended", interrupted: "interrupted by a restart", binding_mismatch: "the score did not match its own layout check",
  router_timeout: "the router ran out of time", check_unfinished: "the check did not finish within its limit",
  reproduction_mismatch: "the replay gave a different score",
  fresh_process_required: "the replay did not run in a fresh process", reproduction_failed: "the replay did not reproduce the score",
});
// #81's own reasons on a run (app/door: dispatch.py REASONS, the launch check's expire and cancel, an unresolved attempt).
export const REASON_WORDS = Object.freeze({
  scorer_down: "the scorer was unreachable", scorer_timeout: "the scorer timed out", scorer_error: "the scorer returned an error",
  scorer_refused: "the scorer refused the run", scorer_cutoff: "the run hit its CPU cutoff", grant_expired: "the compute grant ended",
  interrupted: "interrupted by a restart", window_closed: "the submission window closed before it ran",
  manifest_changed: "the challenge changed before it ran", revalidation_failed: "the stored layout failed its launch check",
  unresolved: "the scorer's answer was lost; it is being reconciled",
});
const plain = (code) => code.replace(/_/g, " ");
export const codeWords = (code) => CODE_WORDS[code] ?? plain(code);
export const reasonWords = (reason) => REASON_WORDS[reason] ?? plain(reason);
const why = (L) => (L.codes?.length ? L.codes.map(codeWords).join(", ") : L.reason ? reasonWords(L.reason) : "");

// One line for a door run's state, from the API's own fields: "Queued · position 3", "Evaluating", "Failed: the scorer
// returned an error", "Expired: the submission window closed before it ran". null for a bundled record (the replay).
const STATE_WORD = Object.freeze({ queued: "Queued", held: "Held", evaluating: "Evaluating", evaluated: "Evaluated", replaying: "Replaying",
  reproduced: "Reproduced", not_reproduced: "Not reproduced", cross_checked: "Cross-checked", failed: "Failed", cancelled: "Cancelled",
  expired: "Expired", rejected: "Rejected" });
export function stateLine(L) {
  const word = STATE_WORD[L?.status];
  if (!word) return null;
  if (L.status === "queued" || L.status === "held") return L.position ? `${word} · position ${L.position}` : word;
  if (L.status === "evaluating") return L.reason ? `${word} · ${reasonWords(L.reason)}` : word;
  const w = why(L);
  return w ? `${word}: ${w}` : word;
}
// The contract's own summary of that state (open_proposals/contract/states.py SUMMARY), when the API gives one.
export const summaryLine = (L) => (L?.summary ? `contract state: ${L.summary}` : null);
// One line for an event of the arrivals panel (after its label).
export function eventLine(e) {
  if (e.kind === "arrival") return "arrived at the door";
  const codes = e.codes?.length ? e.codes.map(codeWords).join(", ") : "";
  if (e.kind === "attempt") return `${e.outcome === "refused" ? "refused" : "rejected"}${codes ? `: ${codes}` : ""}`;
  const word = (STATE_WORD[e.state] ?? plain(e.state)).toLowerCase();
  return codes ? `${word}: ${codes}` : word;
}

// The scorer chip, from the API's scorer snapshot (`scorer` on the results and events pages; #81 dispatch.py
// ScorerState: unknown, up or down, and since when). word:
//   "up"           the API reports the scorer up
//   "busy"         up, and at least one run in the feed is evaluating
//   "unreachable"  the API reports it down (its health probe failed, or a call could not reach it)
//   "unknown"      the API does not know yet, the feed is not connected, or the snapshot is older than LIVE_FRESH_MS
// since: the snapshot's own time (epoch seconds) for up, busy and unreachable; age_s: how old the snapshot is here.
export function scorerChip({ feed = null, nowMs = Date.now() } = {}) {
  const s = feed?.scorer ?? null;
  if (!s || feed.connected !== true || !(nowMs - s.at <= LIVE_FRESH_MS)) return { word: "unknown", since: null, age_s: null };
  const age_s = Math.max(0, Math.round((nowMs - s.at) / 1000));
  if (s.state === "down") return { word: "unreachable", since: s.since, age_s };
  if (s.state === "up") return { word: feed.layouts.some((l) => l.status === "evaluating") ? "busy" : "up", since: s.since, age_s };
  return { word: "unknown", since: null, age_s };
}
// "04:12:31Z": a snapshot time, UTC, to the second.
export const utcTime = (epochS) => new Date(epochS * 1000).toISOString().slice(11, 19) + "Z";
