#!/usr/bin/env python3
"""CPU physics smoke for the openly licensed MicroDuck MJCF.

Fetches Pollen Robotics microduck_rl scene_walk.xml, robot_walk.xml, their
includes, and the STL meshes those files name, at a pinned commit. Steps
MuJoCo 1,000 times with no rendering and no training.

The STL meshes are CC BY-NC-SA 4.0 (LICENSE-MODELS.md). The MJCF is
Apache-2.0. This script does not vendor either. It is not the NVIDIA
Isaac Sim / Isaac Lab / Newton workflow.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

PIN = "bae39f5900b318f7e87fc485c30a31213cfa14eb"
RAW = (
    "https://raw.githubusercontent.com/pollen-robotics/microduck_rl/"
    + PIN
    + "/src/mjlab_microduck/robot/microduck/"
)
ROOT_XML = "scene_walk.xml"
INCLUDE_SEED = ("robot_walk.xml", "joints_properties.xml", "sensors.xml", "additional.xml")
STEPS = 1000
USER_AGENT = "sentilab-slab024a-smoke"


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def write_xmls(root: Path) -> None:
    pending = [ROOT_XML, *INCLUDE_SEED]
    seen: set[str] = set()
    while pending:
        name = pending.pop(0)
        if name in seen or name.endswith(".stl"):
            continue
        seen.add(name)
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(fetch(RAW + name))
        text = target.read_text(encoding="utf-8")
        pending.extend(re.findall(r'<include file="([^"]+)"', text))


def write_meshes(root: Path) -> int:
    text = (root / "robot_walk.xml").read_text(encoding="utf-8")
    meshes = sorted(set(re.findall(r'file="([^"]+\.stl)"', text)))
    if not meshes:
        raise SystemExit("robot_walk.xml names no STL meshes")
    asset_dir = root / "assets"
    asset_dir.mkdir(exist_ok=True)
    total = 0
    for mesh in meshes:
        payload = fetch(RAW + "assets/" + mesh)
        (asset_dir / mesh).write_bytes(payload)
        total += len(payload)
    return len(meshes)


def step(scene: Path, steps: int) -> dict:
    os.environ.setdefault("MUJOCO_GL", "disable")
    import mujoco._functions as functions
    import mujoco._structs as structs

    model = structs.MjModel.from_xml_path(str(scene))
    data = structs.MjData(model)
    key = model.nkey - 1 if model.nkey else None
    if key is not None:
        functions.mj_resetDataKeyframe(model, data, key)
    functions.mj_forward(model, data)
    started = time.perf_counter()
    for _ in range(steps):
        functions.mj_step(model, data)
    elapsed = time.perf_counter() - started
    return {
        "nq": int(model.nq),
        "nv": int(model.nv),
        "nu": int(model.nu),
        "nbody": int(model.nbody),
        "nmesh": int(model.nmesh),
        "timestep": float(model.opt.timestep),
        "keyframe": key,
        "steps": steps,
        "elapsed_s": elapsed,
        "sim_time": float(data.time),
        "root_z": float(data.qpos[2]),
        "ncon": int(data.ncon),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=STEPS)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="slab024a-") as temporary:
        root = Path(temporary)
        write_xmls(root)
        mesh_count = write_meshes(root)
        result = step(root / ROOT_XML, args.steps)
    result["meshes_fetched"] = mesh_count
    print(f"pin {PIN}")
    print(f"scene {ROOT_XML}")
    print(
        "model nq={nq} nv={nv} nu={nu} nbody={nbody} nmesh={nmesh} "
        "timestep={timestep}".format(**result)
    )
    print(
        "steps={steps} elapsed_s={elapsed_s:.6f} steps_per_s={rate:.1f} "
        "sim_time={sim_time:.6f} root_z={root_z:.5f} ncon={ncon}".format(
            rate=result["steps"] / result["elapsed_s"], **result
        )
    )
    print(f"meshes_fetched {mesh_count}")
    print("not_nvidia_workflow true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
