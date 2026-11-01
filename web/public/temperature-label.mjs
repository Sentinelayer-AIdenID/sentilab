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
//   reproduction_tested  exactly the build on REPRODUCTION_TESTED: the complete gate-zero build, which reproduced two
//                 published reference temperatures in simulation; it says nothing about hardware;
//   unvalidated   anything else: any other identity, and a missing or unreadable one (unvalidated provenance). A
//                 different identity never implies validation.
// A value derived from several (a difference, a gap, a range, an axis) takes the most cautious state among its inputs:
// withdrawn, then unvalidated, then illustrative. It is illustrative only if every input is, accepted only if every
// input is, reproduction-tested only if every input is; any other mix, or no input at all, is unvalidated. Withdrawn
// and unvalidated values show the page notice. A label is the evaluator's: it never clears a value's own qualifiers
// (a diagnostic, an unassociated field, a replay status), which each view keeps beside it.

// WITHDRAWN: the known affected build, HotSpot 7.0 at upstream f18831e, in every build, config and grid. It is under
// review for heat-sink coupling; see the SLAB-049 review.
export const WITHDRAWN = Object.freeze(["HotSpot-7:f18831e48cef5d62580585cca0d7fab6c71bc3cc"]);
// ILLUSTRATIVE: the bundled demo replay (sentilab/demo-run.jsonl) is an interface fixture; no solver produced it.
export const ILLUSTRATIVE = Object.freeze(["fixture-no-solver"]);
// ACCEPTED: evaluator identities accepted for comparison. Each entry needs an exact evaluator acceptance, recorded for
// that exact identity string (engine, commit, build, config and grid); it is matched exactly. None yet.
export const ACCEPTED = Object.freeze([]);
// REPRODUCTION_TESTED: the one complete build that reproduced gate zero's two published reference temperatures within
// its declared tolerance (SLAB-049): HotSpot 6.0 at upstream a7a3286e, its pinned binary and image, the HotSpot config
// and package-layer files both references share, grid 64 and the pinned centre mapping. The string is generated from
// contracts/open-proposal-v1/builds.json: its readable fields, then build_sha256, a seal over the whole identity, so a
// change to any one field is another identity; it is matched exactly. The broad alias "hotspot6:<binary>:grid:64x64"
// is not this build.
export const REPRODUCTION_TESTED = Object.freeze([
  "HotSpot-6.0:a7a3286e368867c26381e0a23e36b3e273bdeda9:binary_sha256:751b357f6b5af395a4447d6e3bfeef3a75eb447091798365a3db4f0e00618cc6:config_sha256:2a51fb6cf2b149b29d154371450f5924070fa0d5ab7ad170b7185b929ff9007b:grid:64x64:build_sha256:05a9d9cb9ba06a67123c1b4c9d3da14820429221e23b4882abc82cf49c1a0e74",
]);

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
  reproduction_tested: Object.freeze({
    state: "reproduction_tested", notice: false, text: "simulated · reproduction-tested build", short: "reproduction-tested",
    title: "This build reproduced two published reference temperatures within the declared 1°C tolerance. It has not been tested against hardware.",
  }),
});

const isObj = (x) => x !== null && typeof x === "object" && !Array.isArray(x);
// The leading engine:commit of an identity, compared without case.
const evaluatorKey = (identity) => identity.trim().split(":", 2).join(":").toLowerCase();

// The rule over given lists (the tests build their own; the pages use the frozen lists above).
export function labeller({ withdrawn = WITHDRAWN, illustrative = ILLUSTRATIVE, accepted = ACCEPTED, reproductionTested = REPRODUCTION_TESTED } = {}) {
  const withdrawnKeys = new Set(withdrawn.map((id) => id.toLowerCase()));
  const illustrativeIds = new Set(illustrative), acceptedIds = new Set(accepted), reproducedIds = new Set(reproductionTested);
  // One value, from one identity.
  const labelFor = (identity) => {
    if (typeof identity !== "string" || identity.trim() === "") return LABELS.unvalidated;   // unvalidated provenance
    if (withdrawnKeys.has(evaluatorKey(identity))) return LABELS.withdrawn;                   // every build of it
    if (illustrativeIds.has(identity)) return LABELS.illustrative;                            // exactly the fixture
    if (acceptedIds.has(identity)) return LABELS.accepted;                                    // exactly as accepted
    if (reproducedIds.has(identity)) return LABELS.reproduction_tested;                       // exactly the build
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
    if (labels.length > 0 && labels.every((label) => label === LABELS.reproduction_tested)) return LABELS.reproduction_tested;
    return LABELS.unvalidated;                    // an unvalidated input, a mix of fixture and real inputs, or none
  };
  return Object.freeze({ labelFor, labelForAll });
}
const RULE = labeller();
export const labelFor = RULE.labelFor;
export const labelForAll = RULE.labelForAll;

// ── the run view and the verify page: flight records ─────────────────────────────────────────────────────
// A run (a GET /api/runs/{id} response, a replay file of one, or the raw { run_id, lane_results } it wraps), or one
// lane's record document ({ events, ... }, as the TFL-08 records carry it). The identity of every temperature it holds,
// in record order: each baseline, each of its shared initial samples, and each oracle result (a committed proposal's
// temperature is its oracle result's).
export function runTemperatureIds(run) {
  const ids = [];
  const result = isObj(run) && isObj(run.result) ? run.result : run;
  const records = !isObj(result) ? []
    : isObj(result.lane_results) ? Object.values(result.lane_results).map((lane) => (isObj(lane) ? lane.record : null))
    : [result.events];
  const solverOf = (thermal) => (isObj(thermal) ? thermal.solver_version : undefined);
  for (const record of records) {
    for (const e of Array.isArray(record) ? record : []) {
      if (!isObj(e) || (e.event !== "baseline" && e.event !== "oracle_result")) continue;
      const payload = isObj(e.payload) ? e.payload : {};
      ids.push(solverOf(payload.thermal));
      if (e.event === "baseline" && Array.isArray(payload.shared_initial_samples)) {
        for (const sample of payload.shared_initial_samples) ids.push(isObj(sample) ? solverOf(sample.thermal) : undefined);
      }
    }
  }
  return ids;
}

// The verify page's notice, from the verifier's own report (verify-core.js): each lane's shown best peak comes with the
// identity of every temperature it was taken from (bestIds). A lane showing a best whose inputs need the notice, or that
// names none, shows it (labelForAll: the most cautious state wins).
export function reportNeedsNotice(report) {
  const lanes = isObj(report) && Array.isArray(report.lanes) ? report.lanes : [];
  return lanes.some((lane) => isObj(lane) && typeof lane.best === "number" && Number.isFinite(lane.best) &&
    labelForAll(Array.isArray(lane.bestIds) ? lane.bestIds : []).notice);
}

// ── view envelopes (Lab and Package views) ──────────────────────────────────────────────────────────────────
// node id -> evaluator identity, from the node.create the projector APPLIED for each id: the first one it did not
// reject, the same event the views take the node's values from. A rejected create (missing semantics, an unknown kind,
// a repeat) lends no identity. rejected: project()'s rejections ({ event_id, code } entries, or event ids); the pages
// pass their verification's projection.rejected. Only measurements and comparisons declare semantics, so a candidate
// maps to undefined.
export function evaluatorIds(envelopes, rejected = []) {
  const skip = new Set((Array.isArray(rejected) ? rejected : []).map((r) => (isObj(r) ? r.event_id : r)));
  const ids = new Map();
  for (const env of Array.isArray(envelopes) ? envelopes : []) {
    const body = isObj(env) && isObj(env.event) && env.event.type === "node.create" && isObj(env.event.body) ? env.event.body : null;
    if (!body || typeof body.id !== "string" || ids.has(body.id) || skip.has(env.event.event_id)) continue;
    ids.set(body.id, isObj(body.semantics) ? body.semantics.evaluator_version : undefined);
  }
  return ids;
}
// The qualifiers for a value whose J and centre temperatures may come from different measurements: each keeps its own
// source's label, never merged. J's first; the temperatures' too when their label differs (or when there is no J).
export function sourceTags(jLabel, tempsLabel) {
  const tags = [];
  if (jLabel) tags.push({ label: jLabel, text: jLabel.short });
  if (tempsLabel && tempsLabel !== jLabel) tags.push({ label: tempsLabel, text: `temps ${tempsLabel.short}` });
  return tags;
}
// The identities behind a colour scale, as a set: one entry per distinct identity among EXACTLY the rows that view's own
// scale calculation consumed (each view passes its own inputs: the Lab colorScaleInputs, the Package frameScaleInputs;
// there is no shared contributor rule here). A live scale that widened keeps the identities it was widened from
// (previous); any other scale is rebuilt. So it grows with the number of evaluators, never with rows or verifications.
export function scaleIdentities(contributors, ids, previous = null) {
  const out = new Set(previous ?? []);
  for (const env of Array.isArray(contributors) ? contributors : []) out.add(envelopeEvaluator(env, ids));
  return out;
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
