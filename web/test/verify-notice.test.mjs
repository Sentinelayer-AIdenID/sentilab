// node --test web/test/verify-notice.test.mjs
// The verify page's notice follows the value it shows. verify-core.js signedFacts takes a lane's best peak from the
// baseline, every shared initial sample and every committed proposal, and reports the evaluator identity of each
// (bestIds); temperature-label.mjs reportNeedsNotice labels the shown best by all of them. Records are signed with
// the real writer (sundai_controller FlightRecord), as forgery.test.mjs does.
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { verifyDocument } from "../public/verify-core.js";
import { LABELS, labelForAll, reportNeedsNotice, runTemperatureIds } from "../public/temperature-label.mjs";

const HS7 = "HotSpot-7:f18831e48cef5d62580585cca0d7fab6c71bc3cc:sha256:37b2a3bc8dc52462";
const FIXTURE = "fixture-no-solver";

// lanes: { name: [baseline solver, shared sample solver, committed: "none" | oracle solver | "orphan"] }
const signed = JSON.parse(execFileSync(process.env.PYTHON || "python3", ["-c", `
import json, sys
from sundai_controller.controller import FlightRecord
spec = json.loads(sys.argv[1])
def lane(lane_id, run_id, base, sample, committed):
    r = FlightRecord()
    r.append("lane_identity_bound", lane_id=lane_id, agent_id=run_id + ":" + lane_id, public_key="ab" * 32)
    r.append("baseline", thermal={"maximum_temperature_c": 100.0, "solver_version": base},
             shared_initial_samples=[{"design_hash": "cd" * 32, "thermal": {"maximum_temperature_c": 90.0, "solver_version": sample}}],
             design_hash="ab" * 32)
    if committed != "none":
        if committed != "orphan":
            r.append("oracle_result", proposal_id="p1", candidate_hash="ef" * 32,
                     thermal={"maximum_temperature_c": 80.0, "solver_version": committed})
        r.append("proposal_committed", lane_id=lane_id, proposal_id="p1", candidate_hash="ef" * 32, temperature_c=80.0)
    r.close()
    assert FlightRecord.verify(r.events, r.public_key)
    run = {"run_id": run_id, "lane_results": {lane_id: {"record": r.events, "record_public_key": r.public_key,
           "best_temperature_c": 90.0, "evaluation_count": 0, "record_valid": True}}}
    # Raw JSON text, as the writer serializes it: a JSON.parse round trip would turn 100.0 into 100 and break the hash.
    return {"lane": json.dumps({"lane_id": lane_id, "run_id": run_id, "record_public_key": r.public_key, "events": r.events}),
            "wrapped": json.dumps({"id": run_id, "status": "done", "result": run}), "raw": json.dumps(run)}
print(json.dumps({name: lane("random", "fx", *args) for name, args in spec.items()}))
`, JSON.stringify({
  withdrawnSample: [FIXTURE, HS7, "none"],
  fixtureOnly: [FIXTURE, FIXTURE, "none"],
  committedHs7: [FIXTURE, FIXTURE, HS7],
  committedOrphan: [FIXTURE, FIXTURE, "orphan"],
})], { encoding: "utf8", cwd: new URL("../../", import.meta.url) }));

// Each fixture as the writer's own text: one lane's record, and the same lane as a whole run in the API's wrapped
// form and the raw run it wraps.
const laneText = (name) => signed[name].lane;
const wrapped = (name) => signed[name].wrapped;
const raw = (name) => signed[name].raw;

test("regression: a best peak taken from a withdrawn shared sample shows the notice (baseline illustrative, sample withdrawn)", async () => {
  const report = await verifyDocument(laneText("withdrawnSample"));
  const [lane] = report.lanes;
  assert.equal(lane.ok, true, "the record verifies");
  assert.equal(lane.best, 90, "the shown best is the shared sample's 90.0 °C");
  assert.deepEqual(lane.bestIds, [FIXTURE, HS7], "every temperature the best is taken from, with its identity");
  assert.equal(labelForAll(lane.bestIds), LABELS.withdrawn);
  assert.equal(reportNeedsNotice(report), true, "the page shows the notice");
});

test("a best whose every input is the bundled fixture needs no notice", async () => {
  const report = await verifyDocument(laneText("fixtureOnly"));
  assert.equal(report.lanes[0].best, 90);
  assert.deepEqual(report.lanes[0].bestIds, [FIXTURE, FIXTURE]);
  assert.equal(reportNeedsNotice(report), false);
});

test("a committed proposal's temperature carries its oracle result's identity; one with no matching result names none", async () => {
  const committed = await verifyDocument(laneText("committedHs7"));
  assert.equal(committed.lanes[0].best, 80, "the committed proposal is the best");
  assert.deepEqual(committed.lanes[0].bestIds, [FIXTURE, FIXTURE, HS7]);
  assert.equal(reportNeedsNotice(committed), true);
  const orphan = await verifyDocument(laneText("committedOrphan"));
  assert.equal(orphan.lanes[0].best, 80);
  assert.deepEqual(orphan.lanes[0].bestIds, [FIXTURE, FIXTURE, undefined]);
  assert.equal(labelForAll(orphan.lanes[0].bestIds), LABELS.unvalidated, "fail safe");
  assert.equal(reportNeedsNotice(orphan), true);
});

test("the wrapped run and the raw run it wraps read the same identities and give the same notice", async () => {
  for (const name of ["withdrawnSample", "fixtureOnly"]) {
    const [w, r] = [await verifyDocument(wrapped(name)), await verifyDocument(raw(name))];
    assert.equal(w.kind, "run");
    assert.equal(r.kind, "run");
    assert.deepEqual(w.lanes[0].bestIds, r.lanes[0].bestIds, name);
    assert.equal(w.lanes[0].best, r.lanes[0].best);
    assert.equal(reportNeedsNotice(w), reportNeedsNotice(r), name);
    assert.deepEqual(runTemperatureIds(JSON.parse(wrapped(name))), runTemperatureIds(JSON.parse(raw(name))), `${name}: the run view reads both forms alike`);
  }
  assert.equal(reportNeedsNotice(await verifyDocument(raw("withdrawnSample"))), true);
  assert.equal(reportNeedsNotice(await verifyDocument(raw("fixtureOnly"))), false);
  assert.deepEqual(runTemperatureIds(JSON.parse(raw("withdrawnSample"))), [FIXTURE, HS7], "the baseline and its shared sample");
});
