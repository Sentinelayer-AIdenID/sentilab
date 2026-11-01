// node --test scripts/deck-founder.test.mjs   (CI runs it through scripts/deck-data.test.mjs)
// The founder pitch (v4): Carter's three-minute main talk, built from docs/sentilab/deck/founder-v4/V4.json.
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";
import {
  FOUNDER_DECK_DIR, FOUNDER_DIR, FOUNDER_OUTPUTS, FounderError, buildFounderData, countWords, fillInTable, founderPdfName,
  loadFounder, outputsMatch, scriptPath, serialize, speakerScript,
} from "./build-deck-founder.mjs";
import { PDF_DIR, REPO_ROOT } from "./build-deck-data.mjs";

const require = createRequire(import.meta.url);
const deck = require(join(FOUNDER_DECK_DIR, "deck.js"));
const loaded = loadFounder();
const data = buildFounderData(loaded);
const committed = JSON.parse(readFileSync(join(FOUNDER_DECK_DIR, "deck-data.json"), "utf8"));
// A build of a changed copy of the source, for the refusal tests.
const variant = (mutate, metrics = loaded.metrics) => {
  const v4 = structuredClone(loaded.v4);
  mutate(v4);
  return buildFounderData({ ...loaded, v4, metrics });
};
const slide = (d, id) => d.slides.find((s) => s.id === id);
const html = (d) => deck.renderSlides(d);
// The visible text of one rendered slide, tags dropped and entities decoded.
const shown = (d, id) => {
  const m = new RegExp(`<section class="slide [^"]*" id="s-${id}"[\\s\\S]*?</section>`).exec(html(d));
  return m[0].replace(/<[^>]+>/g, " ").replace(/&#39;/g, "'").replace(/&quot;/g, '"').replace(/&amp;/g, "&").replace(/\s+/g, " ");
};
const MAIN = ["chips", "senti", "room", "hook", "times", "link", "scorecard", "point", "invite", "closer"];
const SHORT = ["chips", "room", "hook", "scorecard", "invite", "closer"];

test("the founder deck is built from V4.json, and the committed deck, script, fill-in and sources match a fresh build", () => {
  assert.equal(serialize(data).json, readFileSync(join(FOUNDER_DECK_DIR, "deck-data.json"), "utf8"));
  assert.ok(outputsMatch(data, loaded.v4, loaded), "deck/founder-v4 and SCRIPT/SCRIPT-2min/FILL-IN/SOURCES are the build's");
  assert.deepEqual(data.slides.filter((s) => s.main).map((s) => s.id), MAIN);
  assert.deepEqual(data.slides.filter((s) => !s.main).map((s) => s.id), ["sources", "cost", "solvers"]);
  assert.match(html(data), /<section class="slide main" id="s-chips"/);
});

test("the talk fits three minutes at 150 words a minute, transitions included; more words stop the build", () => {
  const u = data.budget;
  assert.equal(u.talkWords, data.slides.filter((s) => s.main).reduce((a, s) => a + s.notes.words, 0));
  assert.ok(u.totalSeconds <= 200, `${u.totalSeconds} s`); // 3:00 to 3:20, Carter's slot (57411): 3-4 minutes of talk, then the demo
  assert.deepEqual([u.talkWords, u.talkSeconds, u.transitionSeconds, u.totalSeconds], [379, 151.6, 15, 166.6]);
  assert.throws(() => variant((v) => { v.slides[0].say += " and then".repeat(50); }), (e) => e instanceof FounderError && /over the 200 s cap/.test(e.message));
  // A placeholder is one word, read or not, so filling it in does not move the clock.
  assert.equal(slide(data, "invite").notes.words, countWords("We're inviting agents on Moltbook: N votes, N visits, N passed."));
  // v4-short: two minutes of talk, transitions included, then the demo.
  const short = buildFounderData(loaded, { slot: "2min" });
  assert.deepEqual(short.slides.filter((x) => x.main).map((x) => x.id), SHORT);
  assert.deepEqual([short.budget.talkWords, short.budget.talkSeconds, short.budget.transitionSeconds, short.budget.totalSeconds], [244, 97.6, 10, 107.6]);
  // The cut slides lead the backup, then the backup pages.
  assert.deepEqual(short.slides.filter((x) => !x.main).map((x) => x.id), ["senti", "times", "link", "point", "sources", "cost", "solvers"]);
  assert.throws(() => buildFounderData(loaded, { slot: "4min" }), /--slot must be one of 3min, 2min/);
});

test("root's carried openings, the finding beat in root's words and Carter's additions are spoken word for word", () => {
  const say = (id) => slide(data, id).notes.text;
  // Root, reply to 57809 at 07:04Z: the two paragraph openings, as written.
  assert.ok(say("hook").startsWith("In detailed 3D mode, two versions of HotSpot gave roughly 119 and 241 degrees at the hottest modeled grid cells, for the same design and input files."));
  // Slide 7, the scorecard: aneta's first sentence (57906), root's preferred wording (reply to 57902, 08:04Z), then the beat.
  assert.equal(say("scorecard"), "Our fixed reference test with the older setup reproduced two published values within a hundredth of a degree. Our saved older-build result matched the paper but failed this heat-balance check. The modified output is reported within rounding and nearer the separate solvers; it still misses the paper. Source analysis found non-reciprocal lateral links consistent with that. I nodded.");
  assert.match(slide(data, "scorecard").notes.cue, /Pause before "I nodded\."/);
  assert.equal(slide(data, "scorecard").content.title, "Passing one check isn't passing them all.");
  // Aneta's shortening (57816), with the distinction kept in the footer.
  assert.ok(say("link").endsWith("Two other teams reported results from changing that link."));
  assert.match(slide(data, "link").content.footer, /^Delfie \(delphisci team\) and ScienceClaw reported results from changing that modeled link; those reports are separate from our verified reference reproduction\./);
  // Carter's additions (57800): the chip joke's second half, what the tech does for agents, the room, the closer.
  assert.ok(say("chips").endsWith("All I know is a chip package is a few small chips, chiplets, that get hot, and you can't put them too close together or too far apart. But I'll tell you what: my agents know chip design."));
  for (const w of ["recognizes agents", "sets them up", "collaborate", "serves what they need", "keeps a record of what they did.", "Delegation is scoped", "handled gracefully", "only gets what it's allowed to touch", "Shopping, security, and today, science."]) assert.ok(say("senti").includes(w), w);
  assert.doesNotMatch(say("senti") + shown(data, "senti"), /everywhere they went|where it went|3\.8 s|22,900/, "aneta's 57906 items 3 and 4");
  for (const w of ["outside agents worked beside ours in one room", "People watched every agent work", "agents geared each other up and guarded the room", "plain messages became tickets"]) assert.ok(say("room").includes(w), w);
  // Root (08:40Z): "most teams…" stays out of the narration, as Carter's marked option in the notes only.
  assert.doesNotMatch(say("room") + shown(data, "room"), /most teams/i);
  assert.match(slide(data, "room").notes.cue, /^Carter's option, not a verified fact .*"Most teams had never had their agents talk to another lab's agents\."/);
  // The participants line in aneta's wording (57906), with the metrics pass's numbers (root, 07:52Z).
  assert.ok(say("room").endsWith("422 messages from 28 identities: 5 human, 23 agent."));
  assert.match(shown(data, "room"), /11 in the help room, 9 in our team room/);
  assert.doesNotMatch(shown(data, "room") + say("room"), /\b17 people\b/);
  assert.match(shown(data, "room"), /8 outside agent posting groups, plus 3 human-only groups/);
  assert.doesNotMatch(shown(data, "room") + shown(data, "sources"), /at least 8|outside teams/, "posting groups are not teams (root, 08:40Z)");
  assert.match(shown(data, "room"), /rated helpful by our intent model \(model-rated, not confirmed\)/);
  assert.match(say("closer"), /^My ambition\? Make you wonder why your agents need Kiro, Jira, Slack, Facebook, and GitHub\. Okay, not GitHub\. Yet\./);
  assert.match(slide(data, "closer").notes.cue, /"Okay, not GitHub\. Yet\." is the quiet aside\. Naming the network out loud is Carter's call \(aneta recommends naming it\)/);
  assert.ok(say("closer").endsWith("I believe whoever owns the decision layer on that traffic will own key internet infrastructure for the next decade."));
  // The closer's slide text, exactly as the coordinator gave it.
  assert.equal(slide(data, "closer").content.text, "One of the largest internet networks reports over 10 billion AI-bot requests a week (April 2026), and AI-agent requests grew more than 1,700% in a year (Sept 2026).");
  assert.equal(slide(data, "closer").content.punch, "I believe whoever owns the decision layer on that traffic will own key internet infrastructure for the next decade.");
  // The scorecard is aneta's v1.19 plain7 (root's three repairs drawn in), with one declared edit and this deck's label.
  const fig = slide(data, "scorecard").content.figure;
  assert.equal(fig.id, "plain7");
  assert.equal(loaded.v4.figures.plain7.sha256, "6bc037d767d6cc8e9f65bc96bd49bb31fbc97280d2c79369a9a32fbd67840d36");
  const served = readFileSync(join(FOUNDER_DECK_DIR, "figures", "plain7-scorecard.svg"), "utf8");
  for (const t of ["Each column uses its own reading.", "Rounding limit: about 0.43 W, 0.063%; not a total error bound.", "Older: our pinned 6.0 build", "as ScienceClaw reports", "as Delfie reports; ScienceClaw reports too"]) assert.ok(served.includes(t), t);
  assert.ok(!served.includes("re-ran it"), "the participant-report boundary");
  assert.equal(fig.alt, loaded.v4.figures.plain7.alt);
  // Aneta's expanded description (57915): the selector, rounding and provenance qualifications, with the reported attribution.
  for (const t of ["The heat check's rounding limit is about 0.43 watts, 0.063 percent, and is not a total error bound.", "The paper column uses the native all-block reading, 232.67 degrees for 7.0.", "The solver column uses the hottest chiplet entry, 224.67 degrees for 7.0", "as Delfie reports and ScienceClaw reports too"]) assert.ok(fig.alt.includes(t), t);
  assert.ok(served.includes("aria-label=\"Three versions against three checks on the CPU-DRAM design. Older version, our pinned 6.0 build"));
  assert.ok(shown(data, "scorecard").includes("Delfie (delphisci team) reports the one-step change; ScienceClaw reports reproducing it"));
});

test("the slides name no vendor or product; the two citations appear on the sources page only", () => {
  const vendors = /cloudflare|\bjev\b|typesafe|ascend|\bkiro\b|\bjira\b|\bslack\b|facebook|github|claude|openai|\bgpt\b/i;
  for (const id of MAIN) assert.doesNotMatch(shown(data, id), vendors, id);
  const src = shown(data, "sources");
  assert.ok(src.includes("blog.cloudflare.com/rethinking-cache-ai-humans/") && src.includes("blog.cloudflare.com/agentic-web"), "both citations");
  // Science is labelled simulated wherever it is shown.
  for (const id of ["chips", "hook", "link", "scorecard"]) assert.match(shown(data, id), /simulated, not silicon|Simulated, not silicon/, id);
  // Outside teams: ScienceClaw, and Delfie only in the form the team asked for.
  for (const id of MAIN) assert.doesNotMatch(shown(data, id), /\bDelfie\b(?! \(delphisci team\))/, id);
});

test("claims the talk may not make, and numbers nothing declares, stop the build", () => {
  const refuses = (why, re, mutate) => assert.throws(() => variant(mutate), (e) => e instanceof FounderError && re.test(e.message), why);
  refuses("records", /records claim/, (v) => { v.slides[2].title = "All the records we are breaking."; });
  refuses("records, spoken", /records claim/, (v) => { v.slides[2].say += " Records broken."; });
  refuses("savings", /savings claim/, (v) => { v.slides[4].footer = "Hours saved for every engineer."; });
  refuses("40+ users", /40\+ users/, (v) => { v.slides[2].points.push("40+ users and their agents"); });
  refuses("the old snapshot", /300-post snapshot/, (v) => { v.slides[2].footer = "300 posts in one saved snapshot."; });
  refuses("a vendor on a slide", /public-render rule/, (v) => { v.slides[9].text = v.slides[9].text.replace("One of the largest internet networks", "Cloudflare"); });
  refuses("a product on a slide", /product name/, (v) => { v.slides[9].footer = "Kiro, Jira and Slack in one place."; });
  refuses("an unconsented team", /has not consented/, (v) => { v.slides[4].times[3].what = "for Kiln's finite-element solve of it"; });
  refuses("Delfie in another form", /form the team asked for/, (v) => { v.slides[4].times[2].what = "for Delfie to reproduce our public test case"; });
  refuses("science not labelled", /without saying "simulated"/, (v) => { v.slides[3].label = "two versions"; v.slides[3].footer = "Hottest modeled grid cells."; });
  refuses("an undeclared number", /which none of its facts declares/, (v) => { v.slides[2].tiles[0].value = "512"; });
  refuses("a duration its records don't give", /is not its records'/, (v) => { v.slides[4].times[0].show = "30 min"; });
  refuses("a bar not its value", /is not 119.07 rounded/, (v) => { v.slides[3].bars[0].show = "120 °C"; });
  refuses("17 people", /17 is member accounts/, (v) => { v.slides[2].say += " 17 people took part."; });
  refuses("a solver library named", /unresolved 115.93 against 115.94/, (v) => { v.slides[6].footer += " SuperLU explains it."; });
  refuses("money on a main slide", /money on a main slide/, (v) => { v.slides[2].footer += " It cost USD 8,232.41."; });
  refuses("a number that is not the metrics file's", /but METRICS.json gives 422/, (v) => { v.slides[2].tiles[0].value = "421"; v.slides[2].facts[0].shows = ["421"]; });
  refuses("a different metrics file", /is not the file V4.json pins/, (v) => { v.metrics.sha256 = "0".repeat(64); });
});

test("a number not measured yet shows \"measuring…\" and is listed to fill in; METRICS.json fills it", () => {
  const want = ["moltbook.post_votes", "door.visits", "door.agents_passed", "view.agent_bytes"];
  assert.deepEqual(data.placeholders.map((p) => p.id).sort(), [...want].sort());
  assert.equal((html(data).match(/class="measuring"/g) ?? []).length, 4, "four measuring tiles, all on the door slide");
  assert.equal(readFileSync(FOUNDER_OUTPUTS.fillIn, "utf8"), fillInTable(data));
  for (const id of want) assert.ok(readFileSync(FOUNDER_OUTPUTS.fillIn, "utf8").includes(`\`${id}\``), id);
  assert.match(slide(data, "invite").notes.text, /^We're inviting agents on Moltbook: \[votes on our Moltbook invitation: measuring\]/);
  assert.doesNotMatch(shown(data, "invite") + slide(data, "invite").notes.text, /\bWe invited\b|\bour (?:Moltbook )?post\b/, "no past tense about Moltbook before the post exists");
  assert.ok(data.deck.measuring && founderPdfName(data).endsWith("-draft.pdf"));
  // With the metrics on file, the tiles carry them and the words read them out.
  const keys = ["moltbook.post_votes", "door.visits", "door.agents_passed", "door.view_size"];
  const byId = new Map([...loaded.metrics.byId, ...keys.map((id, k) => [id, { id, value: 100 + k, display: String(100 + k), definition: "d", scope: "s", window: "w", source: "x" }])]);
  const filled = variant(() => {}, { sha256: loaded.metrics.sha256, byId });
  assert.equal(filled.placeholders.length, 0);
  assert.doesNotMatch(html(filled), /class="measuring"/);
  assert.match(slide(filled, "invite").notes.text, /^We're inviting agents on Moltbook: 100 votes, 101 visits, 102 passed\.$/);
  assert.ok(founderPdfName(filled).endsWith("-review.pdf"));
});

test("the founder PDFs are the exports, 3min and 2min: one page per slide, the only PDFs in their folder", () => {
  const short = buildFounderData(loaded, { slot: "2min" });
  const pdfs = readdirSync(FOUNDER_DIR).filter((f) => f.endsWith(".pdf")).sort();
  assert.deepEqual(pdfs, [founderPdfName(short), founderPdfName(committed)].map((p) => p.split("/")[1]).sort());
  for (const d of [committed, short]) {
    const pages = (readFileSync(join(PDF_DIR, founderPdfName(d)), "latin1").match(/\/Type\s*\/Page(?![s\w])/g) ?? []).length;
    assert.equal(pages, d.slides.length, d.deck.slot);
  }
  for (const f of ["sheet-main.png", "sheet-main-2min.png"]) assert.ok(existsSync(join(FOUNDER_DIR, f)), f);
  // Root's timing note: with the demo, and a real timed rehearsal before the talk.
  assert.match(readFileSync(scriptPath("3min"), "utf8"), /\*\*With the demo:\*\* 120 s of demo makes 286\.6 s \(4:47\) at 150 wpm, or 303\.4 s \(5:03\) at 135\. Before the talk, do one real timed rehearsal with the actual demo\./);
  assert.match(readFileSync(scriptPath("2min"), "utf8"), /60 s of demo makes 167\.6 s \(2:48\)/);
  assert.match(committed.slides[0].notes.cue, /one real timed rehearsal with the actual demo/);
  assert.equal(readFileSync(scriptPath("2min"), "utf8"), speakerScript(short, loaded.v4));
});

test("--final drops every number without a receipt, speaks the no-numbers line, and loses the DRAFT tag", () => {
  for (const slot of ["3min", "2min"]) {
    const fin = buildFounderData(loaded, { slot, final: true });
    assert.equal(fin.deck.draft, false);
    assert.equal(fin.deck.measuring, false);
    assert.doesNotMatch(html(fin), /measuring…|class="measuring"|DRAFT/, slot);
    assert.deepEqual(slide(fin, "invite").content.tiles, [], "slide 9's tiles have no receipt yet, so none is shown");
    assert.equal(slide(fin, "invite").notes.text, "We're inviting other people's agents to the chip challenge: scan the code and send yours.");
    assert.ok(founderPdfName(fin).endsWith("-final.pdf"));
    assert.ok(fin.budget.totalSeconds <= fin.budget.talkCapSeconds);
  }
  // The draft keeps the placeholders and the tag.
  assert.match(html(data), /DRAFT · numbers still measuring/);
  // A slide whose words need a missing number must say what to speak at the freeze instead.
  const noLine = structuredClone(loaded.v4);
  delete noLine.slides.find((x) => x.id === "invite").sayIfUnmeasured;
  assert.throws(() => buildFounderData({ ...loaded, v4: noLine }, { final: true }), /no sayIfUnmeasured line/);
});

test("founder deck files are LF-only, with no control bytes", () => {
  const paths = [
    ...["index.html", "deck.js", "deck.css", "deck-data.json", "deck-data.js"].map((f) => join(FOUNDER_DECK_DIR, f)),
    ...readdirSync(FOUNDER_DIR).filter((f) => /\.(json|md)$/.test(f)).map((f) => join(FOUNDER_DIR, f)),
    ...["build-deck-founder.mjs", "deck-founder.test.mjs", "sheet-deck-founder.mjs"].map((f) => join(REPO_ROOT, "scripts", f)),
  ];
  for (const f of paths) {
    const b = readFileSync(f);
    assert.ok(!b.includes(13), `${f} has a CR byte`);
    // eslint-disable-next-line no-control-regex
    assert.doesNotMatch(b.toString("utf8"), /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/, `${f} has a control byte`);
  }
});

test("cost and the other solvers are backup pages, each with its scope, never on a main slide", () => {
  const cost = shown(data, "cost");
  assert.match(cost, /whole subscription, not final: USD 8,232\.41/);
  assert.match(cost, /never added/);
  for (const id of MAIN) assert.doesNotMatch(shown(data, id), /\$\s?\d|\bUSD\b/, id);
  // Root's solvers line (07:52Z), as written, with what is compared and whose implementations they are.
  const solvers = shown(data, "solvers");
  assert.ok(solvers.includes("Two finite-element implementations and a separate finite-volume implementation report about 78 and 122 degrees for these two designs. Those numbers sit nearer the modified HotSpot 7 outputs than the HotSpot 6 outputs. The extraction methods differ, so this does not tell us which model is physically more accurate."));
  assert.match(solvers, /die-centre readings from those implementations against HotSpot's selector values/);
  assert.match(solvers, /one finite-element implementation is ours/);
  assert.match(solvers, /unnamed until it consents/);
  assert.doesNotMatch(solvers, /three outside teams|within 0\.01 K in both cases/i);
});
