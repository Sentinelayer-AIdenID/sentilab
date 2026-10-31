// node --test web/test/sentilab-parity.test.mjs
// The Lab view's browser modules (web/public/sentilab/) must give exactly the contract's answers:
//   - evidence-projection.mjs is aneta's file byte for byte, and project() matches her vectors;
//   - canonical.mjs gives the same strings as resultcheck.mjs's canonical();
//   - view-core.mjs (the WebCrypto port) gives the same result as the VIEW ENVELOPE v0.5 reference on every v0.5 vector:
//     every chain (V1-V11, V13-V15) in every delivery order, the live timelines (V16, V17), the transport caps (V18),
//     every input check (V12), mode, hashing and canonical cases. It never canonicalizes, hashes or verifies input
//     that failed the input checks (instrumented counters);
//   - the production pins hold only the service key (never a derivable test key), and the demo verifies only under TEST keys.
// The originals are the repo's executable contracts in contracts/ (hashes checked below and in contracts/HASHES.txt).
import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { project as refProject } from "../../contracts/contract-0.2/evidence-projection.mjs";
import { canonical as refCanonical } from "../../contracts/contract-0.2/resultcheck.mjs";
import * as ref from "../../contracts/view-envelope-v0.5/view-envelope.mjs";
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
const bytes = (text) => Buffer.byteLength(text, "utf8");
const evidenceVectors = JSON.parse(contract("contract-0.2", "vectors-evidence.json")).vectors;
const viewFile = JSON.parse(contract("view-envelope-v0.5", "vectors-view.json"));

// ── the contracts are what their hashes say they are ────────────────────────────────────────────────────────
const PINNED = {
  "contract-0.2/evidence-projection.mjs": "fe861207ed1bfbf90e457f84606dbbd335cb762d2041c9ee942aa006d3f31001",
  "contract-0.2/resultcheck.mjs": "4fb7a64ea3e22379e3731494225e7be29062990284724ef08a5dc0a4ea582049",
  "contract-0.2/vectors-evidence.json": "5c20a91a0890b9a66774e93b5792b9a717ec085314adf879b458ad9006f2510c",
  "view-envelope-v0.5/VIEW-ENVELOPE.md": "7a92d88aca1e4911a5119dbdff15ad096922dc238a67349e087030d45ad53df6",
  "view-envelope-v0.5/view-envelope.mjs": "54b248236ff93e249c7638a0dbeb4533fc7d9f15915e9b1895d1709d348f1ea7",
  "view-envelope-v0.5/vectors-view.json": "6149b9b131be50e2f4affa6badfa832435a457a6fa306bf137585608dbe54d88",
};
test("the contract files are the hashed originals", () => {
  for (const [path, want] of Object.entries(PINNED)) assert.equal(sha(contract(...path.split("/"))), want, path);
  assert.equal(viewFile.contract_sha256, PINNED["view-envelope-v0.5/VIEW-ENVELOPE.md"], "vectors are for VIEW ENVELOPE v0.5");
  assert.equal(core.VERSION, ref.VERSION);
  assert.equal(core.VERSION, "view-envelope/0.5");
});
test("the browser projection is aneta's evidence-projection.mjs byte for byte", () => {
  assert.equal(sha(read("..", "public", "sentilab", "evidence-projection.mjs")), PINNED["contract-0.2/evidence-projection.mjs"]);
});

// ── canonical() ───────────────────────────────────────────────────────────────────────────────────────────────
test("browser canonical() equals resultcheck.mjs canonical() on every vector input and on edge values", () => {
  const inputs = [
    ...evidenceVectors.flatMap((v) => v.events),
    ...viewFile.chains.flatMap((c) => c.envelopes),
    ...viewFile.live.flatMap((c) => c.envelopes),
    ...viewFile.input_checks.filter((c) => typeof c.raw === "string" && c.build !== "not_json").map((c) => JSON.parse(c.raw)),
    ...viewFile.hashing.map((h) => h.envelope),
    ...viewFile.canonical.map((c) => JSON.parse(c.raw)),
    { a: undefined, b: [undefined, null, NaN, Infinity, -0, 1e21, 1e-7, 5.0], c: " \ud800\u0000é😀" },
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

// ── the v0.5 harness: keys, JSONL lines and input cases, rebuilt by the rules the vector file states ──────────────
const nodePins = (view) => view.pins.map((p) => ({ key_id: p.key_id, key_sha256: testKey(p.test_key).sha256 }));
const nodeKeys = (view) => Object.fromEntries(Object.entries(view.served_keys).map(([id, name]) => [id, testKey(name).publicKey]));
const rawKeys = (view) => Object.fromEntries(Object.entries(view.served_keys).map(([id, name]) => [id, testKey(name).raw]));
const refOptions = (view) => ({ runId: view.run_id, pins: nodePins(view), keys: nodeKeys(view) });
const coreOptions = (view, pins = nodePins(view)) => ({ runId: view.run_id, pins, keys: rawKeys(view) });
// The reference's result fields; the port adds `ordered`, `meta`, `prefix` and `duplicates` for the page.
const refFields = ({ rows, chain_ok, prefix_end, frozen, label, projection, projection_error }) => ({ rows, chain_ok, prefix_end, frozen, label, projection, projection_error });

// The vector file's `send` rule (run-view-vectors.mjs buildLines): one list of JSONL lines per delivery order.
function buildLines(envelopes, send) {
  const line = (env) => {
    const text = JSON.stringify(env);
    return send.pad && env.event.seq === send.pad.seq ? `{${" ".repeat(send.pad.line_bytes - bytes(text))}${text.slice(1)}` : text;
  };
  const lists = send.orders ? send.orders.map((list) => list.map((eid) => envelopes.find((env) => env.event.event_id === eid))) : [envelopes];
  return lists.map((list) => {
    const lines = list.map(line);
    return send.twice ? [...lines, ...lines] : lines;
  });
}
const rowKey = (row) => (row.event_id === null ? null : `${row.seq}:${row.event_id}`);
// The hand-written expect block, checked as run-view-vectors.mjs checks it.
function checkExpect(result, expect) {
  const errors = [];
  if (result.rows.length !== expect.rows) errors.push(`expected ${expect.rows} rows, got ${result.rows.length}`);
  for (const key of ["chain_ok", "prefix_end", "frozen", "label"]) if (result[key] !== expect[key]) errors.push(`${key}: expected ${JSON.stringify(expect[key])}, got ${JSON.stringify(result[key])}`);
  const unreadable = [...expect.unreadable];
  let inPrefix = true;
  for (const row of result.rows) {
    const key = rowKey(row);
    let want;
    if (key === null) want = unreadable.shift() ?? { status: "(none expected)", reasons: [] };
    else if (Object.hasOwn(expect.rejected, key)) want = expect.rejected[key];
    else if (Object.hasOwn(expect.unverified, key)) want = { status: "unverified", reasons: expect.unverified[key] };
    else want = { status: "verified", reasons: [] };
    if (row.status !== want.status || !same(row.reasons, want.reasons)) errors.push(`${key ?? "unreadable row"}: expected ${want.status} ${refCanonical(want.reasons)}, got ${row.status} ${refCanonical(row.reasons)}`);
    inPrefix = inPrefix && want.status === "verified";
    if (row.projected !== inPrefix) errors.push(`${key}: projected should be ${inPrefix}`);
  }
  if (unreadable.length > 0) errors.push(`${unreadable.length} unreadable rows missing`);
  if (result.projection_error !== null) errors.push(`projection_error ${result.projection_error}`);
  if (!result.projection) return [...errors, "no projection"];
  errors.push(...subset(result.projection.nodes, expect.nodes, "nodes"));
  for (const node of expect.absent_nodes) if (Object.hasOwn(result.projection.nodes, node)) errors.push(`${node} should not be in the projection`);
  if (!same(result.projection.rejected, expect.project_rejected)) errors.push(`project rejected: expected ${refCanonical(expect.project_rejected)}, got ${refCanonical(result.projection.rejected)}`);
  return errors;
}
// What the page reads beyond the reference's fields must agree with them.
function checkPageFields(result) {
  const errors = [];
  if (result.ordered.length !== result.rows.length || result.meta.length !== result.rows.length) errors.push("ordered/meta length");
  result.rows.forEach((row, i) => {
    const rejected = row.status === "oversize" || row.status === "malformed";
    if (rejected !== (result.ordered[i] === null)) errors.push(`row ${i}: a rejected row has no envelope, every other row has one`);
    if (!rejected && result.ordered[i].event.seq !== row.seq) errors.push(`row ${i}: envelope seq differs`);
  });
  if (result.prefix !== result.rows.filter((row) => row.projected).length) errors.push("prefix length differs from the projected rows");
  return errors;
}

// ── every chain vector: the browser verifyJsonl() against the recorded result and the reference ─────────────────
const browserResults = new Map();
for (const chain of viewFile.chains) {
  const label = chain.name.split(":")[0];
  const lineSets = buildLines(chain.envelopes, chain.send);
  test(`${label}: the browser verifyJsonl() equals the recorded result, the reference and the hand-written expectations`, async () => {
    const mine = await core.verifyJsonl(lineSets[0], coreOptions(chain.view));
    browserResults.set(label.split(" ")[0], mine);
    assert.ok(same(refFields(mine), chain.result), "differs from the vector file's recorded result");
    assert.ok(same(refFields(mine), ref.verifyJsonl(lineSets[0], refOptions(chain.view))), "differs from the reference");
    assert.deepEqual(checkExpect(mine, chain.expect), []);
    assert.deepEqual(checkPageFields(mine), []);
    if (chain.expect.no_acceptance) assert.ok(!Object.values(mine.projection.nodes).some((n) => n.accepted_ever || n.lifecycle === "accepted"), "a forged or skipped acceptance reached the board");
  });
  test(`${label}: delivery order never changes the browser result (reversed${chain.send.orders ? ", every listed order" : ""})`, async () => {
    for (const lines of [...lineSets, [...lineSets[0]].reverse()]) {
      assert.ok(same(refFields(await core.verifyJsonl(lines, coreOptions(chain.view))), chain.result));
    }
  });
  if (!chain.send.pad) {
    test(`${label}: the parsed path (browser verifyChain) gives the same result as the JSONL path`, async () => {
      for (const lines of lineSets) {
        assert.ok(same(refFields(await core.verifyChain(lines.map((line) => JSON.parse(line)), coreOptions(chain.view))), chain.result));
      }
    });
  }
}

test("V1-V15 in the browser copy: statuses, chain outcomes and K", async () => {
  const summary = {};
  for (const chain of viewFile.chains) {
    const r = await core.verifyJsonl(buildLines(chain.envelopes, chain.send)[0], coreOptions(chain.view));
    summary[chain.name.split(" ")[0]] = `${r.rows.filter((x) => x.status === "verified").length}/${r.rows.length} ${r.chain_ok ? "ok" : "broken"} K=${r.prefix_end}`;
  }
  assert.deepEqual(summary, {
    V1: "11/11 ok K=11", V2: "10/10 ok K=10", V3: "9/11 broken K=3", V4: "11/11 ok K=11", V5a: "0/11 broken K=0", V5b: "0/11 broken K=0",
    V6a: "4/5 broken K=3", V6b: "4/6 broken K=2", V7: "10/11 broken K=3", V8: "8/9 broken K=6", V9: "0/11 broken K=0",
    V10: "9/11 broken K=3", V11: "9/11 broken K=3", V13: "2/4 broken K=0", V14: "1/3 broken K=0", V15: "11/11 ok K=11",
  });
});
test("V13: two different seq 1 envelopes give K = 0 with seq_conflict in both delivery orders", async () => {
  const chain = viewFile.chains.find((c) => c.name.startsWith("V13"));
  for (const lines of buildLines(chain.envelopes, chain.send)) {
    const r = await core.verifyJsonl(lines, coreOptions(chain.view));
    assert.equal(r.prefix_end, 0);
    assert.equal(r.chain_ok, false);
    assert.deepEqual(r.rows.filter((row) => row.seq === 1).map((row) => row.reasons), [["seq_conflict"], ["seq_conflict"]]);
  }
});
test("V14: one event_id at seq 1 and 2 gives K = 0 with event_id_conflict, never chain_ok", async () => {
  const chain = viewFile.chains.find((c) => c.name.startsWith("V14"));
  const r = await core.verifyJsonl(buildLines(chain.envelopes, chain.send)[0], coreOptions(chain.view));
  assert.equal(r.prefix_end, 0);
  assert.equal(r.chain_ok, false);
  assert.ok(r.rows.filter((row) => row.event_id === "v14-e01").every((row) => row.reasons.includes("event_id_conflict")));
});
test("V15: every V1 envelope twice, byte-identical, gives exactly V1's result; the copies make no row", async () => {
  const v1 = viewFile.chains.find((c) => c.name.startsWith("V1 "));
  const v15 = viewFile.chains.find((c) => c.name.startsWith("V15"));
  const once = await core.verifyJsonl(buildLines(v1.envelopes, v1.send)[0], coreOptions(v1.view));
  const twice = await core.verifyJsonl(buildLines(v15.envelopes, v15.send)[0], coreOptions(v15.view));
  assert.ok(same(refFields(twice), refFields(once)));
  assert.equal(twice.duplicates, 11);
  assert.equal(once.duplicates, 0);
});
test("V10: the padded 131,761-byte line is never parsed, canonicalized, hashed or verified by the browser core", async () => {
  const chain = viewFile.chains.find((c) => c.name.startsWith("V10"));
  const padded = buildLines(chain.envelopes, chain.send)[0].find((line) => bytes(line) > 65_536);
  assert.equal(bytes(padded), 131_761);
  core.resetCounters();
  const r = await core.verifyJsonl([padded], coreOptions(chain.view));
  assert.deepEqual(core.counters, { parse: 0, canonical: 0, hash: 0, verify: 0 });
  assert.deepEqual(r.rows, [{ seq: null, event_id: null, status: "oversize", reasons: ["line_too_large"], projected: false }]);
});
test("V7, V10, V11: rejected rows are never canonicalized, hashed or verified by the browser core", async () => {
  let rejectedLines = 0;
  for (const chain of viewFile.chains.filter((c) => Object.keys(c.expect.rejected).length > 0 || c.expect.unreadable.length > 0)) {
    const lines = buildLines(chain.envelopes, chain.send)[0].filter((line) => !ref.checkLine(line).ok);
    rejectedLines += lines.length;
    core.resetCounters();
    const r = await core.verifyJsonl(lines, coreOptions(chain.view));
    assert.ok(r.rows.length === lines.length && r.rows.every((row) => row.status === "oversize" || row.status === "malformed"), chain.name);
    assert.equal(core.counters.canonical + core.counters.hash + core.counters.verify, 0, `${chain.name}: ${JSON.stringify(core.counters)}`);
  }
  assert.equal(rejectedLines, 4, "V7 (1), V10 (1) and V11 (2)");
});

// ── V12: every input check, through the raw path (verifyJsonl) and the parsed path (verifyChain) ──────────────────
// buildInputCase and padTo are the vector file's rules (run-view-vectors.mjs); the rebuilt raw lines are checked
// against the file's raw text or sha256, so this harness can't drift from the vectors.
const nest = (n) => { let x = {}; for (let i = 1; i < n; i += 1) x = { d: x }; return x; };
const artifact = (name) => sha(Buffer.from(`artifact:${name}`, "utf8"));
function padTo(base, target) {
  const env = structuredClone(base);
  env.values = { ...env.values, artifact_hashes: Array.from({ length: 64 }, () => "a".repeat(512)), geometry: Array.from({ length: 64 }, (_, i) => ({ id: `g${i}`, xLL: 0, yLL: 0, w: 1, h: 1, layer: 0 })) };
  let missing = target - bytes(refCanonical(env));
  for (const entry of env.values.geometry) {
    const add = Math.max(0, Math.min(missing, 512 - entry.id.length));
    entry.id += "x".repeat(add);
    missing -= add;
  }
  assert.equal(missing, 0);
  return env;
}
function buildInputCase(build, base) {
  const withValues = (patch) => ({ ...structuredClone(base), values: { ...structuredClone(base.values), ...patch } });
  const both = (value) => ({ value, raw: JSON.stringify(value) });
  const temps = (n) => Object.fromEntries(Array.from({ length: n }, (_, i) => [`c${String(i).padStart(2, "0")}`, 70]));
  switch (build) {
    case "base": return both(structuredClone(base));
    case "deep_100000": {
      const value = withValues({});
      let inner = {};
      for (let i = 0; i < 100_000; i += 1) inner = { d: inner };
      value.values.nest = inner;
      const text = JSON.stringify(withValues({ nest: 0 }));
      return { value, raw: text.replace('"nest":0', `"nest":${"[".repeat(100_000)}${"]".repeat(100_000)}`) };
    }
    case "nest_9": return both(withValues({ nest: nest(7) }));
    case "nest_8": return both(withValues({ nest: nest(6) }));
    case "padded_131761": { const text = JSON.stringify(base); return { value: null, raw: `{${" ".repeat(131_761 - bytes(text))}${text.slice(1)}` }; }
    case "not_json": return { value: null, raw: JSON.stringify(base).slice(0, -1) };
    case "lone_value": return both(withValues({ scenario_id: "scn-01\ud800" }));
    case "lone_key": return both(withValues({ center_temps: { "c\udc00": 70 } }));
    case "string_513": return both(withValues({ scenario_id: "s".repeat(513) }));
    case "string_512": return both(withValues({ scenario_id: "s".repeat(512) }));
    case "astral_512": return both(withValues({ scenario_id: "😀".repeat(512) }));
    case "key_513": return both(withValues({ center_temps: { ["k".repeat(513)]: 70 } }));
    case "infinity": { const raw = JSON.stringify(withValues({ J: { value: 0, unit: "°C" } })).replace('"value":0', '"value":1e999'); return { value: JSON.parse(raw), raw }; }
    case "temps_65": return both(withValues({ center_temps: temps(65) }));
    case "temps_64": return both(withValues({ center_temps: temps(64) }));
    case "geometry_65": return both(withValues({ geometry: Array.from({ length: 65 }, (_, i) => ({ id: `g${i}`, xLL: i, yLL: 0, w: 1, h: 1, layer: 0 })) }));
    case "hashes_65": return both(withValues({ artifact_hashes: Array.from({ length: 65 }, (_, i) => artifact(`cap:${i}`)) }));
    case "alg_rsa": { const value = structuredClone(base); value.sig.alg = "rsa"; return both(value); }
    case "hash_upper": { const value = structuredClone(base); value.hash = value.hash.toUpperCase(); return both(value); }
    case "seq_0": { const value = structuredClone(base); value.event.seq = 0; return both(value); }
    case "no_body": { const value = structuredClone(base); delete value.event.body; return both(value); }
    case "values_null": return both({ ...structuredClone(base), values: null });
    case "values_undefined": return { value: { ...structuredClone(base), values: undefined }, raw: null };
    case "expands_1e20": {
      const text = JSON.stringify({ ...structuredClone(base), event: { ...structuredClone(base.event), body: { ...base.event.body, pad: 0 } } });
      const raw = text.replace('"pad":0', `"pad":[${Array(12_000).fill("1e20").join(",")}]`);
      return { value: JSON.parse(raw), raw };
    }
    case "bytes_65536": return both(padTo(base, 65_536));
    case "bytes_65537": return both(padTo(base, 65_537));
    default: throw new Error(`unknown build ${build}`);
  }
}
const OK = "passes";
const v1Chain = viewFile.chains[0];
const inputBase = v1Chain.envelopes[0];
const outcomeOf = (row) => (["oversize", "malformed"].includes(row.status) ? { status: row.status, reasons: row.reasons } : OK);
const inputCases = viewFile.input_checks.map((spec) => ({ spec, made: buildInputCase(spec.build, inputBase) }));

test(`V12: the rebuilt inputs are the vector file's (${inputCases.length} cases)`, () => {
  for (const { spec, made } of inputCases) {
    if (typeof spec.raw === "string") assert.equal(made.raw, spec.raw, spec.name);
    else if (spec.raw === null) assert.equal(made.raw, null, spec.name);
    else { assert.equal(bytes(made.raw), spec.raw_bytes, spec.name); assert.equal(sha(Buffer.from(made.raw, "utf8")), spec.raw_sha256, spec.name); }
  }
});
for (const { spec, made } of inputCases) {
  test(`V12 input checks: ${spec.name}`, async () => {
    for (const path of ["raw", "parsed"]) {
      const want = spec.expect[path];
      if (want === null) continue;
      core.resetCounters();
      const result = path === "raw" ? await core.verifyJsonl([made.raw], coreOptions(v1Chain.view)) : await core.verifyChain([made.value], coreOptions(v1Chain.view));
      const seen = { ...core.counters };
      assert.ok(same(outcomeOf(result.rows[0]), want), `${path}: expected ${refCanonical(want)}, got ${refCanonical(outcomeOf(result.rows[0]))}`);
      if (want === OK) {
        // The control: the counters do move when input passes, so a zero below is a real zero.
        assert.ok(seen.canonical >= 1 && seen.hash === 1 && seen.verify === 1, `${path}: the control should canonicalize, hash and verify: ${JSON.stringify(seen)}`);
      } else {
        assert.equal(seen.canonical + seen.hash + seen.verify, 0, `${path}: rejected input reached canonical/hash/verify: ${JSON.stringify(seen)}`);
        if (path === "raw" && want.reasons[0] === "line_too_large") assert.equal(seen.parse, 0, "raw: an oversize line was parsed");
      }
    }
    // The single-line checks agree with the reference, field for field.
    if (made.raw !== null) {
      const { value: mineValue, ...mine } = core.checkLine(made.raw);
      const { value: refValue, ...theirs } = ref.checkLine(made.raw);
      assert.deepEqual(mine, theirs);
    }
    if (made.value !== null) assert.deepEqual(core.checkEnvelope(made.value), ref.checkEnvelope(made.value));
  });
}
test("V12: in a mixed feed, the rejected lines add no canonical, hash or verify call", async () => {
  const good = buildLines(v1Chain.envelopes, {})[0];
  const bad = inputCases.filter(({ spec, made }) => typeof made.raw === "string" && spec.expect.raw !== OK).map(({ made }) => made.raw);
  assert.ok(bad.length >= 15, `${bad.length} rejected lines`);
  core.resetCounters();
  await core.verifyJsonl(good, coreOptions(v1Chain.view));
  const alone = { ...core.counters };
  core.resetCounters();
  const mixed = await core.verifyJsonl([...bad.slice(0, 7), ...good, ...bad.slice(7)], coreOptions(v1Chain.view));
  assert.deepEqual({ canonical: core.counters.canonical, hash: core.counters.hash, verify: core.counters.verify }, { canonical: alone.canonical, hash: alone.hash, verify: alone.verify });
  assert.equal(mixed.rows.length, 11 + bad.length);
  assert.equal(mixed.chain_ok, false, "chain_ok is false whenever any row is rejected");
});

// ── V16, V17: the page's live loop (transport caps, liveFeed, verifyChecked, progressTracker) on the client clock ──
const BASE_MS = Date.UTC(2026, 9, 31, 12, 0, 0);
async function simulateBrowser(spec) {
  const options = coreOptions(spec.view);
  const tracker = core.progressTracker();
  const feed = core.liveFeed();
  const lineOf = new Map(spec.envelopes.map((env) => [env.event.seq, JSON.stringify(env)]));
  const sent = new Set();
  const timeline = [];
  let verification = null;
  const { from_s, to_s, every_s } = spec.schedule.polls;
  for (let t = from_s; t <= to_s; t += every_s) {
    const nowMs = BASE_MS + t * 1000;
    const due = spec.schedule.releases.filter((release) => release.at_s <= t).flatMap((release) => release.seqs);
    const batch = spec.schedule.resend_all ? due : due.filter((seq) => !sent.has(seq));
    batch.forEach((seq) => sent.add(seq));
    const response = core.parseApiResponse(batch.map((seq) => `${lineOf.get(seq)}\n`).join(""));
    if (response.ok && (feed.add(response.lines) > 0 || verification === null)) verification = await core.verifyChecked(feed.items, options);
    const K = verification.prefix_end;
    tracker.poll({ nowMs, ok: response.ok, K, received: response.ok ? response.lines.length : 0 });
    timeline.push({ t, received: response.ok ? response.lines.length : 0, K, label: tracker.label("api", nowMs) });
  }
  return { timeline, verification, items: feed.items.length };
}
for (const spec of viewFile.live) {
  const label = spec.name.split(":")[0];
  test(`${label}: the browser live loop gives the recorded timeline, labels and K`, async () => {
    const sim = await simulateBrowser(spec);
    assert.ok(same(sim.timeline, spec.result), "timeline differs from the vector file");
    const byTime = new Map(sim.timeline.map((step) => [step.t, step]));
    for (const [t, want] of Object.entries(spec.expect.labels)) assert.equal(byTime.get(Number(t)).label, want, `label at ${t} s`);
    for (const [t, want] of Object.entries(spec.expect.K)) assert.equal(byTime.get(Number(t)).K, want, `K at ${t} s`);
    for (const step of sim.timeline) {
      const wantLive = step.t >= spec.expect.live_from_s && (spec.expect.stale_from_s === null || step.t < spec.expect.stale_from_s);
      assert.equal(step.label.startsWith("LIVE"), wantLive, `at ${step.t} s: ${step.label}`);
      assert.doesNotMatch(step.label, /complete|final|done|finished/i, "a label never claims completeness");
    }
    if (spec.expect.arrivals_every_poll) {
      assert.ok(sim.timeline.every((step) => step.received > 0 && step.K === sim.timeline[0].K), "arrivals at every poll, none grew K");
      assert.equal(sim.items, spec.envelopes.length, "byte-identical re-sends are no-ops: the feed holds each line once");
    }
    if (spec.expect.board_at_end) assert.deepEqual(subset(sim.verification.projection.nodes, spec.expect.board_at_end, "board"), []);
    if (spec.expect.full_history) {
      const full = await core.verifyChain(spec.envelopes, coreOptions(spec.view));
      assert.deepEqual(subset(full.projection.nodes, spec.expect.full_history, "full"), []);
      assert.equal(full.prefix_end, spec.envelopes.length);
    }
  });
}
test("tracker: only growth of K beyond its highest value refreshes progress; a failed poll is not a good poll", () => {
  const tracker = core.progressTracker();
  tracker.poll({ nowMs: 0, ok: true, K: 0, received: 0 });
  assert.equal(tracker.mode("api", 0), "STALE", "K = 0 is STALE");
  tracker.poll({ nowMs: 1_000, ok: true, K: 5, received: 5 });
  tracker.poll({ nowMs: 2_000, ok: true, K: 3, received: 9 });
  tracker.poll({ nowMs: 3_000, ok: true, K: 5, received: 9 });
  assert.equal(tracker.state().last_progress_ms, 1_000, "a drop and a return to the old K never refresh progress");
  tracker.poll({ nowMs: 4_000, ok: false, K: 9 });
  assert.deepEqual([tracker.state().last_poll_ok_ms, tracker.state().K], [3_000, 5], "a failed poll changes nothing");
  tracker.poll({ nowMs: 5_000, ok: true, K: 6, received: 1 });
  assert.equal(tracker.state().last_progress_ms, 5_000);
  assert.equal(tracker.label("api", 10_001), "STALE", "no good poll for over 5 s");
  tracker.poll({ nowMs: 17_000, ok: true, K: 6, received: 3 });
  assert.equal(tracker.label("api", 17_900), "LIVE · progress 12 s ago", "a good poll with no growth keeps the old progress time");
  tracker.poll({ nowMs: 65_000, ok: true, K: 6, received: 3 });
  assert.equal(tracker.label("api", 65_000), "LIVE · progress 60 s ago", "60 s is inclusive");
  assert.equal(tracker.label("api", 65_001), "STALE", "polls succeed, but K hasn't grown for over 60 s");
});
test("liveFeed: byte-identical re-sends are no-ops, a different line counts, and the cap stops the feed and says so", () => {
  const feed = core.liveFeed(3);
  const [a, b, c, d] = buildLines(v1Chain.envelopes, {})[0];
  assert.equal(feed.add([a, b]), 2);
  assert.equal(feed.add([a, b, a]), 0);
  assert.equal(feed.add([`${a} `]), 1, "not byte-identical, so it is a new line (verification then counts it once)");
  assert.equal(feed.truncated, false);
  assert.equal(feed.repeats, 3);
  assert.equal(feed.add([c, d]), 0);
  assert.equal(feed.truncated, true);
  assert.equal(feed.items.length, 3);
});

// ── V18 and the replay cap: transport limits, before anything is parsed ─────────────────────────────────────────
// The vector file's response rule (run-view-vectors.mjs buildResponse).
function buildResponse(build) {
  if (build.lines !== undefined) return "{}\n".repeat(build.lines);
  const lines = [];
  let left = build.bytes;
  while (left > 0) {
    const size = Math.min(65_536, left);
    lines.push(`${"x".repeat(size - 1)}\n`);
    left -= size;
  }
  return lines.join("");
}
for (const spec of viewFile.transport) {
  test(`V18 transport: ${spec.name}`, () => {
    const text = buildResponse(spec.build);
    core.resetCounters();
    const got = core.parseApiResponse(text);
    assert.equal(got.ok, spec.expect.ok);
    assert.equal(got.reason, spec.expect.reason);
    const theirs = ref.parseApiResponse(text);
    assert.equal(got.ok, theirs.ok);
    assert.equal(got.reason, theirs.reason);
    if (got.ok) assert.deepEqual(got.lines, theirs.lines);
    assert.deepEqual(core.counters, { parse: 0, canonical: 0, hash: 0, verify: 0 });
  });
}
test("V18: a rejected response leaves the prefix unchanged and counts the poll as failed (the page's sequence)", async () => {
  const options = coreOptions(v1Chain.view);
  const tracker = core.progressTracker();
  const feed = core.liveFeed();
  feed.add(core.parseApiResponse(buildLines(v1Chain.envelopes, {})[0].map((line) => `${line}\n`).join("")).lines);
  let verification = await core.verifyChecked(feed.items, options);
  tracker.poll({ nowMs: BASE_MS, ok: true, K: verification.prefix_end });
  for (const [t, build] of [[1, { lines: 257 }], [2, { bytes: 4 * 1024 * 1024 + 1 }]]) {
    const response = core.parseApiResponse(buildResponse(build));
    assert.equal(response.ok, false, `at ${t} s the response was accepted`);
    tracker.poll({ nowMs: BASE_MS + t * 1000, ok: false });
  }
  verification = await core.verifyChecked(feed.items, options);
  assert.equal(verification.prefix_end, 11);
  assert.equal(tracker.state().K, 11);
  assert.equal(tracker.state().last_poll_ok_ms, BASE_MS, "a rejected response is not a good poll");
  assert.equal(tracker.mode("api", BASE_MS + 5_000), "LIVE");
  assert.equal(tracker.mode("api", BASE_MS + 6_000), "STALE");
});
test("readBodyCapped: a response over the cap is never fully read; one at the cap is read whole", async () => {
  const cap = core.MAX_API_BYTES;
  const exact = await core.readBodyCapped(new Response(buildResponse({ bytes: cap })), cap, "response_too_large");
  assert.equal(exact.ok, true);
  assert.equal(bytes(exact.text), cap);
  const over = await core.readBodyCapped(new Response(buildResponse({ bytes: cap + 1 })), cap, "response_too_large");
  assert.deepEqual(over, { ok: false, reason: "response_too_large" });
  // An endless body: reading stops just past the cap and cancels the stream.
  let pulled = 0, cancelled = false;
  const endless = new ReadableStream({
    pull(controller) { pulled += 1; controller.enqueue(new Uint8Array(64 * 1024).fill(0x78)); },
    cancel() { cancelled = true; },
  });
  const stopped = await core.readBodyCapped(new Response(endless), cap, "response_too_large");
  assert.deepEqual(stopped, { ok: false, reason: "response_too_large" });
  assert.ok(cancelled && pulled <= cap / (64 * 1024) + 2, `pulled ${pulled} chunks`);
});
test("readReplayFile: a file over 64 MiB is refused before parsing; a small one splits into lines like the reference", () => {
  core.resetCounters();
  const big = core.readReplayFile("x".repeat(64 * 1024 * 1024 + 1));
  assert.deepEqual(big, { ok: false, reason: "file_too_large" });
  assert.equal(core.counters.parse, 0);
  const text = `${buildLines(v1Chain.envelopes, {})[0].join("\r\n")}\r\n\n${"x"}\n`;
  assert.deepEqual(core.readReplayFile(text), ref.readReplayFile(text));
  assert.equal(core.readReplayFile(text).lines.length, 13, "a blank line in the middle stays a line (a malformed row)");
});
test("utf8Length counts UTF-8 bytes as Buffer.byteLength does, lone surrogates included", () => {
  for (const s of ["", "abc", "é°C", "😀", "\ud800", "x\udc00y", "\ud83d", "\ude00\ud83d", "Ａ😀\u0000", "€".repeat(1000)]) {
    assert.equal(core.utf8Length(s), bytes(s), JSON.stringify(s));
  }
  assert.ok(core.utf8Length("€".repeat(1000), 10) > 10, "with a limit it stops above the limit");
});
test("canonicalSize equals the canonical byte length for every vector envelope, without calling canonical()", () => {
  const all = [...viewFile.chains.flatMap((c) => c.envelopes), ...viewFile.live.flatMap((l) => l.envelopes)];
  core.resetCounters();
  for (const env of all) assert.equal(core.canonicalSize(env), bytes(refCanonical(env)), env.event.event_id);
  assert.equal(core.counters.canonical, 0);
});

// ── mode, hashing ─────────────────────────────────────────────────────────────────────────────────────────────
test(`mode() and modeLabel(): all ${viewFile.mode.length} vector cases`, () => {
  for (const c of viewFile.mode) {
    assert.equal(core.mode(c.source, c.last_poll_ok_ms, c.last_progress_ms, c.now_ms), c.expect, c.note);
    assert.equal(core.modeLabel(c.source, c.last_poll_ok_ms, c.last_progress_ms, c.now_ms), c.label, c.note);
  }
});
test("hashing: absent, undefined and null values hash as the vectors say; the JSON round trip fails; genesis as the rule says", async () => {
  for (const spec of viewFile.hashing) {
    assert.equal(await core.hashEnvelope(spec.envelope), spec.hash_values_absent);
    assert.equal(await core.hashEnvelope({ ...spec.envelope, values: undefined }), spec.hash_values_undefined);
    assert.equal(await core.hashEnvelope({ ...spec.envelope, values: null }), spec.hash_values_null);
    const received = JSON.parse(JSON.stringify(ref.signEnvelope({ ...spec.envelope, values: undefined }, testKey("core").privateKey, "core")));
    const row = (await core.verifyChain([received], coreOptions(v1Chain.view))).rows[0];
    assert.deepEqual(row.reasons, spec.round_trip_reasons);
  }
  assert.equal(await core.genesis("run-v1"), ref.genesis("run-v1"));
  assert.equal(v1Chain.envelopes[0].prev_hash, await core.genesis("run-v1"));
});
test("verifying refuses to run without the run_id the view requested", async () => {
  await assert.rejects(core.verifyChain(v1Chain.envelopes, { pins: nodePins(v1Chain.view), keys: rawKeys(v1Chain.view) }), /run_id/);
});
test("robustness: a junk envelope is a malformed row after the others, and the projection is unchanged", async () => {
  const r = await core.verifyChain([...structuredClone(v1Chain.envelopes), { junk: true }], coreOptions(v1Chain.view));
  assert.equal(r.rows.length, 12);
  assert.deepEqual([r.rows[11].status, r.rows[11].seq], ["malformed", null]);
  assert.ok(same(r.projection, v1Chain.result.projection));
});
test("robustness: a verified event that project() can't read gives an error state, not a throw", async () => {
  const entries = v1Chain.input.entries.map((e) => structuredClone(e));
  entries.push({ event: { event_id: "v1-e12", seq: 12, type: "support.add", actor_role: "core", body: { node: "K1", set_id: "x", members: "M1" } }, ts: "2026-10-31T12:00:12.000Z", actor: { agent_id: null, life_id: null, lab: "core", grant_id: null } });
  const chain = ref.makeChain(v1Chain.input.run, entries, v1Chain.input.values, { key_id: "core", privateKey: testKey("core").privateKey });
  const r = await core.verifyChain(chain, coreOptions(v1Chain.view));
  assert.equal(r.rows.at(-1).status, "verified");
  assert.equal(r.projection, null);
  assert.equal(r.projection_error, "project_threw");
});

// ── keys and pins ─────────────────────────────────────────────────────────────────────────────────────────────
const browserVerify = (envelopes, view, pins = nodePins(view)) => core.verifyChain(structuredClone(envelopes), coreOptions(view, pins));
test("the browser derives the same test keys as the vectors' rule", async () => {
  for (const name of ["core", "forger"]) {
    const raw = await core.publicKeyFromSeedText(`sentilab-view-test-key:${name}`);
    assert.deepEqual([...raw], [...testKey(name).raw], name);
    assert.equal((await core.keySha256(raw)).slice(0, 8), viewFile.test_keys[name].key_sha256_prefix, name);
  }
});
test("the production pins are well-formed, frozen and never a derivable test key", () => {
  assert.ok(Array.isArray(VIEW_PINS));
  assert.ok(Object.isFrozen(VIEW_PINS));
  const testHashes = new Set(["core", "forger", "lab", "gate"].map((name) => testKey(name).sha256));
  for (const pin of VIEW_PINS) {
    assert.ok(Object.isFrozen(pin));
    assert.deepEqual(Object.keys(pin).sort(), ["key_id", "key_sha256"]);
    assert.match(pin.key_sha256, /^[0-9a-f]{64}$/);
    assert.equal(pin.key_id, `sha256:${pin.key_sha256}`, "key_id is the sha256 of the raw public key, as in trust.key_id_for");
    assert.ok(!testHashes.has(pin.key_sha256), "a test key is never a production pin");
  }
  const flightPins = JSON.parse(readFileSync(join(dirname(fileURLToPath(import.meta.url)), "../public/trust-pins.json"), "utf8"));
  assert.deepEqual(VIEW_PINS.map((p) => p.key_id).sort(), flightPins.map((p) => p.key_id).sort(), "one service key in both registries");
  for (const pin of flightPins) {
    assert.equal(createHash("sha256").update(Buffer.from(pin.public_key_hex, "hex")).digest("hex"), pin.key_id.slice(7));
  }
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
  // The key comes with the data (as a forged bundle would ship it), but the page doesn't pin it.
  const v1 = viewFile.chains[0];
  const keys = core.parseKeyResponse({ key_id: "core", public_key: Buffer.from(testKey("core").raw).toString("hex") });
  const r = await core.verifyChain(structuredClone(v1.envelopes), { runId: "run-v1", pins: VIEW_PINS, keys });
  assert.ok(r.rows.every((row) => row.status === "unverified" && row.reasons.includes("key_not_pinned")));
});
test("under the production pins, a chain signed with a derivable key under a production key_id never verifies", async () => {
  // A forger who knows the production key_id signs with a test key and serves that key under the same id.
  const forger = testKey("forger");
  for (const pin of VIEW_PINS) {
    const forged = ref.makeChain(v1Chain.input.run, v1Chain.input.entries, v1Chain.input.values, { key_id: pin.key_id, privateKey: forger.privateKey });
    const r = await core.verifyChain(forged, { runId: "run-v1", pins: VIEW_PINS, keys: { [pin.key_id]: forger.raw } });
    assert.ok(r.rows.every((row) => same(row.reasons, ["key_hash_mismatch"])), pin.key_id);
    assert.equal(r.prefix_end, 0);
  }
});
test("an EMPTY pin registry verifies nothing: every row is 'no pinned key', even with the right key served", async () => {
  const r = await core.verifyChain(structuredClone(v1Chain.envelopes), { runId: "run-v1", pins: [], keys: rawKeys(v1Chain.view) });
  assert.ok(r.rows.every((row) => same(row.reasons, ["key_not_pinned"])));
  assert.equal(r.prefix_end, 0);
  assert.deepEqual(r.projection.nodes, {});
  assert.deepEqual(chainSummary(r.rows).phrases, ["no pinned key"]);
});

// ── the demo fixture ─────────────────────────────────────────────────────────────────────────────────────────
const demoText = readFileSync(DEMO_PATH, "utf8");
const demoLines = core.readReplayFile(demoText).lines;
const testPins = [{ key_id: "core", key_sha256: testKey("core").sha256 }];
const testKeys = { core: testKey("core").raw };
const KEY_REASONS = new Set(["key_not_pinned", "key_unavailable", "key_hash_mismatch"]);

test("demo-run.jsonl is reproducible from its generator (v0.5 reference makeChain, core TEST key)", () => {
  assert.equal(buildDemo().jsonl, demoText);
  assert.equal(demoLines.length, 44);
  assert.ok(demoLines.every((line) => JSON.parse(line).v === "view-envelope/0.5"));
  assert.ok(demoLines.every((line) => core.checkLine(line).ok), "every demo line passes the input checks");
});
test("demo under the production pins: nothing verifies (the demo is signed with a TEST key), nothing is projected", async () => {
  const r = await core.verifyJsonl(demoLines, { runId: DEMO_RUN.run_id, pins: VIEW_PINS, keys: {} });
  assert.ok(r.rows.every((row) => row.status === "unverified" && row.reasons.length === 1 && KEY_REASONS.has(row.reasons[0])));
  assert.equal(r.prefix_end, 0);
  assert.equal(r.label, "chain broken after seq 0; board frozen at seq 0");
  assert.deepEqual(r.projection.nodes, {});
  assert.equal(chainSummary(r.rows).verified, 0);
  const view = buildView(r, r.rows.length);
  assert.equal(view.trustedCount, 0);
  assert.equal(view.cards.length, 0);
  assert.equal(view.board.current, null);
  assert.equal(feedRows(r, r.rows.length).length, 44, "every envelope is still listed");
});
test("demo under an empty pin list: every row 'no pinned key'", async () => {
  const r = await core.verifyJsonl(demoLines, { runId: DEMO_RUN.run_id, pins: [], keys: {} });
  assert.ok(r.rows.every((row) => same(row.reasons, ["key_not_pinned"])));
  assert.deepEqual(chainSummary(r.rows).phrases, ["no pinned key"]);
});
test("demo under TEST keys: 44/44 verified, and the reference agrees", async () => {
  const r = await core.verifyJsonl(demoLines, { runId: DEMO_RUN.run_id, pins: testPins, keys: testKeys });
  assert.equal(r.chain_ok, true);
  assert.equal(r.prefix_end, 44);
  assert.equal(r.frozen, false);
  const theirs = ref.verifyJsonl(demoLines, { runId: DEMO_RUN.run_id, pins: testPins, keys: { core: testKey("core").publicKey } });
  assert.ok(same(refFields(r), theirs));
});
test("demo story: one acceptance, one valid loser, and the drill's stale and surviving nodes come from project()", async () => {
  const r = await core.verifyJsonl(demoLines, { runId: DEMO_RUN.run_id, pins: testPins, keys: testKeys });
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
  assert.ok(isDrill(r.ordered));

  const end = buildView(r, r.rows.length);
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
test("a broken chain freezes the panels at the prefix (V3 tamper, V8 dropped event, V10 padded line, V13 conflict)", async () => {
  for (const [name, k] of [["V3", 3], ["V8", 6], ["V10", 3], ["V13", 0]]) {
    const chain = viewFile.chains.find((c) => c.name.split(" ")[0] === name);
    const r = await core.verifyJsonl(buildLines(chain.envelopes, chain.send)[0], coreOptions(chain.view));
    const view = buildView(r, r.rows.length);
    assert.equal(view.trustedCount, r.prefix);
    assert.deepEqual(view.broken, { afterSeq: k }, chain.name);
    assert.ok(same(view.projection, r.projection), "the panels show exactly the prefix projection");
    const rows = feedRows(r, r.rows.length);
    assert.equal(rows.length, r.rows.length);
    assert.ok(rows.slice(r.prefix).every((row) => row.projected === false));
  }
});
test("the feed shows a rejected row by its reasons only, and the badge counts it", async () => {
  const chain = viewFile.chains.find((c) => c.name.startsWith("V10"));
  const r = await core.verifyJsonl(buildLines(chain.envelopes, chain.send)[0], coreOptions(chain.view));
  const rows = feedRows(r, r.rows.length);
  const last = rows.at(-1);
  assert.deepEqual([last.kind, last.seq, last.projected], ["oversize", null, false]);
  assert.match(last.text, /^rejected before hashing: line over 64 KiB/);
  assert.equal(r.ordered.at(-1), null, "the page holds no envelope for it");
  const sum = chainSummary(r.rows);
  assert.equal(sum.rejected, 1);
  assert.equal(sum.verified, 9);
});
