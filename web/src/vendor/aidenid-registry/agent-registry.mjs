/**
 * AGENT REGISTRY: one sourced table of the AI agents, crawlers and bots aidenid.com can name.
 *
 * Used by the edge (to say WHICH service a request claims to be, and its category) and by the
 * collector (to validate those fields and to serve the public /api/aquarium/registry list).
 *
 * Rules:
 * - A user-agent token is a CLAIM. Anyone can send it. `verification` says how strong our evidence is.
 * - Every entry cites the vendor's own documentation when one exists (`docs`); `docs: null` means
 *   the token is observed in the wild but its vendor publishes no page we could cite.
 * - `robotsOnly` tokens (Google-Extended, Applebot-Extended, Googlebot-News) never appear as an HTTP
 *   user agent: they are robots.txt controls only, listed so the public table is complete.
 * - Order matters: more specific tokens come before the general ones (Googlebot-Image before Googlebot).
 *
 * Sources checked 2026-10-27: Google crawler docs (common, special-case, user-triggered), OpenAI
 * bots page, Anthropic crawler article, Perplexity bots guide, Meta web-crawlers page.
 */

const GOOGLE_COMMON = "https://developers.google.com/crawling/docs/crawlers-fetchers/google-common-crawlers";
const GOOGLE_SPECIAL = "https://developers.google.com/crawling/docs/crawlers-fetchers/google-special-case-crawlers";
const GOOGLE_USER = "https://developers.google.com/crawling/docs/crawlers-fetchers/google-user-triggered-fetchers";
const OPENAI_BOTS = "https://developers.openai.com/api/docs/bots";
const ANTHROPIC_BOTS = "https://support.claude.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler";
const PERPLEXITY_BOTS = "https://docs.perplexity.ai/guides/bots";
const META_CRAWLERS = "https://developers.facebook.com/docs/sharing/webmasters/web-crawlers/";

export const CATEGORIES = Object.freeze([
  { id: "training_crawler", name: "Training crawler", description: "Collects pages that may be used to train AI models." },
  { id: "search_crawler", name: "Search & index crawler", description: "Builds a search, shopping or AI-search index so pages can be found and cited." },
  { id: "ai_assistant", name: "AI assistant fetch", description: "Fetches a page because a person asked an assistant something right now." },
  { id: "ai_agent", name: "AI agent", description: "Browses or acts on a person's behalf, often in a real browser." },
  { id: "preview_bot", name: "Link preview", description: "Builds the preview card when a link is shared in a chat or social app." },
  { id: "monitor", name: "Monitoring & SEO tool", description: "Uptime, ads-quality, SEO and site-audit tools." },
  { id: "automation", name: "Scripts & headless automation", description: "Scripts, HTTP libraries and headless browsers that do not say who runs them." },
  { id: "unknown", name: "Unresolved", description: "Not enough evidence either way." },
  { id: "human", name: "Likely human (count only)", description: "Looks like a person in a browser. Never listed one by one." },
]);
export const CATEGORY_IDS = new Set(CATEGORIES.map((category) => category.id));

/** How strong the identity evidence is, strongest first. */
export const VERIFICATION_LEVELS = Object.freeze(["signature", "network", "claimed", "inferred", "unverified"]);
const VERIFICATION_SET = new Set(VERIFICATION_LEVELS);

// [id, operator, operatorName, name, category, token, docs, verifiableBy, description, robotsOnly]
const ROWS = [
  // ---- Google: user-triggered agents and fetchers (most specific first) ----
  ["google.agent", "google", "Google", "Google-Agent", "ai_agent", "Google-Agent", GOOGLE_USER, ["signature", "network"], "Agents hosted on Google infrastructure that browse and act on a user's request. Some requests are signed (Web Bot Auth, https://agent.bot.goog)."],
  ["google.read-aloud", "google", "Google", "Google Read Aloud", "ai_assistant", "Google-Read-Aloud", GOOGLE_USER, ["network"], "Reads a page aloud when a user asks."],
  ["google.gemini-notebook", "google", "Google", "Gemini Notebook", "ai_assistant", "Google-GeminiNotebook", GOOGLE_USER, ["network"], "Fetches pages a user added as sources to a Gemini Notebook project."],
  ["google.notebooklm", "google", "Google", "NotebookLM (former token)", "ai_assistant", "Google-NotebookLM", GOOGLE_USER, ["network"], "Former token of Gemini Notebook, supported until August 2026."],
  ["google.pinpoint", "google", "Google", "Google Pinpoint", "ai_assistant", "Google-Pinpoint", GOOGLE_USER, ["network"], "Fetches pages a user added to a Pinpoint document collection."],
  ["google.feedfetcher", "google", "Google", "Feedfetcher", "search_crawler", "FeedFetcher-Google", GOOGLE_USER, ["network"], "Fetches RSS and Atom feeds for Google News and WebSub."],
  ["google.producer", "google", "Google", "Google Publisher Center", "search_crawler", "GoogleProducer", GOOGLE_USER, ["network"], "Fetches feeds publishers supplied for Google News landing pages."],
  ["google.site-verification", "google", "Google", "Google Site Verifier", "monitor", "Google-Site-Verification", GOOGLE_USER, ["network"], "Fetches Search Console verification tokens."],
  ["google.cws", "google", "Google", "Chrome Web Store", "monitor", "Google-CWS", GOOGLE_USER, ["network"], "Fetches URLs developers list in Chrome extension metadata."],
  ["google.messages", "google", "Google", "Google Messages", "preview_bot", "GoogleMessages", GOOGLE_USER, ["network"], "Builds link previews for URLs sent in Google Messages chats."],
  // ---- Google: special-case crawlers ----
  ["google.adsbot-mobile", "google", "Google", "AdsBot Mobile Web", "monitor", "AdsBot-Google-Mobile", GOOGLE_SPECIAL, ["network"], "Google Ads checks page ad quality from a mobile user agent."],
  ["google.adsbot", "google", "Google", "AdsBot", "monitor", "AdsBot-Google", GOOGLE_SPECIAL, ["network"], "Google Ads checks page ad quality."],
  ["google.mediapartners", "google", "Google", "Mediapartners-Google", "monitor", "Mediapartners-Google", GOOGLE_SPECIAL, ["network"], "Crawls sites in Google ad programs to match ads."],
  ["google.apis", "google", "Google", "APIs-Google", "monitor", "APIs-Google", GOOGLE_SPECIAL, ["network"], "Delivers Google API push notifications."],
  ["google.safety", "google", "Google", "Google-Safety", "monitor", "Google-Safety", GOOGLE_SPECIAL, ["network"], "Anti-abuse crawling, such as malware checks on shared links."],
  // ---- Google: common crawlers ----
  ["google.inspectiontool", "google", "Google", "Google-InspectionTool", "monitor", "Google-InspectionTool", GOOGLE_COMMON, ["network"], "Search testing tools (Rich Results Test, Search Console URL inspection)."],
  ["google.cloudvertexbot", "google", "Google", "Google-CloudVertexBot", "search_crawler", "Google-CloudVertexBot", GOOGLE_COMMON, ["network"], "Crawls a site at its owner's request to build Vertex AI agents."],
  ["google.storebot", "google", "Google", "Google StoreBot", "search_crawler", "Storebot-Google", GOOGLE_COMMON, ["network"], "Crawls for Google Shopping surfaces."],
  ["google.googleother-image", "google", "Google", "GoogleOther-Image", "search_crawler", "GoogleOther-Image", GOOGLE_COMMON, ["network"], "GoogleOther variant for image URLs; not tied to one product."],
  ["google.googleother-video", "google", "Google", "GoogleOther-Video", "search_crawler", "GoogleOther-Video", GOOGLE_COMMON, ["network"], "GoogleOther variant for video URLs; not tied to one product."],
  ["google.googleother", "google", "Google", "GoogleOther", "search_crawler", "GoogleOther", GOOGLE_COMMON, ["network"], "General-purpose crawler for Google product teams (for example one-time R&D crawls)."],
  ["google.googlebot-image", "google", "Google", "Googlebot Image", "search_crawler", "Googlebot-Image", GOOGLE_COMMON, ["network"], "Crawls images for Google Images, Discover and image features in Search."],
  ["google.googlebot-video", "google", "Google", "Googlebot Video", "search_crawler", "Googlebot-Video", GOOGLE_COMMON, ["network"], "Crawls video for Search video features."],
  ["google.googlebot", "google", "Google", "Googlebot", "search_crawler", "Googlebot", GOOGLE_COMMON, ["network"], "Google Search's main crawler (also covers Discover and Google News)."],
  ["google.googlebot-news", "google", "Google", "Googlebot News (robots.txt only)", "search_crawler", "Googlebot-News", GOOGLE_COMMON, [], "robots.txt control for Google News; requests use ordinary Googlebot user agents.", true],
  ["google.extended", "google", "Google", "Google-Extended (robots.txt only)", "training_crawler", "Google-Extended", GOOGLE_COMMON, [], "robots.txt control over Gemini model training and grounding; never sent as a user agent.", true],
  // ---- OpenAI ----
  ["openai.chatgpt-agent", "openai", "OpenAI", "ChatGPT agent (signed)", "ai_agent", null, OPENAI_BOTS, ["signature"], "ChatGPT's agent mode browsing in a real browser. Identified only by its Web Bot Auth signature from https://chatgpt.com, never by user agent."],
  ["openai.searchbot", "openai", "OpenAI", "OAI-SearchBot", "search_crawler", "OAI-SearchBot", OPENAI_BOTS, ["network"], "Surfaces websites in ChatGPT search results."],
  ["openai.adsbot", "openai", "OpenAI", "OAI-AdsBot", "monitor", "OAI-AdsBot", OPENAI_BOTS, ["network"], "Checks pages submitted as ads on ChatGPT."],
  ["openai.gptbot", "openai", "OpenAI", "GPTBot", "training_crawler", "GPTBot", OPENAI_BOTS, ["network"], "Crawls content that may be used to train OpenAI's foundation models."],
  ["openai.chatgpt-user", "openai", "OpenAI", "ChatGPT-User", "ai_assistant", "ChatGPT-User", OPENAI_BOTS, ["network"], "Fetches a page when a ChatGPT or Custom GPT user's action needs it."],
  // ---- Anthropic ----
  ["anthropic.claude-searchbot", "anthropic", "Anthropic", "Claude-SearchBot", "search_crawler", "Claude-SearchBot", ANTHROPIC_BOTS, ["network"], "Improves search result quality for Claude users."],
  ["anthropic.claude-user", "anthropic", "Anthropic", "Claude-User", "ai_assistant", "Claude-User", ANTHROPIC_BOTS, ["network"], "Fetches a page when a person asks Claude something."],
  ["anthropic.claudebot", "anthropic", "Anthropic", "ClaudeBot", "training_crawler", "ClaudeBot", ANTHROPIC_BOTS, ["network"], "Collects web content that could contribute to model training."],
  ["anthropic.anthropic-ai", "anthropic", "Anthropic", "anthropic-ai (legacy token)", "training_crawler", "anthropic-ai", null, [], "Older Anthropic token still seen in the wild; not on Anthropic's current page."],
  // ---- Perplexity ----
  ["perplexity.perplexity-user", "perplexity", "Perplexity", "Perplexity-User", "ai_assistant", "Perplexity-User", PERPLEXITY_BOTS, ["network"], "Visits a page when a Perplexity user asks a question."],
  ["perplexity.perplexitybot", "perplexity", "Perplexity", "PerplexityBot", "search_crawler", "PerplexityBot", PERPLEXITY_BOTS, ["network"], "Surfaces and links websites in Perplexity search results; not used for model training."],
  // ---- Meta ----
  ["meta.externalfetcher", "meta", "Meta", "meta-externalfetcher", "ai_assistant", "meta-externalfetcher", META_CRAWLERS, [], "Fetches links at a user's request, including agentic tasks."],
  ["meta.externalagent", "meta", "Meta", "meta-externalagent", "training_crawler", "meta-externalagent", META_CRAWLERS, [], "Crawls for training foundation AI models and direct indexing."],
  ["meta.webindexer", "meta", "Meta", "meta-webindexer", "search_crawler", "meta-webindexer", META_CRAWLERS, [], "Improves Meta AI search results and citations."],
  ["meta.externalads", "meta", "Meta", "meta-externalads", "monitor", "meta-externalads", META_CRAWLERS, [], "Improves Meta advertising and business products."],
  ["meta.facebookexternalhit", "meta", "Meta", "facebookexternalhit", "preview_bot", "facebookexternalhit", META_CRAWLERS, [], "Builds link previews when a page is shared in Meta's apps."],
  ["meta.facebookbot", "meta", "Meta", "FacebookBot (legacy token)", "training_crawler", "FacebookBot", null, [], "Older Meta crawler token still seen in the wild; not on Meta's current page."],
  // ---- Others (vendor page cited where we know it; otherwise docs: null) ----
  ["microsoft.bingbot", "microsoft", "Microsoft", "Bingbot", "search_crawler", "bingbot", "https://www.bing.com/webmasters/help/which-crawlers-does-bing-use-8c184ec0", ["network"], "Microsoft Bing's search crawler."],
  ["apple.applebot", "apple", "Apple", "Applebot", "search_crawler", "Applebot", "https://support.apple.com/en-us/119829", ["network"], "Crawls for Siri, Spotlight and Safari suggestions."],
  ["apple.applebot-extended", "apple", "Apple", "Applebot-Extended (robots.txt only)", "training_crawler", "Applebot-Extended", "https://support.apple.com/en-us/119829", [], "robots.txt control over Apple's use of content for model training; not a separate user agent.", true],
  ["amazon.amazonbot", "amazon", "Amazon", "Amazonbot", "search_crawler", "Amazonbot", "https://developer.amazon.com/amazonbot", [], "Amazon's crawler used to improve its services, such as Alexa answers."],
  ["bytedance.bytespider", "bytedance", "ByteDance", "Bytespider", "training_crawler", "Bytespider", null, [], "ByteDance crawler widely reported as AI-training traffic."],
  ["commoncrawl.ccbot", "commoncrawl", "Common Crawl", "CCBot", "training_crawler", "CCBot", "https://commoncrawl.org/ccbot", [], "Builds the open Common Crawl dataset, widely used to train AI models."],
  ["duckduckgo.duckassistbot", "duckduckgo", "DuckDuckGo", "DuckAssistBot", "ai_assistant", "DuckAssistBot", "https://duckduckgo.com/duckduckgo-help-pages/results/duckassistbot", [], "Fetches pages for DuckDuckGo's AI-assisted answers."],
  ["duckduckgo.duckduckbot", "duckduckgo", "DuckDuckGo", "DuckDuckBot", "search_crawler", "DuckDuckBot", "https://duckduckgo.com/duckduckgo-help-pages/results/duckduckbot", [], "DuckDuckGo's search crawler."],
  ["mistral.mistralai-user", "mistral", "Mistral AI", "MistralAI-User", "ai_assistant", "MistralAI-User", "https://docs.mistral.ai/robots", [], "Fetches a page when a Le Chat user asks."],
  ["cohere.cohere-ai", "cohere", "Cohere", "cohere-ai", "training_crawler", "cohere-ai", null, [], "Cohere token seen in the wild."],
  ["you.youbot", "you", "You.com", "YouBot", "search_crawler", "YouBot", null, [], "You.com's search crawler."],
  ["diffbot.diffbot", "diffbot", "Diffbot", "Diffbot", "search_crawler", "Diffbot", null, [], "Builds Diffbot's knowledge graph."],
  ["yandex.yandexbot", "yandex", "Yandex", "YandexBot", "search_crawler", "YandexBot", null, [], "Yandex search crawler."],
  ["baidu.baiduspider", "baidu", "Baidu", "Baiduspider", "search_crawler", "Baiduspider", null, [], "Baidu search crawler."],
  // Telegram's user agent says "TelegramBot (like TwitterBot)", so it must be matched before Twitterbot.
  ["telegram.telegrambot", "telegram", "Telegram", "TelegramBot", "preview_bot", "TelegramBot", null, [], "Builds link previews in Telegram."],
  ["x.twitterbot", "x", "X", "Twitterbot", "preview_bot", "Twitterbot", null, [], "Builds link cards for X posts."],
  ["linkedin.linkedinbot", "linkedin", "LinkedIn", "LinkedInBot", "preview_bot", "LinkedInBot", null, [], "Builds link previews on LinkedIn."],
  ["slack.slackbot-linkexpanding", "slack", "Slack", "Slackbot (link expanding)", "preview_bot", "Slackbot-LinkExpanding", "https://api.slack.com/robots", [], "Unfurls links shared in Slack."],
  ["slack.slackbot", "slack", "Slack", "Slackbot", "preview_bot", "Slackbot", "https://api.slack.com/robots", [], "Slack's general bot user agent."],
  ["discord.discordbot", "discord", "Discord", "Discordbot", "preview_bot", "Discordbot", null, [], "Builds link embeds in Discord."],
  ["whatsapp.whatsapp", "whatsapp", "WhatsApp", "WhatsApp", "preview_bot", "WhatsApp", null, [], "Builds link previews in WhatsApp."],
  ["ahrefs.ahrefsbot", "ahrefs", "Ahrefs", "AhrefsBot", "monitor", "AhrefsBot", "https://ahrefs.com/robot", [], "SEO backlink and site-audit crawler."],
  ["semrush.semrushbot", "semrush", "Semrush", "SemrushBot", "monitor", "SemrushBot", "https://www.semrush.com/bot/", [], "SEO and site-audit crawler."],
  ["majestic.mj12bot", "majestic", "Majestic", "MJ12bot", "monitor", "MJ12bot", null, [], "SEO link-index crawler."],
  ["uptimerobot.uptimerobot", "uptimerobot", "UptimeRobot", "UptimeRobot", "monitor", "UptimeRobot", null, [], "Uptime monitoring."],
  ["google.lighthouse", "google", "Google", "Chrome Lighthouse", "monitor", "Chrome-Lighthouse", null, [], "Page performance and quality audits (Lighthouse / PageSpeed Insights)."],
];

/** Operators that publish NO crawler or agent identity. Listed so the public table says so plainly. */
export const UNDECLARED_OPERATORS = Object.freeze([
  { operator: "deepseek", operatorName: "DeepSeek", note: "DeepSeek publishes no crawler or agent user agent and no signing keys, so its visits can only be inferred, never verified." },
]);

const escape = (token) => token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

export const SERVICES = Object.freeze(ROWS.map(([id, operator, operatorName, name, category, token, docs, verifiableBy, description, robotsOnly]) => Object.freeze({
  id, operator, operatorName, name, category, token, docs, verifiableBy: Object.freeze([...verifiableBy]), description,
  ...(robotsOnly ? { robotsOnly: true } : {}),
})));
export const SERVICE_IDS = new Set(SERVICES.map((service) => service.id));

// A token must stand alone: not followed by "-" or a word character, so "Googlebot" never
// swallows "Googlebot-Image" even when the order above is changed by mistake.
const MATCHERS = SERVICES
  .filter((service) => service.token && !service.robotsOnly)
  .map((service) => [new RegExp(`(?:^|[^A-Za-z0-9_-])${escape(service.token)}(?![A-Za-z0-9_-])`, "i"), service]);

/** The most specific registry service whose token appears in the user agent, or null. */
export function serviceForUserAgent(userAgent) {
  if (typeof userAgent !== "string" || !userAgent) return null;
  const ua = userAgent.slice(0, 1024);
  for (const [pattern, service] of MATCHERS) if (pattern.test(ua)) return service;
  return null;
}

/** Map Cloudflare's verified-bot category (present only on plans with Bot Management) to ours. */
const CF_CATEGORY = new Map([
  ["Search Engine Crawler", "search_crawler"], ["Search Engine Optimization", "monitor"],
  ["AI Crawler", "training_crawler"], ["AI Search", "search_crawler"], ["AI Assistant", "ai_assistant"],
  ["Page Preview", "preview_bot"], ["Monitoring & Analytics", "monitor"], ["Advertising & Marketing", "monitor"],
  ["Feed Fetcher", "search_crawler"], ["Archiver", "search_crawler"],
]);

/**
 * What the public observatory says about one request: its category, the registry service it
 * claims or proves to be (or null), and how strong that evidence is.
 *
 * @param {{ triageClass: string, basis?: string, userAgent?: string, signer?: string|null, cfBotCategory?: string }} input
 * @returns {{ category: string, service: string|null, verification: string }}
 */
export function observationFor({ triageClass, basis, userAgent, signer, cfBotCategory }) {
  if (triageClass === "verified_agent" || triageClass === "signed_agent") {
    const service = signer === "https://chatgpt.com" ? "openai.chatgpt-agent" : signer === "https://agent.bot.goog" ? "google.agent" : null;
    return { category: "ai_agent", service, verification: "signature" };
  }
  const claimed = serviceForUserAgent(userAgent);
  if (claimed) return { category: claimed.category, service: claimed.id, verification: basis === "cloudflare_verified_bot" ? "network" : "claimed" };
  if (triageClass === "crawler_claimed" && basis === "cloudflare_verified_bot") {
    return { category: CF_CATEGORY.get(cfBotCategory ?? "") ?? "search_crawler", service: null, verification: "network" };
  }
  if (triageClass === "declared_agent") return { category: "ai_agent", service: null, verification: "claimed" };
  if (triageClass === "crawler_claimed") return { category: "search_crawler", service: null, verification: "claimed" };
  // A script or bot that names itself in its user agent (curl, a bot token) is a claim, like a crawler's.
  // An empty user agent, a browser shape or a model verdict is our inference.
  if (triageClass === "automation") return { category: "automation", service: null, verification: basis === "user_agent" && typeof userAgent === "string" && userAgent.trim() ? "claimed" : "inferred" };
  if (triageClass === "likely_human") return { category: "human", service: null, verification: "inferred" };
  return { category: "unknown", service: null, verification: "unverified" };
}

/** Validate an observation received from the edge. Unknown values never pass. */
export function normalizeObservation(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  if (!CATEGORY_IDS.has(raw.category) || !VERIFICATION_SET.has(raw.verification)) return null;
  const service = raw.service === null || raw.service === undefined ? null : SERVICE_IDS.has(raw.service) ? raw.service : undefined;
  if (service === undefined) return null;
  return { category: raw.category, service, verification: raw.verification };
}

/** The public registry document served at /api/aquarium/registry. */
export function publicRegistry() {
  return {
    version: 1,
    categories: CATEGORIES,
    verificationLevels: VERIFICATION_LEVELS,
    services: SERVICES,
    undeclaredOperators: UNDECLARED_OPERATORS,
  };
}
