# SLAB047b completed fixture run: independent offline review

The retained bundle consistently records a completed, closed SLAB047b fixture run. All **323 offline consistency checks pass**, with no discrepancy found. All 20 raw responses independently match their expected fixture JSON, and the request/response/receipt hashes agree. This supports the scoped runtime packet as completed engineering evidence; it is not scientific validation or an approval of a broader deliverable. The controller still records `final_deliverable_accepted=false`.

## Exact source, inputs and admission

All 75 downloaded files match the byte counts and SHA256 values in `GPU-DOWNLOAD-AND-CLOSURE.json`. Downloaded controller bytes match exact Git head `3236e23aecafb8e49e31aaec8101d3906f1de2a8`, controller SHA256 `a707a77d4b39836c461b7cacabe17bf1a59efbdcb3938871ea04c077ef32276d`. Independently reconstructed literal policy bytes hash to `1d3acc0186a2d799851f7b43ed1454c6ae893dbacedbfddec3735b6eb593401d`; both match the bridge pins. The grant remains #56545, source `55fe3cab-88b4-4f80-9ae7-2f5ff43c70f7`, with a fresh serving root and owner.

The 17 runtime input-verification entries exactly match committed pins: 13 model files, adapter weights/configuration, retained execution inputs, and the 20-row evaluation fixture. The fixture bytes were independently read from exact Git and rehashed. Multi-gigabyte model and adapter bytes were not downloaded or rehashed by this reviewer; their verification remains the exact reviewed controller's retained attestation.

The frozen approval bytes match the installed/downloaded approval and reservation hash. The preceding offline preflight review independently found native scratch execution and cleanup before controller approval installation. The reservation, worker claim, final container inspection and closure records agree on token `35612fda883c4d2ca7bb0cb82882c8f5` and full container ID `c16b3e9d6a352c2fc64373e4dc65879ed8ca589bf570fa081249932f917e26bb`. Local approval records do not independently authenticate the external room actor.

## Retained startup and request trace

The formerly missing early log context is retained in this run:

| UTC milestone | Evidence |
|---|---|
| 11:37:48.1186 | Kernel mountinfo: read-only `/`; 4 GiB `/tmp` tmpfs with rw/nosuid/nodev and no noexec. Effective UID/GID 1000, HOME=/tmp, HF_HOME=/tmp/hf. |
| 11:38:04.8912 | vLLM begins loading the model from scratch. |
| 11:38:52.8257 | vLLM reports model loading took 48.126966 seconds and 7.67 GiB; the separate weight-load log reports 46.39 seconds. |
| 11:38:58.1136 | FlashInfer JIT/autotuner reports its actual cache at `/tmp/.cache/flashinfer/autotune/v2/3e78077ed30abee7`. |
| 11:39:15.4557–15.8011 | Autotuning ends; engine initialization/profile/KV-cache/warmup completes, reported as 22.96 seconds. |
| 11:39:16.1048 | Adapter `fixture` is loaded from `/adapter`. |
| 11:39:16.9705 | Localhost health returns HTTP 200. |
| 11:39:51.9420 | First completion POST returns HTTP 200. |
| 11:40:11.7066 | Twentieth completion POST returns HTTP 200. |
| 11:40:11.7736 | Container shutdown is triggered after the fixed request loop. |

`STARTUP-TRACE.json` preserves the exact timestamped log lines and line numbers. The service is vLLM `0.33.0rc1.dev157+gedad8b03c`, with `/model`, bfloat16, LoRA rank 8 and maximum model length 1024 shown in its retained configuration. Eager mode disables torch.compile, CUDAGraphs and optional JIT kernel warmup; FlashInfer autotuning still runs. The named Triton/Torch/XDG/CUDA environment overrides are null, meaning package defaults, not resolved-path claims. This run does not explicitly log the resolved Triton `.so` filename. Its actual FlashInfer cache path is observed, and it progresses beyond the previous failed initialization to all 20 responses. No old shared-object mapping exception appears in these retained logs.

The Docker driver still has a 4m/one-file retention limit. `container-log-scope.json` explicitly disclaims complete process history despite capturing all currently available logs without a tail filter. The existing early-to-late milestones above are positively present; no absent event is inferred merely from silence.

## Request binding and measured scope

Every request exactly reconstructs the corresponding committed row with adapter name `fixture`, its system/user messages, temperature 0, seed 818, and max_tokens 80. Every receipt binds the exact raw request and response hashes, row ID, controller and policy. All responses are HTTP 200, valid JSON, finish_reason `stop`, and independently equal the expected output. Reported usage agrees between raw responses and receipts, is additive, and each recorded completion-token rate recomputes from reported completion tokens divided by client-observed seconds.

| Measurement | Observed value |
|---|---:|
| Charged reservation through controller-confirmed removal/port closure | 148.909503 s |
| Docker start intent through first successful health response | 89.050370 s |
| First complete request | 34.969548 s |
| Subsequent 19: median / mean latency | 0.913062 / 1.031705 s |
| Subsequent 19: observed latency range | 0.765914–2.620572 s |
| All 20: summed client request time / completion tokens | 54.571947 s / 353 |
| All 20: completion tokens ÷ summed client time | 6.468525 tokens/s |
| Subsequent 19: completion tokens ÷ summed client time | 17.242787 tokens/s |

These are one serial localhost run's full request durations, including client/transport/receipt-processing overhead, using server-reported token counts. The first request is reported separately because it is much slower; the evidence does not isolate how much of that delay was JIT or any other component. These figures are not decoder throughput, streaming time-to-first-token, a concurrency benchmark, measured GPU busy time, or an adapter-versus-base improvement. `METRICS.json` retains unrounded aggregates; `VALIDATION.json` retains all per-request measurements and bindings.

The 20 rows consist of **six unique source cases and six prompt/output triples**, repeated 4, 4, 3, 3, 3 and 3 times. The same six source record IDs occur in the 200 training rows. Prompts explicitly supply lifecycle/repair labels and the system instruction gives the mapping to the requested output. Consequently 20/20 is exact fixture reproduction and adapter/serving plumbing evidence, not 20 independent held-out trials, scientific generalization, thermal/geometry prediction, or scientific learning.

## Cleanup, clocks and preserved failure history

The GB10 reservation begins at 11:37:44.101327 UTC; controller-confirmed cleanup is 11:40:13.010829, followed by terminal completion at 11:40:13.014224. The recorded monotonic charge is 148.909503325005 seconds, consistent with same-host wall timestamps within microseconds. A separate terminal monotonic sample is not retained, so this corroborates consistency rather than independently reproducing the charge. Original wall and monotonic 900-second deadlines remain intact. The PC's start invocation/return timestamps and GB10 reservation timestamps are separate clock domains; the small PC-return/GB10-reservation offset is not evidence of reversed admission order or clock synchronization.

Final inspection records nonrunning/exited state, exit code 0, no OOM kill, and no container error. Shutdown is not warning-free: vLLM reports force-killing its remaining EngineCore process, and Python reports one leaked semaphore for its resource tracker to clean up. These are retained shutdown diagnostics, not concealed. The later root observation at 11:41:42.683883 reports successful empty Docker inventory, localhost ECONNREFUSED (111), and a free worker lock. It corroborates closure separately, but does not independently pinpoint the earlier controller cleanup instant used for charging.

Original SLAB047 at `baf0091b` remains a separate consumed, failed-closed attempt: 79.617588726003 charged seconds, zero reserved inference requests, and a Triton `/tmp/.triton/cache/.../cuda_utils` mapping failure. Its retained state/reservation/log hashes still match its original download record. SLAB047b's successful scratch preflight (0.638011345 seconds, separate non-GPU charge) and GPU run do not erase or retry that reservation. The earlier noexec explanation remains consistent with the correction, but the old attempt had no effective mount proof, so the historical cause is not retroactively established with certainty.

No device I/O, status/stop, SSH, Docker, compiler, native library, model, solver, test rerun, CI run, deployment, external post or approval action occurred in this independent review. Only local retained files and immutable Git source bytes were read and parsed. Root owns runtime-packet acceptance and broader disposition.
