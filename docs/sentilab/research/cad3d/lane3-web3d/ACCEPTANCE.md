# Package 3D: acceptance criteria

Lane 3 (web 3D + live simulation). Grounded in `origin/main` at `46791be360555d0e24b4ad5f906abafb71f07118`.
Each criterion names how it is tested, what passes, and the adversarial inputs it must survive. "node" tests
run in CI with `node --test web/test/*.test.mjs` (ci.yml:30); "browser" tests use Playwright against a local
server that sends the exact production CSP (the pattern in scripts/export-deck-pdf.mjs:1-11, 72-78, 100-106);
"device" checks are manual on real hardware, with the recording attached to the PR.

Requirement keys: V06 every animation tied to an event; V11 replay and time compression labelled; V13 correct
field/layer display, no false continuous die heatmap; F24 shared declared colour scale, renderer is not the
evaluator (REQUIREMENTS.md:172, 177, 179, 264; CHIPLET-VISUAL-SCOPE-DISPOSITION.md:33, 39).

## Top 5 (must pass before anything ships)

| # | Criterion | Test |
|---|---|---|
| 1 | A withdrawn (or unvalidated) temperature can never render as a plain number, in DOM text, tooltips, the twin, or a cropped screenshot of the canvas | A-01, A-02 |
| 2 | A field reaches the GPU only from an artifact whose sha256 is named by a measurement in the verified projectable prefix and whose content passes every check; anything else is refused, listed, and leaves the texture bytes unchanged | A-03, A-04 |
| 3 | The 3D view's live label is exactly the Package view's (v0.6.2 rule 5): a disconnect mid-solve shows STALE with its reason and "solve status unknown", never "solving"; a K drop removes later fields at once | A-05, A-06 |
| 4 | The CSP string is unchanged and nothing on the page violates it: zero `securitypolicyviolation` events and zero console errors through load, explode, section, live, context loss and fallback; no clipped text at 390 and 1280 px | A-08, A-09 |
| 5 | Phone budgets hold (p95 frame time, draw calls, triangles, GPU memory, idle = no frames), and with no WebGL2 or a lost context the 2D cross-section shows the same parts, labels, label states and notice | A-10, A-11 |

## A-01 Temperature text always carries its label (node + browser)

- node: `formatTemp(v, label)` throws for any `label` that is not one of the frozen `LABELS` objects
  (temperature-label.mjs:38-53), including a structurally identical copy, `null`, a string, and
  `{ ...LABELS.accepted }`. It throws for NaN, ±Infinity and non-numbers.
- node: static scan of `web/public/sentilab/package3d/*.{js,mjs}`: no `toFixed(` and no `°C` outside `temps.mjs`
  (the same kind of source assertion temperature-label.test.mjs makes on its module).
- node: the page is added to the "every page takes its notice and labels from this one module" test
  (temperature-label.test.mjs:320-337): `package3d.js` imports `NOTICE` via `temps.mjs` from
  `../../temperature-label.mjs`, holds no copy of the notice text, and `index.html` has the exact notice slot.
- browser: load a signed replay whose measurements carry the live affected identity (the `LIVE_HS7` string in
  temperature-label.test.mjs). Walk every text node: each match of `/-?\d+(\.\d+)?\s*°C/` sits inside an element
  `.t.s-withdrawn` whose `.q` child reads `pre-correction` (LABELS.withdrawn.short), and the page notice is
  visible. Repeat with the corrected-evaluator identity (expect `.s-unvalidated`, "unvalidated") and with no
  identity at all (fail safe: unvalidated).
- Adversarial: identity spelled with different case and padding (`  hotspot-7:F18831E...:grid:64x64 `) is still
  withdrawn (temperature-label.mjs:57); a variant `HotSpot-7:<commit>+SLAB-049:...` is unvalidated, not plain;
  a legend whose scale mixes a withdrawn and an illustrative source is labelled withdrawn (labelForAll).
- Pass: zero unlabelled temperature strings; every label state on screen equals the rule's output for the
  envelope that carries the value.

## A-02 The canvas itself shows the state (browser, pixel probe)

- With a withdrawn field shown, read back the canvas (Playwright screenshot of the canvas element only) and
  check the hatch: along a horizontal line across a field sheet, the luminance alternates with the hatch
  period. Unvalidated: stipple present. Illustrative/accepted: no pattern.
- The hatch never changes the colour of the unhatched pixels: sampled unhatched pixels at known cells equal
  `heatColor(t, scale)` within ±3/255 per channel (unlit material, no tone mapping).
- The corner chip "Schematic model · not manufacturer CAD" and the label-state chip are inside the canvas
  wrapper at 390 and 1280 px.
- Pass: a screenshot cropped to the canvas alone still shows that a withdrawn field is withdrawn.

## A-03 Only verified, named artifacts are fetched (node + browser network log)

- node (`stream.mjs` with an injected fetch): `fieldRefs()` returns only hashes from measurement
  `node.create` envelopes inside `prefixEnvelopes` that `project()` applied. Hashes in envelopes after K, in
  rejected events, in a replay file's other fields, or in an unverified row are never requested.
- browser: replay vector V8 (signed withdraw at seq 7 dropped; VIEW-ENVELOPE v0.5 lines 118-121) extended with a
  field at seq 9: the network log has zero requests for the seq-9 artifact; the field at seq 5 is shown.
- Pass: requested set ⊆ allowlist, checked on every run of the suite (the instrumented-counter style of
  view-core.mjs, which proves rejected input never reaches hashing).

## A-04 Malformed or mismatched frames are rejected, not rendered (node)

For each case, `checkFieldArtifact` returns `{ ok: false, error }`, the texture updater is never called (spy),
the previous texture bytes are unchanged, and the page lists the refusal with its reason:

| Case | Expected error |
|---|---|
| bytes whose sha256 differs from the signed pointer by one bit | `hash_mismatch` (nothing decoded first) |
| 4 MiB + 1 byte | `too_large` (body read stops at the cap, readBodyCapped) |
| invalid UTF-8, a BOM, truncated JSON | `malformed` |
| `format` other than `sentilab-field/0.1` | `format` |
| binding names another run, another measurement, or another evaluator than the envelope's semantics (including the fixture identity on a withdrawn envelope: an attempt to launder a withdrawn field as illustrative) | `binding_mismatch` |
| rows/cols/layers differ from the pointer, a layer array one value short, 129 rows, 17 layers | `dims` |
| a string, `null`, `1e400` (parses to Infinity) | `out_of_range` |
| −300 °C, 0 K, 2001 °C, 1e20 K | `out_of_range` (scene.mjs BOUNDS) |
| unit missing or `F` | `unit_not_supported` |

- Orientation fixture: a field with one hot cell at row 0 / column 0 declared `row0: "top"` renders the hot texel
  at the upper-left of the sheet (high y, low x); the same data declared `row0: "bottom"` renders it lower-left.
  A flipped field fails the test.
- Pass: every row of the table, plus the orientation pair.

## A-05 Live honesty: same label as the Package view (node, driving the page's own poller)

- The 3D page's header label is computed only by `source.mjs liveModeOf()` / `modeNow()` (source.mjs:172-182);
  a static test asserts package3d.js does not compute LIVE/STALE itself.
- Reuse the Package view's live vectors (sentilab-scene.test.mjs runs C1, C2, C11, C12a, C13, C15a-c, C16,
  C17a-c through the package view's live path, lines 988-1035): the 3D page shows the identical label for every
  poll.
- Disconnect mid-solve: rows deliver a candidate whose lifecycle reaches `simulation_pending`; the next poll
  throws (transport). Expected within that poll: label `STALE · transport`; solve chip `solve status unknown
  (feed STALE · transport)`; never `solving`. After recovery and K growth: `LIVE · progress N s ago` and
  `solving` again only if the verified lifecycle still says so.
- No progress for 60 s after catch-up: STALE (v0.6.2 rule 5). Catching up a long backlog never shows LIVE.
- A doorbell (if built) that fires repeatedly with no new rows never makes the label LIVE (vector V17's rule:
  arrivals that don't grow K never refresh it).
- Pass: label sequence equals the reference trace; no `solving` text while the label is not LIVE.

## A-06 A shrinking prefix takes fields with it (node + browser)

- Live vector C11 on a run with fields: a late signed seq 10 conflict drops K to 9. Within that poll the 3D view
  shows `STALE · chain broken`, the field for any measurement after seq 9 is removed from the GPU, cached
  artifacts for those hashes are dropped, and in-flight fetches for them are aborted (AbortController spy).
- Pass: after the drop, `window.__package3d.facts().fieldAsOf <= 9` and no texture for a removed hash exists.

## A-07 The field is the solver's grid, on the solver's layer, on one declared scale (node + browser) [V13, F24]

- One colour function: `colourLut(scale)` is built only from scene.mjs `heatColor()`, and for 200,000
  temperatures across each of three scales (10 °C, 80 °C and 400 °C wide) every channel of the table's colour is
  within 1/255 of `heatColor()` (the bound measured in evidence/extra-05). Values outside the scale clamp to its
  ends, as `heatColor()` does.
- Nearest filtering only: adjacent texels of different value render as a hard edge (pixel probe across a
  cell boundary shows no intermediate colour beyond antialiasing at the sheet's border).
- The legend names the grid ("grid R × C, cell W × H mm") and the layer ("solver layer L: <name from the
  artifact>"), and the scale is the run's fixed scale: stepping the playhead does not change the legend ticks
  (the rule scene.mjs runFrame applies to centre temperatures, scene.mjs:210-244; widen-only when live,
  playhead.mjs:27-38).
- Without a verified field, no sheet is coloured: chiplets keep the existing per-chiplet centre colour or none,
  with the existing basis text "chiplet-centre temperatures from the solver; not a field" (scene.mjs:18).
- A part with `solver_layer: null` is drawn neutral with "not in the thermal model" in its info panel whenever
  a field is shown.
- Pass: all four, plus a test that no code path builds a field from centre temperatures (no interpolation of
  `center_temps` anywhere in package3d/).

## A-08 CSP stays strict (node + browser)

- worker-csp.test.mjs passes unchanged (the exact string, worker-csp.test.mjs:20, 47-49); the new page is added to
  its asset list and to worker-boot.mjs's checked pages.
- browser: listen for `securitypolicyviolation` on the document and in the console for the whole session
  (load replay, explode, section, field on/off, live with a fixture server, simulated context loss, forced
  fallback). Pass: zero events.
- node: static scan of package3d/*.{js,mjs} for `eval(`, `new Function`, `Function(`, `WebAssembly`,
  `createObjectURL`, `innerHTML`, `insertAdjacentHTML`, `setAttribute("style"`, `createElement("style")`,
  `new Worker(` with a `blob:` or `data:` URL. Any hit fails. (Under the three.js alternative the scan also covers
  the vendored files; web-02 found no `eval`/`Function` constructor in r187 and one `blob:` use, in GLTFLoader,
  which is not vendored.)
- No `blob:` or `data:` workers, no WebAssembly, no CDN URL anywhere in the page's requests (network log: every
  request is same-origin).

## A-09 390 px and 1280 px layouts (browser screenshots)

- Viewports 390×844 (deviceScaleFactor 3) and 1280×800 (1). For each: replay loaded, assembled; exploded; part
  selected; section on; field on with a withdrawn label; fallback forced.
- Checks (the deck exporter's checks, export-deck-pdf.mjs:72-78): no element clipped horizontally or vertically
  where overflow isn't visible; `document.scrollingElement.scrollWidth <= innerWidth` (no sideways scroll); the
  legend, its label-state chip and the page notice are visible in the first viewport at 390 px without
  scrolling past the canvas; labels never overlap each other (bounding boxes) and stay inside the canvas box;
  smallest text ≥ 11 CSS px.
- Pass: all checks, screenshots attached to the PR (the house rule for UI PRs: real-browser 1280 + 390 checks).

## A-10 Performance budgets (device + browser traces)

Measured on a mid-range phone (reference: a 2021-2022 Android, Adreno 6xx or Mali-G7x class, Chrome stable)
and on desktop, with the largest fixture (8 solver layers at 64 × 64, every interconnect array present):

| Budget | Phone | Desktop |
|---|---|---|
| p95 frame time while orbiting or exploding | ≤ 33 ms | ≤ 16.7 ms |
| frames rendered while idle (no input, no animation, no new data) | 0 after 1 s | 0 after 1 s |
| draw calls (the renderer's `stats.calls`, exposed by the `__package3d` test hook; three.js alternative: `renderer.info.render.calls`) | ≤ 60 | ≤ 120 |
| triangles per frame | ≤ 300 k | ≤ 1.5 M |
| drawn interconnect instances | ≤ 6 000 | ≤ 60 000 |
| field texture memory (RGBA8) | ≤ 4 MB | ≤ 16 MB |
| device pixel ratio used | ≤ 2 | ≤ 2 |
| JS heap after 10 min live | ≤ 60 MB, no growth trend | ≤ 120 MB |
| new verified field to pixels (check + texels + upload), 8 × 32 × 32 | ≤ 8 ms | ≤ 2 ms |
| the same for 8 × 64 × 64 (check and parse in a module Worker) | ≤ 30 ms, main thread not blocked | ≤ 8 ms |
| first 3D frame after verification, cold cache, 4G profile | ≤ 2.5 s | ≤ 1 s |

- Pass: all rows on both classes, trace files attached.

## A-11 No-WebGL fallback and context loss (browser)

- Chromium launched with WebGL disabled (`--disable-webgl` / `--disable-3d-apis`): the page shows the SVG
  cross-section from `section.mjs`, the part list, the legend with its label state and the notice; zero errors.
- `WEBGL_lose_context.loseContext()` mid-session: the fallback appears within one frame, the selection and
  playhead are kept; `restoreContext()`: the 3D view returns with the same model, explode amount, section and
  field (rebuilt from the RenderModel; no refetch of verified artifacts).
- Parity: for the same model, plane and explode amount, the 3D cap rectangles and the SVG rectangles come from
  the same `sectionAt()` call (node test compares them; browser test compares counts and ids).

## A-12 Module boundaries (node, static)

- Only `render3d.mjs` and `gl.mjs` call WebGL. No file imports a third-party module. (Under the three.js
  alternative: only `render3d.mjs` imports the vendored copy, by a relative path, and no file imports the bare
  specifier `"three"`.)
- PURE modules (`model`, `explode`, `section`, `interconnect`, `field`, `temps`, `twin`) import no DOM global
  (`document`, `window`, `requestAnimationFrame` outside the explode driver), no `Date.now`, no `Math.random`.
- `package3d.js` gets verified data only from `../package/source.mjs`.

## A-13 Provenance on every number (node + browser)

- node: every box in a RenderModel has `prov.xy`, `prov.z` and `prov.material` in
  `evidence | solver | nominal | schematic`; chiplet footprints are always `evidence`; nothing else is.
- browser: the info panel prints the tag beside each dimension; when any layer is thickened, the chip "thin
  layers thickened for visibility" is visible; when exploded, "exploded; spacing not to scale" is visible;
  sampled arrays show "1 of k² sites drawn; N total (nominal)".
- Adversarial: a parts.json that tries to give a chiplet an explicit lateral size is refused for that field
  (chiplet footprints come only from evidence).

## A-14 Site rules over every new served file (node)

- public-names.test.mjs and control-bytes.test.mjs pass with every new served file included (they scan all of
  web/public: public-names.test.mjs:1-4; control-bytes.test.mjs:1-4): the page, its modules, parts.json and the
  /agents/ twin. If a binary `.glb` is served under /agents/, `.glb` is added to control-bytes' BINARY list with
  that reason.
- Only under the three.js alternative: `web/test/vendor-pins.test.mjs` recomputes sha256 of every file under
  `web/public/vendor/three-0.187.0/` and compares it with VENDOR.json (npm tarball URL, `dist.integrity`, git
  head); the MIT LICENSE is present and listed on licenses.html; the one public-names hit in `three.core.js`
  (evidence/extra-02) is either a narrow exception pinned to that file hash, or removed by a reproducible minify
  step that keeps the `@license` header.

## A-15 Agent twin (node + validator)

- `export3d` run twice on the same replay, parts.json and artifacts gives byte-identical `twin.json` and
  `twin.glb`.
- The twin's parts, boxes, links and field refs equal what `buildModel()` gives the page for the same inputs
  (parity test, as sentilab-scene.test.mjs line 357 does for the 2D scene).
- Khronos glTF-Validator reports 0 errors on `twin.glb`; node names equal part ids; positions are metres, Y up.
- Every temperature in the twin is accompanied by its label text (same rule as A-01); refused values are listed,
  never exported as numbers (the CLI's existing rule, sentilab-scene.mjs:17).

## A-16 Reduced motion and input (browser)

- With `prefers-reduced-motion: reduce` emulated: no auto-orbit, explode jumps without tweening, playhead steps
  without glides, no pulsing; frames are rendered only on direct manipulation.
- Keyboard: every action reachable (Tab to the part list, Enter selects, arrows orbit when the canvas has focus,
  E explode, S section, F field, Esc clears); focus is visible; the canvas has `role="img"` and a summary
  `aria-label`; LIVE/STALE changes are announced through a polite live region.
- Touch at 390 px: one-finger orbit, two-finger pinch zoom and pan, tap selects; page scroll still works outside
  the canvas.

## A-17 The optional sketch solver (only if built)

- Its output is never written as °C, never shares a canvas or legend with verified data, and its mode banner
  "SKETCH · in-browser approximation · not evidence" is visible at 390 px. A test asserts `temps.mjs` refuses its
  values (there is no LABELS entry for it) until the label-rule owner adds a state with its own tests.
- It runs in a same-origin module Worker file (no blob: worker, no WebAssembly).
