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
// The scorer intake (sentilab-api, API_ORIGIN) is called only from here, with the origin token and fresh headers; the
// token's claims travel in the body (submit) or in x-door-claims (status, board), which the public /api proxy strips
// from visitors' requests. Rate limits: DOOR_NONCE_LIMITER per token and DOOR_IP_LIMITER per client IP prefix on
// submit, DOOR_READ_LIMITER per prefix on the routes that call the intake; each falls back to an in-memory window per
// isolate when its binding is absent. The intake's own quotas (CPU-seconds per token, the global grant, the bounded
// queue) are the hard caps. Arrivals are fire-and-forget and carry only {ts, class, declared_operator, purpose,
// short_id}, from fixed lists; with AQUARIUM_POST=on a purpose choice is also posted to the AIdenID collector.
// A module of its own because worker.js may export nothing but its default handler.
import { AGENT_RESPONSE_CACHE } from "../generated/aidenid-intent-gate/agent-resources.js";
import { agentPathFor } from "../agent-paths.js";
import { preferredAgentType, serveAgentVersion } from "../agent-view.js";
import { CSP } from "../csp.js";
import { identityFor } from "../edge.js";
import { observationFor } from "../vendor/aidenid-registry/agent-registry.mjs";
import { BOARD_METRIC, DIES, PURPOSE_IDS } from "./case.js";
import { agentView, gateZeroFrom } from "./engram.js";
import { parseCompact, parseDies, PREVIEW_LABEL, previewViolations, wireProxyMm } from "./layout.js";
import { confirmHtml, problemHtml, resultHtml, tokenHtml, tokenJson, tokenMarkdown, wallHtml, wallJson, wallMarkdown } from "./render.js";
import { scopeError, sha256Hex, TOKEN_PATTERN, usableKey, verifyToken, mintToken } from "./token.js";

export const LIMITS = Object.freeze({
  DOOR_NONCE_LIMITER: { limit: 10, periodMs: 60000 },
  DOOR_IP_LIMITER: { limit: 60, periodMs: 60000 },
  DOOR_READ_LIMITER: { limit: 300, periodMs: 60000 },
});
export const API = Object.freeze({
  submit: "/api/open/v1/door/submit", status: "/api/open/v1/door/status/", board: "/api/open/v1/door/board",
  arrivals: "/api/open/v1/door/arrivals",
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
export async function callApi(env, path, { method = "GET", body, claims, host, timeoutMs }) {
  const origin = apiOrigin(env);
  if (!origin) return { ok: false, reason: "not_configured" };
  const headers = new Headers({ accept: "application/json" });
  if (env.ORIGIN_TOKEN) headers.set("x-origin-token", env.ORIGIN_TOKEN);
  if (host) headers.set("x-forwarded-host", host);
  if (claims) headers.set("x-door-claims", JSON.stringify(claims));
  if (body !== undefined) headers.set("content-type", "application/json");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(origin + path, { method, headers, redirect: "manual", signal: controller.signal,
      body: body === undefined ? undefined : JSON.stringify(body) });
    const text = await res.text();
    if (text.length > MAX_API_BYTES) return { ok: true, status: res.status, json: null };
    let value = null;
    try { value = JSON.parse(text); } catch { /* not JSON: treated as no answer */ }
    return { ok: true, status: res.status, json: value };
  } catch {
    return { ok: false, reason: controller.signal.aborted ? "timeout" : "unreachable" };
  } finally {
    clearTimeout(timer);
  }
}

const finite = (v, lo, hi) => typeof v === "number" && Number.isFinite(v) && v >= lo && v <= hi;
const BOARD_CLASSES = new Set([...CLASSES, "ours"]);

// What the door reads from the intake's board answer, each part checked alone: admission ("open" only when the intake
// says open is true), at most ten entries holding class, short id, state and numbers only, and a token's CPU left.
export function readBoard(answer) {
  const value = answer?.ok && answer.status === 200 && answer.json && typeof answer.json === "object" ? answer.json : null;
  const open = value?.admission?.open;
  const admission = open === true ? "open" : open === false ? "closed" : "unknown";
  const rows = Array.isArray(value?.board) ? value.board : null;
  const board = rows && rows.slice(0, 100).flatMap((row) => {
    if (!row || typeof row !== "object" || !BOARD_CLASSES.has(row.class) || typeof row.short_id !== "string" || !/^[0-9a-f]{4}$/.test(row.short_id)) return [];
    const entry = { class: row.class, short_id: row.short_id };
    if (STATES.has(row.state)) entry.state = row.state;
    if (finite(row[BOARD_METRIC.metric_id], -273.15, 10000)) entry[BOARD_METRIC.metric_id] = row[BOARD_METRIC.metric_id];
    if (finite(row.wire_proxy_mm, 0, 1000)) entry.wire_proxy_mm = row.wire_proxy_mm;
    return [entry];
  }).slice(0, 10).map((entry, index) => ({ rank: index + 1, ...entry }));
  const left = value?.token?.cpu_s_left;
  return { admission, board, cpuSecondsLeft: finite(left, 0, 100000) ? left : null };
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

// The arrival event: only values from fixed lists, the time, and the first 4 hex of sha256(nonce).
export function arrivalOf(identity, purpose, shortId, now) {
  return { ts: new Date(now).toISOString(), class: CLASSES.includes(identity?.triage?.class) ? identity.triage.class : "unknown",
    declared_operator: OPERATORS.includes(identity?.operator) ? identity.operator : "unknown",
    purpose: PURPOSE_IDS.includes(purpose) ? purpose : null, short_id: /^[0-9a-f]{4}$/.test(shortId ?? "") ? shortId : null };
}

async function postCollector(request, env, identity, event, expiresAt) {
  if (env.AQUARIUM_POST !== "on" || !env.COLLECTOR || !env.INGEST_TOKEN || !identity || !event.purpose) return;
  const observation = observationFor({ triageClass: identity.triage.class, basis: identity.basis,
    userAgent: request.headers.get("user-agent") ?? "", signer: identity.verification?.signer, cfBotCategory: request.cf?.verifiedBotCategory });
  const body = { schemaVersion: 1, siteId: "sentilab", sessionId: crypto.randomUUID(), source: "edge", eventType: "page_view",
    path: "/agents/intent", method: "GET", identity: { ...identity, observation },
    intent: { category: event.purpose, source: "declared_preset", classifierVersion: "intent-gate-v1", declaredAt: event.ts, expiresAt } };
  await bounded((signal) => env.COLLECTOR.fetch(INGEST_URL, { method: "POST", redirect: "manual", signal,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${env.INGEST_TOKEN}` }, body: JSON.stringify(body) }), 1200);
}

// Fire and forget: nothing here can delay or change a response.
function emitArrival(request, env, ctx, url, { identity, purpose = null, shortId = null, expiresAt = null }) {
  if (typeof ctx?.waitUntil !== "function") return;
  try {
    ctx.waitUntil((async () => {
      if (!(await allow(env, "DOOR_READ_LIMITER", `arrival:${prefixOf(request)}`))) return;
      const who = identity === undefined ? await identityFor(request, env) : identity;
      const event = arrivalOf(who, purpose, shortId, Date.now());
      await Promise.allSettled([callApi(env, API.arrivals, { method: "POST", body: event, host: url.host, timeoutMs: 1200 }),
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
  const now = Date.now();
  const token = await mintToken(key, { purpose, site: url.host, now });
  const { claims } = await verifyToken(key, token, { site: url.host, now });
  const { admission } = await sharedBoard(env, url);
  emitArrival(request, env, ctx, url, { purpose, shortId: claims.short_id, expiresAt: claims.expires_at });
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
    reading ? callApi(env, API.board, { claims: auth.claims, host: url.host, timeoutMs: 2500 }).then(readBoard) : { admission: "unknown", board: null, cpuSecondsLeft: null },
    gateZero(request, env, url)]);
  return json(request, 200, agentView({ origin: url.origin, token: auth.token, claims: auth.claims, submissions: live.admission,
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
  const { admission } = await sharedBoard(env, url);
  return html(request, 200, confirmHtml({ claims: auth.claims, token: auth.token, compact: parsed.compact, dies: parsed.dies,
    violations: previewViolations(parsed.dies), wireMm: wireProxyMm(parsed.dies), submissions: admission }));
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
  const answer = await callApi(env, API.status + runId, { claims: auth.claims, host: url.host, timeoutMs: 2500 });
  if (!answer.ok || !answer.json || typeof answer.json !== "object" || answer.status >= 500 || [404, 405].includes(answer.status) && !answer.json.error) {
    return json(request, 503, { error: "intake_unavailable" });
  }
  return json(request, answer.status, answer.json);
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
  try { return { text: new TextDecoder("utf-8", { fatal: true }).decode(bytes) }; } catch { return { status: 400, code: { code: "not_utf8" } }; }
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
  let value;
  try { value = JSON.parse(text); } catch { return { codes: [{ code: "malformed_json" }] }; }
  if (!value || typeof value !== "object" || Array.isArray(value)) return { codes: [fieldError("", "type")] };
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

async function submit(request, env, ctx, url) {
  const type = (request.headers.get("content-type") ?? "").toLowerCase();
  const form = /^application\/x-www-form-urlencoded(;|$)/.test(type);
  const format = form ? "html" : "json";
  if (!form && !/^application\/json(;|$)/.test(type)) return refuse(request, format, 415, { error: "unsupported_media_type", accepted: ["application/json", "application/x-www-form-urlencoded"] });
  if (!usableKey(env)) return closed(request, format);
  if (!(await allow(env, "DOOR_IP_LIMITER", `submit:${prefixOf(request)}`))) return limited(request, format);
  const body = await readBody(request, form ? MAX_FORM_BYTES : MAX_JSON_BYTES);
  if (!("text" in body)) return refuse(request, format, body.status, { error: "refused", codes: [body.code] });
  const fields = fieldsOf(body.text, form);
  if (fields.codes) return refuse(request, format, 400, { error: "refused", codes: fields.codes });
  const auth = await authorize(request, env, url, [fields.t], "place-chiplets", format);
  if (auth instanceof Response) return auth;
  const parsed = typeof fields.layout === "string" ? parseCompact(fields.layout) : parseDies(fields.layout);
  if (!parsed.ok) return refuse(request, format, 400, { error: "refused", codes: parsed.codes });
  // Per token, what counts is what would reach the intake: refusals above cost it nothing (the prefix limit bounds them).
  if (!(await allow(env, "DOOR_NONCE_LIMITER", `submit:${auth.claims.nonce}`))) return limited(request, format);
  const requestKey = fields.requestKey ?? `door-${(await sha256Hex(`sentilab-door-request/1|${auth.claims.principal}|${parsed.compact}`)).slice(0, 32)}`;
  const payload = { schema: "sentilab-door-submit/1", token_claims: auth.claims, request_key: requestKey,
    layout: { compact: parsed.compact, dies: parsed.dies }, via: form ? "tap_link" : "post" };
  const answer = await callApi(env, API.submit, { method: "POST", body: payload, host: url.host, timeoutMs: 8000 });
  if (!answer.ok && answer.reason === "timeout") return refuse(request, format, 504, { error: "intake_timeout", request_key: requestKey });
  if (!answer.ok || !answer.json || typeof answer.json !== "object" || Array.isArray(answer.json) || answer.status >= 500 || [404, 405].includes(answer.status) && !answer.json.state) {
    return refuse(request, format, 503, { error: "intake_unavailable" });
  }
  if (form) return html(request, answer.status < 300 ? 200 : answer.status, resultHtml(url.origin, auth.token, outcomeOf(answer)));
  return json(request, answer.status, answer.json);
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
  const held = url.searchParams.getAll("t");
  if (held.length === 1 && TOKEN_PATTERN.test(held[0]) && (await verifyToken(key, held[0], { site: url.host, now: Date.now() })).ok) {
    return serveAgentVersion(request, env);
  }
  if (request.method === "GET") emitArrival(request, env, seam.ctx, url, { identity: seam.identity ?? null });
  return wall(request, env, url);
}
