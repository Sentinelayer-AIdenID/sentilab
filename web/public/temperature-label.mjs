// The one label rule for every temperature on these pages: the run view (app.js), the Lab view (sentilab/lab.js) and
// the Package view (sentilab/package/package.js). Pure, no DOM, so the node tests run it (web/test/temperature-label.test.mjs).
//
// A temperature is labelled by the evaluator identity it came from:
//   - the run view: the result's thermal.solver_version;
//   - the Lab and Package views: the measurement's semantics.evaluator_version (the producer copies solver_version in).
// Replays, the live feed and the API all reach the pages as these same fields, so one rule covers them all.
// An identity names its engine and upstream commit first ("HotSpot-7:<commit>"), then the build, config and grid
// (":binary_sha256:…:config_sha256:…:grid:16x16"; older rows ":sha256:<16 hex>"). A variant extends the commit field
// ("HotSpot-7:<commit>+SLAB-049:…") and is a different evaluator, as is "HotSpot-6.0:…".
//
//   withdrawn     the identity's engine:commit is on WITHDRAWN: the known affected build;
//   illustrative  exactly the bundled interface fixture's identity: illustrative numbers, no solver ran;
//   accepted      exactly an identity on ACCEPTED (there are none yet);
//   unvalidated   anything else: any other identity, and a missing or unreadable one (unvalidated provenance). A
//                 different identity never implies validation.
// A value derived from several (a difference, a gap, a range, an axis) takes the most cautious state among its inputs:
// withdrawn, then unvalidated, then illustrative. It is illustrative only if every input is, accepted only if every
// input is; any other mix, or no input at all, is unvalidated. Withdrawn and unvalidated values show the page notice.

// WITHDRAWN: the known affected build, HotSpot 7.0 at upstream f18831e, in every build, config and grid. It is under
// review for heat-sink coupling; see the SLAB-049 review.
export const WITHDRAWN = Object.freeze(["HotSpot-7:f18831e48cef5d62580585cca0d7fab6c71bc3cc"]);
// ILLUSTRATIVE: the bundled demo replay (sentilab/demo-run.jsonl) is an interface fixture; no solver produced it.
export const ILLUSTRATIVE = Object.freeze(["fixture-no-solver"]);
// ACCEPTED: evaluator identities accepted for comparison. Each entry needs an exact evaluator acceptance, recorded for
// that exact identity string (engine, commit, build, config and grid); it is matched exactly. None yet.
export const ACCEPTED = Object.freeze([]);

// The page notice, shown at the top of any page that shows a withdrawn or unvalidated temperature. One constant:
// reword it here only.
export const NOTICE = "These simulated temperatures are under review and have been withdrawn from comparison with published " +
  "layouts. We are investigating heat-sink coupling and validating the evaluator against reconstructed research layouts. " +
  "Historical results remain available.";

// text: the qualifier; short: the tag beside a value (not "withdrawn" alone, which the evidence views already use for a
// withdrawn node); title: the full sentence, on hover; notice: whether the value shows the page notice.
export const LABELS = Object.freeze({
  withdrawn: Object.freeze({
    state: "withdrawn", notice: true, text: "simulated · pre-correction (withdrawn)", short: "pre-correction",
    title: "Withdrawn: this evaluator build is under review for heat-sink coupling. Not for comparison with published layouts; " +
      "kept as recorded.",
  }),
  unvalidated: Object.freeze({
    state: "unvalidated", notice: true, text: "simulated · unvalidated", short: "unvalidated",
    title: "Unvalidated: this value's evaluator has not been accepted, or isn't named. Not for comparison with published layouts.",
  }),
  illustrative: Object.freeze({
    state: "illustrative", notice: false, text: "illustrative · no solver ran", short: "illustrative",
    title: "Interface fixture: an illustrative number. No solver produced it.",
  }),
  accepted: Object.freeze({ state: "accepted", notice: false, text: "simulated", short: "simulated", title: "Simulated with an accepted evaluator. Not silicon." }),
});

const isObj = (x) => x !== null && typeof x === "object" && !Array.isArray(x);
// The leading engine:commit of an identity, compared without case.
const evaluatorKey = (identity) => identity.trim().split(":", 2).join(":").toLowerCase();

// The rule over given lists (the tests build their own; the pages use the frozen lists above).
export function labeller({ withdrawn = WITHDRAWN, illustrative = ILLUSTRATIVE, accepted = ACCEPTED } = {}) {
  const withdrawnKeys = new Set(withdrawn.map((id) => id.toLowerCase()));
  const illustrativeIds = new Set(illustrative), acceptedIds = new Set(accepted);
  // One value, from one identity.
  const labelFor = (identity) => {
    if (typeof identity !== "string" || identity.trim() === "") return LABELS.unvalidated;   // unvalidated provenance
    if (withdrawnKeys.has(evaluatorKey(identity))) return LABELS.withdrawn;                   // every build of it
    if (illustrativeIds.has(identity)) return LABELS.illustrative;                            // exactly the fixture
    if (acceptedIds.has(identity)) return LABELS.accepted;                                    // exactly as accepted
    return LABELS.unvalidated;
  };
  // A value derived from several: the identities of everything it was made from.
  const labelForAll = (identities) => {
    const list = typeof identities === "string" ? [identities] : Array.isArray(identities) ? identities
      : identities != null && typeof identities[Symbol.iterator] === "function" ? [...identities] : [];
    const labels = list.map(labelFor);
    if (labels.includes(LABELS.withdrawn)) return LABELS.withdrawn;
    if (labels.length > 0 && labels.every((label) => label === LABELS.illustrative)) return LABELS.illustrative;
    if (labels.length > 0 && labels.every((label) => label === LABELS.accepted)) return LABELS.accepted;
    return LABELS.unvalidated;                    // an unvalidated input, a mix of fixture and real inputs, or none
  };
  return Object.freeze({ labelFor, labelForAll });
}
const RULE = labeller();
export const labelFor = RULE.labelFor;
export const labelForAll = RULE.labelForAll;

// ── the run view: a run object (GET /api/runs/{id}, or a replay file of one) ────────────────────────────────
// The identity of every temperature it can show: one per baseline and per oracle result, in record order.
export function runTemperatureIds(run) {
  const ids = [];
  const lanes = isObj(run) && isObj(run.result) && isObj(run.result.lane_results) ? Object.values(run.result.lane_results) : [];
  for (const lane of lanes) {
    for (const e of isObj(lane) && Array.isArray(lane.record) ? lane.record : []) {
      if (!isObj(e) || (e.event !== "baseline" && e.event !== "oracle_result")) continue;
      ids.push(isObj(e.payload) && isObj(e.payload.thermal) ? e.payload.thermal.solver_version : undefined);
    }
  }
  return ids;
}

// ── view envelopes (Lab and Package views) ──────────────────────────────────────────────────────────────────
// node id -> evaluator identity, from the first node.create of each id (project() rejects a repeat). Only measurements
// and comparisons declare semantics, so a candidate maps to undefined.
export function evaluatorIds(envelopes) {
  const ids = new Map();
  for (const env of Array.isArray(envelopes) ? envelopes : []) {
    const body = isObj(env) && isObj(env.event) && env.event.type === "node.create" && isObj(env.event.body) ? env.event.body : null;
    if (!body || typeof body.id !== "string" || ids.has(body.id)) continue;
    ids.set(body.id, isObj(body.semantics) ? body.semantics.evaluator_version : undefined);
  }
  return ids;
}
// The identity behind one envelope's display values: a node.create's own semantics, or for any other event the node it
// names (a verify.add's values belong to the measurement it verifies). Anything else has none.
export function envelopeEvaluator(env, ids) {
  if (!isObj(env) || !isObj(env.event) || !isObj(env.event.body)) return undefined;
  const body = env.event.body;
  if (env.event.type === "node.create") return isObj(body.semantics) ? body.semantics.evaluator_version : undefined;
  return typeof body.node === "string" && ids instanceof Map ? ids.get(body.node) : undefined;
}
// Does an envelope carry a temperature for display (a J, or centre temperatures)?
export const hasTemperature = (env) => isObj(env) && isObj(env.values) && (isObj(env.values.J) || isObj(env.values.center_temps));
// The page notice's test for envelopes: does any of them carry a temperature whose label shows the notice (withdrawn or
// unvalidated)? Envelopes that failed verification count too: the feed lists them.
export function needsNotice(envelopes) {
  const list = (Array.isArray(envelopes) ? envelopes : []).filter(Boolean);
  const ids = evaluatorIds(list);
  return list.some((env) => hasTemperature(env) && labelFor(envelopeEvaluator(env, ids)).notice);
}
