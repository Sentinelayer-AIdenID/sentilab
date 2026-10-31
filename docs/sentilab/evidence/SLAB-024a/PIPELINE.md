# SLAB-024a — NVIDIA MicroDuck pipeline

Inspected 2026-10-31T05:23Z to 2026-10-31T05:32Z from this CPU box (`uname` Linux x86_64, no `nvidia-smi`). OpenResearch (`orx`) is not installed. Quotes below are from the retrieved page or file, not from the earlier second-hand note in `docs/sentilab/draft-0.5/technology-evidence.md`.

This file does not complete SLAB-024 or SLAB-035. Device, ARM, and rendering behavior on the GB10 stay pending SLAB-004. Nothing here is legal clearance.

## What was inspected

| Source | Retrieved | What this box actually got |
| --- | --- | --- |
| NVIDIA Technical Blog, Gabriele Leone, Seun Doherty, Asier Arranz, Johnny Núñez, Asawaree Bhide | HTTP 200, `datePublished` `2026-10-23T14:58:32+00:00`, `dateModified` `2026-10-23T14:58:36+00:00` | Article HTML. Schema.org body was empty; the visible article was extracted from `entry-content`. |
| YouTube `ac6pspFbPsI` | oEmbed HTTP 200; watch-page HTTP 200 | Title, channel, display date, view count, description text. No caption track and no frames. |
| Public GitHub commits and license files | GitHub API HTTP 200 | SHAs and license text cited in `ASSETS.json`. |
| Isaac Sim 6.2.0 requirements and download pages | HTTP 200, page footer "Last updated on Oct 14, 2026" | OS, GPU, driver, and aarch64 limits. |
| Hugging Face MicroDuck tutorial and SimReady article | HTTP 200 | Training commands and asset-library claims. |
| Pollen "Meet Microduck" | HTTP 200 | Robot description, dated August 27, 2026. |
| NVIDIA GTC Berlin keynote blog | HTTP 200 | Onstage MicroDuck account. |

## Video versus NVIDIA article

The watch page shows title **"Nvidia Microduck AI Robots are mind blowing - World Premiere and First Look"**, channel **"REC Anything"**, `publishDate.simpleText` **"Oct 22, 2026"**, and **"1,865,923 views"**. oEmbed confirms the same title and author. The description on the page says the uploader, not NVIDIA, is speaking:

> "Have a look at the new Nvidia Microduck AI robots. NVIDIA CEO Jensen Huang was joined onstage at GTC Berlin 2026 by four waddling Microduck robots."

The player API (`youtubei/v1/player`) returned `LOGIN_REQUIRED` / "Sign in to confirm you're not a bot". No timed captions and no frames were retrieved. **Frame-level fidelity is unverified.**

NVIDIA's own GTC Berlin post (https://blogs.nvidia.com/blog/gtc-berlin-2026-keynote/) says the keynote was Wednesday, Oct. 21, and:

> "Huang then showed a video of an agent helping train Hugging Face's Microduck: it set up a course and simulated the robot in Isaac Sim, sent training jobs to the cloud, then brought the learned policy back to RTX Spark for evaluation before deploying it to the physical robot."

> "A flock of four Microducks joined Huang onstage, sitting down, standing up and even taking a nap on cue."

That confirms a demonstration existed. It does not prove that the REC Anything upload shows the same frames, UI, or timing as the Technical Blog.

## Authored workflow (NVIDIA Technical Blog)

URL: https://developer.nvidia.com/blog/using-ai-agents-to-teach-robots-like-microduck-to-walk-in-simulation/

The page labels an "AI-Generated Summary" separately ("Powered by NVIDIA Nemotron. AI-generated content may summarize information incompletely."). The steps below are from the authored sections, not that summary.

The authored opening says:

> "NVIDIA RTX Spark serves as a local development hub, supporting AI-assisted planning and policy validation. NVIDIA Isaac Lab provides the robot-learning framework for reinforcement learning in the cloud, while Newton models physical behavior, and NVIDIA Omniverse libraries generate simulated visual observations through RTX rendering. Trained policies return to RTX Spark for local evaluation in NVIDIA Isaac Sim."

> "This post walks through the workflow using Microduck as a reference robot, with Hermes, NVIDIA Nemotron, and Astra assisting with planning and preparation."

### 1. Plan the course

> "On RTX Spark, Hermes and NVIDIA Nemotron 3.5 Bolt translate that prompt into a step-by-step project plan."

Named links: Hermes https://hermes-agent.nousresearch.com/ and Nemotron 3.5 Bolt https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Bolt-74B-A9B-24GB.

The sample prompt's workflow list is:

1. Research and plan — "Review official Microduck documentation" and define layout, dimensions, clearances, and route.
2. Generate the concept — photorealistic course concept from "a verified Microduck reference image".
3. Identify assets — inventory, crops, dimensions, and "reference limitations".
4. Prepare the handoff — plan, robot brief, concept, inventory, crops, and instructions, then "delegate to Astra".
5. Create and verify assets — "Astra enhance references, model geometry in FreeCAD, and apply materials in Blender".
6. Assemble and test — "do not operate physical hardware".

Further authored text: "A local image-generation model produces a concept image". Hermes and Nemotron inventory visible assets. Hermes delegates the package to Astra. The article does not name the local image model or Astra's underlying model. **Astra in the article is not this project's `gpt-astra-carter`.**

### 2. Create simulation assets

> "Before modeling, Astra uses cloud image editing to isolate the objects and produce clearer, higher-resolution images."

> "Astra directs FreeCAD to construct the base geometry and editable CAD structure, then uses Blender to add fine geometric details and materials. Both applications run locally through programmatic execution. The generated assets are saved as editable models and exported USD assets."

> "You can also get assets from SimReady Central Library, a free and ungated library of more than 2,000 simulation-ready OpenUSD assets."

SimReady article (https://huggingface.co/blog/nvidia/simready-central-assets-robotics-ai-factories, "Community Article Published October 21, 2026"):

> "SimReady Central brings together more than 2,000 simulation-ready (SimReady) OpenUSD assets on Hugging Face, giving developers a free, ungated starting point."

The blog does not say those assets include MicroDuck geometry.

### 3. Assemble the environment

> "Astra composes the obstacle course using the prepared assets in Isaac Sim. Isaac Sim provides access to Omniverse libraries' rendering and sensor-simulation capabilities, while Newton models Microduck's physical behavior, including movement and balance."

> "A robot's articulated structure and movement are defined in simulation through links, joints, and actuators."

### 4. Train perception and locomotion

> "NVIDIA Isaac Lab provides the tools to train and evaluate robot policies at scale."

> "Newton, an open-source, GPU-accelerated physics engine, simulates how Microduck moves and interacts with the ground."

> "The ramp and obstacle training experiment uses Astra-generated assets from the previous sections and the Isaac Lab Microduck example environment as its starting point. A locomotion policy pretrained in that environment receives additional training in Isaac Lab for traversing ramps and obstacles, using head-camera depth and robot-state observations. This adaptation run used 4,096 parallel environments on an NVIDIA RTX PRO 6000 Blackwell Workstation Edition GPU."

Linked example: https://github.com/isaac-sim/IsaacLab/tree/develop/source/isaaclab_tasks/isaaclab_tasks/contrib/microduck

On 2026-10-31 the `develop` and `main` tips were the same commit `a946f38b8899816ce95492dc608c3c5714ee6aec` (2026-10-31T05:07:13Z). That tree contains task Python only (`flat_env_cfg.py`, `rough_env_cfg.py`, MDP modules, RSL-RL configs). It does not contain USD, URDF, STL, or a policy checkpoint.

`source/isaaclab_assets/isaaclab_assets/robots/microduck.py` at that commit loads:

> `usd_path=f"{ISAACLAB_NUCLEUS_DIR}/Robots/PollenRobotics/MicroDuck/microduck_walk.usd"`

and says the actuator constants are an "XL330 m6 fit from Rhoban BAM revision `62bd8ce12154340be97e06f7f41a0ca8f116d967`". The USD is a Nucleus asset, not a file in the git tree. Its license is not in `docs/licenses/assets/` (no Pollen or MicroDuck file there). Isaac Lab's README says assets not listed there "fall under the terms of the Isaac Sim License."

`docs/source/how-to/train_microduck.rst` at the same commit registers `IsaacContrib-Velocity-Flat-MicroDuck` and `IsaacContrib-Velocity-Rough-MicroDuck` and shows:

```
uv run isaaclab train --task IsaacContrib-Velocity-Rough-MicroDuck \
    --rl_library rsl_rl presets=backlash
```

It also says "With 4,096 environments per GPU" for the distributed recipe. That is the example's own training scale. The blog's 4,096 figure is the ramp-adaptation run on an RTX PRO 6000 Blackwell Workstation Edition, which is a different machine from RTX Spark.

### 5. Validate on RTX Spark

> "After training, validate the trained policy in Isaac Sim on a local RTX Spark."

> "This stage separates policy learning from policy evaluation. During training, the policy changes as it receives new experience. During evaluation, you examine the behavior of a selected policy."

> "Record course completion, falls, collisions, and the situations in which progress stops."

### 6. Prepare sim-to-real, without deploying in the article

> "Once the policy performs reliably in simulation, the next step is to run it on the robot's onboard computer. [...] Detailed hardware deployment is outside the scope."

> "Isaac Lab supports Better Actuator Models (BAM) to model servo response, including command delays, mechanical backlash [...], and drops in voltage as motors draw power from a shared battery."

> "Isaac Lab's domain randomization varies physical parameters and observation noise within realistic ranges."

The article says Figure 10 "shows a locomotion policy trained in Isaac Lab running on the physical Microduck." This box did not retrieve the image pixels.

Get-started links on the article include "Installing Isaac Sim on RTX Spark—download the Windows x86 binaries (runnable out of the box via Windows x86 emulation on Arm)". That sentence is about Windows-on-Arm emulation, not a claim that Linux aarch64 Isaac Sim is limited to Windows.

## Separate tutorial (not the same as the blog's agent workflow)

https://huggingface.co/blog/nvidia/microduck-isaac-lab-sim-to-real — "Community Article Published October 21, 2026". Authors include NVIDIA and Pollen/Hugging Face collaborators.

> "For the simulation and training portion, you'll need: A Linux workstation with a supported NVIDIA GPU and driver."

Commands it prints:

```
uv run isaaclab train \
  --rl_library rsl_rl \
  --task IsaacContrib-Velocity-Rough-MicroDuck \
  --num_envs 4096 \
  presets=backlash
```

> "The policy takes 61 observation values and outputs 14 joint-positions."

> "Isaac Lab's RSL-RL playback workflow automatically exports both TorchScript (policy.pt) and ONNX (policy.onnx)."

That tutorial is a GPU Isaac Lab training recipe. It does not describe Hermes, Nemotron, FreeCAD, Blender, or Astra asset generation.

## What is open, what is proprietary, what was not shown

| Piece | Status from sources |
| --- | --- |
| Hermes agent repo `NousResearch/hermes-agent` | Open, MIT, commit `78077b2b8f83ac7d9293d3269df7ef20e3a9a994`. The blog does not pin a commit. |
| Nemotron 3.5 Bolt weights | Published weights, license name `openmdw-1.1`, revision `cf2effc5c4b794ee9fb8d34eab3d1d65ce64142f`. Not Apache. |
| Astra | Named assistant only. No repo, model id, or license in the article. |
| Local image model and cloud image editor | Named only as functions. No product or license. |
| FreeCAD, Blender | External applications. Versions and licenses not stated in the article. |
| Isaac Lab task code | BSD-3-Clause at `a946f38`. `isaaclab_mimic` is separately Apache-2.0. |
| MicroDuck USD on Nucleus | Referenced, not in git. License unresolved (see ASSETS.json). |
| Isaac Sim application, Omniverse, RTX rendering | Isaac Sim git tree is Apache-2.0 plus a separate additional-materials license for Kit, models, and textures. |
| Newton | Apache-2.0, `newton-physics/newton` `2e20d82d706970a9bb6917eef7f63e0831cb0347`. |
| Pollen MJCF | Apache-2.0. Pollen STL meshes | CC BY-NC-SA 4.0. Different files, same repo. |
| SimReady Central assets | "Free and ungated" in the blog. Per-asset licenses were not enumerated. |
| REC Anything video | Third-party copyright. Not a license to copy footage. |
| Pretrained Isaac Lab locomotion policy the blog starts from | Not in the Isaac Lab tree inspected. Location and license unresolved. |

## Robot identity

Pollen, https://pollen-robotics.com/microduck/blog/introducing-microduck/, August 27, 2026:

> "Microduck is a 25 cm tall biped robot with 15 motors, a camera, a small depth sensor, two IMUs, and an articulated beak that can pick up objects. [...] It weighs less than 800 g."

Isaac Lab's `microduck.py` models **14 servos** and says "the mouth servo is not modeled." The blog's walking policy is that simulated robot, not a claim that all 15 hardware motors are in the Isaac Lab articulation.
