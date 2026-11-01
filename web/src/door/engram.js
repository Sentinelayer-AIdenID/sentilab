// The ENGRAM view an agent reads, sentilab-agent-view/1 (AGENT-DOOR section 2, with Amendments 1 and 2): the case, the
// rules, the one board metric, the reference statistics, the published points, the skills as exact URLs on the
// request's own host, the compact layout format, and the live board. Built from fixed values, root's saved gate-zero
// record (/agents/evidence.json, read through the asset layer, never copied here) and the scorer intake's board.
// A module of its own because worker.js may export nothing but its default handler.
import { BOARD_METRIC, BODY_GAP_UM, CASE_ID, CONNECTIONS, DIES, EDGE_CLEARANCE_UM, FRAME_UM, LATTICE_UM, PUBLISHED,
  SCORER, SNAPPED_REFERENCE, WIRE_PROXY } from "./case.js";
import { PREVIEW_LABEL } from "./layout.js";
import { SCOPES } from "./render.js";
import { TOKEN_WORDING } from "./token.js";

export const VIEW_SCHEMA = "sentilab-agent-view/1";
export const CPU_SECONDS_PER_TOKEN = 30;
const ORDER = DIES.map((die) => die.id);

const SUBMISSION_RULE = "Submissions open only while the scorer intake reports a verified manifest signature and an open admission window. Reading always works.";

// The gate-zero fields of root's evidence record for the raw CPU-DRAM layout, or null when the record is unreadable.
export function gateZeroFrom(evidence) {
  const gate = evidence?.gate_zero;
  const row = (gate?.results ?? []).find((r) => r?.problem === "micro150" && r?.layout === "micro150-tap25d-fig5a/raw");
  const number = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);
  if (!row || typeof gate.status !== "string") return null;
  return { status: gate.status, native: number(row.native_block_max_C), centreMean: number(row.chiplet_centre_average_max_C),
    active: number(row.active_layer_grid_peak_C), precisionK: number(gate.raw_output_precision_K) };
}

export function agentView({ origin, token, claims, submissions, terms, gateZero, board, boardStatus, cpuSecondsLeft }) {
  const evidenceUrl = `${origin}/agents/evidence.json`;
  return {
    schema: VIEW_SCHEMA,
    purpose: claims.purpose,
    label: SCORER.label,
    token: { t: token, kind: TOKEN_WORDING, scope: SCOPES[claims.purpose], expires_at: claims.expires_at, short_id: claims.short_id,
      budget: `${CPU_SECONDS_PER_TOKEN} CPU-seconds per token, kept by the scorer intake`, cpu_s_left: cpuSecondsLeft ?? null },
    submissions: { state: submissions, rule: SUBMISSION_RULE, terms: terms ?? null,
      terms_note: terms ? "Submitting through the door accepts these terms of the signed manifest." : "No terms are published yet, so nothing can be submitted." },
    objective: "Place 4 CPUs and 4 DRAMs on the 45 mm interposer so the board metric goes down without lengthening the wire proxy. Compare like with like: scoring.board_metric for temperature and scoring.wire_proxy for wire. The published points under references are routed wire, a different scale.",
    case: {
      id: CASE_ID, name: "CPU-DRAM (TAP-2.5D Fig. 5a)", units: "um", anchor: "die centre",
      origin: "the interposer's lower-left corner; +x right, +y up",
      interposer: { w: FRAME_UM, h: FRAME_UM },
      dies: DIES.map((d) => ({ id: d.id, index: d.index, unit: d.unit, kind: d.kind, w: d.w, h: d.h, power_w: d.power_w, halo: d.halo, rot_deg: [...d.rot_deg] })),
      dimensions: "w along x and h along y at 0 degrees; 90 degrees swaps them",
      connectivity: { order: ORDER, wires: CONNECTIONS.map((row) => [...row]), note: "symmetric; each unordered pair once; 5,120 wires" },
      stack_ref: "public reference case af66bcfc",
      model: `${origin}/agents/challenge.json`,
    },
    rules: {
      lattice: LATTICE_UM, body_gap: BODY_GAP_UM, edge_clearance_incl_halo: EDGE_CLEARANCE_UM,
      rot_deg: { CPU: [0, 90], DRAM: [0] },
      edge: "each die body grown by its halo stays at least edge_clearance_incl_halo inside every interposer edge (TAP's edge strips)",
      halos: "halo rings (body grown by its halo) never overlap; touching is allowed",
      gap: "die bodies are at least body_gap apart along x or along y",
      check: PREVIEW_LABEL,
    },
    scoring: {
      label: SCORER.label, engine: SCORER.engine, grid: SCORER.grid, readout: SCORER.readout, binary_sha256: SCORER.binary_sha256,
      source_merge: SCORER.source_merge,
      gate_zero: { status: gateZero?.status ?? null, evidence: evidenceUrl },
      board_metric: { metric_id: BOARD_METRIC.metric_id, definition: BOARD_METRIC.definition, unit: BOARD_METRIC.unit,
        precision_K: gateZero?.precisionK ?? null, rounding: BOARD_METRIC.rounding,
        reference_binding: { layout: "raw", value_C: gateZero?.centreMean ?? null },
        snapped_reference_value_C: null },
      reference_statistics: { label: "Other statistics of the raw reference layout, same scorer and record. Never the board metric.",
        layout: "raw", native_all_block_max_C: gateZero?.native ?? null, active_layer_peak_C: gateZero?.active ?? null,
        active_guard: gateZero?.active == null ? null : `strictly < ${gateZero.active}`, source: evidenceUrl },
      wire_proxy: { definition: WIRE_PROXY.definition, unit: WIRE_PROXY.unit,
        references: WIRE_PROXY.references.map((r) => ({ ...r })), rule: WIRE_PROXY.rule },
      states: ["rejected", "queued", "evaluating", "evaluated", "replaying", "reproduced", "not_reproduced"],
      claims: "A result is a candidate until a fresh-process replay reproduces it. A beat verdict also needs routed wire and the fixed predicates.",
    },
    references: { label: PUBLISHED.label, source: PUBLISHED.source, temperature_statistic: PUBLISHED.temperature_statistic,
      points: PUBLISHED.points.map((p) => ({ ...p })) },
    skills: [
      { name: "check", method: "GET", url: `${origin}/agents/check?t=${token}&l={layout}`, template: `${origin}/agents/check?t={t}&l={layout}`,
        does: `${PREVIEW_LABEL}. Answers at once and never starts a solve.` },
      { name: "submit", method: "POST", url: `${origin}/agents/submit`, content_type: "application/json", body: { t: "{t}", layout: "{layout}" },
        does: "Queues one layout for the scorer and spends CPU-seconds from this token. An identical retry returns the same run." },
      { name: "tap_link", method: "GET", url: `${origin}/s?t=${token}&l={layout}`, template: `${origin}/s?t={t}&l={layout}`,
        does: "If you cannot POST, give your person this link. It opens a confirm page; nothing is sent until they press its button." },
      { name: "status", method: "GET", url: `${origin}/agents/status/{run_id}?t=${token}`, template: `${origin}/agents/status/{run_id}?t={t}`,
        does: "The state of one run submitted with this token." },
      { name: "board", method: "GET", url: `${origin}/agents/board`, does: "The top 10: class, short id and scores only." },
    ],
    layout_format: {
      name: "compact layout", param: "l", order: ORDER, item: "<x>.<y>.<r>", separator: ",",
      x_y: `die centre in ${LATTICE_UM} um lattice steps from the interposer's lower-left corner: whole numbers 0 to ${FRAME_UM / LATTICE_UM}`,
      r: "quarter-turns: CPU 0 or 1 (0 or 90 degrees), DRAM 0",
      maps_to: "dies[i] = {die: i, x_um: 500 x, y_um: 500 y, rot_deg: 90 r}",
      example: SNAPPED_REFERENCE, example_note: "the legal snapped reference layout: a starting point, not an improvement",
      post_also_accepts: "layout as the contract's dies array: eight {die, x_um, y_um, rot_deg}",
    },
    board,
    board_status: boardStatus,
    human_page: `${origin}/?view=human`,
  };
}
