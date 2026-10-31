# SLAB-024a — what runs where

Inspected 2026-10-31 on this x86_64 CPU box. No GPU (`nvidia-smi` not installed). The GB10 was not contacted. Answers below are from retrieved documents plus one CPU MuJoCo smoke. They are not a compatibility test of Isaac Sim on GB10 (that stays SLAB-004).

## Direct answers

| Question | Answer | Evidence |
| --- | --- | --- |
| Is there an open MicroDuck model? | **Yes, two different ones.** Pollen publishes MJCF plus STL. Isaac Lab publishes task code that points at a Nucleus USD which is not in git. | `microduck_rl` `bae39f59`; Isaac Lab `microduck.py` at `a946f38`. |
| What is its license? | **Split.** MJCF/XML, configs, and `.part` metadata: Apache-2.0. STL meshes: CC BY-NC-SA 4.0. Isaac Lab task code: BSD-3-Clause. Nucleus USD: unresolved, and Isaac Lab README assigns unlisted assets to the Isaac Sim license. | `LICENSE-MODELS.md`; Isaac Lab `LICENSE` and README license section. |
| Can a CPU box run it tonight? | **Yes for passive MuJoCo stepping of the Pollen walk model. No for the NVIDIA workflow.** | Smoke below. |
| What does GB10 need for the NVIDIA path? | **Not measured.** Isaac Sim's aarch64 documentation says DGX Spark, DGX OS 7, driver 580.159.03. Whether this GB10 matches that is SLAB-004. | Isaac Sim 6.2.0 requirements page. |

## Three columns

| Work | CPU box tonight | GB10 once reachable | Not feasible by Sun 18:00Z (2026-11-01T18:00:00Z) |
| --- | --- | --- | --- |
| Read the NVIDIA article, video metadata, licenses | Done in this slice. | No device needed. | Re-watching the video if YouTube keeps blocking the player API and no human records frames. |
| Smallest honest robot demo | **Passive physics:** load Pollen `scene_walk.xml` at `bae39f59` and step MuJoCo 1,000 times. No policy, no walking gait, no rendering. Command and timing below. | Same CPU demo, plus a *proposed* next demo only after SLAB-004: `uv run isaaclab list_envs --keyword MicroDuck` if Isaac Sim actually installs. Not run. | Isaac Lab training (`--num_envs 4096`), RTX rendering, or a walking policy. No checkpoint is in the inspected repos. |
| NVIDIA agent workflow (Hermes, Nemotron 3.5 Bolt, Astra, FreeCAD, Blender, USD, Isaac Sim, Newton, Isaac Lab) | Cannot run. No GPU, Astra is unidentified, Isaac Sim was not downloaded. | **Unproven.** Requirements page allows an aarch64 Isaac Sim binary only on DGX Spark. Training in the blog was on an RTX PRO 6000 Blackwell Workstation Edition, not on Spark. | Full obstacle-course reproduction: cloud image editing, Astra, Nucleus USD, 4,096-env training, and local RTX evaluation. Also physical robots. |
| Pollen `microduck_rl` training | README: "Requires a CUDA GPU (training runs through MuJoCo Warp)". Not this box. | README names "ARM boxes (DGX Spark / GB10, Jetson)" only for a `uv sync` timeout, not as a tested train result. | A trained gait by Sunday. README's own scale is "~1-2 h for a usable gait at 4096 envs" on an unspecified GPU, and the STL license is NonCommercial. |
| Pollen `scripts/infer_policy.py` CPU playback | Documented as CPU MuJoCo, but it needs an ONNX policy that is not in the repo. Not run. | Same, if a policy with a known license appears. | Walking playback without a policy file. |
| Isaac Sim render / sensors | No. | Pending SLAB-004. Docs: aarch64 "currently only supported on DGX Spark", OS "NVIDIA DGX OS 7", driver tested "580.159.03". x86_64 drivers tested are Linux 595.58.03, which is a different branch. | Claiming a rendered MicroDuck on GB10 before that preflight. |
| SimReady Central assets | HTTP read of the announcement only. | Same. | Using them in a demo before each asset's license is read. |

## Isaac Sim ARM64 statement (documentation only)

From https://docs.isaacsim.omniverse.nvidia.com/6.2.0/installation/requirements.html (footer: Last updated on Oct 14, 2026), section "Requirements for aarch64":

> Device: NVIDIA DGX™ Spark
> OS: NVIDIA DGX OS 7
> Driver: 580.159.03

> "Isaac Sim aarch64 builds are currently only supported on DGX Spark system."

The same page's x86_64 table lists Ubuntu 22.04/24.04 or Windows 11, GPUs from GeForce RTX 4080 through RTX PRO 6000 Blackwell, and driver Linux 595.58.03 / Windows 595.97. It also says:

> "GPUs without RT Cores (A100, H100) are not supported."

Download page https://docs.isaacsim.omniverse.nvidia.com/6.2.0/installation/download.html lists Isaac Sim 6.2.0 (October 2026) for Linux x86_64, Linux aarch64, and Windows. So an aarch64 binary is published. The requirements page, not the download list, is what restricts which aarch64 machine it supports.

The NVIDIA article's RTX Spark install note is different again: "download the Windows x86 binaries (runnable out of the box via Windows x86 emulation on Arm)". That is Windows x86 emulation, not DGX OS.

**Unresolved for SLAB-004:** whether the unreachable GB10 is the DGX Spark the requirements page names, whether it runs DGX OS 7, and whether driver 580.159.03 is installed. This slice does not claim it is or is not.

## CPU smoke (ran)

Not the NVIDIA workflow. MuJoCo 3.3.5, `MUJOCO_GL=disable`, Pollen files fetched at runtime from commit `bae39f5900b318f7e87fc485c30a31213cfa14eb` (38 STL meshes, not committed).

Command:

```
python3 scripts/slab024a_smoke.py
```

Observed on this box, 2026-10-31, second run of that script:

```
pin bae39f5900b318f7e87fc485c30a31213cfa14eb
scene scene_walk.xml
model nq=21 nv=20 nu=14 nbody=16 nmesh=38 timestep=0.002
steps=1000 elapsed_s=0.044373 steps_per_s=22536.4 sim_time=2.000000 root_z=0.04441 ncon=2
meshes_fetched 38
not_nvidia_workflow true
```

An earlier in-process run of the same scene, before the script existed, was 0.054989 s for 1,000 steps. Timing is machine-local, not a benchmark. `root_z` fell from the keyframe height 0.12 m to about 0.044 m with 2 contacts: the passive model is settling under gravity, not executing a walk. Default MuJoCo actuators in the XML are not BAM.

Importing `import mujoco` on this box failed for both `MUJOCO_GL=egl` and `MUJOCO_GL=osmesa` (`eglQueryString` / `glGetError` missing). The smoke therefore calls `mujoco._structs` and `mujoco._functions` and does not open a renderer.

## Observed reference versus substitutes

| Observed | Substitute this slice did not claim |
| --- | --- |
| Blog: agents plan, build USD, assemble Isaac Sim, train Isaac Lab, evaluate on RTX Spark. | A MuJoCo CPU step is not that pipeline. |
| Blog adaptation: 4,096 envs, head-camera depth plus robot state, RTX PRO 6000 Blackwell Workstation Edition. | One passive MuJoCo instance with no camera and no policy. |
| Isaac Lab docs: flat and rough velocity tasks, 61-D actor observations in the rough-task recipe, 14 position actions. | Not run. |
| Pollen README: CUDA training, ONNX export, CPU `infer_policy.py` if you already have a policy. | No policy was fetched or trained. |
| Video page: third-party description of four stage robots. | No frame match to the blog figures. |
