/* SentiLab dated supplement: card generators for the daytime deck engine (../daytime/deck.js).
 *
 * The engine and its stylesheet are reused unchanged (both are frozen with the daytime deck). This file only adds
 * generators to the engine's GEN table. The engine renders on DOMContentLoaded, after this script has run.
 *   <div data-gen="supp_merged"></div>     the cards of one slide group, in the order the build fixed
 *   <ol data-gen="supp_index"></ol>        every item by slide: its title and claim status
 *   <p data-gen="supp_provenance"></p>     the delivered supplement and the accepted packet it supplements
 * It renders only supplement data in the one supported format. Any other data stops the render, and the engine shows
 * its "could not be loaded" banner, so an unknown format never reaches a slide. Every value is printed as the build
 * wrote it: claim status, evidence class and times exactly, a typed unknown as "unknown", never 0.
 */
(function (host, factory) {
  const plugin = factory();
  if (typeof module === "object" && module.exports) module.exports = plugin;
  else plugin.install(host.Deck);
})(typeof window !== "undefined" ? window : globalThis, function () {
  "use strict";
  const SCHEMA = "sentilab-deck-supplement-data/1";
  const FORMAT = "sentilab-deck-facts/1";
  // Slide order: S2 onwards. The deck test checks it against the build's groups and the page's slides.
  const GROUPS = ["merged", "withdrawal", "accepted", "pending", "observed", "agentsite", "science", "gate", "scope", "history"];

  function supported(data) {
    if (data?.schema !== SCHEMA || data?.source?.format !== FORMAT) {
      throw new Error(`this deck renders only ${FORMAT} supplement data (${SCHEMA}), not format ${JSON.stringify(data?.source?.format)} with schema ${JSON.stringify(data?.schema)}; nothing is rendered`);
    }
    return data;
  }
  const need = (x, field, where) => {
    const v = x?.[field];
    if (typeof v !== "string" || !v) throw new Error(`${where}: ${field} is missing; nothing is rendered`);
    return v;
  };

  function install(Deck) {
    if (!Deck?.GEN || typeof Deck.esc !== "function") throw new Error("load ../daytime/deck.js before supplement.js");
    const esc = Deck.esc;
    const fact = (f, where) => {
      const unknown = f.value === null;
      if (unknown && f.display !== "unknown") throw new Error(`${where}: a typed unknown must show "unknown"`);
      return `<div class="sp-fi"><dt>${esc(need(f, "label", where))}</dt><dd${unknown ? ' class="nullv"' : ""}>${esc(need(f, "display", where))}</dd></div>`;
    };
    const card = (it) => {
      const where = `item ${it?.k}`;
      if (!Array.isArray(it?.qualifications) || !it.qualifications.length || !Array.isArray(it.facts) || !it.facts.length) {
        throw new Error(`${where}: qualifications and facts are required; nothing is rendered`);
      }
      return `<article class="sp-c" data-k="${esc(it.k)}"><div class="sp-x">`
        + `<h3>${esc(need(it, "title", where))}</h3>`
        + `<p class="sp-m"><span class="sp-l">status</span><code class="sp-st">${esc(need(it, "claimStatus", where))}</code>`
        + `<span class="sp-l">evidence</span><code class="sp-ev">${esc(need(it, "evidenceClass", where))}</code></p>`
        + `<p class="sp-m"><span class="sp-l">source</span><span class="sp-t${it.source === null ? " nullv" : ""}">${esc(it.source === null ? "unknown" : need(it, "source", where))}</span>`
        + `<span class="sp-l">observed or checkpoint</span><span class="sp-t">${esc(need(it, "observed", where))}</span></p>`
        + `<p class="sp-d">${esc(need(it, "display", where))}</p>`
        + `<ul class="sp-q">${it.qualifications.map((q) => `<li>${esc(q)}</li>`).join("")}</ul></div>`
        + `<dl class="sp-f">${it.facts.map((f) => fact(f, `${where} fact ${f?.key}`)).join("")}</dl></article>`;
    };
    for (const g of GROUPS) {
      Deck.GEN[`supp_${g}`] = (data) => {
        const list = supported(data).lists?.groups?.[g];
        if (!Array.isArray(list) || !list.length) throw new Error(`the supplement data has no ${g} items; nothing is rendered`);
        return list.map(card).join("");
      };
    }
    Deck.GEN.supp_index = (data) => {
      const groups = supported(data).lists?.groups ?? {};
      return GROUPS.map((g, i) => (groups[g] ?? []).map((x) => `<li><b>S${i + 2}</b><span class="sp-it">${esc(need(x, "title", `item ${x.k}`))}</span>`
        + `<code>${esc(need(x, "claimStatus", `item ${x.k}`))}</code></li>`).join("")).join("");
    };
    Deck.GEN.supp_provenance = (data) => {
      const s = supported(data).source;
      const short = (h) => `${esc(String(h).slice(0, 12))}…`;
      return `<span><b>Delivered supplement</b> SHA256 <code>${short(s.supplementSha256)}</code> · schema <code>${short(s.schemaSha256)}</code> · format <code>${esc(s.format)}</code></span>`
        + `<span><b>Accepted packet</b> manifest SHA256 <code>${short(s.acceptedPacket?.manifestSha256)}</code> · commit <code>${short(s.acceptedPacket?.commit)}</code></span>`;
    };
    return Deck;
  }

  return { install, SCHEMA, FORMAT, GROUPS };
});
