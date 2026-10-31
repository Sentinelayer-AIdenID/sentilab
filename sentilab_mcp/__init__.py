"""MCP tool handlers; the host injects the same Context used by the CLI."""
from sentilab_core import operations


async def sentilab_live_run(context, **arguments):
    return await operations.run(context, **arguments)


def sentilab_live_status(context, **arguments):
    return operations.status(context, **arguments)


def sentilab_live_stop(context, **arguments):
    return operations.stop(context, **arguments)


def sentilab_live_verify(context, **arguments):
    return operations.verify(context, **arguments)


TOOLS = {"sentilab_live_" + name: globals()["sentilab_live_" + name] for name in ("run", "status", "stop", "verify")}
