// The agent version of three human pages, and how a request gets it. Pure functions of (request, env), no I/O, so the
// node tests drive them directly and through the Worker (web/test/worker-agents.test.mjs). A module of its own because
// worker.js may export nothing but its default handler (see csp.js).
//
// A request to one of AGENT_PAGES gets that page's agent version in one of two ways:
//   1. Plain content negotiation. Its Accept header gives markdown or JSON a higher q-value than HTML. A tie, "*/*", a
//      missing header and a browser's default Accept all keep the human page. Any client may ask; nothing is detected.
//   2. The edge's class header says "agent", and only when this Worker is told to trust it: env.TRUST_EDGE_CLASS === "1".
//      That flag is set only once the edge fronts this Worker through a service binding, sets the header itself and
//      strips any client-sent copy. With the flag off the header is not read at all, so a client can't flip views by
//      sending it.
// Both versions of a negotiated page say they vary on Accept and on the class header, and neither may sit in a shared
// cache, so no cache hands one version to a request for the other. The human version names its agent version in a Link
// header. /agents and /agents/ serve /agents/index.md to everyone. Every other path is served unchanged.

// The edge's class header and the value that selects the agent version. Provisional: the name and value are confirmed
// with the edge lane before TRUST_EDGE_CLASS is ever set.
export const EDGE_CLASS_HEADER = "x-aidenid-class";
export const EDGE_CLASS_AGENT = "agent";

// Each page with an agent version: the files that version serves (paths under web/public), and the URL the human page
// names as its alternate.
export const AGENT_PAGES = Object.freeze({
  "/": Object.freeze({ md: "/agents/index.md", json: "/agents/index.json", alternate: "/agents/" }),
  "/sentilab/": Object.freeze({ md: "/agents/index.md", json: "/agents/index.json", alternate: "/agents/" }),
  "/sentilab/package/": Object.freeze({ md: "/agents/physics.md", alternate: "/agents/physics.md" }),
});
// The agent site's own index, the same for every client.
export const AGENT_INDEX = Object.freeze({ "/agents": "/agents/index.md", "/agents/": "/agents/index.md" });

export const CONTENT_TYPES = Object.freeze({ md: "text/markdown; charset=utf-8", json: "application/json; charset=utf-8" });
const MEDIA = Object.freeze({ md: "text/markdown", json: "application/json", html: "text/html" });
export const VARY = Object.freeze(["Accept", EDGE_CLASS_HEADER]);
export const NEGOTIATED_CACHE_CONTROL = "private, no-cache";
const QVALUE = /^(0([.][0-9]{0,3})?|1([.]0{0,3})?)$/;

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

// Whether the trusted edge classed this request as an agent. False unless TRUST_EDGE_CLASS is exactly "1"; the header
// is not even read otherwise.
export function edgeSaysAgent(request, env) {
  if (!env || env.TRUST_EDGE_CLASS !== "1") return false;
  const value = request.headers.get(EDGE_CLASS_HEADER);
  return value !== null && value.trim().toLowerCase() === EDGE_CLASS_AGENT;
}

// What the Worker serves for this request. null: not an agent-aware path or method, so serve it unchanged. Otherwise
// { negotiated, serve, kind, alternate }: serve is the file to fetch instead of the requested one (null keeps the human
// page), kind its representation ("md" or "json"), alternate the agent URL a human page names.
export function agentView(request, env) {
  if (request.method !== "GET" && request.method !== "HEAD") return null;
  const { pathname } = new URL(request.url);
  if (Object.hasOwn(AGENT_INDEX, pathname)) return { negotiated: false, serve: AGENT_INDEX[pathname], kind: "md", alternate: null };
  if (!Object.hasOwn(AGENT_PAGES, pathname)) return null;
  const page = AGENT_PAGES[pathname];
  const kind = preferredAgentType(request.headers.get("accept"), page) ?? (edgeSaysAgent(request, env) ? "md" : null);
  return { negotiated: true, serve: kind ? page[kind] : null, kind, alternate: page.alternate };
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
