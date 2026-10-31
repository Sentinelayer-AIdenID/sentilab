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
