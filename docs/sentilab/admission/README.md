# Model admission (SLAB-003)

The shipped `registry.json` is empty. Lead/judge model calls through the lab
boundary are refused until Carter's reviewed decisions are entered. A successful
probe alone never admits a model.
This is a human credential/entitlement control, not the superseded per-step
planning approval gate. No provider credentials or live provider adapter ship
with this change; the conductor remains AI-off and accepts exact replay labs only.
The legacy Jev intake router is a separate, existing signal-routing path, not a
scientific lead or judge; its configuration is outside this change.

## Human decisions still required

Warden must obtain and record Carter's Claude entitlement for boxes, payer,
USD caps for each arm and run, and allowed lead/judge model IDs and pinned
versions. Record the entitlement **name only**, never its value. Provisioning
and enabling credentials happen outside this registry, through human controls.

The standing fourth-lab fallback is `deepseek-v4-pro` if Claude entitlement is
absent on 2026-10-31 at 15:00 UTC. This scheduling decision is not admission:
the fallback also needs its own complete record. No automatic admission,
provider selection, price estimate or entitlement grant is implemented.

## Registry contract

`MODEL-ADMISSION.schema.json` defines the registry and probe evidence. A record
binds provider/model/version, allowed roles, run and arm, payer, prices per
million input/output tokens, arm/run USD caps, entitlement source, approval
reference, approver (`Carter`), approval/expiry timestamps and successful
model-list evidence. Monetary strings use exact nonnegative decimal USD (up to
six fractional digits); unknown properties, missing fields and ambiguous records
are refused. The probe provider/entitlement/model must match. Its capture must
precede approval, and approval must be current and unexpired.

All records in a run agree on payer/run cap; all records in an arm agree on its
cap. Caps aggregate across models and roles. The checker rereads the registry
on every check/reservation, so removal revokes admission. An invalid record
fails the entire registry closed. Registry files and accounting storage are
trusted, service-owned inputs: labs cannot write them. The `approver` field is
an audit assertion in a human-reviewed artifact, not proof of human identity or
a signature. There is no endpoint for labs to submit or approve these records.

## Runtime integration

The agreed interface is `admission.check(model_id) -> AdmissionRecord`, raising
`NotAdmitted`, and `admission.meter(model_id, usd)`, raising `OverCap` for invalid
amounts, exhausted caps or corrupt accounting (and `NotAdmitted` for missing
admission). Bind the module interface in trusted service code:

```python
from sentilab_core import admission

gate = admission.Admission(
    run_id="human-approved-run", arm_id="human-approved-arm",
    spend_path="/durable/service/model-spend.json",
)
with admission.bind(gate):
    record = admission.check("human-approved-model")
    admission.meter(record.model_id, record.ceiling_usd(1000, 500))
```

No context defaults to refusal. These example identifiers are not admissions.
All processes and arms of a run must use the **same durable spend path**. The
service may create an empty ledger for its first allocation only; never delete,
replace or relocate it to restart a run. Accounting locks and atomic fsynced
writes protect concurrent reservations. Restarting against existing storage
retains every charge; corrupt state refuses calls. Storage integrity and
ownership are service deployment responsibilities, as for the existing budget.

Use `sentilab_core.model_calls.AdmittedLab` for live propose (lead), review
(judge), and repair (lead). It checks the configured provider/version and role,
then reserves the entire input/output token ceiling at the admitted prices
before invoking its transport. A changed quote is refused. Reservations remain
charged on failure, timeout or cancellation. `Dispatcher` accepts only exact
`ReplayLab` (no model I/O) or `AdmittedLab` instances and reports
`model_not_admitted` / `model_cost_cap` refusals.

A future **trusted service transport** must implement the pinned route, total
input/output ceilings including prompt/tool overhead, no hidden billable costs,
and at most one provider request (no automatic retries). The transport receives
an immutable `ModelCall` with the admitted record, operation, JSON request and
ceilings. This is an integration contract, not a sandbox for arbitrary Python.
No production transport, service enablement, paid request or model probe has
been added. Provider-specific enforcement must be reviewed before connecting a
transport; the existing conductor's live-model prohibition remains in place.

## Zero-inference evidence recorder

`python -m sentilab_core.probe --provider NAME --entitlement-source NAME
--output PATH` reads at most 1 MiB of JSON from stdin. Pipe only the output of an
**existing configured CLI** whose auth/model-list action is confirmed free;
never use a completion to check a credential. No such CLI is run by the recorder.

The normalized input contract is `{"status_code":200,"data":[{"id":"model-id"}]}`.
This is a local recorder format, not a claim about any provider's API. Adapt an
existing CLI's stdout in memory if necessary; never save raw output. Explicit
failed HTTP status codes can be recorded with an empty list. The recorder writes
only provider, entitlement-source name, capture time, status code and model IDs;
it drops headers, error text and extra response fields and rejects malformed or
credential-like names. No raw diagnostics are echoed on failure. Inspect every
artifact before committing; no recorder can establish that an arbitrary name
chosen by a caller is non-secret. Failed/empty evidence cannot satisfy admission.

## Local proof (no model or native solver calls)

```
python -m unittest -q sentilab_core.test_admission sentilab_core.test_model_calls sentilab_core.test_probe sentilab_core.test_labs
```

The real adapter is driven by in-memory transport fixtures. Tests prove refusal
before transport, role/route binding, pre-call pricing, shared caps, concurrent
reservations, restart persistence, quote changes, and retained charges after
failure/cancellation. The CLI tests launch the shipped recorder as a subprocess.
