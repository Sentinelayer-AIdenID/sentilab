// sentilab.aidenid.com: static assets from ./public, and read-only /api/* proxied to the sentilab-api Azure Container App
// (API_ORIGIN). The upstream body streams through, so server-sent events work unchanged.
// This module's only export is the default handler: the Workers runtime treats every named export of the main module
// as an entry point and refuses to start on anything else (web/test/worker-boot.mjs boots it in CI).
import { CSP } from "./csp.js";
import { CONTENT_TYPES, NEGOTIATED_CACHE_CONTROL, VARY, agentView, alternateLink, varyWith } from "./agent-view.js";

const HOP = ["connection", "keep-alive", "transfer-encoding", "upgrade", "host"];

// Every static asset response (the pages, their scripts and styles, the data files) carries the CSP (csp.js), so only
// our own scripts run on the verifier pages. /api/* responses are passed through untouched. wrangler.jsonc sends every
// request through this Worker (assets.run_worker_first: true); without that the asset layer would answer first and
// this header would never be set.
// The three human pages with an agent version are negotiated (agent-view.js): the agent version is another file under
// public/ (markdown or JSON, its type set here), and both versions vary on Accept and the edge class header and stay out
// of shared caches. The human version names its agent version in a Link header. Every other path is unchanged.

async function asset(request, env) {
  const view = agentView(request, env);
  const target = view && view.serve
    ? new Request(new URL(view.serve, request.url), { method: request.method, headers: request.headers })
    : request;
  const res = await env.ASSETS.fetch(target);
  const headers = new Headers(res.headers);
  headers.set("content-security-policy", CSP);
  if (view && view.serve && res.status === 200) headers.set("content-type", CONTENT_TYPES[view.kind]);
  if (view && view.negotiated) {
    headers.set("vary", varyWith(headers.get("vary"), VARY));
    headers.set("cache-control", NEGOTIATED_CACHE_CONTROL);
    if (!view.serve) headers.set("link", alternateLink(view.alternate));
  }
  return new Response(res.body, { status: res.status, statusText: res.statusText, headers });
}

async function proxy(request, env) {
  const origin = String(env.API_ORIGIN || "").replace(/\/+$/, "");
  if (!origin.startsWith("https://")) return new Response("API origin not configured", { status: 503 });
  const url = new URL(request.url);
  const headers = new Headers(request.headers);
  for (const h of HOP) headers.delete(h);
  headers.set("x-forwarded-host", url.host);
  // Only this Worker holds the origin token; the Container App refuses requests without it.
  if (env.ORIGIN_TOKEN) headers.set("x-origin-token", env.ORIGIN_TOKEN);
  else headers.delete("x-origin-token");
  const init = { method: request.method, headers, redirect: "manual" };
  if (!["GET", "HEAD"].includes(request.method)) init.body = request.body;
  const upstream = await fetch(origin + url.pathname + url.search, init);
  const out = new Headers(upstream.headers);
  if (!out.has("cache-control")) out.set("cache-control", "no-store");
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

// Starting a run spends simulator time, so POST /api/runs is limited per client IP at the edge (the API also
// allows one run at a time). Without the binding (local dev), requests pass through.
async function allowRunStart(request, env) {
  if (!env.RUNS_LIMITER) return true;
  const ip = request.headers.get("cf-connecting-ip") || "unknown";
  const { success } = await env.RUNS_LIMITER.limit({ key: ip });
  return success;
}

export default {
  async fetch(request, env) {
    const { pathname } = new URL(request.url);
    // SentiLab is hands-off: the service runs its own loop, so the public edge is read-only. No caller can start
    // runs or reach any write route from outside.
    if ((pathname === "/api" || pathname.startsWith("/api/")) && !["GET", "HEAD"].includes(request.method)) {
      return new Response(JSON.stringify({ error: "read_only", detail: "The public SentiLab API is read-only." }),
        { status: 405, headers: { "content-type": "application/json", allow: "GET, HEAD", "cache-control": "no-store" } });
    }
    if (request.method === "POST" && pathname === "/api/runs" && !(await allowRunStart(request, env))) {
      return new Response(JSON.stringify({ error: "rate_limited", detail: "Too many runs started; wait a minute." }),
        { status: 429, headers: { "content-type": "application/json", "retry-after": "60", "cache-control": "no-store" } });
    }
    if (pathname === "/api" || pathname.startsWith("/api/")) return proxy(request, env);
    return asset(request, env);
  },
};
