// node --test web/test/sentilab-scene.test.mjs
// The Package view's scene (web/public/sentilab/package/scene.mjs) and its CLI (scripts/sentilab-scene.mjs):
//   - buildScene is deterministic;
//   - only the verified projectable prefix moves or colours anything: the tampered, forged, dropped-event, oversize
//     and wrong-run vectors from contracts/view-envelope/vectors-view.json never contribute geometry or colour;
//   - the colour scale is fixed per run, and the move timeline exists per lab;
//   - the CLI (node reference verifier) builds the same scene as the browser path (view-core.mjs) for the demo.
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { canonical } from "../public/sentilab/canonical.mjs";
import { buildScene, sceneAt, runFrame, heatColor, contiguousPrefix, scaleTicks, describeEvent, STACK, TEMP_BASIS, TRACK_ORDER, LAB_TRACKS, SCENE_VERSION } from "../public/sentilab/package/scene.mjs";
import * as source from "../public/sentilab/package/source.mjs";
import { VIEW_PINS } from "../public/sentilab/view-pins.js";
import { testKey } from "./sentilab-keys.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const repo = join(here, "..", "..");
const CLI = join(repo, "scripts", "sentilab-scene.mjs");
const DEMO_FILE = join(repo, "web", "public", "sentilab", "demo-run.jsonl");
const DEMO_RUN = "demo-8c-0001";
const viewFile = JSON.parse(readFileSync(join(repo, "contracts", "view-envelope", "vectors-view.json"), "utf8"));
const demoText = readFileSync(DEMO_FILE, "utf8");

// Trust as the page builds it under ?pins=test (the vectors' rule), and per vector from its own pins and served keys.
const testTrust = { pins: [{ key_id: "core", key_sha256: testKey("core").sha256 }], keys: { core: testKey("core").raw }, testMode: true };
const vectorTrust = (view) => ({
  pins: view.pins.map((p) => ({ key_id: p.key_id, key_sha256: testKey(p.test_key).sha256 })),
  keys: Object.fromEntries(Object.entries(view.served_keys).map(([id, name]) => [id, testKey(name).raw])),
});
const json = (x) => JSON.parse(JSON.stringify(x));
const sceneOf = (v) => buildScene(v.prefixEnvelopes, v.projection);
const allChiplets = (scene) => scene.tracks.flatMap((t) => t.layout?.chiplets ?? []);

async function demoVerified() {
  return source.verifyRun(source.parseReplay(demoText), { runId: DEMO_RUN, trust: testTrust });
}

// ── determinism ───────────────────────────────────────────────────────────────────────────────────────────────
test("buildScene is deterministic: same prefix, same scene; delivery order and re-runs don't change it", async () => {
  const v = await demoVerified();
  const a = canonical(sceneOf(v));
  const b = canonical(sceneOf(v));
  assert.equal(a, b);
  const shuffled = [...v.prefixEnvelopes].reverse();
  assert.equal(canonical(buildScene(shuffled, v.projection)), a, "input order is not display order: seq is");
  const again = await demoVerified();
  assert.equal(canonical(sceneOf(again)), a, "a fresh verification gives the same scene");
  const frame = runFrame(v.prefixEnvelopes);
  for (let k = 0; k <= v.prefixEnvelopes.length; k += 1) {
    assert.equal(canonical(sceneAt(v.prefixEnvelopes, k, frame)), canonical(sceneAt(v.prefixEnvelopes, k, frame)), `k=${k}`);
  }
  assert.equal(sceneOf(v).v, SCENE_VERSION);
  assert.equal(canonical(sceneAt(v.prefixEnvelopes, v.prefixEnvelopes.length, frame)), a, "the scene at the end equals the whole-prefix scene");
});

// ── only the verified prefix ────────────────────────────────────────────────────────────────────────────────────
// Taint every envelope after the prefix with values that would be impossible to miss, then rebuild. The prefix must
// not move (a changed envelope after it can't join it), and nothing tainted may reach the scene.
const TAINT_ID = "TAINTCHIP";
const TAINT_T = 987.6;
function taint(env) {
  const out = structuredClone(env);
  if (out && typeof out === "object" && out.event && typeof out.event === "object") {
    out.values = {
      geometry: [{ id: TAINT_ID, xLL: 500, yLL: 500, w: 9, h: 9, layer: 0 }, { id: "c0", xLL: 400, yLL: 400, w: 10, h: 10, layer: 0 }],
      units: "mm", scenario_id: "taint", J: { value: TAINT_T, unit: "°C" }, W: { value: TAINT_T, metric_id: "taint" },
      center_temps: { [TAINT_ID]: TAINT_T, c0: TAINT_T, c1: TAINT_T, c2: TAINT_T, c3: TAINT_T },
    };
  }
  return out;
}
const hasTaint = (scene) => {
  const text = JSON.stringify(scene);
  return text.includes(TAINT_ID) || text.includes(String(TAINT_T)) || text.includes("taint") || /"[xy][01]?":\s*(400|500)/.test(text);
};

for (const chain of viewFile.chains) {
  const label = chain.name.split(":")[0];
  test(`${label}: the scene comes only from the verified prefix (K=${chain.expect.prefix_end}); nothing after it moves or colours anything`, async () => {
    const trust = vectorTrust(chain.view);
    const v = await source.verifyRun(structuredClone(chain.envelopes), { runId: chain.view.run_id, trust });
    assert.equal(v.prefixEnd, chain.expect.prefix_end);
    const clean = sceneOf(v);
    assert.equal(clean.at.seq, chain.expect.prefix_end, "the scene ends at K");

    const tainted = v.ordered.map((env, i) => (i < v.prefixCount ? structuredClone(env) : taint(env)));
    const tv = await source.verifyRun(tainted, { runId: chain.view.run_id, trust });
    assert.equal(tv.prefixEnd, v.prefixEnd, "tainting envelopes after the prefix doesn't change the prefix");
    const scene = sceneOf(tv);
    assert.equal(hasTaint(scene), false, "no tainted geometry, temperature, J or W in the scene");
    assert.equal(canonical(scene), canonical(clean), "the scene is the clean prefix's scene");

    // Every chiplet comes from geometry inside the prefix, and every temperature from a measurement inside it.
    const prefixText = JSON.stringify(v.prefixEnvelopes.map((env) => env.values ?? null));
    for (const c of allChiplets(scene)) {
      assert.ok(prefixText.includes(`"id":"${c.id}"`), `${c.id} geometry is from the prefix`);
      if (c.temp !== null) assert.ok(prefixText.includes(`"${c.id}":${c.temp}`), `${c.id} temperature ${c.temp} is from the prefix`);
    }
    if (chain.expect.no_acceptance || chain.expect.frozen) {
      assert.equal(scene.board, null, "a forged, tampered or skipped acceptance never reaches the board");
      assert.ok(!scene.timeline.some((e) => e.kind === "accept"));
    }
  });
}

test("forged and wrong-run replays (V5a, V5b, V9) draw nothing at all", async () => {
  for (const name of ["V5a", "V5b", "V9"]) {
    const chain = viewFile.chains.find((c) => c.name.startsWith(name));
    const v = await source.verifyRun(structuredClone(chain.envelopes), { runId: chain.view.run_id, trust: vectorTrust(chain.view) });
    const scene = sceneOf(v);
    assert.equal(v.prefixEnvelopes.length, 0, name);
    assert.equal(scene.footprint, null, `${name}: no footprint`);
    assert.equal(scene.scale, null, `${name}: no colour scale`);
    assert.ok(scene.tracks.every((t) => t.layout === null), `${name}: no layouts`);
    assert.deepEqual(scene.timeline, [], `${name}: no moves`);
  }
});

test("tampered (V3) and dropped-event (V8) chains: the frozen scene is exactly the prefix's", async () => {
  const v3 = viewFile.chains.find((c) => c.name.startsWith("V3"));
  const r3 = await source.verifyRun(structuredClone(v3.envelopes), { runId: v3.view.run_id, trust: vectorTrust(v3.view) });
  const s3 = sceneOf(r3);
  assert.equal(r3.prefixEnd, 3);
  assert.equal(s3.tracks.find((t) => t.track === "lab-a").layout.ref.id, "K1", "the candidate before the break is drawn");
  assert.ok(allChiplets(s3).every((c) => c.temp === null && c.color === null), "the tampered measurement (seq 4) colours nothing");
  assert.equal(s3.scale, null);

  const v8 = viewFile.chains.find((c) => c.name.startsWith("V8"));
  const r8 = await source.verifyRun(structuredClone(v8.envelopes), { runId: v8.view.run_id, trust: vectorTrust(v8.view) });
  const s8 = sceneOf(r8);
  assert.equal(r8.prefixEnd, 6);
  assert.equal(r8.label, "chain broken after seq 6; board frozen at seq 6");
  const k8 = s8.tracks.find((t) => t.track === "lab-a").layout;
  assert.equal(k8.lifecycle, "evaluated", "the board is frozen before the dropped withdraw: never 'accepted'");
  assert.equal(s8.board, null);
});

test("buildScene keeps only the contiguous run from seq 1, even if a caller passes more", async () => {
  const v8 = viewFile.chains.find((c) => c.name.startsWith("V8"));
  const r8 = await source.verifyRun(structuredClone(v8.envelopes), { runId: v8.view.run_id, trust: vectorTrust(v8.view) });
  const overreach = r8.ordered;                         // seq 1..6, then 8..10 after the dropped seq 7
  assert.deepEqual(contiguousPrefix(overreach).map((e) => e.event.seq), [1, 2, 3, 4, 5, 6]);
  assert.equal(canonical(buildScene(overreach, null)), canonical(sceneOf(r8)));
  assert.equal(canonical(buildScene(overreach, r8.projection)), canonical(sceneOf(r8)), "a projection for a different list is recomputed");
});

test("events project() rejects contribute nothing: a lab's self-acceptance never reaches the board", () => {
  const run = { run_id: "r", arm: "live", family: "f", seed: 1, ticket_id: "t" };
  const env = (seq, lab, role, type, body, values) => ({ v: "view-envelope/0.4", event: { event_id: `e${seq}`, seq, type, actor_role: role, body }, ts: `2026-11-01T14:00:0${seq}.000Z`,
    actor: { agent_id: null, life_id: null, lab, grant_id: null }, run, ...(values ? { values } : {}), prev_hash: "x", hash: "x", sig: { key_id: "core", alg: "ed25519", value: "x" } });
  const geo = (x) => ({ geometry: [{ id: "CPU0", xLL: x, yLL: 0, w: 5, h: 5, layer: 0 }], units: "mm" });
  const prefix = [
    env(1, "lab-a", "lab", "node.create", { id: "K", kind: "candidate" }, geo(0)),
    env(2, "lab-b", "lab", "node.create", { id: "K", kind: "candidate" }, geo(30)),          // duplicate id: rejected
    env(3, "lab-a", "lab", "lifecycle.transition", { node: "K", to: "validated" }),
    env(4, "lab-a", "lab", "lifecycle.transition", { node: "K", to: "accepted" }),           // illegal + not the gate: rejected
  ];
  const scene = buildScene(prefix, null);
  assert.deepEqual(scene.rejected.map((r) => r.event_id).sort(), ["e2", "e4"]);
  assert.equal(scene.tracks.find((t) => t.track === "lab-b").layout, null, "the rejected duplicate draws nothing");
  assert.equal(scene.tracks.find((t) => t.track === "lab-a").layout.chiplets[0].x, 0);
  assert.equal(scene.board, null);
  assert.equal(scene.footprint.extent.x1, 5, "rejected geometry doesn't widen the footprint");
});

// ── fixed colour scale ──────────────────────────────────────────────────────────────────────────────────────────
test("the colour scale is fixed per run: one scale at every playhead position, one colour per value", async () => {
  const v = await demoVerified();
  const frame = runFrame(v.prefixEnvelopes, v.projection);
  assert.deepEqual(json(frame.scale), { min: 65, max: 100, unit: "°C", fixed: true, basis: TEMP_BASIS });
  const colourOf = new Map();
  for (let k = 0; k <= v.prefixEnvelopes.length; k += 1) {
    const scene = sceneAt(v.prefixEnvelopes, k, frame);
    if (k > 0) {
      assert.deepEqual(scene.scale, frame.scale, `scale at k=${k}`);
      assert.deepEqual(scene.footprint, frame.footprint, `footprint at k=${k}`);
    }
    for (const c of allChiplets(scene)) {
      if (c.temp === null) { assert.equal(c.color, null); continue; }
      assert.equal(c.color, heatColor(c.temp, frame.scale), `${c.id} at k=${k}`);
      if (colourOf.has(c.temp)) assert.equal(colourOf.get(c.temp), c.color, `${c.temp} has one colour in the run`);
      colourOf.set(c.temp, c.color);
    }
  }
  assert.ok(colourOf.size > 10, "the run has many coloured values");
  // Every temperature in the run is inside the scale, and the ends map to the ramp's ends.
  for (const t of colourOf.keys()) assert.ok(t >= frame.scale.min && t <= frame.scale.max);
  assert.equal(heatColor(65, frame.scale), "#112a48");
  assert.equal(heatColor(100, frame.scale), "#e45138");
  assert.equal(heatColor(250, frame.scale), "#e45138", "out of range clamps; it never rescales");
  assert.deepEqual(scaleTicks(frame.scale), [65, 70, 75, 80, 85, 90, 95, 100]);
});

test("the stack is declared schematic, and the footprint is the geometry's extent plus a margin", async () => {
  const scene = sceneOf(await demoVerified());
  assert.equal(scene.stack.label, "schematic stack");
  assert.equal(scene.stack.schematic, true);
  assert.deepEqual(scene.stack.layers.map((l) => l.layer), ["substrate", "interposer", "chiplets", "lid"]);
  assert.deepEqual(scene.stack.layers[1].footprint, scene.footprint.interposer);
  assert.equal(scene.stack.layers[3].outline_only, true);
  assert.match(scene.basis.stack, /schematic stack: .*not from the run and not to scale/);
  assert.equal(scene.basis.temps, "chiplet-centre temperatures from the solver; not a field");
  const { extent, interposer, substrate } = scene.footprint;
  assert.deepEqual(json(extent), { x0: 1, y0: 1, x1: 43, y1: 35 });
  assert.equal(interposer.x0, extent.x0 - STACK.interposer_margin_mm);
  assert.equal(interposer.y1, extent.y1 + STACK.interposer_margin_mm);
  assert.equal(substrate.x1, interposer.x1 + STACK.substrate_margin_mm);
  assert.ok(STACK.hbm_mm > STACK.die_mm, "memory stacks are drawn taller");
  const hbm = allChiplets(scene).filter((c) => c.kind === "hbm").map((c) => c.id);
  assert.deepEqual([...new Set(hbm)].sort(), ["HBM0", "HBM1", "HBM2", "HBM3"]);
});

// ── timeline ────────────────────────────────────────────────────────────────────────────────────────────────────
test("a move timeline exists per lab (parent layout -> candidate, per chiplet, with seq and ts), and for the board", async () => {
  const scene = sceneOf(await demoVerified());
  assert.deepEqual(scene.tracks.map((t) => t.track), TRACK_ORDER);
  for (const lab of LAB_TRACKS) {
    const moves = scene.timeline.filter((e) => e.kind === "move" && e.track === lab);
    assert.equal(moves.length, 1, lab);
    const [m] = moves;
    assert.equal(m.from.id, "meas-init", `${lab} starts from the initial layout`);
    assert.equal(m.to.id, scene.tracks.find((t) => t.track === lab).layout.ref.id);
    assert.ok(Number.isSafeInteger(m.seq) && typeof m.ts === "string");
    assert.equal(m.chiplets.length, 8);
    for (const c of m.chiplets) {
      assert.ok(c.from && c.to, `${lab} ${c.id} exists in both layouts`);
      assert.equal(c.moved, c.from.x !== c.to.x || c.from.y !== c.to.y, `${lab} ${c.id} moved flag`);
    }
    assert.ok(m.chiplets.some((c) => c.moved), `${lab} moves something`);
    assert.ok(m.chiplets.filter((c) => c.id.startsWith("HBM")).every((c) => !c.moved), "memory stays in the corners in this fixture");
  }
  const board = scene.timeline.filter((e) => e.track === "board");
  assert.deepEqual(board.map((e) => [e.kind, e.seq]), [["initial", 1], ["move", 32], ["accept", 32]]);
  assert.equal(board[1].from.id, "meas-init");
  assert.equal(board[1].to.id, "cand-b");
  const seqs = scene.timeline.map((e) => e.seq);
  assert.deepEqual(seqs, [...seqs].sort((a, b) => a - b), "the timeline is in seq order");
  assert.ok(scene.timeline.every((e) => describeEvent(e).startsWith(`seq ${e.seq}`)));
});

test("demo story on the package: board = initial layout until seq 32, then cand-b; the drill re-sources its temperatures", async () => {
  const v = await demoVerified();
  const frame = runFrame(v.prefixEnvelopes);
  const at = (k) => sceneAt(v.prefixEnvelopes, k, frame);
  assert.equal(at(0).tracks[0].layout, null);
  assert.equal(at(1).tracks[0].showing, "initial");
  assert.equal(at(31).tracks[0].layout.ref.id, "meas-init");
  assert.equal(at(31).board, null);
  assert.equal(at(32).tracks[0].showing, "accepted");
  assert.equal(at(32).board.candidate, "cand-b");
  assert.equal(at(43).tracks[0].layout.temps_from.measurement, "meas-b");
  const end = at(44).tracks[0].layout;
  assert.equal(end.temps_from.measurement, "repro-b", "after the drill the surviving reproduction supplies the values");
  assert.equal(end.temps_from.via_alternative, true);
  assert.deepEqual(end.temps_from.broken_sets, ["eval"]);
  assert.ok(end.chiplets.every((c) => c.temp_state === "valid"));
  assert.deepEqual(at(44).drill.withdrawn.map((w) => w.node), ["meas-b"]);
  assert.deepEqual(at(44).drill.stale.map((s) => s.node), ["claim-b-lower-j"]);
  const c = at(44).tracks.find((t) => t.track === "lab-c").layout;
  assert.equal(c.lifecycle, "rejected_constraints");
  assert.deepEqual(c.overlaps.map((o) => [o.a, o.b]), [["CPU1", "HBM3"]], "the overlap that failed the constraint check is a geometry fact");
  assert.ok(c.chiplets.every((x) => x.temp === null), "a rejected candidate has no temperatures");
});

test("a withdrawn measurement turns its values stale (V2 correction drill)", async () => {
  const v2 = viewFile.chains.find((c) => c.name.startsWith("V2"));
  const r = await source.verifyRun(structuredClone(v2.envelopes), { runId: v2.view.run_id, trust: vectorTrust(v2.view) });
  const frame = runFrame(r.prefixEnvelopes);
  const before = sceneAt(r.prefixEnvelopes, 9, frame).tracks.find((t) => t.track === "lab-a").layout;
  const after = sceneAt(r.prefixEnvelopes, 10, frame).tracks.find((t) => t.track === "lab-a").layout;
  assert.ok(before.chiplets.every((c) => c.temp_state === "valid"));
  assert.equal(after.validity, "stale");
  assert.ok(after.chiplets.every((c) => c.temp_state === "stale"), "every value from the withdrawn measurement is stale");
  assert.deepEqual(after.chiplets.map((c) => c.color), before.chiplets.map((c) => c.color), "the value's colour is the scale's; the renderer desaturates it");
  const w = sceneAt(r.prefixEnvelopes, 10, frame).timeline.find((e) => e.kind === "withdraw");
  assert.equal(w.drill, true);
  assert.ok(w.affected.includes("K2"));
});

// ── the source adapter's trust rule ───────────────────────────────────────────────────────────────────────────────
test("?pins=test is honoured on exactly the Lab view's local hosts, and never with the production pins", async () => {
  for (const host of ["localhost", "127.0.0.1", "[::1]"]) assert.equal(source.testPinsAllowed(host), true, host);
  for (const host of ["sentilab.example", "sentilab.dev", "127.0.0.1.nip.io", "localhost.example", "", "0.0.0.0"]) assert.equal(source.testPinsAllowed(host), false, host);
  const labJs = readFileSync(join(repo, "web", "public", "sentilab", "lab.js"), "utf8");
  const m = /TEST_PIN_HOSTS\s*=\s*new Set\(\[([^\]]*)\]\)/.exec(labJs);
  if (m) assert.deepEqual(JSON.parse(`[${m[1]}]`), [...source.TEST_PIN_HOSTS], "same hosts as lab.js");
  const refused = await source.setupTrust({ hostname: "sentilab.example", wantsTest: true, fetchKey: async () => ({ keys: {}, note: "no key served" }) });
  assert.equal(refused.testMode, false);
  assert.deepEqual(refused.pins, VIEW_PINS.map((p) => ({ key_id: p.key_id, key_sha256: p.key_sha256 })));
  assert.match(refused.note, /only honoured on a local server/);
  const local = await source.setupTrust({ hostname: "127.0.0.1", wantsTest: true });
  assert.equal(local.testMode, true);
  assert.deepEqual(local.pins, testTrust.pins);
  const v = await source.verifyRun(source.parseReplay(demoText), { runId: DEMO_RUN, trust: refused });
  assert.equal(v.prefixEnd, 0, "the demo verifies nothing under the production pins");
  assert.equal(sceneOf(v).footprint, null);
});

// ── the CLI ───────────────────────────────────────────────────────────────────────────────────────────────────────
const cli = (...args) => spawnSync(process.execPath, [CLI, ...args], { encoding: "utf8" });

test("CLI build (node reference verifier) equals the browser path's buildScene for the demo", async () => {
  const r = cli("build", DEMO_FILE, "--run", DEMO_RUN, "--pins", "test");
  assert.equal(r.status, 0, r.stderr);
  const out = JSON.parse(r.stdout);
  assert.equal(out.trust.mode, "test");
  assert.deepEqual(out.verification.prefix_end, 44);
  assert.equal(out.verification.chain_ok, true);
  const browser = sceneOf(await demoVerified());
  assert.deepEqual(out.scene, json(browser));
  // --at gives the browser's scene at that playhead position.
  const at = JSON.parse(cli("build", DEMO_FILE, "--run", DEMO_RUN, "--pins", "test", "--at", "32").stdout);
  const v = await demoVerified();
  assert.deepEqual(at.scene, json(sceneAt(v.prefixEnvelopes, 32, runFrame(v.prefixEnvelopes))));
});

test("CLI under the production pins: nothing verifies, the scene is empty, and only --strict exits non-zero", () => {
  const plain = cli("build", DEMO_FILE, "--run", DEMO_RUN);
  assert.equal(plain.status, 0, plain.stderr);
  const out = JSON.parse(plain.stdout);
  assert.equal(out.trust.mode, "production");
  assert.equal(out.verification.verified, 0);
  assert.equal(out.verification.prefix_end, 0);
  assert.equal(out.verification.label, "chain broken after seq 0; board frozen at seq 0");
  assert.equal(out.scene.footprint, null);
  assert.ok(out.scene.tracks.every((t) => t.layout === null));
  assert.equal(cli("build", DEMO_FILE, "--run", DEMO_RUN, "--strict").status, 2);
  assert.equal(cli("build", DEMO_FILE, "--run", DEMO_RUN, "--pins", "test", "--strict").status, 0, "an unbroken chain passes --strict");
});

test("CLI export writes the same JSON as build; bad usage exits 1 with a JSON error", () => {
  const dir = mkdtempSync(join(tmpdir(), "sentilab-scene-"));
  try {
    const file = join(dir, "scene.json");
    const r = cli("export", DEMO_FILE, "--out", file, "--pins", "test");
    assert.equal(r.status, 0, r.stderr);
    const summary = JSON.parse(r.stdout);
    assert.equal(summary.run.from, "file", "no --run: the run is taken from the file, and the output says so");
    const written = JSON.parse(readFileSync(file, "utf8"));
    const built = JSON.parse(cli("build", DEMO_FILE, "--pins", "test").stdout);
    assert.equal(written.command, "export");
    assert.deepEqual({ ...written, command: "build" }, built);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
  for (const args of [["nope"], ["build"], ["export", DEMO_FILE], ["build", DEMO_FILE, "--pins", "prod"], ["build", DEMO_FILE, "--bogus"], ["build", join(repo, "no-such-file.jsonl")]]) {
    const r = cli(...args);
    assert.equal(r.status, 1, args.join(" "));
    assert.equal(JSON.parse(r.stderr).error, "usage");
  }
  const help = JSON.parse(execFileSync(process.execPath, [CLI, "help"], { encoding: "utf8" }));
  assert.deepEqual(Object.keys(help.commands), ["build", "export", "help"]);
});
