// thermal.aidenid.com: static assets from ./public, and /api/* proxied to the thermal-api Azure Container App
// (API_ORIGIN). The upstream body streams through, so server-sent events work unchanged.
const HOP = ["connection", "keep-alive", "transfer-encoding", "upgrade", "host"];

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
    if (request.method === "POST" && pathname === "/api/runs" && !(await allowRunStart(request, env))) {
      return new Response(JSON.stringify({ error: "rate_limited", detail: "Too many runs started; wait a minute." }),
        { status: 429, headers: { "content-type": "application/json", "retry-after": "60", "cache-control": "no-store" } });
    }
    if (pathname === "/api" || pathname.startsWith("/api/")) return proxy(request, env);
    return env.ASSETS.fetch(request);
  },
};
