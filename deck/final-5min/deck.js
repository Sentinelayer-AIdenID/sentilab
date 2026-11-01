/* SentiLab talk deck for the five-minute slot: nine main slides from the plain-language script, one picture each (the
 * last is the door to the live demo), then the earlier five-minute deck and the questions page as backup, authored once
 * at 1920x1080 and scaled to the window.
 *
 * Every word on a slide comes from deck-data.json, which scripts/build-deck-final.mjs generates from the reviewed source
 * docs/sentilab/deck/final-5min/FINAL.json. renderSlides() is a pure string function, so the node test renders exactly
 * what the browser renders. The figures are the SVGs the build writes to figures/, shown as images, so nothing in them
 * runs.
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
  // A figure at the scale the source sets; the exporter checks its smallest text against the type floor.
  const fig = (f, cls = "") => {
    const w = Math.round(f.width * f.scale), h = Math.round(f.height * f.scale);
    return `<figure class="fig ${cls}"><img src="${esc(f.src)}" alt="${esc(f.alt)}" width="${w}" height="${h}" data-fig="${esc(f.id)}"`
      + ` data-min-font="${esc(f.minFont)}" data-natural-width="${esc(f.width)}"></figure>`;
  };

  // A screenshot of our own view, drawn at its declared width; it carries no text the checks could read, so none is held to the type floor.
  const still = (st, w, cls = "") => `<figure class="fig still ${cls}"><img src="${esc(st.src)}" alt="${esc(st.alt)}" width="${w}" height="${Math.round((st.height * w) / st.width)}" data-still="${esc(st.id)}"></figure>`;
  // Its label ("simulated, not silicon") sits above it wherever the view's temperatures are shown.
  const stillLabel = (st) => (st.label ? `<span class="pill still-label">${esc(st.label)}</span>` : "");
  // A still as wide as its slide allows: no wider than `maxW`, and no taller than `maxH`.
  const fitStill = (st, maxW, maxH, cls) => still(st, Math.min(maxW, Math.round((maxH * st.width) / st.height)), cls);

  // ── slide bodies ──────────────────────────────────────────────────────────────────────────────────────────────────
  // The plain talk: one title and one picture per slide; "why" may carry its numbers; the door is LIVE or REPLAY.
  const LAYOUTS = {
    talk(c) {
      const pic = c.figure ? fig(c.figure) : c.still ? `${stillLabel(c.still)}${fitStill(c.still, 1320, c.still.label ? 680 : 700)}` : "";
      return `<h1 class="ftitle">${esc(c.title)}</h1>${pic}`;
    },
    why(c) {
      // With its numbers, the tiles take the height of their words; without them, the closer in large type, over the
      // figure when there is one; with neither, the title alone, centred.
      const tiles = c.numbers ? `<div class="ngrid why-numbers n${c.numbers.length}">${c.numbers.map((x) => `<div class="ntile"><b class="nval">${esc(x.value)}</b><p class="nlab">${esc(x.label)}</p></div>`).join("")}</div>` : "";
      const words = !c.numbers && c.statement ? `<div class="why-statement${c.figure ? " ws-with-figure" : ""}"><p class="ws-main">${esc(c.statement.text)}</p><p class="ws-sub">${esc(c.statement.sub)}</p></div>` : "";
      return `<h1 class="ftitle${c.numbers || words ? "" : " why-title"}">${esc(c.title)}</h1>${tiles}${words}${!c.numbers && c.figure ? fig(c.figure) : ""}`;
    },
    door(c) {
      if (c.still) return `<h1>${esc(c.title)}</h1>${stillLabel(c.still)}${fitStill(c.still, 1100, 600, "dstill")}<p class="dstat dstat-${esc(c.status)}">${esc(c.statusText)}</p>`;
      // LIVE: the address and the instruction are the call to action, large enough to read from the back of the room.
      const flow = c.diagram.map((d) => `<li><b>${esc(d.title)}</b><span>${esc(d.text)}</span></li>`).join("");
      return `<h1>${esc(c.title)}</h1><div class="dcta"><p class="dcta-url">${esc(c.url)}</p><p class="dcta-inst">${esc(c.instruction)}</p>`
        + `${c.urlNote ? `<span class="durl">${esc(c.urlNote)}</span>` : ""}</div>`
        + `<ol class="dflow dflow-compact">${flow}</ol><p class="dstat dstat-${esc(c.status)}">${esc(c.statusText)}</p>`;
    },
  };
  const BODY = {
    problem(c) {
      return `<h1 class="ftitle">${esc(c.title)}</h1>${fig(c.figure)}<p class="fline">${esc(c.line)}</p>`;
    },
    stack(c) {
      return `<h1 class="ftitle">${esc(c.title)}</h1>${fig(c.figure)}`
        + `<div class="fpair"><p class="ftext">${rich(c.text)}</p><p class="fcredit">${esc(c.credit)}</p></div>`;
    },
    timeline(c) {
      const tiles = c.tiles.map((t) => `<div class="tile"><b>${esc(t.value)}</b><span>${esc(t.label)}</span></div>`).join("");
      return `<h1 class="ftitle">${esc(c.title)}</h1>${fig(c.figure)}<div class="tiles">${tiles}</div>`;
    },
    gate(c) {
      const box = `<div class="variant v-${esc(c.variant)}"><span class="pill">${esc(c.label)}</span><p>${esc(c.text)}</p></div>`;
      if (c.figure) {
        return `<h1 class="ftitle">${esc(c.title)}</h1><p class="gtest">${esc(c.test)}</p>${fig(c.figure)}${box}`
          + `<p class="ver">${esc(c.verification)}</p>`;
      }
      const rows = c.rows.map((r) => `<tr><th>${esc(r.label)}<span>${esc(r.source)}</span></th><td>${esc(r.publishedC)} C</td>`
        + `<td class="res tone-${esc(r.tone)}">${esc(r.result)}</td><td class="dif tone-${esc(r.tone)}">${esc(r.diff || `must be within ${c.toleranceK} K`)}</td></tr>`).join("");
      return `<h1>${esc(c.title)}</h1><div class="common">${rich(c.common)}</div>`
        + `<table class="gt"><thead><tr><th>Reference</th><th>Paper</th><th>HotSpot 6.0</th><th>Difference</th></tr></thead><tbody>${rows}</tbody></table>`
        + box + `<p class="bottom">${esc(c.bottom)}</p>`;
    },
    checks(c) {
      return `<h1 class="ftitle">${esc(c.title)}</h1><div class="cks">${fig(c.figure, "ck-fig")}<div class="ck-text">`
        + `<p class="rline main-rline">${esc(c.line)}</p><p class="rattr">${esc(c.attribution)}</p>`
        + `<div class="study study-${esc(c.study.status)}"><span class="eyebrow">${esc(c.study.title)}</span><p>${esc(c.study.text)}</p></div></div></div>`;
    },
    teams(c) {
      return `<h1 class="ftitle">${esc(c.title)}</h1>${fig(c.figure)}`;
    },
    numbers(c) {
      if (c.placeholder) return `<h1>${esc(c.title)}</h1><div class="nplace"><span class="pill">PLACEHOLDER</span><p>${esc(c.placeholder)}</p></div>`;
      const tiles = c.items.map((x) => `<div class="ntile n-${esc(x.class.toLowerCase())}"><span class="nclass">${esc(x.tag)} · ${esc(x.n)}</span>`
        + `<b class="nval">${esc(x.value)}</b><p class="nlab">${esc(x.label)}</p></div>`).join("");
      return `<h1>${esc(c.title)}</h1><div class="ngrid n${c.items.length}">${tiles}</div>`;
    },
    demo(c) {
      if (c.still) return `<h1>${esc(c.title)}</h1>${stillLabel(c.still)}${still(c.still, 1100, "dstill")}<p class="dstat dstat-${esc(c.status)}">${esc(c.statusText)}</p>`;
      const flow = c.diagram.map((d) => `<li><b>${esc(d.title)}</b><span>${esc(d.text)}</span></li>`).join("");
      return `<h1>${esc(c.title)}</h1><div class="dinst"><p>${esc(c.instruction)}</p>${c.urlNote ? `<span class="durl">${esc(c.urlNote)}</span>` : ""}</div>`
        + `<ol class="dflow">${flow}</ol><p class="dstat dstat-${esc(c.status)}">${esc(c.statusText)}</p>`;
    },
    how(c) {
      const steps = c.steps.map((s, i) => `<li class="step"><span class="n">${i + 1}</span><b>${esc(s.title)}</b><p>${esc(s.text)}</p>`
        + `<p class="today"><span>31 Oct</span>${esc(s.today)}</p></li>`).join("");
      return `<h1>${esc(c.title)}</h1><ol class="steps">${steps}</ol><p class="foot">${esc(c.footnote)}</p>`
        + (c.evidence ? `<p class="rline main-rline">${esc(c.evidence)}</p>` : "");
    },
    gb10(c) {
      const rows = c.rows.map((r) => `<tr><td>${esc(r.label)}</td><td class="v">${esc(r.value)}</td></tr>`).join("");
      return `<h1>${esc(c.title)}</h1><div class="b8"><table class="rvt"><tbody>${rows}</tbody></table>${list(c.lines, "pts cav")}</div>`;
    },
    chronology(c) {
      const rows = c.rows.map((r) => `<tr><td class="t">${esc(r.at)}</td><td>${esc(r.text)}</td></tr>`).join("");
      return `<h1>${esc(c.title)}</h1><table class="chron"><tbody>${rows}</tbody></table>`;
    },
    reviews(c) {
      const rows = c.rows.map((r) => `<tr><td>${esc(r.label)}</td><td class="v">${esc(r.value)}</td></tr>`).join("");
      return `<h1>${esc(c.title)}</h1><p class="rline">${esc(c.line)}</p><p class="rattr">${esc(c.attribution)}</p>`
        + `<div class="b8"><table class="rvt"><tbody>${rows}</tbody></table>${list(c.caveats, "pts cav")}</div>`;
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
    view3d(c) {
      return `<h1>${esc(c.title)}</h1><span class="pill still-label">${esc(c.label)}</span>${still(c.still, 1280)}`;
    },
    profile(c) {
      return `<h1>${esc(c.title)}</h1>${fig(c.figure)}`;
    },
    layers(c) {
      const head = `<tr>${c.head.map((h) => `<th>${esc(h)}</th>`).join("")}</tr>`;
      const rows = c.rows.map((r) => `<tr><th>${esc(r.label)}</th>${r.values.map((v) => `<td>${esc(v)}</td>`).join("")}</tr>`).join("");
      return `<h1>${esc(c.title)}</h1><p class="rline">${esc(c.sentence)}</p><table class="lt"><thead>${head}</thead><tbody>${rows}</tbody></table>`
        + `<p class="lchip">${esc(c.chip)}</p><p class="lnote">${esc(c.note)}</p>`;
    },
    "gate-detail"(c) {
      const w = c.wordings.map((x) => `<div class="wd${x.chosen ? " chosen" : ""}"><span class="pill">${esc(x.label)}</span><p>${esc(x.text)}</p>${x.chosen ? `<span class="tag">this export</span>` : ""}</div>`).join("");
      const res = c.result ? `<div class="card gres"><div class="gres-h"><span class="pill">${esc(c.result.label)}</span><b>${esc(c.result.values)}</b>`
        + `<p class="ver">${esc(c.result.verification)}</p></div>${list(c.result.detail, "pts two")}<p>${esc(c.result.comparator)}</p></div>` : "";
      return `<h1>${esc(c.title)}</h1>${res}<div class="b3"><div class="card">${list(c.rules, "pts")}<p class="srcl">${esc(c.source)}</p>`
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
      return `<h1>${esc(c.title)}</h1><table class="rct"><tbody>${rows}</tbody></table>`
        + `<p class="notyet">${esc(c.notYet)} ${esc(c.names)}</p><p class="noev">${esc(c.notEvidence)}</p>`;
    },
    qa(c) {
      const items = c.items.map((x) => `<div class="qa-item"><dt>${esc(x.q)}</dt><dd>${esc(x.a)}</dd></div>`).join("");
      return `<h1>${esc(c.title)}</h1><dl class="qa">${items}</dl>`;
    },
  };
  // Footer notes that belong to a slide (the cutoff and the page label are on every slide).
  const LAYOUT_FOOT = {
    talk: (c) => c.caption ?? "",
    why: (c) => (c.numbers ? "Measured counts; the cost was posted so far when read, and is not the price of this experiment." : c.caption ?? ""),
    door: () => "Scores shown in the demo are simulated, not measured on silicon.",
  };
  const FOOT = {
    problem: (c) => c.caption,
    stack: (c) => c.caption,
    timeline: (c) => c.caption,
    gate: (c) => (c.scope ? `${c.scope} ${c.figureCaption}` : "The test and the wording for all three outcomes were written before any result."),
    checks: (c) => c.caption,
    teams: (c) => c.caption,
    numbers: (c) => (c.placeholder ? "Placeholder: no number on this slide has been checked yet."
      : c.items.map((x) => `${x.n}. ${x.caveat}`).join(" ")),
    demo: () => "Scores shown in the demo are simulated, not measured on silicon.",
    profile: (c) => c.caption,
    view3d: (c) => c.caption,
    layers: (c) => c.caption,
    gb10: () => "Measured wall times from the run records. This slide reports no human time saved.",
    chronology: (c) => c.note,
    metrics: () => "No value here is a calibrated temperature.",
  };
  const MARKS = { preview: "PREVIEW · not a result", reviewOnly: "REVIEW · not the recorded result", demoReview: "REVIEW · door variant, not the export" };

  function renderSlide(s, data) {
    const layout = s.content.layout;
    const body = layout ? LAYOUTS[layout] : BODY[s.id];
    if (!body) throw new Error(`no layout for slide ${s.id}`);
    const note = (layout ? LAYOUT_FOOT[layout] : FOOT[s.id])?.(s.content) ?? "";
    const mark = Object.keys(MARKS).filter((k) => data.deck[k]).map((k) => `<span class="preview">${MARKS[k]}</span>`).join("");
    return `<section class="slide ${s.main ? "main" : "backup"}" id="s-${esc(s.id)}" data-label="${esc(s.label)}" data-notes="${esc(s.id)}">`
      + `<header class="bar"><span class="brand"><i class="mark"></i><b>${esc(data.deck.title)}</b><span>${esc(data.deck.event)}</span></span>${mark}<span class="kicker">${esc(s.kicker)}</span></header>`
      + `<div class="body">${body(s.content, data)}</div>`
      + `<footer class="src"><span class="cut">Facts as of ${esc(data.deck.cutoff)}</span><span class="fn">${esc(note)}</span><span class="pg">${esc(s.label)}</span></footer>`
      + `</section>`;
  }
  function renderSlides(data) {
    if (data?.schema !== "sentilab-deck-final-data/2") throw new Error(`unsupported deck data ${JSON.stringify(data?.schema)}`);
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
    // Every figure must have loaded before the deck reports ready (the exporter waits for this).
    await Promise.all([...deck.querySelectorAll("img")].map((img) => (img.complete ? null : new Promise((ok) => { img.onload = ok; img.onerror = ok; }))));
    const slides = [...deck.querySelectorAll(".slide")];
    const byId = new Map(data.slides.map((s) => [s.id, s]));
    const notesEl = doc.getElementById("notes");
    if (params.has("print")) doc.body.classList.add("print");
    const fit = () => deck.style.setProperty("--s", String(Math.min(win.innerWidth / W, win.innerHeight / H)));
    fit();
    win.addEventListener("resize", fit);

    const u = data.budget;
    let i = 0, t0 = Date.now();
    function renderNotes() {
      const s = byId.get(slides[i].dataset.notes);
      const el = Math.floor((Date.now() - t0) / 1000);
      notesEl.querySelector(".n-pos").textContent = `${s.label} · ${s.kicker}`;
      notesEl.querySelector(".n-target").textContent = !s.main ? "backup · not in the five minutes"
        : s.id === "demo" ? `${s.notes.words} words · ${s.notes.seconds} s, inside the ${u.demoSeconds} s demo clock`
          : `${s.notes.words} words · ${s.notes.seconds} s · talk ${u.talkSeconds} s + ${u.transitionSeconds} s of ${u.talkCapSeconds} s`;
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
