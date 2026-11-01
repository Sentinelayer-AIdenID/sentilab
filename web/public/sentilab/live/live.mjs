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
import { readBodyCapped, MAX_API_BYTES } from "../view-core.mjs";

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
  records: new Map(), recTab: "all", recLoading: false, recWhat: "", recError: "", cover: [], gapRetryAt: 0,
  board: { ok: null, board: null, error: "", at: null }, decl: { ok: null, partial: false, list: [], error: "", at: null, through: 0 }, v3: null, v3Failed: false, v3Pending: null, drawn: null, layer: null,
};
// One gate for every request the page makes: spacing, Retry-After and jittered backoff (live-model.mjs createGate).
const gate = M.createGate();
// Each results page the feed reads is also kept as the feed returned it (newest row per run id), so a package for
// engineers copies the feed exactly; the same gated request, read once more under the same size cap.
const rawResults = new Map();
async function feedFetch(url, init) {
  const r = await gate.fetch(url, init);
  if (r?.status === 200 && String(url).includes(M.RESULTS_PATH) && typeof r.clone === "function") {
    try {
      const body = await readBodyCapped(r.clone(), MAX_API_BYTES, "too_large");
      if (body.ok) M.keepRawResults(rawResults, JSON.parse(new TextDecoder().decode(body.bytes)));
    } catch { /* the feed reports its own read errors */ }
  }
  return r;
}
const feed = createDoorFeed({ onChange: () => render(), fetchEvents: M.fetchEventsTimed, fetchImpl: feedFetch });

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
  return { L: S.selectedId == null ? M.followedRun(layouts()) : M.pickRun(layouts(), S.selectedId), at: null };
}

// ── live runs walk through their recorded steps ──────────────────────────────────────────────────────────────────
// The step map draws a run at its latest step. A run first seen live whose several step records arrive in one poll
// (a run can go from queued to reproduced inside one 3 s poll) walks through each recorded step in order instead,
// WALK_STEP_MS apiece, each with its plain word, then rests at its real latest step. Runs held when the page first
// read the door never walk; reduced motion, paused motion or a tab that was hidden jumps at once; a poll that brings
// newer records ends a walk at once and continues from the real latest state.
const walks = new Map();          // run id -> { steps, i }
const walkSeen = new Map();       // run id -> its newest run-record seq already drawn
let walkHistory = null, walkBase = 0, walkCursor = 0, walkTimer = 0, walkEpoch = 0, hiddenSincePoll = false;
// Ends every walk: its timer is cleared and its epoch ended, so a callback already queued does nothing.
function cancelWalks() { walkEpoch += 1; walks.clear(); clearTimeout(walkTimer); walkTimer = 0; }
// Pause all motion, a hidden tab and pagehide end a walk at once and redraw the latest state (root, 0ba078e P2 1).
function stopWalks() { const had = walks.size > 0; cancelWalks(); if (had) drawMaps(); }
// "New proposal" at the top of the model (Carter, 19:33Z: when an agent finishes and proposes, it shows at the top of
// the 3D space and says new proposal): while following live, a change of the followed run to another one
// shows the badge for NEW_PROPOSAL_MS. The run followed at load is never new; a viewer's own pick never shows it.
const NEW_PROPOSAL_MS = 15000;
let followedId, newProposalUntil = 0, newProposalTimer = 0;   // followedId: undefined until the first answered read
// The badge ends at its own deadline: a timer hides it then even if no later render runs, as when reads hang
// (root, 2aab3e2 P2 2). pagehide ends it too.
function showNewProposal() {
  newProposalUntil = Date.now() + NEW_PROPOSAL_MS;
  $("newProposal").hidden = false;
  clearTimeout(newProposalTimer);
  newProposalTimer = setTimeout(endNewProposal, NEW_PROPOSAL_MS);
}
function endNewProposal() { clearTimeout(newProposalTimer); newProposalTimer = 0; newProposalUntil = 0; $("newProposal").hidden = true; }
function planWalks() {
  const ev = feed.state.events;
  if (walkHistory === null) {
    if (!feed.state.lastOkAt) return;
    walkHistory = new Set([...layouts().map((L) => L.id), ...ev.filter((e) => e.kind === "run").map((e) => e.run_id)]);
    for (const id of walkHistory) seenAt.set(id, null);
    walkBase = walkCursor = feed.state.eventsCursor ?? 0;
    return;
  }
  const moved = (feed.state.eventsCursor ?? 0) > walkCursor;
  if (moved) { walkCursor = feed.state.eventsCursor; cancelWalks(); }
  const still = REDUCED || !S.motion || document.hidden || hiddenSincePoll;
  if (moved) hiddenSincePoll = Boolean(document.hidden);
  // A run's records can arrive a poll before its result (two feeds, two requests): its walk waits until it can be drawn.
  const drawable = new Set(layouts().map((L) => L.id));
  const fresh = new Set(ev.filter((e) => e.kind === "run" && e.seq > (walkSeen.get(e.run_id) ?? walkBase) && drawable.has(e.run_id)).map((e) => e.run_id));
  for (const id of fresh) {
    const steps = M.walkSteps(ev, id, walkSeen.get(id) ?? walkBase);
    if (steps.length) walkSeen.set(id, steps[steps.length - 1].seq);
    if (!still && !walkHistory.has(id) && steps.length >= 2) walks.set(id, { steps, i: 0 });
  }
  if (walks.size && !walkTimer) scheduleWalk();
}
function scheduleWalk() { const mine = walkEpoch; walkTimer = setTimeout(() => stepWalks(mine), M.WALK_STEP_MS); }
function stepWalks(mine) {
  if (mine !== walkEpoch) return;
  walkTimer = 0;
  for (const [id, w] of walks) { w.i += 1; if (w.i >= w.steps.length) walks.delete(id); }
  drawMaps();
  if (walks.size) scheduleWalk();
}
const walkAt = () => (walks.size ? new Map([...walks].map(([id, w]) => [id, w.steps[w.i]])) : null);

// ── proposals: one row per run, newest at top (Carter, 19:59Z) ────────────────────────────────────────────────────
// The visitor's figure, "Proposal from visit 9f8c" (or, only through the run record's exact visit_arrival, the
// declared name with its note), "✓ Proposal received" once the door's intake accepted it (root, 20:01Z; a run
// refused at intake shows the refusal mark and reason instead), the evaluation's real step or outcome on its own line,
// when it was submitted (its first record's own time, never a poll time), and "New proposal" for PROPOSAL_NEW_MS after
// it first arrived live. Runs held at the first read are never new. Relative times and the badge's end follow the
// page's 1 s clock. A click selects the run by its full run id.
const PROPOSAL_NEW_MS = 15 * 60 * 1000;
const seenAt = new Map();          // run id -> when it was first seen live (null: held at the first read)
function markSvg(kind) {
  const el = s("svg", { class: `proposal-mark ${kind}`, viewBox: "0 0 24 24", "aria-hidden": "true" });
  const path = s("path", { d: kind === "received" ? "M5 12.5l4.5 4.5L19 7.5" : "M7 7l10 10M17 7L7 17" });
  el.append(path);
  return el;
}
// The selected proposal's linked activity: recent or not, by the newest record on its exact links (never a claim that
// the agent is still here),
// or only this run's last record when the run carries no visit_arrival. Shown on the model and on its timeline row.
function presenceText(L, now = Date.now()) {
  const decl = S.decl.ok === true && S.decl.at && now - S.decl.at <= M.VISITORS_FRESH_MS ? S.decl.items ?? [] : [];
  const act = M.agentActivity(L.id, [...S.records.values(), ...feed.state.events], decl);
  if (!act) return null;
  const t = W.ago(act.at, now);
  return !act.bound ? W.PRESENCE.runOnly(t) : now - act.at <= M.AGENT_HERE_MS ? W.PRESENCE.here(t) : W.PRESENCE.gone(t);
}
function presenceLine(L, now, cls) {
  const text = presenceText(L, now);
  return text ? h("small", { class: cls, title: W.PRESENCE.title }, text) : null;
}
function renderPresence() {
  const L = shownRun().L, el = $("modelPresence");
  const text = L ? presenceText(L) : null;
  el.textContent = text ?? "";
  el.hidden = !text;
  if (text) el.setAttribute("title", W.PRESENCE.title); else el.removeAttribute("title");
}
// Downloads: a Blob and a temporary <a download>; no network call.
function download(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = h("a", { href: url, download: name, hidden: true });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function downloadPackage(runId) {
  const raw = rawResults.get(runId);
  if (!M.packageable(raw)) return;
  const pkg = M.engineerPackage(raw, { submittedAt: M.proposedAt(runId, [...S.records.values(), ...feed.state.events]),
    pageUrl: location.href ?? null, generatedAt: new Date().toISOString() });
  download(M.packageName(raw), `${JSON.stringify(pkg, null, 2)}\n`, "application/json");
}
function downloadTop() {
  const { json, csv } = M.topBundle([...rawResults.values()], { pageUrl: location.href ?? null, generatedAt: new Date().toISOString() });
  if (!json.layouts.length) return;
  download("sentilab-top-layouts.json", `${JSON.stringify(json, null, 2)}\n`, "application/json");
  download("sentilab-top-layouts.csv", csv, "text/csv");
}
function renderPackageButton() {
  const L = shownRun().L, b = $("packageButton");
  const ok = Boolean(L) && M.packageable(rawResults.get(L.id));
  b.hidden = !ok;
  b.setAttribute("title", W.PACKAGE.title);
}
function renderProposals() {
  const box = $("proposalList");
  if (!box) return;
  const now = Date.now();
  if (walkHistory !== null) for (const L of layouts()) if (!seenAt.has(L.id)) seenAt.set(L.id, now);
  const list = M.runsNewestFirst(layouts());
  const shown = shownRun().L;
  const names = namesNow();
  const records = [...S.records.values(), ...feed.state.events];
  box.replaceChildren(...list.flatMap((L) => {
    const name = M.runName(L, feed.state.events, names);
    const at = M.proposedAt(L.id, records);
    const o = M.runOutcome(L), mark = M.proposalMark(L);
    const since = seenAt.get(L.id);
    const fresh = since !== null && since !== undefined && now - since < PROPOSAL_NEW_MS;
    const row = h("button", { type: "button", class: `proposal${shown && shown.id === L.id ? " selected" : ""}`, dataset: { run: L.id } },
      avatar({ cls: L.cls, short: L.short, seq: 0 }),
      h("span", { class: "proposal-main" },
        h("span", { class: "proposal-who" }, ...(name === null ? [W.PROPOSALS.from(L.short)] : [h("bdi", null, name), W.PROPOSALS.named(L.short)]),
          fresh ? h("span", { class: "new-proposal small" }, W.PROPOSALS.fresh) : null),
        mark === "received"
          ? [h("small", { class: "proposal-received", title: W.PROPOSALS.receivedTitle }, markSvg("received"), W.PROPOSALS.received),
            h("small", { class: `outcome ${o.kind}`, title: o.title }, o.text)]
          : h("small", { class: "proposal-refused", title: o.title }, markSvg("refused"), o.text),
        h("small", { class: "proposal-when" }, at ? W.when(at, now) : W.TEXT.submittedEarlier),
        shown && shown.id === L.id ? presenceLine(L, now, "proposal-presence") : null));
    row.addEventListener("click", () => selectRun(L.id));
    // The selected proposal, once accepted with a matching replay, can be packaged for engineers.
    const raw = rawResults.get(L.id);
    if (!(shown && shown.id === L.id && M.packageable(raw))) return [row];
    const pack = h("button", { type: "button", class: "engineer-package text-button", title: W.PACKAGE.title }, W.PACKAGE.button);
    pack.addEventListener("click", () => downloadPackage(L.id));
    return [row, pack];
  }));
  const top = $("topLayouts");
  top.hidden = ![...rawResults.values()].some(M.packageable);
  top.setAttribute("title", W.PACKAGE.topTitle);
  if (!list.length) box.append(h("p", { class: "rail-empty" }, W.PROPOSALS.none));
  $("proposalsHead").textContent = W.PROPOSALS.head;
}

function render() {
  planWalks();
  renderStatus();
  renderRuns();
  renderProposals();
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

// A run's title: by its visit id; by a declared name only through its own record's visit_arrival (exact), with the note.
function runTitleParts(L, names = namesNow()) {
  const name = M.runName(L, feed.state.events, names);
  return name === null ? [M.runTitle(L)] : [h("bdi", null, name), W.namedLayout(L)];
}
function runCard(L, selected, { mobile = false } = {}) {
  const v = M.runView(L);
  const btn = h("button", { type: "button", class: mobile ? (selected ? "selected" : "") : `experiment${selected ? " selected" : ""}`, "aria-pressed": selected ? "true" : "false", dataset: { run: L.id } });
  if (mobile) {
    btn.append(...runTitleParts(L), h("small", null, v.metric ? `${v.metric.text} · ${W.tempWord(v.metric, v.verification)}` : (STATUS_TAG[L.status] ?? L.status).toLowerCase()),
      h("small", { class: "vt" }, W.visitorType(L.cls)));
  } else {
    btn.append(h("span", { class: "experiment-tag" }, STATUS_TAG[L.status] ?? L.status),
      h("strong", null, runTitleParts(L)), h("small", { class: "vt" }, W.visitorType(L.cls)),
      h("small", { class: `outcome ${M.runOutcome(L).kind}`, title: M.runOutcome(L).title }, M.runOutcome(L).text),
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
  const runNamed = L ? M.runName(L, feed.state.events, namesNow()) : null;
  if (L) $("modelTitle").replaceChildren(...runTitleParts(L)); else $("modelTitle").textContent = "A closer look at the package.";
  const following = S.selectedId == null && S.cursorSeq == null;
  // The first answered read sets what the page follows, even with no run yet, so the first proposal after an empty
  // start is new too (root, 2aab3e2 P2 1).
  if (following && feed.state.lastOkAt) { if (followedId !== undefined && L && L.id !== followedId) showNewProposal(); followedId = L ? L.id : null; }
  $("newProposal").hidden = !(L && following && Date.now() < newProposalUntil);
  $("modelSub").textContent = L ? W.visitorType(L.cls) : "";
  const lastRun = L ? [...feed.state.events].filter((e) => e.kind === "run" && e.run_id === L.id).sort((x, y) => y.seq - x.seq)[0] : null;
  renderPresence();
  renderPackageButton();
  $("modelCap").textContent = !L ? "" : [runNamed === null ? W.layoutFrom(L.short) : `${runNamed}${W.namedLayout(L)}`, view.metric ? `${W.METRIC_NAME.toLowerCase()} ${view.metric.text} · ${W.tempWord(view.metric, view.verification)}` : null,
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
    mv.append(num, h("small", null, unit), h("em", { title: view.metric.title }, W.tempWord(view.metric)));
    mv.title = `${view.metricDefinition} ${view.metric.title} Rounded to 0.01 °C for display.`;
    const replay = view.verification?.replay === "reproduced" ? " · replay matched" : view.verification?.replay === "not_reproduced" ? " · replay did not match" : "";
    $("metricDescription").textContent = `${W.METRIC_NAME} · simulated, not silicon${replay}${view.diagnostic ? " · diagnostic" : ""}`;
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
  if (S.v3) { if (!S.drawn || S.drawn.key !== drawKey(L, at)) {
    // A new run while following live drops in: its dies start lifted and settle onto the package (setExplode eases
    // back to the viewer's own setting), so an agent's action visibly moves the model. Its own geometry and words
    // from the first frame; nothing glides from the previous run. Reduced motion: drawn at once, as before.
    const first = !S.drawn, arrived = !first && S.drawn.id !== L.id && S.selectedId == null && S.cursorSeq == null;
    if (arrived && !REDUCED && S.motion) { const rest = S.explode; S.explode = 1; drawPackage(L, view, at); setExplode(rest, { animate: true }); }
    else { drawPackage(L, view, at); if (first) frameCamera(); }
  } }
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
  const a = M.atlas(layouts(), feed.state.events, walkAt());
  const shown = shownRun().L;
  const playing = new Set(a.stations.flatMap((st) => st.playback.map((r) => r.id)));
  const held = [...S.records.values(), ...feed.state.events];
  const visitorsNow = M.doorVisitors(held, Date.now(), M.linkedArrivals(held));
  svg.replaceChildren();
  svg.append(s("ellipse", { class: "atlas-ring", cx: 150, cy: 76, rx: 108, ry: 52 }));
  a.stations.forEach((st, i) => {
    const [x, y] = STATION_XY[i];
    const g = s("g", { class: `atlas-station${st.count ? " has" : ""}` });
    const title = s("title", {}, `${st.name}: ${st.count} ${st.what}${st.id === "door" || st.id === "submit" ? " in the newest records" : ""}`);
    g.append(title, s("rect", { x: x - 22, y: y - 9, width: 44, height: 18, rx: 3 }), s("text", { class: "st-name", x, y: y + 3, "text-anchor": "middle" }, st.name),
      s("text", { x: x - 22, y: y - 12 }, st.n), s("text", { class: "st-count", x: x + 22, y: y - 12, "text-anchor": "end" }, String(st.count)));
    svg.append(g);
    // One figure per run at its live station (a task state), at most 6 drawn per station; arrivals are counted, not
    // drawn. A run playing back its steps is drawn at the step it shows instead, labelled Playback; the count and the
    // "+N" stay the live state (a run playing back elsewhere is one of this station's +N).
    // Six slots a row, playbacks first (root, 0c97bbd P2: with no slot left, slice(-0) kept every live figure). A
    // playback past the sixth is not drawn; like every live run not drawn at its station, it is one of its live
    // station's +N.
    const back = st.playback.slice(0, 6);
    const slots = 6 - back.length;
    const live = st.runs.filter((r) => !playing.has(r.id));
    const kept = slots > 0 ? live.slice(-slots) : [];
    // At Door: the recent visitors (arrival records of the last 15 min), newest nearest, in the slots left; +N counts
    // the rest. The Door count stays the live count. A visitor moves only through its run's records (a run naming
    // its arrival as visit_arrival walks from Door); a visitor with no such run stays here.
    const guests = st.id === "door" ? visitorsNow : [];
    const keptGuests = st.id === "door" && slots > 0 ? guests.slice(0, slots).reverse() : [];
    const row = [...kept, ...keptGuests, ...back];
    const more = st.id === "door" ? guests.length - keptGuests.length : st.runs.length - kept.length - back.filter((r) => r.live === st.id).length;
    if (more > 0) svg.append(s("text", { x: x + 38, y: y + 22, class: "atlas-more", fill: "#cfe2d5", "font-size": 8, "text-anchor": "start" }, `+${more}`));
    row.forEach((r, k) => {
      const cx = x - ((row.length - 1) * 11) / 2 + k * 11, cy = y + 19;
      const size = large ? 16 : 13;
      if (r.kind === "arrival") { drawGuest(svg, r, cx, cy, size, r === keptGuests.at(-1)); return; }
      const dot = avatar({ cls: r.cls, short: r.label.split(" · ")[1] ?? null, seq: 0 });
      dot.setAttribute("x", (cx - size / 2).toFixed(1)); dot.setAttribute("y", (cy - size / 2).toFixed(1));
      dot.setAttribute("width", size); dot.setAttribute("height", size);
      dot.setAttribute("class", `av atlas-av${shown && r.id === shown.id ? " sel" : ""}${r.step ? " playback" : ""}`);
      dot.append(s("title", {}, r.step ? `${W.layoutFrom(r.label.split(" · ")[1] ?? null)}: a playback of a step it just recorded (${W.RUN_STATE[r.status] ?? r.status})`
        : `${W.layoutFrom(r.label.split(" · ")[1] ?? null)} ${W.RUN_STATE[r.status] ?? r.status}`));
      dot.addEventListener("click", () => selectRun(r.id));
      svg.append(dot);
      // A run playing back carries the plain word of the step it shows, marked as a playback, above its figure.
      if (r.step) svg.append(s("text", { class: "atlas-step", x: cx.toFixed(1), y: (cy - size / 2 - 3).toFixed(1), "text-anchor": "middle",
        "data-step": String(r.step.i), "data-station": r.step.station }, W.TEXT.playback(r.step.word)));
      const short = r.label.split(" \u00b7 ")[1] ?? null;
      if (shown && r.id === shown.id && short) svg.append(s("text", { class: "atlas-visit", x: cx.toFixed(1), y: (cy + size / 2 + 8).toFixed(1), "text-anchor": "middle" }, `visit ${short}`));
    });
  });
  return a;
}
// A visitor at Door: its figure (sliding in when it first arrives live) and, under the newest one, its declared name
// through the exact declaration.arrival relation ("self-declared, not verified") or its visit id. Text only.
const guestSeen = new Map();     // arrival seq -> when first drawn (null: held at the first read)
function drawGuest(svg, e, cx, cy, size, newest) {
  const now = Date.now();
  if (!guestSeen.has(e.seq)) guestSeen.set(e.seq, walkHistory === null ? null : now);
  const since = guestSeen.get(e.seq);
  const dot = avatar({ cls: e.cls, short: e.short, seq: e.seq, category: e.category, verification: e.verification });
  dot.setAttribute("x", (cx - size / 2).toFixed(1)); dot.setAttribute("y", (cy - size / 2).toFixed(1));
  dot.setAttribute("width", size); dot.setAttribute("height", size);
  dot.setAttribute("class", `av atlas-av guest${since !== null && now - since < 1500 ? " door-in" : ""}`);
  dot.append(s("title", {}, `${W.doorLabel(e.short)} \u00b7 at the door`));
  svg.append(dot);
  if (!newest) return;
  const name = namesNow().get(e.seq) ?? null;
  svg.append(s("text", { class: "atlas-guest", x: cx.toFixed(1), y: (cy + size / 2 + 8).toFixed(1), "text-anchor": "middle" },
    name === null ? W.doorLabel(e.short) : `${name} \u00b7 self-declared, not verified`));
}
// The open expanded atlas (its map and table), redrawn with the small one on every render and every playback step
// (root, 0ba078e P2 2); null when the dialog is closed or shows something else.
let openAtlas = null;
const atlasTable = (a) => table(a.stations.map((st) => [`${st.n} ${st.name}`, `${st.count} \u00b7 ${st.what}`]));
function drawMaps() {
  const a = drawAtlas($("atlasSvg"));
  if (openAtlas && $("modal").open === false) openAtlas = null;
  if (openAtlas) openAtlas.tableBox.replaceChildren(atlasTable(drawAtlas(openAtlas.svg, { large: true })));
  return a;
}
function renderWork() {
  const scroller = $("visitorList");
  const keep = scroller.scrollTop ?? 0;
  renderArrivals();
  const a = drawMaps();
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
      h("span", null, h("strong", null, `Run ${r.short}`), h("small", null, `${W.visitorType(r.cls)} · ${r.sameLabel ? `${where} · 1 of ${r.sameLabel + 1} designs with this short id` : where}`),
        ...(() => { const L = layouts().find((l) => l.id === r.run_id); if (!L) return []; const o = M.runOutcome(L); return [h("small", { class: `outcome ${o.kind}`, title: o.title }, o.text)]; })()),
      h("span", { class: "agent-task" }, task), h("span", { class: `agent-pip ${r.task ? STATE_PIP(r.task.state) : "grey"}` }));
    btn.addEventListener("click", () => { if (layouts().some((l) => l.id === r.run_id)) selectRun(r.run_id); openRun(r); });
    list.append(btn);
  }
  renderRecords(list);
  if (!runs.length && !door.length && !anonymous.length) list.append(h("p", { class: "rail-empty" }, M.feedStatus(feed.state, { hostname: location.hostname }).state === "error" ? "No records: the door feed is not answering." : "No records yet."));
  // The newest record, or the replay cursor's.
  const pts = points();
  const c = M.cursorIndex(pts, S.cursorSeq);
  const p = c === null ? pts.at(-1) : pts[c];
  $("selectedEventLabel").textContent = c === null ? W.TEXT.newest : W.TEXT.replayStep(c + 1, pts.length);
  scroller.scrollTop = keep;
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
// The declared names, at render time only (live-model.mjs declaredNames); a change re-renders every place that shows one.
const namesNow = () => M.declaredNames(S.decl, Date.now());
let namesSeen = "[]";
function namesChanged() { const k = JSON.stringify([...namesNow()]); if (k === namesSeen) return false; namesSeen = k; return true; }
// A declared name in text only (bdi, never an attribute), followed by its note, visit id and lab.
const named = (name, a, cls = "av-name") => h("span", { class: cls }, h("bdi", null, name), W.namedTail(a));
let cardSeq = null, cardLine = null;
function renderArrivals() {
  const list = M.arrivalsOf(feed.state.events, 13);
  const now = Date.now();
  const names = namesNow();
  const newest = list[0];
  const fresh = newest && newest.at && now - Date.parse(newest.at) <= ARRIVAL_HOLD_MS;
  const card = $("arrivalCard");
  card.hidden = !fresh;
  // A settled card keeps nothing: a name it showed must not linger in its DOM once the card is hidden (root, 19:01Z).
  if (!fresh && cardSeq !== null) { card.replaceChildren(); cardSeq = null; cardLine = null; }
  const cardName = fresh ? names.get(newest.seq) ?? null : null;
  const cardKey = fresh ? JSON.stringify([newest.seq, cardName]) : null;
  if (fresh && cardSeq !== cardKey) {
    cardSeq = cardKey;
    cardLine = h("p", null, W.arrivalSentence(newest, now), h("small", null, W.arrivalDetail(newest)));
    card.replaceChildren(avatar(newest), h("div", null, cardName === null ? null : named(cardName, newest, "av-name card"), cardLine));
  } else if (fresh) {
    cardLine?.firstChild && (cardLine.firstChild.textContent = W.arrivalSentence(newest, now));
  }
  const strip = (fresh ? list.slice(1) : list).slice(0, 12);
  $("arrivalStrip").replaceChildren(...strip.map((a) => h("div", { class: names.has(a.seq) ? "av-item named" : "av-item", role: "listitem", title: `${W.arrivalSentence(a, now)} · ${W.arrivalDetail(a)}` },
    avatar(a), names.has(a.seq) ? named(names.get(a.seq), a) : h("span", null, a.short ? `visit ${a.short}` : W.visitorType(a.cls)), h("span", null, W.when(a.at, now)))));
  $("arrivals").hidden = list.length === 0;
  $("arrivalsHead").textContent = W.ARRIVALS_HEAD;
}

// ── every door record: newest first, in the aquarium's population tabs, older pages on request ────────────────
function renderRecords(list) {
  S.records = M.mergeRecords(S.records, feed.state.events);
  const win = feed.state.events;
  if (win.length) S.cover = M.addRange(S.cover, Math.min(...win.map((e) => e.seq)), feed.state.eventsCursor);
  const gaps = M.rangeGaps(S.cover);
  const empty = !S.cover.length && feed.state.lastOkAt && !(feed.state.eventsCursor > 0);
  const done = !gaps.length && (M.readFromStart(S.cover) || Boolean(empty));
  const all = [...S.records.values()].sort((x, y) => y.seq - x.seq);
  const shown = S.recTab === "all" ? all : all.filter((e) => W.populationOf(e) === S.recTab);
  list.append(h("p", { class: "door-head" }, W.RECORDS.head));
  const tabs = h("div", { class: "rec-tabs", role: "tablist", "aria-label": "Records by who sent them" });
  for (const p of W.POPULATIONS) {
    const n = p.id === "all" ? all.length : all.filter((e) => W.populationOf(e) === p.id).length;
    const b = h("button", { type: "button", role: "tab", class: S.recTab === p.id ? "on" : "", "aria-selected": S.recTab === p.id ? "true" : "false", dataset: { tab: p.id } }, `${p.label} ${n}`);
    b.addEventListener("click", () => { S.recTab = p.id; renderWork(); });
    tabs.append(b);
  }
  list.append(tabs);
  const rows = h("div", { class: "rec-list", id: "recordRows" });
  const names = namesNow();
  if (!shown.length) rows.append(h("p", { class: "rail-empty" }, W.RECORDS.none));
  let newer = null;
  for (const e of shown) {
    // Where records are known to be missing, the list says so in place (never a silent hole).
    if (newer !== null && gaps.some(([lo, hi]) => lo > e.seq && hi < newer)) rows.append(h("p", { class: "rec-gap" }, W.RECORDS.gapHere));
    newer = e.seq;
    rows.append(h("div", { class: "rec-row", title: `seq ${e.seq}` }, avatar({ cls: e.cls, short: e.short, seq: e.seq, category: e.category, verification: e.verification }),
      e.kind === "arrival" && names.has(e.seq)
        ? h("span", null, h("bdi", null, names.get(e.seq)), `${W.namedTail(e)} \u00b7 ${e.event_kind === "declaration" ? W.TEXT.declared : W.TEXT.arrived}`, h("small", null, W.when(e.at)))
        : h("span", null, M.recordSentence(e), h("small", null, W.when(e.at)))));
  }
  list.append(rows);
  const more = h("button", { type: "button", class: "rec-more", id: "recordMore" },
    S.recLoading ? (S.recWhat === "gap" ? W.RECORDS.filling : W.RECORDS.loading)
      : S.recError ? (S.recWhat === "gap" ? W.RECORDS.gapFailed(S.recError) : W.RECORDS.failed(S.recError))
      : gaps.length ? W.RECORDS.filling : done ? W.RECORDS.done : W.RECORDS.more);
  more.disabled = S.recLoading || done;
  more.addEventListener("click", () => { S.gapRetryAt = 0; if (M.rangeGaps(S.cover).length) fillGap(); else loadEarlier(); });
  list.append(more);
  if (gaps.length && !S.recLoading) setTimeout(fillGap, 0);
}
// One older page at a time, through the page's gate (spaced like every other request), never a burst.
// Both readers record what they read as a covered range, and drop an answer from an ended epoch (pagehide).
let recEpoch = 0;
async function readRecords(what, req) {
  const mine = recEpoch;
  S.recLoading = true; S.recWhat = what; S.recError = "";
  renderWork();
  const got = await M.fetchEventsPage(req.after, { fetchImpl: gate.fetch, limit: req.limit });
  if (mine !== recEpoch) return;
  S.recLoading = false;
  if (got.ok && got.next_after > req.after) {
    S.records = M.mergeRecords(S.records, got.events);
    S.cover = M.addRange(S.cover, req.after + 1, got.next_after);
    S.recWhat = "";
  } else {
    S.recError = got.ok ? "the door returned no records for that range" : got.error;
    if (what === "gap") S.gapRetryAt = Date.now() + GAP_RETRY_MS;
  }
  renderWork();
}
async function loadEarlier() {
  if (S.recLoading) return;
  const oldest = S.cover[0]?.[0] ?? (feed.state.lastOkAt ? (feed.state.eventsCursor ?? 0) + 1 : null);
  if (oldest === null || oldest <= 1) { renderWork(); return; }
  await readRecords("older", M.olderPage(oldest));
}
// A hole the feed's window left (a burst of more records than it keeps) is read back on its own, through the gate,
// one page at a time; after a failure it waits GAP_RETRY_MS (or the reader's click) before trying again.
const GAP_RETRY_MS = 30000;
async function fillGap() {
  if (S.recLoading || document.hidden || Date.now() < S.gapRetryAt) return;
  const gap = M.rangeGaps(S.cover)[0];
  if (gap) await readRecords("gap", M.gapPage(gap));
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
  if (!on) { setOrbit(false); stopPlay(); stopWalks(); }
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
  openAtlas = null;
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
    const tableBox = h("div", null, atlasTable(a));
    openDialog("Stations are the door's own records.", "THE DOOR ATLAS",
      lead("Each station is a kind of record the door emits. A figure is a run at its last reported state: a task state, not a screen position. The numbers and this table always show the live state. Arrivals and refused attempts are counted where the door saw them."),
      h("div", { class: "large-map" }, svg),
      tableBox,
      note("When several of a run's step records arrive in one read, its figure plays them back in their recorded order, about 0.7 s a step on the page's own clock, captioned Playback, then rests at the run's latest step. It shows only steps the run recorded; nothing is invented or interpolated between them. With reduced motion, paused motion or a hidden tab, a figure goes straight to its latest step."));
    openAtlas = { svg, tableBox };
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
  $("packageButton").addEventListener("click", () => { const L = shownRun().L; if (L) downloadPackage(L.id); });
  $("topLayouts").addEventListener("click", () => downloadTop());
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
  document.addEventListener("visibilitychange", () => { if (document.hidden) { stopPlay(); hiddenSincePoll = true; stopWalks(); } else pollBoard(); });
  new ResizeObserver(() => renderTrace()).observe($("traceSvg"));
  $("visitorList").addEventListener("scroll", (e) => { const el = e.target; if (el.scrollTop + el.clientHeight >= el.scrollHeight - 40) loadEarlier(); }, { passive: true });
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
    if (got.ok) S.decl = { ok: true, partial: got.partial, list: M.declarationList(got.items), items: got.items, error: "", at: Date.now(), through: got.through ?? S.decl.through };
    else { S.decl = { ...S.decl, ok: false, list: [], items: [], error: got.error }; if (got.error === "answered 404") next = M.VISITORS_SLOW_MS; }
    renderDeclarations();
    if (namesChanged()) render();
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
setInterval(() => { renderStatus(); renderDeclarations(); renderArrivals(); renderProposals(); renderPresence(); if (namesChanged()) render(); }, 1000);
// Leaving the page stops every poll (and an answer still in flight cannot restart one: the board's epoch moves on). A
// page restored from the back/forward cache comes back with them stopped, so pageshow starts again what pagehide
// stopped; a fresh load gets no pageshow with persisted set.
window.addEventListener("pagehide", () => { feed.stop(); stopWalks(); endNewProposal(); recEpoch += 1; S.recLoading = false; boardEpoch += 1; clearTimeout(boardTimer); visitorsEpoch += 1; clearTimeout(visitorsTimer); stopPlay(); });
window.addEventListener("pageshow", (e) => { if (e.persisted) { feed.start(); pollBoard(); pollVisitors(); renderStatus(); } });
