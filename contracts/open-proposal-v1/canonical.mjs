// Open-proposal contract v1: canonical JSON (RFC 8785 JCS) and every hash the contract binds, for JavaScript clients
// and pages. Isomorphic: Node 20+ and browsers, through Web Crypto; no imports. The Python reference is
// open_proposals/contract/canonical.py, over sentilab_core/envelope.py's canonical(). Both run vectors-canonical.json.
//
// Canonical JSON: object keys sorted by UTF-16 code units (JavaScript's default string order), numbers and strings as
// JSON.stringify writes them (ECMAScript shortest round trip; only quote, backslash and control characters escaped),
// no whitespace, then UTF-8. A nonfinite number or a lone surrogate is refused, never written as null or escaped.

const SOURCE_PREFIX = "sentilab-open-source/1:";
const PSEUDONYM_DOMAIN = "sentilab-open-pseudonym/1";
const TRANSPORT_DOMAIN = "sentilab-open-transport/1";
const SALT_DOMAIN = "sentilab-open-salt/1";
const CAPABILITY_DOMAIN = "sentilab-open-capability/1";
export const TRANSPORT_PREFIX = "open-tk1-";
export const TRANSPORT_MAX_LENGTH = 128;
export const CAPABILITY_PREFIX = "opencap1-";

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

export function geometryObject(proposal, manifest) {
  return {
    schema: "sentilab-open-geometry/1", problem: proposal.problem, fixture_config_sha256: manifest.fixture.config_sha256,
    units: proposal.units, anchor: proposal.anchor, lattice_um: proposal.lattice_um,
    dies: proposal.dies.map((die) => ({ die: die.die, x_um: die.x_um, y_um: die.y_um, rot_deg: die.rot_deg })),
  };
}

export const geometrySha256 = (proposal, manifest) => digest(geometryObject(proposal, manifest));
export const proposalSha256 = (proposal) => digest(proposal);
export const manifestId = (manifest) => digest(manifest);
export const bodySha256 = (noteBytes) => sha256Hex(noteBytes);
export const sourceRef = (actionId) => sha256Hex(utf8(SOURCE_PREFIX + actionId));
export const ciphertextRef = (ageFileBytes) => sha256Hex(ageFileBytes);
export const capabilitySha256 = (capability) => sha256Hex(utf8(capability));

export function actorSlot(actorKind, actorAgentId) {
  if (actorKind === "human" && actorAgentId === null) return "human";
  if (actorKind === "agent" && typeof actorAgentId === "string" && actorAgentId) return `agent:${actorAgentId}`;
  throw new Error("actor kind and agent id disagree");
}

// The transport idempotency key: send it as Senti's idempotencyKey. Same canonical content from the same room,
// account and actor slot gives the same key; other content gives a new key under the same proposal_key.
export async function transportId({ room, account_id, actor_kind, actor_agent_id, manifest_id, proposal_key,
  proposal_sha256 }) {
  const material = canonical([TRANSPORT_DOMAIN, room, account_id, actorSlot(actor_kind, actor_agent_id), manifest_id,
    proposal_key, proposal_sha256]);
  const key = TRANSPORT_PREFIX + await sha256Hex(utf8(material));
  if (key.length > TRANSPORT_MAX_LENGTH) throw new Error("transport id exceeds the Idempotency-Key limit");
  return key;
}

export function runId(manifestId_, participantRef_) {
  return `open-${manifestId_.slice(0, 8)}-${participantRef_ === "sentilab" ? "sentilab" : participantRef_.slice(0, 16)}`;
}

// Server side: the public pseudonym, keyed per challenge. Clients never hold the key.
export function participantRef(key, challenge, accountId) {
  if (key.length < 32) throw new Error("the pseudonym key is at least 32 bytes");
  return hmacSha256Hex(key, utf8(canonical([PSEUDONYM_DOMAIN, challenge, accountId])));
}

// A sealed proposal's salt: derived from the client's own 32-byte secret, so a retry recomputes it.
export function deriveSalt(clientSecret, manifestId_, proposalKey) {
  if (clientSecret.length < 32) throw new Error("the client secret is at least 32 bytes");
  return hmacSha256Hex(clientSecret, utf8(canonical([SALT_DOMAIN, manifestId_, proposalKey])));
}

// The bearer capability for one sealed revision at one epoch: whoever holds it can read that revision's private
// status, results and receipt. It is a secret (never logged; the server keeps only its sha256) and proves nothing
// about authorship. Rotation moves to the next epoch.
export async function capability(salt, manifestId_, proposalSha256_, epoch = 1) {
  const key = fromHex(salt);
  if (key.length !== 32) throw new Error("the salt is 32 bytes");
  if (!Number.isSafeInteger(epoch) || epoch < 1) throw new Error("the epoch is a positive integer");
  return CAPABILITY_PREFIX + await hmacSha256Hex(key, utf8(canonical([CAPABILITY_DOMAIN, manifestId_, proposalSha256_,
    epoch])));
}

// values for a receipt, as the conductor writes them: one exact integer ratio per coordinate, rounded once.
export function conductorGeometry(proposal, manifest) {
  const geometry = proposal.dies.map((die) => {
    const spec = manifest.dies[die.die];
    const [w, h] = die.rot_deg === 90 ? [spec.h_um, spec.w_um] : [spec.w_um, spec.h_um];
    return { id: `tap-chiplet-${die.die}`, xLL: (2 * die.x_um - w) / 2000, yLL: (2 * die.y_um - h) / 2000,
      w: w / 1000, h: h / 1000, layer: 0 };
  });
  return { geometry, units: "mm", scenario_id: "nominal" };
}
