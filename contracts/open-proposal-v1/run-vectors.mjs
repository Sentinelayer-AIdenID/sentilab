// Runs vectors-canonical.json against canonical.mjs. Exit 0 only if every vector passes. No dependencies.
//   node run-vectors.mjs
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as c from "./canonical.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const load = (name) => JSON.parse(readFileSync(join(here, name), "utf8"));
const vectors = load("vectors-canonical.json");
const manifests = load("golden/manifests.json").manifests;
const sha256 = async (text) => c.sha256Hex(new TextEncoder().encode(text));
const bytes = (b64) => new Uint8Array(Buffer.from(b64, "base64"));
const phrase = async (text) => c.fromHex(await sha256(text));

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
  const manifest = manifests[v.manifest];
  expect(`geometry object: ${v.name}`, c.geometryObject(v.proposal, manifest), v.object);
  expect(`geometry canonical: ${v.name}`, c.canonical(c.geometryObject(v.proposal, manifest)), v.canonical);
  expect(`geometry_sha256: ${v.name}`, await c.geometrySha256(v.proposal, manifest), v.geometry_sha256);
}
for (const v of vectors.proposal) {
  expect(`proposal canonical: ${v.name}`, c.canonical(v.proposal), v.canonical);
  expect(`proposal_sha256: ${v.name}`, await c.proposalSha256(v.proposal), v.proposal_sha256);
}
for (const v of vectors.body_sha256) expect("body_sha256", await c.bodySha256(bytes(v.note_b64)), v.body_sha256);
for (const v of vectors.source_ref) expect(`source_ref ${v.action_id}`, await c.sourceRef(v.action_id), v.source_ref);
const pseudonymKey = await phrase(vectors.test_phrases.pseudonym_key);
for (const v of vectors.participant_ref) {
  expect(`participant_ref ${v.challenge}`, await c.participantRef(pseudonymKey, v.challenge, v.account_id), v.participant_ref);
}
for (const v of vectors.transport_id) {
  const { transport_id: wanted, ...input } = v;
  const actual = await c.transportId(input);
  expect(`transport_id ${input.actor_kind} ${input.room}`, actual, wanted);
  expect("transport_id fits every transport's Idempotency-Key", actual.length <= c.TRANSPORT_MAX_LENGTH, true);
}
for (const v of vectors.run_id) expect(`run_id ${v.participant_ref.slice(0, 8)}`, c.runId(v.manifest_id, v.participant_ref), v.run_id);
const clientSecret = await phrase(vectors.test_phrases.client_secret);
for (const v of vectors.salt) expect("salt", await c.deriveSalt(clientSecret, v.manifest_id, v.proposal_key), v.salt);
for (const v of vectors.capability) {
  expect(`capability epoch ${v.epoch}`, await c.capability(v.salt, v.manifest_id, v.proposal_sha256, v.epoch), v.capability);
  expect("capability_sha256", await c.capabilitySha256(v.capability), v.capability_sha256);
}
for (const v of vectors.ciphertext_ref) expect("ciphertext_ref", await c.ciphertextRef(bytes(v.age_file_b64)), v.ciphertext_ref);
for (const v of vectors.conductor_geometry) {
  expect(`conductor geometry ${v.manifest}`, c.conductorGeometry(v.proposal, manifests[v.manifest]), v.values);
}
refuses("an actor slot that mixes kinds", () => c.actorSlot("human", "example-agent"));
expect("no age ciphertext is claimed", vectors.age.vectors, []);

console.log(`${passed} vectors passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
