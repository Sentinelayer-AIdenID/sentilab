# Door presence, run totals and the opt-in at the edge (AGENT-DOOR Amendment 4, rev 2)

This layers on root's visitor contract (`DOOR-VISITORS.md`, PR #89) and changes none of its shapes. It adds
the heartbeat presence that #89 publishes as `current_presence`, the run totals endpoint, and the Worker's
side of the opt-in. Fixtures: `web/test/fixtures/door-a4/`.

## 1. Heartbeat: `POST /api/open/v1/door/here`

A lab page sends this every 60 s while it is visible (`web/public/sentilab/here.mjs`).

- **Request:** `Content-Type: application/json`, body exactly `{"page", "tab"}`, at most 256 bytes.
  - `page` is one of `wall`, `package3d`, `live`, `board`, `results`.
  - `tab` is 32 lower-case hex: 128 random bits held in page memory. It is not a cookie and the page never stores it.
- **The Worker** checks the body and the per-IP limit, then forwards `{"page", "tab", "class"}` with fresh
  headers. `class` is the detector-qualified class: `likely_human`, `agent`, `bot` or `unknown`. It never
  forwards the client IP, user agent, cookie or Referer.
- **Answers** (all `cache-control: no-store`):
  - `204` when the tab is counted or refreshed.
  - `400 {"error": "bad_heartbeat"}`.
  - `403 {"error": "cross_site"}`.
  - `415 {"error": "unsupported_media_type"}`.
  - `429 {"error": "rate_limited"}`, with `Retry-After: 60`.
  - `503 {"error": "presence_unavailable"}`, when presence isn't measured on this deployment or the API can't
    be reached.

**What is kept, exactly:**

| Where | What | How long |
|---|---|---|
| API memory | `tab -> {page, class, last_seen}` | 120 s after the tab's last heartbeat; a sweeper erases it within 1 s after that |
| API memory | today's set of HMAC-SHA256(daily key, tab), first 16 bytes; the daily key is random | until the UTC day ends; set and key are dropped together |
| Worker memory | per client IP prefix: `{start, count}` for the rate limit | at most 60 s |

Nothing is written to disk. A restart starts the counts again. The hosting provider's network-level request logs
may record IP addresses under that provider's own policy.

## 2. `current_presence` in `sentilab-door-visitors/1`

- **Measured:** the API runs with `DOOR_PRESENCE=on` once the pages send heartbeats.
  `{"status": "measured", "window_s": 120, "active_tabs": {"total", "by_page", "by_class"}, "tabs_seen_today"}`
  - `active_tabs.total`: tabs whose last heartbeat came within the last 120 s.
  - `by_page`: all five pages, with zeros included.
  - `by_class`: all four classes, with zeros included.
  - `tabs_seen_today`: distinct tabs whose heartbeat was accepted since 00:00 UTC, or since the API started if that
    was later. A tab that comes back is counted once. The number is exact for accepted heartbeats. A refused heartbeat
    is counted nowhere: over the rate limits, or over the memory bounds (20,000 active tabs, 200,000 tabs a day). Once
    today's set is full, a tab not already in it is refused until the UTC day ends.
- **Otherwise:** `{"status": "not_measured", "count": null}`, exactly as #89.

These are tabs, not people. Labels say "active tabs (last 2 min)", never "people" or "humans online".

## 3. Run totals: `GET /api/open/v1/door/stats` -> `sentilab-door-stats/1`

`{"schema": "sentilab-door-stats/1", "through_seq", "passes", "submissions", "results": {"evaluated", "reproduced", "rejected", "failed"}}`

These are counted from the events the feeds serve, up to and including `through_seq`:

| Field | Count of |
|---|---|
| `passes` | arrival events that carry a purpose. Each purpose choice mints one pass. |
| `submissions` | `attempt` events plus runs: every submission the intake recorded. |
| `results.evaluated` | runs with a `run` event in state `evaluated` |
| `results.reproduced` | runs with a `run` event in state `reproduced` |
| `results.rejected` | `attempt` events: submissions refused before any run |
| `results.failed` | runs with a `run` event in state `failed` |

- Runs are told apart by `run_id`. `short_id` is never used as a key.
- Visitor counts come only from #89's `counts`.
- Answers are cached for at most 5 s.

## 4. The opt-in at the edge (the Worker)

- **The notice.** The purpose step shows the exact `notice.text` from `GET /api/open/v1/door/visitors`:
  - on the human form;
  - in the wall's JSON and markdown;
  - in the ENGRAM view (`declare.notice`).
- **The opt-in** is the visitor sending `notice_version`, equal to the notice shown, with the purpose. Only then
  are `name`, `reason` and `source` read. They are checked against #89's rules, and the Worker also refuses C1
  controls. Without that opt-in nothing typed is recorded. The pass is minted either way.
- **The answer.** The token page's `declaration` is one of:
  - `{"status": "sent"}`;
  - `{"status": "not_given"}`;
  - `{"status": "not_sent", "code", "detail"}`.
  It never echoes the text.
- **`?via=<source>`** (one of #89's source values) only pre-fills `source`: the form's selected option and the
  `declare.template`. It records nothing. On `/agents/` it shows classified agents the purpose step in place of
  the static index, with no arrival for that view.
