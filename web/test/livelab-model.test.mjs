// node --test web/test/livelab-model.test.mjs
// The Live Lab page (web/public/sentilab/live) on answers recorded from production's public API
// (web/test/fixtures/livelab, see capture.json): it reaches the same geometry, result and receipt as the Package view,
// switching runs never keeps the old run's field or value, a failing feed never reads LIVE, and a run finishing never
// moves a visitor (location and task stay apart).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as M from "../public/sentilab/live/live-model.mjs";
import { createDoorFeed, fetchDoorResults, normalizeResults, normalizeEvents, mergeArrivals, withPositions, mergeEvents, normalizeReplay,
  verifyPinnedFields, LIVE_FRESH_MS, REPLAY_SCHEMA } from "../public/sentilab/package/source3d.mjs";
import { buildRenderModel } from "../public/sentilab/package/model.mjs";
import { formatTemp } from "../public/sentilab/package/temps.mjs";
import { LABELS } from "../public/temperature-label.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const FIX = join(HERE, "fixtures", "livelab");
const bytes = (name) => readFileSync(join(FIX, name));
const doc = (name) => JSON.parse(bytes(name).toString("utf8"));

test("the fixtures are the recorded answers, byte for byte (capture.json)", () => {
  const cap = doc("capture.json");
  for (const [name, sum] of Object.entries(cap.sha256)) assert.equal(createHash("sha256").update(bytes(name)).digest("hex"), sum, name);
});

// A fetch that answers the four public GETs from the recorded bytes, honouring the cursor, or with an error status.
function recordedFetch({ status = () => 200, log = [] } = {}) {
  return async (url, init = {}) => {
    const u = new URL(url, "https://sentilab.example");
    log.push({ path: u.pathname, method: init.method ?? "GET" });
    const code = status(u.pathname);
    if (code !== 200) return new Response(JSON.stringify({ error: "down" }), { status: code });
    const name = { "/api/open/v1/door/results": "results.json", "/api/open/v1/door/events": "events.json", "/api/open/v1/door/board": "board.json",
      "/api/view/runs": "view_runs.json" }[u.pathname];
    if (!name) return new Response("not found", { status: 404 });
    let body = bytes(name);
    const after = Number(u.searchParams.get("after") ?? 0);
    if (name === "results.json" || name === "events.json") {
      const d = doc(name);
      if (after >= d.next_after) body = Buffer.from(JSON.stringify({ ...d, [name === "results.json" ? "items" : "events"]: [], has_more: false }));
    }
    return new Response(body, { status: 200, headers: { "content-type": "application/json" } });
  };
}
async function liveFeed(fetchImpl, now = () => Date.now()) {
  const feed = createDoorFeed({ fetchImpl, now, fetchEvents: M.fetchEventsTimed });
  return feed;
}

test("the live API data reaches the same geometry, result and receipt as /sentilab/package/", async () => {
  const log = [];
  const feed = await liveFeed(recordedFetch({ log }));
  assert.equal(await feed.pollOnce(), 3000, "a good poll");
  assert.ok(log.every((r) => r.method === "GET"), "read-only");
  // The Package view's own path: the same normalizer, merge and positions over the same answer.
  const pkg = normalizeResults(doc("results.json"));
  const pkgLayouts = withPositions(mergeArrivals([], pkg.layouts));
  assert.equal(feed.state.layouts.length, 9);
  assert.deepEqual(feed.state.layouts, pkgLayouts, "the same layouts, field for field");
  const raw = new Map(doc("results.json").items.map((x) => [x.id, x]));
  for (const L of feed.state.layouts) {
    // Geometry: the same RenderModel (its geometry key covers every drawn box) as the Package view builds for the run.
    const live = buildRenderModel({ kind: "model", layout: L });
    const theirs = buildRenderModel({ kind: "model", layout: pkgLayouts.find((x) => x.id === L.id) });
    assert.equal(live.error, null);
    assert.equal(live.model.geometry_key, theirs.model.geometry_key, `${L.label} geometry`);
    // The dies drawn are the item's own, in micrometres, die i = TAP die i.
    for (const d of raw.get(L.id).dies) {
      const mine = L.dies[d.die];
      assert.deepEqual([mine.x_um, mine.y_um, mine.rot_deg], [d.x_um, d.y_um, d.rot_deg], `${L.label} die ${d.die}`);
    }
    // Result: the scorer's value under its board metric, formatted exactly as the Package view's caption does.
    const v = M.runView(L);
    const r = raw.get(L.id).result;
    assert.equal(L.result.metric.value, r.max_chiplet_centre_cell_mean_C);
    assert.deepEqual(v.metric, formatTemp(r.max_chiplet_centre_cell_mean_C, L.result.label, { digits: 2 }));
    assert.equal(L.result.label, LABELS.unvalidated, "a feed result is never more than unvalidated");
    assert.equal(v.metric.qualifier, "unvalidated");
    assert.equal(v.claim, "simulated, not silicon");
    assert.equal(v.diagnostic, true);
    assert.deepEqual(v.distinct.map((d) => [d.key, d.value]), [["native_all_block_max_C", r.native_all_block_max_C], ["active_layer_peak_C", r.active_layer_peak_C]]);
    // Receipt: the checks the feed reports, unchanged.
    const rc = M.receiptOf(L);
    assert.equal(rc.result.value_C, r.max_chiplet_centre_cell_mean_C);
    assert.deepEqual(rc.result.verification, { replay: r.verification.replay, replay_code: r.verification.replay_code, cpu: r.verification.cpu,
      distinct_execution: r.verification.distinct_execution, receipts_bound: r.verification.receipts_bound, binding_ok: r.verification.binding_ok,
      active_guard_ok: r.verification.active_guard_ok, candidate: r.verification.candidate, not_claimed: r.verification.not_claimed });
    assert.deepEqual(rc.result.replay, r.replay);
    assert.equal(rc.result.field, "unassociated");
    assert.equal(JSON.stringify(rc).includes(L.id), false, "the run id is a key only, never shown");
  }
  const newest = M.pickRun(feed.state.layouts, null);
  assert.equal(newest.label, "unknown · 5cb8");
  assert.equal(M.runView(newest).metric.text, "113.23 °C");
  // Events: the Package view's events, plus the server's own time and nothing else.
  const theirEvents = mergeEvents([], normalizeEvents(doc("events.json")).events);
  assert.deepEqual(feed.state.events.map(({ at, ...e }) => e), theirEvents);
  const rawAt = new Map(doc("events.json").events.map((e) => [e.seq, e.at]));
  for (const e of feed.state.events) assert.equal(e.at, rawAt.get(e.seq));
});

test("switching runs clears the old field and the old value at once", async () => {
  // A run with a verified field: the Package view's bundled raw reference, its pinned field checked with WebCrypto.
  const fixture = JSON.parse(readFileSync(join(HERE, "..", "public", "sentilab", "package", "door-fixture.json"), "utf8"));
  assert.equal(fixture.schema, REPLAY_SCHEMA);
  const checked = await verifyPinnedFields(normalizeReplay(fixture).layouts, { subtle: globalThis.crypto.subtle });
  const withField = checked.find((L) => L.result?.field_state === "verified");
  assert.ok(withField, "the bundled reference has a verified field");
  const before = M.fieldOverlay(withField);
  assert.equal(before.available, true);
  assert.match(before.key, /^[0-9a-f]{64}$/);
  // The live runs: none carries a field; selecting one after the reference shows no field and only its own value.
  const feed = await liveFeed(recordedFetch());
  await feed.pollOnce();
  const list = [withField, ...feed.state.layouts];
  for (const L of feed.state.layouts) {
    const picked = M.pickRun(list, L.id);
    assert.equal(picked, L);
    const v = M.runView(picked);
    assert.deepEqual(v.field, { available: false, key: null, reason: "Field overlay unavailable: the door feed carries a scalar result, no temperature field for this layout" });
    assert.notEqual(v.metric.text, M.runView(withField).metric.text);
    assert.equal(v.id, L.id);
  }
  // And back: the reference's own field returns only with the reference.
  assert.equal(M.runView(M.pickRun(list, withField.id)).field.available, true);
  // A run that left the feed is not kept selected: the page falls back to a run it has, never to stale content.
  assert.equal(M.pickRun(feed.state.layouts, "open-00000000-00000000000000000000000000000000").label, "unknown · 5cb8");
  // A replay cursor at one of a run's records shows that record's state and no value (a record carries none).
  const L = feed.state.layouts[0];
  const atQueued = M.runView(L, { at: { kind: "run", run_id: L.id, state: "queued", seq: 1, at: null } });
  assert.equal(atQueued.metric, null);
  assert.match(atQueued.none, /state at this record: queued/);
  assert.equal(M.runView(L, { at: { kind: "run", run_id: L.id, state: "reproduced", seq: 2, at: null } }).metric, null);
  // A cursor at another run's record changes nothing for this run.
  assert.equal(M.runView(L, { at: { kind: "run", run_id: "open-00000000-00000000000000000000000000000000", state: "queued" } }).metric.text, M.runView(L).metric.text);
});

test("a feed error never shows LIVE; stale and empty are explicit", async () => {
  const host = { hostname: "sentilab.aidenid.com" };
  assert.equal(M.feedStatus({ connected: null, lastOkAt: null, layouts: [], events: [] }, host).state, "connecting");
  let t = 1_000_000;
  const now = () => t;
  // Every sequence of four polls, each answering or failing (503, unreachable, or not a door page).
  const failures = [() => new Response("{}", { status: 503 }), () => { throw new TypeError("offline"); },
    () => new Response("<html>", { status: 200 }), () => new Response(JSON.stringify({ schema: "something-else/1" }), { status: 200 })];
  for (const fail of failures) {
    for (let mask = 0; mask < 16; mask += 1) {
      let ok = false;
      const good = recordedFetch();
      const feed = await liveFeed(async (url, init) => (ok ? good(url, init) : fail()), now);
      for (let k = 0; k < 4; k += 1) {
        ok = Boolean(mask & (1 << k));
        t += 3000;
        await feed.pollOnce();
        const st = M.feedStatus(feed.state, { ...host, nowMs: t });
        if (!ok) assert.notEqual(st.state, "live", `mask ${mask} poll ${k}: a failed poll never reads LIVE`);
        if (!ok) assert.equal(st.state, feed.state.lastOkAt === null ? "error" : "stale", `mask ${mask} poll ${k}`);
        if (ok) assert.equal(st.state, "live", `mask ${mask} poll ${k}`);
        if (!ok) assert.notEqual(st.word, "LIVE", "never the word LIVE after a failure");
      }
    }
  }
  // A good answer that has aged past the freshness window is stale, not live (a hung request, a hidden tab).
  const feed = await liveFeed(recordedFetch(), now);
  await feed.pollOnce();
  assert.equal(M.feedStatus(feed.state, { ...host, nowMs: t }).state, "live");
  assert.equal(M.feedStatus(feed.state, { ...host, nowMs: t }).word, "LIVE");
  assert.equal(M.feedStatus(feed.state, { ...host, nowMs: t + LIVE_FRESH_MS + 1 }).state, "stale");
  // On a staging host (or this machine) live data reads STAGING, by the shared rule; on production LIVE.
  assert.equal(M.feedStatus(feed.state, { hostname: "staging.sentilab.aidenid.com", nowMs: t }).word, "STAGING");
  assert.equal(M.feedStatus(feed.state, { hostname: "127.0.0.1", nowMs: t }).word, "STAGING");
  // Connected with no records: empty, said so.
  const empty = await liveFeed(async (url) => {
    const u = new URL(url, "https://x");
    const d = u.pathname.endsWith("/results") ? { ...doc("results.json"), items: [], next_after: 0 } : { ...doc("events.json"), events: [], next_after: 0 };
    return new Response(JSON.stringify(d), { status: 200 });
  }, now);
  await empty.pollOnce();
  assert.deepEqual([M.feedStatus(empty.state, { ...host, nowMs: t }).state, M.feedStatus(empty.state, { ...host, nowMs: t }).word], ["empty", "NO RECORDS YET"]);
});

test("the board: door, scorer, queue and budget from their own fields; anything else unavailable", async () => {
  const b = M.normalizeBoard(doc("board.json"));
  assert.deepEqual(b.door, { open: true, codes: [] });
  assert.deepEqual(b.scorer, { state: "up", since: doc("board.json").scorer.since });
  assert.deepEqual(b.queue, { length: 0, max: 30, active: 0, parallel: 3 });
  assert.deepEqual(b.budget, { cap_s: 3540, charged_s: 29.07806, remaining_s: 3510.92194, reserved_s: 0 });
  assert.equal(M.normalizeBoard({ ...doc("board.json"), schema: "x" }), null);
  const partial = M.normalizeBoard({ schema: M.BOARD_SCHEMA, door: { open: "yes" }, queue: { length: -1 }, grant: null });
  assert.deepEqual(partial, { door: null, scorer: { state: "unknown", since: null }, queue: null, budget: null });
  assert.deepEqual(await M.fetchBoard({ fetchImpl: recordedFetch({ status: () => 503 }) }), { ok: false, error: "answered 503" });
  assert.equal((await M.fetchBoard({ fetchImpl: recordedFetch() })).ok, true);
  // The lab-runs list is not read at all (/api/view/runs is slow in production; web/test/livelab-load.test.mjs).
  assert.equal("fetchLabRuns" in M || "labRunsLine" in M || "RUNS_POLL_MS" in M, false);
});

test("follow the work: full run ids and classes only; a finished run never moves its submission", async () => {
  const feed = await liveFeed(recordedFetch());
  await feed.pollOnce();
  const { runs, door, anonymous } = M.followWork(feed.state.events, feed.state.layouts);
  assert.equal(runs.length, new Set(runs.map((r) => r.run_id)).size, "one row per full run id");
  for (const L of feed.state.layouts) assert.ok(runs.some((r) => r.run_id === L.id), `${L.label} has its row`);
  for (const r of runs) {
    assert.match(r.run_id, /^open-[0-9a-f]{8}-[0-9a-f]{32}$/);
    assert.match(r.label, /^[a-z_]+ · [0-9a-f]{4}$/, "a class and a 4-hex short id, never a name");
  }
  for (const d of door) assert.match(d.label, /^[a-z_]+ · [0-9a-f]{4}$/);
  for (const a of anonymous) assert.ok(a.count > 0 && !("short" in a));
  // Arrive, submit, then the scorer's work: the run's submission stays where it was; only its task follows the run.
  const base = { cls: "unknown", short: "abcd", label: "unknown · abcd" };
  const run = "open-00000001-00000000000000000000000000000001";
  const ev = [
    { ...base, seq: 1, kind: "arrival", at: "2026-11-01T10:00:00Z" },
    { ...base, seq: 2, kind: "run", run_id: run, state: "queued", codes: [], at: "2026-11-01T10:00:05Z" },
    { ...base, seq: 3, kind: "run", run_id: run, state: "evaluating", codes: [], at: "2026-11-01T10:00:09Z" },
    { ...base, seq: 4, kind: "run", run_id: run, state: "reproduced", codes: [], at: "2026-11-01T10:01:00Z" },
  ];
  const [row] = M.followWork(ev, []).runs;
  assert.deepEqual([row.submitted.seq, row.submitted.at], [2, "2026-11-01T10:00:05Z"]);
  assert.deepEqual([row.task.state, row.task.seq], ["reproduced", 4]);
  // A reordered page gives the same answer.
  assert.deepEqual(M.followWork([...ev].reverse(), []), M.followWork(ev, []));
});

test("the atlas and the flight record count real records only", async () => {
  const feed = await liveFeed(recordedFetch());
  await feed.pollOnce();
  const a = M.atlas(feed.state.layouts, feed.state.events);
  const by = Object.fromEntries(a.stations.map((s) => [s.id, s.count]));
  const statuses = feed.state.layouts.map((l) => l.status);
  assert.equal(by.board, statuses.filter((s) => ["reproduced", "not_reproduced", "cross_checked"].includes(s)).length);
  assert.equal(by.door, feed.state.events.filter((e) => e.kind === "arrival").length);
  assert.equal(by.submit, feed.state.events.filter((e) => e.kind === "attempt").length);
  assert.equal(a.stations.reduce((n, s) => n + s.runs.length, 0) + a.out.length, feed.state.layouts.length);
  const tr = M.traceModel(feed.state.events);
  assert.equal(tr.points.length, feed.state.events.length);
  assert.deepEqual(tr.points.map((p) => p.seq), [...feed.state.events].map((e) => e.seq).sort((x, y) => x - y));
  assert.equal(M.hms(tr.last.at), `${doc("events.json").events.at(-1).at.slice(11, 19)}Z`);
  assert.equal(M.clampCursor(null, 5), null);
  assert.equal(M.clampCursor(9, 5), 4);
  assert.equal(M.clampCursor(2, 0), null);
  assert.equal(M.readAt("2026-11-01T15:21:02.558110Z"), "2026-11-01T15:21:02.558110Z");
  for (const bad of ["2026-11-01 15:21:02Z", "<b>", 12, null, "2026-13-45T99:99:99Z"]) assert.equal(M.readAt(bad), null, String(bad));
});

// ── review P2s (root, at 2eb51527) ─────────────────────────────────────────────────────────────────────────────────
// P2-1: without WebGL2 the page draws the selected run in 2D (the Package view's renderer) and disables the 3D-only
// controls. The 2D input is exactly the run's dies, as the Package view's 2D path builds it.
test("P2-1: the 2D fallback draws the selected run's own dies, and the 3D-only controls are off", async () => {
  const { dieRects } = await import("../public/sentilab/package/model.mjs");
  const feed = await liveFeed(recordedFetch());
  await feed.pollOnce();
  for (const L of feed.state.layouts) {
    const chips = M.chiplets2d(L);
    const rects = dieRects(L.dies);
    assert.equal(chips.length, 8);
    assert.deepEqual(chips.map((c) => [c.id, c.x, c.y, c.w, c.h, c.layer, c.temp]), rects.map((r) => [r.id, r.x0, r.y0, r.w, r.h, 0, null]), L.label);
  }
  assert.deepEqual(M.FOOTPRINT_2D.interposer, { x0: 0, y0: 0, x1: 45, y1: 45 });
  assert.deepEqual(M.viewControls("2d"), { explode: false, orbit: false, reset: false, renderer: "2d" });
  assert.deepEqual(M.viewControls("3d"), { explode: true, orbit: true, reset: true, renderer: "3d" });
  assert.deepEqual(M.viewControls("none"), { explode: false, orbit: false, reset: false, renderer: "none" });
});

// P2-2: a label (class · 4-hex short id) can repeat across distinct runs. Rows and links are keyed on the full run id;
// two runs with one label are never merged, and nothing asserts that one visitor carried on across runs.
test("P2-2: two runs with the same label stay apart, keyed on their full run ids", () => {
  const A = "open-0000000a-0000000000000000000000000000000a", B = "open-0000000b-0000000000000000000000000000000b";
  const base = { cls: "unknown", short: "abcd", label: "unknown · abcd" };
  const ev = [
    { ...base, seq: 1, kind: "arrival", at: "2026-11-01T10:00:00Z" },
    { ...base, seq: 2, kind: "run", run_id: A, state: "queued", codes: [], at: "2026-11-01T10:00:05Z" },
    { ...base, seq: 3, kind: "run", run_id: B, state: "queued", codes: [], at: "2026-11-01T10:00:06Z" },
    { ...base, seq: 4, kind: "run", run_id: A, state: "reproduced", codes: [], at: "2026-11-01T10:01:00Z" },
    { ...base, seq: 5, kind: "attempt", outcome: "refused", codes: [], at: "2026-11-01T10:02:00Z" },
  ];
  const w = M.followWork(ev, []);
  assert.deepEqual(w.runs.map((r) => r.run_id).sort(), [A, B]);
  const a = w.runs.find((r) => r.run_id === A), b = w.runs.find((r) => r.run_id === B);
  assert.deepEqual([a.submitted.seq, a.task.state, a.task.seq], [2, "reproduced", 4]);
  assert.deepEqual([b.submitted.seq, b.task.state, b.task.seq], [3, "queued", 3], "B keeps its own submission and state");
  assert.equal(a.sameLabel, 1);
  assert.equal(b.sameLabel, 1);
  // Door records (arrivals, attempts) carry no run id: they are a qualified label group, never a run's location.
  assert.deepEqual(w.door.map((d) => [d.label, d.arrivals, d.attempts, d.last.seq]), [["unknown · abcd", 1, 1, 5]]);
  for (const r of w.runs) assert.equal("door" in r || "last" in r, false, "a run row holds only its own run's records");
  // Trail links join records of one full run id only: A's two records, nothing to B or to the door records.
  const links = M.traceLinks(ev);
  assert.deepEqual(links, [[2, 4]]);
});

// P2-3: an older replay cursor shows the state as of that record. The latest receipt stays separate, labelled latest.
test("P2-3: a replay cursor shows the state at that record; the latest receipt is separate", async () => {
  const feed = await liveFeed(recordedFetch());
  await feed.pollOnce();
  const L = feed.state.layouts.find((l) => l.label === "unknown · 5cb8");
  assert.equal(L.status, "reproduced");
  const at = { kind: "run", run_id: L.id, state: "evaluated", seq: 85, at: "2026-11-01T14:40:09Z" };
  const v = M.runView(L, { at });
  assert.equal(v.metric, null, "a record carries no value: none is shown as of it");
  assert.equal(v.verification, null);
  assert.equal(v.replay, null);
  assert.deepEqual(v.distinct, []);
  assert.deepEqual(v.atRecord, { state: "evaluated", seq: 85, at: "2026-11-01T14:40:09Z" });
  assert.equal(v.state, "Evaluated", "the state at the cursor, not the latest");
  assert.match(v.none, /state at this record: evaluated/);
  assert.equal(v.latest.status, "reproduced");
  assert.equal(v.latest.seq, L.seq);
  assert.equal(v.latest.metric.text, "113.23 °C");
  assert.equal(v.latest.verification.replay, "reproduced");
  // Live (no cursor): the latest is the state, and no separate latest block is needed.
  const live = M.runView(L);
  assert.equal(live.atRecord, null);
  assert.equal(live.metric.text, "113.23 °C");
});

// Copy review (aneta, staging at 16:09Z): "Run unknown · 9c59" read as if the run were unknown. A run is titled by its
// short id; the class is a separate line, "visitor type: <class>". Records read the same way.
test("copy: a run is titled by its short id, and its class is a separate visitor-type line", async () => {
  const feed = await liveFeed(recordedFetch());
  await feed.pollOnce();
  for (const L of feed.state.layouts) {
    assert.equal(M.runTitle(L), `Run ${L.short}`);
    assert.equal(M.visitorType(L.cls), `visitor type: ${L.cls}`);
    assert.equal(M.runTitle(L).includes(L.cls), false, `${M.runTitle(L)} carries no class word`);
  }
  const pts = M.traceModel(feed.state.events).points;
  const run = pts.find((p) => p.kind === "run"), anon = pts.find((p) => p.kind === "arrival" && !p.label.includes(" · "));
  assert.match(M.recordTitle(run), /^Run [0-9a-f]{4} /);
  assert.equal(M.recordTitle(anon), `${anon.label} ${anon.line}`);
  assert.equal(M.recordTitle({ kind: "arrival", label: "unknown · 7c2e", line: "arrived at the door" }), "Visitor 7c2e (visitor type: unknown) arrived at the door");
});

// Warden's P1-2(b): the page honours Retry-After on 429 and 503, backs off with jitter otherwise (no fixed 5 s
// retry), and spaces its requests so a backlog of pages never bursts. Every request goes through one gate.
test("P1-2(b): the request gate honours Retry-After, backs off with jitter and spaces requests", async () => {
  let t = 1_000_000;
  const waits = [];
  const sleep = async (ms) => { waits.push(Math.round(ms)); t += ms; };
  const answers = [];
  const fetchImpl = async () => answers.shift() ?? new Response("{}", { status: 200 });
  const make = (rand) => M.createGate({ fetchImpl, now: () => t, sleep, random: () => rand });
  // Retry-After in seconds: nothing is sent before it has passed (plus jitter), whatever the backoff would say.
  let g = make(0.5);
  answers.push(new Response("{}", { status: 503, headers: { "retry-after": "20" } }));
  await g.fetch("/api/open/v1/door/results?after=0");
  waits.length = 0;
  await g.fetch("/api/open/v1/door/results?after=0");
  assert.equal(waits.length, 1);
  assert.ok(waits[0] >= 20000, `waited ${waits[0]} ms for Retry-After: 20`);
  assert.ok(waits[0] <= 30000, "jitter stays within half the wait");
  // Retry-After as an HTTP date, on a 429.
  g = make(0);
  answers.push(new Response("{}", { status: 429, headers: { "retry-after": new Date(t + 42000).toUTCString() } }));
  await g.fetch("/a");
  waits.length = 0;
  await g.fetch("/a");
  assert.ok(waits[0] >= 41000 && waits[0] <= 43000, `HTTP-date Retry-After: ${waits[0]}`);
  // Without Retry-After: exponential backoff from 5 s, each wait jittered (two pages with different random draws
  // retry at different times), and a good answer resets it.
  const backoffs = async (rand) => {
    const gg = make(rand);
    const seen = [];
    for (let k = 0; k < 4; k += 1) {
      answers.push(new Response("{}", { status: 503 }));
      waits.length = 0;
      await gg.fetch("/b");
      seen.push(waits[0] ?? 0);
    }
    return seen;
  };
  const a = await backoffs(0.1), b = await backoffs(0.9);
  assert.deepEqual(a.slice(1).map((w) => w >= 5000), [true, true, true], `waits ${a}`);
  assert.ok(a[2] > a[1] && a[3] > a[2], `the backoff grows: ${a}`);
  assert.notDeepEqual(a.slice(1), b.slice(1), "jittered: different draws, different retry times");
  assert.ok(a.slice(1).every((w) => w !== 5000) || b.slice(1).every((w) => w !== 5000), "not a fixed 5 s retry");
  g = make(0);
  answers.push(new Response("{}", { status: 503 }));
  await g.fetch("/c");
  await g.fetch("/c");                                   // waits out the backoff, then answers 200
  waits.length = 0;
  await g.fetch("/c");
  assert.ok(waits[0] < 1000, `a good answer resets the backoff: ${waits[0]}`);
  // Spacing: back-to-back requests are at least GAP_MS apart.
  g = make(0);
  waits.length = 0;
  for (let k = 0; k < 4; k += 1) await g.fetch("/d");
  assert.ok(waits.length === 3 && waits.every((w) => w >= M.GATE.GAP_MS), `spaced: ${waits}`);
  // A stopped page (aborted signal) sends nothing.
  let sent = 0;
  const g2 = M.createGate({ fetchImpl: async () => { sent += 1; return new Response("{}", { status: 503, headers: { "retry-after": "60" } }); },
    now: () => t, random: () => 0 });
  await g2.fetch("/e");
  const ac = new AbortController();
  const pending = g2.fetch("/e", { signal: ac.signal });
  ac.abort();
  await assert.rejects(pending);
  assert.equal(sent, 1, "nothing sent after the abort");
  assert.equal(M.retryAfterMs("12", 0), 12000);
  assert.equal(M.retryAfterMs("soon", 0), null);
});

// Review item P2-1: the replay cursor is a record's seq, not a position in the newest-40 window, so a paused
// "RECORD 6 OF 40" stays on its record (seq 66) when new records arrive and the window moves.
test("P2-1: a paused replay cursor stays on its record's seq when new records arrive", () => {
  const ev = (seq) => ({ seq, kind: "arrival", cls: "automation", short: null, label: "automation", at: null });
  const win = (from) => M.traceModel(Array.from({ length: 40 }, (_, i) => ev(from + i))).points;
  const before = win(61);                                   // seq 61..100
  const seq = before[5].seq;                                // RECORD 6 OF 40
  assert.equal(seq, 66);
  const after = win(64);                                    // three new records: seq 64..103
  assert.equal(M.cursorIndex(after, seq), 2);
  assert.equal(after[M.cursorIndex(after, seq)].seq, 66, "still on seq 66, now record 3 of 40");
  const gone = win(70);                                     // seq 66 has left the window
  assert.equal(gone[M.cursorIndex(gone, seq)].seq, 70, "the nearest kept record after it");
  assert.equal(M.cursorIndex(gone, 500), 39, "past the newest: the newest");
  assert.equal(M.cursorIndex([], 66), null);
  assert.equal(M.cursorIndex(after, null), null);
});

// Root's P1 on the shared gate (17:21Z): queued callers must recheck the deadline after every sleep and reserve their
// slot before they launch, and a success that started before a 429 must never clear that 429's embargo.
test("root's P1: the gate holds a 429's Retry-After against queued and in-flight callers", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"], now: 0 });
  const flush = async () => { for (let i = 0; i < 20; i += 1) await Promise.resolve(); };
  const run = async (ms) => { for (let k = 0; k < ms / 10; k += 1) { await flush(); t.mock.timers.tick(10); } await flush(); };
  // Witness 1: results launches at 0; board and visitors queue for their 300 ms slots; results answers 429,
  // Retry-After: 60, at 100 ms. Neither queued caller may launch before 60.1 s, and they stay spaced.
  const launched = [];
  const pending = new Map();
  const fetchImpl = (url) => { launched.push({ url, at: Date.now() }); return new Promise((resolve) => pending.set(url, resolve)); };
  const g = M.createGate({ fetchImpl, random: () => 0 });
  const a = g.fetch("results"), b = g.fetch("board"), c = g.fetch("visitors");
  await run(100);
  pending.get("results")(new Response("{}", { status: 429, headers: { "retry-after": "60" } }));
  await a;
  await run(61000);
  for (const u of ["board", "visitors"]) pending.get(u)?.(new Response("{}", { status: 200 }));
  await Promise.all([b, c]);
  const at = Object.fromEntries(launched.map((l) => [l.url, l.at]));
  assert.equal(at.results, 0);
  assert.ok(at.board >= 60100, `board waited out Retry-After: launched at ${at.board}`);
  assert.ok(at.visitors >= 60100 && at.visitors - at.board >= M.GATE.GAP_MS, `visitors too, a gap after board: ${at.visitors}`);
  // Witness 2: an in-flight success that started before a 429 and finishes after it keeps the embargo.
  launched.length = 0;
  pending.clear();
  const g2 = M.createGate({ fetchImpl, random: () => 0 });
  const slow = g2.fetch("slow");                         // launches at T, answers 200 only at T+500
  await run(10);
  const quick = g2.fetch("quick");                       // launches at T+300, answers 429 (Retry-After: 60) at T+400
  await run(400);
  pending.get("quick")(new Response("{}", { status: 429, headers: { "retry-after": "60" } }));
  await quick;
  await run(100);
  pending.get("slow")(new Response("{}", { status: 200 }));
  await slow;
  const t429 = Date.now();
  const next = g2.fetch("next");
  await run(61000);
  pending.get("next")?.(new Response("{}", { status: 200 }));
  await next;
  const nextAt = launched.find((l) => l.url === "next").at;
  const quickAt = launched.find((l) => l.url === "quick").at;
  assert.ok(nextAt >= quickAt + 100 + 60000, `the 429's embargo held through the earlier success: next at ${nextAt}, 429 at ~${quickAt + 100}`);
  assert.ok(t429 > 0);
});

// Root's dispatch P2 (pr103-gate-dispatch-1733): the request must be dispatched in the same synchronous turn that
// reserves its slot. Otherwise (a) a long microtask between the reservation and the real fetch call compresses the
// spacing measured at fetch time, and (b) a 429 processed in between lets an already-reserved request cross its
// embargo. Fake time throughout: the clock moves only when the test moves it.
test("root's dispatch P2 (a): a long microtask after the reservation cannot shrink the gap between fetch calls", async () => {
  let clock = 0;
  const calls = [];
  let first = true;
  const random = () => {
    // The reservation of the first request: a long microtask queued right here runs before any later continuation.
    if (first) { first = false; queueMicrotask(() => { clock += 250; }); }
    return 0;
  };
  const sleep = async (ms) => { clock += ms; };
  const fetchImpl = async (url) => { calls.push({ url, at: clock }); return new Response("{}", { status: 200 }); };
  const g = M.createGate({ fetchImpl, now: () => clock, random, sleep });
  await Promise.all([g.fetch("one"), g.fetch("two"), g.fetch("three")]);
  const at = calls.map((c) => c.at);
  const gaps = at.slice(1).map((v, i) => v - at[i]);
  assert.deepEqual(calls.map((c) => c.url), ["one", "two", "three"]);
  assert.ok(gaps.every((d) => d >= M.GATE.GAP_MS), `gaps measured when fetch is called: ${gaps} (calls at ${at})`);
});

test("root's dispatch P2 (b): a reserved request is dispatched in its own turn; a later 429 cannot sit in between", async () => {
  let clock = 0;
  const sleeps = [];
  const sleep = (ms) => new Promise((resolve) => sleeps.push({ ms, resolve }));
  const pending = new Map();
  const seen = [];
  let g;
  const fetchImpl = (url) => {
    // What the gate holds at the moment this request is really dispatched.
    seen.push({ url, at: clock, embargoAhead: g.nextAt - clock });
    return new Promise((resolve) => pending.set(url, resolve));
  };
  g = M.createGate({ fetchImpl, now: () => clock, random: () => 0, sleep });
  const one = g.fetch("one");                          // dispatched at 0; its answer is held
  const two = g.fetch("two");                          // waits for its 300 ms slot
  const three = g.fetch("three");
  for (let i = 0; i < 20; i += 1) await Promise.resolve();
  assert.equal(sleeps.length, 1, "two is sleeping until its slot");
  // In one step: two's slot comes due, and one's 429 (Retry-After: 60) arrives right after it.
  clock = 300;
  sleeps.shift().resolve();
  pending.get("one")(new Response("{}", { status: 429, headers: { "retry-after": "60" } }));
  await one;
  for (let i = 0; i < 20; i += 1) await Promise.resolve();
  const two0 = seen.find((s) => s.url === "two");
  assert.ok(two0, "two was dispatched");
  assert.equal(two0.at, 300, "at its reserved slot");
  assert.ok(two0.embargoAhead <= M.GATE.GAP_MS + M.GATE.GAP_JITTER_MS,
    `two left in the turn that reserved it, before the 429 was taken in (the gate already held ${two0.embargoAhead} ms of embargo)`);
  // Three, still queued, honours the 429's embargo.
  while (sleeps.length) { const s = sleeps.shift(); clock += s.ms; s.resolve(); for (let i = 0; i < 20; i += 1) await Promise.resolve(); }
  const three0 = seen.find((s) => s.url === "three");
  assert.ok(three0 && three0.at >= 300 + 60000, `three waited out Retry-After: dispatched at ${three0?.at}`);
  pending.get("two")(new Response("{}", { status: 200 }));
  pending.get("three")(new Response("{}", { status: 200 }));
  await Promise.all([two, three]);
});
