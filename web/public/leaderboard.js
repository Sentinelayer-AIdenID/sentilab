const $ = (id) => document.getElementById(id);
const svgNS = "http://www.w3.org/2000/svg";
const colors = {
  random: "#78aaff",
  simulated_annealing: "#59d9a4",
  ucb1: "#ffbd5b",
  signal_portfolio: "#d693ff",
  hindsight_best_fixed_operator: "#ff758f",
};
let report = null;

function node(tag, text, className) {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (className) item.className = className;
  return item;
}

function number(value, places = 3) {
  return Number.isFinite(value) ? value.toFixed(places) : "—";
}

function cell(row, text) {
  row.append(node("td", text));
}

function drawCurves(item) {
  const svg = $("curve");
  svg.replaceChildren();
  const lanes = ["random", "simulated_annealing", "ucb1", "signal_portfolio", "hindsight_best_fixed_operator"]
    .filter((lane) => item.statistics.lanes[lane]?.best_so_far_curve?.length);
  const curves = lanes.map((lane) => item.statistics.lanes[lane].best_so_far_curve);
  const values = curves.flatMap((curve) => curve.map((point) => point.median_best_temperature_c));
  if (!values.length) return;
  const min = Math.min(...values), max = Math.max(...values);
  const spread = Math.max(max - min, 0.1);
  const left = 62, right = 880, top = 20, bottom = 264;
  const x = (index, count) => left + (count <= 1 ? 0 : index * (right - left) / (count - 1));
  const y = (value) => bottom - ((value - (min - spread * .08)) / (spread * 1.16)) * (bottom - top);
  const add = (tag, attrs, text) => {
    const el = document.createElementNS(svgNS, tag);
    for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, String(value));
    if (text !== undefined) el.textContent = text;
    svg.append(el);
    return el;
  };
  for (let i = 0; i < 5; i++) {
    const value = min - spread * .08 + spread * 1.16 * i / 4;
    const yy = y(value);
    add("line", {x1: left, x2: right, y1: yy, y2: yy, class: "gridline"});
    add("text", {x: left - 8, y: yy + 4, "text-anchor": "end", class: "tick"}, number(value, 2));
  }
  add("line", {x1: left, x2: right, y1: bottom, y2: bottom, class: "axis"});
  const pointsCount = Math.max(...curves.map((curve) => curve.length));
  for (const lane of lanes) {
    const curve = item.statistics.lanes[lane].best_so_far_curve;
    const points = curve.map((point, index) => `${x(index, pointsCount)},${y(point.median_best_temperature_c)}`).join(" ");
    add("polyline", {points, fill: "none", stroke: colors[lane], "stroke-width": 3, "stroke-linejoin": "round"});
  }
  add("text", {x: left, y: 298, class: "tick"}, "0");
  add("text", {x: right, y: 298, "text-anchor": "end", class: "tick"}, String(pointsCount - 1));
  add("text", {x: (left + right) / 2, y: 316, "text-anchor": "middle", class: "tick"}, "Charged simulator evaluations");

  const legend = $("legend");
  legend.replaceChildren();
  for (const lane of lanes) {
    const label = node("span");
    const swatch = node("i");
    swatch.style.borderColor = colors[lane];
    const name = lane === "hindsight_best_fixed_operator"
      ? "hindsight best fixed operator (upper bound)" : lane.replaceAll("_", " ");
    label.append(swatch, document.createTextNode(name));
    legend.append(label);
  }
}

function renderBenchmark(name) {
  const item = report.benchmarks[name];
  if (!item || item.seed_count < 10) {
    $("status").textContent = "This batch is missing or has fewer than 10 seeds; it is not shown as a TFL-08 result.";
    $("content").hidden = true;
    return;
  }
  $("status").hidden = true;
  $("content").hidden = false;
  $("seedCount").textContent = String(item.seed_count);
  $("protocol").textContent = `${item.evaluations_per_lane} charged evaluations per lane · seeds ${item.seeds.join(", ")}`;
  $("winner").textContent = item.statistics.winner_by_median.replaceAll("_", " ");
  const signal = item.statistics.lanes.signal_portfolio.signal_layer;
  $("signalTitle").textContent = signal.mode === "local"
    ? "Signal-portfolio lane (local policy) vs UCB1"
    : signal.total_provider_calls > 0
      ? "Signal-portfolio lane (live provider calls) vs UCB1"
      : "Signal-portfolio lane (no provider calls) vs UCB1";
  $("signalResult").textContent = item.statistics.signal_vs_ucb1_plain_result;
  $("signalMode").textContent = signal.mode === "live"
    ? `${signal.total_provider_calls} provider calls · ${signal.total_fallbacks} fallbacks`
    : "Local deterministic policy; no provider calls";

  const tbody = $("rows");
  tbody.replaceChildren();
  for (const [lane, stats] of Object.entries(item.statistics.lanes)) {
    const row = node("tr");
    cell(row, lane.replaceAll("_", " "));
    cell(row, `${number(stats.median)} (n=${stats.n})`);
    cell(row, number(stats.iqr));
    cell(row, `${number(stats.bootstrap_95_ci_median?.[0])}–${number(stats.bootstrap_95_ci_median?.[1])}`);
    cell(row, number(stats.sample_variance_c2, 4));
    cell(row, Number.isFinite(stats.median_wall_time_s) ? `${number(stats.median_wall_time_s)} s` : "—");
    cell(row, Number.isFinite(stats.paired_wilcoxon_vs_ucb1?.p_value)
      ? number(stats.paired_wilcoxon_vs_ucb1.p_value, 4) : "—");
    tbody.append(row);
  }
  const cost = $("signalCosts");
  cost.textContent = `Signal layer: ${signal.total_input_tokens ?? "unknown"} input tokens; ` +
    `${signal.total_output_tokens ?? "unknown"} output tokens; ${signal.total_fallbacks} fallbacks; ` +
    `estimated list price ${signal.estimated_list_price_usd === null ? "unavailable" : `$${number(signal.estimated_list_price_usd, 6)}`} ` +
    `(invoice cost unavailable).`;

  const records = $("records");
  records.replaceChildren();
  for (const run of item.runs) {
    const details = node("details");
    details.append(node("summary", `Seed ${run.seed} · ${run.evaluations_per_lane} evaluations per lane · ` +
      `fingerprint ${run.deterministic_fingerprint.slice(0, 16)}…`));
    const links = node("div", undefined, "record-links");
    for (const [lane, data] of Object.entries(run.lanes)) {
      const path = data.record?.path;
      if (typeof path !== "string" || path.split("/").some((part) => part === ".." || part === "")) continue;
      const a = node("a", `${lane.replaceAll("_", " ")} · signed record`);
      a.href = `/tfl08/${path}`;
      a.setAttribute("download", "");
      a.title = `Public key ${data.record.public_key}`;
      links.append(a);
    }
    details.append(links);
    records.append(details);
  }
  drawCurves(item);
}

async function start() {
  try {
    const response = await fetch("/tfl08/leaderboard.json", {cache: "no-store"});
    if (!response.ok) throw new Error(`batch artifact returned HTTP ${response.status}`);
    report = await response.json();
    if (report.schema !== "tfl08-leaderboard-v1" || !report.benchmarks || typeof report.benchmarks !== "object") {
      throw new Error("batch artifact schema is unsupported");
    }
    const select = $("benchmark");
    select.replaceChildren();
    for (const name of Object.keys(report.benchmarks)) select.append(node("option", name));
    if (!select.options.length) throw new Error("batch artifact contains no benchmarks");
    select.disabled = false;
    select.onchange = () => renderBenchmark(select.value);
    const runtime = report.runtime || {};
    const platform = runtime.platform || {};
    $("environment").textContent = `Generated with Python ${runtime.python || "unknown"}, ` +
      `${platform.system || "unknown"} ${platform.release || ""}, NumPy ${runtime.numpy || "unknown"}, ` +
      `SciPy ${runtime.scipy || "unknown"}; OpenBLAS core type ${runtime.openblas_coretype_env || "unspecified"}. ` +
      `Runner source SHA-256 ${runtime.runner_source_sha256?.slice(0, 16) || "unavailable"}.`;
    renderBenchmark(select.value);
  } catch (error) {
    $("status").textContent = `No published 10-seed batch is available yet (${error.message}). Generate one with the TFL-08 runner and publish its leaderboard.json and records under /tfl08/.`;
  }
}

start();
