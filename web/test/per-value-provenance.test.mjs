// node --test web/test/per-value-provenance.test.mjs
// Per-value labels in the Lab and Package views take their identity from the event the projector APPLIED, and the live
// colour scale's identities stay a bounded set. Driven with the real projector (evidence-projection.mjs), the Lab model
// (lab-model.mjs buildView) and the Package scene (scene.mjs), from a stubbed verified prefix and from a chain signed
// with the TEST key through the real verifier (paging.mjs).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { LABELS, labelFor, labelForAll, evaluatorIds, scaleIdentities, sourceTags } from "../public/temperature-label.mjs";
import { project } from "../public/sentilab/evidence-projection.mjs";
import { buildView } from "../public/sentilab/lab-model.mjs";
import { buildScene } from "../public/sentilab/package/scene.mjs";
import * as paging from "../public/sentilab/paging.mjs";
import * as ref from "../../contracts/view-envelope-v0.5/view-envelope.mjs";
import { testKey } from "./sentilab-keys.mjs";

const PUBLIC = join(dirname(fileURLToPath(import.meta.url)), "..", "public");
const HS7 = "HotSpot-7:f18831e48cef5d62580585cca0d7fab6c71bc3cc:binary_sha256:9f971da7370a59afb425ed1c8754e12bc67a6a95e8333c3b4a9d537fd30a77f6:config_sha256:548562a5f49d502f4b9bd03d3a4acc4b42f225056e6d91556416079c291e06d4:grid:16x16";
const CORRECTED = "HotSpot-6.0:a7a3286e368867c26381e0a23e36b3e273bdeda9+SLAB-049:grid_dump=all_layers:binary_sha256:00:config_sha256:00:grid:32x32";
const FIXTURE = "fixture-no-solver";
const RUN = { run_id: "provenance-0001", arm: "live", family: "ascend910", seed: 11, ticket_id: "ticket-provenance" };
const CORE = { agent_id: null, life_id: null, lab: "core", grant_id: null };
const LAB = { agent_id: "agent-lab-a-01", life_id: "life-lab-a-0001", lab: "lab-a", grant_id: "grant-lab-a-0001" };
const semantics = (evaluator) => ({ task_contract: "t", metric_id: "peak-chip-c", evaluator_version: evaluator, coordinate_frame: "lower-left-mm" });
const geometry = [{ id: "CPU0", xLL: 2, yLL: 2, w: 10, h: 8, layer: 0 }, { id: "HBM0", xLL: 16, yLL: 2, w: 7, h: 9, layer: 0 }];

// Astra's witness: a schema-valid create of meas-a that names the fixture but lacks the other semantics fields, which
// the projector REJECTS (missing_semantics); then the applied create of the same meas-a from the withdrawn build, J 52.
const STEPS = [
  { actor: LAB, role: "lab", type: "node.create", body: { id: "cand-a", kind: "candidate" }, values: { geometry, units: "mm", scenario_id: "nominal" } },
  { actor: CORE, role: "core", type: "node.create", body: { id: "meas-a", kind: "measurement", semantics: { evaluator_version: FIXTURE } }, values: { J: { value: 40, unit: "C" }, scenario_id: "nominal" } },
  { actor: CORE, role: "core", type: "node.create", body: { id: "meas-a", kind: "measurement", semantics: semantics(HS7) }, values: { J: { value: 52, unit: "C" }, center_temps: { CPU0: 52, HBM0: 41 }, scenario_id: "nominal" } },
  { actor: CORE, role: "core", type: "support.add", body: { node: "cand-a", set_id: "eval", members: ["meas-a"] } },
];
const entries = STEPS.map((s, i) => ({ event: { event_id: `p${i + 1}`, seq: i + 1, type: s.type, actor_role: s.role, body: s.body }, ts: new Date(Date.UTC(2026, 9, 31, 18, 0, i)).toISOString(), actor: s.actor }));
const values = Object.fromEntries(STEPS.map((s, i) => [`p${i + 1}`, s.values]).filter(([, v]) => v));
// The stubbed verified prefix: the envelopes as the verifier hands them on (hash and signature already checked).
const stubbed = entries.map((e) => ({ v: "view-envelope/0.5", ...e, run: RUN, ...(values[e.event.event_id] ? { values: values[e.event.event_id] } : {}) }));

// What the Lab view labels J with (lab.js jLabel: the identity of the measurement metricFor() picked) and what the
// Package view labels J with (package.js jLabelOf: the same, from the scene's layout).
function labDisplay(verification) {
  const view = buildView(verification, verification.ordered.length);
  const trusted = verification.ordered.slice(0, verification.prefix);
  const ids = evaluatorIds(trusted, verification.projection?.rejected ?? project(trusted.map((env) => env.event)).rejected);
  const card = view.cards.find((c) => c.id === "cand-a");
  return { J: card.J, label: labelFor(ids.get(card.metric?.id)), ids };
}
function packageDisplay(prefixEnvelopes, projection) {
  const scene = buildScene(prefixEnvelopes, projection);
  const L = scene.tracks.find((t) => t.track === "lab-a").layout;
  const ids = evaluatorIds(prefixEnvelopes, projection.rejected);
  return { J: L.J, label: labelFor(ids.get(L.metric?.measurement ?? (L.ref.kind === "measurement" ? L.ref.id : undefined))), temps: labelFor(ids.get(L.temps_from?.measurement)) };
}

test("the projector rejects the fixture create and applies the withdrawn one: the witness is what astra built", () => {
  const projection = project(stubbed.map((env) => env.event));
  assert.deepEqual(projection.rejected, [{ event_id: "p2", code: "missing_semantics" }]);
  assert.equal(projection.nodes["meas-a"].kind, "measurement");
  assert.deepEqual(evaluatorIds(stubbed).get("meas-a"), FIXTURE, "the first RAW create names the fixture: the trap");
});

test("regression (Lab view): J 52 from the applied withdrawn create is labelled withdrawn, not illustrative", () => {
  const { J, label, ids } = labDisplay({ ordered: stubbed, rows: stubbed.map(() => ({ status: "verified", reasons: [] })), prefix: stubbed.length });
  assert.equal(J.value, 52, "the number is the applied create's");
  assert.equal(ids.get("meas-a"), HS7);
  assert.equal(label, LABELS.withdrawn);
});

test("regression (Package view): J 52 and the centre temperatures from the applied withdrawn create are labelled withdrawn", () => {
  const { J, label, temps } = packageDisplay(stubbed, project(stubbed.map((env) => env.event)));
  assert.equal(J.value, 52);
  assert.equal(label, LABELS.withdrawn);
  assert.equal(temps, LABELS.withdrawn);
});

test("regression (real verifier): the same sequence signed with the TEST key, verified, projected and labelled", async () => {
  const rows = ref.makeChain(RUN, entries, values, { key_id: "core", privateKey: testKey("core").privateKey }, { appendChecks: false })
    .map((env) => new TextEncoder().encode(JSON.stringify(env)));
  const v = await paging.verifyBytes(rows, { runId: RUN.run_id, pins: [{ key_id: "core", key_sha256: testKey("core").sha256 }], keys: { core: testKey("core").raw } });
  assert.equal(v.prefix, 4, "all four envelopes verify and form the projectable prefix");
  assert.deepEqual(v.projection.rejected.map((r) => r.event_id), ["p2"]);
  const lab = labDisplay(v);
  assert.equal(lab.J.value, 52);
  assert.equal(lab.label, LABELS.withdrawn);
  const pkg = packageDisplay(v.ordered.slice(0, v.prefix), v.projection);
  assert.equal(pkg.label, LABELS.withdrawn);
});

test("a rejected create lends no identity; with nothing rejected the first create still wins", () => {
  const ids = evaluatorIds(stubbed, [{ event_id: "p2", code: "missing_semantics" }]);
  assert.equal(ids.get("meas-a"), HS7);
  assert.equal(evaluatorIds(stubbed, ["p2"]).get("meas-a"), HS7, "event ids work too");
  assert.equal(evaluatorIds(stubbed, []).get("meas-a"), FIXTURE);
  assert.equal(evaluatorIds(stubbed, ["p2", "p3"]).has("meas-a"), false, "every create rejected: no identity, so unvalidated");
  assert.equal(labelFor(evaluatorIds(stubbed, ["p2", "p3"]).get("meas-a")), LABELS.unvalidated);
});

// ── the opposite order, the Package-only witness, and distinct sources ──────────────────────────────────────
// A chain from steps: [actor, role, type, body, values?] in seq order (stubbed verified prefix).
function chain(steps) {
  return steps.map(([actor, role, type, body, vals], i) => ({ v: "view-envelope/0.5", run: RUN, ts: new Date(Date.UTC(2026, 9, 31, 18, 30, i)).toISOString(), actor,
    event: { event_id: `q${i + 1}`, seq: i + 1, type, actor_role: role, body }, ...(vals ? { values: vals } : {}) }));
}
const verifiedOf = (envs) => ({ ordered: envs, rows: envs.map(() => ({ status: "verified", reasons: [] })), prefix: envs.length, projection: project(envs.map((e) => e.event)) });
const candidate = [LAB, "lab", "node.create", { id: "cand-a", kind: "candidate" }, { geometry, units: "mm" }];
const measure = (evaluator, J, extra = {}) => [CORE, "core", "node.create", { id: "meas-a", kind: "measurement", semantics: semantics(evaluator) }, { J: { value: J, unit: "C" }, center_temps: { CPU0: J, HBM0: J - 11 }, ...extra }];
const supportA = [CORE, "core", "support.add", { node: "cand-a", set_id: "eval", members: ["meas-a"] }];

for (const [first, second, expected] of [[HS7, FIXTURE, LABELS.withdrawn], [FIXTURE, HS7, LABELS.illustrative]]) {
  test(`opposite order: an applied create (${expected.state}) keeps its identity when a REJECTED duplicate follows`, () => {
    const envs = chain([candidate, measure(first, 52), measure(second, 61), supportA]);
    const v = verifiedOf(envs);
    assert.deepEqual(v.projection.rejected, [{ event_id: "q3", code: "duplicate_node" }], "the second create is the rejected duplicate");
    const lab = labDisplay(v);
    assert.equal(lab.J.value, 52, "the number is the applied create's");
    assert.equal(lab.label, expected, "the rejected duplicate never overrides the applied identity");
    const pkg = packageDisplay(envs, v.projection);
    assert.equal(pkg.J.value, 52);
    assert.equal(pkg.label, expected);
    assert.equal(pkg.temps, expected);
  });
}

test("astra's Package witness: the applied measurement carries one rectangle, so the board shows it; its J is labelled withdrawn", () => {
  const rect = { geometry: [{ id: "CPU0", xLL: 2, yLL: 2, w: 10, h: 8, layer: 0 }], units: "mm" };
  const envs = chain([
    [CORE, "core", "node.create", { id: "meas-a", kind: "measurement", semantics: { evaluator_version: FIXTURE } }, { J: { value: 40, unit: "C" }, ...rect }],
    [CORE, "core", "node.create", { id: "meas-a", kind: "measurement", semantics: semantics(HS7) }, { J: { value: 52, unit: "C" }, ...rect }],
  ]);
  const projection = project(envs.map((e) => e.event));
  assert.deepEqual(projection.rejected.map((r) => r.code), ["missing_semantics"]);
  const board = buildScene(envs, projection).tracks.find((t) => t.track === "board");
  assert.equal(board.showing, "initial");
  const L = board.layout;
  assert.equal(L.J.value, 52);
  const ids = evaluatorIds(envs, projection.rejected);
  assert.equal(labelFor(ids.get(L.metric?.measurement ?? (L.ref.kind === "measurement" ? L.ref.id : undefined))), LABELS.withdrawn);
});

// J from one measurement, the centre temperatures from another: metricFor() ranks a reproduced measurement first (here
// one from the corrected evaluator, J only), while measurementFor() takes the first one with temperatures in the first
// valid set (here the withdrawn build's). Each must keep its own label.
test("distinct sources stay distinct: J (unvalidated) and the centre temperatures (withdrawn) each carry their own label", () => {
  const envs = chain([
    candidate,
    [CORE, "core", "node.create", { id: "meas-t", kind: "measurement", semantics: semantics(HS7) }, { J: { value: 58, unit: "C" }, center_temps: { CPU0: 58, HBM0: 47 } }],
    [CORE, "core", "node.create", { id: "meas-j", kind: "measurement", semantics: semantics(CORRECTED) }, { J: { value: 33, unit: "C" } }],
    [CORE, "core", "support.add", { node: "cand-a", set_id: "eval", members: ["meas-t"] }],
    [CORE, "core", "support.add", { node: "cand-a", set_id: "repro", members: ["meas-j"] }],
    [CORE, "core", "verify.add", { node: "meas-j", tier: "replayed", evidence: ["meas-t"] }],
  ]);
  const v = verifiedOf(envs);
  assert.deepEqual(v.projection.rejected, []);
  const ids = evaluatorIds(envs, v.projection.rejected);
  const card = buildView(v, envs.length).cards.find((c) => c.id === "cand-a");
  assert.equal(card.metric.id, "meas-j", "J comes from the reproduced measurement");
  assert.equal(card.source.id, "meas-t", "the centre temperatures come from the other one");
  const jl = labelFor(ids.get(card.metric.id)), tl = labelFor(ids.get(card.source.id));
  assert.equal(jl, LABELS.unvalidated);
  assert.equal(tl, LABELS.withdrawn);
  assert.deepEqual(sourceTags(jl, tl).map((t) => [t.label.state, t.text]), [["unvalidated", "unvalidated"], ["withdrawn", "temps pre-correction"]], "two tags, never one merged");
  const L = buildScene(envs, v.projection).tracks.find((t) => t.track === "lab-a").layout;
  assert.equal(L.metric.measurement, "meas-j");
  assert.equal(L.temps_from.measurement, "meas-t");
  assert.equal(labelFor(ids.get(L.metric.measurement)), LABELS.unvalidated, "the Package view's J");
  assert.equal(labelFor(ids.get(L.temps_from.measurement)), LABELS.withdrawn, "the Package view's chiplet numbers");
});

test("sourceTags: one tag when both sources share a label; the temperatures' alone when there is no J; none when neither", () => {
  assert.deepEqual(sourceTags(LABELS.withdrawn, LABELS.withdrawn).map((t) => t.text), ["pre-correction"]);
  assert.deepEqual(sourceTags(null, LABELS.withdrawn).map((t) => t.text), ["temps pre-correction"]);
  assert.deepEqual(sourceTags(LABELS.unvalidated, null).map((t) => t.text), ["unvalidated"]);
  assert.deepEqual(sourceTags(null, null), []);
});

// ── the live colour scale's identities ───────────────────────────────────────────────────────────────────────
const measurementRow = (i, evaluator) => ({ event: { event_id: `m${i}`, seq: i, type: "node.create", body: { id: `meas-${i}`, kind: "measurement", semantics: semantics(evaluator) } },
  values: { J: { value: 50 + (i % 7), unit: "C" }, center_temps: { CPU0: 50 + (i % 7) } } });

// lab.js: on every verification, src.scaleIds = scaleIdentities(trusted, ids, widened ? src.scaleIds : null).
function liveArrivals(rows) {
  let set = null;
  for (let k = 1; k <= rows.length; k += 1) {
    const trusted = rows.slice(0, k);
    set = scaleIdentities(trusted, evaluatorIds(trusted), k > 1 ? set : null);   // each arrival widens the live scale
  }
  return set;
}

test("regression: 128 one-row arrivals of one evaluator keep ONE identity, not 8,256 entries", () => {
  const rows = Array.from({ length: 128 }, (_, i) => measurementRow(i + 1, HS7));
  const set = liveArrivals(rows);
  assert.ok(set instanceof Set);
  assert.equal(set.size, 1, "one distinct identity in scope");
  assert.equal(labelForAll(set), LABELS.withdrawn);
  // A rejected suffix re-verifies the same trusted prefix of 128 (widened, K unchanged): still one.
  const again = scaleIdentities(rows, evaluatorIds(rows), set);
  assert.equal(again.size, 1);
});

test("the scale's set is the distinct identities in scope: two evaluators give two; a shrink rebuilds", () => {
  const rows = Array.from({ length: 128 }, (_, i) => measurementRow(i + 1, i % 2 ? HS7 : CORRECTED));
  const set = liveArrivals(rows);
  assert.equal(set.size, 2);
  assert.equal(labelForAll(set), LABELS.withdrawn);
  // The prefix shrank (a late conflict cut it back to the first row): rebuilt from what remains.
  const shrunk = scaleIdentities(rows.slice(0, 1), evaluatorIds(rows.slice(0, 1)), null);
  assert.deepEqual([...shrunk], [CORRECTED]);
  assert.equal(labelForAll(shrunk), LABELS.unvalidated);
});

test("a widened scale keeps the identities it was widened from; a rebuilt one does not", () => {
  const earlier = scaleIdentities([measurementRow(1, HS7)], new Map(), null);
  const fixtureRows = [measurementRow(1, FIXTURE), measurementRow(2, FIXTURE)];
  assert.equal(labelForAll(scaleIdentities(fixtureRows, new Map(), earlier)), LABELS.withdrawn, "widened: the withdrawn value still shapes the scale");
  assert.equal(labelForAll(scaleIdentities(fixtureRows, new Map(), null)), LABELS.illustrative, "rebuilt: only what is in scope");
  assert.equal(scaleIdentities([], new Map(), null).size, 0);
  assert.equal(labelForAll(scaleIdentities([], new Map(), null)), LABELS.unvalidated, "no inputs: the rule's fail safe");
});

test("both views take per-value identities from the applied creates and keep the scale's identities as a set", () => {
  const read = (rel) => readFileSync(join(PUBLIC, rel), "utf8");
  assert.match(read("sentilab/lab.js"), /src\.ids = evaluatorIds\(trusted, src\.verification\.projection\?\.rejected\);/);
  assert.match(read("sentilab/lab.js"), /src\.scaleIds = scaleIdentities\(trusted, src\.ids, widened \? src\.scaleIds : null\);/);
  assert.match(read("sentilab/package/package.js"), /src\.ids = evaluatorIds\(verification\.prefixEnvelopes, verification\.projection\?\.rejected\);/);
  assert.match(read("sentilab/package/package.js"), /src\.scaleIds = scaleIdentities\(verification\.prefixEnvelopes, src\.ids\);/);
  // The Lab card shows J's and the centre temperatures' qualifiers from their own sources (sourceTags), never merged.
  assert.match(read("sentilab/lab.js"), /const tags = sourceTags\(jl, tl\);/);
  assert.match(read("sentilab/lab.js"), /tags\.map\(\(t\) => tq\(t\.label, t\.text\)\)/);
});
