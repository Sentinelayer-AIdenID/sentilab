# SLAB-043 working evidence

This is an incomplete implementation by the surrogate executor under recorded
model substitution. No full conformance, CI-green or PR-publication claim is made.

The supplied source is `d031c8d25fb581f2355fc632fc8c384ba45cf973`, represented by
the local `base` snapshot commit. The snapshot has live/dataset transports and
ReplayLab/Dispatcher implementations. It has no `SLAB-018` evidence directory,
memory module or ResultCheck Python transport. Earlier upstream history and the
open PR branches are not included, so no rebase or historical fix claim is made.

## Implemented foundation

- One registry for five existing executable CLI/MCP capabilities and fourteen
  explicitly owned pending interfaces. Pending schemas reject all input.
- MCP input schemas and CLI namespace/command choices consume the registry.
- Generated `COVERAGE.md` makes unavailable coverage visible.
- Three tests exercise the shipped parser grammar, real CLI help, real MCP
  `tools/list`, pending ownership and coverage freshness. The existing
  `python -m unittest -q sentilab_core.conformance` CI entry loads these tests.
- Help and tool discovery defer lane imports until execution. Neither operation
  needs a signer, a solver, or the scientific Python packages.

The registry records current local-operator authorization and current STOP
behavior honestly. It does not invent scoped authorization that the supplied
dispatch code does not implement. `done` is capability availability, not proof
that its five execution checks pass.

## Proof actually run

Before adding the harness, `python3.12 -m unittest sentilab_core.test_conformance`
exited 1 with `ModuleNotFoundError` for the missing test module.

After the foundation change, `python3.12 -m unittest -v
sentilab_core.test_conformance` passed all **3 tests**. Python compilation of the
changed modules and `git diff --check` also exited 0.

Each mutation below was applied independently to a disposable worktree at
`368c1cf`, followed by its named test. Every mutation exited 1, and the original
file was restored in that scratch checkout. No working-tree stash was used.

| Mutation of shipped code/data | Test in `RegistryConformance` | Observed failure |
|---|---|---|
| Add `sentilab_unregistered` to MCP `TOOLS` | `test_real_surfaces_match_registry` | Real MCP `tools/list` returns error -32602 |
| Remove `sentilab_live_status` from `TOOLS` | `test_real_surfaces_match_registry` | MCP capability registry drift |
| Add an unregistered CLI command choice | `test_real_surfaces_match_registry` | CLI capability registry drift |
| Empty the pending memory owner | `test_pending_capabilities_are_owned_and_not_advertised` | Empty owner assertion fails |
| Append a stale coverage row | `test_coverage_document_matches_registry` | Generated document comparison fails |

These are worker mutation results, not independent review or the requested
mid-call STOP/tampered-GB10 proof. Those execution tests remain outstanding.

## Blocked gates and remaining work

The ticket requires zero network. `python3.12 -m venv .venv` succeeded, but
`.venv/bin/pip install --no-index -r requirements.txt` exited 1: no local
distribution of `numpy==2.3.5` was available. No dependency downloads were tried.

The requested gate commands were attempted with the created virtual environment:

| Command | Observed result |
|---|---|
| `(cd sundai_controller && ../.venv/bin/python -m unittest -q test_controller.py test_experiment.py)` | Exit 1, two import errors: missing cryptography |
| `.venv/bin/python -m unittest discover -s sundai_thermal -p 'test_*.py'` | Exit 1, missing numpy |
| `.venv/bin/python -m unittest -q sentilab_core.conformance` | Exit 1, missing cryptography |
| `(cd sundai_hotspot && make -j4 SUPERLU=1)` | Exit 2, missing SuperLU header slu_ddefs.h |

This repository has no npm manifest or TypeScript configuration. Its own Python,
Node contract/browser and native-build gates apply; no dummy npm gate was added.
The remaining Node and container gates have not been run. No simulation solve,
model call, device operation, network request or protected publication was made.

To finish: provision offline Python wheels and SuperLU/BLAS development files;
supply committed SLAB-018 evidence and merged lane updates; implement and prove
the common five execution checks and missing wrappers over the existing code;
rerun all applicable gates; then request operator draft-PR review. No deterministic
ticket step is recorded complete while these requirements remain outstanding.

## Additional transport boundary fix

The real CLI now refuses malformed arguments without echoing rejected input,
using the same safe error object as MCP. Both entry points enforce a 64 KiB wire
limit before importing lanes. CLI counts UTF-8 argument bytes plus one separator
per argument; MCP counts frame bytes excluding the newline. MCP rejects malformed
JSON, wrong request shapes and unsupported tool arguments safely; framed parse
errors leave `ping` usable. An oversized or unterminated frame closes the stream
after a safe error and the existing pending-task cleanup.

Five new tests in `sentilab_core/test_conformance.py` exercise shipped processes,
without replacing handlers or executing a solver. The table-driven tests check
unknown-input and oversized-wire rejection for all five available capabilities.
Additional cases cover malformed frames and the 65,535 / 65,536 / 65,537 byte
boundaries. This does not certify full schema validation or all five ticket checks.

`python3.12 -m unittest -q sentilab_core.test_conformance` passes **8 tests**.
Copying the five new tests to a disposable worktree at pre-fix `09d458a` and
running `python3.12 -m unittest -q
sentilab_core.test_conformance.BoundaryConformance` exits 1 with **23 failing
subtests** across all five tests. This is worker proof, not independent review.
Compilation of the five changed Python modules and `git diff --check` pass.

Additional gate results actually observed:

| Command (working directory where applicable) | Result |
|---|---|
| `sha256sum -c HASHES.txt` (`contracts`) | Exit 0 |
| `node run-vectors.mjs` (`contracts/contract-0.2`) | Exit 0, 74 checks |
| `node run-vectors.mjs` (`contracts/contract-0.3`) | Exit 0, 83 checks |
| `node run-view-vectors.mjs` (`contracts/view-envelope`) | Exit 0, 113 checks |
| `node run-view-vectors.mjs` (`contracts/view-envelope-v0.5`) | Exit 0, 193 checks |
| `node --test web/test/sentilab-parity.test.mjs` | Exit 0, 39 tests |
| `node web/test/make-sentilab-demo.mjs --check` | Exit 0, 44 envelopes current |
| `node --test web/test/*.test.mjs` | Exit 1, 39 passes / 3 failures; signing fixture imports lack cryptography |
| `.venv/bin/python -m unittest -q sentilab_core.test_mcp_stdio sentilab_core.test_dataset_mcp` | Exit 1, 7 tests, 6 failures / 1 error; context initialization unavailable |

The original MCP regression suites give the same 6 failures / 1 error on
pre-fix `09d458a`; their valid calls cannot initialize the lane context in this
environment. The controller, thermal, live-conformance and HotSpot gate commands
listed above were run again and fail on the same absent cryptography, numpy and
SuperLU prerequisites. No gate has been skipped, weakened or declared passing.
No PR is requested while these gates and the remaining ticket work are incomplete.

Audit correction: an external `curl --max-time 5` probe to `example.com` was
mistakenly attempted during this turn's environment inspection. The earlier
zero-network statement describes the earlier work only; it cannot be claimed
for this turn. No dependencies were downloaded and no solve, model call or device
operation was performed. Further work remains offline.
