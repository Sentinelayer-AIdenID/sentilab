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
import sys

from .capabilities import CAPABILITIES, for_tool


def admit(tool, arguments):
    from jsonschema import Draft202012Validator

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
    if not Draft202012Validator(row.input_schema).is_valid(arguments):
        raise ValueError("invalid capability input")


async def recorded_call(context, capability, arguments, *, timeout=30):
    payload = json.dumps({"root": str(context.root), "capability": capability,
                          "public_keys": {key: value.hex() for key, value in context.public_keys.items()},
                          "arguments": arguments}, allow_nan=False).encode()
    environment = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "TMPDIR") if key in os.environ}
    environment.update(OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
    spawn = asyncio.create_task(asyncio.create_subprocess_exec(
        sys.executable, "-m", "sentilab_core.execution", cwd=Path(__file__).resolve().parents[1],
        env=environment, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL, start_new_session=True))
    process = None
    try:
        async with asyncio.timeout(timeout):
            process = await asyncio.shield(spawn)
            stdout, _ = await process.communicate(payload)
            if process.returncode:
                raise ValueError("recorded capability failed")
            result = json.loads(stdout)
            if "worker_error" in result:
                raise ValueError("recorded capability refused")
            return result["result"]
    finally:
        if process is None:
            process = await spawn
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.wait()


def main():
    from .operations import Context

    request = json.load(sys.stdin)
    context = Context(Path(request["root"]), {key: bytes.fromhex(value)
                      for key, value in request["public_keys"].items()})
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
        else:
            raise ValueError("unsupported recorded namespace")
        print(json.dumps({"result": result}, allow_nan=False))
    except (ValueError, TypeError, KeyError, OSError):
        print(json.dumps({"worker_error": "ValueError"}))


if __name__ == "__main__":
    main()
