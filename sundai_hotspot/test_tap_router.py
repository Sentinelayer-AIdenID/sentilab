"""SLAB-048: TAP-2.5D's router on HiGHS lands within 0.1% of every routed wirelength the paper publishes.

Geometry only: a MILP over pin-clump flows, no thermal solve. The check_* functions take a module
bundle so test_slab048_mutations.py can require them to fail on a mutated router.
"""
from __future__ import annotations

import json
import re
import types
import unittest
from unittest import mock

from sundai_hotspot import tap_references
from sundai_hotspot import tap_router as real_tap_router
from sundai_hotspot.tap_oracle import REPO_ROOT, TapGeometry

REAL = types.SimpleNamespace(tap_router=real_tap_router)


def _published_layouts():
    """Every panel with a published routed wirelength: (label, problem, centres, rotated, link, paper mm)."""
    decode = json.loads(tap_references.DECODE.read_text(encoding="utf-8"))
    for spec in tap_references.REFERENCES:
        problem = TapGeometry.load(spec["fixture_id"]).problem
        figure = decode["figures"][spec["figure"]]
        for point in (spec["paper_reported"]["original"], *spec["validation_points"]):
            chiplets = figure["panels"][point["panel"]]["chiplets"]
            centers = [c["decoded_center_mm"] for c in chiplets]
            if point["panel"] != spec["panel"]:  # TAP's placer output: back onto its 1 mm grid
                centers = [[float(round(v)) for v in c] for c in centers]
            yield (f"{spec['figure']}({point['panel']})", problem, centers,
                   [c["rotated_vs_catalog"] for c in chiplets], point["link_type"], point["routed_wirelength_mm"])


def _raw_ascend():
    return next(item for item in _published_layouts() if item[0] == "fig6(a)")


def check_round_trip_wire_on_the_raw_references(mods):
    """Room #56739 (b)2: routed wire on each raw reference within 2% of the paper's."""
    for label, problem, centers, rotated, link, paper in _published_layouts():
        if label.endswith("(a)"):
            routed = mods.tap_router.routed_wirelength(problem, centers, rotated, link_type=link).total_mm
            assert abs(routed - paper) / paper <= 0.02, (label, routed, paper)


def check_router_refuses_any_solve_that_is_not_a_proven_optimum(mods):
    """Time-limited (with or without an incumbent), infeasible, unbounded or failed: never a number."""
    _, problem, centers, rotated, link, _ = _raw_ascend()
    for status, fun in ((1, 16500.0), (1, None), (2, None), (3, None), (4, 16417.5)):
        outcome = types.SimpleNamespace(status=status, fun=fun, message=f"stand-in status {status}")
        with mock.patch.object(mods.tap_router, "milp", return_value=outcome):
            try:
                result = mods.tap_router.routed_wirelength(problem, centers, rotated, link_type=link)
            except RuntimeError:
                continue
        raise AssertionError(f"router returned {result} for solver status {status}")


def check_router_refuses_malformed_inputs(mods):
    _, problem, centers, rotated, link, _ = _raw_ascend()
    bad = {
        "one centre short": (centers[:-1], rotated, link),
        "one centre extra": (centers + [[20.0, 20.0]], rotated, link),
        "one flag short": (centers, rotated[:-1], link),
        "integer flags": (centers, [int(flag) for flag in rotated], link),
        "string flag": (centers, ["yes"] + list(rotated[1:]), link),
        "three coordinates": ([[1.0, 2.0, 3.0]] + list(centers[1:]), rotated, link),
        "boolean coordinate": ([[True, 2.0]] + list(centers[1:]), rotated, link),
        "not finite": ([[float("nan"), 2.0]] + list(centers[1:]), rotated, link),
        "unknown link": (centers, rotated, "optical"),
    }
    for case, (bad_centers, bad_rotated, bad_link) in bad.items():
        try:
            mods.tap_router.routed_wirelength(problem, bad_centers, bad_rotated, link_type=bad_link)
        except ValueError:
            continue
        except Exception as exc:  # crashing deeper in is not a refusal
            raise AssertionError(f"{case}: {type(exc).__name__} instead of a ValueError refusal") from exc
        raise AssertionError(f"router accepted malformed input: {case}")


class RouterTests(unittest.TestCase):
    def test_within_0p1_percent_of_every_published_routed_wirelength(self):
        layouts = list(_published_layouts())
        self.assertEqual(len(layouts), 7)  # Fig. 6 (a)-(c), Fig. 5 (a)-(d)
        for label, problem, centers, rotated, link, paper in layouts:
            with self.subTest(panel=label):
                result = real_tap_router.routed_wirelength(problem, centers, rotated, link_type=link)
                self.assertLessEqual(abs(result.total_mm - paper) / paper, 0.001, (result.total_mm, paper))
                self.assertEqual(result.link_type, link)

    def test_round_trip_wire_on_the_raw_references(self):
        check_round_trip_wire_on_the_raw_references(REAL)

    def test_refuses_any_solve_that_is_not_a_proven_optimum(self):
        check_router_refuses_any_solve_that_is_not_a_proven_optimum(REAL)

    def test_refuses_malformed_inputs(self):
        check_router_refuses_malformed_inputs(REAL)

    def test_solver_versions_are_the_pinned_ones(self):
        pin = re.search(r"^scipy==(\S+)$", (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8"), re.M)
        versions = real_tap_router.solver_versions()
        self.assertEqual(versions["scipy"], pin.group(1))
        self.assertRegex(versions["highs"], r"^\d+\.\d+\.\d+$")
        self.assertEqual(tap_references.pinned_solver(), {**versions, "pinned_by": "requirements.txt"})

    def test_wire_count_matches_taps_directed_nets(self):
        _, problem, centers, rotated, _, _ = _raw_ascend()
        result = real_tap_router.routed_wirelength(problem, centers, rotated)
        self.assertEqual(result.wires, 2 * (200 + 4 * 256))  # each link is routed in both directions

    def test_turned_dies_route_from_their_turned_edges(self):
        label, problem, centers, rotated, link, paper = _raw_ascend()
        unturned = real_tap_router.routed_wirelength(problem, centers, [False] * len(rotated), link_type=link)
        self.assertGreater(abs(unturned.total_mm - paper) / paper, 0.02)

    def test_routed_wire_is_unchanged_by_a_common_translation(self):
        # Why wire agreement is consistency evidence and cannot identify absolute coordinates.
        _, problem, centers, rotated, link, _ = _raw_ascend()
        shifted = [[x + 1.0, y - 1.0] for x, y in centers]
        first = real_tap_router.routed_wirelength(problem, centers, rotated, link_type=link).total_mm
        moved = real_tap_router.routed_wirelength(problem, shifted, rotated, link_type=link).total_mm
        self.assertAlmostEqual(first, moved, places=6)


if __name__ == "__main__":
    unittest.main()
