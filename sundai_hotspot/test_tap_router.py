"""SLAB-048: TAP-2.5D's router on HiGHS reproduces the routed wirelength the paper publishes.

Geometry only: a MILP over pin-clump flows, no thermal solve. The check_* functions take a module
bundle so test_slab048_mutations.py can require them to fail on a mutated router.
"""
from __future__ import annotations

import json
import types
import unittest

from sundai_hotspot import tap_references
from sundai_hotspot import tap_router as real_tap_router
from sundai_hotspot.tap_oracle import TapGeometry

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


def check_round_trip_wire_on_the_raw_references(mods):
    """Room #56739 (b)2: routed wire on each raw reference within 2% of the paper's."""
    for label, problem, centers, rotated, link, paper in _published_layouts():
        if label.endswith("(a)"):
            routed = mods.tap_router.routed_wirelength(problem, centers, rotated, link_type=link).total_mm
            assert abs(routed - paper) / paper <= 0.02, (label, routed, paper)


class RouterTests(unittest.TestCase):
    def test_reproduces_every_published_routed_wirelength(self):
        layouts = list(_published_layouts())
        self.assertEqual(len(layouts), 7)  # Fig. 6 (a)-(c), Fig. 5 (a)-(d)
        for label, problem, centers, rotated, link, paper in layouts:
            with self.subTest(panel=label):
                result = real_tap_router.routed_wirelength(problem, centers, rotated, link_type=link)
                self.assertLessEqual(abs(result.total_mm - paper) / paper, 0.002, (result.total_mm, paper))
                self.assertEqual(result.link_type, link)

    def test_round_trip_wire_on_the_raw_references(self):
        check_round_trip_wire_on_the_raw_references(REAL)

    def test_wire_count_matches_taps_directed_nets(self):
        problem = TapGeometry.load("ascend910-45mm").problem
        layout = next(item for item in _published_layouts() if item[0] == "fig6(a)")
        result = real_tap_router.routed_wirelength(problem, layout[2], layout[3])
        self.assertEqual(result.wires, 2 * (200 + 4 * 256))  # each link is routed in both directions

    def test_turned_dies_route_from_their_turned_edges(self):
        label, problem, centers, rotated, link, paper = next(
            item for item in _published_layouts() if item[0] == "fig6(a)")
        unturned = real_tap_router.routed_wirelength(problem, centers, [False] * len(rotated), link_type=link)
        self.assertGreater(abs(unturned.total_mm - paper) / paper, 0.02)


if __name__ == "__main__":
    unittest.main()
