// node --test web/test/livelab-honesty.test.mjs
// The Live Lab page ships none of the approved prototype's fixtures: no sample journey or named agents, no hardcoded
// reference score used as a live value, no illustrative heat, no random walks, no fixture fallback, and it keeps the
// standing notice and the "simulated, not silicon" claim. Its markup holds no inline code (the site CSP), and every
// asset and API path is absolute, so the page also works when served as the front door (/ redirected or rewritten).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync, existsSync } from "node:fs";
import { dirname, join, resolve, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { NOTICE } from "../public/temperature-label.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const PUBLIC = join(HERE, "..", "public");
const LIVE = join(PUBLIC, "sentilab", "live");
const files = readdirSync(LIVE).map((f) => join(LIVE, f));
const text = (p) => readFileSync(p, "utf8");

test("the live directory holds only the page's own files (no portable preview, no prototype modules)", () => {
  assert.deepEqual(readdirSync(LIVE).sort(), ["index.html", "live-model.mjs", "live.css", "live.mjs", "mark.svg"]);
  assert.equal(existsSync(join(LIVE, "portable-preview.html")), false);
});

test("none of the prototype's fixture names, numbers, labels or random walks appear in shipped files", () => {
  const banned = [
    [/\bastra\b/i, "a sample agent name"], [/\bforge\b/i, "a sample agent name"], [/\baneta\b/i, "a sample agent name"], [/\bwarden\b/i, "a sample agent name"],
    [/illustrative/i, "the prototype's illustrative heat and replay"], [/115\.9[34]/, "the prototype's hardcoded reference readout"], [/119\.07/, "a hardcoded peak"],
    [/\b241\b/, "the prototype's comparison readout"], [/Math\.random/, "a random walk"], [/sample-00\d/, "sample event ids"], [/00:48/, "the 48 s sample clock"],
    [/sample (event )?replay/i, "the sample replay"], [/design preview/i, "the preview badge"], [/sentilab\.preview\.event/, "the fixture event schema"],
    [/createAgentMap|createPackageView|agent-map\.js|package-view\.js/, "the prototype's modules"], [/fonts\.googleapis|fonts\.gstatic/, "external fonts"],
    [/https?:\/\//, "an absolute external URL"], [/45 × 45 mm.*reconstructed/i, "the reconstructed footprint claim"],
  ];
  for (const p of files) {
    const body = text(p).replaceAll("http://www.w3.org/2000/svg", "");   // the SVG namespace is a name, not a link
    for (const [re, why] of banned) {
      assert.equal(re.test(body), false, `${relative(PUBLIC, p)}: ${why} (${re})`);
    }
  }
});

// The modules the page loads, followed from live.mjs through every static and dynamic import, except the pinned
// three.js build (vendored byte for byte, sha256-pinned elsewhere; its UUID helper is not page data).
function importGraph(entry) {
  const seen = new Set();
  const visit = (file) => {
    if (seen.has(file)) return;
    seen.add(file);
    const src = text(file);
    for (const m of src.matchAll(/(?:import|export)\s[^"'`;]*?from\s*["']([^"']+)["']|import\(\s*["']([^"']+)["']\s*\)/g)) {
      const spec = m[1] ?? m[2];
      if (!spec.startsWith(".")) continue;
      const target = resolve(dirname(file), spec);
      if (target.includes(join("vendor", "three"))) continue;
      visit(target);
    }
  };
  visit(entry);
  return [...seen];
}

test("the live path: no randomness, no fixture fallback, no door-page controller", () => {
  const graph = importGraph(join(LIVE, "live.mjs"));
  const rel = graph.map((p) => relative(PUBLIC, p).split("\\").join("/")).sort();
  assert.ok(rel.includes("sentilab/package/source3d.mjs") && rel.includes("sentilab/package/model.mjs") && rel.includes("sentilab/package/render3d.mjs"), rel.join(", "));
  assert.equal(rel.includes("sentilab/package/door.mjs"), false, "the door page's controller (its fixture fallback) is not imported");
  assert.equal(rel.includes("sentilab/package/package.js"), false);
  for (const p of graph) assert.equal(/Math\.random/.test(text(p)), false, `${relative(PUBLIC, p)}: Math.random on the live path`);
  const own = text(join(LIVE, "live.mjs")) + text(join(LIVE, "live-model.mjs"));
  assert.equal(/loadFixture|door-fixture|FIXTURE_URL|demo-run/.test(own), false, "the page never loads a bundled fixture");
  assert.match(own, /createDoorFeed\(/, "one door-feed subscription");
  assert.equal((text(join(LIVE, "live.mjs")).match(/createDoorFeed\(/g) ?? []).length, 1, "exactly one subscription");
});

test("the standing notice and the claim are on the page", () => {
  const page = text(join(LIVE, "live.mjs"));
  assert.match(page, /import \{ NOTICE \} from "\.\.\/\.\.\/temperature-label\.mjs"/, "the shared notice, worded as on the Package view");
  assert.match(page, /\$\("wnotice"\)\.textContent = NOTICE/);
  assert.ok(NOTICE.startsWith("These simulated temperatures are under review"));
  const html = text(join(LIVE, "index.html"));
  assert.match(html, /<p class="wnotice" id="wnotice" role="note"><\/p>/, "the notice is never hidden");
  assert.match(page + text(join(LIVE, "live-model.mjs")), /simulated, not silicon/);
  assert.match(html, /disabled aria-describedby="fieldNote">Thermal view</, "the thermal view starts disabled: no field until a verified one exists");
});

test("CSP-safe markup and front-door-safe paths", () => {
  const html = text(join(LIVE, "index.html"));
  assert.equal(/<script(?![^>]*\bsrc=)[^>]*>/i.test(html), false, "no inline script");
  assert.equal(/<style/i.test(html), false, "no inline style block");
  assert.equal(/\sstyle=/i.test(html), false, "no style attribute");
  assert.equal(/\son[a-z]+=/i.test(html), false, "no inline handler");
  for (const m of html.matchAll(/\s(?:src|href)="([^"]+)"/g)) {
    const url = m[1];
    assert.ok(url.startsWith("/") || url.startsWith("#"), `absolute same-origin path: ${url}`);
    if (url.startsWith("/sentilab/live/") && !url.endsWith("/")) assert.ok(existsSync(join(PUBLIC, url)), `exists: ${url}`);
  }
  for (const p of files.filter((f) => f.endsWith(".mjs"))) {
    for (const m of text(p).matchAll(/["'`](\/api\/[^"'`?$]*)/g)) assert.match(m[1], /^\/api\/(open\/v1\/door\/(results|events|board)|view\/runs)$/, `read-only feed paths only: ${m[1]}`);
    assert.equal(/method:\s*["'](POST|PUT|PATCH|DELETE)/i.test(text(p)), false, `${relative(PUBLIC, p)} writes nothing`);
  }
});
