// node --test web/test/sentilab-scene.test.mjs
// The Package view's scene (web/public/sentilab/package/scene.mjs) and its CLI (scripts/sentilab-scene.mjs):
//   - buildScene is deterministic;
//   - only the verified projectable prefix moves or colours anything: the tampered, forged, dropped-event, oversize,
//     padded, lone-surrogate, conflicting and wrong-run vectors from contracts/view-envelope-v0.5/vectors-view.json
//     never contribute geometry or colour (verification is VIEW ENVELOPE v0.5 over raw rows, through source.mjs);
//   - the colour scale is fixed per run, and the move timeline exists per lab;
//   - the live path (source.mjs over paging.mjs: cursor, cursor_hash, 409/413/terminal states, track() and liveLabel
//     with frozen and the run status) gives the reference's recorded trace for every v0.6.2 paging scenario (C1-C17),
//     poll for poll, and the recorded label for every v0.6.2 label case; LIVE never shows next to a frozen board or
//     during catch-up; a finished run shows ENDED;
//   - the CLI (v0.5 node reference verifier) builds the same scene as the browser path for the demo.
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { closeSync, ftruncateSync, mkdtempSync, openSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createHash } from "node:crypto";
import { Worker } from "node:worker_threads";

import { canonical } from "../public/sentilab/canonical.mjs";
import { buildScene, sceneAt, runFrame, heatColor, contiguousPrefix, scaleTicks, describeEvent, STACK, TEMP_BASIS, TRACK_ORDER, LAB_TRACKS, SCENE_VERSION, SUPPORTED_UNITS, BOUNDS, MAX_TICKS, readGeometry, readTemps } from "../public/sentilab/package/scene.mjs";
import { reconcile, extendsPrefix } from "../public/sentilab/package/playhead.mjs";
import { TrackAnimation } from "../public/sentilab/package/render.mjs";
import { makeChain, signEnvelope } from "../../contracts/view-envelope-v0.5/view-envelope.mjs";
import * as refPaging from "../../contracts/view-envelope-v0.6.2/paging.mjs";
import { viewHref } from "../public/sentilab/view-links.mjs";
import * as cliModule from "../../scripts/sentilab-scene.mjs";
import * as source from "../public/sentilab/package/source.mjs";
import { VIEW_PINS } from "../public/sentilab/view-pins.js";
import { testKey } from "./sentilab-keys.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const repo = join(here, "..", "..");
const CLI = join(repo, "scripts", "sentilab-scene.mjs");
const DEMO_FILE = join(repo, "web", "public", "sentilab", "demo-run.jsonl");
const DEMO_RUN = "demo-8c-0001";
const viewFile = JSON.parse(readFileSync(join(repo, "contracts", "view-envelope-v0.5", "vectors-view.json"), "utf8"));
const pagingFile = JSON.parse(readFileSync(join(repo, "contracts", "view-envelope-v0.6.2", "vectors-paging.json"), "utf8"));
const demoBytes = () => new Uint8Array(readFileSync(DEMO_FILE));
const enc = (text) => new TextEncoder().encode(text);
const lenient = (bytes) => new TextDecoder("utf-8", { fatal: false, ignoreBOM: true }).decode(bytes);
const demoEnvelopes = () => refPaging.splitRows(demoBytes()).map((row) => JSON.parse(lenient(row)));

// Trust as the page builds it under ?pins=test (the vectors' rule), and per vector from its own pins and served keys.
const testTrust = { pins: [{ key_id: "core", key_sha256: testKey("core").sha256 }], keys: { core: testKey("core").raw }, testMode: true };
const vectorTrust = (view) => ({
  pins: view.pins.map((p) => ({ key_id: p.key_id, key_sha256: testKey(p.test_key).sha256 })),
  keys: Object.fromEntries(Object.entries(view.served_keys).map(([id, name]) => [id, testKey(name).raw])),
});
const json = (x) => JSON.parse(JSON.stringify(x));
const sceneOf = (v) => buildScene(v.prefixEnvelopes, v.projection);
const allChiplets = (scene) => scene.tracks.flatMap((t) => t.layout?.chiplets ?? []);

// Every verification goes through the page's own path: raw bytes into source.verifyReplayFile().
async function verifyLines(lines, runId, trust) {
  const r = await source.verifyReplayFile(enc(lines.map((line) => `${line}\n`).join("")), { runId, trust });
  assert.ok(r.ok, r.error);
  return r.verification;
}
const verifyEnvs = (envelopes, runId, trust) => verifyLines(envelopes.map((env) => JSON.stringify(env)), runId, trust);
async function demoVerified(trust = testTrust) {
  const r = await source.verifyReplayFile(demoBytes(), { runId: DEMO_RUN, trust });
  assert.ok(r.ok);
  return r.verification;
}
// The v0.5 vectors' delivery recipe (padding, delivery orders, every line twice), as the parity test builds it.
const utf8Bytes = (text) => Buffer.byteLength(text, "utf8");
function buildLines(envelopes, send) {
  const line = (env) => {
    const text = JSON.stringify(env);
    return send.pad && env.event.seq === send.pad.seq ? `{${" ".repeat(send.pad.line_bytes - utf8Bytes(text))}${text.slice(1)}` : text;
  };
  const lists = send.orders ? send.orders.map((list) => list.map((eid) => envelopes.find((env) => env.event.event_id === eid))) : [envelopes];
  return lists.map((list) => {
    const lines = list.map(line);
    return send.twice ? [...lines, ...lines] : lines;
  });
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
function taintLine(line) {
  let env;
  try { env = JSON.parse(line); } catch { return line; }
  return env && typeof env === "object" && env.event ? JSON.stringify(taint(env)) : line;
}
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
  return text.includes(TAINT_ID) || text.includes(String(TAINT_T)) || text.includes("taint") || /"[xy][01]?":\s*(400|500)\b/.test(text);
};

for (const chain of viewFile.chains) {
  const label = chain.name.split(":")[0];
  test(`${label}: the scene comes only from the verified prefix (K=${chain.expect.prefix_end}); nothing after it moves or colours anything`, async () => {
    const trust = vectorTrust(chain.view);
    const lines = buildLines(chain.envelopes, chain.send)[0];
    const v = await verifyLines(lines, chain.view.run_id, trust);
    assert.equal(v.prefixEnd, chain.expect.prefix_end);
    const clean = sceneOf(v);
    assert.equal(clean.at.seq, chain.expect.prefix_end, "the scene ends at K");

    const inPrefix = new Set(v.inputIndex.slice(0, v.prefixCount));
    const afterPrefix = new Set(v.inputIndex.slice(v.prefixCount));
    const tainted = lines.map((line, i) => (afterPrefix.has(i) && !inPrefix.has(i) ? taintLine(line) : line));
    const tv = await verifyLines(tainted, chain.view.run_id, trust);
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
    const v = await verifyLines(buildLines(chain.envelopes, chain.send)[0], chain.view.run_id, vectorTrust(chain.view));
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
  const r3 = await verifyLines(buildLines(v3.envelopes, v3.send)[0], v3.view.run_id, vectorTrust(v3.view));
  const s3 = sceneOf(r3);
  assert.equal(r3.prefixEnd, 3);
  assert.equal(s3.tracks.find((t) => t.track === "lab-a").layout.ref.id, "K1", "the candidate before the break is drawn");
  assert.ok(allChiplets(s3).every((c) => c.temp === null && c.color === null), "the tampered measurement (seq 4) colours nothing");
  assert.equal(s3.scale, null);

  const v8 = viewFile.chains.find((c) => c.name.startsWith("V8"));
  const r8 = await verifyLines(buildLines(v8.envelopes, v8.send)[0], v8.view.run_id, vectorTrust(v8.view));
  const s8 = sceneOf(r8);
  assert.equal(r8.prefixEnd, 6);
  assert.equal(r8.label, "chain broken after seq 6; board frozen at seq 6");
  const k8 = s8.tracks.find((t) => t.track === "lab-a").layout;
  assert.equal(k8.lifecycle, "evaluated", "the board is frozen before the dropped withdraw: never 'accepted'");
  assert.equal(s8.board, null);
});

test("buildScene keeps only the contiguous run from seq 1, even if a caller passes more", async () => {
  const v8 = viewFile.chains.find((c) => c.name.startsWith("V8"));
  const r8 = await verifyLines(buildLines(v8.envelopes, v8.send)[0], v8.view.run_id, vectorTrust(v8.view));
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
  const r = await verifyLines(buildLines(v2.envelopes, v2.send)[0], v2.view.run_id, vectorTrust(v2.view));
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
  const v = await demoVerified(refused);
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

// ── P2-1: a verification change while paused, playing or mid-glide ───────────────────────────────────────────────
// reconcile() is the one rule the page runs on every verification change (package.js adoptVerification).
const tamperAt = (envelopes, seq) => envelopes.map((env) => {
  if (env.event.seq !== seq) return structuredClone(env);
  const bad = structuredClone(env);
  bad.event.body = { ...bad.event.body, note: "changed after signing" };
  return bad;
});
const productionTrust = { pins: VIEW_PINS.map((p) => ({ key_id: p.key_id, key_sha256: p.key_sha256 })), keys: {} };
async function demoAt38() {
  const v44 = await demoVerified();
  const first = reconcile({ prefix: [], frame: null, cursor: 0, following: false }, v44);
  return { v44, view: { prefix: first.prefix, frame: first.frame, cursor: 38, following: false } };
}
const positions = (layout) => (layout?.chiplets ?? []).map((c) => `${c.id}@${c.x},${c.y}`).sort();

test("paused at seq 38, K drops from 44 to 3: playhead clamped to K, scene and frame rebuilt from the new prefix", async () => {
  const { v44, view } = await demoAt38();
  assert.equal(sceneAt(v44.prefixEnvelopes, 38, view.frame).board.candidate, "cand-b", "before: the accepted package is drawn");
  const v3 = await verifyEnvs(tamperAt(demoEnvelopes(), 4), DEMO_RUN, testTrust);
  assert.equal(v3.prefixCount, 3, "a changed seq 4 ends the prefix at 3");
  const r = reconcile(view, v3);
  assert.equal(r.cursor, 3, "the playhead is clamped to K");
  assert.equal(r.scene.at.seq, 3);
  assert.equal(r.reset, true, "every animation is cut");
  assert.equal(r.grew, false);
  assert.equal(r.scene.board, null, "the accepted cand-b is gone");
  assert.equal(r.scene.tracks[0].showing, "initial");
  assert.ok(!JSON.stringify(r.scene).includes("cand-b\",\"lab\":\"lab-b\",\"seq\":32"), "no acceptance at seq 32");
  assert.ok(!r.scene.timeline.some((e) => e.seq > 3), "nothing after K is in the timeline");
  // The frame is recomputed from seq 1..3 alone: the scale no longer stretches to values that left the prefix.
  assert.deepEqual(r.frame, runFrame(v3.prefixEnvelopes, v3.projection));
  assert.deepEqual([r.frame.scale.min, r.frame.scale.max], [70, 100]);
  assert.notDeepEqual(r.frame.scale, view.frame.scale, "the old extrema (65) are cleared");
  assert.equal(canonical(r.scene), canonical(sceneAt(v3.prefixEnvelopes, 3, runFrame(v3.prefixEnvelopes))));
});

test("K drops to 0 (nothing verifies any more): the playhead goes to 0 and nothing is drawn", async () => {
  const { view } = await demoAt38();
  const v0 = await demoVerified(productionTrust);
  assert.equal(v0.prefixCount, 0);
  const r = reconcile(view, v0);
  assert.equal(r.cursor, 0);
  assert.deepEqual(r.frame, { scale: null, footprint: null });
  assert.ok(r.scene.tracks.every((t) => t.layout === null));
  assert.deepEqual(r.scene.timeline, []);
  assert.equal(r.reset, true);
  const following = reconcile({ ...view, following: true }, v0);
  assert.equal(following.cursor, 0, "following the live edge means sitting at K, here 0");
});

test("K drops mid-glide: the glide, its ghosts and the acceptance pulse are cut; nothing from the old prefix finishes", async () => {
  const { v44, view } = await demoAt38();
  const frame = view.frame;
  const s31 = sceneAt(v44.prefixEnvelopes, 31, frame), s32 = sceneAt(v44.prefixEnvelopes, 32, frame);
  const move = s32.timeline.find((e) => e.kind === "move" && e.track === "board" && e.seq === 32);
  const anim = new TrackAnimation();
  anim.reset(s31.tracks[0].layout, { now: 0 });
  anim.set(s32.tracks[0].layout, { move, animate: true, pulse: true, accepted: true, now: 1000 });
  const mid = anim.frame(1350);
  assert.equal(mid.active, true, "mid-glide");
  assert.ok(mid.ghosts.length > 0 && mid.pulse !== null);
  const cpu1 = mid.chiplets.find((c) => c.id === "CPU1");
  assert.ok(cpu1.x !== 22 && cpu1.x !== 23, "CPU1 is between the initial layout and cand-b");

  const v3 = await verifyEnvs(tamperAt(demoEnvelopes(), 4), DEMO_RUN, testTrust);
  const r = reconcile({ ...view, cursor: 32 }, v3);
  assert.equal(r.reset, true);
  anim.reset(r.scene.tracks[0].layout, { accepted: r.scene.tracks[0].showing === "accepted", now: 1350 });
  for (const t of [1350, 1700, 5000]) {
    const f = anim.frame(t);
    assert.equal(f.active, false, `t=${t}: nothing in flight`);
    assert.deepEqual(f.ghosts, []);
    assert.equal(f.pulse, null);
    assert.equal(f.accepted, false);
    assert.deepEqual(f.chiplets.map((c) => `${c.id}@${c.x},${c.y}`).sort(), positions(r.scene.tracks[0].layout), "exactly the new prefix's layout");
  }
  // K -> 0 mid-glide: the package disappears at once.
  const anim0 = new TrackAnimation();
  anim0.reset(s31.tracks[0].layout, { now: 0 });
  anim0.set(s32.tracks[0].layout, { move, animate: true, pulse: true, now: 1000 });
  anim0.reset(null, { now: 1300 });
  assert.deepEqual(anim0.frame(1300).chiplets, []);
  assert.equal(anim0.frame(1300).active, false);
});

test("a growing prefix keeps a paused playhead, widens the frame, and animates only a single followed step", async () => {
  const all = demoEnvelopes();
  const v20 = await verifyEnvs(all.slice(0, 20), DEMO_RUN, testTrust);
  const v21 = await verifyEnvs(all.slice(0, 21), DEMO_RUN, testTrust);
  const v44 = await demoVerified();
  assert.equal(extendsPrefix(v20.prefixEnvelopes, v44.prefixEnvelopes), true);
  const base = reconcile({ prefix: [], frame: null, cursor: 0, following: false }, v20);
  const paused = reconcile({ prefix: base.prefix, frame: base.frame, cursor: 15, following: false }, v44);
  assert.equal(paused.cursor, 15, "paused inside K: the playhead stays");
  assert.equal(paused.grew, true);
  assert.ok(paused.frame.scale.min <= base.frame.scale.min && paused.frame.scale.max >= base.frame.scale.max, "the frame only widens");
  const followed = reconcile({ prefix: base.prefix, frame: base.frame, cursor: 20, following: true }, v21);
  assert.equal(followed.cursor, 21);
  assert.equal(followed.stepped, true);
  assert.equal(followed.reset, false, "one new envelope at the live edge glides");
  const jumped = reconcile({ prefix: base.prefix, frame: base.frame, cursor: 20, following: true }, v44);
  assert.equal(jumped.cursor, 44);
  assert.equal(jumped.reset, true, "a burst is a jump cut");
  const forked = v44.prefixEnvelopes.map((env) => (env.event.seq === 30 ? { ...structuredClone(env), hash: "0".repeat(64) } : env));
  assert.equal(extendsPrefix(v44.prefixEnvelopes, forked), false, "a different envelope at an old seq is not growth");
  assert.equal(extendsPrefix(v44.prefixEnvelopes, v20.prefixEnvelopes), false, "a shorter prefix is not growth");
});

// ── P2-2 and P2-3: units and numeric bounds ──────────────────────────────────────────────────────────────────────
// Real signed runs (reference makeChain, core TEST key), so the same values go through the verifier and the CLI.
const RUN = { run_id: "units-0001", arm: "live", family: "fixture-units", seed: 1, ticket_id: "ticket-units" };
const ACTOR = Object.fromEntries([["core", { agent_id: null, life_id: null, lab: "core", grant_id: null }],
  ...LAB_TRACKS.map((lab) => [lab, { agent_id: `agent-${lab}`, life_id: `life-${lab}`, lab, grant_id: `grant-${lab}` }])]);
const SEM = { task_contract: "tc-units", metric_id: "max-chiplet-center-temp-c", evaluator_version: "fixture-no-solver", coordinate_frame: "pkg-lower-left-mm" };
// steps: [lab, type, body, values?] in seq order.
function signedRun(steps) {
  const entries = [], values = {};
  steps.forEach(([lab, type, body, vals], i) => {
    const event_id = `u${i + 1}`;
    entries.push({ event: { event_id, seq: i + 1, type, actor_role: lab === "core" ? "core" : "lab", body }, ts: `2026-11-01T15:00:${String(i).padStart(2, "0")}.000Z`, actor: ACTOR[lab] });
    if (vals) values[event_id] = vals;
  });
  return makeChain(RUN, entries, values, { key_id: "core", privateKey: testKey("core").privateKey });
}
const geo = (units, rects) => ({ geometry: rects.map(([id, x, y, w, h]) => ({ id, xLL: x, yLL: y, w, h, layer: 0 })), ...(units === undefined ? {} : { units }) });
const meas = (id, unit, temps, J = Math.max(...Object.values(temps))) => ["core", "node.create", { id, kind: "measurement", semantics: SEM }, { J: unit === undefined ? { value: J } : { value: J, unit }, W: { value: 100, metric_id: "hpwl-mm" }, center_temps: temps }];
const cand = (lab, id, units, rects) => [lab, "node.create", { id, kind: "candidate" }, geo(units, rects)];
const support = (node, m) => ["core", "support.add", { node, set_id: "eval", members: [m] }];
async function verifiedScene(envelopes) {
  const v = await verifyEnvs(envelopes, RUN.run_id, testTrust);
  assert.equal(v.chainOk, true, "the chain itself verifies: refusals are not chain errors");
  return { v, scene: sceneOf(v) };
}
const track = (scene, lab) => scene.tracks.find((t) => t.track === lab).layout;
const everyNumberFinite = (x) => (typeof x === "number" ? Number.isFinite(x) : Array.isArray(x) ? x.every(everyNumberFinite) : x && typeof x === "object" ? Object.values(x).every(everyNumberFinite) : true);
// Every number the scene exports as data (the declared bounds and stack constants aside).
function dataNumbers(x, out = []) {
  if (typeof x === "number") out.push(x);
  else if (Array.isArray(x)) x.forEach((v) => dataNumbers(v, out));
  else if (x && typeof x === "object") for (const [k, v] of Object.entries(x)) if (k !== "bounds" && k !== "constants") dataNumbers(v, out);
  return out;
}

test("units: 25 °C and 298.15 K are one temperature on one °C scale; m and µm are placed in mm", async () => {
  const { scene } = await verifiedScene(signedRun([
    cand("lab-a", "KA", "m", [["A", 0.01, 0, 0.01, 0.005]]),
    cand("lab-b", "KB", "µm", [["A", 2000, 3000, 5000, 4000]]),
    meas("MA", "°C", { A: 25 }),
    meas("MB", "K", { A: 298.15 }),
    support("KA", "MA"),
    support("KB", "MB"),
  ]));
  assert.deepEqual(scene.errors, []);
  assert.equal(scene.units.length, "mm");
  assert.equal(scene.units.temperature, "°C");
  assert.deepEqual(scene.units.supported, SUPPORTED_UNITS);
  assert.deepEqual([scene.scale.min, scene.scale.max, scene.scale.unit], [20, 30, "°C"], "one value, 25 °C, not a 25 to 300 scale");
  const a = track(scene, "lab-a"), b = track(scene, "lab-b");
  assert.deepEqual(a.chiplets.map((c) => [c.x, c.y, c.w, c.h]), [[10, 0, 10, 5]], "0.01 m is 10 mm");
  assert.equal(a.units, "mm");
  assert.equal(a.declared_units, "m");
  assert.deepEqual(b.chiplets.map((c) => [c.x, c.y, c.w, c.h]), [[2, 3, 5, 4]], "µm to mm");
  assert.equal(a.chiplets[0].temp, 25);
  assert.equal(b.chiplets[0].temp, 25, "298.15 K is 25 °C");
  assert.equal(a.chiplets[0].color, b.chiplets[0].color, "the same temperature, the same colour");
  assert.deepEqual(b.J, { value: 25, unit: "°C", declared_unit: "K" });
  assert.deepEqual([scene.footprint.extent.x0, scene.footprint.extent.x1], [2, 20], "the footprint is in mm too");
});

test("units: unsupported, missing and unknown units are refused, never placed or coloured, and listed as errors", async () => {
  const { scene } = await verifiedScene(signedRun([
    cand("lab-a", "KA", "in", [["A", 0, 0, 1, 1]]),                    // unsupported length unit
    cand("lab-b", "KB", undefined, [["A", 0, 0, 5, 5]]),               // no length unit
    cand("lab-c", "KC", "mm", [["A", 0, 0, 6, 6]]),
    cand("lab-d", "KD", "mm", [["A", 10, 0, 6, 6]]),
    cand("baseline-sa", "KS", "constructor", [["A", 0, 0, 6, 6]]),     // an object key, not a unit
    meas("MC", "°F", { A: 77 }),                                       // unsupported temperature unit
    meas("MD", undefined, { A: 25 }),                                  // no temperature unit
    meas("MS", "°C", { A: 40 }),
    support("KC", "MC"),
    support("KD", "MD"),
  ]));
  const byNode = Object.fromEntries(scene.errors.map((e) => [`${e.node}:${e.field}`, e]));
  assert.deepEqual([byNode["KA:geometry"].code, byNode["KA:geometry"].unit], ["unit_not_supported", "in"]);
  assert.equal(byNode["KB:geometry"].code, "unit_missing");
  assert.equal(byNode["KS:geometry"].code, "unit_not_supported");
  assert.deepEqual([byNode["MC:center_temps"].code, byNode["MC:center_temps"].unit], ["unit_not_supported", "°F"]);
  assert.equal(byNode["MC:J"].code, "unit_not_supported");
  assert.equal(byNode["MD:center_temps"].code, "unit_missing");
  assert.equal(byNode["MS:center_temps"], undefined, "a °C measurement is fine");
  assert.equal(scene.errors.length, 7);
  for (const lab of ["lab-a", "lab-b", "baseline-sa"]) {
    const L = track(scene, lab);
    assert.deepEqual(L.chiplets, [], `${lab}: refused geometry is never placed`);
    assert.ok(L.geometry_error);
  }
  for (const lab of ["lab-c", "lab-d"]) {
    const L = track(scene, lab);
    assert.equal(L.chiplets.length, 1, `${lab}: its geometry is fine`);
    assert.equal(L.chiplets[0].color, null, `${lab}: its temperatures are refused, so never coloured`);
    assert.ok(L.temps_error);
  }
  assert.deepEqual([scene.scale.min, scene.scale.max], [35, 45], "only the accepted measurement makes the scale");
  assert.deepEqual([scene.footprint.extent.x0, scene.footprint.extent.x1], [0, 16], "refused geometry is not in the footprint");
  assert.ok(!dataNumbers(scene).includes(77), "the refused temperature is not exported as a number");
});

test("units: refused temperatures leave chiplets placed but uncoloured, with the reason on the layout", async () => {
  const { scene } = await verifiedScene(signedRun([
    cand("lab-a", "KA", "mm", [["A", 0, 0, 6, 6], ["B", 8, 0, 6, 6]]),
    meas("MF", "°F", { A: 77, B: 80 }),
    support("KA", "MF"),
  ]));
  const a = track(scene, "lab-a");
  assert.equal(a.chiplets.length, 2, "geometry is fine, so it is placed");
  assert.ok(a.chiplets.every((c) => c.temp === null && c.color === null && c.temp_state === null), "never coloured");
  assert.deepEqual(a.temps_error, { code: "unit_not_supported", unit: "°F", detail: 'temperature unit "°F" is not one of °C, K', measurement: "MF" });
  assert.equal(a.temps_from.state, "refused");
  assert.equal(a.J, null);
  assert.equal(scene.scale, null, "nothing accepted, so no scale");
  assert.ok(!dataNumbers(scene).includes(77) && !dataNumbers(scene).includes(80), "the refused numbers are not exported");
});

test("bounds: 1e20 °C, below absolute zero, 1e308 + 1e308 mm, zero or huge sizes and wild layers are scene errors, never drawn", async () => {
  const { v, scene } = await verifiedScene(signedRun([
    cand("lab-a", "K1", "mm", [["A", 1e308, 0, 1e308, 5]]),          // the sum overflows; each part is out of range
    cand("lab-b", "K2", "mm", [["A", 0, 0, 0, 5]]),                  // zero size
    cand("lab-c", "K3", "mm", [["A", 0, 0, 1001, 5]]),               // over 1000 mm
    cand("lab-d", "K4", "mm", [["A", 0, 0, 5, 5]]),
    cand("baseline-sa", "K5", "m", [["A", 0, 0, 1.5, 0.001]]),       // 1500 mm after conversion
    meas("M1", "°C", { A: 1e20 }),
    meas("M2", "K", { A: -5 }),
    meas("M3", "°C", { A: 50 }, 50),
    support("K4", "M1"),
  ]));
  assert.equal(v.chainOk, true);
  assert.equal(v.frozen, false, "every envelope verified and projected: these are value errors, not chain errors");
  const codes = Object.fromEntries(scene.errors.map((e) => [`${e.node}:${e.field}`, e.code]));
  for (const k of ["K1:geometry", "K2:geometry", "K3:geometry", "K5:geometry", "M1:center_temps", "M1:J", "M2:center_temps", "M2:J"]) assert.equal(codes[k], "out_of_range", k);
  assert.equal(scene.errors.length, 8);
  assert.ok(everyNumberFinite(scene), "no Infinity anywhere in the scene");
  assert.deepEqual(JSON.parse(JSON.stringify(scene)), scene, "a JSON round trip changes nothing (no Infinity turned into null)");
  assert.ok(dataNumbers(scene).every((n) => Math.abs(n) <= 1e4), "no refused magnitude reaches the scene as data");
  assert.deepEqual(track(scene, "lab-d").chiplets.map((c) => c.temp), [null], "K4's 1e20 °C measurement colours nothing");
  assert.deepEqual([scene.footprint.extent.x0, scene.footprint.extent.x1], [0, 5], "only the in-range layout makes the footprint");
  assert.deepEqual([scene.scale.min, scene.scale.max], [45, 55], "only the in-range temperature makes the scale");
  assert.ok(scaleTicks(scene.scale).length <= MAX_TICKS);
  for (const [id, lo, hi] of [["layer", 17, 17], ["layer", -1, -1]]) {
    const r = readGeometry({ units: "mm", geometry: [{ id: "A", xLL: 0, yLL: 0, w: 1, h: 1, layer: lo }] });
    assert.equal(r.error.code, "out_of_range", `${id} ${lo}..${hi}`);
  }
  assert.equal(readTemps({ J: { value: 2000.5, unit: "°C" }, center_temps: { A: 2000.5 } }).error.code, "out_of_range");
  assert.equal(readTemps({ J: { value: -273.15, unit: "°C" }, center_temps: { A: -273.15 } }).error, null, "the bounds are inclusive");
  assert.deepEqual(BOUNDS.temperature_c, { min: -273.15, max: 2000 });
});

test("bounds: scaleTicks always terminates, is capped, and refuses non-finite scales (timeout guard)", async () => {
  // A worker, so a non-terminating loop fails the test instead of hanging the runner.
  const sceneUrl = pathToFileURL(join(repo, "web", "public", "sentilab", "package", "scene.mjs")).href;
  const code = `
    const { parentPort } = require("node:worker_threads");
    import(${JSON.stringify(sceneUrl)}).then(({ scaleTicks }) => {
      const cases = [[0, 1e20], [65, 100], [-275, 2000], [0, Number.MAX_VALUE], [-Number.MAX_VALUE, Number.MAX_VALUE], [1e300, 1e300 * 2], [NaN, 5], [5, Infinity], [10, 10], [10, 5]];
      parentPort.postMessage(cases.map(([min, max]) => scaleTicks({ min, max })));
    });`;
  const result = await new Promise((resolve, reject) => {
    const w = new Worker(code, { eval: true });
    const timer = setTimeout(() => { w.terminate(); reject(new Error("scaleTicks did not terminate within 2 s")); }, 2000);
    w.once("message", (m) => { clearTimeout(timer); w.terminate(); resolve(m); });
    w.once("error", (e) => { clearTimeout(timer); reject(e); });
  });
  for (const ticks of result) assert.ok(ticks.length <= MAX_TICKS, `${ticks.length} ticks`);
  assert.equal(result[0].length > 1, true, "a huge finite range still gets a few ticks");
  assert.deepEqual(result[1], [65, 70, 75, 80, 85, 90, 95, 100]);
  assert.ok(result[2].length >= 2 && result[2].length <= MAX_TICKS);
  assert.deepEqual(result[4], [], "a range that overflows has no ticks");
  assert.deepEqual(result.slice(6), [[], [], [], []], "NaN, Infinity and empty scales have no ticks");
});

test("CLI: unit-normalised export (0.01 m -> 10 mm), refused values listed not exported, --strict exits 3 on value errors", () => {
  const dir = mkdtempSync(join(tmpdir(), "sentilab-units-"));
  try {
    const good = join(dir, "good.jsonl"), bad = join(dir, "bad.jsonl"), out = join(dir, "scene.json");
    writeFileSync(good, signedRun([cand("lab-a", "KA", "m", [["A", 0.01, 0, 0.01, 0.005]]), meas("MA", "K", { A: 298.15 }), support("KA", "MA")]).map((e) => JSON.stringify(e)).join("\n") + "\n");
    writeFileSync(bad, signedRun([cand("lab-a", "KA", "mm", [["A", 1e308, 0, 1e308, 1]]), meas("MA", "°F", { A: 77 }), support("KA", "MA")]).map((e) => JSON.stringify(e)).join("\n") + "\n");
    const r = cli("export", good, "--out", out, "--pins", "test", "--strict");
    assert.equal(r.status, 0, r.stderr);
    const doc = JSON.parse(readFileSync(out, "utf8"));
    assert.deepEqual(doc.scene.tracks[1].layout.chiplets.map((c) => [c.x, c.w, c.h]), [[10, 10, 5]]);
    assert.equal(doc.scene.tracks[1].layout.chiplets[0].temp, 25);
    assert.equal(doc.value_errors, 0);
    const b = cli("build", bad, "--pins", "test", "--strict");
    assert.equal(b.status, 3, "value errors exit 3 under --strict");
    const res = JSON.parse(b.stdout);
    assert.equal(res.verification.chain_ok, true, "distinct from chain validity");
    assert.equal(res.value_errors, 3, "KA geometry, MA temperatures, MA J");
    assert.ok(everyNumberFinite(res.scene));
    assert.ok(dataNumbers(res.scene).every((n) => Math.abs(n) <= 1e4) && !dataNumbers(res.scene).includes(77), "refused numbers are never exported as data");
    assert.equal(cli("build", bad, "--pins", "test").status, 0, "without --strict, value errors still exit 0");
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

// ── The live path: source.mjs over the shared v0.6 cursor reducer (paging.mjs) and liveLabel() ─────────────────────
// Every v0.6 paging scenario is replayed through the package view's own live driver (createLive / liveRequest /
// applyPage / liveModeOf) against the reference server, with the same scripted server as the reference runner and the
// Lab view's parity test, and compared with the recorded trace poll for poll: every request (cursor, cursor_hash,
// limit; never a seq), every outcome, the paging state after each poll, K, the board label and the mode label.
const pagingTrust = vectorTrust(pagingFile.view);
const P_BASE_MS = Date.UTC(2026, 9, 31, 12, 0, 0);   // the paging runner's clock (run-paging-vectors.mjs BASE_MS)
// The vectors' rule-built chain (C16: 273 envelopes), rebuilt as run-paging-vectors.mjs builds it and checked against
// its recorded rows_sha256.
const CHAIN_ROWS = (() => {
  const spec = pagingFile.chains.c16;
  const v1Chain = viewFile.chains[0];
  const [labActor, coreActor] = [v1Chain.input.entries[0].actor, v1Chain.input.entries[1].actor];
  const at = (seconds) => new Date(P_BASE_MS + seconds * 1000).toISOString();
  const entries = Array.from({ length: spec.count }, (_, i) => {
    const seq = i + 1;
    const event = seq === 1
      ? { event_id: "c16-e001", seq, type: "node.create", actor_role: "lab", body: { id: "K16", kind: "candidate" } }
      : { event_id: `c16-e${String(seq).padStart(3, "0")}`, seq, type: "node.create", actor_role: "core", body: { id: `U${seq}`, kind: "source" } };
    return { event, ts: at(seq), actor: seq === 1 ? labActor : coreActor };
  });
  const rows = makeChain(v1Chain.input.run, entries, {}, { key_id: "core", privateKey: testKey("core").privateKey }).map((env) => enc(JSON.stringify(env)));
  assert.equal(createHash("sha256").update(refPaging.joinRows(rows)).digest("hex"), spec.rows_sha256, "C16 chain rebuilt by its rule");
  return { c16: rows };
})();
const pagingBytes = new Map();
const rowBytes = (rowId) => {
  const chainRow = /^(\w+):(\d+)$/.exec(rowId);
  if (chainRow) return CHAIN_ROWS[chainRow[1]][Number(chainRow[2]) - 1];
  if (!pagingBytes.has(rowId)) {
    const spec = pagingFile.rows[rowId];
    assert.ok(spec, `unknown row ${rowId}`);
    pagingBytes.set(rowId, spec.text !== undefined ? enc(spec.text) : spec.base64 !== undefined ? new Uint8Array(Buffer.from(spec.base64, "base64")) : new Uint8Array(spec.bytes).fill(spec.fill.charCodeAt(0)));
  }
  return pagingBytes.get(rowId);
};
// A log entry is a row id, [id, n] for n copies, or { chain, from, to } for that chain's rows seq from..to.
const expand = (list) => list.flatMap((entry) => (Array.isArray(entry) ? Array(entry[1]).fill(entry[0])
  : typeof entry === "object" ? Array.from({ length: entry.to - entry.from + 1 }, (_, i) => `${entry.chain}:${entry.from + i}`) : [entry]));
const runLengths = (ids) => {
  const out = [];
  for (const rowId of ids) {
    const last = out.at(-1);
    if (Array.isArray(last) && last[0] === rowId) last[1] += 1;
    else if (last === rowId) out[out.length - 1] = [rowId, 2];
    else out.push(rowId);
  }
  return out;
};
const rawHash = (rows) => createHash("sha256").update(Buffer.concat(rows.flatMap((row) => [Buffer.from(row), Buffer.from([0x0a])]))).digest("hex");
const LOGS = pagingFile.logs;
const FILES = {
  "c14v-tail": { rows: expand(LOGS.v1).slice(0, 5), tail: "v1-06" },
  "c14v-done": { rows: expand(LOGS.v1).slice(0, 6), tail: null },
};
const fileBytesOf = (spec) => Buffer.concat([refPaging.joinRows(spec.rows.map(rowBytes)), spec.tail ? rowBytes(spec.tail) : new Uint8Array(0)]);
function legacyRows(logName, after) {
  return expand(LOGS[logName]).filter((rowId) => {
    try { return JSON.parse(lenient(rowBytes(rowId))).event.seq > after; } catch { return false; }
  });
}
// The scripted server of run-paging-vectors.mjs (and the Lab view's parity test).
function serve(server, req) {
  if (server.network_error) return { response: null, bodyIds: [] };
  if (server.status !== undefined && server.status !== 200) {
    if (server.legacy && req.after !== undefined) {
      const ids = legacyRows(server.legacy, req.after);
      return { response: { status: 200, headers: {}, bodyBytes: refPaging.joinRows(ids.map(rowBytes)) }, bodyIds: ids };
    }
    return { response: { status: server.status, headers: {}, bodyBytes: new Uint8Array(0) }, bodyIds: [] };
  }
  if (server.file) {
    const spec = FILES[server.file];
    const response = refPaging.servePage(refPaging.logRowsFromFile(new Uint8Array(fileBytesOf(spec))), req);
    const ids = [...spec.rows, ...(spec.tail ? [spec.tail] : [])];
    return { response, bodyIds: response.status === 200 ? ids.slice(req.cursor, Number(response.headers["x-next-cursor"])) : [] };
  }
  if (server.page) {
    const before = expand(LOGS[server.page.log]);
    const rows = expand(server.page.rows);
    const next = req.cursor + rows.length;
    const headers = { "x-next-cursor": String(next), "x-has-more": "false", "x-cursor-hash": rawHash([...before, ...rows].slice(0, next).map(rowBytes)) };
    return { response: { status: 200, headers, bodyBytes: refPaging.joinRows(rows.map(rowBytes)) }, bodyIds: rows };
  }
  const ids = expand(LOGS[server.log]);
  const response = refPaging.servePage(ids.map(rowBytes), req);
  let bodyIds = response.status === 200 ? ids.slice(req.cursor, Number(response.headers["x-next-cursor"])) : [];
  for (const [name, value] of Object.entries(server.headers ?? {})) {
    if (value === null) delete response.headers[name];
    else response.headers[name] = value;
  }
  if (server.tamper) {
    const at = server.tamper.index - req.cursor;
    if (at >= 0 && at < bodyIds.length) {
      bodyIds = bodyIds.with(at, server.tamper.row);
      response.bodyBytes = refPaging.joinRows(bodyIds.map(rowBytes));
    }
  }
  if (server.strip_final_lf && response.bodyBytes.length > 0) response.bodyBytes = response.bodyBytes.subarray(0, response.bodyBytes.length - 1);
  return { response, bodyIds };
}
const summary = (st) => ({ cursor: st.cursor, rows: st.rows.length, cursor_hash: st.cursor_hash, has_more: st.has_more, last_ok_ms: st.last_ok_ms, failure: st.failure, degraded: st.degraded,
  caught_up: st.caught_up, high_k: st.high_k, last_progress_ms: st.last_progress_ms });
// The package view's live driver, one scripted poll at a time (the reference client loop: up to 16 pages a poll while
// x-has-more is true).
async function runScenarioPackage(spec) {
  const live = source.createLive(pagingFile.view.run_id, { limit: spec.limit });
  const trace = [];
  const transitions = [];
  for (const poll of spec.polls) {
    const nowMs = P_BASE_MS + poll.t_s * 1000;
    const runStatus = poll.run_status ?? "running";
    const fetches = [];
    for (let n = 0; n < 16; n += 1) {
      const req = source.liveRequest(live);
      if (req === null) break;
      const { response, bodyIds } = serve(poll.server, req);
      const before = live.paging;
      const { outcome, newRows } = await source.applyPage(live, response, nowMs, pagingTrust);
      transitions.push({ before, after: live.paging, req, outcome });
      fetches.push({ request: req, response: response && { status: response.status, headers: response.headers, body_bytes: response.bodyBytes.length, body_rows: runLengths(bodyIds) }, outcome, new_rows: newRows,
        catching_up: live.paging.catching_up, label: source.liveModeOf(live, nowMs, runStatus).label });
      if (outcome !== "ok" || !live.paging.has_more) break;
    }
    const v = live.verification;
    const row_counts = {};
    const rejected = {};
    for (const row of v?.rows ?? []) {
      row_counts[row.status] = (row_counts[row.status] ?? 0) + 1;
      if (["malformed", "oversize"].includes(row.status)) rejected[row.reasons.join("+")] = (rejected[row.reasons.join("+")] ?? 0) + 1;
    }
    trace.push({ t_s: poll.t_s, run_status: runStatus, fetches, after: summary(live.paging), K: v?.prefixEnd ?? 0, board: v?.label ?? null, label: source.liveModeOf(live, nowMs, runStatus).label, row_counts, rejected });
  }
  return { trace, transitions, live };
}

const REQUIRED_SCENARIOS = ["C1", "C2", "C11", "C12a", "C13", "C15a", "C15b", "C15c", "C16", "C17a", "C17b", "C17c"];
test("the package view replays every required paging scenario (C1, C2, C11, C12a, C13; v0.6.1 C15a-c; v0.6.2 C16, C17a-c) and the vector file has them", () => {
  const ids = pagingFile.scenarios.map((spec) => spec.name.split(" ")[0]);
  for (const id of REQUIRED_SCENARIOS) assert.ok(ids.includes(id), id);
});
for (const spec of pagingFile.scenarios) {
  const id = spec.name.split(" ")[0];
  test(`live ${id}: the package view's live path gives the reference's recorded trace, poll for poll`, async () => {
    const run = await runScenarioPackage(spec);
    assert.equal(run.trace.length, spec.trace.length);
    for (const [i, step] of run.trace.entries()) {
      assert.deepEqual(json(step), json(spec.trace[i]), `t = ${step.t_s} s`);
      assert.ok(!(step.label.startsWith("LIVE") && step.board !== null), `t = ${step.t_s} s: ${step.label} next to "${step.board}"`);
      for (const f of step.fetches) assert.ok(!(f.catching_up && f.label.startsWith("LIVE")), `t = ${step.t_s} s: LIVE during catch-up`);
    }
    for (const { before, after, req, outcome } of run.transitions) {
      assert.ok(after.cursor >= before.cursor && after.rows.length >= before.rows.length, "never resets");
      if (outcome !== "ok") assert.ok(after.rows === before.rows && after.cursor === before.cursor, "a failed poll keeps nothing");
      assert.deepEqual(Object.keys(req).sort(), before.cursor > 0 ? ["cursor", "cursor_hash", "limit"] : ["cursor", "limit"], "cursor_hash above cursor 0; never a seq parameter");
      if (before.cursor > 0) assert.equal(req.cursor_hash, rawHash(before.rows));
      if (after.degraded) assert.equal(source.liveRequest({ paging: after }), null, "terminal: no further request");
    }
  });
}

// The v0.6.2 label cases, through the package view's own liveModeOf().
for (const spec of pagingFile.label_cases) {
  test(`v0.6.2 label through the package view: ${spec.name}`, () => {
    const nowMs = P_BASE_MS + 100_000;
    const ago = (seconds) => (seconds === null ? null : nowMs - seconds * 1000);
    // A terminal failure is also the state's degraded reason, as step() sets it.
    const degraded = ["stream_replaced", "row_too_large", "paging_unsupported"].includes(spec.failure) ? spec.failure : null;
    const live = source.createLive("run-v1");
    live.paging = { ...live.paging, failure: spec.failure, degraded, caught_up: true, high_k: spec.high_k, last_ok_ms: ago(spec.ok_age_s), last_progress_ms: ago(spec.progress_age_s) };
    live.verification = { prefixEnd: spec.K, frozen: spec.frozen };
    assert.equal(source.liveModeOf(live, nowMs, spec.run_status).label, spec.expect);
    assert.equal(source.liveModeOf(live, nowMs, spec.run_status).label, refPaging.liveLabel(live.paging, nowMs, spec.K, spec.frozen, spec.run_status), "the reference agrees");
  });
}

// C11 on the bundled demo, through the same driver, ending in the package scene: K 44, then a late, validly signed seq
// 10 one second later. The label is STALE · chain broken at once and stays so; the scene follows K down to 9.
async function demoLateConflict() {
  const rows = refPaging.splitRows(demoBytes());
  const { hash, sig, ...seq10 } = JSON.parse(lenient(rows[9]));
  const late = enc(JSON.stringify(signEnvelope({ ...seq10, ts: new Date(Date.parse(seq10.ts) + 500).toISOString() }, testKey("core").privateKey, sig.key_id)));
  return { rows, late };
}
test("live C11 on the demo: a 43-row backlog is STALE, row 44 is LIVE, a late signed seq 10 one second later: STALE · chain broken at once, and the scene drops to 9", async () => {
  const { rows, late } = await demoLateConflict();
  const live = source.createLive(DEMO_RUN);
  const poll = async (log, nowMs) => {
    for (let n = 0; n < 16; n += 1) {
      const req = source.liveRequest(live);
      if (req === null) break;
      const { outcome } = await source.applyPage(live, refPaging.servePage(log, req), nowMs, testTrust);
      if (outcome !== "ok" || !live.paging.has_more) break;
    }
  };
  await poll(rows.slice(0, 43), P_BASE_MS - 1000);
  assert.equal(live.verification.prefixEnd, 43);
  assert.deepEqual(source.liveModeOf(live, P_BASE_MS - 1000), { mode: "STALE", reason: null, label: "STALE" }, "catching up is not progress");
  await poll(rows, P_BASE_MS);
  assert.equal(live.verification.prefixEnd, 44);
  assert.deepEqual(source.liveModeOf(live, P_BASE_MS), { mode: "LIVE", reason: null, label: "LIVE · progress 0 s ago" }, "the first new row is");
  await poll([...rows, late], P_BASE_MS + 1000);
  assert.equal(live.verification.prefixEnd, 9);
  assert.deepEqual(source.liveModeOf(live, P_BASE_MS + 1000), { mode: "STALE", reason: "chain broken", label: "STALE · chain broken" }, "at once, though K grew 1 s ago");
  for (let t = 2; t <= 61; t += 1) {
    await poll([...rows, late], P_BASE_MS + t * 1000);
    assert.equal(source.liveModeOf(live, P_BASE_MS + t * 1000).label, "STALE · chain broken", `t = ${t} s: never LIVE next to a frozen board`);
  }
  // The package scene adopts the drop: paused at 38, the playhead clamps to K = 9 and cand-b's acceptance is gone.
  const before = reconcile({ prefix: [], frame: null, cursor: 0, following: false }, (await source.verifyReplayFile(refPaging.joinRows(rows), { runId: DEMO_RUN, trust: testTrust })).verification);
  const r = reconcile({ prefix: before.prefix, frame: before.frame, cursor: 38, following: false }, live.verification);
  assert.equal(r.cursor, 9);
  assert.equal(r.scene.board, null);
  assert.equal(r.reset, true);
});

test("live: failed and terminal polls show liveLabel's reason; a terminal state stops requests; a file is REPLAY", async () => {
  const rows = refPaging.splitRows(demoBytes());
  const fresh = async (response, nowMs = P_BASE_MS) => {
    const live = source.createLive(DEMO_RUN);
    await source.applyPage(live, refPaging.servePage(rows.slice(0, 5), source.liveRequest(live)), nowMs, testTrust);
    const { outcome } = await source.applyPage(live, response, nowMs + 1000, testTrust);
    return { live, outcome, mode: source.liveModeOf(live, nowMs + 1000) };
  };
  const transport = await fresh(null);
  assert.equal(transport.mode.label, "STALE · transport");
  assert.notEqual(source.liveRequest(transport.live), null, "a transport failure is retried");
  for (const [status, label, outcome] of [[409, "STALE · stream replaced", "stream_replaced"], [413, "STALE · row too large", "row_too_large"], [404, "STALE · paging unsupported", "paging_unsupported"]]) {
    const r = await fresh({ status, headers: {}, bodyBytes: new Uint8Array(0) });
    assert.equal(r.outcome, outcome);
    assert.deepEqual(r.mode, { mode: "STALE", reason: label.slice("STALE · ".length), label });
    assert.equal(source.liveRequest(r.live), null, `${status}: terminal, no further request`);
    assert.equal(r.live.verification.prefixEnd, 5, `${status}: the prefix is kept`);
  }
  assert.deepEqual(source.modeNow("file", null, 0), { mode: "REPLAY", reason: null, label: "REPLAY" });
  assert.equal(source.modeNow("api", null, 0).label, "STALE", "live before any run");
  // Recovery, as liveLabel decides it: back at the high with the last growth (after catch-up) within 60 s is LIVE again.
  const live = source.createLive(DEMO_RUN);
  await source.applyPage(live, refPaging.servePage(rows.slice(0, 43), source.liveRequest(live)), P_BASE_MS, testTrust);
  assert.equal(source.liveModeOf(live, P_BASE_MS).label, "STALE", "the backlog is history, not progress");
  await source.applyPage(live, refPaging.servePage(rows, source.liveRequest(live)), P_BASE_MS + 3000, testTrust);
  const atHigh = live.verification;
  live.verification = { ...atHigh, prefixEnd: 9 };
  assert.equal(source.liveModeOf(live, P_BASE_MS + 3000).label, "STALE · chain broken");
  live.verification = atHigh;
  assert.equal(source.liveModeOf(live, P_BASE_MS + 6000).label, "LIVE · progress 3 s ago");
  assert.deepEqual(source.liveModeOf(live, P_BASE_MS + 6000, "finished"), { mode: "ENDED", reason: "run finished", label: "ENDED · run finished" });
  await source.applyPage(live, refPaging.servePage(rows, source.liveRequest(live)), P_BASE_MS + 63_001, testTrust);
  assert.equal(source.liveModeOf(live, P_BASE_MS + 63_001).label, "STALE", "no growth for over 60 s");
});

test("the source adapter uses the shared code and never pages by seq", () => {
  const text = readFileSync(join(repo, "web", "public", "sentilab", "package", "source.mjs"), "utf8");
  for (const name of ["initialState", "request as pageRequest", "step as pageStep", "verifyRows", "verifyReplayBytes", "track", "liveLabel"]) assert.ok(text.includes(name), name);
  assert.ok(text.includes('from "../paging.mjs"') && text.includes('from "../view-core.mjs"'));
  assert.ok(!/[?&]after=|after:\s|"after"/.test(text), "no after=seq paging");
  assert.ok(!/function (createProgress|recordPoll|liveMode)\b/.test(text), "no duplicate progress tracker");
});

// ── links between the views ─────────────────────────────────────────────────────────────────────────────────────────
test("view links carry the run, source, bundle, test-key request and replay playhead, and nothing else", () => {
  assert.equal(viewHref("package/", { source: "file", search: "" }), "package/");
  assert.equal(viewHref("package/", { source: "api", runId: "demo-8c-0001", search: "?src=live&pins=test&track=lab-b" }), "package/?src=live&run=demo-8c-0001&pins=test");
  assert.equal(viewHref("../", { source: "file", runId: "run-a", seq: 32, search: "?bundle=run-a&pins=test" }), "../?bundle=run-a&run=run-a&pins=test&seq=32");
  assert.equal(viewHref("../", { source: "file", runId: "demo-8c-0001", seq: 12, search: "" }), "../?seq=12", "the demo's own run id is not carried");
  assert.equal(viewHref("../", { source: "api", runId: "x\"><script>", search: "?bundle=../../etc&pins=prod" }), "../?src=live", "junk is dropped, not escaped into the URL");
  const labHtml = readFileSync(join(repo, "web", "public", "sentilab", "index.html"), "utf8");
  assert.match(labHtml, /<a href="package\/" id="packageLink"[^>]*>Package view<\/a>/);
  assert.match(labHtml, /<a href="\/">Run view<\/a>.*Package view.*Honest limits/s);
  assert.match(readFileSync(join(repo, "web", "public", "sentilab", "lab.js"), "utf8"), /\$\("packageLink"\)\.href = viewHref\("package\/"/);
  const pkgHtml = readFileSync(join(repo, "web", "public", "sentilab", "package", "index.html"), "utf8");
  assert.match(pkgHtml, /<a href="\.\.\/" id="labLink">Lab view<\/a>/);
  assert.match(readFileSync(join(repo, "web", "public", "sentilab", "package", "package.js"), "utf8"), /\$\("labLink"\)\.href = viewHref\("\.\.\/"/);
});

// ── Review of 861c611: a failed /runs refresh, and the CLI's file intake ─────────────────────────────────────────────
// 1. The package view's own poller (createLiveFeed), driven with a scripted fetch and clock. Event polls are valid
//    through t15; at t16 the /runs refresh fails: a 503, a network throw, a malformed 200 or a non-schema 200. The
//    shared failed-poll transition (runs-list.mjs refreshRuns: paging.mjs step() with no response, as for a failed
//    events page; the Lab view's path too) runs before the page is told, so the label is "STALE · transport" at once,
//    and rows, cursor and cursor hash are kept.
const RUNS_FAILURES = {
  503: { answer: () => new Response("unavailable", { status: 503 }), error: /answered 503/ },
  "network throw": { answer: () => { throw new TypeError("Failed to fetch"); }, error: /Failed to fetch/ },
  "malformed 200": { answer: () => new Response("{not json", { status: 200, headers: { "content-type": "application/json" } }), error: /aren't JSON/ },
  "non-schema 200": { answer: () => new Response(JSON.stringify({ items: [{ run_id: DEMO_RUN }] }), { status: 200, headers: { "content-type": "application/json" } }), error: /isn't a runs list/ },
};
// The log holds core.released rows (all of them unless a test grows it); /runs lists the run with core.status, or
// fails as core.runsFail says.
function scriptedCore(rows) {
  const core = { runsFail: null, calls: [], released: rows.length, status: "running" };
  core.fetch = async (url) => {
    core.calls.push(url);
    if (url.startsWith("/api/view/runs")) {
      if (core.runsFail) return RUNS_FAILURES[core.runsFail].answer();
      return new Response(JSON.stringify([{ run_id: DEMO_RUN, arm: "live", family: "fixture-8chiplet", seed: 11, last_seq: core.released, status: core.status }]), { status: 200, headers: { "content-type": "application/json" } });
    }
    const q = new URL(url, "http://x").searchParams;
    const page = refPaging.servePage(rows.slice(0, core.released), { cursor: Number(q.get("cursor")), limit: Number(q.get("limit")), ...(q.has("cursor_hash") ? { cursor_hash: q.get("cursor_hash") } : {}) });
    return new Response(Buffer.from(page.bodyBytes), { status: page.status, headers: page.headers });
  };
  return core;
}
for (const kind of Object.keys(RUNS_FAILURES)) test(`live: a /runs ${kind} mid-live gives STALE · transport at once (shared failed-poll transition), with rows, cursor and hash kept`, async () => {
  // The core appends one row a second: 29 rows at t0 (the backlog: catch-up, STALE), then 30 at t1 ... 44 at t15.
  const core = scriptedCore(refPaging.splitRows(demoBytes()));
  core.released = 29;
  let t = P_BASE_MS;
  const seen = [];
  const feed = source.createLiveFeed({ trust: testTrust, fetchImpl: core.fetch, now: () => t,
    onChange: () => seen.push({ t: (t - P_BASE_MS) / 1000, label: feed.state.live ? source.liveModeOf(feed.state.live, t).label : "STALE" }) });
  const label = () => source.liveModeOf(feed.state.live, t).label;
  await feed.pollOnce();
  assert.equal(label(), "STALE", "t0: the backlog is history, not progress");
  for (let s = 1; s <= 15; s += 1) {
    t = P_BASE_MS + s * 1000;
    core.released = 29 + s;
    await feed.pollOnce();
    assert.equal(label(), "LIVE · progress 0 s ago", `t${s}: a new row after catch-up`);
  }
  assert.equal(core.calls.filter((u) => u.startsWith("/api/view/runs")).length, 1, "/runs is refreshed only after 15 s");
  const keptHash = feed.state.live.paging.cursor_hash, keptRows = feed.state.live.paging.rows;
  core.runsFail = kind;
  t = P_BASE_MS + 16_000;
  const before = core.calls.length;
  await feed.pollOnce();
  assert.equal(core.calls.filter((u) => u.startsWith("/api/view/runs")).length, 2, `t16: the /runs refresh is due, and fails (${kind})`);
  assert.equal(core.calls.length, before + 1, "no events request after the failed refresh");
  assert.equal(feed.state.connected, false);
  assert.match(feed.state.error, RUNS_FAILURES[kind].error);
  assert.equal(feed.state.live.paging.failure, "transport", "the shared failed-poll transition ran");
  assert.equal(feed.state.live.paging.cursor_hash, keptHash, "the cursor hash is kept");
  assert.equal(feed.state.live.paging.rows, keptRows, "the rows are kept (the same list)");
  assert.equal(label(), "STALE · transport", "t16: at once, not LIVE");
  assert.deepEqual(seen.at(-1), { t: 16, label: "STALE · transport" }, "the page is told after the transition, never with LIVE");
  assert.equal(feed.state.live.paging.cursor, 44, "the cursor is kept");
  assert.equal(feed.state.live.paging.rows.length, 44, "the rows are kept");
  assert.equal(feed.state.live.verification.prefixEnd, 44, "the prefix is kept");
  for (let s = 17; s <= 20; s += 1) {
    t = P_BASE_MS + s * 1000;
    await feed.pollOnce();
    assert.equal(label(), "STALE · transport", `t${s}: still the transport reason, never a plain STALE`);
  }
  core.runsFail = null;
  t = P_BASE_MS + 21_000;
  await feed.pollOnce();
  assert.equal(feed.state.connected, true);
  assert.equal(label(), "LIVE · progress 6 s ago", "a good poll clears the failure; K last grew at t15");
  assert.equal(feed.state.live.paging.cursor, 44, "no reset: paging resumed from the kept cursor");
  assert.ok(core.calls.every((u) => !/[?&]after=/.test(u)), "never seq paging");
});
test("live: a run /api/view/runs lists as finished shows ENDED · run finished after loading, never LIVE (runStatusOf)", async () => {
  const core = scriptedCore(refPaging.splitRows(demoBytes()));
  core.status = "finished";
  let t = P_BASE_MS;
  const labels = [];
  const feed = source.createLiveFeed({ trust: testTrust, fetchImpl: core.fetch, now: () => t,
    onChange: () => labels.push(source.modeNow("api", feed.state.live, t, source.runStatusOf(feed.state)).label) });
  for (let s = 0; s <= 3; s += 1) {
    t = P_BASE_MS + s * 1000;
    await feed.pollOnce();
  }
  assert.equal(feed.state.live.verification.prefixEnd, 44);
  assert.deepEqual(labels, Array(4).fill("ENDED · run finished"));
  assert.equal(source.runStatusOf(feed.state), "finished");
  assert.equal(source.runStatusOf({ runs: [{ run_id: DEMO_RUN, status: "paused" }], runId: DEMO_RUN }), "running", "unknown status counts as running");
  assert.equal(source.runStatusOf({ runs: [{ run_id: "other", status: "finished" }], runId: DEMO_RUN }), "running", "another run's status is not this one's");
  assert.equal(source.runStatusOf(undefined), "running");
});

// 2. The CLI refuses a replay over 64 MiB before reading, splitting, decoding or parsing any of it.
const sparseFile = (path, size) => {
  const fd = openSync(path, "w");
  try { ftruncateSync(fd, size); } finally { closeSync(fd); }
};
test("CLI entrypoint: a 64 MiB + 1 file exits non-zero with zero bytes read, zero slices and zero reference work", () => {
  const dir = mkdtempSync(join(tmpdir(), "sentilab-cap-"));
  try {
    const big = join(dir, "over-cap.jsonl"), out = join(dir, "scene.json");
    sparseFile(big, cliModule.MAX_FILE_BYTES + 1);
    assert.equal(statSync(big).size, 67_108_865);
    for (const args of [["build", big, "--pins", "test"], ["export", big, "--out", out, "--pins", "test"], ["build", big, "--pins", "test", "--strict"]]) {
      const r = cli(...args);
      assert.notEqual(r.status, 0, args.join(" "));
      assert.equal(r.status, 1, "an input error");
      assert.equal(r.stdout, "", "no scene is printed");
      const err = JSON.parse(r.stderr);
      assert.deepEqual([err.error, err.reason], ["input", "file_too_large"]);
      assert.deepEqual(err.intake, { bytes_read: 0, split_calls: 0, rows_split: 0 }, "nothing read or split");
      assert.deepEqual(err.reference_counters, { parse: 0, canonical: 0, hash: 0, sign: 0, verify: 0 }, "nothing parsed, hashed or verified");
    }
    assert.throws(() => statSync(out), "export wrote nothing");
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
test("CLI intake: type and length are checked before any split; the bounded reader refuses past the cap", () => {
  const before = { ...cliModule.intake };
  const trust = cliModule.trustFor({ pins: "test" });
  assert.throws(() => cliModule.sceneFromReplay(new Uint8Array(cliModule.MAX_FILE_BYTES + 1), { trust }), (e) => e instanceof cliModule.InputError && e.reason === "file_too_large");
  assert.throws(() => cliModule.sceneFromReplay("text, not bytes", { trust }), (e) => e instanceof cliModule.InputError && e.reason === "not_bytes");
  assert.deepEqual(cliModule.intake, before, "no split for refused input");
  const dir = mkdtempSync(join(tmpdir(), "sentilab-read-"));
  try {
    const at = join(dir, "at-cap.jsonl"), over = join(dir, "over-cap.jsonl");
    writeFileSync(at, "x".repeat(32));
    writeFileSync(over, "x".repeat(33));
    const read0 = cliModule.intake.bytes_read;
    assert.equal(cliModule.readReplayCapped(at, { cap: 32 }).length, 32, "exactly at the cap is read");
    assert.equal(cliModule.intake.bytes_read - read0, 32);
    assert.throws(() => cliModule.readReplayCapped(over, { cap: 32 }), (e) => e instanceof cliModule.InputError && e.reason === "file_too_large");
    assert.equal(cliModule.intake.bytes_read - read0, 32, "the over-cap file is refused at the stat, unread");
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
