"""MCP tools delegate to the same lane code and worker cleanup as the CLI."""
import asyncio
import json
import os
import sys

from sentilab_core.execution import recorded_call

RESULTCHECK_TIMEOUT = 10

EXPORT_TIMEOUT_SECONDS = 30


async def sentilab_live_run(context, **arguments):
    from sentilab_core import operations
    return await operations.run(context, **arguments)


async def sentilab_live_status(context, **arguments):
    return await recorded_call(context, "live.status", arguments)


async def sentilab_live_stop(context, **arguments):
    return await recorded_call(context, "live.stop", arguments)


async def sentilab_live_verify(context, **arguments):
    return await recorded_call(context, "live.verify", arguments)


async def sentilab_dataset_export(context, **arguments):
    return await recorded_call(context, "dataset.export", arguments, timeout=EXPORT_TIMEOUT_SECONDS)


async def sentilab_chiplet_build(context, **arguments):
    return await recorded_call(context, "chiplet.build", arguments)


async def sentilab_chiplet_render(context, **arguments):
    return await recorded_call(context, "chiplet.render", arguments)


async def sentilab_chiplet_replay(context, **arguments):
    return await recorded_call(context, "chiplet.replay", arguments)


async def sentilab_chiplet_export(context, **arguments):
    return await recorded_call(context, "chiplet.export", arguments, timeout=EXPORT_TIMEOUT_SECONDS)


async def sentilab_gb10_status(context, **arguments):
    return await recorded_call(context, "gb10.status", arguments)


async def sentilab_gb10_checkpoint_verify(context, **arguments):
    return await recorded_call(context, "gb10.checkpoint_verify", arguments)


TOOLS = {"sentilab_live_" + name: globals()["sentilab_live_" + name]
         for name in ("run", "status", "stop", "verify")}
TOOLS["sentilab_dataset_export"] = sentilab_dataset_export
TOOLS.update({"sentilab_chiplet_" + name: globals()["sentilab_chiplet_" + name]
              for name in ("build", "render", "replay", "export")})
TOOLS.update(sentilab_gb10_status=sentilab_gb10_status,
             sentilab_gb10_checkpoint_verify=sentilab_gb10_checkpoint_verify)


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


def sentilab_memory_recall(context, **arguments):
    from sentilab_core import operations
    return operations.memory_recall(context, **arguments)


def sentilab_memory_audit(context, **arguments):
    from sentilab_core import operations
    return operations.memory_audit(context, **arguments)


def sentilab_route(context, **arguments):
    from sentilab_core import operations
    return operations.route(context, **arguments)


TOOLS.update(sentilab_memory_recall=sentilab_memory_recall,
             sentilab_memory_audit=sentilab_memory_audit,
             sentilab_route=sentilab_route)


async def sentilab_proposal_context(context, **arguments):
    from sentilab_core.proposals import execute
    return await execute("context", context, **arguments)


async def sentilab_proposal_submit(context, **arguments):
    from sentilab_core.proposals import execute
    return await execute("submit", context, **arguments)


TOOLS.update(sentilab_proposal_context=sentilab_proposal_context,
             sentilab_proposal_submit=sentilab_proposal_submit)
