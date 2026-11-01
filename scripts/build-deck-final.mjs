#!/usr/bin/env node
// Builds the SentiLab talk deck for the five-minute slot (deck/final-5min/) from its one reviewed source,
// docs/sentilab/deck/final-5min/FINAL.json: eight main slides, one figure each where the source names one (the last is
// the live-demo door), then backup. The figures are the contributed SVGs kept byte for byte in final-5min/figures/;
// the build applies only the text edits FINAL.json declares, and writes the served copies to deck/final-5min/figures/.
//
//   node scripts/build-deck-final.mjs                                   # the result recorded in FINAL.json (gate.result),
//                                                                       # or NOT RUN when none is recorded
//   node scripts/build-deck-final.mjs --rederived                       # the same, with the status line flipped to
//                                                                       # "independently re-derived" once the second reviewer confirms
//   node scripts/build-deck-final.mjs --demo-status staging|live|replay # the live-demo slide's honest status line
//                                                                       # (staging by default; live is refused while the
//                                                                       # agent door's address is a placeholder in FINAL.json)
//   node scripts/build-deck-final.mjs --gate not-run                    # force an outcome: marked REVIEW on every slide, no PDF
//   node scripts/build-deck-final.mjs --gate fail --measured 77.10,116.02
//   node scripts/build-deck-final.mjs --gate pass --preview             # renders only: no values, marked PREVIEW, no PDF
//   node scripts/build-deck-final.mjs --check                           # exit 1 if the committed data or figures differ from a fresh build
//   ... --cutoff 2026-11-01T12:30:00Z    declare a later fact cutoff (every dated fact must be at or before it)
//   ... --refresh-prs --cutoff <time>    re-read the listed pull requests with gh and stamp them; refused without an
//                                        explicit --cutoff, because a refresh makes only those rows current
//   ... --export [--shots <dir>]         then run export-deck-pdf.mjs --deck final (needs PLAYWRIGHT_DIR)
//
// One flag, --gate, chooses the slide-4 outcome; without it the build uses the reviewed result in FINAL.json. The three
// wordings were fixed in FINAL.json before the result existed, and the build refuses an outcome its measured values
// contradict: PASS needs both values within the tolerance of their published references, FAIL needs at least one outside
// it, NOT RUN takes no values. The gate code can also return ERROR or INCOMPLETE; neither has reviewed wording, so
// neither builds. When the recorded result is shown, slide 4 also carries its figure, its scope and its verification
// state: "verified by the operator" until --rederived says a second reviewer has re-derived it. Any other outcome is a
// review render: every slide says so, and it never exports a PDF.
//
// Outside teams are named only with consent. Each team in FINAL.json has one consent line, null until the team's yes is
// on record ("<room> seq <n> at <time>"). Without it, slide text reads "an outside team" ("a second outside team" for the
// next one on the same slide), the figures carry the anonymous labels FINAL.json declares, and the build refuses any
// slide, note or figure that still holds the name. Credit stays "as reported by them" either way.
//
// Rules for the data:
//   - Every dated line, figure time and tile names at least one room record, and its displayed minute is the minute of
//     one of those records (the post time, or a time the record states). Nothing is dated after the cutoff.
//   - Timing (root, team room 57481): the talk before the door, counted at 150 words a minute, plus its transitions must
//     fit the 180 s talk cap; the door's spoken lines count inside the 120 s live-demo clock; talk and demo fit the 300 s
//     slot. The slower 2.2 words a second is reported beside it.
//   - Every rendered string, figure text included, passes the shared public-render rules, plus this deck's own: no dollar
//     figure outside the "By the numbers" slide, no "deck due", no "source unknown", no "bug", and no internal jargon on
//     the main slides.
//   - The numbers slide quotes its values and their MEASURED or ESTIMATE labels from the quant pack kept in the
//     repository, whose sha256 FINAL.json records.
//   - A figure must be inert (no script, foreignObject, event handler or external reference) and its text at least
//     24 px in its own units, which the slide's scale keeps at 22 px or more.
// The build is deterministic: it reads no clock unless --refresh-prs is given, so a rebuild gives the same bytes.
import { createHash } from "node:crypto";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { DECK_ROOT, PDF_DIR, REPO_ROOT, PacketError, publicText } from "./build-deck-data.mjs";
import { validateSchema } from "./json-schema-lite.mjs";

// The five-minute deck (talk plus live demo) is this script's only output. The dated three-minute deck it replaced
// (final-3min/ and deck/final/, exported at 2026-11-01 00:12 UTC) is preserved byte for byte: the tests pin every file,
// and the export script refuses to write any of them.
export const FINAL_DIR = join(PDF_DIR, "final-5min");
export const FINAL_SOURCE = join(FINAL_DIR, "FINAL.json");
export const FINAL_SCHEMA = join(FINAL_DIR, "FINAL.schema.json");
export const FIGURE_SOURCE_DIR = join(FINAL_DIR, "figures");
export const FINAL_DECK_DIR = join(DECK_ROOT, "final-5min");
export const FIGURE_OUT_DIR = join(FINAL_DECK_DIR, "figures");
export const FINAL3_DIR = join(PDF_DIR, "final-3min");
export const FINAL3_DECK_DIR = join(DECK_ROOT, "final");
export const FROZEN_FINAL_3MIN = {
  "deck/final/index.html": "55d194815d775207ce48fee67886c8494583c41fe71950feb458ec721266e1f3",
  "deck/final/deck.js": "3468fe4142696732a188e53da69530ea25618a3c0222bac27b62d649784868e2",
  "deck/final/deck.css": "fef75e0a3572d74becb5883cbfddd55acd0f3b8b4bccaf419db170c665fbd493",
  "deck/final/deck-data.json": "22df59b7729542ab737c0608fffefcc7d9f8d27f42ea4ea7a63bc8975569e774",
  "deck/final/deck-data.js": "b6a43148e3255e4371b8e601c9398cbe9b7c3670019fe22a4b88688d37fc793d",
  "docs/sentilab/deck/final-3min/FINAL.json": "2bd9a0416fe2508c3f875f8ea573f36dc300b9e9521c8307c92a2d388295c501",
  "docs/sentilab/deck/final-3min/FINAL.schema.json": "ac722d150bc22ea569d6c7ab56cfc50b5ddec8ae75742494823ddf02c2e514e3",
  "docs/sentilab/deck/final-3min/TIMELINE-VERIFY.md": "db2b16a4e5272387380968119a8046fbb490a807183d5ab2bc935d3bc08fbfce",
  "docs/sentilab/deck/final-3min/RE-EXPORT.md": "1cb848ca33c3de26de3c528192c5b3024d8c4a078364ccaf2770abca2f5e1063",
  "docs/sentilab/deck/final-3min/SentiLab-3min-2026-11-01-0012-pass.pdf": "b72a8761108b4634f324b06f2fe2b9eaf0d32bbc1320a04db21a1a1c31d4f814",
  "docs/sentilab/deck/final-3min/variants/slide4-fail-1920x1080.png": "2e9dff8e012f1e7b10c106cc08e311af3451f656f987ad3c5d3a01c3eae45cc1",
  "docs/sentilab/deck/final-3min/variants/slide4-not-run-1920x1080.png": "14b9adf12c4326f6df5e3c42220c9ecedfa056f8c468dd28485d4fec7f594ac2",
  "docs/sentilab/deck/final-3min/variants/slide4-pass-1920x1080.png": "d068bcd55560ac2c8403b98c3427e6ada2e9754cbfb7603a94417addfd8288da",
};
export const FINAL_FORMAT = "sentilab-deck-final/1";
export const DATA_SCHEMA = "sentilab-deck-final-data/2";
export const GATES = ["not-run", "pass", "fail"];
export const PR_REPO = "Sentinelayer-AIdenID/sentilab";

export class FinalError extends Error {}

// ── wording rules ───────────────────────────────────────────────────────────────────────────────────────────────────
// Banned in every rendered string of this deck (on top of the shared NOT_PUBLIC list).
// "+1" and hardware model names are banned on public slides (team room 56383): say "approved" and "our local workstation".
export const FINAL_BANNED = [
  /\$\s?\d/, /\bUSD\b/i, /\bdollars?\b/i, /\bdeck due\b/i, /\bsource unknown\b/i, /\bbugs?\b/i,
  /(^|[\s(])\+1(?!\d|[.,]\d)/, /\bGB10\b/i,
];
// Money may appear only on the "By the numbers" slide, where every value carries a MEASURED label and a caveat (Carter
// asked for money to be quantified), and on the plain talk's "Why it matters" slide while its numbers are on stage;
// everywhere else a dollar figure still stops the build.
export const MONEY = new Set([FINAL_BANNED[0], FINAL_BANNED[1], FINAL_BANNED[2]]);
export const moneyAllowed = (slide) => slide?.id === "numbers" || (slide?.content?.layout === "why" && Boolean(slide.content.numbers));
export const DEMO_STATUSES = ["staging", "live", "replay"];
// Internal jargon kept off the main slides (backup slides may name pull requests and verdict codes).
export const PLAIN_WORDS = [
  /merged_source_verified/i, /\bP[0-3]\b/, /\bCSP\b/, /\bblobs?\b/i, /\bgrid-?64\b/i, /\bnative6\b/i, /finite controls/i,
  /\bSHA\b/i, /\bseq\b/i, /\bPR\b/, /\bCI\b/, /\bJSON\b/, /\bMCP\b/, /\bCLI\b/, /\bheadroom\b/i, /\bfixture\b/i, /\bslab-?\d/i,
];
// A figure is an inert picture: none of these may appear in its SVG.
export const SVG_ACTIVE = [
  [/<script\b/i, "a script element"], [/<foreignObject\b/i, "a foreignObject"], [/\son[a-z]+\s*=/i, "an event-handler attribute"],
  [/javascript:/i, "a javascript: URL"], [/<!ENTITY|<!DOCTYPE/i, "a DTD or entity"], [/<\?xml-stylesheet/i, "an xml-stylesheet"],
  [/@import/i, "a CSS @import"], [/<(?:iframe|embed|object|audio|video|canvas|animate\w*|set|handler|listener)\b/i, "an active element"],
  [/(?:xlink:)?href\s*=\s*["'](?!#|data:image\/(?:png|jpeg);base64,)/i, "a reference that is not a fragment or an embedded PNG or JPEG"],
  [/url\(\s*["']?(?!#)/i, "a url() that is not a fragment"],
];
export const FIGURE_MIN_FONT = 24;
export const FIGURE_MIN_RENDERED_FONT = 22;
const CONTROL = /[\u0000-\u0008\u000b-\u001f\u007f-\u009f]/;

// ── formatting ──────────────────────────────────────────────────────────────────────────────────────────────────────
const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");
const ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/;
function time(iso, where) {
  if (typeof iso !== "string" || !ISO.test(iso) || Number.isNaN(Date.parse(iso))) throw new FinalError(`${where}: not a UTC time: ${JSON.stringify(iso)}`);
  return Date.parse(iso);
}
export const utcStamp = (iso) => `${iso.slice(0, 10)} ${iso.slice(11, 16)} UTC`;
export const hhmm = (iso) => iso.slice(11, 16);
const minuteOf = (iso) => iso.slice(0, 16);
export const short = (sha) => (typeof sha === "string" && /^[0-9a-f]{40}$/.test(sha) ? sha.slice(0, 8) : null);
const xmlEscape = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const xmlText = (s) => String(s).replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;|&apos;/g, "'").replace(/&amp;/g, "&");

// Words: whitespace-separated tokens that hold a letter or digit ("closed-form" is one word, "·" none).
export function countWords(text) {
  return String(text).split(/\s+/).filter((t) => /[\p{L}\p{N}]/u.test(t)).length;
}
const tenths = (x) => Math.round(x * 10) / 10;
// Seconds at the checked pace (150 words a minute, root's rule) and at the slower 2.2 words a second, for the report.
export function speech(text, talk) {
  const words = countWords(text);
  return { text, words, seconds: tenths(words / (talk.checkWordsPerMinute / 60)), slowSeconds: tenths(words / talk.slowWordsPerSecond) };
}

// ── gate outcome ────────────────────────────────────────────────────────────────────────────────────────────────────
const DECIMAL = /^\d{1,3}\.\d{1,3}$/;
export function parseMeasured(value) {
  if (value == null) return null;
  const parts = String(value).split(",").map((s) => s.trim());
  if (parts.length !== 2 || !parts.every((p) => DECIMAL.test(p))) {
    throw new FinalError(`--measured takes two temperatures in C, layout A then layout B, like 75.61,116.02 (got ${JSON.stringify(value)})`);
  }
  return parts;
}
// Thousandths of a kelvin, as integers, so the tolerance comparison has no float error.
const milli = (s) => { const [w, f = ""] = String(s).split("."); return Number(w) * 1000 + Number((f + "000").slice(0, 3)); };
export function checkOutcome(gate, measured, references, toleranceK, { preview = false } = {}) {
  if (!GATES.includes(gate)) {
    throw new FinalError(`--gate must be one of ${GATES.join(", ")} (got ${JSON.stringify(gate)}); ERROR and INCOMPLETE have no reviewed wording`);
  }
  if (gate === "not-run") {
    if (measured) throw new FinalError("NOT RUN takes no measured values");
    return null;
  }
  if (!measured) {
    if (preview) return null;
    throw new FinalError(`${gate.toUpperCase()} needs --measured with both values (or --preview, which never exports a PDF)`);
  }
  const tol = milli(toleranceK);
  const misses = references.map((r, i) => Math.abs(milli(measured[i]) - milli(r.publishedC)) > tol);
  if (gate === "pass" && misses.some(Boolean)) throw new FinalError(`PASS contradicts the values: ${measured.join(", ")} are not all within ${toleranceK} K of ${references.map((r) => r.publishedC).join(", ")}`);
  if (gate === "fail" && !misses.some(Boolean)) throw new FinalError(`FAIL contradicts the values: ${measured.join(", ")} are all within ${toleranceK} K; a FAIL for another reason needs reviewed wording first`);
  return references.map((r, i) => ({ id: r.id, publishedC: r.publishedC, measuredC: measured[i], within: !misses[i] }));
}
export const formatValues = (measured) => `${measured[0]} C and ${measured[1]} C`;
// Signed difference in kelvin at the measured value's precision, with a true minus sign: "0.00 K", "−0.01 K".
export function signedDiff(measured, published) {
  const places = Math.max((measured.split(".")[1] ?? "").length, (published.split(".")[1] ?? "").length);
  const d = milli(measured) - milli(published);
  const abs = (Math.abs(d) / 1000).toFixed(places);
  return `${d < 0 && Number(abs) !== 0 ? "−" : d > 0 ? "+" : ""}${abs} K`;
}
// The version comparator's text must state the rounded gaps to the paper that its own values give.
export function checkComparator(comparator, references) {
  const gaps = comparator.values.map((v, i) => Math.round((milli(v) - milli(references[i].publishedC)) / 1000));
  const lo = Math.min(...gaps), hi = Math.max(...gaps);
  const want = `${lo} to ${hi} K`;
  if (!comparator.text.includes(want)) throw new FinalError(`the version comparison must say "${want}", which its values give`);
  if (!comparator.values.every((v) => comparator.text.includes(`${v} C`))) throw new FinalError("the version comparison must quote both of its values");
  if (!comparator.notes.includes(`${lo} to ${hi} degrees`)) throw new FinalError(`the version comparison's notes must say "${lo} to ${hi} degrees"`);
}
// The reviewer's common slide-4 wording is one paragraph; the figure-led cut shows its link sentences on the stack slide
// and its test sentence on slide 4, each verbatim.
export function splitCommon(common) {
  const at = common.indexOf("Test fixed in advance:");
  if (at <= 0) throw new FinalError("the common slide-4 wording must end with its \"Test fixed in advance:\" sentence");
  return { link: common.slice(0, at).trim(), test: common.slice(at).trim() };
}

// ── source ──────────────────────────────────────────────────────────────────────────────────────────────────────────
export function loadFinal(path = FINAL_SOURCE, schemaPath = FINAL_SCHEMA) {
  const bytes = readFileSync(path);
  const schemaBytes = readFileSync(schemaPath);
  if (bytes.includes(13) || schemaBytes.includes(13)) throw new FinalError("FINAL.json and its schema must use LF line endings");
  const final = JSON.parse(bytes.toString("utf8"));
  if (final.format !== FINAL_FORMAT) throw new FinalError(`unknown deck source format ${JSON.stringify(final.format)}: this builder reads only ${FINAL_FORMAT}`);
  const errors = validateSchema(JSON.parse(schemaBytes.toString("utf8")), final);
  if (errors.length) throw new FinalError(`FINAL.json fails its schema:\n- ${errors.join("\n- ")}`);
  return { final, hashes: { finalSha256: sha256(bytes), schemaSha256: sha256(schemaBytes) } };
}

// Every dated claim names its records; its minute must be one the records carry.
function checkRecords(item, where, cutoffMs) {
  if (!item.records?.length) throw new FinalError(`${where} has no room record`);
  const minutes = new Set();
  for (const [k, r] of item.records.entries()) {
    const at = time(r.at, `${where} record ${k + 1}`);
    if (at > cutoffMs) throw new FinalError(`${where} record ${k + 1} is after the cutoff`);
    minutes.add(minuteOf(r.at));
    if (r.stated != null) {
      if (time(r.stated, `${where} record ${k + 1} stated time`) > at) throw new FinalError(`${where} record ${k + 1} states a time after it was posted`);
      minutes.add(minuteOf(r.stated));
    }
  }
  if (item.at != null) {
    if (time(item.at, where) > cutoffMs) throw new FinalError(`${where} is dated after the cutoff`);
    if (!minutes.has(minuteOf(item.at))) throw new FinalError(`${where} shows ${hhmm(item.at)}, which no record carries (${[...minutes].map((m) => m.slice(11)).join(", ")})`);
  }
}
function checkOrdered(items, where) {
  for (let i = 1; i < items.length; i++) if (items[i].at < items[i - 1].at) throw new FinalError(`${where} is out of time order at line ${i + 1}`);
}
// A stated duration must be what its two record times give: "round" to the minute ("39 min", "1 h 41"), or "under" a bound.
export function checkDuration(text, fromIso, toIso, rule, where) {
  const minutes = (time(toIso, where) - time(fromIso, where)) / 60000;
  if (minutes <= 0) throw new FinalError(`${where}: ${JSON.stringify(text)} runs backwards`);
  const m = /^(?:Under )?(?:(\d+) h )?(\d+)(?: min)?$/.exec(text);
  if (!m) throw new FinalError(`${where}: cannot read the duration ${JSON.stringify(text)}`);
  const stated = Number(m[1] ?? 0) * 60 + Number(m[2]);
  const ok = rule === "under" ? minutes < stated : Math.round(minutes) === stated;
  if (!ok) throw new FinalError(`${where}: ${JSON.stringify(text)} is not what the records give (${minutes.toFixed(2)} min)`);
}

// ── outside teams ───────────────────────────────────────────────────────────────────────────────────────────────────
const CONSENT = /^([0-9a-f]{8}) seq (\d{5,6}) at (\S+)$/;
export function parseConsent(line, where) {
  if (line == null) return null;
  const m = CONSENT.exec(line);
  if (!m) throw new FinalError(`${where}: consent must read "<room> seq <n> at <UTC time>" (got ${JSON.stringify(line)})`);
  time(m[3], where);
  return { room: m[1], seq: Number(m[2]), at: m[3] };
}
const ORDINAL = ["an", "a second", "a third", "a fourth", "a fifth", "a sixth", "a seventh", "an eighth"];
const TOKEN = /\{(repo:)?([A-Za-z]+)\}/g;
// Resolves {delfie}, {Delfie} (sentence start) and {repo:feagent} across one slide: a named team by its name, an unnamed
// one as "an outside team", then "a second outside team" for the next unnamed team on the same slide, in team order.
export function teamResolver(teams, named) {
  const order = Object.keys(teams);
  return (strings) => {
    const mentioned = new Set();
    for (const s of strings) for (const m of s.matchAll(TOKEN)) {
      const id = m[2].toLowerCase();
      if (!Object.hasOwn(teams, id)) throw new FinalError(`unknown team token ${m[0]}`);
      mentioned.add(id);
    }
    const anon = order.filter((id) => mentioned.has(id) && !named.has(id));
    return (s) => s.replace(TOKEN, (_, repo, raw) => {
      const id = raw.toLowerCase();
      if (repo) return named.has(id) ? teams[id].repo : "public repository";
      if (named.has(id)) return teams[id].name;
      const phrase = `${ORDINAL[anon.indexOf(id)]} outside team`;
      return /^[A-Z]/.test(raw) ? phrase[0].toUpperCase() + phrase.slice(1) : phrase;
    });
  };
}
// Applies a resolver to every string inside a value.
const mapStrings = (v, fn) => (typeof v === "string" ? fn(v) : Array.isArray(v) ? v.map((x) => mapStrings(x, fn))
  : v && typeof v === "object" ? Object.fromEntries(Object.entries(v).map(([k, x]) => [k, mapStrings(x, fn)])) : v);
const allStrings = (v, out = []) => { if (typeof v === "string") out.push(v); else if (v && typeof v === "object") Object.values(v).forEach((x) => allStrings(x, out)); return out; };
// Team names are proper nouns: matched case-sensitively, as whole words ("Axis" the team, not "the axis is linear").
const nameIn = (name, text) => new RegExp(`(^|[^\\p{L}\\p{N}])${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![\\p{L}\\p{N}])`, "u").test(text);

// ── figures ─────────────────────────────────────────────────────────────────────────────────────────────────────────
// Replaces one text node exactly: the source must hold it once, between ">" and "<".
function replaceTextNode(svg, from, to, where) {
  const needle = `>${xmlEscape(from).replace(/&quot;/g, '"')}<`;
  const n = svg.split(needle).length - 1;
  if (n !== 1) throw new FinalError(`${where}: the text ${JSON.stringify(from)} must appear exactly once, found ${n}`);
  return svg.replace(needle, `>${xmlEscape(to).replace(/&quot;/g, '"')}<`);
}
export const svgTexts = (svg) => [...svg.matchAll(/<text\b[^>]*>([\s\S]*?)<\/text>/g)].map((m) => xmlText(m[1].replace(/<[^>]+>/g, "")).replace(/\s+/g, " ").trim()).filter(Boolean);
export function svgActive(svg) { return SVG_ACTIVE.filter(([re]) => re.test(svg)).map(([, what]) => what); }
export function buildFigure(id, fig, options) {
  const bytes = readFileSync(join(FIGURE_SOURCE_DIR, fig.file));
  if (sha256(bytes) !== fig.sha256) throw new FinalError(`figure ${id} (${fig.file}) is not the reviewed file: its sha256 differs from FINAL.json`);
  return buildFigureFrom(bytes, id, fig, options);
}
// The figure rules on given bytes: inert, the declared edits only, consent, the accessible label, the type floor.
export function buildFigureFrom(bytes, id, fig, { teams, named, cutoffMs }) {
  const where = `figure ${id} (${fig.file})`;
  let svg = bytes.toString("utf8");
  const active = svgActive(svg);
  if (active.length) throw new FinalError(`${where} is not inert: it holds ${active.join(", ")}`);
  // A figure its author drew for one consent set (aneta's v1.6 fig6) is served byte for byte, its own label included;
  // it is only valid while the consent on record is that set, so any change stops the build until it is redrawn.
  if (fig.drawnFor) {
    const want = [...fig.drawnFor].sort().join(", "), have = [...named].sort().join(", ");
    if (want !== have) throw new FinalError(`${where} is drawn for the consent set [${want}], but consent is on record for [${have}]: ask for it redrawn`);
  }
  for (const e of fig.edits) svg = replaceTextNode(svg, e.from, e.to, where);
  for (const t of fig.teamText) if (!named.has(t.team)) svg = replaceTextNode(svg, t.from, t.anon, where);
  // The accessible label is this deck's own reviewed text, so no name or vendor rides in an attribute; a byte-exact
  // figure keeps its author's label, which the checks below and the slide's public rules then read like any text.
  const label = /<svg\b[^>]*?\saria-label="([^"]*)"/.exec(svg);
  if (!label) throw new FinalError(`${where} has no aria-label on its root`);
  if (!fig.keepLabel) svg = svg.replace(/(<svg\b[^>]*?\saria-label=")[^"]*(")/, `$1${xmlEscape(fig.alt)}$2`);
  const alt = fig.keepLabel ? xmlText(label[1]) : fig.alt;
  for (const [tid, team] of Object.entries(teams)) {
    if (!named.has(tid) && nameIn(team.name, svg.replace(/data:image\/(?:png|jpeg);base64,[A-Za-z0-9+/=]+/g, ""))) throw new FinalError(`${where} still names ${team.name}, who has not consented`);
  }
  const sizes = [...svg.matchAll(/font-size\s*[:=]\s*["']?\s*([\d.]+)/g)].map((m) => Number(m[1]));
  const minFont = Math.min(...sizes);
  if (!(minFont >= FIGURE_MIN_FONT)) throw new FinalError(`${where} has text at ${minFont} px, under the ${FIGURE_MIN_FONT} px figure floor`);
  if (minFont * fig.scale < FIGURE_MIN_RENDERED_FONT - 1e-9) throw new FinalError(`${where} at scale ${fig.scale} shows ${minFont * fig.scale} px text, under ${FIGURE_MIN_RENDERED_FONT} px`);
  const texts = svgTexts(svg);
  for (const c of fig.claims ?? []) {
    if (!texts.some((t) => new RegExp(`(^|\\D)${c.label}(\\D|$)`).test(t))) throw new FinalError(`${where} has no time label ${c.label}`);
    if (hhmm(c.at) !== c.label) throw new FinalError(`${where}: the label ${c.label} is not its claim's minute ${hhmm(c.at)}`);
    checkRecords(c, `${where} label ${c.label}`, cutoffMs);
  }
  if (fig.claims) checkOrdered(fig.claims, where);
  for (const d of fig.durations ?? []) {
    const at = (label) => fig.claims.find((c) => c.label === label)?.at;
    if (!texts.some((t) => t.includes(d.text))) throw new FinalError(`${where} does not show ${JSON.stringify(d.text)}`);
    checkDuration(d.text, at(d.from), at(d.to), d.rule, `${where} ${d.from} to ${d.to}`);
  }
  if (fig.records) checkRecords({ records: fig.records }, where, cutoffMs);
  const out = Buffer.from(svg, "utf8");
  if (fig.keepLabel && !out.equals(bytes)) throw new FinalError(`${where} must be served byte for byte`);
  return { svg: out, meta: { src: `figures/${fig.file}`, sha256: sha256(out), width: fig.width, height: fig.height, scale: fig.scale, minFont, alt, texts } };
}

// ── build ───────────────────────────────────────────────────────────────────────────────────────────────────────────
export function buildFinalData({ final, hashes }, options = {}) {
  const { cutoff = null, preview = false, rederived = false, demoReview = false } = options;
  // The plain talk's door is LIVE or REPLAY, REPLAY until warden's production readback shows LIVE is true.
  const demoStatus = options.demoStatus ?? (final.plainTalk ? "replay" : "staging");
  if (!DEMO_STATUSES.includes(demoStatus)) throw new FinalError(`--demo-status must be one of ${DEMO_STATUSES.join(", ")} (got ${JSON.stringify(demoStatus)})`);
  // A demo review render (--demo-review) shows a door variant before it is true: marked on every slide, never a PDF.
  if (demoStatus === "live" && final.demo.urlIsPlaceholder && !demoReview) throw new FinalError("the demo cannot say live while the agent door's address is still a placeholder in FINAL.json");
  if (!final.demo.instruction.includes(final.demo.url)) throw new FinalError("the demo instruction must name the door's address");
  const recorded = final.gate.result ?? null;
  // Without --gate, the reviewed result recorded in FINAL.json decides; without one, NOT RUN.
  const gate = options.gate ?? recorded?.outcome ?? "not-run";
  const measured = options.measured ?? (recorded && gate === recorded.outcome && !preview ? recorded.measured : null);
  const cut = cutoff ?? final.cutoff;
  const cutoffMs = time(cut, "cutoff");
  if (time(final.cutoff, "FINAL.json cutoff") > cutoffMs) throw new FinalError("--cutoff cannot be earlier than the reviewed cutoff in FINAL.json");
  const values = parseMeasured(measured);
  const outcome = checkOutcome(gate, values, final.gate.references, final.gate.toleranceK, { preview });
  if (preview && gate === "not-run") throw new FinalError("--preview is for PASS and FAIL renders only");
  // The recorded result shows (with its figure, scope and verification state) only when this build is that result.
  const showResult = Boolean(recorded && !preview && gate === recorded.outcome && values && values.join(",") === recorded.measured);
  // Any other outcome, once a result is recorded, is a review render of slide 4's wording: marked, never exported.
  const reviewOnly = Boolean(recorded && !preview && !showResult);
  if (rederived && !showResult) throw new FinalError("--rederived applies only to the reviewed result recorded in FINAL.json");
  if (recorded) {
    checkRecords(recorded, "the recorded gate result", cutoffMs);
    checkOutcome(recorded.outcome, parseMeasured(recorded.measured), final.gate.references, final.gate.toleranceK);
    checkComparator(recorded.comparator, final.gate.references);
  }
  const verification = showResult ? recorded.verification[rederived ? "rederived" : "operator"] : null;
  const talk = final.talk;
  const B = final.backup;

  // Outside teams: named only where consent is on record before the cutoff. The generated data lists the named teams
  // with the record of their consent, and only counts the rest, so not even an id gives an unnamed team away.
  const named = new Set();
  const teamData = { named: [], unnamed: 0 };
  for (const [id, t] of Object.entries(final.teams)) {
    const consent = parseConsent(t.consent, `team ${id} consent`);
    if (consent && time(consent.at, `team ${id} consent`) > cutoffMs) throw new FinalError(`team ${id}'s consent is dated after the cutoff`);
    if (consent) { named.add(id); teamData.named.push({ name: t.name, consent }); } else teamData.unnamed++;
  }
  const resolver = teamResolver(final.teams, named);

  // Figures, built once; each slide that shows one carries its metadata and its text for the checks.
  const figures = {};
  const figureFiles = new Map();
  for (const [id, fig] of Object.entries(final.figures)) {
    const f = buildFigure(id, fig, { teams: final.teams, named, cutoffMs });
    figures[id] = f.meta;
    figureFiles.set(fig.file, f.svg);
  }
  const figureView = (id) => ({ id, ...figures[id] });
  // Stills: raster screenshots of our own views, served byte for byte (a PNG holds no script and no text to check).
  const stills = {};
  for (const [id, st] of Object.entries(final.stills ?? {})) {
    const bytes = readFileSync(join(FIGURE_SOURCE_DIR, st.file));
    if (sha256(bytes) !== st.sha256) throw new FinalError(`still ${id} (${st.file}) is not the reviewed file: its sha256 differs from FINAL.json`);
    if (bytes.subarray(0, 8).toString("hex") !== "89504e470d0a1a0a" || bytes.readUInt32BE(16) !== st.width || bytes.readUInt32BE(20) !== st.height) {
      throw new FinalError(`still ${id} (${st.file}) must be a ${st.width}x${st.height} PNG`);
    }
    stills[id] = { id, src: `figures/${st.file}`, sha256: st.sha256, width: st.width, height: st.height, alt: st.alt };
    figureFiles.set(st.file, bytes);
  }

  // Records and times.
  final.how.steps.forEach((s, i) => checkRecords(s, `backup how-it-works step ${i + 1}`, cutoffMs));
  checkRecords(final.how.evidence, "the review line", cutoffMs);
  if (final.how.evidence.line !== B.reviews.line) throw new FinalError("the review line must be the same on slide 5 and in backup");
  checkRecords(final.problem, "slide 1", cutoffMs);
  checkRecords(final.stack, "slide 2", cutoffMs);
  final.timeline.tiles.forEach((t, i) => {
    checkRecords(t, `slide 3 tile ${i + 1}`, cutoffMs);
    if (t.from) checkDuration(t.value, t.from, t.to, t.rule, `slide 3 tile ${i + 1}`);
    if (t.at && hhmm(t.at) !== t.value) throw new FinalError(`slide 3 tile ${i + 1} shows ${t.value}, not its record minute ${hhmm(t.at)}`);
  });
  checkRecords(final.checks.study, "the seeded-test card", cutoffMs);
  if (!final.checks.study.texts[final.checks.study.status]) throw new FinalError(`the seeded-test card has no text for its status ${final.checks.study.status}`);
  B.chronology.rows.forEach((r, i) => checkRecords(r, `chronology row ${i + 1}`, cutoffMs));
  checkOrdered(B.chronology.rows, "the chronology");
  checkRecords(B.reviews, "the review-quality line", cutoffMs);
  checkRecords(final.demo, "the demo slide", cutoffMs);
  checkRecords(B.receipt, "the outside-team backup", cutoffMs);
  checkRecords(B.gb10, "the GB10 backup", cutoffMs);
  if (B.qa) checkRecords(B.qa, "the questions backup", cutoffMs);
  // Layer maxima (root, team room 57511): the reviewed sentence's "about" values and the "within 0.44 K" line must be
  // what the table's own rows give.
  checkRecords(B.layers, "the layer-maxima backup", cutoffMs);
  const about = /about ([\d.]+) K and ([\d.]+) K/.exec(B.layers.sentence)?.slice(1).map(Number);
  const spreaders = B.layers.rows.filter((r) => r.kind === "spreader");
  if (!about || spreaders.length !== 2 || !spreaders.every((r, i) => r.values.slice(2).every((x) => Math.abs(Number(x) - about[i]) <= 0.0151))) {
    throw new FinalError("the layer-maxima sentence's \"about\" values must be the finite-element spreader-minus-sink rows");
  }
  const within = Number(/within ([\d.]+) K/.exec(B.layers.chip)?.[1]);
  for (const r of B.layers.rows.filter((x) => x.kind === "chip")) {
    const [hs6, , ours, theirs] = r.values.map(Number);
    if (!(Math.max(Math.abs(hs6 - ours), Math.abs(hs6 - theirs)) <= within + 1e-9)) throw new FinalError(`${r.label}: the finite-element solves are not within ${within} K of HotSpot 6.0`);
  }
  const { link: linkText, test: testText } = splitCommon(final.gate.common);
  if (final.stack.text !== linkText) throw new FinalError("slide 2 must carry the reviewer's link sentences word for word");
  // "By the numbers": at most four values, each MEASURED or ESTIMATE with its caveat, read from a hashed quant pack; or,
  // until that pack exists, an empty slide that says plainly it is a placeholder.
  const N = final.numbers;
  if (N.placeholder) {
    if (N.items.length || N.source) throw new FinalError("a placeholder numbers slide carries no numbers and no source");
  } else {
    if (!N.items.length || N.items.length > 4) throw new FinalError("the numbers slide takes one to four numbers");
    if (!N.source) throw new FinalError("the numbers slide must name the quant pack it was read from");
    if (time(N.source.readAt, "the quant pack read time") > cutoffMs) throw new FinalError("the quant pack was read after the cutoff");
    // The pack is kept in the repository byte for byte; every value and its label must be the pack's own.
    const packBytes = readFileSync(join(REPO_ROOT, N.source.path));
    if (sha256(packBytes) !== N.source.sha256) throw new FinalError(`the quant pack at ${N.source.path} is not the one the slide was read from`);
    // One entry per headline, "**N. <value> <label>…**"; a value must open a headline ("360–720 h" opens "360–720 engineer-hours").
    const entries = packBytes.toString("utf8").split(/\n(?=\*\*\d+\. )/).filter((e) => /^\*\*\d+\. /.test(e));
    for (const x of N.items) {
      // A later re-read posted in the room (warden's recount and cost read) names its record instead of the pack.
      if (x.record) { checkRecords({ records: [x.record] }, `the numbers slide value ${JSON.stringify(x.value)}`, cutoffMs); continue; }
      const entry = entries.find((e) => e.replace(/^\*\*\d+\. /, "").startsWith(`${x.value.replace(/ h$/, "")} `));
      if (!entry) throw new FinalError(`the numbers slide value ${JSON.stringify(x.value)} is not in the quant pack`);
      if (!entry.includes(`- ${x.class}.`)) throw new FinalError(`the numbers slide labels ${JSON.stringify(x.value)} ${x.class}, but the quant pack does not`);
    }
  }
  for (const r of final.gate.wordingRecords) if (time(r.at, "slide 4 wording record") > cutoffMs) throw new FinalError("the slide 4 wording record is after the cutoff");
  for (const c of B.status.cards) {
    if (time(c.asOf, `status card ${c.title}`) > cutoffMs) throw new FinalError(`status card ${c.title} is dated after the cutoff`);
    if (c.originAt != null && time(c.originAt, `status card ${c.title} origin`) > time(c.asOf, `status card ${c.title}`)) throw new FinalError(`status card ${c.title} originates after its as-of time`);
  }
  for (const p of B.prs.items) {
    if (time(p.checkedAt, `PR ${p.number}`) > cutoffMs) throw new FinalError(`PR ${p.number} was checked after the cutoff`);
    if ((p.state === "MERGED") !== Boolean(p.merge && p.mergedAt)) throw new FinalError(`PR ${p.number}: a merged state needs its merge commit and time, and only then`);
    if (p.mergedAt && time(p.mergedAt, `PR ${p.number} merge`) > time(p.checkedAt, `PR ${p.number}`)) throw new FinalError(`PR ${p.number} merged after it was checked`);
  }

  // Slide 4: the reviewed wording for the chosen outcome, values filled in.
  const v = final.gate.variants[gate];
  const fill = (s) => (s.includes("[values]") && values ? s.replaceAll("[values]", formatValues(values)) : s);
  const variantText = fill(v.text);
  const variantNotes = showResult ? `${recorded.notes} ${verification.notes} ${recorded.teamsNotes}` : fill(v.notes);
  const gateTitle = final.gate.title;
  if (!/differs between versions/.test(gateTitle)) throw new FinalError("slide 4 must say the link differs between versions");

  const pr = (n) => B.prs.items.find((p) => p.number === n);
  const prLine = (p) => p.state === "MERGED"
    ? { state: "merged", text: `merged as ${short(p.merge)} at ${utcStamp(p.mergedAt)}`, checked: `checked ${utcStamp(p.checkedAt)}` }
    : { state: p.state.toLowerCase(), text: `${p.state.toLowerCase()} at head ${short(p.head)}`, checked: `checked ${utcStamp(p.checkedAt)}` };
  const gatePr = pr(56);
  if (!gatePr) throw new FinalError("the PR list must include #56, the gate-zero code");
  const rows = final.gate.references.map((r, i) => ({
    label: r.label, source: r.source, publishedC: r.publishedC,
    result: gate === "not-run" ? "not run" : outcome ? `${outcome[i].measuredC} C` : "[measured]",
    diff: outcome ? `${signedDiff(outcome[i].measuredC, r.publishedC)} · ${outcome[i].within ? "within" : "outside"}` : "",
    tone: gate === "not-run" ? "muted" : outcome ? (outcome[i].within ? "ok" : "warn") : "muted",
  }));

  // Slides, before the team names are resolved slide by slide.
  const raw = [
    { id: "problem", main: true, kicker: final.problem.kicker, notes: final.problem.notes, content: {
      title: final.problem.title, figure: figureView(final.problem.figure), line: final.problem.line, caption: final.problem.caption } },
    { id: "stack", main: true, kicker: final.stack.kicker, notes: final.stack.notes, content: {
      title: final.stack.title, figure: figureView(final.stack.figure), text: final.stack.text, credit: final.stack.credit, caption: final.stack.caption } },
    { id: "timeline", main: true, kicker: final.timeline.kicker, notes: final.timeline.notes, content: {
      title: final.timeline.title, figure: figureView(final.timeline.figure),
      tiles: final.timeline.tiles.map((t) => ({ value: t.value, label: t.label })), caption: final.timeline.caption } },
    { id: "gate", main: true, kicker: final.gate.kicker, notes: variantNotes, content: {
      title: gateTitle, toleranceK: final.gate.toleranceK, variant: gate, label: v.label, text: variantText, bottom: final.gate.bottom,
      // With the recorded result: its figure, the test sentence, a one-line table, the verification state and the scope.
      // Any other outcome keeps the reviewer's full common wording and the table.
      figure: showResult ? figureView(final.gate.figure) : null,
      common: showResult ? null : final.gate.common,
      test: showResult ? testText : null,
      rows,
      verification: showResult ? verification.text : null,
      scope: showResult ? recorded.scope : null,
      figureCaption: showResult ? recorded.figureCaption : null } },
    { id: "checks", main: true, kicker: final.checks.kicker, notes: final.checks.notes, content: {
      title: final.checks.title, figure: figureView(final.checks.figure), line: final.how.evidence.line, attribution: final.how.evidence.attribution, caption: final.checks.caption,
      study: { title: final.checks.study.title, status: final.checks.study.status, text: final.checks.study.texts[final.checks.study.status] } } },
    { id: "teams", main: true, kicker: final.teamsSlide.kicker, notes: final.teamsSlide.notes, content: {
      title: final.teamsSlide.title, figure: figureView(final.teamsSlide.figure), caption: final.teamsSlide.caption } },
    { id: "numbers", main: true, kicker: N.kicker, notes: N.notes, content: {
      title: N.title, placeholder: N.placeholder ? N.placeholderText : null,
      // The tile shows the pack's class unless the source gives a plainer tag ("POSTED SO FAR" for a total still posting).
      items: N.items.map((x, i) => ({ n: String(i + 1), value: x.value, label: x.label, class: x.class, tag: x.tag ?? x.class, caveat: x.caveat })) } },
    { id: "demo", main: true, kicker: final.demo.kicker, notes: `${final.demo.notes} ${final.demo.statuses[demoStatus].notes}`, content: {
      title: final.demo.title, instruction: final.demo.instruction, urlNote: final.demo.urlIsPlaceholder ? final.demo.urlNote : null,
      diagram: final.demo.diagram, status: demoStatus, statusText: final.demo.statuses[demoStatus].text,
      // REPLAY shows the 3D still in place of the instruction and the six steps (warden reads production back at 18:45).
      still: demoStatus === "replay" && stills.view3d ? { ...stills.view3d, label: B.view3d?.label ?? null } : null } },
    { id: "how", main: false, kicker: "Backup · how the team works", notes: "Backup. If asked how the team works, walk the four steps; each has a dated example.", content: {
      title: final.how.title, footnote: final.how.footnote, evidence: null,
      steps: final.how.steps.map((s) => ({ title: s.title, text: s.text, today: s.today })) } },
    { id: "chronology", main: false, kicker: B.chronology.kicker, notes: "Backup. If asked how the day unfolded, walk this table; every line is a room record.", content: {
      title: B.chronology.title, note: B.chronology.note, rows: B.chronology.rows.map((r) => ({ at: hhmm(r.at), text: r.text })) } },
    { id: "reviews", main: false, kicker: B.reviews.kicker, notes: "Backup. If asked whether the agents really check each other, read the line as written, with its qualifier.", content: {
      title: B.reviews.title, line: B.reviews.line, attribution: B.reviews.attribution, rows: B.reviews.rows, caveats: B.reviews.caveats } },
    { id: "metrics", main: false, kicker: B.metrics.kicker, notes: "Backup. If asked for the numbers, separate saved output from the simplified model; neither is a calibrated temperature.", content: B.metrics },
    ...(B.view3d && stills.view3d ? [{ id: "view3d", main: false, kicker: B.view3d.kicker, notes: "Backup. A replay of our 3D package view: simulated, not silicon.", content: {
      title: B.view3d.title, label: B.view3d.label, caption: B.view3d.caption, still: stills.view3d } }] : []),
    { id: "profile", main: false, kicker: B.profile.kicker, notes: "Backup. The same layer profile as a line chart, both layouts; modeled nodes, not a copper layer.", content: {
      title: B.profile.title, figure: figureView(B.profile.figure), caption: B.profile.caption } },
    { id: "layers", main: false, kicker: B.layers.kicker, notes: "Backup. Independently located layer maxima beside both versions; read the sentence as written, and the cause stays open.", content: {
      title: B.layers.title, head: B.layers.head, rows: B.layers.rows.map((r) => ({ label: r.label, values: r.values })),
      sentence: B.layers.sentence, chip: B.layers.chip, note: B.layers.note, caption: B.layers.caption } },
    { id: "gate-detail", main: false, kicker: B.gate.kicker, notes: "Backup. If asked how the test works, read the rules; the three wordings were written before any result.", content: {
      title: B.gate.title, rules: B.gate.rules, source: B.gate.source, wordingTitle: B.gate.wordingTitle,
      status: { pr: 56, ...prLine(gatePr) },
      result: showResult ? { label: v.label, values: formatValues(values), verification: verification.text, detail: recorded.detail, comparator: recorded.comparator.text } : null,
      wordings: GATES.map((g) => ({ gate: g, label: final.gate.variants[g].label, text: final.gate.variants[g].text, chosen: g === gate })) } },
    { id: "drill", main: false, kicker: B.drill.kicker, notes: "Backup. This is a test fixture with illustrative values; it shows the designed mechanism, not a result.", content: B.drill },
    { id: "status", main: false, kicker: B.status.kicker, notes: "Backup. Where it stands: no deliverable is fully accepted, and scientific benefit is not established.", content: {
      title: B.status.title, deliverables: B.status.deliverables,
      cards: B.status.cards.map((c) => ({ title: c.title, text: c.text,
        origin: c.originAt ? `origin ${utcStamp(c.originAt)}` : "origin time not recorded", asOf: `as of ${utcStamp(c.asOf)}` })) } },
    { id: "gb10", main: false, kicker: B.gb10.kicker, notes: "Backup. If asked about our local workstation, give the wall times and say what they do not show.", content: {
      title: B.gb10.title, rows: B.gb10.rows, lines: B.gb10.lines } },
    { id: "prs", main: false, kicker: B.prs.kicker, notes: "Backup. Pull request states at the check time; merged ones show their merge commit.", content: {
      title: B.prs.title, repo: B.prs.repo,
      // One check time for the table when every row shares it; otherwise each row keeps its own.
      checked: new Set(B.prs.items.map((p) => p.checkedAt)).size === 1 ? `checked ${utcStamp(B.prs.items[0].checkedAt)}` : null,
      rows: B.prs.items.map((p) => ({ number: `#${p.number}`, what: p.what, ...prLine(p) })) } },
    { id: "receipt", main: false, kicker: B.receipt.kicker, notes: "Backup. The outside-team receipts in full, and why our own leaderboard is not used as evidence.", content: {
      title: B.receipt.title, facts: B.receipt.facts, notYet: B.receipt.notYet, notEvidence: B.receipt.notEvidence,
      names: namesLine(final.teams, named) } },
    // Last, so the End key reaches it during questions: plain answers, the "unvalidated" one in the coordinator's words.
    ...(B.qa ? [{ id: "qa", main: false, kicker: B.qa.kicker, notes: B.qa.notes, content: { title: B.qa.title, items: B.qa.items } }] : []),
  ];
  // With the plain talk, its slides lead and the whole earlier deck follows as backup.
  if (final.plainTalk) raw.splice(0, raw.length, ...plainTalkSlides(final.plainTalk, { figureView, stills, demo: final.demo, demoStatus }), ...raw.map((s) => ({ ...s, main: false })));
  // Team names, resolved per slide (content and notes together), then the notes counted.
  const slides = raw.map((s) => {
    const resolve1 = resolver([...allStrings(s.content), s.notes]);
    return { id: s.id, main: s.main, kicker: s.kicker, notes: speech(resolve1(s.notes), talk), content: mapStrings(s.content, resolve1) };
  });
  const mains = slides.filter((s) => s.main).length;
  let b = 0;
  slides.forEach((s, i) => { s.label = s.main ? `${i + 1} / ${mains}` : `B${++b}`; });

  // Timing, root's rule: the talk before the door at 150 words a minute plus transitions within the talk cap; the door
  // lines inside the live-demo clock; talk cap and demo within the slot.
  const door = slides.find((s) => s.main && (s.content.layout === "door" || s.id === "demo"));
  const talkSlides = slides.filter((s) => s.main && s !== door);
  const talkWords = talkSlides.reduce((n, s) => n + s.notes.words, 0);
  const talkSeconds = tenths(talkWords / (talk.checkWordsPerMinute / 60));
  const talkSlowSeconds = tenths(talkWords / talk.slowWordsPerSecond);
  if (tenths(talkSeconds + talk.transitionSeconds) > talk.talkCapSeconds) {
    throw new FinalError(`the talk needs ${talkSeconds} s at ${talk.checkWordsPerMinute} words a minute plus ${talk.transitionSeconds} s of transitions, over the ${talk.talkCapSeconds} s cap`);
  }
  if (door.notes.seconds > talk.demoSeconds) throw new FinalError(`the door lines need ${door.notes.seconds} s, more than the ${talk.demoSeconds} s demo clock`);
  if (talk.talkCapSeconds + talk.demoSeconds > talk.maxSeconds) throw new FinalError("the talk cap and the demo exceed the slot");

  const data = {
    schema: DATA_SCHEMA,
    deck: { ...final.deck, cutoff: utcStamp(cut), variant: gate, variantLabel: v.label, preview, reviewOnly, demoReview, demoStatus, plain: Boolean(final.plainTalk) },
    budget: {
      checkWordsPerMinute: talk.checkWordsPerMinute, slowWordsPerSecond: talk.slowWordsPerSecond,
      talkWords, talkSeconds, talkSlowSeconds, transitionSeconds: talk.transitionSeconds, talkCapSeconds: talk.talkCapSeconds,
      doorWords: door.notes.words, doorSeconds: door.notes.seconds, doorSlowSeconds: door.notes.slowSeconds,
      liveSeconds: tenths(talk.demoSeconds - door.notes.seconds), demoSeconds: talk.demoSeconds, maxSeconds: talk.maxSeconds,
    },
    teams: teamData,
    slides,
    build: { gate, measured: values ? values.join(",") : null, cutoff: cut, preview, rederived, demoStatus, demoReview },
    source: { ...hashes },
  };
  checkRendered(data, final.teams, named);
  Object.defineProperty(data, "figureFiles", { value: figureFiles, enumerable: false });
  return data;
}
// ── the plain-language talk ─────────────────────────────────────────────────────────────────────────────────────────
// Carter presents and must be able to defend every sentence (team room 57563, 02:51). When FINAL.json carries a
// "plainTalk" block, its slides are the main path: the script's titles on the slides and its "Say" text as the notes,
// exactly, one picture each. Every slide of the earlier deck follows as backup with its technical text intact, so
// nothing true is lost. No K, kelvin, formula, grid or "statistic" may appear on a main slide, in its notes or in its
// figure.
export const PLAIN_TALK_BANNED = [/\d\s?K\b/, /\bkelvin\b/i, /\brz\b/, /convection/i, /\bgrid\b/i, /\bstatistic\b/i, /native block/i, /chiplet-centre/i];
export function plainTalkSlides(PT, { figureView, stills, demo, demoStatus }) {
  return PT.slides.map((t) => {
    if (t.door) {
      if (!["live", "replay"].includes(demoStatus)) throw new FinalError(`the plain door has LIVE and REPLAY only (got ${JSON.stringify(demoStatus)})`);
      const live = demoStatus === "live";
      return { id: t.id, main: true, kicker: t.kicker, notes: t.say[demoStatus], content: {
        layout: "door", title: t.title, status: demoStatus, statusText: demo.statuses[demoStatus].text,
        instruction: live ? demo.instruction : null, urlNote: live && demo.urlIsPlaceholder ? demo.urlNote : null,
        // REPLAY shows the 3D still, labelled like slide 1's: "simulated, not silicon" stays visible wherever a 3D-view
        // temperature appears (root, team room reply to 57608, 03:40:48).
        diagram: live ? demo.diagram : null,
        still: live ? null : stills[t.picture?.still ?? "view3d"] ? { ...stills[t.picture?.still ?? "view3d"], label: t.picture?.label ?? null } : null } };
    }
    if (t.numbers) {
      return { id: t.id, main: true, kicker: t.kicker, notes: PT.numbersOnStage ? `${t.sayNumbers} ${t.say}` : t.say, content: {
        layout: "why", title: t.title, numbers: PT.numbersOnStage ? t.numbers : null } };
    }
    const st = t.picture?.still ? { ...stills[t.picture.still], label: t.picture.label ?? null } : null;
    if (t.picture?.still && !stills[t.picture.still]) throw new FinalError(`plain slide ${t.id} names a missing still ${t.picture.still}`);
    // A figure alone on its slide may be drawn larger than its backup use; never smaller than the type floor allows.
    let figure = t.picture?.figure ? figureView(t.picture.figure) : null;
    if (figure && t.picture.scale !== undefined) {
      if (figure.minFont * t.picture.scale < FIGURE_MIN_RENDERED_FONT - 1e-9) {
        throw new FinalError(`plain slide ${t.id}: ${figure.id} at scale ${t.picture.scale} shows ${figure.minFont * t.picture.scale} px text, under ${FIGURE_MIN_RENDERED_FONT} px`);
      }
      figure = { ...figure, scale: t.picture.scale };
    }
    return { id: t.id, main: true, kicker: t.kicker, notes: t.say, content: {
      layout: "talk", title: t.title, figure, still: st, caption: t.caption ?? null } };
  });
}
// The backup line on names, from the consent flags alone.
export function namesLine(teams, named) {
  const yes = Object.keys(teams).filter((id) => named.has(id)).map((id) => teams[id].name);
  if (!yes.length) return "No outside team is named on these slides until it agrees to be named.";
  const no = Object.keys(teams).length - yes.length;
  return `Named with their consent, on record in the help room: ${yes.join(", ")}.${no ? ` The ${no === 1 ? "other team is" : `other ${no} teams are`} not named until they agree.` : ""}`;
}

// Every string a slide or its notes can show, with the slide it sits on; a figure's text and label count as its slide's.
export function renderedStrings(data) {
  const out = [];
  const walk = (v, slide) => {
    if (typeof v === "string") out.push({ slide, text: v });
    else if (Array.isArray(v)) v.forEach((x) => walk(x, slide));
    else if (v && typeof v === "object") Object.entries(v).forEach(([k, x]) => { if (!["src", "sha256", "id"].includes(k)) walk(x, slide); });
  };
  for (const s of data.slides) { walk(s.content, s); walk(s.kicker, s); walk(s.notes.text, s); }
  for (const k of ["title", "event", "talk", "cutoff", "variantLabel"]) out.push({ slide: null, text: data.deck[k] });
  return out;
}
export function checkRendered(data, teams = {}, named = new Set()) {
  for (const { slide, text } of renderedStrings(data)) {
    const where = slide ? `slide ${slide.id}` : "deck";
    if (CONTROL.test(text)) throw new FinalError(`${where}: a control character in ${JSON.stringify(text)}`);
    if (/\{(?:repo:)?[A-Za-z]+\}/.test(text)) throw new FinalError(`${where}: an unresolved team token in ${JSON.stringify(text)}`);
    let shown;
    try { shown = publicText(text, where); } catch (e) { if (e instanceof PacketError) throw new FinalError(e.message); throw e; }
    if (shown !== text) throw new FinalError(`${where}: the public-render rules would rewrite ${JSON.stringify(text)}; write it plainly instead`);
    const bad = FINAL_BANNED.find((re) => re.test(text) && !(MONEY.has(re) && moneyAllowed(slide)));
    if (bad) throw new FinalError(`${where}: ${bad} is not allowed in this deck: ${JSON.stringify(text)}`);
    // The plain-language talk carries no physics arithmetic or simulator internals on a main slide or in its notes.
    if (data.deck.plain && slide?.main) {
      const tech = PLAIN_TALK_BANNED.find((re) => re.test(text));
      if (tech) throw new FinalError(`${where}: the plain talk keeps technical detail in backup, but ${tech} matches ${JSON.stringify(text)}`);
    }
    if (slide?.main) {
      const jargon = PLAIN_WORDS.find((re) => re.test(text));
      if (jargon) throw new FinalError(`${where}: main slides use plain words, but ${jargon} matches ${JSON.stringify(text)}`);
    }
    // A team without consent is named nowhere on a slide, in its notes or in a figure (the event's own name is the
    // deck's, not a slide's).
    if (slide) for (const [id, t] of Object.entries(teams)) {
      if (!named.has(id) && nameIn(t.name, text)) throw new FinalError(`${where}: ${t.name} has not consented to be named: ${JSON.stringify(text)}`);
    }
  }
}

// The speaker script, word for word as the deck renders it: one section per main slide with its words and seconds at the
// checked pace, the door's status lines, and the clock. Written beside FINAL.json as SCRIPT.md.
export function speakerScript(data, final, { label = "review export" } = {}) {
  const u = data.budget;
  const at = (w) => `${tenths(w / (u.checkWordsPerMinute / 60))} s`;
  const names = data.teams.named.map((t) => `${t.name} (help room, message ${t.consent.seq})`);
  const out = [
    `# Speaker script, five-minute deck, ${label} ${data.deck.cutoff}`,
    "",
    `The spoken words, exactly as the deck renders them from FINAL.json (sha256 ${data.source.finalSha256.slice(0, 8)}…)${final.plainTalk ? ", the main slides from the plain-language script in PLAIN-SCRIPT.md; every slide of the earlier five-minute deck is backup and is not spoken" : ""}. ${names.length ? `Named with consent: ${names.join(", ")}.` : "No team has consented yet."} Every other team reads "an outside team". ${final.plainTalk ? "Slide 5's pass test" : "Slide 4"} is the recorded ${data.deck.variantLabel}${data.build.measured ? ` (${data.build.measured.replace(",", " and ")})` : ""}${data.build.rederived ? ", with the completed re-derivation" : ""}.`,
    "",
    `Clock (root, team room 57481): the talk before the door is capped at ${u.talkCapSeconds} s at ${u.checkWordsPerMinute} words a minute, transitions included. The door lines count inside the ${u.demoSeconds} s live demo.`,
  ];
  const slowWpm = Math.round(u.slowWordsPerSecond * 60);
  for (const s of data.slides.filter((x) => x.main)) {
    const n = s.label.split(" ")[0];
    const fig = s.content.figure ? ` (${s.content.figure.id})` : s.content.still ? ` (${s.content.still.id})` : "";
    out.push("", `## ${n}. ${s.content.title}${fig}`, "");
    if (s.content.layout === "door") {
      // The plain door: one of two scripted lines, whichever warden's production readback shows is true.
      const t = final.plainTalk.slides.find((x) => x.door);
      for (const st of ["live", "replay"]) out.push(`Say (${st.toUpperCase()}): ${t.say[st]}`, "", `${countWords(t.say[st])} words, ${at(countWords(t.say[st]))} at ${u.checkWordsPerMinute} wpm.`, "");
      out.push(`Inside the ${u.demoSeconds} s demo clock. This export shows ${data.deck.demoStatus.toUpperCase()}: ${u.doorWords} words, ${u.doorSeconds} s, leaving ${u.liveSeconds} s for the demo itself.`);
      continue;
    }
    if (s.id !== "demo") {
      out.push(s.notes.text, "", `${s.notes.words} words, ${at(s.notes.words)} at ${u.checkWordsPerMinute} wpm.`);
      if (s.content.layout === "why") {
        const t = final.plainTalk.slides.find((x) => x.numbers);
        out.push("", `The numbers line is ${final.plainTalk.numbersOnStage ? "on" : "off"} in this export. ${final.plainTalk.numbersOnStage ? "Without it" : "With it"}, the slide would say: "${final.plainTalk.numbersOnStage ? t.say : `${t.sayNumbers} ${t.say}`}"`);
      }
      continue;
    }
    const base = final.demo.notes;
    out.push(base, "", "Then one status line, whichever is true at the talk:", "");
    for (const st of DEMO_STATUSES) out.push(`- ${st}: "${final.demo.statuses[st].notes}" (${countWords(final.demo.statuses[st].notes)} words)`);
    out.push("", `${countWords(base)} words plus the status line, inside the ${u.demoSeconds} s demo clock. This export is at "${data.deck.demoStatus}": ${u.doorWords} words, ${u.doorSeconds} s, leaving ${u.liveSeconds} s live.`);
  }
  out.push("", `**Talk before the door: ${u.talkWords} words = ${u.talkSeconds} s at ${u.checkWordsPerMinute} wpm, plus ${u.transitionSeconds} s of transitions = ${tenths(u.talkSeconds + u.transitionSeconds)} s of the ${u.talkCapSeconds} s cap. At ${slowWpm} words a minute it would take ${u.talkSlowSeconds} s, plus transitions ${tenths(u.talkSlowSeconds + u.transitionSeconds)} s.**`, "");
  return out.join("\n");
}
export function serialize(data) {
  const json = JSON.stringify(data, null, 2) + "\n";
  const js = "// Generated by scripts/build-deck-final.mjs from docs/sentilab/deck/final-5min/FINAL.json. Do not edit.\n"
    + "// The page reads deck-data.json when served; this copy is for opening index.html from disk.\n"
    + `window.DECK_DATA = ${json.trimEnd()};\n`;
  return { json, js };
}
// The PDF's path inside docs/sentilab/deck/, named from the declared cutoff and the gate outcome, never the clock.
export function finalPdfName(data) {
  if (data.deck.preview) throw new FinalError("a preview build never exports a PDF");
  if (data.deck.reviewOnly) throw new FinalError("a review render of another outcome never exports a PDF");
  if (data.deck.demoReview) throw new FinalError("a demo review render never exports a PDF");
  const c = data.build.cutoff;
  return `final-5min/SentiLab-5min-${c.slice(0, 10)}-${c.slice(11, 13)}${c.slice(14, 16)}-${data.build.gate}.pdf`;
}

// ── pull-request refresh (the only step that reads the clock or the network) ───────────────────────────────────────
export function refreshPrs(final, { gh = "gh", now = new Date() } = {}) {
  const at = `${now.toISOString().slice(0, 16)}:00Z`;
  for (const p of final.backup.prs.items) {
    const raw = execFileSync(gh, ["pr", "view", String(p.number), "--repo", PR_REPO, "--json", "state,headRefOid,mergeCommit,mergedAt"], { encoding: "utf8" });
    const j = JSON.parse(raw);
    p.state = j.state;
    p.head = j.headRefOid;
    p.merge = j.mergeCommit?.oid ?? null;
    p.mergedAt = j.mergedAt ? `${j.mergedAt.slice(0, 19)}Z` : null;
    p.checkedAt = at;
  }
  return at;
}

// ── CLI ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
function arg(args, name) {
  const i = args.indexOf(name);
  if (i < 0) return undefined;
  const v = args[i + 1];
  if (v === undefined || v.startsWith("--")) throw new FinalError(`${name} needs a value`);
  return v;
}
// The command line, read before anything is written. A pull-request refresh makes only those rows current; the deck's
// cutoff is a separate, deliberate declaration that every other fact was checked too, so a refresh needs an explicit
// --cutoff, and the source's own reviewed cutoff never moves here.
export function cliOptions(args) {
  const cutoff = arg(args, "--cutoff") ?? null;
  const refresh = args.includes("--refresh-prs");
  if (refresh && !cutoff) throw new FinalError("--refresh-prs needs an explicit --cutoff: a PR refresh alone does not make every other fact current");
  return {
    check: args.includes("--check"), refresh, export: args.includes("--export"), shots: arg(args, "--shots"),
    build: {
      gate: arg(args, "--gate"), measured: arg(args, "--measured") ?? null, cutoff, preview: args.includes("--preview"),
      rederived: args.includes("--rederived"), demoStatus: arg(args, "--demo-status"), demoReview: args.includes("--demo-review"),
    },
  };
}
// The served figures are generated: exactly the files the source names, nothing else in the folder.
export function figureDirMatches(data) {
  const want = [...data.figureFiles.keys()].sort();
  const have = readdirSync(FIGURE_OUT_DIR).sort();
  return JSON.stringify(want) === JSON.stringify(have) && want.every((f) => readFileSync(join(FIGURE_OUT_DIR, f)).equals(data.figureFiles.get(f)));
}
export const SCRIPT_PATH = join(FINAL_DIR, "SCRIPT.md");
function main(args) {
  const write = (data, final) => {
    const { json, js } = serialize(data);
    writeFileSync(join(FINAL_DECK_DIR, "deck-data.json"), json);
    writeFileSync(join(FINAL_DECK_DIR, "deck-data.js"), js);
    mkdirSync(FIGURE_OUT_DIR, { recursive: true });
    for (const f of readdirSync(FIGURE_OUT_DIR)) if (!data.figureFiles.has(f)) throw new FinalError(`deck/final-5min/figures/${f} is not a figure FINAL.json names; remove it by hand`);
    for (const [f, bytes] of data.figureFiles) writeFileSync(join(FIGURE_OUT_DIR, f), bytes);
    // The script is the export's: a preview or a review render of another outcome leaves it alone.
    if (!data.deck.preview && !data.deck.reviewOnly && !data.deck.demoReview) writeFileSync(SCRIPT_PATH, speakerScript(data, final));
  };
  const cli = cliOptions(args);
  if (cli.check) {
    const committed = JSON.parse(readFileSync(join(FINAL_DECK_DIR, "deck-data.json"), "utf8"));
    const loaded = loadFinal();
    const data = buildFinalData(loaded, committed.build);
    const fresh = serialize(data);
    const same = fresh.json === readFileSync(join(FINAL_DECK_DIR, "deck-data.json"), "utf8") && fresh.js === readFileSync(join(FINAL_DECK_DIR, "deck-data.js"), "utf8")
      && figureDirMatches(data) && readFileSync(SCRIPT_PATH, "utf8") === speakerScript(data, loaded.final);
    if (!same) { console.error("deck/final-5min (data, figures or SCRIPT.md) differs from a fresh build of FINAL.json"); process.exit(1); }
    console.log("deck/final-5min matches a fresh build");
    return;
  }
  if (cli.refresh) {
    const src = JSON.parse(readFileSync(FINAL_SOURCE, "utf8"));
    const at = refreshPrs(src);
    writeFileSync(FINAL_SOURCE, JSON.stringify(src, null, 2) + "\n");
    console.log(`refreshed ${src.backup.prs.items.length} pull requests at ${at}`);
  }
  const loaded = loadFinal();
  const data = buildFinalData(loaded, cli.build);
  write(data, loaded.final);
  const shown = data.slides.find((s) => s.id === "gate").content;
  const u = data.budget;
  console.log(`deck/final-5min: ${data.deck.variantLabel}${data.deck.preview ? " (PREVIEW)" : ""}${data.deck.reviewOnly ? " (REVIEW)" : ""}${data.build.measured ? ` ${data.build.measured}` : ""}${shown.verification ? ` · ${shown.verification}` : ""} · demo ${data.deck.demoStatus}, cutoff ${data.deck.cutoff}`);
  console.log(`  talk ${u.talkWords} words = ${u.talkSeconds} s at ${u.checkWordsPerMinute} wpm (${u.talkSlowSeconds} s at ${u.slowWordsPerSecond} w/s) + ${u.transitionSeconds} s transitions = ${tenths(u.talkSeconds + u.transitionSeconds)} s of ${u.talkCapSeconds} s; door ${u.doorWords} words = ${u.doorSeconds} s (${u.doorSlowSeconds} s), live ${u.liveSeconds} s of the ${u.demoSeconds} s demo clock; slot ${u.maxSeconds} s`);
  for (const s of data.slides) console.log(`  ${s.label.padEnd(6)} ${s.id.padEnd(12)} ${String(s.notes.words).padStart(3)} words ${String(s.notes.seconds).padStart(5)} s (${String(s.notes.slowSeconds).padStart(5)} s)${s.main ? (s.id === "demo" ? "  door, inside the demo clock" : "") : "  (backup, not spoken)"}`);
  if (cli.export) {
    const r = spawnSync(process.execPath, [join(REPO_ROOT, "scripts", "export-deck-pdf.mjs"), "--deck", "final", ...(cli.shots ? ["--shots", cli.shots] : []), ...(data.deck.preview || data.deck.reviewOnly || data.deck.demoReview ? ["--no-pdf"] : [])], { stdio: "inherit" });
    process.exit(r.status ?? 1);
  }
}
if (resolve(process.argv[1] ?? "") === fileURLToPath(import.meta.url)) {
  try { main(process.argv.slice(2)); } catch (e) {
    if (e instanceof FinalError) { console.error(`build-deck-final: ${e.message}`); process.exit(1); }
    throw e;
  }
}
