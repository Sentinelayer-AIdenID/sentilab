// node --test web/test/worker-agents.test.mjs
// The agent version of three human pages (web/src/agent-view.js, served by web/src/worker.js), against the real files
// in web/public:
//   - flag off: with TRUST_EDGE_CLASS anything but "1", the edge class header is ignored and every page is the human
//     page, byte for byte, so a client can't flip views by sending the header;
//   - flag on: x-aidenid-class: agent selects the agent version of /, /sentilab/ and /sentilab/package/;
//   - plain content negotiation, with no edge: an Accept that prefers markdown or JSON to HTML gets the agent version; a
//     browser's Accept, */*, a tie or no Accept gets the human page;
//   - both versions of a negotiated page carry Vary: Accept, x-aidenid-class and private, no-cache; the human version
//     names its agent version in a Link header;
//   - every other path is unchanged: the asset layer's status, bytes and headers, plus the CSP.
// The checks run against mutants of the Worker too (trusting the header without the flag, dropping Vary, letting a tie
// with HTML pick the agent version), and each mutant must be caught.
import { test } from "node:test";
import assert from "node:assert/strict";
import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, extname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import realWorker from "../src/worker.js";
import { CSP } from "../src/csp.js";
import { AGENT_PAGES, EDGE_CLASS_HEADER, acceptQuality, preferredAgentType, varyWith } from "../src/agent-view.js";

const here = dirname(fileURLToPath(import.meta.url));
const PUBLIC = join(here, "..", "public");
const SRC = join(here, "..", "src");
const BASE = "https://sentilab.aidenid.com";
const BROWSER = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8";
const VARY = "Accept, x-aidenid-class";
const NO_SHARED_CACHE = "private, no-cache";
const MD = "text/markdown; charset=utf-8";
const JSON_TYPE = "application/json; charset=utf-8";
const HUMAN = { "/": "index.html", "/sentilab/": "sentilab/index.html", "/sentilab/package/": "sentilab/package/index.html" };
const AGENT_MD = { "/": "agents/index.md", "/sentilab/": "agents/index.md", "/sentilab/package/": "agents/physics.md" };
const ALTERNATE = { "/": "/agents/", "/sentilab/": "/agents/", "/sentilab/package/": "/agents/physics.md" };
const file = (rel) => new Uint8Array(readFileSync(join(PUBLIC, ...rel.split("/"))));
const link = (href) => `<${href}>; rel="alternate"; type="text/markdown"`;

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
async function get(worker, path, { headers = {}, env = {}, method = "GET" } = {}) {
  const bound = { ASSETS: assets(), API_ORIGIN: "https://sentilab-api.example.test", ...env };
  const res = await worker.fetch(new Request(BASE + path, { method, headers }), bound);
  return { res, body: new Uint8Array(await res.arrayBuffer()), asked: bound.ASSETS.asked };
}
const same = (a, b) => a.length === b.length && a.every((x, i) => x === b[i]);

// ── the checks, each a function of a worker, so the mutants below can run them too ──────────────────────────────
async function flagOffIgnoresTheHeader(worker) {
  for (const env of [{}, { TRUST_EDGE_CLASS: "0" }, { TRUST_EDGE_CLASS: "true" }, { TRUST_EDGE_CLASS: "yes" }, { TRUST_EDGE_CLASS: 1 }, { TRUST_EDGE_CLASS: " 1" }, { TRUST_EDGE_CLASS: "" }]) {
    for (const path of Object.keys(HUMAN)) {
      const { res, body } = await get(worker, path, { headers: { [EDGE_CLASS_HEADER]: "agent" }, env });
      assert.equal(res.status, 200);
      assert.ok(same(body, file(HUMAN[path])), `${path} with ${JSON.stringify(env)}: the human page`);
      assert.match(res.headers.get("content-type"), /^text[/]html/);
      assert.equal(res.headers.get("link"), link(ALTERNATE[path]));
    }
  }
}
async function flagOnHeaderSelectsTheAgentVersion(worker) {
  for (const value of ["agent", "Agent", " agent "]) {
    for (const path of Object.keys(HUMAN)) {
      const { res, body } = await get(worker, path, { headers: { [EDGE_CLASS_HEADER]: value }, env: { TRUST_EDGE_CLASS: "1" } });
      assert.equal(res.status, 200);
      assert.ok(same(body, file(AGENT_MD[path])), `${path} classed ${JSON.stringify(value)}: ${AGENT_MD[path]}`);
      assert.equal(res.headers.get("content-type"), MD);
      assert.equal(res.headers.get("link"), null, "the agent version names no alternate");
      assert.equal(res.headers.get("content-security-policy"), CSP);
    }
  }
  for (const value of ["human", "bot", "agents", ""]) {
    const { body } = await get(worker, "/", { headers: { [EDGE_CLASS_HEADER]: value }, env: { TRUST_EDGE_CLASS: "1" } });
    assert.ok(same(body, file("index.html")), `classed ${JSON.stringify(value)}: the human page`);
  }
  const { body } = await get(worker, "/", { env: { TRUST_EDGE_CLASS: "1" } });
  assert.ok(same(body, file("index.html")), "flag on, no header: the human page");
}
async function acceptPreferringMarkdownOrJsonGetsTheAgentIndex(worker) {
  for (const [accept, rel, type] of [["text/markdown", "agents/index.md", MD], ["application/json", "agents/index.json", JSON_TYPE],
    ["text/markdown, text/html;q=0.9", "agents/index.md", MD], ["text/html;q=0.5, application/json;q=0.6", "agents/index.json", JSON_TYPE],
    ["application/json, text/markdown", "agents/index.md", MD]]) {
    const { res, body } = await get(worker, "/", { headers: { accept } });
    assert.ok(same(body, file(rel)), `Accept ${accept}: ${rel}`);
    assert.equal(res.headers.get("content-type"), type);
  }
  const lab = await get(worker, "/sentilab/", { headers: { accept: "application/json" } });
  assert.ok(same(lab.body, file("agents/index.json")));
  const pkg = await get(worker, "/sentilab/package/", { headers: { accept: "text/markdown" } });
  assert.ok(same(pkg.body, file("agents/physics.md")));
  const noJson = await get(worker, "/sentilab/package/", { headers: { accept: "application/json" } });
  assert.ok(same(noJson.body, file("sentilab/package/index.html")), "a page with no JSON version stays human for a JSON-only Accept");
  const edgeAndJson = await get(worker, "/", { headers: { [EDGE_CLASS_HEADER]: "agent", accept: "application/json" }, env: { TRUST_EDGE_CLASS: "1" } });
  assert.ok(same(edgeAndJson.body, file("agents/index.json")), "an agent asking for JSON gets JSON");
}
async function browsersAndTiesGetTheHumanPage(worker) {
  for (const accept of [BROWSER, "*/*", "text/*", "text/html", "", "text/markdown;q=0", "text/markdown;q=2", "text/html, text/markdown"]) {
    for (const path of Object.keys(HUMAN)) {
      const { res, body } = await get(worker, path, { headers: accept ? { accept } : {} });
      assert.ok(same(body, file(HUMAN[path])), `${path} with Accept ${JSON.stringify(accept)}: the human page`);
      assert.match(res.headers.get("content-type"), /^text[/]html/);
    }
  }
}
async function negotiatedPagesVaryAndStayPrivate(worker) {
  const cases = [];
  for (const path of Object.keys(HUMAN)) {
    cases.push([path, {}, {}], [path, { accept: "text/markdown" }, {}], [path, { [EDGE_CLASS_HEADER]: "agent" }, { TRUST_EDGE_CLASS: "1" }]);
  }
  for (const [path, headers, env] of cases) {
    const { res } = await get(worker, path, { headers, env });
    assert.equal(res.headers.get("vary"), VARY, `${path} ${JSON.stringify(headers)}: Vary`);
    assert.equal(res.headers.get("cache-control"), NO_SHARED_CACHE, `${path} ${JSON.stringify(headers)}: cache-control`);
  }
}
async function otherPathsAreUnchanged(worker) {
  const paths = ["/leaderboard.html", "/sentilab/lab.js", "/agents/index.md", "/agents/challenge.json", "/agents.json", "/llms.txt", "/sentilab/package/index.html", "/nope", "/sentilab"];
  const headers = { [EDGE_CLASS_HEADER]: "agent", accept: "text/markdown" };
  for (const path of paths) {
    const direct = await assets().fetch(new Request(BASE + path, { headers }));
    const directBody = new Uint8Array(await direct.arrayBuffer());
    const { res, body, asked } = await get(worker, path, { headers, env: { TRUST_EDGE_CLASS: "1" } });
    assert.deepEqual(asked, [`GET ${path}`], `${path}: the asset layer is asked for the path itself`);
    assert.equal(res.status, direct.status);
    assert.ok(same(body, directBody), `${path}: the body is untouched`);
    const others = [...res.headers.entries()].filter(([k]) => k !== "content-security-policy").sort();
    assert.deepEqual(others, [...direct.headers.entries()].sort(), `${path}: every other header is the asset layer's`);
    assert.equal(res.headers.get("content-security-policy"), CSP);
  }
}

test("flag off: the edge class header is ignored, so every page is the human page", () => flagOffIgnoresTheHeader(realWorker));
test("flag on: x-aidenid-class: agent selects the agent version of each page; any other value keeps the human page", () => flagOnHeaderSelectsTheAgentVersion(realWorker));
test("an Accept that prefers markdown or JSON gets the agent index, with no edge", () => acceptPreferringMarkdownOrJsonGetsTheAgentIndex(realWorker));
test("a browser's Accept, */*, a tie or no Accept gets the human page", () => browsersAndTiesGetTheHumanPage(realWorker));
test("both versions of a negotiated page vary on Accept and the class header and stay out of shared caches", () => negotiatedPagesVaryAndStayPrivate(realWorker));
test("every other path is unchanged: the asset layer's status, bytes and headers, plus the CSP", () => otherPathsAreUnchanged(realWorker));

test("/agents and /agents/ serve /agents/index.md to everyone", async () => {
  for (const path of ["/agents", "/agents/"]) {
    for (const headers of [{}, { accept: BROWSER }]) {
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
  const post = await get(realWorker, "/", { method: "POST", headers: { accept: "text/markdown", [EDGE_CLASS_HEADER]: "agent" }, env: { TRUST_EDGE_CLASS: "1" } });
  assert.deepEqual(post.asked, ["POST /"]);
  assert.equal(post.res.headers.get("vary"), null);
  const fresh = await get(realWorker, "/", { headers: { accept: "text/markdown", "if-none-match": '"/agents/index.md"' } });
  assert.equal(fresh.res.status, 304);
  assert.equal(fresh.res.headers.get("vary"), VARY);
  const stale = await get(realWorker, "/", { headers: { accept: "text/markdown", "if-none-match": '"/index.html"' } });
  assert.equal(stale.res.status, 200, "the human page's ETag never validates the agent version");
  assert.ok(same(stale.body, file("agents/index.md")));
});
test("acceptQuality and preferredAgentType follow q-values, the most specific range first", () => {
  assert.equal(acceptQuality(BROWSER, "text/html"), 1);
  assert.equal(acceptQuality(BROWSER, "text/markdown"), 0.8);
  assert.equal(acceptQuality("text/*;q=0.4, text/markdown;q=0.7", "text/markdown"), 0.7);
  assert.equal(acceptQuality("text/markdown;q=0.7, text/*;q=0.9", "text/markdown"), 0.7, "the specific range wins whatever its order");
  assert.equal(acceptQuality("TEXT/Markdown;Q=0.5", "text/markdown"), 0.5);
  assert.equal(acceptQuality("text/markdown;q=abc", "text/markdown"), 0);
  assert.equal(acceptQuality(undefined, "text/html"), 0);
  assert.equal(preferredAgentType("text/markdown", AGENT_PAGES["/"]), "md");
  assert.equal(preferredAgentType("application/json;q=0.9, text/markdown;q=0.8", AGENT_PAGES["/"]), "json");
  assert.equal(preferredAgentType("application/json", AGENT_PAGES["/sentilab/package/"]), null);
  assert.equal(preferredAgentType("*/*", AGENT_PAGES["/"]), null);
  assert.equal(varyWith("Accept-Encoding", ["Accept", EDGE_CLASS_HEADER]), "Accept-Encoding, Accept, x-aidenid-class");
  assert.equal(varyWith("accept", ["Accept"]), "accept");
  assert.equal(varyWith("*", ["Accept"]), "*");
});

// ── mutants: each must make at least one of the checks above fail ─────────────────────────────────────────────────
const MUTANTS = [
  { name: "trust the header without the flag", file: "agent-view.js", from: 'if (!env || env.TRUST_EDGE_CLASS !== "1") return false;', to: "if (!env) return false;", caughtBy: flagOffIgnoresTheHeader },
  { name: "drop Vary from negotiated pages", file: "worker.js", from: 'headers.set("vary", varyWith(headers.get("vary"), VARY));', to: "", caughtBy: negotiatedPagesVaryAndStayPrivate },
  { name: "let a tie with HTML pick the agent version", file: "agent-view.js", from: "if (quality > bestQuality) {", to: "if (quality >= bestQuality) {", caughtBy: browsersAndTiesGetTheHumanPage },
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
      const mutated = (await import(pathToFileURL(join(dir, "worker.js")).href)).default;
      await mutant.caughtBy(realWorker);
      await assert.rejects(() => mutant.caughtBy(mutated), assert.AssertionError, "the check fails on the mutant");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
}
