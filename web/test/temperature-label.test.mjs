// node --test web/test/temperature-label.test.mjs
// The one temperature label rule (web/public/temperature-label.mjs):
//   withdrawn     a known affected identity (the WITHDRAWN list);
//   unvalidated   any other identity, and a missing or unreadable one: a different identity never implies validation;
//   illustrative  exactly the bundled interface fixture;
//   accepted      exactly an identity on ACCEPTED (empty: nothing is accepted yet).
// Withdrawn and unvalidated values show the page notice. A value derived from several takes the most cautious state
// among its inputs; illustrative or accepted only if every input is. Values that arrive live (the Lab
// view's /api/view/events poller, the run view's /api/runs/{id}) go through the same rule: a signed fixture event is
// driven through the page's own live poller below.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  WITHDRAWN, ILLUSTRATIVE, ACCEPTED, LABELS, NOTICE, labeller, labelFor, labelForAll, evaluatorIds, envelopeEvaluator, hasTemperature,
  needsNotice, runTemperatureIds,
} from "../public/temperature-label.mjs";
import * as ref from "../../contracts/view-envelope-v0.5/view-envelope.mjs";
import * as refPaging from "../../contracts/view-envelope-v0.6.2/paging.mjs";
import * as paging from "../public/sentilab/paging.mjs";
import { pollLiveOnce } from "../public/sentilab/lab-live.mjs";
import { testKey } from "./sentilab-keys.mjs";

const PUBLIC = join(dirname(fileURLToPath(import.meta.url)), "..", "public");
const COMMIT7 = "f18831e48cef5d62580585cca0d7fab6c71bc3cc";
const LIVE_HS7 = `HotSpot-7:${COMMIT7}:binary_sha256:9f971da7370a59afb425ed1c8754e12bc67a6a95e8333c3b4a9d537fd30a77f6` +
  ":config_sha256:548562a5f49d502f4b9bd03d3a4acc4b42f225056e6d91556416079c291e06d4:grid:16x16";   // the live feed, 2026-10-31
// Identities the known affected evaluator has signed, in each format it has used.
const AFFECTED = [
  `HotSpot-7:${COMMIT7}:sha256:37b2a3bc8dc52462`,                                   // replay/, tfl08/ records
  `HotSpot-7:${COMMIT7}:sha256:e4358b46794ebc00`,                                   // local proof ledger
  LIVE_HS7,
  `HotSpot-7:${COMMIT7}:binary_sha256:e4358b46794ebc00f07102d13b3ca687507834a1784eba135d26d1d493d334b4` +
    ":config_sha256:c31956e38b05fc0d31609656e6c92f29109ec3dee6b148b3b1c28c23c2dd1b18:grid:32x32",
  `HotSpot-7:${COMMIT7}`,
  `  hotspot-7:${COMMIT7.toUpperCase()}:grid:64x64 `,                               // case and padding change nothing
];
// Other identities, including the corrected evaluator's: unvalidated, never plain or validated.
const CORRECTED = "HotSpot-6.0:a7a3286e368867c26381e0a23e36b3e273bdeda9+SLAB-049:grid_dump=all_layers:binary_sha256:00:config_sha256:00:grid:32x32";
const OTHER = [
  CORRECTED,
  `HotSpot-7:${COMMIT7}+SLAB-049:coupling=material_only:binary_sha256:00:config_sha256:00:grid:32x32`,
  "synthetic-fvm-plate-v1-grid40",
  "HotSpot-7:0000000000000000000000000000000000000000:binary_sha256:00",
  "corrected-evaluator-v1",
];
const MISSING = [undefined, null, "", "   ", 42, 0, true, {}, [], ["HotSpot-6.0:x"], { evaluator_version: "HotSpot-6.0:x" }];
const FIXTURE = "fixture-no-solver";

test("a known affected identity is withdrawn, in every format the evaluator has signed", () => {
  for (const id of [...WITHDRAWN, ...AFFECTED]) {
    const label = labelFor(id);
    assert.equal(label, LABELS.withdrawn, id);
    assert.equal(label.state, "withdrawn");
    assert.equal(label.notice, true);
    assert.equal(label.text, "simulated · pre-correction (withdrawn)");
  }
});

test("an unknown or new identity is unvalidated: a different identity never implies validation", () => {
  for (const id of OTHER) {
    const label = labelFor(id);
    assert.equal(label, LABELS.unvalidated, id);
    assert.equal(label.state, "unvalidated");
    assert.equal(label.notice, true, "an unvalidated value shows the notice");
    assert.equal(label.text, "simulated · unvalidated");
  }
});

test("a missing or unreadable identity is unvalidated (fail safe: it still shows the notice)", () => {
  for (const id of MISSING) {
    assert.equal(labelFor(id), LABELS.unvalidated, String(JSON.stringify(id)));
    assert.equal(labelFor(id).notice, true);
  }
});

test("only the genuine no-solver fixture is illustrative; a value mixing it with real inputs takes the most cautious state", () => {
  for (const id of ILLUSTRATIVE) assert.equal(labelFor(id), LABELS.illustrative);
  assert.equal(LABELS.illustrative.notice, false);
  for (const near of [`${FIXTURE}:v2`, FIXTURE.toUpperCase(), ` ${FIXTURE}`, "fixture-1", "recorded-fixture-solver"]) {
    assert.equal(labelFor(near), LABELS.unvalidated, `${near}: not the bundled fixture`);
  }
  assert.equal(labelForAll([FIXTURE, FIXTURE]), LABELS.illustrative);
  assert.equal(labelForAll([FIXTURE, CORRECTED]), LABELS.unvalidated, "fixture and a real input");
  assert.equal(labelForAll([CORRECTED, FIXTURE]), LABELS.unvalidated);
  assert.equal(labelForAll([FIXTURE, undefined]), LABELS.unvalidated);
  assert.equal(labelForAll([FIXTURE, AFFECTED[0]]), LABELS.withdrawn);
});

test("ACCEPTED is empty, so nothing is accepted yet; an entry is matched exactly and never overrides a withdrawn build", () => {
  assert.deepEqual([...ACCEPTED], []);
  assert.ok(Object.isFrozen(ACCEPTED));
  for (const id of [...AFFECTED, ...OTHER, ...MISSING, FIXTURE]) assert.notEqual(labelFor(id), LABELS.accepted, String(id));
  // The rule over a list with one accepted identity (the pages use the frozen, empty list).
  const rule = labeller({ accepted: [CORRECTED, AFFECTED[0]] });
  assert.equal(rule.labelFor(CORRECTED), LABELS.accepted);
  assert.equal(LABELS.accepted.notice, false);
  assert.equal(rule.labelFor(` ${CORRECTED}`), LABELS.unvalidated, "exact: no trimming");
  assert.equal(rule.labelFor(CORRECTED.replace("grid:32x32", "grid:64x64")), LABELS.unvalidated, "exact: another grid is another identity");
  assert.equal(rule.labelFor(CORRECTED.toLowerCase()), LABELS.unvalidated, "exact: case counts");
  assert.equal(rule.labelFor(AFFECTED[0]), LABELS.withdrawn, "a withdrawn build stays withdrawn even if listed");
  assert.equal(rule.labelForAll([CORRECTED, CORRECTED]), LABELS.accepted);
  assert.equal(rule.labelForAll([CORRECTED, FIXTURE]), LABELS.unvalidated, "accepted and fixture: neither");
  assert.equal(rule.labelForAll([CORRECTED, OTHER[2]]), LABELS.unvalidated);
  assert.equal(rule.labelForAll([CORRECTED, undefined]), LABELS.unvalidated);
  assert.equal(rule.labelForAll([CORRECTED, AFFECTED[1]]), LABELS.withdrawn);
});

test("a derived value: withdrawn if any input is (a difference of two withdrawn values too), else unvalidated if any is or it names none", () => {
  const [w1, w2] = AFFECTED, [u1, u2] = OTHER;
  assert.equal(labelForAll([w1, w2]), LABELS.withdrawn, "two withdrawn values");
  assert.equal(labelForAll([w1, w1]), LABELS.withdrawn, "the same withdrawn evaluator on both sides");
  assert.equal(labelForAll([u1, w1]), LABELS.withdrawn, "a withdrawn value second");
  assert.equal(labelForAll([w1, u1]), LABELS.withdrawn, "a withdrawn value first");
  assert.equal(labelForAll([undefined, w1]), LABELS.withdrawn, "withdrawn wins over a missing identity");
  assert.equal(labelForAll(new Set([u1, w2])), LABELS.withdrawn, "any iterable");
  assert.equal(labelForAll(w1), LABELS.withdrawn, "one identity passed bare is one identity, not its characters");
  assert.equal(labelForAll([u1, u2]), LABELS.unvalidated);
  assert.equal(labelForAll([u1, undefined]), LABELS.unvalidated);
  assert.equal(labelForAll([]), LABELS.unvalidated, "derived from nothing that names an evaluator");
  assert.equal(labelForAll(undefined), LABELS.unvalidated);
});

test("the lists, labels and notice are frozen; the notice is root's wording, and nothing in the module claims a size", () => {
  for (const x of [WITHDRAWN, ILLUSTRATIVE, ACCEPTED, LABELS, ...Object.values(LABELS)]) assert.ok(Object.isFrozen(x));
  assert.throws(() => WITHDRAWN.push("anything"));
  assert.deepEqual(Object.keys(LABELS).sort(), ["accepted", "illustrative", "unvalidated", "withdrawn"]);
  assert.equal(NOTICE, "These simulated temperatures are under review and have been withdrawn from comparison with published layouts. " +
    "We are investigating heat-sink coupling and validating the evaluator against reconstructed research layouts. " +
    "Historical results remain available.");
  for (const text of [NOTICE, ...Object.values(LABELS).flatMap((l) => [l.text, l.short, l.title])]) assert.doesNotMatch(text, /\d\s*×|×\s*\d|\d\.\d+x|%/i, text);
  // The served module, comments included: no multiplier, gap or reversal figures (provenance is the SLAB-049 review).
  const source = readFileSync(join(PUBLIC, "temperature-label.mjs"), "utf8");
  assert.doesNotMatch(source, /\d\s*×|×\s*\d|\d+(\.\d+)?x|\d+\s*-\s*\d+\s*%|\d\s*%|\d+\s*K|revers|flip/i);
  assert.match(source, /SLAB-049/);
  // The tag beside a value must not read as the evidence views' own "withdrawn" node state.
  assert.notEqual(LABELS.withdrawn.short, "withdrawn");
});

// Every identity in the data these pages serve is classified: the affected evaluator's records are withdrawn, the
// synthetic plate is unvalidated and the bundled fixture is illustrative.
function servedIdentities() {
  const found = new Map();   // identity -> first file
  const walk = (value, file) => {
    if (Array.isArray(value)) { for (const v of value) walk(v, file); return; }
    if (value === null || typeof value !== "object") return;
    for (const [k, v] of Object.entries(value)) {
      if ((k === "solver_version" || k === "evaluator_version") && typeof v === "string" && !found.has(v)) found.set(v, file);
      walk(v, file);
    }
  };
  const files = (dir) => readdirSync(join(PUBLIC, dir), { withFileTypes: true, recursive: true })
    .filter((e) => e.isFile()).map((e) => join(e.parentPath ?? e.path, e.name));
  for (const file of [...files("replay"), ...files("tfl08")].filter((f) => f.endsWith(".json"))) walk(JSON.parse(readFileSync(file, "utf8")), file);
  for (const line of readFileSync(join(PUBLIC, "sentilab", "demo-run.jsonl"), "utf8").split("\n").filter(Boolean)) walk(JSON.parse(line), "demo-run.jsonl");
  return found;
}

test("every identity in the served data is classified: affected withdrawn, plate unvalidated, fixture illustrative", () => {
  const found = servedIdentities();
  assert.ok(found.size >= 3, "the walk reaches the replay, the records and the demo");
  const byState = { withdrawn: [], unvalidated: [], illustrative: [] };
  for (const id of found.keys()) byState[labelFor(id).state].push(id);
  assert.ok(byState.withdrawn.length > 0 && byState.withdrawn.every((id) => id.startsWith(`HotSpot-7:${COMMIT7}:`)), byState.withdrawn.join(", "));
  assert.deepEqual(byState.unvalidated, ["synthetic-fvm-plate-v1-grid40"]);
  assert.deepEqual(byState.illustrative, [FIXTURE]);
  assert.ok([...found.keys()].filter((id) => /^hotspot-7:/i.test(id)).every((id) => labelFor(id) === LABELS.withdrawn), "no affected identity escapes");
});

test("view envelopes: a measurement's identity is its semantics; a verify.add's values belong to the node it names", () => {
  const rows = readFileSync(join(PUBLIC, "sentilab", "demo-run.jsonl"), "utf8").split("\n").filter(Boolean).map((line) => JSON.parse(line));
  const ids = evaluatorIds(rows);
  assert.equal(ids.get("meas-b"), FIXTURE);
  assert.equal(ids.get("cand-a"), undefined, "a candidate declares no evaluator");
  const verify = rows.find((env) => env.event.type === "verify.add" && env.values);
  assert.equal(envelopeEvaluator(verify, ids), FIXTURE);
  assert.equal(envelopeEvaluator(rows[0], ids), FIXTURE);
  assert.equal(labelFor(envelopeEvaluator({ event: { type: "support.add", body: { node: "nowhere" } } }, ids)), LABELS.unvalidated, "unknown node: fail safe");
  assert.equal(envelopeEvaluator(null, ids), undefined);
  // The first node.create of an id wins, as in project().
  const twice = evaluatorIds([
    { event: { type: "node.create", body: { id: "m", kind: "measurement", semantics: { evaluator_version: AFFECTED[0] } } } },
    { event: { type: "node.create", body: { id: "m", kind: "measurement", semantics: { evaluator_version: OTHER[0] } } } },
  ]);
  assert.equal(labelFor(twice.get("m")), LABELS.withdrawn);
  // The bundled fixture is all illustrative, so its pages show no notice.
  assert.equal(needsNotice(rows), false);
});

// A measurement as the producer writes it (sentilab_core/conductor.py): semantics name the evaluator, values carry J.
const measurement = (id, evaluator, J = 118.36) => ({
  event: { type: "node.create", body: { id, kind: "measurement", ...(evaluator === undefined ? {} : { semantics: { task_contract: "t", metric_id: "peak-chip-c", evaluator_version: evaluator, coordinate_frame: "lower-left-mm" } }) } },
  values: { J: { value: J, unit: "C" }, W: { value: 27.7, metric_id: "weighted-manhattan-mm" }, scenario_id: "nominal" },
});

test("the notice test for envelopes: any temperature that is withdrawn or unvalidated", () => {
  assert.equal(needsNotice([measurement("m", LIVE_HS7)]), true, "a live affected measurement");
  assert.equal(needsNotice([measurement("m", undefined)]), true, "a measurement that names no evaluator (fail safe)");
  assert.equal(needsNotice([measurement("m", CORRECTED)]), true, "the corrected evaluator is unvalidated too");
  assert.equal(needsNotice([measurement("m", FIXTURE)]), false, "the fixture alone");
  assert.equal(needsNotice([measurement("m", FIXTURE), measurement("n", CORRECTED)]), true);
  const verifyOld = { event: { type: "verify.add", body: { node: "m", tier: "replayed", evidence: ["r"] } }, values: { J: { value: 118.4, unit: "C" } } };
  assert.equal(needsNotice([measurement("m", FIXTURE), verifyOld]), false, "a verify.add's values belong to the fixture it verifies");
  assert.equal(needsNotice([{ event: { type: "node.create", body: { id: "c", kind: "candidate" } }, values: { geometry: [] } }]), false, "no temperature, no notice");
  assert.equal(needsNotice([null, undefined]), false, "rows rejected before parsing carry nothing");
  assert.equal(needsNotice([]), false);
  assert.equal(hasTemperature({ values: { center_temps: { a: 1 } } }), true);
  assert.equal(hasTemperature({ values: { W: { value: 1 } } }), false);
});

test("the run view: every baseline and oracle result names its identity; the replay is all withdrawn", () => {
  const replay = JSON.parse(readFileSync(join(PUBLIC, "replay", "ascend910-seed11-32x32.json"), "utf8"));
  const ids = runTemperatureIds(replay);
  const events = Object.values(replay.result.lane_results).flatMap((lane) => lane.record).filter((e) => e.event === "baseline" || e.event === "oracle_result");
  assert.equal(ids.length, events.length);
  assert.equal(labelForAll(ids), LABELS.withdrawn);
  // A run as GET /api/runs/{id} returns it, live: one lane, a baseline and an oracle result.
  const run = (solver) => ({ id: "r", result: { lane_results: { random: { record: [
    { event: "baseline", payload: { thermal: { maximum_temperature_c: 118.9, solver_version: solver } } },
    { event: "oracle_result", payload: { thermal: { maximum_temperature_c: 118.4, solver_version: solver } } },
    { event: "proposal_rejected", payload: { reason: "no verified improvement" } },
  ] } } } });
  assert.deepEqual(runTemperatureIds(run(LIVE_HS7)), [LIVE_HS7, LIVE_HS7]);
  assert.equal(labelForAll(runTemperatureIds(run(LIVE_HS7))), LABELS.withdrawn);
  assert.equal(labelForAll(runTemperatureIds(run(CORRECTED))), LABELS.unvalidated);
  assert.equal(labelForAll(runTemperatureIds(run(undefined))), LABELS.unvalidated, "a result that names no evaluator (fail safe)");
  assert.equal(labelForAll(runTemperatureIds(run("synthetic-fvm-plate-v1-grid40"))).notice, true, "the plate shows the notice too");
  assert.deepEqual(runTemperatureIds({ status: "running" }), [], "a run with no results yet shows no temperature");
  assert.deepEqual(runTemperatureIds(null), []);
});

test("the verify page: one lane's record document names its identities too (the TFL-08 records)", () => {
  const record = (rel) => JSON.parse(readFileSync(join(PUBLIC, "tfl08", "records", rel), "utf8"));
  const affected = runTemperatureIds(record("ascend910/seed-0/random.json"));
  assert.ok(affected.length > 1);
  assert.equal(labelForAll(affected), LABELS.withdrawn);
  assert.equal(labelForAll(runTemperatureIds(record("plate/seed-0/random.json"))), LABELS.unvalidated, "the plate: another evaluator");
  assert.deepEqual(runTemperatureIds({ events: "not a list" }), []);
  assert.equal(labelForAll(runTemperatureIds({ events: [{ event: "oracle_result", payload: { thermal: { maximum_temperature_c: 90 } } }] })),
    LABELS.unvalidated, "a result that names no evaluator");
  // The leaderboard's batch summary names no evaluator for its temperatures: unvalidated, so its page shows the notice.
  const batch = JSON.parse(readFileSync(join(PUBLIC, "tfl08", "leaderboard.json"), "utf8"));
  assert.deepEqual(runTemperatureIds(batch), []);
  assert.equal(labelForAll([]).notice, true);
});

// ── live: a signed fixture event through the Lab view's own poller (lab-live.mjs, the code lab.js runs) ─────────
const LIVE_RUN = { run_id: "live-fixture-0001", arm: "live", family: "ascend910", seed: 11, ticket_id: "ticket-live-fixture" };
const encoder = new TextEncoder();
function liveRows(evaluator) {
  const CORE = { agent_id: null, life_id: null, lab: "core", grant_id: null };
  const m = measurement("candidate-0:evaluate:measurement", evaluator);
  const entries = [{ event: { event_id: "live-e1", seq: 1, actor_role: "core", ...m.event }, ts: "2026-10-31T15:51:00.000Z", actor: CORE }];
  return ref.makeChain(LIVE_RUN, entries, { "live-e1": m.values }, { key_id: "core", privateKey: testKey("core").privateKey })
    .map((env) => encoder.encode(JSON.stringify(env)));
}
async function pollOnce(rows) {
  const fetchImpl = async (url) => {
    if (url.startsWith("/api/view/runs")) {
      return new Response(JSON.stringify([{ run_id: LIVE_RUN.run_id, arm: "live", family: "ascend910", seed: 11, last_seq: rows.length, status: "running" }]),
        { status: 200, headers: { "content-type": "application/json" } });
    }
    const q = new URL(url, "http://x").searchParams;
    const page = refPaging.servePage(rows, { cursor: Number(q.get("cursor")), limit: Number(q.get("limit")), ...(q.has("cursor_hash") ? { cursor_hash: q.get("cursor_hash") } : {}) });
    return new Response(Buffer.from(page.bodyBytes), { status: page.status, headers: page.headers });
  };
  const options = { runId: LIVE_RUN.run_id, pins: [{ key_id: "core", key_sha256: testKey("core").sha256 }], keys: { core: testKey("core").raw } };
  const L = { runs: null, runsAt: 0, runId: LIVE_RUN.run_id, paging: paging.initialState(LIVE_RUN.run_id), verification: null, connected: null, error: "" };
  await pollLiveOnce(L, { fetchImpl, now: () => Date.UTC(2026, 9, 31, 15, 51, 1), verify: async (x) => { x.verification = (await paging.verifyRows(x.paging, options)).verification; } });
  return L.verification;
}
const liveLabel = (v) => labelFor(envelopeEvaluator(v.ordered[0], evaluatorIds(v.ordered.slice(0, v.prefix))));

test("live: a signed affected event that arrives through the poller is verified, shown, labelled withdrawn, with the notice", async () => {
  const v = await pollOnce(liveRows(LIVE_HS7));
  assert.equal(v.rows.length, 1);
  assert.equal(v.rows[0].status, "verified", "the page shows it: it is in the projectable prefix");
  assert.equal(v.prefix, 1);
  assert.equal(liveLabel(v), LABELS.withdrawn);
  assert.equal(needsNotice(v.ordered), true);
});

test("live: the same event from another evaluator is unvalidated, with the notice; from the fixture, illustrative, without", async () => {
  const corrected = await pollOnce(liveRows(CORRECTED));
  assert.equal(corrected.rows[0].status, "verified");
  assert.equal(liveLabel(corrected), LABELS.unvalidated);
  assert.equal(needsNotice(corrected.ordered), true);
  const nameless = await pollOnce(liveRows(undefined));
  assert.equal(liveLabel(nameless), LABELS.unvalidated, "an event that names no evaluator (fail safe)");
  assert.equal(needsNotice(nameless.ordered), true);
  const fixture = await pollOnce(liveRows(FIXTURE));
  assert.equal(liveLabel(fixture), LABELS.illustrative);
  assert.equal(needsNotice(fixture.ordered), false);
});

test("every page that shows these temperatures takes its notice and labels from this one module", () => {
  const page = (rel) => readFileSync(join(PUBLIC, rel), "utf8");
  const imports = (rel, from) => assert.match(page(rel), new RegExp(`import \\{[^}]*\\bNOTICE\\b[^}]*\\} from "${from.replace(/[.]/g, "\\.")}";`), rel);
  imports("app.js", "./temperature-label.mjs");
  imports("sentilab/lab.js", "../temperature-label.mjs");
  imports("sentilab/package/package.js", "../../temperature-label.mjs");
  imports("leaderboard.js", "./temperature-label.mjs");
  imports("verify.js", "./temperature-label.mjs");
  for (const rel of ["app.js", "sentilab/lab.js", "sentilab/package/package.js", "leaderboard.js", "verify.js"]) {
    assert.doesNotMatch(page(rel), /under review|heat-sink coupling/, `${rel} holds no copy of the notice text`);
  }
  for (const rel of ["index.html", "sentilab/index.html", "sentilab/package/index.html", "leaderboard.html", "verify.html"]) {
    assert.match(page(rel), /<p class="wnotice" id="wnotice" role="note" hidden><\/p>/, `${rel} has the notice slot`);
  }
  // The run, Lab and Package views label each value too: they take labelFor and labelForAll from the same module.
  for (const rel of ["app.js", "sentilab/lab.js", "sentilab/package/package.js"]) {
    assert.match(page(rel), /import \{[^}]*\blabelFor\b[^}]*\blabelForAll\b[^}]*\} from "(\.\.\/)*(\.\/)?temperature-label\.mjs";/, `${rel} labels each value`);
  }
  assert.match(page("index.html"), /<script type="module" src="app\.js"><\/script>/, "app.js loads as a module");
  assert.match(page("leaderboard.html"), /<script type="module" src="leaderboard\.js"><\/script>/, "leaderboard.js loads as a module");
  assert.match(page("verify.html"), /<script type="module" src="verify\.js"><\/script>/);
});
