// node web/test/door-a4-mutants.mjs [group-prefix]
// Mutants of every new rule of AGENT-DOOR Amendment 4 rev 2 at the edge: the opt-in and its display-text rules and caps
// (src/door/declare.js, with its generated Unicode 16.0 tables in src/door/unicode16.js), the JSON path's well-formed
// strings, the off switch DOOR_DECLARATIONS, the purpose step and the heartbeat proxy with its per-IP limit
// (src/door/door.js, src/worker.js), the wall's copy and form (src/door/render.js), the heartbeat limiter's binding and
// the shipped switch (wrangler.jsonc), the opt-in's delivery, and the pages' heartbeat module
// (public/sentilab/here.mjs). Each runs in
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
// The Unicode 16.0 tables are generated (src/door/unicode16.js, from the API's unicodedata2): a mutant drops a range
// from one, as a hand edit or a stale table would. The Hangul fillers U+115F, U+1160, U+3164 and U+FFA0 are
// default-ignorable too, so dropping one from REFUSED alone is an equivalent mutant (DEFAULT_IGNORABLE still refuses
// it); U+2800 is not default-ignorable.
const U16 = "src/door/unicode16.js";
const CATEGORIES = ["Cc", "Cf", "Co", "Cs", "Cn", "Zl", "Zp"];

const groups = {
  "the character policy (root's shared rule, Unicode 16.0)": [
    ["Cc accepted (U+0000-001F dropped from REFUSED)", U16, `export const REFUSED = Object.freeze([${NL}  0x0000, 0x001F, `, `export const REFUSED = Object.freeze([${NL}  `],
    ["Cf and Cn accepted (U+05F5-0605 dropped)", U16, "0x05F5, 0x0605, ", ""],
    ["Cs, Co and Cn accepted (U+D7FC-F8FF dropped)", U16, "0xD7FC, 0xF8FF, ", ""],
    ["Cn accepted (U+20C1-20CF, unassigned in 16.0, dropped)", U16, "0x20C1, 0x20CF,", ""],
    ["Zl and Zp accepted (U+2028-202E dropped)", U16, "0x2028, 0x202E, ", ""],
    ["the blank Braille filler U+2800 accepted", U16, "0x2800, 0x2800, ", ""],
    ["a mark range dropped (U+0300-036F)", U16, `export const MARKS = Object.freeze([${NL}  0x0300, 0x036F, `, `export const MARKS = Object.freeze([${NL}  `],
    ["the default-ignorables not checked", DECLARE, "const refusedCode = (code) => inRanges(REFUSED, code) || inRanges(DEFAULT_IGNORABLE, code);",
      "const refusedCode = (code) => inRanges(REFUSED, code);"],
    ["the variation selectors U+FE00-FE0F accepted", DECLARE, "0xFE00, 0xFE0F, ", ""],
    ["the supplementary variation selectors U+E0100-E01EF accepted", DECLARE, "0xE0000, 0xE0FFF]", "0xE0000, 0xE00FF]"],
    ["the engine's Unicode 17.0 categories again", DECLARE, "const refusedCode = (code) => inRanges(REFUSED, code) || inRanges(DEFAULT_IGNORABLE, code);",
      `const refusedCode = (code) => /[${CATEGORIES.map((c) => `${B}p{${c}}`).join("")}]/u.test(String.fromCodePoint(code)) || [0x115f, 0x1160, 0x3164, 0xffa0, 0x2800].includes(code) || inRanges(DEFAULT_IGNORABLE, code);`],
    ["the engine's Unicode 17.0 marks again", DECLARE, "    run = inRanges(MARKS, code) ? run + 1 : 0;", `    run = /^${B}p{M}$/u.test(String.fromCodePoint(code)) ? run + 1 : 0;`],
    ["the binary search misses each table's last range", DECLARE, "  let high = table.length / 2 - 1;", "  let high = table.length / 2 - 2;"],
    ["categories judged after normalising (a tag payload stripped, then accepted)", DECLARE, "  const codes = Array.from(text, (char) => char.codePointAt(0));",
      "  const codes = Array.from(nameKey(text), (char) => char.codePointAt(0));"],
    ["a run of 9 marks allowed", DECLARE, "export const MAX_MARK_RUN = 8;", "export const MAX_MARK_RUN = 9;"],
    ["mark runs never reset (a total quota)", DECLARE, "run = inRanges(MARKS, code) ? run + 1 : 0;", "run = inRanges(MARKS, code) ? run + 1 : run;"],
    ["mark runs not checked", DECLARE, '    if (run > MAX_MARK_RUN) return "combining_marks";', ""],
    ["length counted in UTF-16 units", DECLARE, "return codes.length > max ? \"too_long\" : null;", "return text.length > max ? \"too_long\" : null;"],
    ["cap off by one", DECLARE, "return codes.length > max ? \"too_long\" : null;", "return codes.length >= max ? \"too_long\" : null;"],
    ["name cap 65", DECLARE, "FIELD_LIMITS = Object.freeze({ name: 64, reason: 160 });", "FIELD_LIMITS = Object.freeze({ name: 65, reason: 160 });"],
    ["reason cap 161", DECLARE, "FIELD_LIMITS = Object.freeze({ name: 64, reason: 160 });", "FIELD_LIMITS = Object.freeze({ name: 64, reason: 161 });"],
    ["a blank field accepted", DECLARE, '    if (field !== "source" && nameKey(values[0]) === "") return { status: "not_sent", code: "blank" };' + NL, ""],
    ["blank checked on the name only", DECLARE, 'if (field !== "source" && nameKey(values[0]) === "")', 'if (field === "name" && nameKey(values[0]) === "")'],
  ],
  "well-formed strings on the JSON path": [
    ["the check removed (a lone surrogate becomes U+FFFD and passes)", DOOR,
      "  const illFormed = entries.filter(([k, v]) => DECLARED_TEXT.includes(k) && !v.isWellFormed()).map(([k]) => k);", "  const illFormed = [];"],
    ["only the name checked", DOOR, 'const DECLARED_TEXT = Object.freeze(["name", "reason", "source"]);', 'const DECLARED_TEXT = Object.freeze(["name"]);'],
    ["the finding not passed on", DOOR, "  const optIn = readOptIn(params, fields.illFormed);", "  const optIn = readOptIn(params);"],
    ["an ill-formed field not refused", DECLARE, '    if (illFormed.includes(field)) return { status: "not_sent", code: "control_character" };' + NL, ""],
  ],
  "reserved names (defense in depth)": [
    ["reserved names accepted", DECLARE, '    if (field === "name" && RESERVED_NAMES.includes(nameKey(values[0]))) return { status: "not_sent", code: "reserved_name" };', ""],
    ["the rule on reason, not name", DECLARE, 'if (field === "name" && RESERVED_NAMES', 'if (field === "reason" && RESERVED_NAMES'],
    ["a reserved label missing", DECLARE, '  "moderator"]);', '  "moderators"]);'],
    ["compared without NFKC", DECLARE, 'Array.from(name.normalize("NFKC"))', "Array.from(name)"],
    ["compared case-sensitively", DECLARE, ".trim().toLowerCase();", ".trim();"],
    ["compared untrimmed", DECLARE, ".trim().toLowerCase();", ".toLowerCase();"],
    ["whitespace runs kept", DECLARE, `.replace(/${B}s+/gu, " ")`, ""],
    ["format characters kept", DECLARE, '.filter((char) => !inRanges(FORMAT, char.codePointAt(0)))', ""],
    ["the comparison's format table loses U+200B-200F", U16, "0x180E, 0x180E, 0x200B, 0x200F, ", "0x180E, 0x180E, "],
    ["a refusal here reads not_sent", DECLARE, 'if (optIn.status === "not_sent") return { status: "not_recorded", code: optIn.code',
      'if (optIn.status === "not_sent") return { status: "not_sent", code: optIn.code'],
  ],
  "the off switch (DOOR_DECLARATIONS, shipped off)": [
    ["on unless \"off\"", DOOR, 'export const declarationsOn = (env) => env?.DOOR_DECLARATIONS === "on";', 'export const declarationsOn = (env) => env?.DOOR_DECLARATIONS !== "off";'],
    ["on in any case or padding", DOOR, 'export const declarationsOn = (env) => env?.DOOR_DECLARATIONS === "on";',
      'export const declarationsOn = (env) => String(env?.DOOR_DECLARATIONS).trim().toLowerCase() === "on";'],
    ["the declare route routed when off", DOOR, '  if (pathname === "/agents/declare") return declarationsOn(env) ? DECLARE_ROUTE : null;',
      '  if (pathname === "/agents/declare") return DECLARE_ROUTE;'],
    ["the wall offers the opt-in when off", DOOR, "  const options = declarationsOn(env) ? { source: viaSource(url.searchParams), declarations: true } : {};",
      "  const options = { source: viaSource(url.searchParams), declarations: true };"],
    ["via carried when off", DOOR, "  const options = declarationsOn(env) ? { source: viaSource(url.searchParams), declarations: true } : {};",
      "  const options = declarationsOn(env) ? { source: viaSource(url.searchParams), declarations: true } : { source: viaSource(url.searchParams) };"],
    ["the token page offers it when off", DOOR, "  const page = !declarationsOn(env) ? {} : {", "  const page = false ? {} : {"],
    ["the ENGRAM view offers it when off", DOOR, "  const declare = !declarationsOn(env) ? null : declareObject(", "  const declare = false ? null : declareObject("],
    ["the 405 text names the declare route when off", DOOR, "    const detail = declarationsOn(env) ?", "    const detail = true ?"],
    ["the wall's page on by default", RENDER, "export function wallHtml(origin, submissions, { source = null, declarations = false } = {}) {",
      "export function wallHtml(origin, submissions, { source = null, declarations = true } = {}) {"],
    ["the wall's markdown on by default", RENDER, "export function wallMarkdown(origin, submissions, { source = null, declarations = false } = {}) {",
      "export function wallMarkdown(origin, submissions, { source = null, declarations = true } = {}) {"],
    ["the wall's JSON on by default", RENDER, "export function wallJson(origin, submissions, { source = null, declarations = false } = {}) {",
      "export function wallJson(origin, submissions, { source = null, declarations = true } = {}) {"],
    ["the token JSON keeps a declaration field when off", RENDER, "declare: declareObject(origin, { token, key: declare.key, source }) } : {}) };",
      'declare: declareObject(origin, { token, key: declare.key, source }) } : { declaration: { status: "not_given" } }) };'],
    ["the Worker routes without its env", WORKER, "    const door = doorRoute(pathname, env);", '    const door = doorRoute(pathname, { DOOR_DECLARATIONS: "on" });'],
    ["production ships it on", WRANGLER, '    "DOOR_DECLARATIONS": "off" },', '    "DOOR_DECLARATIONS": "on" },'],
    ["staging ships it on", WRANGLER, '"AQUARIUM_POST": "off", "DOOR_DECLARATIONS": "off" },', '"AQUARIUM_POST": "off", "DOOR_DECLARATIONS": "on" },'],
  ],
  "the opt-in: only a POST bound to the pass": [
    ["a GET records a declaration", DOOR, "  emitArrival(request, env, ctx, url, { purpose, nonce: claims.nonce, expiresAt: claims.expires_at });",
      '  emitArrival(request, env, ctx, url, { purpose, nonce: claims.nonce, expiresAt: claims.expires_at, ...(readOptIn(url.searchParams).status === "opted_in" ? { declaration: readOptIn(url.searchParams).declaration } : {}) });'],
    ["the declare route takes a GET", DOOR, 'const DECLARE_ROUTE = Object.freeze({ methods: ["POST"], handler: declare });',
      'const DECLARE_ROUTE = Object.freeze({ methods: ["GET", "HEAD", "POST"], handler: declare });'],
    ["a cross-site form accepted", DOOR, '  if (form && !ownPageForm(request, url)) return refuse(request, format, 403, { error: "cross_site" });', ""],
    ["a user-typed form (Sec-Fetch-Site: none) accepted", DOOR, 'const ownPageForm = (request, url) => request.headers.get("sec-fetch-site") !== "none" && sameSiteForm(request, url);',
      "const ownPageForm = (request, url) => sameSiteForm(request, url);"],
    ["the declare form's site not checked", DOOR, 'const ownPageForm = (request, url) => request.headers.get("sec-fetch-site") !== "none" && sameSiteForm(request, url);',
      'const ownPageForm = (request, url) => request.headers.get("sec-fetch-site") !== "none";'],
    ["another site's Origin accepted (the shared fallback)", DOOR, `  if (site !== null) return site === "same-origin" || site === "none";${NL}  return request.headers.get("origin") === url.origin;`,
      `  if (site !== null) return site === "same-origin" || site === "none";${NL}  return true;`],
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
  "the declare key's construction": [
    ["the declare key truncated to 8 hex", TOKEN, '["sentilab-declare/1", site, nonce, version])))).slice(0, 32);', '["sentilab-declare/1", site, nonce, version])))).slice(0, 8).padEnd(32, "0");'],
    ["the declare key under another domain tag", TOKEN, 'JSON.stringify(["sentilab-declare/1", site, nonce, version])', 'JSON.stringify(["sentilab-spt1", site, nonce, version])'],
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
    ["the confirm page stays no-referrer (an old browser's POST would carry Origin: null)", RENDER,
      "(text.includes(SUBMIT_FORM) || text.includes(DECLARE_FORM))", "(text.includes(SUBMIT_FORM))"],
    ["the old wall line", RENDER, "export const RECORDED = \"What we record: a guess at your assistant's type, and the time of this visit.",
      "export const RECORDED = \"What we record: your assistant's type and the time of this visit."],
  ],
  "via": [
    ["via takes any slug", DECLARE, "return values.length === 1 && SOURCES.includes(values[0]) ? values[0] : null;", "return values.length === 1 && /^[a-z0-9-]{1,32}$/.test(values[0]) ? values[0] : null;"],
    ["via takes the first of two", DECLARE, "return values.length === 1 && SOURCES.includes(values[0]) ? values[0] : null;", "return values.length >= 1 && SOURCES.includes(values[0]) ? values[0] : null;"],
    ["via carried into every next link", RENDER, '{ name: "board", label: "The board: class, short id and scores", url: `${origin}/agents/board` },',
      '{ name: "board", label: "The board: class, short id and scores", url: `${origin}/agents/board${source ? `?via=${source}` : ""}` },'],
  ],
  "the heartbeat proxy": [
    ["any method", DOOR, '  if (request.method !== "POST") return hereAnswer(request, 405, { error: "method_not_allowed" }, { allow: "POST" });\n', ""],
    ["cross-site accepted", DOOR, `  if (site !== null) return site === "same-origin";${NL}  const origin = `, `  if (site !== null) return true;${NL}  const origin = `],
    ["same-site accepted", DOOR, `  if (site !== null) return site === "same-origin";${NL}  const origin = `, `  if (site !== null) return site !== "cross-site";${NL}  const origin = `],
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

const tests = ["door-a4.test.mjs", "here.test.mjs", "door-routes.test.mjs", "door-declaration-u16.test.mjs", "door-declarations-off.test.mjs"];
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
