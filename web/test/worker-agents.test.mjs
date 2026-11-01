// node --test web/test/worker-agents.test.mjs
// The agent version of three human pages (web/src/agent-paths.js maps them, web/src/agent-view.js serves them, through
// web/src/worker.js), against the real files in web/public. Root's rerouting checklist, item by item:
//   1. agentPathFor maps "/" and "/sentilab/" to /agents/index.md and "/sentilab/package/" to /agents/physics.md, and
//      every other path to null (served unchanged); serveAgentVersion serves that file, typed, varying on Accept.
//   2. A browser's Accept gets the exact human page: the asset layer's bytes, untouched.
//   3. Accept negotiation, with one rule: the agent version is served when the Accept header gives markdown or JSON a
//      strictly higher q-value than HTML. Each type's q-value is that of its most specific matching range
//      (type/subtype, then type/*, then */*); a missing or malformed q is 1 or 0 respectively. Markdown wins a tie with
//      JSON, HTML wins any tie with either, and a page without a JSON version never serves JSON.
//   4. Every response that can differ (both versions of the three pages, 304s included) carries Vary: Accept and
//      Cache-Control: private, no-store, so no cache hands one visitor's version to the next.
// Plus: the human page names its agent version in a Link header, /agents/ serves /agents/index.md, every other path is
// unchanged, and mutants of each guard are caught.
import { test } from "node:test";
import assert from "node:assert/strict";
import { cpSync, existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, extname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import realWorker from "../src/worker.js";
import * as realPaths from "../src/agent-paths.js";
import * as realView from "../src/agent-view.js";
import { CSP } from "../src/csp.js";

const here = dirname(fileURLToPath(import.meta.url));
const NL = String.fromCharCode(10);
const PUBLIC = join(here, "..", "public");
const SRC = join(here, "..", "src");
const BASE = "https://sentilab.aidenid.com";
const BROWSERS = [
  "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
  "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
  "text/html, application/xhtml+xml, image/jxr, */*",
];
const MD = "text/markdown; charset=utf-8";
const JSON_TYPE = "application/json; charset=utf-8";
const NO_SHARED_CACHE = "private, no-store";
const HUMAN = { "/": "index.html", "/sentilab/": "sentilab/index.html", "/sentilab/package/": "sentilab/package/index.html" };
const AGENT_MD = { "/": "/agents/index.md", "/sentilab/": "/agents/index.md", "/sentilab/package/": "/agents/physics.md" };
const AGENT_JSON = { "/": "/agents/index.json", "/sentilab/": "/agents/index.json" };
const ALTERNATE = { "/": "/agents/", "/sentilab/": "/agents/", "/sentilab/package/": "/agents/physics.md" };
const UNMAPPED = ["/index.html", "/sentilab", "/sentilab/index.html", "/sentilab/package", "/sentilab/package/index.html", "/sentilab/lab.js",
  "/leaderboard.html", "/verify.html", "/licenses.html", "/agents", "/agents/", "/agents/index.md", "/agents/physics.md", "/llms.txt", "/agents.json",
  "/api/view/runs", "/nope", "", "//", "/SENTILAB/", "/constructor", "/__proto__", "/hasOwnProperty", "/sentilab/package/x"];
const REAL = { paths: realPaths, view: realView };
const file = (rel) => new Uint8Array(readFileSync(join(PUBLIC, ...rel.split("/").filter(Boolean))));
const link = (href) => `<${href}>; rel="alternate"; type="text/markdown"`;
const same = (a, b) => a.length === b.length && a.every((x, i) => x === b[i]);

// A stand-in asset layer over the real files in web/public: a path ending in / serves that folder's index.html. It
// answers with a content type, an ETag and cache-control as an asset layer would, and logs what it was asked.
const TYPES = { ".html": "text/html; charset=utf-8", ".md": "text/markdown", ".json": "application/json", ".js": "text/javascript", ".txt": "text/plain; charset=utf-8" };
function assets() {
  const asked = [];
  return {
    asked,
    fetch: async (request) => {
      const path = new URL(request.url).pathname;
      asked.push(`${request.method} ${path}`);
      const rel = path.endsWith("/") ? `${path}index.html` : path;
      let body;
      try { body = readFileSync(join(PUBLIC, ...rel.split("/").filter(Boolean))); } catch { return new Response("not found", { status: 404, headers: { "content-type": "text/plain" } }); }
      const etag = `"${rel}"`;
      if (request.headers.get("if-none-match") === etag) return new Response(null, { status: 304, headers: { etag } });
      return new Response(request.method === "HEAD" ? null : body,
        { status: 200, headers: { "content-type": TYPES[extname(rel)] || "application/octet-stream", etag, "cache-control": "public, max-age=0, must-revalidate" } });
    },
  };
}
const envOf = () => ({ ASSETS: assets(), API_ORIGIN: "https://sentilab-api.example.test" });
async function get(worker, path, { headers = {}, method = "GET" } = {}) {
  const env = envOf();
  const res = await worker.fetch(new Request(BASE + path, { method, headers }), env);
  return { res, body: new Uint8Array(await res.arrayBuffer()), asked: env.ASSETS.asked };
}

// ── the checks, each a function of (worker, view module), so the mutants below can run them too ──────────────────
async function mappingIsExact(worker, { paths }) {
  for (const [path, target] of Object.entries(AGENT_MD)) {
    assert.equal(paths.agentPathFor(path), target, `agentPathFor(${JSON.stringify(path)})`);
    assert.ok(existsSync(join(PUBLIC, ...target.split("/").filter(Boolean))), `${target} exists`);
  }
  for (const path of UNMAPPED) assert.equal(paths.agentPathFor(path), null, `agentPathFor(${JSON.stringify(path)}) is null: unchanged`);
}
async function serveAgentVersionServesTheMappedFile(worker, { view }) {
  for (const path of Object.keys(AGENT_MD)) {
    for (const accept of [undefined, BROWSERS[0], "text/markdown"]) {
      const env = envOf();
      const res = await view.serveAgentVersion(new Request(BASE + path, { headers: accept ? { accept } : {} }), env);
      assert.equal(res.status, 200);
      assert.ok(same(new Uint8Array(await res.arrayBuffer()), file(AGENT_MD[path])), `${path} with ${accept}: ${AGENT_MD[path]}`);
      assert.deepEqual(env.ASSETS.asked, [`GET ${AGENT_MD[path]}`]);
      assert.equal(res.headers.get("content-type"), MD);
      assert.equal(res.headers.get("vary"), "Accept");
      assert.equal(res.headers.get("cache-control"), NO_SHARED_CACHE);
      assert.equal(res.headers.get("content-security-policy"), CSP);
    }
  }
  for (const path of Object.keys(AGENT_JSON)) {
    const res = await view.serveAgentVersion(new Request(BASE + path, { headers: { accept: "application/json" } }), envOf());
    assert.ok(same(new Uint8Array(await res.arrayBuffer()), file(AGENT_JSON[path])), `${path}: JSON when JSON is preferred`);
    assert.equal(res.headers.get("content-type"), JSON_TYPE);
  }
  const pkg = await view.serveAgentVersion(new Request(`${BASE}/sentilab/package/`, { headers: { accept: "application/json" } }), envOf());
  assert.equal(pkg.headers.get("content-type"), MD, "a page with no JSON version serves its markdown");
  for (const path of UNMAPPED.filter((p) => p.startsWith("/"))) assert.equal(await view.serveAgentVersion(new Request(BASE + path), envOf()), null, `${path}: null`);
  for (const method of ["POST", "PUT", "DELETE", "OPTIONS"]) assert.equal(await view.serveAgentVersion(new Request(`${BASE}/`, { method }), envOf()), null, method);
}
async function browsersGetTheExactHumanPage(worker) {
  for (const accept of [...BROWSERS, "*/*", "text/*", "text/html", "", "text/markdown;q=0", "text/markdown;q=2", "text/html, text/markdown"]) {
    for (const [path, rel] of Object.entries(HUMAN)) {
      const direct = await assets().fetch(new Request(BASE + path));
      const { res, body } = await get(worker, path, { headers: accept ? { accept } : {} });
      assert.equal(res.status, 200);
      assert.ok(same(body, file(rel)), `${path} with Accept ${JSON.stringify(accept)}: the human page, byte for byte`);
      const others = [...res.headers.entries()].filter(([k]) => !["content-security-policy", "vary", "cache-control", "link"].includes(k)).sort();
      assert.deepEqual(others, [...direct.headers.entries()].filter(([k]) => k !== "cache-control").sort(), `${path}: the asset layer's own headers`);
      assert.equal(res.headers.get("link"), link(ALTERNATE[path]), `${path}: names its agent version`);
    }
  }
}
// [Accept, expected for "/", expected for "/sentilab/package/"]: "md", "json" or "human".
const NEGOTIATION = [
  ["text/markdown", "md", "md"], ["application/json", "json", "human"], ["TEXT/Markdown", "md", "md"], ["text/markdown; charset=utf-8", "md", "md"],
  ["text/markdown, application/json", "md", "md"], ["application/json, text/markdown", "md", "md"],
  ["application/json;q=0.9, text/markdown;q=0.8", "json", "md"], ["text/html;q=0.9, text/markdown", "md", "md"],
  ["text/html;q=0.5, application/json;q=0.6", "json", "human"], ["text/markdown;q=0.5, text/html;q=0.5", "human", "human"],
  ["application/*", "json", "human"], ["text/plain", "human", "human"], ["text/markdown;q=0.7, text/*;q=0.9", "human", "human"],
];
async function acceptNegotiationIsDeterministic(worker) {
  const expectFile = { md: AGENT_MD, json: AGENT_JSON, human: { "/": "/index.html", "/sentilab/package/": "/sentilab/package/index.html" } };
  for (const [accept, root, pkg] of NEGOTIATION) {
    for (const [path, outcome] of [["/", root], ["/sentilab/package/", pkg]]) {
      const { res, body } = await get(worker, path, { headers: { accept } });
      assert.ok(same(body, file(expectFile[outcome][path])), `${path} with Accept ${JSON.stringify(accept)}: ${outcome}`);
      assert.match(res.headers.get("content-type"), outcome === "human" ? /^text[/]html/ : outcome === "md" ? /^text[/]markdown; charset=utf-8$/ : /^application[/]json; charset=utf-8$/);
    }
  }
}
async function everyVaryingResponseIsPrivate(worker) {
  for (const path of Object.keys(HUMAN)) {
    for (const headers of [{}, { accept: BROWSERS[0] }, { accept: "text/markdown" }, { accept: "application/json" },
      { accept: "text/markdown", "if-none-match": `"${AGENT_MD[path]}"` }, { accept: BROWSERS[1], "if-none-match": `"${path}index.html"` }]) {
      for (const method of ["GET", "HEAD"]) {
        const { res } = await get(worker, path, { headers, method });
        assert.equal(res.headers.get("vary"), "Accept", `${method} ${path} ${JSON.stringify(headers)} (${res.status}): Vary`);
        assert.equal(res.headers.get("cache-control"), NO_SHARED_CACHE, `${method} ${path} ${JSON.stringify(headers)} (${res.status}): cache-control`);
      }
    }
  }
}
async function otherPathsAreUnchanged(worker) {
  const paths = ["/leaderboard.html", "/sentilab/lab.js", "/agents/index.md", "/agents/challenge.json", "/agents.json", "/llms.txt", "/sentilab/package/index.html", "/nope", "/sentilab"];
  for (const accept of ["text/markdown", "application/json", BROWSERS[0]]) {
    for (const path of paths) {
      const direct = await assets().fetch(new Request(BASE + path, { headers: { accept } }));
      const directBody = new Uint8Array(await direct.arrayBuffer());
      const { res, body, asked } = await get(worker, path, { headers: { accept } });
      assert.deepEqual(asked, [`GET ${path}`], `${path}: the asset layer is asked for the path itself`);
      assert.equal(res.status, direct.status);
      assert.ok(same(body, directBody), `${path}: the body is untouched`);
      const others = [...res.headers.entries()].filter(([k]) => k !== "content-security-policy").sort();
      assert.deepEqual(others, [...direct.headers.entries()].sort(), `${path}: every other header is the asset layer's`);
      assert.equal(res.headers.get("content-security-policy"), CSP);
    }
  }
}

test("1. agentPathFor maps each page with an agent version to its file, and every other path to null", () => mappingIsExact(realWorker, REAL));
test("1. serveAgentVersion serves the mapped file, typed, varying on Accept, private; JSON when preferred; null otherwise", () => serveAgentVersionServesTheMappedFile(realWorker, REAL));
test("2. a browser's Accept gets the exact human page, byte for byte, with its Link to the agent version", () => browsersGetTheExactHumanPage(realWorker));
test("3. markdown or JSON in Accept gets the agent index; mixed and q-weighted headers resolve by the documented rule", () => acceptNegotiationIsDeterministic(realWorker));
test("4. every response that can differ varies on Accept and stays out of shared caches (GET, HEAD and 304)", () => everyVaryingResponseIsPrivate(realWorker));
test("every other path is unchanged: the asset layer's status, bytes and headers, plus the CSP", () => otherPathsAreUnchanged(realWorker));

test("/agents and /agents/ serve /agents/index.md to everyone", async () => {
  for (const path of ["/agents", "/agents/"]) {
    for (const headers of [{}, { accept: BROWSERS[0] }, { accept: "application/json" }]) {
      const { res, body, asked } = await get(realWorker, path, { headers });
      assert.equal(res.status, 200);
      assert.ok(same(body, file("agents/index.md")));
      assert.equal(res.headers.get("content-type"), MD);
      assert.deepEqual(asked, ["GET /agents/index.md"]);
      assert.equal(res.headers.get("vary"), null, "the same for every client");
    }
  }
});
test("HEAD gets the same choice; other methods are never negotiated; conditional requests reach the file served", async () => {
  const head = await get(realWorker, "/", { method: "HEAD", headers: { accept: "text/markdown" } });
  assert.deepEqual(head.asked, ["HEAD /agents/index.md"]);
  assert.equal(head.res.headers.get("content-type"), MD);
  const post = await get(realWorker, "/", { method: "POST", headers: { accept: "text/markdown" } });
  assert.deepEqual(post.asked, ["POST /"]);
  assert.equal(post.res.headers.get("vary"), null);
  const fresh = await get(realWorker, "/", { headers: { accept: "text/markdown", "if-none-match": '"/agents/index.md"' } });
  assert.equal(fresh.res.status, 304);
  const stale = await get(realWorker, "/", { headers: { accept: "text/markdown", "if-none-match": '"/index.html"' } });
  assert.equal(stale.res.status, 200, "the human page's ETag never validates the agent version");
  assert.ok(same(stale.body, file("agents/index.md")));
});
test("acceptQuality, preferredAgentType and varyWith follow the documented rule", () => {
  const { acceptQuality, preferredAgentType, varyWith } = realView;
  const INDEX = { md: "/agents/index.md", json: "/agents/index.json" };
  const PHYSICS = { md: "/agents/physics.md" };
  assert.equal(acceptQuality(BROWSERS[0], "text/html"), 1);
  assert.equal(acceptQuality(BROWSERS[0], "text/markdown"), 0.8);
  assert.equal(acceptQuality("text/*;q=0.4, text/markdown;q=0.7", "text/markdown"), 0.7);
  assert.equal(acceptQuality("text/markdown;q=0.7, text/*;q=0.9", "text/markdown"), 0.7, "the specific range wins whatever its order");
  assert.equal(acceptQuality("TEXT/Markdown;Q=0.5", "text/markdown"), 0.5);
  assert.equal(acceptQuality("text/markdown;q=abc", "text/markdown"), 0);
  assert.equal(acceptQuality(undefined, "text/html"), 0);
  assert.equal(preferredAgentType("text/markdown", INDEX), "md");
  assert.equal(preferredAgentType("application/json;q=0.9, text/markdown;q=0.8", INDEX), "json");
  assert.equal(preferredAgentType("application/json", PHYSICS), null);
  assert.equal(preferredAgentType("*/*", INDEX), null);
  assert.equal(varyWith("Accept-Encoding", ["Accept"]), "Accept-Encoding, Accept");
  assert.equal(varyWith("accept", ["Accept"]), "accept");
  assert.equal(varyWith("*", ["Accept"]), "*");
});
test("the classification header of an earlier draft is not read: x-aidenid-class changes nothing", async () => {
  for (const env of [{}, { TRUST_EDGE_CLASS: "1" }]) {
    const bound = { ...envOf(), ...env };
    const res = await realWorker.fetch(new Request(`${BASE}/`, { headers: { "x-aidenid-class": "agent" } }), bound);
    assert.ok(same(new Uint8Array(await res.arrayBuffer()), file("index.html")));
  }
  assert.doesNotMatch(["agent-paths.js", "agent-view.js", "worker.js"].map((f) => readFileSync(join(SRC, f), "utf8")).join(""), /aidenid-class|TRUST_EDGE_CLASS/);
});
test("agent-paths.js exports exactly agentPathFor(pathname), the seam a classifier imports; worker.js exports only its handler", async () => {
  assert.deepEqual(Object.keys(realPaths), ["agentPathFor"]);
  assert.equal(realPaths.agentPathFor.length, 1);
  assert.deepEqual(Object.keys(await import("../src/worker.js")), ["default"]);
});

// ── mutants: each must make the check named for it fail ──────────────────────────────────────────────────────────
const MUTANTS = [
  { name: "the human page stops varying on Accept", file: "agent-view.js",
    from: '  headers.set("vary", varyWith(headers.get("vary"), VARY));' + NL + '  headers.set("cache-control", NEGOTIATED_CACHE_CONTROL);' + NL + '  headers.set("link"',
    to: '  headers.set("cache-control", NEGOTIATED_CACHE_CONTROL);' + NL + '  headers.set("link"', caughtBy: everyVaryingResponseIsPrivate },
  { name: "negotiated responses may be cached and shared", file: "agent-view.js", from: 'export const NEGOTIATED_CACHE_CONTROL = "private, no-store";',
    to: 'export const NEGOTIATED_CACHE_CONTROL = "public, max-age=0, must-revalidate";', caughtBy: everyVaryingResponseIsPrivate },
  { name: "a tie with HTML picks the agent version", file: "agent-view.js", from: "if (quality > bestQuality) {", to: "if (quality >= bestQuality) {", caughtBy: browsersGetTheExactHumanPage },
  { name: "agentPathFor maps a path without its trailing slash", file: "agent-paths.js",
    from: "return Object.hasOwn(AGENT_PATHS, pathname) ? AGENT_PATHS[pathname] : null;",
    to: "return Object.hasOwn(AGENT_PATHS, pathname) ? AGENT_PATHS[pathname] : Object.hasOwn(AGENT_PATHS, `${pathname}/`) ? AGENT_PATHS[`${pathname}/`] : null;",
    caughtBy: mappingIsExact },
  { name: "serveAgentVersion ignores a JSON preference", file: "agent-view.js", from: 'preferredAgentType(request.headers.get("accept"), versions) === "json" ? "json" : "md";',
    to: '"md";', caughtBy: serveAgentVersionServesTheMappedFile },
  { name: "the human page drops its Link header", file: "agent-view.js", from: '  headers.set("link", alternateLink(Object.hasOwn(PRETTY, md) ? PRETTY[md] : md));', to: "", caughtBy: browsersGetTheExactHumanPage },
];
for (const mutant of MUTANTS) {
  test(`mutant caught: ${mutant.name}`, async () => {
    const dir = mkdtempSync(join(tmpdir(), "worker-mutant-"));
    try {
      cpSync(SRC, dir, { recursive: true });
      const path = join(dir, mutant.file);
      const source = readFileSync(path, "utf8");
      assert.equal(source.split(mutant.from).length - 1, 1, "the mutation applies at exactly one place");
      writeFileSync(path, source.replace(mutant.from, mutant.to));
      const worker = (await import(pathToFileURL(join(dir, "worker.js")).href)).default;
      const mods = { paths: await import(pathToFileURL(join(dir, "agent-paths.js")).href), view: await import(pathToFileURL(join(dir, "agent-view.js")).href) };
      await mutant.caughtBy(realWorker, REAL);
      await assert.rejects(() => mutant.caughtBy(worker, mods), assert.AssertionError, "the check fails on the mutant");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
}
