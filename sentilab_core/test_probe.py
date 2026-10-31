"""Run the real offline probe recorder; raw CLI diagnostics never reach output."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ProbeRecorderTests(unittest.TestCase):
    def run_recorder(self, raw, output):
        return subprocess.run([sys.executable, "-m", "sentilab_core.probe", "--provider", "fixture-provider",
                               "--entitlement-source", "fixture-entitlement", "--output", str(output)],
                              input=raw, text=True, capture_output=True, check=False)

    def test_cli_projects_only_nonsecret_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "probe.json"
            raw = json.dumps(dict(status_code=200, data=[dict(id="fixture-model", key="private-fixture")],
                                  headers={"Authorization": "private-fixture"}, error="private-fixture"))
            result = self.run_recorder(raw, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            evidence = json.loads(output.read_text())
            self.assertEqual(set(evidence), {"provider", "entitlement_source", "checked_at", "status_code", "models"})
            self.assertEqual(evidence["models"], ["fixture-model"])
            self.assertEqual(evidence["status_code"], 200)
            self.assertNotIn("private-fixture", output.read_text() + result.stdout + result.stderr)

    def test_failure_status_is_evidence_and_malformed_input_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "probe.json"
            result = self.run_recorder('{"status_code":401,"error":"private-fixture"}', output)
            self.assertEqual(result.returncode, 0)
            evidence = output.read_text()
            self.assertEqual(json.loads(evidence)["models"], [])
            for raw in ('not JSON private-fixture', '{"status_code":true}',
                        '{"status_code":200,"data":[{}]}',
                        '{"status_code":200,"status_code":401}',
                        '{"status_code":200,"data":[{"id":"Bearer private-fixture"}]}',
                        'x' * (1024 * 1024 + 1)):
                with self.subTest(raw=raw[:60]):
                    result = self.run_recorder(raw, output)
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(output.read_text(), evidence)
                    self.assertNotIn("private-fixture", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
