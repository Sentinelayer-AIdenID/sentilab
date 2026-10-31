// node --test web/test/verify-notice.test.mjs
// The verify page's notice follows the value it shows. verify-core.js signedFacts takes a lane's best peak from the
// baseline, every shared initial sample and every committed proposal, and reports the evaluator identity of each
// (bestIds); temperature-label.mjs reportNeedsNotice labels the shown best by all of them. A committed temperature
// carries the identity of the oracle result it reports: an EARLIER result with the same proposal id, the same candidate
// hash and the same finite temperature; otherwise it names none (unvalidated), and a later result never relabels it.
// Records are signed with the real writer (sundai_controller FlightRecord), as forgery.test.mjs does.
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { verifyDocument } from "../public/verify-core.js";
import { LABELS, labelForAll, reportNeedsNotice, runTemperatureIds } from "../public/temperature-label.mjs";

const HS7 = "HotSpot-7:f18831e48cef5d62580585cca0d7fab6c71bc3cc:sha256:37b2a3bc8dc52462";
const FIXTURE = "fixture-no-solver";
const A = "aa".repeat(32), B = "bb".repeat(32);           // two candidate hashes
const oracle = (proposal, candidate, temp, solver) => ["oracle", proposal, candidate, temp, solver];
const commit = (proposal, candidate, temp) => ["commit", proposal, candidate, temp];

// Each fixture: a baseline at 100.0 °C and one shared sample at 90.0 °C (their evaluators), then oracle results and
// commitments in record order.
const FIXTURES = {
  withdrawnSample: { base: FIXTURE, sample: HS7, ops: [] },
  fixtureOnly: { base: FIXTURE, sample: FIXTURE, ops: [] },
  // A commitment and the result it reports.
  matchFixture: { base: FIXTURE, sample: FIXTURE, ops: [oracle("p1", A, 80.0, FIXTURE), commit("p1", A, 80.0)] },
  matchWithdrawn: { base: FIXTURE, sample: FIXTURE, ops: [oracle("p1", A, 80.0, HS7), commit("p1", A, 80.0)] },
  orphan: { base: FIXTURE, sample: FIXTURE, ops: [commit("p1", A, 80.0)] },
  // Results that must not lend their identity: another proposal, another candidate (root's 1), another value (root's 2),
  // a result after the commitment (root's 3), and a later result for the same proposal (root's 4).
  proposalMismatch: { base: FIXTURE, sample: FIXTURE, ops: [oracle("p2", A, 80.0, FIXTURE), commit("p1", A, 80.0)] },
  candidateMismatch: { base: FIXTURE, sample: FIXTURE, ops: [oracle("p1", B, 80.0, FIXTURE), commit("p1", A, 80.0)] },
  valueMismatch: { base: FIXTURE, sample: FIXTURE, ops: [oracle("p1", A, 85.0, FIXTURE), commit("p1", A, 80.0)] },
  resultAfter: { base: FIXTURE, sample: FIXTURE, ops: [commit("p1", A, 80.0), oracle("p1", A, 80.0, FIXTURE)] },
  laterOverwrite: { base: FIXTURE, sample: FIXTURE, ops: [oracle("p1", A, 80.0, HS7), commit("p1", A, 80.0), oracle("p1", B, 75.0, FIXTURE)] },
  // Two earlier results that both match: the same evaluator (no doubt), or two (ambiguous).
  duplicateSame: { base: FIXTURE, sample: FIXTURE, ops: [oracle("p1", A, 80.0, FIXTURE), oracle("p1", A, 80.0, FIXTURE), commit("p1", A, 80.0)] },
  duplicateAmbiguous: { base: FIXTURE, sample: FIXTURE, ops: [oracle("p1", A, 80.0, HS7), oracle("p1", A, 80.0, FIXTURE), commit("p1", A, 80.0)] },
  // Empty ids on both sides: a missing id, never provenance (astra's two residual controls, rebuilt here).
  emptyCandidate: { base: FIXTURE, sample: FIXTURE, ops: [oracle("p1", "", 80.0, FIXTURE), commit("p1", "", 80.0)] },
  emptyProposal: { base: FIXTURE, sample: FIXTURE, ops: [oracle("", A, 80.0, FIXTURE), commit("", A, 80.0)] },
};

const signed = JSON.parse(execFileSync(process.env.PYTHON || "python3", ["-c", `
import json, sys
from sundai_controller.controller import FlightRecord
spec = json.loads(sys.argv[1])
def lane(lane_id, run_id, base, sample, ops):
    r = FlightRecord()
    r.append("lane_identity_bound", lane_id=lane_id, agent_id=run_id + ":" + lane_id, public_key="ab" * 32)
    r.append("baseline", thermal={"maximum_temperature_c": 100.0, "solver_version": base},
             shared_initial_samples=[{"design_hash": "cd" * 32, "thermal": {"maximum_temperature_c": 90.0, "solver_version": sample}}],
             design_hash="ab" * 32)
    for op in ops:
        if op[0] == "oracle":
            r.append("oracle_result", proposal_id=op[1], candidate_hash=op[2],
                     thermal={"maximum_temperature_c": float(op[3]), "solver_version": op[4]})
        else:
            r.append("proposal_committed", lane_id=lane_id, proposal_id=op[1], candidate_hash=op[2], temperature_c=float(op[3]))
    r.close()
    assert FlightRecord.verify(r.events, r.public_key)
    run = {"run_id": run_id, "lane_results": {lane_id: {"record": r.events, "record_public_key": r.public_key,
           "best_temperature_c": 90.0, "evaluation_count": 0, "record_valid": True}}}
    # Raw JSON text, as the writer serializes it: a JSON.parse round trip would turn 100.0 into 100 and break the hash.
    return {"lane": json.dumps({"lane_id": lane_id, "run_id": run_id, "record_public_key": r.public_key, "events": r.events}),
            "wrapped": json.dumps({"id": run_id, "status": "done", "result": run}), "raw": json.dumps(run)}
print(json.dumps({name: lane("random", "fx", f["base"], f["sample"], f["ops"]) for name, f in spec.items()}))
`, JSON.stringify(FIXTURES)], { encoding: "utf8", cwd: new URL("../../", import.meta.url) }));

// Each fixture as the writer's own text: one lane's record, and the same lane as a whole run in the API's wrapped
// form and the raw run it wraps.
const laneText = (name) => signed[name].lane;
const wrapped = (name) => signed[name].wrapped;
const raw = (name) => signed[name].raw;
const laneOf = async (name) => {
  const report = await verifyDocument(laneText(name));
  assert.equal(report.lanes[0].ok, true, `${name}: the record verifies`);
  return { report, lane: report.lanes[0] };
};

test("regression: a best peak taken from a withdrawn shared sample shows the notice (baseline illustrative, sample withdrawn)", async () => {
  const { report, lane } = await laneOf("withdrawnSample");
  assert.equal(lane.best, 90, "the shown best is the shared sample's 90.0 °C");
  assert.deepEqual(lane.bestIds, [FIXTURE, HS7], "every temperature the best is taken from, with its identity");
  assert.equal(labelForAll(lane.bestIds), LABELS.withdrawn);
  assert.equal(reportNeedsNotice(report), true, "the page shows the notice");
});

test("a best whose every input is the bundled fixture needs no notice", async () => {
  const { report, lane } = await laneOf("fixtureOnly");
  assert.equal(lane.best, 90);
  assert.deepEqual(lane.bestIds, [FIXTURE, FIXTURE]);
  assert.equal(reportNeedsNotice(report), false);
});

test("a commitment carries the identity of the earlier result it reports: fixture, withdrawn, or none (orphan)", async () => {
  const fixture = await laneOf("matchFixture");
  assert.equal(fixture.lane.best, 80, "the committed proposal is the best");
  assert.deepEqual(fixture.lane.bestIds, [FIXTURE, FIXTURE, FIXTURE]);
  assert.equal(reportNeedsNotice(fixture.report), false, "a fixture commitment reported by a fixture result");
  const withdrawn = await laneOf("matchWithdrawn");
  assert.deepEqual(withdrawn.lane.bestIds, [FIXTURE, FIXTURE, HS7]);
  assert.equal(reportNeedsNotice(withdrawn.report), true);
  const orphan = await laneOf("orphan");
  assert.equal(orphan.lane.best, 80);
  assert.deepEqual(orphan.lane.bestIds, [FIXTURE, FIXTURE, undefined]);
  assert.equal(labelForAll(orphan.lane.bestIds), LABELS.unvalidated, "fail safe");
  assert.equal(reportNeedsNotice(orphan.report), true);
});

// Root's four signed controls (each hid the notice while the page showed 80 °C), and the proposal-id control.
for (const [name, why] of [
  ["candidateMismatch", "the earlier result is for another candidate (root's control 1)"],
  ["valueMismatch", "the earlier result measured 85 °C, the commitment says 80 °C (root's control 2)"],
  ["resultAfter", "the only result comes after the commitment (root's control 3)"],
  ["proposalMismatch", "the earlier result is for another proposal"],
]) {
  test(`regression: an unbound commitment is unvalidated and shows the notice: ${why}`, async () => {
    const { report, lane } = await laneOf(name);
    assert.equal(lane.best, 80, "the page shows the committed 80 °C");
    assert.deepEqual(lane.bestIds, [FIXTURE, FIXTURE, undefined], "no result reports this commitment");
    assert.equal(labelForAll(lane.bestIds), LABELS.unvalidated);
    assert.equal(reportNeedsNotice(report), true);
  });
}

for (const [name, field] of [["emptyCandidate", "candidate hash"], ["emptyProposal", "proposal id"]]) {
  test(`regression: an empty ${field} on both the result and the commitment is no join: unvalidated, with the notice`, async () => {
    const { report, lane } = await laneOf(name);
    assert.equal(lane.best, 80, "the page shows the committed 80 °C");
    assert.deepEqual(lane.bestIds, [FIXTURE, FIXTURE, undefined], "an empty id names nothing");
    assert.equal(labelForAll(lane.bestIds), LABELS.unvalidated);
    assert.equal(reportNeedsNotice(report), true);
  });
}

test("regression: a later fixture result never relabels an earlier withdrawn commitment (root's control 4)", async () => {
  const { report, lane } = await laneOf("laterOverwrite");
  assert.equal(lane.best, 80, "the page shows the committed 80 °C, not the later result's 75 °C");
  assert.deepEqual(lane.bestIds, [FIXTURE, FIXTURE, HS7], "the commitment keeps the withdrawn result it reports");
  assert.equal(labelForAll(lane.bestIds), LABELS.withdrawn);
  assert.equal(reportNeedsNotice(report), true);
});

test("two earlier matching results: one evaluator is no doubt; two evaluators are ambiguous, so unvalidated plus both", async () => {
  const same = await laneOf("duplicateSame");
  assert.deepEqual(same.lane.bestIds, [FIXTURE, FIXTURE, FIXTURE]);
  assert.equal(reportNeedsNotice(same.report), false);
  const ambiguous = await laneOf("duplicateAmbiguous");
  assert.deepEqual(ambiguous.lane.bestIds, [FIXTURE, FIXTURE, undefined, HS7, FIXTURE]);
  assert.equal(labelForAll(ambiguous.lane.bestIds), LABELS.withdrawn, "the most cautious wins");
  assert.equal(reportNeedsNotice(ambiguous.report), true);
});

test("the wrapped run and the raw run it wraps read the same identities and give the same notice", async () => {
  for (const name of ["withdrawnSample", "fixtureOnly", "laterOverwrite", "candidateMismatch"]) {
    const [w, r] = [await verifyDocument(wrapped(name)), await verifyDocument(raw(name))];
    assert.equal(w.kind, "run");
    assert.equal(r.kind, "run");
    assert.deepEqual(w.lanes[0].bestIds, r.lanes[0].bestIds, name);
    assert.deepEqual(w.lanes[0].bestIds, (await verifyDocument(laneText(name))).lanes[0].bestIds, `${name}: as in the lane's own record`);
    assert.equal(w.lanes[0].best, r.lanes[0].best);
    assert.equal(reportNeedsNotice(w), reportNeedsNotice(r), name);
    assert.deepEqual(runTemperatureIds(JSON.parse(wrapped(name))), runTemperatureIds(JSON.parse(raw(name))), `${name}: the run view reads both forms alike`);
  }
  assert.equal(reportNeedsNotice(await verifyDocument(raw("withdrawnSample"))), true);
  assert.equal(reportNeedsNotice(await verifyDocument(raw("fixtureOnly"))), false);
  assert.deepEqual(runTemperatureIds(JSON.parse(raw("withdrawnSample"))), [FIXTURE, HS7], "the baseline and its shared sample");
});
