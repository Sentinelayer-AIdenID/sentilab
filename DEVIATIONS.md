# SLAB-037a integration boundaries

- The provisional sequential margin is a diagnostic parameter. It is not PLAN
  5.3's delta_min plus numerical uncertainty bounds and gives no physical signoff.
  A fresh-process repeat is labeled **same-solver reproduction**.
- `contracts/` is imported byte-for-byte from the merged reviewed patch; its
  `HASHES.txt` is checked. The service is Python-only by Warden's instruction.
  `sentilab_core/projection.py` maintains the emitted event subset; CI compares it
  to the exact JavaScript reference. Unsupported evidence workflows report an
  explicit projection error and are not silently approximated.
- The writer emits reviewed v0.5 envelopes; compatible v0.4 history still verifies.
  Input caps, iterative canonical-size accounting, canonical-identical duplicates,
  conflict freezing and bounded JSONL pages are implemented. The native verifier
  keeps stricter existing run/actor/event field and role checks, and reports one
  diagnostic error rather than the reference's complete reason-code list.
  An oversized raw ledger line is represented in the feed by a malformed `null`
  line, preserving a frozen prefix without echoing unbounded input. Replay files
  over 64 MiB fail closed. Legacy sequence groups exceeding a page cap return
  413; append-row cursor pages preserve all evidence and remain within the caps.
  Append cursors assume append-only storage, include late conflicting appends,
  and are not snapshot integrity proofs for externally rewritten files.
  Forge owns the client-clock LIVE/progress tracker and the browser transport
  consumer; those are not implemented by this producer change.
- Baseline operators are imported, but scheduling uses recorded per-proposal
  deterministic substreams, one initial layout, and four interleaved arms. This
  is a live integration baseline, not a replay of the earlier equal-budget
  scientific experiment or an LLM benchmark.
- This slice owns the producer/API. Forge owns the deploy-time browser trust pin
  and live page integration. The read-only API and every emitted event carry
  **AI off** and **provisional margin** labels. No public deployment is included.
- The core signer is one injected service argument. The production factory now
  uses SLAB-040's shared service loader and public-key registry. Deployment owns
  seed provisioning; the explicit local demo signer exists only in RAM. No signer
  material is given to workers.
- The imported HotSpot worker currently returns hashes of its raw input files
  and removes its temporary workspace. Raw-output retention awaits the separately
  owned oracle capture seam; this slice does not claim retained raw outputs.
