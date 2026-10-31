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
proposals consume a cancelled candidate slot with an explicit inconclusive outcome,
without a baseline substitute
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

## Execution evidence

Local execution on 2026-10-31 with Python 3.12.3 and Node 22.23.3:

| Command | Result |
| --- | --- |
| `python3.12 -m venv .venv` and `.venv/bin/pip install -r requirements.txt -r requirements-service.txt` | PASS |
| `python -m compileall -q` on the four changed Python files; `git diff --check` | PASS |
| `(cd sundai_controller && python -m unittest -v test_controller.py test_experiment.py)` | PASS: 55 tests |
| `python -m unittest discover -s sundai_thermal -p 'test_*.py'` | PASS: 2 tests |
| `python -m unittest -q sentilab_core.test_leads sentilab_core.test_lead_conductor` | PASS: 15 tests |
| `make -C sundai_hotspot -j4 SUPERLU=1` | PASS after installing build-essential, libsuperlu-dev, libblas-dev |
| `python -m unittest -q sentilab_core.conformance` | PASS: 9 tests |
| `node --test web/test/*.test.mjs` with the Python environment on PATH | PASS: 103 tests |
| `OPENBLAS_CORETYPE=Haswell bash scripts/container_smoke.sh` | PASS: 259 tests across 30 modules (including all 113 core tests), deterministic demos and 8 HotSpot probes |

The smoke script runs directly because Docker is unavailable in this box. Its
first attempt failed the canonical thermal check because the box used automatic
OpenBLAS dispatch. The passing rerun used the Dockerfile's existing Haswell setting; no
check or threshold was changed. Generated demo artifacts stay in the disposable
checkout. No live experiment or provider call is part of these regression gates.
The repository has no npm package manifest; its Python/native/browser gates
supersede the generic npm template. No manifest was added to manufacture a gate.

Runtime tests exposed two draft defects, now fixed: adapter settings exceeded
the signed envelope nesting cap, and a missing proposal tried an illegal
`proposed -> inconclusive` transition. Settings are flattened; missing proposals
use the existing legal `cancelled` lifecycle and record `outcome: inconclusive`.
The evidence contract, projection and AcceptanceGate were not weakened.

Both new test files fail on `base` (`d7bdaedc08fcf3be1ca802203a092b4cd5123dcf`)
because the adapter module is absent. Behavioral mutation checks at code commit
`002ed50029eaead5130e5702e85de6a24962f12d` independently applied each change below
in a disposable worktree. Every target test returned a failure/error (16/16):

| Deliberate regression | Test that detected it |
| --- | --- |
| Include foreign candidates in lead memory | context isolation/repeatability |
| Bypass admission | denied/over-cap roles |
| Skip metering | admission/meter order |
| Retry a reserved outage | outage/restart reservation |
| Remove the real-adapter readiness block | real-adapter refusal |
| Ignore admitted model version | pin/call-budget enforcement |
| Ignore call budget | pin/call-budget enforcement |
| Trust unvalidated judge output | acceptance/target/identity schema rejection |
| Swallow cancellation | timeout/cancellation/error accounting |
| Report reproduction mismatch as no-concern | stand-in rubric |
| Allow a nonzero charge | zero-spend stub |
| Nest settings too deeply | four-lab live loop |
| Restore illegal missing-data lifecycle | outage without fallback solve |
| Forget persisted reservations | interrupted-call restart |
| Let a judge concern cancel a candidate | identical gate outcomes across verdicts |
| Allow a stand-in subclass through the conductor | provider-subclass refusal |

This is local executor evidence, not independent review. Protected review and
PR publication are pending. Rollback consists of reverting this ticket's commits;
the default AI-off conductor path and ReplayLab route retain their existing API.
