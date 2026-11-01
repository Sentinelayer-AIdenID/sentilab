// node --test web/test/door-review.test.mjs
// Root's review of PR #82 at 75aed822 (three P2 findings), each written as the control the review describes, failing
// first at that head:
//   1. Token referrer protection: every response to a request that can carry a token (the mapped pages' agent
//      version, the human override, a browser, any asset, a missing page) is no-referrer and private, no-store,
//      no-transform; the /api proxy drops a token-bearing Referer before forwarding.
//   2. Strict JSON on POST /agents/submit: duplicate keys at any depth, too-deep bodies and non-finite numbers are
//      refused with the codes #81's contract reader gives (open_proposals/contract/validator.py _json), before any
//      field is chosen and before the intake is asked.
//   3. Honest uncertain delivery: once the POST to the intake has been attempted, a timeout, a lost connection or an
//      answer the door does not recognise is "not confirmed", never "nothing was sent", and the person is offered the
//      same idempotent retry (same token, layout and request key), never a new link.
// Plus the terms a submission accepts, now read from the intake's board (#81 at 796fec43: terms.accepted_versions).
import { test } from "node:test";
import assert from "node:assert/strict";

import { API_ORIGIN, BASE, BOARD, BROWSER, OVERLAP, REF, TERMS, agent, file, installApi, mint, postForm, postJson, same, setup } from "./door-harness.mjs";

const submits = (calls) => calls.filter((c) => c.method === "POST" && c.path === "/api/open/v1/door/submit");
const rejected = (codes) => ({ schema: "sentilab-door-submit/1", state: "rejected", codes: codes.map((code) => ({ code })) });

// ── 1. token referrer protection ───────────────────────────────────────────────────────────────────────────────────
test("1. every response to a request that can carry a token is no-referrer and private, no-store, no-transform", async (t) => {
  installApi(t);
  const s = setup();
  const token = await mint("read");
  const expired = await mint("place-chiplets", { now: Date.now() - 7200e3 });
  const cases = [
    [`/?t=${token}`, agent(), "the agent version for a valid token"],
    [`/sentilab/package/?t=${token}`, agent(), "another mapped page"],
    [`/?t=${token}&view=human`, agent(), "the human override by query"],
    [`/?t=${token}`, agent(undefined, { cookie: "sl_view=human" }), "the human override by cookie"],
    [`/?t=${token}`, { headers: BROWSER }, "a browser on a token-bearing URL"],
    [`/sentilab/?t=${expired}`, agent(), "the wall again, for an expired token"],
    [`/styles.css?t=${token}`, { headers: BROWSER }, "any asset"],
    [`/agents/index.md?t=${token}`, agent(), "an agent page"],
    [`/nope?t=${token}`, { headers: BROWSER }, "a missing page"],
    [`/?x=${token}`, { headers: BROWSER }, "the token in another parameter"],
    [`/?q=${encodeURIComponent(token)}`, { headers: BROWSER }, "the token percent-encoded"],
    ["/?t=", { headers: BROWSER }, "an empty t"],
  ];
  for (const [path, init, why] of cases) {
    const r = await s.go(path, init);
    assert.equal(r.headers.get("referrer-policy"), "no-referrer", why);
    const policy = (r.headers.get("cache-control") ?? "").split(/,\s*/);
    for (const directive of ["private", "no-store", "no-transform"]) assert.ok(policy.includes(directive), `${why}: ${directive}`);
  }
  // The pages are the same bytes as before; only the two headers change.
  assert.ok(same((await s.go(`/?t=${token}&view=human`, agent())).bytes, file("index.html")));
  assert.ok(same((await s.go(`/?t=${token}`, agent())).bytes, file("agents/index.md")));
  // A URL without a token keeps its headers exactly as E and #66 set them.
  const plain = await s.go("/", { headers: BROWSER });
  assert.equal(plain.headers.get("referrer-policy"), null);
  assert.equal(plain.headers.get("cache-control"), "private, no-store");
  assert.equal((await s.go("/styles.css", { headers: BROWSER })).headers.get("referrer-policy"), null);
});

test("1. the /api proxy drops a Referer that carries a token and forwards any other one unchanged", async (t) => {
  const seen = [];
  t.mock.method(globalThis, "fetch", async (input, init) => { seen.push(Object.fromEntries(new Headers(init.headers))); return Response.json({}); });
  const s = setup();
  const token = await mint();
  const bearing = [`${BASE}/?t=${token}`, `${BASE}/s?t=${token}&l=${REF}`, `${BASE}/?view=human&t=${token}`, `${BASE}/x?q=${token}`,
    `${BASE}/?t=`, `${BASE}/?a=1&t=abc`, `${BASE}/?q=spt1%2Eplace-chiplets`, `${BASE}/?q=SPT1.x`];
  for (const referer of bearing) await s.go("/api/view/runs", { headers: { referer } });
  assert.equal(seen.length, bearing.length);
  assert.ok(seen.every((headers) => !("referer" in headers)), JSON.stringify(seen.map((h) => h.referer ?? null)));
  seen.length = 0;
  for (const referer of [`${BASE}/sentilab/`, `${BASE}/leaderboard.html?seed=11`, "https://example.org/a?b=c"]) {
    await s.go("/api/view/runs", { headers: { referer } });
    assert.equal(seen.at(-1).referer, referer);
  }
});

// ── 2. strict JSON on the submit body ──────────────────────────────────────────────────────────────────────────────
test("2. duplicate keys at any depth, too-deep bodies and non-finite numbers are refused before any field is chosen", async (t) => {
  const calls = installApi(t);
  const s = setup();
  const token = await mint();
  const die = (i) => `{"die":${i},"x_um":${[18000, 27000, 27000, 18000, 8500, 36500, 36500, 8500][i]},"y_um":${[17500, 17500, 27500, 27500, 17500, 17500, 27500, 27500][i]},"rot_deg":0}`;
  const dies = (first = die(0)) => `[${[first, ...[1, 2, 3, 4, 5, 6, 7].map(die)].join(",")}]`;
  const cases = [
    [`{"t":"${token}","layout":"36.35.0","layout":"${REF}"}`, ["duplicate_key"], "root's control: a malformed layout, then a legal one"],
    [`{"t":"not-a-token","t":"${token}","layout":"${REF}"}`, ["duplicate_key"], "root's control: an invalid t, then a valid one"],
    [`{"t":"${token}","layout":${dies(`{"die":0,"die":0,"x_um":18000,"y_um":17500,"rot_deg":0}`)}}`, ["duplicate_key"], "a duplicate inside a die"],
    [`{"t":"${token}","layout":"${REF}","request_key":"a","request_key":"b"}`, ["duplicate_key"], "a duplicate request key"],
    [`{"t":"${token}","layout":[[[["x"]]]]}`, ["too_deep"], "depth 5"],
    [`{"t":"${token}","layout":[[[[[[[[[[["x"]]]]]]]]]]]}`, ["too_deep"], "depth 12"],
    [`{"t":"${token}","layout":NaN}`, ["nonfinite_number"], "NaN"],
    [`{"t":"${token}","layout":Infinity}`, ["nonfinite_number"], "Infinity"],
    [`{"t":"${token}","layout":1e400}`, ["nonfinite_number"], "a float that overflows"],
    [`{"t":"${token}","t":"${token}","layout":-Infinity}`, ["duplicate_key", "nonfinite_number"], "both, in contract order"],
    [`\ufeff{"t":"${token}","layout":"${REF}"}`, ["malformed_json"], "a byte-order mark"],
    [`{"t":"${token}","layout":"${REF}",}`, ["malformed_json"], "a trailing comma"],
    [`{"t":"${token}","layout":"${REF}"} {}`, ["malformed_json"], "two values"],
    [`["${token}"]`, ["malformed_json"], "not an object"],
    [`{'t':'${token}'}`, ["malformed_json"], "single quotes"],
    [`{"t":"${token}","layout":"a\tb"}`, ["malformed_json"], "a raw tab in a string"],
    [`{"t":"${token}","layout":01}`, ["malformed_json"], "a leading zero"],
    [`{"t":"${token}","layout":"${REF}"/**/}`, ["malformed_json"], "a comment"],
  ];
  for (const [body, codes, why] of cases) {
    const r = await s.go("/agents/submit", postJson(body));
    assert.equal(r.status, 400, why);
    assert.deepEqual(JSON.parse(r.text), rejected(codes), why);
  }
  await s.drain();
  assert.deepEqual(submits(calls), [], "nothing ambiguous reaches the intake");
  // Depth 4 is within the contract's bound (it reads, then fails the layout's own rules), and a clean body in the dies
  // form still goes through.
  const four = await s.go("/agents/submit", postJson(`{"t":"${token}","layout":[[["x"]]]}`));
  assert.deepEqual([four.status, JSON.parse(four.text).codes], [422, [{ code: "die_count", count: 1 }]]);
  assert.equal((await s.go("/agents/submit", postJson(`{"t":"${token}","layout":${dies()}}`))).status, 202);
  assert.equal(submits(calls).length, 1);
});

// ── 3. honest uncertain delivery ───────────────────────────────────────────────────────────────────────────────────
const UNCERTAIN = [
  ["no_answer", 502, async () => { throw new Error("connection reset"); }],
  ["unrecognized_answer", 502, async () => Response.json({ schema: "sentilab-door-submit/1", state: "queued" }, { status: 500 })],
  ["unrecognized_answer", 502, async () => new Response("<html>Bad gateway</html>", { status: 502 })],
  ["unrecognized_answer", 502, async () => Response.json({ detail: "Not Found" }, { status: 404 })],
  ["unrecognized_answer", 502, async () => Response.json({ state: "queued" }, { status: 202 })],
];

function assertNotConfirmedPage(text, token) {
  assert.match(text, /<h1>Not confirmed<\/h1>/);
  assert.ok(!/nothing was sent/i.test(text) && !/<h1>Not sent<\/h1>/.test(text), "never claims nothing was sent");
  assert.ok(!/new link/i.test(text), "never sends the person for a new link");
  assert.equal((text.match(/<form\b/g) ?? []).length, 1);
  assert.ok(text.includes('<form method="post" action="/agents/submit">'));
  assert.ok(text.includes(`<input type="hidden" name="t" value="${token}">`) && text.includes(`<input type="hidden" name="l" value="${REF}">`), "the same token and layout");
  assert.ok(!/<script|http-equiv/i.test(text));
}

test("3. after the POST is attempted, no answer or an answer the door does not recognise is 'not confirmed', with the same idempotent retry", async (t) => {
  const token = await mint();
  for (const [cause, status, answer] of UNCERTAIN) {
    const calls = installApi(t, { submit: answer });
    const s = setup();
    const r = await s.go("/agents/submit", postJson({ t: token, layout: REF }));
    const body = JSON.parse(r.text);
    assert.equal(r.status, status, cause);
    assert.equal(body.error, "delivery_unknown");
    assert.equal(body.cause, cause);
    assert.match(body.request_key, /^door-[0-9a-f]{32}$/);
    assert.deepEqual(body.retry, { method: "POST", url: `${BASE}/agents/submit`, content_type: "application/json", body: { t: token, layout: REF, request_key: body.request_key } });
    assert.ok(!/nothing was sent/i.test(r.text) && !/new link/i.test(r.text));
    const page = await s.go("/agents/submit", postForm(`t=${token}&l=${encodeURIComponent(REF)}`));
    assert.equal(page.status, status);
    assertNotConfirmedPage(page.text, token);
    // Retrying is the same request: the intake sees the same request key every time.
    const keys = submits(calls).map((c) => c.body.request_key);
    assert.equal(keys.length, 2);
    assert.equal(new Set([...keys, body.request_key]).size, 1, "the JSON retry, the button and the shown key agree");
    t.mock.restoreAll();
  }
});

test("3. a timeout after the POST is 'not confirmed' too (504), with the key to retry with", async (t) => {
  const token = await mint();
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const calls = installApi(t, { submit: (call) => new Promise((_, reject) => call.signal.addEventListener("abort", () => reject(new Error("aborted")))) });
  for (const form of [false, true]) {
    const before = submits(calls).length;
    const pending = setup().go("/agents/submit", form ? postForm(`t=${token}&l=${encodeURIComponent(REF)}`) : postJson({ t: token, layout: REF }));
    for (let i = 0; i < 400 && submits(calls).length === before; i += 1) await new Promise((resolve) => setImmediate(resolve));
    t.mock.timers.tick(8000);
    const r = await pending;
    assert.equal(r.status, 504);
    if (form) assertNotConfirmedPage(r.text, token);
    else {
      const body = JSON.parse(r.text);
      assert.deepEqual([body.error, body.cause], ["delivery_unknown", "timeout"]);
      assert.match(body.request_key, /^door-[0-9a-f]{32}$/);
    }
  }
});

test("3. refusals before the POST still say nothing was sent, and only they do", async (t) => {
  const calls = installApi(t);
  const token = await mint();
  const expired = await mint("place-chiplets", { now: Date.now() - 7200e3 });
  const pages = [
    [setup(), postForm(`t=${expired}&l=${encodeURIComponent(REF)}`), 401],
    [setup(), postForm(`t=${token}&l=${encodeURIComponent(`${REF},1.1.0`)}`), 422],
    [setup({ API_ORIGIN: "none" }), postForm(`t=${token}&l=${encodeURIComponent(REF)}`), 503],
  ];
  for (const [s, init, status] of pages) {
    const r = await s.go("/agents/submit", init);
    assert.equal(r.status, status);
    assert.match(r.text, /<h1>Not sent<\/h1>/);
    assert.match(r.text, /Nothing was sent\./);
  }
  assert.deepEqual(submits(calls), []);
});

// ── terms from the intake's board (#81 at 796fec43) ────────────────────────────────────────────────────────────────
test("the terms a submission accepts come from the intake's board: the highest accepted version", async (t) => {
  const newer = `sentilab-open-terms/12@${"ab".repeat(32)}`;
  const calls = installApi(t, { board: async () => Response.json({ ...BOARD, terms: { accepted_versions: [TERMS, newer, "nonsense"] } }) });
  const s = setup();
  const token = await mint();
  assert.equal((await s.go("/agents/submit", postJson({ t: token, layout: REF }))).status, 202);
  assert.equal(submits(calls)[0].body.terms, newer);
  assert.ok((await s.go(`/s?t=${token}&l=${REF}`, { headers: BROWSER })).text.includes(`Submitting accepts the challenge terms <code>${newer}</code>.`));
  assert.equal(JSON.parse((await s.go(`/agents/engram?t=${token}`, agent())).text).submissions.terms, newer);
  t.mock.restoreAll();
  // No accepted terms: not open yet, at the edge, with nothing sent.
  const none = installApi(t, { board: async () => Response.json({ ...BOARD, terms: { accepted_versions: [] } }) });
  const r = await setup().go("/agents/submit", postJson({ t: token, layout: REF }));
  assert.deepEqual([r.status, JSON.parse(r.text)], [503, rejected(["not_open_yet"])]);
  assert.deepEqual(submits(none), []);
  t.mock.restoreAll();
  // The intake unreachable: nothing is sent, and the door says so before any POST.
  t.mock.method(globalThis, "fetch", async () => { throw new Error("intake down"); });
  const down = await setup().go("/agents/submit", postJson({ t: token, layout: REF }));
  assert.deepEqual([down.status, JSON.parse(down.text).error], [503, "intake_unavailable"]);
  const page = await setup().go(`/s?t=${token}&l=${REF}`, { headers: BROWSER });
  assert.ok(page.text.includes("cannot be reached right now") && !page.text.includes("<form"), "the confirm page says so and offers no button");
  assert.ok(API_ORIGIN.startsWith("https://"));
});
