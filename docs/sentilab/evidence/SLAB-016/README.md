# SLAB-016/017 dataset export

The exporter consumes PR #15's authenticated `view-envelope/0.5` ledger through
`ledger.replay()`. It never runs an oracle, simulator, model or new admission.
It refuses an entire run if the signature chain, durable head or core projection
is broken. Public keys must come from the operator's independent trust pins.

## Interface

```sh
python -m sentilab_cli dataset export --run-id RUN_ID --run-id ANOTHER_RUN \
  --output-dir /tmp/dataset-exports --policy policy.json
```

`SENTILAB_LIVE_DIR` and `SENTILAB_VIEW_PUBLIC_KEYS` have the same meaning as for
live verification. The MCP tool is `sentilab_dataset_export`, with `run_ids`
(required array), `output_dir` (optional string) and `policy` (optional object).
Both transports call `sentilab_core.dataset.export()` and return the identical
receipt, including the directory, manifest, file digests and counts. The default
output parent is `LEDGER_ROOT/datasets`; it is not scanned as an input run.

Policy example:

```json
{"heldout_families":["reserved-family"],"rights":{"RUN_ID":{"status":"ok","reason":"operator-confirmed permitted fixture data"}}}
```

The trusted export operator supplies rights grants; the exporter does not decide
licenses or consent. Missing grants are `blocked` with a reason. A proposal's
self-declared rights, opinion, labels or display values never authorize training
or supply verifier labels. Supplying this policy is an operator operation, not a
permission for a lab to invent grants. No real provider data is licensed here.

## Files and append-only semantics

Every export is an immutable, content-addressed snapshot. Its directory name is
the SHA-256 of its canonical manifest. Identical ledger inputs, pins and policy
produce byte-identical files regardless of input run order or output location.
Existing files with different bytes are refused. Files are fsynced and published
as one directory under an export lock; snapshots are never rewritten/deleted.

- `records.jsonl`: exactly one original proposal row per candidate, followed by
  correction snapshots as recorded measurements, lifecycle or validity change.
  For a fixed policy and run, new ledger events only append journal rows. Across
  multiple runs, journals are grouped in sorted run-ID order. Adding an earlier
  run changes that combined ordering but never mutates an earlier snapshot.
- `current.jsonl`: the latest correction folded onto each candidate, in run and
  proposal order. Includes pending proposals, errors, gate inputs/outputs, design,
  binding, measured evaluation/reproduction, J delta, labels and eligibility.
- `rlaif.jsonl`: current eligible strict preference pairs, sorted by stable
  comparison ID. Every side references the exact verifier envelope hash and seq;
  current records also reference proposal and measurement envelopes.
- `manifest.json`: schema, sorted ledger frontiers, exact policy, split rule,
  candidate/journal/pair counts and file hashes. No wall clock or output path.

Corrections have their own `record_id`, `supersedes` and originating envelope
reference. A withdrawal preserves historical acceptance and reproduction while
changing validity and eligibility. Withdrawing a measurement stales dependent
candidates via the core support projection. Retraction appends another correction
and restores eligibility only if the projection and policy permit it. Training
must consume the current manifest/view, not an older eligibility snapshot. This
exporter does not retract already trained weights or claim to unlearn data.

A parent design hash resolves to a candidate only when exactly one earlier
proposal matches. Ambiguous or later matches do not invent a repair identity.
An accepted child of a recorded failed/rejected parent gets a verifier-confirmed
repair label with simulator scope; mere proposal text never gets that label.

## Splits and preference rule

`sha256(canonical(["family-split/1", family])) mod 10 == 0` selects dev;
otherwise train. Explicit held-out families override that rule. All seeds and
variants of a family remain together, including across runs. The public
experimental seed is still part of the comparison context; it is not a signing
secret. This is a versioned fixture split rule, not authorization to open or tune
a held-out scientific benchmark.

Only eligible accepted candidates can be preferred. A verifier's hard constraint
rejection can be the negative example. Valid non-improving/within-margin results
are comparable only with the same recorded incumbent, family, seed, run, binding
context and run configuration, and a difference in recorded J improvements
strictly exceeding the recorded margin. A within-margin outcome alone is not a
negative preference. Ties, pending, cancelled, failed, missing reproduction and
unorderable contexts abstain. Failure rows remain available as raw examples;
they are not desired SFT targets. Held-out or rights-blocked candidates cannot
enter the preference export; `eligibility.sft` marks eligible accepted examples.

## Fixture and proof

`fixture.jsonl` is 53 signed recorded fixture events: acceptance, wire rejection,
worker failure, within-margin, non-improving, successful repair and a pending
proposal. Numerical values are synthetic fixtures, **not measured physics**.
The fixture was assembled through the real Ledger and AcceptanceGate using fixed
measurement values. Only its public verification key is retained; private key
material was generated in memory and never serialized. Tests use a fresh
in-memory signer to append withdrawals to temporary copies.

```sh
python -m unittest -v sentilab_core.test_dataset
```

The 13 tests execute the shipping exporter and real CLI/MCP subprocesses. They
cover byte identity, rights, whole-family/seed isolation, source hashes, bounded
comparison claims, direct/transitive withdrawal, retraction, pending/failure
retention, repair lineage, forged display/proposal labels, signed inconsistent
records, corrupted signatures, input validation and immutable snapshot checks.
The test file fails at import on the PR #15 dependency head
`de3fa41c9fe45dd958bc2e06418d993027807448` without the new exporter. Targeted
implementation mutations and actual gate evidence are in `VALIDATION.md`.
