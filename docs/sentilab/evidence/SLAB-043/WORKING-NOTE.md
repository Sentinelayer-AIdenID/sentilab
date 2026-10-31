# SLAB-043 working evidence

This implementation is **incomplete**. No all-gates-green or PR-publication claim
is made. The work is by a surrogate executor under recorded model substitution.

## Current-main integration, 2026-10-31

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
