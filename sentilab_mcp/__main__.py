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


def main():
    context = environment_context()
    while raw := sys.stdin.buffer.readline(65538):
        if len(raw) > 65537 or not raw.endswith(b"\n"):
            raise ValueError("MCP request exceeds 64 KiB")
        request = json.loads(raw)
        if "id" not in request:
            continue
        try:
            result = asyncio.run(handle(request, context))
            response = {"jsonrpc": "2.0", "id": request["id"], "result": result}
        except (ValueError, TypeError, KeyError, OSError) as exc:
            response = {"jsonrpc": "2.0", "id": request["id"],
                        "error": {"code": -32602, "message": type(exc).__name__}}
        print(json.dumps(response), flush=True)


if __name__ == "__main__":
    main()
