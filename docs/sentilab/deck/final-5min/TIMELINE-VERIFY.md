# Five-minute deck: every dated line, figure label and number checked against the record

This deck replaces the three-minute deck for the five-minute slot. The three-minute deck stays in `../final-3min/`
byte for byte (the tests pin every file), together with its own `TIMELINE-VERIFY.md`, which still covers the 12:43 to
16:40 lines and the "no person asked" check. The records it lists are reused here. Root's three corrections to that
deck (PR #74 at 16b6c37a: the corrected review tally, the completed re-derivation, the outside finite-element result)
are applied in this one; the three-minute artifact keeps them as published at 00:12 UTC.

Checked between 2026-11-01 00:40 and 02:24 UTC. The reviewed cutoff in `FINAL.json` and the export's cutoff are both
02:26, after a last sweep of both rooms at 02:24 found no new consent answer and no new fact. Times are UTC. The deck shows no room or message numbers, because the public-render rules forbid them; they
are here instead. Rooms: `608657e4` is the team room and `32a841e5` the hackathon help room.

## Timing (root, team room 57481, 01:33:52)

- The talk before the door is counted at 150 words a minute. With its transitions it must fit a 180 s cap.
- The door slide's spoken lines count inside the 120 s live-demo clock, not against the talk.
- The 300 s slot is the cap. `scripts/build-deck-final.mjs` refuses any build that breaks one of these, and prints the
  slower 2.2 words a second beside it.

| | Words | At 150 wpm | At 2.2 w/s |
|---|---:|---:|---:|
| Talk, slides 1 to 7 | 383 | 153.2 s | 174.1 s |
| Transitions | | 15.0 s | |
| Talk with transitions, cap 180 s | | 168.2 s | 189.1 s |
| Door lines, slide 8, inside the demo clock | 47 | 18.8 s | 21.4 s |
| Left for the live demo, of 120 s | | 101.2 s | 98.6 s |

At the slower pace the talk would run 9.1 s over the cap, so the presenter should rehearse at about 150 words a minute.

## Figures

aneta-claude's figures, applied in order: v1 (team room 57446, 01:02:38, `sentilab-deck-figures-v1.zip`, 211,191 bytes,
sha256 `c956836e…`), v1.1 (57451, 01:07:30, 15,868 bytes, `1a092339…`), v1.2 (57470, 01:27:20, 88,614 bytes,
`f1217061…`, members under `deck-figures/`), v1.3 (57475, 01:31:02, 20,712 bytes, `3eac9728…`) and v1.4 (57516,
01:58:54, 149,918 bytes, `1b351835…`, with root's 57501 and 57511 applied) and v1.5 (57538, 02:16:19, 22,400 bytes,
`9281f7a2…`, ScienceClaw's requested wording). The archives, the
overlaid tree and its sha256 list are kept in the evidence folder for this head. `make_figures.py` and `render.mjs` were
never run. Every SVG was scanned for script, foreignObject, event handlers, external references and active elements:
none was found, so nothing was stripped, and the build refuses any figure that holds one. The embedded heat maps are
PNG data inside the SVG. Each figure is shown as an image, so nothing in it can run.

| Figure | Source sha256 | Slide | Edits the build makes (exact text runs) |
|---|---|---|---|
| fig1-same-chips | `7072cc76…` | 1 | "Ascend 910 reference" to "Layout A reference" (the shared public-render rules forbid that product name) |
| fig2-stack | `a430ba49…` | 2 | none (v1.4 adds the separately labelled layer-maxima panel) |
| fig4-timeline | `8c478904…` | 3 | team labels, by consent (below) |
| fig3-agreement | `4179ee6d…` | 4, with the recorded result only | "Ascend 910" to "Layout A"; team labels, by consent |
| fig5-waffle | `2edb9c37…` | 5 | none |
| fig6-teams | `14f0bcda…` | 6 | team names, by consent; the InquilineKea card's two lines to "Built on request; it ran through" / "the open-source ScienceClaw" (root, 57540; short enough for the card); ScienceClaw's line to "“your matchmaking”; it used" (it ran into the card edge, aneta 57541) |
| fig2b-profile | `f052040c…` | backup B5 | "Ascend 910" to "Layout A" |

The root `aria-label` of every figure is replaced by this deck's own reviewed text, so no name or product rides in an
attribute. The tests check that the served copy differs from the source only in those text runs and that label.

Root's four repairs from team room 57456 (01:13:28), all binding:

1. **fig2's caption** uses the CPU-DRAM layout's spreader-to-sink drop, 4.04 K in 6.0 and 141.77 K in 7.0, and says
   "the same x/y grid index through the modeled layers", "modeled nodes, not a copper layer". Layout A's 1.24 K and
   55.31 K are on backup B5 (fig2b) and B7.
2. **Slide 1** keeps the chip-layer grid maxima, 119.07 C and 240.53 C, apart from the frozen gate statistic,
   "the maximum native block output under centre mapping", 115.93 C and 232.67 C. It says that in 7.0 that maximum is
   a substrate block, not a chip. aneta's v1.2 fig1 already reads "Frozen gate statistic".
3. **No "isolates one term", no "until the one-change test runs".** Slide 2 says "This localizes the difference; it
   does not by itself show a single cause." The detailed-3-D-off values are the reproducing team's, "as reported by
   them". aneta's layer-peak reading (57483) stayed off the slides until root checked it (57511); only the panel and
   sentence root gave a scoped +1 are used (see Layer maxima below).
4. **Conditional stage text.** The door's notes begin "If the door is open". The seeded-defect card says "It has not
   run yet; when it does, its result goes here, whatever it shows." The staging status says the door, queue and 3D
   view are being built and tested. Backup B7 scopes the 23.0 CPU-seconds to the validation container only, not the
   cost of the build, the models or the project.

Root's QA refinement in 57481 and the ScienceClaw timeout wording in 57501 apply to aneta's QA.md for the presenter.
That file is not part of this deck.

## Figure times (fig4) and stated durations

| Label | Record | Author | Posted (stated) |
|---|---|---|---|
| 12:43 | team seq 56598 | human-mrrcarter | 12:43:33.374 |
| 13:15 | team seq 56645 | claude-warden | 13:15:38.133 |
| 13:28 | team seq 56654 | gpt-astra-carter | 13:28:00.936 |
| 14:26 | team seq 56739 | aneta-claude | 14:26:32.762 |
| 14:42 | team seq 56764 | gpt-astra-carter | 14:42:11.768 |
| 14:53 | team seq 56778 | gpt-astra-carter | 14:53:42.106 |
| 15:56 | team seq 56870; seq 56865 | claude-warden | 15:57:47.392 (states the halt at 15:56:58.678); proposal 15:52:12.966 |
| 16:40 | team seq 56927 | gpt-astra-carter | 16:43:24.137 (states the reads at 16:40:28) |
| 22:22 | help reply 9de2e042 to seq 57170 | pocket-forge | 22:22:08.352: "the TAP-2.5D case is up … our own evaluator's numbers aren't included" |
| 23:01 | help seq 57312 | delfie-claude | 23:01:16.766 |
| 23:44 | team seq 57377 | claude-warden | 23:45:43.792 (states the run 23:41 to 23:44) |
| 00:03 | help reply 161c27f0 to seq 57170 | feagent-codex | 00:03:07.209 on 1 November |

The build checks each label against its records and recomputes every stated duration from them: "32 min" (12:43:33 to
13:15:38, 32.1 min), "Under 5 min" (15:52:12.966 to 15:56:58.678, 285.7 s), "39 min" (22:22:08 to 23:01:16, 39.1 min)
and "1 h 41" (22:22:08 to 00:03:07, 101.0 min).

## Values in fig3, slide 4

- Paper 75.48 C and 115.94 C (TAP-2.5D, DATE 2021). Our run 75.48 C and 115.93 C in 6.0, 123.42 C and 232.67 C in 7.0
  (team seq 57377), re-derived independently from the signed raw outputs (team seq 57394, 00:05:37).
- The reproducing team, as reported (help seq 57312): 75.48 and 115.94 C in 6.0, 123.42 and 232.67 C in 7.0; with
  `-detailed_3D off`, 75.37 and 115.29 C in both versions.
- The finite-element team, as reported (help reply 161c27f0): 78.060 and 122.252 C; verified from its saved results by
  a second reviewer (team seq 57412, 00:18:39).
- Our own finite-element solve: 78.0423354 and 122.2078371 C on the finest meshes (help seq 57329, 23:08:26).

## fig6, what travelled between teams (help room, to 00:37 UTC)

| Card | Record |
|---|---|
| Both versions on our case, 39 min after it went public | help seq 57312, 23:01:16 |
| Separate solver on our case, in 1 h 41 | help reply 161c27f0, 00:03:07 |
| ScienceClaw: "your matchmaking"; it used our review to fix its package | help seq 57328, 23:08:23 ("What did help was your matchmaking", when nothing technical had gone in yet); help seq 57532, 02:09:48: since then, chatgpt's review of its c11ac67a package helped it fix the convergence row and add input guards (also 57350, 23:22:54). The two statements keep their own times; the card's snapshot runs to 02:09 |
| "Thanks, very useful" | help reply aae908b2 to seq 57188, 21:13:28, quantumswarms-claude |
| "Yes, yours helped." Then it corrected a claim of ours | help replies 028f09e8 (00:08:14) and 37eb0808 (00:04:12) to seq 57270, kiln-claude |
| Built on request; it ran through the open-source ScienceClaw | help reply 8dd4609d to seq 57005 (23:53:05); team reply 289bcfef to seq 57444 (01:25:26), our own proof run. "ScienceClaw" here is the open-source lamm-mit/scienceclaw platform, which the participant team ScienceClaw had no part in (its own words, 57532; root, 57540). The requester has not confirmed adoption |
| Asked for it. Use not confirmed yet | help reply 88926f8c to seq 57007, 21:54:20, human-pixlram |
| Evaluation notes between two other teams | help reply 06911e25 to seq 57007, 20:23:05, axis-claude |
| Blind panel test, running | help reply 9e9e733a to seq 57262, 00:37:12, feagent-codex |

The FEAgent connector stays "running": ScienceClaw confirms the blind panel run has started, with no results (57532). Any print-bench results are separate from this deck's simulated evidence and are not shown.

Not re-read here: the "glad to have another agent on it" quote on one unconfirmed card, and the "physics anchors" link
(aneta cites help seq 56949). Both are aneta's, from her source table. Root checked v1.3 in 57501.

## Outside teams and consent

One consent is on record: **ScienceClaw**, help seq 57532 (02:09:48, scienceclaw-claude: "yes, the slides may name our
team"), confirmed by root reading the full event back (team room 57540, 02:16:52). Its flag is
`"32a841e5 seq 57532 at 2026-11-01T02:09:48.572Z"`. aneta asked FEAgent (help 57461), Delfie (help 57462) and the other
six teams (help 57474). No other answer had arrived by the final sweep, so every other team reads "an outside team",
or "a second outside team" for the next one on the same slide. fig3 reads "Outside", and seven fig6 cards read "An
outside team". Slide 6's notes name ScienceClaw for its own acknowledgment and use root's words for the platform run:
"Our rigidity skill ran through the open-source ScienceClaw registry and executor." Backup B12 lists the named team. The build refuses any slide, note, figure text or label that still holds an unconsented name.
The exported PDF's text is checked the same way. The event is the ScienceClaw hackathon, and its name in the header is
the event's, not a team's.

Earlier drafts said our values reached the finite-element team "from 23:07". The record shows otherwise. The 22:22 case
post withheld our numbers. Our team's finite-element values first appeared in the shared help room at 23:04:27 (help
seq 57323, case A coarse) and 23:08:26 (seq 57329, both cases). They were sent to that team directly at 23:18:03 (seq
57344). Backup B12 now says this.

## The rest, with their records

- **Review line** (slide 5 and B3): the author's corrected wording, team seq 57392 (00:03:42), attributed. The approver
  confirms at least 4 as misses (warden's reply 5de985fb, 23:56:30, and aneta's 83571ec9, 00:00:09, to seq 57388).
- **Seeded-defect test**: designed in team seq 57379 (23:46:45) and contracted in 57427 (00:38:39); not run as of the
  cutoff.
- **By the numbers** (slide 7): the quant pack's `DECK-NUMBERS.md`, sha256 `bcafa3f0…`, kept in `quant/`. All 23
  entries of the pack's `SHA256SUMS` were verified. Its entries 1, 2, 7 and 8 are shown with their MEASURED or ESTIMATE
  labels, which the build reads from the pack. aneta objects to any savings estimate on a main slide (team seq 57405).
  The coordinator's brief asked for it labelled ESTIMATE with its range.
- **GB10** (backup B10): team seq 57413, 00:19:45. The product name is withheld by the public-render rules.
- **Live demo** (slide 8): Carter's seq 57411 and reply dd15a6de; aneta's 57414; the fallback ladder in 57422; staging in
  57436; root's conditional wording in 57456. Root's 57438 keeps real ENGRAM integration as a separate acceptance item.
  The shipped agent view is the custom JSON, so the diagram's "ENGRAM view" is the brief's name for that step.
- **PR states** (backup B11): re-read with `gh` at export time (02:25) for this export; the time is printed on the slide.
- **Layer maxima** (backup B6): root's scoped +1 (team room 57511, 01:51:42) for aneta's table (57483, 01:37:56),
  checked by root against the four 64 by 64 grids, both of our full-precision FE fields and the finite-element
  team's pinned summary. Root's sentence and caption are used word for word, with the finite-element team's name
  behind its consent flag ("ours and an outside team's"). The independent-peak 3.25 K and 141.84 K stay apart from
  slide 2's same-index 4.04 K and 141.77 K. The chip-minus-sink line says "within 0.44 K". The build recomputes that
  line and the sentence's "about 1.30 K and 4.20 K" from the table's rows. The full sentence is on backup B6 only:
  spoken, it would take about 18 s, and the talk with transitions already uses 161 s of its 180 s. aneta's v1.4 fig2
  (team room 57516) draws the same CPU-DRAM values as a separately labelled panel on slide 2 (3.25 K, about 4.20 K
  and 141.84 K). Slide 2's footer gives root's caption for it, word for word, after "Panel at right:". The speaker
  notes do not mention the panel, so the talk stays at 146 s.
