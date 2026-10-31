# Offline comparison contract: the live intent model (Jev) vs an admitted challenger, in an OpenResearch harness

**Version 1, 2026-10-31. Author: forge.** This is a contract only. Nothing has been installed, run or contacted under it, and no grant exists; every run below needs one (§10).

It implements sponsors.md v2 §4.4 and the rules in root's review #57079 and her exact-source correction #57080.

## 1. Scope

**Purpose:** measure offline how one **admitted** challenger model compares with the live intent model on the front door's automation decision.

**In scope:**
- offline replay, for agreement;
- labelled sets, for accuracy;
- fresh calls, for latency.

**Out of scope:**
- **Production changes.** `jev-1.13.0` stays the live decision model. Any shadow, reroute or swap is Carter's decision.
- **The original five-arm chiplet study.** Its arms are: simulated annealing; one lab with the base worker; four isolated labs with the base worker; four sharing labs with the base worker; four sharing labs with the adapted worker [`docs/sentilab/draft-0.5/SCIENCE-REVIEW.md:66`]. No arm, data, budget or result crosses between that study and this comparison.
- **Nebius.** It is deferred under the newer human direction and is not an arm.
- **OpenResearch as an arm.** It is the harness, never an arm.

**Naming:** anything that leaves the team says "intent model", never the vendor or model name (rule of 10-28).

## 2. The decision under test

**Reference source:** AIdenID origin/main `09b2ff46`, as last fetched locally. `workers/aquarium-edge/src/index.ts` last changed at `4f0d9847` (2026-10-29).
- The line numbers below are indicative.
- The export (§7) binds the **deployed** Worker version to its source sha, and records the deployed variable values, since some are passed with `--var` at deploy.

**Worker and config:** `aidenid-aquarium-edge`; `workers/aquarium-edge/wrangler.toml`.

**Shared verdict path:** `obtainVerdict(vector, triage, bucket, env, now, pool?)` (≈ line 588). It runs four steps in order:
1. **Cache:** `shapeKey`, schema v4, TTL `JEV_CACHE_TTL_MS` = 600000.
2. **Isolate budget:** `JEV_MAX_PER_MINUTE` = 300.
3. **Location limiter:** keys `verdicts` / `browser-verdicts`.
4. **Global daily cap:** checked via the collector.

Then it calls `callJev(env, state, TRIAGE_QUESTIONS, boundedMs(JEV_TIMEOUT_MS, 2500, 6000))` (≈ line 634).

**`callJev`** (≈ line 395) tries two providers in order. The first typed answer wins, and every failure is recorded.
1. **TypeSafe API:** `POST https://api.typesafe.ai/v1/systemone` with `model = JEV_MODEL || "jev-1.13.0"`. The model is pinned; Carter's rule of 10-14 is never `jev-latest`.
2. **Workers AI binding:** `typesafe/jev`.

**State:** `jevState(vector, triage, bucket)` (≈ line 512) holds bounded, edge-trusted request features:
- user agent (≤512 chars), claimed browser family, header names and presence;
- HTTP protocol, TLS bands, accept-encoding flags;
- network owner, country, bot-score band;
- deterministic contradictions and the requested section.

It contains no address, cookie or page content.

**Questions:** `TRIAGE_QUESTIONS` (≈ line 311):
- `is_automated` (Noul);
- `operator_hint` (Choice of 11): openai, anthropic, google, perplexity, microsoft, meta, other_ai_vendor, search_engine, scraper, browser_vendor, unknown.

**Paths and decision mapping:** thresholds are `JEV_AUTOMATED_MIN` = 0.75 and `JEV_HUMAN_MAX` = 0.25.

| Path | Where | p ≥ 0.75 | p ≤ 0.25 | Between | Unavailable |
|---|---|---|---|---|---|
| D1 `judgeUnknown` (unknown residue) | ≈ line 559 | automation | stays unresolved ("human by verdict"; never promoted to human) | unresolved | unresolved |
| D2 `judgeBrowser` (consistent browser shapes) | ≈ line 668 | automation | likely human ("intent model agrees") | unknown | likely human, unverified |
| D3 `maybeEnrich` (purpose) | ≈ line 849 | `purpose` Choice | | | |

- **D2:** active only when `JUDGE_CONSISTENT_BROWSERS` is "true" (the toml sets "true"), and only after the DNT/GPC privacy filter.
- **D3:** the Choice is evaluation | integration | discovery | unknown, with confidence capped at 0.6. It is sampled at `JEV_SAMPLE_RATE` = 0.25 for declared, crawler and verified shapes.

**Unit compared:**
- the 3-way class from the probability: automated (≥0.75), human (≤0.25), ambiguous (between);
- the operator hint.

Each is computed per path. D1 and D2 are never pooled without saying so, and D3 is reported separately.

## 3. Datasets

### 3.1 D-orig: frozen original inputs (primary)
- **What a record is:** one per original provider call. Cache hits are recorded separately, each pointing to the call it came from.
- **Contents:**
  - the exact `state` and `questions` objects as sent;
  - provider, model and raw answer;
  - verdict status or error;
  - timestamps and path.
- **Canonical form:** sorted keys, UTF-8, no insignificant whitespace (RFC 8785 style). From it come `state_sha256`, `questions_sha256` and `answers_sha256`.
- **Frozen before any challenger output exists**, by a manifest (§7). After freezing it is never edited; a correction is a new version.
- **Exclusion:** a record whose exact state wasn't retained is **not** in D-orig.

### 3.2 D-recon: reconstructed states (a separate dataset)
- **Use:** only for records without a retained state.
- **Method:** rebuilt from stored features by a written, versioned function. Its sha256 is recorded, and each record carries `reconstructed: true`.
- **Reporting:** separately. Never pooled with D-orig, and never used for the headline numbers.

### 3.3 D-ctrl: known, controlled client conditions
Each probe's label is known by construction. Condition ids are fixed before the run:

| Id | Condition | Label |
|---|---|---|
| C1 | A human-operated mainstream browser on a consumer network | human |
| C2 | curl, python-requests or Go net/http from a datacenter | automated |
| C3 | Headless Chromium automation | automated |
| C4 | A declared AI-crawler user agent from a datacenter | automated |
| C5 | Deliberately mixed conditions, e.g. automation with full browser headers on a residential network | ambiguous, by design |

- **Probe traffic:** these are real production requests and are counted there, so tag them as ours.
- **Grant:** they need a separate warden grant. This contract grants none.

### 3.4 Held-out distinct shapes
- **Unit:** one distinct `state_sha256`. Repeats collapse into one unit; the request count per shape is kept for weighted reports.
- **Split:** a shape is `heldout` when the first 8 hex digits of sha256(split_salt ‖ state_sha256), read as an integer, mod 100 are < 30; otherwise it is `dev`.
  - The salt is fixed and its hash recorded before any challenger output is seen.
  - The salt never changes.
- **Tuning:** challenger prompt, schema and decoding may be tuned on `dev` only.
- **Reporting:** every reported number comes from `heldout`. D-ctrl is entirely held out.

## 4. Arms

| Arm | What | Used for | Never used for |
|---|---|---|---|
| A-jev-replay | Original logged answers in D-orig | Agreement, accuracy | Latency |
| A-jev-fresh | Fresh `jev-1.13.0` calls with the same `state` and `questions` bytes, from the measurement host | Latency; a replay-vs-fresh consistency check | — |
| A-chal | One **admitted** challenger | Agreement, accuracy, latency | — |

**A-jev-fresh custody:** warden supplies payer and key-custody evidence. The key is loaded without printing, per the key-location rule.

**Admission for A-chal.** Every item is needed before the first call:
- **Admission evidence:**
  - host (Dell `promaxgb10-9a1e`);
  - runtime (driver, CUDA, container runtime);
  - image digest;
  - NIM profile;
  - license (model and container terms);
  - latency admission on `dev` shapes under the 2,500 ms budget.
- **Custody:** the NGC key stays on astra's PC only. No Brev registration.
- **Budget:** a warden grant with a GPU-second cap.
- **Priority:** the trained-response implementation keeps priority. No old job (SLAB-018, SLAB-047, SLAB-047b) restarts.

**Candidate:** Nemotron 3.5 Lightning 30B-A3B NIM, the default in the current DGX Spark NIM playbook. **It is not admitted.**

**Challenger input contract:**
- The same `state` object and the same question instructions and criteria text.
- Output schema `{is_automated: number in [0,1], operator_hint: one of the 11 labels}`; D3 adds `purpose`.
- Temperature 0.
- The prompt template, schema and decoding parameters are recorded, each with its sha256.
- If the model has a reasoning mode, it is turned off and that is recorded.

**Not arms:** OpenResearch itself, any Nebius endpoint, and any hosted endpoint without admission.

## 5. Labels and blinded adjudication
- **D-ctrl labels:** they come from the condition and are fixed before the run (C5 = `ambiguous`).
- **Accuracy sample for D-orig and D-recon:** a simple random sample of `heldout` shapes, drawn by hash **before** any arm output is joined to it.
- **Allowed labels:** `automated`, `human`, `ambiguous` (the evidence is insufficient). `operator` is optional.
- **Blinding:**
  - Adjudicators see only the `state` object, never an arm's answer, the arm's identity, the agreement status or another adjudicator's label.
  - Presentation order is randomized, and the presented bytes are hashed.
- **Adjudicators:**
  - Two independent adjudicators per item: two different agent families, or a human and an agent.
  - A third breaks ties.
  - Report agreement between adjudicators (Cohen's κ).
  - An agent adjudicator running inside OpenResearch is recorded as `agent:<family>`.
- **Privacy:** an agent adjudicator sends the state (user agent, network owner, country) to its model provider. Warden and Carter decide whether that's allowed; human-only adjudication is the fallback.

## 6. Metrics

**Outcome classes** for each arm and item. The list is exhaustive, and every item stays in the denominator:
- `automated` (p ≥ 0.75), `human` (p ≤ 0.25), `ambiguous` (between);
- non-answers: `missing` (no record or no answer), `timeout`, `error` (HTTP error or malformed answer), `refused` (budget or limiter);
- the `fallback` flag: answered by a secondary provider. These items are counted, and also reported by provider.

N_total for each arm and path is the sum of all classes. **Nothing is dropped.**

1. **Agreement (not accuracy):** A-jev against A-chal on `heldout`.
   - Percent agreement and Cohen's κ on the 3-way class.
   - Computed over (a) items both arms answered and (b) all items, with each non-answer class as its own category.
   - Both are reported with N.
2. **Accuracy:** each arm against the labels (D-ctrl and the adjudicated sample).
   - Confusion matrix, plus per-class precision and recall.
   - Accuracy over all items, where a non-answer counts as wrong, plus coverage (answered ÷ N_total).
   - Reported with and without `ambiguous` labels, with counts.
3. **Operator hint:**
   - Exact match against labels where an operator label exists.
   - Agreement between arms where both say automated.
4. **Purpose (D3):** a separate table under the same rules.
5. **Latency:** fresh calls only (A-jev-fresh and A-chal). Replayed answers measure nothing about latency.
   - Measured as client-observed wall time from the start of the request to the parsed answer.
   - Same host and network path for both arms where possible; otherwise record the difference and caveat it.
   - Run serially, and at one fixed small concurrency. Mark cold and warm calls.
   - Report p50, p95, p99 and max. Timeouts at 2,500 ms are kept as censored values, not dropped, and the timeout rate is reported.
6. **Cost:**
   - Record per-call `usage` where it is returned.
   - Forecast = tokens × list price. Jev: $0.042 per 1M input tokens, output free.
   - Challenger GPU: the actual cost is unknown. Forecast = charged GPU-seconds × the comparator rate in sponsors.md v2 §3, labelled as a comparator.
   - `cost_actual_usd` stays null until it is measured.
7. **Uncertainty:** 95% bootstrap intervals, resampling shapes. Report N in every cell.

**Pre-registration:** definitions, thresholds, the split-salt hash, sample sizes and this file's sha256 are recorded before any challenger output on `heldout` is generated.

**The results are invalid if any of these happen:**
- D-orig and D-recon are pooled;
- a number has no receipt in `SHA256SUMS`;
- latency comes from replayed answers;
- a non-answer is dropped;
- `heldout` was used for tuning;
- an adjudicator was unblinded.

## 7. Export schema
Files are JSONL, UTF-8, one object per line, except `manifest.json` and `metrics.json`.

**Types:**
- `str`, `int`, `num`, `bool`, `obj`;
- `hex64`: a lowercase sha256;
- `ts`: RFC 3339 UTC with milliseconds;
- `?` means nullable.

**`export/manifest.json`** (one object):

| Field | Type |
|---|---|
| `schema` | str: "sentilab-intent-compare-export/1" |
| `created_at` | ts |
| `exporter` | str |
| `source` | {worker str, deployed_version_id str, deployed_vars obj, source_repo str, source_sha str, questions_sha256 hex64} |
| `window` | {from ts, to ts} |
| `counts` | {orig int, recon int, cache_hits int, by_path obj} |
| `files` | [{path str, sha256 hex64, bytes int, records int}] |
| `split_salt_sha256` | hex64 |
| `contract_sha256` | hex64 |

**`export/decisions-orig.jsonl` and `export/decisions-recon.jsonl`:**

| Field | Type |
|---|---|
| `record_id` | str |
| `dataset` | "orig" \| "recon" |
| `path` | "D1" \| "D2" \| "D3" |
| `observed_at` | ts |
| `shape_key` | hex64 |
| `state` | obj, exact and canonical |
| `state_sha256` | hex64 |
| `questions_sha256` | hex64 |
| `provider` | str?: "typesafe_api" \| "workers_ai" |
| `model` | str? |
| `outcome` | str: "decided" \| "ambiguous" \| "unavailable" \| "skipped" |
| `error` | str? |
| `answers` | obj? |
| `answers_sha256` | hex64? |
| `is_automated` | num? |
| `operator_hint` | str? |
| `operator_confidence` | num? |
| `purpose` | str? |
| `class3` | str?: "automated" \| "human" \| "ambiguous" |
| `fallback` | bool |
| `split` | "dev" \| "heldout" |
| `reconstructed` | bool |
| `reconstruction_fn_sha256` | hex64? |

**`runs/<arm>/calls.jsonl`:** one receipt per call, written before the next call starts.

| Field | Type |
|---|---|
| `call_id` | str |
| `arm` | "jev-fresh" \| "chal" |
| `record_id` | str |
| `state_sha256` | hex64 |
| `request_sha256` | hex64, over the body only; never headers or credentials |
| `model` | str |
| `model_build` | str?, e.g. image digest |
| `endpoint_class` | str: "typesafe_api" \| "local_nim" |
| `host_id` | str |
| `concurrency` | int |
| `cold` | bool |
| `started_at` | ts |
| `finished_at` | ts |
| `latency_ms` | num |
| `timeout_ms` | int (2500) |
| `attempt` | int |
| `http_status` | int? |
| `outcome` | str: "answered" \| "timeout" \| "error" \| "malformed" \| "refused" |
| `error` | str? |
| `response_sha256` | hex64? |
| `parsed` | {is_automated num?, operator_hint str?, purpose str?} |
| `class3` | str? |
| `usage` | {input_tokens int?, output_tokens int?} |
| `cost_forecast_usd` | num? |
| `cost_actual_usd` | num?; null = unknown |
| `prompt_template_sha256` | hex64? |
| `schema_sha256` | hex64? |
| `decoding` | obj? |

**`labels/ctrl.jsonl`:**

| Field | Type |
|---|---|
| `record_id` | str |
| `condition_id` | str: "C1" … "C5" |
| `client` | str |
| `network` | str |
| `expected_label` | str: "automated" \| "human" \| "ambiguous" |
| `executed_at` | ts |
| `executor` | str |
| `grant_ref` | str |

**`labels/adjudication.jsonl`:**

| Field | Type |
|---|---|
| `record_id` | str |
| `adjudicator_id` | str |
| `adjudicator_kind` | str: "human" \| "agent:<family>" |
| `presented_sha256` | hex64 |
| `label` | str: "automated" \| "human" \| "ambiguous" |
| `operator` | str? |
| `rationale_sha256` | hex64? |
| `started_at` | ts |
| `finished_at` | ts |
| `blinded` | bool, must be true |

**`analysis/metrics.json`:** `definitions_sha256` (hex64), `inputs` (the sha256 of every input file), `results` (obj), `generated_at` (ts).

**`SHA256SUMS`:** the sha256 of every file above. Copy it off the run host after each run.

No file ever contains a credential, an IP address, a cookie or page content.

## 8. OpenResearch settings (only once a run is granted)
- **Version:** `orx` v0.2.23, or whatever version is admitted then. Record the binary's sha256.
- **Telemetry:** run `orx telemetry off` before creating the project, and record the setting. Turning telemetry off does not preserve any history.
- **Remote runs:** any SSH or Slurm backend uses `--keep-remote-runs true`. By default those backends keep only each project's three newest remote runs; older runs are deleted except their TensorBoard logs (https://openresearch.sh/docs/compute).
- **Receipts:** the §7 files are the record of truth, independent of OpenResearch's own database.
  - Copy them off the run host after every run.
  - Add them to `SHA256SUMS`.
- **Agent:** an explicitly chosen local coding agent (Claude Code or Codex) on our existing subscription.
  - No OpenResearch account.
  - No managed compute.
  - No default paid model routes. v0.2.21 fixed a bug that silently spent OpenRouter credit on an expensive default model.
- **Local models through OpenCode: not used.**
  - The docs suggest a 32K context.
  - Our adapter was served with `--max-model-len 1024` [`docs/sentilab/evidence/SLAB-018/attempt-01/http-models.json:11`].
  - It is not admitted for agent use.
- **Host:** single-user only. A third-party review reports that the remote-mode service has no application-level authentication.
- **Literature tools** (alphaXiv, bioRxiv, PubMed): optional, for the write-up only.

## 9. Ownership

| Who | Owns |
|---|---|
| forge | This contract and the analysis specification |
| warden | The exact read-only export (D-orig manifest, hashes, deployed-version binding and deployed variables). Payer and access evidence for every paid call (`jev-1.13.0` key custody, per the key-location rule). Grants: the fresh-call budget, the GPU-second cap, probe traffic |
| root (astra) | Reviews the comparison design and its results. Owns the GB10 local lifecycle (start, stop, cleanup) and NGC key custody on astra's PC |
| Carter | Any production change, any new data processor, any swap |

## 10. Grants needed before anything runs
1. The read-only export (warden).
2. A fresh-call budget for `jev-1.13.0`: a call count and a named payer.
3. Challenger admission (§4) and a GPU-second cap.
4. Probe traffic for D-ctrl.
5. The adjudicator decision: human, agent or both, including the privacy decision (§5).
