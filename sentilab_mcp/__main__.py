"""Minimal stdio MCP host for the four shared live operations."""
import asyncio
import json
import sys

from sentilab_core.operations import environment_context
from . import TOOLS


def schema(name):
    properties = {"ai_off": {"type": "boolean", "const": True}}
    required = ["ai_off"]
    if name != "sentilab_live_stop":
        properties["run_id"] = {"type": "string"}
    if name == "sentilab_live_verify":
        required.append("run_id")
    if name == "sentilab_live_run":
        properties.update(duration={"type": "number", "minimum": 0, "maximum": 86400},
                          interval={"type": "number", "minimum": 0, "maximum": 3600},
                          renew={"type": "boolean"})
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


async def handle(request, context):
    method = request.get("method")
    if method == "initialize":
        return {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                "serverInfo": {"name": "sentilab-live", "version": "0.1"}}
    if method == "tools/list":
        return {"tools": [{"name": name, "description": "AI off live " + name.rsplit("_", 1)[-1],
                           "inputSchema": schema(name)} for name in TOOLS]}
    if method == "tools/call":
        params = request["params"]
        name, arguments = params["name"], params.get("arguments", {})
        if name not in TOOLS or set(arguments) - set(schema(name)["properties"]):
            raise ValueError("invalid live operation")
        result = TOOLS[name](context, **arguments)
        if hasattr(result, "__await__"):
            result = await result
        return {"content": [{"type": "text", "text": json.dumps(result, allow_nan=False)}]}
    if method == "ping":
        return {}
    raise ValueError("unknown method")


async def serve(context):
    reader = asyncio.StreamReader(limit=65538)
    transport, _ = await asyncio.get_running_loop().connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(reader), sys.stdin.buffer)
    pending = {}

    def error(id, code, message):
        return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}

    async def dispatch(request):
        try:
            result = await handle(request, context)
            response = {"jsonrpc": "2.0", "id": request["id"], "result": result}
        except asyncio.CancelledError:
            response = error(request["id"], -32800, "request cancelled")
        except (ValueError, TypeError, KeyError, OSError) as exc:
            response = error(request["id"], -32602, type(exc).__name__)
        print(json.dumps(response), flush=True)

    def finished(id, task):
        pending.pop(id, None)
        # Observe task errors, and close a peer that no longer reads responses.
        if not task.cancelled() and task.exception() is not None:
            transport.close()

    try:
        while raw := await reader.readline():
            if len(raw) > 65537 or not raw.endswith(b"\n"):
                raise ValueError("MCP request exceeds 64 KiB")
            request = json.loads(raw)
            if "id" not in request:
                if request.get("method") == "notifications/cancelled":
                    task = pending.get(request.get("params", {}).get("requestId"))
                    if task is not None and not task.cancelling():
                        task.cancel()
                continue
            id = request["id"]
            if type(id) not in (str, int):
                raise ValueError("invalid request id")
            if id in pending or len(pending) >= 8:
                print(json.dumps(error(id, -32000, "request already active or server busy")), flush=True)
                continue
            task = asyncio.create_task(dispatch(request))
            pending[id] = task
            task.add_done_callback(lambda task, id=id: finished(id, task))
            # Dispatch buffered requests promptly without waiting for completion.
            await asyncio.sleep(0)
    finally:
        transport.close()
        tasks = list(pending.values())
        for task in tasks:
            if not task.cancelling():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def main():
    asyncio.run(serve(environment_context()))


if __name__ == "__main__":
    main()
