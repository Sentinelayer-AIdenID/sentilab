// Links between the Lab view and the Package view that keep the viewer's context. Shared by lab.js and
// package/package.js. Carried: the source (?src=live), the run (?run=, for a live run or a named bundle), a named
// replay bundle (?bundle=), the test-key request (?pins=test; each page applies its own local-host rule to it, so
// carrying it never widens trust) and, for a replay, the playhead (?seq=). Nothing else crosses over.
const RUN_ID = /^[A-Za-z0-9._:-]{1,128}$/;
const BUNDLE = /^[A-Za-z0-9._-]{1,128}$/;

// target: the other page's path ("package/" from the Lab view, "../" from the Package view).
// state: { source: "api" | "file", runId, seq, search } where search is the current location.search.
export function viewHref(target, { source, runId = null, seq = null, search = "" } = {}) {
  const from = new URLSearchParams(search);
  const out = new URLSearchParams();
  if (source === "api") out.set("src", "live");
  const bundle = from.get("bundle");
  if (bundle && BUNDLE.test(bundle)) out.set("bundle", bundle);
  if (typeof runId === "string" && RUN_ID.test(runId) && (source === "api" || out.has("bundle"))) out.set("run", runId);
  if (from.get("pins") === "test") out.set("pins", "test");
  if (source !== "api" && Number.isSafeInteger(seq) && seq >= 0) out.set("seq", String(seq));
  const query = out.toString();
  return query ? `${target}?${query}` : target;
}
