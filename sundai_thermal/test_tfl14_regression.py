"""TFL-14 reproducibility checks for the synthetic search and HotSpot probe."""

import contextlib
import io
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import simulation


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EXPECTED_MEANS = {
    "random": "79.9564865",
    "local_annealing": "78.7703960",
    "surrogate_screened": "79.8820836",
}
EXPECTED_PROBE_PEAKS_C = {
    ("baseline_center", 16): 118.36,
    ("baseline_center", 32): 118.89,
    ("left_shift_2mm", 16): 119.23,
    ("left_shift_2mm", 32): 119.36,
    ("left_shift_4mm", 16): 119.82,
    ("left_shift_4mm", 32): 119.78,
    ("right_shift_2mm", 16): 118.88,
    ("right_shift_2mm", 32): 118.84,
}


class TFL14RegressionTests(unittest.TestCase):
    def test_seeded_random_annealing_and_recorded_artifacts_are_reproducible(self):
        fresh_console = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            generated_path = Path(directory)
            with (
                mock.patch.object(simulation, "OUT", generated_path),
                mock.patch.object(simulation, "make_plots"),
                contextlib.redirect_stdout(fresh_console),
            ):
                simulation.main()
            generated = json.loads(
                (generated_path / "results.json").read_text(encoding="utf-8")
            )

        summary = generated["summary"]
        for method in ("random", "local_annealing"):
            expected = EXPECTED_MEANS[method]
            actual = summary[method]["mean_best_objective_C"]
            self.assertEqual(f"{actual:.7f}", expected, method)
        self.assertTrue(
            math.isfinite(summary["surrogate_screened"]["mean_best_objective_C"])
        )

        committed = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(committed["versions"]["openblas_coretype"], "Haswell")
        self.assertEqual(committed["versions"]["openblas_architecture"], "Haswell")
        for method, expected in EXPECTED_MEANS.items():
            actual = committed["summary"][method]["mean_best_objective_C"]
            self.assertEqual(
                f"{actual:.7f}",
                expected,
                f"stale results.json value for {method}",
            )

        if os.environ.get("TFL_CANONICAL_CONTAINER") == "1":
            self.assertEqual(generated["versions"]["openblas_coretype"], "Haswell")
            self.assertEqual(generated["versions"]["openblas_architecture"], "Haswell")
            # Outside the image, OpenBLAS may select a different kernel; skip only
            # exact surrogate-result equality there. The image pins Haswell.
            for method in EXPECTED_MEANS:
                self.assertEqual(
                    summary[method]["mean_best_objective_C"],
                    committed["summary"][method]["mean_best_objective_C"],
                    f"fresh container result differs for {method}",
                )

        run_output = (HERE / "run_output.txt").read_text(encoding="utf-8")
        console_summary = json.loads(run_output[run_output.index("{"):])["summary"]
        fresh_output = fresh_console.getvalue()
        fresh_summary = json.loads(fresh_output[fresh_output.index("{"):])["summary"]
        for method, expected in EXPECTED_MEANS.items():
            actual = console_summary[method]["mean_best_objective_C"]
            self.assertEqual(
                f"{actual:.7f}",
                expected,
                f"stale run_output.txt value for {method}",
            )
            if os.environ.get("TFL_CANONICAL_CONTAINER") == "1":
                self.assertEqual(
                    fresh_summary[method]["mean_best_objective_C"],
                    actual,
                    f"fresh run_output differs for {method}",
                )

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("random 79.9564865°C", readme)
        self.assertIn("local annealing 78.7703960°C", readme)
        self.assertIn("surrogate-screened 79.8820836°C", readme)

    def test_eight_published_hotspot_probe_peaks(self):
        report_path = Path(os.environ.get(
            "TFL_HOTSPOT_PROBE_REPORT",
            HERE.parent / "sundai_hotspot" / "probe_results" / "combined_report.json",
        ))
        report = json.loads(report_path.read_text(encoding="utf-8"))
        runs = report["runs"]
        actual = {
            (run["placement"], run["grid_rows"]): run["chip_layer_peak_C"]
            for run in runs
        }
        self.assertEqual(len(runs), 8)
        self.assertEqual(set(actual), set(EXPECTED_PROBE_PEAKS_C))
        for case, expected in EXPECTED_PROBE_PEAKS_C.items():
            # Round at micro-degree precision so binary representation of an exact
            # 0.01 C difference does not turn the stated tolerance into a failure.
            self.assertLessEqual(
                round(abs(actual[case] - expected), 6), 0.01, str(case)
            )


if __name__ == "__main__":
    unittest.main()
