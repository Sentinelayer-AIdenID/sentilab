// node --test web/test/temperature-label.test.mjs
// The one temperature label rule (web/public/temperature-label.mjs): withdrawn identities and missing ones are
// qualified, any other identity shows only "simulated", and a value derived from several is withdrawn if any is.
// Values that arrive live (the Lab view's /api/view/events poller, the run view's /api/runs/{id}) go through the same
// rule: a signed fixture event is driven through the page's own live poller below.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  WITHDRAWN, ILLUSTRATIVE, LABELS, NOTICE, labelFor, labelForAll, evaluatorIds, envelopeEvaluator, hasTemperature,
  anyWithdrawnTemperature, runTemperatureIds,
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
// Identities the pre-correction evaluator has signed, in each format it has used.
const PRE_CORRECTION = [
  `HotSpot-7:${COMMIT7}:sha256:37b2a3bc8dc52462`,                                   // replay/, tfl08/ records
  `HotSpot-7:${COMMIT7}:sha256:e4358b46794ebc00`,                                   // local proof ledger
  LIVE_HS7,
  `HotSpot-7:${COMMIT7}:binary_sha256:e4358b46794ebc00f07102d13b3ca687507834a1784eba135d26d1d493d334b4` +
    ":config_sha256:c31956e38b05fc0d31609656e6c92f29109ec3dee6b148b3b1c28c23c2dd1b18:grid:32x32",
  `HotSpot-7:${COMMIT7}`,
  `  hotspot-7:${COMMIT7.toUpperCase()}:grid:64x64 `,                               // case and padding change nothing
];
// Identities that are not the pre-correction evaluator: they show only "simulated".
const CORRECTED = "HotSpot-6.0:a7a3286e368867c26381e0a23e36b3e273bdeda9+SLAB-049:grid_dump=all_layers:binary_sha256:00:config_sha256:00:grid:32x32";
const OTHER = [
  CORRECTED,
  `HotSpot-7:${COMMIT7}+SLAB-049:coupling=material_only:binary_sha256:00:config_sha256:00:grid:32x32`,
  "synthetic-fvm-plate-v1-grid40",
  "HotSpot-7:0000000000000000000000000000000000000000:binary_sha256:00",
  "corrected-evaluator-v1",
];
const MISSING = [undefined, null, "", "   ", 42, 0, true, {}, [], ["HotSpot-6.0:x"], { evaluator_version: "HotSpot-6.0:x" }];

test("a withdrawn identity is qualified, in every format the evaluator has signed", () => {
  for (const id of [...WITHDRAWN, ...PRE_CORRECTION]) {
    const label = labelFor(id);
    assert.equal(label, LABELS.withdrawn, id);
    assert.equal(label.withdrawn, true);
    assert.equal(label.text, "simulated · pre-correction (withdrawn)");
    assert.match(label.title, /2\.3×/);
    assert.match(label.title, /Simulated, not silicon\.$/);
  }
});

test("a missing or unreadable identity is qualified (fail safe)", () => {
  for (const id of MISSING) assert.equal(labelFor(id), LABELS.withdrawn, String(JSON.stringify(id)));
});

test("an unknown or new identity shows only \"simulated\"", () => {
  for (const id of OTHER) {
    const label = labelFor(id);
    assert.equal(label, LABELS.simulated, id);
    assert.equal(label.withdrawn, false);
    assert.equal(label.text, "simulated");
    assert.doesNotMatch(`${label.text} ${label.short} ${label.title}`, /withdrawn|pre-correction/i);
  }
});

test("a difference of withdrawn values is withdrawn, and so is any derived value with a withdrawn or missing input", () => {
  const [w1, w2] = PRE_CORRECTION, [s1, s2] = OTHER;
  assert.equal(labelForAll([w1, w2]), LABELS.withdrawn, "two withdrawn values");
  assert.equal(labelForAll([w1, w1]), LABELS.withdrawn, "the same withdrawn evaluator on both sides");
  assert.equal(labelForAll([s1, w1]), LABELS.withdrawn, "a withdrawn value second");
  assert.equal(labelForAll([w1, s1]), LABELS.withdrawn, "a withdrawn value first");
  assert.equal(labelForAll([s1, undefined]), LABELS.withdrawn, "an input with no identity");
  assert.equal(labelForAll(new Set([s1, w2])), LABELS.withdrawn, "any iterable");
  assert.equal(labelForAll([]), LABELS.withdrawn, "derived from nothing that names an evaluator");
  assert.equal(labelForAll(undefined), LABELS.withdrawn);
  assert.equal(labelForAll(w1), LABELS.withdrawn, "one identity passed bare is one identity, not its characters");
  assert.equal(labelForAll([s1, s2]), LABELS.simulated, "only other identities: simulated");
  assert.equal(labelForAll(s1), LABELS.simulated);
});

test("the bundled fixture is illustrative, never simulated; withdrawn still wins over it", () => {
  for (const id of ILLUSTRATIVE) assert.equal(labelFor(id), LABELS.illustrative);
  assert.equal(labelForAll(["fixture-no-solver", "fixture-no-solver"]), LABELS.illustrative);
  assert.equal(labelForAll(["fixture-no-solver", OTHER[0]]), LABELS.illustrative);
  assert.equal(labelForAll(["fixture-no-solver", PRE_CORRECTION[0]]), LABELS.withdrawn);
});

test("the lists, labels and notice are frozen, and the notice is one constant", () => {
  for (const x of [WITHDRAWN, ILLUSTRATIVE, LABELS, LABELS.withdrawn, LABELS.simulated, LABELS.illustrative]) assert.ok(Object.isFrozen(x));
  assert.throws(() => WITHDRAWN.push("anything"));
  assert.equal(NOTICE, "Temperatures on this page come from an evaluator under correction: a known heat-sink coupling defect " +
    "overstates temperature rises (about 2.3×) and distorts the gaps between layouts. They're being re-validated against " +
    "published human layouts, so don't compare them with papers. Simulated, not silicon.");
  // The tag beside a value must not read as the evidence views' own "withdrawn" node state.
  assert.notEqual(LABELS.withdrawn.short, "withdrawn");
});

// Every identity in the data these pages serve is classified as expected: the pre-correction evaluator's records are
// withdrawn, the synthetic plate is simulated and the bundled fixture is illustrative. A new identity in the served data
// fails this test until someone decides which it is.
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

test("every identity in the served data is classified: pre-correction withdrawn, plate simulated, fixture illustrative", () => {
  const found = servedIdentities();
  assert.ok(found.size >= 3, "the walk reaches the replay, the records and the demo");
  const byState = { withdrawn: [], simulated: [], illustrative: [] };
  for (const id of found.keys()) byState[labelFor(id).state].push(id);
  assert.ok(byState.withdrawn.length > 0 && byState.withdrawn.every((id) => id.startsWith(`HotSpot-7:${COMMIT7}:`)), byState.withdrawn.join(", "));
  assert.deepEqual(byState.simulated, ["synthetic-fvm-plate-v1-grid40"]);
  assert.deepEqual(byState.illustrative, ["fixture-no-solver"]);
  assert.ok([...found.keys()].filter((id) => /^hotspot-7:/i.test(id)).every((id) => labelFor(id).withdrawn), "no pre-correction identity escapes");
});

test("view envelopes: a measurement's identity is its semantics; a verify.add's values belong to the node it names", () => {
  const rows = readFileSync(join(PUBLIC, "sentilab", "demo-run.jsonl"), "utf8").split("\n").filter(Boolean).map((line) => JSON.parse(line));
  const ids = evaluatorIds(rows);
  assert.equal(ids.get("meas-b"), "fixture-no-solver");
  assert.equal(ids.get("cand-a"), undefined, "a candidate declares no evaluator");
  const verify = rows.find((env) => env.event.type === "verify.add" && env.values);
  assert.equal(envelopeEvaluator(verify, ids), "fixture-no-solver");
  assert.equal(envelopeEvaluator(rows[0], ids), "fixture-no-solver");
  assert.equal(labelFor(envelopeEvaluator({ event: { type: "support.add", body: { node: "nowhere" } } }, ids)), LABELS.withdrawn, "unknown node: fail safe");
  assert.equal(envelopeEvaluator(null, ids), undefined);
  // The first node.create of an id wins, as in project().
  const twice = evaluatorIds([
    { event: { type: "node.create", body: { id: "m", kind: "measurement", semantics: { evaluator_version: PRE_CORRECTION[0] } } } },
    { event: { type: "node.create", body: { id: "m", kind: "measurement", semantics: { evaluator_version: OTHER[0] } } } },
  ]);
  assert.equal(labelFor(twice.get("m")), LABELS.withdrawn);
  // The bundled fixture shows no withdrawn temperature, so its pages show no notice.
  assert.equal(anyWithdrawnTemperature(rows), false);
});

// A measurement as the producer writes it (sentilab_core/conductor.py): semantics name the evaluator, values carry J.
const measurement = (id, evaluator, J = 118.36) => ({
  event: { type: "node.create", body: { id, kind: "measurement", ...(evaluator === undefined ? {} : { semantics: { task_contract: "t", metric_id: "peak-chip-c", evaluator_version: evaluator, coordinate_frame: "lower-left-mm" } }) } },
  values: { J: { value: J, unit: "C" }, W: { value: 27.7, metric_id: "weighted-manhattan-mm" }, scenario_id: "nominal" },
});

test("the notice test for envelopes: any temperature labelled withdrawn, including ones with no identity", () => {
  assert.equal(anyWithdrawnTemperature([measurement("m", LIVE_HS7)]), true, "a live pre-correction measurement");
  assert.equal(anyWithdrawnTemperature([measurement("m", undefined)]), true, "a measurement that names no evaluator (fail safe)");
  assert.equal(anyWithdrawnTemperature([measurement("m", CORRECTED)]), false, "the corrected evaluator");
  assert.equal(anyWithdrawnTemperature([measurement("m", CORRECTED), measurement("n", LIVE_HS7)]), true, "one withdrawn among corrected ones");
  const verifyOld = { event: { type: "verify.add", body: { node: "m", tier: "replayed", evidence: ["r"] } }, values: { J: { value: 118.4, unit: "C" } } };
  assert.equal(anyWithdrawnTemperature([measurement("m", LIVE_HS7), verifyOld]), true);
  assert.equal(anyWithdrawnTemperature([{ event: { type: "node.create", body: { id: "c", kind: "candidate" } }, values: { geometry: [] } }]), false, "no temperature, no notice");
  assert.equal(anyWithdrawnTemperature([null, undefined]), false, "rows rejected before parsing carry nothing");
  assert.equal(anyWithdrawnTemperature([]), false);
  assert.equal(hasTemperature({ values: { center_temps: { a: 1 } } }), true);
  assert.equal(hasTemperature({ values: { W: { value: 1 } } }), false);
});

test("the run view: every baseline and oracle result names its identity; the replay is all pre-correction", () => {
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
  assert.equal(labelForAll(runTemperatureIds(run(CORRECTED))), LABELS.simulated);
  assert.equal(labelForAll(runTemperatureIds(run(undefined))), LABELS.withdrawn, "a result that names no evaluator (fail safe)");
  assert.deepEqual(runTemperatureIds({ status: "running" }), [], "a run with no results yet shows no temperature");
  assert.deepEqual(runTemperatureIds(null), []);
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

test("live: a signed pre-correction event that arrives through the poller is verified, shown, and labelled withdrawn", async () => {
  const v = await pollOnce(liveRows(LIVE_HS7));
  assert.equal(v.rows.length, 1);
  assert.equal(v.rows[0].status, "verified", "the page shows it: it is in the projectable prefix");
  assert.equal(v.prefix, 1);
  const ids = evaluatorIds(v.ordered.slice(0, v.prefix));
  assert.equal(labelFor(envelopeEvaluator(v.ordered[0], ids)), LABELS.withdrawn, "its J is labelled withdrawn");
  assert.equal(anyWithdrawnTemperature(v.ordered), true, "the page shows the notice");
});

test("live: the same event from the corrected evaluator shows only \"simulated\", and no notice", async () => {
  const v = await pollOnce(liveRows(CORRECTED));
  assert.equal(v.rows[0].status, "verified");
  assert.equal(labelFor(envelopeEvaluator(v.ordered[0], evaluatorIds(v.ordered))), LABELS.simulated);
  assert.equal(anyWithdrawnTemperature(v.ordered), false);
});

test("all three pages take their notice and labels from this one module", () => {
  const page = (rel) => readFileSync(join(PUBLIC, rel), "utf8");
  const imports = (rel, from) => assert.match(page(rel), new RegExp(`import \\{[^}]*\\bNOTICE\\b[^}]*\\} from "${from.replace(/[.]/g, "\\.")}";`), rel);
  imports("app.js", "./temperature-label.mjs");
  imports("sentilab/lab.js", "../temperature-label.mjs");
  imports("sentilab/package/package.js", "../../temperature-label.mjs");
  for (const rel of ["app.js", "sentilab/lab.js", "sentilab/package/package.js"]) {
    assert.doesNotMatch(page(rel), /under correction|overstates temperature/, `${rel} holds no copy of the notice text`);
  }
  for (const rel of ["index.html", "sentilab/index.html", "sentilab/package/index.html"]) {
    assert.match(page(rel), /<p class="wnotice" id="wnotice" role="note" hidden><\/p>/, `${rel} has the notice slot`);
  }
  assert.match(page("index.html"), /<script type="module" src="app\.js"><\/script>/, "app.js loads as a module");
});
