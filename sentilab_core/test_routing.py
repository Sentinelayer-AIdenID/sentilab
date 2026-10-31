import copy
import json
from pathlib import Path
import tempfile
import unittest

from sentilab_core.routing import AdvisoryRouter, load_router_fixture


FIXTURE = Path(__file__).resolve().parents[1] / "docs/sentilab/evidence/SLAB-010/routing-fixtures.json"


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads(FIXTURE.read_text())
        self.router, self.heldout = load_router_fixture(FIXTURE)

    def test_frozen_heldout_reports_accuracy_buckets_and_abstention(self):
        report = self.router.calibrate(self.heldout)
        self.assertEqual(report["fitting_count"], 9)
        self.assertEqual(report["count"], 8)
        self.assertEqual(report["candidate_accuracy"], 0.75)
        self.assertEqual(report["decision_accuracy"], 0.625)
        self.assertEqual(report["selective_accuracy"], 0.8)
        self.assertEqual(report["abstention_rate"], 0.375)
        self.assertEqual(report["answered"], 5)
        self.assertEqual([bucket["count"] for bucket in report["buckets"]], [1, 0, 2, 5])
        self.assertEqual([bucket["accuracy"] for bucket in report["buckets"]], [1.0, None, 0.5, 0.8])
        self.assertAlmostEqual(report["buckets"][-1]["mean_confidence"], 0.85)
        self.assertNotIn("confidence_sum", report["buckets"][1])
        self.assertTrue(report["advisory"])

    def test_confidence_is_fitted_empirical_accuracy_not_adapter_score(self):
        result = self.router.route({"candidate": "thermal-lab", "score": 0.99})
        self.assertEqual(result["confidence"], 0.75)
        self.assertEqual(result["raw_score"], 0.99)
        self.assertEqual(result["calibration_samples"], 4)
        self.assertEqual(result["choice"], "thermal-lab")
        self.assertTrue(result["advisory"])
        self.assertNotIn("accepted", result)

    def test_threshold_is_inclusive_and_below_threshold_abstains(self):
        task = {"candidate": "thermal-lab", "score": 0.9}
        self.assertEqual(self.router.route(task)["choice"], "thermal-lab")
        stricter = AdvisoryRouter(self.fixture["registry"], self.fixture["calibration"], threshold=0.750001)
        self.assertIsNone(stricter.route(task)["choice"])
        result = self.router.route({"candidate": "thermal-lab", "score": 0.4})
        self.assertEqual(result["confidence"], 0.5)
        self.assertTrue(result["abstained"])
        self.assertEqual(result["reason"], "below_threshold")

    def test_unknown_route_rejected_even_with_low_score_or_high_threshold(self):
        for score in (0, 0.1, 1):
            with self.subTest(score=score), self.assertRaisesRegex(ValueError, "unknown route"):
                self.router.route({"candidate": "unregistered", "score": score})
        with self.assertRaisesRegex(ValueError, "unknown route"):
            self.router.route({"candidate": "unregistered", "score": float("nan")})

    def test_no_calibration_support_always_abstains_even_at_zero_threshold(self):
        router = AdvisoryRouter(self.fixture["registry"], self.fixture["calibration"], threshold=0)
        for task in ({"candidate": "literature-lab", "score": 0.99},
                     {"candidate": "thermal-lab", "score": 0.6}):
            result = router.route(task)
            self.assertIsNone(result["choice"])
            self.assertEqual(result["confidence"], 0)
            self.assertEqual(result["calibration_samples"], 0)
            self.assertEqual(result["reason"], "uncalibrated")
        cold = AdvisoryRouter(self.fixture["registry"], [])
        self.assertTrue(cold.route({"candidate": "thermal-lab", "score": 1})["abstained"])

    def test_score_bucket_boundaries_and_inclusive_one(self):
        examples = [{"id": f"edge-{i}", "family": "fit-edge",
                     "task": {"candidate": "thermal-lab", "score": score},
                     "expected": "thermal-lab" if i % 2 == 0 else None}
                    for i, score in enumerate((0, 0.25, 0.5, 0.75))]
        router = AdvisoryRouter(self.fixture["registry"], examples)
        for score, confidence in ((0, 1), (0.249999, 1), (0.25, 0), (0.499999, 0),
                                  (0.5, 1), (0.749999, 1), (0.75, 0), (1, 0)):
            with self.subTest(score=score):
                self.assertEqual(router.route({"candidate": "thermal-lab", "score": score})["confidence"], confidence)

    def test_nonfinite_out_of_range_and_untyped_probabilities_rejected(self):
        for value in (-1, 1.01, float("nan"), float("inf"), float("-inf"), True, "0.5", None, 10 ** 400):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.router.route({"candidate": "thermal-lab", "score": value})
                with self.assertRaises(ValueError):
                    AdvisoryRouter(self.fixture["registry"], [], threshold=value)

    def test_task_and_registry_validation_rejects_missing_or_unknown_fields(self):
        for task in (None, [], {}, {"candidate": "thermal-lab"}, {"candidate": None, "score": 0},
                     {"candidate": "thermal-lab", "score": 1, "accept": True}):
            with self.subTest(task=task), self.assertRaises(ValueError):
                self.router.route(task)
        for registry in ({}, [], {"x": {}}, {"x": {"kind": "executor", "description": "x"}},
                         {"x": {"kind": "lab", "description": ""}}):
            with self.subTest(registry=registry), self.assertRaises(ValueError):
                AdvisoryRouter(registry, [])

    def test_calibration_examples_reject_missing_identity_duplicates_and_unknown_truth(self):
        example = self.fixture["calibration"][0]
        invalid = [[example, example], None, [{**example, "id": ""}],
                   [{**example, "family": None}], [{**example, "expected": "unregistered"}],
                   [{key: value for key, value in example.items() if key != "expected"}]]
        for rows in invalid:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                AdvisoryRouter(self.fixture["registry"], rows)

    def test_heldout_id_and_family_overlap_and_empty_evaluation_rejected(self):
        for field, message in (("id", "IDs overlap"), ("family", "families overlap")):
            rows = copy.deepcopy(self.heldout)
            rows[0][field] = self.fixture["calibration"][0][field]
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, message):
                self.router.calibrate(rows)
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            self.router.calibrate([])

    def test_heldout_labels_do_not_refit_and_reloads_are_deterministic(self):
        before = self.router.route({"candidate": "thermal-lab", "score": 0.9})
        changed = copy.deepcopy(self.heldout)
        for row in changed:
            row["expected"] = None
        self.router.calibrate(changed)
        self.assertEqual(self.router.route({"candidate": "thermal-lab", "score": 0.9}), before)
        report = self.router.calibrate(self.heldout)
        other, examples = load_router_fixture(FIXTURE)
        self.assertEqual(report, other.calibrate(examples))
        self.assertEqual(json.dumps(report, sort_keys=True), json.dumps(self.router.calibrate(self.heldout), sort_keys=True))

    def test_all_abstention_report_has_no_invented_selective_accuracy(self):
        router = AdvisoryRouter(self.fixture["registry"], [])
        report = router.calibrate(self.heldout)
        self.assertEqual(report["abstention_rate"], 1)
        self.assertIsNone(report["selective_accuracy"])
        self.assertEqual(report["answered"], 0)

    def test_registry_and_fit_are_snapshots_not_mutable_caller_inputs(self):
        router = AdvisoryRouter(self.fixture["registry"], self.fixture["calibration"])
        self.fixture["registry"]["thermal-lab"]["kind"] = "executor"
        self.fixture["calibration"][0]["expected"] = None
        self.assertEqual(router.registry["thermal-lab"]["kind"], "lab")
        self.assertEqual(router.route({"candidate": "thermal-lab", "score": 0.9})["confidence"], 0.75)
        with self.assertRaises(TypeError):
            router.registry["thermal-lab"]["kind"] = "executor"

    def test_fixture_loader_rejects_wrong_schema_unlabeled_evidence_and_split_leak(self):
        for field, value in (("schema_version", 2), ("evidence_kind", "production-accuracy"),
                             ("heldout", self.fixture["calibration"])):
            fixture = {**self.fixture, field: value}
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "fixture.json"
                path.write_text(json.dumps(fixture))
                with self.subTest(field=field), self.assertRaises(ValueError):
                    load_router_fixture(path)


if __name__ == "__main__":
    unittest.main()
