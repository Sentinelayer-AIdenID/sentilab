# SLAB047b non-GPU executable-scratch preflight

This helper implements the cheap scratch check required by Warden grant 56545, source 55fe3cab-88b4-4f80-9ae7-2f5ff43c70f7. It does not start a model, request a GPU, install a package or establish vLLM readiness. Root must obtain exact-source review before staging or executing it. Its success is a prerequisite for the separately authorized GPU attempt, not authorization for that attempt.

Install scripts/gb10/preflight047b.py as /home/dell/sentilab/serving-20261031b/preflight/preflight047b.py. Root provisions that fresh directory as dell, mode 0700. The helper follows no symlink in the fixed root path. It accepts only run, status or cleanup, with no caller-selected path, image, shell, code or Docker arguments. It never touches the old SLAB047 root.

Before run, root writes APPROVED.json in that directory with these exact fields:

    {
      "schema": "sentilab-047b-preflight-review/1",
      "grant_source": "55fe3cab-88b4-4f80-9ae7-2f5ff43c70f7",
      "preflight_sha256": "<SHA256 of exact installed helper bytes>",
      "decision": "+1",
      "reviewer": "<external reviewer>",
      "review_record": "<external exact-source review record>"
    }

Approval is reread under the run lock and frozen into a durable, exclusive intent.json before Docker CREATE. This is a trusted local operator gate, not cryptographic room-identity verification. Self-approval identifiers are refused. Subsequent runs cannot consume another attempt. Failed or ambiguous CREATE consumes the preflight attempt; empty inventory does not resolve an ambiguous CREATE with no returned ID.

## Fixed containment and proof

The pinned image is sha256:2e735ffeef26457f8a3ff44a62ae182870b10af37adc06ecbb08baca152365c6, with pull disabled. Runtime is fixed to runc, with no --gpus and with NVIDIA_VISIBLE_DEVICES=void and CUDA_VISIBLE_DEVICES=-1. Runtime, DeviceRequests, Devices and visible NVIDIA device paths are checked. Omitting --gpus alone would be insufficient with an NVIDIA default runtime.

The container uses UID:GID 1000:1000, read-only root, all capabilities dropped, no-new-privileges, no network, no published port and no model/adapter/host mounts. Memory/CPU/shared-memory limits match serving: 96 GiB, 12 CPUs and 2 GiB shared memory; limits do not allocate that memory. The probe adds a 64-process limit and bounded logs. Scratch flags are exactly:

    --tmpfs /tmp:rw,exec,nosuid,nodev,size=4g,mode=1777

In a fresh private /tmp/.triton/cache/slab047b-probe directory, fixed literal C is compiled with /usr/bin/cc -shared -fPIC -O0. The exact .so is loaded through ctypes.CDLL and its no-argument function must return 47. A separate fixed script is executed directly with shell=False; its absolute /usr/bin/python3 shebang must produce exit code 47. Container success is exit code zero. Missing compiler/interpreter or load/exec failure is a failed preflight; nothing is fetched or installed.

Evidence includes HostConfig (including Tmpfs/runtime/devices), image/name/full ID/labels, numeric UID/GID, raw /proc/self/mountinfo, source/script/shared-library hashes, compiler status and bounded compiler tails. Mountinfo must show read-only root and exact /tmp tmpfs with rw/nosuid/nodev and without noexec. Linux may omit positive exec; native loading and direct execution provide behavioral proof. Actual mountinfo is collected before compilation and remains in structured failure output if subsequent compilation/loading/execution fails.

## Lifetime, cleanup and evidence

The synchronous preflight has a fixed 120-second budget including startup and cleanup, with a 30-second cleanup reserve. Original wall and monotonic deadlines are capped at 12:15 UTC, before GPU admission closes. A container-side GNU timeout derived from those same deadlines limits the inner probe to at most 45 seconds including a three-second kill allowance. Compiler and script have independent 15- and five-second timeouts. GNU timeout availability is itself a compatibility requirement.

Each Docker command output stream is bounded to 512 KiB. Commands use the local Unix socket explicitly and a minimal environment. On timeout, only the unreaped owned CLI child is signalled. No arbitrary host PID or process group is stored or killed.

Cleanup mutates only an inspected full 64-hex ID whose image, exact name and ownership/source/grant/token labels match. A name can recover an ID for inspection; it is never a mutation target. Probe stdout/stderr are retained before removal. Absence requires successful daemon inventory corroboration. Unresolved cleanup stays failed and charged at least the entire preflight budget. Host or Docker failure can prevent hard wall-clock cleanup; the result must not conceal that uncertainty.

result.json uses schema sentilab-047b-preflight-result/1. Consumers must check the expected helper SHA, grant, image and tmpfs, plus preflight_ok=true, probe_verified=true, cleanup_verified=true, no errors, no budget exceedance, gpu_requested=false and retry_allowed=false. The hashes map binds intent.json, inspection-created.json, inspection-finished.json, probe.stdout.json, probe.stdout.log and probe.stderr.log. The raw log tail and structured mount/probe proof are separate retained files.

status reads the result without Docker activity. cleanup is bounded owned-container recovery and writes cleanup-recovery.json; it never converts a failed result into successful preflight admission. The source loader freezes installed bytes before any intent or Docker effect.

A green result establishes only native mapping and direct script execution in this pinned image/configuration. It does not prove actual Triton JIT, LoRA loading, GPU visibility, server readiness or inference. Later milestones need retained observations during the separately authorized GPU attempt.

## Local verification

Run python3 -B scripts/gb10/test_preflight047b.py on Linux. Fifteen finite tests passed in 0.781 seconds on the author's Linux run. They cover fixed native-source bytes and argument policy, mount/identity rejection, one-attempt admission, bad source approval, STOP/deadline, GPU-device injection, ambiguous CREATE, owned-ID-only cleanup, missing removal confirmation and proof/hash retention.

Tests use finite Docker/clock fakes and temporary local Linux files/locks. They never run Docker, SSH, the compiler, a generated script, a native library, a model or a GPU. Pure syntax/argument/proof tests also run on Windows; Linux filesystem tests are explicitly skipped there. These tests do not establish real image/runtime/compiler compatibility.
