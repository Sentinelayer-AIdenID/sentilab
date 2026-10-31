// node --test web/test/deck-data.test.mjs
// The SentiLab deck (web/public/sentilab/deck/) shows only what the dated progress packet says:
//   - deck-data.json (and its script copy deck-data.js) is exactly what scripts/build-deck-data.mjs builds from the newest packet;
//   - every fact has a dated source time, and a missing value is PENDING, never a number;
//   - every number on a slide (rendered by deck.js's own renderHtml) exists in deck-data.json, and its source time is on that slide;
//   - the six-case limit sits beside every adapter ratio, on the slides and in the notes;
//   - public-render rules: no internal or vendor names, no agent handles, room numbers, emails or file paths; every time dated.
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";

import { buildFromPacket, newestPacketId, serialize, PENDING } from "../../scripts/build-deck-data.mjs";

const require = createRequire(import.meta.url);
const Deck = require("../public/sentilab/deck/deck.js");
const DIR = new URL("../public/sentilab/deck/", import.meta.url);
const read = (f) => readFileSync(new URL(f, DIR), "utf8");
const data = JSON.parse(read("deck-data.json"));
const html = read("index.html");
const deckMain = html.match(/<main id="deck"[^>]*>([\s\S]*)<\/main>/)[1];
const slidesOf = (h) => [...h.matchAll(/<section\b([^>]*)>([\s\S]*?)<\/section>/g)].map((m) => ({
  id: /\bid="([^"]+)"/.exec(m[1])[1], notes: /\bdata-notes="([^"]+)"/.exec(m[1])?.[1], backup: /class="slide backup"/.test(m[1]), html: m[2],
}));
const rendered = slidesOf(Deck.renderHtml(deckMain, data));
const template = slidesOf(deckMain);
const decode = (s) => s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, "&");
const visible = (h) => decode(h.replace(/<[^>]+>/g, " ")).replace(/\s+/g, " ").trim();
const facts = data.facts;
const notesText = data.notes.map((n) => n.text).join("\n");

// Static, non-data identifiers allowed on a slide: GB10 is the event's hardware name.
const STATIC_IDS = [/\bGB10\b/g];
const NUM = /\d+(?:[.:/]\d+)*/g;
const tokens = (s) => new Set(String(s).match(NUM) ?? []);

const BANNED = [
  // internal and vendor names (hardware named by the event, GB10, is allowed)
  /\bJev\b/i, /\bTypeSafe\b/i, /\bCloudflare\b/i, /\bClaude\b/i, /\bAnthropic\b/i, /\bOpenAI\b/i, /\bGPT/i, /\bQwen\b/i, /\bNeMo\b/i,
  /\bNVIDIA\b/i, /\bGemini\b/i, /\bLlama\b/i, /\bMistral\b/i, /\bDeepSeek\b/i, /\bAzure\b/i, /\bAWS\b/, /\bAscend\b/i, /\bHuawei\b/i,
  /\bOpenResearch\b/i, /\bOpus\b/i, /\bSonnet\b/i, /\bHaiku\b/i, /\bCopilot\b/i, /\bENGRAM\b/i, /\bMicroDuck\b/i, /\bPollen\b/i, /\bReachy\b/i,
  // agent handles and private people/rooms
  /pocket-forge/i, /claude-warden/i, /gpt-astra/i, /\bastra\b/i, /\bwarden\b/i, /\bforge\b/i, /\bnightshift\b/i, /\bcodex\b/i, /\bfable\b/i,
  /\baneta\b/i, /\broot ?0\d\d\b/i, /#\d{4,}/,
  // emails and local/repository file paths
  /[\w.+-]+@[\w-]+\.[a-z]{2,}/i, /\b[A-Za-z]:[\\/]/, /(?:^|[\s"'(=])\/?(?:docs|web|scripts|contracts|sentilab_core|Users|home|tmp)\//,
];
const scan = (text) => BANNED.filter((re) => re.test(text)).map(String);
const PATHLIKE = /\b[\w-]+\.(?:md|mjs|jsonl?|py|pdf|png|ya?ml|toml)\b/i;

test("the banned-term and path scanners can fail", () => {
  for (const s of ["note from claude-warden", "pocket-forge posted", "gpt-astra-carter", "ask Jev", "Cloudflare Worker", "a Qwen model",
    "see #56311", "mail a@b.co", "H:/sl-temp/x", "docs/sentilab/x", "Root 088"]) assert.ok(scan(s).length, s);
  assert.ok(PATHLIKE.test("PAGE-COPY.md"));
  assert.deepEqual(scan("SentiLab on the GB10: the gate accepts reproduced results"), []);
});

test("deck-data is generated from the newest progress packet and is current", () => {
  assert.equal(data.source.packetId, newestPacketId(), "a newer packet exists: run node scripts/build-deck-data.mjs");
  const fresh = serialize(buildFromPacket(data.source.packetId));
  assert.equal(read("deck-data.json"), fresh.json, "deck-data.json differs from a fresh build");
  assert.equal(read("deck-data.js"), fresh.js, "deck-data.js differs from a fresh build");
});

test("every fact has a dated source time, and a missing value shows PENDING", () => {
  assert.equal(data.pending, PENDING);
  for (const [k, f] of Object.entries(facts)) {
    assert.match(f.asOf, /^\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC$/, `${k} asOf`);
    assert.ok(typeof f.source === "string" && f.source.length > 2, `${k} source`);
    if (f.value == null) assert.equal(f.display, PENDING, `${k} has no value, so it must display PENDING`);
    else assert.notEqual(f.display, PENDING, k);
  }
  for (const [name, list] of Object.entries(data.lists)) {
    if (!Array.isArray(list)) continue;
    for (const item of list) assert.match(item.asOf, /^\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC$/, `${name} ${item.id}`);
  }
});

test("every slot in the deck names an existing fact or generator", () => {
  for (const [, key] of deckMain.matchAll(/data-f="([^"]+)"/g)) assert.ok(facts[key], `unknown fact ${key}`);
  for (const [, keys] of deckMain.matchAll(/data-asof="([^"]+)"/g)) for (const k of keys.trim().split(/\s+/)) assert.ok(facts[k], `unknown stamp key ${k}`);
  for (const [, g] of deckMain.matchAll(/data-gen="([^"]+)"/g)) assert.ok(g === "sources" || Deck.GEN[g], `unknown generator ${g}`);
  assert.equal(rendered.length, 7, "five main slides and two backups");
  assert.equal(rendered.filter((s) => s.backup).length, 2);
});

test("the static slide copy carries no numbers of its own", () => {
  const WORDS = /\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|fifty|hundred|thousand)\b/i;
  for (const s of template) {
    let text = visible(s.html.replace(/<svg[\s\S]*?<\/svg>/g, (svg) => svg.replace(/<text[^>]*>([^<]*)<\/text>/g, " $1 ")));
    for (const re of STATIC_IDS) text = text.replace(re, " ");
    assert.deepEqual(text.match(NUM) ?? [], [], `${s.id}: digits in static copy`);
    assert.doesNotMatch(text, WORDS, `${s.id}: a number word in static copy`);
  }
});

test("every number shown on a slide exists in deck-data.json, with its source time on that slide", () => {
  const allowed = new Set();
  const add = (s) => tokens(s).forEach((t) => allowed.add(t));
  for (const f of Object.values(facts)) { add(f.display); add(f.asOf); }
  for (const list of Object.values(data.lists)) {
    if (Array.isArray(list)) for (const item of list) Object.values(item).forEach((v) => (Array.isArray(v) ? v.forEach(add) : add(v)));
    else Object.values(list).forEach(add);
  }
  for (const s of rendered) {
    let text = visible(s.html);
    for (const re of STATIC_IDS) text = text.replace(re, " ");
    for (const t of text.match(NUM) ?? []) assert.ok(allowed.has(t), `${s.id}: "${t}" is shown but not in deck-data.json`);
    for (const [, key] of s.html.matchAll(/data-f="([^"]+)"/g)) {
      assert.ok(text.includes(facts[key].asOf), `${s.id}: ${key} is shown without its source time ${facts[key].asOf}`);
    }
  }
});

test("the six-case limit appears beside every adapter ratio, on slides and in notes", () => {
  const ratio = facts["gb10.adapterExact"].display;
  const caveat = new RegExp(`${facts["gb10.sourceCases"].display} source cases already seen in training`);
  const check = (where, text) => {
    let at = text.indexOf(ratio), n = 0;
    while (at >= 0) {
      n++;
      assert.match(text.slice(at, at + 260), caveat, `${where}: ${ratio} without the six-case limit beside it`);
      at = text.indexOf(ratio, at + 1);
    }
    return n;
  };
  let shown = 0;
  for (const s of rendered) shown += check(s.id, visible(s.html));
  for (const n of data.notes) shown += check(`notes.${n.slide}`, n.text);
  assert.ok(facts["gb10.adapterExact"].value == null || shown >= 2, "the ratio is on the measured slide and in its notes");
  const measured = visible(rendered.find((s) => s.id === "s-measured").html);
  assert.match(measured, /Plumbing, not generalization\./);
  assert.match(measured, /A fixed-sample result, not a universal error bound\./);
});

test("status claims follow the data", () => {
  const status = visible(rendered.find((s) => s.id === "s-status").html);
  assert.ok(status.includes(facts["status.acceptance"].display));
  if (data.lists.deliverables.every((d) => !d.completionVerified)) assert.match(status, /None of the \w+ deliverables is fully accepted\./);
  const correction = visible(rendered.find((s) => s.id === "s-correction").html);
  assert.ok(correction.includes(`Package view · ${facts["packageView.state"].display} · open PR ${facts["packageView.pr"].display}`));
  for (const s of rendered) {
    const text = visible(s.html);
    assert.doesNotMatch(text, /\bdeployed\b/i, `${s.id}: "deployed" is not supported by the data`);
    if (!s.backup) assert.doesNotMatch(text, /\blive\b/i, `${s.id}: nothing on a main slide is called live`);
  }
});

test("public-render rules hold for the page, the data and the notes", () => {
  // Colours are not room numbers: drop SVG fill/stroke values and CSS hex colours before scanning.
  const noColours = (t) => t.replace(/\b(?:fill|stroke)="#[0-9a-f]{3,8}"/gi, "").replace(/points="[^"]*"/g, "");
  const surfaces = {
    "index.html": noColours(html), "deck.js": read("deck.js"), "deck.css": read("deck.css").replace(/#[0-9a-f]{3,8}\b/gi, "#colour"),
    "deck-data.json": read("deck-data.json"), notes: notesText,
  };
  for (const [name, text] of Object.entries(surfaces)) assert.deepEqual(scan(text), [], `${name} breaks a public-render rule`);
  const shownText = [...rendered.map((s) => visible(s.html)), ...[...html.matchAll(/\b(?:alt|title|aria-label)="([^"]*)"/g)].map((m) => m[1]), notesText];
  for (const t of shownText) assert.doesNotMatch(t, PATHLIKE, "a file name is shown");
  const strings = [];
  const walk = (v) => (typeof v === "string" ? strings.push(v) : v && typeof v === "object" && Object.values(v).forEach(walk));
  walk(data);
  for (const s of strings) assert.doesNotMatch(s, PATHLIKE, `deck-data string looks like a file name: ${s}`);
});

test("every time shown or spoken is dated and in UTC", () => {
  const FULL = /\b\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC\b/g;
  for (const [where, text] of [...rendered.map((s) => [s.id, visible(s.html)]), ["notes", notesText], ["deck-data", read("deck-data.json")]]) {
    const rest = text.replace(FULL, " ");
    assert.doesNotMatch(rest, /\b\d{1,2}:\d{2}\b/, `${where}: a time without its date and UTC`);
    assert.doesNotMatch(rest, /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/, `${where}: a raw ISO timestamp`);
  }
});

test("speaker notes exist for every slide and fit a 30-35 second slot", () => {
  const bySlide = new Map(data.notes.map((n) => [n.slide, n]));
  for (const s of rendered) {
    const n = bySlide.get(s.notes);
    assert.ok(n && n.text.length > 40, `${s.id}: notes`);
    if (!s.backup) {
      const words = n.text.split(/\s+/).length;
      assert.ok(words >= 60 && words <= 95, `${s.id}: ${words} words is not 30-35 s of speech`);
    }
  }
  const factTokens = new Set(Object.values(facts).flatMap((f) => [...tokens(f.display)]));
  let spoken = notesText;
  for (const re of STATIC_IDS) spoken = spoken.replace(re, " ");
  for (const t of spoken.match(NUM) ?? []) assert.ok(factTokens.has(t), `notes say "${t}", which is not a fact`);
});

test("images exist and are described", () => {
  for (const [, src] of html.matchAll(/<img\b[^>]*\bsrc="([^"]+)"/g)) assert.ok(existsSync(new URL(src, DIR)), src);
  for (const [tag] of html.matchAll(/<img\b[^>]*>/g)) assert.match(tag, /\balt="[^"]{20,}"/);
});
