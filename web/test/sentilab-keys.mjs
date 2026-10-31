// Test keys for the SentiLab view tests, derived at run time by the rule in vectors-view.json:
// seed = sha256("sentilab-view-test-key:" + name), private key = Ed25519 from that seed (PKCS#8 DER: a fixed
// 16-byte Ed25519 header, then the seed). Nothing is stored: anyone can derive these keys, so they are never
// production pins.
import { createHash, createPrivateKey, createPublicKey } from "node:crypto";

// ASN.1 header of an Ed25519 PKCS#8 private key, written as bytes (not a key; the same for every Ed25519 key).
const PKCS8_ED25519_HEADER = Buffer.from([0x30, 0x2e, 0x02, 0x01, 0x00, 0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x70, 0x04, 0x22, 0x04, 0x20]);
export const SEED_PREFIX = "sentilab-view-test-key:";
const cache = new Map();

export function testKey(name) {
  if (!cache.has(name)) {
    const seed = createHash("sha256").update(`${SEED_PREFIX}${name}`, "utf8").digest();
    const privateKey = createPrivateKey({ key: Buffer.concat([PKCS8_ED25519_HEADER, seed]), format: "der", type: "pkcs8" });
    const publicKey = createPublicKey(privateKey);
    // The raw key is the 32 bytes after the 12-byte SPKI header.
    const raw = new Uint8Array(publicKey.export({ type: "spki", format: "der" }).subarray(12));
    cache.set(name, { privateKey, publicKey, raw, sha256: createHash("sha256").update(raw).digest("hex") });
  }
  return cache.get(name);
}
