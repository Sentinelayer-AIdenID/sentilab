"""Read-only, run-scoped signed view feed and optional service-owned live loop."""
import asyncio
import hashlib
import json
import os
import threading

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from sentilab_core import operations
from sentilab_core.ledger import replay

router = APIRouter()
_context = None
_thread = None
_failure = None


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
    global _thread
    if os.environ.get("SENTILAB_LIVE_ENABLED") != "1":
        return
    ctx = context()
    if ctx.signer is None:
        raise RuntimeError("live service requires the injected core signer and operator trust pin")

    def loop():
        global _failure
        try:
            while not (ctx.root / "STOP").exists():
                asyncio.run(operations.run(ctx, ai_off=True, duration=3600, renew=True))
        except Exception as exc:
            _failure = type(exc).__name__
    _thread = threading.Thread(target=loop, name="sentilab-ai-off", daemon=True)
    _thread.start()


@router.on_event("shutdown")
def stop_live_service():
    if _thread is not None and _thread.is_alive():
        operations.stop(context(), ai_off=True)
        _thread.join(timeout=20)


@router.get("/api/view/runs")
def runs():
    return {**operations.status(context(), ai_off=True), "service_error": _failure}


@router.get("/api/view/events")
def events(run_id: str, after: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=500)):
    try:
        state = replay(context().root, run_id, public_keys=context().public_keys)
        verified = operations.verify(context(), ai_off=True, run_id=run_id)
    except FileNotFoundError:
        raise HTTPException(404, "run not found") from None
    except ValueError:
        raise HTTPException(400, "invalid run_id") from None
    rows = [row["envelope"] for row in state["rows"] if "envelope" in row and
            isinstance(row["envelope"].get("event"), dict) and
            type(row["envelope"]["event"].get("seq")) is int and row["envelope"]["event"]["seq"] > after]
    page = rows[:limit]
    return JSONResponse({"run_id": run_id, "envelopes": page, "after": after,
                         "next_after": page[-1]["event"]["seq"] if page else after,
                         "has_more": len(rows) > limit, "prefix_end": verified["prefix_end"],
                         "chain_error": verified["chain_error"], "projection_error": verified["projection_error"],
                         "board": verified["board"], "projection": verified["projection"],
                         **operations.LABELS}, headers={"cache-control": "no-store"})


@router.get("/api/view/key")
def key():
    keys = [{"key_id": key_id, "alg": "ed25519", "public_key": raw.hex(),
             "key_sha256": hashlib.sha256(raw).hexdigest()} for key_id, raw in context().public_keys.items()]
    return {"keys": keys}
