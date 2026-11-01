// node --test web/test/package3d-copy.test.mjs
// The Package view's copy before the production door opens (aneta #57911, root's reply 08:30:43Z in room 608657e4):
//   1. "independently verified" never appears: a same-build replay in a fresh process is reproduced, not independent. The
//      page prints the contract's summary verbatim only in the door's new words ("reproduced by a fresh-process replay",
//      "no score" for a failed run), and a failed run reads "no score" whatever an older API says.
//   2. Honest limits carries root's known-limit text, and nothing implies a 1.39% temperature error.
//   3. The REPRODUCED chip is neutral: reproduced alone is not a beat (the API emits no beat verdict, and both current
//      runs fail the active guard). Green stays for an explicit beat verdict, which never fires today.
//   4. User-agent classes never become counts of humans or verified agents in the page's copy.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import * as door from "../public/sentilab/package/source3d.mjs";
import * as status from "../public/sentilab/package/status.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const PKG = join(here, "..", "public", "sentilab", "package");
const read = (f) => readFileSync(join(PKG, f), "utf8");
const API = JSON.parse(readFileSync(join(here, "door-api-d1b09d12.json"), "utf8")).responses;
const item = (page, status_) => structuredClone(API[page].body.items.find((x) => x.status === status_));
// Root's known-limit text (gpt-astra-carter, room 608657e4, reply to #57911 at 08:30:43Z). The reply as stored has no
// space next to any number (also "At08:30Z", "main57911"); a single space is restored between a word and a number only,
// as the start Forge quoted it; every number keeps its unit as written.
const KNOWN_LIMIT = "Known limit: for the saved 45mm/grid64 CPU-DRAM reference case, the source-defined ambient-boundary sum exceeds 680W input by 9.4449W (about 1.39%), beyond the 0.429424W allowance for saved-temperature rounding. This is a saved-field consistency finding, not physical calibration; the cause in the deployed binary has not been established. Current results are diagnostic.";

test("1: \"independently verified\" never appears; the door's new summaries print verbatim; a failed run reads \"no score\"", () => {
  for (const f of readdirSync(PKG)) assert.doesNotMatch(read(f), /independently verified/i, f);
  // The API as recorded still says "independently verified" for a reproduced run: the page does not print it.
  const reproduced = door.normalizeItem(item("results_reproduced", "reproduced")).layout;
  assert.equal(API.results_reproduced.body.items[0].summary, "independently verified", "the recorded API's old word");
  assert.equal(reproduced.summary, null, "never kept");
  assert.equal(status.summaryLine(reproduced), null, "never shown");
  assert.equal(status.stateLine(reproduced), "Reproduced");
  // The door's new words (forge's door PR: states.py SUMMARY), one field of a recorded item changed: printed verbatim.
  const fresh = door.normalizeItem({ ...item("results_reproduced", "reproduced"), summary: "reproduced by a fresh-process replay" }).layout;
  assert.equal(status.summaryLine(fresh), "contract state: reproduced by a fresh-process replay");
  const failedNew = door.normalizeItem({ ...item("results_all", "failed"), summary: "no score" }).layout;
  assert.equal(status.summaryLine(failedNew), "contract state: no score");
  // A failed run reads "no score" even when an older API calls it "evaluated".
  const failedOld = door.normalizeItem(item("results_all", "failed")).layout;
  assert.equal(API.results_all.body.items.find((x) => x.status === "failed").summary, "evaluated", "the recorded API's old word");
  assert.equal(status.summaryLine(failedOld), "contract state: no score");
  assert.equal([status.stateLine(failedOld), status.summaryLine(failedOld)].join(" · "), "Failed: the scorer returned an error · contract state: no score");
  // The other summaries still print as the API words them.
  for (const [s, summary] of [["queued", "queued"], ["not_reproduced", "evaluated"]]) {
    const L = door.normalizeItem({ ...item(s === "queued" ? "results_queued_page2" : "results_not_reproduced", s), summary }).layout;
    assert.equal(status.summaryLine(L), `contract state: ${summary}`, s);
  }
});

test("2: Honest limits carries root's known-limit text, and nothing implies a 1.39% temperature error", () => {
  const html = read("index.html");
  const limits = html.slice(html.indexOf('<dialog id="limits"'), html.indexOf("</dialog>", html.indexOf('<dialog id="limits"')));
  assert.ok(limits.includes(`<li>${KNOWN_LIMIT}</li>`), "root's text, verbatim, as one item of Honest limits");
  for (const f of readdirSync(PKG)) {
    const text = read(f);
    assert.doesNotMatch(text, /1\.39\s*%[^.]*\b(temperature|°C)\b[^.]*\berror\b|temperature error|error of 1\.39/i, f);
  }
  assert.equal(html.split("1.39%").length - 1, 1, "the figure appears once, inside root's sentence");
});

test("3: the REPRODUCED chip is neutral; green stays for an explicit beat verdict, which never fires today", () => {
  const d = read("door.mjs");
  const chips = d.slice(d.indexOf("const STATUS_CHIP"), d.indexOf("});", d.indexOf("const STATUS_CHIP")));
  assert.match(chips, /reproduced: \["neutral", "REPRODUCED"\]/);
  assert.match(chips, /cross_checked: \["neutral", "CROSS-CHECKED"\]/);
  assert.doesNotMatch(chips, /"won"/, "no run state is styled as a win");
  assert.match(read("package.css"), /\.chip\.neutral \{[^}]+\}/);
});

test("4: user-agent classes never become counts of humans or verified agents", () => {
  for (const f of ["index.html", "door.mjs", "status.mjs", "package.js"]) {
    const text = read(f);
    assert.doesNotMatch(text, /\b(humans|people|visitors|persons|verified agents|unique (?:humans|agents|visitors))\b/i, f);
  }
  // The page groups nothing by class: a class is shown only beside its own short id.
  const d = read("door.mjs");
  assert.doesNotMatch(d, /\.filter\(\(\w+\) => \w+\.cls ===|countBy|groupBy|\.cls\]\s*\+=|byClass/, "no count per class");
});
