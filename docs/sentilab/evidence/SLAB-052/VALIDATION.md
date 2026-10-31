# SLAB-052 validation receipt

Base: `3e7c4807bf2fbcf5fcde2c12659e8f35fef69f46` (`main-v5`).
Python 3.12.3, Node v22.23.3. These are worker-run checks, not independent review.
No model calls, thermal solves, device access or exploratory labs were run.

Run from the repository root with the existing virtualenv:

```sh
. .venv/bin/activate
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
```

| Command | Observed result |
| --- | --- |
| CPU-only core selection below | 352 tests, pass; 0 skipped within the selection |
| `python -m unittest -q sentilab_core.test_proposals` | 20 tests, pass (included in the 352) |
| `python -m unittest -q sentilab_core.conformance sentilab_core.memory_conformance` | 35 tests, pass |
| `python -m sentilab_core.test_resultcheck --parity` | 9 tests, pass |
| `node --test web/test/*.test.mjs` | 333 tests, pass; 0 skipped |
| `python -m sentilab_core.capabilities --check docs/sentilab/evidence/SLAB-043/COVERAGE.md` | exit 0 |
| `python -m compileall -q sentilab_core sentilab_cli sentilab_mcp` | exit 0 |
| `pip check` | no broken requirements, exit 0 |
| `git diff --check` | exit 0 |

The CPU-only core selection is reproduced below. It deliberately excludes the
single real HotSpot reproduction test, rather than relabeling a solver run as
harness testing. The full container smoke also includes solves and was not run.
Those gates remain for the authorized operator; this receipt does not claim full
container CI passed. No npm manifest or TypeScript project exists in this repo,
so the generic npm/tsc commands are not applicable and none was fabricated.

```sh
python - <<'PY'
import sys
import unittest
suite = unittest.defaultTestLoader.discover('sentilab_core', pattern='test_*.py', top_level_dir='.')
def cases(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from cases(test)
        else:
            yield test
selected, removed = [], []
for test in cases(suite):
    if test.id().endswith('.test_real_fresh_process_reproduction_is_bound_and_metered'):
        removed.append(test.id())
    else:
        selected.append(test)
assert removed == ['sentilab_core.test_oracle.FreshOracleTests.test_real_fresh_process_reproduction_is_bound_and_metered']
print('Not run under no-solves instruction:', removed[0])
print('Selected', len(selected), 'CPU-only core tests')
result = unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite(selected))
sys.exit(not result.wasSuccessful())
PY
```

Regression sensitivity was checked in a disposable worktree, without reverting
or stashing the working checkout. The new test module on the untouched base
fails with `ModuleNotFoundError: No module named 'sentilab_core.proposals'`.
Then the working source was copied to that worktree and nine individual mutations
were applied and restored. Each selected test failed (exit 1). [MUTATIONS.json](MUTATIONS.json)
lists the test/mutation pairs: budget, cross-lab filtering, reservation-before-oracle,
late STOP, lead admission, operator-tool access, grant expiry, total-slot bound and
fresh/replayed byte serialization. Positive proposal tests pass with the guards.

Initial runs exposed a fresh/replayed dictionary-order mismatch, two legacy MCP
expected-tool lists needing the new entries, and a browser command launched without
the virtualenv on PATH (its Python fixture imports could not find cryptography).
The receipt above records the corrected commands/results; no existing assertion
or solver test was deleted or weakened.

Remaining: root's independent budget/isolation review, operator export/publication,
the real SLAB-048/051 adapter/evidence, admission and prospective run grant, and the
later descriptive lab/SA/human run report. Synthetic arithmetic scores are not
performance evidence.
