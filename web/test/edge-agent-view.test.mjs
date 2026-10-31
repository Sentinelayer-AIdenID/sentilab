import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import worker from "../src/worker.js";
import { withEdge } from "../src/edge.js";
import { classifyRequest } from "../src/generated/aidenid-classifier/index.js";

const BASE = "https://sentilab.aidenid.com";
const pages = { "/": "/agents/index.md", "/sentilab/": "/agents/index.md", "/sentilab/package/": "/agents/physics.md" };
function setup() {
  const calls = [];
  const env = { ASSETS: { async fetch(req) {
    const path = new URL(req.url).pathname;
    calls.push(path);
    return new Response(req.method === "HEAD" ? null : `bytes:${path}`, {
      headers: { "content-type": "application/octet-stream", vary: "Accept-Encoding" },
    });
  } } };
  return { calls, env };
}
const request = (path, headers, method = "GET") => new Request(BASE + path, { headers, method });
function privateHeaders(response) {
  assert.equal(response.headers.get("cache-control"), "private, no-store");
  const vary = response.headers.get("vary").toLowerCase().split(/,\s*/);
  for (const name of ["accept", "accept-encoding", "user-agent", "cookie", "signature", "signature-input", "signature-agent"]) {
    assert.equal(vary.filter((value) => value === name).length, 1, name);
  }
  assert.ok(response.headers.has("content-security-policy"));
}

test("classified agents use forge paths and types regardless of Accept", async () => {
  for (const [path, alternate] of Object.entries(pages)) {
    for (const accept of ["text/html", "application/json", "*/*"]) {
      for (const method of ["GET", "HEAD"]) {
        const s = setup();
        const res = await worker.fetch(request(path, { "user-agent": "GPTBot", accept }, method), s.env);
        const target = accept === "application/json" && alternate === "/agents/index.md" ? "/agents/index.json" : alternate;
        assert.deepEqual(s.calls, [target]);
        assert.equal(await res.text(), method === "HEAD" ? "" : `bytes:${target}`);
        assert.equal(res.headers.get("content-type"), target.endsWith(".json") ? "application/json; charset=utf-8" : "text/markdown; charset=utf-8");
        privateHeaders(res);
      }
    }
  }
});

test("requests without User-Agent classify as automation and get the agent version", async () => {
  for (const [path, alternate] of Object.entries(pages)) {
    for (const headers of [{}, { accept: "text/html" }]) {
      const s = setup();
      const req = request(path, headers);
      assert.equal(req.headers.has("user-agent"), false);
      assert.equal(classifyRequest(req).triage.class, "automation");
      const res = await worker.fetch(req, s.env);
      assert.deepEqual(s.calls, [alternate]);
      assert.equal(await res.text(), `bytes:${alternate}`);
      privateHeaders(res);
    }
  }
});

test("unclassified requests retain forge Accept negotiation and direct index", async () => {
  for (const [path, accept, target, type] of [
    ["/", "text/markdown", "/agents/index.md", "text/markdown; charset=utf-8"],
    ["/sentilab/", "application/json", "/agents/index.json", "application/json; charset=utf-8"],
    ["/sentilab/package/", "text/markdown", "/agents/physics.md", "text/markdown; charset=utf-8"],
    ["/", "text/html,text/markdown", "/", "application/octet-stream"],
    ["/", "text/html;q=1,application/json;q=0.5", "/", "application/octet-stream"],
    ["/agents/", "text/html", "/agents/index.md", "text/markdown; charset=utf-8"],
    ["/agents", "*/*", "/agents/index.md", "text/markdown; charset=utf-8"],
    ["/unmapped", "text/markdown", "/unmapped", "application/octet-stream"],
  ]) {
    const s = setup();
    const res = await worker.fetch(request(path, { "user-agent": "unrecognized-client", accept }), s.env);
    assert.deepEqual(s.calls, [target]);
    assert.equal(await res.text(), `bytes:${target}`);
    assert.equal(res.headers.get("content-type"), type);
    if (target === "/") assert.equal(res.headers.get("link"), '</agents/>; rel="alternate"; type="text/markdown"');
    if (pages[path]) privateHeaders(res);
    else {
      assert.equal(res.headers.get("vary"), "Accept-Encoding");
      assert.equal(res.headers.get("cache-control"), null);
    }
  }
});

test("human query and cookie override classification and Accept negotiation", async () => {
  for (const path of Object.keys(pages)) {
    for (const ua of ["GPTBot", "unrecognized-client"]) {
      for (const query of [true, false]) {
        const s = setup();
        const headers = { "user-agent": ua, accept: "application/json,text/markdown" };
        if (!query) headers.cookie = "sl_view=human";
        const res = await worker.fetch(request(path + (query ? "?view=human" : ""), headers), s.env);
        assert.deepEqual(s.calls, [path]);
        assert.equal(await res.text(), `bytes:${path}`);
        if (query) assert.ok(res.headers.getSetCookie().includes("sl_view=human; Max-Age=1800; Path=/; Secure; SameSite=Lax"));
        privateHeaders(res);
      }
    }
  }
});

test("classifier and routing failures bypass Accept negotiation", async () => {
  for (const mode of ["classifier", "seam", "asset"]) {
    const s = setup();
    let negotiations = 0;
    const res = await withEdge(request("/", { "user-agent": "GPTBot", accept: "application/json" }), s.env, {}, {
      classifier() {
        if (mode === "classifier") throw new Error("classification failed");
        return { triage: { class: "declared_agent" } };
      },
      agentPathFor() {
        if (mode === "seam") throw new Error("seam failed");
        return "/agents/index.md";
      },
      serveHuman: (req) => s.env.ASSETS.fetch(req),
      serveAgent: async () => new Response("missing", { status: 404 }),
      serve: async () => { negotiations++; return new Response("negotiated agent"); },
    });
    assert.equal(await res.text(), "bytes:/");
    assert.equal(negotiations, 0, mode);
  }
});

test("failed classified asset falls back to the requested human page", async () => {
  const s = setup();
  const fetch = s.env.ASSETS.fetch;
  s.env.ASSETS.fetch = (req) => new URL(req.url).pathname.startsWith("/agents/")
    ? new Response("not yet deployed", { status: 404 }) : fetch(req);
  const res = await worker.fetch(request("/sentilab/", { "user-agent": "GPTBot", accept: "application/json" }), s.env);
  assert.equal(res.status, 200);
  assert.equal(await res.text(), "bytes:/sentilab/");
  privateHeaders(res);
});

test("classified conditional requests keep the alternate asset 304", async () => {
  const s = setup();
  s.env.ASSETS.fetch = async (req) => {
    s.calls.push(new URL(req.url).pathname);
    assert.equal(req.headers.get("if-none-match"), '"alternate"');
    return new Response(null, { status: 304, headers: { etag: '"alternate"', vary: "Accept-Encoding" } });
  };
  const res = await worker.fetch(request("/sentilab/", { "user-agent": "GPTBot", accept: "text/html", "if-none-match": '"alternate"' }), s.env);
  assert.deepEqual(s.calls, ["/agents/index.md"]);
  assert.equal(res.status, 304);
  assert.equal(await res.text(), "");
  assert.equal(res.headers.get("etag"), '"alternate"');
  privateHeaders(res);
});

test("forge modules pin the exact PR 66 head 609d339d bytes", () => {
  for (const [name, hash] of Object.entries({
    "agent-paths.js": "cc43963e0b71c36320ec9ec91cacbc9cb291279c4ec87f8818c673aeb5836cb2",
    "agent-view.js": "ae48a726abfd64eb9ce28e17312e9bae320067e0b27ba982040f54b7070f104d",
  })) {
    const source = readFileSync(new URL(`../src/${name}`, import.meta.url));
    assert.equal(createHash("sha256").update(source).digest("hex"), hash, name);
  }
});

test("unmapped paths keep their headers; only a human query makes them private and sets a cookie", async () => {
  for (const path of ["/unmapped", "/agents/", "/sentilab/package/index.html"]) {
    for (const ua of ["GPTBot", "unrecognized-client"]) {
      for (const mode of ["plain", "cookie", "query"]) {
        const s = setup();
        const headers = { "user-agent": ua, accept: "text/html" };
        if (mode === "cookie") headers.cookie = "sl_view=human";
        const res = await worker.fetch(request(path + (mode === "query" ? "?view=human" : ""), headers), s.env);
        assert.deepEqual(s.calls, [path === "/agents/" ? "/agents/index.md" : path]);
        if (mode === "query") {
          privateHeaders(res);
          assert.ok(res.headers.getSetCookie().some((value) => value.startsWith("sl_view=human;")));
        } else {
          assert.equal(res.headers.get("vary"), "Accept-Encoding");
          assert.equal(res.headers.get("cache-control"), null);
          assert.equal(res.headers.get("set-cookie"), null);
        }
      }
    }
  }
});

test("classified non-read methods get the normal asset without private edge headers", async () => {
  for (const method of ["POST", "PUT", "OPTIONS", "DELETE"]) {
    const s = setup();
    const res = await worker.fetch(request("/", { "user-agent": "GPTBot", accept: "application/json" }, method), s.env);
    assert.deepEqual(s.calls, ["/"]);
    assert.equal(await res.text(), "bytes:/");
    assert.equal(res.headers.get("vary"), "Accept-Encoding");
    assert.equal(res.headers.get("cache-control"), null);
  }
});
