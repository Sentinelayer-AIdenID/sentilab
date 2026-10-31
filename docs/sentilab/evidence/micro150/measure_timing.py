"""Measure median and max seconds per evaluation for Ascend910 and micro150."""
from __future__ import annotations

import asyncio
import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
os.chdir(REPO_ROOT / "sundai_hotspot")
sys.path.insert(0, str(REPO_ROOT / "sundai_hotspot"))
sys.path.insert(0, str(REPO_ROOT))
from tap_oracle import HotSpotOracle

MICRO150_CENTERS = (
    (10, 10), (28, 10), (10, 28), (28, 28),
    (10, 42), (28, 42), (42, 10), (42, 28),
)
ASCEND910_CENTERS = ((25, 25), (40, 40), (8, 9), (8, 25), (8, 41), (41, 15))


async def measure_fixture(fixture: str, grid_rows: int, grid_cols: int, centers) -> dict:
    oracle = HotSpotOracle(grid_rows, grid_cols, fixture=fixture)
    design = oracle.design_from_centers(centers)
    times = []
    for _ in range(5):
        start = time.perf_counter()
        await oracle(design)
        times.append(time.perf_counter() - start)
    await oracle.aclose()
    return {
        "median_seconds": round(statistics.median(times), 6),
        "max_seconds": round(max(times), 6),
        "times_seconds": [round(t, 6) for t in times],
    }


async def main():
    results = {
        "machine": {
            "platform": platform.platform(),
            "processor": platform.processor() or "",
            "cpu_count": os.cpu_count(),
        },
        "fixtures": {},
    }
    for fixture, centers, label in [
        ("ascend910", ASCEND910_CENTERS, "Ascend910"),
        ("micro150", MICRO150_CENTERS, "micro150"),
    ]:
        results["fixtures"][fixture] = {"label": label}
        for rows, cols in [(16, 16), (32, 32), (64, 64)]:
            results["fixtures"][fixture][f"{rows}x{cols}"] = await measure_fixture(
                fixture, rows, cols, centers
            )
    out = Path(__file__).with_suffix(".json")
    out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(out)


if __name__ == "__main__":
    asyncio.run(main())
