# SLAB-050 — evidence retention and resource forecast

New real headroom invocations refuse before starting workers unless their
preregistration binds a measured phase profile and the full declared schedule
fits both the remaining CPU and call allocations. Historical v3 stays
**INCONCLUSIVE**; its files and charges are unchanged. This change performs no
thermal study and makes only computational, simulated claims.

## Admission and freeze

Add `evidence_profile` to a new declaration with these fields:

- `path`: profile JSON path relative to the declaration (or absolute).
- `sha256`: SHA-256 of those exact JSON bytes.
- `reserve_cpu_seconds`: positive explicit reserve.
- `reserve_reason`: why that reserve covers setup, proposal generation,
  residual receipt/settlement writes, measurement variability and stopping.
- `declared_calls`: optional cross-check; must equal the computed schedule.

The forecast is **declared calls × sum of measured phase mean CPU + reserve**.
CPU units are seconds, not wall time. Reducers include initialization, search and
fresh reproductions; diagnostics include search only; long-SA maxima already
include reproduction. V4 declares 4,768 calls. The retained v3 schedule also
contains 448 diagnostic calls, making its full prospective forecast 5,216.
No-op savings are not assumed in advance. Every prior charge reduces capacity.
A refusal reports the CPU/call shortfall. Equality fits; nonfinite charges,
missing measurements, incomplete samples, altered profile summaries, and changed
binary/config/source/runtime identities refuse admission.

Mean cost plus a reserve is a forecast, **not a bound**. The existing independent
v4 supervisor still meters the whole process tree, stops the run, charges
overshoots, and requires the separate operator resource policy. Profile admission
does not authorize execution, extend the historical deadline, reopen the v4
allocation, or replace that policy. Legacy v1–v3 parsing remains available;
synthetic test oracles have an explicit test seam. Any future production
schedule still needs its applicable runtime stop and operating approval.

Both commands below are solve-free:

```sh
.venv/bin/python -m sundai_controller.profile_headroom summarize \
  --identity /path/to/attempt/IDENTITY.json \
  --records /path/to/attempt/evaluations --out /path/to/PHASE_PROFILE.json
.venv/bin/python -m sundai_controller.profile_headroom freeze \
  --prereg /path/to/proposed.json --budget /path/to/SPEND.json \
  --out /path/to/FROZEN.json
```

Freeze locks and reads the existing ledger and writes an exclusive snapshot only
after admission. It reserves no spend; start rechecks capacity and the exact
profile bytes. The supervisor binds its admission into reservation and settlement;
the worker checks it again. A changed ledger or profile cannot rely on an earlier
freeze. Profiles must be collected under a separately granted profiling budget;
there is deliberately no unrestricted solve command in the profile CLI.

## Retained evidence and accounting

Every real attempt receives a new directory, retaining PREREG, runner source,
identity, admission, signed lane events and per-call `evaluations/*.json`.
The call reservation and initial receipt precede worker startup. Native raw
inputs, generated floorplans/layer config/power trace/config, grid and steady
outputs, stdout/stderr bytes, request/response bytes, commands, exact explicit
child environments, input/artifact hash manifests and exit/error records live
under `raw/<call>/`. No parent environment dump is taken. Worker stderr is spooled
inside that retained tree while running, so forced termination does not depend on
cleanup copying a temporary file.

CPU and wall measurements cover generation, native solve, cold worker startup,
teardown/reap, archive and a reconciled CPU residual. Startup is counted once per
worker; the headroom runner closes workers after each call. Parent teardown CPU
is measured separately; worker exit CPU belongs to the residual. Archive includes
the native manifest, parent receipt and ledger write. Final receipt/checkpoint
serialization is charged by the ledger/supervisor and covered by the forecast
reserve; it cannot recursively measure its own last write. Residual wall time is
not a sequential phase estimate (recorded as zero); per-phase walls may overlap
between processes and must not be summed into a wall-time bound.

`PHASE_PROFILE.json` embeds every call record and its canonical hash. Missing
phases and unknown charges stay explicit; they never become zero-cost samples.
A failure, timeout, incomplete call, or cleanup failure makes that profile
ineligible for admission. After a forced worker stop, the supervisor reconstructs
`PHASE_PROFILE-<reservation>.json` from surviving receipts, preserving unreadable
receipts as excluded records and linking the authoritative whole-lifetime
`SETTLEMENT-<reservation>.json`. Per-call CPU totals are distinct from this
whole-lifetime charge. Raw files survive even if only a partial phase checkpoint
was written before termination.

Identity binds fixture, grid, config, binary, relevant source bytes, interpreter,
kernel, architecture and child environment. The host may supply
`SENTILAB_IMAGE_DIGEST=sha256:<64 lowercase hex digits>`; this is recorded as
host-declared, not independently attested. Without it the image is explicitly
unavailable, with Dockerfile/build-info hashes retained. A base-image pin is not
misrepresented as the final runtime-image digest.

Unchanged proposals emit `noop_skipped`, consume no solver call, and check the
budget before retrying. A bounded proposal-attempt limit retains an incomplete
lane if no progress is possible. Explicit winner-reproduction calls remain fresh.

## Proof and remaining measurement

All new behavioral tests use synthetic oracles or fake native processes.
No new HotSpot solve or measured thermal phase profile is included in this patch.
A four-call grid32 profiling grant (two calls per fixture, proposed 60 CPU-second
ceiling) has been requested; no grant is assumed. Real profiling and operational
reserve selection remain pending that grant. The code is ready for independent
review of arithmetic and retention completeness.
