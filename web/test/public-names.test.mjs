// node --test web/test/public-names.test.mjs
// Public naming rule for everything the site serves from web/public: no vendor, product or model names, and no internal
// agent handles, in the pages, their scripts and styles, or the data they render. licenses.html and licenses/ are
// excluded: third-party license texts must name their authors. Matching is case-insensitive and word-bounded.
//   - HTML, JS, MJS, CSS, SVG, TXT and MD are scanned whole (markup, copy, comments and code: all of it is public).
//   - JSON and JSONL are parsed and every key and string value is scanned, except cryptographic blobs (signatures,
//     keys, hashes), whose random letters can spell anything.
//   - "root" is a handle only in page copy (HTML); in code it is a plain word (a tree's root, a public root key).
// Two narrow, named exceptions, each checked so it can't grow:
//   - app.js plain(): the sanitizer that replaces the signal model's name in record text before it reaches the page.
//   - tfl08/leaderboard.json signal_pricing: imported, pinned evidence (PROVENANCE.json) whose pricing note names the
//     provider; leaderboard.js never reads that field, and the test fails if it starts to.
//   - vendor/three/0.187.0/three.core.js: the vendored three.js build (byte-identical to its release, pinned by sha256
//     in package3d-vendor.test.mjs) holds one source comment that links to a vendor's issue tracker. Exactly that
//     line, exactly once, in exactly that file; any other hit in it, or the line anywhere else, still fails.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, extname, join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

const PUBLIC = join(dirname(fileURLToPath(import.meta.url)), "..", "public");
export const NAMES = [
  // vendors, products and models
  "typesafe", "jev", "system\\s*one", "cloudflare", "openai", "chatgpt", "gpt", "claude", "anthropic", "grok", "kimi", "gemini",
  "deepseek", "qwen", "llama", "mistral", "microduck", "pollen",
  // internal agent handles
  "warden", "astra", "forge", "pocket-forge", "claude-warden", "gpt-astra", "aneta", "codex", "nightshift", "fable",
].map((n) => new RegExp(`(?<![\\w-])${n}(?![\\w])`, "i"));
const ROOT_HANDLE = /(?<![\w-])root(?![\w])/i;          // HTML copy only
const ROOM = /\broot ?0\d\d\b/i;                        // everywhere
const BLOB = /^[A-Za-z0-9+/=_-]{32,}$/;                 // base64 / base64url / hex: signatures, keys, hashes
const SANITIZER = "/\\bjev\\b[-\\w.]*/gi";                // app.js plain(), allowed exactly once, in app.js only
export const THREE_CORE = "vendor/three/0.187.0/three.core.js";
export const THREE_CORE_COMMENT = "\n\t// https://github.com/cloudflare/workerd/issues/3657\n";   // line 45192, allowed exactly once

export function scanText(text, { html = false } = {}) {
  return [...NAMES, ROOM, ...(html ? [ROOT_HANDLE] : [])].filter((re) => re.test(text)).map((re) => re.source);
}
function scanJson(value, path, hits, skip = () => false) {
  if (skip(path)) return;
  if (typeof value === "string") { if (!BLOB.test(value)) for (const h of scanText(value)) hits.push(`${path}: ${h}`); return; }
  if (Array.isArray(value)) { value.forEach((v, i) => scanJson(v, `${path}[${i}]`, hits, skip)); return; }
  if (value && typeof value === "object") {
    for (const [k, v] of Object.entries(value)) {
      for (const h of scanText(k)) hits.push(`${path}.${k} (key): ${h}`);
      scanJson(v, `${path}.${k}`, hits, skip);
    }
  }
}
// Every finding for one served file: [] when it is clean.
export function scanFile(rel, text) {
  const ext = extname(rel).toLowerCase();
  if ([".html", ".js", ".mjs", ".css", ".svg", ".txt", ".md"].includes(ext)) {
    let body = text;
    if (rel === "app.js") {
      assert.equal(body.split(SANITIZER).length - 1, 1, "app.js holds the sanitizer exactly once");
      assert.match(body, /const plain = \(t\) => String\(t == null \? "" : t\)\.replace\(\/\\bjev\\b\[-\\w\.\]\*\/gi, "signal layer"\);/, "the sanitizer only replaces the name");
      body = body.replace(SANITIZER, "/SANITIZER/gi");
    }
    if (rel === THREE_CORE) {
      assert.equal(body.split(THREE_CORE_COMMENT).length - 1, 1, "three.core.js holds the pinned comment exactly once");
      body = body.replace(THREE_CORE_COMMENT, "\n\t// (pinned vendor comment)\n");
    }
    return scanText(body, { html: ext === ".html" }).map((h) => `${rel}: ${h}`);
  }
  if (ext === ".json" || ext === ".jsonl") {
    const hits = [];
    const docs = ext === ".json" ? [JSON.parse(text)] : text.split("\n").filter(Boolean).map((line) => JSON.parse(line));
    const skip = rel === "tfl08/leaderboard.json" ? (path) => /^\$\.benchmarks\.[^.]+\.signal_pricing$/.test(path) : () => false;
    docs.forEach((doc, i) => scanJson(doc, docs.length > 1 ? `$${i}` : "$", hits, skip));
    return hits.map((h) => `${rel} ${h}`);
  }
  return [];
}
function served() {
  const out = [];
  const walk = (dir) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name);
      const rel = relative(PUBLIC, full).split(sep).join("/");
      if (rel === "licenses.html" || rel === "licenses" || rel.startsWith("licenses/")) continue;
      if (entry.isDirectory()) walk(full); else out.push(rel);
    }
  };
  walk(PUBLIC);
  return out.sort();
}

test("no vendor, model or internal names in any served public page, script, style or rendered data (licenses excluded)", () => {
  const files = served();
  assert.ok(files.includes("index.html") && files.includes("sentilab/index.html") && files.includes("sentilab/package/index.html") && files.includes("tfl08/leaderboard.json") && files.includes("agents/index.md") && files.includes("llms.txt"), "the walk reaches the pages, the data and the agent pages");
  const findings = files.flatMap((rel) => scanFile(rel, readFileSync(join(PUBLIC, rel), "utf8")));
  assert.deepEqual(findings, []);
});

test("the leaderboard exception stays unrendered: leaderboard.js never reads signal_pricing", () => {
  assert.ok(!readFileSync(join(PUBLIC, "leaderboard.js"), "utf8").includes("signal_pricing"));
});

test("negative control: seeded names are caught in every file kind; blobs and plain words are not", () => {
  const page = readFileSync(join(PUBLIC, "index.html"), "utf8");
  assert.deepEqual(scanFile("index.html", page), [], "the real page is clean");
  const seeded = [
    ["index.html", page.replace("Our signal layer", "The signal layer (TypeSafe System One)")],
    ["index.html", page.replace("</body>", "<p>Ask Root 088</p></body>")],
    ["index.html", page.replace("</body>", "<p>reviewed by root</p></body>")],
    ["sentilab/view-pins.js", "// provisioned by claude-warden\n"],
    ["sentilab/view-core.mjs", "// reference by pocket-forge\n"],
    ["styles.css", "/* colours from Gemini */\n"],
    ["agents/physics.md", "Reviewed by astra.\n"],
    ["replay/run.json", JSON.stringify({ reason: "jev-1.2 timed out" })],
    ["replay/run.json", JSON.stringify({ note: { "powered by OpenAI": 1 } })],
    ["sentilab/demo-run.jsonl", `${JSON.stringify({ a: 1 })}\n${JSON.stringify({ body: { note: "GPT-4o chose swap" } })}\n`],
    ["tfl08/leaderboard.json", JSON.stringify({ benchmarks: { x: { signal_pricing: { source: "ok here" }, label: "Claude says hi" } } })],
    ["app.js", `const plain = (t) => String(t == null ? "" : t).replace(/\\bjev\\b[-\\w.]*/gi, "signal layer");\n// Jev again\n`],
  ];
  for (const [rel, text] of seeded) assert.ok(scanFile(rel, text).length > 0, `${rel}: ${text.slice(0, 60)}`);
  // Precision: random signature letters, code words and allowed names stay clean.
  assert.deepEqual(scanFile("tfl08/records/x.json", JSON.stringify({ signature: "AeYocYlz4T5/7v/ezAInE6QkmGtRSFlDttXUF+gPTCuYPTuJVLQIMNm", sig: "JevOOUvCwSsi2fOzdeXdMJ3sQnZiPTB5J4A0zfCxIFxSQ3338DU5fE2TbGF" })), []);
  assert.deepEqual(scanFile("verify-core.js", "const root = pins[id]; // the public root key\nfunction forgery() {}\n"), []);
  assert.deepEqual(scanFile("index.html", "<p>SUNDAI · TRACK 02 · HotSpot 7 · Ascend910</p>"), []);
  assert.deepEqual(scanFile("tfl08/leaderboard.json", JSON.stringify({ benchmarks: { x: { signal_pricing: { source: "https://typesafe.ai/" } } } })), [], "the named exception");
  // The vendored three.js exception covers one line in one file, once.
  assert.deepEqual(scanFile(THREE_CORE, `a${THREE_CORE_COMMENT}b`), [], "the pinned three.core.js comment");
  assert.ok(scanFile(THREE_CORE, `a${THREE_CORE_COMMENT}b // made by Claude\n`).length > 0, "another name in three.core.js still fails");
  assert.ok(scanFile("vendor/three/0.187.0/three.module.js", `a${THREE_CORE_COMMENT}b`).length > 0, "the line in another file still fails");
  assert.throws(() => scanFile(THREE_CORE, `a${THREE_CORE_COMMENT}${THREE_CORE_COMMENT}b`), /exactly once/, "a second copy fails");
});
