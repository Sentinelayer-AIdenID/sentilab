// node --test web/test/sentilab-parity.test.mjs
// The Lab view's browser modules (web/public/sentilab/) must give exactly the contract's answers:
//   - evidence-projection.mjs is aneta's file byte for byte, and project() matches her vectors;
//   - canonical.mjs gives the same strings as resultcheck.mjs's canonical();
//   - view-core.mjs (the WebCrypto port) gives the same verifyChain() result as the reference on every view vector,
//     plus the same mode, caps and hashing answers;
//   - the production pin list is empty, so nothing verifies without a pin, and the demo verifies only under TEST keys.
// The originals are the repo's executable contracts in contracts/ (hashes checked below and in contracts/HASHES.txt).
import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { project as refProject } from "../../contracts/contract-0.2/evidence-projection.mjs";
import { canonical as refCanonical } from "../../contracts/contract-0.2/resultcheck.mjs";
import * as ref from "../../contracts/view-envelope/view-envelope.mjs";
import { project } from "../public/sentilab/evidence-projection.mjs";
import { canonical } from "../public/sentilab/canonical.mjs";
import * as core from "../public/sentilab/view-core.mjs";
import { VIEW_PINS } from "../public/sentilab/view-pins.js";
import { buildView, feedRows, chainSummary, isDrill } from "../public/sentilab/lab-model.mjs";
import { testKey } from "./sentilab-keys.mjs";
import { buildDemo, DEMO_PATH, DEMO_RUN } from "./make-sentilab-demo.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const read = (...p) => readFileSync(join(here, ...p));
const contract = (...p) => readFileSync(join(here, "..", "..", "contracts", ...p));
const sha = (buf) => createHash("sha256").update(buf).digest("hex");
const same = (a, b) => refCanonical(a) === refCanonical(b);
const evidenceVectors = JSON.parse(contract("contract-0.2", "vectors-evidence.json")).vectors;
const viewFile = JSON.parse(contract("view-envelope", "vectors-view.json"));

// ── the contracts are what their hashes say they are ────────────────────────────────────────────────────────
const PINNED = {
  "contract-0.2/evidence-projection.mjs": "fe861207ed1bfbf90e457f84606dbbd335cb762d2041c9ee942aa006d3f31001",
  "contract-0.2/resultcheck.mjs": "4fb7a64ea3e22379e3731494225e7be29062990284724ef08a5dc0a4ea582049",
  "contract-0.2/vectors-evidence.json": "5c20a91a0890b9a66774e93b5792b9a717ec085314adf879b458ad9006f2510c",
  "view-envelope/view-envelope.mjs": "ee37a2f47e269f1d17f66a995cb9f5ae3137735b773c8300927e30b3d0626ed5",
  "view-envelope/vectors-view.json": "675c588bbfe9a487950522a9dd4432511d3d06040441c3d50fd71acdabe0a314",
};
test("the contract files are the hashed originals", () => {
  for (const [path, want] of Object.entries(PINNED)) assert.equal(sha(contract(...path.split("/"))), want, path);
  assert.equal(viewFile.contract_sha256, "6a1eb6421f726f1b67f0bcace9dd32322bd472babb30a89c68a69be4e0df4d56", "vectors are for VIEW ENVELOPE v0.4");
});
test("the browser projection is aneta's evidence-projection.mjs byte for byte", () => {
  assert.equal(sha(read("..", "public", "sentilab", "evidence-projection.mjs")), PINNED["contract-0.2/evidence-projection.mjs"]);
});

// ── canonical() ───────────────────────────────────────────────────────────────────────────────────────────────
test("browser canonical() equals resultcheck.mjs canonical() on every vector input and on edge values", () => {
  const inputs = [
    ...evidenceVectors.flatMap((v) => v.events),
    ...viewFile.chains.flatMap((c) => c.envelopes),
    ...viewFile.caps.filter((c) => c.envelope).map((c) => c.envelope),
    ...viewFile.hashing.map((h) => h.envelope),
    ...viewFile.canonical.map((c) => JSON.parse(c.raw)),
    { a: undefined, b: [undefined, null, NaN, Infinity, -0, 1e21, 1e-7, 5.0], c: " \ud800\u0000é😀" },
    JSON.parse('{"__proto__":{"x":1},"constructor":2,"\\uff21":1,"\\ud83d\\ude00":2}'),
    [[[]], {}, "", 0, false, true, null],
  ];
  let checked = 0;
  for (const value of inputs) { assert.equal(canonical(value), refCanonical(value)); checked += 1; }
  assert.ok(checked > 300, `checked ${checked} inputs`);
});
test("browser canonical() gives the vectors' canonical strings (JCS cases)", () => {
  for (const c of viewFile.canonical) assert.equal(canonical(JSON.parse(c.raw)), c.canonical, c.name);
});

// ── project() ─────────────────────────────────────────────────────────────────────────────────────────────────
// Same harness as aneta's run-vectors.mjs: ids and seqs by position unless the vector gives them.
const withIds = (events) => events.map((event, index) => ({ event_id: `e${index}`, seq: index + 1, ...event }));
function subset(actual, expected, path = "") {
  if (expected === null || typeof expected !== "object") {
    if (typeof expected === "number" && typeof actual === "number") return Math.abs(actual - expected) <= 1e-6 ? [] : [`${path}`];
    return actual === expected ? [] : [`${path}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`];
  }
  if (Array.isArray(expected)) return same(actual, expected) ? [] : [`${path}: expected ${refCanonical(expected)}, got ${refCanonical(actual)}`];
  if (actual === null || typeof actual !== "object") return [`${path}: expected an object`];
  if (Object.keys(expected).length === 0 && Object.keys(actual).length > 0) return [`${path}: expected empty`];
  return Object.keys(expected).flatMap((key) => subset(actual[key], expected[key], `${path}.${key}`));
}
test(`browser project() equals the original and meets all ${evidenceVectors.length} evidence vectors`, () => {
  for (const vector of evidenceVectors) {
    const events = withIds(vector.events);
    const mine = project(events);
    assert.equal(canonical(mine), canonical(refProject(events)), vector.name);
    assert.equal(canonical(project([...events].reverse())), canonical(mine), `${vector.name}: delivery order`);
    const errors = [];
    for (const [id, expected] of Object.entries(vector.expect.nodes ?? {})) errors.push(...subset(mine.nodes[id], expected, `nodes.${id}`));
    errors.push(...subset(mine.rejected, vector.expect.rejected ?? [], "rejected"));
    for (const id of vector.expect.absent_nodes ?? []) if (mine.nodes[id]) errors.push(`${id} should not exist`);
    assert.deepEqual(errors, [], vector.name);
  }
});

// ── verifyChain(): the browser port against the reference and the recorded results ──────────────────────────
const nodePins = (view) => view.pins.map((p) => ({ key_id: p.key_id, key_sha256: testKey(p.test_key).sha256 }));
const nodeKeys = (view) => Object.fromEntries(Object.entries(view.served_keys).map(([id, name]) => [id, testKey(name).publicKey]));
const rawKeys = (view) => Object.fromEntries(Object.entries(view.served_keys).map(([id, name]) => [id, testKey(name).raw]));
// The reference's result fields; the port adds `ordered` and `prefix` for the page.
const refFields = ({ rows, chain_ok, prefix_end, frozen, label, projection, projection_error }) => ({ rows, chain_ok, prefix_end, frozen, label, projection, projection_error });
const browserVerify = (envelopes, view, pins = nodePins(view)) => core.verifyChain(structuredClone(envelopes), { runId: view.run_id, pins, keys: rawKeys(view) });

for (const chain of viewFile.chains) {
  const label = chain.name.split(":")[0];
  test(`${label}: the browser verifyChain() equals the recorded result and the reference`, async () => {
    const mine = await browserVerify(chain.envelopes, chain.view);
    assert.ok(same(refFields(mine), chain.result), "differs from the vector file's recorded result");
    const theirs = ref.verifyChain(structuredClone(chain.envelopes), { runId: chain.view.run_id, pins: nodePins(chain.view), keys: nodeKeys(chain.view) });
    assert.ok(same(refFields(mine), theirs), "differs from the reference");
    // The hand-written expectations, as the reference runner checks them.
    const e = chain.expect;
    assert.equal(mine.rows.length, e.rows);
    assert.equal(mine.chain_ok, e.chain_ok);
    for (const key of ["prefix_end", "frozen", "label"]) assert.equal(mine[key], e[key], key);
    let inPrefix = true;
    for (const row of mine.rows) {
      inPrefix = inPrefix && !Object.hasOwn(e.unverified, row.event_id) && !Object.hasOwn(e.oversize, row.event_id);
      assert.equal(row.projected, inPrefix, `${row.event_id} projected`);
      const want = e.unverified[row.event_id];
      if (want) { assert.equal(row.status, "unverified", row.event_id); assert.deepEqual(row.reasons, want, row.event_id); }
      else { assert.equal(row.status, "verified", row.event_id); assert.deepEqual(row.reasons, [], row.event_id); }
      assert.deepEqual(row.oversize, e.oversize[row.event_id] ?? [], `${row.event_id} oversize`);
    }
    assert.deepEqual(subset(mine.projection.nodes, e.nodes, "nodes"), []);
    for (const node of e.absent_nodes) assert.ok(!Object.hasOwn(mine.projection.nodes, node), `${node} must not be projected`);
    assert.ok(same(mine.projection.rejected, e.rejected));
    if (e.no_acceptance) assert.ok(!Object.values(mine.projection.nodes).some((n) => n.accepted_ever), "a forged or skipped acceptance reached the board");
  });
  if (new Set(chain.envelopes.map((env) => env.event.seq)).size === chain.envelopes.length) {
    test(`${label}: delivery order doesn't change the browser result`, async () => {
      const a = await browserVerify(chain.envelopes, chain.view);
      const b = await browserVerify([...chain.envelopes].reverse(), chain.view);
      assert.ok(same(refFields(a), refFields(b)));
    });
  }
}

test("V1-V9 statuses in the browser copy: verified, unverified and chain outcomes", async () => {
  const summary = {};
  for (const chain of viewFile.chains) {
    const r = await browserVerify(chain.envelopes, chain.view);
    summary[chain.name.split(" ")[0]] = `${r.rows.filter((x) => x.status === "verified").length}/${r.rows.length} ${r.chain_ok ? "ok" : "broken"} K=${r.prefix_end}`;
  }
  assert.deepEqual(summary, {
    V1: "11/11 ok K=11", V2: "10/10 ok K=10", V3: "9/11 broken K=3", V4: "11/11 ok K=11", V5a: "0/11 broken K=0", V5b: "0/11 broken K=0",
    V6a: "4/5 broken K=3", V6b: "5/6 broken K=3", V7: "11/11 ok K=3", V8: "8/9 broken K=6", V9: "0/11 broken K=0",
  });
});

// ── mode, caps, hashing ───────────────────────────────────────────────────────────────────────────────────────
test(`mode(): all ${viewFile.mode.length} vector cases`, () => {
  for (const c of viewFile.mode) assert.equal(core.mode(c.source, c.last_poll_ok_ms, c.last_verified_arrival_ms, c.now_ms), c.expect, c.note);
});
// The reference runner's padding rule, as the vector file states it in `build`.
function padTo(base, target) {
  const env = structuredClone(base);
  env.values = { ...env.values, artifact_hashes: Array.from({ length: 64 }, () => "a".repeat(512)), geometry: Array.from({ length: 64 }, (_, i) => ({ id: `g${i}`, xLL: 0, yLL: 0, w: 1, h: 1, layer: 0 })) };
  let missing = target - Buffer.byteLength(refCanonical(env), "utf8");
  for (const entry of env.values.geometry) {
    const add = Math.max(0, Math.min(missing, 512 - entry.id.length));
    entry.id += "x".repeat(add);
    missing -= add;
  }
  assert.equal(missing, 0);
  return env;
}
test(`checkCaps(): all ${viewFile.caps.length} vector cases, including depth and the 64 KiB boundary`, () => {
  const base = viewFile.chains[0].envelopes.find((env) => env.event.seq === 4);
  for (const spec of viewFile.caps) {
    const env = spec.envelope ?? (spec.raw !== undefined ? JSON.parse(spec.raw) : padTo(base, spec.target_bytes));
    if (spec.target_bytes !== undefined) assert.equal(sha(Buffer.from(refCanonical(env), "utf8")), spec.canonical_sha256, spec.name);
    assert.deepEqual(core.checkCaps(env), ref.checkCaps(env), spec.name);
    assert.deepEqual(core.checkCaps(env).reasons, spec.expect, spec.name);
  }
});
test("hashing: absent, undefined and null values hash as the vectors say; genesis as the rule says", async () => {
  for (const spec of viewFile.hashing) {
    assert.equal(await core.hashEnvelope(spec.envelope), spec.hash_values_absent);
    assert.equal(await core.hashEnvelope({ ...spec.envelope, values: undefined }), spec.hash_values_undefined);
    assert.equal(await core.hashEnvelope({ ...spec.envelope, values: null }), spec.hash_values_null);
  }
  assert.equal(await core.genesis("run-v1"), ref.genesis("run-v1"));
  assert.equal(viewFile.chains[0].envelopes[0].prev_hash, await core.genesis("run-v1"));
});

// ── keys and pins ─────────────────────────────────────────────────────────────────────────────────────────────
test("the browser derives the same test keys as the vectors' rule", async () => {
  for (const name of ["core", "forger"]) {
    const raw = await core.publicKeyFromSeedText(`sentilab-view-test-key:${name}`);
    assert.deepEqual([...raw], [...testKey(name).raw], name);
    assert.equal((await core.keySha256(raw)).slice(0, 8), viewFile.test_keys[name].key_sha256_prefix, name);
  }
});
test("the production pin list is empty and frozen", () => {
  assert.ok(Array.isArray(VIEW_PINS));
  assert.equal(VIEW_PINS.length, 0);
  assert.ok(Object.isFrozen(VIEW_PINS));
});
test("a served key is used only if its hash matches the pin: V1 under wrong pins never verifies", async () => {
  const v1 = viewFile.chains[0];
  const forgerPin = [{ key_id: "core", key_sha256: testKey("forger").sha256 }];
  const wrong = await browserVerify(v1.envelopes, v1.view, forgerPin);
  assert.ok(wrong.rows.every((r) => same(r.reasons, ["key_hash_mismatch"])));
  const none = await browserVerify(v1.envelopes, v1.view, []);
  assert.ok(none.rows.every((r) => same(r.reasons, ["key_not_pinned"])));
  assert.equal(none.prefix_end, 0);
  assert.deepEqual(none.projection.nodes, {}, "nothing unverified is projected");
  const unserved = await core.verifyChain(structuredClone(v1.envelopes), { runId: "run-v1", pins: nodePins(v1.view), keys: {} });
  assert.ok(unserved.rows.every((r) => same(r.reasons, ["key_unavailable"])));
  const rotated = await browserVerify(v1.envelopes, v1.view, [{ key_id: "core-previous", key_sha256: testKey("forger").sha256 }, ...nodePins(v1.view)]);
  assert.equal(rotated.chain_ok, true, "two pinned ids: rotation");
});
test("a key served from the feed can't stand in for a missing pin", async () => {
  // The key comes with the data (as a forged bundle would ship it), but the page pins nothing.
  const v1 = viewFile.chains[0];
  const keys = core.parseKeyResponse({ key_id: "core", public_key: Buffer.from(testKey("core").raw).toString("hex") });
  const r = await core.verifyChain(structuredClone(v1.envelopes), { runId: "run-v1", pins: VIEW_PINS, keys });
  assert.ok(r.rows.every((row) => row.status === "unverified" && row.reasons.includes("key_not_pinned")));
});

// ── the demo fixture ─────────────────────────────────────────────────────────────────────────────────────────
const demoText = readFileSync(DEMO_PATH, "utf8");
const demoEnvelopes = core.parseJsonl(demoText);
const testPins = [{ key_id: "core", key_sha256: testKey("core").sha256 }];
const testKeys = { core: testKey("core").raw };

test("demo-run.jsonl is reproducible from its generator (reference makeChain, core TEST key)", () => {
  assert.equal(buildDemo().jsonl, demoText);
  assert.equal(demoEnvelopes.length, 44);
});
test("demo under the production pins: every row unverified as 'no pinned key', nothing projected", async () => {
  const r = await core.verifyChain(demoEnvelopes, { runId: DEMO_RUN.run_id, pins: VIEW_PINS, keys: {} });
  assert.ok(r.rows.every((row) => same(row.reasons, ["key_not_pinned"])));
  assert.equal(r.prefix_end, 0);
  assert.equal(r.label, "chain broken after seq 0; board frozen at seq 0");
  assert.deepEqual(r.projection.nodes, {});
  const sum = chainSummary(r.rows);
  assert.equal(sum.verified, 0);
  assert.deepEqual(sum.phrases, ["no pinned key"]);
  const view = buildView(r, r.ordered.length);
  assert.equal(view.trustedCount, 0);
  assert.equal(view.cards.length, 0);
  assert.equal(view.board.current, null);
  assert.equal(feedRows(r, r.ordered.length).length, 44, "every envelope is still listed");
});
test("demo under TEST keys: 44/44 verified, and the reference agrees", async () => {
  const r = await core.verifyChain(demoEnvelopes, { runId: DEMO_RUN.run_id, pins: testPins, keys: testKeys });
  assert.equal(r.chain_ok, true);
  assert.equal(r.prefix_end, 44);
  assert.equal(r.frozen, false);
  const theirs = ref.verifyChain(demoEnvelopes, { runId: DEMO_RUN.run_id, pins: testPins, keys: { core: testKey("core").publicKey } });
  assert.ok(same(refFields(r), theirs));
});
test("demo story: one acceptance, one valid loser, and the drill's stale and surviving nodes come from project()", async () => {
  const r = await core.verifyChain(demoEnvelopes, { runId: DEMO_RUN.run_id, pins: testPins, keys: testKeys });
  const n = r.projection.nodes;
  assert.equal(n["cand-b"].lifecycle, "accepted");
  assert.equal(n["cand-b"].validity, "valid");
  assert.deepEqual(n["cand-b"].support_status, { eval: "broken", repro: "valid" });
  assert.equal(n["cand-a"].lifecycle, "non_improving_current");
  assert.equal(n["cand-a"].validity, "valid");
  assert.equal(n["cand-c"].lifecycle, "rejected_constraints");
  assert.equal(n["cand-d"].lifecycle, "failed_run");
  assert.equal(n["cand-sa"].lifecycle, "non_improving");
  assert.equal(n["meas-b"].validity, "withdrawn");
  assert.equal(n["claim-b-lower-j"].validity, "stale");
  assert.deepEqual(n["claim-b-lower-j"].stale_because, ["meas-b"]);
  assert.equal(n["cmp-b-vs-init"].validity, "valid");
  assert.deepEqual(r.projection.rejected, []);
  assert.ok(isDrill(demoEnvelopes));

  const end = buildView(r, r.ordered.length);
  assert.equal(end.board.current.id, "cand-b");
  assert.equal(end.cards.length, 6);
  assert.deepEqual(end.drill.withdrawn.map((e) => e.id), ["meas-b"]);
  assert.deepEqual(end.drill.stale.map((e) => e.id), ["claim-b-lower-j"]);
  assert.deepEqual(end.drill.survived.map((e) => e.id).sort(), ["cand-b", "cmp-b-vs-init"]);
  const b = end.cards.find((c) => c.id === "cand-b");
  assert.equal(b.source.id, "repro-b", "after the drill the card shows the surviving measurement");
  assert.equal(b.J.value, 90.1);

  const before = buildView(r, 43);
  assert.equal(before.drill, null);
  assert.equal(before.cards.find((c) => c.id === "cand-b").source.id, "meas-b");
  assert.equal(buildView(r, 31).board.current, null, "nothing accepted before seq 32");
  assert.equal(buildView(r, 32).board.current.id, "cand-b");
});
test("a broken chain freezes the panels at the prefix (V3 tamper, V8 dropped event)", async () => {
  for (const [index, k] of [[2, 3], [9, 6]]) {
    const chain = viewFile.chains[index];
    const r = await browserVerify(chain.envelopes, chain.view);
    const view = buildView(r, r.ordered.length);
    assert.equal(view.trustedCount, r.prefix);
    assert.deepEqual(view.broken, { afterSeq: k }, chain.name);
    assert.ok(same(view.projection, r.projection), "the panels show exactly the prefix projection");
    const rows = feedRows(r, r.ordered.length);
    assert.ok(rows.slice(r.prefix).every((row) => row.projected === false));
  }
});
