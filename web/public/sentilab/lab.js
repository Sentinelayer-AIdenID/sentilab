// SentiLab Lab view (VIEW ENVELOPE v0.5 envelopes, v0.6 live paging). One input type for both modes: a JSONL replay
// file or the live /api/view/events route both give raw JSONL rows, and both go through the same bytes-to-rows rule,
// the same input checks, the same verifier and the same renderer. Transport caps come first (a replay file over
// 64 MiB, or a live page over 256 lines or 4 MiB, is never parsed), then each row's own checks, and only then hashing
// and signature checks. Live paging and the mode label are paging.mjs, the port of the v0.6 reference.
// Every string from an envelope reaches the page through textContent, never innerHTML.
import { VIEW_PINS } from "./view-pins.js";
import { viewHref } from "./view-links.mjs";
import {
  checkLine, readBodyCapped, progressTracker, parseKeyResponse, publicKeyFromSeedText, sha256Hex,
  MAX_LINE_BYTES, MAX_FILE_BYTES, MAX_API_BYTES,
} from "./view-core.mjs";
import { initialState, request as pageRequest, step as pageStep, verifyRows, verifyBytes, splitRows, rowText, liveLabel, REASON_TEXT } from "./paging.mjs";
import {
  buildView, feedRows, chainSummary, isDrill, isRejected, colorScale, nextScale, heat, frameOf, labInfo, reasonText, rankReasons,
  rowIdentity, resolveRow, stageOf, STAGES, isObj,
} from "./lab-model.mjs";

const DEMO = { url: "demo-run.jsonl", runId: "demo-8c-0001", label: "demo-run.jsonl · bundled interface fixture" };
const TEST_KEY_NAMES = ["core"];                 // ?pins=test: the vectors' "core" test key, derived here at run time
const STEP_MS = matchMedia("(prefers-reduced-motion: reduce)").matches ? 1300 : 800;
const POLL_OK_MS = 1000, POLL_BACKOFF_MS = 5000;
const MAX_SMALL_JSON = 256 * 1024;               // /api/view/runs and /api/view/key are small; a bigger answer is refused
const strictJson = (bytes) => JSON.parse(new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(bytes));
const FEED_ROWS_SHOWN = 400;
const params = new URLSearchParams(location.search);
const $ = (id) => document.getElementById(id);

// ── tiny DOM helpers: text only ─────────────────────────────────────────────────────────────────────────────
function h(tag, props, ...kids) {
  const node = document.createElement(tag);
  setProps(node, props);
  for (const kid of kids.flat(Infinity)) if (kid != null && kid !== false) node.append(kid instanceof Node ? kid : String(kid));
  return node;
}
function s(tag, props, ...kids) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  setProps(node, props);
  for (const kid of kids.flat(Infinity)) if (kid != null && kid !== false) node.append(kid instanceof Node ? kid : String(kid));
  return node;
}
function setProps(node, props) {
  for (const [k, v] of Object.entries(props ?? {})) {
    if (v == null || v === false) continue;
    if (k === "class") node.setAttribute("class", v);
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : String(v));
  }
}
const fmt = (v, d = 1) => (typeof v === "number" && Number.isFinite(v) ? v.toFixed(d) : "-");
const short = (x, n = 12) => (typeof x === "string" ? (x.length > n ? `${x.slice(0, n)}…` : x) : "-");
const tsText = (ts) => {
  const t = typeof ts === "string" ? Date.parse(ts) : NaN;
  if (!Number.isFinite(t)) return "-";
  const iso = new Date(t).toISOString();
  return `${iso.slice(11, 19)}.${iso.slice(20, 21)}`;
};

// ── state ───────────────────────────────────────────────────────────────────────────────────────────────────
const S = {
  pins: [], keys: {}, testMode: false, keyNote: "",
  source: params.get("src") === "live" ? "api" : "file",
  file: null,                 // { label, runId, runIdFrom, isDemo, rows, verification, scale, frame, error }
  // paging: paging.mjs state (every raw row received, the cursor and its hash, the latest failure, and "degraded" once
  // the stream was replaced or paging is unsupported). tracker: the v0.5 progress tracker, fed only valid pages.
  live: { runs: null, runId: params.get("run"), paging: initialState(params.get("run") ?? ""), verification: null, scale: null, frame: null,
          tracker: progressTracker(), connected: null, timer: null, error: "" },
  cursor: 0, cursors: {}, playing: null, following: true,
  // Open dialogs follow the data. inspected: the inspector's subject, by stable identity ({ source, id }), and the
  // verification it was last drawn from; chainFor: what the chain dialog was last drawn from.
  inspected: null, chainFor: null,
};
const active = () => (S.source === "api" ? S.live : S.file);

// ── keys: only the page's pins decide; keys from anywhere are checked against them by the verifier ────────────
// Anyone can derive the test keys, so a public host must never accept them: there they would let a forged file show
// as verified on our domain. Only a local server honours ?pins=test.
const TEST_PIN_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);

async function setupKeys() {
  const wantsTest = params.get("pins") === "test";
  if (wantsTest && TEST_PIN_HOSTS.has(location.hostname)) {
    S.testMode = true;
    try {
      for (const name of TEST_KEY_NAMES) {
        const raw = await publicKeyFromSeedText(`sentilab-view-test-key:${name}`);
        S.pins.push({ key_id: name, key_sha256: await sha256Hex(raw) });
        S.keys[name] = raw;
      }
      S.keyNote = "TEST KEYS: derived in this page from a public seed rule; anyone can sign with them";
    } catch {
      S.keyNote = "TEST KEYS requested, but this browser cannot derive Ed25519 keys";
    }
    return;
  }
  await setupPinnedKeys();
  if (wantsTest) S.keyNote = `TEST KEYS are only honoured on a local server; ${S.keyNote}`;
}

async function setupPinnedKeys() {
  S.pins = VIEW_PINS.map((p) => ({ key_id: p.key_id, key_sha256: p.key_sha256 }));
  if (S.pins.length === 0) { S.keyNote = "this page pins no key, so no envelope can verify"; return; }
  // The key may be served by the core; it is used only if its sha256 matches a pin.
  try {
    const r = await fetch("/api/view/key", { cache: "no-store" });
    if (!r.ok) { S.keyNote = `pinned key not served (/api/view/key answered ${r.status})`; return; }
    const body = await readBodyCapped(r, MAX_SMALL_JSON, "too_large");
    if (!body.ok) { S.keyNote = "pinned key not served (/api/view/key answered with more than 256 KiB)"; return; }
    Object.assign(S.keys, parseKeyResponse(strictJson(body.bytes)));
    S.keyNote = "pinned key fetched from /api/view/key and checked against the pin";
  } catch {
    S.keyNote = "pinned key not served (/api/view/key unreachable)";
  }
}

// ── verification: the same path for both sources ─────────────────────────────────────────────────────────────
// Both sources hold raw rows; paging.mjs verifyBytes() decodes each row strictly and runs the v0.5 checks, hashing
// only what passed the input checks.
async function verify(src) {
  const options = { runId: src.runId, pins: S.pins, keys: S.keys };
  const previousK = src.verification ? src.verification.prefix_end : 0;
  src.verification = src === S.live ? (await verifyRows(src.paging, options)).verification : await verifyBytes(src.rows, options);
  const trusted = src.verification.ordered.slice(0, src.verification.prefix);
  const scale = colorScale(trusted);
  // A file is one whole run, so its scale is fixed. A live run's scale only widens while its prefix holds or grows,
  // and is rebuilt from what remains when the prefix shrinks (nextScale).
  src.scale = src === S.live ? nextScale(src.scale, previousK, scale, src.verification.prefix_end) : scale;
  src.frame = frameOf(trusted);
}

// ── replay ──────────────────────────────────────────────────────────────────────────────────────────────────
const MIB = 1024 * 1024;
function replayError(label, runId, isDemo, message) {
  S.file = { label, runId: runId ?? "", runIdFrom: "requested", isDemo, rows: [], verification: null, error: message };
  $("conn").textContent = "";
  render();
}

// bytes: the file's raw bytes, already read (a picked file), or undefined to fetch url. Either way the file must pass
// the 64 MiB replay cap before a single row is decoded or parsed, and it is never decoded whole: each row on its own.
async function loadReplay({ url, bytes, label, runId, isDemo, at = null }) {
  stop();
  $("conn").textContent = "loading…";
  try {
    if (bytes === undefined) {
      const r = await fetch(url, { cache: "no-store" });
      if (!r.ok) throw new Error(`${url} answered ${r.status}`);
      const body = await readBodyCapped(r, MAX_FILE_BYTES, "file_too_large");
      if (!body.ok) throw new Error(`${url} is over the ${MAX_FILE_BYTES / MIB} MiB replay cap, so it was not read`);
      bytes = body.bytes;
    }
    if (bytes.length > MAX_FILE_BYTES) throw new Error(`the file is over the ${MAX_FILE_BYTES / MIB} MiB replay cap, so it was not read`);
  } catch (error) {
    replayError(label, runId, isDemo, String(error.message ?? error));
    return;
  }
  const rows = splitRows(bytes);   // v0.6 bytes-to-rows: split on LF only; each row decoded on its own, later
  // The run to check against. For the bundled demo, or a page opened with ?run=, the page names it. Otherwise a file
  // the user opened carries no request, so the view checks it against the run named by the lowest-seq row that
  // passes the input checks (read, never hashed), and says so on screen.
  let runIdFrom = "requested";
  if (!runId) {
    let first = null;
    for (const row of rows) {
      const text = row.length <= MAX_LINE_BYTES ? rowText(row) : null;
      const checked = text === null ? null : checkLine(text);
      if (checked?.ok && (first === null || checked.value.event.seq < first.event.seq)) first = checked.value;
    }
    runId = first ? first.run.run_id : "";
    runIdFrom = "file";
  }
  S.file = { label, runId, runIdFrom, isDemo, rows, verification: null };
  await verify(S.file);
  $("conn").textContent = "";
  if (S.source !== "file") return;
  // ?seq=N (first load only) opens paused at seq N, for a presenter or a screenshot; otherwise play from the start.
  if (at !== null && Number.isInteger(at) && at >= 0) {
    const rows = S.file.verification.rows;
    S.cursor = rows.filter((row) => row.seq !== null && row.seq <= at).length;
    render();
  } else {
    S.cursor = 0;
    render();
    play();
  }
}

// ── live: GET /api/view/runs, then GET /api/view/events?run_id=&after= ───────────────────────────────────────
function scheduleLive(ms) {
  clearTimeout(S.live.timer);
  if (S.source === "api") S.live.timer = setTimeout(pollLive, ms);
}
// Rule 4 (v0.6): GET /api/view/events?run_id=&cursor=<n>&limit=256[&cursor_hash=<hash of rows 0..n-1>] returns the
// run's log rows n.. as JSONL, with x-next-cursor, x-has-more and x-cursor-hash. paging.mjs step() applies each page:
// the caps before anything is split, then the cursor and the cursor hash over the raw bytes. The page keeps every raw
// row it accepted and re-verifies the whole stream when rows arrive, so a late envelope at a seq it already has (a
// conflict) still reaches it and freezes the board. A failed page keeps nothing and leaves the cursor and the prefix.
// "stream replaced" (409) and "paging unsupported" (400, 404, 501) are terminal: polling stops, the view is never LIVE
// again, and only a reload starts over from cursor 0. The view never pages by seq.
const MAX_PAGES_PER_POLL = 16;   // as the reference client loop
async function fetchPage(runId, req) {
  const query = new URLSearchParams({ run_id: runId, cursor: String(req.cursor), limit: String(req.limit) });
  if (req.cursor_hash !== undefined) query.set("cursor_hash", req.cursor_hash);
  let r;
  try { r = await fetch(`/api/view/events?${query}`, { cache: "no-store" }); } catch { return null; }   // transport
  if (r.status !== 200) { r.body?.cancel().catch(() => {}); return { status: r.status, headers: r.headers, bodyBytes: new Uint8Array(0) }; }
  // Raw bytes, never decoded whole; reading stops past 4 MiB, and a body that isn't read whole fails as transport.
  const body = await readBodyCapped(r, MAX_API_BYTES, "response_too_large").catch(() => ({ ok: false }));
  return { status: 200, headers: r.headers, bodyBytes: body.ok ? body.bytes : null };
}
async function pollLive() {
  const L = S.live;
  if (L.paging.degraded) return;   // stopped for good; a reload starts over
  if (document.hidden) return scheduleLive(POLL_BACKOFF_MS);
  try {
    if (!L.runs || !L.runId || Date.now() - (L.runsAt ?? 0) > 15000) {
      const r = await fetch("/api/view/runs", { cache: "no-store" });
      if (!r.ok) throw new Error(`/api/view/runs answered ${r.status}`);
      const body = await readBodyCapped(r, MAX_SMALL_JSON, "too_large");
      if (!body.ok) throw new Error("/api/view/runs answered with more than 256 KiB");
      if (S.live !== L) return;   // the run was switched while this poll was out
      const doc = strictJson(body.bytes);
      const runs = (Array.isArray(doc) ? doc : isObj(doc) && Array.isArray(doc.runs) ? doc.runs : [])
        .filter((x) => isObj(x) && typeof x.run_id === "string" && x.run_id.length <= 128).slice(0, 200);
      L.runs = runs;
      L.runsAt = Date.now();
      L.connected = true;
      if (!L.runId && runs.length) { L.runId = runs[0].run_id; L.paging = initialState(L.runId); }
      renderRunPicker();
      if (!L.runId) { render(); return scheduleLive(POLL_BACKOFF_MS); }
    }
  } catch (error) {
    if (S.live !== L) return;
    L.connected = false;
    L.error = String(error.message ?? error);
    render();
    return scheduleLive(POLL_BACKOFF_MS);   // calm back-off; one request every 5 s, nothing written to the console
  }
  // Drain: keep fetching while x-has-more is true (at most 16 pages a poll), then poll every 1 s from the last cursor.
  let outcome = "ok", added = 0;
  for (let pages = 0; pages < MAX_PAGES_PER_POLL; pages += 1) {
    const req = pageRequest(L.paging);
    if (req === null) break;     // terminal: request() sends nothing more
    const response = await fetchPage(L.runId, req);
    if (S.live !== L) return;   // the run was switched while this poll was out
    const result = await pageStep(L.paging, response, Date.now());
    if (S.live !== L) return;
    L.paging = result.state;
    outcome = result.outcome;
    added += result.newRows.length;
    if (outcome !== "ok" || !L.paging.has_more) break;
  }
  L.connected = true;
  L.error = "";
  if (added) {
    const anchor = !S.following && L.verification && S.cursor > 0 ? rowIdentity(L.verification, Math.min(S.cursor, L.verification.rows.length) - 1) : null;
    await verify(L);              // the whole stream, every time new rows arrive
    if (S.live !== L) return;
    if (S.following) S.cursor = L.verification.rows.length;
    else if (anchor) {
      // Paused: stay on the same envelope, even if a late row was sorted in before it.
      const at = resolveRow(L.verification, anchor);
      if (at >= 0) S.cursor = at + 1;
    }
  }
  // The tracker is fed only valid pages (rule 5); a failed latest poll shows its reason through liveLabel().
  if (outcome === "ok") L.tracker.poll({ nowMs: Date.now(), ok: true, K: L.verification ? L.verification.prefix_end : 0, received: added });
  else L.tracker.poll({ nowMs: Date.now(), ok: false });
  render();
  if (!L.paging.degraded) scheduleLive(outcome !== "ok" ? POLL_BACKOFF_MS : L.paging.has_more ? 0 : POLL_OK_MS);
}
// The mode pill: rule 5's label from paging.mjs liveLabel(), e.g. "LIVE · progress 3 s ago", "STALE · chain broken",
// "STALE · paging error".
function liveMode(now) {
  const L = S.live;
  const label = liveLabel(L.paging, L.tracker, now, L.verification ? L.verification.prefix_end : 0);
  const mode = label.startsWith("LIVE") ? "LIVE" : "STALE";
  return { mode, detail: label.slice(mode.length) };
}
function resetLive(runId) {
  // A new object, so a poll still out for the previous run writes only to the old one.
  clearTimeout(S.live.timer);
  S.live = { ...S.live, runId, paging: initialState(runId), verification: null, scale: null, frame: null, tracker: progressTracker(), timer: null };
  S.cursor = 0; S.following = true;
}

function setSource(src) {
  if (S.source === src) return;
  stop();
  S.cursors[S.source] = S.cursor;
  S.source = src;
  for (const b of $("source").querySelectorAll("button")) b.classList.toggle("on", b.dataset.src === src);
  clearTimeout(S.live.timer);
  if (src === "api") {
    S.following = true;
    S.cursor = S.live.verification ? S.live.verification.ordered.length : 0;
    pollLive();
  } else {
    S.cursor = Math.min(S.cursors.file ?? 0, total());
  }
  render();
}

// ── playback ────────────────────────────────────────────────────────────────────────────────────────────────
const total = () => active()?.verification?.ordered.length ?? 0;
function stop() { if (S.playing) clearInterval(S.playing); S.playing = null; $("play").textContent = "▶"; $("play").setAttribute("aria-label", "Play"); }
function play() {
  stop();
  if (S.source === "api") { S.following = true; S.cursor = total(); render(); return; }
  if (S.cursor >= total()) S.cursor = 0;
  $("play").textContent = "❚❚"; $("play").setAttribute("aria-label", "Pause");
  S.playing = setInterval(() => { if (S.cursor >= total()) return stop(); S.cursor += 1; render(); }, STEP_MS);
  render();
}
function step(delta) {
  stop();
  if (S.source === "api") S.following = false;
  S.cursor = Math.max(0, Math.min(total(), S.cursor + delta));
  if (S.source === "api" && S.cursor === total()) S.following = true;
  render();
}

// ── rendering ───────────────────────────────────────────────────────────────────────────────────────────────

function render() {
  const src = active();
  const v = src?.verification ?? null;
  const n = v ? Math.min(S.cursor, v.ordered.length) : 0;
  const view = v ? buildView(v, n) : null;
  renderTop(src, v);
  renderControls(src, v, n);
  renderFrozen(view, v);
  renderCards(src, v, view);
  renderBoard(v, view);
  renderEvidence(v, view);
  renderFeed(v, n, view);
  renderOffline(src);
  refreshDialogs();
}

function renderTop(src, v) {
  // Rule 5, on the client clock: REPLAY for a file; LIVE only while polls succeed and K keeps growing, with how long
  // ago it last grew ("LIVE · progress N s ago"); otherwise STALE.
  const now = Date.now();
  const { mode: m, detail } = S.source === "file" ? { mode: "REPLAY", detail: "" } : liveMode(now);
  const modeEl = $("mode");
  modeEl.className = `mode ${m.toLowerCase()}`;
  $("modeText").textContent = m;
  $("modeAge").textContent = detail;
  $("drill").hidden = !(v && isDrill(v.ordered));
  // The Package view link keeps the context (view-links.mjs): source, run, bundle, test-key request, replay playhead.
  $("packageLink").href = viewHref("package/", { source: S.source, runId: src?.runId ?? null, seq: v && S.cursor > 0 ? v.rows[Math.min(S.cursor, v.rows.length) - 1]?.seq ?? null : null, search: location.search });
  $("testKeys").hidden = !S.testMode;

  // Run facts come only from the verified prefix; before anything verifies, only the requested run id is shown.
  const meta = $("runMeta");
  meta.replaceChildren();
  if (src && src.runId) {
    const first = v && v.prefix > 0 ? v.ordered[0] : null;
    const run = first && isObj(first.run) ? first.run : null;
    meta.append(h("span", null, "run ", h("b", null, src.runId)));
    if (run) {
      meta.append(h("span", null, "arm ", h("b", null, String(run.arm ?? "-"))), h("span", null, "seed ", h("b", null, String(run.seed ?? "-"))),
        h("span", { class: "opt" }, "family ", h("b", null, String(run.family ?? "-"))));
    } else meta.append(h("span", null, src.runIdFrom === "file" ? "(run id taken from the file you opened)" : "(requested; nothing verified yet)"));
  }

  const chain = $("chain");
  if (!v || v.rows.length === 0) {
    chain.className = "chain";
    $("chainText").textContent = S.source === "api" ? "no envelopes yet" : "no envelopes";
    return;
  }
  const sum = chainSummary(v.rows);
  chain.className = `chain ${sum.ok ? "ok" : "bad"}`;
  $("chainText").textContent = `${sum.verified}/${sum.total} verified${sum.ok ? "" : ` · ${sum.phrases.join(" · ")}`}${S.testMode ? " · test keys" : ""}`;
}

function renderControls(src, v, n) {
  const max = v ? v.ordered.length : 0;
  $("scrub").max = String(max);
  $("scrub").value = String(n);
  const seqAt = n > 0 && v ? v.rows[n - 1].seq : 0;
  const lastSeq = max > 0 ? v.rows.reduce((m, r) => (Number.isSafeInteger(r.seq) ? Math.max(m, r.seq) : m), 0) : 0;
  $("pos").textContent = `seq ${seqAt ?? "?"} / ${lastSeq}`;
  $("fixture").hidden = !(S.source === "file" && src?.isDemo);
  $("runPick").hidden = S.source !== "api" || !S.live.runs || S.live.runs.length === 0;
  $("openLabel").hidden = S.source !== "file";
  const conn = $("conn");
  if (S.source === "api") {
    const L = S.live;
    const stopped = L.paging.degraded ? " · stopped; reload to start over" : L.paging.failure ? " · retry in 5 s" : "";
    conn.className = `conn${L.connected === false || L.paging.failure ? " bad" : ""}`;
    conn.textContent = L.connected === false ? "not connected · retry in 5 s"
      : L.connected ? `${S.following ? "following" : "paused"}${stopped}` : "connecting…";
    $("statusLeft").textContent = `Live · /api/view/events${L.runId ? ` · run ${L.runId}` : ""}`;
  } else {
    conn.className = "conn";
    $("statusLeft").textContent = src ? `Replay · ${src.label}` : "Replay";
  }
}

function renderFrozen(view, v) {
  const el = $("frozen");
  el.replaceChildren();
  if (!view || !view.broken || !v) { el.hidden = true; return; }
  // The contract label, verbatim, then what broke it: the first row after the prefix (never a verified row).
  const first = v.rows[v.prefix];
  const reasons = first ? rankReasons(first.reasons).map(reasonText) : [];
  const keyOnly = first && first.status === "unverified" && first.reasons.every((r) => KEY_ONLY.has(r));
  const what = !first ? "unverified" : isRejected(first) ? `${first.status}, rejected before hashing` : first.status;
  el.className = `frozen${keyOnly ? " cfg" : ""}`;
  el.hidden = false;
  el.append(v.label ?? `chain broken after seq ${view.broken.afterSeq}; board frozen at seq ${view.broken.afterSeq}`,
    h("span", null, ` · ${first?.seq == null ? "a line with no readable seq" : `seq ${first.seq}`} is ${what}: ${reasons.join(", ") || "unknown"}${keyOnly && S.pins.length === 0 ? " (this page pins no key)" : ""}. Later envelopes are listed in the feed and never projected.`));
}
const KEY_ONLY = new Set(["key_not_pinned", "key_unavailable", "ed25519_unsupported"]);

function emptyState(src, v, view) {
  if (S.source === "api" && S.live.connected !== true) return null;   // the offline card covers it
  if (src?.error) return ["Replay not loaded", src.error];
  if (!v || v.ordered.length === 0) {
    const why = S.live.paging.failure;
    return S.source === "api" ? ["Waiting for envelopes", why ? `Connected, but the last poll failed: ${REASON_TEXT[why] ?? why}.` : "Connected; this run has no envelopes yet."] : ["Nothing loaded", "Open a JSONL replay file."];
  }
  if (v.prefix === 0) {
    // The key note explains the empty board only when the first row failed on its key; otherwise the banner says why.
    const first = v.rows[0];
    const keyWhy = first && first.status === "unverified" && first.reasons.every((r) => KEY_ONLY.has(r) || r === "key_hash_mismatch") && S.keyNote;
    return ["Nothing verified to show", `${keyWhy ? `${S.keyNote[0].toUpperCase()}${S.keyNote.slice(1)}. ` : ""}Panels show only the verified prefix; the feed lists every envelope, marked.`];
  }
  if (view.n === 0) return ["Ready", "Press Space to play, or → to step one envelope."];
  return null;
}

function renderCards(src, v, view) {
  const box = $("cards");
  box.replaceChildren();
  $("legend").replaceChildren();
  const empty = emptyState(src, v, view);
  if (empty || !view || view.cards.length === 0) {
    const [title, text] = empty ?? (view?.projectionError ? ["Projection error", view.projectionError] : ["No layouts yet", "No candidate in the verified prefix so far."]);
    box.append(h("div", { class: "empty", style: "grid-column: 1 / -1" }, h("div", null, h("b", null, title), text)));
    box.style.gridAutoRows = "";
    return;
  }
  const { scale, frame } = src;
  const boardId = view.board.current?.id;
  for (const c of view.cards) box.append(cardEl(c, scale, frame, c.id === boardId));
  renderLegend(scale);
}

function cardEl(c, scale, frame, onBoard) {
  const [, kind] = stageOf(c.lifecycle);
  const chip = c.kind === "candidate" ? h("span", { class: `chip ${kind}` }, c.lifecycle) : h("span", { class: `chip v-${c.validity}` }, c.validity);
  const el = h("div", { class: `card${onBoard ? " board" : ""}`, style: `--lab:${c.color}` },
    h("div", { class: "ch" }, h("b", { style: `color:${c.color}` }, c.labName), chip));
  el.append(drawLayout(c, scale, frame));
  // Where the colors come from, in words. The measurement and its set status are project()'s.
  const src = c.source;
  let note, alt = false;
  if (c.kind === "measurement") note = c.labName === "Core" ? "core measurement" : "measurement";
  else if (!src) note = { rejected_schema: "not simulated", rejected_constraints: "not simulated", failed_run: "simulation failed", cancelled: "cancelled" }[c.lifecycle] ?? "awaiting simulation";
  else if (src.setStatus === "valid" && src.set_id !== c.firstSet) { note = `via ${src.id} · set ${c.firstSet} broken`; alt = true; }
  else if (src.validity === "valid") note = `temps from ${src.id}`;
  else note = `temps from ${src.id} · ${src.validity}`;
  el.append(h("div", { class: "cf" },
    h("span", { class: "j" }, h("small", null, "J"), c.J ? `${fmt(c.J.value)} ${c.J.unit}` : "-"),
    c.W ? h("span", { class: "src", title: `W ${c.W.metric_id}` }, `W ${fmt(c.W.value)} ${c.W.metric_id}`) : null));
  el.append(h("div", { class: "cf", style: "padding-top:0" }, h("span", { class: `src${alt ? " alt" : ""}`, style: "margin-left:0;text-align:left", title: `${c.id} · ${note}` }, `${c.id} · ${note}`),
    onBoard ? h("span", { class: "chip won", style: "margin-left:auto" }, "BOARD") : null));
  return el;
}

function drawLayout(c, scale, frame) {
  const U = 10;                                   // svg units per layout unit
  const f = frame ?? { x0: 0, y0: 0, x1: 10, y1: 10 };
  const W = (f.x1 - f.x0) * U, H = (f.y1 - f.y0) * U;
  const svg = s("svg", { viewBox: `-4 -4 ${W + 8} ${H + 8}`, preserveAspectRatio: "xMidYMid meet", role: "img",
    "aria-label": `${c.labName} layout${c.source ? ", chiplet-center temperatures" : ", no temperatures"}` });
  svg.append(s("rect", { x: 0, y: 0, width: W, height: H, rx: 6, fill: "#0e181d", stroke: "#34474f", "stroke-width": 2 }));
  const temps = c.source?.temps ?? null;
  const faded = c.source && c.source.validity !== "valid";
  const mono = "ui-monospace, Consolas, monospace";
  // Rectangles first, then every label on top, so overlapping geometry (a constraint failure) stays readable.
  // Chiplets without a temperature are drawn see-through, so an overlap shows as an overlap.
  const labels = [];
  for (const r of c.geometry) {
    const x = (r.x - f.x0) * U, y = (f.y1 - (r.y + r.h)) * U, w = r.w * U, hh = r.h * U;   // lower-left origin, y up
    const t = temps && Object.hasOwn(temps, r.id) ? temps[r.id] : null;
    const col = t !== null && scale ? heat(t, scale) : { fill: "#2c4049", ink: "#d3dee2" };
    svg.append(s("rect", { "data-chip": r.id, x, y, width: w, height: hh, rx: 3, fill: col.fill, "fill-opacity": t === null ? 0.55 : faded ? 0.45 : 1,
      stroke: r.layer > 0 ? "#dfe8e6" : t === null ? "#8fa5ad" : "#0a1317", "stroke-width": r.layer > 0 ? 2.5 : 2, "stroke-dasharray": r.layer > 0 ? "8 5" : null }));
    const label = r.layer > 0 ? `${r.id} L${r.layer}` : r.id;
    // Fit the id over the value on two lines, or both on one line for a short, wide chiplet: whichever is larger.
    const two = Math.min(w / (Math.max(label.length, 4) * 0.64), hh * 0.3, 44);
    const one = t === null ? 0 : Math.min(w / ((label.length * 0.8 + 1 + fmt(t).length) * 0.62), hh * 0.58, 44);
    labels.push({ x: x + w / 2, y: y + hh / 2, size: Math.max(10, Math.max(two, one)), oneLine: one > two, label, t, ink: col.ink });
  }
  for (const L of labels) {
    if (L.t !== null && L.oneLine) {
      svg.append(s("text", { x: L.x, y: L.y + L.size * 0.35, "text-anchor": "middle", "font-size": L.size, fill: L.ink, "font-family": mono },
        s("tspan", { "font-size": L.size * 0.8, opacity: 0.9 }, `${L.label} `), s("tspan", { "font-weight": 700 }, fmt(L.t))));
    } else if (L.t !== null) {
      svg.append(s("text", { x: L.x, y: L.y - L.size * 0.2, "text-anchor": "middle", "font-size": L.size * 0.85, fill: L.ink, "font-family": mono, opacity: 0.9 }, L.label));
      svg.append(s("text", { x: L.x, y: L.y + L.size * 0.92, "text-anchor": "middle", "font-size": L.size, "font-weight": 700, fill: L.ink, "font-family": mono }, fmt(L.t)));
    } else {
      svg.append(s("text", { x: L.x, y: L.y + L.size * 0.32, "text-anchor": "middle", "font-size": L.size * 0.9, fill: L.ink, "font-family": mono }, L.label));
    }
  }
  return svg;
}

function renderLegend(scale) {
  const lg = $("legend");
  if (!scale) { lg.append(h("span", { class: "what" }, "No center temperatures in the verified prefix yet.")); return; }
  const unit = scale.unit || "";
  lg.append(h("span", { class: "end" }, `${scale.min} ${unit}`), h("span", { class: "bar" }), h("span", { class: "end" }, `${scale.max} ${unit}`),
    h("span", { class: "what" }, S.source === "file" ? "one fixed scale for this run · center value per chiplet" : "one scale for this run, widens only if a value falls outside"));
}

function renderBoard(v, view) {
  const best = $("best"), table = $("board"), pill = $("boardPill");
  best.replaceChildren(); table.replaceChildren();
  if (!view || view.trustedCount === 0) {
    best.className = "best none";
    best.append(h("span", null, v && v.ordered.length ? "No verified envelopes to project, so the board is empty." : "Nothing loaded."));
    pill.className = "pill"; pill.textContent = "EMPTY";
    return;
  }
  if (view.projectionError) {
    best.className = "best none"; best.append(h("span", null, `Projection error: ${view.projectionError}`));
    pill.className = "pill bad"; pill.textContent = "ERROR";
    return;
  }
  const cur = view.board.current;
  if (cur) {
    best.className = "best";
    best.append(h("div", null, h("div", { class: "lbl" }, "Current board"), h("div", { class: "who", style: `color:${cur.color}` }, cur.labName)),
      h("div", { class: "j" }, cur.J ? `${fmt(cur.J.value)} ${cur.J.unit}` : "-"),
      h("div", { style: "min-width:0" }, h("span", { class: `chip v-${cur.validity}` }, cur.validity),
        h("div", { class: "meta", title: `${cur.id}, accepted by the gate at seq ${cur.acceptedSeq}` }, `accepted at seq ${cur.acceptedSeq} · ${cur.id}`)));
  } else {
    best.className = "best none";
    best.append(h("span", null, "No candidate accepted yet."));
  }
  pill.className = view.broken ? "pill bad" : "pill ok";
  pill.textContent = view.broken ? `FROZEN AT SEQ ${view.frozenAt}` : `PROJECTED · SEQ 1-${view.frozenAt}`;
  table.append(h("thead", null, h("tr", null, h("th", null, "Lab"), h("th", { class: "col-wide" }, "Candidate"), h("th", null, "Lifecycle"), h("th", { class: "col-wide" }, "Path"), h("th", { title: "Display value from the envelope; the gate decides from the core's records" }, "J (display)"), h("th", null, "Validity"))));
  const body = h("tbody");
  for (const c of view.board.candidates) {
    const [pos, kind] = stageOf(c.lifecycle);
    const dots = STAGES.map((name, i) => h("i", { title: name, class: pos === null ? "" : i < pos ? "done" : i === pos ? (kind === "open" ? "done" : kind) : "" }));
    body.append(h("tr", { class: cur && cur.id === c.id ? "cur" : "" },
      h("td", null, h("span", { class: "lab", style: `color:${c.color}` }, c.labName)), h("td", { class: "mono col-wide" }, c.id),
      h("td", null, h("span", { class: `chip ${kind}` }, c.lifecycle)), h("td", { class: "col-wide" }, h("span", { class: "track" }, dots)),
      h("td", { class: "mono" }, c.J ? `${fmt(c.J.value)}` : "-"), h("td", null, h("span", { class: `chip v-${c.validity}` }, c.validity))));
  }
  table.append(body);
}

function renderEvidence(v, view) {
  const table = $("evidence"), box = $("drillbox"), pill = $("evPill");
  table.replaceChildren(); box.replaceChildren();
  if (!view || view.trustedCount === 0 || view.projectionError) {
    box.hidden = true;
    pill.className = "pill"; pill.textContent = view?.projectionError ? "ERROR" : "EMPTY";
    table.append(h("tbody", null, h("tr", null, h("td", { class: "mono", style: "white-space:normal;color:var(--muted)" },
      view?.projectionError ? `Projection error: ${view.projectionError}` : "Validity appears here once the chain has a verified prefix."))));
    return;
  }
  const counts = { valid: 0, stale: 0, withdrawn: 0, unverified: 0 };
  for (const e of view.evidence) counts[e.validity] = (counts[e.validity] ?? 0) + 1;
  pill.className = counts.stale || counts.withdrawn ? "pill warn" : "pill ok";
  pill.textContent = `${counts.valid} valid · ${counts.stale} stale · ${counts.withdrawn} withdrawn`;
  if (view.drill) {
    box.hidden = false;
    const list = (items, fmtItem) => (items.length ? items.map(fmtItem).join(" · ") : "none");
    box.append(
      h("span", { class: "k" }, "Withdrawn"), h("span", { class: "v" }, list(view.drill.withdrawn, (e) => `${e.id}${e.withdrawal ? ` (seq ${e.withdrawal.seq}: ${e.withdrawal.reason})` : ""}`)),
      h("span", { class: "k" }, "Went stale"), h("span", { class: "v" }, list(view.drill.stale, (e) => `${e.id} ← ${e.stale_because.join(", ")}`)),
      h("span", { class: "k" }, "Still valid"), h("span", { class: "v" }, list(view.drill.survived, (e) => `${e.id} via ${Object.entries(e.support_status).filter(([, st]) => st === "valid").map(([k]) => k).join(", ")}`)));
  } else box.hidden = true;
  table.append(h("thead", null, h("tr", null, h("th", null, "Node"), h("th", { class: "col-wide" }, "Kind"), h("th", null, "Validity"), h("th", null, "Support sets"), h("th", null, "Why / tiers"))));
  const body = h("tbody");
  const survived = new Set((view.drill?.survived ?? []).map((e) => e.id));
  // What changed first: withdrawn, then stale, then what survived on an alternative set, then the rest.
  const order = (e) => (e.validity === "withdrawn" ? 0 : e.validity === "stale" ? 1 : survived.has(e.id) ? 2 : 3);
  for (const e of [...view.evidence].sort((a, b) => order(a) - order(b))) {
    const cls = e.validity === "withdrawn" ? "hl-withdrawn" : e.validity === "stale" ? "hl-stale" : survived.has(e.id) ? "hl-survived" : "";
    const sets = Object.entries(e.support_status).map(([id, st]) => h("span", { class: `set ${st}`, title: `support set ${id}: ${st}` }, `${id} ${st === "valid" ? "✓" : "✕"}`));
    const why = e.validity === "stale" ? h("span", { class: "because" }, `stale because ${e.stale_because.join(", ")}`)
      : e.tiers.length ? h("span", { class: "mono" }, `tier ${e.tiers.join(", ")}`) : e.review_required ? h("span", { class: "because" }, "review required") : "";
    body.append(h("tr", { class: cls }, h("td", { class: "mono" }, e.id), h("td", { class: "mono col-wide" }, e.kind),
      h("td", null, h("span", { class: `chip v-${e.validity}` }, e.validity)), h("td", { class: "sets" }, sets.length ? sets : h("span", { class: "mono", style: "color:var(--muted)" }, "-")), h("td", null, why)));
  }
  table.append(body);
}

function checkCell(r) {
  if (r.kind === "oversize") return ["warn", "⚠ oversize · never hashed"];
  if (r.kind === "malformed") return ["bad", "✕ malformed · never hashed"];
  if (r.status !== "verified") return ["bad", `✕ ${reasonText(rankReasons(r.reasons)[0])}`];
  if (!r.projected) return ["warn", "✓ verified, not projected"];
  if (r.rejected) return ["warn", `✓ verified · rejected: ${r.rejected}`];
  return ["ok", "✓ verified"];
}

function renderFeed(v, n, view) {
  const feed = $("feed"), pill = $("feedPill");
  feed.replaceChildren();
  if (!v || n === 0) {
    pill.className = "pill"; pill.textContent = v ? `0 / ${v.ordered.length} shown` : "-";
    feed.append(h("div", { class: "empty" }, v && v.ordered.length ? "Press Space to play, or → to step." : S.source === "api" ? "No envelopes received." : "No envelopes."));
    return;
  }
  const rows = feedRows(v, n, view?.rejected);
  const unv = rows.filter((r) => r.status !== "verified").length;
  pill.className = unv ? "pill bad" : "pill ok";
  pill.textContent = `${n} / ${v.ordered.length} shown${unv ? ` · ${unv} not verified` : ""}`;
  const shown = rows.slice(-FEED_ROWS_SHOWN).reverse();
  for (const r of shown) {
    const [cls, text] = checkCell(r);
    const lab = r.kind === "event" ? labInfo(r.lab) : null;
    const row = h("div", { class: `row${r.i === n - 1 ? " cur" : ""}${r.status !== "verified" ? " unv" : ""}${!r.projected ? " after" : ""}${r.kind !== "event" ? " special" : ""}`,
      role: "listitem", tabindex: 0, "data-i": r.i, title: "Open in the inspector" },
      h("span", { class: "num" }, r.seq == null ? "?" : `#${r.seq}`),
      h("span", null, r.kind === "event" ? tsText(r.ts) : "-"),
      lab ? h("span", { class: "labchip", style: `background:${lab.color}` }, lab.name) : h("span", null, "-"),
      h("span", null, r.kind === "event" ? r.type : r.kind),
      h("span", { class: r.kind !== "event" ? "out" : "" }, r.text),
      h("span", { class: cls }, h("span", { class: "check-icon" }, text.slice(0, 1)), h("span", { class: "check-text" }, text.slice(1))));
    feed.append(row);
  }
}

function renderOffline(src) {
  const off = $("offline");
  if (S.source !== "api" || S.live.connected === true) { off.hidden = true; return; }
  off.hidden = false;
  $("offTitle").textContent = S.live.connected === null ? "Connecting to the live feed…" : "Live feed not connected";
  $("offText").textContent = S.live.connected === null ? "Asking /api/view/runs." :
    `The page asks /api/view/runs every 5 s and gets no answer (${S.live.error || "no response"}). The core that serves the live routes isn't answering. The replay is still available.`;
}

function renderRunPicker() {
  const pick = $("runPick");
  const runs = S.live.runs ?? [];
  pick.replaceChildren(...runs.map((r) => h("option", { value: r.run_id, selected: r.run_id === S.live.runId },
    `${r.run_id}${r.arm ? ` · ${r.arm}` : ""}${r.seed != null ? ` · seed ${r.seed}` : ""}`)));
}

// ── inspector and chain details ─────────────────────────────────────────────────────────────────────────────
function kv(rows) {
  return h("div", { class: "kv" }, rows.map(([k, val]) => (k === "§" ? h("div", { class: "sect" }, val) : [h("div", { class: "k" }, k), h("div", { class: "v" }, val ?? "-")])));
}
const asText = (x) => (x === null || x === undefined ? "-" : typeof x === "string" ? x : JSON.stringify(x));
// The inspector's subject is an envelope identity (event_id and stored hash), not a row index: a late row at an old
// seq is sorted in before others and shifts every index after it.
function inspect(i) {
  const v = active()?.verification;
  if (!v || !v.rows[i]) return;
  stop();
  S.inspected = { source: S.source, id: rowIdentity(v, i) };
  renderInspector();
  $("inspector").showModal();
}
function renderInspector() {
  const src = S.inspected.source === "api" ? S.live : S.file;
  const v = src?.verification ?? null;
  S.inspected.drawnFrom = v;
  const i = v ? resolveRow(v, S.inspected.id) : -1;
  if (i < 0) {
    $("inspTitle").textContent = "Envelope no longer in view";
    $("inspBody").replaceChildren(kv([["status", "The rows changed and this envelope no longer resolves. Close this and pick a row again."],
      ["event_id", S.inspected.id.event_id ?? "unreadable"], ["hash (as stored)", S.inspected.id.hash ?? "unreadable"]]));
    return;
  }
  const env = v.ordered[i], row = v.rows[i], meta = v.meta[i];
  const where = S.inspected.source === "api" ? `received line ${meta.index + 1}` : `line ${meta.index + 1} of the file`;
  const rows = [
    ["status", `${row.status}${i < v.prefix ? " · in the projected prefix" : " · not projected"}`],
    ["reasons", row.reasons.length ? row.reasons.map((r) => `${r} (${reasonText(r)})`).join(", ") : "none"],
    ["input checks", isRejected(row) ? "failed: never canonicalized, hashed or verified" : "passed (size, structure, schema)"],
    ["position", where],
  ];
  if (isRejected(row) || !isObj(env)) {
    // Only fields that could be read safely; the content itself is never rendered.
    rows.push(["§", "rejected line"], ["seq", row.seq ?? "unreadable"], ["event_id", row.event_id ?? "unreadable"], ["hash (as stored)", meta.hash ?? "unreadable"],
      ["content", "not rendered: it failed the input checks"]);
  } else {
    const a = isObj(env.actor) ? env.actor : {}, run = isObj(env.run) ? env.run : {}, sig = isObj(env.sig) ? env.sig : {};
    rows.push(["§", "event"], ["seq", asText(env.event.seq)], ["event_id", asText(env.event.event_id)], ["type", asText(env.event.type)],
      ["actor_role", asText(env.event.actor_role)], ["ts (display only)", asText(env.ts)],
      ["§", "actor"], ["lab", `${labInfo(a.lab).name} (${asText(a.lab)})`], ["agent id", asText(a.agent_id)], ["life id", asText(a.life_id)], ["grant id", asText(a.grant_id)],
      ["§", "run"], ["run id", asText(run.run_id)], ["arm", asText(run.arm)], ["family", asText(run.family)], ["seed", asText(run.seed)], ["ticket id", asText(run.ticket_id)],
      ["§", "hashes"], ["hash", asText(env.hash)], ["prev_hash", asText(env.prev_hash)], ["sig key_id", asText(sig.key_id)], ["sig alg", asText(sig.alg)], ["sig value", short(asText(sig.value), 32)],
      ["§", "body"], ["", h("pre", { class: "json" }, JSON.stringify(env.event.body ?? null, null, 2))]);
    if (isObj(env.values)) rows.push(["§", "values (display only)"], ["", h("pre", { class: "json" }, JSON.stringify(env.values, null, 2))]);
  }
  $("inspTitle").textContent = `Envelope ${row.seq == null ? "?" : `seq ${row.seq}`} · ${row.status}`;
  $("inspBody").replaceChildren(kv(rows));
}
function showChain() {
  renderChain();
  $("chainDlg").showModal();
}
function renderChain() {
  const src = active(), v = src?.verification;
  S.chainFor = { v, paging: S.source === "api" ? S.live.paging : null, tracker: S.source === "api" ? S.live.tracker.state() : null };
  const rows = [["pins in this page", S.testMode ? `${S.pins.length} (TEST KEYS)` : `${S.pins.length}${S.pins.length ? "" : " (an empty list verifies nothing)"}`],
    ["key source", S.keyNote || "-"], ["run checked", src?.runId ? `${src.runId} (${src.runIdFrom === "file" ? "from the file you opened" : "requested by the page"})` : "-"]];
  if (S.source === "api") {
    const t = S.live.tracker.state();
    const why = S.live.paging.failure;
    rows.push(["last poll", S.live.connected === false ? `failed: ${S.live.error}` : why ? `failed: ${REASON_TEXT[why] ?? why}${S.live.paging.degraded ? " (stopped; reload to start over)" : ""}` : t.last_poll_ok_ms ? "ok" : "-"],
      ["progress", t.last_progress_ms ? `K reached ${t.K} ${Math.max(0, Math.floor((Date.now() - t.last_progress_ms) / 1000))} s ago` : "K has not grown yet"]);
  }
  if (v) {
    const sum = chainSummary(v.rows);
    rows.push(["verified", `${sum.verified} of ${sum.total} rows`], ["projected prefix", v.prefix ? `seq 1 to ${v.prefix_end} (${v.prefix} envelopes)` : "none"],
      ["rejected rows", `${sum.rejected}${sum.rejected ? " (failed the input checks; never hashed)" : ""}`],
      ["duplicates ignored", `${v.duplicates}${v.duplicates ? " (identical envelopes; no row)" : ""}`],
      ...(S.source === "api" ? [["paging", `by cursor: ${S.live.paging.cursor} rows read`], ["cursor hash", short(S.live.paging.cursor_hash, 16)]] : []),
      ["§", "reasons"], ...sum.reasons.map((r) => [r.code, `${reasonText(r.code)} · ${r.count} row${r.count > 1 ? "s" : ""} · first at seq ${r.firstSeq ?? "?"}`]));
  }
  $("chainBody").replaceChildren(kv(rows));
}
// Called on every render: an open dialog is redrawn from the current data whenever what it shows has changed, so it
// never contradicts the board behind it. Its scroll position is kept.
function refreshDialogs() {
  const keepScroll = (el, draw) => { const top = el.scrollTop; draw(); el.scrollTop = top; };
  if ($("inspector").open && S.inspected) {
    const src = S.inspected.source === "api" ? S.live : S.file;
    if ((src?.verification ?? null) !== S.inspected.drawnFrom) keepScroll($("inspBody"), renderInspector);
  }
  if ($("chainDlg").open && S.chainFor) {
    const src = active();
    const live = S.source === "api";
    const t = live ? S.live.tracker.state() : null;
    const changed = (src?.verification ?? undefined) !== S.chainFor.v || (live && (S.live.paging !== S.chainFor.paging ||
      t.K !== S.chainFor.tracker.K || t.last_poll_ok_ms !== S.chainFor.tracker.last_poll_ok_ms));
    if (changed) keepScroll($("chainBody"), renderChain);
  }
}

// ── wiring ──────────────────────────────────────────────────────────────────────────────────────────────────
$("play").onclick = () => (S.playing ? stop() : play());
$("scrub").oninput = (e) => { stop(); if (S.source === "api") S.following = false; S.cursor = Number(e.target.value); render(); };
for (const b of $("source").querySelectorAll("button")) b.onclick = () => setSource(b.dataset.src);
$("backToReplay").onclick = () => setSource("file");
$("runPick").onchange = (e) => { resetLive(e.target.value); pollLive(); render(); };
// A picked file is checked against the run the page requests (?run=) if there is one, otherwise against the run its
// own lowest-seq line names (shown as such). Its raw size is checked before a byte of it is read.
$("file").onchange = async (e) => {
  const f = e.target.files && e.target.files[0];
  if (!f) return;
  e.target.value = "";
  if (S.source !== "file") setSource("file");
  const label = `${f.name} · opened file`;
  if (f.size > MAX_FILE_BYTES) { stop(); replayError(label, null, false, `the file is over the ${MAX_FILE_BYTES / MIB} MiB replay cap, so it was not read`); return; }
  await loadReplay({ bytes: new Uint8Array(await f.arrayBuffer()), label, runId: params.get("run") || null, isDemo: false });
};
$("feed").onclick = (e) => { const row = e.target.closest(".row[data-i]"); if (row) inspect(Number(row.dataset.i)); };
$("feed").onkeydown = (e) => { if (e.key === "Enter") { const row = e.target.closest(".row[data-i]"); if (row) inspect(Number(row.dataset.i)); } };
$("chain").onclick = showChain;
$("inspClose").onclick = () => $("inspector").close();
$("chainClose").onclick = () => $("chainDlg").close();
$("inspector").addEventListener("close", () => { S.inspected = null; });
$("chainDlg").addEventListener("close", () => { S.chainFor = null; });
$("limitsLink").onclick = (e) => { e.preventDefault(); $("limits").showModal(); };
$("limitsClose").onclick = () => $("limits").close();
document.addEventListener("keydown", (e) => {
  if (e.target.matches("input, select, textarea") || document.querySelector("dialog[open]")) return;
  if (e.key === " " && e.target.closest("button, a, label")) return;
  if (e.key === " ") { e.preventDefault(); if (S.source === "api") { if (S.following) { S.following = false; render(); } else play(); } else (S.playing ? stop() : play()); }
  else if (e.key === "ArrowRight") { e.preventDefault(); step(1); }
  else if (e.key === "ArrowLeft") { e.preventDefault(); step(-1); }
});
document.addEventListener("visibilitychange", () => { if (!document.hidden && S.source === "api") { clearTimeout(S.live.timer); pollLive(); } });
setInterval(() => { if (S.source === "api") renderTop(active(), active()?.verification); }, 1000);   // the mode label ages on the client clock

// ── start ───────────────────────────────────────────────────────────────────────────────────────────────────
for (const b of $("source").querySelectorAll("button")) b.classList.toggle("on", b.dataset.src === S.source);
// WebCrypto exists only in a secure context (https or a local server). Without it nothing can be verified, so say
// that plainly instead of failing on the first hash.
if (!globalThis.crypto?.subtle) {
  $("frozen").hidden = false;
  $("frozen").textContent = "Signatures can't be checked here: this page needs a secure (https) connection. Nothing is shown as verified.";
  $("chainText").textContent = "cannot verify";
} else {
  await setupKeys();
  const bundle = params.get("bundle");
  const replay = bundle && /^[A-Za-z0-9._-]{1,128}$/.test(bundle)
    ? { url: `/api/replay/${encodeURIComponent(bundle)}.jsonl`, label: `/api/replay/${bundle}.jsonl`, runId: params.get("run") || null, isDemo: false }
    : { url: DEMO.url, label: DEMO.label, runId: DEMO.runId, isDemo: true };
  if (params.has("seq")) replay.at = Number(params.get("seq"));
  render();
  if (S.source === "api") pollLive();
  await loadReplay(replay);
}
