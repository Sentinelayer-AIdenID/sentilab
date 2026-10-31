"""Read-only, run-scoped signed view feed and optional service-owned live loop."""
import asyncio
import hashlib
import json
from itertools import groupby
from typing import Literal
import os
import threading

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from sentilab_core import operations
from sentilab_core.budget import Limits
from sentilab_core.ledger import replay
from sentilab_core.envelope import MAX_PAGE_BYTES, MAX_PAGE_LINES

router = APIRouter()
_context = None
_thread = None
_failure = None
_shutdown = None


def configure(context):
    global _context
    _context = context


def context():
    global _context
    if _context is None:
        _context = operations.environment_context()
    return _context


@router.on_event("startup")
def start_live_service():
    global _thread, _shutdown
    if os.environ.get("SENTILAB_LIVE_ENABLED") != "1":
        return
    if _thread is not None and _thread.is_alive():
        return
    ctx = context()
    ctx.options.setdefault("limits", Limits(development=False))
    if ctx.signer is None:
        raise RuntimeError("live service requires the injected core signer and operator trust pin")
    _shutdown = threading.Event()
    ctx.options["cancel_event"] = _shutdown

    def loop():
        global _failure
        try:
            while not _shutdown.is_set() and not (ctx.root / "STOP").exists():
                asyncio.run(operations.run(ctx, ai_off=True, duration=3600, renew=True))
        except Exception as exc:
            _failure = type(exc).__name__
    _thread = threading.Thread(target=loop, name="sentilab-ai-off", daemon=True)
    _thread.start()


@router.on_event("shutdown")
def stop_live_service():
    if _thread is not None and _thread.is_alive():
        _shutdown.set()
        _thread.join(timeout=20)


@router.get("/api/view/runs")
def runs():
    return {**operations.status(context(), ai_off=True), "service_error": _failure}


@router.get("/api/view/events")
def events(run_id: str, after: int | None = Query(None, ge=0),
           limit: int = Query(MAX_PAGE_LINES, ge=1, le=MAX_PAGE_LINES),
           format: Literal["jsonl", "json"] = "jsonl",
           cursor: int | None = Query(None, ge=0), cursor_hash: str | None = None):
    if cursor is not None and after is not None:
        raise HTTPException(422, "use cursor or after, not both")
    after = after or 0
    if cursor_hash is not None and (cursor is None or len(cursor_hash) != 64 or
                                    any(c not in "0123456789abcdef" for c in cursor_hash)):
        raise HTTPException(422, "invalid cursor hash")
    try:
        state = replay(context().root, run_id, public_keys=context().public_keys)
    except FileNotFoundError:
        raise HTTPException(404, "run not found") from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None

    def sequence(row):
        event = row.get("envelope", {}).get("event")
        seq = event.get("seq") if isinstance(event, dict) else None
        return seq if type(seq) is int and seq >= 1 else None

    # Re-send evidence of an earlier break so an existing client can freeze too.
    after_seq = min(after, state["last_seq"]) if state["error"] else after
    if cursor is not None:
        if cursor > len(state["source_rows"]):
            raise HTTPException(409, "ledger shortened; replay from cursor zero")
        boundary = (state["source_rows"][cursor - 1]["prefix_hash"] if cursor
                    else hashlib.sha256(b"").hexdigest())
        if (cursor and cursor_hash is None) or (cursor_hash is not None and cursor_hash != boundary):
            raise HTTPException(409, "cursor boundary missing or changed; replay from cursor zero")
        rows = state["source_rows"][cursor:]
        groups = ([row] for row in rows)
    else:
        rows = [row for row in state["rows"] if sequence(row) is None or sequence(row) > after_seq]
        groups = (list(group) for _, group in groupby(rows, key=sequence))
    page, byte_count = [], 0
    for group in groups:
        group_bytes = sum(len(row["raw"]) for row in group)
        if len(page) + len(group) > limit or byte_count + group_bytes > MAX_PAGE_BYTES:
            if page:
                break
            # Physical cursor transport preserves an over-cap row alone. The
            # client rejects the poll at its byte cap without losing evidence.
            if cursor is None or format != "jsonl":
                raise HTTPException(413, "one sequence group exceeds the view transport caps")
        page.extend(group)
        byte_count += group_bytes
    next_after = max((sequence(row) or after_seq for row in page), default=after_seq)
    headers = {"cache-control": "no-store", "x-next-after": str(next_after),
               "x-has-more": str(len(rows) > len(page)).lower()}
    position = {}
    if cursor is not None:
        position = {"cursor": cursor, "next_cursor": cursor + len(page),
                    "next_cursor_hash": page[-1]["prefix_hash"] if page else boundary}
        headers["x-next-cursor"] = str(position["next_cursor"])
        headers["x-cursor-hash"] = position["next_cursor_hash"]
    if format == "jsonl":
        return Response(b"".join(row["raw"] for row in page), media_type="application/x-ndjson", headers=headers)

    # Optional diagnostic representation retains the server's verified state.
    verified = operations.verified_state(state, run_id)
    content = json.dumps({"run_id": run_id, "envelopes": [row["envelope"] for row in page if "envelope" in row],
                          "after": after, "next_after": next_after, "has_more": len(rows) > len(page),
                          "prefix_end": verified["prefix_end"],
                          "unrenderable_rows": sum("envelope" not in row for row in state["rows"]),
                          "chain_error": verified["chain_error"], "projection_error": verified["projection_error"],
                          "board": verified["board"], "projection": verified["projection"],
                          **position, **operations.LABELS},
                         ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode()
    if len(content) > MAX_PAGE_BYTES:
        raise HTTPException(413, "diagnostic view exceeds the response byte cap")
    return Response(content, media_type="application/json", headers=headers)


@router.get("/api/view/key")
def key():
    keys = [{"key_id": key_id, "alg": "ed25519", "public_key": raw.hex(),
             "key_sha256": hashlib.sha256(raw).hexdigest()} for key_id, raw in context().public_keys.items()]
    return {"keys": keys}
