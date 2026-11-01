// The SentiLab agent door (AGENT-DOOR sections 1-3, Amendments 1 and 2): the wall, the scoped purpose token, the
// ENGRAM view, the preview check, the two submit routes, status, the board and the arrivals feed.
//
//   GET  /agents/intent?purpose=        the wall with no purpose; with one, a new token and the next links
//   GET  /agents/engram?t=              sentilab-agent-view/1                       place-chiplets token
//   GET  /agents/check?t=&l=            preview check, local and instant; never a solve   place-chiplets token
//   POST /agents/submit                 {t, layout[, request_key]} JSON, or the confirm page's form (t, l)
//   GET  /s?t=&l=                       the tap-link confirm page: one button that POSTs; a GET never submits
//   GET  /agents/status/<run_id>?t=     one run's state, bound to the token's principal   place-chiplets token
//   GET  /agents/board                  the top 10: class, short id and scores
// Any other method on these paths is 405 read_only; POST /agents/submit is the only new write. Classified agents get
// the wall in place of the agent version of the three mapped pages until they hold a valid token. Without a usable
// DOOR_TOKEN_KEY the door is closed: its routes answer 503 door_closed and the mapped pages keep their agent versions.
//
// The scorer intake (sentilab-api at API_ORIGIN; Lane 2, sentilab PR #81) is called only from here, with the origin token
// and fresh headers, under /api/open/v1/door:
//   POST submit   {token_claims: {purpose, case, nonce, exp}, layout, terms, request_key, class, operator}
//   POST arrival  {class, operator, purpose?, nonce?}: the intake stamps the time and derives short_id (4 hex of
//                 sha256(nonce)); nothing else about a visitor is sent
//   GET  status/<run_id> with x-door-nonce, and board (the board call from the ENGRAM view also sends x-door-nonce)
// The public /api proxy strips x-door-* from visitors' requests and drops a Referer that carries a token; every response
// to a request whose URL can carry a token is no-referrer and private, no-store, no-transform (carriesToken,
// protectToken). The terms version a submission carries is the highest of the intake's board terms.accepted_versions
// (the signed manifest's); without one the door takes no submissions. The submit body is read by the contract's strict
// JSON reader (strict-json.js). Refusals before the POST say nothing was sent and use the intake's vocabulary:
// {schema: "sentilab-door-submit/1", state: "rejected", codes}. Once the POST has been attempted, only the intake's own
// answer counts: anything else is delivery_unknown, with the same request key and the same idempotent retry.
// Rate limits: DOOR_NONCE_LIMITER per token and DOOR_IP_LIMITER per client IP prefix on submit, DOOR_READ_LIMITER per
// prefix on the routes that call the intake; each falls back to an in-memory window per isolate when its binding is
// absent. The intake's own quotas (CPU-seconds per token, the global grant, the bounded queue) are the hard caps. With
// AQUARIUM_POST=on a purpose choice is also posted to the AIdenID collector.
// A module of its own because worker.js may export nothing but its default handler.
import { AGENT_RESPONSE_CACHE, indexOrPreviewCrawler } from "../generated/aidenid-intent-gate/agent-resources.js";
import { agentPathFor } from "../agent-paths.js";
import { preferredAgentType, serveAgentVersion } from "../agent-view.js";
import { CSP } from "../csp.js";
import { identityFor } from "../edge.js";
import { observationFor } from "../vendor/aidenid-registry/agent-registry.mjs";
import { BOARD_METRIC, DIES, PURPOSE_IDS } from "./case.js";
import { agentView, gateZeroFrom } from "./engram.js";
import { parseCompact, parseDies, PREVIEW_LABEL, previewViolations, wireProxyMm } from "./layout.js";
import { confirmHtml, notConfirmedHtml, problemHtml, resultHtml, tokenHtml, tokenJson, tokenMarkdown, wallHtml, wallJson, wallMarkdown } from "./render.js";
import { strictJson } from "./strict-json.js";
import { scopeError, sha256Hex, TOKEN_PATTERN, usableKey, verifyToken, mintToken } from "./token.js";

export const LIMITS = Object.freeze({
  DOOR_NONCE_LIMITER: { limit: 10, periodMs: 60000 },
  DOOR_IP_LIMITER: { limit: 60, periodMs: 60000 },
  DOOR_READ_LIMITER: { limit: 300, periodMs: 60000 },
  DOOR_MINT_LIMITER: { limit: 120, periodMs: 60000 },
});
export const API = Object.freeze({
  submit: "/api/open/v1/door/submit", status: "/api/open/v1/door/status/", board: "/api/open/v1/door/board",
  arrival: "/api/open/v1/door/arrival",
});
// The classifier's own enums (src/vendor/aidenid-classifier/src/types.ts): nothing else is ever sent as a class or an
// operator. "ours" marks SentiLab's own background agents on the board.
export const CLASSES = Object.freeze(["verified_agent", "signed_agent", "declared_agent", "crawler_claimed", "automation", "likely_human", "unknown"]);
export const OPERATORS = Object.freeze(["openai", "google", "meta", "anthropic", "perplexity", "microsoft", "apple", "amazon", "bytedance", "commoncrawl", "deepseek", "unknown"]);
const STATES = new Set(["rejected", "queued", "held", "evaluating", "evaluated", "failed", "replaying", "reproduced", "not_reproduced", "cross_checked", "cancelled", "expired"]);
const REASON_CODES = new Set(["oversize", "not_utf8", "malformed_json", "duplicate_key", "nonfinite_number", "too_deep", "unknown_field",
  "schema_invalid", "unknown_manifest", "manifest_mismatch", "manifest_closed", "not_open_yet", "terms_not_accepted", "die_count",
  "die_order", "out_of_frame", "rotation_not_allowed", "lattice", "margin", "halo_overlap", "min_spacing", "keepout",
  "geometry_hash_mismatch", "idempotency_conflict", "unknown_parent", "unknown_proposal", "participant_suspended",
  "participant_paused", "participant_removed", "rate_limited", "queue_full", "budget_exhausted", "timeout", "stopped",
  "oracle_error", "grant_expired", "interrupted", "binding_mismatch", "router_timeout", "check_unfinished",
  "reproduction_mismatch", "fresh_process_required", "reproduction_failed"]);
const RUN_ID = /^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/;
const REQUEST_KEY = /^[a-z0-9][a-z0-9_-]{0,63}$/;
const TERMS_VERSION = /^sentilab-open-terms\/[1-9][0-9]{0,5}@[0-9a-f]{64}$/;
const SUBMIT_SCHEMA = "sentilab-door-submit/1";
// The intake's HTTP status for a refusal, from its first code (PR #81): 413 oversize, 422 geometry, layout and terms,
// 409 a changed request under a used key, 429 policy, 503 not open; any other transport or envelope code is 400.
const GEOMETRY_CODES = new Set(["die_count", "die_order", "out_of_frame", "rotation_not_allowed", "lattice", "margin", "halo_overlap",
  "min_spacing", "keepout", "geometry_hash_mismatch", "terms_not_accepted"]);
const STATUS_PREFIX = "/agents/status/";
const INGEST_URL = "https://aquarium.internal/api/aquarium/edge";
const BOARD_TTL_MS = 10000;
const MAX_JSON_BYTES = 4096;
const MAX_FORM_BYTES = 2048;
const MAX_API_BYTES = 262144;

// ── responses ─────────────────────────────────────────────────────────────────────────────────────────────────────
const BASE_HEADERS = Object.freeze({ "cache-control": AGENT_RESPONSE_CACHE, "content-security-policy": CSP, "referrer-policy": "no-referrer",
  "x-robots-tag": "noindex", "x-content-type-options": "nosniff" });
function respond(request, status, body, type, extra = {}) {
  return new Response(request.method === "HEAD" ? null : body, { status, headers: { ...BASE_HEADERS, "content-type": type, ...extra } });
}
const json = (request, status, value, extra) => respond(request, status, `${JSON.stringify(value, null, 1)}\n`, "application/json; charset=utf-8", extra);
const html = (request, status, text, extra) => respond(request, status, text, "text/html; charset=utf-8", extra);
const markdown = (request, status, text) => respond(request, status, text, "text/markdown; charset=utf-8");
const refuse = (request, format, status, body, extra) => (format === "html"
  ? html(request, status, problemHtml(body.error === "refused" ? "layout" : body.error, (body.codes ?? []).filter((c) => REASON_CODES.has(c.code))), extra)
  : json(request, status, body, extra));
const negotiate = (request) => preferredAgentType(request.headers.get("accept"), { md: true, json: true });
const retryAfter = () => new Date(Date.now() + 60000).toISOString().replace(/\.\d{3}Z$/, "Z");
const limited = (request, format) => refuse(request, format, 429, { error: "rate_limited", retry_after: retryAfter() }, { "retry-after": "60" });
const closed = (request, format) => refuse(request, format, 503, { error: "door_closed" });
function refusalStatus(codes) {
  const first = codes[0]?.code;
  if (first === "oversize") return 413;
  if (GEOMETRY_CODES.has(first)) return 422;
  if (first === "idempotency_conflict") return 409;
  if (first === "rate_limited") return 429;
  if (first === "not_open_yet" || first === "manifest_closed") return 503;
  return 400;
}
// A refused submission, in the intake's own shape.
function rejected(request, format, codes, { limits, headers } = {}) {
  if (format === "html") return html(request, refusalStatus(codes), problemHtml(codes[0]?.code === "rate_limited" ? "rate_limited" : codes[0]?.code === "not_open_yet" ? "door_closed" : "layout", codes), headers);
  return json(request, refusalStatus(codes), { schema: SUBMIT_SCHEMA, state: "rejected", codes, ...(limits ? { limits } : {}) }, headers);
}
const submitLimited = (request, format) => rejected(request, format, [{ code: "rate_limited", retry_after: retryAfter() }],
  { limits: ["request_rate"], headers: { "retry-after": "60" } });
// ── token-bearing URLs ────────────────────────────────────────────────────────────────────────────────────────────
// A URL can carry a scoped purpose token when it has a t parameter, or a token-shaped value anywhere in its query (plain
// or percent-encoded). Valid or not, it is treated as token material.
const TOKEN_SHAPE = /spt1(?:\.|%2e)/i;
export function carriesToken(url) {
  return url.searchParams.has("t") || TOKEN_SHAPE.test(url.search);
}

// The response to such a request never hands its URL on: no Referer from the page, no stored copy, no edge rewriting.
// The status, body and every other header are left as they are.
export function protectToken(response) {
  const headers = new Headers(response.headers);
  headers.set("referrer-policy", "no-referrer");
  headers.set("cache-control", AGENT_RESPONSE_CACHE);
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
}

// The intake's open feeds that the public /api proxy passes on (the board, results and events the human view reads).
export const DOOR_FEEDS = /^\/api\/open\/v1\/door\/(board|results|events)$/;

// A copy of a feed answer without any "operator" field, at any depth: the declared operator stays with the intake, as
// the door's own routes already keep it.
export function withoutOperators(value) {
  if (Array.isArray(value)) return value.map(withoutOperators);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(Object.entries(value).filter(([key]) => key !== "operator").map(([key, item]) => [key, withoutOperators(item)]));
}

// A Referer the /api proxy must drop because it carries a token.
export function tokenBearing(referer) {
  if (!referer) return false;
  if (TOKEN_SHAPE.test(referer)) return true;
  try { return new URL(referer).searchParams.has("t"); } catch { return /[?&]t=/.test(referer); }
}

// The highest of the board's accepted terms versions (the signed manifest's), or null.
function termsFrom(value) {
  const versions = Array.isArray(value?.terms?.accepted_versions) ? value.terms.accepted_versions : [];
  const valid = versions.filter((v) => typeof v === "string" && TERMS_VERSION.test(v));
  const number = (v) => Number(/^sentilab-open-terms\/([0-9]+)@/.exec(v)[1]);
  return valid.reduce((best, v) => (best === null || number(v) > number(best) ? v : best), null);
}

// ── rate limits ───────────────────────────────────────────────────────────────────────────────────────────────────
const windows = new Map();
function memoryAllow(key, { limit, periodMs }, now) {
  const hits = (windows.get(key) ?? []).filter((at) => at > now - periodMs);
  const ok = hits.length < limit;
  if (ok) hits.push(now);
  windows.delete(key);
  windows.set(key, hits);
  if (windows.size > 20000) windows.delete(windows.keys().next().value);
  return ok;
}

// true when one more request under this key is allowed. The Workers binding when present, else the isolate's window.
export async function allow(env, binding, key) {
  const limiter = env?.[binding];
  if (limiter && typeof limiter.limit === "function") {
    try { return (await limiter.limit({ key })).success === true; } catch { /* fall through to the isolate's window */ }
  }
  return memoryAllow(`${binding}|${key}`, LIMITS[binding], Date.now());
}

// The client's /24 (IPv4) or /48 (IPv6) from CF-Connecting-IP; "unknown" when there is none.
export function ipPrefix(ip) {
  const v4 = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.\d{1,3}$/.exec(ip ?? "");
  if (v4) return `${v4[1]}.${v4[2]}.${v4[3]}.0/24`;
  const text = String(ip ?? "").toLowerCase();
  if (!/^[0-9a-f:]{2,39}$/.test(text) || !text.includes(":")) return "unknown";
  const [head, tail] = text.split("::");
  const front = head ? head.split(":") : [];
  const back = tail ? tail.split(":") : [];
  const groups = text.includes("::") ? [...front, ...Array(Math.max(0, 8 - front.length - back.length)).fill("0"), ...back] : front;
  if (groups.length !== 8 || groups.some((g) => !/^[0-9a-f]{1,4}$/.test(g))) return "unknown";
  return `${groups.slice(0, 3).map((g) => g.replace(/^0+(?=.)/, "")).join(":")}::/48`;
}
const prefixOf = (request) => ipPrefix(request.headers.get("cf-connecting-ip"));

// ── the scorer intake ─────────────────────────────────────────────────────────────────────────────────────────────
// The API origin: HTTPS, or a loopback HTTP stub for local runs (a deployed Worker cannot reach loopback).
function apiOrigin(env) {
  const origin = String(env?.API_ORIGIN || "").replace(/\/+$/, "");
  if (origin.startsWith("https://") || /^http:\/\/(127\.0\.0\.1|localhost)(:[0-9]{1,5})?$/.test(origin)) return origin;
  return null;
}

// { ok: true, status, json } or { ok: false, reason }. Never throws; the body is read within the same deadline.
export async function callApi(env, path, { method = "GET", body, nonce, host, timeoutMs }) {
  const origin = apiOrigin(env);
  if (!origin) return { ok: false, attempted: false, reason: "not_configured" };
  const headers = new Headers({ accept: "application/json" });
  if (env.ORIGIN_TOKEN) headers.set("x-origin-token", env.ORIGIN_TOKEN);
  if (host) headers.set("x-forwarded-host", host);
  if (nonce) headers.set("x-door-nonce", nonce);
  if (body !== undefined) headers.set("content-type", "application/json");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(origin + path, { method, headers, redirect: "manual", signal: controller.signal,
      body: body === undefined ? undefined : JSON.stringify(body) });
    const text = await res.text();
    if (text.length > MAX_API_BYTES) return { ok: true, attempted: true, status: res.status, json: null };
    let value = null;
    try { value = JSON.parse(text); } catch { /* not JSON: treated as no answer */ }
    return { ok: true, attempted: true, status: res.status, json: value };
  } catch {
    // Once fetch has been called, the request may have reached the intake: never "nothing was sent".
    return { ok: false, attempted: true, reason: controller.signal.aborted ? "timeout" : "unreachable" };
  } finally {
    clearTimeout(timer);
  }
}

const finite = (v, lo, hi) => typeof v === "number" && Number.isFinite(v) && v >= lo && v <= hi;
const BOARD_CLASSES = new Set([...CLASSES, "ours"]);

// What the door reads from the intake's board answer (sentilab-door-board/1), each part checked alone: admission ("open"
// only when door.open is true), at most ten entries of top holding class, short id, state, verdict and numbers only
// (never the operator, the label or anything else), and a token's CPU-seconds left when the intake reports them.
export function readBoard(answer) {
  const value = answer?.ok && answer.status === 200 && answer.json && typeof answer.json === "object" ? answer.json : null;
  const open = value?.door?.open;
  const admission = open === true ? "open" : open === false ? "closed" : "unknown";
  const rows = Array.isArray(value?.top) ? value.top : null;
  const board = rows && rows.slice(0, 100).flatMap((row) => {
    if (!row || typeof row !== "object" || !BOARD_CLASSES.has(row.class) || typeof row.short_id !== "string" || !/^[0-9a-f]{4}$/.test(row.short_id)) return [];
    const entry = { class: row.class, short_id: row.short_id };
    if (STATES.has(row.status)) entry.state = row.status;
    if (finite(row[BOARD_METRIC.metric_id], -273.15, 10000)) entry[BOARD_METRIC.metric_id] = row[BOARD_METRIC.metric_id];
    if (finite(row.wire_proxy_mm, 0, 1000)) entry.wire_proxy_mm = row.wire_proxy_mm;
    if (row.verdict === "candidate") entry.verdict = "candidate";
    return [entry];
  }).slice(0, 10).map((entry, index) => ({ rank: index + 1, ...entry }));
  const left = value?.token?.cpu_s_remaining;
  return { reachable: value !== null, admission, board, cpuSecondsLeft: finite(left, 0, 100000) ? left : null, terms: termsFrom(value) };
}

let boardCache = null;
// The intake's board without token claims, shared for BOARD_TTL_MS per isolate (admission state included).
async function sharedBoard(env, url) {
  const origin = apiOrigin(env);
  const now = Date.now();
  if (boardCache && boardCache.origin === origin && now - boardCache.at < BOARD_TTL_MS) return boardCache.value;
  const value = readBoard(await callApi(env, API.board, { host: url.host, timeoutMs: 1500 }));
  boardCache = { origin, at: now, value };
  return value;
}

// Test hook: forget the isolate's board cache and rate windows.
export function resetDoorState() {
  boardCache = null;
  windows.clear();
}

// Root's saved gate-zero record, read through the asset layer (never copied into this Worker).
async function gateZero(request, env, url) {
  try {
    const res = await env.ASSETS.fetch(new Request(new URL("/agents/evidence.json", url), { method: "GET" }));
    return res.ok ? gateZeroFrom(await res.json()) : null;
  } catch {
    return null;
  }
}

// ── arrivals ──────────────────────────────────────────────────────────────────────────────────────────────────────
async function bounded(task, ms) {
  const controller = new AbortController();
  let timer;
  try {
    return await Promise.race([task(controller.signal),
      new Promise((_, reject) => { timer = setTimeout(() => { controller.abort(); reject(new Error("timeout")); }, ms); })]);
  } finally {
    clearTimeout(timer);
  }
}

// The arrival the intake records: the class and declared operator from the classifier's enums, the purpose chosen and
// the token's nonce (the intake keeps only short_id, the first 4 hex of sha256(nonce), and stamps the time). A wall
// view has no purpose and no nonce yet.
export function arrivalOf(identity, purpose, nonce) {
  return { class: CLASSES.includes(identity?.triage?.class) ? identity.triage.class : "unknown",
    operator: OPERATORS.includes(identity?.operator) ? identity.operator : "unknown",
    ...(PURPOSE_IDS.includes(purpose) ? { purpose } : {}), ...(/^[0-9a-f]{16}$/.test(nonce ?? "") ? { nonce } : {}) };
}

async function postCollector(request, env, identity, event, expiresAt) {
  if (env.AQUARIUM_POST !== "on" || !env.COLLECTOR || !env.INGEST_TOKEN || !identity || !event.purpose) return;
  const declaredAt = new Date().toISOString();
  const observation = observationFor({ triageClass: identity.triage.class, basis: identity.basis,
    userAgent: request.headers.get("user-agent") ?? "", signer: identity.verification?.signer, cfBotCategory: request.cf?.verifiedBotCategory });
  const body = { schemaVersion: 1, siteId: "sentilab", sessionId: crypto.randomUUID(), source: "edge", eventType: "page_view",
    path: "/agents/intent", method: "GET", identity: { ...identity, observation },
    intent: { category: event.purpose, source: "declared_preset", classifierVersion: "intent-gate-v1", declaredAt, expiresAt } };
  await bounded((signal) => env.COLLECTOR.fetch(INGEST_URL, { method: "POST", redirect: "manual", signal,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${env.INGEST_TOKEN}` }, body: JSON.stringify(body) }), 1200);
}

// Fire and forget: nothing here can delay or change a response.
function emitArrival(request, env, ctx, url, { identity, purpose = null, nonce = null, expiresAt = null }) {
  if (typeof ctx?.waitUntil !== "function") return;
  try {
    ctx.waitUntil((async () => {
      if (!(await allow(env, "DOOR_READ_LIMITER", `arrival:${prefixOf(request)}`))) return;
      const who = identity === undefined ? await identityFor(request, env) : identity;
      const event = arrivalOf(who, purpose, nonce);
      await Promise.allSettled([callApi(env, API.arrival, { method: "POST", body: event, host: url.host, timeoutMs: 1200 }),
        postCollector(request, env, who, event, expiresAt)]);
    })().catch(() => undefined));
  } catch { /* a missing or broken execution context never breaks a page */ }
}

// ── tokens on requests ────────────────────────────────────────────────────────────────────────────────────────────
// { claims, token } for a valid token of the required purpose, or the refusal to send.
async function authorize(request, env, url, values, required, format) {
  const key = usableKey(env);
  if (!key) return closed(request, format);
  const token = values.length === 1 ? values[0] : values.length ? "x" : null;
  const verdict = await verifyToken(key, token, { site: url.host, now: Date.now() });
  if (!verdict.ok) return refuse(request, format, verdict.status, { error: verdict.error, get_one: `${url.origin}/agents/intent?purpose=${required}` });
  const scope = scopeError(verdict.claims, required);
  if (scope) return refuse(request, format, 403, scope);
  return { claims: verdict.claims, token };
}

// ── routes ────────────────────────────────────────────────────────────────────────────────────────────────────────
async function wall(request, env, url) {
  const submissions = request.method === "HEAD" ? "unknown" : (await sharedBoard(env, url)).admission;
  const kind = negotiate(request);
  if (kind === "json") return json(request, 200, wallJson(url.origin, submissions));
  if (kind === "md") return markdown(request, 200, wallMarkdown(url.origin, submissions));
  return html(request, 200, wallHtml(url.origin, submissions));
}

async function intent(request, env, ctx, url) {
  const key = usableKey(env);
  if (!key) return closed(request, negotiate(request) ? "json" : "html");
  const values = url.searchParams.getAll("purpose");
  const purpose = values.length === 1 && PURPOSE_IDS.includes(values[0]) ? values[0] : null;
  if (!purpose) return wall(request, env, url);
  const kind = negotiate(request);
  if (request.method === "HEAD") return respond(request, 200, null, kind === "json" ? "application/json; charset=utf-8" : kind === "md" ? "text/markdown; charset=utf-8" : "text/html; charset=utf-8");
  // Tokens are free but not unlimited: a per-prefix allowance, so one client cannot farm them in a burst.
  if (!(await allow(env, "DOOR_MINT_LIMITER", `mint:${prefixOf(request)}`))) return limited(request, kind === "json" ? "json" : "html");
  const now = Date.now();
  const token = await mintToken(key, { purpose, site: url.host, now });
  const { claims } = await verifyToken(key, token, { site: url.host, now });
  const { admission } = await sharedBoard(env, url);
  emitArrival(request, env, ctx, url, { purpose, nonce: claims.nonce, expiresAt: claims.expires_at });
  if (kind === "json") return json(request, 200, tokenJson(url.origin, claims, token, admission));
  if (kind === "md") return markdown(request, 200, tokenMarkdown(url.origin, claims, token, admission));
  return html(request, 200, tokenHtml(url.origin, claims, token, admission));
}

async function engram(request, env, ctx, url) {
  const auth = await authorize(request, env, url, url.searchParams.getAll("t"), "place-chiplets", "json");
  if (auth instanceof Response) return auth;
  if (request.method === "HEAD") return json(request, 200, null);
  const reading = await allow(env, "DOOR_READ_LIMITER", `engram:${prefixOf(request)}`);
  const [live, gate] = await Promise.all([
    reading ? callApi(env, API.board, { nonce: auth.claims.nonce, host: url.host, timeoutMs: 2500 }).then(readBoard) : { admission: "unknown", board: null, cpuSecondsLeft: null, terms: null },
    gateZero(request, env, url)]);
  return json(request, 200, agentView({ origin: url.origin, token: auth.token, claims: auth.claims, submissions: live.admission, terms: live.terms,
    gateZero: gate, board: live.board ?? [], boardStatus: live.board ? "ok" : "unavailable", cpuSecondsLeft: live.cpuSecondsLeft }));
}

function layoutFrom(values) {
  if (values.length === 1) return parseCompact(values[0]);
  return { ok: false, codes: [{ code: "schema_invalid", path: "/l", keyword: values.length ? "maxItems" : "required" }] };
}

async function check(request, env, ctx, url) {
  const auth = await authorize(request, env, url, url.searchParams.getAll("t"), "place-chiplets", "json");
  if (auth instanceof Response) return auth;
  if (request.method === "HEAD") return json(request, 200, null);
  const parsed = layoutFrom(url.searchParams.getAll("l"));
  const base = { schema: "sentilab-agent-check/1", check: PREVIEW_LABEL, solve: "none: a check never starts a solve" };
  if (!parsed.ok) return json(request, 200, { ...base, outcome: "refused", codes: parsed.codes, next: "Fix the layout format (see layout_format in the engram view) and check again." });
  const codes = previewViolations(parsed.dies);
  const view = { ...base, outcome: codes.length ? "illegal_preview" : "legal_preview", codes, layout: parsed.compact,
    dies: parsed.dies.map((die) => ({ id: DIES[die.die].id, ...die })), wire_proxy_mm: wireProxyMm(parsed.dies),
    wire_proxy_note: "preview: the weighted-mean Manhattan proxy, not routed wire" };
  if (codes.length) return json(request, 200, { ...view, next: "Fix the listed rules and check again." });
  return json(request, 200, { ...view, next: { tap_link: `${url.origin}/s?t=${auth.token}&l=${parsed.compact}`,
    submit: { method: "POST", url: `${url.origin}/agents/submit`, content_type: "application/json", body: { t: auth.token, layout: parsed.compact } } } });
}

async function confirm(request, env, ctx, url) {
  const auth = await authorize(request, env, url, url.searchParams.getAll("t"), "place-chiplets", "html");
  if (auth instanceof Response) return auth;
  const parsed = layoutFrom(url.searchParams.getAll("l"));
  if (!parsed.ok) return html(request, 400, problemHtml("layout", parsed.codes));
  if (request.method === "HEAD") return html(request, 200, null);
  const { reachable, admission, terms } = await sharedBoard(env, url);
  return html(request, 200, confirmHtml({ claims: auth.claims, token: auth.token, compact: parsed.compact, dies: parsed.dies,
    violations: previewViolations(parsed.dies), wireMm: wireProxyMm(parsed.dies), reachable, submissions: admission, terms }));
}

async function board(request, env, ctx, url) {
  if (request.method === "HEAD") return json(request, 200, null);
  const live = await sharedBoard(env, url);
  return json(request, 200, { schema: "sentilab-agent-board/1", label: "simulated, not silicon", metric_id: BOARD_METRIC.metric_id,
    unit: BOARD_METRIC.unit, board: live.board ?? [], board_status: live.board ? "ok" : "unavailable", submissions: live.admission });
}

async function status(request, env, ctx, url) {
  const runId = url.pathname.slice(STATUS_PREFIX.length);
  if (!RUN_ID.test(runId)) return json(request, 404, { error: "unknown_run" });
  const auth = await authorize(request, env, url, url.searchParams.getAll("t"), "place-chiplets", "json");
  if (auth instanceof Response) return auth;
  if (request.method === "HEAD") return json(request, 200, null);
  if (!(await allow(env, "DOOR_READ_LIMITER", `status:${prefixOf(request)}`))) return limited(request, "json");
  const answer = await callApi(env, API.status + runId, { nonce: auth.claims.nonce, host: url.host, timeoutMs: 2500 });
  const value = answer.ok && answer.json && typeof answer.json === "object" && !Array.isArray(answer.json) ? answer.json : null;
  // The intake's own answers only: a run's status, or its 404 for a run this token did not submit. The declared
  // operator stays with the intake: agents never read a vendor name from the door.
  if (answer.status === 200 && value?.schema === "sentilab-door-status/1") {
    const { operator, ...shown } = value;
    return json(request, 200, shown);
  }
  if (answer.status === 404 && value?.error === "run_not_found") return json(request, 404, { error: "run_not_found" });
  return json(request, 503, { error: "intake_unavailable" });
}

// The submitted body, read against a byte cap and a deadline: { text } or { status, code }.
async function readBody(request, max) {
  const length = request.headers.get("content-length");
  if (length !== null && (!/^[0-9]{1,9}$/.test(length) || Number(length) > max)) return { status: 413, code: { code: "oversize", size_bytes: Math.min(Number(length) || 0, 1000000000) } };
  if (!request.body) return { text: "" };
  const reader = request.body.getReader();
  const chunks = [];
  let total = 0;
  let finished = false;
  const deadline = Date.now() + 2000;
  try {
    for (let reads = 0; reads < 256 && !finished; reads += 1) {
      const remaining = deadline - Date.now();
      if (remaining <= 0) return { status: 408, code: { code: "malformed_json" } };
      let timer;
      const late = new Promise((resolve) => { timer = setTimeout(() => resolve(null), remaining); });
      const chunk = await Promise.race([reader.read(), late]).finally(() => clearTimeout(timer));
      if (chunk === null) return { status: 408, code: { code: "malformed_json" } };
      if (chunk.done) { finished = true; break; }
      total += chunk.value.byteLength;
      if (total > max) return { status: 413, code: { code: "oversize", size_bytes: total } };
      chunks.push(chunk.value);
    }
  } catch {
    return { status: 400, code: { code: "malformed_json" } };
  } finally {
    if (!finished) reader.cancel().catch(() => undefined);
  }
  if (!finished) return { status: 413, code: { code: "oversize", size_bytes: total } };
  const bytes = new Uint8Array(total);
  let at = 0;
  for (const chunk of chunks) { bytes.set(chunk, at); at += chunk.byteLength; }
  // ignoreBOM keeps a leading byte-order mark in the text, as Python's strict UTF-8 decode does (it is then malformed).
  try { return { text: new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(bytes) }; } catch { return { status: 400, code: { code: "not_utf8" } }; }
}

const fieldError = (path, keyword) => ({ code: "schema_invalid", path, keyword });

// The submission's fields: { t, layout, requestKey } or { codes }. Unknown fields are refused and never echoed.
function fieldsOf(text, form) {
  if (form) {
    const params = new URLSearchParams(text);
    const keys = [...params.keys()];
    if (keys.some((k) => k !== "t" && k !== "l")) return { codes: [{ code: "unknown_field", path: "" }] };
    if (params.getAll("t").length !== 1) return { codes: [fieldError("/t", "required")] };
    if (params.getAll("l").length !== 1) return { codes: [fieldError("/l", "required")] };
    return { t: params.get("t"), layout: params.get("l"), requestKey: null };
  }
  // The contract's strict reader, before any field is chosen: duplicate keys at any depth, too-deep bodies and
  // non-finite numbers are refused with its codes, never resolved by keeping the last value.
  const read = strictJson(text);
  if (read.codes) return { codes: read.codes };
  const value = read.value;
  if (Object.keys(value).some((k) => !["t", "layout", "request_key"].includes(k))) return { codes: [{ code: "unknown_field", path: "" }] };
  if (typeof value.t !== "string") return { codes: [fieldError("/t", Object.hasOwn(value, "t") ? "type" : "required")] };
  if (!Object.hasOwn(value, "layout")) return { codes: [fieldError("/layout", "required")] };
  if (typeof value.layout !== "string" && !Array.isArray(value.layout)) return { codes: [fieldError("/layout", "type")] };
  if (Object.hasOwn(value, "request_key") && (typeof value.request_key !== "string" || !REQUEST_KEY.test(value.request_key))) {
    return { codes: [fieldError("/request_key", "pattern")] };
  }
  return { t: value.t, layout: value.layout, requestKey: value.request_key ?? null };
}

// What a person sees after the confirm page's button: only the state, the run id and codes from fixed lists.
function outcomeOf(answer) {
  const value = answer.json ?? {};
  const state = STATES.has(value.state) || value.state === "queue_full" ? value.state : null;
  const runId = typeof value.run_id === "string" && RUN_ID.test(value.run_id) ? value.run_id : null;
  const raw = Array.isArray(value.codes) ? value.codes : Array.isArray(value.violations) ? value.violations : [];
  const codes = raw.filter((c) => c && REASON_CODES.has(c.code)).slice(0, 16)
    .map((c) => ({ code: c.code, ...(Array.isArray(c.dies) && c.dies.every((d) => Number.isInteger(d) && d >= 0 && d < 8) ? { dies: c.dies } : {}) }));
  return { state, runId, codes };
}

// A form post must come from this site's own confirm page: the browser says so with Sec-Fetch-Site (same-origin, or
// none for a navigation the person made), or, where it sends no Sec-Fetch-Site, with an Origin equal to this site's.
// A cross-site form would make a visitor spend their own allowance submitting someone else's layout.
function sameSiteForm(request, url) {
  const site = request.headers.get("sec-fetch-site");
  if (site !== null) return site === "same-origin" || site === "none";
  return request.headers.get("origin") === url.origin;
}

// The POST reached for the intake but no answer says what happened: the layout may or may not be queued. The
// response keeps the same token, layout and request key, and offers the same idempotent retry (an identical retry
// returns the same run and is charged once). It never says nothing was sent and never asks for a new link: a new
// token is a new principal, and the same layout under it would be a second, separately charged submission.
function deliveryUnknown(request, format, url, { token, compact, requestKey, cause }) {
  const status = cause === "timeout" ? 504 : 502;
  if (format === "html") return html(request, status, notConfirmedHtml({ token, compact, cause }));
  return json(request, status, { error: "delivery_unknown", cause,
    detail: "The layout may or may not have reached the scorer intake. Send the same request again (same token, layout and request_key): an identical retry returns the same run and is charged once.",
    request_key: requestKey,
    retry: { method: "POST", url: `${url.origin}/agents/submit`, content_type: "application/json", body: { t: token, layout: compact, request_key: requestKey } } });
}

async function submit(request, env, ctx, url) {
  const type = (request.headers.get("content-type") ?? "").toLowerCase();
  const form = /^application\/x-www-form-urlencoded(;|$)/.test(type);
  const format = form ? "html" : "json";
  if (!form && !/^application\/json(;|$)/.test(type)) return refuse(request, format, 415, { error: "unsupported_media_type", accepted: ["application/json", "application/x-www-form-urlencoded"] });
  if (form && !sameSiteForm(request, url)) return refuse(request, format, 403, { error: "cross_site" });
  if (!usableKey(env)) return closed(request, format);
  if (!(await allow(env, "DOOR_IP_LIMITER", `submit:${prefixOf(request)}`))) return submitLimited(request, format);
  const body = await readBody(request, form ? MAX_FORM_BYTES : MAX_JSON_BYTES);
  if (!("text" in body)) return rejected(request, format, [body.code]);
  const fields = fieldsOf(body.text, form);
  if (fields.codes) return rejected(request, format, fields.codes);
  const auth = await authorize(request, env, url, [fields.t], "place-chiplets", format);
  if (auth instanceof Response) return auth;
  const parsed = typeof fields.layout === "string" ? parseCompact(fields.layout) : parseDies(fields.layout);
  if (!parsed.ok) return rejected(request, format, parsed.codes);
  // The terms the intake's board names (the signed manifest's). Unreachable: nothing is sent, and the door says so.
  const live = await sharedBoard(env, url);
  if (!live.reachable) return refuse(request, format, 503, { error: "intake_unavailable" });
  const terms = live.terms;
  if (!terms) return rejected(request, format, [{ code: "not_open_yet" }]);
  // Per token, what counts is what would reach the intake: refusals above cost it nothing (the prefix limit bounds them).
  if (!(await allow(env, "DOOR_NONCE_LIMITER", `submit:${auth.claims.nonce}`))) return submitLimited(request, format);
  const requestKey = fields.requestKey ?? `door-${(await sha256Hex(`sentilab-door-request/1|${auth.claims.principal}|${parsed.compact}`)).slice(0, 32)}`;
  const who = await identityFor(request, env);
  const { purpose, case: caseId, nonce, exp } = auth.claims;
  const payload = { token_claims: { purpose, case: caseId, nonce, exp }, layout: parsed.compact, terms, request_key: requestKey,
    class: CLASSES.includes(who?.triage?.class) ? who.triage.class : "unknown", operator: OPERATORS.includes(who?.operator) ? who.operator : "unknown" };
  const answer = await callApi(env, API.submit, { method: "POST", body: payload, host: url.host, timeoutMs: 8000 });
  // Not attempted (no intake configured): nothing was sent.
  if (!answer.attempted) return refuse(request, format, 503, { error: "intake_unavailable" });
  const value = answer.ok && answer.json && typeof answer.json === "object" && !Array.isArray(answer.json) ? answer.json : null;
  // The intake's own answers only: its submit schema below 500 (or its 503 refusal while closed), or its token
  // refusal. Anything else after the POST (no answer, a timeout, a crash, another service) cannot say whether the
  // layout was queued: delivery is unknown, and the same request is the safe retry.
  const own = (value?.schema === SUBMIT_SCHEMA && (answer.status < 500 || (answer.status === 503 && value.state === "rejected")))
    || (answer.status === 403 && /^token_[a-z]+$/.test(value?.error ?? ""));
  if (!own) {
    const cause = !answer.ok ? (answer.reason === "timeout" ? "timeout" : "no_answer") : "unrecognized_answer";
    return deliveryUnknown(request, format, url, { token: auth.token, compact: parsed.compact, requestKey, cause });
  }
  if (form) return html(request, answer.status < 300 ? 200 : answer.status, resultHtml(url.origin, auth.token, outcomeOf(answer)));
  return json(request, answer.status, value);
}

const ROUTES = Object.freeze({
  "/agents/intent": { methods: ["GET", "HEAD"], handler: intent },
  "/agents/engram": { methods: ["GET", "HEAD"], handler: engram },
  "/agents/check": { methods: ["GET", "HEAD"], handler: check },
  "/agents/submit": { methods: ["POST"], handler: submit },
  "/agents/board": { methods: ["GET", "HEAD"], handler: board },
  "/s": { methods: ["GET", "HEAD"], handler: confirm },
});
const STATUS_ROUTE = Object.freeze({ methods: ["GET", "HEAD"], handler: status });

// The door route for a path, or null when the path is not the door's.
export function doorRoute(pathname) {
  if (Object.hasOwn(ROUTES, pathname)) return ROUTES[pathname];
  return pathname.startsWith(STATUS_PREFIX) ? STATUS_ROUTE : null;
}

export async function handleDoor(route, request, env, ctx) {
  if (!route.methods.includes(request.method)) {
    return json(request, 405, { error: "read_only", detail: "The agent door's only write route is POST /agents/submit." }, { allow: route.methods.join(", ") });
  }
  return route.handler(request, env, ctx, new URL(request.url));
}

// The agent version of a mapped page for a classified agent: the wall until it holds a valid token of this site, then
// the page's agent version as before. withEdge passes its identity and execution context.
export async function serveWallOrAgentVersion(request, env, seam = {}) {
  const url = new URL(request.url);
  const key = usableKey(env);
  if (!key || !["GET", "HEAD"].includes(request.method) || agentPathFor(url.pathname) === null) return serveAgentVersion(request, env);
  // Search and link-preview crawlers keep exactly what they got before the door (the vendored gate's own exemption):
  // the wall is noindex, and would drop these pages from search and turn every link preview into the wall.
  if (indexOrPreviewCrawler(request.headers.get("user-agent") ?? "")) return serveAgentVersion(request, env);
  const held = url.searchParams.getAll("t");
  if (held.length === 1 && TOKEN_PATTERN.test(held[0]) && (await verifyToken(key, held[0], { site: url.host, now: Date.now() })).ok) {
    return serveAgentVersion(request, env);
  }
  if (request.method === "GET") emitArrival(request, env, seam.ctx, url, { identity: seam.identity ?? null });
  return wall(request, env, url);
}
