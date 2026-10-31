# GB10 local-PC backend

This is the initial read-only slice of the device/checkpoint/serve capability.
The complete scope remains **staged/open**. SLAB018 attempt 1 is complete and
must not be rerun. Its former grant does not authorize a new serving session.

## Design and integration contract

`sentilab_core.gb10_backend.execute(operation, context=None, **arguments)` is a
transport-neutral Python API. SLAB043 owns CLI/MCP registration separately.
`context` is reserved for a host-owned context; this implementation never reads
it. Do not deserialize an MCP argument into that parameter.

| Operation | Accepted arguments | Behavior |
| --- | --- | --- |
| `status` | None | A fixed, read-only Python probe over SSH alias `gb10` reports device identity and available driver metadata. |
| `checkpoint_verify` | `location`: `gb10`, `pc`, or `both` (default `both`) | Rehash the retained adapter, its configuration and its input manifest at the pinned locations. |
| `serve` | `action`: `status`, `start`, or `stop` (default `status`) | Status returns pending; start and stop refuse. No remote call occurs. |

Unknown operations, extra arguments, wrong types, paths, host overrides, SSH
options and grant tokens are rejected. A future prospective GPU grant needs a
separately reviewed admission and lifecycle implementation. There is no hidden
launch switch in this API.

Every response has `schema`, `operation`, `ok`, `status`, `checked_at`, and
`scope_state: "staged_open"`. `ok` means only the requested observation passed;
it never closes the full ticket or authorizes compute. Serving status uses
`ok: false, status: "pending"`; start refuses with `gpu_grant_required`, stop
with `no_managed_serve_session`. A historical teardown receipt is not a live
service-status observation.

The remote program is the sibling module `sentilab_core/gb10_readonly.py`,
sent to `python3 -I -S -B -` on stdin. SSH uses batch authentication, strict
known-host checking, no terminal, no forwarding and no local command. The
alias and artifact paths are constants, never command-line interpolation from
caller input. The program imports only the standard library, reads files and
exits. It does not invoke the historical supervisor, Docker, `nvidia-smi`, a
model, a solver or an HTTP endpoint. It creates no remote files.

Transport limits: 32 KiB of source on stdin, 16 KiB each of stdout/stderr,
five-second connection timeout, 20-second local deadline, and a 12-second
remote alarm. Raw SSH errors and invalid response bodies are never returned.
The device hostname, login and architecture must match the retained identity.
GPU/driver information is an optional bounded `/proc` read; its absence is
reported as unknown and does not become evidence of GPU readiness.

Checkpoint checks reject symlinks/reparse points and nonregular files, bound
reads to the pinned size, compare descriptor metadata before/after hashing,
and check the path chain for replacement. On POSIX, traversal additionally
uses directory descriptors and `O_NOFOLLOW`. Local Windows path-chain checks
are observations, not a transaction or a filesystem lease; the result proves
the bytes read at that time, not continued path availability. This does not
parse tensors, evaluate the adapter, revalidate base weights or establish
scientific generalization.

The adapter is 66,126,768 bytes with SHA256
`695581e310def332bd6307527eff6546d95eebb88bec7e6f6ce288a5a61c0f80`.
The source of the pins is the committed SLAB018 `ADAPTER-LOCATION.json` and
`attempt-01/REMOTE-ARTIFACT-MANIFEST.json`, not mutable caller claims. The
input manifest digest is
`230fd89ad116537c30cfd2c934d0ccae28dd4acec5d7b3361e1bd16bbecf1357`.
Keep both retained copies. The historical evidence used CUDA 13.3 for
training/reload and CUDA 13.0 for serving. Its six repeated source fixture
cases establish adapter plumbing, not held-out learning or chiplet results.

## Implementation plan and validation

- [x] Bind a new isolated worktree to main `780427afcf372591cd99fbd0998b188a9f807f1b`.
- [x] Agree the API and leave common CLI/MCP files to SLAB043.
- [x] Implement fixed read-only probes and checkpoint verification.
- [x] Implement a non-launching serve boundary.
- [x] Run guarded fake SSH, parser, argument, path and replacement tests.
- [ ] Root reviews the local diff and, separately, may run a live read-only probe.

Run the offline tests from the repository root:

```sh
python -m unittest sentilab_core.test_gb10_backend
```

The test suite must not use the real SSH executable or the retained checkpoint.
Live inspection is a separate operator action; no live result is claimed by
the implementation tests. No PR, shared registration or prospective GPU grant
is included in this slice.

Validation on 2026-10-31: 32 tests passed under WSL Ubuntu 24.04/Python 3.12.3.
On native Windows, 32 tests ran with 29 passing and three platform skips (FIFO,
POSIX directory traversal race, and creating a symlink without the required
Windows privilege). The Windows reparse-point rejection was tested separately.
The suite executes the actual transmitted stdin source against a guarded fake
host and reaps fake subprocesses after timeout/flood cases. No live GB10 probe
or retained checkpoint read was performed by these tests. Independent root
review and shared CLI/MCP registration remain pending.
