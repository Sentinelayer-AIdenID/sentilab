"""TFL-09-min run service: start a four-lane experiment, poll it, list recent runs.

One run at a time (a second POST gets 429). A run executes run_four_lanes() in a worker thread and is written to
RUNS_DIR as <id>.json through a temp file and rename, so a reader never sees a partial file and runs survive a restart.
A run that was still "running" when the process stopped is marked "interrupted" at the next start."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for extra in (ROOT, ROOT / "sundai_hotspot"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

BENCHMARKS = ("plate", "ascend910")
SIGNAL_MODES = ("local", "live")
SIGNAL_TIMEOUT_S = 5
GRIDS = (16, 32)
MAX_PROPOSALS = 8
TAP_INITIAL_CENTERS = ((25, 25), (40, 40), (8, 9), (8, 25), (8, 41), (41, 15))
_busy = threading.Lock()


def runs_dir() -> Path:
    configured = os.environ.get("RUNS_DIR")
    path = Path(configured) if configured else (Path("/data/runs") if Path("/data").is_dir() else Path("/tmp/runs"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _path(run_id: str) -> Path:
    return runs_dir() / f"{run_id}.json"


def _write(run: dict) -> None:
    tmp = runs_dir() / f".{run['id']}.{uuid.uuid4().hex}.tmp"
    tmp.write_text(json.dumps(run, allow_nan=False), encoding="utf-8")
    os.replace(tmp, _path(run["id"]))


def validate(body: dict) -> dict:
    """The accepted request, or ValueError naming the first bad field."""
    if not isinstance(body, dict):
        raise ValueError("body must be a JSON object")
    benchmark = body.get("benchmark", "plate")
    grid, seed, proposals = body.get("grid", 16), body.get("seed", 11), body.get("proposals", 4)
    signal = body.get("signal", "local")
    if signal not in SIGNAL_MODES:
        raise ValueError(f"signal must be one of {list(SIGNAL_MODES)}")
    if benchmark not in BENCHMARKS:
        raise ValueError(f"benchmark must be one of {list(BENCHMARKS)}")
    for name, value in (("grid", grid), ("seed", seed), ("proposals", proposals)):
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{name} must be an integer")
    if grid not in GRIDS:
        raise ValueError(f"grid must be one of {list(GRIDS)}")
    if not 0 <= seed <= 1_000_000:
        raise ValueError("seed must be between 0 and 1000000")
    if not 1 <= proposals <= MAX_PROPOSALS:
        raise ValueError(f"proposals must be between 1 and {MAX_PROPOSALS}")
    return {"benchmark": benchmark, "grid": grid, "seed": seed, "proposals": proposals, "signal": signal}


def _oracle(benchmark: str, grid: int):
    from sundai_controller.experiment import plate_initial_design

    if benchmark == "plate":
        from sundai_controller.controller import thermal_plate_adapter

        return plate_initial_design(), thermal_plate_adapter(grid_size=grid)
    from tap_oracle import HotSpotOracle

    oracle = HotSpotOracle(grid, grid)
    return oracle.design_from_centers(TAP_INITIAL_CENTERS), oracle


def _signal_router(run: dict):
    """The signal-portfolio lane's router: none for "local" (deterministic policy); for "live", the bounded
    signal-layer CHOICE adapter, at most one call per proposal. JEV_ENABLE_REQUESTS stays the master switch:
    with it off, the adapter falls back to the deterministic policy without calling out."""
    if run.get("signal") != "live":
        return None
    from sundai_controller.controller import JevRoutingAdapter

    return JevRoutingAdapter(max_calls=run["proposals"], timeout_s=SIGNAL_TIMEOUT_S)


def _execute(run: dict) -> None:
    started = time.perf_counter()
    try:
        from sundai_controller.experiment import run_four_lanes

        initial, oracle = _oracle(run["benchmark"], run["grid"])

        async def execute_run():
            try:
                return await run_four_lanes(
                    initial, oracle, run_id=run["id"], seed=run["seed"], evaluations_per_lane=run["proposals"],
                    evaluation_ceiling_microdollars=1, shared_sample_count=3,
                    signal_router=_signal_router(run))
            finally:
                close = getattr(oracle, "aclose", None)
                if close is not None:
                    await close()

        result = asyncio.run(execute_run())
        run.update(status="done", result=result)
    except Exception as exc:  # noqa: BLE001 - a failed run is recorded, never raised into the server
        run.update(status="failed", error=f"{type(exc).__name__}: {exc}"[:500])
    finally:
        run.update(finished_at=time.time(), duration_s=round(time.perf_counter() - started, 3))
        try:
            _write(run)
        finally:
            _busy.release()


def start(body: dict) -> dict | None:
    """Start a run and return its record, or None when one is already running."""
    request = validate(body)
    if not _busy.acquire(blocking=False):
        return None
    try:
        run = {"id": uuid.uuid4().hex, "status": "running", **request, "created_at": time.time(),
               "finished_at": None, "duration_s": None, "error": None, "result": None}
        _write(run)
        threading.Thread(target=_execute, args=(run,), name=f"run-{run['id'][:8]}", daemon=True).start()
    except BaseException:
        _busy.release()
        raise
    return {"id": run["id"], "status": "running"}


def get(run_id: str) -> str | None:
    """The stored run as JSON text (served as-is so number text survives), or None."""
    if not (len(run_id) == 32 and all(c in "0123456789abcdef" for c in run_id)):
        return None
    path = _path(run_id)
    return path.read_text(encoding="utf-8") if path.is_file() else None


def _best(result: dict | None) -> dict | None:
    lanes = (result or {}).get("lane_results") or {}
    scored = [(lane["best_temperature_c"], lane_id) for lane_id, lane in lanes.items()
              if isinstance(lane.get("best_temperature_c"), (int, float))]
    if not scored:
        return None
    temp, lane_id = min(scored)
    return {"lane_id": lane_id, "best_temperature_c": temp}


def recent(limit: int = 20) -> list[dict]:
    rows = []
    for path in sorted(runs_dir().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            run = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        fields = ("id", "status", "benchmark", "grid", "seed", "proposals", "signal", "created_at", "duration_s", "error")
        rows.append({k: run.get(k) for k in fields} | {"best": _best(run.get("result"))})
    return rows


def recover() -> None:
    """Mark runs that were in flight when the process stopped; they will never finish."""
    for path in runs_dir().glob("*.json"):
        try:
            run = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if run.get("status") == "running":
            run.update(status="interrupted", error="the service restarted during this run", finished_at=time.time())
            _write(run)
