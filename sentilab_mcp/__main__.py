"""Stdio MCP host for shared live operations and recorded dataset export."""
import asyncio
import json
import sys

from sentilab_core.capabilities import for_tool
from sentilab_core.transport import MAX_INPUT_BYTES, error_receipt, parse_request
from . import TOOLS


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
    return name, arguments


async def handle(request, context):
    method = request.get("method")
    if method == "initialize":
        return {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                "serverInfo": {"name": "sentilab-live", "version": "0.1"}}
    if method == "tools/list":
        return {"tools": [{"name": name, "description": ("Export recorded verifier datasets" if name == "sentilab_dataset_export"
                                                        else "AI off live " + name.rsplit("_", 1)[-1]),
                           "inputSchema": schema(name)} for name in TOOLS]}
    if method == "tools/call":
        name, arguments = call_arguments(request)
        result = TOOLS[name](context, **arguments)
        if hasattr(result, "__await__"):
            result = await result
        return {"content": [{"type": "text", "text": json.dumps(result, allow_nan=False)}]}
    if method == "ping":
        return {}
    raise ValueError("unknown method")


async def serve(context=None):
    reader = asyncio.StreamReader(limit=MAX_INPUT_BYTES + 2)
    transport, _ = await asyncio.get_running_loop().connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(reader), sys.stdin.buffer)
    pending = {}

    def error(id, code, message):
        return {"jsonrpc": "2.0", "id": id, **error_receipt(code, message)}

    async def dispatch(request):
        nonlocal context
        try:
            if request.get("method") == "tools/call" and context is None:
                # Refuse malformed calls before any signer/solver imports or
                # environment-dependent work. Discovery needs no lane context.
                call_arguments(request)
                from sentilab_core.operations import environment_context
                context = environment_context()
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
        while True:
            try:
                raw = await reader.readline()
            except ValueError:
                print(json.dumps(error(None, -32602, "ValueError")), flush=True)
                break
            if not raw:
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
