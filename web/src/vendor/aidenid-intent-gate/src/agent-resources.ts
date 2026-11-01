/** Cache-Control for every response the edge writes for an agent, and for every refusal: private, never stored, and never
 *  rewritten on its way out. no-transform stops the zone injecting its analytics beacon, which names the platform (Carter #54365). */
export const AGENT_RESPONSE_CACHE = "private, no-store, no-transform";

/** Search/index crawlers and link-preview unfurlers that keep the ordinary site instead of the agent view.
 *  These tokens are anchored and independent of the OPERATORS table. */
export function indexOrPreviewCrawler(userAgent: string): boolean {
  return /\b(Googlebot(?:-Image|-News|-Video)?|Storebot-Google|Google-InspectionTool|AdsBot-Google|bingbot|BingPreview|Applebot|DuckDuckBot|YandexBot|Baiduspider|OAI-SearchBot|Claude-SearchBot|PerplexityBot|facebookexternalhit|Twitterbot|Slackbot|Discordbot|LinkedInBot|Pinterestbot|WhatsApp|TelegramBot|redditbot|Mastodon|Embedly|Mattermost-Bot|Zoombot|SkypeUriPreview|MicrosoftPreview|Iframely|Cardyb|GoogleMessages|vkShare|Viber)\b/i.test(userAgent);
}

/** These exemptions select public presentation only and can never authorize a resource. */
export function discoveryCrawler(userAgent: string): boolean {
  return /\b(GPTBot|OAI-SearchBot|ClaudeBot|Claude-SearchBot|anthropic-ai|PerplexityBot|Googlebot|Google-Extended|GoogleOther|bingbot|Applebot|DuckDuckBot|meta-externalagent|CCBot|Amazonbot|Bytespider|facebookexternalhit|Twitterbot|Slackbot|Discordbot|LinkedInBot|Pinterestbot|YandexBot|Baiduspider)\b/i.test(userAgent);
}
