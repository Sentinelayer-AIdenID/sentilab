# GB10 fixture adapter preflight

**The granted fixture pipeline passed on attempt 1**, completed 2026-10-31 at 07:53:46 UTC: 20 optimizer steps, adapter save, fresh-container reload, fixed-fixture evaluation, localhost vLLM serving and teardown. The independent source/control review passed 15 fake supervisor cases; the independent result audit passed 112 offline checks. This is infrastructure evidence, not a chiplet optimization result.

The implementation loads the model through NeMo AutoModel and trains it with an explicit PyTorch/Hugging Face PEFT loop. It does not execute NeMo's `train_ft` recipe. No thermal solver or paid model endpoint was used in this preflight.

## What ran

- GB10 `promaxgb10-9a1e`, ARM64, NVIDIA driver 580.178.04; authenticated public-key SSH from the operator PC.
- Base: `Qwen/Qwen3-4B-Instruct-2507`, revision `cdbee75f17c01a7cc42f958dc650907174af0554`; Apache-2.0. All 13 downloaded files, totaling 8,060,917,568 bytes, were hashed before execution.
- NeMo image: `nvcr.io/nvidia/nemo-automodel@sha256:70b4e9df8dd23ef451372b25952cffe24ad29c17f5b9de5fd1b244caf4e7b55a`. Installed NeMo AutoModel 0.5.0, PyTorch 2.13.0a0+8145d630e8.nv26.06, CUDA 13.3, PEFT 0.18.1 and Transformers 5.12.1.
- Serving image: `vllm/vllm-openai@sha256:2e735ffeef26457f8a3ff44a62ae182870b10af37adc06ecbb08baca152365c6`. vLLM 0.33.0rc1.dev157+gedad8b03c, PyTorch 2.14.0+cu130, CUDA 13.0 and Transformers 5.20.2. The local Docker image and RepoDigests receipts match; no separate registry revalidation is claimed.
- Seed 818, BF16 base, LoRA rank 8/alpha 32/dropout 0 across seven standard attention/MLP projections. AdamW learning rate 0.0002, 20 optimizer steps, ten single-example microbatches per step. Prompt tokens are masked; response tokens are not truncated or pre-shifted.

| Stage | Result | Charged container seconds |
|---|---|---:|
| Train/save | 200 distinct row IDs consumed once; 20 steps; 16,515,072 adapter parameters | 67.271395921 |
| Fresh reload/evaluate | Distinct container; runtime verifies 504 tensor keys/shapes/values against saved safetensors | 61.155605997 |
| vLLM localhost serving | 40 HTTP200 responses; base and adapter each answer the same 20 requests; teardown confirmed | 185.762536687 |

The three stages total **314.189538605 seconds**. With the separately labeled conservative 180-second reservation for earlier primitive GPU checks, the grant ledger charges **494.189538605 seconds (8.236492310 minutes)**. The grant permits at most 60 GPU-minutes, three attempts and a 10:00 UTC stop. No second attempt ran. The reservation is not a measured historical usage claim. Monetary/electricity cost was not measured; no zero-dollar claim is made.

## Evaluation scope

| Recorded check | Base | Adapter |
|---|---:|---:|
| NeMo-loaded exact JSON | 0/20 | 20/20 |
| vLLM HTTP exact JSON | 0/20 | 20/20 |
| Mean target NLL | 2.2901440203 | 0.00000273187 |

All 20 output pairs changed. Both runtimes produced matching text for each model in this attempt; that is an observation, not a general bitwise-parity guarantee. Training loss decreased from 2.0000299692 at step 1 to 0.00000331448 at step 20.

**There are six source fixture cases, not 200 experiments.** Training has 200 row IDs and 60 distinct prompt contents. Evaluation has 20 row IDs but six distinct prompt contents, repeated 4,4,3,3,3,3 times. Every evaluation source case occurs in training. Prompts expose the recorded lifecycle/repair metadata and explain the requested label mapping. These results establish fixture metadata mapping and adapter plumbing; they establish no held-out scientific generalization, physical prediction, layout improvement or real-data training eligibility.

The fixture data preserves the authenticated SLAB-016 ledger and an export from reviewed source `95e4970fbcd543e26dd0da7aa926f493054c6cc0`. The builder retains source-record IDs and lineage. Failures, rejections and repairs remain explicit; none are silently converted into successful physical experiments.

## Evidence and checkpoint

- `EXECUTION-GRANT.json`: authenticated Warden #56213 and its exact bounds.
- `MODEL-ADMISSION-MANIFEST.json`, `MODEL-LICENSE.txt`, `execution-inputs.json`: base source/rights and exact prelaunch hashes. The historical admission field `trainingApproved:false` precedes the separate execution grant; it is not a later revocation.
- `fixtures/`: original signed input, verifier export, generated train/evaluation rows and their manifest.
- `attempt-01/`: unmodified stage logs, runtime records, step/metric/HTTP receipts, input snapshot, original remote artifact manifest and adapter configuration.
- `review/`: independent pre-execution and result reports, 112 check outcomes and per-tensor hashes.
- `PREPARATION-FAILURES.json`: the corrected preparatory invocation/API errors, distinct from the one successful GPU model attempt.

The original remote manifest covers **31 payload files and 66,305,878 bytes**, all independently rehashed after transfer. Thirty payload files are in this repository; the **66,126,768-byte adapter** is retained separately on GB10 and the operator PC. `ADAPTER-LOCATION.json` records both locations and SHA256 `695581e310def332bd6307527eff6546d95eebb88bec7e6f6ce288a5a61c0f80`. Operator artifact-storage handoff is pending. Do not report the binary as present in Git. Base-model weights are also outside Git.

The offline audit parsed all 504 finite F32 tensor arrays without importing ML libraries; all 252 LoRA B tensors are nonzero. Fresh reload equality is a runtime assertion from the reviewed script, corroborated by its receipt and successful inference, not an independently dumped in-memory checkpoint.

## Operating and verification notes

The scripts under `scripts/gb10/` record this dated, bounded preflight. `model_stage.py` runs inside the pinned NeMo container; `supervise.py` runs on GB10. It checks immutable inputs, reserves attempts before launch, uses an in-container timeout, honors STOP, verifies exact owned-container labels before stopping/removing, retains ambiguous cleanup as active, and refuses duplicate completed execution. NeMo needs UID0 plus only DAC_OVERRIDE/CHOWN to access its root-readable image sources and the mounted operator directory; the model mount is read-only. vLLM runs as UID1000 and publishes only host localhost port 18018. No private SSH key or model-provider credential is transferred.

On GB10, the existing run can be inspected with:

```sh
python3 /home/dell/sentilab/preflight-20261031/supervise.py status
```

The portable fake control checks require Linux/Python and run no Docker, GPU, model, network or thermal process:

```sh
python3 scripts/gb10/test_supervise.py
```

The frozen deadline and completed-run guard intentionally prevent blindly replaying this historical grant. A later run needs a new reviewed grant/input snapshot; never delete the spend state to reset its budget. Original raw request bodies are reconstructed from the pinned HTTP script and frozen data; response bodies are retained directly. Shutdown logs retain a vLLM forced-child-stop and semaphore warning; final owned containers and the localhost listener were absent.

This does **not** complete the product CLI/MCP `gb10 preflight|status` wrappers, the ARM/x86 HotSpot check, SLAB-019 training, production worker deployment, or downstream scientific evaluation. Those remain separate ticket gates.
