// node --test web/test/package3d-vendor.test.mjs
// The vendored three.js build is exactly the pinned release (sha256 per file, as web/public/vendor/three/0.187.0/
// VERSION.txt records), it is reached only through render3d.mjs at that pinned path, and the Package view's own code
// stays inside the page's Content-Security-Policy: no inline code, no eval, no markup from strings, no other origin.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const PUBLIC = join(here, "..", "public");
const VENDOR = join(PUBLIC, "vendor", "three", "0.187.0");
const PKG = join(PUBLIC, "sentilab", "package");
const sha = (p) => createHash("sha256").update(readFileSync(p)).digest("hex");
const PINS = Object.freeze({
  "three.module.js": ["104f56145899722094556490d787aae0617cc2fc3382f31df02d724ea1aee341", 658900],
  "three.core.js": ["613e370f76638fdef83926642bf256dc9615684922de1ce1f63a8583e5d78578", 1474799],
  LICENSE: ["8b378ebe60e2fe500158cb0ac71cb5e8b7d92953c2abcc63a0eb90499653b5bc", 1081],
});

test("every vendored file is byte-identical to the pinned release, and VERSION.txt records the same hashes", () => {
  assert.deepEqual(readdirSync(VENDOR).sort(), ["LICENSE", "VERSION.txt", "three.core.js", "three.module.js"], "nothing else is vendored");
  const note = readFileSync(join(VENDOR, "VERSION.txt"), "utf8");
  for (const [file, [hash, bytes]] of Object.entries(PINS)) {
    assert.equal(sha(join(VENDOR, file)), hash, file);
    assert.equal(readFileSync(join(VENDOR, file)).length, bytes, file);
    assert.match(note, new RegExp(`${file.replace(".", "\\.")}\\s.*\\b${bytes} bytes\\s+sha256 ${hash}`), `VERSION.txt pins ${file}`);
  }
  assert.match(note, /tarball sha256\s+ff540832ded0cfe919764d24a3d88f3e2a05f23303f876423e4f893841e90728/);
  assert.match(readFileSync(join(VENDOR, "LICENSE"), "utf8"), /^The MIT License\n\nCopyright © 2010-2026 three\.js authors/);
});

test("three.module.js imports only ./three.core.js; three.core.js imports nothing", () => {
  const specifiers = (src) => [...src.matchAll(/^\s*(?:import|export)\b[^;'"]*?\bfrom\s*['"]([^'"]+)['"]/gm)].map((m) => m[1]);
  assert.deepEqual([...new Set(specifiers(readFileSync(join(VENDOR, "three.module.js"), "utf8")))], ["./three.core.js"]);
  const core = readFileSync(join(VENDOR, "three.core.js"), "utf8");
  assert.deepEqual(specifiers(core), []);
  assert.doesNotMatch(core, /^\s*import\s*\(/m, "no dynamic import");
});

test("only render3d.mjs reaches three.js, lazily, at the pinned version path; no page module names another origin", () => {
  const mods = readdirSync(PKG).filter((f) => /\.(m?js)$/.test(f));
  for (const f of mods) {
    const src = readFileSync(join(PKG, f), "utf8");
    const reaches = /vendor\/three/.test(src);
    assert.equal(reaches, f === "render3d.mjs", `${f} ${reaches ? "reaches" : "does not reach"} the vendored build`);
    assert.doesNotMatch(src, /\bfrom\s*["']https?:|import\(\s*["']https?:/, `${f}: no remote module`);
    assert.doesNotMatch(src, /\bfrom\s*["']three["']/, `${f}: no bare specifier (no import map)`);
  }
  const r3 = readFileSync(join(PKG, "render3d.mjs"), "utf8");
  assert.match(r3, /export const THREE_VERSION = "0\.187\.0";/);
  assert.match(r3, /const THREE_URL = new URL\(`\.\.\/\.\.\/\.\.\/vendor\/three\/\$\{THREE_VERSION\}\/three\.module\.js`, import\.meta\.url\)\.href;/);
  assert.match(r3, /const THREE = await import\(THREE_URL\);/, "loaded with a dynamic import, only when 3D starts");
  assert.doesNotMatch(r3, /^import .*three/m, "never a static import");
});

test("the Package view's code stays inside the CSP: no inline code, no eval, no markup from strings", () => {
  const html = readFileSync(join(PKG, "index.html"), "utf8");
  assert.deepEqual(html.match(/<script\b[^>]*>/g), ['<script type="module" src="package.js">'], "one script, external");
  assert.doesNotMatch(html, /<script\b[^>]*>[^<\s]/, "no inline script body");
  assert.doesNotMatch(html, /<style\b|\sstyle\s*=|\son[a-z]+\s*=/i, "no style element, style attribute or inline handler");
  for (const f of ["door.mjs", "render3d.mjs", "model.mjs", "source3d.mjs", "case-cpu-dram.mjs", "temps.mjs"]) {
    const src = readFileSync(join(PKG, f), "utf8");
    assert.doesNotMatch(src, /\beval\s*\(|new Function\b|\bFunction\s*\(|innerHTML|outerHTML|insertAdjacentHTML|document\.write|setAttribute\(\s*["']style|\.cssText\b|toDataURL|toBlob/, f);
  }
});

test("the agent twin stub: sentilab-twin/1, every required key, no temperatures, and current hashes of what it was built from", () => {
  const twin = JSON.parse(readFileSync(join(PUBLIC, "agents", "package3d", "index.json"), "utf8"));
  assert.deepEqual(Object.keys(twin).sort(), ["built_from", "content", "data", "derivatives", "frame", "labels", "omitted", "schema", "status_text", "view_transforms"]);
  assert.equal(twin.schema, "sentilab-twin/1");
  assert.equal(twin.content, "model");
  assert.equal(twin.status_text, "Our model · the layers and blocks our thermal solver actually simulates, with its simplifications. Not the real package.");
  assert.equal(twin.view_transforms, "Explode, readable thickening and section are view transforms. Every coordinate here is assembled.");
  assert.ok(twin.built_from.length >= 1);
  for (const f of twin.built_from) assert.equal(sha(join(here, "..", "..", f.path)), f.sha256, `${f.path} changed: rebuild the twin`);
  assert.deepEqual(twin.derivatives, []);
  for (const o of twin.omitted) assert.deepEqual(Object.keys(o).sort(), ["what", "why"]);
  const text = JSON.stringify(twin.data);
  assert.doesNotMatch(text, /°C|temp|_C"|peak|grid64/i, "a static twin carries no temperatures");
  assert.ok(!readFileSync(join(PUBLIC, "agents", "package3d", "index.md"), "utf8").match(/\d\s*°C/), "nor does its page");
});
