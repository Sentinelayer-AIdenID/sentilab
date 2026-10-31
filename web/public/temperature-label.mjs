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
//   withdrawn     the identity's engine:commit is on WITHDRAWN, or the identity is missing or unreadable (fail safe);
//   illustrative  the bundled interface fixture's identity: illustrative numbers, no solver ran;
//   simulated     any other identity, such as the corrected evaluator.
// A value derived from several (a difference, a gap, a range, an axis) is withdrawn if any of them is, or if it names
// none. A difference of two withdrawn values is withdrawn: the defect distorts the gaps too.

// WITHDRAWN: HotSpot 7.0 at upstream f18831e with the detailed-3D model on, as it runs the TAP-2.5D-generated stack. Its
// link between the heat spreader and the sink puts half of the convection resistance inside the copper, so rises above
// ambient come out about 2.3x too high and differences between layouts 2.3-3.7x too large (about 8-9% of layout pairs
// flip order). Every build, config and grid of it is withdrawn until the corrected evaluator, built under its own
// identity in SLAB-049, reruns them.
export const WITHDRAWN = Object.freeze(["HotSpot-7:f18831e48cef5d62580585cca0d7fab6c71bc3cc"]);
// ILLUSTRATIVE: the bundled demo replay (sentilab/demo-run.jsonl) is an interface fixture; no solver produced it.
export const ILLUSTRATIVE = Object.freeze(["fixture-no-solver"]);

// The page notice, shown at the top of any page that shows a withdrawn temperature. One constant: reword it here only.
export const NOTICE = "Temperatures on this page come from an evaluator under correction: a known heat-sink coupling defect " +
  "overstates temperature rises (about 2.3×) and distorts the gaps between layouts. They're being re-validated against " +
  "published human layouts, so don't compare them with papers. Simulated, not silicon.";

// text: the qualifier; short: the tag beside a value (not "withdrawn" alone, which the evidence views already use for a
// withdrawn node); title: the full sentence, on hover.
export const LABELS = Object.freeze({
  withdrawn: Object.freeze({
    state: "withdrawn", withdrawn: true, text: "simulated · pre-correction (withdrawn)", short: "pre-correction",
    title: "Simulated · pre-correction (withdrawn). This temperature comes from an evaluator under correction: a known " +
      "heat-sink coupling defect overstates temperature rises (about 2.3×) and distorts the gaps between layouts. " +
      "Don't compare it with papers. Simulated, not silicon.",
  }),
  simulated: Object.freeze({ state: "simulated", withdrawn: false, text: "simulated", short: "simulated", title: "Simulated, not silicon." }),
  illustrative: Object.freeze({
    state: "illustrative", withdrawn: false, text: "illustrative · no solver ran", short: "illustrative",
    title: "Interface fixture: an illustrative number. No solver produced it.",
  }),
});

// The leading engine:commit of an identity, compared without case.
const evaluatorKey = (identity) => identity.trim().split(":", 2).join(":").toLowerCase();
const WITHDRAWN_KEYS = new Set(WITHDRAWN.map((id) => id.toLowerCase()));
const ILLUSTRATIVE_KEYS = new Set(ILLUSTRATIVE.map((id) => id.toLowerCase()));

// One value, from one identity.
export function labelFor(identity) {
  if (typeof identity !== "string" || identity.trim() === "") return LABELS.withdrawn;   // missing or unreadable
  const key = evaluatorKey(identity);
  if (WITHDRAWN_KEYS.has(key)) return LABELS.withdrawn;
  if (ILLUSTRATIVE_KEYS.has(key)) return LABELS.illustrative;
  return LABELS.simulated;
}

// A value derived from several (a difference, a gap, a range, an axis): the identities of everything it was made from.
export function labelForAll(identities) {
  const list = typeof identities === "string" ? [identities] : Array.isArray(identities) ? identities
    : identities != null && typeof identities[Symbol.iterator] === "function" ? [...identities] : [];
  if (list.length === 0) return LABELS.withdrawn;                                          // made from nothing we can name
  const labels = list.map(labelFor);
  if (labels.some((label) => label.withdrawn)) return LABELS.withdrawn;
  if (labels.some((label) => label.state === "illustrative")) return LABELS.illustrative;
  return LABELS.simulated;
}

const isObj = (x) => x !== null && typeof x === "object" && !Array.isArray(x);

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
// The page notice's test for envelopes: does any of them carry a temperature labelled withdrawn? Envelopes that failed
// verification count too: the feed lists them.
export function anyWithdrawnTemperature(envelopes) {
  const list = (Array.isArray(envelopes) ? envelopes : []).filter(Boolean);
  const ids = evaluatorIds(list);
  return list.some((env) => hasTemperature(env) && labelFor(envelopeEvaluator(env, ids)).withdrawn);
}
