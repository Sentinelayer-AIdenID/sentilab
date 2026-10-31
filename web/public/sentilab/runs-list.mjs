// GET /api/view/runs, the one discovery path for both views: the Lab view's poller (lab-live.mjs) and the Package
// view's (package/source.mjs). Any failure is a failed poll, as for a failed events page: refreshRuns() applies the
// shared failed-poll transition (paging.mjs step() with no response: failure "transport"; the rows, the cursor and the
// cursor hash kept) and hands the new paging state back, so the caller stores it BEFORE its page is told and the
// label reads "STALE · transport" at once, never a LIVE left over from the last good poll.
import { readBodyCapped } from "./view-core.mjs";
import { step } from "./paging.mjs";
import { isObj } from "./lab-model.mjs";

export const MAX_SMALL_JSON = 256 * 1024;   // /api/view/runs and /api/view/key are small; a bigger answer is refused
export const strictJson = (bytes) => JSON.parse(new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(bytes));

// The runs list, or a throw for each way discovery can fail: a network failure (fetch throws), a non-200 answer, a
// body over 256 KiB, bytes that aren't strict UTF-8 JSON, and JSON that isn't a runs list (an array of runs, or
// { runs: [...] }). Entries without a string run_id of at most 128 characters are skipped; at most 200 are kept.
export async function fetchRunsList(fetchImpl) {
  const r = await fetchImpl("/api/view/runs", { cache: "no-store" });
  if (!r.ok) throw new Error(`/api/view/runs answered ${r.status}`);
  const body = await readBodyCapped(r, MAX_SMALL_JSON, "too_large");
  if (!body.ok) throw new Error("/api/view/runs answered with more than 256 KiB");
  let doc;
  try { doc = strictJson(body.bytes); } catch { throw new Error("/api/view/runs answered with bytes that aren't JSON"); }
  const list = Array.isArray(doc) ? doc : isObj(doc) && Array.isArray(doc.runs) ? doc.runs : null;
  if (list === null) throw new Error("/api/view/runs answered JSON that isn't a runs list");
  return list.filter((x) => isObj(x) && typeof x.run_id === "string" && x.run_id.length <= 128).slice(0, 200);
}

// One discovery poll. { ok: true, runs } or { ok: false, error, paging }: on failure, `paging` is the state after the
// shared failed-poll transition (null stays null: no run yet). now() is read after the request settles.
export async function refreshRuns(fetchImpl, paging, now) {
  try {
    return { ok: true, runs: await fetchRunsList(fetchImpl) };
  } catch (error) {
    return { ok: false, error: String(error?.message ?? error), paging: paging ? (await step(paging, null, now())).state : paging };
  }
}
