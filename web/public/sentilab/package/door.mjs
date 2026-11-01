// SentiLab Package view, agent-door feed: CPU-DRAM layouts in 3D, in arrival order, with the scorer's numbers.
// Data only through source3d.mjs (the bundled replay; live, the door API's results and events through one seam),
// geometry only through model.mjs (the RenderModel), drawing through render3d.mjs (three.js) or, without WebGL, with
// reduced motion or on request, the Package view's own Canvas 2D renderer (render.mjs). Every string from data reaches
// the page through textContent and is either a fixed word chosen here, a label rebuilt by source3d.mjs (class · short
// id) or a code or identity source3d.mjs checked against a fixed pattern: never visitor text.
import { loadFixture, verifyPinnedFields, createDoorFeed, statusLine, BOARD_METRIC, SCORED, DOOR_RESULTS_PATH, DOOR_EVENTS_PATH } from "./source3d.mjs";
import { buildRenderModel, displayBoxes, fieldTexels, viewNotes, SCALE, scaleFraction, formatThickness, dieRects, GRID } from "./model.mjs";
import { STACK_LAYERS, REFERENCES, ACTIVE_LAYER_GUARD_C, INTERPOSER_MM, CASE_TITLE, GATE_ZERO_EVALUATOR } from "./case-cpu-dram.mjs";
import { drawPackage, TrackAnimation } from "./render.mjs";
import { webgl2Available, live3d } from "./render3d.mjs";
// Every door temperature becomes text through temps.mjs with a shared label (PL-2), and the page shows the shared
// notice whenever a withdrawn or unvalidated temperature is on screen (temperature-label.mjs, the one rule).
import { formatTemp, tempNode } from "./temps.mjs";
import { labelFor, NOTICE } from "../../temperature-label.mjs";

const DWELL_MS = 7000;
const EXPLODE_MS = 800;
const KIND_FILL = Object.freeze({ CPU: "#9c86c8", DRAM: "#6f93b4" });
const KIND_LINE = Object.freeze({ CPU: "#c4a7f5", DRAM: "#8fb8de" });
const CLASS_COLOR = Object.freeze({
  "reference-only": "#c9b2e8", reference: "#e7c48f", example: "#9fb4bb", ours: "#88d9d0", verified_agent: "#a5d5aa",
  signed_agent: "#a5d5aa", declared_agent: "#8aa9dd", crawler_claimed: "#e6a36a", automation: "#e6a36a", likely_human: "#c9d6d9", unknown: "#9aacb2",
});
const CLASS_NOTE = Object.freeze({
  "reference-only": "The raw reconstruction of the published layout. Off the 0.5 mm lattice: a reference, never a candidate.",
  reference: "The raw layout rounded to the 0.5 mm lattice, no repair: the legal baseline.",
  example: "A synthetic example written for this page. Never submitted, never scored.",
  ours: "Proposed by our own background agent.",
  verified_agent: "An agent whose request signature verified. A classification, not an identity.",
  signed_agent: "An agent that signed its requests. A classification, not an identity.",
  declared_agent: "An agent that declared itself. A classification, not an identity.",
  crawler_claimed: "A client that claims to be a known crawler. A classification, not an identity.",
  automation: "An automated client. A classification, not an identity.",
  likely_human: "Most likely a person's browser. A classification, not an identity.",
  unknown: "An unclassified visitor.",
});
const STATUS_CHIP = Object.freeze({
  reference: ["ref", "REFERENCE"], example: ["init", "EXAMPLE"], queued: ["open", "QUEUED"], held: ["open", "HELD"],
  evaluating: ["open", "EVALUATING"], evaluated: ["open", "EVALUATED"], replaying: ["open", "REPLAYING"],
  reproduced: ["won", "REPRODUCED"], cross_checked: ["won", "CROSS-CHECKED"], not_reproduced: ["out", "NOT REPRODUCED"],
  rejected: ["out", "REJECTED"], failed: ["out", "FAILED"], cancelled: ["out", "CANCELLED"], expired: ["out", "EXPIRED"],
});
const NOT_SCORED = Object.freeze({
  reference: "Temperature not evaluated", example: "Not scored · synthetic example", queued: "Not scored yet · queued",
  held: "Not scored yet · held", evaluating: "Not scored yet · evaluating", rejected: "Rejected · never simulated",
  failed: "Simulation failed · no score", cancelled: "No score · cancelled", expired: "No score · expired",
});
const REFUSED_RESULT = Object.freeze({
  result_not_scored_state: "the state is not a score", result_label_unknown: "unknown claim label", metric_unknown: "not the board metric",
  metric_value: "value out of range", precision_missing: "no precision", grid_orientation_missing: "grid orientation not declared",
  grid_size: "grid is not 64 x 64", grid_value: "grid value out of range", distinct_value: "a statistic missing or out of range", result_malformed: "malformed",
  guard_unknown: "not the board's active-layer guard", guard_inconsistent: "the guard contradicts its own peak",
  verification_malformed: "verification unreadable", replay_malformed: "replay unreadable",
});
const ENGINE = "HotSpot 6.0, grid 64";
// The labels of the reference panel's temperatures: the gate-zero statistics by their (pinned) evaluator, the paper's
// published points by none (labelFor of a missing identity is "unvalidated").
const LABEL_GATE_ZERO = labelFor(GATE_ZERO_EVALUATOR);
const LABEL_PUBLISHED = labelFor(undefined);
const FIELD_NOTE = Object.freeze({
  verified: `Map: active-layer temperature field · ${ENGINE}, block-centre map mode · pinned field, checked in this page`,
  unassociated: "Field unassociated: no admitted association to this layout (the door feed is unsigned), so no map is drawn",
  file_check_unavailable: "File check unavailable here (needs a secure connection): no map is drawn",
  mismatch: "The result does not match its pinned identity (field, orientation or statistics): no map is drawn",
});
const fmtMm = (v) => (Math.abs(v) >= 1000 ? Math.round(v).toLocaleString("en-US") : String(v));
// An evaluator identity, shortened for a line of text (its build hash to 8 hex); the whole string is the title.
const shortIdentity = (id) => id.replace(/[0-9a-f]{64}/, (x) => `${x.slice(0, 8)}…`);
const words = (code) => code.replace(/_/g, " ");
// What the feed says a result was checked for, and what it is not (#81's verification block), as the feed's report.
function verificationText(v) {
  const replay = v.replay === "reproduced"
    ? `replay reproduced${v.distinct_execution ? " in a distinct process" : ""}${v.receipts_bound ? ", receipts bound" : ""}`
    : `replay not reproduced${v.replay_code ? ` (${words(v.replay_code)})` : ""}`;
  return [`The feed reports, unsigned: ${replay}`, `selector binding ${v.binding_ok ? "ok" : "not ok"}`,
    `CPU ${v.cpu === "measured" ? "measured" : "unknown, charged conservatively"}`,
    v.candidate ? "a candidate (on the front against the raw reference)" : null,
    v.not_claimed.length ? `not claimed: ${v.not_claimed.join(", ")}` : null].filter(Boolean).join(" · ");
}

export async function startDoor({ params, REDUCED }) {
  const $ = (id) => document.getElementById(id);
  const h = (tag, props, ...kids) => {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(props ?? {})) {
      if (v == null || v === false) continue;
      if (k === "class") node.className = v;
      else node.setAttribute(k, v === true ? "" : String(v));
    }
    for (const kid of kids.flat(Infinity)) if (kid != null && kid !== false) node.append(kid instanceof Node ? kid : String(kid));
    return node;
  };

  const D = {
    source: params.get("src") === "live" ? "api" : "fixture",
    fixture: null, fixtureError: "",
    feed: null, liveDown: false,
    list: [], idx: -1, following: true, playing: null,
    r: "3d", want: "3d", why2d: "", v3: null, v3Failed: false, lost: false,
    noCrypto: !globalThis.crypto?.subtle,     // D14: without WebCrypto nothing can be checked, so no result is drawn
    overlay: params.get("overlay") === "1",
    orbit: !REDUCED && params.get("orbit") !== "0",
    explode: 0, explodeAnim: null,
    current: null,
    anim2d: new TrackAnimation(),
    fieldCanvas: new Map(),
    announced: new Set(),
  };
  const shown = () => D.list[D.idx] ?? null;

  // ── which renderer ──
  const can3d = webgl2Available();
  const want = params.get("r");
  if (!can3d) { D.r = "2d"; D.why2d = "WebGL 2 is not available in this browser: showing the 2D view"; }
  else if (want === "2d") { D.r = "2d"; D.why2d = ""; }
  else if (REDUCED && want !== "3d") { D.r = "2d"; D.why2d = "Reduced motion is on: showing the 2D view (3D is one click away)"; }

  // ── the 2D surface (render.mjs drawPackage) ──
  const c2 = $("mainCanvas"), ctx2 = c2.getContext("2d");
  const s2 = { w: 1, h: 1 };
  function size2d() {
    const r = c2.getBoundingClientRect(), dpr = Math.min(3, window.devicePixelRatio || 1);
    s2.w = Math.max(1, Math.round(r.width)); s2.h = Math.max(1, Math.round(r.height));
    c2.width = Math.round(s2.w * dpr); c2.height = Math.round(s2.h * dpr);
    ctx2.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  new ResizeObserver(() => { if (D.r === "2d") { size2d(); draw2dSoon(); } else D.v3?.resize(); }).observe($("mainWrap"));

  // ── 3D ──
  // A lost graphics context: the old view is disposed at once (its frames, listeners and GL objects), the 2D view takes
  // over, and when the browser restores the context a new 3D view is built from the layout the page kept.
  function onContextLost() {
    const old = D.v3;
    D.v3 = null;
    D.lost = true;
    cancelAnimationFrame(D.explodeAnim); D.explodeAnim = null;   // a queued explode step never reaches the released view
    old?.dispose();
    $("main3d").addEventListener("webglcontextrestored", () => { D.lost = false; if (D.want === "3d") setRenderer("3d", "", { user: false }); }, { once: true });
    setRenderer("2d", "The 3D view lost its graphics context: showing the 2D view until it is restored", { user: false });
  }
  async function ensure3d() {
    if (D.v3) return D.v3;
    if (D.v3Failed || D.lost) return null;
    try {
      const { createView3D } = await import("./render3d.mjs");
      D.v3 = await createView3D({
        canvas: $("main3d"), labels: $("labels3d"), leaders: $("leaders3d"), reduced: REDUCED, onContextLost,
      });
      D.v3.setLayerWords(new Map(STACK_LAYERS.map((l) => [l.level, [["b", null, l.name], ["span", null, formatThickness(l.t_mm)]]])));
      D.v3.setOverlay(D.overlay);
      D.v3.setAutoOrbit(D.orbit);
      D.v3.onUserMove(() => { if (D.orbit) setOrbit(false); });
      return D.v3;
    } catch (e) {
      D.v3Failed = true;
      D.why2d = `The 3D view could not start (${String(e?.message ?? e).slice(0, 80)}): showing the 2D view`;
      return null;
    }
  }
  async function setRenderer(r, why = "", { user = true } = {}) {
    if (r === "3d" && !can3d) return;
    if (user) D.want = r;
    D.r = r;
    D.why2d = why;
    if (r === "3d") {
      const v = await ensure3d();
      if (!v) { D.r = "2d"; if (D.lost) D.why2d = "The 3D view's graphics context is lost: showing the 2D view until it is restored"; }
    }
    const is3d = D.r === "3d";
    $("main3d").hidden = !is3d; $("labels3d").hidden = !is3d; $("leaders3d").toggleAttribute("hidden", !is3d);   // an <svg> has no .hidden
    c2.hidden = is3d;
    for (const b of document.querySelectorAll(".controls.door .rseg button")) {
      b.classList.toggle("on", b.dataset.r === D.r);
      if (b.dataset.r === "3d") b.disabled = !can3d;
    }
    for (const id of ["dOrbit", "dExplode", "dFit", "dOverlay"]) $(id).disabled = !is3d;
    D.v3?.setAutoOrbit(is3d && D.orbit);   // a hidden 3D view draws no frames
    if (is3d) { D.v3.resize(); render({ animate: false }); }
    else { size2d(); render({ animate: false }); }
  }

  // ── showing a layout ──
  function displayFor(model) { return displayBoxes(model, { thin: true, lift: 1, explode: D.explode }); }
  function render({ animate = true } = {}) {
    const L = shown();
    if (!L) { D.current = null; renderDom(); if (D.r === "2d") draw2dSoon(); return; }
    const { model, error } = buildRenderModel({ kind: "model", layout: L });
    if (error) { D.current = null; renderDom(); return; }
    const field = drawableField(L);
    D.current = { L, model, field };
    if (D.r === "3d" && D.v3) D.v3.setDoor(model, displayFor(model), { field, animate, notScored: tag3d(L, field) });
    else {
      const rects = dieRects(L.dies);
      D.anim2d.set({ chiplets: rects.map((r) => ({ id: r.id, x: r.x0, y: r.y0, w: r.w, h: r.h, layer: 0, kind: "die", temp: null, temp_state: null, color: KIND_FILL[r.kind] })), overlaps: [] },
        { animate: animate && !REDUCED, now: performance.now() });
      draw2dSoon();
    }
    renderDom();
  }
  function show(idx, { animate = true } = {}) {
    if (!D.list.length) { D.idx = -1; render({ animate: false }); return; }
    D.idx = Math.max(0, Math.min(D.list.length - 1, idx));
    render({ animate });
  }
  // A field is drawn only when its association is admitted and verified (source3d.mjs verifyPinnedFields), and its
  // texture, canvas and tile caches are keyed by the field's verified content identity (sha256), never by its score.
  function drawableField(L) {
    const r = L?.result;
    return r && r.field_state === "verified" && r.grid && r.field_key && !D.noCrypto ? fieldTexels(r.grid, r.field_key) : null;
  }
  const resultShown = (L) => Boolean(L?.result) && !D.noCrypto;
  // The 3D view's tag on the chip layer, for a layout drawn without a value; a shown value's caption says why there is
  // no map (a feed result is unassociated), so no tag then.
  const tag3d = (L, field) => (field || resultShown(L) ? null : notScoredText(L));
  function notScoredText(L) {
    if (L.result_refused) return `Score not shown · ${REFUSED_RESULT[L.result_refused] ?? L.result_refused}`;
    if (L.result && D.noCrypto) return "Result not shown · file check unavailable here (needs a secure connection)";
    if (L.result && L.result.field_state !== "verified") return L.result.field_state === "unassociated" ? "Field unassociated · not drawn" : FIELD_NOTE[L.result.field_state];
    return NOT_SCORED[L.status] ?? (SCORED.includes(L.status) ? "No score in this record" : "Not scored yet");
  }

  // ── 2D drawing (the Package view's renderer) with the field drawn onto the tops ──
  let raf2 = 0;
  function draw2dSoon() { if (!raf2) raf2 = requestAnimationFrame(draw2d); }
  function draw2d(now) {
    raf2 = 0;
    if (D.r !== "2d") return;
    const L = shown();
    const fr = D.anim2d.frame(now);
    const footprint = { substrate: { x0: -1.5, y0: -1.5, x1: INTERPOSER_MM + 1.5, y1: INTERPOSER_MM + 1.5 }, interposer: { x0: 0, y0: 0, x1: INTERPOSER_MM, y1: INTERPOSER_MM } };
    const field = L && D.current?.field && !fr.active ? { canvas: fieldCanvasOf(L, D.current.field), x0: 0, y0: 0, x1: INTERPOSER_MM, y1: INTERPOSER_MM } : null;
    const compact = s2.w < 700;
    drawPackage(ctx2, L ? { ...fr, footprint, unit: "°C", field } : null, {
      width: s2.w, height: s2.h, azimuthDeg: -45, labels: true, callouts: false, lid: false,
      pad: compact ? { l: 12, r: 12, t: 70, b: 70 } : { l: 40, r: 40, t: 90, b: 110 },
    });
    if (fr.active) draw2dSoon();
  }
  // A 64 x 64 canvas of the field (image row 0 = the top, y = 45 mm), for the 2D view and the strip.
  function fieldCanvasOf(L, f) {
    const key = `${f.key}:${f.sum}`;              // the field's content identity, never its score
    let c = D.fieldCanvas.get(key);
    if (c) return c;
    c = document.createElement("canvas");
    c.width = GRID; c.height = GRID;
    const g = c.getContext("2d"), img = g.createImageData(GRID, GRID);
    for (let row = 0; row < GRID; row += 1) {
      const src = row * GRID * 4, dst = (GRID - 1 - row) * GRID * 4;
      img.data.set(f.texels.subarray(src, src + GRID * 4), dst);
    }
    g.putImageData(img, 0, 0);
    if (D.fieldCanvas.size > 64) D.fieldCanvas.delete(D.fieldCanvas.keys().next().value);
    D.fieldCanvas.set(key, c);
    return c;
  }

  // ── DOM ──
  function renderDom() {
    const L = shown();
    const line = statusLine({ source: D.liveDown ? "fixture" : D.source, feed: D.feed?.state ?? null, hostname: location.hostname, nowMs: Date.now() });
    const mode = $("mode");
    mode.className = `mode ${line}`;
    const age = D.feed?.state.lastOkAt ? Math.max(0, Math.round((Date.now() - D.feed.state.lastOkAt) / 1000)) : null;
    $("modeText").textContent = line === "replay" ? "REPLAY" : `${line.toUpperCase()}${age !== null ? ` · ${age} s ago` : ""}`;
    $("drill").hidden = true;
    for (const b of $("dSource").querySelectorAll("button")) b.classList.toggle("on", b.dataset.src === D.source);
    const fromFixture = D.source === "fixture" || D.liveDown;
    $("dFixture").hidden = !fromFixture;
    $("dPlay").textContent = D.playing ? "❚❚" : "▶";
    $("dPlay").setAttribute("aria-label", D.playing ? "Pause" : "Play");
    $("dScrub").max = String(Math.max(0, D.list.length - 1));
    $("dScrub").value = String(Math.max(0, D.idx));
    $("dScrub").disabled = D.list.length < 2;
    $("dPos").textContent = D.list.length ? `${D.idx + 1} / ${D.list.length} arrivals` : "0 arrivals";
    renderTicks();
    $("dOverlay").setAttribute("aria-pressed", String(D.overlay));
    $("dExplode").setAttribute("aria-pressed", String(D.explode > 0.5));
    $("dOrbit").setAttribute("aria-pressed", String(D.orbit));
    renderBanner();
    renderHead(L);
    renderCaption(L);
    renderInfo(L);
    renderStrip();
    renderArrivals();
    renderStatus(line);
    // The shared notice: shown whenever a withdrawn or unvalidated temperature is on screen (the reference panel's
    // always are, until an evaluator is accepted), worded only in temperature-label.mjs.
    const labels = [LABEL_GATE_ZERO, LABEL_PUBLISHED, ...(resultShown(L) ? [L.result.label] : [])];
    $("wnotice").hidden = !labels.some((x) => x.notice);
    $("wnotice").textContent = $("wnotice").hidden ? "" : NOTICE;
    const empty = !L;
    $("mainEmpty").hidden = !empty;
    if (empty) {
      $("emptyTitle").textContent = D.source === "api" && !D.liveDown ? "Live · no layouts yet" : D.fixtureError ? "Fixture not loaded" : "Loading";
      $("emptyText").textContent = D.source === "api" && !D.liveDown ? "Connected. The first proposal appears here as it arrives." : D.fixtureError || "Reading the layouts.";
    }
    const canvasLabel = L ? `${D.r === "3d" ? "3D view" : "2D isometric view"} of the ${CASE_TITLE}: ${L.label}, ${(STATUS_CHIP[L.status] ?? ["", L.status])[1].toLowerCase()}. ${captionText(L)}` : "No layout drawn";
    $("main3d").setAttribute("aria-label", canvasLabel);
    c2.setAttribute("aria-label", canvasLabel);
  }
  function captionText(L) {
    if (!resultShown(L)) return notScoredText(L);
    const t = formatTemp(L.result.metric.value, L.result.label, { digits: 2 });
    return `${BOARD_METRIC.name} (${ENGINE}): ${t.text} ${t.qualifier}${L.result.diagnostic ? ", diagnostic" : ""} · simulated, not silicon`;
  }
  function renderBanner() {
    const el = $("dBanner");
    el.replaceChildren();
    const parts = [];
    if (D.source === "api" && D.liveDown) parts.push(["Live feed unreachable", ` · ${D.feed?.state.error || "no answer"} · showing the labelled replay; retrying every 5 s`]);
    const refused = Object.entries(D.source === "api" && !D.liveDown ? D.feed?.state.refused ?? {} : D.fixture?.refused ?? {});
    if (refused.length) parts.push([`${refused.reduce((s, [, n]) => s + n, 0)} record(s) refused, not drawn`, ` · ${refused.map(([k, n]) => `${k.replace(/_/g, " ")} ×${n}`).join(", ")}`]);
    if (D.noCrypto) parts.push(["File check unavailable here", " · this page needs a secure (https) connection to check its pinned files, so no result or map is drawn"]);
    el.hidden = parts.length === 0;
    for (const [b, s] of parts) el.append(h("b", null, b), h("span", null, s), " ");
  }
  function renderTicks() {
    const box = $("dTicks");
    box.replaceChildren();
    if (D.list.length < 2) return;
    D.list.forEach((L, i) => {
      const t = h("i", { class: resultShown(L) ? "accept" : "" });
      t.style.left = `${(i / (D.list.length - 1)) * 100}%`;
      t.style.background = CLASS_COLOR[L.cls] ?? "";
      box.append(t);
    });
  }
  function renderHead(L) {
    $("dTitle").textContent = L ? L.label : "-";
    $("dTitle").style.color = L ? CLASS_COLOR[L.cls] ?? "" : "";
    const chip = $("dChip");
    const sc = L ? STATUS_CHIP[L.status] ?? ["open", L.status.toUpperCase()] : null;
    chip.hidden = !sc;
    if (sc) { chip.className = `chip ${sc[0]}`; chip.textContent = sc[1]; }
    $("dSub").textContent = L ? `${CASE_TITLE} · arrival ${D.idx + 1} of ${D.list.length}` : CASE_TITLE;
  }
  function renderCaption(L) {
    const cap = $("dCaption");
    cap.replaceChildren();
    cap.className = "dcaption";
    if (!L) return;
    if (resultShown(L)) {
      cap.append(`${BOARD_METRIC.name} (${ENGINE}): `, tempNode(h, L.result.metric.value, L.result.label, { digits: 2 }),
        L.result.diagnostic ? " · diagnostic" : "", " · simulated, not silicon",
        h("span", { class: "meta" }, FIELD_NOTE[L.result.field_state] ?? FIELD_NOTE.unassociated));
    } else {
      cap.classList.add("none");
      cap.append(h("b", null, notScoredText(L)), h("span", { class: "meta" }, `${ENGINE} · simulated, not silicon · a map appears when a score exists`));
    }
    const notes = $("vNotes");
    notes.replaceChildren();
    notes.append(h("span", null, "Our model · not the real package"), h("span", null, "Simulated · not silicon"));
    if (D.r === "3d") for (const n of viewNotes({ thin: true, lift: 1, explode: D.explode > 0.01 ? 1 : 0 })) notes.append(h("span", null, n));
    else notes.append(h("span", null, "2D isometric view · schematic heights · footprints to scale"));
    if (D.why2d && D.r === "2d") notes.append(h("span", { class: "why" }, D.why2d));
  }
  function renderInfo(L) {
    $("dName").textContent = L ? L.label : "-";
    $("dName").style.color = L ? CLASS_COLOR[L.cls] ?? "" : "";
    $("dClsNote").textContent = L ? CLASS_NOTE[L.cls] ?? "" : "";
    // The board metric: the scorer's value, its name, its claim; distinct statistics apart, by name.
    $("dMetricName").textContent = `${BOARD_METRIC.name} · board metric`;
    const big = $("dValue"), dl = $("dDistinct");
    dl.replaceChildren();
    if (resultShown(L)) {
      big.className = "big";
      big.replaceChildren(tempNode(h, L.result.metric.value, L.result.label, { digits: 2 }));
      big.title = `${BOARD_METRIC.definition} ${L.result.label.title} Rounded to 0.01 °C for display.`;
      const ev = L.result.evaluator;
      $("dClaim").textContent = [`${ENGINE} · block-centre map mode · simulated, not silicon`, L.result.diagnostic ? "diagnostic: no admitted association" : null,
        ev ? `evaluator named by the feed (not checked here): ${shortIdentity(ev)}` : null].filter(Boolean).join(" · ");
      $("dClaim").title = ev ?? "";
      const guardWord = L.result.guard ? (L.result.guard.ok ? " · met, per the feed" : " · not met, per the feed") : "";
      for (const d of L.result.distinct) {
        dl.append(h("li", null, `${d.name}: `, tempNode(h, d.value, L.result.label, { digits: 2 }),
          d.key === "active_layer_peak_C" ? h("span", null, " (guard: strictly below ", tempNode(h, ACTIVE_LAYER_GUARD_C, LABEL_GATE_ZERO, { digits: 2 }), `${guardWord})`) : null));
      }
      dl.append(h("li", null, "Not the board metric: shown apart, by name."));
      if (!L.result.distinct.length) dl.lastChild.remove();
      $("dVerif").textContent = L.result.verification ? verificationText(L.result.verification) : "";
    } else {
      big.className = "big none";
      big.textContent = L ? notScoredText(L) : "-";
      big.title = BOARD_METRIC.definition;
      $("dClaim").textContent = L ? `${ENGINE} · simulated, not silicon` : "";
      $("dClaim").title = "";
      $("dVerif").textContent = "";
    }
    $("dVerif").hidden = !$("dVerif").textContent;
    // Legend: the fixed scale.
    $("dScaleName").textContent = SCALE.stat;
    const guard = $("dGuard");
    guard.style.left = `calc(${scaleFraction(ACTIVE_LAYER_GUARD_C) * 100}% - 1px)`;
    const g = formatTemp(ACTIVE_LAYER_GUARD_C, LABEL_GATE_ZERO, { digits: 2 });
    guard.title = `Active-layer guard: a layout's active-layer peak must be strictly below ${g.text} (${g.qualifier})`;
    const ticks = $("dTicks2");
    ticks.replaceChildren(...SCALE.ticks.map((v) => { const s = h("span", null, String(v)); s.style.left = `${scaleFraction(v) * 100}%`; return s; }));
    const f = D.current?.field;
    const basis = $("dBasis");
    basis.replaceChildren(`One fixed scale for every layout, ${SCALE.min} to ${SCALE.max} · white line: the active-layer guard, `,
      tempNode(h, ACTIVE_LAYER_GUARD_C, LABEL_GATE_ZERO, { digits: 2 }),
      h("small", null, f ? `${ENGINE} · one colour per ${(INTERPOSER_MM / GRID).toFixed(2)} mm cell, nothing interpolated${f.above || f.below ? ` · ${f.above + f.below} cell(s) beyond the scale, clamped` : ""}` : "No map on screen for this layout"));
    renderRefs();
    renderStack();
  }
  let refsBuilt = false;
  function renderRefs() {
    if (refsBuilt) return;
    refsBuilt = true;
    const box = $("dRefList");
    box.replaceChildren();
    for (const g of [REFERENCES.raw, REFERENCES.snapped, REFERENCES.published]) {
      const label = g === REFERENCES.published ? LABEL_PUBLISHED : LABEL_GATE_ZERO;
      const rows = g.stats.map((s) => h("tr", null, h("td", null, s.stat), h("td", null, s.value === null ? s.text
        : s.unit === "°C" ? tempNode(h, s.value, label, { digits: String(s.value).split(".")[1]?.length ?? 0 }) : `${fmtMm(s.value)} ${s.unit}`)));
      box.append(h("div", { class: "rgroup" }, h("b", null, g.title), h("p", null, g.note), h("table", null, h("tbody", null, rows))));
    }
  }
  let stackBuilt = false;
  function renderStack() {
    if (stackBuilt) return;
    stackBuilt = true;
    const body = $("dStack").tBodies[0];
    body.replaceChildren(...[...STACK_LAYERS].reverse().map((l) => h("tr", { class: l.level === "chip" ? "chip" : null },
      h("td", null, l.name), h("td", { class: "n" }, formatThickness(l.t_mm)), h("td", { class: "k" }, `k ${l.k}`))));
    body.append(h("tr", null, h("td", { colspan: "3" }, "k in W/(m K), the layer default; spreader 90 mm and sink 180 mm square, the rest 45 mm")));
  }

  // The arrivals panel (live only): the newest events of the door's events feed, by class and short id only.
  function eventText(e) {
    const codes = e.codes?.length ? e.codes.map(words).join(", ") : "";
    if (e.kind === "arrival") return "arrived at the door";
    if (e.kind === "attempt") return `attempt ${e.outcome}${codes ? `: ${codes}` : ""}`;
    return `${(STATUS_CHIP[e.state] ?? ["", e.state])[1].toLowerCase()}${codes ? ` (${codes})` : ""}`;
  }
  function renderArrivals() {
    const live = D.source === "api" && !D.liveDown && Boolean(D.feed);
    $("dArrivals").hidden = !live;
    const list = $("dArrList");
    if (!live) { list.replaceChildren(); return; }
    // Newest first; a run once, at its newest state, so agents arriving and refused attempts stay in view.
    const events = [], runs = new Set();
    for (const e of [...D.feed.state.events].reverse()) {
      if (e.kind === "run") { if (runs.has(e.run_id)) continue; runs.add(e.run_id); }
      events.push(e);
      if (events.length === 8) break;
    }
    list.replaceChildren(...(events.length ? events.map((e) => {
      const b = h("b", null, e.label);
      b.style.color = CLASS_COLOR[e.cls] ?? "";
      return h("li", null, b, ` ${eventText(e)}`);
    }) : [h("li", { class: "none" }, "No arrivals yet")]));
  }

  // The arrival strip: one tile per layout, a plan view with the map when there is one.
  const tiles = new Map();
  function renderStrip() {
    const strip = $("dStrip");
    const ids = D.list.map((l) => l.id);
    for (const [id, t] of tiles) if (!ids.includes(id)) { t.btn.remove(); tiles.delete(id); }
    D.list.forEach((L, i) => {
      let t = tiles.get(L.id);
      if (!t) {
        const canvas = h("canvas", { "aria-hidden": "true" });
        const btn = h("button", { type: "button", class: "dtile" }, h("div", { class: "th" }, h("b"), h("span", { class: "chip" })), h("div", { class: "tc" }, canvas), h("div", { class: "tf" }));
        btn.addEventListener("click", () => { stop(); D.following = false; show(D.list.findIndex((x) => x.id === L.id)); });
        t = { btn, canvas, sig: null };
        tiles.set(L.id, t);
      }
      if (strip.children[i] !== t.btn) strip.insertBefore(t.btn, strip.children[i] ?? null);
      const sel = i === D.idx;
      t.btn.classList.toggle("sel", sel);
      t.btn.setAttribute("aria-pressed", String(sel));
      t.btn.style.setProperty("--cls", CLASS_COLOR[L.cls] ?? "");
      const sc = STATUS_CHIP[L.status] ?? ["open", L.status.toUpperCase()];
      const r = resultShown(L) ? L.result : null;
      const sig = `${L.label}|${L.status}|${r ? `${r.metric.value}|${r.field_state}|${r.field_key}|${r.label.state}` : "-"}|${L.dies.map((d) => `${d.x_um},${d.y_um},${d.rot_deg}`).join(";")}`;
      const tt = r ? formatTemp(r.metric.value, r.label, { digits: 2 }) : null;
      t.btn.setAttribute("aria-label", `${L.label}, ${sc[1].toLowerCase()}${tt ? `, ${BOARD_METRIC.name} ${tt.text} ${tt.qualifier}` : ""}`);
      if (t.sig !== sig) {
        t.sig = sig;
        const [b, chip] = t.btn.querySelector(".th").children;
        b.textContent = L.label;
        b.style.color = CLASS_COLOR[L.cls] ?? "";
        chip.className = `chip ${sc[0]}`;
        chip.textContent = sc[1];
        const tf = t.btn.querySelector(".tf");
        tf.replaceChildren(...(r ? [tempNode(h, r.metric.value, r.label, { digits: 2 }), r.diagnostic ? "diagnostic" : "max chiplet-centre mean"] : [notScoredText(L)]));
        drawPlan(t.canvas, L);
      }
    });
    // Keep the tile on screen inside the strip only (never scroll the page).
    const sel = tiles.get(shown()?.id);
    if (sel && (sel.btn.offsetLeft < strip.scrollLeft || sel.btn.offsetLeft + sel.btn.offsetWidth > strip.scrollLeft + strip.clientWidth)) {
      strip.scrollLeft = Math.max(0, sel.btn.offsetLeft - (strip.clientWidth - sel.btn.offsetWidth) / 2);
    }
  }
  // A top-down plan of one layout: interposer, the map when scored, die outlines (CPU / DRAM colours).
  function drawPlan(canvas, L) {
    const r = canvas.getBoundingClientRect(), dpr = Math.min(2, window.devicePixelRatio || 1);
    const w = Math.max(40, Math.round(r.width || 220)), hgt = Math.max(40, Math.round(r.height || 110));
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(hgt * dpr);
    const g = canvas.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, hgt);
    const side = Math.min(w, hgt) - 4, ox = (w - side) / 2, oy = (hgt - side) / 2, k = side / INTERPOSER_MM;
    g.fillStyle = "#2b3944";
    g.fillRect(ox, oy, side, side);
    const f = drawableField(L);
    if (f) { g.imageSmoothingEnabled = false; g.drawImage(fieldCanvasOf(L, f), ox, oy, side, side); }
    for (const d of dieRects(L.dies) ?? []) {
      const x = ox + d.x0 * k, y = oy + (INTERPOSER_MM - d.y1) * k, dw = d.w * k, dh = d.h * k;
      if (!f) { g.fillStyle = KIND_FILL[d.kind]; g.fillRect(x, y, dw, dh); }
      g.strokeStyle = KIND_LINE[d.kind];
      g.lineWidth = 1.2;
      g.strokeRect(x + 0.5, y + 0.5, dw - 1, dh - 1);
    }
    g.strokeStyle = "rgba(214,226,229,.35)";
    g.strokeRect(ox + 0.5, oy + 0.5, side - 1, side - 1);
  }
  function renderStatus(line) {
    const src = D.source === "api" && !D.liveDown ? `Live · ${DOOR_RESULTS_PATH} and ${DOOR_EVENTS_PATH.split("/").pop()}${D.feed?.state.polls ? ` · ${D.feed.state.polls} requests` : ""}` : "Replay · bundled door fixture (arrival order)";
    $("statusLeft").textContent = `${src}${line === "staging" ? " · staging" : ""}`;
    $("statusMid").textContent = "Layouts are named only by class and a 4-character short id. No visitor text is shown.";
    $("hotkeys").textContent = "Space play · ←/→ step · H halo + lattice · E explode · O orbit · F fit · 2/3 view";
  }

  // ── replay and live ──
  function stop() { if (D.playing) clearInterval(D.playing); D.playing = null; renderDom(); }
  function play() {
    stop();
    if (D.list.length < 2) return;
    D.playing = setInterval(() => { show((D.idx + 1) % D.list.length); }, REDUCED ? DWELL_MS + 3000 : DWELL_MS);
    renderDom();
  }
  function step(delta) { stop(); D.following = false; show(D.idx + delta); }
  function useList(list, { follow = D.following } = {}) {
    const prevId = shown()?.id ?? null;
    const prev = shown();
    D.list = list;
    let idx = follow ? list.length - 1 : Math.max(0, list.findIndex((l) => l.id === prevId));
    if (idx < 0) idx = 0;
    const next = list[idx];
    const changed = !prev || !next || prev !== next;
    D.idx = list.length ? idx : -1;
    if (changed) render({ animate: Boolean(prev) });
    else renderDom();
    for (const l of list) {
      if (D.announced.has(`${l.id}:${l.status}`)) continue;
      D.announced.add(`${l.id}:${l.status}`);
      if (D.source === "api" && !D.liveDown) $("announce").textContent = `${l.label}: ${(STATUS_CHIP[l.status] ?? ["", l.status])[1].toLowerCase()}`;
    }
  }
  function onFeed(state) {
    if (D.source !== "api") return;               // replay was selected: a late live answer changes nothing
    const down = state.connected === false;
    if (down !== D.liveDown) {
      D.liveDown = down;
      if (down) { useList(D.fixture?.layouts ?? [], { follow: false }); play(); return; }
      stop();
      D.following = true;   // back from the labelled replay: show the newest arrival again
    }
    if (!down) useList(state.layouts, { follow: D.following });
    else renderDom();
  }
  async function setSource(src) {
    if (src === D.source) return;
    D.source = src;
    stop();
    if (src === "api") {
      D.following = true;
      D.liveDown = false;
      if (!D.feed) D.feed = createDoorFeed({ onChange: onFeed });
      useList(D.feed.state.layouts, { follow: true });
      D.feed.start();
    } else {
      D.feed?.stop();
      D.liveDown = false;
      useList(D.fixture?.layouts ?? [], { follow: false });
      play();
    }
  }

  // ── view toggles ──
  function setOverlay(on) { D.overlay = on; D.v3?.setOverlay(on); renderDom(); }
  function setOrbit(on) { D.orbit = on && !REDUCED; D.v3?.setAutoOrbit(D.orbit); renderDom(); }
  function setExplode(on) {
    if (!D.v3 || !D.current) return;
    const from = D.explode, to = on ? 1 : 0, start = performance.now();
    cancelAnimationFrame(D.explodeAnim);
    const tick = (now) => {
      if (!D.v3) { D.explodeAnim = null; return; }   // the view was released while this step was queued
      const t = REDUCED ? 1 : Math.min(1, (now - start) / EXPLODE_MS);
      const e = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
      D.explode = from + (to - from) * e;
      if (D.current) D.v3.setDoor(D.current.model, displayFor(D.current.model), { field: D.current.field, animate: false, notScored: tag3d(D.current.L, D.current.field) });
      if (t < 1) D.explodeAnim = requestAnimationFrame(tick);
      else { D.v3.fit({ animate: true }); renderDom(); }
    };
    D.explodeAnim = requestAnimationFrame(tick);
  }

  // ── wiring ──
  for (const b of $("dSource").querySelectorAll("button")) b.onclick = () => setSource(b.dataset.src);
  $("dPlay").onclick = () => (D.playing ? stop() : play());
  $("dScrub").oninput = (e) => { stop(); D.following = false; show(Number(e.target.value)); };
  $("dOverlay").onclick = () => setOverlay(!D.overlay);
  $("dExplode").onclick = () => setExplode(D.explode < 0.5);
  $("dOrbit").onclick = () => setOrbit(!D.orbit);
  $("dFit").onclick = () => D.v3?.home();
  for (const b of document.querySelectorAll(".controls.door .rseg button")) b.onclick = () => setRenderer(b.dataset.r);   // user: the wanted renderer
  $("limitsLink").onclick = (e) => { e.preventDefault(); $("limits").showModal(); };
  $("limitsClose").onclick = () => $("limits").close();
  document.addEventListener("keydown", (e) => {
    if (e.target.matches("input, select, textarea") || document.querySelector("dialog[open]")) return;
    if (e.key === " " && e.target.closest("button, a")) return;
    if (e.target === $("main3d") && e.key.startsWith("Arrow")) return;   // the canvas orbits with its arrows
    if (e.key === " ") { e.preventDefault(); D.playing ? stop() : play(); }
    else if (e.key === "ArrowRight") { e.preventDefault(); step(1); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); step(-1); }
    else if (e.key === "h" || e.key === "H") setOverlay(!D.overlay);
    else if (e.key === "e" || e.key === "E") setExplode(D.explode < 0.5);
    else if (e.key === "o" || e.key === "O") setOrbit(!D.orbit);
    else if (e.key === "f" || e.key === "F") D.v3?.home();
    else if (e.key === "2") setRenderer("2d");
    else if (e.key === "3") setRenderer("3d");
  });
  setInterval(() => { if (D.source === "api") renderDom(); }, 1000);   // the LIVE age ticks on the client clock

  // A read-only test hook for real-browser checks: facts only, no control.
  Object.defineProperty(window, "__package3d", { value: Object.freeze({ facts: () => {
    const st = D.v3?.stats() ?? null;
    const L = shown();
    const fig = $("p3d-figure").getBoundingClientRect();
    return { feed: "door", renderer: D.r, source: D.source, liveDown: D.liveDown, count: D.list.length, idx: D.idx,
      label: L?.label ?? null, status: L?.status ?? null, scored: Boolean(L?.result), map: Boolean(D.current?.field),
      line: $("modeText").textContent, overlay: D.overlay, explode: D.explode, geometryKey: D.current?.model.geometry_key ?? null,
      fieldState: L?.result?.field_state ?? null, fieldKey: D.current?.field?.key ?? null, tempLabel: L?.result?.label?.state ?? null,
      evaluator: L?.result?.evaluator ?? null, diagnostic: L?.result?.diagnostic ?? null, events: D.feed?.state.events.length ?? 0,
      cursor: D.feed?.state.cursor ?? null, eventsCursor: D.feed?.state.eventsCursor ?? null, refused: { ...(D.feed?.state.refused ?? {}) },
      notice: !$("wnotice").hidden, noCrypto: D.noCrypto, lost: D.lost, live3d: live3d.count,
      figure: { x: Math.round(fig.x), y: Math.round(fig.y), w: Math.round(fig.width), h: Math.round(fig.height) }, ...(st ?? {}) };
  } }) });

  // ── start ──
  $("feedDoor").classList.add("on");
  $("labLink").href = "../";
  try {
    const fixture = await loadFixture();
    D.fixture = { ...fixture, layouts: await verifyPinnedFields(fixture.layouts, { subtle: globalThis.crypto?.subtle ?? null }) };
  } catch (e) {
    D.fixtureError = `The bundled fixture could not be read (${String(e?.message ?? e).slice(0, 80)}).`;
    D.fixture = { layouts: [], refused: {} };
  }
  await setRenderer(D.r, D.why2d);
  if (D.source === "api") {
    D.source = "fixture";
    await setSource("api");
  } else {
    D.following = false;
    useList(D.fixture.layouts, { follow: false });
    show(Math.max(0, Math.min(D.fixture.layouts.length - 1, Number(params.get("i") ?? 0) || 0)), { animate: false });
    if (params.get("play") !== "0") play();
  }
}
