// Builds web/public/sentilab/demo-run.jsonl, the Lab view's bundled replay, with the VIEW ENVELOPE v0.5 reference
// makeChain() (so every entry passes the core's input checks and append rules before it is signed) and the "core" TEST
// key (web/test/sentilab-keys.mjs). Deterministic: fixed ids and timestamps, and Ed25519 signatures are
// deterministic, so a rerun is byte-identical.
//   node web/test/make-sentilab-demo.mjs          write the file
//   node web/test/make-sentilab-demo.mjs --check  exit 1 if the committed file differs from a fresh build
//
// This is an INTERFACE FIXTURE. The layouts are hand-placed and every temperature is an illustrative number; no
// solver ran. The page labels it that way. The story: four labs and a simulated-annealing baseline propose
// 8-chiplet layouts; the core validates, evaluates and reproduces; the gate accepts one and rules one a valid
// loser; then a seeded correction drill withdraws the accepted candidate's first measurement.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { makeChain } from "../../contracts/view-envelope-v0.5/view-envelope.mjs";
import { testKey } from "./sentilab-keys.mjs";

const here = dirname(fileURLToPath(import.meta.url));
export const DEMO_PATH = join(here, "..", "public", "sentilab", "demo-run.jsonl");
export const DEMO_RUN = { run_id: "demo-8c-0001", arm: "live", family: "fixture-8chiplet", seed: 11, ticket_id: "ticket-demo-8c-0001" };

const BASE_MS = Date.UTC(2026, 10, 1, 14, 0, 0);
const T = (seconds) => new Date(BASE_MS + Math.round(seconds * 1000)).toISOString();
const CORE = { agent_id: null, life_id: null, lab: "core", grant_id: null };
const GATE = { agent_id: null, life_id: null, lab: "gate", grant_id: null };
const lab = (key) => ({ agent_id: `agent-${key}-01`, life_id: `life-${key}-0001`, lab: key, grant_id: `grant-${key}-0001` });
// evaluator_version names the truth: no evaluator ran for this fixture.
const SEMANTICS = { task_contract: "tc-8chiplet-demo-v0", metric_id: "max-chiplet-center-temp-c", evaluator_version: "fixture-no-solver", coordinate_frame: "pkg-lower-left-mm" };

// 8 chiplets on a 44 x 36 mm interposer, lower-left origin. Four memory stacks stay in the corners; the labs move
// the two compute dies, the accelerator and the I/O die.
const MEMORY = [
  { id: "HBM0", xLL: 1, yLL: 1, w: 7, h: 10, layer: 0 }, { id: "HBM1", xLL: 1, yLL: 25, w: 7, h: 10, layer: 0 },
  { id: "HBM2", xLL: 36, yLL: 1, w: 7, h: 10, layer: 0 }, { id: "HBM3", xLL: 36, yLL: 25, w: 7, h: 10, layer: 0 },
];
const layout = (cpu0, cpu1, npu, io) => [
  { id: "CPU0", xLL: cpu0[0], yLL: cpu0[1], w: 11, h: 9, layer: 0 }, { id: "CPU1", xLL: cpu1[0], yLL: cpu1[1], w: 11, h: 9, layer: 0 },
  { id: "NPU0", xLL: npu[0], yLL: npu[1], w: 9, h: 8, layer: 0 }, { id: "IO0", xLL: io[0], yLL: io[1], w: 9, h: 5, layer: 0 },
  ...MEMORY,
];
const GEOMETRY = {
  init: layout([10, 13], [22, 13], [17, 24], [17, 3]),   // both compute dies side by side in the middle
  a: layout([9, 13], [27, 13], [21, 24], [21, 3]),
  b: layout([10, 3], [23, 24], [24, 6], [11, 27]),       // compute dies on opposite corners
  c: layout([10, 13], [31, 22], [17, 24], [17, 3]),      // CPU1 overlaps HBM3: fails the constraint check
  d: layout([12, 2], [12, 25], [26, 14], [2, 15]),
  sa: layout([10, 8], [24, 18], [11, 22], [24, 4]),
};
const temps = (cpu0, cpu1, npu, io, hbm) => ({ CPU0: cpu0, CPU1: cpu1, NPU0: npu, IO0: io, HBM0: hbm[0], HBM1: hbm[1], HBM2: hbm[2], HBM3: hbm[3] });
const TEMPS = {
  init: temps(96.8, 96.1, 88.4, 71.2, [72.5, 73.0, 72.8, 74.1]),
  a: temps(92.4, 91.8, 87.5, 70.4, [73.6, 73.9, 74.4, 75.0]),
  b: temps(90.1, 89.6, 86.0, 69.8, [74.9, 71.7, 75.3, 76.2]),
  sa: temps(93.0, 92.2, 87.9, 70.9, [73.1, 72.4, 73.5, 75.4]),
};
const W = { init: 1712.4, a: 1788.0, b: 1840.5, sa: 1801.2 };
const J = (t) => ({ value: Math.max(...Object.values(t)), unit: "°C" });   // J = max chiplet-center temperature
const measured = (key, withGeometry = false) => ({
  ...(withGeometry ? { geometry: GEOMETRY[key], units: "mm" } : {}),
  scenario_id: "scn-steady-680w", J: J(TEMPS[key]), W: { value: W[key], metric_id: "hpwl-mm" }, center_temps: TEMPS[key],
});
const proposed = (key) => ({ geometry: GEOMETRY[key], units: "mm", scenario_id: "scn-steady-680w" });
const replayed = (key) => ({ scenario_id: "scn-steady-680w", J: J(TEMPS[key]) });

// [seconds, actor, actor_role, type, body, values?]
const core = (t, type, body, values) => [t, CORE, "core", type, body, values];
const STEPS = [
  core(0.0, "node.create", { id: "meas-init", kind: "measurement", semantics: SEMANTICS }, measured("init", true)),
  [4.2, lab("lab-a"), "lab", "node.create", { id: "cand-a", kind: "candidate" }, proposed("a")],
  [5.0, lab("lab-b"), "lab", "node.create", { id: "cand-b", kind: "candidate" }, proposed("b")],
  [6.1, lab("lab-c"), "lab", "node.create", { id: "cand-c", kind: "candidate" }, proposed("c")],
  [7.3, lab("lab-d"), "lab", "node.create", { id: "cand-d", kind: "candidate" }, proposed("d")],
  [8.0, lab("baseline-sa"), "lab", "node.create", { id: "cand-sa", kind: "candidate" }, proposed("sa")],
  core(8.4, "lifecycle.transition", { node: "cand-a", to: "validated" }),
  core(8.6, "lifecycle.transition", { node: "cand-b", to: "validated" }),
  core(8.8, "lifecycle.transition", { node: "cand-c", to: "validated" }),
  core(9.1, "lifecycle.transition", { node: "cand-d", to: "validated" }),
  core(9.3, "lifecycle.transition", { node: "cand-sa", to: "validated" }),
  core(9.5, "lifecycle.transition", { node: "cand-c", to: "rejected_constraints" }),
  core(9.7, "lifecycle.transition", { node: "cand-a", to: "simulation_pending" }),
  core(9.9, "lifecycle.transition", { node: "cand-b", to: "simulation_pending" }),
  core(10.1, "lifecycle.transition", { node: "cand-d", to: "simulation_pending" }),
  core(10.3, "lifecycle.transition", { node: "cand-sa", to: "simulation_pending" }),
  core(31.5, "node.create", { id: "meas-b", kind: "measurement", semantics: SEMANTICS }, measured("b")),
  core(31.6, "support.add", { node: "cand-b", set_id: "eval", members: ["meas-b"] }),
  core(31.7, "lifecycle.transition", { node: "cand-b", to: "evaluated" }),
  core(33.0, "node.create", { id: "meas-a", kind: "measurement", semantics: SEMANTICS }, measured("a")),
  core(33.1, "support.add", { node: "cand-a", set_id: "eval", members: ["meas-a"] }),
  core(33.2, "lifecycle.transition", { node: "cand-a", to: "evaluated" }),
  core(35.0, "node.create", { id: "meas-sa", kind: "measurement", semantics: SEMANTICS }, measured("sa")),
  core(35.1, "support.add", { node: "cand-sa", set_id: "eval", members: ["meas-sa"] }),
  core(35.2, "lifecycle.transition", { node: "cand-sa", to: "evaluated" }),
  core(40.0, "lifecycle.transition", { node: "cand-d", to: "failed_run" }),
  core(40.5, "lifecycle.transition", { node: "cand-b", to: "reproduction_pending" }),
  core(58.0, "node.create", { id: "repro-b", kind: "measurement", semantics: SEMANTICS }, measured("b")),
  core(58.1, "verify.add", { node: "meas-b", tier: "replayed", evidence: ["repro-b"] }, replayed("b")),
  core(58.2, "support.add", { node: "cand-b", set_id: "repro", members: ["repro-b"] }),
  core(58.3, "lifecycle.transition", { node: "cand-b", to: "reproduced" }),
  [59.0, GATE, "acceptance_gate", "lifecycle.transition", { node: "cand-b", to: "accepted" }],
  core(59.4, "lifecycle.transition", { node: "cand-sa", to: "non_improving" }),
  core(59.8, "lifecycle.transition", { node: "cand-a", to: "reproduction_pending" }),
  core(77.0, "node.create", { id: "repro-a", kind: "measurement", semantics: SEMANTICS }, measured("a")),
  core(77.1, "verify.add", { node: "meas-a", tier: "replayed", evidence: ["repro-a"] }, replayed("a")),
  core(77.2, "lifecycle.transition", { node: "cand-a", to: "reproduced" }),
  [77.5, GATE, "acceptance_gate", "lifecycle.transition", { node: "cand-a", to: "non_improving_current" }],
  core(78.0, "node.create", { id: "cmp-b-vs-init", kind: "comparison", semantics: SEMANTICS }),
  core(78.1, "support.add", { node: "cmp-b-vs-init", set_id: "eval", members: ["meas-b", "meas-init"] }),
  core(78.2, "support.add", { node: "cmp-b-vs-init", set_id: "repro", members: ["repro-b", "meas-init"] }),
  [78.5, lab("lab-b"), "lab", "node.create", { id: "claim-b-lower-j", kind: "claim" }],
  core(78.6, "support.add", { node: "claim-b-lower-j", set_id: "eval", members: ["meas-b"] }),
  core(95.0, "withdraw", { node: "meas-b", reason: "drill: seeded fault in the evaluator artifact" }),
];

export function buildDemo() {
  const entries = [], values = {};
  STEPS.forEach(([t, actor, role, type, body, vals], index) => {
    const event_id = `demo-e${String(index + 1).padStart(2, "0")}`;
    entries.push({ event: { event_id, seq: index + 1, type, actor_role: role, body }, ts: T(t), actor });
    if (vals) values[event_id] = vals;
  });
  const core = testKey("core");
  const envelopes = makeChain(DEMO_RUN, entries, values, { key_id: "core", privateKey: core.privateKey });
  return { envelopes, jsonl: `${envelopes.map((env) => JSON.stringify(env)).join("\n")}\n` };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const { jsonl, envelopes } = buildDemo();
  if (process.argv.includes("--check")) {
    const same = readFileSync(DEMO_PATH, "utf8") === jsonl;
    console.log(same ? `demo-run.jsonl is current (${envelopes.length} envelopes)` : "demo-run.jsonl differs from a fresh build");
    process.exit(same ? 0 : 1);
  }
  writeFileSync(DEMO_PATH, jsonl);
  console.log(`wrote ${DEMO_PATH} (${envelopes.length} envelopes)`);
}
