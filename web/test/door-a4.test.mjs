// AGENT-DOOR Amendment 4 rev 2 at the edge (root's #89 contract; docs/sentilab/DOOR-PRESENCE-STATS.md):
//   - the opt-in: no declaration without the visitor sending the notice version they were shown; the exact notice text
//     from GET /door/visitors on the form, in the wall's markdown and JSON, and in the agent view's declare object;
//   - ?via= only pre-fills source (the form's selected option and the declare template) and records nothing;
//   - hostile name and reason text: refused (controls, C1 included, and bidi overrides) or passed on exactly as
//     written, never echoed by the door, and never a change to the token, the check or the submission;
//   - the heartbeat proxy: exactly {page, tab, class} forwarded with fresh headers (no IP, user agent, cookie or
//     Referer), the per-IP limit in memory for at most 60 s, refusals before any call;
//   - the visitors and stats feeds pass the proxy's open-feed filter; the wall's and agent view's copy.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { BROWSER, NAMES, UA, agent, installApi, mint, postJson, setup } from "./door-harness.mjs";
import { DECLARATION_TEXT, OPT_IN_LINE, SOURCES, declareObject, displayTextProblem, noticeFrom, readOptIn, viaSource } from "../src/door/declare.js";
import { HERE_LIMIT, HERE_PAGES, HERE_PATH, hereLimiterEntries } from "../src/door/door.js";
import { HERE_LINE } from "../public/sentilab/here.mjs";
import { RECORDED } from "../src/door/render.js";

const VISITORS = JSON.parse(readFileSync(new URL("./fixtures/door-a4/visitors-measured.json", import.meta.url), "utf8"));
const NOTICE = VISITORS.notice;            // #89's own notice, as its code generated it
const V = NOTICE.version;
const ARRIVAL = "/api/open/v1/door/arrival";
const json = (extra = {}) => ({ headers: { "user-agent": UA.gptbot, accept: "application/json", ...extra } });
const md = (extra = {}) => ({ headers: { "user-agent": UA.gptbot, accept: "text/markdown", ...extra } });
const withNotice = (t, routes = {}) => installApi(t, { visitors: async () => Response.json(VISITORS), ...routes });
const arrivals = (calls) => calls.filter((c) => c.path === ARRIVAL).map((c) => c.body);
const intent = (params) => `/agents/intent?${new URLSearchParams(params)}`;
const HOSTILE = Object.freeze({
  script: "<script>alert(1)</script>", emoji: "🔥🧪 chip fan 👨\u200d👩\u200d👧", url: "https://evil.example/?t=spt1.x&q=1",
  zeroWidth: "ad\u200bmin\u200d", combining: "Zalgo\u0301\u0302\u0303", quotes: "\"'`<>&", markdown: "[click](javascript:alert(1)) **bold**",
  mix: "<img src=x onerror=alert(1)> 🔥 https://x.example/\u200b",
});
const REFUSED = Object.freeze({ nul: "a\u0000b", newline: "a\nb", tab: "a\tb", del: "a\u007fb", nel: "a\u0085b", c1: "a\u009fb",
  rlo: "a\u202eb", lre: "a\u202ab", pdf: "a\u202cb", lri: "a\u2066b", pdi: "a\u2069b" });

// ── the rules, as functions ──────────────────────────────────────────────────────────────────────────────────────
test("display text: at most the cap in code points; controls (C0, DEL, C1) and bidi embeddings, overrides and isolates refused", () => {
  assert.equal(displayTextProblem("x".repeat(64), 64), null);
  assert.equal(displayTextProblem("x".repeat(65), 64), "too_long");
  assert.equal(displayTextProblem("🔥".repeat(64), 64), null, "64 emoji are 64 code points, 128 UTF-16 units");
  assert.equal(displayTextProblem("🔥".repeat(65), 64), "too_long");
  assert.equal(displayTextProblem("x".repeat(10000), 160), "too_long");
  for (const [name, text] of Object.entries(REFUSED)) assert.equal(displayTextProblem(text, 64), "control_character", name);
  for (const cp of [0x00, 0x1f, 0x7f, 0x80, 0x9f, 0x202a, 0x202e, 0x2066, 0x2069]) {
    assert.equal(displayTextProblem(`x${String.fromCodePoint(cp)}`, 64), "control_character", cp.toString(16));
  }
  for (const cp of [0x20, 0x7e, 0xa0, 0x200b, 0x200e, 0x2029, 0x2065, 0x206a, 0x2029, 0xfeff]) {
    assert.equal(displayTextProblem(`x${String.fromCodePoint(cp)}`, 64), null, cp.toString(16));
  }
  for (const [name, text] of Object.entries(HOSTILE)) assert.equal(displayTextProblem(text, 160), null, name);
});

test("the notice is read only in its exact shape", () => {
  assert.deepEqual(noticeFrom(VISITORS), { version: V, text: NOTICE.text });
  for (const bad of [null, {}, { notice: null }, { notice: { version: V } }, { notice: { text: NOTICE.text } },
    { notice: { version: "sentilab-public-visitor/0", text: "x" } }, { notice: { version: `${V} `, text: "x" } },
    { notice: { version: V, text: "" } }, { notice: { version: V, text: "x".repeat(2001) } }, { notice: { version: V, text: "a\u0085b" } },
    { notice: { version: V, text: 7 } }, { notice: [V, "x"] }]) {
    assert.equal(noticeFrom(bad), null, JSON.stringify(bad)?.slice(0, 80));
  }
});

test("via names a source only when it is exactly one of #89's sources", () => {
  for (const source of SOURCES) assert.equal(viaSource(new URLSearchParams({ via: source })), source);
  for (const query of ["", "via=", "via=MOLTBOOK", "via=moltbook2", "via=evil", "via=moltbook&via=github", "via=moltbook%0a", "via=https://moltbook.com",
    "via=%20moltbook"]) {
    assert.equal(viaSource(new URLSearchParams(query)), null, query);
  }
  assert.deepEqual(SOURCES, ["moltbook", "senti", "github", "direct", "other"]);
});

test("an opt-in exists only when the visitor sends the notice version they were shown", () => {
  const notice = { version: V, text: NOTICE.text };
  const read = (query, n = notice) => readOptIn(new URLSearchParams(query), n);
  assert.deepEqual(read("name=a&reason=b&source=moltbook&via=moltbook"), { status: "not_given", typed: true });
  assert.deepEqual(read("via=moltbook&source=moltbook"), { status: "not_given", typed: false });
  assert.deepEqual(read(""), { status: "not_given", typed: false });
  assert.deepEqual(read(`notice_version=${encodeURIComponent(V)}`), { status: "sent", declaration: { notice_version: V } });
  assert.deepEqual(read(new URLSearchParams({ notice_version: V, name: HOSTILE.mix, reason: HOSTILE.emoji, source: "github", via: "moltbook" }).toString()),
    { status: "sent", declaration: { notice_version: V, name: HOSTILE.mix, reason: HOSTILE.emoji, source: "github" } });
  // via never fills source at the opt-in: only the visitor's own source field counts.
  assert.deepEqual(read(`notice_version=${encodeURIComponent(V)}&via=moltbook`), { status: "sent", declaration: { notice_version: V } });
  assert.deepEqual(read(`notice_version=${encodeURIComponent(V)}&name=&reason=&source=`), { status: "sent", declaration: { notice_version: V } });
  const refused = (query, code) => assert.deepEqual(read(query), { status: "not_sent", code }, query);
  refused(`notice_version=${encodeURIComponent(V)}&name=${"x".repeat(65)}`, "too_long");
  refused(`notice_version=${encodeURIComponent(V)}&reason=${"x".repeat(161)}`, "too_long");
  refused(`notice_version=${encodeURIComponent(V)}&name=a%00b`, "control_character");
  refused(`notice_version=${encodeURIComponent(V)}&reason=a%C2%85b`, "control_character");
  refused(`notice_version=${encodeURIComponent(V)}&name=a%E2%80%AEb`, "control_character");
  refused(`notice_version=${encodeURIComponent(V)}&source=MOLTBOOK`, "source_unknown");
  refused(`notice_version=${encodeURIComponent(V)}&source=https://moltbook.com`, "source_unknown");
  refused(`notice_version=${encodeURIComponent(V)}&name=a&name=b`, "field_repeated");
  refused(`notice_version=${encodeURIComponent(V)}&notice_version=${encodeURIComponent(V)}`, "field_repeated");
  refused("notice_version=sentilab-public-visitor%2F2", "notice_changed");
  refused(`notice_version=${encodeURIComponent(V)}`.replace("%2F1", "%2F1%20"), "notice_changed");
  assert.deepEqual(read(`notice_version=${encodeURIComponent(V)}&name=a`, null), { status: "not_sent", code: "notice_unavailable" });
  for (const code of ["too_long", "control_character", "source_unknown", "field_repeated", "notice_changed", "notice_unavailable"]) {
    assert.equal(typeof DECLARATION_TEXT[code], "string", code);
  }
});

// ── the wall: the notice before the opt-in, and via pre-filling source only ──────────────────────────────────────
test("the wall's JSON carries the exact notice and the declare template, with via pre-filling source only", async (t) => {
  withNotice(t);
  const { go } = setup();
  const plain = JSON.parse((await go("/agents/intent", json())).text);
  assert.equal(plain.declare.status, "available");
  assert.deepEqual(plain.declare.notice, NOTICE);
  assert.equal(plain.declare.line, OPT_IN_LINE);
  assert.deepEqual(plain.declare.fields.source, { enum: [...SOURCES], prefilled: null });
  assert.equal(plain.declare.fields.name.max_chars, 64);
  assert.equal(plain.declare.fields.reason.max_chars, 160);
  assert.equal(plain.declare.template,
    "https://sentilab.aidenid.com/agents/intent?purpose={purpose}&notice_version=sentilab-public-visitor%2F1&name={name}&reason={reason}&source={source}");
  for (const p of plain.purposes) assert.equal(new URL(p.href).searchParams.has("via"), false);
  const via = JSON.parse((await go("/agents/intent?via=moltbook", json())).text);
  assert.deepEqual(via.declare.fields.source, { enum: [...SOURCES], prefilled: "moltbook" });
  assert.match(via.declare.template, /&source=moltbook$/);
  for (const p of via.purposes) assert.equal(new URL(p.href).searchParams.get("via"), "moltbook");
  for (const p of via.purposes) assert.equal(new URL(p.href).searchParams.has("notice_version"), false, "a purpose link never opts in");
  for (const bad of ["evil", "MOLTBOOK", "moltbook&via=github"]) {
    const page = JSON.parse((await go(`/agents/intent?via=${bad}`, json())).text);
    assert.equal(page.declare.fields.source.prefilled, null, bad);
    for (const p of page.purposes) assert.equal(new URL(p.href).searchParams.has("via"), false, bad);
  }
});

test("the human form shows the notice before an unticked opt-in, and via selects the source", async (t) => {
  withNotice(t, { visitors: async () => Response.json({ ...VISITORS, notice: { version: V, text: `${NOTICE.text} <i>escaped</i>` } }) });
  const { go } = setup();
  const page = (await go("/agents/intent?via=moltbook", { headers: BROWSER })).text;
  const notice = page.indexOf("&#60;i&#62;escaped&#60;/i&#62;");
  const optIn = page.indexOf('name="notice_version"');
  assert.ok(notice > 0 && optIn > notice, "the notice comes before the opt-in");
  assert.ok(!page.includes("<i>escaped</i>"));
  assert.match(page, /<input type="checkbox" name="notice_version" value="sentilab-public-visitor\/1">/, "unticked: no checked attribute");
  assert.ok(!/notice_version"[^>]*checked/.test(page));
  assert.match(page, /<input type="text" name="name" maxlength="64"/);
  assert.match(page, /<input type="text" name="reason" maxlength="160"/);
  assert.match(page, /<option value="moltbook" selected>/);
  assert.equal((page.match(/ selected>/g) ?? []).length, 1);
  assert.match(page, /<input type="hidden" name="via" value="moltbook">/);
  assert.ok(page.includes(OPT_IN_LINE));
  const plain = (await go("/agents/intent", { headers: BROWSER })).text;
  assert.ok(!plain.includes(" selected>"));
  assert.ok(!plain.includes('name="via"'));
});

test("without a readable notice the wall offers no opt-in and the purpose step accepts none", async (t) => {
  for (const visitors of [async () => new Response("not found", { status: 404 }), async () => Response.json({ notice: { version: V } }),
    async () => new Response("<html>", { status: 200 }), async () => { throw new Error("down"); }]) {
    const calls = installApi(t, { visitors });
    const { go, drain } = setup();
    const wall = JSON.parse((await go("/agents/intent?via=moltbook", json())).text);
    assert.equal(wall.declare.status, "unavailable");
    assert.equal(wall.declare.notice, undefined);
    assert.ok(!(await go("/agents/intent", { headers: BROWSER })).text.includes('name="notice_version"'));
    const token = JSON.parse((await go(intent({ purpose: "read", notice_version: V, name: "x" }), json())).text);
    assert.deepEqual(token.declaration, { status: "not_sent", code: "notice_unavailable", detail: DECLARATION_TEXT.notice_unavailable });
    await drain();
    for (const body of arrivals(calls)) assert.equal(body.declaration, undefined);
    t.mock.restoreAll();
  }
});

test("the wall's markdown quotes the notice and how to opt in", async (t) => {
  withNotice(t);
  const { go } = setup();
  const text = (await go("/agents/intent?via=github", md())).text;
  assert.ok(text.includes(`> ${NOTICE.text}`));
  assert.ok(text.includes(OPT_IN_LINE));
  assert.ok(text.includes("notice_version=sentilab-public-visitor%2F1"));
  assert.ok(text.includes("&source=github"));
  assert.match(text, /\(https:\/\/sentilab\.aidenid\.com\/agents\/intent\?purpose=place-chiplets&via=github\)/);
});

// ── the purpose step: the opt-in, exactly as written, never echoed ───────────────────────────────────────────────
test("no declaration without the opt-in: typed fields and via alone record nothing", async (t) => {
  const calls = withNotice(t);
  const { go, drain } = setup();
  for (const params of [{ purpose: "read" }, { purpose: "read", via: "moltbook" }, { purpose: "read", name: "x", reason: "y", source: "moltbook" },
    { purpose: "read", name: "x", via: "moltbook", source: "moltbook" }]) {
    const res = await go(intent(params), json());
    assert.equal(res.status, 200);
    const typed = Boolean(params.name);
    assert.deepEqual(JSON.parse(res.text).declaration, typed ? { status: "not_given", detail: DECLARATION_TEXT.not_opted_in } : { status: "not_given" });
  }
  await drain();
  const bodies = arrivals(calls);
  assert.equal(bodies.length, 4);
  for (const body of bodies) assert.deepEqual(Object.keys(body).sort(), ["class", "nonce", "operator", "purpose"]);
  // A landing with via records exactly what a landing without it records.
  const without = setup();
  const before = calls.length;
  await without.go("/", agent());
  await without.go("/?via=moltbook", agent());
  await without.drain();
  const walls = arrivals(calls.slice(before));
  assert.equal(walls.length, 2);
  assert.deepEqual(walls[0], walls[1]);
});

test("an opt-in is passed on exactly as written and never echoed by the door", async (t) => {
  const calls = withNotice(t);
  const { go, drain } = setup();
  const declared = { name: HOSTILE.mix, reason: `${HOSTILE.script} ${HOSTILE.markdown} ${HOSTILE.zeroWidth} ${HOSTILE.combining}`, source: "moltbook" };
  const query = intent({ purpose: "place-chiplets", notice_version: V, ...declared, via: "github" });
  const views = [];
  for (const init of [json(), md(), { headers: BROWSER }]) {
    const res = await go(query, init);
    assert.equal(res.status, 200);
    views.push(res.text);
  }
  assert.deepEqual(JSON.parse(views[0]).declaration, { status: "sent", detail: DECLARATION_TEXT.sent });
  for (const view of views) {
    for (const value of Object.values(declared).slice(0, 2)) assert.ok(!view.includes(value));
    for (const piece of ["onerror", "<script", "javascript:", "evil", "x.example", "Zalgo"]) assert.ok(!view.includes(piece), piece);
  }
  await drain();
  const bodies = arrivals(calls);
  assert.equal(bodies.length, 3);
  for (const body of bodies) {
    assert.deepEqual(Object.keys(body).sort(), ["class", "declaration", "nonce", "operator", "purpose"]);
    assert.deepEqual(body.declaration, { notice_version: V, ...declared });
  }
});

test("a refused opt-in still mints the same pass, sends no declaration and says why", async (t) => {
  const calls = withNotice(t);
  const { go, drain } = setup();
  const plain = JSON.parse((await go(intent({ purpose: "place-chiplets" }), json())).text);
  const cases = [...Object.values(REFUSED).map((name) => ["control_character", { name }]), ["control_character", { reason: REFUSED.nel }],
    ["too_long", { name: "x".repeat(65) }], ["too_long", { reason: "x".repeat(10000) }], ["source_unknown", { source: "evil" }]];
  for (const [code, fields] of cases) {
    const res = await go(intent({ purpose: "place-chiplets", notice_version: V, ...fields }), json());
    assert.equal(res.status, 200);
    const token = JSON.parse(res.text);
    assert.deepEqual(token.declaration, { status: "not_sent", code, detail: DECLARATION_TEXT[code] });
    assert.deepEqual(Object.keys(token).sort(), Object.keys(plain).sort());
    for (const key of ["purpose", "kind", "scope", "submissions", "schema"]) assert.equal(token[key], plain[key], key);
    for (const value of Object.values(fields)) assert.ok(!res.text.includes(value.slice(0, 40)));
  }
  await drain();
  const bodies = arrivals(calls);
  assert.equal(bodies.length, cases.length + 1);
  for (const body of bodies) assert.equal(body.declaration, undefined);
});

test("a declaration never changes the token, the check or the submission", async (t) => {
  const calls = withNotice(t);
  const { go } = setup();
  const hostile = JSON.parse((await go(intent({ purpose: "place-chiplets", notice_version: V, name: HOSTILE.script, reason: HOSTILE.url, source: "other" }), json())).text);
  const plain = JSON.parse((await go(intent({ purpose: "place-chiplets" }), json())).text);
  assert.equal(hostile.declaration.status, "sent");
  const strip = (token, value) => JSON.parse(JSON.stringify(value).split(token).join("<t>"));
  const layout = "36.35.0,54.35.0,54.55.0,36.55.0,17.35.0,73.35.0,73.55.0,17.55.0";
  const checks = [];
  for (const token of [hostile.t, plain.t]) checks.push(strip(token, JSON.parse((await go(`/agents/check?t=${token}&l=${layout}`, json())).text)));
  assert.deepEqual(checks[0], checks[1]);
  const answers = [];
  for (const token of [hostile.t, plain.t]) {
    const before = calls.length;
    const res = await go("/agents/submit", postJson({ t: token, layout }, { "user-agent": UA.gptbot }));
    const submit = calls.slice(before).find((c) => c.path === "/api/open/v1/door/submit");
    answers.push({ status: res.status, payload: { ...submit.body, token_claims: { ...submit.body.token_claims, nonce: "<n>", exp: "<e>" }, request_key: "<k>" } });
  }
  assert.deepEqual(answers[0], answers[1]);
  assert.deepEqual(Object.keys(answers[0].payload).sort(), ["class", "layout", "operator", "request_key", "terms", "token_claims"]);
});

// ── the agent view ────────────────────────────────────────────────────────────────────────────────────────────────
test("the agent view's declare object: the notice, the template for a new pass, and via pre-filling source", async (t) => {
  withNotice(t);
  const { go } = setup();
  const token = await mint();
  const view = JSON.parse((await go(`/agents/engram?t=${token}&via=senti`, json())).text);
  assert.equal(view.declare.status, "available");
  assert.deepEqual(view.declare.notice, NOTICE);
  assert.equal(view.declare.line, OPT_IN_LINE);
  assert.equal(view.declare.template,
    "https://sentilab.aidenid.com/agents/intent?purpose=place-chiplets&notice_version=sentilab-public-visitor%2F1&name={name}&reason={reason}&source=senti");
  assert.match(view.declare.note, /new pass/);
  assert.equal(JSON.parse((await go(`/agents/engram?t=${token}`, json())).text).declare.fields.source.prefilled, null);
  assert.deepEqual(declareObject("https://x.test", null), { status: "unavailable", optional: true, line: OPT_IN_LINE, detail: DECLARATION_TEXT.notice_unavailable });
});

test("the token page carries via into the agent view's link only", async (t) => {
  withNotice(t);
  const { go } = setup();
  const token = JSON.parse((await go(intent({ purpose: "place-chiplets", via: "moltbook" }), json())).text);
  assert.equal(new URL(token.next[0].url).searchParams.get("via"), "moltbook");
  const read = JSON.parse((await go(intent({ purpose: "read", via: "moltbook" }), json())).text);
  for (const link of read.next) assert.equal(new URL(link.url).searchParams.has("via"), false);
  const bad = JSON.parse((await go(intent({ purpose: "place-chiplets", via: "evil" }), json())).text);
  assert.equal(new URL(bad.next[0].url).searchParams.has("via"), false);
});

test("/agents/ stays the static index, with or without via, and records nothing", async (t) => {
  const calls = withNotice(t);
  const { go, drain } = setup();
  const plain = await go("/agents/", agent());
  const via = await go("/agents/?via=moltbook", agent());
  assert.equal(via.text, plain.text);
  assert.match(via.headers.get("content-type"), /text\/markdown/);
  await drain();
  assert.equal(arrivals(calls).length, 0);
});

// ── the copy ──────────────────────────────────────────────────────────────────────────────────────────────────────
test("the wall says what it records in aneta's words, and the opt-in line is the same everywhere", async (t) => {
  withNotice(t);
  const { go } = setup();
  assert.ok(RECORDED.startsWith("What we record: a guess at your assistant's type, and the time of this visit."));
  for (const word of ["Optional", "as you wrote it", "don't check it", "publish", "hide"]) assert.ok(OPT_IN_LINE.includes(word), word);
  const pages = [(await go("/agents/intent", { headers: BROWSER })).text, (await go("/agents/intent", md())).text,
    JSON.stringify(JSON.parse((await go("/agents/intent", json())).text))];
  for (const page of pages) {
    assert.ok(page.includes(OPT_IN_LINE));
    assert.ok(page.includes("a guess at your assistant"));
  }
  const ours = [OPT_IN_LINE, RECORDED, ...Object.values(DECLARATION_TEXT)].join(" ");
  for (const name of NAMES) assert.ok(!name.test(ours), String(name));
});

// ── the heartbeat proxy ───────────────────────────────────────────────────────────────────────────────────────────
const TAB = "3f9c2a7b4e1d6c8f0a5b9e2d7c4f1a86";
const beat = (value, extra = {}) => ({ method: "POST", headers: { "content-type": "application/json", ...BROWSER, "sec-fetch-mode": "cors",
  "sec-fetch-dest": "empty", "sec-fetch-site": "same-origin", accept: "*/*", origin: "https://sentilab.aidenid.com", ...extra },
  body: typeof value === "string" ? value : JSON.stringify(value) });
const hereCalls = (calls) => calls.filter((c) => c.path === HERE_PATH);

test("a heartbeat forwards exactly {page, tab, class} with fresh headers, and answers 204 no-store", async (t) => {
  const calls = installApi(t);
  const { go } = setup();
  const res = await go(HERE_PATH, beat({ page: "live", tab: TAB }, { "cf-connecting-ip": "203.0.113.77", "x-forwarded-for": "198.51.100.9",
    cookie: "sl_view=human", referer: "https://sentilab.aidenid.com/sentilab/package/?t=spt1.x" }));
  assert.equal(res.status, 204);
  assert.equal(res.text, "");
  assert.equal(res.headers.get("cache-control"), "no-store");
  const [call] = hereCalls(calls);
  assert.deepEqual(call.body, { page: "live", tab: TAB, class: "likely_human" });
  assert.equal(call.method, "POST");
  assert.deepEqual(Object.keys(call.headers).sort(), ["accept", "content-type", "x-forwarded-host", "x-origin-token"]);
  assert.ok(!JSON.stringify(call).includes("203.0.113.77") && !JSON.stringify(call).includes("198.51.100.9"));
  assert.ok(!JSON.stringify(call).includes("Chrome") && !JSON.stringify(call).includes("sl_view"));
});

test("a heartbeat's class is the detector's, qualified to four values", async (t) => {
  const calls = installApi(t);
  const { go } = setup();
  for (const [ua, klass] of [[UA.gptbot, "agent"], [UA.claudebot, "agent"], [UA.curl, "bot"], [UA.requests, "bot"]]) {
    assert.equal((await go(HERE_PATH, { method: "POST", headers: { "content-type": "application/json", "user-agent": ua },
      body: JSON.stringify({ page: "board", tab: TAB }) })).status, 204, ua);
    assert.equal(hereCalls(calls).at(-1).body.class, klass, ua);
  }
  assert.equal((await go(HERE_PATH, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ page: "board", tab: TAB }) })).status, 204);
  assert.ok(["unknown", "bot"].includes(hereCalls(calls).at(-1).body.class));
});

test("a heartbeat of any other shape is refused before any call", async (t) => {
  const calls = installApi(t);
  const { go } = setup();
  const bad = [{ page: "admin", tab: TAB }, { page: "live", tab: TAB.toUpperCase() }, { page: "live", tab: TAB.slice(1) }, { page: "live" },
    { tab: TAB }, { page: "live", tab: TAB, class: "likely_human" }, { page: "live", tab: TAB, ip: "203.0.113.77" }, [], "null", "{",
    `{"page":"live","page":"wall","tab":"${TAB}"}`, `{"page":"live","tab":"${TAB}"}${" ".repeat(300)}`];
  for (const value of bad) {
    const res = await go(HERE_PATH, beat(value));
    assert.equal(res.status, 400, JSON.stringify(value));
    assert.deepEqual(JSON.parse(res.text), { error: "bad_heartbeat" });
  }
  assert.equal((await go(HERE_PATH, beat({ page: "live", tab: TAB }, { "content-type": "text/plain" }))).status, 415);
  for (const site of ["cross-site", "same-site", "none"]) {
    assert.equal((await go(HERE_PATH, beat({ page: "live", tab: TAB }, { "sec-fetch-site": site }))).status, 403, site);
  }
  const noFetchMeta = beat({ page: "live", tab: TAB }, { origin: "https://evil.example" });
  delete noFetchMeta.headers["sec-fetch-site"];
  assert.equal((await go(HERE_PATH, noFetchMeta)).status, 403);
  for (const method of ["GET", "HEAD", "PUT", "OPTIONS", "DELETE"]) {
    const res = await go(HERE_PATH, { method, headers: BROWSER });
    assert.equal(res.status, 405, method);
    assert.equal(res.headers.get("allow"), "POST");
  }
  assert.equal(hereCalls(calls).length, 0);
  // Only the exact path is the heartbeat; another spelling is the read-only API.
  assert.equal((await go("/api/open/v1/door/%68ere", beat({ page: "live", tab: TAB }))).status, 405);
  assert.equal(hereCalls(calls).length, 0);
});

test("the per-IP limit lives in memory for at most 60 s and keys on the client's prefix only", async (t) => {
  const calls = installApi(t);
  const { go } = setup();
  let now = Date.parse("2026-11-01T19:30:00Z");
  t.mock.method(Date, "now", () => now);
  const from = (ip) => beat({ page: "live", tab: TAB }, { "cf-connecting-ip": ip });
  for (let i = 0; i < HERE_LIMIT.limit; i += 1) assert.equal((await go(HERE_PATH, from("203.0.113.7"))).status, 204);
  const limited = await go(HERE_PATH, from("203.0.113.99"));          // the same /24
  assert.equal(limited.status, 429);
  assert.equal(limited.headers.get("retry-after"), "60");
  assert.deepEqual(JSON.parse(limited.text), { error: "rate_limited" });
  assert.equal((await go(HERE_PATH, from("198.51.100.7"))).status, 204);
  assert.equal(hereCalls(calls).length, HERE_LIMIT.limit + 1);
  const entries = hereLimiterEntries();
  assert.deepEqual(entries.map(([key]) => key).sort(), ["here:198.51.100.0/24", "here:203.0.113.0/24"]);
  for (const [, value] of entries) assert.deepEqual(Object.keys(value).sort(), ["count", "start"]);
  now += HERE_LIMIT.periodMs - 1;
  assert.equal((await go(HERE_PATH, from("203.0.113.7"))).status, 429);
  now += 1;                                                           // the window has ended: nothing older is kept
  assert.equal((await go(HERE_PATH, from("192.0.2.1"))).status, 204);
  assert.deepEqual(hereLimiterEntries().map(([key]) => key), ["here:192.0.2.0/24"]);
  assert.equal((await go(HERE_PATH, from("203.0.113.7"))).status, 204);
  assert.equal(HERE_LIMIT.periodMs, 60000);
});

test("the API's own answers: 429 passes on, anything else is presence_unavailable", async (t) => {
  for (const [here, status, body] of [
    [async () => Response.json({ error: "rate_limited" }, { status: 429 }), 429, { error: "rate_limited" }],
    [async () => Response.json({ error: "presence_not_measured" }, { status: 503 }), 503, { error: "presence_unavailable" }],
    [async () => Response.json({ error: "bad_heartbeat" }, { status: 400 }), 503, { error: "presence_unavailable" }],
    [async () => new Response("ok", { status: 200 }), 503, { error: "presence_unavailable" }],
    [async () => { throw new Error("down"); }, 503, { error: "presence_unavailable" }]]) {
    installApi(t, { here });
    const { go } = setup();
    const res = await go(HERE_PATH, beat({ page: "live", tab: TAB }));
    assert.equal(res.status, status);
    assert.deepEqual(JSON.parse(res.text), body);
    assert.equal(res.headers.get("cache-control"), "no-store");
    t.mock.restoreAll();
  }
  installApi(t);
  const { go } = setup({ API_ORIGIN: undefined });
  assert.equal((await go(HERE_PATH, beat({ page: "live", tab: TAB }))).status, 503);
});

// ── the open feeds through the /api proxy ────────────────────────────────────────────────────────────────────────
test("the visitors and stats feeds pass the open-feed filter: JSON only, no operator at any depth, nosniff", async (t) => {
  const seen = [];
  t.mock.method(globalThis, "fetch", async (input) => {
    const raw = new URL(String(input)).pathname;
    seen.push(raw);
    const path = decodeURIComponent(raw);         // the API routes the decoded path
    if (path.endsWith("/visitors")) return Response.json({ ...VISITORS, items: [{ ...VISITORS.items[1], operator: "openai" }], operator: "x" });
    if (path.endsWith("/stats")) return Response.json({ schema: "sentilab-door-stats/1", through_seq: 3, passes: 1, submissions: 0,
      results: { evaluated: 0, reproduced: 0, rejected: 0, failed: 0 }, operator: "openai" });
    return new Response("<html>", { status: 200, headers: { "content-type": "text/html" } });
  });
  const { go } = setup();
  const visitors = await go("/api/open/v1/door/visitors?limit=500", { headers: BROWSER });
  assert.equal(visitors.status, 200);
  assert.ok(!visitors.text.includes("operator"));
  assert.equal(JSON.parse(visitors.text).items[0].declaration.name, VISITORS.items[1].declaration.name);
  assert.equal(visitors.headers.get("x-content-type-options"), "nosniff");
  assert.match(visitors.headers.get("content-type"), /^application\/json/);
  const stats = await go("/api/open/v1/door/st%61ts", { headers: BROWSER });
  assert.ok(!stats.text.includes("operator"));
  assert.equal(JSON.parse(stats.text).passes, 1);
  assert.deepEqual(seen, ["/api/open/v1/door/visitors", "/api/open/v1/door/st%61ts"]);
});

// ── the published fixture ────────────────────────────────────────────────────────────────────────────────────────
test("the heartbeat fixture (here.json) is what the door does", async (t) => {
  const HERE = JSON.parse(readFileSync(new URL("./fixtures/door-a4/here.json", import.meta.url), "utf8"));
  assert.equal(HERE.request.path, HERE_PATH);
  assert.deepEqual(HERE.fields.page, [...HERE_PAGES]);
  assert.equal(HERE.page_line, HERE_LINE);
  const answers = Object.fromEntries(HERE.responses.map((r) => [r.status, r]));
  const calls = installApi(t);
  const { go } = setup();
  const ok = await go(HERE.request.path, beat(HERE.request.body, HERE.request.headers));
  assert.equal(ok.status, 204);
  assert.equal(answers[204].body, null);
  const [call] = hereCalls(calls);
  assert.deepEqual(call.body, HERE.forwarded_to_api.body);
  for (const name of HERE.forwarded_to_api.never_forwarded) assert.equal(call.headers[name], undefined, name);
  const answer = async (init) => { const res = await go(HERE_PATH, init); return [res.status, JSON.parse(res.text)]; };
  assert.deepEqual(await answer(beat({ page: "home", tab: TAB })), [400, answers[400].body]);
  assert.deepEqual(await answer(beat({ page: "live", tab: TAB }, { "sec-fetch-site": "cross-site" })), [403, answers[403].body]);
  assert.deepEqual(await answer(beat({ page: "live", tab: TAB }, { "content-type": "text/plain" })), [415, answers[415].body]);
  t.mock.restoreAll();
  installApi(t, { here: async () => Response.json({ error: "rate_limited" }, { status: 429 }) });
  const limited = await go(HERE_PATH, beat({ page: "live", tab: TAB }));
  assert.deepEqual([limited.status, JSON.parse(limited.text), limited.headers.get("retry-after")], [429, answers[429].body, answers[429].headers["retry-after"]]);
  t.mock.restoreAll();
  installApi(t, { here: async () => Response.json({ error: "presence_not_measured" }, { status: 503 }) });
  assert.deepEqual(await answer(beat({ page: "live", tab: TAB })), [503, answers[503].body]);
});
