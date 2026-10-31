# Why INCONCLUSIVE: independent analysis by aneta-claude, 2026-10-31

Informed by warden's brief #56713, so not blind. Written before reading your frozen reports. Technical only: no spend, and none of Aneta's time.

## Bottom line

**The evaluator's physics is the first problem to fix.** I wrote my own thermal network from the public HotSpot and TAP-2.5D source. With HotSpot 6's vertical coupling, it lands within 0.4 K of the paper's two original layouts. With HotSpot 7's, the rise is about 2.6 times higher. Nearly all of that excess is one link, from spreader to sink.

| Layout, 45 mm, 64x64, 45 C ambient | Paper | HotSpot 6 form | HotSpot 7 form |
|---|---:|---:|---:|
| Ascend 910 original | 75.48 | 75.09 | 122.32 |
| CPU-DRAM original | 115.94 | 116.27 | 229.35 |
| CPU-DRAM, CPUs at corners (TAP) | 94.89 | 92.52 | 159.87 |

The rise ratio is 2.57 on Ascend and 2.59 on clustered CPU-DRAM. You report about 2.3.

## (a) Calibration

**The coupling hypothesis holds in the public source.**
- HotSpot 6.0 (`uvahotspot/HotSpot` a7a3286e36): in detailed-3D, `BC_det3D` makes the link from layer n to n+1 equal `rz(n)`.
- HotSpot 7.0: the detailed-3D branch of `find_res` makes it `rz(n)/2 + rz(n+1)/2`.
- Both add `r_convec * s_sink^2 / (cw * ch)` to the sink's `rz` (v6 line 833, v7 line 1056), and both also use that `rz` from sink to ambient.
- So v7 puts half the convection in series between spreader and sink, as well as all of it from sink to ambient.
- Drop across that link on Ascend: **54 K with the v7 form, 1.3 K with v6.** Copper on copper shouldn't lose 54 K.
- v7's non-detailed branch keeps the v6 form, and TAP-2.5D runs with `-detailed_3D on`. This looks like a v7 defect for this link. I haven't run v7, and I can't read your vendored copy.

**What else could produce it, each changed alone on Ascend (HotSpot 6 form, rise 30.1 K):**

| Suspect | Rise | Verdict |
|---|---:|---|
| `r_convec` left at 0.1, not rescaled | 66.0 K (2.19x) | **A second route to about 2.3x. Must be ruled out** |
| Spreader 1.2x, sink 1.5x, `r_convec` rescaled | 38.1 K | Partial at most |
| TIM k=1, not 4 | 38.4 K | Partial at most |
| 50 mm, not 45 mm | 30.1 K | Not the cause (under 0.1 K), because TAP scales the package with the interposer |
| Grid max, not block center | 30.1 K | Not the cause on Ascend. It's 3.6 K on clustered CPU-DRAM |

**One run separates them.** Print the effective `r_convec`, `s_sink` and `s_spreader`, which TAP sets to 0.0111, 0.18 and 0.09 at 45 mm, or 0.009, 0.2 and 0.1 at 50 mm. Then read the rise above ambient at the hottest cell from `.grid.steady`:

| Cause | Spreader | Sink |
|---|---:|---:|
| Correct (paper's) | 26.5 K | 25.2 K |
| v7 coupling | 73.5 K | 19.2 K |
| `r_convec` not rescaled | 62.4 K | 61.2 K |

**Recommendation: use HotSpot 6.0 for the MATCH work.** It's what the paper used: commit a7a3286e36, or the binary in `TAP-2.5D/util/`. Taking convection out of v7's link doesn't reproduce the paper: it still gives 78.49 on Ascend (+3.0 K) and 126.78 on CPU-DRAM (+10.8 K). Whether v6 or a patched v7 is closer to real silicon is a separate question that neither answers.

Watch for this too: TAP writes `new_hotspot.config` only if it's absent, so a changed interposer size in a reused folder silently keeps the old package.

## (b) Claim contract: "matches a human-engineered package"

**Evidence that must all exist first.** Each is a node in the evidence record, so withdrawing one makes the claim stale.
1. **Reference record:** source, figure and page, each die's coordinates, how they were obtained, per-coordinate uncertainty, powers and interposer size. Ascend 910 is a shipped product, with positions read from a published figure, not CAD. CPU-DRAM comes from Kannan et al., MICRO 2015, so call it a human-designed research layout, not a shipped package.
2. **Reference round trip:** our evaluator and router on the reference reproduce the paper's numbers for it: temperature within 1.0 K and wire within 2% (Ascend 16,426 mm, CPU-DRAM 67,686 mm). Half a millimeter of digitizing error across Ascend's 1,224 links is about 3.7% of wire, so this is what pins the coordinates.
3. **Out-of-sample validation:** at least two other published layouts that weren't used to choose the configuration, such as Ascend compact 75.13 C / 23,794 mm, or CPU-DRAM TAP 94.89 C / 216,064 mm. A fitted scale factor can't support "matches".
4. **Same metric on both sides:** block-center max at 64x64 when comparing with the paper. Grid peak stays a diagnostic.
5. **One constraint checker** passes both the reference and the candidate. If the reference fails, the checker is wrong.
6. **Fresh-process reproduction** with a pinned binary hash, plus uncertainty U, the largest of: mesh difference at this layout, temperature change from perturbing the reference within its uncertainty, and replay difference.
7. **Discrimination control:** the same bar run on at least 100 random legal layouts, and on wire-only and temperature-only search. If more than 5% of random layouts pass, the claim gets labelled non-discriminating. Ascend needs this most: the paper's three layouts span only 0.35 K, so temperature alone can't tell them apart.

**Allowed verdicts:**
- **MATCH, strict wire:** wire <= reference with the same router, temperature <= reference + U, and temperature <= 85 C.
- **MATCH, relaxed r%:** the same, with r declared before the run and printed. TAP's own "comparable" answer is +1.04% wire.
- **BEAT:** dominates the reference on both axes, by more than U in temperature or more than the round-trip tolerance in wire. Lower temperature at more wire isn't BEAT. Report it as a trade-off, such as "21 K lower at 3.2x the wire". Always show the published TAP-2.5D points beside it, or we'd be presenting a 2021 result as new.
- **Feasible** is separate. Even TAP's best CPU-DRAM layout at 93.89 C is over the paper's 85 C line.

**Required label on every claim:** "Simulated with [evaluator and hash], steady state, uniform power per die. Reference reconstructed from a published figure. Not CAD, not silicon, not measured."

**Not allowed:** "matches a human package" without naming the reference, wire rule and U; "physically validated"; "optimal"; percentages of raw Celsius.

**ResultCheck doesn't decide MATCH.** One layout against one reference is n=1, so it correctly returns `insufficient_data`. It checks family-level comparisons. MATCH is a deterministic predicate for the gate, and I can add it to the contract as a vector-tested rule.

## (c) What you missed

1. **There was no gate zero, and I missed it too.** Nobody ran the evaluator on one published number before spending. One run would have shown about 118 against 75.48. I reviewed this plan twice and gave it a +1 without asking. Make it a blocking gate for every evaluator version.
2. **With the right physics, Ascend is a wire problem, not a thermal one.** 75 C is under the 85 C line, and TAP's code then gives temperature zero weight (`adpTWv2` uses a cutoff of 80 C in code, while the paper says 85 C). The false 118 C made temperature look like the problem. That may be part of why winners pushed HBMs away. The MATCH objective should be minimum wire subject to temperature <= 85 C.
3. **Withdraw every number from this evaluator; don't reinterpret them.** That covers headroom, the 1.595 C gap, mesh error, margins, "near-flat", and the wire-violating winners. Only physics-independent infrastructure survives. The evidence contract does this directly: withdraw the evaluator node and everything behind it goes stale. **That's also your strongest demo: a real error, caught by the team's own review, with the correction drill run on real results.**
4. **The CPU budget assumption may be wrong.** My unoptimized single-threaded solver takes about 2 s per layout at 64x64, against the paper's 23 s. The system is linear, so one factorization could serve many layouts in milliseconds, apart from chip-layer material changes. That could make long reference searches cheap, with full solves on finalists. Use it for references and diagnostics only, so arm budgets stay equal.
5. **TAP-2.5D itself should be the baseline.** Its code and results are public. Without it, any match may only restate its 2021 result.
6. **"Human engineers" only strictly fits Ascend 910.** See evidence item 1.

**Smallest honest result before the deck:** gate zero passes on Ascend and CPU-DRAM, then Ascend MATCH at stated wire with temperature <= 85 C and the discrimination control, plus the correction drill on the withdrawn numbers.

## Limits

- This is my own simplified model. I didn't run HotSpot or any room code.
- Lateral links use one form in both versions, heterogeneous cells are area-weighted, and microbump rings are left out.
- My layouts are hand-built from the paper's descriptions, not its coordinates. Ascend's temperature barely depends on layout, so its agreement is the stronger evidence. My clustered CPU-DRAM layout is a guess, and its block-center value moved by up to 1.7 K between mesh sizes, so its 0.33 K agreement may be partly luck. The corners layout is 2.4 K low.
- Residual: my v7 form gives 122 C on Ascend against your roughly 118 C, and 2.57 against your 2.3. Your layouts and configuration may explain that, but I haven't shown it.
- I haven't read your vendored source or your frozen reports. That comes next.

Model: `thermal-network.mjs` sha256 `2fedbad94e2644560fcb1555e62d7af87b1d0d9dc0d40b512f058aa82a6b1d39`. It needs only Node, and takes under a minute.
