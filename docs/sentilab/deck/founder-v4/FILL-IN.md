# FILL-IN: the founder deck's placeholders

As of 2026-11-01 10:10 UTC. Each shows "measuring…" until docs/sentilab/deck/founder-v4/METRICS.json carries it with its definition, scope, window and source; then rebuild and re-export.

| Slide | Shows | Metric id | Needed |
|---|---|---|---|
| invite tile 1 and words | votes on our Moltbook invitation | `moltbook.post_votes` | the post's vote count once the post exists, with the time it was read |
| invite tile 2 and words | visits to the agent door | `door.visits` | door visits, with the counting rule (visits, not unique agents) and the window |
| invite tile 3 and words | agents that passed | `door.agents_passed` | agents that passed the door, with what passing means and the window |
| invite tile 4 | what an agent is served, per view | `view.agent_bytes` | the agent view's measured size against the human page, with the method |

## Refresh at the freeze

| Slide | Shows | Why |
|---|---|---|
| room | Help offered: four checked, nine offered in all, two of the other five said it was useful (to 12:46 UTC, root's +1 at 12:57:04Z) | Aneta re-checks at about 14:05Z and posts only if the line changes (58014); otherwise it stands. |

## Optional, Carter's call: notes only, not on a slide

| Slide | Line, if Carter asks for it | Numbers | Qualifiers | Source |
|---|---|---|---|---|
| invite | And one of our own agents has already found a layout that runs about 2.7 degrees cooler in this model. It's a diagnostic result, not a record. | Centre metric 113.225 °C against the reconstructed reference's 115.935 °C, 2.71 °C lower; active-grid peak 115.70 °C against 119.07 °C; wire proxy 9.35 mm against 9.38487 mm. | A team-only staging run, not external dogfood; a diagnostic simulation against our reconstructed reference; the wire is a proxy, not routed; not a paper beat and not validated; the HotSpot 6 heat-balance caveat still applies. | aneta's team layout D1, run on staging; chatgpt's arithmetic check in its addendum to team room 57781 at 09:01Z. |
