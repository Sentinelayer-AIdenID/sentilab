# Validation receipts

Implementation source starts at PR #15 dependency
`de3fa41c9fe45dd958bc2e06418d993027807448`; the operator carries only this ticket's
later commits. Executed by a surrogate executor under recorded model substitution.

| Command | Observed result |
| --- | --- |
| `python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt` | exit 0 |
| `.venv/bin/python -m unittest -q sentilab_core.test_dataset` | 13 tests, exit 0 |
| `(cd sundai_controller && ../.venv/bin/python -m unittest -v test_controller.py test_experiment.py)` | 55 tests, exit 0 |
| `.venv/bin/python -m unittest discover -s sundai_thermal -p 'test_*.py'` | 2 tests, exit 0 |
| `sudo apt-get install -y build-essential libsuperlu-dev libblas-dev` then `make -C sundai_hotspot -j4 SUPERLU=1` | exit 0, build only |
| `.venv/bin/python -m unittest -q sentilab_core.test_ledger sentilab_core.test_gate sentilab_core.test_budget sentilab_core.test_environment sentilab_core.test_signing` | 33 tests, exit 0 |
| `PATH="$PWD/.venv/bin:$PATH" node --test web/test/*.test.mjs` | 103 tests, exit 0 |
| `(cd contracts && sha256sum -c HASHES.txt)` | exit 0 |
| `(cd contracts && node contract-0.2/run-vectors.mjs)` | 74 checks, exit 0 |
| `(cd contracts && node view-envelope/run-view-vectors.mjs)` | 113 checks, exit 0 |
| `(cd contracts && node view-envelope-v0.5/run-view-vectors.mjs)` | 193 checks, exit 0 |
| `.venv/bin/python -m compileall -q sentilab_core/dataset.py sentilab_cli sentilab_mcp` | exit 0 |
| `git diff --check` | exit 0 |

The repository has no npm/TypeScript manifest or lint configuration; no synthetic
manifest was added to make framework commands exist. The ticket's Python and C
build gates above apply. No new dependency was introduced. Docker and the full
`sentilab_core` discovery suite were not run: oracle/conductor tests execute
solver workloads outside this ticket's fixture-only scope. The explicitly named
thermal regression gate runs the repository's synthetic search. No HotSpot solve
or LLM evaluation was performed for this ticket.

The new test file fails on the dependency without dataset.py with
`ModuleNotFoundError: No module named 'sentilab_core.dataset'`. This was checked
in a separate detached worktree; the working checkout was never stashed/reverted.
The same failure was reproduced on the original snapshot base
`a84691364fd04e7538b6624af37e77847144c0f9` in a second detached worktree.
`mutation-results.json` records targeted changes to the shipped exporter in that
isolated worktree: all 12 mutations exited nonzero, with the original source
restored after the experiment. These are self-check receipts, not independent
review or proof of deployment.
