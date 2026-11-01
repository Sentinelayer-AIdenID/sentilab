"""The separately granted coupling calls; synthetic engines only, never a thermal solve."""
from __future__ import annotations

import hashlib
import json
import contextlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from sundai_hotspot import coupling_allocation, gate0_anchor, gate0_operator, gate_zero, reference_validation, slab049
from sundai_hotspot import test_gate_zero as fixtures


class CouplingManifestTests(unittest.TestCase):
    def test_explicit_selection_preserves_the_twelve_call_gate_manifest(self):
        gate, gate_hash = reference_validation.load_manifest()
        coupling, coupling_hash = reference_validation.load_manifest(selection="coupling")
        self.assertEqual(gate_hash, "23a1a74b9d4fd56e5fa192982d74d9eaa90f6aeaf81d718247d566f12612053b")
        self.assertEqual(hashlib.sha256(slab049._dump(slab049.build_call_list())).hexdigest(), gate_hash)
        self.assertEqual(len(gate["calls"]), 12)
        self.assertNotEqual(coupling_hash, gate_hash)
        source = slab049.EVIDENCE_DIR / "coupling-call-list.json"
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),
                         "db32a692b749e08324c295e56250f96a9548796aae232ca63f24d2ad4ab3e577")
        frozen = json.loads(source.read_text())
        self.assertEqual([row["id"] for row in coupling["calls"]], [row["call"] for row in frozen["calls"]])
        self.assertTrue(set(c["id"] for c in gate["calls"]).isdisjoint(c["id"] for c in coupling["calls"]))
        self.assertEqual(coupling["accounting"]["manifest_cpu_cap_s"], 234.0)
        for row, listed in zip(coupling["calls"], frozen["calls"]):
            self.assertEqual(row["binary_sha256"],
                             "6ea3b7813412c13d20c92adc6449fbc0bc87c46b521d4d5eaf80b8abc7900609")
            self.assertEqual(row["kind"], "material_only")
            self.assertEqual(row["argv"][1:], listed["argv_after_binary"])
            self.assertEqual(row["accounting"]["reserved_cpu_s"], listed["envelope_cpu_s"])
        with self.assertRaises(reference_validation.CallRefused):
            reference_validation.load_manifest(selection="unknown")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "manifest.json"
            path.write_bytes(slab049._dump(coupling))
            with self.assertRaises(reference_validation.CallRefused):
                reference_validation.load_manifest(path)  # a path never selects coupling implicitly
            self.assertEqual(reference_validation.load_manifest(path, selection="coupling")[1], coupling_hash)


class CouplingEntryTests(fixtures.EntryCase):
    def setUp(self):
        super().setUp()
        self.old_hash = self.manifest_sha256
        self.old_dir = self.scenario.dir
        self.old_bytes = {p.name: p.read_bytes() for p in self.old_dir.glob("*.json")}
        # Keep the existing fake engine, changing only its identity and printed precision.
        fake = self.fake.read_text()
        marker = next(line for line in fake.splitlines() if line.startswith("# markers:"))
        fake = fake.replace(marker, "# microchannel " + gate_zero.VARIANT_TAG.decode()).replace("%.2f", "%.9f")
        self.fake.write_text(fake)
        self.write_provenance(self.fake, "material_only")
        self.patch(coupling_allocation, "BINARY_SHA256", fixtures._sha256(self.fake))
        self.manifest, self.manifest_sha256 = reference_validation.load_manifest(selection="coupling")
        self.calls = {row["id"]: row for row in self.manifest["calls"]}
        self.envelopes = {name: row["accounting"]["reserved_cpu_s"] for name, row in self.calls.items()}
        self.scenario = self.grant("grant", cap=234, grant_id="g49-coupling")

    def call(self, name, out, **kwargs):
        return super().call(name, out, selection="coupling", **kwargs)

    def run_pair(self, index, peak, replay_peak=None):
        primary, replay = list(self.calls)[index:index + 2]
        for call, value in ((primary, peak), (replay, peak if replay_peak is None else replay_peak)):
            self.scenario.reserve(call)
            self.control_case(call, peak_c=value)
            receipt = self.call(call, call)
            self.assertEqual((receipt["status"], receipt["exit_status"]), ("exited", 0), receipt.get("error"))
            self.scenario.settle(call)
        return reference_validation.report(ledger_root=self.scenario.root, tags=self.scenario.tags,
                                           selection="coupling")

    def test_wrong_hash_and_missing_variant_tag_refuse_before_launch(self):
        primary = next(iter(self.calls))
        self.scenario.reserve(primary)
        for data, error in ((self.fake.read_bytes() + b"\n# changed\n", "SHA-256"),
                            (self.fake.read_bytes().replace(gate_zero.VARIANT_TAG, b"wrong-tag"), "identify")):
            with self.subTest(error=error):
                wrong = self.root / "wrong-engine"
                wrong.write_bytes(data)
                wrong.chmod(0o755)
                with self.assertRaisesRegex(reference_validation.CallRefused, error):
                    self.call(primary, "refused", binary=wrong)
                self.assertFalse(self.launched("refused"))
                self.assertEqual(self.scenario.entries(primary), {})
                self.assertEqual(self.scenario.api.launch_tags(), [])
                with mock.patch.object(reference_validation, "REPO_ROOT", self.root):
                    call = {**self.calls[primary], "binary": wrong.name}
                    args = SimpleNamespace(manifest="coupling", ledger_root=self.scenario.root, key=self.key_file)
                    with self.assertRaisesRegex(gate_zero.GateZeroRefusal, error):
                        gate0_operator.call_argv(call, args, self.root / "refused")

    def test_operator_argv_selects_coupling_and_preserves_the_row(self):
        call = next(iter(self.calls.values()))
        args = SimpleNamespace(manifest="coupling", ledger_root=self.scenario.root, key=self.key_file)
        with mock.patch.object(reference_validation, "REPO_ROOT", self.root):
            listed = {**call, "binary": self.fake.name}
            argv = gate0_operator.call_argv(listed, args, self.root / "out")
        self.assertEqual(argv[-2:], ["--manifest", "coupling"])
        self.assertIn(call["id"], argv)

    def test_signed_calls_keep_exact_thresholds_and_replay_bytes(self):
        first = self.run_pair(0, 82.671)
        second = self.run_pair(2, 133.441)
        self.assertIsNone(first["coupling"]["predicate"])
        self.assertTrue(second["coupling"]["predicate"])
        for entry in second["calls"]:
            evaluation = entry["coupling"]
            self.assertEqual(evaluation["fraction"], "0.85")
            self.assertEqual(evaluation["fraction_exact"], "17/20")
            self.assertTrue(evaluation["threshold_met"])
            self.assertEqual(evaluation["maximizing_node"], "layer_4_Chiplet_0")
            self.assertIn("chiplet_block_values_C", evaluation["diagnostics"])
            self.assertIn("active_layer_grid_peak", evaluation["diagnostics"])
            receipt = json.loads((self.scenario.run_dir(entry["call"]) / "receipt.json").read_text())
            self.assertEqual(receipt["coupling"], evaluation)
        self.assertTrue(all(row["replay_byte_identical"] for row in second["rows"]))
        self.assertEqual({p.name: p.read_bytes() for p in self.old_dir.glob("*.json")}, self.old_bytes)
        self.assertNotEqual(self.scenario.dir, self.old_dir)

    def test_report_detects_different_replay_bytes_even_with_equal_maximum(self):
        # Changing a non-maximizing block keeps the selector unchanged but must fail replay identity.
        fake = self.fake.read_text().replace('open("sample.steady", "w").write',
            'if case.get("different"):\n    steady[-1] = "inode_0\\t321.00"\nopen("sample.steady", "w").write')
        self.fake.write_text(fake)
        self.write_provenance(self.fake, "material_only")
        self.patch(coupling_allocation, "BINARY_SHA256", fixtures._sha256(self.fake))
        self.manifest, self.manifest_sha256 = reference_validation.load_manifest(selection="coupling")
        self.calls = {row["id"]: row for row in self.manifest["calls"]}
        self.scenario = self.grant("different", cap=234, grant_id="g49-different")
        primary, replay = list(self.calls)[:2]
        self.control_case(replay, peak_c=82, different=True)
        for name in (primary, replay):
            if name == primary:
                self.control_case(name, peak_c=82)
            self.scenario.reserve(name)
            result = self.call(name, name)
            self.assertEqual(result["status"], "exited")
            self.scenario.settle(name)
        report = reference_validation.report(ledger_root=self.scenario.root, tags=self.scenario.tags,
                                             selection="coupling")
        self.assertFalse(report["rows"][0]["replay_byte_identical"])
        self.assertFalse(report["coupling"]["predicate"])

    def test_report_recomputes_instead_of_trusting_a_signed_evaluation(self):
        sign = reference_validation._sign_receipt

        def forged_evaluation(context, receipt):
            altered = {**receipt, "coupling": {"threshold_met": False, "fraction_exact": "0"}}
            return sign(context, altered)

        with mock.patch.object(reference_validation, "_sign_receipt", side_effect=forged_evaluation):
            report = self.run_pair(0, 82.671)
        self.assertTrue(report["rows"][0]["predicate"])
        self.assertEqual(report["calls"][0]["coupling"]["fraction_exact"], "17/20")

    def test_report_refuses_a_signed_receipt_with_another_binary(self):
        sign = reference_validation._sign_receipt

        def other_binary(context, receipt):
            altered = {**receipt, "evaluator": {"kind": "material_only", "binary_sha256": "different"}}
            return sign(context, altered)

        with mock.patch.object(reference_validation, "_sign_receipt", side_effect=other_binary):
            report = self.run_pair(0, 82.671)
        self.assertIsNone(report["coupling"]["predicate"])
        self.assertFalse(report["calls"][0]["usable"])
        self.assertIn("pinned material-only binary", report["calls"][0]["reason"])


class FrozenEvaluationTests(unittest.TestCase):
    def test_both_sides_of_each_exact_threshold_use_the_native_maximum(self):
        calls = coupling_allocation.build_manifest()["calls"]
        # Kelvin text, exact hand-computed fraction, predicate: +/- 0.001 C around each boundary.
        cases = ((calls[0], (("355.820", "4075/4794", True), ("355.821", "17/20", True),
                            ("355.822", "10187/11985", False))),
                 (calls[2], (("406.590", "9923/11674", True), ("406.591", "17/20", True),
                            ("406.592", "24807/29185", False))))
        for call, values in cases:
            with tempfile.TemporaryDirectory() as temp:
                directory = Path(temp) / "run"
                shutil.copytree(fixtures.REPO_ROOT / gate_zero.reference(call["reference"]).inputs, directory)
                fixtures.write_outputs(directory, 70)
                original = (directory / "sample.steady").read_text()
                for kelvin, exact, expected in values:
                    with self.subTest(reference=call["reference"], kelvin=kelvin):
                        lines = [f"inode_0\t{kelvin}" if line.startswith("inode_0\t") else line
                                 for line in original.splitlines()]
                        (directory / "sample.steady").write_text("\n".join(lines) + "\n")
                        record = slab049.summarize_evaluation(directory, grid_size=64)
                        result = coupling_allocation.evaluate_call(call, directory, record,
                            {"kind": "material_only", "binary_sha256": call["binary_sha256"]})
                        self.assertEqual(result["fraction_exact"], exact)
                        self.assertIs(result["threshold_met"], expected)
                        self.assertEqual(result["maximizing_node"], "inode_0")
                        self.assertLess(result["diagnostics"]["chiplet_block_values_C"]["Chiplet_0"], 71)
                        with self.assertRaisesRegex(gate_zero.GateZeroRefusal, "pinned"):
                            coupling_allocation.evaluate_call(call, directory, record,
                                {"kind": "material_only", "binary_sha256": "different"})

    def test_sub_decimal_context_residual_is_not_rounded_into_a_pass(self):
        call = coupling_allocation.build_manifest()["calls"][0]
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / "run"
            shutil.copytree(fixtures.REPO_ROOT / gate_zero.reference(call["reference"]).inputs, directory)
            fixtures.write_outputs(directory, 70)
            path = directory / "sample.steady"
            lines = ["inode_0\t355.821000000000000000000000000001" if line.startswith("inode_0\t") else line
                     for line in path.read_text().splitlines()]
            path.write_text("\n".join(lines) + "\n")
            result = coupling_allocation.evaluate_call(call, directory,
                slab049.summarize_evaluation(directory, grid_size=64),
                {"kind": "material_only", "binary_sha256": call["binary_sha256"]})
            self.assertFalse(result["threshold_met"])
            self.assertEqual(result["T_variant_C"], "82.671000000000000000000000000001")


class OperatorSelectionTests(fixtures.OperatorCase):
    def test_operator_imports_validation_from_the_checkout_being_reviewed(self):
        stale = self.root / "stale-image"
        (stale / "sundai_hotspot").mkdir(parents=True)
        (stale / "sundai_hotspot/reference_validation.py").write_text("# previous image's validation module\n")
        code = '''import importlib.util, sys
from pathlib import Path
stale, checkout = sys.argv[1:]
sys.path[:0] = [stale, checkout]
spec = importlib.util.spec_from_file_location("operator_under_test", Path(checkout)/"sundai_hotspot/gate0_operator.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(module.reference_validation.__file__)
'''
        result = subprocess.run([sys.executable, "-c", code, str(stale), str(fixtures.REPO_ROOT)],
                                cwd=self.root, text=True, capture_output=True, check=True)
        self.assertEqual(Path(result.stdout.strip()).resolve(),
                         fixtures.REPO_ROOT / "sundai_hotspot/reference_validation.py")

    def run_operator(self, selection="gate0"):
        scenario = self.grant()
        manifest, digest = reference_validation.load_manifest(selection=selection)
        args = SimpleNamespace(ledger_root=scenario.root, key=self.key_file, grant_id=scenario.grant_id, only=None)
        if selection == "coupling":
            args.manifest, args.grant_id, args.cap = selection, "g49-coupling", None
            with mock.patch.object(gate0_operator, "LOG", self.root / "operator.log"), \
                    contextlib.redirect_stdout(io.StringIO()):
                gate0_operator.cmd_grant(args)
        build = scenario.api("POST", "/git/commits", {"message": "synthetic build", "tree": fixtures.EMPTY_TREE,
                                                     "parents": []})["sha"]
        launched = []

        def engine(call, argv, out, budget):
            launched.append(call["id"])
            if selection == "gate0":
                self.assertNotIn("--manifest", argv)
            else:
                self.assertEqual(argv[-2:], ["--manifest", "coupling"])
            return {"survivors": [], "summary": {"status": "exited", "charged_cpu_s": 0,
                "settle_tag_message": gate0_anchor.tag_message("settle", args.grant_id, digest,
                    call["id"], status="exited", receipt_sha256=None, outputs={}, charged_cpu_s=0)},
                "exit": 0, "cpu_s_this_call": 0, "cumulative_cpu_s": 0, "out": str(out), "meter_errors": [],
                "killed": None}

        # This test exercises dispatch and the signed grant. Binary checks have separate prelaunch tests.
        with mock.patch.dict(os.environ, BUILD_SHA=build), mock.patch.object(gate0_operator, "github", return_value=scenario.api), \
                mock.patch.object(gate0_operator, "cgroup_cpu_s", return_value=0), \
                mock.patch.object(gate0_operator, "carried_cpu_s", return_value=0), \
                mock.patch.object(gate0_operator, "RUNS", self.root / "runs"), \
                mock.patch.object(gate0_operator, "LOG", self.root / "operator.log"), \
                mock.patch.object(coupling_allocation, "require_binary"), \
                mock.patch.object(gate0_operator, "run_call", side_effect=engine), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(gate0_operator.cmd_run(args), 0)
        self.assertEqual(launched, [row["id"] for row in manifest["calls"]])
        return launched

    def test_default_run_dispatches_only_the_twelve_gate_calls(self):
        launched = self.run_operator()
        self.assertEqual(len(launched), 12)

    def test_explicit_run_dispatches_only_the_four_coupling_calls(self):
        self.assertEqual(len(self.run_operator("coupling")), 4)

    def test_cli_keeps_coupling_cpu_carry_and_logs_separate(self):
        paths = []
        with mock.patch.object(gate0_operator, "cmd_grant", side_effect=lambda args: paths.append(
                (gate0_operator.RUNS, gate0_operator.CPU_FILE, gate0_operator.LOG)) or 0), \
                mock.patch.object(Path, "mkdir"):
            gate0_operator.main(["grant", "--manifest", "coupling", "--grant-id", "g49-coupling"])
            gate0_operator.main(["grant", "--grant-id", "g49-default"])
        self.assertEqual(paths[0], (Path("/srv/gate0/coupling/runs"),
            Path("/srv/gate0/coupling/runs/cpu-used.json"), Path("/srv/gate0/coupling/runs/operator-log.jsonl")))
        self.assertEqual(paths[1], (Path("/srv/gate0/runs"), Path("/srv/gate0/runs/cpu-used.json"),
                                   Path("/srv/gate0/runs/operator-log.jsonl")))

    def test_coupling_grant_preserves_the_consumed_gate_ledger(self):
        gate = self.grant()
        # All twelve consumed reservations and settlements remain byte-for-byte unchanged.
        gate.fabricate({name: 75 for name in self.calls})
        before = {p.name: p.read_bytes() for p in gate.dir.glob("*.json")}
        args = SimpleNamespace(manifest="coupling", ledger_root=gate.root, key=self.key_file,
                               grant_id="g49-coupling", cap=None)
        with mock.patch.object(gate0_operator, "LOG", self.root / "operator.log"), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(gate0_operator.cmd_grant(args), 0)
        manifest, digest = reference_validation.load_manifest(selection="coupling")
        separate = gate0_anchor.read_ledger(gate.root, self.public, digest)
        self.assertEqual(separate["grant"]["calls"], sorted(row["id"] for row in manifest["calls"]))
        self.assertEqual(separate["grant"]["cpu_cap_s"], 234)
        self.assertNotEqual(separate["dir"], gate.dir)
        self.assertEqual(before, {p.name: p.read_bytes() for p in gate.dir.glob("*.json")})


if __name__ == "__main__":
    unittest.main()
