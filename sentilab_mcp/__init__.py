"""MCP tool handlers; the host injects the same Context used by the CLI."""


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


def sentilab_resultcheck(context=None, *, file):
    from sentilab_core.resultcheck import check_file
    if not isinstance(file, str):
        raise ValueError("file must be a local path string")
    return check_file(file)


TOOLS["sentilab_resultcheck"] = sentilab_resultcheck
