// node --test scripts/deck-data.test.mjs   (CI: the contracts job)
// The SentiLab daytime deck (deck/daytime/, outside web/public, so it is not published) shows only what the selected
// packet's typed day update says:
//   - one packet-selection rule for generation, --check and this test; the packet name cannot be later than its facts;
//   - the packet is verified first (manifest, both schemas, source bindings, frozen baseline), and a missing or
//     unsupported day update stops the build with no fallback;
//   - every value is a typed field found by id, every time keeps its own meaning, and nothing is dated after the cutoff;
//   - every number on a slide (rendered by deck.js's own renderHtml) exists in deck-data.json, beside its time;
//   - the packet's caveats stay beside their numbers, and the focused rejections in FORGE-INTEGRATION.md hold;
//   - public-render rules; deck v1 and its PDF stay byte-identical.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { join, relative, sep } from "node:path";
import { pathToFileURL } from "node:url";
import { spawnSync } from "node:child_process";
import vm from "node:vm";

import {
  buildDeckData, buildFromPacket, loadPacket, listPacketIds, selectPacketId, serialize, packetStamp, pdfName, publicText,
  DECK_DIR, FROZEN_V1, NOT_PUBLIC, PACKETS, PDF_DIR, REPO_ROOT, SIDECAR_VERSION, PacketError,
} from "./build-deck-data.mjs";
import { validateSchema, UnsupportedSchemaError } from "./json-schema-lite.mjs";
import { FROZEN_DAYTIME, SUPPLEMENT, suppPdfName } from "./build-deck-supplement.mjs";
// The dated supplement deck (deck/supplement/) has its own tests; importing them here runs them in the same CI step.
import "./deck-supplement.test.mjs";

const require = createRequire(import.meta.url);
const Deck = require(join(DECK_DIR, "deck.js"));
const DIR = pathToFileURL(DECK_DIR + sep);
const read = (f) => readFileSync(new URL(f, DIR), "utf8");
// The committed files are checked against a fresh build (the --check test); every rule below runs on the fresh, in-memory
// build, so a regression in the builder fails the rule it breaks. Setup errors are kept, never thrown at load, so each
// test reports for itself.
const committed = JSON.parse(read("deck-data.json"));
const PACKET = committed.source.packetId;
const attempt = (f) => { try { return [f(), null]; } catch (e) { return [null, e]; } };
const [loaded, loadError] = attempt(() => loadPacket(PACKET));
const [data, buildError] = loaded ? attempt(() => buildDeckData(loaded)) : [null, loadError];
const html = read("index.html");
const deckMain = html.match(/<main id="deck"[^>]*>([\s\S]*)<\/main>/)[1];
const slidesOf = (h) => [...h.matchAll(/<section\b([^>]*)>([\s\S]*?)<\/section>/g)].map((m) => ({
  id: /\bid="([^"]+)"/.exec(m[1])[1], notes: /\bdata-notes="([^"]+)"/.exec(m[1])?.[1], backup: /class="slide backup"/.test(m[1]), html: m[2],
}));
const render = (d) => slidesOf(Deck.renderHtml(deckMain, d));
const rendered = data ? render(data) : [];
const template = slidesOf(deckMain);
const decode = (s) => s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, "&");
const visible = (h) => decode(h.replace(/<[^>]+>/g, " ")).replace(/\s+/g, " ").replace(/ ([.,;:!?)])/g, "$1").trim();
const slide = (rs, id) => visible(rs.find((s) => s.id === id).html);
const facts = data?.facts ?? {};
const notesText = (data?.notes ?? []).map((n) => n.text).join("\n");
const sha = (b) => createHash("sha256").update(b).digest("hex");

const PDIR = join(PACKETS, PACKET);
const day = JSON.parse(readFileSync(join(PDIR, "DAY-UPDATE.json"), "utf8"));
const clone = (o) => JSON.parse(JSON.stringify(o));
const build = (mutate) => { const d = clone(loaded.day); mutate?.(d); return buildDeckData({ ...loaded, day: d }); };
const everything = (d) => { const rs = render(d); return [...rs.map((s) => visible(s.html)), d.notes.map((n) => n.text).join(" ")].join("\n"); };

// A scratch copy of the packet with mutated files and a regenerated manifest, so only the rule under test can fail.
function scratchPacket({ id = PACKET, edit = () => {}, extraPackets = [] } = {}) {
  const root = mkdtempSync(join(tmpdir(), "deck-packets-"));
  const dir = join(root, id);
  cpSync(PDIR, dir, { recursive: true });
  for (const p of extraPackets) cpSync(join(PACKETS, p), join(root, p), { recursive: true });
  const j = (f) => JSON.parse(readFileSync(join(dir, f), "utf8"));
  const w = (f, v) => writeFileSync(join(dir, f), typeof v === "string" ? v : JSON.stringify(v, null, 2) + "\n");
  edit({ dir, j, w });
  if (existsSync(join(dir, "PACKAGE-MANIFEST.json"))) {
    const m = j("PACKAGE-MANIFEST.json");
    let total = 0;
    for (const f of Object.keys(m.files)) {
      if (!existsSync(join(dir, f))) { delete m.files[f]; continue; }
      const b = readFileSync(join(dir, f)); total += b.length; m.files[f] = { bytes: b.length, sha256: sha(b) };
    }
    m.payloadFileCount = Object.keys(m.files).length; m.payloadBytes = total;
    w("PACKAGE-MANIFEST.json", m);
  }
  return { root, dir, cleanup: () => rmSync(root, { recursive: true, force: true }) };
}
const rejects = (opts, message) => {
  const s = scratchPacket(opts);
  try { assert.throws(() => loadPacket(opts.id ?? PACKET, s.root), (e) => e instanceof PacketError && message.test(e.message), String(message)); }
  finally { s.cleanup(); }
};

// ── banned terms and paths (rendered slides, notes, data, sources) ──────────────────────────────────────────────────
const BANNED = [
  ...NOT_PUBLIC,
  /\bGPT/i, /\bOpus\b/i, /\bSonnet\b/i, /\bHaiku\b/i, /\bCopilot\b/i, /\bENGRAM\b/i, /\bReachy\b/i, /\bHuawei\b/i,
  /pocket-forge/i, /claude-warden/i, /gpt-astra/i, /\bnightshift\b/i, /\bcodex\b/i, /\bfable\b/i,
  /(?:^|[\s"'(=])\/?(?:docs|web|scripts|contracts|sentilab_core|Users|home|tmp)\//, /\binvite\b|\binvitation link\b/i,
];
const scan = (text) => BANNED.filter((re) => re.test(text)).map(String);
const PATHLIKE = /\b[\w-]+\.(?:md|mjs|jsonl?|py|pdf|png|ya?ml|toml)\b/i;
const STATIC_IDS = [/\bGB10\b/g, /\bgate zero\b/gi, /\bnot zero\b/g]; // a name and a negation, not counts
const NUM = /\d+(?:[.:/,]\d+)*/g;
const tokens = (s) => new Set(String(s).match(NUM) ?? []);
const MAIN_WORDS = [55, 80], MAIN_TOTAL = 430; // six main slides in about 2:45

// ── 1. packet selection ─────────────────────────────────────────────────────────────────────────────────────────────
test("the committed packet loads, verifies and builds", () => {
  assert.equal(loadError, null, `the packet does not load: ${loadError?.message}`);
  assert.equal(buildError, null, `the deck data does not build: ${buildError?.message}`);
});

test("the scanners can fail", () => {
  for (const s of ["note from claude-warden", "pocket-forge posted", "gpt-astra-carter", "ask Jev", "Cloudflare Worker", "a Qwen model",
    "see #56311", "mail a@b.co", "H:/sl-temp/x", "docs/sentilab/x", "warden56782", "forge56794", "run 41209694914", "a Nebius bucket",
    "the human cli-user", "Root accepts"]) assert.ok(scan(s).length, s);
  assert.ok(PATHLIKE.test("PAGE-COPY.md"));
  assert.deepEqual(scan("SentiLab on the GB10: the gate accepts reproduced results"), []);
});

test("one selection rule: later dates win; on a date the plain packet ranks before daytime packets, by HHMM", () => {
  const root = mkdtempSync(join(tmpdir(), "deck-select-"));
  try {
    const ids = ["progress-2026-10-31-daytime-1505", "progress-2026-10-30", "progress-2026-10-31-daytime-0930", "progress-2026-10-31",
      "progress-2026-10-31-daytime-0905", "progress-2026-10-31-zzz", "progress-2026-13-01", "progress-2026-10-31-daytime-2460",
      "progress-2026-10-31-daytime-1505b", "notes"];
    for (const d of ids) mkdirSync(join(root, d));
    writeFileSync(join(root, "progress-2026-11-02"), "a file, not a packet");
    assert.deepEqual(listPacketIds(root), ["progress-2026-10-30", "progress-2026-10-31", "progress-2026-10-31-daytime-0905",
      "progress-2026-10-31-daytime-0930", "progress-2026-10-31-daytime-1505"]);
    assert.equal(selectPacketId(root), "progress-2026-10-31-daytime-1505");
    mkdirSync(join(root, "progress-2026-11-01"));
    assert.equal(selectPacketId(root), "progress-2026-11-01", "a later date wins over every earlier daytime packet");
    assert.deepEqual(packetStamp("progress-2026-10-31-daytime-1505"), { date: "2026-10-31", time: "15:05" });
    assert.deepEqual(packetStamp("progress-2026-10-31"), { date: "2026-10-31", time: null });
    for (const bad of ["progress-2026-02-30", "progress-2026-10-31-daytime-1560", "progress-2026-10-31-Daytime-1505"]) assert.equal(packetStamp(bad), null, bad);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test("generation, --check and CI use the same selected packet", () => {
  assert.equal(selectPacketId(), PACKET, "a newer packet exists: run node scripts/build-deck-data.mjs");
  assert.ok(listPacketIds().includes("progress-2026-10-31"), "the morning packet stays, ranked before the daytime one");
  const fresh = serialize(buildFromPacket());
  assert.equal(read("deck-data.json"), fresh.json, "deck-data.json differs from a fresh build of the selected packet");
  assert.equal(read("deck-data.js"), fresh.js, "deck-data.js differs from a fresh build of the selected packet");
  const check = spawnSync(process.execPath, [join(REPO_ROOT, "scripts", "build-deck-data.mjs"), "--check"], { encoding: "utf8" });
  assert.equal(check.status, 0, check.stderr);
  assert.match(check.stdout, new RegExp(`deck-data matches ${PACKET}`));
  assert.match(readFileSync(join(REPO_ROOT, ".github", "workflows", "ci.yml"), "utf8"), /node --test scripts\/deck-data\.test\.mjs/);
});

const renamed = (to) => ({ j, w }) => {
  const d = j("DAY-UPDATE.json"); d.packetId = to; w("DAY-UPDATE.json", d);
  const s = j("DAY-UPDATE.schema.json"); s.properties.packetId.const = to; w("DAY-UPDATE.schema.json", s);
  const m = j("PACKAGE-MANIFEST.json"); m.packetId = to; w("PACKAGE-MANIFEST.json", m);
  const c = j("DAY-SOURCE-CATALOG.json"); c.packetId = to; w("DAY-SOURCE-CATALOG.json", c);
};
test("a packet cannot win the selection with a name later than its facts", () => {
  for (const later of ["progress-2026-11-01-daytime-0900", "progress-2026-10-31-daytime-1600", "progress-2026-11-01"]) {
    rejects({ id: later, edit: renamed(later) }, /does not match its fact cutoff/);
  }
});

test("the newest packet without a day update fails explicitly; nothing falls back to an older packet or to prose", () => {
  assert.throws(() => loadPacket("progress-2026-10-31"), /has no DAY-UPDATE\.json.*does not fall back/);
  const s = scratchPacket({ extraPackets: ["progress-2026-10-31"] });
  try {
    cpSync(join(PACKETS, "progress-2026-10-31"), join(s.root, "progress-2026-11-01"), { recursive: true });
    assert.equal(selectPacketId(s.root), "progress-2026-11-01");
    assert.throws(() => buildFromPacket(selectPacketId(s.root), s.root), /progress-2026-11-01 has no DAY-UPDATE\.json/);
  } finally { s.cleanup(); }
});

// ── 2. the sidecar contract ─────────────────────────────────────────────────────────────────────────────────────────
test("an unsupported day update version stops the build", () => {
  for (const v of ["sentilab-progress-day-update/1", "sentilab-progress-day-update/3", undefined]) {
    rejects({ edit: ({ j, w }) => { const d = j("DAY-UPDATE.json"); if (v) d.schemaVersion = v; else delete d.schemaVersion; w("DAY-UPDATE.json", d); } },
      /unsupported day update version/);
  }
  assert.equal(SIDECAR_VERSION, "sentilab-progress-day-update/2");
  assert.equal(day.schemaVersion, SIDECAR_VERSION);
});

test("the packet is verified first: manifest bytes, unlisted files, both schemas, source bindings, included bodies", () => {
  // A changed file the manifest does not know about.
  const t = scratchPacket();
  try {
    writeFileSync(join(t.dir, "PAGE-COPY.md"), readFileSync(join(t.dir, "PAGE-COPY.md"), "utf8") + "\nLate edit.\n");
    assert.throws(() => loadPacket(PACKET, t.root), /PAGE-COPY\.md does not match PACKAGE-MANIFEST\.json/);
  } finally { t.cleanup(); }
  const u = scratchPacket();
  try {
    writeFileSync(join(u.dir, "EXTRA.md"), "unlisted");
    assert.throws(() => loadPacket(PACKET, u.root), /files not in PACKAGE-MANIFEST\.json: EXTRA\.md/);
  } finally { u.cleanup(); }
  // Manifest regenerated, so only the named rule can fail.
  rejects({ edit: ({ j, w }) => { const d = j("DAY-UPDATE.json"); d.milestones.find((m) => m.id === "DAY-PR55").verification.selectedPassed = 70; w("DAY-UPDATE.json", d); } }, /DAY-UPDATE\.json fails its schema/);
  rejects({ edit: ({ j, w }) => { const p = j("progress.json"); p.tickets[0].id = "SLAB-099"; w("progress.json", p); w("baseline/progress.json", p); } }, /progress\.json fails its schema/);
  rejects({ edit: ({ j, w }) => { const p = j("progress.json"); w("progress.json", JSON.stringify(p)); w("baseline/progress.json", JSON.stringify(p)); } }, /progress\.json is not the baseline the day update pins/);
  rejects({ edit: ({ j, w }) => { const d = j("DAY-UPDATE.json"); d.$schema = "OTHER.schema.json"; w("DAY-UPDATE.json", d); } }, /names schema "OTHER\.schema\.json"/);
  rejects({ edit: ({ j, w }) => { const d = j("DAY-UPDATE.json"); d.packetId = "progress-2026-10-31-daytime-1504"; w("DAY-UPDATE.json", d); const s = j("DAY-UPDATE.schema.json"); s.properties.packetId.const = d.packetId; w("DAY-UPDATE.schema.json", s); } }, /the day update names packet progress-2026-10-31-daytime-1504/);
  rejects({ edit: ({ j, w }) => { const c = j("DAY-SOURCE-CATALOG.json"); c.packetId = "progress-2026-10-31-daytime-1435"; w("DAY-SOURCE-CATALOG.json", c); } }, /unsupported or mismatched DAY-SOURCE-CATALOG\.json/);
  for (const [field, value, message] of [["schemaVersion", "sentilab-private-day-publication-manifest/2", /unsupported manifest/], ["packetId", "progress-2026-10-30", /the manifest names packet progress-2026-10-30/]]) {
    const s = scratchPacket();
    try {
      const p = join(s.dir, "PACKAGE-MANIFEST.json"), m = JSON.parse(readFileSync(p, "utf8"));
      m[field] = value; writeFileSync(p, JSON.stringify(m));
      assert.throws(() => loadPacket(PACKET, s.root), message);
    } finally { s.cleanup(); }
  }
  const c = scratchPacket();
  try {
    const p = join(c.dir, "PACKAGE-MANIFEST.json"), m = JSON.parse(readFileSync(p, "utf8"));
    m.payloadFileCount += 1; writeFileSync(p, JSON.stringify(m));
    assert.throws(() => loadPacket(PACKET, c.root), /manifest counts do not match its files/);
  } finally { c.cleanup(); }
  rejects({ edit: ({ j, w }) => { const c = j("DAY-SOURCE-CATALOG.json"); c.sources = c.sources.filter((x) => x.id !== "pr55_corrective_ci"); w("DAY-SOURCE-CATALOG.json", c); } }, /evidence references not in the source catalog: pr55_corrective_ci/);
  rejects({ edit: ({ j, w }) => { const c = j("DAY-SOURCE-CATALOG.json"); c.sources.push(clone(c.sources[0])); w("DAY-SOURCE-CATALOG.json", c); } }, /listed twice/);
  rejects({ edit: ({ j, w }) => { const f = j("sources/forge56794.json"); f.text += " "; w("sources/forge56794.json", f); } }, /included source forge56794 does not match its catalog hash/);
  rejects({ edit: ({ j, w }) => { const m = j("PACKAGE-MANIFEST.json"); m.factCutoff = "2026-10-31T15:10:00Z"; w("PACKAGE-MANIFEST.json", m); } }, /disagree on the fact cutoff/);
  rejects({ edit: ({ dir }) => rmSync(join(dir, "DAY-UPDATE.schema.json")) }, /DAY-UPDATE\.schema\.json is missing/);
});

test("the legacy progress record and its schema stay byte-identical: baseline/, the sidecar's pins and the original packet", () => {
  for (const f of ["progress.json", "progress.schema.json"]) {
    const b = readFileSync(join(PDIR, f));
    assert.ok(b.equals(readFileSync(join(PDIR, "baseline", f))), `${f} vs baseline/`);
    assert.ok(b.equals(readFileSync(join(PACKETS, "progress-2026-10-31", f))), `${f} vs the original packet`);
  }
  assert.equal(sha(readFileSync(join(PDIR, "progress.json"))), day.baseline.progressSha256);
  assert.equal(sha(readFileSync(join(PDIR, "progress.schema.json"))), day.baseline.schemaSha256);
  rejects({ edit: ({ dir }) => writeFileSync(join(dir, "baseline", "progress.json"), readFileSync(join(dir, "progress.json"), "utf8").replace(/\n$/, "\n\n")) }, /progress\.json differs from baseline\/progress\.json/);
  const s = scratchPacket({ extraPackets: ["progress-2026-10-31"] });
  try {
    const p = join(s.root, "progress-2026-10-31", "progress.schema.json");
    writeFileSync(p, readFileSync(p, "utf8") + " ");
    assert.throws(() => loadPacket(PACKET, s.root), /progress\.schema\.json differs from the original packet progress-2026-10-31/);
  } finally { s.cleanup(); }
});

test("deck-data records the hash of every input file and of the manifest", () => {
  const manifest = JSON.parse(readFileSync(join(PDIR, "PACKAGE-MANIFEST.json"), "utf8"));
  const pairs = { sidecarSha256: "DAY-UPDATE.json", sidecarSchemaSha256: "DAY-UPDATE.schema.json", progressSha256: "progress.json",
    progressSchemaSha256: "progress.schema.json", sourceCatalogSha256: "DAY-SOURCE-CATALOG.json" };
  for (const [k, f] of Object.entries(pairs)) {
    assert.equal(data.source[k], sha(readFileSync(join(PDIR, f))), k);
    assert.equal(data.source[k], manifest.files[f].sha256, `${k} vs the manifest`);
  }
  assert.equal(data.source.manifestSha256, sha(readFileSync(join(PDIR, "PACKAGE-MANIFEST.json"))));
  assert.equal(data.source.manifestSha256, "674276ed0e9358e8f162cbec0b1660b4b623c99693c2fb4b17390cf12693ca95", "the manifest root accepted");
  assert.equal(data.source.sidecarVersion, SIDECAR_VERSION);
});

test("the schema validator accepts the packet, rejects the packet's own negative cases, and fails closed", () => {
  const schema = JSON.parse(readFileSync(join(PDIR, "DAY-UPDATE.schema.json"), "utf8"));
  assert.deepEqual(validateSchema(schema, day), []);
  const negatives = {
    design_acceptance_removed: (d) => { d.nativeGateZero.designAllocationAccepted = false; },
    executable_binding_promoted: (d) => { d.nativeGateZero.exactCallAllocationAccepted = true; },
    execution_promoted: (d) => { d.nativeGateZero.executionRelease = true; },
    extra_primary_call: (d) => { d.nativeGateZero.designAllocation.primaryCalls = 9; },
    extra_replay: (d) => { d.nativeGateZero.designAllocation.freshProcessGrid64Replays = 5; },
    deferred_extras_included: (d) => { d.nativeGateZero.additionalPublishedVerificationIncludedInCurrent12 = true; },
    deferred_status_removed: (d) => { delete d.nativeGateZero.additionalPublishedVerificationStatus; },
    unseen_holdout_claim: (d) => { d.nativeGateZero.unseenStatisticalHoldoutClaim = true; },
    old_out_of_sample_field: (d) => { d.nativeGateZero.outOfSampleChecksC = [75.47, 94.89]; },
    unknown_evidence: (d) => { d.milestones[0].evidenceRefs.push("not_a_source"); },
    fact_cutoff_advanced: (d) => { d.asOf.includedEvidenceThrough = "2026-10-31T15:10:00Z"; },
    extra_top_field: (d) => { d.extra = 1; },
    pr55_all_passed: (d) => { d.milestones.find((m) => m.id === "DAY-PR55").verification.selectedPassed = 70; },
    human_identity_workaround: (d) => { d.priorities.helpRoomAdmission.humanIdentityWorkaroundAllowed = true; },
  };
  const listed = JSON.parse(readFileSync(join(PDIR, "VALIDATION.json"), "utf8")).negativeCasesRejected;
  assert.deepEqual(Object.keys(negatives).sort(), [...listed].sort(), "every negative case the packet lists is reproduced here");
  for (const [name, mutate] of Object.entries(negatives)) { const d = clone(day); mutate(d); assert.ok(validateSchema(schema, d).length, name); }
  const reordered = clone(day); reordered.milestones.reverse(); reordered.history.reverse(); reordered.gb10Attempts.reverse();
  assert.deepEqual(validateSchema(schema, reordered), [], "order is not part of the contract");
  // Keyword semantics the packet schemas rely on.
  const bad = (schema, value) => assert.ok(validateSchema(schema, value).length, JSON.stringify([schema, value]));
  const good = (schema, value) => assert.deepEqual(validateSchema(schema, value), [], JSON.stringify([schema, value]));
  bad({ oneOf: [{ type: "number" }, { type: "integer" }] }, 1); good({ oneOf: [{ type: "string" }, { type: "integer" }] }, 1);
  bad({ contains: { const: 1 }, maxContains: 1 }, [1, 1]); good({ contains: { const: 1 }, maxContains: 1 }, [1, 2]); bad({ contains: { const: 3 } }, [1, 2]);
  bad({ prefixItems: [{ type: "string" }], items: false }, ["a", 1]); bad({ prefixItems: [{ type: "string" }] }, [1]);
  bad({ uniqueItems: true }, [{ a: 1 }, { a: 1 }]); good({ uniqueItems: true }, [{ a: 1 }, { a: 2 }]);
  bad({ if: { const: 1 }, then: { const: 2 } }, 1); good({ if: { const: 1 }, then: { const: 2 } }, 3); bad({ if: { const: 1 }, else: { const: 2 } }, 3);
  bad({ minLength: 1 }, ""); bad({ pattern: "^D0[0-7]$" }, "D08"); bad({ exclusiveMinimum: 0 }, 0); bad({ minimum: 1 }, 0); bad({ maximum: 1 }, 2);
  bad({ minItems: 2 }, [1]); bad({ maxItems: 1 }, [1, 2]); bad({ enum: [1, 2] }, 3); bad({ not: { const: 1 } }, 1); bad({ anyOf: [{ const: 1 }, { const: 2 }] }, 3);
  bad({ type: "integer" }, 1.5); bad({ type: "null" }, 0); bad({ minProperties: 1 }, {}); bad({ $defs: { x: { const: 1 } }, $ref: "#/$defs/x" }, 2);
  bad({ properties: { a: { const: 1 } }, additionalProperties: false }, { a: 1, b: 2 }); bad({ required: ["a"] }, {});
  bad({ type: "string", format: "uuid" }, "not-a-uuid"); bad({ type: "string", format: "uri" }, "no scheme");
  assert.throws(() => validateSchema({ type: "object", patternProperties: {} }, {}), UnsupportedSchemaError);
  assert.throws(() => validateSchema({ type: "string", format: "email" }, "x"), UnsupportedSchemaError);
  assert.throws(() => validateSchema({ $ref: "https://example.org/s" }, 1), UnsupportedSchemaError);
  assert.ok(validateSchema({ type: "string", format: "date-time" }, "2026-02-30T00:00:00Z").length, "calendar-checked date-time");
});

// ── 3. typed facts, found by id ─────────────────────────────────────────────────────────────────────────────────────
// Resolve a fact ref such as "milestones[DAY-PR55].verification.selectedPassed" or "baseline:milestones[M05].title".
const resolve = (ref) => {
  const catalog = JSON.parse(readFileSync(join(PDIR, "DAY-SOURCE-CATALOG.json"), "utf8"));
  const [root, path] = ref.startsWith("baseline:") ? [loaded.progress, ref.slice(9)] : ref.startsWith("catalog:") ? [catalog, ref.slice(8)] : [loaded.day, ref];
  return path.split(".").reduce((v, part) => {
    const m = /^(\w+)(?:\[([^\]]+)\])?$/.exec(part);
    assert.ok(m && v && typeof v === "object" && m[1] in v, `ref ${ref} does not resolve at ${part}`);
    const next = v[m[1]];
    return m[2] ? next.find((x) => x.id === m[2]) : next;
  }, root);
};
test("every fact names the typed field it comes from, and a single-field fact equals that field", () => {
  let checked = 0;
  for (const [k, f] of Object.entries(facts)) {
    assert.ok(f.ref, `${k} has no ref`);
    const refs = [].concat(f.ref), got = refs.map(resolve);
    assert.ok(got.every((v) => v !== undefined), `${k}: ref does not resolve`);
    if (Array.isArray(f.ref) && Array.isArray(f.value)) { assert.deepEqual(f.value, got, k); checked++; }
    else if (typeof f.ref === "string" && (typeof got[0] !== "object" || got[0] === null) && !/At$/.test(f.ref) && !k.endsWith(".label")) {
      if (["status", "binding", "build", "release", "researchFirst", "interruptions", "autoAdmission", "verified", "identity", "secondApprover",
        "physical", "native", "scientificBenefit", "fullCompletion", "publicProduction", "newExecution", "invoice", "timeMetric", "head", "priorHead"].some((s) => k.endsWith(`.${s}`)) || typeof got[0] !== "number") {
        if (typeof got[0] === "number" || typeof got[0] === "boolean" || got[0] === null) assert.equal(f.value, got[0], k);
      } else assert.equal(f.value, got[0], k);
      checked++;
    }
  }
  assert.ok(checked > 80, `${checked} facts compared with their typed fields`);
  for (const [k, sel] of [["pr55.closed", (fs) => fs.filter((x) => x.status !== "OPEN").length], ["pr55.open", (fs) => fs.filter((x) => x.status === "OPEN").length]]) {
    assert.equal(facts[k].value, sel(day.milestones.find((m) => m.id === "DAY-PR55").findingDispositions), k);
  }
  assert.equal(facts["sci.headroom"].display, loaded.progress.milestones.find((m) => m.id === "M05").title, "the historical verdict is the baseline record's title, verbatim");
});

test("reordered or superseded-first records give the same deck; duplicates and missing records stop the build", () => {
  const same = build((d) => {
    for (const k of ["milestones", "history", "gb10Attempts", "claimDispositions", "supplementalTracks"]) d[k].reverse();
    d.milestones.find((m) => m.id === "DAY-PR55").findingDispositions.reverse();
    d.milestones.sort((a, b) => (a.id === "DAY-PR54" ? -1 : b.id === "DAY-PR54" ? 1 : 0)); // the superseded-history fact first
  });
  assert.deepEqual(same, buildDeckData(loaded));
  // A superseded copy placed first is a duplicate, never a first match.
  assert.throws(() => build((d) => { const old = clone(d.milestones.find((m) => m.id === "DAY-PR54")); old.status = "scoped_accepted_pending_ci_merge"; d.milestones.unshift(old); }), /duplicate milestone id DAY-PR54/);
  assert.throws(() => build((d) => { d.gb10Attempts.push(clone(d.gb10Attempts[0])); }), /duplicate GB10 attempt id/);
  assert.throws(() => build((d) => { d.milestones = d.milestones.filter((m) => m.id !== "DAY-PR55"); }), /DAY-PR55 is missing/);
  assert.throws(() => build((d) => { d.gb10Attempts = d.gb10Attempts.filter((a) => a.id !== "SLAB-047b"); }), /cards for GB10 attempts/);
  assert.throws(() => build((d) => { d.claimDispositions[0].status = "promoted"; }), /no reviewed label/);
  // Superseded history renders only as history, beside its replacement and both times.
  const eng = slide(rendered, "s-engineering");
  assert.match(eng, /Superseded history 2026-10-31 14:31 UTC: scoped accepted · CI and merge pending\. Replaced at 2026-10-31 14:38 UTC by: scoped slice accepted\./);
  assert.match(eng, /PR54 scoped slice accepted observed 2026-10-31 14:38 UTC/);
});

test("the adapter's own invariants stop an inconsistent or promoted day update, even past the schema", () => {
  const stops = (mutate, message) => assert.throws(() => build(mutate), message, String(message));
  const stopsBase = (mutate, message) => { const p = clone(loaded.progress); mutate(p); assert.throws(() => buildDeckData({ ...loaded, progress: p }), message); };
  stops((d) => { d.gb10Attempts.find((a) => a.id === "SLAB-047b").labelsProvidedInPrompts = false; }, /six-case and label caveats must stay true/);
  stops((d) => { d.gb10Attempts.find((a) => a.id === "SLAB-047b").sourceCasesSeenInTraining = false; }, /six-case and label caveats must stay true/);
  stops((d) => { d.gb10Attempts.find((a) => a.id === "SLAB-018-attempt-1").totalAttributedSeconds += 1; }, /stage \+ reservation != total/);
  stops((d) => { d.gb10Attempts.find((a) => a.id === "SLAB-047b").retryAuthorized = true; }, /retry or final acceptance is not false/);
  stops((d) => { d.baseline.cliDeclarations = 103; }, /CLI\/MCP declarations/);
  stops((d) => { d.baseline.fullyAcceptedDeliverables = 1; }, /completion counts disagree/);
  stops((d) => { d.baseline.scopeCountsAreNotImplementedCoverage = false; }, /scope, not implemented coverage/);
  stops((d) => { d.summary.allEightDeliverablesRemainIncomplete = false; }, /summary and baseline disagree/);
  stops((d) => { d.resources.pr37Booking.secondAttemptReleased = true; }, /second attempt must not be released/);
  stops((d) => { d.resources.historicalEstimateIsNotCurrentTotal = false; }, /historical estimate must stay marked as not current/);
  stops((d) => { d.claimDispositions.find((c) => c.id === "CLAIM-OLD-THERMAL").replacement = "Corrected physics."; }, /now has a replacement/);
  stops((d) => { d.nativeGateZero.physicalAccuracyEstablished = true; }, /promotes execution/);
  stops((d) => { d.nativeGateZero.designAllocation.primaryCalls = 9; }, /do not add up within the envelope/);
  stops((d) => { d.history.find((h) => h.id === "HISTORY-PR55-FIVE-HELD").factId = "DAY-PR54"; }, /does not belong to DAY-PR55/);
  stops((d) => { d.milestones.find((m) => m.id === "DAY-PR55").findingDispositions[0].status = "WAIVED"; }, /unsupported status|no reviewed label/);
  stopsBase((p) => { p.tickets.pop(); }, /disagree on the ticket count/);
  stopsBase((p) => { p.deliverables.pop(); }, /disagree on the deliverable count/);
  stopsBase((p) => { p.milestones = p.milestones.filter((m) => m.id !== "M05"); }, /baseline milestone M05 is missing/);
});

test("no legacy prose or page-copy fallback: rewriting every prose field the deck does not show changes nothing", () => {
  const prose = clone(loaded.progress);
  for (const list of [prose.milestones, prose.tickets, prose.deliverables, prose.priorities]) for (const x of list) if (x.summary) x.summary = "Verdict remains CONCLUSIVE; 70/70 passed; within the 90-minute cap; grid8/grid64 discrepancy is 0.01 C.";
  assert.deepEqual(buildDeckData({ ...loaded, progress: prose }), buildDeckData(loaded));
  const hidden = build((d) => { for (const id of ["DAY-PR37", "DAY-PR55", "DAY-PR56", "DAY-HELP-ROOM", "DAY-DIAGNOSIS", "DAY-PR52"]) d.milestones.find((m) => m.id === id).summary = "All 70/70 tests passed and the grant is released."; d.pendingWork = ["Nothing pending."]; });
  assert.deepEqual(hidden, buildDeckData(loaded));
  assert.doesNotMatch(readFileSync(join(REPO_ROOT, "scripts", "build-deck-data.mjs"), "utf8"), /PAGE-COPY\.md"\)|readFileSync\([^)]*PAGE-COPY/, "the builder never reads page copy");
});

test("a typed null stays null: unknown cost, no base comparison, no replacement claim; never a number or an older value", () => {
  for (const [k, f] of Object.entries(facts)) if (f.value == null) assert.doesNotMatch(f.display, /\d/, `${k} is null and must not show a number`);
  assert.equal(facts["cost.current"].display, "unknown");
  assert.equal(facts["a047b.base"].display, "not measured in this attempt");
  const all = everything(data);
  for (const c of day.claimDispositions) assert.ok(!all.includes(c.earlierClaim), `earlier claim shown: ${c.earlierClaim}`);
  const withNull = build((d) => { d.claimDispositions.find((c) => c.id === "CLAIM-047B-TIME").replacement = null; });
  const text = everything(withNull);
  assert.ok(!text.includes("GPU-s"), "a null replacement must not bring back the old GPU-s claim");
  assert.match(slide(render(withNull), "s-corrections"), /Serving time unit metric corrected corrected 2026-10-31 14:34 UTC No replacement claim\./);
});

// ── 4. times keep their meaning ─────────────────────────────────────────────────────────────────────────────────────
const UTC = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC$/;
const asMs = (s) => Date.parse(s.replace(" UTC", "Z").replace(" ", "T"));
test("every fact and list item is dated with its own kind of time, and nothing is dated after the fact cutoff", () => {
  const cutoff = asMs(data.source.factCutoff);
  const items = [...Object.entries(facts), ...Object.entries(data.lists).flatMap(([n, l]) => (Array.isArray(l) ? l.map((x) => [`${n}.${x.id}`, x]) : []))];
  for (const [k, x] of items) {
    assert.match(x.asOf, UTC, `${k} asOf`);
    assert.ok(typeof x.asOfKind === "string" && x.asOfKind.length >= 3, `${k} asOfKind`);
    if (x.asOfKind !== "due") assert.ok(asMs(x.asOf) <= cutoff, `${k} is dated ${x.asOf}, after the cutoff`);
  }
  assert.throws(() => build((d) => { d.milestones.find((m) => m.id === "DAY-PR55").evidenceTimes.reviewedAt = d.asOf.laterVerificationAt; }), /after the fact cutoff/);
});

test("old observations keep their times beside later reviews; later verification never redates a fact", () => {
  const gb = slide(rendered, "s-gb10");
  assert.match(gb, /first attempt record evidence 2026-10-31 07:53 UTC/);
  assert.match(gb, /serving attempt review last response 2026-10-31 11:40 UTC, cleanup confirmed 2026-10-31 11:40 UTC, reviewed 2026-10-31 14:34 UTC/);
  for (const k of ["pr55.passed", "pr55.status", "pr55.cardinality"]) assert.equal(facts[k].asOf, "2026-10-31 15:03 UTC", k);
  assert.equal(facts["pr55.delivered"].asOf, "2026-10-31 15:04 UTC");
  assert.equal(facts["sci.headroom"].asOf, "2026-10-31 07:50 UTC", "the historical verdict keeps the baseline date");
  const later = /2026-10-31 15:0[6-9] UTC|15:08|packaged|later verification/i;
  assert.doesNotMatch(JSON.stringify(data) + everything(data), later);
  // The newest cited evidence never dates an item: PR55 cites a 15:08:55 verification record, PR51 a 14:34 review.
  const catalog = new Map(JSON.parse(readFileSync(join(PDIR, "DAY-SOURCE-CATALOG.json"), "utf8")).sources.map((s) => [s.id, s.sourceAt]));
  for (const m of data.lists.engineering) {
    const src = day.milestones.find((x) => x.id === m.id);
    const newest = src.evidenceRefs.map((r) => catalog.get(r)).filter(Boolean).sort().at(-1);
    const own = src.evidenceTimes.observedAt ?? src.evidenceTimes.reviewedAt ?? src.sourceAt;
    assert.equal(m.asOf, data.lists.engineering.find((x) => x.id === m.id).asOf);
    assert.equal(asMs(m.asOf), Math.floor(Date.parse(own) / 60000) * 60000, `${m.id} keeps its own time`);
    if (Math.floor(Date.parse(newest) / 60000) !== Math.floor(Date.parse(own) / 60000)) assert.notEqual(asMs(m.asOf), Math.floor(Date.parse(newest) / 60000) * 60000, `${m.id} took its newest evidence time`);
  }
});

// ── 5. the rendered deck ────────────────────────────────────────────────────────────────────────────────────────────
test("every slot names an existing fact or generator; six main slides and seven backups", () => {
  for (const [, key] of deckMain.matchAll(/data-f="([^"]+)"/g)) assert.ok(facts[key], `unknown fact ${key}`);
  for (const [, keys] of deckMain.matchAll(/data-asof="([^"]+)"/g)) for (const k of keys.trim().split(/\s+/)) assert.ok(facts[k], `unknown stamp key ${k}`);
  for (const [, g] of deckMain.matchAll(/data-gen="([^"]+)"/g)) assert.ok(g === "sources" || Deck.GEN[g], `unknown generator ${g}`);
  assert.equal(rendered.length, 13);
  assert.equal(rendered.filter((s) => s.backup).length, 7);
  for (const s of rendered) assert.doesNotMatch(s.html, /class="[^"]*\bpending\b|missing value/, `${s.id}: a missing value`);
});

test("the static slide copy carries no numbers of its own", () => {
  const WORDS = /\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|fifty|hundred|thousand)\b/i;
  for (const s of template) {
    let text = visible(s.html.replace(/<svg[\s\S]*?<\/svg>/g, (svg) => svg.replace(/<text[^>]*>([^<]*)<\/text>/g, " $1 ")));
    for (const re of STATIC_IDS) text = text.replace(re, " ");
    assert.deepEqual(text.match(NUM) ?? [], [], `${s.id}: digits in static copy`);
    assert.doesNotMatch(text, WORDS, `${s.id}: a number word in static copy`);
  }
  for (const [, note] of deckMain.matchAll(/data-note="([^"]*)"/g)) assert.doesNotMatch(note, /\d/);
});

test("every number on a slide exists in deck-data.json, and every value's time is on its slide", () => {
  const allowed = new Set();
  const add = (v) => (Array.isArray(v) ? v.forEach(add) : v && typeof v === "object" ? Object.values(v).forEach(add) : tokens(v).forEach((t) => allowed.add(t)));
  for (const f of Object.values(facts)) { add(f.display); add(f.asOf); }
  add(data.lists); add(data.source.factCutoff);
  for (const s of rendered) {
    let text = visible(s.html);
    for (const re of STATIC_IDS) text = text.replace(re, " ");
    for (const t of text.match(NUM) ?? []) assert.ok(allowed.has(t), `${s.id}: "${t}" is shown but not in deck-data.json`);
    for (const [, key] of s.html.matchAll(/data-f="([^"]+)"/g)) assert.ok(text.includes(`${facts[key].asOfKind} ${facts[key].asOf}`) || (facts[key].asOfKind === "cutoff" && text.includes(`Facts through ${facts[key].asOf}`)), `${s.id}: ${key} is shown without its time`);
    assert.match(text, /Data Facts through 2026-10-31 15:05 UTC/, `${s.id}: no visible fact cutoff`);
  }
});

test("GB10: three separate attempts, the six-case and label caveat beside every ratio, units never promoted", () => {
  const gb = slide(rendered, "s-gb10");
  const caveat = (text, ratio, where) => {
    let at = text.indexOf(ratio), n = 0;
    while (at >= 0) { n++; assert.match(text.slice(at, at + 240), /six source cases already seen in training, with labels (?:supplied|in the prompts)/, `${where}: ${ratio} without the six-case and label caveat`); at = text.indexOf(ratio, at + 1); }
    return n;
  };
  let shown = 0;
  for (const s of rendered) shown += caveat(visible(s.html), "20/20", s.id);
  for (const n of data.notes) shown += caveat(n.text, "20/20", `notes.${n.slide}`);
  assert.ok(shown >= 4, "both ratios on the slide and in the notes");
  for (const id of ["SLAB-018 attempt 1", "SLAB-047", "SLAB-047b"]) assert.ok(gb.includes(id), id);
  const card3 = gb.slice(gb.indexOf("SLAB-047b"));
  assert.doesNotMatch(card3, /(?<!\d)0\/20/, "the original base score is not reused for SLAB-047b");
  assert.match(card3, /not measured in this attempt base/);
  assert.match(gb, /148\.9 s whole owned lifecycle wall time, including cleanup\. Not GPU time\./);
  assert.match(gb, /First client response 35\.0 s: client-observed latency, not throughput or time to first token; review had corrected a timeout too short for it\./);
  assert.match(gb, /Native preflight 0\.64 s, counted separately/);
  assert.match(gb, /494\.2 s attributed: 314\.2 s of stage time plus a 180 s prior reservation/);
  assert.match(gb, /79\.6 s owned lifecycle/);
  assert.match(gb, /20 steps 40 HTTP responses 112 checks 200 rows used once · 60 unique prompts/, "SLAB-018 keeps its own audit count and unique prompts");
  assert.match(gb, /0 inference requests 75 checks/, "SLAB-047 keeps its own audit count");
  assert.match(card3, /\b323 checks\./, "SLAB-047b keeps its own audit count");
  assert.doesNotMatch(gb.slice(0, gb.indexOf("SLAB-047b")), /\b323\b/, "the serving audit count is not attached to an earlier attempt");
  assert.match(gb, /All three closed, no retry authorized\. A single serving fixture completed; no learning or held-out generalization is shown\./);
  assert.doesNotMatch(everything(data), /GPU-s|GPU seconds|GPU busy time of|tokens? per second|throughput of|time to first token (?:was|of)/i);
});

test("science: INCONCLUSIVE kept, questions are hypotheses, gate zero is design only, and no physical claims", () => {
  const sci = slide(rendered, "s-science");
  assert.match(sci, /Headroom remains inconclusive/);
  assert.match(sci, /historical observations · not corrected physics/);
  assert.match(sci, /Reviewed hypotheses, not results/);
  assert.match(sci, /8 primary calls \+ 4 fresh-process grid-64 replays/);
  assert.match(sci, /Design accepted 2026-10-31 15:02 UTC/);
  assert.match(sci, /grant binding: pending\. Execution not released\./);
  assert.match(sci, /Prospective targets 75\.48 \/ 115\.94 °C at 45 mm: computational reference checks within a prospective 1 K tolerance\. Physical accuracy not established\./);
  assert.match(sci, /75\.47 \/ 94\.89 °C: deferred to a later allocation, with no extra calls and no unseen holdout claimed/);
  assert.match(sci, /No calibrated temperature, silicon, optimality, MATCH\/BEAT or universal-flatness claim\./);
  assert.match(slide(rendered, "s-correction"), /This drill shows the designed mechanism; the scientific correction is still open\./);
  for (const id of ["s-science", "s-sources"]) assert.match(slide(rendered, id), /Eight saved native fields analyzed; two representative cases independently checked/, `${id}: the parent covers eight grids, the reparse two cases`);
  assert.match(slide(rendered, "s-sources"), /Only the two representative cases were independently re-parsed\./);
  const claims = /\b(?:calibrated|optimal|optimality|silicon|MATCH|BEAT|flat(?:ness)?)\b/gi;
  for (const t of [...rendered.map((s) => visible(s.html)), notesText]) for (const m of t.matchAll(claims)) {
    assert.match(t.slice(Math.max(0, m.index - 120), m.index + 60), /\bno\b|\bnot\b|without|never|claim no/i, `unqualified "${m[0]}": ${t.slice(Math.max(0, m.index - 80), m.index + 40)}`);
  }
});

test("scope counts are original obligations, not implemented counts, and nothing inflates completion", () => {
  const st = slide(rendered, "s-status"), cov = slide(rendered, "s-coverage");
  assert.ok(st.startsWith("SentiLab ScienceClaw hackathon Where it stands None of the eight deliverables is fully accepted."));
  assert.match(st, /Original scope, not implemented counts 41 tickets 234 requirements 104 CLI declarations 104 MCP declarations/);
  assert.match(st, /Whole tickets complete: 0\. Deliverables fully accepted: 0 of 8\./);
  assert.match(cov, /41 tickets, 8 deliverables: original scope, not implemented counts/);
  for (const t of loaded.progress.tickets) assert.ok(cov.includes(t.id.replace(/^SLAB-/, "")), t.id);
  for (const d of loaded.progress.deliverables) assert.ok(cov.includes(`${d.id} ${d.status} · not accepted`), d.id);
  // The open items the required checks name stay explicit on the deck.
  assert.match(st, /Parser PR56 parser needs one P2 repair\. No native execution\./);
  assert.match(st, /Bootstrap PR37 failed admission\. A full conservative policy debit, not measured use, of 100 launches and 900 CPU-s is operator-reported · not independently verified\./);
  assert.match(notesText, /the operator reports booking the full conservative debit/);
  assert.equal(facts["pr37.status"].asOfKind, "reviewed", "the record's status is dated by its review");
  assert.equal(facts["pr37.launches"].asOfKind, "reported", "the booking is dated as the operator's report, not as the bootstrap");
  assert.match(st, /Old scientific authority expired 2026-10-31 12:00 UTC\. New execution not released\./);
  assert.match(slide(rendered, "s-queue"), /No second attempt\./);
  assert.equal(data.lists.tickets.length, 41);
  assert.equal(data.lists.tickets.filter((t) => t.complete).length, 0);
  assert.ok(data.lists.deliverables.every((d) => !d.accepted));
  for (const s of rendered) assert.doesNotMatch(visible(s.html), /\b(?:all|every) (?:deliverables?|tickets?) (?:is |are )?(?:complete|accepted|done)\b|fully implemented/i, s.id);
});

// Every string a viewer could be shown. "ref" and "id" are internal pointers into the packet (its stable ids, the
// evidence-appendix role FORGE-INTEGRATION.md allows); they are never rendered, which the rendered scan proves.
const shownStrings = (v, out = []) => {
  if (typeof v === "string") out.push(v);
  else if (Array.isArray(v)) v.forEach((x) => shownStrings(x, out));
  else if (v && typeof v === "object") for (const [k, x] of Object.entries(v)) if (k !== "ref" && k !== "id") shownStrings(x, out);
  return out;
};
test("public-render rules hold for the slides, the notes, the data and the deck sources", () => {
  const noColours = (t) => t.replace(/\b(?:fill|stroke)="#[0-9a-f]{3,8}"/gi, "").replace(/points="[^"]*"/g, "");
  const surfaces = {
    "index.html": noColours(html), "deck.js": read("deck.js"), "deck.css": read("deck.css").replace(/#[0-9a-f]{3,8}\b/gi, "#colour").replace(/:root\b/g, ""),
    "deck-data.json": shownStrings({ ...data, source: { ...data.source, packetId: null } }).join("\n"), notes: notesText,
    rendered: rendered.map((s) => visible(s.html)).join("\n"),
  };
  for (const s of rendered) for (const k of [...Object.values(facts).map((f) => [].concat(f.ref)).flat(), ...Object.values(data.lists).flat().map((x) => x?.id)].filter(Boolean)) {
    if (/^(?:DAY|HISTORY|CLAIM)-|\[/.test(k)) assert.ok(!s.html.includes(k), `${s.id} renders the internal pointer ${k}`);
  }
  for (const [name, text] of Object.entries(surfaces)) assert.deepEqual(scan(text), [], `${name} breaks a public-render rule`);
  const shownText = [...rendered.map((s) => visible(s.html)), ...[...html.matchAll(/\b(?:alt|title|aria-label)="([^"]*)"/g)].map((m) => m[1]), notesText];
  for (const t of shownText) assert.doesNotMatch(t, PATHLIKE, "a file name is shown");
  const strings = [];
  const walk = (v) => (typeof v === "string" ? strings.push(v) : v && typeof v === "object" && Object.values(v).forEach(walk));
  walk(data);
  for (const s of strings) assert.doesNotMatch(s, PATHLIKE, `deck-data string looks like a file name: ${s}`);
  assert.throws(() => publicText("Warden reports booking", "x"), /public-render rule/);
  assert.equal(publicText("Nebius compatibility assessment delivered", "x"), "Cloud-provider compatibility assessment delivered");
  for (const s of rendered) {
    assert.doesNotMatch(visible(s.html), /\bdeployed\b/i, `${s.id}: "deployed" is not supported by the data`);
    if (!s.backup) assert.doesNotMatch(visible(s.html), /\blive\b/i, `${s.id}: nothing on a main slide is called live`);
  }
});

test("every time shown or spoken is dated and in UTC", () => {
  const FULL = /\b\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC\b/g;
  for (const [where, text] of [...rendered.map((s) => [s.id, visible(s.html)]), ["notes", notesText], ["deck-data", JSON.stringify(data, null, 2)]]) {
    const rest = text.replace(FULL, " ");
    assert.doesNotMatch(rest, /\b\d{1,2}:\d{2}\b/, `${where}: a time without its date and UTC`);
    assert.doesNotMatch(rest, /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/, `${where}: a raw ISO timestamp`);
  }
});

test("speaker notes exist for every slide, fit the 2:45 talk, and speak only numbers that are facts", () => {
  const bySlide = new Map(data.notes.map((n) => [n.slide, n]));
  let total = 0;
  for (const s of rendered) {
    const n = bySlide.get(s.notes);
    assert.ok(n && n.text.length > 40, `${s.id}: notes`);
    if (!s.backup) {
      const words = n.text.split(/\s+/).length;
      total += words;
      assert.ok(words >= MAIN_WORDS[0] && words <= MAIN_WORDS[1], `${s.id}: ${words} words`);
    }
  }
  assert.ok(total <= MAIN_TOTAL, `main notes run ${total} words; the talk is about 2:45`);
  const factTokens = new Set(Object.values(facts).flatMap((f) => [...tokens(f.display)]));
  let spoken = notesText;
  for (const re of STATIC_IDS) spoken = spoken.replace(re, " ");
  for (const t of spoken.match(NUM) ?? []) assert.ok(factTokens.has(t), `notes say "${t}", which is not a fact`);
});

test("deck-data.js is the same object as deck-data.json", () => {
  const box = { window: {} };
  vm.runInNewContext(read("deck-data.js"), box);
  assert.deepEqual(JSON.parse(JSON.stringify(box.window.DECK_DATA)), committed, "same values (the VM realm has its own prototypes)");
  assert.equal(read("deck-data.js"), serialize(committed).js);
  assert.equal(read("deck-data.json"), serialize(committed).json, "deterministic serialization");
});

test("images exist and are described; the fixture screenshots are labelled as fixtures", () => {
  for (const [, src] of html.matchAll(/<img\b[^>]*\bsrc="([^"]+)"/g)) assert.ok(existsSync(new URL(src, DIR)), src);
  for (const [tag] of html.matchAll(/<img\b[^>]*>/g)) assert.match(tag, /\balt="[^"]{20,}"/);
  assert.match(slide(rendered, "s-how"), /Demonstrated on a test-key fixture .* Lab view · test-key interface fixture · illustrative values/);
  assert.match(slide(rendered, "s-correction"), /Package view · fixture replay .* Both views replay a test-key interface fixture: illustrative values, no solver ran\./);
});

test("design, fixture and runtime evidence stay distinct; each accepted slice names its evidence", () => {
  const how = slide(rendered, "s-how");
  assert.doesNotMatch(how, /accepted at runtime/i, "only two slices include runtime checks");
  for (const m of data.lists.engineering) assert.ok(how.includes(`${m.pr} ${m.title} ${m.evidence}`), `${m.pr} without its evidence label`);
  const runtime = data.lists.engineering.filter((m) => /boot|HTTP/.test(m.evidence)).map((m) => m.id).sort();
  assert.deepEqual(runtime, ["DAY-PR51", "DAY-PR53"], "runtime evidence follows the typed classification");
  assert.match(notesText, /only two include runtime checks\. That is not production acceptance\./);
  assert.match(slide(rendered, "s-problem"), /drawn for illustration: its colours are not measurements/);
  assert.match(slide(rendered, "s-problem"), /This slide states the design\. It reports no measurement\./);
  assert.match(notesText, /Both views replay a test-key fixture; no solver ran\./);
  const eng = slide(rendered, "s-engineering");
  assert.match(eng, /PR52 .* Evidence: retained merge and CI only No fresh repository query was made while preparing this packet\./, "PR52 shows its limit");
  const help = slide(rendered, "s-community");
  assert.match(help, /Human direction through 2026-10-31 14:49 UTC: research first, a single participant listener, missing materials in parallel\./, "the accepted 14:49 direction keeps its date");
  assert.match(help, /The retained checkpoint of 2026-10-31 14:47 UTC observed a join, post and reply slice only\./);
  assert.equal(facts["help.direction"].asOfKind, "human direction");
});

// ── 6. focused rejections (FORGE-INTEGRATION.md): each check passes on the deck and rejects its regression ──────────
const pr55Current = (text) => /four scoped closures; one open P2 \(unknown method\)/.test(text) && /67 of 70 selected tests passed, three errored/.test(text);
const checks = {
  staleFiveOpen: (d) => {
    const q = slide(render(d), "s-queue"), st = slide(render(d), "s-status");
    const open = (q.match(/\bP[12] open\b/g) ?? []).length, closed = (q.match(/\bP[12] closed\b/g) ?? []).length;
    const history = q.slice(q.indexOf("History, superseded"));
    return pr55Current(st) && open === 1 && closed === 4 && /Two P1 and three P2 findings remain/.test(history) && !/Two P1 and three P2 findings remain/.test(q.slice(0, q.indexOf("History, superseded")));
  },
  closureInflation: (d) => {
    const all = everything(d);
    return !/five scoped closures|\ball (?:five )?findings (?:are )?closed\b|PR55 (?:accepted|merged|approved)/i.test(all) && /\bP2 open unsupported identifier/.test(slide(render(d), "s-queue"));
  },
  noSeventyOfSeventy: (d) => {
    const all = everything(d);
    return !/70\s*\/\s*70|70 of 70|all 70\b/.test(all) && /67 of 70 selected passed; three errored for a missing native binary\. Errors are not passes\./.test(slide(render(d), "s-queue"));
  },
  noGrantFromEnvelope: (d) => {
    const sci = slide(render(d), "s-science");
    const i = sci.indexOf("1,800 CPU-s");
    return i > 0 && /is prospective, not a grant/.test(sci.slice(i, i + 60)) && /binding: pending\. Execution not released/.test(sci) && !/\b(?:granted|authori[sz]ed to run|released to run|execution released)\b/i.test(everything(d));
  },
  noZeroCost: (d) => {
    const all = everything(d);
    const metered = [...all.matchAll(/\b0 launches and 0 CPU-s\b/g)].every((m) => /cover metered container work only/.test(all.slice(m.index, m.index + 90)));
    return metered && /Current dollars: unknown, not zero\./.test(all) && !/(?:USD|\$)\s?0(?:\.0+)?\b|zero cost|no cost|free of charge|cost nothing/i.test(all);
  },
  agentsKeepIdentity: (d) => {
    const c = slide(render(d), "s-community");
    return /Agents keep their own identities; a human identity workaround is not allowed/.test(c) && !/cli-user|as the human|human (?:login|identity) (?:is )?(?:allowed|used|accepted)/i.test(everything(d));
  },
  noRedating: (d) => {
    const cutoff = asMs(d.source.factCutoff);
    return Object.values(d.facts).every((f) => f.asOfKind === "due" || asMs(f.asOf) <= cutoff) && d.facts["pr55.passed"].asOf === "2026-10-31 15:03 UTC" && !/15:08/.test(JSON.stringify(d) + everything(d));
  },
};
const mutateRendered = (d, from, to) => { const copy = clone(d); const s = JSON.stringify(copy).split(from).join(to); return JSON.parse(s); };
test("rejects a stale five-open PR55 presentation", () => {
  assert.ok(checks.staleFiveOpen(data));
  const stale = build((d) => { for (const f of d.milestones.find((m) => m.id === "DAY-PR55").findingDispositions) f.status = "OPEN"; });
  assert.ok(!checks.staleFiveOpen(stale));
});
test("rejects closure inflation", () => {
  assert.ok(checks.closureInflation(data));
  assert.ok(!checks.closureInflation(build((d) => { d.milestones.find((m) => m.id === "DAY-PR55").findingDispositions.find((f) => f.status === "OPEN").status = "CLOSED"; })));
});
test("rejects 70/70", () => {
  assert.ok(checks.noSeventyOfSeventy(data));
  assert.ok(!checks.noSeventyOfSeventy(build((d) => { const v = d.milestones.find((m) => m.id === "DAY-PR55").verification; v.selectedPassed = 70; v.selectedErrorsMissingNativeBinary = 0; })));
  assert.throws(() => build((d) => { d.milestones.find((m) => m.id === "DAY-PR55").verification.selectedPassed = 70; }), /do not add up/);
});
test("rejects grant inference from the native gate-zero envelope", () => {
  assert.ok(checks.noGrantFromEnvelope(data));
  assert.ok(!checks.noGrantFromEnvelope(mutateRendered(data, "pending", "bound")));
  assert.throws(() => build((d) => { d.nativeGateZero.exactCallAllocationAccepted = true; }), /promotes execution/);
  assert.throws(() => build((d) => { d.nativeGateZero.executionRelease = true; }), /promotes execution/);
});
test("rejects whole-run zero-cost inference", () => {
  assert.ok(checks.noZeroCost(data));
  assert.ok(!checks.noZeroCost(build((d) => { d.resources.currentTotalUsd = 0; })));
  assert.ok(!checks.noZeroCost(mutateRendered(data, "\"unknown\"", "\"USD 0\"")));
});
test("rejects human identity substitution", () => {
  assert.ok(checks.agentsKeepIdentity(data));
  assert.ok(!checks.agentsKeepIdentity(mutateRendered(data, "not allowed", "allowed")));
  assert.throws(() => build((d) => { d.priorities.helpRoomAdmission.humanIdentityWorkaroundAllowed = true; }), /own identities/);
});
test("rejects redating pre-cutoff facts from later verification", () => {
  assert.ok(checks.noRedating(data));
  assert.ok(!checks.noRedating(mutateRendered(data, "2026-10-31 15:03 UTC", "2026-10-31 15:08 UTC")));
  assert.throws(() => build((d) => { d.milestones.find((m) => m.id === "DAY-PR55").evidenceTimes.reviewedAt = "2026-10-31T15:08:55.164Z"; }), /after the fact cutoff/);
});

// ── 7. deck v1 and the exports ──────────────────────────────────────────────────────────────────────────────────────
test("deck v1 and its PDF stay byte-identical; the daytime PDF has its own packet-named file", () => {
  for (const [f, h] of Object.entries(FROZEN_V1)) assert.equal(sha(readFileSync(join(REPO_ROOT, f))), h, `${f} changed`);
  assert.equal(pdfName(PACKET), "SentiLab-deck-2026-10-31-daytime-1505.pdf");
  const v1 = relative(REPO_ROOT, join(PDF_DIR, pdfName("progress-2026-10-31"))).split(sep).join("/");
  assert.ok(Object.hasOwn(FROZEN_V1, v1), "the date-only name is the frozen v1 export, which the export script refuses to write");
  // The accepted daytime export is frozen too (PR 63): the export script refuses both sets of paths.
  const daytime = relative(REPO_ROOT, join(PDF_DIR, pdfName(PACKET))).split(sep).join("/");
  assert.ok(Object.hasOwn(FROZEN_DAYTIME, daytime), "the daytime export is frozen");
  for (const f of ["index.html", "deck.js", "deck.css", "deck-data.json", "deck-data.js"]) assert.ok(Object.hasOwn(FROZEN_DAYTIME, `deck/daytime/${f}`), f);
  const exporter = readFileSync(join(REPO_ROOT, "scripts", "export-deck-pdf.mjs"), "utf8");
  assert.match(exporter, /const FROZEN = \{ \.\.\.FROZEN_V1, \.\.\.FROZEN_DAYTIME \};/);
  assert.match(exporter, /if \(Object\.hasOwn\(FROZEN, rel\)\) throw/);
  assert.doesNotMatch(exporter, /new Date\(\)\.toISOString\(\)/, "the PDF name comes from the packet, not the clock");
  const pdf = join(PDF_DIR, pdfName(PACKET));
  assert.ok(existsSync(pdf), `${pdfName(PACKET)} is exported`);
  const pages = (readFileSync(pdf, "latin1").match(/\/Type\s*\/Page(?![s\w])/g) ?? []).length;
  assert.equal(pages, rendered.length, "one PDF page per slide");
  // Beside them only the dated supplement: its source files and its own PDF.
  assert.deepEqual(readdirSync(PDF_DIR).sort(), ["SentiLab-deck-2026-10-31-daytime-1505.pdf", "SentiLab-deck-2026-10-31.pdf", suppPdfName(), SUPPLEMENT.id]);
});
