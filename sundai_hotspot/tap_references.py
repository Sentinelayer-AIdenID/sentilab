"""SLAB-048 reference layouts reconstructed from TAP-2.5D figures, and the SAMPLED envelope plan.

Layouts per reference, never confused:
- raw: the die centres exactly as extracted from the paper's vector figure. Approximate. It passes
  the continuous geometry rules; only the 0.5 mm search lattice refuses it. Gate zero (the
  paper-reconstruction comparison) uses this layout, frozen by its content hash.
- snapped (1 mm): the first legal experiment layout, kept unchanged. It is NOT the paper's layout.
- snap0p5: plain nearest-0.5 mm rounding of the raw layout, legal with no repair. It is the
  ENGINEERING comparison and sensitivity baseline (astra, ScienceClaw #56857/#56858), separately
  admitted, never a paper match. The SAMPLED envelope probes it.

Geometry only: this module builds, checks and writes JSON. It runs TAP's wire router (a MILP on a
real optimizer, no physics) and never a thermal solver. Every route goes through _routed_mm, which
refuses a SciPy other than requirements.txt's pin before the optimizer runs.

    python -m sundai_hotspot.tap_references --check   # committed files equal a fresh build
    python -m sundai_hotspot.tap_references --write   # rebuild them from the committed decode
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import sys
from pathlib import Path

from sundai_hotspot.tap_oracle import REPO_ROOT, TAP_CONFIGS, TapGeometry, TapLegalityError
from sundai_hotspot.tap_router import routed_wirelength, solver_versions

TICKET = {"id": "SLAB-048", "name": "REF-RECON", "uuid": "c3dcb49a-430a-462e-a446-f532da204c46"}
REFERENCES_DIR = REPO_ROOT / "docs" / "sentilab" / "references"
DECODER = REFERENCES_DIR / "decode_tap25d_figures.py"
DECODE = REFERENCES_DIR / "tap25d-figure-decode.json"
ENVELOPE_PLAN = REFERENCES_DIR / "envelope-plan.json"
ROUTER = REPO_ROOT / "sundai_hotspot" / "tap_router.py"
REQUIREMENTS = REPO_ROOT / "requirements.txt"
RAW_LABEL = "raw reconstruction (approximate, from published figure)"
SNAPPED_LABEL = "legal snapped variant (adjusted)"
VARIANT_SUFFIX = "snap0p5"
VARIANT_LATTICE_MM = 0.5
VARIANT_LABEL = "0.5 mm snapped variant (plain nearest rounding, no repair): engineering baseline, not the paper's layout"
VARIANT_ROLE = ("ENGINEERING comparison and sensitivity baseline, separately admitted (astra, ScienceClaw #56857 and "
                "#56858). Never a paper match, and not part of gate zero: gate zero uses the raw 45 mm reference.")
LABELS = ("approximate reconstruction from published figure", "simulated reference, not silicon")
CLAIM_LABEL = ("Simulated with [evaluator and hash], steady state, uniform power per die. Reference reconstructed "
               "from a published figure. Not CAD, not silicon, not measured.")
ROUNDING_RULE = ("Each centre coordinate c becomes 0.5 * floor(c / 0.5 + 0.5): the nearest multiple of 0.5 mm. "
                 "An exact tie (c / 0.5 ends in .5) rounds up, toward +infinity. Rotations are kept. No repair moves.")
UNITS = {"length": "mm", "coordinates": "die centres; origin at the interposer's lower-left corner; +x right, +y up",
         "rotation": "true = turned 90 degrees from the fixture config's (width, height)"}
SNAP_GRID_MM = 1.0
MAX_SNAP_STEPS = 8
PERTURBATION_MM = 0.5
ENVELOPE_GRID = 64
ROUND_TRIP = {"temperature_tolerance_k": 1.0, "routed_wire_tolerance_pct": 2.0}
ROUTED_LABEL = "routed (open router), not paper"
HIGHS_STATUS = ("reported by the pinned SciPy build and recorded; not pinned, and not an admission of any other "
                "binary or host")
WIRE_METRIC = ("wire_proxy_mm is the oracle's W: a connectivity-weighted mean Manhattan centre distance, a proxy, "
               "not comparable with the paper's routed mm. routed_wirelength_mm comes from an open port of TAP's "
               "router (sundai_hotspot/tap_router.py), the same kind of metric the paper reports.")
PAPER_SETTINGS = {
    "interposer_mm": 45, "placement_grid_mm": 1, "thermal_grid": "64x64", "ambient_c": 45,
    "simulator": "HotSpot 6.0 (ours: HotSpot 7)",
    "temperature_metric": (
        "Three statistics, kept separate and never substituted for one another: (1) TAP's selector, "
        "run_hotspot() in sundai_tap/passive_interposer.py: the maximum of stdout.split()[3::2], i.e. of the unit "
        "temperatures HotSpot prints for the run (with -grid_map_mode center from sundai_tap/util/hotspot.config); "
        "it is not by construction limited to the chip layer, and reproducing it needs the literal selector or a "
        "reviewed emulation of it; (2) the native temperatures of the real chiplet units (Chiplet_i); (3) the "
        "active (chip) layer grid peak, our J, with -grid_map_mode max."),
    "wire_metric": "total routed inter-chiplet wirelength from TAP's MILP router (CPLEX)",
}
REFERENCES = (
    {
        "reference_id": "ascend910-tap25d-fig6a",
        "track": "MATCH",
        "title": "Huawei Ascend 910 original layout as drawn in TAP-2.5D Fig. 6(a)",
        "figure": "fig6", "panel": "a", "fixture_id": "ascend910-45mm",
        "dies": ("Vitruvian compute die (TAP spells it Virtuvian), 256 W", "Nimbus I/O die, 14 W",
                 "HBM stack, 20 W", "HBM stack, 20 W", "HBM stack, 20 W", "HBM stack, 20 W"),
        "extra_labels": ("SHIPPED product (Huawei Ascend 910); positions read from a published figure, not CAD",),
        "paper_reported": {
            "original": {"panel": "a", "peak_temperature_c": 75.48, "routed_wirelength_mm": 16426,
                         "link_type": "nppl"},
            "quote": ("The original layout of Ascend 910 System (Fig. 6(a)) already achieves minimum wirelength "
                      "and is thermally-safe when running at the nominal frequency."),
        },
        # Out-of-sample: published points not used to build or tune anything here.
        "validation_points": (
            {"panel": "b", "method": "Compact-2.5D", "peak_temperature_c": 75.13, "routed_wirelength_mm": 23794,
             "link_type": "nppl"},
            {"panel": "c", "method": "TAP-2.5D", "peak_temperature_c": 75.47, "routed_wirelength_mm": 16597,
             "link_type": "nppl"},
        ),
        "model_omissions": (
            "The shipped package carries two unpowered silicon dummy dies (about 110 mm2 each, Hot Chips 31: "
            "'added to ensure mechanical uniformity') beside Nimbus. TAP-2.5D's model, its Fig. 6(a) and this "
            "reconstruction omit them, so their lateral heat path is not modelled.",
            "TAP's die sizes and its 256/14/4x20 W power split are TAP modelling assumptions, not Huawei data "
            "(HBM drawn 7.75 x 11.87 mm = 92 mm2; Huawei's slide gives 96 mm2).",
        ),
    },
    {
        "reference_id": "micro150-tap25d-fig5a",
        "track": "BEAT",
        "title": "CPU-DRAM original placement (Kannan et al., MICRO 2015) as drawn in TAP-2.5D Fig. 5(a)",
        "figure": "fig5", "panel": "a", "fixture_id": "micro150-45mm",
        "dies": ("CPU, 150 W", "CPU, 150 W", "CPU, 150 W", "CPU, 150 W",
                 "DRAM, 20 W", "DRAM, 20 W", "DRAM, 20 W", "DRAM, 20 W"),
        "extra_labels": ("human-designed RESEARCH layout (Kannan et al., MICRO 2015), not a shipped package",),
        "paper_reported": {
            "original": {"panel": "a", "peak_temperature_c": 115.94, "routed_wirelength_mm": 67686,
                         "link_type": "nppl"},
            "quote": ("The original placement (a) is optimal from the routing perspective (total wirelength of "
                      "67,686mm according to our evaluation). However, our HotSpot simulations show that the "
                      "system operates at 115.94oC, which is thermally infeasible."),
        },
        "validation_points": (
            {"panel": "b", "method": "Compact-2.5D", "peak_temperature_c": 113.54, "routed_wirelength_mm": 100864,
             "link_type": "nppl"},
            {"panel": "c", "method": "TAP-2.5D, repeaterless non-pipelined links", "peak_temperature_c": 94.89,
             "routed_wirelength_mm": 216064, "link_type": "nppl"},
            {"panel": "d", "method": "TAP-2.5D, gas-station links", "peak_temperature_c": 93.89,
             "routed_wirelength_mm": 138956, "link_type": "ppl"},
        ),
        "model_omissions": (
            "Kannan et al.'s design is a research proposal; TAP-2.5D's die sizes and powers are its model of it.",
        ),
    },
)
TIMING = REPO_ROOT / "docs/sentilab/evidence/micro150/TIMING.json"
MESH_ASCEND = REPO_ROOT / "docs/sentilab/evidence/mesh/ascend910/RESULT.json"
MESH_MICRO_ROWS = REPO_ROOT / "docs/sentilab/evidence/mesh/micro150/rows.jsonl"
SLAB039 = REPO_ROOT / "docs/sentilab/evidence/SLAB-039/RESULT.json"
POLICY = REPO_ROOT / "docs/sentilab/evidence/SLAB-039/SUPERVISOR-POLICY.json"
# Declared per-call reserves (CPU-s): reap and settlement tail as approved in SUPERVISOR-POLICY.json;
# startup and archive are this plan's own declared reserves, each well above the heuristic overhead estimate.
STARTUP_RESERVE_S = 0.25
ARCHIVE_RESERVE_S = 0.25
FAILED_ATTEMPT_FRACTION = 0.10


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _json_bytes(value) -> bytes:
    return (json.dumps(value, indent=1, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _mm(value: float) -> float:
    """Millimetres at the decode's 1e-4 mm resolution; also strips float noise such as 0.30000000000000004."""
    return round(float(value), 4) + 0.0


def _violations(geometry: TapGeometry, centers, rotated):
    return geometry.layout_violations(geometry.design_from_centers(centers, rotated))


def _violation_records(violations):
    return [{"rule": v.rule, "dies": list(v.dies), "amount_mm": _mm(v.amount_mm), "message": v.message}
            for v in violations]


def round_to_lattice(value: float, step: float) -> float:
    """Nearest multiple of step; an exact tie rounds up, toward +infinity (see ROUNDING_RULE)."""
    return math.floor(value / step + 0.5) * step


def layout_identity(frame_mm: float, centers, rotated, footprints) -> dict:
    """A content hash for a layout: canonical JSON of its frame, units, centres, rotations and footprints."""
    canonical = {"schema": "sentilab-layout-identity-v1", "units": UNITS, "frame_mm": float(frame_mm),
                 "die_order": "TAP fixture config order",
                 "centers_mm": [[float(v) for v in c] for c in centers], "rotated": [bool(f) for f in rotated],
                 "footprints_mm": [[float(v) for v in f] for f in footprints]}
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return {"canonical": canonical, "content_sha256": hashlib.sha256(encoded).hexdigest(),
            "hashing": "sha256 of json.dumps(canonical, sort_keys=True, separators=(',', ':'))"}


def displacement(raw_centers, centers) -> dict:
    """Raw-to-layout displacement under two named norms: per coordinate (L-infinity) and Euclidean per die."""
    per_die = []
    for die, (r, c) in enumerate(zip(raw_centers, centers)):
        dx, dy = c[0] - r[0], c[1] - r[1]
        per_die.append({"die": die, "dx_mm": _mm(dx), "dy_mm": _mm(dy), "euclidean_mm": round(math.hypot(dx, dy), 6)})
    return {"per_die": per_die,
            "max_per_coordinate_linf_mm": _mm(max(max(abs(d["dx_mm"]), abs(d["dy_mm"])) for d in per_die)),
            "max_euclidean_mm": max(d["euclidean_mm"] for d in per_die)}


def pinned_solver() -> dict:
    """Refuse unless SciPy is the version requirements.txt pins; return the checked versions for the record.

    Only SciPy is pinned. The HiGHS version is whatever this SciPy build reports: it is recorded, not pinned,
    and it admits no other binary or host.
    """
    pin = re.search(r"^scipy==(\S+)$", REQUIREMENTS.read_text(encoding="utf-8"), re.M)
    versions = solver_versions()
    if pin is None or versions["scipy"] != pin.group(1):
        raise RuntimeError(f"routed records need scipy=={pin.group(1) if pin else '?'} (requirements.txt); "
                           f"this environment has {versions['scipy']}")
    return {"scipy": versions["scipy"], "scipy_pinned_by": "requirements.txt",
            "highs": versions["highs"], "highs_status": HIGHS_STATUS}


def continuous_legal(geometry: TapGeometry, centers, rotated) -> tuple[bool, str | None]:
    """The continuous geometry rules without the search lattice (TapGeometry.continuous_centers_for)."""
    try:
        geometry.continuous_centers_for(geometry.design_from_centers(centers, rotated))
    except TapLegalityError as exc:
        return False, str(exc)
    return True, None


def legal_on(geometry: TapGeometry, centers, rotated) -> tuple[bool, str | None]:
    """The fixture's own gate (TapGeometry.centers_for), not a re-implementation."""
    try:
        geometry.centers_for(geometry.design_from_centers(centers, rotated))
    except TapLegalityError as exc:
        return False, str(exc)
    return True, None


def minimal_snaps(geometry: TapGeometry, raw_centers, rotated, grid_mm: float) -> tuple[tuple, dict]:
    """Every legal layout reachable from the rounded raw centres with the fewest grid-step moves.

    Conflict-directed: from the current layout it branches only on one-step moves of the dies in the
    first remaining violation. That is complete, because no move of a third die can clear a margin or
    pair violation. Returns the rounded centres and {steps per die: centres}.
    """
    count = len(raw_centers)
    rounded = tuple(tuple(round_to_lattice(value, grid_mm) for value in point) for point in raw_centers)

    def centers_for(steps):
        return tuple((rounded[i][0] + steps[i][0] * grid_mm, rounded[i][1] + steps[i][1] * grid_mm)
                     for i in range(count))

    solutions = {}
    for depth in range(MAX_SNAP_STEPS + 1):
        steps = [[0, 0] for _ in range(count)]

        def search(remaining):
            problems = _violations(geometry, centers_for(steps), rotated)
            if not problems:
                if remaining == 0:
                    key = tuple(tuple(step) for step in steps)
                    solutions[key] = centers_for(steps)
                return
            if remaining == 0:
                return
            for die in problems[0].dies:
                for axis in (0, 1):
                    for sign in (1, -1):
                        if steps[die][axis] * sign < 0:  # never undo a step: a minimal set has no pair
                            continue
                        steps[die][axis] += sign
                        search(remaining - 1)
                        steps[die][axis] -= sign

        search(depth)
        if solutions:
            return rounded, solutions
    raise ValueError(f"no legal {grid_mm:g} mm layout within {MAX_SNAP_STEPS} grid steps of the raw centres")


def snap_to_grid(geometry: TapGeometry, raw_centers, rotated, *, decode_precision_mm: float,
                 grid_mm: float = SNAP_GRID_MM) -> dict:
    """Round each centre to the nearest grid node, then make the fewest grid-step moves that make
    the layout legal on the fixture (minimal_snaps). Among the move sets of minimal size it keeps the
    one closest to the raw centres (sum of squared distances), then the lexicographically smallest
    centres. If the runner-up is closer than the decode precision can separate, the result says so.
    """
    rounded, solutions = minimal_snaps(geometry, raw_centers, rotated, grid_mm)
    count = len(raw_centers)

    def centers_for(steps):
        return tuple((rounded[i][0] + steps[i][0] * grid_mm, rounded[i][1] + steps[i][1] * grid_mm)
                     for i in range(count))

    def cost(centers):
        return sum((c[0] - r[0]) ** 2 + (c[1] - r[1]) ** 2 for c, r in zip(centers, raw_centers))

    ranked = sorted(solutions.items(), key=lambda item: (cost(item[1]), item[1]))
    best_steps, best = ranked[0]
    if not legal_on(geometry, best, rotated)[0]:
        raise AssertionError("snapped layout failed the fixture gate")
    adjustments = []
    for die, (dx, dy) in enumerate(best_steps):
        if dx == 0 and dy == 0:
            continue
        # The reason is exactly what dropping this adjustment would break.
        without = list(best_steps)
        without[die] = (0, 0)
        dropped = _violations(geometry, centers_for(without), rotated)
        if not dropped:
            raise AssertionError(f"adjustment of die {die} is not needed; the move set is not minimal")
        adjustments.append({"die": die, "dx_mm": dx * grid_mm, "dy_mm": dy * grid_mm,
                            "reason": [v.message for v in dropped],
                            "violations_if_dropped": _violation_records(dropped)})
    alternatives = [{"centers_mm": [list(c) for c in centers], "squared_distance_to_raw_mm2": _mm(cost(centers))}
                    for _, centers in ranked[1:4]]
    runner_up = None
    if len(ranked) > 1:
        second = ranked[1][1]
        margin = cost(second) - cost(best)
        # Moving each raw coordinate by up to the decode precision shifts the cost difference by at most this.
        bound = sum(2 * decode_precision_mm * (abs(b - r) + abs(s - r))
                    for bp, sp, rp in zip(best, second, raw_centers) for b, s, r in zip(bp, sp, rp) if b != s)
        runner_up = {"squared_distance_margin_mm2": _mm(margin), "decode_precision_bound_mm2": _mm(bound),
                     "decided_below_decode_precision": margin <= bound}
    return {
        "rounded_centers_mm": [list(c) for c in rounded],
        "rounded_violations": _violation_records(_violations(geometry, rounded, rotated)),
        "grid_steps": int(sum(abs(s) for pair in best_steps for s in pair)),
        "adjustments": adjustments,
        "centers_mm": [list(c) for c in best],
        "squared_distance_to_raw_mm2": _mm(cost(best)),
        "alternatives_same_step_count": alternatives,
        "runner_up": runner_up,
    }


def _precision_evidence(decode: dict) -> dict:
    """TAP's own placer puts centres on the 1 mm grid, so its panels measure the decode error."""
    deviations = []
    for figure in decode["figures"].values():
        for panel_name, panel in figure["panels"].items():
            if panel_name == "a":
                continue
            for chiplet in panel["chiplets"]:
                deviations.extend(abs(v - round(v)) for v in chiplet["decoded_center_mm"])
    return {"tap_placer_panels": "fig5 b,c,d and fig6 b,c (TAP output, 1 mm grid by construction)",
            "max_center_offset_from_grid_mm": _mm(max(deviations)), "centers_checked": len(deviations) // 2,
            "norm": "per coordinate (L-infinity)",
            "kind": ("empirical estimate under stated assumptions: the TAP-placer panels sit exactly on its 1 mm grid, "
                     "and the drawing maps every panel the same way. It is not a figure-to-silicon error bound."),
            "reuse": ("These five panels are also the router's validation points, so the two checks are not "
                      "independent of each other.")}


def _routed_mm(problem, centers, rotated, link_type) -> tuple[float, dict]:
    """The builder's only route. The SciPy pin is checked before the optimizer runs, so a mismatched stack is
    refused with zero optimizer calls.

    Returns the routed total, rounded to 0.1 mm (every committed value sits at least 0.015 mm from a rounding
    boundary), and the solver versions checked for this route, for the record.
    """
    solver = pinned_solver()
    wire = routed_wirelength(problem, centers, rotated, link_type=link_type)
    return round(wire.total_mm, 1), solver


def _vs_paper(routed_mm: float, paper_mm: float) -> float:
    return round(100 * (routed_mm - paper_mm) / paper_mm, 3)


def _coordinate_uncertainty(panel: dict, center, grid_error_mm: float) -> list[float]:
    """Per-coordinate decode uncertainty (mm), rounded up: TAP-grid decode error, plus the coordinate times
    the spread of the panel's three scale estimates, plus half the 1e-4 mm storage step."""
    scales = panel["scale_pt_per_mm"]
    estimates = (scales["x"], scales["y"], scales["from_die_outlines"])
    spread = (max(estimates) - min(estimates)) / min(estimates)
    return [math.ceil((grid_error_mm + abs(v) * spread + 0.00005) * 1e4) / 1e4 for v in center]


def build_reference(spec: dict, decode: dict) -> dict:
    geometry = TapGeometry.load(spec["fixture_id"])
    problem = geometry.problem
    figure = decode["figures"][spec["figure"]]
    panel = figure["panels"][spec["panel"]]
    dies = panel["chiplets"]
    raw_centers = tuple(tuple(d["decoded_center_mm"]) for d in dies)
    rotated = tuple(d["rotated_vs_catalog"] for d in dies)
    if panel["frame_mm"] != problem.interposer_size_mm or len(dies) != len(problem.widths_mm):
        raise ValueError(f"{spec['reference_id']}: decoded frame or die count does not match {spec['fixture_id']}")

    raw_design = geometry.design_from_centers(raw_centers, rotated)
    raw_legal, raw_reason = legal_on(geometry, raw_centers, rotated)
    physical_violations = geometry.layout_violations(raw_design, lattice=False)
    raw_continuous_legal, _ = continuous_legal(geometry, raw_centers, rotated)
    raw_wire = geometry.wirelength_mm(TapGeometry._centers(raw_design))

    precision = _precision_evidence(decode)
    snapped = snap_to_grid(geometry, raw_centers, rotated,
                           decode_precision_mm=precision["max_center_offset_from_grid_mm"])
    snapped_centers = tuple(tuple(c) for c in snapped["centers_mm"])
    snapped_design = geometry.design_from_centers(snapped_centers, rotated)
    snapped_wire = geometry.wirelength_mm(geometry.centers_for(snapped_design))
    deltas = [{"die": i, "dx_mm": _mm(s[0] - r[0]), "dy_mm": _mm(s[1] - r[1])}
              for i, (r, s) in enumerate(zip(raw_centers, snapped_centers))]
    config = TAP_CONFIGS[spec["fixture_id"]]
    original = spec["paper_reported"]["original"]
    raw_routed, solver = _routed_mm(problem, raw_centers, rotated, original["link_type"])
    snapped_routed, _ = _routed_mm(problem, snapped_centers, rotated, original["link_type"])
    validation = []
    for point in spec["validation_points"]:
        chiplets = figure["panels"][point["panel"]]["chiplets"]
        # TAP's own placer output: back onto its 1 mm grid (the decode is within 0.0005 mm of it).
        centers = [[float(round(v)) for v in c["decoded_center_mm"]] for c in chiplets]
        routed, _ = _routed_mm(problem, centers, [c["rotated_vs_catalog"] for c in chiplets], point["link_type"])
        validation.append({**point, "figure": spec["figure"].replace("fig", "Fig. "), "centers_mm": centers,
                           "rotated": [c["rotated_vs_catalog"] for c in chiplets], "our_routed_wirelength_mm": routed,
                           "routed_label": ROUTED_LABEL,
                           "routed_vs_paper_pct": _vs_paper(routed, point["routed_wirelength_mm"]),
                           "reuse": "this panel also feeds the decode-precision estimate",
                           "temperature": "paper value only; not evaluated (no thermal solve in SLAB-048)"})
    raw_identity = layout_identity(problem.interposer_size_mm, raw_centers, rotated, [d["footprint_mm"] for d in dies])
    snapped_identity = layout_identity(problem.interposer_size_mm, snapped_centers, rotated,
                                       [d["footprint_mm"] for d in dies])
    snapped_norms = displacement(raw_centers, snapped_centers)
    return {
        "schema": "sentilab-reference-layout-v1",
        "reference_id": spec["reference_id"],
        "ticket": TICKET,
        "track": spec["track"],
        "title": spec["title"],
        "labels": [*LABELS, *spec["extra_labels"]],
        "claim_label": CLAIM_LABEL,
        "fixture": {"fixture_id": spec["fixture_id"], "config": _rel(config), "config_sha256": _sha256(config),
                    "frame_mm": problem.interposer_size_mm},
        "interposer_mm": problem.interposer_size_mm,
        "source": {**decode["paper"], "page_number": decode["paper"]["page_index"] + 1,
                   "figure": spec["figure"].replace("fig", "Fig. "), "panel": spec["panel"],
                   "caption": figure["caption"]},
        "decoding": {
            "script": _rel(DECODER), "script_sha256": _sha256(DECODER),
            "output": _rel(DECODE), "output_sha256": _sha256(DECODE),
            "pymupdf_version": decode["pymupdf_version"],
            "displayed_rotated_90_cw": panel["displayed_rotated_90_cw"],
            "frame_pt": panel["frame_pt"], "scale_pt_per_mm": panel["scale_pt_per_mm"],
            "frame_checks_mm": panel["frame_checks_mm"],
            "origin": "lower-left corner of the interposer frame (outer edge of TAP's Edge_2/Edge_0 strips)",
            "precision": precision,
        },
        "paper_reported": spec["paper_reported"],
        "paper_settings": PAPER_SETTINGS,
        "model_omissions": list(spec["model_omissions"]),
        "dies": [{"die": i, "name": name, "catalog_mm": [w, h], "power_w": p, "halo_mm": halo}
                 for i, (name, w, h, p, halo) in enumerate(zip(spec["dies"], problem.widths_mm, problem.heights_mm,
                                                                problem.powers_w, problem.bump_halos_mm))],
        "raw": {
            "label": RAW_LABEL,
            "centers_mm": [list(c) for c in raw_centers],
            "rotated": list(rotated),
            "footprints_mm": [list(d["footprint_mm"]) for d in dies],
            "lower_left_mm": [list(d["decoded_lower_left_mm"]) for d in dies],
            "decoded_size_mm": [list(d["decoded_size_mm"]) for d in dies],
            "center_uncertainty_mm": [_coordinate_uncertainty(panel, c, precision["max_center_offset_from_grid_mm"])
                                      for c in raw_centers],
            "how_obtained": [
                f"Die {d['die']}: the outline drawn as Chiplet_{d['die']} (die-sized unit {d['die'] + 1} in the "
                f"figure's drawing order); centre = midpoint of the outline, outline pt {d['body_pt']}, mapped "
                f"through the panel's edge-strip frame" for d in dies],
            "uncertainty_rule": ("An empirical estimate under stated assumptions, per coordinate (L-infinity): "
                                 "the decode error measured on TAP's own panels (max offset from its 1 mm grid) + "
                                 "the coordinate x the relative spread of the panel's three scale estimates + the "
                                 "5e-5 mm storage step, rounded up to 1e-4 mm. It covers reading the figure only; "
                                 "it is not a figure-to-silicon error bound, and the figure's fidelity to the "
                                 "authors' simulated layout is not measurable from the figure."),
            "identity": raw_identity,
            "role": ("gate zero: the paper-reconstruction comparison (astra, ScienceClaw #56858). Frozen by "
                     "identity.content_sha256; use it with its exact continuous geometry and rotations."),
            "design_hash": raw_design.hash,
            "continuous_rules_legal": raw_continuous_legal,
            "continuous_rules_check": "sundai_hotspot/tap_oracle.py TapGeometry.continuous_centers_for",
            "legal_on_fixture": raw_legal,
            "fixture_gate_message": raw_reason,
            "violations_on_fixture": _violation_records(_violations(geometry, raw_centers, rotated)),
            "violations_without_center_lattice": _violation_records(physical_violations),
            "wire_proxy_mm": _mm(raw_wire),
            "routed_wirelength_mm": raw_routed,
        },
        "round_trip": {
            "criteria": (f"Our evaluator and router on the raw reference land within the paper's own numbers: "
                         f"temperature within {ROUND_TRIP['temperature_tolerance_k']:g} K and routed wire within "
                         f"{ROUND_TRIP['routed_wire_tolerance_pct']:g}% (room #56739, item (b)2)."),
            "wire": {"router": _rel(ROUTER), "router_sha256": _sha256(ROUTER), "solver": solver, "layout": "raw",
                     "routed_wirelength_mm": raw_routed, "routed_label": ROUTED_LABEL,
                     "paper_mm": original["routed_wirelength_mm"],
                     "difference_pct": _vs_paper(raw_routed, original["routed_wirelength_mm"]),
                     "tolerance_pct": ROUND_TRIP["routed_wire_tolerance_pct"],
                     "within_tolerance": abs(_vs_paper(raw_routed, original["routed_wirelength_mm"]))
                     <= ROUND_TRIP["routed_wire_tolerance_pct"],
                     "note": ("Consistency evidence, not identification. Routed wire depends only on differences "
                              "between pin positions, so a common translation of the whole layout leaves it "
                              "unchanged: agreement checks the relative geometry, not the absolute coordinates. "
                              "The routes launch no thermal solver; they run a real optimizer (HiGHS) under "
                              "whatever per-job accounting applies.")},
            "temperature": {
                "status": "PLANNED, NOT RUN: SLAB-048 has no solve grant",
                "paper_c": original["peak_temperature_c"],
                "tolerance_k": ROUND_TRIP["temperature_tolerance_k"],
                "layout": "raw",
                "prerequisites": [
                    "a named warden grant for the solves",
                    "the paper's statistic: TAP's literal run_hotspot selector (max of stdout.split()[3::2], with "
                    "-grid_map_mode center at 64x64) or a reviewed emulation of it. It is not assumed to be "
                    "chip-layer-only; the chiplet unit temperatures and our active-layer grid peak J are separate "
                    "statistics (see paper_settings.temperature_metric)",
                    "the paper's package physics: HotSpot 6.0 vertical coupling, or a reviewed fix (SLAB-049 "
                    "CAL-COUPLING)",
                    "an evaluation path that validates the raw centres with the continuous rules "
                    "(TapGeometry.continuous_centers_for): HotSpotOracle calls keep the 0.5 mm search lattice, "
                    "which refuses them",
                ],
            },
        },
        "validation_points": validation,
        "snapped": {
            "label": SNAPPED_LABEL,
            "is_the_paper_layout": False,
            "grid_mm": SNAP_GRID_MM,
            "rule": ("Round every raw centre to the nearest 1 mm grid node, then make the fewest 1 mm moves that "
                     "make the layout legal on the fixture (margin with halo, halo non-overlap, 0.1 mm minimum "
                     "body spacing, centre lattice). Ties at that move count go to the layout closest to the raw "
                     "centres (sum of squared distances), then the lexicographically smallest centres."),
            **snapped,
            "rotated": list(rotated),
            "design_hash": snapped_design.hash,
            "identity": snapped_identity,
            "legal_on_fixture": True,
            "wire_proxy_mm": _mm(snapped_wire),
            "routed_wirelength_mm": snapped_routed,
            "routed_label": ROUTED_LABEL,
        },
        "raw_to_snapped_mm": deltas,
        "max_abs_raw_to_snapped_mm": _mm(max(max(abs(d["dx_mm"]), abs(d["dy_mm"])) for d in deltas)),
        "raw_to_snapped_norms": {
            "max_per_coordinate_linf_mm": snapped_norms["max_per_coordinate_linf_mm"],
            "max_euclidean_mm": snapped_norms["max_euclidean_mm"],
            "raw_inside_pm0p5_mm_per_coordinate_box": snapped_norms["max_per_coordinate_linf_mm"] <= 0.5,
            "note": "max_abs_raw_to_snapped_mm is the per-coordinate (L-infinity) maximum",
        },
        "wire_metric": WIRE_METRIC,
    }


def _timing_inputs() -> dict:
    timing = json.loads(TIMING.read_text(encoding="utf-8"))
    mesh = json.loads(MESH_ASCEND.read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in MESH_MICRO_ROWS.read_text(encoding="utf-8").splitlines() if line.strip()]
    micro64 = [row["parsed_receipt"]["evaluation_seconds"] for row in rows
               if row.get("kind") == "evaluation" and row.get("grid") == 64]
    ascend64 = [layout["seconds"]["64"] for layout in mesh["layouts"]]
    slab039 = json.loads(SLAB039.read_text(encoding="utf-8"))
    policy = json.loads(POLICY.read_text(encoding="utf-8"))["limits"]
    per_call_039 = slab039["cpu_seconds"] / slab039["aggregate_evaluations"]
    grid32 = timing["fixtures"]["ascend910"]["32x32"]["median_seconds"]
    return {
        "host": timing["machine"],
        "median_64_s": {fixture: timing["fixtures"][fixture]["64x64"]["median_seconds"]
                        for fixture in ("ascend910", "micro150")},
        "worst_64_s": max(max(ascend64), max(micro64),
                          *(timing["fixtures"][f]["64x64"]["max_seconds"] for f in ("ascend910", "micro150"))),
        "mesh_64": {"ascend910": {"n": len(ascend64), "median_s": statistics.median(ascend64), "max_s": max(ascend64)},
                    "micro150": {"n": len(micro64), "median_s": statistics.median(micro64), "max_s": max(micro64)}},
        "overhead_s": per_call_039 - grid32,
        "slab039_per_call_cpu_s": per_call_039,
        "grid32_median_s": grid32,
        "reap_s": policy["reap_seconds"],
        "tail_s": policy["settlement_tail_cpu_seconds"],
    }


def build_variant(reference: dict, decode: dict) -> dict:
    """The 0.5 mm engineering variant: plain nearest rounding of the raw layout, legal with no repair."""
    fixture = reference["fixture"]["fixture_id"]
    geometry = TapGeometry.load(fixture)
    problem = geometry.problem
    raw = reference["raw"]
    rotated = tuple(raw["rotated"])
    raw_centers = [tuple(c) for c in raw["centers_mm"]]
    centers = [[round_to_lattice(v, VARIANT_LATTICE_MM) for v in c] for c in raw_centers]
    legal, message = legal_on(geometry, centers, rotated)
    if not legal:
        raise ValueError(f"{reference['reference_id']}: plain 0.5 mm rounding needs a repair: {message}")
    design = geometry.design_from_centers(centers, rotated)
    norms = displacement(raw_centers, centers)
    one_mm = displacement(raw_centers, reference["snapped"]["centers_mm"])
    _, minimal = minimal_snaps(geometry, raw_centers, rotated, SNAP_GRID_MM)
    minimal_linf = [displacement(raw_centers, c)["max_per_coordinate_linf_mm"] for c in minimal.values()]
    original = reference["paper_reported"]["original"]
    routed, solver = _routed_mm(problem, centers, rotated, original["link_type"])
    variant_id = f"{reference['reference_id']}-{VARIANT_SUFFIX}"
    return {
        "schema": "sentilab-layout-variant-v1",
        "variant_id": variant_id,
        "ticket": TICKET,
        "role": VARIANT_ROLE,
        "label": VARIANT_LABEL,
        "labels": [*LABELS, "engineering comparison and sensitivity baseline, not a paper match"],
        "is_the_paper_layout": False,
        "decision": {
            "by": "astra (ScienceClaw #56857, #56858); accepted in astra's sealed review of PR #57",
            "rationale": ("Chosen because plain rounding is legal on the fixture with zero repair moves and moves the "
                          "dies less than the 1 mm variant. Decided before any new thermal outcome, and NOT chosen "
                          "to fit the published routed wire."),
        },
        "derived_from": {"reference_id": reference["reference_id"],
                         "raw_identity_sha256": raw["identity"]["content_sha256"],
                         "raw_design_hash": raw["design_hash"]},
        "units": UNITS,
        "fixture": reference["fixture"],
        "sources": {"pdf_sha256": reference["source"]["pdf_sha256"],
                    "decoder": reference["decoding"]["script"], "decoder_sha256": reference["decoding"]["script_sha256"],
                    "decode_output": reference["decoding"]["output"],
                    "decode_output_sha256": reference["decoding"]["output_sha256"]},
        "rounding_rule": ROUNDING_RULE,
        "repair_moves": 0,
        "centers_mm": centers,
        "rotated": list(rotated),
        "footprints_mm": raw["footprints_mm"],
        "identity": layout_identity(problem.interposer_size_mm, centers, rotated, raw["footprints_mm"]),
        "design_hash": design.hash,
        "legal_on_fixture": True,
        "displacement_from_raw": norms,
        "raw_inside_pm0p5_mm_per_coordinate_box": norms["max_per_coordinate_linf_mm"] <= 0.5,
        "one_mm_snapped_for_comparison": {
            "where": f"docs/sentilab/references/{reference['reference_id']}.json, field snapped",
            "max_per_coordinate_linf_mm": one_mm["max_per_coordinate_linf_mm"],
            "max_euclidean_mm": one_mm["max_euclidean_mm"],
            "raw_inside_pm0p5_mm_per_coordinate_box": one_mm["max_per_coordinate_linf_mm"] <= 0.5,
            "all_minimal_1mm_snaps": {"count": len(minimal), "max_per_coordinate_linf_mm_min": min(minimal_linf),
                                      "max_per_coordinate_linf_mm_max": max(minimal_linf)},
        },
        "wire_proxy_mm": _mm(geometry.wirelength_mm(geometry.centers_for(design))),
        "routed_wirelength": {"value_mm": routed, "label": ROUTED_LABEL,
                              "vs_paper_pct": _vs_paper(routed, original["routed_wirelength_mm"]),
                              "router": _rel(ROUTER), "router_sha256": _sha256(ROUTER), "solver": solver},
        "limits": [
            "A raw layout inside this variant's +/-0.5 mm per-coordinate box is not thereby a sampled point of the "
            "envelope: its one-axis stencil moves one die along one axis at a time.",
            "Finite sensitivity probes do not prove a uniform reconstruction bound.",
        ],
    }


def _envelope(bases: list[dict], timing: dict) -> dict:
    """Calls for each base layout: itself, plus each die +/-0.5 mm in x and separately in y."""
    reserve = STARTUP_RESERVE_S + timing["reap_s"] + ARCHIVE_RESERVE_S
    plans, forecast, reserved, total = [], 0.0, 0.0, 0
    for base in bases:
        geometry = TapGeometry.load(base["fixture_id"])
        rotated = tuple(base["rotated"])
        start = [list(c) for c in base["centers_mm"]]
        calls, excluded = [], []
        options = [("base", None, None, 0.0)] + [
            (f"die{die}/{axis}{'+' if delta > 0 else '-'}{PERTURBATION_MM:g}", die, axis, delta)
            for die in range(len(start)) for axis in ("x", "y") for delta in (PERTURBATION_MM, -PERTURBATION_MM)]
        for name, die, axis, delta in options:
            centers = [list(c) for c in start]
            if die is not None:
                centers[die][0 if axis == "x" else 1] += delta
            entry = {"call_id": f"{base['id']}/{name}", "die": die, "axis": axis, "delta_mm": delta}
            legal, reason = legal_on(geometry, centers, rotated)
            if not legal:
                excluded.append({**entry, "fixture_gate_message": reason,
                                 "violations": _violation_records(_violations(geometry, centers, rotated))})
                continue
            design = geometry.design_from_centers(centers, rotated)
            calls.append({**entry, "centers_mm": centers, "rotated": list(rotated), "design_hash": design.hash,
                          "wire_proxy_mm": _mm(geometry.wirelength_mm(geometry.centers_for(design)))})
        if calls[0]["call_id"] != f"{base['id']}/base":
            raise ValueError("the unperturbed base layout must be legal")
        family = base["fixture_id"].removesuffix("-45mm")
        median = timing["median_64_s"][family]
        forecast += len(calls) * (median + timing["overhead_s"])
        reserved += len(calls) * (median + reserve)
        total += len(calls)
        plans.append({**{k: v for k, v in base.items() if k not in ("centers_mm", "rotated")},
                      "timing_family": family, "grid": ENVELOPE_GRID,
                      "considered": len(options), "expected_call_count": len(calls),
                      "excluded_count": len(excluded), "calls": calls, "excluded": excluded})
    worst_call = timing["worst_64_s"] + reserve
    failed = math.ceil(FAILED_ATTEMPT_FRACTION * total) * worst_call
    cap = reserved + failed + worst_call + timing["tail_s"]
    return {"plans": plans, "total": total, "forecast": forecast, "reserved": reserved, "failed": failed,
            "worst_call": worst_call, "cap": cap}


def build_envelope_plan(references: list[dict], variants: list[dict]) -> dict:
    timing = _timing_inputs()
    bases = [{"id": v["variant_id"], "fixture_id": v["fixture"]["fixture_id"],
              "fixture_config_sha256": v["fixture"]["config_sha256"], "layout": v["label"],
              "layout_source": f"docs/sentilab/references/{v['variant_id']}.json",
              "base_identity_sha256": v["identity"]["content_sha256"], "base_design_hash": v["design_hash"],
              "centers_mm": v["centers_mm"], "rotated": v["rotated"],
              "raw_to_base": {"max_per_coordinate_linf_mm": v["displacement_from_raw"]["max_per_coordinate_linf_mm"],
                              "max_euclidean_mm": v["displacement_from_raw"]["max_euclidean_mm"]}}
             for v in variants]
    plan = _envelope(bases, timing)
    # The first plan probed the 1 mm variants. It was never granted or run; its forecast stays on record.
    prior = _envelope([{"id": r["reference_id"], "fixture_id": r["fixture"]["fixture_id"],
                        "centers_mm": r["snapped"]["centers_mm"], "rotated": r["snapped"]["rotated"]}
                       for r in references], timing)
    total, forecast, reserved, failed, cap = (plan[k] for k in ("total", "forecast", "reserved", "failed", "cap"))
    return {
        "schema": "sentilab-envelope-plan-v2",
        "ticket": TICKET,
        "kind": "SAMPLED sensitivity envelope, not a bound",
        "role": ("ENGINEERING comparison and sensitivity: a separately admitted experiment, never a paper match. "
                 "Nothing here is part of gate zero. These calls are never appended to any other job, the gate-zero "
                 "job included; gate zero (the accepted 8+4 allocation) uses the two original raw 45 mm references."),
        "status": ("PLAN ONLY. No solve has been run for SLAB-048. Every call below waits for a named warden grant "
                   "that lists these exact calls, a CPU cap, an expiry and the prior charges it keeps."),
        "labels": [*LABELS, "sampled envelope: finite probes, not a bound on reconstruction error",
                   "engineering comparison and sensitivity, not a paper match"],
        "design": ("For each reference: its 0.5 mm engineering variant (snap0p5), plus each die moved by +0.5 and by "
                   "-0.5 mm in x, and separately in y. Moves the fixture gate rejects are listed under 'excluded' and "
                   "are not run. Every call id names its snap0p5 base, so no call can be mistaken for raw."),
        "limits": [
            "A raw layout inside the base's +/-0.5 mm per-coordinate box is not thereby a sampled point of this "
            "one-axis stencil.",
            "Finite sensitivity probes do not prove a uniform reconstruction bound.",
        ],
        "grid": ENVELOPE_GRID,
        "perturbation_mm": PERTURBATION_MM,
        "expected_call_count": total,
        "references": plan["plans"],
        "superseded": {
            "what": "the first plan, which probed the 1 mm snapped variants",
            "status": "superseded before any grant (astra #56857, warden review P2); never granted, never run",
            "expected_call_count": prior["total"],
            "forecast_cpu_s": round(prior["forecast"], 3),
            "proposed_cap_cpu_s": round(prior["cap"], 3),
            "qualifier": "forecasts with the same derivation as below; not measured guarantees",
        },
        "sizing": {
            "basis": "measured grid-64 wall time on the recorded Azure x86_64 host; a forecast, not a bound",
            "host": timing["host"],
            "sources": {_rel(path): _sha256(path) for path in (TIMING, MESH_ASCEND, MESH_MICRO_ROWS, SLAB039, POLICY)},
            "median_solve_wall_s_64x64": timing["median_64_s"],
            "mesh_grid64_evaluation_wall_s": {k: {"n": v["n"], "median_s": round(v["median_s"], 6),
                                                  "max_s": round(v["max_s"], 6)} for k, v in timing["mesh_64"].items()},
            "worst_observed_grid64_call_s": round(timing["worst_64_s"], 6),
            "lifecycle_overhead_heuristic_cpu_s_per_call": {
                "value": round(timing["overhead_s"], 6),
                "kind": ("heuristic: an aggregate CPU mean minus a different workload's wall median; it cannot "
                         "isolate lifecycle overhead"),
                "derivation": (f"SLAB-039: {timing['slab039_per_call_cpu_s']:.6f} CPU-s per call (getrusage, fresh "
                               f"worker reaped every call, grid 32) minus the {timing['grid32_median_s']:.6f} s "
                               f"grid-32 median solve wall time from TIMING.json; the SLAB-039 host is not recorded")},
            "reserves_cpu_s_per_call": {"startup": STARTUP_RESERVE_S, "reap": timing["reap_s"],
                                        "archive_raw_outputs": ARCHIVE_RESERVE_S},
            "failed_attempt_reserve": {"fraction_of_calls": FAILED_ATTEMPT_FRACTION,
                                       "calls": math.ceil(FAILED_ATTEMPT_FRACTION * total),
                                       "cpu_s": round(failed, 3), "each_at": "worst observed call plus reserves"},
            "settlement_tail_cpu_s": timing["tail_s"],
            "forecast_cpu_s": round(forecast, 3),
            "forecast_cpu_min": round(forecast / 60, 3),
            "reserved_cpu_s": round(reserved, 3),
            "proposed_cap_cpu_s": round(cap, 3),
            "proposed_cap_cpu_min": round(cap / 60, 3),
            "formula": ("forecast = sum(median solve + heuristic overhead); reserved = sum(median solve + startup + "
                        "reap + archive); cap = reserved + failed-attempt reserve + one worst-case call of stop "
                        "headroom + settlement tail. Every figure here is a forecast, not a measured guarantee."),
            "assumption": ("The 45 mm frame keeps the 64x64 grid, so solve time is assumed equal to the measured "
                           "50 mm grid-64 time; HotSpot is single-threaded, so CPU is close to wall at one CPU."),
        },
        "grant": {"status": "awaiting a named warden grant", "granted_by": None, "grant_id": None, "expiry": None,
                  "prior_charges_kept": None,
                  "slab048_prior_solves": 0},
        "execution_rules": [
            "Run exactly the listed calls on the named 45 mm fixtures at grid 64; refuse any design whose hash is "
            "not listed, and refuse a fixture whose config sha256 differs.",
            "Admit this as its own job: never append these calls to any other job, the gate-zero job included.",
            "One fresh worker per call, reaped after the call; serial at one CPU.",
            "Before each call, stop if cumulative CPU plus one worst-case call would pass the granted cap.",
            "Keep raw outputs and every incomplete or failed outcome; never rerun a completed call.",
            "Report J per call against the base call: a sampled envelope, not a bound.",
        ],
    }


def build_all() -> dict[Path, bytes]:
    decode = json.loads(DECODE.read_text(encoding="utf-8"))
    references = [build_reference(spec, decode) for spec in REFERENCES]
    outputs = {REFERENCES_DIR / f"{ref['reference_id']}.json": _json_bytes(ref) for ref in references}
    variants = [build_variant(ref, decode) for ref in references]
    outputs.update({REFERENCES_DIR / f"{v['variant_id']}.json": _json_bytes(v) for v in variants})
    outputs[ENVELOPE_PLAN] = _json_bytes(build_envelope_plan(references, variants))
    return outputs


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    outputs = build_all()
    if args.write:
        for path, data in outputs.items():
            path.write_bytes(data)
            print(f"wrote {_rel(path)} {hashlib.sha256(data).hexdigest()}")
        return 0
    stale = [_rel(path) for path, data in outputs.items() if not path.is_file() or path.read_bytes() != data]
    for name in stale:
        print(f"stale: {name}", file=sys.stderr)
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
