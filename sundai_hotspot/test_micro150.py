"""Tests for micro150 fixture wiring and cross-fixture identity."""
from __future__ import annotations

import hashlib
import math
import unittest

from tap_oracle import (
    TAP_CONFIG_DEFAULT_ID,
    TAP_CONFIGS,
    HotSpotOracle,
    TapLegalityError,
)

BASE_CENTERS = ((25, 25), (40, 40), (8, 9), (8, 25), (8, 41), (41, 15))


class DefaultAscend910UnchangedTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.oracle = HotSpotOracle(16, 16)

    async def asyncTearDown(self):
        await self.oracle.aclose()

    async def test_default_fixture_is_ascend910_and_peak_unchanged(self):
        design = self.oracle.design_from_centers(BASE_CENTERS)
        result = await self.oracle(design)
        self.assertEqual(self.oracle.fixture_id, "ascend910")
        self.assertEqual(result.fixture_id, "ascend910")
        self.assertEqual(result.config_sha256, self.oracle.problem.config_sha256)
        self.assertAlmostEqual(result.maximum_temperature_c, 118.36, delta=0.01)

    async def test_default_problem_hash_is_stable_for_fixed_config(self):
        """Matches a value captured before micro150 wiring on base 8e73598."""
        self.assertEqual(self.oracle.problem_hash,
                         "5b48b67e8f245f3c7a63941b44da0860612daec6689ba29e171e73d86168b050")


class FixtureIdentityTests(unittest.TestCase):
    def test_default_config_id_and_path(self):
        self.assertEqual(TAP_CONFIG_DEFAULT_ID, "ascend910")
        self.assertTrue(TAP_CONFIGS["ascend910"].name.endswith("sys_ascend910.cfg"))

    def test_ascend910_config_sha_is_unchanged(self):
        expected = "548562a5f49d502f4b9bd03d3a4acc4b42f225056e6d91556416079c291e06d4"
        self.assertEqual(hashlib.sha256(TAP_CONFIGS["ascend910"].read_bytes()).hexdigest(), expected)


class Micro150OracleTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.oracle = HotSpotOracle(32, 32, fixture="micro150")

    async def asyncTearDown(self):
        await self.oracle.aclose()

    def test_eight_chiplets_with_total_power_680_w(self):
        self.assertEqual(self.oracle.problem.fixture_id, "micro150")
        self.assertEqual(len(self.oracle.problem.widths_mm), 8)
        self.assertEqual(len(self.oracle.problem.heights_mm), 8)
        self.assertEqual(len(self.oracle.problem.powers_w), 8)
        self.assertEqual(sum(self.oracle.problem.powers_w), 680.0)
        self.assertEqual(sum(self.oracle.problem.powers_w[:4]), 600.0)
        self.assertEqual(sum(self.oracle.problem.powers_w[4:]), 80.0)

    async def test_legal_micro150_layout_evaluates(self):
        centers = (
            (10, 10), (28, 10), (10, 28), (28, 28),
            (10, 42), (28, 42), (42, 10), (42, 28),
        )
        design = self.oracle.design_from_centers(centers)
        result = await self.oracle(design)
        self.assertEqual(result.fixture_id, "micro150")
        self.assertTrue(result.evaluator_version.endswith(":grid:32x32"))
        self.assertIn("config_sha256:", result.evaluator_version)
        self.assertIn(result.config_sha256, result.evaluator_version)
        self.assertGreater(result.maximum_temperature_c, 100.0)
        self.assertTrue(math.isfinite(result.wirelength_mm))

    async def test_overlapping_micro150_layout_raises(self):
        centers = (
            (10, 10), (10, 10), (10, 28), (28, 28),
            (10, 42), (28, 42), (42, 10), (42, 28),
        )
        design = self.oracle.design_from_centers(centers)
        with self.assertRaisesRegex(TapLegalityError, "overlap"):
            await self.oracle(design)


if __name__ == "__main__":
    unittest.main()
