# Forge: why SentiLab lands on INCONCLUSIVE, and what it takes to match a human-engineered package

Written 2026-10-31 at about 13:20Z, independently: I hadn't read warden's or astra's reports. Evidence is at sentilab origin/main (4b1fc00) plus the PR #25 commits (runner a2c7647). Full fact sheet with file:line cites: `forge-research/repo-forensics.md`. Each claim is tagged READ (in the repo), COMPUTED (from committed data), EXTERNAL (the TAP-2.5D paper, DATE 2021) or INFERRED.

## Claim 1: the INCONCLUSIVE is procedural, not a measured "no headroom"
- v3 rule: INCONCLUSIVE if any declared run is incomplete, regardless of the gap (`a2c7647:sundai_controller/headroom.py:438,489`). [READ]
- The gap did clear the bar: greedy median 117.685 C minus best 116.09 C = **1.595 C ≥ 5ε = 0.80 C**. [READ]
- Long-SA seeds 102 and 103 got **0 evaluations**: the 24 CPU-min per-fixture cap ran out after 2,650 of 4,768 declared calls. [READ]
- **The declared schedule could never fit:** 4,768 × 0.5435 CPU-s = 43.2 CPU-min, against a 24 CPU-min cap. The cap went 90 → 50 → 24 during the amendments, after timing data (about 0.49 s per call at grid 32) already existed. [COMPUTED; READ; foreseeability INFERRED]
- 10.2% of calls (269) re-evaluated a design identical to its parent on a deterministic oracle, so they bought nothing. [COMPUTED]
- **It can't be rescued on the current merge:** v4 is hard-coded to micro150, ε 0.79 and a 12:00Z deadline that has passed. The v3 long-SA winners were never re-verified, so under v4 eligibility the gap is 0.455 C, still INCONCLUSIVE. [READ; COMPUTED]
- Falsifier: reproduce the two long-SA winners (2 solves). If they don't match 116.26 / 116.09 C exactly, the oracle isn't deterministic, and that's a bigger problem.

## Claim 2: Ascend910 is the wrong benchmark. It's almost flat, and the published method found the same
- One 256 W die carries 73% of the 350 W. The peak sits on it in 353/353 grid-16 and 67/67 grid-32 heatmaps. [COMPUTED]
- Legal layouts span only 117.17 to 120.79 C on a ~72 C rise above the 45 C ambient. Placement controls about 6% of the rise. [READ; COMPUTED]
- Four distance features (other dies' proximity to the big die, plus edge and centre offsets) explain R² = 0.98 of J, with leave-one-out median error 0.05 C. In this benchmark, "search" means "keep the small dies away from the big one", and any heuristic finds that. That's why random search ties the best. [COMPUTED]
- **TAP-2.5D reports the same on Ascend 910: original Huawei layout 75.48 C, TAP-2.5D 75.47 C.** On its CPU-DRAM system (our micro150), the original is 115.94 C and TAP-2.5D reaches 94.89 C, **21 C of real headroom**. [EXTERNAL]
- micro150 is wired into our oracle and mesh study, and its J spans 159.7-231.5 C against a 3.95 C bar. But it's not in the live loop or the app, and its headroom run has never been done. [READ; COMPUTED]
- Falsifier: a micro150 run whose best-minus-cheap-median gap is < 5ε would make this claim wrong.

## Claim 3: we have never measured a human-engineered package, so "match a human package" has no anchor yet
- The repo has no original or vendor layout. The "initial" layout is a hand-authored probe. The plan's 114.82 / 105.28 C figures are hand-made micro150 layouts on a different metric, never reproduced. [READ]
- The paper's original layouts were recovered from its vector figures. The decoding lands exactly on TAP's 1 mm grid. [EXTERNAL]
  - **CPU-DRAM / micro150 original (Kannan et al., MICRO 2015) can be built in our fixture** after rounding to 1 mm and a +2.5 mm shift into our 50 mm frame.
  - **The Ascend 910 original cannot**: we have no per-die rotation, the Nimbus orientation is rejected by our catalog, and the paper uses a 45 mm interposer where we use 50 mm.
- Our "best" isn't something an engineer would build. The v3 search had no wire constraint, and the best design's wire proxy is 40.5 mm against 18.8 mm for the human Ascend layout. [READ; COMPUTED]
- Falsifier: evaluate the micro150 original in our oracle (2 solves). If it already sits near our best region with no headroom, Claim 2's micro150 half is wrong.

## Claim 4: our numbers can't be compared with any published package until the oracle is calibrated
- Our temperature rise above ambient is about **2.3-2.4×** the paper's on both fixtures, with the same TAP generator and package recipe. [COMPUTED vs EXTERNAL]
- Suspects: HotSpot 7 vs 6 package and heatsink handling; the 50 vs 45 mm interposer. The probe script itself says "HotSpot 7 without calibration against the original output". [READ; cause INFERRED]
- Until this is resolved, "we beat Huawei" or "we match TAP" is not a claim we can make in degrees. Only within-oracle comparisons are valid.
- Falsifier: run the paper's original layouts in a 45 mm, grid-64 fixture. Getting ≈ 75.5 C (Ascend) and ≈ 115.9 C (CPU-DRAM) would make the calibration gap a frame-size artifact.

## Literature corroboration (`forge-research/literature.md`, with links and quotes; 15 points marked UNVERIFIED)
- **Every paper on this 6-chiplet, 350 W Ascend model lands in a ~2 C band:** TAP-2.5D 75.13-75.48 C, RLPlanner 74.94-77.12 C, TACPAs 75.03-75.26 C, STAMP-2.5D 79.04-81.21 C. The TAP-2.5D authors say the system is "already operating below a critical temperature of 85oC".
- **Those tools switch temperature off for this chip.** TAP-2.5D, TACPAs and RLPlanner ignore temperature below 85 C, so at ~75 C they treat Ascend as a pure wirelength problem. Our peak-only objective optimizes exactly the term they zero out.
- **The only published "matches the commercial chip" claim is joint:** TAP-2.5D's 75.47 C vs 75.48 C AND wirelength +1.0% ("comparable to the actual solution of the commercial chip"). A suggested criterion: within ±0.5 C AND +5% wirelength, plus the same topology.
- **CPU-DRAM:** 115.94 C → 94.89 C, and the power budget at 85 C goes from 400 W to 550 W. Multi-GPU has no human layout. Two 2026 RL placers dropped Ascend and kept CPU-DRAM and Multi-GPU.
- **The real Ascend 910 has 8 dies, including 2 dummy dies** (1228 mm²; Hot Chips 31). The interposer size isn't published (an estimate of ~42 × 31 mm is UNVERIFIED), and TAP omits the dummy dies.
- **Settings matter more than layout on flat chips:** going from a 45 mm to a 50 mm interposer alone moves Multi-GPU by −2.51 C. On Ascend, thermal *gradient* differs 11-20% between layouts while peak moves 2.7% (STAMP-2.5D).
- **Novelty for the hackathon:** we found no LLM-driven thermal chiplet placer in the literature.

## What I think we should do: a proposal to challenge, then decide together
"Match a past package made by human engineers" becomes a measurable target:
- (a) Reproduce the human layout's temperature in a calibrated oracle.
- (b) Under the **same wire budget as the human layout**, have our agents find a layout at or below the human J, and report the gap in units of ε.
- (c) Compare against TAP-2.5D's published result as the state of the art.
- Use micro150 / CPU-DRAM as the primary benchmark: it has published human and optimized numbers and real headroom. Keep Ascend910 as the honest "already near-optimal" control. That's a good story too: "our agents learned when there's nothing left to gain".

Proposed tickets, cheapest first:
1. **REF-1, calibration anchor** (CPU, ~10 solves).
   - Add a 45 mm fixture variant and a rotate move.
   - Evaluate the decoded original layouts (micro150 and Ascend) at grid 32 and 64, and compare with 115.94 and 75.48 C.
   - Find the HotSpot config that closes the 2.3× gap, or document why it can't be closed.
   - Output: a frozen calibrated oracle hash.
2. **REF-2, human anchor in today's fixture** (CPU, 2 solves). Evaluate the micro150 original as is in our 50 mm fixture to get the first human J in our oracle.
3. **GOV-1, budget sizing as a pre-check.** A pre-registration can't freeze unless declared calls × measured CPU-s per call × 1.25 ≤ cap. Add a verified-partial rule. Skip no-op re-evaluations. Code only.
4. **SEARCH-1, engineering-realistic search space.** A wire cap at the human layout's wirelength (or a temperature-and-wirelength Pareto), plus rotate and jump moves for parity with TAP. Code plus tests.
5. **RUN-1, micro150 headroom v5.** Re-dated, sized by GOV-1, run on the calibrated oracle with the wire cap. About 4,800 solves at ~0.54 CPU-s, ≈ 45-60 CPU-min. Needs a warden CPU grant.
6. **LABS-1, more proposal boxes** (Carter approved). Several labs propose micro150 layouts in parallel under RUN-1's caps; the gate accepts only reproduced, verified results.
7. **VIEW-1, my lane.** Lab and Package views show the human reference layout next to our best, with J, W and the gap in ε, so judges see "human 115.9 → ours X at the same wire".
8. **ASC-1, Ascend910 re-adjudication as a control** (2 solves). Reproduce the two long-SA winners under a v5 verified-partial rule, and report it as a near-flat control, not a win.

What I'm least sure of, so please attack these first:
- (i) whether the 2.3× calibration gap is fixable in HotSpot config, or needs HotSpot 6 itself;
- (ii) whether the CPU-DRAM layout from Kannan et al. counts as "a past package made by actual human engineers" for Carter, since it's a published research design, not a shipped product. Only Ascend 910 is a shipped product, and it's the flat one;
- (iii) whether our decoding of the paper's figures is exact enough to serve as the reference.
