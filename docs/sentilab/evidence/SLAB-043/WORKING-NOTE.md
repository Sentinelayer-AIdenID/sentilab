# SLAB-043 working evidence

This implementation is **incomplete**. No all-gates-green or PR-publication claim
is made. The work is by a surrogate executor under recorded model substitution.

## Round-4 GB10 integration and runtime pins, 2026-10-31

Base: `0d4a6eea17971a0aaaa25992ce5cce7e44cf0a7a` (PR #42). Rebased all prior
SLAB-043 commits cleanly, retaining the accepted chiplet Node packaging correction.
GB10 integration is `fab5b5b038f429572226b11d29238adaa7f1669c`; Node runtime
pinning/provenance is `5f14b9dd5e0577ee9c7fb8d2677acc74452f4d8f`.

`gb10.status` and `gb10.checkpoint_verify` are done rows, with CLI spellings
`sentilab gb10 status` and `sentilab gb10 checkpoint-verify [--location gb10|pc|both]`,
and MCP tools `sentilab_gb10_status` / `sentilab_gb10_checkpoint_verify`.
They call the unchanged `gb10_backend.execute` through shared admission and
cancellable workers. They retain all backend receipt fields and staged scope;
backend observations (including `ok: false`) are successful transport receipts.
Invalid arguments/scopes remain shared transport errors. STOP permits these
read-only observations; SIGINT/MCP cancellation reaps the worker group.
`gb10.serve` remains pending with `gpt-astra-carter (root)` for its GPU grant.

The old evidence-reader status placeholder is replaced by the actual backend.
The unimplemented `gb10.preflight-record` placeholder was removed; no executable
legacy alias was dropped. The original broader `train.preflight`, `train.status`
and checkpoint lifecycle contracts remain separately pending. Current inventory:
18 exposed tools, 14 done rows in the matrix, four pending-conformance rows and
24 unavailable pending rows. This is not full ticket completion.

The real CLI/MCP tests substitute only the external SSH peer with a local
executable that consumes the real probe source and supplies bounded fixture
responses. No real SSH client, network, model, device or solver is invoked.
Every pre-existing non-GB10 byte assertion, including chiplet.render, remains
unchanged. GB10's `checked_at` must be valid UTC within the test's call window;
only that per-call clock value is normalized before comparing every other byte.
Tests cover successful payloads/pins, scope refusal before peer I/O, malformed
input, wire bounds, cancellation, peer failure, invalid identity/shape, default
both-location handling and pc-only operation without SSH.

Fresh checks (all commands listed as passing exited 0). Python test commands
used `OPENBLAS_CORETYPE=Haswell OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1`:

| Command | Result |
|---|---|
| `.venv/bin/python -m unittest -q sentilab_core.test_conformance sentilab_core.test_gb10_backend` | 50 pass |
| `.venv/bin/python -m unittest -q sentilab_core.test_memory_transports sentilab_core.test_mcp_stdio sentilab_core.test_dataset_mcp sentilab_core.test_cleanup sentilab_core.test_research_transports sentilab_core.test_resultcheck sentilab_core.test_resultcheck_boundary sentilab_core.test_resultcheck_io sentilab_core.test_resultcheck_platform sentilab_core.test_memory sentilab_core.test_routing sentilab_core.memory_conformance` | 89 pass |
| `/workspace/sentilab/.venv/bin/python -m unittest -q sentilab_core.test_conformance sentilab_core.test_mcp_stdio sentilab_core.test_gb10_backend` from disposable `/app` | 59 pass |
| `.venv/bin/python -m unittest -q sentilab_core.test_build_info` | 1 pass |
| `(cd sundai_controller && ../.venv/bin/python -m unittest -q test_controller.py test_experiment.py)` | 55 pass |
| `.venv/bin/python -m unittest -q sentilab_core.test_dataset sentilab_core.test_ledger sentilab_core.test_history sentilab_core.test_environment sentilab_core.test_signing sentilab_core.test_budget sentilab_core.test_gate sentilab_core.test_labs` | 73 pass |
| `PATH="$PWD/.venv/bin:$PATH" node --test web/test/*.test.mjs` | 216 pass |
| `sha256sum -c HASHES.txt` from `contracts` | All hashes pass |
| `node run-vectors.mjs` in `contracts/contract-0.2` and `contracts/contract-0.3` | 74 / 83 checks pass |
| `node run-view-vectors.mjs` in `contracts/view-envelope` and `contracts/view-envelope-v0.5` | 113 / 193 checks pass |
| `node run-paging-vectors.mjs` in `contracts/view-envelope-v0.6` and `contracts/view-envelope-v0.6.1` | 174 / 222 checks pass |
| `node web/test/make-sentilab-demo.mjs --check` | 44 envelopes current |
| `.venv/bin/python -m sentilab_core.capabilities --check docs/sentilab/evidence/SLAB-043/COVERAGE.md` | Pass |
| `.venv/bin/python -m compileall -q sentilab_core sentilab_cli sentilab_mcp scripts/record_build_info.py` | Pass |
| `.venv/bin/python -m pip check` | No broken requirements |
| `make -C sundai_hotspot -j4 SUPERLU=1` | Build pass; no solver execution |
| `git diff --check` | Pass |

The `/app` check included exactly the two shared browser modules and trust-pins
under `web/`, as selected by `.dockerignore`; both image requirement files were
already installed. It is an image-layout test, not a Docker build. The separately
extracted, checksum-verified Debian Node package reports `v20.19.2` and renders
seven cards using the unchanged JavaScript fragment. See `NODE-RUNTIME.md` for
resolved base/package hashes, reproduction details and `/app/build-info.json`.

Regression proof in a disposable worktree at pre-change
`5e00f0ba1f1f35141f0de7d9ba77d7a96a3abb81`: the two new GB10 tests fail with
`'pending' != 'done'` and missing `{gb10.status, gb10.checkpoint_verify}`.
Misrouting the real worker's checkpoint operation to status also causes the
new error/location test to fail (three failures and three errors). The build-info
test fails before the recorder exists, and passes after adding it. Regression sources:

- `sentilab_core/test_conformance.py`: fails on `5e00f0ba1f1f35141f0de7d9ba77d7a96a3abb81`, passes with `fab5b5b038f429572226b11d29238adaa7f1669c` (both added tests).
- `sentilab_core/test_build_info.py`: fails on `5e00f0ba1f1f35141f0de7d9ba77d7a96a3abb81`, passes with `5f14b9dd5e0577ee9c7fb8d2677acc74452f4d8f`.

Full Docker/thermal/live-conformance solver gates remain unrun: Docker is absent,
and solves remain forbidden for this lane. No npm manifest exists; no dummy npm
or TypeScript gates were added. The wider ticket's active STOP, labs and remaining
public-contract integrations remain open. Warden's 10:36 review message for
published head `86525f3a` contained an empty Verbatim section; a resend and the
referenced thread were requested before making any claim about those findings.

## Round-3 container render correction, 2026-10-31

Warden reported the `chiplet.render` valid-input assertion failing at published
PR #43 head `dd3512cd`. The local pre-fix source is
`b01c08e8ac794f31b216a2aba19cd6e4f41f5bb6`.

The image lacked both parts of the render runtime: Dockerfile did not install
Node, and `.dockerignore` excluded `web/` except `trust-pins.json`. The existing
Python render adapter executes Node and imports `lab-model.mjs`, which imports
`evidence-projection.mjs`. The fix installs `nodejs` and includes exactly those
two existing modules. No handler, fixture, test or assertion is changed. The
existing container smoke already runs the regression through both transports.

Reproduction used a detached pre-fix worktree at `/app` and
`pip install -r requirements.txt -r requirements-service.txt` in the Python 3.12
venv. Every pinned version matched; `pip check` passed. Only the Docker-included
`web/public/trust-pins.json` was retained under `/app/web`, and PATH was set to
an empty directory to reproduce the image's absent Node executable. Running:

```sh
PATH=/tmp/slab043-no-node OPENBLAS_CORETYPE=Haswell OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /workspace/sentilab/.venv/bin/python -m unittest -q sentilab_core.test_conformance.ExecutionConformance.test_each_capability_returns_identical_bytes_and_output_schema
```

failed (1 test, 1 failure) at `chiplet.render` with the reported
`AssertionError: 2 != 0` and JSON error code `-32602`, message `ValueError`.
Calling the real adapter directly exposed `FileNotFoundError: ... 'node'`.
Restoring Node alone exposed `ERR_MODULE_NOT_FOUND` for
`/app/web/public/sentilab/lab-model.mjs`.

After retaining the two modules named by the corrected `.dockerignore` and
providing Node, all **105 conformance/transport/lane tests passed** in `/app`,
including the unchanged failing test. `/app/web` contained exactly the two
modules and the trust-pins file. The exact invocation was:

```sh
OPENBLAS_CORETYPE=Haswell OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /workspace/sentilab/.venv/bin/python -m unittest -q sentilab_core.test_conformance sentilab_core.test_memory_transports sentilab_core.test_mcp_stdio sentilab_core.test_dataset_mcp sentilab_core.test_cleanup sentilab_core.test_research_transports sentilab_core.test_resultcheck sentilab_core.test_resultcheck_boundary sentilab_core.test_resultcheck_io sentilab_core.test_resultcheck_platform sentilab_core.test_memory sentilab_core.test_routing sentilab_core.memory_conformance
```

Additional fresh checks all exited 0. Python tests used the same three
OPENBLAS/OMP settings and the same venv interpreter:

| Command | Result |
|---|---|
| `/workspace/sentilab/.venv/bin/python -m unittest -q test_controller.py test_experiment.py` from `/app/sundai_controller` | 55 pass |
| `/workspace/sentilab/.venv/bin/python -m unittest -q sentilab_core.test_dataset sentilab_core.test_ledger sentilab_core.test_history sentilab_core.test_environment sentilab_core.test_signing sentilab_core.test_budget sentilab_core.test_gate sentilab_core.test_labs` from `/app` | 73 pass |
| `PATH="$PWD/.venv/bin:$PATH" node --test web/test/*.test.mjs` from the source checkout | 216 pass |
| `sha256sum -c HASHES.txt` from `contracts` | All hashes pass |
| `node run-vectors.mjs` from `contracts/contract-0.2` and `contracts/contract-0.3` | 74 and 83 checks pass |
| `node run-view-vectors.mjs` from `contracts/view-envelope` and `contracts/view-envelope-v0.5` | 113 and 193 checks pass |
| `node run-paging-vectors.mjs` from `contracts/view-envelope-v0.6` and `contracts/view-envelope-v0.6.1` | 174 and 222 checks pass |
| `node web/test/make-sentilab-demo.mjs --check` | 44 envelopes current |
| `.venv/bin/python -m sentilab_core.capabilities --check docs/sentilab/evidence/SLAB-043/COVERAGE.md` | Pass |
| `.venv/bin/python -m compileall -q sentilab_core sentilab_cli sentilab_mcp` | Pass |
| `make -C sundai_hotspot -j4 SUPERLU=1` | Build passes; no solver execution |
| `git diff --check` | Pass |

This is an image-layout reproduction on Ubuntu 24.04.5, Python 3.12.3 and
Node 22.23.3, not a Docker build: Docker is unavailable in this box. The full
container/thermal/live-conformance gates also execute solves, which this ticket
forbids. Those gates remain for CI/Warden; no all-gates-green claim is made.
The broader incomplete-ticket items below remain outstanding. Image packaging
requires elevated independent review under SWE Excellence Framework F.2/O.1;
rollback is to revert this packaging correction.

## Round-2 integration on main 780427a, 2026-10-31

Rebased the two partial commits onto supplied main
`780427afcf372591cd99fbd0998b188a9f807f1b` (#23 memory and #39 view included).
The supplied bundle again advertises `refs/remotes/origin/main`, not `main`.
Both dispatcher conflicts were resolved; all 12 main tools and all four chiplet
tools are present exactly once. No existing test assertion was removed. The
stdio schema inventory now includes the four chiplet entries alongside all
12 main entries. The memory owner handlers and direct dispatch remain available.

Memory recall, audit and route are now `done` and run through the shared
real-process execution matrix. `memory.route` explicitly maps to the existing
`route` contract, CLI `sentilab route`, and MCP `sentilab_route`. Its task mode
suggests or abstains; calibration reports held-out fixture results. It does not
silently claim the original intent compiler or route-evaluation contract.
The memory workers call the merged owner handlers with public pins and the
host-configured tenant, held-out policy and routing fixture. They receive no
signer. Shared admission precedes work; cancellation kills and reaps the worker.
The CLI retains a fixed, input-free diagnostic for mutually exclusive arguments.

Current inventory: 16 exposed surfaces, comprising 12 done rows in the execution
matrix and four pending-conformance rows; 25 unavailable pending rows remain
visible and owned. Memory write/invalidate owner code is now present, while its
authorized public transports remain pending. No memory lane is reimplemented.

Fresh checks on this round, all listed commands exit 0. Python commands use
`OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1`:

| Command | Result |
|---|---|
| `.venv/bin/python -m unittest -q sentilab_core.test_conformance sentilab_core.test_memory_transports` | 21 tests pass |
| `.venv/bin/python -m unittest -q sentilab_core.test_conformance.RegistryConformance` | 6 tests pass after final inventory assertions |
| `.venv/bin/python -m unittest -q sentilab_core.test_mcp_stdio sentilab_core.test_dataset_mcp sentilab_core.test_cleanup sentilab_core.test_research_transports sentilab_core.test_resultcheck sentilab_core.test_resultcheck_boundary sentilab_core.test_resultcheck_io sentilab_core.test_resultcheck_platform sentilab_core.test_memory sentilab_core.test_routing sentilab_core.memory_conformance` | 84 tests pass |
| `(cd sundai_controller && ../.venv/bin/python -m unittest -q test_controller.py test_experiment.py)` | 55 tests pass |
| `.venv/bin/python -m unittest -q sentilab_core.test_dataset sentilab_core.test_ledger sentilab_core.test_history sentilab_core.test_environment sentilab_core.test_signing sentilab_core.test_budget sentilab_core.test_gate sentilab_core.test_labs` | 73 tests pass |
| `PATH="$PWD/.venv/bin:$PATH" node --test web/test/*.test.mjs` | 216 tests pass |
| `(cd contracts && sha256sum -c HASHES.txt)` | All manifest entries pass |
| `node run-vectors.mjs` in `contracts/contract-0.2` and `contracts/contract-0.3` | 74 and 83 checks pass |
| `node run-view-vectors.mjs` in `contracts/view-envelope` and `contracts/view-envelope-v0.5` | 113 and 193 checks pass |
| `node run-paging-vectors.mjs` in `contracts/view-envelope-v0.6` and `contracts/view-envelope-v0.6.1` | 174 and 222 checks pass |
| `node web/test/make-sentilab-demo.mjs --check` | 44 envelopes current |
| `make -C sundai_hotspot -j4 SUPERLU=1` | Build passes; binary not executed |
| `.venv/bin/python -m compileall -q sentilab_core sentilab_cli sentilab_mcp` | Pass |
| `.venv/bin/python -m sentilab_core.capabilities --check docs/sentilab/evidence/SLAB-043/COVERAGE.md` and `git diff --check` | Pass |

The new registry regression fails against pre-fix rebased commit
`17f39efbbeaeaef654125a1abc5d8d2a2f1c5c1e` in a disposable worktree:
MCP `tools/list` returned `-32603` instead of the inventory (one test, one failure).
With the fix it passes. Three independent mutations of shipped modules are also
caught: audit downgraded to pending-conformance, removal of a main memory tool,
and removal of a chiplet tool. Each returns exit 1 with the intended assertion.
The existing memory transport assertions, including withdrawal and calibration
refusals, remain intact.

The initial 84-test run found only the stale exact stdio inventory (four missing
chiplet expectations). Adding those expectations preserves every existing schema
assertion; the complete 84-test rerun above passes.

**Full container smoke is not run:** `scripts/container_smoke.sh` executes
HotSpot solves. The ticket's zero-solves constraint remains in force; clarification
was requested. The thermal suite and solver-running live conformance gate are
also unrun. These are not green gates or a completed ticket. Remaining feature
work is GB10 evidence wrappers, active STOP-file parity, lab transports, the four
merged lanes pending unified conformance, and the additional owned pending
contracts. This is a committed partial carry for Warden, with bundle
`/workspace/slab043-v2.bundle`, not a published PR or verified operator export.

## Historical current-main integration on c40e6f1, 2026-10-31

Rebased onto `c40e6f12b0d5d94d442f8b4c6fb5edb004ce17ed`, supplied by Warden
in `/workspace/main-now-c40e6f1.patch`. The bundle advertises
`refs/remotes/origin/main`, not `main`; its actual ref was fetched. The original
work remains on `agent/sentilab`; the rebased branch is
`agent/slab043-current-main`. This is an early coherent partial carry authorized
by Warden, not full ticket completion or a published PR.

All 13 public CLI/MCP surfaces are included in discovery/drift coverage. Nine
previous entries retain the execution matrix below. ResultCheck and research
request/status/export are explicitly `pending_conformance`: they preserve their
merged lane behavior and tests, while shared scope/active-STOP integration is
still open. This status never removes them from surface-drift checks. The four
merged surfaces are not represented as absent or as fully conformant.

The registry exposes original-contract names and explains reserved aliases.
Memory write/invalidate, snapshot/evidence inspection and intent compile/route
evaluate remain visible and owned. PR #23 recall/audit/route are pending with
`astra-slab006a-mesh`, as instructed by Warden. Audit and route are not assumed to
satisfy snapshot, evidence inspection or intent compile without the owner code.
Actual GB10 device, train, checkpoint and serving contracts remain pending with
`gpt-astra-carter (root)`. The two planned GB10 evidence readers are explicitly
excluded from public-capability counts and cannot satisfy device parity.

SLAB-018 is now present: all 67 files in its committed MANIFEST.json matched
both recorded size and SHA-256. The manifest SHA-256 is
`854d8ce70db52deff30f9c77c8eba5a82a5ad5489674ade9a825b7fab66f6bcf`.
Wrapper implementation and tampered-evidence transport proof remain open.
No device was contacted and none of the recorded scripts was executed.

Two new audit regressions failed on pre-fix `1962f06` in a disposable worktree
(2 failures, exit 1), and pass with the inventory fix. The unchanged prior 13
conformance tests are retained. Registry totals are nine matrix entries,
four exposed entries pending unified conformance, and 28 unavailable pending
rows (including the two evidence readers).

Current-main checks, all exit 0:

| Command | Result |
|---|---|
| `.venv/bin/python -m unittest -q sentilab_core.test_conformance sentilab_core.test_mcp_stdio sentilab_core.test_dataset_mcp sentilab_core.test_cleanup sentilab_core.test_research_transports sentilab_core.test_resultcheck sentilab_core.test_resultcheck_boundary sentilab_core.test_resultcheck_io sentilab_core.test_resultcheck_platform` | 67 tests pass |
| `(cd sundai_controller && ../.venv/bin/python -m unittest -q test_controller.py test_experiment.py)` | 55 tests pass |
| `.venv/bin/python -m unittest -q sentilab_core.test_dataset sentilab_core.test_ledger sentilab_core.test_history sentilab_core.test_environment sentilab_core.test_signing sentilab_core.test_budget sentilab_core.test_gate sentilab_core.test_labs` | 73 tests pass |
| `PATH="$PWD/.venv/bin:$PATH" node --test web/test/*.test.mjs` | 207 tests pass |
| `(cd contracts && sha256sum -c HASHES.txt)` | All manifest entries pass |
| `node run-vectors.mjs` in `contracts/contract-0.2` and `contracts/contract-0.3` | 74 and 83 checks pass |
| `node run-view-vectors.mjs` in `contracts/view-envelope` and `contracts/view-envelope-v0.5` | 113 and 193 checks pass |
| `(cd contracts/view-envelope-v0.6 && node run-paging-vectors.mjs)` | 174 checks pass |
| `node web/test/make-sentilab-demo.mjs --check` | 44 envelopes current |
| `make -C sundai_hotspot -j4 SUPERLU=1` | Build passes; binary not executed |
| `.venv/bin/python -m compileall -q sentilab_core/capabilities.py sentilab_core/chiplet.py sentilab_core/execution.py sentilab_core/transport.py sentilab_core/test_conformance.py sentilab_cli sentilab_mcp` | Pass |
| `.venv/bin/python -m sentilab_core.capabilities --check docs/sentilab/evidence/SLAB-043/COVERAGE.md` and `git diff --check` | Pass |

Five mutations on a disposable current-main worktree were detected: remove
memory.write, change the GB10 owner (13 failing subtests), count evidence readers
as capabilities, lose the original invalidation alias, and add an unregistered
MCP tool. Each exited 1 with the expected assertion failures. These are local
mutation proofs, not independent reviewer approval.

The thermal suite, full `sentilab_core.conformance` and container smoke gate
remain unrun because they execute real solvers and this ticket permits zero
solves. No all-gates-green claim is made. The GB10 wrappers, active STOP matrix,
remaining lab surfaces, four merged-lane conformance integrations and PR #23
integration are still required. Warden requested this partial slice for early
carry; the branch is not a ticket-completion claim.

## Historical proof on the original snapshot

The following records describe the earlier snapshot and its earlier test counts;
they are not claims about the availability of modules on current main.

The provisioned source is `d031c8d25fb581f2355fc632fc8c384ba45cf973`, represented by
local snapshot tag `base` (`97b8744`). Earlier upstream history and open PR
branches are unavailable. The source has no SLAB-018 evidence directory, memory
module or ResultCheck Python transport; no rebase onto owner PRs is claimed.

## Current implementation

- A registry owns nine executable CLI/MCP capabilities and ten owned pending
  contracts. CLI choices and MCP schemas consume it. The generated COVERAGE.md
  lists availability separately from proof; adding a surface without registering
  it fails the real discovery/parser test.
- A common schema and host-scope check precedes capability execution. The host
  may set `SENTILAB_CAPABILITY_SCOPES` to a JSON array of exact capability names.
  Unset retains the existing local-operator boundary, while an empty array denies
  every call with -32001. Request arguments cannot grant scopes. AI-off, signer
  and independent public-pin checks remain in the existing lanes.
- Both transports retain the shared 64 KiB input boundary and safe error receipts.
  CLI counts UTF-8 argv bytes plus separators; MCP counts bytes before newline.
- Chiplet build calls the existing plate design and placement validation. Render
  returns the existing browser panel model, not a screenshot or a thermal solve.
  Replay verifies the signed ledger. Export calls the existing immutable dataset
  exporter. Render/replay/export refuse damaged history.
- Eight recorded operations run in cancellable process groups with public pins
  only. CLI SIGINT and MCP cancellation kill/reap the child before responding;
  the browser render child belongs to that same group. The signer-bearing live
  conductor remains in its existing async lane. EOF has a one-second bounded
  response drain before the existing cancellation and cleanup path.
- The existing MCP/cleanup test drivers now supply the required run_id for verify;
  their assertions remain intact. Their old omitted argument was inconsistent
  with the production verify contract.

## Current proof

The new ExecutionConformance tests drive real CLI processes and real MCP stdio.
They check response bytes and declared output schemas, wrong input and bounds,
unauthorized scopes without side effects, real worker cancellation on both
surfaces, and refusal of tampered chiplet history. The live.run fixture starts
with STOP already present and confirms its solve count is zero. Private signing
material for that fixture exists only in process memory/environment, never files.
The stopped-run test uses the existing no-solve BarrierOracle as a host-injected
Context through the shipped CLI main and MCP serve entry points. CLI main now
accepts the same optional host context as MCP; no request can inject one. No
transport, handler, conductor method or gate is replaced by the fixture driver.
This keeps the Python-only CI job independent of a compiled HotSpot binary.

For cancellation, the harness pauses the actual child with SIGSTOP after its
process group exists, cancels through the transport, checks the child is reaped,
and pings the still-usable MCP connection. It does not replace shipped handlers.
**This proves request cancellation, not mid-call STOP-file creation.** Active-run
STOP parity remains outstanding; existing lane STOP behavior is retained.

Observed passing commands (Python 3.12.3; Node v22.23.3). Python suites below use
`OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1`:

| Command | Result |
|---|---|
| `.venv/bin/pip install -r requirements.txt` | Exit 0, pinned dependencies installed |
| `sudo apt-get install -y build-essential libsuperlu-dev libblas-dev` | Exit 0 (after apt-get update) |
| `make -C sundai_hotspot -j4 SUPERLU=1` | Exit 0; compiled only, no execution |
| `.venv/bin/python -m unittest -q sentilab_core.test_conformance` | 13 tests pass |
| `.venv/bin/python -m unittest -q sentilab_core.test_mcp_stdio sentilab_core.test_dataset_mcp sentilab_core.test_cleanup` | 15 tests pass |
| `(cd sundai_controller && ../.venv/bin/python -m unittest -q test_controller.py test_experiment.py)` | 55 tests pass; nonphysical fixture oracles |
| `.venv/bin/python -m unittest -q sentilab_core.test_dataset sentilab_core.test_ledger sentilab_core.test_history sentilab_core.test_environment sentilab_core.test_signing sentilab_core.test_budget sentilab_core.test_gate sentilab_core.test_labs` | 71 tests pass; recorded/fixture-only |
| `PATH="$PWD/.venv/bin:$PATH" node --test web/test/*.test.mjs` | 103 tests pass |

The five newly added execution tests were extracted unchanged into a disposable
worktree at pre-feature commit `6f130c6` and run against that checkout's modules.
All five detect missing behavior. The extraction keeps their real process calls
and avoids an unrelated import failure for the then-absent chiplet parser.
Observed: 5 tests, 13 failing subtests, exit 1 on the pre-feature checkout.

One intermediate cancellation run timed out because the test paused a child
between setsid and exec, holding the subprocess startup handshake open. The
barrier now checks the actual worker command before pausing it. No production
assertion or timeout was weakened to fix that test scheduling race.

Four independent mutations of shipped code at `052c93d`, each restored in its
scratch worktree afterward, were detected with exit 1 by these execution tests:

| Mutation | Test suffix |
|---|---|
| Ignore configured host scopes | `test_each_capability_requires_host_granted_scope_before_side_effects` |
| Bypass input schema validation | `test_each_capability_refuses_wrong_types_or_bounds_without_echo` |
| Return a wrong chiplet design hash | `test_each_capability_returns_identical_bytes_and_output_schema` |
| Allow an unauthenticated/empty prefix into rendering | `test_chiplet_replay_render_export_refuse_tampered_history` |

The final 13-test conformance run passed after the scheduling fix. Python
compilation, generated coverage freshness and `git diff --check` also passed.
The valid-execution test also passes in a clean worktree without a native binary;
after that fixture correction, the wrong-design mutation fails only its intended
chiplet-build assertion. All four mutations and the pre-feature failure proof
were rerun against the final test source.

Earlier foundation proof: the three registry tests passed; independent scratch
mutations adding/removing an MCP tool, adding a CLI command, removing a pending
owner, and changing COVERAGE.md were each detected. Five transport-boundary tests
failed on pre-boundary `09d458a` (23 failing subtests), then passed with the fix.
Earlier contract checks passed: hashes, 74 v0.2 vectors, 83 v0.3 vectors, 113 v0.4
view vectors, 193 v0.5 view vectors, and freshness of 44 demo envelopes.

## Remaining prerequisites and checks

1. Supply the committed SLAB-018 evidence and its manifest contract. No fabricated
   GB10 record or guessed manifest format is substituted. GB10 wrappers remain
   pending; tampered-GB10 refusal cannot yet be proved.
2. Supply merged owner transports for memory/ResultCheck and lab hooks. Their
   reserved rows remain explicitly owned and pending. Do not duplicate the lanes.
3. Complete the requested mid-call STOP matrix, including an active live.run, while
   retaining the existing lane semantics and the zero-solves constraint.
4. Resolve the conflict between zero solves and full thermal/live-conformance/
   container gates: those suites explicitly execute real solvers. They have not
   been rerun after dependencies became available. A subset is not a full gate pass.
5. Run all applicable gates, record checklist completion only when genuinely met,
   and request operator draft publication through the prescribed review/PR route.

This Python/Node/native repository has no npm manifest or TypeScript configuration;
no dummy npm gates were added. The earlier offline dependency failures are
superseded by the latest explicit instruction to install dependencies. Setup used
network downloads and the environment probe returned HTTP 200; this work is not
claimed to be zero-network overall. Capability tests make no model/device calls
or real solver calls.

Checkpoint capture was previously refused because the nested repository snapshot
exceeded the 2 MiB patch cap. Source was not deleted or baseline tags changed to
bypass that guard. `/workspace/slab043-foundation.bundle` holds the local commits
for operator preservation; a local bundle is not a published PR or proof of carry.
