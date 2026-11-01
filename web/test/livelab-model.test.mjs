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
  // A replay cursor at a state that is not a score shows no value for that run.
  const L = feed.state.layouts[0];
  const atQueued = M.runView(L, { at: { kind: "run", run_id: L.id, state: "queued" } });
  assert.equal(atQueued.metric, null);
  assert.match(atQueued.none, /not scored at this point in the record · queued/);
  assert.ok(M.runView(L, { at: { kind: "run", run_id: L.id, state: "reproduced" } }).metric);
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
  const runs = await M.fetchLabRuns({ fetchImpl: recordedFetch() });
  assert.deepEqual(runs, { ok: true, runs: { total: 8, byStatus: { running: 0, finished: 7, stopped: 1 }, other: 0 } });
  assert.equal((await M.fetchLabRuns({ fetchImpl: recordedFetch({ status: () => 502 }) })).ok, false);
});

test("follow the work: opaque ids and classes only; a finished run never moves its visitor", async () => {
  const feed = await liveFeed(recordedFetch());
  await feed.pollOnce();
  const { rows, anonymous } = M.followRows(feed.state.events, feed.state.layouts);
  for (const r of rows) {
    assert.match(r.label, /^[a-z_]+ · [0-9a-f]{4}$/, "a class and a 4-hex short id, never a name");
    if (r.last) assert.ok(["arrival", "attempt", "submission"].includes(r.last.kind), r.label);
  }
  for (const a of anonymous) assert.ok(a.count > 0 && !("short" in a));
  // Synthetic order check on the real shapes: arrive, submit, then the scorer's work. The location stays at the
  // submission; only the task follows the run.
  const base = { cls: "unknown", short: "abcd", label: "unknown · abcd" };
  const ev = [
    { ...base, seq: 1, kind: "arrival", at: "2026-11-01T10:00:00Z" },
    { ...base, seq: 2, kind: "run", run_id: "open-00000001-00000000000000000000000000000001", state: "queued", codes: [], at: "2026-11-01T10:00:05Z" },
    { ...base, seq: 3, kind: "run", run_id: "open-00000001-00000000000000000000000000000001", state: "evaluating", codes: [], at: "2026-11-01T10:00:09Z" },
    { ...base, seq: 4, kind: "run", run_id: "open-00000001-00000000000000000000000000000001", state: "reproduced", codes: [], at: "2026-11-01T10:01:00Z" },
  ];
  const [row] = M.followRows(ev, []).rows;
  assert.deepEqual([row.last.kind, row.last.seq, row.last.at], ["submission", 2, "2026-11-01T10:00:05Z"]);
  assert.deepEqual([row.task.state, row.task.seq], ["reproduced", 4]);
  // A stale or reordered page: the same records in any order give the same answer.
  assert.deepEqual(M.followRows([...ev].reverse(), []).rows, M.followRows(ev, []).rows);
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
