# SLAB047 bounded serving lifecycle

- [x] Inspect ancestor instructions, PR42 backend and retained SLAB018 pins/options.
- [x] Design fixed-root admission, exclusive attempt reservation, detached worker, bounded inference and owned cleanup.
- [x] Author controller and host bridge; leave shared CLI/MCP/registry untouched.
- [x] Exercise adversarial finite fakes for admission, races, STOP, ambiguous operations and accounting.
- [x] Review changes, bind source hashes and document limits for the independent review candidate.

## Author verification

At 2026-10-31 10:51 UTC, native Windows Python 3.11.9 completed 62 tests: 59 pass, three existing backend platform skips, zero failures/errors. The new controller contributes 24 finite fake tests and the host bridge six; the existing backend contributes 32 including the platform skips. Receipts and exact seven source/document hashes are in `docs/sentilab/evidence/SLAB-047/AUTHOR-UNIT-TESTS.json`; detailed output is adjacent. `git diff --check` passes. No actual SSH, Docker, GPU, model, external network, native solver or CI was run.

Self-review strengthened approval revalidation after lock acquisition, immutable worker claiming, ambiguous CREATE handling, original-deadline propagation inside the container, descriptor checks, prompt-byte rehash, port-closure error semantics, and supplied token/timing measurements. The candidate remains subject to independent nonauthor review. Linux flock/host process behavior, read-only-container compatibility, real readiness and actual cleanup/resource measurement are not established by these author fakes.

Only source authoring and local fake tests are authorized for this agent. Root owns exact independent approval, deployment and any GB10 execution. No SSH, Docker, GPU, model/network or CI run is performed here.

## Design and acceptance boundary

The fixed grant is source bb58c601-464f-4ebc-89f1-5b6eba9aeb25 / ticket 1509c616-03ee-4d35-b60c-bc70dd18b7fe: one attempt, <=900 seconds including startup/load/cleanup, start before 11:45 UTC and stop by 12:00 UTC on 2026-10-31. Before reservation, the host-owned approval file must bind the exact controller source and policy and name an independent +1 record. The reservation freezes those bytes and consumes the only attempt before spawning. No caller can supply approval, source, paths, hosts, image, commands or new requests.

The controller uses a new 0700 root, immutable reservation and atomic state; a detached worker owns a lock, with no numeric process-group kills. All container operations serialize under a separate lock. Only full container IDs with matching image/name/owner/token/source/policy labels may be stopped/removed. Ambiguous launch/cleanup consumes the attempt and is charged conservatively. An in-container timeout and controller deadlines retain cleanup reserve. Actual cleanup/port closure must be observed before completion; retained SLAB018 teardown is not proof for SLAB047.

# SLAB-048 REF-RECON: reference layouts, rotation, 45 mm fixtures, envelope plan

- [x] Decode TAP-2.5D Fig. 5(a) and Fig. 6(a) from the paper's vector outlines; keep the raw centres exactly, with origin, scale, rotation, script and hashes.
- [x] Per-die 90-degree rotation: `Design.apply("rotate")`, per-fixture orientation catalog, legality on the turned footprint, worker flags, wire proxy and view geometry.
- [x] 45 mm fixtures next to the unchanged 50 mm ones; frame read from the fixture.
- [x] A separate legal snapped variant per reference, every adjustment recorded with its reason.
- [x] SAMPLED +/-0.5 mm envelope call list on the snapped variants, sized from measured grid-64 timing. No solve run.
- [x] Reference record per room #56739 (b): SHIPPED / RESEARCH labels, page, per-die provenance and per-coordinate uncertainty, round-trip plan, out-of-sample validation points.
- [x] TAP-2.5D's router ported to HiGHS (`sundai_hotspot/tap_router.py`); routed-wire round trip on the raw references.
- [x] Tests, plus one mutation per rule that makes its check fail.

## Review

Merged main (#55) into the PR as a pure merge commit; the only hand resolution is in `tap_oracle_worker.py` (both sides kept).

Post-merge repair (astra #56857/#56858, warden review, astra sealed review):
- [x] 0.5 mm engineering variants (plain nearest rounding, ties up, no repair) with manifests; raw and 1 mm layouts unchanged and pinned.
- [x] Frozen raw identities (content hashes) and `TapGeometry.continuous_centers_for` for gate-zero validation without the lattice.
- [x] Envelope rebased on the 0.5 mm variants: 46 calls, forecast 220.4 CPU-s, proposed cap 321.5 CPU-s; first plan (45 / 215.851 / 316.308) kept as superseded forecasts.
- [x] Router: refuses non-optimal solves and malformed inputs; solver stack pinned and recorded; change notice and THIRD_PARTY_NOTICES entry.
- [x] Claims: three named temperature statistics; wire agreement as consistency evidence (translation invariance); reuse of the five panels disclosed; heuristic overhead labelled; no "solver grant" claim; norms named; decoder docstring states what it does.
- [x] No-append rule widened to the sealed review's words: the envelope is its own job and is never appended to any other job, the gate-zero job included.

24 code mutants and 7 data mutations each fail their checks. Local runs use a refusing stub for HotSpot: the seven existing solve tests fail identically on main, nothing else fails.
