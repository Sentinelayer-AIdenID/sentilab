# Deck numbers: SentiLab hackathon (8 headlines)

Each entry gives the number, its label, its source and a one-line caveat. **MEASURED** means read from a record. **ESTIMATE** means driven by stated assumptions and always given as a range. Sources point to `QUANT.md` sections and team-room (`608657e4`) or help-room (`32a841e5`) messages. Exact values and every method are in `QUANT.md`.

---

**1. 90 pull requests merged since 2026-10-31 00:00 UTC (121 opened), with a median of 44 min 28 s from open to merge.**
- MEASURED. Source: code-host API, read 2026-11-01 00:22–00:27 UTC, across our 7 repositories (`QUANT.md` §2.1).
- Caveat: the 90 include product repositories as well as the hackathon ones; 67 are in the SentiLab repository.

**2. 5 min 46.2 s median from a founder's ask to the first delivered result, across 9 asks (range 46.6 s to 52 min 57.3 s).**
- MEASURED. Source: room timestamps, ask post to delivery post (`QUANT.md` §1.1, items T1 and T3–T10).
- Caveat: "first delivered result" is the first post that delivered what was asked; some items had later completion steps (`QUANT.md` §1.1).

**3. 80 of 190 review findings (42.1%) were first recorded by a second agent reviewer; 17 of them at a version another agent had already approved.**
- MEASURED. Source: the team's catalog of the project-room log, version 2 (team room #57392; `QUANT.md` §2.4).
- Caveat: the reviews weren't blind, so this is descriptive, not a controlled test.

**4. The published reference temperatures were reproduced: 75.48 °C exactly (Δ 0.00 K) and 115.93 °C against 115.94 °C (Δ −0.01 K). The run took 12 metered calls and 23.0 CPU-seconds of the 562 reserved.**
- MEASURED. Source: team room #57377 (`QUANT.md` §1.1 T12, §3.4).
- Caveat: the scope is this simulator build, at grid 64, on the block-centre metric only. The operator verified it, and a second reviewer's re-derivation was in progress when it was posted.

**5. On the edge GPU box, an adapter trained in 67.271 s, and exact fixture answers went from 0/20 to 20/20.**
- MEASURED. Source: team room #57413. The runs are dated 2026-10-31 07:48–11:40 UTC (`QUANT.md` §5).
- Caveat: this is fixture learning and plumbing evidence on six training-seen cases. GPU utilization and energy were not recorded.

**6. 9 outside teams were helped in our open help room; the first host answer came in a median 28.6 s (exact 28.5775 s, n = 22).**
- MEASURED. Source: help-room participants and the frozen help ledger (2026-10-31 23:03 UTC), plus the host's answer log (`QUANT.md` §4).
- Caveat: our own model classified the help events. Recipient-confirmed help comes from the 16:00 UTC confirmed-help table. Latency is measured from the host receiving the message; from room timestamps the median is 30.651 s.

**7. $5,112.39 cloud cost posted for 2026-10-31, all projects; AI model usage is $5,063.62 of it, including $17.48 for the review gate.**
- MEASURED. Source: the cloud provider's actual-cost report, read 2026-11-01 00:30 UTC (team room, reply under #57400; `QUANT.md` §3.1).
- Caveat: the day is still posting, so the figure can only rise. It covers all work on the account, not only the hackathon. It is a separate meter from our per-agent estimates; they overlap, so never add them.

**8. 360–720 engineer-hours ($28,800–$72,000) would have been needed for the 90 merged pull requests; that is 5.587×–13.966× (about 5.6×–14×) the day's measured cloud and CI spend of $5,155.24.**
- ESTIMATE. Assumptions: 4–8 engineer-hours per merged PR and $80–$100 per hour. Both are internal assumptions, not an external benchmark (`QUANT.md` §3.6).
- Caveat: there is no matched human baseline. The measured spend also pays for non-PR work, so the cost side is overstated.
