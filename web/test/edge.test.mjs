import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readdirSync, readFileSync } from "node:fs";
import { stripTypeScriptTypes } from "node:module";
import { classify, withEdge } from "../src/edge.js";
import worker from "../src/worker.js";
import { CSP } from "../src/csp.js";

const BASE = "https://sentilab.aidenid.com";
// The upstream classifier's complete Chromium navigation fixture, not just its UA.
const BROWSER = {
  "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
  "sec-fetch-mode": "navigate", "sec-fetch-dest": "document", "sec-fetch-site": "none",
  accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "accept-language": "en-US,en;q=0.9",
  "sec-ch-ua": '"Chromium";v="130", "Not A(Brand";v="99"', "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"Windows"',
};
const HUMAN = new Uint8Array([0, 255, 0xc3, 0xa9, 13, 10]);
const files = {
  "/": { body: HUMAN, type: "text/html; charset=utf-8" },
  "/unmapped": { body: "original unmapped", type: "text/html" },
  "/agents/index.md": { body: "# Agent home\n", type: "text/markdown; charset=utf-8" },
  "/agents/page.html": { body: "<h1>Agent</h1>", type: "text/html; charset=utf-8" },
  "/agents/data.json": { body: '{"agent":true}', type: "application/json" },
};
const request = (ua = "GPTBot", path = "/", extra = {}) => new Request(BASE + path, { headers: { "user-agent": ua, ...extra } });
const browser = (path = "/") => new Request(BASE + path, { headers: BROWSER });
const snapshot = async (response) => ({ status: response.status, statusText: response.statusText,
  headers: [...response.headers], bytes: [...new Uint8Array(await response.arrayBuffer())] });

function setup(collector = async () => new Response(null, { status: 202 })) {
  const fetched = [], posts = [], pending = [];
  const env = {
    AQUARIUM_POST: "on", // Explicit fake collector opt-in; deployment defaults to off.
    INGEST_TOKEN: "test-only",
    ASSETS: { async fetch(req) {
      const path = new URL(req.url).pathname;
      fetched.push(path);
      const file = files[path];
      return new Response(req.method === "HEAD" ? null : file?.body ?? "missing", { status: file ? 200 : 404,
        headers: { "content-type": file?.type ?? "text/plain", "x-original": "preserved", etag: '"asset"',
          vary: "Accept-Encoding", "cache-control": "public, max-age=3600", "set-cookie": "existing=1" } });
    } },
    COLLECTOR: { fetch(url, init) { posts.push({ url, init }); return collector(url, init); } },
  };
  const ctx = { waitUntil(promise) { pending.push(promise); } };
  const serve = async (req, environment) => {
    const res = await environment.ASSETS.fetch(req);
    const headers = new Headers(res.headers);
    headers.set("content-security-policy", CSP);
    return new Response(res.body, { status: res.status, statusText: res.statusText, headers });
  };
  const options = { serve, agentPathFor: (path) => path === "/" ? "/agents/index.md" : null };
  return { env, ctx, options, fetched, posts, pending,
    run: (req, overrides = {}) => withEdge(req, env, ctx, { ...options, ...overrides,
      serveAgent: async (original) => {
        const path = (overrides.agentPathFor ?? options.agentPathFor)(new URL(original.url).pathname);
        return path ? serve(new Request(new URL(path, original.url), original), env) : null;
      },
    }),
    drain: () => Promise.all(pending) };
}

for (const ua of ["GPTBot", "ClaudeBot", "PerplexityBot", "ChatGPT-User", "Google-Extended", "curl/8.4.0"]) {
  test(`known automation ${ua} gets agent content and a labelled event`, async () => {
    const s = setup();
    const res = await worker.fetch(request(ua), s.env, s.ctx);
    assert.equal(await res.text(), files["/agents/index.md"].body);
    assert.deepEqual(s.fetched, ["/agents/index.md"]);
    assert.equal(res.headers.get("cache-control"), "private, no-store");
    for (const header of ["user-agent", "accept", "signature", "signature-input", "signature-agent", "cookie"]) {
      assert.ok(res.headers.get("vary").toLowerCase().split(/,\s*/).includes(header));
    }
    await s.drain();
    assert.equal(s.posts.length, 1);
    assert.equal(JSON.parse(s.posts[0].init.body).identity.verified, false);
    assert.equal(await classify(request(ua), {}), "agent");
  });
}

test("documented automation and Safari trade-offs route the exact request shapes", async () => {
  const cases = [
    ["python-requests/2.31.0", {}, "agent"],
    ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.6 Safari/605.1.15", {}, "agent"],
    ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.6 Safari/605.1.15",
      { accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "accept-language": "en-US,en;q=0.9", "accept-encoding": "gzip", connection: "keep-alive", "upgrade-insecure-requests": "1", "cache-control": "max-age=0" }, "unknown"],
    ["Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
      { accept: "text/html", "accept-language": "en-US", "accept-encoding": "gzip", connection: "keep-alive", "upgrade-insecure-requests": "1", "cache-control": "max-age=0" }, "unknown"],
    ["Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Instagram 330.0.0.0.0", {}, "unknown"],
  ];
  for (const [ua, headers, expected] of cases) {
    const s = setup();
    assert.equal(await classify(request(ua, "/", headers), s.env), expected, ua);
    const res = await worker.fetch(request(ua, "/", headers), s.env, s.ctx);
    assert.deepEqual(s.fetched, [expected === "agent" ? "/agents/index.md" : "/"]);
    if (expected === "agent") assert.equal(await res.text(), files["/agents/index.md"].body);
    else assert.deepEqual(new Uint8Array(await res.arrayBuffer()), HUMAN);
    await s.drain();
    assert.equal(s.posts.length, expected === "agent" ? 1 : 0);
  }
});

test("browser preserves original bytes, status and headers except cache policy", async () => {
  const s = setup();
  const direct = await snapshot(await s.options.serve(browser(), s.env));
  s.fetched.length = 0;
  const actual = await snapshot(await worker.fetch(browser(), s.env, s.ctx));
  const expectedHeaders = new Headers(direct.headers);
  expectedHeaders.set("cache-control", "private, no-store");
  expectedHeaders.set("link", '</agents/>; rel="alternate"; type="text/markdown"');
  const vary = new Headers(actual.headers).get("vary");
  for (const name of ["Accept-Encoding", "User-Agent", "Accept", "Signature", "Signature-Input", "Signature-Agent", "Cookie",
    "Accept-Language", "Sec-Fetch-Mode", "Sec-Fetch-Dest", "Sec-Fetch-Site", "Sec-CH-UA", "Sec-CH-UA-Mobile", "Sec-CH-UA-Platform", "Referer"]) {
    assert.ok(vary.toLowerCase().split(/,\s*/).includes(name.toLowerCase()));
  }
  expectedHeaders.set("vary", vary);
  assert.deepEqual(actual, { ...direct, headers: [...expectedHeaders] });
  assert.deepEqual(s.fetched, ["/"]);
  assert.equal(await classify(browser(), {}), "human");
});

test("people and unknown clients never create aquarium work", async () => {
  for (const req of [browser(), request("unrecognized-client")]) {
    const s = setup();
    const res = await s.run(req);
    assert.deepEqual(new Uint8Array(await res.arrayBuffer()), HUMAN);
    await s.drain();
    assert.equal(s.pending.length, 0);
    assert.equal(s.posts.length, 0);
  }
  assert.equal(await classify(request("unrecognized-client"), {}), "unknown");
});

test("view=human and the exact cookie force the human page without classification", async () => {
  for (const req of [request("GPTBot", "/?view=human"), request("GPTBot", "/", { cookie: "x=1; sl_view=human; y=2" })]) {
    const s = setup();
    let classified = 0;
    const res = await s.run(req, { classifier() { classified++; return { triage: { class: "declared_agent" } }; } });
    assert.equal(classified, 0, "must bypass classification");
    assert.deepEqual(new Uint8Array(await res.arrayBuffer()), HUMAN);
    assert.equal(res.headers.get("cache-control"), "private, no-store");
    assert.ok(res.headers.getSetCookie().includes("existing=1"));
    assert.equal(res.headers.getSetCookie().includes("sl_view=human; Max-Age=1800; Path=/; Secure; SameSite=Lax"), req.url.includes("?view=human"));
    assert.equal(s.posts.length, 0);
  }
  const s = setup();
  assert.equal(await (await s.run(request("GPTBot", "/", { cookie: "not_sl_view=human" }))).text(), files["/agents/index.md"].body);
  await s.drain();
});

test("classifier exception serves the original page", async () => {
  const s = setup();
  const res = await s.run(request(), { classifier() { throw new Error("broken classifier"); } });
  assert.deepEqual(new Uint8Array(await res.arrayBuffer()), HUMAN);
  assert.deepEqual(s.fetched, ["/"]);
  assert.equal(s.posts.length, 0);
});

test("classifier timeout serves the original page and never observes a late result", { timeout: 2000 }, async () => {
  const s = setup();
  let finish;
  const res = await s.run(request(), { classifier: () => new Promise((resolve) => { finish = resolve; }) });
  finish({ triage: { class: "declared_agent" } });
  assert.deepEqual(new Uint8Array(await res.arrayBuffer()), HUMAN);
  await s.drain();
  assert.equal(s.posts.length, 0);
});

test("collector rejection and timeout leave response identical and background tasks settle", { timeout: 5000 }, async () => {
  const reference = setup();
  const expected = await snapshot(await reference.run(request()));
  await reference.drain();
  for (const mode of ["reject", "hang", "redirect"]) {
    const s = setup(async () => {
      if (mode === "reject") throw new Error("collector down");
      if (mode === "hang") return new Promise(() => {}); // Deliberately ignores abort.
      return new Response(null, { status: 302, headers: { location: "https://elsewhere.test" } });
    });
    let settled = false;
    const res = await s.run(request());
    s.drain().then(() => { settled = true; });
    assert.deepEqual(await snapshot(res), expected);
    if (mode === "hang") assert.equal(settled, false, "response completes before ingest timeout");
    await s.drain();
    assert.equal(s.posts.length, 1);
    assert.equal(s.posts[0].init.redirect, "manual");
    assert.equal(s.posts[0].init.signal.aborted, mode === "hang");
  }
});

test("broken routing seams and missing agent assets fall back to human bytes", async () => {
  for (const agentPathFor of [() => { throw new Error("bad seam"); }, () => "/agents/missing", () => "//elsewhere.test/x",
    () => "/\\elsewhere.test/x", () => undefined, () => "/agents/index.md?private=1"]) {
    const s = setup();
    assert.deepEqual(new Uint8Array(await (await s.run(request(), { agentPathFor })).arrayBuffer()), HUMAN);
    await s.drain();
  }
  const s = setup();
  assert.equal(await (await s.run(request("GPTBot", "/unmapped"))).text(), "original unmapped");
  await s.drain();
});

test("background context failure or missing collector leaves routing usable", async () => {
  for (const kind of ["context", "collector", "secret"]) {
    const s = setup();
    if (kind === "context") s.ctx.waitUntil = () => { throw new Error("bad context"); };
    if (kind === "collector") delete s.env.COLLECTOR;
    if (kind === "secret") delete s.env.INGEST_TOKEN;
    assert.equal(await (await s.run(request())).text(), files["/agents/index.md"].body);
    await s.drain();
  }
});

test("agent HTML keeps CSP; markdown and JSON preserve asset content types", async () => {
  for (const path of ["/agents/page.html", "/agents/index.md", "/agents/data.json"]) {
    const s = setup();
    const res = await s.run(request(), { agentPathFor: () => path });
    assert.equal(await res.text(), files[path].body);
    assert.equal(res.headers.get("content-type"), files[path].type);
    assert.equal(res.headers.get("content-security-policy"), CSP);
    await s.drain();
  }
});

test("API proxy and read-only refusal bypass edge routing and observation", async (t) => {
  const s = setup();
  s.env.API_ORIGIN = "https://api.example.test";
  const upstream = () => new Response("api bytes", { status: 203, headers: { "x-api": "unchanged", "cache-control": "no-store" } });
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url) => { calls.push(url); return upstream(); });
  const res = await worker.fetch(request("GPTBot", "/api/view/runs?view=human"), s.env, s.ctx);
  assert.deepEqual(await snapshot(res), await snapshot(upstream()));
  assert.deepEqual(calls, ["https://api.example.test/api/view/runs?view=human"]);
  const refusal = await worker.fetch(new Request(BASE + "/api/runs", { method: "POST" }), s.env, s.ctx);
  assert.equal(refusal.status, 405);
  assert.equal((await refusal.json()).error, "read_only");
  assert.deepEqual(s.fetched, []);
  assert.deepEqual(s.posts, []);
  assert.equal(s.pending.length, 0);
});

test("future event keeps real site and path, no private request data", async () => {
  const s = setup();
  await s.run(request("GPTBot", "/?credential=private", { cookie: "private=1", "cf-connecting-ip": "192.0.2.1", authorization: "private" }));
  await s.drain();
  const { url, init } = s.posts[0];
  assert.equal(url, "https://aquarium.internal/api/aquarium/edge");
  assert.equal(init.method, "POST");
  assert.deepEqual(init.headers, { "Content-Type": "application/json", Authorization: "Bearer test-only" });
  const event = JSON.parse(init.body);
  assert.deepEqual(Object.keys(event).sort(), ["schemaVersion", "siteId", "sessionId", "source", "eventType", "path", "method", "identity"].sort());
  assert.equal(event.siteId, "sentilab");
  assert.equal(event.path, "/");
  assert.equal(event.identity.operator, "openai");
  assert.equal(event.identity.label, "GPTBot · declared");
  assert.equal(event.identity.triage.class, "declared_agent");
  assert.match(event.sessionId, /^[a-f0-9-]{36}$/);
  assert.deepEqual(event.identity.observation, { category: "training_crawler", service: "openai.gptbot", verification: "claimed" });
  assert.equal(/private|192\.0\.2\.1|credential|user-agent|authorization|cookie/i.test(init.body), false);
  for (const path of ["/unknown-private-id", "/sentilab/lab.js"]) {
    const quiet = setup();
    await quiet.run(request("GPTBot", path));
    await quiet.drain();
    assert.equal(quiet.posts.length, 0);
  }
  for (const path of ["/sentilab/", "/sentilab/package/"]) {
    const realPath = setup();
    await realPath.run(request("GPTBot", path));
    await realPath.drain();
    assert.equal(JSON.parse(realPath.posts[0].init.body).path, path);
  }
});

test("aquarium is off by default and only exact on enables background posts", async () => {
  for (const flag of [undefined, "off", "ON", "true", true, " on ", ""]) {
    const s = setup();
    s.env.AQUARIUM_POST = flag;
    assert.equal(await (await s.run(request())).text(), files["/agents/index.md"].body);
    assert.equal(s.pending.length, 0);
    assert.equal(s.posts.length, 0);
  }
  const config = readFileSync(new URL("../wrangler.jsonc", import.meta.url), "utf8");
  assert.match(config, /"AQUARIUM_POST": "off"/);
});

async function signedRequest(signer = "https://chatgpt.com") {
  // Fresh private key stays in memory; the package's supplied fixture only tests an unverified claim.
  const pair = await crypto.subtle.generateKey({ name: "Ed25519" }, false, ["sign", "verify"]);
  const jwk = await crypto.subtle.exportKey("jwk", pair.publicKey);
  const kid = createHash("sha256").update(JSON.stringify({ crv: "Ed25519", kty: "OKP", x: jwk.x })).digest("base64url");
  const now = Math.floor(Date.now() / 1000);
  const input = `("@authority" "signature-agent");created=${now};expires=${now + 60};keyid="${kid}";alg="ed25519";tag="web-bot-auth"`;
  const base = `"@authority": sentilab.aidenid.com\n"signature-agent": "${signer}"\n"@signature-params": ${input}`;
  const signature = Buffer.from(await crypto.subtle.sign("Ed25519", pair.privateKey, new TextEncoder().encode(base))).toString("base64");
  return { jwk, req: new Request(BASE + "/", { headers: { ...BROWSER, "signature-agent": `"${signer}"`,
    "signature-input": `sig1=${input}`, signature: `sig1=:${signature}:` } }) };
}

test("a valid Web Bot Auth signature routes and carries verified identity", async (t) => {
  const { jwk, req } = await signedRequest();
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, init) => {
    calls.push({ url, init });
    return Response.json({ keys: [jwk] });
  });
  const s = setup();
  assert.equal(await (await s.run(req)).text(), files["/agents/index.md"].body);
  await s.drain();
  assert.equal(calls[0].url, "https://chatgpt.com/.well-known/http-message-signatures-directory");
  const identity = JSON.parse(s.posts[0].init.body).identity;
  assert.equal(identity.verified, true);
  assert.equal(identity.basis, "web_bot_auth");
  assert.equal(identity.triage.class, "verified_agent");
  assert.equal(identity.operator, "openai");
  assert.equal(identity.status, "verified");
  assert.deepEqual(identity.observation, { category: "ai_agent", service: "openai.chatgpt-agent", verification: "signature" });
});

test("a valid generic signature proves a signer, not an operator", async (t) => {
  const { jwk, req } = await signedRequest("https://agent.example.org");
  t.mock.method(globalThis, "fetch", async () => Response.json({ keys: [jwk] }));
  const s = setup();
  assert.equal(await (await s.run(req)).text(), files["/agents/index.md"].body);
  await s.drain();
  const identity = JSON.parse(s.posts[0].init.body).identity;
  assert.equal(identity.operator, "unknown");
  assert.equal(identity.triage.class, "signed_agent");
  assert.equal(identity.observation.service, null);
});

test("signature directory failure or timeout fails toward the human page", { timeout: 2000 }, async (t) => {
  for (const mode of ["reject", "timeout"]) {
    const { req } = await signedRequest();
    let signal;
    const mocked = t.mock.method(globalThis, "fetch", async (url, init) => {
      signal = init.signal;
      if (mode === "reject") throw new Error("unavailable");
      return new Promise(() => {});
    });
    const s = setup();
    assert.deepEqual(new Uint8Array(await (await s.run(req)).arrayBuffer()), HUMAN);
    assert.equal(s.pending.length, 0);
    if (mode === "timeout") assert.equal(signal.aborted, true);
    mocked.mock.restore();
  }
});

test("the shipped unverified signature fixture stays a declared claim", async () => {
  const s = setup();
  const res = await s.run(new Request(BASE + "/", { headers: { ...BROWSER,
    "Signature-Agent": '"https://chatgpt.com"',
    "Signature-Input": 'sig1=("@authority" "signature-agent");created=1;keyid="k";alg="ed25519";tag="web-bot-auth"',
    Signature: "sig1=:AAAA:",
  } }));
  assert.equal(await res.text(), files["/agents/index.md"].body);
  await s.drain();
  assert.equal(JSON.parse(s.posts[0].init.body).identity.verified, false);
});

test("vendored bytes match pinned provenance and generated runtime matches unchanged sources", () => {
  const vendor = new URL("../src/vendor/aidenid-classifier/", import.meta.url);
  const manifest = JSON.parse(readFileSync(new URL("VENDORED.json", vendor)));
  assert.equal(manifest.commit, "09b2ff466d0fadcb83b09b0f6f213d13f430c9e1");
  assert.equal(manifest.source, "packages/aidenid-classifier");
  assert.ok(Array.isArray(manifest.files), "classifier provenance files must be ordered path/sha256 records");
  assert.deepEqual(manifest.files.map(({ path }) => path).sort(), readdirSync(new URL("src/", vendor)).map((name) => `src/${name}`).sort());
  for (const { path, sha256 } of manifest.files) {
    const source = readFileSync(new URL(path, vendor));
    assert.equal(createHash("sha256").update(source).digest("hex"), sha256, path);
    if (path.endsWith(".d.mts")) continue;
    const expected = path.endsWith(".ts") ? stripTypeScriptTypes(source.toString(), { mode: "strip" }) : source.toString();
    const generated = new URL(`../src/generated/aidenid-classifier/${path.slice(4).replace(/\.ts$/, ".js")}`, import.meta.url);
    assert.equal(readFileSync(generated, "utf8"), expected, `generated ${path}`);
  }
  const config = readFileSync(new URL("../wrangler.jsonc", import.meta.url), "utf8");
  assert.match(config, /"binding": "COLLECTOR", "service": "aidenid-aquarium"/);
  const registry = new URL("../src/vendor/aidenid-registry/", import.meta.url);
  const provenance = JSON.parse(readFileSync(new URL("VENDORED.json", registry)));
  assert.equal(provenance.commit, manifest.commit);
  assert.equal(createHash("sha256").update(readFileSync(new URL("agent-registry.mjs", registry))).digest("hex"), provenance.files["agent-registry.mjs"]);
});
