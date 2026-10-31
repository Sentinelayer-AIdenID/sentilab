# PR20 export correction on current PR15

Review 56202 finding 4, rebuilt for the current PR15 dispatcher at
`25d3f9e1543e4c262ee7e69eeffa1eb31fbcc265`. The local carry base is
`d8ad6ae059a6bbecbf5454ce8d5c5a14f47c181d`: the existing dataset implementation
and three accepted dataset corrections applied after that PR15 head. The
operator reports those corrections already carried on PR20 at `95e4970`;
that published head was not available for independent inspection in this box.

Only the export handler becomes asynchronous. It runs the existing exporter in
a subprocess with a 30-second timeout and reaps the worker on cancellation,
timeout or disconnect. The shared eight-request bound and per-ID cancellation
remain owned by PR15. This corrective commit makes **no changes** to
`sentilab_mcp/__main__.py`; the source of `serve()`, including its nested
`dispatch()`, was compared byte-for-byte with PR15 and matched.

The CLI/MCP artifact parity test keeps stdin open until both responses arrive
and correlates them by JSON-RPC ID. Closing stdin earlier requests cancellation
under the existing PR15 disconnect semantics.

## Before/after proof

In a separate detached worktree at the carry base, copying in the new
`sentilab_core/test_dataset_mcp.py` and running
`/workspace/sentilab/.venv/bin/python -m unittest -q sentilab_core.test_dataset_mcp`
exited 1: all three tests failed with `no MCP response for id 'stop'`,
`no MCP response for id 'export'`, or `no MCP response for id 'ping'`.

With the fix, the tests check STOP and status while the export lock is held,
cancellation by request ID, timeout, EOF cleanup, no surviving worker process
group, and no publication after releasing the lock. The timeout test shortens
the host limit to 0.25 seconds. The existing four PR15 stdio tests also pass
unchanged, including its eight-request bound.

## Executed gates

Run from the repository root unless stated otherwise; every command exited 0:

- `.venv/bin/python -m unittest -q sentilab_core.test_dataset sentilab_core.test_dataset_mcp sentilab_core.test_mcp_stdio sentilab_core.test_ledger sentilab_core.test_gate sentilab_core.test_budget sentilab_core.test_environment sentilab_core.test_signing`: **56 tests**.
- `(cd contracts && sha256sum -c HASHES.txt)`: all hashes match.
- `(cd contracts && node contract-0.2/run-vectors.mjs)`: **74 checks**.
- `(cd contracts && node view-envelope/run-view-vectors.mjs)`: **113 checks**.
- `(cd contracts && node view-envelope-v0.5/run-view-vectors.mjs)`: **193 checks**.
- `.venv/bin/python -m compileall -q sentilab_core/dataset.py sentilab_core/test_dataset.py sentilab_core/test_dataset_mcp.py sentilab_cli sentilab_mcp`.
- `.venv/bin/pip check`: no broken requirements.
- `git diff --check`.

All 53 original fixture envelopes verify using the public pins. The fixture and
public-key files are byte-identical to `3b0979b`. No dependencies, contract files
or shared transport tests were changed. There is no npm/TypeScript manifest or
lint configuration; no substitute configuration was added. This round used
recorded fixtures only, with no solver or LLM calls. Solver-backed suites and
native builds were not repeated for this export-only correction.

## Review limitations retained

These are self-check receipts by a surrogate executor under recorded model
substitution, not independent clearance or publication proof. The earlier
automatic review scored 62/100 and returned `pass: false`, reporting a Python
test-name detection problem and a base diff including PR15; it remains
unresolved. The prior corrective round also recorded an accidental synthetic
solver run through two inherited transport tests. This round did not repeat
those tests. Root retains independent corrective review; READY FOR CARRY does
not mean merged or released.
