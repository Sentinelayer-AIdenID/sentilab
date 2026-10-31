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
