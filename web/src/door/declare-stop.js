// The operator's stop for declarations: warden's second condition for turning them on (wrangler.jsonc), that one pass or
// one network prefix can be stopped from declaring. The hide works per event (app/door/moderation.py), so without a stop
// a repost would be public at once. Two Worker variables, which the operator sets and wrangler.jsonc ships empty:
//   DOOR_DECLARE_DENY_IDS       pass short ids: the 4 hex the public feeds show for each declaration, the first 4 of
//                               sha256(the pass's nonce), as the intake derives them (token.js claimsOf); either case
//   DOOR_DECLARE_DENY_PREFIXES  CIDR prefixes of the client address, IPv4 or IPv6 (203.0.113.0/24, 2001:db8::/32); a bare
//                               address is that one address, and host bits are ignored
// Entries are separated by commas or whitespace. An opt-in from a listed pass, or from a client address in a listed
// prefix, is refused at the door before anything is sent (door.js declare), in the shape and words of the door's other
// refusals, which name no list (declare.js not_accepted). While a prefix is listed, a client address the door can't read
// is refused too. The client address is CF-Connecting-IP, which the door's limiters key on.
// A bad configuration fails closed and never fails the Worker. An entry that doesn't parse is ignored and logged by its
// position, never its text and never a client address; the other entries still apply. A variable that isn't text at
// all, or a read that throws, refuses every opt-in while it lasts, and is logged. Nothing here runs unless
// DOOR_DECLARATIONS is "on": the declare route doesn't exist otherwise (door.js doorRoute), so the lists can't turn
// declarations on or change anything while they are off.
// A module of its own because worker.js may export nothing but its default handler.

const DENY_IDS = "DOOR_DECLARE_DENY_IDS";
const DENY_PREFIXES = "DOOR_DECLARE_DENY_PREFIXES";
const SHORT_ID = /^[0-9a-f]{4}$/i;
const DECIMAL = /^(0|[1-9][0-9]{0,2})$/;
const GROUP = /^[0-9a-f]{1,4}$/i;

// An IPv4 or IPv6 address as its 4 or 16 bytes; null for anything else: a leading zero in an IPv4 part, a zone, the
// embedded IPv4 form of IPv6, a list, spaces.
function addressBytes(text) {
  if (typeof text !== "string") return null;
  if (!text.includes(":")) {
    const parts = text.split(".");
    return parts.length === 4 && parts.every((part) => DECIMAL.test(part) && Number(part) <= 255) ? Uint8Array.from(parts, Number) : null;
  }
  const halves = text.split("::");
  if (halves.length > 2) return null;
  const [head, tail = []] = halves.map((half) => (half === "" ? [] : half.split(":")));
  const given = head.length + tail.length;
  if (halves.length === 1 ? given !== 8 : given > 7) return null;
  const groups = [...head, ...Array(8 - given).fill("0"), ...tail];
  if (!groups.every((group) => GROUP.test(group))) return null;
  const bytes = new Uint8Array(16);
  groups.forEach((group, i) => {
    const value = parseInt(group, 16);
    bytes[2 * i] = value >> 8;
    bytes[2 * i + 1] = value & 0xff;
  });
  return bytes;
}

// A prefix entry as { bytes, bits }, or null when it doesn't parse.
function prefixFrom(entry) {
  const slash = entry.indexOf("/");
  const bytes = addressBytes(slash === -1 ? entry : entry.slice(0, slash));
  if (bytes === null) return null;
  if (slash === -1) return { bytes, bits: bytes.length * 8 };
  const bits = entry.slice(slash + 1);
  return DECIMAL.test(bits) && Number(bits) <= bytes.length * 8 ? { bytes, bits: Number(bits) } : null;
}

// Whether an address is in a prefix: the same family, and the prefix's first bits equal.
function inPrefix(address, { bytes, bits }) {
  if (address.length !== bytes.length) return false;
  for (let at = 0; at < bits; at += 8) {
    const mask = bits - at >= 8 ? 0xff : (0xff << (8 - (bits - at))) & 0xff;
    if ((address[at >> 3] & mask) !== (bytes[at >> 3] & mask)) return false;
  }
  return true;
}

// A list variable's parsed entries, or null when its value isn't text. An entry that doesn't parse is left out and
// logged by its position among the entries.
function readList(env, name, parse) {
  const value = env?.[name];
  if (value === undefined || value === null) return [];
  if (typeof value !== "string") {
    console.warn(`door: ${name} isn't text, so every declaration is refused until it is fixed`);
    return null;
  }
  const kept = [];
  const ignored = [];
  value.split(/[\s,]+/).filter((entry) => entry !== "").forEach((entry, index) => {
    const parsed = parse(entry);
    if (parsed === null) ignored.push(index + 1);
    else kept.push(parsed);
  });
  if (ignored.length > 0) console.warn(`door: ${name}: entries ${ignored.join(", ")} don't parse and are ignored; the other entries apply`);
  return kept;
}

// Whether an opt-in from this pass (its short id) and this client address (CF-Connecting-IP, or null) is stopped.
export function declareStopped(env, { shortId, address }) {
  try {
    const ids = readList(env, DENY_IDS, (entry) => (SHORT_ID.test(entry) ? entry.toLowerCase() : null));
    const prefixes = readList(env, DENY_PREFIXES, prefixFrom);
    if (ids === null || prefixes === null) return true;
    if (ids.includes(shortId)) return true;
    if (prefixes.length === 0) return false;
    const bytes = addressBytes(address);
    return bytes === null || prefixes.some((prefix) => inPrefix(bytes, prefix));
  } catch {
    console.warn("door: the declaration stop couldn't be read, so this declaration is refused");
    return true;
  }
}
