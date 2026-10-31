# SLAB047b terminal identity and cleanup audit

No blocking inconsistency was found in the retained local identity, approval-order, timing, and closure records. This is an offline evidence audit, not an external authentication, live device check, final-deliverable acceptance, or scientific-results approval.

Exact source identity is `3236e23aecafb8e49e31aaec8101d3906f1de2a8`, controller SHA256 `a707a77d4b39836c461b7cacabe17bf1a59efbdcb3938871ea04c077ef32276d`, policy SHA256 `1d3acc0186a2d799851f7b43ed1454c6ae893dbacedbfddec3735b6eb593401d`. The downloaded controller bytes hash to that previously independently checked source pin. Reservation, installed approval, worker claim, start receipt, terminal status, final container labels and image all agree. The attempt token is `35612fda883c4d2ca7bb0cb82882c8f5` and full container ID is `c16b3e9d6a352c2fc64373e4dc65879ed8ca589bf570fa081249932f917e26bb`. The new root/owner are `/home/dell/sentilab/serving-20261031b` / `sentilab-slab047b-20261031`, with grant 56545/source `55fe3cab-88b4-4f80-9ae7-2f5ff43c70f7`. Approval bytes exactly match the reservation's frozen bytes and the installation receipt's SHA256.

The recorded same-host chronology is:

| Event | UTC time |
|---|---|
| Preflight finished with verified cleanup | 2026-10-31T11:35:44.142891+00:00 |
| Separate preflight inventory empty; lock free; GPU approval absent | 2026-10-31T11:36:27.217162+00:00 |
| Controller approval installed | 2026-10-31T11:37:23.782117+00:00 |
| GPU reservation | 2026-10-31T11:37:44.101327+00:00 |
| Worker claim | 2026-10-31T11:37:44.145236+00:00 |
| Container start | 2026-10-31T11:37:47.948382098Z |
| Ready | 2026-10-31T11:39:16.974899+00:00 |
| Container exit | 2026-10-31T11:40:12.685959112Z |
| Controller confirms cleanup | 2026-10-31T11:40:13.010829+00:00 |
| Controller completes | 2026-10-31T11:40:13.014224+00:00 |
| Separate retained closure observation | 2026-10-31T11:41:42.683883+00:00 |

The monotonic charged duration is reported as **148.909503325005 seconds**, using `max(0, time.monotonic() - reserved_monotonic)` after removal confirmation and refused-port observation (`gpu-runtime/serve047.py:345–358`). The same-host reservation-to-cleanup wall interval is 148.909508228302 seconds, a difference of about 4.903 microseconds. There is no separately stored terminal monotonic sample to recompute the reported duration independently. The reported warmup is 89.050370427998 seconds and its corresponding wall interval is 89.050357103348 seconds. Both deadline clocks allocate exactly 900 seconds; the effective attempt deadline is 2026-10-31T11:52:44.101321+00:00, earlier than the 12:30 UTC absolute stop. Start and completion meet their respective limits.

The PC's start receipt finished at 2026-10-31T11:37:43.996774+00:00, about 104.547 milliseconds before GB10's recorded reservation time. These are different wall-clock domains with no recorded synchronization bound. Do not use that offset as a causal admission-order reversal or claim globally synchronized timestamps.

Final container inspection records exit code 0, `Running=false`, `Pid=0`, `OOMKilled=false`, and matching ownership/source/policy labels. State records `completed`, 20 reserved/completed requests, no error or budget excess, container removed and port closed, with retries disabled and final deliverable acceptance false. The later status agrees. The separate closure receipt reports successful empty Docker inventory, connect code 111 matching ECONNREFUSED, and free worker lock. That later corroboration time is not additional serving duration. This audit does not replace the parent's raw request/response and startup-trace checks.

All 12 files listed in the old SLAB047 download manifest still match their retained local sizes and hashes. The original snapshot remains `failed_closed`/`server_exited`, zero inference reservations, no retry, and charge **79.617588726003 seconds**, with a different root identity, token, controller pin and container ID. SLAB047b's **148.909503325005 seconds** and the separate native preflight's **0.638011345000 seconds** remain separately attributed. This verifies local snapshot preservation and separation; it does not prove that no later remote filesystem edit occurred.

`EVIDENCE-CHECK.json` binds the source records read and their hashes. No SSH, Docker, status/stop request, network, product runtime, tests, compiler, GPU, model, or numerical workload was executed. Local metadata parsing and hashing only; report files are the only writes.
