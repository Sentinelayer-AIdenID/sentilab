# SentiResultCheck v0.2

From the repository root, using Python 3.12:

```sh
export PATH="$PWD/sentilab_cli:$PATH"
sentilab resultcheck result.json
# Equivalent module entry point:
python -m sentilab_cli resultcheck result.json
python -m sentilab_mcp
```

The MCP stdio host lists `sentilab_resultcheck`. Its arguments are
`{"file":"/path/to/result.json"}`: a file on the host, resolved relative to the
host's working directory if not absolute. Example JSON-RPC call after MCP
initialization:

```json
{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"sentilab_resultcheck","arguments":{"file":"result.json"}}}
```

Both transports call `sentilab_core.resultcheck.check_file`. ResultCheck requires
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
canonical UTF-8 JSON plus one LF. MCP `content[0].text` is those same canonical
JSON bytes, without the CLI's line terminator; normal JSON-RPC framing surrounds
it. MCP `isError` is true for a nonzero ResultCheck outcome.

| CLI exit | Receipt status | Meaning |
|---|---|---|
| 0 | `checked` | Computed with no flags |
| 1 | `checked_with_flags`, `insufficient_data` | A consistency/inference flag or too few usable units |
| 2 | `rejected` | Invalid schema, malformed JSON, or input limit exceeded |

A missing/unreadable file returns `{"error":{"code":"file_unreadable"}}`
(exit 2 / MCP tool error). Invalid CLI arguments use argparse exit 2; invalid
MCP arguments use JSON-RPC invalid-params. These transport errors are not
contract receipts. Invalid UTF-8 bytes produce `not_json` with a raw-byte hash.

The raw cap is **1,048,576 bytes**, checked before JSON parsing. File input is
streamed in 64 KiB chunks with bounded buffering; the full file is read to hash
all bytes even for a size rejection. No oversized prefix is parsed. The
contract also bounds depth (8), values (200,000), pairs (10,000) and notes (4,096
UTF-16 code units). Notes are hashed but never echoed or interpreted. Valid JSON
uses the canonical request hash; size/parse failures use the raw input hash;
structure failures have a null request hash, exactly as the JS reference.

This checks submitted-data consistency and arithmetic only. It does not certify
measurement authenticity, physical validity, or scientific acceptance. Ties,
cluster aggregation, inference flags and refused percentage claims retain the
contract semantics; they do not silently become passes.

## Evidence and reproduction

[MANIFEST.json](MANIFEST.json) pins all six v0.2 contract files against
`contracts/HASHES.txt`, the 39-vector count, and the verdict schema version.
No contract files are changed.

```sh
# Standard-library tests: safe in the Python-only container, no Node needed.
python -m unittest -v sentilab_core.test_resultcheck
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
