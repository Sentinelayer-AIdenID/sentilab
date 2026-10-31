import json
import hashlib
import statistics
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from controller import FlightRecord
import tfl08_leaderboard
from tfl08_leaderboard import run_benchmark, run_leaderboard, summarize


class Tfl08LeaderboardTests(unittest.IsolatedAsyncioTestCase):
    async def test_ten_seed_batch_has_equal_budgets_shared_pool_and_signed_records(self):
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "published"
            first = await run_leaderboard(
                ("plate",), seeds=range(10), evaluations_per_lane=2,
                shared_sample_count=1, output_dir=output_dir,
            )
            second = await run_leaderboard(
                ("plate",), seeds=range(10), evaluations_per_lane=2,
                shared_sample_count=1,
            )

            first_benchmark = first["benchmarks"]["plate"]
            second_benchmark = second["benchmarks"]["plate"]
            self.assertEqual(first["schema"], "tfl08-leaderboard-v1")
            self.assertIn("report-only", first["protocol"]["timing_note"])
            self.assertEqual(first_benchmark["seed_count"], 10)
            self.assertEqual(len(first_benchmark["runs"]), 10)
            self.assertEqual(
                [run["deterministic_fingerprint"] for run in first_benchmark["runs"]],
                [run["deterministic_fingerprint"] for run in second_benchmark["runs"]],
            )

            for run in first_benchmark["runs"]:
                self.assertTrue(run["evaluation_counts_equal"])
                self.assertEqual(len(set(run["shared_initial_sample_hashes"])), 2)
                self.assertIn("signal_portfolio", run["deterministic_fingerprint_lanes"])
                self.assertEqual(len(run["deterministic_fingerprint_lanes"]), 7)
                self.assertEqual(len(run["lanes"]), 7)
                fixed_curve = run["hindsight_best_fixed_operator"]["best_so_far_c"]
                self.assertEqual(len(fixed_curve), 3)
                self.assertEqual(fixed_curve[-1], run["hindsight_best_fixed_operator"]["best_temperature_c"])
                for lane in run["lanes"].values():
                    self.assertEqual(lane["evaluation_count"], 2)
                    self.assertEqual(lane["evaluation_admissions"], 2)
                    self.assertEqual(len(lane["best_so_far_c"]), 3)
                    record_path = output_dir / lane["record"]["path"]
                    stored = json.loads(record_path.read_text(encoding="utf-8"))
                    self.assertTrue(FlightRecord.verify(stored["events"], stored["record_public_key"]))
                    self.assertTrue(lane["record"]["valid"])

            plate_stats = first_benchmark["statistics"]
            for lane_id in ("random", "simulated_annealing", "ucb1", "signal_portfolio"):
                self.assertEqual(plate_stats["lanes"][lane_id]["n"], 10)
                self.assertEqual(len(plate_stats["lanes"][lane_id]["best_so_far_curve"]), 3)
            signal = plate_stats["lanes"]["signal_portfolio"]["signal_layer"]
            self.assertEqual(signal["mode"], "local")
            signal_outcomes = [run["lanes"]["signal_portfolio"]["best_temperature_c"]
                               for run in first_benchmark["runs"]]
            self.assertAlmostEqual(plate_stats["lanes"]["signal_portfolio"]["sample_variance_c2"],
                                   statistics.variance(signal_outcomes))
            self.assertEqual(signal["total_provider_calls"], 0)
            self.assertEqual(signal["total_input_tokens"], 0)
            self.assertEqual(signal["estimated_list_price_usd"], 0)
            comparison = plate_stats["lanes"]["simulated_annealing"]["paired_wilcoxon_vs_ucb1"]
            self.assertEqual(comparison["n"], 10)
            self.assertEqual(comparison["zero_method"], "zsplit")
            self.assertRegex(plate_stats["signal_vs_ucb1_plain_result"],
                             r"paired Wilcoxon p=0\.\d{2}, n=10; not significant")
            reference = plate_stats["lanes"]["hindsight_best_fixed_operator"]
            self.assertEqual(len(reference["best_so_far_curve"]), 3)
            self.assertTrue(reference["selection_is_hindsight_upper_bound"])
            self.assertGreater(reference["median_wall_time_s"], 0)
            self.assertIn("signal portfolio median", plate_stats["signal_vs_ucb1_plain_result"].lower())
            self.assertEqual(json.loads((output_dir / "leaderboard.json").read_text(encoding="utf-8"))["schema"],
                             "tfl08-leaderboard-v1")
            self.assertTrue(first["runtime"]["python"])

    async def test_live_signal_adapter_budget_is_independent_for_each_seed(self):
        adapters = []

        class TrackingRouter:
            def __init__(self, *, max_calls, timeout_s):
                self.max_calls = max_calls
                self.calls = 0
                adapters.append(self)

            async def __call__(self, state):
                self.calls += 1
                return {
                    "route": "swap", "reason": "test provider advice", "provider_called": True,
                    "input_hash": "a" * 64, "output_hash": "b" * 64,
                    "probabilities": {"local_move": 0.1, "swap": 0.6,
                                      "global_resample": 0.2, "stop": 0.1},
                    "confidence": 0.8, "input_tokens": 12, "output_tokens": 3,
                }

        with patch.object(tfl08_leaderboard, "JevRoutingAdapter", TrackingRouter):
            result = await run_benchmark(
                "plate", seeds=range(10), evaluations_per_lane=1,
                shared_sample_count=0, signal_mode="live")

        self.assertEqual(len(adapters), 10)
        self.assertEqual([adapter.calls for adapter in adapters], [1] * 10)
        self.assertNotIn("signal_portfolio", result["runs"][0]["deterministic_fingerprint_lanes"])
        signal = result["statistics"]["lanes"]["signal_portfolio"]["signal_layer"]
        self.assertEqual(signal["total_provider_calls"], 10)
        self.assertEqual(signal["total_input_tokens"], 120)
        self.assertEqual(signal["total_output_tokens"], 30)
        self.assertEqual(signal["total_fallbacks"], 0)
        self.assertAlmostEqual(signal["estimated_list_price_usd"], 120 * 0.042 / 1_000_000)
        self.assertIsNone(signal["invoice_cost_usd"])

    def test_published_batch_assets_are_complete_and_verifiable(self):
        asset_root = tfl08_leaderboard.ROOT / "web" / "public" / "tfl08"
        summary_path = asset_root / "leaderboard.json"
        if not summary_path.is_file():
            self.skipTest("web assets are omitted from this build context")
        report = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(report["schema"], "tfl08-leaderboard-v1")
        runtime = report["runtime"]
        self.assertEqual(runtime["runner_source_sha256"], hashlib.sha256(
            Path(tfl08_leaderboard.__file__).read_bytes()).hexdigest())
        self.assertEqual(runtime["controller_source_sha256"], hashlib.sha256(
            Path(tfl08_leaderboard.__file__).with_name("controller.py").read_bytes()).hexdigest())
        self.assertEqual(runtime["experiment_source_sha256"], hashlib.sha256(
            Path(tfl08_leaderboard.__file__).with_name("experiment.py").read_bytes()).hexdigest())
        verified_records = 0
        for benchmark in ("plate", "ascend910"):
            item = report["benchmarks"][benchmark]
            self.assertEqual(item["seed_count"], 10)
            self.assertEqual(item["evaluations_per_lane"], 8)
            self.assertEqual(item["signal_mode"], "local")
            for run in item["runs"]:
                self.assertTrue(run["evaluation_counts_equal"])
                self.assertEqual(len(run["lanes"]), 7)
                fingerprinted_records = {}
                for lane_id, lane in run["lanes"].items():
                    self.assertEqual(lane["evaluation_count"], 8)
                    relative_path = Path(lane["record"]["path"])
                    self.assertFalse(relative_path.is_absolute())
                    self.assertNotIn("..", relative_path.parts)
                    bundle = json.loads((asset_root / relative_path).read_text(encoding="utf-8"))
                    self.assertEqual(bundle["lane_id"], lane_id)
                    self.assertTrue(FlightRecord.verify(bundle["events"], bundle["record_public_key"]))
                    baseline = next(event["payload"] for event in bundle["events"]
                                    if event["event"] == "baseline")
                    hashes = [sample["design_hash"] for sample in baseline["shared_initial_samples"]]
                    self.assertEqual(hashes, run["shared_initial_sample_hashes"])
                    if lane_id in run["deterministic_fingerprint_lanes"]:
                        fingerprinted_records[lane_id] = tfl08_leaderboard._deterministic_record_projection(
                            bundle["events"])
                    verified_records += 1
                self.assertEqual(tfl08_leaderboard.digest(fingerprinted_records),
                                 run["deterministic_fingerprint"])
        self.assertEqual(verified_records, 140)

    async def test_tfl08_refuses_fewer_than_ten_seeds(self):
        with self.assertRaisesRegex(ValueError, "at least 10"):
            await run_benchmark("plate", seeds=range(9))

    def test_runner_uses_package_controller_shared_with_hotspot_adapter(self):
        self.assertEqual(tfl08_leaderboard.Controller.__module__, "sundai_controller.controller")
        self.assertEqual(tfl08_leaderboard.ThermalResult.__module__, "sundai_controller.controller")

    def test_summary_bootstrap_and_iqr_are_reproducible(self):
        values = [float(number) for number in range(10)]
        first = summarize(values, bootstrap_seed=17, resamples=1000)
        second = summarize(values, bootstrap_seed=17, resamples=1000)
        self.assertEqual(first, second)
        self.assertEqual(first["median"], 4.5)
        self.assertEqual(first["iqr"], 4.5)
        low, high = first["bootstrap_95_ci_median"]
        self.assertLessEqual(low, first["median"])
        self.assertGreaterEqual(high, first["median"])

    def test_best_median_reports_every_tied_strategy(self):
        def lane(temperature, *, signal=False):
            row = {
                "best_temperature_c": temperature,
                "wall_time_s": 0.1,
                "simulator_spend_microdollars": 0,
                "noop_evaluations": 0,
                "best_so_far_c": [temperature],
            }
            if signal:
                row["signal"] = {
                    "provider_calls": 0,
                    "fallback_count": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "list_price_estimate_usd": 0.0,
                }
            return row

        runs = []
        for offset in (0.0, 1.0):
            runs.append({
                "signal_mode": "local",
                "lanes": {
                    "random": lane(80.0 + offset),
                    "simulated_annealing": lane(81.0 + offset),
                    "ucb1": lane(82.0 + offset),
                    "signal_portfolio": lane(80.0 + offset, signal=True),
                },
                "hindsight_best_fixed_operator": {
                    "operator": "local_move",
                    "best_temperature_c": 79.0 + offset,
                    "noop_evaluations": 0,
                    "wall_time_s": 0.1,
                    "best_so_far_c": [79.0 + offset],
                },
            })
        result = tfl08_leaderboard._summary_rows(
            runs,
            ("random", "simulated_annealing", "ucb1", "signal_portfolio"),
            "plate",
        )
        self.assertEqual(result["winners_by_median"], ["random", "signal_portfolio"])
        self.assertEqual(result["winner_by_median"], "tie: random, signal_portfolio")
        signal_test = result["lanes"]["signal_portfolio"]["paired_wilcoxon_vs_ucb1"]
        self.assertEqual(signal_test["n"], 2)
        self.assertEqual(signal_test["zero_method"], "zsplit")
        self.assertRegex(
            result["signal_vs_ucb1_plain_result"],
            r"paired Wilcoxon p=0\.50, n=2; not significant",
        )

    def test_deterministic_fingerprint_ignores_only_runtime_and_temp_path_material(self):
        first = [{"event": "oracle_result", "payload": {"thermal": {
            "evaluation_seconds": 0.2, "solver_seconds": 0.1, "input_generation_seconds": 0.01,
            "input_sha256": [["sampleL4_ChipLayer.flp", "a" * 64], ["samplelayers.lcf", "b" * 64]],
            "maximum_temperature_c": 93.5, "heatmap_c": [[45.0, 93.5]],
        }}}]
        rerun = [{"event": "oracle_result", "payload": {"thermal": {
            "evaluation_seconds": 0.3, "solver_seconds": 0.15, "input_generation_seconds": 0.02,
            "input_sha256": [["sampleL4_ChipLayer.flp", "a" * 64], ["samplelayers.lcf", "c" * 64]],
            "maximum_temperature_c": 93.5, "heatmap_c": [[45.0, 93.5]],
        }}}]
        self.assertEqual(
            tfl08_leaderboard._deterministic_record_projection(first),
            tfl08_leaderboard._deterministic_record_projection(rerun),
        )
        rerun[0]["payload"]["thermal"]["maximum_temperature_c"] = 94.0
        self.assertNotEqual(
            tfl08_leaderboard._deterministic_record_projection(first),
            tfl08_leaderboard._deterministic_record_projection(rerun),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
