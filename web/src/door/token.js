// The scoped purpose token v1 (AGENT-DOOR section 1): a scoped purpose token; not an identity.
//
//   spt1.<purpose>.<case>.<exp>.<nonce16hex>.<mac>
//
// purpose is place-chiplets, review or read; case is cpu-dram; exp is the expiry in Unix seconds (60 minutes after
// minting); nonce is 64 random bits as 16 lower-case hex; mac is the first 32 lower-case hex (128 bits) of
// HMAC-SHA256, keyed by the Worker secret DOOR_TOKEN_KEY, over JSON ["sentilab-spt1", site, purpose, case, exp, nonce],
// where site is the host the token was minted on. A token from one host (staging) is invalid on another (production).
// It travels in links as ?t= and in a POST body as t; no cookie. It says what the holder declared it is here to do,
// never who it is. The scorer intake binds requests to the principal anon-token/1:<sha256(nonce)>; short_id, the
// first 4 hex of sha256(nonce), is all the views show.
//
// Checks, in order: present, then exact shape, then the MAC (constant time), then expiry, then scope. A token whose
// expiry lies beyond one lifetime from now was never minted with this key and is invalid.
// A module of its own because worker.js may export nothing but its default handler.
import { CASE_ID, PURPOSE_IDS } from "./case.js";

export const TOKEN_WORDING = "scoped purpose token; not an identity";
export const TOKEN_SECONDS = 3600;
export const MIN_KEY_CHARS = 32;
export const TOKEN_PATTERN = /^spt1\.(place-chiplets|review|read)\.(cpu-dram)\.([1-9][0-9]{9})\.([0-9a-f]{16})\.([0-9a-f]{32})$/;
const SKEW_SECONDS = 60;
const encoder = new TextEncoder();
const hex = (bytes) => Array.from(new Uint8Array(bytes), (byte) => byte.toString(16).padStart(2, "0")).join("");

export async function sha256Hex(text) {
  return hex(await crypto.subtle.digest("SHA-256", encoder.encode(text)));
}

async function macHex(key, fields) {
  const imported = await crypto.subtle.importKey("raw", encoder.encode(key), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return hex(await crypto.subtle.sign("HMAC", imported, encoder.encode(JSON.stringify(["sentilab-spt1", ...fields])))).slice(0, 32);
}

// The key, or null when it is missing or too short to use (the door then stays closed).
export function usableKey(env) {
  const key = env?.DOOR_TOKEN_KEY;
  return typeof key === "string" && key.length >= MIN_KEY_CHARS ? key : null;
}

function equalHex(a, b) {
  let diff = a.length ^ b.length;
  for (let i = 0; i < Math.max(a.length, b.length); i += 1) diff |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  return diff === 0;
}

function randomNonce() {
  return hex(crypto.getRandomValues(new Uint8Array(8)));
}

// A new token for this purpose on this site, valid for TOKEN_SECONDS from now (ms).
export async function mintToken(key, { purpose, site, now, nonce = randomNonce() }) {
  if (!PURPOSE_IDS.includes(purpose)) throw new Error("unknown purpose");
  if (!/^[0-9a-f]{16}$/.test(nonce)) throw new Error("bad nonce");
  const exp = String(Math.floor(now / 1000) + TOKEN_SECONDS);
  const mac = await macHex(key, [site, purpose, CASE_ID, exp, nonce]);
  return `spt1.${purpose}.${CASE_ID}.${exp}.${nonce}.${mac}`;
}

// What the scorer intake and the views may know about a valid token: never the key, never the MAC.
export async function claimsOf({ purpose, exp, nonce, site }) {
  const digest = await sha256Hex(nonce);
  return { v: "spt1", purpose, case: CASE_ID, exp, expires_at: new Date(exp * 1000).toISOString().replace(".000Z", "Z"),
    nonce, site, principal: `anon-token/1:${digest}`, short_id: digest.slice(0, 4) };
}

// { ok: true, claims } or { ok: false, status, error }: 401 token_missing, token_invalid or token_expired.
export async function verifyToken(key, token, { site, now }) {
  if (token === null || token === undefined || token === "") return { ok: false, status: 401, error: "token_missing" };
  const match = typeof token === "string" && token.length <= 128 ? TOKEN_PATTERN.exec(token) : null;
  if (!match) return { ok: false, status: 401, error: "token_invalid" };
  const [, purpose, caseId, exp, nonce, mac] = match;
  if (!equalHex(await macHex(key, [site, purpose, caseId, exp, nonce]), mac)) return { ok: false, status: 401, error: "token_invalid" };
  const seconds = Number(exp);
  const nowSeconds = Math.floor(now / 1000);
  if (seconds > nowSeconds + TOKEN_SECONDS + SKEW_SECONDS) return { ok: false, status: 401, error: "token_invalid" };
  if (seconds <= nowSeconds) return { ok: false, status: 401, error: "token_expired" };
  return { ok: true, claims: await claimsOf({ purpose, exp: seconds, nonce, site }) };
}

// null when the token's purpose covers the route; otherwise the 403 body the contract fixes.
export function scopeError(claims, required) {
  return claims.purpose === required ? null : { error: "token_scope", allowed: claims.purpose };
}
