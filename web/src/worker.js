// sentilab.aidenid.com: static assets from ./public, and read-only /api/* proxied to the sentilab-api Azure Container App
// (API_ORIGIN). The upstream body streams through, so server-sent events work unchanged.
// This module's only export is the default handler: the Workers runtime treats every named export of the main module
// as an entry point and refuses to start on anything else (web/test/worker-boot.mjs boots it in CI).
import { withEdge } from "./edge.js";
import { agentPathFor } from "./agent-paths.js";
import { CSP } from "./csp.js";
import { addHumanPageHeaders, serveAgentAsset } from "./agent-view.js";
import { carriesToken, decodedPath, DOOR_FEEDS, doorRoute, handleDoor, handleHere, HERE_PATH, protectToken, serveWallOrAgentVersion, tokenBearing,
  withoutOperators } from "./door/door.js";

const HOP = ["connection", "keep-alive", "transfer-encoding", "upgrade", "host"];

// Every static asset response (the pages, their scripts and styles, the data files) carries the CSP (csp.js), so only
// our own scripts run on the verifier pages. /api/* responses are passed through untouched. wrangler.jsonc sends every
// request through this Worker (assets.run_worker_first: true); without that the asset layer would answer first and
// this header would never be set.
// The three pages with an agent version are negotiated on Accept (agent-view.js); /agents/ serves /agents/index.md.
// The human version of / is the Live Lab, and the replay page / served before it is at /lab (humanVersion).

async function asset(request, env) {
  const agent = await serveAgentAsset(request, env);
  if (agent) return agent;
  return humanAsset(request, env);
}

async function humanAsset(request, env) {
  const res = await humanVersion(request, env);
  const headers = new Headers(res.headers);
  headers.set("content-security-policy", CSP);
  addHumanPageHeaders(request, headers);
  return new Response(res.body, { status: res.status, statusText: res.statusText, headers });
}

// The human version of a request: the asset layer's answer, except at / and /lab. A GET or HEAD that gets the human
// version of / (a person's browser, an unclassified client whose Accept prefers HTML, ?view=human and its cookie, and
// every fallback to the human page) is a same-origin 302 to the Live Lab (web/public/sentilab/live/, a plain asset
// directory, so the redirect ends there), and humanAsset and withEdge give it the human page's headers as before: the
// CSP, Vary, private, no-store, the Link to the agent version and the ?view=human cookie. The wall and the agent
// versions never come here, and any other method at / reaches the asset layer as before. /lab is the earlier replay
// page that / served (web/public/index.html), asked of the asset layer as / with this request's method and headers
// (never as /index.html, which the asset layer answers with a 307 to /). It has no agent version, so every client gets
// it as it is, like any other page without one.
// An old run link (/?run=<id>, in posts and earlier decks) keeps opening the run it names: the earlier replay at /lab,
// with the full query, under the same 302. A URL that carries a door token never forwards its query.
const LIVE_LAB = "/sentilab/live/";
async function humanVersion(request, env) {
  const url = new URL(request.url);
  if (url.pathname === "/" && ["GET", "HEAD"].includes(request.method)) {
    const location = url.searchParams.has("run") && !carriesToken(url) ? `/lab${url.search}` : LIVE_LAB;
    return new Response(null, { status: 302, headers: { location } });
  }
  if (url.pathname !== "/lab") return env.ASSETS.fetch(request);
  url.pathname = "/";
  return env.ASSETS.fetch(new Request(url, request));
}

async function proxy(request, env) {
  const origin = String(env.API_ORIGIN || "").replace(/\/+$/, "");
  if (!origin.startsWith("https://")) return new Response("API origin not configured", { status: 503 });
  const url = new URL(request.url);
  // The API routes a path after percent-decoding it, so the open-feed filter below matches the decoded path (every
  // spelling of /api/open/v1/door/board is the board), and a path whose escapes do not decode goes no further.
  const path = decodedPath(url.pathname);
  if (path === null) {
    return new Response(JSON.stringify({ error: "bad_path" }), { status: 400, headers: { "content-type": "application/json", "cache-control": "no-store" } });
  }
  const headers = new Headers(request.headers);
  for (const h of HOP) headers.delete(h);
  // The agent door's token claims reach the API only from the door's own calls (door/door.js), never from a visitor.
  for (const name of [...headers.keys()]) if (name.startsWith("x-door-")) headers.delete(name);
  // A page at a token-bearing URL must not hand its token upstream in a Referer.
  if (tokenBearing(headers.get("referer"))) headers.delete("referer");
  headers.set("x-forwarded-host", url.host);
  // Only this Worker holds the origin token; the Container App refuses requests without it.
  if (env.ORIGIN_TOKEN) headers.set("x-origin-token", env.ORIGIN_TOKEN);
  else headers.delete("x-origin-token");
  const init = { method: request.method, headers, redirect: "manual" };
  if (!["GET", "HEAD"].includes(request.method)) init.body = request.body;
  const upstream = await fetch(origin + url.pathname + url.search, init);
  const out = new Headers(upstream.headers);
  if (!out.has("cache-control")) out.set("cache-control", "no-store");
  if (request.method === "GET" && DOOR_FEEDS.test(path)) return doorFeed(upstream, out);
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

// The intake's open feeds (board, results, events) name each visitor's declared operator. The door never shows it, so
// neither does the proxy: the answer is passed on without any "operator" field. A feed answer that is not JSON is not
// passed on at all.
async function doorFeed(upstream, headers) {
  let value;
  try { value = JSON.parse(await upstream.text()); } catch {
    return new Response(JSON.stringify({ error: "unreadable_feed" }), { status: 502, headers: { "content-type": "application/json", "cache-control": "no-store" } });
  }
  for (const name of ["content-length", "content-encoding", "etag"]) headers.delete(name);
  headers.set("content-type", "application/json");
  // The visitors feed carries visitors' own declared text: never sniffed as anything but JSON.
  headers.set("x-content-type-options", "nosniff");
  return new Response(JSON.stringify(withoutOperators(value)), { status: upstream.status, headers });
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
  async fetch(request, env, ctx) {
    const { pathname } = new URL(request.url);
    // A lab page's heartbeat (door/door.js handleHere): this exact path only, checked and forwarded by the door with
    // fresh headers. Any other spelling of it is the read-only API below.
    if (pathname === HERE_PATH) return handleHere(request, env);
    // SentiLab is hands-off: the service runs its own loop, so the public /api is read-only. No caller can start runs
    // or reach any API write route from outside. The edge's write routes are the agent door's POST /agents/submit and
    // POST /agents/declare (only while DOOR_DECLARATIONS is "on"), which reach the API only after the door's token,
    // format and rate checks, and the heartbeat above (door/door.js).
    if ((pathname === "/api" || pathname.startsWith("/api/")) && !["GET", "HEAD"].includes(request.method)) {
      return new Response(JSON.stringify({ error: "read_only", detail: "The public SentiLab API is read-only." }),
        { status: 405, headers: { "content-type": "application/json", allow: "GET, HEAD", "cache-control": "no-store" } });
    }
    if (request.method === "POST" && pathname === "/api/runs" && !(await allowRunStart(request, env))) {
      return new Response(JSON.stringify({ error: "rate_limited", detail: "Too many runs started; wait a minute." }),
        { status: 429, headers: { "content-type": "application/json", "retry-after": "60", "cache-control": "no-store" } });
    }
    if (pathname === "/api" || pathname.startsWith("/api/")) return proxy(request, env);
    // The agent door (door/door.js): its own routes, and the wall in place of the mapped pages' agent version.
    const door = doorRoute(pathname, env);
    const response = door ? await handleDoor(door, request, env, ctx)
      : await withEdge(request, env, ctx, { agentPathFor, serve: asset, serveHuman: humanAsset, serveAgent: serveWallOrAgentVersion });
    // Whatever page answers a URL that can carry a token (mapped, human override, fallback, any asset) never hands it on.
    return carriesToken(new URL(request.url)) ? protectToken(response) : response;
  },
};
