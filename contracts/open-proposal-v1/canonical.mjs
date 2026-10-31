// Open-proposal contract v1: canonical JSON (RFC 8785 JCS) and every hash and key the contract binds (DESIGN rev 3
// sections 3.4, 3.7, 3.9, 5.2, 7.4), for JavaScript clients, adapters and pages. Isomorphic: Node 20+ and browsers,
// through Web Crypto; no imports. The Python reference is open_proposals/contract/canonical.py, over
// sentilab_core/envelope.py's canonical(). Both run vectors-canonical.json.
//
// Canonical JSON: object keys sorted by UTF-16 code units (JavaScript's default string order), numbers and strings as
// JSON.stringify writes them (ECMAScript shortest round trip; only quote, backslash and control characters escaped),
// no whitespace, then UTF-8. A nonfinite number or a lone surrogate is refused, never written as null or escaped.

const SOURCE_PREFIX = "sentilab-open-source/1:";
export const TRANSPORT_PREFIX = "so1-";
export const TRANSPORT_HEX_CHARS = 48;
export const SEALED_SCHEMA = "sentilab-open-sealed/1";
const PUBLISH_KEY_PREFIX = "publish:";

function hasLoneSurrogate(text) {
  for (let i = 0; i < text.length; i += 1) {
    const unit = text.charCodeAt(i);
    if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = text.charCodeAt(i + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) return true;
      i += 1;
    } else if (unit >= 0xdc00 && unit <= 0xdfff) {
      return true;
    }
  }
  return false;
}

function text(value) {
  if (hasLoneSurrogate(value)) throw new Error("lone surrogate");
  return JSON.stringify(value);
}

export function canonical(value) {
  if (value === null) return "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new Error("nonfinite JSON number");
    return JSON.stringify(value);
  }
  if (typeof value === "string") return text(value);
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${text(key)}:${canonical(value[key])}`).join(",")}}`;
  }
  throw new Error("unsupported JSON value");
}

const utf8 = (value) => new TextEncoder().encode(value);
const hex = (buffer) => Array.from(new Uint8Array(buffer), (byte) => byte.toString(16).padStart(2, "0")).join("");

export function fromHex(value) {
  if (!/^(?:[0-9a-f]{2})*$/.test(value)) throw new Error("not lowercase hex");
  return Uint8Array.from(value.match(/../g) ?? [], (pair) => parseInt(pair, 16));
}

export async function sha256Hex(bytes) {
  return hex(await globalThis.crypto.subtle.digest("SHA-256", bytes));
}

export async function hmacSha256Hex(key, bytes) {
  const imported = await globalThis.crypto.subtle.importKey("raw", key, { name: "HMAC", hash: "SHA-256" }, false,
    ["sign"]);
  return hex(await globalThis.crypto.subtle.sign("HMAC", imported, bytes));
}

export const digest = (value) => sha256Hex(utf8(canonical(value)));

// The geometry_sha256 preimage (section 5.2): problem and fixture hash from the manifest; no actor, time, key, salt,
// terms or client.
export function geometryObject(item, manifest) {
  return {
    schema: "sentilab-open-geometry/1", problem: manifest.problem, fixture_config_sha256: manifest.fixture.config_sha256,
    units: item.units, anchor: item.anchor,
    dies: item.dies.map((die) => ({ die: die.die, x_um: die.x_um, y_um: die.y_um, rot_deg: die.rot_deg })),
  };
}

export const geometrySha256 = (item, manifest) => digest(geometryObject(item, manifest));
// proposal_sha256, request_sha256, the team hash and the publish hash: sha256(JCS(object)). For a sealed object it is
// the canonical salted plaintext's hash, so re-sealing the same plaintext retries identically.
export const contentSha256 = (item) => digest(item);
export const proposalSha256 = contentSha256;
export const requestSha256 = contentSha256;
export const manifestId = (manifest) => digest(manifest);
export const bodySha256 = (noteBytes) => sha256Hex(noteBytes);
export const sourceRef = (actionId) => sha256Hex(utf8(SOURCE_PREFIX + actionId));

// Server side: the public pseudonym HMAC-SHA256(k_challenge, account_id) (section 3.9). Clients never hold the key.
export function participantRef(kChallenge, accountId) {
  if (kChallenge.length < 32) throw new Error("k_challenge is at least 32 bytes");
  return hmacSha256Hex(kChallenge, utf8(accountId));
}

export function actorSlot(actorKind, actorId) {
  if (actorKind === "human" && actorId === null) return "human";
  if (actorKind === "agent" && typeof actorId === "string" && actorId) return `agent:${actorId}`;
  throw new Error("actor kind and actor id disagree");
}

export function logicalKey(item) {
  switch (item.schema) {
    case "sentilab-open-proposal/1": return item.proposal_key;
    case "sentilab-open-check-request/1": return item.request_key;
    case "sentilab-open-team/1": return "team";
    case "sentilab-open-publish/1": return PUBLISH_KEY_PREFIX + item.proposal_sha256;
    default: throw new Error("not a contract object");
  }
}

export function transportKeyObject({ room, account, actor_slot, manifest_id, logical_key, content_sha256 }) {
  return { schema: "sentilab-open-transport-key/1", room, account, actor_slot, manifest_id, logical_key,
    content_sha256 };
}

// Send it as Senti's idempotencyKey (section 3.4): "so1-" + hex(sha256(JCS(preimage)))[0:48], 52 characters.
export async function transportKey(fields) {
  return TRANSPORT_PREFIX + (await digest(transportKeyObject(fields))).slice(0, TRANSPORT_HEX_CHARS);
}

export async function transportKeyFor(item, { room, account, actorKind, actorId }) {
  return transportKey({ room, account, actor_slot: actorSlot(actorKind, actorId), manifest_id: item.manifest_id,
    logical_key: logicalKey(item), content_sha256: await contentSha256(item) });
}

const HEX64 = /^[0-9a-f]{64}$/;

// The run id's preimage: the full manifest identity, the server-derived participant reference and the full proposal
// identity, domain-separated; each exactly 64 lower-case hex characters.
export function runIdObject(manifestId_, participantRef_, proposalSha256_) {
  for (const value of [manifestId_, participantRef_, proposalSha256_]) {
    if (typeof value !== "string" || !HEX64.test(value)) throw new Error("a run id binds three full sha256 hex digests");
  }
  return { schema: "sentilab-open-run/1", manifest_id: manifestId_, participant_ref: participantRef_,
    proposal_sha256: proposalSha256_ };
}

// One signed run per account and proposal: open-<manifest_id 8 hex>-<32 hex of sha256(JCS(preimage))>.
export async function runId(manifestId_, participantRef_, proposalSha256_) {
  const preimage = runIdObject(manifestId_, participantRef_, proposalSha256_);
  return `open-${manifestId_.slice(0, 8)}-${(await digest(preimage)).slice(0, 32)}`;
}

// A sealed note's first line (section 3.7); the ASCII-armoured age file follows on the next line.
export function sealedHeader(manifestId_, keyVersion) {
  if (!Number.isSafeInteger(keyVersion) || keyVersion < 1) throw new Error("the key version is a positive integer");
  return `${SEALED_SCHEMA} ${manifestId_} ${keyVersion}`;
}

const ARMOR_BEGIN = "-----BEGIN AGE ENCRYPTED FILE-----";
const ARMOR_END = "-----END AGE ENCRYPTED FILE-----";
const LF = String.fromCharCode(10);
const SEALED_LINE = new RegExp(`^sentilab-open-sealed[/]1 ([0-9a-f]{64}) ([1-9][0-9]{0,5})${LF}`);

function ascii(text) {
  for (let i = 0; i < text.length; i += 1) if (text.charCodeAt(i) > 127) throw new Error("not ASCII");
  return text;
}

// The ASCII armour of an age file: the BEGIN line, padded standard base64 in 64-column lines, the END line, each
// ending in LF.
export function armor(bytes) {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  const encoded = btoa(binary);
  const lines = [];
  for (let start = 0; start < encoded.length; start += 64) lines.push(encoded.slice(start, start + 64));
  return [ARMOR_BEGIN, ...lines, ARMOR_END].join(LF) + LF;
}

// The age file inside a strict armour: exactly armor()'s output, the final LF optional. Anything else throws.
export function dearmor(text) {
  const lines = ascii(text).split(LF);
  if (lines[lines.length - 1] === "") lines.pop();
  if (lines.length < 3 || lines[0] !== ARMOR_BEGIN || lines[lines.length - 1] !== ARMOR_END) {
    throw new Error("armour: a missing or altered BEGIN or END line, or no body");
  }
  const body = lines.slice(1, -1).join("");
  if (body.length % 4 !== 0 || !/^[A-Za-z0-9+/]*={0,2}$/.test(body)) throw new Error("armour: not padded base64");
  const bytes = Uint8Array.from(atob(body), (char) => char.charCodeAt(0));
  if (bytes.length === 0 || armor(bytes) !== lines.join(LF) + LF) throw new Error("armour: not canonical");
  return bytes;
}

// A sealed note (section 3.7): its first line and the age file in its armour. Opening it needs the intake's key.
export function parseSealedNote(note) {
  ascii(note);
  if (note.length > 8192) throw new Error("sealed note: over 8,192 bytes");
  const match = SEALED_LINE.exec(note);
  if (!match) throw new Error("sealed note: the first line is not 'sentilab-open-sealed/1 <manifest_id> <key_version>'");
  return { manifestId: match[1], keyVersion: Number(match[2]), ageFile: dearmor(note.slice(match[0].length)) };
}

// A q_r key: "0", or r with exactly two decimals. r must have at most two decimals.
export function rKey(r) {
  if (!Number.isFinite(r) || r < 0 || Math.round(r * 100) / 100 !== r) throw new Error("r has at most two decimals");
  return r === 0 ? "0" : r.toFixed(2);
}

// values for a receipt, as the conductor writes them: one exact integer ratio per coordinate, rounded once.
export function conductorGeometry(item, manifest) {
  const geometry = item.dies.map((die) => {
    const spec = manifest.dies[die.die];
    const [w, h] = die.rot_deg === 90 ? [spec.h_um, spec.w_um] : [spec.w_um, spec.h_um];
    return { id: `tap-chiplet-${die.die}`, xLL: (2 * die.x_um - w) / 2000, yLL: (2 * die.y_um - h) / 2000,
      w: w / 1000, h: h / 1000, layer: 0 };
  });
  return { geometry, units: "mm", scenario_id: "nominal" };
}
