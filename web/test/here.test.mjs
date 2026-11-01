// The lab pages' heartbeat module (web/public/sentilab/here.mjs; AGENT-DOOR Amendment 4 rev 2, section 4.3): exactly
// {page, tab} to the door's path, no cookie and no Referer, at most once a minute and only while visible, one random tab
// id per page start held in memory only, and the page line in the spec's words.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { ACTIVE_LABEL, HERE_LINE, HERE_PATH, INTERVAL_MS, PAGES, newTabId, startHeartbeat } from "../public/sentilab/here.mjs";

// A page: its visibility, its listeners, a clock and timers that run only when the test advances them.
function world({ visible = true } = {}) {
  let now = 1793561460000;
  let nextId = 1;
  const timers = new Map();
  const listeners = new Set();
  const sent = [];
  let counter = 0;
  const doc = {
    visibilityState: visible ? "visible" : "hidden",
    addEventListener: (type, fn) => { assert.equal(type, "visibilitychange"); listeners.add(fn); },
    removeEventListener: (type, fn) => { listeners.delete(fn); },
  };
  const env = {
    doc, sent, listeners, pending: timers,
    now: () => now,
    timers: {
      setTimeout: (fn, ms) => { const id = nextId++; timers.set(id, { fn, at: now + ms }); return id; },
      clearTimeout: (id) => { timers.delete(id); },
    },
    send: (path, init) => { sent.push({ at: now, path, init }); return Promise.resolve(new Response(null, { status: 204 })); },
    random: { getRandomValues: (bytes) => { for (let i = 0; i < bytes.length; i += 1) bytes[i] = (counter++ * 37 + 11) & 0xff; return bytes; } },
    // Run every timer due by now + ms, in order, moving the clock to each. A heartbeat that reschedules itself with no
    // interval would loop forever here: that is a failure, not a hang.
    advance(ms) {
      const end = now + ms;
      for (let fired = 0; ; fired += 1) {
        assert.ok(fired < 10000, "runaway timers: heartbeats with no interval between them");
        const due = [...timers].filter(([, t]) => t.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
        if (!due) break;
        timers.delete(due[0]);
        now = Math.max(now, due[1].at);
        due[1].fn();
      }
      now = end;
    },
    show(visibleNow) {
      doc.visibilityState = visibleNow ? "visible" : "hidden";
      for (const fn of [...listeners]) fn();
    },
  };
  return env;
}
const start = (page, w) => startHeartbeat(page, { doc: w.doc, send: w.send, timers: w.timers, now: w.now, random: w.random });

test("a visible page sends exactly {page, tab} at once, then once a minute, with no cookie and no Referer", () => {
  const w = world();
  const heartbeat = start("live", w);
  w.advance(0);
  assert.equal(w.sent.length, 1);
  const [first] = w.sent;
  assert.equal(first.path, HERE_PATH);
  assert.equal(first.path, "/api/open/v1/door/here");
  assert.deepEqual(JSON.parse(first.init.body), { page: "live", tab: heartbeat.tab });
  assert.deepEqual(Object.keys(JSON.parse(first.init.body)), ["page", "tab"]);
  assert.deepEqual(first.init.headers, { "content-type": "application/json" });
  assert.equal(first.init.method, "POST");
  assert.equal(first.init.credentials, "omit");
  assert.equal(first.init.referrerPolicy, "no-referrer");
  assert.equal(first.init.cache, "no-store");
  w.advance(INTERVAL_MS - 1);
  assert.equal(w.sent.length, 1);
  w.advance(1);
  assert.equal(w.sent.length, 2);
  w.advance(INTERVAL_MS * 3);
  assert.equal(w.sent.length, 5);
  assert.ok(w.sent.every((s) => JSON.parse(s.init.body).tab === heartbeat.tab), "one tab id for the page's life");
  for (let i = 1; i < w.sent.length; i += 1) assert.equal(w.sent[i].at - w.sent[i - 1].at, INTERVAL_MS);
  assert.equal(INTERVAL_MS, 60000);
});

test("a hidden page sends nothing; coming back sends at once only if a minute has passed", () => {
  const w = world({ visible: false });
  start("board", w);
  assert.equal(w.pending.size, 0, "nothing is scheduled while hidden: no wake-ups");
  w.advance(INTERVAL_MS * 5);
  assert.equal(w.sent.length, 0);
  w.show(true);
  w.advance(0);
  assert.equal(w.sent.length, 1);
  w.advance(10000);
  w.show(false);
  assert.equal(w.pending.size, 0, "hiding cancels the next heartbeat");
  w.advance(INTERVAL_MS * 2);
  assert.equal(w.sent.length, 1, "nothing while hidden");
  w.show(true);                                       // more than a minute since the last: at once
  w.advance(0);
  assert.equal(w.sent.length, 2);
  w.advance(5000);
  w.show(false);
  w.show(true);                                       // 5 s since the last: waits for the rest of the minute
  w.advance(0);
  assert.equal(w.sent.length, 2);
  w.advance(INTERVAL_MS - 5000 - 1);
  assert.equal(w.sent.length, 2);
  w.advance(1);
  assert.equal(w.sent.length, 3);
  for (let i = 0; i < 6; i += 1) { w.show(false); w.show(true); }   // flipping visibility never sends faster
  w.advance(0);
  assert.equal(w.sent.length, 3);
});

test("stop ends it: no more heartbeats, no listener, no timer", () => {
  const w = world();
  const heartbeat = start("results", w);
  w.advance(0);
  heartbeat.stop();
  w.advance(INTERVAL_MS * 3);
  w.show(true);
  assert.equal(w.sent.length, 1);
  assert.equal(w.listeners.size, 0);
  assert.equal(w.pending.size, 0);
});

test("each page start has its own random tab id of 128 bits", () => {
  // Both with the platform's own random source (no test random).
  const page = () => { const w = world(); return startHeartbeat("wall", { doc: w.doc, send: w.send, timers: w.timers, now: w.now }); };
  const a = page();
  const b = page();
  for (const h of [a, b]) assert.match(h.tab, /^[0-9a-f]{32}$/);
  assert.notEqual(a.tab, b.tab);
  a.stop();
  b.stop();
  assert.match(newTabId(), /^[0-9a-f]{32}$/);
  const seen = new Set(Array.from({ length: 200 }, () => newTabId()));
  assert.equal(seen.size, 200);
});

test("only the five lab pages, and a failing send never breaks the page", () => {
  assert.deepEqual(PAGES, ["wall", "package3d", "live", "board", "results"]);
  for (const page of ["", "Live", "live ", "home", "admin", undefined]) assert.throws(() => start(page, world()), /not a lab page/);
  for (const send of [() => { throw new Error("offline"); }, () => Promise.reject(new Error("down")), () => undefined]) {
    const w = world();
    const heartbeat = startHeartbeat("package3d", { doc: w.doc, send, timers: w.timers, now: w.now, random: w.random });
    assert.doesNotThrow(() => w.advance(INTERVAL_MS * 2));
    heartbeat.stop();
  }
});

test("the tab id lives in memory only: the module never touches cookies or storage", () => {
  const source = readFileSync(new URL("../public/sentilab/here.mjs", import.meta.url), "utf8");
  const code = source.split("\n").filter((line) => !line.trim().startsWith("//")).join("\n");
  for (const word of ["cookie", "localStorage", "sessionStorage", "indexedDB", "caches", "navigator", "location", "referrer:", "document.referrer"]) {
    assert.ok(!code.includes(word), word);
  }
});

// The page text: aneta's plainer version (#57921) with root's two 09:01Z edits, as the coordinator gave it; then one
// sentence for the limiter that ships (the platform's rate-limit binding). Each clause is checked against the code:
// app/door/presence.py (the 120 s window, the 1 s sweeper, the daily digest set ended at the first cleanup after 00:00
// UTC, memory only) and web/src/door/door.js (DOOR_HERE_LIMITER, keyed by the /24 or /48 prefix, 60 s period).
const PAGE_TEXT = "We count active tabs, not people. While a tab is open, we keep its random id, its page, a guess at its type and the time it last checked in. Inactive entries are removed by a scheduled cleanup after the two-minute window. We keep a keyed digest of the tab id until the next cleanup after 00:00 UTC, so we don't count that tab twice today. Restarting the API clears these records. Our hosting provider's network logs may record IP addresses.";
const LIMITER_TEXT = "To limit heartbeats, we pass your network address prefix to our hosting provider's rate-limit service, which counts them in one-minute windows; we keep no copy, and the provider's own policy governs how long its service keeps those counts.";

test("the page line is the agreed text plus one limiter sentence, and the label says tabs", () => {
  assert.equal(HERE_LINE, `${PAGE_TEXT} ${LIMITER_TEXT}`);
  assert.ok(!/nothing else about you/.test(HERE_LINE), "the retired claim is gone");
  assert.equal(ACTIVE_LABEL, "active tabs (last 2 min)");
  assert.ok(!/humans online/i.test(`${HERE_LINE} ${ACTIVE_LABEL}`));
  assert.ok(HERE_LINE.startsWith("We count active tabs, not people."));
});
