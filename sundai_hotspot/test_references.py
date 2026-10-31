"""SLAB-048: 45 mm fixtures, rotation in every geometry consumer, reference layouts and the envelope plan.

Geometry only. HotSpot never runs: the oracle test stops at the worker boundary, and the worker test
calls TAP's input generator without the solver. The check_* functions take a module bundle so that
test_slab048_mutations.py can rerun each one against a mutated module and require it to fail.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from dataclasses import asdict, replace
from unittest import mock

from sentilab_core import conductor as real_conductor
from sundai_hotspot import tap_oracle as real_tap_oracle
from sundai_hotspot import tap_references
from sundai_hotspot.tap_oracle import REPO_ROOT, TAP_CONFIGS, TAP_ROOT, WORKER, TapGeometry

REAL = types.SimpleNamespace(tap_oracle=real_tap_oracle, conductor=real_conductor, worker_source=WORKER)
REFERENCES_DIR = tap_references.REFERENCES_DIR
ASCEND_50_SHA = "548562a5f49d502f4b9bd03d3a4acc4b42f225056e6d91556416079c291e06d4"
MICRO150_50_SHA = "c31956e38b05fc0d31609656e6c92f29109ec3dee6b148b3b1c28c23c2dd1b18"
# The Ascend 910 reference (docs/sentilab/references/ascend910-tap25d-fig6a.json).
RAW = ((17.1501, 22.6003), (38.3497, 22.6003), (7.335, 11.1256), (21.3048, 11.1256),
       (7.335, 33.8754), (21.3048, 33.8754))
SNAPPED = ((17, 23), (39, 23), (7, 11), (21, 11), (7, 35), (21, 35))
ROTATED = (True, False, True, True, True, True)


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def reference(name: str) -> dict:
    return _json(REFERENCES_DIR / f"{name}.json")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _close(a: float, b: float, tolerance: float = 1e-9) -> bool:
    return abs(a - b) <= tolerance


def _lattice_free(mods, geometry):
    return mods.tap_oracle.TapGeometry(geometry.problem, replace(geometry.legality, center_lattice_mm=None))


def _rejects(geometry, design, needle: str) -> None:
    try:
        geometry.centers_for(design)
    except ValueError as exc:  # TapLegalityError, from whichever module built the geometry
        assert needle in str(exc), f"rejected for another reason: {exc}"
        return
    raise AssertionError(f"accepted a layout that breaks: {needle}")


# --- fixtures -----------------------------------------------------------------------------------

def check_45mm_fixtures_sit_next_to_unchanged_50mm_ones(mods):
    for family, sha50 in (("ascend910", ASCEND_50_SHA), ("micro150", MICRO150_50_SHA)):
        g50 = mods.tap_oracle.TapGeometry.load(family)
        g45 = mods.tap_oracle.TapGeometry.load(f"{family}-45mm")
        assert (g50.fixture_id, g45.fixture_id) == (family, f"{family}-45mm"), (g50.fixture_id, g45.fixture_id)
        assert (g50.problem.interposer_size_mm, g45.problem.interposer_size_mm) == (50.0, 45.0)
        assert g50.problem.config_sha256 == sha50 and g45.problem.config_sha256 != sha50
        for field in ("widths_mm", "heights_mm", "powers_w", "connections", "link_type", "granularity_mm",
                      "bump_halos_mm", "ambient_c"):
            assert getattr(g45.problem, field) == getattr(g50.problem, field), field
        assert (g50.legality.rotation, g50.legality.center_lattice_mm, g50.legality.min_die_gap_mm) == \
            ("catalog", 1.0, 0.0), g50.legality
        assert (g45.legality.rotation, g45.legality.center_lattice_mm, g45.legality.min_die_gap_mm) == \
            ("per_die_90", 0.5, 0.1), g45.legality


def check_frame_reaches_the_worker_request(mods):
    request = _captured_request(mods)
    assert request["tap_parameters"]["interposer_size_mm"] == 45.0, request["tap_parameters"]


def check_request_carries_rotation(mods):
    request = _captured_request(mods)
    assert request["rotated"] == list(ROTATED), request["rotated"]
    assert [list(c) for c in request["centers_mm"]] == [[float(v) for v in c] for c in SNAPPED]


def _captured_request(mods) -> dict:
    captured = {}

    class Captured(Exception):
        pass

    async def capture(request, **_):
        captured.update(request)
        raise Captured()

    with tempfile.TemporaryDirectory() as directory:
        binary = Path(directory) / "hotspot-placeholder"
        binary.write_bytes(b"placeholder: hashed for identity, never executed")
        oracle = mods.tap_oracle.HotSpotOracle(16, 16, fixture="ascend910-45mm", hotspot_binary=binary)
        design = oracle.design_from_centers(SNAPPED, ROTATED)

        async def run():
            try:
                await oracle(design)
            finally:
                await oracle.aclose()

        with mock.patch.object(mods.tap_oracle, "_run_worker", capture):
            try:
                asyncio.run(run())
            except Captured:
                pass
    assert captured, "the oracle never reached the worker boundary"
    return captured


# --- rotation legality and footprint consumers ---------------------------------------------------

def check_orientation_catalog_is_per_fixture(mods):
    g45 = mods.tap_oracle.TapGeometry.load("ascend910-45mm")
    g45.centers_for(g45.design_from_centers(SNAPPED, ROTATED))  # turned dies are in the 45 mm catalog
    g50 = mods.tap_oracle.TapGeometry.load("ascend910")
    _rejects(g50, g50.design_from_centers(SNAPPED, ROTATED), "TAP fixture chiplet catalog mismatch")
    micro = mods.tap_oracle.TapGeometry.load("micro150-45mm")
    assert [len(entry) for entry in micro.legality.orientation_catalog_mm] == [2] * 4 + [1] * 4


def check_margin_reads_the_turned_footprint(mods):
    g45 = mods.tap_oracle.TapGeometry.load("ascend910-45mm")
    # HBM 3 turned (11.87 mm wide) beside the right edge: its halo crosses the 0.5 mm margin, while the
    # catalog 7.75 mm footprint at the same centre would be legal there.
    centers = list(SNAPPED)
    centers[3] = (39, 8.5)
    _rejects(g45, g45.design_from_centers(centers, ROTATED), "chiplet 3 violates the 0.5 mm interposer margin")
    g45.centers_for(g45.design_from_centers(centers, ROTATED[:3] + (False,) + ROTATED[4:]))


def check_raw_layout_is_physically_legal_only_as_turned(mods):
    physical = _lattice_free(mods, mods.tap_oracle.TapGeometry.load("ascend910-45mm"))
    physical.centers_for(physical.design_from_centers(RAW, ROTATED))


def check_halo_overlap_is_refused(mods):
    g50 = _lattice_free(mods, mods.tap_oracle.TapGeometry.load("ascend910"))
    # Nimbus 0.05 mm from Vitruvian: the bodies are apart, their microbump halos (0.09 + 0.045) are not.
    centers = ((25, 25), (25 + 7.25 + 0.05 + 5.25, 25), (8, 8), (8, 22), (8, 36), (42, 8))
    _rejects(g50, g50.design_from_centers(centers), "chiplets 0 and 1 overlap with their microbump halos")


def check_min_spacing_is_a_45mm_rule(mods):
    # HBMs 2 and 3 sit 0.095 mm apart: clear of their 0.045 mm halos, closer than TAP-2.5D's 0.1 mm gap.
    centers = ((37, 22.5), (22, 36), (8, 8), (8 + 7.75 + 0.095, 8), (8, 22), (8, 36))
    g45 = _lattice_free(mods, mods.tap_oracle.TapGeometry.load("ascend910-45mm"))
    _rejects(g45, g45.design_from_centers(centers), "chiplets 2 and 3 are 0.0950 mm apart, under the 0.1 mm")
    g50 = _lattice_free(mods, mods.tap_oracle.TapGeometry.load("ascend910"))
    g50.centers_for(g50.design_from_centers(centers))  # the 50 mm fixture keeps halo clearance as its only gap


def check_center_lattice(mods):
    g45 = mods.tap_oracle.TapGeometry.load("ascend910-45mm")
    _rejects(g45, g45.design_from_centers(RAW, ROTATED), "off the 0.5 mm placement grid")
    half_step = list(SNAPPED)
    half_step[0] = (17.5, 23)
    g45.centers_for(g45.design_from_centers(half_step, ROTATED))


def check_wire_proxy_reproduces_the_human_ascend_layout(mods):
    physical = _lattice_free(mods, mods.tap_oracle.TapGeometry.load("ascend910-45mm"))
    centers = physical.centers_for(physical.design_from_centers(RAW, ROTATED))
    wire = physical.wirelength_mm(centers)
    assert round(wire, 2) == 18.82, wire


def check_view_geometry_uses_the_turned_footprint(mods):
    geometry = TapGeometry.load("ascend910-45mm")
    design = geometry.design_from_centers(SNAPPED, ROTATED)
    rects = mods.conductor.view_geometry(design)
    for rect, (x, y), turned, width, height in zip(rects, SNAPPED, ROTATED, geometry.problem.widths_mm,
                                                    geometry.problem.heights_mm):
        expected = (height, width) if turned else (width, height)
        assert (rect["w"], rect["h"]) == expected, (rect, expected)
        assert _close(rect["xLL"] + rect["w"] / 2, x) and _close(rect["yLL"] + rect["h"] / 2, y), rect


GENERATE = r'''
import json, sys, types
from pathlib import Path
real, source, params, out = sys.argv[1:5]
module = types.ModuleType("tap_oracle_worker_under_test")
module.__file__ = real
exec(compile(Path(source).read_text(encoding="utf-8"), real, "exec"), module.__dict__)
module.generate_inputs(Path(out), **json.loads(Path(params).read_text(encoding="utf-8")))
'''


def generated_inputs(worker_source: Path, geometry, centers, rotated) -> dict[str, str]:
    """TAP input generation only, in a child process at TAP_ROOT (TAP reads util/ relative to cwd)."""
    problem = geometry.problem
    params = {"size": problem.interposer_size_mm, "granularity": problem.granularity_mm,
              "widths": list(problem.widths_mm), "heights": list(problem.heights_mm),
              "powers": list(problem.powers_w), "connections": [list(row) for row in problem.connections],
              "link_type": problem.link_type, "halos": list(problem.bump_halos_mm),
              "points": [[float(v) for v in c] for c in centers], "rotated": list(rotated)}
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "out").mkdir()
        (root / "params.json").write_text(json.dumps(params), encoding="utf-8")
        result = subprocess.run([sys.executable, "-c", GENERATE, str(WORKER), str(worker_source),
                                 str(root / "params.json"), str(root / "out")], cwd=TAP_ROOT,
                                capture_output=True, text=True, timeout=60,
                                env={**os.environ, "PYTHONPATH": str(REPO_ROOT)})
        assert result.returncode == 0, result.stderr[-2000:]
        return {path.name: path.read_text(encoding="utf-8") for path in (root / "out").iterdir()}


def _units(flp: str) -> dict[str, list[float]]:
    rows = (line.split() for line in flp.splitlines())
    return {fields[0]: [float(v) for v in fields[1:5]] for fields in rows if fields and not fields[0].startswith("#")}


def check_worker_writes_the_turned_floorplan(mods):
    geometry = TapGeometry.load("ascend910-45mm")
    units = _units(generated_inputs(mods.worker_source, geometry, SNAPPED, ROTATED)["sampleL4_ChipLayer.flp"])
    for index, ((x, y), turned) in enumerate(zip(SNAPPED, ROTATED)):
        width, height = geometry.problem.widths_mm[index], geometry.problem.heights_mm[index]
        if turned:
            width, height = height, width
        w_m, h_m, left_m, bottom_m = units[f"Chiplet_{index}"]
        assert _close(w_m * 1000, width) and _close(h_m * 1000, height), (index, w_m, h_m)
        assert _close(left_m * 1000 + width / 2, x) and _close(bottom_m * 1000 + height / 2, y), (index, left_m)


def check_worker_writes_the_45mm_package(mods):
    files = generated_inputs(mods.worker_source, TapGeometry.load("ascend910-45mm"), SNAPPED, ROTATED)
    substrate = _units(files["sampleL0_Substrate.flp"])["Substrate"]
    assert _close(substrate[0], 0.045) and _close(substrate[1], 0.045), substrate
    config = {fields[0]: fields[1] for fields in (line.split() for line in files["new_hotspot.config"].splitlines())
              if len(fields) >= 2 and fields[0].startswith("-")}
    # TAP scales the package with the frame: spreader 2x, sink 4x the interposer edge (metres).
    assert _close(float(config["-s_spreader"]), 0.09) and _close(float(config["-s_sink"]), 0.18), config


# --- reference data -----------------------------------------------------------------------------

def check_raw_reference_is_stored_exactly(ref: dict):
    decode = _json(tap_references.DECODE)
    spec = next(s for s in tap_references.REFERENCES if s["reference_id"] == ref["reference_id"])
    chiplets = decode["figures"][spec["figure"]]["panels"][spec["panel"]]["chiplets"]
    assert ref["raw"]["label"] == tap_references.RAW_LABEL
    assert ref["raw"]["centers_mm"] == [c["decoded_center_mm"] for c in chiplets], "raw centres differ from the decode"
    assert ref["raw"]["rotated"] == [c["rotated_vs_catalog"] for c in chiplets]
    assert ref["raw"]["footprints_mm"] == [c["footprint_mm"] for c in chiplets]
    assert ref["decoding"]["output_sha256"] == _sha256(tap_references.DECODE)
    assert ref["decoding"]["script_sha256"] == _sha256(tap_references.DECODER) == decode["decoder_sha256"]
    assert ref["source"]["pdf_sha256"] == decode["paper"]["pdf_sha256"]
    # The raw layout may be illegal; what is recorded about it must be true.
    geometry = TapGeometry.load(ref["fixture"]["fixture_id"])
    design = geometry.design_from_centers(ref["raw"]["centers_mm"], ref["raw"]["rotated"])
    assert design.hash == ref["raw"]["design_hash"]
    legal, message = tap_references.legal_on(geometry, ref["raw"]["centers_mm"], ref["raw"]["rotated"])
    assert (legal, message) == (ref["raw"]["legal_on_fixture"], ref["raw"]["fixture_gate_message"])


def check_snapped_reference_is_legal_and_explained(ref: dict):
    geometry = TapGeometry.load(ref["fixture"]["fixture_id"])
    snapped = ref["snapped"]
    rotated = snapped["rotated"]
    assert snapped["label"] == tap_references.SNAPPED_LABEL and snapped["is_the_paper_layout"] is False
    assert rotated == ref["raw"]["rotated"]
    rounded = [[math.floor(v + 0.5) * 1.0 for v in c] for c in ref["raw"]["centers_mm"]]
    assert snapped["rounded_centers_mm"] == rounded
    assert [v["message"] for v in snapped["rounded_violations"]] == \
        [v.message for v in geometry.layout_violations(geometry.design_from_centers(rounded, rotated))]
    centers = copy.deepcopy(rounded)
    for adjustment in snapped["adjustments"]:
        centers[adjustment["die"]][0] += adjustment["dx_mm"]
        centers[adjustment["die"]][1] += adjustment["dy_mm"]
    assert centers == snapped["centers_mm"], "rounded centres plus the recorded adjustments are not the snapped layout"
    design = geometry.design_from_centers(centers, rotated)
    geometry.centers_for(design)  # the fixture's own gate
    assert design.hash == snapped["design_hash"]
    for adjustment in snapped["adjustments"]:
        dropped = copy.deepcopy(centers)
        dropped[adjustment["die"]][0] -= adjustment["dx_mm"]
        dropped[adjustment["die"]][1] -= adjustment["dy_mm"]
        violations = geometry.layout_violations(geometry.design_from_centers(dropped, rotated))
        assert violations, f"die {adjustment['die']}'s adjustment is not needed"
        assert [v.message for v in violations] == adjustment["reason"]
    assert bool(snapped["adjustments"]) == bool(snapped["rounded_violations"])
    deltas = [{"die": i, "dx_mm": round(s[0] - r[0], 4) + 0.0, "dy_mm": round(s[1] - r[1], 4) + 0.0}
              for i, (r, s) in enumerate(zip(ref["raw"]["centers_mm"], centers))]
    assert ref["raw_to_snapped_mm"] == deltas


def check_envelope_plan_is_the_exact_sampled_list(plan: dict):
    total = 0
    assert plan["kind"] == "SAMPLED sensitivity envelope, not a bound" and plan["grid"] == 64
    for entry in plan["references"]:
        ref = reference(entry["reference_id"])
        fixture = entry["fixture_id"]
        geometry = TapGeometry.load(fixture)
        assert fixture.endswith("-45mm") and entry["grid"] == 64 and entry["layout"] == tap_references.SNAPPED_LABEL
        assert entry["fixture_config_sha256"] == _sha256(TAP_CONFIGS[fixture])
        base, rotated = ref["snapped"]["centers_mm"], ref["snapped"]["rotated"]
        assert entry["base_design_hash"] == ref["snapped"]["design_hash"]
        expected_calls, expected_excluded = [], []
        options = [(None, None, 0.0)] + [(die, axis, delta) for die in range(len(base)) for axis in ("x", "y")
                                         for delta in (0.5, -0.5)]
        for die, axis, delta in options:
            centers = copy.deepcopy(base)
            if die is not None:
                centers[die][0 if axis == "x" else 1] += delta
            legal, _ = tap_references.legal_on(geometry, centers, rotated)
            (expected_calls if legal else expected_excluded).append((die, axis, delta, centers))
        assert [(c["die"], c["axis"], c["delta_mm"], c["centers_mm"]) for c in entry["calls"]] == expected_calls
        assert [(e["die"], e["axis"], e["delta_mm"]) for e in entry["excluded"]] == \
            [item[:3] for item in expected_excluded]
        for call in entry["calls"]:
            assert call["rotated"] == rotated
            assert geometry.design_from_centers(call["centers_mm"], rotated).hash == call["design_hash"]
        assert entry["considered"] == len(options) == entry["expected_call_count"] + entry["excluded_count"]
        assert entry["expected_call_count"] == len(entry["calls"])
        total += len(entry["calls"])
    assert plan["expected_call_count"] == total
    sizing = plan["sizing"]
    assert sizing["forecast_cpu_s"] < sizing["reserved_cpu_s"] < sizing["proposed_cap_cpu_s"]
    reserve = sum(sizing["reserves_cpu_s_per_call"].values())
    worst_call = sizing["worst_observed_grid64_call_s"] + reserve
    expected_cap = (sizing["reserved_cpu_s"] + sizing["failed_attempt_reserve"]["cpu_s"] + worst_call +
                    sizing["settlement_tail_cpu_s"])
    assert abs(sizing["proposed_cap_cpu_s"] - expected_cap) < 0.01, (sizing["proposed_cap_cpu_s"], expected_cap)
    assert sizing["failed_attempt_reserve"]["calls"] == math.ceil(0.1 * total)
    assert plan["grant"]["granted_by"] is None and plan["grant"]["slab048_prior_solves"] == 0


class FixtureTests(unittest.TestCase):
    def test_45mm_fixtures_sit_next_to_unchanged_50mm_ones(self):
        check_45mm_fixtures_sit_next_to_unchanged_50mm_ones(REAL)

    def test_50mm_physics_contract_equals_the_frozen_mesh_contract(self):
        for family in ("ascend910", "micro150"):
            with self.subTest(fixture=family):
                frozen = _json(REPO_ROOT / f"docs/sentilab/evidence/mesh/{family}/layouts.json")["fixture_contract"]
                problem = asdict(TapGeometry.load(family).problem)
                contract = {k: v for k, v in problem.items()
                            if k not in ("fixture_id", "hotspot_binary_sha256", "generator_sha256")}
                self.assertEqual(json.loads(json.dumps(contract)), frozen)

    def test_fixture_identity_and_problem_hash_differ_per_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "hotspot-placeholder"
            binary.write_bytes(b"placeholder: hashed for identity, never executed")
            oracles = {fixture: real_tap_oracle.HotSpotOracle(16, 16, fixture=fixture, hotspot_binary=binary)
                       for fixture in TAP_CONFIGS}
        self.assertEqual(len({oracle.problem_hash for oracle in oracles.values()}), 4)
        self.assertEqual(len({oracle.solver_version for oracle in oracles.values()}), 4)
        for fixture, oracle in oracles.items():
            self.assertEqual(oracle.fixture_id, fixture)
            self.assertIn(oracle.problem.config_sha256, oracle.solver_version)
            design = oracle.design_from_centers(((20, 20),) * len(oracle.problem.widths_mm))
            self.assertEqual(design.width_mm, oracle.problem.interposer_size_mm)

    def test_fixture_rules_fail_closed(self):
        problem = TapGeometry.load("ascend910-45mm").problem
        for line, bad in ((b"center_lattice_mm = 0.5", b"center_lattice_mm = 0"),
                          (b"center_lattice_mm = 0.5", b"center_lattice_mm = half"),
                          (b"min_die_gap_mm = 0.1", b"min_die_gap_mm = -1"),
                          (b"rotation = per_die_90", b"rotation = free"),
                          (b"rotation = per_die_90", b"rotation = per_die_90\nunknown_rule = 1")):
            with self.subTest(rule=bad), tempfile.TemporaryDirectory() as directory:
                source = TAP_CONFIGS["ascend910-45mm"].read_bytes()
                self.assertEqual(source.count(line), 1)
                config = Path(directory) / "sys_bad.cfg"
                config.write_bytes(source.replace(line, bad))
                with self.assertRaisesRegex(real_tap_oracle.HotSpotOracleError, "SentiLab fixture rule"):
                    real_tap_oracle._load_legality(config, problem)

    def test_frame_reaches_the_worker_request(self):
        check_frame_reaches_the_worker_request(REAL)

    def test_request_carries_rotation(self):
        check_request_carries_rotation(REAL)

    def test_worker_writes_the_45mm_package(self):
        check_worker_writes_the_45mm_package(REAL)


class RotationLegalityTests(unittest.TestCase):
    def test_orientation_catalog_is_per_fixture(self):
        check_orientation_catalog_is_per_fixture(REAL)

    def test_margin_reads_the_turned_footprint(self):
        check_margin_reads_the_turned_footprint(REAL)

    def test_raw_layout_is_physically_legal_only_as_turned(self):
        check_raw_layout_is_physically_legal_only_as_turned(REAL)
        physical = _lattice_free(REAL, TapGeometry.load("ascend910-45mm"))
        _rejects(physical, physical.design_from_centers(RAW), "overlap")  # read unturned, it collides

    def test_halo_overlap_is_refused(self):
        check_halo_overlap_is_refused(REAL)

    def test_min_spacing_is_a_45mm_rule(self):
        check_min_spacing_is_a_45mm_rule(REAL)

    def test_center_lattice(self):
        check_center_lattice(REAL)

    def test_wire_proxy_reproduces_the_human_ascend_layout(self):
        check_wire_proxy_reproduces_the_human_ascend_layout(REAL)

    def test_view_geometry_uses_the_turned_footprint(self):
        check_view_geometry_uses_the_turned_footprint(REAL)
        design = TapGeometry.load("ascend910-45mm").design_from_centers(SNAPPED, ROTATED)
        self.assertEqual(real_conductor.load_design(real_conductor.design_record(design)).hash, design.hash)

    def test_worker_writes_the_turned_floorplan(self):
        check_worker_writes_the_turned_floorplan(REAL)

    def test_worker_rejects_malformed_rotation_flags(self):
        from sundai_hotspot.tap_oracle_worker import evaluate
        geometry = TapGeometry.load("ascend910-45mm")
        problem = asdict(geometry.problem)
        request = {"hotspot_binary": str(Path(__file__)), "expected_binary_sha256": _sha256(Path(__file__)),
                   "expected_source_sha256": {}, "candidate_hash": "0" * 64, "problem_hash": "0" * 64,
                   "grid_rows": 16, "grid_cols": 16, "solver_timeout_s": 1.0,
                   "centers_mm": [list(map(float, c)) for c in SNAPPED],
                   "tap_parameters": {name: problem[name] for name in (
                       "interposer_size_mm", "widths_mm", "heights_mm", "powers_w", "connections",
                       "link_type", "granularity_mm", "bump_halos_mm", "ambient_c")}}
        # The source-hash gate comes first; give it this test file so the request reaches the flags.
        request["expected_source_sha256"] = {Path(__file__).resolve().relative_to(REPO_ROOT).as_posix():
                                             _sha256(Path(__file__))}
        for flags in ([True] * 5, [1] * 6, "all"):
            with self.subTest(flags=flags), self.assertRaisesRegex(ValueError, "rotation flags are malformed"):
                evaluate({**request, "rotated": flags})
        with self.assertRaisesRegex(ValueError, "parent-owned workspace path is missing"):
            evaluate({**request, "rotated": list(ROTATED)})


class ReferenceDataTests(unittest.TestCase):
    NAMES = ("ascend910-tap25d-fig6a", "micro150-tap25d-fig5a")

    def test_raw_reconstructions_are_stored_exactly_and_may_be_illegal(self):
        for name in self.NAMES:
            with self.subTest(reference=name):
                ref = reference(name)
                check_raw_reference_is_stored_exactly(ref)
                self.assertIs(ref["raw"]["legal_on_fixture"], False)
                self.assertTrue(all(v["rule"] == "lattice" for v in ref["raw"]["violations_on_fixture"]))
                self.assertEqual(ref["raw"]["violations_without_center_lattice"], [])

    def test_cpu_dram_die_identity_agrees_with_the_netlist(self):
        # Die identity comes from the figure's drawing order; the netlist checks it independently.
        centres = reference("micro150-tap25d-fig5a")["raw"]["centers_mm"]
        connections = TapGeometry.load("micro150-45mm").problem.connections
        for cpu in range(4):
            nearest_dram = min(range(4, 8), key=lambda dram: math.dist(centres[cpu], centres[dram]))
            self.assertEqual(connections[cpu][nearest_dram], 1024.0)
        ring = [(a, b) for a in range(4) for b in range(a + 1, 4) if connections[a][b]]
        self.assertEqual(len(ring), 4)
        for a, b in ring:  # ring links join CPUs in one row or one column, never across the diagonal
            self.assertTrue(centres[a][0] == centres[b][0] or centres[a][1] == centres[b][1], (a, b))

    def test_snapped_variants_are_legal_and_every_adjustment_is_recorded_and_needed(self):
        for name in self.NAMES:
            with self.subTest(reference=name):
                check_snapped_reference_is_legal_and_explained(reference(name))

    def test_labels_provenance_and_paper_numbers(self):
        ascend, micro = (reference(name) for name in self.NAMES)
        for ref in (ascend, micro):
            self.assertIn("approximate reconstruction from published figure", ref["labels"])
            self.assertIn("simulated reference, not silicon", ref["labels"])
            self.assertIn("Not CAD, not silicon, not measured.", ref["claim_label"])
            self.assertEqual((ref["fixture"]["frame_mm"], ref["interposer_mm"]), (45.0, 45.0))
            self.assertEqual(ref["decoding"]["precision"]["max_center_offset_from_grid_mm"], 0.0005)
            self.assertEqual((ref["source"]["page_index"], ref["source"]["page_number"]), (5, 6))
            self.assertEqual(len(ref["raw"]["how_obtained"]), len(ref["dies"]))
            for uncertainty in ref["raw"]["center_uncertainty_mm"]:
                self.assertTrue(all(0 < u < 0.005 for u in uncertainty), uncertainty)
            self.assertTrue(all(die["power_w"] > 0 for die in ref["dies"]))
        self.assertTrue(any(label.startswith("SHIPPED product") and "not CAD" in label for label in ascend["labels"]))
        self.assertTrue(any(label.startswith("human-designed RESEARCH layout") and "not a shipped package" in label
                            for label in micro["labels"]))
        self.assertEqual((ascend["track"], micro["track"]), ("MATCH", "BEAT"))
        self.assertEqual(ascend["paper_reported"]["original"],
                         {"panel": "a", "peak_temperature_c": 75.48, "routed_wirelength_mm": 16426, "link_type": "nppl"})
        self.assertEqual(micro["paper_reported"]["original"],
                         {"panel": "a", "peak_temperature_c": 115.94, "routed_wirelength_mm": 67686, "link_type": "nppl"})
        self.assertEqual([(p["panel"], p["peak_temperature_c"], p["routed_wirelength_mm"])
                          for p in ascend["validation_points"]], [("b", 75.13, 23794), ("c", 75.47, 16597)])
        self.assertEqual([(p["panel"], p["peak_temperature_c"], p["routed_wirelength_mm"])
                          for p in micro["validation_points"]],
                         [("b", 113.54, 100864), ("c", 94.89, 216064), ("d", 93.89, 138956)])
        self.assertTrue(any("dummy dies" in note for note in ascend["model_omissions"]))
        self.assertEqual((ascend["source"]["figure"], ascend["source"]["panel"]), ("Fig. 6", "a"))
        self.assertEqual((micro["source"]["figure"], micro["source"]["panel"]), ("Fig. 5", "a"))
        self.assertEqual(ascend["raw"]["wire_proxy_mm"], 18.8238)
        # The micro150 row snap (17/27 rather than 18/28) is decided below the decode precision.
        self.assertTrue(micro["snapped"]["runner_up"]["decided_below_decode_precision"])

    def test_round_trip_record(self):
        for name in self.NAMES:
            with self.subTest(reference=name):
                ref = reference(name)
                wire, temperature = ref["round_trip"]["wire"], ref["round_trip"]["temperature"]
                self.assertEqual(wire["layout"], "raw")
                self.assertEqual(wire["routed_wirelength_mm"], ref["raw"]["routed_wirelength_mm"])
                self.assertEqual(wire["router_sha256"], _sha256(REPO_ROOT / wire["router"]))
                self.assertTrue(wire["within_tolerance"])
                self.assertLessEqual(abs(wire["difference_pct"]), wire["tolerance_pct"])
                self.assertEqual(temperature["tolerance_k"], 1.0)
                self.assertTrue(temperature["status"].startswith("PLANNED, NOT RUN"))
                # The snapped variant is an experiment layout, not a wire-faithful stand-in for the paper's.
                paper = ref["paper_reported"]["original"]["routed_wirelength_mm"]
                self.assertGreater(abs(ref["snapped"]["routed_wirelength_mm"] - paper) / paper, 0.02)

    def test_envelope_plan_is_the_exact_sampled_list(self):
        plan = _json(tap_references.ENVELOPE_PLAN)
        check_envelope_plan_is_the_exact_sampled_list(plan)
        self.assertEqual(plan["expected_call_count"], 45)

    def test_committed_files_equal_a_fresh_build(self):
        for path, data in tap_references.build_all().items():
            with self.subTest(file=path.name):
                self.assertEqual(path.read_bytes(), data)


if __name__ == "__main__":
    unittest.main()
