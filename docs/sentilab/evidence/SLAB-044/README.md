# SLAB-044: isolated lead and advisory judge infrastructure

This slice runs **deterministic stand-ins only**. It does not admit a provider,
make a paid call, establish headroom, or release a frozen scientific experiment.
The existing AI-off labels and deterministic AcceptanceGate remain unchanged.

## What runs

`sentilab_core.leads` defines `LeadAdapter.propose(LayoutContext)` and
`JudgeAdapter.review(candidate, evidence)`. `IsolatedLabs` projects immutable
JSON inputs, applies admission and metering, validates the existing lab wire
schemas, and records invocation provenance. Each proposal records originator,
family, model ID/version, prompt hash, context hash, configuration hash and the
nonsecret experimental seed. Judges additionally pin the rubric hash. Prompt
text, stand-in version/settings, memory policy, timeout, call limit and readiness
are included in the immutable conductor configuration.

Configure `Conductor(..., isolated_labs=IsolatedLabs(...))` with one
`LabAdapters` entry for each of `openai`, `claude`, `grok`, and `kimi`, a
`StandInAdmission`, and an injected fixture oracle. Family names are namespaces,
not claims that those providers have run. Exact built-in stand-in types are
required. Native oracles, provider adapters and stand-in subclasses are refused.
The existing ReplayLab hook remains separate and unchanged.

Lead inputs contain only the pinned initial layout and the last four candidates
from that lab with their associated measurement records. The namespace includes
run, arm, task family, experimental seed and lab. The conductor reconstructs the
input from the current run's verified ledger; it passes no global board, foreign
candidate, shared summary, review transcript, signer or oracle to a lead. New
runs start with empty trajectory memory. A stateless judge receives only the
target candidate and that candidate's evaluation/reproduction evidence. Its
structured concern/no-concern/abstain result becomes a signed source record,
never a gate argument or lifecycle transition. These fixture judges are not
independent scientific-family votes.

Call reservations are signed before admission or adapter invocation. The
SLAB-003 seam is `check(model_id) -> AdmissionRecord` or `NotAdmitted`, followed
by `meter(model_id, usd)` or `OverCap` before execution. The stub admits only two
version-1 stand-in identities, rejects nonzero/invalid charges, and records every
zero-dollar charge. Call counts and timeout reservations bound attempts. A
verified prior reservation prevents another invocation after restart. Missing
proposals consume an inconclusive candidate slot without a baseline substitute
or a thermal evaluation. Failed judges record missing advisory evidence and
leave the deterministic gate unchanged. There is no automatic retry or refund.

## What waits

The loaded source snapshot has no SLAB-003 admission implementation or SLAB-041
freeze/memory module. `AdmissionRecord`, the injected check/meter protocol, and
`Readiness` are explicit integration stubs. `Readiness` defaults to HOLD/unfrozen;
the fixture missing-data policy is `record_missing_no_retry`. This is a pinned
fixture policy, not a claim that SLAB-041 approved it. The future authoritative
freeze adapter must supply/validate that policy, and fail closed for unsupported
policies. Real adapters first require admission, SLAB-039 headroom PASS and
SLAB-041 frozen, and remain disabled even if these stub fields are green. A
separate integration must supply trusted admission/freeze records, actual usage
accounting, provider process isolation and transports. No credential is accepted
by this module and no production/CLI enablement flag was added.

## Reproduce

```sh
python -m unittest -q sentilab_core.test_leads sentilab_core.test_lead_conductor
python -m unittest discover -s sentilab_core -p 'test_*.py'
```

The new files are picked up by the existing container smoke test discovery.
The four-lab proof drives the shipped conductor, signed ledger, evidence
validation and gate for two rounds, with socket creation forbidden. The injected
synthetic plate oracle performs 18 regression-only evaluations/reproductions;
model spend is zero. Additional cases compare all three judge verdicts against
identical gate outcomes, test isolation/memory reset, failure accounting,
interrupted reservations, pin changes, admission refusal and spend caps.

## Execution status

Actual local checks on 2026-10-31:

| Command | Result |
| --- | --- |
| `python3 -m compileall -q` on the four changed Python files | PASS |
| `git diff --check` | PASS |
| `python3.12 -m venv .venv` | PASS |
| `.venv/bin/pip install --no-index -r requirements.txt` | FAIL: no offline numpy 2.3.5 distribution |
| Controller `python -m unittest -v test_controller.py test_experiment.py` | BLOCKED: two import errors, missing cryptography |
| `python -m unittest discover -s sundai_thermal -p 'test_*.py'` | BLOCKED: missing numpy |
| `python -m unittest -q sentilab_core.test_leads sentilab_core.test_lead_conductor` | BLOCKED: two import errors, missing cryptography |
| `make -j4 SUPERLU=1` in sundai_hotspot | FAIL: missing slu_ddefs.h |

Import errors are not executed/passing regression tests. The initial new-test
run failed because `sentilab_core.leads` did not exist; behavior-level mutation
proof remains pending dependencies. No thermal solves or model calls ran.
The repository has no npm package manifest; its Python/native gates supersede
the generic npm template. No manifest was added to manufacture a gate.

The operator has been asked to provide offline Python/native packages or clarify
the ticket's no-network/no-solves restriction for the named regression gates.
The installed `senti` wrapper also lacks the underlying executable for say,
review and PR verbs; room updates use the working `respawn-life say` bridge.
No all-green, independent-proof or PR-publication claim is made.
