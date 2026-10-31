# SentiLab technology evidence — Microduck and OpenResearch

Research date: October 30, 2026 (America/New_York). Read-only source inspection; no project installation, simulation, model deployment, GPU job, or hardware operation was performed. Findings below describe retrieved documentation, not a successful local compatibility test. Implementation and any reduction of the requested reference fidelity remain subject to the user's explicit `+1` gate.

## 1. The exact video and what was actually inspected

The supplied [YouTube reference](https://www.youtube.com/watch?v=ac6pspFbPsI) resolves to **“Nvidia Microduck AI Robots are mind blowing - World Premiere and First Look,” REC Anything**, published October 22, 2026, duration 509 seconds (8:29). YouTube oEmbed and page metadata were retrieved. An English auto-caption track was advertised, but its timed-text response was empty. **The video was not watched and no transcript was obtained.** Frame-specific appearance, camera motion, timing, choreography, and exact on-screen interface fidelity remain unverified.

The uploader is not NVIDIA. However, [NVIDIA's GTC Berlin keynote account](https://blogs.nvidia.com/blog/gtc-berlin-2026-keynote/) independently confirms the October 21 demonstration: an agent created a course in Isaac Sim, training went to the cloud, the learned policy returned to RTX Spark for evaluation, and four physical Microducks appeared onstage. This is **Pollen Robotics/Hugging Face Microduck**, not Disney's BDX robot. [Pollen's introduction](https://pollen-robotics.com/microduck/blog/introducing-microduck/) identifies a roughly 25 cm, under-800 g biped with 15 motors, camera, depth sensor, two IMUs, and an articulated beak.

## 2. The reference workflow is documented by NVIDIA

The primary implementation reference is [Using AI Agents to Teach Robots Like Microduck to Walk in Simulation](https://developer.nvidia.com/blog/using-ai-agents-to-teach-robots-like-microduck-to-walk-in-simulation/), NVIDIA Technical Blog, October 23, 2026. Its authored article body, beyond its separately labeled AI summary, describes:

1. **Intent and planning:** Hermes and Nemotron 3.5 Bolt on RTX Spark turn the request into a plan, robot capability brief, dimensions/clearances, concept image, asset inventory, cropped references, and explicit unknowns.
2. **Asset generation:** an assistant called **Astra** enhances references with cloud image editing, directs **FreeCAD** to create editable geometry, and directs **Blender** to add detail/materials. It exports editable models, preview checks, and **USD** assets. SimReady Central assets can supplement generated objects.
3. **Environment and physics:** **Isaac Sim** assembles the course; **Omniverse** supplies rendering and sensor simulation; **Newton** models articulated motion, balance, and contact. Robot links, joints, actuators, collisions, and sensor geometry must be modeled rather than replaced with decorative animation.
4. **Robot policy learning:** **Isaac Lab** trains perception and locomotion using head-camera depth plus robot-state observations. The documented adaptation used **4,096 parallel environments on an RTX PRO 6000 Blackwell Workstation Edition GPU**, starting from the Isaac Lab Microduck example's pretrained locomotion policy.
5. **Evaluation:** the selected policy returns to **RTX Spark** and Isaac Sim. Record course completion, falls, collisions, stalled progress, and rollout videos. Evaluation holds the policy fixed; it is distinct from training.
6. **Sim-to-real preparation:** Better Actuator Models (**BAM**) model servo delay, backlash, and shared-battery voltage effects; domain randomization covers measured uncertainty. Physical deployment procedures are outside the article's scope, even though it includes a physical walking demonstration.

The article links the [Isaac Lab Microduck environment](https://github.com/isaac-sim/IsaacLab/tree/develop/source/isaaclab_tasks/isaaclab_tasks/contrib/microduck), [Isaac Lab v3.0.0-EA documentation](https://isaac-sim.github.io/IsaacLab/v3.0.0-EA/index.html), [NVIDIA's Microduck sim-to-real tutorial](https://huggingface.co/blog/nvidia/microduck-isaac-lab-sim-to-real), and [Microduck demo](https://isaac-sim.github.io/IsaacLab/demos/v3/?demo=microduck). These need revision/image/checkpoint pins before execution.

**Identity distinction:** the article describes “Astra” as the assistant orchestrating asset generation. It does not identify that assistant's underlying model or establish equivalence to this project's `gpt-astra-carter` identity or Astra scientific lab. Naming overlap is not evidence of matching software, model capability, or affiliation.

**Scope consequence:** matching this workflow requires an asset, physics, policy, and evaluation workstream. A chiplet board with four animated duck icons would not satisfy the requested exact simulation pipeline. Conversely, robot locomotion reward or success must not be reported as thermal-optimization evidence. Keep both domains' observations, models, datasets, acceptance tests, and compute accounting explicit. The user has not approved dropping or reducing the Microduck requirement.

## 3. GB10 is viable to investigate, but RTX Spark is a different reference machine

The reference's **RTX Spark is a Windows laptop platform**. NVIDIA's [local-AI product account](https://blogs.nvidia.com/blog/local-ai-gtc-rtx-dgx-spark-station-sync/) distinguishes RTX Spark laptops from DGX Spark developer systems. The user's **Dell Pro Max GB10** is therefore not proved compatible merely because the video says “Spark.”

[Isaac Sim's retrieved requirements](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/requirements.html) state:

- Aarch64 builds are currently supported **only on DGX Spark**, with **DGX OS 7** and tested driver **580.159.03** in that table. Confirm whether the Dell OEM GB10 configuration is included, and run the compatibility checker against the actual machine before promising support.
- Linux is required for the Isaac Sim container. The x86 desktop table lists Ubuntu 22.04/24.04 or Windows 11 and RTX-class hardware; large sensor workloads need more memory.
- **A100 and H100, which lack RT cores, are explicitly unsupported for Isaac Sim rendering.** An H100 LLM-training allocation cannot be assumed to host the faithful rendered demo.
- The page's DGX Spark limitations list cuRobo/cuMotion as unsupported. Version-specific compatibility must be frozen: the article links Isaac Sim **6.2.0** downloads while the rolling requirements page also contains **6.0** limitations. Do not casually mix these releases.

The [Newton README](https://github.com/newton-physics/newton) separately lists Linux x86-64/aarch64 and CPU or compatible NVIDIA GPU execution, with renderer options including OpenGL, USD, RTX, Rerun, Viser, and null. Newton ARM support alone does not prove the full Isaac Sim + sensor + Lab stack is compatible.

**Required preflight evidence:** actual SKU/OS/driver/GPU architecture and memory; pinned compatible Isaac Sim/Lab/Newton/container/asset revisions; one exact Microduck scene import; one sensor frame; valid joint/actuator ordering; reset; fixed-policy rollout with physical metrics; local render/stream FPS and latency; and resource measurements while the GB10 ML service is present. Plan separate training/inference/rendering schedules or demonstrate resource isolation. Record any cloud training or remote rendering honestly.

## 4. A second, genuine Microduck stack exists — it is not an automatic substitute

Pollen's current canonical sources provide another implementation:

- [Microduck runtime](https://github.com/pollen-robotics/microduck/tree/b2b0d213a402caeac492dd662ea891faa17f67c0), pinned at `b2b0d213a402caeac492dd662ea891faa17f67c0`.
- [Microduck RL](https://github.com/pollen-robotics/microduck_rl/tree/bae39f5900b318f7e87fc485c30a31213cfa14eb), default `develop`, pinned at `bae39f5900b318f7e87fc485c30a31213cfa14eb`.

The latter documents **mjlab / MuJoCo Warp + PPO**, BAM actuator modeling, domain randomization, 50 Hz policy execution, and ONNX export. Its README explicitly mentions **DGX Spark/GB10 ARM**. At the inspected revision, `pyproject.toml` pins Python 3.12, `mjlab==1.3.0`, `warp-lang==1.12.0`, and `torch==2.9.1`; Linux aarch64 torch is routed to the **cu129** index because the PyPI ARM wheel is CPU-only. Its first-download timeout recommendation is `UV_HTTP_TIMEOUT=600`. These are source claims, not a local installation success.

The runtime's [simulation documentation](https://github.com/pollen-robotics/microduck/blob/b2b0d213a402caeac492dd662ea891faa17f67c0/docs/robot/simulation.md) describes real robot daemons driving simulated MuJoCo bodies, including `scripts/duck-sim boot 4` for four separate systemd containers in one scene, head-camera rendering, `robotctl` control, and health gates. It explicitly distinguishes physics simulation from `--fake`. Its wall-clock loops require real-time speed; insufficient speed can cause balance failures and unhealthy status, not merely slow playback. Drivers, radios, the physical camera ISP, and NPU are not simulated.

This is a potentially useful reference and fallback **only after an explicit scope decision**; it must not silently replace the requested NVIDIA Isaac/Omniverse/Newton workflow.

## 5. Asset and software licenses are different

Pollen runtime and RL code are **Apache-2.0**. But [Microduck RL's LICENSE-MODELS.md](https://github.com/pollen-robotics/microduck_rl/blob/bae39f5900b318f7e87fc485c30a31213cfa14eb/LICENSE-MODELS.md) explicitly licenses the robot and actuator-test-bench **STL meshes under CC BY-NC-SA 4.0**. It requires Pollen attribution, license link, modification disclosure, and ShareAlike for adapted meshes. NonCommercial is a material constraint for a commercial product or redistribution; obtain appropriate rights/clarification before that use. Converting STL to USD or reducing polygons does not erase these conditions. The same file says the MJCF/XML descriptions and listed configuration/part metadata are Apache-2.0.

Do not infer that a separate NVIDIA asset path automatically relicenses underlying geometry. Inventory each actual imported mesh, texture, CAD/USD asset, policy checkpoint, sample environment, and third-party library; retain its license and provenance. Inspect Isaac Sim's own additional-material/redistribution terms. The linked video's footage, logos, and creator presentation are separate copyrighted material, not covered by robot-code licenses. Reproduce an authorized workflow and clearly attribute sources; do not claim NVIDIA/Pollen endorsement.

## 6. OpenResearch's precise role

Inspected alphaXiv/OpenResearch at `a92fd471aba91e9bdd14a88e2322ec42f9dfdbdb` (October 31 00:56 UTC / October 30 Eastern): [README](https://github.com/alphaXiv/OpenResearch/blob/a92fd471aba91e9bdd14a88e2322ec42f9dfdbdb/README.md), [MIT license](https://github.com/alphaXiv/OpenResearch/blob/a92fd471aba91e9bdd14a88e2322ec42f9dfdbdb/LICENSE).

OpenResearch is a **local-first research harness/workspace**, implemented around the `orx` CLI, dashboard/API, SQLite experiment store, coding-agent integrations, and execution backends. It is **not a foundation model or a demonstrated high-precision intent classifier**. It integrates Claude Code, Codex, OpenCode, Cursor, and Google Antigravity. It supports literature work with alphaXiv/bioRxiv/PubMed and experiment execution locally or through SSH, Slurm, Kubernetes, Modal, Tinker, Ray, Hugging Face Jobs, and managed OpenResearch compute.

Jev can remain the separately evaluated intent/decision component. OpenResearch can organize the named research agent's literature and experiments. ENGRAM can own governed evidence/dependencies and cross-agent recall. Define the synchronization contract between OpenResearch experiment IDs/artifacts and ENGRAM/Senti receipts; avoid claiming that their independent local stores automatically provide consistent memory, revocation, or authorization.

### Host and model requirements

- [Linux](https://github.com/alphaXiv/OpenResearch/blob/a92fd471aba91e9bdd14a88e2322ec42f9dfdbdb/docs/linux.md): x86_64 and aarch64 AppImages; glibc >=2.35 and FUSE/fusermount, or the documented extract-and-run mode. CLI archives are static musl binaries without a GUI. Linux media previews additionally depend on GStreamer. ARM release availability is promising for GB10, but its installed environment has not been verified.
- [Windows beta](https://github.com/alphaXiv/OpenResearch/blob/a92fd471aba91e9bdd14a88e2322ec42f9dfdbdb/docs/windows.md): requires **Git for Windows**, including its Bash/coreutils, plus a supported coding agent. `orx up --remote-host` is **refused on Windows** because that control mode uses Unix sockets. Normal SSH experiment jobs are a different feature; Windows OpenSSH lacks connection multiplexing. Do not design the GB10 control plane around an unsupported Windows remote-host mode.
- [Local models](https://github.com/alphaXiv/OpenResearch/blob/a92fd471aba91e9bdd14a88e2322ec42f9dfdbdb/docs/local-models.md): OpenCode runs the agent loop; LM Studio, oMLX, Ollama, or a custom OpenAI-compatible endpoint serves the model. Custom endpoints need `/v1/models` and tool-capable chat completions. The endpoint must be **loopback relative to the OpenResearch host**. For inference on another machine, use the documented SSH forwarding pattern, or run the harness on that remote host. Keep authentication and server exposure explicit.
- The documented local connection does not silently fall back to a cloud model when unavailable. Existing provider restrictions are preserved. A chat retains its harness; switching requires a new chat. Record actual provider, returned model identity, revision, prompts, tools, and settings rather than counting two harnesses of the same model as independent judges.
- Official builds describe opt-out coarse analytics and sanitized agent feedback; local execution does not by itself imply offline operation. Capture the chosen setting and ensure evidence exports contain no secrets.

### CLI exists; general MCP parity still needs an adapter

The source defines native commands including `orx create-experiment`, `orx exp run/status/cancel/wait`, `orx runs/logs/metrics`, project/compute operations, and `orx agent spawn` (verify precise release help before use). See [command definitions](https://github.com/alphaXiv/OpenResearch/blob/a92fd471aba91e9bdd14a88e2322ec42f9dfdbdb/src/main.rs).

An MCP implementation does exist, but [the inspected `mcp-gate`](https://github.com/alphaXiv/OpenResearch/blob/a92fd471aba91e9bdd14a88e2322ec42f9dfdbdb/src/commands/mcp_gate.rs) is a **hidden internal Claude permission bridge**, exposing an `approve` tool over stdio and failing closed. It is **not evidence of a public experiment-management/research MCP API**. The user's “everything MCP and CLI” requirement therefore still needs a versioned SentiLab adapter around approved research/experiment operations, with the same typed schemas, authorization, budgets, receipts, errors, idempotency, and cancellation semantics on both transports. Do not advertise parity merely because an internal MCP server exists.

## 7. Concrete gates added to the plan

1. **Reference fidelity:** agree on the exact asset/physics/sensor/policy/evaluation features and frame-level visual acceptance against the supplied video; preserve the full requirement until explicit approval changes it.
2. **Legal artifact inventory:** resolve actual asset and checkpoint rights, attribution, and permitted distribution before importing them into a shipped interface.
3. **GB10 compatibility:** prove the exact OEM runtime and selected versions work; distinguish training support, rendering support, and local inference support.
4. **OpenResearch boundary:** select its host/harness, pin a release, define Senti/ENGRAM binding, and prove one authorized experiment has a complete CLI and MCP receipt.
5. **Benchmark isolation:** separate OpenResearch stores/workspaces and ENGRAM memory snapshots across arms; shared local experiment history must not leak held-out or isolated-arm findings.
6. **No capability substitution by name:** do not conflate RTX Spark with DGX Spark, NVIDIA's Astra asset assistant with this lead identity, OpenResearch with Jev, MuJoCo policy learning with NeMo LLM fine-tuning, or robot behavior with thermal-design validity.

These are planning findings and proposed acceptance gates; no implementation `+1` is implied.

## 8. Additional check: the exact NeMo training route for GB10

The [official NeMo Spark playbook overview](https://build.nvidia.com/playbooks/nemo-fine-tune/overview) explicitly lists DGX Spark with 64 GB or 128 GB unified memory. Its [instructions](https://build.nvidia.com/playbooks/nemo-fine-tune/instructions) currently prescribe a **different environment from the attachment's general 26.10 plan**:

- Runtime image: **`nvcr.io/nvidia/nemo-automodel:26.08`**.
- Source checkout: **`NVIDIA-NeMo/Automodel` at `3b5663a6fdf0fee03abbe82e431ca3a7ba6dd8e2`**, mounted over the image's original source, because the Spark-specific recipes/memory fixes landed after the image build.
- Documented validation container cap: **64 GB** shared host/GPU memory; retain the recipe's batch size, packed length, attention backend, activation checkpointing, and loading behavior until independently validated.
- Documented small preflight: one GPU and 20 steps using a provided Spark LoRA recipe. The examples include **Qwen/Qwen3-8B**, Llama-3.1-8B LoRA, and Llama-3.3-70B QLoRA.

The [pinned Qwen3-8B recipe](https://github.com/NVIDIA-NeMo/Automodel/blob/3b5663a6fdf0fee03abbe82e431ca3a7ba6dd8e2/examples/llm_finetune/qwen/qwen3_8b_squad_rtx_spark.yaml) was retrieved directly. Despite its `rtx_spark` filename, its CI metadata says **`cluster_tag: gb10`**. It selects the Hugging Face model path, `force_hf: true`, FlashAttention-2, `disable_mmap: true`, LoRA rank 8 / alpha 32, FSDP2, activation checkpointing, and **packed length 128**. Comments explain an SM12x cuDNN/packed-attention limitation. This is strong documentation for a bounded **GB10 training preflight**, not proof that the user's machine has already run it, nor a reason to change the requested worker silently.

The attachment's [AutoModel v0.7 installation reference](https://docs.nvidia.com/nemo/automodel/v0.7/get-started/installation.md) really does document **`nvcr.io/nvidia/nemo-automodel:26.10.00`**. The [Qwen3-4B-Base coverage page](https://docs.nvidia.com/nemo/automodel/v0.7/model-coverage/large-language-models/qwen/Qwen3-4B-Base.md) lists checked-in text-generation recipes for **`Qwen/Qwen3-4B-Base`**, with hardware unspecified. That is not the same identifier as the attachment's **`Qwen/Qwen3-4B`** chat model and is not a GB10-specific validation claim. The documented Qwen3-0.6B quickstart also defaults to two GPUs; a single-GB10 plan must explicitly select and validate its topology.

**Recommended decision gate:** retain the requested Qwen3-4B identity as the desired worker; choose one complete, pinned GB10 environment and prove that exact model/tokenizer/chat template, dataset format, required context length, and attention path. If a documented Qwen3-8B or smaller recipe is proposed to reduce integration risk, obtain explicit `+1` before substituting it and freeze the same model across all comparison arms. Do not combine the 26.08 source overlay and 26.10 runtime by assumption.

The ML preflight must go beyond the playbook's checkpoint-directory listing: train for the bounded run, verify weights/adapter hashes and actual optimizer steps, save, reload in a **fresh serving process**, prove the loaded base/adapter identities, and run paired structured-action tasks. A 128-token example cannot validate the real worker's longer engineering prompt. Report achieved context length, unified-memory peak, wall time, GPU utilization, and contention with robot rendering. A successful 20-step run proves infrastructure only; improvement requires held-out evaluation. No model or dataset was downloaded and no training was started during this review.

## 9. ScienceClaw + Infinite prior work and the defensible new contribution

Primary paper: Fiona Y. Wang, Lee Marom, Subhadeep Pal, Rachel K. Luu, Wei Lu, Jaime A. Berkovich, and Markus J. Buehler, **Autonomous Agents Coordinating Distributed Discovery Through Emergent Artifact Exchange**, [arXiv:2603.14312v1](https://arxiv.org/abs/2603.14312), submitted March 15, 2026. The [full HTML](https://arxiv.org/html/2603.14312v1) was retrieved. This review inspected the abstract, architecture/governance sections, quantitative-characterization section, selected case-study/statistical passages, conclusions, and methods; **it did not reproduce the paper's code or numerical experiments and is not a full independent paper validation**.

Already established as prior work in the paper:

- Independent scientific agent profiles and configurable model backends; a large registry of typed JSON-returning CLI skills; autonomous selection and chaining.
- Immutable artifacts with identifiers, SHA-256 hashes, typed metadata, and multi-parent computational-lineage DAGs.
- Broadcast unmet needs, ArtifactReactor pressure scoring and schema matching, peer synthesis, and an ArtifactMutator handling redundant, stagnant, or conflicting branches.
- Persistent journal, investigation tracker, and knowledge graph; autonomous heartbeat cycles; typed human interventions.
- Infinite's provenance displays, threaded discussion, `cite/contradict/extend/replicate` relations, community reputation, and governance.
- Four scientific case studies spanning peptide design, ceramics screening, resonance, and formal urban/grain-boundary analogy. Section 3.1 quantifies agents/tools/artifacts/synthesis counts and DAG depth. These are substantive workflow measurements, but by themselves do not identify the causal benefit of sharing or the effect of learned weights.

**SentiLab must not claim that agent exchange, a provenance DAG, persistent memory, or heterogeneous tool use is its novel invention.** The proposed differential contribution is an executed, narrowly defined thermal-engineering benchmark: exact geometry and constraints; physically interpreted simulator outputs; execution-boundary authority; independent computational and model-validity checks; accurate evidence withdrawal; equal-budget classical/single/isolated/shared/adapted comparisons; a reloadable NeMo worker actually trained/evaluated on the declared hardware; CLI/MCP parity; and observed external reuse. These remain proposed contributions until demonstrated.

Specific expert challenges to carry into review:

1. **Convergence is not correctness.** Common parents, cloned roles, shared model biases, and shared solver defects can make apparently independent paths agree. Track independence by evidence and execution lineage, not by agent count. A multi-parent synthesis node proves combination, not scientific novelty or validity.
2. **Process metrics are not causal benefit.** Artifact counts and average DAG depth can reward busywork. The inspected paper sections do not supply the project's proposed matched-budget isolated-versus-shared or base-versus-adapter ablations. SentiLab should preregister those comparisons and also report failed work, redundant work, final objective, budget, and intervention rate.
3. **Reputation must not override hard evidence.** Social engagement and provenance depth do not establish numerical validity. Deterministic geometry/physics/reproduction gates must dominate any LLM judge, karma score, or consensus.
4. **Mutation must preserve auditability.** If a discovery graph is simplified or pruned, preserve original records and the reason for supersession. SentiLab needs tested stale/withdrawn dependency propagation that retains independently supported findings and the original history, including failed candidates and relevant training lineage.
5. **Autonomy must be scoped precisely.** The paper's Table 1 notes that humans generated reports and figures for materials/resonance even while investigations ran without redirects. SentiLab's requested hands-off live product should measure its whole required path, with interventions and manual work disclosed rather than inherited autonomy claims.
6. **A nonsignificant test does not establish equivalence.** The formal-analogy case explicitly notes limited statistical power for seven-node graphs. For SentiLab, use paired outcomes, preregistered estimands, uncertainty, and practical-equivalence margins where appropriate; no improvement or inconclusive evidence is a valid result.
7. **Proxy scores are domain-limited.** The paper distinguishes computational screens and hypotheses from further experimental follow-up. Likewise, thermal-center readings and weighted Manhattan wiring are defined model outputs/proxies, not manufactured-device validation or timing signoff.

The HTML labels the paper **CC BY-NC-ND 4.0**. Cite and summarize it; separately inspect rights before adapting or redistributing figures. The article's license does not determine the licenses of linked software or datasets.

## 10. Official event verification and remaining onsite claims

The [current official ScienceClaw site](https://scienceclawhack.ai/) and its linked [Luma event](https://luma.com/event/evt-lrhAXSeA3Dq8uSI) were both retrieved on October 30 Eastern. Verified:

- Event: **October 30–November 1, 2026**, MIT Media Lab, in person. Teams have **2–5 people**, all attending in person. Agents are not additional human team members.
- Sunday **November 1 at 1:00 p.m. America/New_York**: hacking ends and final slides are due. Presentations/judging **2:30 p.m.**, awards **4:30 p.m.** Luma metadata explicitly uses America/New_York. November 1 is **EST, UTC−5**, after the DST transition that morning; schedule absolute jobs accordingly.
- The main rubric is significance **20%**, scientific/technical impact **25%**, decentralized agency **20%**, collective capability **25%**, execution/validation **10%**. The collaboration bonus is up to **+10 points** for capabilities that materially strengthen another team.
- The rules permit combining/reusing existing technology and are model/framework agnostic. They demand a functioning system, a meaningful result, and evidence; there is one overall competition rather than separate main tracks.
- The official FAQ lists **three NVIDIA DGX Sparks**. The prize section lists **alphaXiv $500 in OpenResearch GPU credits**, a Formlabs Form Studio 1 printer, and the E14 $50K SAFE with its incorporation conditions. None of this proves an allocation to this team.

**Not confirmed by these public pages:** the NVIDIA three-prize split into BioNeMo, ALCHEMI, and general-platform awards; the precise sponsor submission form/software-use requirements; an allocation of one or sixteen H100s; Brev redemption/credit details; or a Friday 10 p.m. team-registration cutoff. Retain those as attachment/onsite claims awaiting organizer or mentor confirmation. The public site still shows an **October 26 final application deadline**, and Luma currently says **Registration Closed**. Do not report registration as complete or silently replace an onsite instruction; record the team's actual accepted/registered status with the human owner.

Practical plan consequence: keep the internal evidence, rehearsal, and submission buffers before 1 p.m. Sunday, obtain precise sponsor requirements, and demonstrate an actual partner request → deterministic check → returned receipt → downstream use. A published API, self-test, prize mention, or unconfirmed credit allocation does not meet those evidence requirements.
