// The package builder for engineers (Carter, 22:08Z and 22:13Z), shared by the Live Lab and the Packages page: a layout
// and the door's own result for it, copied exactly from the public results feed's rows; nothing added that the feed
// does not claim. Pure functions; downloads are the pages' own (a Blob and a temporary <a download>, no network call).
import { CASE_ID, CASE_TITLE, DIES, INTERPOSER_MM } from "../package/case-cpu-dram.mjs";
import * as W from "./words.mjs";

const isObj = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
const count = (n) => Number.isSafeInteger(n) && n >= 0;
// ── packages for engineers: built from the results feed's own rows, copied exactly ─────────────────────────────────
// The shared feed keeps only its normalized view; the page keeps each run's newest raw row as the feed returned it.
export const RESULTS_PATH = "/api/open/v1/door/results";
export function keepRawResults(store, doc, max = 2000) {
  if (!isObj(doc) || doc.schema !== "sentilab-door-results/1" || !Array.isArray(doc.items)) return store;
  for (const raw of doc.items) {
    if (!isObj(raw) || typeof raw.id !== "string" || !count(raw.seq)) continue;
    const held = store.get(raw.id);
    if (!held || raw.seq >= held.seq) { store.delete(raw.id); store.set(raw.id, raw); }
  }
  while (store.size > max) store.delete(store.keys().next().value);
  return store;
}
// A layout ships to engineers only once it was accepted and a fresh replay matched (status and replay as the feed says).
// Ready only once the fresh replay matched (verification.replay "reproduced" and replay.match true), never at
// "Accepted \u00b7 replay pending".
export const packageable = (raw) => Boolean(raw && (raw.status === "reproduced" || raw.status === "cross_checked")
  && isObj(raw.result) && raw.result.verification?.replay === "reproduced" && raw.result.replay?.match === true);
// The licence allowlist (Terms v1: the door's terms do not grant redistribution). A download exists only for a run
// whose FULL run id is listed; never matched on a short id or a visit. An unreadable list is an empty one.
export const LICENSED_PATH = "/sentilab/packages/licensed-runs.json";
export const LICENSED_SCHEMA = "sentilab-licensed-runs/1";
const RUN_ID = /^open-[0-9a-f]{8}-[0-9a-f]{32}$/;
const field = (v, max) => (typeof v === "string" && v.length > 0 && v.length <= max && !/[\u0000-\u001f\u007f]/.test(v) ? v : null);
export function readLicences(doc) {
  const out = new Map();
  if (!isObj(doc) || doc.schema !== LICENSED_SCHEMA || !Array.isArray(doc.items)) return out;
  for (const x of doc.items) {
    if (!isObj(x) || typeof x.run_id !== "string" || !RUN_ID.test(x.run_id) || !field(x.licence, 80) || !field(x.owner_role, 40)) continue;
    out.set(x.run_id, { run_id: x.run_id, visit: field(x.visit, 8), owner_role: x.owner_role, licence: x.licence,
      confirmed_by: field(x.confirmed_by, 80), confirmed_at: field(x.confirmed_at, 40) });
  }
  return out;
}
export const downloadable = (raw, licences) => packageable(raw) && Boolean(licences instanceof Map && licences.has(raw.id));
export const ENGINEER_SCHEMA = "sentilab-engineer-package/1";
const copy = (v) => (v === undefined ? null : JSON.parse(JSON.stringify(v)));
// The feed's dies, with exactly the four contract fields.
const diesOf = (dies) => (Array.isArray(dies) ? dies.map((x) => ({ die: x.die, x_um: x.x_um, y_um: x.y_um, rot_deg: x.rot_deg })) : null);
// The door's compact l= string (app/door/intake.py compact_text): "x.y.r" per die in die order, x and y in 500 um steps,
// r in 90 degree steps; null when the layout is not on that lattice.
export function compactLayout(dies) {
  if (!Array.isArray(dies) || !dies.length) return null;
  const d = [...dies].sort((a, b) => a.die - b.die);
  const fits = d.every((x, i) => x.die === i && Number.isSafeInteger(x.x_um / 500) && Number.isSafeInteger(x.y_um / 500) && Number.isSafeInteger(x.rot_deg / 90));
  return fits ? d.map((x) => `${x.x_um / 500}.${x.y_um / 500}.${x.rot_deg / 90}`).join(",") : null;
}
// The run id's own part (open-<door>-<32 hex>: the middle part is shared by every run of a door), first 8 characters.
export const shortRunId = (id) => (String(id).split("-").at(-1) ?? String(id)).slice(0, 8);
export const packageName = (raw) => `sentilab-${raw.short_id ?? "visit"}-${shortRunId(raw.id)}.json`;
export function engineerPackage(raw, { licence = null, submittedAt = null, pageUrl = null, generatedAt = null } = {}) {
  const r = raw.result;
  return {
    schema: ENGINEER_SCHEMA,
    licence: licence?.licence ?? null, owner_role: licence?.owner_role ?? null,
    run_id: raw.id, visit: raw.short_id ?? null, submitted_at: submittedAt,
    layout: { compact: compactLayout(raw.dies), dies: diesOf(raw.dies) },
    case: { id: CASE_ID, title: CASE_TITLE, interposer_mm: INTERPOSER_MM,
      dies: DIES.map(({ id, kind, w_mm, h_mm, power_w, halo_mm }) => ({ id, kind, w_mm, h_mm, power_w, halo_mm })) },
    geometry_sha256: raw.geometry_sha256 ?? null, wire_proxy_mm: raw.wire_proxy_mm ?? null,
    result: { metric: copy(r.metric), max_chiplet_centre_cell_mean_C: copy(r.max_chiplet_centre_cell_mean_C), per_die_C: copy(r.per_die_C),
      active_layer_peak_C: copy(r.active_layer_peak_C), active_guard: copy(r.active_guard), replay: copy(r.replay) },
    verification: copy(r.verification),
    evaluator: copy(r.evaluator),
    labels: { label: copy(r.label), temperature_label: copy(r.temperature_label) },
    source: { page: pageUrl, feed: RESULTS_PATH, generated_at: generatedAt },
    readme: W.PACKAGE.readme(licence),
  };
}
// The accepted, replay-matched layouts, lowest board metric first (the feed's own numbers), at most n.
export function topLayouts(raws, n = 10) {
  return [...(raws ?? [])].filter((x) => packageable(x) && Number.isFinite(x.result.max_chiplet_centre_cell_mean_C))
    .sort((a, b) => a.result.max_chiplet_centre_cell_mean_C - b.result.max_chiplet_centre_cell_mean_C || a.seq - b.seq).slice(0, n);
}
const csvCell = (v) => (v === null || v === undefined ? "" : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v));
export const TOP_CSV_HEADER = ["rank", "visit", "run_id", "max_chiplet_centre_cell_mean_C", "wire_proxy_mm", "replay", "licence", "geometry_sha256", "layout"];
export function topBundle(raws, { licences = new Map(), n = 10, pageUrl = null, generatedAt = null } = {}) {
  const top = topLayouts([...(raws ?? [])].filter((x) => downloadable(x, licences)), n);
  const reference = copy(top[0]?.result?.metric?.reference ?? null);
  const layouts = top.map((raw, i) => ({ rank: i + 1, run_id: raw.id, visit: raw.short_id ?? null, max_chiplet_centre_cell_mean_C: raw.result.max_chiplet_centre_cell_mean_C,
    wire_proxy_mm: raw.wire_proxy_mm ?? null, replay: raw.result.verification.replay, licence: licences.get(raw.id)?.licence ?? null, geometry_sha256: raw.geometry_sha256 ?? null, layout: compactLayout(raw.dies),
    verification: copy(raw.result.verification) }));
  const rows = [TOP_CSV_HEADER.join(",")];
  if (reference) rows.push([W.PACKAGE.referenceRow, "", reference.layout ?? "", reference.value_C, "", "", "", "", ""].map(csvCell).join(","));
  for (const x of layouts) rows.push([x.rank, x.visit, x.run_id, x.max_chiplet_centre_cell_mean_C, x.wire_proxy_mm, x.replay, x.licence, x.geometry_sha256, x.layout].map(csvCell).join(","));
  return { json: { schema: "sentilab-top-layouts/1", reference, metric: copy(top[0]?.result?.metric ?? null), layouts,
    labels: { label: copy(top[0]?.result?.label ?? null), temperature_label: copy(top[0]?.result?.temperature_label ?? null) },
    source: { page: pageUrl, feed: RESULTS_PATH, generated_at: generatedAt }, readme: W.PACKAGE.topReadme }, csv: `${rows.join("\n")}\n` };
}
