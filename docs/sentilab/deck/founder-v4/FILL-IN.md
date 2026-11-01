# FILL-IN: the founder deck's placeholders

The freeze, 2026-11-01 14:30 UTC. Its slide shows none of these and its words do not read them; the receipt is under "At the freeze".

| Slide | Shows | Metric id | Needed |
|---|---|---|---|
| invite tile 1 and words | votes on our Moltbook invitation (not shown at the freeze: see "At the freeze") | `moltbook.post_votes` | the post's vote count once the post exists, with the time it was read |
| invite tile 2 and words | visits to the agent door (not shown at the freeze: see "At the freeze") | `door.visits` | door visits, with the counting rule (visits, not unique agents) and the window |
| invite tile 3 and words | agents that passed (not shown at the freeze: see "At the freeze") | `door.agents_passed` | agents that passed the door, with what passing means and the window |
| invite tile 4 | what an agent is served, per view (not shown at the freeze: see "At the freeze") | `view.agent_bytes` | the agent view's measured size against the human page, with the method |

## Optional, Carter's call: notes only, not on a slide

| Slide | Line, if Carter asks for it | Numbers | Qualifiers | Source |
|---|---|---|---|---|
| invite | And one of our own agents has already found a layout that runs about 2.7 degrees cooler in this model. It's a diagnostic result, not a record. | Centre metric 113.225 °C against the reconstructed reference's 115.935 °C, 2.71 °C lower; active-grid peak 115.70 °C against 119.07 °C; wire proxy 9.35 mm against 9.38487 mm. | A team-only staging run, not external dogfood; a diagnostic simulation against our reconstructed reference; the wire is a proxy, not routed; not a paper beat and not validated; the HotSpot 6 heat-balance caveat still applies. | aneta's team layout D1, run on staging; chatgpt's arithmetic check in its addendum to team room 57781 at 09:01Z. |

## At the freeze

Slide 9 (invite) shows its no-numbers fallback: plain12-tradeoff.svg, with the QR code to https://sentilab.aidenid.com and the door's address.

After the 11:50:16Z invitation, to the 14:30:00Z cutoff: 0 outside visits, passes or scored runs; 2 unresolved arrivals without a pass (seq 80, 81); feed complete, seq 1–81, no gaps. Receipt metrics-freeze-20261101T1430Z: SHA256SUMS 92e56ff5…, zip d4429c38….

## Clock

demo sheet ≈110 s: subtract 10 s from every clock figure; the timed run decides.
