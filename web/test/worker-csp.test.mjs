// node --test web/test/worker-csp.test.mjs
// The sentilab-web Worker (web/src/worker.js) adds one exact Content-Security-Policy to every static asset response,
// so only our own scripts run on the verifier pages (a script injected into the HTML on its way out, inline code,
// eval and other origins are refused by the browser), and passes /api/* through byte for byte, headers untouched.
// The config is checked too: without assets.run_worker_first: true the asset layer answers first and the Worker,
// with its header, never runs for a page.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import * as workerModule from "../src/worker.js";
import { CSP } from "../src/csp.js";

const worker = workerModule.default;

const here = dirname(fileURLToPath(import.meta.url));
// The policy, written out here on purpose: the test pins the exact header value, not whatever the module exports.
const EXACT = "default-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'";
const ORIGIN = "https://sentilab-api.example.test";

// A stand-in asset binding: the bytes and headers the asset layer would answer with, and a log of what it was asked.
function assets(files) {
  const asked = [];
  return {
    asked,
    fetch: async (request) => {
      const path = new URL(request.url).pathname;
      asked.push(path);
      const file = files[path];
      if (!file) return new Response("not found", { status: 404, headers: { "content-type": "text/plain" } });
      if (request.headers.get("if-none-match") === file.etag) return new Response(null, { status: 304, headers: { etag: file.etag } });
      return new Response(file.body, { status: 200, headers: { "content-type": file.type, etag: file.etag, "cache-control": "public, max-age=0, must-revalidate" } });
    },
  };
}
const FILES = {
  "/sentilab/": { body: readFileSync(join(here, "..", "public", "sentilab", "index.html")), type: "text/html", etag: '"lab"' },
  "/sentilab/package/": { body: readFileSync(join(here, "..", "public", "sentilab", "package", "index.html")), type: "text/html", etag: '"pkg"' },
  "/sentilab/lab.js": { body: readFileSync(join(here, "..", "public", "sentilab", "lab.js")), type: "text/javascript", etag: '"labjs"' },
  "/": { body: readFileSync(join(here, "..", "public", "index.html")), type: "text/html", etag: '"run"' },
};
const bytes = async (res) => new Uint8Array(await res.arrayBuffer());
const headerList = (res) => [...res.headers.entries()].sort();
// The three pages with an agent version also carry the negotiation headers: they vary on Accept and the edge class
// header, stay out of shared caches and name their agent version (worker-agents.test.mjs covers the negotiation).
const negotiated = (alternate) => ({ vary: "Accept, x-aidenid-class", "cache-control": "private, no-cache", link: `<${alternate}>; rel="alternate"; type="text/markdown"` });
const ADDED = { "/sentilab/": negotiated("/agents/"), "/sentilab/package/": negotiated("/agents/physics.md"), "/sentilab/lab.js": {}, "/": negotiated("/agents/") };

test("the exported policy is exactly the reviewed one", () => {
  assert.equal(CSP, EXACT);
});
test("worker.js exports only its default handler (the Workers runtime refuses any other named export)", () => {
  assert.deepEqual(Object.keys(workerModule), ["default"]);
  assert.equal(typeof worker.fetch, "function");
  const source = readFileSync(join(here, "..", "src", "worker.js"), "utf8");
  assert.deepEqual(source.match(/^[ \t]*export\b.*$/gm), ["export default {"], "the only export statement");
});

for (const path of ["/sentilab/", "/sentilab/package/", "/sentilab/lab.js", "/"]) {
  test(`asset ${path}: the exact CSP is added; status, body bytes and every other header are the asset layer's (pages add their negotiation headers)`, async () => {
    const env = { ASSETS: assets(FILES), API_ORIGIN: ORIGIN };
    const direct = await env.ASSETS.fetch(new Request(`https://sentilab.aidenid.com${path}`));
    const res = await worker.fetch(new Request(`https://sentilab.aidenid.com${path}`), env);
    assert.equal(res.status, 200);
    assert.equal(res.headers.get("content-security-policy"), EXACT);
    assert.deepEqual(await bytes(res), new Uint8Array(FILES[path].body), "the body is untouched");
    const others = headerList(res).filter(([k]) => k !== "content-security-policy");
    const expected = Object.entries({ ...Object.fromEntries(headerList(direct)), ...ADDED[path] }).sort();
    assert.deepEqual(others, expected, "every other header is the asset layer's, plus a page's negotiation headers");
  });
}
test("asset responses that aren't 200 keep their status and still carry the CSP (304, 404)", async () => {
  const env = { ASSETS: assets(FILES), API_ORIGIN: ORIGIN };
  const notModified = await worker.fetch(new Request("https://sentilab.aidenid.com/sentilab/", { headers: { "if-none-match": '"lab"' } }), env);
  assert.equal(notModified.status, 304);
  assert.equal(notModified.headers.get("content-security-policy"), EXACT);
  const missing = await worker.fetch(new Request("https://sentilab.aidenid.com/sentilab/nope.js"), env);
  assert.equal(missing.status, 404);
  assert.equal(missing.headers.get("content-security-policy"), EXACT);
});

// The /api/* passthrough, against what the proxy produced before this change: the upstream status and body bytes,
// the upstream headers, and cache-control: no-store only when upstream sent none. No CSP is added, and an upstream
// CSP (if the API ever sends one) is passed through unchanged.
async function viaWorker(upstream, path = "/api/view/runs") {
  const calls = [];
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (url, init) => { calls.push({ url: String(url), method: init?.method }); return upstream(); };
  try {
    const env = { ASSETS: assets(FILES), API_ORIGIN: ORIGIN };
    const res = await worker.fetch(new Request(`https://sentilab.aidenid.com${path}`), env);
    return { res, calls, assetsAsked: env.ASSETS.asked };
  } finally {
    globalThis.fetch = realFetch;
  }
}
test("/api/view/runs passthrough is unaffected: same status, body bytes and headers; no CSP added; the asset layer is never asked", async () => {
  const body = new TextEncoder().encode(JSON.stringify({ runs: [{ run_id: "35975774fb714bbdaa51972bc39518ec", status: "finished", last_seq: 272 }] }));
  const upstreamHeaders = { "content-type": "application/json", "x-request-id": "r-1", etag: '"runs"' };
  const { res, calls, assetsAsked } = await viaWorker(() => new Response(body, { status: 200, headers: upstreamHeaders }));
  assert.deepEqual(calls, [{ url: `${ORIGIN}/api/view/runs`, method: "GET" }]);
  assert.deepEqual(assetsAsked, []);
  assert.equal(res.status, 200);
  assert.deepEqual(await bytes(res), body);
  assert.equal(res.headers.get("content-security-policy"), null, "no CSP on API responses");
  assert.deepEqual(headerList(res), Object.entries({ ...upstreamHeaders, "cache-control": "no-store" }).sort(), "the upstream headers, plus no-store as before");
});
test("/api passthrough keeps an upstream cache-control and an upstream CSP exactly, and non-200 statuses", async () => {
  const upstreamHeaders = { "content-type": "application/x-ndjson", "cache-control": "max-age=5", "content-security-policy": "default-src 'none'", "x-next-cursor": "256" };
  const { res } = await viaWorker(() => new Response("{}\n", { status: 200, headers: upstreamHeaders }), "/api/view/events?run_id=x&cursor=0&limit=256");
  assert.deepEqual(headerList(res), Object.entries(upstreamHeaders).sort());
  const { res: gone } = await viaWorker(() => new Response('{"detail":"run not found"}', { status: 404, headers: { "content-type": "application/json" } }));
  assert.equal(gone.status, 404);
  assert.equal(gone.headers.get("content-security-policy"), null);
  assert.equal(await gone.text(), '{"detail":"run not found"}');
});
test("the read-only refusal for API writes is unchanged (405, no CSP)", async () => {
  const env = { ASSETS: assets(FILES), API_ORIGIN: ORIGIN };
  const res = await worker.fetch(new Request("https://sentilab.aidenid.com/api/runs", { method: "POST", body: "{}" }), env);
  assert.equal(res.status, 405);
  assert.equal(res.headers.get("content-security-policy"), null);
  assert.deepEqual(env.ASSETS.asked, []);
});

test("wrangler.jsonc sends every request through the Worker (run_worker_first: true), so the CSP reaches the pages", () => {
  const text = readFileSync(join(here, "..", "wrangler.jsonc"), "utf8");
  const config = JSON.parse(text.split("\n").map((line) => line.replace(/^\s*\/\/.*$/, "")).join("\n"));
  assert.equal(config.main, "src/worker.js");
  assert.equal(config.assets.run_worker_first, true);
});
