// node --test scripts/deck-final.test.mjs   (CI runs it through scripts/deck-data.test.mjs)
// The three-minute deck (deck/final/) shows only what its reviewed source, docs/sentilab/deck/final-3min/FINAL.json, says:
//   - the committed deck data is a fresh build of FINAL.json under the options it records;
//   - one flag picks the slide-4 outcome, the wording for each outcome is the reviewer's, word for word, and the build
//     refuses an outcome its values contradict;
//   - the five main slides fit the speech budget at the source's words per second, in every outcome;
//   - every slide-3 line, slide-2 example and chronology row names a room record that carries its minute;
//   - every rendered word passes the public-render rules, this deck's own bans, and plain words on the main slides;
//   - the review's fixes hold: no dollar figure, PR57 merged as d298cb00, the peer model at v2 and "informed peer",
//     no "deck due", and "origin time not recorded" in place of "source unknown".
import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";
import { NOT_PUBLIC, PDF_DIR, REPO_ROOT } from "./build-deck-data.mjs";
import {
  FINAL_BANNED, FINAL_DECK_DIR, FINAL_DIR, FinalError, GATES, PLAIN_WORDS, buildFinalData, checkOutcome, countWords,
  finalPdfName, loadFinal, serialize, speech,
} from "./build-deck-final.mjs";

const require = createRequire(import.meta.url);
const Deck = require(join(FINAL_DECK_DIR, "deck.js"));
const read = (p) => readFileSync(p, "utf8");
const clone = (o) => JSON.parse(JSON.stringify(o));
const sha = (b) => createHash("sha256").update(b).digest("hex");
const loaded = loadFinal();
const committed = JSON.parse(read(join(FINAL_DECK_DIR, "deck-data.json")));
const build = (options = {}, mutate) => {
  const final = clone(loaded.final);
  mutate?.(final);
  return buildFinalData({ final, hashes: loaded.hashes }, options);
};
const MEASURED = { pass: "75.61,116.02", fail: "77.10,116.02" };
const variant = (gate) => build({ gate, measured: MEASURED[gate] ?? null });
const decode = (s) => s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, "&");
const visible = (h) => decode(h.replace(/<[^>]+>/g, " ")).replace(/\s+/g, " ").replace(/ ([.,;:!?)])/g, "$1").trim();
// What each slide shows, rendered by the page's own pure renderer.
const slidesOf = (data) => [...Deck.renderSlides(data).matchAll(/<section class="slide (main|backup)" id="s-([\w-]+)"[^>]*>([\s\S]*?)<\/section>/g)]
  .map((m) => ({ main: m[1] === "main", id: m[2], text: visible(m[3]) }));
const slideText = (data, id) => slidesOf(data).find((s) => s.id === id).text;

// The reviewer's wording for slide 4, copied from the room record (team room, message 57253, 22:21:34Z). Only the code
// marks are added around rz(n), rz(n)/2 + rz(n+1)/2 and rz.
const WORDING = {
  common: "In public source, the spreader-to-sink link is `rz(n)` in HotSpot 6.0 and `rz(n)/2 + rz(n+1)/2` in 7.0, and the sink's `rz` includes convection. Our old results used 7.0. Test fixed in advance: HotSpot 6 must land within 1 K of the published 75.48 C and 115.94 C.",
  pass: "Both landed within 1 K. That reproduces those published numbers. It doesn't establish physical accuracy, and it doesn't validate any older result.",
  fail: "It missed: [values]. Our explanation is incomplete, and the withdrawal stands.",
  "not-run": "The test hasn't run. What we have is a source reading, saved output and a simplified model: 75.34 and 115.83 C, from an agent that had read the hypothesis.",
};

// ── 1. the committed files ──────────────────────────────────────────────────────────────────────────────────────────
test("deck/final is a fresh build of FINAL.json under the options it records", () => {
  const { json, js } = serialize(buildFinalData(loaded, committed.build));
  assert.equal(read(join(FINAL_DECK_DIR, "deck-data.json")), json, "deck-data.json");
  assert.equal(read(join(FINAL_DECK_DIR, "deck-data.js")), js, "deck-data.js");
  assert.equal(committed.source.finalSha256, sha(readFileSync(join(FINAL_DIR, "FINAL.json"))));
  assert.equal(committed.build.gate, "not-run", "the committed export is NOT RUN until a reviewed gate result exists");
  assert.equal(committed.build.preview, false);
});
test("deck and source files are LF-only, with no control bytes", () => {
  const files = [
    ...["index.html", "deck.js", "deck.css", "deck-data.json", "deck-data.js"].map((f) => join(FINAL_DECK_DIR, f)),
    ...readdirSync(FINAL_DIR).filter((f) => /\.(json|md)$/.test(f)).map((f) => join(FINAL_DIR, f)),
    join(REPO_ROOT, "scripts", "build-deck-final.mjs"), join(REPO_ROOT, "scripts", "deck-final.test.mjs"),
  ];
  for (const f of files) {
    const b = readFileSync(f);
    assert.ok(!b.includes(13), `${f} has a CR byte`);
    // eslint-disable-next-line no-control-regex
    assert.doesNotMatch(b.toString("utf8"), /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/, `${f} has a control byte`);
  }
});

// ── 2. slide 4: one flag, the reviewed wording, outcomes that cannot contradict their values ─────────────────────────
test("slide 4 carries the reviewer's wording for every outcome, word for word", () => {
  assert.equal(loaded.final.gate.common, WORDING.common);
  for (const g of GATES) assert.equal(loaded.final.gate.variants[g].text, WORDING[g], g);
  for (const g of GATES) {
    const s4 = slideText(variant(g), "gate");
    assert.match(s4, /differs between versions/);
    assert.doesNotMatch(s4, /\bbugs?\b/i);
    assert.ok(s4.includes(WORDING.common.replace(/`/g, "")), `${g}: the common wording`);
  }
});
test("the --gate flag selects exactly one outcome on slide 4, and the backup lists all three", () => {
  for (const g of GATES) {
    const d = variant(g);
    const s4 = slideText(d, "gate");
    assert.equal(d.deck.variant, g);
    for (const other of GATES) {
      const text = WORDING[other].replace("[values]", "");
      const shown = s4.includes(text.split(":")[0]) && s4.includes(text.slice(-30));
      assert.equal(shown, other === g, `${g}: ${other} wording ${other === g ? "missing" : "leaked"} on slide 4`);
    }
    const b3 = slideText(d, "gate-detail");
    for (const other of GATES) assert.ok(b3.includes(WORDING[other].slice(0, 40)), `${g}: backup lists ${other}`);
    assert.match(b3, new RegExp(`${d.deck.variantLabel} .*this export`));
  }
  // The outcome box holds exactly the chosen wording, with the values filled in, and nothing else.
  const box = (d) => visible(/<div class="variant v-[\w-]+"><span class="pill">[^<]*<\/span><p>([\s\S]*?)<\/p><\/div>/.exec(Deck.renderSlides(d))[1]);
  assert.equal(box(variant("not-run")), WORDING["not-run"]);
  assert.equal(box(variant("pass")), WORDING.pass);
  assert.equal(box(variant("fail")), WORDING.fail.replace("[values]", "77.10 C and 116.02 C"));
  const pass = slideText(variant("pass"), "gate");
  assert.match(pass, /75\.61 C · within/);
  assert.match(pass, /116\.02 C · within/);
  const fail = slideText(variant("fail"), "gate");
  assert.match(fail, /It missed: 77\.10 C and 116\.02 C\. Our explanation is incomplete, and the withdrawal stands\./);
  assert.match(fail, /77\.10 C · outside/);
  assert.match(slideText(variant("not-run"), "gate"), /not run.*not run/);
});
test("an outcome its values contradict, or one without reviewed wording, does not build", () => {
  const refuse = (o, re) => assert.throws(() => build(o), (e) => e instanceof FinalError && re.test(e.message), JSON.stringify(o));
  refuse({ gate: "pass", measured: "76.61,116.02" }, /PASS contradicts/);
  refuse({ gate: "fail", measured: "75.61,116.02" }, /FAIL contradicts/);
  refuse({ gate: "pass" }, /needs --measured/);
  refuse({ gate: "fail" }, /needs --measured/);
  refuse({ gate: "not-run", measured: "75.61,116.02" }, /NOT RUN takes no measured values/);
  refuse({ gate: "incomplete" }, /no reviewed wording/);
  refuse({ gate: "error" }, /no reviewed wording/);
  refuse({ gate: "pass", measured: "75.6" }, /two temperatures/);
  refuse({ gate: "not-run", preview: true }, /PASS and FAIL renders only/);
  refuse({ cutoff: "2026-10-31T20:00:00Z" }, /cannot be earlier/);
});
test("the tolerance is exact: 1.000 K away passes, 1.001 K fails", () => {
  const refs = loaded.final.gate.references;
  assert.ok(checkOutcome("pass", ["76.48", "116.94"], refs, "1.0").every((r) => r.within));
  assert.throws(() => checkOutcome("pass", ["76.481", "116.94"], refs, "1.0"), /PASS contradicts/);
  assert.equal(checkOutcome("fail", ["74.479", "115.94"], refs, "1.0")[0].within, false);
});
test("a preview renders PASS or FAIL without values, is marked PREVIEW on every slide, and never names a PDF", () => {
  for (const g of ["pass", "fail"]) {
    const d = build({ gate: g, preview: true });
    for (const s of slidesOf(d)) assert.match(s.text, /PREVIEW · not a result/, `${g} ${s.id}`);
    assert.match(slideText(d, "gate"), /\[measured\]/);
    assert.throws(() => finalPdfName(d), /preview build never exports a PDF/);
  }
  assert.doesNotMatch(Deck.renderSlides(committed), /PREVIEW/);
});

// ── 3. the three-minute budget ──────────────────────────────────────────────────────────────────────────────────────
test("word count: whitespace tokens holding a letter or digit", () => {
  assert.equal(countWords("A closed-form heat test, 48 files · one command."), 8);
  assert.equal(countWords("  ·  —  "), 0);
  assert.deepEqual(speech("one two three four five six seven eight nine ten eleven", 2.2), { text: "one two three four five six seven eight nine ten eleven", words: 11, seconds: 5 });
});
test("the five main slides fit 165 s of speech at 2.2 words per second, in every outcome, with a 15 s buffer", () => {
  const t = loaded.final.talk;
  assert.deepEqual([t.wordsPerSecond, t.speechBudgetSeconds, t.bufferSeconds, t.maxSeconds], [2.2, 165, 15, 180]);
  for (const g of [...GATES, "pass-preview", "fail-preview"]) {
    const d = g.endsWith("preview") ? build({ gate: g.split("-")[0], preview: true }) : variant(g);
    const mains = d.slides.filter((s) => s.main);
    assert.deepEqual(mains.map((s) => s.id), ["problem", "how", "timeline", "gate", "reuse"]);
    for (const s of d.slides) {
      assert.equal(s.notes.words, countWords(s.notes.text), `${g} ${s.id} words`);
      assert.equal(s.notes.seconds, Math.round((s.notes.words / 2.2) * 10) / 10, `${g} ${s.id} seconds`);
    }
    const words = mains.reduce((n, s) => n + s.notes.words, 0);
    assert.equal(d.budget.mainWords, words);
    assert.ok(d.budget.mainSeconds <= 165, `${g}: ${d.budget.mainSeconds} s`);
    assert.ok(d.budget.mainSeconds + 15 <= 180);
  }
});
test("notes that run over the budget stop the build", () => {
  const long = (f) => { f.timeline.notes += " and then".repeat(10); };
  assert.throws(() => build({}, long), /over the 165 s budget/);
  assert.throws(() => build({}, (f) => { f.talk.bufferSeconds = 16; }), /exceeds the talk length/);
});

// ── 4. records behind every dated line ──────────────────────────────────────────────────────────────────────────────
test("every slide-3 line, slide-2 example and chronology row names a room record that carries its minute", () => {
  const f = loaded.final;
  const dated = [f.timeline.lede, ...f.timeline.lines, ...f.backup.chronology.rows];
  for (const item of dated) {
    assert.ok(item.records.length >= 1, item.text);
    const minutes = item.records.flatMap((r) => [r.at, r.stated].filter(Boolean)).map((t) => t.slice(0, 16));
    assert.ok(minutes.includes(item.at.slice(0, 16)), `${item.at} ${item.text}`);
    for (const r of item.records) assert.equal(r.room, "608657e4");
  }
  for (const s of f.how.steps) assert.ok(s.records.length >= 1, s.title);
  const shown = variant("not-run").slides.find((s) => s.id === "timeline").content;
  assert.deepEqual(shown.lines.map((l) => l.at), ["13:15", "13:28", "14:26", "14:42", "14:53", "15:21", "15:52", "15:57", "16:40"]);
  assert.equal(shown.lede.at, "12:43");
});
test("a line whose minute no record carries, a record after the cutoff, or a line out of order does not build", () => {
  assert.throws(() => build({}, (f) => { f.timeline.lines[0].at = "2026-10-31T13:16:00.000Z"; }), /which no record carries/);
  assert.throws(() => build({}, (f) => { f.timeline.lines[0].records = []; }), /has no room record/);
  assert.throws(() => build({}, (f) => { f.timeline.lines[8].records[0].at = "2026-11-01T00:00:00.000Z"; }), /after the cutoff/);
  assert.throws(() => build({}, (f) => { [f.timeline.lines[1], f.timeline.lines[2]] = [f.timeline.lines[2], f.timeline.lines[1]]; }), /out of time order/);
  assert.throws(() => build({}, (f) => { f.backup.prs.items[0].checkedAt = "2026-11-01T00:00:00Z"; }), /checked after the cutoff/);
});
test("the stop line says what happened, without claiming that no person asked", () => {
  const all = slidesOf(variant("not-run")).map((s) => s.text).join("\n") + variant("not-run").slides.map((s) => s.notes.text).join("\n");
  assert.doesNotMatch(all, /no (?:person|human|one) asked/i);
  assert.match(slideText(variant("not-run"), "timeline"), /An agent proposes stopping the public run\. Two others agree by 15:54\./);
});

// ── 5. public rules, this deck's bans, plain words ──────────────────────────────────────────────────────────────────
test("every rendered word passes the public-render rules and this deck's bans; main slides use plain words", () => {
  for (const g of GATES) {
    const d = variant(g);
    const notes = new Map(d.slides.map((s) => [s.id, s.notes.text]));
    for (const s of slidesOf(d)) {
      for (const text of [s.text, notes.get(s.id)]) {
        for (const re of [...NOT_PUBLIC, ...FINAL_BANNED]) assert.doesNotMatch(text, re, `${g} ${s.id}`);
        if (s.main) for (const re of PLAIN_WORDS) assert.doesNotMatch(text, re, `${g} ${s.id} (plain words)`);
      }
    }
  }
});
test("banned text in the source stops the build", () => {
  const banned = [
    [(f) => { f.backup.receipt.notYet += " Cost so far $255.79."; }, /not allowed/],
    [(f) => { f.backup.status.cards[0].text += " Deck due 2026-11-01 18:00 UTC."; }, /not allowed/],
    [(f) => { f.backup.status.cards[0].text = "source unknown"; }, /not allowed/],
    [(f) => { f.gate.bottom = "The bug stays fixed."; }, /not allowed/],
    [(f) => { f.reuse.next = "See PR 56 for the code."; }, /plain words/],
    [(f) => { f.how.footnote += " The warden reviews it."; }, /public-render rule/],
    [(f) => { f.timeline.note = "Checked by Aneta."; }, /would rewrite/],
  ];
  for (const [mutate, re] of banned) assert.throws(() => build({}, mutate), re);
});

// ── 6. the review's fixes ───────────────────────────────────────────────────────────────────────────────────────────
test("the review's fixes hold: PR states, the peer model at v2, origin times, no dollars, no deadline", () => {
  const d = variant("not-run");
  const all = slidesOf(d).map((s) => s.text).join("\n");
  const prs = slideText(d, "prs");
  assert.match(prs, /#57 Reference layouts from the paper, plus the paper's wire router merged as d298cb00 at 2026-10-31 18:04 UTC/);
  const pr56 = loaded.final.backup.prs.items.find((p) => p.number === 56);
  assert.ok(prs.includes(pr56.state === "MERGED" ? `merged as ${pr56.merge.slice(0, 8)}` : `open at head ${pr56.head.slice(0, 8)}`), "#56 shows its recorded state");
  const metrics = slideText(d, "metrics");
  assert.match(metrics, /informed peer/i);
  assert.match(metrics, /Version 2 \(14:58 UTC\) uses the simulator's 1, 2 or 4 cell centre rule and refuses to return a result that has not converged/);
  assert.doesNotMatch(all, /\bindependent model\b/i);
  assert.match(slideText(d, "status"), /origin time not recorded/);
  assert.doesNotMatch(all, /source unknown|deck due|\$|USD|dollar/i);
  assert.match(slideText(d, "status"), /0 of 8 deliverables fully accepted/);
  assert.match(slideText(d, "reuse"), /Deliverables fully accepted 0 of 8/);
  assert.match(slideText(d, "reuse"), /Scientific benefit not established/);
});
test("other teams: the receipt is FEAgent's public package; our leaderboard appears only as not-evidence", () => {
  const d = variant("not-run");
  const reuse = slideText(d, "reuse");
  assert.match(reuse, /Team FEAgent github\.com\/zucalerega\/feagent · commit 32f3ed1a/);
  assert.match(reuse, /not a test of our simulator/);
  for (const s of slidesOf(d)) {
    for (const m of s.text.matchAll(/[^.]*leaderboard[^.]*\./gi)) {
      assert.match(m[0], /not (?:used|counted) as evidence|not independent|Notice on the leaderboard/i, `${s.id}: ${m[0]}`);
    }
  }
});

// ── 7. exports ──────────────────────────────────────────────────────────────────────────────────────────────────────
test("the PDF is named from the cutoff and the outcome, sits beside its source, and has one page per slide", () => {
  const c = committed.build.cutoff;
  assert.equal(finalPdfName(committed), `final-3min/SentiLab-3min-${c.slice(0, 10)}-${c.slice(11, 13)}${c.slice(14, 16)}-not-run.pdf`);
  const pdf = join(PDF_DIR, finalPdfName(committed));
  assert.ok(existsSync(pdf), `${finalPdfName(committed)} is exported`);
  const pages = (readFileSync(pdf, "latin1").match(/\/Type\s*\/Page(?![s\w])/g) ?? []).length;
  assert.equal(pages, committed.slides.length, "one PDF page per slide");
  const pdfs = readdirSync(FINAL_DIR).filter((f) => f.endsWith(".pdf"));
  assert.deepEqual(pdfs, [finalPdfName(committed).split("/")[1]], "one PDF, one cutoff");
  const exporter = read(join(REPO_ROOT, "scripts", "export-deck-pdf.mjs"));
  assert.match(exporter, /final: \{ dir: FINAL_DECK_DIR, pdf: \(data\) => finalPdfName\(data\), mainMinFont: 28 \}/);
  assert.match(exporter, /const FROZEN = \{ \.\.\.FROZEN_V1, \.\.\.FROZEN_DAYTIME \};/);
});
test("slide 4 is rendered for all three outcomes at 1920x1080", () => {
  for (const g of GATES) {
    const png = readFileSync(join(FINAL_DIR, "variants", `slide4-${g}-1920x1080.png`));
    assert.equal(png.subarray(1, 4).toString("latin1"), "PNG");
    assert.deepEqual([png.readUInt32BE(16), png.readUInt32BE(20)], [1920, 1080], g);
  }
});
