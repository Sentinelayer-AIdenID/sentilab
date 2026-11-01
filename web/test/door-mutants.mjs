// node web/test/door-mutants.mjs
// Mutants of the scoped purpose token's verification and scope (web/src/door/token.js) and of the door's token gate
// (web/src/door/door.js). Each runs in a disposable copy of web/ (the working checkout is never modified) against the
// door's token, route and submit tests, and must fail an assertion there: a mutant that survives, or that only breaks
// an import, fails this script. (Dropping equalHex's length term is an equivalent mutant: TOKEN_PATTERN already fixes
// the MAC at 32 hex characters, so no input can tell the two apart. It is not listed.)
import assert from "node:assert/strict";
import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const TOKEN = "src/door/token.js";
const DOOR = "src/door/door.js";
const mutants = [
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
];

const tests = ["door-token.test.mjs", "door-routes.test.mjs", "door-submit.test.mjs"];
const web = new URL("../", import.meta.url);
let killed = 0;
for (const [name, rel, before, after] of mutants) {
  const dir = mkdtempSync(join(tmpdir(), "door-mutant-"));
  try {
    for (const part of ["src", "public", "test", "scripts"]) cpSync(new URL(`${part}/`, web), join(dir, part), { recursive: true });
    const file = join(dir, ...rel.split("/"));
    const source = readFileSync(file, "utf8");
    assert.equal(source.split(before).length, 2, `unique mutation point: ${name}`);
    writeFileSync(file, source.replace(before, after));
    const result = spawnSync(process.execPath, ["--test", ...tests.map((t) => join(dir, "test", t))], { encoding: "utf8", timeout: 120000 });
    assert.equal(result.status, 1, `${name}: survived (exit ${result.status})\n${result.stdout.slice(-3000)}\n${result.stderr.slice(-2000)}`);
    assert.match(result.stdout, /ERR_ASSERTION/, `${name}: must fail an assertion, not an import or syntax error\n${result.stdout.slice(-3000)}`);
    const first = result.stdout.split("\n").find((line) => /^\s*not ok/.test(line))?.trim();
    console.log(`KILLED ${name}: ${first}`);
    killed += 1;
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}
console.log(`PASS ${killed}/${mutants.length} token and scope mutants fail their behavioral assertions`);
