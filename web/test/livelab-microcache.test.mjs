// node --test web/test/livelab-microcache.test.mjs
// The /api proxy's micro-cache (web/src/worker.js, warden P1-2(a)). A QR code in a live talk brings ~200 viewers within
// ~30 s, each polling results and events every 3 s, and one API replica serves them all. So a GET of exactly
// /api/open/v1/door/results, /events or /board whose filtered answer (doorFeed) is a 200 is kept for 2 s in
// caches.default, keyed by its full URL. Through the real Worker (door-harness setup()), with a stand-in API on a mocked
// global fetch that records every call, a fake caches.default backed by a Map keyed on the request URL (it ignores
// max-age, so expiry is the Worker's own, and adds headers of its own to a match) and node's mocked Date:
//   1. two identical GETs of each feed within 2 s make one upstream call, and both answers are the uncached answer;
//   2. an entry 2 s old or older is a miss: the next GET goes upstream again and the stale entry is deleted, never served;
//   3. a request carrying X-Door-Nonce always goes upstream, never reads or writes the cache, and the API never sees it;
//   4. non-200 answers (503 and 429 with Retry-After, 4xx, 5xx, 206, 502 unreadable feed) and a 200 that sets a cookie
//      are never kept, and pass on exactly as without the cache;
//   5. different queries are different entries;
//   6. other paths, other spellings, HEAD, Range, token-bearing URLs, other methods and an API that is switched off never
//      touch the cache;
//   7. a cache whose match, put or delete throws or rejects, no caches.default, or an entry the Worker did not write:
//      the normal upstream answer;
//   8. no private header and nothing the cache adds reaches a browser; the operator stays stripped in the stored copy;
//      the copy is public, max-age=2; the put rides ctx.waitUntil, and without a ctx the answer still comes.
import { test } from "node:test";
import assert from "node:assert/strict";

import { BASE, BOARD, setup } from "./door-harness.mjs";
import worker from "../src/worker.js";

const FEEDS = ["/api/open/v1/door/results", "/api/open/v1/door/events", "/api/open/v1/door/board"];
const T0 = Date.UTC(2026, 10, 1, 17, 0, 0);
const NONCE = "0123456789abcdef";
const MADE = "x-microcache-made";
const SENT = "x-microcache-headers";
const utf8 = (text) => new TextEncoder().encode(text);

// The stand-in API (app/door/routes.py): every answer JSON with cache-control no-store, each feed carrying declared
// operators the proxy must strip and an ETag the proxy drops. api.version is the API's state (a test moves it on);
// api.respond(call) may answer a call instead. Every call is recorded: method, path with its query, headers.
function installUpstream(t) {
  const api = { calls: [], version: 1, respond: null, count: (path) => api.calls.filter((c) => c.path === path).length };
  t.mock.method(globalThis, "fetch", async (input, init = {}) => {
    const url = new URL(String(input));
    const call = { method: init.method ?? "GET", path: url.pathname + url.search, headers: Object.fromEntries(new Headers(init.headers ?? {})) };
    api.calls.push(call);
    const custom = api.respond?.(call);
    if (custom) return custom;
    const body = url.pathname.endsWith("/board") ? { ...BOARD, version: api.version }
      : { schema: "stand-in", path: url.pathname, query: url.search, version: api.version, operator: "openai",
        items: [{ id: "r1", class: "declared_agent", operator: "openai", label: "declared_agent ab12" }] };
    return new Response(call.method === "HEAD" ? null : JSON.stringify(body), { status: 200,
      headers: { "content-type": "application/json", "cache-control": "no-store", etag: `"v${api.version}"`, "x-api": "stand-in" } });
  });
  return api;
}

// A fake caches.default backed by a Map keyed on the request URL. Like the Workers Cache API it keeps a copy only when
// the copy's own Cache-Control lets a shared cache keep it and it sets no cookie, and a match adds the headers workerd's
// match adds (age, cf-cache-status, content-length, date: seen under wrangler dev 4.156.0). Unlike it, it ignores
// max-age, so an entry's expiry is the Worker's own check. faults[op] is "throw" (synchronously) or "reject".
function installCache(t, faults = {}) {
  const entries = new Map();
  const ops = [];
  const keyOf = (key) => (typeof key === "string" ? key : key.url);
  const fail = (op) => {
    if (faults[op] === "throw") throw new Error(`${op}: cache down`);
    return faults[op] === "reject" ? Promise.reject(new Error(`${op}: cache down`)) : null;
  };
  const store = {
    match(key) {
      ops.push(["match", keyOf(key)]);
      return fail("match") ?? (async () => {
        const entry = entries.get(keyOf(key));
        if (!entry) return undefined;
        const headers = new Headers(entry.headers);
        headers.set("age", "1");
        headers.set("cf-cache-status", "HIT");
        headers.set("content-length", String(entry.bytes.byteLength));
        headers.set("date", new Date().toUTCString());
        return new Response(entry.bytes, { status: entry.status, headers });
      })();
    },
    put(key, response) {
      ops.push(["put", keyOf(key)]);
      return fail("put") ?? (async () => {
        if (typeof key !== "string" && key.method !== "GET") throw new TypeError("only a GET can be a key");
        if (response.status === 206) throw new TypeError("a 206 cannot be stored");
        const bytes = new Uint8Array(await response.arrayBuffer());
        if (/no-store|no-cache|private|max-age=0\b/i.test(response.headers.get("cache-control") ?? "") || response.headers.has("set-cookie")) return;
        entries.set(keyOf(key), { status: response.status, headers: [...response.headers], bytes });
      })();
    },
    delete(key) {
      ops.push(["delete", keyOf(key)]);
      return fail("delete") ?? Promise.resolve(entries.delete(keyOf(key)));
    },
  };
  globalThis.caches = { default: store };
  t.after(() => { delete globalThis.caches; });
  return { entries, ops, store, touched: (from) => ops.slice(from) };
}

const view = (r) => ({ status: r.status, headers: [...r.headers], text: r.text });
const header = (r, name) => r.headers.find(([n]) => n === name)?.[1] ?? null;
// One request with its waitUntil work settled (a put lands before the next request, as it does for polls 3 s apart).
async function get(s, path, init) {
  const r = await s.go(path, init);
  await s.drain();
  return view(r);
}
// The same request with no Cache API at all (node, some runtimes): what the proxy answered before the micro-cache.
async function uncached(s, path, init) {
  const saved = globalThis.caches;
  delete globalThis.caches;
  try { return await get(s, path, init); } finally { globalThis.caches = saved; }
}
function world(t, faults) {
  t.mock.timers.enable({ apis: ["Date"], now: T0 });
  return { api: installUpstream(t), cache: installCache(t, faults), s: setup() };
}

test("1. two identical GETs of each feed within 2 s: one upstream call, and both answers are the uncached answer (no-store)", async (t) => {
  const { api, cache, s } = world(t);
  for (const path of [...FEEDS, ...FEEDS.map((feed) => `${feed}?after=0`)]) {
    const before = await uncached(s, path);
    const calls = api.count(path);
    const first = await get(s, path);
    t.mock.timers.tick(1999);
    const second = await get(s, path);
    assert.equal(api.count(path) - calls, 1, `${path}: one upstream call for two GETs 1.999 s apart`);
    assert.equal(first.status, 200, path);
    assert.deepEqual(first, before, `${path}: the first answer is the uncached answer`);
    assert.deepEqual(second, before, `${path}: so is the second, from the cache: status, every header, body`);
    assert.equal(header(second, "cache-control"), "no-store", `${path}: the browser still gets no-store`);
    assert.ok(cache.entries.has(BASE + path), `${path}: kept under its full URL`);
  }
});

test("2. an entry 2 s old or older is a miss: the next GET goes upstream again, the stale entry is deleted", async (t) => {
  const { api, cache, s } = world(t);
  for (const feed of FEEDS) {
    const path = `${feed}?after=0`;
    const first = await get(s, path);
    t.mock.timers.tick(1999);
    assert.equal((await get(s, path)).text, first.text);
    assert.equal(api.count(path), 1, `${path}: at 1.999 s, the entry`);
    api.version += 1;  // the API's answer moves on
    t.mock.timers.tick(1);
    const fresh = await get(s, path);
    assert.equal(api.count(path), 2, `${path}: at 2 s, the API again`);
    assert.notEqual(fresh.text, first.text, `${path}: the API's new answer, not the old one`);
    assert.ok(cache.ops.some(([op, key]) => op === "delete" && key === BASE + path), `${path}: the stale entry is deleted`);
    t.mock.timers.tick(1999);
    assert.equal((await get(s, path)).text, fresh.text);
    assert.equal(api.count(path), 2, `${path}: the new answer is kept in its place`);
    t.mock.timers.tick(60_000);
    await get(s, path);
    assert.equal(api.count(path), 3, `${path}: a minute later, the API again`);
  }
});

test("2. a stale entry is never served, even when the API then fails: its 503 goes out, and the entry is gone", async (t) => {
  const { api, cache, s } = world(t);
  const path = "/api/open/v1/door/events?after=0";
  assert.equal((await get(s, path)).status, 200);
  api.respond = () => Response.json({ error: "busy" }, { status: 503, headers: { "retry-after": "5" } });
  t.mock.timers.tick(1000);
  assert.equal((await get(s, path)).status, 200, "within 2 s: the entry, and the API is not asked");
  assert.equal(api.count(path), 1);
  t.mock.timers.tick(1000);
  const failed = await get(s, path);
  assert.deepEqual([failed.status, header(failed, "retry-after")], [503, "5"]);
  assert.equal(api.count(path), 2);
  assert.ok(!cache.entries.has(BASE + path), "the stale entry is deleted");
  t.mock.timers.tick(100);
  assert.equal((await get(s, path)).status, 503, "and never comes back");
});

test("3. a request carrying X-Door-Nonce always goes upstream, never reads or writes the cache, and the API never sees it", async (t) => {
  const { api, cache, s } = world(t);
  for (const feed of FEEDS) {
    const path = `${feed}?after=0`;
    for (const name of ["x-door-nonce", "X-Door-Nonce"]) {
      const before = await uncached(s, path, { headers: { [name]: NONCE } });
      const [calls, ops] = [api.count(path), cache.ops.length];
      for (let i = 0; i < 2; i += 1) {
        assert.deepEqual(await get(s, path, { headers: { [name]: NONCE } }), before, `${path} with ${name}: the uncached answer`);
        assert.equal(api.calls.at(-1).headers["x-door-nonce"], undefined, `${path}: the nonce is stripped before the API, as before`);
      }
      assert.equal(api.count(path) - calls, 2, `${path} with ${name}: the API both times`);
      assert.deepEqual(cache.touched(ops), [], `${path} with ${name}: no match, put or delete`);
    }
    assert.ok(!cache.entries.has(BASE + path), `${path}: nothing kept`);
    await get(s, path);
    assert.ok(cache.entries.has(BASE + path), `${path}: a plain GET keeps an entry`);
    const [calls, ops] = [api.count(path), cache.ops.length];
    await get(s, path, { headers: { "x-door-nonce": NONCE } });
    assert.equal(api.count(path) - calls, 1, `${path}: a fresh entry is not served to a request carrying the nonce`);
    assert.deepEqual(cache.touched(ops), [], `${path}: nor read`);
  }
});

const NEVER_KEPT = [
  ["503 with Retry-After", () => Response.json({ error: "door_unavailable" }, { status: 503, headers: { "retry-after": "5", "cache-control": "no-store" } })],
  ["429 with Retry-After and no cache-control of its own", () => Response.json({ error: "rate_limited" }, { status: 429, headers: { "retry-after": "60" } })],
  ["400 invalid paging range", () => Response.json({ error: "invalid paging range" }, { status: 400, headers: { "cache-control": "no-store" } })],
  ["404", () => Response.json({ detail: "Not Found" }, { status: 404 })],
  ["500", () => Response.json({ error: "internal" }, { status: 500 })],
  ["206", () => Response.json({ partial: true }, { status: 206, headers: { "content-range": "bytes 0-9/100" } })],
  ["200 that is not JSON (the proxy's 502 unreadable_feed)", () => new Response("<html>", { status: 200, headers: { "content-type": "text/html" } })],
  ["204 (the proxy's 502 unreadable_feed)", () => new Response(null, { status: 204 })],
  ["200 that sets a cookie", () => Response.json({ ok: true, operator: "openai" }, { headers: { "set-cookie": "affinity=abc; Path=/", "cache-control": "no-store" } })],
];

test("4. non-200 answers and a 200 that sets a cookie are never kept, and pass on exactly as without the cache (Retry-After too)", async (t) => {
  const { api, cache, s } = world(t);
  for (const [why, answer] of NEVER_KEPT) {
    api.respond = answer;
    for (const feed of FEEDS) {
      const path = `${feed}?after=0`;
      const before = await uncached(s, path);
      const calls = api.count(path);
      const [one, two] = [await get(s, path), await get(s, path)];
      assert.equal(api.count(path) - calls, 2, `${why}, ${path}: the API both times`);
      assert.deepEqual(one, before, `${why}, ${path}: the uncached answer`);
      assert.deepEqual(two, before, `${why}, ${path}: the uncached answer again`);
      assert.ok(!cache.entries.has(BASE + path), `${why}, ${path}: nothing kept`);
    }
    assert.ok(!cache.ops.some(([op]) => op === "put"), `${why}: never offered to the cache`);
  }
  // The headers pass through: Retry-After, the API's own no-store, the proxy's no-store where the API set none.
  api.respond = NEVER_KEPT[1][1];
  const limited = await get(s, "/api/open/v1/door/board");
  assert.deepEqual([limited.status, header(limited, "retry-after"), header(limited, "cache-control")], [429, "60", "no-store"]);
  api.respond = NEVER_KEPT[0][1];
  const down = await get(s, "/api/open/v1/door/results?after=0");
  assert.deepEqual([down.status, header(down, "retry-after"), header(down, "cache-control")], [503, "5", "no-store"]);
  api.respond = NEVER_KEPT[6][1];
  const unreadable = await get(s, "/api/open/v1/door/events?after=0");
  assert.deepEqual([unreadable.status, JSON.parse(unreadable.text)], [502, { error: "unreadable_feed" }]);
  api.respond = NEVER_KEPT[8][1];
  const cookie = await get(s, "/api/open/v1/door/events?after=0");
  assert.equal(header(cookie, "set-cookie"), "affinity=abc; Path=/", "a cookie is passed on as before, to its own client only");
});

test("5. different queries are different entries: ?after=0 and ?after=88 each reach the API once and keep their own answer", async (t) => {
  const { api, cache, s } = world(t);
  for (const feed of ["/api/open/v1/door/results", "/api/open/v1/door/events"]) {
    const [a, b] = [`${feed}?after=0`, `${feed}?after=88`];
    const [ra, rb] = [await get(s, a), await get(s, b)];
    assert.notEqual(ra.text, rb.text, `${feed}: two answers`);
    t.mock.timers.tick(500);
    assert.deepEqual(await get(s, b), rb, `${feed}: ?after=88 from its own entry`);
    assert.deepEqual(await get(s, a), ra, `${feed}: ?after=0 from its own entry`);
    assert.deepEqual([api.count(a), api.count(b)], [1, 1], `${feed}: one call each`);
    assert.ok(cache.entries.has(BASE + a) && cache.entries.has(BASE + b), `${feed}: two entries`);
    // Any other spelling of a query is another URL: its own entry, never another query's answer.
    for (const other of [`${feed}?after=88&limit=5`, `${feed}?limit=5&after=88`, `${feed}?after=088`, feed]) {
      const r = await get(s, other);
      assert.equal(api.count(other), 1, `${other}: its own call`);
      assert.equal(JSON.parse(r.text).query, other.slice(feed.length), `${other}: its own answer`);
    }
  }
});

test("6. other paths, other spellings, HEAD, Range, token-bearing URLs: the API every time, the cache never read or written", async (t) => {
  const { api, cache, s } = world(t);
  for (const path of ["/api/open/v1/door/visitors", "/api/open/v1/door/visitors?after=0", "/api/open/v1/door/stats", "/api/view/runs", "/api/runs/x",
    "/api/runs", "/api/open/v1/door/status/x", "/api/open/v1/door/terms", "/api/open/v1/door/%62oard", "/api/open/v1/door/r%65sults?after=0",
    "/api/open/v1/door/results/", "/api/open/v1/door/board/x"]) {
    const before = await uncached(s, path);
    const [calls, ops] = [api.count(path), cache.ops.length];
    const [one, two] = [await get(s, path), await get(s, path)];
    assert.equal(api.count(path) - calls, 2, `${path}: the API both times`);
    assert.deepEqual(cache.touched(ops), [], `${path}: the cache untouched`);
    assert.deepEqual(one, before, `${path}: the uncached answer`);
    assert.deepEqual(two, before, `${path}: the uncached answer again`);
  }
  // Another spelling of a feed still passes the open-feed filter: no operator.
  assert.ok(!(await get(s, "/api/open/v1/door/%62oard")).text.includes("operator"));
  for (const feed of FEEDS) {
    await get(s, feed);
    assert.ok(cache.entries.has(BASE + feed), `${feed}: a fresh entry for the plain GET`);
    for (const [why, path, init] of [["HEAD", feed, { method: "HEAD" }], ["Range", feed, { headers: { range: "bytes=0-99" } }],
      ["a t parameter", `${feed}?t=spt1.read`, {}], ["a token-shaped value", `${feed}?after=0&x=spt1.abc`, {}]]) {
      const before = await uncached(s, path, init);
      const [calls, ops] = [api.count(path), cache.ops.length];
      const [one, two] = [await get(s, path, init), await get(s, path, init)];
      assert.equal(api.count(path) - calls, 2, `${why} ${feed}: the API both times, never the entry`);
      assert.deepEqual(cache.touched(ops), [], `${why} ${feed}: the cache untouched`);
      assert.deepEqual(one, before, `${why} ${feed}: the uncached answer`);
      assert.deepEqual(two, before, `${why} ${feed}: the uncached answer again`);
    }
  }
  // Other methods: the Worker's 405 before the proxy; nothing reaches the API or the cache.
  const [calls, ops] = [api.calls.length, cache.ops.length];
  for (const method of ["POST", "PUT", "DELETE", "PATCH", "OPTIONS"]) {
    for (const feed of FEEDS) {
      const r = await get(s, feed, { method, body: "{}" });
      assert.deepEqual([r.status, JSON.parse(r.text).error], [405, "read_only"], `${method} ${feed}`);
    }
  }
  assert.equal(api.calls.length - calls, 0, "no call reached the API");
  assert.deepEqual(cache.touched(ops), [], "and the cache was untouched");
});

test("6. with the API switched off (no origin, or none) every feed answers 503, never a kept 200, and the cache is untouched", async (t) => {
  const { api, cache, s } = world(t);
  for (const feed of FEEDS) await get(s, feed);
  assert.equal(cache.entries.size, 3, "fresh entries for all three feeds");
  const ops = cache.ops.length;
  for (const origin of [undefined, "none"]) {
    const off = setup({ API_ORIGIN: origin });
    for (const feed of FEEDS) {
      for (let i = 0; i < 2; i += 1) {
        const r = await get(off, feed);
        assert.deepEqual([r.status, r.text], [503, "API origin not configured"], `${feed} (API_ORIGIN ${origin})`);
      }
    }
  }
  // A path whose escapes do not decode: 400 bad_path, before the cache too.
  assert.equal((await get(s, "/api/open/v1/door/%E0%A4%A")).status, 400);
  assert.deepEqual(cache.touched(ops), []);
  assert.equal(api.calls.length, 3);
});

test("7. a cache whose match, put or delete throws or rejects still gives the normal upstream answer", async (t) => {
  t.mock.timers.enable({ apis: ["Date"], now: T0 });
  const api = installUpstream(t);
  const s = setup();
  for (const faults of [{ match: "throw" }, { match: "reject" }, { put: "throw" }, { put: "reject" }, { match: "reject", put: "throw" }]) {
    const cache = installCache(t, faults);
    for (const feed of FEEDS) {
      const path = `${feed}?after=0`;
      const before = await uncached(s, path);
      const calls = api.count(path);
      const [one, two] = [await get(s, path), await get(s, path)];
      assert.deepEqual(one, before, `${JSON.stringify(faults)} ${path}: the uncached answer`);
      assert.deepEqual(two, before, `${JSON.stringify(faults)} ${path}: the uncached answer again`);
      assert.equal(api.count(path) - calls, 2, `${JSON.stringify(faults)} ${path}: nothing usable kept, so the API both times`);
    }
    assert.ok(cache.ops.length > 0, `${JSON.stringify(faults)}: the cache was tried`);
  }
  // A delete that fails: the stale entry is still a miss.
  for (const fault of ["throw", "reject"]) {
    const cache = installCache(t, { delete: fault });
    const path = `/api/open/v1/door/board?fault=${fault}`;
    await get(s, path);
    api.version += 1;
    t.mock.timers.tick(2500);
    const r = await get(s, path);
    assert.equal(api.count(path), 2, `delete ${fault}s: the API again`);
    assert.equal(JSON.parse(r.text).version, api.version, `delete ${fault}s: the API's answer`);
    assert.ok(cache.ops.some(([op]) => op === "delete"));
    t.mock.timers.tick(1000);
    assert.equal((await get(s, path)).text, r.text);
    assert.equal(api.count(path), 2, `delete ${fault}s: the new answer is still kept`);
  }
});

test("7. no caches.default, or one without its methods: nothing is cached, the normal answer", async (t) => {
  t.mock.timers.enable({ apis: ["Date"], now: T0 });
  const api = installUpstream(t);
  const s = setup();
  for (const caches of [{}, { default: null }, { default: {} }, { default: { match: 1, put: 1 } }]) {
    globalThis.caches = caches;
    t.after(() => { delete globalThis.caches; });
    for (const feed of FEEDS) {
      const calls = api.count(feed);
      const [one, two] = [await get(s, feed), await get(s, feed)];
      assert.deepEqual([one.status, two.status], [200, 200], `${JSON.stringify(caches)} ${feed}`);
      assert.equal(two.text, one.text);
      assert.equal(api.count(feed) - calls, 2, `${JSON.stringify(caches)} ${feed}: the API both times`);
    }
  }
});

test("7. an entry the Worker did not write (no stamp, a stamp ahead of the clock, no or bad headers) is a miss, and deleted", async (t) => {
  const { api, cache, s } = world(t);
  const forged = (extra) => ({ status: 200, headers: [["content-type", "application/json"], ...extra], bytes: utf8('{"forged":true}') });
  const cases = [
    ["no private headers", []],
    ["no stamp, a headers list", [[SENT, '[["content-type","application/json"]]']]],
    ["a fresh stamp, no headers list", [[MADE, String(T0)]]],
    ["a fresh stamp, a headers list that is not JSON", [[MADE, String(T0)], [SENT, "{not json"]]],
    ["a fresh stamp, a headers list that is not a list", [[MADE, String(T0)], [SENT, '{"cache-control":"public"}']]],
    ["a stamp ahead of the clock", [[MADE, String(T0 + 5000)], [SENT, '[["content-type","application/json"]]']]],
    ["a stamp that is not a number", [[MADE, "soon"], [SENT, '[["content-type","application/json"]]']]],
  ];
  for (const [i, [why, extra]] of cases.entries()) {
    const path = `/api/open/v1/door/events?after=${i}`;
    cache.entries.set(BASE + path, forged(extra));
    const before = await uncached(s, path);
    const r = await get(s, path);
    assert.deepEqual(r, before, `${why}: the API's answer, not the entry`);
    assert.ok(!r.text.includes("forged"), why);
    assert.ok(cache.ops.some(([op, key]) => op === "delete" && key === BASE + path), `${why}: deleted`);
    assert.ok(!new TextDecoder().decode(cache.entries.get(BASE + path).bytes).includes("forged"), `${why}: replaced by the API's answer`);
  }
});

test("8. nothing private reaches a browser and nothing the cache adds; the operator stays stripped; the copy is public, max-age=2", async (t) => {
  const { api, cache, s } = world(t);
  for (const feed of FEEDS) {
    const made = Date.now();
    const pending = s.pending.length;
    const miss = view(await s.go(feed));
    assert.equal(s.pending.length - pending, 1, `${feed}: the put rides ctx.waitUntil`);
    await s.drain();
    t.mock.timers.tick(10);
    const hit = await get(s, feed);
    assert.equal(api.count(feed), 1, `${feed}: the second answer came from the cache`);
    const entry = cache.entries.get(BASE + feed);
    const stored = new Headers(entry.headers);
    // The stored copy: kept for 2 s, stamped with the time its API request started, and the browser's headers.
    assert.equal(stored.get("cache-control"), "public, max-age=2", feed);
    assert.equal(stored.get(MADE), String(made), `${feed}: the stamp`);
    assert.deepEqual(JSON.parse(stored.get(SENT)), miss.headers, `${feed}: the browser's headers, exactly`);
    assert.ok(!new TextDecoder().decode(entry.bytes).includes("operator"), `${feed}: the stored copy has no operator either`);
    for (const [why, r] of [["miss", miss], ["hit", hit]]) {
      const names = r.headers.map(([name]) => name);
      for (const name of [MADE, SENT, "age", "cf-cache-status", "content-length", "date"]) assert.ok(!names.includes(name), `${feed} ${why}: no ${name}`);
      // Every header the stored copy has and the browser's answer had not is private: never in the browser's answer.
      for (const name of stored.keys()) if (!miss.headers.some(([n]) => n === name)) assert.ok(!names.includes(name), `${feed} ${why}: no ${name}`);
      assert.ok(!r.text.includes("operator"), `${feed} ${why}: the operator stays stripped`);
      assert.deepEqual([header(r, "cache-control"), header(r, "content-type"), header(r, "x-content-type-options"), header(r, "etag")],
        ["no-store", "application/json", "nosniff", null], `${feed} ${why}: the open-feed filter's headers`);
    }
    assert.deepEqual(hit, miss, `${feed}: the hit is the miss, byte for byte`);
    assert.equal(JSON.parse(hit.text).version, 1);
  }
  // A board answer from the cache still has its rows, without the operator at any depth.
  const board = JSON.parse((await get(s, "/api/open/v1/door/board")).text);
  assert.deepEqual(board.top.map((row) => row.id), BOARD.top.map((row) => row.id));
  assert.ok(board.top.every((row) => !("operator" in row)));
});

test("8. without a ctx the answer still comes, and the copy is still kept", async (t) => {
  const { api, cache, s } = world(t);
  const path = "/api/open/v1/door/results?after=0";
  const before = await uncached(s, path);
  const res = await worker.fetch(new Request(BASE + path), s.env, undefined);
  assert.deepEqual(view({ status: res.status, headers: res.headers, text: await res.text() }), before);
  for (let i = 0; i < 50 && !cache.entries.has(BASE + path); i += 1) await new Promise((resolve) => setImmediate(resolve));
  assert.ok(cache.entries.has(BASE + path), "kept without waitUntil");
  const again = await worker.fetch(new Request(BASE + path), s.env, undefined);
  assert.equal(await again.text(), before.text);
  assert.equal(api.count(path), 2, "the uncached baseline and the first GET; the second came from the cache");
});
