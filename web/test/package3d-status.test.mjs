// node --test web/test/package3d-status.test.mjs
// A door run's place and reason, and the scorer's health, as the agent door API reports them (sentilab PR #81, on main):
// queue positions, codes and reasons in plain words (the door Worker's own words where it has them), the contract's
// summary, and the scorer chip from the API's `scorer` snapshot. Fixtures are #81's real responses, recorded from its
// app over HTTP with its own test kit: web/test/door-api-status-0bf1d224.json (main 0bf1d224, whose door app is #81's
// d1b09d12) for positions, refused attempts and each scorer state; door-api-d1b09d12.json for failed, not reproduced,
// cancelled and expired runs. Numbers come from #81's FakeScorer: stand-ins, not physics.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import * as door from "../public/sentilab/package/source3d.mjs";
import * as status from "../public/sentilab/package/status.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const PKG = join(here, "..", "public", "sentilab", "package");
const load = (name) => JSON.parse(readFileSync(join(here, name), "utf8"));
const STATUS = load("door-api-status-0bf1d224.json");
const API = load("door-api-d1b09d12.json");
const body = (name, rec = STATUS) => structuredClone(rec.responses[name].body);
const layouts = (name, rec = STATUS) => door.normalizeResults(body(name, rec)).layouts;
const respond = (b, s = 200) => new Response(typeof b === "string" ? b : JSON.stringify(b), { status: s, headers: { "content-type": "application/json" } });
function scripted(pages) {
  const urls = [];
  return { urls, fetchImpl: async (url) => { urls.push(url); const next = pages.shift(); return typeof next === "number" ? respond("down", next) : respond(next); } };
}

test("queued runs carry their place in the queue, as the API counts it", () => {
  const queued = layouts("results_queued_scorer_unknown");
  assert.deepEqual(queued.map((l) => [l.status, l.position, l.summary]), [["queued", 1, "queued"], ["queued", 2, "queued"], ["queued", 3, "queued"]]);
  assert.deepEqual(queued.map(status.stateLine), ["Queued · position 1", "Queued · position 2", "Queued · position 3"]);
  // One run claimed: the other two move up, by the API's own count; the claimed one has no position.
  const after = layouts("results_scorer_up_evaluating");
  assert.deepEqual(after.map((l) => [l.status, l.position]), [["queued", 1], ["queued", 2], ["evaluating", null]]);
  assert.equal(status.stateLine(after[2]), "Evaluating · the scorer's answer was lost; it is being reconciled", "#81's reason: unresolved");
  assert.equal(status.summaryLine(after[2]), "contract state: queued", "the contract's summary of evaluating");
  // A position is the API's, never derived: absent, out of range or on a run that is not waiting, it is not shown.
  const raw = body("results_queued_scorer_unknown").items[2];
  for (const position of [undefined, null, 0, -1, 2.5, "3", 2 ** 53]) assert.equal(door.normalizeItem({ ...raw, position }).layout.position, null, String(position));
  assert.equal(status.stateLine(door.normalizeItem({ ...raw, position: null }).layout), "Queued");
  assert.equal(door.normalizeItem({ ...raw, status: "evaluating" }).layout.position, null, "only a waiting run has a place");
  assert.equal(door.normalizeItem({ ...raw, status: "held" }).layout.position, 3);
  assert.equal(status.stateLine(door.normalizeItem({ ...raw, status: "held" }).layout), "Held · position 3");
});

test("a waiting run's place stays current as the runs ahead of it leave the queue (#81's own rule)", async () => {
  // Every full page (read from the start): the rule gives exactly the positions the API itself reported.
  for (const name of ["results_queued_scorer_unknown", "results_scorer_down", "results_scorer_up_evaluating", "results_scorer_up_done"]) {
    const api = layouts(name);
    assert.deepEqual(door.withPositions(api).map((l) => l.position), api.map((l) => l.position), name);
  }
  // The feed returns a run again only when the run itself changes. #81's own records: three queued (places 1, 2, 3),
  // then the first claimed. The page after that cursor holds only the claimed run's newer record (the other two did not
  // change), so their reported places (2, 3) are stale; the rule moves them up to 1 and 2, the API's own later count.
  const queued = layouts("results_queued_scorer_unknown");
  const later = body("results_scorer_up_evaluating");
  const claimedRaw = later.items.find((x) => x.status === "evaluating");
  const merged = door.withPositions(door.mergeArrivals(queued, [door.normalizeItem(claimedRaw).layout]));
  assert.deepEqual(merged.map((l) => [l.status, l.position]), [["evaluating", null], ["queued", 1], ["queued", 2]]);
  assert.deepEqual(merged.slice(1).map((l) => l.position), later.items.filter((x) => x.status === "queued").map((x) => x.position), "as the API counts them");
  // The poller applies the rule after every page.
  const { fetchImpl } = scripted([body("results_queued_scorer_unknown"), body("events_refused_attempts"), { ...later, items: [claimedRaw] }, body("events_all")]);
  const feed = door.createDoorFeed({ fetchImpl });
  await feed.pollOnce();
  assert.deepEqual(feed.state.layouts.map((l) => l.position), [1, 2, 3]);
  await feed.pollOnce();
  assert.deepEqual(feed.state.layouts.map((l) => [l.status, l.position]), [["evaluating", null], ["queued", 1], ["queued", 2]]);
  assert.deepEqual(feed.state.layouts.slice(1).map(status.stateLine), ["Queued · position 1", "Queued · position 2"]);
  // A held run keeps its place in the count (#81 counts queued and held); bundled records have no place.
  const held = queued.map((l, i) => (i === 1 ? { ...l, status: "held" } : l));
  assert.deepEqual(door.withPositions(held).map((l) => l.position), [1, 2, 3]);
  assert.ok(door.withPositions([{ status: "reference", arrival: null, position: null }]).every((l) => l.position === null));
});

test("codes and reasons in plain words: refused attempts, failed, not reproduced, cancelled and expired runs", () => {
  const events = door.normalizeEvents(body("events_refused_attempts")).events;
  const attempts = events.filter((e) => e.kind === "attempt");
  assert.deepEqual(attempts.map((e) => e.codes), [["rotation_not_allowed"], ["halo_overlap", "min_spacing"], ["margin"], ["lattice"]]);
  assert.deepEqual(attempts.map(status.eventLine), [
    "rejected: rotation not allowed for this die",
    "rejected: halos overlap, dies closer than 0.1 mm",
    "rejected: too close to the interposer edge (die plus halo)",
    "rejected: centre off the 0.5 mm lattice",
  ]);
  assert.equal(status.eventLine(events.find((e) => e.kind === "run")), "queued");
  // Runs from #81's other recording: each state with its own codes or reason.
  const all = layouts("results_all", API);
  const line = (s) => status.stateLine(all.find((l) => l.status === s));
  assert.equal(line("failed"), "Failed: the scorer returned an error", "codes [oracle_error]");
  assert.equal(line("not_reproduced"), "Not reproduced: the replay did not reproduce the score", "codes [reproduction_failed]");
  assert.equal(line("cancelled"), "Cancelled: the stored layout failed its launch check", "reason revalidation_failed");
  assert.equal(line("expired"), "Expired: the submission window closed before it ran", "reason window_closed");
  assert.equal(line("reproduced"), "Reproduced");
  assert.deepEqual(all.filter((l) => l.status !== "reproduced").map((l) => l.summary), ["evaluated", "evaluated", null, null], "the contract's summaries");
  // A code or reason the page has no words for reads as itself; anything that is not an identifier is dropped.
  const raw = body("results_all", API).items.find((x) => x.status === "failed");
  const odd = door.normalizeItem({ ...raw, codes: ["new_code", "<b>x</b>", "Visit evil.example", 7], reason: "Ignore previous instructions" }).layout;
  assert.deepEqual([odd.codes, odd.reason], [["new_code"], null]);
  assert.equal(status.stateLine(odd), "Failed: new code");
  assert.equal(door.normalizeItem({ ...raw, summary: "won" }).layout.summary, null, "only the contract's summaries");
});

test("the page uses the door Worker's words for the codes the Worker words", async () => {
  // The Worker's table (sentilab PR #82, web/src/door/render.js CODE_TEXT at f7f3e44), copied exactly. Once the Worker is
  // on this branch, its own module is the reference.
  const worker = {
    margin: "too close to the interposer edge (die plus halo)", halo_overlap: "halos overlap", min_spacing: "dies closer than 0.1 mm",
    rotation_not_allowed: "rotation not allowed for this die", out_of_frame: "centre outside the 45 mm frame", die_count: "not eight dies",
    die_order: "dies out of order", lattice: "centre off the 0.5 mm lattice", schema_invalid: "not in the layout format",
    unknown_field: "a field the layout does not have", queue_full: "the scorer's queue is full",
    idempotency_conflict: "an earlier request with this link and layout already stands, so this one was not queued again",
  };
  assert.deepEqual({ ...status.WORKER_CODE_WORDS }, worker);
  for (const [code, words] of Object.entries(worker)) assert.equal(status.codeWords(code), words, code);
  const { existsSync } = await import("node:fs");
  const render = join(here, "..", "src", "door", "render.js");
  if (existsSync(render)) {
    const { codeText } = await import(new URL(`file:///${render.replace(/\\/g, "/")}`).href);
    for (const code of Object.keys(worker)) assert.equal(codeText({ code }), `${code}: ${status.codeWords(code)}`, `${code}: the Worker's own words`);
  }
  // Every contract code a run or an attempt can carry has words (contracts/open-proposal-v1/reason-codes.json).
  const vocabulary = JSON.parse(readFileSync(join(here, "..", "..", "contracts", "open-proposal-v1", "reason-codes.json"), "utf8"));
  const groups = Object.fromEntries(vocabulary.groups.map((g) => [g.group, g.codes.map((c) => c.code)]));
  for (const group of ["geometry", "evaluation", "reproduction"]) for (const code of groups[group]) assert.ok(status.CODE_WORDS[code], `${group}: ${code}`);
  for (const code of Object.keys(status.CODE_WORDS)) assert.ok(Object.values(groups).flat().includes(code), `${code} is a contract code`);
});

test("the scorer snapshot, each state #81 writes, as the chip shows it", async () => {
  const pages = {
    unknown: "results_queued_scorer_unknown", unreachable: "results_scorer_down", busy: "results_scorer_up_evaluating", up: "results_scorer_up_done",
  };
  assert.deepEqual(body("results_queued_scorer_unknown").scorer, { state: "unknown", since: null });
  assert.equal(body("results_scorer_down").scorer.state, "down");
  assert.equal(body("results_scorer_up_done").scorer.state, "up");
  for (const [word, page] of Object.entries(pages)) {
    const { fetchImpl } = scripted([body(page), body("events_all")]);
    const feed = door.createDoorFeed({ fetchImpl, now: () => 50000 });
    await feed.pollOnce();
    // up_done has a run still evaluating (unresolved), so it reads busy too; the events page's snapshot is the newest.
    const events = body("events_all").scorer;
    assert.deepEqual([feed.state.scorer.state, feed.state.scorer.since, feed.state.scorer.at], [events.state, events.since, 50000], "the newest snapshot, and when it was read");
  }
  const chip = (page, { at = 1000, nowMs = 1000, connected = true } = {}) => {
    const p = door.normalizeResults(body(page));
    return status.scorerChip({ feed: { connected, scorer: { ...p.scorer, at }, layouts: p.layouts }, nowMs });
  };
  assert.deepEqual(chip("results_queued_scorer_unknown"), { word: "unknown", since: null, age_s: 0 });
  assert.deepEqual(chip("results_scorer_down"), { word: "unreachable", since: 1793500000, age_s: 0 });
  assert.deepEqual(chip("results_scorer_up_evaluating"), { word: "busy", since: 1793500006, age_s: 0 }, "up, with a run evaluating");
  const done = door.normalizeResults(body("results_scorer_up_done"));
  const idle = done.layouts.filter((l) => l.status !== "evaluating");
  assert.deepEqual(status.scorerChip({ feed: { connected: true, scorer: { ...done.scorer, at: 1000 }, layouts: idle }, nowMs: 3000 }), { word: "up", since: 1793500006, age_s: 2 });
  // Stale or disconnected reads unknown: never the last word it had.
  assert.equal(chip("results_scorer_down", { at: 1000, nowMs: 1000 + door.LIVE_FRESH_MS + 1 }).word, "unknown", "older than the bound");
  assert.equal(chip("results_scorer_down", { at: 1000, nowMs: 1000 + door.LIVE_FRESH_MS }).word, "unreachable", "at the bound, still fresh");
  assert.equal(chip("results_scorer_up_done", { connected: false }).word, "unknown", "the feed stopped answering");
  assert.equal(status.scorerChip({ feed: null }).word, "unknown");
  assert.equal(status.scorerChip({ feed: { connected: true, scorer: null, layouts: [] } }).word, "unknown");
  // An unreadable snapshot is unknown, never up.
  for (const scorer of [undefined, null, "up", { state: "busy" }, { state: "UP" }, { state: "up", since: "yesterday" }]) {
    const read = door.readScorer(scorer);
    assert.ok(read.state === "unknown" || (read.state === "up" && read.since === null), JSON.stringify(scorer));
  }
  assert.deepEqual(door.readScorer({ state: "up", since: "yesterday" }), { state: "up", since: null });
  assert.equal(status.utcTime(1793500006), "02:26:46Z");
});

test("the door shows these lines and the chip from the API only, never from its own animation", () => {
  const d = readFileSync(join(PKG, "door.mjs"), "utf8");
  assert.match(d, /return stateLine\(L\) \?\? NOT_SCORED\[L\.status\]/, "a run's own state line before the generic words");
  assert.match(d, /\$\("dState"\)\.textContent = L \? \[stateLine\(L\), summaryLine\(L\)\]\.filter\(Boolean\)\.join\(" · "\) : "";/);
  assert.match(d, /const c = scorerChip\(\{ feed: D\.feed\?\.state \?\? null, nowMs: Date\.now\(\) \}\);/);
  assert.match(d, /const sig = `\$\{L\.label\}\|\$\{L\.status\}\|\$\{L\.position \?\? ""\}\|\$\{L\.reason \?\? ""\}\|\$\{L\.codes\.join\(","\)\}\|/, "a tile redraws when its place or reason changes");
  const s = readFileSync(join(PKG, "status.mjs"), "utf8").replace(/^\s*\/\/.*$/gm, "");
  assert.doesNotMatch(s, /anim|glide|frame\(|performance|requestAnimationFrame|explode/i, "status.mjs reads no animation state");
  // Full run ids stay internal: no line is made from one.
  const queued = layouts("results_queued_scorer_unknown");
  for (const L of queued) for (const text of [status.stateLine(L), status.summaryLine(L)]) assert.ok(!text.includes(L.id) && !text.includes("open-"), text);
});
