"""Stdio MCP host for live, ResultCheck, datasets, research, memory and chiplet operations."""
import asyncio
import json
import sys

from sentilab_core.capabilities import for_tool
from sentilab_core.transport import MAX_INPUT_BYTES, error_receipt, parse_request
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
    try:
        return for_tool(name).input_schema
    except StopIteration:
        raise ValueError("unregistered MCP tool") from None


def call_arguments(request):
    params = request.get("params")
    if not isinstance(params, dict):
        raise ValueError("invalid tool parameters")
    name, arguments = params.get("name"), params.get("arguments", {})
    if (not isinstance(name, str) or name not in TOOLS or not isinstance(arguments, dict)
            or set(arguments) - set(schema(name)["properties"])):
        raise ValueError("invalid operation")
    from sentilab_core.execution import admit
    admit(name, arguments)
    return name, arguments


async def handle(request, context):
    method = request.get("method")
    if method == "initialize":
        return {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                "serverInfo": {"name": "sentilab-live", "version": "0.1"}}
    if method == "tools/list":
        return {"tools": [{"name": name, "description": for_tool(name).name,
                           "inputSchema": schema(name)} for name in TOOLS
                           if getattr(context, "proposal_session", None) is None
                           or name.startswith("sentilab_proposal_")]}
    if method == "tools/call":
        params = request.get("params")
        if not isinstance(params, dict) or not isinstance(params.get("name"), str):
            raise ValueError("invalid tool parameters")
        name, arguments = params["name"], params.get("arguments", {})
        from sentilab_core.execution import authorize_session
        authorize_session(name, context)
        if name in TOOLS:
            from sentilab_core.execution import authorize
            authorize(name)
        if name in TOOLS and name.startswith("sentilab_research_"):
            from sentilab_core.research import dumps
            if isinstance(context, LazyLiveContext):
                context = context.get()
            if context is None:
                from sentilab_core.operations import environment_context
                context = environment_context()
            result = (TOOLS[name](context, **arguments) if type(arguments) is dict else
                      {"ok": False, "error": {"code": "invalid_input"}})
            return {"content": [{"type": "text", "text": dumps(result)}], "isError": not result["ok"]}
        if (name not in TOOLS or not isinstance(arguments, dict)
                or set(arguments) - set(schema(name)["properties"])):
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
        name, arguments = call_arguments(request)
        if isinstance(context, LazyLiveContext):
            context = context.get()
        if context is None:
            from sentilab_core.operations import environment_context
            context = environment_context()
        if name in ("sentilab_memory_recall", "sentilab_memory_audit", "sentilab_route"):
            from sentilab_core.execution import recorded_call
            result = recorded_call(context, for_tool(name).name, arguments)
        else:
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
    reader = asyncio.StreamReader(limit=MAX_INPUT_BYTES + 2)
    transport, _ = await asyncio.get_running_loop().connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(reader), sys.stdin.buffer)
    pending = {}

    def error(id, code, message):
        return {"jsonrpc": "2.0", "id": id, **error_receipt(code, message)}

    async def dispatch(request):
        try:
            result = await handle(request, context)
            response = {"jsonrpc": "2.0", "id": request["id"], "result": result}
        except asyncio.CancelledError:
            response = error(request["id"], -32800, "request cancelled")
        except PermissionError:
            response = error(request["id"], -32001, "capability scope refused")
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
        while True:
            try:
                raw = await reader.readline()
            except ValueError:
                print(json.dumps(error(None, -32602, "ValueError")), flush=True)
                break
            if not raw:
                # A CLI pipeline closes stdin immediately after its request.
                # Give finite reads a bounded drain window, then use the same
                # cancellation/cleanup path for blocked work and disconnects.
                if pending:
                    await asyncio.wait(list(pending.values()), timeout=1)
                break
            if len(raw) > MAX_INPUT_BYTES + 1 or not raw.endswith(b"\n"):
                print(json.dumps(error(None, -32602, "ValueError")), flush=True)
                break
            try:
                request = parse_request(raw)
            except ValueError:
                print(json.dumps(error(None, -32602, "ValueError")), flush=True)
                continue
            if "id" not in request:
                if request.get("method") == "notifications/cancelled":
                    request_id = request.get("params", {}).get("requestId")
                    if type(request_id) not in (str, int):
                        continue
                    task = pending.get(request_id)
                    if task is not None and not task.cancelling():
                        task.cancel()
                continue
            id = request["id"]
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
