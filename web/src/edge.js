import { classifyRequest, verifyWebBotAuth } from "./generated/aidenid-classifier/index.js";
import { serveAgentVersion, varyWith } from "./agent-view.js";
import { observationFor } from "./vendor/aidenid-registry/agent-registry.mjs";

const AGENT_CLASSES = new Set(["verified_agent", "signed_agent", "declared_agent", "crawler_claimed", "automation"]);
const CLASSIFY_TIMEOUT_MS = 300;
const INGEST_TIMEOUT_MS = 1200;
const INGEST_URL = "https://aquarium.internal/api/aquarium/edge";
const HUMAN_COOKIE = "sl_view=human; Max-Age=1800; Path=/; Secure; SameSite=Lax";
const VARY = ["User-Agent", "Accept", "Signature", "Signature-Input", "Signature-Agent", "Cookie",
  "Accept-Language", "Sec-Fetch-Mode", "Sec-Fetch-Dest", "Sec-Fetch-Site", "Sec-CH-UA", "Sec-CH-UA-Mobile",
  "Sec-CH-UA-Platform", "Referer"];

// A peer that ignores AbortSignal must not keep a background task alive forever.
async function bounded(task, ms) {
  const controller = new AbortController();
  let timer;
  try {
    return await Promise.race([
      Promise.resolve().then(() => task(controller.signal)),
      new Promise((_, reject) => { timer = setTimeout(() => {
        controller.abort();
        reject(new Error("edge timeout"));
      }, ms); }),
    ]);
  } finally {
    clearTimeout(timer);
  }
}

async function identify(request) {
  const identity = classifyRequest(request);
  if (!request.headers.has("signature-input")) return identity;
  const signed = await verifyWebBotAuth(request);
  if (signed.reason?.startsWith("directory_") || signed.reason === "verification_unavailable") return null;
  if (!signed.verified) return identity;
  const known = signed.operator !== "unknown";
  const { method, components, signer, keyid } = signed.verification;
  return { ...identity, operator: signed.operator, label: signed.label, basis: signed.basis,
    confidence: 1, verified: true, status: "verified", verification: { method, components, signer, keyid },
    triage: { ...identity.triage, hard: [], soft: [], class: known ? "verified_agent" : "signed_agent",
      step: "T0", reasons: [known ? "web_bot_auth_verified" : "signature_valid"] } };
}

function audience(identity) {
  if (AGENT_CLASSES.has(identity?.triage?.class)) return "agent";
  return identity?.triage?.class === "unknown" ? "unknown" : "human";
}

async function safelyIdentify(request, env, classifier) {
  try { return await bounded(() => classifier(request, env), CLASSIFY_TIMEOUT_MS); }
  catch { return null; }
}

export async function classify(request, env) {
  return audience(await safelyIdentify(request, env, identify));
}

function privateResponse(response, setHumanCookie) {
  const headers = new Headers(response.headers);
  headers.set("vary", varyWith(headers.get("vary"), VARY));
  // CF metadata and header count also affect the classifier; Vary alone is insufficient.
  headers.set("cache-control", "private, no-store");
  if (setHumanCookie) headers.append("set-cookie", HUMAN_COOKIE);
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
}

// Keep the actual public page path. Never relabel this site's visits as AIdenID pages.
function publicPage(pathname) {
  if (["/", "/index.html", "/agents/index.md"].includes(pathname)) return pathname;
  if (["/sentilab", "/sentilab/", "/sentilab/index.html", "/sentilab/package", "/sentilab/package/",
    "/sentilab/package/index.html"].includes(pathname)) return pathname;
  return null;
}

async function observe(request, env, identity) {
  try {
    if (!env.COLLECTOR || !env.INGEST_TOKEN || !["GET", "HEAD"].includes(request.method)) return;
    const page = publicPage(new URL(request.url).pathname);
    if (!page) return;
    const observation = observationFor({ triageClass: identity.triage.class, basis: identity.basis,
      userAgent: request.headers.get("user-agent") ?? "", signer: identity.verification?.signer,
      cfBotCategory: request.cf?.verifiedBotCategory });
    // Future collector contract: keep posting OFF until it retains siteId and these real paths.
    const event = { schemaVersion: 1, siteId: "sentilab", sessionId: crypto.randomUUID(), source: "edge", eventType: "page_view",
      path: page, method: request.method, identity: { ...identity, observation } };
    await bounded((signal) => env.COLLECTOR.fetch(INGEST_URL, {
      method: "POST", redirect: "manual", signal,
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${env.INGEST_TOKEN}` },
      body: JSON.stringify(event),
    }), INGEST_TIMEOUT_MS);
  } catch { /* Observation cannot affect the response, including on timeout or bad configuration. */ }
}

export async function withEdge(request, env, ctx, { agentPathFor, serve, serveAgent = serveAgentVersion, serveHuman = serve, classifier = identify }) {
  const url = new URL(request.url);
  const setHumanCookie = url.searchParams.get("view") === "human";
  const humanCookie = (request.headers.get("cookie") || "").split(";").some((part) => part.trim() === "sl_view=human");
  let identity = null;
  let response;
  let forceHuman = setHumanCookie || humanCookie;
  let mapped = false;
  try {
    const path = agentPathFor(url.pathname);
    if (path !== null) {
      mapped = ["GET", "HEAD"].includes(request.method);
      if (typeof path !== "string" || !path.startsWith("/") || path.startsWith("//")) throw new Error("invalid agent path");
      const target = new URL(path, url);
      if (target.origin !== url.origin || target.search || target.hash) throw new Error("invalid agent path");
    }
  } catch { mapped = ["GET", "HEAD"].includes(request.method); forceHuman = true; }
  if (!forceHuman) {
    identity = await safelyIdentify(request, env, classifier);
    forceHuman = identity === null;
    if (audience(identity) === "agent") {
      try {
        const routed = await serveAgent(request, env);
        if (routed?.ok || routed?.status === 304) response = routed;
        else if (routed) {
          forceHuman = true;
          await routed.body?.cancel();
        }
      } catch { forceHuman = true; /* A failed agent version falls back to the human page. */ }
    }
  }
  if (!response && !forceHuman) {
    try { response = await serve(request, env); }
    catch { /* Failed content negotiation also falls back to the original asset. */ }
  }
  response ??= await (mapped ? serveHuman : serve)(request, env);
  try {
    if (audience(identity) === "agent" && env.AQUARIUM_POST === "on" && typeof ctx?.waitUntil === "function") {
      ctx.waitUntil(observe(request, env, identity));
    }
  } catch { /* Local/misconfigured execution contexts must not break a page. */ }
  return mapped || setHumanCookie ? privateResponse(response, setHumanCookie) : response;
}
