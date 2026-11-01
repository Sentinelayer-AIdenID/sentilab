// node web/test/door-mutants.mjs
// Mutants of the agent door: the scoped purpose token's verification and scope (src/door/token.js), the door's token
// gate, and every repair of the review round at 75aed822 (root's three P2s, warden's P2 and P3s, the seven mutants
// that survived warden's run, the staging environment) and of root's repair review at df1189c4 (only an outcome the
// door can name is definite after its POST). Each runs in a disposable copy of web/ (the working checkout
// is never modified) against the door's tests, and must fail an assertion there: a mutant that survives, or that only
// breaks an import, fails this script. (Dropping equalHex's length term is an equivalent mutant: TOKEN_PATTERN already
// fixes the MAC at 32 hex characters, so no input can tell the two apart. It is not listed.)
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
const WORKER = "src/worker.js";
const WRANGLER = "wrangler.jsonc";
const RETRY_FORM = `<form method="post" action="/agents/submit">
<input type="hidden" name="t" value="\${esc(token)}">
<input type="hidden" name="l" value="\${esc(compact)}">
<button type="submit">Send the same layout again</button>`;

const groups = {
  "token and scope": [
    ["MAC not checked", TOKEN, '  if (!equalHex(await macHex(key, [site, purpose, caseId, exp, nonce]), mac)) return { ok: false, status: 401, error: "token_invalid" };\n', ""],
    ["MAC compare always equal", TOKEN, "  return diff === 0;", "  return true;"],
    ["MAC compare reads 8 characters", TOKEN, "for (let i = 0; i < Math.max(a.length, b.length); i += 1)", "for (let i = 0; i < 8; i += 1)"],
    ["MAC without the site", TOKEN, 'JSON.stringify(["sentilab-spt1", ...fields])', 'JSON.stringify(["sentilab-spt1", ...fields.slice(1)])'],
    ["MAC without the purpose", TOKEN, 'JSON.stringify(["sentilab-spt1", ...fields])', 'JSON.stringify(["sentilab-spt1", fields[0], ...fields.slice(2)])'],
    ["MAC without the expiry", TOKEN, 'JSON.stringify(["sentilab-spt1", ...fields])', 'JSON.stringify(["sentilab-spt1", ...fields.slice(0, 3), fields[4]])'],
    ["MAC without the nonce", TOKEN, 'JSON.stringify(["sentilab-spt1", ...fields])', 'JSON.stringify(["sentilab-spt1", ...fields.slice(0, 4)])'],
    ["MAC truncated to 8 hex", TOKEN, ".slice(0, 32);\n}", ".slice(0, 8).padEnd(32, \"0\");\n}"],
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
    ["protection without no-referrer", DOOR, '  headers.set("referrer-policy", "no-referrer");\n', ""],
    ["protection without no-store", DOOR, '  headers.set("cache-control", AGENT_RESPONSE_CACHE);\n  return new Response(response.body', "  return new Response(response.body"],
    ["token-shaped values in other parameters ignored", DOOR, 'return url.searchParams.has("t") || TOKEN_SHAPE.test(url.search);', 'return url.searchParams.has("t");'],
    ["proxy keeps a token-bearing Referer", WORKER, '  if (tokenBearing(headers.get("referer"))) headers.delete("referer");\n', ""],
  ],
  "root P2-2, strict JSON": [
    ["submit body read by JSON.parse", DOOR, "  const read = strictJson(text);", "  const read = { value: JSON.parse(text) };"],
    ["duplicate keys not flagged", JSON_READER, '      if (keys.has(key)) flags.add("duplicate_key");\n', ""],
    ["depth bound one level too deep", JSON_READER, "      if (depth > MAX_DEPTH) return true;", "      if (depth > MAX_DEPTH + 1) return true;"],
    ["overflowing floats not flagged", JSON_READER, '    if (!Number.isFinite(value)) { flags.add("nonfinite_number"); return 0; }', "    if (!Number.isFinite(value)) return 0;"],
    ["byte-order mark stripped", DOOR, "{ fatal: true, ignoreBOM: true }", "{ fatal: true, ignoreBOM: false }"],
  ],
  "root P2-3, uncertain delivery": [
    ["uncertain delivery reported as not sent", DOOR, "    return deliveryUnknown(request, format, url, { token: auth.token, compact: parsed.compact, requestKey, cause });", '    return refuse(request, format, 503, { error: "intake_unavailable" });'],
    ["a failed fetch counted as never sent", DOOR, 'return { ok: false, attempted: true, reason: controller.signal.aborted ? "timeout" : "unreachable" };', 'return { ok: false, attempted: false, reason: controller.signal.aborted ? "timeout" : "unreachable" };'],
    ["not-confirmed page says nothing was sent", RENDER, '<p class="fine">Sending it again is safe:', '<p class="fine">Nothing was sent. Ask your assistant for a new link. Sending it again is safe:'],
    ["not-confirmed retry drops the token", RENDER, RETRY_FORM, RETRY_FORM.replace('<input type="hidden" name="t" value="${esc(token)}">\n', "")],
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
    ["cross_checked has no words", RENDER, '  cross_checked: "independently verified", ', "  "],
    ["a refusal page promises the same run", RENDER, '${accepted ? "Pressing the button again returns the same run." : "Nothing was queued."}', "Pressing the button again returns the same run."],
    ["the token refusal page is skipped", RENDER, "  if (outcome.refusal) {\n", "  if (false) {\n"],
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
    ["proxy passes the declared operator", WORKER, '  if (request.method === "GET" && DOOR_FEEDS.test(url.pathname)) return doorFeed(upstream, out);\n', ""],
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
    ["staging reaches the production API", WRANGLER, '      "vars": { "API_ORIGIN": "none", "AQUARIUM_POST": "off" },', '      "vars": { "API_ORIGIN": "https://sentilab-api.graysea-7ff72f94.eastus2.azurecontainerapps.io", "AQUARIUM_POST": "off" },'],
  ],
};

const tests = ["door-token.test.mjs", "door-routes.test.mjs", "door-submit.test.mjs", "door-review.test.mjs", "door-hold.test.mjs",
  "door-json.test.mjs", "door-layout.test.mjs"];
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
