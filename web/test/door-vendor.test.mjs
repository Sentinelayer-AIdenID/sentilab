// node --test web/test/door-vendor.test.mjs
// Where the agent door's fixed values come from, checked against their sources in this tree:
//   - the vendored AIdenID intent gate (src/vendor/aidenid-intent-gate) is byte-identical to AIdenID 09b2ff46 and its
//     generated runtime regenerates exactly (web/scripts/build-intent-gate.mjs);
//   - the classes and operators an arrival may carry are exactly the vendored classifier's enums;
//   - the CPU-DRAM case and its rules are the fixture's (sundai_tap/configs/sys_micro150_45mm.cfg, tap_oracle.py's
//     margin) and the snapped reference is the published reference copy's;
//   - root's gate-zero record (web/public/agents/evidence.json) still holds the fields the ENGRAM view reads.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readdirSync, readFileSync } from "node:fs";

import { runtimeOf } from "../scripts/build-intent-gate.mjs";
import { AGENT_RESPONSE_CACHE } from "../src/generated/aidenid-intent-gate/agent-resources.js";
import { GATE_QUESTION } from "../src/generated/aidenid-intent-gate/intent-gate.js";
import { BODY_GAP_UM, CONNECTIONS, DIES, EDGE_CLEARANCE_UM, FRAME_UM, LATTICE_UM, PURPOSE_IDS, SNAPPED_REFERENCE } from "../src/door/case.js";
import { CLASSES, OPERATORS } from "../src/door/door.js";
import { gateZeroFrom } from "../src/door/engram.js";
import { parseCompact } from "../src/door/layout.js";

const read = (rel) => readFileSync(new URL(rel, import.meta.url));
const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");
const blob = (bytes) => createHash("sha1").update(Buffer.concat([Buffer.from(`blob ${bytes.length}\0`), bytes])).digest("hex");

test("the intent gate is vendored byte for byte from AIdenID 09b2ff46, and its runtime regenerates exactly", () => {
  const vendor = new URL("../src/vendor/aidenid-intent-gate/", import.meta.url);
  const manifest = JSON.parse(readFileSync(new URL("VENDORED.json", vendor)));
  assert.equal(manifest.commit, "09b2ff466d0fadcb83b09b0f6f213d13f430c9e1");
  assert.equal(manifest.source, "workers/aquarium-edge/src");
  assert.deepEqual(Object.keys(manifest.files).sort(), readdirSync(new URL("src/", vendor)).map((name) => `src/${name}`).sort());
  for (const [path, hash] of Object.entries(manifest.files)) {
    const bytes = readFileSync(new URL(path, vendor));
    assert.equal(sha256(bytes), hash, path);
    assert.equal(blob(bytes), manifest.git_blobs[path], `${path}: the upstream git blob`);
    assert.ok(!bytes.includes(13), `${path}: LF only`);
    const generated = readFileSync(new URL(`../src/generated/aidenid-intent-gate/${path.slice(4).replace(/\.ts$/, ".js")}`, import.meta.url), "utf8");
    assert.equal(generated, runtimeOf(bytes.toString("utf8")), `generated ${path}`);
  }
  // The upstream source note stays at the head of the gate.
  assert.match(readFileSync(new URL("src/intent-gate.ts", vendor), "utf8"), /^\/\*\*\n \* The intent gate \(Carter, reply under #54348\)/);
  assert.equal(GATE_QUESTION, "What are you here to do?");
  assert.equal(AGENT_RESPONSE_CACHE, "private, no-store, no-transform");
  assert.deepEqual(PURPOSE_IDS, ["place-chiplets", "review", "read"]);
});

test("arrivals carry only the vendored classifier's classes and operators", () => {
  const types = read("../src/vendor/aidenid-classifier/src/types.ts").toString("utf8");
  const union = (name) => [...new RegExp(`export type ${name} = ([^;]+);`).exec(types)[1].matchAll(/"([a-z_]+)"/g)].map((m) => m[1]);
  assert.deepEqual([...CLASSES], union("TriageClass"));
  assert.deepEqual([...OPERATORS], union("Operator"));
});

test("the CPU-DRAM case and its rules are the fixture's own", () => {
  const cfg = read("../../sundai_tap/configs/sys_micro150_45mm.cfg").toString("utf8");
  assert.equal(sha256(read("../../sundai_tap/configs/sys_micro150_45mm.cfg")), "de6e3edbed848f1bd81758a92f72a1f0b6aa5ffa60aca3153a324cf7a78d9ffd");
  const list = (key) => /^\s*([^=]+?)\s*=\s*(.*)$/m.exec(cfg.split("\n").find((line) => line.startsWith(key)))[2].split(",").map((v) => Number(v.trim()));
  assert.deepEqual(list("widths").map((mm) => mm * 1000), DIES.map((d) => d.w));
  assert.deepEqual(list("heights").map((mm) => mm * 1000), DIES.map((d) => d.h));
  assert.deepEqual(list("powers"), DIES.map((d) => d.power_w));
  const matrix = /connections = ([\s\S]*?)\n\n/.exec(cfg)[1].split(";").map((row) => row.trim().split(",").map((v) => Number(v.trim())));
  assert.deepEqual(matrix, CONNECTIONS.map((row) => [...row]));
  assert.match(cfg, /^intp_size = 45$/m);
  assert.equal(FRAME_UM, 45000);
  assert.match(cfg, /^center_lattice_mm = 0\.5$/m);
  assert.equal(LATTICE_UM, 500);
  assert.match(cfg, /^min_die_gap_mm = 0\.1$/m);
  assert.equal(BODY_GAP_UM, 100);
  assert.match(cfg, /^rotation = per_die_90$/m);
  // A square die has one footprint, so only the CPUs turn (tap_oracle.py _load_legality).
  assert.deepEqual(DIES.map((d) => (d.w === d.h ? [0] : [0, 90])), DIES.map((d) => [...d.rot_deg]));
  assert.match(read("../../sundai_hotspot/tap_oracle.py").toString("utf8"), /^TAP_MARGIN_MM = 0\.5$/m);
  assert.equal(EDGE_CLEARANCE_UM, 500);
  // The published reference copy: halos, footprints and the snapped layout.
  const ref = JSON.parse(read("../public/agents/references/micro150-tap25d-fig5a-snap0p5.json"));
  assert.deepEqual(ref.dies.map((d) => Math.round(d.halo_mm * 1000)), DIES.map((d) => d.halo));
  assert.deepEqual(ref.footprints_mm.map(([w, h]) => [w * 1000, h * 1000]), DIES.map((d) => [d.w, d.h]));
  assert.deepEqual(parseCompact(SNAPPED_REFERENCE).dies.map((d) => [d.x_um / 1000, d.y_um / 1000]), ref.centers_mm);
  assert.equal(ref.wire_proxy_mm, 9.5);
  assert.deepEqual(ref.rotated, [false, false, false, false, false, false, false, false]);
});

test("root's gate-zero record still holds what the ENGRAM view reads from it", () => {
  const evidence = JSON.parse(read("../public/agents/evidence.json"));
  const gate = gateZeroFrom(evidence);
  assert.deepEqual(gate, { status: evidence.gate_zero.status, native: 115.93, centreMean: 115.935, active: 119.07, precisionK: 0.01 });
  assert.equal(gateZeroFrom({}), null);
  assert.equal(gateZeroFrom({ gate_zero: { status: "x", results: [{ problem: "ascend910", layout: "ascend910-tap25d-fig6a/raw" }] } }), null);
});
