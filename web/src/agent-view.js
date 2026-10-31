// The agent version of three human pages, served on plain content negotiation. agent-paths.js says which file is a
// page's agent version (agentPathFor); this module serves it. A module of its own because worker.js may export nothing
// but its default handler (see csp.js). The node tests drive it directly and through the Worker
// (web/test/worker-agents.test.mjs).
//
// The rule: a GET or HEAD for a page with an agent version gets that version when its Accept header gives markdown or
// JSON a strictly higher q-value than HTML. A type's q-value is that of its most specific matching range (type/subtype,
// then type/*, then */*); a missing q is 1 and a malformed one 0. Markdown wins a tie with JSON; HTML wins any tie, so
// a browser's Accept, */*, text/* and no Accept all keep the human page. A page with no JSON version never serves JSON.
// Both versions of these pages vary on Accept and are private, no-store; the human version names its agent version in a
// Link header. /agents and /agents/ serve /agents/index.md to everyone. Who is asking is decided elsewhere, if at all.
import { CSP } from "./csp.js";
import { agentPathFor } from "./agent-paths.js";

// The JSON version of an agent page, where there is one, and the URL a human page names as its agent version.
const JSON_VERSION = Object.freeze({ "/agents/index.md": "/agents/index.json" });
const PRETTY = Object.freeze({ "/agents/index.md": "/agents/" });
// The agent site's own index, the same for every client.
export const AGENT_INDEX = Object.freeze({ "/agents": "/agents/index.md", "/agents/": "/agents/index.md" });

export const CONTENT_TYPES = Object.freeze({ md: "text/markdown; charset=utf-8", json: "application/json; charset=utf-8" });
const MEDIA = Object.freeze({ md: "text/markdown", json: "application/json", html: "text/html" });
export const VARY = Object.freeze(["Accept"]);
export const NEGOTIATED_CACHE_CONTROL = "private, no-store";
const QVALUE = /^(0([.][0-9]{0,3})?|1([.]0{0,3})?)$/;
const readOnly = (request) => request.method === "GET" || request.method === "HEAD";

// The versions a page offers: { md, json? } file paths, or null when it has no agent version.
function versionsOf(pathname) {
  const md = agentPathFor(pathname);
  if (!md) return null;
  return Object.hasOwn(JSON_VERSION, md) ? { md, json: JSON_VERSION[md] } : { md };
}

// The q-value an Accept header gives one media type (the rule above); 0 when no range matches or there is no header.
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

// The agent representation the Accept header prefers to HTML, among those the page offers: "md", "json" or null.
export function preferredAgentType(accept, versions) {
  let best = null;
  let bestQuality = acceptQuality(accept, MEDIA.html);
  for (const kind of ["md", "json"]) {
    if (!versions[kind]) continue;
    const quality = acceptQuality(accept, MEDIA[kind]);
    if (quality > bestQuality) {
      best = kind;
      bestQuality = quality;
    }
  }
  return best;
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

// The asset at path, served for this request (same method and headers, so conditional requests reach that file), with
// the CSP and its type ("md" or "json"). A negotiated response also varies on Accept and is private, no-store.
async function serveAs(request, env, path, kind, negotiated) {
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

// The agent version of the request's page: its JSON when the Accept header prefers JSON and the page has a JSON
// version, its markdown otherwise. null when the page has none or the method is not GET or HEAD (serve it unchanged).
export function serveAgentVersion(request, env) {
  const versions = readOnly(request) ? versionsOf(new URL(request.url).pathname) : null;
  if (!versions) return Promise.resolve(null);
  const kind = preferredAgentType(request.headers.get("accept"), versions) === "json" ? "json" : "md";
  return serveAs(request, env, versions[kind], kind, true);
}

// What the Worker serves in place of the requested asset, if anything: /agents/index.md for /agents and /agents/, and
// the agent version of a page whose Accept header prefers it. null: serve the request as usual.
export function serveAgentAsset(request, env) {
  if (!readOnly(request)) return Promise.resolve(null);
  const { pathname } = new URL(request.url);
  if (Object.hasOwn(AGENT_INDEX, pathname)) return serveAs(request, env, AGENT_INDEX[pathname], "md", false);
  const versions = versionsOf(pathname);
  if (!versions || preferredAgentType(request.headers.get("accept"), versions) === null) return Promise.resolve(null);
  return serveAgentVersion(request, env);
}

// The headers the human version of a page with an agent version adds: Vary: Accept, private, no-store, and the Link
// to its agent version. Anything else is left as it is.
export function addHumanPageHeaders(request, headers) {
  const md = readOnly(request) ? agentPathFor(new URL(request.url).pathname) : null;
  if (!md) return headers;
  headers.set("vary", varyWith(headers.get("vary"), VARY));
  headers.set("cache-control", NEGOTIATED_CACHE_CONTROL);
  headers.set("link", alternateLink(Object.hasOwn(PRETTY, md) ? PRETTY[md] : md));
  return headers;
}
