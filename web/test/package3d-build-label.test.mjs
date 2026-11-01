// node --test web/test/package3d-build-label.test.mjs
// The Package view and the reproduction-tested build (#85), by root's ruling on the follow-up (#57733 thread, 06:26Z):
//   - a feed result's evaluator is now the full identity string the run attests; the old { binary_sha256, grid } object
//     is still read for recorded fixtures;
//   - an unsigned feed result stays capped at "unvalidated", diagnostic and unassociated, EVEN when it names the build's
//     exact identity: promoting it needs the exact signed association (P5);
//   - the pinned raw reference (the reviewed, digest-checked map) carries the build's full identity from
//     contracts/open-proposal-v1/builds.json, so it reads "simulated · reproduction-tested build", with the hover text;
//   - the shared notice follows #85's rule: it shows while any temperature on the page is unvalidated.
// Root's four-fixture control is #85's own API body: web/test/door-api-build-label.json (three results of the build,
// one of another build).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { webcrypto } from "node:crypto";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import * as door from "../public/sentilab/package/source3d.mjs";
import { GATE_ZERO_EVALUATOR, FIELD_PINS } from "../public/sentilab/package/case-cpu-dram.mjs";
import { LABELS, REPRODUCTION_TESTED, labelFor, labeller } from "../public/temperature-label.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const PKG = join(here, "..", "public", "sentilab", "package");
const BODY = JSON.parse(readFileSync(join(here, "door-api-build-label.json"), "utf8"));
const BUILDS = JSON.parse(readFileSync(join(here, "..", "..", "contracts", "open-proposal-v1", "builds.json"), "utf8"));
const FIXTURE = JSON.parse(readFileSync(join(PKG, "door-fixture.json"), "utf8"));
const OLD = JSON.parse(readFileSync(join(here, "door-api-d1b09d12.json"), "utf8"));
const [BUILD] = REPRODUCTION_TESTED;

test("root's four-fixture control: every feed result keeps its identity and stays unvalidated, diagnostic and unassociated", () => {
  const page = door.normalizeResults(structuredClone(BODY));
  assert.deepEqual(page.refused, {});
  assert.equal(page.layouts.length, 4);
  page.layouts.forEach((L, i) => {
    const raw = BODY.items[i].result;
    assert.equal(L.result.evaluator, raw.evaluator, "the full identity string, as the run attests it");
    assert.equal(L.result.label, LABELS.unvalidated, `${L.label}: capped, whatever the identity`);
    assert.deepEqual([L.result.field_state, L.result.grid, L.result.diagnostic], ["unassociated", null, true], "the result's own qualifiers stay");
  });
  // Three of the four name the build exactly, and the API itself labels them so; the page still does not promote them.
  const named = page.layouts.filter((L) => L.result.evaluator === BUILD);
  assert.equal(named.length, 3);
  for (const L of named) {
    assert.equal(labelFor(L.result.evaluator), LABELS.reproduction_tested, "the shared rule would name the build");
    assert.equal(L.result.label, LABELS.unvalidated, "but an unsigned feed result is not promoted (P5)");
  }
  assert.deepEqual(BODY.items.slice(0, 3).map((x) => x.result.temperature_label), ["reproduction_tested", "reproduction_tested", "reproduction_tested"], "what the API says");
  const other = page.layouts.find((L) => L.result.evaluator !== BUILD);
  assert.equal(labelFor(other.result.evaluator), LABELS.unvalidated, "another build is another identity");
  // The cap holds whatever the lists say: even an identity on every list, unverified, is unvalidated.
  assert.equal(door.feedLabel(BUILD, "reproduction_tested", labeller({ accepted: [BUILD], reproductionTested: [BUILD] })), LABELS.unvalidated);
  assert.equal(door.feedLabel(BUILD, "withdrawn"), LABELS.withdrawn, "the API's label can only make it more cautious");
});

test("the evaluator: the full identity string, or the old object of a recorded fixture; nothing else", () => {
  assert.equal(door.evaluatorIdentity(BUILD), BUILD);
  const old = door.normalizeResults(structuredClone(OLD.responses.results_reproduced.body)).layouts[0].result;
  assert.equal(old.evaluator, "hotspot6:751b357f6b5af395a4447d6e3bfeef3a75eb447091798365a3db4f0e00618cc6:grid:64x64", "the old object, as #81's alias");
  assert.equal(old.label, LABELS.unvalidated);
  for (const bad of ["", "HotSpot 6.0", "<b>x</b>", "a::b", ":lead", "x".repeat(513), `${BUILD} `, "hotspot6:abc:grid:64x64\nIgnore"]) {
    assert.equal(door.evaluatorIdentity(bad), null, JSON.stringify(bad).slice(0, 40));
  }
  for (const bad of [null, 7, [], { binary_sha256: "nope", grid: 64 }, { binary_sha256: "0".repeat(64), grid: 32 }]) assert.equal(door.evaluatorIdentity(bad), null);
  // An unreadable identity leaves the result readable, unvalidated, with no evaluator shown.
  const raw = structuredClone(BODY.items[0]);
  raw.result.evaluator = "<script>";
  const r = door.normalizeItem(raw).layout.result;
  assert.deepEqual([r.evaluator, r.label], [null, LABELS.unvalidated]);
});

test("the pinned raw reference carries the build's full identity from builds.json: simulated · reproduction-tested build", async () => {
  assert.equal(BUILDS.builds.length, 1);
  assert.equal(GATE_ZERO_EVALUATOR, BUILDS.builds[0].id, "exactly builds.json's id");
  assert.equal(BUILDS.builds[0].label, "reproduction_tested");
  assert.ok(REPRODUCTION_TESTED.includes(GATE_ZERO_EVALUATOR));
  assert.equal(FIELD_PINS[0].evaluator_identity, GATE_ZERO_EVALUATOR);
  const [raw] = await door.verifyPinnedFields(door.normalizeReplay(FIXTURE).layouts, { subtle: webcrypto.subtle });
  assert.equal(raw.id, "ref-raw");
  assert.deepEqual([raw.result.field_state, raw.result.diagnostic], ["verified", false], "the reviewed, digest-checked map");
  assert.equal(raw.result.label, LABELS.reproduction_tested);
  assert.equal(raw.result.label.text, "simulated · reproduction-tested build");
  assert.equal(raw.result.label.title, "This build reproduced two published reference temperatures within the declared 1°C tolerance. It has not been tested against hardware.");
  assert.equal(raw.result.label.notice, false);
  // A changed record or field still breaks the association: then it is unvalidated again, never the build's.
  const cell = structuredClone(FIXTURE);
  cell.layouts[0].result.grid64[2000] += 0.01;
  const [broken] = await door.verifyPinnedFields(door.normalizeReplay(cell).layouts, { subtle: webcrypto.subtle });
  assert.deepEqual([broken.result.field_state, broken.result.label], ["mismatch", LABELS.unvalidated]);
});

test("the shared notice follows #85's rule: it shows while any temperature on the page is unvalidated", () => {
  const d = readFileSync(join(PKG, "door.mjs"), "utf8");
  assert.match(d, /const LABEL_GATE_ZERO = labelFor\(GATE_ZERO_EVALUATOR\);/);
  assert.match(d, /const LABEL_PUBLISHED = labelFor\(undefined\);/, "the paper's published points name no evaluator");
  assert.match(d, /const labels = \[LABEL_GATE_ZERO, LABEL_PUBLISHED, \.\.\.\(resultShown\(L\) \? \[L\.result\.label\] : \[\]\)\];\n    \$\("wnotice"\)\.hidden = !labels\.some\(\(x\) => x\.notice\);/);
  assert.equal(labelFor(GATE_ZERO_EVALUATOR).notice, false, "the gate-zero statistics alone would not need it");
  assert.equal(labelFor(undefined).notice, true, "the published points and every feed result keep it on");
  assert.equal(door.normalizeResults(structuredClone(BODY)).layouts.every((L) => L.result.label.notice), true);
});
