# SLAB-037a integration boundaries

- The provisional sequential margin is a diagnostic parameter. It is not PLAN
  5.3's delta_min plus numerical uncertainty bounds and gives no physical signoff.
  A fresh-process repeat is labeled **same-solver reproduction**.
- `contracts/` is imported byte-for-byte from the merged reviewed patch; its
  `HASHES.txt` is checked. The service is Python-only by Warden's instruction.
  `sentilab_core/projection.py` maintains the emitted event subset; CI compares it
  to the exact JavaScript reference. Unsupported evidence workflows report an
  explicit projection error and are not silently approximated.
- The writer emits reviewed v0.5 envelopes. The native verifier enumerates only
  `view-envelope/0.4` and `view-envelope/0.5`; every other version fails closed.
  `verify()` and `read_prefix()` can pin `version=` to either profile. Both use
  the same hash/signature format and the stricter native checks below. Signed
  history keeps its original version and bytes; the exact v0.4 reference is used
  for the retained history, which the v0.5-only reference correctly rejects.
  Native historical compatibility does not claim v0.5-only browser conformance.
  JSONL rows are strict UTF-8; a leading BOM on any row is rejected by parsing,
  while U+FEFF inside a JSON string is valid. UTF-16/32 auto-detection is disabled.
  The raw feed preserves rejected bytes. Consumers must preserve a BOM when
  decoding (JavaScript `TextDecoder('utf-8', {fatal:true, ignoreBOM:true})`), then
  pass that text to the exact reference; cursor hashes use original raw bytes.
  Input caps, iterative canonical-size accounting, canonical-identical duplicates,
  conflict freezing and bounded JSONL pages are implemented. The native verifier
  keeps stricter existing run/actor/event field and role checks, and reports one
  diagnostic error rather than the reference's complete reason-code list.
  An oversized raw ledger line is represented in the feed by a malformed `null`
  line, preserving a frozen prefix without echoing unbounded input. Replay files
  over 64 MiB fail closed. Legacy sequence groups exceeding a page cap return
  413; append-row cursor pages preserve all evidence and remain within the caps.
  Append cursors include late conflicting appends and bind consumed physical
  bytes through a required SHA-256 boundary. Changed/truncated prefixes return
  409 and require replay from zero. This transport extension is coordinated
  with Forge pending a versioned cursor contract; frozen v0.4/v0.5 bytes stay
  unchanged. Clients must degrade unsupported row cursors to STALE, never
  advance LIVE/current claims from a sequence-only fallback.
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
