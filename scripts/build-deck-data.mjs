#!/usr/bin/env node
// Builds the SentiLab deck data from the dated progress packet. The deck shows no number that is not in this output.
//
//   node scripts/build-deck-data.mjs                 # newest docs/sentilab/progress-YYYY-MM-DD/ -> deck-data.json + deck-data.js
//   node scripts/build-deck-data.mjs --packet progress-2026-10-31
//   node scripts/build-deck-data.mjs --check         # exit 1 if the committed files differ from a fresh build
//
// Inputs: progress.json (structured facts) and PAGE-COPY.md (the scoped wording, and the GB10 cap it states).
// Output: web/public/sentilab/deck/deck-data.json, plus deck-data.js (the same object as a script, so the deck also
// opens from a file:// path). The build is deterministic: no wall-clock time is read, so a rebuild of the same packet
// gives the same bytes.
//
// Rules:
//   - A value the packet does not state is null, and the deck shows PENDING for it. Nothing is estimated or filled in.
//   - Every fact carries asOf, "YYYY-MM-DD HH:MM UTC": the newest of the item's own sourceAt and the dated evidence it
//     cites, else the packet's coverage cutoff.
//   - Copied text passes the public-render rules (role labels, no internal or vendor names, no room numbers, no paths).
//     A text that still breaks them after the fixed substitutions below stops the build; it is never shipped.
import { createHash } from "node:crypto";
import { existsSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const PACKETS = join(REPO, "docs", "sentilab");
const OUT_DIR = join(REPO, "web", "public", "sentilab", "deck");
export const PENDING = "— (pending freeze)";
const DECK = { title: "SentiLab", version: "draft v1", event: "ScienceClaw hackathon" };

// ── public-render guard ─────────────────────────────────────────────────────────────────────────────────────────────
const SUBSTITUTIONS = [
  [/\bOpenResearch\b/g, "the research harness"],
  [/\bJev\b/g, "intent model"],
  [/\bthe missing Claude route\b/g, "the missing model route"],
  [/\bAscend v\d+\b/g, "headroom"],
  [/\bAneta\b/g, "the reviewer"],
];
const NOT_PUBLIC = [
  /\bJev\b/i, /\bTypeSafe\b/i, /\bCloudflare\b/i, /\bClaude\b/i, /\bAnthropic\b/i, /\bOpenAI\b/i, /\bGPT\b/i, /\bQwen\b/i,
  /\bNeMo\b/i, /\bNVIDIA\b/i, /\bGemini\b/i, /\bLlama\b/i, /\bMistral\b/i, /\bDeepSeek\b/i, /\bAzure\b/i, /\bAscend\b/i,
  /\bOpenResearch\b/i, /\bMicroDuck\b/i, /\bPollen\b/i, /\bAneta\b/i, /\bwarden\b/i, /\bforge\b/i, /\bastra\b/i,
  /\broot ?0\d\d\b/i, /#\d{4,}/, /[\w.+-]+@[\w-]+\.[a-z]{2,}/i, /\b[A-Za-z]:[\\/]/, /(?:^|[\s(])(?:docs|web|scripts|contracts)\//,
];
export function publicText(text, where) {
  let out = String(text);
  for (const [re, to] of SUBSTITUTIONS) out = out.replace(re, to);
  const bad = NOT_PUBLIC.find((re) => re.test(out));
  if (bad) throw new Error(`public-render rule ${bad} fails in ${where}: ${JSON.stringify(out)}`);
  return out;
}

// ── formatting ──────────────────────────────────────────────────────────────────────────────────────────────────────
export function utc(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return `${d.toISOString().slice(0, 10)} ${d.toISOString().slice(11, 16)} UTC`;
}
const WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"];
const word = (n) => (Number.isInteger(n) && n >= 0 && n < WORDS.length ? WORDS[n] : String(n));
const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);
const round = (v, dp) => Number(v.toFixed(dp));
const newest = (isos) => isos.filter(Boolean).map((s) => [s, Date.parse(s)]).filter(([, t]) => !Number.isNaN(t))
  .sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
const firstMatch = (texts, re) => { for (const t of texts) { const m = re.exec(t ?? ""); if (m) return m; } return null; };

export function buildDeckData({ progress: p, pageCopy, packetId, progressSha256, pageCopySha256 }) {
  const ev = p.evidence ?? {};
  const cutoff = p.snapshot?.coverageFactsThrough ?? null;
  // An item is as current as the newest dated source behind it: its own sourceAt or any evidence it cites (a dated
  // correction can be newer than the item's baseline).
  const asOfItem = (item) => newest([item?.sourceAt, ...(item?.evidenceRefs ?? []).map((k) => ev[k]?.sourceAt)]) ?? cutoff;
  const asOfRefs = (refs) => newest(refs.map((k) => ev[k]?.sourceAt)) ?? cutoff;

  const facts = {};
  const fact = (key, value, display, asOfIso, source) => {
    const asOf = utc(asOfIso) ?? utc(cutoff);
    facts[key] = value == null || display == null
      ? { value: null, display: PENDING, asOf, source }
      : { value, display: String(display), asOf, source };
  };

  // Summary and coverage
  const s = p.summary ?? {};
  const latest = p.snapshot?.latestRoomReceiptIncludedAt ?? cutoff;
  fact("coverage.tickets", num(s.ticketsCovered), s.ticketsCovered, cutoff, "coverage snapshot");
  fact("coverage.deliverables", num(s.finalDeliverablesCovered), s.finalDeliverablesCovered, cutoff, "coverage snapshot");
  fact("coverage.deliverablesWord", num(s.finalDeliverablesCovered), word(s.finalDeliverablesCovered), cutoff, "coverage snapshot");
  const accepted = num(s.finalDeliverablesFullyAccepted), total = num(s.finalDeliverablesCovered);
  fact("status.acceptance", accepted,
    accepted == null || total == null ? null
      : accepted === 0 ? `None of the ${word(total)} deliverables is fully accepted.`
        : `${accepted} of ${total} deliverables fully accepted.`,
    latest, "progress record summary");
  const flag = (key, v, yes, no) => fact(key, typeof v === "boolean" ? v : null, typeof v === "boolean" ? (v ? yes : no) : null, latest, "progress record summary");
  flag("status.scientificBenefit", s.scientificBenefitEstablished, "established", "not established");
  flag("status.fullCompletion", s.fullProjectCompletionVerified, "verified", "not verified");
  flag("status.publicRuntime", s.publicProductionVerified, "verified", "not verified");

  // GB10 fixture preflight (structured fields)
  const g = p.gb10 ?? {};
  const gAt = g.completedAt ?? p.snapshot?.gb10CompletedAt ?? null;
  const auditAt = p.snapshot?.gb10AuditAt ?? asOfRefs(["gb10_audit"]);
  const GB = "GB10 attempt record", AUD = "GB10 artifact audit";
  fact("gb10.attempt", num(g.attempt), g.attempt, gAt, GB);
  fact("gb10.steps", num(g.optimizerSteps), g.optimizerSteps, gAt, GB);
  fact("gb10.trainRows", num(g.trainRowIdsConsumedOnce), g.trainRowIdsConsumedOnce, gAt, GB);
  fact("gb10.sourceCases", num(g.uniqueSourceCases), word(g.uniqueSourceCases), gAt, GB);
  fact("gb10.evalEntries", num(g.evaluationEntries), g.evaluationEntries, gAt, GB);
  fact("gb10.evalDistinct", num(g.uniqueEvaluationPromptContents), word(g.uniqueEvaluationPromptContents), gAt, GB);
  fact("gb10.httpResponses", num(g.httpResponses), g.httpResponses, gAt, GB);
  fact("gb10.tensors", num(g.checkpointTensors), g.checkpointTensors, gAt, GB);
  // The two evaluation paths are shown as one ratio only when they agree exactly; otherwise the ratio is pending.
  const a = g.nemoExactJson, h = g.httpExactJson;
  const agree = a && h && a.adapter === h.adapter && a.base === h.base && a.denominator === h.denominator && num(a.denominator) != null;
  fact("gb10.adapterExact", agree ? { exact: a.adapter, of: a.denominator } : null, agree ? `${a.adapter}/${a.denominator}` : null, gAt, GB);
  fact("gb10.baseExact", agree ? { exact: a.base, of: a.denominator } : null, agree ? `${a.base}/${a.denominator}` : null, gAt, GB);
  fact("gb10.teardown", typeof g.teardownRecorded === "boolean" ? g.teardownRecorded : null,
    typeof g.teardownRecorded === "boolean" ? (g.teardownRecorded ? "recorded" : "not recorded") : null, gAt, GB);
  const stage = num(g.stageChargedSeconds), prior = num(g.priorConservativeReservationSeconds), tot = num(g.totalChargedSeconds);
  fact("gb10.chargedSeconds", stage == null ? null : round(stage, 6), stage == null ? null : `${stage.toFixed(1)} s`, gAt, GB);
  fact("gb10.reservationSeconds", prior, prior == null ? null : `${prior} s`, gAt, GB);
  fact("gb10.totalSeconds", tot == null ? null : round(tot, 6), tot == null ? null : `${tot.toFixed(1)} s`, gAt, GB);
  fact("gb10.totalMinutes", tot == null ? null : round(tot / 60, 6), tot == null ? null : `${(tot / 60).toFixed(1)} min`, gAt, GB);
  const cap = /within the (\d+)-minute cap/.exec(pageCopy ?? "");
  fact("gb10.capMinutes", cap ? Number(cap[1]) : null, cap ? `${cap[1]}-minute` : null, gAt, "page copy (GB10 grant cap)");
  const gbMilestone = (p.milestones ?? []).find((m) => /GB10/.test(m.title ?? ""));
  const checks = firstMatch([gbMilestone?.summary, pageCopy], /(?:All (\d+) independent|passed (\d+) checks)/);
  const nChecks = checks ? Number(checks[1] ?? checks[2]) : null;
  fact("gb10.auditChecks", nChecks, nChecks, auditAt, AUD);

  // Mesh study and headroom: stated in milestone text only, so they are parsed; a changed sentence makes them pending.
  const meshM = (p.milestones ?? []).find((m) => /grid\d+\/grid\d+/.test(m.summary ?? ""));
  const meshT = meshM?.summary ?? "", meshAt = asOfItem(meshM), MESH = "mesh study review";
  const lay = /retained (\d+) \S+ layouts and (\d+) receipts/.exec(meshT);
  // "maximum gridA/gridF discrepancy is X C and gridB/gridF is Y C": two coarser meshes against the same finest one.
  const gaps = /(grid\d+)\/(grid\d+) discrepancy is ([\d.]+) C and (grid\d+)\/(grid\d+) is ([\d.]+) C/.exec(meshT);
  const sameFine = gaps && gaps[2] === gaps[5] ? gaps : null;
  const inv = /fixed ([\d.]+) C comparison tolerance there are (\d+) and (\d+) ranking inversions/.exec(meshT);
  fact("mesh.layouts", lay ? Number(lay[1]) : null, lay?.[1], meshAt, MESH);
  fact("mesh.receipts", lay ? Number(lay[2]) : null, lay?.[2], meshAt, MESH);
  fact("mesh.gridFine", sameFine?.[2] ?? null, sameFine?.[2], meshAt, MESH);
  fact("mesh.gridA", sameFine?.[1] ?? null, sameFine?.[1], meshAt, MESH);
  fact("mesh.gapA", sameFine ? Number(sameFine[3]) : null, sameFine ? `${sameFine[3]} °C` : null, meshAt, MESH);
  fact("mesh.gridB", sameFine?.[4] ?? null, sameFine?.[4], meshAt, MESH);
  fact("mesh.gapB", sameFine ? Number(sameFine[6]) : null, sameFine ? `${sameFine[6]} °C` : null, meshAt, MESH);
  fact("mesh.tolerance", inv ? Number(inv[1]) : null, inv ? `${inv[1]} °C` : null, meshAt, MESH);
  fact("mesh.inversionsA", inv ? Number(inv[2]) : null, inv?.[2], meshAt, MESH);
  fact("mesh.inversionsB", inv ? Number(inv[3]) : null, inv?.[3], meshAt, MESH);
  const headM = (p.milestones ?? []).find((m) => /headroom/i.test(m.title ?? ""));
  const verdict = /verdict (?:remains|is|was) ([A-Z][A-Z_]{3,})\b/.exec(headM?.summary ?? "");
  fact("headroom.verdict", verdict ? verdict[1] : null, verdict?.[1], asOfItem(headM), "headroom review");

  // Package view proposal state (D07 wording, corrected and dated in the packet)
  const d07 = (p.deliverables ?? []).find((d) => /Package view/.test(d.summary ?? ""));
  const pv = /Package view is proposed in open, unmerged PR ?(\d+)/.exec(d07?.summary ?? "");
  fact("packageView.pr", pv ? Number(pv[1]) : null, pv ? `#${pv[1]}` : null, asOfItem(d07), "deliverable ledger (dated correction)");
  fact("packageView.state", pv ? "in review" : null, pv ? "in review" : null, asOfItem(d07), "deliverable ledger (dated correction)");

  // Tickets
  const tickets = (p.tickets ?? []).map((t) => ({
    id: t.id, n: String(t.id).replace(/^SLAB-/, ""), status: t.status,
    optional: t.disposition === "optional_deferred", complete: t.wholeTicketCompletionVerified === true,
    deliverables: (p.deliverables ?? []).filter((d) => (d.tickets ?? []).includes(t.id)).map((d) => d.id),
    asOf: utc(asOfItem(t)),
  }));
  const tAt = newest((p.tickets ?? []).map(asOfItem));
  const count = (st) => tickets.filter((t) => t.status === st).length;
  fact("tickets.total", tickets.length || null, tickets.length || null, tAt, "ticket ledger");
  fact("tickets.open", tickets.length ? count("open") : null, tickets.length ? count("open") : null, tAt, "ticket ledger");
  fact("tickets.measured", tickets.length ? count("measured") : null, tickets.length ? count("measured") : null, tAt, "ticket ledger");
  fact("tickets.done", tickets.length ? count("done") : null, tickets.length ? count("done") : null, tAt, "ticket ledger");
  const complete = tickets.filter((t) => t.complete).length;
  fact("tickets.complete", tickets.length ? complete : null, tickets.length ? complete : null, tAt, "ticket ledger");
  fact("tickets.optional", tickets.length ? tickets.filter((t) => t.optional).length : null,
    tickets.length ? tickets.filter((t) => t.optional).length : null, tAt, "ticket ledger");
  // The build pipeline's tracker chips on the "how it works" slide: one ticket per stage.
  const STAGES = { labs: "SLAB-013", gate: "SLAB-008", repro: "SLAB-015", log: "SLAB-007", signer: "SLAB-040", view: "SLAB-025" };
  for (const [k, id] of Object.entries(STAGES)) {
    const t = (p.tickets ?? []).find((x) => x.id === id);
    fact(`stage.${k}`, t ? t.status : null, t ? `${t.id} · ${t.status}` : null, t ? asOfItem(t) : null, "ticket ledger");
  }

  const lists = {
    statusLegend: Object.fromEntries(Object.entries(p.statusLegend ?? {}).map(([k, v]) => [k, publicText(v, `statusLegend.${k}`)])),
    deliverables: (p.deliverables ?? []).map((d) => ({
      id: d.id, title: publicText(d.title, d.id), status: d.status, completionVerified: d.completionVerified === true,
      tickets: d.tickets ?? [], asOf: utc(asOfItem(d)),
    })),
    milestones: (p.milestones ?? []).map((m) => ({ id: m.id, title: publicText(m.title, m.id), status: m.status, asOf: utc(asOfItem(m)) })),
    priorities: (p.priorities ?? []).map((m) => ({ id: m.id, title: publicText(m.title, m.id), status: m.status, asOf: utc(asOfItem(m)) })),
    tickets,
  };

  const F = (k) => facts[k].display;
  const notes = [
    { slide: "problem", target: "30–35 s", text: [
      "Many AI agents now produce engineering findings.",
      "Most of those findings get lost in chats and logs.",
      "Nobody can check what actually ran.",
      "And when an input turns out wrong, nothing tells you what else it broke.",
      "SentiLab is a lab built around that problem.",
      "Every result is signed. A result is reproduced before it is accepted.",
      "And any result can be corrected later, with the damage traced.",
      "Our first domain is chiplet layout under thermal limits.",
    ] },
    { slide: "how", target: "30–35 s", text: [
      "Here is how it works.",
      "Several labs propose candidate layouts.",
      "A deterministic gate, with no model in the decision, accepts only results that were reproduced and verified.",
      "Every event goes into an append-only log. Each entry is hash-chained and signed.",
      "The Lab view shows only the verified prefix of that log.",
      "If an event is missing or forged, the view freezes right there. It shows less rather than something false.",
      `The small chips are tracker status. The gate ticket is ${facts["stage.gate"].value ?? "pending"}.`,
    ] },
    { slide: "correction", target: "30–35 s", text: [
      "This is a correction, end to end.",
      "A lab proposes a candidate. It is re-run in a fresh process. The gate accepts it.",
      "Then we withdraw a measurement on purpose. That is a seeded-fault drill.",
      "Everything that depended only on that measurement goes stale.",
      "The accepted candidate stands, because the independent reproduction still supports it.",
      `Left is the Lab view. Right is the Package view, which is ${F("packageView.state")} as pull request ${F("packageView.pr")}.`,
      "Both run on a test-key fixture with illustrative values.",
    ] },
    { slide: "measured", target: "30–35 s", text: [
      `On the GB10 we ran one fixture preflight: ${F("gb10.steps")} training steps, adapter saved, reloaded in a fresh container, and served.`,
      `Exact JSON went from ${F("gb10.baseExact")} for the base to ${F("gb10.adapterExact")} for the adapter, but on ${F("gb10.sourceCases")} source cases already seen in training.`,
      "So this is plumbing, not generalization.",
      `It used ${F("gb10.chargedSeconds")} of charged GB10 time.`,
      `Our headroom study is ${F("headroom.verdict")}.`,
      `The mesh study is a fixed sample of ${F("mesh.layouts")} layouts, not a universal error bound.`,
    ] },
    { slide: "status", target: "30–35 s", text: [
      `Where we stand. ${F("status.acceptance")}`,
      "The middle column shows what is done as a scoped slice, what is measured, and what is open.",
      "Next, we close the correctness queue and freeze the scientific protocol.",
      "Then model admission, the research harness, full CLI and MCP coverage, and reviewable evidence.",
      "Every number on these slides is generated from our dated progress record, and shows its time.",
      "Thank you.",
    ] },
    { slide: "rules", target: "backup", text: [
      "Backup: the evidence rules.",
      "The core is the only writer. Each event is a signed envelope chained to the previous one.",
      "The view projects only the verified prefix. At the first break it stops.",
      "LIVE needs verified progress, not just arrivals. Otherwise the label says STALE.",
      "Known limit: a server can withhold a suffix. Only a later full replay shows that.",
    ] },
    { slide: "coverage", target: "backup", text: [
      `Backup: ticket coverage. ${F("coverage.tickets")} tickets map to ${F("coverage.deliverables")} deliverables.`,
      `${F("tickets.open")} are open and ${F("tickets.measured")} have measured slices. ${F("tickets.complete")} are verified complete.`,
      "Measured means retained observations with a stated scope. It is not acceptance.",
    ] },
  ].map((n) => ({ ...n, text: publicText(n.text.join(" "), `notes.${n.slide}`) }));

  return {
    schema: "sentilab-deck-data/1",
    deck: DECK,
    pending: PENDING,
    source: {
      packetId,
      progressSchema: p.schemaVersion ?? null,
      progressSha256, pageCopySha256,
      progressGeneratedAt: utc(p.generatedAt),
      coverageThrough: utc(cutoff),
      latestUpdate: utc(latest),
      packagedAt: utc(p.packaging?.packagedAt),
      draft: p.draft === true,
      factsRefreshed: p.packaging?.factsRefreshed ?? null,
    },
    facts, lists, notes,
  };
}

// ── CLI ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
export function newestPacketId() {
  const ids = readdirSync(PACKETS).filter((d) => /^progress-\d{4}-\d{2}-\d{2}$/.test(d) && existsSync(join(PACKETS, d, "progress.json"))).sort();
  if (!ids.length) throw new Error("no progress-YYYY-MM-DD packet with progress.json under docs/sentilab");
  return ids.at(-1);
}
export function buildFromPacket(packetId = newestPacketId()) {
  const dir = join(PACKETS, packetId);
  const progressBytes = readFileSync(join(dir, "progress.json"));
  const pageCopyBytes = existsSync(join(dir, "PAGE-COPY.md")) ? readFileSync(join(dir, "PAGE-COPY.md")) : null;
  const sha = (b) => (b ? createHash("sha256").update(b).digest("hex") : null);
  return buildDeckData({
    progress: JSON.parse(progressBytes.toString("utf8")), pageCopy: pageCopyBytes?.toString("utf8") ?? "",
    packetId, progressSha256: sha(progressBytes), pageCopySha256: sha(pageCopyBytes),
  });
}
export const serialize = (data) => {
  const json = JSON.stringify(data, null, 2) + "\n";
  return { json, js: `// Generated by build-deck-data. Same object as deck-data.json, for file:// viewing.\nwindow.DECK_DATA = ${json.trimEnd()};\n` };
};

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  const at = args.indexOf("--packet");
  const packetId = at >= 0 ? args[at + 1] : newestPacketId();
  const { json, js } = serialize(buildFromPacket(packetId));
  const jsonPath = join(OUT_DIR, "deck-data.json"), jsPath = join(OUT_DIR, "deck-data.js");
  if (args.includes("--check")) {
    const same = (p, s) => existsSync(p) && readFileSync(p, "utf8") === s;
    if (!same(jsonPath, json) || !same(jsPath, js)) { console.error(`deck-data is stale for ${packetId}: run node scripts/build-deck-data.mjs`); process.exit(1); }
    console.log(`deck-data matches ${packetId}`);
  } else {
    writeFileSync(jsonPath, json);
    writeFileSync(jsPath, js);
    const data = JSON.parse(json);
    const pending = Object.entries(data.facts).filter(([, f]) => f.value == null).map(([k]) => k);
    console.log(`wrote deck-data.json + deck-data.js from ${packetId} (${Object.keys(data.facts).length} facts${pending.length ? `; pending: ${pending.join(", ")}` : ""})`);
  }
}
