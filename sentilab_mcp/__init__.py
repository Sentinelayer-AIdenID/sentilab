"""MCP tools delegate to the same lane code and worker cleanup as the CLI."""
from sentilab_core.execution import recorded_call

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


TOOLS = {"sentilab_live_" + name: globals()["sentilab_live_" + name]
         for name in ("run", "status", "stop", "verify")}
TOOLS["sentilab_dataset_export"] = sentilab_dataset_export
TOOLS.update({"sentilab_chiplet_" + name: globals()["sentilab_chiplet_" + name]
              for name in ("build", "render", "replay", "export")})
