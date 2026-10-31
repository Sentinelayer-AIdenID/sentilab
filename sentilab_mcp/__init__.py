"""MCP tool handlers; the host injects the same Context used by the CLI."""
import asyncio
import json
import os
import sys


RESULTCHECK_TIMEOUT = 10


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
