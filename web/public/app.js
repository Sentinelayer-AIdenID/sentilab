// Thermal Flight Lab front end (TFL-10). One renderer for live runs and replays: both are a GET /api/runs/{id} object
// whose result.lane_results[*].record holds every signed event. Every number on screen comes from those events.
"use strict";

const LANES = ["random", "simulated_annealing", "ucb1", "signal_portfolio"];
const LANE_NAME = { random: "Random", simulated_annealing: "Annealing", ucb1: "UCB1 (control)", signal_portfolio: "Signal portfolio" };
const OPS = ["local_move", "swap", "global_resample"];
const REPLAY_URL = "replay/ascend910-seed11-32x32.json";
const HEAT = [[0x11, 0x2a, 0x48], [0x23, 0x6b, 0x91], [0x56, 0xb6, 0xba], [0xdf, 0xd3, 0x76], [0xec, 0x99, 0x4f], [0xe4, 0x51, 0x38]];
const $ = (id) => document.getElementById(id);
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const laneColor = (lane) => css(`--lane-${lane}`) || "#91a3aa";
// The page's Content-Security-Policy (style-src 'self') refuses style="" attributes, so markup built here never
// carries one: lane colours are classes (fg-<lane> for text, bg-<lane> for fills, from the --lane-* variables in
// styles.css), and computed sizes are set through the CSSOM after the markup is in place (data-w: a width in %).
const laneKey = (lane) => (LANES.includes(lane) ? lane : "other");
const applyWidths = (root) => { for (const el of root.querySelectorAll("[data-w]")) el.style.width = `${Number(el.dataset.w)}%`; };
const fmt = (v, d = 2) => (v === null || v === undefined || Number.isNaN(v) ? "-" : Number(v).toFixed(d));
const short = (h, n = 12) => (h ? String(h).slice(0, n) : "-");
const plain = (t) => String(t == null ? "" : t).replace(/\bjev\b[-\w.]*/gi, "signal layer");   // the UI never names the model
// Record and run data can arrive from a replay file or a future router: every string from it is escaped before
// it reaches innerHTML, so a crafted record can never paint a fake verdict into the proof panels.
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" })[c]);

const S = { run: null, lanes: {}, k: 0, maxK: 0, playing: null, view: "step", sel: { lane: LANES[0], step: 0 },
            heatMin: 0, heatMax: 1, liveId: null, mode: "replay" };

// ── parse one run into per-lane steps ──────────────────────────────────────────────────────────────────────────
function parseRun(run) {
  const result = run.result || {};
  const lanes = {};
  let lo = Infinity, hi = -Infinity;
  const seeHeat = (h) => { if (!h) return; for (const row of h) for (const v of row) { if (v < lo) lo = v; if (v > hi) hi = v; } };
  for (const lane of LANES) {
    const lr = (result.lane_results || {})[lane];
    if (!lr) continue;
    const L = { lane, agent: lr.agent_id, key: lr.identity_public_key, recordKey: lr.record_public_key,
                valid: lr.record_valid === true, events: Array.isArray(lr.record) ? lr.record : [], steps: [], baseline: null, closed: null };
    let decision = null, signal = null, admitted = {}, pending = [], current = null;
    for (const e of L.events) {
      const p = e.payload || {};
      pending.push(e);
      if (e.event === "baseline") {
        L.baseline = { temp: p.thermal.maximum_temperature_c, heat: p.thermal.heatmap_c || null, wire: p.thermal.wirelength_mm,
                       wireMetric: p.thermal.wire_metric,
                       design: p.design_hash, pool: (p.shared_initial_samples || []).length, seq: e.sequence, hash: e.hash,
                       problem: p.thermal.problem_hash, solver: p.thermal.solver_version };
        seeHeat(L.baseline.heat);
      } else if (e.event === "lane_decision") decision = p;
      else if (e.event === "signal_decision") signal = p;
      else if (e.event === "proposal_admitted") admitted[p.proposal_id] = { op: p.operation, args: p.args, agent: p.agent_id, seq: e.sequence, cand: p.candidate_hash, parent: p.parent_hash };
      else if (e.event === "oracle_result") {
        const t = p.thermal || {};
        current = { k: L.steps.length + 1, pid: p.proposal_id, cand: p.candidate_hash, temp: t.maximum_temperature_c,
                    heat: t.heatmap_c || null, wire: t.wirelength_mm, wireMetric: t.wire_metric, solverS: t.solver_seconds, problem: t.problem_hash,
                    seq: e.sequence, hash: e.hash, ts: e.timestamp, decision, signal, admitted: admitted[p.proposal_id] || null,
                    outcome: null, events: [] };
        seeHeat(current.heat);
        L.steps.push(current);
        signal = null;
      } else if (e.event.startsWith("proposal_") && current && p.proposal_id === current.pid) {
        current.outcome = { status: e.event.slice(9), reason: p.reason, temp: p.temperature_c, seq: e.sequence };
        current.events = pending; pending = [];
      } else if (e.event === "run_closed") L.closed = { count: p.event_count, finalHash: e.hash, seq: e.sequence };   // the record tip, as /verify.html reports it
    }
    // lane-best curve: starts at the shared pool's best and moves only on a committed, simulator-verified result
    let best = L.baseline ? L.baseline.temp : null, bestHeat = L.baseline ? L.baseline.heat : null, bestCand = L.baseline && L.baseline.design;
    L.best = [{ temp: best, heat: bestHeat, cand: bestCand }];
    for (const s of L.steps) {
      if (s.outcome && s.outcome.status === "committed") { best = s.temp; bestHeat = s.heat; bestCand = s.cand; }
      L.best.push({ temp: best, heat: bestHeat, cand: bestCand });
    }
    lanes[lane] = L;
  }
  if (lo === Infinity) { lo = 0; hi = 1; }
  return { lanes, lo, hi };
}

function load(run, mode) {
  stop();
  const parsed = parseRun(run);
  S.run = run; S.mode = mode; S.lanes = parsed.lanes; S.heatMin = parsed.lo; S.heatMax = parsed.hi;
  S.maxK = Math.max(0, ...Object.values(S.lanes).map((L) => L.steps.length));
  // What the signed records prove about the signal layer: provider calls made, fallbacks taken, call latency.
  const sig = Object.values(S.lanes).flatMap((L) => L.steps.map((s) => s.signal).filter(Boolean));
  const called = sig.filter((d) => d.provider_called === true && d.requested_choice != null);
  const lat = called.map((d) => Number(d.latency_ms)).filter(Number.isFinite).sort((a, b) => a - b);
  S.signal = { decisions: sig.length, calls: called.length, fallbacks: sig.filter((d) => d.requested_choice == null).length,
               medianMs: lat.length ? lat[Math.floor(lat.length / 2)] : null };
  S.k = 0; S.sel = { lane: S.signal.decisions && S.lanes.signal_portfolio ? "signal_portfolio" : (Object.keys(S.lanes)[0] || LANES[0]), step: 0 };
  const pill = $("sigPill");
  pill.textContent = S.signal.calls ? "LIVE SIGNAL" : "LOCAL POLICY";
  pill.className = S.signal.calls ? "pill cyan" : "pill amber";
  $("scrub").max = S.maxK; $("scrub").value = 0;
  $("mode").classList.toggle("live", mode === "live");
  $("modeText").textContent = mode === "live" ? "LIVE RUN" : "REPLAY";
  $("runId").textContent = short(run.id, 18);
  const href = mode === "live" ? `/api/runs/${encodeURIComponent(run.id)}` : REPLAY_URL;
  $("exportLink").href = href; $("exportLink").setAttribute("download", `${run.id}.json`);
  $("legendMin").textContent = `${fmt(S.heatMin, 1)} °C`; $("legendMax").textContent = `${fmt(S.heatMax, 1)} °C`;
  const anyHeat = Object.values(S.lanes).some((L) => L.baseline && L.baseline.heat);
  if (!anyHeat) { $("legendMin").textContent = ""; $("legendMax").textContent = ""; }   // no grid, so no color scale to state
  $("scaleNote").textContent = anyHeat ? `${run.grid}×${run.grid} HotSpot chip-layer grid · fixed scale for this run · peaks come from the solver`
                                       : "plate solver reports peaks only (no grid); temperatures come from the solver";
  renderRecords();
  render();
  play();
}

// ── rendering ───────────────────────────────────────────────────────────────────────────────────────────────────
function stepAt(L, k) { return k > 0 ? L.steps[Math.min(k, L.steps.length) - 1] : null; }

function heatColor(v) {
  const t = Math.max(0, Math.min(1, (v - S.heatMin) / ((S.heatMax - S.heatMin) || 1))) * (HEAT.length - 1);
  const i = Math.min(HEAT.length - 2, Math.floor(t)), f = t - i, a = HEAT[i], b = HEAT[i + 1];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}

function drawHeat(canvas, grid) {
  const rows = grid.length, cols = grid[0].length, scale = Math.max(1, Math.floor(256 / Math.max(rows, cols)));
  canvas.width = cols * scale; canvas.height = rows * scale;
  const ctx = canvas.getContext("2d"), img = ctx.createImageData(cols, rows);
  for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
    const [R, G, B] = heatColor(grid[r][c]), o = (r * cols + c) * 4;
    img.data[o] = R; img.data[o + 1] = G; img.data[o + 2] = B; img.data[o + 3] = 255;
  }
  const off = document.createElement("canvas"); off.width = cols; off.height = rows; off.getContext("2d").putImageData(img, 0, 0);
  ctx.imageSmoothingEnabled = false; ctx.drawImage(off, 0, 0, canvas.width, canvas.height);
}

function renderRace() {
  const race = $("race");
  if (!race.children.length || race.dataset.run !== String(S.run && S.run.id)) {
    race.innerHTML = ""; race.dataset.run = String(S.run && S.run.id);
    for (const lane of LANES) {
      if (!S.lanes[lane]) continue;
      const cell = document.createElement("div");
      cell.className = "lanecell"; cell.dataset.lane = lane; cell.style.borderColor = laneColor(lane);
      cell.innerHTML = `<div class="lh"><b class="fg-${laneKey(lane)}">${LANE_NAME[lane]}</b><span class="muted w"></span><span class="t num"></span></div>` +
        (S.lanes[lane].baseline && S.lanes[lane].baseline.heat ? `<canvas class="heatcanvas"></canvas>`
                                                                : `<div class="noheat"></div>`) + `<span class="verdict"></span>`;
      cell.onclick = () => { S.sel = { lane, step: Math.min(S.k, S.lanes[lane].steps.length) }; render(); };
      race.appendChild(cell);
    }
  }
  for (const cell of race.children) {
    const L = S.lanes[cell.dataset.lane], s = stepAt(L, S.k), b = L.best[Math.min(S.k, L.steps.length)];
    const shown = S.view === "best" ? b : (s ? { temp: s.temp, heat: s.heat } : b);
    cell.classList.toggle("sel", S.sel.lane === L.lane);
    cell.querySelector(".t").textContent = `${fmt(shown.temp)} °C`;
    cell.querySelector(".w").textContent = s && s.wire != null ? `wire proxy ${fmt(s.wire, 1)} mm` : "";
    const canvas = cell.querySelector("canvas");
    if (canvas && shown.heat) drawHeat(canvas, shown.heat);
    const noheat = cell.querySelector(".noheat");
    if (noheat) noheat.innerHTML = `${S.view === "best" ? "lane best" : "this step"}<br><span class="bigtemp fg-${laneKey(L.lane)}">${fmt(shown.temp)} °C</span><br>best ${fmt(b.temp)} °C`;
    const v = cell.querySelector(".verdict");
    v.textContent = s ? (s.outcome ? `${s.outcome.status}: ${s.outcome.reason}` : "simulated") : "shared pool best";
    v.style.color = s && s.outcome && s.outcome.status === "committed" ? css("--cyan") : css("--muted");
  }
}

function renderCurves() {
  const chart = $("chart"), W = 1000, H = 600, pad = 24;
  const all = Object.values(S.lanes).flatMap((L) => L.best.map((b) => b.temp)).filter((v) => v != null);
  if (!all.length) { chart.innerHTML = ""; return; }
  let lo = Math.min(...all), hi = Math.max(...all);
  if (hi - lo < 0.05) { hi += 0.05; lo -= 0.05; }
  const x = (i) => pad + (i / Math.max(1, S.maxK)) * (W - 2 * pad), y = (v) => pad + (1 - (v - lo) / (hi - lo)) * (H - 2 * pad);
  let svg = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">`;
  for (let g = 0; g <= 4; g++) svg += `<line x1="${pad}" x2="${W - pad}" y1="${pad + g * (H - 2 * pad) / 4}" y2="${pad + g * (H - 2 * pad) / 4}" stroke="#22323a" stroke-width="1" vector-effect="non-scaling-stroke"/>`;
  svg += `<line x1="${x(S.k)}" x2="${x(S.k)}" y1="${pad}" y2="${H - pad}" stroke="#91a3aa" stroke-dasharray="4 4" vector-effect="non-scaling-stroke"/>`;
  for (const L of Object.values(S.lanes)) {
    const pts = L.best.slice(0, Math.min(S.k, L.steps.length) + 1).map((b, i) => `${x(i)},${y(b.temp)}`).join(" ");
    svg += `<polyline fill="none" stroke="${laneColor(L.lane)}" stroke-width="2.2" vector-effect="non-scaling-stroke" points="${pts}"/>`;
  }
  chart.innerHTML = svg + `</svg><span class="mono muted axis hi">${fmt(hi)} °C</span>` +
    `<span class="mono muted axis lo">${fmt(lo)} °C</span>`;
  $("curveLegend").innerHTML = Object.values(S.lanes).map((L) =>
    `<span><i class="bg-${laneKey(L.lane)}"></i>${LANE_NAME[L.lane]} ${fmt(L.best[Math.min(S.k, L.steps.length)].temp)}</span>`).join("");
}

function renderEvidence() {
  const L = S.lanes[S.sel.lane];
  if (!L) return;
  const k = Math.min(S.sel.step || S.k, L.steps.length), s = stepAt(L, k), run = S.run;
  const verdict = $("verdict");
  if (!s) {
    verdict.className = "strip";
    verdict.textContent = `Shared starting pool · ${L.baseline ? L.baseline.pool + 1 : "-"} designs simulated by this lane's own controller`;
  } else {
    const ok = s.outcome && s.outcome.status === "committed";
    verdict.className = "strip" + (s.outcome && s.outcome.status !== "committed" && s.outcome.status !== "rejected" ? " bad" : "");
    verdict.textContent = ok ? `Geometry legal · simulator evaluated · committed (${s.outcome.reason})`
                             : `Geometry legal · simulator evaluated · ${s.outcome ? `${s.outcome.status}: ${s.outcome.reason}` : "pending"}`;
  }
  const rows = s ? [
    ["Candidate", `${LANE_NAME[L.lane]} / seed ${run.seed} / eval ${s.k}`],
    ["Proposer identity", `${L.agent} · key ${short(L.key, 10)}`],
    ["Operation", s.admitted ? s.admitted.op : "-"],
    ["Geometry", "PASS (admitted only after legality)"],
    ["Worst chip-layer peak", `${fmt(s.temp, 3)} °C`],
    ["Wire proxy (Manhattan, mm)", s.wire != null ? fmt(s.wire, 2) : "n/a (plate)"],
    ...(s.wireMetric ? [["Wire metric (signed)", s.wireMetric]] : []),   // the oracle's own definition; escaped at render
    ["Solver time", s.solverS != null ? `${fmt(s.solverS, 3)} s` : "-"],
    ["Candidate hash", short(s.cand, 16)],
    ["Problem hash", short(s.problem, 16)],
    ["Event seq · hash", `${s.seq} · ${short(s.hash, 12)}`],
  ] : L.baseline ? [
    ["Lane", LANE_NAME[L.lane]], ["Pool best peak", `${fmt(L.baseline.temp, 3)} °C`],
    ["Wire proxy (Manhattan, mm)", L.baseline.wire != null ? fmt(L.baseline.wire, 2) : "n/a (plate)"],
    ...(L.baseline.wireMetric ? [["Wire metric (signed)", L.baseline.wireMetric]] : []),
    ["Design hash", short(L.baseline.design, 16)], ["Problem hash", short(L.baseline.problem, 16)],
    ["Solver", L.baseline.solver || "-"], ["Event seq · hash", `${L.baseline.seq} · ${short(L.baseline.hash, 12)}`],
  ] : [];
  $("evidence").innerHTML = rows.map(([a, b]) => `<div><span>${esc(a)}</span><span>${esc(b)}</span></div>`).join("");
}

function renderRouting() {
  const L = S.lanes[S.sel.lane];
  if (!L) return;
  const k = Math.min(S.k, L.steps.length), s = stepAt(L, k);
  const d = s && s.decision;
  $("routeReason").innerHTML = d ? `<b class="fg-${laneKey(L.lane)}">${LANE_NAME[L.lane]}</b> chose <b>${esc(d.operator)}</b> · ${esc(plain(d.reason))}`
                                 : `<b class="fg-${laneKey(L.lane)}">${LANE_NAME[L.lane]}</b> · starting from the shared pool`;
  for (const [id, on] of [["r1", !!d], ["r2", !!(s && s.admitted)], ["r3", !!s], ["r4", !!(s && s.outcome)]]) $(id).classList.toggle("on", on);
  // The signal layer's CHOICE for this step, exactly as signed into the record (signal-portfolio lane only).
  const g = s && s.signal;
  if (!g) {
    $("sigCard").innerHTML = L.lane === "signal_portfolio" && S.signal.decisions === 0
      ? `<span class="micro">This run used the local policy for every lane (no signal-layer calls).</span>` : "";
  } else if (g.requested_choice == null) {
    $("sigCard").innerHTML = `<div><span class="pill amber">FALLBACK</span> <span class="micro">${esc(plain(g.fallback_reason || "deterministic policy"))} · applied ${esc(g.applied_operator)}</span></div>`;
  } else {
    const probs = g.probabilities && typeof g.probabilities === "object" ? g.probabilities : {};
    $("sigCard").innerHTML = ["local_move", "swap", "global_resample", "stop"].map((o) => {
      const v = Number(probs[o]), w = Number.isFinite(v) ? Math.max(0, Math.min(1, v)) : 0;
      return `<div class="row${g.requested_choice === o ? " chosen" : ""}"><span>${o}</span><span class="track"><span class="fill" data-w="${100 * w}"></span></span><span class="num">${fmt(w, 2)}</span></div>`;
    }).join("") + `<div class="micro">CHOICE ${esc(g.requested_choice)} · confidence ${fmt(Number(g.confidence), 2)} · ${fmt(Number(g.latency_ms), 0)} ms` +
      `${g.stop_requested ? " · stop requested: deterministic continuation" : ""}</div>`;
    applyWidths($("sigCard"));
  }
  const counts = Object.fromEntries(OPS.map((o) => [o, 0]));
  for (const st of L.steps.slice(0, k)) if (st.decision && counts[st.decision.operator] !== undefined) counts[st.decision.operator]++;
  const max = Math.max(1, ...Object.values(counts));
  $("opbars").innerHTML = OPS.map((o) => `<div class="row${d && d.operator === o ? " chosen" : ""}"><span>${o}</span>` +
    `<span class="track"><span class="fill" data-w="${(100 * counts[o]) / max}"></span></span><span class="num">${counts[o]}</span></div>`).join("");
  applyWidths($("opbars"));
}

function renderFeed() {
  const lines = [];
  for (let i = 1; i <= S.k; i++) for (const L of Object.values(S.lanes)) {
    const s = L.steps[i - 1];
    if (!s) continue;
    const verdict = s.outcome ? s.outcome.status : "simulated";
    lines.push(`<div data-lane="${esc(L.lane)}" data-step="${i}"><span class="num">#${esc(s.seq)}</span><span class="chip bg-${laneKey(L.lane)}">${LANE_NAME[L.lane]}</span>` +
      `<span>${esc(s.decision ? s.decision.operator : "-")} → ${esc(s.admitted ? s.admitted.op : "-")}</span><span>${esc(verdict)}${s.outcome && s.outcome.reason ? ` · ${esc(plain(s.outcome.reason))}` : ""}</span>` +
      `<span class="num">${fmt(s.temp)} °C</span></div>`);
  }
  $("feed").innerHTML = lines.reverse().join("") || `<div><span></span><span></span><span class="muted">Shared pool simulated by each lane; press play.</span></div>`;
}

function renderKpis() {
  const Ls = Object.values(S.lanes);
  if (!Ls.length) return;
  const init = Math.min(...Ls.map((L) => (L.baseline ? L.baseline.temp : Infinity)));
  const bests = Ls.map((L) => ({ L, b: L.best[Math.min(S.k, L.steps.length)].temp }));
  const top = bests.reduce((a, c) => (c.b < a.b ? c : a));
  $("kInit").textContent = `${fmt(init)} °C`;
  $("kBest").textContent = `${fmt(top.b)} °C`;
  $("kBestS").textContent = `${fmt(init - top.b, 3)} °C lower · ${LANE_NAME[top.L.lane]}`;
  const used = Ls.reduce((n, L) => n + Math.min(S.k, L.steps.length), 0), total = Ls.reduce((n, L) => n + L.steps.length, 0);
  $("kBudget").textContent = `${used} / ${total}`;
  $("kWall").textContent = S.run.duration_s != null ? `${fmt(S.run.duration_s, 1)} s` : "-";
  $("kWallS").textContent = `${S.run.benchmark} · grid ${S.run.grid} · seed ${S.run.seed}`;
  const valid = Ls.filter((L) => L.valid).length, events = Ls.reduce((n, L) => n + L.events.length, 0);
  $("kRecord").textContent = valid === Ls.length ? `VALID ${valid}/${Ls.length}` : `INVALID ${Ls.length - valid}`;
  $("kRecord").style.color = valid === Ls.length ? css("--green") : "#e8957a";
  $("kRecordS").textContent = `${events} signed events · final ${short(Ls[0].closed && Ls[0].closed.finalHash, 10)}…`;
  $("recPill").textContent = valid === Ls.length ? "ALL VALID" : "CHECK";
  $("kSignal").textContent = String(S.signal.calls);
  $("kSignalS").textContent = S.signal.decisions
    ? `calls · ${S.signal.fallbacks} fallbacks · median ${S.signal.medianMs != null ? fmt(S.signal.medianMs, 0) + " ms" : "-"}`
    : "calls · local policy run";
}

function renderRecords() {
  const Ls = Object.values(S.lanes);
  const html = `<table><tr><th>Lane</th><th>Record</th><th>Events</th><th>Final hash (tip)</th><th>Record key</th></tr>` +
    Ls.map((L) => `<tr><td class="fg-${laneKey(L.lane)}">${LANE_NAME[L.lane]}</td><td class="${L.valid ? "ok" : "bad"}">${L.valid ? "VALID" : "INVALID"}</td>` +
      `<td class="num">${L.events.length}</td><td class="num">${esc(short(L.closed && L.closed.finalHash, 16))}</td><td class="num">${esc(short(L.recordKey, 16))}</td></tr>`).join("") +
    `</table><p class="micro">Verified by the service with FlightRecord.verify (hash chain, Ed25519 per event, run_closed count and final hash). ` +
    `<a class="dl" href="${esc($("exportLink").href)}" download>Download the full signed records</a> · ` +
    (S.mode === "live" ? `<a class="dl" href="/verify.html?run=${encodeURIComponent(S.run.id)}">Verify in your browser</a>`
                       : `<a class="dl" href="/verify.html">Verify in your browser</a> (drop the downloaded file)`) + `.</p>`;
  $("recordTable").innerHTML = html; $("record2").innerHTML = html;
}

async function renderBoard() {
  const Ls = Object.values(S.lanes);
  const kNow = S.k;
  const rank = Ls.map((L) => ({ L, b: L.best[Math.min(kNow, L.steps.length)].temp })).sort((a, b) => a.b - b.b);
  const init = Math.min(...Ls.map((L) => (L.baseline ? L.baseline.temp : Infinity)));
  let html = `<table><tr><th>This run</th><th>Lane best</th><th>Δ vs pool</th><th>Evals</th><th>Committed</th><th>Record</th></tr>` +
    rank.map(({ L, b }, i) => `<tr class="${i === 0 ? "best" : ""}"><td class="fg-${laneKey(L.lane)}">${LANE_NAME[L.lane]}</td>` +
      `<td class="num">${fmt(b, 3)} °C</td><td class="num">${fmt(b - init, 3)}</td><td class="num">${Math.min(kNow, L.steps.length)}/${L.steps.length}</td>` +
      `<td class="num">${L.steps.slice(0, kNow).filter((s) => s.outcome && s.outcome.status === "committed").length}</td>` +
      `<td class="${L.valid ? "ok" : "bad"}">${L.valid ? "VALID" : "INVALID"}</td></tr>`).join("") + `</table>`;
  try {
    const r = await fetch("/api/runs", { cache: "no-store" });
    if (r.ok) {
      const j = await r.json();
      html += `<table><tr><th>Recent runs</th><th>Benchmark</th><th>Grid</th><th>Seed</th><th>Best lane</th><th>Best</th><th>Time</th></tr>` +
        (j.runs || []).map((x) => `<tr><td class="num"><a class="dl" href="#" data-run="${esc(x.id)}">${esc(short(x.id, 10))}</a></td><td>${esc(x.benchmark)}</td><td>${esc(x.grid)}</td><td>${esc(x.seed)}</td>` +
          `<td>${esc(x.best ? LANE_NAME[x.best.lane_id] || x.best.lane_id : "-")}</td><td class="num">${x.best ? fmt(x.best.best_temperature_c, 3) : "-"}</td>` +
          `<td class="num">${x.duration_s != null ? fmt(x.duration_s, 1) + " s" : esc(x.status)}</td></tr>`).join("") + `</table>`;
    }
  } catch (_) { /* the run API may not be deployed yet; this run's ranking still stands */ }
  html += `<p class="micro">One seed is descriptive, not a statistical result. The result is stated even when the control (UCB1) wins.</p>`;
  $("board").innerHTML = html;
  for (const a of $("board").querySelectorAll("a[data-run]")) a.onclick = (ev) => { ev.preventDefault(); openRun(a.dataset.run); };
}

function render() {
  if (!S.run) return;
  $("scrub").value = S.k; $("stepLabel").textContent = `${S.k} / ${S.maxK}`;
  renderRace(); renderCurves(); renderEvidence(); renderRouting(); renderFeed(); renderKpis();
  if (!$("board").hidden) renderBoard();
}

// ── playback ────────────────────────────────────────────────────────────────────────────────────────────────────
function stop() { if (S.playing) clearInterval(S.playing); S.playing = null; $("play").textContent = "▶"; }
function play() {
  stop();
  if (S.k >= S.maxK) S.k = 0;
  $("play").textContent = "❚❚";
  const delay = matchMedia("(prefers-reduced-motion: reduce)").matches ? 900 : 450;
  S.playing = setInterval(() => { if (S.k >= S.maxK) return stop(); S.k++; S.sel.step = S.k; render(); }, delay);
}
$("play").onclick = () => (S.playing ? stop() : play());
$("reset").onclick = () => { stop(); S.k = 0; S.sel.step = 0; render(); };
$("scrub").oninput = (e) => { stop(); S.k = Number(e.target.value); S.sel.step = S.k; render(); };
for (const b of $("view").querySelectorAll("button")) b.onclick = () => {
  S.view = b.dataset.v; for (const x of $("view").querySelectorAll("button")) x.classList.toggle("on", x === b); render();
};
for (const t of document.querySelectorAll(".tab")) t.onclick = () => {
  for (const x of document.querySelectorAll(".tab")) x.classList.toggle("on", x === t);
  $("feed").hidden = t.dataset.tab !== "feed"; $("board").hidden = t.dataset.tab !== "board"; $("record2").hidden = t.dataset.tab !== "record";
  if (t.dataset.tab === "board") renderBoard();
};
$("feed").onclick = (e) => {
  const row = e.target.closest("div[data-lane]");
  if (row) { stop(); S.sel = { lane: row.dataset.lane, step: Number(row.dataset.step) }; renderEvidence(); renderRouting(); renderRace(); }
};
document.addEventListener("keydown", (e) => {
  if (e.target.matches("input, select")) return;
  if (e.key === " ") { e.preventDefault(); S.playing ? stop() : play(); }
  else if (e.key === "ArrowRight") { stop(); S.k = Math.min(S.maxK, S.k + 1); S.sel.step = S.k; render(); }
  else if (e.key === "ArrowLeft") { stop(); S.k = Math.max(0, S.k - 1); S.sel.step = S.k; render(); }
  else if (/^[1-4]$/.test(e.key) && S.lanes[LANES[Number(e.key) - 1]]) { S.sel.lane = LANES[Number(e.key) - 1]; render(); }
});
$("scope").onclick = $("limitsLink").onclick = (e) => { e.preventDefault(); $("limits").showModal(); };
$("limitsClose").onclick = () => $("limits").close();   // a listener, not an onclick="" attribute (CSP)

// ── data: replay file, live runs (POST then poll GET /api/runs/{id}) ───────────────────────────────────────────
async function openReplay() {
  $("conn").textContent = "loading replay…";
  const r = await fetch(REPLAY_URL);
  load(await r.json(), "replay");
  $("conn").textContent = "replay of a real recorded run · not live";
}

async function openRun(id) {
  const r = await fetch(`/api/runs/${encodeURIComponent(id)}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`GET /api/runs/${id}: ${r.status}`);
  const run = await r.json();
  if (run.status === "done" && run.result) load(run, "live");
  return run;
}

async function startLive() {
  const body = { benchmark: $("bench").value, grid: Number($("grid").value), seed: Number($("seed").value),
                 proposals: Math.max(1, Math.min(8, Number($("props").value) || 1)),
                 signal: $("signal").value === "live" ? "live" : "local" };
  $("start").disabled = true; $("runstate").textContent = "starting…";
  try {
    const r = await fetch("/api/runs", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
    const j = await r.json().catch(() => ({}));
    if (r.status === 429) throw new Error(j.error === "rate_limited" ? "rate limited at the edge: wait a minute" : "another run is in progress; try again in a few seconds");
    if (!r.ok || !j.id) throw new Error(j.error || `POST /api/runs: ${r.status}`);
    S.liveId = j.id;
    const t0 = Date.now();
    for (;;) {
      await new Promise((res) => setTimeout(res, 1000));
      const run = await openRun(j.id);
      $("conn").textContent = `live run ${short(j.id, 10)} · ${run.status} · ${((Date.now() - t0) / 1000).toFixed(0)} s`;
      $("runstate").textContent = `${run.status}…`;
      if (run.status === "done") {
        $("runstate").textContent = `done in ${fmt(run.duration_s, 1)} s`;
        history.replaceState(null, "", `?run=${encodeURIComponent(j.id)}`);   // a shareable link to this run
        break;
      }
      if (run.status === "failed") throw new Error(run.error || "run failed");
      if (Date.now() - t0 > 180000) throw new Error("run did not finish within 3 minutes");
    }
  } catch (err) {
    $("runstate").textContent = String(err.message || err);
  } finally {
    $("start").disabled = false;
  }
}
$("start").onclick = startLive;
$("replay").onclick = openReplay;

fetch("/api/health", { cache: "no-store" }).then((r) => r.json())
  .then((j) => { $("build").textContent = `build ${short(j.build_sha, 12)}`; })
  .catch(() => { $("build").textContent = "build unavailable"; });
async function follow(id) {
  const t0 = Date.now();
  for (;;) {
    const run = await openRun(id);
    $("conn").textContent = `live run ${short(id, 10)} · ${run.status}`;
    if (run.status !== "running") { if (run.status !== "done") $("runstate").textContent = run.error || run.status; return; }
    if (Date.now() - t0 > 180000) return;
    await new Promise((res) => setTimeout(res, 1000));
  }
}
const linked = new URLSearchParams(location.search).get("run");
(linked ? follow(linked) : openReplay()).catch((e) => { $("conn").textContent = `load failed: ${e.message || e}`; });
