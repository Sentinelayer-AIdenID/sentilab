// node --test web/test/door-token.test.mjs
// The scoped purpose token v1 (web/src/door/token.js): mint, verify, scope, expiry and tamper. A token is
// spt1.<purpose>.<case>.<exp>.<nonce16hex>.<mac32hex>, HMAC-SHA256 over every field plus the site, keyed by
// DOOR_TOKEN_KEY; it lasts 60 minutes; it is a scoped purpose token, not an identity.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash, createHmac } from "node:crypto";

import { claimsOf, mintToken, scopeError, TOKEN_PATTERN, TOKEN_SECONDS, TOKEN_WORDING, usableKey, verifyToken } from "../src/door/token.js";

// A test-only key, built at run time so no literal in this tree looks like a credential.
const KEY = "token test key ".repeat(3);
const SITE = "sentilab.aidenid.com";
const NOW = Date.UTC(2026, 10, 1, 15, 0, 0);
const NONCE = "0123456789abcdef";
const mint = (purpose = "place-chiplets", extra = {}) => mintToken(KEY, { purpose, site: SITE, now: NOW, nonce: NONCE, ...extra });
const verify = (token, extra = {}) => verifyToken(KEY, token, { site: SITE, now: NOW, ...extra });
// An independent MAC (node:crypto, not Web Crypto) over the documented message.
const macOf = (key, fields) => createHmac("sha256", key).update(JSON.stringify(["sentilab-spt1", ...fields])).digest("hex").slice(0, 32);

test("a minted token has the documented shape and an independently computed MAC", async () => {
  const token = await mint();
  const exp = String(NOW / 1000 + 3600);
  assert.equal(token, `spt1.place-chiplets.cpu-dram.${exp}.${NONCE}.${macOf(KEY, [SITE, "place-chiplets", "cpu-dram", exp, NONCE])}`);
  assert.match(token, TOKEN_PATTERN);
  assert.equal(TOKEN_SECONDS, 3600);
  assert.equal(TOKEN_WORDING, "scoped purpose token; not an identity");
  for (const purpose of ["review", "read"]) assert.match(await mint(purpose), new RegExp(`^spt1\\.${purpose}\\.cpu-dram\\.`));
  await assert.rejects(mint("anything"), /unknown purpose/);
  await assert.rejects(mint("place-chiplets", { nonce: "XYZ" }), /bad nonce/);
  const random = await mintToken(KEY, { purpose: "read", site: SITE, now: NOW });
  assert.match(random, TOKEN_PATTERN);
  assert.notEqual(random.split(".")[4], (await mintToken(KEY, { purpose: "read", site: SITE, now: NOW })).split(".")[4], "fresh random nonces");
});

test("a valid token verifies to its claims: principal anon-token/1:sha256(nonce), short_id its first 4 hex", async () => {
  const verdict = await verify(await mint());
  assert.equal(verdict.ok, true);
  const digest = createHash("sha256").update(NONCE).digest("hex");
  assert.deepEqual(verdict.claims, { v: "spt1", purpose: "place-chiplets", case: "cpu-dram", exp: NOW / 1000 + 3600,
    expires_at: "2026-11-01T16:00:00Z", nonce: NONCE, site: SITE, principal: `anon-token/1:${digest}`, short_id: digest.slice(0, 4) });
  assert.deepEqual(await claimsOf({ purpose: "place-chiplets", exp: NOW / 1000 + 3600, nonce: NONCE, site: SITE }), verdict.claims);
  assert.ok(!JSON.stringify(verdict.claims).includes(KEY), "claims never carry the key");
});

test("expiry: valid until the last second, token_expired from exp on; the MAC is checked first", async () => {
  const token = await mint();
  assert.equal((await verify(token, { now: NOW + 3599 * 1000 })).ok, true);
  for (const later of [3600, 3601, 86400]) {
    assert.deepEqual(await verify(token, { now: NOW + later * 1000 }), { ok: false, status: 401, error: "token_expired" });
  }
  // An expired token with a bad MAC is invalid, not expired: nothing is learnt about tokens it did not get.
  const forged = token.replace(/[0-9a-f]{32}$/, "0".repeat(32));
  assert.deepEqual(await verify(forged, { now: NOW + 7200 * 1000 }), { ok: false, status: 401, error: "token_invalid" });
});

test("an expiry further out than one lifetime is invalid even with a good MAC", async () => {
  const far = String(NOW / 1000 + 3600 + 61);
  const token = `spt1.read.cpu-dram.${far}.${NONCE}.${macOf(KEY, [SITE, "read", "cpu-dram", far, NONCE])}`;
  assert.deepEqual(await verify(token), { ok: false, status: 401, error: "token_invalid" });
  const edge = String(NOW / 1000 + 3600 + 60);
  assert.equal((await verify(`spt1.read.cpu-dram.${edge}.${NONCE}.${macOf(KEY, [SITE, "read", "cpu-dram", edge, NONCE])}`)).ok, true);
});

test("tamper: every field, the site and the key are bound by the MAC", async () => {
  const token = await mint();
  const [v, purpose, caseId, exp, nonce, mac] = token.split(".");
  const forged = [
    [v, "review", caseId, exp, nonce, mac], [v, "read", caseId, exp, nonce, mac],
    [v, purpose, caseId, String(Number(exp) - 1), nonce, mac], [v, purpose, caseId, String(Number(exp) - 600), nonce, mac],
    [v, purpose, caseId, exp, `${nonce.slice(0, 15)}0`, mac], [v, purpose, caseId, exp, "fedcba9876543210", mac],
    [v, purpose, caseId, exp, nonce, `${mac.slice(0, 31)}${mac.endsWith("0") ? "1" : "0"}`], [v, purpose, caseId, exp, nonce, "0".repeat(32)],
  ].map((parts) => parts.join("."));
  for (const t of forged) assert.deepEqual(await verify(t), { ok: false, status: 401, error: "token_invalid" }, t);
  assert.deepEqual(await verify(token, { site: "staging.sentilab.aidenid.com" }), { ok: false, status: 401, error: "token_invalid" }, "another site");
  assert.deepEqual(await verifyToken(`${KEY}x`, token, { site: SITE, now: NOW }), { ok: false, status: 401, error: "token_invalid" }, "another key");
  // Every single-character change anywhere in the token is refused.
  for (let i = 0; i < token.length; i += 1) {
    const swap = token[i] === "a" ? "b" : token[i] === "." ? "-" : "a";
    const changed = token.slice(0, i) + swap + token.slice(i + 1);
    assert.equal((await verify(changed)).ok, false, `position ${i}`);
  }
});

test("shape: anything but the exact grammar is token_invalid; nothing at all is token_missing", async () => {
  const token = await mint();
  for (const missing of [null, undefined, ""]) assert.deepEqual(await verify(missing), { ok: false, status: 401, error: "token_missing" });
  for (const bad of [` ${token}`, `${token} `, `${token}\n`, token.toUpperCase(), token.replace("spt1", "spt2"),
    token.replace("cpu-dram", "ascend910"), token.replace("place-chiplets", "place_chiplets"), `${token}.x`, token.slice(0, -1),
    token.replaceAll(".", "%2E"), "spt1", 12345, {}, [token], "x".repeat(5000), token.replace(/^spt1\./, "spt1..")]) {
    assert.deepEqual(await verify(bad), { ok: false, status: 401, error: "token_invalid" }, String(bad).slice(0, 40));
  }
});

test("scope: a token works only for its own purpose; elsewhere the contract's exact 403 body", async () => {
  const claims = (await verify(await mint("review"))).claims;
  assert.equal(scopeError(claims, "review"), null);
  assert.deepEqual(scopeError(claims, "place-chiplets"), { error: "token_scope", allowed: "review" });
  const place = (await verify(await mint())).claims;
  assert.equal(scopeError(place, "place-chiplets"), null);
  assert.deepEqual(scopeError(place, "read"), { error: "token_scope", allowed: "place-chiplets" });
});

test("the key must be a string of at least 32 characters, or the door stays closed", () => {
  assert.equal(usableKey({ DOOR_TOKEN_KEY: KEY }), KEY);
  for (const env of [{}, null, undefined, { DOOR_TOKEN_KEY: "" }, { DOOR_TOKEN_KEY: "x".repeat(31) }, { DOOR_TOKEN_KEY: 12345678901234567890123456789012345 }]) {
    assert.equal(usableKey(env), null);
  }
  assert.equal(usableKey({ DOOR_TOKEN_KEY: "x".repeat(32) }), "x".repeat(32));
});
