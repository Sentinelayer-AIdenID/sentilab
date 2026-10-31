"""Gate zero (SLAB-049): raw paper-match references, identities, ledger-assembled records, the manifest-bound
bootstrap entry and the selector. No solves: the "binaries" are placeholders or a tiny fake that writes synthetic
outputs.
"""
from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from sundai_hotspot import gate_zero, provenance, reference_validation, slab049, tap_oracle
from sundai_hotspot.coupling_variant import strip_variant_blocks
from sundai_hotspot.evaluators import EVIDENCE_PREFIX, HotSpot6Oracle, make_oracle
from sundai_hotspot.gate_zero import (
    DEFERRED, GATE, HOTSPOT6_TAG, PINNED_REFERENCES_SHA256, REFERENCES, TOLERANCE_K, TOLERANCE_LABEL, VARIANT_TAG,
    GateZeroRefusal, build_record, call_id, evaluator_identity, references_sha256, require_gate_zero, required_calls,
    tap_selector_c, tap_stdout_selector_c,
)
from sundai_hotspot.reference_validation import CallRefused, validate_call
from sundai_hotspot.tap_oracle import REPO_ROOT, HotSpotOracle, HotSpotOracleError, TapLegalityError

HS6_ROOT = REPO_ROOT / "sundai_hotspot6"
FAKE_BINARIES = {
    "hotspot7_default": b"HotSpot 7 placeholder: microchannel support",
    "material_only": b"HotSpot 7 placeholder: microchannel support; " + VARIANT_TAG,
    "hotspot6": b"HotSpot 6.0 placeholder: Unit\tSteady(Kelvin) dgssv " + HOTSPOT6_TAG,
    "hotspot6_tap_faithful": b"HotSpot 6.0 placeholder: Unit\tSteady(Kelvin)",
}
ASCEND, MICRO = "ascend910-tap25d-fig6a-raw", "micro150-tap25d-fig5a-raw"
REQUIRED = [row["call"] for row in required_calls()]
P_ASCEND, R_ASCEND = call_id("primary", "hotspot6", ASCEND, 64), call_id("replay", "hotspot6", ASCEND, 64)
P_MICRO, R_MICRO = call_id("primary", "hotspot6", MICRO, 64), call_id("replay", "hotspot6", MICRO, 64)
GOOD = {P_ASCEND: 75.09, R_ASCEND: 75.09, P_MICRO: 116.27, R_MICRO: 116.27}
IN_WINDOW = datetime(2026, 10, 31, 16, 0, tzinfo=timezone.utc)
NO_LIBRARIES = {"dynamic": False, "libraries": [], "note": "synthetic"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_outputs(run: Path, peak_c: float, drop_k: float = 1.0, *, grid: int = 64, layers: int = 8,
                  headered: bool = True, omit_block: str | None = None) -> None:
    """Synthetic outputs with the shape HotSpot writes: one steady line per unit of every LCF layer (also on stdout,
    as HotSpot 6.0 prints it) plus package nodes, and a grid file of `layers` sections of grid x grid cells.
    The defaults are the evaluator's real shape (64 x 64, 8 headered layers); other values make shape controls."""
    kelvin = peak_c + 273.15
    lines = []
    for layer in slab049.read_lcf(run / "samplelayers.lcf", run):
        for unit in slab049.read_flp(layer["flp"]):
            name = f"layer_{layer['layer']}_{unit['name']}"
            if name != omit_block:
                lines.append(f"{name}\t{kelvin if name == 'layer_4_Chiplet_0' else kelvin - 20 - layer['layer']:.2f}")
    lines += [f"hsp_TIM\t{kelvin - 30:.2f}", f"hsink_TIM\t{kelvin - 40:.2f}", f"inode_0\t{kelvin - 45:.2f}"]
    (run / "sample.steady").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (run / "stdout.txt").write_text("Unit\tSteady(Kelvin)\n" + "\n".join(lines) + "\n", encoding="utf-8")
    (run / "stderr.txt").write_text("", encoding="utf-8")
    hot = (grid // 4) * grid + grid // 4  # one hot cell, inside the grid
    parts = []
    for layer in range(layers):
        if headered:
            parts.append(f"Layer {layer}:\n")
        base = 380.0 - (drop_k if layer == 7 else 0.0) - (0.5 * layer if layer >= 4 else 0.0)
        parts.append("".join(f"{cell}\t{base + (1.0 if cell == hot else 0.0):.2f}\n" for cell in range(grid * grid)))
    (run / "sample.grid.steady").write_text("".join(parts), encoding="utf-8")


def fabricate_ledger(root: Path, binary: Path, peaks: dict, *, kind: str = "hotspot6",
                     settled: dict[str, tuple] | None = None) -> Path:
    """A ledger and run directories exactly as validate-reference leaves them, with synthetic outputs instead of a
    solve. peaks maps a call id to its peak (C) or to write_outputs keyword arguments; settled maps a call id to a
    (status, exit_status) other than ("exited", 0)."""
    manifest_bytes = reference_validation.MANIFEST_PATH.read_bytes()
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    calls = {c["id"]: c for c in json.loads(manifest_bytes)["calls"]}
    identity = evaluator_identity(kind, binary)
    ledger = root / "ledger"
    ledger.mkdir(parents=True, exist_ok=True)
    for name, peak in peaks.items():
        call = calls[name]
        reference = gate_zero.reference(call["reference"])
        run = root / "runs" / name
        shutil.copytree(REPO_ROOT / reference.inputs, run)
        write_outputs(run, **(peak if isinstance(peak, dict) else {"peak_c": peak}))
        status, exit_status = (settled or {}).get(name, ("exited", 0))
        receipt = {"schema": gate_zero.RECEIPT_SCHEMA, "call": name, "role": call["role"],
                   "replay_of": call["replay_of"], "manifest_sha256": manifest_sha256, "evaluator": identity,
                   "reference": reference.id, "layout_identity": reference.layout_identity,
                   "raw_layout_sha256": reference.raw_layout_sha256, "grid": call["grid"],
                   "status": status, "exit_status": exit_status, "inputs": gate_zero.frozen_inputs(reference),
                   "runtime": NO_LIBRARIES,
                   "outputs": {output: _sha256(run / output) for output in gate_zero.RECEIPT_OUTPUTS}}
        (run / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
        (ledger / f"{name}.reserved.json").write_text(json.dumps({
            "call": name, "manifest_sha256": manifest_sha256, "out": run.as_posix(),
            "reserved_cpu_s": call["accounting"]["reserved_cpu_s"]}), encoding="utf-8")
        (ledger / f"{name}.settled.json").write_text(json.dumps({
            "call": name, "manifest_sha256": manifest_sha256, "status": status, "exit_status": exit_status,
            "charged_cpu_s": 6.0, "receipt_sha256": _sha256(run / "receipt.json")}), encoding="utf-8")
    return ledger


def rebind(ledger: Path, name: str, edit) -> None:
    """A consistent forgery of one receipt: edit it and rebind its settlement, so the deeper checks must act."""
    run = Path(json.loads((ledger / f"{name}.reserved.json").read_text())["out"])
    receipt = json.loads((run / "receipt.json").read_text())
    edit(receipt)
    (run / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    settled = json.loads((ledger / f"{name}.settled.json").read_text())
    settled["receipt_sha256"] = _sha256(run / "receipt.json")
    (ledger / f"{name}.settled.json").write_text(json.dumps(settled), encoding="utf-8")


def reshape(ledger: Path, name: str, **outputs) -> None:
    """Rewrite one run's raw outputs (write_outputs arguments) and rebind every digest to them: the bindings hold,
    so only the strict evaluator-bound reader can tell."""
    run = Path(json.loads((ledger / f"{name}.reserved.json").read_text())["out"])
    write_outputs(run, **outputs)
    rebind(ledger, name, lambda r: r.update(outputs={o: _sha256(run / o) for o in gate_zero.RECEIPT_OUTPUTS}))


def passing_record(root: Path, binary: Path) -> dict:
    return build_record("hotspot6", binary, fabricate_ledger(root, binary, GOOD))


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
        self.assertEqual({r.id: (r.role, r.paper_c, r.layout_identity) for r in REFERENCES}, {
            ASCEND: (GATE, 75.48, "raw"), MICRO: (GATE, 115.94, "raw"),
            "ascend910-tap25d-fig6c": (DEFERRED, 75.47, "tap-solution"),
            "micro150-tap25d-fig5c": (DEFERRED, 94.89, "tap-solution")})
        self.assertEqual((TOLERANCE_K, TOLERANCE_LABEL, gate_zero.GRID, gate_zero.INTERPOSER_MM),
                         (1.0, "prospective computational reference-reproduction tolerance", 64, 45))

    def test_the_predicate_requires_four_native6_grid64_outcomes_and_no_deferred_call(self):
        self.assertEqual(REQUIRED, [P_ASCEND, R_ASCEND, P_MICRO, R_MICRO])
        self.assertEqual(len(set(REQUIRED)), 4)  # a primary and its replay never share an identity
        manifest = slab049.build_call_list()
        self.assertEqual(sorted(c["id"] for c in manifest["calls"] if c["gating"]), sorted(REQUIRED))
        deferred = [r.id for r in REFERENCES if r.role == DEFERRED]
        self.assertFalse([c for c in manifest["calls"] if c["reference"] in deferred])
        self.assertEqual(sorted(manifest["deferred"]), sorted(deferred))
        self.assertTrue(all(d["calls"] == 0 and d["status"] == "pending verification"
                            for d in manifest["deferred"].values()))

    def test_frozen_inputs_are_fresh_45_mm_tap_configs(self):
        for reference in gate_zero.GATE_REFERENCES:
            config = slab049.read_hotspot_config(REPO_ROOT / reference.inputs / "new_hotspot.config")
            self.assertEqual((config["r_convec"], config["s_sink"], config["s_spreader"], config["grid_rows"],
                              config["grid_map_mode"]), ("0.011111111111111112", "0.18", "0.09", "64", "center"))
            for name, digest in gate_zero.frozen_inputs(reference).items():
                self.assertEqual(_sha256(REPO_ROOT / reference.inputs / name), digest)

    def test_a_changed_reference_input_changes_the_pinned_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for reference in gate_zero.GATE_REFERENCES:
                shutil.copytree(REPO_ROOT / reference.inputs, root / reference.inputs)
            self.assertEqual(references_sha256(root), PINNED_REFERENCES_SHA256)
            sums = root / gate_zero.GATE_REFERENCES[0].inputs / "SHA256SUMS"
            sums.write_text(sums.read_text() + "0" * 64 + "  extra.flp\n")
            self.assertNotEqual(references_sha256(root), PINNED_REFERENCES_SHA256)


class RawGeometryTests(unittest.TestCase):
    """root #56858: the paper-match references are SLAB-048's raw geometry, judged by the continuous rules only."""

    def test_raw_layouts_are_slab048s_raw_sections_pinned_by_their_own_content_hash(self):
        for reference in gate_zero.GATE_REFERENCES:
            document = json.loads((REPO_ROOT / reference.raw_vendored).read_text(encoding="utf-8"))
            self.assertEqual(slab049.raw_layout_sha256(document["raw"]), reference.raw_layout_sha256)
            self.assertEqual(document["raw_layout_sha256"], reference.raw_layout_sha256)
            self.assertEqual((document["source"]["pull_request"], document["source"]["commit"],
                              document["source"]["path"], document["source"]["section"]),
                             (57, slab049.SLAB048_COMMIT, reference.raw_record, "raw"))
            self.assertEqual(document["raw"]["label"], "raw reconstruction (approximate, from published figure)")
            record = REPO_ROOT / reference.raw_record
            if record.is_file():  # SLAB-048 (#57) is merged: its own raw section must still carry the pin
                self.assertEqual(slab049.raw_layout_sha256(json.loads(record.read_text(encoding="utf-8"))["raw"]),
                                 reference.raw_layout_sha256)

    def test_annotations_never_count_and_any_raw_change_fails(self):
        """SLAB-048 keeps raw byte-stable and puts its notes in raw_annotations/snapped_annotations: descriptive only."""
        reference = gate_zero.reference(ASCEND)
        vendored = json.loads((REPO_ROOT / reference.raw_vendored).read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / reference.raw_vendored).parent.mkdir(parents=True)
            shutil.copy(REPO_ROOT / reference.raw_vendored, root / reference.raw_vendored)
            record = root / reference.raw_record
            record.parent.mkdir(parents=True)

            def write_record(raw, **sections):
                record.write_text(json.dumps({"raw": raw, **sections}), encoding="utf-8")
            annotations = {"raw_annotations": {"identity": {"content_sha256": "0" * 64}, "role": "anything at all",
                                               "centers_mm": [[0.0, 0.0]] * 6},
                           "snapped_annotations": {"rotated": [False] * 6}}
            write_record(vendored["raw"], **annotations)
            self.assertEqual(slab049.load_raw_layout(reference, root)["raw"], vendored["raw"])  # annotations ignored
            for field, change in (("centers_mm", lambda raw: raw["centers_mm"][0].__setitem__(0, 17.1502)),
                                  ("rotated", lambda raw: raw["rotated"].__setitem__(1, True)),
                                  ("label", lambda raw: raw.__setitem__("label", "relabelled"))):
                with self.subTest(raw=field):
                    moved = json.loads(json.dumps(vendored["raw"]))
                    change(moved)
                    write_record(moved, **annotations)
                    with self.assertRaisesRegex(slab049.ReferenceGeometryError, "changed after it was pinned"):
                        slab049.load_raw_layout(reference, root)
            record.unlink()
            edited = json.loads(json.dumps(vendored))
            edited["raw"]["rotated"][1] = True
            (root / reference.raw_vendored).write_text(json.dumps(edited), encoding="utf-8")
            with self.assertRaisesRegex(slab049.ReferenceGeometryError, "pinned content hash"):
                slab049.load_raw_layout(reference, root)

    @unittest.skipUnless(hasattr(getattr(tap_oracle, "TapGeometry", None), "continuous_centers_for"),
                         "SLAB-048's TapGeometry (PR #57) is not merged yet; this cross-check runs once both are in")
    def test_slab048s_continuous_rules_accept_the_raw_layouts_that_its_lattice_refuses(self):
        for reference in gate_zero.GATE_REFERENCES:
            geometry = tap_oracle.TapGeometry.load(f"{reference.fixture}-45mm")
            raw = slab049.load_raw_layout(reference)["raw"]
            design = geometry.design_from_centers(raw["centers_mm"], raw["rotated"])
            geometry.continuous_centers_for(design)
            with self.assertRaises(TapLegalityError):
                geometry.centers_for(design)

    def test_raw_centres_are_off_the_lattice_yet_pass_the_continuous_rules(self):
        for reference in gate_zero.GATE_REFERENCES:
            spec = slab049.reference_spec(reference.id)
            self.assertEqual(spec["geometry"], {"rules": slab049.CONTINUOUS_RULES, "search_lattice_checked": False,
                                                "violations": []})
            raw = slab049.load_raw_layout(reference)["raw"]
            self.assertEqual([[x, y] for x, y in zip(spec["x"], spec["y"])], raw["centers_mm"])
            self.assertEqual(spec["rotated"], raw["rotated"])
            self.assertTrue(any(abs(v * 2 - round(v * 2)) > 1e-6 for v in spec["x"] + spec["y"]),
                            f"{reference.id} should sit off the 0.5 mm search lattice")

    def test_the_search_path_still_refuses_the_raw_layouts(self):
        # The oracle hashes its fixture config relative to the repository, so the 45 mm copy lives under it briefly.
        with tempfile.TemporaryDirectory(prefix=".slab049-search-path-", dir=REPO_ROOT) as directory:
            placeholder = Path(directory) / "hotspot"
            placeholder.write_bytes(FAKE_BINARIES["hotspot7_default"])
            for reference in gate_zero.GATE_REFERENCES:
                fixture = reference.fixture
                config = Path(directory) / f"sys_{fixture}_45mm.cfg"
                text = tap_oracle.TAP_CONFIGS[fixture].read_text(encoding="utf-8")
                self.assertEqual(text.count("intp_size = 50"), 1)
                config.write_text(text.replace("intp_size = 50", "intp_size = 45"), encoding="utf-8")
                spec = slab049.reference_spec(reference.id)
                with mock.patch.dict(tap_oracle.TAP_CONFIGS, {fixture: config}):
                    oracle = HotSpotOracle(64, 64, fixture=fixture, hotspot_binary=placeholder)
                with self.assertRaises(TapLegalityError, msg=reference.id) as refused:
                    oracle.centers_for(oracle.design_from_centers(list(zip(spec["x"], spec["y"]))))
                if fixture == "micro150":  # catalog orientation: refused by the lattice itself
                    self.assertIn("placement grid", str(refused.exception))

    def test_each_continuous_rule_rejects_its_own_violation(self):
        footprints, halos = [(10.0, 10.0), (10.0, 10.0)], [0.2, 0.2]
        self.assertEqual(slab049.continuous_violations(footprints, [[10.0, 10.0], [21.0, 10.0]], halos, 45.0), [])
        cases = {"margin": [[5.5, 10.0], [21.0, 10.0]], "overlap with their halos": [[10.0, 10.0], [20.3, 10.0]],
                 "spacing": [[10.0, 10.0], [20.05, 10.05]]}
        for rule, centres in cases.items():
            with self.subTest(rule=rule):
                problems = slab049.continuous_violations(footprints, centres, [0.0, 0.0] if rule == "spacing" else halos,
                                                         45.0)
                self.assertTrue(any(rule in problem for problem in problems), problems)

    def test_a_raw_layout_that_breaks_a_continuous_rule_is_refused(self):
        reference = gate_zero.reference(MICRO)
        document = json.loads(json.dumps(slab049.load_raw_layout(reference)))
        document["raw"]["centers_mm"][1] = list(document["raw"]["centers_mm"][0])
        with self.assertRaisesRegex(slab049.ReferenceGeometryError, "continuous rules"):
            slab049.spec_from_raw_layout(document, reference.fixture)
        document = json.loads(json.dumps(slab049.load_raw_layout(reference)))
        document["raw"]["rotated"][0] = True  # an unrotated catalog footprint flagged as turned
        with self.assertRaisesRegex(slab049.ReferenceGeometryError, "turned as flagged"):
            slab049.spec_from_raw_layout(document, reference.fixture)


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
    def test_built_hotspot6_binaries_identify_correctly_and_carry_their_provenance(self):
        for kind, name in (("hotspot6", "hotspot"), ("hotspot6_tap_faithful", "hotspot-tap-faithful")):
            identity = evaluator_identity(kind, HS6_ROOT / name)
            record = provenance.require_build_provenance(kind, HS6_ROOT / name, identity["binary_sha256"])["provenance"]
            self.assertEqual(record["architecture"], platform.machine())
            self.assertTrue(record["debug_info"])  # HotSpot 6.0's CFLAGS always add -g
            self.assertTrue(any("-g" in line for line in record["makefile_flag_lines"]))
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
            run = Path(directory) / "run"
            shutil.copytree(REPO_ROOT / gate_zero.GATE_REFERENCES[0].inputs, run)
            write_outputs(run, 75.48)
            value, block = tap_selector_c(run / "sample.steady")
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
    """Records come from the ledger by admitted call id (astra supplement 6545712065; warden #56856)."""

    def test_four_required_outcomes_within_tolerance_pass_and_bind_the_binary(self):
        binary = self.binaries["hotspot6"]
        record = passing_record(self.root, binary)
        self.assertEqual(record["verdict"], "PASS")
        self.assertEqual(sorted(record["calls"]), sorted(REQUIRED))
        self.assertEqual(record["missing"], [])
        self.assertTrue(all(r["byte_identical"] for r in record["replays"]))
        self.assertEqual(record["manifest"]["sha256"], _sha256(reference_validation.MANIFEST_PATH))
        self.assertEqual(record["pass_scope"]["grid"], 64)
        self.assertEqual(require_gate_zero("hotspot6", binary, record)["verdict"], "PASS")
        rebuilt = self.root / "rebuilt"
        rebuilt.write_bytes(FAKE_BINARIES["hotspot6"] + b" rebuilt")
        with self.assertRaises(GateZeroRefusal):
            require_gate_zero("hotspot6", rebuilt, record)

    def test_deferred_points_are_pending_verification_in_every_record(self):
        record = passing_record(self.root, self.binaries["hotspot6"])
        pending = {p["reference"]: (p["paper_c"], p["status"]) for p in record["claim_scope"]["pending_verification"]}
        self.assertEqual(pending, {"ascend910-tap25d-fig6c": (75.47, "pending verification"),
                                   "micro150-tap25d-fig5c": (94.89, "pending verification")})
        self.assertEqual({c["reference"] for c in record["claim_scope"]["paper_match"]}, {ASCEND, MICRO})
        self.assertIn("not claimed", record["claim_scope"]["snapped_variants"])

    def test_a_completed_miss_fails_for_a_primary_or_a_replay_on_its_own(self):
        binary = self.binaries["hotspot6"]
        for name in (P_MICRO, R_MICRO):
            with self.subTest(call=name):
                ledger = fabricate_ledger(self.root / name, binary, {**GOOD, name: 115.94 + 1.01})
                record = build_record("hotspot6", binary, ledger)
                self.assertEqual(record["verdict"], "FAIL")
                self.assertEqual(record["claim_scope"]["paper_match"], [])
                with self.assertRaises(GateZeroRefusal):
                    require_gate_zero("hotspot6", binary, record)

    def test_a_replay_that_differs_from_its_primary_fails(self):
        binary = self.binaries["hotspot6"]
        ledger = fabricate_ledger(self.root, binary, {**GOOD, R_ASCEND: {"peak_c": 75.09, "drop_k": 2.0}})
        record = build_record("hotspot6", binary, ledger)
        self.assertEqual(record["verdict"], "FAIL")
        self.assertEqual({r["replay"]: r["byte_identical"] for r in record["replays"]}, {R_ASCEND: False, R_MICRO: True})

    def test_a_declared_grid_64_of_any_other_shape_is_never_pass(self):
        """astra (#56982 P2-1): matching digests over a 4x4x8, 64x64x1 or 64x64x7 grid used to PASS."""
        binary = self.binaries["hotspot6"]
        shapes = {"4x4x8": dict(grid=4), "64x64x1": dict(layers=1), "64x64x7": dict(layers=7),
                  "64x64x8 headerless": dict(headered=False),
                  "a block missing from the steady file": dict(omit_block="layer_3_Ubump_0")}
        for label, shape in shapes.items():
            with self.subTest(shape=label):
                ledger = fabricate_ledger(self.root / label.replace(" ", "-"), binary, GOOD)
                for name in (P_ASCEND, R_ASCEND):  # both, so the replay still matches its primary byte for byte
                    reshape(ledger, name, peak_c=GOOD[name], **shape)
                record = build_record("hotspot6", binary, ledger)
                self.assertIn(record["verdict"], ("INCOMPLETE", "FAIL"))
                self.assertEqual({m["call"] for m in record["missing"]}, {P_ASCEND, R_ASCEND})
                self.assertTrue(all("strict evaluator-bound reader" in m["reason"] for m in record["missing"]))
                with self.assertRaises(GateZeroRefusal):
                    require_gate_zero("hotspot6", binary, record)
        control = fabricate_ledger(self.root / "control", binary, GOOD)
        for name in (P_ASCEND, R_ASCEND):  # the same rewrite at the real shape: 64 x 64, 8 headered layers
            reshape(control, name, peak_c=GOOD[name])
        record = build_record("hotspot6", binary, control)
        self.assertEqual(record["verdict"], "PASS", record["missing"])
        self.assertEqual(record["calls"][P_ASCEND]["diagnostics"]["grid"], {"n": 64, "layers_in_file": list(range(8))})
        self.assertEqual(require_gate_zero("hotspot6", binary, record)["verdict"], "PASS")

    def test_withholding_a_failed_point_gives_incomplete_never_pass(self):
        """astra's control: omitting the failed point used to turn FAIL into PASS."""
        binary = self.binaries["hotspot6"]
        ledger = fabricate_ledger(self.root / "fail", binary, {**GOOD, P_ASCEND: 80.0})
        self.assertEqual(build_record("hotspot6", binary, ledger)["verdict"], "FAIL")
        for withheld in ("reserved", "settled"):
            with self.subTest(withheld=withheld):
                ledger = fabricate_ledger(self.root / withheld, binary, {**GOOD, P_ASCEND: 80.0})
                (ledger / f"{P_ASCEND}.settled.json").unlink()
                if withheld == "reserved":
                    (ledger / f"{P_ASCEND}.reserved.json").unlink()
                record = build_record("hotspot6", binary, ledger)
                self.assertEqual(record["verdict"], "INCOMPLETE")
                self.assertEqual([m["call"] for m in record["missing"]], [P_ASCEND])
                with self.assertRaises(GateZeroRefusal):
                    require_gate_zero("hotspot6", binary, record)
        for status, code in (("wall_timeout", None), ("cpu_limit", -9), ("launch_error", None),
                             ("record_error", 0), ("runtime_changed", 0), ("setup_error", None), ("exited", 7)):
            with self.subTest(settled=status, exit_status=code):
                ledger = fabricate_ledger(self.root / f"{status}-{code}", binary, GOOD, settled={R_MICRO: (status, code)})
                record = build_record("hotspot6", binary, ledger)
                self.assertEqual(record["verdict"], "INCOMPLETE")
                self.assertIn(f"exit status {code!r}", next(m["reason"] for m in record["missing"] if m["call"] == R_MICRO))
        ledger = fabricate_ledger(self.root / "only-three", binary, {k: v for k, v in GOOD.items() if k != R_ASCEND})
        self.assertEqual(build_record("hotspot6", binary, ledger)["verdict"], "INCOMPLETE")

    def test_a_primary_and_its_replay_keep_separate_identities_and_outcomes(self):
        """astra: keyed by reference, the replay directory silently replaced the primary."""
        binary = self.binaries["hotspot6"]
        record = passing_record(self.root / "pass", binary)
        self.assertNotEqual(record["calls"][P_ASCEND]["run_dir"], record["calls"][R_ASCEND]["run_dir"])
        self.assertEqual((record["calls"][P_ASCEND]["role"], record["calls"][R_ASCEND]["role"]), ("primary", "replay"))
        for collision in ("the primary's own directory", "a copy of the primary's directory"):
            with self.subTest(collision=collision):
                # A consistent forgery: the replay's reservation and settlement both point at the primary's run.
                ledger = fabricate_ledger(self.root / collision.replace(" ", "-").replace("'", ""), binary, GOOD)
                primary = Path(json.loads((ledger / f"{P_ASCEND}.reserved.json").read_text())["out"])
                if collision.startswith("a copy"):
                    shutil.copytree(primary, primary.with_name("copied-primary"))
                    primary = primary.with_name("copied-primary")
                reservation = json.loads((ledger / f"{R_ASCEND}.reserved.json").read_text())
                reservation["out"] = primary.as_posix()
                (ledger / f"{R_ASCEND}.reserved.json").write_text(json.dumps(reservation))
                settled = json.loads((ledger / f"{R_ASCEND}.settled.json").read_text())
                settled["receipt_sha256"] = _sha256(primary / "receipt.json")
                (ledger / f"{R_ASCEND}.settled.json").write_text(json.dumps(settled))
                with self.assertRaisesRegex(GateZeroRefusal, "does not hold this admitted call's receipt"):
                    build_record("hotspot6", binary, ledger)
        ledger = fabricate_ledger(self.root / "mislabel", binary, GOOD)
        settled = json.loads((ledger / f"{R_MICRO}.settled.json").read_text())
        settled["call"] = P_MICRO
        (ledger / f"{R_MICRO}.settled.json").write_text(json.dumps(settled))
        with self.assertRaisesRegex(GateZeroRefusal, "not the settled ledger entry"):
            build_record("hotspot6", binary, ledger)

    def test_editing_a_fail_record_never_unlocks(self):
        """astra #56837: an edited simulated value or verdict on a FAIL record must not unlock search."""
        binary = self.binaries["hotspot6"]
        ledger = fabricate_ledger(self.root, binary, {P_ASCEND: 122.32, R_ASCEND: 122.32, P_MICRO: 229.35,
                                                      R_MICRO: 229.35})
        record = build_record("hotspot6", binary, ledger)
        forged = json.loads(json.dumps(record))
        forged["verdict"] = "PASS"
        for result in forged["calls"].values():
            result["simulated_c"], result["delta_k"], result["within_tolerance"] = result["paper_c"], 0.0, True
        with self.assertRaises(GateZeroRefusal):
            require_gate_zero("hotspot6", binary, forged)
        with self.assertRaises(GateZeroRefusal):
            make_oracle("hotspot6", "search", hotspot_binary=binary, gate_zero_record=forged)

    def test_raw_evidence_edits_are_refused(self):
        binary = self.binaries["hotspot6"]
        record = passing_record(self.root / "a", binary)
        steady = Path(record["calls"][P_ASCEND]["run_dir"]) / "sample.steady"
        steady.write_text(steady.read_text() + "layer_4_WS_9\t330.00\n", encoding="utf-8")
        with self.assertRaises(GateZeroRefusal):  # the output no longer matches its receipt digest
            require_gate_zero("hotspot6", binary, record)
        record = passing_record(self.root / "b", binary)
        receipt = Path(record["calls"][P_ASCEND]["run_dir"]) / "receipt.json"
        receipt.write_text(receipt.read_text().replace('"grid": 64', '"grid":  64'), encoding="utf-8")
        with self.assertRaisesRegex(GateZeroRefusal, "changed after the call settled"):
            require_gate_zero("hotspot6", binary, record)
        record = passing_record(self.root / "c", binary)
        rebind(Path(record["ledger"]), P_MICRO, lambda r: r.update(host="elsewhere"))
        with self.assertRaisesRegex(GateZeroRefusal, "changed after the record was made"):
            require_gate_zero("hotspot6", binary, record)

    def test_receipts_must_bind_every_digest_the_manifest_and_the_raw_identity(self):
        binary = self.binaries["hotspot6"]
        edits = {
            "drop grid digest": lambda r: r["outputs"].pop("sample.grid.steady"),
            "wrong steady digest": lambda r: r["outputs"].update({"sample.steady": "0" * 64}),
            "unbound input": lambda r: r["inputs"].update({"new_hotspot.config": "0" * 64}),
            "other manifest": lambda r: r.update(manifest_sha256="0" * 64),
            "snapped identity": lambda r: r.update(layout_identity="snapped"),
            "other raw layout": lambda r: r.update(raw_layout_sha256="0" * 64),
            "other binary": lambda r: r["evaluator"].update(binary_sha256="0" * 64),
            "grid 32": lambda r: r.update(grid=32),
            "other call": lambda r: r.update(call=R_ASCEND),
        }
        for edit, change in edits.items():
            with self.subTest(edit=edit):
                ledger = fabricate_ledger(self.root / edit.replace(" ", "-"), binary, GOOD)
                rebind(ledger, P_ASCEND, change)
                with self.assertRaises(GateZeroRefusal):
                    build_record("hotspot6", binary, ledger)
        ledger = fabricate_ledger(self.root / "stale-config", binary, GOOD)
        run = Path(json.loads((ledger / f"{P_ASCEND}.reserved.json").read_text())["out"])
        config = run / "new_hotspot.config"
        config.write_text(config.read_text().replace("0.011111111111111112", "0.1"))
        with self.assertRaises(GateZeroRefusal):
            build_record("hotspot6", binary, ledger)

    def test_a_snapped_run_never_inherits_the_paper_match_claim(self):
        binary = self.binaries["hotspot6"]
        ledger = fabricate_ledger(self.root, binary, GOOD)
        rebind(ledger, P_MICRO, lambda r: r.update(layout_identity="snapped"))
        with self.assertRaisesRegex(GateZeroRefusal, "only the pinned raw layout carries the paper-match claim"):
            build_record("hotspot6", binary, ledger)

    def test_records_bind_their_manifest_and_ledgers_hold_one_manifest(self):
        binary = self.binaries["hotspot6"]
        record = passing_record(self.root / "a", binary)
        other = json.loads(json.dumps(record))
        other["manifest"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(GateZeroRefusal, "another manifest"):
            require_gate_zero("hotspot6", binary, other)
        ledger = fabricate_ledger(self.root / "b", binary, GOOD)
        reservation = json.loads((ledger / f"{P_MICRO}.reserved.json").read_text())
        reservation["manifest_sha256"] = "0" * 64
        (ledger / f"{P_MICRO}.reserved.json").write_text(json.dumps(reservation))
        with self.assertRaisesRegex(GateZeroRefusal, "reserved under another manifest"):
            build_record("hotspot6", binary, ledger)

    def test_the_drop_and_the_stack_are_reported_not_asserted(self):
        binary = self.binaries["hotspot6"]
        ledger = fabricate_ledger(self.root, binary, {**GOOD, P_ASCEND: {"peak_c": 75.09, "drop_k": 51.0},
                                                      R_ASCEND: {"peak_c": 75.09, "drop_k": 51.0}})
        record = build_record("hotspot6", binary, ledger)
        self.assertEqual(record["verdict"], "PASS")
        diagnostics = record["calls"][P_ASCEND]["diagnostics"]
        drop = diagnostics["spreader_sink_drop"]
        self.assertAlmostEqual(drop["drop_K"], 51.5, places=6)  # 51 K of link plus the synthetic 0.5 K per layer
        self.assertIn("copper predicts about 1-2 K", drop["expectation"])
        (stack,) = diagnostics["same_index_stack"]
        self.assertEqual(stack["at"], {"row": 16, "col": 16})
        self.assertEqual([layer["layer"] for layer in stack["layers"]], [4, 5, 6, 7])
        self.assertEqual([layer["name"] for layer in stack["layers"]][2:], ["spreader", "sink"])
        self.assertAlmostEqual(stack["drops"][-1]["drop_K"], 0.5 + 51.0, places=6)

    def test_only_the_native6_engine_can_pass_and_only_at_grid_64(self):
        binary = self.binaries["hotspot6"]
        record = passing_record(self.root, binary)
        with self.assertRaisesRegex(GateZeroRefusal, "covers grid 64 only"):
            require_gate_zero("hotspot6", binary, record, grid=32)
        for kind in ("hotspot7_default", "material_only"):
            with self.assertRaisesRegex(GateZeroRefusal, "judges hotspot6 only"):
                build_record(kind, self.binaries[kind], Path(record["ledger"]))
        with self.assertRaises(GateZeroRefusal):
            require_gate_zero("hotspot6", binary, None)


class ReportTests(TempDirCase):
    """astra (#56982 P2-3): report verifies every binding first and derives its diagnostics from the raw files."""

    def test_report_derives_diagnostics_from_verified_raw_evidence_not_a_stored_record(self):
        ledger = fabricate_ledger(self.root, self.binaries["hotspot6"], GOOD)
        fabricated = {"active_layer_grid_peak": {"peak_C": 999.0}, "spreader_sink_drop_diagnostic": {"drop_K": 0.0},
                      "same_index_stack_at_active_argmax": []}
        rebind(ledger, P_ASCEND, lambda r: r.update(solve_record=fabricated))  # bound, so only derivation can tell
        report = reference_validation.report(ledger)
        entry = next(e for e in report["calls"] if e["call"] == P_ASCEND)
        self.assertTrue(entry["usable"])
        self.assertAlmostEqual(entry["grid_peak_c"], 379.0 - 273.15, places=6)  # the raw grid, not the 999.0 stored
        self.assertAlmostEqual(entry["drop"]["drop_K"], 1.5, places=6)  # the synthetic 1 K link plus 0.5 K
        self.assertEqual(entry["stack"][0]["at"], {"row": 16, "col": 16})
        row = next(r for r in report["rows"] if r["kind"] == "hotspot6" and r["reference"] == ASCEND)
        self.assertTrue(row["replay_byte_identical"])

    def test_every_unusable_call_is_listed_with_its_reason(self):
        ledger = fabricate_ledger(self.root, self.binaries["hotspot6"], GOOD, settled={R_MICRO: ("exited", 7)})
        rebind(ledger, P_MICRO, lambda r: r["outputs"].update({"sample.steady": "0" * 64}))
        reshape(ledger, R_ASCEND, peak_c=GOOD[R_ASCEND], grid=4)
        receipt = Path(json.loads((ledger / f"{P_ASCEND}.reserved.json").read_text())["out"]) / "receipt.json"
        receipt.write_text(receipt.read_text().replace('"grid": 64', '"grid":  64'), encoding="utf-8")  # unbound edit
        report = reference_validation.report(ledger)
        reasons = {item["call"]: item["reason"] for item in report["not_completed"]}
        self.assertEqual(len(reasons), 12)  # nothing usable: four unusable, eight never admitted
        self.assertIn("changed after the call settled", reasons[P_ASCEND])
        self.assertIn("differs from its receipt digest", reasons[P_MICRO])
        self.assertIn("exit status 7", reasons[R_MICRO])
        self.assertIn("strict evaluator-bound reader", reasons[R_ASCEND])
        self.assertEqual(sum(reason == "not admitted" for reason in reasons.values()), 8)
        self.assertFalse(any(e["usable"] for e in report["calls"]))
        self.assertTrue(all(row["block_centre_c"]["64"] is None for row in report["rows"]))


class SelectorAndOracleTests(TempDirCase):
    """Search and headroom need a PASS at grid 64; the selector keeps HotSpot 7's oracle unchanged."""

    def test_search_and_headroom_refuse_without_a_pass_or_off_grid_64(self):
        for purpose in ("search", "headroom"):
            with self.assertRaises(GateZeroRefusal):
                make_oracle("hotspot6", purpose, hotspot_binary=self.binaries["hotspot6"])
            with self.assertRaises(GateZeroRefusal):
                make_oracle("hotspot7", purpose, hotspot_binary=self.binaries["hotspot7_default"])
        record = passing_record(self.root, self.binaries["hotspot6"])
        with self.assertRaisesRegex(GateZeroRefusal, "covers a 64 x 64 grid only"):
            make_oracle("hotspot6", "search", 32, 32, hotspot_binary=self.binaries["hotspot6"], gate_zero_record=record)
        with self.assertRaises(ValueError):
            make_oracle("hotspot6", "validate-reference", hotspot_binary=self.binaries["hotspot6"])

    def test_a_pass_unlocks_search_with_a_new_identity_and_hotspot7_stays_locked(self):
        binary = self.binaries["hotspot6"]
        record = passing_record(self.root, binary)
        oracle = make_oracle("hotspot6", "search", hotspot_binary=binary, gate_zero_record=record)
        self.assertIsInstance(oracle, HotSpot6Oracle)
        self.assertEqual((oracle.grid_rows, oracle.grid_cols), (64, 64))
        base = HotSpotOracle(64, 64, hotspot_binary=binary)
        self.assertEqual(oracle.base_problem_hash, base.problem_hash)
        self.assertNotEqual(oracle.problem_hash, base.problem_hash)
        self.assertTrue(oracle.solver_version.startswith(f"HotSpot-6.0:{gate_zero.HOTSPOT6_COMMIT}+SLAB-049:"))
        self.assertTrue(base.solver_version.startswith("HotSpot-7:"))
        with self.assertRaises(GateZeroRefusal):  # native7 is the comparator: no record can pass it here
            make_oracle("hotspot7", "headroom", hotspot_binary=self.binaries["hotspot7_default"],
                        gate_zero_record=record)

    def test_hotspot6_oracle_refuses_evaluations_and_the_wrong_binary(self):
        oracle = HotSpot6Oracle(16, 16, hotspot_binary=self.binaries["hotspot6"])
        design = oracle.design_from_centers(((25, 25), (40, 40), (8, 9), (8, 25), (8, 41), (41, 15)))
        with self.assertRaises(GateZeroRefusal):
            asyncio.run(oracle(design))
        with self.assertRaises(HotSpotOracleError):
            HotSpot6Oracle(16, 16, hotspot_binary=self.binaries["hotspot6_tap_faithful"])

    def test_hotspot6_results_are_labelled_hotspot6_never_hotspot7(self):
        """warden #56856 P3: the HotSpot 6.0 evidence label was untested."""
        with mock.patch("sundai_hotspot.evaluators.require_gate_zero", return_value={"verdict": "PASS"}):
            oracle = HotSpot6Oracle(4, 4, hotspot_binary=self.binaries["hotspot6"])
        design = oracle.design_from_centers(((25, 25), (40, 40), (8, 9), (8, 25), (8, 41), (41, 15)))
        response = {
            "candidate_hash": design.hash, "problem_hash": oracle.problem_hash,
            "binary_sha256": oracle.problem.hotspot_binary_sha256, "grid_rows": 4, "grid_cols": 4,
            "heatmap_c": [[60.0] * 4 for _ in range(4)], "maximum_temperature_c": 60.0, "all_layers_peak_c": 60.0,
            "solver_seconds": 0.1, "input_generation_seconds": 0.01,
            "input_sha256": {name: "a" * 64 for name in slab049.REFERENCE_INPUTS},
        }

        async def evaluate_once():
            try:
                return await oracle(design)
            finally:
                await oracle.aclose()

        with mock.patch("sundai_hotspot.tap_oracle._run_worker", new_callable=mock.AsyncMock, return_value=response):
            result = asyncio.run(evaluate_once())
        self.assertTrue(result.evidence_kind.startswith(EVIDENCE_PREFIX + "steady-state TAP"), result.evidence_kind)
        self.assertNotIn("HotSpot 7", result.evidence_kind)
        self.assertTrue(result.solver_version.startswith("HotSpot-6.0:"))
        relabelled = mock.Mock(evidence_kind="steady-state TAP from some future label")
        with mock.patch.object(HotSpotOracle, "_result_from_response", return_value=relabelled):
            with self.assertRaises(HotSpotOracleError):
                oracle._result_from_response(response, design, (), 0.0)


class ManifestTests(unittest.TestCase):
    """warden #56856 (2), (3) and astra's supplement: the manifest is the tree's, every row explicit, the cap held."""

    def test_the_prior_snapped_manifest_is_byte_identical_and_never_executable(self):
        prior = REPO_ROOT / slab049.PRIOR_MANIFEST["path"]
        self.assertEqual(_sha256(prior), slab049.PRIOR_MANIFEST["sha256"])
        self.assertEqual(_sha256(REPO_ROOT / slab049.PRIOR_MANIFEST["description"]),
                         slab049.PRIOR_MANIFEST["description_sha256"])
        self.assertEqual(json.loads(prior.read_text())["schema"], slab049.PRIOR_MANIFEST["schema"])
        with self.assertRaisesRegex(slab049.ManifestMismatch, "prior snapped manifest"):
            slab049.check_manifest(prior.read_bytes())
        self.assertNotEqual(reference_validation.MANIFEST_PATH.resolve(), prior.resolve())

    def test_the_committed_manifest_is_what_the_tree_generates_and_drift_is_refused(self):
        committed = reference_validation.MANIFEST_PATH.read_bytes()
        manifest = slab049.check_manifest(committed)  # the committed bytes, not a fresh object against itself
        for path, digest in manifest["source"]["files_sha256"].items():
            self.assertEqual(_sha256(REPO_ROOT / path), digest, path)
        altered = json.loads(committed)
        altered["source"]["files_sha256"]["sundai_hotspot/tap_oracle.py"] = "0" * 64
        with self.assertRaisesRegex(slab049.ManifestMismatch, "tap_oracle.py"):
            slab049.check_manifest(slab049._dump(altered))
        real = slab049._file_sha256

        def drifted(path):
            return "f" * 64 if path == "sundai_hotspot/tap_oracle_worker.py" else real(path)
        with mock.patch.object(slab049, "_file_sha256", side_effect=drifted):
            with self.assertRaisesRegex(slab049.ManifestMismatch, "tap_oracle_worker.py"):
                slab049.check_manifest(committed)
            with self.assertRaises(CallRefused):
                reference_validation.load_manifest()

    def test_every_row_carries_its_call_id_and_its_own_timeout_on_the_cli(self):
        manifest = slab049.build_call_list()
        parser_main = reference_validation.main
        for call in manifest["calls"]:
            argv = call["command"].split("reference_validation ", 1)[1].replace("<fresh empty dir>", "OUT")
            argv = argv.replace("<the grant's ledger dir>", "LEDGER").split()
            with mock.patch.object(reference_validation, "validate_call") as run, \
                    contextlib.redirect_stdout(io.StringIO()):
                run.return_value = {"status": "exited", "exit_status": 0}
                self.assertEqual(parser_main(argv), 0)
            self.assertEqual(run.call_args.args[0], call["id"])
            self.assertEqual(run.call_args.kwargs["timeout_s"], call["timeout_s"])
            self.assertEqual(call["timeout_s"], {64: 60.0, 32: 15.0}[call["grid"]])
            self.assertEqual(call["cpu_limit_s"], int(call["timeout_s"]))
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):  # no default timeout any more
            parser_main(["validate-reference", "--call", REQUIRED[0], "--out", "OUT", "--ledger", "LEDGER"])

    def test_the_forecast_is_inside_the_binding_cap_and_generation_fails_outside_it(self):
        accounting = slab049.build_call_list()["accounting"]
        self.assertEqual((accounting["calls"], accounting["grid64_calls"], accounting["grid32_calls"]), (12, 8, 4))
        self.assertEqual(accounting["timeouts_s"], 8 * 60 + 4 * 15)
        self.assertEqual(accounting["forecast_worst_case_cpu_s"], 540 + 12 * 2.0)
        self.assertTrue(accounting["arithmetic"].startswith("8 x 60 s + 4 x 15 s = 540 s of timeouts"))
        self.assertIn("not a CPU guarantee", accounting["forecast_label"])
        self.assertEqual((accounting["manifest_cpu_cap_s"], accounting["room_envelope_cpu_s"]), (600.0, 1800.0))
        self.assertIn("600 CPU-s, binds", accounting["binding_cap"])
        with mock.patch.dict(slab049.TIMING, {"grid64_timeout_s": 70.0}):
            with self.assertRaisesRegex(ValueError, "exceeds the manifest cap"):
                slab049.build_call_list()

    def test_the_enforcement_split_is_published(self):
        enforcement = slab049.build_call_list()["enforcement"]
        self.assertEqual(len(enforcement["in_code_at_entry"]), len(slab049.IN_CODE_AT_ENTRY))
        contract = " ".join(enforcement["operator_supervisor_contract"])
        for duty in ("append-only", "cumulative CPU budget", "process group", "protected runtime image",
                     "trusted clock", "1,800 CPU-s"):
            self.assertIn(duty, contract)


FAKE_SOLVER = r'''#!PYTHON
# Test-only stand-in for a HotSpot binary: identity markers in this comment, synthetic outputs, no physics.
# markers: Unit	Steady(Kelvin) dgssv SENTILAB_EVALUATOR=hotspot6@a7a3286e;grid_dump=all_layers;ticket=SLAB-049
import json, os, resource, subprocess, sys, time
case = json.load(open("CONTROL")).get(os.path.basename(os.getcwd()), {})
args = sys.argv[1:]
grid = int(args[args.index("-grid_rows") + 1]) if "-grid_rows" in args else 64
peak = float(case.get("peak_c", 75.3)) + 273.15
open("rlimit_cpu.txt", "w").write("%d %d" % resource.getrlimit(resource.RLIMIT_CPU))
open("argv0.txt", "w").write(os.path.realpath(sys.argv[0]))
if case.get("sleep"):
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    open("child.pid", "w").write(str(child.pid))
    time.sleep(120)
tokens = [line.split()[0] for line in open("samplelayers.lcf") if line.split() and not line.startswith("#")]
steady = []
for offset in range(0, len(tokens), 7):  # every unit of every LCF layer, as HotSpot writes them
    number, floorplan = int(tokens[offset]), tokens[offset + 6]
    for line in open(floorplan):
        if line.strip() and not line.startswith("#"):
            name = line.split()[0]
            hot = number == 4 and name == "Chiplet_0"
            steady.append("layer_%d_%s\t%.2f" % (number, name, peak - (0 if hot else 5 + number)))
steady += ["hsp_TIM\t%.2f" % (peak - 30), "hsink_TIM\t%.2f" % (peak - 40), "inode_0\t320.00"]
open("sample.steady", "w").write("\n".join(steady) + "\n")
layers = 1 if case.get("truncate") else 8
with open("sample.grid.steady", "w") as out:
    for layer in range(layers):
        out.write("Layer %d:\n" % layer)
        for cell in range(grid * grid):
            out.write("%d\t%.2f\n" % (cell, peak - 1 - layer if cell else peak - layer))
print("Unit\tSteady(Kelvin)")
print("\n".join(steady))
'''


def _process_gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    with open(f"/proc/{pid}/stat", encoding="ascii") as stat:  # a zombie awaiting init is already dead
        return stat.read().rsplit(")", 1)[1].split()[0] == "Z"


@unittest.skipUnless(os.name == "posix" and platform.machine() == "x86_64",
                     "the manifest lists an x86_64 POSIX host; the fake solver is a POSIX script")
class ManifestEntryTests(TempDirCase):
    """validate-reference: the bootstrap path, bound to the frozen manifest (astra #56794, #56837, #56858).

    These tests stand in for warden's grant host, so CI_ALLOCATION is removed from their environment: the CI image
    sets it, and validate-reference refuses to run under it (test_ci_allocation_refuses_before_anything_runs). The
    "solver" is a Python script; no HotSpot binary is launched.
    """

    def setUp(self):
        super().setUp()
        environment = mock.patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop("CI_ALLOCATION", None)
        self.fake = self.root / "fake-hotspot6"
        self.control = self.root / "control.json"
        self.fake.write_text(FAKE_SOLVER.replace("PYTHON", sys.executable).replace("CONTROL", str(self.control)),
                             encoding="utf-8")
        self.fake.chmod(0o755)
        self.control.write_text("{}", encoding="utf-8")
        self.write_provenance(self.fake)
        self.ledger = self.root / "ledger"
        self.timeouts = {c["id"]: c["timeout_s"] for c in slab049.build_call_list()["calls"]}

    def write_provenance(self, binary: Path, kind: str = "hotspot6") -> None:
        record = provenance.build_provenance(kind, binary)
        provenance.provenance_path(binary).write_text(json.dumps(record), encoding="utf-8")

    def control_case(self, out: str, **case) -> None:
        cases = json.loads(self.control.read_text())
        cases[out] = case
        self.control.write_text(json.dumps(cases), encoding="utf-8")

    def call(self, name: str, out: str, **kwargs) -> dict:
        kwargs.setdefault("timeout_s", self.timeouts.get(name, 60.0))
        return validate_call(name, self.root / out, self.ledger, binary=kwargs.pop("binary", self.fake),
                             now=kwargs.pop("now", IN_WINDOW), **kwargs)

    def test_anything_not_in_the_manifest_is_refused_before_dispatch(self):
        drifted = self.root / "drifted.json"
        manifest = json.loads(reference_validation.MANIFEST_PATH.read_text())
        manifest["source"]["files_sha256"]["sundai_hotspot/tap_oracle.py"] = "0" * 64
        drifted.write_bytes(slab049._dump(manifest))
        g32 = call_id("primary", "hotspot6", ASCEND, 32)
        refusals = {
            "unlisted call": dict(name="u-hs6-ascend910-tap25d-fig6a-raw-g64"),
            "snapped identity": dict(name="p-hs6-ascend910-tap25d-fig6a-snapped-g64"),
            "deferred reference": dict(name=P_ASCEND, reference="ascend910-tap25d-fig6c"),
            "grid 128": dict(name=P_ASCEND, grid=128),
            "other engine": dict(name=P_ASCEND, kind="hotspot6_tap_faithful"),
            "no timeout": dict(name=P_ASCEND, timeout_s=None),
            "the old 60 s default on a 15 s row": dict(name=g32, timeout_s=60.0),
            "timeout 1e6": dict(name=P_ASCEND, timeout_s=1e6),
            "after the window": dict(name=P_ASCEND, now=datetime(2026, 11, 1, 12, 0, 1, tzinfo=timezone.utc)),
            "the prior manifest": dict(name=P_ASCEND, manifest_path=REPO_ROOT / slab049.PRIOR_MANIFEST["path"]),
            "a drifted source pin": dict(name=P_ASCEND, manifest_path=drifted),
        }
        stale = self.root / "stale-provenance"
        shutil.copy(self.fake, stale)
        self.write_provenance(stale)
        stale.write_text(stale.read_text() + "# rebuilt\n")
        other = self.root / "other-libraries"
        shutil.copy(self.fake, other)
        claimed = provenance.build_provenance("hotspot6", other)
        claimed["libraries"] = {"dynamic": True, "libraries": [
            {"name": "libblas.so.3", "path": "/x", "realpath": "/x", "sha256": "0" * 64}]}
        provenance.provenance_path(other).write_text(json.dumps(claimed))
        guarded = self.root / "ci-guarded"  # what a CI_ALLOCATION=1 build compiles in (sundai_hotspot/ci_entry.h)
        guarded.write_bytes(self.fake.read_bytes() + b"# " + provenance.CI_ENTRY_GUARD + b"\n")
        guarded.chmod(0o755)
        self.write_provenance(guarded)
        with mock.patch("sundai_hotspot.reference_validation._run_call") as dispatch:  # admission, staging, launch
            for rule, arguments in refusals.items():
                with self.subTest(rule=rule), self.assertRaises(CallRefused):
                    name = arguments.pop("name")
                    self.call(name, f"out-{rule.replace(' ', '-')}", **arguments)
            with mock.patch("sundai_hotspot.reference_validation.platform.machine", return_value="aarch64"):
                with self.assertRaises(CallRefused):
                    self.call(P_ASCEND, "out-host")
            with self.assertRaisesRegex(CallRefused, "provenance"):
                self.call(P_ASCEND, "out-stale", binary=stale)
            with self.assertRaisesRegex(CallRefused, "libraries"):
                self.call(P_ASCEND, "out-libraries", binary=other)
            with self.assertRaisesRegex(CallRefused, "CI entry guard"):
                self.call(P_ASCEND, "out-guarded", binary=guarded)
            dispatch.assert_not_called()
        self.assertFalse(self.ledger.exists() and list(self.ledger.glob("*.json")), "a refused call is never reserved")

    def test_ci_allocation_refuses_before_anything_runs(self):
        """Main's CI allocation (SLAB-046): native HotSpot launches in CI go through ci_gate; SLAB-049 never solves there."""
        with mock.patch.dict(os.environ, {"CI_ALLOCATION": "1"}), \
                mock.patch("sundai_hotspot.reference_validation._run_call") as dispatch:
            with self.assertRaisesRegex(CallRefused, "never runs under CI allocation"):
                self.call(P_ASCEND, "ci")
            dispatch.assert_not_called()
        self.assertFalse(self.ledger.exists())
        self.assertFalse((self.root / "ci").exists())

    def test_bootstrap_receipts_need_no_pass_bind_every_field_and_unlock_search(self):
        with self.assertRaises(GateZeroRefusal):
            make_oracle("hotspot6", "search", hotspot_binary=self.fake)
        peaks = {P_ASCEND: 75.30, R_ASCEND: 75.30, P_MICRO: 116.50, R_MICRO: 116.50}
        manifest_sha256 = _sha256(reference_validation.MANIFEST_PATH)
        for name, peak in peaks.items():
            self.control_case(name, peak_c=peak)
            receipt = self.call(name, name)
            self.assertEqual((receipt["status"], receipt["exit_status"]), ("exited", 0), receipt.get("error"))
            run = self.root / name
            self.assertEqual((run / "rlimit_cpu.txt").read_text(), "60 60")  # RLIMIT_CPU soft = hard = timeout
            self.assertEqual((receipt["call"], receipt["manifest_sha256"], receipt["layout_identity"]),
                             (name, manifest_sha256, "raw"))
            self.assertEqual(receipt["raw_layout_sha256"],
                             gate_zero.reference(receipt["reference"]).raw_layout_sha256)
            self.assertFalse(receipt["geometry"]["search_lattice_checked"])
            self.assertEqual(receipt["build_provenance"]["sha256"], _sha256(provenance.provenance_path(self.fake)))
            self.assertEqual(receipt["runtime"], receipt["runtime_after"])
            executed = Path((run / "argv0.txt").read_text())
            self.assertEqual(executed.name, f"evaluator-{_sha256(self.fake)[:16]}")  # the private copy ran
            self.assertNotEqual(executed, self.fake.resolve())
            self.assertFalse(executed.parent.exists(), "the private copy is removed after the call")
            record = receipt["solve_record"]
            self.assertEqual(record["config_sha256"], receipt["inputs"]["new_hotspot.config"])
            for field in ("active_layer_grid_peak", "chiplet_centre_mapping", "historical_tap_stdout_selector",
                          "spreader_sink_hottest_cell_rises", "spreader_sink_drop_diagnostic",
                          "same_index_stack_at_active_argmax"):
                self.assertIn(field, record)
            self.assertNotIn("measured", json.dumps(receipt))
            settled = json.loads((self.ledger / f"{name}.settled.json").read_text())
            self.assertEqual(settled["receipt_sha256"], _sha256(run / "receipt.json"))
            self.assertGreater(settled["charged_cpu_s"], 0.0)
        with self.assertRaises(CallRefused):  # each call runs once
            self.call(P_ASCEND, "again")
        result = build_record("hotspot6", self.fake, self.ledger)
        self.assertEqual(result["verdict"], "PASS", result["missing"])
        oracle = make_oracle("hotspot6", "search", hotspot_binary=self.fake, gate_zero_record=result)
        self.assertIsNotNone(oracle.gate_zero)
        report = reference_validation.report(self.ledger)
        self.assertEqual(len(report["calls"]), 12)
        self.assertEqual(len(report["not_completed"]), 8)
        row = next(r for r in report["rows"] if r["kind"] == "hotspot6" and r["reference"] == ASCEND)
        self.assertTrue(row["replay_byte_identical"])
        self.assertEqual([layer["layer"] for layer in row["same_index_stack_g64"][0]["layers"]], [4, 5, 6, 7])

    def test_a_grid_32_row_runs_under_its_own_15_s_limit(self):
        name = call_id("primary", "hotspot6", MICRO, 32)
        receipt = self.call(name, name)
        self.assertEqual((receipt["status"], receipt["timeout_s"], receipt["cpu_limit_s"]), ("exited", 15.0, 15))
        self.assertEqual((self.root / name / "rlimit_cpu.txt").read_text(), "15 15")

    def test_the_cumulative_ledger_refuses_past_the_call_count_or_the_cpu_cap(self):
        manifest_sha256 = _sha256(reference_validation.MANIFEST_PATH)
        self.ledger.mkdir()

        def reserve(name: str, cpu: float, sha: str = manifest_sha256) -> None:
            (self.ledger / f"{name}.reserved.json").write_text(json.dumps(
                {"call": name, "manifest_sha256": sha, "out": "/nonexistent", "reserved_cpu_s": cpu}))
        reserve("p-hs7-ascend910-tap25d-fig6a-raw-g64", 560.0)  # unsettled: charged its reservation
        with self.assertRaisesRegex(CallRefused, "would pass the 600 CPU-s cap"):
            self.call(P_ASCEND, "cpu")
        (self.ledger / "p-hs7-ascend910-tap25d-fig6a-raw-g64.settled.json").write_text(json.dumps(
            {"call": "p-hs7-ascend910-tap25d-fig6a-raw-g64", "status": "exited", "charged_cpu_s": 5.0}))
        with self.assertRaisesRegex(CallRefused, "would pass the 600 CPU-s cap"):  # never freed by settling
            self.call(P_ASCEND, "cpu-after-settlement")
        self.assertEqual(reference_validation.ledger_totals(self.ledger)["charged_cpu_s"], 560.0)
        shutil.rmtree(self.ledger)
        self.ledger.mkdir()
        reserve("p-hs7-ascend910-tap25d-fig6a-raw-g32", 1.0)
        (self.ledger / "p-hs7-ascend910-tap25d-fig6a-raw-g32.settled.json").write_text(json.dumps(
            {"call": "p-hs7-ascend910-tap25d-fig6a-raw-g32", "status": "exited", "charged_cpu_s": 545.0}))
        self.assertEqual(reference_validation.ledger_totals(self.ledger)["charged_cpu_s"], 545.0)  # overshoot, in full
        with self.assertRaisesRegex(CallRefused, "would pass the 600 CPU-s cap"):
            self.call(P_ASCEND, "overshoot")
        receipt = self.call(call_id("primary", "hotspot6", ASCEND, 32), "fits")  # 545 + 17 <= 600
        self.assertEqual(receipt["status"], "exited")
        for index in range(10):
            reserve(f"synthetic-{index}", 0.0)
        with self.assertRaisesRegex(CallRefused, "allows 12"):
            self.call(P_ASCEND, "count")
        shutil.rmtree(self.ledger)
        self.ledger.mkdir()
        reserve("p-hs7-micro150-tap25d-fig5a-raw-g64", 1.0, sha="0" * 64)
        with self.assertRaisesRegex(CallRefused, "another manifest"):
            self.call(P_ASCEND, "manifest")

    def test_the_wall_deadline_kills_the_whole_process_group(self):
        with mock.patch.dict(slab049.TIMING, {"grid64_timeout_s": 3.0}):  # time to start its child
            manifest = self.root / "short.json"
            manifest.write_bytes(slab049._dump(slab049.build_call_list()))
            self.control_case("sleeper", sleep=True)
            started = time.monotonic()
            receipt = self.call(P_ASCEND, "sleeper", timeout_s=3.0, manifest_path=manifest)
        self.assertLess(time.monotonic() - started, 60)
        self.assertEqual((receipt["status"], receipt["exit_status"]), ("wall_timeout", None))
        child = int((self.root / "sleeper" / "child.pid").read_text())
        deadline = time.monotonic() + 5
        while not _process_gone(child) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(_process_gone(child), "the solver's descendant survived the group kill")
        settled = json.loads((self.ledger / f"{P_ASCEND}.settled.json").read_text())
        self.assertEqual(settled["status"], "wall_timeout")

    def test_rlimit_cpu_enforces_cpu_whatever_the_wall_deadline(self):
        """astra #56858: a wall timeout alone is not CPU enforcement; the per-process CPU limit kills by itself."""
        started = time.monotonic()
        process = subprocess.Popen([sys.executable, "-c", "while True: pass"], start_new_session=True,
                                   preexec_fn=reference_validation._cpu_limit(1))
        self.assertEqual(process.wait(timeout=30), -signal.SIGKILL)
        self.assertLess(time.monotonic() - started, 30)

    def test_a_launch_failure_keeps_a_settled_receipt(self):
        unlaunchable = self.root / "not-executable"
        unlaunchable.write_bytes(FAKE_BINARIES["hotspot6"])
        self.write_provenance(unlaunchable)
        receipt = self.call(P_ASCEND, "launch", binary=unlaunchable)
        self.assertEqual(receipt["status"], "launch_error")
        on_disk = json.loads((self.root / "launch" / "receipt.json").read_text())
        self.assertEqual(on_disk["status"], "launch_error")
        self.assertIn("finished_utc", on_disk)
        settled = json.loads((self.ledger / f"{P_ASCEND}.settled.json").read_text())
        self.assertEqual(settled["status"], "launch_error")

    def test_every_post_admission_setup_failure_settles_in_the_ledger(self):
        """astra (#56982 P2-2): a failure between admission and staging used to leave the reservation unsettled."""
        (self.root / "blocker").write_text("a file where the output parent should be", encoding="utf-8")
        receipt = self.call(P_ASCEND, "blocker/run")
        self.assertEqual((receipt["status"], receipt["exit_status"]), ("setup_error", None))
        settled = json.loads((self.ledger / f"{P_ASCEND}.settled.json").read_text())
        self.assertEqual(settled["status"], "setup_error")
        self.assertIsNone(settled["receipt_sha256"])  # no receipt could be written, the ledger still settles
        self.assertTrue(settled["receipt_error"])
        self.assertEqual(reference_validation.ledger_totals(self.ledger)["charged_cpu_s"], 62.0)  # stays charged
        with self.assertRaisesRegex(CallRefused, "already admitted"):  # and is never retried
            self.call(P_ASCEND, "elsewhere")
        name = call_id("primary", "hotspot6", MICRO, 64)
        real, writes = reference_validation._write_durably, []

        def first_write_fails(path, data):
            writes.append(path)
            if len(writes) == 1:
                raise OSError(28, "No space left on device")
            return real(path, data)
        with mock.patch.object(reference_validation, "_write_durably", side_effect=first_write_fails):
            receipt = self.call(name, "first-write")
        self.assertEqual(receipt["status"], "setup_error")
        settled = json.loads((self.ledger / f"{name}.settled.json").read_text())
        self.assertEqual(settled["status"], "setup_error")
        self.assertIn("No space left on device", settled["error"])
        self.assertEqual(settled["receipt_sha256"], _sha256(self.root / "first-write" / "receipt.json"))
        self.assertEqual(reference_validation.ledger_totals(self.ledger)["charged_cpu_s"], 124.0)

    def test_a_truncated_grid_after_exit_zero_keeps_the_raw_outputs_and_is_incomplete(self):
        self.control_case("truncated", truncate=True)
        receipt = self.call(P_ASCEND, "truncated")
        self.assertEqual((receipt["status"], receipt["exit_status"]), ("record_error", 0))
        self.assertIn("GridFormatError", receipt["error"])
        self.assertEqual(set(receipt["outputs"]), set(gate_zero.RECEIPT_OUTPUTS))
        record = build_record("hotspot6", self.fake, self.ledger)
        self.assertEqual(record["verdict"], "INCOMPLETE")
        self.assertIn("record_error", next(m["reason"] for m in record["missing"] if m["call"] == P_ASCEND))


@unittest.skipUnless(os.name == "posix" and shutil.which("ldd"), "glibc ldd")
class RuntimeLibraryTests(unittest.TestCase):
    def test_libraries_are_resolved_with_hashes_without_running_the_program(self):
        resolved = provenance.resolved_libraries(Path("/bin/true"))
        self.assertTrue(resolved["dynamic"])
        libc = next(item for item in resolved["libraries"] if item["name"].startswith("libc.so"))
        self.assertEqual(libc["sha256"], _sha256(libc["realpath"]))
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "script"
            script.write_text("#!/bin/sh\nexit 0\n")
            script.chmod(0o755)
            self.assertEqual(provenance.library_identity(provenance.resolved_libraries(script)), [])


class VendoredHotSpot6Tests(unittest.TestCase):
    def test_vendored_files_are_the_upstream_blobs(self):
        self.assertEqual((HS6_ROOT / "UPSTREAM_COMMIT").read_text(encoding="ascii").strip(), gate_zero.HOTSPOT6_COMMIT)
        listed = dict(reversed(line.split()) for line in (HS6_ROOT / "UPSTREAM_BLOBS.txt").read_text(encoding="ascii").splitlines())
        vendored = {p.name for p in HS6_ROOT.iterdir() if p.is_file() and p.suffix not in (".o", ".d", ".a")
                    and p.name not in ("hotspot", "hotspot-tap-faithful", "hotfloorplan")
                    and not p.name.endswith(".provenance.json")}
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

    def test_build_script_covers_both_architectures_both_binaries_and_their_provenance(self):
        script = (REPO_ROOT / "scripts" / "build_hotspot6.sh").read_text(encoding="utf-8")
        for needle in ("x86_64|aarch64)", "SUPERLU=0", "SUPERLU=1", "-DSENTILAB_GRID_DUMP_ALL_LAYERS=1",
                       "-ffp-contract=off", "hotspot-tap-faithful", "sha256sum",
                       "python3 -m sundai_hotspot.provenance hotspot6 hotspot6_tap_faithful",
                       "it does not make results bit-identical across architectures"):
            self.assertIn(needle, script)
        self.assertIn("python3 -m sundai_hotspot.provenance hotspot7_default",
                      (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8"))


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
