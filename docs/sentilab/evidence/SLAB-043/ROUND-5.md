# SLAB-043 round 5: main merge and transport review fixes

The supplied bundle advertises only `refs/remotes/origin/main` at
`70e19986dd3b33fa8265d39f662959405d9d3dca`. Merge commit
`18853bfe58a20fe2196566235ab426db72e94a2a` preserves the deck CI step verbatim
from that main, its `deck/` Docker exclusion, and the chiplet renderer's two
shared browser modules. The Node pins and build provenance remain intact.

The bundle does **not** contain `gb10_serving`: `git ls-tree -r main-now/main
--name-only` contains `gb10_backend.py` and `gb10_readonly.py`, but no serving
module. Its history ends with #40, #22, #44 and #42. The requested #45 source
was requested from Warden; `gb10.serve` cannot be marked done or assigned a
guessed execution policy. This is the remaining blocker for this round.

Commit `7a9430a6be658574005a3b6518e693d7e89cc7ea` fixes both named P2s:

- Research and ResultCheck apply the shared host scope grant before lane
  dispatch on both CLI and MCP. Their existing input/error contracts and
  ResultCheck confinement remain in place. Matching grants still reach the
  owner; empty, malformed, and unrelated grants return -32001.
- Completed workers are already reaped by `communicate()`. Cleanup no longer
  sends SIGKILL to their reusable numeric process-group IDs. Active workers
  retain the group cancellation and reaping path.

The new tests were copied unchanged into a disposable worktree at `18853bf`.
Running the following command there exited 1: two tests, 17 failing checks.
The auth test received a lane response instead of a scope refusal for all four
research/ResultCheck rows; the worker test observed `killpg` after completion.
Both tests pass with the fix, including successful and refused worker results.

```sh
python -m unittest -q \
  sentilab_core.test_conformance.ExecutionConformance.test_pending_conformance_surfaces_cannot_bypass_empty_or_invalid_grants \
  sentilab_core.test_execution
```

Validation in the Python 3.12 virtual environment, all commands below exit 0:

| Command | Observed result |
|---|---|
| `.venv/bin/python -m unittest -q sentilab_core.test_conformance sentilab_core.test_execution sentilab_core.test_gb10_backend` | 52 tests pass, including real CLI SIGINT/MCP cancellation and worker reaping |
| `.venv/bin/python -m unittest -q sentilab_core.test_mcp_stdio sentilab_core.test_dataset_mcp sentilab_core.test_cleanup sentilab_core.test_memory_transports sentilab_core.test_research_transports sentilab_core.test_resultcheck sentilab_core.test_resultcheck_boundary sentilab_core.test_resultcheck_io sentilab_core.test_resultcheck_platform sentilab_core.test_research` | 71 tests pass |
| `.venv/bin/python -m unittest -q sentilab_core.test_dataset sentilab_core.test_ledger sentilab_core.test_history sentilab_core.test_environment sentilab_core.test_signing sentilab_core.test_budget sentilab_core.test_gate sentilab_core.test_labs` | 73 tests pass |
| `(cd sundai_controller && ../.venv/bin/python -m unittest -q test_controller.py test_experiment.py)` | 55 tests pass |
| `.venv/bin/python -m unittest -q sentilab_core.test_build_info sentilab_core.memory_conformance sentilab_core.conformance.CanonicalConformance` | 9 tests pass |
| `PATH="$PWD/.venv/bin:$PATH" node --test web/test/*.test.mjs scripts/deck-data.test.mjs` | 303 tests pass; the deck's 12 tests also pass alone |
| `(cd contracts && sha256sum -c HASHES.txt)` | All hashes match |
| `node run-vectors.mjs` in `contracts/contract-0.2` and `contract-0.3` | 74 and 83 checks pass |
| `node run-view-vectors.mjs` in `contracts/view-envelope` and `view-envelope-v0.5` | 113 and 193 checks pass |
| `node run-paging-vectors.mjs` in `contracts/view-envelope-v0.6` and `view-envelope-v0.6.1` | 174 and 222 checks pass |
| `node web/test/make-sentilab-demo.mjs --check` | 44 envelopes are current |
| `.venv/bin/python -m compileall -q sentilab_core sentilab_cli sentilab_mcp scripts/record_build_info.py` | Pass |
| `.venv/bin/pip check` | No broken requirements |
| `make -C sundai_hotspot -j4 SUPERLU=1` | Build passes; binary not executed |
| `git diff --check` | Pass |

These are CPU fixture/recorded checks, with no model or device calls and no real
solver execution. Docker is unavailable; the full container/thermal/solver
gates remain unrun under the zero-solves constraint. No npm manifest or
TypeScript configuration exists, and no dummy gates were introduced. This
evidence is not an all-gates-green, published-head, or merge claim. The broader
pending capability and mid-call STOP work remains visible in COVERAGE.md.
