"""SLAB-049 gate-zero operator supervisor (claude-warden), per CALL-LIST-v4.md "Operator supervisor (warden)".

Runs INSIDE the merged build's own image (the repo Dockerfile, /app), as the container's main process, so that the
interpreter, loader and libraries come from that immutable image and the container's cgroup holds every process the
calls start. Paths are identical inside and outside the container (/srv/gate0/...), because the grant binds the
ledger directory's absolute path.

  grant   open the grant: ledger entry 0, signed with the operator key (gate0_anchor.open_ledger)
  run     the 12 calls in manifest order, concurrency 1: the operator's reserve tag, validate-reference, then the
          operator's settle tag with the exact message validate-reference prints
  record  python -m sundai_hotspot.reference_validation record --kind hotspot6 --out ...
  report  python -m sundai_hotspot.reference_validation report --out ...

The cumulative CPU budget (contract item 5) covers the whole container, descendants included, read from the
container's own cgroup v2 cpu.stat. A call starts only if what has been used plus its envelope still fits under the
cap. Usage carries over between container runs through /srv/gate0/runs/cpu-used.json.

Everything a call starts is the call's to stop (root #57395). validate-reference runs in its own session, and it
launches the solver in another one (reference_validation, step 9), so killing validate-reference's process group
alone would leave the solver running. While a call runs, this supervisor is the child subreaper of everything the
call starts (OwnedProcesses; in the container it is PID 1 as well), so a process whose parent dies stays its
descendant. The supervisor reads the meter itself while the call runs, so no separate watcher can die and leave the
call unwatched (root #57472). When the total passes the cap, or a reading fails, it SIGKILLs every process group the
call owns: validate-reference's and the group of each live descendant, the solver's own session included. After
validate-reference exits, for any reason, whatever it left behind is killed and reaped the same way. The CPU is read
only after that reap, so a call is charged for everything it started. The container's cgroup cannot be killed from
inside: cgroupfs is read-only there, and the supervisor is a member of that cgroup. Tracking every owned descendant
group is the fallback root names.

A call whose validate-reference printed no settlement is settled by the operator (contract item 6), and never
relaunched. Its status is supervisor_meter_failed when the meter failed (the errors are kept), supervisor_cap when
the cap killed it, and supervisor_unknown when it died on its own. It is charged its full envelope, or the CPU
measured after the reap if that is larger. If the meter failed after the reap as well, the call's usage is unknown.
It is then charged its full envelope or the CPU already read for it, whichever is larger (root #57510). The
reservation stays consumed, and the charge is never zero, never refunded, and never below what was read. The
cumulative total is recorded as unknown, and every later run refuses until the operator reconciles it by hand. A run
in which the meter failed stops after that call.

Never prints the key, the token or the anchor credential.
"""
from __future__ import annotations

import argparse
import contextlib
import ctypes
import datetime as dt
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "/app")
from sundai_controller import process_budget  # noqa: E402
from sundai_hotspot import gate0_anchor, reference_validation  # noqa: E402

RUNS = Path("/srv/gate0/runs")
CPU_FILE = RUNS / "cpu-used.json"
LOG = RUNS / "operator-log.jsonl"
PR_SET_CHILD_SUBREAPER, PR_GET_CHILD_SUBREAPER = 36, 37


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(event: str, **fields) -> None:
    line = json.dumps({"at": now(), "event": event, **fields}, sort_keys=True)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def cgroup_cpu_s() -> float:
    with open("/sys/fs/cgroup/cpu.stat", encoding="ascii") as handle:
        for line in handle:
            key, value = line.split()
            if key == "usage_usec":
                return int(value) / 1e6
    raise RuntimeError("no usage_usec in the container's cpu.stat")


def carried_cpu_s() -> float:
    """The cumulative CPU used by earlier runs. If a run recorded it as unknown, every run refuses until the operator
    reconciles it by hand: nothing retries on its own, and no unknown usage is ever counted as zero."""
    if not CPU_FILE.exists():
        return 0.0
    record = json.loads(CPU_FILE.read_text(encoding="utf-8"))
    if record.get("used_cpu_s") is None:
        raise SystemExit(f"the cumulative CPU used is unknown since {record.get('at')} (the meter failed; at least "
                         f"{record.get('lower_bound_cpu_s')} CPU-s): reconcile it by hand before any further call")
    return float(record["used_cpu_s"])


def save_cpu(total: float | None, lower_bound: float | None = None) -> None:
    """Saves the cumulative CPU. None means the meter failed after a call: the total is then recorded as unknown, with
    the last value read as a lower bound, never as a number that looks measured."""
    tmp = CPU_FILE.with_suffix(".tmp")
    if total is None:
        record = {"used_cpu_s": None, "usage": "unknown", "lower_bound_cpu_s": lower_bound, "at": now()}
    else:
        record = {"used_cpu_s": round(total, 6), "at": now()}
    tmp.write_text(json.dumps(record), encoding="utf-8")
    os.replace(tmp, CPU_FILE)


def load() -> tuple[dict, str]:
    manifest, manifest_sha256 = reference_validation.load_manifest()  # refused unless this tree generates it
    if not manifest["operator"]["public_key_ed25519"]:
        raise SystemExit("the manifest has no pinned operator key")
    return manifest, manifest_sha256


def check_key(manifest: dict, key_path: Path):
    key = gate0_anchor.load_private_key(key_path)
    if gate0_anchor.public_key_hex(key) != manifest["operator"]["public_key_ed25519"]:
        raise SystemExit("the operator key file does not match the manifest's pinned public key")
    return key


def github() -> object:
    credential = os.environ.get("SLAB049_ANCHOR_TOKEN")
    if not credential:
        raise SystemExit("SLAB049_ANCHOR_TOKEN is not set")
    return gate0_anchor.github_request("Sentinelayer-AIdenID/sentilab", credential)


def cmd_grant(args) -> int:
    manifest, manifest_sha256 = load()
    key = check_key(manifest, args.key)
    not_after = manifest["grant_window"]["not_after_utc"]
    calls = [call["id"] for call in manifest["calls"]]
    entry = gate0_anchor.open_ledger(args.ledger_root, key, manifest_sha256, grant_id=args.grant_id, calls=calls,
                                     not_before_utc=now(), not_after_utc=not_after, cpu_cap_s=args.cap)
    ledger = gate0_anchor.read_ledger(args.ledger_root, manifest["operator"]["public_key_ed25519"], manifest_sha256)
    log("grant_opened", grant_id=args.grant_id, manifest_sha256=manifest_sha256, calls=len(calls),
        not_after_utc=not_after, cpu_cap_s=args.cap, ledger_dir=str(ledger["dir"]),
        entry0_sha256=gate0_anchor.digest(entry))
    return 0


def settle_tag(request, grant_id: str, manifest_sha256: str, call: str, message: str) -> str:
    reader = gate0_anchor.TagReader(request)
    parent = reader.resolve(grant_id, "launch", call, manifest_sha256) or reader.resolve(grant_id, "reserve", call,
                                                                                       manifest_sha256)
    body = json.loads(message)
    if (body.get("kind"), body.get("grant_id"), body.get("manifest_sha256"), body.get("call")) != (
            "settle", grant_id, manifest_sha256, call):
        raise RuntimeError(f"{call}: the printed settle message does not bind this grant, manifest and call")
    ref = gate0_anchor.tag_ref(grant_id, "settle", call)
    return gate0_anchor._create_tag(request, ref, message, tree=parent[1]["tree"]["sha"], parents=[parent[1]["sha"]])


def _kill(send, target: int) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        send(target, signal.SIGKILL)


class OwnedProcesses:
    """Everything one call owns: every live, or exited and unreaped, descendant of this supervisor. While the call
    runs, the supervisor is their child subreaper, so the solver stays a descendant after validate-reference dies.
    It refuses to start while anything is already owned, so a call's cleanup never reaches other work (the rule of
    process_budget.ProcessTreeScope), and it restores the subreaper flag on exit."""

    def __init__(self):
        self.libc = ctypes.CDLL(None, use_errno=True)
        self.previous = ctypes.c_int()

    def _prctl(self, option: int, value) -> None:
        if self.libc.prctl(option, value, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), "the operator supervisor needs Linux child-subreaper support")

    def __enter__(self) -> "OwnedProcesses":
        self._prctl(PR_GET_CHILD_SUBREAPER, ctypes.byref(self.previous))
        self._prctl(PR_SET_CHILD_SUBREAPER, 1)
        try:
            if process_budget.tree_snapshot()[1]:
                raise RuntimeError("the supervisor already has child processes: a call's cleanup must never reach "
                                   "other work")
        except BaseException:
            self._prctl(PR_SET_CHILD_SUBREAPER, self.previous.value)
            raise
        return self

    def __exit__(self, *exc_info) -> None:
        self._prctl(PR_SET_CHILD_SUBREAPER, self.previous.value)

    @staticmethod
    def groups() -> dict[int, int]:
        """Each owned process and its process group, read from /proc (process_budget.tree_snapshot). A pid reused by
        another process, which has a different start time, is never included."""
        owned = {}
        for pid, row in process_budget.tree_snapshot()[1].items():
            with contextlib.suppress(ProcessLookupError):
                group = os.getpgid(pid)
                current = process_budget._stat(pid)
                if current is not None and current["start"] == row["start"]:
                    owned[pid] = group
        return owned

    def kill(self, child: subprocess.Popen) -> None:
        """One SIGKILL pass over the call. While validate-reference is unreaped its pid still names its process group,
        so that group is killed first. Then each owned process is killed together with its group, the solver's own
        session included. The supervisor's own group is never signalled."""
        if child.returncode is None:
            _kill(os.killpg, child.pid)
        own = os.getpgrp()
        for pid, group in self.groups().items():
            if group != own:
                _kill(os.killpg, group)
            _kill(os.kill, pid)

    def stop_and_reap(self, child: subprocess.Popen, stop_s: float) -> tuple[list[int], list[int]]:
        """Runs once validate-reference has been reaped. Kills and reaps whatever the call still owns, until the
        kernel reports no child left (and so no descendant either) or stop_s passes. Returns the pids reaped here, and
        any processes still owned at the deadline: none, unless a kill cannot take effect."""
        reaped, deadline = [], time.monotonic() + stop_s
        while True:
            self.kill(child)
            while True:
                try:
                    pid, _ = os.waitpid(-1, os.WNOHANG)
                except ChildProcessError:
                    return reaped, []
                if not pid:
                    break
                reaped.append(pid)
            if time.monotonic() >= deadline:
                return reaped, sorted(self.groups())
            time.sleep(0.01)


def supervisor_settlement(killed: str | None, envelope_cpu_s: float, cpu_s: float | None, meter_errors: list[dict],
                          lower_bound_cpu_s: float = 0.0) -> dict:
    """The operator's settlement of a call whose validate-reference printed none (contract item 6). The call stays
    consumed and is never relaunched.

    Its status is supervisor_meter_failed when the CPU meter failed (root #57472; the errors are kept),
    supervisor_cap when the cap killed it, and supervisor_unknown otherwise. It is charged its full envelope, or the
    CPU measured after the reap if that is larger. If the meter failed after the reap too (cpu_s None), the call's
    actual usage is unknown, and the CPU already read for it before the failure is a lower bound (root #57510). The
    charge is then the full envelope or that lower bound, whichever is larger. The reservation stays consumed, and the
    charge is never zero, never refunded and never below what was already read."""
    used = lower_bound_cpu_s if cpu_s is None else cpu_s
    settlement = {"status": "supervisor_meter_failed" if meter_errors else
                  "supervisor_cap" if killed else "supervisor_unknown",
                  "charged_cpu_s": round(max(envelope_cpu_s, used), 3),
                  "usage": "unknown" if cpu_s is None else "measured"}
    if cpu_s is None:
        settlement["lower_bound_cpu_s"] = round(lower_bound_cpu_s, 3)
    if meter_errors:
        settlement["meter_errors"] = meter_errors
    return settlement


def call_argv(call: dict, args, out: Path) -> list[str]:
    """validate-reference exactly as the manifest's row writes it."""
    argv = [sys.executable, "-m", "sundai_hotspot.reference_validation", "validate-reference", "--call", call["id"],
            "--timeout", f"{call['timeout_s']:g}", "--out", str(out), "--ledger-root", str(args.ledger_root),
            "--operator-key", str(args.key)]
    expected = call["command"].replace("<fresh empty dir>", str(out)).replace(
        "<operator ledger root>", str(args.ledger_root)).replace("<operator key file>", str(args.key))
    if " ".join(["python"] + argv[1:]) != expected:
        raise SystemExit(f"{call['id']}: the command differs from the manifest's row: {expected}")
    return argv


def _meter_error(where: str, exc: Exception) -> dict:
    return {"where": where, "type": type(exc).__name__, "message": str(exc)}


def run_call(call: dict, argv: list[str], out: Path, budget: dict, *, meter=None, cwd: str = "/app",
             poll_s: float = 0.25, stop_s: float = 10.0) -> dict:
    """Runs one call's validate-reference under the cumulative budget, in its own session. It returns only once
    nothing the call started is left (OwnedProcesses).

    The supervisor reads the meter itself, in this thread, while the call runs (root #57472). There is no separate
    watcher that a failed read could stop, so enforcement cannot end silently. Every process group the call owns is
    killed at once when the total passes the cap, or when a reading fails (the error is kept). When
    validate-reference exits, for any reason, whatever it left behind is killed and reaped. The CPU is read after
    that reap and saved. If that reading fails too, the call's usage is recorded as unknown (save_cpu). The result
    carries validate-reference's printed summary; when there is none, it carries the operator's own settlement
    instead (supervisor_settlement)."""
    meter = meter or cgroup_cpu_s
    # Beside the out dir, never inside it: the strict reader verifies the out dir's own files. The output is written
    # as it comes, not through pipes, so a process left holding a pipe cannot stall the supervisor.
    stdout_path, stderr_path = out.with_name(out.name + ".stdout"), out.with_name(out.name + ".stderr")
    killed, meter_errors = None, []
    with OwnedProcesses() as owned:
        start = meter()  # before the launch: if this read fails, nothing is launched
        last_read = budget["carried"] + start
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            child = subprocess.Popen(argv, cwd=cwd, stdout=stdout, stderr=stderr, start_new_session=True)
        while child.poll() is None:
            try:
                used = budget["carried"] + meter()
            except Exception as exc:  # no reading means no enforcement: stop the call now, on the cap's path
                meter_errors.append(_meter_error("while the call ran", exc))
                killed = f"the CPU meter failed while the call ran ({type(exc).__name__}: {exc})"
                owned.kill(child)
                break
            last_read = used
            if used > budget["cap"]:
                killed = f"cumulative CPU {used:.2f} s passed the cap {budget['cap']:g} s"
                owned.kill(child)  # validate-reference's group and every other group the call owns
                break
            time.sleep(poll_s)
        child.wait()
        reaped, survivors = owned.stop_and_reap(child, stop_s)
    try:
        final = meter()
    except Exception as exc:  # the actual usage is unknown: recorded as unknown, never as zero
        meter_errors.append(_meter_error("after the reap", exc))
        final = None
    cpu_s = None if final is None else final - start
    lower_bound = max(0.0, last_read - (budget["carried"] + start))  # what was read for this call before any failure
    used_now = None if final is None else budget["carried"] + final
    save_cpu(used_now, lower_bound=round(last_read, 6))
    stdout = stdout_path.read_text(encoding="utf-8", errors="replace")
    stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
    summary = None
    for line in reversed(stdout.strip().splitlines()):
        try:
            candidate = json.loads(line)
        except ValueError:
            continue
        if isinstance(candidate, dict) and candidate.get("settle_tag_message"):
            summary = candidate
            break
    settlement = None if summary else supervisor_settlement(
        killed, float(call["accounting"]["reserved_cpu_s"]), cpu_s, meter_errors, lower_bound)
    return {"out": str(out), "exit": child.returncode, "summary": summary, "killed": killed,
            "meter_errors": meter_errors, "usage": "unknown" if final is None else "measured", "reaped": reaped,
            "survivors": survivors, "settlement": settlement,
            "cpu_s_this_call": None if cpu_s is None else round(cpu_s, 3),
            "lower_bound_cpu_s_this_call": round(lower_bound, 3),
            "cumulative_cpu_s": None if used_now is None else round(used_now, 3),
            "stderr_tail": stderr.strip().splitlines()[-3:]}


def cmd_run(args) -> int:
    manifest, manifest_sha256 = load()
    check_key(manifest, args.key)
    ledger = gate0_anchor.read_ledger(args.ledger_root, manifest["operator"]["public_key_ed25519"], manifest_sha256)
    grant = ledger["grant"]
    if grant["grant_id"] != args.grant_id:
        raise SystemExit("the ledger's grant id differs from --grant-id")
    request = github()
    reader = gate0_anchor.TagReader(request)
    build = os.environ.get("BUILD_SHA", "")
    if len(build) != 40:
        raise SystemExit("BUILD_SHA (the merged build commit) is required")
    build_tree = request("GET", f"/git/commits/{build}")["tree"]["sha"]
    budget = {"cap": float(grant["cpu_cap_s"]), "carried": carried_cpu_s() - cgroup_cpu_s()}
    calls = [call for call in manifest["calls"] if not args.only or call["id"] in args.only]
    for call in calls:
        cid = call["id"]
        if reader.read(args.grant_id, "settle", cid, manifest_sha256) is not None:
            log("skip_settled", call=cid)
            continue
        if reader.read(args.grant_id, "launch", cid, manifest_sha256) is not None:
            log("stop_launched_unsettled", call=cid, note="a launch tag without a settle tag: reconcile by hand")
            return 3
        envelope = float(call["accounting"]["reserved_cpu_s"])
        used = budget["carried"] + cgroup_cpu_s()
        if used + envelope > budget["cap"]:
            log("stop_budget", call=cid, used_cpu_s=round(used, 3), envelope_cpu_s=envelope, cap=budget["cap"])
            return 4
        if reader.read(args.grant_id, "reserve", cid, manifest_sha256) is None:
            ref = gate0_anchor.tag_ref(args.grant_id, "reserve", cid)
            sha = gate0_anchor._create_tag(request, ref, gate0_anchor.tag_message(
                "reserve", args.grant_id, manifest_sha256, cid), tree=build_tree, parents=[build])
            log("reserved", call=cid, ref=ref, commit=sha)
        out = RUNS / f"{cid}-{int(time.time())}"
        out.mkdir(parents=True)
        result = run_call(call, call_argv(call, args, out), out, budget)
        if result["survivors"]:
            log("stop_survivors", call=cid, survivors=result["survivors"], killed=result["killed"], out=result["out"],
                cumulative_cpu_s=result["cumulative_cpu_s"], note="owned processes outlived every kill: reconcile "
                "by hand")
            return 7
        if result["summary"]:
            sha = settle_tag(request, args.grant_id, manifest_sha256, cid, result["summary"]["settle_tag_message"])
            log("settled", call=cid, status=result["summary"].get("status"), exit=result["exit"],
                charged_cpu_s=result["summary"].get("charged_cpu_s"), settle_commit=sha,
                cpu_s_this_call=result["cpu_s_this_call"], cumulative_cpu_s=result["cumulative_cpu_s"],
                out=result["out"])
        else:
            admitted = bool(gate0_anchor.call_entries(gate0_anchor.read_ledger(
                args.ledger_root, manifest["operator"]["public_key_ed25519"], manifest_sha256), cid))
            log("no_settlement_printed", call=cid, exit=result["exit"], killed=result["killed"], admitted=admitted,
                meter_errors=result["meter_errors"], usage=result["usage"], reaped=result["reaped"],
                stderr_tail=result["stderr_tail"], out=result["out"], cpu_s_this_call=result["cpu_s_this_call"],
                lower_bound_cpu_s_this_call=result["lower_bound_cpu_s_this_call"],
                cumulative_cpu_s=result["cumulative_cpu_s"])
            if admitted:
                settlement = result["settlement"]
                message = gate0_anchor.tag_message("settle", args.grant_id, manifest_sha256, cid,
                                                   status=settlement["status"], receipt_sha256=None, outputs={},
                                                   charged_cpu_s=settlement["charged_cpu_s"])
                sha = settle_tag(request, args.grant_id, manifest_sha256, cid, message)
                log("settled_by_supervisor", call=cid, settle_commit=sha, **settlement)
            return 5
        if result["meter_errors"]:  # validate-reference settled itself, but the meter failed: no further call
            log("stop_meter_failed", call=cid, meter_errors=result["meter_errors"], usage=result["usage"],
                killed=result["killed"])
            return 8
        if result["killed"]:
            log("stop_killed", call=cid, reason=result["killed"])
            return 6
    log("run_complete", calls=len(calls), cumulative_cpu_s=round(budget["carried"] + cgroup_cpu_s(), 3))
    return 0


def cmd_readback(args, kind: str) -> int:
    argv = [sys.executable, "-m", "sundai_hotspot.reference_validation", kind, "--out", str(args.out),
            "--ledger-root", str(args.ledger_root)]
    if kind == "record":
        argv[4:4] = ["--kind", "hotspot6"]
    done = subprocess.run(argv, cwd="/app", capture_output=True, text=True)
    log(f"{kind}_done", exit=done.returncode, stdout_tail=done.stdout.strip().splitlines()[-3:],
        stderr_tail=done.stderr.strip().splitlines()[-3:], out=str(args.out))
    return done.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("grant", "run", "record", "report"):
        p = sub.add_parser(name)
        p.add_argument("--ledger-root", type=Path, default=Path("/srv/gate0/ledger"))
        if name in ("grant", "run"):
            p.add_argument("--key", type=Path, default=Path("/srv/gate0/key/operator.pem"))
            p.add_argument("--grant-id", required=True)
        if name == "grant":
            p.add_argument("--cap", type=float, default=600.0)
        if name == "run":
            p.add_argument("--only", nargs="*")
        if name in ("record", "report"):
            p.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    RUNS.mkdir(parents=True, exist_ok=True)
    if args.command == "grant":
        return cmd_grant(args)
    if args.command == "run":
        return cmd_run(args)
    return cmd_readback(args, args.command)


if __name__ == "__main__":
    sys.exit(main())
