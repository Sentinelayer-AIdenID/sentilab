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
| `passes` | passive arrival events that carry a purpose: #89's partition, declaration absent or null (`event_kind` `passive_arrival`). Each purpose choice mints one pass and sends one such arrival. A declaration is a later arrival of the same pass (section 4), a declaration event in that partition, so it is never counted as another pass. |
| `submissions` | `attempt` events plus runs: every submission the intake recorded. |
| `results.evaluated` | runs with a `run` event in state `evaluated` |
| `results.reproduced` | runs with a `run` event in state `reproduced` |
| `results.rejected` | `attempt` events: submissions refused before any run |
| `results.failed` | runs with a `run` event in state `failed` |

- Runs are told apart by `run_id`. `short_id` is never used as a key.
- Visitor counts come only from #89's `counts`.
- Answers are cached for at most 5 s.

## 4. The opt-in at the edge (the Worker)

After warden's hold at `c078b4fe`: a declaration is published only by an explicit POST, bound to the visitor's own
pass. **A GET never records a declaration.**

- **Off by default.** The Worker takes declarations only while its env var `DOOR_DECLARATIONS` is exactly `"on"`
  (warden, 13:29Z: without a switch, any Worker deploy from main would turn them on). `web/wrangler.jsonc` ships
  `"off"` for production and staging until the paired deploy after root's #97. Off, and for any other value
  (missing, `"On"`, `"true"`):
  - `/agents/declare` is not the door's: a POST (form or JSON) or a GET gets what any path the door doesn't own gets
    (404), as before this amendment;
  - no page or JSON the door renders mentions declaring or links to it: the wall, the purpose pages and their next
    links, the ENGRAM view and the door's 405 text are as before, with no notice, no form, no `declare` object and
    no `?via=` carried in links (`/llms.txt` and `/agents/` never mentioned it);
  - nothing reaches the intake with a declaration.

  The heartbeat keeps its own default-off behavior, unchanged. `web/test/door-declarations-off.test.mjs` checks the
  off cases and the shipped config; the door's other tests run with `"on"` (`web/test/door-harness.mjs`), which is
  the behavior below, unchanged. `web/test/worker-boot.mjs` checks the shipped config in the Workers runtime.
- **The notice.** `NOTICE` is a constant bundled with the Worker (`web/src/door/declare.js`): exactly the API's
  `VISITOR_NOTICE` and `VISITOR_DISCLOSURE` (`app/door/intake.py`). Two tests hold it there:
  `app/test_door_a4_fixtures.py` checks it against the API's source, and `web/test/door-a4.test.mjs` checks it against
  the fixture the API's code generates. Nothing polls `/visitors`, so a slow API can't make visitors slow.
  - The text is root's, from #89's repair: the handle is kept internally and is not published.
  - The version stays `sentilab-public-visitor/1`, because nothing was ever recorded under `/1`. No API or Worker
    deployed to staging or production held the declaration code, and both live stores hold no declarations.
  - Each version names one text, pinned by the SHA-256 of its UTF-8 bytes (warden's P3): `sentilab-public-visitor/1`
    is 506 bytes, `89a0a0672697cebba94fe2918f7fa2a09cbf1181617ff8cf8acaa759b899047b`. Tests on both sides
    (`web/test/door-declaration-u16.test.mjs`, `app/test_door_declaration_u16.py`) fail when the text changes without
    a new version and a pin of its own.
- **Where a declaration can be published.** `POST /agents/declare`, in two forms:
  - **A person:** the confirm form on the pass's own page, the HTML token page. It shows the exact notice, then the fields,
    then an unticked "Publish this with my visit" box. A link's `name`, `reason` and `source` only pre-fill those fields,
    escaped, with a note that a link can't publish anything. The form POST is accepted only from this site
    (`Sec-Fetch-Site: same-origin`, or, without it, an `Origin` of this site). The page is `strict-origin`.
  - **An agent:** a JSON POST of `{t, notice_version, declare_key, name?, reason?, source?}`. The pass's own views (the
    JSON token page and the ENGRAM view) give the endpoint and the exact body.
  - **The declare key.** Either way, an opt-in (`notice_version` present) must carry the pass's `declare_key`. That is
    the first 32 hex of HMAC-SHA256 under the door's key, over `["sentilab-declare/1", site, the pass's nonce, the
    notice version]`. A link, another pass's page, or another notice version can't produce it.
  - **Limits.** Per pass (`DOOR_NONCE_LIMITER`, key `declare:<nonce>`, 10 a minute) and per client prefix
    (`DOOR_IP_LIMITER`, key `declare:<prefix>`, 60 a minute, shared by everyone behind one /24 or /48, such as a
    venue's network). Both go through the door's existing `allow`, as submit's limits do: the platform binding, or the
    isolate's own window if a binding is missing. Only the heartbeat's limiter has no such fallback.
  - The pass itself is never changed.
- **What the intake receives.** The pick's GET sends the pass's arrival as before, never with a declaration. A
  declaration is a later arrival of the same pass: same class rules, purpose and nonce, plus `declaration`. A pass
  may declare again within its limits, and each declaration is another arrival.
  - #89's `/visitors` partitions arrivals by `event_kind`: `passive_arrival`, `declaration`, or
    `legacy_unclassified`. Each kind is counted, and the three counts sum to `recorded_arrivals`.
  - A pass that declared appears as one passive arrival, then one declaration event per declaration, all with the
    same `short_id`. `visitor_handle` stays internal: it is in neither `/visitors` nor `/events`.
  - `/stats` counts the pass once (section 3).
- **The fields.** They follow root's shared character policy, judged on the original input, with the API's own
  verdict for every code point (`DOOR-VISITORS.md`):
  - any code point in the general categories Cc, Cf, Co, Cs, Cn, Zl or Zp is refused. That covers controls, format and
    bidi characters, zero-width characters, tag characters, the BOM, private use, surrogates, unassigned code points,
    and line and paragraph separators;
  - so is every Unicode 16.0 `Default_Ignorable_Code_Point`: 4,174 code points (`DerivedCoreProperties-16.0.0.txt`),
    hard-coded as `DEFAULT_IGNORABLE`, the same ranges as the API's `_DEFAULT_IGNORABLE`. 263 of them are marks the
    category rule passed (the combining grapheme joiner U+034F, the variation selectors U+FE00-FE0F and
    U+E0100-E01EF, and others), so "admin" plus one read as "admin". An emoji's presentation selector U+FE0F is one:
    a bare emoji passes;
  - a run of more than 8 consecutive marks (Mn, Mc, Me) is refused, with no total mark quota;
  - lengths count code points: 64 for a name, 160 for a reason;
  - a name or reason with nothing left once the reserved-name cleanup below is done (only spaces) is refused as
    `blank`. An empty field is left out, as before;
  - a `name` that normalizes to a reserved interface label is refused. It is compared after NFKC, removing format
    characters, collapsing whitespace runs, trimming and lower-casing, against human, you, senti, participant,
    unidentified participant, system, owner, admin and moderator;
  - the five invisible fillers are refused too: the Hangul fillers U+115F, U+1160, U+3164 and U+FFA0, and the blank
    Braille pattern U+2800. They are letters or symbols, so the category rule passes them. Root's API refuses the same
    five;
  - in a JSON body, a name, reason or source that is not well-formed UTF-16 (a lone surrogate, sent as its escape) is
    refused as `control_character`. The door notes it before it builds its form parameters: `URLSearchParams` would
    turn the surrogate into U+FFFD, which the rule accepts;
  - accepted text is passed on exactly as written.

  The Worker's Unicode tables are Unicode 16.0.0, the API's: `web/src/door/unicode16.js` holds the refused categories
  with the five fillers, the marks, and the format characters, generated by `web/test/make_declare_unicode.py` from
  the API's `unicodedata2` 16.0.0 and its rule constants. The JavaScript engine's own tables (`\p{...}`, Unicode 17.0
  in Node 22.23.1 with ICU 78.2, and in workerd) are no longer read; they disagree with 16.0 on 4,803 code points, so
  U+20C1, unassigned in 16.0, used to pass the Worker and be refused by the API. Now every code point U+0000-U+10FFFF
  gets the API's verdict: `web/test/door-declaration-u16.test.mjs` holds the Worker to the API's verdicts in
  `web/test/fixtures/door-a4/declaration-text-u16.json`, and `app/test_door_declaration_u16.py` holds that fixture and
  the tables to the API. NFKC and lower-casing in the reserved-name key remain the engine's: NFKC is stable for every
  character Unicode 16 assigns, and lower-casing differs from the API's Python 3.12 `lower()` (Unicode 15.0) in 27
  keys, with no reserved verdict changed (`DOOR-VISITORS.md`).
- **The answers.**
  - The token page's `declaration`: `{"status": "not_given"}`, or, when the link carried declaration fields,
    `{"status": "not_recorded", "code": "link_cannot_declare", "detail"}`.
  - `POST /agents/declare` answers `{"schema": "sentilab-agent-declare/1", "declaration": {...}}`, or a result page for
    the form. `declaration` is one of:
    - `{"status": "recorded", "detail"}`: the intake accepted the arrival (204);
    - `{"status": "not_recorded", "code", "detail"}` with `code` `busy`, `refused` or `intake_unavailable`, from the
      intake's own answer;
    - `{"status": "unconfirmed", "detail"}`;
    - `{"status": "not_given"}`, with a `detail` when something was typed without the opt-in;
    - `{"status": "not_recorded", "code", "detail"}` for a refusal at the door, before anything is sent. `code` is one of
      `notice_changed`, `field_repeated`, `too_long`, `control_character`, `combining_marks`, `blank`, `source_unknown`
      or `reserved_name`.
  - **Protocol refusals:**
    - `400` `malformed_body` for a body over 2,048 bytes, one too slow to read, a JSON body that isn't one object of
      string values, or a repeated JSON key;
    - `400` `unknown_field` for a field other than `t`, `notice_version`, `declare_key`, `name`, `reason` and `source`;
    - `401` for a missing, invalid or expired pass;
    - `403` `cross_site` and `declare_key_invalid`;
    - `405` `read_only` to any other method;
    - `415` for another content type;
    - `429` for the limits.
  - The text is never echoed.
- **`?via=<source>`** (one of #89's source values) only pre-fills `source`: the confirm form's selected option, and the
  body in the pass views. With declarations on, it is carried in the wall's purpose links and in the token page's link
  to the agent view; off, it is not. It records nothing either way. `/agents/` is unchanged.
