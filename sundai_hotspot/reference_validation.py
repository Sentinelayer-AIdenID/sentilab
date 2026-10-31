"""validate-reference (SLAB-049): the only path that may run an evaluator before it has passed gate zero.

It produces the gate-zero receipts, so it cannot require a prior PASS; that would be circular. Everything the
frozen manifest (docs/sentilab/diagnostics/SLAB-049/CALL-LIST-v4.json) does not allow is refused before anything
is reserved or launched. In code, at this one entry (the manifest's enforcement.in_code_at_entry):

- the manifest must be byte-identical to what this tree generates (sources, references, raw layout pins, predicate,
  accounting); the prior snapped manifest, kept as an artifact, is refused;
- only a listed call id, with its listed --timeout (and engine, reference and grid if given), before the window
  closes, on the listed architecture, on POSIX (the CPU limit is RLIMIT_CPU), and never under CI allocation
  (CI_ALLOCATION=1): in CI every native HotSpot launch goes through sundai_hotspot.ci_gate, and SLAB-049 solves
  run only on the grant host;
- the binary must identify as the listed kind and match its build provenance, and must not carry the CI entry
  guard; it runs from a private, content-addressed copy, and the shared libraries the loader resolves must be the
  build's, hashed before and after;
- the raw reference geometry is checked with the continuous rules only (margin, halo, spacing), never the search
  lattice;
- admission is atomic under the ledger lock: one manifest per ledger, each call reserved once (no retries), and the
  admitted count and charged CPU must stay inside the manifest's cap;
- the reservation and receipt are written before staging; the solver runs in its own process group under
  RLIMIT_CPU (its timeout) and a separate wall deadline (the same timeout); the group is killed and the solver
  reaped on every path; the receipt and the ledger settle durably on every exit path.

What this entry cannot do is the operator supervisor's contract (the manifest's enforcement section).

    python -m sundai_hotspot.reference_validation validate-reference --call CALL_ID --timeout SECONDS \\
        --out FRESH_DIR --ledger GRANT_LEDGER_DIR [--binary PATH]
    python -m sundai_hotspot.reference_validation record --kind hotspot6 --ledger GRANT_LEDGER_DIR --out RECORD.json
    python -m sundai_hotspot.reference_validation report --ledger GRANT_LEDGER_DIR --out REPORT.json

Running validate-reference is a thermal solve. It needs warden's grant. `record` and `report` only read files.
"""
from __future__ import annotations

import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from sundai_hotspot import gate_zero, provenance, slab049
from sundai_hotspot.tap_oracle import REPO_ROOT

MANIFEST_PATH = slab049.EVIDENCE_DIR / slab049.MANIFEST_NAME
LOCK_NAME = "ledger.lock"
# The solver gets exactly this environment: locale and zone as in production, one BLAS thread with a pinned
# OpenBLAS dispatch so a replay is byte-identical whichever BLAS the loader resolves.
SOLVER_ENVIRONMENT = {"LANG": "C", "LC_ALL": "C", "TZ": "UTC", "OPENBLAS_CORETYPE": "Haswell",
                      "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
# aneta-claude's independent network model (#56739) predicts these grid 32 -> 64 changes in the block-centre peak
# on HotSpot 6.0. Context for the report only: nothing is frozen on them, nor on the old mesh error.
NETWORK_MODEL_MESH_DELTA_K = {"ascend910": 0.01, "micro150": 0.18}
OLD_HOTSPOT7_MESH_ERROR_K = {"ascend910": 0.16, "micro150": 0.79}


class CallRefused(RuntimeError):
    """The requested call is not what the frozen manifest allows."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _cpu_s(who: int) -> float:
    import resource
    usage = resource.getrusage(who)
    return usage.ru_utime + usage.ru_stime


def _children_cpu_s() -> float:
    import resource
    return _cpu_s(resource.RUSAGE_CHILDREN)


def _self_cpu_s() -> float:
    import resource
    return _cpu_s(resource.RUSAGE_SELF)


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_durably(path: Path, data: bytes) -> None:
    """Atomic replace with fsync of the file and its directory."""
    temporary = path.with_name(path.name + ".tmp")
    with open(temporary, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    _fsync_directory(path.parent)


def _create_durably(path: Path, data: bytes) -> None:
    """Write-once (O_EXCL) with fsync: an existing entry is never replaced."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    _fsync_directory(path.parent)


def _json(value) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def load_manifest(manifest_path: Path | None = None) -> tuple[dict, str]:
    """The manifest and its SHA-256, refused unless it is exactly what this tree generates."""
    data = Path(manifest_path or MANIFEST_PATH).read_bytes()
    try:
        return slab049.check_manifest(data), hashlib.sha256(data).hexdigest()
    except slab049.ManifestMismatch as exc:
        raise CallRefused(str(exc)) from exc


def admit(call_id: str, manifest: dict, *, timeout_s: float | None, kind: str | None = None,
          reference: str | None = None, grid: int | None = None, now: datetime | None = None) -> dict:
    """Refuse anything the manifest does not list. The timeout is required and must be the call's own."""
    if os.environ.get("CI_ALLOCATION") == "1":
        raise CallRefused("validate-reference never runs under CI allocation: SLAB-049 solves run only on warden's "
                          "grant host, and in CI every native HotSpot launch goes through sundai_hotspot.ci_gate")
    if os.name != "posix":
        raise CallRefused("validate-reference needs POSIX: the CPU limit is RLIMIT_CPU on the solver process "
                          "(Linux, macOS). Windows has no RLIMIT_CPU, and its equivalent, a Job Object process-time "
                          "limit, is not implemented")
    calls = {c["id"]: c for c in manifest.get("calls", [])}
    if call_id not in calls:
        raise CallRefused(f"{call_id!r} is not a call in the frozen manifest")
    call = calls[call_id]
    for name, given, listed in (("engine", kind, call["kind"]), ("reference", reference, call["reference"]),
                                ("grid", grid, call["grid"])):
        if given is not None and given != listed:
            raise CallRefused(f"{call_id}: {name} {given!r} is not the listed {listed!r}")
    if (timeout_s is None or isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float))
            or float(timeout_s) != float(call["timeout_s"])):
        raise CallRefused(f"{call_id}: --timeout must be the listed {call['timeout_s']:g} s, not {timeout_s!r}")
    deadline = datetime.fromisoformat(manifest["grant_window"]["not_after_utc"].replace("Z", "+00:00"))
    if (now or _now()) > deadline:
        raise CallRefused(f"the grant window closed at {deadline.isoformat()}")
    architecture = manifest["accounting"]["host_architecture"]
    if platform.machine() != architecture:
        raise CallRefused(f"this host is {platform.machine()}; the manifest lists {architecture}")
    return call


@contextlib.contextmanager
def _ledger_lock(ledger: Path):
    import fcntl
    ledger.mkdir(parents=True, exist_ok=True)
    with open(ledger / LOCK_NAME, "a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def ledger_totals(ledger: Path) -> dict:
    """Admitted calls and the CPU charged so far. A settled call is charged its measured CPU (its reservation when
    the measurement is unknown); an unsettled one, its reservation."""
    calls, charged, manifests = [], 0.0, set()
    for path in sorted(Path(ledger).glob("*.reserved.json")):
        reservation = json.loads(path.read_text(encoding="utf-8"))
        calls.append(reservation["call"])
        manifests.add(reservation["manifest_sha256"])
        settled = path.with_name(path.name[: -len(".reserved.json")] + ".settled.json")
        measured = json.loads(settled.read_text(encoding="utf-8")).get("charged_cpu_s") if settled.is_file() else None
        known = isinstance(measured, (int, float)) and not isinstance(measured, bool) and math.isfinite(measured)
        charged += float(measured) if known and measured >= 0 else float(reservation["reserved_cpu_s"])
    return {"calls": calls, "charged_cpu_s": charged, "manifest_sha256": sorted(manifests)}


def _admit_to_ledger(ledger: Path, call: dict, manifest: dict, manifest_sha256: str, reservation: dict) -> None:
    """Atomic admission: under the ledger lock, check the cumulative count and CPU, then reserve exactly once."""
    accounting = manifest["accounting"]
    with _ledger_lock(ledger):
        totals = ledger_totals(ledger)
        if totals["manifest_sha256"] and totals["manifest_sha256"] != [manifest_sha256]:
            raise CallRefused("this ledger holds calls admitted under another manifest; one ledger per manifest")
        if call["id"] in totals["calls"]:
            raise CallRefused(f"{call['id']} was already admitted in this ledger; calls are not retried")
        if len(totals["calls"]) + 1 > accounting["calls"]:
            raise CallRefused(f"the ledger has admitted {len(totals['calls'])} calls; the manifest allows "
                              f"{accounting['calls']}")
        reserved = float(call["accounting"]["reserved_cpu_s"])
        if totals["charged_cpu_s"] + reserved > accounting["manifest_cpu_cap_s"] + 1e-9:
            raise CallRefused(f"{totals['charged_cpu_s']:.2f} CPU-s charged plus this call's {reserved:g} would pass "
                              f"the {accounting['manifest_cpu_cap_s']:g} CPU-s cap")
        try:
            _create_durably(ledger / f"{call['id']}.reserved.json", _json(reservation))
        except FileExistsError as exc:
            raise CallRefused(f"{call['id']} was already reserved in this ledger; calls are not retried") from exc


def _private_executable(binary: Path, directory: Path) -> Path:
    """Copy the binary's bytes once into a private 0700 directory, as a 0500 file named by its hash. The identity
    check reads that copy, and that copy is what runs: the bytes hashed are the bytes executed."""
    data = Path(binary).read_bytes()
    target = directory / f"evaluator-{hashlib.sha256(data).hexdigest()[:16]}"
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o700)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
    os.chmod(target, 0o500)
    return target


def _kill_group(group: int) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(group, signal.SIGKILL)


def _wait_unreaped(pid: int, timeout: float) -> bool:
    """Wait for the solver to exit without reaping it (WNOWAIT), so its process-group id cannot be reused before the
    group is killed. True when it exited, False at the wall deadline."""
    deadline = time.monotonic() + timeout
    while os.waitid(os.P_PID, pid, os.WEXITED | os.WNOWAIT | os.WNOHANG) is None:
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.01)
    return True


def _cpu_limit(seconds: int):
    def apply() -> None:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (seconds, seconds))  # soft = hard: SIGKILL at the limit
    return apply


def stage(reference: gate_zero.Reference, spec: dict, out: Path) -> dict[str, str]:
    """Write the reference inputs fresh into the call's new directory; they must equal the frozen ones.

    validate_call has already refused a non-empty directory; the only file there is the call's own receipt.
    """
    out = Path(out)
    if any(path.name != "receipt.json" for path in out.iterdir()):
        raise CallRefused(f"{out} holds files other than this call's receipt; every call needs a fresh directory")
    files = slab049.generate_reference(spec, out)
    for name, data in files.items():  # local LCF paths and LF line ends, as frozen
        (out / name).write_bytes(data)
    frozen = gate_zero.frozen_inputs(reference)
    staged = {name: _sha256(out / name) for name in frozen}
    if staged != frozen:
        raise CallRefused(f"{reference.id}: fresh inputs differ from the frozen ones: "
                          f"{sorted(n for n in frozen if staged[n] != frozen[n])}")
    return staged


def validate_call(call_id: str, out: Path, ledger: Path, *, timeout_s: float | None, binary: Path | None = None,
                  manifest_path: Path | None = None, kind: str | None = None, reference: str | None = None,
                  grid: int | None = None, now: datetime | None = None) -> dict:
    """Run one listed call in a fresh process and settle its receipt. Needs no prior gate-zero PASS."""
    manifest, manifest_sha256 = load_manifest(manifest_path)
    call = admit(call_id, manifest, timeout_s=timeout_s, kind=kind, reference=reference, grid=grid, now=now)
    pinned = gate_zero.reference(call["reference"])
    try:  # the pinned raw layout, judged by the continuous rules only (never the search lattice)
        spec = slab049.reference_spec(pinned.id)
    except slab049.ReferenceGeometryError as exc:
        raise CallRefused(f"{call_id}: {exc}") from exc
    out, ledger = Path(out), Path(ledger)
    if out.exists() and any(out.iterdir()):
        raise CallRefused(f"{out} is not empty; every call needs a fresh directory")
    source = Path(binary or REPO_ROOT / call["binary"]).resolve()
    private = Path(tempfile.mkdtemp(prefix="slab049-evaluator-"))
    try:
        executable = _private_executable(source, private)
        try:
            identity = gate_zero.evaluator_identity(call["kind"], executable)
            build = provenance.require_build_provenance(call["kind"], source, identity["binary_sha256"])
        except (gate_zero.GateZeroRefusal, provenance.ProvenanceError) as exc:
            raise CallRefused(f"{call_id}: {exc}") from exc
        if provenance.CI_ENTRY_GUARD in executable.read_bytes():
            raise CallRefused(f"{call_id}: this binary was built with the CI entry guard (CI_ALLOCATION=1) and runs "
                              "only through sundai_hotspot.ci_gate under a CI reservation; the grant host needs a "
                              "build without CI_ALLOCATION")
        runtime = provenance.resolved_libraries(executable)
        if provenance.library_identity(runtime) != provenance.library_identity(build["provenance"]["libraries"]):
            raise CallRefused(f"{call_id}: the shared libraries the loader resolves now differ from the build's")
        return _run_call(call, pinned, spec, out, ledger, manifest, manifest_sha256, executable, source, identity,
                         build, runtime, now)
    finally:
        shutil.rmtree(private, ignore_errors=True)


def _run_call(call: dict, pinned: gate_zero.Reference, spec: dict, out: Path, ledger: Path, manifest: dict,
              manifest_sha256: str, executable: Path, source: Path, identity: dict, build: dict, runtime: dict,
              now: datetime | None) -> dict:
    timeout = float(call["timeout_s"])
    argv = slab049.tap_argv(str(executable), call["grid"])
    receipt = {
        "schema": gate_zero.RECEIPT_SCHEMA, "call": call["id"], "role": call["role"], "replay_of": call["replay_of"],
        "manifest_sha256": manifest_sha256, "evaluator": identity, "reference": pinned.id, "role_in_gate": pinned.role,
        "layout_identity": pinned.layout_identity, "raw_layout_sha256": pinned.raw_layout_sha256,
        "paper_c": pinned.paper_c, "grid": call["grid"], "argv": argv,
        "binary": {"source": source.as_posix(), "executed": "a private content-addressed copy (0500 in a 0700 "
                   "directory), removed after the call"},
        "build_provenance": {"path": build["path"], "sha256": build["sha256"]}, "runtime": runtime,
        "geometry": spec["geometry"], "temperature_label": gate_zero.TEMPERATURE_LABELS[call["kind"]],
        "timeout_s": timeout, "cpu_limit_s": call["cpu_limit_s"], "solver_environment": SOLVER_ENVIRONMENT,
        "host": {"architecture": platform.machine(), "node": platform.node(), "python": sys.version.split()[0]},
        "reserved_utc": (now or _now()).isoformat(), "status": "reserved",
    }
    reservation = {key: receipt[key] for key in ("call", "manifest_sha256", "evaluator", "reference", "grid",
                                                 "reserved_utc")}
    reservation.update({"out": out.resolve().as_posix(), "reserved_cpu_s": call["accounting"]["reserved_cpu_s"]})
    _admit_to_ledger(ledger, call, manifest, manifest_sha256, reservation)
    out.mkdir(parents=True, exist_ok=True)
    _write_durably(out / "receipt.json", _json(receipt))  # reserved and identified before anything runs
    started, clock = _now(), time.perf_counter()
    self_before, children_before = _self_cpu_s(), _children_cpu_s()
    try:
        receipt["inputs"] = stage(pinned, spec, out)
        receipt["config_sha256"] = receipt["inputs"]["new_hotspot.config"]
        _write_durably(out / "receipt.json", _json(receipt))
        solver_before = _children_cpu_s()
        with (out / "stdout.txt").open("wb") as stdout, (out / "stderr.txt").open("wb") as stderr:
            process = subprocess.Popen(argv, cwd=out, stdout=stdout, stderr=stderr, env=SOLVER_ENVIRONMENT,
                                       start_new_session=True, preexec_fn=_cpu_limit(call["cpu_limit_s"]))
            try:
                exited = _wait_unreaped(process.pid, timeout)
            finally:
                _kill_group(process.pid)  # the whole group; the leader is not yet reaped, so the id is still ours
                code = process.wait()     # reap
        receipt["solver_cpu_s"] = _children_cpu_s() - solver_before
        if not exited:
            code = None
        if code is None:
            receipt["status"], receipt["exit_status"] = "wall_timeout", None
        else:
            receipt["exit_status"] = code
            limited = -code == signal.SIGXCPU or (-code == signal.SIGKILL and
                                                   receipt["solver_cpu_s"] >= call["cpu_limit_s"] - 1)
            receipt["status"] = "exited" if code >= 0 else ("cpu_limit" if limited else "signalled")
        receipt["runtime_after"] = provenance.resolved_libraries(executable)
        if provenance.library_identity(receipt["runtime_after"]) != provenance.library_identity(runtime):
            receipt["status"] = "runtime_changed"
    except subprocess.TimeoutExpired:
        receipt["status"], receipt["exit_status"] = "stage_error", None
        receipt["error"] = "the TAP generator passed its wall deadline"
    except OSError as exc:
        receipt["status"] = "launch_error" if "inputs" in receipt else "stage_error"
        receipt["exit_status"], receipt["error"] = None, repr(exc)
    except BaseException as exc:  # settle the receipt, then let the caller see the failure
        receipt["status"] = "error" if "inputs" in receipt else "stage_error"
        receipt["exit_status"], receipt["error"] = None, f"{type(exc).__name__}: {exc}"
        raise
    finally:
        _settle(call, receipt, out, ledger, started, clock, self_before, children_before)
    return receipt


def _settle(call: dict, receipt: dict, out: Path, ledger: Path, started: datetime, clock: float,
            self_before: float, children_before: float) -> None:
    """Durable settlement on every exit path: the receipt, then the write-once ledger entry that binds it."""
    receipt["started_utc"], receipt["finished_utc"] = started.isoformat(), _now().isoformat()
    receipt["wall_s"] = time.perf_counter() - clock
    receipt["outputs"] = {name: _sha256(out / name) for name in gate_zero.RECEIPT_OUTPUTS if (out / name).is_file()}
    if receipt["status"] == "exited" and receipt["exit_status"] == 0:
        try:
            receipt["solve_record"] = slab049.summarize_evaluation(
                out, grid_size=call["grid"], grid_format=gate_zero.GRID_FORMATS[call["kind"]])
        except Exception as exc:  # the raw outputs stay; the receipt says why the record failed
            receipt["status"], receipt["error"] = "record_error", f"{type(exc).__name__}: {exc}"
    receipt["children_cpu_s"] = _children_cpu_s() - children_before
    receipt["self_cpu_s"] = _self_cpu_s() - self_before
    receipt["charged_cpu_s"] = receipt["children_cpu_s"] + receipt["self_cpu_s"]
    receipt["overshoot_cpu_s"] = max(0.0, receipt["charged_cpu_s"] - call["accounting"]["reserved_cpu_s"])
    _write_durably(out / "receipt.json", _json(receipt))
    settled = {key: receipt.get(key) for key in ("call", "manifest_sha256", "status", "exit_status", "started_utc",
                                                 "finished_utc", "wall_s", "solver_cpu_s", "children_cpu_s",
                                                 "self_cpu_s", "charged_cpu_s", "overshoot_cpu_s", "outputs")}
    settled.update({"reserved_cpu_s": call["accounting"]["reserved_cpu_s"], "out": out.resolve().as_posix(),
                    "receipt_sha256": _sha256(out / "receipt.json")})
    _create_durably(ledger / f"{call['id']}.settled.json", _json(settled))


def report(ledger: Path, manifest_path: Path | None = None) -> dict:
    """From the ledger, by admitted call id, with no extra call (reads receipts and outputs only):

    - every manifest call's settlement, or that it is missing;
    - HotSpot 6.0's (and the comparator's) grid 32 -> 64 change per reference, on the block-centre metric and the
      grid peak;
    - CPU seconds per call;
    - whether each replay's outputs are byte-identical to its primary's;
    - the same-index spreader-sink drop and the same-index stack at the active argmax (reported, not asserted).
    """
    data = Path(manifest_path or MANIFEST_PATH).read_bytes()
    manifest, manifest_sha256 = json.loads(data), hashlib.sha256(data).hexdigest()
    entries = {}
    for call in manifest["calls"]:
        reservation = gate_zero._ledger_entry(ledger, call["id"], "reserved")
        settled = gate_zero._ledger_entry(ledger, call["id"], "settled")
        entry = {"call": call["id"], "kind": call["kind"], "reference": call["reference"], "grid": call["grid"],
                 "role": call["role"], "replay_of": call["replay_of"], "gating": call["gating"],
                 "admitted": reservation is not None, "settled": None if settled is None else settled.get("status"),
                 "charged_cpu_s": None if settled is None else settled.get("charged_cpu_s"),
                 "solver_cpu_s": None if settled is None else settled.get("solver_cpu_s")}
        if reservation is not None and reservation.get("manifest_sha256") != manifest_sha256:
            entry["settled"] = "admitted under another manifest"
        elif settled is not None and (settled.get("status"), settled.get("exit_status")) == ("exited", 0):
            directory = Path(reservation["out"])
            receipt = json.loads((directory / "receipt.json").read_text(encoding="utf-8"))
            record = receipt.get("solve_record", {})
            entry.update({"selector_c": gate_zero.tap_selector_c(directory / "sample.steady")[0],
                          "grid_peak_c": record.get("active_layer_grid_peak", {}).get("peak_C"),
                          "outputs": receipt.get("outputs", {}),
                          "drop": record.get("spreader_sink_drop_diagnostic"),
                          "stack": record.get("same_index_stack_at_active_argmax")})
        entries[call["id"]] = entry
    rows = []
    for kind in sorted({c["kind"] for c in manifest["calls"]}):
        for reference in sorted({c["reference"] for c in manifest["calls"]}):
            g64 = entries.get(gate_zero.call_id("primary", kind, reference, 64), {})
            g32 = entries.get(gate_zero.call_id("primary", kind, reference, 32), {})
            replay = entries.get(gate_zero.call_id("replay", kind, reference, 64), {})
            both = "selector_c" in g64 and "selector_c" in g32
            fixture = reference.split("-")[0]
            rows.append({
                "kind": kind, "reference": reference, "temperature_label": gate_zero.TEMPERATURE_LABELS[kind],
                "block_centre_c": {"64": g64.get("selector_c"), "32": g32.get("selector_c"),
                                   "64 replay": replay.get("selector_c")},
                "grid32_to_64_block_centre_delta_k": g64["selector_c"] - g32["selector_c"] if both else None,
                "grid32_to_64_grid_peak_delta_k": (g64["grid_peak_c"] - g32["grid_peak_c"]
                                                   if both and None not in (g64["grid_peak_c"], g32["grid_peak_c"])
                                                   else None),
                "network_model_prediction_k": NETWORK_MODEL_MESH_DELTA_K.get(fixture) if kind == "hotspot6" else None,
                "old_hotspot7_mesh_error_k": OLD_HOTSPOT7_MESH_ERROR_K.get(fixture),
                "replay_byte_identical": (all(g64["outputs"].get(name) == replay["outputs"].get(name)
                                              for name in gate_zero.REPLAY_OUTPUTS)
                                          if "outputs" in g64 and "outputs" in replay else None),
                "spreader_sink_drop_g64": g64.get("drop"), "same_index_stack_g64": g64.get("stack"),
            })
    missing = [e["call"] for e in entries.values() if e["settled"] != "exited"]
    return {"schema": "sentilab-slab049-manifest-report-v2", "manifest_sha256": manifest_sha256,
            "calls": list(entries.values()), "rows": rows, "not_completed": missing,
            "note": "nothing here is frozen as a mesh error; the next protocol sets its own"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("validate-reference")
    record = sub.add_parser("record")
    summary = sub.add_parser("report")
    run.add_argument("--call", required=True)
    run.add_argument("--timeout", type=float, required=True, help="the call's listed timeout, in seconds")
    run.add_argument("--binary", type=Path)
    run.add_argument("--kind")
    run.add_argument("--reference")
    run.add_argument("--grid", type=int)
    record.add_argument("--kind", required=True, choices=sorted(gate_zero.EVALUATOR_KINDS))
    record.add_argument("--binary", type=Path)
    for command in (run, record, summary):
        command.add_argument("--ledger", type=Path, required=True)
        command.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "report":
        args.out.write_text(json.dumps(report(args.ledger), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 0
    if args.command == "validate-reference":
        try:
            receipt = validate_call(args.call, args.out, args.ledger, timeout_s=args.timeout, binary=args.binary,
                                    kind=args.kind, reference=args.reference, grid=args.grid)
        except CallRefused as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return 2
        print(json.dumps({k: receipt.get(k) for k in ("call", "status", "exit_status", "wall_s", "charged_cpu_s")}))
        return 0 if receipt["status"] == "exited" and receipt["exit_status"] == 0 else 1
    binary = args.binary or REPO_ROOT / gate_zero.EVALUATOR_KINDS[args.kind]["binary"]
    result = gate_zero.build_record(args.kind, binary, args.ledger)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(result["verdict"])
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
