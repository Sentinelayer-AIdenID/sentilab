// node web/test/door-a4-mutants.mjs [group-prefix]
// Mutants of every new rule of AGENT-DOOR Amendment 4 rev 2 at the edge: the opt-in and its display-text rules and caps
// (src/door/declare.js), the purpose step and the heartbeat proxy with its per-IP limit (src/door/door.js, src/worker.js),
// the wall's copy and form (src/door/render.js), and the pages' heartbeat module (public/sentilab/here.mjs). Each runs in
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
const B = String.fromCharCode(92);       // a backslash, so no escape in this file can turn into the character it names
const refused = (ranges) => `const REFUSED = /[${ranges.map(([a, b]) => `${B}u${a}-${B}u${b}`).join("")}]/u;`;
const ALL = [["0000", "001f"], ["007f", "009f"], ["202a", "202e"], ["2066", "2069"]];
const without = (index) => ALL.filter((_, i) => i !== index);

const groups = {
  "display text and caps": [
    ["C0 controls accepted", DECLARE, refused(ALL), refused(without(0))],
    ["C1 controls accepted (DEL only)", DECLARE, refused(ALL), refused([ALL[0], ["007f", "007f"], ALL[2], ALL[3]])],
    ["bidi embeddings and overrides accepted", DECLARE, refused(ALL), refused(without(2))],
    ["bidi isolates accepted", DECLARE, refused(ALL), refused(without(3))],
    ["length counted in UTF-16 units", DECLARE, "return [...text].length > max ? \"too_long\" : null;", "return text.length > max ? \"too_long\" : null;"],
    ["cap off by one", DECLARE, "return [...text].length > max ? \"too_long\" : null;", "return [...text].length >= max ? \"too_long\" : null;"],
    ["name cap 65", DECLARE, "FIELD_LIMITS = Object.freeze({ name: 64, reason: 160 });", "FIELD_LIMITS = Object.freeze({ name: 65, reason: 160 });"],
    ["reason cap 161", DECLARE, "FIELD_LIMITS = Object.freeze({ name: 64, reason: 160 });", "FIELD_LIMITS = Object.freeze({ name: 64, reason: 161 });"],
  ],
  "the opt-in": [
    ["a stale notice version accepted", DECLARE, '  if (versions[0] !== notice.version) return { status: "not_sent", code: "notice_changed" };\n', ""],
    ["two notice versions: the first taken", DECLARE, '  if (versions.length > 1) return { status: "not_sent", code: "field_repeated" };\n', ""],
    ["a repeated field: the first taken", DECLARE, '    if (values.length > 1) return { status: "not_sent", code: "field_repeated" };\n', ""],
    ["an empty field kept", DECLARE, '    if (values.length === 0 || values[0] === "") continue;', "    if (values.length === 0) continue;"],
    ["any source accepted", DECLARE, '(SOURCES.includes(values[0]) ? null : "source_unknown")', "null"],
    ["via fills an absent source", DECLARE, '    if (values.length === 0 || values[0] === "") continue;',
      '    if (values.length === 0 || values[0] === "") { if (field === "source" && viaSource(params)) declaration.source = viaSource(params); continue; }'],
    ["the door declares on the visitor's behalf", DOOR, 'declaration: optIn.status === "sent" ? optIn.declaration : null });',
      'declaration: optIn.status === "sent" ? optIn.declaration : { notice_version: "sentilab-public-visitor/1" } });'],
    ["the opt-in accepted without the intake's notice", DOOR, 'url.searchParams.has("notice_version") ? await sharedNotice(env, url) : null',
      '{ version: url.searchParams.get("notice_version"), text: "x" }'],
    ["the token page echoes the declaration", DOOR, "const page = { declaration: declarationOutcome(optIn), source: viaSource(url.searchParams) };",
      "const page = { declaration: { ...declarationOutcome(optIn), echo: optIn.declaration ?? null }, source: viaSource(url.searchParams) };"],
    ["a notice with controls shown", DECLARE, " || text.length > MAX_NOTICE_CHARS || REFUSED.test(text)) return null;", " || text.length > MAX_NOTICE_CHARS) return null;"],
    ["a notice of version 0 shown", DECLARE, `const NOTICE_VERSION = /^sentilab-public-visitor${B}/[1-9][0-9]{0,5}$/;`, `const NOTICE_VERSION = /^sentilab-public-visitor${B}/[0-9]{1,6}$/;`],
  ],
  "via": [
    ["via takes any slug", DECLARE, "return values.length === 1 && SOURCES.includes(values[0]) ? values[0] : null;", "return values.length === 1 && /^[a-z0-9-]{1,32}$/.test(values[0]) ? values[0] : null;"],
    ["via takes the first of two", DECLARE, "return values.length === 1 && SOURCES.includes(values[0]) ? values[0] : null;", "return values.length >= 1 && SOURCES.includes(values[0]) ? values[0] : null;"],
    ["via does not select the source", RENDER, '${s === source ? " selected" : ""}', ""],
    ["via carried into every next link", RENDER, '[{ name: "board", label: "The board: class, short id and scores", url: `${origin}/agents/board` },',
      '[{ name: "board", label: "The board: class, short id and scores", url: `${origin}/agents/board${source ? `?via=${source}` : ""}` },'],
  ],
  "the wall's form and copy": [
    ["the opt-in pre-ticked", RENDER, '<input type="checkbox" name="notice_version" value="${esc(notice.version)}">', '<input type="checkbox" name="notice_version" value="${esc(notice.version)}" checked>'],
    ["the notice not escaped", RENDER, '<blockquote class="notice">${esc(notice.text)}</blockquote>', '<blockquote class="notice">${notice.text}</blockquote>'],
    ["the old wall line", RENDER, "export const RECORDED = \"What we record: a guess at your assistant's type, and the time of this visit.",
      "export const RECORDED = \"What we record: your assistant's type and the time of this visit."],
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
  "the per-IP limit": [
    ["windows never end", DOOR, "    if (now - window.start < HERE_LIMIT.periodMs) break;", "    break;"],
    ["one window for everyone", DOOR, "if (!hereAllow(`here:${prefixOf(request)}`, Date.now()))", "if (!hereAllow(\"here:all\", Date.now()))"],
    ["the limit off by one", DOOR, "  if (window.count >= HERE_LIMIT.limit) return false;", "  if (window.count > HERE_LIMIT.limit) return false;"],
    ["a window of 120 s", DOOR, "export const HERE_LIMIT = Object.freeze({ limit: 300, periodMs: 60000 });", "export const HERE_LIMIT = Object.freeze({ limit: 300, periodMs: 120000 });"],
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
