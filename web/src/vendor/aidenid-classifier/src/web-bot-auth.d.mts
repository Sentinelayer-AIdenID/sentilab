export type WebBotAuthVerification = {
  method: "web_bot_auth";
  components?: string[];
  keyid?: string;
  signer?: string;
  signedAuthority?: string;
};
export type WebBotAuthResult = {
  status: "verified" | "unverified";
  verified: boolean;
  basis: string;
  label: string;
  operator?: string;
  reason?: string;
  verification: WebBotAuthVerification;
  evidence?: unknown;
};
export const SIGNER_TO_OPERATOR: Readonly<Record<string, {
  operator: string;
  label: string;
  reason: string;
}>>;
export function verifyWebBotAuth(request: Request, options?: {
  fetcher?: typeof fetch;
  now?: number;
  timeoutMs?: number;
  captureEvidence?: boolean;
}): Promise<WebBotAuthResult>;
export function verifyWorkerRequest(request: Request, env?: { WEB_BOT_AUTH_VERIFY?: string }): Promise<WebBotAuthResult>;
export function normalizeSignatureEvidence(value: unknown, service: string, recordTime: number, path: string): { version: number; service: string; origin: string; method: string; input: string; signature: string; checkedAt: number; path: string } | null;
export function captureSignatureEvidence(request: Request, service: string, env: { WEB_BOT_AUTH_VERIFY?: string }): Promise<{ version: number; service: string; origin: string; method: string; input: string; signature: string; checkedAt: number; path: string } | null>;
export function recheckSignatureEvidence(value: unknown, service: string, recordTime: number, path: string, fetcher?: typeof fetch): Promise<{ status: string }>;
