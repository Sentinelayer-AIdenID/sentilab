#!/usr/bin/env node
// Builds the dated factual supplement (facts through 2026-10-31 17:54 UTC) as its own deck, deck/supplement/, with its
// own PDF. It supplements the accepted 15:05 packet. It never rewrites that packet, the daytime deck or any frozen PDF:
// the deck test pins every one of those bytes.
//
//   node scripts/build-deck-supplement.mjs           # verify the supplement, write deck/supplement/deck-data.json + .js
//   node scripts/build-deck-supplement.mjs --check   # exit 1 if the committed files differ from a fresh build
//
// Rules:
//   - Routing: the input is routed by its "format" field. Only sentilab-deck-facts/1 has an adapter. Any other value,
//     or none, stops the build with a visible error. The deck's own script refuses data in any other format, so an
//     unknown format never renders.
//   - Inputs: before either file is parsed, both must match the size and SHA256 pinned in SUPPLEMENT (as delivered at
//     its source commit), and the directory may hold nothing else. The supplement must validate against its schema
//     (json-schema-lite). It must also bind the accepted packet it supplements: commit, manifest hash, cutoff, 26 files
//     and 9 baseline files, each checked against the packet in this repository.
//   - Numbers: integers print as decimal strings. A fixed decimal prints whole + "." + fraction, zero-padded to places,
//     with BigInt and strings only, never floats. A typed unknown stays null and shows "unknown", never 0. claimStatus
//     and evidenceClass print exactly as delivered. Titles, display text and qualifications print verbatim except for
//     the fixed public-render substitutions below; the output records each one with its count. No value is ever read
//     out of prose.
//   - Dates: each item keeps its own sourceAt (shown "unknown" when null) and its own observedAt, and both are at or
//     before the fact cutoff. The packaging time is never a fact date and is not rendered. Nothing is promoted: each
//     card shows its claim status and evidence class next to its facts, and a slide's heading must hold for every item
//     on it (GROUPS).
// The build is deterministic: no wall-clock time is read.
import { createHash } from "node:crypto";
import { existsSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { validateSchema } from "./json-schema-lite.mjs";
import { DECK_ROOT, NOT_PUBLIC, PACKETS, PDF_DIR, PacketError, loadPacket, utc } from "./build-deck-data.mjs";

// The supplement this deck renders, pinned as delivered at its source commit.
export const SUPPLEMENT = {
  id: "supplement-2026-10-31-1754-v2",
  sourceCommit: "d3576e328e0bdb3ca698aa114b408105d092f017",
  files: {
    "SUPPLEMENT.json": { bytes: 46290, sha256: "a61cb1add9feba5b2671d77924c2ad3262704468c602b4717413d0a2d07545d6" },
    "SUPPLEMENT.schema.json": { bytes: 10286, sha256: "c6af7ed73598c7efa36598ea6f25340608600017714e185d565181d5cb8cfe25" },
  },
  // The accepted packet it supplements: copied into this repository byte for byte from that commit.
  acceptedPacket: {
    id: "progress-2026-10-31-daytime-1505", commit: "405332861cfc2303019523c831b35c9b2b89da2d",
    manifestSha256: "674276ed0e9358e8f162cbec0b1660b4b623c99693c2fb4b17390cf12693ca95", fileCount: 26, baselineFiles: 9,
  },
};
export const FORMAT = "sentilab-deck-facts/1";
export const DATA_SCHEMA = "sentilab-deck-supplement-data/1";
export const SUPP_DIR = join(PDF_DIR, SUPPLEMENT.id);
export const SUPP_DECK_DIR = join(DECK_ROOT, "supplement");
export const suppPdfName = () => `SentiLab-deck-${SUPPLEMENT.id}.pdf`;
// The daytime deck and its PDF (PR 63: renderer and PDF +1 from the lead reviewer at f515b44) are frozen from here on.
// The deck test pins these bytes, and the export script refuses to write any of these paths.
export const FROZEN_DAYTIME = {
  "deck/daytime/index.html": "56a87bc2e1e02b9a50d4893241b7e1e8badc3637038f55e4d00d3460b873a492",
  "deck/daytime/deck.js": "f77fb9074af4160623c9d1a5de689143c9da717ca5fe34cd216321728403f485",
  "deck/daytime/deck.css": "ba51dcbdf1f849f409c46ca9d5e4b5a091678573c8edb368650563b7a59d3e58",
  "deck/daytime/deck-data.json": "6e5e28d5ffd56779351e691a9ab6015df54c69f08c478ce7c635e6aa8eb3b9ab",
  "deck/daytime/deck-data.js": "c5f1c1e1ba978280212dbdbde5ef216c94e7678da44d41d22afd264727ed3997",
  "docs/sentilab/deck/SentiLab-deck-2026-10-31-daytime-1505.pdf": "f2a87277faea940b4bb2c847e76204a676c79e25dcb148a1b9f487e446a8b7f8",
};

// ── public render ───────────────────────────────────────────────────────────────────────────────────────────────────
// The only edits to any delivered sentence. Reviewer and project names stay in the delivered file, and the slides name
// roles instead. Every rule must match at least once, so a changed supplement cannot pass with a stale table.
export const SUPP_SUBSTITUTIONS = [
  [/\bAneta v3\b/g, "The informed peer model (v3)"],
  [/\bRoot\b/g, "The lead reviewer"],
  [/\b(in|during|from) root\b/g, "$1 the lead"],
  [/\ban ENGRAM\b/g, "a memory-system"],
  [/^Ascend\b/g, "Headroom"],
  [/\bAscend\b/g, "headroom"],
  [/\bAzure\b/g, "cloud"],
];
// The deck's public-render rules plus the project name. The long-number rule (it catches run and room numbers) skips
// the fraction digits of an exact decimal such as 471.654559.
const LONG_NUMBER = String(/\b\d{6,}\b/);
export const SUPP_NOT_PUBLIC = [...NOT_PUBLIC.filter((re) => String(re) !== LONG_NUMBER), /(?<![.\d])\b\d{6,}\b/, /\bENGRAM\b/i];
export function assertPublic(text, where) {
  const bad = SUPP_NOT_PUBLIC.find((re) => re.test(text));
  if (bad) throw new PacketError(`public-render rule ${bad} fails in ${where}: ${JSON.stringify(text)}`);
  return text;
}
function suppText(text, where, counts) {
  let out = String(text);
  for (const [re, to] of SUPP_SUBSTITUTIONS) {
    const n = out.match(re)?.length ?? 0;
    if (n) { counts.set(String(re), (counts.get(String(re)) ?? 0) + n); out = out.replace(re, to); }
  }
  return assertPublic(out, where);
}

// ── exact numbers ───────────────────────────────────────────────────────────────────────────────────────────────────
const isCount = (v) => Number.isSafeInteger(v) && v >= 0;
// whole + "." + fraction zero-padded to places, with BigInt and strings only: {0, 2, 2} is 0.02.
export function fixedDecimal(v, where = "fixed decimal") {
  if (!v || typeof v !== "object") throw new PacketError(`${where} is not a {whole, fraction, places} object`);
  const { whole, fraction, places } = v;
  if (!isCount(whole) || !isCount(fraction) || !Number.isSafeInteger(places) || places < 1 || places > 15) {
    throw new PacketError(`${where}: whole and fraction must be non-negative safe integers and places 1 to 15`);
  }
  const f = BigInt(fraction);
  if (f >= 10n ** BigInt(places)) throw new PacketError(`${where}: fraction ${f} does not fit in ${places} places`);
  return `${BigInt(whole)}.${f.toString().padStart(places, "0")}`;
}
// A reviewed display for every unit the supplement uses. A unit without one stops the build.
const UNITS = {
  count: (s) => s, seconds: (s) => `${s} s`, cpu_seconds: (s) => `${s} CPU-s`, bytes: (s) => `${s} bytes`,
  basis_points: (s) => `${s} bp`, millimetres: (s) => `${s} mm`, usd: (s) => `USD ${s}`, http_status: (s) => s,
  boolean: (s) => s,
};
export function factDisplay(f, where) {
  const unit = Object.hasOwn(UNITS, f.unit) ? UNITS[f.unit] : null;
  if (!unit) throw new PacketError(`${where}: unit ${JSON.stringify(f.unit)} has no reviewed display`);
  if ((f.kind === "boolean") !== (f.unit === "boolean") && f.kind !== "unknown") throw new PacketError(`${where}: kind ${f.kind} does not fit unit ${f.unit}`);
  switch (f.kind) {
    case "integer": if (!isCount(f.value)) throw new PacketError(`${where}: an integer fact must be a non-negative safe integer`); return unit(BigInt(f.value).toString());
    case "fixed_decimal": return unit(fixedDecimal(f.value, where));
    case "boolean": if (typeof f.value !== "boolean") throw new PacketError(`${where}: a boolean fact must be true or false`); return f.value ? "true" : "false";
    case "unknown": if (f.value !== null) throw new PacketError(`${where}: an unknown fact must be null`); return "unknown";
    default: throw new PacketError(`${where}: fact kind ${JSON.stringify(f.kind)} has no reviewed display`);
  }
}
// A fact's label is its key spelled out. Facts about the lead reviewer's own review read "(lead review)".
const WORDS = {
  root: "lead", engram: "memory-system", cpu: "CPU", usd: "USD", ci: "CI", cli: "CLI", mcp: "MCP", csp: "CSP", gpu: "GPU",
  html: "HTML", http: "HTTP", p2: "P2", pr: "PR", pr57: "PR57", slab018: "SLAB-018", slab047: "SLAB-047", slab047b: "SLAB-047b",
  round4: "round-4",
};
const PHRASES = [[/\bnon GPU\b/g, "non-GPU"], [/\bheld out five arm\b/g, "held-out five-arm"], [/\bexit zero\b/g, "exit-zero"], [/\bfollowup\b/g, "follow-up"]];
export function factLabel(key) {
  const words = key.split("_");
  const byLead = words[0] === "root";
  let text = (byLead ? words.slice(1) : words).map((w) => (Object.hasOwn(WORDS, w) ? WORDS[w] : w)).join(" ");
  for (const [from, to] of PHRASES) text = text.replace(from, to);
  return assertPublic(byLead ? `${text} (lead review)` : text, `label of ${key}`);
}

// ── the slides: every item on exactly one slide, by stable id ───────────────────────────────────────────────────────
// Each placement pins the claim status the slide's heading was written for, plus any typed fact the heading states. If
// the supplement changes either, the build stops until the heading is reviewed again: a heading never outruns its cards.
export const GROUPS = {
  merged: { "pr55": "merged_source_verified", "pr62": "bounded_runtime_verified" },
  withdrawal: { "withdrawal-notice": "bounded_runtime_verified", "pr61": "merged_source_verified", "pr60": "source_accepted" },
  accepted: { "pr59": "design_accepted", "web709": "source_accepted" },
  pending: { "pr56": "repair_pending", "keeper": "repair_pending" },
  observed: { "loop-stopped": "observed", "help-room": "observed" },
  agentsite: { "agent-site-priority": "directed_pending", "science-content": "private_content_delivered" },
  science: { "aneta-v3": "peer_reported", "reference-consistency": "retained_author_results" },
  gate: { "native-gate": "proposed_not_released", "open-science": "open" },
  scope: { "baseline": "preserved", "ascend-history": "retained_inconclusive" },
  history: { "gb10-history": "closed_historical", "costs": "unknown" },
};
// Typed facts a heading states: "Merged, with the merge verified" and "merge not verified at the cutoff".
export const GROUP_FACTS = { merged: { merge_verified: true }, accepted: { merge_verified: false } };
const factValue = (it, key) => it.facts.find((f) => f.key === key)?.value;

// ── format routing ──────────────────────────────────────────────────────────────────────────────────────────────────
const FORMATS = new Map([[FORMAT, adaptDeckFactsV1]]);
export function routeFormat(doc) {
  const format = doc !== null && typeof doc === "object" && !Array.isArray(doc) ? doc.format : undefined;
  const adapt = typeof format === "string" && FORMATS.has(format) ? FORMATS.get(format) : null;
  if (!adapt) throw new PacketError(`unknown deck-facts format ${JSON.stringify(format)}: this renderer supports only ${[...FORMATS.keys()].join(", ")}, and nothing is rendered`);
  return adapt;
}

// ── inputs ──────────────────────────────────────────────────────────────────────────────────────────────────────────
const sha256 = (b) => createHash("sha256").update(b).digest("hex");
const DATE_TIME = { type: "string", format: "date-time" };
const time = (s, where) => {
  if (validateSchema(DATE_TIME, s).length) throw new PacketError(`${where}: ${JSON.stringify(s)} is not an RFC 3339 date-time`);
  return Date.parse(s);
};
const countFiles = (d) => readdirSync(d, { withFileTypes: true }).reduce((n, e) => n + (e.isDirectory() ? countFiles(join(d, e.name)) : 1), 0);

export function loadSupplement(dir = SUPP_DIR, packets = PACKETS, pin = SUPPLEMENT) {
  if (!existsSync(dir)) throw new PacketError(`supplement directory ${pin.id} is missing`);
  const extra = readdirSync(dir).filter((f) => !Object.hasOwn(pin.files, f));
  if (extra.length) throw new PacketError(`${pin.id}: unexpected files ${extra.join(", ")}`);
  const bytes = {};
  for (const [f, want] of Object.entries(pin.files)) {
    const p = join(dir, f);
    if (!existsSync(p)) throw new PacketError(`${pin.id}: ${f} is missing`);
    const b = readFileSync(p);
    if (b.length !== want.bytes) throw new PacketError(`${pin.id}: ${f} is ${b.length} bytes, not the delivered ${want.bytes}`);
    if (sha256(b) !== want.sha256) throw new PacketError(`${pin.id}: ${f} does not match its delivered SHA256`);
    bytes[f] = b;
  }
  const parse = (f) => { try { return JSON.parse(bytes[f].toString("utf8")); } catch (e) { throw new PacketError(`${pin.id}: ${f} is not JSON (${e.message})`); } };
  const doc = parse("SUPPLEMENT.json");
  const adapt = routeFormat(doc);
  const errors = validateSchema(parse("SUPPLEMENT.schema.json"), doc);
  if (errors.length) throw new PacketError(`${pin.id}: SUPPLEMENT.json fails its schema: ${errors.slice(0, 5).join("; ")}`);
  // The accepted packet it supplements must be the one in this repository, unchanged.
  const a = pin.acceptedPacket, prior = doc.priorPacket;
  if (prior.commit !== a.commit || prior.manifestSha256 !== a.manifestSha256 || prior.fileCount !== a.fileCount || prior.baselineFiles !== a.baselineFiles) {
    throw new PacketError(`${pin.id}: it supplements a different packet than the accepted ${a.id}`);
  }
  const packet = loadPacket(a.id, packets);
  if (packet.hashes.manifestSha256 !== prior.manifestSha256) throw new PacketError(`${a.id}: its manifest is not the one the supplement binds`);
  if (Date.parse(packet.day.asOf.includedEvidenceThrough) !== time(prior.factualCutoff, "priorPacket.factualCutoff")) {
    throw new PacketError(`${a.id}: its fact cutoff is not the one the supplement binds`);
  }
  const pdir = join(packets, a.id);
  if (countFiles(pdir) !== prior.fileCount || countFiles(join(pdir, "baseline")) !== prior.baselineFiles) {
    throw new PacketError(`${a.id}: its file counts differ from the supplement's binding`);
  }
  return { doc, adapt, hashes: Object.fromEntries(Object.entries(bytes).map(([f, b]) => [f, sha256(b)])), packet, pin };
}

// ── sentilab-deck-facts/1 ───────────────────────────────────────────────────────────────────────────────────────────
function adaptDeckFactsV1(doc) {
  const cutoff = time(doc.asOf, "asOf");
  if (time(doc.packagedAt, "packagedAt") < cutoff) throw new PacketError("packagedAt is before the fact cutoff");
  const counts = new Map(), items = new Map();
  doc.items.forEach((it, k) => {
    if (items.has(it.id)) throw new PacketError(`supplement item ${it.id} is listed twice`);
    if (it.asOf !== doc.asOf) throw new PacketError(`${it.id}: asOf ${it.asOf} is not the supplement's fact cutoff`);
    const observed = time(it.observedAt, `${it.id}.observedAt`);
    const source = it.sourceAt === null ? null : time(it.sourceAt, `${it.id}.sourceAt`);
    if (observed > cutoff) throw new PacketError(`${it.id}: observedAt is after the fact cutoff`);
    if (source !== null && source > observed) throw new PacketError(`${it.id}: sourceAt is after its observedAt`);
    const keys = new Set();
    const facts = it.facts.map((f) => {
      if (keys.has(f.key)) throw new PacketError(`${it.id}: fact ${f.key} is listed twice`);
      keys.add(f.key);
      return { key: f.key, label: factLabel(f.key), kind: f.kind, unit: f.unit, value: f.value, display: factDisplay(f, `${it.id}.${f.key}`) };
    });
    items.set(it.id, {
      k, id: it.id,
      title: suppText(it.title, `${it.id}.title`, counts),
      display: suppText(it.display, `${it.id}.display`, counts),
      qualifications: it.qualifications.map((q, i) => suppText(q, `${it.id}.qualifications[${i}]`, counts)),
      claimStatus: assertPublic(it.claimStatus, `${it.id}.claimStatus`), evidenceClass: assertPublic(it.evidenceClass, `${it.id}.evidenceClass`),
      sourceAt: it.sourceAt, observedAt: it.observedAt,
      source: it.sourceAt === null ? null : utc(it.sourceAt), observed: utc(it.observedAt),
      facts,
    });
  });
  for (const [re] of SUPP_SUBSTITUTIONS) if (!counts.has(String(re))) throw new PacketError(`public-render substitution ${re} no longer matches anything: review the table`);
  // Every item sits on exactly one slide, and every slide's heading holds for each of its items.
  const placed = Object.values(GROUPS).flatMap((g) => Object.keys(g));
  const unplaced = [...items.keys()].filter((id) => !placed.includes(id));
  const unknown = placed.filter((id) => !items.has(id));
  const twice = placed.filter((id, i) => placed.indexOf(id) !== i);
  if (unplaced.length || unknown.length || twice.length) {
    throw new PacketError(`every supplement item must sit on exactly one slide (unplaced: ${unplaced.join(", ") || "none"}; unknown: ${unknown.join(", ") || "none"}; twice: ${twice.join(", ") || "none"})`);
  }
  for (const [name, g] of Object.entries(GROUPS)) {
    for (const [id, status] of Object.entries(g)) {
      const it = items.get(id);
      if (it.claimStatus !== status) throw new PacketError(`${id} is now ${it.claimStatus}, not the ${status} the ${name} slide heading was written for`);
      for (const [key, want] of Object.entries(GROUP_FACTS[name] ?? {})) {
        if (factValue(it, key) !== want) throw new PacketError(`${id}: ${key} is not ${want}, as the ${name} slide heading states`);
      }
    }
  }
  return { cutoff: doc.asOf, items, counts };
}

// ── deck data ───────────────────────────────────────────────────────────────────────────────────────────────────────
export function buildSupplementData({ doc, adapt, hashes, packet, pin = SUPPLEMENT }) {
  const { cutoff, items, counts } = adapt(doc);
  const nFacts = [...items.values()].reduce((n, i) => n + i.facts.length, 0);
  const prior = doc.priorPacket;
  const at = (iso) => utc(iso);
  const fact = (value, display, iso, kind, source, ref) => ({ value, display, asOf: at(iso), asOfKind: kind, source, ref });
  const facts = {
    "supp.cutoff": fact(at(cutoff), at(cutoff), cutoff, "cutoff", "supplement", "asOf"),
    "supp.items": fact(items.size, String(items.size), cutoff, "cutoff", "supplement", "items"),
    "supp.facts": fact(nFacts, String(nFacts), cutoff, "cutoff", "supplement", "items[].facts"),
    "supp.priorCutoff": fact(at(prior.factualCutoff), at(prior.factualCutoff), prior.factualCutoff, "cutoff", "accepted packet", "priorPacket.factualCutoff"),
    "supp.priorFiles": fact(prior.fileCount, String(prior.fileCount), prior.factualCutoff, "cutoff", "accepted packet", "priorPacket.fileCount"),
    "supp.priorBaseline": fact(prior.baselineFiles, String(prior.baselineFiles), prior.factualCutoff, "cutoff", "accepted packet", "priorPacket.baselineFiles"),
  };
  const groups = Object.fromEntries(Object.entries(GROUPS).map(([g, placed]) => [g, Object.keys(placed).map((id) => items.get(id))]));
  const say = (list) => list.map((i) => `${i.title}. ${i.display} Limits: ${i.qualifications.join(" ")}`).join(" ");
  const notes = [
    ["cover", `Facts through ${at(cutoff)}: ${items.size} dated items with ${nFacts} typed facts. This supplements the accepted packet, whose facts run through ${at(prior.factualCutoff)}, and changes none of it. Each card keeps its own claim status, evidence class, source time and observed or checkpoint time. A typed unknown shows unknown, never zero.`],
    ...Object.keys(GROUPS).map((g) => [g, say(groups[g])]),
  ].map(([slide, text]) => ({ slide: `supp-${slide}`, target: "backup", text: assertPublic(text, `notes.${slide}`) }));
  return {
    schema: DATA_SCHEMA,
    deck: { title: "SentiLab", version: "dated supplement v2", event: "ScienceClaw hackathon" },
    source: {
      format: doc.format, supplementId: pin.id, sourceCommit: pin.sourceCommit,
      supplementSha256: hashes["SUPPLEMENT.json"], schemaSha256: hashes["SUPPLEMENT.schema.json"], factCutoff: at(cutoff),
      acceptedPacket: { ...pin.acceptedPacket, factCutoff: at(prior.factualCutoff), loadedManifestSha256: packet.hashes.manifestSha256 },
      publicRender: SUPP_SUBSTITUTIONS.map(([re, to]) => ({ rule: String(re), to, count: counts.get(String(re)) ?? 0 })),
    },
    facts,
    lists: { groups },
    notes,
  };
}

export const buildSupplement = (dir = SUPP_DIR, packets = PACKETS, pin = SUPPLEMENT) => buildSupplementData(loadSupplement(dir, packets, pin));
export const serializeSupplement = (data) => {
  const json = JSON.stringify(data, null, 2) + "\n";
  return { json, js: `// Generated by build-deck-supplement. Same object as deck-data.json, for file:// viewing.\nwindow.DECK_DATA = ${json.trimEnd()};\n` };
};

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const { json, js } = serializeSupplement(buildSupplement());
    const jsonPath = join(SUPP_DECK_DIR, "deck-data.json"), jsPath = join(SUPP_DECK_DIR, "deck-data.js");
    if (process.argv.includes("--check")) {
      const same = (p, s) => existsSync(p) && readFileSync(p, "utf8") === s;
      if (!same(jsonPath, json) || !same(jsPath, js)) { console.error("supplement deck-data is stale: run node scripts/build-deck-supplement.mjs"); process.exit(1); }
      console.log(`supplement deck-data matches ${SUPPLEMENT.id}`);
    } else {
      writeFileSync(jsonPath, json);
      writeFileSync(jsPath, js);
      const d = JSON.parse(json);
      console.log(`wrote supplement deck-data.json + deck-data.js from ${SUPPLEMENT.id} (${d.facts["supp.items"].value} items, ${d.facts["supp.facts"].value} facts)`);
    }
  } catch (e) {
    if (!(e instanceof PacketError)) throw e;
    console.error(`build-deck-supplement: ${e.message}`);
    process.exit(1);
  }
}
