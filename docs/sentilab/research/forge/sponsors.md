# ScienceClaw sponsors: where they help SentiLab win (v2.1)

Forge research subagent. Read-only: no sign-ups, keys, installs, runs, posts or contact. Companion to `nebius.md` (Nebius in depth), `FORGE-FINDINGS.md` (benchmark headroom) and `openresearch-jev-comparison-contract.md` (the offline comparison contract, same folder in the repo).

**Timing.**
- **v1:** research ran 2026-10-31 from 18:11Z to about 19:30Z (completed). The file was written at about 19:30Z and committed at 153c79e6 (19:32:39Z). v1's header said "19:20–20:30Z": that was a planned window, not the time the research took.
- **v2:** applies root's review #57079 and her exact-source correction #57080. Work started at 19:41Z; see the commit timestamp.
- **v2.1:** applies the wording repairs from root's review of d30b9f30 (commit comment 207557916, room #57104): H100 figures relabelled as list-price illustrations, router "optimum" qualified as solver termination, the historical 1 mm row added, and the source binding stated exactly. Work started at about 20:10Z; see the commit timestamp.
- **Confirmed by root** (#57079; four independent official reads at 19:35Z): the prizes, the six judges, one overall competition, and the rubric (20/25/20/25/10 plus a 10-point collaboration bonus).
- **Still unknown:** our registration, separate NVIDIA award categories and team credit allocations.

**Tags:**
- [OFFICIAL]: fetched 10-31 from the event's, sponsor's or vendor's own page.
- [OFFICIAL-snippet]: an official page seen only in a search snippet.
- [THIRD-PARTY]: any other source.
- [INTERNAL]: our repo, room or memory notes, cited by path@sha or message number.
- [COMPUTED]: my arithmetic.
- [INFERRED]: my reasoning.
- [UNVERIFIED]: I could not confirm it.

**Clock:** US DST ends at 2 AM Sunday, so Sun 1:00 PM EST = **18:00Z** (slides due), 2:30 PM = 19:30Z (judging), 4:30 PM = 21:30Z (awards). [COMPUTED from the OFFICIAL schedule]

---

## 0. Bottom line

1. **There are no sponsor tracks.** The site says "There is one overall competition, rather than separate tracks", and no rubric line rewards sponsor use. Sponsors matter in two ways [OFFICIAL]:
   - their prizes, though the site doesn't say who gets which;
   - two of the six judges: Nikita Fedik (NVIDIA, ALCHEMI) and Ian Ferguson (Formlabs).
2. **Known prizes** [OFFICIAL]:
   - E14: $50K SAFE.
   - NVIDIA: three DGX Sparks.
   - Formlabs: a Form Studio 1 printer.
   - alphaXiv: $500 in OpenResearch GPU credits.
   - "with more to be announced".
   - Source B says the Sparks are three separate awards: BioNeMo, ALCHEMI, and a general NVIDIA-platform award. [INTERNAL, UNVERIFIED]
3. **OpenResearch is a harness, not a substitute decision model.**
   - The reviewed documentation describes no directly substitutable endpoint. [OFFICIAL docs, as qualified in §4.1]
   - Jev (`jev-1.13.0`) stays live.
   - OpenResearch can host the offline comparison under the new contract. Any challenger must be an admitted model. [INFERRED]
4. **Most credible NVIDIA story, if admissions and grants land:** NVIDIA software in the loop on one GB10.
   - A NeMo AutoModel-loaded LoRA preflight already exists. It is plumbing evidence only.
   - A Nemotron NIM could join, but only after admission on our Dell host.
   - A cuOpt cross-check would be bound to one exact routing MILP.
   - The trained-response implementation has priority, and no old job restarts. [INTERNAL #57079]
5. **Gates:**
   - Memory says our registration is unconfirmed. [INTERNAL]
   - The onsite questions are already with the human; send no duplicate prompt. [INTERNAL #57079]
   - Nebius stays deferred under the newer human direction. [INTERNAL #57079]
6. **Visibility conflict.** Carter's 10-28 rule forbids naming vendors on public surfaces. [INTERNAL `memory/feedback_public_naming_intent_model.md`]
   - He decides whether the deck and sentilab.aidenid.com may name sponsors.
   - The front door stays vendor-free, and the deck says "intent model", not Jev.

---

## 1. Event rules behind every prize
Source: [OFFICIAL https://scienceclawhack.ai/] unless a row says otherwise.

| Item | Fact |
|---|---|
| Format | In person at the MIT Media Lab, Oct 30–Nov 1. Teams of 2–5; "every member should attend in person". Approved applicants are added to Discord. The final application deadline was Oct 26. |
| Deliverable | "End of hacking - final slides due", Sun 1:00 PM. No portal or format is given. Presentations start 2:30 PM, awards 4:30 PM. Luma matches. [OFFICIAL https://luma.com/event/evt-lrhAXSeA3Dq8uSI] |
| Rubric | Problem Significance 20% · Scientific/Technical Impact 25% · Decentralized Agency 20% · Collective Capability 25% · Execution & Validation 10%. For Collective Capability: "multi-agent vs. single-agent, collaborative vs. isolated, or decentralized vs. centralized". |
| Bonus | Up to +10 for "capabilities that materially strengthen other teams", e.g. "A tool or agent successfully reused by another team". |
| Models | "ScienceClaw is model- and framework-agnostic." The shared pool is "allocated based on project needs, technical fit, and availability". No request procedure is published. |
| Judges | Avijit Ghosh (Hugging Face) · Desiree Plata (MIT Associate Dean of Engineering) · Yilun Du (Harvard) · Riken Shah (xAI) · Ian Ferguson (Formlabs Director of Hardware) · Nikita Fedik (NVIDIA Senior TME; NVIDIA's author page shows ALCHEMI work [OFFICIAL https://developer.nvidia.com/blog/author/nfedik/]). |
| Contact | scienceclaw@mit.edu (shown obfuscated on the page) and Discord. |

---

## 2. Sponsor list (tier per the site's sponsor strip)

**Columns:** "Prize / track / bounty" is what the sponsor puts up. "Eligibility, judging" covers what's known about winning it.

**Deadline for every row:** prizes are judged on the Sun 1:00 PM slides and the 2:30 PM presentations. [OFFICIAL]

| Sponsor | Tier | Credited with | Prize / track / bounty | Eligibility, judging | What we'd do to qualify |
|---|---|---|---|---|---|
| LAMM (MIT, Buehler lab) | Top bar, organizer | Builders of ScienceClaw × Infinite (arXiv 2603.14312) [OFFICIAL arXiv] | None | — | None. The collaboration-bonus angle is in §3 |
| E14 Fund | Top bar, host | "E14 Fund Prize $50K*" [OFFICIAL] | "$50K SAFE (no cap, no discount) on incorporation of an E14-backable startup" [OFFICIAL] | E14 "only invests in startups with key contributors from MIT" and doesn't invest before founders leave MIT [OFFICIAL https://www.e14.vc/faq]. Unclear whether an existing company or our team qualifies [UNVERIFIED] | An MIT key contributor, plus willingness to incorporate |
| NVIDIA | Platform | Fri talk "NVIDIA: Agentic Methods for ALCHEMI and BioNeMo"; judge Fedik [OFFICIAL] | Three DGX Sparks [OFFICIAL]. Source B splits them BioNeMo / ALCHEMI / general [INTERNAL, UNVERIFIED]. Another team's notes: "awarded as a prize", with NIM access via "hackathon credits or build.nvidia.com key" [THIRD-PARTY https://github.com/fractastical/delphi/issues/1] | Criteria unpublished. Source B: NVIDIA wants "meaningful use of their software higher in the stack" [INTERNAL, UNVERIFIED] | Show NVIDIA software inside the loop (§5) |
| Claude (Anthropic) | Builder | Logo only | None stated | — | Already used by our agents. No event credits found. The startup program is closed: "Our current cohort is now full" (Oct 13) [OFFICIAL https://claude.com/resources/articles/were-expanding-the-claude-startups-program-to-help-founders-build] |
| Formlabs | Builder | Sat 10–11 AM "Formlabs Preform API Demo"; Sat dinner; judge Ferguson [OFFICIAL] | Form Studio 1 resin printer, "Starting at $699" [OFFICIAL https://formlabs.com/3d-printers/form-studio-1/] | Criteria unpublished [UNVERIFIED] | PreForm Local API in the agent loop (§3, top-5 #4) |
| Nebius | Builder | Logo only [OFFICIAL] | None stated. Source B mentions an H100 pool and a "sponsor submission" [INTERNAL, UNVERIFIED] | — | **Deferred** under the newer human direction [INTERNAL #57079]. `nebius.md` holds the details |
| Edison Scientific | Builder | Sun breakfast [OFFICIAL] | None | — | Optional literature check (§3) |
| Stifel Venture Banking | Builder | Sat lunch [OFFICIAL] | None | — | Nothing technical |
| Google Cloud | Builder | Logo only | None | — | Optional Gemini lab (§3) |
| OpenAI | Supporter | Logo only | None | — | Already used (astra/Codex labs) [INTERNAL] |
| Romix Biosciences | Supporter | Sat breakfast | None | — | No fit: "Revolutionizing Liquid Biopsy", cfRNA [OFFICIAL https://romixbio.com/] |
| alphaXiv | Supporter | Prize sponsor | "$500 in OpenResearch GPU Credits", linking to https://openresearch.sh/ [OFFICIAL] | Criteria unpublished [UNVERIFIED] | OpenResearch and the alphaXiv MCP, used visibly (§3, §4) |
| MIT School of Engineering | Supporter | Fri dinner; judge Plata is its Associate Dean | None | — | Nothing |
| LILA (Lila Sciences) | Supporter | Sun lunch | None | No public API ("Partner with LILA") [OFFICIAL https://www.lila.ai/] | Nothing in 24 h |

**Sponsor challenges:** mentioned only generically. No bounties are listed. [OFFICIAL]

**Not sponsors:** the "With People From" strip lists Hardmode, Sundai, Harvard, UMich, MIT and ReactorField. ReactorField runs mentor sessions Sat 2–6 PM. [OFFICIAL]

---

## 3. Integration fit per sponsor

**Surfaces:** SentiLab (labs, oracle, live view), the AIdenID front door (aquarium-edge Worker) and Senti rooms (incl. help room 32a841e5).

**Cost fields used below:**
- **Actual:** what we really paid. **Unknown** unless measured. A local GB10 does not establish $0. [INTERNAL SLAB-018 README: "no zero-dollar claim is made"]
- **H100 list-price illustration:** `charged_seconds / 3600 × USD_per_hour`, with USD_per_hour = $4.50.
  - $4.50 is Nebius's HGX H100 on-demand list price [OFFICIAL via `nebius.md` §2.2].
  - **It is a normalized H100 list-price illustration only.** It is not a forecast of GB10 runtime, not a forecast of marginal actual cost, and not a claim of hardware equivalence. Nebius use is deferred.

### NVIDIA
- **Build or use:** see §5.
- **Access:**
  - An NGC API key, with custody on astra's PC only.
  - The GB10 is reachable only from astra's PC. No Brev registration to share access. [INTERNAL #57079]
- **Cost:** see §5.4.

### Formlabs
- **Build:** an agent step called "print-prep".
  1. Turn temperature fields from an evaluator that has passed gate zero into two heightmap STLs on the same z-scale: the human reference and the best agent layout.
     - Gate zero is a computational reproduction of the published 75.48 / 115.94 C, not a physical calibration [INTERNAL #57079].
  2. Drive PreFormServer over HTTP: `POST /scene/` → `/import-model/` → `/auto-orient/` → `/auto-support/` → `/estimate-print-time/`, then save the .form and print.
- **PreFormServer facts** [OFFICIAL Local API 0.9.30 https://formlabs-dashboard-api-resources.s3.amazonaws.com/formlabs-local-api-latest.html]:
  - Windows and macOS only.
  - `--port` is required.
  - A Dashboard login is needed only for remote or Fleet printing.
- **Caveats:**
  - Form Studio 1 needs PreForm; whether it supports the Local API isn't stated [OFFICIAL; UNVERIFIED].
  - **A printed map is a physical rendering of data, not a thermal test.**
- **Access:** printer time and resin onsite [UNVERIFIED].
- **Cost:** PreForm is free [OFFICIAL]; actual resin cost is unknown.
- **Time:** 2–3 h plus print time [UNVERIFIED].

### alphaXiv
- **(a) alphaXiv MCP** for literature lookups in Senti research tickets [OFFICIAL https://www.alphaxiv.org/docs/mcp].
  - Endpoint `https://api.alphaxiv.org/mcp/v1`; auth by OAuth 2.1 or an API key.
  - 21 tools. Quota amounts aren't published. Native MCP clients only.
- **(b) OpenResearch harness**, see §4.
- **Access:** an alphaXiv account for the MCP.
- **Cost:** actual unknown; quota [UNVERIFIED].
- **Time:** ≤1 h.

### Nebius
- **Deferred** under the newer human direction [INTERNAL #57079]. The integration analysis stays in `nebius.md` for later.

### Claude
- **Already used:** Claude agents run warden and forge.
- **Help room:** a Claude.ai custom connector to our hosted Senti MCP lets other teams' Claude agents take help-room tickets [INTERNAL `memory/reference_hosted_mcp.md`].
- **Blocker:** "Claude in boxes" needs a key; that's a Carter item [INTERNAL].

### OpenAI
- The astra labs already use it [INTERNAL].

### Google Cloud
- **Build:** an optional Gemini lab via an AI Studio key [INFERRED].
- **ScienceClaw link:** its README points agents to a Gemini key [OFFICIAL https://github.com/lamm-mit/scienceclaw].
- **GCP Free Trial:** "$300 Welcome credit to spend over 90 days", and it requires a card [OFFICIAL https://docs.cloud.google.com/free/docs/free-cloud-features].

### Edison Scientific
- **Build:** one bounded literature task through edison-client (`JobNames.LITERATURE`) with a platform API key [OFFICIAL-snippet https://edisonscientific.gitbook.io/edison-cookbook/edison-client].
- **Credits** [OFFICIAL-snippet https://edisonscientific.com/news/we-raised-70m-to-accelerate-science]:
  - A Literature task costs 1–2 credits.
  - Users without a paid plan get 10 credits a month.
  - "API access will remain paid".
- **Value:** low.

### LAMM / ScienceClaw × Infinite
- **Build:** wrap our read-only oracle as a ScienceClaw skill or MCP tool, then post one verified artifact with its lineage to Infinite [INFERRED].
- **Access** [OFFICIAL https://github.com/lamm-mit/scienceclaw]:
  - API base `https://lamm.mit.edu/infinite/api`.
  - Setup registers the agent.
  - "Minimum 10 karma required to post".
- **Approval:** posting is publication, so it needs Carter's GO.
- **Time:** 3–5 h.

### E14, Stifel, Lila, Romix, MIT SoE
- No technical integration.

---

## 4. OpenResearch compared with Jev

### 4.1 What OpenResearch is [OFFICIAL]
- **What it is:**
  - "Turn your coding agents into research agents"; "The local-first harness & workspace for research agents".
  - MIT license. v0.2.23 (Oct 31) ships Linux aarch64 builds.
  - Sources: https://github.com/alphaXiv/OpenResearch and https://github.com/alphaXiv/OpenResearch/releases.
- **Agents it drives** (https://openresearch.sh/docs/agents):
  - Claude Code, Codex, OpenCode, Cursor and Google Antigravity, plus any ACP agent.
  - "OpenResearch runs your existing coding agent with your own subscription or API key."
- **Local models**, per the same page:
  - Through OpenCode you "choose a tool-capable model" served locally: LM Studio, oMLX, Ollama, or "any OpenAI-compatible server (such as vLLM) that exposes `/v1/models` and tool calls on a loopback address".
  - A remote server needs an SSH port forward.
  - The docs say "A 32K context window is a good start." That does not show our trained adapter fits: SLAB-018 and SLAB-047b served it with `--max-model-len 1024` [INTERNAL `docs/sentilab/evidence/SLAB-018/attempt-01/http-models.json:11`].
- **Backends** (https://openresearch.sh/docs/compute):
  - local, SSH, Slurm, Kubernetes, Ray, HF Jobs, Modal, Tinker, and managed.
  - SSH hosts need bash, tar and Python 3.6+.
- **Evidence retention (same page):**
  - SSH and Slurm runs keep only each project's "three newest runs". Older runs are deleted except their TensorBoard logs, unless `--keep-remote-runs true` is passed.
  - So any integration uses `--keep-remote-runs true` **and** writes complete independent receipts. Turning telemetry off does not preserve history.
- **Managed compute** (https://openresearch.sh/docs/cli, https://openresearch.sh/docs/billing):
  - Machines are rented from Lambda, RunPod, Vast and others, "billed at cost" from a prepaid balance.
  - No GPU prices are published.
  - The $500 prize is presumably a balance credit [INFERRED].
- **Endpoints:** **no directly substitutable decision endpoint was found in the reviewed documentation** (README; docs pages agents, compute, cli, billing; release notes v0.2.19–v0.2.23). They describe no hosted inference API, hosted model or MCP server.
- **Telemetry:**
  - On by default: coarse analytics plus agent-written feedback. Counts feed the public /rankings page.
  - Opt out with `orx telemetry off`.
- **Security:** a third-party review says that in remote mode "the remote service binds to loopback and has no application-level authentication". Use single-user hosts only. [THIRD-PARTY https://hysenlabs.com/projects/alphaxiv-openresearch]

### 4.2 The decision under test, and why OpenResearch can't take Jev's place

| | Jev (front door today) | OpenResearch |
|---|---|---|
| What it is | System One model: typed Choice / Score / Noul answers with calibrated probabilities [OFFICIAL https://docs.typesafe.ai/llms.txt] | A research-agent harness [OFFICIAL] |
| Per-request endpoint | `POST https://api.typesafe.ai/v1/systemone` [OFFICIAL] | None directly substitutable in the reviewed docs |
| Latency | "70–500 ms, TypeSafe-reported" [THIRD-PARTY https://www.truefoundry.com/blog/typesafe-ai-jev]. Not measured by us. Edge timeout 2,500 ms [INTERNAL] | Not applicable per request |
| Cost | $0.042 per 1M input tokens, output free [OFFICIAL https://docs.typesafe.ai/models] | Free software, plus the agent's model and any managed GPUs [OFFICIAL] |
| Rate limit | Per-org tokens/s and requests/s; HTTP 429 when exceeded [OFFICIAL] | Whatever the agent provider allows |
| Version | `jev-latest` → `jev-1.14.0` (Oct 14). We pin `jev-1.13.0`, which is still active [OFFICIAL] | v0.2.23 |

**How the front door uses Jev** [INTERNAL source facts at Sentinelayer-AIdenID/AIdenID `09b2ff466d0fadcb83b09b0f6f213d13f430c9e1`, `workers/aquarium-edge/src/index.ts` sha256 `0b0668d9…`. These are not facts about the deployed Worker or its effective variables; warden owns that binding]:
- `obtainVerdict` is shared by two paths, and both call `callJev(env, jevState(...), TRIAGE_QUESTIONS, 2500 ms)` with the pinned `jev-1.13.0`:
  - **`judgeUnknown`** (the unknown residue): ≥0.75 becomes automation; anything else stays unresolved.
  - **`judgeBrowser`** (consistent browser shapes):
    - Behind `JUDGE_CONSISTENT_BROWSERS`, and only after the DNT/GPC privacy filter.
    - ≥0.75 becomes automation, ≤0.25 "intent model agrees" human, in between becomes unknown, unavailable becomes unverified human.
- `maybeEnrich` adds a sampled `purpose` Choice. It calls `callJev` directly, not through `obtainVerdict`, with a different payload and a 750 ms code default. See contract §2.
- Calls run in `ctx.waitUntil`, off the response path.

### 4.3 Where OpenResearch fits
1. **Harness for the offline comparison.** It is governed by `openresearch-jev-comparison-contract.md`. Nothing is installed, run or contacted under it yet.
2. **Blinded adjudication support.** An agent session may act as one blinded adjudicator: it sees only the state, never arm outputs. Its labels are recorded as agent labels.
3. **Help-room OpenResearch-review ticket.** A "reproduce gate zero" project: computational reproduction of 75.48 / 115.94 C.
   - Team fractastical/delphi already uses OpenResearch (#16) and wants evidence for the +10 bonus (#41). [THIRD-PARTY https://github.com/fractastical/delphi/issues]
4. **Prize credits.** Only if we win.

### 4.4 Comparison rules (summary; the contract is binding)
- **Agreement is not accuracy.**
  - Agreement compares Jev with the challenger.
  - Accuracy needs labels: known controlled client conditions, plus blinded adjudication of held-out distinct shapes, with "ambiguous" as an allowed label.
- **Datasets:**
  - The exact original states are frozen and hashed.
  - Any reconstruction is a separate, labelled dataset and is never pooled.
- **Denominators:** every missing, timeout, error, budget refusal and fallback stays in them.
- **Latency:** fresh calls only. Replayed answers don't measure latency.
- **Challenger:** an admitted model only. Nemotron 3.5 Lightning is a candidate, not admitted (§5.2).
- **Scope:**
  - Jev stays live; any production change is Carter's.
  - The original five-arm chiplet study stays separate [INTERNAL `docs/sentilab/draft-0.5/SCIENCE-REVIEW.md:66`].

**List-price illustrations per 1k decisions** [COMPUTED; assumes 1,000 input + 50 output tokens per decision; actual = unknown until `usage` is measured]:
- Jev: 1M × $0.042 = $0.042.
- An admitted local GPU challenger: actual unknown. Any H100 figure is the §3 list-price illustration, not a cost forecast.

---

## 5. NVIDIA

### 5.1 At this event
- **Official** [OFFICIAL]:
  - Platform tier.
  - Three DGX Sparks.
  - The Friday ALCHEMI/BioNeMo talk.
  - Judge Fedik.
- **From Source B, unconfirmed** [INTERNAL, UNVERIFIED]:
  - Three awards.
  - NVIDIA wants "software higher in the stack".
  - An H100 pool.
  - Brev redemption.
- **What other teams are doing** [THIRD-PARTY]:
  - fractastical/delphi filed NVIDIA, NIM, BioNeMo and ALCHEMI integration issues.
  - InquilineKea is using ALCHEMI (https://github.com/InquilineKea/scienceclaw-hackathon-2026).

### 5.2 NVIDIA offerings and their fit

#### NeMo AutoModel: what SLAB-018 did and didn't establish [INTERNAL `docs/sentilab/evidence/SLAB-018/README.md`]
- **Method:** the model loads through NeMo AutoModel and trains with an explicit PyTorch/HF PEFT loop, not NeMo's `train_ft` recipe.
- **Ledger charge: 494.189538605 s.** That is 314.189538605 s of measured stages plus a separately labelled, conservative 180 s reservation for earlier primitive checks.
  - It is **not** "8.24 measured GPU minutes", and the reservation is not measured usage.
  - The grant cap is 60 GPU-minutes.
- **Scope:** evaluation used six source fixture cases, all present in training. It is plumbing evidence only.

#### Charges kept separate [INTERNAL `docs/sentilab/evidence/SLAB-047/README.md`]
- SLAB-047 failed closed: 79.617588726 s.
- SLAB-047b preflight was non-GPU: 0.638011345 s.
- SLAB-047b serving: 148.909503325 s.
- Lifecycle seconds are not measured GPU busy time, and monetary cost is unmeasured.
- Never rerun completed SLAB-018, failed SLAB-047 or completed SLAB-047b.

#### Nemotron 3.5 Lightning 30B-A3B NIM
- **Documented:** it is the default NIM in the current DGX Spark NIM playbook [OFFICIAL https://build.nvidia.com/spark/nim-llm/overview].
- **Admission on our Dell host (promaxgb10-9a1e) is separate and pending.** Each item needs its own evidence:
  - host;
  - runtime (driver 580.178.04, CUDA, container runtime);
  - image digest;
  - NIM profile;
  - license. The model is OpenMDW-1.1 per Nebius's catalog [OFFICIAL via `nebius.md`]. The container terms for development use are [THIRD-PARTY].
  - latency admission.
- **Constraints:**
  - NGC key custody stays on astra's PC.
  - No Brev registration.
  - The trained-response implementation has priority.
- **Speed:** third-party DGX Spark figures (~80 tok/s single-stream) are not a measurement on our host [THIRD-PARTY https://dev.classmethod.jp/en/articles/dgx-spark-nemotron-3-5-lightning-first-touch/].

#### cuOpt (LP/QP/VRP; MIP in beta)
- **Platform:** aarch64 builds and containers exist; the Spark porting guide lists cuOpt as supported (minimum 25.12); `cuopt_cli` reads MPS/LP files [OFFICIAL https://github.com/NVIDIA/cuopt, https://docs.nvidia.com/dgx/dgx-spark-porting-guide/latest/porting/dependencies.html, https://docs.nvidia.com/cuopt/user-guide/latest/cuopt-cli/index.html].
- **Our router:** `sundai_hotspot/tap_router.py` (TAP-2.5D's MILP, ported from CPLEX to HiGHS via `scipy.optimize.milp`).
  - Pinned SciPy is 1.17.0; HiGHS 1.8.0 is recorded, not pinned.
  - It refuses any solve whose solver termination status is not "optimal" under the recorded tolerances. That status is the solver's report, not an exact arithmetic proof or an independent feasibility check. [INTERNAL sentilab@46791be]
- **Router acceptance is still PENDING.** [INTERNAL #57079, #57080]
- **Three separate wirelength sets** [INTERNAL PR #66 source audit via #57080; values stored rounded to one decimal]. Never interchange them:

| Set | Ascend 910 (Fig. 6a) | CPU-DRAM / micro150 (Fig. 5a) | Source field |
|---|---:|---:|---|
| Raw open-router output | 16,417.5 mm | 67,688.4 mm | `docs/sentilab/references/ascend910-tap25d-fig6a.json` and `micro150-tap25d-fig5a.json`, `routed_wirelength_mm` |
| Snap-0.5 mm engineering output | 16,672.1 mm | 68,867.3 mm | `*-snap0p5.json`, `value_mm` ("routed (open router), not paper") |
| Paper target (Ma et al., DATE 2021) | 16,426 mm | 67,686 mm | `paper_reported` / `paper_mm` |
| *Historical, separately labelled:* kept 1 mm `snapped` layout (not a comparison baseline) | 18,155.8 mm | 64,771.3 mm | `snapped.routed_wirelength_mm` |

- **Rule:** none of these copies shows the paper values are accepted HiGHS results. The paper targets are never a numerical oracle.
- **"Four identities"** in root's review means two problems × two layouts (raw and snap-0.5), not four numeric categories [INTERNAL review comment 207557916].
- **What a cross-check must do:**
  - Bind to one selected geometry (raw or snap-0.5), its exact netlist and MILP, and its units.
  - Record full solver evidence for both solvers: status, objective, bound and gap, tolerances, iterations and time, versions, and input hashes.
  - Check assignment feasibility (every constraint satisfied at the stated tolerance), integrality, objective and tolerances. Objective equality alone is not enough.

#### PhysicsNeMo
- **Fit:** a surrogate "scout" lab trained on maps from an evaluator that passed gate zero (computational reproduction).
  - DeepOHeat-v1/v2 pair a surrogate with a solver check [THIRD-PARTY arXiv 2504.03955, 2608.16080].
- **On GB10:** aarch64 installs via uv [OFFICIAL-snippet https://docs.nvidia.com/physicsnemo/latest/getting-started/installation.html].
- **Time:** 6–10 h. Risky.

#### NemoGuard JailbreakDetect NIM (`/v1/classify`)
- **Fit:** shadow-classify agents' free-text purpose declarations.
- **Platform:** ARM64 support is [UNVERIFIED] [OFFICIAL-snippet https://docs.nvidia.com/nim/nemoguard-jailbreakdetect/latest/index.html].
- **Constraint:** it is a production edge change, in Daybreak's lane.

#### NemoClaw / OpenShell
- **Fit:** NVIDIA's sandboxed OpenClaw stack. ScienceClaw has an OpenClaw MCP path [OFFICIAL https://build.nvidia.com/spark/nemoclaw, https://github.com/lamm-mit/scienceclaw].
- **Time:** 2–4 h after admission.

#### Brev
- **Not used.** Key custody stays on astra's PC, and nobody registers with Brev to share access. [INTERNAL #57079]

#### ALCHEMI / BioNeMo
- **Recommendation:** skip. There is no defensible bridge from package-level thermal work in 24 h [INFERRED].

#### Warp / cuDSS heat solver
- **Recommendation:** skip. It would replace the evaluator, and no evaluator version runs searches until it reproduces a published number [INTERNAL].

**GB10 specs** [OFFICIAL https://www.nvidia.com/en-us/products/workstations/dgx-spark/]:
- 128 GB unified memory, 273 GB/s.
- Up to 1 PFLOP FP4 (sparse).
- 20-core Arm CPU.

**Our box:** a Dell Pro Max GB10 [INTERNAL].

### 5.3 What would most convince judges in about 24 h
- **The story:** "NVIDIA software in the loop on one DGX Spark-class box", shown only for steps that actually ran with evidence. [INFERRED]
  1. Labs propose layouts.
  2. A cuOpt cross-check runs on one exact routing MILP.
  3. HotSpot, after gate zero's computational reproduction, verifies.
  4. The trained-response implementation (priority) serves the LoRA worker.
  5. A Nemotron NIM lab, only if admitted.
- **Per-step provenance:**
  - container digest, model ID, solver evidence;
  - charged seconds as recorded (not GPU busy time).
- **Don't claim:**
  - $0 cost or measured speed on our host;
  - cuOpt speed-ups;
  - "accepted" router values;
  - a "trained" worker beyond the evaluation;
  - ALCHEMI relevance.

### 5.4 GPU cost fields

**Illustration basis:** `charged_seconds / 3600 × $4.50`, the §3 H100 list-price illustration. It is not a GB10 runtime or actual-cost forecast. [COMPUTED]

| Item | Recorded charge | Actual $ | H100 list-price illustration |
|---|---|---|---|
| SLAB-018 (completed; never rerun) | 494.189538605 s incl. 180 s reservation | Unknown | $0.62 |
| SLAB-047 (failed closed; never rerun) | 79.617588726 s | Unknown | $0.10 |
| SLAB-047b preflight (non-GPU) | 0.638011345 s, no GPU | Unknown | n/a |
| SLAB-047b serving (completed; never rerun) | 148.909503325 s | Unknown | $0.19 |
| Nemotron NIM admission (proposed) | Not run | Unknown | $4.50 per granted GPU-hour of lifecycle |
| cuOpt cross-check (proposed) | Not run | Unknown | e.g. a 10-minute lifecycle → $0.75 |

---

## 6. Top recommendations, ranked by win value ÷ effort

### 1. Settle eligibility and sponsor terms in person
- **Effort:** low. **Win value:** unlocks everything.
- **Status:** the questions are **already with the human**. This list is a reference, not a new prompt. [INTERNAL #57079]
- **Questions:**
  - Organizers: registration, where slides go, who gets which prize, any sponsor submissions.
  - NVIDIA: award categories and criteria in writing; NIM credits.
  - Formlabs: printer time and Local API support.
  - alphaXiv: how the credits are awarded.
  - E14: do we qualify?
  - Others: any event credits.

### 2. Admit a Nemotron NIM on the GB10 as a separate lab
- **Effort:** 3–5 h after grants. **Win value:** high (Sparks, NVIDIA judge, Decentralized Agency).
- **Owners:** astra/root (GB10 and local lifecycle), warden (grants and review), forge (slide).
- **Steps:**
  1. Complete the §5.2 admission items, with the NGC key kept on astra's PC.
  2. Run under a warden grant with a GPU-second cap.
  3. Add lab `gb10-nemotron`. If the SLAB-041 freeze fixed the lab list, run it as a labelled exploratory arm.
- **Blockers:**
  - The trained-response implementation has priority; no old job restarts.
  - Admission evidence.
  - +1s for any scope change.
  - No Brev registration.

### 3. cuOpt cross-check of one exact routing MILP
- **Effort:** 2–4 h after a grant. **Win value:** medium-high (NVIDIA "higher in the stack", Execution & Validation).
- **Owner:** a box ticket via astra and warden.
- **Steps:**
  1. Select one geometry (raw or snap-0.5) and export its exact MILP, with hashes, to MPS.
  2. Run `cuopt_cli` on it.
  3. Compare full solver evidence with HiGHS on the same MILP: feasibility, integrality, objective, tolerances.
- **Rules:** never use the paper targets as an oracle, and don't call any router value "accepted" while acceptance is pending.

### 4. Formlabs "thermal relief" print through the PreForm Local API
- **Effort:** 2–3 h plus print time. **Win value:** medium-high (Formlabs judge, printer prize, A·03, a tangible demo).
- **Owners:** forge (STLs) and warden (PreFormServer on the Windows workstation).
- **Precondition:** maps from an evaluator that has passed gate zero.
- **Caption:** a physical rendering of data, not a thermal test.
- **Blockers:** printer and resin access, and pickup. Downloading PreFormServer may need a sign-in [UNVERIFIED].

### 5. OpenResearch as the offline comparison harness
- **Effort:** contract written; a run needs grants. **Win value:** low-medium.
- **Owners:**
  - forge: the contract.
  - warden: the exact read-only export, plus payer and access evidence.
  - root: reviews the comparison and the local lifecycle.
- **Settings:** `orx telemetry off`, `--keep-remote-runs true`, independent receipts, a local agent.
- **Approval:** none needed for treating it as a harness [INTERNAL #57079].

### Next tier
- ScienceClaw/Infinite skill: public, needs Carter's GO.
- PhysicsNeMo scout.
- NemoGuard shadow.
- Edison literature task.
- Gemini lab.
- Nebius cloud labs: **deferred**.

### Carter-only decisions
- Registration.
- Whether the deck and sentilab.aidenid.com may name sponsors.
- Any production front-door change or new data processor.
- Whether to pursue the E14 SAFE.
