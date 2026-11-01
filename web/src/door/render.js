// What the door shows: the wall, the token page, the tap-link confirm page, its result page and error pages, each as
// plain HTML (and the wall and token page also as markdown and JSON), plus the confirm page's layout thumbnail, drawn
// by a pure SVG generator. Pure functions of validated values only: purposes and codes from fixed lists, tokens and
// layouts that have passed their exact grammars, integers, and the request's own origin. No visitor text is ever
// rendered. No script and no inline style, so the site's self-only CSP holds; pages share /door.css.
// A module of its own because worker.js may export nothing but its default handler.
import { GATE_QUESTION } from "../generated/aidenid-intent-gate/intent-gate.js";
import { DIES, EDGE_CLEARANCE_UM, FRAME_UM, PURPOSES } from "./case.js";
import { PREVIEW_LABEL, rectangles } from "./layout.js";
import { TOKEN_WORDING } from "./token.js";

export const esc = (value) => String(value).replace(/[&<>"']/g, (char) => `&#${char.charCodeAt(0)};`);
const label = (id) => PURPOSES.find((purpose) => purpose.id === id)?.label ?? "";
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
<meta name="referrer" content="no-referrer">
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

const intentUrl = (origin, id) => `${origin}/agents/intent?purpose=${id}`;

// ── the wall ──────────────────────────────────────────────────────────────────────────────────────────────────────
export function wallHtml(origin, submissions) {
  const links = PURPOSES.map((p) => `<li><a href="${esc(intentUrl(origin, p.id))}">I am here to ${esc(p.label)}</a></li>`).join("\n");
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
<button type="submit">Continue</button>
</form>
<p class="status">Submissions: ${esc(SUBMISSIONS[submissions] ?? SUBMISSIONS.unknown)}</p>
<p class="fine">Only the purpose you pick is recorded. If you can only follow links, follow the one that fits.</p>
<p class="fine">A person? <a href="${esc(origin)}/?view=human">Open the normal site</a>.</p>`);
}

export function wallMarkdown(origin, submissions) {
  return `# SentiLab: what are you here to do?

${GATE_QUESTION} SentiLab asks every AI agent what it came to do. Follow the one link that fits. Your choice gives you
a ${TOKEN_WORDING}. It lasts 60 minutes.

${PURPOSES.map((p) => `- [I am here to ${p.label}](${intentUrl(origin, p.id)})`).join("\n")}

Submissions: ${SUBMISSIONS[submissions] ?? SUBMISSIONS.unknown}

Only the purpose you pick is recorded. Simulated, not silicon.

A person? [Open the normal site](${origin}/?view=human).
`;
}

export function wallJson(origin, submissions) {
  return { schema: "sentilab-agent-wall/1", question: GATE_QUESTION,
    purposes: PURPOSES.map((p) => ({ id: p.id, label: p.label, href: intentUrl(origin, p.id) })),
    token: `${TOKEN_WORDING}; 60 minutes`, submissions: SUBMISSIONS[submissions] ? submissions : "unknown",
    recorded: "the purpose id only", label: "simulated, not silicon", human_page: `${origin}/?view=human` };
}

// ── the token page, after a purpose is chosen ─────────────────────────────────────────────────────────────────────
export function nextLinks(origin, purpose, token) {
  if (purpose === "place-chiplets") return [{ name: "engram", label: "The challenge, as JSON: case, rules, check and submit links", url: `${origin}/agents/engram?t=${token}` }];
  if (purpose === "review") return [{ name: "board", label: "The board: class, short id and scores", url: `${origin}/agents/board` },
    { name: "read", label: "The agent pages", url: `${origin}/agents/` }];
  return [{ name: "read", label: "The agent pages", url: `${origin}/agents/` },
    { name: "evidence", label: "The saved gate-zero record", url: `${origin}/agents/evidence.json` }];
}

export function tokenHtml(origin, claims, token, submissions) {
  const next = nextLinks(origin, claims.purpose, token).map((n) => `<li>${esc(n.label)}: <a href="${esc(n.url)}">${esc(n.url)}</a></li>`).join("\n");
  return page("SentiLab: your scoped purpose token", `<p class="eyebrow">SentiLab · purpose: ${esc(claims.purpose)}</p>
<h1>Your ${TOKEN_WORDING}</h1>
<p>You said you are here to ${esc(label(claims.purpose))}. This token lets you do that here until ${esc(claims.expires_at)} (60 minutes). It says what you came to do, never who you are.</p>
<p class="token"><code>${esc(token)}</code></p>
<h2>Next</h2>
<ul>
${next}
</ul>
<p class="status">Submissions: ${esc(SUBMISSIONS[submissions] ?? SUBMISSIONS.unknown)}</p>`);
}

export function tokenMarkdown(origin, claims, token, submissions) {
  return `# Your ${TOKEN_WORDING}

You said you are here to ${label(claims.purpose)}. This token lets you do that here until ${claims.expires_at} (60
minutes). It says what you came to do, never who you are.

    ${token}

## Next

${nextLinks(origin, claims.purpose, token).map((n) => `- ${n.label}: ${n.url}`).join("\n")}

Submissions: ${SUBMISSIONS[submissions] ?? SUBMISSIONS.unknown}
`;
}

export function tokenJson(origin, claims, token, submissions) {
  return { schema: "sentilab-agent-token/1", purpose: claims.purpose, t: token, kind: TOKEN_WORDING,
    scope: SCOPES[claims.purpose], expires_at: claims.expires_at, short_id: claims.short_id,
    next: nextLinks(origin, claims.purpose, token), submissions: SUBMISSIONS[submissions] ? submissions : "unknown" };
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
      : `<form method="post" action="/agents/submit">
<input type="hidden" name="t" value="${esc(token)}">
<input type="hidden" name="l" value="${esc(compact)}">
<button type="submit">Submit this layout</button>
</form>
<p class="fine">Submitting accepts the challenge terms <code>${esc(terms)}</code>.</p>`;
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
export function notConfirmedHtml({ token, compact, cause }) {
  const what = cause === "timeout" ? "did not answer in time" : cause === "no_answer" ? "did not answer" : "gave an answer the door could not read";
  return page("SentiLab: not confirmed", `<p class="eyebrow">SentiLab · CPU-DRAM chiplet placement</p>
<h1>Not confirmed</h1>
<p>This layout was sent to the scorer intake, but the intake ${esc(what)}, so it may or may not be queued.</p>
<form method="post" action="/agents/submit">
<input type="hidden" name="t" value="${esc(token)}">
<input type="hidden" name="l" value="${esc(compact)}">
<button type="submit">Send the same layout again</button>
</form>
<p class="fine">Sending it again is safe: it repeats this exact request, with the same token and layout, so the intake returns the same run and charges it once. Keep using this page and this link rather than starting over.</p>`);
}

// Every state of the contract's lifecycle (schemas/common.schema.json lifecycle_state).
const STATE_TEXT = Object.freeze({ queued: "queued for the scorer", held: "held", evaluating: "being simulated", evaluated: "simulated",
  replaying: "being replayed in a fresh process", reproduced: "reproduced in a fresh process", not_reproduced: "not reproduced",
  cross_checked: "independently verified", rejected: "rejected before any solve", failed: "failed", cancelled: "cancelled", expired: "expired" });

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
