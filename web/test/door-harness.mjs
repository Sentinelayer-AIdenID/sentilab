// Shared fixtures for the agent door's route tests (door-routes.test.mjs, door-submit.test.mjs): the real Worker over
// the real files in web/public, a stand-in scorer intake on a mocked global fetch that records every call, answering in
// Lane 2's shapes (sentilab PR #81 at c5130696), and the request shapes of agents and of a desktop browser.
import { readFileSync } from "node:fs";
import { dirname, extname, join } from "node:path";
import { fileURLToPath } from "node:url";

import worker from "../src/worker.js";
import { resetDoorState } from "../src/door/door.js";
import { mintToken } from "../src/door/token.js";

export const PUBLIC = join(dirname(fileURLToPath(import.meta.url)), "..", "public");
// A test-only key, built at run time so no literal in this tree looks like a credential.
export const KEY = "route test key ".repeat(3);
export const BASE = "https://sentilab.aidenid.com";
export const STAGING = "https://staging.sentilab.aidenid.com";
export const API_ORIGIN = "https://sentilab-api.example.test";
export const REF = "36.35.0,54.35.0,54.55.0,36.55.0,17.35.0,73.35.0,73.55.0,17.55.0";
export const OVERLAP = "36.35.0,53.35.0,54.55.0,36.55.0,17.35.0,73.35.0,73.55.0,17.55.0";
export const RUN = "open-12345678-0123456789abcdef0123456789abcdef";
// A terms version of the contract's shape, built at run time (one of a signed manifest's accepted versions).
export const TERMS = `sentilab-open-terms/1@${"0f".repeat(32)}`;
export const UA = Object.freeze({
  gptbot: "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.2; +https://openai.com/gptbot)",
  chatgptUser: "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ChatGPT-User/1.0; +https://openai.com/bot",
  claudebot: "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ClaudeBot/1.0; +claudebot@anthropic.com)",
  curl: "curl/8.4.0",
  requests: "python-requests/2.31.0",
});
// The upstream classifier's complete Chromium navigation fixture (as in edge.test.mjs).
export const BROWSER = Object.freeze({
  "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
  "sec-fetch-mode": "navigate", "sec-fetch-dest": "document", "sec-fetch-site": "none",
  accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "accept-language": "en-US,en;q=0.9",
  "sec-ch-ua": '"Chromium";v="130", "Not A(Brand";v="99"', "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"Windows"',
});

const TYPES = { ".html": "text/html; charset=utf-8", ".md": "text/markdown", ".json": "application/json", ".css": "text/css", ".txt": "text/plain" };
export const file = (rel) => readFileSync(join(PUBLIC, ...rel.split("/").filter(Boolean)));
function assets() {
  return { async fetch(request) {
    const path = new URL(request.url).pathname;
    const rel = path.endsWith("/") ? `${path}index.html` : path;
    let body;
    try { body = file(rel); } catch { return new Response("not found", { status: 404, headers: { "content-type": "text/plain" } }); }
    return new Response(request.method === "HEAD" ? null : body, { status: 200, headers: { "content-type": TYPES[extname(rel)] ?? "application/octet-stream" } });
  } };
}

// GET /board in Lane 2's shape, abridged: door.open, and top rows carrying more than the door may show agents.
export const BOARD = Object.freeze({ schema: "sentilab-door-board/1", label: "simulated, not silicon", door: { open: true, codes: [] }, top: [
  { id: RUN, label: "declared_agent · ab12", class: "declared_agent", operator: "openai", short_id: "ab12", status: "evaluated",
    max_chiplet_centre_cell_mean_C: 101.25, native_all_block_max_C: 101.2, active_layer_peak_C: 104.5, wire_proxy_mm: 9.75, verdict: null },
  { id: "open-12345678-ffffffffffffffffffffffffffffffff", label: "ours · 0f0f", class: "ours", operator: "unknown", short_id: "0f0f",
    status: "reproduced", max_chiplet_centre_cell_mean_C: 99.5, wire_proxy_mm: 10.25, verdict: "candidate" },
], token: { cpu_s_remaining: 28.9 }, terms: { accepted_versions: [TERMS] } });

// The stand-in intake: route -> async (call) => Response. Records { method, path, headers, body } per call.
export function installApi(t, routes = {}) {
  const calls = [];
  const handlers = {
    board: async () => Response.json(BOARD),
    submit: async () => Response.json({ schema: "sentilab-door-submit/1", state: "queued", run_id: RUN, position: 1, duplicate: false,
      label: "automation · ab12", short_id: "ab12" }, { status: 202 }),
    arrival: async () => new Response(null, { status: 204 }),
    status: async () => Response.json({ schema: "sentilab-door-status/1", id: RUN, label: "automation · ab12", class: "automation",
      operator: "openai", short_id: "ab12", status: "queued" }),
    ...routes,
  };
  t.mock.method(globalThis, "fetch", async (input, init = {}) => {
    const url = new URL(String(input));
    const headers = Object.fromEntries(new Headers(init.headers ?? {}));
    const body = typeof init.body === "string" ? JSON.parse(init.body) : init.body ?? null;
    const call = { method: init.method ?? "GET", origin: url.origin, path: url.pathname + url.search, headers, body, signal: init.signal, redirect: init.redirect };
    calls.push(call);
    const name = url.pathname === "/api/open/v1/door/board" ? "board" : url.pathname === "/api/open/v1/door/submit" ? "submit"
      : url.pathname === "/api/open/v1/door/arrival" ? "arrival" : url.pathname.startsWith("/api/open/v1/door/status/") ? "status" : null;
    if (!name) return new Response("not found", { status: 404 });
    return handlers[name](call);
  });
  return calls;
}

// A fresh Worker environment and execution context; extra overrides env (undefined values delete keys).
export function setup(extra = {}) {
  resetDoorState();
  const pending = [];
  const env = { ASSETS: assets(), API_ORIGIN, ORIGIN_TOKEN: "origin-test-token", DOOR_TOKEN_KEY: KEY, AQUARIUM_POST: "off" };
  for (const [k, v] of Object.entries(extra)) { if (v === undefined) delete env[k]; else env[k] = v; }
  const ctx = { waitUntil: (promise) => pending.push(promise) };
  const go = async (path, init = {}, base = BASE) => {
    const res = await worker.fetch(new Request(base + path, init), env, ctx);
    const bytes = new Uint8Array(await res.arrayBuffer());
    return { res, status: res.status, headers: res.headers, bytes, text: new TextDecoder().decode(bytes) };
  };
  return { env, ctx, pending, go, drain: () => Promise.allSettled(pending) };
}

export const mint = (purpose = "place-chiplets", { site = "sentilab.aidenid.com", now = Date.now(), nonce } = {}) =>
  mintToken(KEY, { purpose, site, now, ...(nonce ? { nonce } : {}) });
export const agent = (ua = UA.gptbot, extra = {}) => ({ headers: { "user-agent": ua, ...extra } });
export const postJson = (value, extra = {}) => ({ method: "POST", headers: { "content-type": "application/json", "user-agent": UA.curl, ...extra },
  body: typeof value === "string" ? value : JSON.stringify(value) });
export const postForm = (text, extra = {}) => ({ method: "POST", headers: { "content-type": "application/x-www-form-urlencoded", ...BROWSER, ...extra }, body: text });
export const same = (a, b) => a.length === b.length && a.every((x, i) => x === b[i]);
// Vendor, product, model and internal names that never appear in what agents read (as web/test/public-names.test.mjs).
export const NAMES = ["typesafe", "jev", "system\\s*one", "cloudflare", "openai", "chatgpt", "gpt", "claude", "anthropic", "grok", "kimi",
  "gemini", "deepseek", "qwen", "llama", "mistral", "microduck", "pollen", "warden", "astra", "forge", "pocket-forge", "aneta", "codex",
  "nightshift", "fable"].map((n) => new RegExp(`(?<![\\w-])${n}(?![\\w])`, "i"));
