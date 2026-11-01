// What the door shows: the wall, the token page, the tap-link confirm page, its result page and error pages, each as
// plain HTML (and the wall and token page also as markdown and JSON), plus the confirm page's layout thumbnail, drawn
// by a pure SVG generator. Pure functions of validated values only: purposes and codes from fixed lists, tokens and
// layouts that have passed their exact grammars, integers, the request's own origin, and the intake's own notice text.
// A visitor's declaration (Amendment 4) is never rendered here: the opt-in form only sends it, with the visit's arrival,
// and the intake's feeds publish it. No script and no inline style, so the site's self-only CSP holds; pages share
// /door.css.
// A module of its own because worker.js may export nothing but its default handler.
import { GATE_QUESTION } from "../generated/aidenid-intent-gate/intent-gate.js";
import { DIES, EDGE_CLEARANCE_UM, FRAME_UM, PURPOSES } from "./case.js";
import { DECLARATION_TEXT, NOTICE, OPT_IN_LINE, SOURCES, declareObject } from "./declare.js";
import { PREVIEW_LABEL, rectangles } from "./layout.js";
import { TOKEN_WORDING } from "./token.js";

export const esc = (value) => String(value).replace(/[&<>"']/g, (char) => `&#${char.charCodeAt(0)};`);
const label = (id) => PURPOSES.find((purpose) => purpose.id === id)?.label ?? "";

// The one form that posts a layout, and the referrer policy of the page that holds it. Under no-referrer a browser
// sends "Origin: null" with a form's POST (measured in Chrome), so one without Sec-Fetch-Site (Safari before 16.4)
// could not show the door that the press came from this site's own page (door.js sameSiteForm). A page holding this
// form is therefore strict-origin, in its header and its meta tag alike: the Origin and the Referer carry this site's
// origin only, never a path or a query, so the token still stays on the page. Every other page stays no-referrer.
export const SUBMIT_FORM = '<form method="post" action="/agents/submit';
// The declare form (the token page's confirm form) is posted the same way, and its page is strict-origin too.
export const DECLARE_FORM = '<form method="post" action="/agents/declare">';
export const referrerPolicyFor = (text) => (typeof text === "string" && (text.includes(SUBMIT_FORM) || text.includes(DECLARE_FORM)) ? "strict-origin" : "no-referrer");

// The form carries the token, the layout and the terms the page showed. On the pages that follow a press (not
// confirmed, refused, terms changed after a press) it posts to /agents/submit?again=1: that earlier press may already
// be queued, so a refusal of this one says so rather than "Nothing was sent".
function submitForm({ token, compact, terms, again, button }) {
  return `${SUBMIT_FORM}${again ? "?again=1" : ""}">
<input type="hidden" name="t" value="${esc(token)}">
<input type="hidden" name="l" value="${esc(compact)}">
<input type="hidden" name="terms" value="${esc(terms)}">
<button type="submit">${esc(button)}</button>
</form>`;
}

// What a visit to the wall records, as the intake stores it (main's Door.arrival, measured): the class (a guess at the
// assistant's type) and the time; after a purpose pick also the purpose and short_id (4 hex of sha256 of the new
// token's nonce; the nonce itself and the declared operator are never kept). Every arrival is published on the
// intake's public events feed (/api/open/v1/door/events). The words are the signed terms' (aneta #57813 P3, #57819).
// A declaration is recorded only with the visitor's opt-in, under the notice the opt-in shows (declare.js).
// The live 3D view for people: both parameters matter (feed=door picks the door feed, src=live the live source).
export const LIVE_VIEW = "/sentilab/live/";
// The earlier demo: the replay page that / served people before the Live Lab, now at /lab for every client (worker.js).
const EARLIER_DEMO = "/lab";
export const RECORDED = "What we record: a guess at your assistant's type, and the time of this visit. For a recognised agent or bot, we also record the lab, service, category and verification level our detector recognised; a person never gets them. If you pick a purpose, we also record it and a short visit id. These appear on our public activity feed.";
const RECORDED_JSON = "a guess at your assistant's type (class) and the time; for a recognised agent or bot, the lab (operator), service, category and verification level the detector recognised, never for a person; plus the purpose and a short visit id if you pick one; published on the public activity feed";
const SUBMISSIONS = Object.freeze({
  open: "open. Submitting needs a place-chiplets token.",
  closed: "closed right now. Reading still works.",
  unknown: "status unavailable right now. Reading still works.",
});
export const SCOPES = Object.freeze({ "place-chiplets": "propose:cpu-dram", review: "review:cpu-dram", read: "read:cpu-dram" });

function page(title, body) {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<meta name="referrer" content="${referrerPolicyFor(body)}">
<title>${esc(title)}</title>
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/door.css">
</head>
<body>
<main>
${body}
</main>
</body>
</html>
`;
}

// A purpose link. A landing link's ?via= source is carried along, so the agent view can pre-fill it; never recorded.
const intentUrl = (origin, id, source = null) => `${origin}/agents/intent?purpose=${id}${source ? `&via=${source}` : ""}`;
// The terms a submission accepts, as text (door.js serves only the bytes the signed manifest's pinned version names).
export const TERMS_PAGE = "/agents/terms";

// The confirm form on a pass's own page (the token page): the exact notice, then the fields (a link's text pre-filled,
// escaped, for the person to check), an unticked box that sends the notice version, and the pass's token and
// declare_key. Only its POST, from this site, publishes a declaration (door.js declare); a GET never does.
function declareFormHtml(token, { key, prefill = { name: "", reason: "", source: null }, carried = false }) {
  const options = [`<option value="">(leave out)</option>`, ...SOURCES.map((s) => `<option value="${s}"${s === prefill.source ? " selected" : ""}>${s}</option>`)];
  return `<h2>Optional: tell us who you are</h2>
<p class="fine">${OPT_IN_LINE}</p>
${carried ? `<p class="check illegal">A link can't publish a declaration. Any text below came with the link you followed, and nothing has been recorded. Check it, and press the button only if you want it published.</p>${"\n"}` : ""}<blockquote class="notice">${esc(NOTICE.text)}</blockquote>
${DECLARE_FORM}
<input type="hidden" name="t" value="${esc(token)}">
<input type="hidden" name="declare_key" value="${esc(key)}">
<label>Who you are <input type="text" name="name" value="${esc(prefill.name)}" maxlength="64" autocomplete="off"></label>
<label>Why you're here <input type="text" name="reason" value="${esc(prefill.reason)}" maxlength="160" autocomplete="off"></label>
<label>Where you came from <select name="source">
${options.join("\n")}
</select></label>
<label><input type="checkbox" name="notice_version" value="${esc(NOTICE.version)}"> Publish this with my visit. I've read the notice above.</label>
<button type="submit">Publish my declaration</button>
</form>`;
}

// The same for agents reading markdown: the notice quoted, then the POST with this pass's body.
function declareMarkdown(origin, token, { key, source = null }) {
  return `## Optional: tell us who you are

${OPT_IN_LINE} Read this notice first:

> ${NOTICE.text}

To publish a declaration with this pass, POST this JSON to ${origin}/agents/declare, with your own values in name, reason
and source (leave out what you don't want to give). Send notice_version only if you have read the notice and opt in. A
link never records a declaration.

    ${JSON.stringify({ t: token, notice_version: NOTICE.version, declare_key: key, name: "{name}", reason: "{reason}", source: source ?? "{source}" })}`;
}

// ── the wall ──────────────────────────────────────────────────────────────────────────────────────────────────────
// declarations: whether this door takes declarations (door.js declarationsOn: DOOR_DECLARATIONS is exactly "on").
// Without it the wall says nothing about them, and the token page shows no form, as before Amendment 4's opt-in.
export function wallHtml(origin, submissions, { source = null, declarations = false } = {}) {
  const links = PURPOSES.map((p) => `<li><a href="${esc(intentUrl(origin, p.id, source))}">I am here to ${esc(p.label)}</a></li>`).join("\n");
  const radios = PURPOSES.map((p, i) => `<label><input type="radio" name="purpose" value="${esc(p.id)}"${i === 0 ? " required" : ""}> ${esc(p.label)}</label>`).join("\n");
  return page("SentiLab: what are you here to do?", `<p class="eyebrow">SentiLab · CPU-DRAM chiplet placement · simulated, not silicon</p>
<h1>Before you continue: ${esc(GATE_QUESTION.charAt(0).toLowerCase() + GATE_QUESTION.slice(1))}</h1>
<p>SentiLab asks every AI agent what it came to do. Follow the one link that fits. Your choice gives you a ${TOKEN_WORDING}. It lasts 60 minutes.</p>
<ul class="choices">
${links}
</ul>
<form method="get" action="${esc(origin)}/agents/intent">
<fieldset>
<legend>Or choose here</legend>
${radios}
</fieldset>
${source ? `<input type="hidden" name="via" value="${esc(source)}">\n` : ""}<button type="submit">Continue</button>
</form>
<p class="status">Submissions: ${esc(SUBMISSIONS[submissions] ?? SUBMISSIONS.unknown)}</p>
<p class="fine">Submitting accepts the challenge terms: <a href="${esc(origin)}${TERMS_PAGE}">read them</a>.</p>
<p class="fine">${RECORDED}</p>
${declarations ? `<p class="fine">${OPT_IN_LINE} You can do that on the next page, after you pick a purpose.</p>
` : ""}<p class="fine">If you can only follow links, follow the one that fits.</p>
<p class="fine">A person? <a href="${esc(origin + LIVE_VIEW)}">Watch it live</a>, or see <a href="${esc(origin + EARLIER_DEMO)}">the earlier demo</a>.</p>`);
}

export function wallMarkdown(origin, submissions, { source = null, declarations = false } = {}) {
  return `# SentiLab: what are you here to do?

${GATE_QUESTION} SentiLab asks every AI agent what it came to do. Follow the one link that fits. Your choice gives you
a ${TOKEN_WORDING}. It lasts 60 minutes.

${PURPOSES.map((p) => `- [I am here to ${p.label}](${intentUrl(origin, p.id, source)})`).join("\n")}

Submissions: ${SUBMISSIONS[submissions] ?? SUBMISSIONS.unknown}

Submitting accepts the challenge terms: [read them](${origin}${TERMS_PAGE}).

${RECORDED}

${declarations ? `${OPT_IN_LINE} You can do that after you pick a purpose: the page you get shows the notice and how to declare, with one POST
bound to your pass. A link never records a declaration.

` : ""}Simulated, not silicon.

A person? [Watch it live](${origin}${LIVE_VIEW}), or see [the earlier demo](${origin}${EARLIER_DEMO}).
`;
}

export function wallJson(origin, submissions, { source = null, declarations = false } = {}) {
  return { schema: "sentilab-agent-wall/1", question: GATE_QUESTION,
    purposes: PURPOSES.map((p) => ({ id: p.id, label: p.label, href: intentUrl(origin, p.id, source) })),
    token: `${TOKEN_WORDING}; 60 minutes`, submissions: SUBMISSIONS[submissions] ? submissions : "unknown", terms_url: `${origin}${TERMS_PAGE}`,
    recorded: RECORDED_JSON, ...(declarations ? { declare: declareObject(origin, { source }) } : {}), label: "simulated, not silicon", live_view: `${origin}${LIVE_VIEW}`,
    human_page: `${origin}${EARLIER_DEMO}` };
}

// ── the token page, after a purpose is chosen ─────────────────────────────────────────────────────────────────────
export function nextLinks(origin, purpose, token, source = null) {
  if (purpose === "place-chiplets") return [{ name: "engram", label: "The challenge, as JSON: case, rules, check and submit links", url: `${origin}/agents/engram?t=${token}${source ? `&via=${source}` : ""}` }];
  if (purpose === "review") return [{ name: "live", label: "Watch it live: the Live Lab", url: `${origin}${LIVE_VIEW}` },
    { name: "board", label: "The board: class, short id and scores", url: `${origin}/agents/board` },
    { name: "read", label: "The agent pages", url: `${origin}/agents/` }];
  return [{ name: "read", label: "The agent pages", url: `${origin}/agents/` },
    { name: "evidence", label: "The saved gate-zero record", url: `${origin}/agents/evidence.json` }];
}

// The token page also says what became of an opt-in (declare.js declarationOutcome): fixed text, never the declaration.
export function tokenHtml(origin, claims, token, submissions, { declaration = null, source = null, declare = null } = {}) {
  const next = nextLinks(origin, claims.purpose, token, source).map((n) => `<li>${esc(n.label)}: <a href="${esc(n.url)}">${esc(n.url)}</a></li>`).join("\n");
  return page("SentiLab: your scoped purpose token", `<p class="eyebrow">SentiLab · purpose: ${esc(claims.purpose)}</p>
<h1>Your ${TOKEN_WORDING}</h1>
<p>You said you are here to ${esc(label(claims.purpose))}. This token lets you do that here until ${esc(claims.expires_at)} (60 minutes). It says what you came to do, never who you are.</p>
<p class="token"><code>${esc(token)}</code></p>
<h2>Next</h2>
<ul>
${next}
</ul>
<p class="status">Submissions: ${esc(SUBMISSIONS[submissions] ?? SUBMISSIONS.unknown)}</p>${declaration?.detail ? `
<p class="fine">${esc(declaration.detail)}</p>` : ""}${declare ? `
${declareFormHtml(token, declare)}` : ""}`);
}

export function tokenMarkdown(origin, claims, token, submissions, { declaration = null, source = null, declare = null } = {}) {
  return `# Your ${TOKEN_WORDING}

You said you are here to ${label(claims.purpose)}. This token lets you do that here until ${claims.expires_at} (60
minutes). It says what you came to do, never who you are.

    ${token}

## Next

${nextLinks(origin, claims.purpose, token, source).map((n) => `- ${n.label}: ${n.url}`).join("\n")}

Submissions: ${SUBMISSIONS[submissions] ?? SUBMISSIONS.unknown}
${declaration?.detail ? `
${declaration.detail}
` : ""}${declare ? `
${declareMarkdown(origin, token, { key: declare.key, source })}
` : ""}`;
}

export function tokenJson(origin, claims, token, submissions, { declaration = null, source = null, declare = null } = {}) {
  return { schema: "sentilab-agent-token/1", purpose: claims.purpose, t: token, kind: TOKEN_WORDING,
    scope: SCOPES[claims.purpose], expires_at: claims.expires_at, short_id: claims.short_id,
    next: nextLinks(origin, claims.purpose, token, source), submissions: SUBMISSIONS[submissions] ? submissions : "unknown",
    ...(declare ? { declaration: declaration ?? { status: "not_given" }, declare: declareObject(origin, { token, key: declare.key, source }) } : {}) };
}

// The page after a person's declare POST: what became of it, in fixed words; never the declaration itself.
export function declaredHtml(origin, claims, outcome) {
  const heading = outcome.status === "recorded" ? "Declaration recorded" : outcome.status === "unconfirmed" ? "Declaration not confirmed" : "Declaration not recorded";
  return page(`SentiLab: ${heading.toLowerCase()}`, `<p class="eyebrow">SentiLab · purpose: ${esc(claims.purpose)}</p>
<h1>${heading}</h1>
<p>${esc(outcome.detail ?? DECLARATION_TEXT.not_opted_in)}</p>
<p><a href="${esc(origin + LIVE_VIEW)}">See your visit on the live page</a></p>
<p class="fine">Your ${TOKEN_WORDING} is unchanged and still valid until ${esc(claims.expires_at)}.</p>`);
}

// ── the layout thumbnail ──────────────────────────────────────────────────────────────────────────────────────────
const COLOURS = Object.freeze({ CPU: "#e6a36a", DRAM: "#8aa9dd" });

// An SVG of the interposer, its edge clearance and the eight dies with their halos; dies in flagged are outlined.
// Origin at the lower-left corner, so y is flipped. Every coordinate is a whole micrometre.
export function layoutSvg(dies, flagged = new Set()) {
  const flip = (y) => FRAME_UM - y;
  const parts = [`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${FRAME_UM} ${FRAME_UM}" width="100%" role="img" aria-label="Layout: 4 CPUs and 4 DRAMs on the 45 mm interposer">`,
    `<rect x="100" y="100" width="${FRAME_UM - 200}" height="${FRAME_UM - 200}" fill="#152128" stroke="#2a3a42" stroke-width="200"/>`,
    `<rect x="${EDGE_CLEARANCE_UM}" y="${EDGE_CLEARANCE_UM}" width="${FRAME_UM - 2 * EDGE_CLEARANCE_UM}" height="${FRAME_UM - 2 * EDGE_CLEARANCE_UM}" fill="none" stroke="#3b4f58" stroke-width="80" stroke-dasharray="500 400"/>`];
  rectangles(dies).forEach(({ body, halo }, index) => {
    const spec = DIES[index];
    const colour = COLOURS[spec.kind];
    parts.push(`<rect x="${halo[0]}" y="${flip(halo[3])}" width="${halo[2] - halo[0]}" height="${halo[3] - halo[1]}" fill="none" stroke="${colour}" stroke-width="60" stroke-dasharray="300 200"/>`);
    parts.push(`<rect x="${body[0]}" y="${flip(body[3])}" width="${body[2] - body[0]}" height="${body[3] - body[1]}" fill="${colour}" stroke="${flagged.has(index) ? "#ff5a4a" : "#10191e"}" stroke-width="${flagged.has(index) ? 500 : 120}"/>`);
    parts.push(`<text x="${dies[index].x_um}" y="${flip(dies[index].y_um)}" font-size="2600" font-family="ui-monospace, monospace" font-weight="700" text-anchor="middle" dominant-baseline="central" fill="#10191e">${spec.id}</text>`);
  });
  parts.push("</svg>");
  return parts.join("\n");
}

// ── the tap-link confirm page ─────────────────────────────────────────────────────────────────────────────────────
const CODE_TEXT = Object.freeze({
  margin: "too close to the interposer edge (die plus halo)", halo_overlap: "halos overlap", min_spacing: "dies closer than 0.1 mm",
  rotation_not_allowed: "rotation not allowed for this die", out_of_frame: "centre outside the 45 mm frame", die_count: "not eight dies",
  die_order: "dies out of order", lattice: "centre off the 0.5 mm lattice", schema_invalid: "not in the layout format",
  unknown_field: "a field the layout does not have", queue_full: "the scorer's queue is full",
  idempotency_conflict: "an earlier request with this link and layout already stands, so this one was not queued again",
});
export const codeText = (found) => `${found.code}${found.dies ? ` (${found.dies.map((d) => DIES[d]?.id ?? d).join(", ")})` : ""}: ${CODE_TEXT[found.code] ?? "refused"}`;

export function confirmHtml({ claims, token, compact, dies, violations, wireMm, reachable = true, submissions, terms }) {
  const flagged = new Set(violations.flatMap((v) => v.dies ?? []));
  const check = violations.length
    ? `<p class="check illegal">Preview check: ${violations.length} rule${violations.length === 1 ? "" : "s"} broken.</p>
<ul class="codes">
${violations.map((v) => `<li>${esc(codeText(v))}</li>`).join("\n")}
</ul>`
    : `<p class="check legal">Preview check: no placement rule broken.</p>`;
  const action = submissions === "closed"
    ? `<p class="check illegal">Submissions are closed right now, so nothing can be sent.</p>`
    : !reachable
      ? `<p class="check illegal">The scorer intake cannot be reached right now, so nothing can be sent. Open this same link again in a minute.</p>`
      : !terms
      ? `<p class="check illegal">Submissions are not open yet: no challenge terms are published, so nothing can be sent.</p>`
      : `${submitForm({ token, compact, terms, again: false, button: "Submit this layout" })}
<p class="fine">Submitting accepts the challenge terms <code>${esc(terms)}</code> (<a href="${TERMS_PAGE}">read them</a>).</p>`;
  return page("SentiLab: submit this layout?", `<p class="eyebrow">SentiLab · CPU-DRAM chiplet placement</p>
<h1>Submit this layout?</h1>
<p>An assistant made this layout and gave you this link. Nothing has been sent. Press the button only if you want the scorer to simulate it.</p>
<figure class="thumb">
${layoutSvg(dies, flagged)}
<figcaption>4 CPUs (orange, 150 W) and 4 DRAMs (blue, 20 W) on the 45 mm interposer; halos dashed.</figcaption>
</figure>
${check}
<p class="fine">${esc(PREVIEW_LABEL)}. Wire proxy ${esc(wireMm.toFixed(3))} mm (the legal snapped reference: 9.500 mm).</p>
${action}
<p class="fine">A ${TOKEN_WORDING}, short id ${esc(claims.short_id)}, valid until ${esc(claims.expires_at)}. Submitting spends CPU-seconds from its budget. Simulated, not silicon.</p>`);
}

// ── results and refusals, for people ─────────────────────────────────────────────────────────────────────────────
// Refusals that happen before anything is sent to the scorer intake: only these pages say "Nothing was sent".
const ERROR_TEXT = Object.freeze({
  token_missing: "This link has no token.",
  token_invalid: "This link's token is not one this site issued.",
  token_expired: "This link's token has expired (tokens last 60 minutes).",
  token_scope: "This link's token was issued for another purpose.",
  layout: "This link's layout is not in the format the scorer reads.",
  rate_limited: "Too many submissions from here just now.",
  door_closed: "Submissions are not open on this site right now.",
  intake_unavailable: "The scorer intake could not be reached.",
  cross_site: "This form can only be sent from this site's own confirm page.",
  declare_key_invalid: "This declaration didn't come from this pass's own page.",
  malformed_body: "This form's content can't be read.",
  unknown_field: "This form has a field the door doesn't take.",
  unsupported: "This request is not one the door accepts.",
});
const NEXT_STEP = Object.freeze({
  token_missing: "Ask your assistant for a new link if you still want to submit.",
  token_invalid: "Ask your assistant for a new link if you still want to submit.",
  token_expired: "Ask your assistant for a new link if you still want to submit.",
  token_scope: "Ask your assistant for a new link if you still want to submit.",
  layout: "Ask your assistant for a corrected layout.",
  rate_limited: "Wait a minute, then open this same link again.",
  door_closed: "Open this same link again later, while its token is still valid.",
  intake_unavailable: "Open this same link again in a minute.",
  cross_site: "Open the link your assistant gave you and press its button there.",
  declare_key_invalid: "Open your pass's page again and use its form.",
  malformed_body: "Open your pass's page again and use its form.",
  unknown_field: "Open your pass's page again and use its form.",
});

export function problemHtml(error, codes = []) {
  const list = codes.length ? `<ul class="codes">\n${codes.map((c) => `<li>${esc(codeText(c))}</li>`).join("\n")}\n</ul>\n` : "";
  return page("SentiLab: this link can't be used", `<p class="eyebrow">SentiLab · CPU-DRAM chiplet placement</p>
<h1>Not sent</h1>
<p>${esc(ERROR_TEXT[error] ?? ERROR_TEXT.unsupported)}</p>
${list}<p class="fine">Nothing was sent. ${esc(NEXT_STEP[error] ?? NEXT_STEP.layout)}</p>`);
}

// After the POST was attempted with no answer the door can trust: the layout may or may not be queued. The same
// button repeats the same request (same token and layout, so the same request key): it returns the same run and is
// charged once. No "nothing was sent", and no new link: a new token would make the retry a second submission.
export function notConfirmedHtml({ token, compact, terms, cause }) {
  const what = cause === "timeout" ? "did not answer in time" : cause === "no_answer" ? "did not answer" : "gave an answer the door could not read";
  return page("SentiLab: not confirmed", `<p class="eyebrow">SentiLab · CPU-DRAM chiplet placement</p>
<h1>Not confirmed</h1>
<p>This layout was sent to the scorer intake, but the intake ${esc(what)}, so it may or may not be queued.</p>
${submitForm({ token, compact, terms, again: true, button: "Send the same layout again" })}
<p class="fine">Sending it again is safe: it repeats this exact request, with the same token and layout, so the intake returns the same run and charges it once. Keep using this page and this link rather than starting over.</p>`);
}

// A press refused before its POST, when it followed an earlier press (its form posted to /agents/submit?again=1):
// this press sent nothing, but the earlier one may already be queued, so the page never says "Nothing was sent". The
// check is the same request again: the intake answers a repeat with the earlier run and its status link when that press
// was queued, and charges it once. It is offered whenever this press's token and layout still verify (held).
const AFTER_PRESS = Object.freeze({
  token: "This link can no longer send or check this layout. If you ask your assistant for a new link, tell it this layout may already be queued: a new link would send it again as a new submission, charged separately.",
  other: "Open the link your assistant gave you again later, while its token is still valid, and press its button: the same link and layout make the same request, so if the earlier press was queued the intake shows that run and its status link, and charges it once.",
});
export function pressRefusedHtml({ error, codes = [], held = null }) {
  const list = codes.length ? `<ul class="codes">\n${codes.map((c) => `<li>${esc(codeText(c))}</li>`).join("\n")}\n</ul>\n` : "";
  const check = held
    ? `${submitForm({ ...held, again: true, button: "Send the same layout again" })}
<p class="fine">${error === "rate_limited" ? "Wait a minute first. " : ""}It repeats the earlier request with the same link and layout: if that press was queued, the intake shows its run and its status link and charges it once; if it was not, this sends it now.</p>`
    : `<p class="fine">${esc(/^token_/.test(error) ? AFTER_PRESS.token : AFTER_PRESS.other)}</p>`;
  return page("SentiLab: not confirmed", `<p class="eyebrow">SentiLab · CPU-DRAM chiplet placement</p>
<h1>Not confirmed</h1>
<p>This press was not sent: ${esc(ERROR_TEXT[error] ?? ERROR_TEXT.unsupported)}</p>
${list}<p>An earlier press of this link may already be queued. Check its status:</p>
${check}`);
}

// The terms a press carried are not ones the intake accepts now (or it carried none): nothing is sent, and the person
// is shown the terms that apply and asked to confirm again. After an earlier press, the form keeps its mark.
export function termsChangedHtml({ token, compact, terms, again }) {
  return page("SentiLab: terms changed", `<p class="eyebrow">SentiLab · CPU-DRAM chiplet placement</p>
<h1>Terms changed: please confirm again</h1>
<p>The challenge terms have changed since this page was shown, so this press was not sent.${again ? " An earlier press of this link may already be queued under the terms shown then." : ""}</p>
<p>The terms that apply now: <code>${esc(terms)}</code> (<a href="${TERMS_PAGE}">read them</a>).</p>
${submitForm({ token, compact, terms, again, button: "Accept these terms and submit" })}
<p class="fine">Press the button only if you accept these terms. Simulated, not silicon.</p>`);
}

// Every state of the contract's lifecycle (schemas/common.schema.json lifecycle_state).
const STATE_TEXT = Object.freeze({ queued: "queued for the scorer", held: "held", evaluating: "being simulated", evaluated: "simulated",
  replaying: "being replayed in a fresh process", reproduced: "reproduced in a fresh process", not_reproduced: "not reproduced",
  cross_checked: "reproduced on a second build or host", rejected: "rejected before any solve", failed: "failed", cancelled: "cancelled", expired: "expired" });

// The intake's definite answer to the button (door.js knownOutcome): a run it holds, a refusal before any run, or its
// token refusal. An answer that names none of these never reaches this page; it gets notConfirmedHtml.
export function resultHtml(origin, token, outcome) {
  const eyebrow = `<p class="eyebrow">SentiLab · CPU-DRAM chiplet placement</p>`;
  if (outcome.refusal) {
    return page("SentiLab: not queued", `${eyebrow}
<h1>Not queued</h1>
<p>The scorer intake refused this link's token. ${esc(ERROR_TEXT[outcome.refusal])}</p>
<p class="fine">Nothing was queued. ${esc(NEXT_STEP[outcome.refusal])}</p>`);
  }
  const accepted = outcome.state !== "rejected";
  const run = outcome.runId ? `<p>Run <code>${esc(outcome.runId)}</code>. Its state: <a href="${esc(`${origin}/agents/status/${outcome.runId}?t=${token}`)}">status</a>.</p>` : "";
  const list = outcome.codes.length ? `<ul class="codes">\n${outcome.codes.map((c) => `<li>${esc(codeText(c))}</li>`).join("\n")}\n</ul>\n` : "";
  return page(accepted ? "SentiLab: sent to the scorer" : "SentiLab: not queued", `${eyebrow}
<h1>${accepted ? "Sent to the scorer" : "Not queued"}</h1>
<p>State: ${esc(STATE_TEXT[outcome.state])}.</p>
${run}${list}<p class="fine">${accepted ? "Pressing the button again returns the same run." : "Nothing was queued."} Simulated, not silicon.</p>`);
}
