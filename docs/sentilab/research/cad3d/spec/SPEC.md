# SentiLab chip room (Package 3D): joint spec sheet

**Version 0.2, 2026-10-31: the corrected successor of v0.1 (`da9b1ee`) after root's review (A#57218). A proposal for
sign-off by forge (coordinator), warden (operations) and astra (root reviewer). Nothing here is implemented,
deployed or agreed.** After all three sign the exact document, warden
provisions one build agent (the "Astra ultra box") that implements it phase by phase (section 9).

Companions in this folder: `PSEUDOCODE.md` (modules and signatures, with integration points), `ACCEPTANCE.md`
(testable criteria, AC-01 to AC-40), `TRACE.md` (every requirement mapped to its source, input hashes, and the line
moves since lane 3 was written).

## 0. How to read this

- **Source tags.** `L1:<file> §n` is lane 1 and `L3:<file> §n` is lane 3, both on branch `forge/cad3d-research` at
  `253ee4f74f998f52c06e437acf935f2bf7e63067` (under `docs/sentilab/research/cad3d/`). `A#57053` and `A#57059` are
  astra's room messages (verbatim copy read from `C:/tmp/cad3d-astra-lane2.md`); `A#57218` is root's (astra's) review
  of v0.1, pinned in TRACE.md section 1. `F#57046` is the founder's ask.
  `main:<path>:<line>` is origin/main at `d25046256b4a712b529977f31e10b7e32248a9c0`. `pr66:<path>:<line>` is the
  open PR #66 head `609d339d79cfa0c120806fc5132044b460db5cd3`.
- **Line numbers moved once.** Lane 3 cited origin/main at `46791be`. Commit `d250462` (#64, per-value labels)
  changed `temperature-label.mjs`, `package.js`, `scene.mjs` and a few other web files, so some lane 3 line numbers
  shifted; this spec uses the `d250462` lines (TRACE.md section 3 lists every moved citation). `git diff --stat
  46791be d250462` touches only `web/`, so lane 1's citations into the solver, producer and API still hold.
- **Which code I relied on.** Every integration point is on origin/main. PR #66 (agent-friendly site) is OPEN and
  not merged; `web/public/agents/` does not exist on origin/main. This spec borrows only PR #66's conventions for
  `/agents/` (markdown plus JSON, an `omitted` record, no simulated temperatures on agent pages) and works whether or
  not PR #66 merges (section 6.9, D9).
- **MUST / MUST NOT** are requirements on the build. **Default** marks a starting choice while an open decision
  (section 11) is pending; reviewers may change it. Where two inputs disagree, both are recorded in section 11.
- **Changes since v0.1** (`da9b1ee60c6b2fd11ab97e66e9384cc44da1a0d7`, the exact draft root reviewed in A#57218). Each
  item below is one commit; TRACE.md section 5 maps every finding to its change, its lines now and its ACs.
  - R1 (A#57218 item 1): an instance is drawn or undrawn. An undrawn part keeps its id, parent, connections and null
    dimensions, carries no box, and is left out of bounds, picking and field association (section 5.3; AC-11).
  - R2 (item 2): labels travel as serialized records. A reader recomputes `labelFor()` from the verified evaluator
    identity, compares the four strings and resolves the canonical in-process `LABELS` object (PL-2; AC-06).
  - R3 (item 3): `geometry_sha256` has a frozen, versioned preimage (`sentilab-geometry/1`) sorted by stable id, with
    parent and box associations and no view state; reordering keeps the hash, changed geometry changes it (5.0; AC-14).

## 1. Goals and non-goals

### Goals

| Id | Goal | Source |
|---|---|---|
| G1 | One new page, `/sentilab/package3d/`, linked from the Package view and the Lab view, showing an AI accelerator package in 3D, assembled and exploded ("open body"), every part labelled and every connection explainable. | F#57046; L3:ARCHITECTURE §0 |
| G2 | Three kinds of content, separate in data and on screen: typical anatomy, our model, results (section 3). | task rule 2; A#57053 |
| G3 | The thermal part in full: the typical junction-to-coolant path, the stack our solver actually simulates, and (once the producer publishes it) the solver's per-layer field. | F#57046; L1:thermal_path.md; L1:our_model_mapping.md; L3:ARCHITECTURE §5 |
| G4 | 3D for results, "real time" exactly in the existing LIVE sense (section 4.5). | task rule 4; L3:ARCHITECTURE §6.4 |
| G5 | Every value shows its provenance; every temperature its label; unknowns stay visible (section 7). | task rules 1, 3; A#57059 |
| G6 | Usable without WebGL, by keyboard and by touch, at 320, 390 and 1280 CSS px and at 200% zoom. | A#57059; L3:ACCEPTANCE A-09 |
| G7 | Every visual has an agent-readable twin (JSON plus markdown under `/agents/`) with the same qualifications. | task rule 9; A#57053 |
| G8 | Same trust posture as today: CSP unchanged, no third-party runtime code (default), no Worker change, read-only. | L3:ARCHITECTURE §1-2; main:web/src/csp.js:7 |

### Non-goals

| Id | Not built, not claimed | Source |
|---|---|---|
| NG1 | Manufacturer CAD or any product's real floorplan. The anatomy is a representative reconstruction from public sources. | L1:REPORT.md status block |
| NG2 | Silicon validation or acceptance of any evaluator. ACCEPTED is empty. A rendering success creates no scientific acceptance. | main:web/public/temperature-label.mjs:26-28; A#57059 |
| NG3 | Die-internal anatomy (tensor arrays, SRAM, network-on-chip floorplan, power maps). No public power map was captured. | L1:thermal_path.md §4 item 1; D13 |
| NG4 | Solver iterates, transient physical time, or anything mid-solve. The solver is steady state. | L3:ARCHITECTURE §6, §6.4 |
| NG5 | An in-browser solver in this build. SKETCH is specified only as constraints (section 4.9). | task rule 4; D7 |
| NG6 | Write routes, WebSockets, or any way for a viewer to start a solve. | main:web/src/worker.js:51-56; A#57059 |
| NG7 | CAD, WebAssembly or CDN code in the display path. | L3:ARCHITECTURE §2.1, §7 |
| NG8 | Any MicroDuck or Pollen code, model, mesh, asset or text. | task rule 7; main:docs/sentilab/CHIPLET-VISUAL-SCOPE-DISPOSITION.md:7 |
| NG9 | Changing the label rule, the producer, the API or the contracts. Those are prerequisites owned elsewhere (section 8). | task rule 5 |
| NG10 | Restarting any numerical or GB10 job. | A#57053 |

## 2. What exists today

| Fact | Where |
|---|---|
| The site is plain ES modules from `web/public`, no bundler and no `package.json`; CI runs `node --test web/test/*.test.mjs` on Node 22 and boots the real Worker. | main:.github/workflows/ci.yml:23, :30, :35; main:web/wrangler.jsonc:9 |
| Every asset response carries one exact CSP: `default-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'`, pinned by a test. | main:web/src/csp.js:7; main:web/test/worker-csp.test.mjs:20, :47-49 |
| `/api/*` is read-only at the edge; hop headers including `upgrade` are stripped, so WebSockets cannot pass; upstream `cache-control` is passed through. | main:web/src/worker.js:7, :21-37, :51-56 |
| The Package view is hand-written Canvas 2D: one flat colour per chiplet ("not a field"), a schematic stack of drawing constants, the interposer drawn as the layout extent plus 1.5 mm. | main:web/public/sentilab/package/render.mjs:1-9; scene.mjs:18, :23-35, :235-246 |
| One label rule for every temperature: withdrawn, illustrative (exactly `fixture-no-solver`), accepted (none), unvalidated (everything else); HotSpot-7 at `f18831e` is withdrawn; each value carries its own label. | main:web/public/temperature-label.mjs:12-28, :38-53; main:web/test/per-value-provenance.test.mjs:1-5 |
| LIVE only with a poll within 5 s, K grown within 60 s after catch-up, nothing after the prefix; otherwise STALE with a reason, or ENDED, or REPLAY for files. Catching up is not progress. | main:contracts/view-envelope-v0.6.2/VIEW-ENVELOPE.md:113-130; main:web/public/sentilab/package/source.mjs:172-182 |
| The live producer's measurement carries `J` (unit "C"), `W` (metric `weighted-manhattan-mm`), `scenario_id` and `artifact_hashes` (the solver's input hashes as an unnamed list). No centre temperatures, no field. | main:sentilab_core/conductor.py:342-346 |
| The solver writes 8 grid layers; the worker keeps only layer 4 (chip) as `heatmap_c`; J is that layer's grid maximum with `-grid_map_mode max`. | main:sundai_hotspot/tap_oracle_worker.py:91-100, :356-369, :417-431 |
| API routes: `/api/health`, `GET` and `POST /api/runs`, `/api/runs/{id}`, `/api/view/runs`, `/api/view/events`, `/api/view/key`. No artifact route, no SSE route, no `/api/replay/` route (the Package view builds that URL anyway). | main:app/main.py:28, :38, :54, :59; main:app/view.py:90, :97, :186; main:web/public/sentilab/package/package.js:652-654 |
| Signed flight records with a chip-layer grid do exist: the served run-view replay holds `oracle_result` events whose `thermal.heatmap_c` is a 32 x 32 chip-layer grid from the withdrawn HotSpot-7 build, and the run view draws them with labels. No view envelope carries any field. | main:web/public/replay/ascend910-seed11-32x32.json (`result.lane_results.*.record[*].payload.thermal`); main:web/public/app.js:52, :63, :119-123, :139; see D3 |
| The model: TAP's 6-layer LCF plus HotSpot's appended spreader and sink; bump and TSV layers as homogenised mixes; bottom adiabatic. | main:sundai_tap/passive_interposer.py:22-48, :135-165; main:sundai_tap/util/hotspot.config:15-35, :48; main:sundai_hotspot/temperature_grid.h:46-48; temperature_grid.c:523-552 |
| Fixtures `ascend910`, `micro150` (50 mm) and their 45 mm variants; chiplet ids are `tap-chiplet-<i>`. | main:sundai_hotspot/tap_oracle.py:25-33, :311 |
| Reviewed reference layouts (raw, 0.5 mm, 1 mm) with content hashes, 45 mm frame, origin at the interposer's lower-left corner. | main:docs/sentilab/references/README.md:14-24, :46-70 |
| Served files may not name vendors, models or internal agent handles (two pinned exceptions); no file holds a control byte. | main:web/test/public-names.test.mjs:1-12, :20-26; main:web/test/control-bytes.test.mjs:1-4, :12-13 |
| PR #66 (open) adds `/agents/`: its index says simulated temperatures are not shown, and its reference copies omit temperature fields with a reason. | pr66:web/public/agents/index.json:14; pr66:web/public/agents/references/ascend910-tap25d-fig6a.json:272-281 |

## 3. The three content kinds

| | Typical anatomy | Our model | Results |
|---|---|---|---|
| What it is | What a 2.5D AI accelerator package is made of and how its parts connect | What HotSpot/TAP actually simulates, with its simplifications | Values a signed run produced, on the exact geometry they were produced for |
| Data | `sentilab-anatomy/1` and `sentilab-assembly/1` (section 5.2-5.3), converted from L1 `parts.json` plus a reviewed overlay | `sentilab-model-stack/1` (5.4), transcribed from the solver code at a pinned commit and checked by running TAP's floorplan writer; `sentilab-layouts/1` (5.5) from the reviewed reference manifests | The verified projectable prefix only, through `source.mjs`; field artifacts once P1-P4 land (section 8) |
| Geometry | Schematic arrangement; sourced sizes where they exist; render hints otherwise | The model's layer table, floorplan rules and reference layouts | Footprints from the signed candidate geometry; stack from the model manifest of the run's fixture |
| Temperatures | None (PL-4) | None; the ambient is a temperature-valued input and is not rendered (PL-4, D2) | Only through `temperature-label.mjs`, per value (PL-2) |
| Banner (exact) | `Typical anatomy · a representative reconstruction from public sources. Not any manufacturer's CAD. Not silicon-validated. Arrangement schematic; unknown values are marked.` | `Our model · the layers and blocks our thermal solver actually simulates, with its simplifications. Not the real package.` | `Results · from signed, verified evidence only. Each value names its run, geometry, evaluator and label. Simulated, not silicon.` |
| Chip inside the canvas | `Typical anatomy · not manufacturer CAD` | `Our model · not the real package` | the legend's label-state chip and `Simulated · not silicon` |

Crossing rules (MUST):

- **X1.** A RenderModel holds exactly one content kind. `buildRenderModel()` refuses mixed input (PSEUDOCODE §5).
- **X2.** Anatomy to model goes only through the model manifest's `stands_for` (which model layer a part type is
  lumped into). The anatomy panel shows "In our model: …" or "Not in the thermal model". No model number sits in
  the anatomy dataset and no anatomy number sits in the model dataset.
- **X3.** Model to results goes through the run's fixture id (signed `run.family`, main:sentilab_core/conductor.py:116)
  and the signed candidate geometry. Model mode never shows result values. Results mode never draws anatomy-only
  parts as if simulated; when a field is shown they are listed as "not in the thermal model" (L3:ARCHITECTURE §5.3).
- **X4.** No value from one kind fills a gap in another. Results-mode thickness never falls back to anatomy nominal
  thickness (lane 3 proposed that fallback: L3:PSEUDOCODE §1 step 3; see D6). A missing model value is shown as
  unknown or schematic, labelled.
- **X5.** Lane 1's `in_our_model` blocks and model-valued entries (the heat sink's 6,900 µm and 180 mm, every
  `our_model*` conductivity) move to the model manifest; the anatomy dataset keeps none (section 5.9).
- **X6.** Raw and 0.5 mm reference layouts keep distinct identities (`content_sha256`) and results; they are never
  merged, averaged or relabelled. A result is shown only on the geometry it was signed with.
  (A#57059; main:docs/sentilab/references/README.md:18-24)

## 4. Experiences, screen by screen

Each screen lists what a person sees and does, what an agent gets for the same thing, and the rules that hold.

### 4.0 The page frame (every screen)

- **Header:** `SentiLab · Package 3D`; a mode switch (three buttons: `Typical anatomy`, `Our model`, `Results`);
  in Results, the source switch (`Replay` / `Live`) and the mode chip from `source.mjs` (REPLAY, LIVE · progress N s
  ago, STALE · reason, ENDED · run finished); links to the Package view, the Lab view, `Honest limits` and
  `Agent version` (`/agents/package3d/`).
- **Banners, top to bottom:** the page notice slot, exactly `<p class="wnotice" id="wnotice" role="note" hidden></p>`
  (the markup the notice test pins: main:web/test/temperature-label.test.mjs:331-333; main:web/public/sentilab/package/index.html:48);
  the frozen-chain banner and value-check banner (Results only, as the Package view: package.js:358-381); then the
  content banner of the current mode (section 3, exact text).
- **Stage:** canvas left (desktop) with in-canvas chips (content chip; `exploded · spacing not to scale` when
  exploded; `thin layers thickened for visibility` in readable mode; `1 of k² sites drawn · N total` for sampled
  arrays; the label-state chip in Results). Right panel: part tree, part detail, legend.
- **Controls under the canvas:** Explode slider with `Assembled` / `Exploded`; Section (`off`, `X`, `Y`, position);
  Overlay (`none`, `heat`, `power`, `signal`); Variant (`lidded`, `lidless`; anatomy only); `True scale` / `Readable`;
  `Lid` (anatomy) or `Spreader and sink` (model, results); Layer (results, when a field exists).
- **Results only:** playhead strip (scrub, `seq K / total`, play), the solve-status chip, the as-of stamp and the
  simulated-time line (section 4.5).
- **Keys:** arrows orbit, `+`/`-` zoom, `0` home, `E` explode, `S` section, `O` overlay cycle, `V` variant, `T` true
  scale, `L` lid, `F` field layer (results), `Esc` clears selection. Space, left and right keep the Package view's
  playhead meaning in Results (package.js:626-636).
- **Agent:** `/agents/package3d/index.md` and `index.json` describe the page, the three modes with their banners, and
  link every twin below.

### 4.1 Exploded "open body" view (S1)

- **Person:** drag the slider from assembled (t = 0) to exploded (t = 1); `E` toggles; tweened over 600 ms with the
  existing ease (main:web/public/sentilab/package/render.mjs:19), or a jump under reduced motion (package.js:17).
  Frames are drawn only while something moves (render on demand, as package.js:243).
- **Levels.** Anatomy: the part type's `level` (L1 `stack_order`, decimals for sub-layers); inside an HBM stack the
  base die, bond layers, core dies and top die separate by a smaller inner gap. Model and Results: the 8 grid layers
  (0 to 7) as levels.
- **Labels.** Level names on phones (at most 6), part names on desktop (at most 24), plus the selected part's
  connections (L3:ARCHITECTURE §4.4). Labels are DOM text, never canvas text, and never carry temperatures.
- **Rules.** Explode, readable thickening and section are view transforms over immutable assembled geometry (PL-12).
  Every length shown, every pick and every field lookup uses assembled coordinates.
- **Agent:** the twin carries assembled boxes only (an undrawn part carries its id, parent, edges and null
  dimensions, and no box) and says: `Explode, readable thickening and section are view transforms. Every coordinate
  here is assembled.`

### 4.2 Part detail (S2)

Selecting a part (tap, click, part tree button or keyboard) highlights it, its connections and the interconnect
between them, dims the rest (L3:ARCHITECTURE §4.5), and fills the detail panel.

| Mode | The panel shows |
|---|---|
| Typical anatomy | name (generic, D1); content chip; kind; what it is and why it is there (reviewed text with fact ids); material (name, class, conductivity "near room temperature" with basis); dimensions (thickness, footprint, area, count), each with its basis tag: `sourced [fact ids]`, `derived (inputs)`, `not sourced · drawn at X (display only: basis)`, or `unknown`; connections (kinds and via); `In our model: lumped into layer 4, chip layer (150 µm silicon block, uniform power)` or `Not in the thermal model`; sources (fact claims, source type and year; titles and URLs only under D1 "named"); confidence. |
| Our model | layer name as coded; grid index; thickness (model, `file:line@commit`); material as coded (resistivity and the k it implies, with the bump-mix derivation where it applies); lateral rule (interposer, 2 x, 4 x); powered or not; `Stands for` (anatomy part types, linking back); the ranked simplifications that apply; for a die: role, size, rotation, power input in W, halo width. |
| Results | chiplet id and role (from the fixture's role map); footprint (evidence: run, seq); J and W from the measurement `metricFor()` picks (main:web/public/sentilab/lab-model.mjs:124), each with its statistic name and label; centre temperature with its own label; evidence validity (valid or stale); the receipt (measurement seq, event id, envelope hash, evaluator identity); receipt completeness (section 5.6). |

- **Agent:** `anatomy.json` (part types, facts, sources, materials, edges) and `anatomy.md` (one section per part
  type with the same text); `model-<fixture>.json`/`.md`; for results, the result twin (section 4.8).

### 4.3 Interconnect overlays: heat, power, signal (S3)

| Overlay | Typical anatomy | Our model | Results |
|---|---|---|---|
| Heat | Lane 1's flows drawn as paths through the parts: primary path up (lidded or lidless), secondary path down, HBM vertical path, and three lateral coupling paths (lid or spreader, interposer, mold) with the contested-share note (thm-026 against thm-048). The legend states the sourced share ("about 95% leaves through the top", thm-036) without numbers on arrows. | Conduction through the 8 layers, with a cross at the bottom of layer 0 (`bottom adiabatic: no heat leaves through the substrate in this model`, hotspot.config:48) and the spreader's 2 x lateral extent marked. | No arrows. A verified field per solver layer (once P1-P4 land), else per-chiplet centre colours where the run has them, else nothing; the existing basis text applies (`chiplet-centre temperatures from the solver; not a field`, scene.mjs:18). |
| Power | VRM to board, BGA, substrate, C4, interposer TSV, interposer wiring with deep-trench capacitors, micro-bumps, die. Sourced numbers (core rail as low as 0.7 V, about 1,000 A, at least 3 mF of board capacitance) live in the panel, not on the path. | Per-die power inputs in W from the fixture config, spread uniformly over each die (passive_interposer.py:182-195). | The same model inputs for the run's fixture. |
| Signal | HBM bus (PHY, micro-bumps, interposer wiring, base die, TSVs, DRAM), die-to-die, off-package; bus widths and per-stack bandwidths from facts in the panel. | The fixture's netlist weights between dies (sys_*.cfg connections), labelled `TAP connection weights; not routed wires, not bandwidth`. | The same netlist; `W` shown only as `wire proxy (mm)`, never as routed wire (conductor.py:345; README.md:105-108). |

- **Rules.** Every overlay shows its qualifier: `Typical path through the parts. Not a solved heat flux, not a routed
  wire, not a measured bandwidth.` (anatomy) or the model's equivalent; no watts or temperatures on arrows; Results
  draws no arrows at all (PL-14, PL-15; A#57059 "a heat arrow is not solved flux/Watts"). A flow step on an undrawn
  part (section 5.3) is listed in the legend as `passes through <part> · not drawn`; the drawn path invents no point
  for it.
- **Agent:** `flows` and `edges` in the twins carry the same qualifier string.

### 4.4 Thermal-path view (S4)

A `Thermal path` tab beside the part detail: a DOM table plus a simple ladder drawing (SVG from the same data).

- **Typical anatomy:** lane 1's one-dimensional resistance stack (L1:thermal_path.md §1-§3): per layer, thickness,
  conductivity and area-specific resistance R″ in K·mm²/W, with R in K/W over an 814 mm² reticle-class die (prd-009),
  and the derived sums (about 0.050 to 0.056 K/W lidded, 0.047 to 0.052 K/W lidless); the secondary path; the HBM path
  (about 3.8 K·mm²/W per bond interface, thm-031, and the derived 9 x of a logic die). Header text: `One-dimensional
  hand estimates from cited inputs. Not simulation results. No temperatures.` Literature temperature limits,
  conductivities stated at a temperature, and "rise per watt" figures are not shown as numbers (PL-4, D2); the
  conductivity column uses the near-room-temperature values only, with the note "k falls as silicon heats" and its
  fact id.
- **Our model:** the model stack's t/k per layer (L1:our_model_mapping.md §2 table, re-derived from the manifest),
  the lumped convection as an effective coefficient of about 2,778 W/(m²·K) on the sink base (derived), `bottom
  adiabatic`, and the comparison column against the typical values. Header: `Model inputs and derived t/k. Not
  results.`
- **Results:** per-layer statistics of a verified field (minimum and maximum per solver layer, each labelled), once
  P1-P4 land; until then: `No per-layer values in this run's receipts.`
- **Agent:** `anatomy.md#thermal-path`, `model-<fixture>.md#stack`, and the result twin's `field` block.

### 4.5 Live and replay states (S5, Results only)

| Element | Rule | Source |
|---|---|---|
| Mode chip | From `source.mjs` `modeNow()` / `liveModeOf()` only; the page never computes LIVE or STALE. | main:web/public/sentilab/package/source.mjs:172-182; L3:ACCEPTANCE A-05 |
| Playhead | `seq K / total`; rows after the break never draw ("after the break · not drawn"). | package.js:441-442; VIEW-ENVELOPE v0.5 rule 1 (main:contracts/view-envelope-v0.5/VIEW-ENVELOPE.md:75-79) |
| As-of stamp | Every result value and field says `as of seq S`, and `behind` when S is below the playhead. | L3:ARCHITECTURE §6.1, §6.4 |
| Solve status | `solving (since seq S)` only when the verified lifecycle is `simulation_pending` and the chip is LIVE; otherwise `solve status unknown (feed STALE · reason)` or nothing. | L3:PSEUDOCODE §7 `solveStatus`; main:web/public/sentilab/evidence-projection.mjs:11-12 |
| Simulated time | `Steady state · no simulated time axis`. Shown separately from the wall-clock mode chip and the playhead. | A#57059 (separate job status, replay position and physical time) |
| New receipt | A new verified result is announced once (polite live region, a one-time highlight); no pulsing or idle motion. | A#57053; L3:RISKS R-08 |
| Field change | A hard cut to the new verified field; no blend between fields (D17). | PL-20 |
| Disconnect | `STALE · transport`, `solve status unknown`, the last verified state stays, labelled. | VIEW-ENVELOPE v0.6.2 rule 4-5 (VIEW-ENVELOPE.md:102-126) |
| K drops | `STALE · chain broken`; fields named after the new K leave the GPU and the cache at once; fetches for them abort. | L3:ACCEPTANCE A-06; playhead.mjs:43-56 |
| Doorbell (optional, later) | Only pokes the poller; never data, never progress, never LIVE. | L3:ARCHITECTURE §6.2 |

"Real time" means exactly this: results appear within seconds of the core signing them, under the unchanged LIVE
rule, and every field is a completed, signed solve stamped with its seq. Nothing from inside a solve is shown, and
nothing about the chip's own operation is implied (L3:ARCHITECTURE §6.4).

### 4.6 Phone (390 and 320 CSS px) and 200% zoom (S6)

- Stacked layout: header (compact), mode switch (full width), notice, content banner, canvas (height
  `min(56vh, 460px)`), one legend line with its state chip, controls wrapping onto two rows (no sideways scroll),
  part tree (accordion), detail panel inline below (L3:ARCHITECTURE §4.6).
- Lid off by default on phones, as today (package.js:59). Labels limited to level names (at most 6).
- One-finger orbit, two-finger pinch and pan; page scroll keeps working outside the canvas.
- At 390 px the notice, the content banner, the legend and its state chip are visible without scrolling past the
  canvas. At 320 px and at 200% zoom on a 1280 px window nothing clips and nothing scrolls sideways. Smallest text
  11 CSS px.

### 4.7 No WebGL, lost context, no WebCrypto (S7)

- **No WebGL2, shader failure or a lost context:** the same page shows the 2D cross-section (SVG) built from the same
  `sectionAt()` rectangles, plus the part tree, detail panel, legend with its label state, and notice. Never a
  half-drawn 3D scene (L3:ARCHITECTURE §9). After `webglcontextrestored` the renderer rebuilds from the cached
  RenderModel; nothing is refetched or re-verified.
- **No WebCrypto (insecure context):** Results shows nothing, with the Package view's sentence (package.js:644-648).
  Anatomy and Model still render, with the chip `file check unavailable here (needs a secure connection)` because their
  pinned-hash check cannot run (D14).

### 4.8 Agent experience (S8)

| Visual | Agent twin | Notes |
|---|---|---|
| Page and modes | `/agents/package3d/index.md`, `index.json` | Banners verbatim; links to every twin; the label rule explained in words. |
| Typical anatomy (S1-S4) | `anatomy.json` (`sentilab-twin/1`, content `anatomy`), `anatomy.md` | Assembled instances with true quantities and bases, unknowns as null with basis, edges, flows with qualifiers, facts, `omitted` list. Optional `anatomy.glb` derivative (hashed, metres, +Y up). |
| Our model (S1-S4) | `model-<fixture>.json`, `model-<fixture>.md` | Layer table, materials as coded, role map, netlist with qualifier, reference layouts (raw and 0.5 mm, separate identities), simplifications, code citations. No temperatures (the ambient is listed in `omitted`). |
| Results (S2-S5) | `results.md` (how to obtain a result twin and the rules); `replays/<bundle>-at-<seq>.json` for the bundled replays, built by the CLI; for any run, `node scripts/package3d.mjs export3d <replay.jsonl> ...` (same verifier path as `scripts/sentilab-scene.mjs`, main:scripts/sentilab-scene.mjs:1-17); in the page, a `Twin JSON` dialog that shows the current view's twin as text | Every temperature carries its serialized label record (PL-2); refused values are listed, never exported as numbers (sentilab-scene.mjs:17). No blob or data URLs: the dialog shows text. |

The MCP half of SLAB-026's CLI+MCP comes later through the generated bridge and calls this CLI; it adds no
validation of its own (main:scripts/sentilab-scene.mjs:6-7; A#57059 "CLI/MCP must share validation/artifacts").

### 4.9 SKETCH mode (deferred, D7)

Only if the founder asks for it later: an in-browser approximation in its own mode, own banner
(`SKETCH · in-browser approximation · not evidence`), own colour map and legend, dimensionless (no °C, no K), never
on the same canvas or legend as verified data, never in a twin, run in a same-origin module Worker file (no `blob:`
worker, no WebAssembly). Numbers wait for the label-rule owner to add a state with tests; "illustrative" is reserved
for the bundled fixture (main:web/public/temperature-label.mjs:24-25, :48-51; L3:ARCHITECTURE §6.3).

## 5. Data model

### 5.0 Conventions

- **Frame.** One frame for all three kinds: lengths in mm; origin at the interposer's lower-left corner on the
  interposer's bottom face; +x right and +y up in plan view (the reference layouts' convention,
  main:docs/sentilab/references/README.md:53-59, and the producer's `lower-left-mm`, conductor.py:343); +z out of the
  board toward the cooler. Parts below the interposer (C4, substrate, BGA, board) have negative z.
- **Units, converted once.** Data carries an explicit unit per quantity (thickness in µm, lateral sizes in mm).
  `quantity.mjs` converts to mm once, when a RenderModel is built; the GLB writer converts mm to metres once and
  rotates z-up to glTF's +Y-up once (glTF 2.0 section 3.4, L3:evidence/extra-03). Nothing else converts (PL-13; A#57059
  "a 45 mm golden edge must become 0.045 m exactly once").
- **Ids.** Part types keep lane 1's snake_case ids. Instance ids are path-shaped and authored in the reviewed source,
  never generated from array order: `<assembly>/<type>#<n>[/<type>#<n>…]`, for example
  `typ-1c4m/hbm_stack#2/hbm_dram_core_die#7`. An id is never reused for a different part; removed ids are listed in
  `retired_ids` (PL-11). glTF node names are not relied on for identity (A#57059: "glTF names are not unique").
- **Basis tags** (every number): `sourced` (fact ids), `derived` (arithmetic on cited inputs, inputs named), `model`
  (`file:line@commit`), `evidence` (run, seq), `render_hint` (the real value is not sourced; this is the display
  value, with its reason), `unknown` (no value, nothing drawn from it). Lane 3's `nominal` maps to `sourced` or
  `derived`, and its `schematic` to `render_hint` (L3:PSEUDOCODE §1 `PROVENANCE`).
- **No temperatures in static content.** No unit in these schemas is a temperature unit. Static files (anatomy,
  assembly, model stack, layouts, static twins) MUST NOT contain a temperature number in any string or key either
  (PL-4); temperature-valued inputs and literature values are listed in `omitted` with the reason.
- **Hashes.** Files are pinned by sha256 of their exact bytes, never of a re-serialisation (JavaScript re-serialising
  Python JSON changes numbers such as `45.0`: main:web/public/verify-core.js:5-6). `geometry_sha256` follows the
  frozen geometry preimage below. Layout `content_sha256` values are Python-canonical (README.md:53-59) and are
  recomputed only by a parser that keeps number text (verify-core.js `parseRaw` and `canonical`, :14, :103).
- **Geometry preimage, version `sentilab-geometry/1`** (A#57218 item 3). `geometry_sha256` is the lowercase hex
  sha256 of the UTF-8 bytes of `canonical()` (main:web/public/sentilab/canonical.mjs:4-10: object keys sorted, arrays
  kept in order, numbers in shortest round-trip form, no whitespace) applied to
  `{ "v": "sentilab-geometry/1", "frame": <the assembly's frame>, "instances": [...] }`. `instances` holds one record
  per instance, drawn or not, `{ id, type, parent, variants, drawn, box, array }`: `variants` sorted; `box` the six
  assembled mm values of a drawn instance and `null` for an undrawn one; `array` a drawn interconnect array's geometry
  only, `{ class, region, lattice, pitch_mm, diameter_mm, height_mm }` (the drawn values, from `drawnMm()`), else
  `null`. Records are sorted ascending by `id`: the id grammar is ASCII, so code-unit, code-point and byte order agree,
  and duplicate ids are refused before hashing. Outside the preimage: labels, notes, bases, `dims`, fact lists, edges,
  `retired_ids`, `omitted`, and every view state (explode, readable thickening, section, the selected variant, the
  camera), none of which a caller can pass in. Reordering instances or their variants leaves the hash unchanged;
  moving a box, re-parenting, or changing a type, a variant membership, the drawn state or an array's geometry changes
  it. Another preimage shape needs another version string. It is computed in JavaScript (the build script and the
  page) from `JSON.parse`d values, never in Python. ACCEPTANCE AC-14 pins a golden preimage and its hash.

### 5.1 Common definitions

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:sentilab:package3d:common:1",
  "$defs": {
    "slug": { "type": "string", "pattern": "^[a-z0-9][a-z0-9_-]{0,63}$" },
    "typeId": { "type": "string", "pattern": "^[a-z][a-z0-9_]{0,47}$" },
    "instanceId": { "type": "string", "maxLength": 400, "pattern": "^[a-z0-9][a-z0-9-]{0,39}(/[a-z][a-z0-9_]{0,47}#[0-9]{1,4})+$" },
    "factId": { "type": "string", "pattern": "^(hbm|pkg|prd|thm)-[0-9]{3}$" },
    "sha256": { "type": "string", "pattern": "^[0-9a-f]{64}$" },
    "commit": { "type": "string", "pattern": "^[0-9a-f]{40}$" },
    "cite": { "type": "string", "maxLength": 200, "pattern": "^[A-Za-z0-9_./-]+:[0-9]+(-[0-9]+)?(, ?[0-9]+(-[0-9]+)?)*$" },
    "text": { "type": "string", "minLength": 1, "maxLength": 1000 },
    "basis": { "enum": ["sourced", "derived", "model", "evidence", "render_hint", "unknown"] },
    "unit": { "enum": ["um", "mm", "m", "mm2", "GB", "count", "fraction", "W", "W/cm2", "A", "A/us", "V", "mF", "nF/mm2", "uOhm", "bit", "Gbit/s", "GT/s", "GB/s", "TB/s", "pJ/bit", "W/(m*K)", "K*mm2/W", "K/W", "W/(m2*K)", "J/(m3*K)", "m*K/W"] },
    "connection": { "enum": ["thermal", "power", "signal", "mechanical"] },
    "variant": { "enum": ["all", "lidded", "lidless", "si_interposer", "rdl_interposer", "bridge_interposer", "product_reference", "liquid_cooled", "air_cooled", "vertical_power_delivery"] },
    "pinnedFile": {
      "type": "object", "required": ["path", "sha256"], "additionalProperties": false,
      "properties": { "path": { "type": "string", "maxLength": 300 }, "sha256": { "$ref": "#/$defs/sha256" }, "commit": { "$ref": "#/$defs/commit" } }
    },
    "omission": {
      "type": "object", "required": ["what", "why"], "additionalProperties": false,
      "properties": { "what": { "$ref": "#/$defs/text" }, "why": { "$ref": "#/$defs/text" }, "from": { "type": "string", "maxLength": 300 } }
    },
    "rect": {
      "type": "object", "required": ["x0", "x1", "y0", "y1"], "additionalProperties": false,
      "properties": { "x0": { "type": "number" }, "x1": { "type": "number" }, "y0": { "type": "number" }, "y1": { "type": "number" } }
    },
    "box": {
      "type": "object", "required": ["x0", "x1", "y0", "y1", "z0", "z1"], "additionalProperties": false,
      "properties": { "x0": { "type": "number" }, "x1": { "type": "number" }, "y0": { "type": "number" }, "y1": { "type": "number" }, "z0": { "type": "number" }, "z1": { "type": "number" } }
    },
    "quantity": {
      "type": "object",
      "required": ["basis", "unit", "value", "min", "max", "facts"],
      "additionalProperties": false,
      "properties": {
        "basis": { "$ref": "#/$defs/basis" },
        "unit": { "$ref": "#/$defs/unit" },
        "value": { "type": ["number", "null"] },
        "min": { "type": ["number", "null"] },
        "max": { "type": ["number", "null"] },
        "facts": { "type": "array", "uniqueItems": true, "items": { "$ref": "#/$defs/factId" } },
        "derivation": { "$ref": "#/$defs/text" },
        "hint_basis": { "$ref": "#/$defs/text" },
        "model_ref": { "$ref": "#/$defs/cite" },
        "evidence_ref": { "type": "string", "maxLength": 300 },
        "note": { "$ref": "#/$defs/text" }
      },
      "allOf": [
        { "if": { "properties": { "basis": { "const": "unknown" } } },
          "then": { "properties": { "value": { "type": "null" }, "min": { "type": "null" }, "max": { "type": "null" } } } },
        { "if": { "properties": { "basis": { "const": "render_hint" } } },
          "then": { "required": ["hint_basis"], "properties": { "value": { "type": "number" }, "min": { "type": "null" }, "max": { "type": "null" } } } },
        { "if": { "properties": { "basis": { "const": "sourced" } } },
          "then": { "properties": { "facts": { "minItems": 1 } },
                    "anyOf": [ { "properties": { "value": { "type": "number" } } }, { "properties": { "min": { "type": "number" } } }, { "properties": { "max": { "type": "number" } } } ] } },
        { "if": { "properties": { "basis": { "const": "derived" } } },
          "then": { "required": ["derivation"], "properties": { "facts": { "minItems": 1 }, "value": { "type": "number" } } } },
        { "if": { "properties": { "basis": { "const": "model" } } }, "then": { "required": ["model_ref"] } },
        { "if": { "properties": { "basis": { "const": "evidence" } } }, "then": { "required": ["evidence_ref"], "properties": { "value": { "type": "number" } } } }
      ]
    },
    "label": {
      "type": "object", "required": ["state", "text", "short", "title"], "additionalProperties": false,
      "properties": {
        "state": { "enum": ["withdrawn", "unvalidated", "illustrative", "accepted"] },
        "text": { "type": "string" }, "short": { "type": "string" }, "title": { "type": "string" }
      }
    }
  }
}
```

Checks the schema language cannot state, enforced by the readers (PSEUDOCODE §1-§3) with these refusal codes:
`range_order` (min > value or value > max), `not_finite`, `bare_temperature` (any string or key matching the
temperature pattern of PSEUDOCODE §8), `fact_unknown` (a fact id not in `facts`), `label_mismatch` (a serialized label
whose keys are not exactly `state`, `text`, `short` and `title`, or whose strings differ from `labelFor()` of the
value's verified evaluator identity: PL-2; main:web/public/temperature-label.mjs:38-53, :64-70),
`dangling` (an id that resolves to nothing), `cycle` (parent loop), `id_reused` (an id in `retired_ids` back in use).
Every reader is all-or-nothing, like `readGeometry()` (main:web/public/sentilab/package/scene.mjs:105-132): one bad
entry refuses the file, because a package missing a part is a picture that never existed.

### 5.2 Anatomy manifest `sentilab-anatomy/1`

Served at `/sentilab/package3d/data/anatomy.json`; generated by `scripts/package3d.mjs data` from L1 `parts.json`
(pinned by sha256) plus a reviewed overlay (generic names, rewritten claims, content fixes), never edited by hand.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:sentilab:package3d:anatomy:1",
  "type": "object",
  "required": ["schema", "content", "status_text", "names_policy", "built_from", "sources", "facts", "materials", "part_types", "interconnect_classes", "type_edges", "flows", "omitted"],
  "additionalProperties": false,
  "properties": {
    "schema": { "const": "sentilab-anatomy/1" },
    "content": { "const": "anatomy" },
    "status_text": { "const": "Typical anatomy · a representative reconstruction from public sources. Not any manufacturer's CAD. Not silicon-validated. Arrangement schematic; unknown values are marked." },
    "names_policy": { "enum": ["generic", "named"] },
    "built_from": {
      "type": "object", "required": ["parts_json", "overlay", "converter"], "additionalProperties": false,
      "properties": {
        "parts_json": { "$ref": "urn:sentilab:package3d:common:1#/$defs/pinnedFile" },
        "overlay": { "$ref": "urn:sentilab:package3d:common:1#/$defs/pinnedFile" },
        "converter": { "$ref": "urn:sentilab:package3d:common:1#/$defs/pinnedFile" }
      }
    },
    "sources": { "type": "object", "propertyNames": { "$ref": "urn:sentilab:package3d:common:1#/$defs/slug" }, "additionalProperties": { "$ref": "#/$defs/source" } },
    "facts": { "type": "object", "propertyNames": { "$ref": "urn:sentilab:package3d:common:1#/$defs/factId" }, "additionalProperties": { "$ref": "#/$defs/fact" } },
    "materials": { "type": "object", "propertyNames": { "$ref": "urn:sentilab:package3d:common:1#/$defs/slug" }, "additionalProperties": { "$ref": "#/$defs/material" } },
    "part_types": { "type": "object", "propertyNames": { "$ref": "urn:sentilab:package3d:common:1#/$defs/typeId" }, "additionalProperties": { "$ref": "#/$defs/partType" } },
    "interconnect_classes": { "type": "object", "propertyNames": { "$ref": "urn:sentilab:package3d:common:1#/$defs/slug" }, "additionalProperties": { "$ref": "#/$defs/interconnectClass" } },
    "type_edges": { "type": "array", "items": { "$ref": "#/$defs/typeEdge" } },
    "flows": { "type": "array", "items": { "$ref": "#/$defs/flow" } },
    "omitted": { "type": "array", "items": { "$ref": "urn:sentilab:package3d:common:1#/$defs/omission" } }
  },
  "$defs": {
    "aq": { "allOf": [ { "$ref": "urn:sentilab:package3d:common:1#/$defs/quantity" }, { "properties": { "basis": { "enum": ["sourced", "derived", "render_hint", "unknown"] } } } ] },
    "facts": { "type": "array", "uniqueItems": true, "items": { "$ref": "urn:sentilab:package3d:common:1#/$defs/factId" } },
    "source": {
      "type": "object", "required": ["type", "kind", "year"], "additionalProperties": false,
      "properties": {
        "type": { "enum": ["primary", "secondary"] },
        "kind": { "enum": ["standard", "datasheet", "white_paper", "paper", "slides", "patent", "press_release", "product_page", "article", "blog", "distributor_page"] },
        "year": { "type": ["string", "null"], "pattern": "^[0-9]{4}$" },
        "title": { "type": "string", "maxLength": 300 },
        "publisher": { "type": "string", "maxLength": 200 },
        "url": { "type": "string", "maxLength": 500, "pattern": "^https?://" },
        "sha256": { "$ref": "urn:sentilab:package3d:common:1#/$defs/sha256" }
      }
    },
    "fact": {
      "type": "object", "required": ["source", "claim", "confidence", "visual"], "additionalProperties": false,
      "properties": {
        "source": { "$ref": "urn:sentilab:package3d:common:1#/$defs/slug" },
        "claim": { "$ref": "urn:sentilab:package3d:common:1#/$defs/text" },
        "confidence": { "enum": ["high", "medium", "low"] },
        "visual": { "type": "boolean" }
      }
    },
    "material": {
      "type": "object", "required": ["name", "class", "k", "k_condition", "facts"], "additionalProperties": false,
      "properties": {
        "name": { "$ref": "urn:sentilab:package3d:common:1#/$defs/text" },
        "class": { "enum": ["semiconductor", "metal", "solder", "polymer", "composite", "ceramic", "fluid", "mixed", "unknown"] },
        "k": { "$ref": "#/$defs/aq" },
        "k_condition": { "enum": ["near_room_temperature", "not_stated"] },
        "facts": { "$ref": "#/$defs/facts" },
        "note": { "$ref": "urn:sentilab:package3d:common:1#/$defs/text" },
        "swatch": { "type": "string", "pattern": "^#[0-9a-f]{6}$" }
      }
    },
    "partType": {
      "type": "object",
      "required": ["name", "kind", "parent_type", "level", "variants", "material", "material_text", "thickness", "footprint", "count", "function", "explanation", "confidence", "facts"],
      "additionalProperties": false,
      "properties": {
        "name": { "$ref": "urn:sentilab:package3d:common:1#/$defs/text" },
        "kind": { "enum": ["board", "region", "array", "layer", "die", "die_stack", "fill", "lid", "cooler", "fluid", "assembly"] },
        "parent_type": { "oneOf": [ { "$ref": "urn:sentilab:package3d:common:1#/$defs/typeId" }, { "type": "null" } ] },
        "level": { "type": ["number", "null"] },
        "variants": { "type": "array", "minItems": 1, "uniqueItems": true, "items": { "$ref": "urn:sentilab:package3d:common:1#/$defs/variant" } },
        "material": { "oneOf": [ { "$ref": "urn:sentilab:package3d:common:1#/$defs/slug" }, { "type": "null" } ] },
        "material_text": { "$ref": "urn:sentilab:package3d:common:1#/$defs/text" },
        "thickness": { "$ref": "#/$defs/aq" },
        "footprint": {
          "type": "object", "required": ["w", "h", "area", "pattern"], "additionalProperties": false,
          "properties": { "w": { "$ref": "#/$defs/aq" }, "h": { "$ref": "#/$defs/aq" }, "area": { "$ref": "#/$defs/aq" }, "pattern": { "$ref": "urn:sentilab:package3d:common:1#/$defs/text" } }
        },
        "count": { "$ref": "#/$defs/aq" },
        "function": { "$ref": "urn:sentilab:package3d:common:1#/$defs/text" },
        "explanation": {
          "type": "object", "required": ["what", "why", "facts"], "additionalProperties": false,
          "properties": { "what": { "$ref": "urn:sentilab:package3d:common:1#/$defs/text" }, "why": { "$ref": "urn:sentilab:package3d:common:1#/$defs/text" }, "facts": { "$ref": "#/$defs/facts" } }
        },
        "confidence": { "enum": ["high", "medium", "low"] },
        "facts": { "$ref": "#/$defs/facts" },
        "note": { "$ref": "urn:sentilab:package3d:common:1#/$defs/text" }
      }
    },
    "interconnectClass": {
      "type": "object", "required": ["name", "kind", "pitch", "diameter", "height", "count", "facts"], "additionalProperties": false,
      "properties": {
        "name": { "$ref": "urn:sentilab:package3d:common:1#/$defs/text" },
        "kind": { "enum": ["bump_array", "bond", "ball_array", "via_array", "wiring", "bus", "link", "delivery_chain"] },
        "pitch": { "$ref": "#/$defs/aq" }, "diameter": { "$ref": "#/$defs/aq" }, "height": { "$ref": "#/$defs/aq" }, "count": { "$ref": "#/$defs/aq" },
        "material_text": { "$ref": "urn:sentilab:package3d:common:1#/$defs/text" },
        "electrical": {
          "type": "object", "additionalProperties": false,
          "properties": { "width": { "$ref": "#/$defs/aq" }, "rate": { "$ref": "#/$defs/aq" }, "bandwidth": { "$ref": "#/$defs/aq" }, "energy": { "$ref": "#/$defs/aq" }, "voltage": { "$ref": "#/$defs/aq" }, "current": { "$ref": "#/$defs/aq" } }
        },
        "facts": { "$ref": "#/$defs/facts" },
        "note": { "$ref": "urn:sentilab:package3d:common:1#/$defs/text" }
      }
    },
    "typeEdge": {
      "type": "object", "required": ["from", "to", "kinds", "via", "basis", "facts"], "additionalProperties": false,
      "properties": {
        "from": { "$ref": "urn:sentilab:package3d:common:1#/$defs/typeId" },
        "to": { "$ref": "urn:sentilab:package3d:common:1#/$defs/typeId" },
        "kinds": { "type": "array", "minItems": 1, "uniqueItems": true, "items": { "$ref": "urn:sentilab:package3d:common:1#/$defs/connection" } },
        "via": { "oneOf": [ { "$ref": "urn:sentilab:package3d:common:1#/$defs/slug" }, { "type": "null" } ] },
        "basis": { "enum": ["sourced", "lane1_typical"] },
        "facts": { "$ref": "#/$defs/facts" }
      }
    },
    "flow": {
      "type": "object", "required": ["id", "kind", "name", "variants", "steps", "share", "facts", "qualifier"], "additionalProperties": false,
      "properties": {
        "id": { "$ref": "urn:sentilab:package3d:common:1#/$defs/slug" },
        "kind": { "enum": ["heat", "power", "signal"] },
        "name": { "$ref": "urn:sentilab:package3d:common:1#/$defs/text" },
        "variants": { "type": "array", "minItems": 1, "items": { "$ref": "urn:sentilab:package3d:common:1#/$defs/variant" } },
        "steps": {
          "type": "array", "minItems": 2,
          "items": { "oneOf": [
            { "type": "object", "required": ["part"], "additionalProperties": false, "properties": { "part": { "$ref": "urn:sentilab:package3d:common:1#/$defs/typeId" } } },
            { "type": "object", "required": ["any_of"], "additionalProperties": false, "properties": { "any_of": { "type": "array", "minItems": 2, "uniqueItems": true, "items": { "$ref": "urn:sentilab:package3d:common:1#/$defs/typeId" } } } }
          ] }
        },
        "share": { "oneOf": [ { "$ref": "#/$defs/aq" }, { "type": "null" } ] },
        "contested": {
          "type": "array",
          "items": { "type": "object", "required": ["claim", "facts"], "additionalProperties": false,
                     "properties": { "claim": { "$ref": "urn:sentilab:package3d:common:1#/$defs/text" }, "facts": { "$ref": "#/$defs/facts" } } }
        },
        "facts": { "$ref": "#/$defs/facts" },
        "qualifier": { "const": "Typical path through the parts. Not a solved heat flux, not a routed wire, not a measured bandwidth." }
      }
    }
  }
}
```

Under `names_policy: "generic"` a source carries only `type`, `kind` and `year` (D1); `title`, `publisher`, `url` and
`sha256` appear only under `"named"`. Every served `claim` is a generic rewrite of the lane-1 fact claim that keeps
every number of the original (checked mechanically, AC-40) and contains no temperature (PL-4).

### 5.3 Assembly `sentilab-assembly/1` (instances, transforms, edges)

Served at `/sentilab/package3d/data/assembly-<id>.json`. Phase 1 ships one assembly, `typ-1c4m` (one compute die,
four HBM stacks, silicon interposer, `lidded` and `lidless` variants, liquid cold plate; D11), built from a reviewed
source file in `docs/sentilab/package3d/`.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:sentilab:package3d:assembly:1",
  "type": "object",
  "required": ["schema", "content", "id", "title", "status_text", "names_policy", "anatomy_sha256", "frame", "arrangement", "variants_offered", "instances", "edges", "retired_ids", "omitted", "geometry_sha256"],
  "additionalProperties": false,
  "properties": {
    "schema": { "const": "sentilab-assembly/1" },
    "content": { "const": "anatomy" },
    "id": { "$ref": "urn:sentilab:package3d:common:1#/$defs/slug" },
    "title": { "$ref": "urn:sentilab:package3d:common:1#/$defs/text" },
    "status_text": { "const": "Typical anatomy · a representative reconstruction from public sources. Not any manufacturer's CAD. Not silicon-validated. Arrangement schematic; unknown values are marked." },
    "names_policy": { "enum": ["generic", "named"] },
    "anatomy_sha256": { "$ref": "urn:sentilab:package3d:common:1#/$defs/sha256" },
    "frame": { "const": { "length_unit": "mm", "origin": "interposer lower-left corner, on the interposer's bottom face", "x": "right", "y": "up in plan view", "z": "out of the board, toward the cooler" } },
    "arrangement": { "enum": ["schematic", "sourced"] },
    "variants_offered": { "type": "array", "minItems": 1, "uniqueItems": true, "items": { "$ref": "urn:sentilab:package3d:common:1#/$defs/variant" } },
    "instances": { "type": "array", "minItems": 1, "items": { "$ref": "#/$defs/instance" } },
    "edges": { "type": "array", "items": { "$ref": "#/$defs/instanceEdge" } },
    "retired_ids": { "type": "array", "uniqueItems": true, "items": { "$ref": "urn:sentilab:package3d:common:1#/$defs/instanceId" } },
    "omitted": { "type": "array", "items": { "$ref": "urn:sentilab:package3d:common:1#/$defs/omission" } },
    "geometry_sha256": { "$ref": "urn:sentilab:package3d:common:1#/$defs/sha256" }
  },
  "$defs": {
    "drawnBasis": { "enum": ["sourced", "derived", "render_hint"] },
    "instance": { "oneOf": [ { "$ref": "#/$defs/drawnInstance" }, { "$ref": "#/$defs/undrawnInstance" } ] },
    "drawnInstance": {
      "type": "object", "required": ["id", "type", "parent", "label", "variants", "drawn", "box", "basis"], "additionalProperties": false,
      "properties": {
        "id": { "$ref": "urn:sentilab:package3d:common:1#/$defs/instanceId" },
        "type": { "$ref": "urn:sentilab:package3d:common:1#/$defs/typeId" },
        "parent": { "oneOf": [ { "$ref": "urn:sentilab:package3d:common:1#/$defs/instanceId" }, { "type": "null" } ] },
        "label": { "$ref": "urn:sentilab:package3d:common:1#/$defs/text" },
        "variants": { "type": "array", "minItems": 1, "uniqueItems": true, "items": { "$ref": "urn:sentilab:package3d:common:1#/$defs/variant" } },
        "drawn": { "const": true },
        "box": { "$ref": "urn:sentilab:package3d:common:1#/$defs/box" },
        "basis": {
          "type": "object", "required": ["position", "footprint", "thickness"], "additionalProperties": false,
          "properties": { "position": { "$ref": "#/$defs/drawnBasis" }, "footprint": { "$ref": "#/$defs/drawnBasis" }, "thickness": { "$ref": "#/$defs/drawnBasis" } }
        },
        "dims": {
          "type": "object", "additionalProperties": false,
          "properties": { "w": { "$ref": "urn:sentilab:package3d:anatomy:1#/$defs/aq" }, "h": { "$ref": "urn:sentilab:package3d:anatomy:1#/$defs/aq" }, "t": { "$ref": "urn:sentilab:package3d:anatomy:1#/$defs/aq" } }
        },
        "array": {
          "type": "object", "required": ["class", "region", "pitch", "diameter", "height", "count", "lattice"], "additionalProperties": false,
          "properties": {
            "class": { "$ref": "urn:sentilab:package3d:common:1#/$defs/slug" },
            "region": { "$ref": "urn:sentilab:package3d:common:1#/$defs/rect" },
            "pitch": { "$ref": "urn:sentilab:package3d:anatomy:1#/$defs/aq" },
            "diameter": { "$ref": "urn:sentilab:package3d:anatomy:1#/$defs/aq" },
            "height": { "$ref": "urn:sentilab:package3d:anatomy:1#/$defs/aq" },
            "count": { "$ref": "urn:sentilab:package3d:anatomy:1#/$defs/aq" },
            "lattice": { "enum": ["square", "staggered", "unknown"] }
          }
        },
        "note": { "$ref": "urn:sentilab:package3d:common:1#/$defs/text" }
      }
    },
    "undrawnInstance": {
      "type": "object", "required": ["id", "type", "parent", "label", "variants", "drawn", "dims"], "additionalProperties": false,
      "properties": {
        "id": { "$ref": "urn:sentilab:package3d:common:1#/$defs/instanceId" },
        "type": { "$ref": "urn:sentilab:package3d:common:1#/$defs/typeId" },
        "parent": { "oneOf": [ { "$ref": "urn:sentilab:package3d:common:1#/$defs/instanceId" }, { "type": "null" } ] },
        "label": { "$ref": "urn:sentilab:package3d:common:1#/$defs/text" },
        "variants": { "type": "array", "minItems": 1, "uniqueItems": true, "items": { "$ref": "urn:sentilab:package3d:common:1#/$defs/variant" } },
        "drawn": { "const": false },
        "dims": {
          "type": "object", "required": ["w", "h", "t"], "additionalProperties": false,
          "properties": { "w": { "$ref": "urn:sentilab:package3d:anatomy:1#/$defs/aq" }, "h": { "$ref": "urn:sentilab:package3d:anatomy:1#/$defs/aq" }, "t": { "$ref": "urn:sentilab:package3d:anatomy:1#/$defs/aq" } }
        },
        "note": { "$ref": "urn:sentilab:package3d:common:1#/$defs/text" }
      }
    },
    "instanceEdge": {
      "type": "object", "required": ["id", "from", "to", "kinds", "via", "type_edge"], "additionalProperties": false,
      "properties": {
        "id": { "$ref": "urn:sentilab:package3d:common:1#/$defs/slug" },
        "from": { "$ref": "urn:sentilab:package3d:common:1#/$defs/instanceId" },
        "to": { "$ref": "urn:sentilab:package3d:common:1#/$defs/instanceId" },
        "kinds": { "type": "array", "minItems": 1, "uniqueItems": true, "items": { "$ref": "urn:sentilab:package3d:common:1#/$defs/connection" } },
        "via": { "oneOf": [ { "$ref": "urn:sentilab:package3d:common:1#/$defs/instanceId" }, { "type": "null" } ] },
        "type_edge": { "type": "string", "pattern": "^[a-z][a-z0-9_]*->[a-z][a-z0-9_]*$" }
      }
    }
  }
}
```

Reader rules beyond the schema: a drawn instance's `box` is assembled and in mm with `x0 < x1`, `y0 < y1`,
`z0 < z1`, and agrees with its quantities (a `sourced` thickness is drawn at its value, or inside its range when only a
range exists; a `render_hint` is drawn at the hint). **Drawn or undrawn is a union, not a flag** (A#57218 item 1). An
undrawn instance (`drawn: false`: size unknown and no hint) has no `box`, `basis` or `array`; the reader refuses any of
them on it instead of drawing an invented box. It keeps its id, type, parent, label, variants and every edge that
names it, and carries `dims` with `value: null` and `basis: "unknown"` wherever the size is unknown. At least one of
its dimensions has no drawable value (`drawnMm()` returns null); a part whose every dimension can be drawn is drawn.
Undrawn parts appear in the part tree as `not drawn · size unknown`, keep their connections in the panel and the
twin, and are left out of the RenderModel's boxes and bounds, picking, section rectangles and every field
association. Every `type_edge` exists in the anatomy's `type_edges`; a drawn child lies inside the footprint of its
nearest drawn ancestor; children that do not sum to their parent's sourced height are not stretched, and the residual
is shown as a labelled gap (PL-10). `geometry_sha256` follows the frozen preimage of section 5.0
(`sentilab-geometry/1`); the page recomputes it and refuses a mismatch (`hash_mismatch`).

### 5.4 Model stack `sentilab-model-stack/1` (what the solver simulates)

Served at `/sentilab/package3d/data/model-stack.json`. Hand-transcribed from the code at a pinned commit, with a
citation on every value, and checked by a Python test that runs TAP's floorplan writer (never HotSpot) for every
fixture and compares (W4, AC-16).

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:sentilab:package3d:model-stack:1",
  "type": "object",
  "required": ["schema", "content", "status_text", "code", "materials_as_coded", "layers", "boundary", "fixtures", "not_modelled", "simplifications"],
  "additionalProperties": false,
  "properties": {
    "schema": { "const": "sentilab-model-stack/1" },
    "content": { "const": "model" },
    "status_text": { "const": "Our model · the layers and blocks our thermal solver actually simulates, with its simplifications. Not the real package." },
    "code": {
      "type": "object", "required": ["commit", "files"], "additionalProperties": false,
      "properties": { "commit": { "$ref": "urn:sentilab:package3d:common:1#/$defs/commit" }, "files": { "type": "array", "minItems": 1, "items": { "$ref": "urn:sentilab:package3d:common:1#/$defs/pinnedFile" } } }
    },
    "materials_as_coded": {
      "type": "object", "propertyNames": { "$ref": "urn:sentilab:package3d:common:1#/$defs/slug" },
      "additionalProperties": {
        "type": "object", "required": ["resistivity_mK_per_W", "heat_capacity_J_per_m3K", "k_W_per_mK", "derivation", "cite"], "additionalProperties": false,
        "properties": {
          "resistivity_mK_per_W": { "type": "number", "exclusiveMinimum": 0 },
          "heat_capacity_J_per_m3K": { "type": "number", "exclusiveMinimum": 0 },
          "k_W_per_mK": { "type": "number", "exclusiveMinimum": 0 },
          "derivation": { "$ref": "urn:sentilab:package3d:common:1#/$defs/text" },
          "cite": { "type": "array", "minItems": 1, "items": { "$ref": "urn:sentilab:package3d:common:1#/$defs/cite" } }
        }
      }
    },
    "layers": { "type": "array", "minItems": 8, "maxItems": 8, "items": { "$ref": "#/$defs/modelLayer" } },
    "boundary": {
      "type": "object", "required": ["bottom", "top", "temperature_inputs", "cite"], "additionalProperties": false,
      "properties": {
        "bottom": { "const": "adiabatic: no heat leaves through the bottom of layer 0 (secondary path off)" },
        "top": { "$ref": "urn:sentilab:package3d:common:1#/$defs/text" },
        "temperature_inputs": {
          "type": "array",
          "items": { "type": "object", "required": ["name", "cite", "rendered", "why"], "additionalProperties": false,
                     "properties": { "name": { "enum": ["ambient", "initial", "dtm_threshold"] }, "cite": { "$ref": "urn:sentilab:package3d:common:1#/$defs/cite" }, "rendered": { "const": false }, "why": { "$ref": "urn:sentilab:package3d:common:1#/$defs/text" } } }
        },
        "cite": { "type": "array", "items": { "$ref": "urn:sentilab:package3d:common:1#/$defs/cite" } }
      }
    },
    "fixtures": { "type": "array", "minItems": 1, "items": { "$ref": "#/$defs/fixture" } },
    "not_modelled": { "type": "array", "uniqueItems": true, "items": { "$ref": "urn:sentilab:package3d:common:1#/$defs/typeId" } },
    "simplifications": {
      "type": "array",
      "items": { "type": "object", "required": ["id", "rank", "text", "cite"], "additionalProperties": false,
                 "properties": { "id": { "type": "string", "pattern": "^S[0-9]{1,2}$" }, "rank": { "type": "integer", "minimum": 1 }, "text": { "$ref": "urn:sentilab:package3d:common:1#/$defs/text" }, "cite": { "type": "array", "items": { "$ref": "urn:sentilab:package3d:common:1#/$defs/cite" } } } }
    }
  },
  "$defs": {
    "modelLayer": {
      "type": "object",
      "required": ["grid_index", "lcf_index", "name", "role", "thickness_m", "lateral", "material", "units", "powered", "stands_for", "simplifications", "cite", "index_basis"],
      "additionalProperties": false,
      "properties": {
        "grid_index": { "type": "integer", "minimum": 0, "maximum": 7 },
        "lcf_index": { "oneOf": [ { "type": "integer", "minimum": 0, "maximum": 5 }, { "type": "null" } ] },
        "name": { "$ref": "urn:sentilab:package3d:common:1#/$defs/text" },
        "role": { "enum": ["lcf", "spreader", "sink"] },
        "thickness_m": { "type": "number", "exclusiveMinimum": 0 },
        "lateral": {
          "type": "object", "required": ["rule", "grid_extent", "note"], "additionalProperties": false,
          "properties": { "rule": { "enum": ["interposer", "2x_interposer", "4x_interposer"] }, "grid_extent": { "const": "interposer" }, "note": { "$ref": "urn:sentilab:package3d:common:1#/$defs/text" } }
        },
        "material": { "$ref": "urn:sentilab:package3d:common:1#/$defs/slug" },
        "units": {
          "type": "array",
          "items": { "type": "object", "required": ["pattern", "material", "meaning"], "additionalProperties": false,
                     "properties": { "pattern": { "type": "string", "pattern": "^(Chiplet|Ubump|Edge|Unit|Substrate|C4Layer|Interposer|TIM|fill)(_\\*)?$" }, "material": { "$ref": "urn:sentilab:package3d:common:1#/$defs/slug" }, "meaning": { "$ref": "urn:sentilab:package3d:common:1#/$defs/text" } } }
        },
        "powered": { "type": "boolean" },
        "stands_for": { "type": "array", "uniqueItems": true, "items": { "$ref": "urn:sentilab:package3d:common:1#/$defs/typeId" } },
        "simplifications": { "type": "array", "items": { "type": "string", "pattern": "^S[0-9]{1,2}$" } },
        "cite": { "type": "array", "minItems": 1, "items": { "$ref": "urn:sentilab:package3d:common:1#/$defs/cite" } },
        "index_basis": { "enum": ["code_reading", "producer_confirmed"] }
      }
    },
    "fixture": {
      "type": "object",
      "required": ["fixture_id", "title", "config", "interposer_mm", "spreader_mm", "sink_mm", "dies", "netlist", "legality", "layouts", "role_basis"],
      "additionalProperties": false,
      "properties": {
        "fixture_id": { "enum": ["ascend910", "ascend910-45mm", "micro150", "micro150-45mm"] },
        "title": { "$ref": "urn:sentilab:package3d:common:1#/$defs/text" },
        "config": { "$ref": "urn:sentilab:package3d:common:1#/$defs/pinnedFile" },
        "interposer_mm": { "type": "number", "exclusiveMinimum": 0 },
        "spreader_mm": { "type": "number", "exclusiveMinimum": 0 },
        "sink_mm": { "type": "number", "exclusiveMinimum": 0 },
        "dies": {
          "type": "array", "minItems": 1,
          "items": {
            "type": "object", "required": ["index", "chiplet_id", "role", "anatomy_type", "w_mm", "h_mm", "power_W", "halo_mm", "cite"], "additionalProperties": false,
            "properties": {
              "index": { "type": "integer", "minimum": 0 },
              "chiplet_id": { "type": "string", "pattern": "^tap-chiplet-[0-9]+$" },
              "role": { "enum": ["compute", "io", "memory_hbm_block", "memory_dram_block"] },
              "anatomy_type": { "oneOf": [ { "$ref": "urn:sentilab:package3d:common:1#/$defs/typeId" }, { "type": "null" } ] },
              "w_mm": { "type": "number", "exclusiveMinimum": 0 },
              "h_mm": { "type": "number", "exclusiveMinimum": 0 },
              "power_W": { "type": "number", "minimum": 0 },
              "halo_mm": { "type": ["number", "null"], "minimum": 0 },
              "cite": { "$ref": "urn:sentilab:package3d:common:1#/$defs/cite" }
            }
          }
        },
        "netlist": {
          "type": "object", "required": ["matrix", "meaning", "cite"], "additionalProperties": false,
          "properties": {
            "matrix": { "type": "array", "items": { "type": "array", "items": { "type": "integer", "minimum": 0 } } },
            "meaning": { "const": "TAP connection weights between dies, as configured. Not routed wires and not bandwidth." },
            "cite": { "$ref": "urn:sentilab:package3d:common:1#/$defs/cite" }
          }
        },
        "legality": {
          "type": "object", "required": ["center_lattice_mm", "min_die_gap_mm", "rotation", "cite"], "additionalProperties": false,
          "properties": {
            "center_lattice_mm": { "type": ["number", "null"] },
            "min_die_gap_mm": { "type": ["number", "null"] },
            "rotation": { "enum": ["catalog", "per_die_90"] },
            "cite": { "oneOf": [ { "$ref": "urn:sentilab:package3d:common:1#/$defs/cite" }, { "type": "null" } ] }
          }
        },
        "layouts": { "type": "array", "items": { "$ref": "urn:sentilab:package3d:common:1#/$defs/slug" } },
        "role_basis": { "$ref": "urn:sentilab:package3d:common:1#/$defs/text" }
      }
    }
  }
}
```

The initial content (transcribed and to be confirmed by AC-16):

| grid | LCF | Layer (as coded) | Thickness | Material as coded (k = 1 / resistivity) | Stands for (anatomy) | Cite (origin/main) |
|---|---|---|---|---|---|---|
| 0 | 0 | substrate | 200 µm | 3.33 m·K/W (k 0.30) | `package_substrate`, `substrate_*` | sundai_tap/passive_interposer.py:144, :50-56 |
| 1 | 1 | Epoxy SiO2 underfill with C4 copper pillar | 70 µm | layer underfill 0.625 (k 1.6); unit `C4Layer` mix k ≈ 70.8 (250 µm "Cu" on a 600 µm cell) | `c4_bumps`, `c4_underfill` | :145, :31-32, :37-48, :59-65 |
| 2 | 2 | silicon interposer | 110 µm | silicon 0.01 (k 100); unit `Interposer` TSV mix k ≈ 112 (10 µm on a 50 µm cell) | `interposer_silicon`, `interposer_tsv` | :146, :33-34, :68-74 |
| 3 | 3 | Underfill with ubump | 10 µm | underfill; `Chiplet_*`, `Ubump_*`, `Edge_*` use the bump mix k ≈ 124.6 (25 µm on a 45 µm cell) | `microbumps`, `microbump_underfill` | :147, :35-36, :90-93, :105-108, :115, :121 |
| 4 | 4 | Chip layer (the only powered layer) | 150 µm | silicon for `Chiplet_*` and halo `Ubump_*`; bump mix on `Edge_*`; underfill whitespace | `compute_die`, `io_die`, `hbm_stack`, `mold_compound` (gaps) | :148, :94-97, :109-112, :116, :122, :182-195 |
| 5 | 5 | TIM | 20 µm | 0.25 (k 4) | `tim1` | :149, :126-132 |
| 6 | none | spreader (appended) | 1 mm | k 400; side 2 x interposer | `lid` | sundai_tap/util/hotspot.config:29-35; passive_interposer.py:154, :160-161; temperature_grid.c:529, :532-541 |
| 7 | none | sink (appended) + lumped convection | 6.9 mm | k 400; side 2 x spreader; `r_convec = 0.1 x 0.06² / s_sink²` | `heat_sink`, `cold_plate`, `coolant` (stand-in) | hotspot.config:15-25; passive_interposer.py:155-163; temperature_grid.c:530, :543-552 |

Index basis for grid layers 6 and 7 is `code_reading`: `DEFAULT_PACK_LAYERS 2`, `LAYER_SP 0`, `LAYER_SINK 1`
(main:sundai_hotspot/temperature_grid.h:46-48) put the spreader at index 6 and the sink at 7 for 8 layers, and both
reuse the TIM layer's floorplan mapping (temperature_grid.c:539-541, :550-552), so their grid covers the interposer
area, not the full 90 mm and 180 mm squares. The producer confirms this (P7) before any field is drawn on them.

Boundary: bottom adiabatic (`-model_secondary 0`, hotspot.config:48); ambient and initial temperature are
temperature-valued inputs (hotspot.config:78, :82) and the DTM threshold another (:11); all three are listed in
`boundary.temperature_inputs` with `rendered: false` (PL-4, D2). Solver arguments (`-model_type grid -detailed_3D on
-grid_map_mode max`, tap_oracle_worker.py:356-369) are listed as model facts.

Fixture role map (for the model and for results): `ascend910*`: die 0 compute, die 1 I/O, dies 2-5 HBM blocks;
`micro150*`: dies 0-3 compute (CPU), dies 4-7 DRAM blocks (no anatomy counterpart: `anatomy_type: null`). Basis:
TAP-2.5D Table II (thm-007), main:docs/sentilab/references/README.md:5-7 and :86, and the configs
(main:sundai_tap/configs/sys_ascend910_45mm.cfg:19-28; sys_micro150_45mm.cfg:19-30). Halo widths come from the
floorplan writer's output (`Ubump_*` units, passive_interposer.py:102-113), recorded by the W4 check, never guessed.

Simplifications S1-S9 are lane 1's ranked list, verbatim in meaning, with its citations (L1:our_model_mapping.md §4);
the panel shows them where they apply (for example S1 on every HBM block: "a 150 µm, 20 W silicon block; the real
stack is about 720 µm with bond layers").

### 5.5 Reference layouts `sentilab-layouts/1`

Served at `/sentilab/package3d/data/layouts.json`; generated from `docs/sentilab/references/*.json` by
`scripts/package3d.mjs data`, which recomputes every `content_sha256` from `identity.canonical` with a number-text
preserving parser (verify-core.js `parseRaw`, `canonical`) and refuses to build on any mismatch.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:sentilab:package3d:layouts:1",
  "type": "object",
  "required": ["schema", "content", "status_text", "layouts", "omitted"],
  "additionalProperties": false,
  "properties": {
    "schema": { "const": "sentilab-layouts/1" },
    "content": { "const": "model" },
    "status_text": { "const": "Reference layouts reconstructed from a published figure. Not CAD, not silicon, not measured." },
    "layouts": {
      "type": "array", "minItems": 1,
      "items": {
        "type": "object",
        "required": ["variant_id", "reference_id", "fixture_id", "kind", "label", "role", "frame_mm", "centers_mm", "footprints_mm", "rotated", "content_sha256", "source", "wire_proxy_mm", "routed_wire_mm"],
        "additionalProperties": false,
        "properties": {
          "variant_id": { "$ref": "urn:sentilab:package3d:common:1#/$defs/slug" },
          "reference_id": { "$ref": "urn:sentilab:package3d:common:1#/$defs/slug" },
          "fixture_id": { "enum": ["ascend910-45mm", "micro150-45mm"] },
          "kind": { "enum": ["raw", "snap0p5"] },
          "label": { "$ref": "urn:sentilab:package3d:common:1#/$defs/text" },
          "role": { "$ref": "urn:sentilab:package3d:common:1#/$defs/text" },
          "frame_mm": { "type": "number", "exclusiveMinimum": 0 },
          "centers_mm": { "type": "array", "items": { "type": "array", "minItems": 2, "maxItems": 2, "items": { "type": "number" } } },
          "footprints_mm": { "type": "array", "items": { "type": "array", "minItems": 2, "maxItems": 2, "items": { "type": "number", "exclusiveMinimum": 0 } } },
          "rotated": { "type": "array", "items": { "type": "boolean" } },
          "content_sha256": { "$ref": "urn:sentilab:package3d:common:1#/$defs/sha256" },
          "source": { "$ref": "urn:sentilab:package3d:common:1#/$defs/pinnedFile" },
          "wire_proxy_mm": { "type": ["number", "null"] },
          "routed_wire_mm": { "type": ["number", "null"] }
        }
      }
    },
    "omitted": { "type": "array", "items": { "$ref": "urn:sentilab:package3d:common:1#/$defs/omission" } }
  }
}
```

Phase 1 serves the two raw and the two 0.5 mm layouts; the 1 mm snapped variants are omitted with the reason
"superseded as the baseline" (README.md:22; the same choice as pr66:web/public/agents/references/ascend910-tap25d-fig6a.json:282-290).
Paper-reported temperatures, round-trip plans and validation points are omitted (PL-4). `footprints_mm` are the
turned footprints (the identity's own convention: README.md:53-59; config die 0 is 14.5 x 31.4 and the raw
`rotated[0]` is true, so its footprint is 31.4 x 14.5). `wire_proxy_mm` and `routed_wire_mm` are separate statistics
(PL-9).

### 5.6 Result view `sentilab-result/1` (binding to receipts)

Not a served file: computed by `results.mjs` from the verified prefix, shown by the page and written by the CLI into
result twins.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:sentilab:package3d:result:1",
  "type": "object",
  "required": ["schema", "content", "status_text", "run", "prefix", "layout", "model", "values", "field", "receipt_completeness", "refused"],
  "additionalProperties": false,
  "properties": {
    "schema": { "const": "sentilab-result/1" },
    "content": { "const": "result" },
    "status_text": { "const": "Results · from signed, verified evidence only. Each value names its run, geometry, evaluator and label. Simulated, not silicon." },
    "run": {
      "type": "object", "required": ["run_id", "family", "arm", "seed"], "additionalProperties": false,
      "properties": { "run_id": { "type": "string" }, "family": { "type": ["string", "null"] }, "arm": { "type": ["string", "null"] }, "seed": { "type": ["integer", "null"] } }
    },
    "prefix": {
      "type": "object", "required": ["K", "total", "frozen", "mode", "mode_label", "at_seq"], "additionalProperties": false,
      "properties": {
        "K": { "type": "integer", "minimum": 0 }, "total": { "type": "integer", "minimum": 0 }, "frozen": { "type": "boolean" },
        "mode": { "enum": ["REPLAY", "LIVE", "STALE", "ENDED"] }, "mode_label": { "type": "string" }, "at_seq": { "type": "integer", "minimum": 0 }
      }
    },
    "layout": {
      "oneOf": [ { "type": "null" }, {
        "type": "object", "required": ["node", "track", "candidate_event", "units", "chiplets", "reference_match"], "additionalProperties": false,
        "properties": {
          "node": { "type": "string" }, "track": { "type": "string" },
          "candidate_event": { "$ref": "#/$defs/receipt" },
          "units": { "const": "mm" },
          "chiplets": { "type": "array", "items": { "type": "object", "required": ["id", "x", "y", "w", "h", "layer", "role"], "additionalProperties": false,
            "properties": { "id": { "type": "string" }, "x": { "type": "number" }, "y": { "type": "number" }, "w": { "type": "number" }, "h": { "type": "number" }, "layer": { "type": "integer" }, "role": { "enum": ["compute", "io", "memory_hbm_block", "memory_dram_block", "unknown"] } } } },
          "reference_match": { "oneOf": [ { "type": "null" }, { "type": "object", "required": ["variant_id", "content_sha256", "max_abs_diff_mm"], "additionalProperties": false,
            "properties": { "variant_id": { "type": "string" }, "content_sha256": { "$ref": "urn:sentilab:package3d:common:1#/$defs/sha256" }, "max_abs_diff_mm": { "type": "number", "minimum": 0 } } } ] }
        }
      } ]
    },
    "model": {
      "type": "object", "required": ["fixture_id", "model_stack_sha256", "status"], "additionalProperties": false,
      "properties": { "fixture_id": { "type": ["string", "null"] }, "model_stack_sha256": { "oneOf": [ { "$ref": "urn:sentilab:package3d:common:1#/$defs/sha256" }, { "type": "null" } ] }, "status": { "enum": ["bound", "unknown_family"] } }
    },
    "values": { "type": "array", "items": { "$ref": "#/$defs/resultValue" } },
    "field": { "oneOf": [ { "type": "null" }, { "$ref": "#/$defs/fieldStatus" } ] },
    "receipt_completeness": {
      "type": "object", "required": ["evaluator_identity", "geometry_signed", "input_hashes", "argv", "power_trace", "field"], "additionalProperties": false,
      "properties": {
        "evaluator_identity": { "type": "boolean" }, "geometry_signed": { "type": "boolean" },
        "input_hashes": { "enum": ["named", "unnamed", "absent"] }, "argv": { "enum": ["present", "absent"] },
        "power_trace": { "enum": ["named", "in_unnamed_list", "absent"] }, "field": { "enum": ["verified", "refused", "absent"] }
      }
    },
    "refused": { "type": "array", "items": { "type": "object", "required": ["node", "field", "code", "detail"], "additionalProperties": false,
      "properties": { "node": { "type": "string" }, "field": { "type": "string" }, "code": { "type": "string" }, "detail": { "type": "string" } } } }
  },
  "$defs": {
    "receipt": {
      "type": "object", "required": ["seq", "event_id", "hash"], "additionalProperties": false,
      "properties": { "seq": { "type": "integer", "minimum": 1 }, "event_id": { "type": "string" }, "hash": { "$ref": "urn:sentilab:package3d:common:1#/$defs/sha256" } }
    },
    "resultValue": {
      "type": "object", "required": ["quantity", "statistic", "value", "unit", "declared_unit", "association", "measurement", "evaluator_identity", "label", "validity", "as_of_seq"], "additionalProperties": false,
      "properties": {
        "quantity": { "enum": ["J", "W", "center_temp", "field_layer_min", "field_layer_max"] },
        "statistic": { "enum": ["chip_layer_grid_max", "chiplet_centre", "field_cell", "all_layers_grid_max", "chiplet_unit_native", "tap_selector", "wire_proxy_weighted_manhattan", "routed_wire_open_router"] },
        "value": { "type": "number" },
        "unit": { "enum": ["degC", "mm"] },
        "declared_unit": { "type": ["string", "null"] },
        "association": { "type": "object", "additionalProperties": false,
          "properties": { "chiplet": { "type": "string" }, "layer": { "type": "integer", "minimum": 0, "maximum": 15 }, "scope": { "type": "string" } } },
        "measurement": { "type": "object", "required": ["node", "receipt"], "additionalProperties": false,
          "properties": { "node": { "type": "string" }, "receipt": { "$ref": "#/$defs/receipt" } } },
        "evaluator_identity": { "type": ["string", "null"] },
        "label": { "oneOf": [ { "$ref": "urn:sentilab:package3d:common:1#/$defs/label" }, { "type": "null" } ] },
        "validity": { "enum": ["valid", "stale"] },
        "as_of_seq": { "type": "integer", "minimum": 1 }
      },
      "if": { "properties": { "unit": { "const": "degC" } } },
      "then": { "properties": { "label": { "$ref": "urn:sentilab:package3d:common:1#/$defs/label" } } }
    },
    "fieldStatus": {
      "type": "object", "required": ["sha256", "format", "rows", "cols", "layers", "status", "as_of_seq"], "additionalProperties": false,
      "properties": {
        "sha256": { "$ref": "urn:sentilab:package3d:common:1#/$defs/sha256" }, "format": { "const": "sentilab-field/0.1" },
        "rows": { "type": "integer" }, "cols": { "type": "integer" }, "layers": { "type": "integer" },
        "status": { "enum": ["verified", "refused", "loading", "unavailable"] }, "error": { "type": "string" },
        "stack_differs_from_manifest": { "type": "array", "items": { "type": "string" } },
        "as_of_seq": { "type": "integer", "minimum": 1 }
      }
    }
  }
}
```

Statistics (PL-9), each with where it comes from today:

| `statistic` | Meaning | Today |
|---|---|---|
| `chip_layer_grid_max` | J: the chip layer's grid maximum with `-grid_map_mode max` (`metric_id` `peak-chip-c`) | in every live measurement (conductor.py:342-344; tap_oracle_worker.py:368, :426) |
| `chiplet_centre` | `values.center_temps`, read in the J's unit | demo fixture and older rows (scene.mjs:148-162); not emitted by the live producer |
| `field_cell` | one cell of a verified field artifact, on one solver layer | none until P1-P4 |
| `all_layers_grid_max` | peak over all 8 layers | worker result only (tap_oracle_worker.py:427); not in any envelope |
| `chiplet_unit_native` | HotSpot's native per-unit temperatures of `Chiplet_i` | not emitted |
| `tap_selector` | TAP's own `run_hotspot()` selector with `-grid_map_mode center` | not computed (README.md:116-119) |
| `wire_proxy_weighted_manhattan` | W: connectivity-weighted Manhattan centre distance | every live measurement (conductor.py:345) |
| `routed_wire_open_router` | routed length from the open router | reference layouts only (README.md:96-108), never from an envelope |

Rules: a value's statistic comes from its `metric_id` and source field, never from a caption; values with different
statistics are never compared, ranked, differenced or put in one column. A value's `label` is the serialized record
of `labelFor(evaluator_identity)`; wherever it is read back it is recomputed and compared, never trusted (PL-2). `receipt_completeness` is shown as a chip on
every result (for today's live rows: evaluator identity yes, geometry signed yes, input hashes `unnamed`
(conductor.py:346), argv `absent`, power trace `in_unnamed_list`, field `absent`), so the binding astra asks for
(A#57059: geometry, material, power, layer, config, argv and executable identity) is shown as partial rather than
implied (P5, D12).

Geometry identity of a result is the candidate envelope's receipt (run, seq, event id, envelope hash): the envelope
hash already covers its `values.geometry` (main:contracts/view-envelope-v0.5/VIEW-ENVELOPE.md:31). A match to a
reference layout is numeric (centres within 1e-6 mm, rotations equal, same fixture), never a re-hash in JavaScript
(section 5.0).

### 5.7 Field artifact `sentilab-field/0.1` and its pointer (prerequisite formats)

Lane 3's proposal (L3:ARCHITECTURE §5.2) with three additions marked (+). Produced by the core, not by this build.

```json
{
  "format": "sentilab-field/0.1",
  "binding": { "run_id": "<run>", "measurement": "<node id>", "evaluator_version": "<identity>", "candidate_hash": "<64 hex> (+)", "problem_hash": "<64 hex> (+)" },
  "grid": { "rows": 32, "cols": 32, "extent_mm": { "x0": 0, "y0": 0, "x1": 45, "y1": 45 }, "row0": "top", "map_mode": "max (+)" },
  "unit": "K",
  "layers": [ { "index": 0, "name": "substrate", "thickness_m": 0.0002, "resistivity_mK_W": 3.33, "heat_capacity_J_m3K": 1060000, "powered": false, "source": "samplelayers.lcf" } ],
  "sources": { "samplelayers.lcf": "<64 hex>", "new_hotspot.config": "<64 hex>", "sample.ptrace": "<64 hex> (+)", "sample.grid.steady": "<64 hex>" },
  "argv": ["(+) the solver command line, as run"],
  "values": [ [ "rows x cols numbers per layer" ] ]
}
```

Pointer in the measurement envelope: `values.field = { "sha256", "format", "rows", "cols", "layers", "unit" }`.
Checks before anything is drawn (PSEUDOCODE §9, AC-21): allowlist (named by an applied measurement `node.create` in
the verified prefix), size cap (4 MiB), sha256 of the exact bytes, strict UTF-8 JSON, format, binding equals the
envelope (run, measurement, evaluator identity), (+) every input source hash (`samplelayers.lcf`,
`new_hotspot.config`, `sample.ptrace`) is a member of the envelope's signed `artifact_hashes`, dims equal the pointer
and the caps (at most 128 x 128, the worker's bound at tap_oracle_worker.py:283-287; at most 16 layers), every value
finite and inside scene.mjs `BOUNDS` after conversion (scene.mjs:92-98). A layer table that differs from the model
manifest is not refused: the artifact's table is the authority for that result, and the difference is listed
(`stack_differs_from_manifest`).

### 5.8 Agent twin `sentilab-twin/1`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "urn:sentilab:package3d:twin:1",
  "type": "object",
  "required": ["schema", "content", "status_text", "built_from", "frame", "view_transforms", "data", "labels", "omitted", "derivatives"],
  "additionalProperties": false,
  "properties": {
    "schema": { "const": "sentilab-twin/1" },
    "content": { "enum": ["anatomy", "model", "result"] },
    "status_text": { "type": "string" },
    "built_from": { "type": "array", "minItems": 1, "items": { "$ref": "urn:sentilab:package3d:common:1#/$defs/pinnedFile" } },
    "frame": { "type": "object" },
    "view_transforms": { "const": "Explode, readable thickening and section are view transforms. Every coordinate here is assembled." },
    "data": { "type": "object" },
    "labels": { "type": "array", "items": { "$ref": "urn:sentilab:package3d:common:1#/$defs/label" } },
    "omitted": { "type": "array", "items": { "$ref": "urn:sentilab:package3d:common:1#/$defs/omission" } },
    "derivatives": {
      "type": "array",
      "items": { "type": "object", "required": ["path", "sha256", "format", "units", "up", "note"], "additionalProperties": false,
        "properties": { "path": { "type": "string" }, "sha256": { "$ref": "urn:sentilab:package3d:common:1#/$defs/sha256" }, "format": { "const": "glb" }, "units": { "const": "m" }, "up": { "const": "+Y" }, "note": { "const": "Render derivative of the assembled geometry. Not a CAD source." } } }
    }
  },
  "allOf": [
    { "if": { "properties": { "content": { "const": "anatomy" } } }, "then": { "properties": { "status_text": { "const": "Typical anatomy · a representative reconstruction from public sources. Not any manufacturer's CAD. Not silicon-validated. Arrangement schematic; unknown values are marked." } } } },
    { "if": { "properties": { "content": { "const": "model" } } }, "then": { "properties": { "status_text": { "const": "Our model · the layers and blocks our thermal solver actually simulates, with its simplifications. Not the real package." } } } },
    { "if": { "properties": { "content": { "const": "result" } } }, "then": { "properties": { "status_text": { "const": "Results · from signed, verified evidence only. Each value names its run, geometry, evaluator and label. Simulated, not silicon." } } } }
  ]
}
```

`data` holds, by content: the assembly and the subset of the anatomy it uses (anatomy); the model stack, one fixture
and its layouts (model); a `sentilab-result/1` (result). The markdown twin is generated from the same JSON by
`twinMarkdown()` and repeats the banner, every qualifier and every label text. Both are byte-reproducible (canonical
key order, LF). A GLB derivative carries one node per drawn instance, `extras.instance_id`, metres, +Y up, no
textures, no compression (L3:PSEUDOCODE §10), and its sha256 is listed in `derivatives`.

### 5.9 What changes from lane 1's `parts.json` (and from lane 3's assumed schema)

| `parts.json` (L1) | Served form | Why |
|---|---|---|
| `schema: sentilab.cad3d.lane1.parts/v1`, `repo_snapshot` 46791be | `sentilab-anatomy/1` with `built_from` pinned files | versioned served format; the research file stays frozen |
| `parts[].id`, `parent`, `stack_order` | `part_types` keys, `parent_type`, `level` | kept (sound) |
| `count` (number or null) | `count` quantity with basis | "30" phases is "thirty or more" (min 30); unknown counts become `unknown` |
| `material` (free text) | `material_text` (generic) plus `material` id into a new `materials` table | one record per physical material, k with basis |
| `thickness_um {min, typical, max, notes, render_hint, render_hint_basis}` or `null` | `thickness` quantity | one shape; `typical` becomes `value`; render hints keep their basis; null becomes `unknown` |
| `lateral_mm {w, h, pattern, examples …}` | `footprint {w, h, area, pattern}` quantities | product-specific sizes (TAP Table II for one product) move to a later product assembly (D1); examples become facts in the text |
| `k_W_per_mK` (array, number, object or null) | `material.k` quantity, near room temperature | temperature-conditioned entries (the keys `silicon_85C`, `silicon_100C`, `silicon_at_100C`, and the interposer note that states a conductivity at a temperature) are omitted (PL-4); `our_model*` values move to the model manifest (X5) |
| `connects_to [{id, type[]}]` | `type_edges` (`basis: lane1_typical`) and per-assembly instance edges | edges get a `via` and become instance-to-instance in assemblies |
| `sources [{fact, source}]` | `facts` ids; `facts` and `sources` tables | the claim is served, the quote stays in the repo (FACTS.jsonl) |
| `variant` (one string; `cowos_r`, `cowos_l_or_emib`, `ascend910`) | `variants` array (`rdl_interposer`, `bridge_interposer`, `product_reference`) | several variants per part; generic names |
| `in_our_model` | removed; the model manifest's `stands_for` | X2, X5 |
| `notes` | `note` or folded into `explanation` (generic, temperature-free) | |
| `interconnects` (class records, mixed fields, "10K-30K" text) | `interconnect_classes` with quantities; counts written in full ("10,000-30,000") | thousands written as "10K" or "10k" read like kelvin to the PL-4 scanner (case-insensitive), so they are written in full |
| `flows` (lists, a list of lists, a pipe-joined alternative, a note string) | `flows` with `steps` (`part` or `any_of`), `share`, `contested`, `qualifier` | one shape; lateral coupling split into three flows |
| `reference_layouts.ascend910_reference` | not served in phase 1 (no positions; a product: D1) | arrangement would be invented |
| `reference_layouts.generic_hbm3e_two_die` | a later generic assembly (D11) | phase 1 ships one assembly |
| `source_index.tap25d_date2021` (no URL, no hash) | completed: URL and PDF sha256 `b209f51a…` from main:docs/sentilab/references/README.md:79-80, which equals the lane-1 sealed manifest's entry for `thermal/tap25d_date2021.pdf` | provenance gap (L1:SOURCES.md row 58) |
| `heat_sink.thickness_um.typical 6900`, `lateral_mm 180` (model values in a typical field) | model manifest only; the anatomy heat sink's thickness is `unknown` with a render hint | X5 |
| `coolant.in_our_model.detail` (contains an ambient temperature) | removed | PL-4 |
| `source_index.vertiv_coolant_temp_roadmap.title` (a temperature in the title) | title shown only under D1 "named", and then only after D2 | PL-4 |

Against lane 3's assumed `sentilab-parts/0.1` (L3:PSEUDOCODE §1): `solver_layer` becomes the model manifest's
`stands_for` (inverse map); `kind` keeps its role; `lateral.from: "evidence"` becomes the Results rule "chiplet
footprints only from signed geometry"; scalar `thickness` becomes a quantity; the twin moves from
`sentilab-twin/0.1` to `sentilab-twin/1` (three content kinds, markdown, `omitted`).

## 6. Rendering architecture

Lane 3's architecture (L3:ARCHITECTURE §0-§10) is adopted, with the deltas in 6.8.

### 6.1 Stack and what the CSP allows

- **Renderer: our own WebGL2 renderer** (default; D5), the 3D sibling of the hand-written Canvas 2D renderer
  (render.mjs:1-9): three GLSL programs (instanced lit boxes and cylinders, unlit field sheets, lines), our own orbit
  and touch camera, our own DOM labels; estimated 900 to 1,300 lines (an estimate, not measured). No third-party
  runtime code, no build step, no CSP change. three.js r187 stays the documented alternative behind the same
  `render3d.mjs` interface (L3:PSEUDOCODE Appendix A).
- **CSP consequences** (main:web/src/csp.js:7; L3:ARCHITECTURE §2.1): same-origin module files only; no `eval` or
  `Function`; no WebAssembly (so no Draco, meshopt, KTX2, WASM CAD); no inline script, so no import map; module
  Workers only from our own files; images only from our origin or `data:`; no `<style>` or `style=""`; styles set per
  CSSOM property (`el.style.transform = …`). Whether per-property writes are outside CSP3's `cssText` gating is a
  reading of the specs, marked unverified by lane 3 (L3:evidence/web-06 (d)); AC-27 checks it in a real browser. The
  existing pages' `h()` helper writes `style.cssText` (main:web/public/sentilab/package/package.js:29); the new page's
  helper does not.
- **WebGL2 required for 3D; WebGPU unused**; without WebGL2 the 2D cross-section (L3:ARCHITECTURE §2.4).

### 6.2 One model per mode, three outputs

```
 anatomy.json + assembly-*.json      model-stack.json + layouts.json      source.mjs (verified prefix)
          |                                    |                          + scene.mjs + results.mjs
          v                                    v                                    |
   readAnatomy / readAssembly          readModelStack / readLayouts          resultView()  (+ field.mjs later)
          \__________________________________  |  _________________________________/
                                             v  v  v
                       model.mjs buildRenderModel({ kind, ... })  ->  RenderModel (deep-frozen, one kind)
                                             |
            view.mjs displayBoxes(model, viewState)  ->  Map(id -> display box)   (view transform only)
                 |                         |                          |
       render3d.mjs (WebGL2)      fallback2d.mjs (SVG, sectionAt)     twin.mjs / twinMarkdown (JSON, MD; CLI)
                 |
  temps.mjs (labels) -> DOM only: legend, readout, detail panel, chips, notice
```

- **The renderer decides nothing.** Every meaning (which state, number, label, field, basis) is decided by pure
  modules; the renderer draws boxes, instances and sheets with colours already chosen (L3:ARCHITECTURE §3).
- **No text in the canvas.** All words and numbers are DOM, set through `textContent`.
- **Same data adapter** for results: `../package/source.mjs` and `reconcile()` (main:web/public/sentilab/package/source.mjs:1-12;
  playhead.mjs:1-13), so replay, live, K drops and paging behave exactly as in the reviewed Package view.

### 6.3 Frames: assembled, display, exploded

- **Assembled** (in the RenderModel): true or hinted geometry in mm, frozen. Every length shown, every pick result
  and every field lookup is in assembled coordinates.
- **Display** (in `view.mjs`, recomputed per view change): readable thickening (layers under 0.25 mm drawn at
  0.25 mm and levels restacked), explode offsets (level k rises by `t · gap · k`, gap = 0.18 x the lateral span; inner
  HBM gap 0.04 x; L3:PSEUDOCODE §1-§2 `DRAW`), and the section plane. It returns a new map and never writes to the
  model.
- **Picking** is analytic (ray against boxes, slab test) on display boxes of drawn instances only (an undrawn
  instance has no box, so it is never picked, never bounds the view and never maps to a field cell) and returns
  instance ids; a field lookup
  maps the picked sheet back to its grid layer and the hit's x and y (unchanged by explode and readable, which move
  only z) to a grid cell.

### 6.4 Fields on 3D (after P1-P4)

Per solver layer, not per anatomy part: one RGBA8 texture per grid layer, NEAREST filtering, texels from a 1,024-entry
lookup table built from scene.mjs `heatColor()` (main:web/public/sentilab/package/scene.mjs:269-275), so the 3D, the
2D views and the legend share one colour function; unlit sheets; withdrawn sheets hatched and unvalidated sheets
stippled in screen space; one fixed scale per run over every accepted field value, rounded out to 5 and at least 10
wide, widening only while live (scene.mjs:230-233; playhead.mjs:28-38); grid size and layer name in the legend; no
interpolation and no field built from centre temperatures (L3:ARCHITECTURE §5.3-§5.5; REQUIREMENTS V13 and F24,
main:docs/sentilab/draft-0.5/REQUIREMENTS.md:179, :264). Grid layers 6 and 7 cover the interposer area only (5.4).

### 6.5 Labels and DOM

Our own label layer (about 60 lines): one element per label, positioned by a per-property transform, text by
`textContent`, culled by priority without overlap (at most 6 on phones, 24 on desktop), leader lines by the line
program (L3:ARCHITECTURE §4.4). The part tree is the keyboard and screen-reader route to every part; the canvas has
`role="img"` and a summary `aria-label` (as main:web/public/sentilab/package/package.js:428-430); a polite live region
announces mode changes and new verified results.

### 6.6 Live transport

Cursor paging through `source.mjs` `createLiveFeed()` is the only data path (source.mjs:205-258). Field artifacts are
fetched only for hashes the verified prefix names, at most two in flight, aborted when they leave the prefix, cached
by content (L3:PSEUDOCODE §7). An optional SSE doorbell (needs P10) only calls `feed.poke()` (source.mjs:256). No
WebSocket: the Worker strips `upgrade` (main:web/src/worker.js:7, :26).

### 6.7 Lifecycle, disposal, budgets

- Render on demand: zero frames while idle. On mode switch, page hide and `webglcontextlost`, every GL object is
  deleted and counted (A#57059: "explicitly dispose resources"); the test hook reports live GL object counts.
- Stale fetches are aborted on mode switch and K drop (AbortController), and a late response is discarded by hash.
- Budgets: ACCEPTANCE AC-34 (both sources' numbers; D4). Interconnect instances are sampled on a regular lattice
  within a budget derived from the triangle budget, and the view says `1 of k² sites drawn · N total`
  (L3:ARCHITECTURE §4.5).

### 6.8 Deltas from lane 3

| Lane 3 | This spec | Why |
|---|---|---|
| One RenderModel from parts.json plus verified scene plus solver stack | One RenderModel per content kind; mixed input refused | rule 2, A#57053 (X1) |
| Modelled-part thickness falls back to parts.json nominal without a field (PSEUDOCODE §1 step 3) | Falls back to the model manifest, else "schematic", never anatomy | X4, D6 |
| RenderModel carries display thickness next to true (`z0`, `z0_true`, `thickened`) | RenderModel is assembled only; display boxes come from `view.mjs` | rule 3, A#57059 (immutable assembled geometry) |
| `checkFieldArtifact` binds run, measurement, evaluator | also checks input-source hashes against the signed `artifact_hashes`, and lists layer-table differences | L3:ARCHITECTURE §5.2 item 1 says those hashes are signed; this makes the check explicit |
| Twin JSON (+ GLB) at `/agents/package3d/<id>.json`, catalogue at `/agents/index.json` | JSON plus markdown per content kind under `/agents/package3d/`; catalogue `/agents/package3d/index.json` | rule 9; PR #66 owns `/agents/index.json` (D9) |
| Budgets: phone 300,000 triangles, 60 draw calls | the stricter of lane 3 and astra per row, pending D4 | inputs differ |
| `explodedZ` added to section rectangles | the same, through `view.mjs` | |
| Glides and pulses as in the Package view | glides for chiplet moves only; field changes are hard cuts | PL-20, D17 |

### 6.9 `/agents/` with or without PR #66

The twins are static files under `web/public/agents/package3d/` and are linked from the page. If PR #66 merges, the
room may also be added to its Accept negotiation (`AGENT_PATHS`, pr66:web/src/agent-paths.js:4-8) as a separate,
small change (D9). Nothing in phases 1-5 needs that.

## 7. Provenance and labelling rules

| Id | Rule | Source |
|---|---|---|
| PL-1 | Every displayed number shows its basis tag beside it (section 5.0). | L3:ACCEPTANCE A-13; A#57059 |
| PL-2 | A temperature becomes text only through `temps.mjs` `formatTemp(valueC, label)`, which refuses any label that is not one of the frozen `LABELS` objects (identity, not shape) and any non-finite value; the value and its qualifier sit in one DOM element. Labels that travel as data (result values, twins, the Twin JSON dialog, CLI output) are serialized records `{ state, text, short, title }` (the rule's `notice` flag is not serialized; it follows from the state), because a JSON round trip cannot keep object identity. A record reaches `formatTemp` only through `resolveLabel(record, identity)`, which recomputes `labelFor(identity)` from the value's verified evaluator identity, requires exactly those four keys with strings equal to the recomputed label's, and returns the canonical in-process `LABELS` object; any difference is `label_mismatch` and the value is refused (PSEUDOCODE §8). This holds for DOM text, `title`, `aria-label`, the twin JSON and markdown, and the Twin JSON dialog. No canvas text exists. | task rule 1; main:web/public/temperature-label.mjs:38-85; L3:PSEUDOCODE §5; A#57218 item 2 |
| PL-3 | Labels are per value. A global badge or the page notice never replaces a value's own label. J and centre temperatures from different measurements keep separate labels. | A#57059; main:web/public/temperature-label.mjs:137-144; main:web/test/per-value-provenance.test.mjs |
| PL-4 | Static content (anatomy, assembly, model stack, layouts, static twins) contains no temperature number in any string, key or unit (absolute or difference), until D2 is decided. Literature limits, model boundary temperatures and temperature-conditioned material values are listed in `omitted` with the reason. | task rule 1; D2 |
| PL-5 | Withdrawn and unvalidated field sheets carry pixel patterns (hatch, stipple); the state chip sits inside the canvas wrapper, so a canvas-only crop still shows the state. | L3:ARCHITECTURE §5.5 |
| PL-6 | A field's label is `labelFor()` of the verified envelope's evaluator identity, never the artifact's claim; a mismatch refuses the artifact. | L3:ARCHITECTURE §5.5; main:web/public/temperature-label.mjs:156-161 |
| PL-7 | A legend is a derived value: `labelForAll()` over the identities behind its scale. | main:web/public/temperature-label.mjs:17-19, :145-153 |
| PL-8 | The page notice follows `needsNotice()` over the verified prefix, as the Package view does, and must also fire for field-only measurements once P4 lands. The notice slot markup is the existing one. | main:web/public/sentilab/package/package.js:297-300; temperature-label.mjs:163-170; temperature-label.test.mjs:331-333 |
| PL-9 | Statistics are named and never mixed (section 5.6 table). | A#57059; main:docs/sentilab/references/README.md:105-119 |
| PL-10 | Unknown stays unknown: `unknown` or `not sourced · drawn at X (display only: reason)` in the panel; null plus basis in the twin; never filled silently; sourced children that do not add up to a sourced parent leave a labelled gap. A part whose size is unknown and has no hint is undrawn: it keeps its id, parent and connections, has no box, and is left out of bounds, picking and field association (section 5.3). | task rule 3; L1:parts.json `conventions.thickness_um`; A#57218 item 1 |
| PL-11 | Instance ids are stable, unique, authored, never reused; removed ids are listed in `retired_ids`. | task rule 3; A#57053 |
| PL-12 | Assembled geometry is immutable; explode, readable and section are view transforms; lengths, picks and field lookups use assembled coordinates. No view state enters the geometry preimage (section 5.0). | task rule 3; A#57053; A#57059; A#57218 item 3 |
| PL-13 | Units convert once: µm to mm in `quantity.mjs`, mm to m (and z-up to +Y-up) in the GLB writer. | A#57059 |
| PL-14 | Overlays draw typical or model paths with their qualifier always visible; no watts or temperatures on arrows; Results draws no flow arrows. | A#57059 |
| PL-15 | A drawn link is not a routed wire and not a bandwidth; the model's netlist weights and W say so (`wire proxy`). | A#57059; main:sentilab_core/conductor.py:345; README.md:105-108 |
| PL-16 | The HBM illustration is not a recovered internal stack (anatomy), and the model's HBM is a 150 µm block (model); the panel says which. | A#57059; L1:our_model_mapping.md §2 (L4 row) |
| PL-17 | Names: `generic` until D1 is decided; no infrastructure vendor or mechanism names in any served room file (scan, AC-29). | task rule 8 |
| PL-18 | No MicroDuck or Pollen material of any kind. | task rule 7 |
| PL-19 | Live honesty: the mode chip comes only from `source.mjs`; every result says `as of seq S`; `solving` only from a verified `simulation_pending` while LIVE; fields only from completed signed solves; simulated time stated separately; the doorbell never sets LIVE. | task rule 4; L3:ARCHITECTURE §6.4; VIEW-ENVELOPE v0.6.2 rule 5 |
| PL-20 | Motion is one of three kinds and says which: replay playback (REPLAY), a new live receipt (announced once), view-only motion (explode, orbit, chiplet glides). No idle effects. Field changes are hard cuts. | A#57053; L3:RISKS R-08 |
| PL-21 | Stale, refused, withdrawn and mismatched values are shown as such; never a success fallback or a fabricated heatmap; refused values are listed with their reason and never drawn or exported as numbers. | A#57059; main:scripts/sentilab-scene.mjs:17 |
| PL-22 | The twin is produced by the same pure functions from the same inputs as the page, carries the same texts, and is byte-reproducible. | task rule 9; L3:ACCEPTANCE A-15 |
| PL-23 | Wording: "simulated", never "measured", for simulated values; "not silicon" wherever a result appears. | L3:RISKS R-02; temperature-label.mjs:52 |
| PL-24 | Every sourced number resolves to a lane-1 fact with a verbatim, machine-checked quote; served claims are generic rewrites that keep every number of the original. | L1:SOURCES.md "How the facts were checked" |

## 8. Prerequisites owned elsewhere (not done)

| Id | Change | Owner | Blocks | Today |
|---|---|---|---|---|
| P1 | **Producer:** publish `sentilab-field/0.1` (section 5.7) from `sample.grid.steady`, all 8 layers, with the layer table, grid extent, row order, named input sources and argv. | TBD (core producer owner) | any field (W14) | the worker parses all 8 layers but keeps layer 4 only (main:sundai_hotspot/tap_oracle_worker.py:91-100, :417-431) |
| P2 | **Measurement pointer:** `values.field = { sha256, format, rows, cols, layers, unit }` in the measurement envelope, and documented in the VIEW-ENVELOPE contract. | TBD (producer and contract owners) | W14 | values are J, W, scenario_id, artifact_hashes (main:sentilab_core/conductor.py:344-346; VIEW-ENVELOPE v0.5:23-25) |
| P3 | **API route:** `GET /api/view/artifacts/<sha256>`: read-only, immutable, capped at 4 MiB, serving only hashes a run's log names. The Worker passes upstream `cache-control` through, so no Worker change. | TBD (API owner) | W14 | no such route (main:app/view.py:90, :97, :186) |
| P4 | **Label rule:** `hasTemperature()` counts `values.field`, with a test, so a field-only measurement raises the notice. | TBD (label-rule owner) | W14 | J and centre temperatures only (main:web/public/temperature-label.mjs:163) |
| P5 | **Receipt completeness:** named input hashes and the solver argv in the measurement (and the field artifact). | TBD (producer owner) | the `receipt_completeness` chip turning green (never blocks display) | unnamed list (conductor.py:346); names and argv exist in the worker (tap_oracle_worker.py:346-348, :356-369) |
| P6 | **Replay artifacts:** serve fields next to replay bundles (`/api/replay/<bundle>/artifacts/<sha256>` or static files). | TBD (API owner) | fields in replays | the page builds `/api/replay/…` (package.js:652-654); not served |
| P7 | **Grid layer order and extent** for layers 6 and 7 confirmed by the producer (section 5.4). | TBD (producer owner) | drawing fields on spreader and sink | code reading only |
| P8 | **Evaluator acceptance:** an ACCEPTED entry for an exact identity. | label-rule owner with the SLAB-049 review | any "accepted" label (never blocks the build) | ACCEPTED is empty (temperature-label.mjs:28) |
| P9 | **A label state for non-result temperatures** (D2). | TBD (label-rule owner) and the founder | showing literature or input temperatures as numbers | none |
| P10 | **Doorbell route** (optional): `GET /api/view/doorbell?run_id=` (SSE); measure edge and container idle timeouts first. | TBD (API owner) | W15 | none |
| P11 | **PR #66 merged** (optional) for Accept negotiation of the room. | forge | D9 only | PR #66 open |

## 9. Phased plan for one build agent

Sizes are rough guides for code plus tests (S under 300 lines, M 300 to 900, L over 900); they are estimates, not
measurements. Each work item lands as its own PR with its acceptance checks green; UI PRs attach 320, 390 and 1280 px
screenshots. No item deploys, runs a solver, or touches the producer, the API, the label rule or the contracts.

### Phase 0: freeze (reviewers; no code)

| Item | Scope | Exit check |
|---|---|---|
| W0.1 | forge, warden and astra sign this exact document (section 5 schemas at version 1, the operation names in PSEUDOCODE §0, the no-result behaviour in sections 4.5 and 7, the AC list). | three sign-offs naming the commit |
| W0.2 | astra maps her 41 source cases (30 web, 11 anatomy; A#57059) to AC ids, or lists the gaps; gaps become ACs before W1. | mapping committed next to ACCEPTANCE.md |
| W0.3 | The founder answers D1 (names) and D2 (non-result temperatures), or accepts the defaults. | decision recorded |
| W0.4 | warden provisions the box: a branch with push rights only (no deploy credentials, no secrets, no solver or GB10 access); Node 22; Python with the repo's requirements for the W4 check (TAP's floorplan writer only); Playwright with Chromium via `PLAYWRIGHT_DIR` (the pattern of main:scripts/export-deck-pdf.mjs:4); the pinned wrangler for a local Worker (main:web/test/worker-boot.mjs:5-11, :22); gitleaks; access to the reference phone named under D4. | warden's admission record |

### Phase 1: data and validators (no page)

| Item | Size | Scope | Acceptance |
|---|---|---|---|
| W1 | M | `quantity.mjs`, `ids.mjs`, the common schema checks, refusal codes (section 5.1). | AC-10, AC-14 (grammar) |
| W2 | L | Anatomy content: the reviewed overlay (generic names, rewritten claims, explanations for all 44 part types, content fixes listed in 5.9) in `docs/sentilab/package3d/`; `scripts/package3d.mjs data` writes `web/public/sentilab/package3d/data/anatomy.json` from L1 `parts.json` pinned by sha256; `--check` mode for CI. forge reviews content, astra reviews evidence. | AC-03, AC-08, AC-10, AC-29, AC-30, AC-40 |
| W3 | M | Assembly `typ-1c4m` (lidded and lidless) as a reviewed source; `geometry_sha256`; id stability across builds. | AC-11, AC-12 (hash), AC-14 |
| W4 | M | Model stack manifest (section 5.4) and `layouts.json` (5.5); `sundai_hotspot/test_package3d_model_stack.py` regenerates each fixture's LCF, floorplans and config with TAP's writer (never HotSpot) and compares; layout identities recomputed Python-canonically. | AC-16, AC-17 |
| W5 | S | Static scanners: bare temperatures (strings, keys, units), infrastructure names, generic-names policy, over `web/public/sentilab/package3d/**` and `web/public/agents/package3d/**`. | AC-02, AC-03, AC-29 |

### Phase 2: pure view modules

| Item | Size | Scope | Acceptance |
|---|---|---|---|
| W6 | L | `model.mjs` (one kind per model, deep-frozen), `view.mjs`, `explode.mjs`, `section.mjs`, `interconnect.mjs` (triangle-derived budgets), `pick.mjs`, `flows.mjs` (overlays and qualifiers per mode). | AC-08, AC-12, AC-13, AC-15 |
| W7 | M | `temps.mjs`, `results.mjs` (result view, statistics, per-value labels, receipt completeness, numeric reference match). | AC-01, AC-06, AC-07, AC-18, AC-19 |
| W8 | M | `twin.mjs`, `twinMarkdown`, `scripts/package3d.mjs twin` and `export3d`, `scripts/lib/glb.mjs`; the static `/agents/package3d/` files; twins for the bundled replays. | AC-06, AC-13, AC-36, AC-37 |

### Phase 3: the page without WebGL (accessible first)

| Item | Size | Scope | Acceptance |
|---|---|---|---|
| W9 | L | `index.html`, `package3d.js`, `package3d.css`: header, mode switch, banners, notice slot, part tree, detail panel, thermal-path tab, legend, SVG cross-section (`fallback2d.mjs`), Twin JSON dialog; links from the Package and Lab views; the page added to `worker-csp.test.mjs`, `worker-boot.mjs`, the notice test, public-names and control-bytes; `scripts/package3d-browser-check.mjs` (Playwright against the local Worker). | AC-04, AC-09, AC-11, AC-27, AC-28, AC-31, AC-32, AC-33, AC-35 |

### Phase 4: the WebGL2 renderer

| Item | Size | Scope | Acceptance |
|---|---|---|---|
| W10 | L | `mat4.mjs`, `camera.mjs`, `gl.mjs`, `shaders.mjs`, `render3d.mjs`, `labels.mjs`; picking, explode tween, section caps, overlays, lid and spreader outlines; context loss and restore; disposal; the `window.__package3d.facts()` test hook. | AC-12 (browser), AC-15, AC-27, AC-33, AC-35 |
| W11 | S | Performance and device run on the reference phone and a desktop; traces attached. | AC-34 |

### Phase 5: results (view envelopes; no fields in production)

| Item | Size | Scope | Acceptance |
|---|---|---|---|
| W12 | M | Results mode on replay and live through `source.mjs`: J, W and centre temperatures with per-value labels and statistics, as-of stamps, solve status, simulated-time line, STALE and ENDED, K drops; the demo replay as the default, as in the Package view. | AC-04, AC-18, AC-19, AC-23, AC-24, AC-26 |
| W13 | M | `field.mjs` and `stream.mjs`, tested only on fixtures signed with the TEST key; in production the field path reports "no field in this run's receipts" until P1-P4 land. | AC-05, AC-20, AC-21, AC-22, AC-25 |

### Phase 6: gated items

| Item | Gate | Scope | Acceptance |
|---|---|---|---|
| W14 | P1-P4 merged (and P7 for layers 6-7) | Enable fields in production; rerun device budgets. | AC-05, AC-20 to AC-22, AC-25, AC-34 |
| W15 | P10 | Optional doorbell. | AC-24 (doorbell clause) |
| W16 | a trial approved by the reviewers (section 10) | Optional scriptable CAD for authored geometry. | AC-38 |
| W17 | D7 | Optional SKETCH mode. | AC-39 |
| W18 | D1 = named | Named content variant and a product assembly. | AC-29 (named mode), AC-40 |

## 10. CAD

**Recommendation (astra's, A#57059; consistent with lane 3, L3:ARCHITECTURE §7):** build the room from original
primitives (boxes, short cylinders, sheets), reviewed physical-layout manifests and sourced part explanations, with a
synchronized DOM, 2D and 3D view. Scriptable CAD is optional and later, only when richer authored geometry warrants it,
and gated on a trial (W16): build123d or CadQuery with agentcad as a possible CLI/MCP artifact wrapper.

**Tool identities, copied from astra's claims matrix (captured sources, not independently executed by her or by this
spec).** Similarly named projects are separate identities and are never merged.

| Tool (exact identity) | License (as captured) | Documented capability | Caveats | Pinned source |
|---|---|---|---|---|
| CADCraft, `storytold/cadcraft` | MIT OR Apache-2.0 (both license files captured) | pure-Rust desktop/WASM; CLI/MCP/JSON control documented | early development; unmodeled imported entities can be lost on save; ARM64 release artifacts do not prove GB10 compatibility | github.com/storytold/cadcraft at `b6331c8603f9cc51b8044237f4517f79da1932b6` (README.md, docs/file-format-parity.md) |
| CadCraft, `getcadcraft/cadcraft` (a different project) | Apache-2.0 | browser drafting | do not transfer the first project's Rust, MCP or format claims to this identity | github.com/getcadcraft/cadcraft at `80b7225198e97fea75519dda16f5587b6fdfd803` (README.md) |
| SolidCraft, `tangency-labs/solidcraft` | README offers MIT OR Apache-2.0; the actual Apache license was inspected | Rust parametric CAD; headless CLI/MCP; assemblies and several exchange formats "where supported" | "early but usable for simple parts"; the same-head README says 75/76 reference matches, the oracle says 90/90 and warns that a corrected centre-of-mass reference needs replay: no clean accuracy headline | github.com/tangency-labs/solidcraft at `76e009ab100ca8def6525fcbbfd2c36e282975ef` (README.md, docs/oracle.md) |
| SolveCraft | unresolved | unresolved | the exact described CAD/MCP identity is unresolved; this is not a finding that it does not exist, and not permission to rename it SolidCraft | none |
| agentcad, `jdilla1277/agentcad` | Apache-2.0 | build123d by default, CadQuery optional; structured CLI and optional MCP; STEP, PNG, STL, GLB, OBJ; validation and diffs; localhost preview | dependency profiles and Python compatibility must be pinned and tested; a source license does not establish zero compute cost or license every dependency | github.com/jdilla1277/agentcad at `f68d00feae9193f38a45add577dc019721129b56` (README.md); agentcad.dev/incorporating-agentcad |
| CadQuery, `CadQuery/cadquery` | Apache-2.0 | headless use, assemblies, exchange | the library identity alone does not prove the proposed MCP workflow | github.com/CadQuery/cadquery at `8178185a24a035c9af7f4679033be14267f6a6ef` |
| build123d, `gumyr/build123d` | Apache-2.0 | OpenCascade-based | as above; CadQuery and build123d share a kernel, so they are not fully independent geometry witnesses; their resolved combination needs a trial | github.com/gumyr/build123d at `7d23c772a3c61a6d0546e723aac9b44dcd65ffd9` |
| FreeCAD, `FreeCAD/FreeCAD` | LGPL-2.1 source | candidate geometry reference | latest stable release, a complete unattended/export matrix and an official built-in MCP were not established in her review; community adapters need their own identity, version and license review (lane 3 recorded release 1.1.4 from the releases API: D15) | github.com/FreeCAD/FreeCAD at `24ea8589aa8676049f7fe53ca9d1d1c398c38d26` |
| Autodesk official MCP offerings | vendor terms | Product Help reads documentation, not geometry (announcement: 110+ products); Fusion's landing page claims feature/geometry editing; Revit's 17 June launch was a Revit 2027 Tech Preview with stdio and seven read-only tools and an add-on entitlement | Fusion's exact current tools, unattended behaviour and entitlements not established; Fusion Automation marked "Coming Soon" in the October capture, no callable cloud service proved; the Revit tool count is dated, not an October inventory; Fusion personal use excludes company environments and must not be assumed to cover SentiLab; product entitlement, adapter license and dependency rights are separate things | https://aps.autodesk.com/blog/now-available-chatgpt-autodesk-product-help-plugin; https://www.autodesk.com/solutions/autodesk-ai/autodesk-mcp-servers; https://www.autodesk.com/blogs/aec/2026/06/17/revit-public-mcp-server/; https://www.autodesk.com/products/fusion-360/personal |

Lane 3's offline-tool facts, kept beside the matrix (L3:ARCHITECTURE §7.2, L3:evidence/cad-01 to cad-05-12, web-10,
extra-04): build123d 0.13.0 and CadQuery 2.8.0 (Apache-2.0), OCP 8.0.1.1 (Apache-2.0, binds OCCT 8.0.1), OCCT V8_0_1
(LGPL-2.1 with the Open CASCADE exception 1.0; no determinism statement found, parallel meshing on), Khronos
glTF-Validator npm `gltf-validator` 2.0.0-dev.3.10 (Apache-2.0, a pre-release tag), `@gltf-transform/core` 4.5.1 (MIT),
occt-import-js 0.0.23 (LGPL-2.1, WebAssembly, blocked by the CSP), Blender excluded (GPL). The site's rule "No GPL code
enters this project" (main:web/public/licenses.html:31) holds; nothing from OCCT ships to the site.

**Benchmark claims.** The pasted "98% autonomous structural-sheet reconstruction" figure is unattributed and
unverified. agentcad's Candidate L reports 80/81 VALID outputs and a 0.245 CAD Score in a single run; 98.8% validity is
not complete task success, and its relation to the pasted figure is unknown. CADWorld v1's abstract reports 17.5% on
200 tasks and its introduction 25% on a 60-task subset; the populations are unreconciled (arxiv.org/html/2609.16251v1).
Any trial judges persistent geometry, dimensions, constraints and task completion separately and keeps failures and
interventions in the denominator (A#57059).

**Contract if CAD is used later (W16 gate).** The authored script (or native file) is the source and STEP its export;
GLB is a separately hashed render derivative. Bind stable instance ids, the physical frame and units, source rights,
material records, export settings and exact node/primitive mappings; glTF names are not unique; a visual PBR material is
not a physical material model; 45 mm becomes 0.045 m exactly once; exploded transforms derive from immutable assembled
transforms (A#57059). Parity with the primitive model: per-instance bounding boxes within 1 µm, names equal instance
ids, glTF-Validator 0 errors (L3:ARCHITECTURE §7.2), every resolved dependency's license reviewed, versions and Python
pinned, no CAD in the display path.

## 11. Open decisions for the founder and the reviewers

| Id | Decision | Options and inputs | Default until decided | Who |
|---|---|---|---|---|
| D1 | Naming the chip products studied (for example "Ascend 910", "H100") and their makers and technologies in the room's educational content and citations. | Rule 8 makes it open. The site already names "Ascend910-class 2.5D (TAP, HotSpot)" in the run view's benchmark list (main:web/public/index.html:28) and serves the fixture id `ascend910` in data (main:web/public/replay/ascend910-seed11-32x32.json `benchmark`); PR #66 names "Ascend 910" and "CPU-DRAM" as problems (pr66:web/public/agents/index.json:19). | `generic`: no product or company names in new copy or twins; sources shown as type, kind and year; fixture ids kept only as identifiers. | founder |
| D2 | Temperatures that are not results (literature limits such as HBM refresh trip points, model inputs such as the ambient, the condition of a material value). | **Contradiction.** Rule 1 requires one of four label states, and none is truthful for them: withdrawn and unvalidated say "simulated", illustrative means the bundled fixture, accepted says "simulated" (main:web/public/temperature-label.mjs:38-53). Lane 1 content contains such values (L1:thermal_path.md §3; parts.json `silicon_85C` and others). PR #66 shows policy temperatures with "provisional" and "invented" qualifiers that are not label states (pr66:web/public/agents/math.md:168, :221-225). Options: keep them unrendered; or the label-rule owner adds a state (for example "sourced · not a result") with tests, outside the four states rule 1 names. | unrendered, listed in `omitted` (PL-4) | founder and label-rule owner |
| D3 | Signed chip-layer grids that already exist. | **Contradiction.** The task's rule 5 says no signed record carries a temperature field today. Lane 3's finding is narrower: no verified view envelope carries a field (L3:ARCHITECTURE §0 and §5.1). On origin/main, the served run-view replay holds signed flight records with a 32 x 32 chip-layer `heatmap_c` from the withdrawn HotSpot-7 build, drawn by the run view (main:web/public/app.js:52, :63, :139). Use them in the room (through the flight-record verifier, main:web/public/verify-core.js), or not. | not used; the Results path is view envelopes only; P1-P4 stay required for any 3D field | founder and reviewers |
| D4 | Phone performance budgets and the reference phone. | **Inputs differ.** Lane 3: at most 300,000 triangles, 60 draw calls, 6,000 interconnect instances, p95 frame 33 ms, DPR 2 (L3:ACCEPTANCE A-10). astra: at most 50,000 triangles, 100 draw calls, a 2 MiB derivative, a 1-megapixel buffer, p95 interaction frame 33 ms on a named tested phone; proposed and unmeasured (A#57059). | the stricter value per row, plus both sources' extra rows (ACCEPTANCE AC-34) | reviewers; warden names the phone |
| D5 | Renderer. | Own WebGL2 (lane 3's recommendation) or vendored three.js r187 (lane 3's alternative: 2,133,699 B raw, 419,212 B gzip, a public-names exception needed; L3:ARCHITECTURE §2.2-§2.3). | own WebGL2 | reviewers |
| D6 | Thickness in results mode without a field artifact. | **Inputs differ.** Lane 3 falls back to the parts list's nominal thickness (L3:PSEUDOCODE §1 step 3); astra and rule 2 keep anatomy separate from the computational references (A#57053). | the model manifest, else "schematic"; never anatomy | reviewers |
| D7 | Build SKETCH mode at all, and a label state for its numbers. | L3:ARCHITECTURE §6.3; rule 4. | not built | founder and label-rule owner |
| D8 | Which model content is shown by default. | The 45 mm raw references are gate zero (README.md:24; A#57059: the retained references are on a 45 mm interposer); the live service's default fixture is the 50 mm `ascend910` (main:sentilab_core/conductor.py:55; tap_oracle.py:25). | Model mode opens on `ascend910-45mm` raw, with the 0.5 mm variant and the other fixtures selectable; Results always uses the run's own `run.family` | forge and astra |
| D9 | Agent catalogue location and negotiation. | Lane 3 put a catalogue at `/agents/index.json` (L3:ARCHITECTURE §8); PR #66 uses that path for its own index (`sentilab-agents-index/1`, pr66:web/public/agents/index.json:2). | `/agents/package3d/index.json` and `index.md`; linked from PR #66's index only if it merges; Accept negotiation for the room only after PR #66 | forge |
| D10 | Scope of the infrastructure-names scan (rule 8). | A room-scoped test now, or extend the global `NAMES` list (main:web/test/public-names.test.mjs:20-26). | room-scoped (AC-29) | site test owner |
| D11 | The first typical assembly. | One compute die and four HBM stacks on a silicon interposer (within lane 1's "one or two compute dies and four to eight HBM stacks", L1:REPORT §1), 12-high HBM (lane 1's FEM stack), lidded with a lidless variant; lane 1's `generic_hbm3e_two_die` (two dies, eight stacks, bridge-class interposer) as the second. | as stated | forge |
| D12 | Results whose receipts lack named inputs and argv (all of today's). | Show with the `receipt incomplete` chip, or hide until P5. | show, with the chip (section 5.6) | astra and founder |
| D13 | Die-internal anatomy ("every intricacy", F#57046). | No public power map or die floorplan was captured (L1:thermal_path.md §4). | out of scope; the compute die's function is described in words | founder |
| D14 | Static manifests when WebCrypto is unavailable. | Refuse to draw, or draw with a `file check unavailable` chip. | draw with the chip; Results draws nothing (package.js:644-648) | reviewers |
| D15 | FreeCAD's latest release. | Lane 3 recorded 1.1.4 from the GitHub releases API on 2026-10-31 (L3:evidence/cad-05-12 §cad-06); astra's review did not establish the latest stable release. FreeCAD is not used. | informational; no action | none needed |
| D16 | Test mapping to astra's 41 source cases. | Her full report (sha256 `cccbe9d165fc358a17108e23ab6cbf1d8bdc4739d049e5e2565a90d430614d97`) is retained by her and was not available here. | Phase 0 exit (W0.2) | astra |
| D17 | Transitions between verified fields. | astra calls a steady-map fade "presentation" (A#57059), which permits a labelled fade; this spec prefers a hard cut so no frame shows colours of no solve. | hard cut | reviewers |
| D18 | Page path and title. | Lane 3's `/sentilab/package3d/` and "Package 3D"; the founder calls it the simulation room. | `/sentilab/package3d/`, "Package 3D" | founder |

## 12. Limits of this spec

- **Not verified here:** third-party facts relayed from lane 3's evidence (library sizes, browser support, CSP3
  readings) were spot-checked (web-06, extra-05) but not re-fetched; astra's CAD claims were copied, not re-fetched;
  lane 1's quotes were not re-run against the sealed evidence (lane 1 reports 176 of 176 machine-checked); the sealed
  evidence outside git was not inspected.
- **Estimates, not measurements:** renderer size, frame times, latencies and the budgets are lane 3's estimates or
  astra's proposed targets; AC-34 measures them.
- **Code readings:** grid layers 6 and 7 being the spreader and sink, covering the interposer area, is a reading of
  `temperature_grid.c` and `.h` (P7). The halo widths and bump-mix conductivities will be read from the floorplan
  writer's output by W4, not from this document.
- **Lane 1 internal note:** L1:SOURCES.md line 15 says the readable report "could not be written here", yet
  `REPORT.md` exists in the lane. Where this spec uses a value, REPORT.md, parts.json and thermal_path.md agree on it;
  the lane files were not otherwise cross-checked line by line.
- **No temperature values** are quoted in this document, from the repo or from the literature; it states rules about
  temperatures only. The only temperature-bearing strings in it are lane 1's key names that the converter must drop
  (section 5.9).
