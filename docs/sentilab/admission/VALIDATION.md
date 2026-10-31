# SLAB-003 local validation — 2026-10-31

Executor: surrogate executor under recorded model substitution. These are local
worker observations, not independent review or Carter's model admissions.

Base: `3d9fe55f6260e186defa2900557b007896399649`, a loaded snapshot of source
`d031c8d25fb581f2355fc632fc8c384ba45cf973`. Implementation commits:
`377e665` and `b85f94b`; subsequent evidence edits do not alter runtime code.

## Gates actually run

- `python3.12 -m venv .venv`: exit 0.
- `.venv/bin/pip install -r requirements.txt -r requirements-service.txt`: exit 0.
- `sudo apt-get update` and `sudo apt-get install -y build-essential libsuperlu-dev libblas-dev`: exit 0.
- `(cd sundai_controller && ../.venv/bin/python -m unittest -v test_controller.py test_experiment.py)`: 55 tests, exit 0.
- `.venv/bin/python -m unittest discover -s sundai_thermal -p 'test_*.py'`: 2 tests, exit 0.
- `make -C sundai_hotspot -j4 SUPERLU=1`: exit 0; built, not executed.
- `.venv/bin/python -m unittest -q sentilab_core.test_admission sentilab_core.test_model_calls sentilab_core.test_probe sentilab_core.test_labs`: 34 tests, exit 0.
- `.venv/bin/python -m unittest -q sentilab_core.test_lab_conductor`: 4 tests, exit 0; synthetic CPU oracle only.
- `.venv/bin/python -m compileall -q sentilab_core/admission.py sentilab_core/model_calls.py sentilab_core/probe.py`: exit 0.
- `.venv/bin/pip check` and `git diff --check`: exit 0.

Total: 95 tests. No paid model call, entitlement probe or native HotSpot solve
was run. A full container smoke was not run because it executes native solves;
the ticket's named Python/build gates were used. No package.json or TypeScript
project exists here; npm/typecheck/lint/build/audit commands are inapplicable.
No dependency vulnerability audit is claimed by `pip check`.

## Failure proof

Copied the three new test files into a separate worktree at the base and ran
the real unittest modules with the installed environment: exit 1, two missing
admission/module import errors and two probe CLI failures. No stash or changes
to the working implementation were used.

Separately restored the committed implementation between each mutation in an
isolated worktree. Each row below produced a nonzero unittest exit; all 17
mutations were caught. Tests call the shipping functions/CLI, with in-memory
transport fixtures; admission, pricing and accounting are not mocked.

| Reintroduced defect | Test method (module prefix omitted) |
| --- | --- |
| Permit unbound interface | AdmissionTests.test_empty_default_and_unbound_interface_refuse |
| Omit input price | AdmissionTests.test_complete_record_and_scoped_interface |
| Remove JSON schema validation | AdmissionTests.test_incomplete_malformed_and_unproven_records_refuse |
| Match model without run/arm | AdmissionTests.test_scope_conflicts_duplicates_and_revocation_refuse |
| Accept changed quote | AdmissionTests.test_changed_quote_is_refused_before_reservation |
| Remove arm cap | AdmissionTests.test_arm_and_run_caps_aggregate_across_models_and_restart |
| Remove run cap | AdmissionTests.test_arm_and_run_caps_aggregate_across_models_and_restart |
| Drop reservation persistence | AdmissionTests.test_invalid_spend_and_corrupt_ledger_never_refund |
| Allow concurrent cap overrun | AdmissionTests.test_concurrent_reservations_cannot_overspend |
| Call transport without admission | ModelCallTests.test_unadmitted_lead_judge_and_repair_refuse_before_transport |
| Ignore model role | ModelCallTests.test_role_provider_version_and_input_ceiling_refuse |
| Omit pre-transport reservation | ModelCallTests.test_all_roles_reserve_priced_ceiling_before_transport |
| Leave failed/cancelled calls uncharged | ModelCallTests.test_over_cap_and_failure_or_cancellation_never_refund |
| Dispatch unguarded adapters | ModelCallTests.test_dispatch_refuses_unguarded_adapters_and_replay_subclasses |
| Lose cost refusal classification | ModelCallTests.test_dispatch_uses_guard_and_preserves_specific_refusal |
| Save raw probe response | ProbeRecorderTests.test_cli_projects_only_nonsecret_evidence |
| Accept malformed probe input | ProbeRecorderTests.test_failure_status_is_evidence_and_malformed_input_never_overwrites |

Carter's actual credentials, entitlement, payer/caps and model list remain
unresolved. Production transport enforcement and enabling live labs are outside
this patch. The fourth-lab fallback does not bypass admission. Warden's independent
refusal/cap proof and human review remain required before release.

## Review 56432: reservation/publication race

Merged supplied main `60ddc5517397226dbd21e45b4de42c13ef29f867` before fixing
the race. The supplied bundle advertised `refs/remotes/origin/main`, not `main`.
The loaded snapshot and upstream `d031c8d` had identical trees (`git diff
--exit-code` passed), so a history-only merge connected them before the normal
main merge. Pre-fix merged HEAD: `9da0a743269dfb816b39e5e51f41c761b0603b4f`.

Fresh registry validation and quote equality now run after both spend and
registry locks are acquired. Registry publication holds the same registry lock
through atomic replacement; reservations hold it through durable commit. The
complete canonical policy hash is recorded in each new reservation. The README
defines publication ordering and the treatment of already committed/in-flight
requests, including retained charges.

### Gates actually run for this revision

All commands below exited 0. The environment already contained the pinned Python
3.12 dependencies and native build prerequisites from the initial validation.

- `make -C sundai_hotspot -j4 SUPERLU=1`.
- With `/app` linked to this checkout: `PATH="/workspace/sentilab/.venv/bin:$PATH" OPENBLAS_CORETYPE=Haswell OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 bash scripts/container_smoke.sh`: **293 tests in 33 unittest invocations**, all passing, plus demo checks, both benchmark smokes and **8 native HotSpot probe cases**. The right-shift 32x32 case was 118.8400 C. The 32x32 median was 0.499 s, passing the script's 2 s SuperLU bound; its 0.4 s deployed-host target is reported, not enforced on this box.
- `PATH="/workspace/sentilab/.venv/bin:$PATH" node --test web/test/*.test.mjs`: **207 passed**, zero failures/skips.
- `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -m unittest -q sentilab_core.conformance`: **9 passed**.
- `(cd contracts && sha256sum -c HASHES.txt)`.
- `node run-vectors.mjs` in `contracts/contract-0.2` and `contracts/contract-0.3`: **74 and 83 checks**.
- `node run-view-vectors.mjs` in `contracts/view-envelope` and `contracts/view-envelope-v0.5`: **113 and 193 checks**.
- `(cd contracts/view-envelope-v0.6 && node run-paging-vectors.mjs)`: **174 checks**.
- `node web/test/make-sentilab-demo.mjs --check`: **44 envelopes**, current.
- `.venv/bin/python -m compileall -q sentilab_core/admission.py`, `.venv/bin/pip check`, and `git diff --check`.

The smoke includes all **23 admission/model-call tests** (nine added in this
revision). Its generated controller demo artifacts were restored afterward;
they are not part of the patch. The latest reviewer request explicitly required
the full smoke, so this revision did execute native solves, unlike the initial
validation above. No paid model calls, entitlement provisioning or provider
probes were performed. This is a direct smoke-script run, not a Docker build.

### Regression and mutation proof

Copied the new tests into a separate worktree at the pre-fix merged HEAD. Each
required real contended-flock regression (revocation, expiry, quote change)
failed: expected zero reservations/transport calls, observed **one reservation,
USD 0.002, one transport call**. All three pass with the fix. The judge policy
test also failed for role, route, payer, caps and entitlement changes. The expiry
during accounting test failed with `NotAdmitted not raised`. The remaining four
new publication/policy tests failed on absent publication API/policy hash.

In that isolated worktree, separately reintroduced five defects into the fixed
implementation. Every targeted test exited 1: removing the reservation's
registry lock; removing the publisher's lock; ignoring quote changes; omitting
the reservation policy hash; omitting the final expiry check. The first two
failed the assertion that publication must contend on the real flock. No mocks
replace admission or accounting decisions; transport is an in-memory fixture,
the clock is controlled for expiry, and lock spies still invoke real `flock`.

This is local worker proof; operator export verification and independent review
of the carried HEAD remain required. The shipped registry remains empty.
