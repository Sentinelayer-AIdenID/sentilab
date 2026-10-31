# CI process launch review after the main merge

Reviewed against PR #37 base `d694252107d66201948028e5502d0f66ee3097b5`.
The existing allocation inventory test refused 24 unlisted Python call sites.
The scan now also includes `sentilab_mcp` and `sentilab_cli`, adding two MCP
worker sites. Review also found the saved `REAL_POPEN` alias in the GB10 tests;
the scan now resolves saved process functions as well as import aliases. All 27
expressions are explicitly listed in `RAW_SPAWNS`, with their multiplicities
retained. The exact-expression `assertCountEqual`, import alias
resolution, native entry checks and existing gate tests remain in force.

These are classifications of the shipped commands and their current callers,
not permission for arbitrary commands at a variable named `command` or `argv`.
Changing a worker, its command construction or its requests requires another
review. The source inventory is not a sandbox: the compiled CI entry guard and
reservation broker still enforce native HotSpot entry, including copied binaries.

| File / call sites (lines at the reviewed base) | Count | Why these calls do not launch HotSpot |
| --- | ---: | --- |
| `sentilab_core/gb10_backend.py:32` | 1 | `_capture` is called by `_remote` with fixed `ssh` arguments and `shell=False`. Its stdin is the checked-in `gb10_readonly.py`, limited to status and checkpoint file inspection. Caller input cannot select an executable or source; serve start/stop is refused. Tests substitute fake Python peers. No solver is invoked locally or by that remote program. |
| `sentilab_core/test_gb10_backend.py:57` | 1 | `REAL_POPEN` saves `subprocess.Popen` before the production dependency is mocked. It launches `sys.executable -I -S -B -c behavior` as a fake SSH peer. The scripts return synthetic probe responses or exercise the transmitted read-only source under OS hooks; they never launch SSH or a solver. |
| `sentilab_core/memory_conformance.py:28,41,62` | 3 | Node runs the projection adapter or a fixed script importing the evidence projection contract. Both transform recorded JSON and have no process launch or oracle path. |
| `sentilab_core/test_memory_transports.py:51,58` | 2 | CLI/MCP commands request memory recall/audit or advisory routing/calibration, not live execution. Routing produces a suggestion; it does not dispatch an oracle. |
| `sentilab_core/test_probe.py:12` | 1 | The fixed `sentilab_core.probe` command validates supplied model-list JSON from stdin and writes a receipt. It does not call a provider or a solver. |
| `sentilab_core/test_research_transports.py:31,38,101` | 3 | Python CLI/MCP research requests use the shipped deterministic offline fixture backend, including refusal, status and export cases. The variable `command` at line 101 is the fixed executable-CLI research request used to check the `ai_off_required` error. |
| `sentilab_core/test_resultcheck.py:43,142,221,229,275,305` | 6 | Python CLI/MCP invokes offline ResultCheck; the two Node scripts import the reference ResultCheck contract. All check supplied files/vectors; none requests thermal evaluation. The two identical CLI expressions remain separate inventory entries. |
| `sentilab_core/test_resultcheck_boundary.py:69` | 1 | CLI ResultCheck tests refusal of a file outside the configured root. |
| `sentilab_core/test_resultcheck_io.py:165,203` | 2 | Starts the MCP host or fixed cancellation/delay host script, and CLI ResultCheck. The tests send ResultCheck requests only; scripted delays do not introduce another executable. |
| `sentilab_core/test_resultcheck_platform.py:105,123,177` | 3 | CLI ResultCheck runs directly or through fixed OS/stdio hooks to test descriptor handling and output bytes. Hooks call the same offline CLI branch. |
| `sentilab_core/test_mcp_stdio.py:165` | 1 | `LazyContextTests.start` launches the MCP host or fixed import/context scripts. Requests exercise ResultCheck, recorded-data export/verification, offline research, advisory registration, status/stop and failed live initialization. The combined-host run request has `ai_off=False` and is refused before evaluation. |
| `app/check_view_paging.py:46` | 1 | Node runs `check_view_paging.mjs` against the local `ViewTests` HTTP fixture. It calls the recorded-ledger view endpoint and contract reducers, not a run endpoint. |
| `sentilab_mcp/__init__.py:38` | 1 | Fixed `sentilab_mcp.export_worker` calls `sentilab_core.dataset.export`, which replays and exports recorded evidence. It does not evaluate or reproduce a thermal run. |
| `sentilab_mcp/__init__.py:69` | 1 | Fixed CLI `resultcheck --root ... -- file` enters the offline checker before live context creation. The file is a positional argument after `--`, not executable input. |

The other areas named in review were inspected as well:

- `scripts/build-deck-data.mjs` and `scripts/deck-data.test.mjs` read and
  regenerate the dated progress packet in-process. Their `.exec` uses are
  regular-expression matches, not process execution.
- `scripts/export-deck-pdf.mjs` calls Playwright `chromium.launch()` with no
  executable override, renders the static deck from a local HTTP server and
  writes PDFs/screenshots. That process is Chromium, not HotSpot. This exporter
  is not invoked by the CI workflow.
- `scripts/sentilab-scene.mjs` and the chiplet/package scene modules consume
  recorded envelopes and build scenes in-process. No subprocess or solver is
  started; `.exec` parses a key/pin string with a regular expression.
  `web/test/sentilab-scene.test.mjs` has two Node child-process sites:
  `spawnSync` runs that fixed scene CLI with test fixture arguments, and
  `execFileSync` requests its help output. Both use `process.execPath` and the
  fixed `scripts/sentilab-scene.mjs` path; neither invokes HotSpot.
- `app/view.py` and `app/test_view_cache.py` use the recorded-ledger cache and
  HTTP route fixtures. They add no raw process call. The Node HTTP parity call
  is inventoried above, including its comparison of warm and cold cache output.
  The existing optional live-loop thread delegates to `operations.run` and the
  shared gated oracle; the cache does not introduce a second launch path.

No new native HotSpot caller was found among these additions. Existing live
CLI/MCP operations still reach the shared oracle/worker and `run_hotspot` gate.
This review makes no claim about historical consumption, global admission
rollout, or measured container CPU usage.

## Round 6: headroom merge

Main `2d9eca2` adds the SLAB-039 headroom supervisor and retained-output worker
changes. The worker keeps `ExitStack` and file-backed `stdout.bin`/`stderr.bin`
when retention is requested, or `capture_output=True` otherwise; both paths
call `run_hotspot`. Its existing keyword forwarding accepts those file handles,
so neither the reservation wrapper nor its settlement behavior changes.

The complete inventory initially failed on seven unclassified call sites.
Review also identified the production fork, now explicitly scanned and listed.
All eight sites are classified below, including identical-call multiplicities.
Path comparisons use POSIX separators so the inventory is portable.

| File | Count | Classification |
| --- | ---: | --- |
| `sundai_controller/headroom.py` | 1 | `os.execv` enters the fixed `sundai_controller.headroom_supervisor` module, preserving the CI environment. It does not execute a native solver itself. |
| `sundai_controller/headroom_supervisor.py` | 1 | `LinuxTree.start` forks the supplied worker. The production `work` closure calls `run_headroom`, which constructs `HotSpotOracle`; its warm worker executes `tap_oracle_worker.evaluate` through `run_hotspot`. CI environment and the enclosing cgroup are inherited across exec/fork. A failed headroom reservation cannot bypass the independent CI launch reservation. The synthetic test closures use fake oracles or CPU loops. |
| `sundai_controller/test_headroom_supervisor.py` | 2 | Dedicated Python programs test CPU/reaping with a forked busy loop and the production supervisor with `oracle_factory=Fake`. Neither executes HotSpot. |
| `sundai_controller/test_process_budget.py` | 3 | Fixed Python programs test sleep, orphan cleanup, and threaded hash work under affinity. Embedded forks create CPU/signal probes, not solvers. |
| `sentilab_core/test_oracle.py` | 1 | Saved `asyncio.create_subprocess_exec` alias starts a fixed Python cancellation host and sleeping forked descendant. It substitutes the real worker at the process boundary; no solver runs. |

`tap_oracle.py` retains its existing two inventoried process calls: the fixed
warm Python worker (gated as above) and Windows `taskkill.exe` for cleanup. Its
new immediate-kill, latency and retained-output paths introduce no launch.
`sentilab_core/oracle.py` still launches the fixed `sentilab_core.worker`, whose
`evaluate` path reaches the same gate. Existing GB10 serving additions use the
reviewed SSH transport; scripts under `scripts/gb10` are outside this inventory
and do not introduce a HotSpot call.

## Round 7: capability registry and image runtime merge

Main `1e6b97e` brings the SLAB-043 recorded capability worker and conformance
suite. The unchanged inventory assertion initially refused 21 added raw call
sites and one removed export-worker call. The removed entry is replaced by
the shared recorded worker below; the ResultCheck MCP entry remains. All new
expressions and duplicate counts are listed explicitly, with no scan exclusions
or assertion changes.

| File | Count | Classification |
| --- | ---: | --- |
| `sentilab_core/execution.py` | 1 | `_WorkerJob` starts the fixed `sentilab_core.execution` module. `main` permits recorded live status/stop/verify, dataset export, chiplet geometry/projection/replay/export, GB10 read-only evidence, and memory recall/audit/route. It explicitly excludes `live.run` and does not dispatch an oracle. Its restricted environment therefore needs no solver reservation. Production live execution stays in the original gated oracle path. |
| `sentilab_core/chiplet.py` | 1 | Fixed Node source imports the shared browser model and projects verified recorded JSON from stdin. The model and its evidence projection import have no child-process or solver calls. `build` validates geometry only; replay/export also operate on records. |
| `sentilab_core/test_execution.py` | 2 | Saved `Popen` aliases either start the recorded worker with pidfd setup forced to fail before request dispatch, or replace that exact module command with a finite Python fork/pipe/cancellation fixture. The fixture never invokes a solver. |
| `sentilab_core/test_build_info.py` | 4 | Two fixed commands query the Debian Node package and `/usr/bin/node --version`; two run the fixed build-receipt script with valid or invalid image/package pins. The script only queries `dpkg-query` and Node version before writing public runtime metadata. |
| `sentilab_core/test_conformance.py` | 13 | CLI/MCP processes exercise recorded capabilities, fake SSH evidence, scope/input refusal, cancellation of recorded workers, help output and registry listing. The successful `live.run` case injects `BarrierOracle` via `FIXTURE_HOST` and creates STOP before execution, asserting zero solves. Other live-run requests fail admission or input validation. Cancellation explicitly excludes `live.run`. All command-building helpers and requests were inspected; repeated CLI, MCP and help expressions keep their exact multiplicities. |

Main's `scripts/record_build_info.py` is also invoked directly by the image
build. Its two subprocesses only query `dpkg-query` and Node version; scripts
remain outside the Python source inventory. The Dockerfile preserves main's
pinned Python base, pinned Debian Node package and build receipt, followed by
the allocation ARG/ENV and allocation-aware native build. The enclosing cgroup
still includes these build steps through the existing dedicated Docker daemon.

## Round 9: worker evidence and proposal harness merge

Main `315bbff4` adds SLAB-050 worker evidence and SLAB-052 proposal transports.
The unchanged inventory assertion refused three new sites in
`sentilab_core/test_proposals.py`: the CLI `subprocess.run`, MCP `Popen`, and
CLI interrupt `Popen`. Each command uses this Python interpreter with the fixed
`HOST` program, which injects `BarrierOracle(FixtureOracle)` before entering
the real CLI/MCP. The fixture returns synthetic metrics or waits for cancellation;
none of these three sites invokes HotSpot. Their exact command expressions are
now listed without changing the inventory assertion or scan scope.

The merged TAP worker preserves main's parameter/cardinality validation order,
native environment allowlist, retained streams and phase accounting. Its one
native call uses `run_hotspot`, preserving reservation before execution and
settlement after termination. Main's incremental response spool in
`tap_oracle.py` is unchanged. Its explicit child environment preserves only the
nonsecret `CI_ALLOCATION=1` flag so the warm worker uses the reservation gate;
all other parent settings remain excluded. A real protocol-worker regression
refuses the old environment omission. The frontend inventory now checks both
main's `oracle_type = oracle_factory or HotSpotOracle` binding and its calls. The two native-process mocks in the new worker
evidence tests target `worker.run_hotspot`; all assertions remain intact.
