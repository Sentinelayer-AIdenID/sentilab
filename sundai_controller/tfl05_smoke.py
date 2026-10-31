"""Run the TFL-05 four-lane smoke on the synthetic plate or TAP Ascend910."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "sundai_hotspot"))

from sundai_controller.controller import thermal_plate_adapter  # noqa: E402
from sundai_controller.experiment import plate_initial_design, run_four_lanes  # noqa: E402


TAP_INITIAL_CENTERS = ((25, 25), (40, 40), (8, 9), (8, 25), (8, 41), (41, 15))


async def run(benchmark: str) -> dict:
    if benchmark == "plate":
        initial = plate_initial_design()
        oracle = thermal_plate_adapter(grid_size=16)
    else:
        from tap_oracle import HotSpotOracle

        oracle = HotSpotOracle(16, 16)
        initial = oracle.design_from_centers(TAP_INITIAL_CENTERS)
    try:
        experiment = await run_four_lanes(
            initial, oracle, run_id=f"tfl05-{benchmark}-seed11", seed=11,
            evaluations_per_lane=4, evaluation_ceiling_microdollars=1,
            shared_sample_count=3,
        )
    finally:
        close = getattr(oracle, "aclose", None)
        if close is not None:
            await close()
    assert experiment["evaluation_counts_equal"]
    assert experiment["flight_records_valid"]
    assert all(lane["evaluation_count"] == 4 and lane["evaluation_admissions"] == 4
               for lane in experiment["lane_results"].values())
    return {
        "benchmark": benchmark,
        "grid": "16x16",
        "seed": experiment["seed"],
        "shared_initial_samples": experiment["shared_initial_sample_count"],
        "evaluation_counts_equal": experiment["evaluation_counts_equal"],
        "flight_records_valid": experiment["flight_records_valid"],
        "lanes": {
            lane_id: {
                "agent_id": lane["agent_id"],
                "evaluation_count": lane["evaluation_count"],
                "best_temperature_c": lane["best_temperature_c"],
                "record_valid": lane["record_valid"],
            }
            for lane_id, lane in experiment["lane_results"].items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", choices=("plate", "ascend910"), required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.benchmark)), sort_keys=True, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
