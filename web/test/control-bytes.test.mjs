// node --test web/test/control-bytes.test.mjs
// No file under web/public or web/test holds a raw control byte below 0x20 other than tab, LF and CR. Such a byte is
// invisible in review and silently changes what the code does: a regex's word boundary that became a raw backspace
// (0x08) matched nothing, and the guard it belonged to was off without failing. Known binary formats are skipped.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, extname, join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

const WEB = join(dirname(fileURLToPath(import.meta.url)), "..");
const ALLOWED = new Set([0x09, 0x0a, 0x0d]);   // tab, LF, CR
const BINARY = new Set([".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".woff", ".woff2", ".ttf", ".otf", ".wasm", ".zip", ".gz", ".pdf"]);

// The offsets of every control byte that isn't tab, LF or CR.
export function controlBytes(bytes) {
  const out = [];
  for (let i = 0; i < bytes.length; i += 1) if (bytes[i] < 0x20 && !ALLOWED.has(bytes[i])) out.push(i);
  return out;
}

function filesUnder(dir) {
  const out = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...filesUnder(full));
    else if (!BINARY.has(extname(entry.name).toLowerCase())) out.push(full);
  }
  return out;
}

test("no file under web/public or web/test holds a control byte other than tab, LF or CR", () => {
  const files = [...filesUnder(join(WEB, "public")), ...filesUnder(join(WEB, "test"))];
  const rel = (f) => relative(WEB, f).split(sep).join("/");
  assert.ok(files.length > 100, "the walk reaches the served files and the tests");
  for (const known of ["public/temperature-label.mjs", "test/temperature-label.test.mjs", "test/control-bytes.test.mjs"]) {
    assert.ok(files.some((f) => rel(f) === known), `the walk reaches ${known}`);
  }
  const findings = files.flatMap((f) => {
    const at = controlBytes(readFileSync(f));
    return at.length ? [`${rel(f)}: ${at.length} control byte(s), first 0x${readFileSync(f)[at[0]].toString(16).padStart(2, "0")} at byte ${at[0]}`] : [];
  });
  assert.deepEqual(findings, []);
});

test("negative control: a backspace, a NUL, an escape and a vertical tab are caught; tab, LF and CR are not", () => {
  const bytes = (...codes) => Uint8Array.from(codes);
  assert.deepEqual(controlBytes(bytes(0x61, 0x09, 0x62, 0x0a, 0x63, 0x0d, 0x0a)), [], "tab, LF and CR are text");
  assert.deepEqual(controlBytes(bytes(0x2f, 0x08, 0x64, 0x2b, 0x08, 0x2f)), [1, 4], "a word boundary turned into backspaces");
  assert.deepEqual(controlBytes(bytes(0x00)), [0]);
  assert.deepEqual(controlBytes(bytes(0x41, 0x1b)), [1]);
  assert.deepEqual(controlBytes(bytes(0x0b, 0x0c, 0x1f, 0x20)), [0, 1, 2], "0x1f is the last control byte; 0x20 is a space");
  // UTF-8 text above 0x7f (the pages' ×, ° and ·) is not a control byte.
  assert.deepEqual(controlBytes(new TextEncoder().encode("a × b · 118.4 °C → ok")), []);
});
