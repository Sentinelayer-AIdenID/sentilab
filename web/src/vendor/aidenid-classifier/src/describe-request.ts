// describeRequest: builds a RequestVector from a Request.
// Pure: reads only request headers and cf metadata, no network, no env.

import type { RequestVector } from "./types.js";
import { userAgentFamily } from "./recognized-automation.js";

type CfHints = {
  country?: string;
  regionCode?: string;
  httpProtocol?: string;
  tlsVersion?: string;
  tlsClientCiphersSha1?: string;
  tlsClientExtensionsSha1?: string;
  tlsClientHelloLength?: string;
  tlsCipher?: string;
  requestPriority?: string;
  clientAcceptEncoding?: string;
  requestHeaderNames?: string[];
  asn?: number;
  asOrganization?: string;
  botManagement?: { verifiedBot?: boolean; score?: number; signedAgent?: boolean };
  verifiedBotCategory?: string;
};

const cfHints = (request: Request): CfHints => (request as Request & { cf?: CfHints }).cf ?? {};
const boundedCfString = (value: unknown, max: number) => typeof value === "string" && value.length > 0 ? value.slice(0, max) : undefined;

function cfBotEvidence(cf: CfHints): { cfBotCategory?: string; cfSignedAgent?: boolean } {
  const signedAgent = cf.botManagement?.signedAgent;
  return { cfBotCategory: boundedCfString(cf.verifiedBotCategory, 64), cfSignedAgent: typeof signedAgent === "boolean" ? signedAgent : undefined };
}

function clientHintMajor(secChUa: string | null): number | undefined {
  if (!secChUa) return undefined;
  const majors: number[] = [];
  for (const m of secChUa.matchAll(/"([^"]+)";\s*v="(\d+)"/g)) {
    if (!/brand/i.test(m[1] ?? "")) majors.push(Number(m[2]));
  }
  return majors.length ? Math.max(...majors) : undefined;
}

export function describeRequest(request: Request): RequestVector {
  const h = (name: string) => request.headers.get(name);
  const ua = (h("user-agent") ?? "").slice(0, 1024);
  const fam = userAgentFamily(ua);
  const cf = cfHints(request);
  const rawBotScore = cf.botManagement?.score;
  const cloudflareBotScore = typeof rawBotScore === "number" && Number.isInteger(rawBotScore) && rawBotScore >= 1 && rawBotScore <= 99
    ? rawBotScore : undefined;
  const cfNames = Array.isArray(cf.requestHeaderNames) ? cf.requestHeaderNames.filter((name): name is string => typeof name === "string") : null;
  const headerNames = (cfNames ?? Array.from(request.headers.keys())).map((name) => name.toLowerCase()).filter((name) => !name.startsWith("cf-") && name !== "x-real-ip" && name !== "x-forwarded-proto").slice(0, 40);
  return {
    ua, family: fam.family, uaMajor: fam.major, mobile: fam.mobile,
    headerCount: headerNames.length, headerNames,
    tlsCiphersSha1: boundedCfString(cf.tlsClientCiphersSha1, 64),
    tlsExtensionsSha1: boundedCfString(cf.tlsClientExtensionsSha1, 64),
    tlsClientHelloLength: boundedCfString(cf.tlsClientHelloLength, 12),
    tlsCipher: boundedCfString(cf.tlsCipher, 80),
    requestPriority: boundedCfString(cf.requestPriority, 120),
    clientAcceptEncoding: boundedCfString(cf.clientAcceptEncoding, 120),
    signatureAgent: (h("signature-agent") || (h("signature-input") ? "unknown" : null)),
    accept: h("accept"), acceptLanguage: h("accept-language"),
    secFetchMode: h("sec-fetch-mode"), secFetchDest: h("sec-fetch-dest"), secFetchSite: h("sec-fetch-site"),
    secChUa: h("sec-ch-ua"), secChUaMobile: h("sec-ch-ua-mobile"), secChUaPlatform: h("sec-ch-ua-platform"),
    chMajor: clientHintMajor(h("sec-ch-ua")),
    cookie: !!h("cookie"), referer: !!h("referer"),
    httpProtocol: typeof cf.httpProtocol === "string" ? cf.httpProtocol : undefined,
    tlsVersion: typeof cf.tlsVersion === "string" ? cf.tlsVersion : undefined,
    asn: typeof cf.asn === "number" ? cf.asn : undefined,
    asOrganization: typeof cf.asOrganization === "string" ? cf.asOrganization.slice(0, 120) : undefined,
    country: typeof cf.country === "string" ? cf.country : undefined,
    verifiedBot: cf.botManagement?.verifiedBot === true,
    cloudflareBotScore,
    ...cfBotEvidence(cf),
  };
}
