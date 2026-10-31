# SLAB018 corrected preflight: independent pre-execution review

Reviewer: requirements_audit. Decision: **scoped +1 for one fixture-only preflight attempt under the existing SLAB018 grant**, using the exact scripts below. This is a review decision, not a new execution grant. Root remains the execution owner.

The review combined the actual pinned image's source/API inspection, a reproduced no-GPU import failure for the original UID1000 invocation, final source review, and 15 fake-only supervisor cases. Root separately reported that its corrected exact CPU invocation successfully imported NeMo and tokenized all 200 training and 20 evaluation rows. No model, training, GPU, thermal simulation, real network request, or Docker process ran in the fake harness.

## Exact reviewed inputs

| File | SHA256 |
|---|---|
| model_stage.py | 3e8412d3a2c7cf2c7aab4c720e9d30ba56b4803c299393f893f8525de3a4a8a5 |
| supervise.py | f6d33d4941cdba0c697f382f9fa3f080487ab53a121e0cb77d5728caaa3e4aae |
| http_eval.py | 480e4e5da6eda285a6fc1272fb22aec59142723f752096c10b097a93a8abadee |

Source directory: `.sentinelayer/sentilab-planning/gpt-astra-carter/slab018-worktree/scripts/gb10/`. Immutable reviewed copies and a hash manifest accompany this report.

The execution grant is Warden sequence 56213, sourceId `3f4d0596-1b3d-45a6-aa98-2c865c6a351f`: synthetic SLAB016 fixture data, 20 optimizer steps, saved adapter, fresh-container reload, 20 fixed prompts base/adapter, localhost vLLM serving of the same prompts, and teardown. Its caps are 60 total GPU-minutes, three attempts, and an absolute stop at 2026-10-31T10:00:00Z. This review +1 is for the next single attempt; a new runtime failure needs review before retry.

Model: `Qwen/Qwen3-4B-Instruct-2507`, revision `cdbee75f17c01a7cc42f958dc650907174af0554`. Admission manifest SHA256: `3888c92c4c60bcd20ea15e3a2bc05d9ee421dedc50cfcf0d6d2bc5f5b1da4120`.

NeMo image: `nvcr.io/nvidia/nemo-automodel@sha256:70b4e9df8dd23ef451372b25952cffe24ad29c17f5b9de5fd1b244caf4e7b55a`. Actual package metadata is 0.5.0; public v0.6 documentation was not substituted for container source. vLLM local image ID: `sha256:2e735ffeef26457f8a3ff44a62ae182870b10af37adc06ecbb08baca152365c6`.

## Corrections verified

- NeMo's root-readable image sources use the explicit `_transformers.auto_model` import with UID0, capability drop plus DAC_OVERRIDE/CHOWN, and no new privileges. The invocation's direct output subtree is restored to UID/GID1000 in `finally`; symlinks are skipped. vLLM remains UID1000.
- Tokenizer calls explicitly request `return_dict=False`, assert lists, preserve the original row's prompt prefix and answer tokens, and fail on truncation or empty answer masks. HF labels are not pre-shifted.
- The loop creates a single HF-PEFT adapter after loading with NeMo, verifies finite loss/gradients and changed finite trainable tensors, saves safetensors, and compares loaded adapter tensor keys, shapes, finiteness, and values in a fresh container.
- The supervisor reserves the attempt and stage before launch, verifies input hashes and path containment, uses deterministic names plus exact owner/attempt labels, and retains ambiguous cleanup as an active state blocking retry.
- STOP can find the deterministic name before the returned ID is saved and falls back from stop to kill. Stage teardown confirms stopped state, preserves stdout and stderr, and only then removes the owned container.
- GPU accounting covers container launch through confirmed stop. Post-stop log archival is excluded; unconfirmed stop is charged conservatively. Final budget, deadline, active-state and no-running-owned-container gates are explicit.
- Unchanged generated outputs retain the HTTP plumbing evidence but finish as `plumbing_finished_difference_requirement_unmet`, rather than falsely completing the grant's difference requirement.

## Executed verification

`test_supervisor_fake.py` loads the unchanged supervisor while redirecting its fixed root into an isolated temporary directory. Process, Docker, HTTP, signal registration and time calls are replaced by fakes. Actual fcntl and file operations only affect that temporary directory. The test imports no model code or ML framework.

Fifteen cases passed: successful difference; zero difference; both log streams and teardown; active-state refusal; attempt cap; completed-run refusal; exhausted budget; STOP file; expired deadline; changed input; STOP by name with kill fallback; wrong owner rejection; ambiguous creation cleanup; unresolved cleanup fail-closed accounting; final budget gate; and final owned-running gate. Some cases jointly test multiple properties; there are 15 case records, not 17 independent runs.

Invocation: `wsl -d Ubuntu-24.04 -- env PYTHONDONTWRITEBYTECODE=1 python3 -B /mnt/c/Users/carth/Desktop/projects/PlexAura_Inc/SentinelLayer/AIdenID/tasks/sentilab-review-2026-10-30/slab018-preflight-review/test_supervisor_fake.py`. Result: exit0; all 15 cases passed. The JSON result is retained alongside this report.

## Limits and required runtime evidence

No blocker remains in the reviewed static/source/control-flow scope. Dynamic GB10 loading, optimization, save/reload, output differences and HTTP serving must still succeed in the granted attempt. The fake harness is not a GPU-runtime compatibility test or a proof against arbitrary Docker daemon failure. Runtime failures remain evidence to preserve and review; they are not permission to change models, substitute prompts, bypass limits or retry automatically.

The fixture repeats six source cases across 200 training rows and 20 evaluation rows. Prompts disclose lifecycle/gate metadata. It tests metadata mapping and adapter plumbing, not hidden physical outcomes, generalization, chiplet optimization, or learning from independent experiments. No grouped holdout or scientific evaluation is claimed. A zero-difference outcome must remain unmet even if tensors changed or likelihood improved. HF/vLLM greedy outputs may differ because full generation-configuration parity is not asserted; do not claim bitwise parity.

Describe the implementation as **NeMo AutoModel-loaded model plus explicit PyTorch/HF-PEFT SFT**, not execution of NeMo's `train_ft` recipe. Record both container identities, driver and CUDA versions (including serving), hashes, timings, raw logs, actual step count, fresh reload tensor receipt, all fixed base/adapter outputs, all 40 HTTP responses, and confirmed teardown in the flight record. CLI/MCP wrappers remain the granted follow-up. No +1 is given for real-run data, SLAB019, broader training or scientific success.
