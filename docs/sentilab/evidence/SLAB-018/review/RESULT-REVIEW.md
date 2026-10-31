# SLAB-018 attempt 1: independent artifact audit

Reviewer: `aneta_packet`. Decision: **scoped +1 for the recorded fixture plumbing result**. All 112 offline artifact checks passed. The evidence supports the granted train, save, fresh-container reload, fixed-fixture evaluation, localhost HTTP serving, and teardown sequence. Root still needs to package the flight record in its evidence PR for Warden review; this audit is not that review or a new execution grant.

The audit began after `ROOT-FETCH-COMPLETE.json`, timestamped 2026-10-31T07:55:07.837Z, bound the complete artifact set. No SSH, model execution, GPU work, thermal work, Docker command, or network call was performed by this reviewer. The audit uses Python standard-library parsing, hashing, arithmetic, and raw float inspection. It does not import PyTorch, safetensors, or the supplied runtime scripts.

## Independently checked evidence

- All 31 archived payload files match the remote manifest, totaling **66,305,878 bytes**. Remote manifest SHA256: `69e2d99bee3d7c6ca825aef26741094d1ceb2223bb79a62dca605e8541430a01`.
- The three executed scripts match the exact independently reviewed script hashes. The attempt binds execution-inputs SHA256 `230fd89ad116537c30cfd2c934d0ccae28dd4acec5d7b3361e1bd16bbecf1357`.
- The data files, builder, and source-export snapshot match their frozen hashes. All 220 rows match the source verifier labels and lineage. The 20 step records and raw timestamped training log agree exactly. **200 distinct training row IDs were each consumed once**, in the seed-818 order, ten rows per optimizer step.
- The saved checkpoint has **504 finite F32 tensors and 16,515,072 parameters**. All 252 LoRA B tensors contain nonzero values. Shapes, rank-eight pairs, complete nonoverlapping data offsets, file hashes, and separate SHA256 hashes of every tensor's raw bytes were checked. Adapter SHA256: `695581e310def332bd6307527eff6546d95eebb88bec7e6f6ce288a5a61c0f80`.
- The train and evaluate stages have distinct container IDs and PIDs, sequential timestamps, exit code zero, and no recorded error. The runtime's fresh reload assertion checks identical tensor keys, shapes, finiteness, and values against the saved adapter; its receipt records 504 equal tensors.
- Every evaluation expected answer matches the frozen dataset. Exact-JSON flags, output-difference counts, and arithmetic means were recomputed from all per-row results and checked against the raw evaluation log.
- The HTTP receipts contain 40 distinct response IDs for the same ordered 20 evaluation row IDs, once for `base` and once for `fixture`. The model listing binds the adapter to `/work/attempt-01/adapter`. Every response finished with `stop`; all 40 corresponding POST log entries have HTTP200. Exact-JSON flags were recomputed from response content.

## Recorded result

| Measurement | Base | Adapter |
|---|---:|---:|
| NeMo-loaded evaluation exact JSON | 0/20 | 20/20 |
| Mean target NLL | 2.290144020318985 | 0.0000027318667491726956 |
| vLLM HTTP exact JSON | 0/20 | 20/20 |

All 20 base-to-adapter output pairs differ in both evaluation paths. The actual HF and vLLM output texts agree for all 20 base pairs and all 20 adapter pairs; that is an observation of this attempt, not a general parity guarantee. Training loss fell from 2.000029969215393 on step 1 to 0.0000033144783401439782 on step 20.

The 200 training rows contain **60 distinct prompt contents drawn from six source cases**. The 20 evaluation rows contain **six distinct prompt contents**, with source-case multiplicities 4, 4, 3, 3, 3, 3. Every evaluation source case occurs in training; all rows belong to `fixture-family`. Prompts supply lifecycle, repair, and gate metadata, and the system prompt explains the requested label mapping. These measurements demonstrate fixture metadata mapping and adapter plumbing. They establish no independent scientific generalization or physical prediction.

## Runtime and resource record

The implementation is **NeMo AutoModel-loaded model plus explicit PyTorch/HF-PEFT SFT**, not execution of NeMo's `train_ft` recipe. The base is `Qwen/Qwen3-4B-Instruct-2507` revision `cdbee75f17c01a7cc42f958dc650907174af0554`. The Apache-2.0 license bytes were independently checked; all 13 model-file hashes agree between the model download manifest and execution inputs.

| Stage | Runtime identity | Charged container seconds |
|---|---|---:|
| Train | NeMo 0.5.0; torch 2.13.0a0+8145d630e8.nv26.06; CUDA 13.3; PEFT 0.18.1; transformers 5.12.1 | 67.27139592099411 |
| Fresh reload/evaluate | Same pinned NeMo image and package versions | 61.15560599700257 |
| Serve | vLLM 0.33.0rc1.dev157+gedad8b03c; torch 2.14.0+cu130; CUDA 13.0; transformers 5.20.2 | 185.7625366870052 |

NeMo image pin: `nvcr.io/nvidia/nemo-automodel@sha256:70b4e9df8dd23ef451372b25952cffe24ad29c17f5b9de5fd1b244caf4e7b55a`.

vLLM image ID: `sha256:2e735ffeef26457f8a3ff44a62ae182870b10af37adc06ecbb08baca152365c6`. Root's separate Docker `RepoDigests` receipt records `vllm/vllm-openai@sha256:2e735ffeef26457f8a3ff44a62ae182870b10af37adc06ecbb08baca152365c6`, matching that ID. This is a host-cache provenance receipt, not an independent registry revalidation. Driver **580.178.04** is linked from the earlier host runtime-preflight receipt. The two runtime CUDA versions should both remain in the evidence record.

The actual three-stage charge is **314.18953860500187 seconds**. Adding the explicitly conservative **180-second** reservation for earlier primitive checks yields **494.18953860500187 seconds (8.236492310083365 minutes)**, below 60 minutes. The 180 seconds is not a measured historical usage claim. This is attempt 1 of at most 3; it completed at **2026-10-31T07:53:46.147370Z**, before the 10:00Z deadline. Stage charges cover launch through confirmed stop; the slight difference from 314.412842 seconds of attempt wall time is consistent with post-stop log archival and removal.

The supervisor success path confirms each owned container stopped before removing it. The final state has `active: null`, no cleanup errors, and one completed attempt; the remote archive receipt asserts no owned running containers. Serving logs record shutdown completion. The retained warnings include vLLM forcing its EngineCore child to stop and a semaphore cleanup warning during shutdown; the stage exits zero and the evidence does not indicate a remaining owned container. This reviewer did not independently inspect the host or listening port.

## Evidence limits and follow-up boundary

The 8.06GB base-model weights are not included in this local 31-file bundle. Their hashes were checked for consistency with the downloaded manifest and prelaunch supervisor gate, rather than rehashed from local weight bytes by this audit. The claimed 504 changed tensors and exact fresh-reload equality are assertions of the exact reviewed runtime corroborated by exit-zero receipts; no before-training checkpoint or independent dump of reloaded memory was retained. The saved tensor bytes themselves were independently inspected and hashed.

The HTTP script binds the frozen evaluation file and preserves all row IDs and responses, but does not retain raw request bodies separately. The same-prompt assertion therefore uses the exact script plus frozen data and receipts. All source and result evidence remains available for review without replaying the GPU workload.

This result does not complete the CLI/MCP `gb10 preflight|status` wrapper follow-up, any ARM/x86 HotSpot comparison, SLAB-019 real-data eligibility or execution approval, or downstream scientific/model claims. No further attempt is needed to demonstrate this fixture sequence. Warden remains the evidence-PR reviewer and authority for downstream gates.

Audit outputs: `ARTIFACT-AUDIT.json` contains all 112 check outcomes and computed metrics; `TENSOR-BYTE-HASHES.json` contains the 504 per-tensor byte hashes; `AUDITED-FILE-HASHES.json` contains the inspected payload inventory and fixture hashes. `audit_artifacts.py` is the standalone standard-library audit implementation.
