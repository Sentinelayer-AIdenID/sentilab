# repo-01: verbatim excerpts of our code at origin/main 46791be360555d0e24b4ad5f906abafb71f07118

Produced with `git -C H:/sentilab show 46791be360555d0e24b4ad5f906abafb71f07118:<path>` (read-only). Line numbers are the file's own. Each block names the git blob id of the file at that commit.

### web/src/csp.js

blob `db1064a30b83f480e8aff3bbffcc4c527b58db8b`

```text
    1  // The Content-Security-Policy every static asset response carries (web/src/worker.js adds it), so only our own scripts
    2  // run on the verifier pages: a script the edge injects into the HTML on its way out (its analytics script), any inline
    3  // script or inline style, eval, and any other origin are all refused by the browser. The pages hold no inline code (no
    4  // <script> or <style> blocks, no on* or style="" attributes; styles set from script use the CSSOM).
    5  // A module of its own on purpose: the Workers runtime treats every named export of the Worker's main module as an
    6  // entry point, so worker.js exports nothing but its default handler.
    7  export const CSP = "default-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'";
```

### web/src/worker.js

blob `a37d04a39d8daac00bf1ed35e238f4302826f396`

```text
    1  // sentilab.aidenid.com: static assets from ./public, and read-only /api/* proxied to the sentilab-api Azure Container App
    2  // (API_ORIGIN). The upstream body streams through, so server-sent events work unchanged.
    3  // This module's only export is the default handler: the Workers runtime treats every named export of the main module
    4  // as an entry point and refuses to start on anything else (web/test/worker-boot.mjs boots it in CI).
    5  import { CSP } from "./csp.js";
    6  
    7  const HOP = ["connection", "keep-alive", "transfer-encoding", "upgrade", "host"];
```

```text
   14  async function asset(request, env) {
   15    const res = await env.ASSETS.fetch(request);
   16    const headers = new Headers(res.headers);
   17    headers.set("content-security-policy", CSP);
   18    return new Response(res.body, { status: res.status, statusText: res.statusText, headers });
   19  }
   20  
   21  async function proxy(request, env) {
   22    const origin = String(env.API_ORIGIN || "").replace(/\/+$/, "");
   23    if (!origin.startsWith("https://")) return new Response("API origin not configured", { status: 503 });
   24    const url = new URL(request.url);
   25    const headers = new Headers(request.headers);
   26    for (const h of HOP) headers.delete(h);
   27    headers.set("x-forwarded-host", url.host);
   28    // Only this Worker holds the origin token; the Container App refuses requests without it.
   29    if (env.ORIGIN_TOKEN) headers.set("x-origin-token", env.ORIGIN_TOKEN);
   30    else headers.delete("x-origin-token");
   31    const init = { method: request.method, headers, redirect: "manual" };
   32    if (!["GET", "HEAD"].includes(request.method)) init.body = request.body;
   33    const upstream = await fetch(origin + url.pathname + url.search, init);
   34    const out = new Headers(upstream.headers);
   35    if (!out.has("cache-control")) out.set("cache-control", "no-store");
   36    return new Response(upstream.body, { status: upstream.status, headers: out });
   37  }
```

```text
   48  export default {
   49    async fetch(request, env) {
   50      const { pathname } = new URL(request.url);
   51      // SentiLab is hands-off: the service runs its own loop, so the public edge is read-only. No caller can start
   52      // runs or reach any write route from outside.
   53      if ((pathname === "/api" || pathname.startsWith("/api/")) && !["GET", "HEAD"].includes(request.method)) {
   54        return new Response(JSON.stringify({ error: "read_only", detail: "The public SentiLab API is read-only." }),
   55          { status: 405, headers: { "content-type": "application/json", allow: "GET, HEAD", "cache-control": "no-store" } });
   56      }
   57      if (request.method === "POST" && pathname === "/api/runs" && !(await allowRunStart(request, env))) {
   58        return new Response(JSON.stringify({ error: "rate_limited", detail: "Too many runs started; wait a minute." }),
   59          { status: 429, headers: { "content-type": "application/json", "retry-after": "60", "cache-control": "no-store" } });
   60      }
   61      if (pathname === "/api" || pathname.startsWith("/api/")) return proxy(request, env);
   62      return asset(request, env);
   63    },
```

### web/wrangler.jsonc

blob `1a3fa3614df099935e3fdf58abfceb66710fd438`

```text
    8    // run_worker_first: true, so static assets go through the Worker too and get its Content-Security-Policy header.
    9    "assets": { "directory": "./public", "binding": "ASSETS", "run_worker_first": true },
   10    "routes": [{ "pattern": "sentilab.aidenid.com", "custom_domain": true }],
   11    "vars": { "API_ORIGIN": "https://sentilab-api.graysea-7ff72f94.eastus2.azurecontainerapps.io" },
```

### web/README.md

blob `f7bbb8a7d31e124269b1c0536c11253d6aa33b07`

```text
    1  # thermal.aidenid.com front door
    2  
    3  A Cloudflare Worker (`thermal-flight-lab-web`) serves `public/` as static assets and proxies `/api/*` to the
    4  thermal-api Azure Container App named in `wrangler.jsonc` (`API_ORIGIN`). Responses stream, so server-sent events
    5  pass through unchanged. The custom domain is attached by the `routes` entry.
    6  
    7  Deploy (warden): `npx wrangler deploy` from this directory. The frontend build (TFL-10) replaces `public/` with the
    8  Vite output directory.
```

### web/test/worker-csp.test.mjs

blob `8ebe93fed9761eaa74925d08222094674ae14950`

```text
   19  // The policy, written out here on purpose: the test pins the exact header value, not whatever the module exports.
   20  const EXACT = "default-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'";
```

```text
   47  test("the exported policy is exactly the reviewed one", () => {
   48    assert.equal(CSP, EXACT);
   49  });
```

### web/public/sentilab/package/index.html

blob `6167d0450ef728c075b7eda1c2abf42832c8820a`

```text
   56          <canvas id="mainCanvas" role="img" aria-label="Isometric drawing of the selected chiplet package"></canvas>
```

```text
   82        <div class="block legend" id="legend">
   83          <div class="lbl">Colour = one value per chiplet <span id="scaleUnit"></span></div>
   84          <div class="scalebar" id="scaleBarBox"><span class="bar" id="scaleBar"></span></div>
   85          <div class="ticks2" id="scaleTicks"></div>
   86          <p class="noscale" id="noScale" hidden>No per-chiplet temperatures in the verified data, so chiplets are not coloured. J is the measurement's value, not a chiplet's.</p>
   87          <p class="basis" id="basis">chiplet-centre temperatures from the solver; not a field</p>
   88          <p class="spannote" id="spanNote" title="Max − min of the chiplet extents in the run's verified layouts, in mm. Footprints are drawn to scale."></p>
   89          <p class="fixnote" id="fixNote" hidden>This replay is an interface fixture: the values are illustrative and no solver ran.</p>
   90          <ul class="keys">
   91            <li title="Not simulated, or no measurement yet"><i class="k-none"></i>no temperature</li>
   92            <li title="Its measurement was withdrawn or its support broke"><i class="k-stale"></i>stale value</li>
   93            <li title="Chiplets overlap in the proposed geometry"><i class="k-overlap"></i>geometry overlap</li>
   94            <li title="The board's accepted package"><i class="k-accept"></i>accepted (board)</li>
   95          </ul>
   96        </div>
   97        <div class="block drillbox" id="drillBox" hidden></div>
   98        <div class="block stack">
   99          <div class="lbl">Schematic stack</div>
  100          <p id="stackNote">Substrate, interposer, heights and lid are nominal drawing constants, not to scale. Chiplet footprints are from the evidence, in mm, to scale.</p>
  101        </div>
```

```text
  124  <dialog id="limits" aria-labelledby="limitsTitle">
  125    <header><h3 id="limitsTitle">Honest limits</h3><span class="spacer"></span><button type="button" class="btn" id="limitsClose">Close</button></header>
  126    <ul>
  127      <li>Everything drawn here comes from the unbroken, verified prefix of the chain, with the same check and pins as the Lab view. After the first break the drawing freezes; unverified or later envelopes never move or colour anything.</li>
  128      <li>Each chiplet's top face is one colour: its centre temperature, on one fixed scale for the run. It is not a thermal field, and nothing is interpolated across a die. Side faces are the same colour, shaded only for depth. A run whose data has no centre temperatures draws its chiplets uncoloured: J is its measurement's value and is never spread over the chiplets as if it were one of theirs.</li>
  129      <li>The stack is schematic. Substrate, interposer, die heights and the lid are drawing constants. Only the chiplet footprints come from the evidence.</li>
  130      <li>A glide is display only: chiplets move from the layout the package showed before (a lab's previous candidate, else the initial layout) to the new candidate. Status (proposed, accepted, stale) comes only from the evidence contract's project().</li>
  131      <li>A verified envelope proves the core's key signed it. It does not prove a temperature is physically right.</li>
  132      <li>The bundled demo is an interface fixture with illustrative numbers. No solver produced them.</li>
  133      <li>TEST KEYS mode uses keys anyone can derive, so only a local server honours it.</li>
  134    </ul>
  135  </dialog>
  136  
  137  <script type="module" src="package.js"></script>
```

### web/public/sentilab/package/package.js

blob `dc27ea5a88d84e967f8b43f31b32f27871aa59c8`

```text
    1  // SentiLab Package view: our own animated render of the chiplet package, driven by the verified evidence stream.
    2  // Data comes only through source.mjs (the same verifier and pins as the Lab view); the scene through scene.mjs
    3  // (pure, also used by the CLI); the drawing through render.mjs (hand-written Canvas 2D). Every string from an
    4  // envelope reaches the page through textContent, never innerHTML.
    5  import { DEMO, CONTRACT_VERSION, MAX_FILE_BYTES, setupTrust, fetchReplayBytes, verifyReplayFile, isDrill, chainSummary, modeNow, runStatusOf, createLiveFeed, reasonText } from "./source.mjs";
    6  import { viewHref } from "../view-links.mjs";
    7  import { shortId } from "../lab-model.mjs";
    8  import { sceneAt, scaleTicks, describeEvent, describeSource, refusalText, spanText, TRACK_ORDER, TRACKS, trackName } from "./scene.mjs";
    9  import { reconcile } from "./playhead.mjs";
   10  import { drawPackage, TrackAnimation, HOME_AZIMUTH, ORBIT_MS, easeInOut } from "./render.mjs";
   11  // Temperatures are labelled by the one rule (temperature-label.mjs) from the evaluator identity of the measurement each
   12  // came from, for replays and the live feed alike. The numbers stay as recorded; the page says so above the stage.
   13  import { needsNotice, NOTICE } from "../../temperature-label.mjs";
```

```text
   17  const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
   18  const STEP_MS = REDUCED ? 1300 : 800;
```

```text
   21  // ── tiny DOM helper: text only ────────────────────────────────────────────────────────────────────────────────
   22  // A `style` prop goes through the CSSOM (style.cssText), never a style="" attribute: the page's Content-Security-Policy
   23  // (style-src 'self') refuses inline style attributes, and allows the CSSOM.
   24  function h(tag, props, ...kids) {
   25    const node = document.createElement(tag);
   26    for (const [k, v] of Object.entries(props ?? {})) {
   27      if (v == null || v === false) continue;
   28      if (k === "class") node.className = v;
   29      else if (k === "style") node.style.cssText = String(v);
   30      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
   31      else node.setAttribute(k, v === true ? "" : String(v));
   32    }
   33    for (const kid of kids.flat(Infinity)) if (kid != null && kid !== false) node.append(kid instanceof Node ? kid : String(kid));
   34    return node;
   35  }
```

```text
  150  // ── the playhead ────────────────────────────────────────────────────────────────────────────────────────────
  151  function setCursor(n, { stepwise = false } = {}) {
  152    const src = active();
  153    const v = src?.verification;
  154    const prev = S.scene;
  155    S.cursor = Math.max(0, Math.min(n, v ? v.ordered.length : 0));
  156    if (!v || !src.frame) { applyScene(null); return; }
  157    // Rule 1: the drawing is the scene of the projectable prefix, as far as the playhead has reached. Envelopes after
  158    // the prefix move the playhead but never the package.
  159    const k = Math.min(S.cursor, v.prefixCount);
  160    const scene = sceneAt(v.prefixEnvelopes, k, src.frame);
  161    applyScene(scene, { animate: stepwise && prev !== null && scene.at.seq === prev.at.seq + 1 });
  162  }
```

```text
  235  // ── drawing ─────────────────────────────────────────────────────────────────────────────────────────────────
  236  let raf = 0;
  237  function requestDraw() { if (!raf) raf = requestAnimationFrame(drawAll); }
```

```text
  279    renderOffline();
  280    // Only the verified prefix is drawn: any withdrawn or unvalidated temperature in it shows the notice.
  281    const notice = Boolean(v) && needsNotice(v.prefixEnvelopes);
  282    $("wnotice").hidden = !notice;
  283    $("wnotice").textContent = notice ? NOTICE : "";
  284  }
```

```text
  616  if (!globalThis.crypto?.subtle) {
  617    // WebCrypto exists only in a secure context. Without it nothing can be verified, so nothing is drawn.
  618    $("frozen").hidden = false;
  619    $("frozen").textContent = "Signatures can't be checked here: this page needs a secure (https) connection. Nothing is drawn.";
  620    $("chainText").textContent = "cannot verify";
```

```text
  633  // A test hook for real-browser checks: read-only facts, no control over trust or data.
  634  Object.defineProperty(window, "__packageView", { value: Object.freeze({ facts: () => ({ cursor: S.cursor, seq: S.scene?.at.seq ?? 0, selected: S.selected, prefix: active()?.verification?.prefixCount ?? 0, total: total() }) }) });
```

### web/public/sentilab/package/scene.mjs

blob `7188a9c2c05dd322b1fb235be5237d60508434fc`

```text
    1  // SentiLab Package view: the scene model. Pure functions, no DOM, no clock, no randomness, so the same verified
    2  // prefix gives the same scene in node (scripts/sentilab-scene.mjs) and in the browser (package.js).
    3  //
    4  // Input is ONLY the projectable prefix (VIEW ENVELOPE rule 1): the unbroken run of verified, non-oversize envelopes
    5  // from seq 1, as the verifier returns it. Status (lifecycle, validity, support sets, acceptance) is never computed
    6  // here: it is read from the contract's project() over that prefix. Geometry, temperatures, J and W are the display-only
    7  // `values` of envelopes in the prefix that project() applied. Nothing after the prefix can move or colour anything.
    8  //
    9  // Everything drawn comes from our own data: chiplet footprints from values.geometry, colours from values.center_temps
   10  // on one fixed scale per run (a run without centre temperatures draws its chiplets uncoloured; J is the measurement's
   11  // value and never colours a chiplet), J and W from the measurement both views pick (lab-model.mjs metricFor, the
   12  // one rule). The vertical stack (substrate, interposer, die heights, lid) is schematic: nominal
   13  // constants below, declared as such in the scene and on screen.
   14  import { project } from "../evidence-projection.mjs";
   15  import { metricFor, tempUnit } from "../lab-model.mjs";
   16  
   17  export const SCENE_VERSION = "sentilab-scene/0.1";
   18  export const TEMP_BASIS = "chiplet-centre temperatures from the solver; not a field";
   19  
   20  // Schematic stack. These heights are drawing constants, not measurements and not to scale. Only the chiplet
   21  // footprints (x, y, w, h) come from the evidence. The interposer is the bounding extent of the run's geometry plus
   22  // a margin; the substrate is the interposer plus a margin.
   23  export const STACK = Object.freeze({
   24    label: "schematic stack",
   25    note: "Layer heights are nominal drawing constants, not from the run and not to scale. Chiplet footprints are from the evidence, to scale.",
   26    units: "mm",
   27    substrate_mm: 2.6,
   28    interposer_mm: 1.0,
   29    die_mm: 2.0,
   30    hbm_mm: 3.6,          // memory stacks drawn taller, by chiplet id prefix "HBM"
   31    lid_clearance_mm: 1.6,
   32    lid_mm: 0.6,
   33    interposer_margin_mm: 1.5,
   34    substrate_margin_mm: 4,
   35  });
```

```text
   52  // The heat ramp: the Lab view's stops, so both views colour a value the same way.
   53  export const HEAT_STOPS = Object.freeze(["#112a48", "#236b91", "#56b6ba", "#dfd376", "#ec994f", "#e45138"]);
```

```text
   78  // ── units and bounds ─────────────────────────────────────────────────────────────────────────────────────────
   79  // Every length is placed in mm and every temperature coloured in °C. Only the units below are converted; a missing
   80  // or unsupported unit is REFUSED: the value is never placed, coloured or exported as a number, and the scene lists
   81  // it in `errors` with the unit as declared. Centre temperatures carry no unit of their own, so they are read in the
   82  // unit of the same measurement's J (the only temperature unit an envelope declares). Producers spell Celsius "°C"
   83  // (older signed rows) or "C" (newer rows): both are °C (lab-model.mjs tempUnit, the Lab view's rule).
   84  export const SUPPORTED_UNITS = Object.freeze({
   85    length: Object.freeze({ canonical: "mm", accepted: Object.freeze(["mm", "m", "µm", "μm", "um"]), declared_in: "values.units" }),
   86    temperature: Object.freeze({ canonical: "°C", accepted: Object.freeze(["°C", "C", "K"]), declared_in: "values.J.unit (centre temperatures use their measurement's J unit)" }),
   87  });
   88  const LENGTH_TO_MM = Object.freeze({ mm: null, m: (v) => v * 1000, "µm": (v) => v / 1000, "μm": (v) => v / 1000, um: (v) => v / 1000 });
   89  const TEMP_TO_C = Object.freeze({ "°C": null, K: (v) => v - 273.15 });
   90  // Representable ranges, after conversion. A finite value outside them is an `out_of_range` scene error (distinct
   91  // from chain validity): it is never drawn, never widens the scale or footprint, and never reaches an export.
   92  export const BOUNDS = Object.freeze({
   93    temperature_c: Object.freeze({ min: -273.15, max: 2000 }),
   94    size_mm: Object.freeze({ above: 0, max: 1000 }),
   95    coordinate_mm: Object.freeze({ min: -1000, max: 1000 }),
   96    layer: Object.freeze({ min: 0, max: 16 }),
   97    W_abs_max: 1e12,
   98  });
```

```text
  210  // ── run frame: one colour scale and one footprint per run ────────────────────────────────────────────────────
  211  // The colour scale covers every chiplet-centre temperature in the run's prefix, rounded out to 5 degrees and at
  212  // least 10 degrees wide (the Lab view's rule). The footprint is the run's layout span (layoutSpan) plus margins.
  213  // A replay computes this once from the whole prefix, so neither changes while the playhead moves.
  214  export function runFrame(prefixEnvelopes, projection = null) {
  215    const prefix = contiguousPrefix(prefixEnvelopes);
  216    const proj = projection && prefix.length === (prefixEnvelopes?.length ?? 0) ? projection : project(prefix.map((env) => env.event));
  217    const applied = appliedEvents(prefix, proj);
  218    // Only accepted values count: normalised to °C and mm, inside the bounds. Refused values never move the frame.
  219    let lo = Infinity, hi = -Infinity;
  220    for (const env of measurementCreates(applied)) {
  221      const { temps } = readTemps(env.values);
  222      if (!temps) continue;
  223      for (const v of Object.values(temps)) { if (v < lo) lo = v; if (v > hi) hi = v; }
  224    }
  225    let scale = null;
  226    if (lo !== Infinity) {
  227      let min = Math.floor(lo / 5) * 5, max = Math.ceil(hi / 5) * 5;
  228      if (max - min < 10) { const mid = (min + max) / 2; min = Math.floor((mid - 5) / 5) * 5; max = min + 10; }
  229      scale = { min, max, unit: SUPPORTED_UNITS.temperature.canonical, fixed: true, basis: TEMP_BASIS };
  230    }
  231    const extent = layoutSpan(prefix, proj);
  232    let footprint = null;
  233    if (extent) {
  234      const { x0, y0, x1, y1 } = extent;
  235      const m = STACK.interposer_margin_mm, s = STACK.substrate_margin_mm;
  236      footprint = {
  237        extent: { x0, y0, x1, y1 },
  238        interposer: { x0: x0 - m, y0: y0 - m, x1: x1 + m, y1: y1 + m },
  239        substrate: { x0: x0 - m - s, y0: y0 - m - s, x1: x1 + m + s, y1: y1 + m + s },
  240        rule: `interposer = bounding extent of the run's geometry + ${m} mm; substrate = interposer + ${s} mm`,
  241      };
  242    }
  243    return { scale, footprint };
  244  }
```

```text
  264  // Colour for a centre temperature on the run's fixed scale. Values outside the scale clamp to its ends.
  265  export function heatColor(t, scale) {
  266    if (!finite(t) || !scale) return null;
  267    const stops = HEAT_STOPS.map((h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)));
  268    const f0 = Math.max(0, Math.min(1, (t - scale.min) / ((scale.max - scale.min) || 1))) * (stops.length - 1);
  269    const i = Math.min(stops.length - 2, Math.floor(f0)), f = f0 - i, a = stops[i], b = stops[i + 1];
  270    return `#${[0, 1, 2].map((k) => Math.round(a[k] + (b[k] - a[k]) * f).toString(16).padStart(2, "0")).join("")}`;
  271  }
```

```text
  534  // The scene after the first `count` envelopes of the prefix, on the run's fixed frame. The page calls this as the
  535  // playhead moves; the CLI's --at uses it too.
  536  export function sceneAt(prefixEnvelopes, count, frame) {
  537    const prefix = contiguousPrefix(prefixEnvelopes);
  538    const slice = prefix.slice(0, Math.max(0, Math.min(prefix.length, count)));
  539    return buildScene(slice, project(slice.map((env) => env.event)), { frame: frame ?? runFrame(prefix) });
  540  }
```

### web/public/sentilab/package/render.mjs

blob `91d204e1cf4494c2da30ec38dfb63f3b868b36db`

```text
    1  // SentiLab Package view: Canvas 2D isometric renderer. Hand-written for this page: no libraries, no models, no
    2  // textures, no third-party assets. Every shape is drawn from the scene (scene.mjs): footprints from the evidence's
    3  // geometry, top-face colours from chiplet-centre temperatures on the run's fixed scale, and a schematic stack.
    4  //
    5  // Honesty rules held here:
    6  //   - a chiplet's top face is ONE flat colour (its centre value); there is no gradient across a die;
    7  //   - side faces are the same colour, flat-shaded for depth only;
    8  //   - stale values are drawn desaturated and tagged "stale";
    9  //   - the stack (substrate, interposer, heights, lid) is schematic and labelled so on the main canvas.
   10  import { STACK } from "./scene.mjs";
```

### web/public/sentilab/package/playhead.mjs

blob `50b3492eb0f2b7787da3d6c64bd0718e245cef8b`

```text
    1  // SentiLab Package view: the playhead rule for a verification change. Pure (no DOM, no clock), so the node tests
    2  // run exactly what the page runs.
    3  //
    4  // A verification can change at any time: a live poll adds envelopes, a late conflicting or tampered envelope
    5  // shrinks the projectable prefix K, or a new replay is opened. On EVERY change, paused or playing, the page calls
    6  // reconcile() and adopts its result:
    7  //   - the playhead is clamped to K (following the live edge means sitting at K);
    8  //   - the scene is rebuilt from the new prefix, at the clamped playhead;
    9  //   - the frame (colour-scale extrema and footprint) is kept and widened only if the new prefix EXTENDS the old one
   10  //     (the same envelopes, by stored hash, at every old seq). Otherwise it is recomputed from the new prefix alone,
   11  //     so a value that left the prefix can't keep stretching the scale;
   12  //   - `reset` tells the page to cut every animation (glides, ghosts, pulses) to the new scene: nothing in flight
   13  //     from the old prefix may finish drawing.
```

```text
   27  // A growing live run keeps its scale and footprint from shifting: they only widen. Only valid while the prefix grows.
   28  export function widenFrame(old, fresh) {
   29    if (!old) return fresh;
   30    const scale = old.scale && fresh.scale ? { ...fresh.scale, min: Math.min(old.scale.min, fresh.scale.min), max: Math.max(old.scale.max, fresh.scale.max) } : fresh.scale ?? old.scale;
   31    const footprint = old.footprint && fresh.footprint ? {
   32      ...fresh.footprint,
   33      extent: unionRect(old.footprint.extent, fresh.footprint.extent),
   34      interposer: unionRect(old.footprint.interposer, fresh.footprint.interposer),
   35      substrate: unionRect(old.footprint.substrate, fresh.footprint.substrate),
   36    } : fresh.footprint ?? old.footprint;
   37    return { scale, footprint };
   38  }
```

```text
   40  // view: what the page showed before { prefix (the old prefix envelopes), frame, cursor, following }.
   41  // verification: the adapter's result (source.mjs verifyRun): prefixEnvelopes, prefixCount, projection.
   42  // Returns { prefix, frame, cursor, scene, reset, grew, stepped }.
   43  export function reconcile(view, verification, { widen = true } = {}) {
   44    const prefix = verification?.prefixEnvelopes ?? [];
   45    const K = verification?.prefixCount ?? 0;
   46    const before = view?.prefix ?? [];
   47    const grew = before.length > 0 && extendsPrefix(before, prefix);
   48    const fresh = runFrame(prefix, verification?.projection ?? null);
   49    const frame = grew && widen && view?.frame ? widenFrame(view.frame, fresh) : fresh;
   50    const oldCursor = Number.isSafeInteger(view?.cursor) ? Math.max(0, view.cursor) : 0;
   51    const cursor = view?.following ? K : Math.min(oldCursor, K);
   52    const scene = sceneAt(prefix, cursor, frame);
   53    // Animate only the ordinary live case: the prefix grew by exactly the one envelope the followed playhead moved to.
   54    const stepped = grew && Boolean(view?.following) && cursor === oldCursor + 1;
   55    return { prefix, frame, cursor, scene, grew, stepped, reset: !stepped };
   56  }
```

### web/public/sentilab/package/source.mjs

blob `ad3154c52d4a9007592a272698fcaf7c061b2c31`

```text
    1  // SentiLab Package view: the ONE place this page gets verified data. It uses the shared view code, exactly as the
    2  // Lab view (lab.js) does, and hands package.js a small, version-neutral result:
    3  //   - replay files: paging.mjs verifyReplayBytes() (VIEW ENVELOPE v0.6 bytes-to-rows, then the v0.5 browser core:
    4  //     input checks before any hashing, duplicates and conflicts, the projectable prefix);
    5  //   - live: the v0.6 cursor reducer from paging.mjs (initialState / request / step, cursor + cursor_hash, the 409, 413
    6  //     and paging-unsupported terminal states), verifyRows() over every row held, and the v0.6.2 label from track() and
    7  //     liveLabel(): "LIVE · progress N s ago", "ENDED · run finished", "STALE · chain broken", "STALE · <reason>".
    8  //     Catching up is not progress, and a run /api/view/runs lists as finished shows ENDED. There is no seq paging.
    9  // The trust rules are the Lab view's, unchanged:
   10  //   - pins come only from view-pins.js (the deployed page), never from a replay file, its manifest or the API;
   11  //   - ?pins=test (keys anyone can derive) is honoured only on a local server, exactly as lab.js does;
   12  //   - only the projectable prefix (verified, in-run, unbroken from seq 1, before any conflict) is handed on for drawing.
```

```text
   19  export const CONTRACT_VERSION = `${VERSION} (live paging: view-envelope/0.6.2)`;
```

```text
   27  const MAX_PAGES_PER_POLL = 16;                  // as the reference client loop and lab.js
   28  export const LIVE_POLL_MS = 1000;
   29  export const LIVE_BACKOFF_MS = 5000;
```

```text
  167  // The label (v0.6.2), from paging.mjs liveLabel(). A finished run: ENDED · run finished, unless the board is frozen
  168  // (STALE · chain broken) or a terminal reason holds. A running run: a failed latest poll shows its reason; a frozen
  169  // board (anything after the prefix, including K cut back below its high) is "STALE · chain broken" at once; otherwise
  170  // LIVE · progress N s ago when K grew after catch-up within 60 s and a poll succeeded within 5 s, else STALE.
  171  // runStatus: the run's status from /api/view/runs (runStatusOf); anything but "finished" counts as running.
  172  export function liveModeOf(live, nowMs, runStatus = "running") {
  173    const label = liveLabel(live.paging, nowMs, live.verification?.prefixEnd ?? 0, live.verification?.frozen ?? false, runStatus);
  174    const mode = label.startsWith("LIVE") ? "LIVE" : label.startsWith("ENDED") ? "ENDED" : "STALE";
  175    const reason = mode !== "LIVE" && label.includes(" · ") ? label.slice(label.indexOf(" · ") + 3) : null;
  176    return { mode, reason, label };
  177  }
  178  // { mode, reason, label } for the header. A replay file is always REPLAY; live before any run is STALE.
  179  export function modeNow(kind, live, nowMs, runStatus = "running") {
  180    if (kind === "file") return { mode: "REPLAY", reason: null, label: "REPLAY" };
  181    return live ? liveModeOf(live, nowMs, runStatus) : { mode: "STALE", reason: null, label: "STALE" };
  182  }
  183  // The selected run's status as /api/view/runs lists it: "finished" or, for anything else or no entry, "running".
  184  export function runStatusOf(feedState) {
  185    const status = (feedState?.runs ?? []).find((run) => run.run_id === feedState.runId)?.status;
  186    return status === "finished" ? "finished" : "running";
  187  }
  188  export { REASON_TEXT };
```

```text
  190  // The browser poller: GET /api/view/runs, then GET /api/view/events?run_id=&cursor=&limit=[&cursor_hash=], draining up
  191  // to 16 pages a poll while x-has-more is true, then every 1 s from the last cursor. Terminal states stop it for good;
  192  // only a reload (a new feed) starts over from cursor 0. onChange() is called after every poll.
  193  // fetchImpl and now are injectable so the tests drive this exact poller; the page uses fetch and Date.now.
  194  async function fetchPage(fetchImpl, runId, req) {
  195    const query = new URLSearchParams({ run_id: runId, cursor: String(req.cursor), limit: String(req.limit) });
  196    if (req.cursor_hash !== undefined) query.set("cursor_hash", req.cursor_hash);
  197    let r;
  198    try { r = await fetchImpl(`/api/view/events?${query}`, { cache: "no-store" }); } catch { return null; }   // transport
  199    if (r.status !== 200) { r.body?.cancel().catch(() => {}); return { status: r.status, headers: r.headers, bodyBytes: new Uint8Array(0) }; }
  200    // Raw bytes, never decoded whole; reading stops past 4 MiB, and a body that isn't read whole fails as transport.
  201    const body = await readBodyCapped(r, MAX_API_BYTES, "response_too_large").catch(() => ({ ok: false }));
  202    return { status: 200, headers: r.headers, bodyBytes: body.ok ? body.bytes : null };
  203  }
  204  
  205  export function createLiveFeed({ trust, runId = null, onChange = () => {}, fetchImpl = (...args) => fetch(...args), now = () => Date.now() }) {
```

```text
  244      return live.paging.degraded ? null : outcome !== "ok" ? LIVE_BACKOFF_MS : live.paging.has_more ? 0 : LIVE_POLL_MS;
  245    }
  246    async function poll() {
  247      if (stopped) return;
  248      if (typeof document !== "undefined" && document.hidden) return schedule(LIVE_BACKOFF_MS);
  249      schedule(await pollOnce());
  250    }
  251    return {
  252      state,
  253      pollOnce,
  254      start() { if (!stopped) return; stopped = false; poll(); },
  255      stop() { stopped = true; clearTimeout(timer); },
  256      poke() { if (!stopped) { clearTimeout(timer); poll(); } },
  257    };
  258  }
```

### web/public/temperature-label.mjs

blob `9f1986bb5d07461947650110ee81041ad15d8e0e`

```text
    1  // The one label rule for every temperature on these pages: the run view (app.js), the Lab view (sentilab/lab.js) and
    2  // the Package view (sentilab/package/package.js). Pure, no DOM, so the node tests run it (web/test/temperature-label.test.mjs).
    3  //
    4  // A temperature is labelled by the evaluator identity it came from:
    5  //   - the run view: the result's thermal.solver_version;
    6  //   - the Lab and Package views: the measurement's semantics.evaluator_version (the producer copies solver_version in).
    7  // Replays, the live feed and the API all reach the pages as these same fields, so one rule covers them all.
    8  // An identity names its engine and upstream commit first ("HotSpot-7:<commit>"), then the build, config and grid
    9  // (":binary_sha256:…:config_sha256:…:grid:16x16"; older rows ":sha256:<16 hex>"). A variant extends the commit field
   10  // ("HotSpot-7:<commit>+SLAB-049:…") and is a different evaluator, as is "HotSpot-6.0:…".
   11  //
   12  //   withdrawn     the identity's engine:commit is on WITHDRAWN: the known affected build;
   13  //   illustrative  exactly the bundled interface fixture's identity: illustrative numbers, no solver ran;
   14  //   accepted      exactly an identity on ACCEPTED (there are none yet);
   15  //   unvalidated   anything else: any other identity, and a missing or unreadable one (unvalidated provenance). A
   16  //                 different identity never implies validation.
   17  // A value derived from several (a difference, a gap, a range, an axis) takes the most cautious state among its inputs:
   18  // withdrawn, then unvalidated, then illustrative. It is illustrative only if every input is, accepted only if every
   19  // input is; any other mix, or no input at all, is unvalidated. Withdrawn and unvalidated values show the page notice.
   20  
   21  // WITHDRAWN: the known affected build, HotSpot 7.0 at upstream f18831e, in every build, config and grid. It is under
   22  // review for heat-sink coupling; see the SLAB-049 review.
   23  export const WITHDRAWN = Object.freeze(["HotSpot-7:f18831e48cef5d62580585cca0d7fab6c71bc3cc"]);
   24  // ILLUSTRATIVE: the bundled demo replay (sentilab/demo-run.jsonl) is an interface fixture; no solver produced it.
   25  export const ILLUSTRATIVE = Object.freeze(["fixture-no-solver"]);
   26  // ACCEPTED: evaluator identities accepted for comparison. Each entry needs an exact evaluator acceptance, recorded for
   27  // that exact identity string (engine, commit, build, config and grid); it is matched exactly. None yet.
   28  export const ACCEPTED = Object.freeze([]);
   29  
   30  // The page notice, shown at the top of any page that shows a withdrawn or unvalidated temperature. One constant:
   31  // reword it here only.
   32  export const NOTICE = "These simulated temperatures are under review and have been withdrawn from comparison with published " +
   33    "layouts. We are investigating heat-sink coupling and validating the evaluator against reconstructed research layouts. " +
   34    "Historical results remain available.";
   35  
   36  // text: the qualifier; short: the tag beside a value (not "withdrawn" alone, which the evidence views already use for a
   37  // withdrawn node); title: the full sentence, on hover; notice: whether the value shows the page notice.
   38  export const LABELS = Object.freeze({
   39    withdrawn: Object.freeze({
   40      state: "withdrawn", notice: true, text: "simulated · pre-correction (withdrawn)", short: "pre-correction",
   41      title: "Withdrawn: this evaluator build is under review for heat-sink coupling. Not for comparison with published layouts; " +
   42        "kept as recorded.",
   43    }),
   44    unvalidated: Object.freeze({
   45      state: "unvalidated", notice: true, text: "simulated · unvalidated", short: "unvalidated",
   46      title: "Unvalidated: this value's evaluator has not been accepted, or isn't named. Not for comparison with published layouts.",
   47    }),
   48    illustrative: Object.freeze({
   49      state: "illustrative", notice: false, text: "illustrative · no solver ran", short: "illustrative",
   50      title: "Interface fixture: an illustrative number. No solver produced it.",
   51    }),
   52    accepted: Object.freeze({ state: "accepted", notice: false, text: "simulated", short: "simulated", title: "Simulated with an accepted evaluator. Not silicon." }),
   53  });
```

```text
   55  const isObj = (x) => x !== null && typeof x === "object" && !Array.isArray(x);
   56  // The leading engine:commit of an identity, compared without case.
   57  const evaluatorKey = (identity) => identity.trim().split(":", 2).join(":").toLowerCase();
   58  
   59  // The rule over given lists (the tests build their own; the pages use the frozen lists above).
   60  export function labeller({ withdrawn = WITHDRAWN, illustrative = ILLUSTRATIVE, accepted = ACCEPTED } = {}) {
   61    const withdrawnKeys = new Set(withdrawn.map((id) => id.toLowerCase()));
   62    const illustrativeIds = new Set(illustrative), acceptedIds = new Set(accepted);
   63    // One value, from one identity.
   64    const labelFor = (identity) => {
   65      if (typeof identity !== "string" || identity.trim() === "") return LABELS.unvalidated;   // unvalidated provenance
   66      if (withdrawnKeys.has(evaluatorKey(identity))) return LABELS.withdrawn;                   // every build of it
   67      if (illustrativeIds.has(identity)) return LABELS.illustrative;                            // exactly the fixture
   68      if (acceptedIds.has(identity)) return LABELS.accepted;                                    // exactly as accepted
   69      return LABELS.unvalidated;
   70    };
   71    // A value derived from several: the identities of everything it was made from.
   72    const labelForAll = (identities) => {
   73      const list = typeof identities === "string" ? [identities] : Array.isArray(identities) ? identities
   74        : identities != null && typeof identities[Symbol.iterator] === "function" ? [...identities] : [];
   75      const labels = list.map(labelFor);
   76      if (labels.includes(LABELS.withdrawn)) return LABELS.withdrawn;
   77      if (labels.length > 0 && labels.every((label) => label === LABELS.illustrative)) return LABELS.illustrative;
   78      if (labels.length > 0 && labels.every((label) => label === LABELS.accepted)) return LABELS.accepted;
   79      return LABELS.unvalidated;                    // an unvalidated input, a mix of fixture and real inputs, or none
   80    };
   81    return Object.freeze({ labelFor, labelForAll });
   82  }
   83  const RULE = labeller();
   84  export const labelFor = RULE.labelFor;
   85  export const labelForAll = RULE.labelForAll;
```

```text
  121  // ── view envelopes (Lab and Package views) ──────────────────────────────────────────────────────────────────
  122  // node id -> evaluator identity, from the first node.create of each id (project() rejects a repeat). Only measurements
  123  // and comparisons declare semantics, so a candidate maps to undefined.
  124  export function evaluatorIds(envelopes) {
  125    const ids = new Map();
  126    for (const env of Array.isArray(envelopes) ? envelopes : []) {
  127      const body = isObj(env) && isObj(env.event) && env.event.type === "node.create" && isObj(env.event.body) ? env.event.body : null;
  128      if (!body || typeof body.id !== "string" || ids.has(body.id)) continue;
  129      ids.set(body.id, isObj(body.semantics) ? body.semantics.evaluator_version : undefined);
  130    }
  131    return ids;
  132  }
  133  // The identity behind one envelope's display values: a node.create's own semantics, or for any other event the node it
  134  // names (a verify.add's values belong to the measurement it verifies). Anything else has none.
  135  export function envelopeEvaluator(env, ids) {
  136    if (!isObj(env) || !isObj(env.event) || !isObj(env.event.body)) return undefined;
  137    const body = env.event.body;
  138    if (env.event.type === "node.create") return isObj(body.semantics) ? body.semantics.evaluator_version : undefined;
  139    return typeof body.node === "string" && ids instanceof Map ? ids.get(body.node) : undefined;
  140  }
  141  // Does an envelope carry a temperature for display (a J, or centre temperatures)?
  142  export const hasTemperature = (env) => isObj(env) && isObj(env.values) && (isObj(env.values.J) || isObj(env.values.center_temps));
  143  // The page notice's test for envelopes: does any of them carry a temperature whose label shows the notice (withdrawn or
  144  // unvalidated)? Envelopes that failed verification count too: the feed lists them.
  145  export function needsNotice(envelopes) {
  146    const list = (Array.isArray(envelopes) ? envelopes : []).filter(Boolean);
  147    const ids = evaluatorIds(list);
  148    return list.some((env) => hasTemperature(env) && labelFor(envelopeEvaluator(env, ids)).notice);
  149  }
```

### web/test/temperature-label.test.mjs

blob `7ff5b2d704714778b19a1c4052277d2a2d79a667`

```text
  320  test("every page that shows these temperatures takes its notice and labels from this one module", () => {
  321    const page = (rel) => readFileSync(join(PUBLIC, rel), "utf8");
  322    const imports = (rel, from) => assert.match(page(rel), new RegExp(`import \\{[^}]*\\bNOTICE\\b[^}]*\\} from "${from.replace(/[.]/g, "\\.")}";`), rel);
  323    imports("app.js", "./temperature-label.mjs");
  324    imports("sentilab/lab.js", "../temperature-label.mjs");
  325    imports("sentilab/package/package.js", "../../temperature-label.mjs");
  326    imports("leaderboard.js", "./temperature-label.mjs");
  327    imports("verify.js", "./temperature-label.mjs");
  328    for (const rel of ["app.js", "sentilab/lab.js", "sentilab/package/package.js", "leaderboard.js", "verify.js"]) {
  329      assert.doesNotMatch(page(rel), /under review|heat-sink coupling/, `${rel} holds no copy of the notice text`);
  330    }
  331    for (const rel of ["index.html", "sentilab/index.html", "sentilab/package/index.html", "leaderboard.html", "verify.html"]) {
  332      assert.match(page(rel), /<p class="wnotice" id="wnotice" role="note" hidden><\/p>/, `${rel} has the notice slot`);
  333    }
  334    assert.match(page("index.html"), /<script type="module" src="app\.js"><\/script>/, "app.js loads as a module");
  335    assert.match(page("leaderboard.html"), /<script type="module" src="leaderboard\.js"><\/script>/, "leaderboard.js loads as a module");
  336    assert.match(page("verify.html"), /<script type="module" src="verify\.js"><\/script>/);
  337  });
```

### web/public/sentilab/view-core.mjs

blob `21f1189cef652b6ad54bcaf2cf2d3fd8e31b9071`

```text
   13  export const VERSION = "view-envelope/0.5";
   14  export const ALG = "ed25519";
   15  const KIB = 1024;
   16  export const MAX_LINE_BYTES = 64 * KIB;
   17  export const MAX_API_LINES = 256;
   18  export const MAX_API_BYTES = 4 * KIB * KIB;
   19  export const MAX_FILE_BYTES = 64 * KIB * KIB;
   20  const MAX_CANONICAL_BYTES = 64 * KIB;
   21  const MAX_DEPTH = 8;
   22  const MAX_STRING = 512;
   23  const MAX_ENTRIES = 64;
   24  const POLL_OK_MS = 5_000;
   25  const PROGRESS_MS = 60_000;
   26  const CAPPED_FIELDS = ["geometry", "center_temps", "artifact_hashes"];
   27  const HEX64 = /^[0-9a-f]{64}$/;
   28  const HEX128 = /^[0-9a-f]{128}$/;
```

```text
  105  
  106  // Browser transport (not in the reference): read a fetch Response body as raw bytes, but stop once it passes maxBytes,
  107  // so an oversize response is never fully read, split or parsed. Returns { ok: true, bytes } or { ok: false, reason }.
  108  export async function readBodyCapped(response, maxBytes, reason) {
  109    if (!response.body) {
  110      const bytes = new Uint8Array(await response.arrayBuffer());
  111      return bytes.length > maxBytes ? { ok: false, reason } : { ok: true, bytes };
  112    }
  113    const reader = response.body.getReader();
  114    const chunks = [];
  115    let size = 0;
  116    for (;;) {
  117      const { done, value } = await reader.read();
  118      if (done) break;
  119      size += value.byteLength;
  120      if (size > maxBytes) {
  121        reader.cancel().catch(() => {});
  122        return { ok: false, reason };
  123      }
  124      chunks.push(value);
  125    }
  126    const all = new Uint8Array(size);
  127    let at = 0;
  128    for (const chunk of chunks) { all.set(chunk, at); at += chunk.byteLength; }
  129    return { ok: true, bytes: all };
  130  }
```

### web/public/sentilab/paging.mjs

blob `af25c841fd5b9f6cfc673b56e6245330826605f9`

```text
  214  export function liveLabel(state, nowMs, K, frozen, runStatus = "running") {
  215    if (runStatus === "finished") {
  216      if (state.degraded) return `STALE · ${REASON_TEXT[state.degraded]}`;
  217      return K < state.high_k || frozen ? "STALE · chain broken" : "ENDED · run finished";
  218    }
  219    if (state.failure) return `STALE · ${REASON_TEXT[state.failure]}`;
  220    if (K < state.high_k) return "STALE · chain broken";
  221    if (frozen) return "STALE · chain broken";
  222    return modeLabel("api", state.last_ok_ms, state.last_progress_ms, nowMs);
  223  }
```

### web/public/sentilab/lab.js

blob `2832bfa8024966f5c211bb4ac30580dfffc61a80`

```text
  487  function renderLegend(scale, anyGeometry, span) {
  488    const lg = $("legend");
  489    $("p1note").textContent = scale ? "chiplet-center temperatures, not a field" : "layouts only: no temperatures drawn";
  490    if (anyGeometry) {
  491      lg.append(h("span", { class: "dims", title: "Max − min of the chiplet extents in the run's verified layouts, in mm (the Package view's figure). Every card is drawn on one frame from 0, lower-left origin." },
  492        span ?? "layout units missing or not supported: no span"));
  493    }
  494    if (!scale) {
  495      const what = "No per-chiplet temperatures in the verified data: chiplets are uncolored; J is the measurement's, not a chiplet's.";
  496      lg.append(h("span", { class: "what", title: what }, what));
  497      return;
  498    }
  499    const unit = scale.unit || "";
  500    lg.append(h("span", { class: "end" }, `${scale.min} ${unit}`), h("span", { class: "bar" }), h("span", { class: "end" }, `${scale.max} ${unit}`),
  501      h("span", { class: "what" }, S.source === "file" ? "one fixed scale for this run · center value per chiplet" : "one scale for this run, widens only if a value falls outside"));
```

### web/public/leaderboard.js

blob `342978f61d344a65e47bf43820b659ca3a256d91`

```text
    1  // A module: the page notice comes from the one rule (temperature-label.mjs). leaderboard.json names no evaluator for its
    2  // temperatures, so they are unvalidated (the rule's fail safe) and the notice shows while any are on the page.
    3  import { labelForAll, NOTICE } from "./temperature-label.mjs";
    4  
    5  const $ = (id) => document.getElementById(id);
    6  const setNotice = (on) => { $("wnotice").hidden = !on; $("wnotice").textContent = on ? NOTICE : ""; };
```

```text
   92    setNotice(labelForAll([]).notice);   // the batch's temperatures, with no evaluator named for them
```

### web/public/verify-core.js

blob `57efe13ee1764230ff620aa0ceb800e3dfa482a6`

```text
    1  // Offline flight-record verifier: the same checks as controller.FlightRecord.verify, in the browser.
    2  // It hashes each entry with Python's canonical JSON, json.dumps(sort_keys=True, separators=(",", ":"),
    3  // ensure_ascii=True), and checks every Ed25519 signature with WebCrypto. Nothing is sent anywhere.
    4  //
    5  // JSON.parse would turn 93.0 into 93 and change the hash, so parseRaw keeps every number's exact source
    6  // text. The server writes JSON with Python, so that text is already Python's repr of the value.
    7  
    8  import servicePins from "./trust-pins.json" with { type: "json" };
```

### web/test/public-names.test.mjs

blob `be64b1f087c775352e9dabb5fac70f9a7ac18a44`

```text
    1  // node --test web/test/public-names.test.mjs
    2  // Public naming rule for everything the site serves from web/public: no vendor, product or model names, and no internal
    3  // agent handles, in the pages, their scripts and styles, or the data they render. licenses.html and licenses/ are
    4  // excluded: third-party license texts must name their authors. Matching is case-insensitive and word-bounded.
```

```text
   20  export const NAMES = [
   21    // vendors, products and models
   22    "typesafe", "jev", "system\\s*one", "cloudflare", "openai", "chatgpt", "gpt", "claude", "anthropic", "grok", "kimi", "gemini",
   23    "deepseek", "qwen", "llama", "mistral", "microduck", "pollen",
   24    // internal agent handles
   25    "warden", "astra", "forge", "pocket-forge", "claude-warden", "gpt-astra", "aneta", "codex", "nightshift", "fable",
   26  ].map((n) => new RegExp(`(?<![\\w-])${n}(?![\\w])`, "i"));
```

```text
   70      for (const entry of readdirSync(dir, { withFileTypes: true })) {
   71        const full = join(dir, entry.name);
   72        const rel = relative(PUBLIC, full).split(sep).join("/");
   73        if (rel === "licenses.html" || rel === "licenses" || rel.startsWith("licenses/")) continue;
   74        if (entry.isDirectory()) walk(full); else out.push(rel);
   75      }
   76    };
   77    walk(PUBLIC);
   78    return out.sort();
   79  }
```

### web/test/control-bytes.test.mjs

blob `f446d12f8db628a618869a37e757a6d55b00628e`

```text
    1  // node --test web/test/control-bytes.test.mjs
    2  // No file under web/public or web/test holds a raw control byte below 0x20 other than tab, LF and CR. Such a byte is
    3  // invisible in review and silently changes what the code does: a regex's word boundary that became a raw backspace
    4  // (0x08) matched nothing, and the guard it belonged to was off without failing. Known binary formats are skipped.
```

```text
   12  const ALLOWED = new Set([0x09, 0x0a, 0x0d]);   // tab, LF, CR
   13  const BINARY = new Set([".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".woff", ".woff2", ".ttf", ".otf", ".wasm", ".zip", ".gz", ".pdf"]);
```

### web/public/licenses.html

blob `a3113c3000a465436e91de8451ee13c2c391a2a6`

```text
   14  
   15    <h2>Third-party components</h2>
   16    <div class="wrap"><table>
   17      <tr><th>Component</th><th>Upstream</th><th>Commit</th><th>License (full text)</th></tr>
   18      <tr><td>HotSpot thermal simulator</td><td><a href="https://github.com/uvahotspot/HotSpot">uvahotspot/HotSpot</a></td>
   19        <td class="mono">f18831e48cef</td><td><a href="/licenses/HotSpot-LICENSE.txt">University of Virginia license</a></td></tr>
   20      <tr><td>TAP-2.5D chiplet placement</td><td><a href="https://github.com/bu-icsg/TAP-2.5D">bu-icsg/TAP-2.5D</a></td>
   21        <td class="mono">3a3f4e5a4d01</td><td><a href="/licenses/TAP-2.5D-LICENSE.txt">Apache License 2.0</a></td></tr>
   22      <tr><td>SuperLU (linked by the HotSpot build in the API image)</td><td>Debian libsuperlu7 7.0.1</td>
   23        <td class="mono">-</td><td>BSD-style (LBNL); the full notice ships in the image at <span class="mono">/licenses/SuperLU-copyright</span></td></tr>
   24    </table></div>
   25  
   26    <h2>What we do to honor them</h2>
   27    <ul>
   28      <li>HotSpot's copyright line and license paragraphs travel with every copy, source or binary.</li>
   29      <li>The Apache-2.0 license travels with every copy of TAP-2.5D. Upstream has no NOTICE file. Any TAP file we modify carries a change notice at its top.</li>
   30      <li>SuperLU's notice is reproduced inside the binary distribution (the container image).</li>
   31      <li>No GPL code enters this project.</li>
```

### contracts/view-envelope-v0.5/VIEW-ENVELOPE.md

blob `37525f8ebbcc584350139e575c8438ccbe87070c`

```text
   23  `values` appears only on `node.create` of a candidate or measurement, and on `verify.add`:
   24  `geometry [{id, xLL, yLL, w, h, layer}]`, `units`, `scenario_id`, `J` (with unit), `W` (with metric_id),
   25  `center_temps {chiplet_id: value}`, `artifact_hashes [...]`.
```

```text
   43    1. **Raw size, before parsing.**
   44       - Both sources are JSONL, one envelope per line.
   45       - A line is at most 64 KiB of raw bytes. A padded line can't shrink past this check.
   46       - A trailing newline doesn't count as a line. A blank line in the middle is a `malformed` row.
   47       - An API response is at most 256 lines and 4 MiB raw (caps are inclusive). A larger one is a transport error: the response is dropped, the prefix is unchanged, and the poll counts as failed.
   48       - A replay file is at most 64 MiB raw.
   49    2. **Parse** one line as JSON.
   50    3. **Structure,** checked iteratively (an explicit stack, no recursion):
   51       - At most 8 levels of nesting: the envelope is level 1, and only objects and arrays count.
   52       - Every string and object key is well-formed UTF-16, with no lone surrogates, and has at most 512 code points.
   53       - Every number is finite.
   54       - At most 64 entries each in `geometry`, `center_temps` and `artifact_hashes`.
   55       - The schema holds. Extra top-level fields are allowed, and they are hashed. `v` is a string; `event` is an object with `event_id` (string), `seq` (integer, at least 1), `type` (string), `actor_role` (string) and `body` (object); `ts` is a string; `actor` is an object; `run` is an object with `run_id` (string); `prev_hash` and `hash` are 64 lowercase hex; `sig` is an object with `key_id` (string), `alg` equal to "ed25519" and `value` (128 lowercase hex); `values` is optional and, if present, an object.
   56    4. **Canonical size:** the byte length of `canonical(envelope)`, counted iteratively without serializing, is at most 64 KiB. It covers the whole envelope, including `sig` and `hash`.
```

```text
   73  ## Rules
   74  
   75  1. The view never stores or computes status itself. It runs aneta's `project()` only over the projectable prefix, so the view's status is the contract's status on an unbroken, authenticated history (aneta's trust boundary).
   76     - The projectable prefix is the longest run of envelopes from `seq` 1 in which every envelope passes the input checks, is verified and is in the requested run, with `seq` exactly one more than the last and `prev_hash` exact (genesis first). It also ends before the earliest conflict (see Duplicates and conflicts).
   77     - Let K be the last `seq` of the prefix (0 if none). The board, lifecycle, validity and evidence panel show exactly `project()` over seq 1..K. When anything follows the prefix, the view labels it "chain broken after seq K; board frozen at seq K".
   78     - Every envelope after the prefix is shown, marked in the feed and inspector, and never projected, even if it verifies on its own. Skipping a dropped event could show a state that never existed.
   79     - A projection error shows as an error state, never a blank page.
   80  2. Order is `seq`. `ts` is for display and is never used to order.
   81  3. `values` are display only. AcceptanceGate never reads them from an envelope; it reads the core's records.
   82  4. One input type for both modes. Live is `GET /api/view/events?run_id=<id>&after=<seq>`, polled every 1 s (SSE later). It returns JSONL, one envelope per line, for that run only, within the raw caps above. Replay is a JSONL file of the same envelopes for one run. `GET /api/view/runs` lists the runs, with `run_id`, `arm`, `family`, `seed` and last `seq`. The view picks one, and that is the run it checks against.
   83  5. The mode label must be honest. It uses the client's own clock, never `ts`, and it describes recent progress, never completeness.
   84     - LIVE: the source is the API, the last poll succeeded within 5 s, and the projectable prefix K grew within the last 60 s (both limits inclusive).
   85     - "Grew" means K rose above the highest value it has reached so far.
   86     - Arrivals that don't grow K never refresh it: duplicates, unverified envelopes, and envelopes after a break or conflict.
   87     - The LIVE label shows how long ago K last grew, e.g. "LIVE · progress 12 s ago".
   88     - STALE: the source is the API and LIVE doesn't hold, including before the first envelope.
   89     - REPLAY: the source is a file.
   90     - Seeded drills also show "drill".
   91     - Known limit: a server can withhold any suffix, including a final withdrawal, while it keeps releasing earlier envelopes. LIVE stays on and the view can't tell. Only the full history, replayed later, shows the truth.
```

```text
   99  ## Routes (all under /api/, so the Worker needs no change)
  100  
  101  - `GET /api/health`
  102  - `GET /api/view/runs`
  103  - `GET /api/view/events?run_id=<id>&after=<seq>`
  104  - `GET /api/view/key`
  105  - `GET /api/replay/<bundle>.jsonl`
```

### contracts/view-envelope-v0.6.2/VIEW-ENVELOPE.md

blob `e385bac2b2a4db757a25470398dffe8413592fd2`

```text
   82  4. One input type for both modes. Replay is a JSONL file of envelopes for one run. `GET /api/view/runs` lists the runs, with `run_id`, `arm`, `family`, `seed`, last `seq` and `status` (`running` or `finished`). The view picks one, and that is the run it checks against.
   83     - **The run's log.** For each run the core keeps an append-only log of physical JSONL rows, in append order. Duplicates, rejected and conflicting rows are all rows. A row never changes and never disappears once served.
   84     - **Live paging.** `GET /api/view/events?run_id=<id>&cursor=<n>&limit=<m>`:
   85       - `n` is the number of rows the client has already received, starting at 0. `m` is between 1 and 256.
   86       - The server returns rows n to n+k-1 of the log as JSONL (0 ≤ k ≤ m), with headers `x-next-cursor: n+k` and `x-has-more: true|false`. The v0.5 response caps (256 lines, 4 MiB) apply.
   87       - A cursor beyond the end of the log is answered `409` with no rows.
   88       - **A row too big to page.** The server never answers `200` over the 4 MiB cap. The page holds as many whole rows, each with its LF, as fit within the cap, up to m. If the very first row at cursor n can't fit even alone (its bytes plus LF exceed 4 MiB), the answer is `413` with no rows and no cursor headers.
   89       - **Only complete rows are rows.** The log counts and serves only complete, LF-terminated rows, exactly as stored, including oversize, malformed and duplicate ones. A tail with no LF yet is neither served nor hashed until its LF is written. Nothing is replaced by a sentinel.
   90     - **The cursor hash** (proposed by the producer, #56186). It binds a cursor to the exact rows behind it, so a replaced log is caught even when it is the same length.
   91       - Every page carries `x-cursor-hash`: the lowercase hex SHA-256 over the raw bytes of rows 0 to `x-next-cursor`-1, each row followed by a single LF.
   92       - Every request with a cursor above 0 also sends `cursor_hash=<hash of rows 0..n-1>`. If the server's own first n rows hash differently, it answers `409`.
   93       - The client hashes the raw response bytes it received, not decoded text, so invalid UTF-8 can't change the hash.
   94     - **Bytes to rows** (pinned, because decoders differ: a default browser `TextDecoder` drops a leading BOM and node's doesn't, so the same row could verify differently):
   95       - Split the raw bytes on LF (0x0A) only. Each row is the bytes between separators. A trailing LF ends the last row and doesn't start a new one.
   96       - Decode each row on its own as strict UTF-8, keeping any BOM: in a browser, `new TextDecoder("utf-8", { fatal: true, ignoreBOM: true })`.
   97       - A row that isn't valid UTF-8 is a `malformed` row. A row that starts with a BOM is also `malformed`, because `JSON.parse` rejects it. Either way the page continues.
   98       - The same rule applies to replay files, except that a replay file's last line may lack its LF and still counts as a row.
   99     - **The client:**
  100       - It starts at cursor 0 and keeps fetching while `x-has-more` is true; it then polls every 1 s from its last cursor.
  101       - It keeps every raw row it has received and re-runs the full v0.5 verification over the combined rows whenever new rows arrive. So a late conflict at an old `seq` still freezes the board.
  102     - **A poll fails, keeping the prefix and making the label STALE with the reason, when:**
  103       - the transport fails or the caps are exceeded: "transport";
  104       - `x-next-cursor` is missing, isn't an integer, or isn't exactly n plus the number of rows returned: "paging error";
  105       - more rows than the requested `limit`: "paging error";
  106       - a non-empty page body that doesn't end with LF, which a conforming server never sends: "paging error";
  107       - `x-cursor-hash` is missing or doesn't equal the client's own hash of the rows it now holds: "paging error";
  108       - the server answers `409`: "stream replaced". The view never resets on its own. Only a manual reload restarts at cursor 0 and re-verifies everything from scratch.
  109     - **`413`** means the next row can never be paged. The view keeps its prefix, shows "STALE · row too large" and stops polling. It never retries the same cursor in a loop.
  110     - **Terminal states.** "row too large", "stream replaced" and "paging unsupported" all stop polling until a manual reload.
  111     - **No cursor support** (`400`, `404` or `501` on the cursor parameters): the view keeps its last verified prefix and shows "STALE · paging unsupported". It never goes LIVE in this state, and it never pages by `seq`, because that can't deliver a late conflict.
  112     - **The legacy `after=<seq>` parameter** may stay on the server for compatibility. It is not part of this contract, and the view doesn't use it.
  113  5. The mode label must be honest. It uses the client's own clock, never `ts`, and it describes recent progress, never completeness.
  114     - LIVE: the source is the API, the last poll succeeded within 5 s as a valid cursor page (rule 4), the projectable prefix K grew within the last 60 s (both limits inclusive), K is not below the highest value it has reached, and nothing follows the projectable prefix.
  115     - A late conflict or break can shrink K below that high, freezing the board at an earlier `seq`. When it does, LIVE ends at once and the label shows "STALE · chain broken", even if K grew moments before.
  116     - A refused row can also arrive after the prefix without shrinking K: unverified, malformed, oversize, conflicting, or after a gap. That too freezes the board ("chain broken after seq K"). LIVE ends at once and the label shows "STALE · chain broken", even though K never dropped.
  117     - The rule in one line: LIVE never shows while the board is frozen.
  118     - "Grew" means K rose above the highest value it has reached so far.
  119     - **Catching up is not progress.** Rows received before the client first reaches the end of the log (the first page answered `x-has-more: false`) never count as growth. The first load of a long log is history, not activity, so LIVE can only follow growth that arrives after that point.
  120     - **ENDED:** when `GET /api/view/runs` lists the run as `finished`, the label is "ENDED · run finished" instead of LIVE or STALE. The view still verifies and shows everything, but claims no activity.
  121     - Integrity problems always win over ENDED: a frozen board ("STALE · chain broken") and the terminal states ("stream replaced", "row too large", "paging unsupported") keep their labels.
  122     - Only a passing failure ("transport", "paging error") on a finished run stays ENDED, since nothing new is expected.
  123     - A missing or unknown run status counts as `running`.
  124     - Arrivals that don't grow K never refresh it: duplicates, unverified envelopes, and envelopes after a break or conflict.
  125     - The LIVE label shows how long ago K last grew, e.g. "LIVE · progress 12 s ago".
  126     - STALE: the source is the API and LIVE doesn't hold, including before the first envelope. When a failed poll is the cause, STALE shows its reason: "transport", "paging error", "stream replaced", "row too large" or "paging unsupported". When K has dropped below its high, the reason is "chain broken".
  127     - REPLAY: the source is a file.
  128     - After catch-up, a running run with no growth for 60 s is STALE, as before.
  129     - Seeded drills also show "drill".
  130     - Known limit: a server can withhold any suffix, including a final withdrawal, while it keeps releasing earlier envelopes. LIVE stays on and the view can't tell. Only the full history, replayed later, shows the truth.
  131  6. Signatures and where the expected key comes from:
```

### app/view.py

blob `00a3520acea825796615c898fcf486da2d840dfb`

```text
   90  @router.get("/api/view/runs")
   91  def runs():
   92      return {**operations.status(context(), ai_off=True), "service_error": _failure,
   93              "last_failure_at": _last_failure_at,
   94              "loop_alive": _thread is not None and _thread.is_alive()}
   95  
   96  
   97  @router.get("/api/view/events")
   98  def events(run_id: str, after: str | None = None,
   99             limit: str = str(MAX_PAGE_LINES),
  100             format: Literal["jsonl", "json"] = "jsonl",
  101             cursor: str | None = None, cursor_hash: str | None = None):
```

```text
  159      next_after = max((sequence(row) or after_seq for row in page), default=after_seq)
  160      headers = {"cache-control": "no-store", "x-next-after": str(next_after),
  161                 "x-has-more": str(len(rows) > len(page)).lower()}
  162      position = {}
  163      if cursor is not None:
  164          position = {"cursor": cursor, "next_cursor": cursor + len(page),
  165                      "next_cursor_hash": page[-1]["prefix_hash"] if page else boundary}
  166          headers["x-next-cursor"] = str(position["next_cursor"])
  167          headers["x-cursor-hash"] = position["next_cursor_hash"]
  168      if format == "jsonl":
  169          return Response(b"".join(row["raw"] for row in page), media_type="application/x-ndjson", headers=headers)
```

```text
  186  @router.get("/api/view/key")
  187  def key():
  188      keys = [{"key_id": key_id, "alg": "ed25519", "public_key": raw.hex(),
  189               "key_sha256": hashlib.sha256(raw).hexdigest()} for key_id, raw in context().public_keys.items()]
  190      return {"keys": keys}
```

### app/main.py

blob `224e312972e9a6c879fe23a478d18aac7622466c`

```text
   28  @app.get("/api/health")
   29  def health() -> dict:
   30      return {"ok": True, "service": "thermal-api", "build_sha": os.environ.get("BUILD_SHA", "unknown")}
   31  
   32  
   33  @app.on_event("startup")
   34  def mark_interrupted_runs() -> None:
   35      runs.recover()
   36  
   37  
   38  @app.post("/api/runs")
   39  async def start_run(request: Request):
   40      try:
   41          body = await request.json()
   42      except ValueError:
   43          return JSONResponse({"error": "body must be JSON"}, status_code=400)
   44      try:
   45          started = runs.start(body)
   46      except ValueError as exc:
   47          return JSONResponse({"error": str(exc)}, status_code=400)
   48      if started is None:
   49          return JSONResponse({"error": "busy", "detail": "one run at a time; try again shortly"}, status_code=429,
   50                              headers={"retry-after": "5"})
   51      return JSONResponse(started, status_code=202)
   52  
   53  
   54  @app.get("/api/runs")
   55  def list_runs() -> dict:
   56      return {"runs": runs.recent()}
   57  
   58  
   59  @app.get("/api/runs/{run_id}")
   60  def get_run(run_id: str):
   61      text = runs.get(run_id)
   62      if text is None:
   63          return JSONResponse({"error": "run not found"}, status_code=404)
   64      return Response(text, media_type="application/json", headers={"cache-control": "no-store"})
```

### sentilab_core/conductor.py

blob `06f8658b1b401af9f9dfead995baf4bcd75fd32c`

```text
  341                    "input_hashes": dict(result.input_sha256)}
  342          semantics = {"task_contract": self.config["task_id"], "metric_id": "peak-chip-c",
  343                       "evaluator_version": self.config["solver_id"], "coordinate_frame": "lower-left-mm"}
  344          values = {"J": {"value": record["j"], "unit": "C"},
  345                    "W": {"value": record["wire_mm"], "metric_id": "weighted-manhattan-mm"},
  346                    "scenario_id": "nominal", "artifact_hashes": list(record["input_hashes"].values())}
  347          self.emit("node.create", {"id": measurement_id, "kind": "measurement", "semantics": semantics,
```

```text
  387                  proposal["originator"] = provenance
  388                  proposal["missing"] = missing
  389              geometry = view_geometry(candidate)
  390              candidate_envelope = self.emit("node.create", {"id": node, "kind": "candidate", "record": proposal}, node,
  391                                             {"geometry": geometry, "units": "mm", "scenario_id": "nominal"})
```

### sentilab_core/test_conductor.py

blob `ebdf9db367e8a0e3855dde8ab1b20b23b8ac48f3`

```text
   78          measurements = [e for e in prefix if e["event"]["type"] == "node.create"
   79                          and e["event"]["body"].get("kind") == "measurement"]
   80          self.assertEqual(len(measurements), 4)
   81          for entry in measurements:
   82              record, values = entry["event"]["body"]["record"], entry["values"]
   83              self.assertEqual(values["J"], {"value": record["j"], "unit": "C"})
   84              self.assertEqual(values["W"], {"value": record["wire_mm"], "metric_id": "weighted-manhattan-mm"})
   85              self.assertNotIn("center_temps", values)
   86  
```

### sundai_hotspot/tap_oracle_worker.py

blob `89006afabdccac612c01335464f5077d550e8366`

```text
   61  def _parse_grid(path: Path, rows: int, cols: int) -> tuple[tuple[tuple[float, ...], ...], float]:
   62      layers: dict[int, list[float]] = {}
   63      current_layer = None
   64      for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
   65          stripped = line.strip()
   66          if not stripped:
   67              continue
   68          if stripped.startswith("Layer "):
   69              match = re.fullmatch(r"Layer\s+(\d+):", stripped)
   70              if not match:
   71                  raise ValueError(f"invalid grid layer header at line {line_number}")
   72              current_layer = int(match.group(1))
   73              if current_layer in layers:
   74                  raise ValueError(f"duplicate grid layer {current_layer}")
   75              layers[current_layer] = []
   76              continue
   77          if current_layer is None:
   78              raise ValueError(f"grid value before layer header at line {line_number}")
   79          fields = stripped.split()
   80          if len(fields) != 2:
   81              raise ValueError(f"invalid grid cell at line {line_number}")
   82          index = int(fields[0])
   83          value = _finite_number(float(fields[1]), "grid temperature")
   84          if value <= 0:
   85              raise ValueError(f"grid temperature must be positive Kelvin at line {line_number}")
   86          values = layers[current_layer]
   87          if index != len(values):
   88              raise ValueError(f"non-sequential grid index at line {line_number}")
   89          values.append(value)
   90  
   91      if set(layers) != set(range(8)):
   92          raise ValueError("HotSpot did not return all eight TAP layers")
   93      expected_cells = rows * cols
   94      for layer, values in layers.items():
   95          if len(values) != expected_cells:
   96              raise ValueError(
   97                  f"HotSpot layer {layer} has {len(values)} cells; expected {expected_cells}"
   98              )
   99      values = layers[4]
  100      heatmap = tuple(tuple(values[offset:offset + cols]) for offset in range(0, expected_cells, cols))
  101      return heatmap, max(max(layer) for layer in layers.values())
```

```text
  343      steady = output / "sample.steady"
  344      grid = output / "sample.grid.steady"
  345      layers = output / "samplelayers.lcf"
  346      input_paths = tuple(sorted(path for path in output.iterdir()
  347                                if path.is_file() and path.name not in {'REQUEST.json', 'PHASES.json'}))
  348      input_hashes = {path.name: _sha256(path) for path in input_paths}
  349      layer_references = {
  350          Path(line.strip()).name
  351          for line in layers.read_text(encoding="utf-8").splitlines()
  352          if line.strip().endswith(".flp")
  353      }
  354      if not layer_references or not layer_references.issubset(input_hashes):
  355          raise RuntimeError("TAP layer config references an unhashed generated floorplan")
  356      command = [
  357          str(hotspot_binary),
  358          "-c", str(config),
  359          "-f", str(floorplan),
  360          "-p", str(trace),
  361          "-steady_file", str(steady),
  362          "-grid_steady_file", str(grid),
  363          "-model_type", "grid",
  364          "-detailed_3D", "on",
  365          "-grid_layer_file", str(layers),
  366          "-grid_rows", str(rows),
  367          "-grid_cols", str(cols),
```

```text
  418      return {
  419          "candidate_hash": candidate_hash,
  420          "problem_hash": problem_hash,
  421          "binary_sha256": binary_sha256,
  422          "grid_rows": rows,
  423          "grid_cols": cols,
  424          "ambient_c": ambient_c,
  425          "heatmap_c": [[cell - 273.15 for cell in row] for row in heatmap],
  426          "maximum_temperature_c": max(max(row) for row in heatmap) - 273.15,
  427          "all_layers_peak_c": all_layers_peak - 273.15,
  428          "solver_seconds": solver_seconds,
  429          "input_generation_seconds": generation_seconds,
  430          "input_sha256": input_hashes,
  431      }
```

### sundai_tap/passive_interposer.py

blob `b51518258f3a4572efb636926bfcd5495c8a3c9b`

```text
  135  		with open(self.path+filename + 'layers.lcf','w') as LCF:
  136  			LCF.write("# File Format:\n")
  137  			LCF.write("#<Layer Number>\n")
  138  			LCF.write("#<Lateral heat flow Y/N?>\n")
  139  			LCF.write("#<Power Dissipation Y/N?>\n")
  140  			LCF.write("#<Specific heat capacity in J/(m^3K)>\n")
  141  			LCF.write("#<Resistivity in (m-K)/W>\n")
  142  			LCF.write("#<Thickness in m>\n")
  143  			LCF.write("#<floorplan file>\n")
  144  			LCF.write("\n# Layer 0: substrate\n0\nY\nN\n1.06E+06\n3.33\n0.0002\n"+self.path+filename+"L0_Substrate.flp\n")
  145  			LCF.write("\n# Layer 1: Epoxy SiO2 underfill with C4 copper pillar\n1\nY\nN\n2.32E+06\n0.625\n0.00007\n"+self.path+filename+"L1_C4Layer.flp\n")
  146  			LCF.write("\n# Layer 2: silicon interposer\n2\nY\nN\n1.75E+06\n0.01\n0.00011\n"+self.path+filename+"L2_Interposer.flp\n")
  147  			LCF.write("\n# Layer 3: Underfill with ubump\n3\nY\nN\n2.32E+06\n0.625\n1.00E-05\n"+self.path+filename+"L3_UbumpLayer.flp\n")
  148  			LCF.write("\n# Layer 4: Chip layer\n4\nY\nY\n1.75E+06\n0.01\n0.00015\n"+self.path+filename+"L4_ChipLayer.flp\n")
  149  			LCF.write("\n# Layer 5: TIM\n5\nY\nN\n4.00E+06\n0.25\n2.00E-05\n"+self.path+filename+"L5_TIM.flp\n")
  150  
  151  		if os.path.isfile(self.path + 'new_hotspot.config') == False:
  152  			with open('util/hotspot.config','r') as Config_in:
  153  				with open(self.path + 'new_hotspot.config','w') as Config_out:
  154  					size_spreader = 2 * self.intp_size / 1000
  155  					size_heatsink = 2 * size_spreader
  156  					r_convec =  0.1 * 0.06 * 0.06 / size_heatsink / size_heatsink   #0.1*0.06*0.06 are from default hotspot.config file
  157  					for line in Config_in:
  158  						if line == '		-s_sink				0.06\n':
```

### docs/sentilab/draft-0.5/REQUIREMENTS.md

blob `ad6a38f71cbaa6769ed7c2cb236c951cca6d835c`

```text
  172  | V06 | Every animation tied to agent/artifact/event timestamp | A6; B8 | SLAB-007, SLAB-025, SLAB-027 | No fabricated activity check |
```

```text
  177  | V11 | Replays and time compression visibly labeled | A8; B8 | SLAB-027 | Replay labeling test |
```

```text
  179  | V13 | Correct field/layer display; no false continuous die heatmap | A6; B4 | SLAB-006, SLAB-025 | Exporter/display unit/layer assertion |
```

```text
  264  | F24 | Temperature comparisons share a declared color scale; robotics physics never substitutes thermal evidence | Science review | SLAB-025, SLAB-026 | Visual scale and physics-source assertions |
```

```text
  269  | F29 | Current TAP uses chip-layer grid peak; proposed eight-chiplet primary change requires G1/version approval | Canonical addendum | SLAB-005, SLAB-006, SLAB-025 | Correct layer/statistic and approved primary/diagnostic labels |
```

### docs/sentilab/CHIPLET-VISUAL-SCOPE-DISPOSITION.md

blob `0288958990d5aebb762fd89b945250fdb14574e3`

```text
    7  Carter's authenticated human reply `6eafa071-acf2-40f7-bf40-a875babaedc4` to #56110 at `2026-10-31T05:45:27.427Z` says: “Wait I never said to use microduck at all. I said to take after their simulation model to make ours the visual etc. Never anything from their licenses. Wtf”. The effective scope is NVIDIA-inspired simulation and visualization for **our chiplets**, with original chiplet assets and truthful thermal evidence. No MicroDuck/Pollen robot, code, models or meshes; no robot locomotion, robot policy-training or sim-to-real delivery obligation. This resolves the old pending-owner-narrowing condition. It does not reduce the work to cosmetic styling.
```

```text
   33  | F24 | Retain common declared temperature scales and truthful source binding. Express the remaining boundary as renderer/animation versus thermal evaluator; neither animation nor a general physics engine proves temperatures. |
```

```text
   39  V01–V07 and V11–V13 remain: exact layout/moves, real lab activity, evidence/dependencies, comparisons, measured results/reproduction, artifact/agent/time-bound animation, exact supplied video as reference, replay/compression labels, rebuildable backup and correct field/layer display. V07 remains source inspection, not permission to import robot assets.
```

### scripts/sentilab-scene.mjs

blob `62d14adb2f3eb2023fc8b7a037b93ebf9bf69362`

```text
    1  #!/usr/bin/env node
    2  // SentiLab scene CLI: build the Package view's scene from a replay, with the same verification and prefix rule as
    3  // the page, but using the node REFERENCE verifier: VIEW ENVELOPE v0.5 (contracts/view-envelope-v0.5/view-envelope.mjs),
    4  // after the v0.6.1 bytes-to-rows rule (contracts/view-envelope-v0.6.1/paging.mjs verifyReplayBytes), exactly the path the
    5  // page takes through the browser ports of both.
    6  // Output is JSON on stdout. This is the CLI half of SLAB-026's CLI+MCP; the MCP half comes later through the
    7  // generated bridge, so the command table stays small and every result is one JSON object.
    8  //
    9  //   node scripts/sentilab-scene.mjs build  <replay.jsonl> [--run <id>] [--pins test] [--key <key_id>=<hex>] [--at <seq>] [--strict]
   10  //   node scripts/sentilab-scene.mjs export <replay.jsonl> --out <scene.json> [same options]
   11  //   node scripts/sentilab-scene.mjs help
   12  //
   13  // Trust: the production pins come from web/public/sentilab/view-pins.js, as in the page. A served public key may be
   14  // given with --key; it is used only if its sha256 matches a pin. --pins test uses the vectors' "core" test key, which
   15  // anyone can derive; the output says so. Exit codes: 0 ok; 1 usage or input error; with --strict, 2 for a broken
   16  // prefix (chain) and 3 for refused values (a verified value with an unsupported unit or out of range: scene.errors).
   17  // Lengths are exported in mm and temperatures in °C; a refused value is listed, never exported as a number.
```

### scripts/export-deck-pdf.mjs

blob `34cec45cae99e950c2a26f2f0bf89f074ea89122`

```text
    1  #!/usr/bin/env node
    2  // Prints the SentiLab deck to PDF (one 1920x1080 page per slide) and, with --shots, screenshots and checks every slide.
    3  //
    4  //   PLAYWRIGHT_DIR=<dir containing node_modules/playwright> node scripts/export-deck-pdf.mjs [--shots <dir>] [--no-pdf]
    5  //
    6  // Run scripts/build-deck-data.mjs first. The deck directory (DECK_DIR, deck/) is served by a throwaway local server, so
    7  // it reads deck-data.json exactly as a browser would. Output: docs/sentilab/deck/SentiLab-deck-<UTC date>.pdf, one page
    8  // per slide and nothing else: the speaker notes are not printed (they are in deck-data.json and the deck's N panel).
    9  // --shots <dir> also writes every slide at 1920x1080 and 1280x720 (plus one with the notes panel) and a report.json.
   10  // Each slide is checked: nothing outside its block or the canvas, no clipped text, smallest font size, pending values.
   11  // Exit 1 when a check fails, the browser logs an error or a request fails, or the PDF page count differs from the slide
```

```text
   72          const pr = parent.getBoundingClientRect();
   73          if (!within(r, pr, 2.5)) out.issues.push(`spills out of its container ${name(parent)}: ${name(el)}`);
   74        }
   75        if (el.classList.contains("frame")) continue; // a crop window: its image overflows on purpose
   76        if (el.scrollWidth > el.clientWidth + 2 && cs.overflowX !== "visible") out.issues.push(`clipped horizontally: ${name(el)}`);
   77        if (el.scrollHeight > el.clientHeight + 2 && cs.overflowY !== "visible") out.issues.push(`clipped vertically: ${name(el)}`);
   78        const text = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
```

```text
  100  async function open(w, h, query = "") {
  101    const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
  102    const page = await ctx.newPage();
  103    page.on("console", (m) => { if (["error", "warning"].includes(m.type())) report.console.push(`${w}x${h}: ${m.text()}`); });
  104    page.on("pageerror", (e) => report.console.push(`${w}x${h}: pageerror ${e.message}`));
  105    page.on("requestfailed", (r) => report.console.push(`${w}x${h}: request failed ${r.url()} ${r.failure()?.errorText ?? ""}`));
  106    page.on("response", (r) => { if (r.status() >= 400) report.console.push(`${w}x${h}: HTTP ${r.status()} ${r.url()}`); });
```

### .github/workflows/ci.yml

blob `9276a5122cfe45d4983e1bc81086decaf889916b`

```text
   14    browser-verifier:
   15      runs-on: ubuntu-24.04
   16      timeout-minutes: 10
   17      permissions:
   18        contents: read
   19      steps:
   20        - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
   21        - uses: actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020 # v4.4.0
   22          with:
   23            node-version: '22'
   24        - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5.6.0
   25          with:
   26            python-version: '3.12'
   27        - name: Install the Python signing fixture dependency
   28          run: python -m pip install "$(grep '^cryptography==' requirements.txt)"
   29        - name: Verify browser trust and Python record compatibility (ephemeral keys)
   30          run: node --test web/test/*.test.mjs
   31        # The unit tests import worker.js as a plain module; only the Workers runtime refuses what it can't start (a
   32        # named export of the main module, for one). Bundle it, boot it with wrangler dev (no credentials; the /api
   33        # upstream is off), and check the pages carry the exact CSP and /api still reaches the proxy.
   34        - name: The Worker boots in the Workers runtime and serves the CSP (wrangler dev)
   35          run: node web/test/worker-boot.mjs
```

