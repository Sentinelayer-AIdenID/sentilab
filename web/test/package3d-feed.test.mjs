// node --test web/test/package3d-feed.test.mjs
// The Package view against the agent door API's own contract (AGENT-DOOR Amendment 3): `sentilab-door-results/1` and
// `sentilab-door-events/1` as sentilab PR #81 serves them. The fixtures are #81's real responses, recorded from its app
// over HTTP with its own test kit (web/test/door-api-d1b09d12.json at #81's head d1b09d12; door-api-a3012546.json at
// a3012546, the build before `operator` left the open feeds). Their numbers come from #81's FakeScorer: stand-ins for
// the contract, not physics. Where a test needs a state or a value #81 never wrote, it changes one field of a recorded
// item and says so.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash, webcrypto } from "node:crypto";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import * as door from "../public/sentilab/package/source3d.mjs";
import { DIE_IDS } from "../public/sentilab/package/case-cpu-dram.mjs";
import { LABELS, labeller } from "../public/temperature-label.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const PKG = join(here, "..", "public", "sentilab", "package");
const load = (name) => JSON.parse(readFileSync(join(here, name), "utf8"));
const API = load("door-api-d1b09d12.json");
const OLD = load("door-api-a3012546.json");
const body = (name, rec = API) => structuredClone(rec.responses[name].body);
const item = (name, i = 0, rec = API) => body(name, rec).items[i];
const sha256 = (text) => createHash("sha256").update(text, "utf8").digest("hex");
const respond = (b, status = 200) => new Response(typeof b === "string" ? b : JSON.stringify(b), { status, headers: { "content-type": "application/json" } });
// A scripted fetch: answers in order, records each URL asked.
function scripted(pages) {
  const urls = [];
  return { urls, fetchImpl: async (url) => { urls.push(url); const next = pages.shift(); return typeof next === "number" ? respond("down", next) : respond(next); } };
}

test("the recordings are #81's: its commits, every response read whole with nothing refused", () => {
  assert.equal(API.recorded_from.commit, "d1b09d121c75c7a8e60238fbdd8a1553f1865a3c");
  assert.equal(OLD.recorded_from.commit, "a30125466ac4ed2a43d1d6b4ea647cdb6cd5fa98");
  for (const rec of [API, OLD]) {
    for (const [name, r] of Object.entries(rec.responses)) {
      assert.equal(r.status, 200, name);
      const page = r.body.schema === door.RESULTS_SCHEMA ? door.normalizeResults(r.body) : door.normalizeEvents(r.body);
      assert.ok(page, `${name}: a ${r.body.schema} page`);
      assert.deepEqual(page.refused, {}, name);
      assert.equal((page.layouts ?? page.events).length, r.body.schema === door.RESULTS_SCHEMA ? r.body.items.length
        : r.body.events.filter((e) => e.kind !== "scorer").length, `${name}: every record kept`);
    }
  }
  assert.equal(body("results_empty").schema, "sentilab-door-results/1");
  assert.equal(body("events_empty").schema, "sentilab-door-events/1");
});

test("empty: no items and no events, the cursor stays at 0, and live is honest about having nothing yet", async () => {
  const results = door.normalizeResults(body("results_empty")), events = door.normalizeEvents(body("events_empty"));
  assert.deepEqual([results.layouts, results.next_after, results.has_more], [[], 0, false]);
  assert.deepEqual([events.events, events.next_after, events.has_more], [[], 0, false]);
  const { urls, fetchImpl } = scripted([body("results_empty"), body("events_empty")]);
  const feed = door.createDoorFeed({ fetchImpl, now: () => 1000 });
  assert.equal(await feed.pollOnce(), door.POLL_MS);
  assert.deepEqual(urls, ["/api/open/v1/door/results?after=0", "/api/open/v1/door/events?after=0"]);
  assert.deepEqual([feed.state.connected, feed.state.layouts, feed.state.cursor, feed.state.events, feed.state.eventsCursor], [true, [], 0, [], 0]);
  assert.equal(door.statusLine({ source: "api", feed: feed.state, hostname: "sentilab.aidenid.com", nowMs: 1000 }), "live", "connected, nothing yet: live, not replay");
  assert.equal(door.statusLine({ source: "api", feed: feed.state, hostname: "127.0.0.1", nowMs: 1000 }), "staging");
  // Nothing changed since the cursor: an empty page with the same cursor (results_unchanged) moves nothing.
  const same = door.normalizeResults(body("results_unchanged"));
  assert.deepEqual([same.layouts.length, same.next_after, same.has_more], [0, 41, false]);
});

test("paging: next_after and has_more, page by page; the cursor moves only on a good page and never backwards", async () => {
  const p1 = body("results_queued_page1"), p2 = body("results_queued_page2");
  assert.deepEqual([p1.items.length, p1.next_after, p1.has_more, p2.items.length, p2.next_after, p2.has_more], [2, 4, true, 1, 5, false]);
  const { urls, fetchImpl } = scripted([p1, p2, body("events_page"), { ...body("events_page"), events: [], has_more: false }]);
  const feed = door.createDoorFeed({ fetchImpl, now: () => 1000 });
  await feed.pollOnce();
  assert.deepEqual(urls, ["/api/open/v1/door/results?after=0", "/api/open/v1/door/results?after=4",
    "/api/open/v1/door/events?after=0", "/api/open/v1/door/events?after=3"], "the next page from next_after, at once, while has_more");
  assert.deepEqual([feed.state.cursor, feed.state.eventsCursor, feed.state.layouts.length], [5, 3, 3]);
  assert.deepEqual(feed.state.layouts.map((l) => [l.status, l.arrival]), [["queued", 3], ["queued", 4], ["queued", 5]]);
  // A failed page keeps both cursors and the layouts; the next poll resumes from them.
  const again = scripted([503]);
  const f2 = door.createDoorFeed({ fetchImpl: again.fetchImpl, now: () => 2000 });
  Object.assign(f2.state, { cursor: 5, eventsCursor: 3 });
  assert.equal(await f2.pollOnce(), door.BACKOFF_MS);
  assert.deepEqual([f2.state.connected, f2.state.cursor, f2.state.eventsCursor, f2.state.error], [false, 5, 3, "answered 503"]);
  // A poll is good only when both feeds answer: results without events is not live.
  const half = scripted([body("results_empty"), 503]);
  const f3 = door.createDoorFeed({ fetchImpl: half.fetchImpl, now: () => 3000 });
  assert.equal(await f3.pollOnce(), door.BACKOFF_MS);
  assert.deepEqual([f3.state.connected, f3.state.error, f3.state.lastOkAt], [false, "answered 503", null]);
  // A page whose cursor goes backwards is not taken.
  const back = await door.fetchDoorResults(5, { fetchImpl: async () => respond(body("results_queued_page1")) });
  assert.deepEqual(back, { ok: false, error: "the cursor went backwards" });
  // has_more with no progress stops instead of looping.
  const stuck = scripted([{ ...p1, next_after: 0, has_more: true }, body("events_empty")]);
  await door.createDoorFeed({ fetchImpl: stuck.fetchImpl }).pollOnce();
  assert.equal(stuck.urls.length, 2);
});

test("every status #81 writes, from its own pages; a result only with a score that stands", () => {
  const pages = { queued: "results_queued_page2", evaluating: "results_evaluating", failed: "results_failed", reproduced: "results_reproduced",
    not_reproduced: "results_not_reproduced", cancelled: "results_cancelled", expired: "results_expired" };
  for (const [status, page] of Object.entries(pages)) {
    const layouts = door.normalizeResults(body(page)).layouts;
    const L = layouts.find((x) => x.status === status);
    assert.ok(L, `${status} is on ${page}`);
    assert.equal(Boolean(L.result), status === "reproduced" || status === "not_reproduced", `${status}: a result only after a score`);
    assert.equal(L.result_refused, null, status);
  }
  const all = door.normalizeResults(body("results_all")).layouts;
  assert.deepEqual([...new Set(all.map((l) => l.status))].sort(), ["cancelled", "expired", "failed", "not_reproduced", "reproduced"]);
  // The contract's other states (#81's door never writes them: held is operator-only; evaluated and replaying pass
  // inside one transaction; cross_checked and rejected are not runs): one field of a recorded item changed.
  for (const status of door.STATUSES) assert.equal(door.normalizeItem({ ...item("results_queued_page2"), status }).layout.status, status);
  for (const status of ["reference", "example", "won", "scored", ""]) assert.equal(door.normalizeItem({ ...item("results_queued_page2"), status }).refused, "status_unknown", status);
  const scored = item("results_reproduced");
  for (const status of ["queued", "evaluating", "failed", "cancelled", "expired", "rejected", "held"]) {
    assert.equal(door.normalizeItem({ ...scored, status }).layout.result_refused, "result_not_scored_state", status);
  }
  // The door labels every state it can show (door.mjs STATUS_CHIP).
  const d = readFileSync(join(PKG, "door.mjs"), "utf8");
  const chips = d.slice(d.indexOf("const STATUS_CHIP"), d.indexOf("});", d.indexOf("const STATUS_CHIP")));
  for (const status of door.STATUSES) assert.match(chips, new RegExp(`\\b${status}: \\[`), status);
});

test("an item maps to the layout model: id, the rebuilt label, the status, the dies by TAP index, nothing else", () => {
  const raw = item("results_reproduced");
  const { layout } = door.normalizeItem(raw);
  assert.deepEqual(Object.keys(layout).sort(), ["arrival", "cls", "dies", "id", "label", "result", "result_refused", "seq", "short", "status"]);
  assert.deepEqual([layout.id, layout.cls, layout.short, layout.label, layout.status, layout.seq, layout.arrival],
    [raw.id, "declared_agent", raw.short_id, `declared_agent · ${raw.short_id}`, "reproduced", raw.seq, raw.arrival]);
  assert.deepEqual(layout.dies, raw.dies.map((d) => ({ die: DIE_IDS[d.die], x_um: d.x_um, y_um: d.y_um, rot_deg: d.rot_deg })), "die i is TAP die i: C0..C3, D0..D3");
  assert.deepEqual(layout.dies.map((d) => d.die), DIE_IDS);
  const shuffled = structuredClone(raw);
  shuffled.dies.reverse();
  assert.deepEqual(door.normalizeItem(shuffled).layout.dies, layout.dies, "kept in the fixed order whatever the item's order");
  // The label is rebuilt from class and short id, and must agree with the item's own.
  for (const [edit, why] of [[{ label: "declared_agent · ffff" }, "a label that disagrees"], [{ class: "reference" }, "a replay-only class"],
    [{ class: "root" }, "an unknown class"], [{ short_id: "E958" }, "upper case"], [{ short_id: "e95" }, "three hex"], [{ label: "Visit evil.example" }, "free text"]]) {
    assert.equal(door.normalizeItem({ ...raw, ...edit }).refused, "label_invalid", why);
  }
  for (const id of ["ref-raw", "open-8f581de2-XYZ", "", 7]) assert.equal(door.normalizeItem({ ...raw, id }).refused, "id_invalid", String(id));
  // Dies: 0..7 each once, numbers in range, catalogue rotations only.
  const dies = (f) => { const r = structuredClone(raw); f(r.dies); return door.normalizeItem(r).refused; };
  assert.equal(dies((d) => d.pop()), "dies_count");
  assert.equal(dies((d) => { d[0].die = 8; }), "die_unknown");
  assert.equal(dies((d) => { d[0].die = "C0"; }), "die_unknown", "the API numbers its dies");
  assert.equal(dies((d) => { d[7].die = 0; }), "die_duplicate");
  assert.equal(dies((d) => { d[0].x_um = "17500"; }), "coord_not_number");
  assert.equal(dies((d) => { d[0].y_um = 1e9; }), "coord_out_of_range");
  assert.equal(dies((d) => { d[4].rot_deg = 90; }), "rotation_not_allowed", "a DRAM never turns");
  assert.equal(dies((d) => { d[0].rot_deg = 90; }), undefined, "a CPU may");
  // Whatever else an item carries is dropped unread.
  const text = JSON.stringify(layout);
  for (const unread of [raw.geometry_sha256, "wire_proxy_mm", "summary", "independently verified", "per_die_C", "GRID_CENTER", "position", "verdict"]) {
    assert.ok(!text.includes(String(unread)), String(unread));
  }
});

test("a result maps to the value under metric_id, its statistics, guard, evaluator, label, verification and replay", () => {
  const raw = item("results_reproduced");
  const r = door.normalizeItem(raw).layout.result;
  assert.deepEqual(Object.keys(r).sort(), ["claim", "diagnostic", "distinct", "evaluator", "field_key", "field_state", "grid", "grid_text", "guard",
    "label", "metric", "replay", "result_text", "verification"]);
  assert.deepEqual(r.metric, { id: "max_chiplet_centre_cell_mean_C", value: raw.result.max_chiplet_centre_cell_mean_C, precision_K: 0.01 });
  assert.deepEqual(r.distinct.map((d) => [d.key, d.value]), [["native_all_block_max_C", raw.result.native_all_block_max_C], ["active_layer_peak_C", raw.result.active_layer_peak_C]]);
  assert.deepEqual(r.guard, { limit_C: 119.07, ok: true });
  assert.equal(r.evaluator, "hotspot6:751b357f6b5af395a4447d6e3bfeef3a75eb447091798365a3db4f0e00618cc6:grid:64x64", "the identity the feed names, spelled as #81's");
  assert.equal(r.label, LABELS.unvalidated);
  assert.equal(raw.result.temperature_label, "unvalidated", "the API agrees");
  assert.deepEqual(r.verification, { replay: "reproduced", replay_code: null, cpu: "measured", distinct_execution: true, receipts_bound: true, binding_ok: true,
    active_guard_ok: true, candidate: false, not_claimed: ["beat", "margin", "routed wire", "source acceptance"] });
  assert.deepEqual(r.replay, { fresh_process: true, match: true, receipts_bound: true, code: null });
  assert.deepEqual([r.claim, r.field_state, r.diagnostic], ["simulated, not silicon", "unassociated", true]);
  const nr = door.normalizeItem(item("results_not_reproduced")).layout.result;
  assert.deepEqual([nr.verification.replay, nr.verification.replay_code, nr.replay.code], ["not_reproduced", "reproduction_failed", "reproduction_failed"]);
  // Refusals, each one field of a recorded result changed: the layout still draws, without the value.
  const refusal = (edit) => { const x = structuredClone(raw); edit(x.result); return door.normalizeItem(x).layout.result_refused; };
  assert.equal(refusal((x) => { x.label = "preview, not the scorer"; }), "result_label_unknown");
  assert.equal(refusal((x) => { x.metric_id = "active_layer_peak_C"; }), "metric_unknown", "never another statistic as the board metric");
  assert.equal(refusal((x) => { x.metric.metric_id = "peak_c"; }), "metric_unknown");
  assert.equal(refusal((x) => { x.max_chiplet_centre_cell_mean_C = "101"; }), "metric_value");
  assert.equal(refusal((x) => { delete x.metric.precision_K; }), "precision_missing");
  assert.equal(refusal((x) => { x.active_layer_peak_C = 1e9; }), "distinct_value");
  assert.equal(refusal((x) => { delete x.native_all_block_max_C; }), "distinct_value");
  assert.equal(refusal((x) => { x.active_guard.limit_C = 125; }), "guard_unknown");
  assert.equal(refusal((x) => { x.active_guard.ok = false; }), "guard_inconsistent", "the guard must agree with its own peak");
  assert.equal(refusal((x) => { x.verification.replay = "trust me"; }), "verification_malformed");
  assert.equal(refusal((x) => { x.verification.not_claimed = ["Visit evil.example"]; }), "verification_malformed");
  assert.equal(refusal((x) => { x.replay.code = "<b>x</b>"; }), "replay_malformed");
  const noEvaluator = structuredClone(raw);
  noEvaluator.result.evaluator = { binary_sha256: "nope", grid: 64 };
  assert.deepEqual([door.normalizeItem(noEvaluator).layout.result.evaluator, door.normalizeItem(noEvaluator).layout.result.label], [null, LABELS.unvalidated]);
});

test("labels: a feed result is never more than unvalidated; a withdrawn API label stays withdrawn (PL-2, PL-6)", () => {
  const raw = item("results_reproduced");
  const id = door.normalizeItem(raw).layout.result.evaluator;
  const withLabel = (temperature_label) => { const x = structuredClone(raw); x.result.temperature_label = temperature_label; return door.normalizeItem(x).layout.result.label; };
  assert.equal(withLabel("unvalidated"), LABELS.unvalidated);
  assert.equal(withLabel("accepted"), LABELS.unvalidated, "the API's label never upgrades it");
  assert.equal(withLabel("illustrative"), LABELS.unvalidated);
  assert.equal(withLabel("withdrawn"), LABELS.withdrawn, "but may make it more cautious");
  assert.equal(withLabel(undefined), LABELS.unvalidated);
  // Even an identity on the accepted list stays unvalidated while it is unverified: the composition always counts an
  // unverified input. And a withdrawn engine is withdrawn whatever the API says.
  assert.equal(door.feedLabel(id, "accepted", labeller({ accepted: [id] })), LABELS.unvalidated);
  assert.equal(door.feedLabel(id, "unvalidated", labeller({ withdrawn: ["hotspot6:751b357f6b5af395a4447d6e3bfeef3a75eb447091798365a3db4f0e00618cc6"] })), LABELS.withdrawn);
});

test("a grid64 in the feed never draws a map: it is never read, never kept and never reaches a pin", async () => {
  const raw = item("results_reproduced_with_grid64");
  assert.deepEqual([raw.result.grid64.length, new Set(raw.result.grid64.map((row) => row.length)).size, raw.result.grid64[0].length], [64, 1, 64], "#81 sent a 64 x 64 grid");
  assert.match(raw.result.grid.orientation, /^row 0 is the frame's top edge/);
  const { layout } = door.normalizeItem(raw);
  const r = layout.result;
  assert.deepEqual([r.field_state, r.grid, r.grid_text, r.result_text, r.field_key, r.diagnostic], ["unassociated", null, null, null, null, true]);
  assert.ok(!JSON.stringify(layout).includes(JSON.stringify(raw.result.grid64[0].slice(0, 4)).slice(1, -1)), "no grid row survives");
  // Not even a pin for this exact run, grid and record admits it: a feed result is never pending, so no digest is taken.
  const pins = [{ layout_id: raw.id, geometry_sha256: sha256(door.geometryText(layout)), field_sha256: sha256(JSON.stringify(raw.result.grid64)),
    result_sha256: sha256(door.resultText(raw.result)), evaluator_identity: r.evaluator }];
  let digests = 0;
  const subtle = { digest: (alg, bytes) => { digests += 1; return webcrypto.subtle.digest(alg, bytes); } };
  const [checked] = await door.verifyPinnedFields([layout], { subtle, pins });
  assert.deepEqual([checked.result.field_state, checked.result.grid, checked.result.field_key, digests], ["unassociated", null, null, 0]);
  // Through the poller too: the state holds no grid.
  const { fetchImpl } = scripted([body("results_reproduced_with_grid64"), body("events_empty")]);
  const feed = door.createDoorFeed({ fetchImpl });
  await feed.pollOnce();
  assert.deepEqual(feed.state.layouts.map((l) => [l.result.field_state, l.result.grid]), [["unassociated", null]]);
  // And the door draws only a verified field (the pinned bundled reference), never one by payload shape.
  const d = readFileSync(join(PKG, "door.mjs"), "utf8");
  assert.match(d, /r\.field_state === "verified" && r\.grid && r\.field_key && !D\.noCrypto \? fieldTexels\(r\.grid, r\.field_key\) : null/);
});

test("operator never arrives in the model: #81's older build sends it on items and events; the page drops it unread", async () => {
  const items = body("results_reproduced", OLD).items;
  const events = body("events_all", OLD).events;
  assert.ok(items.every((x) => x.operator === "openai") && events.some((e) => e.operator === "anthropic"), "the recording carries operators");
  const { urls, fetchImpl } = scripted([body("results_reproduced", OLD), body("events_all", OLD)]);
  const feed = door.createDoorFeed({ fetchImpl });
  await feed.pollOnce();
  assert.equal(urls.length, 2);
  assert.deepEqual([feed.state.layouts.length, feed.state.events.length], [3, events.filter((e) => e.kind !== "scorer").length]);
  const text = JSON.stringify(feed.state);
  for (const word of ["operator", "openai", "anthropic"]) assert.ok(!text.includes(word), word);
  for (const L of feed.state.layouts) assert.ok(!("operator" in L));
  for (const e of feed.state.events) assert.ok(!("operator" in e));
  // At #81's current head the field is gone from every open feed.
  for (const [name, r] of Object.entries(API.responses)) assert.ok(!JSON.stringify(r.body).includes("\"operator\""), name);
  // The page's code never reads it.
  for (const f of ["door.mjs", "render3d.mjs", "model.mjs", "temps.mjs", "case-cpu-dram.mjs"]) {
    assert.doesNotMatch(readFileSync(join(PKG, f), "utf8"), /operator/, f);
  }
  assert.doesNotMatch(readFileSync(join(PKG, "source3d.mjs"), "utf8").replace(/^\/\/.*$/gm, ""), /operator/, "source3d.mjs: only its comment names it");
});

test("events: the arrivals, by class and short id, with outcomes, states and codes; scorer events move the cursor only", async () => {
  const doc = body("events_all");
  const page = door.normalizeEvents(doc);
  assert.deepEqual(page.events.slice(0, 3).map((e) => [e.kind, e.label, e.outcome ?? e.state]),
    [["arrival", `declared_agent · ${doc.events[0].short_id}`, undefined], ["attempt", `declared_agent · ${doc.events[1].short_id}`, "rejected"],
      ["run", `declared_agent · ${doc.events[2].short_id}`, "queued"]]);
  assert.deepEqual(page.events[1].codes, ["rotation_not_allowed"]);
  assert.ok(!page.events.some((e) => e.kind === "scorer"));
  assert.deepEqual(Object.keys(page.events[0]).sort(), ["cls", "kind", "label", "seq", "short"]);
  assert.deepEqual(Object.keys(page.events[2]).sort(), ["cls", "codes", "kind", "label", "run_id", "seq", "short", "state"]);
  const states = new Set(page.events.filter((e) => e.kind === "run").map((e) => e.state));
  for (const s of ["queued", "evaluating", "evaluated", "replaying", "reproduced", "not_reproduced", "failed", "cancelled", "expired"]) assert.ok(states.has(s), s);
  // Paged: events_page asked after the first event, two per page.
  const p = door.normalizeEvents(body("events_page"));
  assert.deepEqual([p.events.map((e) => e.seq), p.next_after, p.has_more], [[2, 3], 3, true]);
  // An arrival without a token has no short id: its label is its class alone (#81 service.arrival).
  const bare = { ...doc.events[0], short_id: null, label: "declared_agent" };
  assert.deepEqual(door.normalizeEvent(bare).event, { seq: 1, kind: "arrival", cls: "declared_agent", short: null, label: "declared_agent" });
  // Refusals: a label that disagrees, free text, an unknown kind.
  assert.equal(door.normalizeEvent({ ...doc.events[2], label: "Claude says hi" }).refused, "label_invalid");
  assert.equal(door.normalizeEvent({ ...doc.events[2], short_id: null, label: "declared_agent" }).refused, "label_invalid", "only an arrival may have no short id");
  assert.equal(door.normalizeEvent({ ...doc.events[2], kind: "chat" }).refused, "event_kind_unknown");
  assert.equal(door.normalizeEvent({ ...doc.events[2], state: "won" }).refused, "event_malformed");
  assert.deepEqual(door.normalizeEvent({ ...doc.events[1], codes: ["rotation_not_allowed", "<script>", "Visit evil.example"] }).event.codes, ["rotation_not_allowed"]);
  // The poller keeps each event once, the newest BOUNDS.events.
  const merged = door.mergeEvents(door.mergeEvents([], page.events), page.events);
  assert.equal(merged.length, Math.min(door.BOUNDS.events, page.events.length));
  assert.deepEqual(merged.map((e) => e.seq), [...merged.map((e) => e.seq)].sort((a, b) => a - b));
});

test("arrival order: the door's admission order, whatever order the versions come in", () => {
  const all = door.normalizeResults(body("results_all")).layouts;
  const raw = body("results_all").items;
  assert.notDeepEqual(raw.map((x) => x.arrival), [...raw.map((x) => x.arrival)].sort((a, b) => a - b), "#81 pages by version, not arrival");
  const merged = door.mergeArrivals([], all);
  assert.deepEqual(merged.map((l) => l.arrival), [...raw.map((x) => x.arrival)].sort((a, b) => a - b));
  // A later version of a run replaces the held one in place; an older one never does (#81's own pages: queued, then reproduced).
  const queued = door.normalizeResults(body("results_queued_page1")).layouts;
  const scored = door.normalizeResults(body("results_reproduced")).layouts;
  const step = door.mergeArrivals(queued, scored);
  assert.deepEqual(step.map((l) => [l.id, l.status]), scored.map((l) => [l.id, "reproduced"]));
  assert.deepEqual(door.mergeArrivals(step, queued).map((l) => l.status), ["reproduced", "reproduced", "reproduced"], "an older version is dropped");
});

test("the seam: two read-only GETs with the integer cursor and nothing else", async () => {
  const calls = [];
  const fetchImpl = async (url, init) => { calls.push({ url, init }); return respond(url.includes("events") ? body("events_empty") : body("results_empty")); };
  assert.equal((await door.fetchDoorResults(0, { fetchImpl })).ok, true);
  assert.equal((await door.fetchDoorEvents(0, { fetchImpl })).ok, true);
  await door.fetchDoorResults("7&limit=20", { fetchImpl });
  assert.deepEqual(calls.map((c) => c.url), ["/api/open/v1/door/results?after=0", "/api/open/v1/door/events?after=0", "/api/open/v1/door/results?after=0"],
    "a cursor that is not a whole number is never sent");
  for (const { init } of calls) assert.deepEqual([init.method, init.body, init.redirect, init.cache], ["GET", undefined, "error", "no-store"]);
  const fail = (b, status) => door.fetchDoorResults(0, { fetchImpl: async () => respond(b, status) });
  assert.deepEqual(await fail("nope", 503), { ok: false, error: "answered 503" });
  assert.deepEqual(await fail("{not json"), { ok: false, error: "answer is not JSON" });
  assert.deepEqual(await fail({ layouts: [], schema: "sentilab-door-layouts/1" }), { ok: false, error: "answer is not a door results page" }, "the retired shape is not read");
  assert.deepEqual(await fail(body("events_empty")), { ok: false, error: "answer is not a door results page" });
  assert.deepEqual(await fail({ ...body("results_empty"), metric: { metric_id: "peak_c" } }), { ok: false, error: "answer is not a door results page" }, "another board's metric");
  assert.deepEqual(await door.fetchDoorEvents(0, { fetchImpl: async () => respond(body("results_empty")) }), { ok: false, error: "answer is not a door events page" });
  assert.deepEqual(await door.fetchDoorResults(0, { fetchImpl: async () => { throw new TypeError("network"); } }), { ok: false, error: "unreachable" });
});
