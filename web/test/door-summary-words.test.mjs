// node --test web/test/door-summary-words.test.mjs
// One contract across the API and the page: the "summary" the door's open feeds give each run (app/door/service.py
// FEED_SUMMARY, on every results, board and status item) and the words the Package view reads and prints verbatim
// (web/public/sentilab/package/source3d.mjs SUMMARIES) are the same set. The page then shows every summary the API can
// give and nothing else, and neither side can drift alone. Neither says "independently verified": what ran is the same
// pinned build replayed in a fresh process (aneta #57911, root's reply 08:30:43Z).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { SUMMARIES } from "../public/sentilab/package/source3d.mjs";

const REPO = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const SERVICE = readFileSync(join(REPO, "app", "door", "service.py"), "utf8");
// The contract's lifecycle (open_proposals/contract/states.py LIFECYCLE); app/test_door_terms.py checks FEED_SUMMARY
// covers exactly these on the Python side.
const STATES = ["rejected", "queued", "held", "evaluating", "evaluated", "failed", "replaying", "reproduced", "not_reproduced",
  "cross_checked", "cancelled", "expired"];

// FEED_SUMMARY's literal in service.py, as { state: word, or null for None }.
function feedSummary(source) {
  const start = source.indexOf("FEED_SUMMARY = {");
  if (start === -1) return null;
  const body = source.slice(start, source.indexOf("}", start) + 1);
  return Object.fromEntries([...body.matchAll(/"([a-z_]+)": (?:"([^"\\]*)"|None)/g)].map((m) => [m[1], m[2] ?? null]));
}

// Every way the two sides disagree: [] when they are one contract.
function drift(source, pageWords) {
  const words = feedSummary(source);
  if (!words) return ["service.py has no FEED_SUMMARY literal"];
  const found = [];
  const keys = Object.keys(words).sort();
  if (JSON.stringify(keys) !== JSON.stringify([...STATES].sort())) found.push(`states: ${keys.join(", ")}`);
  const api = [...new Set(Object.values(words).filter((w) => w !== null))].sort();
  const page = [...pageWords].sort();
  for (const w of api) if (!page.includes(w)) found.push(`the API says "${w}", which the page does not read`);
  for (const w of page) if (!api.includes(w)) found.push(`the page reads "${w}", which the API never says`);
  for (const w of [...api, ...page]) if (/independently/i.test(w)) found.push(`"${w}"`);
  return found;
}

test("the API's feed summaries are exactly the words the Package view reads", () => {
  assert.deepEqual(drift(SERVICE, SUMMARIES), []);
  const words = feedSummary(SERVICE);
  assert.equal(words.reproduced, "reproduced by a fresh-process replay");
  assert.equal(words.failed, "no score");
  assert.equal(words.cancelled, null);
});

test("negative control: a word changed on either side, a missing state or the old word is caught", () => {
  assert.ok(drift(SERVICE.replace('"failed": "no score"', '"failed": "evaluated"'), SUMMARIES).length, "the API's failed word");
  assert.ok(drift(SERVICE, SUMMARIES.map((w) => (w === "no score" ? "no result" : w))).length, "the page's word");
  assert.ok(drift(SERVICE.replace(/"expired": None,?\s*/, ""), SUMMARIES).length, "a state dropped");
  assert.ok(drift(SERVICE.replaceAll("reproduced by a fresh-process replay", "independently verified"),
    SUMMARIES.map((w) => (w === "reproduced by a fresh-process replay" ? "independently verified" : w))).length, "the old word on both sides");
  assert.ok(drift(SERVICE.replace("FEED_SUMMARY = {", "WORDS = {"), SUMMARIES).length, "no literal to read");
});
