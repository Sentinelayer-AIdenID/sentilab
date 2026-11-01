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
- **The per-IP limit is the platform's rate-limit binding `DOOR_HERE_LIMITER`.** It is in `web/wrangler.jsonc`
  `ratelimits` for production (namespace `2026110105`) and staging (`2026110115`), with `simple: {limit: 300, period: 60}`.
  - The key is `here:<the client's /24 or /48 prefix>`.
  - The Worker keeps no limiter state of its own and has no fallback. A missing binding, a binding error, or an
    answer that isn't `{success: true|false}` refuses the heartbeat (`503 presence_unavailable`).
  - What the platform documents (Rate Limiting API, last updated 2026-10-21):
    - the period must be 10 or 60 seconds, and the limit is per Cloudflare location;
    - counts are approximate and eventually consistent, so a burst can pass more than the limit;
    - the docs say nothing about how long counters or keys are kept;
    - the docs advise against IP keys, because shared networks are limited together, which is why the limit is a
      generous 300 a minute per prefix.
- **Answers** (all `cache-control: no-store`):
  - `204` when the tab is counted or refreshed.
  - `400 {"error": "bad_heartbeat"}`.
  - `403 {"error": "cross_site"}`: a Sec-Fetch-Site other than `same-origin`, or an `Origin` of another site.
  - `405` with `allow: POST`, to any other method.
  - `415 {"error": "unsupported_media_type"}`.
  - `429 {"error": "rate_limited"}`, with `Retry-After: 60`.
  - `503 {"error": "presence_unavailable"}`, when the rate-limit binding is missing or failing, presence isn't
    measured on this deployment, or the API can't be reached.
- **The API's own answers to the Worker:** `204`; `400 {"error": "bad_heartbeat", "codes"}`; `429` with
  `Retry-After: 60`; `503 {"error": "presence_not_measured"}` without `DOOR_PRESENCE=on`. Only the exact path
  `/api/open/v1/door/here` takes a POST: any other spelling of it is the read-only API.

**What is kept, exactly:**

| Where | What | How long |
|---|---|---|
| API memory | `tab -> {page, class, last_seen}` | 120 s after the tab's last heartbeat; a sweeper erases it within 1 s after that |
| API memory | today's set of HMAC-SHA256(daily key, tab), first 16 bytes; the daily key is random | until the UTC day ends; set and key are dropped together |
| Platform rate-limit service | a count per `here:<prefix>` key, in 60 s windows, per location | the provider's policy; its documentation doesn't say |
| Worker | nothing | |

Nothing is written to disk. A restart clears these records and starts the counts again. The hosting provider's
network-level request logs may record IP addresses under that provider's own policy.

**The page line** (`web/public/sentilab/here.mjs` `HERE_LINE`): the agreed text (aneta #57921 with root's 09:01Z edits),
checked against this code clause by clause, and one sentence for the limiter that ships:

> We count active tabs, not people. While a tab is open, we keep its random id, its page, a guess at its type and the
> time it last checked in. Inactive entries are removed by a scheduled cleanup after the two-minute window. We keep a
> keyed digest of the tab id until the next cleanup after 00:00 UTC, so we don't count that tab twice today. Restarting
> the API clears these records. Our hosting provider's network logs may record IP addresses. To limit heartbeats, we pass
> your network address prefix to our hosting provider's rate-limit service, which counts them in one-minute windows; we
> keep no copy, and the provider's own policy governs how long its service keeps those counts.

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
  are `name`, `reason` and `source` read. They are checked by #89's rules, with its C1 repair:
  - controls (C0, DEL and C1) and bidi embeddings, overrides and isolates are refused;
  - lengths count code points;
  - a `name` that normalizes to a reserved interface label is refused. It is compared after NFKC, removing format
    characters, collapsing whitespace runs, trimming and lower-casing, against human, you, senti, participant,
    unidentified participant, system, owner, admin and moderator. This is defense in depth, since a declaration is always
    shown as "self-described", behind a click. The API's matching rule is a separate contract delta for #89;
  - the text is otherwise passed on exactly as written.

  Without that opt-in nothing typed is recorded. The pass is minted either way.
- **The answer.** An opt-in's arrival is delivered before the token page answers. The page's `declaration` reports
  what the intake did with it, from the intake's own answer, and is one of:
  - `{"status": "recorded", "detail"}`: the intake accepted the arrival (204);
  - `{"status": "not_recorded", "code", "detail"}`, where `code` is `busy` (the door's arrival limit held it back, or the
    intake answered 429), `refused` (the intake answered 400, rejected) or `intake_unavailable` (no intake configured);
  - `{"status": "unconfirmed", "detail"}`: a timeout, no answer, or an answer the door can't name, so it may or may not
    be published;
  - `{"status": "not_given"}`, with a `detail` when a name or reason was typed without the opt-in;
  - `{"status": "not_recorded", "code", "detail"}` for a refusal at the door, before anything is sent. `code` is one of
    `notice_unavailable`, `notice_changed`, `field_repeated`, `too_long`, `control_character`, `source_unknown` or
    `reserved_name`.
  It never echoes the text.
- **`?via=<source>`** (one of #89's source values) only pre-fills `source`: the form's selected option and the
  `declare.template`. It is carried in the wall's purpose links and in the token page's link to the agent view, so
  the agent view can pre-fill it too, and it records nothing. `/agents/` is unchanged.
