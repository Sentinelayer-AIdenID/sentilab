// node --test scripts/deck-founder.test.mjs   (CI runs it through scripts/deck-data.test.mjs)
// The founder pitch (v4): Carter's three-minute main talk, built from docs/sentilab/deck/founder-v4/V4.json.
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";
import {
  FOUNDER_DECK_DIR, FOUNDER_DIR, FOUNDER_OUTPUTS, FounderError, buildFounderData, countWords, fillInTable, founderPdfName,
  loadFounder, outputsMatch, serialize,
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
const MAIN = ["chips", "senti", "room", "hook", "times", "link", "passed", "point", "invite", "closer"];

test("the founder deck is built from V4.json, and the committed deck, script, fill-in and sources match a fresh build", () => {
  assert.equal(serialize(data).json, readFileSync(join(FOUNDER_DECK_DIR, "deck-data.json"), "utf8"));
  assert.ok(outputsMatch(data, loaded.v4), "deck/founder-v4 and SCRIPT/FILL-IN/SOURCES are the build's");
  assert.deepEqual(data.slides.filter((s) => s.main).map((s) => s.id), MAIN);
  assert.deepEqual(data.slides.filter((s) => !s.main).map((s) => s.id), ["sources"]);
  assert.match(html(data), /<section class="slide main" id="s-chips"/);
});

test("the talk fits three minutes at 150 words a minute, transitions included; more words stop the build", () => {
  const u = data.budget;
  assert.equal(u.talkWords, data.slides.filter((s) => s.main).reduce((a, s) => a + s.notes.words, 0));
  assert.ok(u.totalSeconds <= 180, `${u.totalSeconds} s`);
  assert.deepEqual([u.talkWords, u.talkSeconds, u.transitionSeconds, u.totalSeconds], [403, 161.2, 15, 176.2]);
  assert.throws(() => variant((v) => { v.slides[0].say += " and then".repeat(5); }), (e) => e instanceof FounderError && /over the 180 s cap/.test(e.message));
  // A placeholder is one word, read or not, so filling it in does not move the clock.
  assert.equal(slide(data, "invite").notes.words, countWords("We invited agents on Moltbook: N votes, N visits, N passed."));
});

test("root's carried openings, the finding beat in root's words and Carter's additions are spoken word for word", () => {
  const say = (id) => slide(data, id).notes.text;
  // Root, reply to 57809 at 07:04Z: the two paragraph openings, as written.
  assert.ok(say("hook").startsWith("In detailed 3D mode, two versions of HotSpot gave roughly 119 and 241 degrees at the hottest modeled grid cells, for the same design and input files."));
  assert.ok(say("passed").startsWith("Using the older setup and a separate declared reference readout, we reproduced two published reference values within a hundredth of a degree in the saved outputs. The pass bar was one degree, set beforehand. That doesn't establish hardware accuracy."));
  // Root's wording of aneta's beat (reply to 57816 at 07:14Z), right after "hardware accuracy"; the pause is a cue.
  assert.ok(say("passed").endsWith("That doesn't establish hardware accuracy. Then we checked the version that passed. In a saved CPU-DRAM case, 1.39 percent more heat left the model than entered. Source analysis found non-reciprocal lateral links consistent with that. I nodded."));
  assert.match(slide(data, "passed").notes.cue, /Pause before "I nodded\."/);
  // Aneta's shortening (57816), with the distinction kept in the footer.
  assert.ok(say("link").endsWith("Two other teams reported results from changing that link."));
  assert.match(slide(data, "link").content.footer, /^Delfie \(delphisci team\) and ScienceClaw reported results from changing that modeled link; those reports are separate from our verified reference reproduction\./);
  // Carter's additions (57800): the chip joke's second half, what the tech does for agents, the room, the closer.
  assert.ok(say("chips").endsWith("All I know is a chip package is a few small chips, chiplets, that get hot, and you can't put them too close together or too far apart. But I'll tell you what: my agents know chip design."));
  for (const w of ["recognizes agents", "sets them up", "collaborate", "serves what they need", "records everything they did and everywhere they went", "Delegation is scoped", "handled gracefully", "only gets what it's allowed to touch", "Shopping, security, and today, science."]) assert.ok(say("senti").includes(w), w);
  for (const w of ["didn't know how to get their agents talking to other labs' agents", "people watched every agent work", "agents geared each other up and guarded the room", "plain messages became engineering-grade tickets"]) assert.ok(say("room").includes(w), w);
  assert.match(say("closer"), /^My ambition\? Make you wonder why your agents need Kiro, Jira, Slack, Facebook, and GitHub\. Okay, not GitHub\. Yet\./);
  assert.match(slide(data, "closer").notes.cue, /"Okay, not GitHub\. Yet\." is the quiet aside\. Carter may say the network's name out loud: his call/);
  // The closer's slide text, exactly as the coordinator gave it.
  assert.equal(slide(data, "closer").content.text, "One of the largest internet networks reports over 10 billion AI-bot requests a week (April 2026), and AI-agent requests grew more than 1,700% in a year (Sept 2026).");
  assert.equal(slide(data, "closer").content.punch, "Whoever owns the decision layer on that traffic owns key internet infrastructure for the next decade.");
  // Aneta's tile and footer (57816), with Ascend as Layout A (the earlier decks' name for it).
  assert.equal(slide(data, "passed").content.tiles[1].body, "Saved 6.0 runs show more heat out than in: 1.39% on CPU-DRAM, 0.63% on Layout A.");
  assert.equal(slide(data, "passed").content.footer, "Saved 45 mm, 64×64 cases. A non-reciprocal side-link mechanism in the source is consistent with them. The matching saved 7.0 cases balance within rounding. Physical validation remains open.");
});

test("the slides name no vendor or product; the two citations appear on the sources page only", () => {
  const vendors = /cloudflare|\bjev\b|typesafe|ascend|\bkiro\b|\bjira\b|\bslack\b|facebook|github|claude|openai|\bgpt\b/i;
  for (const id of MAIN) assert.doesNotMatch(shown(data, id), vendors, id);
  const src = shown(data, "sources");
  assert.ok(src.includes("blog.cloudflare.com/rethinking-cache-ai-humans/") && src.includes("blog.cloudflare.com/agentic-web"), "both citations");
  // Science is labelled simulated wherever it is shown.
  for (const id of ["chips", "hook", "link", "passed"]) assert.match(shown(data, id), /simulated, not silicon|Simulated, not silicon/, id);
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
});

test("a number not measured yet shows \"measuring…\" and is listed to fill in; METRICS.json fills it", () => {
  const want = ["intent.helpful_messages", "cost.weekend_total", "moltbook.post_votes", "door.visits", "door.agents_passed", "view.agent_bytes"];
  assert.deepEqual(data.placeholders.map((p) => p.id).sort(), [...want].sort());
  assert.equal((html(data).match(/class="measuring"/g) ?? []).length, 6, "six measuring tiles");
  assert.equal(readFileSync(FOUNDER_OUTPUTS.fillIn, "utf8"), fillInTable(data));
  for (const id of want) assert.ok(readFileSync(FOUNDER_OUTPUTS.fillIn, "utf8").includes(`\`${id}\``), id);
  assert.match(slide(data, "invite").notes.text, /\[votes on our Moltbook post: measuring\]/);
  assert.ok(data.deck.measuring && founderPdfName(data).endsWith("-draft.pdf"));
  // With the metrics on file, the tiles carry them and the words read them out.
  const byId = new Map(want.map((id, k) => [id, { id, value: 100 + k, display: String(100 + k), definition: "d", scope: "s", window: "w", source: "x" }]));
  const filled = variant(() => {}, { sha256: "f".repeat(64), byId });
  assert.equal(filled.placeholders.length, 0);
  assert.doesNotMatch(html(filled), /class="measuring"/);
  assert.match(slide(filled, "invite").notes.text, /^We invited agents on Moltbook: 102 votes, 103 visits, 104 passed\.$/);
  assert.ok(founderPdfName(filled).endsWith("-review.pdf"));
});

test("the founder PDF is the export: one page per slide, the only PDF in its folder", () => {
  const pdfs = readdirSync(FOUNDER_DIR).filter((f) => f.endsWith(".pdf"));
  assert.deepEqual(pdfs, [founderPdfName(committed).split("/")[1]]);
  const pages = (readFileSync(join(PDF_DIR, founderPdfName(committed)), "latin1").match(/\/Type\s*\/Page(?![s\w])/g) ?? []).length;
  assert.equal(pages, committed.slides.length);
  assert.ok(existsSync(join(FOUNDER_DIR, "sheet-main.png")), "the one-image sheet of the main slides is committed beside it");
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
