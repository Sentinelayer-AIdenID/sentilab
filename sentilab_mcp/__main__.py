"""Stdio MCP host for shared live operations, ResultCheck and dataset export."""
import asyncio
import json
import sys

from . import TOOLS


class LazyLiveContext:
    """Share one live context per host, initialized only by a live call."""

    def __init__(self):
        self.context = None

    def get(self):
        if self.context is None:
            from sentilab_core.operations import environment_context
            self.context = environment_context()
        return self.context


def schema(name):
    if name == "sentilab_resultcheck":
        return {"type": "object", "properties": {"file": {"type": "string"}},
                "required": ["file"], "additionalProperties": False}
    if name == "sentilab_dataset_export":
        return {"type": "object", "properties": {
            "run_ids": {"type": "array", "minItems": 1, "items": {"type": "string"}},
            "output_dir": {"type": "string"},
            "policy": {"type": "object", "properties": {
                "heldout_families": {"type": "array", "items": {"type": "string"}},
                "rights": {"type": "object", "additionalProperties": {
                    "type": "object", "properties": {
                        "status": {"enum": ["ok", "blocked"]}, "reason": {"type": "string", "minLength": 1}},
                    "required": ["status", "reason"], "additionalProperties": False}}},
                "additionalProperties": False}},
            "required": ["run_ids"], "additionalProperties": False}
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
        return {"tools": [{"name": name, "description": ("Check local ResultCheck v2 file consistency and arithmetic"
                                           if name == "sentilab_resultcheck" else
                                           "Export recorded verifier datasets" if name == "sentilab_dataset_export" else
                                           "AI off live " + name.rsplit("_", 1)[-1]),
                           "inputSchema": schema(name)} for name in TOOLS]}
    if method == "tools/call":
        params = request["params"]
        name, arguments = params["name"], params.get("arguments", {})
        if name not in TOOLS or set(arguments) - set(schema(name)["properties"]):
            raise ValueError("invalid live operation")
        if name == "sentilab_resultcheck":
            from sentilab_core.resultcheck import canonical
            if set(arguments) != {"file"} or not isinstance(arguments["file"], str):
                raise ValueError("file must be a local path string")
            try:
                receipt = await TOOLS[name](context, **arguments)
            except (OSError, ValueError):
                return {"content": [{"type": "text", "text": canonical({"error": {"code": "file_unreadable"}})}],
                        "isError": True}
            return {"content": [{"type": "text", "text": canonical(receipt)}],
                    "isError": receipt["status"] == "rejected"}
        if isinstance(context, LazyLiveContext):
            context = context.get()
        if context is None:
            from sentilab_core.operations import environment_context
            context = environment_context()
        result = TOOLS[name](context, **arguments)
        if hasattr(result, "__await__"):
            result = await result
        return {"content": [{"type": "text", "text": json.dumps(result, allow_nan=False)}]}
    if method == "ping":
        return {}
    raise ValueError("unknown method")


async def serve(context=None):
    if context is None:
        context = LazyLiveContext()
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
        except Exception:
            response = error(request["id"], -32603, "internal error")
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
    asyncio.run(serve())


if __name__ == "__main__":
    main()
