# Package 3D: acceptance criteria

**Companion to SPEC.md v0.1 (2026-10-31).** Each criterion says how it is tested, what passes, and the adversarial
inputs it must survive. It consolidates lane 3's A-01 to A-17 (L3:ACCEPTANCE.md at `253ee4f7`) with astra's criteria
(A#57053, A#57059) and the separation, quantity and identity rules of SPEC.md. File:line citations are origin/main
`d25046256b4a712b529977f31e10b7e32248a9c0`.

Test kinds:
- **node**: `node --test web/test/*.test.mjs` in CI on Node 22 (.github/workflows/ci.yml:23, :30).
- **python**: the repo's Python test run (`sundai_hotspot/test_package3d_model_stack.py`).
- **static**: source or data scans inside node tests.
- **browser**: Playwright (via `PLAYWRIGHT_DIR`, as scripts/export-deck-pdf.mjs:4) against the real Worker run locally
  the way web/test/worker-boot.mjs:5-11 runs it, so the production CSP header applies. (The deck exporter's own server
  sends no CSP, scripts/export-deck-pdf.mjs:38, so it is not used for these checks.)
- **device**: manual on the reference phone (D4), recording and traces attached to the PR.

Gate: no phase is done until its listed ACs pass (SPEC.md §9). The top gate for any public release of the page is
AC-01 to AC-06, AC-12, AC-20 to AC-27, AC-32, AC-34 and AC-36.

## Temperatures and labels

**AC-01 `formatTemp` refuses anything but the rule's labels** (node). `formatTemp(v, label)` throws for any `label`
that is not one of the frozen `LABELS` objects (main:web/public/temperature-label.mjs:38-53): a structurally identical
copy, `{ ...LABELS.accepted }`, `null`, a string, `undefined`. It throws for `NaN`, `±Infinity`, a numeric string and
`null` values. Pass: every case throws; the four real labels format.

**AC-02 No temperature text outside `temps.mjs`** (static). In `web/public/sentilab/package3d/*.{js,mjs}`: no
`toFixed(` outside `temps.mjs` and `quantity.mjs` (non-temperature quantities), no `°C`, `℃` or `degC` literal outside
`temps.mjs`, no `fillText`/`strokeText` (no canvas text at all), no import that bypasses `temps.mjs` to format a value.
The page is added to the existing "every page takes its notice and labels from this one module" test
(main:web/test/temperature-label.test.mjs:320-341): `package3d.js` gets `NOTICE` through `temps.mjs` from
`../../temperature-label.mjs`, holds no copy of the notice text, and `index.html` has the exact slot
`<p class="wnotice" id="wnotice" role="note" hidden></p>`. Pass: zero hits; the extended test passes.

**AC-03 Static content holds no temperature** (static). The scanner of PSEUDOCODE §8 (`TEMP_PATTERN`, `TEMP_KEY`) runs
over every string and every key of `web/public/sentilab/package3d/data/*.json`, every static file under
`web/public/agents/package3d/` except result twins, and the model-stack and anatomy sources in
`docs/sentilab/package3d/`. Unit fields are checked against the unit list (no temperature unit). Adversarial: seeded
copies containing `47 C`, `300.5 K`, `61 °C`, `99°C`, `-12 degC`, `0.7 K rise`, `12 kelvin`, `33 ºC`,
`0.04 °C·cm²/W` and the keys `silicon_85C`, `silicon_at_100C` are each caught; `4 K*mm2/W`, `0.039 K/W`,
`5 K·mm²/W`, `117.5 W/(m*K)`, `C4 bumps`, `4 C4 rows`, `10,000-30,000`, `2,778 W/(m²·K)`, `HBM3E 12-high` stay clean.
The model stack's `boundary.temperature_inputs` entries all have `rendered: false` and carry no value. Pass: real files
clean, every seeded case caught, every clean case clean.

**AC-04 Every temperature on screen carries its label** (browser). Load signed replays whose measurements carry
(a) the withdrawn HotSpot-7 identity (`LIVE_HS7`, main:web/test/temperature-label.test.mjs:28; `HS7`,
main:web/test/per-value-provenance.test.mjs:20), (b) the corrected-evaluator identity (`CORRECTED`,
temperature-label.test.mjs:41; per-value-provenance.test.mjs:21), (c) the fixture identity, (d) no identity. Walk every text node and every `title`,
`aria-label` and `alt` attribute in the document, including the Twin JSON dialog. Every match of `TEMP_PATTERN` sits
inside an element `.t.s-<state>` whose `.q` child reads the rule's `short` for that value's identity (pre-correction,
unvalidated, illustrative, simulated), or, for attributes, contains that `short`. The notice is visible for (a), (b),
(d) and hidden for (c). Adversarial: the identity in a different case with padding is still withdrawn
(temperature-label.mjs:57); a `HotSpot-7:<commit>+SLAB-049:…` variant is unvalidated, not plain; a legend over a mix of
withdrawn and fixture values is withdrawn (`labelForAll`); a rejected duplicate create never lends its identity (the
cases of per-value-provenance.test.mjs:59-120). Pass: zero unlabelled temperature strings; every label equals the rule's
output for the envelope that carries that value.

**AC-05 The canvas shows the state by itself** (browser, pixel probe; fields only, fixtures before W14). With a
withdrawn field shown, a screenshot of the canvas element alone shows the hatch (luminance alternates with the hatch
period along a line across a sheet); unvalidated shows the stipple; illustrative and accepted show no pattern;
unhatched pixels at known cells equal `heatColor(t, scale)` within ±3/255 per channel. The content chip and the
label-state chip sit inside the canvas wrapper at 390 and 1280 px. Pass: a canvas-only crop still shows the state
(L3:ACCEPTANCE A-02).

**AC-06 The twin carries the same labels** (node). For result twins (CLI `export3d` and the dialog): every value with
`unit: "degC"` has a `label` object whose `state`, `text`, `short` and `title` equal `LABELS[state]` exactly; refused
values appear only in `refused`, never as numbers (main:scripts/sentilab-scene.mjs:17); the markdown twin shows each
temperature as `<value> °C <short>` in one cell. Adversarial: `twinOf()` given a value without a label, or with a
hand-made look-alike label object, throws; a twin whose label text was edited fails the reader (`label_mismatch`).
Pass: all.

**AC-07 Identity edge cases** (node). Reuse the per-value provenance vectors through `results.mjs`: J from the applied
withdrawn create is labelled withdrawn, not illustrative; J and centre temperatures from different measurements keep
separate labels (`sourceTags`, temperature-label.mjs:139-144); every create rejected means no identity, so unvalidated.
Pass: the same labels the Package view computes for the same prefix (per-value-provenance.test.mjs:73-91).

## Three kinds of content

**AC-08 Separation in data and models** (node, static). `buildRenderModel()` refuses any call that supplies inputs of
two kinds (`mixed_content`). `anatomy.json` and the assembly contain no key matching `our_model`, `in_our_model` or
`solver_layer`, and no quantity with basis `model` or `evidence`; `model-stack.json` contains no anatomy quantity
(only `stands_for` ids); a result RenderModel built without a model stack for its family draws a schematic stack with
every box `render_hint` and the note "model stack unknown for family <f>; drawn schematic", and never an anatomy
thickness. Adversarial: delete the model stack file → the result RenderModel shows the schematic note, not lane-1
numbers; inject an anatomy thickness into a result build → refused. Pass: all (X1 to X5).

**AC-09 Banners and chips match their kind** (browser, node). In each mode the content banner and the canvas chip are
the exact strings of SPEC.md §3, and the twin's `status_text` for that kind is the same string (schema const). Model
mode shows no result value; Results shows no flow arrows; Anatomy shows no result value and no model number outside the
"In our model" line. Pass: string equality, and zero result or model values in the wrong mode.

## Quantities, unknowns, ids

**AC-10 Quantity rules** (node). `readQuantity` refuses: `unknown` with a number; `render_hint` without a value or
`hint_basis`; `sourced` without facts or without any number; `derived` without `derivation`; `model` without
`model_ref`; `evidence` without `evidence_ref`; `min > max`; `value` outside `[min, max]`; a non-finite number; a fact
id not in the manifest; a temperature unit; a bare temperature inside `derivation`, `hint_basis` or `note`. The schema
blocks of SPEC.md §5.1 refuse the same set where the schema language can say it. Pass: every case refused with its
code; valid cases accepted.

**AC-11 An unknown dimension renders as unknown** (browser, node). The lid's thickness (no source in lane 1:
L1:REPORT §3.3) shows `not sourced · drawn at 1.000 mm (display only: …)` with the hint's reason; the die-side
capacitors' count shows `unknown`; an instance with an unknown size and no hint is listed `not drawn · size unknown` in
the part tree and absent from the canvas; the twin carries `value: null` with `basis: "unknown"` or the hint with
`basis: "render_hint"`. Adversarial: a build that silently fills an unknown (for example copies the model's 1 mm
spreader into the anatomy lid as `sourced`) fails `readAnatomy`. Pass: all.

**AC-12 Explode never mutates geometry** (node, browser). After `buildRenderModel()`, `Object.isFrozen` holds for the
model and every nested object; a write in strict mode throws. Record `geometry_key` (the canonical text of frame and
boxes), then apply 1,000 random view operations (explode t in [0, 1], readable on/off, section x/y at random positions,
overlay changes, selections, variant toggles that rebuild a new model) and check that every model's `geometry_key` equals
a fresh build from the same inputs and that the original's is unchanged. Picking the same screen point at t = 0 and
t = 1 returns the same instance id when that instance is under the point in both; a field lookup returns the same cell
at any t. The page recomputes the assembly's `geometry_sha256` and refuses a mismatch. In the browser,
`__package3d.facts().geometryKey` is identical before and after a scripted explode, section and orbit session. Pass:
all.

**AC-13 Units convert exactly once** (node). The model-mode interposer edge of 45 mm appears as `0.045` m in the GLB
accessor bounds (x and the glTF z axis), and a 150 µm chip layer as 0.00015 m in y; the RenderModel holds 45 and 0.15
(mm). A static scan finds no `* 1000`, `/ 1000`, `1e-3` or `1e3` length conversion outside `quantity.mjs` and
`scripts/lib/glb.mjs`. Adversarial: a test double that converts twice (0.000045) or never (45 in the GLB) fails.
Pass: all (A#57059).

**AC-14 Stable instance ids** (node). Every id matches the grammar of SPEC.md §5.0 and is unique; every id of the
previous release is present or in `retired_ids`; no retired id is reused; GLB node names are unique and equal the ids,
and `extras.instance_id` repeats them (glTF names are not relied on). Adversarial: reorder the instances in the
source → identical ids and an identical `geometry_sha256` only if boxes are unchanged (ids are authored, not positional);
duplicate an id → refused. Pass: all.

**AC-15 Section parity** (node, browser). For the same model, plane and display state, the 3D cap rectangles and the
SVG fallback rectangles come from the same `sectionAt()` call: node compares them exactly; the browser compares counts
and ids (L3:ACCEPTANCE A-11). Pass: equal.

## Model manifest and layouts

**AC-16 The model manifest matches the generator** (python). For every fixture: the 6 LCF layers' thickness,
resistivity and heat capacity equal the generated `samplelayers.lcf` (main:sundai_tap/passive_interposer.py:135-149);
the bump-mix materials equal the generated floorplan units (:37-48); halo widths equal the generated `Ubump_*` units;
`s_spreader = 2 × interposer` and `s_sink = 2 × s_spreader` in the generated config (:151-165); `-model_secondary 0`
(main:sundai_tap/util/hotspot.config:48); the config files' sha256 equal the pinned values. A process spy shows no
HotSpot binary ran. Pass: all equal; zero solver processes.

**AC-17 Layout identities and separation** (node). For each served layout, `scripts/package3d.mjs data` recomputes
`content_sha256` from the source's `identity.canonical` with verify-core.js `parseRaw` and `canonical`
(main:web/public/verify-core.js:5-6, :14, :103) and it equals the stored value and the README table
(main:docs/sentilab/references/README.md:61-68); raw and 0.5 mm variants have different ids and hashes; no served
layout carries paper temperatures, round-trip plans or validation points. Adversarial: parse with `JSON.parse` and
re-serialise → the hash differs (`45.0` vs `45`), proving the build does not do that; move one die by 0.0001 mm in a
copy → the build refuses. Pass: all.

## Results bound to receipts

**AC-18 Every result value names its statistic, receipt and label** (node). For a signed replay: J has statistic
`chip_layer_grid_max` (metric `peak-chip-c`), W has `wire_proxy_weighted_manhattan` (metric `weighted-manhattan-mm`)
and is shown as `wire proxy (mm)`, centre temperatures have `chiplet_centre`; each value carries the measurement's
receipt (seq, event id, envelope hash), the evaluator identity, validity and `as_of_seq`; `receipt_completeness` reads
evaluator identity yes, geometry signed yes, input hashes `unnamed`, argv `absent`, power trace `in_unnamed_list`, field
`absent` for producer rows of today (main:sentilab_core/conductor.py:342-346). Adversarial: an unknown `metric_id` →
the value is refused (`statistic_unknown`), never shown; W and J are never put in one column, compared or differenced;
a caption calling W "routed" is impossible because captions come from `STATISTICS`. Pass: all.

**AC-19 Results sit only on the geometry they were signed with** (node, browser). The result RenderModel's chiplet
boxes equal the signed `values.geometry` of the candidate (scene.mjs readGeometry), on the stack of the run's own
`run.family`; `matchReference()` reports a reference only when every centre and footprint is within 1e-6 mm and every
rotation equal. Adversarial: a candidate 0.0001 mm off the raw reference → no match; a candidate equal to the 0.5 mm
variant → matched to `snap0p5`, never to `raw`; a run whose family is `ascend910` (50 mm) is never drawn on the 45 mm
stack. Pass: all (X6).

## Fields (fixtures until P1-P4 land)

**AC-20 Only verified, named artifacts are fetched** (node, browser network log). `fieldRefs()` returns only hashes from
applied measurement `node.create` envelopes inside the verified prefix. Hashes after K, in rejected events, in a replay
file's other fields or in unverified rows are never requested; replay vector V8 extended with a field at seq 9 makes
zero requests for it (L3:ACCEPTANCE A-03). In production before P1-P4 the page makes zero artifact requests and shows
"No field in this run's receipts". Pass: requested set ⊆ allowlist.

**AC-21 Bad frames are refused, not rendered** (node). For each case `checkFieldArtifact` returns `{ ok: false, error }`,
the texture updater is never called (spy) and the previous texture bytes are unchanged:

| Case | Error |
|---|---|
| bytes one bit off the signed hash | `hash_mismatch` (nothing decoded first) |
| 4 MiB + 1 byte | `too_large` |
| invalid UTF-8, a BOM, truncated JSON | `malformed` |
| another format string | `format` |
| binding names another run, measurement or evaluator (including the fixture identity on a withdrawn envelope: laundering) | `binding_mismatch` |
| an input source hash (`samplelayers.lcf`, `new_hotspot.config`, `sample.ptrace`) missing or not in the envelope's `artifact_hashes` | `binding_mismatch` |
| rows, cols or layers differ from the pointer; a layer one value short; 129 rows; 17 layers; `row0` missing | `dims` |
| a string, `null`, `1e400` | `out_of_range` |
| a value below absolute zero or above the scene bounds after conversion (scene.mjs:92-98) | `out_of_range` |
| unit missing or `F` | `unit_not_supported` |

A layer table that differs from the model manifest is accepted and listed in `stack_differs_from_manifest`. The
orientation pair (one hot cell at row 0 / column 0 declared `row0: "top"` vs `"bottom"`) renders at the upper-left vs
lower-left (L3:ACCEPTANCE A-04). Pass: every row, plus the pair.

**AC-22 The field is the solver's grid on the solver's layer, on one declared scale** (node, browser). `colourLut()` is
built only from `heatColor()` and stays within 1/255 of it over 200,000 temperatures on scales 10, 80 and 400 wide;
adjacent cells render with a hard edge (NEAREST); the legend names the grid and the solver layer; stepping the playhead
does not change the legend ticks; grid layers 6 and 7 are drawn over the interposer extent only and say so; no code
path builds a field from centre temperatures (L3:ACCEPTANCE A-07). Pass: all.

## Live and replay

**AC-23 The mode chip is the Package view's** (node, static). `package3d.js` never computes LIVE or STALE (static
check); driving the same live vectors the Package view's tests use, the room shows the identical mode text for every
poll (L3:ACCEPTANCE A-05). Pass: identical sequences.

**AC-24 A disconnect shows STALE** (node). Rows deliver a candidate whose lifecycle reaches `simulation_pending`; the
next poll throws (transport). Within that poll: mode `STALE · transport`, solve chip `solve status unknown (feed STALE ·
transport)`, never `solving`; the last verified values stay, labelled, with their `as of seq`. After recovery and K
growth: `LIVE · progress N s ago`, and `solving` again only if the verified lifecycle still says so. No growth for 60 s
after catch-up: STALE. Catching up a long backlog never shows LIVE. A doorbell (if built) firing repeatedly with no new
rows never makes the mode LIVE. Pass: the reference trace.

**AC-25 A shrinking prefix takes fields with it** (node, browser). A late signed conflict drops K: within that poll the
mode is `STALE · chain broken`, fields named after the new K leave the GPU and the cache, in-flight fetches for them
abort (spy), and `__package3d.facts().fieldAsOf <= K` (L3:ACCEPTANCE A-06). Pass: all.

**AC-26 Real time means completed, signed results only** (node). Every shown value has an `as_of_seq` within the
verified prefix; the simulated-time line reads `Steady state · no simulated time axis`; pages, keepalives, duplicate
rows and backlog never change `as_of_seq` or count as a new result; a new verified result is announced once in the live
region; a field change is a single cut (no intermediate blended frame in a frame-by-frame capture). Pass: all.

## Site rules

**AC-27 CSP unchanged and unviolated** (node, browser). `web/src/csp.js` is byte-identical to origin/main and
`worker-csp.test.mjs` passes with its `EXACT` string unchanged (main:web/test/worker-csp.test.mjs:20, :47-49). In the
browser, through load, every mode, explode, section, overlays, live (fixture server), context loss and forced fallback:
zero `securitypolicyviolation` events and zero console errors. Static scan of the room's modules: no `eval(`,
`new Function`, `Function(`, `WebAssembly`, `createObjectURL`, `innerHTML`, `insertAdjacentHTML`, `outerHTML`,
`setAttribute("style"`, `.style.cssText`, `createElement("style")`, `insertRule`, or `new Worker(` with a `blob:` or
`data:` URL. Every network request is same-origin. Pass: all.

**AC-28 The site's own tests cover the page** (node). `/sentilab/package3d/` is added to `worker-csp.test.mjs`'s
`FILES` and path loop (:38-43, :57), to `worker-boot.mjs`'s page list (:62), to the notice test (AC-02); public-names
and control-bytes pass over every new file; if a `.glb` is served, `.glb` joins control-bytes' `BINARY` list
(main:web/test/control-bytes.test.mjs:13) with its reason. Pass: all green.

**AC-29 Names** (static). (a) main:web/test/public-names.test.mjs passes. (b) A room-scoped scan over the page, its
data and `/agents/package3d/` finds none of the infrastructure vendor or mechanism names (rule 8): `cloudflare`,
`workers.dev`, `wrangler`, `azure`, `containerapps`, `container app`, `aws`, `amazon`, `s3`, `r2`, `vercel`, `netlify`,
`fastly`, `akamai`, `github pages`, `durable object`, and the model-vendor names already in `NAMES`
(public-names.test.mjs:20-26); negative controls are seeded and caught. (c) Under `names_policy: "generic"` the served
anatomy and twins contain none of the product, company or technology names on the reviewed generic-names list
(built in W2 from lane 1's sources and facts); under `"named"` (D1) the scan is replaced by the founder's allow-list.
Pass: all.

**AC-30 No MicroDuck or Pollen material** (static, review). Names scan as AC-29 (both are in `NAMES`); the room ships
no binary asset except generated GLB derivatives, each traceable to `writeGlb()` output by hash; the reviewed sources
cite only lane-1 facts. Pass: all (main:docs/sentilab/CHIPLET-VISUAL-SCOPE-DISPOSITION.md:7).

**AC-31 Viewing never starts a solver** (browser network log). Through a scripted session in every mode, every request
is a same-origin `GET` or `HEAD`; none goes to `/api/runs`; no request carries a body. Pass: all
(main:web/src/worker.js:51-56; A#57059).

## Layout and accessibility

**AC-32 320, 390 and 1280 px and 200% zoom, no clipping** (browser screenshots). Viewports 320x640, 390x844 (device
scale 3) and 1280x800 (1), plus 1280x800 at 200% zoom. For each: every mode; assembled; exploded; a part selected;
section on; an overlay on; Results with a withdrawn label; forced fallback. Checks (the deck exporter's checks,
scripts/export-deck-pdf.mjs:70-80): no element clipped where overflow is not visible; `scrollWidth <= innerWidth`; at
390 px the notice, content banner, legend and its state chip are visible without scrolling past the canvas; labels never
overlap and stay inside the canvas box; smallest text 11 CSS px. Pass: all, screenshots attached.

**AC-33 Keyboard, touch and reduced motion select the same things** (browser). The part tree, a canvas tap or click,
and keyboard navigation select the same instance id (`__package3d.facts().shown` and the selection agree); focus is
visible; the canvas has `role="img"` and a summary `aria-label`; mode changes and new verified results are announced
in a polite live region; with `prefers-reduced-motion: reduce` there is no auto-orbit, explode jumps, the playhead steps
without glides and nothing pulses (L3:ACCEPTANCE A-16). Pass: all.

## Performance and resilience

**AC-34 Budgets** (device, browser traces). Measured with the largest fixture (the anatomy assembly with every array,
and a results run with 8 layers at 64 x 64 once fields exist). Gating values are the stricter per row (D4):

| Budget | Lane 3 phone (A-10) | astra phone (A#57059) | Gate on the phone | Desktop (lane 3) |
|---|---|---|---|---|
| p95 frame time while orbiting or exploding | ≤ 33 ms | ≤ 33 ms (interaction, named phone) | ≤ 33 ms | ≤ 16.7 ms |
| triangles per frame | ≤ 300 k | ≤ 50 k | ≤ 50 k | ≤ 1.5 M |
| draw calls | ≤ 60 | ≤ 100 | ≤ 60 | ≤ 120 |
| interconnect instances | ≤ 6,000 | (follows from triangles) | `instanceBudget()` from 50 k (about 1,600 at 28 triangles each) | ≤ 60,000 |
| drawing buffer | DPR ≤ 2 | ≤ 1 megapixel | DPR ≤ 2 and ≤ 1,000,000 px | DPR ≤ 2 |
| render derivative per scene | not set | ≤ 2 MiB | GLB ≤ 2 MiB; served JSON per scene reported | reported |
| frames while idle | 0 after 1 s | not set | 0 after 1 s | 0 after 1 s |
| field texture memory | ≤ 4 MB | not set | ≤ 4 MB | ≤ 16 MB |
| JS heap after 10 min live | ≤ 60 MB, flat | not set | ≤ 60 MB, flat | ≤ 120 MB |
| new verified field to pixels, 8 x 64 x 64 | ≤ 30 ms off the main thread | not set | ≤ 30 ms off the main thread | ≤ 8 ms |
| first 3D frame after verification, cold, 4G | ≤ 2.5 s | not set | ≤ 2.5 s | ≤ 1 s |
| GL objects after a mode switch | not set | explicit disposal | back to the baseline count | same |

The reference phone is named by warden before W11; both sources' values are proposals, not measurements, until W11
measures them. Pass: every gate row on both classes; traces attached.

**AC-35 No WebGL, lost context, no WebCrypto** (browser). Chromium with WebGL disabled: the SVG cross-section, part
tree, detail panel, legend with its label state and notice appear; zero errors. `WEBGL_lose_context.loseContext()`
mid-session: the fallback appears within one frame with the selection and playhead kept, and GL object counts drop to
zero; `restoreContext()`: the 3D view returns with the same model, explode amount, section and field, with no refetch
(network log) and no re-verification (counter). An insecure origin: Results draws nothing with the Package view's
sentence; Anatomy and Model draw with the `file check unavailable` chip (D14). Pass: all.

## Agent twin

**AC-36 The twin matches the visual** (node, browser). Node: `twinOf()` on the same inputs as the page's
`buildRenderModel()` gives the same instance ids, boxes, bases, edges, flows and qualifiers; result twins give the same
values, statistics, labels and receipts as `resultView()`; `export3d` run twice gives byte-identical `twin.json`,
`twin.md` and `twin.glb`; the static `/agents/package3d/` files equal `scripts/package3d.mjs twin --check`'s output.
Browser: for each mode and a scripted set of states, every instance id, chip text, value text and label state in
`__package3d.facts()` is present in the twin for the same inputs, and the twin holds nothing the page would contradict
(same banner, same qualifiers). GLB: Khronos glTF-Validator reports 0 errors; metres, +Y up; its sha256 is the one in
`derivatives`. Pass: all.

**AC-37 The markdown twin carries the same qualifications** (node). `twinMarkdown()` output contains the banner
verbatim, every overlay qualifier, every `omitted` reason, every label text for every temperature (result twins), and
links that resolve to files under `/agents/package3d/`. It passes the public-names scan (origin/main's test scans
`.txt` but not `.md`, main:web/test/public-names.test.mjs:49; PR #66 adds `.md`, pr66:web/test/public-names.test.mjs:49;
until PR #66 merges, the room's own test applies the same scan to its `.md` files) and the AC-03 scanner for static twins.
Pass: all.

## Gated and content criteria

**AC-38 CAD trial gate** (review, before W16 starts). A written trial plan and result: exact tool identities and
versions from SPEC.md §10 (no merged identities; SolveCraft unresolved), Python and dependency pins, every resolved
dependency's license, the task list with failures and interventions in the denominator, per-instance bounding boxes
within 1 µm of the primitive model, names equal instance ids, glTF-Validator 0 errors, STEP as the export and GLB as a
hashed derivative, no CAD in the display path. Pass: reviewers approve the plan and the result.

**AC-39 SKETCH mode (only if D7 says build it)** (browser, node). Never °C or K; never on the canvas or legend of
verified data; never in a twin; banner `SKETCH · in-browser approximation · not evidence` visible at 390 px; runs in a
same-origin module Worker file; `temps.mjs` refuses its values until the label-rule owner adds a state with tests
(L3:ACCEPTANCE A-17). Pass: all.

**AC-40 Content provenance** (node, review). Every fact id in the served anatomy resolves to a lane-1 FACTS.jsonl
record (at `253ee4f7`) with a verbatim quote; every number in a served claim occurs in that record's `claim` or `value`
(number-preservation); the TAP-2.5D source record is completed (URL and the PDF sha256 shared by
main:docs/sentilab/references/README.md:79-80 and the lane-1 sealed manifest); the anatomy heat sink carries no model
value; forge signs the content review and astra the evidence review. Pass: all, with the two sign-offs recorded.
