"""Dependency-free wire limits and safe CLI/MCP error receipts."""
import json


MAX_INPUT_BYTES = 64 * 1024


def error_receipt(code=-32602, message="ValueError"):
    # Callers supply fixed messages or exception class names, never input or
    # exception text (which can contain paths, rejected values or credentials).
    return {"error": {"code": code, "message": message}}


def check_cli_size(arguments):
    size = 0
    for argument in arguments:
        size += len(argument.encode("utf-8")) + 1
        if size > MAX_INPUT_BYTES:
            raise ValueError("CLI input exceeds 64 KiB")


def parse_request(raw):
    def reject_constant(value):
        raise ValueError("nonfinite JSON value")

    try:
        request = json.loads(raw, parse_constant=reject_constant)
        if not isinstance(request, dict) or not isinstance(request.get("method"), str):
            raise ValueError("invalid MCP request")
        if "id" in request and type(request["id"]) not in (str, int):
            raise ValueError("invalid request id")
        if "params" in request and not isinstance(request["params"], dict):
            raise ValueError("invalid request parameters")
        return request
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ValueError("invalid MCP request") from None
