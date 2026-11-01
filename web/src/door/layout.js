// Layouts at the door: the compact form (AGENT-DOOR section 3), the contract's dies form, and the preview check.
//
// Compact: eight comma-separated items in the fixed order C0, C1, C2, C3, D0, D1, D2, D3, each <x>.<y>.<r>: x and y the
// die centre in 500 um lattice steps from the interposer's lower-left corner (decimal integers 0..999, no sign, no
// leading zero), r quarter-turns: CPU 0 or 1, DRAM 0. It maps to the contract's proposal dies as
// dies[i] = {die: i, x_um: 500 x, y_um: 500 y, rot_deg: 90 r}. Anything else is refused with contract reason codes:
//   schema_invalid  an item that is not three such integers, a layout that is not a string or is too long, or r of 2
//                   or more (rot_deg outside the contract's enum [0, 90], as the intake reports it)
//   die_count       not exactly eight items
//   rotation_not_allowed  a DRAM turned 90 degrees (r = 1): in the contract's enum, not in its catalogue
//   out_of_frame    a centre beyond the 45 mm frame
// The dies form ({die, x_um, y_um, rot_deg} x 8, only on POST /agents/submit) adds unknown_field, die_order and lattice,
// with the contract's field rules: integers that are JSON integer literals, die 0..31, x_um and y_um 0..1000000,
// rot_deg in [0, 90].
//
// The preview check reproduces TapGeometry.layout_violations (sundai_hotspot/tap_oracle.py) on whole micrometres:
// margin (body plus halo at least 500 um inside every edge), halo_overlap (halo rings may touch, never overlap) and
// min_spacing (bodies at least 100 um apart along x or y), with the same die pairs and amounts. It is a preview: the
// scorer intake's TapGeometry adapter decides legality, and a check never starts a solve.
// Codes carry only their declared fields: die indices and whole-micrometre amounts, never submitted text.
import { BODY_GAP_UM, CONNECTIONS, DIES, EDGE_CLEARANCE_UM, FRAME_UM, LATTICE_UM } from "./case.js";

export const MAX_COMPACT_CHARS = 200;
export const PREVIEW_LABEL = "preview check; the scorer intake decides";
const ITEM = /^(0|[1-9][0-9]{0,2})\.(0|[1-9][0-9]{0,2})\.([0-9])$/;
const DIE_KEYS = ["die", "x_um", "y_um", "rot_deg"];
// The contract's dies schema (contracts/open-proposal-v1/schemas/common.schema.json #/$defs/dies).
const BOUNDS = Object.freeze({ die: [0, 31], x_um: [0, 1000000], y_um: [0, 1000000] });
const ROT_DEG = Object.freeze([0, 90]);

const code = (name, fields = {}) => ({ code: name, ...fields });

// Rotation and frame for dies that already have integer micrometre centres: the codes, in die order.
function catalogue(dies) {
  const found = [];
  for (const die of dies) {
    if (!DIES[die.die].rot_deg.includes(die.rot_deg)) found.push(code("rotation_not_allowed", { dies: [die.die] }));
    const outside = Math.max(die.x_um - FRAME_UM, die.y_um - FRAME_UM, 0);
    if (outside) found.push(code("out_of_frame", { dies: [die.die], amount_um: outside }));
  }
  return found;
}

const compactOf = (dies) => dies.map((die) => `${die.x_um / LATTICE_UM}.${die.y_um / LATTICE_UM}.${die.rot_deg / 90}`).join(",");

// { ok: true, dies, compact } or { ok: false, codes }.
export function parseCompact(text) {
  if (typeof text !== "string") return { ok: false, codes: [code("schema_invalid", { path: "/l", keyword: "type" })] };
  if (text.length === 0) return { ok: false, codes: [code("schema_invalid", { path: "/l", keyword: "minLength" })] };
  if (text.length > MAX_COMPACT_CHARS) return { ok: false, codes: [code("schema_invalid", { path: "/l", keyword: "maxLength" })] };
  const items = text.split(",");
  if (items.length !== DIES.length) return { ok: false, codes: [code("die_count", { count: items.length })] };
  const shape = [];
  const dies = items.map((item, index) => {
    const match = ITEM.exec(item);
    if (!match) { shape.push(code("schema_invalid", { path: `/l/${index}`, keyword: "pattern" })); return null; }
    const rot = Number(match[3]) * 90;
    if (!ROT_DEG.includes(rot)) { shape.push(code("schema_invalid", { path: `/l/${index}`, keyword: "enum" })); return null; }
    return { die: index, x_um: Number(match[1]) * LATTICE_UM, y_um: Number(match[2]) * LATTICE_UM, rot_deg: rot };
  });
  if (shape.length) return { ok: false, codes: shape };
  const found = catalogue(dies);
  return found.length ? { ok: false, codes: found } : { ok: true, dies, compact: compactOf(dies) };
}

const plainObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value) && Object.getPrototypeOf(value) === Object.prototype;

// The contract's dies form: exactly eight {die, x_um, y_um, rot_deg} with integer values, in catalogue order, on the
// lattice and in the frame. Unknown keys are reported by position only: their names are never echoed.
export function parseDies(value) {
  if (!Array.isArray(value)) return { ok: false, codes: [code("schema_invalid", { path: "/layout", keyword: "type" })] };
  if (value.length !== DIES.length) return { ok: false, codes: [code("die_count", { count: Math.min(value.length, 1000000) })] };
  const shape = [];
  value.forEach((die, index) => {
    if (!plainObject(die)) { shape.push(code("schema_invalid", { path: `/layout/${index}`, keyword: "type" })); return; }
    if (Object.keys(die).some((key) => !DIE_KEYS.includes(key))) shape.push(code("unknown_field", { path: `/layout/${index}` }));
    for (const key of DIE_KEYS) {
      const at = `/layout/${index}/${key}`;
      if (!Object.hasOwn(die, key)) shape.push(code("schema_invalid", { path: `/layout/${index}`, keyword: "required" }));
      else if (!Number.isInteger(die[key])) shape.push(code("schema_invalid", { path: at, keyword: "type" }));
      else if (key === "rot_deg") { if (!ROT_DEG.includes(die[key])) shape.push(code("schema_invalid", { path: at, keyword: "enum" })); }
      else if (die[key] < BOUNDS[key][0]) shape.push(code("schema_invalid", { path: at, keyword: "minimum" }));
      else if (die[key] > BOUNDS[key][1]) shape.push(code("schema_invalid", { path: at, keyword: "maximum" }));
    }
  });
  if (shape.length) return { ok: false, codes: shape };
  const misplaced = value.map((die, index) => (die.die === index ? -1 : index)).filter((index) => index >= 0);
  if (misplaced.length) return { ok: false, codes: [code("die_order", { dies: misplaced })] };
  const dies = value.map((die) => ({ die: die.die, x_um: die.x_um, y_um: die.y_um, rot_deg: die.rot_deg }));
  const found = catalogue(dies);
  for (const die of dies) {
    const off = Math.max(...[die.x_um, die.y_um].map((v) => Math.min(v % LATTICE_UM, LATTICE_UM - (v % LATTICE_UM))));
    if (off) found.push(code("lattice", { dies: [die.die], amount_um: off }));
  }
  return found.length ? { ok: false, codes: found } : { ok: true, dies, compact: compactOf(dies) };
}

// Each die's body and halo rectangles in micrometres, [x0, y0, x1, y1], with its own (possibly turned) footprint.
export function rectangles(dies) {
  return dies.map((die) => {
    const spec = DIES[die.die];
    const [w, h] = die.rot_deg === 90 ? [spec.h, spec.w] : [spec.w, spec.h];
    const body = [die.x_um - w / 2, die.y_um - h / 2, die.x_um + w / 2, die.y_um + h / 2];
    return { body, halo: [body[0] - spec.halo, body[1] - spec.halo, body[2] + spec.halo, body[3] + spec.halo] };
  });
}

// Every placement-rule miss, in TapGeometry's order: margins, halo overlaps, then minimum spacing.
export function previewViolations(dies) {
  const rects = rectangles(dies);
  const found = [];
  rects.forEach(({ halo }, index) => {
    const excess = Math.max(EDGE_CLEARANCE_UM - halo[0], EDGE_CLEARANCE_UM - halo[1],
      halo[2] - (FRAME_UM - EDGE_CLEARANCE_UM), halo[3] - (FRAME_UM - EDGE_CLEARANCE_UM));
    if (excess > 0) found.push(code("margin", { dies: [index], amount_um: excess }));
  });
  rects.forEach(({ halo: a }, index) => {
    rects.slice(0, index).forEach(({ halo: b }, other) => {
      if (a[2] <= b[0] || b[2] <= a[0] || a[3] <= b[1] || b[3] <= a[1]) return;
      const depth = Math.min(Math.min(a[2], b[2]) - Math.max(a[0], b[0]), Math.min(a[3], b[3]) - Math.max(a[1], b[1]));
      found.push(code("halo_overlap", { dies: [other, index], amount_um: depth }));
    });
  });
  rects.forEach(({ body: a }, index) => {
    rects.slice(0, index).forEach(({ body: b }, other) => {
      const spacing = Math.max(b[0] - a[2], a[0] - b[2], b[1] - a[3], a[1] - b[3]);
      if (spacing < BODY_GAP_UM) found.push(code("min_spacing", { dies: [other, index], amount_um: BODY_GAP_UM - spacing }));
    });
  });
  return found;
}

// The wire proxy in millimetres: weighted-mean Manhattan distance between die centres, each unordered pair once.
export function wireProxyMm(dies) {
  let weighted = 0;
  let total = 0;
  for (let i = 0; i < dies.length; i += 1) {
    for (let j = i + 1; j < dies.length; j += 1) {
      const wires = CONNECTIONS[i][j];
      weighted += wires * (Math.abs(dies[i].x_um - dies[j].x_um) + Math.abs(dies[i].y_um - dies[j].y_um));
      total += wires;
    }
  }
  return Math.round(weighted / total) / 1000;
}
