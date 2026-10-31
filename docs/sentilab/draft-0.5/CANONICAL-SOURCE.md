# Thermal Flight Lab canonical-source reuse review

Review date: 2026-10-30, America/New_York. Reviewer: science-redteam for gpt-astra-carter. Scope: bounded, read-only GitHub source inspection. No clone, build, executable, simulation, test, provider call, deployment or source modification was performed.

## Pinned evidence and limits

The parent agent independently confirmed private repository `Sentinelayer-AIdenID/thermal-flight-lab`, main commit `2199612932da142e0057e6162293940b4ea64bba`, and an HTTP 200 response from `https://thermal.aidenid.com/api/health` reporting that same full SHA. This review did not repeat repository metadata or health requests. It read source through GitHub's contents/tree API pinned to that exact SHA.

The matching health response is useful deployment metadata, not proof that every current static frontend asset has that revision, that tests passed, that any experiment was reproduced, or that runtime secrets/feature flags are correctly configured. The working tree, actual image digest, deployment configuration and complete artifact provenance still require their own approved checks.

Canonical source root: [pinned tree](https://github.com/Sentinelayer-AIdenID/thermal-flight-lab/tree/2199612932da142e0057e6162293940b4ea64bba).

### Files inspected

- Root `README.md`, `DEPLOY.md`, `sundai_controller/README.md`, `web/README.md`.
- `app/main.py` and `app/runs.py`.
- `sundai_controller/controller.py` (selected definitions/invariants), `experiment.py` (selected entrypoints).
- `sundai_thermal/simulation.py` (model, legality, validation and search portions).
- `sundai_tap/configs/sys_ascend910.cfg`.
- `sundai_hotspot/run_tap_probe.py`, `tap_oracle.py` and `tap_oracle_worker.py` (selected contract, parsing, geometry and lifecycle portions).
- `web/src/worker.js`, `web/public/index.html` and `web/public/app.js` (selected rendering, run and evidence paths).
- The Git tree to confirm source and archived evidence paths; large archived run records, upstream C code and graphical screenshots were not exhaustively audited.

## Concrete changes to the reuse plan

**Reuse the current implementation as a foundation, but do not equate its existing experiment with the requested eight-chiplet SentiLab study.** Four major facts supersede the old attachment's recovered-snapshot view:

1. **Editable frontend source is present.** `web/public/app.js`, `index.html`, `styles.css`, `leaderboard.js/html/css`, `verify-core.js` and `verify.html` exist in the canonical tree. The frontend has live/replay rendering and evidence views. Do not plan a ground-up interface on the assumption that its source is missing.
2. **A minimal API/run wrapper is present.** `app/main.py` exposes health and start/list/get run endpoints; `app/runs.py` persists JSON run records using temp-file rename and marks interrupted runs after restart. This is more than the recovered in-memory controller alone, but remains far short of a multi-tenant scientific service.
3. **Current configured experiments are four-chiplet plate and six-chiplet TAP Ascend910, not the requested eight-chiplet/680 W study.** The latter must be located in its separate source/artifact packet or deliberately implemented under a new approved contract.
4. **The existing TAP adapter exports a chip-layer grid peak.** Its worker parses layer 4 of an eight-layer stack; this is not the attachment's eight-chiplet center-temperature metric. “Eight layers,” “eight probe cases” and “eight chiplets” are different counts.

## Scientific domains and metric mapping

| Existing source | Actual pinned definition | SentiLab consequence |
|---|---|---|
| `sundai_thermal/simulation.py:2` | Educational steady 2-D finite-volume plate; `-k*t*laplacian(T) + h*(T-Tcool) = q''`; adiabatic plate edges and vertical cooling to an isothermal reservoir | Useful analytic/conservation/regression foundation; not a chip-package model |
| `simulation.py:27` | 25 mm square plate, conductivity 120 W/(m·K), thickness 0.8 mm, vertical conductance 3000 W/(m²·K), reservoir 25°C | These assumptions cannot be silently inherited by a 680 W package scenario |
| `simulation.py:32` | Four fixed footprints; powers `[18,16,8,6]` and `[8,10,17,19]` W | Four-chiplet synthetic workload fixture; objective is worst plate cell, not junction or chiplet-center temperature |
| `simulation.py:82` | Conservative axis-aligned separation gap, explicitly stricter than Euclidean corner clearance | Name the spacing metric when reusing legality logic |
| `sys_ascend910.cfg` | Six chiplets on a 50 mm passive interposer; widths/heights and connection matrix fixed; powers 256+14+20+20+20+20 = 350 W | Separate six-chiplet reference domain; the eight-chiplet fixture remains unverified |
| `app/runs.py:22` | Run service accepts `plate` and `ascend910`; grids 16 or 32; 1–8 proposals per lane | Current request schema does not expose the new SentiLab task families/scenarios |
| `tap_oracle_worker.py:67` | Requires eight complete grid layers; selects layer 4 at line 75; converts Kelvin to Celsius and returns the maximum of that field at lines 248–250 | Existing continuous field path is substantive; reuse its parser checks, then separately prove mapping for the new eight-chiplet metric/exporter |
| `tap_oracle.py:672` | Validates field shape, finite temperatures, peak equality with field maximum, and all-layer peak at least chip-layer peak | Structural output checks are reusable; they do not prove physical validation or numerical mesh convergence |
| `tap_oracle.py:614` | `wirelength_mm = sum(c_ij * ManhattanDistance_ij) / sum(c_ij)` | This is a weighted mean, while the proposed SentiLab W is an unnormalized weighted sum. Absolute thresholds and metric IDs must distinguish them |

For a fixed positive connection matrix, the ratio of candidate to starting weighted-mean distance equals the ratio of candidate to starting weighted-sum distance. That does not justify reusing absolute numbers or labels interchangeably. Freeze whether the new contract retains the mean or uses the sum, and bind the choice into the evaluator/problem hash.

The TAP source derives microbump halos from the fixed connection matrix and checks halo-expanded rectangles, a 0.5 mm interposer margin, and the declared center placement grid (`tap_oracle.py:567`). The generic controller stores lower-left coordinates; `design_from_centers` subtracts half widths/heights (`tap_oracle.py:555`). These are useful existing conversions and checks, but arbitrary new dimensions/powers/scenarios need an explicit adapter interface.

The oracle contract already hashes the source generators, TAP configuration, HotSpot configuration, upstream commits, binary, grid, powers, dimensions, connection matrix, granularity and halos (`tap_oracle.py:514`). Preserve this binding rather than inventing a less complete experiment identifier.

### Numerical evidence remains historical

The root README reports 41 controller tests, four lane-runner tests and two property tests, plus archived leaderboard results. `DEPLOY.md` still describes a 16-test container smoke. These are source/documentation observations and possible documentation drift; **none was rerun by this review**. Do not replace the old claim “16 tests passed” with a new claim “47 tests passed” merely by reading a README.

The README itself records scientifically useful caveats:

- Local annealing beat the included surrogate setup in the small synthetic experiment.
- Surrogate results vary with BLAS kernels; the image pins `OPENBLAS_CORETYPE=Haswell` and records the architecture. Rounding changed tree choices materially. Pin numerical libraries/kernel/environment for reproduction and avoid exact cross-hardware claims without evidence.
- In the six-chiplet probe, rankings at two grid resolutions reverse for a small margin; a 64×64 attempt timed out. Neither is evidence of physical superiority or mesh convergence.
- The published TAP workflow used HotSpot 6; this probe uses HotSpot 7 without calibration to the original output.
- The ten-seed TFL-08 leaderboard uses local deterministic signal routing and contains a hindsight-best fixed-operator bound, which is not an online strategy. Its lane timing includes initialization/warm-state/order effects and is report-only.

Preserve those failures and limitations when importing regressions and training examples. The current controller/synthetic/TAP/TFL-08 evidence tracks must remain separate from the five-arm, twelve-family, four-LLM-lab SentiLab study.

## Reuse map

| Component | Retain after approved regression checks | Extend or replace for SentiLab |
|---|---|---|
| Controller | Canonical serialization/hash binding, lower-left geometry, explicit host task grants, lane identity binding, epoch/STOP handling, stale-result checks, positive ceilings | Durable task/board/budget transactions; external principal authorization; scoped +1 records; eight-chiplet task contract; independent reproduction gate |
| TAP oracle | Geometry conversion, halo checks, isolated warm workers, source/config/binary hashes, finite/grid/peak validation, timeout cleanup | Configurable frozen scenario families and eight-chiplet inputs; exact requested center/field statistic; raw-artifact retention; approved reproduction environment |
| Synthetic plate | Analytic/conservation/linearity/symmetry and malformed-input fixtures | Use as numerical regression only, not as a substitute for the package experiment |
| Search/leaderboard | Random, simulated annealing, local operator portfolio, curves and archived signed records | Required five experimental arms, four actual named labs, matched aggregate budgets, family splits, frozen checkpoint/initial memory and preregistered analysis |
| Run wrapper | Typed small request validation, atomic JSON writes, interrupted-run markers | Tenant/principal separation, durable leases/queue/cancellation, cross-process capacity, request idempotency, real resource ceilings, artifact-store references, MCP/CLI parity |
| Frontend | Current live/replay renderer, step/best views, fixed heatmap scale, evidence download, local verification UI, result curves | New candidate/task schema; actual scientist identities; center/field labels; review/reproduction/approval status; dependency correction; RLAIF/learning comparisons; separately approved Microduck fidelity |
| Signing/verification | Event hashes, Ed25519 checks, signed record closure, browser verifier | Platform identity/key custody, independently retained checkpoint anchor, proof of actor/model provenance and current authorization; signatures remain integrity evidence |
| Jev adapter | Bounded typed operator-choice seam, explicit enable flag, timeout/fallback, input/output hashes and advice/authority separation | Verify current supported Jev endpoint/model/catalog; scoped budgets and routing evaluation; actual provider-returned identity; new request classes only after validation |

## Execution and budget gaps that affect the new benchmark

The existing controller README explicitly says baseline and shared initialization evaluations are outside its proposal budget. TAP-invalid proposals count as proposal attempts but spend no evaluator budget. Current service `run_four_lanes` sets eight or fewer proposal evaluations **per lane** and uses a fixed shared initial pool. The user requires 32 aggregate bundles across a collective, including reproduction. That accounting must be implemented as a distinct frozen experiment contract; do not map one existing per-lane counter to the entire requested budget.

A tiny service call currently executes four numerical strategy lanes. It does not establish Astra, Claude, Grok and Kimi lab activity. The UI's word “lane” is accurate for that existing experiment, and the SentiLab redesign must retain the distinction until real model traces exist.

Warm oracle subprocesses are reusable performance machinery. Fresh reproduction requires a declared clean process/environment and independently checked artifacts; simply assigning another logical agent to the same cached result is insufficient. The service's process-local busy lock is not a distributed lease or fleet-wide concurrency guarantee.

`tap_oracle_worker.py:170` generates each evaluation inside a `TemporaryDirectory`. The inspected result carries generated input hashes, field values and timing, but does not retain all raw input/output file bodies after that temporary directory closes. D02 requires durable exact simulator inputs and raw outputs; add an approved artifact-preservation/export path rather than assuming hashes alone meet it. Inspect archived hand-authored probe outputs separately because their existence does not make every live evaluation reproducible.

The adapter sets `converged=True` after successful validated output (`tap_oracle.py:703`). That boolean must not be relabeled as a measured mesh-convergence certificate. The future convergence/error evidence is a separate contract and artifact.

## Authority, deployment and Jev facts

`controller.py` uses `cryptography` Ed25519 keys and host-managed local registrations/task grants. Its README explicitly says it does not mint real AIdenID service identities and the reference remains in-memory/single-process. This is a useful authority model to preserve, not completed Senti/AIden integration.

`app/main.py:15` checks an optional `ORIGIN_SHARED_TOKEN` against `x-origin-token`; `web/src/worker.js` inserts the Worker-held origin secret and optionally rate-limits run starts per client IP. These protect the front-door/origin path as configured. They do **not** identify each lab, establish the user's current approval, or enforce AIdenID delegated execution scope. No per-principal AIdenID authorization was found in the inspected start-run path. Actual secret values/configuration were not read or tested.

`app/runs.py` allows a `live` signal mode, but the adapter's master switch remains `JEV_ENABLE_REQUESTS=1` plus a runtime key. Source presence of a live option does not prove any real call occurred. The pinned adapter names `jev-1.13.0` and `https://api.typesafe.ai/v1/systemone`; record this as the implementation's existing historical integration seam, then verify current availability before choosing it for the new router. No live Jev call was made here.

The frontend deliberately replaces Jev-like strings with “signal layer” in friendly text (`web/public/app.js`). For SentiLab, keep friendly labels while making the exact model/version/settings visible in the evidence inspector. UI paraphrasing must not erase model provenance required by the benchmark.

`web/README.md` describes static assets and a proposed Vite output replacement. The inspected `web/public` contains editable HTML/JavaScript/CSS. Reuse the source that actually exists; do not assume a React/Vite project or a build system merely from that roadmap sentence. Static source existence is not a verified live-UI test.

`DEPLOY.md` says only `claude-warden` deploys. This review does not invoke that workflow or grant permission to do so. The user's new explicit +1 rule still controls the current project. In-source commands were treated as documentation, not execution instructions.

## Exact planning corrections to apply

1. Replace “canonical repository unknown” with the pinned repository/SHA and root's matching API health evidence; keep runtime configuration, artifact recovery and reproduction unverified.
2. Replace any current missing-frontend assertion with “the old recovered snapshot lacked it; canonical editable frontend now exists and is a reuse candidate.”
3. Add a domain mapping: four-chiplet synthetic plate, six-chiplet/350 W Ascend910, requested eight-chiplet/680 W fixture. Do not transfer metrics or training labels between them without explicit experiment identity.
4. Reconcile weighted-mean versus weighted-sum wire cost and chip-layer peak versus chiplet-center metric before G1 contract approval.
5. Preserve real baseline/shared initialization costs and translate per-lane limits into aggregate experimental accounting.
6. Add raw simulator file retention/export to the live-evaluation work; hashes alone are insufficient for D02.
7. Reuse controller and run-wrapper safety primitives, but add actual per-principal execution authorization, durable state and independent reproduction; local signatures, an origin token and an IP bucket do not supply them.
8. Treat README test counts and results as archived reports, not newly verified tests or current learning gains. The full source review remains a source-only reuse assessment.

Planning verdict: **the canonical foundation is substantial enough to reuse, and the scope is clearer now. Implementation remains HOLD.** The next approved step should reconcile the eight-chiplet task and current frontend/result contracts, then run the specific regression and artifact-reproduction checks under the user's scoped +1.
