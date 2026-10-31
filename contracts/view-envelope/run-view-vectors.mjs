// Builds and checks the view-envelope vectors (DRAFT v0.4).
//   node run-view-vectors.mjs           regenerate every vector from the code and compare with vectors-view.json
//   node run-view-vectors.mjs --write   rewrite vectors-view.json from the code, then run the same checks
// Exit 0 only if every check passes.
import { createHash, createPrivateKey, createPublicKey, verify } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { canonical } from "../contract-0.2/resultcheck.mjs";
import { project } from "../contract-0.2/evidence-projection.mjs";
import { checkCaps, genesis, hashEnvelope, keySha256, makeChain, mode, signEnvelope, verifyChain } from "./view-envelope.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const FILE = join(here, "vectors-view.json");
const CONTRACT_SHA256 = "6a1eb6421f726f1b67f0bcace9dd32322bd472babb30a89c68a69be4e0df4d56";
const sha256 = (text) => createHash("sha256").update(text, "utf8").digest("hex");
const same = (a, b) => canonical(a) === canonical(b);

// ---- Test keys. Derived at run time from a public rule; no key material is stored anywhere. ----
// seed = sha256("sentilab-view-test-key:" + name). The private key is PKCS8 DER: a fixed 16-byte
// Ed25519 header followed by the 32-byte seed.
const PKCS8_ED25519_HEADER = Buffer.from("302e020100300506032b657004220420", "hex");
const seedFor = (name) => createHash("sha256").update(`sentilab-view-test-key:${name}`, "utf8").digest();
const keyCache = new Map();
function testKey(name) {
  if (!keyCache.has(name)) {
    const privateKey = createPrivateKey({ key: Buffer.concat([PKCS8_ED25519_HEADER, seedFor(name)]), format: "der", type: "pkcs8" });
    keyCache.set(name, { privateKey, publicKey: createPublicKey(privateKey) });
  }
  return keyCache.get(name);
}
// Written separately from view-envelope.mjs on purpose: the raw key is the 32 bytes after the 12-byte SPKI header.
const rawKeyHash = (publicKey) => createHash("sha256").update(publicKey.export({ type: "spki", format: "der" }).subarray(12)).digest("hex");
const resolvePins = (view) => view.pins.map((pin) => ({ key_id: pin.key_id, key_sha256: rawKeyHash(testKey(pin.test_key).publicKey) }));
const resolveKeys = (view) => Object.fromEntries(Object.entries(view.served_keys).map(([id, name]) => [id, testKey(name).publicKey]));
const verifyFor = (envelopes, view) => verifyChain(envelopes, { runId: view.run_id, pins: resolvePins(view), keys: resolveKeys(view) });

// ---- Scenario building blocks. Fixed ids and timestamps, so everything is deterministic. ----
const BASE_MS = Date.UTC(2026, 9, 31, 12, 0, 0);
const T = (seconds) => new Date(BASE_MS + seconds * 1000).toISOString();
const CORE = { agent_id: null, life_id: null, lab: "core", grant_id: null };
const GATE = { agent_id: null, life_id: null, lab: "gate", grant_id: null };
const LAB_A = { agent_id: "agent-lab-a-01", life_id: "life-lab-a-0001", lab: "lab-a", grant_id: "grant-lab-a-0001" };
const SEMANTICS = { task_contract: "tc-thermal-2.5d-v1", metric_id: "peak-temp-c", evaluator_version: "hotspot-ref-6.0", coordinate_frame: "pkg-lower-left-mm" };
const GEOMETRY = [
  { id: "c0", xLL: 0, yLL: 0, w: 10, h: 10, layer: 0 },
  { id: "c1", xLL: 12, yLL: 0, w: 10, h: 10, layer: 0 },
  { id: "c2", xLL: 0, yLL: 12, w: 10, h: 8.5, layer: 0 },
  { id: "c3", xLL: 12, yLL: 12, w: 10, h: 8.5, layer: 1 },
];
const TEMPS = { c0: 71.5, c1: 78.25, c2: 69.125, c3: 74 };
const artifact = (name) => sha256(`artifact:${name}`);
const id = (prefix, position) => `${prefix}-e${String(position).padStart(2, "0")}`;
const run = (runId, arm, seed) => ({ run_id: runId, arm, family: "fam-micro150", seed, ticket_id: `ticket-${runId}` });

// Steps get event_id by position and seq by position unless a step gives its own seq.
function entries(prefix, steps) {
  return steps.map((step, index) => {
    const seq = step.seq ?? index + 1;
    return { event: { event_id: id(prefix, index + 1), seq, type: step.type, actor_role: step.role, body: step.body }, ts: step.ts ?? T(seq), actor: step.actor };
  });
}
// Roles (v0.3 and later): labs write proposals, the core writes evaluation and reproduction, the gate writes board outcomes.
const core = (type, body, extra = {}) => ({ type, role: "core", actor: CORE, body, ...extra });
const gate = (body) => ({ type: "lifecycle.transition", role: "acceptance_gate", actor: GATE, body });

// A lab proposes K, the core evaluates it with measurement M and reproduces M with R, and the gate writes `final`.
function happySteps({ K, M, R, final }) {
  return [
    { type: "node.create", role: "lab", actor: LAB_A, body: { id: K, kind: "candidate" } },
    core("lifecycle.transition", { node: K, to: "validated" }),
    core("lifecycle.transition", { node: K, to: "simulation_pending" }),
    core("node.create", { id: M, kind: "measurement", semantics: SEMANTICS }),
    core("support.add", { node: K, set_id: "eval", members: [M] }),
    core("lifecycle.transition", { node: K, to: "evaluated" }),
    core("lifecycle.transition", { node: K, to: "reproduction_pending" }),
    core("node.create", { id: R, kind: "measurement", semantics: SEMANTICS }),
    core("verify.add", { node: M, tier: "replayed", evidence: [R] }),
    core("lifecycle.transition", { node: K, to: "reproduced" }),
    gate({ node: K, to: final }),
  ];
}
const candidateValues = () => ({ geometry: GEOMETRY, units: "mm", scenario_id: "scn-01" });
const measurementValues = (prefix, J = 78.25, temps = TEMPS) => ({
  scenario_id: "scn-01", J: { value: J, unit: "°C" }, W: { value: 1840.5, metric_id: "hpwl-mm" }, center_temps: temps,
  artifact_hashes: [artifact(`${prefix}:hotspot.ptrace`), artifact(`${prefix}:hotspot.steady`)],
});
const replayValues = (prefix, J = 78.25) => ({ scenario_id: "scn-01", J: { value: J, unit: "°C" }, center_temps: TEMPS, artifact_hashes: [artifact(`${prefix}:replay.steady`)] });
function happyValues(prefix, J = 78.25, temps = TEMPS) {
  return {
    [id(prefix, 1)]: candidateValues(),
    [id(prefix, 4)]: measurementValues(prefix, J, temps),
    [id(prefix, 8)]: measurementValues(`${prefix}-r`, J),
    [id(prefix, 9)]: replayValues(prefix, J),
  };
}
const CORE_SIGNER = { test_key: "core", key_id: "core" };
const coreView = (runId) => ({ run_id: runId, pins: [{ key_id: "core", test_key: "core" }], served_keys: { core: "core" } });
const allIds = (prefix, n) => Array.from({ length: n }, (_, i) => id(prefix, i + 1));
const NODES_ACCEPTED = {
  K1: { lifecycle: "accepted", accepted_ever: true, validity: "valid", support_status: { eval: "valid" } },
  M1: { validity: "valid", tiers: ["replayed"] },
  R1: { validity: "valid" },
};
// The board of a happy run frozen at seq 3: K1 is proposed, validated and simulation_pending, with no support yet.
const NODES_AT_SEQ3 = { K1: { lifecycle: "simulation_pending", accepted_ever: false, validity: "unverified", support_status: {} } };
const happy = { K: "K1", M: "M1", R: "R1", final: "accepted" };
// Rule 1's label, as the contract words it.
const frozenAt = (k) => ({ prefix_end: k, frozen: true, label: `chain broken after seq ${k}; board frozen at seq ${k}` });
const whole = (k) => ({ prefix_end: k, frozen: false, label: null });

// Each chain vector: input (what the core wrote), view (the run the view requested, what the page pins and
// what keys it was served), and expect (hand-written). In expect, `unverified` lists every row that must be
// unverified; every other row must be verified with no reasons. prefix_end, frozen and label are rule 1's;
// a row is projected exactly when it and every row before it is expected verified and not oversize.
// `nodes` is a subset of the projection, `absent_nodes` must not be in it, and `no_acceptance` means no node
// may show as accepted.
function chainSpecs() {
  const specs = [];

  specs.push({
    name: "V1 normal run: a lab proposes, the core evaluates, a measurement is added and reproduced, the gate accepts",
    input: { run: run("run-v1", "live", 1), signer: CORE_SIGNER, append_checks: true, entries: entries("v1", happySteps(happy)), values: happyValues("v1") },
    view: coreView("run-v1"),
    expect: { rows: 11, chain_ok: true, ...whole(11), unverified: {}, oversize: {}, nodes: NODES_ACCEPTED, absent_nodes: [], rejected: [] },
  });

  const drill = [
    { type: "node.create", role: "lab", actor: LAB_A, body: { id: "K2", kind: "candidate" } },
    core("node.create", { id: "MA", kind: "measurement", semantics: SEMANTICS }),
    core("node.create", { id: "MB", kind: "measurement", semantics: SEMANTICS }),
    core("node.create", { id: "CMP", kind: "comparison", semantics: SEMANTICS }),
    core("support.add", { node: "CMP", set_id: "s", members: ["MA"] }),
    core("node.create", { id: "C2", kind: "claim" }),
    core("support.add", { node: "C2", set_id: "via_a", members: ["MA"] }),
    core("support.add", { node: "C2", set_id: "via_b", members: ["MB"] }),
    // ts runs backwards here on purpose: ts is display only and never orders (rule 2).
    core("support.add", { node: "K2", set_id: "eval", members: ["MA"] }, { ts: T(6.5) }),
    core("withdraw", { node: "MA", reason: "drill: thermocouple fault" }),
  ];
  specs.push({
    name: "V2 correction drill: a measurement is withdrawn, its dependents go stale, the alternative support set stays valid",
    input: {
      run: run("run-v2-drill", "B1", 2), signer: CORE_SIGNER, append_checks: true, entries: entries("v2", drill),
      values: { [id("v2", 1)]: candidateValues(), [id("v2", 2)]: measurementValues("v2-a"), [id("v2", 3)]: measurementValues("v2-b", 77.5) },
    },
    view: coreView("run-v2-drill"),
    expect: {
      rows: 10, chain_ok: true, ...whole(10), unverified: {}, oversize: {}, absent_nodes: [], rejected: [],
      nodes: {
        MA: { validity: "withdrawn" },
        MB: { validity: "valid" },
        CMP: { validity: "stale", stale_because: ["MA"] },
        K2: { lifecycle: "proposed", validity: "stale", stale_because: ["MA"] },
        C2: { validity: "valid", stale_because: [], support_status: { via_a: "broken", via_b: "valid" } },
      },
    },
  });

  // The first break is seq 4, so the board freezes at seq 3. Seqs 5 to 10 verify but are never projected.
  specs.push({
    name: "V3 tamper: seq 4 has a value changed after signing; seq 11 is a validly signed envelope from a fork, so its prev_hash is wrong",
    input: {
      run: run("run-v3", "live", 3), signer: CORE_SIGNER, append_checks: true, entries: entries("v3", happySteps(happy)), values: happyValues("v3"),
      after_signing: [{ seq: 4, path: ["values", "J", "value"], value: 71.75 }],
      replace_from_fork: { fork_seq: 10, fork_ts: T(10.5), take_seq: 11 },
    },
    view: coreView("run-v3"),
    expect: {
      rows: 11, chain_ok: false, ...frozenAt(3), oversize: {}, nodes: NODES_AT_SEQ3, absent_nodes: ["M1", "R1"], rejected: [],
      unverified: { [id("v3", 4)]: ["hash_mismatch", "bad_sig"], [id("v3", 11)]: ["prev_hash_mismatch"] },
    },
  });

  specs.push({
    name: "V4 valid loser: reproduced, then the gate writes non_improving_current; valid and not accepted",
    input: { run: run("run-v4", "B3", 4), signer: CORE_SIGNER, append_checks: true, entries: entries("v4", happySteps({ K: "K4", M: "M4", R: "R4", final: "non_improving_current" })), values: happyValues("v4", 80) },
    view: coreView("run-v4"),
    expect: {
      rows: 11, chain_ok: true, ...whole(11), unverified: {}, oversize: {}, absent_nodes: [], rejected: [],
      nodes: { K4: { lifecycle: "non_improving_current", accepted_ever: false, validity: "valid" }, M4: { validity: "valid", tiers: ["replayed"] } },
    },
  });

  specs.push({
    name: "V5a forged replay: signed by forger, the manifest serves forger's key under key_id forger; pins are core only",
    input: { run: run("run-v5a", "live", 5), signer: { test_key: "forger", key_id: "forger" }, append_checks: true, entries: entries("v5a", happySteps(happy)), values: happyValues("v5a") },
    view: { run_id: "run-v5a", pins: [{ key_id: "core", test_key: "core" }], served_keys: { forger: "forger" } },
    expect: {
      rows: 11, chain_ok: false, ...frozenAt(0), oversize: {}, nodes: {}, absent_nodes: ["K1", "M1", "R1"], rejected: [], no_acceptance: true,
      unverified: Object.fromEntries(allIds("v5a", 11).map((eid) => [eid, ["key_not_pinned"]])),
    },
  });
  specs.push({
    name: "V5b forged replay: signed by forger under key_id core, and forger's key is served under that id; pins are core only",
    input: { run: run("run-v5b", "live", 5), signer: { test_key: "forger", key_id: "core" }, append_checks: true, entries: entries("v5b", happySteps(happy)), values: happyValues("v5b") },
    view: { run_id: "run-v5b", pins: [{ key_id: "core", test_key: "core" }], served_keys: { core: "forger" } },
    expect: {
      rows: 11, chain_ok: false, ...frozenAt(0), oversize: {}, nodes: {}, absent_nodes: ["K1", "M1", "R1"], rejected: [], no_acceptance: true,
      unverified: Object.fromEntries(allIds("v5b", 11).map((eid) => [eid, ["key_hash_mismatch"]])),
    },
  });

  // A faulty writer skips seq 4. prev_hash still links, so the seq rule is the only thing that catches it.
  // The board freezes at seq 3; seq 6 verifies against seq 5 but is after the break.
  const gapSteps = happySteps({ K: "K6", M: "M6", R: "R6", final: "accepted" }).slice(0, 5).map((step, i) => ({ ...step, seq: [1, 2, 3, 5, 6][i] }));
  specs.push({
    name: "V6a seq gap: seqs 1, 2, 3, 5, 6 with an intact prev_hash chain",
    input: { run: run("run-v6a", "B2", 6), signer: CORE_SIGNER, append_checks: false, entries: entries("v6a", gapSteps), values: { [id("v6a", 1)]: candidateValues(), [id("v6a", 4)]: measurementValues("v6a") } },
    view: coreView("run-v6a"),
    expect: {
      rows: 5, chain_ok: false, ...frozenAt(3), oversize: {}, unverified: { [id("v6a", 4)]: ["seq_gap"] },
      nodes: { K6: { lifecycle: "simulation_pending", validity: "unverified" } }, absent_nodes: ["M6"], rejected: [],
    },
  });

  // A faulty writer gives seq 3 to two different events. prev_hash still links. The board freezes at the first
  // seq 3; the repeat and everything after it are shown but not projected.
  const base6 = happySteps({ K: "K6", M: "M6", R: "R6", final: "accepted" });
  const repeatSteps = [base6[0], base6[1], base6[2], core("lifecycle.transition", { node: "K6", to: "cancelled" }, { seq: 3 }), { ...base6[3], seq: 4 }, { ...base6[4], seq: 5 }];
  specs.push({
    name: "V6b seq repeat: seqs 1, 2, 3, 3, 4, 5 with an intact prev_hash chain",
    input: { run: run("run-v6b", "B2", 6), signer: CORE_SIGNER, append_checks: false, entries: entries("v6b", repeatSteps), values: { [id("v6b", 1)]: candidateValues(), [id("v6b", 5)]: measurementValues("v6b") } },
    view: coreView("run-v6b"),
    expect: {
      rows: 6, chain_ok: false, ...frozenAt(3), oversize: {}, unverified: { [id("v6b", 4)]: ["seq_repeat"] },
      nodes: { K6: { lifecycle: "simulation_pending", validity: "unverified" } }, absent_nodes: ["M6"], rejected: [],
    },
  });

  // Oversize ends the prefix: the board freezes at seq 3, and the authentic seqs 5 to 11 are shown but not projected.
  const temps65 = Object.fromEntries(Array.from({ length: 65 }, (_, i) => [`c${String(i).padStart(2, "0")}`, 60 + i * 0.25]));
  specs.push({
    name: "V7 oversize: seq 4 has 65 center_temps entries; it is authentic but oversize, so the board freezes at seq 3 and later rows are shown but not projected",
    input: { run: run("run-v7", "live", 7), signer: CORE_SIGNER, append_checks: false, entries: entries("v7", happySteps(happy)), values: happyValues("v7", 78.25, temps65) },
    view: coreView("run-v7"),
    expect: {
      rows: 11, chain_ok: true, ...frozenAt(3), unverified: {}, oversize: { [id("v7", 4)]: ["too_many_entries:center_temps"] },
      nodes: NODES_AT_SEQ3, absent_nodes: ["M1", "R1"], rejected: [],
    },
  });

  // The core signs seq 1..10, and the withdraw at seq 7 is left out of the file. Seq 8 fails only on the chain
  // (its seq and prev_hash point at the missing 7); 9 and 10 verify outright. Nothing after 6 is projected.
  const dropSteps = [
    { type: "node.create", role: "lab", actor: LAB_A, body: { id: "K8", kind: "candidate" } },
    core("node.create", { id: "M8", kind: "measurement", semantics: SEMANTICS }),
    core("support.add", { node: "K8", set_id: "eval", members: ["M8"] }),
    core("lifecycle.transition", { node: "K8", to: "validated" }),
    core("lifecycle.transition", { node: "K8", to: "simulation_pending" }),
    core("lifecycle.transition", { node: "K8", to: "evaluated" }),
    core("withdraw", { node: "M8", reason: "thermocouple fault" }),
    core("lifecycle.transition", { node: "K8", to: "reproduction_pending" }),
    core("lifecycle.transition", { node: "K8", to: "reproduced" }),
    gate({ node: "K8", to: "accepted" }),
  ];
  specs.push({
    name: "V8 dropped event: seq 1..10 signed, the withdraw at seq 7 left out of the file; the board equals project() over seq 1..6",
    input: {
      run: run("run-v8", "live", 8), signer: CORE_SIGNER, append_checks: true, entries: entries("v8", dropSteps),
      values: { [id("v8", 1)]: candidateValues(), [id("v8", 2)]: measurementValues("v8") }, drop_seqs: [7],
    },
    view: coreView("run-v8"),
    expect: {
      rows: 9, chain_ok: false, ...frozenAt(6), oversize: {}, unverified: { [id("v8", 8)]: ["seq_gap", "prev_hash_mismatch"] },
      nodes: { K8: { lifecycle: "evaluated", accepted_ever: false, validity: "valid", support_status: { eval: "valid" } }, M8: { validity: "valid" } },
      absent_nodes: [], rejected: [], no_acceptance: true,
      dropped: { board_seqs: [1, 6], after: [id("v8", 8), id("v8", 9), id("v8", 10)], skipping_would_accept: "K8" },
    },
  });

  // Not in the contract's vector list; it covers the rule that the run_id comes from the view, not the file.
  specs.push({
    name: "V9 wrong run: a complete, validly signed chain for run-v9-other, served when the view asked for run-v9",
    input: { run: run("run-v9-other", "live", 9), signer: CORE_SIGNER, append_checks: true, entries: entries("v9", happySteps(happy)), values: happyValues("v9") },
    view: coreView("run-v9"),
    expect: {
      rows: 11, chain_ok: false, ...frozenAt(0), oversize: {}, nodes: {}, absent_nodes: ["K1", "M1", "R1"], rejected: [], no_acceptance: true,
      unverified: Object.fromEntries(allIds("v9", 11).map((eid, i) => [eid, i === 0 ? ["run_mismatch", "prev_hash_mismatch"] : ["run_mismatch"]])),
    },
  });
  return specs;
}

// Builds the envelopes for a chain input. Everything here is driven by the input, so the file is self-describing.
function buildEnvelopes(input) {
  const signer = { key_id: input.signer.key_id, privateKey: testKey(input.signer.test_key).privateKey };
  const options = { appendChecks: input.append_checks };
  const envelopes = structuredClone(makeChain(input.run, input.entries, input.values, signer, options));
  for (const change of input.after_signing ?? []) {
    let target = envelopes.find((env) => env.event.seq === change.seq);
    for (const key of change.path.slice(0, -1)) target = target[key];
    target[change.path.at(-1)] = change.value;
  }
  if (input.replace_from_fork) {
    const { fork_seq, fork_ts, take_seq } = input.replace_from_fork;
    const forkEntries = input.entries.map((entry) => (entry.event.seq === fork_seq ? { ...entry, ts: fork_ts } : entry));
    const fork = makeChain(input.run, forkEntries, input.values, signer, options);
    envelopes[envelopes.findIndex((env) => env.event.seq === take_seq)] = structuredClone(fork.find((env) => env.event.seq === take_seq));
  }
  return envelopes.filter((env) => !(input.drop_seqs ?? []).includes(env.event.seq));
}

// ---- Independent re-derivation of the run, hash, chain, seq and signature rules and of the projectable prefix,
// using only the contract text, canonical(), project(), node:crypto and the hand-written oversize list.
// It shares no code with view-envelope.mjs. ----
function oracle(envelopes, view, expect) {
  const pins = resolvePins(view);
  const served = resolveKeys(view);
  const sorted = envelopes.map((env, i) => [env, i]).sort((a, b) => a[0].event.seq - b[0].event.seq || a[1] - b[1]).map(([env]) => env);
  const statuses = sorted.map((env, i) => {
    const prev = sorted[i - 1];
    const { sig, hash, ...covered } = env;
    const pin = pins.find((p) => p.key_id === sig.key_id);
    const key = served[sig.key_id];
    const ok = env.v === "view-envelope/0.4" && env.run.run_id === view.run_id &&
      sha256(canonical(covered)) === hash &&
      env.prev_hash === (prev ? prev.hash : sha256(`sentilab-view-genesis:${view.run_id}`)) &&
      env.event.seq === (prev ? prev.event.seq + 1 : 1) &&
      Boolean(pin && key && rawKeyHash(key) === pin.key_sha256) && sig.alg === "ed25519" &&
      verify(null, Buffer.from(hash, "utf8"), key, Buffer.from(sig.value, "hex"));
    return { event_id: env.event.event_id, status: ok ? "verified" : "unverified" };
  });
  let prefix = 0;
  while (prefix < sorted.length && statuses[prefix].status === "verified" && !Object.hasOwn(expect.oversize, sorted[prefix].event.event_id)) prefix += 1;
  return { statuses, prefix_end: prefix === 0 ? 0 : sorted[prefix - 1].event.seq, projection: project(sorted.slice(0, prefix).map((env) => env.event)) };
}

function subset(actual, expected, path) {
  if (expected === null || typeof expected !== "object") return actual === expected ? [] : [`${path}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`];
  if (Array.isArray(expected)) return same(actual, expected) ? [] : [`${path}: expected ${canonical(expected)}, got ${canonical(actual)}`];
  if (actual === null || typeof actual !== "object") return [`${path}: expected an object, got ${JSON.stringify(actual)}`];
  if (Object.keys(expected).length === 0 && Object.keys(actual).length > 0) return [`${path}: expected empty, got ${canonical(actual)}`];
  return Object.keys(expected).flatMap((key) => subset(actual[key], expected[key], `${path}.${key}`));
}
function checkExpect(result, expect) {
  const errors = [];
  if (result.rows.length !== expect.rows) errors.push(`expected ${expect.rows} rows, got ${result.rows.length}`);
  if (result.chain_ok !== expect.chain_ok) errors.push(`chain_ok: expected ${expect.chain_ok}, got ${result.chain_ok}`);
  for (const key of ["prefix_end", "frozen", "label"]) if (result[key] !== expect[key]) errors.push(`${key}: expected ${JSON.stringify(expect[key])}, got ${JSON.stringify(result[key])}`);
  let inPrefix = true;
  for (const row of result.rows) {
    inPrefix = inPrefix && !Object.hasOwn(expect.unverified, row.event_id) && !Object.hasOwn(expect.oversize, row.event_id);
    if (row.projected !== inPrefix) errors.push(`${row.event_id}: projected should be ${inPrefix}`);
  }
  for (const row of result.rows) {
    const want = expect.unverified[row.event_id];
    if (want && (row.status !== "unverified" || !same(row.reasons, want))) errors.push(`${row.event_id}: expected unverified ${canonical(want)}, got ${row.status} ${canonical(row.reasons)}`);
    if (!want && (row.status !== "verified" || row.reasons.length > 0)) errors.push(`${row.event_id}: expected verified, got ${row.status} ${canonical(row.reasons)}`);
    const caps = expect.oversize[row.event_id] ?? [];
    if (!same(row.oversize, caps)) errors.push(`${row.event_id}: expected oversize ${canonical(caps)}, got ${canonical(row.oversize)}`);
  }
  for (const eid of Object.keys(expect.unverified)) if (!result.rows.some((row) => row.event_id === eid)) errors.push(`${eid}: no row`);
  if (result.projection_error !== null) errors.push(`projection_error ${result.projection_error}`);
  if (!result.projection) return [...errors, "no projection"];
  errors.push(...subset(result.projection.nodes, expect.nodes, "nodes"));
  for (const node of expect.absent_nodes) if (Object.hasOwn(result.projection.nodes, node)) errors.push(`${node} should not be in the projection`);
  if (!same(result.projection.rejected, expect.rejected)) errors.push(`rejected: expected ${canonical(expect.rejected)}, got ${canonical(result.projection.rejected)}`);
  return errors;
}

// ---- Mode (rule 5). Ages are measured back from now_ms on the client clock; a negative age is a future time. ----
const NOW = BASE_MS + 120_000;
function modeSpecs() {
  const at = (age) => (age === null ? null : NOW - age);
  const c = (source, pollAge, arrivalAge, expect, note) => ({ source, last_poll_ok_ms: at(pollAge), last_verified_arrival_ms: at(arrivalAge), now_ms: NOW, expect, note });
  return [
    c("api", 1_000, 2_000, "LIVE", "a poll succeeded 1 s ago and a verified envelope arrived 2 s ago"),
    c("api", 5_000, 60_000, "LIVE", "both limits are inclusive"),
    c("api", 5_001, 2_000, "STALE", "the last good poll was over 5 s ago"),
    c("api", 30_000, 2_000, "STALE", "polling is failing"),
    c("api", 1_000, 60_001, "STALE", "polling works, but no verified envelope for over 60 s"),
    c("api", 1_000, null, "STALE", "before the first envelope"),
    c("api", null, null, "STALE", "before the first poll"),
    c("api", 1_000, -3_600_000, "STALE", "an arrival time an hour in the future, e.g. a forged envelope ts passed by mistake, never makes LIVE"),
    c("api", -1_000, 2_000, "STALE", "a poll time in the future never makes LIVE"),
    c("file", 1_000, 2_000, "REPLAY", "a file is REPLAY whatever the times"),
    c("file", null, null, "REPLAY", "a file is REPLAY whatever the times"),
  ];
}

// ---- Caps. Base is the V1 envelope at seq 4 (a measurement). Small cases store the whole envelope;
// the two 64 KiB boundary cases store how to build it plus its canonical byte count and sha256. ----
function padTo(base, target) {
  const env = structuredClone(base);
  env.values = { ...env.values, artifact_hashes: Array.from({ length: 64 }, () => "a".repeat(512)), geometry: Array.from({ length: 64 }, (_, i) => ({ id: `g${i}`, xLL: 0, yLL: 0, w: 1, h: 1, layer: 0 })) };
  let missing = target - Buffer.byteLength(canonical(env), "utf8");
  for (const entry of env.values.geometry) {
    const add = Math.max(0, Math.min(missing, 512 - entry.id.length));
    entry.id += "x".repeat(add);
    missing -= add;
  }
  if (missing !== 0) throw new Error(`can't pad to ${target} bytes`);
  return env;
}
const PAD_BUILD = "Start from the V1 envelope at seq 4. Set values.artifact_hashes to 64 strings of 512 'a', and values.geometry to 64 entries {id:'g<i>',xLL:0,yLL:0,w:1,h:1,layer:0}. Then append 'x' to geometry ids in order, each up to 512 characters, until canonical(envelope) is exactly target_bytes.";
// n nested objects: {"d":{"d":...{}}}.
const nest = (n) => { let x = {}; for (let i = 1; i < n; i += 1) x = { d: x }; return x; };
function capsSpecs(base) {
  const withValues = (patch) => ({ ...structuredClone(base), values: { ...structuredClone(base.values), ...patch } });
  const temps = (n) => Object.fromEntries(Array.from({ length: n }, (_, i) => [`c${String(i).padStart(2, "0")}`, 70]));
  const geometry = (n) => Array.from({ length: n }, (_, i) => ({ id: `g${i}`, xLL: i, yLL: 0, w: 1, h: 1, layer: 0 }));
  const hashes = (n) => Array.from({ length: n }, (_, i) => artifact(`cap:${i}`));
  const keyed = (key) => withValues({ center_temps: { [key]: 70 } });
  const depthNote = "values.nest is not a real field; it only adds depth. The envelope is level 1 and values level 2, so nest's objects take levels 3 and up";
  const cases = [
    { name: "64 center_temps entries is within the cap", envelope: withValues({ center_temps: temps(64) }), expect: [] },
    { name: "65 center_temps entries", envelope: withValues({ center_temps: temps(65) }), expect: ["too_many_entries:center_temps"] },
    { name: "64 geometry entries is within the cap", envelope: withValues({ geometry: geometry(64) }), expect: [] },
    { name: "65 geometry entries", envelope: withValues({ geometry: geometry(65) }), expect: ["too_many_entries:geometry"] },
    { name: "65 artifact_hashes entries", envelope: withValues({ artifact_hashes: hashes(65) }), expect: ["too_many_entries:artifact_hashes"] },
    { name: "a 512-character string is within the cap", envelope: withValues({ scenario_id: "s".repeat(512) }), expect: [] },
    { name: "a 513-character string", envelope: withValues({ scenario_id: "s".repeat(513) }), expect: ["string_too_long"] },
    { name: "512 two-byte characters (1,024 UTF-8 bytes) is within the cap: characters, not bytes", envelope: withValues({ scenario_id: "é".repeat(512) }), expect: [] },
    { name: "512 astral characters (1,024 UTF-16 units) is within the cap: code points, not UTF-16 units", envelope: withValues({ scenario_id: "😀".repeat(512) }), expect: [] },
    { name: "a 513-character object key counts as a string", envelope: keyed("k".repeat(513)), expect: ["string_too_long"] },
    { name: "8 levels of nesting is within the cap", envelope: withValues({ nest: nest(6) }), expect: [], note: depthNote },
    { name: "9 levels of nesting", envelope: withValues({ nest: nest(7) }), expect: ["too_deep"], note: depthNote },
    { name: "a number that parses to Infinity (1e999 in the JSONL line)", raw: canonical(base).replace('"value":78.25', '"value":1e999'), expect: ["non_finite_number"] },
  ];
  for (const target of [65_536, 65_537]) {
    const env = padTo(base, target);
    cases.push({ name: `exactly ${target.toLocaleString("en-US")} canonical bytes`, build: PAD_BUILD, target_bytes: target, canonical_sha256: sha256(canonical(env)), expect: target > 65_536 ? ["too_large"] : [] });
  }
  return cases;
}
const capsEnvelope = (spec, base) => (spec.envelope ?? (spec.raw !== undefined ? JSON.parse(spec.raw) : padTo(base, spec.target_bytes)));

// ---- Absent vs undefined vs null. The hashes are computed here with sha256(canonical()) directly, not with
// hashEnvelope, so the check below tests the module against them. ----
function hashingSpecs(v1First) {
  const { sig, hash, values, ...base } = v1First;
  const h = (env) => sha256(canonical(env));
  return [{
    name: "values absent, undefined and null: undefined and null both canonicalize to null, so neither hashes like absent",
    envelope: base,
    hash_values_absent: h(base),
    hash_values_undefined: h({ ...base, values: undefined }),
    hash_values_null: h({ ...base, values: null }),
    round_trip: "sign the envelope with values: undefined in memory, then JSON.stringify and JSON.parse it, which drops the key",
    round_trip_reasons: ["hash_mismatch", "bad_sig"],
  }];
}

// ---- canonical() examples from v0.3 and later (equal to RFC 8785 JCS for these). Hand-written expectations. ----
const CANONICAL_SPECS = [
  { name: "keys sorted, no whitespace, 5.0 written as 5", raw: '{ "b": 1, "a": 5.0 }', canonical: '{"a":5,"b":1}' },
  { name: "numbers in shortest round-trip form", raw: "[1e16, 1e21, 0.1, -0.0, 1E2, 2.50]", canonical: "[10000000000000000,1e+21,0.1,0,100,2.5]" },
  { name: "keys sorted by UTF-16 code units: U+1F600 (D83D DE00) sorts before U+FF21", raw: '{"\\uff21":1,"\\ud83d\\ude00":2}', canonical: '{"😀":2,"Ａ":1}' },
  { name: "strings as JSON.stringify: non-ASCII stays as is, control characters are escaped", raw: '"°C\\u00e9\\n\\u001f"', canonical: '"°Cé\\n\\u001f"' },
];

// ---- The whole vector file, from code. ----
function generate() {
  const chains = chainSpecs().map((spec) => {
    const envelopes = buildEnvelopes(spec.input);
    return { ...spec, envelopes, result: verifyFor(envelopes, spec.view) };
  });
  const base = chains[0].envelopes.find((env) => env.event.seq === 4);
  return {
    description: "Test vectors for the SentiLab view envelope, DRAFT v0.4 (view-envelope-0.4.md). Generated by `node run-view-vectors.mjs --write` and checked by `node run-view-vectors.mjs`. Each chain gives the core's input, the run the view requested, what the page pins and what keys it was served, the envelopes, a hand-written expect block, and the full verifyChain() result.",
    contract_sha256: CONTRACT_SHA256,
    rules: {
      canonical: "canonical() from ../contract-0.2/resultcheck.mjs; for these values it equals RFC 8785 (JCS). Absent fields are omitted, never undefined or null",
      hash: "sha256(canonical(envelope without sig and hash)), lowercase hex, recomputed from the content by the verifier",
      prev_hash: "the stored hash of the previous envelope by seq; the first is sha256(\"sentilab-view-genesis:\" + the run_id the view requested)",
      run: "an envelope whose run.run_id differs from the run the view requested is run_mismatch",
      sig: "Ed25519 over the 64 hex characters of the recomputed hash as UTF-8; sig.value is lowercase hex, 128 characters",
      seq: "1, 2, 3, ... in seq order; equal to the previous is seq_repeat, anything else is seq_gap; only that envelope is flagged",
      key_sha256: "sha256 of the raw 32-byte Ed25519 public key (the last 32 bytes of its SPKI DER), lowercase hex",
      projection: "the projectable prefix is the longest run from seq 1 of rows that are verified and not oversize; prefix_end K is its last seq (0 if none); the board is project() over exactly those events; each row has projected true or false; when anything follows the prefix, frozen is true and label is \"chain broken after seq K; board frozen at seq K\", otherwise frozen is false and label is null; if project() throws, projection is null and projection_error is project_threw",
      mode: "api: LIVE when a poll succeeded within 5 s and a verified envelope arrived within 60 s (client clock, inclusive, never in the future), otherwise STALE; file: REPLAY",
      roles: "actor_role is lab, core or acceptance_gate; actor.lab gate goes with acceptance_gate; only the gate writes accepted, non_improving_current and within_margin",
      test_keys: "seed = sha256(\"sentilab-view-test-key:\" + name) (32 bytes); private key = Ed25519 from that seed, i.e. PKCS8 DER 302e020100300506032b657004220420 || seed",
      after_signing: "set the value at path in the envelope with that seq, after it was signed",
      replace_from_fork: "build the same chain with entry fork_seq's ts set to fork_ts, then put that chain's envelope take_seq in place of ours",
      append_checks: "false means a faulty writer: makeChain skips the checks the core makes on append",
      drop_seqs: "sign the whole chain, then leave the envelopes with these seqs out of the file",
    },
    test_keys: Object.fromEntries(["core", "forger"].map((name) => [name, { key_sha256_prefix: rawKeyHash(testKey(name).publicKey).slice(0, 8) }])),
    reason_codes: {
      malformed: "required fields missing or the wrong type, or the hash can't be computed",
      bad_version: "v is not view-envelope/0.4",
      run_mismatch: "run.run_id differs from the run the view requested",
      seq_gap: "seq is not the previous seq + 1 (or not 1 for the first)",
      seq_repeat: "seq equals the previous seq",
      prev_hash_mismatch: "prev_hash is not the previous envelope's stored hash (or the genesis value)",
      hash_mismatch: "the stored hash is not the hash recomputed from the content",
      key_not_pinned: "sig.key_id is not among the page's pins",
      key_unavailable: "pinned, but no key was served for that key_id",
      key_hash_mismatch: "the served key's sha256 doesn't match the pin",
      bad_alg: "sig.alg is not ed25519",
      bad_sig: "the signature doesn't verify over the recomputed hash",
    },
    cap_codes: {
      too_large: "canonical(envelope) is over 65,536 bytes (not evaluated when too_deep)",
      "too_many_entries:<field>": "over 64 entries in values.geometry, values.center_temps or values.artifact_hashes",
      string_too_long: "a string or object key over 512 code points",
      non_finite_number: "a number that is NaN or infinite",
      too_deep: "an object or array below level 8, counting the envelope as level 1",
      malformed: "canonical() can't serialize the envelope",
    },
    chains,
    mode: modeSpecs(),
    caps: capsSpecs(base),
    hashing: hashingSpecs(chains[0].envelopes[0]),
    canonical: CANONICAL_SPECS,
  };
}

// Indented JSON, except that each envelope, entry, result row, projection node and caps envelope sits on
// one line, the way a JSONL replay file holds envelopes. Formatting only; the checks compare parsed JSON.
function format(vectors) {
  const inline = [];
  const mark = (value) => `@@inline-${inline.push(JSON.stringify(value)) - 1}@@`;
  const marked = {
    ...vectors,
    chains: vectors.chains.map((chain) => ({
      ...chain,
      input: { ...chain.input, entries: chain.input.entries.map(mark) },
      envelopes: chain.envelopes.map(mark),
      result: {
        ...chain.result,
        rows: chain.result.rows.map(mark),
        projection: chain.result.projection && { ...chain.result.projection, nodes: Object.fromEntries(Object.entries(chain.result.projection.nodes).map(([k, v]) => [k, mark(v)])) },
      },
    })),
    caps: vectors.caps.map((spec) => (spec.envelope ? { ...spec, envelope: mark(spec.envelope) } : spec)),
    hashing: vectors.hashing.map((spec) => ({ ...spec, envelope: mark(spec.envelope) })),
  };
  return `${JSON.stringify(marked, null, 2).replace(/"@@inline-(\d+)@@"/g, (_, i) => inline[Number(i)])}\n`;
}

// ---- Checks. ----
const results = [];
function check(name, fn) {
  let errors;
  try { errors = fn(); } catch (error) { errors = [`threw ${error.name}: ${error.message}`]; }
  results.push({ name, errors });
  console.log(errors.length === 0 ? `PASS  ${name}` : `FAIL  ${name}: ${errors.slice(0, 4).join("; ")}${errors.length > 4 ? ` (+${errors.length - 4} more)` : ""}`);
}
const expectThrow = (fn, pattern) => {
  try { fn(); } catch (error) { return pattern.test(error.message) ? [] : [`threw the wrong error: ${error.message}`]; }
  return ["did not throw"];
};

if (process.argv.includes("--write")) {
  writeFileSync(FILE, format(generate()));
  console.log(`wrote ${FILE}`);
}
const file = JSON.parse(readFileSync(FILE, "utf8"));
const fresh = generate();
const coreKey = testKey("core");

check("file: same top-level content as the generator (rules, keys, codes)", () =>
  ["description", "contract_sha256", "rules", "test_keys", "reason_codes", "cap_codes"].filter((k) => !same(file[k], fresh[k])).map((k) => `${k} differs`));
check("file: same chain, mode, caps, hashing and canonical vectors as the generator", () => {
  const names = (o) => [o.chains.map((c) => c.name), o.mode.length, o.caps.map((c) => c.name), o.hashing.map((c) => c.name), o.canonical.map((c) => c.name)];
  return same(names(file), names(fresh)) ? [] : ["vector list differs"];
});

for (const [index, vector] of file.chains.entries()) {
  const label = vector.name.split(":")[0];
  const generated = fresh.chains[index];
  check(`${label}: input, view and expect match the generator`, () =>
    ["name", "input", "view", "expect"].filter((k) => !same(vector[k], generated?.[k])).map((k) => `${k} differs`));
  check(`${label}: envelopes regenerate byte-identically from the file's input`, () => {
    const rebuilt = buildEnvelopes(vector.input);
    if (rebuilt.length !== vector.envelopes.length) return [`${rebuilt.length} envelopes, file has ${vector.envelopes.length}`];
    return rebuilt.flatMap((env, i) => (same(env, vector.envelopes[i]) ? [] : [`envelope ${i} (seq ${env.event.seq}) differs`]));
  });
  const result = verifyFor(vector.envelopes, vector.view);
  check(`${label}: verifyChain over the file's envelopes equals the recorded result`, () => {
    if (same(result, vector.result)) return [];
    const diffs = result.rows.flatMap((row, i) => (same(row, vector.result.rows[i]) ? [] : [`row ${i}: ${canonical(row)}`]));
    for (const key of ["chain_ok", "prefix_end", "frozen", "label"]) if (result[key] !== vector.result[key]) diffs.push(`${key} ${JSON.stringify(result[key])}`);
    if (!same(result.projection, vector.result.projection)) diffs.push("projection differs");
    return diffs.length ? diffs : ["differs"];
  });
  check(`${label}: the hand-written expectations hold`, () => checkExpect(result, vector.expect));
  check(`${label}: an independent re-derivation agrees on every status, the prefix and the projection`, () => {
    const theirs = oracle(vector.envelopes, vector.view, vector.expect);
    const errors = result.rows.flatMap((row, i) => (row.status === theirs.statuses[i]?.status ? [] : [`${row.event_id}: verifyChain says ${row.status}, the rules say ${theirs.statuses[i]?.status}`]));
    if (result.prefix_end !== theirs.prefix_end) errors.push(`prefix_end: verifyChain says ${result.prefix_end}, the rules say ${theirs.prefix_end}`);
    if (!same(result.projection, theirs.projection)) errors.push("projection differs from project() over the projectable prefix");
    return errors;
  });
  if (vector.expect.no_acceptance) {
    check(`${label}: the claimed acceptance never appears on the board`, () => {
      const shown = Object.entries(result.projection?.nodes ?? {}).filter(([, node]) => node.accepted_ever || node.lifecycle === "accepted").map(([nodeId]) => nodeId);
      return result.projection && shown.length === 0 ? [] : [`shown as accepted: ${shown.join(", ") || "(no projection)"}`];
    });
  }
  const dropped = vector.expect.dropped;
  if (dropped) {
    const [from, to] = dropped.board_seqs;
    check(`${label}: the board equals project() over seq ${from}..${to} exactly`, () => {
      const events = vector.envelopes.filter((env) => env.event.seq >= from && env.event.seq <= to).map((env) => env.event);
      return events.length === to - from + 1 && same(result.projection, project(events)) ? [] : ["the board is not project() over that range"];
    });
    check(`${label}: envelopes after the gap carry a valid hash and core signature, and none is projected`, () => dropped.after.flatMap((eid) => {
      const env = vector.envelopes.find((e) => e.event.event_id === eid);
      const { sig, hash, ...covered } = env;
      const errors = sha256(canonical(covered)) === hash && verify(null, Buffer.from(hash, "utf8"), coreKey.publicKey, Buffer.from(sig.value, "hex")) ? [] : [`${eid}: hash or signature invalid`];
      return result.rows.find((row) => row.event_id === eid).projected ? [...errors, `${eid} is projected`] : errors;
    }));
    check(`${label}: skipping the dropped event would show ${dropped.skipping_would_accept} accepted; the full history rejects that acceptance`, () => {
      const all = vector.input.entries.map((entry) => entry.event);
      const skipped = project(all.filter((event) => !vector.input.drop_seqs.includes(event.seq)));
      const full = project(all);
      const node = dropped.skipping_would_accept;
      const errors = skipped.nodes[node]?.lifecycle === "accepted" ? [] : ["skipping the dropped event doesn't show the acceptance"];
      if (full.nodes[node]?.accepted_ever !== false || !full.rejected.some((r) => r.code === "unsupported_acceptance")) errors.push("the full history should reject the acceptance");
      return errors;
    });
  }
  if (new Set(vector.envelopes.map((env) => env.event.seq)).size === vector.envelopes.length) {
    check(`${label}: delivery order doesn't change the result`, () => (same(verifyFor([...vector.envelopes].reverse(), vector.view), result) ? [] : ["reversed input gave a different result"]));
  }
}

check(`mode: ${file.mode.length} cases (rule 5)`, () => {
  const errors = file.mode.flatMap((c) => {
    const got = mode(c.source, c.last_poll_ok_ms, c.last_verified_arrival_ms, c.now_ms);
    return got === c.expect ? [] : [`${c.note}: expected ${c.expect}, got ${got}`];
  });
  if (!same(file.mode, fresh.mode)) errors.push("mode cases differ from the generator");
  return errors;
});

const capsBase = file.chains[0].envelopes.find((env) => env.event.seq === 4);
for (const [index, spec] of file.caps.entries()) {
  check(`caps: ${spec.name}`, () => {
    const errors = same(spec, fresh.caps[index]) ? [] : ["differs from the generator"];
    const env = capsEnvelope(spec, capsBase);
    if (spec.target_bytes !== undefined) {
      const bytes = Buffer.byteLength(canonical(env), "utf8");
      if (bytes !== spec.target_bytes) errors.push(`built ${bytes} bytes`);
      if (sha256(canonical(env)) !== spec.canonical_sha256) errors.push("built envelope has a different sha256");
    }
    const got = checkCaps(env);
    if (!same(got.reasons, spec.expect) || got.ok !== (spec.expect.length === 0)) errors.push(`expected ${canonical(spec.expect)}, got ${canonical(got)}`);
    return errors;
  });
}

for (const [index, spec] of file.hashing.entries()) {
  check(`hashing: ${spec.name}`, () => {
    const errors = same(spec, fresh.hashing[index]) ? [] : ["differs from the generator"];
    const base = spec.envelope;
    if (hashEnvelope(base) !== spec.hash_values_absent) errors.push("hashEnvelope differs for values absent");
    if (hashEnvelope({ ...base, values: undefined }) !== spec.hash_values_undefined) errors.push("hashEnvelope differs for values: undefined");
    if (hashEnvelope({ ...base, values: null }) !== spec.hash_values_null) errors.push("hashEnvelope differs for values: null");
    if (spec.hash_values_absent === spec.hash_values_undefined) errors.push("absent and undefined hash the same");
    if (spec.hash_values_absent === spec.hash_values_null) errors.push("absent and null hash the same");
    if (spec.hash_values_undefined !== spec.hash_values_null) errors.push("undefined and null should both canonicalize to null");
    const signed = signEnvelope({ ...base, values: undefined }, coreKey.privateKey, "core");
    const received = JSON.parse(JSON.stringify(signed));
    if (Object.hasOwn(received, "values")) errors.push("JSON kept the undefined key");
    const row = verifyChain([received], { runId: base.run.run_id, pins: resolvePins(file.chains[0].view), keys: resolveKeys(file.chains[0].view) }).rows[0];
    if (!same(row.reasons, spec.round_trip_reasons)) errors.push(`round trip: expected ${canonical(spec.round_trip_reasons)}, got ${canonical(row.reasons)}`);
    return errors;
  });
}
for (const [index, spec] of file.canonical.entries()) {
  check(`canonical: ${spec.name}`, () => {
    const errors = same(spec, fresh.canonical[index]) ? [] : ["differs from the generator"];
    const got = canonical(JSON.parse(spec.raw));
    return got === spec.canonical ? errors : [...errors, `expected ${spec.canonical}, got ${got}`];
  });
}

// Checks that don't fit the vector format.
const v1 = file.chains[0];
const v1Signer = { key_id: "core", privateKey: coreKey.privateKey };
const v1Entries = v1.input.entries;
const withEntry = (seq, change) => v1Entries.map((e) => (e.event.seq === seq ? change(structuredClone(e)) : e));
const appendV1 = (entries, values = v1.input.values) => makeChain(v1.input.run, entries, values, v1Signer);
check("keys: each test key's PKCS8 seed round-trips and its SPKI is 44 bytes", () => ["core", "forger"].flatMap((name) => {
  const { privateKey, publicKey } = testKey(name);
  const errors = [];
  if (privateKey.export({ format: "jwk" }).d !== seedFor(name).toString("base64url")) errors.push(`${name}: seed doesn't round-trip`);
  if (publicKey.export({ type: "spki", format: "der" }).length !== 44) errors.push(`${name}: SPKI is not 44 bytes`);
  if (keySha256(publicKey) !== rawKeyHash(publicKey)) errors.push(`${name}: keySha256 disagrees with the raw-key rule`);
  if (rawKeyHash(publicKey).slice(0, 8) !== file.test_keys[name].key_sha256_prefix) errors.push(`${name}: key_sha256 prefix differs from the file`);
  return errors;
}));
check("hashing: hash ignores sig and hash, and genesis is sha256 of the prefixed run_id", () => {
  const env = v1.envelopes[0];
  const { sig, hash, ...bare } = env;
  const errors = [];
  if (hashEnvelope(env) !== env.hash || hashEnvelope(bare) !== env.hash) errors.push("hashEnvelope depends on sig or hash");
  if (genesis("run-v1") !== sha256("sentilab-view-genesis:run-v1") || env.prev_hash !== genesis("run-v1")) errors.push("genesis differs");
  if (env.v !== "view-envelope/0.4") errors.push(`v is ${env.v}`);
  return errors;
});
check("run: verifyChain refuses to run without the run_id the view requested", () => expectThrow(() => verifyChain(v1.envelopes, { pins: resolvePins(v1.view), keys: resolveKeys(v1.view) }), /run_id/));
check("pins: rotation, two pinned ids, the chain verifies under the second", () => {
  const pins = [{ key_id: "core-previous", key_sha256: rawKeyHash(testKey("forger").publicKey) }, ...resolvePins(v1.view)];
  return verifyChain(v1.envelopes, { runId: "run-v1", pins, keys: resolveKeys(v1.view) }).chain_ok ? [] : ["chain not ok"];
});
check("pins: a pinned id with no served key is key_unavailable, and nothing is projected", () => {
  const result = verifyChain(v1.envelopes, { runId: "run-v1", pins: resolvePins(v1.view), keys: {} });
  const errors = result.rows.every((row) => same(row.reasons, ["key_unavailable"])) ? [] : ["wrong reasons"];
  return Object.keys(result.projection?.nodes ?? { x: 1 }).length === 0 ? errors : [...errors, "something was projected"];
});
check("robustness: a junk envelope is a malformed row and is not projected", () => {
  const result = verifyFor([...v1.envelopes, { junk: true }], v1.view);
  const errors = result.rows.length === 12 && same(result.rows[11].reasons, ["malformed"]) ? [] : ["junk row missing or not malformed"];
  return same(result.projection, v1.result.projection) ? errors : [...errors, "the junk envelope changed the projection"];
});
check("robustness: a verified event that project() can't read gives an error state, not a throw", () => {
  const bodyless = { event: { event_id: "v1-e12", seq: 12, type: "withdraw", actor_role: "core" }, ts: T(12), actor: CORE };
  const result = verifyFor(appendV1([...v1Entries, bodyless]), v1.view);
  const errors = result.rows.at(-1).status === "verified" ? [] : ["the bodyless envelope should verify"];
  return result.projection === null && result.projection_error === "project_threw" ? errors : [...errors, `projection_error is ${result.projection_error}`];
});
check("robustness: 100,000 levels of nesting is too_deep and a row, not a stack overflow", () => {
  const deep = structuredClone(v1.envelopes[0]);
  let inner = {};
  for (let i = 0; i < 100_000; i += 1) inner = { d: inner };
  deep.values.nest = inner;
  const errors = same(checkCaps(deep).reasons, ["too_deep"]) ? [] : [`checkCaps gave ${canonical(checkCaps(deep).reasons)}`];
  const result = verifyFor([deep, ...v1.envelopes.slice(1)], v1.view);
  if (result.rows[0].status !== "unverified" || !same(result.rows[0].oversize, ["too_deep"])) errors.push(`row 0: ${result.rows[0].status} ${canonical(result.rows[0].oversize)}`);
  return errors;
});
check("append: makeChain refuses a seq gap", () => expectThrow(() => appendV1(withEntry(5, (e) => { e.event.seq = 50; return e; })), /seq/));
check("append: makeChain refuses a seq repeat", () => expectThrow(() => appendV1(withEntry(5, (e) => { e.event.seq = 4; return e; })), /seq/));
check("append: makeChain refuses an oversize envelope", () => expectThrow(() => appendV1(v1Entries, { ...v1.input.values, "v1-e04": { center_temps: Object.fromEntries(Array.from({ length: 65 }, (_, i) => [`c${i}`, 1])) } }), /too_many_entries/));
check("append: makeChain refuses NaN, which canonical() would turn into null", () => expectThrow(() => appendV1(v1Entries, { ...v1.input.values, "v1-e04": { J: { value: NaN, unit: "°C" } } }), /non_finite_number/));
check("append: makeChain refuses values on an event that can't carry them", () => expectThrow(() => appendV1(v1Entries, { ...v1.input.values, "v1-e05": { units: "mm" } }), /can't carry values/));
check("append: makeChain refuses values set to undefined or null", () => [
  ...expectThrow(() => appendV1(v1Entries, { ...v1.input.values, "v1-e04": undefined }), /never undefined or null/),
  ...expectThrow(() => appendV1(v1Entries, { ...v1.input.values, "v1-e04": null }), /never undefined or null/),
]);
check("append: makeChain refuses undefined anywhere in the envelope", () => expectThrow(() => appendV1(withEntry(2, (e) => { e.actor.agent_id = undefined; return e; })), /never undefined/));
check("append: makeChain refuses an actor_role outside lab, core and acceptance_gate", () => expectThrow(() => appendV1(withEntry(2, (e) => { e.event.actor_role = "agent"; return e; })), /not lab, core or acceptance_gate/));
check("append: makeChain refuses a board outcome not written by the gate", () => ["accepted", "non_improving_current", "within_margin"].flatMap((to) =>
  expectThrow(() => appendV1(withEntry(11, (e) => { e.event.actor_role = "core"; e.actor = CORE; e.event.body.to = to; return e; })), /only the gate writes/)));
check("append: makeChain refuses a gate actor without the acceptance_gate role, and the reverse", () => [
  ...expectThrow(() => appendV1(withEntry(11, (e) => { e.event.actor_role = "core"; return e; })), /actor.lab gate goes with/),
  ...expectThrow(() => appendV1(withEntry(2, (e) => { e.event.actor_role = "acceptance_gate"; return e; })), /actor.lab gate goes with/),
]);

const failed = results.filter((r) => r.errors.length > 0).length;
console.log(failed === 0 ? `PASS: ${results.length} of ${results.length} checks` : `FAIL: ${failed} of ${results.length} checks failed`);
const fileSha = (name) => createHash("sha256").update(readFileSync(join(here, name))).digest("hex");
for (const name of ["view-envelope.mjs", "run-view-vectors.mjs", "vectors-view.json"]) console.log(`${fileSha(name)}  ${name}`);
process.exit(failed === 0 ? 0 : 1);
