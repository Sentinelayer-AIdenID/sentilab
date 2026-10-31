"""Thermal Flight Lab API: /api/health and the TFL-09-min run service (app/runs.py).

When ORIGIN_SHARED_TOKEN is set (production), every request must carry it in x-origin-token: the Container App URL
is public, and only the thermal.aidenid.com Worker holds the token, so callers cannot bypass the front door (and its
rate limits). Unset (local runs, CI), the check is off."""
import hmac
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from app import runs

app = FastAPI(title="Thermal Flight Lab API")
ORIGIN_TOKEN = os.environ.get("ORIGIN_SHARED_TOKEN", "")


@app.middleware("http")
async def require_origin_token(request: Request, call_next):
    sent = request.headers.get("x-origin-token", "").encode("utf-8")
    if ORIGIN_TOKEN and not hmac.compare_digest(sent, ORIGIN_TOKEN.encode("utf-8")):
        return JSONResponse({"ok": False, "error": "use https://thermal.aidenid.com"}, status_code=403)
    return await call_next(request)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "service": "thermal-api", "build_sha": os.environ.get("BUILD_SHA", "unknown")}


@app.on_event("startup")
def mark_interrupted_runs() -> None:
    runs.recover()


@app.post("/api/runs")
async def start_run(request: Request):
    try:
        body = await request.json()
    except ValueError:
        return JSONResponse({"error": "body must be JSON"}, status_code=400)
    try:
        started = runs.start(body)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    if started is None:
        return JSONResponse({"error": "busy", "detail": "one run at a time; try again shortly"}, status_code=429,
                            headers={"retry-after": "5"})
    return JSONResponse(started, status_code=202)


@app.get("/api/runs")
def list_runs() -> dict:
    return {"runs": runs.recent()}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    text = runs.get(run_id)
    if text is None:
        return JSONResponse({"error": "run not found"}, status_code=404)
    return Response(text, media_type="application/json", headers={"cache-control": "no-store"})
