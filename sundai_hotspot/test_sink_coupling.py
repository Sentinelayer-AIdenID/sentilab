"""SLAB-049: the material-only coupling flag, default byte-identity and the frozen equations.

No test here runs a thermal solve. The native tests compile HotSpot's sources and assemble the
conductance matrix (build_transient_grid_matrix) without factorizing it.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from sundai_hotspot import slab049
from sundai_hotspot.coupling_variant import (
    NEW, OLD, PRISTINE_TEMPERATURE_GRID_SHA256, VARIANT_BINARY, VARIANT_MACRO, VARIANT_SOURCES, VARIANT_TAG,
    MaterialOnlyCouplingOracle, PackageStack, area_resistances, cell_resistances, strip_variant_blocks,
)
from sundai_hotspot.gate_zero import GateZeroRefusal
from sundai_hotspot.tap_oracle import HOTSPOT_BINARY, HOTSPOT_ROOT, REPO_ROOT, HotSpotOracle, HotSpotOracleError

H_VALUES = (0.25, 0.5, 1.0, 2.0, 4.0)
GRID_SOURCE = HOTSPOT_ROOT / "temperature_grid.c"
DEFAULT_LINE = "      res = (find_res_3D(n1, i1, j1, model, 3) / 2.0) + (find_res_3D(n2, i2, j2, model, 3) / 2.0);\n"
VARIANT_SINK_TEST = "  if (n == hsidx)\n"


def h_dependent(values_by_h: dict[float, float]) -> bool:
    """The bug signature: an interior link whose resistance moves when only h moves."""
    return len(set(values_by_h.values())) > 1


class FrozenEquationTests(unittest.TestCase):
    def setUp(self):
        self.stack = slab049.tap_stack(50.0)
        self.cell = 0.05 / 64

    def links(self, coupling: str, multiplier: float):
        return cell_resistances(self.stack.with_h_multiplier(multiplier), self.cell, self.cell, coupling)

    def test_old_interior_link_moves_with_h_and_new_does_not(self):
        old = {m: self.links(OLD, m).spreader_sink for m in H_VALUES}
        new = {m: self.links(NEW, m).spreader_sink for m in H_VALUES}
        self.assertTrue(h_dependent(old), "OLD must show the bug signature")
        self.assertFalse(h_dependent(new), "NEW interior link must not depend on h")
        self.assertEqual(sorted(old, key=old.get), sorted(H_VALUES, reverse=True))

    def test_convection_stays_on_the_sink_ambient_link_in_both_couplings(self):
        for multiplier in H_VALUES:
            old, new = self.links(OLD, multiplier), self.links(NEW, multiplier)
            self.assertEqual(old.sink_ambient, new.sink_ambient)
            self.assertEqual(new.sink_ambient, new.sink_material_rz + new.sink_convection_rz)
            self.assertEqual(new.spreader_sink, new.spreader_rz / 2.0 + new.sink_material_rz / 2.0)
            self.assertEqual(old.spreader_sink, old.spreader_rz / 2.0 + old.sink_rz / 2.0)

    def test_per_area_form_puts_half_the_convection_inside_the_old_link(self):
        old, new = area_resistances(self.stack, OLD), area_resistances(self.stack, NEW)
        self.assertAlmostEqual(old["convection"], 1 / self.stack.heat_transfer_coefficient, places=15)
        self.assertAlmostEqual(old["spreader_sink"] - new["spreader_sink"], old["convection"] / 2, places=15)
        self.assertAlmostEqual(old["convection_inside_interior_link"], 1.8e-4, places=12)  # ~1.8 cm^2 K/W
        self.assertEqual(new["convection_inside_interior_link"], 0.0)

    def test_fixture_packages_follow_the_generator(self):
        self.assertEqual(slab049.tap_package(50), {"interposer_mm": 50.0, "s_spreader_m": 0.1, "s_sink_m": 0.2,
                                                  "r_convec_K_per_W": 0.008999999999999998})
        package45 = slab049.tap_package(45)
        self.assertEqual((package45["s_spreader_m"], package45["s_sink_m"]), (0.09, 0.18))
        self.assertAlmostEqual(package45["r_convec_K_per_W"], 0.0111111111111, places=12)
        # Both fixtures keep HotSpot's default h.
        for size in (45.0, 50.0):
            self.assertAlmostEqual(slab049.tap_stack(size).heat_transfer_coefficient, slab049.default_h(), places=6)

    def test_unknown_coupling_is_rejected(self):
        with self.assertRaises(ValueError):
            cell_resistances(self.stack, self.cell, self.cell, "material")


class SourceIdentityTests(unittest.TestCase):
    def test_default_build_compiles_the_unmodified_upstream_source(self):
        stripped = strip_variant_blocks(GRID_SOURCE.read_text(encoding="utf-8"))
        self.assertEqual(hashlib.sha256(stripped.encode("utf-8")).hexdigest(), PRISTINE_TEMPERATURE_GRID_SHA256)

    def test_variant_is_two_blocks_behind_the_macro(self):
        source = GRID_SOURCE.read_text(encoding="utf-8")
        self.assertEqual(source.count(f"#if {VARIANT_MACRO}"), 2)
        self.assertEqual(source.count(DEFAULT_LINE), 1)
        self.assertIn(VARIANT_TAG.decode("ascii"), source)

    def test_mutated_default_branch_breaks_the_identity(self):
        source = GRID_SOURCE.read_text(encoding="utf-8").replace(DEFAULT_LINE, DEFAULT_LINE.replace("/ 2.0);", "/ 1.999);"))
        stripped = strip_variant_blocks(source)
        self.assertNotEqual(hashlib.sha256(stripped.encode("utf-8")).hexdigest(), PRISTINE_TEMPERATURE_GRID_SHA256)

    def test_strip_rejects_malformed_blocks(self):
        with self.assertRaises(ValueError):
            strip_variant_blocks(f"#if {VARIANT_MACRO}\nint x;\n")
        with self.assertRaises(ValueError):
            strip_variant_blocks(f"#if {VARIANT_MACRO}\n#if 1\n#endif\n#endif\n")

    def test_default_make_target_and_ignore_rules(self):
        makefile = (HOTSPOT_ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("all:\thotspot hotfloorplan lib\n", makefile)
        self.assertIn(f"-D{VARIANT_MACRO}=1 -c temperature_grid.c -o $(VARIANT_GRIDOBJ)", makefile)
        # The image may not carry the ignore files; where they exist they must list the variant binary.
        for ignore in (REPO_ROOT / ".gitignore", REPO_ROOT / ".dockerignore"):
            if ignore.is_file():
                self.assertIn("sundai_hotspot/hotspot-material-only", ignore.read_text(encoding="utf-8"))


class CommittedOutputTests(unittest.TestCase):
    """The 2026-10-18 probe kept every layer's grid temperatures; these checks only read them."""

    @classmethod
    def setUpClass(cls):
        cls.cases = sorted(p for p in slab049.PROBE_RESULTS.iterdir() if (p / "sample.grid.steady").is_file())
        if len(cls.cases) != 8:
            raise AssertionError("expected the eight committed probe cases")

    def test_committed_solver_output_satisfies_old_coupling_and_violates_new(self):
        for record in slab049.committed_output_residuals():
            with self.subTest(case=record["case"]):
                self.assertEqual(record[OLD]["cells_outside_rounding_bound"], 0)
                self.assertEqual(record[NEW]["cells_outside_rounding_bound"], record[NEW]["cells_checked"])
                self.assertGreater(record[NEW]["worst_residual_over_bound"], 100.0)

    def test_block_extents_reproduce_hotspot_max_mapping(self):
        for case in self.cases:
            layers = slab049.read_lcf(case / "samplelayers.lcf", case)
            grid = slab049.read_grid(case / "sample.grid.steady")
            n = int(math.isqrt(len(grid[0])))
            width, height = slab049.total_extent(slab049.read_flp(layers[0]["flp"]))
            steady = dict(slab049.read_steady(case / "sample.steady"))
            checked = 0
            for layer in range(len(layers) + 2):
                floorplan = layers[min(layer, len(layers) - 1)]["flp"]
                prefix = (f"layer_{layer}_" if layer < len(layers) else ("hsp_" if layer == len(layers) else "hsink_"))
                for unit in slab049.read_flp(floorplan):
                    i1, i2, j1, j2 = slab049.block_extent(unit, width, height, n, n)
                    block_max = max(grid[layer][i * n + j] for i in range(i1, i2) for j in range(j1, j2))
                    self.assertEqual(block_max, steady[prefix + unit["name"]], (case.name, layer, unit["name"]))
                    checked += 1
            self.assertGreater(checked, 50)

    def test_center_mapping_uses_one_two_or_four_cells(self):
        self.assertEqual(slab049.center_cells((0, 3, 0, 3)), [{"row": 1, "col": 1, "weight": 1.0}])
        self.assertEqual(len(slab049.center_cells((0, 4, 0, 3))), 2)
        self.assertEqual([c["weight"] for c in slab049.center_cells((0, 4, 0, 4))], [0.25] * 4)

    def test_solve_record_carries_every_requested_field(self):
        case = slab049.PROBE_RESULTS / "baseline_center_32"
        report = json.loads((slab049.PROBE_RESULTS / "combined_report.json").read_text(encoding="utf-8"))
        expected_peak = next(r["chip_layer_peak_C"] for r in report["runs"]
                             if r["placement"] == "baseline_center" and r["grid_rows"] == 32)
        record = slab049.summarize_evaluation(case, expected_package=slab049.tap_package(50), grid_size=32)
        self.assertTrue(record["package_matches_fixture"])
        self.assertFalse(slab049.summarize_evaluation(case, expected_package=slab049.tap_package(45))
                         ["package_matches_fixture"])
        self.assertEqual(record["output_precision"], {"grid_decimals_K": 2, "steady_decimals_K": 2})
        self.assertEqual(record["config_sha256"], record["files"]["new_hotspot.config"]["sha256"])
        peak = record["active_layer_grid_peak"]
        self.assertEqual(peak["layer"], 4)
        self.assertAlmostEqual(peak["peak_C"], expected_peak, places=9)
        self.assertTrue(all(0 <= c["row"] < 32 and 0 <= c["col"] < 32 for c in peak["argmax"]))
        mapping = record["chiplet_centre_mapping"]
        self.assertEqual(len(mapping["chiplets"]), 6)
        for chiplet in mapping["chiplets"]:
            self.assertIn(chiplet["distinct_cells"], (1, 2, 4))
            self.assertAlmostEqual(sum(c["weight"] for c in chiplet["cells"]), 1.0)
            self.assertLessEqual(chiplet["centre_C"], peak["peak_C"] + 1e-9)
        self.assertEqual(mapping["max_C"], max(c["centre_C"] for c in mapping["chiplets"]))
        selector = record["historical_tap_stdout_selector"]
        self.assertFalse(selector["literal_on_stdout"]["applicable"])  # HotSpot 7 prints no temperatures
        self.assertGreaterEqual(selector["on_steady_file_C"], peak["peak_C"] - 1e-9)  # this run mapped max
        rises = record["spreader_sink_hottest_cell_rises"]
        self.assertAlmostEqual(rises["spreader"]["rise_K"], 70.11, places=6)
        self.assertAlmostEqual(rises["sink"]["rise_K"], 18.51, places=6)
        self.assertEqual(rises["pattern"]["pattern"], "v7-link")

    def test_committed_probes_show_the_v7_link_signature_with_scaled_convection(self):
        records = slab049.committed_run1_signature()
        self.assertEqual(len(records), 8)
        for record in records:
            self.assertTrue(record["r_convec_is_generator_scaled"], record["case"])
            self.assertEqual(record["pattern"], "v7-link", record["case"])
            self.assertGreater(record["spreader_rise_K"] - record["sink_rise_K"], 50.0)


def _grid_lines(case: Path) -> list[str]:
    return (case / "sample.grid.steady").read_text(encoding="utf-8").splitlines(keepends=True)


class GridParserTests(unittest.TestCase):
    """Strict parsing (astra #56785): one mutated input per rule, plus the unmodified control."""

    CASE = slab049.PROBE_RESULTS / "baseline_center_32"

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="slab049-grid-")
        self.lines = _grid_lines(self.CASE)
        self.header4 = self.lines.index("Layer 4:\n")
        self.header5 = self.lines.index("Layer 5:\n")

    def tearDown(self):
        self.directory.cleanup()

    def parse(self, lines: list[str], **kwargs) -> dict:
        path = Path(self.directory.name) / "sample.grid.steady"
        path.write_text("".join(lines), encoding="utf-8")
        return slab049.read_grid(path, **kwargs)

    def summarize(self, lines: list[str]) -> dict:
        case = Path(self.directory.name) / "case"
        if not case.exists():
            shutil.copytree(self.CASE, case)
        (case / "sample.grid.steady").write_text("".join(lines), encoding="utf-8")
        return slab049.summarize_evaluation(case)

    def test_the_committed_file_parses(self):
        grid = self.parse(self.lines, grid=32, layers=8, ambient_k=318.15)
        self.assertEqual(sorted(grid), list(range(8)))
        self.assertTrue(all(len(values) == 1024 for values in grid.values()))

    def test_astra_control_an_extra_cell_in_layer_4_is_rejected(self):
        mutated = self.lines[:self.header5] + ["1024\t999.00\n"] + self.lines[self.header5:]
        with self.assertRaises(slab049.GridFormatError):
            self.parse(mutated)
        with self.assertRaises(slab049.GridFormatError):
            self.summarize(mutated)

    def test_astra_control_a_duplicate_layer_4_is_rejected(self):
        mutated = self.lines + self.lines[self.header4:self.header5]
        with self.assertRaises(slab049.GridFormatError):
            self.parse(mutated)
        with self.assertRaises(slab049.GridFormatError):
            self.summarize(mutated)

    def test_each_rule_rejects_its_own_mutation(self):
        cell = self.header4 + 1  # "0\t..." of layer 4
        mutations = {
            "missing cell": self.lines[:cell] + self.lines[cell + 1:],
            "out-of-order index": self.lines[:cell] + ["5\t330.00\n"] + self.lines[cell + 1:],
            "malformed cell": self.lines[:cell] + ["0 330.00 extra\n"] + self.lines[cell + 1:],
            "malformed header": self.lines[:self.header4] + ["Layer four:\n"] + self.lines[self.header4 + 1:],
            "missing layer": self.lines[:self.header4] + self.lines[self.header5:],
            "nan": self.lines[:cell] + ["0\tnan\n"] + self.lines[cell + 1:],
            "infinity": self.lines[:cell] + ["0\tinf\n"] + self.lines[cell + 1:],
            "not above 0 K": self.lines[:cell] + ["0\t0.00\n"] + self.lines[cell + 1:],
            "implausibly hot": self.lines[:cell] + ["0\t2500.00\n"] + self.lines[cell + 1:],
            "below ambient": self.lines[:cell] + ["0\t300.00\n"] + self.lines[cell + 1:],
            "headerless cells before a header": ["0\t330.00\n"] + self.lines,
        }
        for rule, lines in mutations.items():
            with self.subTest(rule=rule), self.assertRaises(slab049.GridFormatError):
                self.parse(lines, layers=8, ambient_k=318.15)
        with self.assertRaises(slab049.GridFormatError):  # the grid size is enforced when known
            self.parse(self.lines, grid=64)
        with self.assertRaises(slab049.GridFormatError):  # the layer count is enforced when known
            self.parse(self.lines, layers=9)

    def test_argmax_is_always_inside_the_grid(self):
        self.assertEqual(slab049.grid_argmax([1.0, 3.0, 2.0, 3.0], 2), [{"row": 0, "col": 1}, {"row": 1, "col": 1}])
        with self.assertRaises(slab049.GridFormatError):
            slab049.grid_argmax([1.0, 2.0, 3.0, 4.0, 999.0], 2)

    def test_upstream_hotspot6_top_layer_only_format_parses_as_one_layer(self):
        rows = ["%d\t%.2f\n" % (i, 330.0) for i in range(16)]
        grid = self.parse(rows[:4] + ["\n"] + rows[4:8] + ["\n"] + rows[8:12] + ["\n"] + rows[12:] + ["\n"], grid=4)
        self.assertEqual(list(grid), [0])


class GeneratedArtifactTests(unittest.TestCase):
    """The committed SLAB-049 files must be exactly what the frozen code generates."""

    def test_manifest_slab_and_reference_inputs_are_current(self):
        directory = slab049.EVIDENCE_DIR
        self.assertEqual((directory / "CALL-LIST.json").read_bytes(), slab049._dump(slab049.build_call_list()))
        for name, data in slab049.slab_files().items():
            self.assertEqual((directory / "slab" / name).read_bytes(), data, name)
        for layout, variant in slab049.REFERENCE_SETS:
            folder = REPO_ROOT / slab049.reference_dir(layout, variant)
            for name, data in slab049.reference_files(layout, variant).items():
                self.assertEqual((folder / name).read_bytes(), data, (layout, variant, name))

    def test_frozen_analytic_report_is_current(self):
        committed = json.loads((slab049.EVIDENCE_DIR / "ANALYTIC.json").read_text(encoding="utf-8"))
        self.assertIn("assembly_confirmation", committed)
        committed.pop("assembly_confirmation")
        self.assertEqual(committed, json.loads(slab049._dump(slab049.analytic_report(include_assembly=False))))

    def test_manifest_is_twelve_calls_within_the_cap(self):
        manifest = slab049.build_call_list()
        calls = manifest["calls"]
        self.assertEqual(len(calls), 12)
        self.assertEqual(len({c["id"] for c in calls}), 12)
        primary = [c for c in calls if c["replay_of"] is None]
        replays = [c for c in calls if c["replay_of"] is not None]
        self.assertEqual(len(primary), 8)
        self.assertEqual({(c["kind"], c["reference"], c["grid"]) for c in primary},
                         {(k, f"{r}-snapped", g) for k in ("hotspot6", "hotspot7_default")
                          for r in ("ascend910-original", "micro150-original") for g in (32, 64)})
        self.assertEqual(len(replays), 4)
        self.assertTrue(all(c["grid"] == 64 and c["replay_of"] in {p["id"] for p in primary} for c in replays))
        self.assertEqual({c["id"] for c in calls if c["gating"]},
                         {"p-hs6-ascend910-original-g64", "p-hs6-micro150-original-g64"})
        accounting = manifest["accounting"]
        self.assertEqual((accounting["max_runs"], accounting["retries"]), (12, 0))
        self.assertLessEqual(accounting["cpu_cap_minutes"], 30)
        self.assertGreaterEqual(accounting["cpu_cap_minutes"] * 60, accounting["worst_case_cpu_s"])
        for call in calls:
            folder = REPO_ROOT / call["inputs"]["dir"]
            self.assertEqual(hashlib.sha256((folder / "SHA256SUMS").read_bytes()).hexdigest(),
                             call["inputs"]["sha256sums_sha256"])
        for path, digest in manifest["source"]["files_sha256"].items():
            self.assertEqual(hashlib.sha256((REPO_ROOT / path).read_bytes()).hexdigest(), digest, path)
        self.assertIn("not_requested", manifest)

    def test_slab_predictions_stay_bounded_diagnostic_evidence(self):
        for kind, drop in ((NEW, 2.4675), ("hotspot6", 1.26)):
            values = {m: round(slab049.slab_prediction(kind, m)["interior_drop_die_minus_sink_K"], 9) for m in H_VALUES}
            self.assertFalse(h_dependent(values), kind)
            self.assertAlmostEqual(values[1.0], drop, places=6)
        self.assertTrue(h_dependent({m: slab049.slab_prediction(OLD, m)["interior_drop_die_minus_sink_K"]
                                     for m in H_VALUES}))


class OracleIdentityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="slab049-identity-")
        root = Path(self.directory.name)
        self.untagged = root / "hotspot-default"
        self.untagged.write_bytes(b"placeholder default binary")
        self.tagged = root / "hotspot-material-only"
        self.tagged.write_bytes(b"placeholder microchannel\0" + VARIANT_TAG + b"\0variant")
        self.root = root

    def tearDown(self):
        self.directory.cleanup()

    def test_variant_oracle_refuses_a_binary_without_the_tag(self):
        with self.assertRaises(HotSpotOracleError):
            MaterialOnlyCouplingOracle(16, 16, hotspot_binary=self.untagged)

    def test_variant_identity_names_the_coupling_and_never_equals_the_default(self):
        variant = MaterialOnlyCouplingOracle(16, 16, hotspot_binary=self.tagged)
        same_binary_default = HotSpotOracle(16, 16, hotspot_binary=self.tagged)
        self.assertEqual(variant.base_problem_hash, same_binary_default.problem_hash)
        self.assertNotEqual(variant.problem_hash, same_binary_default.problem_hash)
        self.assertIn("+SLAB-049:coupling=material_only:", variant.solver_version)
        self.assertNotIn("coupling", same_binary_default.solver_version)
        sources = dict(variant.problem.generator_sha256)
        for path in VARIANT_SOURCES:
            self.assertEqual(sources[path], hashlib.sha256((REPO_ROOT / path).read_bytes()).hexdigest())
        for path in VARIANT_SOURCES:
            self.assertNotIn(path, dict(same_binary_default.problem.generator_sha256))

    def test_variant_refuses_evaluations_without_a_gate_zero_pass(self):
        variant = MaterialOnlyCouplingOracle(4, 4, hotspot_binary=self.tagged)
        design = variant.design_from_centers(((25, 25), (40, 40), (8, 9), (8, 25), (8, 41), (41, 15)))
        with self.assertRaises(GateZeroRefusal):
            asyncio.run(variant(design))

    def test_variant_result_is_labelled(self):
        from sundai_hotspot.test_gate_zero import passing_record
        record = passing_record(self.root / "receipts", "material_only", self.tagged)
        variant = MaterialOnlyCouplingOracle(4, 4, hotspot_binary=self.tagged, gate_zero_record=record)
        design = variant.design_from_centers(((25, 25), (40, 40), (8, 9), (8, 25), (8, 41), (41, 15)))
        response = {
            "candidate_hash": design.hash, "problem_hash": variant.problem_hash,
            "binary_sha256": variant.problem.hotspot_binary_sha256, "grid_rows": 4, "grid_cols": 4,
            "heatmap_c": [[60.0] * 4 for _ in range(4)], "maximum_temperature_c": 60.0, "all_layers_peak_c": 60.0,
            "solver_seconds": 0.1, "input_generation_seconds": 0.01,
            "input_sha256": {name: "a" * 64 for name in (
                "new_hotspot.config", "sampleL0_Substrate.flp", "sampleL1_C4Layer.flp", "sampleL2_Interposer.flp",
                "sampleL3_UbumpLayer.flp", "sampleL4_ChipLayer.flp", "sampleL5_TIM.flp", "samplelayers.lcf",
                "sample.ptrace")},
        }
        async def evaluate_once():
            try:
                return await variant(design)
            finally:
                await variant.aclose()

        with mock.patch("sundai_hotspot.tap_oracle._run_worker", new_callable=mock.AsyncMock,
                        return_value=response) as worker:
            result = asyncio.run(evaluate_once())
        request = worker.await_args.args[0]
        self.assertEqual(request["problem_hash"], variant.problem_hash)
        for path in VARIANT_SOURCES:
            self.assertIn(path, request["expected_source_sha256"])
        self.assertIn("coupling=material_only", result.evidence_kind)
        self.assertIn("coupling=material_only", result.solver_version)

    @unittest.skipUnless(HOTSPOT_BINARY.is_file() and VARIANT_BINARY.is_file(), "both HotSpot binaries are built in the image")
    def test_built_binaries_carry_the_right_identity(self):
        self.assertNotIn(VARIANT_TAG, HOTSPOT_BINARY.read_bytes())
        self.assertIn(VARIANT_TAG, VARIANT_BINARY.read_bytes())
        MaterialOnlyCouplingOracle(16, 16)
        with self.assertRaises(HotSpotOracleError):
            MaterialOnlyCouplingOracle(16, 16, hotspot_binary=HOTSPOT_BINARY)


@unittest.skipIf(os.name != "posix", "HotSpot and SuperLU build on POSIX only (the CI image runs these)")
class NativeAssemblyTests(unittest.TestCase):
    """Compile temperature_grid.c variants and compare assembled conductance matrices. No solves."""

    GRID = 16

    @classmethod
    def setUpClass(cls):
        problem = slab049.native_toolchain_problem()
        if problem:
            raise AssertionError(f"native assembly tests need gcc and SuperLU: {problem}")
        cls.directory = tempfile.TemporaryDirectory(prefix="slab049-native-")
        root = Path(cls.directory.name)
        cls.harness = slab049.AssemblyHarness(root / "build")
        current = GRID_SOURCE.read_text(encoding="utf-8")
        if current.count(VARIANT_SINK_TEST) != 1:
            raise AssertionError("variant sink test line moved; update the mutation")
        builds = {
            "pristine": (strip_variant_blocks(current), ()),
            "default": (current, ()),
            "variant": (current, (f"-D{VARIANT_MACRO}=1",)),
            # Mutation 1: the flag compiles, but the sink keeps its convection share in the interior link.
            "mutant_variant": (current.replace(VARIANT_SINK_TEST, "  if (0 && n == hsidx)\n"), (f"-D{VARIANT_MACRO}=1",)),
            # Mutation 2: the default branch changes.
            "mutant_default": (current.replace(DEFAULT_LINE, DEFAULT_LINE.replace("/ 2.0);", "/ 1.999);")), ()),
        }
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(5, os.cpu_count() or 1)) as pool:
            futures = {label: pool.submit(cls.harness.build, label, text, flags) for label, (text, flags) in builds.items()}
            cls.binaries = {label: future.result() for label, future in futures.items()}
        cls.inputs = root / "inputs"
        cls.config, cls.lcf = slab049.stage_probe_inputs(slab049.PROBE_RESULTS / "baseline_center_32", cls.inputs)
        base = float(slab049.read_hotspot_config(cls.inputs / cls.config)["r_convec"])
        cls.runs = {label: {m: cls.harness.run(binary, cls.inputs, cls.config, cls.lcf, cls.GRID, base / m)
                            for m in (0.5, 1.0, 2.0)}
                    for label, binary in cls.binaries.items()}

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def link(self, label: str, multiplier: float) -> float:
        run = self.runs[label][multiplier]
        return run["vertical"][(run["spreader"], run["sink"])]

    def test_default_object_is_byte_identical_to_the_upstream_object(self):
        default = (self.binaries["default"].parent / "temperature_grid.o").read_bytes()
        pristine = (self.binaries["pristine"].parent / "temperature_grid.o").read_bytes()
        self.assertEqual(hashlib.sha256(default).hexdigest(), hashlib.sha256(pristine).hexdigest())

    def test_default_assembly_is_byte_identical_to_upstream(self):
        for multiplier in (0.5, 1.0, 2.0):
            self.assertEqual(self.runs["default"][multiplier]["matrix"]["bytes"],
                             self.runs["pristine"][multiplier]["matrix"]["bytes"])

    def test_assembly_matches_the_frozen_equations(self):
        for label, coupling in (("default", OLD), ("variant", NEW)):
            for multiplier in (0.5, 1.0, 2.0):
                run = self.runs[label][multiplier]
                layers = run["layers"]
                stack = PackageStack(layers[run["spreader"]]["k"], layers[run["spreader"]]["thickness"],
                                     layers[run["sink"]]["k"], layers[run["sink"]]["thickness"],
                                     run["r_convec"], run["s_sink"])
                frozen = cell_resistances(stack, run["cell_width"], run["cell_height"], coupling)
                self.assertEqual(self.link(label, multiplier), frozen.spreader_sink)
                self.assertEqual(run["sink_ambient"], frozen.sink_ambient)

    def test_only_the_spreader_sink_link_depends_on_h_in_old_and_nothing_interior_in_new(self):
        self.assertTrue(h_dependent({m: self.link("default", m) for m in (0.5, 1.0, 2.0)}))
        self.assertFalse(h_dependent({m: self.link("variant", m) for m in (0.5, 1.0, 2.0)}))
        for label in ("default", "variant"):
            run = self.runs[label][1.0]
            for pair, value in run["vertical"].items():
                if pair != (run["spreader"], run["sink"]):
                    self.assertFalse(h_dependent({m: self.runs[label][m]["vertical"][pair] for m in (0.5, 1.0, 2.0)}))
                    self.assertEqual(value, self.runs["default"][1.0]["vertical"][pair])

    def test_variant_changes_only_spreader_sink_entries(self):
        for multiplier in (0.5, 1.0, 2.0):
            default = slab049.matrix_entries(self.runs["default"][multiplier]["matrix"])
            variant = slab049.matrix_entries(self.runs["variant"][multiplier]["matrix"])
            self.assertEqual(default.keys(), variant.keys())
            run = self.runs["variant"][multiplier]
            cells = run["rows"] * run["cols"]
            sp, hs = run["spreader"] * cells, run["sink"] * cells
            expected = set()
            for k in range(cells):
                expected |= {(sp + k, sp + k), (sp + k, hs + k), (hs + k, sp + k), (hs + k, hs + k)}
            changed = {key for key in default if default[key] != variant[key]}
            self.assertEqual(changed, expected)
            coupling = self.link("variant", multiplier)
            for k in range(cells):
                self.assertEqual(variant[(sp + k, hs + k)], -1.0 / coupling)
                self.assertEqual(variant[(hs + k, sp + k)], -1.0 / coupling)

    def test_mutation_keeping_convection_in_the_variant_is_caught(self):
        self.assertTrue(h_dependent({m: self.link("mutant_variant", m) for m in (0.5, 1.0, 2.0)}))

    def test_mutation_of_the_default_branch_is_caught(self):
        self.assertNotEqual(self.runs["mutant_default"][1.0]["matrix"]["bytes"],
                            self.runs["pristine"][1.0]["matrix"]["bytes"])


if __name__ == "__main__":
    unittest.main()
