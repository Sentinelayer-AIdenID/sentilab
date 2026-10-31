"""validate-reference (SLAB-049): the only path that may run an evaluator before it has passed gate zero.

It produces the gate-zero receipts, so it cannot require a prior PASS; that would be circular. The order of one call,
as validate_call and _run_call write it. Accounting starts before any work, and admission comes before any process
(root's round-D review of PR #56):

0. The accounting starts: this invocation's own and its children's CPU counters, before anything else.
1. Refusals that do no process work, cheapest first: the manifest must be byte-identical to what this tree generates;
   only a listed call id with its listed --timeout (and engine, reference and grid if given), inside the manifest's
   window, on the listed architecture, on POSIX, never under CI allocation (CI_ALLOCATION=1); the operator's key must
   match the manifest's pinned public key (a null pin refuses here); a launch credential must be present.
2. The operator's grant: the signed, hash-chained ledger (gate0_anchor) must verify, and its grant's cap may not
   exceed the manifest's.
3. Prechecks that only read files: the pinned raw layout by the continuous rules (never the search lattice), a fresh
   output directory, the binary's identity on a private content-addressed copy, its build provenance, and the CI
   entry guard.
4. THE ADMISSION (gate0_anchor.admit_and_reserve), one critical section for the grant, the single place where the
   operator's authority is checked: under the ledger's lock, the grant's window, the call's place in the grant, the
   operator's reserve tag, no ledger entry and no earlier admission anywhere (the anchored admission chain); every
   admitted call charged its envelope or its measured CPU, and this call's envelope within the grant's cap; then the
   next admission tag CREATED (create-only) and the signed reservation appended. The window is read on the clock
   after the remote reads and before the create, and again when the create returns; a create that returns after the
   cutoff stays consumed and charged and settles as window_closed at step 5, before any process. From here every exit settles; the call stays consumed and charged, and is never retried, settle tag or
   not.
5. Setup: a fresh output directory and a signed receipt.
6. The process-capable precheck, inside the attempt: the shared libraries the binary's loader resolves for the
   private copy must equal the build's. A mismatch settles the call as runtime_refused.
7. Staging: the TAP inputs written fresh and compared with the frozen ones.
8. THE CLAIM (claim_launch): the launch tag is CREATED, create-only, immediately before launch. Only a successful
   create launches. An existing tag refuses; an uncertain create consumes the call with no launch.
9. The launch: the private copy in its own process group, under RLIMIT_CPU and a wall deadline both equal to its
   timeout; the group is killed while the leader is unreaped, then the solver is reaped. Every other child (the TAP
   generator, the two loader listings) runs under its own RLIMIT_CPU and wall deadline (slab049, provenance).
10. Settlement: the signed receipt and a signed settlement entry, on every exit path after 4, with the CPU charged
    since 0. The operator then writes the settle tag (its message is printed).

What this entry cannot do is the operator supervisor's contract (the manifest's enforcement section).

    python -m sundai_hotspot.reference_validation validate-reference --call CALL_ID --timeout SECONDS \\
        --out FRESH_DIR [--ledger-root DIR] [--operator-key PEM] [--binary PATH]
    python -m sundai_hotspot.reference_validation record --kind hotspot6 [--ledger-root DIR] --out RECORD.json
    python -m sundai_hotspot.reference_validation report [--ledger-root DIR] --out REPORT.json

The ledger root, the operator key and the credentials come from the operator's environment (SLAB049_LEDGER_ROOT,
SLAB049_OPERATOR_KEY, SLAB049_ANCHOR_TOKEN to claim launches, GH_TOKEN to read tags), never from the repository.
Running validate-reference is a thermal solve. It needs warden's grant. `record` and `report` only read.
"""
from __future__ import annotations

import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from sundai_hotspot import gate0_anchor, gate_zero, provenance, slab049
from sundai_hotspot.gate0_anchor import AnchorUnavailable, AuthenticationError, ClaimRefused, ClaimUncertain
from sundai_hotspot.tap_oracle import REPO_ROOT

try:  # CPU accounting (getrusage); Windows has none, and validate-reference refuses there (admit)
    import resource
except ImportError:
    resource = None

ANCHOR_TOKEN_ENV = "SLAB049_ANCHOR_TOKEN"   # the operator's tag-creation credential, supplied by its supervisor
OPERATOR_SIGNER_ENV = "SLAB049_OPERATOR_KEY"  # path to the operator's Ed25519 private key, outside the repository
# The solver gets exactly this environment: locale and zone as in production, one BLAS thread with a pinned
# OpenBLAS dispatch so a replay is byte-identical whichever BLAS the loader resolves.
SOLVER_ENVIRONMENT = {"LANG": "C", "LC_ALL": "C", "TZ": "UTC", "OPENBLAS_CORETYPE": "Haswell",
                      "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
# aneta-claude's independent network model (#56739) predicts these grid 32 -> 64 changes in the block-centre peak
# on HotSpot 6.0. Context for the report only: nothing is frozen on them, nor on the old mesh error.
NETWORK_MODEL_MESH_DELTA_K = {"ascend910": 0.01, "micro150": 0.18}
OLD_HOTSPOT7_MESH_ERROR_K = {"ascend910": 0.16, "micro150": 0.79}


class CallRefused(RuntimeError):
    """The requested call is not what the frozen manifest and the operator allow. Nothing was launched."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _children_cpu_s() -> float:
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    return usage.ru_utime + usage.ru_stime


def _self_cpu_s() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return usage.ru_utime + usage.ru_stime


def _write_durably(path: Path, data: bytes) -> None:
    """Atomic replace with fsync of the file and its directory."""
    temporary = path.with_name(path.name + ".tmp")
    with open(temporary, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _json(value) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def load_manifest(manifest_path: Path | None = None) -> tuple[dict, str]:
    """The manifest and its SHA-256, refused unless it is exactly what this tree generates."""
    data = Path(manifest_path or slab049.MANIFEST_PATH).read_bytes()
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
    if os.name != "posix" or resource is None:
        raise CallRefused("validate-reference needs POSIX: the CPU limit is RLIMIT_CPU on each process (Linux, "
                          "macOS). Windows has no RLIMIT_CPU, and its equivalent, a Job Object process-time limit, "
                          "is not implemented")
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
    if (now or _now()) > _utc(manifest["grant_window"]["not_after_utc"]):
        raise CallRefused(f"the manifest's window closed at {manifest['grant_window']['not_after_utc']}")
    architecture = manifest["accounting"]["host_architecture"]
    if platform.machine() != architecture:
        raise CallRefused(f"this host is {platform.machine()}; the manifest lists {architecture}")
    return call


def operator_key(manifest: dict, key_path: Path | None):
    """The operator's private key (from outside the repository) and the manifest's pinned public key; they must
    match."""
    pinned = manifest["operator"]["public_key_ed25519"]
    if not pinned:
        raise CallRefused("no operator public key is pinned in the manifest: warden pins it before the grant")
    path = key_path or os.environ.get(OPERATOR_SIGNER_ENV)
    if not path:
        raise CallRefused(f"no operator key ({OPERATOR_SIGNER_ENV}): only the operator's supervisor can admit a call")
    try:
        key = gate0_anchor.load_private_key(Path(path))
    except (OSError, ValueError, TypeError, AuthenticationError) as exc:
        raise CallRefused(f"the operator key cannot be loaded: {type(exc).__name__}") from exc
    if gate0_anchor.public_key_hex(key) != pinned:
        raise CallRefused("the operator key is not the one the manifest pins")
    return key, pinned


def _cpu_counters() -> dict:
    """This process's own CPU and its reaped children's so far: where an invocation's accounting starts."""
    if resource is None:  # validate-reference refuses off POSIX (admit)
        return {"self_s": 0.0, "children_s": 0.0}
    return {"self_s": _self_cpu_s(), "children_s": _children_cpu_s()}


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


def validate_call(call_id: str, out: Path, *, timeout_s: float | None, ledger_root: Path | None = None,
                  operator_key_path: Path | None = None, anchor_request=None, binary: Path | None = None,
                  manifest_path: Path | None = None, kind: str | None = None, reference: str | None = None,
                  grid: int | None = None, now: datetime | None = None) -> dict:
    """Admit and run one listed call (the order is in the module docstring). Needs no prior gate-zero PASS.

    anchor_request is the operator's GitHub client (gate0_anchor.github_request with SLAB049_ANCHOR_TOKEN): it reads
    the tags and creates the admission and launch tags. Without it nothing is admitted and nothing launches.
    """
    # 0. The accounting starts before any work of this invocation: every exit after admission is charged from here.
    baseline, started, clock = _cpu_counters(), _now(), time.perf_counter()
    # 1. Refusals that do no process work, cheapest first.
    manifest, manifest_sha256 = load_manifest(manifest_path)
    call = admit(call_id, manifest, timeout_s=timeout_s, kind=kind, reference=reference, grid=grid, now=now)
    key, public_hex = operator_key(manifest, operator_key_path)
    if anchor_request is None:
        token = os.environ.get(ANCHOR_TOKEN_ENV)
        if not token:
            raise CallRefused(f"no launch credential ({ANCHOR_TOKEN_ENV}): without the claim nothing launches")
        anchor_request = gate0_anchor.github_request(manifest["anchor"]["repository"], token)
    configured_root = ledger_root or os.environ.get("SLAB049_LEDGER_ROOT")
    if not configured_root:
        raise CallRefused("no operator ledger root is configured (SLAB049_LEDGER_ROOT)")
    root = Path(configured_root)
    # 2. The operator's grant: the signed ledger must verify, and the grant's cap may not exceed the manifest's.
    #    Everything that can change (the window, the call's place in the grant, the operator's reserve tag, the
    #    ledger and the admission chain) is checked once, atomically, at admission (step 4).
    try:
        grant = gate0_anchor.read_ledger(root, public_hex, manifest_sha256)["grant"]
    except AuthenticationError as exc:
        raise CallRefused(f"{call_id}: {type(exc).__name__}: {exc}") from exc
    if grant["cpu_cap_s"] > manifest["accounting"]["manifest_cpu_cap_s"]:
        raise CallRefused("the grant's CPU cap exceeds the manifest's binding cap")
    # 3. Prechecks that only read files: geometry, a fresh directory, identity, build provenance, the CI entry guard.
    pinned = gate_zero.reference(call["reference"])
    try:  # the pinned raw layout, judged by the continuous rules only (never the search lattice)
        spec = slab049.reference_spec(pinned.id)
    except slab049.ReferenceGeometryError as exc:
        raise CallRefused(f"{call_id}: {exc}") from exc
    out = Path(out)
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
        # 4. THE ADMISSION: balance, admission tag and signed reservation in one critical section for the grant.
        envelopes = {c["id"]: float(c["accounting"]["reserved_cpu_s"]) for c in manifest["calls"]}
        try:
            reservation = gate0_anchor.admit_and_reserve(
                root, key, public_hex, manifest_sha256, call_id,
                {"out": out.resolve().as_posix(), "reserved_cpu_s": envelopes[call_id]}, request=anchor_request,
                envelopes=envelopes, not_after_utc=manifest["grant_window"]["not_after_utc"], now=now)
        except gate0_anchor.AdmissionUncertain as exc:
            raise CallRefused(f"{call_id}: {exc}; if its admission tag exists the call is consumed and charged, and "
                              "the operator reconciles it") from exc
        except (gate0_anchor.AdmissionRefused, AuthenticationError, AnchorUnavailable, OSError) as exc:
            raise CallRefused(f"{call_id}: not admitted: {type(exc).__name__}: {exc}") from exc
        context = {"call": call, "pinned": pinned, "spec": spec, "out": out, "root": root, "key": key,
                   "public_hex": public_hex, "grant": grant, "manifest_sha256": manifest_sha256,
                   "anchor_request": anchor_request, "executable": executable, "source": source,
                   "identity": identity, "build": build, "reservation": reservation, "baseline": baseline,
                   "started": started, "clock": clock, "now": now}
        return _run_call(context)
    finally:
        shutil.rmtree(private, ignore_errors=True)


def _sign_receipt(context: dict, receipt: dict) -> bytes:
    return _json(gate0_anchor.sign(context["key"], {k: v for k, v in receipt.items() if k != "signature"}))


def _run_call(context: dict) -> dict:
    """Steps 5-10 of an admitted call. Every exit settles (_settle), consumed and charged from step 0."""
    call, pinned, out = context["call"], context["pinned"], context["out"]
    timeout = float(call["timeout_s"])
    argv = slab049.tap_argv(str(context["executable"]), call["grid"])
    reservation = context["reservation"]
    receipt = {
        "schema": gate_zero.RECEIPT_SCHEMA, "call": call["id"], "role": call["role"], "replay_of": call["replay_of"],
        "manifest_sha256": context["manifest_sha256"], "grant_id": context["grant"]["grant_id"],
        "evaluator": context["identity"], "reference": pinned.id, "role_in_gate": pinned.role,
        "layout_identity": pinned.layout_identity, "raw_layout_sha256": pinned.raw_layout_sha256,
        "paper_c": pinned.paper_c, "grid": call["grid"], "argv": argv,
        "binary": {"source": context["source"].as_posix(), "executed": "a private content-addressed copy (0500 in a "
                   "0700 directory), removed after the call"},
        "build_provenance": {"path": context["build"]["path"], "sha256": context["build"]["sha256"]},
        "runtime": None, "geometry": context["spec"]["geometry"],
        "temperature_label": gate_zero.TEMPERATURE_LABELS[call["kind"]], "timeout_s": timeout,
        "cpu_limit_s": call["cpu_limit_s"], "solver_environment": SOLVER_ENVIRONMENT,
        "host": {"architecture": platform.machine(), "node": platform.node(), "python": sys.version.split()[0]},
        "reservation_sha256": gate0_anchor.digest(reservation), "admission": reservation["admission"],
        "cpu_baseline": context["baseline"],
        "reserved_utc": (context["now"] or _now()).isoformat(), "status": "reserved",
    }
    phase = "setup"
    try:
        # 5. Setup.
        out.mkdir(parents=True, exist_ok=True)
        _write_durably(out / "receipt.json", _sign_receipt(context, receipt))
        if reservation["admission"].get("late"):  # admitted after the cutoff: consumed and charged, nothing runs
            receipt["status"], receipt["exit_status"] = "window_closed", None
            receipt["error"] = (f"the admission tag's create returned at {reservation['admission']['created_utc']}, "
                                "after the window closed: the call stays consumed and charged, and nothing runs")
            return receipt
        # 6. The process-capable precheck, inside the attempt.
        phase = "precheck"
        receipt["runtime"] = provenance.resolved_libraries(context["executable"])
        if (provenance.library_identity(receipt["runtime"])
                != provenance.library_identity(context["build"]["provenance"]["libraries"])):
            receipt["status"], receipt["exit_status"] = "runtime_refused", None
            receipt["error"] = ("the shared libraries the loader resolves differ from the build's: refused before "
                                "staging; the call stays consumed and charged")
            return receipt
        # 7. Staging.
        phase = "stage"
        receipt["inputs"] = stage(pinned, context["spec"], out)
        receipt["config_sha256"] = receipt["inputs"]["new_hotspot.config"]
        _write_durably(out / "receipt.json", _sign_receipt(context, receipt))
        # 8. THE CLAIM: create the launch tag; only a successful create may launch.
        phase = "claim"
        claim = gate0_anchor.claim_launch(context["anchor_request"], context["grant"]["grant_id"],
                                          context["manifest_sha256"], call["id"],
                                          reservation_sha256=receipt["reservation_sha256"])
        receipt["claim"] = {"ref": claim["ref"], "commit_sha": claim["commit_sha"]}
        # 9. The launch.
        phase = "launch"
        solver_before = _children_cpu_s()
        with (out / "stdout.txt").open("wb") as stdout, (out / "stderr.txt").open("wb") as stderr:
            process = subprocess.Popen(argv, cwd=out, stdout=stdout, stderr=stderr, env=SOLVER_ENVIRONMENT,
                                       start_new_session=True, **provenance.cpu_limited(call["cpu_limit_s"]))
            phase = "solve"
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
        receipt["runtime_after"] = provenance.resolved_libraries(context["executable"])
        if provenance.library_identity(receipt["runtime_after"]) != provenance.library_identity(receipt["runtime"]):
            receipt["status"] = "runtime_changed"
    except ClaimRefused as exc:  # another request holds the launch, or no reserve tag binds the call: no launch
        receipt["status"], receipt["exit_status"], receipt["error"] = "claim_refused", None, str(exc)
    except ClaimUncertain as exc:  # consumed, never launched: the operator reconciles it with a failure settle tag
        receipt["status"], receipt["exit_status"], receipt["error"] = "claim_uncertain", None, str(exc)
    except (AnchorUnavailable, AuthenticationError) as exc:  # the claim could not be made: no launch
        receipt["status"], receipt["exit_status"] = "claim_unavailable", None
        receipt["error"] = f"{type(exc).__name__}: {exc}"
    except subprocess.TimeoutExpired:  # only the TAP generator can raise it here
        receipt["status"], receipt["exit_status"] = "stage_error", None
        receipt["error"] = "the TAP generator passed its wall deadline"
    except OSError as exc:
        receipt["status"] = {"setup": "setup_error", "precheck": "precheck_error", "stage": "stage_error",
                             "launch": "launch_error"}.get(phase, "error")
        receipt["exit_status"], receipt["error"] = None, repr(exc)
    except BaseException as exc:  # settle the receipt, then let the caller see the failure
        receipt["status"] = {"setup": "setup_error", "precheck": "precheck_error", "stage": "stage_error"}.get(
            phase, "error")
        receipt["exit_status"], receipt["error"] = None, f"{type(exc).__name__}: {exc}"
        raise
    finally:
        _settle(context, receipt)
    return receipt


def _settle(context: dict, receipt: dict) -> None:
    """Durable settlement on every exit path after the admission: the signed receipt when it can be written, then
    always the signed settlement entry. The CPU charged is everything since the invocation's accounting started
    (step 0): the prechecks, the loader listings, the generator, the solver and the parent's own work. A call whose
    receipt cannot be written still settles, with a null receipt digest; it stays consumed and charged, and is never
    retried."""
    call, out, baseline = context["call"], context["out"], context["baseline"]
    receipt["started_utc"], receipt["finished_utc"] = context["started"].isoformat(), _now().isoformat()
    receipt["wall_s"] = time.perf_counter() - context["clock"]
    try:
        receipt["outputs"] = {name: _sha256(out / name) for name in gate_zero.RECEIPT_OUTPUTS
                              if (out / name).is_file()}
    except OSError as exc:
        receipt["outputs"], receipt["outputs_error"] = {}, repr(exc)
    if receipt["status"] == "exited" and receipt["exit_status"] == 0:
        try:
            receipt["solve_record"] = slab049.summarize_evaluation(
                out, grid_size=call["grid"], grid_format=gate_zero.GRID_FORMATS[call["kind"]])
        except Exception as exc:  # the raw outputs stay; the receipt says why the record failed
            receipt["status"], receipt["error"] = "record_error", f"{type(exc).__name__}: {exc}"
    receipt["children_cpu_s"] = _children_cpu_s() - baseline["children_s"]
    receipt["self_cpu_s"] = _self_cpu_s() - baseline["self_s"]
    receipt["charged_cpu_s"] = receipt["children_cpu_s"] + receipt["self_cpu_s"]
    receipt["overshoot_cpu_s"] = max(0.0, receipt["charged_cpu_s"] - call["accounting"]["reserved_cpu_s"])
    receipt_sha256 = None
    try:
        _write_durably(out / "receipt.json", _sign_receipt(context, receipt))
        receipt_sha256 = _sha256(out / "receipt.json")
    except OSError as exc:  # nowhere to write it: the ledger still records the terminal failure
        receipt["receipt_error"] = repr(exc)
    payload = {key: receipt.get(key) for key in ("status", "exit_status", "started_utc", "finished_utc", "wall_s",
                                                 "solver_cpu_s", "children_cpu_s", "self_cpu_s", "charged_cpu_s",
                                                 "overshoot_cpu_s", "outputs", "error", "receipt_error", "claim")}
    payload.update({"reserved_cpu_s": call["accounting"]["reserved_cpu_s"], "out": out.resolve().as_posix(),
                    "receipt_sha256": receipt_sha256, "cpu_baseline": baseline})
    gate0_anchor.append(context["root"], context["key"], context["public_hex"], context["manifest_sha256"],
                        "settlement", call["id"], payload)
    receipt["settle_tag_message"] = gate0_anchor.tag_message(
        "settle", context["grant"]["grant_id"], context["manifest_sha256"], call["id"], status=receipt["status"],
        receipt_sha256=receipt_sha256, outputs=receipt["outputs"], charged_cpu_s=receipt["charged_cpu_s"])


def report(*, ledger_root: Path | None = None, tags: gate0_anchor.TagReader | None = None,
           manifest_path: Path | None = None) -> dict:
    """From the authenticated ledger and the operator's tags, by admitted call id, with no extra call (reads only).

    A call is usable only after gate_zero.verify_call binds it (signed ledger and receipt, the operator's reserve,
    launch and settle tags, outputs, frozen inputs) and its raw files pass the strict evaluator-bound reader; its
    diagnostics are derived from those raw files, never read from a stored solve record. Every other call is in
    not_completed with the reason. From the usable calls:

    - HotSpot 6.0's (and the comparator's) grid 32 -> 64 change per reference, on the block-centre metric and the
      grid peak;
    - CPU seconds per call;
    - whether each replay's outputs are byte-identical to its primary's;
    - the same-index spreader-sink drop and the same-index stack at the active argmax (reported, not asserted).
    """
    manifest, manifest_sha256 = load_manifest(manifest_path)  # the pinned operator key comes from the tree's manifest
    root, tags = gate0_anchor.configured(manifest, ledger_root=ledger_root, tags=tags)
    ledger = gate0_anchor.read_ledger(root, manifest["operator"]["public_key_ed25519"], manifest_sha256)
    entries, not_completed = {}, []
    for call in manifest["calls"]:
        entry = {"call": call["id"], "kind": call["kind"], "reference": call["reference"], "grid": call["grid"],
                 "role": call["role"], "replay_of": call["replay_of"], "gating": call["gating"], "usable": False}
        try:
            verified = gate_zero.verify_call(call, ledger, tags, manifest, manifest_sha256)
        except (gate_zero.GateZeroRefusal, AuthenticationError, AnchorUnavailable, KeyError, TypeError,
                ValueError) as exc:  # a malformed signed entry is unusable too
            entry["reason"] = f"{type(exc).__name__}: {exc}"
            not_completed.append({"call": call["id"], "reason": entry["reason"]})
            entries[call["id"]] = entry
            continue
        evidence, record = verified["evidence"], verified["evidence"]["record"]
        entry.update({"usable": True, "settled": verified["settlement"]["status"],
                      "charged_cpu_s": verified["settlement"].get("charged_cpu_s"),
                      "solver_cpu_s": verified["settlement"].get("solver_cpu_s"),
                      "selector_c": evidence["simulated_c"], "grid_peak_c": record["active_layer_grid_peak"]["peak_C"],
                      "outputs": evidence["output_sha256"], "drop": record["spreader_sink_drop_diagnostic"],
                      "stack": record["same_index_stack_at_active_argmax"]})
        entries[call["id"]] = entry
    rows = []
    for kind in sorted({c["kind"] for c in manifest["calls"]}):
        for reference in sorted({c["reference"] for c in manifest["calls"]}):
            g64 = entries.get(gate_zero.call_id("primary", kind, reference, 64), {})
            g32 = entries.get(gate_zero.call_id("primary", kind, reference, 32), {})
            replay = entries.get(gate_zero.call_id("replay", kind, reference, 64), {})
            both = g64.get("usable") and g32.get("usable")
            fixture = reference.split("-")[0]
            rows.append({
                "kind": kind, "reference": reference, "temperature_label": gate_zero.TEMPERATURE_LABELS[kind],
                "block_centre_c": {"64": g64.get("selector_c"), "32": g32.get("selector_c"),
                                   "64 replay": replay.get("selector_c")},
                "grid32_to_64_block_centre_delta_k": g64["selector_c"] - g32["selector_c"] if both else None,
                "grid32_to_64_grid_peak_delta_k": g64["grid_peak_c"] - g32["grid_peak_c"] if both else None,
                "network_model_prediction_k": NETWORK_MODEL_MESH_DELTA_K.get(fixture) if kind == "hotspot6" else None,
                "old_hotspot7_mesh_error_k": OLD_HOTSPOT7_MESH_ERROR_K.get(fixture),
                "replay_byte_identical": (all(g64["outputs"][name] == replay["outputs"][name]
                                              for name in gate_zero.REPLAY_OUTPUTS)
                                          if g64.get("usable") and replay.get("usable") else None),
                "spreader_sink_drop_g64": g64.get("drop"), "same_index_stack_g64": g64.get("stack"),
            })
    return {"schema": "sentilab-slab049-manifest-report-v4", "manifest_sha256": manifest_sha256,
            "grant_id": ledger["grant"]["grant_id"], "calls": list(entries.values()), "rows": rows,
            "not_completed": not_completed,
            "note": "nothing here is frozen as a mesh error; the next protocol sets its own"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("validate-reference")
    record = sub.add_parser("record")
    summary = sub.add_parser("report")
    run.add_argument("--call", required=True)
    run.add_argument("--timeout", type=float, required=True, help="the call's listed timeout, in seconds")
    run.add_argument("--operator-key", type=Path,
                     help=f"the operator's Ed25519 key file (default: ${OPERATOR_SIGNER_ENV})")
    run.add_argument("--binary", type=Path)
    run.add_argument("--kind")
    run.add_argument("--reference")
    run.add_argument("--grid", type=int)
    record.add_argument("--kind", required=True, choices=sorted(gate_zero.EVALUATOR_KINDS))
    record.add_argument("--binary", type=Path)
    for command in (run, record, summary):
        command.add_argument("--ledger-root", type=Path,
                             help="the operator's ledger root (default: $SLAB049_LEDGER_ROOT)")
        command.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "report":
        args.out.write_text(json.dumps(report(ledger_root=args.ledger_root), indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
        return 0
    if args.command == "validate-reference":
        try:
            receipt = validate_call(args.call, args.out, timeout_s=args.timeout, ledger_root=args.ledger_root,
                                    operator_key_path=args.operator_key, binary=args.binary, kind=args.kind,
                                    reference=args.reference, grid=args.grid)
        except CallRefused as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return 2
        print(json.dumps({k: receipt.get(k) for k in ("call", "status", "exit_status", "wall_s", "charged_cpu_s",
                                                      "settle_tag_message")}))
        return 0 if receipt["status"] == "exited" and receipt["exit_status"] == 0 else 1
    binary = args.binary or REPO_ROOT / gate_zero.EVALUATOR_KINDS[args.kind]["binary"]
    result = gate_zero.build_record(args.kind, binary, ledger_root=args.ledger_root)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(result["verdict"])
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
