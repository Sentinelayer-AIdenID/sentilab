// The deterministic signals by which a request announces itself as automation.
// Extracted from shared/recognized-automation.mjs for the classifier package.

export const OPERATOR_PATTERNS = Object.freeze([
  [/\bGPTBot\b/i, "openai", "GPTBot", "ai"],
  [/\bOAI-SearchBot\b/i, "openai", "OAI-SearchBot", "ai"],
  [/\bChatGPT-User\b/i, "openai", "ChatGPT-User", "ai"],
  [/\bClaudeBot\b/i, "anthropic", "ClaudeBot", "ai"],
  [/\bClaude-SearchBot\b/i, "anthropic", "Claude-SearchBot", "ai"],
  [/\bClaude-User\b/i, "anthropic", "Claude-User", "ai"],
  [/\banthropic-ai\b/i, "anthropic", "anthropic-ai", "ai"],
  [/\bPerplexityBot\b/i, "perplexity", "PerplexityBot", "ai"],
  [/\bPerplexity-User\b/i, "perplexity", "Perplexity-User", "ai"],
  [/\bGoogle-Agent\b/i, "google", "Google-Agent", "ai"],
  [/\bGoogle-Extended\b/i, "google", "Google-Extended", "ai"],
  [/\bGoogleOther\b/i, "google", "GoogleOther", "ai"],
  [/\bGooglebot\b/i, "google", "Googlebot", "search"],
  [/\bbingbot\b/i, "microsoft", "bingbot", "search"],
  [/\bApplebot\b/i, "apple", "Applebot", "search"],
  [/\bDuckDuckBot\b/i, "unknown", "DuckDuckBot", "search"],
  [/\bDuckAssistBot\b/i, "unknown", "DuckAssistBot", "ai"],
  [/\bmeta-externalagent\b/i, "meta", "Meta crawler", "ai"],
  [/\bmeta-externalfetcher\b/i, "meta", "Meta fetcher", "ai"],
  [/\bFacebookBot\b/i, "meta", "FacebookBot", "search"],
  [/\bAmazonbot\b/i, "amazon", "Amazonbot", "ai"],
  [/\bBytespider\b/i, "bytedance", "Bytespider", "ai"],
  [/\bCCBot\b/i, "commoncrawl", "CCBot", "ai"],
  [/\bcohere-ai\b/i, "unknown", "cohere-ai", "ai"],
  [/\bMistralAI-User\b/i, "unknown", "MistralAI-User", "ai"],
  [/\bYouBot\b/i, "unknown", "YouBot", "ai"],
  [/\bDiffbot\b/i, "unknown", "Diffbot", "ai"],
].map((row) => Object.freeze(row)));
export const SCRIPT_TOOLS = /\b(curl|wget|python-requests|python-urllib|aiohttp|httpx|Go-http-client|okhttp|Java|libwww-perl|Scrapy|node-fetch|undici|axios|HeadlessChrome|PhantomJS|Puppeteer|Playwright|Selenium|WebDriver|Apache-HttpClient|PostmanRuntime|insomnia|Dart|Faraday|RestSharp|Typhoeus|Nikto|sqlmap|masscan|zgrab)\b/i;
export const GENERIC_BOT = /(bot|crawl|spider|scrap|fetch|monitor|scanner|probe|validator|archiver)/i;
export const HEADLESS_CLIENT_HINT = /(?:^|,)\s*"HeadlessChrome"\s*;\s*v\s*=\s*"\d+(?:\.\d+)*"(?=\s*(?:;|,|$))/i;
export const SELF_DECLARED = /compatible;\s*([A-Za-z][A-Za-z0-9_.-]{1,39})\/[0-9][A-Za-z0-9.]*;?\s*\+\S+/i;

export function userAgentFamily(ua: string): { family: "chromium" | "firefox" | "safari" | "other" | "none"; major?: number; mobile: boolean } {
  if (!ua) return { family: "none", mobile: false };
  const mobile = /\bMobile\b|Android|iPhone|iPad/i.test(ua);
  const num = (re: RegExp) => { const r = re.exec(ua); return r ? Number(r[1]) : undefined; };
  if (/\b(?:CriOS|FxiOS|EdgiOS)\/\d/.test(ua)) return { family: "safari", major: num(/\bVersion\/(\d+)/) ?? num(/\b(?:CriOS|FxiOS|EdgiOS)\/(\d+)/), mobile };
  if (/\bFirefox\/\d/.test(ua) && !/\bSeaMonkey\//i.test(ua)) return { family: "firefox", major: num(/\bFirefox\/(\d+)/), mobile };
  if (/\bAppleWebKit\//.test(ua) && /\b(?:Chrome|Chromium|Edg|OPR|Brave|SamsungBrowser|YaBrowser|Vivaldi)\/\d/.test(ua)) {
    return { family: "chromium", major: num(/\b(?:Chrome|Chromium)\/(\d+)/) ?? num(/\b(?:Edg|OPR|SamsungBrowser|YaBrowser|Vivaldi)\/(\d+)/), mobile };
  }
  if (/\bAppleWebKit\//.test(ua) && /\bVersion\/\d/.test(ua) && /\bSafari\/\d/.test(ua)) return { family: "safari", major: num(/\bVersion\/(\d+)/), mobile };
  return { family: "other", mobile };
}

const CONTACT = /\+?(?:https?:\/\/|mailto:)\S+|\+?[\w.+-]+@[\w.-]+\.\w+/gi;
const WORD = /[A-Za-z][A-Za-z0-9_.-]*/g;
function productWords(ua: string): string[] {
  return (ua.replace(CONTACT, " ").match(WORD) ?? []).map((word) => word.replace(/[._-]+$/, "")).filter(Boolean);
}
export function genericBotWord(ua: string): string | null {
  return productWords(ua).find((word) => GENERIC_BOT.test(word)) ?? null;
}
