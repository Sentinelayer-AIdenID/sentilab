// SentiLab Live Lab: the words a visitor reads, in one place. Codes from the door's feeds (visitor classes, record
// kinds) never reach the page as text: they go through these tables, and times are shown as people read them
// ("just now", "14 min ago", or a local time with its zone), never as UTC stamps. Rewording the page is a change to
// this file only. Two phrases are fixed by the honesty rules and must stay as they are: "unvalidated" (the shared
// temperature label) and "self-declared, not verified".

// A visitor's type, from the door's classification of it. A classification, not an identity.
export const VISITOR_TYPE = Object.freeze({
  verified_agent: "AI agent · identity verified",
  signed_agent: "AI agent · signed, not verified",
  declared_agent: "automated visitor · says what it is",
  crawler_claimed: "automated visitor · says it is a crawler",
  automation: "script or bot",
  likely_human: "probably a person",
  unknown: "not identified",
  ours: "our own agent",
});
export const visitorType = (cls) => VISITOR_TYPE[cls] ?? VISITOR_TYPE.unknown;
// The same, as the subject of a sentence: "An AI agent (says so itself) arrived".
export const VISITOR_SUBJECT = Object.freeze({
  verified_agent: "An AI agent (identity verified)",
  signed_agent: "An AI agent (signed, not verified)",
  declared_agent: "An automated visitor that says what it is",
  crawler_claimed: "An automated visitor that says it is a crawler",
  automation: "A script or bot",
  likely_human: "Probably a person",
  unknown: "A visitor (not identified)",
  ours: "Our own agent",
});
export const visitorSubject = (cls) => VISITOR_SUBJECT[cls] ?? VISITOR_SUBJECT.unknown;

// Times. Under an hour: relative ("just now", "2 min ago"). Older: the reader's local time with its zone, through Intl
// ("1:08 PM EST"); on another day, with the date. Never a UTC stamp.
const MINUTE = 60000, HOUR = 3600000;
export function ago(ms, nowMs = Date.now()) {
  const d = nowMs - ms;
  if (!Number.isFinite(d)) return "time not recorded";
  if (d < 45000) return "just now";
  if (d < HOUR) return `${Math.max(1, Math.round(d / MINUTE))} min ago`;
  return localTime(ms, nowMs);
}
export function localTime(ms, nowMs = Date.now()) {
  if (!Number.isFinite(ms)) return "time not recorded";
  const sameDay = new Date(ms).toDateString() === new Date(nowMs).toDateString();
  const opts = sameDay ? { hour: "numeric", minute: "2-digit", timeZoneName: "short" }
    : { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short" };
  return new Intl.DateTimeFormat(undefined, opts).format(new Date(ms));
}
// A server timestamp (ISO 8601) or null -> the reader's words.
export const when = (iso, nowMs = Date.now()) => (iso ? ago(Date.parse(iso), nowMs) : "time not recorded");

// The arrival card: one plain sentence per arrival. Today's feeds carry only the visitor class, so the words never
// claim more than it states (a declared class is "an automated visitor that says what it is": it may be an assistant
// or a crawler). When an arrival carries the registry's operatorName, service name and verification level (a feed
// field, validated by the door), the card adds them, in the registry's own verification terms; a claim is never
// called verified.
export const VERIFICATION = Object.freeze({
  signature: "signature verified", network: "network verified", claimed: "says it is", inferred: "inferred", unverified: "unverified",
});
// The registry's categories (AIdenID public registry, its category ids), in words: used only when an arrival carries
// its category (a feed field the door validates); never derived from the visitor class.
export const CATEGORY = Object.freeze({
  training_crawler: "A training crawler", search_crawler: "A search crawler", ai_assistant: "An AI assistant", ai_agent: "An AI agent",
  preview_bot: "A link preview bot", monitor: "A monitoring tool", automation: "A script or automation", unknown: "A visitor (not identified)",
  human: "Probably a person",
});
export const PURPOSE = Object.freeze({ "place-chiplets": "here to place chiplets", review: "here to review", read: "here to read" });
export function arrivalSentence(a, nowMs = Date.now()) {
  const subject = a.category && CATEGORY[a.category] ? CATEGORY[a.category] : visitorSubject(a.cls);
  const who = a.operatorName ? `${subject}, from ${a.operatorName}${a.serviceName ? ` (${a.serviceName})` : ""},` : subject;
  const did = a.declaration ? "sent a declaration" : "arrived";
  const why = a.purpose && PURPOSE[a.purpose] ? ` · ${PURPOSE[a.purpose]}` : "";
  return `${who} ${did}${why} · ${when(a.at, nowMs)}`;
}
export function arrivalDetail(a) {
  const parts = [];
  if (a.verification && VERIFICATION[a.verification]) parts.push(VERIFICATION[a.verification]);
  else parts.push(visitorType(a.cls));
  if (a.short) parts.push(`visit ${a.short}`);
  return parts.join(" · ");
}
export const ARRIVALS_HEAD = "VISITORS AND THEIR LATEST RECORDED ACTIVITY";

// Temperatures: each number carries the plain word "simulated" (a withdrawn evaluator keeps its own word); one line
// near the top of the work area says what that means. The full label stays in each number's tooltip.
// The board's one statistic, by its name (the inspector explains the 1, 2 or 4 central cells).
export const METRIC_NAME = "Highest chiplet-centre average";
export const TEMP_LINE = "Every temperature here comes from a published heat model. It is simulated, not measured on real chips.";
// With the run's own check, in plain bounded words (root, 18:18Z): a reproduced result says the replay matched. The
// page does not check the result's signed proof itself, so it never says more than that.
export function tempWord(t, verification = null) {
  if (t?.state === "withdrawn") return t.qualifier;
  if (verification?.replay === "reproduced") return "replay matched · simulated";
  if (verification?.replay === "not_reproduced") return "replay did not match · simulated";
  return "simulated";
}
export const YOUR_PICK = "your pick";

// A design's steps in plain words, for the newest-event line and the model's caption.
export const RUN_STATE = Object.freeze({
  queued: "is waiting in line", held: "is on hold", evaluating: "is being simulated", evaluated: "was simulated",
  replaying: "is being checked again", reproduced: "was checked again by a fresh run", not_reproduced: "did not repeat when checked again",
  cross_checked: "was cross-checked", rejected: "was rejected", failed: "could not be simulated", cancelled: "was cancelled",
  expired: "expired before it ran",
});
export const RESULT_CHECK = Object.freeze({
  reproduced: "checked again by a fresh run", not_reproduced: "did not repeat when checked again", cross_checked: "cross-checked",
  evaluated: "simulated once, not yet checked again", replaying: "being checked again",
});
export const layoutFrom = (short) => (short ? `The layout from visit ${short}` : "A layout");

// The rest of the page's words that used to be codes or engineer shorthand.
export const TEXT = Object.freeze({
  submittedEarlier: "submitted earlier",
  submitted: (t) => `submitted ${t}`,
  recentVisitors: "Recent visitors",
  visits: (n) => `${n} visit${n === 1 ? "" : "s"}`,
  attempts: (n) => `${n} refused attempt${n === 1 ? "" : "s"}`,
  noTask: (n) => `${n} arrival${n === 1 ? "" : "s"} without a purpose pass`,
  lastSeen: (t) => `last seen ${t}`,
  arrived: "arrived",
  declared: "sent a declaration",
  mapLegend: "Each figure is a design, at the last step it reached",
  outOfFlow: (n) => `${n} stopped early (rejected, failed, cancelled or expired)`,
  computeLeft: (leftMin, capMin) => `about ${leftMin} of ${capMin} min`,
  simulatorUp: (t) => `running since ${t}`,
  queue: (waiting, running) => `${waiting} waiting · ${running} running`,
  feedLive: (designs, events) => `LIVE · ${designs} DESIGNS · ${events} RECENT EVENTS`,
  feedEmpty: "LIVE · NOTHING YET",
  feedStale: (s) => `NOT UPDATING · LAST UPDATE ${s} S AGO`,
  newest: "NEWEST EVENT",
  replayStep: (i, n) => `REPLAY · STEP ${i} OF ${n}`,
  traceOldest: (t) => `OLDEST SHOWN · ${t}`,
  traceNewest: (t) => `NEWEST · ${t}`,
  timecodeLive: (t) => `LIVE · newest ${t}`,
  timecodeReplay: (i, n, t) => `step ${i} of ${n} · ${t}`,
  frameNote: "45 mm square base · 8 chips placed by this design",
  atStep: (t) => `at this step · ${t} · no temperature at this step`,
  declarationsHead: (n) => `DECLARATIONS AMONG THE LATEST ${n} DOOR EVENTS · NEWEST FIRST`,
  declarationsNone: () => "No published names in the recent records",
});
