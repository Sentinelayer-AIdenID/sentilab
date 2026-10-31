# SLAB-024a — one workflow, two jobs

Carter, 2026-10-31, recorded in `docs/sentilab/draft-0.5/OWNER-DECISIONS-2026-10-31.md`: both (1) an actual MicroDuck robotics simulation and (2) the NVIDIA workflow applied to the chiplet interface. This mapping only shows the shared stages. It does not make robot physics and thermal physics the same model, and it does not authorize either implementation.

## Shared stages

| Stage | NVIDIA MicroDuck, as the article states | Chiplet interface, same stage, different physics |
| --- | --- | --- |
| Intent | Hermes and Nemotron 3.5 Bolt turn a prompt into a plan, robot brief, dimensions, clearances, concept, asset inventory, crops, and unknowns. | A lab turns a placement request into a plan: board id, chiplet count, power, keep-outs, and what is still unknown. The plan is text, not a gait. |
| Geometry | Astra drives FreeCAD for editable CAD and Blender for materials, then exports USD. SimReady assets may be added. | The geometry already exists: TAP configs and the HotSpot floorplan. An agent may explain or edit coordinates. It must not replace them with a decorative model. |
| Simulation | Isaac Sim assembles the scene. Omniverse RTX renders sensors. Newton integrates articulated contact. | HotSpot 7 plus SuperLU scores temperature. There is no contact solver and no RGB camera in that score. |
| Evaluation | A frozen policy returns to RTX Spark. Record completion, falls, collisions, stalls, and videos. Training and evaluation are separate. | AcceptanceGate freezes a layout and records temperature, events, and replay. A lab must not edit the score after the fact. |

## What must stay distinct

- MicroDuck success is locomotion under Newton or, in the Pollen stack, MuJoCo. Chiplet success is a thermal objective. A shared screen that shows both does not convert one number into the other.
- The blog's "Astra" is an unnamed asset assistant. It is not `gpt-astra-carter`.
- Robot meshes, USD, and policies have their own licenses (`ASSETS.json`). Chiplet TAP/HotSpot files keep the licenses already in `sundai_hotspot/LICENSE`, `sundai_tap/LICENSE`, and `THIRD_PARTY_NOTICES.md`.
- The CPU MuJoCo smoke is a robot-lane fact only. It is not a thermal regression and not an Isaac render.

## Smallest honest demo of each choice

1. Robot, tonight, CPU: `python3 scripts/slab024a_smoke.py`. Passive 1,000-step MuJoCo load. Not a walk.
2. Robot, NVIDIA fidelity: only after SLAB-004 shows the GB10 can run the documented Isaac Sim aarch64 stack, and after the Nucleus USD license is resolved. Not this PR.
3. Chiplet: the existing HotSpot referee and live/replay UI. Applying the *workflow* means intent, geometry, simulation, and evaluation stay inspectable. It does not mean placing duck actors on the board.
