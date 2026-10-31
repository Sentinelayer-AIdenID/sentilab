"""Tests for SLAB-039 headroom runner (v3)."""
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
    _validate_mesh_error,
    _compute_prereg_digest,
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

    def test_negative_mesh_error_rejected(self):
        with self.assertRaises(ValueError):
            _gate_pass(118.0, 117.0, -0.1, k=5)

    def test_infinite_mesh_error_rejected(self):
        with self.assertRaises(ValueError):
            _gate_pass(118.0, 117.0, float("inf"), k=5)

    def test_nan_mesh_error_rejected(self):
        with self.assertRaises(ValueError):
            _gate_pass(118.0, 117.0, float("nan"), k=5)


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


class MeshValidationTests(unittest.TestCase):
    """Test mesh error validation."""

    def test_validate_negative_rejected(self):
        with self.assertRaises(ValueError):
            _validate_mesh_error(-0.1)

    def test_validate_inf_rejected(self):
        with self.assertRaises(ValueError):
            _validate_mesh_error(float("inf"))

    def test_validate_nan_rejected(self):
        with self.assertRaises(ValueError):
            _validate_mesh_error(float("nan"))

    def test_validate_none_rejected(self):
        with self.assertRaises(ValueError):
            _validate_mesh_error(None)

    def test_validate_zero_accepted(self):
        _validate_mesh_error(0.0)

    def test_validate_positive_accepted(self):
        _validate_mesh_error(0.16)


class ParsePreregTests(unittest.TestCase):
    """Test prereg JSON parsing."""

    def test_valid_prereg_v1(self):
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
            }, f)
            f.close()
        try:
            prereg = _parse_prereg(f.name)
            self.assertEqual(prereg["schema"], "slab-039-prereg-v2")
        finally:
            os.unlink(f.name)

    def test_valid_prereg_v3(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "schema": "slab-039-prereg-v3",
                "fixture": "ascend910",
                "grid": 32,
                "rule": {"k": 5},
                "reducer_methods": {
                    "methods": ["random", "greedy", "simulated_annealing"],
                    "search_evaluations_per_method": 28,
                    "reproduction_evaluations_per_method": 4,
                    "total_evaluations_per_method": 32,
                    "seeds": [0, 1, 2, 3, 4, 5, 6, 7],
                    "seed_count": 8,
                },
                "extra_diagnostics": {
                    "methods": ["ucb1", "signal_portfolio"],
                },
                "long_sa": {
                    "restarts": 4,
                    "max_evaluations_per_restart": 1000,
                    "max_cpu_minutes": 24,
                    "seeds": [100, 101, 102, 103],
                },
            }, f)
            f.close()
        try:
            prereg = _parse_prereg(f.name)
            self.assertEqual(prereg["schema"], "slab-039-prereg-v3")
        finally:
            os.unlink(f.name)

    def test_invalid_schema(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"schema": "slab-039-prereg-v99", "fixture": "ascend910"}, f)
            f.close()
        try:
            with self.assertRaises(ValueError):
                _parse_prereg(f.name)
        finally:
            os.unlink(f.name)

    def test_invalid_fixture(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"schema": "slab-039-prereg-v1", "fixture": "micro150"}, f)
            f.close()
        try:
            with self.assertRaises(ValueError):
                _parse_prereg(f.name)
        finally:
            os.unlink(f.name)

    def test_invalid_k(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"schema": "slab-039-prereg-v1", "fixture": "ascend910",
                       "rule": {"k": 3}}, f)
            f.close()
        try:
            with self.assertRaises(ValueError):
                _parse_prereg(f.name)
        finally:
            os.unlink(f.name)

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            _parse_prereg("/nonexistent/prereg.json")


class PreregDigestTests(unittest.TestCase):
    """Test prereg file content hashing."""

    def test_digest_is_consistent(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"test": "content"}, f)
            f.close()
        try:
            d1 = _compute_prereg_digest(f.name)
            d2 = _compute_prereg_digest(f.name)
            self.assertEqual(d1, d2)
            self.assertEqual(len(d1), 64)
        finally:
            os.unlink(f.name)

    def test_digest_changes_with_content(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"test": "content1"}, f)
            f.close()
        try:
            d1 = _compute_prereg_digest(f.name)
        finally:
            os.unlink(f.name)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"test": "content2"}, f)
            f.close()
        try:
            d2 = _compute_prereg_digest(f.name)
            self.assertNotEqual(d1, d2)
        finally:
            os.unlink(f.name)


class Ucb1ChoiceTests(unittest.TestCase):
    """Test UCB1 operator selection."""

    def test_untried_chosen_first(self):
        import random
        rng = random.Random(42)
        counts = {"local_move": 0, "swap": 0, "global_resample": 0}
        rewards = {"local_move": 0.0, "swap": 0.0, "global_resample": 0.0}
        op, reason = _choose_ucb1(counts, rewards, 1, rng)
        self.assertIn(op, ("local_move", "swap", "global_resample"))
        self.assertIn("untried", reason)

    def test_all_tried_uses_ucb1_scores(self):
        import random
        rng = random.Random(42)
        counts = {"local_move": 10, "swap": 10, "global_resample": 10}
        rewards = {"local_move": 5.0, "swap": 3.0, "global_resample": 1.0}
        op, reason = _choose_ucb1(counts, rewards, 31, rng)
        self.assertIn("ucb1 score", reason)


class HeadroomRunnerTests(unittest.IsolatedAsyncioTestCase):
    """Integration tests for the headroom runner."""

    async def test_run_headroom_with_counting_oracle(self):
        """Run a tiny headroom experiment with a counting oracle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prereg_path = Path(tmpdir) / "PREREG.json"
            prereg = {
                "schema": "slab-039-prereg-v3",
                "fixture": "ascend910",
                "grid": 32,
                "rule": {"k": 5},
                "reducer_methods": {
                    "methods": ["random", "greedy", "simulated_annealing"],
                    "search_evaluations_per_method": 4,
                    "reproduction_evaluations_per_method": 0,
                    "total_evaluations_per_method": 4,
                    "seeds": [0, 1],
                    "seed_count": 2,
                },
                "extra_diagnostics": {
                    "methods": ["ucb1"],
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

            self.assertEqual(result["schema"], "slab-039-result-v3")
            self.assertIn("prereg_digest_sha256", result)
            self.assertEqual(len(result["prereg_digest_sha256"]), 64)
            self.assertIn(result["verdict"], ("PASS", "FAIL", "INCONCLUSIVE"))
            self.assertIn("reducer_results", result)
            self.assertIn("extra_diagnostic_results", result)
            self.assertIn("long_sa_results", result)
            self.assertIn("aggregate_evaluations", result)
            self.assertGreater(result["aggregate_evaluations"], 0)

            reducer_bests = [r["best_temperature_c"] for r in result["reducer_results"]]
            self.assertGreater(len(reducer_bests), 0)

            diag_results = result.get("extra_diagnostic_results", [])
            if diag_results:
                diag_bests = [r["best_temperature_c"] for r in diag_results]
                self.assertGreater(len(diag_bests), 0)

            long_bests = [r["best_temperature_c"] for r in result["long_sa_results"]]
            self.assertGreater(len(long_bests), 0)

            self.assertIsInstance(result["passed"], bool)

    async def test_headroom_verdict_is_plain(self):
        """The verdict is stated plainly as PASS, FAIL, or INCONCLUSIVE."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prereg_path = Path(tmpdir) / "PREREG.json"
            prereg = {
                "schema": "slab-039-prereg-v3",
                "fixture": "ascend910",
                "grid": 32,
                "rule": {"k": 5},
                "reducer_methods": {
                    "methods": ["random"],
                    "search_evaluations_per_method": 2,
                    "reproduction_evaluations_per_method": 0,
                    "total_evaluations_per_method": 2,
                    "seeds": [0],
                    "seed_count": 1,
                },
                "extra_diagnostics": {
                    "methods": [],
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

            self.assertIn(result["verdict"], ("PASS", "FAIL", "INCONCLUSIVE"))

    async def test_cpu_cap_enforced_in_long_sa(self):
        """The CPU cap is enforced in the long SA runner function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prereg_path = Path(tmpdir) / "PREREG.json"
            prereg = {
                "schema": "slab-039-prereg-v3",
                "fixture": "ascend910",
                "grid": 32,
                "rule": {"k": 5},
                "reducer_methods": {
                    "methods": ["random"],
                    "search_evaluations_per_method": 2,
                    "reproduction_evaluations_per_method": 0,
                    "total_evaluations_per_method": 2,
                    "seeds": [0],
                    "seed_count": 1,
                },
                "extra_diagnostics": {
                    "methods": [],
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

    async def test_long_sa_exhaustion_yields_inconclusive(self):
        """When all long SA runs are CPU-exhausted, verdict is INCONCLUSIVE."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prereg_path = Path(tmpdir) / "PREREG.json"
            prereg = {
                "schema": "slab-039-prereg-v3",
                "fixture": "ascend910",
                "grid": 32,
                "rule": {"k": 5},
                "reducer_methods": {
                    "methods": ["random"],
                    "search_evaluations_per_method": 2,
                    "reproduction_evaluations_per_method": 0,
                    "total_evaluations_per_method": 2,
                    "seeds": [0],
                    "seed_count": 1,
                },
                "extra_diagnostics": {
                    "methods": [],
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

            self.assertEqual(result["verdict"], "INCONCLUSIVE")
            self.assertTrue(result["long_sa_exhausted"])

    async def test_evaluation_budget_enforced(self):
        """The evaluation budget is enforced: each cheap lane runs exactly N evaluations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prereg_path = Path(tmpdir) / "PREREG.json"
            prereg = {
                "schema": "slab-039-prereg-v3",
                "fixture": "ascend910",
                "grid": 32,
                "rule": {"k": 5},
                "reducer_methods": {
                    "methods": ["random"],
                    "search_evaluations_per_method": 7,
                    "reproduction_evaluations_per_method": 0,
                    "total_evaluations_per_method": 7,
                    "seeds": [0],
                    "seed_count": 1,
                },
                "extra_diagnostics": {
                    "methods": [],
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

            cheap = result["reducer_results"][0]
            self.assertEqual(cheap["evaluation_count"], 7)

    async def test_cheap_median_uses_strongest_reducer_method_min_median(self):
        """cheap_median = min over reducer methods of per-method median, not average."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prereg_path = Path(tmpdir) / "PREREG.json"
            prereg = {
                "schema": "slab-039-prereg-v3",
                "fixture": "ascend910",
                "grid": 32,
                "rule": {"k": 5},
                "reducer_methods": {
                    "methods": ["random", "greedy", "simulated_annealing"],
                    "search_evaluations_per_method": 3,
                    "reproduction_evaluations_per_method": 0,
                    "total_evaluations_per_method": 3,
                    "seeds": [10, 11, 12],
                    "seed_count": 3,
                },
                "extra_diagnostics": {
                    "methods": ["ucb1", "signal_portfolio"],
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

            reducer_medians = {}
            for method in prereg["reducer_methods"]["methods"]:
                method_results = [r for r in result["reducer_results"] if r["method"] == method]
                bests = [r["best_temperature_c"] for r in method_results]
                reducer_medians[method] = statistics.median(bests)

            self.assertAlmostEqual(result["cheap_median_c"], min(reducer_medians.values()))

    async def test_extra_diagnostics_excluded_from_cheap_median(self):
        """Extra diagnostics (UCB1, signal_portfolio) are excluded from cheap_median."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prereg_path = Path(tmpdir) / "PREREG.json"
            prereg = {
                "schema": "slab-039-prereg-v3",
                "fixture": "ascend910",
                "grid": 32,
                "rule": {"k": 5},
                "reducer_methods": {
                    "methods": ["random"],
                    "search_evaluations_per_method": 3,
                    "reproduction_evaluations_per_method": 0,
                    "total_evaluations_per_method": 3,
                    "seeds": [10, 11],
                    "seed_count": 2,
                },
                "extra_diagnostics": {
                    "methods": ["ucb1"],
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

            reducer_medians = {}
            for method in prereg["reducer_methods"]["methods"]:
                method_results = [r for r in result["reducer_results"] if r["method"] == method]
                bests = [r["best_temperature_c"] for r in method_results]
                reducer_medians[method] = statistics.median(bests)

            self.assertAlmostEqual(result["cheap_median_c"], min(reducer_medians.values()))

    async def test_greedy_lane_included(self):
        """The greedy lane runs and produces results."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prereg_path = Path(tmpdir) / "PREREG.json"
            prereg = {
                "schema": "slab-039-prereg-v3",
                "fixture": "ascend910",
                "grid": 32,
                "rule": {"k": 5},
                "reducer_methods": {
                    "methods": ["greedy"],
                    "search_evaluations_per_method": 3,
                    "reproduction_evaluations_per_method": 0,
                    "total_evaluations_per_method": 3,
                    "seeds": [0],
                    "seed_count": 1,
                },
                "extra_diagnostics": {
                    "methods": [],
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

            greedy_results = [r for r in result["reducer_results"] if r["method"] == "greedy"]
            self.assertEqual(len(greedy_results), 1)
            self.assertGreater(greedy_results[0]["evaluation_count"], 0)

    async def test_aggregate_evaluations_tracks_all(self):
        """aggregate_evaluations counts all evaluations including init."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prereg_path = Path(tmpdir) / "PREREG.json"
            prereg = {
                "schema": "slab-039-prereg-v3",
                "fixture": "ascend910",
                "grid": 32,
                "rule": {"k": 5},
                "reducer_methods": {
                    "methods": ["random"],
                    "search_evaluations_per_method": 2,
                    "reproduction_evaluations_per_method": 0,
                    "total_evaluations_per_method": 2,
                    "seeds": [0],
                    "seed_count": 1,
                },
                "extra_diagnostics": {
                    "methods": [],
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

            self.assertGreater(result["aggregate_evaluations"], 0)
            self.assertIn("total_evaluations_including_init", result["reducer_results"][0])
            self.assertGreaterEqual(
                result["reducer_results"][0]["total_evaluations_including_init"],
                result["reducer_results"][0]["evaluation_count"],
            )

    async def test_mesh_error_validation_rejects_negative(self):
        """run_headroom rejects negative mesh_error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prereg_path = Path(tmpdir) / "PREREG.json"
            prereg = {
                "schema": "slab-039-prereg-v3",
                "fixture": "ascend910",
                "grid": 32,
                "rule": {"k": 5},
                "reducer_methods": {
                    "methods": ["random"],
                    "search_evaluations_per_method": 2,
                    "reproduction_evaluations_per_method": 0,
                    "total_evaluations_per_method": 2,
                    "seeds": [0],
                    "seed_count": 1,
                },
                "extra_diagnostics": {"methods": []},
                "long_sa": {
                    "restarts": 1,
                    "max_evaluations_per_restart": 4,
                    "max_cpu_minutes": 1,
                    "seeds": [100],
                },
            }
            prereg_path.write_text(json.dumps(prereg), encoding="utf-8")

            with self.assertRaises(ValueError):
                await run_headroom(
                    fixture="ascend910",
                    mesh_error=-0.1,
                    prereg_path=prereg_path,
                )

    async def test_mesh_error_validation_rejects_inf(self):
        """run_headroom rejects infinite mesh_error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prereg_path = Path(tmpdir) / "PREREG.json"
            prereg = {
                "schema": "slab-039-prereg-v3",
                "fixture": "ascend910",
                "grid": 32,
                "rule": {"k": 5},
                "reducer_methods": {
                    "methods": ["random"],
                    "search_evaluations_per_method": 2,
                    "reproduction_evaluations_per_method": 0,
                    "total_evaluations_per_method": 2,
                    "seeds": [0],
                    "seed_count": 1,
                },
                "extra_diagnostics": {"methods": []},
                "long_sa": {
                    "restarts": 1,
                    "max_evaluations_per_restart": 4,
                    "max_cpu_minutes": 1,
                    "seeds": [100],
                },
            }
            prereg_path.write_text(json.dumps(prereg), encoding="utf-8")

            with self.assertRaises(ValueError):
                await run_headroom(
                    fixture="ascend910",
                    mesh_error=float("inf"),
                    prereg_path=prereg_path,
                )


if __name__ == "__main__":
    unittest.main()
