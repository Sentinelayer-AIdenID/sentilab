# Agent door scorer

Internal Python 3.12 service for the sentilab API, running on the mint host in the
**existing gate-zero image**. It uses `micro150-45mm` geometry, the `validate-reference`
path's `slab049.generate_reference` and `tap_argv`, and its strict
`summarize_evaluation` reader. No thermal constants or selectors are rederived.
All reported temperatures are **simulated, not silicon**.

## API

Every request, including health, requires `Authorization: Bearer <SCORER_TOKEN>`.
The API alone knows this service credential; purpose tokens never reach the scorer.
Bind the listener to a private interface and restrict access to the API host.

`POST /v1/score` and `POST /v1/replay` accept exactly:

```json
{"run_id":"<contract run id>","token_ref":"<sha256 of purpose-token nonce>","proposal":{"schema":"sentilab-open-proposal/1","...":"unchanged contract proposal"}}
```

The schematic proposal above is not a valid submission: use the full schema in
`contracts/open-proposal-v1/schemas/proposal.schema.json`. The API maps
C0..C3,D0..D3 to contract die indices 0..7, computes the contract geometry hash, and
calls `run_id(manifest_id, token_ref, proposal_sha256)` from `open_proposals.contract`.
`anon-token/1:<token_ref>` is an anonymous principal, not a person or identity.
The proposal's `proposal_key` is the stable request key. Principal, manifest, key,
canonical payload and run are bound atomically. Exact retries return the original
response without another charge, including after restart; changed content or an
incorrect run id gets 409 `idempotency_conflict`. Replay requires a successful score
owned by that same principal and payload; a replay is also idempotent.

Both intake and dispatch rerun `validate_local` **with the pinned TapGeometry
layout checker**, terms and current signed admission. CPU rotations are 0/90;
DRAM rotation is 0. Candidate centres use the 500 µm lattice. Illegal input gets
422 `rejected` and unchanged contract violations, with no reservation or solve.
Unknown proposal fields, nonfinite values, duplicate JSON keys, oversized bodies
and unsupported request shapes are refused without echoing submitted text.

A successful score returns `evaluated`, `per_die_c`, `wire_proxy_mm`, a receipt, and:

| Field | Definition |
| --- | --- |
| `metric_id` | `max_chiplet_centre_cell_mean_C` |
| `max_chiplet_centre_mean_c`, `peak_c` | Maximum mean of each chiplet's 1/2/4 central grid cells |
| `native_all_block_max_c` | Native all-block maximum from the steady output |
| `active_grid_max_c` | Active-layer grid maximum |
| `hotspot_ok` | Strictly `active_grid_max_c < 119.07` |

The contract amendment's `native_all_block_max_C` and `active_layer_peak_C` are
also explicit aliases. Responses include the metric definition, °C units, 0.01 K
underlying grid resolution, and a raw-layout reference hash. Averaging adds no
measurement precision; display rounding must not enter comparisons. The raw
reference binds 115.93 / 115.935 / 119.07 °C and wire 9.38487 mm; the legal snapped
reference has wire 9.5 mm and a **null** reference temperature until separately
measured. Neither score nor replay declares a routed-wire or "beat" claim.

Replay uses a fresh supervisor, solver process and temporary directory. It returns
`reproduced` only for identical numerical results, input hashes, and both output
hashes. Otherwise it returns `not_reproduced` with `reproduction_mismatch` or
`reproduction_failed`, retaining both receipts. Failed score attempts return
`failed` with `timeout`, `interrupted` or `oracle_error`.

`GET /v1/health` reports the startup-measured binary SHA, image digest, grant id,
and `budget_left_cpu_s`. It never starts a solve. Missing/wrong auth returns 401.

## Runtime and admission

Required environment (supply credentials through the operator's secret injector;
never write them to files, command arguments or a checked-in `.env`):

- `SCORER_TOKEN`: service bearer credential.
- `SCORER_ENGINE`: engine path; defaults to `/app/sundai_hotspot6/hotspot`.
- `SCORER_ENGINE_SHA256`: expected digest; defaults to
  `751b357f6b5af395a4447d6e3bfeef3a75eb447091798365a3db4f0e00618cc6`.
  A mismatch refuses startup. Local tests override it with their fake engine's hash.
  The verified private copy is executed for the lifetime of the service.
- `SCORER_IMAGE_DIGEST`: actual gate-zero image digest, `sha256:<64 lowercase hex>`.
- `SCORER_ADMISSION_PUBLIC_KEY`: the operator's Ed25519 public key as 64 lowercase
  hex characters. This is public verification material, not a private key.

`--admission` names an operator-owned, read-only JSON file:

```text
{"payload": {
  "schema": "sentilab-scorer-admission/1",
  "manifest": <the unchanged, fully pinned, signed open-proposal manifest>,
  "grant_id": "slab-demo-20261101",
  "scope": "propose:cpu-dram",
  "admission": "open",
  "not_before": <UTC ISO timestamp>,
  "not_after": <UTC ISO timestamp>,
  "enforcement_sha256": <whole-container enforcement evidence SHA-256>,
  "binary_sha256": <the engine SHA-256>,
  "image_digest": <the actual image digest>
}, "signature": <hex Ed25519 signature over canonical(payload)>}
```

Use `sentilab_core.envelope.canonical` for the signature bytes. No private key is
loaded by this service. This internal wrapper binds the manifest signature to the
operator's grant/runtime/scope; it does not change the proposal contract. The
manifest must pass `validate_record('manifest', ...)`, match micro150's catalogue,
netlist, geometry and selector, pin this binary, name this grant in `refs.grant`,
and carry the same enforcement evidence in `checks.cpu_enforcement_evidence_sha256`.
The fixture config digest and `fixture.package.hotspot_config_sha256` are checked
separately. The frozen gate-zero `new_hotspot.config` bytes are loaded once,
copied into the solve directory, hashed under the reservation lock, and checked
again in the worker immediately before engine execution. Only an admitted solve
launches the input generator, inside the same owned and CPU-metered tree as the
engine. Cached, busy, and budget-refused requests launch no generator process.
The effective window is the intersection of manifest and wrapper windows. Only
`admission: open` permits work; update the file by atomic replacement to close it.
An invalid signature or missing evidence fails closed. Health remains readable
when admission closes. Warden supplies the actual signed manifest, runtime digest,
and whole-container enforcement evidence at deployment; test fixtures grant no
production authority.

The host is Linux with `/proc`, `prctl` subreaping, pidfds, and `libseccomp.so.2`. Network
syscalls (including socket creation and io_uring setup) are denied in each solve
supervisor and inherited by its children. The engine gets only the gate-zero
locale/timezone/single-thread BLAS environment, no service credentials. Each engine
has its own session/group and `RLIMIT_CPU=10`; the supervisor monitors cumulative
tree CPU. A separate request guardian outside that CPU limit holds an engine
pidfd before execution and adopts orphans if the worker dies. It enforces the
30-second wall deadline, then allows two seconds for kill/reap; the service also
bounds its wait and escalation. A failed `/proc` scan falls back to retained
handles and the guardian's direct children, including adopted `setsid()` orphans.
`wait4` reports CPU for the guardian and its reaped tree. Worker death, failed
metering or unconfirmed cleanup sets `usage_complete: false` and charges at least
the full 10 CPU-second reservation. Receipts also carry `cleanup_complete` and the
separate `owner_pid`, `worker_pid` and `engine_pid`.
Output files are limited to 16 MiB each. Per-solve directories are removed after
hashing; both output hashes and all input hashes remain in the receipt.

## Ledger and deployment

`--ledger` is an append-only JSONL file on a **persistent local filesystem** shared
by every scorer process under this grant. Under one `flock`, dispatch revalidates,
checks balances/concurrency and appends+fsyncs a 10 CPU-second reservation. Settlement
appends measured CPU and the response. Caps are 3,600 CPU-seconds globally, 30 per
nonce hash, and four simultaneous reservations. A fifth solve gets 429 `busy`;
insufficient CPU balance gets 403 `budget_exhausted`. There is no queue. Attempts
are the number of reserved records, separate from CPU balances.

A crash leaves its reservation charged and its slot occupied: restart does not
refund, relaunch or silently recover it. Operator reconciliation requires proving
the old process tree is gone and settling the outstanding reservation; never delete
or truncate the ledger to reset a grant. Corrupt/torn ledger records refuse service
until the operator reconciles them. A local filesystem with working advisory locks
and fsync is required; separate ledger files would create separate caps.

Example launch inside the gate-zero image, with env already injected:

```sh
python research/agent-door/scorer/service.py \
  --host 0.0.0.0 --port 8765 \
  --ledger /scorer-state/grant.jsonl \
  --admission /scorer-config/admission.json \
  --work-root /scorer-work
```

Example container flags (`SCORER_IMAGE` is the actual pinned `repository@sha256:...` image; use an API-only network):

```sh
docker run --rm --cpus=4 --pids-limit=128 --memory=4g \
  --read-only --cap-drop=ALL --security-opt=no-new-privileges \
  --network scorer-internal \
  --mount type=bind,src=/srv/scorer-state,dst=/scorer-state \
  --mount type=bind,src=/srv/scorer-config,dst=/scorer-config,readonly \
  --mount type=bind,src=/srv/scorer-code,dst=/app/research/agent-door/scorer,readonly \
  --tmpfs /scorer-work:rw,exec,size=512m --tmpfs /tmp:rw,size=128m \
  -e SCORER_TOKEN -e SCORER_ENGINE -e SCORER_IMAGE_DIGEST -e SCORER_ADMISSION_PUBLIC_KEY \
  --entrypoint python "$SCORER_IMAGE" \
  /app/research/agent-door/scorer/service.py --host 0.0.0.0 \
  --ledger /scorer-state/grant.jsonl --admission /scorer-config/admission.json --work-root /scorer-work
```

The gate-zero image must contain this scorer code (or receive a read-only code
mount) while preserving the pinned engine. Do not rebuild the engine on another
distribution and claim the same identity. To roll back, close admission, drain the
service, and retain the ledger before changing the code/image. Do not run two
versions with independent ledgers. Only request run id, nonce hash, state and CPU
are logged; neither bearer credentials nor the proposal/salted private handle is
written to the ledger or logs.

## Verification

```sh
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pip install pytest
(cd sundai_controller && python -m unittest -v test_controller.py test_experiment.py)
python -m unittest discover -s sundai_thermal -p 'test_*.py'
(cd sundai_hotspot && make -j4 SUPERLU=1)
python -m pytest -q research/agent-door/scorer/tests
```

The HTTP tests run the shipping server with a fake executable, sign synthetic
admissions with keys generated only in RAM, and test actual subprocess limits,
network denial, process cleanup, reservations, replay and refusals. Synthetic
114.93/115.93/119.07 values test selector separation, not thermal accuracy.

`test_reference.py` **skips unless `SCORER_ENGINE` hashes to the production pin**.
Inside the gate-zero image it reserves/settles raw-reference solves, checks all
three exact raw statistics and frozen inputs, uses the production replay comparator,
then separately scores/replays the legal snapped candidate through HTTP. A local
skip is not a gate-zero reproduction; Warden must run this check in the image.
`SCORER_REFERENCE_CASE` optionally locates the af66bcfc public `case.json` mirror
(default `/workspace/inputs/case.json`); its separate cross-check compares the
published sizes, powers, halos and stack to the repo's generated inputs.
