# PR23 main integration — 2026-10-31

The supplied main bundle contains `refs/remotes/origin/main`, not `main`.
Fetched that advertised ref into `refs/remotes/main-now/main` and merged
`d031c8d25fb581f2355fc632fc8c384ba45cf973` into local reviewed carry
`215b252d709b5da209100167e0b89bc48ed913f6`.
The operator reported published PR23 head `1168907d`; that object is not in this
checkout, so this report identifies the local carry separately.

Resolved the three conflicts in `sentilab_cli/__main__.py`,
`sentilab_mcp/__init__.py` and `sentilab_mcp/__main__.py`. CLI live
run/status/stop/verify, memory recall/audit, route and dataset export survive.
MCP advertises all eight corresponding tools, with their individual schemas.
Retained shared operation dispatch, authority checks, STOP handling, bounded
concurrent requests, export-worker cancellation/reaping and error translation.
AST comparisons confirmed that every import and function from both parents
remains; reviewed all call sites and their global names as well.

The new real-stdio regression
`StdioTests.test_tool_listing_keeps_live_memory_routing_and_dataset_schemas`
requires all eight tools exactly once and checks their required fields. It fails
in separate disposable worktrees on both unmerged parents:

- `215b252`: `First has 0, Second has 1: 'sentilab_dataset_export'`.
- `d031c8d`: missing `sentilab_memory_recall`, `sentilab_memory_audit`,
  and `sentilab_route`.

It passes on the merged source. Existing process tests also exercise actual
dataset export with a policy file, memory recall/audit, routing, live operations,
STOP while an export is locked, cancellation, disconnect and timeout cleanup.

## Fresh validation

Python 3.12.3 and Node v22.23.3. Installed the merged pinned requirements with
`.venv/bin/python -m pip install -r requirements.txt -r requirements-service.txt`.
After `. .venv/bin/activate`, the following commands exited 0:

| Command | Observed result |
| --- | --- |
| `OPENBLAS_CORETYPE=Haswell OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 bash scripts/container_smoke.sh` | 279 tests across 32 unittest commands, 32 OK summaries, zero failures/skips; eight HotSpot probes; deterministic demo and both TFL05 checks pass |
| `python -m unittest -q sentilab_core.test_mcp_stdio sentilab_core.test_dataset_mcp sentilab_core.test_memory_transports sentilab_core.test_transports` | 15 tests, zero failures/skips; includes five MCP stdio and three dataset stdio tests |
| `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m unittest -q sentilab_core.conformance sentilab_core.memory_conformance` | 15 test executions, zero failures/skips (includes the separately invoked memory parity suite) |
| `node --test web/test/*.test.mjs` | 103 tests pass, zero failures/skips |
| `(cd contracts && sha256sum -c HASHES.txt)` | 22 reviewed files match |
| `(cd contracts/contract-0.2 && node run-vectors.mjs)` | 74 checks pass |
| `(cd contracts/contract-0.3 && node run-vectors.mjs)` | 83 checks pass |
| `(cd contracts/view-envelope && node run-view-vectors.mjs)` | 113 checks pass |
| `(cd contracts/view-envelope-v0.5 && node run-view-vectors.mjs)` | 193 checks pass |
| `node web/test/make-sentilab-demo.mjs --check` | Existing 44-envelope fixture is current |
| `python -m pip check` | No broken requirements |
| `python -m compileall -q sentilab_cli sentilab_mcp sentilab_core` | Pass |
| `git diff --check` and `git diff --cached --check` | Pass |

Counts are the actual unittest executions, summed as CI invokes the modules;
the separately reported transport tests are also included in the smoke total.
The smoke used the existing `/app` symlink to this checkout and the built
HotSpot/SuperLU binary. Its generated demo output changes were restored before
commit. The 32-grid probe median was 0.497 seconds, above the script's reported
0.400-second deployed-host target but below its enforced 2-second SuperLU gate.

This was the complete smoke script on the host, not a Docker image build.
Docker image health/origin-lock checks and full-history gitleaks were not run
here (Docker/gitleaks unavailable). Operator export verification, CI and
independent review remain external. No remote push or new PR request.
The existing workflow addition for Node-enabled memory parity remains, with
main's contract-0.3 runner; workflow review remains elevated under SWE Excellence
Framework sections F.2/O.1.
