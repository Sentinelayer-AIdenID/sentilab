"""Reproduce the eight published Ascend910 probes through the controller oracle."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import os
import tempfile

from tap_oracle import HOTSPOT_BINARY, HOTSPOT_ROOT, TAP_ROOT, HotSpotOracle


CASES = {
    "baseline_center": 25,
    "left_shift_2mm": 23,
    "left_shift_4mm": 21,
    "right_shift_2mm": 27,
}
BASE_CENTERS = ((25, 25), (40, 40), (8, 9), (8, 25), (8, 41), (41, 15))
LIMITATIONS = [
    "The TAP source models HotSpot 6; these measurements use upstream HotSpot 7 without calibration against the original output.",
    "Chiplet power is fixed; there is no transient workload or leakage feedback.",
    "The reported Manhattan center-distance metric is not CPLEX routed wirelength.",
    "Package parameters and bump assumptions are research defaults, not foundry verified.",
    "Each solver runtime is one measured observation, not a performance distribution.",
    "The 16x16 and 32x32 meshes can rank x=25 and x=27 differently; small temperature margins are not resolved physical superiority.",
]


def _revision(directory: Path) -> str:
    return (directory / "UPSTREAM_COMMIT").read_text(encoding="utf-8").strip()


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


async def _run(cases: list[str], solver_timeout_s: float) -> list[dict]:
    oracles = {}
    try:
        oracles = {
            grid: HotSpotOracle(grid, grid, solver_timeout_s=solver_timeout_s)
            for grid in (16, 32)
        }
        results = []
        for name in cases:
            centers = [list(point) for point in BASE_CENTERS]
            centers[0][0] = CASES[name]
            for grid in (16, 32):
                oracle = oracles[grid]
                design = oracle.design_from_centers(centers)
                result = await oracle(design)
                item = {
                    "placement": name,
                    "grid_rows": grid,
                    "grid_cols": grid,
                    "centers_mm": centers,
                    "microbump_halo_mm": oracle.problem.bump_halos_mm,
                    "legal_with_microbump_halo": True,
                    "power_W": sum(oracle.problem.powers_w),
                    "ambient_C": result.ambient_c,
                    "chip_layer_peak_C": result.maximum_temperature_c,
                    "all_layers_peak_C": result.all_layers_peak_c,
                    "weighted_Manhattan_center_distance_mm": result.wirelength_mm,
                    "solver_seconds": result.solver_seconds,
                    "evaluation_seconds": result.evaluation_seconds,
                    "input_generation_seconds": result.input_generation_seconds,
                    "candidate_hash": result.candidate_hash,
                    "problem_hash": result.problem_hash,
                    "solver_version": result.solver_version,
                    "heatmap_c": result.heatmap_c,
                    "input_sha256": dict(result.input_sha256),
                    "files": dict(result.input_sha256),
                }
                results.append(item)
                print(json.dumps({key: value for key, value in item.items()
                                  if key not in ("heatmap_c", "input_sha256", "files")},
                                 allow_nan=False), flush=True)
        return results
    finally:
        await asyncio.gather(*(oracle.aclose() for oracle in oracles.values()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", nargs="*", choices=tuple(CASES), help="probe cases to run (default: all four)")
    parser.add_argument("--solver-timeout", type=float, default=45.0,
                        help="maximum seconds for each HotSpot process (default: 45)")
    parser.add_argument("--report", type=Path,
                        help="report destination; the default is a unique timestamped file")
    args = parser.parse_args()
    cases = args.cases or list(CASES)

    results = asyncio.run(_run(cases, args.solver_timeout))
    report = {
        "hotspot_commit": _revision(HOTSPOT_ROOT),
        "tap_commit": _revision(TAP_ROOT),
        "tap_config_sha256": _sha256(TAP_ROOT / "configs" / "sys_ascend910.cfg"),
        "hotspot_config_sha256": _sha256(TAP_ROOT / "util" / "hotspot.config"),
        "hotspot_binary_sha256": _sha256(HOTSPOT_BINARY),
        "source_urls": ["https://github.com/bu-icsg/TAP-2.5D", "https://github.com/uvahotspot/HotSpot"],
        "meaning": "Hand-authored placement perturbations on published research data, generated through the TAP adapter and evaluated by upstream HotSpot 7. Not an agent optimization result, surrogate training, or commercial chip signoff.",
        "limitations": LIMITATIONS,
        "runs": results,
    }
    report_path = args.report
    if report_path is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        report_path = HOTSPOT_ROOT / "probe_results" / f"report_{stamp}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(report, indent=2, allow_nan=False)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=report_path.parent,
                                     prefix=f".{report_path.name}.", delete=False) as handle:
        temporary_path = Path(handle.name)
        handle.write(encoded)
        handle.write("\n")
    os.replace(temporary_path, report_path)
    print(f"report: {report_path}")


if __name__ == "__main__":
    main()
