"""The shipped smoke script must keep its pinned MicroDuck CPU contract.

This drives scripts/slab024a_smoke.py as source: the pin, step count, and
MuJoCo entry points a later change could silently drop. It does not reimplement
physics and does not fetch meshes.
"""

from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SMOKE = ROOT / "scripts" / "slab024a_smoke.py"


class Slab024aSmokeContractTest(unittest.TestCase):
    def test_shipped_script_keeps_cpu_microduck_contract(self) -> None:
        source = SMOKE.read_text(encoding="utf-8")
        self.assertIn("bae39f5900b318f7e87fc485c30a31213cfa14eb", source)
        self.assertIn("scene_walk.xml", source)
        self.assertIn("robot_walk.xml", source)
        self.assertEqual(source.count("STEPS = 1000"), 1)
        self.assertIn("mujoco._structs", source)
        self.assertIn("mujoco._functions", source)
        self.assertIn("mj_step", source)
        self.assertIn("not_nvidia_workflow true", source)
        self.assertNotIn("isaacsim", source.lower())


if __name__ == "__main__":
    unittest.main()
