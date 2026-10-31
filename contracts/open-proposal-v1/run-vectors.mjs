// Runs vectors-canonical.json against canonical.mjs (test T1: Python and Node agree). Exit 0 only if every vector
// passes. No dependencies.
//   node run-vectors.mjs
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as c from "./canonical.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const load = (name) => JSON.parse(readFileSync(join(here, name), "utf8"));
const vectors = load("vectors-canonical.json");
const manifests = load("golden/manifests.json").manifests;
const objects = vectors.objects;
const utf8 = (text) => new TextEncoder().encode(text);
const sha256 = async (text) => c.sha256Hex(utf8(text));
const bytes = (b64) => new Uint8Array(Buffer.from(b64, "base64"));

let passed = 0;
let failed = 0;
function expect(name, actual, wanted) {
  const same = c.canonical(actual) === c.canonical(wanted);
  if (same) passed += 1; else { failed += 1; console.log(`FAIL ${name}: expected ${c.canonical(wanted)}, got ${c.canonical(actual)}`); }
}
function refuses(name, fn) {
  try { fn(); failed += 1; console.log(`FAIL ${name}: accepted`); } catch { passed += 1; }
}

for (const v of vectors.canonical) {
  expect(`canonical: ${v.name}`, c.canonical(v.value), v.canonical);
  expect(`canonical sha256: ${v.name}`, await sha256(c.canonical(v.value)), v.sha256);
}
const surrogate = String.fromCharCode(0xd800);
refuses("NaN is refused", () => c.canonical(Number.NaN));
refuses("Infinity is refused", () => c.canonical(Number.POSITIVE_INFINITY));
refuses("a lone surrogate value is refused", () => c.canonical({ s: `a${surrogate}` }));
refuses("a lone surrogate key is refused", () => c.canonical({ [surrogate]: 1 }));
refuses("undefined is refused", () => c.canonical([undefined]));

for (const v of vectors.manifest_id) expect(`manifest_id ${v.manifest}`, await c.manifestId(manifests[v.manifest]), v.manifest_id);
for (const v of vectors.geometry) {
  const [item, manifest] = [objects[v.object], manifests[v.manifest]];
  expect(`geometry preimage: ${v.object}`, c.geometryObject(item, manifest), v.preimage);
  expect(`geometry canonical: ${v.object}`, c.canonical(c.geometryObject(item, manifest)), v.canonical);
  expect(`geometry_sha256: ${v.object}`, await c.geometrySha256(item, manifest), v.geometry_sha256);
}
for (const v of vectors.content) {
  expect(`canonical object: ${v.object}`, c.canonical(objects[v.object]), v.canonical);
  expect(`content_sha256: ${v.object}`, await c.contentSha256(objects[v.object]), v.content_sha256);
  expect(`logical key: ${v.object}`, c.logicalKey(objects[v.object]), v.logical_key);
}
for (const v of vectors.body_sha256) expect("body_sha256", await c.bodySha256(bytes(v.note_b64)), v.body_sha256);
for (const v of vectors.source_ref) expect(`source_ref ${v.action_id}`, await c.sourceRef(v.action_id), v.source_ref);
const kChallenge = c.fromHex(await sha256(vectors.test_phrases.k_challenge));
for (const v of vectors.participant_ref) {
  expect(`participant_ref ${v.account_id}`, await c.participantRef(kChallenge, v.account_id), v.participant_ref);
}
for (const v of vectors.actor_slot) expect(`actor slot ${v.actor_kind}`, c.actorSlot(v.actor_kind, v.actor_id), v.actor_slot);
refuses("an actor slot that mixes kinds", () => c.actorSlot("human", "example-agent"));
refuses("an agent slot without its agent", () => c.actorSlot("agent", null));
for (const v of vectors.transport_key) {
  const item = objects[v.object];
  const fields = { room: v.room, account: v.account, actor_slot: c.actorSlot(v.actor_kind, v.actor_id),
    manifest_id: item.manifest_id, logical_key: c.logicalKey(item), content_sha256: await c.contentSha256(item) };
  expect(`transport-key preimage: ${v.object} ${v.actor_kind} ${v.room}`, c.transportKeyObject(fields), v.preimage);
  const key = await c.transportKeyFor(item, { room: v.room, account: v.account, actorKind: v.actor_kind, actorId: v.actor_id });
  expect(`transport key: ${v.object} ${v.actor_kind} ${v.room}`, key, v.transport);
  expect("a transport key is 52 characters", key.length, 52);
}
for (const v of vectors.run_id) expect(`run_id ${v.run_id}`, c.runId(v.manifest_id, v.proposal_sha256), v.run_id);
for (const v of vectors.sealed_header) expect(`sealed header ${v.key_version}`, c.sealedHeader(v.manifest_id, v.key_version), v.line);
refuses("a key version is a positive integer", () => c.sealedHeader("f".repeat(64), 0));
for (const v of vectors.sealed_notes) {
  const parsed = c.parseSealedNote(v.note);
  expect(`sealed note ${v.id}: manifest`, parsed.manifestId, v.manifest_id);
  expect(`sealed note ${v.id}: key version`, parsed.keyVersion, v.key_version);
  expect(`sealed note ${v.id}: age file`, await c.sha256Hex(parsed.ageFile), v.age_file_sha256);
}
for (const v of vectors.sealed_note_refusals) {
  refuses(`sealed note refused: ${v.name}`, () => c.parseSealedNote(Buffer.from(v.note_b64, "base64").toString("latin1")));
}
for (const v of vectors.armour_refusals) refuses(`armour refused: ${v.name}`, () => c.dearmor(Buffer.from(v.armour_b64, "base64").toString("latin1")));
for (const v of vectors.r_key) expect(`r key ${v.r}`, c.rKey(v.r), v.key);
for (const r of vectors.r_key_refused) refuses(`r key refused ${r}`, () => c.rKey(r));
for (const v of vectors.conductor_geometry) {
  expect(`conductor geometry ${v.object}`, c.conductorGeometry(objects[v.object], manifests[v.manifest]), v.values);
}

console.log(`${passed} vectors passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
