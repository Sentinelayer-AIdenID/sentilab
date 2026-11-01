// node --test web/test/door-warden-p3.test.mjs
// Warden's four P3s from the +1 at df1189c4 (PR #82 issue comment 6553430239), each written as the control the
// finding describes, failing first at 609a007d:
//   1. Terms drift: the confirm form carries the terms it showed. A press is sent under exactly those while the intake
//      still accepts them; otherwise the person gets "Terms changed: please confirm again" with the current terms, and
//      nothing is sent. Never a silent submit under other terms.
//   2. A press that follows an earlier one (the forms on the pages after a press post to /agents/submit?again=1) and
//      is refused before its POST says that the earlier press may already be queued and offers the check (the same
//      request again), never "Nothing was sent".
//   3. The proxy's open-feed filter matches the path as the API routes it (percent-decoded), so no spelling of
//      /api/open/v1/door/{board,results,events} skips it; a path whose escapes do not decode is refused.
//   4. Browsers without Sec-Fetch-Site: a form post passes when its Origin is this site and is refused otherwise
//      (door-hold P3-1 keeps those cases), and every page that holds the submit form is Referrer-Policy strict-origin:
//      under no-referrer a browser sends "Origin: null" with the form's POST (measured in Chrome), which that rule must
//      refuse. strict-origin still sends no path and no query, so the token stays on the page.
import { test } from "node:test";
import assert from "node:assert/strict";

import { BASE, BOARD, BROWSER, REF, TERMS, installApi, mint, postForm, postJson, setup } from "./door-harness.mjs";

const submits = (calls) => calls.filter((c) => c.method === "POST" && c.path === "/api/open/v1/door/submit");
const denying = (prefix) => ({ limit: async ({ key }) => ({ success: !key.startsWith(prefix) }) });
const NEWER = `sentilab-open-terms/2@${"1e".repeat(32)}`;
const boardWith = (versions) => async () => Response.json({ ...BOARD, terms: { accepted_versions: versions } });
const press = (token, terms, extra = {}) => postForm(`t=${token}&l=${encodeURIComponent(REF)}${terms === undefined ? "" : `&terms=${encodeURIComponent(terms)}`}`, extra);
const field = (name, value) => `<input type="hidden" name="${name}" value="${value}">`;
const UNCERTAIN = async () => new Response("<html>Bad gateway</html>", { status: 502 });

// ── 1. terms drift ─────────────────────────────────────────────────────────────────────────────────────────────────
test("P3-1: the confirm form carries the terms it shows, and a press is sent under exactly those while the intake accepts them", async (t) => {
  const token = await mint();
  const calls = installApi(t, { board: boardWith([TERMS, NEWER]) });
  const s = setup();
  const page = await s.go(`/s?t=${token}&l=${REF}`, { headers: BROWSER });
  assert.ok(page.text.includes(`Submitting accepts the challenge terms <code>${NEWER}</code> (<a href="/agents/terms">read them</a>).`));
  assert.ok(page.text.includes(field("terms", NEWER)), "the form carries the terms the page shows");
  // A page shown before the newer version, under one the intake still accepts: sent under that one, not the newest.
  const r = await s.go("/agents/submit", press(token, TERMS));
  assert.equal(r.status, 200);
  assert.match(r.text, /<h1>Sent to the scorer<\/h1>/);
  assert.deepEqual(submits(calls).map((c) => c.body.terms), [TERMS]);
  // JSON keeps its rule (the ENGRAM view's note): the intake's newest accepted version.
  await s.go("/agents/submit", postJson({ t: token, layout: REF }));
  assert.deepEqual(submits(calls).map((c) => c.body.terms), [TERMS, NEWER]);
});

test("P3-1: terms the intake no longer accepts (or none) get 'Terms changed: please confirm again' with the current terms, and nothing is sent", async (t) => {
  const token = await mint();
  const calls = installApi(t, { board: boardWith([NEWER]) });
  for (const [why, terms] of [["an older version", TERMS], ["no terms field", undefined], ["not a terms version", "anything"]]) {
    const r = await setup().go("/agents/submit", press(token, terms));
    assert.equal(r.status, 409, why);
    assert.match(r.text, /<h1>Terms changed: please confirm again<\/h1>/, why);
    assert.ok(r.text.includes(`<code>${NEWER}</code>`) && r.text.includes(field("terms", NEWER)), `${why}: the current terms, and the form to accept them`);
    assert.ok(r.text.includes(field("t", token)) && r.text.includes(field("l", REF)), `${why}: the same link and layout`);
    assert.ok(r.text.includes('<form method="post" action="/agents/submit">'), `${why}: a first press, so no earlier press to mark`);
    assert.ok(r.text.includes("so this press was not sent") && !/may already be queued|anything/.test(r.text), why);
    assert.equal(r.headers.get("referrer-policy"), "strict-origin", `${why}: the page holds the submit form`);
  }
  assert.deepEqual(submits(calls), [], "never a silent submit under other terms");
  // Pressing on that page sends it under the terms it now shows.
  assert.equal((await setup().go("/agents/submit", press(token, NEWER))).status, 200);
  assert.deepEqual(submits(calls).map((c) => c.body.terms), [NEWER]);
});

// ── 2. a press after an earlier one ────────────────────────────────────────────────────────────────────────────────
test("P3-2: the page after an uncertain press marks its button as a press that follows an earlier one, with the same terms", async (t) => {
  const token = await mint();
  installApi(t, { submit: UNCERTAIN });
  const page = await setup().go("/agents/submit", press(token, TERMS));
  assert.equal(page.status, 502);
  assert.ok(page.text.includes('<form method="post" action="/agents/submit?again=1">'));
  assert.ok(page.text.includes(field("t", token)) && page.text.includes(field("l", REF)) && page.text.includes(field("terms", TERMS)));
});

test("P3-2: a press after an earlier one, refused before its POST, says the earlier press may already be queued and offers the check, never 'Nothing was sent'", async (t) => {
  const token = await mint();
  const expired = await mint("place-chiplets", { now: Date.now() - 7200e3 });
  const cases = [
    ["the token's rate limit", { DOOR_NONCE_LIMITER: denying("submit:") }, {}, token, 429, "Too many submissions from here just now.", true],
    ["the prefix rate limit", { DOOR_IP_LIMITER: denying("submit:") }, {}, token, 429, "Too many submissions from here just now.", true],
    ["the intake unreachable", {}, { board: async () => { throw new Error("down"); } }, token, 503, "The scorer intake could not be reached.", true],
    ["submissions not open", {}, { board: boardWith([]) }, token, 503, "Submissions are not open on this site right now.", true],
    ["an expired token", {}, {}, expired, 401, "This link&#39;s token has expired (tokens last 60 minutes).", "a new link would send it again as a new submission"],
    ["the door closed", { DOOR_TOKEN_KEY: undefined }, {}, token, 503, "Submissions are not open on this site right now.", "Open the link your assistant gave you again later"],
  ];
  for (const [why, env, routes, value, status, text, retry] of cases) {
    const calls = installApi(t, routes);
    const r = await setup(env).go("/agents/submit?again=1", press(value, TERMS));
    assert.equal(r.status, status, why);
    assert.match(r.text, /<h1>Not confirmed<\/h1>/, why);
    assert.ok(r.text.includes(`This press was not sent: ${text}`), `${why}: ${r.text}`);
    assert.ok(r.text.includes("An earlier press of this link may already be queued"), why);
    assert.ok(!/nothing was sent/i.test(r.text) && !/<h1>Not sent<\/h1>/.test(r.text), `${why}: never "Nothing was sent"`);
    if (retry === true) {
      assert.ok(r.text.includes('<form method="post" action="/agents/submit?again=1">') && r.text.includes(field("t", value))
        && r.text.includes(field("l", REF)) && r.text.includes(field("terms", TERMS)), `${why}: the check is the same request again`);
      assert.equal(r.headers.get("referrer-policy"), "strict-origin", why);
    } else {
      // Nothing this press carried can be offered back (no key to verify it, or a token past its time): the way to check.
      assert.ok(!/<form\b/.test(r.text) && r.text.includes(retry), `${why}: how to check without this press`);
      assert.equal(r.headers.get("referrer-policy"), "no-referrer", why);
    }
    assert.deepEqual(submits(calls), [], why);
    t.mock.restoreAll();
  }
  // A first press keeps its wording: nothing was sent, and there is no earlier press to speak of.
  installApi(t, {});
  const first = await setup({ DOOR_NONCE_LIMITER: denying("submit:") }).go("/agents/submit", press(token, TERMS));
  assert.deepEqual([first.status, /<h1>Not sent<\/h1>/.test(first.text), first.text.includes("Nothing was sent."), /may already be queued/.test(first.text)], [429, true, true, false]);
  // The mark means nothing to JSON: an agent's refusal is the same body either way.
  const limited = await setup({ DOOR_NONCE_LIMITER: denying("submit:") }).go("/agents/submit?again=1", postJson({ t: token, layout: REF }));
  assert.deepEqual([limited.status, JSON.parse(limited.text).codes[0].code], [429, "rate_limited"]);
});

test("P3-2: terms that changed after an earlier press: the same terms page, with the mark kept and the earlier press named", async (t) => {
  const token = await mint();
  const calls = installApi(t, { board: boardWith([NEWER]) });
  const r = await setup().go("/agents/submit?again=1", press(token, TERMS));
  assert.equal(r.status, 409);
  assert.match(r.text, /<h1>Terms changed: please confirm again<\/h1>/);
  assert.ok(r.text.includes('<form method="post" action="/agents/submit?again=1">') && r.text.includes(field("terms", NEWER)));
  assert.ok(r.text.includes("An earlier press of this link may already be queued") && !/nothing was sent/i.test(r.text));
  assert.deepEqual(submits(calls), []);
});

// ── 3. every spelling of an open feed ──────────────────────────────────────────────────────────────────────────────
test("P3-3: no spelling of an open feed's path skips the proxy's operator filter; a path that does not decode is refused", async (t) => {
  const feed = { schema: "sentilab-door-board/1", operator: "openai", top: [{ class: "declared_agent", operator: "anthropic", short_id: "ab12" }] };
  const asked = [];
  // The stand-in API answers every path with a body naming operators, so only the Worker's filter can remove them.
  t.mock.method(globalThis, "fetch", async (input) => { asked.push(new URL(String(input)).pathname); return Response.json(feed); });
  const s = setup();
  for (const path of ["/api/open/v1/door/%62oard", "/api/open/v1/door/%62%6F%61%72%64", "/api/open/v1/door/%72esults", "/api/open/v1/door/ev%65nts",
    "/api/open/v1/door%2Fboard", "/api/open/v1/door%2fresults", "/api/open/v1%2Fdoor/events", "/api/%6Fpen/v1/door/board",
    "/api/open/v1/door/%2562oard", "/api/open/v1/door/%252562oard"]) {
    const r = await s.go(path);
    assert.equal(r.status, 200, path);
    assert.ok(!r.text.includes("operator") && !/openai|anthropic/.test(r.text), `${path}: ${r.text}`);
    assert.equal(JSON.parse(r.text).top[0].short_id, "ab12", path);
  }
  const before = asked.length;
  for (const path of ["/api/open/v1/door/%E0%A4%A", "/api/open/v1/door/%ZZboard", "/api/open/v1/door/%"]) {
    const r = await s.go(path);
    assert.deepEqual([r.status, JSON.parse(r.text).error], [400, "bad_path"], path);
  }
  assert.equal(asked.length, before, "a path that does not decode never reaches the API");
  // A path that decodes to anything else is passed on as before.
  assert.equal(JSON.parse((await s.go("/api/view/%72uns")).text).operator, "openai");
});

// ── 4. browsers without Sec-Fetch-Site ─────────────────────────────────────────────────────────────────────────────
test("P3-4: every page that holds the submit form is strict-origin, so its POST carries this site's Origin; every other door page stays no-referrer", async (t) => {
  const token = await mint();
  installApi(t, { submit: UNCERTAIN });
  const s = setup();
  const confirm = await s.go(`/s?t=${token}&l=${REF}`, { headers: BROWSER });
  assert.ok(confirm.text.includes('<form method="post" action="/agents/submit">'));
  assert.equal(confirm.headers.get("referrer-policy"), "strict-origin", "the confirm page, at its token-bearing URL");
  const notConfirmed = await s.go("/agents/submit", press(token, TERMS));
  assert.equal(notConfirmed.headers.get("referrer-policy"), "strict-origin", "the not-confirmed page's retry");
  // No form, no exception: a refusal, a page without the button, the agents' pages.
  for (const [why, r] of [
    ["a refusal", await s.go("/agents/submit", press("x", TERMS))],
    ["the confirm page with no button", await setup({ API_ORIGIN: "none" }).go(`/s?t=${token}&l=${REF}`, { headers: BROWSER })],
    ["the token page", await s.go("/agents/intent?purpose=place-chiplets", { headers: BROWSER })],
    ["a mapped page at a token-bearing URL", await s.go(`/?t=${token}`, { headers: { "user-agent": "curl/8.4.0" } })],
  ]) {
    assert.equal(r.headers.get("referrer-policy"), "no-referrer", why);
  }
  // A browser without Sec-Fetch-Site that names this site in Origin, as strict-origin makes it, is let through.
  const old = await setup().go("/agents/submit", { method: "POST", headers: { "content-type": "application/x-www-form-urlencoded", "user-agent": BROWSER["user-agent"], origin: BASE },
    body: `t=${token}&l=${encodeURIComponent(REF)}&terms=${encodeURIComponent(TERMS)}` });
  assert.equal(old.status, 502, "it reached the intake (an uncertain answer here)");
});
