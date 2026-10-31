# GB10 serving lifecycle evidence, 31 October 2026

The separate SLAB047b serving validation completed at **11:40:13 UTC**. It returned the expected JSON for all 20 fixed fixture requests and removed its owned container. A later operator check independently observed empty Docker inventory, localhost port 18047 refused, and a free worker lock. This package preserves the earlier failed attempt, the non-GPU executable-scratch preflight, the successful run, and their independent offline reviews. It does not authorize another device run.

| Stage | Outcome | Recorded charge | Scope |
|---|---|---:|---|
| Original SLAB047 | Failed closed before inference | 79.617588726 s | One consumed attempt; zero requests; original failure and cleanup retained |
| Separate SLAB047b preflight | Passed native library and script execution on scratch | 0.638011345 s | Non-GPU; runc, no GPU devices or network |
| Separate SLAB047b serving | Completed 20 fixture requests | 148.909503325 s | One consumed GPU lifecycle; startup through controller-confirmed cleanup |

These charges remain separate and do not replace SLAB018's previously recorded 494.189538605 seconds including its 180-second reservation. Lifecycle seconds are not measured GPU busy time. Monetary cost is unmeasured. Never rerun completed SLAB018, failed SLAB047, or completed SLAB047b from this evidence package.

All 20 requests repeat **six cases already present in training**, with lifecycle and repair labels supplied in the prompt. The result demonstrates adapter loading and serving plumbing. It does not measure scientific generalization, thermal optimization, or 20 independent held-out trials. All eight final SentiLab deliverables remain incomplete; the original 41-ticket/234-requirement baseline is unchanged.

## Evidence and verification

- [Independent successful-run review](slab047b-gpu-review/RUNTIME-REVIEW.md): 323 consistency checks, all 75 downloaded files, 17 input-pin receipts, and all 20 raw responses.
- [Independent non-GPU preflight review](slab047b-preflight-review/PREFLIGHT-REVIEW.md): 76 checks, including executable scratch and cleanup before GPU admission.
- [Independent original-failure review](slab047-runtime-review/RUNTIME-REVIEW.md): 75 checks; the failure, reservation and zero-request state remain intact.
- [Successful-run download and independent closure](slab047b-admission/GPU-DOWNLOAD-AND-CLOSURE.json), [preflight download](slab047b-admission/PREFLIGHT-DOWNLOAD.json), and [original-failure download](slab047-admission/DOWNLOAD-AND-CLOSURE.json) bind the raw runtime files.
- [Source manifest](SOURCE-MANIFEST.json) preserves the exact bytes and original locations. Copies under `source/` are bound to PR45 head `3236e23aecafb8e49e31aaec8101d3906f1de2a8`; `room/` retains separately authenticated grant/review records. Local hashes and recorded approvals do not independently authenticate a remote actor or prove the underlying hardware observation.
- Run `node verify.mjs` from this directory for an offline transport-integrity and fixture check. It does not invoke SSH, Docker, a compiler, model, solver or any archived script. The original independent reports remain byte-for-byte snapshots; historical local paths in them refer to the review workspace.

The final controller is SHA256 `a707a77d4b39836c461b7cacabe17bf1a59efbdcb3938871ea04c077ef32276d`; canonical policy is `1d3acc0186a2d799851f7b43ed1454c6ae893dbacedbfddec3735b6eb593401d`. The grant is Warden #56545, with exact-head Warden #56553 and Forge #56555 approvals before the new work. Both attempts use pinned retained SLAB018 model/adapter inputs. No model or adapter binary, credentials, SSH key, or third-party robot asset is included. Model licensing and pinned methods remain in the SLAB018 technical package; original project-generated fixture records, traces and review reports are copied here.

## Timing and limits

Docker start intent to first successful health response was 89.050370 seconds. The first full request took 34.969548 seconds; the subsequent 19 had median 0.913062 seconds and range 0.765914–2.620572 seconds. These are one serial localhost run's client-observed durations. They are not decoder throughput, time to first token, a concurrency benchmark or a base-versus-adapter speed comparison. The evidence does not isolate the cold-delay components.

The new traces retain effective mount flags, UID/GID, model load, actual FlashInfer JIT/cache path, all 20 HTTP responses and shutdown. Scratch explicitly permits execution; the earlier noexec explanation is consistent with the correction, but original effective mount flags were not recorded, so historical causality remains uncertain. Logs retain bounded Docker rotation/completeness limitations, forced EngineCore termination and a leaked-semaphore warning. Final inspection reports exit 0 and no OOM; the later independent closure confirms no owned container or port remains. The recorded monotonic charge is consistent with same-host wall timestamps, but there is no separate terminal monotonic sample for independent recomputation.

This package is additive engineering evidence. Secure model/provider admission, actual scientific research and agents, numerical headroom, independent reproduction, eligible real-data training, full CLI/MCP parity, and long-running serving promotion remain separate work.
