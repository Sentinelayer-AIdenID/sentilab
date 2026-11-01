// SentiLab Live Lab: the page. Draws only what live-model.mjs derives from the door feed (source3d.mjs createDoorFeed),
// the door's board and the lab-runs list, and the package geometry through model.mjs and render3d.mjs, exactly as the
// Package view does. Every string from data reaches the page through textContent (a run's label is rebuilt and checked
// by source3d.mjs; codes come from fixed vocabularies). No sample records, no random numbers, no clock-driven movement:
// the page changes only when a record changes or when the visitor asks (orbit, explode, an explicit replay).
import { createDoorFeed } from "../package/source3d.mjs";
import { buildRenderModel, displayBoxes, formatThickness, fieldTexels, VIEW } from "../package/model.mjs";
import { STACK_LAYERS, INTERPOSER_MM, CASE_TITLE } from "../package/case-cpu-dram.mjs";
import { webgl2Available } from "../package/render3d.mjs";
import { drawPackage as draw2dPackage, TrackAnimation } from "../package/render.mjs";
import { scorerChip, utcTime, stateLine } from "../package/status.mjs";
import { NOTICE } from "../../temperature-label.mjs";
import * as M from "./live-model.mjs";
import * as W from "./words.mjs";

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
  selectedId: null, cursorSeq: null, playing: false, playTimer: 0, explode: 0, explodeAnim: 0, orbit: false, motion: true, stage: false,
  board: { ok: null, board: null, error: "", at: null }, decl: { ok: null, partial: false, list: [], error: "", at: null, through: 0 }, v3: null, v3Failed: false, v3Pending: null, drawn: null, layer: null,
};
// One gate for every request the page makes: spacing, Retry-After and jittered backoff (live-model.mjs createGate).
const gate = M.createGate();
const feed = createDoorFeed({ onChange: () => render(), fetchEvents: M.fetchEventsTimed, fetchImpl: gate.fetch });

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
        onContextLost: () => { const old = S.v3; S.v3 = null; S.drawn = null; old?.dispose(); S.v3Failed = true; S.v3Lost = true; renderModel(); } });
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
  const c = M.cursorIndex(pts, S.cursorSeq);
  return c === null ? null : pts[c];
}
function shownRun() {
  const at = cursorEvent();
  if (at && at.kind === "run" && at.run_id) {
    const L = layouts().find((l) => l.id === at.run_id);
    if (L) return { L, at: { kind: "run", run_id: at.run_id, state: at.state, seq: at.seq, at: at.at } };
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
  const replay = S.cursorSeq !== null;
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
  $("feedStateText").textContent = st.state === "live" ? W.TEXT.feedLive(layouts().length, feed.state.events.length)
    : st.state === "empty" ? W.TEXT.feedEmpty
      : st.state === "stale" ? W.TEXT.feedStale(st.ageS)
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
    setFact("factQueue", board.queue ? `${W.TEXT.queue(board.queue.length, board.queue.active)}${stale}` : "unavailable", board.queue ? (fresh ? "" : "warn") : "na");
    setFact("factBudget", board.budget ? `${W.TEXT.computeLeft(Math.round(board.budget.remaining_s / 60), Math.round(board.budget.cap_s / 60))}${stale}` : "unavailable", board.budget ? (fresh ? "" : "warn") : "na");
  }
  // The scorer: the door feed's own snapshot while it is fresh (status.mjs scorerChip), else unknown.
  const chip = scorerChip({ feed: feed.state, nowMs: Date.now() });
  setFact("factScorer", chip.word === "unknown" ? "unknown" : chip.word === "unreachable" ? "not reachable"
    : chip.since ? W.TEXT.simulatorUp(W.localTime(chip.since * 1000)) : chip.word === "busy" ? "running, busy" : "running",
    chip.word === "unreachable" ? "bad" : chip.word === "unknown" ? "na" : "");
}

function runCard(L, selected, { mobile = false } = {}) {
  const v = M.runView(L);
  const btn = h("button", { type: "button", class: mobile ? (selected ? "selected" : "") : `experiment${selected ? " selected" : ""}`, "aria-pressed": selected ? "true" : "false", dataset: { run: L.id } });
  if (mobile) {
    btn.append(M.runTitle(L), h("small", null, v.metric ? `${v.metric.text} · ${W.tempWord(v.metric, v.verification)}` : (STATUS_TAG[L.status] ?? L.status).toLowerCase()),
      h("small", { class: "vt" }, W.visitorType(L.cls)));
  } else {
    btn.append(h("span", { class: "experiment-tag" }, STATUS_TAG[L.status] ?? L.status),
      h("strong", null, M.runTitle(L)), h("small", { class: "vt" }, W.visitorType(L.cls)),
      h("small", null, v.metric ? [v.metric.text, " ", h("em", { title: v.metric.title }, W.tempWord(v.metric, v.verification))] : v.none),
      h("span", { class: "experiment-bottom" }, h("span", { class: v.metric ? "mint-dot" : "grey-dot" }), v.metric ? "simulated, not silicon" : "no temperature yet"));
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
}

function renderModel() {
  const { L, at } = shownRun();
  const view = M.runView(L, { at });
  const empty = $("modelEmpty");
  const st = M.feedStatus(feed.state, { hostname: location.hostname }).state;
  const renderer = !L ? "none" : can3d && !S.v3Failed ? "3d" : "2d";
  if (!L) {
    empty.hidden = false;
    $("modelEmptyTitle").textContent = st === "error" ? "The door feed is not answering" : st === "connecting" ? "Waiting for the door" : "No runs yet";
    $("modelEmptyText").textContent = st === "error" ? "No geometry is drawn: nothing has arrived from the door, and no sample stands in for it."
      : st === "connecting" ? "Reading the runs." : "Connected. The first proposal is drawn here as it arrives.";
  } else empty.hidden = true;
  applyControls(M.viewControls(renderer));
  $("selectionCaption").textContent = renderer === "2d" ? "2D drawing · orbit and explode need the 3D view" : "Drag to orbit · scroll to zoom · arrows when focused";
  $("modelTitle").textContent = L ? M.runTitle(L) : "A closer look at the package.";
  $("modelSub").textContent = L ? W.visitorType(L.cls) : "";
  const lastRun = L ? [...feed.state.events].filter((e) => e.kind === "run" && e.run_id === L.id).sort((x, y) => y.seq - x.seq)[0] : null;
  $("modelCap").textContent = !L ? "" : [W.layoutFrom(L.short), view.metric ? `${W.METRIC_NAME.toLowerCase()} ${view.metric.text} · ${W.tempWord(view.metric, view.verification)}` : null,
    W.RESULT_CHECK[L.status] ?? null, lastRun?.at ? W.when(lastRun.at) : null].filter(Boolean).join(" · ");
  const picked = Boolean(L && S.selectedId === L.id && M.pickRun(layouts(), null)?.id !== L.id);
  $("modelKindText").textContent = !L ? "NO RUN" : view.atRecord ? `REPLAY · ${view.state.toUpperCase()}`
    : `${STATUS_TAG[L.status] ?? L.status}${picked ? ` · ${W.YOUR_PICK.toUpperCase()}` : ""}`;
  // Metrics, bound to this run's own record; at a replay cursor, the state as of that record, and the latest apart.
  const mv = $("metricValue");
  mv.replaceChildren();
  mv.className = view?.metric ? "" : "none";
  if (view?.metric) {
    const [num, unit] = view.metric.text.split(" ");
    mv.append(num, h("small", null, unit), h("em", { title: view.metric.title }, W.tempWord(view.metric, view.verification)));
    mv.title = `${view.metricDefinition} ${view.metric.title} Rounded to 0.01 °C for display.`;
    $("metricDescription").textContent = `${W.METRIC_NAME} · simulated, not silicon${view.diagnostic ? " · diagnostic" : ""}`;
  } else if (view?.atRecord) {
    mv.textContent = view.state.toLowerCase();
    mv.title = "";
    $("metricDescription").textContent = W.TEXT.atStep(W.when(view.atRecord.at));
  } else {
    mv.textContent = L ? "not scored" : "--";
    mv.title = "";
    $("metricDescription").textContent = view ? view.none : "No run selected";
  }
  $("metricLabel").textContent = view?.atRecord ? "STATE AT THIS RECORD" : "BOARD METRIC · SELECTED RUN";
  $("frameValue").replaceChildren(...(L ? [`${INTERPOSER_MM} × ${INTERPOSER_MM}`, h("small", null, "mm")] : ["--"]));
  $("frameNote").textContent = L ? W.TEXT.frameNote : "Interposer square of the model";
  const src = $("metricSource"), det = $("metricSourceDetail");
  const latest = view?.atRecord ? view.latest : view;
  $("sourceLabel").textContent = view?.atRecord ? "LATEST RESULT · NOT AT THIS STEP" : "EVALUATION SOURCE";
  if (latest?.metric) {
    src.textContent = view.atRecord ? `${latest.metric.text} · ${W.tempWord(latest.metric)}` : "HotSpot 6.0";
    det.replaceChildren(view.atRecord ? `latest state ${latest.state.toLowerCase()} · HotSpot 6.0, grid 64` : `grid 64 · ${M.verificationWords(latest.verification).split(";")[0] || "as the feed reports it"}`,
      h("button", { type: "button", "aria-label": "Open this run's latest receipt", dataset: { modal: "receipt" } }, "↗"));
  } else {
    src.textContent = L ? "No result" : "--";
    det.textContent = L ? (latest?.none ?? "") : "No result selected";
  }
  for (const b of det.querySelectorAll("[data-modal]")) b.addEventListener("click", () => showModal(b.dataset.modal));
  // The field overlay: never without a verified, associated field.
  const field = view ? view.field : { available: false, reason: "Field overlay unavailable: no run" };
  $("heatMode").disabled = !field.available;
  $("heatMode").title = field.available ? "Show the verified field" : field.reason;
  $("fieldNote").textContent = field.available ? "" : field.reason.replace("Field overlay unavailable: ", "Field overlay unavailable · ");
  $("modelNote").replaceChildren(...(renderer === "2d"
    ? ["2D view: this browser can't run the 3D view", h("br"), "Schematic · not manufacturing CAD"]
    : [`Thin layers drawn ×${VIEW.THIN_Z} in z · cooling stack lifted`, h("br"), S.explode > 0 ? "Exploded · spacing not to scale" : "Schematic · not manufacturing CAD"]));
  const words = L ? `${M.runTitle(L)} (${W.visitorType(L.cls)}), ${view.state.toLowerCase()}${view.atRecord ? " at this record" : ""}. ${view.metric ? `${view.metricName} ${view.metric.text} ${view.metric.qualifier}, simulated, not silicon` : view.none}.` : "";
  $("packageCanvas").setAttribute("aria-label", L ? `3D view of the ${CASE_TITLE}: ${words} Arrow keys orbit, plus and minus zoom.` : "No run drawn");
  $("packageCanvas2d").setAttribute("aria-label", L ? `2D drawing of the ${CASE_TITLE}: ${words}` : "No run drawn");
  $("packageCanvas").hidden = renderer === "2d";
  $("packageCanvas2d").hidden = renderer !== "2d";
  if (!L) { draw2d(null); return; }
  if (renderer === "2d") { draw2d(L); return; }
  if (S.v3) { if (!S.drawn || S.drawn.key !== drawKey(L, at)) { const first = !S.drawn; drawPackage(L, view, at); if (first) frameCamera(); } }
  else ensure3d().then(() => renderModel());
}
// The controls the renderer in use supports; the others are disabled and say why.
function applyControls(c) {
  for (const id of ["explodeButton", "explodeRange", "orbitButton", "modelReset"]) {
    const el = $(id);
    const on = id === "orbitButton" ? c.orbit : id === "modelReset" ? c.reset : c.explode;
    el.disabled = !on;
    if (!on) el.title = c.renderer === "2d" ? "3D view only: this browser draws the package in 2D" : "No run drawn";
    else el.removeAttribute("title");
  }
  if (!c.orbit && S.orbit) setOrbit(false);
}
// The 2D fallback: the Package view's own 2D renderer, a hard cut to the selected run's dies (no temperature).
const anim2d = new TrackAnimation();
function draw2d(L) {
  const c = $("packageCanvas2d");
  if (c.hidden && L) return;
  const r = c.getBoundingClientRect(), dpr = Math.min(3, window.devicePixelRatio || 1);
  const w = Math.max(1, Math.round(r.width)), hgt = Math.max(1, Math.round(r.height));
  if (c.width !== Math.round(w * dpr) || c.height !== Math.round(hgt * dpr)) { c.width = Math.round(w * dpr); c.height = Math.round(hgt * dpr); }
  const ctx = c.getContext("2d");
  if (!ctx) return;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const now = performance.now();
  anim2d.reset(L ? { chiplets: M.chiplets2d(L), overlaps: [] } : null, { now });
  const compact = w < 700;
  draw2dPackage(ctx, L ? { ...anim2d.frame(now), footprint: M.FOOTPRINT_2D, unit: "°C", field: null } : null, {
    width: w, height: hgt, azimuthDeg: -45, labels: true, callouts: false, lid: false,
    pad: compact ? { l: 12, r: 12, t: 56, b: 56 } : { l: 24, r: 24, t: 44, b: 40 },
  });
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
      const cx = x - ((row.length - 1) * 11) / 2 + k * 11, cy = y + 19;
      const dot = avatar({ cls: r.cls, short: r.label.split(" · ")[1] ?? null, seq: 0 });
      const size = large ? 16 : 13;
      dot.setAttribute("x", (cx - size / 2).toFixed(1)); dot.setAttribute("y", (cy - size / 2).toFixed(1));
      dot.setAttribute("width", size); dot.setAttribute("height", size);
      dot.setAttribute("class", `av atlas-av${shown && r.id === shown.id ? " sel" : ""}`);
      dot.append(s("title", {}, `${W.layoutFrom(r.label.split(" · ")[1] ?? null)} ${W.RUN_STATE[r.status] ?? r.status}`));
      dot.addEventListener("click", () => selectRun(r.id));
      svg.append(dot);
    });
  });
  return a;
}
function renderWork() {
  renderArrivals();
  const a = drawAtlas($("atlasSvg"));
  $("mapLegend").textContent = `${W.TEXT.mapLegend}${a.out.length ? ` · ${W.TEXT.outOfFlow(a.out.length)}` : ""}`;
  // Keyed on the full run id: two runs with one label are two rows, and door records (no run id) are a qualified label
  // group, never attached to a run (live-model.mjs followWork).
  const { runs, door, anonymous } = M.followWork(feed.state.events, layouts());
  const shown = shownRun().L;
  $("visitorCount").textContent = `${runs.length} RUN${runs.length === 1 ? "" : "S"}`;
  const list = $("visitorList");
  list.replaceChildren();
  for (const r of runs.slice(0, 30)) {
    const task = r.task ? (STATUS_TAG[r.task.state] ?? r.task.state).toLowerCase() : "unknown";
    const where = r.submitted ? W.TEXT.submitted(W.when(r.submitted.at)) : W.TEXT.submittedEarlier;
    const btn = h("button", { type: "button", class: `agent-row${shown && r.run_id === shown.id ? " selected" : ""}`, dataset: { run: r.run_id } },
      h("span", { class: `agent-avatar c-${r.cls}`, "aria-hidden": "true" }, CLASS_MARK[r.cls] ?? "?"),
      h("span", null, h("strong", null, `Run ${r.short}`), h("small", null, `${W.visitorType(r.cls)} · ${r.sameLabel ? `${where} · 1 of ${r.sameLabel + 1} designs with this short id` : where}`)),
      h("span", { class: "agent-task" }, task), h("span", { class: `agent-pip ${r.task ? STATE_PIP(r.task.state) : "grey"}` }));
    btn.addEventListener("click", () => { if (layouts().some((l) => l.id === r.run_id)) selectRun(r.run_id); openRun(r); });
    list.append(btn);
  }
  if (door.length || anonymous.length) list.append(h("p", { class: "door-head" }, W.TEXT.recentVisitors));
  for (const d of door.slice(0, 12)) {
    list.append(h("div", { class: "anon-row" }, h("span", { class: "agent-pip sky" }), h("b", null, W.visitorType(d.cls)),
      `visit ${d.short} · ${W.TEXT.visits(d.arrivals)}${d.attempts ? `, ${W.TEXT.attempts(d.attempts)}` : ""} · ${W.TEXT.lastSeen(W.when(d.last.at))}`));
  }
  for (const a of anonymous) list.append(h("div", { class: "anon-row" }, h("span", { class: "agent-pip sky" }), h("b", null, W.visitorType(a.cls)), `${W.TEXT.noTask(a.count)} · ${W.TEXT.lastSeen(W.when(a.lastAt))}`));
  if (!runs.length && !door.length && !anonymous.length) list.append(h("p", { class: "rail-empty" }, M.feedStatus(feed.state, { hostname: location.hostname }).state === "error" ? "No records: the door feed is not answering." : "No records yet."));
  // The newest record, or the replay cursor's.
  const pts = points();
  const c = M.cursorIndex(pts, S.cursorSeq);
  const p = c === null ? pts.at(-1) : pts[c];
  $("selectedEventLabel").textContent = c === null ? W.TEXT.newest : W.TEXT.replayStep(c + 1, pts.length);
  $("eventTitle").textContent = p ? M.recordTitle(p) : "No record yet";
  $("eventSubtitle").textContent = p ? W.when(p.at) : "Waiting for the door";
  $("eventSubtitle").title = p ? `seq ${p.seq}` : "";
}

// ── who just arrived: the aquarium's avatar (AIdenID live-aquarium Character, ported), a sentence, the visit id ─────
// Cards come from arrival records only (never from a declaration, never joined to a run); a declaration event reads
// "sent a declaration" and carries none of its text. The newest arrival holds the card for ARRIVAL_HOLD_MS after its
// server time, then settles into the strip of the last ~12. Motion is the card's CSS slide-in, off with reduced motion.
const ARRIVAL_HOLD_MS = 10000;
const SKIN = ["#f6d7c3", "#e8b996", "#c98b63", "#9c6644", "#6d4330"];
const HAIR = ["#2b2118", "#5a3a22", "#b5651d", "#d9b26f", "#3a3a3a", "#8c2f39"];
const SHIRT = ["#3d9bff", "#1fdc4d", "#f5a623", "#a274ff", "#ff6b8a", "#2ec4b6"];
const BOT_COLORS = { verified: { body: "#17342f", accent: "#72d5b5" }, inferred: { body: "#3a2a1c", accent: "#e5b18a" },
  automation: { body: "#3a1f1c", accent: "#f08b7c" }, crawler: { body: "#1c2d3a", accent: "#7cc4f0" }, neutral: { body: "#1c2d3a", accent: "#9fc2d8" } };
function hashOf(seed) { let x = 2166136261; for (const ch of String(seed)) { x ^= ch.charCodeAt(0); x = Math.imul(x, 16777619) >>> 0; } return x; }
function avatar(a) {
  const svg = s("svg", { class: "av", viewBox: "0 0 64 64", fill: "none", "aria-hidden": "true" });
  const add = (tag, attrs) => svg.append(s(tag, attrs));
  add("ellipse", { cx: 32, cy: 58, rx: 15, ry: 3, fill: "currentColor", opacity: ".16" });
  const verified = a.verification === "signature" || a.verification === "network" || (!a.verification && a.cls === "verified_agent");
  if (a.cls === "likely_human") {
    const hsh = hashOf(a.short ?? a.seq), style = Math.floor(hsh / 199) % 3;
    add("path", { d: "M13 56c1-11 9-17 19-17s18 6 19 17c0 1-1 2-2 2H15c-1 0-2-1-2-2Z", fill: SHIRT[Math.floor(hsh / 61) % SHIRT.length] });
    add("circle", { cx: 32, cy: 24, r: 12, fill: SKIN[hsh % SKIN.length] });
    const hair = HAIR[Math.floor(hsh / 7) % HAIR.length];
    add("path", { d: style === 0 ? "M20 23c0-9 5-14 12-14s12 5 12 14c-2-4-6-6-12-6s-10 2-12 6Z" : style === 1 ? "M19 26c0-11 6-16 13-16s13 5 13 16v6c-3-5-7-7-13-7s-10 2-13 7Z"
      : "M21 21c1-6 5-10 11-10s10 4 11 10c-3-2-7-3-11-3s-8 1-11 3Z", fill: hair });
    add("circle", { cx: 27.5, cy: 25, r: 1.6, fill: "#1f2a2e" });
    add("circle", { cx: 36.5, cy: 25, r: 1.6, fill: "#1f2a2e" });
    add("path", { d: "M28 30c2 2 6 2 8 0", stroke: "#1f2a2e", "stroke-width": 1.6, "stroke-linecap": "round" });
    return svg;
  }
  if (a.cls === "unknown") {
    add("path", { d: "M32 9c-12 0-19 10-19 23v22h38V32c0-13-7-23-19-23Z", fill: "#2a2414", stroke: "#f2d479", "stroke-width": 1.5 });
    add("ellipse", { cx: 32, cy: 31, rx: 9, ry: 10, fill: "#120f08" });
    add("path", { d: "M29 27a3 3 0 1 1 4.5 2.6c-1 .6-1.5 1.2-1.5 2.4M32 36v.5", stroke: "#f2d479", "stroke-width": 1.8, "stroke-linecap": "round" });
    return svg;
  }
  // Every automated visitor: the aquarium's robot. Its colour says what is known: verified, a script, or (declared
  // and crawler-claimed classes, which today's feeds cannot tell apart) neutral.
  const c = verified ? BOT_COLORS.verified : a.cls === "automation" ? BOT_COLORS.automation : BOT_COLORS.neutral;
  add("path", { d: "M32 8v5", stroke: c.accent, "stroke-width": 2, "stroke-linecap": "round" });
  add("circle", { cx: 32, cy: 6, r: 2.6, fill: c.accent });
  add("rect", { x: 16, y: 13, width: 32, height: 24, rx: 7, fill: c.body, stroke: c.accent, "stroke-width": 1.5 });
  add("rect", { x: 22, y: 21, width: 7, height: 6, rx: 1.5, fill: c.accent });
  add("rect", { x: 35, y: 21, width: 7, height: 6, rx: 1.5, fill: c.accent });
  add("path", { d: "M25 32h14M29 30v4M35 30v4", stroke: c.accent, "stroke-width": 1.6, "stroke-linecap": "round" });
  add("path", { d: "M20 40h24a4 4 0 0 1 4 4v10H16V44a4 4 0 0 1 4-4Z", fill: c.body, stroke: c.accent, "stroke-width": 1.2 });
  add("circle", { cx: 32, cy: 47, r: 2.5, fill: c.accent });
  if (a.category === "training_crawler" || a.category === "search_crawler") {
    add("circle", { cx: 52, cy: 46, r: 5, stroke: c.accent, "stroke-width": 1.8, fill: "none" });
    add("path", { d: "m55.5 49.5 4 4", stroke: c.accent, "stroke-width": 2, "stroke-linecap": "round" });
  }
  if (verified) { add("circle", { cx: 52, cy: 14, r: 8, fill: "#102a27", stroke: "#72d5b5" }); add("path", { d: "m49 14 2 2 4-4", stroke: "#72d5b5", "stroke-width": 2, "stroke-linecap": "round" }); }
  else { add("circle", { cx: 52, cy: 14, r: 8, fill: "#1f2a2e", stroke: "#a9b4b4", "stroke-width": 1.5, "stroke-dasharray": "2.6 1.8" }); add("path", { d: "M48.5 14h7", stroke: "#d9e0e0", "stroke-width": 2, "stroke-linecap": "round" }); }
  return svg;
}
let cardSeq = null;
function renderArrivals() {
  const list = M.arrivalsOf(feed.state.events, 13);
  const now = Date.now();
  const newest = list[0];
  const fresh = newest && newest.at && now - Date.parse(newest.at) <= ARRIVAL_HOLD_MS;
  const card = $("arrivalCard");
  card.hidden = !fresh;
  if (fresh && cardSeq !== newest.seq) {
    cardSeq = newest.seq;
    card.replaceChildren(avatar(newest), h("p", null, W.arrivalSentence(newest, now), h("small", null, W.arrivalDetail(newest))));
  } else if (fresh) {
    card.querySelector?.("p")?.firstChild && (card.querySelector("p").firstChild.textContent = W.arrivalSentence(newest, now));
  }
  const strip = (fresh ? list.slice(1) : list).slice(0, 12);
  $("arrivalStrip").replaceChildren(...strip.map((a) => h("div", { class: "av-item", role: "listitem", title: `${W.arrivalSentence(a, now)} · ${W.arrivalDetail(a)}` },
    avatar(a), h("span", null, a.short ? `visit ${a.short}` : W.visitorType(a.cls)), h("span", null, W.when(a.at, now)))));
  $("arrivals").hidden = list.length === 0;
  $("arrivalsHead").textContent = W.ARRIVALS_HEAD;
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
  // A trail joins consecutive records of one full run id (live-model.mjs traceLinks): never across runs, never from a
  // door record to a run, and never on a label, which can repeat.
  const bySeq = new Map(pts.map((p) => [p.seq, p]));
  for (const [from, to] of M.traceLinks(feed.state.events)) {
    const p0 = bySeq.get(from), p1 = bySeq.get(to);
    if (!p0 || !p1) continue;
    const [px, py, x, y] = [xOf(p0), ys[p0.lane], xOf(p1), ys[p1.lane]];
    svg.append(s("path", { d: `M${px} ${py} C${px + 18} ${py},${x - 18} ${y},${x} ${y}`, stroke: LANE_COLOR.run, "stroke-width": 0.8, fill: "none", opacity: 0.45 }));
  }
  const c = M.cursorIndex(pts, S.cursorSeq);
  pts.forEach((p, i) => {
    const g = s("g", { class: "trace-pt", tabindex: -1, dataset: null });
    g.dataset.index = String(i);
    const cx = xOf(p), cy = ys[p.lane];
    g.append(s("rect", { x: cx - 6, y: cy - 10, width: 12, height: 20, fill: "transparent" }),
      s("circle", { cx, cy, r: c === i ? 4.5 : 3, fill: LANE_COLOR[p.kind], opacity: c !== null && i > c ? 0.3 : 1 }),
      s("title", {}, `${M.recordTitle(p)} · seq ${p.seq} · ${M.hms(p.at)}`));
    g.addEventListener("click", () => { setCursor(i); openRecord(i); });
    svg.append(g);
  });
  $("traceStart").textContent = first ? W.TEXT.traceOldest(W.when(first.at)) : "NOTHING YET";
  $("traceEnd").textContent = last ? W.TEXT.traceNewest(W.when(last.at)) : "";
  const ph = $("playhead");
  ph.hidden = c === null;
  if (c !== null) ph.style.left = `${xOf(pts[c])}px`;
  const range = $("replayRange");
  range.max = String(Math.max(0, pts.length - 1));
  range.disabled = pts.length === 0;
  range.value = String(c ?? Math.max(0, pts.length - 1));
  range.setAttribute("aria-valuetext", pts.length ? `record ${(c ?? pts.length - 1) + 1} of ${pts.length}` : "no records");
  const tc = $("timecode");
  tc.replaceChildren(c === null ? (last ? W.TEXT.timecodeLive(W.when(last.at)) : "--") : W.TEXT.timecodeReplay(c + 1, pts.length, W.when(pts[c].at)),
    h("span", null, c === null ? "" : " · recorded"));
  $("followLive").setAttribute("aria-pressed", c === null ? "true" : "false");
  $("transportNote").textContent = c === null ? "Live: following the newest record. Replay plays only when you choose it." : "Replay of records already received, at their original times";
  $("play").innerHTML = icon(S.playing ? "pause" : "play");
  $("play").setAttribute("aria-label", S.playing ? "Pause the replay" : "Replay the recorded records");
  // Phones: a readable list of the newest records.
  const ml = $("mobileEventList");
  ml.replaceChildren(...pts.slice(-12).reverse().map((p) => {
    const i = pts.indexOf(p);
    const b = h("button", { type: "button" }, h("span", null, W.when(p.at)), h("strong", null, M.recordTitle(p)), h("b", { "aria-hidden": "true" }, "↗"));
    b.addEventListener("click", () => { setCursor(i); openRecord(i); });
    return b;
  }));
}

// ── interaction ────────────────────────────────────────────────────────────────────────────────────────────────────
function selectRun(id) { S.selectedId = id; if (S.cursorSeq !== null) { S.cursorSeq = null; stopPlay(); } render(); }
// The replay cursor is held as a record's seq (live-model.mjs cursorIndex): new records never move a paused cursor.
function setCursor(i) { const pts = points(); const c = M.clampCursor(i, pts.length); S.cursorSeq = c === null ? null : pts[c].seq; render(); }
const cursorIdx = () => M.cursorIndex(points(), S.cursorSeq);
function followLive() { stopPlay(); S.cursorSeq = null; S.selectedId = null; render(); }
function stopPlay() { S.playing = false; clearTimeout(S.playTimer); }
function play() {
  const n = points().length;
  if (!n) return;
  if (!S.motion) setMotion(true);   // choosing to play is choosing motion
  const at = cursorIdx();
  if (at === null || at >= n - 1) S.cursorSeq = points()[0].seq;
  S.playing = true;
  const tick = () => {
    if (!S.playing) return;
    const m = points().length;
    const i = cursorIdx();
    if (i === null || i >= m - 1) { stopPlay(); render(); return; }
    S.cursorSeq = points()[i + 1].seq;
    render();
    S.playTimer = setTimeout(tick, REDUCED ? 2000 : 1200);
  };
  render();
  S.playTimer = setTimeout(tick, REDUCED ? 2000 : 1200);
}
function setExplode(v, { animate = false } = {}) {
  cancelAnimationFrame(S.explodeAnim);
  const to = Math.max(0, Math.min(1, v));
  // The control states the chosen setting at once; only the drawing eases toward it.
  $("explodeButton").setAttribute("aria-pressed", to > 0.02 ? "true" : "false");
  $("explodeWord").textContent = to > 0.02 ? "Exploded" : "Assembled";
  const apply = (x) => {
    S.explode = x;
    $("explodeRange").value = String(Math.round(x * 100));
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
  openDialog(M.recordTitle(p), `RECORD ${i + 1} OF ${points().length} · ${p.kind.toUpperCase()}`,
    lead("One record as the door's events feed returned it, after the page's checks. The time is the server's own; the label is a classification and a short id, never a name."),
    table([["What happened", M.recordTitle(p)], ["When", p.at ? W.localTime(Date.parse(p.at)) : "not recorded"], ["Visitor type", W.visitorType(String(p.label).split(" · ")[0])],
      ["Page route", "not recorded: the door's events carry no page route", "unknown"], ["Identity", "not established: a class is an observation, not an identity", "unknown"]]),
    h("pre", { class: "json-block" }, JSON.stringify(e ?? p, null, 2)));
}
function openRun(r) {
  const L = layouts().find((l) => l.id === r.run_id) ?? null;
  openDialog(`Run ${r.short}`, `RUN · ${M.visitorType(r.cls).toUpperCase()} · KEYED ON ITS FULL RUN ID`,
    lead(`${CLASS_NOTE[r.cls] ?? "A classification, not an identity."} The label is a class and a 4-character short id; short ids can repeat, so this page never joins two runs, or a run and the door's other records, on it.`),
    h("div", { class: "modal-grid" },
      h("div", { class: "modal-card" }, h("span", { class: "label" }, "SUBMITTED (WHERE THE DOOR SAW IT ACT)"), h("h3", null, r.submitted ? `submitted · ${r.submitted.state}` : "unknown"),
        h("p", null, r.submitted ? W.TEXT.submitted(W.when(r.submitted.at)) : W.TEXT.submittedEarlier),
        h("p", null, "The scorer's later work changes the run's state, not where its submitter was.")),
      h("div", { class: "modal-card" }, h("span", { class: "label" }, "TASK (RUN STATE)"), h("h3", null, r.task ? (STATUS_TAG[r.task.state] ?? r.task.state).toLowerCase() : "unknown"),
        h("p", null, r.task && r.task.seq >= 0 ? W.when(r.task.at) : "from the results list"),
        h("p", null, L ? stateLine(L) ?? L.status : "This run is not in the results list."))),
    table([["Other runs with this label", r.sameLabel ? `${r.sameLabel}: shown as separate rows, never merged` : "none in view"],
      ["Presence now", "unknown: the door does not publish presence to this page", "unknown"], ["Page route", "not recorded", "unknown"],
      ["Identity", "not established (classification only)", "unknown"], ["Records of this run in the newest window", String(r.records)]]));
}
function showModal(kind) {
  const { L, at } = shownRun();
  if (kind === "receipt" || kind === "evidence") {
    const rc = M.receiptOf(L);
    const v = M.runView(L);
    const cursorNote = at ? `The replay cursor is at record ${at.seq ?? "?"} (${String(at.state).replace(/_/g, " ")}). This is the run's LATEST receipt, not its state at the cursor.` : "";
    openDialog(L ? M.runTitle(L) : "No run selected", at ? "LATEST RECEIPT · NOT THE STATE AT THE CURSOR" : kind === "receipt" ? "RECEIPT · AS THE FEED REPORTS IT" : "EVIDENCE",
      at ? note(cursorNote, true) : "",
      lead("Every number here is the scorer's, as the door's results feed reports it, for this run's own record. The page shows it; it does not recompute or verify it."),
      L ? table([["Board metric", v.metric ? `${v.metric.text} · ${W.tempWord(v.metric)}${v.diagnostic ? " · diagnostic" : ""}` : v.none],
        ["Definition", v.metricDefinition], ...v.distinct.map((d) => [`${d.name} (a different statistic)`, `${d.text.text} · ${W.tempWord(d.text)}`]),
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
      h("div", null, pts.map((p, i) => { const b = h("button", { type: "button", class: "event-list-row" }, h("span", null, W.when(p.at)), h("span", null, ""), h("strong", null, M.recordTitle(p))); b.addEventListener("click", () => { setCursor(i); openRecord(i); }); return b; })));
  } else if (kind === "sources") {
    openDialog("What is real on this page?", "SOURCES & SCOPE",
      h("ul", { class: "modal-list" },
        h("li", null, h("span", { class: "step-no" }, "01"), h("div", null, h("strong", null, "The door's runs and results"), h("p", null, "GET /api/open/v1/door/results: each run's eight dies and, once scored, the scorer's board metric and the checks it reports. Simulated by HotSpot 6.0 on the model stack; not silicon."))),
        h("li", null, h("span", { class: "step-no" }, "02"), h("div", null, h("strong", null, "The door's records"), h("p", null, "GET /api/open/v1/door/events: arrivals, refused attempts and run state changes, with server times."))),
        h("li", null, h("span", { class: "step-no" }, "03"), h("div", null, h("strong", null, "The board"), h("p", null, "GET /api/open/v1/door/board: whether the door is open, the queue and the compute budget."))),
        h("li", null, h("span", { class: "step-no" }, "04"), h("div", null, h("strong", null, "Self-declared visitors"), h("p", null, "GET /api/open/v1/door/visitors: a name, reason and source a visitor chose to publish. Shown as written, as text, clipped to 64 and 160 characters, and never verified. A declaration the operator hid reads \"hidden by the operator\".")))),
      note("Geometry and layer thicknesses come from the model stack the solver simulates (the Package view's model). Layer heights are drawn thicker than true where marked; explode spacing is display only."),
      note(NOTICE, true));
  } else {
    openDialog("One workspace. Three ways to read it.", "HOW TO READ THIS LAB",
      h("ol", { class: "modal-list" },
        h("li", null, h("span", { class: "step-no" }, "01"), h("div", null, h("strong", null, "The physical model."), h("p", null, "Each run's eight dies on the CPU-DRAM package, from its own record. Drag to orbit, explode the layers (display only), select a layer to read its true thickness."))),
        h("li", null, h("span", { class: "step-no" }, "02"), h("div", null, h("strong", null, "The work."), h("p", null, "The door's stations and the visitors' short ids, from the door's own records. Unknown stays unknown."))),
        h("li", null, h("span", { class: "step-no" }, "03"), h("div", null, h("strong", null, "The flight record."), h("p", null, "The newest records, in order. Replay one only when you choose to; LIVE returns to the newest.")))),
      note("No temperature colours are drawn: the door's results carry a scalar, not a temperature field. Every temperature is simulated and diagnostic, not measured on real chips."));
  }
}
function closeDialog() { $("modal").close(); }

// ── wiring ─────────────────────────────────────────────────────────────────────────────────────────────────────────
function wire() {
  hydrateIcons();
  $("wnotice").textContent = NOTICE;
  $("tempLine").textContent = W.TEMP_LINE;
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
  $("step").addEventListener("click", () => { stopPlay(); const n = points().length; if (n) { const i = cursorIdx(); setCursor(i === null ? 0 : Math.min(n - 1, i + 1)); } });
  $("replayRange").addEventListener("input", (e) => { stopPlay(); setCursor(Number(e.target.value)); });
  $("followLive").addEventListener("click", followLive);
  $("selectedEvent").addEventListener("click", () => { const n = points().length; if (n) openRecord(cursorIdx() ?? n - 1); });
  for (const b of $$("[data-mobile]")) b.addEventListener("click", () => setMobile(b.dataset.mobile));
  $("brand").addEventListener("click", () => showIntro());
  $("replayIntro").addEventListener("click", () => showIntro());
  $("skipIntro").addEventListener("click", hideIntro);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { hideIntro(); if (S.stage && !$("modal").open) setStage(false); }
  });
  document.addEventListener("visibilitychange", () => { if (document.hidden) stopPlay(); else pollBoard(); });
  new ResizeObserver(() => renderTrace()).observe($("traceSvg"));
  new ResizeObserver(() => { frameCamera(); if (!$("packageCanvas2d").hidden) draw2d(shownRun().L); }).observe($("modelViewport"));
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
    const got = await M.fetchBoard({ fetchImpl: gate.fetch });
    if (mine !== boardEpoch) return;
    S.board = got.ok ? { ok: true, board: got.board, error: "", at: Date.now() } : { ...S.board, ok: false, error: got.error };
    renderStatus();
  }
  boardTimer = setTimeout(pollBoard, M.BOARD_POLL_MS);
}
// The self-declared visitor text: the whole window, every VISITORS_POLL_MS, replacing what the page holds (a hide
// reaches this tab on its next poll). Skipped while the tab is hidden; an API without the feed (404) is asked again a
// minute later. Declarations whose last good read is older than VISITORS_FRESH_MS are not shown.
let visitorsTimer = 0, visitorsEpoch = 0;
async function pollVisitors() {
  clearTimeout(visitorsTimer);
  const mine = ++visitorsEpoch;
  let next = M.VISITORS_POLL_MS;
  if (!document.hidden) {
    const latest = Math.max(feed.state.eventsCursor ?? 0, S.decl.through ?? 0);
    const got = await M.fetchVisitorsWindow({ fetchImpl: gate.fetch, latest });
    if (mine !== visitorsEpoch) return;
    if (got.ok) S.decl = { ok: true, partial: got.partial, list: M.declarationList(got.items), error: "", at: Date.now(), through: got.through ?? S.decl.through };
    else { S.decl = { ...S.decl, ok: false, list: [], error: got.error }; if (got.error === "answered 404") next = M.VISITORS_SLOW_MS; }
    renderDeclarations();
  }
  visitorsTimer = setTimeout(pollVisitors, next);
}
// The declarations list (live-model.mjs declarationList): its own list, newest first, never attached to a run, with
// explicit states: unavailable (the last read failed, or the last good read is too old to show: a hide may be missed,
// so no declared text is shown or kept), partial (the window was not read to its end), none, or the entries. Entries
// show only while the last read succeeded AND is fresh (a failed refresh drops the held list at once).
function renderDeclarations() {
  const d = S.decl, box = $("declList");
  const fresh = d.at && Date.now() - d.at <= M.VISITORS_FRESH_MS;
  const n = M.VISITORS_WINDOW.toLocaleString("en-US");
  box.hidden = d.ok === null;
  if (d.ok !== true || !fresh) {
    box.replaceChildren(h("p", { class: "decl-head" }, d.ok === false && d.error === "answered 404" ? "DECLARATIONS · NOT AVAILABLE ON THIS API"
      : `DECLARATIONS · UNAVAILABLE${d.error ? ` · ${d.error.toUpperCase()}` : ""}`));
    return;
  }
  const head = d.list.length ? W.TEXT.declarationsHead(n) : W.TEXT.declarationsNone();
  box.replaceChildren(h("p", { class: "decl-head" }, head),
    ...(d.partial ? [h("p", { class: "decl-head warn" }, "PARTIAL · NOT ALL OF THE WINDOW COULD BE READ; SOME NEWER DECLARATIONS MAY BE MISSING")] : []),
    ...d.list.map((x) => declBlock(x.view, x)));
}
// One declaration as plain text nodes (never markup, never an attribute), bidi-isolated, clipped by live-model.mjs,
// with its own time and seq.
function declBlock(v, x) {
  if (!v) return null;
  const when = h("small", { title: `seq ${x.seq}` }, W.when(x.at));
  if (v.kind !== "declared") return h("div", { class: "decl hidden" }, v.text, when);
  return h("div", { class: "decl" }, h("b", null, h("bdi", null, v.name === "" ? "(no name given)" : v.name)),
    v.reason ? h("span", null, h("bdi", null, v.reason)) : null, v.source ? h("span", null, `source: ${v.source}`) : null, when, h("em", null, v.note));
}

wire();
render();
try { if (!sessionStorage.getItem("sentilab-intro-seen")) showIntro(); } catch { /* storage off: no entrance */ }
feed.start();
pollBoard();
pollVisitors();
// The badge and ages follow the clock even when no answer arrives (a hung request must still turn LIVE into STALE).
setInterval(() => { renderStatus(); renderDeclarations(); renderArrivals(); }, 1000);
// Leaving the page stops every poll (and an answer still in flight cannot restart one: the board's epoch moves on). A
// page restored from the back/forward cache comes back with them stopped, so pageshow starts again what pagehide
// stopped; a fresh load gets no pageshow with persisted set.
window.addEventListener("pagehide", () => { feed.stop(); boardEpoch += 1; clearTimeout(boardTimer); visitorsEpoch += 1; clearTimeout(visitorsTimer); stopPlay(); });
window.addEventListener("pageshow", (e) => { if (e.persisted) { feed.start(); pollBoard(); pollVisitors(); renderStatus(); } });
