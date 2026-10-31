"""Optional live TypeSafe smoke. Reads credentials from the process environment only."""
from __future__ import annotations

import asyncio
import json
import math
import os
import statistics
import sys

from controller import JevRoutingAdapter


async def main() -> int:
    if os.environ.get("JEV_ENABLE_REQUESTS") != "1" or not os.environ.get("JEV_API_KEY"):
        print("live call skipped: set JEV_ENABLE_REQUESTS=1 and JEV_API_KEY in the environment",
              file=sys.stderr)
        return 2
    try:
        samples = int(os.environ.get("JEV_LIVE_SAMPLES", "1"))
        timeout_s = float(os.environ.get("JEV_TIMEOUT_SECONDS", "10"))
    except ValueError:
        print("live call failed: sample count or timeout is invalid", file=sys.stderr)
        return 2
    if (not 1 <= samples <= 25 or not math.isfinite(timeout_s) or
            timeout_s <= 0 or timeout_s > JevRoutingAdapter.max_timeout_s):
        print("live call failed: samples must be 1..25 and timeout must be positive and at most 60 seconds",
              file=sys.stderr)
        return 2

    adapter = JevRoutingAdapter(max_calls=samples, timeout_s=timeout_s)
    latencies = []
    for _ in range(samples):
        result = await adapter.route({
            "verified_history": [],
            "evaluations_remaining": 1,
            "stagnation_count": 0,
            "current_tmax_c": None,
            "current_wirelength_mm": None,
            "current_wire_metric": None,
            "horizon_evaluations": 1,
        })
        if not result.get("provider_called") or result.get("model_validated") is not True:
            print("live call failed: pinned model response was not validated",
                  file=sys.stderr)
            return 1
        latencies.append(result["duration_ms"])

    ordered = sorted(latencies)
    p95 = ordered[math.ceil(0.95 * len(ordered)) - 1]
    print(json.dumps({
        "status": "ok",
        "model": "jev-1.13.0",
        "live_calls": samples,
        "median_latency_ms": statistics.median(latencies),
        "p95_latency_ms": p95,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
