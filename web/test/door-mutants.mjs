// node web/test/door-mutants.mjs
// Mutants of the agent door: the scoped purpose token's verification and scope (src/door/token.js), the door's token
// gate, and every repair of the review round at 75aed822 (root's three P2s, warden's P2 and P3s, the seven mutants
// that survived warden's run, the staging environment) and of root's repair review at df1189c4 (only an outcome the
// door can name is definite after its POST) and warden's four P3s there (the terms a page showed, a press after an
// earlier press, every spelling of an open feed, browsers without Sec-Fetch-Site), and of the copy repairs before the
// production door opens (aneta #57911: the terms text bound to its pin, the links to it, the known limit, the start-here
// discovery and the honest status words). Each runs in a disposable copy of
// web/ (the working checkout is never modified) against the door's tests, and must fail an assertion there: a mutant
// that survives, or that only breaks an import, fails this script. (Dropping equalHex's length term is an equivalent
// mutant: TOKEN_PATTERN already fixes the MAC at 32 hex characters, so no input can tell the two apart. It is not
// listed.)
import assert from "node:assert/strict";
import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const TOKEN = "src/door/token.js";
const DOOR = "src/door/door.js";
const JSON_READER = "src/door/strict-json.js";
const LAYOUT = "src/door/layout.js";
const RENDER = "src/door/render.js";
const ENGRAM = "src/door/engram.js";
const WORKER = "src/worker.js";
const WRANGLER = "wrangler.jsonc";

const groups = {
  "token and scope": [
    ["MAC not checked", TOKEN, '  if (!equalHex(await macHex(key, [site, purpose, caseId, exp, nonce]), mac)) return { ok: false, status: 401, error: "token_invalid" };\n', ""],
    ["MAC compare always equal", TOKEN, "  return diff === 0;", "  return true;"],
    ["MAC compare reads 8 characters", TOKEN, "for (let i = 0; i < Math.max(a.length, b.length); i += 1)", "for (let i = 0; i < 8; i += 1)"],
    ["MAC without the site", TOKEN, 'JSON.stringify(["sentilab-spt1", ...fields])', 'JSON.stringify(["sentilab-spt1", ...fields.slice(1)])'],
    ["MAC without the purpose", TOKEN, 'JSON.stringify(["sentilab-spt1", ...fields])', 'JSON.stringify(["sentilab-spt1", fields[0], ...fields.slice(2)])'],
    ["MAC without the expiry", TOKEN, 'JSON.stringify(["sentilab-spt1", ...fields])', 'JSON.stringify(["sentilab-spt1", ...fields.slice(0, 3), fields[4]])'],
    ["MAC without the nonce", TOKEN, 'JSON.stringify(["sentilab-spt1", ...fields])', 'JSON.stringify(["sentilab-spt1", ...fields.slice(0, 4)])'],
    ["MAC truncated to 8 hex", TOKEN, '["sentilab-spt1", ...fields])))).slice(0, 32);\n}', '["sentilab-spt1", ...fields])))).slice(0, 8).padEnd(32, "0");\n}'],
    ["expiry not checked", TOKEN, '  if (seconds <= nowSeconds) return { ok: false, status: 401, error: "token_expired" };\n', ""],
    ["expiry off by one second", TOKEN, "if (seconds <= nowSeconds)", "if (seconds < nowSeconds)"],
    ["no lifetime ceiling", TOKEN, '  if (seconds > nowSeconds + TOKEN_SECONDS + SKEW_SECONDS) return { ok: false, status: 401, error: "token_invalid" };\n', ""],
    ["expiry judged before the MAC", TOKEN,
      '  if (!equalHex(await macHex(key, [site, purpose, caseId, exp, nonce]), mac)) return { ok: false, status: 401, error: "token_invalid" };\n  const seconds = Number(exp);\n  const nowSeconds = Math.floor(now / 1000);\n',
      '  const seconds = Number(exp);\n  const nowSeconds = Math.floor(now / 1000);\n  if (seconds <= nowSeconds) return { ok: false, status: 401, error: "token_expired" };\n  if (!equalHex(await macHex(key, [site, purpose, caseId, exp, nonce]), mac)) return { ok: false, status: 401, error: "token_invalid" };\n'],
    ["missing token reads as invalid", TOKEN, 'return { ok: false, status: 401, error: "token_missing" };', 'return { ok: false, status: 401, error: "token_invalid" };'],
    ["scope always passes", TOKEN, "return claims.purpose === required ? null : { error: \"token_scope\", allowed: claims.purpose };", "return null;"],
    ["scope names the route's purpose", TOKEN, 'allowed: claims.purpose };', "allowed: required };"],
    ["short keys accepted", TOKEN, "key.length >= MIN_KEY_CHARS", "key.length >= 1"],
    ["door gate skips scope", DOOR, "  if (scope) return refuse(request, format, 403, scope);\n", ""],
    ["door gate takes the first of two tokens", DOOR, 'const token = values.length === 1 ? values[0] : values.length ? "x" : null;', "const token = values[0] ?? null;"],
    ["door gate checks the token against another host", DOOR, "const verdict = await verifyToken(key, token, { site: url.host, now: Date.now() });", 'const verdict = await verifyToken(key, token, { site: "sentilab.aidenid.com", now: Date.now() });'],
    ["wall opens for any well-formed token", DOOR, "(await verifyToken(key, held[0], { site: url.host, now: Date.now() })).ok", "true"],
    ["submit accepts any purpose", DOOR, 'const auth = await authorize(request, env, url, [fields.t], "place-chiplets", format);', 'const auth = await authorize(request, env, url, [fields.t], fields.t.split(".")[1], format);'],
  ],
  "root P2-1, token referrer protection": [
    ["token-bearing responses unprotected", WORKER, "    return carriesToken(new URL(request.url)) ? protectToken(response) : response;", "    return response;"],
    ["protection without no-referrer", DOOR, '  if (headers.get("referrer-policy") !== "strict-origin") headers.set("referrer-policy", "no-referrer");\n', ""],
    ["protection without no-store", DOOR, '  headers.set("cache-control", AGENT_RESPONSE_CACHE);\n  return new Response(response.body', "  return new Response(response.body"],
    ["token-shaped values in other parameters ignored", DOOR, 'return url.searchParams.has("t") || TOKEN_SHAPE.test(url.search);', 'return url.searchParams.has("t");'],
    ["proxy keeps a token-bearing Referer", WORKER, '  if (tokenBearing(headers.get("referer"))) headers.delete("referer");\n', ""],
  ],
  "root P2-2, strict JSON": [
    ["submit body read by JSON.parse", DOOR, "  const read = strictJson(text);\n  if (read.codes) return { codes: read.codes };", "  const read = { value: JSON.parse(text) };\n  if (read.codes) return { codes: read.codes };"],
    ["duplicate keys not flagged", JSON_READER, '      if (keys.has(key)) flags.add("duplicate_key");\n', ""],
    ["depth bound one level too deep", JSON_READER, "      if (depth > MAX_DEPTH) return true;", "      if (depth > MAX_DEPTH + 1) return true;"],
    ["overflowing floats not flagged", JSON_READER, '    if (!Number.isFinite(value)) { flags.add("nonfinite_number"); return 0; }', "    if (!Number.isFinite(value)) return 0;"],
    ["byte-order mark stripped", DOOR, "{ fatal: true, ignoreBOM: true }", "{ fatal: true, ignoreBOM: false }"],
  ],
  "root P2-3, uncertain delivery": [
    ["uncertain delivery reported as not sent", DOOR, "    return deliveryUnknown(request, format, url, { token: auth.token, compact: parsed.compact, terms, requestKey, cause });", '    return refuse(request, format, 503, { error: "intake_unavailable" });'],
    ["a failed fetch counted as never sent", DOOR, 'return { ok: false, attempted: true, reason: controller.signal.aborted ? "timeout" : "unreachable" };', 'return { ok: false, attempted: false, reason: controller.signal.aborted ? "timeout" : "unreachable" };'],
    ["not-confirmed page says nothing was sent", RENDER, '<p class="fine">Sending it again is safe:', '<p class="fine">Nothing was sent. Ask your assistant for a new link. Sending it again is safe:'],
    ["not-confirmed retry drops the token", RENDER, '<input type="hidden" name="t" value="${esc(token)}">\n<input type="hidden" name="l"', '<input type="hidden" name="l"'],
  ],
  "root repair P2, only a named outcome is definite": [
    ["a schema tag alone is definite (the code at df1189c4)", DOOR, "  const outcome = knownOutcome(answer);\n",
      "  const outcome = answer.ok && answer.json?.schema === SUBMIT_SCHEMA && answer.status < 500 ? { refusal: null, state: answer.json.state, runId: answer.json.run_id ?? null, codes: [] } : knownOutcome(answer);\n"],
    ["a state outside the lifecycle names a run", DOOR, 'const run = value.state !== "rejected" && STATES.has(value.state) && typeof value.run_id', 'const run = value.state !== "rejected" && typeof value.run_id'],
    ["a run needs no run id", DOOR, ' && typeof value.run_id === "string" && RUN_ID.test(value.run_id);', ";"],
    ["any run id string names a run", DOOR, ' && typeof value.run_id === "string" && RUN_ID.test(value.run_id);', ' && typeof value.run_id === "string";'],
    ["a run under any status", DOOR, "  if (ACCEPTED_STATUS.has(answer.status)) {\n", '  if (value.state !== "rejected") {\n'],
    ["a refusal under any status", DOOR, "const refused = REFUSAL_STATUS.has(answer.status) && ", "const refused = "],
    ["a refusal with no codes", DOOR, "value.codes.length > 0", "value.codes.length >= 0"],
    ["a refusal with some contract code", DOOR, "&& value.codes.every((c) =>", "&& value.codes.some((c) =>"],
    ["a refusal with any code", DOOR, 'typeof c === "object" && REASON_CODES.has(c.code));', 'typeof c === "object" && typeof c.code === "string");'],
    ["any token_ error is the intake's token refusal", DOOR, "TOKEN_REFUSALS.has(value.error) ?", '/^token_[a-z]+$/.test(value.error ?? "") ?'],
    ["the vocabulary misses a contract code", DOOR, '"edited_before_ingest", "unattributable", ', '"edited_before_ingest", '],
    ["cross_checked has no words", RENDER, '  cross_checked: "reproduced on a second build or host", ', "  "],
    ["a refusal page promises the same run", RENDER, '${accepted ? "Pressing the button again returns the same run." : "Nothing was queued."}', "Pressing the button again returns the same run."],
    ["the token refusal page is skipped", RENDER, "  if (outcome.refusal) {\n", "  if (false) {\n"],
  ],
  "warden P3s at df1189c4 (terms, presses after a press, encoded feeds, old browsers)": [
    ["the form does not carry the shown terms", RENDER, '<input type="hidden" name="terms" value="${esc(terms)}">\n', ""],
    ["the shown terms are not checked", DOOR, "  if (form && !live.accepted.includes(fields.terms)) {\n", "  if (false) {\n"],
    ["a form press is sent under the newest terms", DOOR, "  const terms = form ? fields.terms : live.terms;\n", "  const terms = live.terms;\n"],
    ["a press after an earlier one says nothing was sent", DOOR, "(earlier ? pressRefused(request, response, { error, codes, held }) : response)", "response"],
    ["the pages after a press drop the mark", RENDER, '${SUBMIT_FORM}${again ? "?again=1" : ""}">', '${SUBMIT_FORM}">'],
    ["a prefix-limited press after an earlier one is refused unread", DOOR, "  if (!prefixAllowed && !earlier) return submitLimited(request, format);\n",
      '  if (!prefixAllowed) return stop(submitLimited(request, format), "rate_limited");\n'],
    ["the check is never offered", DOOR, '  if (earlier && TERMS_VERSION.test(fields.terms ?? "")) held = { token: auth.token, compact: parsed.compact, terms: fields.terms };\n', ""],
    ["the feed filter matches the raw path", WORKER, "DOOR_FEEDS.test(path)", "DOOR_FEEDS.test(url.pathname)"],
    ["escapes decoded once", DOOR, 'round < 4 && path.includes("%")', 'round < 1 && path.includes("%")'],
    ["a path that does not decode is passed on", DOOR, "    try { path = decodeURIComponent(path); } catch { return null; }", "    try { path = decodeURIComponent(path); } catch { return pathname; }"],
    ["a page holding the form stays no-referrer", RENDER, "(text.includes(SUBMIT_FORM) || text.includes(DECLARE_FORM))", "(text.includes(DECLARE_FORM))"],
    ["the token guard overrides strict-origin", DOOR, '  if (headers.get("referrer-policy") !== "strict-origin") headers.set("referrer-policy", "no-referrer");\n',
      '  headers.set("referrer-policy", "no-referrer");\n'],
    ["the meta tag stays no-referrer", RENDER, '<meta name="referrer" content="${referrerPolicyFor(body)}">', '<meta name="referrer" content="no-referrer">'],
    ["any Origin passes without Sec-Fetch-Site", DOOR, 'return request.headers.get("origin") === url.origin;', 'return request.headers.get("origin") !== null;'],
    ["no Origin fallback without Sec-Fetch-Site", DOOR, 'return request.headers.get("origin") === url.origin;', "return false;"],
  ],
  "terms from the intake's board": [
    ["the first accepted version, not the highest", DOOR, "number(v) > number(best)", "false"],
  ],
  "warden P2, crawlers": [
    ["search and preview crawlers walled", DOOR, '  if (indexOrPreviewCrawler(request.headers.get("user-agent") ?? "")) return serveAgentVersion(request, env);\n', ""],
  ],
  "warden P3-1 to P3-3": [
    ["cross-site forms accepted", DOOR, '  if (form && !sameSiteForm(request, url)) return refuse(request, format, 403, { error: "cross_site" });\n', ""],
    ["same-site forms accepted", DOOR, 'if (site !== null) return site === "same-origin" || site === "none";', 'if (site !== null) return site !== "cross-site";'],
    ["minting unlimited", DOOR, '  if (!(await allow(env, "DOOR_MINT_LIMITER", `mint:${prefixOf(request)}`))) return limited(request, kind === "json" ? "json" : "html");\n', ""],
    ["proxy passes the declared operator", WORKER, '  if (request.method === "GET" && DOOR_FEEDS.test(path)) return doorFeed(upstream, out);\n', ""],
    ["operator stripped only at the top level", DOOR, ".map(([key, item]) => [key, withoutOperators(item)])", ".map(([key, item]) => [key, item])"],
  ],
  "warden P3-4, the seven survivors": [
    ["status read unlimited", DOOR, '  if (!(await allow(env, "DOOR_READ_LIMITER", `status:${prefixOf(request)}`))) return limited(request, "json");\n', ""],
    ["ENGRAM board read unlimited", DOOR, 'const reading = await allow(env, "DOOR_READ_LIMITER", `engram:${prefixOf(request)}`);', "const reading = true;"],
    ["arrivals unlimited", DOOR, '      if (!(await allow(env, "DOOR_READ_LIMITER", `arrival:${prefixOf(request)}`))) return;\n', ""],
    ["intake redirects followed", DOOR, 'const res = await fetch(origin + path, { method, headers, redirect: "manual", signal: controller.signal,', 'const res = await fetch(origin + path, { method, headers, redirect: "follow", signal: controller.signal,'],
    ["plain-http intake origin allowed", DOOR, String.raw`if (origin.startsWith("https://") || /^http:\/\/(127\.0\.0\.1|localhost)(:[0-9]{1,5})?$/.test(origin)) return origin;`, 'if (origin.startsWith("http")) return origin;'],
    ["minted token bound to x-forwarded-host", DOOR, "  const token = await mintToken(key, { purpose, site: url.host, now });\n  const { claims } = await verifyToken(key, token, { site: url.host, now });",
      '  const site = request.headers.get("x-forwarded-host") ?? url.host;\n  const token = await mintToken(key, { purpose, site, now });\n  const { claims } = await verifyToken(key, token, { site, now });'],
    ["wall checks x-forwarded-host", DOOR, "(await verifyToken(key, held[0], { site: url.host, now: Date.now() })).ok", '(await verifyToken(key, held[0], { site: request.headers.get("x-forwarded-host") ?? url.host, now: Date.now() })).ok'],
  ],
  "warden P3-5, the contract's grammar": [
    ["float literals unboxed", JSON_READER, "    return new Number(value); // a float literal: never an integer, whatever its value", "    return value;"],
    ["r of 2 or more as rotation_not_allowed", LAYOUT, '    if (!ROT_DEG.includes(rot)) { shape.push(code("schema_invalid", { path: `/l/${index}`, keyword: "enum" })); return null; }\n', ""],
  ],
  "deploy, staging of its own": [
    ["staging reaches the production API", WRANGLER, '      "vars": { "API_ORIGIN": "none", "AQUARIUM_POST": "off", "DOOR_DECLARATIONS": "off" },',
      '      "vars": { "API_ORIGIN": "https://sentilab-api.graysea-7ff72f94.eastus2.azurecontainerapps.io", "AQUARIUM_POST": "off", "DOOR_DECLARATIONS": "off" },'],
  ],
  "terms and copy (door-copy-p1)": [
    ["terms served without the hash check", DOOR, '    return hexOf(await crypto.subtle.digest("SHA-256", bytes)) === pin ? bytes : null;', "    return bytes;"],
    ["terms hash compared with the pin and its @", DOOR, 'const pin = version.slice(version.indexOf("@") + 1);', 'const pin = version.slice(version.indexOf("@"));'],
    ["/agents/terms takes the first accepted version, not the highest", DOOR, "return serveTerms(request, env, url, (await sharedBoard(env, url)).terms);",
      "return serveTerms(request, env, url, (await sharedBoard(env, url)).accepted[0]);"],
    ["the canonical path serves the board's version, not its own name", DOOR,
      "return serveTerms(request, env, url, `sentilab-open-terms/${match[1]}`);",
      "return serveTerms(request, env, url, (await sharedBoard(env, url)).terms);"],
    ["the terms directory matched on its raw spelling only", DOOR, "  if (termsDirPath(pathname)) return TERMS_VERSION_ROUTE;", "  if (TERMS_PATH.test(pathname)) return TERMS_VERSION_ROUTE;"],
    ["terms paths compared case-sensitively", DOOR, '"https://door.invalid").pathname.toLowerCase(); }', '"https://door.invalid").pathname; }'],
    ["repeated slashes not folded", DOOR, 'new URL(decoded.replace(/[\\\\/]+/g, "/"), "https://door.invalid")', 'new URL(decoded, "https://door.invalid")'],
    ["no /agents/terms route", DOOR, '  "/agents/terms": { methods: ["GET", "HEAD"], handler: currentTerms },\n', ""],
    ["/agents/terms answers POST", DOOR, '"/agents/terms": { methods: ["GET", "HEAD"], handler: currentTerms }', '"/agents/terms": { methods: ["GET", "HEAD", "POST"], handler: currentTerms }'],
    ["the wall does not link the terms", RENDER, '<p class="fine">Submitting accepts the challenge terms: <a href="${esc(origin)}${TERMS_PAGE}">read them</a>.</p>\n', ""],
    ["the confirm page does not link the terms", RENDER, '<code>${esc(terms)}</code> (<a href="${TERMS_PAGE}">read them</a>).</p>`;', '<code>${esc(terms)}</code>.</p>`;'],
    ["the agent view has no terms_url", ENGRAM, " terms_url: `${origin}${TERMS_PAGE}`,", ""],
    ["the agent view drops the known limit", ENGRAM, "known_limit: knownLimit ?? null,", "known_limit: null,"],
    ["the agent view shows any known_limit text", ENGRAM, 'text.startsWith("Known limit: ") && ', ""],
    ["cross_checked reads independently verified again", RENDER, 'cross_checked: "reproduced on a second build or host"', 'cross_checked: "independently verified"'],
    ["index.md loses its first line", "public/agents/index.md", "Start here: /agents/intent\n\n# SentiLab, for agents", "# SentiLab, for agents"],
    ["llms.txt hard-codes the state again", "public/llms.txt", "stays short. Current state: see /agents/intent.", "stays short. Status: submissions not open yet."],
    ["evidence.json says planned again", "public/agents/evidence.json", '"public_submission_service": "the door\'s POST /agents/submit, under the terms at /agents/terms",',
      '"public_submission_service": "planned",'],
    ["the known limit drifts from root's words", "public/agents/evidence.json", "(about 1.39%)", "(about 1.4%)"],
    ["robots.txt disallows the site", "public/robots.txt", "Disallow:\n", "Disallow: /\n"],
    ["the classification docs drift from the classifier", "public/agents/index.md",
      "| `Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36` | `automation` |", "| `Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36` | `unknown` |"],
    ["the classifier drifts from the classification docs", "src/generated/aidenid-classifier/deterministic-triage.js",
      '  if (vector.family === "other" && INCOMPLETE_WEBKIT_SHELL.test(vector.ua)) {', '  if (false && INCOMPLETE_WEBKIT_SHELL.test(vector.ua)) {'],
  ],
};

const tests = ["door-token.test.mjs", "door-routes.test.mjs", "door-submit.test.mjs", "door-review.test.mjs", "door-hold.test.mjs",
  "door-warden-p3.test.mjs", "door-json.test.mjs", "door-layout.test.mjs", "door-copy.test.mjs", "agents-site.test.mjs"];
const web = new URL("../", import.meta.url);
const repo = new URL("../", web);
const CONTRACT_FILES = ["contracts/open-proposal-v1/reason-codes.json", "contracts/open-proposal-v1/schemas/common.schema.json"];
const only = process.argv[2];
let killed = 0;
let total = 0;
for (const [group, mutants] of Object.entries(groups)) {
  if (only && !group.startsWith(only)) continue;
  for (const [name, rel, before, after] of mutants) {
    total += 1;
    // The copy keeps the repository's shape (<root>/web next to <root>/contracts): the door's tests read the contract's
    // lifecycle states and reason codes from contracts/open-proposal-v1.
    const root = mkdtempSync(join(tmpdir(), "door-mutant-"));
    const dir = join(root, "web");
    try {
      for (const part of ["src", "public", "test", "scripts"]) cpSync(new URL(`${part}/`, web), join(dir, part), { recursive: true });
      cpSync(new URL("wrangler.jsonc", web), join(dir, "wrangler.jsonc"));
      for (const rel of CONTRACT_FILES) cpSync(new URL(rel, repo), join(root, ...rel.split("/")));
      const file = join(dir, ...rel.split("/"));
      const source = readFileSync(file, "utf8");
      assert.equal(source.split(before).length, 2, `unique mutation point: ${name}`);
      writeFileSync(file, source.replace(before, after));
      const result = spawnSync(process.execPath, ["--test", ...tests.map((t) => join(dir, "test", t))], { encoding: "utf8", timeout: 180000 });
      assert.equal(result.status, 1, `${name}: survived (exit ${result.status})\n${result.stdout.slice(-3000)}\n${result.stderr.slice(-2000)}`);
      assert.match(result.stdout, /ERR_ASSERTION/, `${name}: must fail an assertion, not an import or syntax error\n${result.stdout.slice(-3000)}`);
      const first = result.stdout.split("\n").find((line) => /^\s*not ok/.test(line))?.trim();
      console.log(`KILLED [${group}] ${name}: ${first}`);
      killed += 1;
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  }
}
console.log(`PASS ${killed}/${total} mutants fail their behavioral assertions`);
