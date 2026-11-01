#!/usr/bin/env node
// Prints a SentiLab deck to PDF (one 1920x1080 page per slide) and, with --shots, screenshots and checks every slide.
//
//   PLAYWRIGHT_DIR=<dir containing node_modules/playwright> node scripts/export-deck-pdf.mjs [--deck daytime|supplement|final]
//     [--shots <dir>] [--no-pdf]
//
// --deck daytime (the default) is the daytime deck, deck/daytime/; --deck supplement is the dated supplement,
// deck/supplement/; --deck final is the five-minute talk deck, deck/final-5min/ (build-deck-final.mjs); --deck final3min
// is the preserved three-minute deck, deck/final/, which can be screenshot and checked but never re-exported. Run its
// build script first (build-deck-data.mjs, build-deck-supplement.mjs or build-deck-final.mjs). deck/ (DECK_ROOT) is
// served by a throwaway local server and the deck opens at /<deck>/, so it reads deck-data.json exactly as a browser
// would and loads the shared images, engine and stylesheet from their committed paths. Output, one page per slide and
// nothing else (the speaker notes are in deck-data.json and the N panel, never printed):
//   daytime     docs/sentilab/deck/SentiLab-deck-<packet date>-daytime-<HHMM>.pdf, named from the packet (pdfName)
//   supplement  docs/sentilab/deck/SentiLab-deck-supplement-<date>-<HHMM>-v<n>.pdf (suppPdfName)
//   final       docs/sentilab/deck/final-5min/SentiLab-5min-<cutoff date>-<HHMM>-<gate outcome>.pdf (finalPdfName); a
//               preview build (PASS or FAIL without values) is refused: it screenshots, it never prints
// The final deck also holds its main slides to a 28px type floor (the footer line keeps 22px) and every deck's text to a
// 4.5:1 contrast ratio against the background it sits on.
// The v1 deck, the daytime deck and their PDFs are frozen (FROZEN_V1, FROZEN_DAYTIME): this script never writes any of
// those paths, so the daytime PDF is not re-exported; --no-pdf still screenshots and checks the daytime deck.
// --shots <dir> also writes every slide at 1920x1080 and 1280x720 (plus one with the notes panel) and a report.json.
// Each slide is checked: nothing outside its block or the canvas, no clipped text, smallest font size, missing values,
// empty generated blocks. Exit 1 when a check fails, the deck shows its error banner, the browser logs an error or a
// request fails, or the PDF page count differs from the slide count.
import { createServer } from "node:http";
import { mkdirSync, readFileSync, writeFileSync, existsSync, statSync } from "node:fs";
import { createRequire } from "node:module";
import { extname, join, normalize, relative, resolve, sep } from "node:path";
import { pathToFileURL } from "node:url";
import { DECK_DIR, DECK_ROOT, FROZEN_V1, PDF_DIR, REPO_ROOT, pdfName } from "./build-deck-data.mjs";
import { FROZEN_DAYTIME, SUPP_DECK_DIR, suppPdfName } from "./build-deck-supplement.mjs";
import { FINAL3_DECK_DIR, FINAL_DECK_DIR, FROZEN_FINAL_3MIN, finalPdfName } from "./build-deck-final.mjs";

const args = process.argv.slice(2);
const deckAt = args.indexOf("--deck");
const DECKS = {
  daytime: { dir: DECK_DIR, pdf: (data) => pdfName(data.source.packetId) },
  supplement: { dir: SUPP_DECK_DIR, pdf: () => suppPdfName() },
  final: { dir: FINAL_DECK_DIR, pdf: (data) => finalPdfName(data), mainMinFont: 28 },
  final3min: { dir: FINAL3_DECK_DIR, pdf: () => { throw new Error("the three-minute deck is preserved as exported at 00:12 UTC; it is never re-exported"); }, mainMinFont: 28 },
};
const DECK_NAME = deckAt >= 0 ? args[deckAt + 1] : "daytime";
if (!Object.hasOwn(DECKS, DECK_NAME)) { console.error(`unknown deck ${JSON.stringify(DECK_NAME)}: use --deck daytime, supplement, final or final3min`); process.exit(2); }
const DECK = DECKS[DECK_NAME];
const FROZEN = { ...FROZEN_V1, ...FROZEN_DAYTIME };
const OUT_DIR = PDF_DIR;
const PAGE = `${relative(DECK_ROOT, DECK.dir).split(sep).join("/")}/`;
const MIN_FONT = 22; // canvas px at 1920x1080
const MAIN_MIN_FONT = DECK.mainMinFont ?? MIN_FONT; // main (non-backup) slides, outside the footer line
const MIN_CONTRAST = 4.5; // WCAG AA for body text

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
  const out = { id: slide.id, main: !slide.classList.contains("backup"), issues: [], minFont: Infinity, minFontAt: "", bodyMinFont: Infinity, bodyMinFontAt: "", minContrast: Infinity, minContrastAt: "", pending: [] };
  // Contrast: the text colour against the first opaque background behind it, blending translucent layers on the way.
  const rgba = (c) => {
    const m = /rgba?\(([^)]+)\)/.exec(c);
    if (!m) return null;
    const p = m[1].split(/[\s,/]+/).filter(Boolean).map((x) => parseFloat(x));
    return p.length >= 3 && p.slice(0, 3).every(Number.isFinite) ? [p[0], p[1], p[2], Number.isFinite(p[3]) ? p[3] : 1] : null;
  };
  const over = (top, bot) => { const a = top[3]; return [top[0] * a + bot[0] * (1 - a), top[1] * a + bot[1] * (1 - a), top[2] * a + bot[2] * (1 - a), 1]; };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const backdrop = (el) => {
    const layers = [];
    for (let e = el; e; e = e.parentElement) {
      const cs = getComputedStyle(e);
      // A gradient paints over its element's colour: take its lightest stop, the worst case for light text.
      if (cs.backgroundImage && cs.backgroundImage !== "none") {
        const stops = [...cs.backgroundImage.matchAll(/rgba?\([^)]+\)/g)].map((m) => rgba(m[0])).filter(Boolean);
        if (stops.length) { layers.push(stops.reduce((x, y) => (lum(y) > lum(x) ? y : x))); if (layers.at(-1)[3] >= 1) break; }
      }
      const bg = rgba(cs.backgroundColor);
      if (bg && bg[3] > 0) { layers.push(bg); if (bg[3] >= 1) break; }
    }
    return layers.reverse().reduce((acc, l) => over(l, acc), [16, 25, 30, 1]);
  };
  // An unreadable colour is reported, never scored as perfect contrast, so this check can fail.
  const contrast = (el) => {
    const fg = rgba(getComputedStyle(el).color);
    if (!fg) { out.issues.push(`unreadable text colour ${getComputedStyle(el).color}: ${name(el)}`); return 0; }
    const bg = backdrop(el);
    const a = lum(over(fg, bg)), b = lum(bg);
    return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
  };
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
        if (!el.closest(".src") && fs < out.bodyMinFont) { out.bodyMinFont = fs; out.bodyMinFontAt = name(el); }
        const cr = contrast(el);
        if (cr < out.minContrast) { out.minContrast = cr; out.minContrastAt = name(el); }
      }
      if (el.classList.contains("pending")) out.pending.push(el.dataset.f || name(el)); // a missing value: a failure
    }
  });
  for (const el of slide.querySelectorAll("[data-gen]")) if (!el.textContent.trim()) out.pending.push(`empty generated block ${el.dataset.gen}`);
  for (const t of slide.querySelectorAll("svg text")) {
    const fs = parseFloat(getComputedStyle(t).fontSize) * (t.closest("svg").getBoundingClientRect().width / scale) / t.closest("svg").viewBox.baseVal.width;
    if (fs < out.minFont) { out.minFont = fs; out.minFontAt = `svg text "${t.textContent}"`; }
  }
  // A figure is a picture with text in it: it must load, and its smallest text, scaled to the width it is drawn at, is
  // held to the same floor as the slide's own text.
  out.figures = [];
  for (const img of slide.querySelectorAll("img[data-fig]")) {
    if (!img.complete || !img.naturalWidth) { out.issues.push(`figure ${img.dataset.fig} did not load`); continue; }
    const shown = img.getBoundingClientRect().width / scale;
    const fs = (Number(img.dataset.minFont) * shown) / Number(img.dataset.naturalWidth);
    out.figures.push({ id: img.dataset.fig, width: Math.round(shown), minFont: Math.round(fs * 10) / 10 });
    if (fs < out.minFont) { out.minFont = fs; out.minFontAt = `figure ${img.dataset.fig}`; }
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
  await page.waitForFunction(() => window.__deck?.ready === true || document.querySelector(".fatal"));
  const fatal = await page.evaluate(() => document.querySelector(".fatal")?.textContent ?? null);
  if (fatal) throw new Error(`${w}x${h}: the deck shows its error banner: ${fatal}`);
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
          if (c.main && c.bodyMinFont < MAIN_MIN_FONT - 0.01) fail(`${c.id}: main-slide text ${c.bodyMinFont.toFixed(1)}px < ${MAIN_MIN_FONT}px at ${c.bodyMinFontAt}`);
          if (DECK_NAME.startsWith("final") && c.minContrast < MIN_CONTRAST) fail(`${c.id}: contrast ${c.minContrast.toFixed(2)} < ${MIN_CONTRAST} at ${c.minContrastAt}`);
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
    const path = join(OUT_DIR, DECK.pdf(JSON.parse(readFileSync(join(DECK.dir, "deck-data.json"), "utf8")))); // a final preview throws here
    const rel = relative(REPO_ROOT, path).split(sep).join("/");
    if (Object.hasOwn(FROZEN, rel)) throw new Error(`refusing to overwrite the frozen export ${rel}`);
    if (Object.hasOwn(FROZEN_FINAL_3MIN, rel)) throw new Error(`refusing to overwrite the preserved three-minute export ${rel}`);
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
for (const s of report.slides) console.log(`${s.id.padEnd(14)} min font ${s.minFont.toFixed(1)}px${s.main && Number.isFinite(s.bodyMinFont) ? ` · body ${s.bodyMinFont.toFixed(1)}px` : ""} · contrast ${s.minContrast.toFixed(2)}${s.pending.length ? ` · pending: ${s.pending.join(", ")}` : ""}${s.issues.length ? ` · ${s.issues.length} issue(s)` : ""}`);
if (report.pdf) console.log(`PDF ${report.pdf.path} · ${report.pdf.pages} pages`);
if (report.failures.length) { console.error(`FAIL\n- ${report.failures.join("\n- ")}`); process.exit(1); }
console.log("OK");
