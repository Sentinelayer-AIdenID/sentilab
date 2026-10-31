# SLAB-024a follow-ups — commands later implementation must ship

Docs do not ship these. Names are the contract for SLAB-026 and the rest of SLAB-024 / SLAB-035. None of these CLIs exist in sentilab today.

## `sentilab reference inspect`

- Input: a reference id (`nvidia-microduck-blog`, `youtube:ac6pspFbPsI`).
- Output: retrieved URL, timestamp, content hash, quoted lines, and whether frames or captions were actually fetched.
- Must refuse a fidelity claim when the video has no frames, as in this slice.

## `sentilab simulation doctor`

- Report host arch, GPU, driver, OS, and whether Isaac Sim's published aarch64 limits (DGX Spark, DGX OS 7, driver 580.159.03) match this machine.
- Separate probes: `mujoco` CPU import, Newton import, Isaac Lab `list_envs --keyword MicroDuck`.
- Must print `not_nvidia_workflow` when only MuJoCo CPU is available.
- GB10 result stays empty until SLAB-004.

## `sentilab provenance inspect`

- For a robot asset: repo, commit, path, blob sha256, and which license file covers that path.
- Must show the Nucleus USD as unresolved when only `ISAACLAB_NUCLEUS_DIR` is known.
- Must not let a repo-level Apache badge cover `*.stl`.

## `sentilab license manifest`

- One row per code, model, dataset, STL, texture, USD, and policy used at runtime.
- Fields: SPDX or "unresolved", redistribution condition, training condition, commercial-use condition, source URL, pin.
- A public-demo flag may not be "yes" while any row is NonCommercial or unresolved.
- This slice is not that manifest and is not legal clearance.

## Already true, do not re-decide here

- This docs slice does not complete SLAB-024 or SLAB-035.
- Device, ARM, and rendering claims stay pending SLAB-004.
- Do not vendor CC BY-NC-SA meshes into the git tree.
