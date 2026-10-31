// node --test web/test/verify-core.test.mjs : the browser verifier must accept what Python signs and reject every
// tamper, including a run that drops lanes or whose lanes did not share a budget or a starting pool.
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { verifyDocument as verifyDocumentWithPins, verifyRun as verifyRunWithPins } from "../public/verify-core.js";

const here = dirname(fileURLToPath(import.meta.url));
const dir = mkdtempSync(join(tmpdir(), "tfl-verify-"));
execFileSync(process.env.PYTHON || "python3", [join(here, "make_record.py"), dir]);
const read = (name) => readFileSync(join(dir, name), "utf8");
const fastapi = read("run_fastapi.json");
const pins = JSON.parse(read("pins.json")); // Trusted test configuration, separate from submitted records.
const verifyDocument = (text) => verifyDocumentWithPins(text, pins);
const verifyRun = (text) => verifyRunWithPins(text, pins);

test("accepts a Python-signed four-lane run in both serializations", async () => {
  for (const text of [read("run_stdlib.json"), fastapi]) {
    const report = await verifyRun(text);
    assert.equal(report.allValid, true, JSON.stringify(report.lanes.map((l) => l.reason)));
    assert.deepEqual(report.lanes.map((l) => l.evaluations), [3, 3, 3, 3]);
    assert.equal(report.samePool, true);
  }
});

const edits = {
  "a changed temperature": (s) => s.replace('"maximum_temperature_c":93.0', '"maximum_temperature_c":92.5'),
  "93.0 written as 93": (s) => s.replace('"maximum_temperature_c":93.0', '"maximum_temperature_c":93'),
  "a changed agent id": (s) => s.replace('"agent_id":"random"', '"agent_id":"ucb1"'),
  "a changed non-ASCII character": (s) => s.replace("café", "cafe"),
  "a wrong public key": (s) => s.replace(/"record_public_key":"[0-9a-f]{64}"/, `"record_public_key":"${"11".repeat(32)}"`),
  "three lanes deleted": (s) => {
    const doc = JSON.parse(s);
    for (const id of ["simulated_annealing", "ucb1", "signal_portfolio"]) delete doc.result.lane_results[id];
    return JSON.stringify(doc);
  },
  "every lane deleted": (s) => { const doc = JSON.parse(s); doc.result.lane_results = {}; return JSON.stringify(doc); },
  "an extra lane added": (s) => {
    const doc = JSON.parse(s);
    doc.result.lane_results.extra = doc.result.lane_results.random;
    return JSON.stringify(doc);
  },
  "a summary count that disagrees with the record": (s) => s.replace('"evaluation_count":3', '"evaluation_count":4'),
};
for (const [name, edit] of Object.entries(edits)) {
  test(`rejects a run with ${name}`, async () => {
    const changed = edit(fastapi);
    assert.notEqual(changed, fastapi, "the tamper must land");
    let report;
    try { report = await verifyRun(changed); } catch { return; }
    assert.equal(report.allValid, false);
  });
}

test("rejects lanes that signed different evaluation counts", async () => {
  const report = await verifyRun(read("run_unequal.json"));
  assert.equal(report.recordsValid, true);
  assert.equal(report.equalCounts, false);
  assert.equal(report.allValid, false);
});

test("rejects lanes that signed different starting pools", async () => {
  const report = await verifyRun(read("run_pool.json"));
  assert.equal(report.recordsValid, true);
  assert.equal(report.samePool, false);
  assert.equal(report.allValid, false);
});

test("verifyDocument verifies a published single-lane record and says the run checks were not made", async () => {
  const report = await verifyDocument(read("lane_artifact.json"));
  assert.equal(report.kind, "lane");
  assert.equal(report.allValid, true);
  assert.equal(report.lanes[0].evaluations, 3);
  assert.equal(report.laneSet, null);
  assert.equal(report.equalCounts, null);
});

test("verifyDocument rejects a tampered single-lane record", async () => {
  const changed = read("lane_artifact.json").replace('"maximum_temperature_c":93.0', '"maximum_temperature_c":92.5');
  assert.notEqual(changed, read("lane_artifact.json"), "the tamper must land");
  const report = await verifyDocument(changed);
  assert.equal(report.allValid, false);
});

test("verifyDocument routes a whole run to the run checks and refuses unknown shapes", async () => {
  const run = await verifyDocument(fastapi);
  assert.equal(run.kind, "run");
  assert.equal(run.allValid, true);
  await assert.rejects(verifyDocument('{"hello":1}'), /neither a run nor a lane record/);
});

// Binding: a verified record proves only what it signs, so every label shown beside VALID must be the signed one.
test("rejects a lane file relabelled as another lane", async () => {
  const text = read("lane_artifact.json");
  const relabelled = text.replace('"lane_id":"random"', '"lane_id":"signal_portfolio"');
  assert.notEqual(relabelled, text, "the relabel must land");
  assert.ok(relabelled.indexOf('"lane_id":"signal_portfolio"') < relabelled.indexOf('"events"'), "only the unsigned label changed");
  const report = await verifyDocument(relabelled);
  assert.equal(report.allValid, false);
  assert.match(report.lanes[0].reason, /signs lane "random".*labels it "signal_portfolio"/);
});

test("rejects a run whose lane_results keys were swapped", async () => {
  const swapped = fastapi.replace('"random":{', '"__tmp__":{').replace('"signal_portfolio":{', '"random":{')
    .replace('"__tmp__":{', '"signal_portfolio":{');
  assert.notEqual(swapped, fastapi, "the swap must land");
  const report = await verifyRun(swapped);
  assert.equal(report.laneSet, true, "all four labels are still present");
  assert.equal(report.allValid, false);
});

test("rejects a run whose summary best temperature was lowered", async () => {
  const lowered = fastapi.replace('"best_temperature_c":92.0', '"best_temperature_c":87.0');
  assert.notEqual(lowered, fastapi, "the edit must land");
  const report = await verifyRun(lowered);
  assert.equal(report.recordsValid, true, "the records themselves are untouched");
  assert.equal(report.bestMatchesClaims, false);
  assert.equal(report.allValid, false);
});

test("renders the signed best, and the valid fixture's claims match it", async () => {
  const report = await verifyRun(fastapi);
  assert.equal(report.bestMatchesClaims, true);
  assert.deepEqual(report.lanes.map((l) => l.best), [92, 92, 92, 92]);
  assert.deepEqual(report.lanes.map((l) => l.agentId), ["fixture:random", "fixture:simulated_annealing", "fixture:ucb1", "fixture:signal_portfolio"]);
});

test("rejects a run with a lane spliced in from another run", async () => {
  const report = await verifyRun(read("run_spliced.json"));
  assert.equal(report.laneSet, true);
  const spliced = report.lanes.find((l) => l.laneId === "signal_portfolio");
  const host = report.lanes.find((l) => l.laneId === "random");
  // The splice is honest in every other respect: same signed pool, same signed count, its own label.
  assert.equal(spliced.checked, host.checked, "same-shaped record");
  assert.equal(spliced.pool, host.pool, "the spliced lane signed the same starting pool");
  assert.equal(spliced.evaluations, host.evaluations, "and the same evaluation count");
  assert.equal(spliced.ok, false, "only the run binding rejects it");
  assert.match(spliced.reason, /fixture-b:signal_portfolio/);
  assert.equal(report.allValid, false);
});

test("rejects a response whose id is missing, malformed, or another run's", async () => {
  assert.ok(fastapi.startsWith('{"id":"fixture",'), "fixture shape");
  for (const id of ["null", "123", "false", "{}", '"other-run"', '""']) {
    const changed = fastapi.replace('{"id":"fixture",', `{"id":${id},`);
    const report = await verifyRun(changed);
    assert.equal(report.runIdMatchesDoc, false, id);
    assert.equal(report.allValid, false, id);
    assert.equal(report.runId, "fixture", "the displayed run id is the signed one");
  }
  const noId = fastapi.replace('{"id":"fixture",', "{");
  assert.equal((await verifyRun(noId)).allValid, false, "an API envelope without an id");
  const raw = read("run_raw.json");
  assert.ok(!raw.includes('"id":'), "a raw run_four_lanes() dict has no id key");
  const rawReport = await verifyRun(raw);
  assert.equal(rawReport.allValid, true, "a raw dict is bound by its run_id alone");
  assert.equal(rawReport.runIdMatchesDoc, true);
});
