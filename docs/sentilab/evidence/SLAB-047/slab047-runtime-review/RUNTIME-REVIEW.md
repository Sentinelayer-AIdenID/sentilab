# SLAB047 attempt 1: offline retained-evidence review

The retained evidence consistently records a startup failure with cleanup, not a successful serving run. The one permitted attempt was consumed. It reserved zero inference slots and produced no request, response or inference receipt files. No retry or new workload is authorized by this review.

The offline validator passed 75 evidence-consistency checks with zero failures. All 12 downloaded files match the lengths and SHA256 values in root's download record. This checks the downloaded record's consistency; it is not an independent live observation of the GB10.

## Source, approval and inputs

- Exact source: `baf0091b11c6020601b5ce11029307bf034a3953`.
- Downloaded controller SHA256: `1e4b901a1b8b65ad8b40afd89637b6b6044e12f8f6df58fd6ae4771309c21eaa`; bytes match the independently reviewed source.
- Policy SHA256: `9b49f5149bcab62137dba7515c305a7079364630f74c6a0bab002a430ed944fc`; frozen policy bytes match the one-attempt, 900-second, 20-request grant.
- Attempt token: `6a11048db3704a84afeaf4289cb360ce`; reservation, permanent worker claim and container name agree.
- Frozen approval SHA256: `fce8e1bc31cfe025eb629f4daef32acb0f3024304cb1b5e84ac4f2c21fd32be1`; matches downloaded `APPROVED.json`. Its record names `pocket-forge`, sequence 56532 and the exact final source. Root separately reports Warden 56531. Local JSON does not itself authenticate external room identity or authority.
- All 17 runtime input-verification receipt entries match the reviewed source pins. The 13 model-file entries also match the admission manifest. The multi-gigabyte model and adapter bytes were not downloaded or independently rehashed by this offline review; their runtime verification is the reviewed controller's retained attestation.

## Outcome and charging

Reservation began at `2026-10-31T11:09:50.886416Z`. The retained state records cleanup at `11:11:10.504003Z` and terminal `failed_closed` at `11:11:10.507591Z`, with error `server_exited`, `retry_allowed=false`, `final_deliverable_accepted=false` and no budget exceedance.

The recorded monotonic charge is **79.617588726 seconds**, covering reservation through controller-confirmed container removal and port closure. The corresponding wall timestamps differ by 79.617587090 seconds, within approximately 1.7 microseconds of that charge. The original 900-second deadlines are consistent with the reservation and were not reset. This is a charged attempt lifetime, not measured GPU busy time or inference duration.

Root's separate `DOWNLOAD-AND-CLOSURE.json` observation is at `11:11:48.085121Z`, 37.581118 seconds after recorded cleanup. Its successful Docker inventory command returns an empty inventory, the localhost connection code is `ECONNREFUSED` (111), and the worker lock is free. Its SSH return code is zero. The observation is bound to the downloaded files by its per-file hashes.

That later observation corroborates closure independently of the controller's final state. It does not independently pinpoint the earlier closure instant used for charging. The interval from reservation to this later observation is 117.198711 seconds; it must not be represented as an additional workload or confused with the controller's 79.617589-second lifetime.

## Startup failure and limits of the diagnosis

The retained bounded stderr tail ends the engine-core traceback with:

`ImportError: /tmp/.triton/cache/.../cuda_utils.cpython-312-aarch64-linux-gnu.so: failed to map segment from shared object`

It then reports `RuntimeError: Engine core initialization failed`. The same shared-object mapping error appears in the bounded stdout tail. Relevant stderr lines are 132 and 193; the retained log hashes are sealed with the artifacts.

An execution restriction on the `/tmp` tmpfs is a plausible explanation: the reviewed source mounts `/tmp` with `rw,nosuid,nodev,size=4g,mode=1777` and the failure occurs while loading Triton's generated shared library from that location. **The retained evidence does not include effective mount options or an equivalent controlled mapping probe, so `noexec` is not established as the cause.** Other loader or resource-policy explanations are not excluded by this error text alone. Any corrective configuration and further device experiment need their own scope, source review and explicit authorization; this consumed attempt must not be restarted.

## What this run establishes

The artifacts show input verification followed by a failed engine initialization, zero inference admissions, retained diagnostic tails, conservative attempt consumption and coherent closure records. They provide no model-output correctness, latency, throughput, warmup-to-readiness, serving-parity or worker-quality result. Zero inference receipts means no accuracy denominator; it must not be reported as 0% accuracy or 0/20 successful predictions.

The pinned evaluation file contains 20 rows drawn from six unique source records and six unique prompt/output triples, repeated 3, 3, 3, 3, 4 and 4 times. Labels are exposed in the prompts. Even a future successful run on these rows would be fixture plumbing evidence, not held-out generalization, thermal or geometry prediction, or scientific learning.

## Reproduction and seal

`validate_retained_offline.py` accepts `--artifacts` pointing at the downloaded serving-root directory and `--closure` pointing at root's `DOWNLOAD-AND-CLOSURE.json`. It reads local bytes, parses the pinned controller's literal input tuple without importing or executing controller code, and writes a fresh report directory. `--describe` reads only the pinned review inputs.

The completed run is retained under `validation-20261031T111419608092Z/`. Its `VALIDATION.json` SHA256 is `b2b4d5a0c5760aa36b10ec3a3e4cf0dd6c371de854cf3997180b124f4f128151`. Root's download-and-closure record SHA256 is `ba3b300534d2fc0e531f982ca8742dbae357a99839cd04007271db7f2f361b1a`. `audit-seal.json` binds this report, helper, validation output, downloaded runtime files and closure record.

No SSH, live-state inspection, start/stop, Docker, GPU, model, solver, CI, external post, approval or delivery action was performed by this offline reviewer.
