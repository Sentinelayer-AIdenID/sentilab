// node web/test/door-a4-mutants.mjs [group-prefix]
// Mutants of every new rule of AGENT-DOOR Amendment 4 rev 2 at the edge: the opt-in and its display-text rules and caps
// (src/door/declare.js), the purpose step and the heartbeat proxy with its per-IP limit (src/door/door.js, src/worker.js),
// the wall's copy and form (src/door/render.js), the heartbeat limiter's binding (wrangler.jsonc), the opt-in's delivery,
// and the pages' heartbeat module (public/sentilab/here.mjs). Each runs in
// a disposable copy of web/ (the working checkout is never modified) against the A4 tests, and must fail an assertion
// there: a mutant that survives, or that only breaks an import or the syntax, fails this script.
import assert from "node:assert/strict";
import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const DECLARE = "src/door/declare.js";
const DOOR = "src/door/door.js";
const RENDER = "src/door/render.js";
const WORKER = "src/worker.js";
const HERE = "public/sentilab/here.mjs";
const WRANGLER = "wrangler.jsonc";
const B = String.fromCharCode(92);       // a backslash, so no escape in this file can turn into the character it names
const NL = String.fromCharCode(10);
const TOKEN = "src/door/token.js";
const CATEGORIES = ["Cc", "Cf", "Co", "Cs", "Cn", "Zl", "Zp"];
const categories = (list) => `const REFUSED_CATEGORY = /[${list.map((c) => `${B}p{${c}}`).join("")}]/u;`;

const groups = {
  "the character policy (root's shared rule)": [
    ...CATEGORIES.map((category) => [`${category} accepted`, DECLARE, categories(CATEGORIES), categories(CATEGORIES.filter((c) => c !== category))]),
    ["categories judged after normalising (a tag payload stripped, then accepted)", DECLARE, "  if (REFUSED_CATEGORY.test(text)) return \"control_character\";",
      `  if (REFUSED_CATEGORY.test(text.normalize("NFKC").replace(/${B}p{Cf}/gu, ""))) return "control_character";`],
    ["a run of 9 marks allowed", DECLARE, "export const MAX_MARK_RUN = 8;", "export const MAX_MARK_RUN = 9;"],
    ["mark runs never reset (a total quota)", DECLARE, "run = MARK.test(char) ? run + 1 : 0;", "run = MARK.test(char) ? run + 1 : run;"],
    ["mark runs not checked", DECLARE, '    if (run > MAX_MARK_RUN) return "combining_marks";', ""],
    ["length counted in UTF-16 units", DECLARE, "return [...text].length > max ? \"too_long\" : null;", "return text.length > max ? \"too_long\" : null;"],
    ["cap off by one", DECLARE, "return [...text].length > max ? \"too_long\" : null;", "return [...text].length >= max ? \"too_long\" : null;"],
    ["name cap 65", DECLARE, "FIELD_LIMITS = Object.freeze({ name: 64, reason: 160 });", "FIELD_LIMITS = Object.freeze({ name: 65, reason: 160 });"],
    ["reason cap 161", DECLARE, "FIELD_LIMITS = Object.freeze({ name: 64, reason: 160 });", "FIELD_LIMITS = Object.freeze({ name: 64, reason: 161 });"],
  ],
  "reserved names (defense in depth)": [
    ["reserved names accepted", DECLARE, '    if (field === "name" && RESERVED_NAMES.includes(nameKey(values[0]))) return { status: "not_sent", code: "reserved_name" };', ""],
    ["the rule on reason, not name", DECLARE, 'if (field === "name" && RESERVED_NAMES', 'if (field === "reason" && RESERVED_NAMES'],
    ["a reserved label missing", DECLARE, '  "moderator"]);', '  "moderators"]);'],
    ["compared without NFKC", DECLARE, 'return name.normalize("NFKC").replace(', "return name.replace("],
    ["compared case-sensitively", DECLARE, ".trim().toLowerCase();", ".trim();"],
    ["compared untrimmed", DECLARE, ".trim().toLowerCase();", ".toLowerCase();"],
    ["whitespace runs kept", DECLARE, `.replace(/${B}s+/gu, " ")`, ""],
    ["format characters kept", DECLARE, `.replace(/${B}p{Cf}/gu, "")`, ""],
    ["a refusal here reads not_sent", DECLARE, 'if (optIn.status === "not_sent") return { status: "not_recorded", code: optIn.code',
      'if (optIn.status === "not_sent") return { status: "not_sent", code: optIn.code'],
  ],
  "the opt-in: only a POST bound to the pass": [
    ["a GET records a declaration", DOOR, "  emitArrival(request, env, ctx, url, { purpose, nonce: claims.nonce, expiresAt: claims.expires_at });",
      '  emitArrival(request, env, ctx, url, { purpose, nonce: claims.nonce, expiresAt: claims.expires_at, ...(readOptIn(url.searchParams).status === "opted_in" ? { declaration: readOptIn(url.searchParams).declaration } : {}) });'],
    ["a cross-site form accepted", DOOR, '  if (form && !ownPageForm(request, url)) return refuse(request, format, 403, { error: "cross_site" });', ""],
    ["a same-site or user-typed form accepted", DOOR, `  if (site !== null) return site === "same-origin";${NL}  return request.headers.get("origin") === url.origin;`,
      `  if (site !== null) return site !== "cross-site";${NL}  return request.headers.get("origin") === url.origin;`],
    ["another site's Origin accepted", DOOR, '  return request.headers.get("origin") === url.origin;', "  return true;"],
    ["the declare key not checked", DOOR, '    if (versions.length !== 1 || keys.length !== 1 || !sameHex(keys[0], expected)) return refuse(request, format, 403, { error: "declare_key_invalid" });', ""],
    ["the key not bound to the pass", TOKEN, 'JSON.stringify(["sentilab-declare/1", site, nonce, version])', 'JSON.stringify(["sentilab-declare/1", site, version])'],
    ["the key not bound to the notice version", TOKEN, 'JSON.stringify(["sentilab-declare/1", site, nonce, version])', 'JSON.stringify(["sentilab-declare/1", site, nonce])'],
    ["the declaration echoed", DOOR, '  return json(request, 200, { schema: "sentilab-agent-declare/1", declaration: outcome });',
      '  return json(request, 200, { schema: "sentilab-agent-declare/1", declaration: outcome, echo: optIn.declaration ?? null });'],
    ["a stale notice version accepted", DECLARE, '  if (versions[0] !== NOTICE.version) return { status: "not_sent", code: "notice_changed" };', ""],
    ["two notice versions: the first taken", DECLARE, '  if (versions.length > 1) return { status: "not_sent", code: "field_repeated" };', ""],
    ["a repeated field: the first taken", DECLARE, '    if (values.length > 1) return { status: "not_sent", code: "field_repeated" };', ""],
    ["an empty field kept", DECLARE, '    if (values.length === 0 || values[0] === "") continue;', "    if (values.length === 0) continue;"],
    ["any source accepted", DECLARE, '(SOURCES.includes(values[0]) ? null : "source_unknown")', "null"],
    ["via fills an absent source", DECLARE, '    if (values.length === 0 || values[0] === "") continue;',
      '    if (values.length === 0 || values[0] === "") { if (field === "source" && viaSource(params)) declaration.source = viaSource(params); continue; }'],
  ],
  "the notice and the confirm form": [
    ["the bundled notice's version drifts", DECLARE, 'version: "sentilab-public-visitor/1",', 'version: "sentilab-public-visitor/2",'],
    ["the bundled notice's text drifts", DECLARE, "Do not include private information.", "Do not include private data."],
    ["the confirm page without the notice", RENDER, '<blockquote class="notice">${esc(NOTICE.text)}</blockquote>', ""],
    ["the opt-in pre-ticked", RENDER, '<input type="checkbox" name="notice_version" value="${esc(NOTICE.version)}">', '<input type="checkbox" name="notice_version" value="${esc(NOTICE.version)}" checked>'],
    ["a link's text not escaped", RENDER, 'value="${esc(prefill.reason)}"', 'value="${prefill.reason}"'],
    ["via does not select the source", RENDER, '${s === prefill.source ? " selected" : ""}', ""],
    ["the pass's key missing from the form", RENDER, '<input type="hidden" name="declare_key" value="${esc(key)}">', ""],
    ["a crafted link not flagged", RENDER, "${carried ?", "${false ?"],
    ["the old wall line", RENDER, "export const RECORDED = \"What we record: a guess at your assistant's type, and the time of this visit.",
      "export const RECORDED = \"What we record: your assistant's type and the time of this visit."],
  ],
  "via": [
    ["via takes any slug", DECLARE, "return values.length === 1 && SOURCES.includes(values[0]) ? values[0] : null;", "return values.length === 1 && /^[a-z0-9-]{1,32}$/.test(values[0]) ? values[0] : null;"],
    ["via takes the first of two", DECLARE, "return values.length === 1 && SOURCES.includes(values[0]) ? values[0] : null;", "return values.length >= 1 && SOURCES.includes(values[0]) ? values[0] : null;"],
    ["via carried into every next link", RENDER, '[{ name: "board", label: "The board: class, short id and scores", url: `${origin}/agents/board` },',
      '[{ name: "board", label: "The board: class, short id and scores", url: `${origin}/agents/board${source ? `?via=${source}` : ""}` },'],
  ],
  "the heartbeat proxy": [
    ["any method", DOOR, '  if (request.method !== "POST") return hereAnswer(request, 405, { error: "method_not_allowed" }, { allow: "POST" });\n', ""],
    ["cross-site accepted", DOOR, '  if (site !== null) return site === "same-origin";', "  if (site !== null) return true;"],
    ["same-site accepted", DOOR, '  if (site !== null) return site === "same-origin";', '  if (site !== null) return site !== "cross-site";'],
    ["another site's Origin accepted", DOOR, "  return origin === null || origin === url.origin;", "  return true;"],
    ["extra fields accepted", DOOR, '  if (keys.length !== 2 || keys[0] !== "page" || keys[1] !== "tab") return null;\n', ""],
    ["any page", DOOR, "  return HERE_PAGES.includes(page) && typeof tab", "  return typeof page === \"string\" && typeof tab"],
    ["an upper-case tab", DOOR, "const HERE_TAB = /^[0-9a-f]{32}$/;", "const HERE_TAB = /^[0-9a-f]{32}$/i;"],
    ["the detector's class unqualified", DOOR, 'class: TAB_CLASS[who?.triage?.class] ?? "unknown"', 'class: who?.triage?.class ?? "unknown"'],
    ["the client IP forwarded", DOOR, 'body: { ...beat, class: TAB_CLASS[who?.triage?.class] ?? "unknown" },',
      'body: { ...beat, class: TAB_CLASS[who?.triage?.class] ?? "unknown", ip: request.headers.get("cf-connecting-ip") },'],
    ["a visitor header forwarded", DOOR, 'host: url.host, timeoutMs: 1500 });\n  if (answer.ok && answer.status === 204)',
      'host: url.host, nonce: request.headers.get("user-agent"), timeoutMs: 1500 });\n  if (answer.ok && answer.status === 204)'],
    ["every spelling of the path", WORKER, "    if (pathname === HERE_PATH) return handleHere(request, env);", "    if (decodedPath(pathname) === HERE_PATH) return handleHere(request, env);"],
    ["the API's 429 hidden", DOOR, '  if (answer.ok && answer.status === 429) return hereAnswer(request, 429, { error: "rate_limited" }, { "retry-after": "60" });\n', ""],
  ],
  "the heartbeat limiter: the platform binding, no fallback": [
    ["no binding lets heartbeats through", DOOR, 'if (!limiter || typeof limiter.limit !== "function") return "unavailable";',
      'if (!limiter || typeof limiter.limit !== "function") return "allowed";'],
    ["the in-memory fallback restored", DOOR, 'if (!limiter || typeof limiter.limit !== "function") return "unavailable";',
      'if (!limiter || typeof limiter.limit !== "function") return (await allow(env, "DOOR_IP_LIMITER", `here:${prefixOf(request)}`)) ? "allowed" : "limited";'],
    ["a binding error lets it through", DOOR, '    return "unavailable";', '    return "allowed";'],
    ["the binding's refusal ignored", DOOR, 'return success === true ? "allowed" : success === false ? "limited" : "unavailable";', 'return "allowed";'],
    ["a strange answer lets it through", DOOR, ': success === false ? "limited" : "unavailable";', ': success === false ? "limited" : "allowed";'],
    ["one key for everyone", DOOR, "limiter.limit({ key: `here:${prefixOf(request)}` })", 'limiter.limit({ key: "here" })'],
    ["unavailable answered as allowed", DOOR, '  if (limit === "unavailable") return hereAnswer(request, 503, { error: "presence_unavailable" });', ""],
    ["the limit not applied", DOOR, '  if (limit === "limited") return hereAnswer(request, 429, { error: "rate_limited" }, { "retry-after": "60" });', ""],
    ["a 10 s period", WRANGLER, '{ "name": "DOOR_HERE_LIMITER", "namespace_id": "2026110105", "simple": { "limit": 300, "period": 60 } }',
      '{ "name": "DOOR_HERE_LIMITER", "namespace_id": "2026110105", "simple": { "limit": 300, "period": 10 } }'],
    ["staging shares production's namespace", WRANGLER, '"namespace_id": "2026110115"', '"namespace_id": "2026110105"'],
  ],
  "the opt-in's delivery: recorded only on the intake's acceptance": [
    ["every opt-in reads recorded", DECLARE, 'const known = typeof delivery === "string" && Object.hasOwn(DELIVERED, delivery) ? DELIVERED[delivery] : { status: "unconfirmed" };',
      "const known = DELIVERED.recorded;"],
    ["an unknown delivery reads recorded", DECLARE, '? DELIVERED[delivery] : { status: "unconfirmed" };', "? DELIVERED[delivery] : DELIVERED.recorded;"],
    ["the opt-in not awaited", DOOR, "delivery = await deliverArrival(", "delivery = deliverArrival("],
    ["a skipped arrival reads recorded", DOOR, 'if (!(await allow(env, "DOOR_READ_LIMITER", `arrival:${prefixOf(request)}`))) return "skipped";',
      'if (!(await allow(env, "DOOR_READ_LIMITER", `arrival:${prefixOf(request)}`))) return "recorded";'],
    ["nothing sent reads unconfirmed", DOOR, '  if (!answer.attempted) return "not_sent";', ""],
    ["a failure reads recorded", DOOR, '  if (!answer.ok) return "unconfirmed";', '  if (!answer.ok) return "recorded";'],
    ["any 2xx reads recorded", DOOR, "  if (answer.status === 204) return \"recorded\";", "  if (answer.status < 300) return \"recorded\";"],
    ["the intake's 429 reads recorded", DOOR, '  if (answer.status === 429) return "rate_limited";', '  if (answer.status === 429) return "recorded";'],
    ["a refusal reads unconfirmed", DOOR, '  if (answer.status === 400 && answer.json?.state === "rejected") return "refused";', ""],
    ["any 400 reads refused", DOOR, 'answer.status === 400 && answer.json?.state === "rejected"', "answer.status === 400"],
  ],
  "the open feeds": [
    ["visitors unfiltered", DOOR, "events|visitors|stats)$/", "events|stats)$/"],
    ["stats unfiltered", DOOR, "events|visitors|stats)$/", "events|visitors)$/"],
    ["feeds sniffable", WORKER, '  headers.set("x-content-type-options", "nosniff");\n', ""],
  ],
  "the page heartbeat module": [
    ["cookies sent", HERE, 'credentials: "omit"', 'credentials: "include"'],
    ["a Referer sent", HERE, 'referrerPolicy: "no-referrer"', 'referrerPolicy: "strict-origin-when-cross-origin"'],
    ["beats while hidden", HERE, "    if (stopped || !visible()) return;\n    timer = timers.setTimeout(", "    if (stopped) return;\n    timer = timers.setTimeout("],
    ["no minute between beats", HERE, "Math.max(0, last + intervalMs - now())", "0"],
    ["a new tab id each beat", HERE, "JSON.stringify({ page, tab })", "JSON.stringify({ page, tab: newTabId(random) })"],
    ["a 64-bit tab id", HERE, "new Uint8Array(16)", "new Uint8Array(8)"],
  ],
};

const tests = ["door-a4.test.mjs", "here.test.mjs", "door-routes.test.mjs"];
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
    const root = mkdtempSync(join(tmpdir(), "door-a4-mutant-"));
    const dir = join(root, "web");
    try {
      for (const part of ["src", "public", "test", "scripts"]) cpSync(new URL(`${part}/`, web), join(dir, part), { recursive: true });
      cpSync(new URL("wrangler.jsonc", web), join(dir, "wrangler.jsonc"));
      for (const file of CONTRACT_FILES) cpSync(new URL(file, repo), join(root, ...file.split("/")));
      const file = join(dir, ...rel.split("/"));
      const source = readFileSync(file, "utf8");
      assert.equal(source.split(before).length, 2, `unique mutation point: ${name}`);
      writeFileSync(file, source.replace(before, () => after));
      assert.notEqual(readFileSync(file, "utf8"), source, `the mutant lands: ${name}`);
      const result = spawnSync(process.execPath, ["--test", ...tests.map((t) => join(dir, "test", t))], { encoding: "utf8", timeout: 300000 });
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
