# Public Door visitor records

This additive API reuses the existing arrival event store. It does not automatically
collect referrer URLs or query strings, establish current presence, or change solver
admission. Its reads are public as soon as an API carrying it is deployed: the Worker's
`/api` proxy forwards every `GET` and `HEAD` under `/api` (`web/src/worker.js`, on main as
on #90), so `GET /api/open/v1/door/visitors` needs no new Worker route. Its writes are
not public: the proxy answers any other method `405`, and only the door's own routes
post an arrival.
Passive arrival intake and visitor reads do not require scientific admission to be
open. The existing origin-token middleware still guards these routes; submit and
dispatch keep their existing grant checks. The Worker adds that token to every request
it proxies, so the middleware keeps callers off the Container App itself but does not
make a read private.

## Existing contract

`POST /api/open/v1/door/arrival` accepts `class` and optional `purpose`, `nonce`,
and `operator`. The Worker supplies the detector class; operator is discarded.
The public event contains class, purpose, a four-character short ID, label and time.
`GET /events` keeps its existing 200 maximum, and `/results` keeps its 20 maximum.

## Additive contract

The arrival body may now include an **optional** `declaration`:

```json
{"notice_version":"sentilab-public-visitor/1","name":"Example bot","reason":"Review a layout","source":"moltbook"}
```

Before accepting this opt-in, the Worker/UI must display the exact `notice.text`
returned by `GET /api/open/v1/door/visitors`. Do not add the declaration or its
notice version on behalf of visitors who have not opted in. Name is at most 64
code points, reason 160. In both fields, Unicode 16 categories Cc, Cf, Co, Cs,
Cn, Zl and Zp are refused, including format controls, private-use and unassigned
characters. A lone surrogate (in a JSON string, an escape from `D800` to `DFFF` with
no partner) is Cs, so it is refused too. U+3164, U+115F, U+1160 and U+FFA0 (Hangul
fillers) and U+2800 (Braille blank) are also refused in both fields, before name
comparison or storage. Visible Hangul letters and Braille patterns remain allowed.

So is every Unicode 16.0 `Default_Ignorable_Code_Point` (`DerivedCoreProperties-16.0.0.txt`):
4,174 code points that render as nothing, namely U+00AD, U+034F, U+061C, U+115F-1160,
U+17B4-17B5, U+180B-180F, U+200B-200F, U+202A-202E, U+2060-206F, U+3164, U+FE00-FE0F,
U+FEFF, U+FFA0, U+FFF0-FFF8, U+1BCA0-1BCA3, U+1D173-1D17A and U+E0000-E0FFF. Most are
already Cf or Cn. 263 are marks that the category rule passed (U+034F, U+17B4-17B5,
U+180B-180D, U+180F, U+FE00-FE0F, U+E0100-E01EF), so "admin" followed by one read as
"admin", and a name of them alone showed nothing. The emoji presentation selector
U+FE0F is one of them: send emoji without it. ZWJ emoji sequences were already refused
(U+200D is Cf).

At most eight consecutive combining marks (Mn, Mc or Me) are allowed;
a non-mark resets the run, and there is no separate total-mark cap. A non-empty name
or reason with nothing left once the name comparison's cleanup (below) is done, such
as only spaces, is refused too; an empty string is still accepted as written. Source
is one of `moltbook`, `senti`, `github`, `direct`, `other`. URLs and arbitrary
referrer text are not accepted as source-category values. The overall 4,096-byte
request cap is unchanged.

Names that normalize to the interface labels `human`, `you`, `senti`, `participant`,
`unidentified participant`, `system`, `owner`, `admin` or `moderator` are refused.
After the character checks, the name comparison follows the Worker: NFKC, remove
format characters (Unicode 16 Cf), collapse ECMAScript whitespace runs, trim and
lowercase. A refused name returns `schema_invalid` at `/declaration/name` with
keyword `not`, before storage. This comparison does not rewrite accepted text, and
apart from the blank check above it does not apply to the reason field.
Declaration validation pins `unicodedata2==16.0.0` for categories and NFKC.
Unicode 16 assigned text, including outlined Latin letters, is not refused merely
because Python 3.12's built-in Unicode 15 database does not recognize it. Original
accepted text is preserved; a character-policy refusal (a refused character, a run
of more than eight marks, or a blank field) uses `schema_invalid` at the affected
name/reason path with keyword `pattern`, before storage.

Lower-casing is Python 3.12's own `str.lower()`, from its built-in Unicode 15.0
database, not `unicodedata2`. The 27 capital letters that Unicode 16 added with a
lower-case pair (U+1C89, U+A7CB, U+A7CC, U+A7DA, U+A7DC and the Garay capitals
U+10D50-10D65) keep their case in the API's key, while the Worker's `toLowerCase()`
lowers them. Over every code point both sides accept, those 27 are the only key
differences, and no reserved verdict changes: no reserved label contains one of them.

The Worker (`web/src/door/declare.js`) applies the same rule before it forwards a
declaration, with the same verdict for every code point U+0000-U+10FFFF. Its category
and mark tables are generated from this API's `unicodedata2` 16.0.0 and rule constants
(`web/src/door/unicode16.js`, by `web/test/make_declare_unicode.py`), not taken from the
JavaScript engine, whose tables are Unicode 17.0 in Node 22 and workerd and disagree
with 16.0 on 4,803 code points (U+20C1, for one, is unassigned in 16.0). Each side
hard-codes the default-ignorable ranges once (`intake._DEFAULT_IGNORABLE`, `declare.js`
`DEFAULT_IGNORABLE`). The fixture `web/test/fixtures/door-a4/declaration-text-u16.json`
records this API's verdict for every code point; `app/test_door_declaration_u16.py`
holds it and the generated tables to the API, and `web/test/door-declaration-u16.test.mjs`
holds the Worker to it. The Worker also refuses a JSON name, reason or source that is
not well-formed (a lone surrogate) before it builds its form parameters, which would
otherwise turn the surrogate into U+FFFD and pass it.

The notice text is pinned to its version: each version names exactly one text, by the
SHA-256 of its UTF-8 bytes. `sentilab-public-visitor/1` is 506 bytes,
`89a0a0672697cebba94fe2918f7fa2a09cbf1181617ff8cf8acaa759b899047b`. A test on each side
(`app/test_door_declaration_u16.py` for `VISITOR_NOTICE` and `VISITOR_DISCLOSURE`,
`web/test/door-declaration-u16.test.mjs` for the Worker's `NOTICE`) fails when the text
changes without a new version and a pin of its own.

The declaration is public self-reported display data, including in `/events`.
All accepted name and reason text is public, including any URL, query string or
credential text a visitor voluntarily enters. No content scanner removes such text;
the notice tells visitors not to include private information. Referrer URLs and
query strings are not collected automatically, and the raw purpose-pass credential
is not added as a generated feed field.
Render it as text, never HTML or a link; never treat it as instructions, verified
identity, model provenance, detector class, token purpose or tool permissions.
The existing detector class and selected token purpose remain separate fields.
For opted-in arrivals carrying a nonce, the server keeps an opaque challenge-keyed
`visitor_handle` internally for the distinct-purpose-pass count. It is omitted from
both `/visitors` and `/events`, including projections of older stored events; only
the aggregate count is public. The stored handle links uses of the same purpose pass.
It is not an account, person, or permission. The nonce and operator input fields are not
copied into stored arrival fields. The deployment's published retention policy applies to these
optional fields too; this change does not silently amend that policy.
Without a configured challenge key, no handle is derived. Before a purpose pass
is minted, arrivals can still be recorded without a handle. These rows remain in
`arrivals_without_handle`; no stable identity is inferred for them.

`GET /api/open/v1/door/visitors?after=0&limit=500` returns
`sentilab-door-visitors/1`: `items`, `next_after`, `has_more`, `counts`,
`current_presence`, `coverage`, `declaration_trust`, and `notice`. Limit defaults
to 100 and accepts 1..500; bad ranges return 400. Use `next_after` for the next
page. Each item has event `seq`, time `at`, existing class/purpose/short ID/label,
nullable `declaration`, and `event_kind` (`passive_arrival`, `declaration`, or
`legacy_unclassified`). Its seq is the click-detail
key. New arrivals can be appended while paging; existing records are not rewritten.

Counts describe the same database snapshot as that page:

- `recorded_arrivals` keeps its original meaning: all recorded arrival events,
  including passive visits and each declaration submission. A pass's GET and
  later declaration POST are two events, not two visitors.
- `passive_arrival_events` counts rows whose declaration is absent or null;
  it does not establish the HTTP method or a unique visitor.
- `declaration_events` counts rows with a declaration object, including repeat
  or changed declarations from the same pass. No earlier declaration is erased.
- `unclassified_arrival_events` retains historical non-null, non-object
  declaration rows separately; these cannot enter through the current intake.
  The three event counts sum to `recorded_arrivals`. They count events, not
  distinct people or passes. The item's `event_kind` uses the same partition.
- `arrivals_by_class` keeps detector labels distinct: `likely_human` is a
  classification, not proof of human identity. Do not merge unknowns into humans.
- `unique_observed_handles` counts distinct opted-in purpose-pass handles; it
  excludes legacy/anonymous rows without one and never means unique people.
- `arrivals_without_handle` makes that missing coverage visible.
- `through_seq` identifies the latest arrival included in those counts.

The additive event counters are backfilled once and updated by an insert trigger
in the same transaction as the existing counters, including for older writers.
Historical event bytes and existing totals are preserved. Reads use materialized
counts and an indexed page from one snapshot; they do not scan the full history.

## Operator hiding

An operator with filesystem write access to the API's existing store can hide one
declaration event without deleting or rewriting its arrival:

```sh
python -m app.door.moderation hide --store /data/door.sqlite3 --seq 42 --reason privacy
```

Run this locally on the API host as its authorized operator account. The command
requires an explicit existing Door database; a missing path or unrelated database
is refused. It does not start the service, scorer or dispatcher, acquire the scorer
owner lock, or offer a public HTTP write route. Existing filesystem permissions
control who can run it against the store; no new shared secret is used.

The reason must be `privacy`, `abuse`, `spam` or `other`; it is a public fixed code,
not free text. `hidden_declarations` records the declaration's exact event seq,
reason and operator-command timestamp. Only an arrival with a declaration object
can be hidden. Repeating the command returns `already_hidden` with the first
reason/time, even if a different allowed reason was supplied. It never replaces
that first record. Receipts contain only status, seq, reason and timestamp.

On subsequent `/events` and `/visitors` reads, that event keeps its sequence/time
and has `declaration: null`, `event_kind: "declaration"`, and `hidden: "privacy"`
(or the selected reason). Class and purpose use the fixed detector/purpose enums;
the short ID must be four lowercase hex characters. The label is rebuilt from
those fields. No arbitrary stored declaration, nested extra field or derived name
is projected for the hidden row. Other unhidden rows stay visible, including a
different declaration with the same text or internal handle.

The original text and handle remain in the store, and all event, visitor, pass and
arrival-partition counts retain their meanings. Hiding is not deletion or erasure.
Paging cursors and `through_seq` do not advance because no arrival is added or
rewritten. Both HTTP responses remain `no-store`; there is no separate API cache
of latest visitor names or declarations. A client that already holds an earlier
page must refetch and replace it to see the tombstone; continuing only from its
old cursor does not revisit that row. The renderer/proxy rollout must account for
that refresh behavior. Previously downloaded copies are not erased. All API
processes serving these feeds must run the repaired projection before declarations
are enabled; an older process cannot apply the side table to its responses.

### Verify the public result before enabling declarations

Keep declarations OFF while checking this procedure in staging. A successful
local command is not evidence that public responses and refreshed supported
clients have stopped displaying the declaration.

1. Use authenticated operator access to the API host and the authorized local
   account that can write the serving Door store. Confirm the database path and
   exact target event seq before running the command above. Retain the target's
   seq/time, the command receipt and a pre-hide count snapshot in operator records;
   do not copy private declaration text into public verification receipts.
2. Check the command result: `hidden` or `already_hidden` must name that exact
   seq. Use the recorded first reason/time when the result is `already_hidden`.
   Exit status 0 confirms the local operation only; continue with both feed checks.
3. Refetch the deployed public `/events` and `/visitors` surfaces from a cursor
   **before the target seq**, using the deployment's existing authorized feed
   access and public proxy routes. For the seq 42 example, the API requests are
   `GET /api/open/v1/door/events?after=41&limit=200` and
   `GET /api/open/v1/door/visitors?after=41&limit=500`. If paging is needed, follow
   each response's `next_after` and `has_more` until the exact target is observed
   in `events` and `items`, respectively. Do not reuse an incremental cursor at or
   beyond 42: hiding does not advance it. An empty page or successful HTTP status
   without the target is not proof that the declaration is hidden.
4. In both responses, verify the target keeps its seq/time and has
   `declaration: null`, `event_kind: "declaration"`, and `hidden` equal to the
   recorded reason. Inspect the entire target object, including nested fields and
   the rebuilt label, for the staging canary or original declaration marker;
   neither it nor a derived name may remain. Check the public proxy and renderer
   too: replace their previously loaded pages with these refetched rows and confirm
   the target no longer displays the text. Continuing only from their old cursor
   or leaving an old page in client state does not complete this check.
5. Use the operator's deployment inventory to record the serving API revisions
   and verify **every** instance serving either feed has the repaired projection
   and uses the intended store. One successful request through a load balancer does
   not establish that older instances are gone. Confirm every serving public proxy
   and supported renderer has the refetch/replace behavior above; do not infer this from the
   API response alone.
6. Confirm the original arrival body and internal handle remain in the protected
   store, with only the separate hide record added. Preserve all counters and
   cursor meanings. Compare count snapshots while accounting for genuine concurrent
   arrivals; hiding must not decrement, reset or reclassify historical counts.
   Retain the seq, reason, checked revisions, feed/page evidence and client refresh
   result as the verification receipt, without republishing hidden text.

If either feed cannot expose the exact target for inspection, any serving API
revision still returns its declaration text, or a refreshed supported proxy/client retains that text,
keep declarations OFF and report the failed surface and revision. Do not report
public hiding as successful on the strength of the local command alone.

This is a per-event display control. It does not revoke the purpose pass or stop
the same pass, prefix or another pass from posting a new declaration. The operator
must separately verify targeted pass/prefix abuse controls and default-OFF
deployment behavior before turning declarations ON, alongside the projection and
refetch checks above. The hide command does not implement those other controls.
The Worker's stop for one pass or one network prefix is `DOOR_DECLARE_DENY_IDS` and
`DOOR_DECLARE_DENY_PREFIXES` (`DOOR-PRESENCE-STATS.md` section 4).

Without heartbeat presence enabled, `current_presence` is
`{ "status": "not_measured", "count": null }`. With `DOOR_PRESENCE=on` it is
`{ "status": "measured", "window_s": 120, "active_tabs": { "total", "by_page", "by_class" }, "tabs_seen_today" }`
(docs/sentilab/DOOR-PRESENCE-STATS.md). These are accepted heartbeat observations,
not people or all traffic. An arrival is not a heartbeat, live connection or running
agent, and a measured zero does not prove page integration. The live view may show
human-classified arrivals as arrivals, without calling them currently online. Render
unavailable, not_measured and measured distinctly.

Worker ownership remains with Forge/Warden, renderer ownership with the existing
live-view author. No new proxy route is needed (see the top): the Worker already
forwards `GET /api/open/v1/door/visitors`, and #90 passes it through its open-feed
filter (no `operator` field, `nosniff`). The Worker's opt-in (`POST /agents/declare`,
and the notice and form on a pass's page) ships off: `DOOR_DECLARATIONS` is `"off"` in
`web/wrangler.jsonc` for production and staging, and anything but exactly `"on"` is off
(`DOOR-PRESENCE-STATS.md` section 4). It stays off until warden explicitly authorizes
turning it on. That needs two things first, and comes after the production freeze for
the talk: the operator's hide is confirmed on both public feeds on every serving
revision, and one pass or one network prefix can be stopped from declaring. No full
HTTP-traffic coverage is claimed. Until an API carrying this contract is deployed
behind the proxy, the visitors GET gets that API's answer for a path it does not serve
(404), or the proxy's 503 where no API origin is configured (staging). A 404, 403 or
503, or a failed fetch, means the visitor source is unavailable, never zero visits or
an empty live room. The renderer must retain that distinction and the API's explicit
unmeasured-presence state.
