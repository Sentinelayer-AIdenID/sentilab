# Package 3D: acceptance criteria

**Companion to SPEC.md v0.2 (2026-10-31).** Each criterion says how it is tested, what passes, and the adversarial
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
- **device**: D4's named emulation on the build box (Chromium mobile emulation at 412 x 915 CSS px, DPR 2, 4x CPU
  throttling), every result labelled "emulated, not a phone" (the GPU is not throttled), traces attached to the PR;
  Carter's own phone is the real-device check, at the screenshot gate.

Gate: no phase is done until its listed ACs pass (SPEC.md §9). The top gate for any public release of the page is
AC-01 to AC-06, AC-12, AC-20 to AC-27, AC-32, AC-34, AC-36, AC-41 and AC-46 (a) to (c). The product gate is separate:
Carter approves the rendered page, from real-browser screenshots, before any deploy (SPEC.md §11).

## Temperatures and labels

**AC-01 `formatTemp` refuses anything but the rule's labels** (node). `formatTemp(v, label)` throws for any `label`
that is not one of the frozen `LABELS` objects (main:web/public/temperature-label.mjs:38-53): a structurally identical
copy, `{ ...LABELS.accepted }`, `null`, a string, `undefined`. It throws for `NaN`, `±Infinity`, a numeric string and
`null` values. Pass: every case throws; the four real labels format. (A serialized record reaches `formatTemp` only
through `resolveLabel()`: AC-06.)

**AC-02 No temperature text outside `temps.mjs`** (static). In `web/public/sentilab/package3d/*.{js,mjs}`: no
`toFixed(` outside `temps.mjs` and `quantity.mjs` (non-temperature quantities), no `°C`, `℃` or `degC` literal outside
`temps.mjs` (one exception: the adopted `field-validator.mjs`, while its sha256 equals AC-46 (a)'s pin, compares the
unit alias `°C` and never shows it), no `fillText`/`strokeText` (no canvas text at all), no import that bypasses
`temps.mjs` to format a value. The page is added to the existing "every page takes its notice and labels from this one
module" test (main:web/test/temperature-label.test.mjs:320-341): `package3d.js` gets `NOTICE` through `temps.mjs` from
`../../temperature-label.mjs`, holds no copy of the notice text, and `index.html` has the exact slot
`<p class="wnotice" id="wnotice" role="note" hidden></p>`. Pass: zero hits; the extended test passes.

**AC-03 Static content holds no temperature** (static). The scanner of PSEUDOCODE §8 (`TEMP_PATTERN`, `TEMP_KEY`) runs
over every string and every key of `web/public/sentilab/package3d/data/*.json`, every static file under
`web/public/agents/package3d/` except result twins, and the model-stack and anatomy sources in
`docs/sentilab/package3d/`. Unit fields are checked against the unit list (no temperature unit). Adversarial: seeded
copies containing `47 C`, `300.5 K`, `61 °C`, `99°C`, `-12 degC`, `0.7 K rise`, `12 kelvin`, `33 ºC`, `0.04 °C·cm²/W`
and the keys `silicon_85C`, `silicon_at_100C` are each caught; `4 K*mm2/W`, `0.039 K/W`, `5 K·mm²/W`, `117.5 W/(m*K)`,
`C4 bumps`, `4 C4 rows`, `10,000-30,000`, `2,778 W/(m²·K)`, `HBM3E 12-high` stay clean. The model stack's
`boundary.temperature_inputs` entries all have `rendered: false` and carry no value, and every temperature-valued
`omitted` entry names its role (`model_input`, `material_condition`, `published_limit`: D2). Pass: real files clean,
every seeded case caught, every clean case clean.

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

**AC-05 The figure carries the words; the pixels carry the pattern** (browser; fields only, fixtures before W14). Two
separate checks. (a) Pixel probes over the canvas pixels only: with a withdrawn field shown, luminance along a line
across a sheet alternates with the hatch period; unvalidated shows the stipple; illustrative and accepted show no
pattern; unpatterned pixels at known cells equal `heatColor(t, scale)` within ±3/255 per channel. These probes test
hatching and stippling and nothing else. (b) The export boundary (SPEC.md §6.5), at 320, 390 and 1280 px and at 200%
zoom: a screenshot of `figure#p3d-figure` holds the canvas, the content chip, the label-state chip (whose text equals
the legend's label state), the legend and the source line (mode chip text, run id, `as of seq S`); each of these
elements' bounding box lies inside the figure's box, is not clipped, and wins a DOM hit test at its centre (the
canvas does not cover it); `__package3d.facts().figure` reports the same texts. Adversarial: a test double that moves
the legend or the source line out of the figure, or positions a chip outside the figure's box, fails (b); a static
scan finds no `toDataURL(` or `toBlob(` in the room's modules (no canvas-only image export). Pass: (a) and (b)
(L3:ACCEPTANCE A-02, narrowed: no claim rests on a canvas-only crop).

**AC-06 Labels survive serialization; identity is resolved, never assumed** (node). For result twins (CLI `export3d`
and the dialog), the full path runs for each identity of AC-04 (withdrawn HotSpot-7, the corrected evaluator, the
fixture, none): `resultView()` → `twinOf()` → `twinJsonText()` → UTF-8 bytes → `readTwin()` → `twinMarkdown()`. In the
JSON every value with `unit: "degC"` carries `evaluator_identity` and a `label` record with exactly the keys `state`,
`text`, `short` and `title`, each equal to `labelFor(evaluator_identity)`'s; after reading, `resolveLabel()` returns
an object `===` `LABELS[state]` (the canonical in-process object, not a copy); the markdown shows each temperature as
`<value> °C <short>` in one cell; refused values appear only in `refused`, never as numbers
(main:scripts/sentilab-scene.mjs:17); the same inputs give byte-identical JSON and markdown. Adversarial, each refused
with `label_mismatch` (the value never formatted; `readTwin` all or nothing): `state` changed (withdrawn to
unvalidated); one character of `text`, `short` or `title` changed; a trailing space or a case change (no trimming or
folding); an extra key (`notice`); a missing key; a non-string field; `evaluator_identity` changed with the label left
(the withdrawn identity replaced by the fixture's, and the reverse); in the page path, a value whose
`evaluator_identity` differs from the verified identity of its measurement; `twinOf()` given a value without a label
throws. A structurally identical copy passed straight to `formatTemp()` still throws (AC-01). A twin whose identity
and label were both edited consistently is caught by re-running `export3d` on its pinned replay and comparing bytes
(AC-36), not by the reader. Pass: all.

**AC-07 Identity edge cases** (node). Reuse the per-value provenance vectors through `results.mjs`: J from the applied
withdrawn create is labelled withdrawn, not illustrative; J and centre temperatures from different measurements keep
separate labels (`sourceTags`, temperature-label.mjs:139-144); every create rejected means no identity, so unvalidated.
Pass: the same labels the Package view computes for the same prefix (per-value-provenance.test.mjs:73-91).

## Three kinds of content

**AC-08 Separation in data and models** (node, static). `buildRenderModel()` refuses any call that supplies inputs of
two kinds (`mixed_content`). `anatomy.json` and the assembly contain no key matching `our_model`, `in_our_model` or
`solver_layer`, and no quantity with basis `model` or `evidence`; `model-stack.json` contains no anatomy quantity
(only `stands_for` ids); a result RenderModel whose run inputs are not verified (`run_inputs_verified: false`,
SPEC.md §5.6) draws a schematic stack with every box `render_hint` and the note "this run's layer inputs are not
verified; schematic stack" (and "no model for family <f>" without a family match), and never an anatomy thickness or
the family manifest's thicknesses. Adversarial: delete the model stack file → the schematic note, not lane-1 numbers;
inject an anatomy thickness into a result build → refused; a family match with unverified inputs → schematic, not
the manifest's thicknesses. Pass: all (X1 to X5).

**AC-09 Banners and chips match their kind** (browser, node). In each mode the content banner and the canvas chip are
the exact strings of SPEC.md §3, and the twin's `status_text` for that kind is the same string (schema const). Model
mode shows no result value; Results shows no flow arrows; the compute die's conceptual inset carries the chip
`conceptual · not a floorplan` and a fact id on every block (D13); Anatomy shows no result value and no model number
outside the "In our model" line. Pass: string equality, and zero result or model values in the wrong mode.

## Quantities, unknowns, ids

**AC-10 Quantity rules** (node). `readQuantity` refuses: `unknown` with a number; `render_hint` without a value or
`hint_basis`; `sourced` without facts or without any number; `derived` without `derivation`; `model` without
`model_ref`; `evidence` without `evidence_ref` or without a value; `min > max`; `value` outside `[min, max]`; a
non-finite number; a fact id not in the manifest; a temperature unit; a bare temperature inside `derivation`,
`hint_basis`, `note` or `display.derivation`; a `display` on anything but a `sourced` quantity with `value: null`; a
`display` without `basis: "render_hint"`, a finite value or a derivation; a `display.value` outside `[min, max]`. The
schema blocks of SPEC.md §5.1 refuse the same set where the schema language can say it. Pass: every case refused with
its code; valid cases accepted.

**AC-11 An unknown dimension renders as unknown** (browser, node). The lid's thickness (no source in lane 1:
L1:REPORT §3.3) shows `not sourced · drawn at 1.000 mm (display only: …)` with the hint's reason; the die-side
capacitors' count shows `unknown`; the twin carries `value: null` with `basis: "unknown"` or the hint with
`basis: "render_hint"`. TIM1 (lane 1: a sourced 20 to 50 µm range with no typical value, L1:parts.json
`tim1.thickness_um`) keeps `basis: "sourced"`, `value: null`, `min` and `max` in the served anatomy and in the twin;
drawn, it sits at the reviewed overlay's `display` representative with the instance's thickness basis `render_hint`,
and the panel reads `20–50 µm · sourced [facts] · drawn at X (display only: <derivation>)`. An instance with an
unknown size and no hint is undrawn (SPEC.md §5.3): it is listed
`not drawn · size unknown` in the part tree, keeps its id, parent and every edge that names it in the panel and the
twin (with `dims` null where unknown and no box), and is absent from the canvas, `RenderModel.boxes`, `bounds`,
`pick()`, `sectionAt()` and every field lookup. Adversarial: a build that silently fills an unknown (for example copies
the model's 1 mm spreader into the anatomy lid as `sourced`) fails `readAnatomy`; an undrawn instance carrying any
`box` (a placeholder, a zero-size or a 1 mm cube), `basis` or `array` is refused by the schema and by `readAssembly`;
a `drawn: true` instance without a box is refused; an undrawn instance whose every dimension is drawable is refused
(a drawable part is drawn); adding an undrawn part leaves `bounds` unchanged, and a pick ray through the space it
would occupy returns the drawn part behind it or `null`; a data build whose served `value` differs from lane 1's
`typical` (for example TIM1's midpoint written into `value`) is refused by `scripts/package3d.mjs data`, and an
assembly that declares a range's drawn thickness `sourced` is refused by `readAssembly`; `drawnMm()` on a range
without `display` returns `null` (no midpoint is invented), so that part is undrawn. Pass: all.

**AC-12 Explode never mutates geometry** (node, browser). After `buildRenderModel()`, `Object.isFrozen` holds for the
model and every nested object; a write in strict mode throws. Record `geometry_key` (the geometry preimage of SPEC.md
§5.0 over the model's instances), then apply 1,000 random view operations (explode t in [0, 1], readable on/off,
section x/y at random positions, overlay changes, selections, variant toggles that rebuild a new model) and check that
every model's `geometry_key` equals a fresh build from the same inputs and that the original's is unchanged. Picking
the same screen point at t = 0 and t = 1 returns the same instance id when that instance is under the point in both; a
field lookup returns the same cell at any t. The page recomputes the assembly's `geometry_sha256` and refuses a
mismatch. In the browser, `__package3d.facts().geometryKey` is identical before and after a scripted explode, section
and orbit session. Pass: all.

**AC-13 Units convert exactly once** (node). The model-mode interposer edge of 45 mm appears as `0.045` m in the GLB
accessor bounds (x and the glTF z axis), and a 150 µm chip layer as 0.00015 m in y; the RenderModel holds 45 and 0.15
(mm). A static scan finds no `* 1000`, `/ 1000`, `1e-3` or `1e3` length conversion outside `quantity.mjs` and
`scripts/lib/glb.mjs`. The W4 vector (C#57232; AC-45 (a)): a chiplet with centre (12.5, 17.25) mm and size 8 x 5.5 mm
sits at lower-left (8.5, 14.5) mm in the RenderModel, and its GLB node at x = 0.0085 m and glTF z = -0.0145 m (the +Y-up
rotation). Adversarial: a test double that converts twice (0.000045) or never (45 in the GLB) fails. Pass: all
(A#57059).

**AC-14 Stable instance ids and an order-free geometry hash** (node). Every id matches the grammar of SPEC.md §5.0
and is unique; every id of the previous release is present or in `retired_ids`; no retired id is reused; GLB node
names are unique and equal the ids, and `extras.instance_id` repeats them (glTF names are not relied on). The geometry
preimage is exactly SPEC.md §5.0's (`sentilab-geometry/1`). Golden fixture: the assembly frame of SPEC.md §5.3 and
these three instances, in this source order (labels, bases and dims take any valid values: they are outside the
preimage):

```text
{"id":"golden/interposer_silicon#1/interposer_tsv#1","type":"interposer_tsv","parent":"golden/interposer_silicon#1","variants":["all"],"drawn":true,"box":{"x0":2,"x1":4,"y0":2,"y1":5,"z0":0,"z1":0.1}}
{"id":"golden/tim1#1","type":"tim1","parent":null,"variants":["lidded"],"drawn":false}
{"id":"golden/interposer_silicon#1","type":"interposer_silicon","parent":null,"variants":["lidless","lidded"],"drawn":true,"box":{"x0":0,"x1":30,"y0":0,"y1":25,"z0":0,"z1":0.1}}
```

`geometryPreimage()` returns exactly these 735 bytes, and `geometry_sha256` is
`0480119fc57ab1c48d8010c11c695ae593bf9b3775c6234a2b3cb1cd23fffbe9`:

```text
{"frame":{"length_unit":"mm","origin":"interposer lower-left corner, on the interposer's bottom face","x":"right","y":"up in plan view","z":"out of the board, toward the cooler"},"instances":[{"array":null,"box":{"x0":0,"x1":30,"y0":0,"y1":25,"z0":0,"z1":0.1},"drawn":true,"id":"golden/interposer_silicon#1","parent":null,"type":"interposer_silicon","variants":["lidded","lidless"]},{"array":null,"box":{"x0":2,"x1":4,"y0":2,"y1":5,"z0":0,"z1":0.1},"drawn":true,"id":"golden/interposer_silicon#1/interposer_tsv#1","parent":"golden/interposer_silicon#1","type":"interposer_tsv","variants":["all"]},{"array":null,"box":null,"drawn":false,"id":"golden/tim1#1","parent":null,"type":"tim1","variants":["lidded"]}],"v":"sentilab-geometry/1"}
```

Adversarial, each against the golden fixture: (a) the instances in reverse order, and one instance's `variants`
reversed → identical bytes and hash; (b) one box face moved by 0.001 mm, an instance re-parented, a drawn instance
made undrawn, an instance added or removed (drawn or undrawn), a type changed or a variant membership changed → a
different hash; (c) only a `label`, `note`, `basis`, `dims` or fact list changed → the same hash (the file pin still
changes); (d) explode, readable thickening, a section plane, a variant switch or an orbit applied to the RenderModel →
no preimage input changes (the function takes no view state); (e) a duplicated id → refused before hashing. Pass: all
(the golden bytes and hash were produced with main's `canonical()` while writing this version, and re-hashed
independently: TRACE.md section 5).

**AC-15 Section parity** (node, browser). For the same model, plane and display state, the 3D cap rectangles and the
SVG fallback rectangles come from the same `sectionAt()` call: node compares them exactly; the browser compares counts
and ids (L3:ACCEPTANCE A-11). Pass: equal.

## Model manifest and layouts

**AC-16 The model manifest matches the generator** (python). Every fixture is generated in its own fresh directory
(C5). For each: the 6 LCF layers' thickness, resistivity, heat capacity, power and lateral flags equal the generated
`samplelayers.lcf` (main:sundai_tap/passive_interposer.py:135-149); every region of all six generated floorplans
carries the resistivity, heat capacity and power of its class in the manifest's per-layer `units` records, which the
W4 check records from the generated files (sizes and positions are checked against the layout, halos and edge
strips), the floorplan's values
taking precedence over the LCF defaults (C6; main:sundai_hotspot/temperature_grid.c:387-400): layer-4 `Ubump_*`
regions are silicon with zero power, `Edge_*` regions use the bump mix, the C4 and interposer slabs carry their
mixtures (:59-74), and whitespace is the underfill `fill_space` writes (main:sundai_tap/util/fill_space.py:18-20,
:157-165), each recorded from the files and never inferred from a name; halo widths equal the generated `Ubump_*`
units; the resolved config has `s_spreader = 2 × interposer`, `s_sink = 2 × s_spreader`, `r_convec` by the writer's
own expression and `-model_secondary 0` (:151-165; main:sundai_tap/util/hotspot.config:48), and the spreader and sink
thickness, conductivity and volumetric capacity of manifest layers 6 and 7; each fixture's config sha256 equals its
own pin, checked inside the loop; the generated LCF and resolved config hashes equal `expected_inputs`. A second test
writes another fixture into a reused directory: the retained config's hash differs from that fixture's
`expected_inputs` (the stale case AC-41 (c) relies on). The W4 geometry vectors (C#57232; AC-45 (a)-(d)) run as unit
cases of the same comparison. A process spy shows no HotSpot binary ran. Pass: all equal; zero solver processes.

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
receipt (seq, event id, envelope hash), the evaluator identity, validity and `as_of_seq`; for a row shaped as today's
producer code writes it (a named `record.input_hashes` in the signed body, the unnamed `values.artifact_hashes`, no
argv: main:sentilab_core/conductor.py:337-347) `receipt_completeness` reads evaluator identity yes, geometry signed
yes, input hashes `named`, argv `absent`, power trace `named`, field `absent`; for a row with only the unnamed list it
reads input hashes `unnamed` and power trace `in_unnamed_list`. Adversarial: an unknown `metric_id` →
the value is refused (`statistic_unknown`), never shown; W and J are never put in one column, compared or differenced;
a caption calling W "routed" is impossible because captions come from `STATISTICS`. Pass: all.

**AC-19 Results sit only on the geometry they were signed with** (node, browser). The result RenderModel's chiplet
boxes equal the signed `values.geometry` of the candidate (scene.mjs readGeometry) in every case; the vertical stack is
the run's own only when `run_inputs_verified` (AC-41), and `family_match` is reported separately as reference
context; `matchReference()` reports a reference only when every centre and footprint is within 1e-6 mm and every
rotation equal. Adversarial: a candidate 0.0001 mm off the raw reference → no match; a candidate equal to the 0.5 mm
variant → matched to `snap0p5`, never to `raw`; a run whose family is `ascend910` (50 mm) is never drawn on the 45 mm
stack. Pass: all (X3, X6).

## Fields (fixtures until P1-P5 land)

**AC-20 Only verified, named artifacts are fetched** (node, browser network log). `fieldRefs()` returns only hashes from
applied measurement `node.create` envelopes inside the verified prefix. Hashes after K, in rejected events, in a replay
file's other fields or in unverified rows are never requested; replay vector V8 extended with a field at seq 9 makes
zero requests for it (L3:ACCEPTANCE A-03). In production before P1-P4 the page makes zero artifact requests and shows
"No field in this run's receipts". Pass: requested set ⊆ allowlist.

**AC-21 Bad frames are refused, not rendered** (node). Each case runs on a run with verified inputs (AC-41 (b)), with
a complete target and association record, and changes only what its row names. For each, the field's status is
`refused` with the adopted module's code (SPEC.md §5.7) or the host's (from `fieldRefs`, the feed or `checkField`),
the texture updater is never called (spy) and the previous texture bytes are unchanged:

| Case | Error |
|---|---|
| bytes one bit off the signed hash | `hash_mismatch` (nothing decoded first; the resolver never called) |
| 4 MiB + 1 byte | `too_large` (the feed, from `readBodyCapped`, before the module runs) |
| invalid UTF-8, a BOM, truncated JSON, trailing data, a duplicate member name (also under an escaped alias) | `malformed_json` |
| another format string, in the artifact or the pointer | `format` |
| (C4) a key missing or added at the top level (for example a v0.2 `producer` block, or no `unit` key) | `artifact_schema` |
| (C4) a key missing or added in `binding`, in `grid` or `extent_mm` (for example `extent_m` for `extent_mm`), in a layer record, or among the four named `sources` | `binding_schema`, `grid_schema`, `layer_schema`, `source_schema` |
| a signed pointer (`values.field`) with a key added or missing, or a `sha256` that is not 64 hex | `pointer_schema` (`fieldRefs`, before any fetch) |
| (C1) a `null` or non-hash `candidate_hash` or `problem_hash`; an empty run, measurement or evaluator | `binding_schema` |
| binding names another run, measurement or evaluator than the target (including the fixture identity on a withdrawn envelope: laundering) | `binding_mismatch` |
| (C1) the artifact's `candidate_hash` names another candidate's layout, or its `problem_hash` another problem, than the target's signed `record.binding.candidate_id` and `semantics.task_contract` | `binding_mismatch` |
| the stale-target replay: a valid earlier artifact with its valid earlier receipt, checked while the playhead selects a later run sharing its candidate, problem, model and producer | `binding_mismatch`; through a draft-shaped ref, `draft_target_conflict` before the resolver is called (AC-46) |
| two named source hashes swapped, or any differing from the association record's | `source_association_mismatch` |
| argv empty or not strings; argv differing from the record's (compared, never run) | `argv_schema`; `argv_association_mismatch` |
| (C2) a pointer in C over an artifact in K, or the reverse (the values are never converted) | `unit_mismatch` |
| unit `F`, `null` or any undocumented alias, in the pointer or the artifact | `unit_not_supported` |
| (C3) a layer index duplicated (3 twice), not an integer (`"four"`), negative or above 15; a layer record with a non-finite or non-positive thickness, resistivity or heat capacity, a non-boolean `powered`, no name or an unknown `source` | `layer_schema` |
| (C3) a layer missing (no 4, with pointer and artifact agreeing on seven), unexpected (8 in place of 7) or in another order than the association record's | `layer_identity_mismatch` |
| a layer record differing from the record's (name, thickness, material, `powered`, source) | `layer_association_mismatch` |
| rows, cols or layers differ from the pointer; a layer one value short; (C4) a 3 x 2 artifact under a 2 x 3 pointer (same cell count); a pointer with 0 rows, 129 rows or 17 layers | `dims` |
| (C4) in the artifact, `rows: 0`, a non-integer `cols` or 129 rows; `row0` not `top` or `bottom`; `map_mode` not `center` or `max`; `extent_mm` with a non-finite bound or a zero span | `grid_schema` |
| a grid, row origin or map mode differing from the association record's; (C4) an extent stretched to the spreader or sink outline while the record keeps the central grid | `grid_association_mismatch` |
| (C4) a registered extent that is not the verified central grid domain (artifact and record both stretched to a package outline) | `extent` (the host, after registration) |
| a string, `true`, `null` or an overflowing number (`1e400`) as a value | `nonfinite_value` |
| a value outside scene.mjs `BOUNDS.temperature_c` after conversion (scene.mjs:92-98) | `out_of_range` |
| an association record for another hash, with another identity than the target's, or malformed (an identity, the receipt `{ seq, event_id, hash }`, the grid, the layer table, the sources or argv) | `association_hash_mismatch`, `association_mismatch`, `association_schema`, `association_receipt` |
| a target hash identity present but malformed (a non-hash `model_hash`) | `target_schema` |
| a target run, measurement or evaluator that differs from the ref's, an empty one included | `draft_target_conflict` (`checkField`, before the module runs) |
| a ref or target that is not plain data (an accessor, a class instance, a sparse array) | `malformed_context` |
| bytes that are not a `Uint8Array`, or a view of a shared buffer | `invalid_bytes`, `shared_buffer` |

The module's `temperature_bounds_schema` and `reference_stack_schema` cannot arise from this host, which passes
scene.mjs's bounds and no reference table.

The artifact's layer table, equal to the association record's, is the authority for that result: it is never
relabelled or remapped to the family's manifest, and a malformed or ambiguous table is refused above (C3). Missing
association evidence is not a refusal: the field is unassociated (AC-41 (h)). The orientation case uses an asymmetric
basis, so that a swapped or flipped mapping cannot pass (A#57218): rows unequal to columns, a non-square extent, and
one marked cell off both diagonals and away from every corner. Declared `row0: "top"`, the cell renders, and
`cellAt()` picks it, at its expected centre; declared `row0: "bottom"`, at the vertically mirrored centre; a
transposed (rows for columns), flipped or corner-for-centre mapping lands elsewhere and fails; a row index equal to
`rows` is out of range (L3:ACCEPTANCE A-04, made asymmetric). The W4 fixture `asymmetric_zero_origin_mapper` supplies
the numbers (C#57232): 3 rows by 5 columns over 20 x 9 mm (cells 4 x 3 mm); the cell at row 0, column 3 has centre
(14, 7.5) mm and lower-left (12, 6) mm under `row0: "top"`, and centre (14, 1.5) mm under `row0: "bottom"`; row 2,
column 1 has centre (6, 1.5) mm; a vertical flip, (14, 1.5) under `top`, or the corner (12, 6) given as the centre
fails; row 3 is out of range. Pass: every row, plus the orientation case.

**AC-22 The field is the solver's grid on the solver's layer, on one declared scale** (node, browser). `colourLut()` is
built only from `heatColor()` and stays within 1/255 of it over 200,000 temperatures on scales 10, 80 and 400 wide;
adjacent cells render with a hard edge (NEAREST); the legend names the grid and the solver layer; stepping the playhead
does not change the legend ticks; grid layers 6 and 7 are drawn over the central grid (the interposer extent) only and
say so, with the rest of the spreader and sink outlines uncoloured and labelled `unmeasured` because the grid output
holds no peripheral-node values, and with the spreader and sink configuration's properties (C7); no code path builds a
field from centre temperatures or a centre value from a field (L3:ACCEPTANCE A-07); J (the warm oracle's max mapping)
and a gate-validation centre value are never put in one column or compared (A#57278). Pass: all.

## Live and replay

**AC-23 The mode chip is the Package view's** (node, static). `package3d.js` never computes LIVE or STALE (static
check); driving the same live vectors the Package view's tests use, the room shows the identical mode text for every
poll (L3:ACCEPTANCE A-05). Pass: identical sequences.

**AC-24 A disconnect shows STALE** (node). Rows deliver a candidate whose lifecycle reaches `simulation_pending`; the
next poll throws (transport). Within that poll: mode `STALE · transport`, solve chip `solve status unknown (feed STALE ·
transport)`, never `solving`; the last verified values stay, labelled, with their `as of seq`. After recovery and K
growth: `LIVE · progress N s ago`, and `solving` again only if the verified lifecycle still says so. No growth for 60 s
after catch-up: STALE. Catching up a long backlog never shows LIVE. A doorbell (if built) firing repeatedly with no new
rows never makes the mode LIVE. Terminal states (A#57218): with the run listed `finished` the chip reads `ENDED · run
finished`, a candidate still `simulation_pending` reads `no result (run ended)` and never `solving`, and a passing
transport failure stays ENDED; a frozen board (`STALE · chain broken`) and the terminal paging states (`stream
replaced`, `row too large`, `paging unsupported`) keep their labels over ENDED, stop polling and never show `solving`
(main:contracts/view-envelope-v0.6.2/VIEW-ENVELOPE.md:110, :120-123). Pass: the reference trace.

**AC-25 A shrinking prefix takes fields with it** (node, browser). A late signed conflict drops K: within that poll the
mode is `STALE · chain broken`, fields named after the new K leave the GPU and the cache, in-flight fetches for them
abort (spy), and `__package3d.facts().fieldAsOf <= K` (L3:ACCEPTANCE A-06). Pass: all.

**AC-26 Real time means completed, signed results only** (node). Every shown value has an `as_of_seq` within the
verified prefix; the simulated-time line reads `Steady state · no simulated time axis`; pages, keepalives, duplicate
rows and backlog never change `as_of_seq` or count as a new result; a new verified result is announced once in the
live region; a field change is a single cut (no intermediate blended frame in a frame-by-frame capture). Late results
(A#57218): a field fetch or check that completes after its result left the prefix, after a mode switch, after K
dropped below it or after the playhead moved to another result is discarded by the host's generation guard (its stamp
of epoch, view mode and the playhead's measurement, checked before the module is called and when it returns, against
the allowlist at the current cut: A#57404), whatever it returned, `verified` included, and never drawn, while K
growing alone never discards one; a verified result that arrives after the run is listed `finished` is shown with its
own `as of seq S` and announced once while the label stays ENDED; a result behind the playhead says `behind`; nothing
is ordered as newest by arrival time. Pass: all.

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
(public-names.test.mjs:20-26); negative controls are seeded and caught. (c) Under `names_policy: "generic"` (D1) the
served teaching copy (part and instance names, claims, explanations, labels, flow and edge text, the twins' prose)
contains none of the product, company or technology names on the reviewed generic-names list (built in W2 from lane
1's sources and facts); source records (`title`, `publisher`, `url`, `sha256`) keep usable citations and are exempt
from (c), never from (a) or (b) (D10). (d) A license inventory lists every vendored or copied file the room serves,
with its license and sha256, and matches the served files exactly (D10; for D5 option B, the MIT text and each
vendored core file). Pass: all.

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

**AC-34 Budgets, measured against targets** (device, browser traces). Measured by the plan of SPEC.md §6.11: the
workload (the anatomy assembly with every array, and a results run with 8 layers at 64 x 64 once fields exist), the
reference device (D4's named emulation) and its browser, and a desktop are named before measuring; preparation and
end-to-present are reported separately; the D5 pick is measured as a spike in W9.5 and as built in W11. The phone
column is root's initial tier (D4): prospective targets, not limits, measured on the named emulation (warden, #57424),
Chromium mobile emulation at 412 x 915 CSS px, DPR 2, with 4x CPU throttling, labelled "emulated, not a phone"; it
does not throttle the GPU.

| Measure | Lane 3 phone (A-10) | astra phone (A#57059) | Phone target (D4, or lane 3 where D4 sets none), emulated, not a phone | Desktop (lane 3) |
|---|---|---|---|---|
| p95 frame time while orbiting or exploding | ≤ 33 ms | ≤ 33 ms (interaction, named phone) | ≤ 33 ms (D4, #57424; lane 3, astra) | ≤ 16.7 ms |
| triangles per frame | ≤ 300,000 | ≤ 50,000 | ≤ 50,000 (D4) | ≤ 1,500,000 |
| draw calls | ≤ 60 | ≤ 100 | ≤ 60 (D4) | ≤ 120 |
| interconnect instances | ≤ 6,000 | (follows from triangles) | a setting: `instanceBudget()` from the 50,000 target (about 1,600 at 28 triangles each) | ≤ 60,000 |
| drawing buffer | DPR ≤ 2 | ≤ 1 megapixel | ≤ 1,000,000 px (D4), met by the settings DPR ≤ 2 and the pixel cap | DPR ≤ 2 |
| render derivative per scene | not set | ≤ 2 MiB | GLB ≤ 2 MiB (D4); served JSON per scene reported | reported |
| frames while idle | 0 after 1 s | not set | 0 after 1 s | 0 after 1 s |
| field texture memory | ≤ 4 MB | not set | ≤ 4 MB | ≤ 16 MB |
| JS heap after 10 min live | ≤ 60 MB, flat | not set | ≤ 60 MB, flat | ≤ 120 MB |
| new verified field to pixels, 8 x 64 x 64 | ≤ 30 ms off the main thread | not set | ≤ 30 ms off the main thread | ≤ 8 ms |
| first 3D frame after verification, cold, 4G | ≤ 2.5 s | not set | ≤ 2.5 s | ≤ 1 s |
| GL objects after a mode switch | not set | explicit disposal | back to the baseline count | same |
| preparation (fetch to first frame ready) and end-to-present (input or new result to presented frame) | not set | measured separately (A#57218) | reported, p50 and p95 | reported |
| bytes the renderer adds (raw, gzip, brotli), for the D5 pick | not set | not set | reported | reported |

The reference device is D4's named emulation (warden, #57424), and every result from it is labelled "emulated, not a
phone": the GPU is not throttled, so GPU-bound rows are the build box's GPU under a phone's CPU budget. Carter's own
phone is the real-device check, at the screenshot gate before deploy. Pass: every row measured and reported on both
classes against a named workload, device and browser, with traces attached; a missed target is recorded with its cause
and the three owners' disposition (D4), never silently relaxed. The renderer's own caps (DPR 2; 1,000,000 pixels on
phones) are settings, verified rather than measured.

**AC-35 No WebGL, lost context, no WebCrypto** (browser). Chromium with WebGL disabled: the SVG cross-section, part
tree, detail panel, legend with its label state and notice appear; zero errors. `WEBGL_lose_context.loseContext()`
mid-session: the fallback appears within one frame with the selection and playhead kept, and GL object counts drop to
zero; `restoreContext()`: the 3D view returns with the same model, explode amount, section and field, with no refetch
(network log) and no re-verification (counter). An insecure origin: Results draws nothing with the Package view's
sentence; Anatomy and Model draw with the `file check unavailable` chip (D14). Cleanup over 100 switches (A#57218):
100 consecutive mode switches (Anatomy, Model, Results with a field shown and an explode in each) return, after
every switch, the GL object count, in-flight fetches (abort spy), event listeners and timers to their baseline
(`__package3d.facts()`), leave one live RenderModel and no duplicate live-region entries, and keep the JS heap after
the 100th switch within 5% of its value after the first (forced garbage collection in the test browser). Pass: all.

## Agent twin

**AC-36 The twin matches the visual** (node, browser). Node: `twinOf()` on the same inputs as the page's
`buildRenderModel()` gives the same instance ids, boxes, bases, edges, flows and qualifiers (undrawn parts: the same
ids, parents, edges and null dimensions, and no box); result twins give the same
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

## Added in v0.2 (after root's review, A#57218, and the inputs since)

**AC-41 Family match is not input verification; validity is not association** (node). With TEST-key replays: (a) a
row shaped as today's producer writes it (a named `record.input_hashes`, no signed flags) whose family matches →
`family_match: match`, `reference` set, `inputs_evidence: named_map`, `flags_evidence: absent`,
`run_inputs_verified: false`, `stack_basis: schematic`; its J, W and centre values still show with their labels,
statistics and receipts, and the panel and twin label the family's manifest as reference context; (b) the same row
with signed flags, and `samplelayers.lcf`, `new_hotspot.config` and flags equal to the fixture's `expected_inputs` →
`run_inputs_verified: true`, `stack_basis: run_inputs`, the stack drawn from the run's inputs; (c) as (b) but with a
`new_hotspot.config` resolved for an older package size in a reused directory (same family, stale config) →
`input_differences: ["new_hotspot.config"]`, not verified, schematic; (d) as (b) with `-detailed_3D off` → that flag
listed, not verified; (e) a row with only `values.artifact_hashes` → `inputs_evidence: unnamed_list`, not verified;
(f) a family the manifest lacks → `family_match: no_match`, `reference: null`, schematic with "no model for family
<f>"; (g) a field artifact the module registers, on a run of (a), (c), (e) or (f) → status `unassociated` with reason
`run_inputs_unverified`: no texture, no legend scale from it, no number in the twin, while its existence and receipt
are listed; on a run of (b) → `verified`; (h) on a run of (b), an artifact that passes every AC-21 check but whose
association is missing → `unassociated` with the module's code as the reason (C#57177 C1-C4, as the adopted module
carries them: C#57385): a target lacking a signed identity, as every target lacks `model_hash` and `producer_hash`
today (P5) → `target_incomplete`; no complete signed association record in the verified prefix (no signed grid, layer
table, argv or steady-grid hash: P1, P5) → `association_missing`; a record lacking an identity →
`association_incomplete`; a resolver that throws → `association_unavailable`; no resolver →
`association_resolver_missing`; no bounds → `temperature_bounds_missing`. A family match, signed flags or the
artifact's own declarations never fill what is missing: never drawn, never exported as numbers. An artifact-side
`null` is a malformed artifact, refused in AC-21. Pass: all (SPEC.md §5.6, §5.7).

**AC-42 Paused presentation during ingestion** (node, browser; W-E12). Results on a live fixture feed and on a long
replay load: Pause holds the drawn values, the field and the playhead at seq S while rows keep arriving and verifying
(K grows; the mode chip still follows `source.mjs` exactly as in AC-23); the chip reads `paused · N new verified
results`, where N counts verified results after S (pages, keepalives, duplicate rows and backlog never change N, as
in AC-26); nothing new is drawn or announced while paused; Resume (the button or `P`) moves to the newest verified
state and announces once. Adversarial: 1,000 keepalive pages while paused → N unchanged; Resume twice → one
announcement; a late conflict that drops K below S while paused → the view drops to K at once (`STALE · chain
broken`, AC-25) and N recounts; a field verified while paused is not drawn until Resume; with reduced motion, Resume
jumps without animation. Pass: all (SPEC.md §4.5; A#57218).

**AC-43 Nested rotated and mirrored transforms** (node, browser; W-C04; gated on W16). Only for authored CAD
geometry: with a fixture of nested occurrences (an instance inside a parent rotated 90° about z, inside an assembly
mirrored in x), the composed world transforms equal the expected matrices; mirrored (negative-determinant)
occurrences flip triangle winding so faces stay outward (normals point out, and back-face culling shows the outside);
per-instance boxes in the assembled frame match the primitive model within 1 µm (AC-38); `pick()` at known screen
points returns the right instance id through the nested rotated and mirrored occurrences, before and after explode;
the GLB node hierarchy and `extras.instance_id` round-trip. The first, original-primitive page has no nested
transforms (every box is axis-aligned in assembled coordinates), so this criterion does not block it. Pass: all,
before W16 merges (A#57218).

**AC-44 MCP conformance, when the MCP half exists** (node; owner per D9). The room's MCP tools call the same code
path as `scripts/package3d.mjs export3d` and add no validation of their own: for a valid replay, a broken prefix and
a replay with refused values, each tool returns twin JSON and markdown byte-identical to the CLI's, the same refusal
codes, and outcomes that map one-to-one onto the CLI's exit codes (0, 1, 2, 3); a tool can neither fetch nor start
anything the CLI cannot (no solver, no write route: AC-31); tool descriptions carry the banners, the label rule and
"Simulated, not silicon" verbatim; every temperature in a tool result keeps its serialized label, resolved as AC-06
requires. Not required for the first page; required before any MCP tool for the room ships. Pass: all
(main:scripts/sentilab-scene.mjs:6-7; A#57059; A#57218).

**AC-45 The W4 review fixtures, adapted** (node, python; synthetic inputs from C#57232, SPEC.md §5.10). W13 runs every
field case below in its wrapped form (a `sentilab-field/0.1` artifact as P1 would write it, with its association
record and target, under a TEST-key measurement) through `checkField` and the adopted module, and expects this spec's
outcome; rows marked P1 only test P1's converter and are listed for its owner. The module's own crosswalk of these
cases (`fixture-crosswalk.json`, C#57385) agrees with every row's status; it names in words what this table names as
codes (for `hs6_03`, "association missing" where the code here is `target_incomplete`), and records that its tests did
not execute the native cases. No grid value of the pack is ever shown or exported as a temperature.

| Case | Pack outcome | This spec's outcome |
|---|---|---|
| `hs6_01_bound_layer0` | accept | `verified`, as layer 0, the substrate: the record's layer table holds layer 0 only (SPEC.md §5.7); never shown as layer 4 |
| `hs6_02_branch_unknown` | no_association | `unassociated` (`association_missing`): no signed record binds the secondary-path branch |
| `hs6_03_unknown_producer` | no_association | `unassociated` (`target_incomplete`): no signed producer identity, and none is made from the format's resemblance |
| `hs6_04_wrong_layer_request` | reject | asking for layer 4 of the registered layer-0 field is refused (`layer_not_emitted`); an artifact that relabels it layer 4 is `layer_identity_mismatch`; nothing is relabelled |
| `hs6_05_truncated` | reject | `dims` (a layer one value short) |
| `hs6_06_duplicate_index` | reject | P1 only: P1 refuses a repeated cell index |
| `hist_01_all_layers` | accept | `verified`, ids 0 to 7 kept |
| `hist_02_select_layer4` | accept | `verified`; layer 4 is selected by its id after the whole document passed, never the first layer as a proxy |
| `hist_03_truncated_last_layer` | reject | `dims`; no partial field |
| `hist_04_missing_layer4` | reject | `layer_identity_mismatch`: seven layers, agreeing with the pointer, against the record's eight (C3) |
| `hist_05_duplicate_layer3` | reject | `layer_schema` (C3) |
| `hist_06_indexes_do_not_reset` | reject | P1 only: P1 refuses indices that do not restart in each layer |
| `hist_07_unexpected_layer8` | reject | `layer_identity_mismatch` (C3) |
| `hist_08_malformed_header` | reject | P1 only: P1 refuses the header; the wrapped analogue, a non-integer `index` such as `"four"`, is `layer_schema` |
| `hist_09_same_count_wrong_shape` | reject | `dims` (a 3 x 2 artifact under a 2 x 3 pointer: C4); `grid_association_mismatch` when artifact and pointer agree and the record differs |
| `hist_10_shape_missing` | no_association | no artifact: P1 writes none without a shape, and the page shows no field; the wrapped analogue, `rows: null` in the artifact under a 2 x 3 pointer, is `grid_schema` (a pointer without its shape is `dims`, before the hash) |
| `hist_11_nonnumeric_value` | reject | `nonfinite_value` (a string value) |
| `hist_12_reject_package_stretch` | reject | `grid_association_mismatch`: the artifact's extent stretched to the spreader outline, the record's the central grid (C4); with both stretched, `extent` |
| `hist_13_core_field_with_package_outline` | accept | `verified`; layer 6 coloured over the central grid only, its 40 x 40 mm outline uncoloured and labelled `unmeasured` |
| `hist_14_units_missing` | no_association | no artifact: P1 writes none without a declared unit; the wrapped analogue, `unit: null`, is `unit_not_supported`; never labelled K or C |

Added beside the pack, from the same review's field-contract findings (C1, C2): an artifact whose `candidate_hash` or
`problem_hash` is `null` → `binding_schema`, or contradicts the target → `binding_mismatch`; a target without them →
`unassociated` (`target_incomplete`); a pointer in C over an artifact in K → `unit_mismatch`.

Geometry vectors: (a) centre (12.5, 17.25) mm with an 8 x 5.5 mm size → lower-left (8.5, 14.5) mm in the RenderModel
and (0.0085, 0.0145) m in the writer's floorplan; centre (4, 3) mm with 8 x 6 mm → (0, 0); a centre used as a
lower-left (0.0125, 0.01725 m) or millimetres labelled metres (8.5, 14.5 "m") fail (AC-13, AC-16); (b) a 10 x 4 mm
die at centre (12, 8) mm with a 0.5 mm halo → die lower-left (7, 6) mm and a halo envelope with lower-left (6.5, 5.5)
mm, 11 x 5 mm; no vertical thickness is taken from the halo width (AC-16); (c) the six explicit layers are 200, 70,
110, 10, 150 and 20 µm (0.56 mm in all), only layer 4 has power, and the model RenderModel places them at z = -0.27 to
-0.07, -0.07 to 0, 0 to 0.11, 0.11 to 0.12, 0.12 to 0.27 and 0.27 to 0.29 mm; a chip layer of 0.15 m, all six layers
powered, or "every layer-4 region is silicon because the layer default is" fail (AC-16); (d) layer 4's `Ubump_0` is
silicon with zero block power, and a copper assignment inferred from its name fails (AC-16); (e) the asymmetric
mapper of AC-21. Pass: every row and vector, with each fixture's synthetic origin recorded.

**AC-46 The adopted field check and its boundary** (node, static; W13; C#57385, A#57404). (a) `field-validator.mjs` is
byte-identical to the adopted module: 17,067 bytes, sha256
`af0d24a7f4029cca378775c83be9465422127f00c2e5c75bbf7188b82d7880bc`; only `field.mjs` imports it, and no other module
of the room checks a field artifact itself (static). (b) The capped body: `checkFieldArtifact` is called only from
`checkField`, and only with the `Uint8Array` that `readBodyCapped` returned for that fetch (spies on both); an
over-cap body is refused `too_large` with no module call. (c) The stale-target repair, the three cases of the replay
the delivery keeps (C#57385, `independent/root-portable-review.json`): an earlier valid artifact with its valid
earlier receipt, checked while the target is a later run that shares its candidate, problem, model and producer →
`refused` (`binding_mismatch`), and through a draft-shaped ref `draft_target_conflict`, with zero resolver calls and
no retry under another target; the matching target → `verified` (on a run with verified inputs); no target →
`unassociated` (`target_incomplete`), with zero resolver calls. (d) Follow-up (root's one nonblocking finding in
A#57404, which she rated P3): a decorated `Uint8Array` (an own `byteLength` reporting under the cap on a longer array,
a custom iterator yielding other bytes, or a shadowed `buffer`, `byteOffset` or `length`) cannot change the bytes the
module copies or slip past the cap: the copy equals the array's intrinsic contents, read through the typed-array
prototype's own getters, and the cap applies to the intrinsic length. The adopted module reads `byteLength` and copies
through the iterator (field-validator-proposal.mjs:165, :169), so (d) waits for a revised module with its own digest
and review. It does not block W13: a wire body cannot carry those properties, and (b) admits no other input; it is
required before the module takes input from any other caller. Pass: (a) to (c) for W13; (d) when the revised module
lands.

## Crosswalk to astra's 41 source cases (W0.2)

astra's input binding holds 41 source cases: 30 web cases (7 conversion, 8 interface, 15 evidence and streaming) and
11 anatomy cases (A#57059). Root's crosswalk of the v0.1 draft preserves every one of them: 10 direct, 29 partial and
2 missing, with zero executed (A#57218; the case-level table is retained by root with her review, sha256
`a8c13fee…`, seal `dffaec2f…`: TRACE.md section 1). This version changes the ACs as root asked:

| Case or family (root's id) | Root's request (A#57218) | This version | ACs |
|---|---|---|---|
| W-E12 | Add paused presentation during ingestion, with a pending count and an explicit resume | Added (SPEC.md §4.5) | AC-42 |
| W-C04 | Retain nested rotated and mirrored transform, winding and picking coverage for later W16 | Kept, gated on W16; it does not block the first original-primitive page | AC-43 |
| Terminal and late results | Tighten | ENDED, the terminal transport states, candidates still pending when the run ends, late fetches and late results (SPEC.md §4.5) | AC-24, AC-26 |
| 100-switch cleanup | Tighten | 100 consecutive mode switches return GL objects, fetches, listeners, timers, models and heap to their baseline | AC-35 |
| Asymmetric field basis | Tighten | The orientation case uses rows unequal to columns, a non-square extent and a cell off both diagonals, so a swap or a flip cannot pass | AC-21 |
| Eventual MCP | Tighten | MCP conformance to the CLI, with an explicit owner (D9) | AC-44 |

**Traceability.** Every AC id of v0.1 (AC-01 to AC-40) keeps its number and meaning: criteria were tightened, never
removed or renumbered, so every case root's crosswalk maps to them still resolves. New criteria are appended (AC-41
onward). The case-level table (41 rows: case id, ACs, and direct, partial or missing) is root's; W0.2 commits it next
to this file, and its exit check is that no row is missing. Deferred CAD cases do not block the first
original-primitive page.
