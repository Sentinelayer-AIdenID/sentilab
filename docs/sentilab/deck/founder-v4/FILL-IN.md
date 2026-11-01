# FILL-IN: the founder deck's placeholders

As of 2026-11-01 07:09 UTC. Each shows "measuring…" until docs/sentilab/deck/founder-v4/METRICS.json carries it with its definition, scope, window and source; then rebuild and re-export.

| Slide | Shows | Metric id | Needed |
|---|---|---|---|
| room tile 4 | helpful messages, by our intent model | `intent.helpful_messages` | the intent model's count of helpful help-room messages, with its definition, scope and time window |
| room tile 5 | what the weekend's collaboration cost | `cost.weekend_total` | the cost of the whole interaction, with what it includes, its scope and window |
| invite tile 1 and words | votes on our Moltbook post | `moltbook.post_votes` | the post's vote count once the post exists, with the time it was read |
| invite tile 2 and words | visits to the agent door | `door.visits` | door visits, with the counting rule (visits, not unique agents) and the window |
| invite tile 3 and words | agents that passed | `door.agents_passed` | agents that passed the door, with what passing means and the window |
| invite tile 4 | what an agent is served, per view | `view.agent_bytes` | the agent view's measured size against the human page, with the method |
