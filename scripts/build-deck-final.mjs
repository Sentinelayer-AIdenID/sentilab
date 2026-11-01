#!/usr/bin/env node
// Builds the SentiLab three-minute deck (deck/final/) from its one reviewed source, docs/sentilab/deck/final-3min/FINAL.json.
//
//   node scripts/build-deck-final.mjs                                   # the result recorded in FINAL.json (gate.result),
//                                                                       # or NOT RUN when none is recorded
//   node scripts/build-deck-final.mjs --rederived                       # the same, with the status line flipped to
//                                                                       # "independently re-derived" once the second reviewer confirms
//   node scripts/build-deck-final.mjs --gate not-run                    # force an outcome (the recorded result is then not shown)
//   node scripts/build-deck-final.mjs --gate fail --measured 77.10,116.02
//   node scripts/build-deck-final.mjs --gate pass --preview             # renders only: no values, marked PREVIEW, no PDF
//   node scripts/build-deck-final.mjs --check                           # exit 1 if the committed data differ from a fresh build
//   ... --cutoff 2026-11-01T12:30:00Z    declare a later fact cutoff (every dated fact must be at or before it)
//   ... --refresh-prs                    re-read the listed pull requests with gh, stamp them, and move the cutoff to now
//   ... --export [--shots <dir>]         then run export-deck-pdf.mjs --deck final (needs PLAYWRIGHT_DIR)
//
// One flag, --gate, chooses the slide-4 outcome; without it the build uses the reviewed result in FINAL.json. The three
// wordings were fixed in FINAL.json before the result existed, and the build refuses an outcome its measured values
// contradict: PASS needs both values within the tolerance of their published references, FAIL needs at least one outside
// it, NOT RUN takes no values. The gate code can also return ERROR or INCOMPLETE; neither has reviewed wording, so
// neither builds. When the recorded result is shown, slide 4 also carries its version comparison, its scope and its
// verification state: "verified by the operator" until --rederived says a second reviewer has re-derived it.
//
// Rules for the data:
//   - Every timeline line, chronology row and example names at least one room record, and its displayed minute is the
//     minute of one of those records (the post time, or a time the record states). Nothing is dated after the cutoff.
//   - Speaker notes are counted at the source's words per second; the five main slides must fit the speech budget.
//   - Every rendered string passes the shared public-render rules, plus this deck's own: no dollar figure, no "deck due",
//     no "source unknown", no "bug", and no internal jargon on the five main slides.
// The build is deterministic: it reads no clock unless --refresh-prs is given, so a rebuild gives the same bytes.
import { createHash } from "node:crypto";
import { execFileSync, spawnSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { DECK_ROOT, PDF_DIR, REPO_ROOT, PacketError, publicText } from "./build-deck-data.mjs";
import { validateSchema } from "./json-schema-lite.mjs";

export const FINAL_DIR = join(PDF_DIR, "final-3min");
export const FINAL_SOURCE = join(FINAL_DIR, "FINAL.json");
export const FINAL_SCHEMA = join(FINAL_DIR, "FINAL.schema.json");
export const FINAL_DECK_DIR = join(DECK_ROOT, "final");
export const FINAL_FORMAT = "sentilab-deck-final/1";
export const DATA_SCHEMA = "sentilab-deck-final-data/1";
export const GATES = ["not-run", "pass", "fail"];
export const PR_REPO = "Sentinelayer-AIdenID/sentilab";

export class FinalError extends Error {}

// ── wording rules ───────────────────────────────────────────────────────────────────────────────────────────────────
// Banned in every rendered string of this deck (on top of the shared NOT_PUBLIC list).
export const FINAL_BANNED = [
  /\$\s?\d/, /\bUSD\b/i, /\bdollars?\b/i, /\bdeck due\b/i, /\bsource unknown\b/i, /\bbugs?\b/i,
];
// Internal jargon kept off the five main slides (backup slides may name pull requests and verdict codes).
export const PLAIN_WORDS = [
  /merged_source_verified/i, /\bP[0-3]\b/, /\bCSP\b/, /\bblobs?\b/i, /\bgrid\s?-?64\b/i, /\bnative6\b/i, /finite controls/i,
  /\bSHA\b/i, /\bseq\b/i, /\bPR\b/, /\bCI\b/, /\bJSON\b/, /\bMCP\b/, /\bCLI\b/, /\bheadroom\b/i, /\bfixture\b/i, /\bslab-?\d/i,
];
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

// Words: whitespace-separated tokens that hold a letter or digit ("closed-form" is one word, "·" none).
export function countWords(text) {
  return String(text).split(/\s+/).filter((t) => /[\p{L}\p{N}]/u.test(t)).length;
}
export function speech(text, wordsPerSecond) {
  const words = countWords(text);
  return { text, words, seconds: Math.round((words / wordsPerSecond) * 10) / 10 };
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

// ── build ───────────────────────────────────────────────────────────────────────────────────────────────────────────
export function buildFinalData({ final, hashes }, options = {}) {
  const { cutoff = null, preview = false, rederived = false } = options;
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
  // The recorded result shows (with its comparison, scope and verification state) only when this build is that result.
  const showResult = Boolean(recorded && !preview && gate === recorded.outcome && values && values.join(",") === recorded.measured);
  if (rederived && !showResult) throw new FinalError("--rederived applies only to the reviewed result recorded in FINAL.json");
  if (recorded) {
    checkRecords(recorded, "the recorded gate result", cutoffMs);
    checkOutcome(recorded.outcome, parseMeasured(recorded.measured), final.gate.references, final.gate.toleranceK);
    checkComparator(recorded.comparator, final.gate.references);
  }
  const verification = showResult ? recorded.verification[rederived ? "rederived" : "operator"] : null;
  const wps = final.talk.wordsPerSecond;
  const B = final.backup;

  // Records and times.
  checkRecords(final.timeline.lede, "slide 3 opening line", cutoffMs);
  final.timeline.lines.forEach((l, i) => checkRecords(l, `slide 3 line ${i + 1}`, cutoffMs));
  checkOrdered([final.timeline.lede, ...final.timeline.lines], "slide 3");
  final.how.steps.forEach((s, i) => checkRecords(s, `slide 2 step ${i + 1}`, cutoffMs));
  checkRecords(final.how.evidence, "the slide 2 review line", cutoffMs);
  if (final.how.evidence.line !== B.reviews.line) throw new FinalError("slide 2 and backup must carry the same review line");
  B.chronology.rows.forEach((r, i) => checkRecords(r, `chronology row ${i + 1}`, cutoffMs));
  checkOrdered(B.chronology.rows, "the chronology");
  checkRecords(B.reviews, "the review-quality line", cutoffMs);
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
  const variantNotes = showResult ? `${fill(v.notes)} ${recorded.comparator.notes} ${verification.notes}` : fill(v.notes);
  const gateTitle = final.gate.title;
  if (!/differs between versions/.test(gateTitle)) throw new FinalError("slide 4 must say the link differs between versions");

  const pr = (n) => B.prs.items.find((p) => p.number === n);
  const prLine = (p) => p.state === "MERGED"
    ? { state: "merged", text: `merged as ${short(p.merge)} at ${utcStamp(p.mergedAt)}`, checked: `checked ${utcStamp(p.checkedAt)}` }
    : { state: p.state.toLowerCase(), text: `${p.state.toLowerCase()} at head ${short(p.head)}`, checked: `checked ${utcStamp(p.checkedAt)}` };
  const gatePr = pr(56);
  if (!gatePr) throw new FinalError("the PR list must include #56, the gate-zero code");

  const notes = {
    problem: speech(final.problem.notes, wps), how: speech(final.how.notes, wps), timeline: speech(final.timeline.notes, wps),
    gate: speech(variantNotes, wps), reuse: speech(final.reuse.notes, wps),
  };
  const mainWords = Object.values(notes).reduce((n, s) => n + s.words, 0);
  const mainSeconds = Math.round((mainWords / wps) * 10) / 10;
  if (mainSeconds > final.talk.speechBudgetSeconds) {
    throw new FinalError(`the five main slides need ${mainSeconds} s at ${wps} words/s, over the ${final.talk.speechBudgetSeconds} s budget`);
  }
  if (final.talk.speechBudgetSeconds + final.talk.bufferSeconds > final.talk.maxSeconds) throw new FinalError("speech plus buffer exceeds the talk length");

  const backupNote = (text) => speech(text, wps);
  const slides = [
    { id: "problem", main: true, kicker: final.problem.kicker, notes: notes.problem, content: {
      hero: final.problem.hero, question: final.problem.question, caption: final.problem.caption,
      answerEyebrow: final.problem.answerEyebrow, answer: final.problem.answer, domain: final.problem.domain } },
    { id: "how", main: true, kicker: final.how.kicker, notes: notes.how, content: {
      title: final.how.title, footnote: final.how.footnote, evidence: final.how.evidence.line,
      steps: final.how.steps.map((s) => ({ title: s.title, text: s.text, today: s.today })) } },
    { id: "timeline", main: true, kicker: final.timeline.kicker, notes: notes.timeline, content: {
      title: final.timeline.title,
      lede: { at: hhmm(final.timeline.lede.at), date: "31 Oct", text: final.timeline.lede.text },
      lines: final.timeline.lines.map((l) => ({ at: hhmm(l.at), text: l.text })),
      callout: final.timeline.callout, note: final.timeline.note } },
    { id: "gate", main: true, kicker: final.gate.kicker, notes: notes.gate, content: {
      title: gateTitle, common: final.gate.common, toleranceK: final.gate.toleranceK,
      variant: gate, label: v.label, text: variantText, bottom: final.gate.bottom,
      rows: final.gate.references.map((r, i) => ({
        label: r.label, source: r.source, publishedC: r.publishedC,
        result: gate === "not-run" ? "not run" : outcome ? `${outcome[i].measuredC} C` : "[measured]",
        diff: outcome ? `${signedDiff(outcome[i].measuredC, r.publishedC)} · ${outcome[i].within ? "within" : "outside"}` : "",
        tone: gate === "not-run" ? "muted" : outcome ? (outcome[i].within ? "ok" : "warn") : "muted",
      })),
      // Shown only with the reviewed result: the same-layout version comparison, the verification state and the scope.
      replay: showResult ? recorded.replay : null,
      comparator: showResult ? recorded.comparator.text : null,
      verification: showResult ? verification.text : null,
      scope: showResult ? recorded.scope : null } },
    { id: "reuse", main: true, kicker: final.reuse.kicker, notes: notes.reuse, content: {
      title: final.reuse.title, receipt: final.reuse.receipt, next: final.reuse.next, status: final.reuse.status } },
    { id: "chronology", main: false, kicker: B.chronology.kicker, notes: backupNote("Backup. If asked how the day unfolded, walk this table; every line is a room record."), content: {
      title: B.chronology.title, note: B.chronology.note, rows: B.chronology.rows.map((r) => ({ at: hhmm(r.at), text: r.text })) } },
    { id: "reviews", main: false, kicker: B.reviews.kicker, notes: backupNote("Backup. If asked whether the agents really check each other, read the line as written, with its qualifier."), content: {
      title: B.reviews.title, line: B.reviews.line, rows: B.reviews.rows, caveats: B.reviews.caveats } },
    { id: "metrics", main: false, kicker: B.metrics.kicker, notes: backupNote("Backup. If asked for the numbers, separate saved output from the simplified model; neither is a calibrated temperature."), content: B.metrics },
    { id: "gate-detail", main: false, kicker: B.gate.kicker, notes: backupNote("Backup. If asked how the test works, read the rules; the three wordings were written before any result."), content: {
      title: B.gate.title, rules: B.gate.rules, source: B.gate.source, wordingTitle: B.gate.wordingTitle,
      status: { pr: 56, ...prLine(gatePr) },
      result: showResult ? { label: v.label, values: formatValues(values), verification: verification.text, detail: recorded.detail, comparator: recorded.comparator.text } : null,
      wordings: GATES.map((g) => ({ gate: g, label: final.gate.variants[g].label, text: final.gate.variants[g].text, chosen: g === gate })) } },
    { id: "drill", main: false, kicker: B.drill.kicker, notes: backupNote("Backup. This is a test fixture with illustrative values; it shows the designed mechanism, not a result."), content: B.drill },
    { id: "status", main: false, kicker: B.status.kicker, notes: backupNote("Backup. Where it stands: no deliverable is fully accepted, and scientific benefit is not established."), content: {
      title: B.status.title, deliverables: B.status.deliverables,
      cards: B.status.cards.map((c) => ({ title: c.title, text: c.text,
        origin: c.originAt ? `origin ${utcStamp(c.originAt)}` : "origin time not recorded", asOf: `as of ${utcStamp(c.asOf)}` })) } },
    { id: "prs", main: false, kicker: B.prs.kicker, notes: backupNote("Backup. Pull request states at the check time; merged ones show their merge commit."), content: {
      title: B.prs.title, repo: B.prs.repo,
      // One check time for the table when every row shares it; otherwise each row keeps its own.
      checked: new Set(B.prs.items.map((p) => p.checkedAt)).size === 1 ? `checked ${utcStamp(B.prs.items[0].checkedAt)}` : null,
      rows: B.prs.items.map((p) => ({ number: `#${p.number}`, what: p.what, ...prLine(p) })) } },
    { id: "receipt", main: false, kicker: B.receipt.kicker, notes: backupNote("Backup. The other-team receipt in full, and why our own leaderboard is not used as evidence."), content: B.receipt },
  ];
  const mains = slides.filter((s) => s.main).length;
  let b = 0;
  slides.forEach((s, i) => { s.label = s.main ? `${i + 1} / ${mains}` : `B${++b}`; });

  const data = {
    schema: DATA_SCHEMA,
    deck: { ...final.deck, cutoff: utcStamp(cut), variant: gate, variantLabel: v.label, preview },
    budget: {
      wordsPerSecond: wps, mainWords, mainSeconds, speechBudgetSeconds: final.talk.speechBudgetSeconds,
      bufferSeconds: final.talk.bufferSeconds, maxSeconds: final.talk.maxSeconds,
    },
    slides,
    build: { gate, measured: values ? values.join(",") : null, cutoff: cut, preview, rederived },
    source: { ...hashes },
  };
  checkRendered(data);
  return data;
}

// Every string a slide or its notes can show, with the slide it sits on.
export function renderedStrings(data) {
  const out = [];
  const walk = (v, slide) => {
    if (typeof v === "string") out.push({ slide, text: v });
    else if (Array.isArray(v)) v.forEach((x) => walk(x, slide));
    else if (v && typeof v === "object") Object.values(v).forEach((x) => walk(x, slide));
  };
  for (const s of data.slides) { walk(s.content, s); walk(s.kicker, s); walk(s.notes.text, s); }
  for (const k of ["title", "event", "talk", "cutoff", "variantLabel"]) out.push({ slide: null, text: data.deck[k] });
  return out;
}
export function checkRendered(data) {
  for (const { slide, text } of renderedStrings(data)) {
    const where = slide ? `slide ${slide.id}` : "deck";
    if (CONTROL.test(text)) throw new FinalError(`${where}: a control character in ${JSON.stringify(text)}`);
    let shown;
    try { shown = publicText(text, where); } catch (e) { if (e instanceof PacketError) throw new FinalError(e.message); throw e; }
    if (shown !== text) throw new FinalError(`${where}: the public-render rules would rewrite ${JSON.stringify(text)}; write it plainly instead`);
    const bad = FINAL_BANNED.find((re) => re.test(text));
    if (bad) throw new FinalError(`${where}: ${bad} is not allowed in this deck: ${JSON.stringify(text)}`);
    if (slide?.main) {
      const jargon = PLAIN_WORDS.find((re) => re.test(text));
      if (jargon) throw new FinalError(`${where}: main slides use plain words, but ${jargon} matches ${JSON.stringify(text)}`);
    }
  }
}

export function serialize(data) {
  const json = JSON.stringify(data, null, 2) + "\n";
  const js = "// Generated by scripts/build-deck-final.mjs from docs/sentilab/deck/final-3min/FINAL.json. Do not edit.\n"
    + "// The page reads deck-data.json when served; this copy is for opening index.html from disk.\n"
    + `window.DECK_DATA = ${json.trimEnd()};\n`;
  return { json, js };
}
// The PDF's path inside docs/sentilab/deck/, named from the declared cutoff and the gate outcome, never the clock.
export function finalPdfName(data) {
  if (data.deck.preview) throw new FinalError("a preview build never exports a PDF");
  const c = data.build.cutoff;
  return `final-3min/SentiLab-3min-${c.slice(0, 10)}-${c.slice(11, 13)}${c.slice(14, 16)}-${data.build.gate}.pdf`;
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
function main(args) {
  const write = (data) => {
    const { json, js } = serialize(data);
    writeFileSync(join(FINAL_DECK_DIR, "deck-data.json"), json);
    writeFileSync(join(FINAL_DECK_DIR, "deck-data.js"), js);
  };
  if (args.includes("--check")) {
    const committed = JSON.parse(readFileSync(join(FINAL_DECK_DIR, "deck-data.json"), "utf8"));
    const fresh = serialize(buildFinalData(loadFinal(), committed.build));
    const same = fresh.json === readFileSync(join(FINAL_DECK_DIR, "deck-data.json"), "utf8") && fresh.js === readFileSync(join(FINAL_DECK_DIR, "deck-data.js"), "utf8");
    if (!same) { console.error("deck/final/deck-data.json or .js differs from a fresh build of FINAL.json"); process.exit(1); }
    console.log("deck/final matches a fresh build");
    return;
  }
  let cutoff = arg(args, "--cutoff") ?? null;
  if (args.includes("--refresh-prs")) {
    const src = JSON.parse(readFileSync(FINAL_SOURCE, "utf8"));
    const at = refreshPrs(src);
    // The source now holds facts checked at this minute, so its own reviewed cutoff moves with them.
    if (Date.parse(at) > Date.parse(src.cutoff)) src.cutoff = at;
    writeFileSync(FINAL_SOURCE, JSON.stringify(src, null, 2) + "\n");
    cutoff ??= at;
    console.log(`refreshed ${src.backup.prs.items.length} pull requests at ${at}`);
  }
  const options = {
    gate: arg(args, "--gate"), measured: arg(args, "--measured") ?? null, cutoff, preview: args.includes("--preview"),
    rederived: args.includes("--rederived"),
  };
  const data = buildFinalData(loadFinal(), options);
  write(data);
  const shown = data.slides.find((s) => s.id === "gate").content;
  console.log(`deck/final: ${data.deck.variantLabel}${data.deck.preview ? " (PREVIEW)" : ""}${data.build.measured ? ` ${data.build.measured}` : ""}${shown.verification ? ` · ${shown.verification}` : ""}, cutoff ${data.deck.cutoff}, main speech ${data.budget.mainWords} words = ${data.budget.mainSeconds} s of ${data.budget.speechBudgetSeconds} s`);
  for (const s of data.slides) console.log(`  ${s.label.padEnd(6)} ${s.id.padEnd(12)} ${String(s.notes.words).padStart(3)} words ${String(s.notes.seconds).padStart(5)} s${s.main ? "" : "  (backup, not spoken)"}`);
  if (args.includes("--export")) {
    const shots = arg(args, "--shots");
    const r = spawnSync(process.execPath, [join(REPO_ROOT, "scripts", "export-deck-pdf.mjs"), "--deck", "final", ...(shots ? ["--shots", shots] : []), ...(data.deck.preview ? ["--no-pdf"] : [])], { stdio: "inherit" });
    process.exit(r.status ?? 1);
  }
}
if (resolve(process.argv[1] ?? "") === fileURLToPath(import.meta.url)) {
  try { main(process.argv.slice(2)); } catch (e) {
    if (e instanceof FinalError) { console.error(`build-deck-final: ${e.message}`); process.exit(1); }
    throw e;
  }
}
