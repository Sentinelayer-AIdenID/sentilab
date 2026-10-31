// deterministicTriage, classifyRequest, operatorFromHint.
// Pure functions: no env, no network, no side effects.
// Order matches aquarium-edge/src/index.ts exactly — this is the same logic.

                                                                                
import { OPERATOR_PATTERNS, SCRIPT_TOOLS, HEADLESS_CLIENT_HINT, SELF_DECLARED, genericBotWord } from "./recognized-automation.js";
import { describeRequest } from "./describe-request.js";

const VENDOR_WORDS = /openai|chatgpt|gpt|anthropic|claude|google|perplexity|microsoft|bing|meta|facebook|apple|amazon|bytedance|cloudflare/i;
const OPERATOR_NAMES                         = {
  openai: "OpenAI", anthropic: "Anthropic", google: "Google", perplexity: "Perplexity", microsoft: "Microsoft",
  meta: "Meta", apple: "Apple", amazon: "Amazon", bytedance: "ByteDance", commoncrawl: "Common Crawl",
  deepseek: "DeepSeek",
};

function toolToken(ua        )         {
  const m = SCRIPT_TOOLS.exec(ua);
  return (m?.[1] ?? "script").toLowerCase().slice(0, 24);
}

function clientWord(word        )                {
  const bounded = word.slice(0, 24);
  return VENDOR_WORDS.test(bounded) ? null : bounded;
}

const INCOMPLETE_WEBKIT_SHELL = /\bMozilla\/5\.0\b.*\bAppleWebKit\/\d+(?:\.\d+)*\s*$/i;
const DATACENTER = /amazon|aws|google cloud|google llc|microsoft|azure|digitalocean|hetzner|ovh|linode|akamai|vultr|oracle|alibaba|tencent|choopa|m247|leaseweb|contabo|scaleway|fly\.io|cloudflare|datacamp|serverius|hostinger|godaddy|namecheap|ionos|upcloud|equinix|packethost|psychz|quadranet|zenlayer/i;

                                                     
const SEC_FETCH_MIN                              = { chromium: 76, firefox: 90, safari: 16 };
const CLIENT_HINTS_MIN = 89;
const H2_MIN                              = { chromium: 80, firefox: 80, safari: 14 };
const PLAUSIBLE                                        = { chromium: [60, 170], firefox: [60, 170], safari: [10, 30] };
const OPERATORS = OPERATOR_PATTERNS;

export function operatorFromHint(hint                    , confidence                    )                {
  if (!hint || typeof confidence !== "number" || confidence < 0.6) return null;
  if (OPERATOR_NAMES[hint]) return `resembles ${OPERATOR_NAMES[hint]}`;
  if (hint === "scraper") return "likely scraper";
  if (hint === "search_engine") return "likely crawler";
  if (hint === "other_ai_vendor") return "likely AI agent";
  return null;
}

function identity(partial                                                                         )               {
  return { verified: false, confidence: 0, ...partial };
}

export function deterministicTriage(vector               )               {
  const base         = { family: vector.family, uaMajor: vector.uaMajor, hard: []            , soft: []            , reasons: []            , class: "unknown", step: "T3" };

  // Cloudflare's verified-bot bit is a network classification.
  if (vector.verifiedBot) {
    const named = (OPERATORS                                               ).find(([pattern]) => pattern.test(vector.ua));
    return identity({
      operator: "unknown", label: named ? `${(named                                       )[2]} · verified crawler` : "Verified crawler",
      basis: "cloudflare_verified_bot", confidence: 1,
      triage: { ...base, class: "crawler_claimed", step: "T1", reasons: ["cloudflare_verified_bot"] },
    });
  }
  if (!vector.ua.trim()) {
    return identity({ operator: "unknown", label: "Script · no user agent", basis: "user_agent", confidence: 0.9,
      triage: { ...base, class: "automation", step: "T1", reasons: ["empty_user_agent"] } });
  }
  for (const [pattern, operator, name, kind] of OPERATORS                                                 ) {
    if (pattern.test(vector.ua)) {
      return identity({ operator: operator            , label: kind === "search" ? `${name} · claimed crawler` : `${name} · declared`, basis: "user_agent", confidence: 0.5,
        triage: { ...base, class: kind === "search" ? "crawler_claimed" : "declared_agent", step: "T1", reasons: ["declared_user_agent"] } });
    }
  }
  if (SCRIPT_TOOLS.test(vector.ua)) {
    return identity({ operator: "unknown", label: `Script · ${toolToken(vector.ua)}`, basis: "user_agent", confidence: 0.9,
      triage: { ...base, class: "automation", step: "T1", reasons: ["script_tool_user_agent"] } });
  }
  // A request that carries HTTP Message Signature headers is an agent announcing itself.
  // When T0 cannot verify the signature it stays a claim, visibly.
  if (vector.signatureAgent) {
    const host = vector.signatureAgent.replace(/^"|"$/g, "").replace(/^https?:\/\//, "").split("/")[0]?.toLowerCase() ?? "";
    const operator           = /(^|\.)chatgpt\.com$|(^|\.)openai\.com$/.test(host) ? "openai" : /(^|\.)anthropic\.com$|(^|\.)claude\.ai$/.test(host) ? "anthropic" : "unknown";
    const who = operator === "unknown" ? (clientWord(host) || "unknown signer") : OPERATOR_NAMES[operator];
    return identity({ operator, label: `${who} · signed claim, not verified`, basis: "user_agent", confidence: 0.6,
      triage: { ...base, class: "declared_agent", step: "T1", reasons: ["signature_claim_unverified"] } });
  }
  const generic = vector.family === "other" ? genericBotWord(vector.ua) : null;
  if (generic) {
    const word = clientWord(generic);
    return identity({ operator: "unknown", label: word ? `Bot · ${word}` : "Bot · (vendor name refused)", basis: "user_agent", confidence: 0.7,
      triage: { ...base, class: "automation", step: "T1", reasons: ["generic_bot_token"] } });
  }
  const declared = vector.family === "other" ? SELF_DECLARED.exec(vector.ua) : null;
  if (declared) {
    const word = clientWord(declared[1] ?? "bot");
    const label = word ? `Bot · ${word} · self-declared` : "Bot · self-declared (vendor name refused)";
    return identity({ operator: "unknown", label, basis: "user_agent", confidence: 0.8,
      triage: { ...base, class: "automation", step: "T1", reasons: ["self_declared_bot"] } });
  }
  if (vector.secChUa && HEADLESS_CLIENT_HINT.test(vector.secChUa)) {
    return identity({ operator: "unknown", label: "Headless browser - Chromium client hint", basis: "request_shape", confidence: 0.95,
      triage: { ...base, hard: ["headless_client_hint"], soft: [], class: "automation", step: "T3", reasons: ["headless_client_hint"] } });
  }
  if (vector.family === "other" && INCOMPLETE_WEBKIT_SHELL.test(vector.ua)) {
    return identity({ operator: "unknown", label: "Browser shell - incomplete user agent", basis: "request_shape", confidence: 0.9,
      triage: { ...base, hard: ["incomplete_browser_user_agent"], class: "automation", step: "T3", reasons: ["incomplete_browser_user_agent"] } });
  }

  // T3: browser shape contradictions
  if (vector.family === "chromium" || vector.family === "firefox" || vector.family === "safari") {
    const family              = vector.family;
    const major = vector.uaMajor ?? 999;
    const hard           = [];
    const soft           = [];
    const navigation = (!vector.secFetchDest || vector.secFetchDest === "document") && (!vector.secFetchMode || vector.secFetchMode === "navigate");
    if (major >= SEC_FETCH_MIN[family] && (!vector.secFetchMode || !vector.secFetchDest)) hard.push("missing_sec_fetch");
    if (family === "chromium" && major >= CLIENT_HINTS_MIN && !vector.secChUa) hard.push("missing_client_hints");
    if (vector.secChUa && vector.chMajor !== undefined && vector.uaMajor !== undefined && vector.chMajor !== vector.uaMajor) hard.push("client_hints_version_mismatch");
    if (vector.secChUaMobile && ((vector.secChUaMobile === "?1") !== vector.mobile)) soft.push("client_hints_mobile_mismatch");
    if (navigation) {
      if (!vector.accept || !/text\/html/i.test(vector.accept)) hard.push("accept_not_html");
      if (!vector.acceptLanguage) hard.push("missing_accept_language");
    }
    if (vector.httpProtocol && /^HTTP\/1\./i.test(vector.httpProtocol) && major >= H2_MIN[family]) hard.push("http1_with_modern_browser");
    if (vector.tlsVersion && /^TLSv1(\.0|\.1)?$/i.test(vector.tlsVersion)) hard.push("legacy_tls");
    if (vector.headerCount <= 4) hard.push("too_few_headers");
    else if (vector.headerCount <= 6) soft.push("sparse_headers");
    if (vector.asOrganization && DATACENTER.test(vector.asOrganization)) soft.push("datacenter_network");
    if (vector.uaMajor !== undefined && (vector.uaMajor < PLAUSIBLE[family][0] || vector.uaMajor > PLAUSIBLE[family][1])) soft.push("implausible_browser_version");
    if (vector.uaMajor !== undefined && major < SEC_FETCH_MIN[family]) soft.push("old_browser_version");

    if (vector.cloudflareBotScore === 1) {
      hard.push("cloudflare_bot_score_automated");
      return identity({ operator: "unknown", label: `Automation - ${vector.family} browser risk`, basis: "request_shape", confidence: 0.9,
        triage: { ...base, hard, soft, class: "automation", step: "T3", reasons: ["cloudflare_bot_score_automated"] } });
    }
    if (vector.cloudflareBotScore !== undefined && vector.cloudflareBotScore <= 29 && (hard.length > 0 || soft.length > 0)) {
      soft.push("cloudflare_bot_score_likely_automated");
    }

    if (hard.length >= 2) {
      return identity({ operator: "unknown", label: `Headless browser · ${vector.family} shell`, basis: "request_shape", confidence: 0.85,
        triage: { ...base, hard, soft, class: "automation", step: "T3", reasons: ["browser_shape_contradictions"] } });
    }
    if (hard.length === 0 && soft.length === 0) {
      return identity({ operator: "unknown", label: `Browser visitor · ${vector.family}`, basis: "request_shape", confidence: 0.8,
        triage: { ...base, hard, soft, class: "likely_human", step: "T3", reasons: ["consistent_browser_shape"] } });
    }
    return identity({ operator: "unknown", label: "Unresolved · browser shape in doubt", basis: "unknown", confidence: 0,
      triage: { ...base, hard, soft, class: "unknown", step: "T3", reasons: ["browser_shape_in_doubt"] } });
  }

  const soft = vector.asOrganization && DATACENTER.test(vector.asOrganization) ? ["datacenter_network"] : [];
  return identity({ operator: "unknown", label: "Unresolved · unrecognized client", basis: "unknown", confidence: 0,
    triage: { ...base, soft, class: "unknown", step: "T3", reasons: ["unrecognized_user_agent"] } });
}

export function classifyRequest(request         )               {
  return deterministicTriage(describeRequest(request));
}
