#!/usr/bin/env node
// Prints the SentiLab daytime deck to PDF (one 1920x1080 page per slide) and, with --shots, screenshots and checks every
// slide.
//
//   PLAYWRIGHT_DIR=<dir containing node_modules/playwright> node scripts/export-deck-pdf.mjs [--shots <dir>] [--no-pdf]
//
// Run scripts/build-deck-data.mjs first. deck/ (DECK_ROOT) is served by a throwaway local server and the deck opens at
// /daytime/, so it reads deck-data.json exactly as a browser would and loads the shared images from deck/img/. Output:
// docs/sentilab/deck/SentiLab-deck-<packet date>-daytime-<HHMM>.pdf, named from the packet the data came from (pdfName),
// one page per slide and nothing else: the speaker notes are not printed (they are in deck-data.json and the N panel).
// The v1 deck and its date-only PDF are frozen (FROZEN_V1): this script never writes any of those paths.
// --shots <dir> also writes every slide at 1920x1080 and 1280x720 (plus one with the notes panel) and a report.json.
// Each slide is checked: nothing outside its block or the canvas, no clipped text, smallest font size, missing values.
// Exit 1 when a check fails, the browser logs an error or a request fails, or the PDF page count differs from the slide
// count.
import { createServer } from "node:http";
import { mkdirSync, readFileSync, writeFileSync, existsSync, statSync } from "node:fs";
import { createRequire } from "node:module";
import { extname, join, normalize, relative, resolve, sep } from "node:path";
import { pathToFileURL } from "node:url";
import { DECK_DIR, DECK_ROOT, FROZEN_V1, PDF_DIR, REPO_ROOT, pdfName } from "./build-deck-data.mjs";

const OUT_DIR = PDF_DIR;
const PAGE = `${relative(DECK_ROOT, DECK_DIR).split(sep).join("/")}/`;
const MIN_FONT = 22; // canvas px at 1920x1080

const args = process.argv.slice(2);
const shotsAt = args.indexOf("--shots");
const SHOTS = shotsAt >= 0 ? resolve(args[shotsAt + 1]) : null;
const PDF = !args.includes("--no-pdf");

async function loadPlaywright() {
  const dir = process.env.PLAYWRIGHT_DIR;
  if (dir) return createRequire(pathToFileURL(join(resolve(dir), "noop.js")))("playwright");
  return import("playwright");
}

const TYPES = { ".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript", ".mjs": "text/javascript",
  ".json": "application/json", ".png": "image/png", ".svg": "image/svg+xml" };
function serve() {
  const server = createServer((req, res) => {
    const url = new URL(req.url, "http://localhost");
    let p = normalize(join(DECK_ROOT, decodeURIComponent(url.pathname)));
    if (!p.startsWith(DECK_ROOT + sep) && p !== DECK_ROOT) { res.writeHead(403).end(); return; }
    if (existsSync(p) && statSync(p).isDirectory()) p = join(p, "index.html");
    if (req.method !== "GET" || !existsSync(p)) { res.writeHead(404).end(); return; }
    res.writeHead(200, { "content-type": TYPES[extname(p)] ?? "application/octet-stream", "cache-control": "no-store" }).end(readFileSync(p));
  });
  return new Promise((ok) => server.listen(0, "127.0.0.1", () => ok(server)));
}

// Runs in the page: geometry and type checks for slide k, on the 1920x1080 canvas.
function checkSlide(k) {
  const slide = document.querySelectorAll(".slide")[k];
  const sr = slide.getBoundingClientRect();
  const scale = sr.width / 1920;
  const out = { id: slide.id, issues: [], minFont: Infinity, minFontAt: "", pending: [] };
  const name = (el) => `${el.tagName.toLowerCase()}${el.id ? `#${el.id}` : ""}${el.className && typeof el.className === "string" ? `.${el.className.trim().split(/\s+/).join(".")}` : ""} "${(el.textContent || "").trim().slice(0, 40)}"`;
  const within = (r, c, tol = 1.5) => r.left >= c.left - tol && r.right <= c.right + tol && r.top >= c.top - tol && r.bottom <= c.bottom + tol;
  const blocks = [...slide.children];
  blocks.forEach((b, i) => {
    const br = b.getBoundingClientRect();
    if (!within(br, sr)) out.issues.push(`block outside the canvas: ${name(b)}`);
    const next = blocks[i + 1]?.getBoundingClientRect();
    if (next && br.bottom > next.top + 1.5) out.issues.push(`block overlaps the next one by ${((br.bottom - next.top) / scale).toFixed(0)}px: ${name(b)}`);
    for (const el of b.querySelectorAll("*")) {
      if (el.closest(".frame") && el.tagName === "IMG") continue; // crops overflow their frame by design
      if (el.closest("svg")) continue;
      const cs = getComputedStyle(el);
      if (cs.display === "none" || cs.visibility === "hidden") continue;
      const r = el.getBoundingClientRect();
      if (r.width && r.height && !within(r, br)) out.issues.push(`outside its block (${((r.bottom - br.bottom) / scale).toFixed(0)}px below): ${name(el)}`);
      const parent = el.parentElement;
      if (parent && parent !== b && r.width && r.height && !cs.display.startsWith("inline") && !getComputedStyle(parent).display.startsWith("inline")) {
        const pr = parent.getBoundingClientRect();
        if (!within(r, pr, 2.5)) out.issues.push(`spills out of its container ${name(parent)}: ${name(el)}`);
      }
      if (el.classList.contains("frame")) continue; // a crop window: its image overflows on purpose
      if (el.scrollWidth > el.clientWidth + 2 && cs.overflowX !== "visible") out.issues.push(`clipped horizontally: ${name(el)}`);
      if (el.scrollHeight > el.clientHeight + 2 && cs.overflowY !== "visible") out.issues.push(`clipped vertically: ${name(el)}`);
      const text = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
      if (text) {
        const fs = parseFloat(cs.fontSize);
        if (fs < out.minFont) { out.minFont = fs; out.minFontAt = name(el); }
      }
      if (el.classList.contains("pending")) out.pending.push(el.dataset.f || name(el)); // a missing value: a failure
    }
  });
  for (const t of slide.querySelectorAll("svg text")) {
    const fs = parseFloat(getComputedStyle(t).fontSize) * (t.closest("svg").getBoundingClientRect().width / scale) / t.closest("svg").viewBox.baseVal.width;
    if (fs < out.minFont) { out.minFont = fs; out.minFontAt = `svg text "${t.textContent}"`; }
  }
  return out;
}

const { chromium } = await loadPlaywright();
const server = await serve();
const base = `http://127.0.0.1:${server.address().port}/`;
const browser = await chromium.launch();
const report = { base, shots: [], slides: [], console: [], pdf: null, failures: [] };
const fail = (m) => report.failures.push(m);

async function open(w, h, query = "") {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  page.on("console", (m) => { if (["error", "warning"].includes(m.type())) report.console.push(`${w}x${h}: ${m.text()}`); });
  page.on("pageerror", (e) => report.console.push(`${w}x${h}: pageerror ${e.message}`));
  page.on("requestfailed", (r) => report.console.push(`${w}x${h}: request failed ${r.url()} ${r.failure()?.errorText ?? ""}`));
  page.on("response", (r) => { if (r.status() >= 400) report.console.push(`${w}x${h}: HTTP ${r.status()} ${r.url()}`); });
  await page.goto(base + PAGE + query, { waitUntil: "networkidle" });
  await page.waitForFunction(() => window.__deck?.ready === true);
  return { ctx, page };
}

try {
  if (SHOTS) {
    mkdirSync(SHOTS, { recursive: true });
    for (const [w, h] of [[1920, 1080], [1280, 720]]) {
      const { ctx, page } = await open(w, h);
      const info = await page.evaluate(() => ({ count: window.__deck.count, ids: window.__deck.ids, from: window.__deck.from }));
      if (info.from !== "deck-data.json") fail(`${w}x${h}: deck read ${info.from}, not deck-data.json`);
      for (let k = 0; k < info.count; k++) {
        await page.evaluate((i) => window.__deck.go(i), k);
        await page.waitForTimeout(120);
        const file = join(SHOTS, `${String(k + 1).padStart(2, "0")}-${info.ids[k].replace(/^s-/, "")}-${w}x${h}.png`);
        await page.screenshot({ path: file });
        report.shots.push(file);
        if (w === 1920) {
          const c = await page.evaluate(checkSlide, k);
          report.slides.push(c);
          if (c.issues.length) fail(`${c.id}: ${c.issues.join(" | ")}`);
          if (c.pending.length) fail(`${c.id}: missing values ${c.pending.join(", ")}`);
          if (c.minFont < MIN_FONT - 0.01) fail(`${c.id}: smallest text ${c.minFont.toFixed(1)}px < ${MIN_FONT}px at ${c.minFontAt}`);
        }
      }
      await ctx.close();
    }
    const { ctx, page } = await open(1920, 1080, "?notes=1#4");
    await page.waitForTimeout(150);
    const file = join(SHOTS, "notes-panel-04-1920x1080.png");
    await page.screenshot({ path: file });
    report.shots.push(file);
    await ctx.close();
  }
  if (PDF) {
    mkdirSync(OUT_DIR, { recursive: true });
    const { ctx, page } = await open(1920, 1080, "?print=1");
    const count = await page.evaluate(() => window.__deck.count);
    const { packetId } = JSON.parse(readFileSync(join(DECK_DIR, "deck-data.json"), "utf8")).source;
    const path = join(OUT_DIR, pdfName(packetId));
    const rel = relative(REPO_ROOT, path).split(sep).join("/");
    if (Object.hasOwn(FROZEN_V1, rel)) throw new Error(`refusing to overwrite the frozen v1 export ${rel}`);
    await page.pdf({ path, width: "1920px", height: "1080px", printBackground: true, preferCSSPageSize: true });
    const pages = (readFileSync(path, "latin1").match(/\/Type\s*\/Page(?![s\w])/g) ?? []).length;
    report.pdf = { path, pages, slides: count };
    if (pages !== count) fail(`PDF has ${pages} pages for ${count} slides`);
    await ctx.close();
  }
} finally {
  await browser.close();
  server.close();
}
if (report.console.length) fail(`browser console or requests: ${report.console.join(" | ")}`);
if (SHOTS) writeFileSync(join(SHOTS, "report.json"), JSON.stringify(report, null, 2) + "\n");
for (const s of report.slides) console.log(`${s.id.padEnd(14)} min font ${s.minFont.toFixed(1)}px${s.pending.length ? ` · pending: ${s.pending.join(", ")}` : ""}${s.issues.length ? ` · ${s.issues.length} issue(s)` : ""}`);
if (report.pdf) console.log(`PDF ${report.pdf.path} · ${report.pdf.pages} pages`);
if (report.failures.length) { console.error(`FAIL\n- ${report.failures.join("\n- ")}`); process.exit(1); }
console.log("OK");
