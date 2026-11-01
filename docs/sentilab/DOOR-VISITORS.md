# Public Door visitor records

This additive API draft reuses the existing arrival event store. It does not deploy
an endpoint, automatically collect referrer URLs or query strings, establish current
presence, or change solver admission.
Passive arrival intake and visitor reads do not require scientific admission to be
open. The existing origin-token middleware still guards these routes; submit and
dispatch keep their existing grant checks.

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
characters, reason 160; controls and bidi overrides are rejected. Source is one
of `moltbook`, `senti`, `github`, `direct`, `other`. URLs and arbitrary referrer
text are not accepted as source-category values. The overall 4,096-byte request
cap is unchanged.

Names that normalize to the interface labels `human`, `you`, `senti`, `participant`,
`unidentified participant`, `system`, `owner`, `admin` or `moderator` are refused.
The comparison matches the Worker: NFKC, remove Unicode format characters (Cf),
collapse ECMAScript whitespace runs, trim and lowercase. A refused name returns
`schema_invalid` at `/declaration/name` with keyword `not`, before storage.
This comparison does not rewrite accepted text or apply to the reason field.

The declaration is public self-reported display data, including in `/events`.
All accepted name and reason text is public, including any URL, query string or
credential text a visitor voluntarily enters. No content scanner removes such text;
the notice tells visitors not to include private information. Referrer URLs and
query strings are not collected automatically, and the raw purpose-pass credential
is not added as a generated feed field.
Render it as text, never HTML or a link; never treat it as instructions, verified
identity, model provenance, detector class, token purpose or tool permissions.
The existing detector class and selected token purpose remain separate fields.
For opted-in arrivals carrying a nonce, the server also publishes an opaque
challenge-keyed `visitor_handle`. It links uses of the same purpose pass. It is
not an account, person, or permission. The nonce and operator input fields are not
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
nullable `visitor_handle`, and nullable `declaration`. Its seq is the click-detail
key. New arrivals can be appended while paging; existing records are not rewritten.

Counts describe the same database snapshot as that page:

- `recorded_arrivals` counts accepted arrival events, including repeat visits.
- `arrivals_by_class` keeps detector labels distinct: `likely_human` is a
  classification, not proof of human identity. Do not merge unknowns into humans.
- `unique_observed_handles` counts distinct opted-in purpose-pass handles; it
  excludes legacy/anonymous rows without one and never means unique people.
- `arrivals_without_handle` makes that missing coverage visible.
- `through_seq` identifies the latest arrival included in those counts.

`current_presence` is always `{ "status": "not_measured", "count": null }`.
An arrival is not a heartbeat, live connection or running agent. The live view
may show human-classified arrivals as arrivals, without calling them currently
online. Actual presence needs a separately defined heartbeat/expiry contract.

Worker ownership remains with Forge/Warden, renderer ownership with the existing
live-view author. They must add the public proxy route and prospective notice
before using the opt-in fields. No full HTTP-traffic coverage is claimed.
Until that proxy is deployed, a 404/403 or a failed fetch means the visitor source
is unavailable, never zero visits or an empty live room. The renderer must retain
that distinction and the API's explicit unmeasured-presence state.
