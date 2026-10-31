# SLAB-037a integration boundaries

- The provisional sequential margin is a diagnostic parameter. It is not PLAN
  5.3's delta_min plus numerical uncertainty bounds and gives no physical signoff.
  A fresh-process repeat is labeled **same-solver reproduction**.
- `contracts/` is imported byte-for-byte from the merged reviewed patch; its
  `HASHES.txt` is checked. The service is Python-only by Warden's instruction.
  `sentilab_core/projection.py` maintains the emitted event subset; CI compares it
  to the exact JavaScript reference. Unsupported evidence workflows report an
  explicit projection error and are not silently approximated.
- While the corrective v0.5 contract is landing, the writer uses v0.4 plus the
  agreed pre-hash validation and duplicate-group fixes. No v0.4 reference file is
  edited. Binding to the reviewed v0.5 manifest remains an upstream handoff.
- Baseline operators are imported, but scheduling uses recorded per-proposal
  deterministic substreams, one initial layout, and four interleaved arms. This
  is a live integration baseline, not a replay of the earlier equal-budget
  scientific experiment or an LLM benchmark.
- This slice owns the producer/API. Forge owns the deploy-time browser trust pin
  and live page integration. The read-only API and every emitted event carry
  **AI off** and **provisional margin** labels. No public deployment is included.
- The core signer is one injected service argument. Production provisioning and
  trust/grant enforcement remain the SLAB-040 integration seam; the explicit
  local demo signer exists only in RAM. No signer material is given to workers.
- The imported HotSpot worker currently returns hashes of its raw input files
  and removes its temporary workspace. Raw-output retention awaits the separately
  owned oracle capture seam; this slice does not claim retained raw outputs.
