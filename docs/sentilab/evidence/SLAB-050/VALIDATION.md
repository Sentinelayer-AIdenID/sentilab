# SLAB-050 validation

Base: `3e7c480` (`main-v5`). All new evaluation tests use fake oracles/processes.
No thermal solves were run. Real phase measurement remains pending a separate
profiling grant; this is code/test proof, not a measured thermal study.

## Passing gates

```sh
OPENBLAS_NUM_THREADS=1 .venv/bin/python -m unittest -q \
  sundai_controller.test_evidence_profile sundai_controller.test_headroom \
  sundai_controller.test_headroom_caps sundai_controller.test_headroom_v4 \
  sundai_controller.test_headroom_supervisor sundai_controller.test_headroom_identity \
  sundai_controller.test_headroom_policy sundai_controller.test_headroom_evidence \
  sundai_controller.test_headroom_adapter_evidence sundai_controller.test_headroom_worker_evidence
```

184 tests passed (489.298 seconds). The final focused profile/evidence/identity/
policy suites also passed: 61 tests. Initial broad runs exposed two synthetic
harness compatibility issues; both were fixed, and the full gate above reran
successfully. Existing policy-byte and 24-call runtime-cap tests isolate the new
forecast prerequisite while retaining their original assertions. Separate new
integration tests exercise missing, fitting and depleted-capacity admission.

```sh
. .venv/bin/activate
node --test web/test/*.test.mjs scripts/deck-data.test.mjs
make -C sundai_hotspot -j2 SUPERLU=1
.venv/bin/python -m compileall -q sundai_controller sundai_hotspot/tap_oracle.py sundai_hotspot/tap_oracle_worker.py
.venv/bin/python -m pip check
git diff --check
```

345 web/deck tests passed. Build, compilation, dependency consistency and
whitespace checks exited 0. The initial web command used system Python and
failed on missing cryptography; activating the repository venv fixed that
execution environment. No dependency or lockfile changes were required.

There is no npm/TypeScript manifest, so no manifest was invented for generic npm
gates. The full container smoke was not run: it executes real thermal solves,
which were forbidden without a grant.

## Baseline proof

Disposable worktrees at main-v5 retained the old implementation:

- All six new worker-retention tests fail on the base.
- All five new adapter-retention tests fail on the base.
- Runner/supervisor integration tests, supplied with the new helper fixtures but
  old headroom/supervisor code: 12 tests, 11 failures/errors and one unchanged
  historical-capacity control passes.
- The new profile module is absent on the base, so its new test module fails to
  import there; with the implementation, all 24 profile tests pass.

Raw logs and exact commands are retained outside the repository in
`/workspace/slab050-proof` for operator carry. Historical SLAB-039 evidence has
no changes. Independent arithmetic/retention review and the profiling grant
remain operator/reviewer actions.
