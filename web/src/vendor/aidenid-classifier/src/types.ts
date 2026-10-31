// Shared type definitions for the classifier. These are the exact same shapes the
// aquarium edge uses. The edge's EdgeIdentity includes additional fields (observation,
// verification, checkpoint) that the classifier alone does not produce; those remain
// aquarium-edge-only.

export type Operator = "openai" | "google" | "meta" | "anthropic" | "perplexity" | "microsoft" | "apple" | "amazon" | "bytedance" | "commoncrawl" | "deepseek" | "unknown";

export type BrowserFamily = "chromium" | "firefox" | "safari" | "other" | "none";

export type TriageClass = "verified_agent" | "signed_agent" | "declared_agent" | "crawler_claimed" | "automation" | "likely_human" | "unknown";

export type TriageStep = "T0" | "T1" | "T3" | "T4";

export type VerdictStatus = "decided" | "ambiguous" | "unavailable" | "skipped";

export type Verdict = {
  status: VerdictStatus;
  provider?: "workers_ai" | "typesafe_api" | "cache";
  model?: string;
  isAutomated?: number;
  operatorHint?: string;
  operatorConfidence?: number;
  error?: string;
};

export type Triage = {
  class: TriageClass;
  step: TriageStep;
  family: BrowserFamily;
  uaMajor?: number;
  hard: string[];
  soft: string[];
  reasons: string[];
  verdict?: Verdict;
};

/** EdgeIdentity as produced by the deterministic classifier (T1+T3 only). */
export type EdgeIdentity = {
  operator: Operator;
  label: string;
  basis: "user_agent" | "cloudflare_verified_bot" | "web_bot_auth" | "request_shape" | "jev" | "unknown";
  confidence: number;
  verified: boolean;
  triage: Triage;
};

export type RequestVector = {
  ua: string;
  family: BrowserFamily;
  uaMajor?: number;
  mobile: boolean;
  headerCount: number;
  headerNames: string[];
  tlsCiphersSha1?: string;
  tlsExtensionsSha1?: string;
  tlsClientHelloLength?: string;
  tlsCipher?: string;
  requestPriority?: string;
  clientAcceptEncoding?: string;
  signatureAgent: string | null;
  accept: string | null;
  acceptLanguage: string | null;
  secFetchMode: string | null;
  secFetchDest: string | null;
  secFetchSite: string | null;
  secChUa: string | null;
  secChUaMobile: string | null;
  secChUaPlatform: string | null;
  chMajor?: number;
  cookie: boolean;
  referer: boolean;
  httpProtocol?: string;
  tlsVersion?: string;
  asn?: number;
  asOrganization?: string;
  country?: string;
  verifiedBot: boolean;
  cloudflareBotScore?: number;
  cfBotCategory?: string;
  cfSignedAgent?: boolean;
};
