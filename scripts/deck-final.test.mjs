// node --test scripts/deck-final.test.mjs   (CI runs it through scripts/deck-data.test.mjs)
// The five-minute talk deck (deck/final-5min/) shows only what its reviewed source, docs/sentilab/deck/final-5min/FINAL.json,
// says, and the three-minute deck it replaced (deck/final/ and final-3min/) stays exactly as exported at 00:12 UTC:
//   - the committed deck data and figures are a fresh build of FINAL.json under the options it records, and every
//     preserved three-minute file still has its pinned sha256;
//   - the figures are the contributed SVGs byte for byte, inert, with only the declared text edits, and their text is
//     held to the same public rules as the slides;
//   - outside teams are named only where their consent is on record; otherwise "an outside team", in slides, notes,
//     figures and the generated data alike;
//   - one flag picks the slide-4 outcome, the wording for each outcome is the reviewer's, word for word, and the build
//     refuses an outcome its values contradict; the recorded PASS keeps the operator's exact scope, and --rederived
//     states the completed independent re-derivation;
//   - timing (root, team room 57481): the talk before the door at 150 words a minute plus transitions fits 180 s, the
//     door lines fit inside the 120 s demo clock, and the 300 s slot holds both;
//   - "By the numbers" shows measured values only, each the quant pack's own value and class, with no savings estimate;
//   - every dated line, figure time and tile names a room record that carries its minute;
//   - the main talk is the coordinator's plain-language script (PLAIN-SCRIPT.md, v2.5): its titles on the slides, its
//     "Say" text as the notes, one picture each, no K, formula, grid or "statistic" on a main slide; every slide of the
//     earlier five-minute deck follows as backup, unchanged. Where an older test says "slide 2" or "slide 4", it means
//     that deck's slide, now backup B2 or B4.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { inflateSync } from "node:zlib";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { createRequire } from "node:module";
import { join, relative, sep } from "node:path";
import { NOT_PUBLIC, PDF_DIR, REPO_ROOT } from "./build-deck-data.mjs";
import {
  FIGURE_OUT_DIR, FIGURE_SOURCE_DIR, FINAL3_DECK_DIR, FINAL3_DIR, FINAL_BANNED, FINAL_DECK_DIR, FINAL_DIR, FINAL_SOURCE,
  FROZEN_FINAL_3MIN, FinalError, GATES, MONEY, PLAIN_TALK_BANNED, PLAIN_WORDS, buildFigureFrom, buildFinalData, checkDuration, checkOutcome, cliOptions, countWords,
  figureDirMatches, finalPdfName, loadFinal, moneyAllowed, parseConsent, refreshPrs, serialize, speech, speakerScript, splitCommon, svgActive, svgTexts, teamResolver,
  SCRIPT_PATH,
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
const recorded = (options = {}, mutate) => build({ rederived: true, ...options }, mutate);
const MEASURED = { pass: "75.61,116.02", fail: "77.10,116.02" };
const variant = (gate) => build({ gate, measured: MEASURED[gate] ?? null });
const decode = (s) => s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, "&");
const visible = (h) => decode(h.replace(/<[^>]+>/g, " ")).replace(/\s+/g, " ").replace(/ ([.,;:!?)])/g, "$1").trim();
// What each slide shows, rendered by the page's own pure renderer, plus the text inside its figure.
const slidesOf = (data) => [...Deck.renderSlides(data).matchAll(/<section class="slide (main|backup)" id="s-([\w-]+)"[^>]*>([\s\S]*?)<\/section>/g)]
  .map((m) => ({ main: m[1] === "main", id: m[2], text: visible(m[3]) }));
const slideText = (data, id) => slidesOf(data).find((s) => s.id === id).text;
const figureText = (data, id) => (data.slides.find((s) => s.id === id).content.figure?.texts ?? []).join(" | ");
const notesOf = (data, id) => data.slides.find((s) => s.id === id).notes.text;
const everything = (data) => [...slidesOf(data).map((s) => s.text), ...data.slides.map((s) => s.notes.text),
  ...data.slides.map((s) => figureText(data, s.id))].join("\n");
const sentences = (text) => text.split(/(?<=[.!?])\s+/);
const files = (dir) => readdirSync(dir, { recursive: true }).map((f) => join(dir, f)).filter((f) => statSync(f).isFile())
  .map((f) => relative(REPO_ROOT, f).split(sep).join("/")).sort();
const TEAM_NAMES = Object.values(loaded.final.teams).map((t) => t.name);
const named = (text, name) => new RegExp(`(^|[^\\p{L}\\p{N}])${name}(?![\\p{L}\\p{N}])`, "u").test(text);
const consentLine = (seq, at = "2026-11-01T01:20:00Z") => `32a841e5 seq ${seq} at ${at}`;

// The reviewer's wording for slide 4, copied from the room record (team room, message 57253, 22:21:34Z). Only the code
// marks are added around rz(n), rz(n)/2 + rz(n+1)/2 and rz.
const WORDING = {
  common: "In public source, the spreader-to-sink link is `rz(n)` in HotSpot 6.0 and `rz(n)/2 + rz(n+1)/2` in 7.0, and the sink's `rz` includes convection. Our old results used 7.0. Test fixed in advance: HotSpot 6 must land within 1 K of the published 75.48 C and 115.94 C.",
  pass: "Both landed within 1 K. That reproduces those published numbers. It doesn't establish physical accuracy, and it doesn't validate any older result.",
  fail: "It missed: [values]. Our explanation is incomplete, and the withdrawal stands.",
  "not-run": "The test hasn't run. What we have is a source reading, saved output and a simplified model: 75.34 and 115.83 C, from an agent that had read the hypothesis.",
};
// The operator's scope for the PASS, word for word (team room, message 57377, 23:45:43Z).
const OPERATOR_SCOPE = "this binary, at grid 64, on the block-centre metric only. It doesn't cover other grids or the search objective J.";
// The review author's corrected slide line (team room, message 57392, 00:03:42Z on 1 Nov), with "approved" for "+1" as
// she asked in her review of the 02:06 PDF (message 57554): "+1" is banned on public slides (message 56383).
const REVIEW_LINE = "Across 34 code reviews, a later agent was first on record with 80 of 190 findings, 17 of them at a version another agent had already approved. The reviews weren't blind, so this is descriptive, not a controlled test.";
// The demo instruction as given for the live-demo slide.
const INSTRUCTION = "Tell your assistant: go to sentilab.aidenid.com, say you're here to place chiplets, and propose a layout.";
// The plain talk's nine main slides, then every slide of the earlier five-minute deck, in its order, as backup.
// Script v3's ten main slides; then the earlier five-minute deck, the figures the v2.5 talk carried, and the answer pages.
const MAIN = ["t-hook", "t-grader", "t-team", "t-reports", "t-stop", "t-step", "t-bar", "t-open", "t-lesson", "t-door"];
const OLD_MAIN = ["problem", "stack", "timeline", "gate", "checks", "teams", "numbers", "demo"];
const OLD_DECK = [...OLD_MAIN, "how", "chronology", "reviews", "metrics", "view3d", "profile", "layers", "gate-detail", "drill", "status", "gb10", "prs", "receipt"];
const PLAIN_BACKUP = ["b-plain1", "b-plain4", "b-plain5", "b-fig6"];
const DOOR = "t-door";

// ── 1. the committed files ──────────────────────────────────────────────────────────────────────────────────────────
test("deck/final-5min is a fresh build of FINAL.json under the options it records, figures included", () => {
  const data = buildFinalData(loaded, committed.build);
  const { json, js } = serialize(data);
  assert.equal(read(join(FINAL_DECK_DIR, "deck-data.json")), json, "deck-data.json");
  assert.equal(read(join(FINAL_DECK_DIR, "deck-data.js")), js, "deck-data.js");
  assert.match(js, /^\/\/ Generated by scripts\/build-deck-final\.mjs from docs\/sentilab\/deck\/final-5min\/FINAL\.json\./);
  assert.ok(figureDirMatches(data), "deck/final-5min/figures holds exactly the generated figures");
  assert.equal(committed.source.finalSha256, sha(readFileSync(FINAL_SOURCE)));
  // The committed export is the reviewed result recorded in FINAL.json, never a preview or a review render, with the
  // re-derivation stated (it is on record before the cutoff), the full 3+2 slot, and the door at its honest default:
  // RECORDED until the address is confirmed.
  assert.deepEqual([committed.build.gate, committed.build.measured], [loaded.final.gate.result.outcome, loaded.final.gate.result.measured]);
  assert.deepEqual([committed.build.preview, committed.deck.reviewOnly, committed.build.rederived, committed.build.demoStatus, committed.build.demoReview, committed.build.slot],
    [false, false, true, "recorded", false, "3+2"]);
  const qaIds = committed.slides.map((s) => s.id).filter((id) => /^qa(-\d+)?$/.test(id));
  const BACKUP = [...OLD_DECK, ...PLAIN_BACKUP, ...qaIds];
  assert.deepEqual(committed.slides.map((s) => s.id), [...MAIN, ...BACKUP]);
  assert.deepEqual(committed.slides.map((s) => s.main), [...MAIN.map(() => true), ...BACKUP.map(() => false)]);
});
test("the three-minute deck is preserved byte for byte, and nothing writes over it", () => {
  for (const [rel, pin] of Object.entries(FROZEN_FINAL_3MIN)) assert.equal(sha(readFileSync(join(REPO_ROOT, rel))), pin, rel);
  // Every file in its two folders is pinned: nothing was added beside them either.
  assert.deepEqual([...files(FINAL3_DIR), ...files(FINAL3_DECK_DIR)].sort(), Object.keys(FROZEN_FINAL_3MIN).sort());
  const exporter = read(join(REPO_ROOT, "scripts", "export-deck-pdf.mjs"));
  assert.match(exporter, /if \(Object\.hasOwn\(FROZEN_FINAL_3MIN, rel\)\) throw/);
  assert.match(exporter, /final3min: \{ dir: FINAL3_DECK_DIR, pdf: \(\) => \{ throw new Error\(/);
  // The exporter deletes nothing: a new export never replaces an earlier PDF.
  assert.doesNotMatch(exporter, /unlinkSync|rmSync|renameSync|\bunlink\(/);
});
test("deck, source and figure files are LF-only, with no control bytes", () => {
  const paths = [
    ...["index.html", "deck.js", "deck.css", "deck-data.json", "deck-data.js"].map((f) => join(FINAL_DECK_DIR, f)),
    ...files(FINAL_DIR).filter((f) => /\.(json|md|svg)$/.test(f)).map((f) => join(REPO_ROOT, f)),
    ...readdirSync(FIGURE_OUT_DIR).filter((f) => f.endsWith(".svg")).map((f) => join(FIGURE_OUT_DIR, f)),
    ...["build-deck-final.mjs", "deck-final.test.mjs", "export-deck-pdf.mjs"].map((f) => join(REPO_ROOT, "scripts", f)),
  ];
  const svgs = paths.filter((p) => p.endsWith(".svg")).length;
  assert.ok(paths.some((p) => p.endsWith("DECK-NUMBERS.md")) && paths.some((p) => p.endsWith("PLAIN-SCRIPT.md")), "the quant pack and the plain script are checked");
  assert.equal(svgs, 2 * Object.keys(loaded.final.figures).length, "both copies of every figure are checked");
  for (const f of paths) {
    const b = readFileSync(f);
    assert.ok(!b.includes(13), `${f} has a CR byte`);
    // eslint-disable-next-line no-control-regex
    assert.doesNotMatch(b.toString("utf8"), /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/, `${f} has a control byte`);
  }
});

// ── 2. the figures ──────────────────────────────────────────────────────────────────────────────────────────────────
test("the figures are the contributed SVGs byte for byte, inert, with only the declared edits", () => {
  const figs = loaded.final.figures;
  assert.deepEqual(Object.keys(figs), ["fig1", "fig2", "fig2b", "fig3", "fig4", "fig5", "fig6", "plain1", "plain2", "plain3", "plain4", "plain5", "plain6"]);
  // aneta's files as sent: plain1 from v1.10, plain2 from v1.11, and plain3 to plain6, fig4 and fig6 from v1.15 (team room, 1 Nov).
  assert.deepEqual(Object.fromEntries(Object.entries(figs).filter(([id]) => /^plain|^fig6$/.test(id)).map(([id, f]) => [id, f.sha256.slice(0, 16)])),
    { fig6: "e9eeadb9217c9849", plain1: "9d1e00cabb836fcb", plain2: "1b7f851e28fda639", plain3: "e4a79736d5f841eb", plain4: "036788919f1a9f8a", plain5: "c0773bfb8432beaa", plain6: "b47128e9a4c1b5d1" });
  const stills = Object.values(loaded.final.stills).map((s) => s.file);
  assert.deepEqual(readdirSync(FIGURE_SOURCE_DIR).sort(), [...Object.values(figs).map((f) => f.file), ...stills].sort());
  assert.deepEqual(readdirSync(FIGURE_OUT_DIR).sort(), [...Object.values(figs).map((f) => f.file), ...stills].sort());
  for (const st of Object.values(loaded.final.stills)) {
    const b = readFileSync(join(FIGURE_SOURCE_DIR, st.file));
    assert.equal(sha(b), st.sha256, st.file);
    assert.ok(readFileSync(join(FIGURE_OUT_DIR, st.file)).equals(b), `${st.file}: served byte for byte`);
  }
  for (const [id, f] of Object.entries(figs)) {
    const src = readFileSync(join(FIGURE_SOURCE_DIR, f.file));
    assert.equal(sha(src), f.sha256, `${id}: the source file is the one FINAL.json pins`);
    assert.deepEqual(svgActive(src.toString("utf8")), [], `${id}: source is inert`);
    const out = read(join(FIGURE_OUT_DIR, f.file));
    assert.deepEqual(svgActive(out), [], `${id}: served copy is inert`);
    if (f.keepLabel) {
      assert.ok(readFileSync(join(FIGURE_OUT_DIR, f.file)).equals(src), `${id}: served byte for byte`);
      continue;
    }
    // The served copy differs from the source only in declared text and in the accessible label, which is ours.
    const expected = [...f.edits.map((e) => [e.from, e.to]), ...f.teamText.map((t) => [t.from, t.anon])];
    const srcTexts = svgTexts(src.toString("utf8")), outTexts = svgTexts(out);
    assert.equal(outTexts.length, srcTexts.length, `${id}: same number of text runs`);
    srcTexts.forEach((t, i) => { if (t !== outTexts[i]) assert.ok(expected.some(([a, b]) => a.replace(/\s+/g, " ") === t && b.replace(/\s+/g, " ") === outTexts[i]), `${id}: undeclared change ${JSON.stringify(t)} -> ${JSON.stringify(outTexts[i])}`); });
    const strip = (s) => s.replace(/<text\b[^>]*>[\s\S]*?<\/text>/g, "").replace(/aria-label="[^"]*"/, "");
    assert.equal(strip(out), strip(src.toString("utf8")), `${id}: nothing but text runs and the label changed`);
    // The label is the reviewed alt text, its team tokens resolved by the consent on record, as on the slides.
    const shownAlt = committed.slides.map((s) => s.content.figure).find((x) => x?.id === id)?.alt ?? f.alt;
    assert.ok(out.includes(`aria-label="${shownAlt.replace(/&/g, "&amp;").replace(/"/g, "&quot;")}"`), `${id}: the label is the reviewed alt text`);
    assert.doesNotMatch(out, /\{(?:repo:)?[A-Za-z]+\}/, `${id}: no unresolved team token`);
  }
  assert.ok(svgActive('<svg><script>x()</script></svg>').length && svgActive('<svg><image href="https://example.com/a.png"/></svg>').length
    && svgActive('<svg><foreignObject/></svg>').length && svgActive('<svg onload="x()"/>').length, "the inert check can fail");
});
test("a figure that is not the reviewed file, names an unconsented team, or shrinks its text below 22 px does not build", () => {
  assert.throws(() => recorded({}, (f) => { f.figures.fig5.sha256 = "0".repeat(64); }), /not the reviewed file/);
  assert.throws(() => recorded({}, (f) => { f.figures.fig3.teamText.pop(); }), /still names FEAgent, who has not consented/);
  // Withdrawing Delfie's consent stops the build: fig6 is drawn for it, and aneta's plain figures name it.
  assert.throws(() => recorded({}, (f) => { f.teams.delfie.consent = null; }), /drawn for the consent set \[delfie, scienceclaw\], but consent is on record for \[scienceclaw\]/);
  assert.throws(() => recorded({}, (f) => { f.teams.delfie.consent = null; f.figures.fig6.drawnFor = ["scienceclaw"]; }), /still names Delfie, who has not consented/);
  assert.throws(() => recorded({}, (f) => { f.figures.fig1.edits = []; }), /public-render rule/, "the vendor name in the original fig1 label");
  assert.throws(() => recorded({}, (f) => { f.figures.fig4.scale = 0.9; }), /under 22 px/);
  assert.throws(() => recorded({}, (f) => { f.figures.fig6.edits = [{ from: "SentiLab", to: "SentiLab lab", why: "test" }]; }), /must be served byte for byte/);
  assert.throws(() => recorded({}, (f) => { f.figures.fig3.edits[0].from = "Ascend 911"; }), /must appear exactly once/);
  // The build itself refuses active content, whatever the file's hash.
  const fig5 = loaded.final.figures.fig5;
  const ctx = { teams: loaded.final.teams, named: new Set(), cutoffMs: Date.parse(loaded.final.cutoff) };
  const src = readFileSync(join(FIGURE_SOURCE_DIR, fig5.file), "utf8");
  assert.doesNotThrow(() => buildFigureFrom(Buffer.from(src), "fig5", fig5, ctx));
  for (const bad of ["<script>alert(1)</script>", '<foreignObject width="1" height="1"/>', '<image href="https://example.com/x.png"/>', '<rect onclick="x()"/>']) {
    assert.throws(() => buildFigureFrom(Buffer.from(src.replace("</svg>", `${bad}</svg>`)), "fig5", fig5, ctx), /is not inert/, bad);
  }
  assert.throws(() => buildFigureFrom(Buffer.from(src.replace("</svg>", "<text>Kiln</text></svg>")), "fig5", fig5, ctx), /still names Kiln/);
});
test("every figure time names a room record that carries its minute, and its durations are what the records give", () => {
  const f4 = loaded.final.figures.fig4;
  assert.deepEqual(f4.claims.map((c) => c.label), ["12:43", "13:15", "13:28", "14:26", "14:42", "14:53", "15:56", "16:40", "22:22", "23:01", "23:44", "00:03"]);
  for (const c of f4.claims) {
    const minutes = c.records.flatMap((r) => [r.at, r.stated].filter(Boolean)).map((t) => t.slice(11, 16));
    assert.ok(minutes.includes(c.label), c.label);
  }
  checkDuration("39 min", f4.claims[8].at, f4.claims[9].at, "round", "t");
  checkDuration("1 h 41", f4.claims[8].at, f4.claims[11].at, "round", "t");
  assert.throws(() => checkDuration("40 min", f4.claims[8].at, f4.claims[9].at, "round", "t"), /not what the records give/);
  assert.throws(() => checkDuration("Under 4 min", "2026-10-31T15:52:12.966Z", "2026-10-31T15:56:58.678Z", "under", "t"), /not what the records give/);
  assert.throws(() => recorded({}, (f) => { f.figures.fig4.claims[0].at = "2026-10-31T12:44:00.000Z"; }), /is not its claim's minute|which no record carries/);
  assert.throws(() => recorded({}, (f) => { f.figures.fig4.claims[0].label = "13:15"; }), /the label 13:15 is not its claim's minute 12:43/);
  assert.throws(() => recorded({}, (f) => { f.figures.fig4.claims[9].records[0].at = "2026-11-02T00:00:00.000Z"; }), /after the cutoff/);
  // plain4, aneta's lane chart on slide 4: every event time it shows (the hour ticks are its axis) has a claim whose
  // records carry that minute, and its durations are recomputed from them.
  const p4 = loaded.final.figures.plain4;
  const shown = new Set(recorded().slides.find((s) => s.id === "b-plain4").content.figure.texts.flatMap((t) => t.match(/\b\d\d:\d\d\b/g) ?? []).filter((t) => !t.endsWith(":00")));
  assert.deepEqual([...shown].sort(), p4.claims.map((c) => c.label).sort());
  for (const c of p4.claims) assert.ok(c.records.flatMap((r) => [r.at, r.stated].filter(Boolean)).some((t) => t.slice(11, 16) === c.label), c.label);
  assert.deepEqual(p4.durations.map((x) => x.text), ["32 min", "39 min", "1 h 41"]);
  assert.throws(() => recorded({}, (f) => { f.figures.plain4.durations[0].text = "31 min"; }), /does not show|not what the records give/);
  assert.throws(() => recorded({}, (f) => { f.figures.plain4.claims[1].at = "2026-10-31T13:09:00.000Z"; }), /is not its claim's minute/);
  assert.throws(() => recorded({}, (f) => { f.timeline.tiles[0].value = "31 min"; }), /not what the records give/);
  assert.throws(() => recorded({}, (f) => { f.timeline.tiles[2].value = "16:41"; }), /not its record minute/);
});

// ── 3. outside teams: named only with consent ───────────────────────────────────────────────────────────────────────
// The consents on record: ScienceClaw said yes in the help room (message 57532, 02:09:48 on 1 Nov; root confirmed it in
// team room 57540), and Delfie said yes (message 57644, 03:45:39), asking to be named "Delfie (delphisci team)". Every
// other flag is off.
const SCIENCECLAW = "32a841e5 seq 57532 at 2026-11-01T02:09:48.572Z";
const DELFIE = "32a841e5 seq 57644 at 2026-11-01T03:45:39.060Z";
const CONSENTED = ["Delfie", "ScienceClaw"];
test("only a team whose consent is on record is named: slides, notes, figures and generated data", () => {
  assert.deepEqual(Object.entries(loaded.final.teams).filter(([, t]) => t.consent).map(([id, t]) => [id, t.consent]), [["delfie", DELFIE], ["scienceclaw", SCIENCECLAW]]);
  assert.equal(loaded.final.teams.delfie.credit, "Delfie (delphisci team)", "the form Delfie asked for");
  const d = recorded();
  // The event is the ScienceClaw hackathon: its name in the slide header is the deck's, not a team's.
  assert.ok(everything(d).includes("ScienceClaw hackathon"));
  const all = everything(d).replaceAll(d.deck.event, "");
  for (const name of CONSENTED) assert.ok(named(all, name), `${name}, who consented, is named`);
  for (const name of TEAM_NAMES.filter((n) => !CONSENTED.includes(n))) {
    assert.ok(!named(all, name), `${name} appears on a slide`);
    for (const f of readdirSync(FIGURE_OUT_DIR)) assert.ok(!named(read(join(FIGURE_OUT_DIR, f)).replace(/data:image\/\w+;base64,[A-Za-z0-9+/=]+/g, ""), name), `${name} in ${f}`);
    // The served data is checked without regard to case: a lower-case id or handle names a team too.
    assert.doesNotMatch(read(join(FINAL_DECK_DIR, "deck-data.json")).replaceAll(committed.deck.event, ""), new RegExp(`(^|[^\\p{L}\\p{N}])${name}(?![\\p{L}\\p{N}])`, "iu"), `${name} in deck-data.json`);
  }
  assert.doesNotMatch(read(join(FINAL_DECK_DIR, "deck-data.json")), /zucalerega|feagent/i, "no repository name either");
  assert.deepEqual(committed.teams, { named: [{ name: "Delfie (delphisci team)", consent: { room: "32a841e5", seq: 57644, at: "2026-11-01T03:45:39.060Z" } },
    { name: "ScienceClaw", consent: { room: "32a841e5", seq: 57532, at: "2026-11-01T02:09:48.572Z" } }], unnamed: 6 });
  // Delfie in the form it asked for, its results as reported by them; the next unnamed team is "an outside team".
  assert.match(slideText(d, "stack"), /Delfie \(delphisci team\) ran both versions with the detailed 3-D mode off: both give 75\.37 C and 115\.29 C, as reported by them\./);
  assert.match(notesOf(d, "gate"), /Two outside teams checked us, as reported by them: Delfie \(delphisci team\) ran both versions, and an outside team used its own finite-element code\./);
  assert.match(slideText(d, "receipt"), /Reproduction Delfie \(delphisci team\): both simulator versions built from source/);
  assert.match(slideText(d, "receipt"), /An outside team \(public repository, frozen report at commit c73d642b\)/);
  assert.match(slideText(d, "receipt"), /Named with their consent, on record in the help room: Delfie \(delphisci team\), ScienceClaw\. The other 6 teams are not named here\./);
  assert.match(slideText(d, "t-step"), /Mode off, both versions agree, as reported by Delfie \(delphisci team\)\./);
  const answers = d.slides.filter((s) => /^qa(-\d+)?$/.test(s.id)).map((s) => slideText(d, s.id)).join("\n");
  assert.match(answers, /What should I do if I use HotSpot\? If you run version 7's detailed-3D mode on stacks like these, compare it against 6\.0\. Delfie reports that with that mode off, both versions give the same answer\./);
  // fig6 v1.15: the map after Delfie's consent and ScienceClaw's 04:01 re-run, drawn for exactly these two consents.
  assert.equal(loaded.final.figures.fig6.sha256, "e9eeadb9217c9849f47511795058857b685ad8980079575ae02625af82bf5e79", "aneta's v1.15, drawn for Delfie and ScienceClaw");
  assert.deepEqual(loaded.final.figures.fig6.drawnFor, ["delfie", "scienceclaw"]);
  assert.match(figureText(d, "teams"), /Delfie \| Both versions on our case in \| 39 min\. Then tested one change/);
  assert.match(figureText(d, "teams"), /Ran through the open-source \| ScienceClaw registry, executor \| ScienceClaw \| Re-ran our case: same numbers\. \| Used our review on its package/);
  assert.match(notesOf(d, "teams"), /ScienceClaw credited our matchmaking, and later used our review to fix its package\. Our rigidity skill ran through the open-source ScienceClaw registry and executor\.$/);
  assert.match(slideText(d, "teams"), /Help room, to 1 November 04:01 UTC; a dated snapshot\. Only teams that agreed are named\./);
  assert.match(slideText(d, "b-fig6"), /Help room, to 1 November 04:01 UTC\. Only teams that agreed are named\./);
  assert.match(slideText(d, "t-open"), /Only what each team said or did counts\. Help room, to 1 November 04:01 UTC\./);
  assert.match(figureText(d, "teams"), /blind solve, compared/);
  assert.equal(figureText(d, "b-fig6"), figureText(d, "teams"), "both backups show the same drawing");
  assert.match(notesOf(d, "t-open"), /ScienceClaw used our review to fix its package\.$/);
  assert.match(figureText(d, "gate"), /Delfie 75\.48 \| 78\.06 Outside/);
  assert.match(figureText(d, "timeline"), /Delfie reproduces \| it: 39 min/);
  assert.match(figureText(d, "timeline"), /Outside finite- \| element solve: 1 h 41/);
  assert.equal((figureText(d, "teams").match(/An outside team/g) ?? []).length, 6);
  // fig6 is drawn for exactly this consent set; with any other set the build stops until it is redrawn.
  assert.throws(() => recorded({}, (f) => { f.teams.scienceclaw.consent = null; }), /drawn for the consent set \[delfie, scienceclaw\], but consent is on record for \[delfie\]/);
  // The resolver on its own: two unnamed teams on one slide are "an outside team", then "a second outside team"; a
  // named team appears in the form it asked for.
  const line = "{Delfie} ran both versions, and {feagent} used its own finite-element code.";
  assert.equal(teamResolver(loaded.final.teams, new Set(["scienceclaw"]))([line])(line), "An outside team ran both versions, and a second outside team used its own finite-element code.");
  assert.equal(teamResolver(loaded.final.teams, new Set(["delfie"]))([line])(line), "Delfie (delphisci team) ran both versions, and an outside team used its own finite-element code.");
});
test("a consent line switches one team to its name, with a pointer to where it agreed, and nothing else moves", () => {
  // The flag is one line in FINAL.json.
  const text = read(FINAL_SOURCE);
  const flipped = text.replace(/("feagent": \{\n\s+"name": "FEAgent",\n\s+"repo": "[^"]+",\n\s+"consent": )null/, `$1"${consentLine(57490)}"`);
  assert.equal(flipped.split("\n").filter((l, i) => l !== text.split("\n")[i]).length, 1, "one changed line");
  // fig6 is aneta's drawing for Delfie and ScienceClaw, so a new consent first stops the build until she redraws it ...
  assert.throws(() => buildFinalData({ final: JSON.parse(flipped), hashes: loaded.hashes }, { rederived: true }), /drawn for the consent set \[delfie, scienceclaw\], but consent is on record for \[delfie, feagent, scienceclaw\]/);
  // ... and with a redrawn fig6 (simulated by its consent set alone) everything else switches by itself.
  const redrawn = JSON.parse(flipped);
  redrawn.figures.fig6.drawnFor = ["delfie", "feagent", "scienceclaw"];
  const d = buildFinalData({ final: redrawn, hashes: loaded.hashes }, { rederived: true });
  assert.deepEqual(d.teams.named.map((t) => [t.name, t.consent.seq]), [["Delfie (delphisci team)", 57644], ["FEAgent", 57490], ["ScienceClaw", 57532]]);
  assert.equal(d.teams.unnamed, 5);
  assert.match(notesOf(d, "gate"), /Delfie \(delphisci team\) ran both versions, and FEAgent used its own finite-element code\./);
  assert.match(figureText(d, "gate"), /122\.25 FEAgent/);
  assert.match(slideText(d, "receipt"), /FEAgent \(github\.com\/zucalerega\/feagent, frozen report at commit c73d642b\)/);
  assert.match(slideText(d, "receipt"), /Named with their consent, on record in the help room: Delfie \(delphisci team\), FEAgent, ScienceClaw\. The other 5 teams are not named here\./);
  for (const name of TEAM_NAMES.filter((n) => !["Delfie", "FEAgent", "ScienceClaw"].includes(n))) assert.ok(!named(everything(d).replaceAll(d.deck.event, ""), name), name);
  // No re-layout: the same slides, the same figures, the same text runs.
  const before = recorded();
  assert.deepEqual(d.slides.map((s) => s.id), before.slides.map((s) => s.id));
  for (const id of Object.keys(loaded.final.figures)) assert.equal(d.slides.flatMap((s) => (s.content.figure?.id === id ? [s.content.figure.texts.length] : []))[0] ?? null, before.slides.flatMap((s) => (s.content.figure?.id === id ? [s.content.figure.texts.length] : []))[0] ?? null, id);
  // A consent after the cutoff, or in another form, does not build.
  assert.throws(() => recorded({}, (f) => { f.teams.kiln.consent = consentLine(57490, "2026-11-02T00:00:00Z"); }), /dated after the cutoff/);
  assert.throws(() => recorded({}, (f) => { f.teams.kiln.consent = "yes"; }), /consent must read/);
  assert.equal(parseConsent(null, "x"), null);
  // A name written into the source outside a team token is refused while that team has not consented.
  assert.throws(() => recorded({}, (f) => { f.checks.caption += " Thanks, Kiln."; }), /Kiln has not consented to be named/);
});

// ── 4. slide 4: one flag, the reviewed wording, outcomes that cannot contradict their values ─────────────────────────
test("the reviewer's slide-4 wording is kept word for word: its link sentences on slide 2, its test sentence on slide 4", () => {
  assert.equal(loaded.final.gate.common, WORDING.common);
  for (const g of GATES) assert.equal(loaded.final.gate.variants[g].text, WORDING[g], g);
  const { link, test: testLine } = splitCommon(WORDING.common);
  const d = recorded();
  assert.ok(slideText(d, "stack").includes(link.replace(/`/g, "")), "slide 2 carries the link sentences");
  assert.ok(slideText(d, "gate").includes(testLine), "slide 4 carries the test sentence");
  assert.throws(() => recorded({}, (f) => { f.stack.text = f.stack.text.replace("convection", "the convection term"); }), /word for word/);
  // Any other outcome keeps the whole paragraph on slide 4.
  for (const g of GATES) {
    const s4 = slideText(variant(g), "gate");
    assert.match(s4, /differs between versions/);
    assert.doesNotMatch(s4, /\bbugs?\b/i);
    assert.ok(s4.includes(WORDING.common.replace(/`/g, "")), `${g}: the common wording`);
  }
});
test("the --gate flag selects exactly one outcome on slide 4; any outcome but the recorded one is marked REVIEW and never exported", () => {
  for (const g of GATES) {
    const d = variant(g);
    const s4 = slideText(d, "gate");
    assert.equal(d.deck.variant, g);
    for (const other of GATES) {
      const text = WORDING[other].replace("[values]", "");
      const shown = s4.includes(text.split(":")[0]) && s4.includes(text.slice(-30));
      assert.equal(shown, other === g, `${g}: ${other} wording ${other === g ? "missing" : "leaked"} on slide 4`);
    }
    const detail = slideText(d, "gate-detail");
    for (const other of GATES) assert.ok(detail.includes(WORDING[other].slice(0, 40)), `${g}: backup lists ${other}`);
    assert.match(detail, new RegExp(`${d.deck.variantLabel} .*this export`));
    assert.equal(d.deck.reviewOnly, true);
    for (const s of slidesOf(d)) assert.match(s.text, /REVIEW · not the recorded result/, `${g} ${s.id}`);
    assert.throws(() => finalPdfName(d), /review render of another outcome never exports a PDF/);
    // Values that are not the recorded result never carry its figure, scope or verification state.
    assert.equal(d.slides.find((s) => s.id === "gate").content.figure, null);
    assert.doesNotMatch(s4, /Verified by the operator|in the operator's words/, g);
  }
  // The outcome box holds exactly the chosen wording, with the values filled in, and nothing else.
  const box = (d) => visible(/<div class="variant v-[\w-]+"><span class="pill">[^<]*<\/span><p>([\s\S]*?)<\/p><\/div>/.exec(Deck.renderSlides(d))[1]);
  assert.equal(box(variant("not-run")), WORDING["not-run"]);
  assert.equal(box(variant("pass")), WORDING.pass);
  assert.equal(box(variant("fail")), WORDING.fail.replace("[values]", "77.10 C and 116.02 C"));
  assert.equal(box(recorded()), WORDING.pass);
  assert.match(slideText(variant("pass"), "gate"), /75\.61 C \+0\.13 K · within/);
  assert.match(slideText(variant("fail"), "gate"), /It missed: 77\.10 C and 116\.02 C\. Our explanation is incomplete, and the withdrawal stands\./);
  assert.match(slideText(variant("fail"), "gate"), /77\.10 C \+1\.62 K · outside/);
  assert.match(slideText(variant("not-run"), "gate"), /not run must be within 1\.0 K.*not run must be within 1\.0 K/);
  assert.doesNotMatch(Deck.renderSlides(committed), /REVIEW ·|PREVIEW/);
});

// The reviewed gate result, as the operator posted it (team room, message 57377, 23:45:43Z): paper 75.48 and 115.94 C,
// HotSpot 6.0 at a 64 by 64 grid 75.48 and 115.93 C, HotSpot 7.0 default 123.42 and 232.67 C; independently re-derived
// from the signed raw outputs by a second reviewer (message 57394, 00:05:37Z on 1 Nov).
test("the recorded result is the default export: PASS with its figure, the operator's exact scope and the re-derivation", () => {
  const r = loaded.final.gate.result;
  assert.deepEqual([r.outcome, r.measured], ["pass", "75.48,115.93"]);
  assert.deepEqual(r.comparator.values, ["123.42", "232.67"]);
  assert.ok(r.records.some((x) => x.ref === "seq 57377" && x.author === "claude-warden" && x.at === "2026-10-31T23:45:43.792Z"));
  assert.ok(r.records.some((x) => x.ref === "seq 57394" && x.author === "gpt-astra-carter" && x.at === "2026-11-01T00:05:37.132Z"));
  const d = recorded();
  assert.deepEqual([d.build.gate, d.build.measured, d.build.rederived], ["pass", "75.48,115.93", true]);
  const s4 = slideText(d, "gate");
  assert.equal(d.slides.find((s) => s.id === "gate").content.figure.id, "fig3");
  assert.match(figureText(d, "gate"), /Paper 75\.48 \| Our run 75\.48/);
  assert.match(figureText(d, "gate"), /Paper 115\.94 \| Our run 115\.93/);
  assert.match(figureText(d, "gate"), /Our run 232\.67/);
  assert.ok(s4.includes(WORDING.pass), "the reviewer's PASS wording");
  assert.match(s4, /Verified by the operator and independently re-derived from signed raw outputs by a second reviewer\./);
  // The scope is the operator's, word for word and marked as a quotation, with the statistic named.
  assert.ok(s4.includes(`Scope, in the operator's words: “${OPERATOR_SCOPE}”`), "the operator's exact scope");
  assert.match(s4, /Statistic: the maximum native block output under centre mapping\./);
  assert.doesNotMatch(s4, /\bbugs?\b/i);
  assert.match(notesOf(d, "gate"), /^We fixed a test in advance: the older version must reproduce both published numbers within one kelvin\. It passed, which reproduces those numbers but does not prove physical accuracy\. A second reviewer has independently re-derived it from the signed raw outputs\./);
  const detail = slideText(d, "gate-detail");
  assert.match(detail, /PASS 75\.48 C and 115\.93 C Verified by the operator and independently re-derived from signed raw outputs/);
  assert.match(detail, /Version comparison on the same layouts and readout: version 7\.0 gives 123\.42 C and 232\.67 C, 48 to 117 K above the paper\./);
  assert.match(detail, /Compute, for the validation container only: 23\.0 CPU-seconds of 562 reserved \(cap 600\); the solver used 17\.86\. Not the cost of the build, the models or the project\./);
  assert.match(slideText(d, "chronology"), /23:44 The fixed test runs from 23:41 to 23:44, and the operator reports PASS/);
  assert.match(slideText(d, "chronology"), /12:43 A person asks why the study was inconclusive and how to match the published reference design/);
  assert.doesNotMatch(everything(d), /human engineers built|human design/);
});
test("the frozen gate statistic, the chiplet-centre means and the chip-layer and active-grid peaks are never run together", () => {
  const d = recorded();
  const said = sentences(everything(d));
  assert.ok(said.some((s) => s.includes("115.935")) && said.some((s) => s.includes("119.07")) && said.some((s) => s.includes("240.53")));
  for (const s of said) {
    if (s.includes("115.935")) assert.match(s, /chiplet-centre/i, s);
    if (/\b119\.07\b|\b240\.53\b/.test(s)) assert.match(s, /active-grid|chip-layer grid maxima/i, s);
  }
  assert.match(slideText(d, "problem"), /119 and 241 are chip-layer grid maxima \(119\.07 C and 240\.53 C\)\. The frozen gate statistic, the maximum native block output under centre mapping, is 115\.93 C and 232\.67 C; in 7\.0 that maximum is a substrate block, not a chip\./);
  assert.match(figureText(d, "problem"), /Frozen gate statistic \| 115\.93 → 232\.67 °C/);
  assert.match(slideText(d, "gate"), /Chiplet-centre means \(75\.475 and 115\.935 C\) and active-grid peaks \(75\.48 and 119\.07 C\) are separate\./);
});
test("one flag, --rederived, flips the verification state, and only for the recorded result", () => {
  const before = build();
  assert.equal(before.build.rederived, false);
  assert.match(slideText(before, "gate"), /Verified by the operator; independent re-derivation by a second reviewer in progress\./);
  const s4 = slideText(recorded(), "gate");
  assert.match(s4, /independently re-derived from signed raw outputs by a second reviewer\./);
  assert.doesNotMatch(s4, /in progress/);
  assert.throws(() => build({ gate: "not-run", rederived: true }), /--rederived applies only/);
  assert.throws(() => build({ gate: "pass", measured: "75.61,116.02", rederived: true }), /--rederived applies only/);
  assert.throws(() => build({ gate: "pass", preview: true, rederived: true }), /--rederived applies only/);
});
test("a recorded result that its own numbers contradict does not build", () => {
  assert.throws(() => build({}, (f) => { f.gate.result.comparator.text = f.gate.result.comparator.text.replace("48 to 117 K", "48 to 116 K"); }), /must say "48 to 117 K"/);
  assert.throws(() => build({}, (f) => { f.gate.result.comparator.notes = f.gate.result.comparator.notes.replace("117", "120"); }), /notes must say "48 to 117 degrees"/);
  assert.throws(() => build({}, (f) => { f.gate.result.measured = "77.48,115.93"; }), /PASS contradicts/);
  assert.throws(() => build({}, (f) => { f.gate.result.records[0].at = "2026-11-02T00:00:00.000Z"; }), /after the cutoff/);
  assert.throws(() => build({ gate: "pass" }, (f) => { delete f.gate.result; }), /needs --measured/);
});
test("an outcome its values contradict, or one without reviewed wording, does not build", () => {
  const refuse = (o, re) => assert.throws(() => build(o), (e) => e instanceof FinalError && re.test(e.message), JSON.stringify(o));
  refuse({ gate: "pass", measured: "76.61,116.02" }, /PASS contradicts/);
  refuse({ gate: "fail", measured: "75.61,116.02" }, /FAIL contradicts/);
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
});

// ── 5. slides 2, 3, 5 and 6 ─────────────────────────────────────────────────────────────────────────────────────────
test("the review line is the author's corrected wording, attributed, on slide 5 and in backup", () => {
  assert.equal(loaded.final.how.evidence.line, REVIEW_LINE);
  assert.equal(loaded.final.backup.reviews.line, REVIEW_LINE);
  assert.ok(loaded.final.how.evidence.records.some((r) => r.ref === "seq 57392" && r.author === "aneta-claude" && r.at === "2026-11-01T00:03:42.458Z"));
  assert.throws(() => recorded({}, (f) => { f.how.evidence.line = REVIEW_LINE.replace("80 of 190", "80 of 191"); }), /same on slide 5 and in backup/);
  const d = recorded();
  const html = Deck.renderSlides(d);
  for (const id of ["checks", "reviews"]) {
    const sec = new RegExp(`id="s-${id}"[\\s\\S]*?<p class="rline[^"]*">([\\s\\S]*?)<\\/p>`).exec(html);
    assert.ok(sec, `${id}: the line renders as one paragraph`);
    assert.equal(decode(sec[1]), REVIEW_LINE, id);
  }
  const checks = slideText(d, "checks");
  assert.match(checks, /The review author's tally from the room log; a second reviewer independently retrieved its row file and re-counted it\./);
  assert.doesNotMatch(checks, /at least 4|not been independently retrieved/);
  assert.equal((checks.match(/4 of the 17/g) ?? []).length, 1, "the approver's four, once");
  assert.ok(loaded.final.how.evidence.records.some((r) => r.ref === "seq 57559" && r.at === "2026-11-01T02:34:08.150Z"));
  assert.match(checks, /Controlled test with seeded defects Designed to compare agents with defects planted in advance\. It has not run yet; when it does, its result goes here, whatever it shows\./);
  assert.match(figureText(d, "checks"), /17 at a version another agent had approved \| 63 more where a later agent was first \| 110 others/);
  assert.equal(notesOf(d, "checks"), `Why many agents? ${REVIEW_LINE}`);
  const rv = slidesOf(d).find((s) => s.id === "reviews");
  assert.equal(rv.main, false);
  assert.match(rv.text, /First recorded by a later reviewer 80 \(42\.1%\)/);
  assert.match(rv.text, /Of the 80, at the same version after a recorded approval 17, in 7 pull requests/);
  assert.doesNotMatch(everything(d), /(^|[\s(])\+1(?!\d|[.,]\d)/m, "no \"+1\" on any slide or note");
  assert.doesNotMatch(everything(d), /\b191\b|\b18 were found|in 8 pull requests|24 of 74|41\.9%/);
  assert.match(slideText(d, "how"), /Three agents sealed their findings before reading each other's; one had seen a one-line preview\./);
});
test("slides 2 and 3 describe modeled nodes and the record, never a copper layer, a bug or a single cause", () => {
  const d = recorded();
  assert.match(slideText(d, "stack"), /the same x\/y grid index through the modeled layers, shown exploded\. Spreader to sink: 4\.04 K in 6\.0, 141\.77 K in 7\.0\. Modeled nodes, not a copper layer\. This localizes the difference; it does not by itself show a single cause\./);
  assert.match(figureText(d, "stack"), /4\.04 K \| spreader to sink/);
  assert.match(figureText(d, "stack"), /141\.77 K \| spreader to sink/);
  assert.match(slideText(d, "profile"), /layout A 1\.24 K in 6\.0 and 55\.31 K in 7\.0; the CPU-DRAM layout 4\.04 K and 141\.77 K/);
  assert.match(slideText(d, "metrics"), /eight retained probes \(four floorplans at two grid sizes\)/);
  const all = everything(d);
  assert.doesNotMatch(all, /copper layers? (?:measurement|drop)|across copper|lost between|isolates? one term|one-change test/i);
  assert.doesNotMatch(all, /eight (?:layouts|floorplans|cases)/i);
  assert.match(slideText(d, "timeline"), /Under 5 min from one agent's proposal to the halt; two others agreed first/);
  assert.match(figureText(d, "timeline"), /Agents halt their own public \| run, under 5 min after one \| proposed it/);
  assert.doesNotMatch(all, /no (?:person|human|one) asked/i);
});
// Root's scoped +1 for the layer-maxima panel (team room 57511, 01:51:42): the sentence and caption word for word, the
// finite-element team's name behind its consent flag.
test("the layer-maxima backup carries root's sentence and caption word for word, apart from the same-index values", () => {
  const SENTENCE = "Two separate FE implementations (ours and an outside team's) give spreader-minus-sink layer-maximum contrasts of about 1.30 K and 4.20 K, much closer to HotSpot 6 than HotSpot 7. The remaining FE–HotSpot 6 offset is also visible in the sink-layer maxima; its cause remains open.";
  const CAPTION = "Difference of independently located layer maxima; FE nodal versus HotSpot grid readouts. One configured model, simulated.";
  const d = recorded();
  const s = slidesOf(d).find((x) => x.id === "layers");
  assert.equal(s.main, false, "backup only: the talk has no room for it under the 180 s cap");
  assert.ok(s.text.includes(SENTENCE), "root's sentence, anonymous wording");
  assert.ok(s.text.includes(CAPTION), "root's caption");
  assert.match(s.text, /Chip minus sink, both finite-element solves agree with HotSpot 6\.0 within 0\.44 K\./);
  assert.match(s.text, /CPU-DRAM, spreader minus sink 3\.25 141\.84 4\.20 4\.21/);
  assert.match(s.text, /not the same-index column of the exploded stack \(4\.04 K and 141\.77 K there\)/);
  assert.doesNotMatch(s.text, /8 to 9|8–9|percent|convection|isn't in the stack|compact sink/i);
  // fig2 on slide 2 carries the same panel (aneta's v1.4, team room 57516), captioned in root's words, and its
  // independent-peak values stay apart from the same-index exploded view.
  assert.match(figureText(d, "stack"), /Spreader minus sink, \| separate layer maxima \| 3\.25 K \| HotSpot 6\.0 \| about 4\.20 K \| 2 finite-element codes \| 141\.84 K \| HotSpot 7\.0/);
  assert.ok(slideText(d, "stack").includes(`Panel at right: ${CAPTION}`), "root's caption under the panel");
  const consented = buildFinalData({ final: (() => { const f = clone(loaded.final); f.teams.feagent.consent = consentLine(57495); f.figures.fig6.drawnFor = ["delfie", "feagent", "scienceclaw"]; return f; })(), hashes: loaded.hashes }, { rederived: true });
  assert.ok(slideText(consented, "layers").includes(SENTENCE.replace("an outside team's", "FEAgent's")));
  assert.throws(() => recorded({}, (f) => { f.backup.layers.rows[3].values[2] = "15.38"; }), /not within 0\.44 K/);
  assert.throws(() => recorded({}, (f) => { f.backup.layers.rows[1].values[3] = "4.30"; }), /"about" values/);
});
test("outside teams: results as reported by them, the blindness note, the open gap, and the leaderboard only as not-evidence", () => {
  const d = recorded();
  const receipt = slideText(d, "receipt");
  assert.match(receipt, /78\.060 C and 122\.252 C, \+2\.58 K and \+6\.31 K over the paper\. As reported by them\./);
  assert.match(receipt, /its author declares no reading of peer values before freezing at 23:45 UTC/);
  assert.match(receipt, /posted in the shared help room from 23:04 UTC, and to that team directly at 23:18, which shows they were available, not that they were read/);
  assert.match(slideText(d, "metrics"), /An outside team, as reported by them: 78\.060 C and 122\.252 C \(\+2\.58 K and \+6\.31 K\)\./);
  assert.match(slideText(d, "gate"), /Finite element sits 8 to 9 percent above 6\.0 in rise; that gap is open\./);
  const all = everything(d);
  // The answer sheet's note to the authors is the one thing still pending; no outside result is.
  assert.doesNotMatch(all.replace("Sending it is still pending.", ""), /still pending/i);
  for (const s of sentences(all)) if (/0\.001 K|thousandth/.test(s)) assert.match(s, /extrapolat/, s);
  for (const s of slidesOf(d)) for (const m of s.text.matchAll(/[^.]*leaderboard[^.]*\./gi)) {
    assert.match(m[0], /not (?:used|counted) as evidence|not independent|Notice on the leaderboard/i, `${s.id}: ${m[0]}`);
  }
  assert.match(slideText(d, "teams"), /Only what the receiving team said or did counts as confirmed\./);
  // fig6 v1.15's legend, and the same words in the backup notes and on slide 7 (script v2.5).
  assert.match(figureText(d, "teams"), /3 checked our thermal case \| 2 said other help was useful \| 3 haven't confirmed yet/);
  assert.match(notesOf(d, "teams"), /We offered help to eight outside teams: three checked our thermal case, two told us other help was useful, and three haven't confirmed\./);
  assert.match(notesOf(d, "t-open"), /We offered help to eight teams\. Three re-checked our thermal result themselves, and ScienceClaw used our review to fix its package\./);
  assert.doesNotMatch(everything(d), /used it and returned a result|said it helped in their own words/);
});

// ── 6. by the numbers ───────────────────────────────────────────────────────────────────────────────────────────────
test("by the numbers: at most four values, each the quant pack's own value and label, with its caveat", () => {
  const N = loaded.final.numbers;
  assert.equal(N.placeholder, false);
  const pack = readFileSync(join(REPO_ROOT, N.source.path));
  assert.equal(sha(pack), N.source.sha256, "the repository copy is the pack the slide was read from");
  const entries = pack.toString("utf8").split(/\n(?=\*\*\d+\. )/).filter((e) => /^\*\*\d+\. /.test(e));
  assert.equal(entries.length, 8);
  // The pack's own count for the window it was collected in; warden's recount at 00:25 is the caveat, not the value.
  assert.deepEqual(N.items.map((x) => [x.value, x.class, x.tag ?? x.class]), [["90", "MEASURED", "MEASURED"], ["5 min 46.2 s", "MEASURED", "MEASURED"], ["$6,376.21", "MEASURED", "POSTED SO FAR"]]);
  assert.match(N.items[0].label, /^pull requests merged since 31 Oct 00:00 UTC, collected 1 Nov 00:22–00:27 UTC \(121 opened\); median 44 min 28 s from open to merge$/);
  assert.match(N.items[0].caveat, /A recount at 00:25 UTC found 91\.$/);
  assert.match(N.items[2].label, /^cloud cost posted by 02:44 UTC for 31 Oct \(whole account; includes lagged earlier-day usage\)$/);
  // The backup slide's notes say what its tiles say.
  assert.equal(N.notes, "By the numbers, measured: from midnight UTC on Saturday to the count at 00:22 to 00:27 on Sunday, we merged 90 pull requests. The cloud cost posted by 02:44 UTC for Saturday is 6,376 dollars for the whole account, and it is still posting.");
  // warden's re-reads (team room, reply eebd4c7c to 57558, 02:45:35) carry their record; the rest are the pack's.
  for (const x of N.items.filter((y) => y.record)) assert.deepEqual([x.record.ref, x.record.at], ["reply eebd4c7c-34f7-4760-9718-de3b0471b20f to seq 57558", "2026-11-01T02:45:35.476Z"]);
  for (const x of N.items.filter((y) => !y.record)) {
    const entry = entries.find((e) => e.replace(/^\*\*\d+\. /, "").startsWith(`${x.value.replace(/ h$/, "")} `));
    assert.ok(entry, `${x.value} opens a headline in the pack`);
    assert.ok(entry.includes(`- ${x.class}.`), `${x.value} is ${x.class} in the pack`);
  }
  assert.match(N.items[2].caveat, /Still posting, so it can only rise\. An operator-reported total for the whole account, not only the hackathon\./);
  const d = recorded();
  const shown = slideText(d, "numbers");
  // No savings estimate anywhere in the deck (aneta, 57554): no baseline, and it would contradict the backup.
  assert.doesNotMatch(everything(d), /ESTIMATE|engineer-hours|360–720|28,800|savings figure/);
  N.items.forEach((x, i) => {
    assert.ok(shown.includes(`${x.tag ?? x.class} · ${i + 1} ${x.value} ${x.label}`), `tile ${i + 1}`);
    assert.ok(shown.includes(`${i + 1}. ${x.caveat}`), `caveat ${i + 1}`);
  });
});
test("the numbers slide refuses values or labels the pack does not have, a fifth number, and an unread pack", () => {
  const refuse = (mutate, re) => assert.throws(() => recorded({}, mutate), (e) => e instanceof FinalError && re.test(e.message));
  refuse((f) => { f.numbers.items[0].value = "91"; }, /is not in the quant pack/);
  refuse((f) => { f.numbers.items[1].class = "ESTIMATE"; }, /but the quant pack does not/);
  // A value read after the pack (warden's re-read) needs its own room record, before the cutoff.
  refuse((f) => { delete f.numbers.items[2].record; }, /is not in the quant pack/);
  refuse((f) => { f.numbers.items[2].record.at = "2026-11-02T00:00:00Z"; }, /after the cutoff/);
  refuse((f) => { f.numbers.source.sha256 = "0".repeat(64); }, /is not the one the slide was read from/);
  refuse((f) => { f.numbers.items.push(clone(f.numbers.items[0]), clone(f.numbers.items[1])); }, /one to four numbers/);
  refuse((f) => { f.numbers.source.readAt = "2026-11-02T00:00:00Z"; }, /read after the cutoff/);
  refuse((f) => { f.numbers.placeholder = true; }, /carries no numbers/);
  const d = recorded({}, (f) => { f.numbers.placeholder = true; f.numbers.items = []; f.numbers.source = null; });
  assert.match(slideText(d, "numbers"), /PLACEHOLDER/);
  assert.doesNotMatch(slideText(d, "numbers"), /MEASURED|ESTIMATE/);
});

// ── 7. script v3: the ten main slides ───────────────────────────────────────────────────────────────────────────────
// aneta's 3+2 arc (team room 57701), assembled by the coordinator with root's and chatgpt's corrections as script v3,
// committed byte for byte as PLAIN-SCRIPT.md, and its short cut as PLAIN-SCRIPT-SHORT.md. Each main slide is built
// from its "Screen:" line; its notes are its "Say" text, exactly.
const PLAIN_SCRIPT = join(FINAL_DIR, "PLAIN-SCRIPT.md");
const SHORT_SCRIPT = join(FINAL_DIR, "PLAIN-SCRIPT-SHORT.md");
const scriptSections = (file) => read(file).split(/\n(?=## \d+\. )/).slice(1).map((sec) => {
  const say = (label) => new RegExp(`^${label}: (.*)$`, "m").exec(sec)?.[1].trim() ?? null;
  return { heading: /^## \d+\. (.*)$/m.exec(sec)[1].trim(), say: say("Say"), live: say("Say \\(LIVE\\)"), recorded: say("Say \\(RECORDED\\)") };
});
const liveReview = (options = {}, mutate) => recorded({ demoStatus: "live", demoReview: true, ...options }, mutate);
const short = (options = {}, mutate) => recorded({ slot: "3total", ...options }, mutate);
const PT = loaded.final.plainTalk;
test("the main slides are script v3's ten: each slide's heading and its words in the notes, exactly", () => {
  assert.equal(sha(readFileSync(PLAIN_SCRIPT)), "48b68cd60c226d5fdb452a1522053cca30b565ca602e662cc32452223a54d768", "script v3.1 as sent");
  const V = scriptSections(PLAIN_SCRIPT);
  assert.equal(V.length, 10);
  const d = recorded();
  const main = d.slides.filter((s) => s.main);
  assert.deepEqual(main.map((s) => s.id), MAIN);
  PT.slides.forEach((t, i) => assert.equal(t.heading, V[i].heading.replace(/ \(Demo clock.*\)$/, ""), t.id));
  // Slide 1 is the hook: its top line, not a heading, opens it; every other slide shows its heading as its title.
  assert.equal(main[0].content.title, null);
  main.slice(1).forEach((s, i) => assert.equal(s.content.title, PT.slides[i + 1].heading, s.id));
  V.slice(0, 9).forEach((x, i) => assert.equal(main[i].notes.text, x.say, main[i].id));
  assert.equal(notesOf(d, DOOR), V[9].recorded, "RECORDED by default");
  assert.equal(notesOf(liveReview(), DOOR), V[9].live);
});
test("the short cut (--slot 3total) speaks script v3.1-short over the same screens, slides 3 and 8 in backup, a 60 s demo", () => {
  assert.equal(sha(readFileSync(SHORT_SCRIPT)), "3aed8f61a42ed79b3c720f3cca8b63eff478c37abe2d64485b4fe486f2f3bf77", "script v3.1-short as sent");
  const S = scriptSections(SHORT_SCRIPT);
  assert.equal(S.length, 8);
  const d = short();
  assert.equal(d.build.slot, "3total");
  const main = d.slides.filter((s) => s.main);
  assert.deepEqual(main.map((s) => s.id), MAIN.filter((id) => !["t-team", "t-open"].includes(id)));
  S.slice(0, 7).forEach((x, i) => assert.equal(main[i].notes.text, x.say, main[i].id));
  assert.doesNotMatch(main.map((s) => s.notes.text).join(" "), /\bwrong\b|receipts are yours/i, "v3.1-short carries v3.1's two fixes (team room 57719)");
  assert.equal(notesOf(d, DOOR), S[7].recorded);
  assert.equal(notesOf(short({ demoStatus: "live", demoReview: true }), DOOR), S[7].live);
  // The same screens: every main slide's content is the full talk's.
  const full = recorded();
  for (const s of main) assert.deepEqual(s.content, full.slides.find((x) => x.id === s.id).content, s.id);
  // The two moved slides lead the backup, with the full talk's words as their notes.
  assert.deepEqual(d.slides.filter((s) => !s.main).slice(0, 2).map((s) => s.id), ["t-team", "t-open"]);
  assert.deepEqual([d.budget.talkCapSeconds, d.budget.demoSeconds, d.budget.maxSeconds], [120, 60, 180]);
  assert.throws(() => recorded({ slot: "4min" }), /--slot must be one of 3\+2, 3total/);
});
test("the pictures follow the coordinator's mapping, from reviewed values only", () => {
  const d = recorded();
  const c = (id) => d.slides.find((s) => s.id === id).content;
  // 1: two bars to scale from the reviewed chip-layer peaks, 119.07 and 240.53, rounded.
  assert.deepEqual(c("t-hook").hook.bars.map((b) => [b.value, b.label, b.tone]), [["119°C", "older version 6.0", "older"], ["241°C", "newer version 7.0", "newer"]]);
  assert.equal(c("t-hook").hook.bars[0].share, 119.07 / 240.53);
  assert.equal(c("t-hook").hook.top, "One published chip design · same input files · same 3D mode");
  assert.match(slideText(d, "t-hook"), /Hottest spot on the chips · simulated, not silicon/);
  assert.throws(() => recorded({}, (f) => { f.plainTalk.slides[0].hook.bars[1].value = 241; }), /is not a reviewed peak/);
  // 2: the cropped 3D still beside the three steps and the punchline.
  assert.deepEqual([c("t-grader").still.id, c("t-grader").still.label], ["render", "simulated, not silicon"]);
  assert.match(slideText(d, "t-grader"), /Agent proposes simulator scores agent chases the score Unchecked grader → confident agent\./);
  assert.doesNotMatch(`${slideText(d, "t-grader")} ${notesOf(d, "t-grader")} ${notesOf(d, "t-lesson")}`, /\bwrong\b|receipts are yours/i, "aneta's two fixes (team room 57719)");
  // 3: two person cards and five role chips; no names until Carter says yes.
  assert.deepEqual(c("t-team").roles.map((r) => r.role), ["builder", "guard", "fact-checker", "skeptic", "science reader"]);
  assert.ok(c("t-team").people.every((p) => p.name === null) && c("t-team").roles.every((r) => r.agent === null));
  assert.match(slideText(d, "t-team"), /Each agent has its own tools, data and job/);
  // 4: the three reports at their record minutes, and the 32 minutes recomputed.
  assert.deepEqual(c("t-reports").cards.map((k) => k.when), ["sealed 13:06", "posted 13:15", "posted 13:15"]);
  assert.match(slideText(d, "t-reports"), /Together: a suspect in 32 minutes\./);
  assert.match(slideText(d, "t-reports"), /Sealed before reading each other's full reports; one had seen a one-line preview\. In the review log, later agents raised 17 issues after an approval; descriptive, not controlled\./);
  assert.throws(() => recorded({}, (f) => { f.plainTalk.slides[3].cards[0].when = "sealed 13:07"; }), /not its record minute 13:06/);
  assert.throws(() => recorded({}, (f) => { f.plainTalk.slides[3].together.value = "31 min"; }), /not what the records give/);
  // 5: the orange statement, its "under 5 minutes" recomputed.
  assert.deepEqual(c("t-stop").statement, ["1 agent proposed", "2 agreed", "under 5 minutes to halt", "numbers withdrawn in public"]);
  assert.throws(() => recorded({}, (f) => { f.plainTalk.slides[4].duration.value = "Under 4 min"; }), /not what the records give/);
  assert.throws(() => recorded({}, (f) => { f.plainTalk.slides[4].records[0].at = "2026-11-02T00:00:00Z"; }), /after the cutoff/);
  // 6: plain2 v1.11 with the reported line, credited in the caption.
  assert.equal(c("t-step").figure.id, "plain2");
  assert.match(slideText(d, "t-step"), /Delfie changed only that step: most of the gap went away\. ScienceClaw got the same\..*Mode off, both versions agree, as reported by Delfie \(delphisci team\)\./);
  // 7: plain3 v2 with the two-row test, each row the recorded result against its published reference.
  assert.equal(c("t-bar").figure.id, "plain3");
  assert.deepEqual(c("t-bar").table.map((r) => [r.published, r.ours, r.result]), [["75.48", "75.48", "PASS"], ["115.94", "115.93", "PASS"]]);
  assert.match(slideText(d, "t-bar"), /A reproduction, not proof of physical accuracy\./);
  assert.throws(() => recorded({}, (f) => { f.plainTalk.slides[6].table[1].ours = "115.94"; }), /is not the recorded result/);
  // 8: big numbers and two cards; no leaderboard claim.
  assert.deepEqual(c("t-open").numbers.map((x) => x.value), ["8", "3", "2", "3"]);
  assert.deepEqual(c("t-open").cards, ["ScienceClaw fixed its package using our review", "A blind cross-team solve started in our room"]);
  assert.doesNotMatch(slideText(d, "t-open"), /leaderboard|top 3/i);
  // 9: the closer, the check line, and aneta's why figure under it.
  assert.match(slideText(d, "t-lesson"), /An optimizer is only as reliable as the tool grading it\. Independent checks expose disagreements before we build on them\. Using the newer version's 3D mode\? Check it against the older one\./);
  assert.equal(c("t-lesson").figure.id, "plain6");
  // One picture per main slide at most, and the backup keeps the figures that left the main deck.
  for (const m of Deck.renderSlides(d).matchAll(/<section class="slide main" id="s-([\w-]+)"[^>]*>([\s\S]*?)<\/section>/g)) {
    assert.ok((m[2].match(/<img /g) ?? []).length <= 1, `${m[1]}: one picture`);
  }
  assert.deepEqual(d.slides.filter((s) => s.id.startsWith("b-")).map((s) => s.content.figure.id), ["plain1", "plain4", "plain5", "fig6"]);
});
test("names stay off the slides until Carter says yes; the talk's own words may name the co-lead", () => {
  assert.equal(PT.namesOnStage, false);
  assert.throws(() => recorded({}, (f) => { f.plainTalk.namesOnStage = true; }), /names are on, but a person or an agent has no name to show/);
  // The public-render rule still refuses a person's name on a slide ...
  assert.throws(() => recorded({}, (f) => { f.plainTalk.slides[2].people[1].card = "Aneta builds AI agents"; }), /public-render rule/);
  // ... while the script's spoken line keeps it, in the notes only.
  assert.match(notesOf(recorded(), "t-team"), /Aneta builds AI agents and research pipelines\./);
  assert.doesNotMatch(slideText(recorded(), "t-team"), /Aneta|Carter/);
});
test("the door: LIVE shows the address, its QR code and three steps; RECORDED shows only real recorded runs, or says there are none", () => {
  const D = loaded.final.demo;
  const live = liveReview();
  const html = (d) => /id="s-t-door"[\s\S]*?<\/section>/.exec(Deck.renderSlides(d))[0];
  assert.match(html(live), /<p class="dcta-url">sentilab\.aidenid\.com<\/p>/);
  assert.match(html(live), /data-qr="https:\/\/sentilab\.aidenid\.com"/);
  assert.match(slideText(live, DOOR), /say you're here to place chiplets get a one-hour pass for that one job propose a layout and watch it land in 3D/);
  assert.match(slideText(live, DOOR), /address to be confirmed/);
  for (const s of slidesOf(live)) assert.match(s.text, /REVIEW · door variant, not the export/, s.id);
  assert.throws(() => finalPdfName(live), /demo review render never exports a PDF/);
  // RECORDED: no instruction and no QR code; with no real recorded runs, the plain empty state and the 3D still.
  const rec = recorded();
  assert.equal(rec.deck.demoStatus, "recorded");
  assert.doesNotMatch(html(rec), /dcta-url|data-qr|Tell your/);
  assert.match(slideText(rec, DOOR), /No recorded runs yet/);
  assert.equal(rec.slides.find((s) => s.id === DOOR).content.still.id, "render");
  assert.ok(slideText(rec, DOOR).includes(D.statuses.recorded.text));
  assert.doesNotMatch(`${slideText(rec, DOOR)} ${notesOf(rec, DOOR)}`, /sample arrival|synthetic|preview/i, "only real activity");
  // A real recorded run shows with its date, and needs its room record before the cutoff.
  const withRun = recorded({}, (f) => { f.plainTalk.slides[9].runs = [{ at: "2026-11-01T01:00:00Z", text: "A layout scored", records: [{ room: "608657e4", ref: "seq 57400", author: "pocket-forge", at: "2026-11-01T01:00:00Z" }] }]; });
  assert.match(slideText(withRun, DOOR), /2026-11-01 01:00 UTC A layout scored/);
  assert.throws(() => recorded({}, (f) => { f.plainTalk.slides[9].runs = [{ at: "2026-11-02T01:00:00Z", text: "x", records: [{ room: "608657e4", ref: "seq 57400", author: "x", at: "2026-11-02T01:00:00Z" }] }]; }), /after the cutoff/);
  // The status flag: live and recorded only; live refused while the address is a placeholder.
  assert.throws(() => recorded({ demoStatus: "live" }), /cannot say live while the agent door's address is still a placeholder/);
  for (const st of ["staging", "replay"]) assert.throws(() => recorded({ demoStatus: st }), /LIVE and RECORDED only/);
  assert.throws(() => build({ demoStatus: "tonight" }), /--demo-status must be one of/);
});
test("the QR code is the reviewed image of exactly https://sentilab.aidenid.com", () => {
  const Q = loaded.final.stills.qr;
  assert.deepEqual([Q.file, Q.sha256, Q.width, Q.height], ["qr-sentilab.png", "f62a077ae0010d876fe7674d3c134f0cbac994f95827ef8c286911c40fc744ec", 592, 592]);
  const q = liveReview().slides.find((s) => s.id === DOOR).content.qr;
  assert.deepEqual([q.id, q.payload, q.alt], ["qr", "https://sentilab.aidenid.com", "QR code for https://sentilab.aidenid.com"]);
  // Only black and white modules: nothing else is drawn into it.
  const px = decodePng(readFileSync(join(FIGURE_SOURCE_DIR, Q.file)));
  const seen = new Set();
  for (let i = 0; i < px.px.length; i += px.bpp) seen.add(`${px.px[i]},${px.px[i + 1]},${px.px[i + 2]}`);
  assert.deepEqual([...seen].sort(), ["0,0,0", "255,255,255"]);
});
test("no K, formula, grid or \"statistic\" on a main slide, in its notes or in its picture, and a technical word there stops the build", () => {
  for (const d of [recorded(), liveReview(), short()]) for (const s of d.slides.filter((x) => x.main)) {
    const text = [slideText(d, s.id), s.notes.text, figureText(d, s.id), s.content.figure?.alt ?? "", s.content.still?.alt ?? ""].join("\n");
    for (const re of PLAIN_TALK_BANNED) assert.doesNotMatch(text, re, `${s.id}: ${re}`);
    assert.doesNotMatch(text, /kelvin|\brz\b|\bgrid\b|statistic|\d\s?K\b/i, s.id);
  }
  const refuse = (mutate) => assert.throws(() => recorded({}, mutate), /the plain talk keeps technical detail in backup/);
  refuse((f) => { f.plainTalk.slides[5].say["3+2"] += " The gap is 142 K."; });
  refuse((f) => { f.plainTalk.slides[5].caption += " Grid 64."; });
  refuse((f) => { f.plainTalk.slides[5].picture.figure = "fig1"; });
  refuse((f) => { f.plainTalk.slides[6].title = "The frozen gate statistic passed."; });
});
// Root kept the 3D view's door temperatures "unvalidated" for this event (team room, reply to 57608, 03:40:48); the
// answer pages carry aneta's corrected sheet (team room 57700), with the coordinator's "unvalidated" answer added.
test("the answer pages carry aneta's sheet, brackets filled only where the facts exist, and every 3D still says simulated", () => {
  const d = recorded();
  const pages = d.slides.filter((s) => /^qa(-\d+)?$/.test(s.id));
  assert.ok(pages.length >= 2);
  assert.equal(d.slides.at(-1).id, pages.at(-1).id, "last, where the End key goes");
  const all = pages.map((p) => slideText(d, p.id)).join("\n");
  const QA = loaded.final.backup.qa;
  for (const x of QA.items) assert.ok(all.includes(`${x.q} ${x.a}`), x.q);
  assert.equal(QA.items.length, 25);
  assert.match(slideText(d, "qa"), /An AI agent is only as good as the grader it optimizes against\./);
  // Brackets: our own run of the change, the 25-layout test and the note to the authors haven't happened.
  assert.ok(all.includes("Did you run that change yourselves? Not yet. It's reported by those two teams."));
  assert.ok(all.includes("Does it change which design wins? We haven't measured that yet."));
  assert.ok(all.includes("Have you told the authors? A note is drafted. Sending it is still pending."));
  // The sheet's records are dated before the cutoff, like every other dated line.
  assert.throws(() => recorded({}, (f) => { f.backup.qa.records[0].at = "2026-11-02T00:00:00Z"; }), /after the cutoff/);
  assert.doesNotMatch(all, /\[|Fill/);
  assert.ok(all.includes("Why does it say unvalidated? That tag is about approving the simulator setup in general. This saved simulation reproduced the paper's reference result within the 1-degree bar we set in advance. It's simulated, not silicon."));
  // "bug" appears only as the question and as Delfie's attributed word; money only in the cost answer.
  assert.deepEqual(all.match(/[^.?]*\bbug\b[^.?]*[.?]/g).map((x) => x.trim()), ["So it's a bug?", "Delfie's report calls it a likely bug; those are their words."]);
  assert.deepEqual(all.match(/\$[\d,]+/g), ["$6,400"]);
  // The reading notes are the presenter's: in SCRIPT.md, never on a slide.
  assert.doesNotMatch(everything(d), /Please don't say|Learn the first line/);
  // Every slide that shows the 3D view says simulated, not silicon.
  for (const v of [d, liveReview()]) {
    for (const m of Deck.renderSlides(v).matchAll(/<section class="slide (?:main|backup)" id="s-([\w-]+)"[^>]*>([\s\S]*?)<\/section>/g)) {
      if (/data-still="(?:render|view3d)"/.test(m[2])) assert.match(visible(m[2]), /simulated, not silicon/i, `${m[1]}: the still is labelled`);
    }
  }
});
// The package render on slides 2 and 10 is cut from our 3D view's screenshot (PR78 build 35323889); the full screenshot,
// with its labels, its "unvalidated" tags and its notice, is the backup still. The crop is exactly its box of that
// screenshot: no pixel was edited.
const decodePng = (buf) => {
  let off = 8, w, h, type;
  const idat = [];
  while (off < buf.length) {
    const len = buf.readUInt32BE(off), kind = buf.toString("latin1", off + 4, off + 8), data = buf.subarray(off + 8, off + 8 + len);
    if (kind === "IHDR") {
      [w, h, type] = [data.readUInt32BE(0), data.readUInt32BE(4), data[9]];
      assert.deepEqual([data[8], data[12]], [8, 0], "8-bit, not interlaced");
    } else if (kind === "IDAT") idat.push(data);
    off += 12 + len;
  }
  const bpp = { 0: 1, 2: 3, 6: 4 }[type];
  assert.ok(bpp, `PNG colour type ${type}`);
  const raw = inflateSync(Buffer.concat(idat)), stride = w * bpp, px = Buffer.alloc(h * stride);
  for (let y = 0; y < h; y++) {
    const filter = raw[y * (stride + 1)], line = y * (stride + 1) + 1, row = y * stride;
    for (let x = 0; x < stride; x++) {
      const a = x >= bpp ? px[row + x - bpp] : 0, b = y ? px[row - stride + x] : 0, c = y && x >= bpp ? px[row - stride + x - bpp] : 0;
      const p = a + b - c, pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c);
      px[row + x] = (raw[line + x] + [0, a, b, (a + b) >> 1, pa <= pb && pa <= pc ? a : pb <= pc ? b : c][filter]) & 255;
    }
  }
  return { w, h, bpp, px };
};
test("slides 2 and 10 show the package render cut from our 3D view, pixel for pixel; the full screenshot is the backup still", () => {
  const S = loaded.final.stills;
  assert.deepEqual([S.view3d.file, S.view3d.sha256], ["package-view-35323889.png", "c5356137e7b6c2b9592f1288dff95e0f37471df810c92f3267c7e411118c1bd8"]);
  assert.deepEqual([S.render.file, S.render.sha256, S.render.crop], ["package-render-35323889.png",
    "7ea5c23232c4f3d3cedb54fd6704e9879d622c660dc515b16310c0fa4dde560a", { from: "view3d", box: [540, 280, 1225, 781] }]);
  const full = decodePng(readFileSync(join(FIGURE_SOURCE_DIR, S.view3d.file)));
  const crop = decodePng(readFileSync(join(FIGURE_SOURCE_DIR, S.render.file)));
  const [x0, y0, x1, y1] = S.render.crop.box;
  assert.deepEqual([crop.w, crop.h, crop.bpp], [x1 - x0, y1 - y0, full.bpp]);
  for (let y = 0; y < crop.h; y++) {
    const want = full.px.subarray(((y0 + y) * full.w + x0) * full.bpp, ((y0 + y) * full.w + x1) * full.bpp);
    assert.ok(crop.px.subarray(y * crop.w * crop.bpp, (y + 1) * crop.w * crop.bpp).equals(want), `crop row ${y} is the screenshot's row ${y0 + y}`);
  }
  const d = recorded();
  assert.deepEqual(["t-grader", DOOR].map((id) => d.slides.find((s) => s.id === id).content.still.id), ["render", "render"]);
  assert.deepEqual(["demo", "view3d"].map((id) => d.slides.find((s) => s.id === id).content.still.id), ["view3d", "view3d"]);
  assert.match(slideText(d, "view3d"), /Its temperatures carry the view's own unvalidated tag\./);
  assert.throws(() => recorded({}, (f) => { f.stills.render.crop.box = [540, 280, 1226, 781]; }), /is not a 685x501 region of view3d/);
  assert.throws(() => recorded({}, (f) => { f.stills.render.crop.from = "render"; }), /not an uncropped still/);
  assert.throws(() => recorded({}, (f) => { f.stills.render.sha256 = "0".repeat(64); }), /still render .* is not the reviewed file/);
});
test("every slide of the earlier five-minute deck is in backup, its content and notes unchanged", () => {
  for (const options of [{}, { demoStatus: "live", demoReview: true }]) {
    const d = recorded(options);
    const old = recorded({ demoStatus: "recorded", ...options }, (f) => { delete f.plainTalk; });
    const oldBackup = old.slides.filter((s) => !/^qa(-\d+)?$/.test(s.id));
    assert.deepEqual(oldBackup.map((s) => s.id), OLD_DECK);
    for (const s of oldBackup) {
      const b = d.slides.find((x) => x.id === s.id);
      assert.equal(b.main, false, s.id);
      assert.deepEqual(b.content, s.content, s.id);
      assert.equal(b.notes.text, s.notes.text, s.id);
    }
  }
});

// ── 8. the local workstation ────────────────────────────────────────────────────────────────────────────────────────
// Wall times as measured and independently checked (team room, message 57413, 00:19:45Z on 1 Nov).
test("the workstation backup gives the measured wall times, dated, with no hardware model name and the 20 of 20 caveat", () => {
  const d = recorded();
  const b = slideText(d, "gb10");
  assert.match(b, /Train a small adapter 67\.271 s Evaluate it in a fresh container 61\.156 s Serve it locally 185\.763 s/);
  assert.match(b, /Runs on 31 October, 07:48 to 11:40 UTC\./);
  assert.ok(loaded.final.backup.gb10.records.some((r) => r.ref === "seq 57413" && r.at === "2026-11-01T00:19:45.881Z"));
  assert.match(b, /Our local workstation: what ran on 31 October, and for how long\./);
  assert.match(b, /0 of 20 to 20 of 20: 20 rows from 6 distinct source cases, all seen in training\./);
  assert.doesNotMatch(everything(d), /\bGB10\b/i);
  assert.throws(() => recorded({}, (f) => { f.backup.gb10.title = "The NVIDIA box."; }), /public-render rule/);
  assert.throws(() => recorded({}, (f) => { f.backup.gb10.title = "The GB10 box."; }), /not allowed/);
  assert.throws(() => recorded({}, (f) => { f.checks.caption += " The approver gave a +1."; }), /not allowed/);
});

// ── 9. timing ───────────────────────────────────────────────────────────────────────────────────────────────────────
test("word count: whitespace tokens holding a letter or digit, timed at 150 words a minute and at 2.2 a second", () => {
  assert.equal(countWords("A closed-form heat test, 48 files · one command."), 8);
  assert.equal(countWords("  ·  —  "), 0);
  assert.deepEqual(speech("one two three four five six seven eight nine ten eleven", { checkWordsPerMinute: 150, slowWordsPerSecond: 2.2 }),
    { text: "one two three four five six seven eight nine ten eleven", words: 11, seconds: 4.4, slowSeconds: 5 });
});
test("each slot's talk fits its cap with its transitions at 150 words a minute, and its door lines fit its demo clock", () => {
  const t = loaded.final.talk;
  // 2.25 words a second is the relaxed 135 words a minute the coordinator asked to see beside 150.
  assert.deepEqual([t.checkWordsPerMinute, t.slowWordsPerSecond, t.talkCapSeconds, t.transitionSeconds, t.demoSeconds, t.maxSeconds], [150, 2.25, 180, 15, 120, 300]);
  const confirmed = (f) => { f.demo.urlIsPlaceholder = false; };
  const builds = {
    recorded: () => recorded(), operator: () => build(),
    live: () => recorded({ demoStatus: "live" }, confirmed), "live-review": () => recorded({ demoStatus: "live", demoReview: true }),
    short: () => recorded({ slot: "3total" }), "short-live": () => recorded({ slot: "3total", demoStatus: "live", demoReview: true }),
    "pass-preview": () => build({ gate: "pass", preview: true }), "fail-preview": () => build({ gate: "fail", preview: true }),
    ...Object.fromEntries(GATES.map((g) => [g, () => variant(g)])),
  };
  for (const [g, make] of Object.entries(builds)) {
    const d = make();
    assert.deepEqual(d.slides.filter((s) => s.main).map((s) => s.id), d.build.slot === "3total" ? MAIN.filter((id) => !["t-team", "t-open"].includes(id)) : MAIN, g);
    for (const s of d.slides) {
      assert.equal(s.notes.words, countWords(s.notes.text), `${g} ${s.id} words`);
      assert.equal(s.notes.seconds, Math.round((s.notes.words / 2.5) * 10) / 10, `${g} ${s.id} seconds at 150 wpm`);
      assert.equal(s.notes.slowSeconds, Math.round((s.notes.words / 2.25) * 10) / 10, `${g} ${s.id} seconds at 135 wpm`);
    }
    // Only the main slides before the door are timed against the talk cap; backup notes are not spoken.
    const u = d.budget;
    const talkWords = d.slides.filter((s) => s.main && s.id !== DOOR).reduce((n, s) => n + s.notes.words, 0);
    assert.equal(u.talkWords, talkWords, g);
    assert.equal(u.doorWords, d.slides.find((s) => s.id === DOOR).notes.words, g);
    assert.ok(u.talkSeconds + u.transitionSeconds <= u.talkCapSeconds, `${g}: talk ${u.talkSeconds} s + ${u.transitionSeconds} s`);
    assert.ok(u.doorSeconds <= u.demoSeconds && u.liveSeconds > 0, `${g}: door ${u.doorSeconds} s`);
    assert.ok(u.talkCapSeconds + u.demoSeconds <= u.maxSeconds);
  }
  // The coordinator's figures for script v3.1: 364 words, 161 s at 150 wpm and 177 s at 135 with transitions; the door
  // 79 words LIVE and 32 RECORDED. The short cut: 211 words in a 120 s talk cap and a 60 s demo.
  const u = recorded().budget;
  assert.deepEqual([u.talkWords, u.talkSeconds, u.talkSlowSeconds, u.doorWords, u.doorSeconds, u.liveSeconds], [364, 145.6, 161.8, 32, 12.8, 107.2]);
  assert.deepEqual([u.talkSeconds + u.transitionSeconds, u.talkSlowSeconds + u.transitionSeconds], [160.6, 176.8]);
  assert.equal(recorded({ demoStatus: "live", demoReview: true }).budget.doorWords, 79);
  const v = recorded({ slot: "3total" }).budget;
  assert.deepEqual([v.talkWords, v.talkSeconds, v.talkCapSeconds, v.doorWords, v.demoSeconds], [211, 84.4, 120, 30, 60]);
  assert.equal(recorded({ slot: "3total", demoStatus: "live", demoReview: true }).budget.doorWords, 49);
});
test("a talk over its cap, door lines longer than the demo clock, or a cap and demo over the slot stop the build", () => {
  assert.throws(() => recorded({}, (f) => { f.plainTalk.slides[3].say["3+2"] += " and then".repeat(30); }), /over the 180 s cap/);
  assert.throws(() => recorded({ slot: "3total" }, (f) => { f.plainTalk.slides[3].say["3total"] += " and then".repeat(30); }), /over the 120 s cap/);
  assert.throws(() => recorded({ slot: "3total", demoStatus: "live", demoReview: true }, (f) => { f.plainTalk.slides[9].say["3total"].live += " and then".repeat(80); }), /more than the 60 s demo clock/);
  assert.doesNotThrow(() => recorded({}, (f) => { f.timeline.notes += " and then".repeat(30); }), "backup notes are not timed");
  assert.throws(() => recorded({}, (f) => { f.plainTalk.slots["3+2"].transitionSeconds = 40; }), /over the 180 s cap/);
  assert.throws(() => recorded({}, (f) => { f.plainTalk.slots["3+2"].demoSeconds = 10; }), /more than the 10 s demo clock/);
  assert.throws(() => recorded({}, (f) => { f.plainTalk.slots["3+2"].demoSeconds = 121; }), /exceed the slot/);
});

// ── 10. records behind every dated line ─────────────────────────────────────────────────────────────────────────────
test("every chronology row, tile and how-it-works example names a room record that carries its minute", () => {
  const f = loaded.final;
  for (const item of f.backup.chronology.rows) {
    const minutes = item.records.flatMap((r) => [r.at, r.stated].filter(Boolean)).map((t) => t.slice(0, 16));
    assert.ok(minutes.includes(item.at.slice(0, 16)), `${item.at} ${item.text}`);
    for (const r of item.records) assert.ok(["608657e4", "32a841e5"].includes(r.room));
  }
  for (const s of f.how.steps) assert.ok(s.records.length >= 1, s.title);
  for (const part of [f.demo, f.backup.receipt, f.backup.gb10, f.backup.reviews, f.how.evidence, f.problem, f.stack, f.checks.study, f.figures.fig6]) assert.ok(part.records.length >= 1);
  assert.deepEqual(recorded().slides.find((s) => s.id === "chronology").content.rows.map((r) => r.at).slice(-4), ["22:22", "23:01", "23:44", "00:03"]);
  assert.throws(() => recorded({}, (x) => { x.backup.chronology.rows[0].at = "2026-10-31T12:44:00.000Z"; }), /which no record carries/);
  assert.throws(() => recorded({}, (x) => { x.backup.prs.items[0].checkedAt = "2026-11-02T00:00:00Z"; }), /checked after the cutoff/);
  assert.throws(() => recorded({}, (x) => { x.demo.records[0].at = "2026-11-02T00:00:00.000Z"; }), /after the cutoff/);
  assert.throws(() => recorded({}, (x) => { x.checks.study.records = []; }), /has no room record/);
});

// ── 11. public rules, this deck's bans, plain words ─────────────────────────────────────────────────────────────────
test("every rendered word, figure text included, passes the public-render rules and this deck's bans", () => {
  const builds = [...GATES.map((g) => variant(g)), recorded(), recorded({ slot: "3total" }), recorded({ demoStatus: "live", demoReview: true })];
  for (const d of builds) {
    const notes = new Map(d.slides.map((s) => [s.id, s.notes.text]));
    for (const s of slidesOf(d)) {
      const money = moneyAllowed(d.slides.find((x) => x.id === s.id));
      for (const text of [s.text, notes.get(s.id), figureText(d, s.id)]) {
        // The talk's spoken words name the co-lead; the slides do not.
        const checked = text === notes.get(s.id) ? text.replace(/\bAneta\b/g, "the co-lead") : text;
        for (const re of NOT_PUBLIC) assert.doesNotMatch(checked, re, `${d.deck.variant} ${s.id}`);
        const qaPage = /^qa(-\d+)?$/.test(s.id);
        for (const re of FINAL_BANNED) if (!(MONEY.has(re) && money) && !(qaPage && re === FINAL_BANNED[5])) assert.doesNotMatch(text, re, `${d.deck.variant} ${s.id}`);
        if (s.main) for (const re of PLAIN_WORDS) assert.doesNotMatch(text, re, `${d.deck.variant} ${s.id} (plain words)`);
      }
    }
  }
  // Money only on the backup numbers slide and the answer pages.
  const d = recorded();
  assert.deepEqual(d.slides.filter(moneyAllowed).map((s) => s.id), ["numbers", ...d.slides.map((s) => s.id).filter((id) => /^qa(-\d+)?$/.test(id))]);
  assert.match(slideText(d, "numbers"), /\$6,376\.21/);
  for (const s of slidesOf(d)) if (!moneyAllowed(d.slides.find((x) => x.id === s.id))) assert.doesNotMatch(`${s.text}\n${notesOf(d, s.id)}`, /\$|USD|dollar/i, s.id);
});
test("banned text in the source stops the build", () => {
  const banned = [
    [(f) => { f.backup.receipt.notYet += " Cost so far $255.79."; }, /not allowed/],
    [(f) => { f.problem.caption += " It cost 40 dollars."; }, /not allowed/],
    [(f) => { f.backup.status.cards[0].text += " Deck due 2026-11-01 18:00 UTC."; }, /not allowed/],
    [(f) => { f.backup.status.cards[0].text = "source unknown"; }, /not allowed/],
    [(f) => { f.stack.caption = "It is a bug."; }, /not allowed/],
    [(f) => { f.plainTalk.slides[5].caption = "See PR 56 for the code."; }, /plain words/],
    [(f) => { f.plainTalk.slides[9].say["3+2"].recorded += " The CLI works too."; }, /plain words/],
    [(f) => { f.plainTalk.slides[7].say["3+2"] += " It cost 40 dollars."; }, /not allowed/],
    [(f) => { f.plainTalk.slides[1].punch = "A bug in the grader."; }, /not allowed/],
    [(f) => { f.how.footnote += " The warden reviews it."; }, /public-render rule/],
    [(f) => { f.teamsSlide.caption = "Checked by Aneta."; }, /would rewrite/],
  ];
  for (const [mutate, re] of banned) assert.throws(() => recorded({}, mutate), re);
});
test("the review's fixes hold: PR states, the peer model at v2, origin times, no deadline", () => {
  const d = recorded();
  const all = slidesOf(d).map((s) => s.text).join("\n");
  const prs = slideText(d, "prs");
  assert.match(prs, /#57 Reference layouts from the paper, plus the paper's wire router merged as d298cb00 at 2026-10-31 18:04 UTC/);
  const pr56 = loaded.final.backup.prs.items.find((p) => p.number === 56);
  assert.ok(prs.includes(pr56.state === "MERGED" ? `merged as ${pr56.merge.slice(0, 8)}` : `open at head ${pr56.head.slice(0, 8)}`));
  assert.match(slideText(d, "metrics"), /informed peer/i);
  assert.doesNotMatch(all, /\bindependent model\b/i);
  assert.match(slideText(d, "status"), /origin time not recorded/);
  assert.match(slideText(d, "status"), /0 of 8 deliverables fully accepted/);
  assert.doesNotMatch(all, /source unknown|deck due/i);
});

// ── 12. the command line ────────────────────────────────────────────────────────────────────────────────────────────
test("a pull-request refresh needs an explicit cutoff, and never moves the source's own", () => {
  assert.throws(() => cliOptions(["--refresh-prs"]), /--refresh-prs needs an explicit --cutoff/);
  assert.equal(cliOptions(["--refresh-prs", "--cutoff", "2026-11-01T02:00:00Z"]).refresh, true);
  assert.throws(() => cliOptions(["--demo-status"]), /--demo-status needs a value/);
  assert.deepEqual(cliOptions(["--rederived", "--demo-status", "replay"]).build,
    { gate: undefined, measured: null, cutoff: null, preview: false, rederived: true, demoStatus: "replay", demoReview: false, slot: undefined });
  assert.equal(cliOptions(["--slot", "3total"]).build.slot, "3total");
  assert.equal(cliOptions(["--demo-status", "live", "--demo-review"]).build.demoReview, true);
  assert.doesNotMatch(String(refreshPrs), /cutoff/, "a refresh stamps the rows it read and nothing else");
  // The real command stops before it reads or writes anything (no gh on the PATH, so a regression cannot reach the network).
  const before = sha(readFileSync(FINAL_SOURCE));
  const env = Object.fromEntries(Object.entries(process.env).filter(([k]) => k.toUpperCase() !== "PATH"));
  const r = spawnSync(process.execPath, [join(REPO_ROOT, "scripts", "build-deck-final.mjs"), "--refresh-prs"], { env: { ...env, PATH: "" }, encoding: "utf8" });
  assert.equal(r.status, 1);
  assert.match(r.stderr, /needs an explicit --cutoff/);
  assert.equal(sha(readFileSync(FINAL_SOURCE)), before, "FINAL.json is untouched");
});

// ── 13. exports ─────────────────────────────────────────────────────────────────────────────────────────────────────
test("the PDF is named from the cutoff and the outcome, sits beside its source, and has one page per slide", () => {
  const c = committed.build.cutoff;
  assert.equal(finalPdfName(committed), `final-5min/SentiLab-5min-${c.slice(0, 10)}-${c.slice(11, 13)}${c.slice(14, 16)}-${committed.build.gate}.pdf`);
  const pdf = join(PDF_DIR, finalPdfName(committed));
  assert.ok(existsSync(pdf), `${finalPdfName(committed)} is exported`);
  const pages = (readFileSync(pdf, "latin1").match(/\/Type\s*\/Page(?![s\w])/g) ?? []).length;
  assert.equal(pages, committed.slides.length, "one PDF page per slide");
  assert.deepEqual(readdirSync(FINAL_DIR).sort(),
    [finalPdfName(committed).split("/")[1], "FINAL.json", "FINAL.schema.json", "PLAIN-SCRIPT-SHORT.md", "PLAIN-SCRIPT.md", "RE-EXPORT.md", "SCRIPT.md", "TIMELINE-VERIFY.md", "figures", "quant", "variants"].sort());
  const exporter = read(join(REPO_ROOT, "scripts", "export-deck-pdf.mjs"));
  assert.match(exporter, /final: \{ dir: FINAL_DECK_DIR, pdf: \(data\) => finalPdfName\(data\), mainMinFont: 28 \}/);
  assert.match(exporter, /const FROZEN = \{ \.\.\.FROZEN_V1, \.\.\.FROZEN_DAYTIME \};/);
  assert.match(exporter, /querySelectorAll\("img\[data-fig\]"\)/, "the exporter holds figure text to the type floor");
});
// The speaker script exported with the PDF (aneta, 57554; the coordinator's layout): every main slide's exact words,
// counts and seconds at 150 words a minute, the door's status lines, the clock, and short enough for one room message.
test("SCRIPT.md is the export's speaker script, word for word, under 16,000 characters", () => {
  const script = read(SCRIPT_PATH);
  assert.equal(script, speakerScript(buildFinalData(loaded, committed.build), loaded.final));
  assert.ok(script.length < 16000, `${script.length} characters`);
  assert.match(script, /^# Speaker script, five-minute deck \(slot 3\+2\), review export /);
  assert.match(script, /the main slides from script v3\.1 in PLAIN-SCRIPT\.md; the backup slides are not spoken\./);
  // The version is the script file's own heading: the short cut's script says it speaks v3.1-short.
  assert.match(speakerScript(short(), loaded.final), /^# Speaker script, three-minute deck \(slot 3total\), review export /);
  assert.match(speakerScript(short(), loaded.final), /the main slides from script v3\.1-short in PLAIN-SCRIPT-SHORT\.md; the backup slides are not spoken\./);
  assert.match(script, /The pass test is the recorded PASS \(75\.48 and 115\.93\), with the completed re-derivation\./);
  // One section per main slide, its script heading and its words; no backup slide is in the script.
  assert.deepEqual([...script.matchAll(/^## (\d+)\. /gm)].map((m) => Number(m[1])), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  for (const s of committed.slides.filter((x) => x.main && x.content.layout !== "door")) {
    const heading = loaded.final.plainTalk.slides.find((x) => x.id === s.id).heading;
    assert.ok(script.includes(`## ${s.label.split(" ")[0]}. ${heading}`), `${s.id}: heading`);
    assert.ok(script.includes(`${s.notes.text}\n\n${s.notes.words} words, ${s.notes.seconds} s at 150 wpm.`), s.id);
  }
  // The door's two scripted lines, and the answer sheet's reading notes, for the presenter only.
  const door = loaded.final.plainTalk.slides.find((x) => x.door);
  for (const st of ["live", "recorded"]) assert.ok(script.includes(`Say (${st.toUpperCase()}): ${door.say["3+2"][st]}\n\n${countWords(door.say["3+2"][st])} words,`), st);
  assert.match(script, /## For questions \(not shown on a slide\)\n\nLearn the first line and the last row/);
  assert.match(script, /- "bug" as your own word/);
  const u = committed.budget;
  assert.ok(script.includes(`Talk before the door: ${u.talkWords} words = ${u.talkSeconds} s at 150 wpm, plus 15 s of transitions = ${u.talkSeconds + u.transitionSeconds} s of the 180 s cap. At 135 words a minute it would take ${u.talkSlowSeconds} s, plus transitions ${Math.round((u.talkSlowSeconds + u.transitionSeconds) * 10) / 10} s.`));
  for (const name of TEAM_NAMES.filter((n) => !CONSENTED.includes(n))) assert.ok(!named(script, name), name);
  assert.match(script, /Named with consent: Delfie \(delphisci team\), help room message 57644; ScienceClaw, help room message 57532\./);
});
// Renders beside the export: the backup gate slide in all three outcomes, and the door in both stage variants.
test("the gate slide is rendered for all three outcomes and the door for LIVE and RECORDED, at 1920x1080", () => {
  const names = [...GATES.map((g) => `gate-${g}-1920x1080.png`), "slide10-live-1920x1080.png", "slide10-recorded-1920x1080.png"];
  assert.deepEqual(readdirSync(join(FINAL_DIR, "variants")).sort(), [...names].sort());
  for (const n of names) {
    const png = readFileSync(join(FINAL_DIR, "variants", n));
    assert.equal(png.subarray(1, 4).toString("latin1"), "PNG", n);
    assert.deepEqual([png.readUInt32BE(16), png.readUInt32BE(20)], [1920, 1080], n);
  }
});
