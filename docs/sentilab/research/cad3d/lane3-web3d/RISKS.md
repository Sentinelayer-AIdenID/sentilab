# Package 3D: what could make it misleading, and how the UI prevents it

Lane 3 (web 3D + live simulation). Grounded in `origin/main` at `46791be360555d0e24b4ad5f906abafb71f07118`.
Ordered by how likely each is to mislead a viewer, then by how bad it would be. "Test" points at
ACCEPTANCE.md.

The existing pages already hold the line in 2D: the Package view says the stack is schematic and the colours
are "chiplet-centre temperatures from the solver; not a field" (package/index.html:86-101, 124-135;
scene.mjs:18-35), every temperature is labelled by one rule (temperature-label.mjs:1-19), and only the verified
prefix draws anything (package.js:157-161). A 3D view looks more real than a flat drawing, so each of these
needs a stronger guard, not the same one.

## R-01 The model reads as manufacturer CAD or a real product (high likelihood)

A shaded, exploded package with bumps and TSVs looks like an engineering model of a specific shipping part.
- Generic part names only (no vendor, product or trademark names; public-names.test.mjs scans every served
  file, including parts.json, the twin and any vendored code).
- Stylised, flat materials; no photoreal textures, logos, markings or brand colours.
- A chip inside the canvas, always visible: "Schematic model · not manufacturer CAD". The Honest limits dialog
  says where every dimension comes from.
- Every dimension in the info panel shows its provenance tag: evidence, solver, nominal (with citation) or
  schematic (ACCEPTANCE A-13).
- No MicroDuck/Pollen code, models, meshes or assets, per the owner's correction
  (CHIPLET-VISUAL-SCOPE-DISPOSITION.md:7); all geometry is generated from our own parts list.
- Test: A-13, A-14; review of parts.json citations.

## R-02 The thermal picture implies silicon validation (high)

- Every temperature carries the rule's qualifier ("simulated · pre-correction (withdrawn)", "simulated ·
  unvalidated"); even the accepted state says "Simulated with an accepted evaluator. Not silicon."
  (temperature-label.mjs:38-53). ACCEPTED is empty today (temperature-label.mjs:28), so nothing shown is
  validated.
- The page notice appears whenever any shown temperature needs it (package.js:280-283 rule, reused).
- No "measured" wording for simulated values anywhere in the 3D copy.
- Test: A-01.

## R-03 A withdrawn or unvalidated field is shown as a clean result (high; screenshots travel)

The live feed today signs with the withdrawn HotSpot 7 build (the `LIVE_HS7` identity in the label tests), so
any live field would be withdrawn.
- The label is taken from the verified envelope's `semantics.evaluator_version`, never from the artifact's own
  claim; a mismatch refuses the artifact (blocks laundering a withdrawn field as the fixture's "illustrative").
- The state is drawn into the pixels: withdrawn fields hatched, unvalidated stippled, so a canvas-only crop still
  shows it. The legend header and the state chip sit inside the canvas wrapper.
- `temperature-label.mjs hasTemperature()` counts only J and centre temperatures (temperature-label.mjs:142); a
  measurement carrying only a field would not raise the page notice. The rule must learn `values.field`, with a
  test, before fields ship.
- Test: A-01, A-02, A-04 (binding_mismatch).

## R-04 A false continuous heatmap (high) [V13]

Interpolating chiplet-centre temperatures across a die, or across the package, would invent a field. Smooth
bilinear filtering of a coarse 16 × 16 or 32 × 32 grid would imply resolution the solver doesn't have.
- A field is drawn only from a verified grid artifact. Without one, chiplets keep today's one-colour-per-chiplet
  rule (render.mjs:5-9) and the "not a field" basis text.
- Nearest filtering: one flat colour per solver cell; the legend states the grid and cell size.
- No code path builds a field from `center_temps` (static test).
- Test: A-07.

## R-05 The field is drawn on the wrong layer, flipped, or misplaced (medium)

The solver models 8 layers (6 from the generated layer file plus spreader and heat sink;
tap_oracle_worker.py:91-92, passive_interposer.py:144-149), each a homogenised slab. The anatomy has many more
parts. A field painted on the wrong part, or mirrored, would be wrong in a way nobody can see.
- Field sheets are drawn per SOLVER layer, at the solver's layer height, over the grid's declared extent, and
  titled with the solver's layer name from the artifact. Anatomy parts are mapped to a solver layer only through
  parts.json `solver_layer`; unmapped parts are labelled "not in the thermal model" when a field is shown.
- Individual bumps are never coloured as if simulated: the solver's C4 and microbump layers are homogenised
  "underfill with bumps" slabs (passive_interposer.py:145-147). The info panel says so.
- Orientation is declared in the artifact (`row0`) and tested with an asymmetric fixture.
- Test: A-04 (orientation), A-07.

## R-06 Colour-scale tricks (medium) [F24]

Auto-scaling each frame makes a 0.3 °C change look dramatic; per-layer scales make a cool heat sink look hot.
- One fixed scale per run, rounded out and at least 10 °C wide (scene.mjs runFrame's rule), widen-only while
  live (playhead.mjs widenFrame). Never rescaled per frame. The legend states its basis and the rule.
- The legend is labelled with `labelForAll()` over every value that set it (an axis is a derived value,
  temperature-label.mjs:17-19).
- Test: A-07.

## R-07 "Live" overclaims (medium)

Viewers will read "real time" as "the chip is running now" or "the solver is mid-calculation".
- The 3D page uses the existing label rules unchanged (v0.6.2 rule 5): LIVE only with a poll within 5 s, K grown
  within 60 s after catch-up, and nothing after the prefix; ENDED for finished runs; STALE with a reason.
- Fields only from completed solves. Intermediate solver iterates are never shown: they aren't temperatures of
  anything.
- The field is stamped "as of seq K" and "behind" when it lags the playhead.
- "solving" comes only from a verified `simulation_pending` lifecycle while the label is LIVE; otherwise "solve
  status unknown".
- The contract's own known limit stays in Honest limits: a server can withhold a suffix and LIVE stays on
  (VIEW-ENVELOPE v0.6.2 line 130).
- Test: A-05, A-06.

## R-08 Animation implies physical motion or time (medium) [V06, V11]

- Glides between layouts stay display-only, as in the Package view (package/index.html:130), and happen only on
  a verified event. No idle effects (no shimmering heat, no fake convection, no pulsing without an event).
- Replays say REPLAY; any time compression is printed ("simulated time t; playback × k"). The current solver is
  steady state, so there is no simulated time axis to show today.
- Exploding is a view control, labelled "exploded; spacing not to scale".
- Test: A-16, the existing V06/V11 replay-label tests.

## R-09 Exaggerated or sampled geometry is read as real (medium)

Real layer thicknesses span about four orders of magnitude (the solver's microbump layer is 10 µm, its
substrate 0.2 mm: passive_interposer.py:144, 147), and microbump counts can run to six figures.
- Thin layers are thickened to a minimum visible size only with the chip "thin layers thickened for
  visibility"; a "true scale" toggle shows real proportions; the info panel shows true thickness.
- Interconnect arrays are sampled on a lattice with "1 of k² sites drawn; N total (nominal)".
- Test: A-13.

## R-10 The in-browser sketch solver is mistaken for verified results (medium, only if built)

The task suggests labelling it "illustrative". In our rule, "illustrative" means exactly the bundled fixture,
and its text is "illustrative · no solver ran" (temperature-label.mjs:24-25, 48-50). That text would be false
for a solver that did run, so it must not be reused.
- The sketch shows a dimensionless relative field (no °C), in its own mode with its own banner and a visibly
  different colour map, never on the same canvas or legend as verified data, never exported to the twin.
- Any numeric output waits for the label-rule owner to add a state, with tests.
- Test: A-17.

## R-11 Supply chain: third-party code on a verifier page (medium, only under the three.js alternative)

Today the verifier pages run only our own code, and the recommended renderer keeps it that way. If the three.js
alternative is chosen, a vendored library runs in the same realm as the signature checks.
- Only the new 3D page loads it; the Lab view, Package view and verify page stay library-free.
- Byte-identical copy of the npm tarball files (three@0.187.0, `dist.integrity` verified: evidence/web-01),
  hash-pinned in a test; upgrades are reviewed diffs. Loaded with a dynamic import only after the first
  verification completes.
- Meaning never passes through it: labels, numbers, state chips and the legend are our DOM, from pure modules.
- Hardening option for either renderer: run it in a module Worker with OffscreenCanvas (WebGL2 there from Chrome
  69, Firefox 105, Safari 17: evidence/extra-01), so drawing code can't touch the DOM or the verifier at all.
- Test: A-12, A-14.

## R-12 A chain break after a field is shown (low likelihood, high impact)

- Every verification change goes through the same reconcile path as the Package view (playhead.mjs:1-13): when K
  drops, fields named after K are removed from the GPU and the cache at once, fetches are aborted, and the label
  is "STALE · chain broken".
- Test: A-06.

## R-13 Phone performance degrades into wrong pictures (low)

Dropped frames are harmless; half-drawn scenes, missing layers or a mis-sorted transparent lid are not.
- Budgets (A-10); transparency only on the lid and only as an outline-plus-low-alpha style; on WebGL2 failure or
  context loss, the 2D cross-section with the same labels, never a partial 3D scene.
- Test: A-10, A-11.

## R-14 Agent twin drifts from what the page shows (low)

- The twin is generated by the same `buildModel()` from the same verified inputs (parity test), carries the same
  label texts, and is byte-reproducible.
- Test: A-15.

## R-15 Accessibility gaps hide state from some users (low)

- The part list, live region and keyboard controls carry everything the canvas shows; label states are text,
  not colour alone.
- Test: A-16.
