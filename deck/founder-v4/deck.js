/* SentiLab founder pitch (v4): Carter's three-minute main talk, ten main slides with one point and one picture each, then
 * the sources page, authored once at 1920x1080 and scaled to the window.
 *
 * Every word on a slide comes from deck-data.json, which scripts/build-deck-founder.mjs generates from
 * docs/sentilab/deck/founder-v4/V4.json. renderSlides() is a pure string function, so the node test renders exactly what
 * the browser renders. A number that is not measured yet shows "measuring…" in its own style, never an estimate.
 *
 * Keys: Right/Down/Space/PageDown next · Left/Up/PageUp previous · Home/End · F fullscreen · N speaker notes · R reset clock.
 * ?print=1 lays every slide out as a 1920x1080 page (export-deck-pdf.mjs --deck founder prints it to PDF).
 */
(function (host, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else { host.FounderDeck = api; if (host.document) api.boot(host); }
})(typeof window !== "undefined" ? window : globalThis, function () {
  "use strict";
  const W = 1920, H = 1080;
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const h1 = (c, cls = "") => (c.title ? `<h1 class="${cls}">${esc(c.title)}</h1>` : "");
  const pill = (t, cls = "") => (t ? `<span class="pill ${cls}">${esc(t)}</span>` : "");
  // A still at a declared width; it holds no text the checks could read.
  const still = (st, w) => `<figure class="fig still"><img src="${esc(st.src)}" alt="${esc(st.alt)}" width="${w}" height="${Math.round((st.height * w) / st.width)}" data-still="${esc(st.id)}"></figure>`;
  // A figure at the scale the source sets; the exporter holds its smallest text to the type floor.
  const fig = (f) => {
    const w = Math.round(f.width * f.scale), h = Math.round(f.height * f.scale);
    return `<figure class="fig"><img src="${esc(f.src)}" alt="${esc(f.alt)}" width="${w}" height="${h}" data-fig="${esc(f.id)}" data-min-font="${esc(f.minFont)}" data-natural-width="${esc(f.width)}"></figure>`;
  };
  // A number tile; one not measured yet says so, in its own style; a measured one prints its time window.
  const tile = (t) => `<div class="tile${t.measuring ? " is-measuring" : ""}"><b class="${t.measuring ? "measuring" : "tv"}">${esc(t.value)}</b><span class="tl">${esc(t.label)}</span>${t.when ? `<span class="tw">${esc(t.when)}</span>` : ""}</div>`;

  const LAYOUTS = {
    joke(c) {
      return `${h1(c, "big")}<div class="joke"><div class="jpic">${pill(c.still.label, "warn")}${still(c.still, 900)}</div><p class="jcap">${esc(c.caption)}</p></div>`;
    },
    flow(c) {
      const steps = c.steps.map((s, i) => `<li class="fstep"><span class="fn">${i + 1}</span><b>${esc(s.verb)}</b><span>${esc(s.what)}</span></li>`).join("");
      return `${h1(c)}<ol class="fsteps">${steps}</ol><div class="fchips">${c.chips.map((x) => pill(x, "cy")).join("")}</div><p class="fapps">${esc(c.apps)}</p>${c.stats ? `<div class="fstats">${c.stats.map((x) => `<div class="fstat"><b>${esc(x.value)}</b><span>${esc(x.label)}</span></div>`).join("")}</div>` : ""}`;
    },
    numbers(c) {
      const tiles = `<div class="tiles n${c.tiles.length}${c.still ? " with-pic" : ""}">${c.tiles.map(tile).join("")}</div>`;
      const points = c.points ? `<ul class="npoints">${c.points.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>` : "";
      // With a picture (the door's QR code), the tiles sit two by two beside it.
      return c.still ? `${h1(c)}<div class="npic"><div>${tiles}${points}</div>${still(c.still, 420)}</div>` : `${h1(c)}${tiles}${points}`;
    },
    // Slide 9 at a freeze with no measured number: the fallback picture, with the door's QR code beside it.
    fallback(c) {
      return `<div class="fb">${fig(c.figure)}<div class="fbqr">${still(c.still, 200)}${c.points ? `<p>${esc(c.points[0])}</p>` : ""}</div></div>`;
    },
    bars(c) {
      const bars = c.bars.map((b) => `<div class="hbar hbar-${esc(b.tone)}"><span class="hbar-fill" style="width:${(b.share * 100).toFixed(2)}%"></span>`
        + `<b class="hbar-val">${esc(b.show)}</b><span class="hbar-lab">${esc(b.label)}</span></div>`).join("");
      return `${h1(c)}<p class="blabel">${pill(c.label, "warn")}</p><div class="hbars">${bars}</div>`;
    },
    times(c) {
      return `${h1(c)}<div class="times">${c.times.map((t) => `<div class="time"><b>${esc(t.show)}</b><span>${esc(t.what)}</span></div>`).join("")}</div>`;
    },
    figure(c) {
      return `${h1(c)}${c.label ? `<p class="blabel">${pill(c.label, "warn")}</p>` : ""}<div class="fwrap">${fig(c.figure)}</div>${c.line ? `<p class="fline">${esc(c.line)}</p>` : ""}`;
    },
    tiles(c) {
      return `${h1(c)}<p class="blabel">${pill(c.label, "warn")}</p><div class="pair">${c.tiles.map((t) => `<div class="ptile ptile-${esc(t.tone)}"><b>${esc(t.head)}</b><p>${esc(t.body)}</p></div>`).join("")}</div>`;
    },
    statement(c) {
      return `${h1(c, "big")}<ol class="loop">${c.flow.map((x) => `<li>${esc(x)}</li>`).join("")}</ol><p class="punch">${esc(c.punch)}</p>`;
    },
    closer(c) {
      return `<div class="closer"><p class="ctext">${esc(c.text)}</p><p class="cpunch">${esc(c.punch)}</p></div>`;
    },
    sources(c) {
      return `${h1(c)}<ul class="srclist">${c.items.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
    },
  };

  function renderSlide(s, data) {
    const body = LAYOUTS[s.content.layout];
    if (!body) throw new Error(`no layout for slide ${s.id}`);
    // A figure still pending its reviewer's +1 says so on its own slide; the freeze refuses it altogether.
    const note = s.content.figure?.pending ? " · figure pending review" : data.deck.measuring ? " · numbers still measuring" : "";
    const mark = data.deck.draft ? `<span class="preview">DRAFT${note}</span>` : "";
    return `<section class="slide ${s.main ? "main" : "backup"}" id="s-${esc(s.id)}" data-label="${esc(s.label)}" data-notes="${esc(s.id)}">`
      + `<header class="bar"><span class="brand"><i class="mark"></i><b>${esc(data.deck.title)}</b><span>${esc(data.deck.event)}</span></span>${mark}<span class="kicker">${esc(s.kicker)}</span></header>`
      + `<div class="body l-${esc(s.content.layout)}">${body(s.content, data)}</div>`
      + `<footer class="src"><span class="cut">Facts as of ${esc(data.deck.cutoff)}</span><span class="fn">${esc(s.content.footer ?? "")}</span><span class="pg">${esc(s.label)}</span></footer>`
      + `</section>`;
  }
  function renderSlides(data) {
    if (data?.schema !== "sentilab-deck-founder-data/1") throw new Error(`unsupported deck data ${JSON.stringify(data?.schema)}`);
    return data.slides.map((s) => renderSlide(s, data)).join("\n");
  }

  // ── browser ────────────────────────────────────────────────────────────────────────────────
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
      notesEl.querySelector(".n-target").textContent = s.main ? `${s.notes.words} words · ${s.notes.seconds} s · talk ${u.talkSeconds} s + ${u.transitionSeconds} s of ${u.talkCapSeconds} s` : "backup · not in the three minutes";
      notesEl.querySelector(".n-clock").textContent = `${Math.floor(el / 60)}:${String(el % 60).padStart(2, "0")} elapsed`;
      notesEl.querySelector(".n-text").textContent = s.main ? s.notes.text : "Backup: not spoken.";
      notesEl.querySelector(".n-cue").textContent = s.main && s.notes.cue ? `Cue: ${s.notes.cue}` : "";
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
    win.__deck = { ready: true, from, count: slides.length, go: (k) => show(k), ids: slides.map((s) => s.id), main: data.slides.map((s) => s.main), preview: data.deck.measuring };
  }

  return { renderSlides, renderSlide, LAYOUTS, esc, boot };
});
