# Nebius and our GB10 worker: what we can do before Sun 2026-11-01 18:00Z

Research by a forge subagent, 2026-10-31, 15:00–16:30Z. It was read-only: no account created, no key requested, nothing posted.

**Question (Carter):** "look for anything we can do with Nebius with our worker on GB10".

**Tags:**
- **[OFFICIAL]**: fetched on 10-31 from a Nebius, NVIDIA or ScienceClaw page.
- **[OFFICIAL-SNIPPET]**: an official page, seen only through a search-engine snippet.
- **[THIRD-PARTY]**: a non-official source.
- **[INTERNAL]**: our repo or room notes.
- **[COMPUTED]**: my arithmetic from quoted prices.
- **[INFERRED]**: my reasoning; nothing states it.
- **[UNVERIFIED]**: a claim I could not confirm.

---

## 0. Bottom line

1. **Nebius IS a ScienceClaw sponsor.** It sits in the "Builder" tier, as a logo only. The site names no Nebius prize, track, credits or GPUs. [OFFICIAL] https://scienceclawhack.ai/
2. **There is no Nebius + DGX Spark product tie-in.** The natural story is edge plus cloud:
   - GB10 runs our small Qwen3-4B + LoRA worker on site.
   - Nebius Token Factory serves large open models over an OpenAI-compatible API, paid per token. Examples: Qwen3-235B (same family as our worker), NVIDIA Nemotron, DeepSeek.
3. **Best move:** add one or two Token Factory "cloud labs" to the SLAB-052 proposal harness next to the GB10 edge lab. Give them equal signed slot budgets, the same oracle and the same ledger.
   - Model cost is about **$0.48–$9.24 per 1,000 calls** at 4k input / 1k output tokens each. [COMPUTED, §3.1]
4. **Not feasible by the deadline:**
   - Nebius LoRA fine-tuning of our exact base. Qwen3-4B-Instruct-2507 is not on the tunable list, and a third party saw an 11-hour queue.
   - Serving our adapter on Token Factory. Custom weights are "beta and available on request".
5. **Privacy:**
   - Nebius says it does not train on API content.
   - By default it MAY store prompts and outputs in Finland for speculative decoding.
   - Turn on **Zero Data Retention** (an org-wide toggle) before sending anything. [OFFICIAL, §4]

---

## 1. Is Nebius a sponsor? Hackathon facts

### 1.1 ScienceClaw (our event)

| Fact | Source |
|---|---|
| ScienceClaw, MIT Media Lab, Oct 30 – Nov 1 2026, in person, teams of 2–5. | [OFFICIAL] https://scienceclawhack.ai/ |
| Sponsor tiers: **Platform:** NVIDIA. **Builder:** Claude, Formlabs, **Nebius**, Edison, Stifel, Google Cloud. **Supporter:** OpenAI, Romix, alphaXiv, MIT SoE, LILA. | [OFFICIAL] same page. "Nebius" appears once, as logo alt text linking to nebius.com. |
| Nebius's contribution is not stated anywhere on the site. No Nebius prize or track. | [OFFICIAL] same page |
| Compute: "Shared compute and model resources may be available for project work … allocated based on project needs, technical fit, and availability." | [OFFICIAL] same page |
| Prizes: E14 $50K SAFE, **three NVIDIA DGX Sparks**, Formlabs Form Studio 1, $500 alphaXiv OpenResearch GPU credits, "with more to be announced". "There is one overall competition, rather than separate tracks." | [OFFICIAL] same page |
| Rubric: Problem 20%, Scientific/Technical Impact 25%, **Decentralized Agency 20%**, **Collective Capability 25%**, Execution & Validation 10%, plus a **Collaboration Bonus of up to +10** (e.g. "A tool or agent successfully reused by another team"). "ScienceClaw is model- and framework-agnostic." No criterion rewards sponsor usage. | [OFFICIAL] same page |
| Luma event page: no sponsors listed, no Nebius. | [OFFICIAL] https://luma.com/event/evt-lrhAXSeA3Dq8uSI |
| Our Source B says "Treat the **16 H100s as a shared event pool**", and its sponsor table says "**Nebius** – Request the H100 allocation; retain training and runtime evidence for its sponsor submission." This came from an onsite transcript and is **not on the official site**. | [INTERNAL, UNVERIFIED] `H:/sentilab/docs/sentilab/draft-0.5/sources/source-b.txt:334,414`; PLAN.md: "Nebius confirmed H100 allocation only if approved" |
| Source B also says the third DGX Spark is a general NVIDIA-platform award, and that NVIDIA wants "meaningful use of their software higher in the stack". | [INTERNAL, UNVERIFIED] source-b.txt (top) |

### 1.2 Other Nebius hackathons (precedent only; none is usable now)

| Event | Nebius role / DGX Spark link | Status | Source |
|---|---|---|---|
| Nebius x NVIDIA Global AI Hackathon (Devpost, online) | Projects must run on Token Factory or AI Cloud and use at least one NVIDIA open model. Prizes: $20K / $10K / $6K, $3K Best Use of Tavily, Jetson Orin Nano category prizes, $500 city awards. | **Closed.** Nebius on X: "Submissions close Oct 30th". | [OFFICIAL] https://x.com/nebiusai/status/2107168602160001198. Rules page returned 403 to my fetcher, so the details are [OFFICIAL-SNIPPET/THIRD-PARTY]: https://nebiusglobalaihackathon.devpost.com/rules |
| Nebius Build Week Hackathon (with NVIDIA), Berlin | Tracks: Cloud & Serverless, Apps & Agentic AI, Vertical AI. NVIDIA Nemotron via Token Factory challenge. No DGX Spark mentioned. | Past (Oct 18 2026) | [OFFICIAL] https://nebius.com/events/nebius-nvidia-ai-builders-hackathon |
| NVIDIA Hack for Impact – London | "Cloud Compute Sponsor: Nebius". "every team" gets "a DGX Spark or ZGX Nano AI Station" (GB10). The page doesn't say what Nebius provided. | Registration closed; no date shown | [OFFICIAL] https://luma.com/NVIDIA-Hack-London. **The closest precedent for Nebius cloud plus GB10 at one event.** |
| BuilderShip (SF, June 2026) | Nebius co-host. Winner got "$50K in cloud credits and a DGX Spark". "Every builder gets GPU credits, Token Factory inference keys". Its sponsor-stack rubric: "One API call is 2; meaningful integration across services is 8+". | Past | [THIRD-PARTY summary of an official X post and ship.builders, UNVERIFIED] https://x.com/nebiusai/status/2061545520141660304, https://ship.builders/ |
| 2026 Nebius Physical AI Awards | 5 × $150K compute credits. Minimum $1M raised. | Closed: Oct 25 per later sources, Sept 30 per early ones. Winners Nov 18. | [THIRD-PARTY] https://www.marktechpost.com/2026/09/29/nebius-opens-2026-physical-ai-awards-five-150k-compute-prizes/; [OFFICIAL] https://nebius.com/robotics-physical-ai-awards |

### 1.3 Nebius + NVIDIA / DGX Spark tie-ins

- **No direct DGX Spark product link found.** I searched "Nebius DGX Spark", "Nebius GB10", Lepton and Spark plus Token Factory.
- Nebius was a launch partner of NVIDIA DGX Cloud Lepton (Computex, May 2025), listed among the NVIDIA Cloud Partners. [OFFICIAL-SNIPPET] https://nvidianews.nvidia.com/news/nvidia-announces-dgx-cloud-lepton-to-connect-developers-to-nvidias-global-compute-ecosystem
  - DCD reports that NVIDIA scaled back DGX Cloud. [THIRD-PARTY] https://www.datacenterdynamics.com/en/news/nvidia-pulls-back-on-its-own-cloud-platform-report/
- Token Factory serves the NVIDIA Nemotron family (§2.1). The Builder Program offers an "NVIDIA x Nebius certification for $1". [OFFICIAL] https://dev.nebius.com/builders
- **Name clash:** Rafay's "Token Factory" runs on DGX Spark. It belongs to Rafay, not Nebius; don't cite it as a Nebius tie-in. [THIRD-PARTY] https://rafay.co/ai-and-cloud-native-blog/serving-llms-on-arm-running-rafay-token-factory-on-nvidia-dgx-spark

---

## 2. What Nebius offers right now

### 2.1 Token Factory (formerly "Nebius AI Studio")

**API**
- Base URL `https://api.tokenfactory.nebius.com/v1/`, with a bearer key from env `NEBIUS_API_KEY`. The OpenAI SDK works by changing the base URL. [OFFICIAL] https://docs.tokenfactory.nebius.com/quickstart.md
- Paths in the official OpenAPI spec: `/v1/chat/completions`, `/v1/completions`, `/v1/responses`, `/v1/embeddings`, `/v1/rerank`, `GET /v1/models`, `/v1/files`, `/v1/fine_tuning/jobs` (plus `/events`, `/checkpoints`), `/v0/dedicated_endpoints`, `/v1/datasets`, `/v1/operations`. [OFFICIAL] https://api.tokenfactory.nebius.com/openapi.json
  - Operation types include `batch_inference`, `finetuning` and `merge`.
  - **There is no `/v1/batches` path.**
- `GET /v1/models` returns 401 without a key ("token is not present"). I checked this directly.

**Structured output**
- `response_format` accepts `{"type":"json_schema",…}` (strict) or `{"type":"json_object"}`.
- "Some models are better in providing JSON"; choose models tagged **"JSON mode"**. [OFFICIAL] https://docs.tokenfactory.nebius.com/ai-models-inference/json.md

**Flavors**
- The docs describe Base and Fast flavors, with Fast selected by appending `-fast`. [OFFICIAL] https://docs.tokenfactory.nebius.com/ai-models-inference/overview.md
- However, **today's public catalog lists only one flavor per model, labelled "cheap"** (30/30 rows). [OFFICIAL JSON, below]

**Signup and billing**
- Log in with Google or GitHub.
- "Billing setup is mandatory—you cannot complete onboarding without it". A bank card is debited in real time.
- Promo codes give free credits ("typically issued as part of a special offer"). They expire and "cannot be used to pay outstanding invoices".
- **To redeem:** balance → **Top up** → **With promo code**.
- [OFFICIAL] https://docs.tokenfactory.nebius.com/other-capabilities/billing-new.md

**Rate limits**
- Per-model defaults are shown in the console.
- The docs' illustrative base is **60 RPM / 400,000 TPM**. At ≥80% use, limits rise ×1.2 per 15-minute bucket, up to 20× the base. Over the limit returns HTTP 429.
- The Batch API "has significantly higher limits".
- [OFFICIAL] https://docs.tokenfactory.nebius.com/ai-models-inference/rate-limits.md

**Model catalog**

Source: the official machine-readable catalog https://tokenfactory.nebius.com/api/public/models_info, fetched 16:00Z 10-31, sha256 `35cd5966…7cc5219d`. https://tokenfactory.nebius.com/model-catalog.md calls it "the authoritative machine-readable source". It lists 30 public models: 29 `active` and `moonshotai/Kimi-K3` in status `error` at fetch time. [OFFICIAL]

| Model ID | Region | tok/s | Quant | Context | $ per 1M tokens (in / cached in / out) | License | Notes |
|---|---|---|---|---|---|---|---|
| `Qwen/Qwen3-235B-A22B-Instruct-2507` | eu-north1 | 27 | fp8 | 262K | 0.20 / 0.05 / 0.60 | Apache 2.0 | "JSON mode". Same family as our 4B worker. **Leaves serverless Nov 9 2026.** |
| `Qwen/Qwen3-30B-A3B-Instruct-2507` | eu-north1 | 70 | fp8 | 262K | 0.10 / 0.10 / 0.30 | Apache 2.0 | "JSON mode". Nebius's named replacement for the 235B. |
| `nvidia/Nemotron-3_5-Lightning` | eu-north1 | 314 | bf16 | 1M | 0.06 / 0.03 / 0.24 | OpenMDW v1.1 | NVIDIA open model. No "JSON mode" tag. |
| `nvidia/Nemotron-3.5-Super-VL` | us-north1 | 282 | bf16 | 1M | 0.30 / 0.06 / 0.90 | OpenMDW-1.1 | Vision. |
| `nvidia/Nemotron-3-Ultra-550b-a55b` | us-central1 | 523 | fp4 | 1M | 1.00 / 0.12 / 3.00 | OpenMDW-1.1 | Largest NVIDIA model on the list. |
| `openai/gpt-oss-120b` | eu-north1 | 40 | fp4 | 131K | 0.15 / 0.10 / 0.60 | Apache 2.0 | "JSON mode". |
| `deepseek-ai/DeepSeek-V4-Pro-0813` | uk-south1 | 37 | fp8 | 979K | 1.32 / 0.04 / 3.96 | MIT | |
| `deepseek-ai/DeepSeek-V4-Flash-0731` | us-central1 | 351 | fp8 | 1M | 0.14 / 0.01 / 0.28 | MIT | "JSON mode". |

- **Cross-check:** a Nebius cookbook "checked on October 15, 2026" lists Qwen3-30B-A3B-Instruct-2507 at $0.10 / $0.30 and Kimi K3 at $3.00 / $15.00. These match the JSON. [OFFICIAL] https://dev.nebius.com/cookbook/opencode-nebius-token-factory
- **Removals from serverless on Nov 9 2026** (after the event), with Nebius's suggested replacements [OFFICIAL] https://docs.tokenfactory.nebius.com/model-deprecations-november-2026.md:
  - Qwen3-235B-A22B-Instruct-2507 → Qwen3-30B-A3B-Instruct-2507
  - NVIDIA-Nemotron-3-Nano-30B-A3B → Nemotron-3_5-Lightning
  - nemotron-3-super-120b-a12b → Nemotron-3.5-Super-VL
  - DeepSeek-V4-Pro → V4-Pro-0813
  - Kimi-K2.6 → Kimi-K3
  - plus others
- **Reproducibility consequence:** anyone re-running our signed log after Nov 9 cannot query the 235B serverless model again. [INFERRED]

**Batch inference**
- "Batch inference is available at **half the real-time price** for async and data processing workloads." [OFFICIAL] https://nebius.com/solutions/inference
- API: `POST /v1/operations` with type `batch_inference`. Its parameters require `model` and `completion_window` (example `"12h"`). [OFFICIAL openapi.json]
- The docs page `data-lab/batch-inference` returns 404 today.
- The completion window makes batch useless for live labs. It could only serve an offline sweep. [INFERRED]

**Fine-tuning (LoRA and full)** [OFFICIAL] https://docs.tokenfactory.nebius.com/post-training/how-to-fine-tune.md
- Flow: upload `POST /v1/files` (`purpose=fine-tune`), then create `POST /v1/fine_tuning/jobs`.
- Hyperparameters and defaults:
  - `lora` defaults to **false**, which means a full fine-tune.
  - `lora_r` 8–128 (default 8); `lora_alpha` ≥ 8; `lora_dropout`.
  - `n_epochs` 1–20 (default 3); `batch_size` default 8; `learning_rate` default 1e-5.
  - `context_length` default 8192; `packing` default true.
- Checkpoints: `GET …/jobs/{id}/checkpoints` gives `result_files`; download each with `GET /v1/files/{id}/content`.
- Dataset format: JSONL with a `messages` list ending in an assistant turn. `tools` and `prompt/completion`, `text` or pretokenized formats are also accepted. The size limit is 20 GB via the Files API. [OFFICIAL] https://docs.tokenfactory.nebius.com/post-training/datasets.md

**Fine-tuning: tunable models** [OFFICIAL] https://docs.tokenfactory.nebius.com/post-training/models.md
- The only Qwen3 4B options are `Qwen/Qwen3-4B` and `Qwen/Qwen3-4B-Base`. **`Qwen3-4B-Instruct-2507` (our GB10 base) is not listed.**
- No NVIDIA model is tunable.
- The 30B-A3B and 235B-A22B Instruct-2507 models are tunable with LoRA or full fine-tuning.

**Fine-tuning: serving tuned models**
- "Deployment options currently only include via Dedicated endpoints." [OFFICIAL, same page]
- "Working with custom model weights is currently in beta and available on request" through Support. [OFFICIAL] https://docs.tokenfactory.nebius.com/ai-models-inference/dedicated-endpoints/custom-weights.md
- Older cookbook notebooks show a one-click serverless LoRA deploy. Current docs and the field report below contradict this. [OFFICIAL vs THIRD-PARTY]

**Fine-tuning: price and field report**
- The docs publish no price, and the pricing page is JS-only.
- **Field report from Oct 26–27 2026** (third party; job `ftjob-5c66…`). [THIRD-PARTY] https://github.com/gibouu/understudy/pull/126
  - "US$2.8 per 1M tokens (the console's price for this model up to 32K context)" for a Qwen3-30B-A3B-Instruct-2507 LoRA.
  - "waited 11 hours in a queue, then trained 40 steps in 49 minutes".
  - A 422 error: "at least 131,072 tokens a batch (batch size x context length)".
  - "the checkpoint id answers 404 on the serverless API".
  - The cookbook's `/v0/models` route returned 404.
  - Endpoint creation returned a 422: "custom_weights_id must start with 'model-artifact_'".
- A May 2025 Nebius blog quoted $0.40 per 1M tokens for models under 20B. [THIRD-PARTY via search; probably stale]
- **The current price for Qwen3-4B is UNVERIFIED.**

**Other Token Factory services**
- Dedicated endpoints: "Per GPU/hour, billed with per-minute granularity", fixed user-selected region. No public prices. [OFFICIAL] https://docs.tokenfactory.nebius.com/ai-models-inference/dedicated-endpoints/overview.md
- Sandboxes (ConTree code execution): "in Beta, please request access". **Not usable by Sunday.** [OFFICIAL] https://docs.tokenfactory.nebius.com/sandboxes/overview.md

### 2.2 Nebius AI Cloud (VMs, serverless jobs and endpoints, managed services)

GPU prices are per GPU-hour on-demand, with the listed vCPU and RAM included. [OFFICIAL] https://nebius.com/prices and https://docs.nebius.com/compute/resources/pricing

| GPU | On-demand | Preemptible ("from") | Regions (docs) |
|---|---|---|---|
| GB300 NVL72 / **GB200 NVL72** | price on request ("Contact us"), sales-led | – | – |
| HGX B300 | $9.50 | $0.99 | uk-south1, eu-west2, us-north1 |
| HGX **B200** | $8.50 | $0.99 | us-central1, me-west1 |
| HGX **H200** | $5.40 | $0.79 | eu-north1, eu-north2, eu-west1, us-central1 |
| HGX **H100** | $4.50 | $0.79 | eu-north1 |
| RTX PRO 6000 | $1.80 | $0.79 | us-central1, uk-south2, eu-south1 |
| L40S | from $1.55 (Intel) / from $1.82 (AMD), CPU and RAM included | from $0.74 / $0.90 | eu-north1 |

**CPU-only VMs** [OFFICIAL docs]
- AMD EPYC Genoa: $0.015 per vCPU-h plus $0.0045 per GiB-h, in every region.
- Intel Ice Lake: $0.012 per vCPU-h plus $0.0045 per GiB-h, eu-north1 only.
- Equivalent: nebius.com/prices shows "from $0.13" and "from $0.06".
- `cpu-d3` is most likely Genoa, since it is the platform available outside eu-north1. [INFERRED]

**Billing terms** [OFFICIAL]
- Spot prices can change "as frequently as every 15 minutes". The spot maximum is always $0.01 below on-demand.
- Billing is per second. Egress, ingress and public IPs are free.
- Managed Kubernetes and Soperator (Slurm) carry no fee.
- "There is a minimum amount for the first payment, which is $25".
- "A promo code grants you free credits for using Nebius AI Cloud resources."

**Price history:** on Oct 1 2026, H100 went $3.85→$4.50, H200 $4.50→$5.40, B200 $7.15→$8.50 and B300 $7.85→$9.50. [THIRD-PARTY] https://www.usagepricing.com/blueprint/activity/nebius-ai-2026-09-24-gpu-price-increase

**Quotas**
- Defaults are set per region, and you can request increases. [OFFICIAL-SNIPPET] https://docs.nebius.com/overview/quotas
- The changelog says new tenants need a quota raise before using some GPU types in us-central1. [OFFICIAL-SNIPPET] https://docs.nebius.com/changelog
- **A fresh account may not get GPUs immediately.** [INFERRED]

**Serverless AI**
- Jobs: `nebius ai job create`, which auto-terminates. Endpoints: `nebius ai endpoint create`.
- CPU platform `cpu-d3` with preset `4vcpu-16gb` is valid for jobs.
- Endpoints in the vLLM recipe serve over **plain HTTP**, with a bearer token you generate.
- [OFFICIAL] https://github.com/nebius/serverless-ai-cookbook, https://github.com/nebius/skills/blob/main/skills/nebius-serverless-jobs/SKILL.md, https://raw.githubusercontent.com/nebius/serverless-ai-cookbook/main/inference/vllm-endpoint/README.md

**Managed MLflow**
- The `medium` cluster has 8 vCPU and 32 GiB: 8 × $0.03 + 32 × $0.0075 = **$0.48/h**.
- Its 200 GiB disk costs $14.20 per 730 h. Artifacts are billed at Object Storage rates.
- **Not useful for us this weekend.** [OFFICIAL] https://docs.nebius.com/mlflow/resources/pricing

### 2.3 Credit programmes

| Programme | What you get | Who can get it | Source |
|---|---|---|---|
| **AI Builder Program** | "**$25 Token Factory credit**", plus Tavily $25, LangSmith $100, Toloka $100 (the FAQ says $50 + $50 Tendem) and a $1 NVIDIA x Nebius certification. "primarily intended for learning, testing, and experimentation". | "free to join for everyone". Sign up, then verify email. | [OFFICIAL] https://dev.nebius.com/builders, https://nebius.com/blog/posts/introducing-the-nebius-ai-builder-program (Sept 10 2026) |
| Token Factory / AI Cloud promo codes | Free credits | "issued as part of a special offer". **Ask the Nebius rep onsite.** | [OFFICIAL] billing doc; nebius.com/prices FAQ |
| Nebius for Startups | Credits through approved VC partners only, $5M+ raised; waitlist | Not us now | [OFFICIAL] https://nebius.com/startups |
| Research grants | Discretionary | Apply | [OFFICIAL-SNIPPET] https://nebius.com/nebius-research-grants |
| Automatic signup credit | None found in the current docs. A third party says the $1 trial credit was removed in early October and that credits expire after 90 days. | – | [THIRD-PARTY, UNVERIFIED] https://startupperks.co/programs/nebius-token-factory-trial-credit |

---

## 3. Integrations, ranked

| Rank | Option | Effort | Impact | Feasible by Sun 18:00Z? |
|---|---|---|---|---|
| **1** | (a) Token Factory **cloud labs** (Qwen3-235B/30B, Nemotron) next to the GB10 edge lab in the SLAB-052 harness | Medium: a transport of about 60 lines plus tests and admission | **High:** Collective Capability 25%, Decentralized Agency 20%, sponsor plus NVIDIA-model story | **Yes**, if account, key, approval and +1s land by about Sat 22:00Z |
| **2** | **Ask Nebius onsite:** promo code, the rumored H100 pool, any Nebius prize | ~0 | **Enabler:** makes #1 free and decides #4 | Yes, now |
| **3** | (d) Help-room helper agent on a Nebius route | Low for an OpenAI-SDK helper; Codex compatibility unknown | Low–medium: visible sponsor usage; the collaboration bonus only if other teams actually use it | Yes |
| 4 | Cross-platform reproduction: run the same NeMo LoRA recipe on a Nebius H100, then serve and score on GB10 | Medium–high | Medium: rigor for Execution & Validation | Only if #2 confirms GPUs |
| 5 | (c) Burst HotSpot to Nebius CPU | Medium | Low: HotSpot is CPU work, and we already have Azure | Only on a **measured** solver bottleneck |
| 6 | (b) Fine-tune on Nebius and serve on GB10, or the reverse | High | Low for this event | **No** (§3.6) |

### 3.1 (a) Cloud labs next to the GB10 edge lab (rank 1)

**Design** [INTERNAL code read at sentilab@1bdf584; the rest INFERRED]

**Labs**
| Lab | Model | Notes |
|---|---|---|
| `gb10-qwen4b-lora` | Our vLLM server on GB10 | Already exists |
| `nebius-qwen235b` | `Qwen/Qwen3-235B-A22B-Instruct-2507` | Same family, about 59× the parameters |
| `nebius-nemotron` | `nvidia/Nemotron-3_5-Lightning` or `nvidia/Nemotron-3-Ultra-550b-a55b` | An NVIDIA open model |
| *(optional)* | `Qwen/Qwen3-30B-A3B-Instruct-2507` | Instead of the 235B, if post-event reproducibility matters (the 235B leaves serverless Nov 9) |

**How it fits the harness**
- **Lab IDs:** SLAB-052 `ProposalLab` accepts any lab_id matching `[a-z0-9][a-z0-9_-]{0,63}` (`proposals.py:100-115`, `envelope.py:26`). All three IDs above are valid. The older leads/dispatch path hard-codes `FAMILIES = ("openai", "claude", "grok", "kimi")` (`labs.py:16`), so use the SLAB-052 path, or add a family through review.
- **Equal budgets:** each lab gets the same `PublicProblem`, an equal `solve_budget` and only its own last 16 receipts. That is the "isolated, equal, signed lab budgets" design (`docs/sentilab/evidence/SLAB-052/HARNESS.md`).
- **Arms:**
  - Arm E: edge-only (GB10 lab alone).
  - Arm E+C: edge plus the cloud labs.
  - Both arms use the same total oracle slots. This is the "multi-agent vs single-agent / collaborative vs isolated" comparison the rubric asks for.
- **Freeze caveat:** if the SLAB-041 freeze already fixed the lab list (32 slots), cloud labs can only run as a separately labelled exploratory arm. Adding them is a scientific scope change for Carter and the +1 reviewers. [INFERRED]
- **Benchmark caveat:** a stronger proposer can only show a gain on a benchmark with headroom. Ascend910 is nearly flat; micro150 has about 21 C of room. See `forge-research/FORGE-FINDINGS.md` Claim 2. [INTERNAL]

**Step 1: admission probe.** `GET /v1/models` is a list call. I assume it is non-billable, as `probe.py` requires; that is [INFERRED], since Nebius bills per token.

```bash
resp=$(curl -sS -w '\n%{http_code}' -H "Authorization: Bearer $NEBIUS_API_KEY" \
       https://api.tokenfactory.nebius.com/v1/models)
code=${resp##*$'\n'}; body=${resp%$'\n'*}
printf '%s' "$body" | jq --argjson c "$code" '{status_code: $c, data: [.data[] | {id}]}' \
 | python -m sentilab_core.probe --provider nebius-token-factory \
     --entitlement-source nebius-promo-<ref-or-card-ref> --output admission/probe-nebius.json
```

**Step 2: admission record.** Fill the `AdmissionRecord` fields from `admission.py:99-117`:
- `provider` = `nebius-token-factory`
- `model_id` = `Qwen/Qwen3-235B-A22B-Instruct-2507`
- `model_version`: pin it to the catalog row, e.g. `tf-catalog-2026-10-31:fp8:eu-north1`.
  - Nebius exposes no weights revision through the API, so hash the `models_info` row and re-fetch it before each run to detect drift. [INFERRED]
- `roles` = `["lead"]`, plus `judge` for a reviewer lab.
- `input_usd_per_million` = `0.20`, `output_usd_per_million` = `0.60`. Re-read these from the catalog at approval time.
- `payer`, `entitlement_source`, `approver`, `approval_ref`, `arm_cap_usd`, `run_cap_usd`, `expires_at`: owner fields.

All IDs must match `[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}` and must not be credential-like (`admission.py:24,60-65`). The Nebius model IDs above pass.

**Step 3: transport.** This is a sketch of the `model_calls.py` contract, which requires "MUST honor both total token ceilings, the pinned provider/version, and make at most one request (no retry)".

```python
import json, os
from openai import AsyncOpenAI

def nebius_transport(model_id: str, system_prompts: dict, timeout_s: float = 120.0):
    client = AsyncOpenAI(base_url="https://api.tokenfactory.nebius.com/v1/",
                         api_key=os.environ["NEBIUS_API_KEY"],
                         max_retries=0,          # SDK default retries would break "at most one request"
                         timeout=timeout_s)
    async def transport(call):                   # call: sentilab_core.model_calls.ModelCall
        resp = await client.chat.completions.create(
            model=model_id,
            messages=[{"role": "system", "content": system_prompts[call.operation]},
                      {"role": "user", "content": call.request_json.decode()}],
            max_tokens=call.output_tokens,       # output ceiling enforced server-side
            temperature=0.6, seed=7,             # record both in the ledger
            response_format={"type": "json_object"},  # json_schema for "JSON mode" models
        )
        u = resp.usage
        if u.prompt_tokens > call.input_tokens or u.completion_tokens > call.output_tokens:
            raise RuntimeError("provider usage exceeded admitted ceiling")  # spend already metered at ceiling
        return json.loads(resp.choices[0].message.content)  # must validate as lab-proposal/1 (labs.validate_message)
    return transport
```

- The GB10 edge lab uses the same function with `base_url=http://127.0.0.1:8000/v1` and the LoRA module name as `model_id`.
  - Only astra's PC reaches the GB10 (`ssh gb10`), so the generating host needs a tunnel. [INTERNAL]
  - Warm up GB10 vLLM first. Its cold first request takes about 35 s, so an edge slot would otherwise be lost to a timeout.
- The return shape is assumed from `fixtures/labs/openai.json` (`lab-proposal/1` with `geometry[{id,x_mm,y_mm}]`); confirm against `labs.py:54-75`.
- `seed` is assumed accepted, because the API "Supports the full set of vLLM parameters". [OFFICIAL overview; seed effect UNVERIFIED]
- Nemotron models carry no "JSON mode" tag in the catalog. Their schema adherence is **UNVERIFIED**; the harness rejects schema errors before admission without charging a slot.

**Step 4: smoke test.** Billable, a fraction of a cent.

```bash
curl -sS https://api.tokenfactory.nebius.com/v1/chat/completions \
  -H "Authorization: Bearer $NEBIUS_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"Qwen/Qwen3-235B-A22B-Instruct-2507","max_tokens":32,
       "response_format":{"type":"json_object"},
       "messages":[{"role":"user","content":"Return {\"ok\": true} as JSON."}]}'
```

**Cost and latency per call** [COMPUTED], assuming 4,000 input and 1,000 output tokens per call, at catalog prices and tok/s:

| Model | $ per call | $ per 1,000 calls | Output time at catalog tok/s |
|---|---|---|---|
| Nemotron-3_5-Lightning | $0.00048 | $0.48 | ~3 s |
| Qwen3-30B-2507 | $0.0007 | $0.70 | ~14 s |
| gpt-oss-120b | $0.0012 | $1.20 | ~25 s |
| Qwen3-235B-2507 | $0.0014 | $1.40 | ~37 s |
| Nemotron-3-Ultra | $0.007 | $7.00 | ~2 s |
| DeepSeek-V4-Pro-0813 | $0.00924 | $9.24 | ~27 s |

- The $25 Builder credit covers thousands of calls.
- Reasoning models can emit far more output tokens, so always set `max_tokens`.

### 3.2 Ask Nebius onsite (rank 2)

**Ask the Nebius rep** at the MIT Media Lab, or the organizers (scienceclaw@mit.edu / Discord):
1. Is there a Token Factory or AI Cloud **promo code** for ScienceClaw teams? Promo codes are a documented mechanism.
2. Is the "16 H100 shared pool" from Source B Nebius-provided, and how do we get access (a project or tenant invite)?
3. Is there a **Nebius prize** among the "more to be announced"?

**Fallback:** the Builder Program's $25 Token Factory credit. Signup is free, but **Token Factory still requires a card on file**.

### 3.3 (d) Help-room helper agent on a Nebius model route (rank 3)

- **OpenAI-SDK-based helper:** no code change. The OpenAI SDK reads these two env vars.
  ```bash
  export OPENAI_BASE_URL=https://api.tokenfactory.nebius.com/v1
  export OPENAI_API_KEY="$NEBIUS_API_KEY"
  ```
  - Model: `Qwen/Qwen3-30B-A3B-Instruct-2507` ($0.10 / $0.30, 70 tok/s, function_calling and responses_api use-cases).
  - Or `nvidia/Nemotron-3_5-Lightning` ($0.06 / $0.24, 314 tok/s).
- **Codex-based box (mint):** Codex now accepts only `wire_api = "responses"`; chat was removed. [THIRD-PARTY] https://github.com/openai/codex/discussions/7782
  - Nebius serves `POST /v1/responses` with `tools` (function) and `stream`. [OFFICIAL] https://docs.tokenfactory.nebius.com/api-reference/inference/create-a-response.md
  - Put this in the **user-level** `~/.codex/config.toml`; Codex drops provider keys from project config:
  ```toml
  model_provider = "nebius"
  model = "Qwen/Qwen3-30B-A3B-Instruct-2507"
  [model_providers.nebius]
  name = "Nebius Token Factory"
  base_url = "https://api.tokenfactory.nebius.com/v1"
  env_key = "NEBIUS_API_KEY"
  wire_api = "responses"
  ```
  - Whether Codex's tool loop works on Nebius's Responses implementation is **UNVERIFIED**. Test once with `codex exec` on a throwaway box before any routing.
  - **Paraphrase the `env_key` line in mint tickets.** The mint refuses `key = …`-shaped lines. [INTERNAL]
  - The mint registry lists Azure Foundry deployments only, so a Nebius route needs this provider block plus the key as a box secret. [INTERNAL memory, verify]
- I did not inspect the help-room helper's implementation. These sketches assume an OpenAI-compatible client.

### 3.4 Conditional: cross-platform reproduction on a Nebius H100 (rank 4)

- **Only if #2 yields GPUs or credits.** One H100 on-demand costs $4.50/h. [OFFICIAL]
- Sketch from the official job flags:
  ```bash
  nebius ai job create --parent-id "$NB_PROJECT" --name slab-sft-h100-repro \
    --image <derived image: nemo-automodel, same tag as the GB10 run, plus run_sft.sh and data> \
    --platform gpu-h100-sxm --preset 1gpu-16vcpu-200gb --timeout 2h \
    --container-command /workspace/run_sft.sh --dry-run
  nebius ai logs "$JOB_ID"
  ```
  - `--args` splits on spaces and can't carry shell one-liners; bake the script into the image. Remove `--dry-run` only after cost approval. [OFFICIAL skill]
- **Architecture caveat:** H100 hosts are x86_64 and GB10 is aarch64, so the image must be the amd64 variant of the same tag. Any byte-level comparison is cross-architecture. [INFERRED]

### 3.5 (c) Burst HotSpot to Nebius CPU (rank 5, only on a measured bottleneck)

- **Cost:** `cpu-d3` `16vcpu-64gb` ≈ 16 × $0.015 + 64 × $0.0045 = **$0.528/h**; `4vcpu-16gb` ≈ **$0.132/h**. [COMPUTED from OFFICIAL unit prices; cpu-d3 = Genoa is INFERRED]
- **Serverless job** [OFFICIAL flags]:
  ```bash
  nebius ai job create --parent-id "$NB_PROJECT" --name hotspot-burst-01 \
    --image cr.eu-north1.nebius.cloud/<registry-id>/sentilab-solver:<sha> \
    --platform cpu-d3 --preset 4vcpu-16gb --timeout 1h \
    --container-command /app/burst.sh --dry-run
  ```
- **VM alternative** [OFFICIAL] https://docs.nebius.com/serverless/tutorials/tts:
  ```bash
  nebius compute disk create --name hs-boot --size-gibibytes 50 --type network_ssd \
    --source-image-family-image-family ubuntu24.04-driverless --block-size-bytes 4096
  nebius compute instance create --name hs-burst-1 --resources-platform cpu-d3 --resources-preset 16vcpu-64gb \
    --boot-disk-existing-disk-id <disk-id> --boot-disk-attach-mode READ_WRITE \
    --network-interfaces '[{"name":"eth0","subnet_id":"<subnet-id>","ip_address":{},"public_ip_address":{}}]' \
    --cloud-init-user-data "$USER_DATA"
  ```
- **Oracle integrity:**
  - A Nebius solver is x86_64. That is the same architecture as the Azure Container App oracle [INTERNAL notes; verify] and a different one from GB10.
  - Never mix architectures inside one oracle identity or arm. Prove bit-identical J on a fixture set first.
  - SLAB-052 allows "one evaluation maximum" per slot. A remote crash after reservation stays charged.
- **Bottom line:** HotSpot needs no GPU, so a GPU burst buys nothing.

### 3.6 (b) Fine-tune on Nebius ↔ serve on GB10 (rank 6, not before the deadline)

**Blockers**
- Our base, Qwen3-4B-Instruct-2507, is **not tunable**. A Nebius adapter would be for `Qwen/Qwen3-4B`, a different base, so GB10 would need a second vLLM base model.
- A third party saw an **11-hour queue**.
- Training price for 4B is **UNVERIFIED**.

**If done after the event**
```bash
curl -sS https://api.tokenfactory.nebius.com/v1/files -H "Authorization: Bearer $NEBIUS_API_KEY" \
  -F purpose=fine-tune -F file=@train.jsonl
curl -sS https://api.tokenfactory.nebius.com/v1/fine_tuning/jobs -H "Authorization: Bearer $NEBIUS_API_KEY" \
  -H "Content-Type: application/json" -d '{"model":"Qwen/Qwen3-4B","training_file":"<file-id>","suffix":"slab",
  "hyperparameters":{"lora":true,"lora_r":16,"lora_alpha":32,"n_epochs":3,"batch_size":16,"context_length":8192}}'
# batch_size 16 x context 8192 = 131,072 tokens, the minimum per batch the third party reported
curl -sS -H "Authorization: Bearer $NEBIUS_API_KEY" \
  https://api.tokenfactory.nebius.com/v1/fine_tuning/jobs/$JOB/checkpoints | jq '.data | max_by(.step_number)'
curl -sS -H "Authorization: Bearer $NEBIUS_API_KEY" https://api.tokenfactory.nebius.com/v1/files/$FID -o meta.json
curl -sS -H "Authorization: Bearer $NEBIUS_API_KEY" https://api.tokenfactory.nebius.com/v1/files/$FID/content \
  -o "ckpt/$(jq -r .filename meta.json)"
```

**Adapter format**
- `adapter_config.json` plus `adapter_model.safetensors`, read with PEFT's `LoraConfig`. [OFFICIAL] https://docs.tokenfactory.nebius.com/post-training/merge-moe-lora-weights.md
- Nebius's merge script expects adapter keys in base-model naming (`model.layers.*.self_attn…`) with **no `base_model.model.` prefix**. [INFERRED from the official script]
- Current vLLM `parse_fine_tuned_lora_name` handles both forms. [OFFICIAL] https://raw.githubusercontent.com/vllm-project/vllm/main/vllm/lora/utils.py
- Older vLLM builds may mis-parse unprefixed keys. **Check the GB10 vLLM version.** [INFERRED]

**Check, then serve on GB10**
```bash
python -I - <<'EOF'
import json; from safetensors import safe_open
c = json.load(open("ckpt/adapter_config.json")); print({k: c.get(k) for k in ("base_model_name_or_path","r","lora_alpha","target_modules")})
with safe_open("ckpt/adapter_model.safetensors", "pt") as f: print(list(f.keys())[:3])
EOF
vllm serve Qwen/Qwen3-4B --port 8001 --enable-lora --max-lora-rank <r from config> \
  --lora-modules nebius-ft=/models/ckpt
```

**Reverse direction: our GB10 adapter on Nebius**
- Token Factory custom weights are beta, through Support.
- The self-serve alternative is a Nebius Serverless **Endpoint** running our own vLLM image plus the adapter, billed per GPU-hour (e.g. L40S from $1.55/h).
  - The cookbook endpoint is **plain HTTP with a bearer token** (`ENDPOINT_URL="http://$ENDPOINT_IP"`), so the token crosses the internet unencrypted. Use a throwaway token or tunnel it. [OFFICIAL recipe; risk INFERRED]

### 3.7 (e) What could score with judges

- **Collective Capability (25%):** show matched arms, E vs E+C, at equal oracle slots. Report best J, charged slots and **USD per accepted improvement per lab** from the signed ledger and metering.
- **Decentralized Agency (20%):** each lab proposes independently through its own bound session. The ledger shows which lab, edge or cloud, originated each accepted layout. No Nebius model reviews its own family's proposals, to avoid self-preference. [INFERRED]
- **NVIDIA general award:**
  - A Nemotron lab adds an NVIDIA open model to the collective, alongside NeMo AutoModel training and vLLM serving on GB10.
  - Whether NVIDIA judges count Nemotron-through-Nebius as "software higher in the stack" is **UNVERIFIED** (Source B).
- **Sponsor credit:**
  - The rubric does not score sponsor usage. [OFFICIAL]
  - Nebius is a Builder sponsor. Claim only measured use: request counts, cost, results. Don't claim "powered by Nebius".
  - BuilderShip's rubric (a different event) gave "One API call is 2; meaningful integration across services is 8+". [THIRD-PARTY] That suggests depth matters more than a single call.
- **One-line pitch:** "GB10 runs our private, always-on 4B student; Nebius serves big open teachers on demand; one deterministic oracle and one signed ledger judge them all."

---

## 4. Data and privacy terms

Source for everything in this section unless noted: [OFFICIAL] https://docs.tokenfactory.nebius.com/legal/legal-quick-guide.md

- **No training:** "Your content is not used to train any models in either mode." "We do not use your content to train, fine-tune or improve any AI models – ours or third parties'."
- **Default retention:**
  - "Your API inputs and outputs may be stored and used for Speculative Decoding – and for no other purpose."
  - They are "stored in Finland (EU)" wherever the request ran.
  - **No retention period is stated.**
- **Zero Data Retention (ZDR):**
  - Turn it on with "activate Zero Data Retention on your account profile page".
  - "ZDR applies at the organization level and covers all projects and endpoints". It is off by default; the guide implies this.
  - Inputs and outputs "are not stored on our systems after each request is processed".
  - It "may impact the level of service provided (e.g., inference speed)".
  - **Recommendation:** enable it before the first call. That lets the signed log say the provider kept no copy. [INFERRED]
- **Regions:**
  - Public (serverless) endpoints show region "Global": "the processing location is decided dynamically and can change at any time, without notice". "Not intended for production use cases that depend on a stable region." [OFFICIAL] https://docs.tokenfactory.nebius.com/public-serverless.md
  - The catalog lists eu-north1 (FI) for Qwen3-235B, Qwen3-30B and Nemotron-Lightning, and us-central1 for Nemotron-Ultra.
  - Dedicated endpoints fix the region contractually.
- **Fine-tuning data:** "all fine-tuning datasets, artifacts, and model outputs are stored exclusively in EU data centers". US users' jobs are processed in the US. No region choice.
- **Ownership:** "You retain all ownership rights to your input data", "to the content generated", and "to any fine-tuned and distilled models you create". Outputs "may not be unique".
- **Compliance:**
  - The DPA is part of the ToS, with no separate signature needed. EU SCCs apply, and Nebius is certified under the EU-US Data Privacy Framework.
  - Certifications claimed: "ISO 27001, ISO 27701 and SOC 2 Type II".
  - Sub-processor changes come with at least 15 days' notice.
  - Links: https://docs.nebius.com/legal/agreement, https://docs.nebius.com/legal/privacy, https://docs.nebius.com/legal/dpa, https://docs.nebius.com/legal/sub-processors_tofa, https://nebius.com/trust-center
- **Model licenses** (catalog JSON): Qwen Apache 2.0; Nemotron 3.5 / Ultra OpenMDW-1.1; Nemotron-3-Nano nvidia-open-model-license; DeepSeek-V4-Pro-0813 MIT. Check a model's license before using its outputs as SFT data. The legal guide doesn't cover model licenses.
- **Our payload:**
  - Chiplet layouts are reconstructions of published benchmarks (Ascend910, micro150), so they are low-sensitivity. [INTERNAL]
  - Never put the API key or any ledger seed in prompts. Admission artifacts already reject credential-like IDs (`admission.py:60-65`). [INTERNAL]

---

## 5. Open items: verify with an account or onsite

1. Promo code, H100 pool and any Nebius prize at ScienceClaw: ask the rep (§3.2).
2. Per-model default rate limits for a new account (console → Rate Limits).
3. Nemotron `json_object` / `json_schema` adherence: test about 20 calls before admitting it as a lab.
4. Whether Codex's tool loop works over Nebius `/v1/responses` (one throwaway `codex exec`).
5. ZDR latency impact (time 10 calls with ZDR on and off).
6. Token Factory fine-tune price for `Qwen/Qwen3-4B` (console), and the real adapter key format (inspect one checkpoint).
7. GB10 vLLM version, for unprefixed LoRA keys (§3.6).
8. Whether the SLAB-041 freeze allows new labs, or only a labelled exploratory arm (§3.1).
