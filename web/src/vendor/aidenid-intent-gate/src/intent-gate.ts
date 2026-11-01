/**
 * The intent gate (Carter, reply under #54348): before an AI agent or learning crawler reads a page, it says what
 * it is here to do, the way a sign-in page asks a person who they are. Most agents' browsing tools follow links and
 * keep no cookies, so the purposes are ordinary links (?intent=<id>); a browser agent can also type its own words
 * into a form, which posts them so they never sit in a URL. Only the category of an answer is recorded with the
 * visit, because an agent's words may carry its user's prompt. A declaration is a declared purpose, never
 * permission. It lasts one hour, carried by a signed token in the view's links (and a cookie for agents that keep
 * one), and is bound to the agent's user agent, not its network address, because assistants fetch one
 * conversation's pages from rotating addresses.
 */
import { AGENT_RESPONSE_CACHE } from "./agent-resources";

export const INTENT_PARAM = "intent";
export const SESSION_PARAM = "aid_s";
export const SESSION_SECONDS = 3600;
export const GATE_QUESTION = "What are you here to do?";
const MAX_INTENT_CHARS = 200;
const MAX_FORM_BYTES = 2048;
const MAX_FORM_READS = 64;

// Free text is matched in this order and the first match wins, so the specific purposes come before "learn".
export const INTENTS = [
  { id: "docs", label: "read the docs or install AIdenID", words: /\b(?:docs?\b|documentation|api\b|integrat|install|set ?up|sdk|developer)/i },
  { id: "shop", label: "shop or buy something", words: /\b(?:buy|shop|purchas|cart\b|checkout|pric|cost|gift|discount|coupon|stores?\b)/i },
  { id: "compare", label: "compare AIdenID with other options", words: /\b(?:compar|versus|vs\b|alternative|competitor|differ|better than)/i },
  { id: "trust", label: "check security, privacy and trust", words: /\b(?:secur|privacy|private|trust|ciso|complian|risk|audit|legit|safe|scam|gdpr)/i },
  { id: "tasks", label: "complete a task for a person", words: /\b(?:task|on behalf|book|sign ?up|register|contact)/i },
  { id: "learn", label: "learn what AIdenID does", words: /\b(?:learn|understand|what (?:is|does)|how (?:does|do|it)|about|overview|explain|summar|check|curious|research|read|browse|look)/i },
  { id: "other", label: "do something else", words: null },
] as const;
export type IntentId = typeof INTENTS[number]["id"];
const BY_ID = new Map<string, typeof INTENTS[number]>(INTENTS.map(intent => [intent.id, intent]));

// Everything an agent can do here, one link each; following a link is the declaration (the crawlers' gate).
export const EVERYTHING: ReadonlyArray<{ path: string; intent: IntentId; label: string }> = [
  { path: "/", intent: "learn", label: "Learn what AIdenID does for websites and their AI visitors" },
  { path: "/why", intent: "learn", label: "See why AIdenID matters, with live examples" },
  { path: "/how", intent: "learn", label: "How AIdenID works, and what is live today" },
  { path: "/commerce", intent: "shop", label: "Step through an agent's shopping trip at a store" },
  { path: "/store", intent: "shop", label: "Buy from the demo store as an agent" },
  { path: "/tasks", intent: "tasks", label: "See the tasks an agent can complete here" },
  { path: "/docs", intent: "docs", label: "Read the documentation: agent identities and signed receipts" },
  { path: "/install", intent: "docs", label: "Install AIdenID on a website, step by step" },
  { path: "/trust", intent: "trust", label: "Check signatures, consent, provenance and receipts" },
  { path: "/savings", intent: "compare", label: "Measure what agent-ready pages save a store" },
  { path: "/report", intent: "learn", label: "Find the requests going nowhere in a site's own logs (free report)" },
  { path: "/about", intent: "learn", label: "Meet the company and the team" },
];

export function intentLabel(id: IntentId): string {
  return BY_ID.get(id)?.label ?? "do something else";
}

/** An intent id as written in a link, or free text sorted by keyword. The text itself is never returned. */
export function classifyIntent(raw: string | null): IntentId | null {
  const text = (raw ?? "").normalize("NFKC").replace(/[\u0000-\u001f\u007f-\u009f]/g, " ").trim().slice(0, MAX_INTENT_CHARS);
  if (!text) return null;
  return (BY_ID.get(text.toLowerCase()) ?? INTENTS.find(intent => intent.words?.test(text)) ?? BY_ID.get("other")!).id;
}

/** The answer a request carries: a link's ?intent=, or the intent field of a small posted form. A posted body is read
 *  chunk by chunk, checking the deadline and a read count before every read so empty chunks cannot hold it open, and is
 *  abandoned the moment it passes its declared length. It counts only when it is exactly as long as declared. */
export async function declaredText(request: Request, deadlineMs = 2000): Promise<string | null> {
  if (request.method !== "POST") return new URL(request.url).searchParams.get(INTENT_PARAM);
  const length = request.headers.get("content-length") ?? "";
  if (!/^application\/x-www-form-urlencoded(?:;|$)/i.test(request.headers.get("content-type") ?? "") || !/^[0-9]{1,4}$/.test(length) || !request.body) return null;
  const declared = Number(length);
  if (declared < 1 || declared > MAX_FORM_BYTES) return null;
  const reader = request.body.getReader();
  const deadline = Date.now() + deadlineMs;
  const chunks: Uint8Array[] = [];
  let total = 0;
  let finished = false;
  try {
    for (let reads = 0; reads < MAX_FORM_READS; reads++) {
      const remaining = deadline - Date.now();
      if (remaining <= 0) return null;
      let timer: ReturnType<typeof setTimeout> | undefined;
      const late = new Promise<null>(resolve => { timer = setTimeout(() => resolve(null), remaining); });
      const chunk = await Promise.race([reader.read(), late]).finally(() => clearTimeout(timer));
      if (chunk === null) return null;
      if (chunk.done) { finished = true; break; }
      if (total + chunk.value.byteLength > declared) return null;
      chunks.push(chunk.value);
      total += chunk.value.byteLength;
    }
  } catch {
    return null;
  } finally {
    if (!finished) void reader.cancel().catch(() => undefined);
  }
  if (!finished || total !== declared) return null;
  const bytes = new Uint8Array(total);
  let at = 0;
  for (const chunk of chunks) { bytes.set(chunk, at); at += chunk.byteLength; }
  return new URLSearchParams(new TextDecoder().decode(bytes)).get(INTENT_PARAM);
}

const encoder = new TextEncoder();
async function mac(secret: string, message: string): Promise<string> {
  const key = await crypto.subtle.importKey("raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const signed = new Uint8Array(await crypto.subtle.sign("HMAC", key, encoder.encode(message)));
  return Array.from(signed, byte => byte.toString(16).padStart(2, "0")).join("");
}

/** Who a declaration belongs to: this site and this user agent. */
export function agentBinding(request: Request, secret: string, site: string): Promise<string> {
  return mac(secret, JSON.stringify(["aidenid-intent-binding-v1", site, (request.headers.get("user-agent") ?? "").slice(0, 1024)]));
}

export async function sessionToken(secret: string, binding: string, intent: IntentId, now: number): Promise<string> {
  const payload = `${intent}.${Math.floor(now / 1000) + SESSION_SECONDS}`;
  return `${payload}.${(await mac(secret, `aidenid-intent-session-v1|${binding}|${payload}`)).slice(0, 32)}`;
}

/** The declared intent, if the token was issued for this same agent and has not expired. */
export async function readSession(secret: string, binding: string, token: string, now: number): Promise<IntentId | null> {
  const match = /^([a-z]{1,16})\.(\d{1,12})\.([0-9a-f]{32})$/.exec(token);
  if (!match || !BY_ID.has(match[1]!) || Number(match[2]) * 1000 <= now) return null;
  const expected = (await mac(secret, `aidenid-intent-session-v1|${binding}|${match[1]}.${match[2]}`)).slice(0, 32);
  let diff = 0;
  for (let i = 0; i < expected.length; i++) diff |= expected.charCodeAt(i) ^ match[3]!.charCodeAt(i);
  return diff === 0 ? match[1] as IntentId : null;
}

/** The tokens a request carries: in its address (agents without cookies), then in its cookie. */
export function heldTokens(request: Request): string[] {
  const fromUrl = new URL(request.url).searchParams.get(SESSION_PARAM);
  const cookie = (request.headers.get("cookie") ?? "").split(";").map(part => part.trim()).find(part => part.startsWith(`${SESSION_PARAM}=`));
  return [fromUrl, cookie?.slice(SESSION_PARAM.length + 1)].filter((token): token is string => !!token);
}

/** The address the gate's own links and form point back to: a path on this site, never another host. A request
 *  for //other.example/x (or /\other.example/x) keeps its path here instead of becoming a protocol-relative link. */
export function gatePath(url: URL): string {
  const resolved = new URL(url.pathname.replace(/^[/\\]+/, "/"), url.origin);
  return resolved.origin === url.origin ? resolved.pathname : "/";
}

const escapeHtml = (value: string) => value.replace(/[&<>"']/g, char => `&#${char.charCodeAt(0)};`);
const STYLE = `body{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;max-width:52rem;margin:0 auto;padding:2rem 1.5rem;background:#0a0a0b;color:#e4e5e4;line-height:1.6;overflow-wrap:anywhere}a{color:#1fdc4d;text-underline-offset:3px}li{margin:.4rem 0}label{display:block;font-weight:600}input,button{font:inherit;padding:.6rem .8rem;border-radius:6px}input{width:100%;box-sizing:border-box;margin:.5rem 0;border:1px solid rgba(255,255,255,.25);background:#141416;color:#f4f5f4}button{border:0;background:#1fdc4d;color:#0a0a0b;cursor:pointer}code{background:rgba(255,255,255,.06);padding:.15em .4em;border-radius:4px}`;

/** The question, at the address the agent asked for: a text entry for assistants, everything they can do for crawlers.
 *  Every link is absolute, because some agents can only open addresses that appear in full on a page they read. */
export function gatePage(origin: string, path: string, audience: "assistant" | "crawler"): string {
  const site = escapeHtml(origin);
  const here = site + escapeHtml(path);
  const ask = audience === "crawler"
    ? `<h2>Everything you can do here</h2><ul>${EVERYTHING.map(item => `<li><a href="${site}${escapeHtml(item.path)}?${INTENT_PARAM}=${item.intent}">${escapeHtml(item.label)}</a></li>`).join("")}</ul>
<p>Here for something else? Follow the link that comes closest.</p>`
    : `<form method="post" action="${here}"><label for="intent">In your own words</label><input id="intent" name="${INTENT_PARAM}" maxlength="${MAX_INTENT_CHARS}" required placeholder="For example: buy running shoes for my user"><button type="submit">Continue</button></form>
<h2>Or pick one</h2><ul>${INTENTS.map(intent => `<li><a href="${here}?${INTENT_PARAM}=${intent.id}">I am here to ${escapeHtml(intent.label)}</a></li>`).join("")}</ul>
<p>If you can only follow links, pick the one that comes closest.</p>`;
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AIdenID: what are you here to do?</title><meta name="robots" content="noindex, follow"><style>${STYLE}</style></head>
<body><main><h1>Before you continue: what are you here to do?</h1>
<p>AIdenID asks every AI agent what it came to do, the way a sign-in page asks a person who they are. Your answer shapes the page you get and lasts one hour.</p>
${ask}
<p>Do not include personal details. We record the category of your answer with your visit, not your words.</p>
</main></body></html>`;
}

/** The line at the top of an agent view, so the agent knows what it is reading and why. */
export function intentNote(intent: IntentId): string {
  return `<p data-aidenid-intent="${intent}"><strong>You told us you are here to ${escapeHtml(intentLabel(intent))}.</strong> This version of the page is written for AI agents: plain HTML, no scripts, with the facts and links an agent needs to finish. Its links keep your answer for one hour. To change it, open any page with <code>?${INTENT_PARAM}=</code> and one of: ${INTENTS.map(item => item.id).join(", ")}.</p>`;
}

/** The note goes first in the page body (or first in the document when there is no body tag). */
export function withIntentNote(html: string, intent: IntentId): string {
  const body = /<body\b[^>]*>/i.exec(html);
  if (!body) return intentNote(intent) + html;
  const at = body.index + body[0].length;
  return html.slice(0, at) + intentNote(intent) + html.slice(at);
}

// Addresses that are never gated pages: the session token has no business in them.
const UNGATED = /^\/(?:api|cdn-cgi|\.well-known|assets)\/|\.[a-z0-9]+$/i;

/** Links to this site become absolute, for agents that can only open addresses written out in full, and links to its
 *  pages also carry the session, so following one needs no new declaration. A link changes only
 *  when it plainly names this site: a single leading slash or this site's own origin, with no character reference,
 *  backslash or whitespace that a browser could read as another host. Anything else is left alone, so the token
 *  never travels anywhere but here. */
export function withSession(html: string, token: string, origin: string): string {
  const hosts = new Set([origin, origin.replace("://www.", "://"), origin.replace("://", "://www.")]);
  return html.replace(/<a\b[^>]*>/gi, tag => tag.replace(/(\shref=)(["'])([^"']*)\2/i, (attribute, name: string, quote: string, href: string) => {
    if (/[\\\s]|&(?!amp;)/.test(href)) return attribute;
    const host = [...hosts].find(candidate => href.startsWith(`${candidate}/`));
    const local = host ? href.slice(host.length) : href;
    let resolved: URL;
    try { resolved = new URL(local.replaceAll("&amp;", "&"), origin); } catch { return attribute; }
    if (!local.startsWith("/") || !hosts.has(resolved.origin)) return attribute;
    const hash = local.indexOf("#");
    const target = hash < 0 ? local : local.slice(0, hash);
    // Files and APIs become absolute too, so an agent can follow them, but only pages carry the session.
    const page = !UNGATED.test(target.split("?")[0]!) && !new RegExp(`[?&](?:amp;)?${SESSION_PARAM}=`).test(target);
    const joined = page ? `${target}${target.includes("?") ? "&amp;" : "?"}${SESSION_PARAM}=${token}` : target;
    return `${name}${quote}${host ?? origin}${joined}${hash < 0 ? "" : local.slice(hash)}${quote}`;
  }));
}

export type IntentStep = "agent_intent_ask" | "agent_intent_answered";
/** What an answer records about itself (the collector's intent-declaration contract): the category, whether it came
 *  from a preset link or the agent's own words, and when it was given and expires. Never the words, never authority. */
export type IntentDeclaration = {
  category: IntentId;
  source: "declared_preset" | "declared_text";
  classifierVersion: "intent-gate-v1";
  declaredAt: string;
  expiresAt: string;
};
export type IntentGateDeps = {
  secret: string;
  site: string;
  now: number;
  /** Learning crawlers get the list of everything they can do; every other agent gets the text entry. */
  audience: "assistant" | "crawler";
  /** The public address the gate's links and form point at; by default the address the agent asked for. */
  path?: string;
  /** The agent view of the address the agent asked for; `recorded` is false when an answer's record already covers it,
   *  and for HEAD, which records nothing. */
  view: (recorded: boolean) => Promise<Response>;
  /** The flight record of this step. An answer is recorded as its category label, never the agent's words. */
  record: (step: IntentStep, detail: { ask?: string; answer?: string; declaration?: IntentDeclaration }) => void;
};

const GATE_HEADERS = {
  "Content-Type": "text/html; charset=utf-8", "Cache-Control": AGENT_RESPONSE_CACHE, "X-Robots-Tag": "noindex",
  "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff",
  "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
};

/** Ask an agent without a declaration; otherwise serve its view, noted with what it declared. A posted answer is
 *  followed by a redirect to the same page, so a browser agent lands on an ordinary address it can reload. Each
 *  request makes one flight record at most, and a HEAD request (a link check) declares and records nothing. */
export async function intentGate(request: Request, deps: IntentGateDeps): Promise<Response> {
  const url = new URL(request.url);
  const here = deps.path ?? gatePath(url);
  const binding = await agentBinding(request, deps.secret, deps.site);
  const answer = request.method === "HEAD" ? null : await declaredText(request);
  const declared = classifyIntent(answer);
  let intent: IntentId | null = declared;
  let token = declared ? await sessionToken(deps.secret, binding, declared, deps.now) : null;
  for (const held of declared ? [] : heldTokens(request)) {
    intent = await readSession(deps.secret, binding, held, deps.now);
    if (intent) { token = held; break; }
  }
  if (!intent || !token) {
    if (request.method !== "HEAD") deps.record("agent_intent_ask", { ask: GATE_QUESTION });
    return new Response(request.method === "HEAD" ? null : gatePage(url.origin, here, deps.audience), { status: 200, headers: GATE_HEADERS });
  }
  if (declared) {
    const preset = BY_ID.has((answer ?? "").normalize("NFKC").trim().toLowerCase());
    deps.record("agent_intent_answered", {
      answer: intentLabel(declared),
      declaration: {
        category: declared, source: preset ? "declared_preset" : "declared_text", classifierVersion: "intent-gate-v1",
        declaredAt: new Date(deps.now).toISOString(), expiresAt: new Date((Math.floor(deps.now / 1000) + SESSION_SECONDS) * 1000).toISOString(),
      },
    });
  }
  const cookie = `${SESSION_PARAM}=${token}; Path=/; Max-Age=${SESSION_SECONDS}; Secure; HttpOnly; SameSite=Lax`;
  if (request.method === "POST") {
    return new Response(null, { status: 303, headers: { Location: `${url.origin}${here}?${SESSION_PARAM}=${token}`, "Set-Cookie": cookie, "Cache-Control": AGENT_RESPONSE_CACHE, "Referrer-Policy": "no-referrer" } });
  }
  const view = await deps.view(!declared && request.method !== "HEAD");
  const headers = new Headers(view.headers);
  if (declared) headers.append("Set-Cookie", cookie);
  if (request.method === "HEAD" || !/^text\/html/i.test(headers.get("content-type") ?? "")) {
    return new Response(request.method === "HEAD" ? null : view.body, { status: view.status, headers });
  }
  headers.delete("Content-Length");
  return new Response(withSession(withIntentNote(await view.text(), intent), token, url.origin), { status: view.status, headers });
}
