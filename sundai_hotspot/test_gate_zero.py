"""Gate zero (SLAB-049): pinned references, identities, evidence-bound records, the manifest-bound bootstrap entry
and the selector. No solves: the "binaries" are placeholders or a tiny fake that writes synthetic outputs.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from sundai_hotspot import gate_zero, reference_validation, slab049
from sundai_hotspot.coupling_variant import strip_variant_blocks
from sundai_hotspot.evaluators import HotSpot6Oracle, make_oracle
from sundai_hotspot.gate_zero import (
    GATE, HOTSPOT6_TAG, PINNED_REFERENCES_SHA256, REFERENCES, TOLERANCE_K, TOLERANCE_LABEL, VARIANT_TAG,
    GateZeroRefusal, build_record, evaluator_identity, references_sha256, require_gate_zero, tap_selector_c,
    tap_stdout_selector_c,
)
from sundai_hotspot.reference_validation import CallRefused, validate_call
from sundai_hotspot.tap_oracle import REPO_ROOT, HotSpotOracle, HotSpotOracleError

HS6_ROOT = REPO_ROOT / "sundai_hotspot6"
FAKE_BINARIES = {
    "hotspot7_default": b"HotSpot 7 placeholder: microchannel support",
    "material_only": b"HotSpot 7 placeholder: microchannel support; " + VARIANT_TAG,
    "hotspot6": b"HotSpot 6.0 placeholder: Unit\tSteady(Kelvin) dgssv " + HOTSPOT6_TAG,
    "hotspot6_tap_faithful": b"HotSpot 6.0 placeholder: Unit\tSteady(Kelvin)",
}
GATE_IDS = [r.id for r in REFERENCES if r.role == GATE]
IN_WINDOW = datetime(2026, 10, 31, 16, 0, tzinfo=timezone.utc)


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_outputs(run: Path, peak_c: float, drop_k: float = 1.0, side: int = 4) -> None:
    """Synthetic steady, stdout and all-layer grid files, as a HotSpot run would leave them."""
    kelvin = peak_c + 273.15
    (run / "sample.steady").write_text(f"layer_4_WS_0\t{kelvin - 20:.2f}\nlayer_4_Chiplet_0\t{kelvin:.2f}\n"
                                       f"hsp_TIM\t{kelvin - 30:.2f}\ninode_0\t{kelvin - 40:.2f}\n", encoding="utf-8")
    (run / "stdout.txt").write_text("Unit\tSteady(Kelvin)\n" + (run / "sample.steady").read_text(), encoding="utf-8")
    (run / "stderr.txt").write_text("", encoding="utf-8")
    with (run / "sample.grid.steady").open("w", encoding="utf-8") as grid:
        for layer in range(8):
            grid.write(f"Layer {layer}:\n")
            base = 380.0 if layer < 7 else 380.0 - drop_k
            for cell in range(side * side):
                grid.write(f"{cell}\t{base:.2f}\n")


def fabricate_runs(root: Path, kind: str, binary: Path, simulated: dict[str, float], grid: int = 64) -> dict[str, Path]:
    """Run directories as validate-reference leaves them, with synthetic outputs instead of a solve."""
    identity = evaluator_identity(kind, binary)
    dirs = {}
    for reference in REFERENCES:
        if reference.id not in simulated:
            continue
        run = root / f"{kind}-{reference.id}"
        shutil.copytree(REPO_ROOT / reference.inputs, run)
        write_outputs(run, simulated[reference.id])
        receipt = {"schema": gate_zero.RECEIPT_SCHEMA, "evaluator": identity, "reference": reference.id, "grid": grid,
                   "status": "exited", "exit_status": 0, "inputs": gate_zero.frozen_inputs(reference),
                   "outputs": {name: _sha256(run / name) for name in gate_zero.RECEIPT_OUTPUTS}}
        (run / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
        dirs[reference.id] = run
    return dirs


def passing_record(root: Path, kind: str, binary: Path) -> dict:
    return build_record(kind, binary, fabricate_runs(root, kind, binary, {"ascend910-original-snapped": 75.09,
                                                                          "micro150-original-snapped": 116.27}))


class TempDirCase(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory(prefix="gate-zero-")
        self.root = Path(self._directory.name)
        self.binaries = {}
        for kind, data in FAKE_BINARIES.items():
            path = self.root / f"bin-{kind}"
            path.write_bytes(data)
            self.binaries[kind] = path

    def tearDown(self):
        self._directory.cleanup()


class PinnedReferenceTests(unittest.TestCase):
    def test_references_values_roles_and_digest_are_pinned(self):
        self.assertEqual(references_sha256(), PINNED_REFERENCES_SHA256)
        self.assertEqual({r.id: (r.role, r.paper_c) for r in REFERENCES}, {
            "ascend910-original-snapped": (GATE, 75.48), "micro150-original-snapped": (GATE, 115.94),
            "ascend910-original-raw": (gate_zero.RAW_NEXT, 75.48), "micro150-original-raw": (gate_zero.RAW_NEXT, 115.94),
            "ascend910-tap": (gate_zero.VERIFICATION, 75.47), "micro150-tap": (gate_zero.VERIFICATION, 94.89)})
        self.assertEqual((TOLERANCE_K, TOLERANCE_LABEL, gate_zero.GRID, gate_zero.INTERPOSER_MM),
                         (1.0, "prospective computational reference-reproduction tolerance", 64, 45))

    def test_frozen_inputs_are_fresh_45_mm_tap_configs(self):
        for reference in REFERENCES:
            if reference.inputs is None:
                continue
            config = slab049.read_hotspot_config(REPO_ROOT / reference.inputs / "new_hotspot.config")
            self.assertEqual((config["r_convec"], config["s_sink"], config["s_spreader"], config["grid_rows"],
                              config["grid_map_mode"]), ("0.011111111111111112", "0.18", "0.09", "64", "center"))
            for name, digest in gate_zero.frozen_inputs(reference).items():
                self.assertEqual(_sha256(REPO_ROOT / reference.inputs / name), digest)

    def test_snapped_references_are_legal_and_raw_ones_are_the_decoded_centres(self):
        for layout, variant in slab049.REFERENCE_SETS:
            spec = slab049.reference_spec(layout, variant)
            self.assertEqual(spec["legality_problems"], [], (layout, variant))
            if variant == "snapped":
                self.assertTrue(all(float(v).is_integer() for v in spec["x"] + spec["y"]))
            else:
                self.assertEqual([[x, y] for x, y in zip(spec["x"], spec["y"])],
                                 slab049.REFERENCE_LAYOUTS[layout]["centers_mm"])

    def test_a_changed_reference_input_changes_the_pinned_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for reference in REFERENCES:
                if reference.inputs:
                    shutil.copytree(REPO_ROOT / reference.inputs, root / reference.inputs)
            self.assertEqual(references_sha256(root), PINNED_REFERENCES_SHA256)
            sums = root / REFERENCES[0].inputs / "SHA256SUMS"
            sums.write_text(sums.read_text() + "0" * 64 + "  extra.flp\n")
            self.assertNotEqual(references_sha256(root), PINNED_REFERENCES_SHA256)


class EvaluatorIdentityTests(TempDirCase):
    def test_each_kind_accepts_its_own_binary_and_refuses_the_others(self):
        for kind, path in self.binaries.items():
            self.assertEqual(evaluator_identity(kind, path)["binary_sha256"], _sha256(path))
            for other, other_path in self.binaries.items():
                if other != kind:
                    with self.assertRaises(GateZeroRefusal, msg=f"{kind} accepted a {other} binary"):
                        evaluator_identity(kind, other_path)

    def test_missing_binary_and_unknown_kind_are_refused(self):
        with self.assertRaises(GateZeroRefusal):
            evaluator_identity("hotspot6", self.root / "absent")
        with self.assertRaises(GateZeroRefusal):
            evaluator_identity("hotspot8", self.binaries["hotspot6"])

    @unittest.skipUnless((HS6_ROOT / "hotspot").is_file() and (HS6_ROOT / "hotspot-tap-faithful").is_file(),
                         "both HotSpot 6.0 binaries are built in the image")
    def test_built_hotspot6_binaries_identify_correctly(self):
        evaluator_identity("hotspot6", HS6_ROOT / "hotspot")
        evaluator_identity("hotspot6_tap_faithful", HS6_ROOT / "hotspot-tap-faithful")
        with self.assertRaises(GateZeroRefusal):
            evaluator_identity("hotspot6", HS6_ROOT / "hotspot-tap-faithful")
        with self.assertRaises(GateZeroRefusal):
            evaluator_identity("hotspot7_default", HS6_ROOT / "hotspot")

    def test_temperature_labels_never_call_a_simulation_measured(self):
        for kind, label in gate_zero.TEMPERATURE_LABELS.items():
            self.assertTrue(label.startswith("simulated ("), kind)
            self.assertNotIn("measured", label)
        self.assertIn("withdrawn pending the HS6 correction", gate_zero.TEMPERATURE_LABELS["hotspot7_default"])


class SelectorTests(unittest.TestCase):
    def test_steady_selector_is_the_maximum_block(self):
        with tempfile.TemporaryDirectory() as directory:
            write_outputs(Path(directory), 75.48)
            value, block = tap_selector_c(Path(directory) / "sample.steady")
            self.assertAlmostEqual(value, 75.48, places=9)
            self.assertEqual(block, "layer_4_Chiplet_0")

    def test_stdout_selector_reads_hotspot6_output_and_not_hotspot7_output(self):
        with tempfile.TemporaryDirectory() as directory:
            stdout = Path(directory) / "stdout.txt"
            stdout.write_text("Unit\tSteady(Kelvin)\nlayer_4_Chiplet_0\t348.63\ninode_0\t320.00\n", encoding="utf-8")
            self.assertAlmostEqual(tap_stdout_selector_c(stdout), 75.48, places=9)
            stdout.write_text("Parsing input files...\nCreating thermal circuit...\nSimulation complete.\n")
            with self.assertRaises(ValueError):
                tap_stdout_selector_c(stdout)

    def test_steady_reader_rejects_duplicates_and_garbage(self):
        with tempfile.TemporaryDirectory() as directory:
            steady = Path(directory) / "sample.steady"
            for text in ("a\t330.00\na\t331.00\n", "a\tnan\n", "a\tinf\n", "a\t-1.00\n", "a\t5000.00\n", "\n"):
                steady.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError, msg=text):
                    gate_zero.read_steady_values(steady)


class RecordTests(TempDirCase):
    GOOD = {"ascend910-original-snapped": 75.48, "micro150-original-snapped": 115.94}

    def test_within_tolerance_passes_and_binds_the_binary(self):
        record = passing_record(self.root, "hotspot6", self.binaries["hotspot6"])
        self.assertEqual(record["verdict"], "PASS")
        self.assertEqual(require_gate_zero("hotspot6", self.binaries["hotspot6"], record)["verdict"], "PASS")
        rebuilt = self.root / "rebuilt"
        rebuilt.write_bytes(FAKE_BINARIES["hotspot6"] + b" rebuilt")
        with self.assertRaises(GateZeroRefusal):
            require_gate_zero("hotspot6", rebuilt, record)

    def test_a_gate_reference_outside_tolerance_fails(self):
        runs = fabricate_runs(self.root, "hotspot6", self.binaries["hotspot6"],
                              {**self.GOOD, "micro150-original-snapped": 115.94 + 1.01})
        record = build_record("hotspot6", self.binaries["hotspot6"], runs)
        self.assertEqual(record["verdict"], "FAIL")
        with self.assertRaises(GateZeroRefusal):
            require_gate_zero("hotspot6", self.binaries["hotspot6"], record)

    def test_a_simulated_verification_point_cannot_be_contradicted(self):
        runs = fabricate_runs(self.root, "hotspot6", self.binaries["hotspot6"], {**self.GOOD, "ascend910-tap": 77.0})
        self.assertEqual(build_record("hotspot6", self.binaries["hotspot6"], runs)["verdict"], "FAIL")

    def test_editing_a_fail_record_never_unlocks(self):
        """astra #56837: an edited simulated value or verdict on a FAIL record must not unlock search."""
        binary = self.binaries["hotspot6"]
        runs = fabricate_runs(self.root, "hotspot6", binary, {"ascend910-original-snapped": 122.32,
                                                              "micro150-original-snapped": 229.35})
        record = build_record("hotspot6", binary, runs)
        forged = json.loads(json.dumps(record))
        forged["verdict"] = "PASS"
        for result in forged["results"]:
            result["simulated_c"], result["delta_k"], result["within_tolerance"] = result["paper_c"], 0.0, True
        with self.assertRaises(GateZeroRefusal):
            require_gate_zero("hotspot6", binary, forged)
        with self.assertRaises(GateZeroRefusal):
            make_oracle("hotspot6", "search", 16, 16, hotspot_binary=binary, gate_zero_record=forged)

    def test_raw_evidence_edits_are_refused(self):
        binary = self.binaries["hotspot6"]
        record = passing_record(self.root / "a", "hotspot6", binary)
        run = Path(record["results"][0]["run_dir"])
        steady = run / "sample.steady"
        steady.write_text(steady.read_text() + "layer_4_WS_9\t330.00\n", encoding="utf-8")
        with self.assertRaises(GateZeroRefusal):  # the output no longer matches its receipt digest
            require_gate_zero("hotspot6", binary, record)
        record = passing_record(self.root / "b", "hotspot6", binary)
        receipt = Path(record["results"][0]["run_dir"]) / "receipt.json"
        receipt.write_text(receipt.read_text().replace('"grid": 64', '"grid":  64'), encoding="utf-8")
        with self.assertRaises(GateZeroRefusal):  # the receipt changed after the record
            require_gate_zero("hotspot6", binary, record)
        record = passing_record(self.root / "c", "hotspot6", binary)
        nameless = json.loads(json.dumps(record))
        del nameless["results"][0]["run_dir"]
        with self.assertRaises(GateZeroRefusal):  # a record must name its raw evidence
            require_gate_zero("hotspot6", binary, nameless)

    def test_receipt_digests_must_be_complete_and_correct(self):
        binary = self.binaries["hotspot6"]
        for edit in ("drop grid digest", "wrong steady digest", "unbound input"):
            with self.subTest(edit=edit):
                runs = fabricate_runs(self.root / edit.replace(" ", "-"), "hotspot6", binary, self.GOOD)
                receipt_path = runs[GATE_IDS[0]] / "receipt.json"
                receipt = json.loads(receipt_path.read_text())
                if edit == "drop grid digest":
                    del receipt["outputs"]["sample.grid.steady"]
                elif edit == "wrong steady digest":
                    receipt["outputs"]["sample.steady"] = "0" * 64
                else:
                    receipt["inputs"]["new_hotspot.config"] = "0" * 64
                receipt_path.write_text(json.dumps(receipt))
                with self.assertRaises(GateZeroRefusal):
                    build_record("hotspot6", binary, runs)

    def test_receipts_must_be_completed_grid_64_runs_of_this_binary_on_the_frozen_inputs(self):
        binary = self.binaries["hotspot6"]
        with self.assertRaises(GateZeroRefusal):
            build_record("hotspot6", binary, fabricate_runs(self.root / "g32", "hotspot6", binary, self.GOOD, grid=32))
        runs = fabricate_runs(self.root / "other", "hotspot6", binary, self.GOOD)
        receipt = runs[GATE_IDS[0]] / "receipt.json"
        data = json.loads(receipt.read_text())
        data["evaluator"]["binary_sha256"] = "0" * 64
        receipt.write_text(json.dumps(data))
        with self.assertRaises(GateZeroRefusal):
            build_record("hotspot6", binary, runs)
        runs = fabricate_runs(self.root / "stale", "hotspot6", binary, self.GOOD)
        config = runs[GATE_IDS[0]] / "new_hotspot.config"
        config.write_text(config.read_text().replace("0.011111111111111112", "0.1"))
        with self.assertRaises(GateZeroRefusal):
            build_record("hotspot6", binary, runs)

    def test_the_spreader_sink_drop_is_reported_not_asserted(self):
        binary = self.binaries["hotspot6"]
        runs = fabricate_runs(self.root, "hotspot6", binary, self.GOOD)
        write_outputs(runs[GATE_IDS[0]], 75.48, drop_k=51.0)
        receipt = runs[GATE_IDS[0]] / "receipt.json"
        data = json.loads(receipt.read_text())
        data["outputs"] = {name: _sha256(runs[GATE_IDS[0]] / name) for name in gate_zero.RECEIPT_OUTPUTS}
        receipt.write_text(json.dumps(data))
        record = build_record("hotspot6", binary, runs)
        self.assertEqual(record["verdict"], "PASS")
        drop = record["results"][0]["spreader_sink_drop_diagnostic"]
        self.assertAlmostEqual(drop["drop_K"], 51.0, places=6)
        self.assertEqual((drop["spreader_K"], drop["sink_K"]), (380.0, 329.0))
        self.assertIn("copper predicts about 1-2 K", drop["expectation"])

    def test_no_record_is_refused(self):
        with self.assertRaises(GateZeroRefusal):
            require_gate_zero("hotspot6", self.binaries["hotspot6"], None)


class SelectorAndOracleTests(TempDirCase):
    """Search and headroom need a PASS; the selector keeps HotSpot 7's oracle unchanged."""

    def test_search_and_headroom_refuse_without_a_pass(self):
        for purpose in ("search", "headroom"):
            with self.assertRaises(GateZeroRefusal):
                make_oracle("hotspot6", purpose, 16, 16, hotspot_binary=self.binaries["hotspot6"])
            with self.assertRaises(GateZeroRefusal):
                make_oracle("hotspot7", purpose, 16, 16, hotspot_binary=self.binaries["hotspot7_default"])
        with self.assertRaises(ValueError):
            make_oracle("hotspot6", "validate-reference", 16, 16, hotspot_binary=self.binaries["hotspot6"])

    def test_a_pass_receipt_unlocks_search_with_a_new_identity(self):
        binary = self.binaries["hotspot6"]
        record = passing_record(self.root, "hotspot6", binary)
        oracle = make_oracle("hotspot6", "search", 16, 16, hotspot_binary=binary, gate_zero_record=record)
        self.assertIsInstance(oracle, HotSpot6Oracle)
        base = HotSpotOracle(16, 16, hotspot_binary=binary)
        self.assertEqual(oracle.base_problem_hash, base.problem_hash)
        self.assertNotEqual(oracle.problem_hash, base.problem_hash)
        self.assertTrue(oracle.solver_version.startswith(f"HotSpot-6.0:{gate_zero.HOTSPOT6_COMMIT}+SLAB-049:"))
        self.assertTrue(base.solver_version.startswith("HotSpot-7:"))
        v7 = passing_record(self.root / "v7", "hotspot7_default", self.binaries["hotspot7_default"])
        production = make_oracle("hotspot7", "headroom", 16, 16, hotspot_binary=self.binaries["hotspot7_default"],
                                 gate_zero_record=v7)
        self.assertIs(type(production), HotSpotOracle)

    def test_hotspot6_oracle_refuses_evaluations_and_the_wrong_binary(self):
        oracle = HotSpot6Oracle(16, 16, hotspot_binary=self.binaries["hotspot6"])
        design = oracle.design_from_centers(((25, 25), (40, 40), (8, 9), (8, 25), (8, 41), (41, 15)))
        with self.assertRaises(GateZeroRefusal):
            asyncio.run(oracle(design))
        with self.assertRaises(HotSpotOracleError):
            HotSpot6Oracle(16, 16, hotspot_binary=self.binaries["hotspot6_tap_faithful"])


FAKE_SOLVER = r'''#!PYTHON
# Test-only stand-in for a HotSpot binary: identity markers in this comment, synthetic outputs, no physics.
# markers: Unit	Steady(Kelvin) dgssv SENTILAB_EVALUATOR=hotspot6@a7a3286e;grid_dump=all_layers;ticket=SLAB-049
import os, resource, sys
args = sys.argv[1:]
grid = int(args[args.index("-grid_rows") + 1]) if "-grid_rows" in args else 64
peak = float(os.environ.get("FAKE_PEAK_C", "75.3")) + 273.15
open("rlimit_cpu.txt", "w").write(str(resource.getrlimit(resource.RLIMIT_CPU)[0]))
names = [line.split()[0] for line in open("sampleL4_ChipLayer.flp") if line.strip() and not line.startswith("#")]
steady = ["layer_4_%s\t%.2f" % (n, peak - (0 if n == "Chiplet_0" else 5)) for n in names]
steady += ["hsp_TIM\t%.2f" % (peak - 30), "hsink_TIM\t%.2f" % (peak - 40), "inode_0\t320.00"]
open("sample.steady", "w").write("\n".join(steady) + "\n")
layers = 1 if os.environ.get("FAKE_TRUNCATE") else 8
with open("sample.grid.steady", "w") as out:
    for layer in range(layers):
        out.write("Layer %d:\n" % layer)
        for cell in range(grid * grid):
            out.write("%d\t%.2f\n" % (cell, peak - 1 - layer if cell else peak - layer))
print("Unit\tSteady(Kelvin)")
print("\n".join(steady))
'''


@unittest.skipUnless(os.name == "posix" and platform.machine() == "x86_64",
                     "the manifest lists an x86_64 POSIX host; the fake solver is a POSIX script")
class ManifestEntryTests(TempDirCase):
    """validate-reference: the bootstrap path, bound to the frozen manifest (astra #56794, #56837)."""

    def setUp(self):
        super().setUp()
        self.fake = self.root / "fake-hotspot6"
        self.fake.write_text(FAKE_SOLVER.replace("PYTHON", sys.executable), encoding="utf-8")
        self.fake.chmod(0o755)
        self.ledger = self.root / "ledger"

    def call(self, call_id: str, out: str, **kwargs) -> dict:
        return validate_call(call_id, self.root / out, self.ledger, binary=kwargs.pop("binary", self.fake),
                             now=kwargs.pop("now", IN_WINDOW), **kwargs)

    def test_anything_not_in_the_manifest_is_refused_before_dispatch(self):
        refusals = {
            "unlisted call": dict(call_id="u-hs6-ascend910-original-g64"),
            "deferred reference": dict(call_id="p-hs6-ascend910-original-g64", reference="ascend910-original-raw"),
            "grid 128": dict(call_id="p-hs6-ascend910-original-g64", grid=128),
            "other engine": dict(call_id="p-hs6-ascend910-original-g64", kind="hotspot6_tap_faithful"),
            "timeout 1e6": dict(call_id="p-hs6-ascend910-original-g64", timeout_s=1e6),
            "after the window": dict(call_id="p-hs6-ascend910-original-g64",
                                     now=datetime(2026, 11, 1, 12, 0, 1, tzinfo=timezone.utc)),
        }
        with mock.patch("sundai_hotspot.reference_validation.subprocess.run") as dispatch:
            for rule, arguments in refusals.items():
                with self.subTest(rule=rule), self.assertRaises(CallRefused):
                    call_id = arguments.pop("call_id")
                    self.call(call_id, f"out-{rule.replace(' ', '-')}", **arguments)
            with mock.patch("sundai_hotspot.reference_validation.platform.machine", return_value="aarch64"):
                with self.assertRaises(CallRefused):
                    self.call("p-hs6-ascend910-original-g64", "out-host")
            dispatch.assert_not_called()
        self.assertFalse(self.ledger.exists() and any(self.ledger.iterdir()), "a refused call must not be reserved")

    def test_bootstrap_receipts_need_no_pass_bind_every_field_and_unlock_search(self):
        with self.assertRaises(GateZeroRefusal):
            make_oracle("hotspot6", "search", 16, 16, hotspot_binary=self.fake)
        runs = {}
        for call_id, reference_id, peak in (("p-hs6-ascend910-original-g64", "ascend910-original-snapped", 75.30),
                                            ("p-hs6-micro150-original-g64", "micro150-original-snapped", 116.50)):
            with mock.patch.dict(os.environ, {"FAKE_PEAK_C": str(peak)}):
                receipt = self.call(call_id, call_id)
            self.assertEqual((receipt["status"], receipt["exit_status"]), ("exited", 0))
            self.assertEqual((Path(self.root / call_id) / "rlimit_cpu.txt").read_text(), "60")  # the CPU cap
            record = receipt["solve_record"]
            self.assertEqual(record["config_sha256"], receipt["inputs"]["new_hotspot.config"])
            for field in ("active_layer_grid_peak", "chiplet_centre_mapping", "historical_tap_stdout_selector",
                          "spreader_sink_hottest_cell_rises", "spreader_sink_drop_diagnostic"):
                self.assertIn(field, record)
            self.assertNotIn("measured", json.dumps(receipt))
            self.assertTrue((self.ledger / f"{call_id}.reserved.json").is_file())
            self.assertTrue((self.ledger / f"{call_id}.settled.json").is_file())
            runs[reference_id] = self.root / call_id
        with self.assertRaises(CallRefused):  # each call runs once
            self.call("p-hs6-ascend910-original-g64", "again")
        result = build_record("hotspot6", self.fake, runs)
        self.assertEqual(result["verdict"], "PASS")
        oracle = make_oracle("hotspot6", "search", 16, 16, hotspot_binary=self.fake, gate_zero_record=result)
        self.assertIsNotNone(oracle.gate_zero)
        report = reference_validation.report(list(runs.values()))
        self.assertEqual({row["reference"] for row in report["rows"]}, set(runs))

    def test_a_launch_failure_keeps_a_settled_receipt(self):
        unlaunchable = self.root / "not-executable"
        unlaunchable.write_bytes(FAKE_BINARIES["hotspot6"])
        unlaunchable.chmod(0o644)
        receipt = self.call("p-hs6-ascend910-original-g64", "launch", binary=unlaunchable)
        self.assertEqual(receipt["status"], "launch_error")
        on_disk = json.loads((self.root / "launch" / "receipt.json").read_text())
        self.assertEqual(on_disk["status"], "launch_error")
        self.assertIn("finished_utc", on_disk)
        settled = json.loads((self.ledger / "p-hs6-ascend910-original-g64.settled.json").read_text())
        self.assertEqual(settled["status"], "launch_error")

    def test_a_truncated_grid_after_exit_zero_keeps_the_raw_outputs_and_fails(self):
        with mock.patch.dict(os.environ, {"FAKE_TRUNCATE": "1"}):
            receipt = self.call("p-hs6-ascend910-original-g64", "truncated")
        self.assertEqual((receipt["status"], receipt["exit_status"]), ("record_error", 0))
        self.assertIn("GridFormatError", receipt["error"])
        self.assertEqual(set(receipt["outputs"]), set(gate_zero.RECEIPT_OUTPUTS))
        with self.assertRaises(GateZeroRefusal):
            build_record("hotspot6", self.fake, {"ascend910-original-snapped": self.root / "truncated"})


class VendoredHotSpot6Tests(unittest.TestCase):
    def test_vendored_files_are_the_upstream_blobs(self):
        self.assertEqual((HS6_ROOT / "UPSTREAM_COMMIT").read_text(encoding="ascii").strip(), gate_zero.HOTSPOT6_COMMIT)
        listed = dict(reversed(line.split()) for line in (HS6_ROOT / "UPSTREAM_BLOBS.txt").read_text(encoding="ascii").splitlines())
        vendored = {p.name for p in HS6_ROOT.iterdir() if p.is_file() and p.suffix not in (".o", ".d", ".a")
                    and p.name not in ("hotspot", "hotspot-tap-faithful", "hotfloorplan")}
        self.assertEqual(set(listed), vendored - {"UPSTREAM_COMMIT", "UPSTREAM_BLOBS.txt"})
        for name, blob in listed.items():
            data = (HS6_ROOT / name).read_bytes()
            if name == "temperature_grid.c":  # the writer-only SentiLab block, off by default
                data = strip_variant_blocks(data.decode("latin-1"), "SENTILAB_GRID_DUMP_ALL_LAYERS").encode("latin-1")
            self.assertEqual(hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest(), blob, name)
        self.assertIn("NEITHER THE NAME OF ANY VIRGINIA ENTITY", (HS6_ROOT / "LICENSE").read_text(encoding="ascii"))

    def test_the_sentilab_block_touches_only_the_grid_writer(self):
        source = (HS6_ROOT / "temperature_grid.c").read_text(encoding="latin-1")
        self.assertEqual(source.count("#if SENTILAB_GRID_DUMP_ALL_LAYERS"), 2)
        self.assertIn(HOTSPOT6_TAG.decode("ascii"), source)
        block = source[source.index("#if SENTILAB_GRID_DUMP_ALL_LAYERS"):source.index("#endif", source.index("#if SENTILAB"))]
        for physics in ("find_res_3D", "rz", "getr", "dgssv", "steady_state"):
            self.assertNotIn(physics, block)

    def test_hotspot6_couples_layers_through_the_upper_layer_rz(self):
        source = (HS6_ROOT / "temperature_grid.c").read_text(encoding="latin-1")
        self.assertIn("define BC_det3D(l,n,i,j,nl,nr,nc)\t\t((n < nl-1) ? (1.0/find_res_3D(n, i, j, model,3)) : 0.0)",
                      source)
        self.assertIn("if(l < nl-1) Rb = find_res_3D(l,i,j,model,3);", source)
        self.assertNotIn("double find_res(", source)

    def test_build_script_covers_both_architectures_and_both_binaries(self):
        script = (REPO_ROOT / "scripts" / "build_hotspot6.sh").read_text(encoding="utf-8")
        for needle in ("x86_64|aarch64)", "SUPERLU=0", "SUPERLU=1", "-DSENTILAB_GRID_DUMP_ALL_LAYERS=1",
                       "-ffp-contract=off", "hotspot-tap-faithful", "sha256sum"):
            self.assertIn(needle, script)


class KnownAnswerSlabTests(unittest.TestCase):
    """The analytic slab fixture: declared now, run later under its own 2-call allocation."""

    def test_expected_rises_follow_the_series_resistance(self):
        hs6, hs7 = slab049.known_answer_expected("hotspot6"), slab049.known_answer_expected("hotspot7_default")
        self.assertAlmostEqual(hs6["expected_rise_K"], 54.075, places=9)
        self.assertAlmostEqual(hs7["expected_rise_K"], 80.4825, places=9)
        self.assertAlmostEqual(hs6["tolerance_K"], 0.270375, places=9)
        manifest = slab049.build_call_list()
        slab = next(a for a in manifest["separate_allocations"] if a["id"] == "known-answer-slab")
        self.assertEqual((slab["calls"], slab["in_this_manifest"], slab["gate_zero_calls"]), (2, False, False))
        self.assertEqual(len(manifest["calls"]), 12)

    def test_the_check_reads_the_die_block(self):
        with tempfile.TemporaryDirectory() as directory:
            steady = Path(directory) / "slab.steady"
            for rise, verdict in ((54.075, "PASS"), (54.30, "PASS"), (80.48, "FAIL")):
                steady.write_text(f"layer_0_die\t{318.15 + rise:.2f}\nlayer_1_TIM\t{318.15 + rise - 1:.2f}\n")
                self.assertEqual(slab049.check_known_answer_slab(Path(directory), "hotspot6")["verdict"], verdict)


if __name__ == "__main__":
    unittest.main()
