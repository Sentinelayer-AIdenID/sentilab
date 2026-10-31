# SLAB047: bounded fixture serving lifecycle

This source implements a proposed engineering slice for the authenticated Warden grant #56496, source `bb58c601-464f-4ebc-89f1-5b6eba9aeb25`, ticket `1509c616-03ee-4d35-b60c-bc70dd18b7fe`. It has not been deployed or executed by its author. An exact-source independent nonauthor +1 and root-controlled staging are required before execution.

The grant permits one attempt with at most 900 seconds including startup/load/cleanup, starting before 2026-10-31 11:45 UTC and stopping by 12:00 UTC. It permits only the retained SLAB018 model/adapter/vLLM image and up to 20 fixed fixture inference requests in one owned localhost container. No training, SLAB018 restart, external route, arbitrary prompts or new model comparison is implemented.

This supports original **SLAB033** checkpoint identity/resource evidence and SLAB018 lifecycle measurement. It does **not** complete SLAB033's held-out promotion, quarantine or rollback, or original **SLAB038** private box-to-GB10 routing/probe. SLAB043 owns canonical CLI/MCP mapping and aliases. No shared CLI/MCP/registry files are changed by this slice. All responses remain `scope_state=staged_open`; no final deliverable is accepted.

## Fixed interface and source identity

The existing entry point remains `sentilab_core.gb10_backend.execute('serve', action='start'|'status'|'stop')`; omitted action means status. No caller can supply a root, host, executable, source, image, grant, approval, command, request body, timeout or SSH option. `context` remains unused. Status/checkpoint operations remain the independently reviewed PR42 implementation.

`gb10_serving.py` uses alias `gb10`, strict known_hosts checking, no forwarding, no multiplexed master and the existing bounded 20-second SSH transport. Its small stdin bootstrap opens every installed source path component without following links, reads at most 64 KiB, checks the compiled-in controller SHA256, then executes those exact bytes. Host identity is additionally checked, but hostname/login/architecture are self-reports: authentication relies on the PC's existing known_hosts pin. Missing/unreviewed staging returns unavailable/refused, not success.

The remote controller is only `/home/dell/sentilab/serving-20261031/serve047.py`, under a root-provisioned directory owned by `dell` with mode 0700. All new artifacts remain there. The retained `/home/dell/sentilab/preflight-20261031` root is only read and mounted read-only. There is no runtime installation, download or SSH-key change.

## Root staging after independent review

Root must use the exact reviewed commit and verify `scripts/gb10/serve047.py` against `CONTROLLER_SHA256` in `sentilab_core/gb10_serving.py`. Any correction changes that pin and requires a new exact-source decision. This source does not grant itself execution.

Root provisions the new 0700 directory and exact controller bytes, then creates a 0600 `APPROVED.json` there from the actual authenticated nonauthor decision. Its shape is:

```json
{
  "schema": "sentilab-slab047-review/1",
  "grant_source": "bb58c601-464f-4ebc-89f1-5b6eba9aeb25",
  "controller_sha256": "EXACT_CONTROLLER_SHA256_FROM_REVIEWED_BRIDGE",
  "policy_sha256": "EXACT_POLICY_SHA256_FROM_REVIEWED_BRIDGE",
  "decision": "PENDING",
  "reviewer": "INDEPENDENT_NONAUTHOR_IDENTITY",
  "review_record": "AUTHENTICATED_EXACT_SOURCE_PLUS_ONE_RECORD"
}
```

The example deliberately cannot authorize a start. Only root may replace `PENDING` with the actual `+1` and fill the verified record and pins. The approval file is a trusted local operator gate, not a cryptographic verifier for room identity. It is not accepted through caller arguments. Root should preserve the review record and source hashes alongside deployment evidence.

Admission acquires an exclusive lock and reads approval **after** obtaining that lock, so a revocation while waiting is not stale authorization. It checks the cutoff and STOP again. An exclusive, fsynced `reservation.json` consumes the only attempt before child spawn or Docker work; it freezes exact approval bytes/hash and policy bytes/hash. Interrupted/spawn-ambiguous reservations remain consumed with a 900-second conservative charge. A permanent `worker-claimed.json` prevents restarting the same attempt even after the worker exits. There is no retry/reset endpoint.

The detached worker embeds the validated source bytes in its launch arguments, with stdin/stdout/stderr closed, an independent session, and no later PID signals. It holds a worker lock and uses a separate lock around Docker lifecycle operations. Status reports lock observation, current fully checked container state and current port state rather than inferring liveness from stale state or an old SLAB018 teardown.

## Runtime boundaries and evidence

Seventeen retained-file pins cover the 13 model files, adapter weights/config, original attempt input manifest and exact 20-row evaluation JSONL. Model shards are streamed with bounded reads and descriptor identity/stability checks. The exact bytes used as prompts are rehashed after loading. No model shard is accumulated in RAM. Host files are assumed to remain under trusted operator control; the container receives read-only mounts and cannot mutate them.

Docker commands explicitly use `/usr/bin/docker --host unix:///var/run/docker.sock` with a minimal environment and a new-root Docker configuration path. They cannot inherit a cloud Docker context. The pinned image ID uses `--pull=never`. The controller creates one container with owner/token/source/policy labels, saves the full ID before start, and uses user 1000:1000, dropped capabilities, no-new-privileges, 96 GiB memory, 12 CPUs, 2 GiB shared memory, read-only root filesystem, temporary `/tmp`, offline model settings and disabled usage telemetry. Only `127.0.0.1:18047:8000` is published. These new filesystem restrictions still require a real approved compatibility observation; fake tests do not establish vLLM readiness.

The container's entry wrapper derives its timeout from the original reservation wall and monotonic deadlines, including if Docker START is delayed. GNU timeout provides TERM plus a five-second kill fallback, leaving at least 35 seconds before the original deadline. The controller stops new work with a 60-second cleanup reserve. Readiness is bounded to 300 seconds, and every HTTP child has a hard outer timeout of at most 15 seconds. Requests are serial. Only the fixed adapter name `fixture` and original 20 rows are used. Health GETs do not consume inference slots; every inference POST first persists its exact JSON body and consumes a slot. Ambiguous POSTs are never retried.

The new root retains reservation/state, input verification, exact request and response **body** bytes, SHA256s, HTTP status, per-request receipts, and bounded container log tails. A non-200 body is retained before failure. When the server supplies valid integer token usage, receipts retain it and derive completion tokens divided by client-observed request duration; absent usage remains null. Timing includes the serial client overhead and is not decoder throughput or a concurrency benchmark. Warmup is Docker start intent through the first successful localhost health response. Six repeated training-source cases and label metadata mean this is plumbing evidence, not held-out generalization or scientific learning.

STOP is durable and remains set. Cleanup can only stop/remove a full 64-hex container ID after matching exact owner/token/source/policy labels, image and name. A name is used solely to recover a full ID for inspection after ambiguous CREATE. A daemon CREATE with no returned ID cannot be declared closed from an empty inventory; it stays unresolved and charged conservatively. No arbitrary listener, host PID or process group is killed. After stop, the controller retains bounded raw logs, removes the exact checked container, confirms absence via daemon inventory, and requires a localhost connection-refused result. A timeout/permission error is not port-closure proof.

Actual charge covers reservation through confirmed removal and port closure, including startup, hashing, load, requests and cleanup. Unknown cleanup uses at least the full 900-second reservation; measured overshoot is retained and makes the result fail. No charge is presented as monetary cost. Docker/host failure can prevent confirmed cleanup despite the internal watchdog; this is reported as unresolved and blocks retry rather than asserting a hard physical guarantee. Root must independently confirm closure and account any overshoot. A slow STOP may outlast the existing 20-second SSH transport; the durable STOP and detached worker continue to govern it, and root must query status instead of interpreting transport timeout as cleanup success.

## Verification limits

The author runs finite local fakes only, including one-attempt races, source/policy/reviewer gates, approval revocation during lock wait, frozen admitted bytes, STOP before/between requests, ambiguous CREATE/HTTP/removal, ownership mismatch, deadline handling, exactly 20 byte-bound receipts and token/timing scope. Existing Windows backend tests retain their platform skips. No actual SSH, Docker daemon, Linux lock contention, GPU, vLLM/container startup, model inference, external network, CI or deployment is exercised by the author. An independent exact-source reviewer must assess the Linux path/lock/process boundaries before root considers the one real attempt.
