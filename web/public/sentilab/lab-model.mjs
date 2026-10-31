// Lab view display model (VIEW ENVELOPE v0.5). Pure functions, no DOM, so the node tests can run them.
// Status (lifecycle, validity, support sets, the board) is never computed here: it is the contract's project() over the
// projectable prefix only (rule 1): the leading run of verified envelopes from seq 1, ending before the first
// rejected, unverified or conflicting row. This file only arranges that output, plus the display-only `values` from
// those same envelopes, for the panels. Everything after the prefix appears only as marked feed rows, never in a
// panel. A row that failed the input checks has no envelope here at all: only its readable seq, event_id and hash.
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
  ["seq_conflict", "two different envelopes share this seq"],
  ["event_id_conflict", "two different envelopes share this event_id"],
  // Input checks: the row was rejected before anything was hashed.
  ["line_too_large", "line over 64 KiB, never parsed"],
  ["not_json", "not JSON"],
  ["invalid_utf8", "not valid UTF-8"],
  ["too_deep", "nested deeper than 8 levels"],
  ["lone_surrogate", "broken Unicode (lone surrogate)"],
  ["string_too_long", "string over 512 characters"],
  ["non_finite_number", "number that is not finite"],
  ["too_large", "over 64 KiB in canonical form"],
  ["invalid_value", "not a JSON value"],
  ["prev_hash_mismatch", "prev_hash break"],
  ["seq_gap", "seq gap"],
  ["run_mismatch", "envelope from another run"],
  ["bad_version", "unknown envelope version"],
  ["key_hash_mismatch", "served key does not match the pin"],
  ["key_unavailable", "pinned key not served"],
  ["key_not_pinned", "no pinned key"],
  ["ed25519_unsupported", "this browser cannot check Ed25519"],
];
const REASON_TEXT = new Map(REASONS);
const REASON_RANK = new Map(REASONS.map(([code], i) => [code, i]));
// too_many_entries:<field> and schema:<path> carry their field in the code.
const rankOf = (code) => REASON_RANK.get(code) ?? (String(code).startsWith("too_many_entries:") ? REASON_RANK.get("too_large") : String(code).startsWith("schema:") ? REASON_RANK.get("invalid_value") : 99);
export const reasonText = (code) => {
  const c = String(code);
  if (REASON_TEXT.has(c)) return REASON_TEXT.get(c);
  if (c.startsWith("too_many_entries:")) return `over 64 entries in ${c.slice("too_many_entries:".length)}`;
  if (c.startsWith("schema:")) return `schema: ${c.slice("schema:".length)}`;
  return c;
};
export const rankReasons = (codes) => [...codes].sort((a, b) => rankOf(a) - rankOf(b));
// Per-envelope problems get "at seq N"; a key problem usually affects every row, so it is named once.
const KEY_REASONS = new Set(["key_not_pinned", "key_unavailable", "key_hash_mismatch", "ed25519_unsupported", "bad_version"]);
// A row that failed the input checks (steps 1 to 4): never canonicalized, hashed or verified.
export const isRejected = (row) => row.status === "oversize" || row.status === "malformed";

export const isObj = (x) => x !== null && typeof x === "object" && !Array.isArray(x);
// A node id for display: a leading run-id segment (16 or more hex digits, then ":") is dropped, so
// "35975774fb714bbdaa51972bc39518ec:candidate-0" shows as "candidate-0" and
// "...:candidate-0:evaluate:measurement" as "candidate-0:evaluate:measurement" (still distinct from its siblings).
// Ids without that prefix are unchanged. The full id stays in the tooltip and the inspector.
export const shortId = (id) => (typeof id === "string" ? id.replace(/^[0-9a-f]{16,}:(?=.)/, "") : id);
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
  const reasons = [...byCode.values()].sort((a, b) => rankOf(a.code) - rankOf(b.code));
  const rejected = rows.filter(isRejected).length;
  const phrases = reasons.slice(0, 3).map((r) => (KEY_REASONS.has(r.code) || r.firstSeq == null
    ? reasonText(r.code) : `${reasonText(r.code)} at seq ${r.firstSeq}${r.count > 1 ? ` (+${r.count - 1})` : ""}`));
  return { total, verified, ok: total > 0 && verified === total, reasons, rejected, phrases };
}

// A seeded drill is declared by the core in the withdrawal itself: a withdraw whose reason starts "drill".
// Over-labeling a drill is the safe error, so any envelope that passed the input checks counts, verified or not.
// Rejected rows are null here and never read.
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

// J's unit, for display. Newer producer rows spell Celsius "C", older signed rows "°C": both show as °C. Display
// only, after verification: the signed bytes are checked exactly as they arrived and the inspector shows them raw.
export const tempUnit = (unit) => (unit === "C" ? "°C" : unit);

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
    if (!unit && isObj(env.values.J) && typeof env.values.J.unit === "string") unit = tempUnit(env.values.J.unit);
  }
  if (lo === Infinity) return null;
  let min = Math.floor(lo / 5) * 5, max = Math.ceil(hi / 5) * 5;
  if (max - min < 10) { const mid = (min + max) / 2; min = Math.floor((mid - 5) / 5) * 5; max = min + 10; }
  return { min, max, unit: unit ?? "" };
}

// A live run's colour scale after a verification. While the verified prefix holds or grows, the scale only widens,
// so colours already on screen never shift. When the prefix shrinks (a late conflict or break cut it back), the scale
// is rebuilt from the prefix that remains, so no colour carries a value from the discarded suffix.
export function nextScale(previous, previousK, scale, K) {
  if (!previous || !scale || K < previousK) return scale;
  return { min: Math.min(previous.min, scale.min), max: Math.max(previous.max, scale.max), unit: previous.unit || scale.unit };
}

// The chip colour for a centre temperature on a scale: a six-stop ramp, and a dark or light label to match.
const HEAT = [[0x11, 0x2a, 0x48], [0x23, 0x6b, 0x91], [0x56, 0xb6, 0xba], [0xdf, 0xd3, 0x76], [0xec, 0x99, 0x4f], [0xe4, 0x51, 0x38]];
export function heat(v, scale) {
  const t = Math.max(0, Math.min(1, (v - scale.min) / ((scale.max - scale.min) || 1))) * (HEAT.length - 1);
  const i = Math.min(HEAT.length - 2, Math.floor(t)), f = t - i, a = HEAT[i], b = HEAT[i + 1];
  const c = [0, 1, 2].map((k) => Math.round(a[k] + (b[k] - a[k]) * f));
  const lum = (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255;
  return { fill: `rgb(${c[0]},${c[1]},${c[2]})`, ink: lum > 0.5 ? "#0b1418" : "#f4f7f6" };
}

// A row's stable identity across re-verifications: its event_id and stored hash (a conflict shares an event_id or a
// seq, never both with the same hash), plus its position in the input, which is stable because a live stream only
// grows and a file doesn't change. Row indexes are not stable: a late row at an old seq is sorted in before them.
export function rowIdentity(verification, i) {
  return { event_id: verification.rows[i].event_id, hash: verification.meta[i].hash, index: verification.meta[i].index };
}
// The row index of an identity in a (newer) verification, or -1 if it no longer resolves. A row with a readable
// event_id and hash is found by those; one without (an unreadable rejected line) by its input position.
export function resolveRow(verification, id) {
  if (id.event_id !== null && id.hash !== null) {
    return verification.rows.findIndex((row, i) => row.event_id === id.event_id && verification.meta[i].hash === id.hash);
  }
  return verification.rows.findIndex((row, i) => verification.meta[i].index === id.index && row.event_id === id.event_id && verification.meta[i].hash === id.hash);
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

// The view at a cursor: the first `cursor` rows in seq order.
// verification: { ordered, rows, prefix } from verifyChecked (rows[i] belongs to ordered[i], which is null for a
// rejected row; prefix is how many rows, from the first, form the projectable prefix, and all of them have an envelope).
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
    // J and W: a measurement's own; a candidate's from metricFor() (which needs no temperatures).
    const metric = own ?? metricFor(id);
    const J = isObj(metric?.values?.J) && finite(metric.values.J.value) ? { value: metric.values.J.value, unit: tempUnit(str(metric.values.J.unit) ?? "") } : null;
    const W = isObj(metric?.values?.W) && finite(metric.values.W.value) ? { value: metric.values.W.value, metric_id: str(metric.values.W.metric_id) ?? "" } : null;
    return {
      id, kind: node.kind, lab: made?.lab ?? null, labName: lab.name, color: lab.color, lifecycle: node.lifecycle,
      validity: node.validity, geometry: geometry.rects, skipped: geometry.skipped, source, J, W,
      metric: metric ? { id: metric.id, validity: metric.validity, set_id: metric.set_id ?? null } : null,
      scenario: str(made?.values?.scenario_id) ?? str(source?.values?.scenario_id),
      units: str(made?.values?.units), seq: made?.seq ?? null,
      firstSet: (sets.get(id) ?? [])[0]?.set_id ?? null,
    };
  };

  // The measurement that gives a candidate its J and W (display values; a producer puts them on measurements): a
  // member of one of its support sets that carries a finite J, chosen as project() marks them: a set it calls valid
  // first, then a measurement it calls valid, then one it marks reproduced (a verify tier, e.g. "replayed"); the
  // set order breaks ties. None: J and W stay empty.
  const metricFor = (id) => {
    const status = nodes[id]?.support_status ?? {};
    const found = [];
    for (const set of sets.get(id) ?? []) {
      for (const m of set.members) {
        const values = created.get(m)?.values;
        if (!isObj(values) || !isObj(values.J) || !finite(values.J.value)) continue;
        const node = nodes[m];
        found.push({ id: m, set_id: set.set_id, validity: node?.validity ?? "unverified", values,
          rank: (status[set.set_id] === "valid" ? 4 : 0) + (node?.validity === "valid" ? 2 : 0) + ((node?.tiers ?? []).length > 0 ? 1 : 0) });
      }
    }
    return found.reduce((best, m) => (best === null || m.rank > best.rank ? m : best), null);
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

// Panel 04: the feed. Every row, verified or not, in seq order, up to the cursor. `projected` is false for
// everything after the prefix, including envelopes that verify on their own. A rejected row shows only its reasons:
// its content failed the input checks, so it is never rendered.
export function feedRows(verification, cursor, rejected = new Map()) {
  const { ordered, rows, prefix } = verification;
  const n = Math.max(0, Math.min(cursor, rows.length));
  const out = [];
  for (let i = 0; i < n; i += 1) {
    const env = ordered[i], row = rows[i];
    const base = { i, seq: row.seq, status: row.status, reasons: row.reasons, projected: i < prefix };
    if (isRejected(row) || !isObj(env)) {
      out.push({ ...base, kind: row.status, text: `rejected before hashing: ${row.reasons.map(reasonText).join(", ")}` });
      continue;
    }
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
      const J = values && isObj(values.J) && finite(values.J.value) ? ` · J ${fmt1(values.J.value)} ${tempUnit(s(values.J.unit))}` : "";
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
