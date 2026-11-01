"""HTTP routes of the agent door, under /api/open/v1/door. The origin-token middleware in app/main.py guards them all:
only the Worker reaches them. GET routes only read; nothing a GET does can start a solve."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Header, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response

from .intake import MAX_BODY_BYTES
from .service import Door

router = APIRouter(prefix="/api/open/v1/door")
_door: Door | None = None
NO_STORE = {"cache-control": "no-store"}


def configure(door: Door | None) -> Door | None:
    """Install a door (tests, or the service at startup); returns the one it replaces."""
    global _door
    previous, _door = _door, door
    return previous


def runtime() -> Door:
    global _door
    if _door is None:
        _door = Door.from_env()
    return _door


def startup() -> None:
    """Start the workers. A door that cannot start stays closed; the rest of the API keeps serving."""
    try:
        runtime().start()
    except Exception:  # noqa: BLE001 - the door fails closed; its routes answer from what exists
        logging.getLogger(__name__).exception("the agent door did not start")


def shutdown() -> None:
    if _door is not None:
        _door.stop()


def _reply(status: int, body, headers: dict) -> Response:
    if body is None:
        return Response(status_code=status, headers={**NO_STORE, **headers})
    return JSONResponse(body, status_code=status, headers={**NO_STORE, **headers})


async def _body(request: Request) -> tuple:
    """(at most MAX_BODY_BYTES + 1 bytes, the declared length when the body is not read): enough to know a body is
    too large without reading the rest of it."""
    length = request.headers.get("content-length", "")
    declared = int(length) if length.isascii() and length.isdecimal() and len(length) <= 12 else None
    if declared is not None and declared > MAX_BODY_BYTES:
        return b"", declared
    chunks, size = [], 0
    async for chunk in request.stream():
        chunks.append(chunk)
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            break
    return b"".join(chunks)[:MAX_BODY_BYTES + 1], None


@router.post("/submit")
async def submit(request: Request) -> Response:
    raw, declared = await _body(request)
    return _reply(*await run_in_threadpool(runtime().submit, raw, declared))


@router.post("/arrival")
async def arrival(request: Request) -> Response:
    raw, declared = await _body(request)
    return _reply(*await run_in_threadpool(runtime().arrival, raw, declared))


@router.get("/status/{run_id}")
def status(run_id: str, x_door_nonce: str | None = Header(default=None)) -> Response:
    return _reply(*runtime().status(run_id, x_door_nonce))


@router.get("/results")
def results(after: str | None = None, limit: str | None = None) -> Response:
    return _reply(*runtime().results(after, limit))


@router.get("/events")
def events(after: str | None = None, limit: str | None = None) -> Response:
    return _reply(*runtime().events(after, limit))


@router.get("/board")
def board(x_door_nonce: str | None = Header(default=None)) -> Response:
    return _reply(*runtime().board(x_door_nonce))


@router.api_route("/terms", methods=["GET", "HEAD"])
def terms() -> Response:
    """The signed manifest's terms text: exactly the bytes its pin names (terms.py), or 503 terms_unavailable."""
    found = runtime().terms
    if found is None:
        return _reply(503, {"error": "terms_unavailable"}, {})
    return Response(found.data, media_type="text/markdown; charset=utf-8",
                    headers={**NO_STORE, "x-terms-version": found.version})
