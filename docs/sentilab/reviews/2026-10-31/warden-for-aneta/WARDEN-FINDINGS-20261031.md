# Warden findings: why SentiLab lands on INCONCLUSIVE, and what it takes to match a human-built package
Independent: written before reading astra's or forge's reports. Frozen 2026-10-31 13:16Z; I'd seen only forge's one-line preview, after this draft was written. Evidence is at sentilab origin/main 4b1fc00 unless noted. [V] means verified at source; [E] means an estimate with its arithmetic shown; [H] means a hypothesis that still needs verification.

## 1. INCONCLUSIVE was a budget failure, built in before the first solve, and partly mine
- [V] The declared v3 protocol was 768 cheap calls plus 4 × 1,000 long-SA calls, at a measured 0.5435 CPU-s per call. That's **43.2 CPU-min, against a 24 CPU-min cap** that I co-signed as allocator (#56067/#56093; PREREG.json:20-25,96). Timing data showing about 0.49 s per call existed at 05:37Z, before the 06:05Z freeze. The cap bought exactly the 2,650 calls that ran, so long-SA seeds 102 and 103 got 0 calls.
- [V] The numeric bar was **met**: gap 1.595 °C against 5e = 0.80 °C (`numeric_threshold_met: true`). The missing seeds could only lower `best`, so they could only widen the gap. The blanket rule "any run incomplete ⇒ INCONCLUSIVE" (headroom.py:935) discarded a determined outcome. v4 fixes the rule (monotone PASS), but **v4 never ran**: it's HELD, and its latency is null (PREREG-v4.json:165-169; SUPERVISOR-POLICY.json:23).
- [V] After the run, 12 branch commits went into a 0.29 CPU-s overshoot, not the science. No headroom solve has happened since 06:55Z.

## 2. Even a PASS would not have answered your question: nothing compares against a human package
- [V] The experiment pits cheap search against long search (PREREG.json:4). The "initial layout" is a **hand-authored probe placement** (headroom.py:34; PROBE_README.txt:14-18), scoring 118.89 °C, not a vendor package. Grep finds zero references to the real Ascend 910 package (HBM, CoWoS, Huawei).

## 3. Our "better" layouts are ones no package engineer would ship
- [V] The score is the peak temperature only (controller.py:512-529). The winners push the 4 HBM-sized stacks from 5 mm to **13–23 mm** away from the compute die, so wire length grows **+46–56%**. Only **1 of 24** reducer winners passes our own live gate's wire cap (gate.py:55-71), and that one is the unchanged starting layout.
- [V] Upstream TAP-2.5D, which we vendor, scores temperature AND routed wirelength (sim_annealing.py:77-104) and allows rotation. We dropped both.
- Real HBM must sit right at the SoC edge for its interface. Under that constraint, Ascend910's thermal headroom is probably close to zero.

## 4. Ascend910 is flat by physics; the search wasn't weak
- [E] One 256 W die carries 73% of the 350 W, at 56 W/cm², while the HBM and IO dies run at 22 and 8 W/cm². Self-heating is about 92% of the 74 K rise, so placement can move the peak by at most **about 2.5–3 K**. We found 2.8 K (118.89 → 116.09). That's the physics ceiling, not a failure.
- [V/E] **micro150** (4 × 150 W at 202 W/cm², 680 W) is the placement-sensitive fixture. Its measured spread is SD 18.2 K against Ascend's 0.91 K, with expected headroom of **10–20 K against a 3.95 K bar**. It never ran: v3's parser was Ascend-only, and its mesh error merged mid-run.

## 5. The model's absolute calibration is suspect
- [H] The vendored HotSpot detailed-3D coupling appears to put the convection term between the spreader and the sink, about 1.8 cm²K/W. That would add an estimated **+40–50 K placement-independent offset** and shrink lateral spreading.
- Symptom: the model puts an HBM that sits right next to the die at about 98 °C, above HBM's 85–95 °C limits. But that adjacent layout is exactly how the real chip ships. A model that cooks the human package's HBM is miscalibrated. It needs one check by astra or root before we lean on absolute numbers.
- [V] Also: uniform power per die, grid 32 (finalists never re-solved at 64), and no rotation.
- **Live loop:** it runs grid 16 (e16 = 0.86 °C) but accepts improvements over 0.32 °C, a margin sized for grid 32. So the public demo can accept noise (conductor.py:48-50).

## 6. No AI ever proposed a layout
- [V] The live loop runs seeded operators with AI off, at 20 candidates an hour or fewer. The admission registry is empty and the labs are canned replays.
- [V] Each gate waits on the one before it: headroom PASS → 041 freeze → LLM labs. It stalled on the first.
- My process failure: I spent the night carrying infrastructure PRs (CI allocation, conformance, view versions, voice) instead of escalating the stalled science chain.

## 7. Matching the human package: the target
- PENDING: my literature thread (the TAP-2.5D benchmark numbers, the real Ascend 910 package layout and how to digitise it) was still running at freeze time. It will be added as a separately hashed, dated addendum. Nothing above depends on it.

## What I propose we decide, then ticket
- **A. Human reference first-class.** Source and coordinates: see the literature addendum. Digitise it with provenance. Score it in our oracle. It becomes the target and the floor.
- **B. A real objective.** Hard constraints: each HBM ≤ 1 mm from its SoC edge, halo spacing, no overlap, rotation allowed. Wire length ≤ 1.05 × the human layout. HBM ≤ 95 °C. Report peak J plus per-die temperatures.
  - "Matches human" = J ≤ J_human + 2e and wire length ≤ 1.05 × WL_human.
  - "Beats" = Pareto-dominates the human layout by more than 2e.
- **C. Calibrate before claiming.** Reproduce one published human-layout number. Verify or fix the spreader–sink coupling. Re-score every finalist at grid 64.
- **D. Re-run with an honest protocol.** micro150, plus Ascend910 with constraints.
  - Caps are computed in code from measured CPU per call × declared calls, and the run refuses to start if it can't fit.
  - Budget-matched curves, medians on both sides, a monotone PASS, and a bootstrap bound. About 2 CPU-h [E]. With the budget unlimited, CPU isn't the constraint; honesty is.
- **E. Layout-proposer boxes,** as Carter offered. Several LLM labs propose layouts against the constrained oracle at an equal solve budget to SA, with every proposal signed into the flight record. Judged against the human reference, not against each other.
- **F. Live loop.** Accept margin ≥ 2 × e of its own grid (≥ 1.72 °C at grid 16), or move to grid 32.
