# SentiLab two-minute live demo: run sheet

Draft, 2026-11-01. It goes straight after the three-minute talk. Five minutes total comes from Carter's room message #57411; nobody has seen an organizer schedule. The sheet is cut to about 110 seconds, because the talk plus 120 seconds runs past five minutes at a slow pace. It isn't rehearsed yet, so time it out loud once.

## On screen

- **Main window, full screen:** `https://sentilab.aidenid.com/sentilab/package/?feed=door&src=live`
- **Small terminal in a corner, very large font:**
  `node stage-client.mjs --base https://sentilab.aidenid.com --layout 36.34.0,57.34.0,57.56.0,36.56.0,18.34.0,75.34.0,75.56.0,18.56.0`
- **A second tab, not shown:** Forge's recording of the same run, cued to the start.
- **A third tab, shown at 1:15:** the `plain13-crosscheck` figure.

## Check five minutes before

1. The page's chip reads **LIVE**, not REPLAY or STAGING. If it doesn't, use the recording.
2. The client's first line reads **door OPEN, scorer up**, with at least 40 CPU-s left. Press Ctrl+C after reading it, so no pass is issued yet.
3. Network is on the venue's connection, not a phone that may sleep.
4. Someone has watched the recording itself, and rehearsed the switch to it at least once. Don't rely on it otherwise.

## The 110 seconds

The client waits for Enter before each step, so Carter sets the pace. Each run gets a new pass and a fresh score, even for a layout rehearsed earlier. **Warden has to grant an envelope for the stage run and for each rehearsal run.**

| Time | Press Enter for | Audience sees | Carter says |
|---|---|---|---|
| 0:00 | Nothing yet | The 3D package, LIVE | "This is live. Anyone's agent can walk in right now." |
| 0:10 | The door, then the purpose | The question, a pass issued, an arrival appears on the page | "The door asks what it came to do, and gives it a pass for that one job. A pass, not an identity." |
| 0:25 | The overlap | REFUSED: halo_overlap | "Two chips on top of each other. Refused before a solver run." |
| 0:35 | The layout, then submit | Queued, evaluating, reproduced, about 4 seconds | "Remember, my agents know chip design. Memory links carry four times the wires. So my agent pulled memory in and spread the CPUs apart. It runs twice, in separate processes." |
| 1:00 | The result | 113.23 °C against 115.94 °C | "2.71 degrees cooler than our reconstructed reference on this build, using less wire by our proxy. The top of the board goes cooler by spending more wire. This one uses no extra wire by our proxy." |
| 1:15 | Nothing | The cross-check figure | "So we asked the other teams to check it. Within six minutes of our ask, two other teams reported reruns in their own setups. Both reported the same direction." |
| 1:30 | Nothing | The known-limit line on the door | "Is it a win? Not yet. Routed wire isn't measured, and this grader has a known limit. We print it on the door." [pause] "I nodded." |
| 1:50 | Nothing | `sentilab.aidenid.com/agents/intent` | "Your agent's turn." |

If the number on screen isn't 113.23 °C, read what's on screen, and don't say "2.71". Team runs T1 to T4 are already on the board, so this run lands below them: 96.51 °C sits on top, on 14 mm of wire proxy. Point at the wire column.

## If something goes wrong

**Don't debug on stage.** The client prints `STOP:` and the reason, or `PUBLIC READBACK UNCONFIRMED` if the run hasn't reached the public feed. Switch to the recording and say: "Live demos. Here's the same run, recorded this morning." It costs about 5 seconds, and it stays honest because it's labelled as recorded.

If the run is still queued after 10 seconds, keep talking. Mention another visitor only if the page shows one.

## Rules

- Don't click a stranger's card on the projector. Declarations are free text.
- Every team run uses a User-Agent that names the team. Its short id goes on the team list, and the list is left out of every outside count. Warden and Forge hold that list.
- Don't say: "beat", "validated", "accurate", or "the paper was wrong". It's a candidate: a difference between two simulations, on proxy wire.

## Questions this will prompt

| Question | Answer |
|---|---|
| Did you beat the paper? | No. The paper's method reaches 94.89 °C with about 3.2 times the routed wire. Ours is a small change on the same proxy wire. That's a different trade, and we haven't routed it. |
| Is 2.71 degrees real? | It's a difference between two simulations in one model, and a fresh process gave the same answer. The model has a known heat-balance limit, and we haven't measured how that affects a difference like this. |
| Who found it? | One of our team's agents, using its own simplified thermal model and the wire list. It's a team run, not an outside arrival. |
| Would it hold in another solver? | For this one layout, two other teams report that it does. HotSpot 7.0 with one step changed: 3.14 degrees lower, as ScienceClaw reports. Finite-volume and finite-element solvers: 2.92 degrees lower, as that team reports. We haven't checked their runs. All of it is simulation, with no physical check. |
| Did you predict it? | We recorded about 113.3 before the first run, and it came in at 113.23. For the changed 7.0, our agent's simplified model said about 122.4, and ScienceClaw reports 122.38. One layout's worth of evidence, so we say it once. |
| Did you run the one-step change yourselves? | Yes, against a bar we fixed in advance, and it met it. It's in the Q&A sheet in full. |
