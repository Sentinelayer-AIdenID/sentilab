// The agent version of three human pages: /, /sentilab/ and /sentilab/package/. A module of its own because worker.js
// may export nothing but its default handler (see csp.js); worker.js imports it, and so can any other part of the
// Worker. The node tests drive it directly and through the Worker (web/test/worker-agents.test.mjs).
//
// The seam, for any caller that decides a request should get the agent version:
//   agentPathFor(pathname)          the file a page's agent version serves, or null: the page has none, serve it as is.
//   serveAgentVersion(request, env) the agent version of the request's page, typed and with its Vary header (null when
//                                   the page has none, or the method is not GET or HEAD).
// This module decides nothing about who is asking. On its own it applies plain content negotiation: an Accept header
// that gives markdown or JSON a higher q-value than HTML gets the agent version; a browser's Accept, */*, a tie and no
// Accept all keep the human page. Both versions of these pages vary on Accept and stay out of shared caches, and the
// human version names its agent version in a Link header. /agents and /agents/ serve /agents/index.md to everyone.
import { CSP } from "./csp.js";

// Each page with an agent version: the files that version serves (paths under web/public), markdown first, and the URL
// the human page names as its alternate.
export const AGENT_PAGES = Object.freeze({
  "/": Object.freeze({ md: "/agents/index.md", json: "/agents/index.json", alternate: "/agents/" }),
  "/sentilab/": Object.freeze({ md: "/agents/index.md", json: "/agents/index.json", alternate: "/agents/" }),
  "/sentilab/package/": Object.freeze({ md: "/agents/physics.md", alternate: "/agents/physics.md" }),
});
// The agent site's own index, the same for every client.
export const AGENT_INDEX = Object.freeze({ "/agents": "/agents/index.md", "/agents/": "/agents/index.md" });

export const CONTENT_TYPES = Object.freeze({ md: "text/markdown; charset=utf-8", json: "application/json; charset=utf-8" });
const MEDIA = Object.freeze({ md: "text/markdown", json: "application/json", html: "text/html" });
export const VARY = Object.freeze(["Accept"]);
export const NEGOTIATED_CACHE_CONTROL = "private, no-cache";
const QVALUE = /^(0([.][0-9]{0,3})?|1([.]0{0,3})?)$/;
const readOnly = (request) => request.method === "GET" || request.method === "HEAD";
const pageOf = (pathname) => (Object.hasOwn(AGENT_PAGES, pathname) ? AGENT_PAGES[pathname] : null);

// The seam: the file the agent version of a requested page serves, or null when the page has no agent version (serve
// it unchanged). "/" and "/sentilab/" map to /agents/index.md, "/sentilab/package/" to /agents/physics.md.
export function agentPathFor(pathname) {
  const page = pageOf(pathname);
  return page ? page.md : null;
}

// The q-value an Accept header gives one media type: that of the most specific range that matches it (type/subtype,
// then type/*, then */*), or 0 when none does or the header is missing. A malformed q counts as 0; other parameters
// are ignored.
export function acceptQuality(accept, media) {
  const [type, subtype] = media.split("/");
  let rank = -1;
  let quality = 0;
  for (const part of String(accept ?? "").split(",")) {
    const [range, ...params] = part.split(";").map((s) => s.trim().toLowerCase());
    const [t, s] = range.split("/");
    const r = t === type && s === subtype ? 2 : t === type && s === "*" ? 1 : t === "*" && s === "*" ? 0 : -1;
    if (r < 0 || r < rank) continue;
    let q = 1;
    for (const param of params) {
      const at = param.indexOf("=");
      if (at > 0 && param.slice(0, at).trim() === "q") {
        const value = param.slice(at + 1).trim();
        q = QVALUE.test(value) ? Number(value) : 0;
      }
    }
    quality = r > rank ? q : Math.max(quality, q);
    rank = r;
  }
  return quality;
}

// The agent representation the Accept header prefers to HTML, among those the page has: "md", "json" or null.
// Markdown wins a tie with JSON; a tie with HTML keeps the human page.
export function preferredAgentType(accept, page) {
  let best = null;
  let bestQuality = acceptQuality(accept, MEDIA.html);
  for (const kind of ["md", "json"]) {
    if (!page[kind]) continue;
    const quality = acceptQuality(accept, MEDIA[kind]);
    if (quality > bestQuality) {
      best = kind;
      bestQuality = quality;
    }
  }
  return best;
}

// Whether plain content negotiation picks the agent version for this request: a GET or HEAD for a page that has one,
// with an Accept header that prefers markdown or JSON to HTML.
export function prefersAgentVersion(request) {
  const page = readOnly(request) ? pageOf(new URL(request.url).pathname) : null;
  return page !== null && preferredAgentType(request.headers.get("accept"), page) !== null;
}

// A Vary value that keeps every name already there and adds the given ones once each (compared without case).
export function varyWith(current, names) {
  const have = String(current ?? "").split(",").map((s) => s.trim()).filter(Boolean);
  if (have.includes("*")) return "*";
  const lower = new Set(have.map((s) => s.toLowerCase()));
  for (const name of names) if (!lower.has(name.toLowerCase())) { have.push(name); lower.add(name.toLowerCase()); }
  return have.join(", ");
}

// The Link header a human page sends, naming its agent version.
export const alternateLink = (href) => `<${href}>; rel="alternate"; type="text/markdown"`;

// The headers a negotiated page's human version adds: Vary, no shared caching, and the Link to its agent version.
export function addHumanPageHeaders(headers, pathname) {
  const page = pageOf(pathname);
  if (!page) return headers;
  headers.set("vary", varyWith(headers.get("vary"), VARY));
  headers.set("cache-control", NEGOTIATED_CACHE_CONTROL);
  headers.set("link", alternateLink(page.alternate));
  return headers;
}

// The asset at path, served for this request (same method and headers, so conditional requests reach that file), with
// the CSP and its type ("md" or "json"). A negotiated response also varies on Accept and stays out of shared caches.
export async function serveAs(request, env, path, kind, { negotiated = false } = {}) {
  const res = await env.ASSETS.fetch(new Request(new URL(path, request.url), { method: request.method, headers: request.headers }));
  const headers = new Headers(res.headers);
  headers.set("content-security-policy", CSP);
  if (res.status === 200) headers.set("content-type", CONTENT_TYPES[kind]);
  if (negotiated) {
    headers.set("vary", varyWith(headers.get("vary"), VARY));
    headers.set("cache-control", NEGOTIATED_CACHE_CONTROL);
  }
  return new Response(res.body, { status: res.status, statusText: res.statusText, headers });
}

// The seam: serve the agent version of the request's page, its JSON when the Accept header prefers JSON and the page
// has a JSON version, and its markdown otherwise. null when the page has no agent version or the method is not GET or
// HEAD, so the caller serves the request unchanged.
export function serveAgentVersion(request, env) {
  const page = readOnly(request) ? pageOf(new URL(request.url).pathname) : null;
  if (!page) return Promise.resolve(null);
  const kind = preferredAgentType(request.headers.get("accept"), page) === "json" ? "json" : "md";
  return serveAs(request, env, page[kind], kind, { negotiated: true });
}
