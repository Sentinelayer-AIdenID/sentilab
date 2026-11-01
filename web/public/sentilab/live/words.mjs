// SentiLab Live Lab: the words a visitor reads, in one place. Codes from the door's feeds (visitor classes, record
// kinds) never reach the page as text: they go through these tables, and times are shown as people read them
// ("just now", "14 min ago", or a local time with its zone), never as UTC stamps. Rewording the page is a change to
// this file only. Two phrases are fixed by the honesty rules and must stay as they are: "unvalidated" (the shared
// temperature label) and "self-declared, not verified".

// A visitor's type, from the door's classification of it. A classification, not an identity.
export const VISITOR_TYPE = Object.freeze({
  verified_agent: "Verified agent · signed",
  signed_agent: "Agent · signed, not verified",
  declared_agent: "Automated visitor · declared",
  crawler_claimed: "Crawler · claimed",
  automation: "Automation · bot",
  likely_human: "Likely human",
  unknown: "Unresolved",
  ours: "Our own agent",
});
export const visitorType = (cls) => VISITOR_TYPE[cls] ?? VISITOR_TYPE.unknown;
// The same, as the subject of a sentence: "A likely human arrived".
export const VISITOR_SUBJECT = Object.freeze({
  verified_agent: "A verified agent (signed)",
  signed_agent: "An agent (signed, not verified)",
  declared_agent: "An automated visitor (declared)",
  crawler_claimed: "A crawler (claimed)",
  automation: "An automation bot",
  likely_human: "A likely human",
  unknown: "An unresolved visitor",
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
// A declared name is shown only with this note, and never as proof: the visitor said it; nothing checked it.
export const SELF_DECLARED = "self-declared, not verified";
// The lab, only when the door recognised one (its registry), with how it knows.
export function labWords(a) {
  if (!a?.operatorName) return "";
  const how = a.verification === "signature" || a.verification === "network" || a.verification === "inferred" ? VERIFICATION[a.verification] : "its user agent says";
  return ` \u00b7 ${a.operatorName} (${how})`;
}
// What follows a declared name: the note, the visit id and the lab.
export const namedTail = (a) => ` \u00b7 ${SELF_DECLARED}${a?.short ? ` \u00b7 visit ${a.short}` : ""}${labWords(a)}`;
export const namedLayout = (L) => `'s layout \u00b7 ${SELF_DECLARED}${L?.short ? ` \u00b7 visit ${L.short}` : ""}`;
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
// A run's step, in the words its outcome line uses (live-model.mjs runOutcome), as its avatar passes it.
export const STEP_WORD = Object.freeze({ queued: "Waiting in line", held: "Held", evaluating: "Simulating", evaluated: "Re-checking (replay)",
  replaying: "Re-checking (replay)", reproduced: "Accepted \u00b7 replay matched", cross_checked: "Accepted \u00b7 cross-checked",
  not_reproduced: "Scored \u00b7 replay did not match", arrival: "At the door", submitted: "Submission accepted" });
// A visitor at the Door station: its declared name (exact declaration.arrival only) with the note, or its visit id.
export const doorLabel = (short) => (short ? `visit ${short}` : "a visitor");
// The proposals timeline (Carter, 19:59Z): one row per run, newest at top.
export const PROPOSALS = Object.freeze({
  head: "PROPOSALS \u00b7 NEWEST FIRST",
  from: (short) => (short ? `Proposal from visit ${short}` : "Proposal"),
  named: (short) => ` \u00b7 self-declared, not verified${short ? ` \u00b7 visit ${short}` : ""}`,
  received: "Submission accepted",
  receivedTitle: "The door’s intake accepted this submission (it has a queued record)",
  refused: "Refused at intake",
  fresh: "New proposal",
  none: "No proposals yet. The first one appears here as it arrives.",
});
// The selected proposal's linked records (Carter, 20:13Z): the newest record on its exact links (visit, declarations,
// linked runs). That is not presence: the scorer writes a run's records after the agent may have gone and there is
// no heartbeat, so the words never say the agent is here or gone (review, 20:37Z).
export const PRESENCE = Object.freeze({
  here: (t) => `Recent linked activity \u00b7 last record ${t}`,
  gone: (t) => `No recent linked activity \u00b7 last record ${t}`,
  runOnly: (t) => `This run\u2019s last record: ${t}`,
  title: "Linked visit/run events; not proof the agent remains connected",
});
// Packages for engineers (Carter, 22:08Z): a layout and the door's own result for it, copied from the public results
// feed, downloaded from the page. Nothing here adds a claim the feed does not make.
export const PACKAGE = Object.freeze({
  button: "Package for engineers",
  title: "Download this layout and the door\u2019s result for it as JSON. Simulated, not silicon.",
  top: "Download top layouts",
  topTitle: "Download the accepted layouts whose replay matched, lowest board metric first, as JSON and CSV. Simulated, not silicon.",
  // Terms v1 (the terms review, 22:16Z): the door\u2019s terms grant evaluation, keeping the evidence and public display,
  // not redistribution. A package exists only for a run on the licence allowlist; its readme carries that licence.
  readme: (licence) => [
    "SentiLab engineer package: one layout proposed through the SentiLab agent door, with the door\u2019s own result for it, copied as the public results feed gives it.",
    "The number: result.max_chiplet_centre_cell_mean_C is the highest chiplet-centre average. For each chiplet, the mean of its central cells on a 64 x 64 grid, then the highest over the chiplets, computed by HotSpot 6.0 at grid 64 (result.metric.definition). It is simulated, not measured, and comes with no warranty.",
    "Known limit: the saved heat balance is off by +1.39% on this CPU-DRAM case, and HotSpot 7.0 reads very differently on the same inputs.",
    "The wire figure: wire_proxy_mm is a proxy computed from chip-to-chip distances, not routed wire.",
    "What it is not: not a manufacturing design, not an optimum, and not checked on hardware. verification.not_claimed lists what the feed itself does not claim.",
    "Next steps for an engineer: route it, and run your own thermal model.",
    "The fields: layout.dies is the layout as the feed gives it (die, x_um, y_um, rot_deg); layout.compact is the same layout as the door\u2019s compact l= string (x.y.r per die, x and y in 500 um steps, r in 90 degree steps), or null off that lattice; case gives the interposer and die sizes; result.per_die_C, result.active_layer_peak_C with result.active_guard, and result.replay are copied from the feed; labels keeps the feed\u2019s own labels as given.",
    `Licence: ${licence?.licence ?? "none"}${licence?.owner_role ? ` (granted by its ${licence.owner_role} owner)` : ""}.`,
  ].join("\n\n"),
  viewOnly: "View only: shown under the door\u2019s terms, not licensed for redistribution",
  topReadme: "SentiLab top layouts: only layouts whose owners licensed them for redistribution (each row carries its "
    + "licence), accepted with a matching fresh-process replay, sorted by the highest chiplet-centre average (lower first) "
    + "with wire_proxy_mm alongside. The reference value is for comparison only. "
    + "Scientific limits: every temperature is diagnostic, from HotSpot 6.0 at grid 64; for the saved reference case the "
    + "simulator’s heat balance is off by about +1.39%, with no established cause in the deployed build, and HotSpot 7.0 "
    + "reads very differently on the same inputs; these temperatures are withdrawn from comparison with published layouts. "
    + "Every temperature is simulated "
    + "(HotSpot 6.0, grid 64), not measured, with no warranty; wire_proxy_mm is a proxy from chip distances, not routed "
    + "wire; none of these is a manufacturing design, an optimum, or checked on hardware.",
  referenceRow: "reference (for comparison only)",
});
// The Packages page (/sentilab/packages/): every accepted layout whose replay matched, coolest first.
export const PACKAGES_PAGE = Object.freeze({
  lead: (n) => (n ? `${n} accepted layout${n === 1 ? "" : "s"} whose fresh-process replay matched, coolest first, as the door’s public results feed gives them.` : "No accepted layout whose replay matched yet."),
  reading: "Reading every page of the door’s results…",
  done: (n) => `Every page read · ${n} listed`,
  failed: (e) => `The door’s results could not all be read (${e}). The list may be incomplete, and the bulk downloads stay off.`,
  visit: (short) => (short ? `visit ${short}` : "a visit"),
  facts: (value, wire) => `highest chiplet-centre average ${Number.isFinite(value) ? value.toFixed(2) : "?"} °C · simulated · wire proxy ${Number.isFinite(wire) ? wire : "?"} mm`,
  outcome: "replay matched",
  submitted: (t) => `submitted ${t}`,
  timeLoading: "submission time: reading…",
  noTime: "submission time not recorded",
  download: "Download package",
  licence: (l) => `licensed ${l}`,
  allReadme: "SentiLab packages: only layouts whose owners licensed them for redistribution (each package carries its "
    + "licence), accepted with a matching fresh-process replay, coolest first, each as the same package the Live Lab "
    + "downloads (see each package’s readme). Layouts shown on the page as view only are not in this file. "
    + "Scientific limits: every temperature is diagnostic, from HotSpot 6.0 at grid 64; for the saved reference case the "
    + "simulator’s heat balance is off by about +1.39%, with no established cause in the deployed build, and HotSpot 7.0 "
    + "reads very differently on the same inputs; these temperatures are withdrawn from comparison with published layouts. "
    + "Every temperature is simulated, not measured on silicon; each package’s verification.not_claimed lists what the "
    + "feed does not claim. This file adds no claim of its own.",
});
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

// The aquarium's populations as tabs (AIdenID live-aquarium POPULATIONS and populationOf): a record's population comes
// from the registry category when a feed carries it, else from the visitor class (a declared visitor is grouped with
// the agents, as the aquarium does, while its own label stays "Automated visitor · declared").
export const POPULATIONS = Object.freeze([
  { id: "all", label: "All" }, { id: "agent", label: "AI agents" }, { id: "crawler", label: "Crawlers" },
  { id: "human", label: "People" }, { id: "bot", label: "Bots" }, { id: "unresolved", label: "Unresolved" },
]);
const BY_CATEGORY = Object.freeze({ training_crawler: "crawler", search_crawler: "crawler", ai_agent: "agent", ai_assistant: "agent", human: "human",
  automation: "bot", monitor: "bot", preview_bot: "bot", unknown: "unresolved" });
const BY_CLASS = Object.freeze({ verified_agent: "agent", signed_agent: "agent", declared_agent: "agent", ours: "agent", crawler_claimed: "crawler",
  likely_human: "human", automation: "bot", unknown: "unresolved" });
export const populationOf = (r) => BY_CATEGORY[r.category] ?? BY_CLASS[r.cls] ?? "unresolved";

// The records list.
export const RECORDS = Object.freeze({
  head: "EVERY DOOR RECORD · NEWEST FIRST",
  more: "Show earlier records",
  loading: "Loading earlier records…",
  done: "That is every record.",
  none: "No records in this tab yet.",
  failed: (e) => `Earlier records could not be loaded (${e}). Try again.`,
  filling: "Reading records that arrived all at once\u2026",
  gapHere: "Some records that arrived all at once are not loaded yet",
  gapFailed: (e) => `Some records that arrived all at once could not be loaded (${e}). Try again.`,
});

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
  mapLegend: "Each figure is a design, at the last step it reached. When several of a run's steps arrive at once, its figure plays them back "
    + "in order, marked Playback; the numbers always show where every run is now",
  playback: (word) => `Playback \u00b7 ${word}`,
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
