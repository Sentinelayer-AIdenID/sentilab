// Builds and checks the view-envelope vectors (DRAFT v0.5).
//   node run-view-vectors.mjs           regenerate every vector from the code and compare with vectors-view.json
//   node run-view-vectors.mjs --write   rewrite vectors-view.json from the code, then run the same checks
// Exit 0 only if every check passes.
import { createHash, createPrivateKey, createPublicKey, verify } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { canonical } from "../contract-0.2/resultcheck.mjs";
import { project } from "../contract-0.2/evidence-projection.mjs";
import {
  canonicalSize, counters, genesis, hashEnvelope, keySha256, makeChain, mode, modeLabel,
  parseApiResponse, progressTracker, readReplayFile, resetCounters, signEnvelope, verifyChain, verifyJsonl,
} from "./view-envelope.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const FILE = join(here, "vectors-view.json");
const CONTRACT_SHA256 = "7a92d88aca1e4911a5119dbdff15ad096922dc238a67349e087030d45ad53df6";
const V_STRING = "view-envelope/0.5";
const sha256 = (text) => createHash("sha256").update(text, "utf8").digest("hex");
const same = (a, b) => canonical(a) === canonical(b);
const bytes = (text) => Buffer.byteLength(text, "utf8");

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
const viewOptions = (view) => ({ runId: view.run_id, pins: resolvePins(view), keys: resolveKeys(view) });
const coreKey = testKey("core");
const CORE_SIGNER_KEY = { key_id: "core", privateKey: coreKey.privateKey };

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
// Rows are identified as "seq:event_id", because V14 uses one event_id at two seqs.
const at = (prefix, position, seq = position) => `${seq}:${id(prefix, position)}`;
const run = (runId, arm, seed) => ({ run_id: runId, arm, family: "fam-micro150", seed, ticket_id: `ticket-${runId}` });

// Steps get event_id by position and seq by position unless a step gives its own seq.
function entries(prefix, steps) {
  return steps.map((step, index) => {
    const seq = step.seq ?? index + 1;
    return { event: { event_id: id(prefix, index + 1), seq, type: step.type, actor_role: step.role, body: step.body }, ts: step.ts ?? T(seq), actor: step.actor };
  });
}
// Roles: labs write proposals, the core writes evaluation and reproduction, the gate writes board outcomes.
const core = (type, body, extra = {}) => ({ type, role: "core", actor: CORE, body, ...extra });
const gate = (body) => ({ type: "lifecycle.transition", role: "acceptance_gate", actor: GATE, body });
const propose = (K) => ({ type: "node.create", role: "lab", actor: LAB_A, body: { id: K, kind: "candidate" } });

// A lab proposes K, the core evaluates it with measurement M and reproduces M with R, and the gate writes `final`.
function happySteps({ K, M, R, final }) {
  return [
    propose(K),
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
const allKeys = (prefix, n) => Array.from({ length: n }, (_, i) => at(prefix, i + 1));
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
const none = { unverified: {}, rejected: {}, unreadable: [], absent_nodes: [], project_rejected: [] };

// ---- Chain vectors. input: what the core wrote. send: how the envelopes reach the view as JSONL lines.
// view: the run the view requested, its pins and the keys it was served. expect (hand-written):
//   unverified: rows that pass the input checks but fail the chain or signature checks, with their reasons;
//   rejected: rows that fail the input checks, with status and reasons; unreadable: rejected rows whose seq
//   can't be read, in order; every other row must be verified. A row is projected exactly when it and every
//   row before it is expected verified. nodes is a subset of the projection, absent_nodes must not be in it,
//   and project_rejected is project()'s rejected list. ----
function chainSpecs() {
  const specs = [];
  const add = (spec) => specs.push({ send: {}, ...spec, expect: { ...none, ...spec.expect } });

  add({
    name: "V1 normal run: a lab proposes, the core evaluates, a measurement is added and reproduced, the gate accepts",
    input: { run: run("run-v1", "live", 1), signer: CORE_SIGNER, append_checks: true, entries: entries("v1", happySteps(happy)), values: happyValues("v1") },
    view: coreView("run-v1"),
    expect: { rows: 11, chain_ok: true, ...whole(11), nodes: NODES_ACCEPTED },
  });

  const drill = [
    propose("K2"),
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
  add({
    name: "V2 correction drill: a measurement is withdrawn, its dependents go stale, the alternative support set stays valid",
    input: {
      run: run("run-v2-drill", "B1", 2), signer: CORE_SIGNER, append_checks: true, entries: entries("v2", drill),
      values: { [id("v2", 1)]: candidateValues(), [id("v2", 2)]: measurementValues("v2-a"), [id("v2", 3)]: measurementValues("v2-b", 77.5) },
    },
    view: coreView("run-v2-drill"),
    expect: {
      rows: 10, chain_ok: true, ...whole(10),
      nodes: {
        MA: { validity: "withdrawn" },
        MB: { validity: "valid" },
        CMP: { validity: "stale", stale_because: ["MA"] },
        K2: { lifecycle: "proposed", validity: "stale", stale_because: ["MA"] },
        C2: { validity: "valid", stale_because: [], support_status: { via_a: "broken", via_b: "valid" } },
      },
    },
  });

  add({
    name: "V3 tamper: seq 4 has a value changed after signing; seq 11 is a validly signed envelope from a fork, so its prev_hash is wrong",
    input: {
      run: run("run-v3", "live", 3), signer: CORE_SIGNER, append_checks: true, entries: entries("v3", happySteps(happy)), values: happyValues("v3"),
      after_signing: [{ seq: 4, path: ["values", "J", "value"], value: 71.75 }],
      replace_from_fork: { fork_seq: 10, fork_ts: T(10.5), take_seq: 11 },
    },
    view: coreView("run-v3"),
    expect: {
      rows: 11, chain_ok: false, ...frozenAt(3), nodes: NODES_AT_SEQ3, absent_nodes: ["M1", "R1"],
      unverified: { [at("v3", 4)]: ["hash_mismatch", "bad_sig"], [at("v3", 11)]: ["prev_hash_mismatch"] },
    },
  });

  add({
    name: "V4 valid loser: reproduced, then the gate writes non_improving_current; valid and not accepted",
    input: { run: run("run-v4", "B3", 4), signer: CORE_SIGNER, append_checks: true, entries: entries("v4", happySteps({ K: "K4", M: "M4", R: "R4", final: "non_improving_current" })), values: happyValues("v4", 80) },
    view: coreView("run-v4"),
    expect: { rows: 11, chain_ok: true, ...whole(11), nodes: { K4: { lifecycle: "non_improving_current", accepted_ever: false, validity: "valid" }, M4: { validity: "valid", tiers: ["replayed"] } } },
  });

  add({
    name: "V5a forged replay: signed by forger, the manifest serves forger's key under key_id forger; pins are core only",
    input: { run: run("run-v5a", "live", 5), signer: { test_key: "forger", key_id: "forger" }, append_checks: true, entries: entries("v5a", happySteps(happy)), values: happyValues("v5a") },
    view: { run_id: "run-v5a", pins: [{ key_id: "core", test_key: "core" }], served_keys: { forger: "forger" } },
    expect: {
      rows: 11, chain_ok: false, ...frozenAt(0), nodes: {}, absent_nodes: ["K1", "M1", "R1"], no_acceptance: true,
      unverified: Object.fromEntries(allKeys("v5a", 11).map((key) => [key, ["key_not_pinned"]])),
    },
  });
  add({
    name: "V5b forged replay: signed by forger under key_id core, and forger's key is served under that id; pins are core only",
    input: { run: run("run-v5b", "live", 5), signer: { test_key: "forger", key_id: "core" }, append_checks: true, entries: entries("v5b", happySteps(happy)), values: happyValues("v5b") },
    view: { run_id: "run-v5b", pins: [{ key_id: "core", test_key: "core" }], served_keys: { core: "forger" } },
    expect: {
      rows: 11, chain_ok: false, ...frozenAt(0), nodes: {}, absent_nodes: ["K1", "M1", "R1"], no_acceptance: true,
      unverified: Object.fromEntries(allKeys("v5b", 11).map((key) => [key, ["key_hash_mismatch"]])),
    },
  });

  // A faulty writer skips seq 4. prev_hash still links, so the seq rule is the only thing that catches it.
  const gapSteps = happySteps({ K: "K6", M: "M6", R: "R6", final: "accepted" }).slice(0, 5).map((step, i) => ({ ...step, seq: [1, 2, 3, 5, 6][i] }));
  add({
    name: "V6a seq gap: seqs 1, 2, 3, 5, 6 with an intact prev_hash chain",
    input: { run: run("run-v6a", "B2", 6), signer: CORE_SIGNER, append_checks: false, entries: entries("v6a", gapSteps), values: { [id("v6a", 1)]: candidateValues(), [id("v6a", 4)]: measurementValues("v6a") } },
    view: coreView("run-v6a"),
    expect: { rows: 5, chain_ok: false, ...frozenAt(3), unverified: { [at("v6a", 4, 5)]: ["seq_gap"] }, nodes: { K6: { lifecycle: "simulation_pending", validity: "unverified" } }, absent_nodes: ["M6"] },
  });

  // A faulty writer gives seq 3 to two different events. Under v0.5 that is a seq_conflict on both, so the board
  // freezes before seq 3 (v0.4 projected the first seq 3 and froze at 3). A byte-identical repeat would be a
  // duplicate instead; V15 covers that. The writer chained the second seq 3 after the first, so its prev_hash
  // points at a seq 3 envelope, not at seq 2.
  const base6 = happySteps({ K: "K6", M: "M6", R: "R6", final: "accepted" });
  const repeatSteps = [base6[0], base6[1], base6[2], core("lifecycle.transition", { node: "K6", to: "cancelled" }, { seq: 3 }), { ...base6[3], seq: 4 }, { ...base6[4], seq: 5 }];
  add({
    name: "V6b seq repeat: two different events at seq 3, both signed; a seq_conflict, so the board freezes at seq 2",
    input: { run: run("run-v6b", "B2", 6), signer: CORE_SIGNER, append_checks: false, entries: entries("v6b", repeatSteps), values: { [id("v6b", 1)]: candidateValues(), [id("v6b", 5)]: measurementValues("v6b") } },
    view: coreView("run-v6b"),
    expect: {
      rows: 6, chain_ok: false, ...frozenAt(2), unverified: { [at("v6b", 3)]: ["seq_conflict"], [at("v6b", 4, 3)]: ["seq_conflict", "prev_hash_mismatch"] },
      nodes: { K6: { lifecycle: "validated", validity: "unverified" } }, absent_nodes: ["M6"],
    },
  });

  // An oversize envelope fails the input checks and is never hashed. Its seq can be read, so the board freezes
  // before it. Seq 5 links to its stored hash, so it verifies, but it is after the break.
  const temps65 = Object.fromEntries(Array.from({ length: 65 }, (_, i) => [`c${String(i).padStart(2, "0")}`, 60 + i * 0.25]));
  add({
    name: "V7 oversize: seq 4 has 65 center_temps entries; one oversize row, the board freezes at seq 3, later rows are shown but not projected",
    input: { run: run("run-v7", "live", 7), signer: CORE_SIGNER, append_checks: false, entries: entries("v7", happySteps(happy)), values: happyValues("v7", 78.25, temps65) },
    view: coreView("run-v7"),
    expect: {
      rows: 11, chain_ok: false, ...frozenAt(3), rejected: { [at("v7", 4)]: { status: "oversize", reasons: ["too_many_entries:center_temps"] } },
      nodes: NODES_AT_SEQ3, absent_nodes: ["M1", "R1"],
    },
  });

  const dropSteps = [
    propose("K8"),
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
  add({
    name: "V8 dropped event: seq 1..10 signed, the withdraw at seq 7 left out of the file; the board equals project() over seq 1..6",
    input: {
      run: run("run-v8", "live", 8), signer: CORE_SIGNER, append_checks: true, entries: entries("v8", dropSteps),
      values: { [id("v8", 1)]: candidateValues(), [id("v8", 2)]: measurementValues("v8") }, drop_seqs: [7],
    },
    view: coreView("run-v8"),
    expect: {
      rows: 9, chain_ok: false, ...frozenAt(6), unverified: { [at("v8", 8)]: ["seq_gap", "prev_hash_mismatch"] }, no_acceptance: true,
      nodes: { K8: { lifecycle: "evaluated", accepted_ever: false, validity: "valid", support_status: { eval: "valid" } }, M8: { validity: "valid" } },
      dropped: { board_seqs: [1, 6], after: [id("v8", 8), id("v8", 9), id("v8", 10)], skipping_would_accept: "K8" },
    },
  });

  // Not in the contract's vector list; it covers the rule that the run_id comes from the view, not the file.
  add({
    name: "V9 wrong run: a complete, validly signed chain for run-v9-other, served when the view asked for run-v9",
    input: { run: run("run-v9-other", "live", 9), signer: CORE_SIGNER, append_checks: true, entries: entries("v9", happySteps(happy)), values: happyValues("v9") },
    view: coreView("run-v9"),
    expect: {
      rows: 11, chain_ok: false, ...frozenAt(0), nodes: {}, absent_nodes: ["K1", "M1", "R1"], no_acceptance: true,
      unverified: Object.fromEntries(allKeys("v9", 11).map((key, i) => [key, i === 0 ? ["run_mismatch", "prev_hash_mismatch"] : ["run_mismatch"]])),
    },
  });

  // The line for seq 4 is padded with spaces after its opening brace to 131,761 bytes. It is rejected before
  // parsing, so its seq is unknown and its row comes last; seq 4 is missing, so the board freezes at seq 3.
  add({
    name: "V10 padded line: the valid seq 4 envelope padded with whitespace to a 131,761-byte line; oversize at the raw check, never parsed or hashed",
    input: { run: run("run-v10", "live", 10), signer: CORE_SIGNER, append_checks: true, entries: entries("v10", happySteps(happy)), values: happyValues("v10") },
    send: { pad: { seq: 4, line_bytes: 131_761 } },
    view: coreView("run-v10"),
    expect: {
      rows: 11, chain_ok: false, ...frozenAt(3), unreadable: [{ status: "oversize", reasons: ["line_too_large"] }],
      unverified: { [at("v10", 5)]: ["seq_gap", "prev_hash_mismatch"] }, nodes: NODES_AT_SEQ3, absent_nodes: ["M1", "R1"],
    },
  });

  // A faulty core signs envelopes holding lone surrogates; the view rejects them at the structure check.
  const v11Values = happyValues("v11");
  v11Values[id("v11", 4)].scenario_id = "scn-01\ud800";
  v11Values[id("v11", 8)].center_temps = { ...TEMPS, "c\udc00": 70 };
  add({
    name: "V11 lone surrogates: one in a value (seq 4) and one in a key (seq 8); each row is malformed and never hashed",
    input: { run: run("run-v11", "live", 11), signer: CORE_SIGNER, append_checks: false, entries: entries("v11", happySteps(happy)), values: v11Values },
    view: coreView("run-v11"),
    expect: {
      rows: 11, chain_ok: false, ...frozenAt(3), nodes: NODES_AT_SEQ3, absent_nodes: ["M1", "R1"],
      rejected: { [at("v11", 4)]: { status: "malformed", reasons: ["lone_surrogate"] }, [at("v11", 8)]: { status: "malformed", reasons: ["lone_surrogate"] } },
    },
  });

  // Two different seq 1 envelopes, each validly signed by the core (the second from its own chain).
  const alt = { event: { event_id: "v13-e01-alt", seq: 1, type: "node.create", actor_role: "lab", body: { id: "K13", kind: "candidate" } }, ts: T(0.5), actor: LAB_A };
  const order = ["v13-e01", "v13-e01-alt", "v13-e02", "v13-e03"];
  add({
    name: "V13 conflicting seq 1: two different, validly signed seq 1 envelopes; K = 0 with seq_conflict in both delivery orders",
    input: {
      run: run("run-v13", "live", 13), signer: CORE_SIGNER, append_checks: true, entries: entries("v13", happySteps({ K: "K13", M: "M13", R: "R13", final: "accepted" }).slice(0, 3)),
      values: { [id("v13", 1)]: candidateValues() }, also: [{ entries: [alt], values: { "v13-e01-alt": candidateValues() } }],
    },
    send: { orders: [order, [order[1], order[0], order[2], order[3]]] },
    view: coreView("run-v13"),
    expect: { rows: 4, chain_ok: false, ...frozenAt(0), nodes: {}, absent_nodes: ["K13"], unverified: { [at("v13", 1)]: ["seq_conflict"], "1:v13-e01-alt": ["seq_conflict"] } },
  });

  // A faulty writer reuses the seq 1 event_id at seq 2.
  const v14Entries = entries("v14", happySteps({ K: "K14", M: "M14", R: "R14", final: "accepted" }).slice(0, 3));
  v14Entries[1].event.event_id = id("v14", 1);
  add({
    name: "V14 reused event_id: one event_id at seq 1 and at seq 2, both validly signed; K = 0 with event_id_conflict, never chain_ok",
    input: { run: run("run-v14", "live", 14), signer: CORE_SIGNER, append_checks: false, entries: v14Entries, values: { [id("v14", 1)]: candidateValues() } },
    view: coreView("run-v14"),
    expect: { rows: 3, chain_ok: false, ...frozenAt(0), nodes: {}, absent_nodes: ["K14"], unverified: { [at("v14", 1)]: ["event_id_conflict"], [`2:${id("v14", 1)}`]: ["event_id_conflict"] } },
  });

  add({
    name: "V15 duplicates: every envelope of V1 sent twice, byte-identical; the result is exactly V1's, with no errors",
    input: { run: run("run-v1", "live", 1), signer: CORE_SIGNER, append_checks: true, entries: entries("v1", happySteps(happy)), values: happyValues("v1") },
    send: { twice: true },
    view: coreView("run-v1"),
    expect: { rows: 11, chain_ok: true, ...whole(11), nodes: NODES_ACCEPTED, same_result_as: "V1" },
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
  for (const extra of input.also ?? []) envelopes.push(...structuredClone(makeChain(input.run, extra.entries, extra.values, signer, options)));
  return envelopes.filter((env) => !(input.drop_seqs ?? []).includes(env.event.seq));
}

// The JSONL lines the view receives: one array per delivery order.
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

// ---- Independent re-derivation of the v0.5 rules: raw size, parsing, duplicates, conflicts, run, seq, prev_hash,
// hash, pins, signature and the projectable prefix. It shares no code with view-envelope.mjs, and takes the
// structure-check failures from the hand-written expect.rejected list instead of re-deriving them. ----
function oracle(lines, view, expect) {
  const pins = resolvePins(view);
  const served = resolveKeys(view);
  const rows = [];
  const seen = new Set();
  lines.forEach((line, index) => {
    if (bytes(line) > 65536) { rows.push({ index, ok: false, seq: null, key: null }); return; }
    let env;
    try { env = JSON.parse(line); } catch { rows.push({ index, ok: false, seq: null, key: null }); return; }
    const key = `${env.event.seq}:${env.event.event_id}`;
    if (Object.hasOwn(expect.rejected, key)) { rows.push({ index, ok: false, seq: env.event.seq, key, hash: env.hash }); return; }
    const text = canonical(env);
    if (seen.has(text)) return;
    seen.add(text);
    rows.push({ index, ok: true, env, seq: env.event.seq, key, hash: env.hash });
  });
  const tally = (keyOf) => {
    const counts = new Map();
    for (const row of rows) if (row.ok) counts.set(keyOf(row), (counts.get(keyOf(row)) ?? 0) + 1);
    return (row) => counts.get(keyOf(row)) > 1;
  };
  const seqConflict = tally((row) => `${row.env.run.run_id}|${row.seq}`);
  const idConflict = tally((row) => `${row.env.run.run_id}|${row.env.event.event_id}`);
  rows.sort((a, b) => (a.seq ?? Infinity) - (b.seq ?? Infinity) || (a.ok ? 1 : 0) - (b.ok ? 1 : 0) || (a.ok && a.hash !== b.hash ? (a.hash < b.hash ? -1 : 1) : 0) || a.index - b.index);
  let prevSeq = 0;
  let prevHashes = new Set([sha256(`sentilab-view-genesis:${view.run_id}`)]);
  for (let i = 0; i < rows.length && rows[i].seq !== null;) {
    let j = i;
    while (j < rows.length && rows[j].seq === rows[i].seq) j += 1;
    for (const row of rows.slice(i, j)) if (row.ok) {
      const { sig, hash, ...covered } = row.env;
      const pin = pins.find((p) => p.key_id === sig.key_id);
      const key = served[sig.key_id];
      row.verified = !seqConflict(row) && !idConflict(row) && row.env.v === V_STRING && row.env.run.run_id === view.run_id &&
        row.seq === prevSeq + 1 && prevHashes.has(row.env.prev_hash) && sha256(canonical(covered)) === hash &&
        Boolean(pin && key && rawKeyHash(key) === pin.key_sha256) && verify(null, Buffer.from(hash, "utf8"), key, Buffer.from(sig.value, "hex"));
    }
    prevSeq = rows[i].seq;
    prevHashes = new Set(rows.slice(i, j).map((row) => row.hash).filter(Boolean));
    i = j;
  }
  let prefix = 0;
  while (prefix < rows.length && rows[prefix].verified) prefix += 1;
  return {
    statuses: rows.map((row) => ({ key: row.key, status: !row.ok ? "rejected" : row.verified ? "verified" : "unverified" })),
    prefix_end: prefix === 0 ? 0 : rows[prefix - 1].seq,
    projection: project(rows.slice(0, prefix).map((row) => row.env.event)),
  };
}

function subset(actual, expected, path) {
  if (expected === null || typeof expected !== "object") return actual === expected ? [] : [`${path}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`];
  if (Array.isArray(expected)) return same(actual, expected) ? [] : [`${path}: expected ${canonical(expected)}, got ${canonical(actual)}`];
  if (actual === null || typeof actual !== "object") return [`${path}: expected an object, got ${JSON.stringify(actual)}`];
  if (Object.keys(expected).length === 0 && Object.keys(actual).length > 0) return [`${path}: expected empty, got ${canonical(actual)}`];
  return Object.keys(expected).flatMap((key) => subset(actual[key], expected[key], `${path}.${key}`));
}
const rowKey = (row) => (row.event_id === null ? null : `${row.seq}:${row.event_id}`);
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
    if (row.status !== want.status || !same(row.reasons, want.reasons)) errors.push(`${key ?? "unreadable row"}: expected ${want.status} ${canonical(want.reasons)}, got ${row.status} ${canonical(row.reasons)}`);
    inPrefix = inPrefix && want.status === "verified";
    if (row.projected !== inPrefix) errors.push(`${key}: projected should be ${inPrefix}`);
  }
  if (unreadable.length > 0) errors.push(`${unreadable.length} unreadable rows missing`);
  for (const key of [...Object.keys(expect.rejected), ...Object.keys(expect.unverified)]) if (!result.rows.some((row) => rowKey(row) === key)) errors.push(`${key}: no row`);
  if (result.projection_error !== null) errors.push(`projection_error ${result.projection_error}`);
  if (!result.projection) return [...errors, "no projection"];
  errors.push(...subset(result.projection.nodes, expect.nodes, "nodes"));
  for (const node of expect.absent_nodes) if (Object.hasOwn(result.projection.nodes, node)) errors.push(`${node} should not be in the projection`);
  if (!same(result.projection.rejected, expect.project_rejected)) errors.push(`project rejected: expected ${canonical(expect.project_rejected)}, got ${canonical(result.projection.rejected)}`);
  return errors;
}

// ---- V16 and V17: a client polling the API every second, on the client clock. ----
function liveSpecs() {
  const backlog = [
    propose("K16"),
    core("node.create", { id: "M16", kind: "measurement", semantics: SEMANTICS }),
    core("support.add", { node: "K16", set_id: "eval", members: ["M16"] }),
    core("lifecycle.transition", { node: "K16", to: "validated" }),
    core("lifecycle.transition", { node: "K16", to: "simulation_pending" }),
    core("lifecycle.transition", { node: "K16", to: "evaluated" }),
    core("withdraw", { node: "M16", reason: "thermocouple fault" }),
  ];
  const liveAt = (seconds) => `LIVE · progress ${seconds} s ago`;
  return [
    {
      name: "V16 backlog: a valid next envelope every 30 s while the final signed withdrawal (seq 7) is withheld; LIVE with progress at 0, 30, 60 and 90 s",
      input: { run: run("run-v16", "live", 16), signer: CORE_SIGNER, append_checks: true, entries: entries("v16", backlog), values: { [id("v16", 1)]: candidateValues(), [id("v16", 2)]: measurementValues("v16") } },
      view: coreView("run-v16"),
      schedule: { releases: [{ at_s: 0, seqs: [1, 2, 3] }, { at_s: 30, seqs: [4] }, { at_s: 60, seqs: [5] }, { at_s: 90, seqs: [6] }], withheld_seqs: [7], resend_all: false, polls: { from_s: 0, to_s: 90, every_s: 1 } },
      expect: {
        labels: { 0: liveAt(0), 29: liveAt(29), 30: liveAt(0), 60: liveAt(0), 90: liveAt(0) },
        K: { 0: 3, 30: 4, 60: 5, 90: 6 },
        live_from_s: 0, stale_from_s: null,
        board_at_end: { M16: { validity: "valid" }, K16: { lifecycle: "evaluated", validity: "valid" } },
        full_history: { M16: { validity: "withdrawn" }, K16: { lifecycle: "evaluated", validity: "stale", stale_because: ["M16"] } },
      },
    },
    {
      name: "V17 duplicates only: seq 1..3 at 0 s, then every poll re-sends the same lines; LIVE turns STALE 60 s after K last grew",
      input: { run: run("run-v17", "live", 17), signer: CORE_SIGNER, append_checks: true, entries: entries("v17", happySteps({ K: "K17", M: "M17", R: "R17", final: "accepted" }).slice(0, 3)), values: { [id("v17", 1)]: candidateValues() } },
      view: coreView("run-v17"),
      schedule: { releases: [{ at_s: 0, seqs: [1, 2, 3] }], withheld_seqs: [], resend_all: true, polls: { from_s: 0, to_s: 70, every_s: 1 } },
      expect: { labels: { 0: liveAt(0), 30: liveAt(30), 60: liveAt(60), 61: "STALE", 70: "STALE" }, K: { 0: 3, 70: 3 }, live_from_s: 0, stale_from_s: 61, arrivals_every_poll: true },
    },
  ];
}
function simulate(spec, envelopes) {
  const options = viewOptions(spec.view);
  const tracker = progressTracker();
  const lineOf = new Map(envelopes.map((env) => [env.event.seq, JSON.stringify(env)]));
  const received = [];
  const sent = new Set();
  const timeline = [];
  const { from_s, to_s, every_s } = spec.schedule.polls;
  for (let t = from_s; t <= to_s; t += every_s) {
    const nowMs = BASE_MS + t * 1000;
    const due = spec.schedule.releases.filter((release) => release.at_s <= t).flatMap((release) => release.seqs);
    const batch = spec.schedule.resend_all ? due : due.filter((seq) => !sent.has(seq));
    batch.forEach((seq) => sent.add(seq));
    const response = parseApiResponse(batch.map((seq) => `${lineOf.get(seq)}\n`).join(""));
    if (response.ok) received.push(...response.lines);
    const K = verifyJsonl(received, options).prefix_end;
    tracker.poll({ nowMs, ok: response.ok, K, received: response.ok ? response.lines.length : 0 });
    timeline.push({ t, received: response.ok ? response.lines.length : 0, K, label: tracker.label("api", nowMs) });
  }
  return { timeline, board: verifyJsonl(received, options).projection };
}

// ---- V18: API response caps, checked before parsing. ----
function transportSpecs() {
  return [
    { name: "an API response of 257 lines", build: { lines: 257 }, expect: { ok: false, reason: "too_many_lines" } },
    { name: "256 lines is within the cap", build: { lines: 256 }, expect: { ok: true } },
    { name: "an API response of 4 MiB + 1 byte", build: { bytes: 4 * 1024 * 1024 + 1 }, expect: { ok: false, reason: "response_too_large" } },
    { name: "exactly 4 MiB is within the cap", build: { bytes: 4 * 1024 * 1024 }, expect: { ok: true } },
  ];
}
// Lines of "{}" (lines case), or up to 64 lines of 'x' that add up to exactly `bytes` (bytes case). Every line ends in \n.
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

// ---- V12: each input-check failure, through the raw path (verifyJsonl), the parsed path (verifyChain) and the core
// (makeChain). Base is the V1 envelope at seq 1. "passes" means the input checks pass; a rejected outcome must
// come with zero canonical(), hash, sign and verify calls. ----
const nest = (n) => { let x = {}; for (let i = 1; i < n; i += 1) x = { d: x }; return x; };
function padTo(base, target) {
  const env = structuredClone(base);
  env.values = { ...env.values, artifact_hashes: Array.from({ length: 64 }, () => "a".repeat(512)), geometry: Array.from({ length: 64 }, (_, i) => ({ id: `g${i}`, xLL: 0, yLL: 0, w: 1, h: 1, layer: 0 })) };
  let missing = target - bytes(canonical(env));
  for (const entry of env.values.geometry) {
    const add = Math.max(0, Math.min(missing, 512 - entry.id.length));
    entry.id += "x".repeat(add);
    missing -= add;
  }
  if (missing !== 0) throw new Error(`can't pad to ${target} bytes`);
  return env;
}
const OK = "passes";
const out = (status, ...reasons) => ({ status, reasons });
function inputCheckSpecs() {
  return [
    { name: "a valid envelope (control)", build: "base", expect: { raw: OK, parsed: OK, core: OK } },
    { name: "100,000 levels of nesting", build: "deep_100000", expect: { raw: out("oversize", "line_too_large"), parsed: out("oversize", "too_deep"), core: out("oversize", "line_too_large") } },
    { name: "9 levels of nesting", build: "nest_9", expect: { raw: out("oversize", "too_deep"), parsed: out("oversize", "too_deep"), core: out("oversize", "too_deep") } },
    { name: "8 levels of nesting is within the cap", build: "nest_8", expect: { raw: OK, parsed: OK, core: OK } },
    { name: "the V10 line: a valid envelope padded with whitespace to 131,761 bytes", build: "padded_131761", expect: { raw: out("oversize", "line_too_large"), parsed: null, core: null } },
    { name: "a line that isn't JSON", build: "not_json", expect: { raw: out("malformed", "not_json"), parsed: null, core: null } },
    { name: "a lone high surrogate in a value", build: "lone_value", expect: { raw: out("malformed", "lone_surrogate"), parsed: out("malformed", "lone_surrogate"), core: out("malformed", "lone_surrogate") } },
    { name: "a lone low surrogate in a key", build: "lone_key", expect: { raw: out("malformed", "lone_surrogate"), parsed: out("malformed", "lone_surrogate"), core: out("malformed", "lone_surrogate") } },
    { name: "a 513-character string", build: "string_513", expect: { raw: out("oversize", "string_too_long"), parsed: out("oversize", "string_too_long"), core: out("oversize", "string_too_long") } },
    { name: "a 512-character string is within the cap", build: "string_512", expect: { raw: OK, parsed: OK, core: OK } },
    { name: "512 astral characters (1,024 UTF-16 units) is within the cap: code points", build: "astral_512", expect: { raw: OK, parsed: OK, core: OK } },
    { name: "a 513-character object key", build: "key_513", expect: { raw: out("oversize", "string_too_long"), parsed: out("oversize", "string_too_long"), core: out("oversize", "string_too_long") } },
    { name: "a number that parses to Infinity (1e999)", build: "infinity", expect: { raw: out("malformed", "non_finite_number"), parsed: out("malformed", "non_finite_number"), core: out("malformed", "non_finite_number") } },
    { name: "65 center_temps entries", build: "temps_65", expect: { raw: out("oversize", "too_many_entries:center_temps"), parsed: out("oversize", "too_many_entries:center_temps"), core: out("oversize", "too_many_entries:center_temps") } },
    { name: "64 center_temps entries is within the cap", build: "temps_64", expect: { raw: OK, parsed: OK, core: OK } },
    { name: "65 geometry entries", build: "geometry_65", expect: { raw: out("oversize", "too_many_entries:geometry"), parsed: out("oversize", "too_many_entries:geometry"), core: out("oversize", "too_many_entries:geometry") } },
    { name: "65 artifact_hashes entries", build: "hashes_65", expect: { raw: out("oversize", "too_many_entries:artifact_hashes"), parsed: out("oversize", "too_many_entries:artifact_hashes"), core: out("oversize", "too_many_entries:artifact_hashes") } },
    { name: "schema: sig.alg is not ed25519", build: "alg_rsa", expect: { raw: out("malformed", "schema:sig.alg"), parsed: out("malformed", "schema:sig.alg"), core: null } },
    { name: "schema: hash is not lowercase hex", build: "hash_upper", expect: { raw: out("malformed", "schema:hash"), parsed: out("malformed", "schema:hash"), core: null } },
    { name: "schema: event.seq is 0", build: "seq_0", expect: { raw: out("malformed", "schema:event.seq"), parsed: out("malformed", "schema:event.seq"), core: out("malformed", "schema:event.seq") } },
    { name: "schema: event.body is missing", build: "no_body", expect: { raw: out("malformed", "schema:event.body"), parsed: out("malformed", "schema:event.body"), core: out("malformed", "schema:event.body") } },
    { name: "schema: values is null", build: "values_null", expect: { raw: out("malformed", "schema:values"), parsed: out("malformed", "schema:values"), core: out("malformed", "schema:values") } },
    { name: "values is undefined (in memory only; JSON drops it)", build: "values_undefined", expect: { raw: null, parsed: out("malformed", "invalid_value", "schema:values"), core: out("malformed", "invalid_value", "schema:values") } },
    { name: "a 60,001-byte line of 1e20 numbers whose canonical form is 264 KB", build: "expands_1e20", expect: { raw: out("oversize", "too_large"), parsed: out("oversize", "too_large"), core: out("oversize", "line_too_large") } },
    { name: "exactly 65,536 canonical bytes", build: "bytes_65536", expect: { raw: OK, parsed: OK, core: OK } },
    { name: "65,537 canonical bytes", build: "bytes_65537", expect: { raw: out("oversize", "line_too_large"), parsed: out("oversize", "too_large"), core: out("oversize", "line_too_large") } },
  ];
}
// Returns { value, raw }: the parsed (or in-memory) envelope and the JSONL line, either of which may be null.
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
const viewV1 = coreView("run-v1");
// Runs one path and reports { outcome, counters }. outcome is "passes" or { status, reasons }.
function runPath(path, made) {
  resetCounters();
  let outcome;
  if (path === "raw") {
    const row = verifyJsonl([made.raw], viewOptions(viewV1)).rows[0];
    outcome = ["oversize", "malformed"].includes(row.status) ? out(row.status, ...row.reasons) : OK;
  } else if (path === "parsed") {
    const row = verifyChain([made.value], viewOptions(viewV1)).rows[0];
    outcome = ["oversize", "malformed"].includes(row.status) ? out(row.status, ...row.reasons) : OK;
  } else {
    const env = made.value;
    const entry = { event: env.event, ts: env.ts, actor: env.actor };
    try {
      makeChain(env.run, [entry], Object.hasOwn(env, "values") ? { [env.event.event_id]: env.values } : {}, CORE_SIGNER_KEY);
      outcome = OK;
    } catch (error) {
      if (!error.reasons) throw error;
      outcome = out(error.status, ...error.reasons);
    }
  }
  return { outcome, counters: { ...counters } };
}

// ---- Mode (rule 5). Ages are measured back from now_ms on the client clock; a negative age is a future time. ----
const NOW = BASE_MS + 120_000;
function modeSpecs() {
  const ago = (age) => (age === null ? null : NOW - age);
  const c = (source, pollAge, progressAge, expect, label, note) => ({ source, last_poll_ok_ms: ago(pollAge), last_progress_ms: ago(progressAge), now_ms: NOW, expect, label, note });
  return [
    c("api", 1_000, 2_000, "LIVE", "LIVE · progress 2 s ago", "a poll succeeded 1 s ago and K grew 2 s ago"),
    c("api", 1_000, 12_900, "LIVE", "LIVE · progress 12 s ago", "the label shows whole seconds since K grew"),
    c("api", 5_000, 60_000, "LIVE", "LIVE · progress 60 s ago", "both limits are inclusive"),
    c("api", 5_001, 2_000, "STALE", "STALE", "the last good poll was over 5 s ago"),
    c("api", 1_000, 60_001, "STALE", "STALE", "polling works, but K hasn't grown for over 60 s"),
    c("api", 1_000, null, "STALE", "STALE", "K has never grown, e.g. before the first envelope"),
    c("api", null, null, "STALE", "STALE", "before the first poll"),
    c("api", 1_000, -3_600_000, "STALE", "STALE", "a progress time an hour in the future, e.g. a forged envelope ts passed by mistake, never makes LIVE"),
    c("api", -1_000, 2_000, "STALE", "STALE", "a poll time in the future never makes LIVE"),
    c("file", 1_000, 2_000, "REPLAY", "REPLAY", "a file is REPLAY whatever the times"),
    c("file", null, null, "REPLAY", "REPLAY", "a file is REPLAY whatever the times"),
  ];
}

// ---- Absent vs undefined vs null. The hashes are computed here with sha256(canonical()) directly. ----
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

// ---- canonical() examples (equal to RFC 8785 JCS for these). Hand-written expectations. ----
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
    return { ...spec, envelopes, result: verifyJsonl(buildLines(envelopes, spec.send)[0], viewOptions(spec.view)) };
  });
  const live = liveSpecs().map((spec) => {
    const envelopes = buildEnvelopes(spec.input);
    return { ...spec, envelopes, result: simulate(spec, envelopes).timeline };
  });
  const base = chains[0].envelopes[0];
  const inputChecks = inputCheckSpecs().map((spec) => {
    const made = buildInputCase(spec.build, base);
    const raw = made.raw === null ? null : made.raw.length <= 4096 ? made.raw : undefined;
    return { ...spec, ...(raw !== undefined ? { raw } : { raw_bytes: bytes(made.raw), raw_sha256: sha256(made.raw) }) };
  });
  return {
    description: "Test vectors for the SentiLab view envelope, DRAFT v0.5 (view-envelope-0.5.md). Generated by `node run-view-vectors.mjs --write` and checked by `node run-view-vectors.mjs`. Chains give the core's input, how the envelopes reach the view as JSONL, the run the view requested, its pins and served keys, the envelopes, a hand-written expect block and the full verifyJsonl() result.",
    contract_sha256: CONTRACT_SHA256,
    rules: {
      input_checks: "in order, before anything is hashed: (1) a JSONL line is at most 65,536 raw bytes; (2) parse; (3) structure, iteratively: depth at most 8 (the envelope is level 1, only objects and arrays count), strings and keys well-formed UTF-16 with at most 512 code points, finite numbers, at most 64 entries in values.geometry, values.center_temps and values.artifact_hashes, and the schema; (4) canonical size at most 65,536 bytes, measured without calling canonical(). A failure is one row with status oversize or malformed and is never passed to canonical(), hashed, signed or verified",
      transport: "an API response is at most 256 lines and 4 MiB (4,194,304 bytes); a replay file is at most 64 MiB; both are checked before parsing",
      canonical: "canonical() from ../contract-0.2/resultcheck.mjs; for these values it equals RFC 8785 (JCS). Absent fields are omitted, never undefined or null",
      hash: "sha256(canonical(envelope without sig and hash)), lowercase hex, recomputed from the content by the verifier",
      prev_hash: "the stored hash of an envelope at the previous seq; the first is sha256(\"sentilab-view-genesis:\" + the run_id the view requested)",
      run: "an envelope whose run.run_id differs from the run the view requested is run_mismatch",
      sig: "Ed25519 over the 64 hex characters of the recomputed hash as UTF-8; sig.value is lowercase hex, 128 characters",
      seq: "1, 2, 3, ... in seq order; a seq that isn't one more than the previous is seq_gap, and only that envelope is flagged",
      duplicates: "envelopes with identical canonical bytes (sig and hash included) are one envelope; the copies make no row",
      conflicts: "different envelopes in the same run sharing a seq (seq_conflict) or an event_id (event_id_conflict); every one involved is flagged",
      ordering: "rows are in seq order; at one seq, rejected rows first, then envelopes by stored hash; rows whose seq can't be read come last",
      projection: "the projectable prefix is the leading run of verified rows; prefix_end K is its last seq (0 if none); the board is project() over exactly those events; when anything follows, frozen is true and label is \"chain broken after seq K; board frozen at seq K\"; if project() throws, projection is null and projection_error is project_threw",
      mode: "api: LIVE when a poll succeeded within 5 s and the projectable prefix K last grew within 60 s (client clock, inclusive, never in the future), with the label \"LIVE · progress N s ago\"; otherwise STALE; file: REPLAY",
      roles: "actor_role is lab, core or acceptance_gate; actor.lab gate goes with acceptance_gate; only the gate writes accepted, non_improving_current and within_margin",
      key_sha256: "sha256 of the raw 32-byte Ed25519 public key (the last 32 bytes of its SPKI DER), lowercase hex",
      test_keys: "seed = sha256(\"sentilab-view-test-key:\" + name) (32 bytes); private key = Ed25519 from that seed, i.e. PKCS8 DER 302e020100300506032b657004220420 || seed",
      after_signing: "set the value at path in the envelope with that seq, after it was signed",
      replace_from_fork: "build the same chain with entry fork_seq's ts set to fork_ts, then put that chain's envelope take_seq in place of ours",
      also: "build these entries as separate chains with the same run and signer, and add their envelopes",
      drop_seqs: "sign the whole chain, then leave the envelopes with these seqs out",
      send: "pad: insert spaces after the opening brace of that seq's JSON line until it is line_bytes; orders: deliver the envelopes in each order (by event_id); twice: send every line twice",
      append_checks: "false means a faulty writer: makeChain skips every check the core makes and signs whatever it is given",
    },
    test_keys: Object.fromEntries(["core", "forger"].map((name) => [name, { key_sha256_prefix: rawKeyHash(testKey(name).publicKey).slice(0, 8) }])),
    reason_codes: {
      bad_version: "v is not view-envelope/0.5",
      run_mismatch: "run.run_id differs from the run the view requested",
      seq_gap: "seq is not the previous seq + 1 (or not 1 for the first)",
      seq_conflict: "another, different envelope in the same run has this seq",
      event_id_conflict: "another, different envelope in the same run has this event_id",
      prev_hash_mismatch: "prev_hash is not the stored hash of an envelope at the previous seq (or the genesis value)",
      hash_mismatch: "the stored hash is not the hash recomputed from the content",
      key_not_pinned: "sig.key_id is not among the page's pins",
      key_unavailable: "pinned, but no key was served for that key_id",
      key_hash_mismatch: "the served key's sha256 doesn't match the pin",
      bad_sig: "the signature doesn't verify over the recomputed hash",
    },
    input_check_codes: {
      line_too_large: "oversize: the raw line is over 65,536 bytes (step 1; never parsed)",
      not_json: "malformed: the line doesn't parse (step 2)",
      too_deep: "oversize: an object or array below level 8 (step 3)",
      lone_surrogate: "malformed: a string or key that isn't well-formed UTF-16 (step 3)",
      string_too_long: "oversize: a string or key over 512 code points (step 3)",
      non_finite_number: "malformed: a number that is NaN or infinite (step 3)",
      "too_many_entries:<field>": "oversize: over 64 entries in values.geometry, values.center_temps or values.artifact_hashes (step 3)",
      invalid_value: "malformed: not a JSON value, e.g. undefined, possible only for in-memory input (step 3)",
      "schema:<path>": "malformed: the schema doesn't hold at that path (step 3)",
      too_large: "oversize: canonical(envelope) is over 65,536 bytes (step 4)",
    },
    chains,
    live,
    transport: transportSpecs(),
    input_checks: inputChecks,
    mode: modeSpecs(),
    hashing: hashingSpecs(base),
    canonical: CANONICAL_SPECS,
  };
}

// Indented JSON, except that each envelope, entry, result row, projection node and timeline step sits on one
// line, the way a JSONL replay file holds envelopes. Formatting only; the checks compare parsed JSON.
function format(vectors) {
  const inline = [];
  const mark = (value) => `@@inline-${inline.push(JSON.stringify(value)) - 1}@@`;
  const markInput = (input) => ({ ...input, entries: input.entries.map(mark), ...(input.also ? { also: input.also.map((extra) => ({ ...extra, entries: extra.entries.map(mark) })) } : {}) });
  const marked = {
    ...vectors,
    chains: vectors.chains.map((chain) => ({
      ...chain,
      input: markInput(chain.input),
      envelopes: chain.envelopes.map(mark),
      result: {
        ...chain.result,
        rows: chain.result.rows.map(mark),
        projection: chain.result.projection && { ...chain.result.projection, nodes: Object.fromEntries(Object.entries(chain.result.projection.nodes).map(([k, v]) => [k, mark(v)])) },
      },
    })),
    live: vectors.live.map((spec) => ({ ...spec, input: markInput(spec.input), envelopes: spec.envelopes.map(mark), result: spec.result.map(mark) })),
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
const refusal = (fn) => {
  try { fn(); } catch (error) { return error.reasons ? [error.reasons] : [`threw ${error.message}`]; }
  return [];
};
const expectRefusal = (fn, reasons) => {
  const got = refusal(fn);
  return got.length === 1 && same(got[0], reasons) ? [] : [`expected refusal ${canonical(reasons)}, got ${canonical(got)}`];
};

if (process.argv.includes("--write")) {
  writeFileSync(FILE, format(generate()));
  console.log(`wrote ${FILE}`);
}
const file = JSON.parse(readFileSync(FILE, "utf8"));
const fresh = generate();

check("file: same top-level content as the generator (rules, keys, codes)", () =>
  ["description", "contract_sha256", "rules", "test_keys", "reason_codes", "input_check_codes"].filter((k) => !same(file[k], fresh[k])).map((k) => `${k} differs`));
check("file: same vectors as the generator in every section", () =>
  ["chains", "live", "transport", "input_checks", "mode", "hashing", "canonical"].filter((k) => !same(file[k].map((v) => v.name ?? v.note), fresh[k].map((v) => v.name ?? v.note))).map((k) => `${k} list differs`));

const chainResults = new Map();
for (const [index, vector] of file.chains.entries()) {
  const label = vector.name.split(":")[0];
  const generated = fresh.chains[index];
  const options = viewOptions(vector.view);
  const lineSets = buildLines(vector.envelopes, vector.send);
  const result = verifyJsonl(lineSets[0], options);
  chainResults.set(vector.name.split(" ")[0], result);
  check(`${label}: input, send, view and expect match the generator`, () =>
    ["name", "input", "send", "view", "expect"].filter((k) => !same(vector[k], generated?.[k])).map((k) => `${k} differs`));
  check(`${label}: envelopes regenerate byte-identically from the file's input`, () => {
    const rebuilt = buildEnvelopes(vector.input);
    if (rebuilt.length !== vector.envelopes.length) return [`${rebuilt.length} envelopes, file has ${vector.envelopes.length}`];
    return rebuilt.flatMap((env, i) => (same(env, vector.envelopes[i]) ? [] : [`envelope ${i} (seq ${env.event.seq}) differs`]));
  });
  check(`${label}: verifyJsonl over the file's envelopes equals the recorded result`, () => {
    if (same(result, vector.result)) return [];
    const diffs = result.rows.flatMap((row, i) => (same(row, vector.result.rows[i]) ? [] : [`row ${i}: ${canonical(row)}`]));
    for (const key of ["chain_ok", "prefix_end", "frozen", "label"]) if (result[key] !== vector.result[key]) diffs.push(`${key} ${JSON.stringify(result[key])}`);
    if (!same(result.projection, vector.result.projection)) diffs.push("projection differs");
    return diffs.length ? diffs : ["differs"];
  });
  check(`${label}: the hand-written expectations hold`, () => checkExpect(result, vector.expect));
  check(`${label}: an independent re-derivation agrees on every row, the prefix and the projection`, () => {
    const theirs = oracle(lineSets[0], vector.view, vector.expect);
    const mine = result.rows.map((row) => ({ key: rowKey(row), status: ["oversize", "malformed"].includes(row.status) ? "rejected" : row.status }));
    const errors = same(mine, theirs.statuses) ? [] : [`rows: verifyJsonl ${canonical(mine)}, the rules ${canonical(theirs.statuses)}`];
    if (result.prefix_end !== theirs.prefix_end) errors.push(`prefix_end: verifyJsonl ${result.prefix_end}, the rules ${theirs.prefix_end}`);
    if (!same(result.projection, theirs.projection)) errors.push("projection differs from project() over the projectable prefix");
    return errors;
  });
  if (!vector.send.pad) {
    check(`${label}: the parsed path (verifyChain) gives the same result as the JSONL path`, () =>
      lineSets.every((lines) => same(verifyChain(lines.map((line) => JSON.parse(line)), options), verifyJsonl(lines, options))) ? [] : ["the paths differ"]);
  }
  check(`${label}: delivery order doesn't change the result (reversed${vector.send.orders ? ", and every listed order" : ""})`, () => {
    const errors = same(verifyJsonl([...lineSets[0]].reverse(), options), result) ? [] : ["reversed lines gave a different result"];
    for (const [i, lines] of lineSets.entries()) if (!same(verifyJsonl(lines, options), result)) errors.push(`order ${i} gave a different result`);
    return errors;
  });
  if (vector.expect.no_acceptance) {
    check(`${label}: the claimed acceptance never appears on the board`, () => {
      const shown = Object.entries(result.projection?.nodes ?? {}).filter(([, node]) => node.accepted_ever || node.lifecycle === "accepted").map(([nodeId]) => nodeId);
      return result.projection && shown.length === 0 ? [] : [`shown as accepted: ${shown.join(", ") || "(no projection)"}`];
    });
  }
  if (vector.expect.same_result_as) {
    check(`${label}: the result is exactly ${vector.expect.same_result_as}'s`, () => (same(result, chainResults.get(vector.expect.same_result_as)) ? [] : ["differs"]));
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
  if (vector.send.pad) {
    check(`${label}: the padded line is ${vector.send.pad.line_bytes.toLocaleString("en-US")} bytes and is never parsed, canonicalized or hashed`, () => {
      const padded = lineSets[0].find((line) => bytes(line) > 65_536);
      if (!padded || bytes(padded) !== vector.send.pad.line_bytes) return ["no padded line of that size"];
      resetCounters();
      verifyJsonl([padded], options);
      return counters.parse + counters.canonical + counters.hash + counters.verify === 0 ? [] : [`counters ${canonical(counters)}`];
    });
  }
  if (Object.keys(vector.expect.rejected).length > 0) {
    check(`${label}: rejected envelopes are never canonicalized, hashed or verified`, () => {
      const keys = new Set(Object.keys(vector.expect.rejected));
      const lines = lineSets[0].filter((line) => { const env = JSON.parse(line); return keys.has(`${env.event.seq}:${env.event.event_id}`); });
      resetCounters();
      verifyJsonl(lines, options);
      return lines.length === keys.size && counters.canonical + counters.hash + counters.verify === 0 ? [] : [`counters ${canonical(counters)} for ${lines.length} lines`];
    });
  }
}

for (const [index, vector] of file.live.entries()) {
  const label = vector.name.split(":")[0];
  const sim = simulate(vector, vector.envelopes);
  const byTime = new Map(sim.timeline.map((step) => [step.t, step]));
  check(`${label}: input, view, schedule and expect match the generator`, () =>
    ["name", "input", "view", "schedule", "expect"].filter((k) => !same(vector[k], fresh.live[index]?.[k])).map((k) => `${k} differs`));
  check(`${label}: envelopes regenerate byte-identically from the file's input`, () => (same(buildEnvelopes(vector.input), vector.envelopes) ? [] : ["envelopes differ"]));
  check(`${label}: the simulated timeline equals the recorded one`, () => (same(sim.timeline, vector.result) ? [] : ["timeline differs"]));
  check(`${label}: the labels and K at the listed times are as expected`, () => [
    ...Object.entries(vector.expect.labels).flatMap(([t, want]) => (byTime.get(Number(t))?.label === want ? [] : [`at ${t} s: expected "${want}", got "${byTime.get(Number(t))?.label}"`])),
    ...Object.entries(vector.expect.K).flatMap(([t, want]) => (byTime.get(Number(t))?.K === want ? [] : [`K at ${t} s: expected ${want}, got ${byTime.get(Number(t))?.K}`])),
  ]);
  check(`${label}: LIVE from ${vector.expect.live_from_s} s${vector.expect.stale_from_s === null ? " to the end" : `, STALE from ${vector.expect.stale_from_s} s`}, and no label claims completeness`, () => sim.timeline.flatMap((step) => {
    const wantLive = step.t >= vector.expect.live_from_s && (vector.expect.stale_from_s === null || step.t < vector.expect.stale_from_s);
    const errors = step.label.startsWith("LIVE") === wantLive ? [] : [`at ${step.t} s: ${step.label}`];
    return /complete|final|done|finished/i.test(step.label) ? [...errors, `at ${step.t} s claims completeness: ${step.label}`] : errors;
  }));
  if (vector.expect.arrivals_every_poll) {
    check(`${label}: envelopes arrived at every poll, yet none grew K`, () => sim.timeline.flatMap((step) => (step.received > 0 && (step.t === 0 || step.K === sim.timeline[0].K) ? [] : [`at ${step.t} s: received ${step.received}, K ${step.K}`])));
  }
  if (vector.expect.full_history) {
    check(`${label}: the withheld board shows the measurement valid; the full history, withdrawal included, projects it withdrawn`, () => {
      const errors = subset(sim.board.nodes, vector.expect.board_at_end, "board");
      const full = verifyChain(buildEnvelopes({ ...vector.input }), viewOptions(vector.view));
      errors.push(...subset(full.projection.nodes, vector.expect.full_history, "full"));
      if (full.prefix_end !== vector.input.entries.length) errors.push(`full history prefix_end ${full.prefix_end}`);
      return errors;
    });
  }
}

for (const [index, spec] of file.transport.entries()) {
  check(`V18 transport: ${spec.name}`, () => {
    const errors = same(spec, fresh.transport[index]) ? [] : ["differs from the generator"];
    const text = buildResponse(spec.build);
    resetCounters();
    const got = parseApiResponse(text);
    if (got.ok !== spec.expect.ok || got.reason !== spec.expect.reason) errors.push(`expected ${canonical(spec.expect)}, got ok ${got.ok} ${got.reason ?? ""}`);
    if (counters.parse + counters.canonical + counters.hash !== 0) errors.push(`parsed or hashed: ${canonical(counters)}`);
    return errors;
  });
}
check("V18 transport: a rejected response leaves the prefix unchanged and counts the poll as failed", () => {
  const options = viewOptions(file.chains[0].view);
  const v1Lines = buildLines(file.chains[0].envelopes, {})[0];
  const tracker = progressTracker();
  const received = [...v1Lines];
  tracker.poll({ nowMs: BASE_MS, ok: true, K: verifyJsonl(received, options).prefix_end, received: received.length });
  const errors = [];
  for (const [t, build] of [[1, { lines: 257 }], [2, { bytes: 4 * 1024 * 1024 + 1 }]]) {
    const response = parseApiResponse(buildResponse(build));
    if (response.ok) errors.push(`at ${t} s the response was accepted`);
    else tracker.poll({ nowMs: BASE_MS + t * 1000, ok: false });
  }
  if (verifyJsonl(received, options).prefix_end !== 11 || tracker.state().K !== 11) errors.push("the prefix changed");
  if (tracker.state().last_poll_ok_ms !== BASE_MS) errors.push("a rejected response counted as a good poll");
  if (tracker.mode("api", BASE_MS + 5_000) !== "LIVE" || tracker.mode("api", BASE_MS + 6_000) !== "STALE") errors.push("STALE should follow 5 s after the last good poll");
  return errors;
});

const base = file.chains[0].envelopes[0];
for (const [index, spec] of file.input_checks.entries()) {
  check(`V12 input checks: ${spec.name}`, () => {
    const errors = same(spec, fresh.input_checks[index]) ? [] : ["differs from the generator"];
    const made = buildInputCase(spec.build, base);
    if (spec.raw !== undefined && spec.raw !== made.raw) errors.push("raw line differs from the file");
    if (spec.raw_sha256 !== undefined && sha256(made.raw) !== spec.raw_sha256) errors.push("raw line sha256 differs from the file");
    for (const path of ["raw", "parsed", "core"]) {
      const want = spec.expect[path];
      if (want === null) continue;
      const { outcome, counters: seen } = runPath(path, made);
      if (!same(outcome, want)) errors.push(`${path}: expected ${canonical(want)}, got ${canonical(outcome)}`);
      if (want === OK) {
        if (seen.hash < 1 || (path === "core" ? seen.sign !== 1 : seen.verify > 1)) errors.push(`${path}: the control should hash${path === "core" ? " and sign" : ""}: ${canonical(seen)}`);
      } else if (seen.canonical + seen.hash + seen.sign + seen.verify !== 0) errors.push(`${path}: rejected input reached canonical/hash/sign/verify: ${canonical(seen)}`);
      if (path === "raw" && want !== OK && want.reasons[0] === "line_too_large" && seen.parse !== 0) errors.push("raw: an oversize line was parsed");
    }
    return errors;
  });
}

check(`mode: ${file.mode.length} cases (rule 5), with labels`, () => {
  const errors = file.mode.flatMap((c) => {
    const got = mode(c.source, c.last_poll_ok_ms, c.last_progress_ms, c.now_ms);
    const label = modeLabel(c.source, c.last_poll_ok_ms, c.last_progress_ms, c.now_ms);
    return got === c.expect && label === c.label ? [] : [`${c.note}: expected ${c.expect} "${c.label}", got ${got} "${label}"`];
  });
  if (!same(file.mode, fresh.mode)) errors.push("mode cases differ from the generator");
  return errors;
});
check("tracker: only growth of K beyond its highest value refreshes progress; a failed poll is not a good poll", () => {
  const tracker = progressTracker();
  const errors = [];
  tracker.poll({ nowMs: 0, ok: true, K: 0, received: 0 });
  if (tracker.mode("api", 0) !== "STALE") errors.push("K = 0 should be STALE");
  tracker.poll({ nowMs: 1_000, ok: true, K: 5, received: 5 });
  tracker.poll({ nowMs: 2_000, ok: true, K: 3, received: 9 });
  tracker.poll({ nowMs: 3_000, ok: true, K: 5, received: 9 });
  if (tracker.state().last_progress_ms !== 1_000) errors.push(`a drop and a return to the old K refreshed progress: ${canonical(tracker.state())}`);
  tracker.poll({ nowMs: 4_000, ok: false, K: 9 });
  if (tracker.state().last_poll_ok_ms !== 3_000 || tracker.state().K !== 5) errors.push("a failed poll changed the state");
  tracker.poll({ nowMs: 5_000, ok: true, K: 6, received: 1 });
  if (tracker.state().last_progress_ms !== 5_000) errors.push("growth didn't refresh progress");
  return errors;
});

for (const [index, spec] of file.hashing.entries()) {
  check(`hashing: ${spec.name}`, () => {
    const errors = same(spec, fresh.hashing[index]) ? [] : ["differs from the generator"];
    const env = spec.envelope;
    if (hashEnvelope(env) !== spec.hash_values_absent) errors.push("hashEnvelope differs for values absent");
    if (hashEnvelope({ ...env, values: undefined }) !== spec.hash_values_undefined) errors.push("hashEnvelope differs for values: undefined");
    if (hashEnvelope({ ...env, values: null }) !== spec.hash_values_null) errors.push("hashEnvelope differs for values: null");
    if (spec.hash_values_absent === spec.hash_values_undefined) errors.push("absent and undefined hash the same");
    if (spec.hash_values_absent === spec.hash_values_null) errors.push("absent and null hash the same");
    if (spec.hash_values_undefined !== spec.hash_values_null) errors.push("undefined and null should both canonicalize to null");
    const received = JSON.parse(JSON.stringify(signEnvelope({ ...env, values: undefined }, coreKey.privateKey, "core")));
    if (Object.hasOwn(received, "values")) errors.push("JSON kept the undefined key");
    const row = verifyChain([received], viewOptions(viewV1)).rows[0];
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
const v1Entries = v1.input.entries;
const withEntry = (seq, change) => v1Entries.map((e) => (e.event.seq === seq ? change(structuredClone(e)) : e));
const appendV1 = (list, values = v1.input.values) => makeChain(v1.input.run, list, values, CORE_SIGNER_KEY);
const allEnvelopes = [...file.chains.flatMap((c) => c.envelopes), ...file.live.flatMap((l) => l.envelopes)];
check("keys: each test key's PKCS8 seed round-trips and its SPKI is 44 bytes", () => ["core", "forger"].flatMap((name) => {
  const { privateKey, publicKey } = testKey(name);
  const errors = [];
  if (privateKey.export({ format: "jwk" }).d !== seedFor(name).toString("base64url")) errors.push(`${name}: seed doesn't round-trip`);
  if (publicKey.export({ type: "spki", format: "der" }).length !== 44) errors.push(`${name}: SPKI is not 44 bytes`);
  if (keySha256(publicKey) !== rawKeyHash(publicKey)) errors.push(`${name}: keySha256 disagrees with the raw-key rule`);
  if (rawKeyHash(publicKey).slice(0, 8) !== file.test_keys[name].key_sha256_prefix) errors.push(`${name}: key_sha256 prefix differs from the file`);
  return errors;
}));
check("hashing: hash ignores sig and hash, genesis is sha256 of the prefixed run_id, and v is view-envelope/0.5", () => {
  const env = v1.envelopes[0];
  const { sig, hash, ...bare } = env;
  const errors = [];
  if (hashEnvelope(env) !== env.hash || hashEnvelope(bare) !== env.hash) errors.push("hashEnvelope depends on sig or hash");
  if (genesis("run-v1") !== sha256("sentilab-view-genesis:run-v1") || env.prev_hash !== genesis("run-v1")) errors.push("genesis differs");
  if (env.v !== V_STRING) errors.push(`v is ${env.v}`);
  return errors;
});
check(`size: canonicalSize() equals the canonical byte length and the JSON line length for all ${allEnvelopes.length} vector envelopes, without calling canonical()`, () => allEnvelopes.flatMap((env) => {
  const want = bytes(canonical(env));
  resetCounters();
  const got = canonicalSize(env);
  return got === want && bytes(JSON.stringify(env)) === want && counters.canonical === 0 ? [] : [`${env.event.event_id}: ${got} vs ${want}`];
}));
check("run: verifying refuses to run without the run_id the view requested", () => {
  try { verifyChain(v1.envelopes, { pins: resolvePins(v1.view), keys: resolveKeys(v1.view) }); } catch (error) { return /run_id/.test(error.message) ? [] : [error.message]; }
  return ["did not throw"];
});
check("pins: rotation, two pinned ids, the chain verifies under the second", () => {
  const pins = [{ key_id: "core-previous", key_sha256: rawKeyHash(testKey("forger").publicKey) }, ...resolvePins(v1.view)];
  return verifyChain(v1.envelopes, { runId: "run-v1", pins, keys: resolveKeys(v1.view) }).chain_ok ? [] : ["chain not ok"];
});
check("pins: a pinned id with no served key is key_unavailable, and nothing is projected", () => {
  const result = verifyChain(v1.envelopes, { runId: "run-v1", pins: resolvePins(v1.view), keys: {} });
  const errors = result.rows.every((row) => same(row.reasons, ["key_unavailable"])) ? [] : ["wrong reasons"];
  return result.prefix_end === 0 ? errors : [...errors, "something was projected"];
});
check("robustness: a junk envelope is a malformed row after the others, and the projection is unchanged", () => {
  const result = verifyChain([...v1.envelopes, { junk: true }], viewOptions(v1.view));
  const errors = result.rows.length === 12 && result.rows[11].status === "malformed" && result.rows[11].seq === null ? [] : ["junk row missing or wrong"];
  return same(result.projection, v1.result.projection) ? errors : [...errors, "the junk envelope changed the projection"];
});
check("robustness: a verified event that project() can't read gives an error state, not a throw", () => {
  const bad = { event: { event_id: "v1-e12", seq: 12, type: "support.add", actor_role: "core", body: { node: "K1", set_id: "x", members: "M1" } }, ts: T(12), actor: CORE };
  const result = verifyChain(appendV1([...v1Entries, bad]), viewOptions(v1.view));
  const errors = result.rows.at(-1).status === "verified" ? [] : ["the envelope should verify"];
  return result.projection === null && result.projection_error === "project_threw" ? errors : [...errors, `projection_error is ${result.projection_error}`];
});
check("transport: a replay file over 64 MiB is refused before parsing; a small one is split into lines", () => {
  resetCounters();
  const big = readReplayFile("x".repeat(64 * 1024 * 1024 + 1));
  const errors = !big.ok && big.reason === "file_too_large" && counters.parse === 0 ? [] : [`big file: ${canonical(big)}`];
  const small = readReplayFile(buildLines(v1.envelopes, {})[0].map((line) => `${line}\n`).join(""));
  return small.ok && small.lines.length === 11 ? errors : [...errors, "small file not split into 11 lines"];
});
check("append: makeChain treats a byte-identical retransmission as a no-op", () => (same(appendV1([...v1Entries, ...v1Entries]), appendV1(v1Entries)) ? [] : ["the chain changed"]));
check("append: makeChain refuses a conflicting seq before signing it", () => {
  resetCounters();
  const errors = expectRefusal(() => appendV1([...v1Entries.slice(0, 3), withEntry(3, (e) => { e.ts = T(3.5); e.event.event_id = "v1-x"; return e; })[2]]), ["seq_conflict"]);
  return counters.sign === 3 ? errors : [...errors, `signed ${counters.sign} times, expected 3`];
});
check("append: makeChain refuses the same event_id with different content at the same seq", () => expectRefusal(() => appendV1([...v1Entries.slice(0, 3), withEntry(3, (e) => { e.ts = T(3.5); return e; })[2]]), ["event_id_conflict", "seq_conflict"]));
// No values here: values are keyed by event_id, so reusing v1-e01 would also hand the candidate's values to seq 2.
check("append: makeChain refuses an event_id reused at a later seq", () => expectRefusal(() => appendV1(withEntry(2, (e) => { e.event.event_id = "v1-e01"; return e; }), {}), ["event_id_conflict"]));
check("append: makeChain refuses a seq gap", () => expectRefusal(() => appendV1(withEntry(5, (e) => { e.event.seq = 50; return e; })), ["seq_gap"]));
check("append: makeChain refuses values on an event that can't carry them", () => expectRefusal(() => appendV1(v1Entries, { ...v1.input.values, "v1-e05": { units: "mm" } }), ["values_not_allowed"]));
check("append: makeChain refuses undefined anywhere in the envelope", () => expectRefusal(() => appendV1(withEntry(1, (e) => { e.actor.agent_id = undefined; return e; })), ["invalid_value"]));
check("append: makeChain refuses an actor_role outside lab, core and acceptance_gate", () => expectRefusal(() => appendV1(withEntry(2, (e) => { e.event.actor_role = "agent"; return e; })), ["bad_actor_role"]));
check("append: makeChain refuses a board outcome not written by the gate", () => ["accepted", "non_improving_current", "within_margin"].flatMap((to) =>
  expectRefusal(() => appendV1(withEntry(11, (e) => { e.event.actor_role = "core"; e.actor = CORE; e.event.body.to = to; return e; })), ["board_outcome_not_gate"])));
check("append: makeChain refuses a gate actor without the acceptance_gate role, and the reverse", () => [
  ...expectRefusal(() => appendV1(withEntry(11, (e) => { e.event.actor_role = "core"; return e; })), ["gate_role_mismatch"]),
  ...expectRefusal(() => appendV1(withEntry(2, (e) => { e.event.actor_role = "acceptance_gate"; return e; })), ["gate_role_mismatch"]),
]);

const failed = results.filter((r) => r.errors.length > 0).length;
console.log(failed === 0 ? `PASS: ${results.length} of ${results.length} checks` : `FAIL: ${failed} of ${results.length} checks failed`);
const fileSha = (name) => createHash("sha256").update(readFileSync(join(here, name))).digest("hex");
for (const name of ["view-envelope.mjs", "run-view-vectors.mjs", "vectors-view.json"]) console.log(`${fileSha(name)}  ${name}`);
process.exit(failed === 0 ? 0 : 1);
