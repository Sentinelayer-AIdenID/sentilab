"""SLAB-048: a die turned 90 degrees about its centre, in the placement model and the search moves.

The check_* functions take a module bundle so test_slab048_mutations.py can rerun them against a
mutated module and require that they fail. No solver is involved.
"""
from __future__ import annotations

import random
import types
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sundai_controller import controller as real_controller
from sundai_controller import experiment as real_experiment
from sundai_hotspot.tap_oracle import TapGeometry

REAL = types.SimpleNamespace(controller=real_controller, experiment=real_experiment)
# Widely spaced micro150 layout on the 45 mm frame: every CPU has room to turn.
SPREAD_MICRO150 = ((8, 8), (37, 8), (37, 37), (8, 37), (22, 8), (37, 22), (22, 37), (8, 22))
# The legal snapped Ascend 910 variant (docs/sentilab/references): packed, so no single turn fits.
SNAPPED_ASCEND = ((17, 23), (39, 23), (7, 11), (21, 11), (7, 35), (21, 35))
SNAPPED_ASCEND_ROTATED = (True, False, True, True, True, True)


def _hbm_and_dram(controller):
    return controller.Design(45.0, 45.0, 0.0,
                             (controller.Chiplet("hbm", 7.75, 11.87), controller.Chiplet("dram", 8.75, 8.75)),
                             ((10.0 - 7.75 / 2, 20.0 - 11.87 / 2), (30.0, 30.0)))


def check_rotate_swaps_footprint(mods):
    turned = _hbm_and_dram(mods.controller).apply("rotate", {"chiplet": "hbm"})
    footprint = (turned.chiplets[0].width_mm, turned.chiplets[0].height_mm)
    assert footprint == (11.87, 7.75), footprint
    assert turned.chiplets[1] == _hbm_and_dram(mods.controller).chiplets[1]


def check_rotate_keeps_centre(mods):
    design = _hbm_and_dram(mods.controller)
    for layout in (design, design.apply("rotate", {"chiplet": "hbm"}),
                   design.apply("rotate", {"chiplet": "hbm"}).apply("rotate", {"chiplet": "hbm"})):
        chiplet, (x, y) = layout.chiplets[0], layout.positions[0]
        centre = (x + chiplet.width_mm / 2, y + chiplet.height_mm / 2)
        assert abs(centre[0] - 10.0) < 1e-9 and abs(centre[1] - 20.0) < 1e-9, centre


def check_square_die_has_one_orientation(mods):
    try:
        _hbm_and_dram(mods.controller).apply("rotate", {"chiplet": "dram"})
    except mods.controller.DesignValidationError as exc:
        assert "square" in str(exc), exc
        return
    raise AssertionError("a square die was turned, which only spends a solve on the same layout")


def check_rotate_operator_turns_one_die(mods):
    geometry = TapGeometry.load("micro150-45mm")
    parent = geometry.design_from_centers(SPREAD_MICRO150)
    candidate, operation, args = mods.experiment._candidate(parent, "rotate", random.Random(7), geometry)
    assert operation == "rotate", (operation, args)
    turned = geometry.rotated(candidate)
    assert sum(turned) == 1 and turned.index(True) < 4, turned  # only CPUs are non-square
    assert geometry.centers_for(candidate) == geometry.centers_for(parent)  # turned in place


class DesignRotationTests(unittest.TestCase):
    def test_rotate_swaps_the_footprint(self):
        check_rotate_swaps_footprint(REAL)

    def test_rotate_keeps_the_centre_and_twice_is_identity(self):
        check_rotate_keeps_centre(REAL)
        design = _hbm_and_dram(real_controller)
        twice = design.apply("rotate", {"chiplet": "hbm"}).apply("rotate", {"chiplet": "hbm"})
        self.assertEqual(twice.chiplets, design.chiplets)

    def test_square_die_has_one_orientation(self):
        check_square_die_has_one_orientation(REAL)

    def test_rotate_arguments_are_allowlisted(self):
        design = _hbm_and_dram(real_controller)
        with self.assertRaises(KeyError):
            design.apply("rotate", {"chiplet": "missing"})
        for args in ({}, {"chiplet": "hbm", "angle": 90}):
            with self.subTest(args=args), self.assertRaisesRegex(ValueError, "not allowlisted"):
                design.apply("rotate", args)

    def test_turned_footprint_is_checked_against_the_substrate(self):
        # Turning a die whose turned footprint leaves the substrate is refused by Design.check.
        design = real_controller.Design(12.0, 30.0, 0.0, (real_controller.Chiplet("long", 10.0, 20.0),), ((1.0, 5.0),))
        with self.assertRaisesRegex(ValueError, "outside substrate"):
            design.apply("rotate", {"chiplet": "long"})


class ControllerRotationTests(unittest.IsolatedAsyncioTestCase):
    async def run_rotate(self, fixture):
        geometry = TapGeometry.load(fixture)
        seen = []

        async def oracle(candidate):
            seen.append(candidate)
            # Deliberately nonphysical: a turned die "improves", so the controller commits it.
            return real_controller.ThermalResult(candidate.hash, 100.0 - sum(geometry.rotated(candidate)),
                                                 "NONPHYSICAL-rotation-test")

        controller = real_controller.Controller(geometry.design_from_centers(SPREAD_MICRO150), oracle,
                                                evaluation_ceiling_microdollars=1, max_oracle_calls=4,
                                                pre_admission_check=geometry.centers_for)
        key = Ed25519PrivateKey.generate()
        controller.register("agent", key)
        await controller.initialize()
        task = controller.mint_task("agent")
        outcome = await controller.submit(controller.proposal("agent", key, task, "rotate",
                                                              {"chiplet": "tap-chiplet-0"}))
        return geometry, outcome, seen

    async def test_signed_rotate_proposal_reaches_the_oracle_turned(self):
        geometry, outcome, seen = await self.run_rotate("micro150-45mm")
        self.assertEqual(outcome.status, "committed", outcome.reason)
        self.assertEqual(geometry.rotated(seen[-1]), (True,) + (False,) * 7)
        self.assertEqual(geometry.centers_for(seen[-1])[0], (8.0, 8.0))

    async def test_50mm_fixture_keeps_catalog_orientation_and_refuses_before_the_oracle(self):
        geometry, outcome, seen = await self.run_rotate("micro150")
        self.assertEqual(outcome.status, "rejected")
        self.assertEqual(outcome.reason, "TAP fixture chiplet catalog mismatch")
        self.assertEqual(len(seen), 1)  # the initial layout only


class RotateOperatorTests(unittest.TestCase):
    def test_rotate_operator_turns_one_die_in_place(self):
        check_rotate_operator_turns_one_die(REAL)

    def test_rotate_operator_falls_back_to_a_legal_noop_when_no_turn_fits(self):
        geometry = TapGeometry.load("ascend910-45mm")
        parent = geometry.design_from_centers(SNAPPED_ASCEND, SNAPPED_ASCEND_ROTATED)
        candidate, operation, _ = real_experiment._candidate(parent, "rotate", random.Random(7), geometry)
        self.assertEqual(operation, "place")
        self.assertEqual(candidate.hash, parent.hash)

    def test_frozen_lanes_keep_their_three_operators(self):
        # Adding rotate to a frozen lane would change its RNG draws; protocols opt in explicitly.
        self.assertEqual(real_experiment.OPERATORS, ("local_move", "swap", "global_resample"))
        self.assertEqual(real_experiment.ROTATE_OPERATOR, "rotate")


if __name__ == "__main__":
    unittest.main()
