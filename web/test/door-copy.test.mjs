// node --test web/test/door-copy.test.mjs
// The door's copy repairs before production opens (aneta #57911, root's reply at 08:30:43Z):
//   - the terms a submission accepts are readable at a stable URL, /agents/terms, and at the contract's canonical path
//     /sentilab/open/terms/<n>@<sha256>.md, and only as bytes whose SHA-256 is the pin: the board's (the signed
//     manifest's) highest accepted version for /agents/terms, the file's own name for the canonical path. A copy whose
//     bytes differ, a missing copy, no terms on the board or no board: 503 terms_unavailable, never another text;
//   - the wall (HTML, markdown, JSON), the agent view's submissions, the confirm page and the terms-changed page link
//     the terms;
//   - the agent view's scoring states the scoring build's known limit, in root's words;
//   - no door page calls a reproduced run "independently verified";
//   - /robots.txt is served and allows the agent pages.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readdirSync } from "node:fs";
import { join } from "node:path";

import { confirmHtml, resultHtml, termsChangedHtml, wallHtml, wallJson, wallMarkdown } from "../src/door/render.js";
import { BASE, BOARD, PUBLIC, REF, agent, file, installApi, mint, setup } from "./door-harness.mjs";

const TERMS_DIR = join(PUBLIC, "sentilab", "open", "terms");
const SHA = "f11989175769a7a3410b26ecea46aac1756033ee562c792fe29a02af931899f7";
const VERSION = `sentilab-open-terms/1@${SHA}`;
const CANONICAL = `/sentilab/open/terms/1@${SHA}.md`;
const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");

const boardWith = (terms) => ({ ...BOARD, terms: { accepted_versions: terms } });
// The real assets, except that one path answers with other bytes (a tampered or replaced copy) or 404.
function assetsWith(env, path, answer) {
  const real = env.ASSETS;
  return { async fetch(request) {
    if (new URL(request.url).pathname !== path) return real.fetch(request);
    if (answer === null) return new Response("not found", { status: 404 });
    return new Response(request.method === "HEAD" ? null : answer, { status: 200, headers: { "content-type": "text/markdown" } });
  } };
}

test("the committed terms are named by their own SHA-256, and the signed manifest's pin is one of them", () => {
  const names = readdirSync(TERMS_DIR);
  assert.ok(names.length >= 1);
  for (const name of names) {
    const match = /^([1-9][0-9]{0,5})@([0-9a-f]{64})[.]md$/.exec(name);
    assert.ok(match, name);
    assert.equal(sha256(file(`sentilab/open/terms/${name}`)), match[2], `${name}: its bytes hash to its name`);
  }
  assert.ok(names.includes(`1@${SHA}.md`), "the signed manifest's terms (warden #57911 reply: 1,761 bytes)");
  assert.equal(file(CANONICAL).length, 1761);
});

test("/agents/terms serves exactly the bytes the board's highest accepted version pins", async (t) => {
  const calls = installApi(t, { board: async () => Response.json(boardWith([`sentilab-open-terms/0@${"0".repeat(64)}`, VERSION])) });
  const s = setup();
  for (const ua of ["curl/8.4.0", agent().headers["user-agent"]]) {
    const r = await s.go("/agents/terms", { headers: { "user-agent": ua } });
    assert.equal(r.status, 200);
    assert.equal(r.headers.get("content-type"), "text/markdown; charset=utf-8");
    assert.equal(r.headers.get("x-terms-version"), VERSION);
    assert.equal(sha256(r.bytes), SHA, "the served bytes hash to the pin");
    assert.deepEqual([...r.bytes], [...file(CANONICAL)]);
  }
  const head = await s.go("/agents/terms", { method: "HEAD" });
  assert.equal(head.status, 200);
  assert.equal(head.bytes.length, 0);
  assert.ok(calls.some((c) => c.path === "/api/open/v1/door/board"), "the pin comes from the intake's board");
  const post = await s.go("/agents/terms", { method: "POST" });
  assert.equal(post.status, 405);
});

test("a tampered copy is refused: 503 terms_unavailable, and its bytes never leave the Worker", async (t) => {
  installApi(t, { board: async () => Response.json(boardWith([VERSION])) });
  const original = file(CANONICAL);
  const tampered = Buffer.from(original);
  tampered[tampered.length - 2] ^= 1;
  for (const answer of [tampered, Buffer.concat([original, Buffer.from("\nOne more term.\n")]), Buffer.alloc(0), null]) {
    const s = setup();
    s.env.ASSETS = assetsWith(s.env, CANONICAL, answer);
    for (const path of ["/agents/terms", CANONICAL]) {
      const r = await s.go(path);
      assert.equal(r.status, 503, `${path} ${answer === null ? "missing" : answer.length}`);
      assert.deepEqual(JSON.parse(r.text), { error: "terms_unavailable" });
      assert.ok(!r.text.includes("terms (version 1)"), "no terms text at all");
    }
  }
});

test("no pin, no terms: no accepted version, a malformed one, or an unreachable board is 503 terms_unavailable", async (t) => {
  for (const board of [async () => Response.json(boardWith([])), async () => Response.json(boardWith(["sentilab-open-terms/1@" + SHA.slice(1)])),
    async () => Response.json({ ...BOARD, terms: undefined }), async () => new Response("down", { status: 502 }),
    async () => { throw new Error("unreachable"); }]) {
    t.mock.restoreAll();
    installApi(t, { board });
    const s = setup();
    const r = await s.go("/agents/terms");
    assert.equal(r.status, 503);
    assert.deepEqual(JSON.parse(r.text), { error: "terms_unavailable" });
  }
  // A version the board names but this site has no copy of: never another version's text, not even an older accepted one.
  for (const accepted of [[`sentilab-open-terms/2@${"ab".repeat(32)}`], [VERSION, `sentilab-open-terms/2@${"ab".repeat(32)}`]]) {
    t.mock.restoreAll();
    installApi(t, { board: async () => Response.json(boardWith(accepted)) });
    const r = await setup().go("/agents/terms");
    assert.equal(r.status, 503, accepted.join(" "));
    assert.ok(!r.text.includes("terms (version 1)"));
  }
});

test("the canonical path serves a committed version by its own name, and nothing else under it", async (t) => {
  installApi(t, { board: async () => Response.json(boardWith([])) });
  const s = setup();
  const r = await s.go(CANONICAL);
  assert.equal(r.status, 200, "readable at its own name even while no version is accepted");
  assert.equal(sha256(r.bytes), SHA);
  assert.equal(r.headers.get("x-terms-version"), VERSION);
  assert.equal(r.headers.get("content-type"), "text/markdown; charset=utf-8");
  for (const path of [`/sentilab/open/terms/2@${SHA}.md`, `/sentilab/open/terms/1@${"ab".repeat(32)}.md`]) {
    const other = await s.go(path);
    assert.equal(other.status, 503, path);
  }
});

test("the wall, the agent view, the confirm page and the terms-changed page link the terms", async (t) => {
  installApi(t, { board: async () => Response.json(boardWith([VERSION])) });
  assert.ok(wallHtml(BASE, "open").includes(`<a href="${BASE}/agents/terms">`));
  assert.ok(wallMarkdown(BASE, "closed").includes(`(${BASE}/agents/terms)`));
  assert.equal(wallJson(BASE, "unknown").terms_url, `${BASE}/agents/terms`);
  const s = setup();
  const token = await mint();
  const view = JSON.parse((await s.go(`/agents/engram?t=${token}`, agent())).text);
  assert.equal(view.submissions.terms, VERSION);
  assert.equal(view.submissions.terms_url, `${BASE}/agents/terms`);
  const claims = { purpose: "place-chiplets", short_id: "ab12", expires_at: "2026-11-01T12:00:00Z" };
  const page = confirmHtml({ claims, token, compact: REF, dies: [], violations: [], wireMm: 9.5, submissions: "open", terms: VERSION });
  assert.ok(page.includes('<a href="/agents/terms">'), "the confirm page links the terms it accepts");
  assert.ok(termsChangedHtml({ token, compact: REF, terms: VERSION, again: false }).includes('<a href="/agents/terms">'));
});

// The text's one copy is evidence.json's known_limit (agents-site.test.mjs pins it to root's words); the view reads it.
test("the agent view's scoring states the known limit, read from evidence.json", async (t) => {
  installApi(t);
  const stated = JSON.parse(file("agents/evidence.json")).known_limit;
  assert.match(stated, /^Known limit: .* Current results are diagnostic[.]$/);
  const view = JSON.parse((await setup().go(`/agents/engram?t=${await mint()}`, agent())).text);
  assert.equal(view.scoring.known_limit, stated);
  // Unreadable or without the sentence: null, never a stale copy.
  for (const answer of [null, Buffer.from("{}"), Buffer.from(JSON.stringify({ known_limit: "Everything is fine." }))]) {
    const s = setup();
    s.env.ASSETS = assetsWith(s.env, "/agents/evidence.json", answer);
    const other = JSON.parse((await s.go(`/agents/engram?t=${await mint()}`, agent())).text);
    assert.equal(other.scoring.known_limit, null);
  }
});

test("the known limit is the same sentence the Package view's Honest limits shows", () => {
  const stated = JSON.parse(file("agents/evidence.json")).known_limit;
  const html = file("sentilab/package/index.html").toString("utf8");
  const limits = html.slice(html.indexOf('<dialog id="limits"'), html.indexOf("</dialog>", html.indexOf('<dialog id="limits"')));
  assert.ok(limits.includes(`<li>${stated}</li>`), "one sentence on both surfaces");
});

test("no door page calls a run independently verified", () => {
  for (const state of ["reproduced", "cross_checked", "failed", "evaluated"]) {
    const page = resultHtml(BASE, "t", { refusal: null, state, runId: null, codes: [] });
    assert.doesNotMatch(page, /independently/i, state);
  }
  assert.match(resultHtml(BASE, "t", { refusal: null, state: "reproduced", runId: null, codes: [] }), /reproduced in a fresh process/);
});

test("/robots.txt is served and allows the agent pages", async (t) => {
  installApi(t);
  const r = await setup().go("/robots.txt", agent());
  assert.equal(r.status, 200);
  assert.match(r.headers.get("content-type"), /^text\/plain/);
  const lines = r.text.split("\n").map((line) => line.trim());
  assert.ok(lines.includes("User-agent: *"));
  for (const path of ["/agents/", "/llms.txt", "/agents.json"]) assert.ok(lines.includes(`Allow: ${path}`), path);
  assert.ok(!lines.some((line) => /^Disallow:\s*\/?\s*$/i.test(line) && line !== "Disallow:"), "nothing disallows the site");
});
