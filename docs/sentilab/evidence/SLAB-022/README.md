# SentiResultCheck v0.2

From the repository root, using Python 3.12:

```sh
export PATH="$PWD/sentilab_cli:$PATH"
sentilab resultcheck result.json
# Equivalent module entry point:
python -m sentilab_cli resultcheck result.json
SENTILAB_RESULTCHECK_DIR=/absolute/path/to/results python -m sentilab_mcp
```

The MCP stdio host lists `sentilab_resultcheck`. Its arguments are
`{"file":"result.json"}`: a file within the host-configured
`SENTILAB_RESULTCHECK_DIR`. Relative paths resolve under that directory; absolute
paths and symlinks are accepted only if their resolved target stays inside it.
The directory must be explicitly configured and exist. Missing/invalid configuration,
outside paths and missing files all return the same `file_unreadable` error without
a hash. The worker also checks the opened descriptor's resolved path before reading,
so a directory/symlink swap after path validation cannot expose outside bytes.
This restricted mode requires Linux `/proc/self/fd`; it fails closed if descriptor
resolution is unavailable. Only put files intended for MCP callers in this directory.
The ordinary local CLI keeps its existing file access; `--root DIRECTORY` opts into
the same restriction. Example JSON-RPC call after MCP
initialization:

```json
{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"sentilab_resultcheck","arguments":{"file":"result.json"}}}
```

Both transports use `sentilab_core.resultcheck.check_file`; MCP runs the same CLI
in a cancellable Python child process. ResultCheck requires
only Python's standard library and does not initialize the live signer, solver,
network, or model. `check(request)` accepts a parsed JSON value; `check_raw(bytes)`
(`checkRaw` alias) accepts UTF-8 bytes or text.

The output is the **normative `resultcheck.receipt.v2` receipt**, with
`checker_version: resultcheck-ref-0.2`, rather than a new wrapper around the
contract. `status` is the verdict, `errors` and `flags` are stable reason codes,
and `counts`, `details`, `statistics` and `claim_result` explain it. The request
schema is `resultcheck.request.v2`; see
[CONTRACTS.md](../../../../contracts/contract-0.2/CONTRACTS.md#2-resultcheck).
Neither timestamps nor transport metadata enter the receipt. CLI stdout is
canonical UTF-8 JSON plus one LF, written and flushed as bytes so Windows text
mode cannot translate the terminator to CRLF. ResultCheck help and usage errors
also use binary UTF-8 writes, retaining argparse's stdout/stderr and exit codes.
MCP `content[0].text` is those same canonical
JSON bytes, without the CLI's line terminator; normal JSON-RPC framing surrounds
it. MCP `isError` is true only for `rejected` receipts or `file_unreadable` transport
errors. Flags (including `arithmetic_discrepancy`) and insufficient data are completed
checks with `isError: false`; the CLI exit codes below are unchanged.

| CLI exit | Receipt status | Meaning |
|---|---|---|
| 0 | `checked` | Computed with no flags |
| 1 | `checked_with_flags`, `insufficient_data` | A consistency/inference flag or too few usable units |
| 2 | `rejected` | Invalid schema, malformed JSON, or input limit exceeded |

A missing/unreadable or unsupported file returns `{"error":{"code":"file_unreadable"}}`
(exit 2 / MCP tool error). Invalid CLI arguments use argparse exit 2; invalid
MCP arguments use JSON-RPC invalid-params. These transport errors are not
contract receipts. Invalid UTF-8 bytes produce `not_json` with a raw-byte hash.

The raw cap is **1,048,576 bytes**, checked before JSON parsing. File intake accepts
regular files up to **16,777,216 bytes**. The open uses `O_RDONLY` plus `O_BINARY`,
`O_NOFOLLOW` and `O_NONBLOCK` where each is available. Binary mode preserves the
original CRLF bytes on Windows. Immediately after open, `fstat` must identify a
regular file before any read. On Linux, nonblocking open also rejects FIFOs without
waiting for a writer; no equivalent nonblocking-open guarantee is claimed on
platforms without `O_NONBLOCK`. Where `O_NOFOLLOW` exists, the ordinary CLI rejects
a final-component symlink. Restricted intake resolves in-root symlinks first and
then validates the opened descriptor, as described above. Files
above the intake cap are transport errors; no partial hash is emitted. Reads use
64 KiB chunks and at most the initial file size plus one byte. Changes in size,
mtime or ctime during intake also fail as transport errors. For a stable file
within the intake cap, the full file is hashed even for a contract size rejection
(including a 10 MiB file). No oversized prefix is parsed. The
contract also bounds depth (8), values (200,000), pairs (10,000) and notes (4,096
UTF-16 code units). Notes are hashed but never echoed or interpreted. Valid JSON
uses the canonical request hash; size/parse failures use the raw input hash;
structure failures have a null request hash, exactly as the JS reference.

MCP allows at most eight active requests. ResultCheck work has a 10-second worker
deadline; a timeout returns `file_unreadable`. Cancellation or stdin EOF kills
and reaps the child before completing cleanup; explicit cancellation returns
JSON-RPC error `-32800`. Ping and live status/STOP can run while file work is in
progress. Clients must keep stdin open until expected responses arrive.

This checks submitted-data consistency and arithmetic only. It does not certify
measurement authenticity, physical validity, or scientific acceptance. Ties,
cluster aggregation, inference flags and refused percentage claims retain the
contract semantics; they do not silently become passes.

## Evidence and reproduction

[MANIFEST.json](MANIFEST.json) pins all six v0.2 contract files against
`contracts/HASHES.txt`, the 39-vector count, and the verdict schema version.
No contract files are changed. [VERIFICATION.json](VERIFICATION.json) records
the gates rerun on the final implementation, source hashes, and transport regression proofs.
[P2-VERIFICATION.json](P2-VERIFICATION.json) records the file-intake/cancellation
correction, actual stdio regressions, mutation checks and remaining gate scope.
The merge of PR #21's `fbf6ea2` with main `d031c8d` is recorded in
`MAIN-MERGE-VERIFICATION.json`. All six MCP tools and the live, dataset export,
and ResultCheck CLI paths survive; the combined-host regression fails on both
parents and passes after the merge. The unchanged CI smoke script passed 276
tests (zero skips), including every requested module and both MCP stdio suites,
plus eight HotSpot probes. Browser tests (103), live conformance (9), ResultCheck
parity (9 over 39 vectors), and all four contract runners also passed. Execution
was native Ubuntu 24.04/Python 3.12.3 at `/app`, with pinned dependencies and
Haswell OpenBLAS dispatch; Docker is absent and mount namespaces are denied, so
this is not a Docker image-build or container health/secret-scan claim. The
manifest records exact commands, module counts, source hashes and log hashes.
Warden separately reported native Windows verification of `fbf6ea2`: CLI exit 2,
551 bytes ending in one LF without CR, and 8 platform tests with 1 skip. That
Windows evidence is Warden's report, not execution in this Linux box.

The Windows correction is exercised on Linux by replacing only the core's OS
dependency: no `O_NONBLOCK`/`O_NOFOLLOW`, an available `O_BINARY`, and simulated
CRLF translation unless binary mode is selected. Actual CLI subprocesses prove
four bytes read for `[]\r\n`, receipt parity, and structured exit 2 for nonregular
descriptors and injected OS exceptions before/during/after reading. Native Windows
execution was not run in this box. Warden reported a direct CLI check on native
Windows (Python 3.11.9) at `63aa3f7`: `[]\r\n` produced a full `not_an_object`
receipt and exit 2, but stdout ended in CRLF. Warden also reported platform-test
failures at that revision. The probe was stripping `O_BINARY` on native Windows;
it now strips that synthetic flag only on hosts without a native `O_BINARY`.
No platform assertions are skipped or weakened for this correction. New real-CLI
subprocess checks configure CRLF text streams and assert exact UTF-8 output,
one final LF, no CR, correct stdout/stderr, and exits 0/1/2. Immediate child exit
after `main()` proves the CLI explicitly flushes the binary output. These checks
cover receipts, unreadable errors, injected intake exceptions, usage errors and
help. Native Windows execution of this follow-up remains for Warden to verify;
the native Windows evidence above is Warden's direct CLI result on `63aa3f7` only.
MCP and CLI `--root` still require Linux procfs
and fail closed elsewhere; ordinary CLI file intake has no procfs dependency.
Independent review remains pending.

```sh
# Standard-library tests: safe in the Python-only container, no Node needed.
python -m unittest -v sentilab_core.test_resultcheck
# Actual FIFO/device/large-file intake, lock-gated read cancellation and cleanup.
python -m unittest -v sentilab_core.test_resultcheck_io
# Configured file boundary, symlink escape and descriptor-swap regression tests.
python -m unittest -v sentilab_core.test_resultcheck_boundary
# Portable flags, binary bytes, descriptor rejection and intake exception exits.
python -m unittest -v sentilab_core.test_resultcheck_platform
# Mandatory additional CI gate: Python 3.12 and Node 22, no solver/model calls.
python -m sentilab_core.test_resultcheck --parity
```

The parity gate materializes every positive and negative contract vector in JS,
compares `check` with `checkRaw`, and compares the full canonical receipt (both
hashes included) with Python, a real CLI subprocess, and MCP stdio. Each vector's
hand-worked `expect` subset is asserted separately, so flipping an expected
status fails even when implementations agree. A missing Node executable fails
this explicit gate. Python-only tests run the same vectors against the core and
transports, and cover size/depth boundaries, invalid encoding, inert notes,
transport errors, and live-configuration independence.

To roll back this feature, revert the SLAB-022 commits; the live operations and
immutable contracts remain on the PR #15 base. CI changes require elevated human
review under SWE Excellence Framework §F.2 and §O.1.
