// Offline record verifier (verify.html). A file, not an inline <script>: the page's Content-Security-Policy
// (script-src 'self') runs only this site's own script files. Markup built here carries no style="" attributes.
import { verifyDocument } from "./verify-core.js";
// The page notice comes from the one rule (temperature-label.mjs), over the identity of every temperature each shown
// best peak was taken from, as the verifier reports it: any withdrawn or unvalidated one (or none named) shows it.
import { reportNeedsNotice, NOTICE } from "./temperature-label.mjs";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" })[c]);
const short = (h) => (h ? `${h.slice(0, 12)}…${h.slice(-6)}` : "—");
const setNotice = (on) => { $("wnotice").hidden = !on; $("wnotice").textContent = on ? NOTICE : ""; };

function render(report, source) {
  const badge = (ok, yes, no) => `<span class="badge ${ok ? "ok" : "bad"}">${ok ? "✓" : "✗"} ${ok ? yes : no}</span>`;
  const laneProblem = [report.missing.length ? `missing ${report.missing.join(", ")}` : "",
    report.extra.length ? `unexpected ${report.extra.join(", ")}` : ""].filter(Boolean).join("; ");
  if (report.kind === "lane") {
    const l = report.lanes[0];
    $("summary").innerHTML = `<span>lane <strong>${esc(l.laneId)}</strong> (signed) · run label <strong>${esc(report.runId || "—")}</strong> ${report.runIdUnsigned ? "(unsigned)" : "(certified)"}</span>`
      + badge(report.allValid, "AUTHENTIC RECORD", "origin NOT authenticated")
      + `<span class="badge">scientific validity: not checked</span>`
      + (l.ok ? `<span class="badge">${esc(l.evaluations)} signed evaluations</span>` : "")
      + `<span class="dim">single lane: the four-lane, equal-budget and shared-pool checks need the whole run · source: ${esc(source)}</span>`;
    $("results").innerHTML = laneTable(report.lanes);
    return;
  }
  $("summary").innerHTML = `<span>run <strong>${esc(report.runId || "—")}</strong></span>`
    + badge(report.allValid, "AUTHENTIC RUN", "run NOT authenticated")
    + badge(report.laneSet, "all four lanes present", esc(laneProblem || "lane set wrong"))
    + badge(report.recordsValid, "record integrity passes", "record integrity fails")
    + badge(report.authentic, "authentic service origin", "origin NOT authenticated")
    + `<span class="badge">scientific validity: not checked</span>`
    + badge(report.equalCounts, "equal signed evaluation counts", "evaluation counts differ")
    + badge(report.samePool, "same signed starting pool", "starting pools differ")
    + (report.countsMatchClaims ? "" : badge(false, "", "summary counts disagree with the records"))
    + (report.bestMatchesClaims ? "" : badge(false, "", "summary best temperatures disagree with the records"))
    + (report.runIdMatchesDoc ? "" : badge(false, "", "the response id is not the run id the lanes were signed for"))
    + `<span class="dim">source: ${esc(source)}</span>`;
  $("results").innerHTML = laneTable(report.lanes);
}

function laneTable(lanes) {
  const rows = lanes.map((l) => `<tr>
      <td>${l.integrity ? '<span class="ok">✓ integrity</span>' : '<span class="bad">✗ integrity</span>'}<br>${l.authentic ? '<span class="ok">✓ authentic origin</span>' : l.origin === "unanchored" ? 'integrity only, unanchored' : '<span class="bad">✗ origin not authenticated</span>'}</td>
      <td>${esc(l.laneId)}<br><span class="k">${esc(l.agentId)}</span></td>
      <td>${esc(l.checked)} events</td>
      <td>${Number.isFinite(l.best) ? l.best.toFixed(4) + " °C" : "—"}<br><span class="k">${esc(l.evaluations)} evaluations</span></td>
      <td><span class="k">key</span> ${esc(short(l.publicKey))}<br><span class="k">final</span> ${esc(short(l.finalHash))}</td>
      <td>${esc(l.reason || l.originReason)}${!l.ok && l.claimedValid === true ? '<br><span class="k">(the file claims record_valid=true; this check disagrees)</span>' : ""}</td>
    </tr>`).join("");
  return `<table><thead><tr><th>Verdict</th><th>Lane</th><th>Checked</th><th>Best peak</th><th>Signing key · final hash</th><th>First failure</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function fail(message) {
  setNotice(false);
  $("summary").innerHTML = `<span class="badge bad">✗ ${esc(message)}</span>`;
  $("results").innerHTML = "";
}

async function verifyText(text, source) {
  try {
    const report = await verifyDocument(text);
    render(report, source);
    setNotice(reportNeedsNotice(report));
  } catch (e) { fail(e.message || String(e)); }
}

async function fetchRun(id) {
  const clean = String(id || "").trim();
  if (!/^[A-Za-z0-9_-]{1,80}$/.test(clean)) return fail("run id should be letters, digits, - or _");
  $("summary").innerHTML = `<span class="dim">fetching ${esc(clean)}…</span>`;
  try {
    const res = await fetch(`/api/runs/${encodeURIComponent(clean)}`, { headers: { accept: "application/json" } });
    if (!res.ok) return fail(`server answered ${res.status} for that run`);
    await verifyText(await res.text(), `/api/runs/${clean}`);
  } catch (e) { fail(`could not fetch: ${e.message || e}`); }
}

$("load").addEventListener("click", () => fetchRun($("run-id").value));
$("run-id").addEventListener("keydown", (e) => { if (e.key === "Enter") fetchRun($("run-id").value); });
$("file").addEventListener("change", async (e) => { const f = e.target.files[0]; if (f) verifyText(await f.text(), f.name); });
const drop = $("drop");
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", async (e) => { e.preventDefault(); drop.classList.remove("over"); const f = e.dataTransfer.files[0]; if (f) verifyText(await f.text(), f.name); });
const param = new URLSearchParams(location.search).get("run");
if (param) { $("run-id").value = param; fetchRun(param); }
