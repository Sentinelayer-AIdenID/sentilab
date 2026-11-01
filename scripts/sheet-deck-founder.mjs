#!/usr/bin/env node
// One image of the founder pitch for review: the ten main slides, each beside its spoken words, with the clock and the
// placeholders still to fill. It is drawn from the exporter's screenshots, so it shows exactly the slides the PDF prints.
//
//   PLAYWRIGHT_DIR=<dir> node scripts/sheet-deck-founder.mjs --shots <dir from export-deck-pdf.mjs --deck founder --shots>
//
// Writes docs/sentilab/deck/founder-v4/sheet-main.png for the 3min build, sheet-main-<slot>.png for another slot.
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { FOUNDER_DECK_DIR, FOUNDER_DIR, sheetFillLine } from "./build-deck-founder.mjs";

const args = process.argv.slice(2);
const at = args.indexOf("--shots");
if (at < 0) { console.error("usage: sheet-deck-founder.mjs --shots <dir>"); process.exit(2); }
const shots = resolve(args[at + 1]);
const data = JSON.parse(readFileSync(join(FOUNDER_DECK_DIR, "deck-data.json"), "utf8"));
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const main = data.slides.map((s, k) => ({ s, k })).filter(({ s }) => s.main);
const cells = main.map(({ s, k }) => {
  const png = readFileSync(join(shots, `${String(k + 1).padStart(2, "0")}-${s.id}-1920x1080.png`)).toString("base64");
  return `<div class="cell"><img src="data:image/png;base64,${png}" width="800" height="450"><div class="say"><b>${esc(s.label)} · ${esc(s.kicker)}</b>`
    + `<p>${esc(s.notes.text)}</p><small>${s.notes.words} words · ${s.notes.seconds} s${s.notes.cue ? ` · cue: ${esc(s.notes.cue)}` : ""}</small></div></div>`;
}).join("");
const u = data.budget;
const head = `<h1>SentiLab founder pitch (v4${data.deck.slot === "3min" ? "" : "-short"}), ${esc(data.deck.talk)} · ${esc(data.deck.cutoff)}${data.deck.draft ? " · draft" : ""}</h1>`
  + `<p class="clock">${u.talkWords} words = ${u.talkSeconds} s at ${u.wordsPerMinute} wpm + ${u.transitionSeconds} s transitions = ${u.totalSeconds} s of ${u.talkCapSeconds} s · at ${u.slowWordsPerMinute} wpm ${u.slowTotalSeconds} s</p>`
  + (sheetFillLine(data) ? `<p class="fill">${esc(sheetFillLine(data))}</p>` : "");
const page = `<!doctype html><meta charset="utf-8"><style>
body { margin: 0; padding: 36px 40px; width: 3000px; background: #0b1216; color: #eef3f2; font: 20px/1.4 "Segoe UI", system-ui, sans-serif; }
h1 { margin: 0; font: 650 40px "Segoe UI", system-ui, sans-serif; }
.clock { margin: 8px 0 0; color: #ecc993; font-weight: 600; }
.fill { margin: 6px 0 0; color: #ecc993; }
.grid { margin-top: 26px; display: grid; grid-template-columns: 1fr 1fr; gap: 22px 30px; }
.cell { display: grid; grid-template-columns: 800px 1fr; gap: 20px; padding: 14px; border: 2px solid #2a3a42; border-radius: 12px; background: #121c23; }
.cell img { display: block; border-radius: 6px; }
.say b { display: block; font: 600 18px Consolas, monospace; color: #93afb8; text-transform: uppercase; letter-spacing: .06em; }
.say p { margin: 8px 0; font-size: 21px; color: #d6e0e0; }
.say small { color: #a3b4ba; font-size: 16px; }
</style><body>${head}<div class="grid">${cells}</div></body>`;

const dir = process.env.PLAYWRIGHT_DIR;
const { chromium } = dir ? createRequire(pathToFileURL(join(resolve(dir), "noop.js")))("playwright") : await import("playwright");
const browser = await chromium.launch();
try {
  const ctx = await browser.newContext({ viewport: { width: 3100, height: 1200 }, deviceScaleFactor: 2 });
  const p = await ctx.newPage();
  await p.setContent(page, { waitUntil: "load" });
  const out = join(FOUNDER_DIR, data.deck.slot === "3min" ? "sheet-main.png" : `sheet-main-${data.deck.slot}.png`);
  await p.screenshot({ path: out, fullPage: true });
  console.log(`sheet ${out}`);
} finally {
  await browser.close();
}
