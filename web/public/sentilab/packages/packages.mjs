// SentiLab packages (Carter, 22:13Z: "since it's open source when packages are ready with all stuff post them too").
// Every accepted layout whose fresh-process replay matched, coolest first, each downloadable as the same package the
// Live Lab builds (live/package-export.mjs), from the public results feed's own rows. Every page of the feed is read,
// through the Live Lab's request gate (spacing, backoff, Retry-After); scoring may be closed and past layouts still list.
// The submission time is the run's own first record (the results row's `arrival` seq, read from the events feed).
import { createGate } from "../live/live-model.mjs";
import * as P from "../live/package-export.mjs";
import * as W from "../live/words.mjs";
import { readBodyCapped, MAX_API_BYTES } from "../view-core.mjs";

const gate = createGate();
const $ = (id) => document.getElementById(id);
function h(tag, props = null, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props ?? {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v; else el.setAttribute(k, v === true ? "" : String(v));
  }
  for (const c of kids.flat()) if (c !== null && c !== undefined && c !== false) el.append(c instanceof Node ? c : String(c));
  return el;
}
async function getJson(url) {
  const r = await gate.fetch(url, { method: "GET", cache: "no-store", redirect: "error", headers: { accept: "application/json" } });
  if (r.status !== 200) throw new Error(`answered ${r.status}`);
  const body = await readBodyCapped(r, MAX_API_BYTES, "too_large");
  if (!body.ok) throw new Error("answer too large");
  return JSON.parse(new TextDecoder().decode(body.bytes));
}
const MAX_PAGES = 200;
export const state = { raws: new Map(), times: new Map(), licences: new Map(), done: false, error: "" };
// The licence allowlist first (Terms v1): only listed runs, by full run id, get downloads; an unreadable list is empty.
async function readLicences() {
  try { state.licences = P.readLicences(await getJson(P.LICENSED_PATH)); } catch { state.licences = new Map(); }
}

// Every page of the results feed, from the start, until has_more is false.
async function readAll() {
  let after = 0;
  for (let page = 0; page < MAX_PAGES; page += 1) {
    const doc = await getJson(`${P.RESULTS_PATH}?after=${after}`);
    if (doc?.schema !== "sentilab-door-results/1" || !Array.isArray(doc.items)) throw new Error("not a results page");
    P.keepRawResults(state.raws, doc, Infinity);
    render();
    if (!doc.has_more || !(doc.next_after > after)) return;
    after = doc.next_after;
  }
}
// The run's own first record (its queued record, seq = the results row's arrival), for its submission time.
async function readTimes() {
  for (const raw of listed()) {
    if (state.times.has(raw.id) || !Number.isSafeInteger(raw.arrival) || raw.arrival < 1) continue;
    try {
      const doc = await getJson(`/api/open/v1/door/events?after=${raw.arrival - 1}&limit=1`);
      const e = Array.isArray(doc?.events) ? doc.events[0] : null;
      state.times.set(raw.id, e && e.seq === raw.arrival && e.kind === "run" && e.run_id === raw.id && typeof e.at === "string" ? e.at : null);
    } catch { state.times.set(raw.id, null); }
    render();
  }
}
const listed = () => P.topLayouts([...state.raws.values()], Infinity);

function download(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = h("a", { href: url, download: name, hidden: true });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
const meta = () => ({ pageUrl: location.href ?? null, generatedAt: new Date().toISOString() });
export const packageOf = (raw, m = meta()) => P.engineerPackage(raw, { licence: state.licences.get(raw.id), submittedAt: state.times.get(raw.id) ?? null, ...m });
const licensed = () => listed().filter((raw) => P.downloadable(raw, state.licences));
function downloadAllJson() {
  const m = meta();
  const list = licensed();
  if (!list.length) return;
  download("sentilab-packages.json", `${JSON.stringify({ schema: "sentilab-engineer-packages/1", readme: W.PACKAGES_PAGE.allReadme,
    source: { page: m.pageUrl, feed: P.RESULTS_PATH, generated_at: m.generatedAt }, packages: list.map((raw) => packageOf(raw, m)) }, null, 2)}\n`, "application/json");
}
function downloadAllCsv() {
  if (!licensed().length) return;
  download("sentilab-packages.csv", P.topBundle([...state.raws.values()], { licences: state.licences, n: Infinity, ...meta() }).csv, "text/csv");
}

function render() {
  const list = listed();
  const box = $("packageList");
  box.replaceChildren(...list.map((raw, i) => {
    const at = state.times.get(raw.id);
    let button = null;
    if (P.downloadable(raw, state.licences)) {
      button = h("button", { type: "button", title: W.PACKAGE.title }, W.PACKAGES_PAGE.download);
      button.addEventListener("click", () => download(P.packageName(raw), `${JSON.stringify(packageOf(raw), null, 2)}
`, "application/json"));
    }
    return h("li", { class: "pkg", "data-run": raw.id },
      h("span", { class: "rank" }, String(i + 1)),
      h("span", null,
        h("span", { class: "visit" }, W.PACKAGES_PAGE.visit(raw.short_id)),
        h("span", { class: "facts" }, W.PACKAGES_PAGE.facts(raw.result.max_chiplet_centre_cell_mean_C, raw.wire_proxy_mm)),
        h("span", { class: "facts" }, h("span", { class: "ok" }, W.PACKAGES_PAGE.outcome),
          P.downloadable(raw, state.licences) ? ` · ${W.PACKAGES_PAGE.licence(state.licences.get(raw.id).licence)}` : null),
        P.downloadable(raw, state.licences) ? null : h("span", { class: "view-only" }, W.PACKAGE.viewOnly),
        h("span", { class: "when" }, at ? W.PACKAGES_PAGE.submitted(W.localTime(Date.parse(at))) : at === null ? W.PACKAGES_PAGE.noTime : W.PACKAGES_PAGE.timeLoading)),
      button);
  }));
  $("pageLead").textContent = W.PACKAGES_PAGE.lead(list.length);
  $("feedState").textContent = state.error ? W.PACKAGES_PAGE.failed(state.error) : state.done ? W.PACKAGES_PAGE.done(list.length) : W.PACKAGES_PAGE.reading;
  const any = licensed().length > 0;
  $("allJson").disabled = !state.done || !any;
  $("allCsv").disabled = !state.done || !any;
}

$("allJson").addEventListener("click", downloadAllJson);
$("allCsv").addEventListener("click", downloadAllCsv);
export const ready = (async () => {
  render();
  await readLicences();
  try { await readAll(); state.done = true; } catch (e) { state.error = e instanceof Error ? e.message : String(e); }
  render();
  await readTimes();
})();
