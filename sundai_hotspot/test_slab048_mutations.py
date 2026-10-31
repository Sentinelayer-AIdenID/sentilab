"""SLAB-048: every new rule has one mutation that makes its check fail.

A check that cannot fail proves nothing. Each mutant below is a realistic bug written at the line it
would live on; the same check that passes on the real code must fail on the mutant. Data mutations
do the same for the committed reference files. No solver runs.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest

from sentilab_core import conductor as real_conductor
from sundai_controller import controller as real_controller
from sundai_controller import experiment as real_experiment
from sundai_controller import test_rotation as rotation
from sundai_hotspot import tap_oracle as real_tap_oracle
from sundai_hotspot import tap_oracle_worker as real_worker
from sundai_hotspot import tap_references
from sundai_hotspot import tap_router as real_tap_router
from sundai_hotspot import test_references as refs
from sundai_hotspot import test_tap_router as router

REAL_MODULES = {"controller": real_controller, "experiment": real_experiment, "tap_oracle": real_tap_oracle,
                "conductor": real_conductor, "worker": real_worker, "tap_router": real_tap_router}

# (rule, module, anchor, replacement, check)
MUTANTS = (
    ("rotate swaps the footprint", "controller",
     "chiplets[index] = Chiplet(chiplet.id, chiplet.height_mm, chiplet.width_mm)",
     "chiplets[index] = chiplet",
     rotation.check_rotate_swaps_footprint),
    ("rotate turns about the die centre", "controller",
     "positions[index] = (center_x - chiplet.height_mm / 2, center_y - chiplet.width_mm / 2)",
     "positions[index] = (x, y)",
     rotation.check_rotate_keeps_centre),
    ("a square die has one orientation", "controller",
     "if chiplet.width_mm == chiplet.height_mm:",
     "if False:",
     rotation.check_square_die_has_one_orientation),
    ("the search's rotate operator proposes a turn", "experiment",
     'found = accept("rotate", {"chiplet": chiplet_id})',
     "found = None",
     rotation.check_rotate_operator_turns_one_die),
    ("the 45 mm fixtures are separate files", "tap_oracle",
     '"ascend910-45mm": TAP_ROOT / "configs" / "sys_ascend910_45mm.cfg",',
     '"ascend910-45mm": TAP_ROOT / "configs" / "sys_ascend910.cfg",',
     refs.check_45mm_fixtures_sit_next_to_unchanged_50mm_ones),
    ("the orientation catalog follows the fixture's rotation rule", "tap_oracle",
     'if rotation == "catalog" or w == h else',
     "if w == h else",
     refs.check_orientation_catalog_is_per_fixture),
    ("legality reads the turned footprint", "tap_oracle",
     "zip(candidate.chiplets, centers, self.problem.bump_halos_mm)):",
     "zip([Chiplet(c.id, w, h) for c, w, h in zip(candidate.chiplets, self.problem.widths_mm, "
     "self.problem.heights_mm)], centers, self.problem.bump_halos_mm)):",
     refs.check_margin_reads_the_turned_footprint),
    ("the raw layout is legal only with its dies turned", "tap_oracle",
     "zip(candidate.chiplets, centers, self.problem.bump_halos_mm)):",
     "zip([Chiplet(c.id, w, h) for c, w, h in zip(candidate.chiplets, self.problem.widths_mm, "
     "self.problem.heights_mm)], centers, self.problem.bump_halos_mm)):",
     refs.check_raw_layout_is_physically_legal_only_as_turned),
    ("microbump halos may not overlap", "tap_oracle",
     "                if not (rect[2] <= other[0] or other[2] <= rect[0] or\n"
     "                        rect[3] <= other[1] or other[3] <= rect[1]):\n"
     "                    depth",
     "                if False:\n"
     "                    depth",
     refs.check_halo_overlap_is_refused),
    ("the 45 mm minimum spacing", "tap_oracle",
     "if min_gap > 0:",
     "if False:",
     refs.check_min_spacing_is_a_45mm_rule),
    ("the centre lattice", "tap_oracle",
     "if step is not None:",
     "if False:",
     refs.check_center_lattice),
    ("centres (and so the wire proxy) come from the turned footprint", "tap_oracle",
     "return tuple((float(x + chiplet.width_mm / 2), float(y + chiplet.height_mm / 2))",
     "return tuple((float(x + chiplet.height_mm / 2), float(y + chiplet.width_mm / 2))",
     refs.check_wire_proxy_reproduces_the_human_ascend_layout),
    ("the fixture frame reaches the worker", "tap_oracle",
     '"tap_parameters": {\n                "interposer_size_mm": self.problem.interposer_size_mm,',
     '"tap_parameters": {\n                "interposer_size_mm": 50.0,',
     refs.check_frame_reaches_the_worker_request),
    ("the worker is told which dies are turned", "tap_oracle",
     '"rotated": list(self.geometry.rotated(candidate)),',
     '"rotated": [False] * len(candidate.chiplets),',
     refs.check_request_carries_rotation),
    ("the worker turns flagged dies before writing the floorplan", "worker",
     "        if turned:\n            system.rotate(index)",
     "        if False:\n            system.rotate(index)",
     refs.check_worker_writes_the_turned_floorplan),
    ("the worker scales the package with the fixture frame", "worker",
     "system.set_interposer_size(size)",
     "system.set_interposer_size(50.0)",
     refs.check_worker_writes_the_45mm_package),
    ("the view draws the turned footprint", "conductor",
     '"w": c.width_mm,\n             "h": c.height_mm,',
     '"w": c.height_mm,\n             "h": c.width_mm,',
     refs.check_view_geometry_uses_the_turned_footprint),
    ("the router turns flagged dies before placing pin clumps", "tap_router",
     "        if turned:\n            system.rotate(index)",
     "        if False:\n            system.rotate(index)",
     router.check_round_trip_wire_on_the_raw_references),
    ("the router's pin clumps sit on the die edges", "tap_router",
     "xc.append((b / 2, w / 2 + b, w + b * 1.5, w / 2 + b))",
     "xc.append((w / 2 + b,) * 4)",
     router.check_round_trip_wire_on_the_raw_references),
)
PACKAGES = {"controller": "sundai_controller", "experiment": "sundai_controller", "tap_oracle": "sundai_hotspot",
            "conductor": "sentilab_core", "worker": "sundai_hotspot", "tap_router": "sundai_hotspot"}


def mutated_source(module, anchor: str, replacement: str) -> str:
    source = Path(module.__file__).read_text(encoding="utf-8")
    count = source.count(anchor)
    if count != 1:
        raise AssertionError(f"anchor found {count} times in {Path(module.__file__).name}; update the mutant:\n{anchor}")
    return source.replace(anchor, replacement)


class MutationTests(unittest.TestCase):
    def bundle(self, target: str | None = None, source: str | None = None):
        modules = dict(REAL_MODULES)
        worker_source = real_tap_oracle.WORKER
        if target == "worker":
            directory = Path(tempfile.mkdtemp(prefix="slab048-mutant-"))
            self.addCleanup(shutil.rmtree, directory, True)
            worker_source = directory / "tap_oracle_worker.py"
            worker_source.write_text(source, encoding="utf-8")
        elif target is not None:
            name = f"slab048_mutant_{target}_{len(sys.modules)}"
            module = types.ModuleType(name)
            module.__file__ = REAL_MODULES[target].__file__
            module.__package__ = PACKAGES[target]
            sys.modules[name] = module  # dataclasses resolve annotations through it
            self.addCleanup(sys.modules.pop, name, None)
            exec(compile(source, f"<mutant {target}>", "exec"), module.__dict__)
            modules[target] = module
        return types.SimpleNamespace(**{k: v for k, v in modules.items() if k != "worker"}, worker_source=worker_source)

    def test_every_check_passes_on_the_real_code(self):
        for rule, _, _, _, check in MUTANTS:
            with self.subTest(rule=rule):
                check(self.bundle())

    def test_every_rule_has_a_mutant_that_fails_its_check(self):
        for rule, target, anchor, replacement, check in MUTANTS:
            with self.subTest(rule=rule):
                mods = self.bundle(target, mutated_source(REAL_MODULES[target], anchor, replacement))
                with self.assertRaises(Exception, msg=f"the check for '{rule}' passed on its mutant"):
                    check(mods)


class DataMutationTests(unittest.TestCase):
    def reference(self, name="ascend910-tap25d-fig6a"):
        return refs.reference(name)

    def test_raw_centre_moved_by_a_tenth_of_a_micron_is_caught(self):
        ref = self.reference()
        ref["raw"]["centers_mm"][0][0] += 0.0001
        with self.assertRaisesRegex(AssertionError, "raw centres differ from the decode"):
            refs.check_raw_reference_is_stored_exactly(ref)

    def test_dropping_any_recorded_adjustment_makes_the_snapped_layout_illegal(self):
        for name in ("ascend910-tap25d-fig6a", "micro150-tap25d-fig5a"):
            for index in range(len(self.reference(name)["snapped"]["adjustments"])):
                with self.subTest(reference=name, adjustment=index):
                    ref = self.reference(name)
                    dropped = ref["snapped"]["adjustments"].pop(index)
                    # Keep the record self-consistent, so only legality can catch it.
                    ref["snapped"]["centers_mm"][dropped["die"]][0] -= dropped["dx_mm"]
                    ref["snapped"]["centers_mm"][dropped["die"]][1] -= dropped["dy_mm"]
                    with self.assertRaisesRegex(ValueError, "overlap|minimum spacing|margin"):
                        refs.check_snapped_reference_is_legal_and_explained(ref)

    def test_an_unrecorded_adjustment_is_caught(self):
        ref = self.reference()
        ref["snapped"]["adjustments"].pop()
        with self.assertRaisesRegex(AssertionError, "recorded adjustments are not the snapped layout"):
            refs.check_snapped_reference_is_legal_and_explained(ref)

    def test_an_excluded_probe_listed_as_a_call_is_caught(self):
        plan = json.loads(tap_references.ENVELOPE_PLAN.read_text(encoding="utf-8"))
        entry = plan["references"][0]
        moved = copy.deepcopy(entry["excluded"][0])
        entry["calls"].append({**moved, "centers_mm": [], "rotated": [], "design_hash": ""})
        with self.assertRaises(AssertionError):
            refs.check_envelope_plan_is_the_exact_sampled_list(plan)


if __name__ == "__main__":
    unittest.main()
