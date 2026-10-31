#!/usr/bin/env node
// Builds the SentiLab daytime deck data from the selected progress packet's typed day update. The deck shows no number
// that is not in this output, and this output holds no number that is not a typed field of the packet.
//
//   node scripts/build-deck-data.mjs                   # select the packet, verify it, write deck/daytime/deck-data.json + .js
//   node scripts/build-deck-data.mjs --check           # exit 1 if the committed files differ from a fresh build
//   node scripts/build-deck-data.mjs --packet <id>     # build a named packet; it must pass every check below
//
// Packet selection: one rule (selectPacketId) for generation, --check and the CI test. Packets are
// docs/sentilab/progress-YYYY-MM-DD/ and docs/sentilab/progress-YYYY-MM-DD-daytime-HHMM/. A later date wins; on one date
// the plain (morning baseline) packet ranks before every daytime packet, and daytime packets rank by HHMM. A packet's
// date and HHMM must equal its sidecar's fact cutoff, so no packet can win with a name later than its facts. The
// selected packet must carry a supported typed day update: without one the build fails. It never falls back to an older
// packet, to progress.json prose or to PAGE-COPY.md.
//
// Inputs, every one verified before use (loadPacket):
//   PACKAGE-MANIFEST.json      every listed file's bytes and SHA256, the counts, and no unlisted file in the packet;
//   DAY-UPDATE.json            version sentilab-progress-day-update/2 only, valid against DAY-UPDATE.schema.json;
//   progress.json (+ schema)   the frozen legacy baseline: valid against its schema, byte-identical to baseline/ and to
//                              the original packet, and equal to the hashes the sidecar pins;
//   DAY-SOURCE-CATALOG.json    every evidence reference resolves, and every included source body matches its hash.
// The output records the SHA256 of each input file and of the manifest.
//
// Rules for the data (buildDeckData):
//   - Values come from typed sidecar fields, found by stable id, never by array position or by matching prose. Prose is
//     shown only verbatim (after the public-render rules) where the packet has no typed field for a count it requires.
//   - A typed null stays null. It shows "unknown", "not measured" or "none": never a number, never an older value.
//   - Every fact carries asOf ("YYYY-MM-DD HH:MM UTC") and asOfKind: the time from its own record and what that time
//     means (observed, reviewed, corrected, accepted, ...). A time is never taken from the newest cited evidence, and
//     nothing is dated after the fact cutoff except the delivery deadline.
//   - Copied text passes the public-render rules (no internal, vendor or agent names, room or run numbers, or paths).
//     Text that still breaks them after the fixed substitutions stops the build; it is never shipped.
// The build is deterministic: no wall-clock time is read, so a rebuild of the same packet gives the same bytes.
import { createHash } from "node:crypto";
import { existsSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { validateSchema } from "./json-schema-lite.mjs";

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "..");
export const PACKETS = join(REPO, "docs", "sentilab");
export const DECK_ROOT = join(REPO, "deck");               // served by the export script; holds the shared images
export const DECK_DIR = join(DECK_ROOT, "daytime");        // the deck this script builds
export const PDF_DIR = join(PACKETS, "deck");
// Deck v1 (PR 40) and its PDF are historical artifacts of the morning packet progress-2026-10-31. They are never
// rebuilt or re-exported: the deck test pins every byte, and the export script refuses to write any of these paths.
// The daytime deck reuses the three screenshots and the icon from deck/ without changing them.
export const FROZEN_V1 = {
  "deck/index.html": "14e1efd7b5fea1ea375844e2e2942e4caebbe4c1a84b4cb6e54a1bb862f4088b",
  "deck/deck.js": "691408fcce47fba1dac131817cce6ca2572aa87f12153ea03fe70ec2c24cc009",
  "deck/deck.css": "ef5d436f6e4959422e77b1ec79b7c04a9048c9d452cd9d73df837b85c22d9338",
  "deck/deck-data.json": "d12336887725db4d12ba4f18d346d65246895a196bfd8d487ecf3ee287f5d198",
  "deck/deck-data.js": "5fafc45ee324fee41f903eb438707dd987365138ebd8b70e02854924dc1f6077",
  "deck/favicon.svg": "b897974546f8ea69f9488c2d01ba83c8782264d0466ed8090be9470fa0f2f0db",
  "deck/img/lab-drill.png": "0b6991e01b9d62fcc3ef282897e7cf7e43521867169c62fbbbd53d5b08be42c3",
  "deck/img/lab-frozen.png": "7f913fa55ccfe44229b7dc5365705834a39f5fd7f9ef8b63ae5b1f7c6a841852",
  "deck/img/package-drill.png": "c0da2e80655006bc1f90eb0dc234cf5e7961568789b6e4841927e353d8f69d83",
  "docs/sentilab/deck/SentiLab-deck-2026-10-31.pdf": "666028044f1e59c85c6b70132ce3f04df4b0f76cb2d55eaa69d23aa0edc4b76c",
};
export const REPO_ROOT = REPO;
export const SIDECAR_VERSION = "sentilab-progress-day-update/2";
const MANIFEST_VERSION = "sentilab-private-day-publication-manifest/1";
const CATALOG_VERSION = "sentilab-day-source-catalog/1";
const DECK = { title: "SentiLab", version: "daytime draft v2", event: "ScienceClaw hackathon" };

export class PacketError extends Error {}

// ── public-render guard ─────────────────────────────────────────────────────────────────────────────────────────────
const SUBSTITUTIONS = [
  [/\bOpenResearch\b/g, "the research harness"],
  [/\bJev\b/g, "intent model"],
  [/\bthe missing Claude route\b/g, "the missing model route"],
  [/\bAscend[- ]v\d+\b/g, "headroom"],
  [/\bAneta\b/g, "the reviewer"],
  [/\bNebius\b/g, (m, at) => (at === 0 ? "Cloud-provider" : "cloud-provider")],
  [/\bTestFlight\b/g, "app-beta"],
  [/\s+on run \d{6,}\b/g, ""],            // CI run numbers are internal source ids; they stay in the evidence catalog
];
export const NOT_PUBLIC = [
  /\bJev\b/i, /\bTypeSafe\b/i, /\bCloudflare\b/i, /\bClaude\b/i, /\bAnthropic\b/i, /\bOpenAI\b/i, /\bGPT\b/i, /\bQwen\b/i,
  /\bNeMo\b/i, /\bNVIDIA\b/i, /\bTriton\b/i, /\bGemini\b/i, /\bLlama\b/i, /\bMistral\b/i, /\bDeepSeek\b/i, /\bAzure\b/i,
  /\bAWS\b/, /\bNebius\b/i, /\bTestFlight\b/i, /\bAscend\b/i, /\bOpenResearch\b/i, /\bMicroDuck\b/i, /\bPollen\b/i, /\bAneta\b/i,
  /\bwarden\b/i, /\bforge\b/i, /\bastra\b/i, /\broot\b/i, /\bcarter\b/i, /cli-user/i, /\b(?:human|root|warden|forge|astra)_?\d{2,}/i,
  /#\d{4,}/, /\b\d{6,}\b/, /[\w.+-]+@[\w-]+\.[a-z]{2,}/i, /\b[A-Za-z]:[\\/]/, /(?:^|[\s(])\/?(?:docs|web|scripts|contracts|tmp|home|Users)\//,
];
export function publicText(text, where) {
  let out = String(text);
  for (const [re, to] of SUBSTITUTIONS) out = out.replace(re, to);
  const bad = NOT_PUBLIC.find((re) => re.test(out));
  if (bad) throw new PacketError(`public-render rule ${bad} fails in ${where}: ${JSON.stringify(out)}`);
  return out;
}

// ── formatting ──────────────────────────────────────────────────────────────────────────────────────────────────────
export function utc(iso) {
  if (typeof iso !== "string") return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  const s = new Date(t).toISOString();
  return `${s.slice(0, 10)} ${s.slice(11, 16)} UTC`;
}
const WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"];
export const word = (n) => (Number.isInteger(n) && n >= 0 && n < WORDS.length ? WORDS[n] : String(n));
const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");
const isNum = (v) => typeof v === "number" && Number.isFinite(v);
const seconds = (v, dp) => `${v.toFixed(dp)} s`;
const thousands = (n) => n.toLocaleString("en-US");
const short = (sha) => (typeof sha === "string" && /^[0-9a-f]{40}$/.test(sha) ? sha.slice(0, 7) : null);

// ── packet selection ────────────────────────────────────────────────────────────────────────────────────────────────
const PACKET_ID = /^progress-(\d{4}-\d{2}-\d{2})(?:-daytime-([01]\d|2[0-3])([0-5]\d))?$/;
// The date and, for a daytime packet, the HH:MM its name states.
export function packetStamp(id) {
  const m = PACKET_ID.exec(id);
  if (!m || utc(`${m[1]}T00:00:00Z`)?.slice(0, 10) !== m[1]) return null;
  return { date: m[1], time: m[2] ? `${m[2]}:${m[3]}` : null };
}
// Sort key: date, then the plain packet (0) before daytime packets (1), then HH:MM.
const rank = (id) => { const s = packetStamp(id); return `${s.date}|${s.time ? `1|${s.time}` : "0|"}`; };
export function listPacketIds(root = PACKETS) {
  return readdirSync(root).filter((d) => packetStamp(d) && statSync(join(root, d)).isDirectory())
    .sort((a, b) => (rank(a) < rank(b) ? -1 : rank(a) > rank(b) ? 1 : 0));
}
export function selectPacketId(root = PACKETS) {
  const ids = listPacketIds(root);
  if (!ids.length) throw new PacketError(`no progress-YYYY-MM-DD[-daytime-HHMM] packet under ${root}`);
  return ids.at(-1);
}

// ── packet verification ─────────────────────────────────────────────────────────────────────────────────────────────
function walkFiles(dir, base = dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walkFiles(join(dir, e.name), base)
    : [relative(base, join(dir, e.name)).split(sep).join("/")]));
}
function collectRefs(value, out = new Set()) {
  if (Array.isArray(value)) value.forEach((v) => collectRefs(v, out));
  else if (value && typeof value === "object") for (const [k, v] of Object.entries(value)) {
    if (k === "evidenceRefs") { if (!Array.isArray(v)) throw new PacketError("evidenceRefs is not a list"); v.forEach((r) => out.add(r)); } else collectRefs(v, out);
  }
  return out;
}

// Reads and verifies a packet; returns the parsed inputs and their hashes. Throws PacketError on any failed check.
export function loadPacket(packetId, root = PACKETS) {
  const stamp = packetStamp(packetId);
  if (!stamp) throw new PacketError(`"${packetId}" is not a progress-YYYY-MM-DD[-daytime-HHMM] packet id`);
  const dir = join(root, packetId);
  if (!existsSync(dir)) throw new PacketError(`packet ${packetId} does not exist under ${root}`);
  const read = (f) => { const p = join(dir, f); if (!existsSync(p)) throw new PacketError(`${packetId}: ${f} is missing`); return readFileSync(p); };
  const json = (f, bytes = read(f)) => { try { return JSON.parse(bytes.toString("utf8")); } catch (e) { throw new PacketError(`${packetId}: ${f} is not JSON (${e.message})`); } };

  // 1. The typed day update must exist and be the one supported version, before anything else is read from the packet.
  if (!existsSync(join(dir, "DAY-UPDATE.json"))) {
    throw new PacketError(`${packetId} has no DAY-UPDATE.json: the daytime deck renders only a typed day update (${SIDECAR_VERSION}); it does not fall back to progress.json or PAGE-COPY.md prose`);
  }
  const sidecarBytes = read("DAY-UPDATE.json");
  const day = json("DAY-UPDATE.json", sidecarBytes);
  if (day?.schemaVersion !== SIDECAR_VERSION) {
    throw new PacketError(`${packetId}: unsupported day update version ${JSON.stringify(day?.schemaVersion)}; this builder supports only ${SIDECAR_VERSION}`);
  }

  // 2. Package integrity: every listed file matches, the counts match, and nothing unlisted is present.
  const manifestBytes = read("PACKAGE-MANIFEST.json");
  const manifest = json("PACKAGE-MANIFEST.json", manifestBytes);
  if (manifest.schemaVersion !== MANIFEST_VERSION) throw new PacketError(`${packetId}: unsupported manifest ${JSON.stringify(manifest.schemaVersion)}`);
  if (manifest.packetId !== packetId) throw new PacketError(`${packetId}: the manifest names packet ${manifest.packetId}`);
  const listed = Object.entries(manifest.files ?? {});
  let total = 0;
  for (const [f, want] of listed) {
    const b = read(f);
    total += b.length;
    if (b.length !== want.bytes || sha256(b) !== want.sha256) throw new PacketError(`${packetId}: ${f} does not match PACKAGE-MANIFEST.json`);
  }
  if (listed.length !== manifest.payloadFileCount || total !== manifest.payloadBytes) throw new PacketError(`${packetId}: manifest counts do not match its files`);
  const unlisted = walkFiles(dir).filter((f) => f !== "PACKAGE-MANIFEST.json" && !Object.hasOwn(manifest.files, f));
  if (unlisted.length) throw new PacketError(`${packetId}: files not in PACKAGE-MANIFEST.json: ${unlisted.join(", ")}`);
  if (manifest.factCutoff !== day.asOf?.includedEvidenceThrough) throw new PacketError(`${packetId}: manifest and day update disagree on the fact cutoff`);

  // 3. Both schemas.
  if (day.$schema !== "DAY-UPDATE.schema.json") throw new PacketError(`${packetId}: the day update names schema ${JSON.stringify(day.$schema)}`);
  const sidecarSchemaBytes = read("DAY-UPDATE.schema.json");
  const dayErrors = validateSchema(json("DAY-UPDATE.schema.json", sidecarSchemaBytes), day);
  if (dayErrors.length) throw new PacketError(`${packetId}: DAY-UPDATE.json fails its schema: ${dayErrors.slice(0, 5).join("; ")}`);
  const progressBytes = read("progress.json"), progressSchemaBytes = read("progress.schema.json");
  const progress = json("progress.json", progressBytes);
  const progressErrors = validateSchema(json("progress.schema.json", progressSchemaBytes), progress);
  if (progressErrors.length) throw new PacketError(`${packetId}: progress.json fails its schema: ${progressErrors.slice(0, 5).join("; ")}`);

  // 4. Identity and time binding: the folder name, the sidecar and its cutoff agree, so no name is later than its facts.
  if (day.packetId !== packetId) throw new PacketError(`${packetId}: the day update names packet ${day.packetId}`);
  const cutoff = day.asOf.includedEvidenceThrough;
  const cut = utc(cutoff);
  if (cut.slice(0, 10) !== stamp.date || (stamp.time && cut.slice(11, 16) !== stamp.time)) {
    throw new PacketError(`${packetId}: the packet name does not match its fact cutoff ${cut}`);
  }

  // 5. The legacy baseline stays byte-identical: to baseline/, to the hashes the sidecar pins, and to the original packet.
  const b = day.baseline;
  const legacy = [["progress.json", progressBytes, b.progressSha256], ["progress.schema.json", progressSchemaBytes, b.schemaSha256]];
  for (const [f, bytes, pinned] of legacy) {
    if (sha256(bytes) !== pinned) throw new PacketError(`${packetId}: ${f} is not the baseline the day update pins`);
    if (!read(`baseline/${f}`).equals(bytes)) throw new PacketError(`${packetId}: ${f} differs from baseline/${f}`);
    const original = join(root, b.packetId, f);
    if (existsSync(original) && !readFileSync(original).equals(bytes)) throw new PacketError(`${packetId}: ${f} differs from the original packet ${b.packetId}`);
  }

  // 6. Source bindings: every evidence reference resolves; every included body matches its catalog hash.
  const catalogBytes = read("DAY-SOURCE-CATALOG.json");
  const catalog = json("DAY-SOURCE-CATALOG.json", catalogBytes);
  if (catalog.schemaVersion !== CATALOG_VERSION || catalog.packetId !== packetId || !Array.isArray(catalog.sources)) {
    throw new PacketError(`${packetId}: unsupported or mismatched DAY-SOURCE-CATALOG.json`);
  }
  const sources = new Map();
  for (const s of catalog.sources) {
    if (sources.has(s.id)) throw new PacketError(`${packetId}: source ${s.id} is listed twice`);
    sources.set(s.id, s);
    if (s.bodyIncluded) {
      const body = read(s.packetPath);
      if (body.length !== s.bytes || sha256(body) !== s.sha256) throw new PacketError(`${packetId}: included source ${s.id} does not match its catalog hash`);
    }
  }
  const dangling = [...collectRefs(day)].filter((r) => !sources.has(r));
  if (dangling.length) throw new PacketError(`${packetId}: evidence references not in the source catalog: ${dangling.join(", ")}`);

  return {
    packetId, day, progress,
    hashes: {
      sidecarSha256: sha256(sidecarBytes), sidecarSchemaSha256: sha256(sidecarSchemaBytes),
      progressSha256: sha256(progressBytes), progressSchemaSha256: sha256(progressSchemaBytes),
      sourceCatalogSha256: sha256(catalogBytes), manifestSha256: sha256(manifestBytes),
    },
    sources: new Map([...sources].map(([id, s]) => [id, { kind: s.kind, sourceAt: s.sourceAt }])),
  };
}

// ── typed labels: every status the deck shows has a reviewed label; an unknown status stops the build ──────────────
const LABELS = {
  milestone: {
    scoped_accepted: "scoped slice accepted", source_accepted_execution_failed: "source accepted · execution failed",
    changes_requested: "changes requested", reviewed_direction_execution_gated: "reviewed direction · execution gated",
    static_review_complete: "static review complete", announced_acceptance_pending: "announced · acceptance pending",
    representative_rows_corroborated: "representative rows corroborated", assessment_complete_deployment_unproved: "assessment complete · deployment unproved",
    scoped_accepted_pending_ci_merge: "scoped accepted · CI and merge pending",
  },
  attempt: { completed_closed_historical: "completed · closed · historical", failed_closed: "failed · closed", completed_closed: "completed · closed" },
  finding: { CLOSED: "closed", CLOSED_SCOPED: "closed, scoped", OPEN: "open" },
  track: {
    accepted_direction_execution_gated: "accepted direction · execution gated", source_repairs_required_no_profile_grant: "source repairs required · no profiling grant",
    prospective_protocol_not_result: "prospective protocol · not a result", source_slice_reviewed_actual_labs_gated: "source slice reviewed · actual labs gated",
    dependent_work_not_whole_deliverable_completion: "dependent work · not a deliverable completion",
  },
  claim: {
    historical_operator_observations_not_corrected_physics_certification: "historical observations · not corrected physics",
    forecast_only: "forecast only", unproved_cause: "cause unproved", metric_corrected: "metric corrected",
    announced_not_end_to_end_accepted: "announced · not accepted end to end",
  },
  gate: { DESIGN_ALLOCATION_ACCEPTED_EXECUTION_BINDING_PENDING: "design allocation accepted · executable binding pending" },
  booking: { OPERATOR_REPORTED_NOT_INDEPENDENTLY_VERIFIED: "operator-reported · not independently verified" },
  deferral: { DEFERRED: "deferred to a later allocation" },
  plan: { NOT_REQUESTED: "not requested" },
  parallel: { continue_in_parallel_acceptance_pending: "continue in parallel · acceptance pending" },
  // What kind of evidence an accepted engineering slice has: only two of them include anything observed at runtime.
  evidence: {
    scoped_source_merge_and_http_evidence: "source, merge and production HTTP checks",
    scoped_actual_boot_and_source_evidence: "actual worker boot and source checks",
    scoped_source_merge_and_ci_evidence: "source, merge and CI only",
    retained_root_checkpoint: "retained merge and CI only",
  },
  ciJob: { FAILED: "failed" },
};
export function label(kind, status) {
  const l = LABELS[kind]?.[status];
  if (!l) throw new PacketError(`no reviewed label for ${kind} status ${JSON.stringify(status)}: add one before rendering it`);
  return l;
}
// Short topics for the corrected claims, by stable id. A claim id without a topic stops the build.
const CLAIM_TOPICS = {
  "CLAIM-OLD-THERMAL": "Old evaluator results", "CLAIM-BUDGET": "Budget fit", "CLAIM-047-CAUSE": "First serving failure",
  "CLAIM-047B-TIME": "Serving time unit", "CLAIM-HELP-READY": "Participant onboarding",
};
// The three GB10 attempt cards, by stable id. The deck has one card per id; a different set of attempts stops the build.
const ATTEMPTS = { "SLAB-018-attempt-1": "a018", "SLAB-047-attempt-1": "a047", "SLAB-047b": "a047b" };
const ATTEMPT_LABELS = { a018: "SLAB-018 attempt 1", a047: "SLAB-047", a047b: "SLAB-047b" };
// The legacy baseline record of the historical headroom verdict. The sidecar has no typed verdict field, so its exact
// title is shown verbatim, dated at the baseline cutoff (the record has no time of its own).
const HEADROOM_BASELINE_ID = "M05";
// The human direction behind "research first, one participant listener": the packet dates it through this cited room
// record (LEDGER: "Human direction through 14:49:30.285"). Its own catalog time keeps the accepted 14:49 date.
const HUMAN_DIRECTION_SOURCE = "human56774_reply";

// ── the typed adapter ───────────────────────────────────────────────────────────────────────────────────────────────
export function buildDeckData({ packetId, day, progress, hashes, sources = new Map() }) {
  const cutoff = day.asOf.includedEvidenceThrough;
  const cutoffMs = Date.parse(cutoff);
  const index = (list, what) => {
    const m = new Map();
    for (const x of list ?? []) { if (m.has(x.id)) throw new PacketError(`duplicate ${what} id ${x.id}`); m.set(x.id, x); }
    return m;
  };
  const need = (map, id, what) => { const x = map.get(id); if (!x) throw new PacketError(`${what} ${id} is missing from the day update`); return x; };
  const milestones = index(day.milestones, "milestone"), attempts = index(day.gb10Attempts, "GB10 attempt");
  const tracks = index(day.supplementalTracks, "supplemental track"), claims = index(day.claimDispositions, "claim");
  const history = index(day.history, "history"), baselineMilestones = index(progress.milestones, "baseline milestone");

  const facts = {};
  const fact = (key, { value = null, display, at, kind, source, ref }) => {
    if (facts[key]) throw new PacketError(`fact ${key} is defined twice`);
    const asOf = utc(at);
    if (!asOf) throw new PacketError(`${key}: no valid time`);
    if (Date.parse(at) > cutoffMs && kind !== "due") throw new PacketError(`${key}: dated ${asOf}, after the fact cutoff`);
    if (typeof display !== "string" || !display) throw new PacketError(`${key}: no display text`);
    facts[key] = { value, display: publicText(display, `fact ${key}`), asOf, asOfKind: kind, source, ref };
  };
  const num = (key, v, display, at, kind, source, ref) => {
    if (!isNum(v)) throw new PacketError(`${key}: ${ref} is not a number`);
    fact(key, { value: v, display, at, kind, source, ref });
  };
  const flag = (key, v, yes, no, at, kind, source, ref) => {
    if (typeof v !== "boolean") throw new PacketError(`${key}: ${ref} is not a boolean`);
    fact(key, { value: v, display: v ? yes : no, at, kind, source, ref });
  };
  // A typed value that may be null: null shows its stated label and never a number.
  const maybe = (key, v, show, nullLabel, at, kind, source, ref) => fact(key, { value: v ?? null, display: v == null ? nullLabel : show(v), at, kind, source, ref });

  // ── packet, baseline and status ──
  const PKT = "day update", BASE = "original scope", base = day.baseline, s = day.summary;
  fact("packet.cutoff", { value: utc(cutoff), display: utc(cutoff), at: cutoff, kind: "cutoff", source: "fact cutoff", ref: "asOf.includedEvidenceThrough" });
  fact("packet.baseline", { value: utc(base.coverageThrough), display: utc(base.coverageThrough), at: base.coverageThrough, kind: "baseline", source: BASE, ref: "baseline.coverageThrough" });
  if (base.originalTickets !== progress.tickets.length) throw new PacketError("the day update and the baseline disagree on the ticket count");
  if (base.deliverables !== progress.deliverables.length) throw new PacketError("the day update and the baseline disagree on the deliverable count");
  const sumOf = (k) => progress.tickets.reduce((n, t) => n + (t[k]?.length ?? 0), 0);
  if (base.cliDeclarations !== sumOf("cliRequired") || base.mcpDeclarations !== sumOf("mcpRequired")) throw new PacketError("the day update and the baseline disagree on CLI/MCP declarations");
  const accepted = progress.deliverables.filter((d) => d.completionVerified === true).length;
  const completeTickets = progress.tickets.filter((t) => t.wholeTicketCompletionVerified === true).length;
  if (base.fullyAcceptedDeliverables !== accepted || base.wholeTicketCompletions !== completeTickets) throw new PacketError("completion counts disagree with the baseline");
  if (s.allEightDeliverablesRemainIncomplete !== (base.fullyAcceptedDeliverables === 0 && base.deliverables === 8)) throw new PacketError("summary and baseline disagree on deliverable acceptance");
  if (base.scopeCountsAreNotImplementedCoverage !== true) throw new PacketError("scope counts must be marked as scope, not implemented coverage");
  const bAt = base.coverageThrough;
  num("scope.tickets", base.originalTickets, String(base.originalTickets), bAt, "baseline", BASE, "baseline.originalTickets");
  num("scope.requirements", base.requirements, String(base.requirements), bAt, "baseline", BASE, "baseline.requirements");
  num("scope.cli", base.cliDeclarations, String(base.cliDeclarations), bAt, "baseline", BASE, "baseline.cliDeclarations");
  num("scope.mcp", base.mcpDeclarations, String(base.mcpDeclarations), bAt, "baseline", BASE, "baseline.mcpDeclarations");
  num("scope.deliverables", base.deliverables, String(base.deliverables), bAt, "baseline", BASE, "baseline.deliverables");
  num("scope.ticketsComplete", base.wholeTicketCompletions, String(base.wholeTicketCompletions), cutoff, "cutoff", PKT, "baseline.wholeTicketCompletions");
  num("scope.accepted", base.fullyAcceptedDeliverables, String(base.fullyAcceptedDeliverables), cutoff, "cutoff", PKT, "baseline.fullyAcceptedDeliverables");
  num("scope.supplemental", day.supplementalTracks.length, String(day.supplementalTracks.length), cutoff, "cutoff", PKT, "supplementalTracks");
  fact("status.acceptance", {
    value: base.fullyAcceptedDeliverables,
    display: base.fullyAcceptedDeliverables === 0 ? `None of the ${word(base.deliverables)} deliverables is fully accepted.` : `${base.fullyAcceptedDeliverables} of ${base.deliverables} deliverables fully accepted.`,
    at: cutoff, kind: "cutoff", source: PKT, ref: ["baseline.fullyAcceptedDeliverables", "baseline.deliverables"],
  });
  flag("status.scientificBenefit", s.scientificBenefitEstablished, "established", "not established", cutoff, "cutoff", PKT, "summary.scientificBenefitEstablished");
  flag("status.fullCompletion", s.fullProjectCompletionVerified, "verified", "not verified", cutoff, "cutoff", PKT, "summary.fullProjectCompletionVerified");
  flag("status.publicProduction", s.publicProductionFullyAccepted, "fully accepted", "not fully accepted", cutoff, "cutoff", PKT, "summary.publicProductionFullyAccepted");
  flag("status.newExecution", s.newScientificExecutionReleased, "released", "not released", cutoff, "cutoff", PKT, "summary.newScientificExecutionReleased");

  // ── GB10: three separate attempts ──
  const ids = [...attempts.keys()].sort(), want = Object.keys(ATTEMPTS).sort();
  if (ids.join() !== want.join()) throw new PacketError(`the deck has cards for GB10 attempts ${want.join(", ")}, the day update has ${ids.join(", ")}`);
  for (const a of attempts.values()) if (a.retryAuthorized !== false || a.finalDeliverableAccepted !== false) throw new PacketError(`${a.id}: retry or final acceptance is not false`);
  num("gb10.count", attempts.size, word(attempts.size), cutoff, "cutoff", PKT, "gb10Attempts");
  const A = (id) => `gb10Attempts[${id}]`;
  const a1 = need(attempts, "SLAB-018-attempt-1", "GB10 attempt"), a2 = need(attempts, "SLAB-047-attempt-1", "GB10 attempt"), a3 = need(attempts, "SLAB-047b", "GB10 attempt");
  const G1 = "first attempt record", G2 = "failed attempt review", G3 = "serving attempt review";
  // An attempt's own time: its typed review time where it has one, else its retained evidence time (sourceAt), which
  // the packet defines as neither the experiment start nor its cleanup.
  const attemptAt = (a) => (a.reviewedAt ? [a.reviewedAt, "reviewed"] : [a.sourceAt, "evidence"]);
  for (const [k, a, src] of [["a018", a1, G1], ["a047", a2, G2], ["a047b", a3, G3]]) {
    const [at, kind] = attemptAt(a);
    fact(`${k}.label`, { value: a.id, display: ATTEMPT_LABELS[k], at, kind, source: src, ref: `${A(a.id)}.id` });
    fact(`${k}.status`, { value: a.status, display: label("attempt", a.status), at, kind, source: src, ref: `${A(a.id)}.status` });
    fact(`${k}.timeMetric`, { value: a.timeMetric, display: a.timeMetric, at, kind, source: src, ref: `${A(a.id)}.timeMetric` });
    num(`${k}.checks`, a.auditChecks, String(a.auditChecks), at, kind, src, `${A(a.id)}.auditChecks`);
  }
  const ratio = (key, n, d, at, kind, src, refs) => {
    if (!isNum(n) || !isNum(d)) throw new PacketError(`${key}: ratio parts are not numbers`);
    fact(key, { value: [n, d], display: `${n}/${d}`, at, kind, source: src, ref: refs });
  };
  // SLAB-018 attempt 1: the original training/save/reload/serve preflight.
  num("a018.steps", a1.optimizerSteps, String(a1.optimizerSteps), a1.sourceAt, "evidence", G1, `${A(a1.id)}.optimizerSteps`);
  num("a018.trainRows", a1.trainRowIdsConsumedOnce, String(a1.trainRowIdsConsumedOnce), a1.sourceAt, "evidence", G1, `${A(a1.id)}.trainRowIdsConsumedOnce`);
  num("a018.trainPrompts", a1.uniqueTrainPromptContents, String(a1.uniqueTrainPromptContents), a1.sourceAt, "evidence", G1, `${A(a1.id)}.uniqueTrainPromptContents`);
  num("a018.entries", a1.evaluationEntries, String(a1.evaluationEntries), a1.sourceAt, "evidence", G1, `${A(a1.id)}.evaluationEntries`);
  num("a018.http", a1.httpResponses, String(a1.httpResponses), a1.sourceAt, "evidence", G1, `${A(a1.id)}.httpResponses`);
  num("a018.sourceCases", a1.sourceCases, word(a1.sourceCases), a1.sourceAt, "evidence", G1, `${A(a1.id)}.sourceCases`);
  ratio("a018.adapter", a1.adapterExact, a1.denominator, a1.sourceAt, "evidence", G1, [`${A(a1.id)}.adapterExact`, `${A(a1.id)}.denominator`]);
  ratio("a018.base", a1.baseExact, a1.denominator, a1.sourceAt, "evidence", G1, [`${A(a1.id)}.baseExact`, `${A(a1.id)}.denominator`]);
  if (Math.abs(a1.stageChargeSeconds + a1.priorReservationSeconds - a1.totalAttributedSeconds) > 1e-6) throw new PacketError(`${a1.id}: stage + reservation != total`);
  num("a018.stage", a1.stageChargeSeconds, seconds(a1.stageChargeSeconds, 1), a1.sourceAt, "evidence", G1, `${A(a1.id)}.stageChargeSeconds`);
  num("a018.reservation", a1.priorReservationSeconds, seconds(a1.priorReservationSeconds, 0), a1.sourceAt, "evidence", G1, `${A(a1.id)}.priorReservationSeconds`);
  num("a018.total", a1.totalAttributedSeconds, seconds(a1.totalAttributedSeconds, 1), a1.sourceAt, "evidence", G1, `${A(a1.id)}.totalAttributedSeconds`);
  // SLAB-047: startup failure before inference.
  num("a047.requests", a2.completedRequests, String(a2.completedRequests), a2.sourceAt, "evidence", G2, `${A(a2.id)}.completedRequests`);
  num("a047.reservations", a2.inferenceReservations, String(a2.inferenceReservations), a2.sourceAt, "evidence", G2, `${A(a2.id)}.inferenceReservations`);
  num("a047.lifecycle", a2.stageChargeSeconds, seconds(a2.stageChargeSeconds, 1), a2.sourceAt, "evidence", G2, `${A(a2.id)}.stageChargeSeconds`);
  // SLAB-047b: the closed serving fixture.
  if (a3.sourceCasesSeenInTraining !== true || a3.labelsProvidedInPrompts !== true) throw new PacketError(`${a3.id}: the six-case and label caveats must stay true`);
  ratio("a047b.exact", a3.exactMatches, a3.denominator, a3.reviewedAt, "reviewed", G3, [`${A(a3.id)}.exactMatches`, `${A(a3.id)}.denominator`]);
  num("a047b.sourceCases", a3.sourceCases, word(a3.sourceCases), a3.reviewedAt, "reviewed", G3, `${A(a3.id)}.sourceCases`);
  num("a047b.lifecycle", a3.stageChargeSeconds, seconds(a3.stageChargeSeconds, 1), a3.reviewedAt, "reviewed", G3, `${A(a3.id)}.stageChargeSeconds`);
  num("a047b.preflight", a3.separateNativePreflightSeconds, seconds(a3.separateNativePreflightSeconds, 2), a3.reviewedAt, "reviewed", G3, `${A(a3.id)}.separateNativePreflightSeconds`);
  num("a047b.firstResponse", a3.firstClientResponseSeconds, seconds(a3.firstClientResponseSeconds, 1), a3.reviewedAt, "reviewed", G3, `${A(a3.id)}.firstClientResponseSeconds`);
  num("a047b.launchToHealth", a3.launchToHealthSeconds, seconds(a3.launchToHealthSeconds, 1), a3.reviewedAt, "reviewed", G3, `${A(a3.id)}.launchToHealthSeconds`);
  maybe("a047b.base", a3.baseComparison, (v) => String(v), "not measured in this attempt", a3.reviewedAt, "reviewed", G3, `${A(a3.id)}.baseComparison`);
  fact("a047b.lastResponse", { value: utc(a3.lastResponseAt), display: utc(a3.lastResponseAt), at: a3.lastResponseAt, kind: "last response", source: G3, ref: `${A(a3.id)}.lastResponseAt` });
  fact("a047b.cleanup", { value: utc(a3.cleanupConfirmedAt), display: utc(a3.cleanupConfirmedAt), at: a3.cleanupConfirmedAt, kind: "cleanup confirmed", source: G3, ref: `${A(a3.id)}.cleanupConfirmedAt` });

  // ── science: the historical verdict, the old results, the supplemental questions and native gate zero ──
  const m05 = need(baselineMilestones, HEADROOM_BASELINE_ID, "baseline milestone");
  fact("sci.headroom", { value: m05.status, display: m05.title, at: base.coverageThrough, kind: "baseline", source: "historical headroom record", ref: `baseline:milestones[${HEADROOM_BASELINE_ID}].title` });
  const old = need(claims, "CLAIM-OLD-THERMAL", "claim");
  if (old.replacement !== null) throw new PacketError("CLAIM-OLD-THERMAL now has a replacement: review the science slide before rendering it");
  fact("sci.oldResults", { value: old.status, display: label("claim", old.status), at: old.correctedAt, kind: "corrected", source: "claim corrections", ref: "claimDispositions[CLAIM-OLD-THERMAL].status" });
  const fields = need(milestones, "DAY-RETAINED-FIELDS", "milestone");
  fact("sci.fields", { value: fields.status, display: fields.title, at: fields.evidenceTimes.reviewedAt ?? fields.sourceAt, kind: "reviewed", source: "saved-field review", ref: "milestones[DAY-RETAINED-FIELDS].title" });
  const g = day.nativeGateZero, da = g.designAllocation, NG = "gate-zero design";
  if (g.executionRelease !== false || g.exactCallAllocationAccepted !== false || g.physicalAccuracyEstablished !== false || g.unseenStatisticalHoldoutClaim !== false || g.additionalPublishedVerificationIncludedInCurrent12 !== false) {
    throw new PacketError("native gate zero promotes execution, the exact allocation, physical accuracy or a holdout: review before rendering");
  }
  if (da.primaryCalls + da.freshProcessGrid64Replays !== da.totalCalls || da.totalCalls > g.prospectiveMaximumRuns) throw new PacketError("native gate zero design calls do not add up within the envelope");
  const gAt = da.acceptedAt;
  fact("ngz.status", { value: g.status, display: label("gate", g.status), at: gAt, kind: "accepted", source: NG, ref: "nativeGateZero.status" });
  fact("ngz.engine", { value: g.engine, display: g.engine, at: gAt, kind: "accepted", source: NG, ref: "nativeGateZero.engine" });
  fact("ngz.acceptedAt", { value: utc(gAt), display: utc(gAt), at: gAt, kind: "accepted", source: NG, ref: "nativeGateZero.designAllocation.acceptedAt" });
  num("ngz.primary", da.primaryCalls, String(da.primaryCalls), gAt, "accepted", NG, "nativeGateZero.designAllocation.primaryCalls");
  num("ngz.replays", da.freshProcessGrid64Replays, String(da.freshProcessGrid64Replays), gAt, "accepted", NG, "nativeGateZero.designAllocation.freshProcessGrid64Replays");
  num("ngz.total", da.totalCalls, String(da.totalCalls), gAt, "accepted", NG, "nativeGateZero.designAllocation.totalCalls");
  flag("ngz.binding", g.exactCallAllocationAccepted, "bound", "pending", gAt, "accepted", NG, "nativeGateZero.exactCallAllocationAccepted");
  flag("ngz.build", g.mergedBuildBound, "bound", "not bound", gAt, "accepted", NG, "nativeGateZero.mergedBuildBound");
  flag("ngz.release", g.executionRelease, "released", "not released", gAt, "accepted", NG, "nativeGateZero.executionRelease");
  maybe("ngz.grant", g.ownerLedgerReceipt, (v) => String(v), "none", gAt, "accepted", NG, "nativeGateZero.ownerLedgerReceipt");
  num("ngz.maxRuns", g.prospectiveMaximumRuns, String(g.prospectiveMaximumRuns), gAt, "accepted", NG, "nativeGateZero.prospectiveMaximumRuns");
  num("ngz.maxCpu", g.prospectiveMaximumCpuSeconds, `${thousands(g.prospectiveMaximumCpuSeconds)} CPU-s`, gAt, "accepted", NG, "nativeGateZero.prospectiveMaximumCpuSeconds");
  fact("ngz.targets", { value: g.referenceTargetsC, display: `${g.referenceTargetsC.map((t) => t.toFixed(2)).join(" / ")} °C`, at: gAt, kind: "accepted", source: NG, ref: "nativeGateZero.referenceTargetsC" });
  num("ngz.tolerance", g.prospectiveComputationalToleranceK, `${g.prospectiveComputationalToleranceK} K`, gAt, "accepted", NG, "nativeGateZero.prospectiveComputationalToleranceK");
  num("ngz.mm", g.packageSizeMm, `${g.packageSizeMm} mm`, gAt, "accepted", NG, "nativeGateZero.packageSizeMm");
  num("ngz.grid", g.grid, `grid-${g.grid}`, gAt, "accepted", NG, "nativeGateZero.grid");
  fact("ngz.extra", { value: g.additionalPublishedVerificationC, display: `${g.additionalPublishedVerificationC.map((t) => t.toFixed(2)).join(" / ")} °C`, at: gAt, kind: "accepted", source: NG, ref: "nativeGateZero.additionalPublishedVerificationC" });
  fact("ngz.extraStatus", { value: g.additionalPublishedVerificationStatus, display: label("deferral", g.additionalPublishedVerificationStatus), at: gAt, kind: "accepted", source: NG, ref: "nativeGateZero.additionalPublishedVerificationStatus" });
  fact("ngz.oldPlan", { value: g.materialOnlyHotspot7Plan, display: label("plan", g.materialOnlyHotspot7Plan), at: gAt, kind: "accepted", source: NG, ref: "nativeGateZero.materialOnlyHotspot7Plan" });
  // The engine of the old plan is named by its typed field, materialOnlyHotspot7Plan.
  num("ngz.oldPlanCalls", g.oldMaterialPlanCalls, `HotSpot 7 material-only ${g.oldMaterialPlanCalls}-call`, gAt, "accepted", NG, "nativeGateZero.oldMaterialPlanCalls");
  flag("ngz.physical", g.physicalAccuracyEstablished, "established", "not established", gAt, "accepted", NG, "nativeGateZero.physicalAccuracyEstablished");

  // ── open repairs: PR55, PR56, PR37 ──
  const p55 = need(milestones, "DAY-PR55", "milestone"), v55 = p55.verification, P55 = "PR55 corrective review";
  const t55 = p55.evidenceTimes.reviewedAt;
  const findings = index(p55.findingDispositions, "PR55 finding");
  const closed = [...findings.values()].filter((f) => f.status === "CLOSED" || f.status === "CLOSED_SCOPED");
  const open = [...findings.values()].filter((f) => f.status === "OPEN");
  if (closed.length + open.length !== findings.size) throw new PacketError("a PR55 finding has an unsupported status");
  if (v55.selectedPassed + v55.selectedErrorsMissingNativeBinary !== v55.selectedTests) throw new PacketError("PR55 selected tests do not add up");
  const prLabel = (key, m, at, kind, src) => {
    const n = /^DAY-PR(\d+)$/.exec(m.id)?.[1];
    if (!n) throw new PacketError(`${m.id} is not a pull-request milestone id`);
    fact(key, { value: m.id, display: `PR${n}`, at, kind, source: src, ref: `milestones[${m.id}].id` });
  };
  prLabel("pr55.label", p55, t55, "reviewed", P55);
  fact("pr55.status", { value: p55.status, display: label("milestone", p55.status), at: t55, kind: "reviewed", source: P55, ref: "milestones[DAY-PR55].status" });
  fact("pr55.head", { value: p55.head, display: short(p55.head), at: t55, kind: "reviewed", source: P55, ref: "milestones[DAY-PR55].head" });
  num("pr55.closed", closed.length, word(closed.length), t55, "reviewed", P55, "milestones[DAY-PR55].findingDispositions");
  num("pr55.open", open.length, word(open.length), t55, "reviewed", P55, "milestones[DAY-PR55].findingDispositions");
  fact("pr55.openSeverity", { value: open.map((f) => f.severity), display: open.map((f) => f.severity).join(", ") || "none", at: t55, kind: "reviewed", source: P55, ref: "milestones[DAY-PR55].findingDispositions" });
  num("pr55.passed", v55.selectedPassed, String(v55.selectedPassed), t55, "reviewed", P55, "milestones[DAY-PR55].verification.selectedPassed");
  num("pr55.selected", v55.selectedTests, String(v55.selectedTests), t55, "reviewed", P55, "milestones[DAY-PR55].verification.selectedTests");
  num("pr55.errors", v55.selectedErrorsMissingNativeBinary, word(v55.selectedErrorsMissingNativeBinary), t55, "reviewed", P55, "milestones[DAY-PR55].verification.selectedErrorsMissingNativeBinary");
  ratio("pr55.protocol", v55.protocolPassed, v55.protocolTests, t55, "reviewed", P55, ["milestones[DAY-PR55].verification.protocolPassed", "milestones[DAY-PR55].verification.protocolTests"]);
  num("pr55.ciPassed", v55.existingCiPassedJobs, word(v55.existingCiPassedJobs), t55, "reviewed", P55, "milestones[DAY-PR55].verification.existingCiPassedJobs");
  fact("pr55.ciContainer", { value: v55.existingCiContainer, display: label("ciJob", v55.existingCiContainer), at: t55, kind: "reviewed", source: P55, ref: "milestones[DAY-PR55].verification.existingCiContainer" });
  num("pr55.cardinality", v55.workerCardinalityFailingSubcases, word(v55.workerCardinalityFailingSubcases), t55, "reviewed", P55, "milestones[DAY-PR55].verification.workerCardinalityFailingSubcases");
  flag("pr55.native", v55.nativeExecution, "ran", "none", t55, "reviewed", P55, "milestones[DAY-PR55].verification.nativeExecution");
  fact("pr55.delivered", { value: utc(p55.evidenceTimes.publishedAt), display: utc(p55.evidenceTimes.publishedAt), at: p55.evidenceTimes.publishedAt, kind: "published", source: P55, ref: "milestones[DAY-PR55].evidenceTimes.publishedAt" });
  const h55 = need(history, "HISTORY-PR55-FIVE-HELD", "history");
  if (h55.factId !== "DAY-PR55") throw new PacketError("HISTORY-PR55-FIVE-HELD does not belong to DAY-PR55");
  fact("pr55.priorHead", { value: h55.priorHead, display: short(h55.priorHead), at: h55.recordedAt, kind: "recorded", source: "PR55 earlier review", ref: "history[HISTORY-PR55-FIVE-HELD].priorHead" });
  fact("pr55.superseded", { value: utc(h55.supersededAt), display: utc(h55.supersededAt), at: h55.supersededAt, kind: "superseded", source: "PR55 earlier review", ref: "history[HISTORY-PR55-FIVE-HELD].supersededAt" });

  const p56 = need(milestones, "DAY-PR56", "milestone"), v56 = p56.verification, P56 = "PR56 parser review", t56 = p56.evidenceTimes.reviewedAt;
  prLabel("pr56.label", p56, t56, "reviewed", P56);
  fact("pr56.title", { value: p56.title, display: p56.title, at: t56, kind: "reviewed", source: P56, ref: "milestones[DAY-PR56].title" });
  fact("pr56.status", { value: p56.status, display: label("milestone", p56.status), at: t56, kind: "reviewed", source: P56, ref: "milestones[DAY-PR56].status" });
  fact("pr56.head", { value: p56.head, display: short(p56.head), at: t56, kind: "reviewed", source: P56, ref: "milestones[DAY-PR56].head" });
  num("pr56.passed", v56.suppliedPassed, String(v56.suppliedPassed), t56, "reviewed", P56, "milestones[DAY-PR56].verification.suppliedPassed");
  num("pr56.skipped", v56.suppliedSkipped, word(v56.suppliedSkipped), t56, "reviewed", P56, "milestones[DAY-PR56].verification.suppliedSkipped");
  num("pr56.controls", v56.independentParserControls, word(v56.independentParserControls), t56, "reviewed", P56, "milestones[DAY-PR56].verification.independentParserControls");
  num("pr56.ciPassed", v56.existingCiPassedJobs, word(v56.existingCiPassedJobs), t56, "reviewed", P56, "milestones[DAY-PR56].verification.existingCiPassedJobs");
  flag("pr56.native", v56.nativeExecution, "ran", "none", t56, "reviewed", P56, "milestones[DAY-PR56].verification.nativeExecution");

  // PR37: the record's status is as of its latest review; the booking is the operator's later report (the record's
  // observedAt). The original failed bootstrap keeps its own historical time, which the packet does not type.
  const p37 = need(milestones, "DAY-PR37", "milestone"), P37 = "PR37 record", t37 = p37.evidenceTimes.reviewedAt;
  const book = day.resources.pr37Booking, BK = "operator booking report", tBook = p37.evidenceTimes.observedAt;
  if (book.secondAttemptReleased !== false || day.resources.pr37SecondAttemptReleased !== false) throw new PacketError("PR37 second attempt must not be released");
  prLabel("pr37.label", p37, t37, "reviewed", P37);
  fact("pr37.title", { value: p37.title, display: p37.title, at: t37, kind: "reviewed", source: P37, ref: "milestones[DAY-PR37].title" });
  fact("pr37.status", { value: p37.status, display: label("milestone", p37.status), at: t37, kind: "reviewed", source: P37, ref: "milestones[DAY-PR37].status" });
  fact("pr37.booking", { value: book.status, display: label("booking", book.status), at: tBook, kind: "reported", source: BK, ref: "resources.pr37Booking.status" });
  num("pr37.launches", book.conservativeLaunchDebit, String(book.conservativeLaunchDebit), tBook, "reported", BK, "resources.pr37Booking.conservativeLaunchDebit");
  num("pr37.cpu", book.conservativeCpuSecondsDebit, `${book.conservativeCpuSecondsDebit} CPU-s`, tBook, "reported", BK, "resources.pr37Booking.conservativeCpuSecondsDebit");
  num("pr37.meteredLaunches", book.reportedMeteredContainerLaunches, String(book.reportedMeteredContainerLaunches), tBook, "reported", BK, "resources.pr37Booking.reportedMeteredContainerLaunches");
  num("pr37.meteredCpu", book.reportedMeteredContainerCpuSeconds, `${book.reportedMeteredContainerCpuSeconds} CPU-s`, tBook, "reported", BK, "resources.pr37Booking.reportedMeteredContainerCpuSeconds");
  maybe("pr37.runnerCpu", book.runnerAdmissionCpuSeconds, (v) => `${v} CPU-s`, "unknown", tBook, "reported", BK, "resources.pr37Booking.runnerAdmissionCpuSeconds");
  maybe("pr37.money", book.money, (v) => `USD ${v}`, "unknown", tBook, "reported", BK, "resources.pr37Booking.money");

  // ── community ──
  const help = need(milestones, "DAY-HELP-ROOM", "milestone"), pr = day.priorities, adm = pr.helpRoomAdmission, HR = "help-room record";
  const tHelp = help.evidenceTimes.reviewedAt;
  if (adm.humanIdentityWorkaroundAllowed !== false || adm.agentIdentityRequired !== true) throw new PacketError("agents must keep their own identities; a human identity workaround must stay disallowed");
  fact("help.title", { value: help.title, display: help.title, at: tHelp, kind: "reviewed", source: HR, ref: "milestones[DAY-HELP-ROOM].title" });
  fact("help.status", { value: help.status, display: label("milestone", help.status), at: tHelp, kind: "reviewed", source: HR, ref: "milestones[DAY-HELP-ROOM].status" });
  flag("help.researchFirst", pr.researchFirst, "research first", "research not first", tHelp, "reviewed", HR, "priorities.researchFirst");
  fact("help.materials", { value: pr.missingParticipantMaterialsAndUx, display: label("parallel", pr.missingParticipantMaterialsAndUx), at: tHelp, kind: "reviewed", source: HR, ref: "priorities.missingParticipantMaterialsAndUx" });
  const direction = sources.get(HUMAN_DIRECTION_SOURCE);
  if (!direction || direction.kind !== "human_room_record" || !pr.evidenceRefs.includes(HUMAN_DIRECTION_SOURCE)) {
    throw new PacketError(`the human direction record ${HUMAN_DIRECTION_SOURCE} is not a human room record cited by the priorities`);
  }
  fact("help.direction", { value: utc(direction.sourceAt), display: utc(direction.sourceAt), at: direction.sourceAt, kind: "human direction", source: HR, ref: `catalog:sources[${HUMAN_DIRECTION_SOURCE}].sourceAt` });
  fact("help.checkpoint", { value: utc(day.asOf.checkpointAt), display: utc(day.asOf.checkpointAt), at: day.asOf.checkpointAt, kind: "checkpoint", source: HR, ref: "asOf.checkpointAt" });
  flag("help.interruptions", adm.humanApprovalInterruptionsRequired, "required", "none", tHelp, "reviewed", HR, "priorities.helpRoomAdmission.humanApprovalInterruptionsRequired");
  flag("help.autoAdmission", adm.operatorReportedAutomaticAdmission, "operator-reported", "not reported", tHelp, "reviewed", HR, "priorities.helpRoomAdmission.operatorReportedAutomaticAdmission");
  flag("help.verified", adm.independentImplementationVerification, "independently verified", "not independently verified", tHelp, "reviewed", HR, "priorities.helpRoomAdmission.independentImplementationVerification");
  flag("help.identity", adm.humanIdentityWorkaroundAllowed, "allowed", "not allowed", tHelp, "reviewed", HR, "priorities.helpRoomAdmission.humanIdentityWorkaroundAllowed");
  flag("help.secondApprover", adm.secondAutoApproverRequested, "requested", "not requested", tHelp, "reviewed", HR, "priorities.helpRoomAdmission.secondAutoApproverRequested");
  fact("help.listener", { value: "single", display: adm.singleListenerOwner === pr.participantListenerOwner ? "one agent" : "unresolved", at: tHelp, kind: "reviewed", source: HR, ref: ["priorities.participantListenerOwner", "priorities.helpRoomAdmission.singleListenerOwner"] });
  const helpClaim = need(claims, "CLAIM-HELP-READY", "claim");
  fact("help.claim", { value: helpClaim.status, display: helpClaim.replacement ?? label("claim", helpClaim.status), at: helpClaim.correctedAt, kind: "corrected", source: "claim corrections", ref: "claimDispositions[CLAIM-HELP-READY].replacement" });
  const crit = need(milestones, "DAY-INFORMED-CRITIQUE", "milestone"), neb = need(milestones, "DAY-NEBIUS", "milestone");
  fact("research.critique", { value: crit.status, display: label("milestone", crit.status), at: crit.evidenceTimes.reviewedAt, kind: "reviewed", source: "informed critique", ref: "milestones[DAY-INFORMED-CRITIQUE].status" });
  fact("research.delivered", { value: utc(crit.evidenceTimes.publishedAt), display: utc(crit.evidenceTimes.publishedAt), at: crit.evidenceTimes.publishedAt, kind: "published privately", source: "research supplement", ref: "milestones[DAY-INFORMED-CRITIQUE].evidenceTimes.publishedAt" });
  fact("research.cloud", { value: neb.status, display: label("milestone", neb.status), at: neb.evidenceTimes.publishedAt, kind: "published privately", source: "cloud assessment", ref: "milestones[DAY-NEBIUS].status" });

  // ── cost and authority ──
  const r = day.resources, CO = "cost record";
  if (r.historicalEstimateIsNotCurrentTotal !== true) throw new PacketError("the historical estimate must stay marked as not current");
  maybe("cost.current", r.currentTotalUsd, (v) => `USD ${v}`, "unknown", cutoff, "cutoff", CO, "resources.currentTotalUsd");
  maybe("cost.cpu", r.comprehensiveCpuSeconds, (v) => `${v} CPU-s`, "unknown", cutoff, "cutoff", CO, "resources.comprehensiveCpuSeconds");
  flag("cost.invoice", r.invoiceVerified, "verified", "not verified", cutoff, "cutoff", CO, "resources.invoiceVerified");
  num("cost.historical", r.lastHistoricalEstimateUsd, `USD ${r.lastHistoricalEstimateUsd.toFixed(2)}`, r.lastHistoricalEstimateAt, "estimated", CO, "resources.lastHistoricalEstimateUsd");
  fact("authority.expired", { value: utc(r.oldScientificDeadlineExpiredAt), display: utc(r.oldScientificDeadlineExpiredAt), at: r.oldScientificDeadlineExpiredAt, kind: "expired", source: "scientific authority", ref: "resources.oldScientificDeadlineExpiredAt" });
  fact("delivery.deadline", { value: utc(day.delivery.deadline), display: utc(day.delivery.deadline), at: day.delivery.deadline, kind: "due", source: "delivery", ref: "delivery.deadline" });

  // ── lists ──
  const evidenceTime = (m) => {
    // A milestone's time is its own: the most specific typed event time, else the evidence observation time it states.
    const t = m.evidenceTimes ?? {};
    if (t.observedAt) return [t.observedAt, "observed"];
    if (t.reviewedAt) return [t.reviewedAt, "reviewed"];
    return [m.sourceAt, "evidence"];
  };
  const prOf = (id) => /^DAY-PR(\d+)$/.exec(id)?.[1] ?? null;
  const engineering = [...milestones.values()].filter((m) => m.status === "scoped_accepted" && short(m.head) && short(m.merge))
    .sort((x, y) => Date.parse(x.sourceAt) - Date.parse(y.sourceAt) || (x.id < y.id ? -1 : 1))
    .map((m) => {
      const [at, kind] = evidenceTime(m);
      const superseded = [...history.values()].filter((h) => h.factId === m.id).map((h) => ({
        id: h.id, prior: label("milestone", h.priorStatus), now: label("milestone", h.replacementStatus),
        recorded: utc(h.recordedAt), superseded: utc(h.supersededAt), asOf: utc(h.supersededAt), asOfKind: "superseded",
      }));
      // The typed summary is shown verbatim only where it carries the scoped counts the packet has no field for.
      const show = ["DAY-PR51", "DAY-PR53", "DAY-PR54"].includes(m.id);
      return {
        id: m.id, pr: prOf(m.id) ? `PR${prOf(m.id)}` : m.id, title: publicText(m.title, `${m.id}.title`), status: m.status,
        statusLabel: label("milestone", m.status), evidence: label("evidence", m.classification), head: short(m.head), merge: short(m.merge),
        summary: show ? publicText(m.summary, `${m.id}.summary`) : null,
        limits: m.limitations.map((l, i) => publicText(l, `${m.id}.limitations[${i}]`)),
        superseded, asOf: utc(at), asOfKind: kind,
      };
    });
  // Closed findings first, then open ones, each by id: the order never depends on the packet's array order.
  const openLast = (f) => (f.status === "OPEN" ? 1 : 0);
  const findingList = [...findings.values()].sort((x, y) => openLast(x) - openLast(y) || (x.id < y.id ? -1 : 1))
    .map((f) => ({ id: f.id, severity: f.severity, status: f.status, statusLabel: label("finding", f.status), scope: publicText(f.scope, `${f.id}.scope`), asOf: utc(t55), asOfKind: "reviewed" }));
  const trackList = [...tracks.values()].sort((x, y) => (x.id < y.id ? -1 : 1))
    .map((t) => ({ id: t.id, name: t.name, status: t.status, statusLabel: label("track", t.status), purpose: publicText(t.purpose, `${t.id}.purpose`), asOf: utc(cutoff), asOfKind: "cutoff" }));
  const claimList = [...claims.values()].sort((x, y) => (x.id < y.id ? -1 : 1)).map((c) => {
    if (!CLAIM_TOPICS[c.id]) throw new PacketError(`claim ${c.id} has no reviewed topic`);
    return {
      id: c.id, topic: CLAIM_TOPICS[c.id], status: c.status, statusLabel: label("claim", c.status),
      // A null replacement stays null: the earlier claim is never shown or reused in its place.
      replacement: c.replacement == null ? null : publicText(c.replacement, `${c.id}.replacement`),
      reason: publicText(c.reason, `${c.id}.reason`), asOf: utc(c.correctedAt), asOfKind: "corrected",
    };
  });
  const h55List = [{ id: h55.id, prior: label("milestone", h55.priorStatus), summary: publicText(h55.priorSummary, `${h55.id}.priorSummary`), head: short(h55.priorHead), recorded: utc(h55.recordedAt), superseded: utc(h55.supersededAt), asOf: utc(h55.supersededAt), asOfKind: "superseded" }];
  const bindingList = g.requiredBindings.map((x, i) => ({ id: `binding-${i + 1}`, text: publicText(x, `nativeGateZero.requiredBindings[${i}]`), asOf: utc(gAt), asOfKind: "accepted" }));
  const prose = (m, what) => ({ id: m.id, title: publicText(m.title, `${m.id}.title`), statusLabel: label("milestone", m.status), [what]: true });
  const science = [
    { ...prose(crit, "critique"), summary: publicText(crit.summary, "DAY-INFORMED-CRITIQUE.summary"), limits: crit.limitations.map((l, i) => publicText(l, `DAY-INFORMED-CRITIQUE.limitations[${i}]`)), asOf: utc(crit.evidenceTimes.reviewedAt), asOfKind: "reviewed" },
    { ...prose(fields, "fields"), summary: publicText(fields.summary, "DAY-RETAINED-FIELDS.summary"), limits: fields.limitations.map((l, i) => publicText(l, `DAY-RETAINED-FIELDS.limitations[${i}]`)), asOf: utc(fields.evidenceTimes.reviewedAt), asOfKind: "reviewed" },
  ];
  const helpLimits = help.limitations.map((l, i) => ({ id: `help-${i + 1}`, text: publicText(l, `DAY-HELP-ROOM.limitations[${i}]`), asOf: utc(tHelp), asOfKind: "reviewed" }));
  const research = [
    { ...prose(neb, "cloud"), limits: neb.limitations.map((l, i) => publicText(l, `DAY-NEBIUS.limitations[${i}]`)), asOf: utc(neb.evidenceTimes.publishedAt), asOfKind: "published privately" },
  ];
  const ticketDeliverables = (t) => progress.deliverables.filter((d) => (d.tickets ?? []).includes(t.id)).map((d) => d.id);
  const tickets = progress.tickets.map((t) => ({
    id: t.id, n: String(t.id).replace(/^SLAB-/, ""), status: t.status, optional: t.disposition === "optional_deferred",
    complete: t.wholeTicketCompletionVerified === true, deliverables: ticketDeliverables(t), asOf: utc(base.coverageThrough), asOfKind: "baseline",
  }));
  const deliverables = progress.deliverables.map((d) => ({
    id: d.id, title: publicText(d.title, d.id), baselineStatus: d.status, accepted: d.completionVerified === true,
    tickets: d.tickets ?? [], asOf: utc(base.coverageThrough), asOfKind: "baseline",
  }));
  const statusLegend = Object.fromEntries(Object.entries(progress.statusLegend ?? {}).map(([k, v]) => [k, publicText(v, `statusLegend.${k}`)]));

  const lists = { engineering, findings: findingList, pr55History: h55List, tracks: trackList, claims: claimList, bindings: bindingList,
    helpLimits, science, research, deliverables, tickets, statusLegend };

  // ── speaker notes: six main slides in about 2:45 (25–30 s each); every number spoken is a fact on the deck ──
  const F = (k) => { if (!facts[k]) throw new PacketError(`notes use unknown fact ${k}`); return facts[k].display; };
  const notes = [
    { slide: "problem", target: "25–30 s", text: [
      "Many AI agents now produce engineering findings.",
      "Most get lost in chats and logs, nobody can check what actually ran,",
      "and when an input turns out wrong, nothing shows what else it broke.",
      "SentiLab is a lab designed around that problem.",
      "By design, every result is signed, reproduced before it is accepted, and correctable later.",
      "Next: what we demonstrated on a fixture, and what is accepted.",
    ] },
    { slide: "how", target: "25–30 s", text: [
      "Here is the design. Labs propose candidate layouts.",
      "A deterministic gate, with no model deciding, accepts only reproduced, verified results.",
      "Every event goes into a hash-chained, signed log, and the Lab view shows only the verified prefix.",
      "On the right, a test-key fixture: a dropped event freezes the board.",
      "What is accepted so far are scoped engineering slices; only two include runtime checks. That is not production acceptance.",
    ] },
    { slide: "correction", target: "25–30 s", text: [
      "This is a correction, as a drill.",
      "A lab proposes a candidate, it is re-run in a fresh process, and the gate accepts it.",
      "Then we withdraw a measurement on purpose. Everything that depended only on it goes stale,",
      "and the candidate stands on its independent reproduction.",
      "Both views replay a test-key fixture; no solver ran.",
      "This is the mechanism, not the scientific correction, which is still open.",
    ] },
    { slide: "gb10", target: "25–30 s", text: [
      `On the GB10 we ran ${F("gb10.count")} separate attempts.`,
      `The original preflight trained ${F("a018.steps")} steps and scored ${F("a018.adapter")} for the adapter against ${F("a018.base")} for the base, on ${F("a018.sourceCases")} source cases already seen in training, with labels supplied.`,
      "The second failed at startup, before inference.",
      `The third served ${F("a047b.exact")}, on ${F("a047b.sourceCases")} source cases already seen in training, with labels in the prompts,`,
      `in ${F("a047b.lifecycle")} of lifecycle wall time, not GPU time.`,
      "Only the serving fixture worked; learning is not shown.",
    ] },
    { slide: "science", target: "25–30 s", text: [
      "On the science, the historical headroom result remains inconclusive, and the old evaluator's results stay historical.",
      "Review sharpened the questions: references, thermal coupling, profiling, constrained screening, agent proposals and truthful labels.",
      "Those are hypotheses, not results.",
      `Next is a native gate zero. Its design is accepted: ${F("ngz.primary")} primary calls plus ${F("ngz.replays")} replays.`,
      "The executable binding and grant are pending, so nothing has run.",
      "We claim no calibrated temperature and no optimality.",
    ] },
    { slide: "status", target: "25–30 s", text: [
      `Where it stands. ${F("status.acceptance")}`,
      `The original scope is ${F("scope.tickets")} tickets and ${F("scope.requirements")} requirements: obligations, not finished work.`,
      `Open repairs: the profiling change has ${F("pr55.closed")} scoped closures, ${F("pr55.open")} open finding and ${F("pr55.cardinality")} failing CI cases;`,
      "a parser fix needs one repair; for a failed bootstrap, the operator reports booking the full conservative debit.",
      "Research stays first. Current spending is unknown, not zero.",
      "Every number here is dated. Thank you.",
    ] },
    { slide: "rules", target: "backup", text: [
      "Backup: the evidence rules, as designed and as the executable contract vectors check them.",
      "The core is the only writer. Each event is a signed envelope chained to the previous one.",
      "The view projects only the verified prefix. At the first break it stops.",
      "LIVE needs verified progress, not just arrivals. Otherwise the label says STALE.",
      "Known limit: a server can withhold a suffix. Only a later full replay shows that.",
    ] },
    { slide: "engineering", target: "backup", text: [
      "Backup: the reviewed engineering slices.",
      "Each card is one change with its exact head and merge, its retained checks and its stated limits.",
      "The admission and stop fix was first seen with CI and merge pending; the later merge record supersedes only that pending status.",
      "None of these merges releases science, a model or a device, and browser reports from the operator stay separate.",
    ] },
    { slide: "queue", target: "backup", text: [
      `Backup: the open queue. The profiling change closes ${F("pr55.closed")} of its findings within source and fixture scope; the unknown-method finding is still open.`,
      `Of ${F("pr55.selected")} selected tests, ${F("pr55.passed")} passed and ${F("pr55.errors")} errored for a missing native binary, so it is not a full pass.`,
      `The container job fails ${F("pr55.cardinality")} cardinality cases that need valid owned workspaces.`,
      "The earlier five-finding review stays on record as history.",
      `The failed bootstrap's conservative booking of ${F("pr37.launches")} launches is operator-reported; its reported zero covers metered container work only, not runner CPU or money.`,
    ] },
    { slide: "community", target: "backup", text: [
      "Backup: participant help.",
      "The announcement is out and a starter kit has scoped reviews, but a fresh outside account has not been shown end to end.",
      "Research stays first. One agent is the sole participant listener, with no duplicate approver.",
      "Ordinary help-room work needs no human approval step, and agents keep their own identities; a human identity is not a workaround.",
      "The research supplement was delivered privately. The cloud assessment is documentation, not a tested transfer, connection, deployment or restart.",
    ] },
    { slide: "coverage", target: "backup", text: [
      `Backup: scope and cost. ${F("scope.tickets")} tickets map to ${F("scope.deliverables")} deliverables, with ${F("scope.requirements")} requirements and ${F("scope.cli")} CLI and ${F("scope.mcp")} MCP declarations.`,
      "Those are the original obligations, not implemented counts. The chips show each ticket's status at the morning baseline.",
      `The ${F("scope.supplemental")} supplemental tracks add work outside the original tickets.`,
      `Current dollars and total CPU are unknown. ${F("cost.historical")} is a historical estimate, not a current balance.`,
    ] },
    { slide: "corrections", target: "backup", text: [
      "Backup: our own claims, corrected and dated.",
      "A forecast is not an impossibility proof, an unretained mount flag is not a proven cause, and a lifecycle wall time is not GPU time.",
      "Onboarding was reviewed in source and documents, not proven for an outside account.",
      "The old evaluator's results have no replacement claim: they stay historical, and we do not restate them as current.",
    ] },
    { slide: "sources", target: "backup", text: [
      "Backup: the source findings behind the sharper questions.",
      "The informed model critique matched both frozen hashes, corroborates the coupling lead in source and challenges the centre metric. Its model was not run here.",
      "The saved native fields were re-read across all of their grids, and only two representative cases were re-parsed independently.",
      "These are hand-authored probes, not the headroom study, and no new solve ran.",
    ] },
  ].map((n) => ({ ...n, text: publicText(n.text.join(" "), `notes.${n.slide}`) }));

  return {
    schema: "sentilab-deck-data/2",
    deck: DECK,
    source: {
      packetId, sidecarVersion: day.schemaVersion, baselinePacketId: base.packetId, draft: day.draft === true,
      factCutoff: utc(cutoff), checkpointAt: utc(day.asOf.checkpointAt), baselineCoverageThrough: utc(base.coverageThrough),
      ...hashes,
    },
    facts, lists, notes,
  };
}

// ── CLI ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
export function buildFromPacket(packetId = selectPacketId(), root = PACKETS) {
  return buildDeckData(loadPacket(packetId, root));
}
export const serialize = (data) => {
  const json = JSON.stringify(data, null, 2) + "\n";
  return { json, js: `// Generated by build-deck-data. Same object as deck-data.json, for file:// viewing.\nwindow.DECK_DATA = ${json.trimEnd()};\n` };
};
// The PDF for a packet: the packet id's date and daytime suffix, so a later export never replaces an earlier one.
export const pdfName = (packetId) => `SentiLab-deck-${packetId.replace(/^progress-/, "")}.pdf`;

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  const at = args.indexOf("--packet");
  try {
    const packetId = at >= 0 ? args[at + 1] : selectPacketId();
    const { json, js } = serialize(buildFromPacket(packetId));
    const jsonPath = join(DECK_DIR, "deck-data.json"), jsPath = join(DECK_DIR, "deck-data.js");
    if (args.includes("--check")) {
      const same = (p, s) => existsSync(p) && readFileSync(p, "utf8") === s;
      if (!same(jsonPath, json) || !same(jsPath, js)) { console.error(`deck-data is stale for ${packetId}: run node scripts/build-deck-data.mjs`); process.exit(1); }
      console.log(`deck-data matches ${packetId}`);
    } else {
      writeFileSync(jsonPath, json);
      writeFileSync(jsPath, js);
      const data = JSON.parse(json);
      console.log(`wrote deck-data.json + deck-data.js from ${packetId} (${Object.keys(data.facts).length} facts, sidecar ${data.source.sidecarSha256.slice(0, 12)})`);
    }
  } catch (e) {
    if (!(e instanceof PacketError)) throw e;
    console.error(`build-deck-data: ${e.message}`);
    process.exit(1);
  }
}
