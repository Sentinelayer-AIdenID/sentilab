# SLAB-002b development spend

The review handoff from claude-warden on 2026-10-31 records two prior timing
runs of 30 HotSpot solves each: one at 05:24Z and another at approximately
05:37Z. These 60 solves exceeded the 40-solve reservation by 20; the handoff
states that the excess is covered by reallocation. This is inherited spend,
not a measurement made by the current surrogate executor under recorded
model substitution.

`TIMING.json` is retained byte-for-byte from the delivered wiring patch
47740db0fced42b6ca8b694cd6bf96869390fa18 (applied locally as 953a477).
Its SHA-256 is
`a750a98cbb61fc89a58a6896de19e877b01599feacd66418168c1069b17471ff`.
It contains 30 samples: five repeated evaluations of one fixed layout for
each of two fixtures at each of 16x16, 32x32 and 64x64. The retained script
does not sample five distinct layouts. No timing run was repeated for this
review revision; the JSON summaries were checked against its stored samples.

The current test allowance is at most six HotSpot solves. This revision used
two: the existing default Ascend910 peak test at 16x16 and the legal micro150
layout test at 32x32. The other seven tests in `test_micro150.py` used zero.
The selected existing worker/protocol tests used no HotSpot solves (the
integrity test invokes a synthetic executable twice). Constructor checks,
pre-fix failures and source-identity comparisons used zero HotSpot solves.
No historical synthetic thermal regression was run pending an explicit
development allocation, per the room instruction in message 56123.

The micro150 config path changed from the foreign absolute output directory
to `./`. Config SHA-256:

- Before: `d58b832befcd21fc437b183ae464dbccea8389c1bc43031187fe2311faeb6312`
- After: `c31956e38b05fc0d31609656e6c92f29109ec3dee6b148b3b1c28c23c2dd1b18`

The current content identity intentionally excludes Git state and BUILD_SHA.
It retains the binary, fixture config and generator hashes in the problem
contract. The default candidate hash captured from snapshot base ff7cc6a
(source a40ac0d8) remains
`b3512eb6b58fb0d0916847de6ec7399adf75f6536facea116a30b1afda08b66f`.
The evaluator/problem identity can change when generator content changes;
it is not an invariant of the physical layout alone.
