// A visitor's opt-in declaration at the purpose step (AGENT-DOOR Amendment 4 rev 2, section 4.1; root's #89 contract,
// docs/sentilab/DOOR-VISITORS.md): {notice_version, name (up to 64 characters), reason (up to 160), source (one of
// SOURCES)}, public display data the visitor chooses to give, shown as written and checked by no one.
//
//   - The notice. The purpose step shows the exact notice.text of GET /api/open/v1/door/visitors before it accepts an
//     opt-in: on the human form, in the wall's markdown and JSON, and in the agent view's declare object.
//   - The opt-in is the visitor sending notice_version, equal to the version of that notice, with the purpose. Only then
//     are name, reason and source read. The door never adds one on a visitor's behalf.
//   - Controls (C0, DEL and C1) and the bidi embeddings, overrides and isolates are refused, as #89 refuses them; the
//     text is otherwise passed on exactly as written (no trimming, no normalising). Lengths count code points.
//   - ?via=<source> on a landing page only pre-fills source: the form's selected option and the declare template. It
//     never records anything; at the opt-in only the visitor's own source field counts.
//   - The door never echoes a declaration. The token page says what the intake did with it, from the intake's own
//     answer to the arrival (door.js deliverArrival): recorded, not recorded, or unconfirmed; never "sent" on a guess.
// A module of its own because worker.js may export nothing but its default handler.

export const SOURCES = Object.freeze(["moltbook", "senti", "github", "direct", "other"]);
export const FIELD_LIMITS = Object.freeze({ name: 64, reason: 160 });
const NOTICE_VERSION = /^sentilab-public-visitor\/[1-9][0-9]{0,5}$/;
const MAX_NOTICE_CHARS = 2000;
const REFUSED = /[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069]/u;

// The one line the wall and the agent view both show about declarations: optional, public, as written, unchecked,
// hideable (the signed terms, aneta #57819).
export const OPT_IN_LINE = "Optional: you can also tell us who you are, why you're here and where you came from. We publish it as you wrote it, we don't check it, and we may hide it.";

// What the token page says about a declaration, by outcome; fixed text, never the visitor's.
export const DECLARATION_TEXT = Object.freeze({
  recorded: "Your declaration was recorded with this visit. It's public, shown as you wrote it, not checked by us, and we may hide it.",
  busy: "Your declaration was not recorded: too many visits from your network just now. Your purpose pass works as usual.",
  refused: "Your declaration was not recorded: the intake refused it. Your purpose pass works as usual.",
  intake_unavailable: "Your declaration was not recorded: the intake can't be reached. Your purpose pass works as usual.",
  unconfirmed: "Your declaration was sent with this visit, but no confirmation came back, so it may or may not appear on the public feed. Your purpose pass works as usual.",
  not_opted_in: "You didn't opt in, so nothing you typed was recorded.",
  notice_unavailable: "Declarations can't be accepted right now: the notice could not be loaded. Nothing you typed was recorded.",
  notice_changed: "The notice has changed since you read it, so nothing you typed was recorded. Read the current notice and try again.",
  field_repeated: "A field was given more than once, so nothing you typed was recorded.",
  too_long: "A field is too long (a name is at most 64 characters, a reason at most 160), so nothing you typed was recorded.",
  control_character: "A field has a control or direction-override character, so nothing you typed was recorded.",
  source_unknown: "Where you came from must be one of moltbook, senti, github, direct or other, so nothing you typed was recorded.",
  reserved_name: "That name is reserved for the lab's own labels, so nothing you typed was recorded. Your purpose pass works as usual.",
});

// Names that would pass for the lab's own interface labels are refused, so no declaration can read as a system, staff
// or participant label. They are compared by nameKey: NFKC, format characters removed, whitespace runs collapsed,
// trimmed, lower-cased. This is defense in depth; a declaration is always shown as "self-described", behind a click.
export const RESERVED_NAMES = Object.freeze(["human", "you", "senti", "participant", "unidentified participant", "system", "owner", "admin",
  "moderator"]);
export function nameKey(name) {
  return name.normalize("NFKC").replace(/\p{Cf}/gu, "").replace(/\s+/gu, " ").trim().toLowerCase();
}

// null when text is acceptable display text of at most max code points; otherwise the reason it is not.
export function displayTextProblem(text, max) {
  if (REFUSED.test(text)) return "control_character";
  return [...text].length > max ? "too_long" : null;
}

// The notice of a GET /visitors answer, {version, text}, or null unless it has exactly the expected shape.
export function noticeFrom(value) {
  const notice = value?.notice;
  if (!notice || typeof notice !== "object" || Array.isArray(notice)) return null;
  const { version, text } = notice;
  if (typeof version !== "string" || !NOTICE_VERSION.test(version)) return null;
  if (typeof text !== "string" || text.length === 0 || text.length > MAX_NOTICE_CHARS || REFUSED.test(text)) return null;
  return { version, text };
}

// The source a landing link's ?via= pre-fills: exactly one via, exactly one of SOURCES; otherwise null.
export function viaSource(params) {
  const values = params.getAll("via");
  return values.length === 1 && SOURCES.includes(values[0]) ? values[0] : null;
}

// The purpose step's opt-in: { status: "not_given", typed } (no notice_version: nothing is read, typed says whether a
// name or reason was typed anyway), { status: "opted_in", declaration }, or { status: "not_sent", code } (refused here,
// so nothing is sent).
export function readOptIn(params, notice) {
  const versions = params.getAll("notice_version");
  if (versions.length === 0) {
    return { status: "not_given", typed: ["name", "reason"].some((field) => params.getAll(field).some((value) => value !== "")) };
  }
  if (versions.length > 1) return { status: "not_sent", code: "field_repeated" };
  if (!notice) return { status: "not_sent", code: "notice_unavailable" };
  if (versions[0] !== notice.version) return { status: "not_sent", code: "notice_changed" };
  const declaration = { notice_version: notice.version };
  for (const field of ["name", "reason", "source"]) {
    const values = params.getAll(field);
    if (values.length > 1) return { status: "not_sent", code: "field_repeated" };
    if (values.length === 0 || values[0] === "") continue;
    const problem = field === "source" ? (SOURCES.includes(values[0]) ? null : "source_unknown") : displayTextProblem(values[0], FIELD_LIMITS[field]);
    if (problem) return { status: "not_sent", code: problem };
    if (field === "name" && RESERVED_NAMES.includes(nameKey(values[0]))) return { status: "not_sent", code: "reserved_name" };
    declaration[field] = values[0];
  }
  return { status: "opted_in", declaration };
}

// What the token page shows about the opt-in: { status, code?, detail? }. An opt-in's status comes from its delivery
// (door.js deliverArrival), and only the intake's acceptance reads "recorded".
const DELIVERED = Object.freeze({
  recorded: { status: "recorded" },
  skipped: { status: "not_recorded", code: "busy" },
  rate_limited: { status: "not_recorded", code: "busy" },
  refused: { status: "not_recorded", code: "refused" },
  not_sent: { status: "not_recorded", code: "intake_unavailable" },
});
export function declarationOutcome(optIn, delivery = null) {
  if (optIn.status === "opted_in") {
    const known = typeof delivery === "string" && Object.hasOwn(DELIVERED, delivery) ? DELIVERED[delivery] : { status: "unconfirmed" };
    return { ...known, detail: DECLARATION_TEXT[known.code ?? known.status] };
  }
  // Refused here, before anything was sent: not recorded, with the reason.
  if (optIn.status === "not_sent") return { status: "not_recorded", code: optIn.code, detail: DECLARATION_TEXT[optIn.code] };
  return optIn.typed ? { status: "not_given", detail: DECLARATION_TEXT.not_opted_in } : { status: "not_given" };
}

// The URL template of an opt-in at the purpose step; {purpose} and {source} stay placeholders unless given.
export function declareTemplate(origin, notice, { purpose = null, source = null } = {}) {
  return `${origin}/agents/intent?purpose=${purpose ?? "{purpose}"}&notice_version=${encodeURIComponent(notice.version)}&name={name}&reason={reason}&source=${source ?? "{source}"}`;
}

// How an agent opts in (the wall's JSON and the agent view): the notice, the template and the fields.
export function declareObject(origin, notice, { purpose = null, source = null } = {}) {
  if (!notice) return { status: "unavailable", optional: true, line: OPT_IN_LINE, detail: DECLARATION_TEXT.notice_unavailable };
  return {
    status: "available",
    optional: true,
    line: OPT_IN_LINE,
    notice: { version: notice.version, text: notice.text },
    how: "To opt in, follow the purpose link with notice_version as in the template, plus any of name, reason and source, each URL-encoded. Leave out what you don't want to give. Without notice_version nothing you type is recorded.",
    template: declareTemplate(origin, notice, { purpose, source }),
    fields: {
      notice_version: { const: notice.version, means: "you have read the notice and opt in" },
      name: { max_chars: FIELD_LIMITS.name, means: "who you are" },
      reason: { max_chars: FIELD_LIMITS.reason, means: "why you're here" },
      source: { enum: [...SOURCES], prefilled: source },
    },
    rules: "Plain text: no control characters and no direction-override characters. Published as you wrote it, not checked by us, and we may hide it.",
  };
}
