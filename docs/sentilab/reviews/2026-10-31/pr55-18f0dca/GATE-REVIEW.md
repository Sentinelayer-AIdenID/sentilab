# PR55 independent gate and arithmetic review

**Disposition: HOLD; no +1.** Four finite synthetic counterexamples require correction. The review also identifies an untested profile-applicability limitation. This is a source and synthetic-fixture review, not authorization for profiling or execution.

- Head: `18f0dcaea086c7817990112398d358bcd28dbe07`
- Base: `1e6b97e2a41fb760154e1bb6f3ba8b2df23a1737`
- Checkout: `C:/Users/carth/Desktop/projects/PlexAura_Inc/SentinelLayer/AIdenID/.sentinelayer/pr55-profile-review`
- Ownership: profile admission, freeze/start arithmetic, schedule integration, and finite fixtures. The parent reviewer owns worker/raw-output retention and supervisor changes.
- One fetch preceded this review; no subsequent fetch was performed. No product source was edited.

## Confirmed findings

### 1. P1 — The admitted long-SA search/reproduction split is not executed

`sundai_controller/evidence_profile.py:91–99` accepts a declared split whose sum matches the long maximum. `sundai_controller/headroom.py:970–972` passes only that maximum to `_run_long_sa`; the callee at `758–763` always uses one reproduction for v4 and zero for other schemas. Completion at `733` uses the callee's counts, not the admitted split; the non-v4 verdict at `1037` consequently accepts the wrong completed schedule.

The retained fixture declares Ascend910/v3 long maximum **5**, search **4**, reproduction **1**. Admission succeeds with **9 total calls**. Execution records **5 long searches, 0 long reproductions, complete=true**, and overall **PASS** after 9 fake calls. This establishes a declaration/execution mismatch; the fake temperatures are not thermal evidence.

**Correction:** either execute the admitted split, or reject unsupported splits before freeze/start. Apply this to new declarations without rewriting historical v3 results. Add a fixture asserting actual search and reproduction counts against the admitted declaration. The long-SA convention predates this PR; the new admission layer explicitly validates a split it does not enforce.

Evidence: `ADVERSARIAL-FIXTURES.json` → `declaredReproductionMismatch`; reproducer: `run_fixture_review.py`.

### 2. P1 — Retained measurements can be relabeled with another execution identity

`evidence_profile.py:107–124` copies the caller-supplied identity into a profile without binding the retained records to that identity. The CLI accepts identity and records separately in `profile_headroom.py:17–37`. `_validate_measurements` at `evidence_profile.py:188` rebuilds the records under the same supplied identity, so the summary and record digests do not close this gap. The comparison at `203–208` checks the profile header against current execution, not the measurements' provenance.

The retained fixture places a foreign `result.problem_hash` in a record and labels it micro150/grid64, then builds a profile with the current Ascend910/grid32 identity. It reports **zero exclusions** and **admitted=true**. `result.problem_hash` is an actual result field; the extra per-record fixture/grid/identity fields in this fixture make the mismatch explicit rather than proving those fields are always present in production.

**Correction:** bind each retained record to its actual profiling attempt identity/manifest, including the problem and relevant executable/configuration identity; reject mismatches and mixed incompatible attempts. Authenticate the record-to-attempt relationship according to the evidence trust model. This is a missing provenance binding, not evidence of a broken cryptographic primitive or an observed hostile attack.

Evidence: `ADVERSARIAL-FIXTURES.json` → `foreignRecordRelabel`; reproducer: `run_fixture_review.py`.

### 3. P2 — A successful newly retained non-v4 attempt stays `started`

`headroom.py:872` enables retention for all required-profile runs, and `895–907` records their attempts as `started`. The successful terminal update at `1083–1085` remains inside `if v4` at `1070`.

The completed synthetic Ascend910/v3 run from finding 1 writes a PASS result but leaves `SPEND.attempts[-1].status == "started"`, with no ending call count or verdict on that attempt. A consumer cannot infer a reliable terminal state from this retained ledger entry.

**Correction:** finalize every retained attempt's status, ending counts, and verdict on successful termination, while preserving distinct setup-failure, execution-failure, and incomplete states. This does not assert an unmetered-call or CPU-stop defect.

Evidence: `ADVERSARIAL-FIXTURES.json` → `declaredReproductionMismatch.persistedAttempt`.

### 4. P2 — An unknown method passes admission and can report PASS

`evidence_profile.py:77–86` validates list shape but not supported method names. `headroom.py:949–956` launches those names. `_run_lane` initializes the controller at `630–631`; unsupported names are rejected only within the proposal loop at `659–660`. A one-search schedule completes initialization without entering that loop.

The retained fixture declares reducer method **`typo`**, search **1**, reproduction **1**. Admission succeeds; the lane reports **complete=true**, and the final result reports **PASS**, retaining `reducer_methods=["typo"]`, after **4 aggregate fake calls**. This is a supported-input validation gap, not a claim about numerical superiority of any method.

**Correction:** validate reducer and diagnostic identifiers against the supported method set before admission/freeze and before any lane initialization or worker/call. The late lane rejection predates this PR; the new admission layer fails to reject the unsupported declaration. Do not expand this finding into untested seed or duplicate-lane claims.

Evidence: `UNKNOWN-METHOD-FIXTURE.json`; reproducer: `run_method_fixture.py`.

## Source-only applicability limitation

`headroom.py:859–862` obtains the current execution identity. `headroom_evidence.py:57–64` includes Python version, architecture, kernel, and worker environment but no host CPU model, affinity, quota, or allocated core count. Identical software/image/kernel fields can therefore match across different hardware or allocations, even though measured phase CPU costs can differ.

Declare the hardware/allocation applicability of a profile, or define an explicit portability/reprofiling policy. This observation has **not** been reproduced across two machines; it is a forecast-applicability limitation, not a demonstrated runtime-stop bypass. Hardware binding would still not turn sample means into a guaranteed bound.

## Checks that held

- Missing profiles refuse before calls or output creation; available capacity is checked again while the ledger lock is held.
- Profile byte digests, profile-header/current-identity equality, and embedded record/summary consistency are checked. Finding 2 concerns the separate record-to-attempt provenance relationship.
- Existing fixed v4 expiry and retained-charge checks remain. Independent source review found no new v4 verified-witness or partial-reference PASS bypass.
- Historical schedules and evidence were not changed by this review. Previously closed CPU findings are not reopened here.
- `evidence_profile.py:1–4` explicitly says means plus reserve are a forecast, never a hard bound; admission returns `forecast_is_bound=false` and `requires_runtime_stop=true`.

The author-body assertion relayed by the parent that this prevents future cap-induced INCONCLUSIVE is stronger than the implementation supports. The defensible claim is **forecast-based refusal before start plus continuing runtime metering/stopping**. Admission cannot guarantee completion from measured means and a reserve alone.

## Verification and limits

**53 selected existing tests passed; zero failures/errors.** These cover `test_evidence_profile`, `test_headroom.GateFunctionTests`, `GatePassDynamicTests`, `MeshValidationTests`, and `test_headroom_evidence.EvidenceRunnerTests`. The retained run records approximately 3.0484 seconds wall time and 1.56564 seconds process CPU, with Python 3.12.3 in WSL Ubuntu-24.04. See `FIXTURE-TESTS.json` and `FIXTURE-TESTS.log`.

The counterexamples use the existing `CountingOracle`, an overridden execution identity, and mocked `os.fsync` for finite fixture execution. They use disposable temporary directories; scripts and captured JSON retain the reproduction evidence. An audit hook rejected process/network launches; no forbidden launch attempt was observed. No dependency installation, thermal solve, build, profiling, model/provider call, GPU work, CI run, grant, or external post occurred.

A second reviewer independently checked findings 1, 3, and 4 against the saved artifacts and exact source. The compact unknown-method output retains the verdict and counts, not the temperatures/threshold needed to recompute PASS arithmetic from that JSON alone; the retained script reproduces the full execution path.

An initial review-wrapper invocation used an incorrect parent-directory index and aborted before tests. The wrapper path was corrected; the retained successful run is the evidence above. This was a review-harness issue, not a product failure.

To rerun the bounded fixtures from PowerShell, with the exact checkout retained:

```powershell
wsl -d Ubuntu-24.04 -- /usr/bin/python3 -B '/mnt/c/Users/carth/Desktop/projects/PlexAura_Inc/SentinelLayer/AIdenID/tasks/sentilab-review-2026-10-30/pr55-18f0dca-gates/run_fixture_review.py'
wsl -d Ubuntu-24.04 -- /usr/bin/python3 -B '/mnt/c/Users/carth/Desktop/projects/PlexAura_Inc/SentinelLayer/AIdenID/tasks/sentilab-review-2026-10-30/pr55-18f0dca-gates/run_method_fixture.py'
```

Rerunning overwrites the captured fixture outputs and requires resealing. `SOURCE-MANIFEST.json` records the source state and hashes; `SEAL.json` binds this report and the retained review artifacts. Parent review should combine these findings with the separately owned worker and supervisor review before requesting any +1.
