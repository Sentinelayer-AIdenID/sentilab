import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { parseRaw, canonical, verifyChain, verifyDocument, verifyRun } from "../public/verify-core.js";

// Keep Python's exact numeric representations while separating trusted test pins
// from the uploaded document. Every artifact comes from the real run_four_lanes.
const data = parseRaw(execFileSync(process.env.PYTHON || "python3",
  ["-m", "sundai_controller.test_trust", "--fixtures"],
  { encoding: "utf8", cwd: new URL("../../", import.meta.url) }));
const inspect = (doc, pins = data.pins) => verifyDocument(canonical(doc), pins);

test("real Python experiment authenticates each record under explicitly pinned service root", async () => {
  const run = await verifyRun(canonical(data.run), data.pins);
  assert.equal(run.allValid, true, JSON.stringify(run.lanes.map((l) => l.originReason)));
  assert.equal(run.authentic, true);
  assert.equal(run.scientificValidity, "not checked");
  const lane = await inspect(data.valid);
  assert.equal(lane.allValid, true);
  assert.equal(lane.runIdUnsigned, false);
  assert.equal(lane.lanes[0].origin, "authentic");
});

for (const [name, doc] of Object.entries(data.cases)) {
  test(`service trust rejects ${name}`, async () => {
    const report = await inspect(doc);
    assert.equal(report.allValid, false);
    assert.equal(report.authentic, false);
    assert.equal((await verifyChain(doc.events, doc.record_certificate, data.pins,
      { runId: doc.run_id, laneId: doc.lane_id })).ok, false);
    if (name === "resigned-temperature") assert.equal(report.lanes[0].integrity, true);
    if (name === "altered-payload") assert.equal(report.lanes[0].integrity, false);
  });
}

test("old throwaway-key records are integrity only, unanchored", async () => {
  const report = await inspect(data.legacy);
  assert.equal(report.allValid, false);
  assert.equal(report.recordsValid, true);
  assert.equal(report.authentic, false);
  assert.equal(report.lanes[0].origin, "unanchored");
  assert.equal(report.lanes[0].originReason, "integrity only, unanchored");
  assert.equal(report.scientificValidity, "not checked");
});

test("file-carried roots never configure pins; removal revokes even a valid certificate", async () => {
  const doc = { ...data.valid, pinned_service_keys: data.pins };
  assert.equal((await verifyDocument(canonical(doc))).authentic, false);
  assert.equal((await inspect(doc, {})).authentic, false);
  assert.equal((await inspect(doc)).authentic, true);
});

test("certificate expiry uses verifier time and fails at the boundary", async () => {
  const doc = data.valid;
  const expiry = Number(doc.record_certificate.expires_at.text);
  assert.equal((await verifyChain(doc.events, doc.record_certificate, data.pins, { now: expiry - 1 })).ok, true);
  assert.equal((await verifyChain(doc.events, doc.record_certificate, data.pins, { now: expiry })).ok, false);
});
