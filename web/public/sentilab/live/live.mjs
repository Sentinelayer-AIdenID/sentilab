// SentiLab Live Lab: the page. Draws only what live-model.mjs derives from the door feed (source3d.mjs createDoorFeed),
// the door's board and the lab-runs list, and the package geometry through model.mjs and render3d.mjs, exactly as the
// Package view does. Every string from data reaches the page through textContent (a run's label is rebuilt and checked
// by source3d.mjs; codes come from fixed vocabularies). No sample records, no random numbers, no clock-driven movement:
// the page changes only when a record changes or when the visitor asks (orbit, explode, an explicit replay).
import { createDoorFeed } from "../package/source3d.mjs";
import { buildRenderModel, displayBoxes, formatThickness, fieldTexels, VIEW } from "../package/model.mjs";
import { STACK_LAYERS, INTERPOSER_MM, CASE_TITLE } from "../package/case-cpu-dram.mjs";
import { webgl2Available } from "../package/render3d.mjs";
import { scorerChip, utcTime, stateLine } from "../package/status.mjs";
import { NOTICE } from "../../temperature-label.mjs";
import * as M from "./live-model.mjs";

const $ = (id) => document.getElementById(id);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
const SVG_NS = "http://www.w3.org/2000/svg";
function h(tag, props = null, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props ?? {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v; else if (k === "dataset") Object.assign(el.dataset, v); else el.setAttribute(k, v === true ? "" : String(v));
  }
  for (const c of kids.flat()) if (c !== null && c !== undefined && c !== false) el.append(c instanceof Node ? c : String(c));
  return el;
}
function s(tag, attrs = {}, text = null) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== null && v !== undefined) el.setAttribute(k, String(v));
  if (text !== null) el.textContent = text;
  return el;
}
const ICONS = { pause: '<path d="M6 4v16M17 4v16"/>', play: '<path d="m7 4 12 8-12 8Z"/>', expand: '<path d="M9 4H4v5m11-5h5v5M4 15v5h5m11-5v5h-5"/>',
  reset: '<path d="M4 10a8 8 0 1 1 1 8M4 4v6h6"/>', layers: '<path d="m12 3 10 6-10 6L2 9Zm-9 11 9 5 9-5M3 18l9 5 9-5"/>',
  orbit: '<circle cx="12" cy="12" r="3"/><ellipse cx="12" cy="12" rx="11" ry="5" transform="rotate(-30 12 12)"/>',
  compare: '<path d="M4 5h7v14H4Zm12 0h4v14h-4M9 12h8m-2-3 3 3-3 3"/>', info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7v1"/>',
  code: '<path d="m8 5-7 7 7 7m8-14 7 7-7 7m-3-15-2 18"/>', close: '<path d="m5 5 14 14M19 5 5 19"/>', rewind: '<path d="M4 4v16m15-16L7 12l12 8Z"/>',
  step: '<path d="M20 4v16M5 4l12 8-12 8Z"/>' };
const icon = (name) => `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] ?? ICONS.info}</svg>`;
function hydrateIcons(root = document) { for (const el of root.querySelectorAll("[data-icon]")) el.innerHTML = icon(el.dataset.icon); }

const CLASS_NOTE = Object.freeze({
  verified_agent: "An agent whose request signature verified. A classification, not an identity.",
  signed_agent: "An agent that signed its requests. A classification, not an identity.",
  declared_agent: "An agent that declared itself. A classification, not an identity.",
  crawler_claimed: "A client that claims to be a known crawler. A classification, not an identity.",
  automation: "An automated client. A classification, not an identity.",
  likely_human: "Most likely a person's browser. A classification, not an identity.",
  unknown: "An unclassified visitor.", ours: "Proposed by our own background agent.",
});
const CLASS_MARK = Object.freeze({ verified_agent: "V", signed_agent: "S", declared_agent: "D", crawler_claimed: "C", automation: "A", likely_human: "H", unknown: "?", ours: "O" });
const STATE_PIP = (state) => (["reproduced", "cross_checked", "evaluated"].includes(state) ? "mint"
  : ["queued", "held", "evaluating", "replaying"].includes(state) ? "sky" : ["failed", "rejected", "not_reproduced", "cancelled", "expired"].includes(state) ? "amber" : "grey");
const STATUS_TAG = Object.freeze({ queued: "QUEUED", held: "HELD", evaluating: "EVALUATING", evaluated: "EVALUATED", replaying: "REPLAYING",
  reproduced: "REPRODUCED", not_reproduced: "NOT REPRODUCED", cross_checked: "CROSS-CHECKED", rejected: "REJECTED", failed: "FAILED",
  cancelled: "CANCELLED", expired: "EXPIRED" });
const LAYER_COLOR = Object.freeze({ substrate: "#2c5a4c", c4: "#8c6f3e", interposer: "#5d6e7b", ubump: "#a8874d", chip: "#c4a7f5", tim: "#c9d4da",
  spreader: "#d39a66", sink: "#b9c4ca" });
const LANE_COLOR = Object.freeze({ arrival: "#8eb5d5", attempt: "#e8b878", run: "#a4e1c7" });
const fmtInt = (n) => Math.round(n).toLocaleString("en-US");

// ── state ──────────────────────────────────────────────────────────────────────────────────────────────────────────
const S = {
  selectedId: null, cursor: null, playing: false, playTimer: 0, explode: 0, explodeAnim: 0, orbit: false, motion: true, stage: false,
  board: { ok: null, board: null, error: "", at: null }, labRuns: null, v3: null, v3Failed: false, v3Pending: null, drawn: null, layer: null,
};
const feed = createDoorFeed({ onChange: () => render(), fetchEvents: M.fetchEventsTimed });

// ── the 3D package ─────────────────────────────────────────────────────────────────────────────────────────────────
const can3d = webgl2Available();
// The orbit-safe fit leaves room for every azimuth; the workspace frames the package a little closer (display only).
const ZOOM = 0.74;
function frameCamera() { if (!S.v3) return; S.v3.resize(); S.v3.zoomBy(ZOOM); }
async function ensure3d() {
  if (S.v3 || S.v3Failed || !can3d) return S.v3;
  if (S.v3Pending) return S.v3Pending;
  S.v3Pending = (async () => {
    try {
      const { createView3D } = await import("../package/render3d.mjs");
      const v = await createView3D({ canvas: $("packageCanvas"), labels: $("labels3d"), leaders: $("leaders3d"), reduced: REDUCED,
        onContextLost: () => { const old = S.v3; S.v3 = null; S.drawn = null; old?.dispose(); S.v3Failed = true; renderModel(); } });
      v.setLayerWords(new Map(STACK_LAYERS.map((l) => [l.level, [["b", null, l.name], ["span", null, formatThickness(l.t_mm)]]])));
      v.onUserMove(() => { if (S.orbit) setOrbit(false); });
      S.v3 = v;
    } catch {
      S.v3Failed = true;
    }
    S.v3Pending = null;
    return S.v3;
  })();
  return S.v3Pending;
}
// The field drawn on the chip layer: only a verified field associated with this exact layout (never a feed result).
const drawableField = (L) => (M.fieldOverlay(L).available ? fieldTexels(L.result.grid, L.result.field_key) : null);
// A run change is a hard cut (no glide from the previous run's dies): the new run's own geometry, field and words at once.
const drawKey = (L, at) => `${L.id}:${L.seq}:${L.status}:${at ? at.state : ""}:${S.explode}`;
function drawPackage(L, view, at) {
  if (!S.v3 || !L) return;
  const { model, error } = buildRenderModel({ kind: "model", layout: L });
  if (error) { S.drawn = { key: drawKey(L, at), error }; return; }
  const field = drawableField(L);
  const display = displayBoxes(model, { thin: true, lift: 1, explode: S.explode });
  S.v3.setDoor(model, display, { field, animate: false, notScored: view.metric ? null : view.none });
  S.drawn = { key: drawKey(L, at), id: L.id };
}

// ── rendering ──────────────────────────────────────────────────────────────────────────────────────────────────────
const layouts = () => feed.state.layouts;
const points = () => M.traceModel(feed.state.events).points;
function cursorEvent() {
  const pts = points();
  const c = M.clampCursor(S.cursor, pts.length);
  return c === null ? null : pts[c];
}
function shownRun() {
  const at = cursorEvent();
  if (at && at.kind === "run" && at.run_id) {
    const L = layouts().find((l) => l.id === at.run_id);
    if (L) return { L, at: { kind: "run", run_id: at.run_id, state: at.state } };
  }
  return { L: M.pickRun(layouts(), S.selectedId), at: null };
}

function render() {
  renderStatus();
  renderRuns();
  renderModel();
  renderWork();
  renderTrace();
}

function renderStatus() {
  const st = M.feedStatus(feed.state, { nowMs: Date.now(), hostname: location.hostname });
  const replay = S.cursor !== null;
  const badge = $("liveBadge");
  badge.dataset.state = replay ? "replay" : st.state;
  $("liveWord").textContent = replay ? "REPLAY · RECORDED" : st.word;
  $("liveAge").textContent = replay ? "" : st.state === "live" || st.state === "empty" ? (st.host === "staging" ? "staging host" : "")
    : st.state === "stale" ? `last answer ${st.ageS}s ago` : "";
  badge.title = replay ? "You chose a replay of records already received, shown with their original times. Follow live to return."
    : st.state === "live" ? "The door feed answered within the last 12 s." : st.state === "empty" ? "The door feed answered; it has no records yet."
      : st.state === "stale" ? `No fresh answer from the door feed (${st.error}). The last records stay on screen, marked stale.`
        : st.state === "error" ? `The door feed has not answered (${st.error}).` : "Asking the door feed.";
  const fs = $("feedState");
  fs.dataset.state = st.state;
  $("feedStateText").textContent = st.state === "live" ? `DOOR FEED LIVE · ${feed.state.events.length} RECORDS · ${layouts().length} RUNS`
    : st.state === "empty" ? "DOOR FEED LIVE · NO RECORDS YET"
      : st.state === "stale" ? `STALE · LAST GOOD ANSWER ${st.ageS}S AGO`
        : st.state === "error" ? `NOT CONNECTED · ${st.error.toUpperCase()}` : "CONNECTING TO THE DOOR";
  // The banner: a feed that is down or stale, and records the page refused.
  const banner = $("feedBanner");
  const refused = Object.entries(feed.state.refused ?? {});
  const parts = [];
  if (st.state === "error") parts.push(`The door feed is not answering (${st.error}). Nothing on this page is live; no records are shown in place of real ones. Retrying every 5 s.`);
  if (st.state === "stale") parts.push(`The door feed stopped answering (${st.error}). The records below are the last ones received, ${st.ageS} s ago, and may be out of date.`);
  if (refused.length) parts.push(`${refused.reduce((n, [, v]) => n + v, 0)} record(s) refused and not drawn: ${refused.map(([k, v]) => `${k.replace(/_/g, " ")} ×${v}`).join(", ")}.`);
  banner.hidden = parts.length === 0;
  banner.dataset.tone = st.state === "error" ? "error" : st.state === "stale" ? "stale" : "info";
  banner.textContent = parts.join(" ");
  renderDoorFacts(st);
}

function setFact(id, text, tone = "") { const el = $(id); el.textContent = text; el.className = tone; }
function renderDoorFacts(st) {
  const b = S.board;
  const fresh = b.ok === true && b.at !== null && Date.now() - b.at <= 2 * M.BOARD_POLL_MS;
  const board = b.board;
  if (!board) {
    const why = b.ok === false ? `unavailable (${b.error})` : "checking";
    for (const id of ["factDoor", "factQueue", "factBudget"]) setFact(id, why, "na");
  } else {
    const stale = fresh ? "" : " · stale";
    setFact("factDoor", board.door ? `${board.door.open ? "open" : "closed"}${board.door.codes.length ? ` · ${board.door.codes.join(", ").replace(/_/g, " ")}` : ""}${stale}` : "unavailable",
      board.door ? (board.door.open ? (fresh ? "" : "warn") : "warn") : "na");
    setFact("factQueue", board.queue ? `${board.queue.length} of ${board.queue.max} · ${board.queue.active} running${stale}` : "unavailable", board.queue ? (fresh ? "" : "warn") : "na");
    setFact("factBudget", board.budget ? `${fmtInt(board.budget.remaining_s)} of ${fmtInt(board.budget.cap_s)} s left${stale}` : "unavailable", board.budget ? (fresh ? "" : "warn") : "na");
  }
  // The scorer: the door feed's own snapshot while it is fresh (status.mjs scorerChip), else unknown.
  const chip = scorerChip({ feed: feed.state, nowMs: Date.now() });
  setFact("factScorer", chip.word === "unknown" ? "unknown" : `${chip.word}${chip.since ? ` since ${utcTime(chip.since)}` : ""}`,
    chip.word === "unreachable" ? "bad" : chip.word === "unknown" ? "na" : "");
}

function runCard(L, selected, { mobile = false } = {}) {
  const v = M.runView(L);
  const btn = h("button", { type: "button", class: mobile ? (selected ? "selected" : "") : `experiment${selected ? " selected" : ""}`, "aria-pressed": selected ? "true" : "false", dataset: { run: L.id } });
  if (mobile) {
    btn.append(L.label, h("small", null, v.metric ? `${v.metric.text} · ${v.metric.qualifier}` : (STATUS_TAG[L.status] ?? L.status).toLowerCase()));
  } else {
    btn.append(h("span", { class: "experiment-tag" }, STATUS_TAG[L.status] ?? L.status),
      h("strong", null, L.label),
      h("small", null, v.metric ? [v.metric.text, " ", h("em", null, v.metric.qualifier)] : v.none),
      h("span", { class: "experiment-bottom" }, h("span", { class: v.metric ? "mint-dot" : "grey-dot" }), `arrival ${L.arrival ?? "?"} · record ${L.seq ?? "?"}`));
  }
  btn.addEventListener("click", () => selectRun(L.id));
  return btn;
}
function renderRuns() {
  const list = M.runsNewestFirst(layouts());
  const shown = shownRun().L;
  $("runCount").textContent = String(list.length).padStart(2, "0");
  const box = $("runList"), mob = $("mobileRuns");
  const focusId = document.activeElement?.dataset?.run ?? null;
  box.replaceChildren(...list.map((L) => runCard(L, L === shown)));
  mob.replaceChildren(...list.map((L) => runCard(L, L === shown, { mobile: true })));
  if (!list.length) {
    const st = M.feedStatus(feed.state, { hostname: location.hostname }).state;
    box.append(h("p", { class: "rail-empty" }, st === "error" ? "No runs: the door feed is not answering." : st === "connecting" ? "Reading the door's runs." : "No runs yet. The first proposal appears here as it arrives."));
  }
  if (focusId) $$(`[data-run]`).find((b) => b.dataset.run === focusId && b.offsetParent !== null)?.focus();
  const lr = S.labRuns;
  $("labRunsText").textContent = !lr ? "Lab runs: checking" : lr.ok ? `Lab runs: ${lr.runs.total} listed · ${lr.runs.byStatus.finished} finished` : "Lab runs: list unavailable";
}

function renderModel() {
  const { L, at } = shownRun();
  const view = M.runView(L, { at });
  const empty = $("modelEmpty");
  const st = M.feedStatus(feed.state, { hostname: location.hostname }).state;
  if (!L) {
    empty.hidden = false;
    $("modelEmptyTitle").textContent = st === "error" ? "The door feed is not answering" : st === "connecting" ? "Waiting for the door" : "No runs yet";
    $("modelEmptyText").textContent = st === "error" ? "No geometry is drawn: nothing has arrived from the door, and no sample stands in for it."
      : st === "connecting" ? "Reading the runs." : "Connected. The first proposal is drawn here as it arrives.";
  } else if (!can3d || S.v3Failed) {
    empty.hidden = false;
    $("modelEmptyTitle").textContent = "The 3D view needs WebGL2";
    $("modelEmptyText").textContent = "This browser can't start it. The Package view draws the same run in 2D.";
  } else empty.hidden = true;
  $("modelTitle").textContent = L ? `Run ${L.label}` : "A closer look at the package.";
  $("modelKindText").textContent = L ? `${STATUS_TAG[L.status] ?? L.status} · RECORD ${L.seq ?? "?"}` : "NO RUN";
  // Metrics, bound to this run's own record.
  const mv = $("metricValue");
  mv.replaceChildren();
  mv.className = view?.metric ? "" : "none";
  if (view?.metric) {
    const [num, unit] = view.metric.text.split(" ");
    mv.append(num, h("small", null, unit), h("em", { title: view.metric.title }, view.metric.qualifier));
    mv.title = `${view.metricDefinition} ${view.metric.title} Rounded to 0.01 °C for display.`;
    $("metricDescription").textContent = `${view.metricName} · simulated, not silicon${view.diagnostic ? " · diagnostic" : ""}`;
  } else {
    mv.textContent = L ? "not scored" : "--";
    mv.title = "";
    $("metricDescription").textContent = view ? view.none : "No run selected";
  }
  $("metricLabel").textContent = at ? "BOARD METRIC · AT THIS RECORD" : "BOARD METRIC · SELECTED RUN";
  $("frameValue").replaceChildren(...(L ? [`${INTERPOSER_MM} × ${INTERPOSER_MM}`, h("small", null, "mm")] : ["--"]));
  $("frameNote").textContent = L ? `Interposer frame · 8 dies from this run's record (arrival ${L.arrival ?? "?"})` : "Interposer square of the model";
  const src = $("metricSource"), det = $("metricSourceDetail");
  if (view?.metric) {
    src.textContent = "HotSpot 6.0";
    det.replaceChildren(`grid 64 · ${M.verificationWords(view.verification).split(";")[0] || "as the feed reports it"}`,
      h("button", { type: "button", "aria-label": "Open this run's receipt", dataset: { modal: "receipt" } }, "↗"));
  } else {
    src.textContent = L ? "No result" : "--";
    det.textContent = L ? (view.none ?? "") : "No result selected";
  }
  for (const b of det.querySelectorAll("[data-modal]")) b.addEventListener("click", () => showModal(b.dataset.modal));
  // The field overlay: never without a verified, associated field.
  const field = view ? view.field : { available: false, reason: "Field overlay unavailable: no run" };
  $("heatMode").disabled = !field.available;
  $("heatMode").title = field.available ? "Show the verified field" : field.reason;
  $("fieldNote").textContent = field.available ? "" : field.reason.replace("Field overlay unavailable: ", "Field overlay unavailable · ");
  $("modelNote").replaceChildren(`Thin layers drawn ×${VIEW.THIN_Z} in z · cooling stack lifted`, h("br"), S.explode > 0 ? "Exploded · spacing not to scale" : "Schematic · not manufacturing CAD");
  $("packageCanvas").setAttribute("aria-label", L ? `3D view of the ${CASE_TITLE}: run ${L.label}, ${(stateLine(L) ?? L.status).toLowerCase()}. ${view.metric ? `${view.metricName} ${view.metric.text} ${view.metric.qualifier}, simulated, not silicon` : view.none}. Arrow keys orbit, plus and minus zoom.` : "No run drawn");
  if (!L) return;
  if (S.v3) { if (!S.drawn || S.drawn.key !== drawKey(L, at)) { const first = !S.drawn; drawPackage(L, view, at); if (first) frameCamera(); } }
  else if (can3d && !S.v3Failed) ensure3d().then((v) => { if (v) { S.drawn = null; renderModel(); } else renderModel(); });
}

// ── the work: atlas, visitors, newest record ─────────────────────────────────────────────────────────────────────
const STATION_XY = [[56, 34], [150, 22], [244, 34], [258, 108], [150, 128], [42, 108]];
function drawAtlas(svg, { large = false } = {}) {
  const a = M.atlas(layouts(), feed.state.events);
  const shown = shownRun().L;
  svg.replaceChildren();
  svg.append(s("ellipse", { class: "atlas-ring", cx: 150, cy: 76, rx: 108, ry: 52 }));
  a.stations.forEach((st, i) => {
    const [x, y] = STATION_XY[i];
    const g = s("g", { class: `atlas-station${st.count ? " has" : ""}` });
    const title = s("title", {}, `${st.name}: ${st.count} ${st.what}${st.id === "door" || st.id === "submit" ? " in the newest records" : ""}`);
    g.append(title, s("rect", { x: x - 22, y: y - 9, width: 44, height: 18, rx: 3 }), s("text", { class: "st-name", x, y: y + 3, "text-anchor": "middle" }, st.name),
      s("text", { x: x - 22, y: y - 12 }, st.n), s("text", { class: "st-count", x: x + 22, y: y - 12, "text-anchor": "end" }, String(st.count)));
    svg.append(g);
    // One dot per run at its station (a task state), at most 12 drawn per station; arrivals are counted, not drawn.
    const row = st.runs.slice(-12);
    row.forEach((r, k) => {
      const cx = x - ((row.length - 1) * 7) / 2 + k * 7, cy = y + (y < 76 ? 17 : -17);
      const dot = s("circle", { class: `atlas-dot${shown && r.id === shown.id ? " sel" : ""}`, cx: cx.toFixed(1), cy, r: large ? 3.5 : 2.8, fill: LANE_COLOR.run });
      dot.append(s("title", {}, `${r.label} · ${(STATUS_TAG[r.status] ?? r.status).toLowerCase()}`));
      dot.addEventListener("click", () => selectRun(r.id));
      svg.append(dot);
    });
  });
  if (a.out.length) svg.append(s("text", { x: 150, y: 168, "text-anchor": "middle", class: "atlas-out", fill: "#8fa398", "font-size": 8, "font-family": "monospace" },
    `${a.out.length} run(s) out of the flow: rejected, failed, cancelled or expired`));
  return a;
}
function renderWork() {
  drawAtlas($("atlasSvg"));
  const { rows, anonymous } = M.followRows(feed.state.events, layouts());
  const shown = shownRun().L;
  $("visitorCount").textContent = `${rows.length} ID${rows.length === 1 ? "" : "S"}`;
  const list = $("visitorList");
  list.replaceChildren();
  for (const r of rows.slice(0, 30)) {
    const task = r.task ? (STATUS_TAG[r.task.state] ?? r.task.state).toLowerCase() : "no run";
    const btn = h("button", { type: "button", class: `agent-row${shown && r.task?.run_id === shown.id ? " selected" : ""}`, dataset: { visitor: r.key } },
      h("span", { class: `agent-avatar c-${r.cls}`, "aria-hidden": "true" }, CLASS_MARK[r.cls] ?? "?"),
      h("span", null, h("strong", null, r.label), h("small", null, r.last ? `seen ${M.hms(r.last.at)} · ${r.last.line}` : "location unknown: not in the newest records")),
      h("span", { class: "agent-task" }, task), h("span", { class: `agent-pip ${r.task ? STATE_PIP(r.task.state) : "grey"}` }));
    btn.addEventListener("click", () => { if (r.task && layouts().some((l) => l.id === r.task.run_id)) selectRun(r.task.run_id); openVisitor(r); });
    list.append(btn);
  }
  for (const a of anonymous) list.append(h("div", { class: "anon-row" }, h("span", { class: "agent-pip sky" }), h("b", null, a.cls), `${a.count} arrival(s) without a token · last ${M.hms(a.lastAt)}`));
  if (!rows.length && !anonymous.length) list.append(h("p", { class: "rail-empty" }, M.feedStatus(feed.state, { hostname: location.hostname }).state === "error" ? "No records: the door feed is not answering." : "No records yet."));
  // The newest record, or the replay cursor's.
  const pts = points();
  const c = M.clampCursor(S.cursor, pts.length);
  const p = c === null ? pts.at(-1) : pts[c];
  $("selectedEventLabel").textContent = c === null ? "NEWEST RECORD" : `REPLAY · RECORD ${c + 1} OF ${pts.length}`;
  $("eventTitle").textContent = p ? `${p.label} ${p.line}` : "No record yet";
  $("eventSubtitle").textContent = p ? `${p.kind} · seq ${p.seq} · ${M.hms(p.at)}` : "Waiting for the door";
}

// ── the flight record ──────────────────────────────────────────────────────────────────────────────────────────────
function renderTrace() {
  const svg = $("traceSvg");
  const { points: pts, first, last } = M.traceModel(feed.state.events);
  const w = Math.max(260, svg.clientWidth || 1000), hgt = Math.max(60, svg.clientHeight || 84);
  svg.setAttribute("viewBox", `0 0 ${w} ${hgt}`);
  const ys = [0.18, 0.5, 0.82].map((f) => f * hgt);
  const xOf = (p) => 10 + p.x * (w - 20);
  svg.replaceChildren(...ys.map((y) => s("path", { d: `M0 ${y} H${w}`, fill: "none", stroke: "#355040", "stroke-width": 0.6 })));
  // A trail joins records of the same short id (the same run or visitor): a real link, not an invented handoff.
  const byLabel = new Map();
  for (const p of pts) {
    if (p.label.includes(" · ")) {
      const prev = byLabel.get(p.label);
      if (prev) {
        const [px, py, x, y] = [xOf(prev), ys[prev.lane], xOf(p), ys[p.lane]];
        svg.append(s("path", { d: `M${px} ${py} C${px + 18} ${py},${x - 18} ${y},${x} ${y}`, stroke: LANE_COLOR[p.kind], "stroke-width": 0.8, fill: "none", opacity: 0.45 }));
      }
      byLabel.set(p.label, p);
    }
  }
  const c = M.clampCursor(S.cursor, pts.length);
  pts.forEach((p, i) => {
    const g = s("g", { class: "trace-pt", tabindex: -1, dataset: null });
    g.dataset.index = String(i);
    const cx = xOf(p), cy = ys[p.lane];
    g.append(s("rect", { x: cx - 6, y: cy - 10, width: 12, height: 20, fill: "transparent" }),
      s("circle", { cx, cy, r: c === i ? 4.5 : 3, fill: LANE_COLOR[p.kind], opacity: c !== null && i > c ? 0.3 : 1 }),
      s("title", {}, `${p.label} ${p.line} · seq ${p.seq} · ${M.hms(p.at)}`));
    g.addEventListener("click", () => { setCursor(i); openRecord(i); });
    svg.append(g);
  });
  $("traceStart").textContent = first ? `FIRST KEPT · ${M.hms(first.at)}` : "NO RECORDS";
  $("traceEnd").textContent = last ? `NEWEST · ${M.hms(last.at)}` : "";
  const ph = $("playhead");
  ph.hidden = c === null;
  if (c !== null) ph.style.left = `${xOf(pts[c])}px`;
  const range = $("replayRange");
  range.max = String(Math.max(0, pts.length - 1));
  range.disabled = pts.length === 0;
  range.value = String(c ?? Math.max(0, pts.length - 1));
  range.setAttribute("aria-valuetext", pts.length ? `record ${(c ?? pts.length - 1) + 1} of ${pts.length}` : "no records");
  const tc = $("timecode");
  tc.replaceChildren(c === null ? (last ? `LIVE · ${M.hms(last.at)}` : "--") : `${c + 1} / ${pts.length} · ${M.hms(pts[c].at)}`,
    h("span", null, c === null ? ` · ${pts.length} kept` : " · recorded"));
  $("followLive").setAttribute("aria-pressed", c === null ? "true" : "false");
  $("transportNote").textContent = c === null ? "Live: following the newest record. Replay plays only when you choose it." : "Replay of records already received, at their original times";
  $("play").innerHTML = icon(S.playing ? "pause" : "play");
  $("play").setAttribute("aria-label", S.playing ? "Pause the replay" : "Replay the recorded records");
  // Phones: a readable list of the newest records.
  const ml = $("mobileEventList");
  ml.replaceChildren(...pts.slice(-12).reverse().map((p) => {
    const i = pts.indexOf(p);
    const b = h("button", { type: "button" }, h("span", null, M.hms(p.at), h("small", null, `seq ${p.seq}`)), h("strong", null, `${p.label} ${p.line}`), h("b", { "aria-hidden": "true" }, "↗"));
    b.addEventListener("click", () => { setCursor(i); openRecord(i); });
    return b;
  }));
}

// ── interaction ────────────────────────────────────────────────────────────────────────────────────────────────────
function selectRun(id) { S.selectedId = id; if (S.cursor !== null) { S.cursor = null; stopPlay(); } render(); }
function setCursor(i) { const n = points().length; S.cursor = M.clampCursor(i, n); render(); }
function followLive() { stopPlay(); S.cursor = null; render(); }
function stopPlay() { S.playing = false; clearTimeout(S.playTimer); }
function play() {
  const n = points().length;
  if (!n || !S.motion) return;
  if (S.cursor === null || S.cursor >= n - 1) S.cursor = 0;
  S.playing = true;
  const tick = () => {
    if (!S.playing) return;
    const m = points().length;
    if (S.cursor >= m - 1) { stopPlay(); render(); return; }
    S.cursor += 1;
    render();
    S.playTimer = setTimeout(tick, REDUCED ? 2000 : 1200);
  };
  render();
  S.playTimer = setTimeout(tick, REDUCED ? 2000 : 1200);
}
function setExplode(v, { animate = false } = {}) {
  cancelAnimationFrame(S.explodeAnim);
  const to = Math.max(0, Math.min(1, v));
  const apply = (x) => {
    S.explode = x;
    $("explodeRange").value = String(Math.round(x * 100));
    $("explodeButton").setAttribute("aria-pressed", x > 0.02 ? "true" : "false");
    $("explodeWord").textContent = x > 0.02 ? "Exploded" : "Assembled";
    const { L, at } = shownRun();
    if (L && S.v3) drawPackage(L, M.runView(L, { at }), at);
  };
  if (!animate || REDUCED || !S.motion) { apply(to); frameCamera(); renderModel(); return; }
  const from = S.explode, start = performance.now();
  const step = (now) => {
    const t = Math.min(1, (now - start) / 600), e = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
    apply(from + (to - from) * e);
    if (t < 1) S.explodeAnim = requestAnimationFrame(step); else { frameCamera(); renderModel(); }
  };
  S.explodeAnim = requestAnimationFrame(step);
}
function setOrbit(on) {
  S.orbit = Boolean(on) && !REDUCED && S.motion;
  S.v3?.setAutoOrbit(S.orbit);
  $("orbitButton").setAttribute("aria-pressed", S.orbit ? "true" : "false");
  $("orbitButton").setAttribute("aria-label", S.orbit ? "Stop slow orbit" : "Start slow orbit");
}
function setMotion(on) {
  S.motion = on;
  if (!on) { setOrbit(false); stopPlay(); }
  $("motionToggle").setAttribute("aria-pressed", on ? "false" : "true");
  $("motionToggle").setAttribute("aria-label", on ? "Pause all motion" : "Allow motion");
  $("motionToggle").innerHTML = icon(on ? "pause" : "play");
  render();
}
function setStage(on) {
  S.stage = on;
  document.body.classList.toggle("stage-mode", on);
  $("stageButton").setAttribute("aria-pressed", on ? "true" : "false");
  $("stageButton").querySelector(".stage-word").textContent = on ? "Exit stage" : "Stage mode";
  requestAnimationFrame(() => { frameCamera(); renderTrace(); });
}
function setMobile(tab) {
  document.body.classList.remove("mobile-agents", "mobile-trace");
  if (tab !== "model") document.body.classList.add(`mobile-${tab}`);
  for (const b of $$("[data-mobile]")) { const on = b.dataset.mobile === tab; b.classList.toggle("active", on); b.setAttribute("aria-selected", on ? "true" : "false"); }
  requestAnimationFrame(() => { frameCamera(); renderTrace(); });
}
function selectLayer(level) {
  S.layer = S.layer === level ? null : level;
  for (const b of $$("#layerList button")) b.classList.toggle("active", b.dataset.layer === S.layer);
  const box = $("layerDetail");
  const l = STACK_LAYERS.find((x) => x.level === S.layer);
  box.hidden = !l;
  if (!l) return;
  box.replaceChildren(h("strong", null, l.name), h("small", null, `${formatThickness(l.t_mm)} thick · ${l.material} · k ${l.k} W/m·K`),
    h("small", null, l.side_mm === INTERPOSER_MM ? `${l.side_mm} mm square, the model's grid` : `${l.side_mm} mm part; the grid covers its central ${INTERPOSER_MM} mm`));
}

// ── dialogs ────────────────────────────────────────────────────────────────────────────────────────────────────────
function openDialog(title, eyebrow, ...body) {
  $("modalTitle").textContent = title;
  $("modalEyebrow").textContent = eyebrow;
  $("modalBody").replaceChildren(...body);
  hydrateIcons($("modalBody"));
  for (const b of $("modalBody").querySelectorAll("[data-modal]")) b.addEventListener("click", () => showModal(b.dataset.modal));
  if (!$("modal").open) $("modal").showModal();
}
const lead = (t) => h("p", { class: "modal-lead" }, t);
const note = (t, amber = false) => h("div", { class: `modal-note${amber ? " amber-note" : ""}` }, t);
const table = (rows) => h("table", { class: "evidence-table" }, h("tbody", null, rows.map(([k, v, cls]) => h("tr", null, h("td", null, k), h("td", { class: cls ?? null }, v)))));
function openRecord(i) {
  const p = points()[i];
  if (!p) return;
  const e = feed.state.events.find((x) => x.seq === p.seq);
  openDialog(`${p.label} ${p.line}`, `RECORD ${i + 1} OF ${points().length} · ${p.kind.toUpperCase()}`,
    lead("One record as the door's events feed returned it, after the page's checks. The time is the server's own; the label is a classification and a short id, never a name."),
    table([["Kind", p.kind], ["Server time", p.at ?? "not recorded"], ["Sequence", String(p.seq)], ["Label (class · short id)", p.label],
      ["Page route", "not recorded: the door's events carry no page route", "unknown"], ["Identity", "not established: a class is an observation, not an identity", "unknown"]]),
    h("pre", { class: "json-block" }, JSON.stringify(e ?? p, null, 2)));
}
function openVisitor(r) {
  const runs = layouts().filter((l) => l.label === r.label);
  openDialog(r.label, "VISITOR · CLASS · SHORT ID",
    lead(CLASS_NOTE[r.cls] ?? "A classification, not an identity."),
    h("div", { class: "modal-grid" },
      h("div", { class: "modal-card" }, h("span", { class: "label" }, "LAST OBSERVED (LOCATION)"), h("h3", null, r.last ? r.last.line : "unknown"),
        h("p", null, r.last ? `${r.last.kind} record · seq ${r.last.seq} · ${M.hms(r.last.at)}` : "The newest records the door kept show no action by this id."),
        h("p", null, "A record says where the door saw this id act. It stays here until a new record says otherwise.")),
      h("div", { class: "modal-card" }, h("span", { class: "label" }, "TASK (RUN STATE)"), h("h3", null, r.task ? (STATUS_TAG[r.task.state] ?? r.task.state).toLowerCase() : "no run"),
        h("p", null, r.task ? `run record · seq ${r.task.seq >= 0 ? r.task.seq : "?"} · ${M.hms(r.task.at ?? null)}` : "No run record for this id."),
        h("p", null, runs.length ? runs.map((l) => stateLine(l) ?? l.status).join(" · ") : "No run of this id is in the results list."),
        h("p", null, "A run finishing changes the task, not the location."))),
    table([["Presence now", "unknown: the door does not publish presence to this page", "unknown"], ["Page route", "not recorded", "unknown"],
      ["Identity", "not established (classification only)", "unknown"], ["Records in the newest window", String(r.records)]]));
}
function showModal(kind) {
  const { L, at } = shownRun();
  if (kind === "receipt" || kind === "evidence") {
    const rc = M.receiptOf(L);
    const v = M.runView(L, { at });
    openDialog(L ? `Run ${L.label}` : "No run selected", kind === "receipt" ? "RECEIPT · AS THE FEED REPORTS IT" : "EVIDENCE",
      lead("Every number here is the scorer's, as the door's results feed reports it, for this run's own record. The page shows it; it does not recompute or verify it."),
      L ? table([["Board metric", v.metric ? `${v.metric.text} · ${v.metric.qualifier}${v.diagnostic ? " · diagnostic" : ""}` : v.none],
        ["Definition", v.metricDefinition], ...v.distinct.map((d) => [`${d.name} (a different statistic)`, `${d.text.text} · ${d.text.qualifier}`]),
        ["Claim", v.claim ?? "none"], ["Evaluator named by the feed", v.evaluator ?? "none named", v.evaluator ? null : "unknown"],
        ["Checks the feed reports", v.verification ? M.verificationWords(v.verification) : "none"],
        ["Temperature field", v.field.available ? "verified field, associated with this layout" : v.field.reason, v.field.available ? null : "unknown"],
        ["Physical validation", "not established: simulated, not silicon", "unknown"]]) : lead("No run is selected."),
      L ? h("pre", { class: "json-block" }, JSON.stringify(rc, null, 2)) : "",
      note(NOTICE, true));
  } else if (kind === "atlas") {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 300 172");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "Door atlas, expanded");
    const a = drawAtlas(svg, { large: true });
    openDialog("Stations are the door's own records.", "THE DOOR ATLAS",
      lead("Each station is a kind of record the door emits. A dot is a run at its last reported state: a task state, not a screen position. Arrivals and refused attempts are counted where the door saw them."),
      h("div", { class: "large-map" }, svg),
      table(a.stations.map((st) => [`${st.n} ${st.name}`, `${st.count} · ${st.what}`])),
      note("No dot moves on the page's own clock. When a record changes a run's state, its dot changes station at once; nothing is interpolated in between."));
  } else if (kind === "live") {
    const st = M.feedStatus(feed.state, { hostname: location.hostname });
    openDialog("Live means the door answered just now.", "WHAT IS LIVE",
      lead("This page reads the agent door's public feeds every few seconds: its runs and results, its records of arrivals, attempts and run changes, and its board."),
      table([["Feed state now", `${st.word}${st.error ? ` · ${st.error}` : ""}`], ["Last good answer", feed.state.lastOkAt ? new Date(feed.state.lastOkAt).toISOString().slice(11, 19) + "Z" : "none yet"],
        ["LIVE badge", "only while the last good answer is under 12 s old"], ["STALE", "the feed stopped answering: the last records stay, marked stale"],
        ["NOT CONNECTED", "no answer ever: nothing is shown in place of real records"], ["REPLAY", "only when you choose it: records already received, at their original times"],
        ["Presence, identity, page routes", "not published by the door: shown as unknown", "unknown"]]),
      note("A record proves the door saw an action at that time. It is not a continuous position, a visit to any other page, or an identity."));
  } else if (kind === "trace") {
    const pts = points();
    openDialog("The door's newest records.", "FLIGHT RECORD",
      lead(`The ${pts.length} newest records the door returned, oldest first. Select one to replay from it.`),
      h("div", null, pts.map((p, i) => { const b = h("button", { type: "button", class: "event-list-row" }, h("span", null, M.hms(p.at)), h("span", null, p.kind), h("strong", null, `${p.label} ${p.line}`)); b.addEventListener("click", () => { setCursor(i); openRecord(i); }); return b; })));
  } else if (kind === "sources") {
    openDialog("What is real on this page?", "SOURCES & SCOPE",
      h("ul", { class: "modal-list" },
        h("li", null, h("span", { class: "step-no" }, "01"), h("div", null, h("strong", null, "The door's runs and results"), h("p", null, "GET /api/open/v1/door/results: each run's eight dies and, once scored, the scorer's board metric and the checks it reports. Simulated by HotSpot 6.0 on the model stack; not silicon."))),
        h("li", null, h("span", { class: "step-no" }, "02"), h("div", null, h("strong", null, "The door's records"), h("p", null, "GET /api/open/v1/door/events: arrivals, refused attempts and run state changes, with server times."))),
        h("li", null, h("span", { class: "step-no" }, "03"), h("div", null, h("strong", null, "The board"), h("p", null, "GET /api/open/v1/door/board: whether the door is open, the queue and the compute budget."))),
        h("li", null, h("span", { class: "step-no" }, "04"), h("div", null, h("strong", null, "Lab runs"), h("p", null, "GET /api/view/runs: the lab runs listed; the Lab view shows them.")))),
      note("Geometry and layer thicknesses come from the model stack the solver simulates (the Package view's model). Layer heights are drawn thicker than true where marked; explode spacing is display only."),
      note(NOTICE, true));
  } else {
    openDialog("One workspace. Three ways to read it.", "HOW TO READ THIS LAB",
      h("ol", { class: "modal-list" },
        h("li", null, h("span", { class: "step-no" }, "01"), h("div", null, h("strong", null, "The physical model."), h("p", null, "Each run's eight dies on the CPU-DRAM package, from its own record. Drag to orbit, explode the layers (display only), select a layer to read its true thickness."))),
        h("li", null, h("span", { class: "step-no" }, "02"), h("div", null, h("strong", null, "The work."), h("p", null, "The door's stations and the visitors' short ids, from the door's own records. Unknown stays unknown."))),
        h("li", null, h("span", { class: "step-no" }, "03"), h("div", null, h("strong", null, "The flight record."), h("p", null, "The newest records, in order. Replay one only when you choose to; LIVE returns to the newest.")))),
      note("No temperature colours are drawn: the door's results carry a scalar, not a temperature field. Every temperature is simulated, unvalidated and diagnostic."));
  }
}
function closeDialog() { $("modal").close(); }

// ── wiring ─────────────────────────────────────────────────────────────────────────────────────────────────────────
function wire() {
  hydrateIcons();
  $("wnotice").textContent = NOTICE;
  $("layerCount").textContent = String(STACK_LAYERS.length).padStart(2, "0");
  $("layerList").replaceChildren(...[...STACK_LAYERS].reverse().map((l) => {
    const sw = h("i", { class: "layer-swatch" });
    sw.style.background = LAYER_COLOR[l.level];
    const b = h("button", { type: "button", dataset: { layer: l.level } }, sw, h("span", null, l.name), h("small", null, formatThickness(l.t_mm)));
    b.addEventListener("click", () => selectLayer(l.level));
    return b;
  }));
  for (const b of $$("[data-modal]")) b.addEventListener("click", () => showModal(b.dataset.modal));
  $("closeModal").addEventListener("click", closeDialog);
  $("modal").addEventListener("click", (e) => { if (e.target === $("modal")) { const r = $("modal").getBoundingClientRect(); if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) closeDialog(); } });
  $("modelReset").addEventListener("click", () => { S.v3?.home(); frameCamera(); if (S.layer) selectLayer(S.layer); });
  $("explodeButton").addEventListener("click", () => setExplode(S.explode > 0.02 ? 0 : 1, { animate: true }));
  $("explodeRange").addEventListener("input", (e) => setExplode(Number(e.target.value) / 100));
  $("orbitButton").addEventListener("click", () => setOrbit(!S.orbit));
  $("motionToggle").addEventListener("click", () => setMotion(!S.motion));
  $("stageButton").addEventListener("click", () => setStage(!S.stage));
  $("play").addEventListener("click", () => (S.playing ? (stopPlay(), render()) : play()));
  $("rewind").addEventListener("click", () => { stopPlay(); setCursor(0); });
  $("step").addEventListener("click", () => { stopPlay(); const n = points().length; if (n) setCursor(S.cursor === null ? 0 : Math.min(n - 1, S.cursor + 1)); });
  $("replayRange").addEventListener("input", (e) => { stopPlay(); setCursor(Number(e.target.value)); });
  $("followLive").addEventListener("click", followLive);
  $("selectedEvent").addEventListener("click", () => { const n = points().length; if (n) openRecord(M.clampCursor(S.cursor, n) ?? n - 1); });
  for (const b of $$("[data-mobile]")) b.addEventListener("click", () => setMobile(b.dataset.mobile));
  $("brand").addEventListener("click", () => showIntro());
  $("replayIntro").addEventListener("click", () => showIntro());
  $("skipIntro").addEventListener("click", hideIntro);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { hideIntro(); if (S.stage && !$("modal").open) setStage(false); }
  });
  document.addEventListener("visibilitychange", () => { if (document.hidden) stopPlay(); else pollBoard(); });
  new ResizeObserver(() => renderTrace()).observe($("traceSvg"));
  new ResizeObserver(() => frameCamera()).observe($("modelViewport"));
}

// ── the entrance (skippable; once per session; none with reduced motion) ─────────────────────────────────────────────
let introTimer = 0;
function hideIntro() { clearTimeout(introTimer); const el = $("intro"); el.classList.add("hidden"); el.setAttribute("aria-hidden", "true"); el.inert = true; try { sessionStorage.setItem("sentilab-intro-seen", "yes"); } catch { /* storage off */ } }
function showIntro() {
  if (REDUCED) return;
  clearTimeout(introTimer);
  const el = $("intro");
  el.classList.remove("hidden"); el.removeAttribute("aria-hidden"); el.inert = false;
  for (const x of el.querySelectorAll(".intro-chip,.intro-word,.intro-grid")) { x.style.animation = "none"; void x.offsetWidth; x.style.animation = ""; }
  introTimer = setTimeout(hideIntro, 2400);
}

// ── polling: the door feed (one subscription), the board and the lab-runs list ────────────────────────────────────
let boardTimer = 0, boardEpoch = 0;
async function pollBoard() {
  clearTimeout(boardTimer);
  const mine = ++boardEpoch;
  if (!document.hidden) {
    const got = await M.fetchBoard();
    if (mine !== boardEpoch) return;
    S.board = got.ok ? { ok: true, board: got.board, error: "", at: Date.now() } : { ...S.board, ok: false, error: got.error };
    renderStatus();
  }
  boardTimer = setTimeout(pollBoard, M.BOARD_POLL_MS);
}
let runsTimer = 0;
async function pollLabRuns() {
  clearTimeout(runsTimer);
  if (!document.hidden) { S.labRuns = await M.fetchLabRuns(); renderRuns(); }
  runsTimer = setTimeout(pollLabRuns, M.RUNS_POLL_MS);
}

wire();
render();
try { if (!sessionStorage.getItem("sentilab-intro-seen")) showIntro(); } catch { /* storage off: no entrance */ }
feed.start();
pollBoard();
pollLabRuns();
// The badge and ages follow the clock even when no answer arrives (a hung request must still turn LIVE into STALE).
setInterval(() => { renderStatus(); }, 1000);
window.addEventListener("pagehide", () => { feed.stop(); clearTimeout(boardTimer); clearTimeout(runsTimer); stopPlay(); });
