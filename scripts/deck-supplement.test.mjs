// node --test scripts/deck-supplement.test.mjs   (CI runs it through scripts/deck-data.test.mjs, which imports this file)
// The dated supplement deck (deck/supplement/) shows only what the delivered supplement says, and changes nothing else:
//   - only the sentilab-deck-facts/1 format is routed, and any other format stops the build and the render visibly;
//   - both files match their delivered size and SHA256, the supplement validates against its schema, and it binds the
//     accepted 15:05 packet in this repository;
//   - fixed decimals print digit for digit (BigInt and strings, never floats); a typed unknown shows "unknown", never 0;
//   - claim status, evidence class, qualifications and each item's own times print exactly; nothing is redated, the
//     packaging time is never shown, and no heading outruns its cards;
//   - public-render rules; the accepted packet, the daytime deck and every earlier PDF stay byte-identical.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { cpSync, existsSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { join, relative, sep } from "node:path";
import { spawnSync } from "node:child_process";
import vm from "node:vm";

import { DECK_DIR, FROZEN_V1, PACKETS, PDF_DIR, REPO_ROOT, PacketError, loadPacket, utc } from "./build-deck-data.mjs";
import {
  DATA_SCHEMA, FORMAT, FROZEN_DAYTIME, GROUPS, GROUP_FACTS, SUPPLEMENT, SUPP_DECK_DIR, SUPP_DIR, SUPP_NOT_PUBLIC, SUPP_SUBSTITUTIONS,
  assertPublic, buildSupplementData, factDisplay, factLabel, fixedDecimal, loadSupplement, routeFormat, serializeSupplement, suppPdfName,
} from "./build-deck-supplement.mjs";
import { validateSchema } from "./json-schema-lite.mjs";

// Setup errors are kept, never thrown at import, so each test reports for itself (and the daytime file still runs).
const attempt = (f) => { try { return [f(), null]; } catch (e) { return [null, e]; } };
const sha = (b) => createHash("sha256").update(b).digest("hex");
const clone = (o) => JSON.parse(JSON.stringify(o));
const readJson = (p) => JSON.parse(readFileSync(p, "utf8"));
const [SRC] = attempt(() => readJson(join(SUPP_DIR, "SUPPLEMENT.json")));            // the delivered file, as delivered
const [SCHEMA] = attempt(() => readJson(join(SUPP_DIR, "SUPPLEMENT.schema.json")));
const [committed] = attempt(() => readJson(join(SUPP_DECK_DIR, "deck-data.json")));
const [loaded, loadError] = attempt(() => loadSupplement());
const [data, buildError] = loaded ? attempt(() => buildSupplementData(loaded)) : [null, loadError];

// The daytime engine, unchanged, plus the supplement plugin: a private instance, so the daytime tests keep their own.
const require = createRequire(import.meta.url);
const ENGINE = join(DECK_DIR, "deck.js"), PLUGIN = join(SUPP_DECK_DIR, "supplement.js");
const [Deck, engineError] = attempt(() => {
  const engine = require(ENGINE);
  delete require.cache[require.resolve(ENGINE)];
  const plugin = require(PLUGIN);
  plugin.install(engine);
  return Object.assign(engine, { plugin });
});
const html = readFileSync(join(SUPP_DECK_DIR, "index.html"), "utf8");
const deckMain = html.match(/<main id="deck"[^>]*>([\s\S]*)<\/main>/)?.[1] ?? "";
const slidesOf = (h) => [...h.matchAll(/<section\b([^>]*)>([\s\S]*?)<\/section>/g)].map((m) => ({
  id: /\bid="([^"]+)"/.exec(m[1])[1], label: /\bdata-label="([^"]+)"/.exec(m[1])?.[1], notes: /\bdata-notes="([^"]+)"/.exec(m[1])?.[1], html: m[2],
}));
const render = (d) => slidesOf(Deck.renderHtml(deckMain, d));
const [rendered, renderError] = data && Deck ? attempt(() => render(data)) : [[], buildError ?? engineError];
const decode = (s) => s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, "&");
const visible = (h) => decode(h.replace(/<[^>]+>/g, " ")).replace(/\s+/g, " ").replace(/ ([.,;:!?)])/g, "$1").trim();
const notesText = (data?.notes ?? []).map((n) => n.text).join("\n");
const item = (d, id) => d.items.find((i) => i.id === id);
const factOf = (d, id, key) => item(d, id).facts.find((f) => f.key === key);

// A modified copy of the delivered document, built without the file pin, so only the rule under test can fail.
const rebuild = (mutate) => { const doc = clone(SRC); mutate(doc); return buildSupplementData({ ...loaded, doc, adapt: routeFormat(doc) }); };
// A scratch copy of the supplement directory, with a pin for the edited bytes unless the test keeps the delivered pin.
function scratch(edit = () => {}, { keepPin = false, pin: pinEdit = (p) => p } = {}) {
  const root = mkdtempSync(join(tmpdir(), "deck-supp-"));
  const dir = join(root, SUPPLEMENT.id);
  cpSync(SUPP_DIR, dir, { recursive: true });
  edit({ dir, doc: (f) => { const d = readJson(join(dir, "SUPPLEMENT.json")); f(d); writeFileSync(join(dir, "SUPPLEMENT.json"), JSON.stringify(d, null, 2) + "\n"); } });
  const files = Object.fromEntries(Object.keys(SUPPLEMENT.files).filter((f) => existsSync(join(dir, f))).map((f) => {
    const b = readFileSync(join(dir, f)); return [f, { bytes: b.length, sha256: sha(b) }];
  }));
  const pin = pinEdit(keepPin ? SUPPLEMENT : { ...SUPPLEMENT, files: { ...SUPPLEMENT.files, ...files }, acceptedPacket: { ...SUPPLEMENT.acceptedPacket } });
  return { dir, pin, cleanup: () => rmSync(root, { recursive: true, force: true }) };
}
const rejects = (s, message) => {
  try { assert.throws(() => loadSupplement(s.dir, PACKETS, s.pin), (e) => e instanceof PacketError && message.test(e.message), String(message)); }
  finally { s.cleanup(); }
};

// ── independent oracles: the test's own reviewed tables, never the builder's ────────────────────────────────────────
const REVIEWED_SUBSTITUTIONS = [
  ["/\\bAneta v3\\b/g", "The informed peer model (v3)", 1], ["/\\bRoot\\b/g", "The lead reviewer", 4],
  ["/\\b(in|during|from) root\\b/g", "$1 the lead", 3], ["/\\ban ENGRAM\\b/g", "a memory-system", 1], ["/^Ascend\\b/g", "Headroom", 1],
  ["/\\bAscend\\b/g", "headroom", 1], ["/\\bAzure\\b/g", "cloud", 1],
];
const subst = (t) => SUPP_SUBSTITUTIONS.reduce((s, [re, to]) => s.replace(re, to), t);
const UNIT_TEXT = { count: "", seconds: " s", cpu_seconds: " CPU-s", bytes: " bytes", basis_points: " bp", millimetres: " mm", http_status: "", boolean: "" };
// Strings only: "{494, 18953860500187, 14}" is "494" + "." + the fraction digits zero-padded to 14 places.
const oracle = (f) => {
  if (f.kind === "unknown") return "unknown";
  if (f.kind === "boolean") return String(f.value);
  const n = f.kind === "fixed_decimal" ? `${f.value.whole}.${String(f.value.fraction).padStart(f.value.places, "0")}` : String(f.value);
  return f.unit === "usd" ? `USD ${n}` : `${n}${UNIT_TEXT[f.unit]}`;
};
// The parts of one rendered card, read from the generated markup.
const cardsOf = (h) => [...h.matchAll(/<article class="sp-c" data-k="(\d+)">([\s\S]*?)<\/article>/g)].map(([, k, c]) => ({
  k: Number(k), html: c,
  title: decode(/<h3>([\s\S]*?)<\/h3>/.exec(c)?.[1] ?? ""),
  status: decode(/<code class="sp-st">([\s\S]*?)<\/code>/.exec(c)?.[1] ?? ""),
  evidence: decode(/<code class="sp-ev">([\s\S]*?)<\/code>/.exec(c)?.[1] ?? ""),
  times: [...c.matchAll(/<span class="sp-t( nullv)?">([\s\S]*?)<\/span>/g)].map((m) => decode(m[2])),
  display: decode(/<p class="sp-d">([\s\S]*?)<\/p>/.exec(c)?.[1] ?? ""),
  quals: [...c.matchAll(/<li>([\s\S]*?)<\/li>/g)].map((m) => decode(m[1])),
  facts: [...c.matchAll(/<dt>([\s\S]*?)<\/dt><dd( class="nullv")?>([\s\S]*?)<\/dd>/g)].map((m) => ({ label: decode(m[1]), shown: decode(m[3]), nullv: !!m[2] })),
  rest: visible(c.replace(/<h3>[\s\S]*?<\/h3>|<code class="sp-(?:st|ev)">[\s\S]*?<\/code>|<span class="sp-t[^"]*">[\s\S]*?<\/span>|<p class="sp-d">[\s\S]*?<\/p>|<li>[\s\S]*?<\/li>|<dt>[\s\S]*?<\/dt>|<dd\b[^>]*>[\s\S]*?<\/dd>/g, " ")),
}));
const allCards = () => rendered.flatMap((s) => cardsOf(s.html).map((c) => ({ ...c, slide: s.id })));
const BANNED = [
  ...SUPP_NOT_PUBLIC,
  /\bGPT/i, /\bOpus\b/i, /\bSonnet\b/i, /\bHaiku\b/i, /\bCopilot\b/i, /\bReachy\b/i, /\bHuawei\b/i, /\bAneta\b/i,
  /pocket-forge/i, /claude-warden/i, /gpt-astra/i, /\bnightshift\b/i, /\bcodex\b/i, /\bfable\b/i, /\bScienceClaw #/i,
  /(?:^|[\s"'(=])\/?(?:docs|web|scripts|contracts|sentilab_core|Users|home|tmp)\//, /\binvite\b|\binvitation link\b/i,
];
const scan = (text) => BANNED.filter((re) => re.test(text)).map(String);

// ── 1. inputs ───────────────────────────────────────────────────────────────────────────────────────────────────────
test("the delivered supplement loads, verifies, builds and renders", () => {
  assert.equal(loadError, null, `the supplement does not load: ${loadError?.message}`);
  assert.equal(buildError, null, `the deck data does not build: ${buildError?.message}`);
  assert.equal(engineError, null, `the engine or plugin does not load: ${engineError?.message}`);
  assert.equal(renderError, null, `the deck does not render: ${renderError?.message}`);
});

test("both files match their delivered size and SHA256 before either is parsed, and nothing else sits beside them", () => {
  for (const [f, want] of Object.entries(SUPPLEMENT.files)) {
    const b = readFileSync(join(SUPP_DIR, f));
    assert.equal(b.length, want.bytes, f);
    assert.equal(sha(b), want.sha256, f);
  }
  assert.deepEqual(Object.keys(SUPPLEMENT.files).sort(), ["SUPPLEMENT.json", "SUPPLEMENT.schema.json"]);
  assert.equal(SUPPLEMENT.sourceCommit, "d3576e328e0bdb3ca698aa114b408105d092f017");
  assert.equal(SUPPLEMENT.files["SUPPLEMENT.json"].sha256, "a61cb1add9feba5b2671d77924c2ad3262704468c602b4717413d0a2d07545d6");
  assert.equal(SUPPLEMENT.files["SUPPLEMENT.schema.json"].sha256, "c6af7ed73598c7efa36598ea6f25340608600017714e185d565181d5cb8cfe25");
  // One changed byte, same size: refused before parsing (the bytes are not even JSON-checked).
  rejects(scratch(({ dir }) => { const p = join(dir, "SUPPLEMENT.json"); const b = readFileSync(p); b[b.indexOf(0x37)] = 0x38; writeFileSync(p, b); }, { keepPin: true }), /does not match its delivered SHA256/);
  rejects(scratch(({ dir }) => writeFileSync(join(dir, "SUPPLEMENT.json"), readFileSync(join(dir, "SUPPLEMENT.json"), "utf8") + " "), { keepPin: true }), /bytes, not the delivered/);
  rejects(scratch(({ dir }) => rmSync(join(dir, "SUPPLEMENT.schema.json")), { keepPin: true }), /SUPPLEMENT\.schema\.json is missing/);
  rejects(scratch(({ dir }) => writeFileSync(join(dir, "PAGE-COPY.md"), "prose")), /unexpected files PAGE-COPY\.md/);
  rejects(scratch(({ dir }) => writeFileSync(join(dir, "SUPPLEMENT.json"), "{not json")), /is not JSON/);
  assert.throws(() => loadSupplement(join(tmpdir(), "no-such-supplement")), /supplement directory .* is missing/);
});

test("the supplement validates against its schema with the dependency-free validator, which rejects each violation", () => {
  assert.deepEqual(validateSchema(SCHEMA, SRC), []);
  const pr62 = (d) => item(d, "pr62");
  const violations = {
    "unknown format": (d) => { d.format = "sentilab-deck-facts/2"; },
    "extra top-level field": (d) => { d.supersedes = "everything"; },
    "missing renderer": (d) => { delete d.renderer; },
    "claim status outside the enum": (d) => { d.items[0].claimStatus = "accepted"; },
    "evidence class outside the enum": (d) => { d.items[0].evidenceClass = "runtime_accepted"; },
    "kind and value disagree": (d) => { pr62(d).facts[0].kind = "boolean"; },
    "unknown kind with a number": (d) => { factOf(d, "costs", "current_total_usd").value = 0; },
    "negative integer": (d) => { pr62(d).facts[0].value = -1; },
    "fractional integer": (d) => { pr62(d).facts[0].value = 1.5; },
    "integer beyond 2^53-1": (d) => { pr62(d).facts[0].value = 9007199254740992; },
    "too many decimal places": (d) => { factOf(d, "pr62", "accounted_cpu").value.places = 16; },
    "decimal with a float": (d) => { factOf(d, "pr62", "accounted_cpu").value = 471.654559; },
    "unit outside the enum": (d) => { pr62(d).facts[0].unit = "kelvin"; },
    "bad fact key": (d) => { pr62(d).facts[0].key = "PR-Number"; },
    "no qualifications": (d) => { d.items[0].qualifications = []; },
    "seven qualifications": (d) => { d.items[0].qualifications = Array(7).fill("q"); },
    "nineteen facts": (d) => { pr62(d).facts = Array(19).fill(pr62(d).facts[0]); },
    "title over 1800 characters": (d) => { d.items[0].title = "x".repeat(1801); },
    "empty display": (d) => { d.items[0].display = ""; },
    "observedAt not a date": (d) => { d.items[0].observedAt = "yesterday"; },
    "sourceAt a number": (d) => { d.items[0].sourceAt = 5; },
    "bad evidence hash": (d) => { d.items[0].evidenceRefs[0].sha256 = "abc"; },
    "thirty-one items": (d) => { d.items = Array(31).fill(d.items[0]); },
    "bad prior commit": (d) => { d.priorPacket.commit = "4053328"; },
  };
  for (const [what, mutate] of Object.entries(violations)) {
    const d = clone(SRC);
    mutate(d);
    assert.ok(validateSchema(SCHEMA, d).length > 0, `the validator accepts: ${what}`);
  }
  // Through the loader, past the pin: the schema is enforced.
  rejects(scratch(({ doc }) => doc((d) => { d.items[0].claimStatus = "accepted"; })), /fails its schema/);
});

test("it binds the accepted packet: commit, manifest, fact cutoff, 26 files and 9 baseline files", () => {
  const a = SUPPLEMENT.acceptedPacket;
  assert.deepEqual(SRC.priorPacket, { commit: a.commit, manifestSha256: a.manifestSha256, factualCutoff: "2026-10-31T15:05:00Z", fileCount: 26, baselineFiles: 9 });
  assert.equal(data.source.acceptedPacket.loadedManifestSha256, a.manifestSha256);
  assert.equal(data.source.acceptedPacket.factCutoff, "2026-10-31 15:05 UTC");
  rejects(scratch(({ doc }) => doc((d) => { d.priorPacket.commit = "0".repeat(40); })), /different packet than the accepted/);
  rejects(scratch(({ doc }) => doc((d) => { d.priorPacket.manifestSha256 = "0".repeat(64); })), /different packet than the accepted/);
  // Past the pinned identity: each binding is checked against the packet in this repository.
  rejects(scratch(({ doc }) => doc((d) => { d.priorPacket.manifestSha256 = "1".repeat(64); }), { pin: (p) => ({ ...p, acceptedPacket: { ...p.acceptedPacket, manifestSha256: "1".repeat(64) } }) }), /manifest is not the one the supplement binds/);
  rejects(scratch(({ doc }) => doc((d) => { d.priorPacket.factualCutoff = "2026-10-31T15:06:00Z"; })), /fact cutoff is not the one/);
  rejects(scratch(({ doc }) => doc((d) => { d.priorPacket.fileCount = 25; }), { pin: (p) => ({ ...p, acceptedPacket: { ...p.acceptedPacket, fileCount: 25 } }) }), /file counts differ/);
  rejects(scratch(({ doc }) => doc((d) => { d.priorPacket.baselineFiles = 10; }), { pin: (p) => ({ ...p, acceptedPacket: { ...p.acceptedPacket, baselineFiles: 10 } }) }), /file counts differ/);
});

// ── 2. format routing ───────────────────────────────────────────────────────────────────────────────────────────────
test("only sentilab-deck-facts/1 is routed; any other format stops the build and the render visibly", () => {
  assert.equal(FORMAT, "sentilab-deck-facts/1");
  assert.equal(SRC.format, FORMAT);
  assert.equal(typeof routeFormat(SRC), "function");
  for (const format of ["sentilab-deck-facts/2", "sentilab-deck-facts/1 ", "SENTILAB-DECK-FACTS/1", "sentilab-progress-day-update/2", "", null, 1]) {
    assert.throws(() => routeFormat({ ...SRC, format }), (e) => e instanceof PacketError && /unknown deck-facts format/.test(e.message), String(format));
  }
  for (const doc of [null, [], "sentilab-deck-facts/1", { items: SRC.items }]) assert.throws(() => routeFormat(doc), /unknown deck-facts format/);
  // Routing comes before the schema, so the failure names the format, not a schema keyword.
  rejects(scratch(({ doc }) => doc((d) => { d.format = "sentilab-deck-facts/2"; })), /unknown deck-facts format "sentilab-deck-facts\/2"/);
  assert.throws(() => rebuild((d) => { d.format = "sentilab-deck-facts/2"; }), /unknown deck-facts format/);
  // The page renders only supplement data in this format; anything else throws, and the engine shows its banner.
  assert.throws(() => render({ ...data, source: { ...data.source, format: "sentilab-deck-facts/2" } }), /renders only sentilab-deck-facts\/1/);
  assert.throws(() => render({ ...data, schema: "sentilab-deck-data/2" }), /renders only sentilab-deck-facts\/1/);
  assert.throws(() => render(readJson(join(DECK_DIR, "deck-data.json"))), /renders only sentilab-deck-facts\/1/);
  assert.equal(data.schema, DATA_SCHEMA);
  assert.equal(data.source.format, FORMAT);
  const engine = readFileSync(ENGINE, "utf8");
  assert.match(engine, /Deck data could not be loaded: \$\{esc\(e\.message\)\}/, "the engine shows a render error on the page");
  assert.deepEqual([...html.matchAll(/<script src="([^"]+)"><\/script>/g)].map((m) => m[1]), ["deck-data.js", "../daytime/deck.js", "supplement.js"]);
});

// ── 3. numbers ──────────────────────────────────────────────────────────────────────────────────────────────────────
test("fixed decimals print exactly with BigInt and string operations, never floats", () => {
  const cases = [
    [{ whole: 0, fraction: 2, places: 2 }, "0.02"], [{ whole: 494, fraction: 18953860500187, places: 14 }, "494.18953860500187"],
    [{ whole: 79, fraction: 6175887260033, places: 13 }, "79.6175887260033"], [{ whole: 148, fraction: 90950332500506, places: 14 }, "148.90950332500506"],
    [{ whole: 9007199254740991, fraction: 1, places: 15 }, "9007199254740991.000000000000001"], [{ whole: 1, fraction: 0, places: 3 }, "1.000"],
    [{ whole: 0, fraction: 999999999999999, places: 15 }, "0.999999999999999"], [{ whole: 1440, fraction: 294565, places: 6 }, "1440.294565"],
  ];
  for (const [v, want] of cases) assert.equal(fixedDecimal(v), want, JSON.stringify(v));
  for (const v of [{ whole: 0, fraction: 100, places: 2 }, { whole: 0, fraction: 1, places: 0 }, { whole: 0, fraction: 1, places: 16 }, { whole: -1, fraction: 0, places: 1 },
    { whole: 1.5, fraction: 0, places: 1 }, { whole: 0, fraction: 2 ** 53, places: 15 }, { whole: 0, fraction: 5 }, null, 1.5]) {
    assert.throws(() => fixedDecimal(v), PacketError, JSON.stringify(v));
  }
  let n = 0;
  for (const it of SRC.items) for (const f of it.facts.filter((x) => x.kind === "fixed_decimal")) {
    n++;
    const shown = data.lists.groups[Object.keys(GROUPS).find((g) => Object.hasOwn(GROUPS[g], it.id))].find((x) => x.id === it.id).facts.find((x) => x.key === f.key);
    assert.equal(shown.display, oracle(f), `${it.id}.${f.key}`);
    assert.deepEqual(shown.value, f.value, "the typed value is carried unchanged");
  }
  assert.equal(n, 10, "ten fixed decimals in the delivered file");
});

test("integers print as delivered; every unit has a reviewed display and an unreviewed unit or kind stops the build", () => {
  assert.equal(factDisplay({ kind: "integer", value: 9007199254740991, unit: "count" }, "x"), "9007199254740991");
  assert.equal(factDisplay({ kind: "integer", value: 200, unit: "http_status" }, "x"), "200");
  assert.equal(factDisplay({ kind: "integer", value: 45, unit: "millimetres" }, "x"), "45 mm");
  assert.equal(factDisplay({ kind: "boolean", value: false, unit: "boolean" }, "x"), "false");
  assert.throws(() => factDisplay({ kind: "integer", value: 3, unit: "error" }, "x"), /no reviewed display/);
  assert.throws(() => factDisplay({ kind: "integer", value: 3, unit: "kelvin" }, "x"), /no reviewed display/);
  assert.throws(() => factDisplay({ kind: "integer", value: 3, unit: "constructor" }, "x"), /no reviewed display/);
  assert.throws(() => factDisplay({ kind: "boolean", value: true, unit: "count" }, "x"), /does not fit unit/);
  assert.throws(() => factDisplay({ kind: "integer", value: 1, unit: "boolean" }, "x"), /does not fit unit/);
  assert.throws(() => factDisplay({ kind: "integer", value: 1.5, unit: "count" }, "x"), /safe integer/);
  assert.throws(() => factDisplay({ kind: "boolean", value: "true", unit: "boolean" }, "x"), /true or false/);
  assert.throws(() => factDisplay({ kind: "ratio", value: 1, unit: "count" }, "x"), /no reviewed display/);
  assert.equal(Object.values(data.lists.groups).flat().reduce((n, i) => n + i.facts.length, 0), 125);
  assert.throws(() => rebuild((d) => { item(d, "pr61").facts.push(clone(item(d, "pr61").facts[0])); }), /fact pr_number is listed twice/);
});

test("fact labels spell out their keys; the lead reviewer's own checks read (lead review), project names become roles", () => {
  const REVIEWED = {
    root_model_executed: "model executed (lead review)", root_real_optimizer_calls: "real optimizer calls (lead review)",
    live_keeper_effects_in_root_reviews: "live keeper effects in lead reviews", engram_implemented: "memory-system implemented",
    slab047b_separate_non_gpu_preflight: "SLAB-047b separate non-GPU preflight", held_out_five_arm_complete: "held-out five-arm complete",
    open_round4_p2_findings: "open round-4 P2 findings", exact_head_ci_successes: "exact head CI successes", all_http_200: "all HTTP 200",
    current_total_usd: "current total USD", exit_zero_outcomes: "exit-zero outcomes", followup_review_active: "follow-up review active",
    final_pr57_source_accepted: "final PR57 source accepted", requirements: "requirements",
  };
  for (const [key, want] of Object.entries(REVIEWED)) assert.equal(factLabel(key), want, key);
  const keys = SRC.items.flatMap((i) => i.facts.map((f) => f.key));
  for (const key of keys) assert.deepEqual(scan(factLabel(key)), [], key);
  assert.throws(() => factLabel("root_and_warden12345"), PacketError);
});

test("a typed unknown stays null and shows unknown, never zero", () => {
  const costs = data.lists.groups.history.find((i) => i.id === "costs");
  for (const key of ["current_total_usd", "comprehensive_cpu"]) {
    const f = costs.facts.find((x) => x.key === key);
    assert.equal(f.value, null, key);
    assert.equal(f.display, "unknown", key);
  }
  const card = allCards().find((c) => c.title === subst(item(SRC, "costs").title));
  assert.deepEqual(card.facts.filter((f) => f.nullv).map((f) => [f.label, f.shown]), [["current total USD", "unknown"], ["comprehensive CPU", "unknown"]]);
  assert.doesNotMatch(card.html, /USD 0|\b0 CPU-s/);
  assert.throws(() => factDisplay({ kind: "unknown", value: 0, unit: "usd" }, "x"), /must be null/);
  assert.equal(factDisplay({ kind: "unknown", value: null, unit: "usd" }, "x"), "unknown");
  assert.throws(() => rebuild((d) => { factOf(d, "costs", "current_total_usd").value = 0; }), /must be null/);
  // The page refuses a null shown as anything else, and a missing source time shows "unknown".
  const zeroed = clone(data);
  zeroed.lists.groups.history.find((i) => i.id === "costs").facts.find((x) => x.key === "current_total_usd").display = "USD 0";
  assert.throws(() => render(zeroed), /must show "unknown"/);
  for (const c of allCards()) {
    const raw = SRC.items[c.k];
    if (raw.sourceAt === null) assert.match(c.html, /<span class="sp-t nullv">unknown<\/span>/, raw.id);
  }
});

// ── 4. every card shows exactly its item ────────────────────────────────────────────────────────────────────────────
test("every card shows its item exactly: title, claim status, evidence class, own times, text, limits and typed facts", () => {
  const cards = allCards();
  assert.equal(cards.length, SRC.items.length);
  assert.deepEqual(cards.map((c) => c.k).sort((a, b) => a - b), SRC.items.map((_, k) => k));
  for (const c of cards) {
    const raw = SRC.items[c.k];
    const at = `${c.slide} ${raw.id}`;
    assert.equal(c.title, subst(raw.title), `${at}: title`);
    assert.equal(c.status, raw.claimStatus, `${at}: claim status`);
    assert.equal(c.evidence, raw.evidenceClass, `${at}: evidence class`);
    assert.deepEqual(c.times, [raw.sourceAt === null ? "unknown" : utc(raw.sourceAt), utc(raw.observedAt)], `${at}: its own source and observed times`);
    assert.equal(c.display, subst(raw.display), `${at}: display text`);
    assert.deepEqual(c.quals, raw.qualifications.map(subst), `${at}: every qualification, in order`);
    assert.deepEqual(c.facts.map((f) => f.label), raw.facts.map((f) => factLabel(f.key)), `${at}: fact labels`);
    assert.deepEqual(c.facts.map((f) => f.shown), raw.facts.map(oracle), `${at}: fact values`);
    assert.deepEqual(c.facts.map((f) => f.nullv), raw.facts.map((f) => f.value === null), `${at}: typed unknowns`);
    assert.equal(c.rest, "status evidence source observed or checkpoint", `${at}: nothing else on the card`);
  }
  for (const s of rendered) assert.ok(!s.html.includes(Deck.MISSING), `${s.id}: a missing value`);
});

test("values come from typed facts, never from prose", () => {
  const changed = rebuild((d) => { factOf(d, "pr62", "accounted_cpu").value = { whole: 471, fraction: 654560, places: 6 }; });
  const pr62 = changed.lists.groups.merged.find((i) => i.id === "pr62");
  assert.equal(pr62.facts.find((f) => f.key === "accounted_cpu").display, "471.654560 CPU-s");
  assert.match(pr62.qualifications[1], /471\.654559 CPU-seconds/, "the prose stays as delivered");
  const reword = (t) => t.replace(/(?<!v)\d/g, "7"); // every number but the model version names
  const reworded = rebuild((d) => { for (const it of d.items) { it.display = reword(it.display); it.qualifications = it.qualifications.map(reword); } });
  const facts = (d) => Object.values(d.lists.groups).flat().map((i) => i.facts.map((f) => f.display));
  assert.deepEqual(facts(reworded), facts(data), "rewriting every number in the prose changes no fact");
});

test("titles, display text and qualifications are verbatim except for the reviewed public-render substitutions", () => {
  assert.deepEqual(data.source.publicRender.map((r) => [r.rule, r.to, r.count]), REVIEWED_SUBSTITUTIONS);
  assert.deepEqual(SUPP_SUBSTITUTIONS.map(([re, to]) => [String(re), to]), REVIEWED_SUBSTITUTIONS.map(([r, t]) => [r, t]));
  // Counted the way they apply: in order, each rule on the text the earlier rules left.
  const counts = SUPP_SUBSTITUTIONS.map(() => 0);
  for (const t of SRC.items.flatMap((i) => [i.title, i.display, ...i.qualifications])) {
    SUPP_SUBSTITUTIONS.reduce((s, [re, to], i) => { counts[i] += s.match(re)?.length ?? 0; return s.replace(re, to); }, t);
  }
  assert.deepEqual(counts, REVIEWED_SUBSTITUTIONS.map((r) => r[2]));
  for (const it of Object.values(data.lists.groups).flat()) {
    const raw = item(SRC, it.id);
    assert.equal(it.title, subst(raw.title));
    assert.equal(it.display, subst(raw.display));
    assert.deepEqual(it.qualifications, raw.qualifications.map(subst));
    assert.equal(it.claimStatus, raw.claimStatus);
    assert.equal(it.evidenceClass, raw.evidenceClass);
  }
  // A rule that stops matching stops the build, so the table cannot go stale.
  assert.throws(() => rebuild((d) => { item(d, "costs").qualifications[0] = item(d, "costs").qualifications[0].replace("Azure", "shared"); }), /no longer matches anything/);
});

// ── 5. dates ────────────────────────────────────────────────────────────────────────────────────────────────────────
test("dates: each item keeps its own times, nothing is redated past the cutoff, and the packaging time is never shown", () => {
  assert.equal(data.source.factCutoff, utc(SRC.asOf));
  assert.equal(data.facts["supp.cutoff"].display, "2026-10-31 17:54 UTC");
  for (const it of Object.values(data.lists.groups).flat()) {
    const raw = item(SRC, it.id);
    assert.equal(it.observedAt, raw.observedAt, `${it.id}: observedAt carried exactly`);
    assert.equal(it.sourceAt, raw.sourceAt, `${it.id}: sourceAt carried exactly`);
    assert.equal(it.observed, utc(raw.observedAt));
    assert.equal(it.source, raw.sourceAt === null ? null : utc(raw.sourceAt));
  }
  const packaged = utc(SRC.packagedAt);
  assert.equal(packaged, "2026-10-31 18:20 UTC");
  const everything = [...rendered.map((s) => visible(s.html)), notesText, JSON.stringify(data)].join("\n");
  assert.ok(!everything.includes(packaged) && !everything.includes(SRC.packagedAt), "the packaging time is not a fact date");
  for (const t of everything.match(/\b\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC\b/g)) assert.ok(t <= data.source.factCutoff, `${t} is after the fact cutoff`);
  // A clock time inside delivered text is one of its own card's times (PR60's 17:44 snapshot).
  for (const raw of SRC.items) for (const t of [raw.title, raw.display, ...raw.qualifications].join(" ").match(/\b\d{2}:\d{2}\b/g) ?? []) {
    assert.ok([raw.sourceAt, raw.observedAt].filter(Boolean).some((x) => utc(x).slice(11, 16) === t), `${raw.id}: ${t} is not one of its own times`);
  }
  // The builder checks every time: real date-times, source <= observed <= cutoff <= packaging, and one cutoff.
  assert.throws(() => rebuild((d) => { item(d, "help-room").observedAt = "2026-10-31T17:55:00Z"; }), /observedAt is after the fact cutoff/);
  assert.throws(() => rebuild((d) => { item(d, "pr55").sourceAt = "2026-10-31T15:44:00Z"; }), /sourceAt is after its observedAt/);
  assert.throws(() => rebuild((d) => { item(d, "pr55").observedAt = "2026-02-30T15:43:36Z"; }), /not an RFC 3339 date-time/);
  assert.throws(() => rebuild((d) => { item(d, "pr55").sourceAt = "2026-10-31 15:38"; }), /not an RFC 3339 date-time/);
  assert.throws(() => rebuild((d) => { item(d, "pr55").asOf = d.packagedAt; }), /is not the supplement's fact cutoff/);
  assert.throws(() => rebuild((d) => { d.packagedAt = "2026-10-31T17:00:00Z"; }), /packagedAt is before the fact cutoff/);
  assert.throws(() => rebuild((d) => { d.asOf = "2026-10-31T17:00:00Z"; }), /is not the supplement's fact cutoff/);
});

// ── 6. slides, headings and notes ───────────────────────────────────────────────────────────────────────────────────
test("every item sits on exactly one slide, in the page's order, and each heading holds for its cards", () => {
  const placed = Object.values(GROUPS).flatMap((g) => Object.keys(g));
  assert.equal(new Set(placed).size, placed.length);
  assert.deepEqual([...placed].sort(), SRC.items.map((i) => i.id).sort());
  const pageGroups = [...deckMain.matchAll(/data-gen="supp_(\w+)"/g)].map((m) => m[1]).filter((g) => !["index", "provenance"].includes(g));
  assert.deepEqual(pageGroups, Object.keys(GROUPS), "page order");
  assert.deepEqual([...Deck.plugin.GROUPS], Object.keys(GROUPS), "plugin order");
  assert.deepEqual(rendered.map((s) => s.label), Array.from({ length: rendered.length }, (_, i) => `S${i + 1}`));
  for (const [g, pins] of Object.entries(GROUPS)) {
    for (const [id, status] of Object.entries(pins)) {
      assert.equal(item(SRC, id).claimStatus, status, `${id} on ${g}`);
      for (const [key, want] of Object.entries(GROUP_FACTS[g] ?? {})) assert.equal(factOf(SRC, id, key).value, want, `${id}.${key}`);
    }
    assert.deepEqual(cardsOf(rendered.find((s) => s.id === `s-${g}`).html).map((c) => SRC.items[c.k].id), Object.keys(pins), `${g} cards`);
  }
  assert.throws(() => rebuild((d) => { item(d, "pr59").claimStatus = "merged_source_verified"; }), /heading was written for/);
  assert.throws(() => rebuild((d) => { factOf(d, "pr55", "merge_verified").value = false; }), /as the merged slide heading states/);
  assert.throws(() => rebuild((d) => { factOf(d, "web709", "merge_verified").value = true; }), /as the accepted slide heading states/);
  assert.throws(() => rebuild((d) => { d.items.push({ ...clone(item(d, "costs")), id: "costs-later" }); }), /exactly one slide \(unplaced: costs-later/);
  assert.throws(() => rebuild((d) => { d.items = d.items.filter((i) => i.id !== "pr61"); }), /exactly one slide .*unknown: pr61/);
  assert.throws(() => rebuild((d) => { d.items.push(clone(item(d, "pr61"))); }), /listed twice/);
  // The cover lists every item under its slide, with its exact claim status.
  const cover = rendered.find((s) => s.id === "s-cover").html;
  const rows = [...cover.matchAll(/<li><b>(S\d+)<\/b><span class="sp-it">([\s\S]*?)<\/span><code>([\s\S]*?)<\/code><\/li>/g)].map((m) => [m[1], decode(m[2]), m[3]]);
  const want = Object.entries(GROUPS).flatMap(([, pins], i) => Object.keys(pins).map((id) => [`S${i + 2}`, subst(item(SRC, id).title), item(SRC, id).claimStatus]));
  assert.deepEqual(rows, want);
});

test("the page reuses the frozen engine and stylesheet and adds only the plugin; every slot is filled", () => {
  assert.match(html, /<link rel="stylesheet" href="\.\.\/daytime\/deck\.css">\s*<link rel="stylesheet" href="supplement\.css">/);
  const gens = [...deckMain.matchAll(/data-gen="(\w+)"/g)].map((m) => m[1]);
  for (const g of gens) assert.ok(Object.hasOwn(Deck.GEN, g) || g === "sources", `generator ${g}`);
  for (const k of [...deckMain.matchAll(/data-f="([\w.]+)"/g)].map((m) => m[1])) assert.ok(Object.hasOwn(data.facts, k), `fact ${k}`);
  for (const s of rendered) {
    for (const m of s.html.matchAll(/<(div|ol)\b[^>]*data-gen="(\w+)"[^>]*>([\s\S]*?)<\/\1>/g)) assert.ok(visible(m[3]).length > 0, `${s.id}: ${m[2]} is empty`);
    assert.match(visible(s.html), /Data Facts through 2026-10-31 17:54 UTC/, `${s.id}: the fact cutoff in the footer`);
  }
  assert.equal(rendered.length, 11);
  // The static copy adds no numbers: only the device name GB10 carries digits.
  const statics = visible(deckMain.replace(/<(\w+)\b[^>]*\bdata-(?:f|gen)="[^"]*"[^>]*>[\s\S]*?<\/\1>/g, " "));
  assert.deepEqual(statics.replace(/\bGB10\b/g, "").match(/\d+/g), null, `static copy: ${statics.match(/.{0,20}\d+.{0,20}/g)}`);
});

test("speaker notes: one per slide, in the cards' own words, with no number the data does not hold", () => {
  const bySlide = new Map(data.notes.map((n) => [n.slide, n]));
  for (const s of rendered) assert.ok(bySlide.get(s.notes)?.text.length > 40, `${s.id}: notes`);
  assert.equal(data.notes.length, rendered.length);
  for (const [g, pins] of Object.entries(GROUPS)) {
    const text = bySlide.get(`supp-${g}`).text;
    for (const id of Object.keys(pins)) {
      const raw = item(SRC, id);
      for (const t of [raw.title, raw.display, ...raw.qualifications]) assert.ok(text.includes(subst(t)), `${g} notes: ${t.slice(0, 50)}`);
    }
  }
  const cover = bySlide.get("supp-cover").text;
  for (const k of ["supp.cutoff", "supp.items", "supp.facts", "supp.priorCutoff"]) assert.ok(cover.includes(data.facts[k].display), k);
  const strings = [];
  const walk = (v) => (typeof v === "string" ? strings.push(v) : typeof v === "number" ? strings.push(String(v)) : v && typeof v === "object" && Object.values(v).forEach(walk));
  walk({ ...data, notes: [] });
  const known = new Set(strings.flatMap((s) => s.match(/\d+(?:[.:,]\d+)*/g) ?? []));
  for (const t of notesText.match(/\d+(?:[.:,]\d+)*/g) ?? []) assert.ok(known.has(t), `notes say "${t}", which the data does not hold`);
});

// ── 7. public render ────────────────────────────────────────────────────────────────────────────────────────────────
test("public-render rules hold for the slides, the notes, the data and the supplement's own files", () => {
  for (const s of ["Root accepts", "Aneta v3 reports", "Ascend history", "an ENGRAM implementation", "Azure figures", "room 123456", "run 98765432101", "claude-warden"]) {
    assert.ok(scan(s).length, `the scanner misses: ${s}`);
  }
  for (const s of ["471.654559 CPU-seconds", "494.18953860500187 s", "1440.294565 CPU-s", "14,909 bytes", "GB10"]) assert.deepEqual(scan(s), [], s);
  const attrs = rendered.flatMap((s) => [...s.html.matchAll(/\b(?:title|alt|aria-label)="([^"]*)"/g)].map((m) => decode(m[1])));
  const shown = { slides: rendered.map((s) => visible(s.html)).join("\n"), attributes: attrs.join("\n"), notes: notesText };
  const files = Object.fromEntries(["index.html", "supplement.js", "supplement.css"].map((f) => [f, readFileSync(join(SUPP_DECK_DIR, f), "utf8").replace(/#[0-9a-f]{3,8}\b/gi, "#colour")]));
  for (const [name, text] of Object.entries({ ...shown, ...files })) assert.deepEqual(scan(text), [], `${name} breaks a public-render rule`);
  // Data strings: everything but internal identifiers (item ids, fact keys) and the substitution table's own patterns.
  const strings = [];
  const walk = (v, k) => (typeof v === "string" ? !["id", "key", "rule"].includes(k) && strings.push(v) : v && typeof v === "object" && Object.entries(v).forEach(([kk, vv]) => walk(vv, Array.isArray(v) ? k : kk)));
  walk(data);
  assert.deepEqual(scan(strings.join("\n")), [], "deck-data");
  // No item id or fact key reaches the page's markup. (Every text node of every card and index row is pinned exactly
  // by the card and slide tests, so attributes are the only place one could hide.)
  const page = rendered.map((s) => s.html).join("\n");
  const attrValues = [...page.matchAll(/\s[\w-]+="([^"]*)"/g)].map((m) => m[1]);
  for (const name of [...SRC.items.map((i) => i.id), ...SRC.items.flatMap((i) => i.facts.map((f) => f.key))]) {
    assert.ok(!attrValues.some((v) => v.split(/[\s·]+/).includes(name)), `an attribute carries the internal name ${name}`);
  }
  assert.throws(() => assertPublic("Root accepts", "x"), PacketError);
  assert.equal(rebuild((d) => { item(d, "pr61").display += " Root merged it."; }).lists.groups.withdrawal.find((i) => i.id === "pr61").display.endsWith(" The lead reviewer merged it."), true);
  assert.throws(() => rebuild((d) => { item(d, "pr61").display += " Posted by warden12345."; }), /public-render rule/);
  assert.throws(() => rebuild((d) => { item(d, "pr61").qualifications.push("Ask Jev."); }), /public-render rule/);
  assert.throws(() => rebuild((d) => { item(d, "pr61").display += " See run 98765432101."; }), /public-render rule/);
});

// ── 8. outputs and frozen files ─────────────────────────────────────────────────────────────────────────────────────
test("deck-data.json is a fresh, deterministic build of the delivered supplement, and deck-data.js is the same object", () => {
  const r = spawnSync(process.execPath, ["scripts/build-deck-supplement.mjs", "--check"], { cwd: REPO_ROOT, encoding: "utf8" });
  assert.equal(r.status, 0, `${r.stdout}${r.stderr}`);
  const { json, js } = serializeSupplement(data);
  assert.equal(readFileSync(join(SUPP_DECK_DIR, "deck-data.json"), "utf8"), json);
  assert.equal(readFileSync(join(SUPP_DECK_DIR, "deck-data.js"), "utf8"), js);
  const box = { window: {} };
  vm.runInNewContext(js, box);
  assert.deepEqual(JSON.parse(JSON.stringify(box.window.DECK_DATA)), committed);
  assert.equal(data.source.supplementSha256, SUPPLEMENT.files["SUPPLEMENT.json"].sha256);
  assert.equal(data.source.schemaSha256, SUPPLEMENT.files["SUPPLEMENT.schema.json"].sha256);
  assert.equal(data.source.sourceCommit, SUPPLEMENT.sourceCommit);
});

test("the accepted packet, its 9 baseline files, the legacy schema, the daytime deck and every earlier PDF stay byte-identical", () => {
  for (const [f, h] of Object.entries({ ...FROZEN_V1, ...FROZEN_DAYTIME })) assert.equal(sha(readFileSync(join(REPO_ROOT, f))), h, `${f} changed`);
  const a = SUPPLEMENT.acceptedPacket, dir = join(PACKETS, a.id);
  assert.equal(sha(readFileSync(join(dir, "PACKAGE-MANIFEST.json"))), a.manifestSha256, "the accepted manifest");
  const p = loadPacket(a.id); // every listed file's bytes and SHA256, and no unlisted file
  const count = (d) => readdirSync(d, { withFileTypes: true }).reduce((n, e) => n + (e.isDirectory() ? count(join(d, e.name)) : 1), 0);
  assert.equal(count(dir), 26);
  assert.equal(count(join(dir, "baseline")), 9);
  assert.equal(p.hashes.progressSchemaSha256, "8102def84c206bfd27e89378e7eb0cfaa9eb032198fb3c9e042bda70aa6093e7", "the legacy schema");
  assert.equal(p.hashes.progressSha256, "cf75fd2fbaa2a4860d043b02bdfe82abc3052ec655e40ee0f002b8b53faf1b61", "the legacy progress record");
  for (const f of ["progress.json", "progress.schema.json"]) {
    assert.ok(readFileSync(join(dir, "baseline", f)).equals(readFileSync(join(PACKETS, "progress-2026-10-31", f))), `baseline/${f} is the original`);
  }
});

test("the supplement exports to its own dated PDF, and no export can overwrite a frozen file", () => {
  assert.equal(suppPdfName(), "SentiLab-deck-supplement-2026-10-31-1754-v2.pdf");
  const frozen = { ...FROZEN_V1, ...FROZEN_DAYTIME };
  assert.ok(!Object.hasOwn(frozen, relative(REPO_ROOT, join(PDF_DIR, suppPdfName())).split(sep).join("/")));
  const exporter = readFileSync(join(REPO_ROOT, "scripts", "export-deck-pdf.mjs"), "utf8");
  assert.match(exporter, /const FROZEN = \{ \.\.\.FROZEN_V1, \.\.\.FROZEN_DAYTIME \};/);
  assert.match(exporter, /if \(Object\.hasOwn\(FROZEN, rel\)\) throw/);
  assert.match(exporter, /supplement: \{ dir: SUPP_DECK_DIR, pdf: \(\) => suppPdfName\(\) \}/);
  const pdf = join(PDF_DIR, suppPdfName());
  assert.ok(existsSync(pdf), `${suppPdfName()} is exported`);
  const pages = (readFileSync(pdf, "latin1").match(/\/Type\s*\/Page(?![s\w])/g) ?? []).length;
  assert.equal(pages, rendered.length, "one PDF page per slide");
  assert.deepEqual(readdirSync(PDF_DIR).sort(), [
    "SentiLab-deck-2026-10-31-daytime-1505.pdf", "SentiLab-deck-2026-10-31.pdf", "SentiLab-deck-supplement-2026-10-31-1754-v2.pdf", "final-3min", SUPPLEMENT.id,
  ]);
});
