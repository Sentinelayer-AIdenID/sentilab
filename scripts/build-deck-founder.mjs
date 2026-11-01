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
import { basename, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { DECK_ROOT, NOT_PUBLIC, PDF_DIR, REPO_ROOT } from "./build-deck-data.mjs";
import { readQr } from "./qr-read.mjs";

export const FOUNDER_DIR = join(PDF_DIR, "founder-v4");
export const FOUNDER_SOURCE = join(FOUNDER_DIR, "V4.json");
export const FOUNDER_METRICS = join(FOUNDER_DIR, "METRICS.json");
// Numbers measured at the freeze (slide 9's door and Moltbook counts, the refreshed help count), in METRICS.json's item
// schema; when present it is pinned by V4.json metrics.freezeSha256 and its items add to (or replace) METRICS.json's.
export const FOUNDER_METRICS_FREEZE = join(FOUNDER_DIR, "METRICS-FREEZE.json");
export const FOUNDER_DECK_DIR = join(DECK_ROOT, "founder-v4");
export const FOUNDER_FIGURE_DIR = join(FOUNDER_DECK_DIR, "figures");
export const FOUNDER_OUTPUTS = { script: join(FOUNDER_DIR, "SCRIPT.md"), fillIn: join(FOUNDER_DIR, "FILL-IN.md"), sources: join(FOUNDER_DIR, "SOURCES.md"), cuts: join(FOUNDER_DIR, "CUTS.md") };

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
  const from = basename(path);
  for (const m of list) {
    const id = m.key ?? m.id;
    if (m.value === null || m.value === undefined) continue;
    const window = m.window ?? (m.window_end ? `${m.window_start ?? "?"} to ${m.window_end}` : null);
    for (const [k, v] of [["key", id], ["definition", m.definition], ["scope", m.scope], ["window", window], ["source", m.source]]) {
      if (v === undefined || v === null || v === "") throw new FounderError(`${from}: ${id ?? "an item"} has no ${k}`);
    }
    byId.set(id, { ...m, id, window, display: String(m.display ?? fmt(m.value)), from });
  }
  return { sha256: sha256(bytes), byId };
}
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
// A measured tile's time window as the slide prints it, from the item's own window: "Nov 1, 07:13–14:20 UTC" within a
// day, "Oct 31, 13:46 – Nov 1, 14:20 UTC" across days, "as of Nov 1, 14:20 UTC" with no start; else the window as given.
export function windowShown(m) {
  const at = (iso) => {
    const d = new Date(iso ?? NaN);
    return Number.isNaN(d.getTime()) ? null : { day: `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}`, hm: d.toISOString().slice(11, 16) };
  };
  const a = at(m.window_start), b = at(m.window_end);
  if (a && b) return a.day === b.day ? `${b.day}, ${a.hm}–${b.hm} UTC` : `${a.day}, ${a.hm} – ${b.day}, ${b.hm} UTC`;
  if (b) return `as of ${b.day}, ${b.hm} UTC`;
  return m.window;
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
  const metrics = loadMetrics();
  const freeze = loadMetrics(FOUNDER_METRICS_FREEZE);
  if (freeze.sha256 && v4.metrics.freezeSha256 !== freeze.sha256) throw new FounderError(`METRICS-FREEZE.json is not the file V4.json pins (${String(v4.metrics.freezeSha256).slice(0, 8)}…)`);
  if (!freeze.sha256 && v4.metrics.freezeSha256) throw new FounderError("V4.json pins a METRICS-FREEZE.json that is not there");
  for (const [k, m] of freeze.byId) metrics.byId.set(k, m);
  return { v4, sourceSha256: sha256(bytes), metrics: { ...metrics, freezeSha256: freeze.sha256 } };
}

const SCIENCE = new Set(["chips", "hook", "link", "scorecard"]);
const LAYOUTS = new Set(["joke", "flow", "numbers", "bars", "times", "figure", "tiles", "statement", "closer", "sources", "fallback"]);

// The text a slide shows, for the checks: everything but the pictures.
function shownText(c) {
  const parts = [c.title, c.caption, c.footer, c.line, c.apps, c.punch, c.text, c.label, c.still?.label];
  for (const k of ["chips", "points", "flow", "items"]) parts.push(...(c[k] ?? []));
  for (const s of c.steps ?? []) parts.push(s.verb, s.what);
  for (const t of [...(c.tiles ?? []), ...(c.stats ?? [])]) parts.push(t.value, t.label, t.when, t.head, t.body);
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
export function buildFounderData({ v4, sourceSha256, metrics }, { slot = "3min", final = v4.build === "final" } = {}) {
  if (![undefined, "draft", "final"].includes(v4.build)) throw new FounderError(`V4.json build must be "draft" or "final", not ${JSON.stringify(v4.build)}`);
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
    return m ? { value: m.display, label: wanted[id].label, metric: id, measuring: false, when: windowShown(m) } : { value: v4.metrics.placeholder, label: wanted[id].label, metric: id, measuring: true };
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
      // A QR code is checked by what it encodes: the build decodes the image and refuses one that reads as anything else.
      if (st.payload !== undefined) {
        let read;
        try { read = readQr(readFileSync(join(FOUNDER_DIR, "figures", st.file))).text; } catch (e) { throw new FounderError(`${where}: ${st.file} does not read as a QR code: ${e.message}`); }
        if (read !== st.payload) throw new FounderError(`${where}: ${st.file} encodes ${JSON.stringify(read)}, not ${JSON.stringify(st.payload)}`);
      }
      content.still = { id: s.picture.still, src: `figures/${st.file}`, width: st.width, height: st.height, alt: st.alt, label: s.picture.label ?? null };
    }
    // A figure: served with only its declared edits; its own words follow the public-render and consent rules too; one still
    // pending its reviewer's +1 is marked on the draft and refused at the freeze.
    const figureContent = (id) => {
      const f = v4.figures[id];
      if (!f) throw new FounderError(`${where}: no figure ${id}`);
      if (final && f.pending) throw new FounderError(`${where}: figure ${id} is ${f.pending}; the freeze takes only reviewed figures`);
      const svg = servedFigure(id, f).toString("utf8");
      const alt = /<svg\b[^>]*?\saria-label="([^"]*)"/.exec(svg)?.[1];
      const minFont = Math.min(...[...svg.matchAll(/font-size\s*[:=]\s*["']?\s*([\d.]+)/g)].map((m) => Number(m[1])));
      if (!alt || !Number.isFinite(minFont)) throw new FounderError(`${where}: ${f.file} has no label or no text sizes`);
      // Its drawn words, decoded as they render, face the public-render rule; everything readable in it, the consent rule.
      publicRule(svgText(svg), `${where} figure ${id}`);
      const readable = svgReadable(svg, `${where} figure ${id}`);
      for (const t of v4.teams.unnamed) if (new RegExp(`\\b${t}\\b`, "i").test(readable)) throw new FounderError(`${where} figure ${id} names ${t}, who has not consented`);
      return { id, src: `figures/${f.file}`, width: f.width, height: f.height, scale: f.scale, minFont, alt: decodeXml(alt), pending: f.pending ?? null };
    };
    if (s.picture?.figure) content.figure = figureContent(s.picture.figure);
    // At the freeze (the coordinator, 11:45Z): each tile with a receipt stays, each without one is dropped and the rest
    // reflow; only when no tile has a receipt does the fallback picture take their place. The QR code and the door's
    // address stay on the slide in every case: they are the audience's call to action.
    const measuredTiles = (s.tiles ?? []).filter((t) => t.metric && metrics.byId.get(wanted[t.metric]?.key ?? t.metric));
    if (final && s.finalFallback && (s.tiles ?? []).some((t) => t.metric) && measuredTiles.length === 0) {
      delete content.tiles;
      content.layout = "fallback";
      content.figure = figureContent(s.finalFallback.figure);
      content.footer = s.finalFallback.footer;
    }
    if (s.picture?.still === "qr" && !content.still) throw new FounderError(`${where} lost its QR code`);
    // A QR code comes with the address it encodes, printed on the slide, for anyone who cannot scan it.
    const encodes = content.still && v4.stills[content.still.id].payload;
    if (encodes && !shownText(content).includes(new URL(encodes).host)) throw new FounderError(`${where} shows a QR code without the address it encodes (${new URL(encodes).host})`);
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
      const measured = new Set((content.tiles ?? []).filter((t) => t.metric && !t.measuring).flatMap((t) => numberTokens(`${t.value} ${t.when}`)));
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
    // For SOURCES.md: a metrics fact, and each measured tile, is described by its file's own definition, window and scope.
    const receipt = (keys) => `${[...new Set(keys.map((k) => metrics.byId.get(k).from))].join(" and ")} ${keys.map((k) => { const m = metrics.byId.get(k); return `${k} = ${m.display}${m.unit ? ` ${m.unit}` : ""} (${m.definition.slice(0, 160)}${m.definition.length > 160 ? "…" : ""}; window ${m.window}; scope ${m.scope.slice(0, 120)})`; }).join(" minus ")}`;
    const facts = [
      ...(s.facts ?? []).map((f) => (f.metric ? {
        shows: f.shows,
        source: `${receipt([].concat(f.metric))}${f.derive && f.derive !== "value" && f.derive !== "minus" ? `, shown as its ${f.derive}` : ""}.`,
      } : f)),
      ...(content.tiles ?? []).filter((t) => t.metric && !t.measuring).map((t) => ({ shows: [t.value, t.when], source: `${receipt([wanted[t.metric].key ?? t.metric])}.` })),
    ];
    // The script's heading for the slide: its source heading, else its on-screen title, else its kicker; never empty.
    const heading = [s.heading, content.title, s.kicker].find((x) => typeof x === "string" && x.trim());
    if (!heading) throw new FounderError(`${where} has no heading, title or kicker for the script`);
    return { id: s.id, main: s.main, label: s.main ? `${i + 1} / ${main}` : `B${i - main + 1}`, kicker: s.kicker, heading, content, notes, facts };
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
    options: v4.options ?? [],
    refresh: v4.refresh ?? [],
    slides: slides.map(({ facts, ...s }) => s),
    facts: slides.map((s) => ({ id: s.id, facts: s.facts })),
  };
}

// What a build is: the freeze's final, a draft with numbers still measuring, or a review export with none missing.
export const buildKind = (data) => (!data.deck.draft ? "final" : data.deck.measuring ? "draft" : "review");
export const founderPdfName = (data) => `founder-v4/SentiLab-founder-${data.deck.slot}-${data.deck.cutoffIso.slice(0, 10)}-${data.deck.cutoffIso.slice(11, 13)}${data.deck.cutoffIso.slice(14, 16)}-${buildKind(data)}.pdf`;

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
    `# SentiLab founder pitch (v4${data.deck.slot === "3min" ? "" : "-short"}), ${data.deck.talk}, ${buildKind(data)} ${data.deck.cutoff}`,
    "",
    `The spoken words, exactly as the deck's notes hold them (V4.json sha256 ${data.source.sourceSha256.slice(0, 8)}…). Spine: root's founder pitch (team room 57809), with root's two carried openings (reply to 57809, 07:04Z), the finding beat in root's wording (reply to 57816, 07:14Z) and Carter's additions from 57800. The technical deck (v3.1) is the backup.`,
    "",
    `**Clock:** ${u.talkWords} words = ${u.talkSeconds} s at ${u.wordsPerMinute} wpm, plus ${u.transitionSeconds} s of transitions = ${u.totalSeconds} s of the ${u.talkCapSeconds} s maximum. At ${u.slowWordsPerMinute} wpm: ${u.slowTotalSeconds} s. Numbers and hyphenated words take longer to say than one word each, and the jokes need their pauses: time it out loud once.`,
    "",
    `**With the demo:** ${u.demoSeconds} s of demo makes ${u.withDemoSeconds} s (${mss(u.withDemoSeconds)}) at ${u.wordsPerMinute} wpm, or ${u.slowWithDemoSeconds} s (${mss(u.slowWithDemoSeconds)}) at ${u.slowWordsPerMinute}. Before the talk, do one real timed rehearsal with the actual demo.`,
    "",
  ];
  for (const s of data.slides.filter((x) => x.main)) {
    out.push(`## ${s.label.split(" ")[0]}. ${s.heading} (${s.kicker})`, "", s.notes.text, "", `${s.notes.words} words, ${s.notes.seconds} s at ${u.wordsPerMinute} wpm.${s.notes.cue ? ` Cue: ${s.notes.cue}` : ""}`, "");
  }
  for (const o of data.options) {
    out.push(`## Option, Carter's call: not spoken unless he asks (slide ${o.slide})`, "", o.line, "", `Numbers: ${o.numbers} Qualifiers that travel with it: ${o.qualifiers} Source: ${o.source}`, "");
  }
  if (data.placeholders.length) {
    out.push("## Still measuring", "", "Each shows \"measuring…\" on its slide and is read out only once it is filled:", "");
    for (const p of data.placeholders) out.push(`- ${p.label} (${p.where}; metric \`${p.id}\`)`);
    out.push("");
  }
  return out.join("\n");
}

export function fillInTable(data) {
  const rows = data.placeholders.map((p) => `| ${p.where.replace(/^slide /, "")} | ${p.label}${p.dropped ? " (dropped at the freeze: no receipt)" : ""} | \`${p.id}\` | ${p.need} |`);
  const head = data.deck.draft
    ? `As of ${data.deck.cutoff}. Each shows "measuring…" until docs/sentilab/deck/founder-v4/METRICS.json carries it with its definition, scope, window and source; then rebuild and re-export.`
    : `The freeze, ${data.deck.cutoff}. Each below had no receipt, so its slide does not show it and its words are not read.`;
  return ["# FILL-IN: the founder deck's placeholders", "", head, "",
    "| Slide | Shows | Metric id | Needed |", "|---|---|---|---|", ...(rows.length ? rows : ["| none | | | |"]), "",
    ...(data.refresh.length ? ["## Refresh at the freeze", "", "| Slide | Shows | Why |", "|---|---|---|", ...data.refresh.map((r) => `| ${r.slide} | ${r.what} | ${r.why} |`), ""] : []),
    ...(data.options.length ? ["## Optional, Carter's call: notes only, not on a slide", "", "| Slide | Line, if Carter asks for it | Numbers | Qualifiers | Source |", "|---|---|---|---|---|",
      ...data.options.map((o) => `| ${o.slide} | ${o.line} | ${o.numbers} | ${o.qualifiers} | ${o.source} |`), ""] : [])].join("\n");
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

// Everything the build writes, by path: the deck data, both speaker scripts, FILL-IN, SOURCES and each picture as served.
export function publicOutputs(data, v4, loaded) {
  const { json, js } = serialize(data);
  const out = new Map([[join(FOUNDER_DECK_DIR, "deck-data.json"), json], [join(FOUNDER_DECK_DIR, "deck-data.js"), js]]);
  for (const slot of FOUNDER_SLOTS) out.set(scriptPath(slot), speakerScript(slot === data.deck.slot ? data : buildFounderData(loaded, { slot, final: !data.deck.draft }), v4));
  out.set(FOUNDER_OUTPUTS.fillIn, fillInTable(data));
  out.set(FOUNDER_OUTPUTS.sources, sourcesList(data));
  if (v4.cuts) out.set(FOUNDER_OUTPUTS.cuts, cutsDoc(cutsPlan(loaded)));
  for (const [f, b] of pictureFiles(v4)) out.set(join(FOUNDER_FIGURE_DIR, f), b);
  return out;
}

// A proposed cut of the full talk's spoken words, for review and Carter's timed run (the coordinator, 13:05Z): never
// applied by the build. Each change replaces one exact passage of a main slide's words, once; it may not touch a number
// or a measured placeholder, and slides, figures and the short cut are not touched at all. The clock with the cut is the
// build's own, on a copy of V4.json with the cut applied.
export function cutsPlan(loaded) {
  const { v4 } = loaded;
  const main = v4.slots["3min"].main;
  const check = (c, where) => {
    const s = v4.slides.find((x) => x.id === c.slide);
    if (!s || !main.includes(c.slide)) throw new FounderError(`${where}: ${c.slide} is not a main slide of the full talk`);
    const n = String(s.say).split(c.from).length - 1;
    if (n !== 1) throw new FounderError(`${where}: the passage must appear once in slide ${c.slide}'s words, found ${n}: ${JSON.stringify(c.from)}`);
    if (/\{m:/.test(c.from + c.to)) throw new FounderError(`${where}: a cut may not touch a measured placeholder`);
    if (JSON.stringify(numberTokens(c.from)) !== JSON.stringify(numberTokens(c.to))) throw new FounderError(`${where}: a cut may not touch a number: ${JSON.stringify(c.from)}`);
    const saved = countWords(c.from) - countWords(c.to);
    if (!(saved > 0)) throw new FounderError(`${where}: saves no words`);
    const before = String(s.say);
    return { ...c, n: main.indexOf(c.slide) + 1, saved, before, after: before.replace(c.from, c.to).replace(/\s+/g, " ").trim() };
  };
  const cut = v4.cuts.cut.map((c, i) => check(c, `cut ${i + 1}`));
  const alternates = (v4.cuts.alternates ?? []).map((c, i) => check(c, `alternate ${i + 1}`));
  const cutV4 = structuredClone(v4);
  for (const c of cut) cutV4.slides.find((x) => x.id === c.slide).say = c.after;
  const clock = (w, final) => buildFounderData({ ...loaded, v4: w }, { slot: "3min", final }).budget;
  return {
    note: v4.cuts.note, cut, alternates, saved: cut.reduce((a, c) => a + c.saved, 0),
    clocks: [["Now, draft", clock(v4, false)], ["Now, at the freeze (slide 9's no-numbers line)", clock(v4, true)],
      ["With the cut, draft", clock(cutV4, false)], ["With the cut, at the freeze (slide 9's no-numbers line)", clock(cutV4, true)]],
  };
}
export function cutsDoc(plan) {
  const q = (t) => (t ? `"${t.trim()}"` : "(nothing)");
  return ["# CUTS: a proposed cut of the spoken words, not applied", "", plan.note, "",
    "## The clock", "", "| | Words | Talk and transitions | With the 120 s demo, 150 wpm | With the demo, 135 wpm |", "|---|---|---|---|---|",
    ...plan.clocks.map(([k, u]) => `| ${k} | ${u.talkWords} | ${u.totalSeconds} s | ${u.withDemoSeconds} s (${mss(u.withDemoSeconds)}) | ${u.slowWithDemoSeconds} s (${mss(u.slowWithDemoSeconds)}) |`), "",
    `## The cut: ${plan.saved} words`, "",
    ...plan.cut.flatMap((c, i) => [`### ${i + 1}. Slide ${c.n} (${c.slide}): ${c.saved} words`, "", `- Before: ${q(c.from)}`, `- After: ${q(c.to)}`, `- Why: ${c.why}`, ""]),
    "## Each slide's words, before and after the cut", "",
    ...plan.cut.flatMap((c) => [`### Slide ${c.n} (${c.slide})`, "", `Before: ${c.before}`, "", `After: ${c.after}`, ""]),
    "## Alternates, not in the cut", "", "| Slide | Before | After | Words | Why |", "|---|---|---|---|---|",
    ...plan.alternates.map((c) => `| ${c.n} (${c.slide}) | ${q(c.from)} | ${q(c.to)} | ${c.saved} | ${c.why} |`), ""].join("\n");
}
// Carter's handoff files (the coordinator, 12:31Z): aneta's answer sheet and demo run sheet, beside the scripts and not on
// a slide, exactly as received; V4.json pins each by its sha256.
export function handoffFiles(v4) {
  const files = new Map();
  for (const [file, h] of Object.entries(v4.handoff ?? {})) {
    const path = join(FOUNDER_DIR, file);
    const bytes = existsSync(path) ? readFileSync(path) : null;
    if (!bytes || sha256(bytes) !== h.sha256) throw new FounderError(`handoff file ${file} is not the file V4.json pins (${h.sha256.slice(0, 8)}…)`);
    files.set(path, bytes);
  }
  return files;
}
// XML's five predefined entities and numeric character references: all an SVG without a DTD can hold, and what a markdown
// renderer decodes too. One pass, as a renderer makes ("&amp;#116;" shows as the text "&#116;"); nothing else is expanded.
const XML_NAMED = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'" };
export const decodeXml = (s) => String(s).replace(/&(?:#(\d+)|#x([0-9a-f]+)|(amp|lt|gt|quot|apos));/gi, (m, dec, hex, name) => {
  if (name) return XML_NAMED[name.toLowerCase()];
  const cp = dec !== undefined ? Number(dec) : parseInt(hex, 16);
  return cp > 0 && cp <= 0x10ffff ? String.fromCodePoint(cp) : m;
});
// Character data as XML reads it: a CDATA section stays literal, everything else is decoded once; markup between the
// pieces becomes `sep` ("" inside a text element, so tspans join as they render).
const textContent = (s, sep = "") => String(s).split(/(<!\[CDATA\[[\s\S]*?\]\]>)/).map((p) => (p.startsWith("<![CDATA[") ? p.slice(9, -3) : decodeXml(p.replace(/<[^>]*>/g, sep)))).join("");
// A comment is not rendered: inside an element the text on either side joins ("Vor<!-- -->tex" reads "Vortex").
const dropComments = (s, sep = "") => String(s).replace(/<!--[\s\S]*?-->/g, sep);
// An SVG's drawn words, decoded, one text element per line.
export const svgText = (svg) => [...dropComments(svg).matchAll(/<text\b[^>]*>([\s\S]*?)<\/text>/gi)].map((m) => textContent(m[1])).join(" \n ");
// A start tag, quoted attribute values allowed to hold ">", and its attributes.
const TAG = /<[A-Za-z][^>"']*(?:(?:"[^"]*"|'[^']*')[^>"']*)*>/g;
const ATTR = /([\w:.-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')/g;
// Data URIs in text already decoded: binary image data (base64 PNG, JPEG, GIF, WebP, AVIF, BMP) is not text and is
// dropped; any other is decoded (base64 or percent-encoding) and read, an SVG as an SVG (root, 13:30:15Z: decode the
// attribute value first, then recognize the URI, so an encoded "d&#97;ta:" or ";b&#97;se64" cannot hide it).
const BINARY_IMAGE = /^image\/(?:png|jpe?g|gif|webp|avif|bmp)$/i;
function expandData(text, where) {
  const inner = [];
  const rest = String(text).replace(/data:([^;,"')\s]*)((?:;[^;,"')\s]*)*),([^"')\s]*)/gi, (m, type, params, payload) => {
    const base64 = /;base64$/i.test(params);
    if (base64 && BINARY_IMAGE.test(type)) return " ";
    let body;
    try { body = base64 ? Buffer.from(payload, "base64").toString("utf8") : decodeURIComponent(payload); } catch { body = payload; }
    inner.push(/svg/i.test(type) ? svgReadable(body, `${where} (an embedded image)`) : body);
    return " ";
  });
  return [rest, ...inner].join(" \n ");
}
// Everything a reader can get from an SVG, decoded (root's P2, 12:55:54Z, and 13:30:15Z): the drawn words, titles and
// descriptions, every attribute value decoded once (alt and aria labels among them), the other character data, the tag and
// attribute names, and the comments as written; then every data: URI in those decoded strings, as above. An SVG that
// declares a DTD or an entity is refused: what it would spell is not known without expanding it.
export function svgReadable(svg, where) {
  const src = String(svg);
  if (/<!DOCTYPE|<!ENTITY/i.test(src)) throw new FounderError(`${where} declares a DTD or an entity; it is refused, not expanded`);
  const comments = [...src.matchAll(/<!--([\s\S]*?)-->/g)].map((m) => m[1]);
  const doc = dropComments(src);
  const markup = doc.replace(/<!\[CDATA\[[\s\S]*?\]\]>/g, " ");
  const tags = [...markup.matchAll(TAG)].map((t) => t[0]);
  const inner = (tag) => [...doc.matchAll(new RegExp(`<${tag}\\b[^>]*>([\\s\\S]*?)</${tag}>`, "gi"))].map((m) => textContent(m[1]));
  const parts = [svgText(src), ...inner("title"), ...inner("desc"), textContent(dropComments(src, " "), " \n "), ...comments,
    ...tags.map((t) => t.replace(/"[^"]*"|'[^']*'/g, " ")), ...tags.flatMap((t) => [...t.matchAll(ATTR)].map((a) => decodeXml(a[2] ?? a[3])))];
  return parts.map((p) => expandData(p, where)).join(" \n ");
}
// A team that has not consented to be named appears in nothing the deck publishes, in any letter case (the coordinator,
// 12:31Z: Vortex stays "another team"): the slides and the sources page, a figure's text or alt text, the notes, both
// scripts, FILL-IN, SOURCES and Carter's handoff files, each read as it renders (an SVG decoded as above; markdown and
// the deck data with their character references decoded). The PDFs are exported separately; their own bytes get their own
// scan at the freeze, which this does not replace.
export function checkUnnamed(files, v4) {
  for (const [path, body] of files) {
    if (!/\.(json|js|md|svg)$/.test(path)) continue;
    const where = relative(REPO_ROOT, path);
    const text = path.endsWith(".svg") ? svgReadable(body, where) : expandData(`${body} \n ${decodeXml(body)}`, where);
    for (const t of v4.teams.unnamed) if (new RegExp(`\\b${t}\\b`, "i").test(text)) throw new FounderError(`${where} names ${t}, who has not consented`);
  }
}

export function outputsMatch(data, v4, loaded) {
  const outputs = publicOutputs(data, v4, loaded);
  const pics = [...outputs.keys()].filter((p) => p.startsWith(FOUNDER_FIGURE_DIR)).map((p) => basename(p)).sort();
  return JSON.stringify(readdirSync(FOUNDER_FIGURE_DIR).sort()) === JSON.stringify(pics)
    && [...outputs].every(([p, b]) => existsSync(p) && readFileSync(p).equals(Buffer.isBuffer(b) ? b : Buffer.from(b, "utf8")));
}

function main(args) {
  const loaded = loadFounder();
  const at = args.indexOf("--slot");
  const slot = at >= 0 ? args[at + 1] : "3min";
  const final = args.includes("--final") || loaded.v4.build === "final";
  const data = buildFounderData(loaded, { slot, final });
  const outputs = publicOutputs(data, loaded.v4, loaded);
  checkUnnamed([...outputs, ...handoffFiles(loaded.v4)], loaded.v4);
  if (args.includes("--check")) {
    if (slot !== "3min") throw new FounderError("--check reads the committed build, which is the 3min slot");
    if (!outputsMatch(data, loaded.v4, loaded)) { console.error("deck/founder-v4 or its SCRIPT/FILL-IN/SOURCES differ from a fresh build of V4.json"); process.exit(1); }
    console.log("deck/founder-v4 matches a fresh build");
    return;
  }
  mkdirSync(FOUNDER_FIGURE_DIR, { recursive: true });
  const pics = new Set([...outputs.keys()].filter((p) => p.startsWith(FOUNDER_FIGURE_DIR)).map((p) => basename(p)));
  for (const f of readdirSync(FOUNDER_FIGURE_DIR)) if (!pics.has(f)) throw new FounderError(`deck/founder-v4/figures/${f} is not a picture V4.json names; remove it by hand`);
  for (const [p, b] of outputs) writeFileSync(p, b);
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
