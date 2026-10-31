# ScienceClaw sponsors: where they help SentiLab win

Forge research subagent, 2026-10-31 19:20–20:30Z. Read-only: no sign-ups, keys, posts or contact. Companion to `nebius.md` (Nebius in depth) and `FORGE-FINDINGS.md` (benchmark headroom, gate zero).

**Tags:**
- [OFFICIAL]: fetched 10-31 from the event's, sponsor's or vendor's own page.
- [OFFICIAL-snippet]: an official page seen only in a search snippet.
- [THIRD-PARTY]: any other source.
- [INTERNAL]: our repo or memory notes, cited by path@sha. Primary for our own systems.
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
   - Our Source B says the three Sparks are separate awards: best BioNeMo, best ALCHEMI, and a general NVIDIA-platform award. [INTERNAL, UNVERIFIED]
3. **OpenResearch is not a model.** It is alphaXiv's open-source harness that turns Claude Code, Codex and similar agents into research agents, plus managed GPUs billed at cost.
   - It has no inference API, so it can't sit in the front door's request path. [OFFICIAL]
   - Jev stays live.
   - OpenResearch can run the bake-off. The shadow challenger should be a real model, e.g. Nemotron as a NIM on our GB10. [INFERRED]
4. **Most credible NVIDIA story in 24 h:** the full loop on one GB10.
   - NeMo AutoModel LoRA, already preflighted.
   - A Nemotron NIM serving as a separate lab and as the AIdenID shadow challenger.
   - cuOpt cross-solving our routing MILP.
   - [OFFICIAL capabilities; INTERNAL state; INFERRED value]
5. **Gate first:** memory says our team's registration is unconfirmed, and nothing else matters until it is. [INTERNAL `memory/project_sentilab_hackathon.md`]
6. **Visibility conflict.** Carter's 10-28 rule forbids naming vendors on public surfaces (aidenid.com, public repos and docs). [INTERNAL `memory/feedback_public_naming_intent_model.md`]
   - He must decide whether the deck and sentilab.aidenid.com may name sponsors.
   - The front door stays vendor-free either way, and the deck says "intent model", not Jev.

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

**Columns:** "Prize / track / bounty" is what the sponsor puts up. "Eligibility, judging, deadline" covers what's known about winning it.

**Deadline for every row:** prizes are judged on the Sun 1:00 PM slides and the 2:30 PM presentations. [OFFICIAL]

| Sponsor | Tier | Credited with | Prize / track / bounty | Eligibility, judging, deadline | What we'd do to qualify |
|---|---|---|---|---|---|
| LAMM (MIT, Buehler lab) | Top bar, organizer | Builders of ScienceClaw × Infinite (arXiv 2603.14312) [OFFICIAL arXiv] | None | — | None. The collaboration-bonus angle is in §3 |
| E14 Fund | Top bar, host | "E14 Fund Prize $50K*" [OFFICIAL] | "$50K SAFE (no cap, no discount) on incorporation of an E14-backable startup" [OFFICIAL] | E14 "only invests in startups with key contributors from MIT" and doesn't invest before founders leave MIT [OFFICIAL https://www.e14.vc/faq]. Unclear whether an existing company or our team qualifies [UNVERIFIED] | An MIT key contributor, plus willingness to incorporate. Ask E14 (Haddad/Chin) |
| NVIDIA | Platform | Fri talk "NVIDIA: Agentic Methods for ALCHEMI and BioNeMo"; judge Fedik [OFFICIAL] | Three DGX Sparks [OFFICIAL]. Source B splits them BioNeMo / ALCHEMI / general [INTERNAL, UNVERIFIED]. Another team's notes say "awarded as a prize", with NIM access via "hackathon credits or build.nvidia.com key" [THIRD-PARTY https://github.com/fractastical/delphi/issues/1] | Criteria unpublished. Source B: NVIDIA wants "meaningful use of their software higher in the stack" [INTERNAL, UNVERIFIED] | Show NVIDIA software inside the loop (§5). Get the award categories and any sponsor form in writing |
| Claude (Anthropic) | Builder | Logo only | None stated | — | Already used by our agents. No event credits found. The startup program is closed: "Our current cohort is now full" (Oct 13) [OFFICIAL https://claude.com/resources/articles/were-expanding-the-claude-startups-program-to-help-founders-build] |
| Formlabs | Builder | Sat 10–11 AM "Formlabs Preform API Demo"; Sat dinner; judge Ferguson [OFFICIAL] | Form Studio 1 resin printer, "Starting at $699" [OFFICIAL https://formlabs.com/3d-printers/form-studio-1/] | Criteria unpublished [UNVERIFIED] | Put the PreForm Local API in the agent loop (§3, top-5 #4) |
| Nebius | Builder | Logo only [OFFICIAL] | None stated. Source B mentions an H100 pool and a "sponsor submission" [INTERNAL, UNVERIFIED] | — | See `nebius.md` §3: ask the rep, then Token Factory labs |
| Edison Scientific | Builder | Sun breakfast [OFFICIAL] | None | — | Optional literature check (§3) |
| Stifel Venture Banking | Builder | Sat lunch [OFFICIAL] | None | — | Nothing technical; commercial conversation only |
| Google Cloud | Builder | Logo only | None | — | Optional Gemini lab (§3) |
| OpenAI | Supporter | Logo only | None | — | Already used (astra/Codex labs) [INTERNAL] |
| Romix Biosciences | Supporter | Sat breakfast | None | — | No fit: "Revolutionizing Liquid Biopsy", cfRNA [OFFICIAL https://romixbio.com/] |
| alphaXiv | Supporter | Prize sponsor | "$500 in OpenResearch GPU Credits", linking to https://openresearch.sh/ [OFFICIAL] | Criteria unpublished [UNVERIFIED] | Use OpenResearch and the alphaXiv MCP visibly (§3, §4) |
| MIT School of Engineering | Supporter | Fri dinner; judge Plata is its Associate Dean | None | — | Nothing |
| LILA (Lila Sciences) | Supporter | Sun lunch | None | No public API ("Partner with LILA") [OFFICIAL https://www.lila.ai/] | Nothing in 24 h |

**Sponsor challenges:** mentioned only generically ("Sponsor-led challenges provide concrete inspiration"). No bounties are listed. [OFFICIAL]

**Not sponsors:** the "With People From" strip lists Hardmode, Sundai, Harvard, UMich, MIT and ReactorField. ReactorField runs mentor sessions Sat 2–6 PM. [OFFICIAL]

---

## 3. Integration fit per sponsor

**Surfaces:** SentiLab (labs, oracle, live view), the AIdenID front door (aquarium-edge Worker) and Senti rooms (incl. help room 32a841e5).

### NVIDIA
- **Build or use:** see §5.
- **Access:**
  - NGC API key (free account) for NIM containers [OFFICIAL https://build.nvidia.com/spark/nim-llm/overview].
  - An `nvapi-` key for hosted endpoints [THIRD-PARTY].
  - The GB10 is reachable only from astra's PC [INTERNAL].
- **Cost:** $0 on the GB10.
- **Time:** 2–5 h per item.

### Formlabs
- **Build:** an agent step called "print-prep".
  1. Turn the human-reference and best-agent temperature fields into two heightmap STLs on the same z-scale. Needs gate-zero-calibrated maps first [INTERNAL `FORGE-FINDINGS.md`].
  2. Drive PreFormServer over HTTP: `POST /scene/` → `/import-model/` → `/auto-orient/` → `/auto-support/` → `/estimate-print-time/`, then save the .form and print.
- **PreFormServer facts** [OFFICIAL Local API 0.9.30 https://formlabs-dashboard-api-resources.s3.amazonaws.com/formlabs-local-api-latest.html]:
  - Windows and macOS only, so run it on our Windows workstation.
  - `--port` is required.
  - A Dashboard login is needed only for remote or Fleet printing.
- **Caveats:**
  - Form Studio 1 needs PreForm; whether it supports the Local API isn't stated [OFFICIAL; UNVERIFIED].
  - The print is a physical rendering of our data, not a thermal test. Caption it that way.
- **Access:** printer time and resin onsite [UNVERIFIED].
- **Cost:** PreForm is free [OFFICIAL]; resin cost is [UNVERIFIED].
- **Time:** 2–3 h plus print time [UNVERIFIED].

### alphaXiv
- **(a) alphaXiv MCP** for literature lookups in Senti research tickets [OFFICIAL https://www.alphaxiv.org/docs/mcp].
  - Endpoint `https://api.alphaxiv.org/mcp/v1`; auth by OAuth 2.1 or an API key.
  - 21 tools. Quota amounts aren't published. Native MCP clients only.
- **(b) OpenResearch harness**, see §4.
- **Access:** an alphaXiv account for the MCP. Local OpenResearch needs no account.
- **Cost:** $0 within quota [UNVERIFIED].
- **Time:** ≤1 h.

### Nebius
- **Build:** Token Factory cloud labs next to the GB10 lab, plus a help-room helper agent [INTERNAL `nebius.md` §3].
- **Access:** account, card on file, key, and turn Zero Data Retention on.
- **Cost:** about $0.48–$9.24 per 1k calls [COMPUTED in `nebius.md`].
- **Time:** medium.

### Claude
- **Already used:** Claude agents run warden and forge.
- **Help room:** a Claude.ai custom connector to our hosted Senti MCP lets other teams' Claude agents take help-room tickets [INTERNAL `memory/reference_hosted_mcp.md`].
- **Blocker:** "Claude in boxes" needs a key; that's a Carter item [INTERNAL].
- **Cost:** our own spend.
- **Time:** already exists.

### OpenAI
- The astra labs already use it (gpt-6-astra/Codex) [INTERNAL]. Nothing new to add.

### Google Cloud
- **Build:** an optional Gemini lab via an AI Studio key. A free tier exists [INFERRED].
- **ScienceClaw link:** its README points agents to a Gemini key [OFFICIAL https://github.com/lamm-mit/scienceclaw].
- **GCP Free Trial:** "$300 Welcome credit to spend over 90 days", and it requires a card [OFFICIAL https://docs.cloud.google.com/free/docs/free-cloud-features].
- **Time:** about 1 h.

### Edison Scientific
- **Build:** one bounded literature task on a disputed assumption, e.g. HotSpot 6 vs 7 package handling. Use edison-client (`JobNames.LITERATURE`) with a platform API key [OFFICIAL-snippet https://edisonscientific.gitbook.io/edison-cookbook/edison-client].
- **Credits** [OFFICIAL-snippet https://edisonscientific.com/news/we-raised-70m-to-accelerate-science]:
  - Academics get 650 a month; others get 10.
  - A Literature task costs 1–2 credits.
  - "API access will remain paid".
  - Current prices are unpublished [THIRD-PARTY therundown.ai, Aug 29].
- **Time:** about 1 h.
- **Value:** low. Edison isn't a judge.

### LAMM / ScienceClaw × Infinite
- **Build:** wrap our read-only oracle as a ScienceClaw skill or MCP tool, then post one verified artifact with its lineage to Infinite. This is the only route into the organizers' own ecosystem, which is what the bonus describes [INFERRED].
- **Access** [OFFICIAL https://github.com/lamm-mit/scienceclaw]:
  - API base `https://lamm.mit.edu/infinite/api`.
  - Setup registers the agent.
  - "Minimum 10 karma required to post".
- **Approval:** posting there is publication, so it needs Carter's GO.
- **Time:** 3–5 h.

### E14, Stifel, Lila, Romix, MIT SoE
- No technical integration.
- E14 matters only if Carter wants the SAFE.

---

## 4. OpenResearch compared with Jev

### 4.1 What OpenResearch is [OFFICIAL]
- **What it is:**
  - "Turn your coding agents into research agents."
  - "The local-first harness & workspace for research agents".
  - MIT license. v0.2.23 shipped Oct 31 with Linux aarch64 builds (an AppImage and a musl CLI), so it runs on the GB10.
  - Sources: https://github.com/alphaXiv/OpenResearch and https://github.com/alphaXiv/OpenResearch/releases.
- **Agents it drives:**
  - Claude Code, Codex, OpenCode, Cursor and Google Antigravity, plus any ACP agent.
  - "OpenResearch runs your existing coding agent with your own subscription or API key" (https://openresearch.sh/docs/agents).
  - Local models work through OpenCode with any OpenAI-compatible server, e.g. vLLM.
- **Features:**
  - Literature search via alphaXiv, bioRxiv and PubMed.
  - Each experiment is recorded in a local SQL database.
- **Backends** (https://openresearch.sh/docs/compute):
  - local, SSH, Slurm, Kubernetes, Ray, HF Jobs, Modal, Tinker, and managed.
  - SSH hosts need bash, tar and Python 3.6+.
  - `orx compute test ssh --host <alias>` checks a host.
- **Managed compute** (https://openresearch.sh/docs/cli, https://openresearch.sh/docs/billing):
  - Machines are rented from Lambda, RunPod, Vast and others, "billed at cost" from a prepaid balance.
  - Manual top-ups run $1–$2,000, by card, WeChat Pay or Alipay.
  - No GPU prices are published; they show live in the dashboard.
  - The $500 prize is presumably a balance credit [INFERRED].
- **Not offered:** no inference API, no hosted model and no MCP server. None is described in the docs or the README.
- **Telemetry:**
  - On by default: coarse analytics plus agent-written feedback. Usage counts feed the public /rankings page.
  - Opt out with `orx telemetry off`. Do this before it touches private repos.
- **Security:** a third-party review says that in remote mode (`orx up --remote user@host`) "the remote service binds to loopback and has no application-level authentication", so other users on that host can reach it. Use single-user hosts only. [THIRD-PARTY https://hysenlabs.com/projects/alphaxiv-openresearch]
- **Name clash:** "OpenResearcher" (arXiv 2603.20278) is a separate project. [THIRD-PARTY]

### 4.2 Can it be the front door's decision model? No.

| | Jev (front door today) | OpenResearch |
|---|---|---|
| What it is | System One model: typed Choice / Score / Noul answers with calibrated probabilities [OFFICIAL https://docs.typesafe.ai/llms.txt] | A research-agent harness; minutes-to-hours sessions [OFFICIAL; duration INFERRED] |
| Per-request API | `POST https://api.typesafe.ai/v1/systemone` [OFFICIAL] | None [OFFICIAL] |
| Latency | "70–500 ms, TypeSafe-reported" [THIRD-PARTY https://www.truefoundry.com/blog/typesafe-ai-jev]. The official docs give no figure. Our edge timeout is 2,500 ms [INTERNAL] | Not applicable per request |
| Cost | $0.042 per 1M input tokens, output free [OFFICIAL https://docs.typesafe.ai/models] | Free software. You pay the agent's model plus any managed GPUs [OFFICIAL] |
| Rate limit | Per-org tokens/s and requests/s; HTTP 429 when exceeded [OFFICIAL] | Whatever the underlying agent provider allows |
| Versions | `jev-latest` → `jev-1.14.0` (Oct 14). Our pinned `jev-1.13.0` is still active [OFFICIAL] | v0.2.23 [OFFICIAL] |

**How the front door uses Jev today** [INTERNAL H:/aid-deploy@68516469 `workers/aquarium-edge/src/index.ts`; this checkout may lag main]:
- Jev only judges the "unknown residue" (T4): unsigned or unrecognized requests.
- Two questions: `is_automated` (Noul) and `operator_hint` (Choice of 11).
- Thresholds: ≥0.75 means automated, ≤0.25 means human. It only narrows: unknown can become automation, never the reverse.
- Declared or verified agents get an optional `purpose` Choice (evaluation / integration / discovery / unknown), sampled at 25%.
- Calls run in `ctx.waitUntil`, off the response path.
- Limits: 2,500 ms timeout, ≤300 calls/min per isolate, a 10-minute cache per request shape.
- Providers, in order: the TypeSafe API pinned to `jev-1.13.0`, then Workers AI `typesafe/jev`.

### 4.3 Where OpenResearch fits instead
1. **Bake-off harness.** It runs the A/B below as recorded experiments, and its agent writes the analysis.
2. **Offline labelling.** A Claude Code session inside OpenResearch adjudicates only the cases where Jev and the challenger disagree, giving a rationale and literature context. A human then samples its labels.
3. **Help-room OpenResearch-review ticket.** Publish a "reproduce gate zero (75.48 / 115.94 C)" project that outside teams' agents can run [INTERNAL figures].
   - Team fractastical/delphi already uses OpenResearch (issue #16). They are hunting evidence for the +10 bonus (issue #41), so they're a natural reuse partner. [THIRD-PARTY https://github.com/fractastical/delphi/issues]
4. **Prize credits.** Only if we win: $500 of managed GPU time after the event.

### 4.4 A/B shadow plan. Jev stays live throughout.

**Phase 0: offline replay. No production change; can run tonight.** [INFERRED design]
1. **Export.** Warden pulls, read-only, ≥500 recent T4 and purpose records, each with the exact `jevState(...)` input and Jev's answers.
   - The cron re-judges only "unavailable" records, so the collector may not keep `state` for decided ones [INTERNAL; retention UNVERIFIED].
   - If it doesn't, rebuild `state` from the stored request features, or start Phase 1 logging first.
2. **Gold set.** About 100 probes from known clients, passed through `describeRequest` → `jevState`:
   - real browsers on consumer networks;
   - curl, python-requests and Go clients;
   - HeadlessChrome;
   - AI-crawler user agents from a datacenter.
   - Probes are real traffic and get counted; label them as ours [INTERNAL `memory/reference_aquarium_edge_review.md`].
3. **Challenger.** The Nemotron 3.5 Lightning 30B-A3B NIM (the default DGX Spark NIM) on the GB10 [OFFICIAL https://build.nvidia.com/spark/nim-llm/overview].
   - Send the same state and question texts.
   - Use one JSON schema: `{is_automated: 0..1, operator_hint: enum(11), purpose: enum(4)}`.
   - Enforce it with NIM structured generation (`guided_json`) [OFFICIAL https://docs.nvidia.com/nim/large-language-models/latest/structured-generation.html].
   - Temperature 0. Disable reasoning mode if the model has one [INFERRED].
4. **Run.** Both arms run as one OpenResearch experiment from astra's PC, with GB10 as the SSH backend.
   - For agreement, the Jev arm reuses the logged answers.
   - For latency, warden times 200 fresh `jev-1.13.0` calls, loading the key without printing it [INTERNAL `memory/reference_typesafe_jev_key_location.md`].
   - The two arms' latencies come from different hosts; state that caveat next to the numbers.
5. **Outputs.** decisions.jsonl, confusion matrices, latency histograms and token usage. A second agent checks the numbers before any of them enter the deck.

**Phase 1: online shadow. Production, so it needs Carter's GO; realistically after Sunday.** [INFERRED design]
- **Code change:** in `judgeUnknown`, call Jev and the challenger with `Promise.allSettled`, using the same `state`, separate 2,500 ms timeouts and a separate budget and cache.
  - Log `{shapeKey, both answers, both latencies, tokens}` to the collector under a shadow key.
  - Never change the `verdict`. Do the same for `maybeEnrich`.
- **Reachability:** the GB10 is LAN-only, so the edge needs a hosted challenger:
  - Nebius `nvidia/Nemotron-3_5-Lightning`: eu-north1, $0.06 / $0.24 per 1M tokens, no "JSON mode" tag [OFFICIAL via `nebius.md`].
  - build.nvidia.com: free prototyping at about 40 RPM; production needs NVIDIA AI Enterprise [THIRD-PARTY https://klymentiev.com/blog/nvidia-nim-free-credits].
  - Tunnelling the GB10 to the edge is a security change. Not this weekend.
- **Lanes:** Daybreak writes detection code, warden keys the exact head, and fable deploys from merged main.
  - CI doesn't run the edge suites, so run them on the PR head.
  - [INTERNAL `memory/reference_aquarium_edge_review.md`, rule of 10-14]
- **Privacy:** the user agent, network owner and country would go to a new processor. That's Carter's decision, and Nebius ZDR must be on.

**Gate, written down before looking at results:**
- Agreement with Jev on the 3-way decision (automated / human / ambiguous) over ≥500 distinct shapes, as a percentage and as Cohen's κ.
- Gold-set accuracy: the challenger must match or beat Jev.
- Operator-hint exact match whenever both say "automated".
- p50 and p95 latency, and the unavailable rate at 2,500 ms, no worse than Jev's.
- Cost per 1k decisions, taken from the returned `usage` fields.
- Compare thresholded decisions only. An LLM's self-reported probabilities aren't calibrated [INFERRED].
- Any swap is Carter's call after ≥7 days of Phase 1 data. Nothing changes before Sun 18:00Z.

**Cost per 1k decisions** [COMPUTED; assumes 1,000 input + 50 output tokens per decision; replace with measured usage]:

| Option | Cost per 1k decisions | Notes |
|---|---|---|
| Jev | 1M × $0.042 = **$0.042** | |
| Nebius Nemotron Lightning | 1M × $0.06 + 50k × $0.24/M = **$0.072** | |
| GB10 NIM | $0 marginal | Capacity-bound: about 80 tok/s single-stream (≈108–117 with speculative decoding) and ≈422 tok/s at 8 concurrent [THIRD-PARTY https://dev.classmethod.jp/en/articles/dgx-spark-nemotron-3-5-lightning-first-touch/] |
| build.nvidia.com | $0 | About 40 RPM [THIRD-PARTY] |

---

## 5. NVIDIA

### 5.1 At this event
- **Official** [OFFICIAL]:
  - Platform tier.
  - Three DGX Sparks.
  - The Friday ALCHEMI/BioNeMo talk.
  - Judge Fedik, who works on ALCHEMI.
- **From Source B, unconfirmed** [INTERNAL, UNVERIFIED]:
  - Three awards: BioNeMo, ALCHEMI and general.
  - NVIDIA wants "software higher in the stack".
  - A "16 H100 shared event pool".
  - Brev redemption instructions exist.
- **What other teams are doing** [THIRD-PARTY]:
  - fractastical/delphi filed NVIDIA, NIM, BioNeMo and ALCHEMI integration issues.
  - InquilineKea is using ALCHEMI for collagen chemistry (https://github.com/InquilineKea/scienceclaw-hackathon-2026).

### 5.2 NVIDIA offerings and their fit

**NeMo AutoModel**
- **Fit:** already in use. The SLAB-018 preflight used 8.24 of 60 GPU-min. Base vs adapter scored 0/20 vs 20/20 on six cases the adapter had trained on, so it shows plumbing only [INTERNAL].
- **On GB10:** yes, via the playbook. Container `nvcr.io/nvidia/nemo-automodel:26.08`, LoRA/QLoRA, 45–90 min [OFFICIAL https://build.nvidia.com/spark/nemo-fine-tune].
- **Access:** an HF token.
- **Time:** done.

**NIM for LLMs** (Nemotron 3.5 Lightning 30B-A3B, Llama 3.1 8B, Qwen3-32B)
- **Fit:** (a) an extra proposal lab with a distinct model; (b) the AIdenID challenger.
- **On GB10:** yes. About 30 minutes plus the download [OFFICIAL https://build.nvidia.com/spark/nim-llm/overview].
- **Access:** an NGC API key, free.
- **Time:** 3–5 h including the harness wiring.

**cuOpt** (LP/QP/VRP; MIP in beta)
- **Fit:** cross-solve our routing MILP. It currently runs on `scipy.optimize.milp` (HiGHS), which replaced CPLEX [INTERNAL sentilab@46791be `sundai_hotspot/tap_router.py:9,34,185`].
- **On GB10:** yes. aarch64 builds and containers exist, and the Spark porting guide lists cuOpt as supported (minimum 25.12). `cuopt_cli` reads MPS/LP files.
  - Sources [OFFICIAL]: https://github.com/NVIDIA/cuopt, https://docs.nvidia.com/dgx/dgx-spark-porting-guide/latest/porting/dependencies.html, https://docs.nvidia.com/cuopt/user-guide/latest/cuopt-cli/index.html
- **Access:** free. `docker pull nvidia/cuopt:latest-cu13`.
- **Time:** 2–4 h.

**PhysicsNeMo**
- **Fit:** a surrogate "scout" lab trained on calibrated HotSpot maps. The surrogate proposes and HotSpot verifies.
  - DeepOHeat-v1 does the same with a solver fallback, and DeepOHeat-v2 adds SA placement [THIRD-PARTY arXiv 2504.03955, 2608.16080; https://github.com/Cadence-Celsius/DeepOHeat].
  - Steady conduction has the same PDE form as Darcy flow, so the Darcy FNO example is the closest template [INFERRED].
- **On GB10:** aarch64 installs via uv [OFFICIAL-snippet https://docs.nvidia.com/physicsnemo/latest/getting-started/installation.html].
- **Access:** free.
- **Time:** 6–10 h. Risky.

**NemoGuard JailbreakDetect NIM** (`/v1/classify`)
- **Fit:** shadow-classify visiting agents' free-text purpose declarations.
- **On GB10:** hosted or NGC container. ARM64 support is [UNVERIFIED] [OFFICIAL-snippet https://docs.nvidia.com/nim/nemoguard-jailbreakdetect/latest/index.html].
- **Access:** an `nvapi-` key.
- **Time:** about 2 h, but it's a production edge change.

**NemoClaw / OpenShell**
- **Fit:** NVIDIA's sandboxed OpenClaw stack with local vLLM. ScienceClaw has an OpenClaw MCP path [OFFICIAL https://github.com/lamm-mit/scienceclaw].
- **On GB10:** yes. Express install takes 30–60 min [OFFICIAL https://build.nvidia.com/spark/nemoclaw].
- **Access:** free.
- **Time:** 2–4 h.

**Brev**
- **Fit:** registers the GB10 as a shared SSH node, which could end the "only astra's PC" bottleneck [INFERRED].
- **On GB10:** 5–10 min. No tunnels or exposed endpoints are mentioned [OFFICIAL https://build.nvidia.com/spark/brev].
- **Access:** a Brev account plus sudo on the box.
- **Time:** <1 h.

**ALCHEMI / BioNeMo**
- **Fit:** separate award paths [INTERNAL, UNVERIFIED]. There's no defensible bridge from package-level thermal to atomistic simulation within 24 h [INFERRED].
- **Recommendation:** skip.

**Warp / cuDSS GPU heat solver**
- **Fit:** it would replace the evaluator. Rule: "no evaluator version runs searches until it reproduces a published number" [INTERNAL].
- **Recommendation:** skip this weekend.

**GB10 specs** [OFFICIAL https://www.nvidia.com/en-us/products/workstations/dgx-spark/]:
- 128 GB unified memory, 273 GB/s.
- Up to 1 PFLOP FP4 (sparse).
- 20-core Arm CPU.
- Up to 200B parameters for inference.

**Our box** is a Dell Pro Max GB10 [INTERNAL]. That the Spark playbooks apply unchanged is [INFERRED].

### 5.3 What would most convince judges in about 24 h
- **The story:** "One DGX Spark runs the whole loop." [INFERRED]
  1. Labs propose layouts, including a Nemotron NIM lab.
  2. cuOpt routes the layout, and HiGHS agrees.
  3. Calibrated HotSpot verifies it.
  4. Verified corrections train the shared Qwen3-4B worker with NeMo AutoModel on the same GB10.
  5. vLLM or NIM serves the worker back into the loop.
  6. The AIdenID front door labels visiting agents, with Nemotron as its shadow decision model (offline numbers only).
- **Benchmark:** show it on micro150, which has headroom [INTERNAL `FORGE-FINDINGS.md`].
- **Per-step provenance:** container digest, model ID, GPU-min and solver objective.
- **Don't claim:**
  - cuOpt speed-ups on a small MILP;
  - a "trained" worker beyond what the evaluation shows;
  - any ALCHEMI relevance;
  - Spark-vs-cloud speed.

---

## 6. Top recommendations, ranked by win value ÷ effort

### 1. Settle eligibility and sponsor terms in person
- **Effort:** about 30 min. **Win value:** unlocks everything.
- **Owner:** Carter, or whichever human is onsite.
- **Ask the organizers** (desk, Discord or scienceclaw@mit.edu):
  - Is our team registered and approved?
  - Where do slides go?
  - Who gets which prize, and what are the "more to be announced" prizes?
  - Do sponsor prizes need separate submissions?
- **Ask NVIDIA** (Fedik or the NVIDIA table):
  - What are the Spark award categories and criteria, in writing, and is there a sponsor form?
  - Are there NIM or Brev credits?
  - Does the H100 pool exist?
- **Ask Nebius:** promo code, H100 access, any prize (`nebius.md` §3.2).
- **Ask Formlabs** (Ferguson or demo staff):
  - Can we get printer time and resin tonight?
  - Does Form Studio 1 support the Local API?
  - What are the prize criteria?
- **Ask alphaXiv:** how the $500 credits are awarded.
- **Ask E14:** do we qualify for the SAFE?
- **Ask Anthropic, OpenAI, Google and Edison:** are there event credits?
- **Blocker:** a human must be onsite. Agents may not contact anyone.

### 2. NVIDIA on the GB10: Nemotron NIM as a lab and as the front-door challenger, plus a provenance slide
- **Effort:** 3–5 h, $0. **Win value:** high. It targets the Sparks and the NVIDIA judge, and adds a distinct agent (Decentralized Agency).
- **Owners:** astra (GB10), warden (review and merge), forge (slide).
- **Steps:**
  1. Get an NGC key.
  2. Run the `nim-llm` playbook with `nemotron-3.5-lightning-30b-a3b` and record the image digest.
  3. Smoke-test `/v1/chat/completions` with `guided_json`.
  4. Add lab `gb10-nemotron` to the SLAB-052 harness. If the SLAB-041 freeze fixed the lab list, run it as a separately labelled exploratory arm [INTERNAL `nebius.md` §3.1].
  5. Run it on micro150.
  6. Reuse the endpoint for §4.4 Phase 0.
- **Blockers for Carter:**
  - Create or approve the NGC account.
  - The GB10 is reachable only via astra; Brev registration would need his Brev account and the box owner's consent.
  - Adding a lab after the freeze needs +1s.

### 3. cuOpt cross-solve of the routing MILP on the GB10
- **Effort:** 2–4 h, $0. **Win value:** medium-high. It's NVIDIA software "higher in the stack" with a built-in correctness check, which helps Execution & Validation.
- **Owner:** a box ticket via astra and warden.
- **Steps:**
  1. Export the objective, constraint matrix, bounds and integrality from `tap_router.py` to MPS.
  2. On the GB10, run `cuopt_cli` in `nvidia/cuopt:latest-cu13` on both reference layouts.
  3. Record status, objective and time for both HiGHS and cuOpt.
  4. Accept only if cuOpt reaches the optimum HiGHS recorded in PR #57 (16,426 / 67,686 mm) [INTERNAL].
  5. HiGHS stays the reference, since cuOpt's MIP is beta [OFFICIAL].
- **Blocker:** GB10 access only.

### 4. Formlabs "thermal relief" print through the PreForm Local API
- **Effort:** 2–3 h plus print time. **Win value:** medium-high. Formlabs judge, the printer prize, "closing the loop between simulation and matter" (A·03), and a tangible demo.
- **Owners:** forge (STLs from the gate-zero-calibrated maps, same z-scale) and warden (PreFormServer on the Windows workstation).
- **Steps:**
  1. Log each API call as an agent action in the lab feed.
  2. Print onsite, starting by about Sun 08:00Z [INFERRED; print time UNVERIFIED].
  3. Caption it as a physical rendering of the data, not a thermal test.
- **Blockers for Carter:**
  - Printer and resin access, and picking up the print in person.
  - Downloading PreFormServer may need a sign-in [UNVERIFIED].
  - Gate zero must pass first.

### 5. OpenResearch where it actually fits: the bake-off harness and the help-room ticket, not a Jev replacement
- **Effort:** 1–2 h, $0. **Win value:** low-medium. It covers Carter's question, makes alphaXiv usage visible, and could earn the bonus through reuse by delphi.
- **Owners:** astra and forge.
- **Steps:**
  1. Install `orx` v0.2.23 on astra's PC or the GB10, then run `orx telemetry off`.
  2. Create the "front-door decision-model bake-off" project, i.e. Phase 0 of §4.4. Jev stays live.
  3. Publish "reproduce gate zero" as the help-room OpenResearch-review ticket.
- **Blockers:**
  - Carter accepts that OpenResearch is a harness, not a model.
  - Warden's read-only collector export.
  - The Jev key stays under the key-location rule.

### Next tier (not in the top 5)
- Nebius cloud labs (`nebius.md` #1). Needs an account and a card.
- ScienceClaw/Infinite skill plus one artifact post. High upside for the bonus, but it's public and needs Carter's GO.
- PhysicsNeMo scout lab.
- NemoGuard shadow on agent declarations. Production edge change, Daybreak's lane.
- Edison literature task.
- Gemini lab.

**Carter-only decisions:**
- Registration.
- The onsite asks in #1.
- NGC, Brev and Formlabs accounts (or delegating them).
- Whether sponsors may be named on the deck and on sentilab.aidenid.com.
- Any production front-door change and the new data processor (Phase 1).
- Whether to pursue the E14 SAFE.
