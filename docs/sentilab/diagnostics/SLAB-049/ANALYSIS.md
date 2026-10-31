# SLAB-049 CAL-COUPLING: source analysis and frozen equations

Ticket `d41fca43-2e6c-464e-8fbc-0c485e4828dd` (owner pocket-forge). Line numbers refer to `3e7c480`;
`sundai_hotspot/` and `sundai_tap/` are unchanged on `origin/main` through `1e6b97e`.

**Status.** Source analysis, code, an analytic check, and a frozen 12-call manifest for gate zero. **No
thermal solve was run for this ticket.** The pre-declared interpretation and the raw-primary manifest are in
[CALL-LIST-v4.md](CALL-LIST-v4.md), written before any run. The snapped-primary manifest reviewed at `6413a3c`
([CALL-LIST.md](CALL-LIST.md)) is kept byte-identical as a prior artifact; nothing executes it.

**Room decision (section 8).** The cause is settled from source and saved grids. HotSpot 7 is not patched as the
path forward. The material-only HotSpot 7 variant below (sections 3, 4 and 7) stays as labelled, bounded
diagnostic evidence only. The MATCH candidate is HotSpot 6.0, the version TAP-2.5D pinned, and it is behind gate
zero.

**The question.** Our oracle's rise above ambient is about 2.3 to 2.4 times TAP-2.5D's on both fixtures
(forge-research `repo-forensics.md` section 5 #6). The suspect: in the vendored HotSpot detailed-3D model,
the spreader-to-sink coupling goes through half the heatsink cell's `rz`, and that `rz` includes the
convection share.

Labels: **[READ]** read in source or committed evidence. **[COMPUTED]** arithmetic on committed data, no
solver. **[INFERRED]** my interpretation.

## 1. What actually executes

Our oracle runs the following chain. All line numbers are at `3e7c480`, which equals upstream HotSpot `f18831e`
for `temperature_grid.c`; the whole-file SHA-256 is `1d50f58d...82441df`.

| Step | Location | What it does |
|---|---|---|
| Worker command | `sundai_hotspot/tap_oracle_worker.py:241-255` | `-model_type grid -detailed_3D on -grid_layer_file ... -grid_map_mode max`. No `-o`, and no override of any package parameter. |
| J | `tap_oracle_worker.py:91` | J is the layer-4 (chip layer) grid maximum. |
| Steady state only | `sundai_hotspot/hotspot.c:405-406, 684` | Without `-o`, `do_transient` is false, so HotSpot calls `steady_state_temp` once. |
| SuperLU branch | `temperature_grid.c:2819-2823` | With `SUPERLU=1` (the Dockerfile build), `steady_state_temp_grid` calls `direct_SLU`. |
| Matrix | `temperature_grid.c:5154-5157` | `direct_SLU` assembles with **`build_transient_grid_matrix`** and `build_transient_power_vector`. `build_steady_grid_matrix` is commented out. |
| Vertical links | `temperature_grid.c:5287-5288` | `Ra = find_res(model, l-1,i,j, l,i,j)` and `Rb = find_res(model, l+1,i,j, l,i,j)`. |
| Iterative path | `temperature_grid.c:2397-2421, 2426-2608` | The non-SuperLU build (the 2026-10-18 probe) uses `find_res` through the `NC..AT` macros, so it applies the same rule. |

[READ] Both live solver paths go through `find_res`. `build_steady_grid_matrix` (`temperature_grid.c:3837+`) is
dead code in this build. It uses a different rule: the spreader row takes the sink's full `rz` and the sink row
takes the spreader's `rz` (3921-3928). That matrix is non-symmetric, so re-enabling it would not restore
HotSpot 6.0's behaviour (section 5).

## 2. Where the coupling comes from (file:line)

| Item | Location | Code fact [READ] |
|---|---|---|
| `find_res`, detailed-3D vertical pair | `temperature_grid.c:103-105` (line 104) | `res = rz(n1)/2 + rz(n2)/2` for any two vertically adjacent cells, neither in layer 0 |
| Layer-0 rule | `temperature_grid.c:98-102` | A pair that includes layer 0 uses `rz(0) + rz(other)/2` |
| Non-detailed rule, for contrast | `temperature_grid.c:117-122` | Upper layer's `rz` only |
| `find_res_3D` | `temperature_grid.c:144-173` (choice 3 at 165-170) | Per-cell `rz`, or the layer `rz` when `hasRes` is false |
| Spreader and sink cell maps | `temperature_grid.c:555-558`, `1000-1010` | With detailed-3D the sink shares the spreader's map, and every cell has `hasRes = FALSE`, so both use the layer `rz` |
| `rz_hs`, the sink layer `rz` | `temperature_grid.c:1052` and `1054-1058` | `rz = t_sink/(k_sink cw ch)`, **then `rz += r_convec * s_sink^2 / (cw ch)`** |
| Sink to ambient, matrix | e.g. `temperature_grid.c:5439-5441` (all nine cell-position cases: 5440, 5520, 5599, 5678, 5757, 5820, 5882, 5944, 5998) | Diagonal `+= 1/rz_hs` |
| Sink to ambient, right-hand side | `temperature_grid.c:6555` | `ambient/rz_hs + power` |
| Iterative sink to ambient | `temperature_grid.c:2497-2500` | `csum += 1/l[n].rz` |
| Package periphery | `sundai_hotspot/temperature.c:458-525` (vertical links 487-492, convection 494-497) | Periphery links are material-only. Convection appears only on the paths to ambient (`r_amb_*`). **The periphery is already correct.** |
| CSC orientation | `sundai_hotspot/util.c:562-613` | `cooX` is the row; each loop cell is one node-balance row |
| Default convection | `sundai_hotspot/temperature.c:31-32` | `c_convec 140.4`, `r_convec 0.1` |
| TAP layer stack | `sundai_tap/passive_interposer.py:144-149` | Substrate, C4, interposer, microbump, chip (layer 4, powered), TIM; then HotSpot appends spreader (6) and sink (7) |
| TAP package scaling | `sundai_tap/passive_interposer.py:151-165` (154-156) | Spreader = 2x interposer, sink = 2x spreader, `r_convec = 0.1*0.06*0.06/s_sink^2` (h held at HotSpot's default) |
| Base package config | `sundai_tap/util/hotspot.config:17, 19, 21, 23, 29, 31, 33, 48, 78, 112, 114, 123` | `r_convec 0.1`, `s_sink 0.06`, `t_sink 0.0069`, `k_sink 400`, `s_spreader 0.03`, `t_spreader 0.001`, `k_spreader 400`, `model_secondary 0`, ambient 318.15 K, grid 64x64, `grid_map_mode center` |
| TAP's own HotSpot call | `sundai_tap/passive_interposer.py:197-210` | No `-grid_map_mode`, so `center` from the config. Reports `max(float(stdout_tokens[3::2])) - 273.15` |
| Oracle identity | `sundai_hotspot/tap_oracle.py:173-188, 549-576` | `solver_version` and `problem_hash` bind the binary SHA-256 and the generator file hashes |

Generated package per fixture [READ: `passive_interposer.py:154-156`; COMPUTED]:

| Interposer | Spreader | Sink | `r_convec` | h |
|---|---|---|---|---|
| 50 mm (our fixtures) | 100 mm | 200 mm | 0.008999999999999998 K/W | 2777.8 W/(m^2 K) |
| 45 mm (paper) | 90 mm | 180 mm | 0.011111111111111112 K/W | 2777.8 W/(m^2 K) |

## 3. Frozen equations

These are fixed in `sundai_hotspot/coupling_variant.py` (`cell_resistances`, `area_resistances`) before any run.
For grid cell (i, j) with area `A = cw*ch`:

```
rz_sp      = t_sp / (k_sp A)                    spreader material
rz_hs,mat  = t_hs / (k_hs A)                    sink material
R_conv     = r_convec s_sink^2 / A              this cell's share of convection (per area: 1/h)
rz_hs      = rz_hs,mat + R_conv                 what populate_R_model_grid stores for the sink layer
```

**OLD** (HotSpot 7 as vendored, `coupling=hotspot7_default`):

```
R(spreader <-> sink)  = rz_sp/2 + rz_hs/2 = rz_sp/2 + rz_hs,mat/2 + R_conv/2
R(sink -> ambient)    = rz_hs              = rz_hs,mat + R_conv
series, spreader node -> ambient = rz_sp/2 + 1.5 rz_hs,mat + 1.5 R_conv
```

**NEW** (`coupling=material_only`):

```
R(spreader <-> sink)  = rz_sp/2 + rz_hs,mat/2           material only; no h
R(sink -> ambient)    = rz_hs,mat + R_conv               unchanged; convection only here
series, spreader node -> ambient = rz_sp/2 + 1.5 rz_hs,mat + R_conv
```

Every other conductance is identical in OLD and NEW: lateral links, every other vertical pair, the periphery
and the right-hand side.

Per unit area at the TAP h, OLD puts **1.80e-4 m^2 K/W (1.8 cm^2 K/W)** of convection inside the
spreader-to-sink link. The material part of that link is 9.875e-6 m^2 K/W. [COMPUTED]

**What NEW deliberately does not change.** This is a controlled, one-term change; these differences remain:

- The interior lumping rule. HotSpot 7 couples every vertical pair as half plus half. HotSpot 6.0 used the upper
  layer's `rz` (section 5).
- The sink material is still counted 1.5 times in the spreader-to-ambient series. HotSpot 6.0 counts it once
  (`rz_sp + rz_hs,mat + R_conv`). The difference is 7.4e-6 m^2 K/W, about 1 K at TAP's average flux of
  1.4e5 W/m^2. [COMPUTED]
- The layer-0 rule (`temperature_grid.c:98-102`).
- `find_res` uses `rx` for row neighbours and `ry` for column neighbours (`temperature_grid.c:106-111`). This is
  harmless on our square cells, where `rx == ry`.

## 4. Analytic result: conductance as h varies (no solver)

From `ANALYTIC.json` (`python -m sundai_hotspot.slab049 analytic`). h multipliers scale h, so `r_convec` is
divided by the multiplier. The 50 mm fixture is shown at grid 64; the 45 mm fixture has the same per-area
values.

| h multiplier | h (W/m^2 K) | Coupling | R(sp<->hs) per area (cm^2 K/W) | G(sp<->hs) per cell (W/K) | G(sink->amb) per cell (W/K) |
|---|---|---|---|---|---|
| 0.5 | 1388.9 | OLD | 3.6987 | 0.00165016 | 0.000827876 |
| 0.5 | 1388.9 | NEW | 0.0987 | 0.0618078 | 0.000827876 |
| 1 | 2777.8 | OLD | 1.8987 | 0.00321449 | 0.0016179 |
| 1 | 2777.8 | NEW | 0.0987 | 0.0618078 | 0.0016179 |
| 2 | 5555.6 | OLD | 0.9987 | 0.00611115 | 0.0030943 |
| 2 | 5555.6 | NEW | 0.0987 | 0.0618078 | 0.0030943 |

- **OLD:** the interior conductance changes with h, from 0.00165 to 0.00611 W/K per cell. That is the bug signature.
- **NEW:** the interior conductance is invariant at 0.0618 W/K per cell, about 19 times OLD at the TAP h.
- **Both:** the sink-to-ambient conductance scales with h.

**C assembly confirmation (real code, no solve).** `coupling_assembly_harness.c` builds the HotSpot grid model
from a committed TAP probe's inputs. It calls `populate_R_model` and `build_transient_grid_matrix`, then stops
without calling `dgssv`. At grid 16 and h x {0.5, 1, 2}:

- **OLD:** the assembled spreader-sink resistance is 37.8752, 19.4432 and 10.2272 K/W.
- **NEW:** it is 1.0112 K/W at every h.
- Both are **bit-identical** to the frozen Python equations.
- Every other vertical pair is unchanged across h and across builds.
- Toolchain: gcc 15.2.0, Ubuntu (WSL).

## 5. Upstream: HotSpot 6.0 (TAP's version) vs 7.0 (vendored)

Read-only web check of `github.com/uvahotspot/HotSpot` and `github.com/bu-icsg/TAP-2.5D`. [READ unless marked]

- **Vendored code equals upstream `f18831e`.** `temperature_grid.c` has the same SHA-256 (275,052 bytes, 6,778
  lines). Only two upstream commits ever touched the file:
  - `a7a3286e` (2019-01-23), "Initial commit to migrate HotSpot 6.0 to GitHub"
  - `e68c9187` (2021-04-21), "Finalized everything for HotSpot 7.0 Release", +3428/-1308 lines, one squashed commit
  `f18831e` itself only adds an example script.
- **HotSpot 6.0 coupled the spreader and sink through the spreader's `rz` alone, in both solver paths.**
  - 6.0 has no `find_res`.
  - SuperLU path: `build_steady_grid_matrix` used `Ra = find_res_3D(l-1)` and `Rb = find_res_3D(l)` (6.0
    L3396-3397). That is the upper layer's `rz` from both sides.
  - Iterative path: macros `BC_det3D`/`AC_det3D` (6.0 L2228/2230) follow the same rule.
  - Sink to ambient: the full sink `rz` (6.0 L3446-3447, L2335-2336).
  - So 6.0 counted convection exactly once.
- **The convection share entered the interior link with 7.0.** `find_res`'s half-plus-half rule, applied to the
  convection-laden sink `rz`, arrived in `e68c9187`. No finer history exists, because the source fork returns 404.
- **TAP-2.5D pinned a HotSpot 6.0 binary.** TAP's `util/hotspot` is a prebuilt binary; the README says it was
  "compiled from HotSpot-6.0".
  - It links only libc and libm and has no SuperLU symbols, so it was built with `SUPERLU=0` and uses the
    iterative path.
  - Its debug-info line numbers for 12 `temperature_grid.c` functions match `a7a3286e`.
  - [INFERRED: binary inspected, not disassembled] TAP's published numbers came from spreader-only coupling.
- **No upstream issue mentions this.** None of the 23 upstream issues and PRs discusses convection double counting.
- **TAP's metric.** HotSpot 6.0 prints `Unit Steady(Kelvin)`, then the steady dump, to stdout (6.0
  `hotspot.c:548-549`). TAP's selector is therefore the maximum over every block of every layer and the package
  nodes, centre-mapped in TAP's config. Our J is the layer-4 grid maximum. The per-solve record
  (CALL-LIST-v4.md) captures both.

## 6. Evidence in committed outputs (read-only; corroborating, not causal)

Every temperature in this section is simulated (HotSpot 7 detailed-3D coupling; withdrawn pending the HS6
correction). None is measured.

The 2026-10-18 probe (`sundai_hotspot/probe_results/*`) kept every layer's grid temperatures, printed to 0.01 K.
It ran this source, built without SuperLU, so it also assembled through `find_res`. [COMPUTED,
`committed_output_residuals`]

- **Node balance.** Interior spreader and sink cells have no power, so the conductance-weighted neighbour sum
  must vanish.
  - With the **OLD** equations, every one of the 8,768 interior checks (8 cases) is within the +/-0.005 K print
    rounding bound. The worst case reaches 0.86 of the bound.
  - With **NEW**, every check is violated, by up to 946 times the bound.
  - So the committed solver output is exactly the OLD model.
- **Energy split.** At `baseline_center_32`, the OLD links carry **267.1 W** from spreader to sink. That
  reproduces warden's figure. The grid sink cells give 86.5 W to ambient directly; the rest leaves through the
  sink periphery.
- **Where the rise goes.** The spreader-to-sink drop reaches **51.6 K** of the 73.7 K chip-layer rise at that
  layout. The maximum spreader temperature is 115.11 C; the maximum sink temperature is 63.51 C.

This corroborates that the executed model puts half the convection resistance between the spreader and the sink.
**It does not show that this term causes the 2.3 to 2.4 times gap against the paper.** Other in-model
differences are listed in CALL-LIST-v4.md. Only the controlled OLD/NEW comparison can attribute the gap.

## 7. Implementation

Line numbers in this section are on this branch.

| Piece | Location |
|---|---|
| Variant code, compiled only with `-DSENTILAB_SINK_COUPLING_MATERIAL_ONLY=1` | `sundai_hotspot/temperature_grid.c:26-46` (helper and identity tag), `125-129` (the `find_res` branch) |
| Build target | `sundai_hotspot/Makefile:193-203`: `make SUPERLU=1 hotspot-material-only`. Not in `all`; the default objects are untouched. |
| Image | `Dockerfile:20-25` builds the binaries and writes each gate-zero evaluator's build provenance. `.gitignore` and `.dockerignore` list the binaries and `*.provenance.json`. |
| Evaluator identity | `sundai_hotspot/coupling_variant.py`: `MaterialOnlyCouplingOracle`. It requires the tag in the binary bytes it hashed. `solver_version` gets `+SLAB-049:coupling=material_only`. `problem_hash` is a new schema over the base hash, the coupling, the tag and the variant source hashes. The worker re-hashes those sources before every solve, and `evidence_kind` is labelled. |
| Frozen equations | `coupling_variant.py` `cell_resistances` / `area_resistances` |
| Tooling (no solves) | `sundai_hotspot/slab049.py`: analytic report, committed-output residuals, slab inputs, the raw reference layouts and their frozen inputs, the manifest and its check, and the strict per-solve record |
| C harness (assembly only) | `sundai_hotspot/coupling_assembly_harness.c` |
| HotSpot 6.0 evaluator | `sundai_hotspot6/` (upstream `a7a3286e`, blob-checked), `scripts/build_hotspot6.sh` (x86_64 and aarch64), `sundai_hotspot/evaluators.py` (`HotSpot6Oracle`, `make_oracle`) |
| Gate zero | `sundai_hotspot/gate_zero.py` (raw references, the frozen predicate, identities, ledger-assembled records, refusal), `sundai_hotspot/reference_validation.py` (`validate-reference`, the one enforcement entry, and `record`/`report` by call id) and `sundai_hotspot/provenance.py` (build provenance and runtime library identity) |
| Raw reference layouts | `docs/sentilab/diagnostics/SLAB-049/references/raw-layouts/`: SLAB-048's raw sections (PR #57 at `063f659`), pinned by their own content hash |
| Tests | `sundai_hotspot/test_sink_coupling.py`, `sundai_hotspot/test_gate_zero.py`. The container smoke loop picks them up automatically. |

**The default is byte-identical** (author host: gcc 15.2.0, glibc 2.43, SuperLU 7.0.1; WSL Ubuntu):

| Artifact | SHA-256 |
|---|---|
| `hotspot`, built from `3e7c480` (pristine) | `37b2a3bc8dc524625392a48e64a7e8a9eabf998d1c35a6dc383a83ae2287a4aa` |
| `hotspot`, built from this branch | `37b2a3bc8dc524625392a48e64a7e8a9eabf998d1c35a6dc383a83ae2287a4aa` (identical) |
| `hotspot-material-only` (NEW) | `e59230147e15c54f782ebf94d2aaf7c6f3da3456954553787a221bf2850ed132` |
| `temperature_grid.o`, pristine and default | identical (`9a766c71...`) |

Both binary hashes are unchanged after merging main's SLAB-046 CI launch gate, built without `CI_ALLOCATION` (the
gate compiles to nothing then). A `CI_ALLOCATION=1` build, as in the CI image, carries the entry guard and differs.

Binary hashes depend on the toolchain. The grant host pins its own hashes at run time through the oracle. The
source identity of NEW is the SHA-256 of `temperature_grid.c`, `Makefile` and `coupling_variant.py`, as listed
in `problem.generator_sha256`.

**What the tests show** (99 tests across both modules; the native, fake-solver and built-binary tests run on
POSIX and in the CI image; 38 code mutants, each caught by a named test):

- **Default byte-identity.**
  - Stripping the variant blocks from `temperature_grid.c` gives exactly the upstream bytes.
  - The default object equals the pristine object.
  - The default assembled matrix equals the pristine matrix byte for byte at three h values.
- **NEW.** It equals the frozen equations bit for bit and does not depend on h. It changes exactly the
  `4 x rows x cols` spreader/sink entries and nothing else.
- **Mutations.**
  - A variant that keeps convection in the link is caught by the h-dependence check.
  - A perturbed default branch is caught by both the source-identity check and the matrix byte-identity check.
- **Committed output.** The probe output satisfies OLD and violates NEW.
- **Block extents.** The replica of HotSpot's `set_bgmap` reproduces every block value in the committed max-mapped
  steady files.
- **Identity.** The variant oracle refuses an untagged binary, and its identity never equals the default's.
- **Generated artifacts.** The committed artifacts are exactly what the code generates.
- **Gate zero.**
  - The pinned values, roles, raw layout hashes, predicate and input digest are fixed.
  - Each evaluator kind accepts only its own binary.
  - A record is built from the ledger by call id. It is FAIL on a completed miss (primary or replay) or a replay
    that differs; INCOMPLETE, never PASS, when a required outcome is withheld, unsettled or incomplete; and refused
    when it is forged, binds another binary, manifest, call, grid or layout identity, or comes from stale inputs.
  - The bootstrap path (`validate-reference`, driven by a fake solver) runs the raw off-lattice references without
    a prior PASS; the search path still refuses them; the four required receipts unlock search at grid 64 only.
  - The entry refuses anything off the manifest before reserving it, holds the cumulative count and CPU, sets
    RLIMIT_CPU, kills the whole process group at the wall deadline, and runs a private copy of the binary.
- **Strict parser.** Astra's controls are rejected: an extra layer-4 cell, and a duplicate layer 4. So is one
  mutation per rule.
- **HotSpot 6.0 source.** Every vendored file matches its upstream blob. The SentiLab block touches only the grid
  writer.

## 8. Room decision: settled cause, HotSpot 6.0 evaluator, gate zero

Warden #56773, astra #56778, #56780, #56785 and #56794, and aneta #56739. [READ: room messages, relayed by the
coordinator]

**The cause is settled without new solves.**

- **Source:** warden traced the HotSpot 7 chain in our code. `temperature_grid.c:104` links layers half and half;
  `:1056` puts the cooling term in the sink's `rz`; `:167` reads that `rz` back on the link. TAP runs with
  `-detailed_3D on` (`passive_interposer.py:205`).
- **Saved grids:** astra's zero-solve read shows a 51.10 K / 51.60 K drop inside the copper, the v7 signature,
  confirmed by a second, independent parser over 28 of 28 hashes.
- **Section 6 agrees.** `committed_run1_signature` in `ANALYTIC.json`, read from files only, gives on all 8 saved
  probes:
  - spreader rise 69.6-71.0 K and sink rise 18.4-18.6 K, within 2.5-4.0 K of aneta's v7-link signature
    (73.5 / 19.2 K) and about 43 K from the other two;
  - `r_convec = 0.008999999999999998`, the generator's scaled value. That rules out the unscaled-`r_convec`
    route for those probes. The generator skips an existing config, so its source alone does not prove it for
    every run.

**HotSpot 7 is not patched as the path forward.**

- **The residual:** in aneta's independent network model (`thermal-network.mjs`, SHA-256 `2fedbad9...`), taking
  convection out of v7's link still leaves +3.0 K on Ascend and +10.8 K on CPU-DRAM. With HotSpot 6.0's form, the
  model lands at 75.09 C and 116.27 C, against the paper's 75.48 C and 115.94 C.
- **What remains of the residual:** these are the lumping differences in section 3 that the single-term variant
  leaves alone.
- **The variant's role:** it remains bounded diagnostic evidence, not the MATCH evaluator. Its earlier call plans
  are not requested.

**The HotSpot 6.0 evaluator.**

- **Source:** `sundai_hotspot6/` is uvahotspot/HotSpot `a7a3286e368867c26381e0a23e36b3e273bdeda9`. That is
  TAP-2.5D's version: its `util/hotspot` is a 6.0 binary whose debug lines match this commit, built without
  SuperLU.
  - `UPSTREAM_BLOBS.txt` pins the git blob of all 30 vendored files.
  - One macro-gated block (`SENTILAB_GRID_DUMP_ALL_LAYERS`) changes only the grid writer, so the chip, spreader and
    sink layers can be read. Without the macro the file compiles to the upstream text.
- **Physics:** HotSpot 6.0 couples layer n to n+1 through `rz(n)`, in both solver paths (`BC_det3D`; and
  `build_steady_grid_matrix`, where `Rb = find_res_3D(l)`). So the spreader-to-sink link is the spreader's
  material alone, and convection appears once, on the link to ambient.
- **Build:** `scripts/build_hotspot6.sh` works on x86_64 and aarch64 with the same Debian/Ubuntu packages. It
  builds:
  - `hotspot`, the evaluator: SuperLU, `-ffp-contract=off`;
  - `hotspot-tap-faithful`: `SUPERLU=0`, as TAP built it.

  On the author box (WSL, gcc 15.2.0), both build with no source changes. Binary hashes depend on the toolchain
  and, through the Makefile's `-g`, on the build path, so each host pins its own through gate zero. Each build
  writes `<binary>.provenance.json` (compiler, make command and flag lines, build path, SuperLU/BLAS/libc package
  versions, every library the loader resolves with its hash, the binary hash); validate-reference requires it.
- **What `-ffp-contract=off` does and does not do:** it stops GCC contracting `a*b+c` into one fused multiply-add
  in the HotSpot sources compiled here (GCC contracts by default where the target has FMA, as aarch64 does; the
  x86_64 baseline target has none). It does not reach the precompiled SuperLU, BLAS or libm, which may choose FMA
  or other kernels per CPU. It narrows cross-architecture differences; it does not make results bit-identical
  across architectures, and no such claim is made. An aarch64 build needs its own gate-zero receipts.
- **Selector:** `evaluators.make_oracle(evaluator, purpose)`. `HotSpot6Oracle` has its own solver version
  (`HotSpot-6.0:a7a3286e...`) and problem hash. HotSpot 7's class, binary and identity are unchanged.
  - Code that constructs `HotSpotOracle` directly (the live loop and the existing headroom runner) is not
    rerouted. Rerouting it would stop them until HotSpot 7 passes gate zero, which is an owner decision.
- **Licence:** the UVA notices are kept (`sundai_hotspot6/LICENSE`, `THIRD_PARTY_NOTICES.md`, and
  `/licenses/HotSpot-6.0-LICENSE` in the image).

**Gate zero (`gate_zero.py`).** Root #56858, forge reply `1ed1c902` and astra's supplement on PR #56 (comment
6545712065) fixed it to the raw geometry; warden #56856 set the grant prerequisites.

- **The rule:** search and headroom refuse an evaluator identity until a PASS for its exact binary re-derives from
  the grant's ledger: the pinned originals reproduced at 45 mm and grid 64, on the block-centre metric, within the
  prospective computational reference-reproduction tolerance of 1.0 K.
- **The references are raw.** TAP-2.5D's originals as SLAB-048 decoded them (PR #57 at `063f659`), with their
  continuous centres and rotations: Ascend 910 at 75.48 C and CPU-DRAM at 115.94 C. Each is pinned by its raw
  section's own content hash (`15c77bbe...`, `6eba70b6...`), checked on the vendored copy and on SLAB-048's record,
  now in the tree (#57 merged at `a48ceec5`, main `d298cb0`); any change to raw fails. SLAB-048's own continuous
  rules (`TapGeometry.continuous_centers_for`) are cross-checked on both raw layouts, which its search lattice still
  refuses. SLAB-048 keeps raw byte-stable and puts later notes in
  `raw_annotations` and `snapped_annotations`, which are descriptive only and never read by the gate. Raw geometry is
  judged by the continuous rules only (margin, halo, 0.1 mm body spacing); the search lattice never applies to it,
  and the search path still refuses it.
- **Snapped variants are other identities.** They are an engineering comparison, carry no paper-match claim, and
  cannot enter a gate-zero record.
- **The frozen predicate:** the native6 primary and its fresh-process replay at grid 64 on each reference, four
  outcomes, each within 1.0 K, each replay byte-identical to its primary. FAIL on a completed miss; INCOMPLETE
  (STOP, never PASS) when any required outcome is missing, unsettled or incomplete. The native7 comparator and the
  grid 32 calls are reported, never judged.
- **Deferred, not omitted:** the TAP-2.5D solutions, 75.47 C and 94.89 C, are declared pending verification for a
  later allocation, with no calls here. Every record lists them under `pending_verification`.
- **The digest:** the references digest covers values, roles, raw layout hashes, frozen inputs, the predicate, the
  tolerance and the metric, so any change invalidates old records.
- **Bootstrap:** `reference_validation validate-reference` produces the first receipts and needs no PASS. It is the
  one in-code enforcement entry (CALL-LIST-v4.md lists what it enforces and what the operator supervisor must).
  It writes fresh inputs into a fresh directory with TAP's own generator, checks them byte for byte against the
  frozen ones, and records their hashes and the effective start and stop. It never runs under main's CI allocation
  (`CI_ALLOCATION=1`, SLAB-046), where every native HotSpot launch goes through `sundai_hotspot.ci_gate`, and it
  refuses a binary built with the CI entry guard. Its process launches are listed in `docs/ci-spawn-review.md`.
- **Records:** assembled from the ledger by admitted call id, never from caller-chosen directories. Each outcome is
  bound to its manifest row, reservation, settlement, receipt, outputs and frozen inputs, and then re-derived from
  the raw files by the strict evaluator-bound reader that settles a run: grid size, layer count, header format and
  complete block evidence. Bound evidence that fails it (a 4 x 4 x 8, 64 x 64 x 1 or 64 x 64 x 7 grid declared as
  grid 64, say) is unusable, so the record is INCOMPLETE, never PASS. The verdict is recomputed every time; the
  stored one is never trusted. `report` uses the same verification and derivation. A PASS covers grid 64 on the
  block-centre metric only, not the search objective J.

**The 12-call manifest** is in [CALL-LIST-v4.md](CALL-LIST-v4.md), a new version beside the unchanged prior one:

- 2 raw 45 mm references x 2 engines (native6 target, native7 comparator) x grids 32 and 64;
- plus 4 fresh-process grid-64 replays, one per reference and engine;
- explicit `--call` and `--timeout` on every row; timeouts 8 x 60 s + 4 x 15 s = 540 s plus a 24 CPU-s overhead
  assumption, a 564 CPU-s forecast (not a CPU guarantee) inside the binding 600 CPU-s manifest cap; no retries,
  expiring 2026-11-01T12:00Z.
