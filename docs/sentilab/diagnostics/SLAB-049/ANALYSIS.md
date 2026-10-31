# SLAB-049 CAL-COUPLING: source analysis and frozen equations

Ticket `d41fca43-2e6c-464e-8fbc-0c485e4828dd` (owner pocket-forge). Line numbers refer to `3e7c480`;
`sundai_hotspot/` and `sundai_tap/` are unchanged on `origin/main` through `1e6b97e`.

**Status.** Source analysis, code, an analytic check and a call list. **No thermal solve was run for this
ticket.** The pre-declared interpretation is in [CALL-LIST.md](CALL-LIST.md), written before any run.

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
  nodes, centre-mapped in TAP's config. Our J is the layer-4 grid maximum. The call record (CALL-LIST.md)
  captures both.

## 6. Evidence in committed outputs (read-only; corroborating, not causal)

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
differences are listed in CALL-LIST.md. Only the controlled OLD/NEW comparison can attribute the gap.

## 7. Implementation

Line numbers in this section are on this branch.

| Piece | Location |
|---|---|
| Variant code, compiled only with `-DSENTILAB_SINK_COUPLING_MATERIAL_ONLY=1` | `sundai_hotspot/temperature_grid.c:26-46` (helper and identity tag), `125-129` (the `find_res` branch) |
| Build target | `sundai_hotspot/Makefile:193-203`: `make SUPERLU=1 hotspot-material-only`. Not in `all`; the default objects are untouched. |
| Image | `Dockerfile:20-22` builds both binaries. `.gitignore` and `.dockerignore` list the new binary. |
| Evaluator identity | `sundai_hotspot/coupling_variant.py`: `MaterialOnlyCouplingOracle`. It requires the tag in the binary bytes it hashed. `solver_version` gets `+SLAB-049:coupling=material_only`. `problem_hash` is a new schema over the base hash, the coupling, the tag and the variant source hashes. The worker re-hashes those sources before every solve, and `evidence_kind` is labelled. |
| Frozen equations | `coupling_variant.py` `cell_resistances` / `area_resistances` |
| Tooling (no solves) | `sundai_hotspot/slab049.py`: analytic report, committed-output residuals, slab inputs, call list, per-call summarizer |
| C harness (assembly only) | `sundai_hotspot/coupling_assembly_harness.c` |
| Tests | `sundai_hotspot/test_sink_coupling.py`. The container smoke loop picks it up automatically. |

**The default is byte-identical** (author host: gcc 15.2.0, glibc 2.43, SuperLU 7.0.1; WSL Ubuntu):

| Artifact | SHA-256 |
|---|---|
| `hotspot`, built from `3e7c480` (pristine) | `37b2a3bc8dc524625392a48e64a7e8a9eabf998d1c35a6dc383a83ae2287a4aa` |
| `hotspot`, built from this branch | `37b2a3bc8dc524625392a48e64a7e8a9eabf998d1c35a6dc383a83ae2287a4aa` (identical) |
| `hotspot-material-only` (NEW) | `e59230147e15c54f782ebf94d2aaf7c6f3da3456954553787a221bf2850ed132` |
| `temperature_grid.o`, pristine and default | identical (`9a766c71...`) |

Binary hashes depend on the toolchain. The grant host pins its own hashes at run time through the oracle. The
source identity of NEW is the SHA-256 of `temperature_grid.c`, `Makefile` and `coupling_variant.py`, as listed
in `problem.generator_sha256`.

**What the tests show** (28 tests; the native ones run on POSIX and in the CI image):

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
