/* SentiLab daytime deck. Slides are authored once at 1920x1080 and scaled to the window.
 *
 * Every value on a slide comes from deck-data.json, which the build-deck-data script generates from the selected
 * packet's typed day update:
 *   <span data-f="a047b.lifecycle"></span>   the fact's display text; a typed null shows its stated label ("unknown")
 *   <span data-asof="key key"></span>        "<kind> <time> · <source>" for those facts: observed, reviewed, corrected...
 *   <ul data-gen="engineering"></ul>         a block generated from deck-data lists
 *   <footer data-gen="sources"></footer>     the fact cutoff, then the dated source of every value on the slide that
 *                                            no stamp on the slide already dates
 * renderHtml() is a pure string function, so the node test renders exactly what the browser renders.
 *
 * Keys: Right/Down/Space/PageDown next · Left/Up/PageUp previous · Home/End · F fullscreen · N speaker notes.
 * ?print=1 lays every slide out as a 1920x1080 page (the export-deck-pdf script prints it to PDF).
 * Deck v1 (../deck.js, ../index.html) is a frozen historical artifact; this deck only reuses its images.
 */
(function (host, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else { host.Deck = api; if (host.document) api.boot(host); }
})(typeof window !== "undefined" ? window : globalThis, function () {
  "use strict";
  const W = 1920, H = 1080;
  const MISSING = "— (missing value)";
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const addClass = (attrs, cls) => (/\bclass="/.test(attrs) ? attrs.replace(/\bclass="([^"]*)"/, (m, c) => `class="${c} ${cls}"`) : `${attrs} class="${cls}"`);
  const dated = (x) => `${x.asOfKind} ${x.asOf}`;
  const TONE = {
    scoped_accepted: "ok", CLOSED: "ok", CLOSED_SCOPED: "ok", OPEN: "warn", changes_requested: "warn", open: "warn", measured: "info",
    done: "ok", superseded: "muted",
  };
  const pill = (text, status) => `<span class="pill tone-${esc(TONE[status] ?? "info")}">${esc(text)}</span>`;
  const items = (list) => (list ?? []).map((t) => `<li>${esc(t)}</li>`).join("");

  // ── generated blocks ──────────────────────────────────────────────────────────────────────────────────────────────
  // Each generator receives the data and note(source, item, shown): an item's dated source goes in the slide footer,
  // unless shown is true because the block prints that time itself.
  const GEN = {
    accepted(data, note) {
      return (data.lists?.engineering ?? []).map((m) => {
        note("engineering record", m);
        return `<li><b>${esc(m.pr)}</b><span>${esc(m.title)}<i class="ev">${esc(m.evidence)}</i></span></li>`;
      }).join("");
    },
    engineering(data, note) {
      const cards = (data.lists?.engineering ?? []).map((m) => {
        note("engineering record", m, true);
        const sha = m.head && m.merge ? `<p class="sha">head <code>${esc(m.head)}</code> → merge <code>${esc(m.merge)}</code></p>` : "";
        const hist = (m.superseded ?? []).map((h) => `<p class="hist"><b>Superseded history</b> ${esc(h.recorded)}: ${esc(h.prior)}. Replaced at ${esc(h.superseded)} by: ${esc(h.now)}.</p>`).join("");
        const text = [m.title, m.summary ?? "", ...(m.limits ?? []), ...(m.superseded ?? []).map((h) => h.prior)].join(" ");
        return { size: text.length + 160, html: `<article class="eng-c"><div class="eng-h"><b>${esc(m.pr)}</b>${pill(m.statusLabel, m.status)}<span class="eng-t">${esc(dated(m))}</span></div>`
          + `<h3>${esc(m.title)}</h3>${sha}<p class="ev">Evidence: ${esc(m.evidence)}</p>${m.summary ? `<p class="sum">${esc(m.summary)}</p>` : ""}`
          + `${m.limits?.length ? `<ul class="lim">${items(m.limits)}</ul>` : ""}${hist}</article>` };
      });
      // Two columns in time order: the first takes cards until it holds about half of the text.
      const half = cards.reduce((n, c) => n + c.size, 0) / 2;
      let filled = 0, split = 0;
      while (split < cards.length - 1 && filled + cards[split].size / 2 < half) filled += cards[split++].size;
      const col = (cs) => `<div class="eng-col">${cs.map((c) => c.html).join("")}</div>`;
      return col(cards.slice(0, split)) + col(cards.slice(split));
    },
    findings(data, note) {
      return (data.lists?.findings ?? []).map((f) => {
        note("PR55 corrective review", f);
        return `<li class="fd-${esc(f.status)}"><span class="fd-sev">${esc(f.severity)}</span>${pill(f.statusLabel, f.status)}<span class="fd-s">${esc(f.scope)}</span></li>`;
      }).join("");
    },
    pr55History(data, note) {
      return (data.lists?.pr55History ?? []).map((h) => {
        note("PR55 earlier review", h, true);
        return `<p><b>History, superseded ${esc(h.superseded)}</b> The earlier review of head <code>${esc(h.head)}</code>, as recorded at ${esc(h.recorded)}: “${esc(h.summary)}”</p>`;
      }).join("");
    },
    tracks(data, note) {
      return (data.lists?.tracks ?? []).map((t) => {
        note("supplemental tracks", t);
        return `<li><div class="tr-h"><b>${esc(t.name)}</b><span class="tr-st">${esc(t.statusLabel)}</span></div><span class="tr-p">${esc(t.purpose)}</span></li>`;
      }).join("");
    },
    helpLimits(data, note) {
      return (data.lists?.helpLimits ?? []).map((l) => { note("help-room record", l); return `<li>${esc(l.text)}</li>`; }).join("");
    },
    bindings(data, note) {
      return (data.lists?.bindings ?? []).map((b) => { note("gate-zero design", b); return `<li>${esc(b.text)}</li>`; }).join("");
    },
    claims(data, note) {
      return (data.lists?.claims ?? []).map((c) => {
        note("claim corrections", c, true);
        const now = c.replacement ? `<p class="cl-r">${esc(c.replacement)}</p>` : `<p class="cl-r cl-none">No replacement claim. ${esc(c.reason)}</p>`;
        return `<li><div class="cl-h"><b>${esc(c.topic)}</b>${pill(c.statusLabel, c.status)}<span class="cl-t">${esc(dated(c))}</span></div>${now}${c.replacement ? `<p class="cl-why">${esc(c.reason)}</p>` : ""}</li>`;
      }).join("");
    },
    science(data, note) {
      return (data.lists?.science ?? []).map((m) => {
        note(m.critique ? "informed critique" : "saved-field review", m, true);
        return `<article class="sci-c"><div class="eng-h"><b>${esc(m.title)}</b><span class="eng-t">${esc(dated(m))}</span></div>`
          + `<p class="sum">${esc(m.summary)}</p><ul class="lim">${items(m.limits)}</ul></article>`;
      }).join("");
    },
    research(data, note) {
      return (data.lists?.research ?? []).map((m) => {
        note("cloud assessment", m, true);
        return `<div class="rs"><div class="eng-h"><b>${esc(m.title)}</b><span class="eng-t">${esc(dated(m))}</span></div>${pill(m.statusLabel, "measured")}<ul class="lim">${items(m.limits)}</ul></div>`;
      }).join("");
    },
    coverage(data, note) {
      const tickets = data.lists?.tickets ?? [], dels = data.lists?.deliverables ?? [], tracks = data.lists?.tracks ?? [];
      if (!tickets.length || !dels.length) return `<div class="pending">${MISSING}</div>`;
      const chip = (t) => { note("original scope", t); return `<span class="tk st-${esc(t.status)}${t.optional ? " opt" : ""}" title="${esc(t.id)} · ${esc(t.status)} at the baseline">${esc(t.n)}</span>`; };
      const byId = new Map(tickets.map((t) => [t.id, t]));
      const rows = dels.map((d) => {
        note("original scope", d);
        const ts = (d.tickets ?? []).map((id) => byId.get(id)).filter(Boolean);
        return `<div class="cv-row"><div class="cv-d"><b>${esc(d.id)}</b><span class="cv-sub">${esc(d.baselineStatus)} · ${d.accepted ? "accepted" : "not accepted"}</span></div><div class="cv-t">${ts.map(chip).join("")}</div></div>`;
      });
      const mapped = new Set(dels.flatMap((d) => d.tickets ?? []));
      rows.push(`<div class="cv-row cv-rest"><div class="cv-d"><b>Shared</b><span class="cv-sub">cross-cutting</span></div><div class="cv-t">${tickets.filter((t) => !mapped.has(t.id)).map(chip).join("")}</div></div>`);
      rows.push(`<div class="cv-row cv-sup"><div class="cv-d"><b>Added</b><span class="cv-sub">outside the original tickets</span></div><div class="cv-t">${tracks.map((t) => { note("supplemental tracks", t); return `<span class="tk st-sup" title="${esc(t.id)} · ${esc(t.statusLabel)}">${esc(t.id.replace(/^SLAB-/, ""))}</span>`; }).join("")}</div></div>`);
      return rows.join("");
    },
    legend(data) {
      const lg = data.lists?.statusLegend ?? {};
      return ["measured", "open"].filter((k) => lg[k]).map((k) => `<p><span class="tk st-${k}">${esc(k)}</span>${esc(lg[k])}</p>`).join("")
        + `<p><span class="tk st-sup">added</span>A supplemental track: added work, not part of the original ticket count.</p>`;
    },
  };

  // ── rendering ─────────────────────────────────────────────────────────────────────────────────────────────────────
  function renderSection(sec, data) {
    const facts = data.facts ?? {};
    const used = [];            // facts shown on this slide
    const listed = [];          // dated list items shown on this slide
    const stamped = new Set();  // "source|kind|time" already printed in a stamp on this slide
    const key3 = (source, x) => `${source}|${x.asOfKind}|${x.asOf}`;
    const note = (source, item, shown = false) => {
      if (!item?.asOf) return;
      if (shown) stamped.add(key3(source, item)); else listed.push({ source, item });
    };

    sec = sec.replace(/<(span|b|strong|em|i|div|p|h1|h2|h3|li|code)\b([^>]*?)\sdata-f="([\w.]+)"([^>]*)>\s*<\/\1>/g, (m, tag, pre, key, post) => {
      const f = facts[key];
      if (f) used.push(f);
      const attrs = `${pre} data-f="${key}"${post}${f ? ` title="${esc(dated(f))} · ${esc(f.source)}"` : ""}`;
      const cls = !f ? "pending" : f.value == null ? "nullv" : null;
      return `<${tag}${cls ? addClass(attrs, cls) : attrs}>${esc(f ? f.display : MISSING)}</${tag}>`;
    });
    sec = sec.replace(/<(span|div|p)\b([^>]*?)\sdata-asof="([\w. ]+)"([^>]*)>\s*<\/\1>/g, (m, tag, pre, keys, post) => {
      // One line per source: "<source> <kind> <time>, <kind> <time>".
      const bySource = new Map();
      for (const k of keys.trim().split(/\s+/)) {
        const f = facts[k];
        if (!f) continue;
        stamped.add(key3(f.source, f));
        const times = bySource.get(f.source) ?? bySource.set(f.source, []).get(f.source);
        if (!times.includes(dated(f))) times.push(dated(f));
      }
      const parts = [...bySource].map(([source, times]) => `<span class="st-i"><b>${esc(source)}</b> ${esc(times.join(", "))}</span>`);
      return `<${tag}${pre} data-asof="${keys}"${post}>${parts.length ? parts.join("") : esc(MISSING)}</${tag}>`;
    });
    sec = sec.replace(/<(div|ul|ol)\b([^>]*?)\sdata-gen="(\w+)"([^>]*)>\s*<\/\1>/g, (m, tag, pre, name, post) => {
      if (!GEN[name]) return m;
      return `<${tag}${pre} data-gen="${name}"${post}>${GEN[name](data, note)}</${tag}>`;
    });
    sec = sec.replace(/<(footer)\b([^>]*?)\sdata-gen="sources"([^>]*)>\s*<\/\1>/, (m, tag, pre, post) => {
      // The cutoff first; then, per source, every distinct dated time of a value shown here and not stamped already.
      const bySource = new Map();
      // A time at the fact cutoff is already dated by "Facts through".
      const atCutoff = (x) => x.asOfKind === "cutoff" && x.asOf === data.source?.factCutoff;
      const add = (source, x) => {
        if (stamped.has(key3(source, x)) || atCutoff(x)) return;
        (bySource.get(source) ?? bySource.set(source, new Set()).get(source)).add(dated(x));
      };
      for (const f of used) add(f.source, f);
      for (const { source, item } of listed) add(source, item);
      const parts = [...bySource].filter(([, t]) => t.size).map(([source, times]) => `<span class="src-i"><b>${esc(source)}</b> ${esc([...times].sort((a, b) => a.slice(-20).localeCompare(b.slice(-20)) || a.localeCompare(b)).join(", "))}</span>`);
      const cut = data.source?.factCutoff ? `<span class="src-i src-cut">Facts through ${esc(data.source.factCutoff)}</span>` : "";
      const noteText = /\bdata-note="([^"]*)"/.exec(`${pre}${post}`)?.[1];
      const rest = parts.length ? parts.join("") : `<span class="src-i">${noteText ?? "every value on this slide is stamped with its source time"}</span>`;
      return `<${tag}${pre} data-gen="sources"${post}><span class="src-h">Data</span>${cut}${rest}</${tag}>`;
    });
    return sec;
  }
  function renderHtml(html, data) {
    return html.replace(/<section\b[^>]*\bclass="slide\b[^"]*"[^>]*>[\s\S]*?<\/section>/g, (sec) => renderSection(sec, data));
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
    // Served over http(s): read deck-data.json. Opened from disk (file:, where fetch is refused): use the generated
    // script copy, which the node test proves is the same object.
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
    deck.innerHTML = renderHtml(deck.innerHTML, data);
    const slides = [...deck.querySelectorAll(".slide")];
    const notesById = new Map((data.notes ?? []).map((n) => [n.slide, n]));
    const notesEl = doc.getElementById("notes");
    const print = params.has("print");
    let i = 0, t0 = Date.now();

    if (print) doc.body.classList.add("print");
    const fit = () => deck.style.setProperty("--s", String(Math.min(win.innerWidth / W, win.innerHeight / H)));
    fit();
    win.addEventListener("resize", fit);

    const label = (k) => slides[k].dataset.label || "";
    function renderNotes() {
      const n = notesById.get(slides[i].dataset.notes);
      const s = Math.floor((Date.now() - t0) / 1000);
      notesEl.querySelector(".n-pos").textContent = `${label(i)} · ${slides[i].dataset.title || ""}`;
      notesEl.querySelector(".n-target").textContent = n ? `target ${n.target}` : "";
      notesEl.querySelector(".n-clock").textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")} elapsed`;
      notesEl.querySelector(".n-text").textContent = n ? n.text : "";
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
    win.__deck = { ready: true, from, count: slides.length, go: (k) => show(k), ids: slides.map((s) => s.id), labels: slides.map((s) => s.dataset.label) };
  }

  return { renderHtml, GEN, MISSING, esc, boot };
});
