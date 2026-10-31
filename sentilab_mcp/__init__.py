"""MCP tool handlers; the host injects the same Context used by the CLI."""
import asyncio
import json
import sys

from sentilab_core import operations


EXPORT_TIMEOUT_SECONDS = 30


async def sentilab_live_run(context, **arguments):
    return await operations.run(context, **arguments)


def sentilab_live_status(context, **arguments):
    return operations.status(context, **arguments)


def sentilab_live_stop(context, **arguments):
    return operations.stop(context, **arguments)


def sentilab_live_verify(context, **arguments):
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
TOOLS["sentilab_dataset_export"] = sentilab_dataset_export


def sentilab_research_request(context, **arguments):
    from sentilab_core.research import request
    return request(context, **arguments)


def sentilab_research_status(context, **arguments):
    from sentilab_core.research import status
    return status(context, **arguments)


def sentilab_research_export(context, **arguments):
    from sentilab_core.research import export
    return export(context, **arguments)


TOOLS.update({"sentilab_research_" + name: globals()["sentilab_research_" + name]
              for name in ("request", "status", "export")})
