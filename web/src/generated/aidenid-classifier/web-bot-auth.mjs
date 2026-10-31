/**
 * Observe-only, deliberately narrow RFC 9421 / Cloudflare Web Bot Auth verifier.
 *
 * Any valid Ed25519 HTTPS Signature-Agent with a published key directory is
 * verified. ChatGPT (chatgpt.com) → operator "openai" is the only evidence-based
 * origin-to-operator mapping. All other verified signers are labeled
 * "Signed agent · <origin>" with operator "unknown" (proves key control, not
 * operator identity).
 *
 * Signature-Agent is parsed as one sf-string via the Structured Fields subset
 * parser; malformed values are refused pre-fetch. Signer origins must be
 * canonical public HTTPS origins (no IP literals, no localhost, no explicit
 * port, at least 2 labels, alphabetic last label).
 *
 * Supported components (no component parameters): @authority, signature-agent,
 * @method, @path, @query, @target-uri. Mandatory @authority + signature-agent.
 * Unsupported RFC features, stale requests and directory failures remain
 * unverified. A valid signature proves the signing operator and covered values;
 * it does not prove user delegation, unique agent, intent or absence of replay.
 * Official profiles: developers.cloudflare.com/bots/reference/bot-verification/
 * web-bot-auth/ and help.openai.com/en/articles/11845367.
 */

const MAX_CACHE_ORIGINS = 64;
const CACHE_TTL_SECONDS = 60;
const KEY_MISS_COOLDOWN_SECONDS = 10;
const keysByFetcherSigner = new WeakMap();
const MAX_DIRECTORY_BYTES = 32 * 1024;
const MAX_SIGNATURE_AGE_SECONDS = 60;
const MAX_FUTURE_SECONDS = 30;
const MAX_LIFETIME_SECONDS = 300;
const COMPONENTS = new Set(['@authority', 'signature-agent', '@method', '@path', '@query', '@target-uri']);
const PARAMS = new Set(['created', 'expires', 'keyid', 'alg', 'nonce', 'tag']);
const encoder = new TextEncoder();
const REASONS = new Set([
  'malformed_signature_headers', 'unsupported_signature_component', 'unsupported_signature_parameter',
  'too_many_signatures', 'duplicate_signature_label', 'directory_unavailable', 'directory_invalid',
  'directory_too_large', 'directory_timeout', 'required_components_missing', 'unsupported_signature_profile',
  'outside_supported_time_window', 'unsupported_request_target', 'signature_label_missing',
  'signature_invalid', 'key_not_trusted',
]);
const errorReason = (error) => error instanceof Error && REASONS.has(error.message)
  ? error.message : 'verification_unavailable';

const unverified = (reason) => ({
  status: 'unverified', verified: false, basis: 'web_bot_auth', label: 'Unknown',
  verification: { method: 'web_bot_auth' }, reason,
});
const failure = (reason) => { throw new Error(reason); };
const ascii = (value) => /^[\x20-\x7e]*$/.test(value);
const sfString = (value) => `"${value.replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`;

/** A bounded Structured Fields subset; serialization normalizes whitespace. */
class Parser {
  constructor(text) { this.text = text; this.pos = 0; }
  peek() { return this.text[this.pos]; }
  consume(value) {
    if (this.text.slice(this.pos, this.pos + value.length) !== value) failure('malformed_signature_headers');
    this.pos += value.length;
  }
  spaces() { while (this.peek() === ' ') this.pos += 1; }
  ows() { while (this.peek() === ' ' || this.peek() === '\t') this.pos += 1; }
  key() {
    const match = /^[a-z*][a-z0-9_.*-]*/.exec(this.text.slice(this.pos));
    if (!match) failure('malformed_signature_headers');
    this.pos += match[0].length;
    return match[0];
  }
  string() {
    this.consume('"');
    let value = '';
    while (this.pos < this.text.length) {
      const char = this.text[this.pos++];
      if (char === '"') return value;
      if (char === '\\') {
        const escaped = this.text[this.pos++];
        if (escaped !== '"' && escaped !== '\\') failure('malformed_signature_headers');
        value += escaped;
      } else {
        if (char.charCodeAt(0) < 0x20 || char.charCodeAt(0) > 0x7e) failure('malformed_signature_headers');
        value += char;
      }
    }
    failure('malformed_signature_headers');
  }
  value() {
    if (this.peek() === '"') return this.string();
    const number = /^-?\d{1,15}(?![\d.])/.exec(this.text.slice(this.pos));
    if (!number) failure('unsupported_signature_parameter');
    this.pos += number[0].length;
    const value = Number(number[0]);
    if (!Number.isSafeInteger(value)) failure('malformed_signature_headers');
    return value;
  }
  input() {
    this.consume('(');
    this.spaces();
    const components = [];
    while (this.peek() !== ')') {
      if (components.length >= 6) failure('unsupported_signature_component');
      const component = this.string();
      if (this.peek() === ';') failure('unsupported_signature_component');
      if (!COMPONENTS.has(component) || components.includes(component)) failure('unsupported_signature_component');
      components.push(component);
      if (this.peek() !== ' ' && this.peek() !== ')') failure('malformed_signature_headers');
      this.spaces();
    }
    this.consume(')');
    const params = {};
    const serialized = [];
    while (this.peek() === ';') {
      this.consume(';');
      this.spaces();
      const name = this.key();
      if (!PARAMS.has(name) || Object.hasOwn(params, name)) failure('unsupported_signature_parameter');
      this.consume('=');
      const value = this.value();
      params[name] = value;
      serialized.push(`;${name}=${typeof value === 'string' ? sfString(value) : value}`);
    }
    return { components, params, serialized: `(${components.map(sfString).join(' ')})${serialized.join('')}` };
  }
  bytes() {
    this.consume(':');
    const match = /^[A-Za-z0-9+/]*={0,2}/.exec(this.text.slice(this.pos));
    this.pos += match[0].length;
    this.consume(':');
    return match[0];
  }
  dictionary(parseValue) {
    const entries = new Map();
    this.ows();
    while (this.pos < this.text.length) {
      if (entries.size >= 4) failure('too_many_signatures');
      const label = this.key();
      if (entries.has(label)) failure('duplicate_signature_label');
      this.consume('=');
      entries.set(label, parseValue.call(this));
      this.ows();
      if (this.pos === this.text.length) return entries;
      this.consume(',');
      this.ows();
      if (this.pos === this.text.length) failure('malformed_signature_headers');
    }
    if (!entries.size) failure('malformed_signature_headers');
    return entries;
  }
}

function fromBase64(value, url = false) {
  if (url && !/^[A-Za-z0-9_-]+$/.test(value)) failure('directory_invalid');
  const encoded = url ? value.replace(/-/g, '+').replace(/_/g, '/') : value;
  const binary = atob(encoded);
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  if (toBase64(bytes, url) !== value) failure(url ? 'directory_invalid' : 'signature_invalid');
  return bytes;
}

function toBase64(bytes, url = false) {
  const value = btoa(String.fromCharCode(...bytes));
  return url ? value.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '') : value;
}

/** RFC 7638 required members only, lexicographic JSON member order. */
async function thumbprint(jwk) {
  const canonical = JSON.stringify({ crv: jwk.crv, kty: jwk.kty, x: jwk.x });
  return toBase64(new Uint8Array(await crypto.subtle.digest('SHA-256', encoder.encode(canonical))), true);
}

async function readDirectory(response, signal, directoryURL) {
  if (!response.ok || response.redirected ||
    (response.url && response.url !== directoryURL)) failure('directory_unavailable');
  const contentType = (response.headers.get('content-type') ?? '').split(';')[0].trim().toLowerCase();
  if (!['application/http-message-signatures-directory+json', 'application/json'].includes(contentType)) failure('directory_invalid');
  const contentLength = response.headers.get('content-length');
  if (contentLength && Number(contentLength) > MAX_DIRECTORY_BYTES) failure('directory_too_large');
  if (!response.body) failure('directory_invalid');
  const reader = response.body.getReader();
  const abortRead = () => { void reader.cancel().catch(() => undefined); };
  signal.addEventListener('abort', abortRead, { once: true });
  const chunks = [];
  let size = 0;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_DIRECTORY_BYTES) {
        await reader.cancel();
        failure('directory_too_large');
      }
      chunks.push(value);
    }
  } finally {
    signal.removeEventListener('abort', abortRead);
    reader.releaseLock();
  }
  const buffer = new Uint8Array(size);
  let position = 0;
  for (const chunk of chunks) { buffer.set(chunk, position); position += chunk.byteLength; }
  const json = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(buffer));
  if (!Array.isArray(json?.keys) || !json.keys.length || json.keys.length > 16) failure('directory_invalid');
  const keys = new Map();
  for (const jwk of json.keys) {
    if (jwk?.kty !== 'OKP' || jwk.crv !== 'Ed25519') continue;
    if (typeof jwk.x !== 'string' || jwk.x.length !== 43 || fromBase64(jwk.x, true).length !== 32 ||
      Object.hasOwn(jwk, 'd')) failure('directory_invalid');
    const id = await thumbprint(jwk);
    keys.set(id, { kty: 'OKP', crv: 'Ed25519', x: jwk.x });
  }
  if (!keys.size) failure('directory_invalid');
  return keys;
}

/** Validate a signer origin: canonical public HTTPS origin only. */
function validateSignerOrigin(signerURL) {
  if (!signerURL.startsWith('https://')) return false;
  let parsed;
  try { parsed = new URL(signerURL); } catch { return false; }
  if (parsed.origin !== signerURL) return false;
  // No explicit port.
  if (parsed.port) return false;
  const host = parsed.hostname;
  // No IP literals, no localhost.
  if (/^[\d.]+$/.test(host) || /^[:\da-fA-F]+$/.test(host) || host === 'localhost') return false;
  const labels = host.split('.');
  if (labels.length < 2) return false;
  if (!/^[A-Za-z]+$/.test(labels[labels.length - 1])) return false;
  return true;
}

/** Evidence-based signer→operator mapping. ChatGPT is the only verified mapping. */
export const SIGNER_TO_OPERATOR = Object.freeze({
  // ChatGPT documented Web Bot Auth key directory: help.openai.com/en/articles/11845367
  'https://chatgpt.com': { operator: 'openai', label: 'OpenAI signed browser', reason: 'trusted_operator_signature_valid' },
});

async function publicKeys(fetcher, now, timeoutMs, neededKey, signerURL) {
  const signerCache = keysByFetcherSigner.get(fetcher) ?? new Map();
  keysByFetcherSigner.set(fetcher, signerCache);
  const directoryURL = `${signerURL}/.well-known/http-message-signatures-directory`;
  const cached = signerCache.get(signerURL);
  if (cached && cached.expiresAt > now) {
    if (cached.keys && cached.keys.has(neededKey)) return cached.keys;
    if (cached.error) failure(cached.reason ?? 'directory_unavailable');
  }
  // Key-miss rate limiting: at most one directory refetch per KEY_MISS_COOLDOWN_SECONDS
  // per origin when the needed keyid is absent from a valid cache.
  const keyMissedAt = cached?.keyMissedAt;
  if (cached && cached.keys && !cached.keys.has(neededKey)) {
    if (keyMissedAt !== undefined && now - keyMissedAt < KEY_MISS_COOLDOWN_SECONDS) {
      failure('key_not_trusted');
    }
  }
  const controller = new AbortController();
  let timer;
  try {
    const keys = await Promise.race([
      (async () => {
        const response = await fetcher(directoryURL, {
          method: 'GET', redirect: 'manual', signal: controller.signal,
          headers: { Accept: 'application/http-message-signatures-directory+json' },
        });
        return readDirectory(response, controller.signal, directoryURL);
      })(),
      new Promise((_, reject) => {
        timer = setTimeout(() => { controller.abort(); reject(new Error('directory_timeout')); }, timeoutMs);
      }),
    ]);
    // Evict the oldest entry when at capacity, but never evict the signer we are refreshing.
    if (signerCache.size >= MAX_CACHE_ORIGINS && !signerCache.has(signerURL)) {
      const oldest = signerCache.keys().next().value;
      signerCache.delete(oldest);
    }
    // Delete-then-set: move refreshed origin to the newest (MRU) slot.
    signerCache.delete(signerURL);
    const entry = { expiresAt: now + CACHE_TTL_SECONDS, keys };
    // Carry forward keyMissedAt if the needed key is still absent after refetch
    if (!keys.has(neededKey)) {
      entry.keyMissedAt = keyMissedAt ?? now;
    }
    signerCache.set(signerURL, entry);
    return keys;
  } catch (err) {
    if (signerCache.size >= MAX_CACHE_ORIGINS && !signerCache.has(signerURL)) {
      const oldest = signerCache.keys().next().value;
      signerCache.delete(oldest);
    }
    signerCache.delete(signerURL);
    signerCache.set(signerURL, { expiresAt: now + CACHE_TTL_SECONDS, error: true, reason: errorReason(err) });
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

function validateInput(input, now) {
  const { components, params } = input;
  if (!components.includes('@authority') || !components.includes('signature-agent')) failure('required_components_missing');
  if (params.tag !== 'web-bot-auth' || (params.alg !== undefined && params.alg !== 'ed25519') ||
    typeof params.keyid !== 'string' || !/^[A-Za-z0-9_-]{43}$/.test(params.keyid)) failure('unsupported_signature_profile');
  if (!Number.isSafeInteger(params.created) || !Number.isSafeInteger(params.expires) ||
    params.created < 0 || params.expires <= params.created ||
    params.created > now + MAX_FUTURE_SECONDS || now - params.created > MAX_SIGNATURE_AGE_SECONDS ||
    params.expires <= now || params.expires - params.created > MAX_LIFETIME_SECONDS) failure('outside_supported_time_window');
  if (params.nonce !== undefined && (typeof params.nonce !== 'string' || params.nonce.length > 256)) failure('unsupported_signature_parameter');
}

function signatureBase(request, input, signatureAgent) {
  const url = new URL(request.url);
  if (url.protocol !== 'https:' || url.username || url.password || url.hash) failure('unsupported_request_target');
  const values = {
    '@authority': url.host.toLowerCase(), 'signature-agent': signatureAgent,
    '@method': request.method, '@path': url.pathname || '/',
    '@query': url.search || '?', '@target-uri': request.url,
  };
  const lines = input.components.map((component) => {
    const value = values[component];
    if (!ascii(value)) failure('unsupported_signature_component');
    return `${sfString(component)}: ${value}`;
  });
  lines.push(`"@signature-params": ${input.serialized}`);
  return { bytes: encoder.encode(lines.join('\n')), authority: values['@authority'] };
}

/** Never throws, modifies requests, performs policy enforcement or fetches an origin. */
export async function verifyWebBotAuth(request, options = {}) {
  try {
    const signatureAgent = request.headers.get('signature-agent');
    const rawInput = request.headers.get('signature-input');
    const rawSignature = request.headers.get('signature');
    if (!signatureAgent || !rawInput || !rawSignature) return unverified('signature_missing');
    if (signatureAgent.length > 256 || rawInput.length > 8192 || rawSignature.length > 4096) return unverified('signature_headers_too_large');
    // Parse Signature-Agent as one sf-string.
    let signerURL;
    try {
      const p = new Parser(signatureAgent);
      signerURL = p.string();
      if (p.pos !== signatureAgent.length) return unverified('signer_not_trusted');
    } catch {
      return unverified('signer_not_trusted');
    }
    if (!validateSignerOrigin(signerURL)) return unverified('signer_not_trusted');
    const inputs = new Parser(rawInput).dictionary(Parser.prototype.input);
    const signatures = new Parser(rawSignature).dictionary(Parser.prototype.bytes);
    const now = options.now ?? Math.floor(Date.now() / 1000);
    if (!Number.isFinite(now) || now < 0) return unverified('invalid_clock');
    const timeoutMs = Number.isFinite(options.timeoutMs) ? Math.min(250, Math.max(10, options.timeoutMs)) : 250;
    const deadline = Date.now() + timeoutMs;
    const fetcher = options.fetcher ?? fetch;
    let lastReason = 'signature_invalid';
    let firstVerified = null;
    for (const [label, input] of inputs) {
      try {
        validateInput(input, now);
        const encodedSignature = signatures.get(label);
        if (!encodedSignature) failure('signature_label_missing');
        const signature = fromBase64(encodedSignature);
        if (signature.length !== 64) failure('signature_invalid');
        const base = signatureBase(request, input, signatureAgent);
        const remaining = deadline - Date.now();
        if (remaining <= 0) failure('directory_timeout');
        const keys = await publicKeys(fetcher, now, remaining, input.params.keyid, signerURL);
        const jwk = keys.get(input.params.keyid);
        if (!jwk) failure('key_not_trusted');
        const key = await crypto.subtle.importKey('jwk', jwk, { name: 'Ed25519' }, false, ['verify']);
        if (!await crypto.subtle.verify('Ed25519', key, signature, base.bytes)) failure('signature_invalid');
        const mapping = SIGNER_TO_OPERATOR[signerURL];
        // A narrow detached receipt can be rechecked later without retaining query strings,
        // cookies, authorization headers, page contents, or the source IP.
        const evidence = options.captureEvidence && !input.components.some(component => component === '@query' || component === '@target-uri')
          && input.serialized.length <= 1200 && ['GET', 'HEAD'].includes(request.method)
          ? { version: 1, origin: new URL(request.url).origin, method: request.method, input: `sig=${input.serialized}`, signature: `sig=:${encodedSignature}:`, checkedAt: now * 1000, path: new URL(request.url).pathname } : null;
        let result;
        if (mapping) {
          result = {
            ...(evidence ? { evidence } : {}),
            status: 'verified', verified: true, basis: 'web_bot_auth',
            operator: mapping.operator, label: mapping.label, reason: mapping.reason,
            verification: {
              method: 'web_bot_auth', components: input.components, signer: signerURL,
              keyid: input.params.keyid, signedAuthority: base.authority,
            },
          };
        } else {
          const origin = new URL(signerURL).origin;
          result = {
            ...(evidence ? { evidence } : {}),
            status: 'verified', verified: true, basis: 'web_bot_auth', operator: 'unknown',
            label: `Signed agent · ${origin}`, reason: 'signature_valid',
            verification: {
              method: 'web_bot_auth', components: input.components, signer: signerURL,
              keyid: input.params.keyid, signedAuthority: base.authority,
            },
          };
        }
        if (!options.captureEvidence || evidence) return result;
        // A valid query-bound signature still proves this request. During
        // capture, keep it as fallback while looking for a separately valid
        // receipt-safe signature within the same bounded signature/deadline limits.
        firstVerified ??= result;
      } catch (error) {
        lastReason = errorReason(error);
      }
    }
    return firstVerified ?? unverified(lastReason);
  } catch (error) {
    return unverified(errorReason(error));
  }
}

/** Opt-in wrapper for Cloudflare Worker env configuration. */
export async function verifyWorkerRequest(request, env = {}) {
  return env.WEB_BOT_AUTH_VERIFY === 'true'
    ? verifyWebBotAuth(request)
    : unverified('verification_disabled');
}

const RECHECK_SIGNERS = Object.freeze({ 'openai.chatgpt-agent': 'https://chatgpt.com', 'google.agent': 'https://agent.bot.goog' });

export function normalizeSignatureEvidence(value, service, recordTime, path) {
  if (!value || value.version !== 1 || !RECHECK_SIGNERS[service] || value.service !== service
    || !Number.isSafeInteger(value.checkedAt) || Math.abs(value.checkedAt - recordTime) > 120_000
    || !['GET', 'HEAD'].includes(value.method) || !['https://aidenid.com', 'https://www.aidenid.com'].includes(value.origin)
    || typeof value.input !== 'string' || value.input.length > 1204 || typeof value.signature !== 'string' || value.signature.length > 100) return null;
  try {
    const inputs = new Parser(value.input).dictionary(Parser.prototype.input);
    const signatures = new Parser(value.signature).dictionary(Parser.prototype.bytes);
    const input = inputs.get('sig');
    if (inputs.size !== 1 || signatures.size !== 1 || !signatures.has('sig') || !input
      || input.components.some(component => component === '@query' || component === '@target-uri')
      || (input.components.includes('@path') && value.path !== path)) return null;
    validateInput(input, Math.floor(value.checkedAt / 1000));
    return { version: 1, service, origin: value.origin, method: value.method, input: value.input, signature: value.signature, checkedAt: value.checkedAt, path };
  } catch { return null; }
}

export async function captureSignatureEvidence(request, service, env) {
  if (env.WEB_BOT_AUTH_VERIFY !== 'true' || !RECHECK_SIGNERS[service]
    || request.headers.get('signature-agent') !== JSON.stringify(RECHECK_SIGNERS[service])) return null;
  const result = await verifyWebBotAuth(request, { captureEvidence: true });
  return result.status === 'verified' && result.evidence ? { ...result.evidence, service } : null;
}

export async function recheckSignatureEvidence(value, service, recordTime, path, fetcher = fetch) {
  const evidence = normalizeSignatureEvidence(value, service, recordTime, path);
  if (!evidence) return { status: 'unavailable' };
  const signer = RECHECK_SIGNERS[service], directory = `${signer}/.well-known/http-message-signatures-directory`;
  // A fresh wrapper isolates this historical check from live-signature cache clocks.
  const guardedFetch = (url, init) => url === directory ? fetcher(url, init) : Promise.reject(new Error('signer_not_trusted'));
  const result = await verifyWebBotAuth(new Request(evidence.origin + evidence.path, {
    method: evidence.method, headers: { 'signature-agent': JSON.stringify(signer), 'signature-input': evidence.input, signature: evidence.signature },
  }), { now: Math.floor(evidence.checkedAt / 1000), fetcher: guardedFetch });
  return { status: result.status === 'verified' ? 'verified' : result.reason === 'signature_invalid' ? 'invalid' : 'unavailable' };
}
