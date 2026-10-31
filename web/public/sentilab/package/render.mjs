// SentiLab Package view: Canvas 2D isometric renderer. Hand-written for this page: no libraries, no models, no
// textures, no third-party assets. Every shape is drawn from the scene (scene.mjs): footprints from the evidence's
// geometry, top-face colours from chiplet-centre temperatures on the run's fixed scale, and a schematic stack.
//
// Honesty rules held here:
//   - a chiplet's top face is ONE flat colour (its centre value); there is no gradient across a die;
//   - side faces are the same colour, flat-shaded for depth only;
//   - stale values are drawn desaturated and tagged "stale";
//   - the stack (substrate, interposer, heights, lid) is schematic and labelled so on the main canvas.
import { STACK } from "./scene.mjs";

export const ISO_ELEVATION = Math.atan(1 / Math.SQRT2);   // true isometric, about 35.26 degrees
export const HOME_AZIMUTH = -45;                          // camera at the package's lower-left (south-west) corner
export const GLIDE_MS = 700;
export const FADE_MS = 450;
export const PULSE_MS = 1500;
export const ORBIT_MS = 1600;

export const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const clamp01 = (t) => Math.max(0, Math.min(1, t));
const lerp = (a, b, t) => a + (b - a) * t;

// ── colour helpers ────────────────────────────────────────────────────────────────────────────────────────────
export function rgb(hex) {
  const h = String(hex).replace("#", "");
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
}
const toHex = (c) => `#${c.map((v) => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, "0")).join("")}`;
export const mix = (a, b, t) => toHex(rgb(a).map((v, i) => lerp(v, rgb(b)[i], t)));
export const shade = (hex, f) => toHex(rgb(hex).map((v) => v * f));
export function desaturate(hex, amount = 0.78) {
  const c = rgb(hex);
  const l = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  return toHex(c.map((v) => lerp(v, l * 0.82 + 28, amount)));
}
export const luminance = (hex) => { const c = rgb(hex); return (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255; };
const rgba = (hex, a) => { const c = rgb(hex); return `rgba(${c[0]},${c[1]},${c[2]},${a})`; };

export const PALETTE = Object.freeze({
  substrate: "#1d3b35", interposer: "#2b3944", noTemp: "#3b4c55", lid: "#c9d6d9", accept: "#e7c48f",
  overlap: "#f0937a", ghost: "#9fb4bb", ink: "#0b1418", inkLight: "#f4f7f6", stale: "#e7c48f", ball: "#4a5960",
});

// ── camera ────────────────────────────────────────────────────────────────────────────────────────────────────
// Orthographic: rotate about the package centre by the azimuth, then tilt by the elevation. The fit uses the
// footprint's bounding circle, so the scale stays the same while the camera orbits.
export function stackHeights() {
  const S = STACK.substrate_mm, I = STACK.interposer_mm;
  const chipBase = S + I;
  const lidTop = chipBase + Math.max(STACK.die_mm, STACK.hbm_mm) + STACK.lid_clearance_mm + STACK.lid_mm;
  return { S, I, chipBase, lidTop };
}

export function makeCamera({ width, height, substrate, azimuthDeg = HOME_AZIMUTH, elevation = ISO_ELEVATION, pad = {} }) {
  const p = { l: 16, r: 16, t: 16, b: 16, ...pad };
  const cx = (substrate.x0 + substrate.x1) / 2, cy = (substrate.y0 + substrate.y1) / 2;
  const R = Math.hypot((substrate.x1 - substrate.x0) / 2, (substrate.y1 - substrate.y0) / 2);
  const { lidTop } = stackHeights();
  const zLo = -0.8, zHi = lidTop;
  const se = Math.sin(elevation), ce = Math.cos(elevation);
  const upMin = -R * se + zLo * ce, upMax = R * se + zHi * ce;
  const availW = Math.max(10, width - p.l - p.r), availH = Math.max(10, height - p.t - p.b);
  const s = Math.max(0.5, Math.min(availW / (2 * R), availH / (upMax - upMin)));
  const ox = p.l + availW / 2;
  const oy = p.t + availH / 2 + (s * (upMax + upMin)) / 2;
  const az = (azimuthDeg * Math.PI) / 180, ca = Math.cos(az), sa = Math.sin(az);
  const project = (x, y, z) => {
    const dx = x - cx, dy = y - cy;
    const rx = dx * ca + dy * sa;
    const ry = -dx * sa + dy * ca;
    return [ox + s * rx, oy - s * (ry * se + z * ce)];
  };
  // Horizontal unit vector pointing from the package toward the camera, and screen-right in world xy.
  const toward = { x: sa, y: -ca };
  const right = { x: ca, y: sa };
  const depth = (x, y) => (x - cx) * toward.x + (y - cy) * toward.y;
  return { project, toward, right, depth, s, width, height, azimuthDeg };
}

// ── boxes ─────────────────────────────────────────────────────────────────────────────────────────────────────
const SIDES = [
  { i: 0, j: 1, n: { x: 0, y: -1 } },   // south
  { i: 1, j: 2, n: { x: 1, y: 0 } },    // east
  { i: 2, j: 3, n: { x: 0, y: 1 } },    // north
  { i: 3, j: 0, n: { x: -1, y: 0 } },   // west
];
const cornersOf = (b) => [[b.x0, b.y0], [b.x1, b.y0], [b.x1, b.y1], [b.x0, b.y1]];

function boxGeometry(cam, b) {
  const c = cornersOf(b);
  const bottom = c.map(([x, y]) => cam.project(x, y, b.z0));
  const top = c.map(([x, y]) => cam.project(x, y, b.z1));
  const sides = SIDES.filter((f) => f.n.x * cam.toward.x + f.n.y * cam.toward.y > 1e-6)
    .map((f) => ({ ...f, poly: [bottom[f.i], bottom[f.j], top[f.j], top[f.i]], lit: f.n.x * cam.right.x + f.n.y * cam.right.y }));
  const xs = [...bottom, ...top].map((q) => q[0]), ys = [...bottom, ...top].map((q) => q[1]);
  return { bottom, top, sides, bbox: { x0: Math.min(...xs), y0: Math.min(...ys), x1: Math.max(...xs), y1: Math.max(...ys) } };
}

function poly(ctx, pts) {
  ctx.beginPath();
  ctx.moveTo(pts[0][0], pts[0][1]);
  for (let k = 1; k < pts.length; k += 1) ctx.lineTo(pts[k][0], pts[k][1]);
  ctx.closePath();
}

// Flat shading: faces turned to screen-left are lighter, to screen-right darker. One colour per face.
const sideFactor = (lit) => 0.66 - 0.17 * lit;

function drawBox(ctx, cam, b, style) {
  const g = boxGeometry(cam, b);
  ctx.save();
  ctx.globalAlpha = style.alpha ?? 1;
  ctx.lineJoin = "round";
  for (const side of g.sides) {
    poly(ctx, side.poly);
    ctx.fillStyle = shade(style.side ?? style.top, sideFactor(side.lit) * (style.sideDim ?? 1));
    ctx.fill();
    if (style.stripes) {
      // Memory stacks: thin lines on the sides suggest stacked dies (schematic).
      ctx.strokeStyle = "rgba(0,0,0,0.28)";
      ctx.lineWidth = 1;
      for (let k = 1; k < style.stripes; k += 1) {
        const t = k / style.stripes;
        const a = [lerp(side.poly[0][0], side.poly[3][0], t), lerp(side.poly[0][1], side.poly[3][1], t)];
        const z = [lerp(side.poly[1][0], side.poly[2][0], t), lerp(side.poly[1][1], side.poly[2][1], t)];
        ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(z[0], z[1]); ctx.stroke();
      }
    }
    ctx.strokeStyle = style.edge ?? "rgba(4,10,12,0.55)";
    ctx.lineWidth = style.edgeWidth ?? 1;
    ctx.stroke();
  }
  poly(ctx, g.top);
  ctx.fillStyle = style.top;
  ctx.fill();
  ctx.strokeStyle = style.topEdge ?? "rgba(255,255,255,0.22)";
  ctx.lineWidth = style.topEdgeWidth ?? 1;
  ctx.stroke();
  ctx.restore();
  return g;
}

// Painter's order for boxes that sit on a common plane: if a vertical plane separates two footprints, the one on the
// camera's side is drawn later. Overlapping footprints (a stacked layer, or a constraint failure) fall back to base
// height, then centre depth. Only pairs whose screen boxes overlap are ordered; Kahn's sort, nearest last.
export function paintOrder(cam, boxes, geoms) {
  const n = boxes.length;
  const after = Array.from({ length: n }, () => []);
  const indeg = new Array(n).fill(0);
  const t = cam.toward, eps = 1e-6;
  const sep = (a0, a1, b0, b1, tc) => (a1 <= b0 + eps ? (tc > eps ? -1 : tc < -eps ? 1 : 0) : b1 <= a0 + eps ? (tc > eps ? 1 : tc < -eps ? -1 : 0) : null);
  const centreDepth = (b) => cam.depth((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2);
  for (let i = 0; i < n; i += 1) {
    for (let j = i + 1; j < n; j += 1) {
      const A = geoms[i].bbox, B = geoms[j].bbox;
      if (A.x1 < B.x0 || B.x1 < A.x0 || A.y1 < B.y0 || B.y1 < A.y0) continue;
      const a = boxes[i], b = boxes[j];
      const sx = sep(a.x0, a.x1, b.x0, b.x1, t.x), sy = sep(a.y0, a.y1, b.y0, b.y1, t.y);
      let ord;
      if (sx !== null && sy !== null && sx !== 0 && sy !== 0 && sx !== sy) ord = Math.abs(t.x) >= Math.abs(t.y) ? sx : sy;
      else if (sx !== null && sx !== 0) ord = sx;
      else if (sy !== null && sy !== 0) ord = sy;
      else if (a.z0 !== b.z0 && (sx === null && sy === null)) ord = a.z0 < b.z0 ? -1 : 1;
      else ord = centreDepth(a) <= centreDepth(b) ? -1 : 1;
      const [first, second] = ord < 0 ? [i, j] : [j, i];
      after[first].push(second);
      indeg[second] += 1;
    }
  }
  const out = [], done = new Array(n).fill(false);
  const byDepth = (i) => centreDepth(boxes[i]) + boxes[i].z0 * 0.01;
  while (out.length < n) {
    let pick = -1;
    for (let i = 0; i < n; i += 1) if (!done[i] && indeg[i] === 0 && (pick < 0 || byDepth(i) < byDepth(pick))) pick = i;
    if (pick < 0) for (let i = 0; i < n; i += 1) if (!done[i] && (pick < 0 || byDepth(i) < byDepth(pick))) pick = i;   // a cycle: nearest-last
    done[pick] = true;
    out.push(pick);
    for (const k of after[pick]) indeg[k] -= 1;
  }
  return out;
}

// ── labels ────────────────────────────────────────────────────────────────────────────────────────────────────
const SANS = '"Inter", "Segoe UI", system-ui, -apple-system, sans-serif';
const fmt1 = (v) => (Math.round(v * 10) / 10).toFixed(1);

function fitText(ctx, text, weight, size, maxW, family = SANS) {
  let s = size;
  ctx.font = `${weight} ${s}px ${family}`;
  while (s > 9 && ctx.measureText(text).width > maxW) { s -= 1; ctx.font = `${weight} ${s}px ${family}`; }
  return s;
}

function drawChipletLabel(ctx, c, top, unit) {
  const xs = top.map((q) => q[0]), ys = top.map((q) => q[1]);
  const cx = xs.reduce((a, b) => a + b, 0) / 4, cy = ys.reduce((a, b) => a + b, 0) / 4;
  const fw = Math.max(...xs) - Math.min(...xs), fh = Math.max(...ys) - Math.min(...ys);
  const hasT = c.temp !== null && c.temp !== undefined;
  const ink = luminance(c.fill) > 0.46 ? PALETTE.ink : PALETTE.inkLight;
  const maxW = fw * 0.62;
  ctx.save();
  ctx.globalAlpha = c.alpha;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  if (ink === PALETTE.inkLight) { ctx.shadowColor = "rgba(0,0,0,0.55)"; ctx.shadowBlur = 3; ctx.shadowOffsetY = 1; }
  ctx.fillStyle = ink;
  const idSize = fitText(ctx, c.id, 600, Math.min(17, Math.max(10, fh * 0.2)), maxW);
  if (!hasT) {
    ctx.globalAlpha = c.alpha * 0.9;
    ctx.fillText(c.id, cx, cy);
    ctx.restore();
    return;
  }
  const value = `${fmt1(c.temp)}${unit === "°C" ? "°" : ""}`;
  const vSize = fitText(ctx, value, 700, Math.min(28, Math.max(11, fh * 0.34)), maxW);
  const gap = Math.max(2, vSize * 0.12);
  const totalH = idSize + gap + vSize + (c.state === "stale" ? vSize * 0.75 : 0);
  let y = cy - totalH / 2 + idSize / 2;
  ctx.font = `600 ${idSize}px ${SANS}`;
  ctx.globalAlpha = c.alpha * 0.86;
  ctx.fillText(c.id, cx, y);
  y += idSize / 2 + gap + vSize / 2;
  ctx.globalAlpha = c.alpha;
  ctx.font = `700 ${vSize}px ${SANS}`;
  ctx.fillText(value, cx, y);
  if (c.state === "stale") {
    const tag = "STALE", ts = Math.max(9, Math.round(vSize * 0.46));
    ctx.font = `700 ${ts}px ${SANS}`;
    const tw = ctx.measureText(tag).width + ts * 0.9, th = ts * 1.45;
    const ty = y + vSize / 2 + th / 2 + 2;
    ctx.shadowColor = "transparent";
    ctx.fillStyle = "rgba(20,16,8,0.82)";
    roundRect(ctx, cx - tw / 2, ty - th / 2, tw, th, 3); ctx.fill();
    ctx.strokeStyle = PALETTE.stale; ctx.lineWidth = 1; ctx.stroke();
    ctx.fillStyle = PALETTE.stale;
    ctx.fillText(tag, cx, ty + 0.5);
  }
  ctx.restore();
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y); ctx.lineTo(x + w - r, y); ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r); ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h); ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r); ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

// ── the package ───────────────────────────────────────────────────────────────────────────────────────────────
// frame: { footprint, chiplets: [{ id, x, y, w, h, layer, kind, temp, state, fill, alpha, overlap }], ghosts,
//          overlaps, pulse (0..1 or null), accepted (bool), unit }
// opts:  { width, height, azimuthDeg, labels (bool), callouts (bool), lid (bool), pad }
export function drawPackage(ctx, frame, opts) {
  const { width, height } = opts;
  ctx.clearRect(0, 0, width, height);
  if (!frame || !frame.footprint) return null;
  const { substrate, interposer } = frame.footprint;
  const cam = makeCamera({ width, height, substrate, azimuthDeg: opts.azimuthDeg, pad: opts.pad });
  const { S, I, chipBase, lidTop } = stackHeights();

  // Soft shadow under the package (decorative, outside the die).
  ctx.save();
  const sh = cornersOf(substrate).map(([x, y]) => cam.project(x, y, -0.4));
  ctx.shadowColor = "rgba(0,0,0,0.55)";
  ctx.shadowBlur = Math.max(8, cam.s * 2.2);
  ctx.shadowOffsetY = Math.max(4, cam.s * 0.9);
  poly(ctx, sh); ctx.fillStyle = "rgba(0,0,0,0.5)"; ctx.fill();
  ctx.restore();

  // Solder balls along the two visible bottom edges (schematic).
  if (opts.balls !== false && cam.s >= 6) {
    const r = 0.55 * cam.s;
    ctx.save();
    for (const side of SIDES) {
      if (side.n.x * cam.toward.x + side.n.y * cam.toward.y <= 1e-6) continue;
      const c = cornersOf(substrate), a = c[side.i], b = c[side.j];
      const len = Math.hypot(b[0] - a[0], b[1] - a[1]), n = Math.floor(len / 2.2);
      for (let k = 0; k <= n; k += 1) {
        const t = (k + 0.5) / (n + 1);
        const x = lerp(a[0], b[0], t) - side.n.x * 0.9, y = lerp(a[1], b[1], t) - side.n.y * 0.9;
        const [px, py] = cam.project(x, y, -0.15);
        ctx.beginPath(); ctx.ellipse(px, py, r, r * 0.8, 0, 0, Math.PI * 2);
        ctx.fillStyle = PALETTE.ball; ctx.fill();
        ctx.strokeStyle = "rgba(0,0,0,0.45)"; ctx.lineWidth = 1; ctx.stroke();
      }
    }
    ctx.restore();
  }

  const subG = drawBox(ctx, cam, { ...substrate, z0: 0, z1: S }, { top: PALETTE.substrate, topEdge: "rgba(160,210,190,0.18)" });
  const intG = drawBox(ctx, cam, { ...interposer, z0: S, z1: S + I }, { top: PALETTE.interposer, topEdge: "rgba(190,215,225,0.30)" });

  // The board's accepted package carries a thin gold edge; the acceptance itself pulses it once.
  if (frame.accepted || frame.pulse !== null) {
    const p = frame.pulse;
    ctx.save();
    const grow = p === null ? 0 : easeInOut(p) * 2.4;
    const ring = cornersOf({ x0: interposer.x0 - grow, y0: interposer.y0 - grow, x1: interposer.x1 + grow, y1: interposer.y1 + grow }).map(([x, y]) => cam.project(x, y, S + I));
    poly(ctx, ring);
    ctx.strokeStyle = rgba(PALETTE.accept, p === null ? 0.55 : 0.95 * (1 - p) + 0.1);
    ctx.lineWidth = p === null ? 1.5 : 2 + 5 * (1 - p);
    if (p !== null) { ctx.shadowColor = rgba(PALETTE.accept, 0.9 * (1 - p)); ctx.shadowBlur = 18 * (1 - p); }
    ctx.stroke();
    ctx.restore();
  }

  // Ghost footprints: where gliding chiplets came from (dashed outlines on the interposer, fading out).
  for (const gh of frame.ghosts ?? []) {
    if (gh.alpha <= 0.01) continue;
    const z = chipBase + gh.layer * STACK.die_mm;
    const pts = cornersOf({ x0: gh.x, y0: gh.y, x1: gh.x + gh.w, y1: gh.y + gh.h }).map(([x, y]) => cam.project(x, y, z));
    ctx.save();
    ctx.globalAlpha = gh.alpha;
    poly(ctx, pts);
    ctx.setLineDash([5, 4]);
    ctx.strokeStyle = PALETTE.ghost; ctx.lineWidth = 1.4; ctx.stroke();
    ctx.restore();
  }

  // Lid outline (cut away): edges not on the camera side are drawn before the chiplets, so dies hide them.
  const lidBox = { x0: substrate.x0 + 1.2, y0: substrate.y0 + 1.2, x1: substrate.x1 - 1.2, y1: substrate.y1 - 1.2, z0: S, z1: lidTop };
  const lidEdges = opts.lid ? lidLines(cam, lidBox) : null;
  if (lidEdges) strokeLines(ctx, lidEdges.back, rgba(PALETTE.lid, 0.22));

  // Chiplets.
  const boxes = frame.chiplets.map((c) => {
    const z0 = chipBase + c.layer * STACK.die_mm;
    return { x0: c.x, y0: c.y, x1: c.x + c.w, y1: c.y + c.h, z0, z1: z0 + (c.kind === "hbm" ? STACK.hbm_mm : STACK.die_mm) * c.grow };
  });
  const geoms = boxes.map((b) => boxGeometry(cam, b));
  const order = paintOrder(cam, boxes, geoms);
  const tops = new Array(boxes.length);
  for (const k of order) {
    const c = frame.chiplets[k];
    if (c.alpha <= 0.01) continue;
    const overlapping = c.overlap;
    tops[k] = drawBox(ctx, cam, boxes[k], {
      top: c.fill, alpha: c.alpha * (overlapping ? 0.72 : 1), stripes: c.kind === "hbm" ? 4 : 0,
      edge: overlapping ? rgba(PALETTE.overlap, 0.9) : "rgba(4,10,12,0.6)", edgeWidth: overlapping ? 1.6 : 1,
      topEdge: overlapping ? PALETTE.overlap : c.state === "stale" ? rgba(PALETTE.stale, 0.75) : "rgba(255,255,255,0.38)",
      topEdgeWidth: overlapping || c.state === "stale" ? 1.8 : 1.1,
    }).top;
  }
  // Overlaps that failed the constraint check: the shared rectangle, outlined at the taller top.
  for (const o of frame.overlaps ?? []) {
    const a = frame.chiplets.find((c) => c.id === o.a), b = frame.chiplets.find((c) => c.id === o.b);
    if (!a || !b) continue;
    const z = chipBase + Math.max(a.kind === "hbm" ? STACK.hbm_mm : STACK.die_mm, b.kind === "hbm" ? STACK.hbm_mm : STACK.die_mm) + 0.02;
    const pts = cornersOf(o).map(([x, y]) => cam.project(x, y, z));
    ctx.save();
    poly(ctx, pts);
    ctx.fillStyle = rgba(PALETTE.overlap, 0.32); ctx.fill();
    ctx.setLineDash([6, 4]); ctx.strokeStyle = PALETTE.overlap; ctx.lineWidth = 2; ctx.stroke();
    ctx.restore();
  }
  if (lidEdges) strokeLines(ctx, lidEdges.front, rgba(PALETTE.lid, 0.5));

  if (opts.labels) {
    frame.chiplets.forEach((c, k) => { if (tops[k] && c.alpha > 0.05) drawChipletLabel(ctx, c, tops[k], frame.unit); });
  }
  if (opts.callouts) drawCallouts(ctx, cam, { substrate, interposer, lidBox, S, I, chipBase, lid: opts.lid, chiplets: frame.chiplets });
  return cam;
}

function lidLines(cam, b) {
  const c = cornersOf(b);
  const lo = c.map(([x, y]) => cam.project(x, y, b.z0)), hi = c.map(([x, y]) => cam.project(x, y, b.z1));
  const visible = SIDES.filter((f) => f.n.x * cam.toward.x + f.n.y * cam.toward.y > 1e-6).map((f) => [f.i, f.j]);
  const front = [], back = [];
  const onFront = (i) => visible.some(([a, b2]) => a === i || b2 === i);
  for (let i = 0; i < 4; i += 1) {
    const j = (i + 1) % 4;
    const isFront = visible.some(([a, b2]) => a === i && b2 === j);
    (isFront ? front : back).push([lo[i], lo[j]]);
    front.push([hi[i], hi[j]]);                        // the lid's top edges sit above every chiplet
    (onFront(i) ? front : back).push([lo[i], hi[i]]);
  }
  return { front, back };
}
function strokeLines(ctx, lines, color) {
  ctx.save();
  ctx.setLineDash([7, 6]);
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.3;
  for (const [a, b] of lines) { ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke(); }
  ctx.restore();
}

// Stack callouts on the main canvas: leader lines from the left silhouette to plain labels.
function drawCallouts(ctx, cam, g) {
  const leftCorner = (rect, z) => cornersOf(rect).map(([x, y]) => cam.project(x, y, z)).sort((a, b) => a[0] - b[0])[0];
  // The chiplet callout points at the left top corner of the left-most memory stack (or chiplet), never at a label.
  const shown = g.chiplets.filter((c) => c.alpha > 0.5);
  const pool = shown.some((c) => c.kind === "hbm") ? shown.filter((c) => c.kind === "hbm") : shown;
  const chip = pool.map((c) => ({ c, p: leftCorner({ x0: c.x, y0: c.y, x1: c.x + c.w, y1: c.y + c.h }, g.chipBase + c.layer * STACK.die_mm + (c.kind === "hbm" ? STACK.hbm_mm : STACK.die_mm) * c.grow * 0.5) }))
    .sort((a, b) => a.p[0] - b.p[0])[0];
  const items = [
    { text: "SUBSTRATE", at: leftCorner(g.substrate, g.S * 0.5) },
    { text: "INTERPOSER", at: leftCorner(g.interposer, g.S + g.I * 0.5) },
  ];
  if (chip) items.push({ text: chip.c.kind === "hbm" ? "HBM STACK · drawn taller" : "CHIPLET", at: chip.p });
  if (g.lid) items.push({ text: "LID · outline, cut away", at: leftCorner(g.lidBox, g.lidBox.z1) });
  ctx.save();
  ctx.font = `600 14px ${SANS}`;
  const widest = Math.max(...items.map((it) => ctx.measureText(it.text).width));
  const minX = Math.min(...items.map((it) => it.at[0]));
  const labelX = Math.max(14, minX - widest - 70);
  // Spread label rows so they never collide: bottom-up, at least 32 px apart.
  const rows = items.map((it) => ({ ...it, y: it.at[1] })).sort((a, b) => b.y - a.y);
  rows[0].y += 14;
  for (let k = 1; k < rows.length; k += 1) rows[k].y = Math.min(rows[k].y, rows[k - 1].y - 32);
  ctx.textBaseline = "middle";
  for (const r of rows) {
    const tw = ctx.measureText(r.text).width;
    ctx.strokeStyle = "rgba(170,195,202,0.6)";
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.moveTo(labelX + tw + 10, r.y);
    ctx.lineTo(Math.max(labelX + tw + 12, r.at[0] - 22), r.y);
    ctx.lineTo(r.at[0], r.at[1]);
    ctx.stroke();
    ctx.beginPath(); ctx.arc(r.at[0], r.at[1], 3, 0, Math.PI * 2); ctx.fillStyle = "#d6e2e5"; ctx.fill();
    ctx.fillStyle = "#c6d5d9";
    ctx.fillText(r.text, labelX, r.y);
  }
  const lowest = Math.max(...rows.map((r) => r.y));
  ctx.font = `500 13.5px ${SANS}`;
  ctx.fillStyle = "#95aab1";
  ctx.fillText("schematic stack · heights not to scale", labelX, lowest + 34);
  ctx.fillText("footprints from the evidence, to scale", labelX, lowest + 54);
  ctx.restore();
}

// ── animation state per track ─────────────────────────────────────────────────────────────────────────────────
// Holds what a track's canvas is showing and tweens it: a glide when the playhead crosses a move (700 ms
// ease-in-out, from the parent layout to the candidate), a colour fade when a value arrives or turns stale, and a
// one-off pulse when the gate accepts. With reduced motion everything is a jump cut.
const displayFill = (c) => (c.color ? (c.temp_state === "stale" ? desaturate(c.color) : c.color) : PALETTE.noTemp);

export class TrackAnimation {
  constructor() {
    this.items = new Map();      // chiplet id -> { from, to, start, dur, fill0, fill1, fstart, alpha0, alpha1, data }
    this.ghosts = [];
    this.layout = null;
    this.pulseStart = null;
    this.accepted = false;
  }

  // layout: a scene layout or null. move: the timeline move crossed by this step (or null). animate: tween or cut.
  set(layout, { move = null, animate = false, pulse = false, accepted = false, now = 0 } = {}) {
    const current = new Map(this.frame(now).chiplets.map((c) => [c.id, c]));
    const next = new Map();
    const fromOf = new Map((move?.chiplets ?? []).filter((c) => c.from).map((c) => [c.id, c.from]));
    if (move || !animate) this.ghosts = [];
    for (const c of layout?.chiplets ?? []) {
      const fill = displayFill(c);
      const cur = current.get(c.id);
      const parent = fromOf.get(c.id);
      let start = parent ?? (cur ? { x: cur.x, y: cur.y, w: cur.w, h: cur.h, layer: cur.layer } : null);
      const glide = animate && start && (start.x !== c.x || start.y !== c.y || start.w !== c.w || start.h !== c.h);
      if (glide && parent) this.ghosts.push({ ...parent, start: now });
      if (!animate) start = null;
      next.set(c.id, {
        data: c,
        from: glide ? start : null, start: now, dur: GLIDE_MS,
        fill0: animate && cur ? cur.fill : animate && !cur && parent ? PALETTE.noTemp : fill, fill1: fill, fstart: now,
        alpha0: animate && !cur && !parent ? 0 : 1, grow0: animate && !cur && !parent ? 0.05 : 1,
      });
    }
    // Chiplets that left the layout fade out where they were.
    if (animate) {
      for (const [id, cur] of current) {
        if (next.has(id)) continue;
        next.set(id, { data: { ...cur, temp: cur.temp }, leaving: true, from: null, start: now, dur: FADE_MS, fill0: cur.fill, fill1: cur.fill, fstart: now, alpha0: cur.alpha, grow0: 1 });
      }
    }
    this.items = next;
    this.layout = layout;
    this.accepted = accepted;
    if (pulse) this.pulseStart = now;
    else if (!animate) this.pulseStart = null;
  }

  frame(now) {
    const chiplets = [];
    let active = false;
    const overlapIds = new Set((this.layout?.overlaps ?? []).flatMap((o) => [o.a, o.b]));
    for (const [id, it] of this.items) {
      const d = it.data;
      const tg = clamp01((now - it.start) / it.dur);
      const e = easeInOut(tg);
      let x = d.x, y = d.y, w = d.w, h = d.h;
      if (it.from && tg < 1) { x = lerp(it.from.x, d.x, e); y = lerp(it.from.y, d.y, e); w = lerp(it.from.w, d.w, e); h = lerp(it.from.h, d.h, e); active = true; }
      const tf = clamp01((now - it.fstart) / FADE_MS);
      const fill = tf < 1 && it.fill0 !== it.fill1 ? mix(it.fill0, it.fill1, easeInOut(tf)) : it.fill1;
      if (tf < 1 && it.fill0 !== it.fill1) active = true;
      let alpha = 1, grow = 1;
      if (it.leaving) { alpha = (1 - tg) * (it.alpha0 ?? 1); if (tg < 1) active = true; }
      else if (it.alpha0 < 1 || it.grow0 < 1) { alpha = lerp(it.alpha0, 1, e); grow = lerp(it.grow0, 1, e); if (tg < 1) active = true; }
      if (it.leaving && tg >= 1) continue;
      chiplets.push({ id, x, y, w, h, layer: d.layer, kind: d.kind, temp: d.temp, state: d.temp_state, fill, alpha, grow, overlap: overlapIds.has(id) });
    }
    const ghosts = this.ghosts.map((g) => {
      const t = clamp01((now - g.start) / (GLIDE_MS + 500));
      if (t < 1) active = true;
      return { ...g, alpha: 0.85 * (1 - t) };
    }).filter((g) => g.alpha > 0.01);
    let pulse = null;
    if (this.pulseStart !== null) {
      const t = (now - this.pulseStart) / PULSE_MS;
      if (t < 1) { pulse = clamp01(t); active = true; } else this.pulseStart = null;
    }
    return { chiplets, ghosts, pulse, active, overlaps: this.layout?.overlaps ?? [], accepted: this.accepted };
  }
}
