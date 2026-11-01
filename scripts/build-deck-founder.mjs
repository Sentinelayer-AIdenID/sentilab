#!/usr/bin/env node
// Builds the founder pitch (v4): Carter's three-minute main talk, from docs/sentilab/deck/founder-v4/V4.json.
//
//   node scripts/build-deck-founder.mjs            # writes deck/founder-v4/ (data, pictures), SCRIPT.md, FILL-IN.md, SOURCES.md
//   node scripts/build-deck-founder.mjs --check    # exit 1 unless the committed outputs match a fresh build
//   PLAYWRIGHT_DIR=<dir> node scripts/build-deck-founder.mjs --export [--shots <dir>]   # then prints the PDF
//
// The spine is root's founder pitch (team room 57809), with root's carried openings, aneta's finding beat and Carter's
// additions; the technical deck (final-5min, v3.1) stays the backup. The build refuses what the talk may not say:
// - a vendor or person name on a slide (the public-render rule), an unconsented team, or Delfie without the form the
//   team asked for;
// - a claim with nothing behind it: "records" broken, hours or money saved, "40+ users", the historical 300-post snapshot;
// - a number on a main slide that its own facts do not declare, or an elapsed time its two records do not give;
// - a science slide without "simulated";
// - more talk than the clock allows: three minutes at 150 words a minute, transitions included.
// A number not measured yet is a metric placeholder: it shows "measuring…" until docs/sentilab/deck/founder-v4/METRICS.json
// (a copy of the metrics pass's file) carries it with its definition, scope, window and source.
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { DECK_ROOT, NOT_PUBLIC, PDF_DIR, REPO_ROOT } from "./build-deck-data.mjs";

export const FOUNDER_DIR = join(PDF_DIR, "founder-v4");
export const FOUNDER_SOURCE = join(FOUNDER_DIR, "V4.json");
export const FOUNDER_METRICS = join(FOUNDER_DIR, "METRICS.json");
export const FOUNDER_DECK_DIR = join(DECK_ROOT, "founder-v4");
export const FOUNDER_FIGURE_DIR = join(FOUNDER_DECK_DIR, "figures");
export const FOUNDER_OUTPUTS = { script: join(FOUNDER_DIR, "SCRIPT.md"), fillIn: join(FOUNDER_DIR, "FILL-IN.md"), sources: join(FOUNDER_DIR, "SOURCES.md") };

export class FounderError extends Error {}
const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");
const tenths = (x) => Math.round(x * 10) / 10;
// Words: whitespace-separated tokens that hold a letter or digit, as in the five-minute deck; a placeholder is one word.
export const countWords = (text) => String(text).split(/\s+/).filter((t) => /[\p{L}\p{N}]/u.test(t)).length;

// What a slide may not show, on top of the public-render rule (no vendor, model, person or agent-role names).
export const SLIDE_BANNED = [
  [/\brecord-breaking\b|\bnew\s+records?\b|\brecords?\s+(?:broken|set)\b|\bset(?:s|ting)?\s+(?:a\s+)?records?\b|\brecords?\b[^.]{0,40}\bbreak|\bbreak\w*\b[^.]{0,20}\brecords?\b/i, "a records claim with no comparison behind it"],
  [/\b(?:hours|money|time|costs?)\s+(?:saved|saving)\b|\bsav(?:e|es|ed|ing)\s+(?:engineers|hours|money|time)\b/i, "a savings claim with no baseline"],
  [/\b40\s*\+|\bforty\s+(?:users|people)\b|\b40\s+(?:users|people)\b/i, "\"40+ users\": the record shows 28 senders"],
  [/\b300\s+posts\b|\bnine\s+outside\s+teams\b/i, "the historical 300-post snapshot (aneta's count replaces it)"],
  // Root, 07:52Z: 17 is member accounts, not people who took part; say posting identities.
  [/\b17\s+people\b|\bseventeen\s+people\b/i, "\"17 people\": 17 is member accounts; say posting identities"],
  // Root, 07:52Z: the 115.93 against 115.94 question is unresolved, so no solver library is named as its cause.
  [/\bSuperLU\b|\bmulti-?grid\b/i, "a solver library named for the unresolved 115.93 against 115.94 question"],
  [/\b(?:Kiro|Jira|Slack|Facebook|GitHub)\b/i, "a product name (the Kiro/Jira/Slack line is spoken, not shown)"],
];
// The spoken words may name those products (the joke), but never the vendor rules or the unbacked claims.
const SAY_BANNED = SLIDE_BANNED.filter(([, why]) => !why.startsWith("a product name"));
// Money stays off the main slides: the two cost scopes are a backup page, Carter's call (the coordinator, 07:51Z).
const MONEY = [/\$\s?\d|\bUSD\b|\bdollars?\b/i, "money on a main slide (cost is a backup page)"];
// The two citations may name their publisher, on the sources page only.
const CITATIONS = ["blog.cloudflare.com/rethinking-cache-ai-humans/", "blog.cloudflare.com/agentic-web"];

function publicRule(text, where) {
  const bad = NOT_PUBLIC.find((re) => re.test(text));
  if (bad) throw new FounderError(`public-render rule ${bad} fails in ${where}: ${JSON.stringify(text)}`);
}
function claimRules(text, where, rules) {
  for (const [re, why] of rules) if (re.test(text)) throw new FounderError(`${where}: ${why}: ${JSON.stringify(text)}`);
}
// A digit-bearing token, trimmed of the punctuation around it ("(2026)," -> "2026", "1,700%" -> "1,700", "0.01°" -> "0.01").
const numberTokens = (text) => String(text).split(/\s+/).map((t) => t.replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, "")).filter((t) => /\d/.test(t));

// A count as the slides print it: 1496 -> "1,496"; other values as they are.
export const fmt = (v) => (typeof v === "number" && Number.isInteger(v) ? v.toLocaleString("en-US") : String(v));
// METRICS.json, from the metrics pass (C:/tmp/metrics, copied here byte for byte): { "items": [ { "key", "value", "unit",
// "definition", "scope", "window_start", "window_end", "source", ... } ], "could_not_measure": [...] }. A value of null is
// not measured, so its slide keeps "measuring…". Every measured item must carry its definition, scope, window and source.
export function loadMetrics(path = FOUNDER_METRICS) {
  if (!existsSync(path)) return { sha256: null, byId: new Map() };
  const bytes = readFileSync(path);
  const raw = JSON.parse(bytes.toString("utf8"));
  const list = Array.isArray(raw.items) ? raw.items : Array.isArray(raw.metrics) ? raw.metrics : [];
  const byId = new Map();
  for (const m of list) {
    const id = m.key ?? m.id;
    if (m.value === null || m.value === undefined) continue;
    const window = m.window ?? (m.window_end ? `${m.window_start ?? "?"} to ${m.window_end}` : null);
    for (const [k, v] of [["key", id], ["definition", m.definition], ["scope", m.scope], ["window", window], ["source", m.source]]) {
      if (v === undefined || v === null || v === "") throw new FounderError(`METRICS.json: ${id ?? "an item"} has no ${k}`);
    }
    byId.set(id, { ...m, id, window, display: String(m.display ?? fmt(m.value)) });
  }
  return { sha256: sha256(bytes), byId };
}
// A fact tied to the metrics file: the number the slide shows must be the file's value, or a stated derivation of it.
export function metricValue(fact, metrics, where) {
  const get = (key) => {
    const m = metrics.byId.get(key);
    if (!m) throw new FounderError(`${where}: METRICS.json has no measured ${key}`);
    return m.value;
  };
  switch (fact.derive ?? "value") {
    case "value": return fmt(get(fact.metric));
    case "minus": return fmt(get(fact.metric[0]) - get(fact.metric[1]));
    case "median-seconds": {
      const v = Object.values(get(fact.metric)).map(Number).sort((a, b) => a - b);
      const mid = v.length % 2 ? v[(v.length - 1) / 2] : (v[v.length / 2 - 1] + v[v.length / 2]) / 2;
      return (mid / 1000).toFixed(1);
    }
    case "range-seconds": {
      const v = Object.values(get(fact.metric)).map(Number);
      return `${(Math.min(...v) / 1000).toFixed(1)}–${(Math.max(...v) / 1000).toFixed(1)}`;
    }
    case "tokens-from-bytes": return fmt(Math.round(get(fact.metric) / 400) * 100);
    default: throw new FounderError(`${where}: unknown derivation ${fact.derive}`);
  }
}

export function loadFounder() {
  const bytes = readFileSync(FOUNDER_SOURCE);
  const v4 = JSON.parse(bytes.toString("utf8"));
  if (v4.schema !== "sentilab-deck-founder-source/1") throw new FounderError(`unsupported source schema ${JSON.stringify(v4.schema)}`);
  return { v4, sourceSha256: sha256(bytes), metrics: loadMetrics() };
}

const SCIENCE = new Set(["chips", "hook", "link", "scorecard"]);
const LAYOUTS = new Set(["joke", "flow", "numbers", "bars", "times", "figure", "tiles", "statement", "closer", "sources"]);

// The text a slide shows, for the checks: everything but the pictures.
function shownText(c) {
  const parts = [c.title, c.caption, c.footer, c.line, c.apps, c.punch, c.text, c.label, c.still?.label];
  for (const k of ["chips", "points", "flow", "items"]) parts.push(...(c[k] ?? []));
  for (const s of c.steps ?? []) parts.push(s.verb, s.what);
  for (const t of [...(c.tiles ?? []), ...(c.stats ?? [])]) parts.push(t.value, t.label, t.head, t.body);
  for (const b of c.bars ?? []) parts.push(b.show, b.label);
  for (const t of c.times ?? []) parts.push(t.show, t.what);
  return parts.filter((x) => x !== undefined && x !== null && x !== "").join(" \n ");
}

function checkTimes(s) {
  for (const t of s.times ?? []) {
    const minutes = (Date.parse(t.to) - Date.parse(t.from)) / 60000;
    if (!(minutes > 0)) throw new FounderError(`${s.id}: ${t.show} has no positive interval`);
    const m = /^(?:under\s+)?(?:(\d+)\s*h\s*)?(\d+)(?:\s*min)?$/.exec(t.show);
    if (!m) throw new FounderError(`${s.id}: cannot read the duration ${JSON.stringify(t.show)}`);
    const stated = Number(m[1] ?? 0) * 60 + Number(m[2]);
    const ok = t.rule === "under" ? t.show.startsWith("under") && minutes < stated : t.rule === "round" && Math.round(minutes) === stated;
    if (!ok) throw new FounderError(`${s.id}: ${JSON.stringify(t.show)} is not its records' ${minutes.toFixed(2)} minutes`);
  }
}

// The slot picks the cut: "3min" is the full talk; "2min" (v4-short) speaks fewer slides, each with its own words where
// V4.json gives them, and moves the rest to the head of the backup, as v3.1-short did.
export const FOUNDER_SLOTS = ["3min", "2min"];
// --final is the freeze: a number without a receipt is dropped from its slide (never "measuring…" on stage), and a slide
// whose words need one speaks its sayIfUnmeasured line instead. Drafts keep the placeholders and the DRAFT tag.
export function buildFounderData({ v4, sourceSha256, metrics }, { slot = "3min", final = false } = {}) {
  if (!FOUNDER_SLOTS.includes(slot)) throw new FounderError(`--slot must be one of ${FOUNDER_SLOTS.join(", ")}`);
  const S = v4.slots[slot];
  const wanted = v4.metrics.wanted;
  const named = v4.teams.named;
  const placeholders = [];
  // The metrics file the deck was reviewed with: a different file is a different set of numbers.
  if (metrics.sha256 && v4.metrics.sha256 !== metrics.sha256) throw new FounderError(`METRICS.json is not the file V4.json pins (${String(v4.metrics.sha256).slice(0, 8)}…)`);
  const metric = (id, where) => {
    if (!Object.hasOwn(wanted, id)) throw new FounderError(`${where}: metric ${id} is not one the deck asks for`);
    const m = metrics.byId.get(wanted[id].key ?? id);
    if (!m) placeholders.push({ id, where, label: wanted[id].label, need: wanted[id].need, dropped: final });
    return m ? { value: m.display, label: wanted[id].label, metric: id, measuring: false, window: m.window } : { value: v4.metrics.placeholder, label: wanted[id].label, metric: id, measuring: true };
  };
  const ids = new Set();
  for (const id of S.main) if (!v4.slides.some((s) => s.id === id)) throw new FounderError(`slot ${slot}: no slide ${id}`);
  const all = [
    ...S.main.map((id) => ({ ...v4.slides.find((s) => s.id === id), main: true, say: S.say?.[id] ?? v4.slides.find((s) => s.id === id).say })),
    ...v4.slides.filter((s) => !S.main.includes(s.id)).map((s) => ({ ...s, main: false })),
    ...v4.backup.map((s) => ({ ...s, main: false })),
  ];
  const slides = all.map((s, i) => {
    if (ids.has(s.id)) throw new FounderError(`duplicate slide id ${s.id}`);
    ids.add(s.id);
    if (!LAYOUTS.has(s.layout)) throw new FounderError(`${s.id}: unknown layout ${s.layout}`);
    const where = `slide ${s.id}`;
    const content = { layout: s.layout };
    for (const k of ["title", "caption", "footer", "line", "apps", "punch", "text", "label", "chips", "points", "flow", "steps", "bars", "times", "items", "stats"]) if (s[k] !== undefined) content[k] = s[k];
    if (s.tiles) content.tiles = s.tiles.map((t, k) => (t.metric ? metric(t.metric, `${where} tile ${k + 1}`) : { ...t })).filter((t) => !(final && t.measuring));
    if (s.picture?.still) {
      const st = v4.stills[s.picture.still];
      if (!st) throw new FounderError(`${where}: no still ${s.picture.still}`);
      content.still = { id: s.picture.still, src: `figures/${st.file}`, width: st.width, height: st.height, alt: st.alt, label: s.picture.label ?? null };
    }
    if (s.picture?.figure) {
      const f = v4.figures[s.picture.figure];
      if (!f) throw new FounderError(`${where}: no figure ${s.picture.figure}`);
      const svg = servedFigure(s.picture.figure, f).toString("utf8");
      const alt = /<svg\b[^>]*?\saria-label="([^"]*)"/.exec(svg)?.[1];
      const minFont = Math.min(...[...svg.matchAll(/font-size\s*[:=]\s*["']?\s*([\d.]+)/g)].map((m) => Number(m[1])));
      if (!alt || !Number.isFinite(minFont)) throw new FounderError(`${where}: ${f.file} has no label or no text sizes`);
      content.figure = { id: s.picture.figure, src: `figures/${f.file}`, width: f.width, height: f.height, scale: f.scale, minFont, alt: alt.replace(/&quot;/g, '"').replace(/&amp;/g, "&") };
    }
    if (s.bars) {
      const top = Math.max(...s.bars.map((b) => b.value));
      content.bars = s.bars.map((b) => {
        if (b.show !== `${Math.round(b.value)} °C`) throw new FounderError(`${where}: ${b.show} is not ${b.value} rounded`);
        return { ...b, share: b.value / top };
      });
    }
    checkTimes(s);
    // The rules on what the slide shows.
    let shown = shownText(content);
    if (s.id === "sources") for (const c of CITATIONS) shown = shown.split(c).join("the cited article");
    publicRule(shown, where);
    claimRules(shown, where, SLIDE_BANNED);
    for (const t of v4.teams.unnamed) if (new RegExp(`\\b${t}\\b`, "i").test(shown)) throw new FounderError(`${where} names ${t}, who has not consented`);
    if (/\bDelfie\b(?!\s+\(delphisci team\))/.test(shown)) throw new FounderError(`${where} names Delfie without the form the team asked for: "${named.Delfie}"`);
    if (SCIENCE.has(s.id) && !/simulated/i.test(shown)) throw new FounderError(`${where} shows simulated science without saying "simulated"`);
    if (s.main) {
      claimRules(shown, where, [MONEY]);
      // A fact tied to METRICS.json shows exactly the file's value (or its stated derivation) first.
      for (const f of s.facts ?? []) {
        if (!f.metric) continue;
        const v = metricValue(f, metrics, where);
        if (f.shows[0] !== v) throw new FounderError(`${where} shows ${f.shows[0]} for ${[].concat(f.metric).join(" - ")}, but METRICS.json gives ${v}`);
      }
      const declared = new Set((s.facts ?? []).flatMap((f) => (f.source || f.metric ? f.shows : [])));
      const measured = new Set((content.tiles ?? []).filter((t) => t.metric && !t.measuring).flatMap((t) => numberTokens(t.value)));
      for (const n of numberTokens(shown)) if (!declared.has(n) && !measured.has(n)) throw new FounderError(`${where} shows ${n}, which none of its facts declares`);
    }
    // The spoken words, with each metric read out or marked for the presenter. A metric counts as one word, measured or
    // not, so filling it in does not move the clock.
    let notes = null;
    if (s.main) {
      const unmeasured = [...String(s.say ?? "").matchAll(/\{m:([\w.]+)\}/g)].some(([, id]) => !metrics.byId.get(wanted[id]?.key ?? id));
      if (final && unmeasured && !s.sayIfUnmeasured) throw new FounderError(`${where}: its words need a number with no receipt, and it has no sayIfUnmeasured line`);
      if (final && unmeasured) for (const [, id] of String(s.say).matchAll(/\{m:([\w.]+)\}/g)) metric(id, `${where} words`);
      const raw = String(final && unmeasured ? s.sayIfUnmeasured : s.say ?? "");
      const say = raw.replace(/\{m:([\w.]+)\}/g, (_, id) => {
        const m = metric(id, `${where} words`);
        return m.measuring ? `[${m.label}: measuring]` : m.value;
      });
      if (!say.trim()) throw new FounderError(`${where} has no spoken words`);
      publicRule(say, `${where} words`);
      claimRules(say, `${where} words`, SAY_BANNED);
      for (const t of v4.teams.unnamed) if (new RegExp(`\\b${t}\\b`, "i").test(say)) throw new FounderError(`${where} words name ${t}, who has not consented`);
      const words = countWords(raw.replace(/\{m:[\w.]+\}/g, "N"));
      notes = { text: say, words, seconds: tenths(words / (v4.clock.wordsPerMinute / 60)), slowSeconds: tenths(words / (v4.clock.slowWordsPerMinute / 60)), cue: s.cue ?? null };
    }
    const main = S.main.length;
    // For SOURCES.md: a metrics fact is described by the file's own definition, window and scope.
    const facts = (s.facts ?? []).map((f) => (f.metric ? {
      shows: f.shows,
      source: `METRICS.json ${[].concat(f.metric).map((k) => { const m = metrics.byId.get(k); return `${k} = ${m.display}${m.unit ? ` ${m.unit}` : ""} (${m.definition.slice(0, 160)}${m.definition.length > 160 ? "…" : ""}; window ${m.window}; scope ${m.scope.slice(0, 120)})`; }).join(" minus ")}${f.derive && f.derive !== "value" && f.derive !== "minus" ? `, shown as its ${f.derive}` : ""}.`,
    } : f));
    return { id: s.id, main: s.main, label: s.main ? `${i + 1} / ${main}` : `B${i - main + 1}`, kicker: s.kicker, content, notes, facts };
  });
  const talk = slides.filter((s) => s.main);
  const words = talk.reduce((a, s) => a + s.notes.words, 0);
  const c = { ...v4.clock, talkCapSeconds: S.talkCapSeconds, transitionSeconds: S.transitionSeconds };
  const talkSeconds = tenths(words / (c.wordsPerMinute / 60));
  const slowSeconds = tenths(words / (c.slowWordsPerMinute / 60));
  const total = tenths(talkSeconds + c.transitionSeconds);
  if (total > c.talkCapSeconds) throw new FounderError(`the talk is ${words} words = ${talkSeconds} s at ${c.wordsPerMinute} wpm + ${c.transitionSeconds} s of transitions = ${total} s, over the ${c.talkCapSeconds} s cap`);
  const cutoff = `${v4.cutoff.slice(0, 10)} ${v4.cutoff.slice(11, 16)} UTC`;
  // Placeholders, once each (a metric shown on a tile and read in the words is one fill-in), with every place it shows.
  const fills = [];
  for (const p of placeholders) {
    const seen = fills.find((x) => x.id === p.id);
    if (seen) { if (!seen.where.includes(p.where)) seen.where = `${seen.where} and ${p.where.replace(/^slide \S+ /, "")}`; } else fills.push({ ...p });
  }
  return {
    schema: "sentilab-deck-founder-data/1",
    deck: { title: v4.title, event: v4.event, talk: S.talk, slot, cutoff, cutoffIso: v4.cutoff, draft: !final, measuring: !final && fills.length > 0 },
    source: { sourceSha256, metricsSha256: metrics.sha256 },
    budget: { talkWords: words, talkSeconds, slowSeconds, transitionSeconds: c.transitionSeconds, totalSeconds: total, slowTotalSeconds: tenths(slowSeconds + c.transitionSeconds), talkCapSeconds: c.talkCapSeconds, wordsPerMinute: c.wordsPerMinute, slowWordsPerMinute: c.slowWordsPerMinute,
      // With the demo the slot plans for (Carter's slot, 57411: 3-4 minutes of talk, then 1-2 of demo).
      demoSeconds: S.demoSeconds ?? 0, withDemoSeconds: tenths(total + (S.demoSeconds ?? 0)), slowWithDemoSeconds: tenths(slowSeconds + c.transitionSeconds + (S.demoSeconds ?? 0)) },
    placeholders: fills,
    slides: slides.map(({ facts, ...s }) => s),
    facts: slides.map((s) => ({ id: s.id, facts: s.facts })),
  };
}

export const founderPdfName = (data) => `founder-v4/SentiLab-founder-${data.deck.slot}-${data.deck.cutoffIso.slice(0, 10)}-${data.deck.cutoffIso.slice(11, 13)}${data.deck.cutoffIso.slice(14, 16)}-${!data.deck.draft ? "final" : data.deck.measuring ? "draft" : "review"}.pdf`;

export function serialize(data) {
  const { facts, ...pub } = data;
  const json = JSON.stringify(pub, null, 2) + "\n";
  return { json, js: `window.DECK_DATA = ${JSON.stringify(pub)};\n` };
}

// Seconds as m:ss, rounded to the second (291 -> "4:51").
const mss = (s) => `${Math.floor(Math.round(s) / 60)}:${String(Math.round(s) % 60).padStart(2, "0")}`;
export function speakerScript(data, v4) {
  const u = data.budget;
  const out = [
    `# SentiLab founder pitch (v4${data.deck.slot === "3min" ? "" : "-short"}), ${data.deck.talk}, ${data.deck.measuring ? "draft" : "review"} ${data.deck.cutoff}`,
    "",
    `The spoken words, exactly as the deck's notes hold them (V4.json sha256 ${data.source.sourceSha256.slice(0, 8)}…). Spine: root's founder pitch (team room 57809), with root's two carried openings (reply to 57809, 07:04Z), the finding beat in root's wording (reply to 57816, 07:14Z) and Carter's additions from 57800. The technical deck (v3.1) is the backup.`,
    "",
    `**Clock:** ${u.talkWords} words = ${u.talkSeconds} s at ${u.wordsPerMinute} wpm, plus ${u.transitionSeconds} s of transitions = ${u.totalSeconds} s of the ${u.talkCapSeconds} s maximum. At ${u.slowWordsPerMinute} wpm: ${u.slowTotalSeconds} s. Numbers and hyphenated words take longer to say than one word each, and the jokes need their pauses: time it out loud once.`,
    "",
    `**With the demo:** ${u.demoSeconds} s of demo makes ${u.withDemoSeconds} s (${mss(u.withDemoSeconds)}) at ${u.wordsPerMinute} wpm, or ${u.slowWithDemoSeconds} s (${mss(u.slowWithDemoSeconds)}) at ${u.slowWordsPerMinute}. Before the talk, do one real timed rehearsal with the actual demo.`,
    "",
  ];
  for (const s of data.slides.filter((x) => x.main)) {
    out.push(`## ${s.label.split(" ")[0]}. ${s.content.title ?? s.content.punch} (${s.kicker})`, "", s.notes.text, "", `${s.notes.words} words, ${s.notes.seconds} s at ${u.wordsPerMinute} wpm.${s.notes.cue ? ` Cue: ${s.notes.cue}` : ""}`, "");
  }
  if (data.placeholders.length) {
    out.push("## Still measuring", "", "Each shows \"measuring…\" on its slide and is read out only once it is filled:", "");
    for (const p of data.placeholders) out.push(`- ${p.label} (${p.where}; metric \`${p.id}\`)`);
    out.push("");
  }
  return out.join("\n");
}

export function fillInTable(data) {
  const rows = data.placeholders.map((p) => `| ${p.where.replace(/^slide /, "")} | ${p.label} | \`${p.id}\` | ${p.need} |`);
  return ["# FILL-IN: the founder deck's placeholders", "", `As of ${data.deck.cutoff}. Each shows "measuring…" until docs/sentilab/deck/founder-v4/METRICS.json carries it with its definition, scope, window and source; then rebuild and re-export.`, "",
    "| Slide | Shows | Metric id | Needed |", "|---|---|---|---|", ...(rows.length ? rows : ["| none | | | |"]), ""].join("\n");
}

export function sourcesList(data) {
  const out = ["# SOURCES: every number on the founder deck's slides", "", "The build refuses a number on a main slide that the slide's facts do not declare. Room references are for reviewers; the slides show none.", ""];
  for (const { id, facts } of data.facts) {
    if (!facts.length) continue;
    out.push(`## ${id}`, "");
    for (const f of facts) out.push(`- ${f.shows.join(", ")}: ${f.source}`);
    out.push("");
  }
  return out.join("\n");
}

// A figure as the deck serves it: the reviewed file, then only its declared text edits and this deck's own label.
const xmlEsc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
export function servedFigure(id, f) {
  const bytes = readFileSync(join(FOUNDER_DIR, "figures", f.file));
  if (sha256(bytes) !== f.sha256) throw new FounderError(`figure ${id} (${f.file}) is not the reviewed file`);
  if (!f.edits?.length && !f.alt) return bytes;
  let svg = bytes.toString("utf8");
  if (/<script\b|<foreignObject\b|\son[a-z]+\s*=|javascript:|<!ENTITY|<!DOCTYPE/i.test(svg)) throw new FounderError(`figure ${id} is not inert`);
  for (const e of f.edits ?? []) {
    const needle = `>${xmlEsc(e.from).replace(/&quot;/g, '"')}<`;
    const n = svg.split(needle).length - 1;
    if (n !== 1) throw new FounderError(`figure ${id}: the text ${JSON.stringify(e.from)} must appear exactly once, found ${n}`);
    svg = svg.replace(needle, `>${xmlEsc(e.to).replace(/&quot;/g, '"')}<`);
  }
  if (f.alt) svg = svg.replace(/(<svg\b[^>]*?\saria-label=")[^"]*(")/, `$1${xmlEsc(f.alt)}$2`);
  return Buffer.from(svg, "utf8");
}
function pictureFiles(v4) {
  const files = new Map();
  for (const [id, f] of Object.entries(v4.stills)) {
    const bytes = readFileSync(join(FOUNDER_DIR, "figures", f.file));
    if (sha256(bytes) !== f.sha256) throw new FounderError(`still ${id} (${f.file}) is not the reviewed file`);
    files.set(f.file, bytes);
  }
  for (const [id, f] of Object.entries(v4.figures)) files.set(f.file, servedFigure(id, f));
  return files;
}
// The short cut's speaker script sits beside the full one.
export const scriptPath = (slot) => (slot === "3min" ? FOUNDER_OUTPUTS.script : join(FOUNDER_DIR, `SCRIPT-${slot}.md`));

export function outputsMatch(data, v4, loaded) {
  const { json, js } = serialize(data);
  const pics = pictureFiles(v4);
  const same = (p, s) => existsSync(p) && readFileSync(p, "utf8") === s;
  const scripts = FOUNDER_SLOTS.every((slot) => same(scriptPath(slot), speakerScript(slot === data.deck.slot ? data : buildFounderData(loaded, { slot }), v4)));
  return same(join(FOUNDER_DECK_DIR, "deck-data.json"), json) && same(join(FOUNDER_DECK_DIR, "deck-data.js"), js)
    && scripts && same(FOUNDER_OUTPUTS.fillIn, fillInTable(data)) && same(FOUNDER_OUTPUTS.sources, sourcesList(data))
    && JSON.stringify(readdirSync(FOUNDER_FIGURE_DIR).sort()) === JSON.stringify([...pics.keys()].sort())
    && [...pics].every(([f, b]) => readFileSync(join(FOUNDER_FIGURE_DIR, f)).equals(b));
}

function main(args) {
  const loaded = loadFounder();
  const at = args.indexOf("--slot");
  const slot = at >= 0 ? args[at + 1] : "3min";
  const final = args.includes("--final");
  const data = buildFounderData(loaded, { slot, final });
  if (args.includes("--check")) {
    if (slot !== "3min") throw new FounderError("--check reads the committed build, which is the 3min slot");
    if (!outputsMatch(data, loaded.v4, loaded)) { console.error("deck/founder-v4 or its SCRIPT/FILL-IN/SOURCES differ from a fresh build of V4.json"); process.exit(1); }
    console.log("deck/founder-v4 matches a fresh build");
    return;
  }
  const { json, js } = serialize(data);
  mkdirSync(FOUNDER_FIGURE_DIR, { recursive: true });
  writeFileSync(join(FOUNDER_DECK_DIR, "deck-data.json"), json);
  writeFileSync(join(FOUNDER_DECK_DIR, "deck-data.js"), js);
  const pics = pictureFiles(loaded.v4);
  for (const f of readdirSync(FOUNDER_FIGURE_DIR)) if (!pics.has(f)) throw new FounderError(`deck/founder-v4/figures/${f} is not a picture V4.json names; remove it by hand`);
  for (const [f, b] of pics) writeFileSync(join(FOUNDER_FIGURE_DIR, f), b);
  for (const s of FOUNDER_SLOTS) writeFileSync(scriptPath(s), speakerScript(s === slot ? data : buildFounderData(loaded, { slot: s }), loaded.v4));
  writeFileSync(FOUNDER_OUTPUTS.fillIn, fillInTable(data));
  writeFileSync(FOUNDER_OUTPUTS.sources, sourcesList(data));
  const u = data.budget;
  console.log(`deck/founder-v4: ${data.slides.length} slides (${data.slides.filter((s) => s.main).length} main), facts as of ${data.deck.cutoff}${data.deck.measuring ? `, ${data.placeholders.length} placeholders` : ""}`);
  console.log(`  talk ${u.talkWords} words = ${u.talkSeconds} s at ${u.wordsPerMinute} wpm + ${u.transitionSeconds} s transitions = ${u.totalSeconds} s of ${u.talkCapSeconds} s (${u.slowTotalSeconds} s at ${u.slowWordsPerMinute} wpm)`);
  for (const s of data.slides.filter((x) => x.main)) console.log(`  ${s.label.padEnd(7)} ${s.id.padEnd(8)} ${String(s.notes.words).padStart(3)} words ${String(s.notes.seconds).padStart(5)} s`);
  if (args.includes("--export")) {
    const at = args.indexOf("--shots");
    const r = spawnSync(process.execPath, [join(REPO_ROOT, "scripts", "export-deck-pdf.mjs"), "--deck", "founder", ...(at >= 0 ? ["--shots", args[at + 1]] : [])], { stdio: "inherit" });
    process.exit(r.status ?? 1);
  }
}
if (resolve(process.argv[1] ?? "") === fileURLToPath(import.meta.url)) {
  try { main(process.argv.slice(2)); } catch (e) {
    if (e instanceof FounderError) { console.error(`build-deck-founder: ${e.message}`); process.exit(1); }
    throw e;
  }
}
