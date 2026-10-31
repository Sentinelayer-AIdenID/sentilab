// An independent steady-state thermal network, written from reading public HotSpot source and TAP-2.5D's stack.
// It runs no HotSpot or room code. It exists to measure one question: how much do HotSpot 6's and 7's different
// detailed-3D vertical couplings change the temperature rise, compared with the other suspects?
//
// Simplifications, all stated in the report: lateral links use the half-half form in both versions; heterogeneous
// cells use area-weighted conductivity; microbump rings and interposer edge cells are ignored.

const CELLS = Number(process.env.CELLS ?? 64);
const UNDERFILL = 0.625, COPPER = 0.0025, SILICON = 0.01;
const parallel = (edge, diameter, a, b) => { const ratio = (edge / diameter) ** 2 - 1; return (1 + ratio) * a * b / (b + ratio * a); };
const R_C4 = parallel(0.0006, 0.00025, COPPER, UNDERFILL);
const R_TSV = parallel(0.00005, 0.00001, COPPER, SILICON);
const R_UBUMP = parallel(0.000045, 0.000025, COPPER, UNDERFILL);

function solve(system, opts) {
  const { width: W, chiplets } = system;
  const { link = "v6", rConvec = null, sinkScale = 2, spreaderScale = 2, tim = 0.25 } = opts;
  const n = CELLS, cell = W / n, area = cell * cell;
  const sSp = spreaderScale * W, sHs = sinkScale * sSp, tSp = 0.001, tHs = 0.0069, kCu = 400;
  const rc = rConvec ?? (0.1 * 0.06 * 0.06) / (sHs * sHs);

  // Layers: 0 substrate, 1 C4, 2 interposer, 3 microbump, 4 chip, 5 TIM, 6 spreader, 7 sink.
  const thickness = [0.0002, 0.00007, 0.00011, 0.00001, 0.00015, 0.00002, tSp, tHs];
  const coverage = new Float64Array(n * n);
  const power = new Float64Array(n * n);
  for (const c of chiplets) {
    const dieArea = c.w * c.h;
    for (let i = 0; i < n; i += 1) for (let j = 0; j < n; j += 1) {
      const ox = Math.min((j + 1) * cell, c.x + c.w) - Math.max(j * cell, c.x);
      const oy = Math.min((i + 1) * cell, c.y + c.h) - Math.max(i * cell, c.y);
      if (ox <= 0 || oy <= 0) continue;
      const overlap = ox * oy;
      coverage[i * n + j] += overlap / area;
      power[i * n + j] += (c.p * overlap) / dieArea;
    }
  }
  const conductivity = (layer, cellIndex) => {
    const f = Math.min(1, coverage[cellIndex]);
    switch (layer) {
      case 0: return 1 / 3.33;
      case 1: return 1 / R_C4;
      case 2: return 1 / R_TSV;
      case 3: return f / R_UBUMP + (1 - f) / UNDERFILL;
      case 4: return f / SILICON + (1 - f) / UNDERFILL;
      case 5: return 1 / tim;
      default: return kCu;
    }
  };
  const L = 8, cells = n * n, EXTRA = 12, N = L * cells + EXTRA;
  const id = (l, i, j) => l * cells + i * n + j;
  const SP = (side) => L * cells + side, SC = (side) => L * cells + 4 + side, SO = (side) => L * cells + 8 + side;
  const convCell = (rc * sHs * sHs) / area;
  const rz = (l, c) => thickness[l] / (conductivity(l, c) * area) + (l === 7 ? convCell : 0);
  const rLateral = (l, c) => cell / (conductivity(l, c) * cell * thickness[l]);

  const pkg = {
    sp1: ((sSp - W) / 4) / (kCu * (((sSp + 3 * W) / 4) * tSp)),
    hs1: ((sSp - W) / 4) / (kCu * (((sSp + 3 * W) / 4) * tHs)),
    hs2: ((sSp - W) / 4) / (kCu * (((3 * sSp + W) / 4) * tHs)),
    hs: ((sHs - sSp) / 4) / (kCu * (((sHs + 3 * sSp) / 4) * tHs)),
    spPer: tSp / (kCu * ((sSp + W) * (sSp - W) / 4)),
    hsCPer: tHs / (kCu * ((sSp + W) * (sSp - W) / 4)),
    hsPer: tHs / (kCu * ((sHs * sHs - sSp * sSp) / 4)),
    ambCPer: (rc * sHs * sHs) / ((sSp + W) * (sSp - W) / 4),
    ambPer: (rc * sHs * sHs) / ((sHs * sHs - sSp * sSp) / 4),
  };

  // Edge list, plus a diagonal that holds links to ambient.
  const from = [], to = [], g = [];
  const diag = new Float64Array(N);
  const add = (a, b, resistance) => { const c = 1 / resistance; from.push(a); to.push(b); g.push(c); diag[a] += c; diag[b] += c; };
  const ground = (a, resistance) => { diag[a] += 1 / resistance; };
  for (let l = 0; l < L; l += 1) for (let i = 0; i < n; i += 1) for (let j = 0; j < n; j += 1) {
    const c = i * n + j, a = id(l, i, j);
    if (j < n - 1) add(a, id(l, i, j + 1), rLateral(l, c) / 2 + rLateral(l, c + 1) / 2);
    if (i < n - 1) add(a, id(l, i + 1, j), rLateral(l, c) / 2 + rLateral(l, c + n) / 2);
    if (l < L - 1) {
      let r;
      if (link === "v6") r = rz(l, c);
      else if (l === 0) r = rz(0, c) + rz(1, c) / 2;
      // "v7-fixed": HotSpot 7's half-half form, with convection left out of the spreader-to-sink link.
      else if (link === "v7-fixed" && l === 6) r = rz(6, c) / 2 + (rz(7, c) - convCell) / 2;
      else r = rz(l, c) / 2 + rz(l + 1, c) / 2;
      add(a, id(l + 1, i, j), r);
    } else ground(a, rz(l, c));
  }
  const edge = (l, c) => rLateral(l, c) / 2;
  for (let k = 0; k < n; k += 1) {
    const sides = [[k * n, 0], [k * n + n - 1, 1], [k, 2], [n * (n - 1) + k, 3]];
    for (const [c, side] of sides) {
      const i = Math.floor(c / n), j = c % n;
      add(id(6, i, j), SP(side), edge(6, c) + n * pkg.sp1);
      add(id(7, i, j), SC(side), edge(7, c) + n * pkg.hs1);
    }
  }
  for (let side = 0; side < 4; side += 1) {
    add(SP(side), SC(side), pkg.spPer);
    ground(SC(side), pkg.hsCPer + pkg.ambCPer);
    add(SC(side), SO(side), pkg.hs2 + pkg.hs);
    ground(SO(side), pkg.hsPer + pkg.ambPer);
  }

  // Jacobi-preconditioned conjugate gradient on G T = P.
  const b = new Float64Array(N);
  for (let c = 0; c < cells; c += 1) b[id(4, 0, 0) + c] = power[c];
  const multiply = (x, out) => {
    for (let a = 0; a < N; a += 1) out[a] = diag[a] * x[a];
    for (let e = 0; e < from.length; e += 1) { const a = from[e], d = to[e], c = g[e]; out[a] -= c * x[d]; out[d] -= c * x[a]; }
  };
  const x = new Float64Array(N), r = Float64Array.from(b), z = new Float64Array(N), p = new Float64Array(N), q = new Float64Array(N);
  for (let a = 0; a < N; a += 1) { z[a] = r[a] / diag[a]; p[a] = z[a]; }
  let rho = 0; for (let a = 0; a < N; a += 1) rho += r[a] * z[a];
  const stop = 1e-20 * rho;
  let iterations = 0;
  for (; iterations < 60000 && rho > stop; iterations += 1) {
    multiply(p, q);
    let pq = 0; for (let a = 0; a < N; a += 1) pq += p[a] * q[a];
    const alpha = rho / pq;
    for (let a = 0; a < N; a += 1) { x[a] += alpha * p[a]; r[a] -= alpha * q[a]; z[a] = r[a] / diag[a]; }
    let next = 0; for (let a = 0; a < N; a += 1) next += r[a] * z[a];
    const beta = next / rho; rho = next;
    for (let a = 0; a < N; a += 1) p[a] = z[a] + beta * p[a];
  }

  let gridMax = -1, at = 0;
  for (let c = 0; c < cells; c += 1) if (x[id(4, 0, 0) + c] > gridMax) { gridMax = x[id(4, 0, 0) + c]; at = c; }
  let centerMax = -1;
  for (const d of chiplets) {
    const i = Math.min(n - 1, Math.floor((d.y + d.h / 2) / cell)), j = Math.min(n - 1, Math.floor((d.x + d.w / 2) / cell));
    centerMax = Math.max(centerMax, x[id(4, i, j)]);
  }
  const stack = [4, 5, 6, 7].map((l) => x[l * cells + at]);
  let lost = 0;
  for (let a = 7 * cells; a < 8 * cells; a += 1) lost += x[a] / rz(7, a - 7 * cells);
  for (let side = 0; side < 4; side += 1) lost += x[SC(side)] / (pkg.hsCPer + pkg.ambCPer) + x[SO(side)] / (pkg.hsPer + pkg.ambPer);
  return { gridMax, centerMax, stack, iterations, balance: lost / chiplets.reduce((s, c) => s + c.p, 0), rc, sHs, sSp };
}

const die = (x, y, w, h, p) => ({ x: x / 1000, y: y / 1000, w: w / 1000, h: h / 1000, p });

// Ascend 910 at 45 mm: the compute die flanked by HBMs, with the IO die beside it. Reconstructed by hand from the
// paper's description, not taken from its data. The paper reports placement barely matters here (75.13-75.48 C).
function ascend(W) {
  const s = (W - 45) / 2;
  return { width: W / 1000, chiplets: [
    die(s + 15, s + 6.8, 14.5, 31.4, 256), die(s + 29.8, s + 14.5, 10.5, 16, 14),
    die(s + 7, s + 9, 7.75, 11.87, 20), die(s + 7, s + 24.1, 7.75, 11.87, 20),
    die(s + 29.8, s + 1.5, 7.75, 11.87, 20), die(s + 29.8, s + 31.5, 7.75, 11.87, 20),
  ] };
}
const cpu = (x, y) => die(x, y, 8.25, 9, 150);
const dram = (x, y) => die(x, y, 8.75, 8.75, 20);
// CPU-DRAM at 45 mm: the original clusters the four CPUs at the center with DRAM around them.
function cpuDramClustered(W) {
  const c = W / 2, g = 0.5;
  return { width: W / 1000, chiplets: [
    cpu(c - 8.25 - g / 2, c - 9 - g / 2), cpu(c + g / 2, c - 9 - g / 2), cpu(c - 8.25 - g / 2, c + g / 2), cpu(c + g / 2, c + g / 2),
    dram(c - 8.75 - g / 2 - 9, c - 8.75 - g / 2), dram(c + g / 2 + 9, c - 8.75 - g / 2), dram(c - 8.75 - g / 2 - 9, c + g / 2), dram(c + g / 2 + 9, c + g / 2),
  ] };
}
// TAP-2.5D's answer pushes the CPUs to the corners with DRAM between them.
function cpuDramCorners(W) {
  const e = 0.5, far = W - e;
  return { width: W / 1000, chiplets: [
    cpu(e, e), cpu(far - 8.25, e), cpu(e, far - 9), cpu(far - 8.25, far - 9),
    dram(W / 2 - 4.4, e), dram(W / 2 - 4.4, far - 8.75), dram(e, W / 2 - 4.4), dram(far - 8.75, W / 2 - 4.4),
  ] };
}

const AMBIENT = 45;
const report = (label, system, opts) => {
  const r = solve(system, opts);
  const f = (v) => (v + AMBIENT).toFixed(2).padStart(7);
  console.log(`${label.padEnd(58)} center ${f(r.centerMax)} C  grid-max ${f(r.gridMax)} C  rise ${r.centerMax.toFixed(1).padStart(6)} K  [chip ${r.stack.map((t) => t.toFixed(1)).join(" > ")}]  bal ${r.balance.toFixed(4)} it ${r.iterations}`);
  return r;
};

console.log(`grid ${CELLS}x${CELLS}, 8 layers, ambient ${AMBIENT} C. Paper targets at 45 mm: Ascend original 75.48, CPU-DRAM original 115.94, TAP corners 94.89.`);
console.log("\n-- TAP-2.5D's configuration: spreader 2x, sink 2x spreader, r_convec scaled to hold the transfer coefficient");
const a6 = report("Ascend 45 mm, HotSpot 6 coupling", ascend(45), { link: "v6" });
const a7 = report("Ascend 45 mm, HotSpot 7 coupling", ascend(45), { link: "v7" });
report("CPU-DRAM clustered 45 mm, HotSpot 6 coupling", cpuDramClustered(45), { link: "v6" });
report("CPU-DRAM clustered 45 mm, HotSpot 7 coupling", cpuDramClustered(45), { link: "v7" });
report("CPU-DRAM corners 45 mm, HotSpot 6 coupling", cpuDramCorners(45), { link: "v6" });
report("CPU-DRAM corners 45 mm, HotSpot 7 coupling", cpuDramCorners(45), { link: "v7" });
console.log(`rise ratio, Ascend 7 over 6: ${(a7.centerMax / a6.centerMax).toFixed(2)}`);
report("Ascend 45 mm, HotSpot 7 with convection removed from the link", ascend(45), { link: "v7-fixed" });
report("CPU-DRAM clustered 45 mm, same fix", cpuDramClustered(45), { link: "v7-fixed" });
report("CPU-DRAM corners 45 mm, same fix", cpuDramCorners(45), { link: "v7-fixed" });

console.log("\n-- Other suspects, each changed alone on Ascend");
report("50 mm interposer, HotSpot 6", ascend(50), { link: "v6" });
report("50 mm interposer, HotSpot 7", ascend(50), { link: "v7" });
report("r_convec left at 0.1 with sink 2x spreader, HotSpot 6", ascend(45), { link: "v6", rConvec: 0.1 });
report("r_convec left at 0.1 with sink 2x spreader, HotSpot 7", ascend(45), { link: "v7", rConvec: 0.1 });
report("r_convec for the 50 mm config used at 45 mm, HotSpot 6", ascend(45), { link: "v6", rConvec: (0.1 * 0.06 * 0.06) / 0.04 });
report("spreader 1.2x and sink 1.5x, r_convec scaled, HotSpot 6", ascend(45), { link: "v6", spreaderScale: 1.2, sinkScale: 1.5 });
report("TIM k=1 instead of 4, HotSpot 6", ascend(45), { link: "v6", tim: 1 });
