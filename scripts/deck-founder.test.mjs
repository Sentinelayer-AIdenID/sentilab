// node --test scripts/deck-founder.test.mjs   (CI runs it through scripts/deck-data.test.mjs)
// The founder pitch (v4): Carter's three-minute main talk, built from docs/sentilab/deck/founder-v4/V4.json.
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";
import {
  FOUNDER_DECK_DIR, FOUNDER_DIR, FOUNDER_OUTPUTS, FounderError, buildFounderData, checkUnnamed, countWords, fillInTable,
  founderPdfName, handoffFiles, inputFiles, loadFounder, loadMetrics, outputsMatch, publicOutputs, scriptPath, serialize, sourcesList,
  speakerScript, windowShown,
} from "./build-deck-founder.mjs";
import { PDF_DIR, REPO_ROOT } from "./build-deck-data.mjs";

const require = createRequire(import.meta.url);
const deck = require(join(FOUNDER_DECK_DIR, "deck.js"));
const loaded = loadFounder();
const data = buildFounderData(loaded);
// The source as it stood before the freeze: V4.json in draft mode, with METRICS.json's numbers only. The tests that
// describe placeholders, the fallback and the draft build from it, so they hold before and after the freeze lands.
const pre = (() => {
  const v4 = structuredClone(loaded.v4);
  delete v4.build;
  delete v4.metrics.freezeSha256;
  delete v4.metrics.freezeNote;
  return { ...loaded, v4, metrics: { ...loadMetrics(), freezeSha256: null } };
})();
// The draft, built explicitly: the tests that describe placeholders and the DRAFT tag hold before and after the freeze.
const draft = buildFounderData(pre, { final: false });
const committed = JSON.parse(readFileSync(join(FOUNDER_DECK_DIR, "deck-data.json"), "utf8"));
// A build of a changed copy of the pre-freeze source, for the refusal tests.
const variant = (mutate, metrics = pre.metrics) => {
  const v4 = structuredClone(pre.v4);
  mutate(v4);
  return buildFounderData({ ...pre, v4, metrics });
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
  const d = draft.budget;
  assert.deepEqual([d.talkWords, d.talkSeconds, d.transitionSeconds, d.totalSeconds], [400, 160, 15, 175]);
  assert.throws(() => variant((v) => { v.slides[0].say += " and then".repeat(50); }), (e) => e instanceof FounderError && /over the 200 s cap/.test(e.message));
  // A placeholder is one word, read or not, so filling it in does not move the clock.
  assert.equal(slide(draft, "invite").notes.words, countWords("We're inviting agents on Moltbook: N votes, N visits, N passed."));
  // v4-short: two minutes of talk, transitions included, then the demo.
  const short = buildFounderData(loaded, { slot: "2min", final: false });
  assert.deepEqual(short.slides.filter((x) => x.main).map((x) => x.id), SHORT);
  assert.deepEqual([short.budget.talkWords, short.budget.talkSeconds, short.budget.transitionSeconds, short.budget.totalSeconds], [250, 100, 10, 110]);
  // The cut slides lead the backup, then the backup pages.
  assert.deepEqual(short.slides.filter((x) => !x.main).map((x) => x.id), ["senti", "times", "link", "point", "sources", "cost", "solvers"]);
  assert.throws(() => buildFounderData(loaded, { slot: "4min" }), /--slot must be one of 3min, 2min/);
});

test("root's carried openings, the finding beat in root's words and Carter's additions are spoken word for word", () => {
  const say = (id) => slide(data, id).notes.text;
  // Root, reply to 57809 at 07:04Z: the two paragraph openings, as written.
  assert.ok(say("hook").startsWith("In detailed 3D mode, two versions of HotSpot gave roughly 119 and 241 degrees at the hottest modeled grid cells, for the same design and input files."));
  // Slide 7, the scorecard: aneta's first sentence (57906), root's preferred wording (reply to 57902, 08:04Z), then the beat.
  assert.equal(say("scorecard"), "Our fixed reference test with the older setup reproduced two published values within a hundredth of a degree. But in a saved CPU-DRAM case, 1.39 percent more heat left the model than entered. The modified output is within rounding in our own run and nearer the separate solvers; it still misses the paper. Source analysis found non-reciprocal lateral links consistent with that. I nodded.");
  assert.match(slide(data, "scorecard").notes.cue, /Pause before "I nodded\."/);
  assert.equal(slide(data, "scorecard").content.title, "Passing one check isn't passing them all.");
  // Aneta's shortening (57816), with the distinction kept in the footer.
  assert.ok(say("link").endsWith("Two other teams reported results from changing that link. We ran it too, against a bar we fixed in advance, and it met it."));
  assert.match(slide(data, "link").notes.cue, /"We ran it too" is the configured diagnostic, as Carter's Q&A has it .*localizes the difference to this term in this configured model/);
  assert.equal(slide(data, "link").content.line, "Two other teams reported results from changing that link.", "the slide itself is unchanged");
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
  // The room's numbers are the metrics file's (its facts hold each to METRICS.json, refreshed at the freeze).
  const help = (k) => loaded.metrics.byId.get(k).value;
  assert.match(say("room"), new RegExp(`${help("crosscheck.help.messages")} messages from ${help("crosscheck.help.posting_identities")} identities: \\d+ human, ${help("crosscheck.help.members_plus_posting_agents") - help("crosscheck.help.members")} agent\\.$`));
  // Slide 3 is aneta's plain14-room v4 (root's scoped +1 at 14:56:50Z): its footer and SOURCES carry root's three
  // qualifications, and the picture its own counts, links, help outcomes and ticket split.
  assert.equal(slide(data, "room").content.figure.id, "plain14");
  for (const q of ["Messages posted by 14:30 UTC, with the structure read at 14:36 UTC and a later edit retained.", "Links are thread author plus mentions: a message reaching five handles counts five times. They're links, not confirmed exchanges or usefulness.", "30 tickets = 21 in the help room + 9 in our team room, at 14:31 UTC."]) {
    assert.ok(slide(data, "room").content.footer.includes(q), q);
    assert.ok(shown(data, "sources").includes(q), q);
  }
  assert.ok(shown(data, "sources").includes("Accepted for structure and picture, with 546 of 583 rows corroborated; not a complete raw-history verification."));
  const p14 = readFileSync(join(FOUNDER_DECK_DIR, "figures", "plain14-room.svg"), "utf8");
  for (const t of ["21 in the help room, 9 in our team room", "4 reported checks of our test case", "2 of the other 5 said it was useful", "We offered help to 9 outside groups, by 12:46 UTC"]) assert.ok(p14.includes(t), t);
  assert.doesNotMatch(shown(data, "room") + say("room"), /\b17 people\b/);
  // Rev 5 (aneta 57941): one 8 on the slide; the posting-group estimate stays on the sources page.
  assert.doesNotMatch(shown(data, "room"), /posting groups/);
  assert.ok(shown(data, "sources").includes("The slide 3 picture: 583 messages posted by 14:30 UTC, from 28 posting identities."));
  assert.equal(slide(data, "room").content.tiles, undefined, "the picture takes the tiles' place");
  assert.doesNotMatch(shown(data, "room"), /at least 8|outside teams/, "posting groups are not teams (root, 08:40Z)");
  // Help offered, in the groups' own reports, in place of the model-rated count, which moves to the sources page. Refreshed
  // to 12:46 UTC in root's explicit disjoint wording, word for word (aneta 58014; root's +1, reply to 57809 at 12:57:04Z).
  // The help outcomes (4/9/2) stay the separately accepted line, with root's +1 at 12:57:04Z, in SOURCES.
  assert.ok(readFileSync(FOUNDER_OUTPUTS.sources, "utf8").includes("Aneta's refreshed help line (team room 58014, 12:46:31Z), with root's scoped +1 and his explicit disjoint wording"));
  assert.doesNotMatch(shown(data, "room"), /\b281\b|04:01|we offered help to 8|3 outside groups/);
  assert.match(shown(data, "sources"), /Help offered, to 12:46 UTC: nine outside groups, each counted once\. Four reported checks of our test case/);
  assert.match(shown(data, "sources"), new RegExp(`Model-rated, not confirmed usefulness, to 1 Nov \\d\\d:\\d\\d UTC: our intent model rated ${help("helpful.messages")} of the ${help("helpful.scored_messages")}`));
  // Root's content P2 (14:45:47Z): the cost page's intent-model line is the freeze file's, in its own window, with no dollar claim.
  assert.ok(shown(data, "cost").includes(`Our intent model: ${help("intent_model.calls")} recorded successful calls (109 dry run, 448 live, 77 host scores), 31 Oct 22:13 to 1 Nov 14:18 UTC; its cost is not measured.`));
  assert.doesNotMatch(shown(data, "cost"), /\b480 calls\b|hackathon window/);
  assert.match(shown(data, "sources"), /Help offered, to 12:46 UTC: nine outside groups, each counted once\. Four reported checks of our test case: .*; another outside team, after 04:01\. Two of the other five said our help was useful \(21:13:28; 00:04:12 and 00:08:14\)\. Three unconfirmed\./);
  assert.ok(readFileSync(FOUNDER_OUTPUTS.sources, "utf8").includes("Aneta's refreshed help line (team room 58014, 12:46:31Z), with root's scoped +1 and his explicit disjoint wording (reply to 57809, 12:57:04Z)"));
  assert.match(fillInTable(draft), /## Refresh at the freeze/);
  assert.match(say("closer"), /^My ambition\? Make you wonder why your agents need Kiro, Jira, Slack, Facebook, and GitHub\. Okay, not GitHub\. Yet\./);
  assert.match(slide(data, "closer").notes.cue, /"Okay, not GitHub\. Yet\." is the quiet aside\. Naming the network out loud is Carter's call \(aneta recommends naming it\)/);
  assert.ok(say("closer").endsWith("I believe whoever owns the decision layer on that traffic will own key internet infrastructure for the next decade."));
  // The closer's slide text, exactly as the coordinator gave it.
  // Rev 4: slide 10 is aneta's plain11; the two numbers and the belief line are drawn in it, as reported, with sources on B1.
  // Rev 4: the v1.24 visuals, pending root's +1, marked as such on the draft.
  const v124 = { senti: ["plain9", "f984958943931297813ccc201296b67d133aa9b36e55b5f7d94dd9abee28023e"], times: ["plain4", "036788919f1a9f8a6138b139e0da55eac6592dc9dd7b7326155682bd7f1fea71"], point: ["plain10", "58a26507ea34052bc8e1dbcde9f49e5ead6718916a86ef676c587adac747edd7"], closer: ["plain11", "770f3bff3176ed19e15023e6b26865d7c30eae53764befd7afbc350e910c9521"] };
  for (const [id, [fig, hash]] of Object.entries(v124)) {
    assert.equal(slide(data, id).content.figure.id, fig, id);
    assert.equal(loaded.v4.figures[fig].sha256, hash, fig);
    // Root's scoped +1 on the v1.24 figure assets (10:16:54Z), so none is pending any more.
    assert.equal(loaded.v4.figures[fig].pending, undefined, fig);
    assert.ok(loaded.v4.figures[fig].review.startsWith("root's scoped +1 on v1.24, 10:16:54Z (review 66d1d020"), fig);
  }
  // Slide 9's freeze fallback is aneta's plain12-tradeoff from v1.25, root's scoped +1 (10:42:24Z), with the QR code (the
  // coordinator, 14:13Z): the board the audience is invited to. plain13 is the demo's figure at 1:15 and leaves the deck,
  // as v1.22's plain8 did; both stay in the review evidence.
  assert.equal(loaded.v4.figures.plain12.sha256, "31176c7d13ef96c987b5775c9c9ee41a4b739e6bafac1314eef838a59f69524a");
  assert.match(loaded.v4.figures.plain12.review, /^aneta's v1\.25 \(ZIP 824dd6a6f13838d0628b98136778440aea826d04254cb395f780eb656eae73a0, 44,927 bytes\); root's scoped \+1, 10:42:24Z \(reply to 57940\)/);
  // Every figure on the freeze branch is approved: v1.24's, v1.25's plain12, v1.30's plain7.
  for (const [id, f] of Object.entries(loaded.v4.figures)) assert.equal(f.pending, undefined, id);
  const p12 = readFileSync(join(FOUNDER_DECK_DIR, "figures", "plain12-tradeoff.svg"), "utf8");
  for (const t of ["Each dot is one team run, reproduced by a fresh-process replay", "Not a frontier or an optimum: an adaptive search that stopped early chose these points."]) assert.ok(p12.includes(t), t);
  assert.equal(loaded.v4.slides.find((x) => x.id === "invite").finalFallback.figure, "plain12");
  for (const gone of ["plain8", "plain13"]) {
    assert.equal(loaded.v4.figures[gone], undefined, gone);
    for (const dir of [join(FOUNDER_DIR, "figures"), join(FOUNDER_DECK_DIR, "figures")]) assert.ok(!readdirSync(dir).some((f) => f.startsWith(gone)), `${dir}: ${gone}`);
  }
  assert.ok(readFileSync(join(FOUNDER_DECK_DIR, "figures", "plain11-traffic.svg"), "utf8").includes("I believe whoever owns the decision layer on that traffic"));
  assert.doesNotMatch(html(data), /figure pending review/);
  // plain9 is captioned as the historical staging run it shows (root, 10:16:54Z): the figure carries the caveat, the footer
  // only the place and time (aneta's audience read, 13:43:46Z).
  assert.equal(slide(data, "senti").content.footer, "Staging door, 08:39 UTC, 1 November.");
  assert.ok(readFileSync(join(FOUNDER_DECK_DIR, "figures", "plain9-senti-door.svg"), "utf8").includes("These are our own team's test runs, not outside arrivals."));
  assert.equal(slide(data, "senti").content.figure.minFont, 21, "plain9's own 21 px text stays as drawn, recorded for the renderer");
  // The scorecard is aneta's v1.30 plain7, with root's +1 (12:12:03Z): its third row is our own run, served as drawn, with
  // its own alt text (the expanded description, now with our run) and this deck's label.
  const fig = slide(data, "scorecard").content.figure;
  assert.equal(fig.id, "plain7");
  assert.equal(loaded.v4.figures.plain7.sha256, "b5d487be828a694d8e9b22c23a79e5b355970805042243ad20683adcaf657ae9");
  assert.match(loaded.v4.figures.plain7.review, /^aneta's v1\.30 \(ZIP 251fee39fa8c3e9982aabaed27840deae6cb5461e44ef4b0875c0c5d3ec89cfd, 45,938 bytes\).*root's \+1, 12:12:03Z \(reply to 57988\), covering the g1 heat balance and attribution$/);
  assert.equal(loaded.v4.figures.plain7.pending, undefined);
  assert.equal(loaded.v4.figures.plain7.edits, undefined);
  assert.equal(loaded.v4.figures.plain7.alt, undefined);
  const served = readFileSync(join(FOUNDER_DECK_DIR, "figures", "plain7-scorecard.svg"), "utf8");
  for (const t of ["Each column uses its own reading.", "Rounding limit: about 0.43 W, 0.063%; not a total error bound.", "Older: our pinned 6.0 build", "our run; also Delfie and ScienceClaw"]) assert.ok(served.includes(t), t);
  assert.ok(!served.includes("re-ran it") && !served.includes("as ScienceClaw reports"), "our own run, no longer only reported");
  // The expanded description (57915): the selector, rounding and provenance qualifications, with our run.
  for (const t of ["The heat check's rounding limit is about 0.43 watts, 0.063 percent, and is not a total error bound.", "The paper column uses the native all-block reading, 232.67 degrees for 7.0.", "The solver column uses the hottest chiplet entry, 224.67 degrees for 7.0", "our own run, with the same result reported by Delfie and ScienceClaw"]) assert.ok(fig.alt.includes(t), t);
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
  refuses("a vendor on a slide", /public-render rule/, (v) => { v.slides[9].footer = "As Cloudflare reports."; });
  refuses("a product on a slide", /product name/, (v) => { v.slides[9].footer = "Kiro, Jira and Slack in one place."; });
  refuses("an unconsented team", /has not consented/, (v) => { v.slides[4].footer += " Kiln solved it too."; });
  refuses("Delfie in another form", /form the team asked for/, (v) => { v.slides[4].footer += " Delfie checked it."; });
  refuses("science not labelled", /without saying "simulated"/, (v) => { v.slides[3].label = "two versions"; v.slides[3].footer = "Hottest modeled grid cells."; });
  refuses("an undeclared number", /which none of its facts declares/, (v) => { v.slides[2].footer += " 512 more."; });
  refuses("a duration its records don't give", /is not its records'/, (v) => { v.slides[4].times = [{ show: "30 min", what: "from a question to a suspect", from: "2026-10-31T12:43:33.374Z", to: "2026-10-31T13:15:38.133Z", rule: "round" }]; });
  refuses("a bar not its value", /is not 119.07 rounded/, (v) => { v.slides[3].bars[0].show = "120 °C"; });
  refuses("17 people", /17 is member accounts/, (v) => { v.slides[2].say += " 17 people took part."; });
  refuses("a solver library named", /unresolved 115.93 against 115.94/, (v) => { v.slides[6].footer += " SuperLU explains it."; });
  refuses("money on a main slide", /money on a main slide/, (v) => { v.slides[2].footer += " It cost USD 8,232.41."; });
  const msgs = pre.metrics.byId.get("crosscheck.help.messages").value;
  refuses("a number that is not the metrics file's", new RegExp(`but METRICS.json gives ${msgs.toLocaleString("en-US")}`), (v) => { v.slides[2].facts[0].shows = [String(msgs - 1)]; });
  refuses("a different metrics file", /is not the file V4.json pins/, (v) => { v.metrics.sha256 = "0".repeat(64); });
});

test("a number not measured yet shows \"measuring…\" and is listed to fill in; METRICS.json fills it", () => {
  const want = ["moltbook.post_votes", "door.visits", "door.agents_passed", "view.agent_bytes"];
  assert.deepEqual(draft.placeholders.map((p) => p.id).sort(), [...want].sort());
  assert.equal((html(draft).match(/class="measuring"/g) ?? []).length, 4, "four measuring tiles, all on the door slide");
  assert.equal(readFileSync(FOUNDER_OUTPUTS.fillIn, "utf8"), fillInTable(data), "FILL-IN is the committed build's");
  for (const id of want) assert.ok(fillInTable(draft).includes(`\`${id}\``), id);
  for (const p of data.placeholders) assert.ok(readFileSync(FOUNDER_OUTPUTS.fillIn, "utf8").includes(`\`${p.id}\``), p.id);
  assert.match(slide(draft, "invite").notes.text, /^We're inviting agents on Moltbook: \[votes on our Moltbook invitation: measuring\]/);
  assert.doesNotMatch(shown(draft, "invite") + slide(draft, "invite").notes.text, /\bWe invited\b|\bour (?:Moltbook )?post\b/, "no past tense about Moltbook before the post exists");
  assert.ok(draft.deck.measuring && founderPdfName(draft).endsWith("-draft.pdf"));
  // With the metrics on file, the tiles carry them and the words read them out.
  const keys = ["moltbook.post_votes", "door.visits", "door.agents_passed", "door.view_size"];
  const byId = new Map([...pre.metrics.byId, ...keys.map((id, k) => [id, { id, value: 100 + k, display: String(100 + k), definition: "d", scope: "s", window: "w", source: "x" }])]);
  const filled = variant(() => {}, { sha256: pre.metrics.sha256, byId });
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
  assert.match(speakerScript(draft, pre.v4), /\*\*With the demo:\*\* 120 s of demo makes 295 s \(4:55\) at 150 wpm, or 312\.8 s \(5:13\) at 135\. Before the talk, do one real timed rehearsal with the actual demo\./);
  assert.match(speakerScript(buildFounderData(pre, { slot: "2min", final: false }), pre.v4), /60 s of demo makes 170 s \(2:50\)/);
  assert.match(committed.slides[0].notes.cue, /one real timed rehearsal with the actual demo/);
  assert.equal(readFileSync(scriptPath("2min"), "utf8"), speakerScript(short, loaded.v4));
});

test("--final drops every number without a receipt, speaks the no-numbers line, and loses the DRAFT tag", () => {
  // The freeze refuses a figure still pending review; with root's +1 on v1.24, none is.
  const pending = structuredClone(pre.v4);
  pending.figures.plain10.pending = "v9.99, pending a reviewer's +1";
  assert.throws(() => buildFounderData({ ...pre, v4: pending }, { final: true }), /pending a reviewer's \+1; the freeze takes only reviewed figures/);
  const reviewed = structuredClone(pre.v4);
  for (const slot of ["3min", "2min"]) {
    const fin = buildFounderData({ ...pre, v4: reviewed }, { slot, final: true });
    assert.equal(fin.deck.draft, false);
    assert.equal(fin.deck.measuring, false);
    assert.doesNotMatch(html(fin), /measuring…|class="measuring"|DRAFT/, slot);
    assert.equal(slide(fin, "invite").content.tiles, undefined, "slide 9's tiles have no receipt yet, so none is shown");
    assert.equal(slide(fin, "invite").content.figure.id, "plain12", "the fallback picture at the freeze");
    assert.equal(slide(fin, "invite").notes.text, "We're inviting other people's agents to the chip challenge: scan the code and send yours.");
    assert.ok(founderPdfName(fin).endsWith("-final.pdf"));
    // Root's copy P2 (relayed 13:49Z): the final's script lists what was dropped, and claims no "measuring…" for it.
    const script = speakerScript(fin, reviewed);
    assert.ok(fin.placeholders.length > 0 && fin.placeholders.every((p) => p.dropped && script.includes(`\`${p.id}\``)), slot);
    assert.match(script, /## Not shown: dropped at the freeze\n\nEach had no number on its slide at the freeze, so the slide does not show it and the words do not read it \(no receipt\):/);
    assert.doesNotMatch(script, /## Still measuring|shows "measuring…" on its slide/, slot);
    // The script and FILL-IN say what the build is: the freeze's final, not a review.
    assert.match(speakerScript(fin, reviewed).split("\n")[0], /, final \d{4}-\d\d-\d\d \d\d:\d\d UTC$/, slot);
    assert.match(fillInTable(fin), /^# FILL-IN: the founder deck's placeholders\n\nThe freeze, \d{4}-\d\d-\d\d \d\d:\d\d UTC\. Each below had no receipt/);
    assert.ok(fin.budget.totalSeconds <= fin.budget.talkCapSeconds);
  }
  assert.match(speakerScript(draft, pre.v4).split("\n")[0], /, draft \d{4}-\d\d-\d\d \d\d:\d\d UTC$/);
  assert.match(speakerScript(draft, pre.v4), /## Still measuring\n\nEach shows "measuring…" on its slide and is read out only once it is filled:/, "a draft keeps its wording");
  // The draft keeps the placeholders and the tag.
  assert.match(html(draft), /DRAFT · numbers still measuring/);
  // A slide whose words need a missing number must say what to speak at the freeze instead.
  const noLine = structuredClone(reviewed);
  delete noLine.slides.find((x) => x.id === "invite").sayIfUnmeasured;
  assert.throws(() => buildFounderData({ ...pre, v4: noLine }, { final: true }), /no sayIfUnmeasured line/);
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
  assert.match(solvers, /another outside team's, unnamed at its request\./);
  assert.doesNotMatch(solvers, /until it consents/);
  assert.doesNotMatch(solvers, /three outside teams|within 0\.01 K in both cases/i);
});

test("the optional D1 layout result is Carter's call: in the notes and FILL-IN with its qualifiers, never on a slide or spoken", () => {
  const o = loaded.v4.options.find((x) => x.id === "d1-layout");
  assert.equal(o.line, "And one of our own agents has already found a layout that runs about 2.7 degrees cooler in this model. It's a diagnostic result, not a record.");
  for (const q of ["team-only staging run, not external dogfood", "diagnostic simulation against our reconstructed reference", "proxy, not routed", "not a paper beat and not validated", "HotSpot 6 heat-balance caveat"]) assert.ok(o.qualifiers.includes(q), q);
  for (const d of [data, buildFounderData(loaded, { slot: "2min" })]) {
    for (const x of d.slides.filter((y) => y.main)) assert.doesNotMatch(x.notes.text + shown(d, x.id), /2\.7 degrees cooler|113\.225|D1/, x.id);
  }
  assert.match(slide(data, "invite").notes.cue, /Carter's option, not spoken unless he asks: the D1 layout line/);
  const fill = readFileSync(FOUNDER_OUTPUTS.fillIn, "utf8");
  assert.ok(fill.includes("## Optional, Carter's call: notes only, not on a slide") && fill.includes(o.line) && fill.includes(o.qualifiers));
  for (const slot of ["3min", "2min"]) assert.ok(readFileSync(scriptPath(slot), "utf8").includes("## Option, Carter's call: not spoken unless he asks (slide invite)"), slot);
});

test("the freeze drops tiles without a receipt even with no fallback picture, and a figure's own words face the public-render rule", () => {
  const reviewed = structuredClone(pre.v4);
  for (const fig of Object.values(reviewed.figures)) delete fig.pending;
  delete reviewed.slides.find((x) => x.id === "invite").finalFallback;
  const fin = buildFounderData({ ...pre, v4: reviewed }, { final: true });
  assert.deepEqual(slide(fin, "invite").content.tiles, [], "no receipt, no tile");
  // A vendor name drawn into a figure stops the build like one typed on the slide.
  const named = structuredClone(loaded.v4);
  named.figures.plain11.edits = [{ from: "AI-bot requests a week", to: "Cloudflare AI-bot requests a week", why: "test only" }];
  assert.throws(() => buildFounderData({ ...loaded, v4: named }), (e) => e instanceof FounderError && /public-render rule .* figure plain11/.test(e.message));
});

test("a figure still pending review is marked on its draft slide", () => {
  const pending = structuredClone(pre.v4);
  pending.figures.plain10.pending = "v9.99, pending a reviewer's +1";
  const d = buildFounderData({ ...pre, v4: pending });
  const section = (id) => html(d).split("\n").find((x) => x.includes(`id="s-${id}"`));
  assert.match(section("point"), /DRAFT · figure pending review/);
  assert.doesNotMatch(section("chips"), /figure pending review/);
});

test("slide 9's QR code is read from its pixels: exactly https://sentilab.aidenid.com, the door the slide prints", async () => {
  const { readQr, readQrPixels, decodePng } = await import("./qr-read.mjs");
  const Q = loaded.v4.stills.qr;
  assert.equal(Q.payload, "https://sentilab.aidenid.com");
  for (const p of [join(FOUNDER_DIR, "figures", Q.file), join(FOUNDER_DECK_DIR, "figures", Q.file)]) {
    const r = readQr(readFileSync(p));
    assert.deepEqual([r.text, r.version, r.ec], ["https://sentilab.aidenid.com", 3, "M"], p);
  }
  // The slide prints the same door, and the image is the one the build checks.
  assert.ok(slide(draft, "invite").content.points.includes("The agent door: sentilab.aidenid.com"));
  assert.equal(slide(draft, "invite").content.still.id, "qr");
  // A damaged module fails the read instead of returning other text, and a QR that reads otherwise stops the build.
  const img = decodePng(readFileSync(join(FOUNDER_DIR, "figures", Q.file)));
  const flip = { ...img, px: Buffer.from(img.px) };
  const at = (r, c) => [64 + (c + 0.5) * 16, 64 + (r + 0.5) * 16].map(Math.floor);
  const [x, y] = at(10, 12); // a data module: clear of the finders, the timing lines, the alignment pattern and the format bits
  for (let dy = -8; dy < 8; dy++) for (let dx = -8; dx < 8; dx++) {
    const i = ((y + dy) * img.w + (x + dx)) * img.bpp;
    for (let k = 0; k < Math.min(3, img.bpp); k++) flip.px[i + k] = 255 - flip.px[i + k];
  }
  assert.throws(() => readQrPixels(flip), /syndrome|format information/);
  const wrong = structuredClone(loaded.v4);
  wrong.stills.qr.payload = "https://sentilab.aidenid.com/sentilab/package/?feed=door&src=live";
  assert.throws(() => buildFounderData({ ...loaded, v4: wrong }), (e) => e instanceof FounderError && /encodes "https:\/\/sentilab\.aidenid\.com", not/.test(e.message));
});

test("root's rev 5 review: the timeline keeps its qualifications, the help line is dated, and no script heading is undefined", () => {
  // Page 5: the accepted v1.24 timeline travels with its qualifications; the fuller account sits on the sources page.
  assert.equal(slide(data, "times").content.footer, "Room posting times, not earlier local freezes. One agent saw a one-line preview; Agent4 had already read the suspect. Lanes show contributions, not independence. No savings baseline.");
  assert.equal(slide(data, "times").content.figure.id, "plain4");
  for (const t of ["room posting times, not earlier local freezes", "one agent had seen a one-line preview", "having already read the suspect", "not independence", "No savings figure: there is no baseline", "every plotted time kept"]) assert.ok(shown(data, "sources").includes(t), t);
  // Page 3: the help count carries its date (refreshed to 12:46 UTC, root's +1 at 12:57:04Z); aneta's 14:05Z re-check is
  // on the FILL-IN refresh list, and nothing claims a refresh the build has not made.
  assert.ok(slide(data, "room").content.footer.startsWith("Help room record, 31 Oct 13:46 to 1 Nov 14:30 UTC; handles, not people."));
  assert.doesNotMatch(shown(data, "room") + shown(data, "sources"), /refresh(?:ed)? at the freeze/);
  assert.match(fillInTable(draft), /\| room \| Help offered: four checked, nine offered in all, two of the other five said it was useful \(to 12:46 UTC, root's \+1 at 12:57:04Z\) \| Aneta re-checks at about 14:05Z/);
  // The scripts: every main slide has a real heading, in both cuts.
  for (const slot of ["3min", "2min"]) {
    const heads = [...readFileSync(scriptPath(slot), "utf8").matchAll(/^## (\d+)\. (.*) \(([^)]*)\)$/gm)];
    assert.equal(heads.length, slot === "3min" ? 10 : 6, slot);
    for (const [, n, h] of heads) assert.ok(h.trim() && !/\bundefined\b|\bnull\b/.test(h), `${slot} slide ${n}: ${JSON.stringify(h)}`);
  }
  assert.match(readFileSync(scriptPath("3min"), "utf8"), /^## 8\. Check the grader before celebrating the score\. \(The point\)$/m);
  assert.match(readFileSync(scriptPath("3min"), "utf8"), /^## 10\. Whoever owns the decision layer on agent traffic\. \(Why it matters\)$/m);
});

test("V4.json's build sets the committed build's mode: \"final\" is the freeze, anything else but \"draft\" stops the build", () => {
  const frozen = structuredClone(pre.v4);
  frozen.build = "final";
  const fin = buildFounderData({ ...pre, v4: frozen });
  assert.equal(fin.deck.draft, false);
  assert.doesNotMatch(html(fin), /DRAFT/);
  assert.ok(founderPdfName(fin).endsWith("-final.pdf"));
  // At the freeze, a number with no receipt is listed as dropped, not as still measuring.
  assert.match(fillInTable(fin), /votes on our Moltbook invitation \(dropped at the freeze: no receipt\)/);
  // With the coordinator's receipt for what slide 9 does not show, FILL-IN carries it and points each row to it.
  const noted = structuredClone(frozen);
  noted.metrics.freezeNote = "Counted to 14:30:00Z: none from outside (test).";
  const withNote = fillInTable(buildFounderData({ ...pre, v4: noted }));
  assert.match(withNote, /votes on our Moltbook invitation \(not shown at the freeze: see "At the freeze"\)/);
  assert.ok(withNote.includes("## At the freeze\n\nSlide 9 (invite) shows its no-numbers fallback: plain12-tradeoff.svg, with the QR code to https://sentilab.aidenid.com and the door's address.\n\nCounted to 14:30:00Z: none from outside (test).\n"));
  assert.match(withNote, /^# FILL-IN: the founder deck's placeholders\n\nThe freeze, .*the receipt is under "At the freeze"\./);
  // The refresh list is a draft's to-do for the freeze: the final lists none.
  assert.match(fillInTable(draft), /## Refresh at the freeze/);
  assert.doesNotMatch(fillInTable(fin), /Refresh at the freeze/);
  assert.ok(!fillInTable(buildFounderData({ ...pre, v4: noted }, { final: false })).includes("## At the freeze"), "a draft carries no freeze note");
  assert.doesNotMatch(fillInTable(draft), /dropped at the freeze/);
  const odd = structuredClone(loaded.v4);
  odd.build = "rehearsal";
  assert.throws(() => buildFounderData({ ...loaded, v4: odd }), /V4.json build must be "draft" or "final"/);
});

test("at the freeze, slide 9 keeps each measured tile and always the QR code and the door: all four measured, some, none", async () => {
  const { readQr } = await import("./qr-read.mjs");
  const m = (id, value) => [id, { id, value, display: String(value), definition: "d", scope: "s", window_start: "2026-11-01T07:13:20Z", window_end: "2026-11-01T14:20:05Z", window: "2026-11-01T07:13:20Z to 2026-11-01T14:20:05Z", source: "x", from: "METRICS-FREEZE.json" }];
  const freeze = (keys) => variant((v) => { v.build = "final"; }, { sha256: pre.metrics.sha256, byId: new Map([...pre.metrics.byId, ...keys.map((k, i) => m(k, 10 + i))]) });
  const cases = { all: ["moltbook.post_votes", "door.visits", "door.agents_passed", "door.view_size"], some: ["door.visits", "door.agents_passed"], none: [] };
  for (const [name, keys] of Object.entries(cases)) {
    const d = freeze(keys);
    const inv = slide(d, "invite");
    assert.equal(inv.content.title, "We're inviting other people's agents to the chip challenge.", `${name}: the invitation stays`);
    // The call to action, in every case: the QR code (read from its pixels) and the door's address.
    assert.equal(inv.content.still?.id, "qr", `${name}: the QR code stays`);
    assert.equal(readQr(readFileSync(join(FOUNDER_DIR, "figures", loaded.v4.stills[inv.content.still.id].file))).text, "https://sentilab.aidenid.com", name);
    assert.match(shown(d, "invite"), /The agent door: sentilab\.aidenid\.com/, `${name}: the door's address stays, as drawn`);
    const section = html(d).split("\n").find((x) => x.includes('id="s-invite"'));
    assert.match(section, /data-still="qr"/, `${name}: the QR code is drawn`);
    assert.doesNotMatch(html(d), /measuring…|DRAFT/, name);
    const receipts = sourcesList(d).split("## invite")[1]?.split("\n## ")[0] ?? "";
    if (name === "none") {
      assert.equal(inv.content.layout, "fallback");
      assert.equal(inv.content.figure.id, "plain12", "the fallback picture only when nothing is measured");
      assert.match(section, /data-fig="plain12"/, "the fallback picture is drawn");
      assert.equal(inv.content.tiles, undefined);
      // No tile, so no tile receipt; the picture's numbers have theirs in SOURCES.md, and FILL-IN names the fallback.
      assert.match(receipts, /^\n\n- 115\.94, 113\.23, 108\.85, 104\.62, 98\.29, 96\.51, 2\.71, 19\.43, 1\.49, 0\.2: plain12-tradeoff, aneta's v1\.25 \(ZIP 824dd6a6\.\.\., 44,927 bytes; root's scoped \+1 at 10:42:24Z, reply to 57940\)/);
      assert.ok(fillInTable(d).includes("Slide 9 (invite) shows its no-numbers fallback: plain12-tradeoff.svg, with the QR code to https://sentilab.aidenid.com and the door's address."));
      // The footer was plain13's line; plain12 carries its own small print, so the fallback adds none.
      assert.equal(inv.content.footer, "");
    } else {
      assert.equal(inv.content.layout, "numbers");
      assert.equal(inv.content.figure, undefined, `${name}: no fallback picture while a number is measured`);
      assert.deepEqual(inv.content.tiles.map((t) => t.metric), loaded.v4.slides.find((x) => x.id === "invite").tiles.map((t) => t.metric).filter((id) => keys.includes(loaded.v4.metrics.wanted[id].key ?? id)), `${name}: each measured tile, in order`);
      // The footer's promise: each count is shown with its time window; and each has its receipt in SOURCES.md.
      for (const t of inv.content.tiles) assert.equal(t.when, "Nov 1, 07:13–14:20 UTC", `${name}: ${t.metric} shows its window`);
      assert.equal((section.match(/<span class="tw">Nov 1, 07:13–14:20 UTC<\/span>/g) ?? []).length, keys.length, `${name}: one window per tile`);
      for (const k of keys) assert.match(receipts, new RegExp(`METRICS-FREEZE\\.json ${k.replace(/\./g, "\\.")} = \\d+ \\(d; window 2026-11-01T07:13:20Z to 2026-11-01T14:20:05Z; scope s\\)`), `${name}: ${k}'s receipt`);
    }
  }
});

test("the deck's own words on the cross-check follow root's P2: never \"their own solvers\", never a rerun duration", () => {
  const texts = [
    ...[join(FOUNDER_DIR, "V4.json"), scriptPath("3min"), scriptPath("2min"), FOUNDER_OUTPUTS.fillIn, FOUNDER_OUTPUTS.sources].map((p) => readFileSync(p, "utf8")),
    html(draft),
    html(variant((v) => { v.build = "final"; })),
  ];
  for (const t of texts) assert.doesNotMatch(t, /own solvers|re-?ran (?:it )?(?:with)?in (?:under )?(?:six|6) minutes/i);
});

test("a slide with a QR code also prints the address it encodes, on the draft and at the freeze", () => {
  const noDoor = (v) => { v.slides.find((x) => x.id === "invite").points = []; };
  assert.throws(() => variant(noDoor), /slide invite shows a QR code without the address it encodes \(sentilab\.aidenid\.com\)/);
  assert.throws(() => variant((v) => { noDoor(v); v.build = "final"; }), /slide invite shows a QR code without the address it encodes/);
});

test("a team that has not consented to be named appears in nothing the deck publishes: Vortex stays \"another team\"", () => {
  assert.ok(loaded.v4.teams.unnamed.includes("Vortex"));
  // Everything the build writes (deck data, both scripts, FILL-IN, SOURCES, every figure as served, text and alt) and
  // Carter's handoff files: none names an unnamed team, and none holds "vortex" in any letter case, even inside a word.
  const files = [...publicOutputs(data, loaded.v4, loaded), ...handoffFiles(loaded.v4), ...inputFiles()];
  assert.ok(files.some(([p]) => p.endsWith("METRICS.json")) && files.some(([p]) => p.endsWith("METRICS.md")), "the metrics files are scanned too");
  for (const f of [scriptPath("3min"), scriptPath("2min"), FOUNDER_OUTPUTS.fillIn, FOUNDER_OUTPUTS.sources, join(FOUNDER_DIR, "CARTER-QA.md"), join(FOUNDER_DIR, "DEMO-RUN-SHEET.md")]) assert.ok(files.some(([p]) => p === f), f);
  checkUnnamed(files, loaded.v4);
  for (const [p, b] of files) if (/\.(json|js|md|svg)$/.test(p)) assert.doesNotMatch(String(b).replace(/data:[^"')\s]+/g, ""), /vortex/i, p);
  // The guard reads every surface, in any letter case: the notes, a figure's alt text, SOURCES, a handoff file.
  const built = (mutate) => { const v4 = structuredClone(loaded.v4); mutate(v4); const l = { ...loaded, v4 }; return [...publicOutputs(buildFounderData(l), v4, l)]; };
  assert.throws(() => checkUnnamed(built((v) => { v.slides.find((x) => x.id === "link").cue += " As vORtex said."; }), loaded.v4), (e) => e instanceof FounderError && /names Vortex, who has not consented/.test(e.message));
  assert.throws(() => checkUnnamed(built((v) => { v.figures.plain7.alt = "Read by VORTEX."; }), loaded.v4), /names Vortex/);
  assert.throws(() => checkUnnamed(built((v) => { v.slides.find((x) => x.id === "hook").facts[0].source += " (vortex)"; }), loaded.v4), /names Vortex/);
  assert.throws(() => checkUnnamed([[join(FOUNDER_DIR, "CARTER-QA.md"), "Team Vortex re-ran it."]], loaded.v4), /CARTER-QA\.md names Vortex/);
  // Embedded image data is not text: a run of base64 that happens to spell a name is not a mention.
  checkUnnamed([[join(FOUNDER_DECK_DIR, "figures", "x.svg"), '<image href="data:image/png;base64,QQ+vortex+QQ"/>']], loaded.v4);
});

test("root's P2 (12:55:54Z): the unnamed-team scan reads an SVG as it renders, decoded, and a markdown file as it renders", () => {
  const at = join(FOUNDER_DECK_DIR, "figures", "control.svg");
  const refused = (body) => assert.throws(() => checkUnnamed([[at, body]], loaded.v4), (e) => e instanceof FounderError && /control\.svg names Vortex, who has not consented/.test(e.message), body);
  // Root's two controls: a decimal character reference in the drawn text, a hex one in the label.
  refused('<svg xmlns="http://www.w3.org/2000/svg"><text x="0" y="20">Vor&#116;ex</text></svg>');
  refused('<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Vor&#x74;ex"></svg>');
  // The same name split by markup, behind a comment or CDATA, or in a title, a description or an alt attribute.
  refused('<svg><text>Vor<tspan font-weight="700">tex</tspan></text></svg>');
  refused('<svg><text>Vor<!-- a comment -->tex</text></svg>');
  refused('<svg><text><![CDATA[Vor]]><![CDATA[tex]]></text></svg>');
  refused('<svg><title>V&#111;rtex</title></svg>');
  refused('<svg><desc>VORT&#X45;X</desc></svg>');
  refused('<svg><image alt="&#86;ortex" href="x.png"/></svg>');
  // A markdown file renders character references too.
  assert.throws(() => checkUnnamed([[join(FOUNDER_DIR, "CARTER-QA.md"), "Team Vor&#116;ex re-ran it."]], loaded.v4), /CARTER-QA\.md names Vortex/);
  // No DTD, so no entity it could declare: refused outright, never expanded.
  assert.throws(() => checkUnnamed([[at, '<!DOCTYPE svg [<!ENTITY t "x">]><svg><text>&t;</text></svg>']], loaded.v4), /control\.svg declares a DTD or an entity; it is refused, not expanded/);
  // Binary image data stays out: base64 PNG that happens to spell a name is not a mention.
  checkUnnamed([[at, '<svg><image href="data:image/png;base64,QQ+Vortex+QQ"/></svg>']], loaded.v4);
  // An embedded SVG is text, base64 or percent-encoded: it is decoded and read too.
  refused(`<svg><image href="data:image/svg+xml;base64,${Buffer.from("<svg><text>Vortex</text></svg>").toString("base64")}"/></svg>`);
  refused('<svg><image href="data:image/svg+xml,%3Csvg%3E%3Ctext%3EVor%74ex%3C/text%3E%3C/svg%3E"/></svg>');
  // Root (13:30:15Z): the attribute value is decoded before a data: URI is recognized, so an encoded scheme or parameter
  // cannot hide an embedded SVG; data: URIs in a style element and attributes after a quoted ">" are read too.
  const named = Buffer.from("<svg><text>Vortex</text></svg>").toString("base64");
  refused(`<svg><image href="d&#97;ta:image/svg+xml;base64,${named}"/></svg>`);
  refused(`<svg><image href="data:image/svg+xml;b&#97;se64,${named}"/></svg>`);
  refused('<svg><image href="d&#x61;ta:image/svg+xml,%3Csvg%3E%3Ctext%3EVortex%3C/text%3E%3C/svg%3E"/></svg>');
  refused(`<svg><style>.a{fill:url(data:image/svg+xml;base64,${named})}</style></svg>`);
  refused('<svg><image title="a>b" alt="Vor&#116;ex"/></svg>');
  // Still excluded once decoded: binary image data. And literal CDATA stays literal: it shows "Vor&#116;ex".
  checkUnnamed([[at, '<svg><image href="d&#97;ta:image/png;b&#97;se64,QQ+Vortex+QQ"/></svg>']], loaded.v4);
  checkUnnamed([[at, "<svg><text><![CDATA[Vor&#116;ex]]></text></svg>"]], loaded.v4);
  // One decoding pass, as a renderer makes: an escaped ampersand stays literal text ("Vor&#116;ex" is what shows).
  checkUnnamed([[at, '<svg><text>Vor&amp;#116;ex &lt;b&gt; &quot;q&quot; &apos;a&apos;</text></svg>']], loaded.v4);
});

test("a figure's drawn words are read decoded, as they render, for the public-render rule", async () => {
  const { svgText } = await import("./build-deck-founder.mjs");
  assert.equal(svgText('<svg><text>Cloudfl&#97;re <tspan>AI</tspan></text><text>x&lt;y</text></svg>'), "Cloudflare AI \n x<y");
});

test("CUTS.md proposes a cut of at least 30 spoken words, not applied, that brings the freeze under 5:00 with the demo", async () => {
  const { cutsPlan } = await import("./build-deck-founder.mjs");
  const plan = cutsPlan(loaded);
  assert.ok(plan.saved >= 30, `${plan.saved} words`);
  assert.equal(plan.saved, plan.cut.reduce((a, c) => a + countWords(c.from) - countWords(c.to), 0));
  // Root's arithmetic (12:55:54Z) for now; with the cut, the slot's 5:00 holds at 135 wpm, at the freeze too.
  const clock = Object.fromEntries(plan.clocks.map(([k, u]) => [k, u]));
  assert.deepEqual([clock["Now, draft"].talkWords, clock["Now, draft"].withDemoSeconds, clock["Now, draft"].slowWithDemoSeconds], [400, 295, 312.8]);
  for (const k of ["With the cut, draft", "With the cut, at the freeze (slide 9's no-numbers line)"]) assert.ok(clock[k].slowWithDemoSeconds <= 300, `${k}: ${clock[k].slowWithDemoSeconds} s`);
  // Not applied: the deck speaks every word it did, and no slide, figure or number moves.
  assert.equal(draft.budget.talkWords, 400);
  for (const c of [...plan.cut, ...plan.alternates]) assert.ok(slide(data, c.slide).notes.text.includes(c.from.trim()), c.slide);
  // The document is the build's, with each passage before and after.
  const doc = readFileSync(join(FOUNDER_DIR, "CUTS.md"), "utf8");
  assert.ok(doc.startsWith("# CUTS: a proposed cut of the spoken words, not applied"));
  for (const c of plan.cut) assert.ok(doc.includes(`- Before: "${c.from.trim()}"`) && doc.includes(`After: ${c.after}`), c.slide);
  // The demo sheet runs about 110 s, not 120 (aneta, relayed 13:40Z): CUTS.md stays as root reviewed it, and FILL-IN
  // carries the caveat for every clock figure, in the coordinator's words.
  assert.ok(readFileSync(FOUNDER_OUTPUTS.fillIn, "utf8").includes("## Clock\n\ndemo sheet ≈110 s: subtract 10 s from every clock figure; the timed run decides.\n"));
  assert.ok(fillInTable(draft).includes("demo sheet ≈110 s"));
  // The build refuses a passage that is not there exactly once, or one that touches a number or a placeholder.
  const bad = (mutate, re) => { const v4 = structuredClone(loaded.v4); mutate(v4.cuts); assert.throws(() => cutsPlan({ ...loaded, v4 }), re); };
  bad((k) => { k.cut[0].from = " not in the words"; }, /must appear once in slide room's words, found 0/);
  const counted = / \d[\d,]* messages from \d+ identities/.exec(loaded.v4.slides.find((x) => x.id === "room").say)[0];
  bad((k) => { k.cut.push({ slide: "room", from: counted, to: " Messages", why: "test" }); }, /may not touch a number/);
  bad((k) => { k.cut.push({ slide: "invite", from: " {m:door.visits} visits,", to: "", why: "test" }); }, /may not touch a measured placeholder/);
  bad((k) => { k.cut.push({ slide: "sources", from: "x", to: "", why: "test" }); }, /sources is not a main slide of the full talk/);
});

test("a final build claims no \"measuring\" in any cue or the sheet header, and slide 9's fallback QR is at least 320 px (final-2)", async () => {
  const B = await import("./build-deck-founder.mjs");
  const m = (id, value) => [id, { id, value, display: String(value), definition: "d", scope: "s", window_end: "2026-11-01T14:20:05Z", window: "to 2026-11-01T14:20:05Z", source: "x", from: "METRICS-FREEZE.json" }];
  const freeze = (keys) => variant((v) => { v.build = "final"; }, { sha256: pre.metrics.sha256, byId: new Map([...pre.metrics.byId, ...keys.map((k, i) => m(k, 10 + i))]) });
  for (const [name, keys] of Object.entries({ none: [], some: ["door.visits"], all: ["moltbook.post_votes", "door.visits", "door.agents_passed", "door.view_size"] })) {
    const d = freeze(keys);
    // The coordinator (relayed 14:42Z): the final says what the slide does; no "measuring" claim in a cue or the sheet header.
    for (const s of d.slides) assert.doesNotMatch(s.notes?.cue ?? "", /measuring/i, `${name}: ${s.id}'s cue`);
    assert.equal(typeof B.sheetFillLine, "function", "the sheet header line is the build's");
    assert.doesNotMatch(B.sheetFillLine(d), /measuring/i, name);
    if (name === "none") {
      assert.match(slide(d, "invite").notes.cue, /^No outside numbers at the 14:30 freeze: the slide shows the team board \(plain12\) and the QR\. Don't read numbers from it\. Carter's option, not spoken unless he asks: the D1 layout line/);
      assert.match(B.sheetFillLine(d), /^Not shown: dropped at the freeze \(no receipt\): votes on our Moltbook invitation/);
      // Aneta's P2 (14:41Z): the fallback's QR code at least 320 px on the 1920 canvas (about 240 px on a 1400 px page).
      const section = html(d).split("\n").find((x) => x.includes('id="s-invite"'));
      const qr = /<img [^>]*width="(\d+)"[^>]*data-still="qr"/.exec(section);
      assert.ok(qr && Number(qr[1]) >= 320, `fallback QR width ${qr?.[1]}`);
    }
  }
  // Drafts keep today's wording.
  assert.match(slide(draft, "invite").notes.cue, /until then this slide says "measuring…"/);
  assert.match(B.sheetFillLine(draft), /^Still measuring \(shown as "measuring…"\): /);
});

test("SUBMISSION-INDEX.md: every in-repo entry reads back exactly, and the index has no signed link or declined name", () => {
  const { createHash } = createRequire(import.meta.url)("node:crypto");
  const index = readFileSync(join(REPO_ROOT, "docs", "sentilab", "SUBMISSION-INDEX.md"), "utf8");
  const rows = [...index.matchAll(/^\| [^|]+ \| `([^`]+)` \| ([\d,]+) \| `([0-9a-f]{64})` \|$/gm)];
  assert.ok(rows.length >= 9, `${rows.length} in-repo rows`);
  for (const [, path, bytes, sha] of rows) {
    const b = readFileSync(join(REPO_ROOT, path));
    assert.equal(b.length, Number(bytes.replace(/,/g, "")), path);
    assert.equal(createHash("sha256").update(b).digest("hex"), sha, path);
  }
  // The final PDFs are the ones the deck exports, the handoff files the ones V4.json pins.
  for (const d of [data, buildFounderData(loaded, { slot: "2min" })]) assert.ok(index.includes(`\`docs/sentilab/deck/${founderPdfName(d)}\``), d.deck.slot);
  for (const [f, h] of Object.entries(loaded.v4.handoff)) assert.ok(index.includes(`\`docs/sentilab/deck/founder-v4/${f}\` | ${readFileSync(join(FOUNDER_DIR, f)).length.toLocaleString("en-US")} | \`${h.sha256}\``), f);
  assert.doesNotMatch(index, /[?&](?:sig|se|sv|sp)=|vortex/i);
});

test("Carter's handoff files sit beside the scripts, exactly as received and pinned, and are not slides", () => {
  const pins = { "CARTER-QA.md": "07edabefbbb5296ae617cd3ea0560952b067d7774a43b23201ffe50a79a22982", "DEMO-RUN-SHEET.md": "edd18756a02cf498c4ac5671e4162ecb61623c3924ef0f1b8962405b248c9962" };
  assert.deepEqual(Object.fromEntries(Object.entries(loaded.v4.handoff).map(([f, h]) => [f, h.sha256])), pins);
  assert.equal(handoffFiles(loaded.v4).size, 2);
  for (const f of Object.keys(pins)) assert.ok(existsSync(join(FOUNDER_DIR, f)) && !existsSync(join(FOUNDER_DECK_DIR, f)), f);
  // Root's P2 wording is already in the answer sheet's 2.71-degree row.
  assert.match(readFileSync(join(FOUNDER_DIR, "CARTER-QA.md"), "utf8"), /Within six minutes of our ask, two other teams reported reruns in their own setups, and both reported the same direction/);
  const moved = structuredClone(loaded.v4);
  moved.handoff["CARTER-QA.md"].sha256 = "0".repeat(64);
  assert.throws(() => handoffFiles(moved), /handoff file CARTER-QA\.md is not the file V4\.json pins \(00000000…\)/);
});

test("a measured tile's time window, as the slide prints it", () => {
  assert.equal(windowShown({ window_start: "2026-11-01T07:13:20.235Z", window_end: "2026-11-01T14:20:05Z" }), "Nov 1, 07:13–14:20 UTC");
  assert.equal(windowShown({ window_start: "2026-10-31T13:46:10.752Z", window_end: "2026-11-01T07:39:30.156Z" }), "Oct 31, 13:46 – Nov 1, 07:39 UTC");
  assert.equal(windowShown({ window_end: "2026-11-01T14:20:05Z" }), "as of Nov 1, 14:20 UTC");
  assert.equal(windowShown({ window_start: "2026-10-31T04:55:00.660910+00:00", window_end: "2026-11-01T07:41:05.745Z" }), "Oct 31, 04:55 – Nov 1, 07:41 UTC");
  assert.equal(windowShown({ window: "the door's first hour" }), "the door's first hour");
});
