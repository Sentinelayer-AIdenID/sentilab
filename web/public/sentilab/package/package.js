// SentiLab Package view: our own animated render of the chiplet package, driven by the verified evidence stream.
// Data comes only through source.mjs (the same verifier and pins as the Lab view); the scene through scene.mjs
// (pure, also used by the CLI); the drawing through render.mjs (hand-written Canvas 2D). Every string from an
// envelope reaches the page through textContent, never innerHTML.
import { DEMO, CONTRACT_VERSION, MAX_FILE_BYTES, setupTrust, fetchReplayBytes, verifyReplayFile, isDrill, chainSummary, modeNow, runStatusOf, createLiveFeed, reasonText } from "./source.mjs";
import { viewHref } from "../view-links.mjs";
import { shortId } from "../lab-model.mjs";
import { sceneAt, scaleTicks, describeEvent, describeSource, refusalText, spanText, TRACK_ORDER, TRACKS, trackName } from "./scene.mjs";
import { reconcile } from "./playhead.mjs";
import { drawPackage, TrackAnimation, HOME_AZIMUTH, ORBIT_MS, easeInOut } from "./render.mjs";

const params = new URLSearchParams(location.search);
const $ = (id) => document.getElementById(id);
const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
const STEP_MS = REDUCED ? 1300 : 800;
const ORBIT_EVERY_MS = 6500;

// ── tiny DOM helper: text only ────────────────────────────────────────────────────────────────────────────────
// A `style` prop goes through the CSSOM (style.cssText), never a style="" attribute: the page's Content-Security-Policy
// (style-src 'self') refuses inline style attributes, and allows the CSSOM.
function h(tag, props, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props ?? {})) {
    if (v == null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "style") node.style.cssText = String(v);
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
// Why a verified value was refused: scene.mjs refusalText (scene.errors codes). Refused values are never placed or coloured.
const FIELD = { geometry: "geometry", center_temps: "temperatures", J: "J", W: "W" };

// ── state ───────────────────────────────────────────────────────────────────────────────────────────────────
const S = {
  trust: null,
  source: params.get("src") === "live" ? "api" : "file",
  file: null,            // { label, runId, runIdFrom, isDemo, verification, frame, fullScene, error }
  live: null,            // created on first switch to live
  liveSrc: { verification: null, frame: null, fullScene: null },
  gen: 0,                // bumps on every verification change (ticks, banners and the scene are rebuilt)
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
const prefixK = () => active()?.verification?.prefixCount ?? 0;

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
// bytes: a picked file's raw bytes, or undefined to fetch url. Either way the 64 MiB replay cap is checked before a
// single row is decoded, and the file is never decoded whole (source.mjs, the Lab view's path).
async function loadReplay({ url, bytes, label, runId, isDemo, at = null }) {
  stop();
  let result;
  try {
    if (bytes === undefined) bytes = await fetchReplayBytes(url);
    result = await verifyReplayFile(bytes, { runId, trust: S.trust });
    if (!result.ok) throw new Error(result.error);
  } catch (error) {
    S.file = { label, runId: runId ?? "", runIdFrom: "requested", isDemo, verification: null, error: String(error.message ?? error) };
    applyScene(null);
    return;
  }
  const { verification, runIdFrom } = result;
  runId = result.runId;
  // A new file is a verification change like any other: one frame for the run (scale and footprint from its whole
  // verified prefix, fixed while the playhead moves), the playhead clamped to K, every animation cut.
  S.file = { label, runId, runIdFrom, isDemo, verification: null, frame: null, fullScene: null };
  adoptVerification(S.file, verification, { active: S.source === "file", following: false, fresh: true });
  if (S.source !== "file") return;
  if (verification.prefixCount === 0) {
    // Nothing verifies: there is nothing to play. The frozen banner and the empty state say why.
    setCursor(0);
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
  if (!v || !src.frame) { applyScene(null); return; }
  // Rule 1: the drawing is the scene of the projectable prefix, as far as the playhead has reached. Envelopes after
  // the prefix move the playhead but never the package.
  const k = Math.min(S.cursor, v.prefixCount);
  const scene = sceneAt(v.prefixEnvelopes, k, src.frame);
  applyScene(scene, { animate: stepwise && prev !== null && scene.at.seq === prev.at.seq + 1 });
}

// Show a scene: tween each track into it (a playhead step), or cut every animation to it (anything else).
function applyScene(scene, { animate = false } = {}) {
  S.scene = scene;
  const tween = animate && !REDUCED;
  const crossed = tween ? scene.timeline.filter((e) => e.seq === scene.at.seq) : [];
  const now = performance.now();
  for (const t of TRACK_ORDER) {
    const track = scene?.tracks.find((x) => x.track === t) ?? null;
    const accepted = t === "board" && track?.showing === "accepted";
    if (!tween) { anims[t].reset(track?.layout ?? null, { accepted, now }); continue; }
    const move = crossed.find((e) => e.kind === "move" && e.track === t) ?? null;
    const pulse = t === "board" && crossed.some((e) => e.kind === "accept");
    anims[t].set(track?.layout ?? null, { move, animate: true, pulse, accepted, now });
  }
  renderDom();
  requestDraw();
}

// Every verification change (a replay opened, a live poll, a late conflict that shrinks K) goes through here:
// reconcile() clamps the playhead to K, rebuilds the scene from the new prefix, recomputes the frame unless the
// prefix only grew, and the scene is cut in without any animation from the old prefix left running.
function adoptVerification(src, verification, { active: isActive, following, fresh = false }) {
  const r = reconcile({
    prefix: fresh ? [] : src.verification?.prefixEnvelopes ?? [],
    frame: fresh ? null : src.frame,
    cursor: isActive ? S.cursor : 0,
    following,
  }, verification);
  src.verification = verification;
  src.frame = r.frame;
  src.fullScene = sceneAt(r.prefix, verification.prefixCount, r.frame);
  S.gen += 1;
  if (!isActive) return;
  S.cursor = r.cursor;
  applyScene(r.scene, { animate: r.stepped });
}
function stop() { if (S.playing) clearInterval(S.playing); S.playing = null; $("play").textContent = "▶"; $("play").setAttribute("aria-label", "Play"); }
function play() {
  stop();
  if (S.source === "api") { S.following = true; setCursor(prefixK()); return; }
  if (S.cursor >= total()) setCursor(0);
  $("play").textContent = "❚❚"; $("play").setAttribute("aria-label", "Pause");
  S.playing = setInterval(() => { if (S.cursor >= total()) return stop(); setCursor(S.cursor + 1, { stepwise: true }); }, STEP_MS);
}
function step(delta) {
  stop();
  if (S.source === "api") S.following = false;
  setCursor(S.cursor + delta, { stepwise: delta === 1 });
  if (S.source === "api" && S.cursor >= prefixK()) S.following = true;
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
  // A layout whose geometry was refused draws nothing at all, not even an empty package.
  const drawable = (t) => { const L = S.scene?.tracks.find((x) => x.track === t)?.layout; return Boolean(footprint && L && !L.geometry_error); };
  const hasMain = drawable(S.selected);
  const compactMain = main.w < 700;
  drawPackage(main.ctx, hasMain ? { ...mf, footprint, unit } : null, {
    width: main.w, height: main.h, azimuthDeg: az, labels: true, callouts: !compactMain, lid: S.lid,
    pad: compactMain ? { l: 12, r: 12, t: 12, b: 12 } : { l: Math.min(250, main.w * 0.18), r: 24, t: 20, b: 26 },
  });
  for (const [t, tile] of tiles) {
    const fr = t === S.selected ? mf : anims[t].frame(now);
    if (t !== S.selected) busy ||= fr.active;
    const has = drawable(t);
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
  renderValueErrors();
  renderMain(src, v);
  renderInfo(src);
  renderStrip();
  renderOffline();
}

function renderTop(src, v) {
  const m = modeNow(S.source === "api" ? "api" : "file", S.live?.state.live ?? null, Date.now(), runStatusOf(S.live?.state));
  $("mode").className = `mode ${m.mode.toLowerCase()}${m.reason === "chain broken" ? " broken" : ""}`;
  $("modeText").textContent = m.label;
  $("drill").hidden = !(src && isDrill(src.verification));
  // The Lab view link keeps the context: source, run, bundle, test-key request and (replay) the playhead.
  $("labLink").href = viewHref("../", { source: S.source, runId: S.source === "api" ? S.live?.state.runId : src?.runId, seq: S.scene?.at.seq ?? null, search: location.search });
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
  const key = v ? `${S.source}:${S.gen}` : "";
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

// Values that verified but can't be drawn (an unsupported or missing unit, a value outside the bounds). Listed for
// what is on screen now; distinct from the chain banner because the chain itself is fine.
function renderValueErrors() {
  const el = $("valerr");
  el.replaceChildren();
  const errs = S.scene?.errors ?? [];
  if (!errs.length) { el.hidden = true; return; }
  el.hidden = false;
  el.append(`Value check: ${errs.length} verified value${errs.length === 1 ? "" : "s"} refused, not drawn`,
    h("span", null, ` · ${errs.slice(0, 3).map((e) => `${shortId(e.node)} ${FIELD[e.field] ?? e.field}: ${refusalText(e)}`).join(" · ")}${errs.length > 3 ? ` · +${errs.length - 3} more` : ""}. Supported units: mm, m, µm; °C (also written C), K.`));
}

function renderFrozen(v) {
  const el = $("frozen");
  el.replaceChildren();
  // Shown whenever anything follows the prefix, wherever the playhead is: the drawing can never pass seq K.
  if (!v || !v.frozen || !v.firstBreak) { el.hidden = true; return; }
  const fb = v.firstBreak;
  el.className = `frozen${fb.keyOnly ? " cfg" : ""}`;
  const what = fb.rejected ? `rejected (${fb.status})` : fb.status === "verified" ? "not projectable" : "unverified";
  el.hidden = false;
  el.append(v.label ?? `chain broken after seq ${v.prefixEnd}; board frozen at seq ${v.prefixEnd}`,
    h("span", null, ` · ${fb.seq == null ? "a row whose seq can't be read" : `seq ${fb.seq}`} is ${what}: ${fb.text || "unknown"}${fb.keyOnly && S.trust.pins.length === 0 ? " (the production pin list is empty until the core key exists)" : ""}. Nothing from it or after it is drawn.`));
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
  if (t?.layout?.geometry_error) return ["Not drawn: geometry refused", `${shortId(t.layout.ref.id)}: ${refusalText(t.layout.geometry_error)}. ${t.layout.geometry_error.detail}. The envelope verified; this value can't be placed, so nothing is drawn for it.`];
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
      sub = `${shortId(L.ref.id)} · ${trackName(L.ref.lab)} · accepted by the gate at seq ${t.accepted.seq}`;
      chip.className = "chip won"; chip.textContent = "ACCEPTED"; chip.hidden = false;
    } else {
      sub = `initial layout ${shortId(L.ref.id)} (core measurement) · nothing accepted yet`;
      chip.className = "chip init"; chip.textContent = "INITIAL"; chip.hidden = false;
    }
  } else if (L) {
    sub = `${shortId(L.ref.id)} · proposed at seq ${L.ref.seq}${t.on_board ? " · on the board" : ""}`;
    chip.className = `chip ${lifeKind(L.lifecycle)}`; chip.textContent = L.lifecycle ?? ""; chip.hidden = !L.lifecycle;
  } else chip.hidden = true;
  $("mainSub").textContent = sub;
  $("mainSub").title = L ? L.ref.id : "";
  const coloured = L ? L.chiplets.some((c) => c.color !== null) : false;
  $("mainCanvas").setAttribute("aria-label", L
    ? `${TRACKS[S.selected].name}: ${shortId(L.ref.id)}, ${L.chiplets.length} chiplets${L.J ? `, J ${fmt(L.J.value)} ${L.J.unit}` : ", no J"}. Isometric drawing; ${coloured ? "colours are chiplet-centre temperatures" : "no chiplet temperatures, so nothing is coloured"}.`
    : "No package drawn");
  $("picker").value = S.selected;

  const note = $("refusedNote");
  note.hidden = !(L && L.temps_error && !L.geometry_error);
  if (!note.hidden) note.textContent = `Temperatures not drawn: ${refusalText(L.temps_error)} · from ${shortId(L.temps_error.measurement)}`;

  // Caption: what the playhead just did (from the prefix's timeline), or why the package is not moving.
  const cap = $("caption");
  cap.replaceChildren();
  cap.title = "";
  if (v && S.cursor > v.prefixCount && v.prefixCount > 0) {
    cap.append(h("b", null, `seq ${v.rows[S.cursor - 1]?.seq ?? "?"} is after the break`), " · not drawn; the package stays at seq ", String(v.prefixEnd));
  } else if (S.scene && S.scene.timeline.length) {
    const last = S.scene.timeline[S.scene.timeline.length - 1];
    const stepSeq = S.scene.at.seq;
    cap.append(last.seq === stepSeq ? h("b", null, describeEvent(last, shortId)) : describeEvent(last, shortId));
    cap.title = describeEvent(last);   // full ids
  }
}

function renderInfo(src) {
  const t = S.scene?.tracks.find((x) => x.track === S.selected) ?? null;
  const L = t?.layout ?? null;
  const nothing = (src?.verification?.prefixCount ?? 0) === 0;
  $("infoLbl").textContent = nothing ? `${TRACKS[S.selected].name} · nothing verified` : S.selected === "board" ? (t?.showing === "accepted" ? "Board · accepted package" : "Board · before any acceptance") : `${TRACKS[S.selected].name} · current candidate`;
  $("infoName").textContent = L ? shortId(L.ref.id) : nothing ? "Nothing drawn" : "No package yet";
  $("infoName").title = L ? L.ref.id : "";
  $("infoFull").textContent = L && shortId(L.ref.id) !== L.ref.id ? L.ref.id : "";   // the full id, in the inspector
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
  // J and the centre temperatures can come from different measurements (scene.mjs describeSource): each part is
  // labelled and styled by its own source, and the J figure only by J's.
  const prov = describeSource(L, shortId);
  $("infoJ").textContent = L?.J ? `${fmt(L.J.value)} ${L.J.unit}` : "-";
  $("infoJ").className = prov.j_state;
  $("infoJ").title = L?.metric ? `J from ${L.metric.measurement} (${L.metric.validity})` : "";
  $("infoW").textContent = L?.W ? `W ${fmt(L.W.value)} ${L.W.metric_id}` : "";
  const srcEl = $("infoSrc");
  srcEl.replaceChildren();
  prov.parts.forEach((p, i) => srcEl.append(i ? " · " : "", h("span", { class: p.state || null }, p.text)));
  srcEl.title = L ? [L.metric ? `J from ${L.metric.measurement}` : null, L.temps_from ? `temperatures from ${L.temps_from.measurement}` : null].filter(Boolean).join(" · ") : "";
  if (L && L.overlaps.length) srcEl.append(` · overlap: ${L.overlaps.map((o) => `${o.a}/${o.b}`).join(", ")}`);

  // Legend: the run's one fixed scale.
  const scale = src?.frame?.scale ?? null;
  const ticks = $("scaleTicks");
  ticks.replaceChildren();
  $("scaleBarBox").hidden = !scale;
  ticks.hidden = !scale;
  $("noScale").hidden = !!scale;
  $("basis").hidden = !scale;          // "chiplet-centre temperatures from the solver" only when there are some
  $("scaleUnit").textContent = scale?.unit ? `· ${scale.unit}, fixed` : "";
  // The run's layout span, in the legend so every layout shows it (the stack block is hidden on small desktops).
  // One definition and label for both views: scene.mjs layoutSpan and spanText, as the Lab view's legend.
  $("spanNote").textContent = spanText(src?.frame?.footprint?.extent ?? null) ?? "";
  if (scale) for (const v of scaleTicks(scale)) ticks.append(h("span", { style: `left:${((v - scale.min) / (scale.max - scale.min)) * 100}%` }, String(v)));

  // Drill: what the withdrawal did, straight from project().
  const box = $("drillBox");
  box.replaceChildren();
  const d = S.scene?.drill ?? null;
  if (!d) { box.hidden = true; return; }
  box.hidden = false;
  box.append(h("div", { class: "lbl" }, "Correction drill"));
  for (const w of d.withdrawn) box.append(h("p", null, h("b", { title: w.node }, shortId(w.node)), ` withdrawn at seq ${w.seq ?? "?"}${w.reason ? ` · ${w.reason}` : ""}`));
  box.append(h("p", null, "went stale: ", d.stale.length ? d.stale.map((s) => shortId(s.node)).join(", ") : "none"));
  if (d.survived.length) box.append(h("p", null, "still valid on another support set: ", d.survived.map(shortId).join(", ")));
}

function renderStrip() {
  for (const [t, tile] of tiles) {
    const track = S.scene?.tracks.find((x) => x.track === t) ?? null;
    const L = track?.layout ?? null;
    tile.btn.classList.toggle("sel", t === S.selected);
    tile.btn.setAttribute("aria-pressed", String(t === S.selected));
    const nothing = (active()?.verification?.prefixCount ?? 0) === 0;
    tile.none.hidden = (!!L && !L.geometry_error) || (!L && !nothing && (!S.scene || S.scene.at.count === 0));
    tile.none.textContent = L?.geometry_error ? `geometry: ${refusalText(L.geometry_error)}` : nothing ? "nothing verified" : t === "board" ? "no layout yet" : "no candidate yet";
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
    tile.id.textContent = L ? shortId(L.ref.id) : "";
    tile.id.title = L ? L.ref.id : "";
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
  const v = st.live?.verification ?? null;
  // Any new verification, paused or following: the same rule as a replay (a live run's frame only widens while
  // its prefix grows; a shrinking or rewritten prefix recomputes it).
  if (v && v !== S.liveSrc.verification) { adoptVerification(S.liveSrc, v, { active: S.source === "api", following: S.following }); return; }
  if (S.source === "api") renderDom();
}

function setSource(src) {
  if (S.source === src) return;
  stop();
  S.cursors[S.source] = S.cursor;
  S.source = src;
  for (const b of $("source").querySelectorAll("button")) b.classList.toggle("on", b.dataset.src === src);
  ticksFor = null;
  for (const a of Object.values(anims)) a.reset(null);
  S.scene = null;
  if (src === "api") {
    if (!S.live) S.live = createLiveFeed({ trust: S.trust, runId: params.get("run"), onChange: onLive });
    S.following = true;
    S.live.start();
    if (S.liveSrc.verification) adoptVerification(S.liveSrc, S.liveSrc.verification, { active: true, following: true, fresh: true });
    else setCursor(0);
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
  if (S.source === "api" && S.live?.state.live) {
    const pg = S.live.state.live.paging;
    rows.push(["paging", `by cursor: ${pg.cursor} rows read${pg.degraded ? ` · stopped (${pg.degraded.replace(/_/g, " ")})` : ""}`], ["cursor hash", `${pg.cursor_hash.slice(0, 16)}…`]);
  }
  if (v) {
    rows.push(["verified", `${v.verified} of ${v.total}${v.duplicates ? ` · ${v.duplicates} duplicate${v.duplicates === 1 ? "" : "s"} ignored` : ""}`], ["drawn prefix", v.prefixCount ? `seq 1 to ${v.prefixEnd} (${v.prefixCount} envelopes)` : "none"],
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
  e.target.value = "";
  if (S.source !== "file") setSource("file");
  ticksFor = null;
  // Over the replay cap, the file is not even read.
  const bytes = f.size > MAX_FILE_BYTES ? null : new Uint8Array(await f.arrayBuffer());   // null: refused by the cap
  await loadReplay({ bytes, label: `${f.name} · opened file`, runId: null, isDemo: false });
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
