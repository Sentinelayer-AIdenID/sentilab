// A visitor's opt-in declaration (AGENT-DOOR Amendment 4 rev 2, section 4.1; root's #89 contract,
// docs/sentilab/DOOR-VISITORS.md): {notice_version, name (up to 64 characters), reason (up to 160), source (one of
// SOURCES)}, public display data the visitor chooses to give, shown as written and checked by no one.
//
//   - Published only by an explicit POST to /agents/declare, bound to the visitor's own pass (warden's hold at
//     c078b4fe): a person's same-origin form POST from the confirm page (the token page, which shows the exact notice and
//     the exact text), or an agent's JSON POST with its pass token and the declare_key its own pass's view showed. A GET
//     never records a declaration: a link's query parameters at most pre-fill the confirm form (door.js).
//   - The notice is NOTICE, bundled with the Worker: the API's own (app/door/intake.py VISITOR_NOTICE and
//     VISITOR_DISCLOSURE), checked at test time against the fixture the API's code generates. Nothing polls the API.
//   - The opt-in is the visitor sending notice_version, equal to NOTICE.version, with the pass's declare_key. Only then
//     are name, reason and source read. The door never declares on a visitor's behalf.
//   - Name and reason follow root's shared character policy, judged on the original input exactly as the API judges it
//     (app/door/intake.py, Unicode 16.0.0): any code point of the general categories Cc, Cf, Co, Cs, Cn, Zl or Zp is
//     refused (controls, format and bidi characters, tag characters, zero-width characters, the BOM, private use,
//     surrogates, unassigned code points, line and paragraph separators), as are the five invisible fillers, every
//     Default_Ignorable_Code_Point (DEFAULT_IGNORABLE) and a run of more than MAX_MARK_RUN consecutive marks (Mn, Mc,
//     Me); there is no total mark quota. Categories and marks come from unicode16.js, tables generated from the API's
//     own unicodedata2 16.0.0, never from the engine's property escapes (Unicode 17.0 in Node 22 and workerd). A field with
//     nothing left once the reserved-name comparison's cleanup is done (only spaces) is refused as blank. Lengths count
//     code points. Accepted text is passed on exactly as written: no trimming, no normalising.
//   - A name that normalizes to one of the lab's own interface labels is refused (RESERVED_NAMES, defense in depth).
//   - ?via=<source> on a landing link only pre-fills source and records nothing.
// A module of its own because worker.js may export nothing but its default handler.
import { FORMAT, MARKS, REFUSED } from "./unicode16.js";

export const SOURCES = Object.freeze(["moltbook", "senti", "github", "direct", "other"]);
export const FIELD_LIMITS = Object.freeze({ name: 64, reason: 160 });
export const MAX_MARK_RUN = 8;
// The five assigned characters that render blank but are letters or symbols, so the category rule passes them
// (warden's P3 at c43571e4): the Hangul fillers U+115F, U+1160, U+3164 and U+FFA0, and the blank Braille pattern
// U+2800. They are in unicode16.js REFUSED, from the API's own list (intake._REFUSED_DECLARATION_FILLERS).
// Unicode 16.0 Default_Ignorable_Code_Point (DerivedCoreProperties-16.0.0.txt): 4,174 code points that render as
// nothing. Most are already Cf or Cn; 263 are marks that the category rule passes (the combining grapheme joiner
// U+034F, the variation selectors and others), so "admin" plus one of them would read as "admin". Each is refused in a
// name or reason, as the API refuses them (app/door/intake.py _DEFAULT_IGNORABLE, the same ranges). [first, last]
// pairs, flattened, as in unicode16.js.
export const DEFAULT_IGNORABLE = Object.freeze([0x00AD, 0x00AD, 0x034F, 0x034F, 0x061C, 0x061C, 0x115F, 0x1160, 0x17B4, 0x17B5,
  0x180B, 0x180F, 0x200B, 0x200F, 0x202A, 0x202E, 0x2060, 0x206F, 0x3164, 0x3164, 0xFE00, 0xFE0F, 0xFEFF, 0xFEFF, 0xFFA0,
  0xFFA0, 0xFFF0, 0xFFF8, 0x1BCA0, 0x1BCA3, 0x1D173, 0x1D17A, 0xE0000, 0xE0FFF]);
export const NOTICE = Object.freeze({
  version: "sentilab-public-visitor/1",
  text: "Your visit time, detector classification and selected purpose are public. If you opt in, your declared name, reason and source category are also public. We keep a handle internally to count purpose passes; that handle is not published. These declarations are not verified identity. Referrer URLs and query strings are not collected automatically, and the raw purpose-pass credential is not added as a generated feed field. All text you enter in name or reason is public. Do not include private information.",
});
// Whether a code point is in a table of sorted, disjoint [first, last] ranges, flattened (unicode16.js): a binary search.
function inRanges(table, code) {
  let low = 0;
  let high = table.length / 2 - 1;
  while (low <= high) {
    const middle = (low + high) >> 1;
    if (code < table[2 * middle]) high = middle - 1;
    else if (code > table[2 * middle + 1]) low = middle + 1;
    else return true;
  }
  return false;
}
const refusedCode = (code) => inRanges(REFUSED, code) || inRanges(DEFAULT_IGNORABLE, code);

// The one line the wall and the agent view both show about declarations: optional, public, as written, unchecked,
// hideable (the signed terms, aneta #57819).
export const OPT_IN_LINE = "Optional: you can also tell us who you are, why you're here and where you came from. We publish it as you wrote it, we don't check it, and we may hide it.";

// Names that would pass for the lab's own interface labels are refused, so no declaration can read as a system, staff
// or participant label. They are compared by nameKey: NFKC, format characters removed, whitespace runs collapsed,
// trimmed, lower-cased. The character policy has already judged the original input. This is defense in depth; a
// declaration is always shown as "self-described", behind a click. The format characters are Unicode 16.0's
// (unicode16.js FORMAT), as the API's. NFKC and lower-casing are the engine's: NFKC is stable for every character that
// Unicode 16 assigns (the only ones the policy lets through), and toLowerCase lowers the 27 capitals Unicode 16 added
// with a lower-case pair, which the API's Python 3.12 lower() (Unicode 15.0) keeps; no reserved name holds one.
export const RESERVED_NAMES = Object.freeze(["human", "you", "senti", "participant", "unidentified participant", "system", "owner", "admin",
  "moderator"]);
export function nameKey(name) {
  const kept = Array.from(name.normalize("NFKC")).filter((char) => !inRanges(FORMAT, char.codePointAt(0))).join("");
  return kept.replace(/\s+/gu, " ").trim().toLowerCase();
}

// What a page says about a declaration, by outcome; fixed text, never the visitor's.
export const DECLARATION_TEXT = Object.freeze({
  recorded: "Your declaration was recorded with this visit. It's public, shown as you wrote it, not checked by us, and we may hide it.",
  busy: "Your declaration was not recorded: too many visits from your network just now. Your purpose pass works as usual.",
  refused: "Your declaration was not recorded: the intake refused it. Your purpose pass works as usual.",
  intake_unavailable: "Your declaration was not recorded: the intake can't be reached. Your purpose pass works as usual.",
  unconfirmed: "Your declaration was sent with this visit, but no confirmation came back, so it may or may not appear on the public feed. Your purpose pass works as usual.",
  not_opted_in: "You didn't opt in, so nothing you typed was recorded.",
  link_cannot_declare: "A link can't publish a declaration, so nothing was recorded. To publish one, confirm it with this pass's own form or POST.",
  notice_changed: "The notice has changed since you read it, so nothing you typed was recorded. Read the current notice and try again.",
  field_repeated: "A field was given more than once, so nothing you typed was recorded.",
  too_long: "A field is too long (a name is at most 64 characters, a reason at most 160), so nothing you typed was recorded.",
  control_character: "A field has an invisible, control or unassigned character, so nothing you typed was recorded.",
  combining_marks: "A field has more than 8 combining marks in a row, so nothing you typed was recorded.",
  blank: "A field has nothing visible in it, so nothing you typed was recorded.",
  source_unknown: "Where you came from must be one of moltbook, senti, github, direct or other, so nothing you typed was recorded.",
  reserved_name: "That name is reserved for the lab's own labels, so nothing you typed was recorded. Your purpose pass works as usual.",
});

// null when text is acceptable display text of at most max code points; otherwise the reason it is not. Judged on the
// text exactly as given, code point by code point, with the Unicode 16.0 tables (a lone surrogate is a code point of
// its own, Cs, and refused). A refused character anywhere outranks a run of marks.
export function displayTextProblem(text, max) {
  const codes = Array.from(text, (char) => char.codePointAt(0));
  if (codes.some(refusedCode)) return "control_character";
  let run = 0;
  for (const code of codes) {
    run = inRanges(MARKS, code) ? run + 1 : 0;
    if (run > MAX_MARK_RUN) return "combining_marks";
  }
  return codes.length > max ? "too_long" : null;
}

// The source a landing link's ?via= pre-fills: exactly one via, exactly one of SOURCES; otherwise null.
export function viaSource(params) {
  const values = params.getAll("via");
  return values.length === 1 && SOURCES.includes(values[0]) ? values[0] : null;
}

// Whether a link's query carries anything of a declaration (which a GET never records).
export function linkCarriesDeclaration(params) {
  return ["notice_version", "declare_key", "name", "reason", "source"].some((field) => params.getAll(field).some((value) => value !== ""));
}

// The confirm form's pre-fill from a link's query: its text is shown, escaped, for the person to check; never recorded.
export function prefillFrom(params) {
  const first = (field) => params.getAll(field)[0] ?? "";
  const source = SOURCES.includes(first("source")) ? first("source") : viaSource(params);
  return { name: first("name"), reason: first("reason"), source };
}

// The declare POST's opt-in: { status: "not_given", typed } (no notice_version: nothing is read, typed says whether a
// name or reason was typed anyway), { status: "opted_in", declaration }, or { status: "not_sent", code } (refused here,
// so nothing is sent). illFormed names the fields whose value, as sent, was not well-formed UTF-16: a JSON body's lone
// surrogate, which the params can't hold (door.js declareFields). Each is refused as the control character it is.
export function readOptIn(params, illFormed = []) {
  const versions = params.getAll("notice_version");
  if (versions.length === 0) {
    return { status: "not_given", typed: ["name", "reason"].some((field) => params.getAll(field).some((value) => value !== "")) };
  }
  if (versions.length > 1) return { status: "not_sent", code: "field_repeated" };
  if (versions[0] !== NOTICE.version) return { status: "not_sent", code: "notice_changed" };
  const declaration = { notice_version: NOTICE.version };
  for (const field of ["name", "reason", "source"]) {
    const values = params.getAll(field);
    if (values.length > 1) return { status: "not_sent", code: "field_repeated" };
    if (illFormed.includes(field)) return { status: "not_sent", code: "control_character" };
    if (values.length === 0 || values[0] === "") continue;
    const problem = field === "source" ? (SOURCES.includes(values[0]) ? null : "source_unknown") : displayTextProblem(values[0], FIELD_LIMITS[field]);
    if (problem) return { status: "not_sent", code: problem };
    // Nothing left once the comparison's cleanup is done (only spaces): nothing a reader could check. The API refuses it.
    if (field !== "source" && nameKey(values[0]) === "") return { status: "not_sent", code: "blank" };
    if (field === "name" && RESERVED_NAMES.includes(nameKey(values[0]))) return { status: "not_sent", code: "reserved_name" };
    declaration[field] = values[0];
  }
  return { status: "opted_in", declaration };
}

// What a page shows about a declaration: { status, code?, detail? }. An opt-in's status comes from its delivery
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

// How an agent declares. Without a pass (the wall): after the pick, by POST. With one (the token page and the ENGRAM
// view): the endpoint and the exact body, this pass's token and its declare_key included.
export function declareObject(origin, { token = null, key = null, source = null } = {}) {
  const fields = {
    notice_version: { const: NOTICE.version, means: "you have read the notice and opt in" },
    name: { max_chars: FIELD_LIMITS.name, means: "who you are" },
    reason: { max_chars: FIELD_LIMITS.reason, means: "why you're here" },
    source: { enum: [...SOURCES], prefilled: source },
  };
  const rules = "Plain text with something visible in it: no invisible, control or unassigned characters (Unicode 16.0), at most 8 combining marks in a row, and not one of the lab's own labels. Published as you wrote it, not checked by us, and we may hide it.";
  if (!token) {
    return { status: "after_purpose", optional: true, line: OPT_IN_LINE, notice: { ...NOTICE },
      how: "Pick a purpose first. Your pass's own view (the page the purpose link returns, and the ENGRAM view) then gives the endpoint and the key to declare with one POST. A link never records a declaration.",
      fields, rules };
  }
  return { status: "available", optional: true, line: OPT_IN_LINE, notice: { ...NOTICE },
    how: "To publish a declaration with this pass, POST this JSON body to the endpoint, with your own values in name, reason and source; leave out what you don't want to give. Send notice_version only if you have read the notice and opt in.",
    endpoint: { method: "POST", url: `${origin}/agents/declare`, content_type: "application/json" },
    body: { t: token, notice_version: NOTICE.version, declare_key: key, name: "{name}", reason: "{reason}", source: source ?? "{source}" },
    fields, rules };
}
