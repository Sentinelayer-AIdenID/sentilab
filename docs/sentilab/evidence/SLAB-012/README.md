# SLAB-012: offline research interface

Research request/status/export now use one bounded core implementation from both
CLI and MCP. The only shipped backend is `FixtureBackend`, an offline synthetic
answer set selected by the request hash. Its underlying model is explicitly
`none:deterministic-fixture`; its citations identify the fixture, not real
literature. It makes no model calls, network requests or solver calls.

## Calling the interface

The host pins one exact run/arm/family/seed/lab scope. There is no default scope.
The CLI reads the pin from `SENTILAB_RESEARCH_NAMESPACE`; embedded hosts set
`Context.options['research_namespace']`. MCP tool arguments cannot set that pin,
select a backend, supply an admission record, claim a role or grant acceptance.
Run separate hosts/OS access boundaries for separate principals. A user who can
change the host environment or storage already controls this local service;
namespace matching is not a replacement for remote authentication.

```sh
export SENTILAB_LIVE_DIR=/tmp/research-example
export SENTILAB_RESEARCH_NAMESPACE='{"run_id":"example","arm":"baseline","family":"thermal","seed":7,"lab":"lab-a"}'
python -m sentilab_cli research request --ai-off \
  --namespace "$SENTILAB_RESEARCH_NAMESPACE" --question 'Document a reproduction method'
# Use the returned request_id for these two commands:
python -m sentilab_cli research status --ai-off \
  --namespace "$SENTILAB_RESEARCH_NAMESPACE" --request-id REQUEST_ID
python -m sentilab_cli research export --ai-off \
  --namespace "$SENTILAB_RESEARCH_NAMESPACE" --request-id REQUEST_ID
python -m sentilab_mcp
```

MCP advertises `sentilab_research_request`, `sentilab_research_status` and
`sentilab_research_export`. Their arguments are `ai_off: true`, `namespace` as a
JSON object, and either `question` or `request_id`. The MCP content text is
byte-identical to CLI stdout excluding the CLI's final newline. Errors contain
only `{"ok":false,"error":{"code":"..."}}`; the CLI exits 2 and MCP sets
`isError`. Missing or wrong host scope, AI-on requests and unknown fields refuse
before writing or invoking a backend. This is a real stdio wrapper, independently
exercised as a subprocess in `test_research_transports.py`.

## Evidence and storage boundary

All exports and individual notes have `type: untrusted_source_evidence`, source
citations and host-stamped provenance: full namespace, question hash, request ID,
backend/tool version, actual underlying-model identity and admission hash.
Non-fixture provenance also retains the approver, scope, telemetry setting,
effective off value and evidence hashes. Documentation and data-flow hashes are
references to human-reviewed artifacts, not self-verifying claims of safety.
Citation contents remain untrusted and URLs are never fetched.

Records live in `SENTILAB_LIVE_DIR/research/<namespace-sha256>.jsonl`, separately
from signed accepted-run ledgers. Each row is hash-linked, appended under the
existing nonblocking ledger lock and fsynced. This detects accidental corruption;
it is not authentication against a host/storage owner who can rewrite a chain.
Raw questions and backend exceptions are not written to the journal. Notes may
contain submitted text and remain confidential to their authorized namespace.
No endpoint lists other namespaces. Symlinked research stores/files are refused.

Requests are idempotent by namespace, question hash, backend identity and
admission hash. A request is recorded before backend invocation, followed by a
completed or failed row. An interrupted request remains pending and is never
silently rerun. There is no recovery/resubmission service in this slice. A STOP
file refuses new requests (including retries); status/export remain readable.
Locks return `busy` immediately so a contended store cannot block MCP STOP.

Questions are limited to 8 KiB UTF-8. Structured values have depth, traversal,
item and 32 KiB serialized limits. Responses allow at most 8 notes with 8
citations each. A namespace journal is limited to 512 rows / 4 MiB, reserving
room for the request and terminal record. Full/corrupt stores fail closed; no
automatic deletion or rollover loses audit evidence.

`AcceptanceGate` explicitly refuses the evidence discriminator in evaluation,
reproduction and current-state slots, even with added measurement fields.
Research never writes gate outcomes, accepted lab state or training data.
The existing dataset exporter only reads authenticated run ledgers; a research
journal is not one. There is no promotion API. A future source-review and
separately authorized measurement workflow is required before any downstream
acceptance or training use.

## Admission contract and remaining human work

`ResearchBackend` exposes `tool`, `version`, `underlying_model`, and
`request(request_hash, question) -> list[{text, citations}]`. Only the exact
built-in fixture class is exempt from admission; subclasses and lookalikes are
not. A host may inject a backend and record via `Context.options` keys
`research_backend` and `research_admission`. No remote import or plugin discovery
is implemented. Injected Python code belongs to the trusted host process; this
protocol is not a sandbox or a production runner for untrusted executable code.
Production cancellation/time limits and deployment authorization for a real tool
must be designed in its later integration. Its returned data is untrusted now.

`admit(backend, record)` requires exactly:

- `tool`, `version`, `underlying_model`: matching the backend identity; empty or
  unknown model names refuse.
- `namespace`: the full approved scope, also checked against the request.
- `approver`: a nonempty host-provided approval identity.
- `telemetry_setting`: the documented setting's key in `effective_config`.
- `effective_config`: a bounded JSON object whose named setting equals `"off"`.
- `evidence_hashes`: exactly `effective_config`, `documentation`, `data_flow`,
  each a SHA-256 hex digest. The configuration hash must match the exact config
  serialized with `research.dumps()` (UTF-8); other hashes reference separately
  retained review artifacts.

An on/unknown setting, missing evidence, mismatched config hash, changed identity
or wrong scope refuses before the question reaches the backend. The gate checks
a record, not an `admitted` flag. The record's approver string is not a signature:
the operator is responsible for authenticated approval and immutable retention
of the complete record and referenced evidence outside this interface. A caller
cannot submit a record through CLI/MCP. Before admitting a real tool, a human
must verify its actual model and version, documented controls, effective config,
all external data paths and approval scope. An off flag or valid hash alone does
not prove those controls. No real tool has been selected or admitted here.

## Local proof

See `validation.json` for exact commands, counts and source linkage, and
`mutation-proof.json` for checks against deliberately reintroduced defects.
New tests use the shipping functions and real CLI/MCP subprocesses. Existing
repository CI discovers `sentilab_core/test_*.py` in `scripts/container_smoke.sh`;
no workflow changes are needed. Local proof is not a claim that remote CI or
independent human review has passed. Rollback is reverting this ticket's commits;
archived research journals stay separate from acceptance history.
