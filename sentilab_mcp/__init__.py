"""MCP tool handlers; the host injects the same Context used by the CLI."""
import asyncio
import json
import os
import sys


RESULTCHECK_TIMEOUT = 10
EXPORT_TIMEOUT_SECONDS = 30


async def sentilab_live_run(context, **arguments):
    from sentilab_core import operations
    return await operations.run(context, **arguments)


def sentilab_live_status(context, **arguments):
    from sentilab_core import operations
    return operations.status(context, **arguments)


def sentilab_live_stop(context, **arguments):
    from sentilab_core import operations
    return operations.stop(context, **arguments)


def sentilab_live_verify(context, **arguments):
    from sentilab_core import operations
    return operations.verify(context, **arguments)


async def sentilab_dataset_export(context, **arguments):
    # A thread waiting on flock cannot be cancelled. Reap the worker before
    # acknowledging cancellation/timeout so it cannot publish after that reply.
    payload = json.dumps({'root': str(context.root),
                          'public_keys': {key: value.hex() for key, value in context.public_keys.items()},
                          'arguments': arguments}, allow_nan=False).encode()
    spawn = asyncio.create_task(asyncio.create_subprocess_exec(
        sys.executable, '-m', 'sentilab_mcp.export_worker', stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL))
    process = None
    try:
        async with asyncio.timeout(EXPORT_TIMEOUT_SECONDS):
            process = await asyncio.shield(spawn)
            stdout, _ = await process.communicate(payload)
            if process.returncode:
                raise ValueError('dataset export worker failed')
            return json.loads(stdout)
    finally:
        # Shield spawning as well: a cancellation during subprocess creation
        # must not leave a child outside this task's cleanup.
        if process is None:
            process = await spawn
        if process.returncode is None:
            process.kill()
        await process.wait()


TOOLS = {"sentilab_live_" + name: globals()["sentilab_live_" + name] for name in ("run", "status", "stop", "verify")}


async def sentilab_resultcheck(context=None, *, file):
    """Run the shared CLI/core in a worker we can kill and reap on cancellation."""
    if not isinstance(file, str):
        raise ValueError("file must be a local path string")
    root = os.environ.get("SENTILAB_RESULTCHECK_DIR")
    if not root:
        raise OSError("ResultCheck directory is not configured")
    creation = asyncio.create_task(asyncio.create_subprocess_exec(
        sys.executable, "-m", "sentilab_cli", "resultcheck", "--root", root, "--", file,
        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL))

    async def cleanup():
        # Own the child even if cancellation arrives during process creation.
        process = await creation
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        # Drain stdout as well: wait() can deadlock after killing a child whose
        # output filled the pipe before communicate() began.
        await process.communicate()

    try:
        async with asyncio.timeout(RESULTCHECK_TIMEOUT):
            process = await asyncio.shield(creation)
            output, _ = await process.communicate()
        if process.returncode not in (0, 1, 2):
            raise OSError("ResultCheck worker failed")
        receipt = json.loads(output)
        if "error" in receipt:
            raise OSError("ResultCheck file unreadable")
        return receipt
    finally:
        closing = asyncio.create_task(cleanup())
        cancelled = False
        while not closing.done():
            try:
                await asyncio.shield(closing)
            except asyncio.CancelledError:
                cancelled = True
        closing.result()
        if cancelled:
            raise asyncio.CancelledError


TOOLS["sentilab_resultcheck"] = sentilab_resultcheck
TOOLS["sentilab_dataset_export"] = sentilab_dataset_export
