"""Local-PC GB10 status/checkpoint backend; serve lifecycle remains staged/open."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time

from . import gb10_readonly as readonly


SCHEMA = "sentilab-gb10-backend/1"
MAX_SCRIPT_BYTES = 32768
MAX_OUTPUT_BYTES = 16384
SSH_TIMEOUT_SECONDS = 20
EXPECTED_IDENTITY = {"hostname": "promaxgb10-9a1e", "architecture": "aarch64", "login": "dell"}


class ProbeError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _capture(argv, source):
    """Bound all three pipes without capture_output's unbounded accumulation."""
    if len(source) > MAX_SCRIPT_BYTES:
        raise ProbeError("probe_source_oversize")
    try:
        process = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            shell=False, bufsize=0,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except OSError:
        raise ProbeError("ssh_unavailable") from None
    output, diagnostic = bytearray(), bytearray()
    overflow = threading.Event()
    pipe_failure = threading.Event()

    def consume(stream, destination):
        try:
            while chunk := stream.read(min(4096, MAX_OUTPUT_BYTES + 1 - len(destination))):
                destination.extend(chunk)
                if len(destination) > MAX_OUTPUT_BYTES:
                    overflow.set()
                    return
        except (OSError, ValueError):
            pipe_failure.set()

    def provide():
        try:
            # Unbuffered FileIO.write may be partial, especially with fake peers.
            remaining = memoryview(source)
            while remaining:
                count = process.stdin.write(remaining)
                if not count:
                    raise OSError()
                remaining = remaining[count:]
        except (OSError, ValueError):
            pipe_failure.set()
        finally:
            try:
                process.stdin.close()
            except OSError:
                pipe_failure.set()

    threads = [threading.Thread(target=consume, args=(process.stdout, output), daemon=True),
               threading.Thread(target=consume, args=(process.stderr, diagnostic), daemon=True),
               threading.Thread(target=provide, daemon=True)]
    deadline = time.monotonic() + SSH_TIMEOUT_SECONDS
    try:
        for thread in threads:
            thread.start()
        while True:
            if overflow.is_set():
                raise ProbeError("ssh_output_oversize")
            if time.monotonic() >= deadline:
                raise ProbeError("ssh_timeout")
            if process.poll() is not None and not any(thread.is_alive() for thread in threads):
                break
            time.sleep(0.01)
        if process.returncode != 0:
            raise ProbeError("ssh_failed")
        if pipe_failure.is_set():
            raise ProbeError("ssh_io_error")
        return bytes(output)
    finally:
        if process.poll() is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
        for stream in (process.stdin, process.stdout, process.stderr):
            try:
                stream.close()
            except OSError:
                pass
        for thread in threads:
            thread.join(timeout=0.1)


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


def _constant(_):
    raise ValueError()


def _parse(raw, operation):
    try:
        if len(raw) > MAX_OUTPUT_BYTES:
            raise ValueError()
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_object,
                          parse_constant=_constant)
        payload = "device" if operation == "status" else "artifacts"
        if not isinstance(data, dict) or set(data) != {"schema", "operation", "identity", payload}:
            raise ValueError()
        if data["schema"] != readonly.PROBE_SCHEMA or data["operation"] != operation:
            raise ValueError()
        if data["identity"] != EXPECTED_IDENTITY:
            raise ProbeError("device_identity_mismatch")
        if operation == "status":
            device = data["device"]
            if not isinstance(device, dict) or set(device) != {"python", "driver", "gpu_model", "memory_bytes"}:
                raise ValueError()
            if not isinstance(device["python"], str) or not re.fullmatch(r"[0-9]{1,2}\.[0-9]{1,2}\.[0-9]{1,3}", device["python"]):
                raise ValueError()
            if device["driver"] is not None and (not isinstance(device["driver"], str) or not re.fullmatch(r"[0-9]{3}\.[0-9]{1,3}\.[0-9]{1,3}", device["driver"])):
                raise ValueError()
            if device["gpu_model"] not in (None, "NVIDIA GB10"):
                raise ValueError()
            if type(device["memory_bytes"]) is not int or not 0 < device["memory_bytes"] < 2**60:
                raise ValueError()
        else:
            _validate_artifacts(data["artifacts"])
        return data
    except ProbeError:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise ProbeError("invalid_probe_response") from None


def _validate_artifacts(artifacts):
    if not isinstance(artifacts, list) or len(artifacts) != len(readonly.ARTIFACTS):
        raise ValueError()
    for observed, (name, size, digest) in zip(artifacts, readonly.ARTIFACTS):
        if not isinstance(observed, dict) or set(observed) != {"name", "status", "bytes", "sha256"}:
            raise ValueError()
        if observed["name"] != name or observed["status"] not in readonly.FILE_STATUSES:
            raise ValueError()
        count, actual = observed["bytes"], observed["sha256"]
        if count is not None and (type(count) is not int or not 0 <= count < 2**63):
            raise ValueError()
        if actual is not None and (not isinstance(actual, str) or not re.fullmatch(r"[0-9a-f]{64}", actual)):
            raise ValueError()
        if observed["status"] == "verified" and (count != size or actual != digest):
            raise ValueError()
        if observed["status"] == "hash_mismatch" and (count != size or actual is None or actual == digest):
            raise ValueError()
        if observed["status"] == "size_mismatch" and (count is None or count == size):
            raise ValueError()


def _remote(operation):
    if operation not in {"status", "checkpoint"}:
        raise ProbeError("invalid_input")
    with Path(readonly.__file__).open("rb") as handle:
        source = handle.read(MAX_SCRIPT_BYTES + 1)
    argv = ["ssh", "-T", "-a", "-x", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "ConnectTimeout=5", "-o", "ConnectionAttempts=1", "-o", "ClearAllForwardings=yes",
            "-o", "PermitLocalCommand=no", "-o", "RemoteCommand=none", "-o", "ControlMaster=no",
            "-o", "ControlPath=none", "-o", "LogLevel=ERROR", "gb10",
            "python3 -I -S -B - " + operation]
    return _parse(_capture(argv, source), operation)


def _result(operation, *, ok, status, **details):
    return {"schema": SCHEMA, "operation": operation, "ok": ok, "status": status,
            "checked_at": datetime.now(timezone.utc).isoformat(), "scope_state": "staged_open", **details}


def execute(operation, context=None, **arguments):
    """The shared registration owner exposes only these operation arguments.

    Context is deliberately unused, reserved for host configuration. Caller data
    cannot change the alias, paths, executable, source, pins or admission policy.
    """
    allowed = {"status": set(), "checkpoint_verify": {"location"}, "serve": {"action"}}
    if not isinstance(operation, str) or operation not in allowed or not set(arguments) <= allowed[operation]:
        return _result("invalid", ok=False, status="refused", error={"code": "invalid_input"})
    try:
        if operation == "serve":
            action = arguments.get("action", "status")
            if not isinstance(action, str) or action not in {"status", "start", "stop"}:
                raise ProbeError("invalid_input")
            code = {"status": "prospective_gpu_grant_pending", "start": "gpu_grant_required",
                    "stop": "no_managed_serve_session"}[action]
            return _result(operation, ok=False, status="pending" if action == "status" else "refused",
                           action=action, error={"code": code}, launched=False,
                           managed_session=None, live_service_state="not_observed")
        if operation == "status":
            observed = _remote("status")
            return _result(operation, ok=True, status="observed", ssh_alias="gb10",
                           identity=observed["identity"], device=observed["device"],
                           gpu_readiness="not_tested", serve_state="not_observed")
        location = arguments.get("location", "both")
        if not isinstance(location, str) or location not in {"gb10", "pc", "both"}:
            raise ProbeError("invalid_input")
        locations = {}
        if location in {"pc", "both"}:
            locations["pc"] = {"artifacts": readonly.checkpoint(readonly.PC_ROOT)}
        if location in {"gb10", "both"}:
            try:
                observed = _remote("checkpoint")
                locations["gb10"] = {"artifacts": observed["artifacts"], "identity": observed["identity"]}
            except (ProbeError, OSError) as exc:
                locations["gb10"] = {"error": {"code": exc.code if isinstance(exc, ProbeError) else "probe_unavailable"}}
        passed = all("artifacts" in value and all(item["status"] == "verified" for item in value["artifacts"])
                     for value in locations.values())
        return _result(operation, ok=passed, status="verified" if passed else "unverified",
                       locations=locations, checkpoint="SLAB-018/attempt-01",
                       claim="retained_file_integrity_only", held_out_evaluation=False,
                       serve_state="not_observed")
    except (ProbeError, OSError) as exc:
        return _result(operation, ok=False,
                       status="refused" if isinstance(exc, ProbeError) and exc.code == "invalid_input" else "unavailable",
                       error={"code": exc.code if isinstance(exc, ProbeError) else "probe_unavailable"})
