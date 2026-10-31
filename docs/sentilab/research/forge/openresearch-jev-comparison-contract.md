# Offline comparison contract: the live intent model (Jev) vs an admitted challenger, in an OpenResearch harness

**Version 2, 2026-10-31. Author: forge.** This is a contract only. Nothing has been installed, run, exported or contacted under it, and no grant exists; every run below needs its own grant (§14).

- **v1** (d30b9f30) implemented sponsors.md v2 §4.4 and root's review #57079 and correction #57080.
- **v2** applies root's review of v1 (commit comment 207557916, room #57104), repairs 1–6:

| Repair | Where it landed |
|---|---|
| 1. Paths and payloads | §2 |
| 2. Labels | §3.4, §5, §6 |
| 3. Decisions and attempts | §3.1–3.2, §8 |
| 4. Latency | §7 |
| 5. Bytes and statistics | §3.5, §6, §9 |
| 6. Sensitive text and config | §10 |

## 1. Scope

**Purpose:** describe offline how one **admitted** challenger model compares with the live intent model on the front door's decisions.

**Pilot P0 (named and bounded):** the first execution, if granted, is P0, a small **descriptive** pilot. It makes no superiority, non-inferiority or equivalence claim (§6.4).

**Out of scope:**
- **Production changes.** `jev-1.13.0` stays live. Any shadow, reroute or swap is Carter's decision.
- **The original five-arm chiplet study.** Its arms are: simulated annealing; one lab with the base worker; four isolated labs with the base worker; four sharing labs with the base worker; four sharing labs with the adapted worker [`docs/sentilab/draft-0.5/SCIENCE-REVIEW.md:66`].
  - It stays separate and incomplete.
  - No arm, data, budget or result crosses between it and this comparison.
- **Nebius.** It is deferred and is not an arm.
- **OpenResearch as an arm.** It is the harness, never an arm.

**Naming:** anything that leaves the team says "intent model", never the vendor or model name (rule of 10-28).

## 2. Source binding and decision paths (repair 1)

### 2.1 Source binding

**Retrieved source:** `Sentinelayer-AIdenID/AIdenID` at commit `09b2ff466d0fadcb83b09b0f6f213d13f430c9e1`, tree `71c35858d7df7505c4594d023634f12d4f01fa58`.

| File | sha256 |
|---|---|
| `workers/aquarium-edge/src/index.ts` | `0b0668d9d32e68e4c9fea60f750034fe49a2b0fcae8d875d630876f925b70792` |
| `workers/aquarium-edge/wrangler.toml` | `c7e0834e9c0ac02b8a38f47bfd64013f5e1e3017831cf4c7f1dcc83c89483b75` |

**What this binding is and isn't:**
- Forge fetched these hashes read-only, and they match root's retrieval. **These are source facts.** They do not verify the deployed Worker or its effective variables.
- Warden binds the deployed version to its source sha and records the effective variables through the allowlist in §10.2.
- Citations below take the form `index.ts:L` or `wrangler.toml:L` at this commit.

### 2.2 The three paths

| | D1 unknown residue | D2 consistent browsers | D3 purpose |
|---|---|---|---|
| Entry | `judgeUnknown` (index.ts:559–584) via `triageRequest` (:695–700) | `judgeBrowser` (index.ts:668–692), called at :1004, after the privacy filter | `maybeEnrich` (index.ts:849–884), called at :1041 |
| Eligibility | Triage class `unknown` (:560) | Class `likely_human` with reason `consistent_browser_shape`, and `JUDGE_CONSISTENT_BROWSERS == "true"` (:669–670; toml sets "true" at wrangler.toml:48) | Classes `declared_agent`, `crawler_claimed`, `verified_agent` and **`signed_agent`** (:853). Deterministic per-shape sampling: first byte of sha256 over JSON `[bucket, label, basis]` ÷ 256 < `JEV_SAMPLE_RATE` (:858–863) |
| Goes through `obtainVerdict` | Yes (:588–651): cache (:591–597), isolate budget (:598), location limiter key `verdicts` (:602–610), global daily cap (:611–632) | Yes, with limiter key `browser-verdicts` (:605) | **No.** Calls `callJev` directly (:868). No `obtainVerdict` cache, limiter or global cap |
| State sent | `jevState(...)` (:512–551), e.g. `user_agent` (:521) and `header_names` (:524) | Same `jevState(...)` | **Only `{route_bucket, observed_label, evidence_basis}`** (:868) |
| Questions | `TRIAGE_QUESTIONS` (:311–337): `is_automated` (Noul), `operator_hint` (Choice of 11) | Same | **Only `purpose`** (Choice: evaluation, integration, discovery, unknown) (:869–878) |
| Timeout, code default | `boundedMs(JEV_TIMEOUT_MS, 2500, 6000)` (:634) | Same | `boundedMs(JEV_TIMEOUT_MS, 750, 6000)` (:879) |
| Effective timeout | Overridden by an effective `JEV_TIMEOUT_MS`, clamped to 50–6000 ms (`boundedMs`, :341–344). The checked toml sets 2500 (wrangler.toml:33). The deployed value comes from warden | Same | Same override. Under the checked toml, D3 also gets 2500 |
| Raw model result → production policy | p ≥ 0.75 → `automation` (:568–571). Otherwise, if decided (incl. p ≤ 0.25) → stays **unresolved**, never human (:574). Ambiguous → unresolved (:576–577). Unavailable or off → unresolved (:579–580) | p ≥ 0.75 → `automation` (:678–681). p ≤ 0.25 → **likely human, "intent model agrees"** (:683–684). Other decided or ambiguous → `unknown` (:687–689). Unavailable → likely human, unverified (:691) | `parseJevIntent` (:832–846) drops the answer if confidence < 0.7 (:843), and caps the stored confidence at 0.6 (:845) |

**Raw model class vs production verdict.** Every record keeps two things separately:
- the **raw model result**: probability-derived `model_class3`, operator hint and purpose, with raw confidence where it was retained;
- the **production-policy verdict** above, with its `policy_ref` (file:line).

Neither is derived from the other after the fact.

**Replay is not production replay.** Replaying a model answer does not replay the production policy, cache, budget or limiter path. Results say which one was measured.

**Export schemas are path-specific (§11):**
- D1/D2 records carry triage questions and state.
- D3 records carry the purpose question and the D3 payload only, with purpose-only outputs.
- D3 adds no `purpose` field to the triage schema, and D1/D2 add none either.

## 3. Datasets, identities and selection

### 3.1 Logical decisions and ordered attempts (repair 3)

**A logical decision** is one production decision on one request and path.
- **`logical_decision_id`:** the collector's own record key where one exists (the key read and written back at index.ts:1675 and :1696). Otherwise sha256 over the canonical bytes (§9) of `{path, source_sha, effective_config_sha256, questions_sha256, payload_canonical_sha256, observed_at, collector_sequence}`.
- **Each decision carries:** its path, questions identity, source and config identity, and its **ordered attempts** as actually retained.

**What original records can contain**, limited by the source:
- **The Verdict object** keeps only `status`, `provider` (`typesafe_api` | `workers_ai` | `cache`), `model`, `isAutomated`, `operatorHint`, `operatorConfidence` and `error` (index.ts:119–127).
- **`callJev` gives each provider the full supplied timeout** (:410, :419).
  - A successful fallback returns **without** the earlier error: the error is pushed at :415–416, and the fallback returns at :422 without it.
  - A failure returns the joined errors truncated to 48 characters (:426–427).
  - No per-attempt token usage is kept: `parseAnswers` keeps only `model` and `answers` (:375–381).
- **Cache hits** are reported with provider `cache` (:596). The originating call is not referenced.
- **Cron re-judges** of unavailable records (:1657–1712) rebuild a vector from the stored user agent only, leaving every other field empty (:1681–1688), then call `judgeUnknown` (:1691).
  - This is a different, reduced state. It is recorded as a separate attempt with `state_variant: "cron_ua_only"` and its own payload hash, never as the original state.
- **D3 keeps only the policy intent:** label, plus a confidence capped at 0.6; nothing below 0.7 is kept (:843–845). The raw D3 choice and confidence are not retained.

**Rules for originals:**
- Preserve exactly what the original records contain.
- A missing earlier attempt, error, usage figure, raw answer or wire body stays **missing**, with a `missing_reason`. It is never recreated as an original.
- A failed first attempt and its successful fallback are **one** decision. Fallback attempts are never scored as independent accuracy items.
- Cache-hit decisions count in the volume denominators and are not model-accuracy items. Any link back to an originating call that is inferred from the shape key and time window is labelled `inferred`.

### 3.2 D-orig: frozen originals and repeated shapes
- **Frozen before any challenger output exists**, by a manifest (§9.3). After freezing it is never edited; a correction is a new version.
- **Shape:** the shape of a decision is `(path, source_sha, effective_config_sha256, questions_sha256, payload_canonical_sha256)`.
- **Representative (frozen rule):** for each shape, the earliest logical decision with a typed, non-cache original answer. Ties on `observed_at` are broken by `collector_sequence`, then by `logical_decision_id` byte order.
- **Repeats:** all other decisions of the shape. They are used only for:
  - the **temporal-disagreement** report: the share of repeats whose `model_class3` differs from the representative's, per path;
  - **volume**: the request count and cache-hit count per shape.
- **Denominators:** request volume and shape counts are kept in every denominator report.

### 3.3 D-recon: reconstructed payloads (a separate dataset)
- **Use:** only where the original payload wasn't retained.
- **Method:** rebuilt by a written, versioned function whose sha256 is recorded, with `reconstructed: true`.
- **Reporting:** separately. Never pooled with D-orig, never used for headline numbers, and never described as original.

### 3.4 D-ctrl: controlled executions (repair 2)
Each probe has a retained **execution record**: the client binary or script and its version, the host and network, the exact headers sent, the start and end times, and the operator, which is always us. The label comes from that record, not from the observed state.

| Id | What is executed | `execution_truth` | Notes |
|---|---|---|---|
| C1 | A person operating a mainstream browser on a consumer network | human | |
| C2 | curl, python-requests or Go net/http from a datacenter | automated | |
| C3 | Headless Chromium automation | automated | |
| C4 | Our automation sending a declared AI-crawler user agent from a datacenter | automated | `execution_operator` = `sentilab-controlled`. A crawler user agent alone proves neither automation nor the named vendor's identity |
| C5 | Automation explicitly executed with browser-like headers on a residential network | **automated** | Its observed state may be insufficient to show that. Observable sufficiency is a separate field (§5) |

- **Probe traffic:** these are production requests and are counted there, so tag them as ours.
- **Grant:** they need a separate probe grant. This contract grants none.

### 3.5 Grouping, splits, samples and seeds (repair 5)
- **Group:** shapes are joined into a group if they share:
  - (a) a visitor pseudonym, where the export retains one; or
  - (b) the same `ua_skeleton` (the user agent lowercased, every digit run replaced by `0`), the same `network_owner` and the same path.

  The union is taken transitively. Grouping prevents near-duplicates from straddling the split.
- **Split** (per group): `heldout` if `int(sha256(split_salt ‖ group_key)[0:8], 16) mod 100 < 30`, otherwise `dev`.
  - Tuning (prompt, schema, decoding) uses `dev` only.
  - Every reported number comes from `heldout`.
  - D-ctrl is entirely held out.
- **P0 sample sizes** (maxima, frozen now):
  - Held-out groups: up to 300, ordered by `sha256(sample_seed ‖ group_key)`.
  - Adjudication: the first 100 held-out representatives in that order.
  - D-ctrl: 10 executions per condition (50 total).
  - Latency: §7.
- **Seeds and custody:**
  - Warden generates `split_salt`, `sample_seed` and `bootstrap_seed`, 32 random bytes each, before any held-out output exists.
  - Only their sha256 values go in the pre-registration record.
  - The values are revealed after the analysis freeze, so splits and samples can be re-derived.

## 4. Arms

| Arm | What | Used for | Never used for |
|---|---|---|---|
| A-jev-replay | The representative original answers (§3.2) | Agreement and consensus comparisons | Latency, or a claim about the production policy path |
| A-jev-fresh | New `jev-1.13.0` calls with the same payload and questions, **direct provider only** (§7) | Latency; replay-vs-fresh consistency | — |
| A-chal | One **admitted** challenger | Agreement, controlled-condition accuracy, latency | — |

**Admission for A-chal.** Every item is needed before the first call:
- **Admission evidence:** host (Dell `promaxgb10-9a1e`); runtime (driver, CUDA, container runtime); image digest; NIM profile; license (model and container terms).
- **Custody:** the NGC key stays on astra's PC only. No Brev registration.
- **Budget:** a warden grant with a GPU-second cap.
- **Priority:** the trained-response implementation keeps priority. No old job (SLAB-018, SLAB-047, SLAB-047b) restarts.
- **Latency preflight:** its own separately bounded grant (§7.5). Listing it here does not authorize it.

**Candidate:** Nemotron 3.5 Lightning 30B-A3B NIM. It is **not admitted**.

**Challenger input:** exactly the path's payload and question text (§2.2), temperature 0, with the prompt template, schema and decoding parameters each hashed. If the model has a reasoning mode, it is turned off and that is recorded.
- D1/D2 schema: `{is_automated: [0,1], operator_hint: 11 labels}`.
- D3 schema: `{purpose: 4 labels}` only.

**Not arms:** OpenResearch itself, any Nebius endpoint, and any hosted endpoint without admission.

## 5. Labels (repair 2)

| Label family | Source | Values | Measures |
|---|---|---|---|
| `execution_truth` | D-ctrl execution record (§3.4) | automated, human | Known execution facts |
| `execution_operator` | D-ctrl execution record | `sentilab-controlled` | Who actually operated the client |
| `scripted_purpose` | A D-ctrl execution with a scripted purpose, if any | One of the 4 purposes | Known purpose (D3) |
| `observable_sufficiency` | Blinded adjudicators on D-ctrl states | sufficient, insufficient | Whether the state shows the truth |
| `consensus_label` | Blinded adjudication of real held-out traffic | automated, human, ambiguous, tie | **Evidence-based consensus, not real-operator ground truth** |

- **Blinding:**
  - Adjudicators see only the payload object for the path, never an arm's answer, the arm's identity, agreement status or another adjudicator's label.
  - Presentation order is randomized by `sample_seed`, and the presented bytes are hashed.
- **Adjudicators:**
  - Two independent adjudicators per item; a third resolves disagreements.
  - If still unresolved, the item is a `tie`. Ties stay in the counts.
  - Each adjudicator's confidence (0–1) is retained.
  - Agreement between adjudicators (Cohen's κ) is reported.
- **No relabelling:** `ambiguous` never replaces a known `execution_truth`.
- **Operator accuracy** is reported only where an independent operator label exists. A crawler user agent is not one. A signature-verified signer proves key control, not operator identity (index.ts:886–891).
- **Purpose accuracy** is reported only against `scripted_purpose`.
- **Who may adjudicate:** a model adjudicator is a processor decision (§10.4). Until that decision, real traffic goes to human adjudicators only.

## 6. Metrics, undefined values and claims

### 6.1 Outcome classes and denominators
**Classes** per arm and decision. The list is exhaustive:
- `automated`, `human`, `ambiguous` (D1/D2 raw class, from p ≥ 0.75 / ≤ 0.25 / between); for D3, the purpose label;
- `missing`, `timeout`, `error`, `malformed`, `refused` (budget or limiter), `unknown` (§8);
- a `fallback` flag.

**Denominators:**
- Every decision stays in N_total. Nothing is dropped.
- Volume-weighted versions report request counts alongside shape counts.

### 6.2 Metric families (reported separately, each with N)
1. **Controlled-condition accuracy:** against `execution_truth` on D-ctrl.
   - Confusion matrix, per-class recall, and accuracy where a non-answer counts as wrong.
   - Coverage = answered ÷ N_total.
   - **This is the only family called "accuracy".**
2. **Consensus agreement:** against `consensus_label` on held-out real traffic. Ties and adjudicator uncertainty are reported, and it is never called accuracy.
3. **Model-vs-model agreement:** A-jev against A-chal. Percent agreement and Cohen's κ over (a) decisions both arms answered and (b) all decisions, with each non-answer class as its own category.
4. **Policy-level comparison:** the production verdict each arm's answer would produce under §2.2's mapping, per path. It is labelled as policy-level, not raw.
5. **Purpose (D3):** agreement; accuracy only against `scripted_purpose`.
6. **Temporal disagreement** among original repeats (§3.2).

### 6.3 Statistics
- **Intervals:** group-level percentile bootstrap.
  - B = 10,000 resamples of held-out groups.
  - RNG: `numpy.random.default_rng(int.from_bytes(bootstrap_seed, "big"))`.
  - 95% intervals.
- **Undefined values:**
  - Cohen's κ is undefined when N = 0 or the expected agreement is 1. Report it as "undefined", never 0 or 1.
  - Precision or recall with a zero denominator is "undefined".
  - Any cell with N = 0 is "n/a (N=0)".
  - Report the share of bootstrap resamples where a metric is undefined. If that share exceeds 5%, its interval is "not estimable".

### 6.4 Claims (frozen before held-out results exist)
- **P0 is descriptive.**
  - Tables with N, intervals and coverage.
  - No superiority, non-inferiority or equivalence claim.
  - No headline "accuracy" outside family 1.
- **Any later comparative claim** needs a new pre-registered protocol with its margin, for example a non-inferiority δ on family 1, and fresh held-out data. P0's held-out data can't be reused to confirm.
- **Pre-registration record:**
  - this contract's sha256;
  - definitions and thresholds;
  - P0 sizes;
  - the sha256 of each seed and of the salt.

  It is written before any challenger output on `heldout` exists.
- **Results are invalid if any of these happen:**
  - D-orig and D-recon are pooled;
  - a number has no receipt in `SHA256SUMS`;
  - latency comes from replayed answers;
  - a non-answer is dropped;
  - `heldout` was used for tuning;
  - an adjudicator was unblinded;
  - a fallback attempt was scored as an item.

## 7. Latency (repair 4)

**7.1 Two quantities:**
- **Provider-attempt latency:** one provider call, from request start to parsed answer or terminal error.
- **Logical-decision latency:** end to end, across every attempt of a decision.

**7.2 Reference mode.** The fresh Jev reference is **direct-provider-only**: the TypeSafe API, one attempt per decision, with an attempt timeout equal to the effective `JEV_TIMEOUT_MS`.
- The production chain's second provider is the in-Worker Workers AI binding (index.ts:418–419), which can't be reached off-edge.
- Each provider gets its own full timeout (:410, :419), so the chain's end-to-end bound is up to two timeouts plus overhead. That is a source fact, **not measured offline**.
- The challenger makes one attempt with the same attempt timeout and no fallback.

**7.3 Design:**
- **Regimes:**
  - R1 serial cold: the first call after ≥10 minutes idle, and for the challenger after a container start;
  - R2 serial warm;
  - R3 concurrency 4, warm.
- **Blocks:** within each regime, paired blocks use one held-out payload for both arms. The arm order inside each block is randomized by `sample_seed`, and blocks are interleaved. The regime order is also randomized.
- **P0 size:** 30 blocks per regime, so at most 90 attempts per arm.
- **Paths:** different network paths (internet API vs LAN GPU) are recorded per attempt and caveated.

**7.4 Censoring:**
- **Timeouts** are right-censored at the attempt timeout.
- **Budget refusals and pre-call errors** are not latency observations, but they stay in the outcome denominators with their counts.
- **Quantiles** (p50, p95, p99) use every attempted call, with censored values ordered above the timeout.
  - If the ⌈qN⌉-th order statistic is censored, report "p_q > timeout (not estimable)" with the bound.
  - A timeout cutoff is never reported as a completed response time.

**7.5 Latency preflight:** a development check of plumbing and timeouts, with its **own** bounded prospective grant: ≤10 attempts per arm, and a GPU-second cap set by warden.
- Its data are excluded from P0.
- Requiring a preflight does not authorize one.

## 8. Receipts for new calls (repair 3)

**Format:** append-only JSONL in `runs/<arm>/attempts.jsonl`, with fsync after every write. Each attempt writes:
1. **`reserve`,** before the request is sent: `attempt_id` (UUIDv7), `logical_decision_id`, `arm`, `provider`, `attempt_index`, `parent_attempt_id` and `link` (first | retry | fallback), `reserved_at`, `timeout_ms`, and `charge_reserved` {calls, gpu_seconds}.
2. **`terminal`,** after the request: `outcome` (answered | timeout | error | malformed | refused), `finished_at`, `latency_ms`, `http_status`, `error`, `response_raw_sha256`, `usage`, `charge` {calls, input_tokens, output_tokens, gpu_seconds} and `cost_actual_usd` (null unless measured).
3. **`terminal` with `outcome: unknown`,** written on recovery for any reserve that has no terminal record. Unknown is never inferred to be success.

**Rules:**
- Every attempt's charge is recorded, including failures, retries and fallbacks.
- **Concurrency:** writers never rely on "before the next call". Each attempt is self-contained and keyed by `attempt_id`, and the merge orders by `reserved_at`, then `attempt_id`.

## 9. Bytes, canonical form and hashes (repair 5)

### 9.1 Canonical serializer (exact)
**Implementation:** Python ≥ 3.11 stdlib `json`, as below.

```python
def strict_load(raw: bytes):                 # parse original bytes
    text = raw.decode("utf-8", errors="strict")
    return json.loads(text, object_pairs_hook=reject_duplicate_or_non_ascii_keys,
                      parse_constant=reject_nan_infinity)

def canonical_bytes(obj) -> bytes:           # after a recursive type/range check
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")
```

**Accepted:** objects with unique ASCII string keys; arrays; strings; true, false, null; integers with |n| ≤ 2^53−1; finite floats.

**Rejected:**
- duplicate keys;
- non-ASCII keys;
- NaN or Infinity literals;
- overflow to infinity (e.g. `1e400`);
- lone surrogates;
- invalid UTF-8;
- a byte-order mark;
- integers outside ±(2^53−1).

**Normalization rules:**
- Numbers keep the type parsed from the source text. A float is written by Python's shortest round-trip repr (`0.00001` → `1e-05`, `1.5e3` → `1500.0`).
- Strings get no Unicode normalization.
- Keys sort by code point.
- Output is UTF-8. Only `"`, `\` and control characters below U+0020 are escaped.

**Test vectors** (computed locally with Python 3.11.9):

| Id | Raw input bytes (ASCII) | Canonical output | sha256(canonical) |
|---|---|---|---|
| V1 | `{"b": 1, "a": [true, false, null]}` | `{"a":[true,false,null],"b":1}` | `087e44ed138472a81a4a0f8ae84e8f358d0d957d27f51123952aa88c007b1f9f` |
| V2 | `{"p": 0.82, "q": 0.00001, "r": 10, "s": 1.5e3}` | `{"p":0.82,"q":1e-05,"r":10,"s":1500.0}` | `701897c2e1c936e7fac2a7bef4f1c09251cdf3cb1e1b75b92c45cfadbde12fea` |
| V3 | `{"ua": "Mozilla/5.0 (X11) \u00e9\u4e2d", "h": ["accept", "user-agent"]}` | `{"h":["accept","user-agent"],"ua":"Mozilla/5.0 (X11) <c3a9 e4b8ad>"}` (60 bytes; raw UTF-8 shown as hex) | `60240532bb9f3f2c53ca9e68698604d10cd95216631c48d1e4f940c777126190` |
| V4 | `{"s": "a\u0001b\n\"q\"\\"}` | `{"s":"a\u0001b\n\"q\"\\"}` | `010bb5f554b870631a324a487298c16920eb9516b8c8f3ff296c1097be9bad0a` |
| V5 | `{"z": {"y": 1, "x": 2}, "a": 0}` | `{"a":0,"z":{"x":2,"y":1}}` | `088a6516823f03c484c874a2f698b6b5bd515174a3ca6f68137566c49c68a939` |

**Rejection vectors.** Each must raise:

| Id | Input | Reason |
|---|---|---|
| R1 | `{"a": 1, "a": 2}` | duplicate key |
| R2 | `{"a": NaN}` | non-finite literal |
| R3 | `{"a": 1e400}` | overflow to infinity |
| R4 | `{"a": "\ud800"}` | lone surrogate |
| R5 | `{"\u00e9": 1}` | non-ASCII key |
| R6 | byte `0xff` | invalid UTF-8 |
| R7 | UTF-8 BOM + `{"a": 1}` | byte-order mark |
| R8 | `{"a": 9007199254740992}` | integer out of range |

### 9.2 Raw bytes vs canonical objects
- **`raw_sha256`** hashes the bytes exactly as retrieved from the store. This is usually a stored record, because the original wire body to the provider was not retained.
- **`canonical_sha256`** hashes the parsed object.
- Reserialized bytes are never presented as the original wire body.
- Both hashes are kept.

### 9.3 Hash graph (no self-reference)
1. **Payload-level:** `raw_sha256` and `canonical_sha256` live inside records.
2. **Data files** (JSONL): each file's sha256 is computed over its bytes, and no file contains its own hash.
3. **`manifest.json`** lists every data file's sha256, plus `contract_sha256` and the seed and salt hashes. It does not contain its own hash.
4. **`analysis/metrics.json`** lists the sha256 of the data files and of `manifest.json`. It does not list `SHA256SUMS`.
5. **`SHA256SUMS`** covers every file except itself.
6. **Outside the export:** the sha256 of `SHA256SUMS` is recorded in the grant or run receipt.

**Record identity** includes the path, `questions_sha256`, `source_sha` and `effective_config_sha256` (§3.1).

## 10. Sensitive text and configuration (repair 6)

### 10.1 Client-controlled text
These fields are arbitrary client text:
- `jevState`'s `user_agent` (up to 512 chars, index.ts:521);
- `jevState`'s `header_names` (up to 24, :524);
- D3's `observed_label`, which can carry request-derived text such as a signer origin (:868, :886–891).

**Having no named address or cookie field does not show these contain no secret, address or cookie.** The source itself notes that verdict records keep the raw user agent with no expiry (:1057–1059).

### 10.2 Effective configuration allowlist
Read from the **deployed** version; the line numbers below are the toml for reference.

**Values exported:**
- `ENABLE_JEV` (32), `JEV_MODEL` (35), `JEV_TIMEOUT_MS` (33);
- `JEV_AUTOMATED_MIN` (36), `JEV_HUMAN_MAX` (37);
- `JEV_MAX_PER_MINUTE` (38), `JEV_DAILY_CAP` (40), `JEV_SAMPLE_RATE` (42), `JEV_CACHE_TTL_MS` (43);
- `JUDGE_CONSISTENT_BROWSERS` (48), `OBSERVE_BROWSER_REQUESTS` (22);
- `WEB_BOT_AUTH_VERIFY` (44), `CHECKPOINT_MODE` (26), `AQUARIUM_SITE_ID` (16).

**Derived facts only (never the values):**
- the AI binding is present (56–57);
- a `TYPESAFE_API_KEY` secret is present;
- `TYPESAFE_API_URL` is set, and whether it equals the default;
- the `JEV_LIMITER` limit and period (67–71);
- the cron schedule (97–98).

**Nothing else is exported, and arbitrary environment values never are.**

### 10.3 Originals, quarantine and derivatives
- **Original private bytes** stay unchanged in warden's private store, with restricted access, and are never rewritten.
- **Shared analysis uses derivatives only**, made by a versioned sanitizer whose sha256 is recorded.
  - It scans the client-controlled fields with gitleaks rules plus patterns for IPv4/IPv6, email addresses, URLs with credentials and long high-entropy tokens.
  - A matching record is **quarantined**: it is excluded from shared derivatives and listed only by `record_id` and rule id.
  - Any redaction applies only to a derivative, which has its own `derivative_sha256` and is never presented as an exact original.

### 10.4 Processors
Sending any state to a model or adjudicator service is a **separate, scoped processor and custody decision** (warden and Carter). Listing an agent in this contract does not authorize sending real retained traffic. This applies to D1/D2 states and to D3 labels.

## 11. Export schema
**Encoding:** JSONL, UTF-8; `manifest.json` and `metrics.json` are single objects.

**Types:**
- `str`, `int`, `num`, `bool`, `obj`;
- `hex64`: a lowercase sha256;
- `ts`: RFC 3339 UTC with milliseconds;
- `?` means nullable.

### `export/manifest.json`

| Field | Type |
|---|---|
| `schema` | "sentilab-intent-compare-export/2" |
| `created_at` | ts |
| `exporter` | str |
| `source` | {repo str, source_sha str, deployed_version_id str, effective_config obj (allowlist §10.2 only), effective_config_sha256 hex64} |
| `window` | {from ts, to ts} |
| `counts` | {decisions, attempts_known, cache_hits, quarantined, by_path obj} |
| `files` | [{path, sha256, bytes, records}] |
| `split_salt_sha256` | hex64 |
| `sample_seed_sha256` | hex64 |
| `bootstrap_seed_sha256` | hex64 |
| `contract_sha256` | hex64 |
| `sanitizer_sha256` | hex64? |

### `export/decisions-orig.jsonl` and `export/decisions-recon.jsonl` (one line per logical decision)

| Field | Type |
|---|---|
| `logical_decision_id` | str |
| `dataset` | "orig" \| "recon" |
| `path` | "D1" \| "D2" \| "D3" |
| `observed_at` | ts |
| `collector_sequence` | int? |
| `shape_id` | hex64 |
| `group_key` | hex64 |
| `split` | "dev" \| "heldout" |
| `representative` | bool |
| `payload` | obj; the path-specific state, D3 payload or derivative |
| `payload_raw_sha256` | hex64? |
| `payload_canonical_sha256` | hex64 |
| `questions_sha256` | hex64 |
| `attempts` | [{index int, provider str?, outcome str, error str?, error_truncated bool, usage obj?, state_variant str ("original" \| "cron_ua_only"), payload_canonical_sha256 hex64, missing_reason str?}] |
| `model_raw` | {p_automated num?, operator_hint str?, operator_confidence num?, purpose str?, purpose_confidence num?} |
| `model_class3` | str? |
| `policy_verdict` | str? |
| `policy_ref` | str |
| `cache_hit` | bool |
| `reconstructed` | bool |
| `reconstruction_fn_sha256` | hex64? |
| `quarantined` | bool |
| `derivative_sha256` | hex64? |

### `runs/<arm>/attempts.jsonl`
The reserve and terminal records in §8, plus these fields on every record: `payload_canonical_sha256`, `request_raw_sha256` (the body only; never headers or credentials), `model`, `model_build`, `endpoint_class` ("typesafe_api" | "local_nim"), `host_id`, `network_path`, `regime` ("R1" | "R2" | "R3" | "pilot"), `block_id`, `order_in_block`, `prompt_template_sha256`, `schema_sha256` and `decoding`.

### `labels/ctrl.jsonl`

| Field | Type |
|---|---|
| `logical_decision_id` | str |
| `condition_id` | "C1" … "C5" |
| `execution_record_sha256` | hex64 |
| `execution_truth` | str |
| `execution_operator` | str |
| `scripted_purpose` | str? |
| `executed_at` | ts |
| `executor` | str |
| `grant_ref` | str |

### `labels/adjudication.jsonl`

| Field | Type |
|---|---|
| `logical_decision_id` | str |
| `adjudicator_id` | str |
| `adjudicator_kind` | "human" \| "agent:<family>" |
| `processor_decision_ref` | str?; required for agents |
| `presented_sha256` | hex64 |
| `label` | str |
| `observable_sufficiency` | str? |
| `confidence` | num |
| `rationale_sha256` | hex64? |
| `started_at` | ts |
| `finished_at` | ts |
| `blinded` | true |

### `analysis/metrics.json` and `SHA256SUMS`
As in §9.3.

## 12. OpenResearch settings (only once a run is granted)
- **Version:** `orx` v0.2.23, or whatever version is admitted then. Record the binary's sha256.
- **Telemetry:** run `orx telemetry off` before creating the project, and record the setting. Turning telemetry off preserves no history.
- **Remote runs:** any SSH or Slurm backend uses `--keep-remote-runs true`. By default those backends keep only the three newest remote runs (https://openresearch.sh/docs/compute).
- **Receipts:** the §11 files are the record of truth, independent of OpenResearch's database. Copy them off the run host after every run, and add them to `SHA256SUMS`.
- **Agent:** an explicitly chosen local coding agent on our existing subscription.
  - No OpenResearch account.
  - No managed compute.
  - No default paid model routes.
- **Local models through OpenCode: not used.** Our adapter was served with `--max-model-len 1024` [`docs/sentilab/evidence/SLAB-018/attempt-01/http-models.json:11`].
- **Host:** single-user only. A third-party review reports that the remote-mode service has no application-level authentication.

## 13. Ownership

| Who | Owns |
|---|---|
| forge | This contract and the analysis specification |
| warden | Continues the authorized read-only inventory of available original fields, the deployed-source binding and the effective configuration, and reports unavailable fields directly (no new overall human approval gate is needed for that inventory). Also: the private store and quarantine; payer and access evidence for every paid call (`jev-1.13.0` key custody, per the key-location rule); seeds and salt (§3.5) |
| root (astra) | Reviews the revised protocol, its results and the GB10 local lifecycle (start, stop, cleanup), and holds NGC key custody on astra's PC |
| Carter | Any production change, any processor decision (§10.4), any swap |

## 14. Grants needed (each specific and prospective; none is granted here)
1. The read-only export of original fields (warden).
2. A fresh-call budget for `jev-1.13.0`: a call count, a payer, and the P0 latency design (§7).
3. Challenger admission (§4) and a GPU-second cap.
4. The latency preflight (§7.5), as its own bounded grant.
5. Probe traffic for D-ctrl.
6. Processor decisions for any model adjudicator (§10.4).
