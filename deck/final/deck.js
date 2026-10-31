/* SentiLab three-minute deck. Five main slides, then backup, authored once at 1920x1080 and scaled to the window.
 *
 * Every word on a slide comes from deck-data.json, which scripts/build-deck-final.mjs generates from the reviewed source
 * docs/sentilab/deck/final-3min/FINAL.json. renderSlides() is a pure string function, so the node test renders exactly
 * what the browser renders. The one illustration (the chiplet package) is an inline SVG template in index.html.
 *
 * Keys: Right/Down/Space/PageDown next · Left/Up/PageUp previous · Home/End · F fullscreen · N speaker notes · R reset clock.
 * ?print=1 lays every slide out as a 1920x1080 page (export-deck-pdf.mjs --deck final prints it to PDF).
 */
(function (host, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else { host.FinalDeck = api; if (host.document) api.boot(host); }
})(typeof window !== "undefined" ? window : globalThis, function () {
  "use strict";
  const W = 1920, H = 1080;
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  // `code` spans in the reviewed wording become <code>; everything else is escaped text.
  const rich = (s) => esc(s).replace(/`([^`]+)`/g, "<code>$1</code>");
  const list = (items, cls = "") => `<ul class="${cls}">${items.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>`;

  // ── slide bodies ──────────────────────────────────────────────────────────────────────────────────────────────────
  const BODY = {
    problem(c) {
      return `<div class="s1"><div class="s1-left"><h1 class="hero">${esc(c.hero)}</h1><p class="q">${esc(c.question)}</p></div>`
        + `<figure class="s1-art"><div class="art" data-art="iso"></div><figcaption>${esc(c.caption)}</figcaption></figure></div>`
        + `<div class="answer"><span class="eyebrow">${esc(c.answerEyebrow)}</span><p>${esc(c.answer)}</p><p class="dom">${esc(c.domain)}</p></div>`;
    },
    how(c) {
      const steps = c.steps.map((s, i) => `<li class="step"><span class="n">${i + 1}</span><b>${esc(s.title)}</b><p>${esc(s.text)}</p>`
        + `<p class="today"><span>31 Oct</span>${esc(s.today)}</p></li>`).join("");
      return `<h1>${esc(c.title)}</h1><ol class="steps">${steps}</ol><p class="foot">${esc(c.footnote)}</p>`;
    },
    timeline(c) {
      const lines = c.lines.map((l) => `<li><time>${esc(l.at)}</time><span>${esc(l.text)}</span></li>`).join("");
      return `<h1>${esc(c.title)}</h1><p class="lede"><time>${esc(c.lede.at)}</time><span>${esc(c.lede.text)}</span></p>`
        + `<div class="s3"><ol class="tl">${lines}</ol><aside class="callout"><span class="big">${esc(c.callout.big)}</span>`
        + `<p class="cl">${esc(c.callout.label)}</p><p class="sub">${esc(c.callout.sub)}</p></aside></div>`;
    },
    gate(c) {
      const rows = c.rows.map((r) => `<tr><th>${esc(r.label)}<span>${esc(r.source)}</span></th><td>${esc(r.publishedC)} C</td>`
        + `<td>within ${esc(c.toleranceK)} K</td><td class="res tone-${esc(r.tone)}">${esc(r.result)}</td></tr>`).join("");
      return `<h1>${esc(c.title)}</h1><div class="common">${rich(c.common)}</div>`
        + `<table class="gt"><thead><tr><th>Reference</th><th>Published</th><th>Must land</th><th>Result</th></tr></thead><tbody>${rows}</tbody></table>`
        + `<div class="variant v-${esc(c.variant)}"><span class="pill">${esc(c.label)}</span><p>${esc(c.text)}</p></div>`
        + `<p class="bottom">${esc(c.bottom)}</p>`;
    },
    reuse(c) {
      const r = c.receipt;
      const row = (k, v) => `<div class="rr"><span>${esc(k)}</span><p>${esc(v)}</p></div>`;
      return `<h1>${esc(c.title)}</h1><article class="receipt"><div class="rh"><b>${esc(r.team)}</b><span class="where">${esc(r.where)} · commit <code>${esc(r.commit)}</code></span></div>`
        + row("What", r.what) + row("Result", r.result) + row("Rerun", r.rerun) + row("Limit", r.limit) + `</article>`
        + `<p class="next">${esc(c.next)}</p>`
        + `<div class="strip"><span class="sh">Where it stands</span>${c.status.map((s) => `<div class="sv"><span>${esc(s.label)}</span><b>${esc(s.value)}</b></div>`).join("")}</div>`;
    },
    chronology(c) {
      const rows = c.rows.map((r) => `<tr><td class="t">${esc(r.at)}</td><td>${esc(r.text)}</td></tr>`).join("");
      return `<h1>${esc(c.title)}</h1><table class="chron"><tbody>${rows}</tbody></table>`;
    },
    metrics(c) {
      const m = c.model;
      const table = `<table class="mt"><thead><tr>${m.head.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>`
        + m.rows.map((r) => `<tr>${r.map((v) => `<td>${esc(v)}</td>`).join("")}</tr>`).join("") + `</tbody></table>`;
      return `<h1>${esc(c.title)}</h1><div class="b2">`
        + `<div class="card"><span class="eyebrow">${esc(c.saved.eyebrow)}</span>${list(c.saved.lines, "pts")}<p class="lim">${esc(c.saved.limit)}</p>`
        + `<span class="eyebrow sep">${esc(c.continuum.eyebrow)}</span>${list(c.continuum.lines, "pts")}<p class="lim">${esc(c.continuum.limit)}</p></div>`
        + `<div class="card"><span class="eyebrow">${esc(m.eyebrow)}</span>${table}<p>${esc(m.spread)}</p><p class="lim">${esc(m.review)}</p></div>`
        + `</div><p class="hist">${esc(c.history)}</p>`;
    },
    "gate-detail"(c) {
      const w = c.wordings.map((x) => `<div class="wd${x.chosen ? " chosen" : ""}"><span class="pill">${esc(x.label)}</span><p>${esc(x.text)}</p>${x.chosen ? `<span class="tag">this export</span>` : ""}</div>`).join("");
      return `<h1>${esc(c.title)}</h1><div class="b3"><div class="card">${list(c.rules, "pts")}<p class="srcl">${esc(c.source)}</p>`
        + `<p class="gst">Gate-zero code: PR #${esc(c.status.pr)}, ${esc(c.status.text)} (${esc(c.status.checked)}).</p></div>`
        + `<div class="card"><span class="eyebrow">${esc(c.wordingTitle)}</span>${w}</div></div>`;
    },
    drill(c) {
      const flow = c.flow.map((f) => `<li><b>${esc(f.title)}</b><span>${esc(f.text)}</span></li>`).join("");
      return `<h1>${esc(c.title)}</h1><ol class="flow">${flow}</ol><div class="shots">`
        + `<figure><div class="frame"><img src="../img/lab-drill.png" alt="Lab view evidence panel after the drill"></div><figcaption>${esc(c.labCaption)}</figcaption></figure>`
        + `<figure><div class="frame"><img src="../img/package-drill.png" alt="Package view of the accepted board after the drill"></div><figcaption>${esc(c.packageCaption)}</figcaption></figure>`
        + `</div><p class="fx">${esc(c.fixture)}</p>`;
    },
    status(c) {
      const d = c.deliverables.map((x) => `<li><b>${esc(x.id)}</b><span>${esc(x.text)}</span><i>not fully accepted</i></li>`).join("");
      const cards = c.cards.map((x) => `<div class="sc"><b>${esc(x.title)}</b><p>${esc(x.text)}</p><p class="when">${esc(x.origin)} · ${esc(x.asOf)}</p></div>`).join("");
      return `<h1>${esc(c.title)}</h1><div class="b5"><ol class="dl">${d}</ol><div class="cards">${cards}</div></div>`;
    },
    prs(c) {
      const rows = c.rows.map((r) => `<tr><td class="n">${esc(r.number)}</td><td>${esc(r.what)}</td><td class="pst pst-${esc(r.state)}">${esc(r.text)}</td>${c.checked ? "" : `<td class="ck">${esc(r.checked)}</td>`}</tr>`).join("");
      return `<h1>${esc(c.title)}</h1><p class="repo">Repository: ${esc(c.repo)}${c.checked ? ` · ${esc(c.checked)}` : ""}</p><table class="prt"><tbody>${rows}</tbody></table>`;
    },
    receipt(c) {
      const rows = c.facts.map((f) => `<tr><th>${esc(f.label)}</th><td>${esc(f.text)}</td></tr>`).join("");
      return `<h1>${esc(c.title)}</h1><table class="rct"><tbody>${rows}</tbody></table><p class="notyet">${esc(c.notYet)}</p><p class="noev">${esc(c.notEvidence)}</p>`;
    },
  };
  // Footer notes that belong to a slide (the cutoff and the page label are on every slide).
  const FOOT = {
    problem: () => "This slide states the problem and the design. It reports no measurement.",
    timeline: (c) => `Times UTC, 31 Oct 2026, from the room record. ${c.note}`,
    gate: () => "The test and the wording for all three outcomes were written before any result.",
    reuse: () => "The other team's package is public. Our own help-room leaderboard is not used as evidence.",
    chronology: (c) => c.note,
    metrics: () => "No value here is a calibrated temperature.",
  };

  function renderSlide(s, data) {
    const body = BODY[s.id];
    if (!body) throw new Error(`no layout for slide ${s.id}`);
    const note = FOOT[s.id]?.(s.content) ?? "";
    const preview = data.deck.preview ? `<span class="preview">PREVIEW · not a result</span>` : "";
    return `<section class="slide ${s.main ? "main" : "backup"}" id="s-${esc(s.id)}" data-label="${esc(s.label)}" data-notes="${esc(s.id)}">`
      + `<header class="bar"><span class="brand"><i class="mark"></i><b>${esc(data.deck.title)}</b><span>${esc(data.deck.event)}</span></span>${preview}<span class="kicker">${esc(s.kicker)}</span></header>`
      + `<div class="body">${body(s.content, data)}</div>`
      + `<footer class="src"><span class="cut">Facts as of ${esc(data.deck.cutoff)}</span><span class="fn">${esc(note)}</span><span class="pg">${esc(s.label)}</span></footer>`
      + `</section>`;
  }
  function renderSlides(data) {
    if (data?.schema !== "sentilab-deck-final-data/1") throw new Error(`unsupported deck data ${JSON.stringify(data?.schema)}`);
    return data.slides.map((s) => renderSlide(s, data)).join("\n");
  }

  // ── browser ───────────────────────────────────────────────────────────────────────────────────────────────────────
  function boot(win) {
    const doc = win.document;
    const start = () => run(win).catch((e) => {
      doc.body.insertAdjacentHTML("afterbegin", `<p class="fatal">Deck data could not be loaded: ${esc(e.message)}</p>`);
    });
    if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", start); else start();
  }
  async function loadData(win) {
    if (win.location.protocol !== "file:") {
      try {
        const r = await win.fetch("deck-data.json", { cache: "no-store" });
        if (r.ok) return { data: await r.json(), from: "deck-data.json" };
      } catch { /* offline: fall back to the script copy */ }
    }
    if (win.DECK_DATA) return { data: win.DECK_DATA, from: "deck-data.js" };
    throw new Error("neither deck-data.json nor deck-data.js is available");
  }
  async function run(win) {
    const doc = win.document;
    const params = new win.URLSearchParams(win.location.search);
    const { data, from } = await loadData(win);
    const deck = doc.getElementById("deck");
    deck.innerHTML = renderSlides(data);
    const art = doc.getElementById("art-iso");
    for (const el of deck.querySelectorAll('[data-art="iso"]')) el.appendChild(art.content.cloneNode(true));
    const slides = [...deck.querySelectorAll(".slide")];
    const byId = new Map(data.slides.map((s) => [s.id, s]));
    const notesEl = doc.getElementById("notes");
    if (params.has("print")) doc.body.classList.add("print");
    const fit = () => deck.style.setProperty("--s", String(Math.min(win.innerWidth / W, win.innerHeight / H)));
    fit();
    win.addEventListener("resize", fit);

    let i = 0, t0 = Date.now();
    function renderNotes() {
      const s = byId.get(slides[i].dataset.notes);
      const el = Math.floor((Date.now() - t0) / 1000);
      notesEl.querySelector(".n-pos").textContent = `${s.label} · ${s.kicker}`;
      notesEl.querySelector(".n-target").textContent = s.main
        ? `${s.notes.words} words · ${s.notes.seconds} s · main total ${data.budget.mainSeconds} s of ${data.budget.speechBudgetSeconds} s`
        : "backup · not in the three minutes";
      notesEl.querySelector(".n-clock").textContent = `${Math.floor(el / 60)}:${String(el % 60).padStart(2, "0")} elapsed`;
      notesEl.querySelector(".n-text").textContent = s.notes.text;
    }
    function show(k, push = true) {
      i = Math.max(0, Math.min(slides.length - 1, k));
      slides.forEach((s, j) => s.classList.toggle("on", j === i));
      if (push) win.history.replaceState(null, "", `#${i + 1}`);
      renderNotes();
    }
    const fromHash = () => { const n = parseInt(win.location.hash.slice(1), 10); return Number.isFinite(n) ? n - 1 : 0; };
    win.addEventListener("hashchange", () => show(fromHash(), false));
    win.addEventListener("keydown", (e) => {
      if (e.altKey || e.ctrlKey || e.metaKey) return;
      const k = e.key;
      if (["ArrowRight", "ArrowDown", " ", "PageDown", "Enter"].includes(k)) { e.preventDefault(); show(i + 1); }
      else if (["ArrowLeft", "ArrowUp", "PageUp", "Backspace"].includes(k)) { e.preventDefault(); show(i - 1); }
      else if (k === "Home") show(0);
      else if (k === "End") show(slides.length - 1);
      else if (k === "f" || k === "F") {
        if (doc.fullscreenElement) doc.exitFullscreen?.(); else doc.documentElement.requestFullscreen?.().catch(() => {});
      } else if (k === "n" || k === "N") { notesEl.hidden = !notesEl.hidden; renderNotes(); }
      else if (k === "r" || k === "R") { t0 = Date.now(); renderNotes(); }
    });
    deck.addEventListener("click", (e) => {
      if (e.target.closest("a")) return;
      const r = deck.getBoundingClientRect();
      show(e.clientX < r.left + r.width / 3 ? i - 1 : i + 1);
    });
    win.setInterval(() => { if (!notesEl.hidden) renderNotes(); }, 1000);
    if (params.has("notes")) notesEl.hidden = false;
    show(fromHash(), false);
    win.__deck = { ready: true, from, count: slides.length, go: (k) => show(k), ids: slides.map((s) => s.id), main: data.slides.map((s) => s.main), preview: data.deck.preview };
  }

  return { renderSlides, renderSlide, BODY, esc, boot };
});
