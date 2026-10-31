"""Tests for SLAB-039 headroom runner."""
import json
import math
import os
import signal
import statistics
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sundai_controller.headroom import (
    _gate_pass,
    _gate_pass_dynamic,
    _parse_prereg,
    _choose_ucb1,
    run_headroom,
)
from controller import Chiplet, Design, ThermalResult


class CountingOracle:
    """Fast test oracle that returns temperature = sum of positions."""
    def __init__(self, grid_rows=32, grid_cols=32, **kwargs):
        self.calls = []
        self._closed = False

    def design_from_centers(self, centers):
        """Build a Design matching the TAP centers (mocked for tests)."""
        from controller import Chiplet, Design
        chiplets = tuple(Chiplet(f"tap-chiplet-{i}", 2.0, 2.0) for i in range(len(centers)))
        positions = tuple((float(x) - 1.0, float(y) - 1.0) for x, y in centers)
        return Design(50.0, 50.0, 0.0, chiplets, positions)

    async def aclose(self):
        self._closed = True

    async def __call__(self, candidate):
        self.calls.append(candidate.hash)
        temperature = float(sum(x + y for x, y in candidate.positions))
        return ThermalResult(candidate.hash, temperature, "NONPHYSICAL-test",
                             problem_hash="same-problem-for-all-lanes")


class GateFunctionTests(unittest.TestCase):
    """Test the gate function on hand-built inputs."""

    def test_pass_when_gap_exceeds_threshold(self):
        passed, gap = _gate_pass(120.0, 119.5, 0.02, k=5)
        self.assertTrue(passed)
        self.assertAlmostEqual(gap, 0.5)

    def test_fail_when_gap_below_threshold(self):
        passed, gap = _gate_pass(118.1, 117.84, 0.1, k=5)
        self.assertFalse(passed)
        self.assertAlmostEqual(gap, 0.26)

    def test_exactly_at_threshold(self):
        passed, gap = _gate_pass(118.0, 117.5, 0.1, k=5)
        self.assertTrue(passed)
        self.assertAlmostEqual(gap, 0.5)

    def test_cheap_median_lower_than_best_negative_gap(self):
        passed, gap = _gate_pass(117.5, 118.0, 0.1, k=5)
        self.assertFalse(passed)
        self.assertLess(gap, 0)

    def test_zero_mesh_error_any_positive_gap_passes(self):
        passed, gap = _gate_pass(118.0, 117.99, 0.0, k=5)
        self.assertTrue(passed)

    def test_large_gap_passes_easily(self):
        passed, gap = _gate_pass(130.0, 100.0, 1.0, k=5)
        self.assertTrue(passed)
        self.assertAlmostEqual(gap, 30.0)


class GatePassDynamicTests(unittest.TestCase):
    """Test dynamic mesh error gate (max|J32-J64|)."""

    def test_pass_dynamic(self):
        j32 = [118.0, 118.1]
        j64 = [118.05, 118.15]
        passed, gap, mesh = _gate_pass_dynamic(118.5, 118.0, j32, j64, k=5)
        self.assertTrue(passed)
        self.assertAlmostEqual(mesh, 0.05)

    def test_fail_dynamic(self):
        j32 = [118.0, 118.1]
        j64 = [118.3, 118.4]
        passed, gap, mesh = _gate_pass_dynamic(118.2, 118.0, j32, j64, k=5)
        self.assertFalse(passed)

    def test_dynamic_empty_raises(self):
        with self.assertRaises(ValueError):
            _gate_pass_dynamic(118.0, 117.0, [], [1.0], k=5)
        with self.assertRaises(ValueError):
            _gate_pass_dynamic(118.0, 117.0, [1.0], [], k=5)

    def test_dynamic_mismatched_lengths(self):
        j32 = [118.0, 118.1]
        j64 = [118.05]
        with self.assertRaises(ValueError):
            _gate_pass_dynamic(118.5, 118.0, j32, j64, k=5)


class ParsePreregTests(unittest.TestCase):
    """Test prereg JSON parsing."""

    def test_valid_prereg(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "schema": "slab-039-prereg-v1",
                "fixture": "ascend910",
                "grid": 32,
                "rule": {"k": 5},
                "cheap_methods": {
                    "methods": ["random", "simulated_annealing", "ucb1"],
                    "evaluations_per_method": 32,
                    "seeds": [0, 1, 2, 3, 4, 5, 6, 7],
                    "seed_count": 8,
                },
                "long_sa": {
                    "restarts": 4,
                    "max_evaluations_per_restart": 1500,
                    "max_cpu_minutes": 90,
                    "seeds": [100, 101, 102, 103],
                },
            }, f)
            f.close()
        try:
            prereg = _parse_prereg(f.name)
            self.assertEqual(prereg["schema"], "slab-039-prereg-v1")
            self.assertEqual(prereg["fixture"], "ascend910")
            self.assertEqual(prereg["grid"], 32)
            self.assertEqual(prereg["rule"]["k"], 5)
        finally:
            os.unlink(f.name)

    def test_valid_prereg_v2(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "schema": "slab-039-prereg-v2",
                "fixture": "ascend910",
                "grid": 32,
                "rule": {"k": 5},
                "cheap_methods": {
                    "methods": ["random", "simulated_annealing", "ucb1", "signal_portfolio"],
                    "search_evaluations_per_method": 28,
                    "reproduction_evaluations_per_method": 4,
                    "total_evaluations_per_method": 32,
                    "seeds": [0, 1, 2, 3, 4, 5, 6, 7],
                    "seed_count": 8,
                },
                "long_sa": {
                    "restarts": 4,
                    "max_evaluations_per_restart": 1500,
                    "max_cpu_minutes": 50,
                    "seeds": [100, 101, 102, 103],
                },
                "allocation": {
                    "headroom_cpu_minutes": 50,
                    "aggregate_cpu_minutes": 60,
                },
            }, f)
            f.close()
        try:
            prereg = _parse_prereg(f.name)
            self.assertEqual(prereg["schema"], "slab-039-prereg-v2")
            self.assertEqual(prereg["fixture"], "ascend910")
            self.assertEqual(prereg["long_sa"]["max_cpu_minutes"], 50)
            self.assertIn("signal_portfolio", prereg["cheap_methods"]["methods"])
            self.assertEqual(prereg["cheap_methods"]["search_evaluations_per_method"], 28)
            self.assertEqual(prereg["cheap_methods"]["reproduction_evaluations_per_method"], 4)
        finally:
            os.unlink(f.name)

    def test_invalid_schema(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"schema": "wrong", "fixture": "ascend910", "rule": {"k": 5}}, f)
            f.close()
        try:
            with self.assertRaises(ValueError):
                _parse_prereg(f.name)
        finally:
            os.unlink(f.name)

    def test_invalid_fixture(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "schema": "slab-039-prereg-v1",
                "fixture": "plate",
                "rule": {"k": 5},
            }, f)
            f.close()
        try:
            with self.assertRaises(ValueError):
                _parse_prereg(f.name)
        finally:
            os.unlink(f.name)

    def test_invalid_k(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "schema": "slab-039-prereg-v1",
                "fixture": "ascend910",
                "rule": {"k": 3},
            }, f)
            f.close()
        try:
            with self.assertRaises(ValueError):
                _parse_prereg(f.name)
        finally:
            os.unlink(f.name)

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            _parse_prereg("/nonexistent/path/prereg.json")


class Ucb1ChoiceTests(unittest.TestCase):
    """Tests for UCB1 operator selection."""

    def test_untried_chosen_first(self):
        import random
        rng = random.Random(42)
        counts = {"local_move": 0, "swap": 0, "global_resample": 1}
        rewards = {"local_move": 0.0, "swap": 0.0, "global_resample": 1.0}
        choice = _choose_ucb1(counts, rewards, rng)
        self.assertIn(choice, ("local_move", "swap"))

    def test_all_tried_uses_ucb1_scores(self):
        import random
        rng = random.Random(42)
        counts = {"local_move": 10, "swap": 5, "global_resample": 2}
        rewards = {"local_move": 5.0, "swap": 3.0, "global_resample": 2.0}
        choice = _choose_ucb1(counts, rewards, rng)
        self.assertIn(choice, ("local_move", "swap", "global_resample"))


class HeadroomRunnerTests(unittest.IsolatedAsyncioTestCase):
    """Integration-style tests for the headroom runner."""

    async def test_run_headroom_with_counting_oracle(self):
        """Run a tiny headroom experiment (2 seeds x 4 evals) with a counting oracle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prereg_path = Path(tmpdir) / "PREREG.json"
            prereg = {
                "schema": "slab-039-prereg-v1",
                "fixture": "ascend910",
                "grid": 32,
                "rule": {"k": 5},
                "cheap_methods": {
                    "methods": ["random", "simulated_annealing", "ucb1"],
                    "evaluations_per_method": 4,
                    "seeds": [0, 1],
                    "seed_count": 2,
                },
                "long_sa": {
                    "restarts": 1,
                    "max_evaluations_per_restart": 8,
                    "max_cpu_minutes": 1,
                    "seeds": [100],
                },
            }
            prereg_path.write_text(json.dumps(prereg), encoding="utf-8")
            out_dir = Path(tmpdir) / "out"

            with patch("sundai_hotspot.tap_oracle.HotSpotOracle", CountingOracle):
                result = await run_headroom(
                    fixture="ascend910",
                    mesh_error=0.1,
                    prereg_path=prereg_path,
                    output_dir=out_dir,
                )

            self.assertIn("verdict", result)
            self.assertIn("cheap_median_c", result)
            self.assertIn("best_c", result)
            self.assertIn("gap_c", result)
            self.assertIn("passed", result)
            self.assertEqual(len(result["cheap_results"]), 3 * 2)
            self.assertEqual(len(result["long_sa_results"]), 1)

            self.assertTrue((out_dir / "RESULT.json").is_file())
            self.assertTrue((out_dir / "REPORT.md").is_file())

    async def test_headroom_verdict_is_plain(self):
        """The verdict is stated plainly as PASS or FAIL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prereg_path = Path(tmpdir) / "PREREG.json"
            prereg = {
                "schema": "slab-039-prereg-v1",
                "fixture": "ascend910",
                "grid": 32,
                "rule": {"k": 5},
                "cheap_methods": {
                    "methods": ["random"],
                    "evaluations_per_method": 2,
                    "seeds": [0],
                    "seed_count": 1,
                },
                "long_sa": {
                    "restarts": 1,
                    "max_evaluations_per_restart": 4,
                    "max_cpu_minutes": 1,
                    "seeds": [100],
                },
            }
            prereg_path.write_text(json.dumps(prereg), encoding="utf-8")
            out_dir = Path(tmpdir) / "out"

            with patch("sundai_hotspot.tap_oracle.HotSpotOracle", CountingOracle):
                result = await run_headroom(
                    fixture="ascend910",
                    mesh_error=0.1,
                    prereg_path=prereg_path,
                    output_dir=out_dir,
                )

            self.assertIn(result["verdict"], ("PASS", "FAIL"))
            self.assertIsInstance(result["passed"], bool)

    async def test_cpu_cap_enforced_in_long_sa(self):
        """The CPU cap is enforced in the long SA runner function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prereg_path = Path(tmpdir) / "PREREG.json"
            prereg = {
                "schema": "slab-039-prereg-v2",
                "fixture": "ascend910",
                "grid": 32,
                "rule": {"k": 5},
                "cheap_methods": {
                    "methods": ["random"],
                    "search_evaluations_per_method": 2,
                    "reproduction_evaluations_per_method": 0,
                    "total_evaluations_per_method": 2,
                    "seeds": [0],
                    "seed_count": 1,
                },
                "long_sa": {
                    "restarts": 1,
                    "max_evaluations_per_restart": 100,
                    "max_cpu_minutes": 0,
                    "seeds": [100],
                },
            }
            prereg_path.write_text(json.dumps(prereg), encoding="utf-8")
            out_dir = Path(tmpdir) / "out"

            with patch("sundai_hotspot.tap_oracle.HotSpotOracle", CountingOracle):
                result = await run_headroom(
                    fixture="ascend910",
                    mesh_error=0.1,
                    prereg_path=prereg_path,
                    output_dir=out_dir,
                )

            sa_result = result["long_sa_results"][0]
            self.assertTrue(sa_result["cpu_exhausted"])

    async def test_evaluation_budget_enforced(self):
        """The evaluation budget is enforced: each cheap lane runs exactly N evaluations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prereg_path = Path(tmpdir) / "PREREG.json"
            prereg = {
                "schema": "slab-039-prereg-v2",
                "fixture": "ascend910",
                "grid": 32,
                "rule": {"k": 5},
                "cheap_methods": {
                    "methods": ["random"],
                    "search_evaluations_per_method": 7,
                    "reproduction_evaluations_per_method": 0,
                    "total_evaluations_per_method": 7,
                    "seeds": [0],
                    "seed_count": 1,
                },
                "long_sa": {
                    "restarts": 1,
                    "max_evaluations_per_restart": 10,
                    "max_cpu_minutes": 1,
                    "seeds": [100],
                },
            }
            prereg_path.write_text(json.dumps(prereg), encoding="utf-8")
            out_dir = Path(tmpdir) / "out"

            with patch("sundai_hotspot.tap_oracle.HotSpotOracle", CountingOracle):
                result = await run_headroom(
                    fixture="ascend910",
                    mesh_error=0.1,
                    prereg_path=prereg_path,
                    output_dir=out_dir,
                )

            cheap = result["cheap_results"][0]
            self.assertEqual(cheap["evaluation_count"], 7)
            self.assertEqual(cheap["evaluation_admissions"], 7)

    async def test_cheap_median_uses_strongest_method_min_median(self):
        """cheap_median = min over methods of per-method median, not average."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prereg_path = Path(tmpdir) / "PREREG.json"
            prereg = {
                "schema": "slab-039-prereg-v2",
                "fixture": "ascend910",
                "grid": 32,
                "rule": {"k": 5},
                "cheap_methods": {
                    "methods": ["random", "simulated_annealing", "ucb1", "signal_portfolio"],
                    "search_evaluations_per_method": 3,
                    "reproduction_evaluations_per_method": 0,
                    "total_evaluations_per_method": 3,
                    "seeds": [10, 11, 12],
                    "seed_count": 3,
                },
                "long_sa": {
                    "restarts": 1,
                    "max_evaluations_per_restart": 6,
                    "max_cpu_minutes": 1,
                    "seeds": [100],
                },
            }
            prereg_path.write_text(json.dumps(prereg), encoding="utf-8")
            out_dir = Path(tmpdir) / "out"

            with patch("sundai_hotspot.tap_oracle.HotSpotOracle", CountingOracle):
                result = await run_headroom(
                    fixture="ascend910",
                    mesh_error=0.1,
                    prereg_path=prereg_path,
                    output_dir=out_dir,
                )

            medians = result["cheap_method_medians_c"]
            self.assertAlmostEqual(result["cheap_median_c"], min(medians.values()))
            avg = statistics.mean(medians.values())
            if max(medians.values()) - min(medians.values()) > 0.01:
                self.assertNotAlmostEqual(result["cheap_median_c"], avg)


if __name__ == "__main__":
    unittest.main()
