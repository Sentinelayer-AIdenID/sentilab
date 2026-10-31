"""Build receipt checks against installed executables, without an image build."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BuildInfoTests(unittest.TestCase):
    def test_actual_runtime_is_recorded_and_unpinned_inputs_fail_before_write(self):
        # The base identity is a test input, not a claim that this host runs it.
        base = "test-fixture@sha256:" + "0" * 64
        package = subprocess.check_output(
            ["dpkg-query", "-W", "-f=${Version}", "nodejs"], text=True).strip()
        version = subprocess.check_output(["/usr/bin/node", "--version"], text=True).strip()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "build-info.json"
            command = [sys.executable, str(ROOT / "scripts/record_build_info.py"),
                       "--output", str(output)]
            success = subprocess.run([*command, "--base-image", base, "--node-package-version", package],
                                     capture_output=True, text=True)
            self.assertEqual(success.returncode, 0, success.stderr)
            self.assertEqual(success.stdout, output.read_text())
            self.assertEqual(json.loads(success.stdout), {
                "schema": "sentilab-build-info/1", "base_image": base,
                "base_image_digest": base.split("@")[1],
                "node_version": version, "debian_nodejs_version": package})
            output.unlink()
            for image, pin in (("python:3.12-slim", package), (base, "not-the-installed-package")):
                with self.subTest(image=image, pin=pin):
                    failure = subprocess.run([*command, "--base-image", image, "--node-package-version", pin],
                                             capture_output=True, text=True)
                    self.assertNotEqual(failure.returncode, 0)
                    self.assertFalse(output.exists())
                    self.assertEqual(failure.stdout, "")


if __name__ == "__main__":
    unittest.main()
