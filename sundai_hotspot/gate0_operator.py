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
cap, and a watcher kills the call's process group the moment the total passes the cap. Usage carries over between
container runs through /srv/gate0/runs/cpu-used.json. A call whose validate-reference dies without printing its
settlement is settled as unknown, charged its full envelope (contract item 6), and never relaunched.

Never prints the key, the token or the anchor credential.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, "/app")
from sundai_hotspot import gate0_anchor, reference_validation, slab049  # noqa: E402

RUNS = Path("/srv/gate0/runs")
CPU_FILE = RUNS / "cpu-used.json"
LOG = RUNS / "operator-log.jsonl"


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
    if not CPU_FILE.exists():
        return 0.0
    return float(json.loads(CPU_FILE.read_text(encoding="utf-8"))["used_cpu_s"])


def save_cpu(total: float) -> None:
    tmp = CPU_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"used_cpu_s": round(total, 6), "at": now()}), encoding="utf-8")
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


def run_call(call: dict, args, manifest_sha256: str, budget: dict) -> dict:
    """Runs one call under the cumulative budget. Returns the validate-reference summary (or a supervisor one)."""
    out = RUNS / f"{call['id']}-{int(time.time())}"
    out.mkdir(parents=True)
    argv = [sys.executable, "-m", "sundai_hotspot.reference_validation", "validate-reference", "--call", call["id"],
            "--timeout", f"{call['timeout_s']:g}", "--out", str(out), "--ledger-root", str(args.ledger_root),
            "--operator-key", str(args.key)]
    expected = call["command"].replace("<fresh empty dir>", str(out)).replace(
        "<operator ledger root>", str(args.ledger_root)).replace("<operator key file>", str(args.key))
    if " ".join(["python"] + argv[1:]) != expected:
        raise SystemExit(f"{call['id']}: the command differs from the manifest's row: {expected}")
    start = cgroup_cpu_s()
    child = subprocess.Popen(argv, cwd="/app", stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             start_new_session=True)
    killed = {"reason": None}

    def watch() -> None:
        while child.poll() is None:
            used = budget["carried"] + cgroup_cpu_s()
            if used > budget["cap"]:
                killed["reason"] = f"cumulative CPU {used:.2f} s passed the cap {budget['cap']:g} s"
                os.killpg(child.pid, signal.SIGKILL)
                return
            time.sleep(0.25)

    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    stdout, stderr = child.communicate()
    watcher.join(timeout=5)
    # beside the out dir, never inside it: the strict reader verifies the out dir's own files
    out.with_name(out.name + ".stdout").write_text(stdout, encoding="utf-8")
    out.with_name(out.name + ".stderr").write_text(stderr, encoding="utf-8")
    summary = None
    for line in reversed(stdout.strip().splitlines()):
        try:
            candidate = json.loads(line)
        except ValueError:
            continue
        if isinstance(candidate, dict) and candidate.get("settle_tag_message"):
            summary = candidate
            break
    used_now = budget["carried"] + cgroup_cpu_s()
    save_cpu(used_now)
    return {"out": str(out), "exit": child.returncode, "summary": summary, "killed": killed["reason"],
            "cpu_s_this_call": round(cgroup_cpu_s() - start, 3), "cumulative_cpu_s": round(used_now, 3),
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
        result = run_call(call, args, manifest_sha256, budget)
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
                stderr_tail=result["stderr_tail"], out=result["out"], cumulative_cpu_s=result["cumulative_cpu_s"])
            if admitted:
                message = gate0_anchor.tag_message("settle", args.grant_id, manifest_sha256, cid,
                                                   status="supervisor_unknown", receipt_sha256=None, outputs={},
                                                   charged_cpu_s=envelope)
                sha = settle_tag(request, args.grant_id, manifest_sha256, cid, message)
                log("settled_unknown", call=cid, charged_cpu_s=envelope, settle_commit=sha)
            return 5
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
