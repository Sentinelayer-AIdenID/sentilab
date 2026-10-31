// Runs both vector files against the reference code. Exit 0 only if everything passes.
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { project } from "./evidence-projection.mjs";
import { canonical, check, checkRaw } from "./resultcheck.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const load = (name) => JSON.parse(readFileSync(join(here, name), "utf8"));
let failures = 0;
const fail = (name, message) => { failures += 1; console.log(`FAIL ${name}: ${message}`); };

function subset(actual, expected, path = "") {
  if (expected === null || typeof expected !== "object") {
    if (typeof expected === "number" && typeof actual === "number") return Math.abs(actual - expected) <= 1e-6 ? [] : [`${path}: expected ${expected}, got ${actual}`];
    return actual === expected ? [] : [`${path}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`];
  }
  if (Array.isArray(expected)) {
    return canonical(actual) === canonical(expected) ? [] : [`${path}: expected ${canonical(expected)}, got ${canonical(actual)}`];
  }
  if (actual === null || typeof actual !== "object") return [`${path}: expected an object, got ${JSON.stringify(actual)}`];
  if (Object.keys(expected).length === 0 && Object.keys(actual).length > 0) return [`${path}: expected empty, got ${canonical(actual)}`];
  return Object.keys(expected).flatMap((key) => subset(actual[key], expected[key], `${path}.${key}`));
}

// seq defaults to the event's position, but an explicit seq in a vector is kept.
const withIds = (events) => events.map((event, index) => ({ event_id: `e${index}`, seq: index + 1, ...event }));

const evidence = load("vectors-evidence.json").vectors;
for (const vector of evidence) {
  const events = withIds(vector.events);
  const errors = [];
  try {
    const result = project(events);
    for (const [id, expected] of Object.entries(vector.expect.nodes ?? {})) errors.push(...subset(result.nodes[id], expected, `nodes.${id}`));
    errors.push(...subset(result.rejected, vector.expect.rejected ?? [], "rejected"));
    for (const id of vector.expect.absent_nodes ?? []) if (result.nodes[id]) errors.push(`${id} should not exist`);
    if (canonical(project(events)) !== canonical(result)) errors.push("replay gave a different projection");
    if (canonical(project([...events].reverse())) !== canonical(result)) errors.push("delivery order changed the projection");
  } catch (error) {
    errors.push(`threw ${error.name}: ${error.message}`);
  }
  if (errors.length) fail(`evidence "${vector.name}"`, errors.join("; "));
}

const VERSION = "resultcheck.request.v2";
function rawFor(vector) {
  if (vector.raw !== undefined) return vector.raw;
  const spec = vector.raw_generate;
  if (spec.kind === "deep") return "[".repeat(spec.depth) + "]".repeat(spec.depth);
  if (spec.kind === "multibyte_notes") {
    return JSON.stringify({ schema_version: VERSION, request_id: "x", metric: { name: "t", unit: "ms", direction: "lower_is_better" }, pairs: [], notes: "é".repeat(spec.chars) });
  }
  throw new Error(`unknown raw_generate ${spec.kind}`);
}
function requestFor(vector) {
  const request = { schema_version: VERSION, request_id: "vector", ...vector.request };
  if (vector.generate_pairs) {
    const { wins, losses } = vector.generate_pairs;
    request.pairs = [
      ...Array.from({ length: wins }, (_, i) => ({ id: `w${i}`, baseline: 2, candidate: 1 })),
      ...Array.from({ length: losses }, (_, i) => ({ id: `l${i}`, baseline: 1, candidate: 2 })),
    ];
  }
  return request;
}

const resultcheck = load("vectors-resultcheck.json").vectors;
for (const vector of resultcheck) {
  const errors = [];
  try {
    const isRaw = vector.raw !== undefined || vector.raw_generate !== undefined;
    const run = isRaw ? () => checkRaw(rawFor(vector)) : () => check(requestFor(vector));
    const receipt = run();
    errors.push(...subset(receipt, vector.expect, "receipt"));
    const text = JSON.stringify(receipt);
    for (const banned of vector.receipt_must_not_contain ?? []) if (text.includes(banned)) errors.push(`receipt contains "${banned}"`);
    if (JSON.stringify(run()) !== text) errors.push("receipt is not byte-identical on a second run");
  } catch (error) {
    errors.push(`threw ${error.name}: ${error.message}`);
  }
  if (errors.length) fail(`resultcheck "${vector.name}"`, errors.join("; "));
}

// Checks that don't fit the vector format.
const base = { schema_version: VERSION, request_id: "n", metric: { name: "t", unit: "ms", direction: "lower_is_better" }, pairs: [{ id: "a", baseline: 5, candidate: 4 }, { id: "b", baseline: 5, candidate: 3 }] };
const extras = [
  ["notes change the request hash", check(base).request_hash !== check({ ...base, notes: "x" }).request_hash],
  ["notes don't change the statistics", canonical(check(base).statistics) === canonical(check({ ...base, notes: "x" }).statistics)],
  ["key order doesn't change the hash", check({ pairs: base.pairs, metric: base.metric, request_id: "n", schema_version: VERSION }).request_hash === check(base).request_hash],
  ["raw and parsed input give the same receipt", JSON.stringify(checkRaw(JSON.stringify(base))) === JSON.stringify(check(base))],
  ["the old schema version is rejected", check({ ...base, schema_version: "resultcheck.request.v1" }).status === "rejected"],
];
for (const [name, ok] of extras) if (!ok) fail(`extra "${name}"`, "failed");

// A long chain of diamonds must not take exponential time.
const diamondEvents = [{ event_id: "root", seq: 1, type: "node.create", body: { id: "n0", kind: "source" } }];
let seq = 2;
for (let i = 1; i <= 200; i += 1) {
  for (const id of [`a${i}`, `b${i}`, `n${i}`]) diamondEvents.push({ event_id: `c-${id}`, seq: seq++, type: "node.create", body: { id, kind: "claim" } });
  diamondEvents.push({ event_id: `s-a${i}`, seq: seq++, type: "support.add", body: { node: `a${i}`, set_id: "s", members: [`n${i - 1}`] } });
  diamondEvents.push({ event_id: `s-b${i}`, seq: seq++, type: "support.add", body: { node: `b${i}`, set_id: "s", members: [`n${i - 1}`] } });
  diamondEvents.push({ event_id: `s-n${i}`, seq: seq++, type: "support.add", body: { node: `n${i}`, set_id: "s", members: [`a${i}`, `b${i}`] } });
}
const started = Date.now();
const diamondResult = project(diamondEvents);
if (diamondResult.nodes.n200.validity !== "valid") fail("diamond chain", `expected valid, got ${diamondResult.nodes.n200.validity}`);
const staleResult = project([...diamondEvents, { event_id: "w", seq, type: "withdraw", body: { node: "n0", reason: "drill" } }]);
if (staleResult.nodes.n200.validity !== "stale" || canonical(staleResult.nodes.n200.stale_because) !== canonical(["n0"])) fail("diamond chain", `expected stale because n0, got ${canonical(staleResult.nodes.n200)}`);
if (Date.now() - started > 20000) fail("diamond chain", "took over 20 seconds");

const sha = (name) => createHash("sha256").update(readFileSync(join(here, name))).digest("hex");
const total = evidence.length + resultcheck.length + extras.length + 1;
console.log(failures === 0 ? `PASS: ${evidence.length} evidence vectors, ${resultcheck.length} ResultCheck vectors, ${extras.length + 1} other checks (${total} total)` : `${failures} of ${total} FAILED`);
for (const name of ["CONTRACTS.md", "vectors-evidence.json", "vectors-resultcheck.json", "evidence-projection.mjs", "resultcheck.mjs", "run-vectors.mjs"]) console.log(`${sha(name)}  ${name}`);
process.exit(failures === 0 ? 0 : 1);
