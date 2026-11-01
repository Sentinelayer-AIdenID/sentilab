// node --test web/test/door-hold.test.mjs
// Warden's HOLD on PR #82 at 75aed822, item by item:
//   P2   search and link-preview crawlers keep exactly what main serves (no wall, no noindex); AI agents still meet it;
//   P3-1 a cross-site form post is refused before any allowance is spent;
//   P3-2 minting has a per-prefix limit;
//   P3-3 the public /api proxy passes the intake's open feeds (board, results, events) on without any declared operator;
//   P3-4 the seven mutants that survived: the read limiters on status, the ENGRAM board read and arrivals; redirect
//        "manual"; the https-only API origin; the token's and the wall's binding to the URL's host;
//   P3-5 the contract's number grammar (no 18000.0, 1.75e4 or 0e0 where an integer is due) and r of 2 or more as
//        schema_invalid;
//   deploy: a staging environment of its own that cannot reach the production API.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { indexOrPreviewCrawler } from "../src/generated/aidenid-intent-gate/agent-resources.js";
import { LIMITS } from "../src/door/door.js";
import { verifyToken } from "../src/door/token.js";
import { BASE, BROWSER, KEY, REF, RUN, TERMS, UA, agent, file, installApi, mint, postForm, postJson, same, setup } from "./door-harness.mjs";

const submits = (calls) => calls.filter((c) => c.method === "POST" && c.path === "/api/open/v1/door/submit");
const arrivals = (calls) => calls.filter((c) => c.path === "/api/open/v1/door/arrival");
const CRAWLERS = {
  Googlebot: "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
  bingbot: "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
  Slackbot: "Slackbot-LinkExpanding 1.0 (+https://api.slack.com/robots)",
  Twitterbot: "Twitterbot/1.0",
  Discordbot: "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)",
  LinkedInBot: "LinkedInBot/1.0 (compatible; Mozilla/5.0; Apache-HttpClient +http://www.linkedin.com)",
};
// A rate-limit binding that refuses keys starting with the given prefix and records every key it sees.
const denying = (prefix, seen = []) => ({ limit: async ({ key }) => { seen.push(key); return { success: !key.startsWith(prefix) }; } });

// ── P2: crawlers ───────────────────────────────────────────────────────────────────────────────────────────────────
test("P2: search and link-preview crawlers get exactly main's response on the mapped pages; AI agents still get the wall", async (t) => {
  const calls = installApi(t);
  for (const [name, ua] of Object.entries(CRAWLERS)) {
    assert.ok(indexOrPreviewCrawler(ua), `${name} is one of the gate's index or preview crawlers`);
    for (const path of ["/", "/sentilab/", "/sentilab/package/"]) {
      const open = await setup().go(path, agent(ua));
      const main = await setup({ DOOR_TOKEN_KEY: undefined }).go(path, agent(ua));   // the door closed: main's path
      assert.ok(same(open.bytes, main.bytes), `${name} ${path}: the same bytes as main`);
      assert.deepEqual([...open.headers], [...main.headers], `${name} ${path}: the same headers as main`);
      assert.ok(!/noindex/i.test(open.text) && !(open.headers.get("x-robots-tag") ?? "").includes("noindex"), `${name} ${path}: no noindex`);
      assert.ok(!/what are you here to do\?/i.test(open.text), `${name} ${path}: no wall`);
    }
  }
  assert.equal(arrivals(calls).length, 0, "crawlers are not counted as arrivals at the door");
  for (const ua of [UA.gptbot, UA.chatgptUser, UA.claudebot, UA.curl]) {
    assert.ok(!indexOrPreviewCrawler(ua));
    assert.match((await setup().go("/", agent(ua))).text, /what are you here to do\?/);
  }
});

// ── P3-1: cross-site forms ─────────────────────────────────────────────────────────────────────────────────────────
test("P3-1: a form post must come from this site's own page; a cross-site one is refused before any allowance is spent", async (t) => {
  const calls = installApi(t);
  const token = await mint();
  const body = `t=${token}&l=${encodeURIComponent(REF)}&terms=${encodeURIComponent(TERMS)}`;
  const form = (headers) => ({ method: "POST", headers: { "content-type": "application/x-www-form-urlencoded", "user-agent": BROWSER["user-agent"], ...headers }, body });
  for (const headers of [{ "sec-fetch-site": "cross-site", origin: "https://evil.example" }, { "sec-fetch-site": "cross-site", origin: BASE },
    { "sec-fetch-site": "same-site", origin: "https://staging.sentilab.aidenid.com" }, { origin: "https://evil.example" }, {}, { origin: "null" }]) {
    const seen = [];
    const s = setup({ DOOR_IP_LIMITER: denying("never", seen), DOOR_NONCE_LIMITER: denying("never", seen) });
    const r = await s.go("/agents/submit", form(headers));
    assert.equal(r.status, 403, JSON.stringify(headers));
    assert.ok(/<h1>Not sent<\/h1>/.test(r.text) && r.text.includes("Nothing was sent.") && r.text.includes("own confirm page"));
    assert.deepEqual(seen, [], "no rate allowance is spent on a cross-site form");
  }
  assert.deepEqual(submits(calls), []);
  for (const headers of [{ "sec-fetch-site": "same-origin", origin: BASE }, { "sec-fetch-site": "none" }, { origin: BASE }]) {
    assert.equal((await setup().go("/agents/submit", form(headers))).status, 200, JSON.stringify(headers));
  }
  // JSON is never a simple cross-site request (it needs a preflight the door does not answer), so it keeps no check.
  assert.equal((await setup().go("/agents/submit", postJson({ t: token, layout: REF }, { origin: "https://evil.example" }))).status, 202);
});

// ── P3-2: minting ──────────────────────────────────────────────────────────────────────────────────────────────────
test("P3-2: minting has a per-prefix allowance; another prefix keeps its own", async (t) => {
  installApi(t);
  const s = setup();
  const statuses = [];
  for (let i = 0; i < LIMITS.DOOR_MINT_LIMITER.limit + 5; i += 1) {
    statuses.push((await s.go("/agents/intent?purpose=place-chiplets", agent(UA.curl, { accept: "application/json", "cf-connecting-ip": `198.51.100.${i % 200}` }))).status);
  }
  assert.deepEqual([statuses.filter((x) => x === 200).length, statuses.filter((x) => x === 429).length], [LIMITS.DOOR_MINT_LIMITER.limit, 5]);
  const limited = await s.go("/agents/intent?purpose=place-chiplets", agent(UA.curl, { accept: "application/json", "cf-connecting-ip": "198.51.100.7" }));
  assert.deepEqual([limited.status, JSON.parse(limited.text).error, limited.headers.get("retry-after")], [429, "rate_limited", "60"]);
  assert.equal((await s.go("/agents/intent?purpose=place-chiplets", agent(UA.curl, { "cf-connecting-ip": "192.0.2.9" }))).status, 200);
  // With the binding present, it is the one asked, keyed by the client's prefix.
  const seen = [];
  await setup({ DOOR_MINT_LIMITER: denying("never", seen) }).go("/agents/intent?purpose=read", agent(UA.curl, { "cf-connecting-ip": "203.0.113.5" }));
  assert.deepEqual(seen, ["mint:203.0.113.0/24"]);
});

// ── P3-3: the declared operator stays with the intake ─────────────────────────────────────────────────────────────
test("P3-3: the public proxy passes the intake's board, results and events on without any declared operator", async (t) => {
  const feed = { schema: "sentilab-door-board/1", operator: "openai", top: [{ class: "declared_agent", operator: "anthropic", short_id: "ab12", label: "declared_agent · ab12" }],
    events: [{ kind: "arrival", operator: "google", body: { operator: "meta", class: "automation" } }], items: [{ result: { operator: "x", metric_id: "m" } }] };
  const answers = { "/api/open/v1/door/board": feed, "/api/open/v1/door/results": feed, "/api/open/v1/door/events": feed };
  t.mock.method(globalThis, "fetch", async (input) => {
    const path = new URL(String(input)).pathname;
    if (path === "/api/open/v1/door/events" && String(input).includes("bad=1")) return new Response("not json", { status: 200 });
    if (answers[path]) return Response.json(answers[path], { headers: { "content-length": "999", etag: '"x"' } });
    return Response.json({ operator: "openai", untouched: true });
  });
  const s = setup();
  for (const path of Object.keys(answers)) {
    const r = await s.go(`${path}?after=0`);
    assert.equal(r.status, 200);
    // Only the arrival record keeps its recognised lab (an OPERATORS value, Carter #58250); nothing else carries one.
    assert.ok(!/openai|anthropic|meta/.test(r.text) && (r.text.match(/"operator"/g) ?? []).length === 1, `${path}: ${r.text}`);
    const value = JSON.parse(r.text);
    assert.equal(value.events[0].operator, "google");
    assert.ok(!("operator" in value.events[0].body) && !("operator" in value) && !("operator" in value.top[0]));
    assert.deepEqual([value.top[0].short_id, value.top[0].label, value.events[0].body.class, value.items[0].result.metric_id], ["ab12", "declared_agent · ab12", "automation", "m"]);
    assert.equal(r.headers.get("etag"), null);
  }
  // A feed answer the proxy cannot read is not passed on; other API paths are untouched.
  assert.deepEqual([(await s.go("/api/open/v1/door/events?bad=1")).status], [502]);
  assert.equal(JSON.parse((await s.go("/api/view/runs")).text).operator, "openai");
});

// ── root's rollback finding (18:40Z): the intake's internal pass handles never leave through the proxy ────────────
test("the public proxy drops pass_handle and visitor_handle at any depth on every open feed", async (t) => {
  const leaky = { schema: "x", pass_handle: "a".repeat(64), visitor_handle: "b".repeat(64),
    events: [{ kind: "arrival", class: "declared_agent", operator: "openai", pass_handle: "c".repeat(64),
      declaration: { name: "n", visitor_handle: "d".repeat(64) } }, { kind: "run", visit_arrival: 3, nested: [{ pass_handle: "e".repeat(64) }] }],
    items: [{ event_kind: "declaration", visitor_handle: "f".repeat(64), arrival: 1 }] };
  const paths = ["board", "results", "events", "visitors", "stats"].map((name) => `/api/open/v1/door/${name}`);
  t.mock.method(globalThis, "fetch", async () => Response.json(leaky));
  const s = setup();
  for (const path of paths) {
    const r = await s.go(`${path}?after=0`);
    assert.equal(r.status, 200, path);
    assert.ok(!/pass_handle|visitor_handle|aaaa|bbbb|cccc|dddd|eeee|ffff/.test(r.text), `${path}: ${r.text}`);
    const value = JSON.parse(r.text);
    assert.deepEqual([value.events[0].operator, value.events[0].declaration.name, value.events[1].visit_arrival, value.items[0].arrival],
      ["openai", "n", 3, 1], path);
  }
});

// ── P3-4: the seven surviving mutants ──────────────────────────────────────────────────────────────────────────────
test("P3-4: the read limiter guards status: a refused prefix gets 429 and the intake is not asked", async (t) => {
  const calls = installApi(t);
  const token = await mint();
  const r = await setup({ DOOR_READ_LIMITER: denying("status:") }).go(`/agents/status/${RUN}?t=${token}`, agent());
  assert.deepEqual([r.status, JSON.parse(r.text).error], [429, "rate_limited"]);
  assert.deepEqual(calls.filter((c) => c.path.startsWith("/api/open/v1/door/status/")), []);
});

test("P3-4: the read limiter guards the ENGRAM view's board read: refused, the view still answers without asking", async (t) => {
  const calls = installApi(t);
  const token = await mint();
  const view = JSON.parse((await setup({ DOOR_READ_LIMITER: denying("engram:") }).go(`/agents/engram?t=${token}`, agent())).text);
  assert.deepEqual([view.schema, view.board_status, view.token.cpu_s_left], ["sentilab-agent-view/1", "unavailable", null]);
  assert.deepEqual(calls.filter((c) => c.headers["x-door-nonce"]), [], "no board read with this token's nonce");
});

test("P3-4: the read limiter guards arrivals: a refused prefix posts none", async (t) => {
  const calls = installApi(t);
  const s = setup({ DOOR_READ_LIMITER: denying("arrival:") });
  await s.go("/agents/intent?purpose=place-chiplets", agent());
  await s.go("/", agent());
  await s.drain();
  assert.deepEqual(arrivals(calls), []);
  const open = setup();
  await open.go("/agents/intent?purpose=place-chiplets", agent());
  await open.drain();
  assert.equal(arrivals(calls).length, 1, "the control: without the refusal the arrival is posted");
});

test("P3-4: every call the door makes to the intake refuses redirects (redirect: manual)", async (t) => {
  const calls = installApi(t, { submit: async () => new Response(null, { status: 307, headers: { location: "https://evil.example/collect" } }) });
  const s = setup();
  const token = await mint();
  await s.go(`/agents/engram?t=${token}`, agent());
  await s.go(`/agents/status/${RUN}?t=${token}`, agent());
  const r = await s.go("/agents/submit", postJson({ t: token, layout: REF }));
  await s.go("/agents/intent?purpose=read", agent());
  await s.drain();
  assert.ok(calls.length >= 5);
  assert.deepEqual([...new Set(calls.map((c) => c.redirect))], ["manual"]);
  assert.equal(JSON.parse(r.text).error, "delivery_unknown", "a redirect is not the intake's answer");
  assert.ok(!calls.some((c) => c.origin === "https://evil.example"));
});

test("P3-4: the intake is reached only over https (or a loopback stub): a plain-http origin is never called", async (t) => {
  const calls = installApi(t);
  const token = await mint();
  const s = setup({ API_ORIGIN: "http://sentilab-api.example.test" });
  const view = JSON.parse((await s.go(`/agents/engram?t=${token}`, agent())).text);
  const r = await s.go("/agents/submit", postJson({ t: token, layout: REF }));
  await s.go("/agents/intent?purpose=read", agent());
  await s.drain();
  assert.deepEqual(calls, [], "nothing at all was sent to a plain-http origin");
  assert.deepEqual([view.board_status, r.status, JSON.parse(r.text).error], ["unavailable", 503, "intake_unavailable"]);
  const local = setup({ API_ORIGIN: "http://127.0.0.1:8787" });
  await local.go(`/agents/engram?t=${token}`, agent());
  assert.ok(calls.some((c) => c.origin === "http://127.0.0.1:8787"), "the loopback stub for local runs is allowed");
});

test("P3-4: a minted token is bound to the URL's host, never to x-forwarded-host", async (t) => {
  installApi(t);
  const r = await setup().go("/agents/intent?purpose=read", agent(UA.curl, { accept: "application/json", "x-forwarded-host": "evil.example", host: "evil.example" }));
  const minted = JSON.parse(r.text).t;
  assert.equal((await verifyToken(KEY, minted, { site: "sentilab.aidenid.com", now: Date.now() })).ok, true);
  assert.equal((await verifyToken(KEY, minted, { site: "evil.example", now: Date.now() })).ok, false);
  assert.ok(JSON.parse(r.text).next.every((n) => n.url.startsWith(`${BASE}/`)));
});

test("P3-4: the wall opens only for a token of the URL's host, whatever x-forwarded-host says", async (t) => {
  installApi(t);
  const foreign = await mint("read", { site: "evil.example" });
  const r = await setup().go(`/?t=${foreign}`, agent(UA.gptbot, { "x-forwarded-host": "evil.example" }));
  assert.match(r.text, /what are you here to do\?/);
  const own = await mint("read");
  assert.ok(same((await setup().go(`/?t=${own}`, agent(UA.gptbot, { "x-forwarded-host": "evil.example" }))).bytes, file("agents/index.md")));
});

// ── P3-5: the contract's number grammar and rotation enum, end to end ─────────────────────────────────────────────
test("P3-5: float literals where an integer is due, and r of 2 or more, are refused like the intake refuses them", async (t) => {
  const calls = installApi(t);
  const s = setup();
  const token = await mint();
  const dies = (x) => `[${[`{"die":0,"x_um":${x},"y_um":17500,"rot_deg":0}`, ...REF.split(",").slice(1).map((item, i) => {
    const [px, py] = item.split(".");
    return `{"die":${i + 1},"x_um":${px * 500},"y_um":${py * 500},"rot_deg":0}`;
  })].join(",")}]`;
  for (const literal of ["18000.0", "1.8e4", "18E3"]) {
    const r = await s.go("/agents/submit", postJson(`{"t":"${token}","layout":${dies(literal)}}`));
    assert.deepEqual([r.status, JSON.parse(r.text).codes], [400, [{ code: "schema_invalid", path: "/layout/0/x_um", keyword: "type" }]], literal);
  }
  const zero = await s.go("/agents/submit", postJson(`{"t":"${token}","layout":${dies("18000").replace('"y_um":17500', '"y_um":0e0')}}`));
  assert.deepEqual(JSON.parse(zero.text).codes, [{ code: "schema_invalid", path: "/layout/0/y_um", keyword: "type" }]);
  for (const r of [2, 3, 9]) {
    const res = await s.go("/agents/submit", postJson({ t: token, layout: REF.replace("36.35.0", `36.35.${r}`) }));
    assert.deepEqual([res.status, JSON.parse(res.text).codes], [400, [{ code: "schema_invalid", path: "/l/0", keyword: "enum" }]]);
  }
  assert.deepEqual(submits(calls), []);
  assert.equal((await s.go("/agents/submit", postJson(`{"t":"${token}","layout":${dies("18000")}}`))).status, 202, "the integer literal goes through");
});

// ── deploy: staging of its own ─────────────────────────────────────────────────────────────────────────────────────
test("deploy: wrangler.jsonc has a staging environment with its own Worker, domain and limits, and no API to reach", () => {
  const text = readFileSync(new URL("../wrangler.jsonc", import.meta.url), "utf8");
  const config = JSON.parse(text.split("\n").map((line) => line.replace(/^\s*\/\/.*$/, "")).join("\n"));
  const staging = config.env?.staging;
  assert.equal(staging.name, "sentilab-web-staging");
  assert.deepEqual(staging.routes, [{ pattern: "staging.sentilab.aidenid.com", custom_domain: true }]);
  assert.equal(staging.vars.API_ORIGIN, "none", "staging must never reach the production API");
  assert.notEqual(config.vars.API_ORIGIN, "none");
  assert.equal(staging.vars.AQUARIUM_POST, "off");
  const names = (list) => list.map((b) => b.name).sort();
  assert.deepEqual(names(staging.ratelimits), names(config.ratelimits), "the same limiters");
  const ids = (list) => new Set(list.map((b) => b.namespace_id));
  assert.equal([...ids(staging.ratelimits)].filter((id) => ids(config.ratelimits).has(id)).length, 0, "namespaces of its own");
  for (const binding of [...config.ratelimits, ...staging.ratelimits]) {
    assert.deepEqual(binding.simple, config.ratelimits.find((b) => b.name === binding.name).simple, binding.name);
  }
  assert.deepEqual(staging.services, config.services);
});
