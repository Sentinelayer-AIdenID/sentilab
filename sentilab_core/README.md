# AI-off live service

This is a diagnostic integration slice: **AI off**, **provisional margin**, and
**same-solver reproduction**. It makes no claim of scientific acceptance or
independent physics confirmation. Ascend910 alone is released here. Its margin
defaults to 0.32°C (the ticket's provisional 2e); other fixtures need their own
reviewed configuration.

The conductor imports the existing proposal operators and HotSpot request/result
validation. It evaluates and reproduces each eligible proposal in separate fresh
processes, then compares the reproduced objective against the current board while
holding the ledger lock. A positive margin makes this sequential rule order
dependent. Arm exploration state is reconstructed from recorded measurements,
including valid losers. The wire cap is fixed at the initial layout's weighted
Manhattan wire proxy; it never follows the board.

Every run has an append-only, fsynced JSONL ledger with a run-scoped sequence and
idempotency keys. Opening or appending verifies the entire chain. A broken ledger
refuses writes. Read-only replay and the view expose the verified prefix and a
chain error; they never skip a gap to project later events. Byte-identical
retransmissions are ignored; conflicting ID/sequence groups freeze before every
member. Signed `values` are display data; the gate reads core records.
Only writers create lock sidecars. Readers open existing locks read-only and
can replay imported history without a sidecar; public GETs create no files.
New envelopes use `view-envelope/0.5`. Native history verification supports only
that version and `view-envelope/0.4`, preserving signed bytes. `verify()` and
`read_prefix()` accept `version=` to require either profile; the same stricter
native checks apply to both. The retained v0.4 history is checked against its
v0.4 reference, and is rejected by the v0.5-only reference as designed.
JSONL decoding is strict UTF-8 without a leading BOM on any row. Rejected bytes
remain in the raw feed. Consumers must preserve a BOM during decoding so the
reference parser can reject it; cursor hashes always use the original bytes.

The service records a reservation before each worker starts and retains it after
failure or interruption. Live ceilings are 600 solves and 600 charged CPU seconds
per rolling hour, one concurrent solve, and 200 solves per finite run. Development
allocations additionally cap at 2,000 HotSpot reservations and 1,800 charged CPU
seconds. A reservation charges its full conservative ceiling (15 seconds by
default), while measured CPU is recorded separately; missing measurements remain
explicitly unmeasured. The isolated worker and its native solver share one CPU;
an independent worker timer kills the entire process group within the reservation.
An inherited lease prevents overlap if the conductor dies. The `STOP` file is
durable; normal service shutdown uses transient cancellation so restart can resume.

## Local commands

Install `requirements.txt` and `requirements-service.txt`, and build HotSpot with
`make -C sundai_hotspot -j4 SUPERLU=1`. Activate that Python environment, then put
`sentilab_cli/` on `PATH`, or use `python -m sentilab_cli`.

```
python -m sentilab_core.conductor --fixture ascend910 --margin 0.32 \
  --max-evals-per-hour 40 --max-evals-per-run 40 --duration 600 \
  --interval 35 --renew --ephemeral
sentilab live status --ai-off
sentilab live stop --ai-off
sentilab live verify --ai-off --run-id RUN_ID --export replay.jsonl
python -m sentilab_mcp
```

`--ephemeral` is an explicit local-only in-memory signer. Restarting a local demo
requires a newly provisioned signer and trusted public-key configuration; private
material is never serialized. Production sets
`SENTILAB_SIGNER_FACTORY=sentilab_core.signing:service_signer`. This adapter uses
`sundai_controller.trust.load_service_key()` and the same `FLIGHT_SIGNING_SEED_B64`
service identity as flight-record certificates. Missing or invalid signing
configuration fails closed. The adapter exposes `key_id`, raw public-key bytes
in `public_key`, and `sign(bytes) -> bytes`; its ID comes from `trust.key_id_for()`.

Verification defaults to `sundai_controller.trust.PINNED_SERVICE_KEYS`, backed by
the shared `web/public/trust-pins.json` registry. `SENTILAB_VIEW_PUBLIC_KEYS` is an
explicit override: a JSON mapping of key IDs to raw public-key hex that replaces
the registry, including when set to `{}`. The signer must match a configured pin.
The browser's deploy-time pin remains independent of `/key` and replay artifacts.
Do not provision trust from an untrusted replay.

`SENTILAB_LIVE_DIR` must point to durable service storage, such as the deployment's
mounted volume, for restart-resume. Its default `/tmp/sentilab-live` is temporary
and does not guarantee history survives a container replacement.
`SENTILAB_LIVE_ENABLED=1`
starts the bounded renewable loop with FastAPI startup. Without a matching signer
and operator pin, startup fails closed. Run one service writer per storage root;
the OS ownership lock enforces this across processes. To release an explicit
STOP, the service operator removes that file and starts a new finite run.

The read-only routes are `/api/view/runs`,
`/api/view/events?run_id=...&cursor=0&limit=256`, and `/api/view/key`. Event responses
default to v0.5 JSONL, with at most 256 lines and 4 MiB per page. `cursor` is the
number of physical append rows already consumed, including duplicates and
malformed rows. Follow `x-next-cursor` and `x-has-more`; JSON diagnostics provide
`next_cursor` and `has_more`. A page may split conflicting sequences: retain all
received evidence and reverify the combined stream. Each cursor also has an
`x-cursor-hash` (`next_cursor_hash` in JSON), the SHA-256 of the consumed physical
byte prefix. Echo it as `cursor_hash` with every nonzero `cursor`. A missing or
changed boundary returns 409 and requires replay from zero, including after
in-place changes or file replacement. Append-only progress preserves the hash.
Only LF-terminated rows are counted, hashed or served. An unfinished tail waits
for its LF; writers still refuse to append onto it. Oversize rows retain their
original bytes, including invalid UTF-8. A page whose whole rows including LFs
total exactly 4 MiB is served; further rows wait for the next page. If the first
row at the cursor exceeds 4 MiB including its LF, the response is 413 with no
body or paging headers, including in cursor JSONL mode. The v0.6 client keeps
its prefix, shows "STALE · row too large" and stops polling until manual reload.
The hash binds a read boundary; envelope verification against pinned keys still
establishes authenticity. Late conflicting appends
are delivered at their append position and can retract an earlier verified
prefix. `has_more=false` describes only the current read; poll the same cursor
for new appends. Storage is append-only; a cursor beyond its current length
returns 409 and requires replay from zero.

Legacy `after=seq` remains supported separately. Its conflicting sequence groups
stay on one page; earlier break evidence is sent again. A group that cannot fit
returns 413. Clients needing bounded progress through such evidence use `cursor`.
Do not combine `after` with `cursor`, even `after=0`. Mixed parameters or malformed
`cursor_hash` return 422, so clients do not mistake them for unsupported paging.
Invalid numeric paging ranges return 400 with a fixed error message that never
echoes submitted values. Counts must be nonnegative safe integers; `limit` is 1–256.
Unsupported row-cursor polling
must preserve the prior prefix as STALE/unsupported; incremental sequence-only
fallback must not advance a LIVE/current claim.

For v0.6 transport conformance, run `python -m app.check_view_paging` after its
contract lands, or pass the exact `contracts/view-envelope-v0.6` directory from
PR26 as an argument. It drives the unchanged reducer and C1–C14 vector data
against a local HTTP server, plus unfinished-tail and oversize-row regressions.
Fault scenarios deliberately alter responses after fetching from the real route.
All C7 range statuses and C12/C14 server cases must match the reference exactly.
An explicit `format=json` returns diagnostic `envelopes`, `next_after`, `has_more`,
`prefix_end`, `chain_error`, and the core projection, also capped at 4 MiB.
Clients fetch one run from genesis through contiguous pages and
verify against their independent pins. A chain break freezes the board even when
later rows have individually valid signatures. Frontend LIVE labels must refresh
only on new verified-prefix progress, and claim recency rather than completeness.

CLI and MCP handlers call the same four operations. The MCP stdio host publishes
`sentilab_live_run`, `sentilab_live_status`, `sentilab_live_stop` and
`sentilab_live_verify`. Only a host holding the injected signer can start work;
no lab/UI transport accepts an actor role or writes a gate outcome.
The stdio host uses one persistent event loop with at most eight in-flight
requests, so status and STOP can complete while a run is active. Excess requests
receive a busy error. `notifications/cancelled` cancels the matching request;
disconnect cancels pending work and awaits cleanup before the host exits.
The conductor retains its ownership lock while oracle cleanup completes, even
when cancellation arrives during normal cleanup or is repeated. Cancellation is
reported only after cleanup; unexpected cleanup failures return an internal-error
response instead of silently ending the request.

## Checks

```
python -m unittest discover -s sentilab_core -p 'test_*.py'
python -m unittest app.test_view
python -m unittest sentilab_core.conformance
```

Only the last command requires Node 22. CI compares Python canonical bytes and
sizes with the exact references, all 16 v0.5 chain-vector prefixes, and a ledger
produced with the real synthetic plate solver against v0.5 `verifyJsonl()` and
the exact `project()` reference. Signed version rejection, the UTF-8 boundary,
and the unchanged 203-envelope historical proof are also checked against their
matching reference profiles. The service image remains Python-only.
