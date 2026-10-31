// Lab view display model (VIEW ENVELOPE v0.4). Pure functions, no DOM, so the node tests can run them.
// Status (lifecycle, validity, support sets, the board) is never computed here: it is aneta's project() over the
// projectable prefix only (rule 1): the unbroken run of verified, non-oversize envelopes from seq 1. This file
// only arranges that output, plus the display-only `values` from those same envelopes, for the panels.
// Everything after the prefix appears only as marked feed rows, never in a panel.
import { project } from "./evidence-projection.mjs";

export const LABS = Object.freeze({
  "lab-a": { name: "Lab A", color: "#8aa9dd" },
  "lab-b": { name: "Lab B", color: "#88d9d0" },
  "lab-c": { name: "Lab C", color: "#a5d5aa" },
  "lab-d": { name: "Lab D", color: "#e6a36a" },
  "baseline-sa": { name: "Baseline (SA)", color: "#c9b2e8" },
  gate: { name: "AcceptanceGate", color: "#e7c48f" },
  core: { name: "Core", color: "#a9bcc2" },
});
export const labInfo = (lab) => (typeof lab === "string" && Object.hasOwn(LABS, lab) ? LABS[lab] : { name: "Other", color: "#a9bcc2" });

// Plain words for the reason codes, most serious first. The code itself is shown in the inspector.
export const REASONS = [
  ["hash_mismatch", "content does not match its hash"],
  ["bad_sig", "bad signature"],
  ["prev_hash_mismatch", "prev_hash break"],
  ["seq_gap", "seq gap"],
  ["seq_repeat", "seq repeat"],
  ["run_mismatch", "envelope from another run"],
  ["malformed", "malformed envelope"],
  ["bad_version", "unknown envelope version"],
  ["bad_alg", "unknown signature algorithm"],
  ["key_hash_mismatch", "served key does not match the pin"],
  ["key_unavailable", "pinned key not served"],
  ["key_not_pinned", "no pinned key"],
  ["ed25519_unsupported", "this browser cannot check Ed25519"],
];
const REASON_TEXT = new Map(REASONS);
const REASON_RANK = new Map(REASONS.map(([code], i) => [code, i]));
export const reasonText = (code) => REASON_TEXT.get(code) ?? String(code);
// Per-envelope problems get "at seq N"; a key problem usually affects every row, so it is named once.
const KEY_REASONS = new Set(["key_not_pinned", "key_unavailable", "key_hash_mismatch", "ed25519_unsupported", "bad_alg", "bad_version"]);

export const isObj = (x) => x !== null && typeof x === "object" && !Array.isArray(x);
const finite = (x) => typeof x === "number" && Number.isFinite(x);
const str = (x) => (typeof x === "string" ? x : null);

// The chain badge: how many rows verified, and the reasons for the rest, most serious first.
export function chainSummary(rows) {
  const total = rows.length;
  const verified = rows.filter((r) => r.status === "verified").length;
  const byCode = new Map();
  for (const row of rows) {
    for (const code of row.reasons) {
      if (!byCode.has(code)) byCode.set(code, { code, count: 0, firstSeq: row.seq });
      byCode.get(code).count += 1;
    }
  }
  const reasons = [...byCode.values()].sort((a, b) => (REASON_RANK.get(a.code) ?? 99) - (REASON_RANK.get(b.code) ?? 99));
  const oversize = rows.filter((r) => r.oversize.length > 0).length;
  const phrases = reasons.slice(0, 3).map((r) => (KEY_REASONS.has(r.code) || r.firstSeq == null
    ? reasonText(r.code) : `${reasonText(r.code)} at seq ${r.firstSeq}${r.count > 1 ? ` (+${r.count - 1})` : ""}`));
  return { total, verified, ok: total > 0 && verified === total, reasons, oversize, phrases };
}

// A seeded drill is declared by the core in the withdrawal itself: a withdraw whose reason starts "drill".
// Over-labeling a drill is the safe error, so any well-formed envelope counts, verified or not.
export function isDrill(envelopes) {
  return envelopes.some((env) => isObj(env) && isObj(env.event) && env.event.type === "withdraw" &&
    isObj(env.event.body) && typeof env.event.body.reason === "string" && /^\s*drill\b/i.test(env.event.body.reason));
}

// Geometry entries that can be drawn. Anything else is counted and skipped, never guessed at.
export function cleanGeometry(geometry) {
  if (!Array.isArray(geometry)) return { rects: [], skipped: 0 };
  const rects = [];
  let skipped = 0;
  for (const g of geometry) {
    if (isObj(g) && typeof g.id === "string" && [g.xLL, g.yLL, g.w, g.h].every(finite) && g.w > 0 && g.h > 0) {
      rects.push({ id: g.id, x: g.xLL, y: g.yLL, w: g.w, h: g.h, layer: finite(g.layer) ? g.layer : 0 });
    } else skipped += 1;
  }
  return { rects, skipped };
}

const tempsOf = (values) => {
  if (!isObj(values) || !isObj(values.center_temps)) return null;
  const out = {};
  for (const [k, v] of Object.entries(values.center_temps)) if (finite(v)) out[k] = v;
  return out;
};

// One color scale per run, declared up front: every center temperature in the run's authenticated envelopes,
// rounded out to 5 degrees, at least 10 degrees wide. Replay sees the whole run, so it never changes during play.
export function colorScale(trusted) {
  let lo = Infinity, hi = -Infinity, unit = null;
  for (const env of trusted) {
    const temps = tempsOf(env.values);
    if (!temps) continue;
    for (const v of Object.values(temps)) { if (v < lo) lo = v; if (v > hi) hi = v; }
    if (!unit && isObj(env.values.J) && typeof env.values.J.unit === "string") unit = env.values.J.unit;
  }
  if (lo === Infinity) return null;
  let min = Math.floor(lo / 5) * 5, max = Math.ceil(hi / 5) * 5;
  if (max - min < 10) { const mid = (min + max) / 2; min = Math.floor((mid - 5) / 5) * 5; max = min + 10; }
  return { min, max, unit: unit ?? "" };
}

// One package frame per run, so every card is drawn at the same scale: the union of all geometry, from 0.
export function frameOf(trusted) {
  let x1 = 0, y1 = 0, x0 = 0, y0 = 0, any = false;
  for (const env of trusted) {
    for (const r of cleanGeometry(env.values?.geometry).rects) {
      any = true;
      x0 = Math.min(x0, r.x); y0 = Math.min(y0, r.y);
      x1 = Math.max(x1, r.x + r.w); y1 = Math.max(y1, r.y + r.h);
    }
  }
  return any ? { x0: Math.floor(x0), y0: Math.floor(y0), x1: Math.ceil(x1) + 1, y1: Math.ceil(y1) + 1 } : null;
}

// Where the board's lifecycle states sit on the contract's state machine (display only: a position for the
// track, read from the lifecycle project() returned). Terminal states that end early are "out".
const STAGE = {
  proposed: [0, "open"], validated: [1, "open"], simulation_pending: [2, "open"], evaluated: [3, "open"],
  reproduction_pending: [4, "open"], reproduced: [5, "open"],
  accepted: [6, "won"], non_improving_current: [6, "lost"], within_margin: [6, "lost"],
  rejected_schema: [0, "out"], rejected_constraints: [1, "out"], failed_run: [2, "out"],
  non_improving: [3, "lost"], tie: [3, "lost"], inconclusive: [3, "lost"], reproduction_failed: [4, "out"],
  cancelled: [null, "out"],
};
export const STAGES = ["proposed", "validated", "simulated", "evaluated", "reproducing", "reproduced", "board"];
export const stageOf = (lifecycle) => STAGE[lifecycle] ?? [null, "open"];

// The view at a cursor: the first `cursor` envelopes in seq order.
// verification: { ordered, rows, prefix } from verifyChain (rows[i] belongs to ordered[i]; prefix is how many
// envelopes, from the first, form the projectable prefix).
export function buildView(verification, cursor) {
  const { ordered, prefix } = verification;
  const n = Math.max(0, Math.min(cursor, ordered.length));

  // Rule 1: project() over the projectable prefix only, as far as the cursor has reached.
  const trusted = ordered.slice(0, Math.min(n, prefix));
  const frozenAt = trusted.length ? trusted[trusted.length - 1].event.seq : 0;
  // Something after the prefix is on screen: the board is frozen at the last seq of the prefix.
  const broken = n > prefix ? { afterSeq: frozenAt } : null;
  let projection = null, projectionError = null;
  try { projection = project(trusted.map((env) => env.event)); } catch (error) { projectionError = String(error?.message ?? error); }
  const rejected = new Map((projection?.rejected ?? []).map((r) => [r.event_id, r.code]));
  const applied = trusted.filter((env) => !rejected.has(env.event.event_id));

  // Display links, read from applied events only: who created each node, its values, and its support sets.
  const created = new Map(), sets = new Map(), accepts = new Map(), withdrawals = new Map();
  for (const env of applied) {
    const { type, body } = env.event;
    if (!isObj(body)) continue;
    if (type === "node.create" && typeof body.id === "string" && !created.has(body.id)) {
      created.set(body.id, { env, seq: env.event.seq, lab: str(env.actor?.lab), values: isObj(env.values) ? env.values : null });
    } else if (type === "support.add" && typeof body.node === "string" && Array.isArray(body.members)) {
      if (!sets.has(body.node)) sets.set(body.node, []);
      sets.get(body.node).push({ set_id: String(body.set_id), members: body.members.filter((m) => typeof m === "string") });
    } else if (type === "lifecycle.transition" && body.to === "accepted" && typeof body.node === "string") {
      accepts.set(body.node, env.event.seq);
    } else if (type === "withdraw" && typeof body.node === "string") {
      withdrawals.set(body.node, { seq: env.event.seq, reason: str(body.reason) ?? "" });
    }
  }
  const nodes = projection?.nodes ?? {};
  const byCreation = Object.keys(nodes).sort((a, b) => (created.get(a)?.seq ?? 0) - (created.get(b)?.seq ?? 0));

  // The measurement whose temperatures a card shows: the first member with temperatures in the first support set
  // project() calls valid; with no valid set, the first one found, marked by its own validity.
  const measurementFor = (id) => {
    const status = nodes[id]?.support_status ?? {};
    const list = sets.get(id) ?? [];
    const pick = (onlyValid) => {
      for (const set of list) {
        if (onlyValid && status[set.set_id] !== "valid") continue;
        for (const m of set.members) {
          const temps = tempsOf(created.get(m)?.values);
          if (temps) return { id: m, set_id: set.set_id, setStatus: status[set.set_id] ?? "broken", validity: nodes[m]?.validity ?? "unverified", values: created.get(m).values, temps };
        }
      }
      return null;
    };
    return pick(true) ?? pick(false);
  };

  const card = (id) => {
    const node = nodes[id];
    const made = created.get(id);
    const lab = labInfo(made?.lab);
    const geometry = cleanGeometry(made?.values?.geometry);
    const own = node.kind === "measurement" ? { id, set_id: null, setStatus: null, validity: node.validity, values: made?.values, temps: tempsOf(made?.values) } : null;
    const source = own ?? measurementFor(id);
    const J = isObj(source?.values?.J) && finite(source.values.J.value) ? { value: source.values.J.value, unit: str(source.values.J.unit) ?? "" } : null;
    const W = isObj(source?.values?.W) && finite(source.values.W.value) ? { value: source.values.W.value, metric_id: str(source.values.W.metric_id) ?? "" } : null;
    return {
      id, kind: node.kind, lab: made?.lab ?? null, labName: lab.name, color: lab.color, lifecycle: node.lifecycle,
      validity: node.validity, geometry: geometry.rects, skipped: geometry.skipped, source, J, W,
      scenario: str(made?.values?.scenario_id) ?? str(source?.values?.scenario_id),
      units: str(made?.values?.units), seq: made?.seq ?? null,
      firstSet: (sets.get(id) ?? [])[0]?.set_id ?? null,
    };
  };

  // Panel 01: every candidate, plus any measurement that carries its own layout (such as an initial layout).
  const cards = byCreation
    .filter((id) => nodes[id].kind === "candidate" || (nodes[id].kind === "measurement" && cleanGeometry(created.get(id)?.values?.geometry).rects.length > 0))
    .map(card);

  // Panel 02: the board. The current accepted best is the accepted candidate accepted last (by seq).
  const candidates = cards.filter((c) => c.kind === "candidate");
  const accepted = candidates.filter((c) => c.lifecycle === "accepted" && accepts.has(c.id))
    .sort((a, b) => accepts.get(b.id) - accepts.get(a.id));
  const board = { current: accepted[0] ? { ...accepted[0], acceptedSeq: accepts.get(accepted[0].id) } : null, candidates };

  // Panel 03: evidence, straight from project(): validity, stale_because, support sets, tiers.
  const evidence = byCreation.map((id) => ({
    id, kind: nodes[id].kind, lab: labInfo(created.get(id)?.lab).name, validity: nodes[id].validity,
    stale_because: nodes[id].stale_because, support_status: nodes[id].support_status, tiers: nodes[id].tiers,
    tainted_by: nodes[id].tainted_by, review_required: nodes[id].review_required,
    withdrawal: withdrawals.get(id) ?? null,
  }));
  const withdrawn = evidence.filter((e) => e.validity === "withdrawn");
  const drill = withdrawn.length === 0 ? null : {
    withdrawn,
    stale: evidence.filter((e) => e.validity === "stale"),
    survived: evidence.filter((e) => e.validity === "valid" && Object.values(e.support_status).includes("broken") && Object.values(e.support_status).includes("valid")),
  };

  return { n, trustedCount: trusted.length, frozenAt, broken, projection, projectionError, rejected, cards, board, evidence, drill };
}

// Panel 04: the feed. Every envelope, verified or not, in seq order, up to the cursor. `projected` is false for
// everything after the prefix, including envelopes that verify on their own.
export function feedRows(verification, cursor, rejected = new Map()) {
  const { ordered, rows, prefix } = verification;
  const n = Math.max(0, Math.min(cursor, ordered.length));
  const out = [];
  for (let i = 0; i < n; i += 1) {
    const env = ordered[i], row = rows[i];
    const base = { i, seq: row.seq, status: row.status, reasons: row.reasons, oversize: row.oversize, projected: i < prefix };
    if (row.reasons.includes("malformed") || !isObj(env?.event)) { out.push({ ...base, kind: "malformed", text: "malformed envelope: not shown" }); continue; }
    if (row.oversize.length > 0) { out.push({ ...base, kind: "oversize", text: `over the size cap (${row.oversize.join(", ")}): not rendered` }); continue; }
    const { type, body } = env.event;
    out.push({
      ...base, kind: "event", ts: str(env.ts), lab: str(env.actor?.lab), type: str(type) ?? "?",
      text: outcomeText(type, isObj(body) ? body : {}, isObj(env.values) ? env.values : null),
      rejected: i < prefix ? rejected.get(env.event.event_id) ?? null : null,
    });
  }
  return out;
}

const fmt1 = (v) => (Math.round(v * 10) / 10).toFixed(1);
export function outcomeText(type, body, values) {
  const s = (x) => (typeof x === "string" ? x : Array.isArray(x) ? x.filter((m) => typeof m === "string").join(", ") : "?");
  switch (type) {
    case "node.create": {
      const J = values && isObj(values.J) && finite(values.J.value) ? ` · J ${fmt1(values.J.value)} ${s(values.J.unit)}` : "";
      return `${s(body.kind)} ${s(body.id)}${J}`;
    }
    case "lifecycle.transition": return `${s(body.node)} → ${s(body.to)}`;
    case "support.add": return `${s(body.node)} ⇐ ${s(body.set_id)}: ${s(body.members)}`;
    case "verify.add": return `${s(body.node)} tier ${s(body.tier)} ← ${s(body.evidence)}`;
    case "withdraw": return `withdraw ${s(body.node)} · ${s(body.reason)}`;
    case "withdraw.retract": return `retract withdrawal of ${s(body.node)}`;
    case "link.add": return `${s(body.from)} ${s(body.rel)} ${s(body.to)}`;
    case "review.resolve": return `${s(body.node)} review: ${s(body.decision)}`;
    default: return s(type);
  }
}
