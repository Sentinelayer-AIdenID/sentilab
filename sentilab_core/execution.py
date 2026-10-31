"""Shared transport admission and cancellable calls to existing lane code.

Scopes come from the host environment, never request arguments. An unset policy
retains the local-operator CLI/stdio trust boundary; an explicit empty list denies
all capabilities. Workers receive public verification pins, never a signer.
"""
import asyncio
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

from .capabilities import CAPABILITIES, for_tool


def authorize(tool):
    """Apply the host grant even to lanes with their own input/error contract."""
    row = for_tool(tool)
    configured = os.environ.get("SENTILAB_CAPABILITY_SCOPES")
    if configured is not None:
        try:
            scopes = json.loads(configured)
            known = {entry.name for entry in CAPABILITIES}
            if (not isinstance(scopes, list) or any(not isinstance(s, str) or s not in known for s in scopes)
                    or row.name not in scopes):
                raise ValueError
        except (TypeError, ValueError):
            raise PermissionError("capability scope refused") from None


def authorize_session(tool, context):
    """A host-bound proposer transport cannot read the operator's other lanes."""
    if (getattr(context, "proposal_session", None) is not None
            and tool not in {"sentilab_proposal_context", "sentilab_proposal_submit"}):
        raise PermissionError("capability scope refused")


def admit(tool, arguments):
    from jsonschema import Draft202012Validator

    authorize(tool)
    row = for_tool(tool)
    if not Draft202012Validator(row.input_schema).is_valid(arguments):
        raise ValueError("invalid capability input")


async def _ready(fd, *, writing=False):
    """Wait for pipe I/O or pidfd exit notification without reaping a child."""
    loop = asyncio.get_running_loop()
    ready = loop.create_future()

    def notify():
        if not ready.done():
            ready.set_result(None)

    add = loop.add_writer if writing else loop.add_reader
    remove = loop.remove_writer if writing else loop.remove_reader
    add(fd, notify)
    try:
        await ready
    finally:
        remove(fd)


def _process_record(pid):
    try:
        # comm can contain spaces and ')'; fields after its final ')' are fixed.
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return (pid, int(fields[19])), int(fields[2]), fields[0]
    except (FileNotFoundError, ProcessLookupError):
        return None


class _WorkerJob:
    """Own the leader's waitpid until its entire process group has exited.

    asyncio subprocess watchers eagerly reap, so they cannot reserve the group.
    Popen plus non-reaping pipe/pidfd I/O keeps even an exited leader reserved.
    A pidfd closes the stat-to-signal PID reuse race for every discovered member.
    """

    def __init__(self, environment):
        self.process = subprocess.Popen(
            [sys.executable, "-m", "sentilab_core.execution"],
            cwd=Path(__file__).resolve().parents[1], env=environment,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            start_new_session=True, bufsize=0)
        self.members = {}
        try:
            self.leader = _process_record(self.process.pid)[0]
            self._pin(self.leader)
        except BaseException:
            # No request has been written, so the worker cannot dispatch a
            # capability. EOF releases it even if pidfd setup is unavailable.
            self.process.stdin.close()
            self.process.stdout.close()
            self.process.wait()
            raise

    def _pin(self, identity):
        if identity in self.members:
            return
        try:
            fd = os.pidfd_open(identity[0])
        except ProcessLookupError:
            return
        record = _process_record(identity[0])
        if record is None or record[0] != identity or record[1] != self.leader[0]:
            os.close(fd)
        else:
            self.members[identity] = fd

    def _scan(self):
        leader = _process_record(self.leader[0])
        if leader is None or leader[0] != self.leader:
            raise RuntimeError("worker ownership lost before cleanup")
        records = []
        for path in Path("/proc").iterdir():
            if path.name.isdecimal():
                record = _process_record(int(path.name))
                if record is not None and record[1] == self.leader[0]:
                    records.append(record)
        # Fail closed even if an external reaper violated our ownership contract.
        current = _process_record(self.leader[0])
        if current is None or current[0] != self.leader:
            raise RuntimeError("worker ownership lost during cleanup")
        return records

    def _signal(self, identity, signum):
        record = _process_record(identity[0])
        if record is not None and record[0] == identity:
            try:
                signal.pidfd_send_signal(self.members[identity], signum)
            except ProcessLookupError:
                pass

    async def communicate(self, payload):
        process = self.process
        os.set_blocking(process.stdin.fileno(), False)
        os.set_blocking(process.stdout.fileno(), False)
        remaining = memoryview(payload)
        try:
            while remaining:
                try:
                    remaining = remaining[os.write(process.stdin.fileno(), remaining):]
                except BlockingIOError:
                    await _ready(process.stdin.fileno(), writing=True)
        except BrokenPipeError:
            pass
        finally:
            process.stdin.close()
        chunks = []
        while True:
            try:
                chunk = os.read(process.stdout.fileno(), 65536)
            except BlockingIOError:
                await _ready(process.stdout.fileno())
                continue
            if not chunk:
                break
            chunks.append(chunk)
        await _ready(self.members[self.leader])
        return b"".join(chunks)

    async def cleanup(self):
        try:
            # Freeze to a fixed point before killing: a running member can fork
            # after a scan. Once every member is stopped or exited it cannot.
            while True:
                records = self._scan()
                for identity, _, state in records:
                    self._pin(identity)
                    if identity in self.members and state not in {"T", "t", "Z", "X"}:
                        self._signal(identity, signal.SIGSTOP)
                if all(state in {"T", "t", "Z", "X"} for _, _, state in records):
                    break
                await asyncio.sleep(0.001)
            for identity in self.members:
                self._signal(identity, signal.SIGKILL)
            await asyncio.gather(*(_ready(fd) for fd in self.members.values()))
            # This is the only reap. The group cannot be recycled before here.
            self.process.wait()
        finally:
            self.process.stdin.close()
            self.process.stdout.close()
            for fd in self.members.values():
                os.close(fd)


async def _finish(task):
    """Drain owned cleanup even when cancellation is repeated."""
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    return task.result(), cancelled


async def recorded_call(context, capability, arguments, *, timeout=30):
    payload = json.dumps({"root": str(context.root), "capability": capability,
                          "public_keys": {key: value.hex() for key, value in context.public_keys.items()},
                          "memory_tenant": context.memory_tenant,
                          "held_out_families": context.held_out_families,
                          "routing_fixture": str(context.routing_fixture) if context.routing_fixture else None,
                          "arguments": arguments}, allow_nan=False).encode()
    environment = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "TMPDIR") if key in os.environ}
    environment.update(OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
    job = None
    try:
        async with asyncio.timeout(timeout):
            job = _WorkerJob(environment)
            stdout = await job.communicate(payload)
    finally:
        if job is not None:
            _, cancelled = await _finish(asyncio.create_task(job.cleanup()))
            if cancelled:
                raise asyncio.CancelledError
    if job.process.returncode:
        raise ValueError("recorded capability failed")
    result = json.loads(stdout)
    if "worker_error" in result:
        raise ValueError("recorded capability refused")
    return result["result"]


def main():
    from .operations import Context

    request = json.load(sys.stdin)
    context = Context(Path(request["root"]), {key: bytes.fromhex(value)
                      for key, value in request["public_keys"].items()},
                      memory_tenant=request["memory_tenant"], held_out_families=request["held_out_families"],
                      routing_fixture=Path(request["routing_fixture"]) if request["routing_fixture"] else None)
    namespace, command = request["capability"].split(".")
    try:
        if namespace == "live":
            from . import operations
            if command not in {"status", "stop", "verify"}:
                raise ValueError("unsupported recorded operation")
            result = getattr(operations, command)(context, **request["arguments"])
        elif namespace == "dataset" and command == "export":
            from .dataset import export
            result = export(context.root, public_keys=context.public_keys, **request["arguments"])
        elif namespace == "chiplet":
            from . import chiplet
            if command not in {"build", "render", "replay", "export"}:
                raise ValueError("unsupported chiplet operation")
            result = getattr(chiplet, command)(context, **request["arguments"])
        elif namespace == "gb10" and command in {"status", "checkpoint_verify"}:
            from .gb10_backend import execute
            result = execute(command, context, **request["arguments"])
        elif namespace == "memory" and command in {"recall", "audit", "route"}:
            from sentilab_mcp import TOOLS
            tool = "sentilab_route" if command == "route" else "sentilab_memory_" + command
            result = TOOLS[tool](context, **request["arguments"])
        else:
            raise ValueError("unsupported recorded namespace")
        print(json.dumps({"result": result}, allow_nan=False))
    except (ValueError, TypeError, KeyError, OSError):
        print(json.dumps({"worker_error": "ValueError"}))


if __name__ == "__main__":
    main()
