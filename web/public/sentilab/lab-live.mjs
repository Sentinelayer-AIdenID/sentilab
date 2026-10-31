// The Lab view's live poller, one poll at a time (VIEW ENVELOPE v0.6.2 rules 4 and 5). No DOM: fetch and the clock
// are injected, so the node tests drive this exact code; lab.js passes fetch and Date.now and renders after each poll.
//   1. GET /api/view/runs when the list is missing or older than 15 s, through runs-list.mjs refreshRuns(), the path
//      the Package view's poller uses too. A failed refresh (a 503 or any non-200, a network throw, a malformed or
//      non-schema 200) is a failed poll: the shared transition (paging.mjs step() with no response: failure
//      "transport"; rows, cursor and cursor hash kept) is stored before the caller is told, so the label leaves LIVE
//      at once and shows the transport reason.
//   2. GET /api/view/events?run_id=&cursor=<n>&limit=256[&cursor_hash=], draining while x-has-more is true (at most 16
//      pages a poll). paging.mjs step() applies each page: the caps before anything is split, then the cursor and the
//      cursor hash over the raw bytes. A failed page keeps nothing. "stream replaced" (409), "row too large" (413) and
//      "paging unsupported" (400, 404, 501) are terminal. The view never pages by seq.
//   3. track() with the K the drain gives: pages read while catching up raise the high but are never progress.
import { readBodyCapped, MAX_API_BYTES } from "./view-core.mjs";
import { initialState, request as pageRequest, step as pageStep, track } from "./paging.mjs";
import { refreshRuns } from "./runs-list.mjs";

export const POLL_OK_MS = 1000, POLL_BACKOFF_MS = 5000;
export const RUNS_REFRESH_MS = 15000;             // /api/view/runs is asked again after this long
export const MAX_PAGES_PER_POLL = 16;             // as the reference client loop

export async function fetchPage(fetchImpl, runId, req) {
  const query = new URLSearchParams({ run_id: runId, cursor: String(req.cursor), limit: String(req.limit) });
  if (req.cursor_hash !== undefined) query.set("cursor_hash", req.cursor_hash);
  let r;
  try { r = await fetchImpl(`/api/view/events?${query}`, { cache: "no-store" }); } catch { return null; }   // transport
  if (r.status !== 200) { r.body?.cancel().catch(() => {}); return { status: r.status, headers: r.headers, bodyBytes: new Uint8Array(0) }; }
  // Raw bytes, never decoded whole; reading stops past 4 MiB, and a body that isn't read whole fails as transport.
  const body = await readBodyCapped(r, MAX_API_BYTES, "response_too_large").catch(() => ({ ok: false }));
  return { status: 200, headers: r.headers, bodyBytes: body.ok ? body.bytes : null };
}

// One poll of the live state L: { runs, runsAt, runId, paging, verification, connected, error }.
//   fetchImpl, now   fetch and the clock (ms);
//   current()        false once L is no longer the page's live state (the run was switched): the poll is dropped;
//   verify(L)        re-verify every row held; sets L.verification (with prefix_end), called only when rows arrived;
//   onRuns()         the runs list was refreshed.
// Returns null when the poll was dropped, else { delay }: ms until the next poll, or null when stopped for good.
export async function pollLiveOnce(L, { fetchImpl, now, current = () => true, verify, onRuns = () => {} }) {
  if (L.paging.degraded) return { delay: null };   // stopped for good; a reload starts over
  if (!L.runs || !L.runId || now() - (L.runsAt ?? 0) > RUNS_REFRESH_MS) {
    const got = await refreshRuns(fetchImpl, L.paging, now);
    if (!current()) return null;
    if (!got.ok) {
      // The failed-poll transition, stored before the page is told: the label reads "STALE · transport" from now on,
      // with the rows, the cursor and the cursor hash kept, until a poll succeeds.
      L.paging = got.paging;
      L.connected = false;
      L.error = got.error;
      return { delay: POLL_BACKOFF_MS };   // calm back-off; one request every 5 s, nothing written to the console
    }
    L.runs = got.runs;
    L.runsAt = now();
    L.connected = true;
    if (!L.runId && L.runs.length) { L.runId = L.runs[0].run_id; L.paging = initialState(L.runId); }
    onRuns();
    if (!L.runId) return { delay: POLL_BACKOFF_MS };
  }
  // Drain: keep fetching while x-has-more is true (at most 16 pages a poll), then poll every 1 s from the last cursor.
  let outcome = "ok", added = 0, anyOk = false;
  for (let pages = 0; pages < MAX_PAGES_PER_POLL; pages += 1) {
    const req = pageRequest(L.paging);
    if (req === null) break;     // terminal: request() sends nothing more
    const response = await fetchPage(fetchImpl, L.runId, req);
    if (!current()) return null;
    const result = await pageStep(L.paging, response, now());
    if (!current()) return null;
    L.paging = result.state;
    outcome = result.outcome;
    anyOk ||= outcome === "ok";
    added += result.newRows.length;
    if (outcome !== "ok" || !L.paging.has_more) break;
  }
  L.connected = true;
  L.error = "";
  if (added) {
    await verify(L);              // the whole stream, every time new rows arrive
    if (!current()) return null;
  }
  // Progress (rule 5, v0.6.2): after valid pages, track() with the K they give. Pages up to and including the first
  // with no more to fetch are history (catch-up): they raise the high-water mark but are never progress, so a page
  // load of a long log never shows LIVE. The whole drain is verified once; the outcome is the reference's, whose
  // pages within one drain are all catch-up or all after it.
  if (anyOk) L.paging = track(L.paging, L.verification ? L.verification.prefix_end : 0, now());
  return { delay: L.paging.degraded ? null : outcome !== "ok" ? POLL_BACKOFF_MS : L.paging.has_more ? 0 : POLL_OK_MS };
}
