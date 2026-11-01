// node --test web/test/door-build-label.test.mjs
// The door API's own results body (web/test/door-api-build-label.json, kept equal to the API's output by
// app/test_door_build_label.py) through the page's label rule (web/public/temperature-label.mjs):
//   - a result of the complete gate-zero build reads "simulated · reproduction-tested build", the same state the API
//     wrote, and shows no notice;
//   - a run that attests anything else (here a package-layer file it staged) is another identity: unvalidated;
//   - the broad alias, carried alone, stays unvalidated;
//   - the page notice hides only when every temperature on the page carries the build's label;
//   - hard rule: the label is the build's; each result's own qualifiers (replay status, binding, no associated grid,
//     candidate, what it does not claim) are still there beside it, unchanged.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { LABELS, REPRODUCTION_TESTED, labelFor, labelForAll, needsNotice, sourceTags } from "../public/temperature-label.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const BODY = JSON.parse(readFileSync(join(HERE, "door-api-build-label.json"), "utf8"));
const [BUILD] = REPRODUCTION_TESTED;
const items = BODY.items;
const results = items.map((item) => item.result);
const ALIAS = `hotspot6:${BUILD.split(":binary_sha256:")[1].split(":")[0]}:grid:64x64`;
// A view envelope carrying one door temperature under the identity the API named (as the Lab and Package views take it).
const envelope = (id, evaluator) => ({ event: { type: "node.create", body: { id, kind: "measurement",
  ...(evaluator === undefined ? {} : { semantics: { evaluator_version: evaluator } }) } }, values: { J: { value: 115.9, unit: "C" } } });

test("the fixture is the door API's results body: four scored runs, three of them the gate-zero build", () => {
  assert.equal(BODY.schema, "sentilab-door-results/1");
  assert.equal(items.length, 4);
  assert.deepEqual(results.map((r) => r.evaluator === BUILD), [true, true, true, false]);
});

test("each result's label, by the page's rule, is the state the API wrote for it", () => {
  for (const r of results) assert.equal(labelFor(r.evaluator).state, r.temperature_label, r.evaluator);
  for (const r of results.slice(0, 3)) {
    assert.equal(labelFor(r.evaluator), LABELS.reproduction_tested);
    assert.equal(labelFor(r.evaluator).text, "simulated · reproduction-tested build");
    assert.equal(labelFor(r.evaluator).notice, false);
  }
  assert.equal(labelFor(results[3].evaluator), LABELS.unvalidated, "another staged package file is another build");
  assert.equal(results[3].evaluator.split(":config_sha256:")[0], BUILD.split(":config_sha256:")[0], "same binary, same engine");
  assert.equal(labelFor(ALIAS), LABELS.unvalidated, "the broad alias alone stays unvalidated");
});

test("the page notice hides only when every temperature on the page carries the build's label", () => {
  const build = results.slice(0, 3).map((r) => r.evaluator);
  assert.equal(labelForAll(build).notice, false);
  assert.equal(needsNotice(build.map((e, i) => envelope(`m${i}`, e))), false);
  assert.equal(labelForAll(results.map((r) => r.evaluator)).notice, true, "one other build on the page");
  assert.equal(needsNotice(results.map((r, i) => envelope(`m${i}`, r.evaluator))), true);
  assert.equal(needsNotice([...build.map((e, i) => envelope(`m${i}`, e)), envelope("a", ALIAS)]), true, "the alias beside them");
  assert.equal(needsNotice([...build.map((e, i) => envelope(`m${i}`, e)), envelope("u", undefined)]), true, "an unassociated value beside them");
});

test("hard rule: the build's label leaves every result's own qualifiers in place", () => {
  const [reproduced, notReproduced, bindingMismatch] = items;
  assert.equal(reproduced.status, "reproduced");
  assert.equal(notReproduced.status, "not_reproduced");
  assert.equal(notReproduced.result.verification.replay, "not_reproduced");
  assert.equal(notReproduced.result.replay.match, false);
  assert.equal(notReproduced.verdict, null);
  assert.equal(bindingMismatch.result.binding_ok, false);
  assert.equal(bindingMismatch.result.verification.binding_ok, false);
  assert.equal(bindingMismatch.result.verification.candidate, false);
  for (const item of items.slice(0, 3)) {
    assert.equal(item.result.temperature_label, "reproduction_tested");
    assert.equal(item.result.grid64, null, "no field is associated with the value");
    assert.deepEqual(item.result.verification.binding_basis, ["per_die", "wire"], "no grid check is claimed");
    assert.deepEqual(item.result.verification.not_claimed, ["beat", "margin", "routed wire", "source acceptance"]);
    assert.equal(item.result.label, "simulated, not silicon; HotSpot 6.0, grid 64; max_chiplet_centre_cell_mean_C");
  }
  // Beside an unassociated value, each keeps its own tag: the build's never replaces the other's.
  assert.deepEqual(sourceTags(labelFor(BUILD), labelFor(undefined)).map((t) => t.text), ["reproduction-tested", "temps unvalidated"]);
});
