// SentiLab Package view: our own animated render of the chiplet package, driven by the verified evidence stream.
// Data comes only through source.mjs (the same verifier and pins as the Lab view); the scene through scene.mjs
// (pure, also used by the CLI); the drawing through render.mjs (hand-written Canvas 2D). Every string from an
// envelope reaches the page through textContent, never innerHTML.
import { DEMO, CONTRACT_VERSION, setupTrust, parseReplay, runIdFromFile, isDrill, verifyRun, chainSummary, modeNow, createLiveFeed, reasonText } from "./source.mjs";
import { sceneAt, runFrame, scaleTicks, describeEvent, TRACK_ORDER, TRACKS, trackName } from "./scene.mjs";
import { drawPackage, TrackAnimation, HOME_AZIMUTH, ORBIT_MS, easeInOut } from "./render.mjs";

const params = new URLSearchParams(location.search);
const $ = (id) => document.getElementById(id);
const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
const STEP_MS = REDUCED ? 1300 : 800;
const ORBIT_EVERY_MS = 6500;

// ── tiny DOM helper: text only ────────────────────────────────────────────────────────────────────────────────
function h(tag, props, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props ?? {})) {
    if (v == null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : String(v));
  }
  for (const kid of kids.flat(Infinity)) if (kid != null && kid !== false) node.append(kid instanceof Node ? kid : String(kid));
  return node;
}
const fmt = (v, d = 1) => (typeof v === "number" && Number.isFinite(v) ? v.toFixed(d) : "-");

// Where a lifecycle sits, for the chip colour (display only; the state itself is project()'s).
const KIND = {
  accepted: "won", non_improving_current: "lost", within_margin: "lost", non_improving: "lost", tie: "lost", inconclusive: "lost",
  rejected_schema: "out", rejected_constraints: "out", failed_run: "out", reproduction_failed: "out", cancelled: "out",
};
const lifeKind = (l) => KIND[l] ?? "open";
const NO_TEMPS = { rejected_schema: "not simulated (schema rejected)", rejected_constraints: "not simulated (failed the constraint check)", failed_run: "simulation failed", cancelled: "cancelled" };

// ── state ───────────────────────────────────────────────────────────────────────────────────────────────────
const S = {
  trust: null,
  source: params.get("src") === "live" ? "api" : "file",
  file: null,            // { label, runId, runIdFrom, isDemo, envelopes, verification, frame, fullScene, error }
  live: null,            // created on first switch to live
  liveSrc: { verification: null, frame: null, fullScene: null, envelopes: [] },
  cursor: 0, cursors: {}, following: true,
  scene: null,
  selected: TRACK_ORDER.includes(params.get("track")) ? params.get("track") : "board",
  playing: null,
  lid: params.has("lid") ? params.get("lid") !== "0" : !matchMedia("(max-width: 760px)").matches,   // phones: off unless asked
  orbit: false, orbitTimer: null,
  az: { from: HOME_AZIMUTH, to: HOME_AZIMUTH, start: 0 },
};
const anims = Object.fromEntries(TRACK_ORDER.map((t) => [t, new TrackAnimation()]));
const active = () => (S.source === "api" ? S.liveSrc : S.file);
const total = () => active()?.verification?.ordered.length ?? 0;

// ── canvases ────────────────────────────────────────────────────────────────────────────────────────────────
const surfaces = new Map();      // name -> { canvas, ctx, w, h }
function surface(name, canvas) {
  const ctx = canvas.getContext("2d");
  const s = { canvas, ctx, w: 0, h: 0 };
  surfaces.set(name, s);
  new ResizeObserver(() => { sizeSurface(s); requestDraw(); }).observe(canvas);
  sizeSurface(s);
  return s;
}
function sizeSurface(s) {
  const r = s.canvas.getBoundingClientRect();
  const dpr = Math.min(3, window.devicePixelRatio || 1);
  s.w = Math.max(1, Math.round(r.width)); s.h = Math.max(1, Math.round(r.height));
  s.canvas.width = Math.round(s.w * dpr); s.canvas.height = Math.round(s.h * dpr);
  s.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

// ── the strip ───────────────────────────────────────────────────────────────────────────────────────────────
const tiles = new Map();
function buildStrip() {
  const strip = $("strip");
  for (const [i, t] of TRACK_ORDER.entries()) {
    const canvas = h("canvas", { "aria-hidden": "true" });
    const chip = h("span", { class: "chip" });
    const j = h("span", { class: "j" });
    const id = h("span", { class: "id" });
    const none = h("div", { class: "none" }, "no candidate yet");
    const btn = h("button", { type: "button", class: "tile", style: `--lab:${TRACKS[t].color}`, "data-track": t, title: `Show ${TRACKS[t].name} (${i})`, "aria-label": `Show ${TRACKS[t].name}` },
      h("div", { class: "th" }, h("b", { style: `color:${TRACKS[t].color}` }, TRACKS[t].name), chip),
      h("div", { class: "tc" }, canvas, none),
      h("div", { class: "tf" }, j, id));
    btn.addEventListener("click", () => select(t));
    strip.append(btn);
    tiles.set(t, { btn, chip, j, id, none, surf: surface(`tile:${t}`, canvas) });
  }
  const picker = $("picker");
  picker.replaceChildren(...TRACK_ORDER.map((t) => h("option", { value: t }, TRACKS[t].name)));
  picker.onchange = () => select(picker.value);
}

function select(track) {
  if (!TRACK_ORDER.includes(track)) return;
  S.selected = track;
  $("picker").value = track;
  renderDom();
  requestDraw();
}

// ── keys and loading ────────────────────────────────────────────────────────────────────────────────────────
async function loadReplay({ url, text, label, runId, isDemo, at = null }) {
  stop();
  try {
    if (text === undefined) {
      const r = await fetch(url, { cache: "no-store" });
      if (!r.ok) throw new Error(`${url} answered ${r.status}`);
      text = await r.text();
    }
  } catch (error) {
    S.file = { label, runId: runId ?? "", runIdFrom: "requested", isDemo, envelopes: [], verification: null, error: String(error.message ?? error) };
    S.scene = null;
    renderDom();
    return;
  }
  const envelopes = parseReplay(text);
  let runIdFrom = "requested";
  if (!runId) { runId = runIdFromFile(envelopes); runIdFrom = "file"; }
  const verification = await verifyRun(envelopes, { runId, trust: S.trust });
  // One frame per run: the scale and the footprint come from the whole verified prefix, so they never change
  // while the playhead moves.
  const frame = runFrame(verification.prefixEnvelopes, verification.projection);
  const fullScene = sceneAt(verification.prefixEnvelopes, verification.prefixCount, frame);
  S.file = { label, runId, runIdFrom, isDemo, envelopes, verification, frame, fullScene };
  if (S.source !== "file") return;
  for (const a of Object.values(anims)) a.set(null);
  if (verification.prefixCount === 0) {
    // Nothing verifies: there is nothing to play. Show the whole list's state (frozen at seq 0) with the reason.
    setCursor(verification.ordered.length);
  } else if (at !== null && Number.isInteger(at) && at >= 0) {
    setCursor(verification.ordered.filter((e, i) => verification.rows[i].seq !== null && verification.rows[i].seq <= at).length);
  } else {
    setCursor(0);
    play();
  }
}

// ── the playhead ────────────────────────────────────────────────────────────────────────────────────────────
function setCursor(n, { stepwise = false } = {}) {
  const src = active();
  const v = src?.verification;
  const prev = S.scene;
  S.cursor = Math.max(0, Math.min(n, v ? v.ordered.length : 0));
  if (!v || !src.frame) { S.scene = null; renderDom(); requestDraw(); return; }
  // Rule 1: the drawing is the scene of the projectable prefix, as far as the playhead has reached. Envelopes after
  // the prefix move the playhead but never the package.
  const k = Math.min(S.cursor, v.prefixCount);
  S.scene = sceneAt(v.prefixEnvelopes, k, src.frame);
  const animate = stepwise && !REDUCED && prev !== null && S.scene.at.seq === prev.at.seq + 1;
  const crossed = animate ? S.scene.timeline.filter((e) => e.seq === S.scene.at.seq) : [];
  const now = performance.now();
  for (const track of S.scene.tracks) {
    const move = crossed.find((e) => e.kind === "move" && e.track === track.track) ?? null;
    const pulse = animate && track.track === "board" && crossed.some((e) => e.kind === "accept");
    anims[track.track].set(track.layout, { move, animate, pulse, accepted: track.track === "board" && track.showing === "accepted", now });
  }
  renderDom();
  requestDraw();
}
function stop() { if (S.playing) clearInterval(S.playing); S.playing = null; $("play").textContent = "▶"; $("play").setAttribute("aria-label", "Play"); }
function play() {
  stop();
  if (S.source === "api") { S.following = true; setCursor(total()); return; }
  if (S.cursor >= total()) setCursor(0);
  $("play").textContent = "❚❚"; $("play").setAttribute("aria-label", "Pause");
  S.playing = setInterval(() => { if (S.cursor >= total()) return stop(); setCursor(S.cursor + 1, { stepwise: true }); }, STEP_MS);
}
function step(delta) {
  stop();
  if (S.source === "api") S.following = false;
  setCursor(S.cursor + delta, { stepwise: delta === 1 });
  if (S.source === "api" && S.cursor === total()) S.following = true;
}

// ── camera ──────────────────────────────────────────────────────────────────────────────────────────────────
function azimuthAt(now) {
  const { from, to, start } = S.az;
  if (from === to || REDUCED) return to;
  const t = Math.min(1, (now - start) / ORBIT_MS);
  return from + (to - from) * easeInOut(t);
}
function rotate(deltaDeg) {
  const now = performance.now();
  S.az = { from: azimuthAt(now), to: S.az.to + deltaDeg, start: now };
  requestDraw();
}
function setOrbit(on) {
  S.orbit = on;
  $("orbit").setAttribute("aria-pressed", String(on));
  clearInterval(S.orbitTimer);
  if (on) { rotate(90); S.orbitTimer = setInterval(() => rotate(90), ORBIT_EVERY_MS); }
}
function setLid(on) { S.lid = on; $("lid").setAttribute("aria-pressed", String(on)); requestDraw(); }

// ── drawing ─────────────────────────────────────────────────────────────────────────────────────────────────
let raf = 0;
function requestDraw() { if (!raf) raf = requestAnimationFrame(drawAll); }
function drawAll(now) {
  raf = 0;
  const src = active();
  const footprint = src?.frame?.footprint ?? null;
  const unit = src?.frame?.scale?.unit ?? "";
  let busy = false;
  const az = azimuthAt(now);
  if (az !== S.az.to) busy = true;
  const main = surfaces.get("main");
  const mf = anims[S.selected].frame(now);
  busy ||= mf.active;
  const hasMain = footprint && S.scene && S.scene.tracks.find((t) => t.track === S.selected)?.layout;
  const compactMain = main.w < 700;
  drawPackage(main.ctx, hasMain ? { ...mf, footprint, unit } : null, {
    width: main.w, height: main.h, azimuthDeg: az, labels: true, callouts: !compactMain, lid: S.lid,
    pad: compactMain ? { l: 12, r: 12, t: 12, b: 12 } : { l: Math.min(250, main.w * 0.18), r: 24, t: 20, b: 26 },
  });
  for (const [t, tile] of tiles) {
    const fr = t === S.selected ? mf : anims[t].frame(now);
    if (t !== S.selected) busy ||= fr.active;
    const has = footprint && S.scene && S.scene.tracks.find((x) => x.track === t)?.layout;
    drawPackage(tile.surf.ctx, has ? { ...fr, footprint, unit } : null, {
      width: tile.surf.w, height: tile.surf.h, azimuthDeg: HOME_AZIMUTH, labels: false, callouts: false, lid: false, balls: false, pad: { l: 6, r: 6, t: 4, b: 4 },
    });
  }
  if (busy) requestDraw();
}

// ── DOM ─────────────────────────────────────────────────────────────────────────────────────────────────────
function renderDom() {
  const src = active();
  const v = src?.verification ?? null;
  renderTop(src, v);
  renderControls(src, v);
  renderFrozen(v);
  renderMain(src, v);
  renderInfo(src);
  renderStrip();
  renderOffline();
}

function renderTop(src, v) {
  const m = modeNow(S.source === "api" ? "api" : "file", S.live?.state ?? {}, Date.now());
  $("mode").className = `mode ${m.toLowerCase()}`;
  $("modeText").textContent = m;
  $("drill").hidden = !(src && isDrill(src.envelopes ?? []));
  $("testKeys").hidden = !S.trust?.testMode;
  const meta = $("runMeta");
  meta.replaceChildren();
  const runId = S.source === "api" ? S.live?.state.runId : src?.runId;
  if (runId) {
    // Run facts come only from the verified prefix.
    const run = S.scene?.run ?? null;
    meta.append(h("span", null, "run ", h("b", null, runId)));
    if (run && v?.prefixCount > 0) meta.append(h("span", null, "arm ", h("b", null, String(run.arm ?? "-"))), h("span", { class: "opt" }, "seed ", h("b", null, String(run.seed ?? "-"))));
    else meta.append(h("span", null, src?.runIdFrom === "file" ? "(run id taken from the file you opened)" : "(requested; nothing verified yet)"));
  }
  const chain = $("chain");
  if (!v || v.rows.length === 0) { chain.className = "chain"; $("chainText").textContent = "no envelopes"; return; }
  const sum = chainSummary(v.rows);
  chain.className = `chain ${sum.ok ? "ok" : "bad"}`;
  $("chainText").textContent = `${sum.verified}/${sum.total} verified${sum.ok ? "" : ` · ${sum.phrases.join(" · ")}`}${S.trust?.testMode ? " · test keys" : ""}`;
}

function renderControls(src, v) {
  const max = v ? v.ordered.length : 0;
  $("scrub").max = String(max);
  $("scrub").value = String(S.cursor);
  const seqAt = S.cursor > 0 && v ? v.rows[S.cursor - 1].seq : 0;
  const lastSeq = max > 0 ? v.rows.reduce((m, r) => (Number.isSafeInteger(r.seq) ? Math.max(m, r.seq) : m), 0) : 0;
  $("pos").textContent = `seq ${seqAt ?? "?"} / ${lastSeq}`;
  $("fixture").hidden = !(S.source === "file" && src?.isDemo);
  $("fixNote").hidden = $("fixture").hidden;
  $("openLabel").hidden = S.source !== "file";
  $("statusLeft").textContent = S.source === "api" ? `Live · /api/view/events${S.live?.state.runId ? ` · run ${S.live.state.runId}` : ""}` : src ? `Replay · ${src.label}` : "Replay";
}

let ticksFor = null;
function renderTicks(src, v) {
  const key = v ? `${S.source}:${v.total}:${v.prefixCount}` : "";
  if (ticksFor === key) return;
  ticksFor = key;
  const box = $("ticks");
  box.replaceChildren();
  if (!v || v.total === 0) return;
  const pct = (n) => `${(n / v.total) * 100}%`;
  if (v.prefixCount < v.total) box.append(h("span", { class: "after", style: `left:${pct(v.prefixCount)};right:0`, title: "after the break: never drawn" }));
  for (const e of src.fullScene?.timeline ?? []) {
    if (!["move", "accept", "withdraw", "gate", "out"].includes(e.kind) || (e.kind === "move" && e.track === "board")) continue;
    const color = e.kind === "move" ? TRACKS[e.track]?.color : null;
    box.append(h("i", { class: e.kind, style: `left:${pct(e.seq)}${color ? `;background:${color}` : ""}` }));
  }
}

function renderFrozen(v) {
  const el = $("frozen");
  el.replaceChildren();
  if (!v || S.cursor <= v.prefixCount || !v.firstBreak) { el.hidden = true; return; }
  const fb = v.firstBreak;
  el.className = `frozen${fb.keyOnly ? " cfg" : ""}`;
  el.hidden = false;
  el.append(v.label ?? `chain broken after seq ${v.prefixEnd}; board frozen at seq ${v.prefixEnd}`,
    h("span", null, ` · seq ${fb.seq ?? "?"} is ${fb.status === "verified" ? "not projectable" : "unverified"}: ${fb.text || "unknown"}${fb.keyOnly && S.trust.pins.length === 0 ? " (the production pin list is empty until the core key exists)" : ""}. Nothing from it or after it is drawn.`));
}

function emptyState(src, v) {
  if (S.source === "api" && S.live?.state.connected !== true) return null;
  if (src?.error) return ["Replay not loaded", src.error];
  if (!v || v.ordered.length === 0) return S.source === "api" ? ["Waiting for envelopes", "Connected; this run has no envelopes yet."] : ["Nothing loaded", "No replay file."];
  if (v.prefixCount === 0) {
    const note = S.trust?.note ? `${S.trust.note[0].toUpperCase()}${S.trust.note.slice(1)}.` : "";
    return ["Nothing verified to draw", `${note} The package is drawn only from the verified prefix of the chain, so there is nothing to show. ${v.total} envelope${v.total === 1 ? "" : "s"} received, 0 verified.`];
  }
  if (!S.scene || S.scene.at.count === 0) return ["Ready", "Press Space to play, or → to step one envelope."];
  const t = S.scene.tracks.find((x) => x.track === S.selected);
  if (!t?.layout) return S.selected === "board" ? ["No layout yet", "The board shows the initial layout once the core's first measurement is verified."] : [`${TRACKS[S.selected].name} has no candidate yet`, "Its package appears when the lab proposes a layout."];
  return null;
}

function renderMain(src, v) {
  renderTicks(src, v);
  const empty = emptyState(src, v);
  $("mainEmpty").hidden = !empty;
  if (empty) { $("emptyTitle").textContent = empty[0]; $("emptyText").textContent = empty[1]; }
  const t = S.scene?.tracks.find((x) => x.track === S.selected) ?? null;
  const L = t?.layout ?? null;
  $("mainTitle").textContent = TRACKS[S.selected].name;
  $("mainTitle").style.color = S.selected === "board" ? "" : TRACKS[S.selected].color;
  const chip = $("mainChip");
  let sub = "";
  if (L && S.selected === "board") {
    if (t.showing === "accepted") {
      sub = `${L.ref.id} · ${trackName(L.ref.lab)} · accepted by the gate at seq ${t.accepted.seq}`;
      chip.className = "chip won"; chip.textContent = "ACCEPTED"; chip.hidden = false;
    } else {
      sub = `initial layout ${L.ref.id} (core measurement) · nothing accepted yet`;
      chip.className = "chip init"; chip.textContent = "INITIAL"; chip.hidden = false;
    }
  } else if (L) {
    sub = `${L.ref.id} · proposed at seq ${L.ref.seq}${t.on_board ? " · on the board" : ""}`;
    chip.className = `chip ${lifeKind(L.lifecycle)}`; chip.textContent = L.lifecycle ?? ""; chip.hidden = !L.lifecycle;
  } else chip.hidden = true;
  $("mainSub").textContent = sub;
  $("mainCanvas").setAttribute("aria-label", L
    ? `${TRACKS[S.selected].name}: ${L.ref.id}, ${L.chiplets.length} chiplets${L.J ? `, J ${fmt(L.J.value)} ${L.J.unit}` : ", no temperatures"}. Isometric drawing; colours are chiplet-centre temperatures.`
    : "No package drawn");
  $("picker").value = S.selected;

  // Caption: what the playhead just did (from the prefix's timeline), or why the package is not moving.
  const cap = $("caption");
  cap.replaceChildren();
  if (v && S.cursor > v.prefixCount && v.prefixCount > 0) {
    cap.append(h("b", null, `seq ${v.rows[S.cursor - 1]?.seq ?? "?"} is after the break`), " · not drawn; the package stays at seq ", String(v.prefixEnd));
  } else if (S.scene && S.scene.timeline.length) {
    const last = S.scene.timeline[S.scene.timeline.length - 1];
    const stepSeq = S.scene.at.seq;
    cap.append(last.seq === stepSeq ? h("b", null, describeEvent(last)) : describeEvent(last));
  }
}

function renderInfo(src) {
  const t = S.scene?.tracks.find((x) => x.track === S.selected) ?? null;
  const L = t?.layout ?? null;
  const nothing = (src?.verification?.prefixCount ?? 0) === 0;
  $("infoLbl").textContent = nothing ? `${TRACKS[S.selected].name} · nothing verified` : S.selected === "board" ? (t?.showing === "accepted" ? "Board · accepted package" : "Board · before any acceptance") : `${TRACKS[S.selected].name} · current candidate`;
  $("infoName").textContent = L ? L.ref.id : nothing ? "Nothing drawn" : "No package yet";
  $("metrics").hidden = !L;
  $("infoName").style.color = L && L.ref.lab && TRACKS[L.ref.lab] ? TRACKS[L.ref.lab].color : "";
  $("infoId").textContent = L ? (L.ref.kind === "measurement" ? "core measurement" : `by ${trackName(L.ref.lab)}`) : "";
  const chips = $("infoChips");
  chips.replaceChildren();
  if (L) {
    if (L.lifecycle) chips.append(h("span", { class: `chip ${lifeKind(L.lifecycle)}` }, L.lifecycle));
    chips.append(h("span", { class: `chip v-${L.validity}`, title: "Validity from the evidence contract's project(): whether its support still stands" }, `evidence: ${L.validity}`));
    if (L.scenario_id) chips.append(h("span", { class: "chip lost" }, L.scenario_id));
  }
  $("infoJ").textContent = L?.J ? `${fmt(L.J.value)} ${L.J.unit}` : "-";
  $("infoJ").className = L?.temps_from?.state === "stale" ? "stale" : "";
  $("infoW").textContent = L?.W ? `W ${fmt(L.W.value)} ${L.W.metric_id}` : "";
  const srcEl = $("infoSrc");
  srcEl.className = "src";
  if (!L) srcEl.textContent = "";
  else if (!L.temps_from) srcEl.textContent = `no temperatures · ${NO_TEMPS[L.lifecycle] ?? "awaiting simulation"}`;
  else if (L.temps_from.state === "stale") { srcEl.className = "src stale"; srcEl.textContent = `values from ${L.temps_from.measurement} · STALE (${L.temps_from.validity})`; }
  else if (L.temps_from.via_alternative) { srcEl.className = "src alt"; srcEl.textContent = `values via ${L.temps_from.measurement} (set ${L.temps_from.set_id}) · set ${L.temps_from.broken_sets.join(", ")} broken`; }
  else srcEl.textContent = L.temps_from.set_id ? `values from ${L.temps_from.measurement} · support set ${L.temps_from.set_id}` : `values from ${L.temps_from.measurement} (its own)`;
  if (L && L.overlaps.length) srcEl.textContent += ` · overlap: ${L.overlaps.map((o) => `${o.a}/${o.b}`).join(", ")}`;

  // Legend: the run's one fixed scale.
  const scale = src?.frame?.scale ?? null;
  const ticks = $("scaleTicks");
  ticks.replaceChildren();
  $("scaleBarBox").hidden = !scale;
  ticks.hidden = !scale;
  $("noScale").hidden = !!scale;
  $("scaleUnit").textContent = scale?.unit ? `· ${scale.unit}, fixed` : "";
  if (scale) for (const v of scaleTicks(scale)) ticks.append(h("span", { style: `left:${((v - scale.min) / (scale.max - scale.min)) * 100}%` }, String(v)));

  // Drill: what the withdrawal did, straight from project().
  const box = $("drillBox");
  box.replaceChildren();
  const d = S.scene?.drill ?? null;
  if (!d) { box.hidden = true; return; }
  box.hidden = false;
  box.append(h("div", { class: "lbl" }, "Correction drill"));
  for (const w of d.withdrawn) box.append(h("p", null, h("b", null, w.node), ` withdrawn at seq ${w.seq ?? "?"}${w.reason ? ` · ${w.reason}` : ""}`));
  box.append(h("p", null, "went stale: ", d.stale.length ? d.stale.map((s) => s.node).join(", ") : "none"));
  if (d.survived.length) box.append(h("p", null, "still valid on another support set: ", d.survived.join(", ")));
}

function renderStrip() {
  for (const [t, tile] of tiles) {
    const track = S.scene?.tracks.find((x) => x.track === t) ?? null;
    const L = track?.layout ?? null;
    tile.btn.classList.toggle("sel", t === S.selected);
    tile.btn.setAttribute("aria-pressed", String(t === S.selected));
    const nothing = (active()?.verification?.prefixCount ?? 0) === 0;
    tile.none.hidden = !!L || (!nothing && (!S.scene || S.scene.at.count === 0));
    tile.none.textContent = nothing ? "nothing verified" : t === "board" ? "no layout yet" : "no candidate yet";
    tile.j.hidden = !L;
    if (t === "board") {
      tile.chip.className = `chip ${track?.showing === "accepted" ? "won" : "init"}`;
      tile.chip.textContent = track?.showing === "accepted" ? `accepted · seq ${track.accepted.seq}` : track?.showing === "initial" ? "initial layout" : "";
    } else {
      tile.chip.className = `chip ${L ? lifeKind(L.lifecycle) : ""}`;
      tile.chip.textContent = L?.lifecycle ?? "";
    }
    tile.chip.hidden = !tile.chip.textContent;
    tile.j.replaceChildren(h("small", null, "J"), L?.J ? `${fmt(L.J.value)}` : "-");
    tile.id.textContent = L ? L.ref.id : "";
  }
}

function renderOffline() {
  const off = $("offline");
  if (S.source !== "api" || S.live?.state.connected === true) { off.hidden = true; return; }
  off.hidden = false;
  const st = S.live?.state;
  $("offTitle").textContent = !st || st.connected === null ? "Connecting to the live feed…" : "Live feed not connected";
  $("offText").textContent = !st || st.connected === null ? "Asking /api/view/runs." :
    `The page asks /api/view/runs every 5 s and gets no answer (${st.error || "no response"}). The core that serves the live routes is not running yet. The replay is still available.`;
}

// ── live ────────────────────────────────────────────────────────────────────────────────────────────────────
function onLive() {
  const st = S.live.state;
  const v = st.verification;
  if (v && v !== S.liveSrc.verification) {
    // A live run can only widen its scale and footprint, never shift or narrow them (the Lab view's rule).
    const f = runFrame(v.prefixEnvelopes, v.projection), old = S.liveSrc.frame;
    const frame = !old ? f : {
      scale: old.scale && f.scale ? { ...f.scale, min: Math.min(old.scale.min, f.scale.min), max: Math.max(old.scale.max, f.scale.max) } : f.scale ?? old.scale,
      footprint: old.footprint && f.footprint ? widen(old.footprint, f.footprint) : f.footprint ?? old.footprint,
    };
    S.liveSrc = { verification: v, frame, fullScene: sceneAt(v.prefixEnvelopes, v.prefixCount, frame), envelopes: st.envelopes };
    if (S.source === "api" && S.following) { const before = S.cursor; setCursor(v.ordered.length, { stepwise: v.ordered.length === before + 1 }); return; }
  }
  if (S.source === "api") renderDom();
}
const widen = (a, b) => Object.fromEntries(Object.entries(a).map(([k, r]) => [k, typeof r === "object" ? { x0: Math.min(r.x0, b[k].x0), y0: Math.min(r.y0, b[k].y0), x1: Math.max(r.x1, b[k].x1), y1: Math.max(r.y1, b[k].y1) } : r]));

function setSource(src) {
  if (S.source === src) return;
  stop();
  S.cursors[S.source] = S.cursor;
  S.source = src;
  for (const b of $("source").querySelectorAll("button")) b.classList.toggle("on", b.dataset.src === src);
  ticksFor = null;
  for (const a of Object.values(anims)) a.set(null);
  S.scene = null;
  if (src === "api") {
    if (!S.live) S.live = createLiveFeed({ trust: S.trust, runId: params.get("run"), onChange: onLive });
    S.following = true;
    S.live.start();
    setCursor(total());
  } else {
    S.live?.stop();
    setCursor(Math.min(S.cursors.file ?? 0, total()));
  }
}

// ── chain dialog ────────────────────────────────────────────────────────────────────────────────────────────
function showChain() {
  const src = active(), v = src?.verification;
  const kv = (rows) => h("div", { class: "kv" }, rows.map(([k, val]) => [h("div", { class: "k" }, k), h("div", { class: "v" }, val ?? "-")]));
  const rows = [
    ["envelope contract", CONTRACT_VERSION],
    ["pins in this page", S.trust.testMode ? `${S.trust.pins.length} (TEST KEYS)` : `${S.trust.pins.length}${S.trust.pins.length ? "" : " (production list is empty until the core key exists)"}`],
    ["key source", S.trust.note || "-"],
    ["run checked", src?.runId ? `${src.runId} (${src.runIdFrom === "file" ? "from the file you opened" : "requested by the page"})` : "-"],
  ];
  if (v) {
    rows.push(["verified", `${v.verified} of ${v.total}`], ["drawn prefix", v.prefixCount ? `seq 1 to ${v.prefixEnd} (${v.prefixCount} envelopes)` : "none"],
      ["first break", v.firstBreak ? `seq ${v.firstBreak.seq ?? "?"}: ${v.firstBreak.text}` : "none"],
      ["reasons", [...new Set(v.rows.flatMap((r) => r.reasons))].map((c) => `${c} (${reasonText(c)})`).join(", ") || "none"]);
  }
  $("chainBody").replaceChildren(kv(rows));
  $("chainDlg").showModal();
}

// ── wiring ──────────────────────────────────────────────────────────────────────────────────────────────────
$("play").onclick = () => (S.playing ? stop() : play());
$("scrub").oninput = (e) => { stop(); if (S.source === "api") S.following = false; setCursor(Number(e.target.value)); };
for (const b of $("source").querySelectorAll("button")) b.onclick = () => setSource(b.dataset.src);
$("backToReplay").onclick = () => setSource("file");
$("file").onchange = async (e) => {
  const f = e.target.files && e.target.files[0];
  if (!f) return;
  const text = await f.text();
  e.target.value = "";
  if (S.source !== "file") setSource("file");
  ticksFor = null;
  await loadReplay({ text, label: `${f.name} · opened file`, runId: null, isDemo: false });
};
$("rotL").onclick = () => rotate(-90);
$("rotR").onclick = () => rotate(90);
$("orbit").onclick = () => setOrbit(!S.orbit);
$("lid").onclick = () => setLid(!S.lid);
$("chain").onclick = showChain;
$("chainClose").onclick = () => $("chainDlg").close();
$("limitsLink").onclick = (e) => { e.preventDefault(); $("limits").showModal(); };
$("limitsClose").onclick = () => $("limits").close();
document.addEventListener("keydown", (e) => {
  if (e.target.matches("input, select, textarea") || document.querySelector("dialog[open]")) return;
  if (e.key === " " && e.target.closest("button, a")) return;
  if (e.key === " ") { e.preventDefault(); S.playing ? stop() : play(); }
  else if (e.key === "ArrowRight") { e.preventDefault(); step(1); }
  else if (e.key === "ArrowLeft") { e.preventDefault(); step(-1); }
  else if (e.key === "r" || e.key === "R") rotate(e.shiftKey ? -90 : 90);
  else if (e.key === "o" || e.key === "O") setOrbit(!S.orbit);
  else if (e.key === "l" || e.key === "L") setLid(!S.lid);
  else if (/^[0-5]$/.test(e.key)) select(TRACK_ORDER[Number(e.key)]);
});
setInterval(() => { if (S.source === "api") renderTop(active(), active()?.verification); }, 1000);   // the mode label ages on the client clock

// ── start ───────────────────────────────────────────────────────────────────────────────────────────────────
surface("main", $("mainCanvas"));
buildStrip();
setLid(S.lid);
for (const b of $("source").querySelectorAll("button")) b.classList.toggle("on", b.dataset.src === S.source);
if (!globalThis.crypto?.subtle) {
  // WebCrypto exists only in a secure context. Without it nothing can be verified, so nothing is drawn.
  $("frozen").hidden = false;
  $("frozen").textContent = "Signatures can't be checked here: this page needs a secure (https) connection. Nothing is drawn.";
  $("chainText").textContent = "cannot verify";
} else {
  S.trust = await setupTrust({ hostname: location.hostname, wantsTest: params.get("pins") === "test" });
  const bundle = params.get("bundle");
  const replay = bundle && /^[A-Za-z0-9._-]{1,128}$/.test(bundle)
    ? { url: `/api/replay/${encodeURIComponent(bundle)}.jsonl`, label: `/api/replay/${bundle}.jsonl`, runId: params.get("run") || null, isDemo: false }
    : { url: DEMO.url, label: DEMO.label, runId: DEMO.runId, isDemo: true };
  if (params.has("seq")) replay.at = Number(params.get("seq"));
  if (params.get("orbit") === "1") setOrbit(true);
  renderDom();
  if (S.source === "api") { S.source = "file"; setSource("api"); }
  await loadReplay(replay);
}
// A test hook for real-browser checks: read-only facts, no control over trust or data.
Object.defineProperty(window, "__packageView", { value: Object.freeze({ facts: () => ({ cursor: S.cursor, seq: S.scene?.at.seq ?? 0, selected: S.selected, prefix: active()?.verification?.prefixCount ?? 0, total: total() }) }) });
