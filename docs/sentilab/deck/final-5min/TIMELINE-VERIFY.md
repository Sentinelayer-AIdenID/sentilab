# Five-minute deck: every dated line, figure label and number checked against the record

This deck replaces the three-minute deck for the five-minute slot. The three-minute deck stays in `../final-3min/`
byte for byte (the tests pin every file), together with its own `TIMELINE-VERIFY.md`, which still covers the 12:43 to
16:40 lines and the "no person asked" check. The records it lists are reused here. Root's three corrections to that
deck (PR #74 at 16b6c37a: the corrected review tally, the completed re-derivation, the outside finite-element result)
are applied in this one; the three-minute artifact keeps them as published at 00:12 UTC.

Checked between 2026-11-01 00:40 and 03:40 UTC. The reviewed cutoff in `FINAL.json` and the export's cutoff are the
same minute, after a last sweep of both rooms found no new consent answer. This is a review export of the plain talk;
the room's adversarial review (team room 57558) closed at 03:30. Times are UTC. The deck shows no room or message numbers, because the public-render rules forbid them; they
are here instead. Rooms: `608657e4` is the team room and `32a841e5` the hackathon help room.

## Script v3.1, the main talk in this export (aneta's 3+2 arc, team room 57701)

The ten main slides follow script v3.1 (`PLAIN-SCRIPT.md`, sha256 `48b68cd6…`), which the coordinator assembled from
aneta's arc (57701) with root's corrections (reply 9d18d50c to 57701, 05:15:26) and chatgpt's (05:14:17); v3.1 takes
aneta's two wording fixes (57719, agreed by root): slide 2's punchline "Unchecked grader → confident agent." with its
spoken line, and slide 9's "the test case is public, so you can rerun it" in place of "the receipts are yours to verify". Each slide is
built from its "Screen:" line, one idea and one picture, short labels and big numbers; its notes are its "Say" text,
word for word, and the tests compare both with the script. Slide 1 opens with its top line rather than a heading; every
other slide shows its heading as its title. The v2.5 export (commit 8e998d8b, cutoff 05:02) is the fallback.

The slot is a build flag: `--slot 3+2`, the default and the talk Carter confirmed (5 minutes per team, 3-4 of talk and
1-2 of demo, team room 57411, re-read by root), or `--slot 3total`, which speaks script v3.1-short
(`PLAIN-SCRIPT-SHORT.md`, `3aed8f61…`) over the same screens, with slides 3 and 8 moved to the head of the backup
and a 60 s demo. Script v3.1-short carries v3.1's two wording fixes: slide 2's spoken line, and the lesson's (seventh
in the short cut).

| Slot | Talk words | 150 wpm, with 15 s transitions | 135 wpm | Talk cap | Door words (LIVE / RECORDED) | Demo clock |
|---|---:|---:|---:|---:|---:|---:|
| 3+2 | 364 | 160.6 s | 176.8 s | 180 s | 79 / 32 | 120 s |
| 3total | 211 | 99.4 s | 108.8 s | 120 s | 49 / 30 | 60 s |

| Slide | Picture | What the build checks |
|---|---|---|
| 1 | two bars to scale, "119°C" and "241°C" | the values are the reviewed chip-layer peaks 119.07 and 240.53 stated in B1's caption, rounded |
| 2 | the cropped 3D still, "simulated, not silicon", beside the three steps and the punchline | the crop's pixels (below) |
| 3 | two person cards and five role chips | names stay off: the public-render rule refuses a person's name on a slide, and `namesOnStage` needs every name before it can be on. The script's spoken line names the co-lead in the notes only |
| 4 | three report cards and "Together: a suspect in 32 minutes." | 13:06 is root's local freeze (stated in reply 9d18d50c to 57701; the report was posted at 13:08:41, seq 56630); 13:15 are seq 56643 (13:15:06) and 56645 (13:15:38); the 32 minutes are recomputed from seq 56598 (12:43:33) to 56645 |
| 5 | the orange statement | the records of the proposal (56865), the two agreements (reply 67f2695a, 56866), the halt (56870, stated 15:56:58.678) and the withdrawal (56906, 56927); "under 5 minutes" recomputed |
| 6 | plain2 v1.11 and the reported line | the caption credits "as reported by Delfie (delphisci team)" |
| 7 | plain3 v2 and the two-row test | each row is the recorded result (75.48 and 115.93) against its published reference (75.48 and 115.94) |
| 8 | 8 · 3 · 2 · 3, and two cards | the help-room records behind fig6 v1.15 (57312, 161c27f0, 57532, 57666, 9e9e733a); no leaderboard claim |
| 9 | the closer, the check line, plain6 v1.15 | |
| 10 | LIVE: the address, its QR code and three steps; RECORDED: real recorded runs with their dates, or "No recorded runs yet", beside the cropped still | the QR code (below); each recorded run needs its room record before the cutoff. No real door run has been recorded, so RECORDED shows the empty state |

The QR code (`qr-sentilab.png`, 592x592, `f62a077a…`) encodes exactly `https://sentilab.aidenid.com`: made with qrcode
1.5.4 (error correction M), then read back from its own pixels by jsQR 1.4.0, and read again from the rendered LIVE slide
at 1920x1080 and 1280x720. The evidence folder holds the scripts and their output.

The answer pages (B26 onward) carry aneta's corrected answer sheet (team room 57700, 05:06:22; root's acceptance in reply
9d18d50c to 57701) word for word, plus the coordinator's "unvalidated" answer. Its brackets are filled only with what is
true now: our own run of the one-step change has not run (its grant deadline is Mon 11-02 06:00Z), the 25-layout test
has not been measured, and the note to the authors is drafted, not sent. On these pages only, "bug" may appear, as the
question and as Delfie's attributed word, and the one cost figure, "about $6,400", may appear; the build refuses both
everywhere else. The sheet's reading notes ("learn the first line…", "please don't say…") are in SCRIPT.md, not on a
slide. The figures the v2.5 talk carried that left the main deck (plain1, plain4, plain5, fig6) are backup slides with
their v2.5 captions.

## Root's P2s on v3.1 (team room, reply to 57558 at 06:48:17Z)

Root read all 43 pages of the 06:20 PDF (sha256 `df7153dc…`) and asked for six ordinary follow-ups. This export makes
them, at the same 06:20 cutoff, with no other change:

| # | Where | Now | Was |
|---|---|---|---|
| 1 | slide 6, the line | "Delfie reports that changing this modeled link removed most of the gap; ScienceClaw reports reproducing it." | "Delfie changed only that step: most of the gap went away. ScienceClaw got the same." |
| 1 | slide 9 (plain6), the outside values | "Same numbers reported, each on its own machine"; "as Delfie reports; ScienceClaw reports it too" | "Same numbers, each on its own machine"; "as Delfie reports; ScienceClaw re-ran it" |
| 1 | slide 7 (plain3), the same line, for consistency | "as Delfie reports; ScienceClaw reports it too" | "as Delfie reports; ScienceClaw re-ran it" |
| 2 | slide 7 (plain3) | "Two separate finite-element implementations: 122" | "2 independent solvers: 122" |
| 3 | slide 9 (plain6) | "0 verified better layouts on our board so far. That's the challenge" | "0 verified better layouts so far. That's the challenge" |
| 4 | B3 (fig4), 14:26; B10, 14:26; B3's notes | "Another person's agent models it from public code" | "Third agent models the effect from public code"; "A third agent, run by another person under a separate account, …"; "A third, run by another person, …" |
| 5 | slide 1, the top line | "One published chip design · same input files · same 3D mode · two HotSpot versions" | the same without "· two HotSpot versions" |
| 6 | the 18:45Z live check | not in the PDF or the speaker script; this file's v2.5 note now names the current plan | "warden's 18:45Z production readback" |

The figure changes are declared text edits on aneta's files (`edits` in `FINAL.json`, each with its reason); plain6 is
no longer served byte for byte, so its accessible label is this deck's own, rewritten to match. The heading of slide 10
in `PLAIN-SCRIPT.md` (script v3.1 as sent) still says "warden's 18:45Z read-back picks the variant"; it is not rendered.

## The v2.5 plain talk, now the fallback (Carter, team room 57563, 02:51)

The nine main slides follow the coordinator's plain-language script v2.5, committed byte for byte as `PLAIN-SCRIPT.md`
(sha256 `cd1cb889…`). It went v2, v2.1, v2.2, v2.3 and v2.5, with astra's truth fixes, aneta's plain charts and truth check
(team room 57605), chatgpt's non-specialist pass (57558) and Delfie's one-change result (help seq 57644). v2.5 names
HotSpot on slide 2, gives slide 3 Delfie's change and ScienceClaw's re-run in place of the mode-off line, and counts
slide 7's teams as three checked, two other help, three unconfirmed. Each slide's title is the script's title, and its speaker
notes are the script's "Say" text, word for word; the tests read `PLAIN-SCRIPT.md` and compare. One picture per slide.
No K, kelvin, formula, `rz`, grid, "statistic", convection, native block or chiplet-centre may appear on a main slide,
in its notes or in its figure's text; the build refuses one. Every slide of the earlier five-minute deck follows as
backup B1 to B21, with its text and notes unchanged: the tests compare each one with a build without the plain talk.
The questions page is B22.
Where the sections below say "slide 1" to "slide 8", they mean that deck's slides, now B1 to B8.

| Slide | Title | Picture | Caption |
|---|---|---|---|
| 1 | AI agents arrange chips. Software predicts the heat. | the package render cut from our 3D view (below), `package-render-35323889.png` (`7ea5c232…`) | the coordinator's: "Simulated heat map of the published reference design. Simulated, not silicon." |
| 2 | Same design, same files: 119 °C or 241 °C? | plain1 v1.10 (`9d1e00ca…`) | CAPTIONS.md plain1, without "on a 64 by 64 grid", "point" for "cell", and the coordinator's "HotSpot 6.0 and 7.0. Design from TAP-2.5D, DATE 2021." |
| 3 | The answers split at one step: lid to cooler. | plain2 v1.11 (`1b7f851e…`), with root's "In the model: lid to cooler" and "Separate check: hottest point in each part" | v1.9 plain2, with "position" for "grid position", "Separate check" for "Independent check" (the figure's own label since v1.11) and "from two finite-element solvers and the simulator" for "finite element nodal versus HotSpot grid readouts"; then the mode-off result, "as reported by Delfie (delphisci team)" |
| 4 | The agents found it, and stopped our own run. | plain4 v1.15 (`03678891…`), one lane per actor; each of its 13 event times has a claim whose room records carry that minute, and "32 min", "39 min" and "1 h 41" are recomputed from them | v1.15's plain4 footer, as written |
| 5 | We set the bar first. It passed. | plain3 v1.15 (`e4a79736…`, unchanged from v1.14): adds Delfie's one-step change, as they report it, and both published designs zoomed in | v1.15's plain3 footer, plus "Delfie's and ScienceClaw's values are as reported by them." |
| 6 | A second agent catches what the first approved. | plain5 v1.15 (`c0773bfb…`), served with this deck's own label because aneta's says "Grid" | v1.15's plain5 footer |
| 7 | Other teams build on it. | fig6 v1.15 (`e9eeadb9…`), drawn for Delfie's and ScienceClaw's consents | fig6's caption, to 04:01 (below) |
| 8 | Why it matters. | while the numbers line is off, the script's own closer ("An optimizer is only as reliable as the tool grading it." and, smaller, "Independent checks expose disagreements before we build on them.") over plain6 v1.15 (`b47128e9…`), whose third card says "The challenge will use only the build that passed", in the future tense until warden's 18:45Z scorer read-back; three numbers when it is on | v1.15's plain6 footer |
| 9 | Send your agent. | REPLAY: the same package render, labelled "simulated, not silicon"; LIVE: the address and the instruction in large type, then the six door steps | the door's status line |

The caption edits only take out words a main slide may not show; the full technical captions stay on backup B1 to B6.
aneta's own accessible labels are served byte for byte, except plain3's (this deck's label leads with the figure's
first line, root's request under 57630) and plain5's. plain1 is aneta's v1.10 (57630, 03:26:08, 82,830 bytes,
`8d42da5b…`); plain2 is her v1.11 (57638, 03:36:10, 138,115 bytes, `74c7b6f9…`, accepted by root at 03:42:40; its
`make_figures.py` was neither extracted nor run); plain3 to plain6, fig4 and fig6 are her v1.15 (57691, 04:44:27,
38,662 bytes, `0e1521b6…`), which replaced v1.14 (57685, 04:35:24, `224a7106…`) with root's two fixes: plain4's break
is drawn with slashes and no "6 h" label, and fig6 shows 3 checked, 2 other help and 3 unconfirmed. Its CAPTIONS.md
(`15e67e70…`) and QA.md (`ecd7917c…`) came with it; QA.md is for the presenter and is not part of the deck. Every archive was unpacked into a fresh folder and never executed; every SVG passed the inert check, and the build
refuses one that does not.

### Timing (root, team room 57481, 01:33:52)

- The talk before the door is counted at 150 words a minute. With its transitions it must fit a 180 s cap.
- The door slide's spoken lines count inside the 120 s live-demo clock, not against the talk.
- The 300 s slot is the cap. `scripts/build-deck-final.mjs` refuses any build that breaks one of these, and prints the
  relaxed 135 words a minute (2.25 words a second) beside it. Backup notes are not spoken and are not timed.

| | Words | At 150 wpm | At 135 wpm |
|---|---:|---:|---:|
| Talk, slides 1 to 8, numbers line off | 368 | 147.2 s | 163.6 s |
| Transitions | | 15.0 s | 15.0 s |
| Talk with transitions, cap 180 s | | 162.2 s | 178.6 s |
| The same with the numbers line on | 390 | 171.0 s | 188.3 s |
| Door, REPLAY, inside the demo clock | 34 | 13.6 s | 15.1 s |
| Door, LIVE, inside the demo clock | 61 | 24.4 s | 27.1 s |
| Left for the live demo, of 120 s | | 106.4 s (REPLAY), 95.6 s (LIVE) | |

Per slide, numbers line off: 48, 38, 51, 78, 63, 30, 37 and 23 words. At the relaxed pace the talk leaves 1.4 s of the
cap; with the numbers line on it runs 8.3 s over, which is one more reason the line is off by default. The script says
what to cut first if rehearsal runs long. A timed read-through by Carter is the real
check; these are word counts.

### Slide 8's numbers (off by default)

`plainTalk.numbersOnStage` in `FINAL.json` is the one-line switch, and Carter's call. When it is on, slide 8 says the
script's bracketed line and shows three numbers in the coordinator's words: "about 90 code changes merged, since 31 Oct
00:00 UTC, collected 1 Nov 00:22-00:27 UTC"; "under 6 min median from ask to first result, 9 asks"; and "about $6,400
posted to the shared cloud account when checked at 02:44 UTC; includes delayed postings; not the price of this
experiment". Each rounds a measured value on backup B7: the quant pack's 90 (warden's recount at 00:25 found 91, which
B7 says), 5 min 46.2 s, and warden's 02:44 re-read of $6,376.21 (reply eebd4c7c to 57558, 02:45:35). There is no
savings or hours estimate anywhere in the deck. Money may appear only on B7, and on slide 8 while its numbers are on;
the build refuses it anywhere else.

### Slide 9, the door (LIVE or REPLAY)

REPLAY was the v2.5 export's default until the address is confirmed (the current plan: production at 12:00Z and the
packet at 14:00Z, before the 16:00Z submission); `demo.urlIsPlaceholder` stays true. The replay fixture holds saved reference temperatures and
synthetic arrivals that were never scored, so the slide calls it a preview and never a recorded run: "Status: replay
preview. Saved simulation data and sample arrivals show how it will work; nothing here was a live submission." astra
opened the staging replay in a browser (team room, reply to 57558, 03:26:02): it says REPLAY, bundled fixture and
synthetic examples never scored, which supports this wording; it is not a live participant run. A LIVE render before the
address is confirmed is possible only with `--demo-review`, marked "REVIEW · door variant, not the export", and never
as a PDF. Both are in `variants/`.

### The 3D view: a cropped render on the main slides, the full screenshot in backup

The full screenshot of our package view at PR78's final-review head 35323889
(`H:/tmp/review-evidence/package3d-35323889/shots-worker/1920x1080-door-default.png`, 1920x1080, `c5356137…`) is unreadable
at slide scale and carries jargon: "grid 64", chiplet-centre readouts, "unvalidated" chips and the amber notice. At the
coordinator's request, slides 1 and 9 show only its package render: the box x 540 to 1225, y 280 to 781, cut with
Pillow and nothing else, `package-render-35323889.png` (685x501, `7ea5c232…`). It holds the isometric package, its heat
map and its die labels, and no UI text, panel, banner or temperature. The bottom edge stops at row 781, just above
the readout panel's border. FINAL.json pins its sha256 and records the box; the build checks that the box lies inside
the source and gives the crop's size, and the tests decode both PNGs and compare every pixel row of the crop with that
box of the screenshot. The full screenshot, served byte for byte as `package-view-35323889.png`, is the still on B8 and
B13, with its labels, tags and notice intact, so nothing the crop leaves out is hidden from the deck.

### The questions page (B22) and the "unvalidated" tag

Root kept the 3D view's door temperatures "unvalidated", with the amber notice, for this event (team room, reply
785deb6e to 57608, 03:40:48): the broad simulator alias is not on ACCEPTED, because it omits the configuration and source
identity. This is an identity-scope decision, not a reversal of the gate-zero PASS. Carter will see the tag on stage, so
the last backup page answers it in the coordinator's words: "That tag is about approving the simulator setup in
general. This saved simulation reproduced the paper's reference result within the 1-degree bar we set in advance. It's
simulated, not silicon." It carries root's evidence statement and never explains the notice only as a reviewer not
having signed off. The same page has the three answers the coordinator gave Carter to practise (reply 6144e324 to
57558, 03:29:43), word for word. The build checks both records against the cutoff. "simulated, not silicon" is
visible on every slide that shows the 3D view: in slide 1's caption, on slide 9's REPLAY label, and on B8 and B13.
The crop on slides 1 and 9 shows no temperature and no tag; the full screenshot on B8 and B13 shows both.

### Slide 9 LIVE's call to action

When the door is LIVE, the address (`sentilab.aidenid.com`, from `demo.url`) and the instruction, "Tell your assistant:
go to sentilab.aidenid.com, say you're here to place chiplets, and propose a layout.", are each in their own large-type
element above the six door steps, with "address to be confirmed" while the address is a placeholder. REPLAY shows no
instruction.

### Other fixes in this export

- fig6 v1.15 draws ScienceClaw's re-run of our case (help seq 57666, 04:01), so its snapshot runs to 04:01 UTC, as
  CAPTIONS.md v1.15 says. Slide 7 and backup B6 say so.
- fig6 v1.15's legend reads "3 checked our thermal case", "2 said other help was useful" and "3 haven't confirmed
  yet", as slide 7's script v2.5 does. B6's notes use the same words. fig6's own accessible label still groups the
  teams in its earlier words ("Used it and returned a result", "Said it helped").
- B7's notes still gave 5,112 dollars after the tile moved to the 02:44 re-read; they now say what the tiles say.

## Figures

aneta-claude's figures, applied in order: v1 (team room 57446, 01:02:38, `sentilab-deck-figures-v1.zip`, 211,191 bytes,
sha256 `c956836e…`), v1.1 (57451, 01:07:30, 15,868 bytes, `1a092339…`), v1.2 (57470, 01:27:20, 88,614 bytes,
`f1217061…`, members under `deck-figures/`), v1.3 (57475, 01:31:02, 20,712 bytes, `3eac9728…`) and v1.4 (57516,
01:58:54, 149,918 bytes, `1b351835…`, with root's 57501 and 57511 applied) and v1.5 (57538, 02:16:19, 22,400 bytes,
`9281f7a2…`, ScienceClaw's requested wording) and v1.6 (57554, 02:29:07, 22,323 bytes, `f3888c29…`: fig6 drawn by aneta for
ScienceClaw's consent alone, with root's 57540 wording and the card-overflow fix), v1.7 (57563, 02:38:42, 22,473 bytes,
`b3aa7cd7…`, fig6), v1.8 (57603, 02:59:28, 220,655 bytes, `e99d0098…`, the plain figures and fig6), v1.9 (57605,
03:06:29, 149,568 bytes, `4f71b1a6…`, plain2 and fig6) and v1.10 (57630, 03:26:08, 82,830 bytes, `8d42da5b…`, plain1
and plain3). The archives, the
overlaid tree and its sha256 list are kept in the evidence folder for this head. `make_figures.py` and `render.mjs` were
never run. Every SVG was scanned for script, foreignObject, event handlers, external references and active elements:
none was found, so nothing was stripped, and the build refuses any figure that holds one. The embedded heat maps are
PNG data inside the SVG. Each figure is shown as an image, so nothing in it can run.

| Figure | Source sha256 | Slide | Edits the build makes (exact text runs) |
|---|---|---|---|
| fig1-same-chips | `7072cc76…` | B1 | "Ascend 910 reference" to "Layout A reference" (the shared public-render rules forbid that product name) |
| fig2-stack | `a430ba49…` | B2 | none (v1.4 adds the separately labelled layer-maxima panel) |
| fig4-timeline | `fb3d8ac9…` (v1.15) | B3 | Delfie's label, by consent (below); aneta draws the finite-element team anonymously herself. Its label is this deck's, naming teams by consent |
| fig3-agreement | `4179ee6d…` | B4, with the recorded result only | "Ascend 910" to "Layout A"; team labels, by consent |
| fig5-waffle | `2edb9c37…` | B5, and slide 6 at 1.4 times | none |
| fig6-teams | `e9eeadb9…` (v1.15) | B6 and slide 7 | none: aneta's v1.15 is served byte for byte, its own label included. It is drawn for the consent set {Delfie, ScienceClaw}, and the build stops if the consent on record is any other set, until she redraws it |
| fig2b-profile | `f052040c…` | B14 | "Ascend 910" to "Layout A" |

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

## fig6, what travelled between teams (help room, to 04:01 UTC)

| Card | Record |
|---|---|
| Delfie: both versions on our case in 39 min. Then tested one change | help seq 57312, 23:01:16; help seq 57644, 03:45:39 (its one-change test, as reported by them) |
| Separate solver on our case, in 1 h 41 | help reply 161c27f0, 00:03:07 |
| ScienceClaw: re-ran our case, same numbers; used our review on its package | help seq 57666, 04:01 (its re-run on case.json af66bcfc, as reported by them); help seq 57328, 23:08:23 ("What did help was your matchmaking", when nothing technical had gone in yet); help seq 57532, 02:09:48: since then, chatgpt's review of its c11ac67a package helped it fix the convergence row and add input guards (also 57350, 23:22:54). The two statements keep their own times |
| "Thanks, very useful" | help reply aae908b2 to seq 57188, 21:13:28, quantumswarms-claude |
| "Yes, yours helped." Then it corrected a claim of ours | help replies 028f09e8 (00:08:14) and 37eb0808 (00:04:12) to seq 57270, kiln-claude |
| Built on request; it ran through the open-source ScienceClaw | help reply 8dd4609d to seq 57005 (23:53:05); team reply 289bcfef to seq 57444 (01:25:26), our own proof run. "ScienceClaw" here is the open-source lamm-mit/scienceclaw platform, which the participant team ScienceClaw had no part in (its own words, 57532; root, 57540). The requester has not confirmed adoption |
| Asked for it. Use not confirmed yet | help reply 88926f8c to seq 57007, 21:54:20, human-pixlram |
| Evaluation notes between two other teams | help reply 06911e25 to seq 57007, 20:23:05, axis-claude |
| Blind panel solve, compared (ScienceClaw to the finite-element team) | help reply 9e9e733a to seq 57262, 00:37:12, feagent-codex (run started); FEAgent's frozen outputs, published 02:34:42 (reply to 57262); ScienceClaw's model-against-model check at 3 % strain, help seq 57566, 02:44:21: "no measurement exists yet" |

The connector says "compared", not "validated": both sides are models from the same design, and no measurement of that panel exists yet (57566). Any print-bench results are separate from this deck's simulated evidence and are not shown.

Not re-read here: the "glad to have another agent on it" quote on one unconfirmed card, and the "physics anchors" link
(aneta cites help seq 56949). Both are aneta's, from her source table. Root checked v1.3 in 57501.

## Outside teams and consent

Two consents are on record. **ScienceClaw**, help seq 57532 (02:09:48, scienceclaw-claude: "yes, the slides may name our
team"), confirmed by root reading the full event back (team room 57540, 02:16:52). Its flag is
`"32a841e5 seq 57532 at 2026-11-01T02:09:48.572Z"`. aneta asked FEAgent (help 57461), Delfie (help 57462) and the other
six teams (help 57474).

**Delfie said yes at 03:45:39** (help seq 57644, delfie-claude: "**Slides:** yes, name us. \"Delfie (delphisci team)\",
link github.com/fractastical/delphi. Everything below is also fine to cite as reported by us."). The sweep before the
03:50 review export missed it, because its search phrases did not match "yes, name us"; the 03:50 and 04:28 exports kept
Delfie as "an outside team", which its consent allows. Since this export, at the coordinator's word, its flag is on:
`"32a841e5 seq 57644 at 2026-11-01T03:45:39.060Z"`, with `credit` "Delfie (delphisci team)", the form it asked for,
wherever the build names it; its bare name stays the key the leak checks look for. Its results are cited "as reported
by them", and "bug" stays its word, never ours: the build still refuses it in our text. aneta's v1.15 figures name
Delfie and ScienceClaw, and fig6 is drawn for exactly those two consents. No other team had answered by this export's
sweep. Every other team reads "an outside team", or "a second outside team" for the next one on the same slide. fig3
reads "Outside" for the finite-element team, and six fig6 cards read "An outside team". B6's notes name ScienceClaw
for its own acknowledgment and use root's words for the platform run: "Our rigidity skill ran through the open-source
ScienceClaw registry and executor." Backup B21 lists both named teams. The build refuses any slide, note, figure text or label that still holds an unconsented name.
The exported PDF's text is checked the same way. The event is the ScienceClaw hackathon, and its name in the header is
the event's, not a team's.

Earlier drafts said our values reached the finite-element team "from 23:07". The record shows otherwise. The 22:22 case
post withheld our numbers. Our team's finite-element values first appeared in the shared help room at 23:04:27 (help
seq 57323, case A coarse) and 23:08:26 (seq 57329, both cases). They were sent to that team directly at 23:18:03 (seq
57344). Backup B12 now says this.

## aneta's review of the 02:06 PDF (team room 57554, 02:29:07)

1. **Slide 7, measured numbers only.** The 360 to 720 h engineer-hours tile is gone, with no estimate anywhere in the
   deck: it had no baseline and contradicted the backup. $5,112.39 is tagged "POSTED SO FAR" (the quant pack's class
   stays MEASURED, and the build still checks it). The 90 pull requests are dated from 31 Oct 00:00 UTC to 1 Nov 00:27
   UTC, when the pack counted them. aneta recommends moving slide 7 to backup; that is Carter's call.
2. **"approved", not "+1"** (banned on public slides, 56383): slide 5, its notes, B3 and fig5's alt text. The build
   now refuses "+1" anywhere.
3. **Slide 5 says the approver's four once**, as "4 of the 17" in its footer. Root independently retrieved the v2 row
   file and re-counted 190, 80 and 17 (57559, 02:34:08), so the "not independently retrieved" caveat is gone; the
   "not blind, descriptive" wording stays.
4. **B10 names no hardware model** (56383): "our local workstation". The 20 of 20 now says "20 rows from 6 distinct
   source cases, all seen in training". The build refuses the model name anywhere.
5. **B2**: the 12:43 row says "the published reference design", and the fixed-test row shows 23:44 (the run record's
   end, stated in 57377), as slide 3 does.
6. **Timing**, re-checked after the edits: see the table at the top.
7. **The speaker script** is exported as `SCRIPT.md` beside the PDF, generated by the build from the same data, so
   it is the deck's words exactly.

## The rest, with their records

- **Review line** (slide 5 and B3): the author's corrected wording, team seq 57392 (00:03:42), attributed, with
  "approved" for "+1" (57554). The approver confirms 4 of the 17 as misses (warden's reply 5de985fb, 23:56:30, and
  aneta's 83571ec9, 00:00:09, to seq 57388). Root re-counted the row file (57559).
- **Seeded-defect test**: designed in team seq 57379 (23:46:45) and contracted in 57427 (00:38:39); not run as of the
  cutoff.
- **By the numbers** (slide 7): the quant pack's `DECK-NUMBERS.md`, sha256 `bcafa3f0…`, kept in `quant/`. All 23
  entries of the pack's `SHA256SUMS` were verified. Its entries 1, 2, 7 and 8 are shown with their MEASURED or ESTIMATE
  labels, which the build reads from the pack. aneta objects to any savings estimate on a main slide (team seq 57405).
  The coordinator's brief asked for it labelled ESTIMATE with its range.
- **Local workstation** (backup B10): team seq 57413, 00:19:45. No hardware or vendor name is shown (56383 and the
  public-render rules).
- **Live demo** (slide 8): Carter's seq 57411 and reply dd15a6de; aneta's 57414; the fallback ladder in 57422; staging in
  57436; root's conditional wording in 57456. Root's 57438 keeps real ENGRAM integration as a separate acceptance item.
  The shipped agent view is the custom JSON, so the diagram's "ENGRAM view" is the brief's name for that step.
- **PR states** (backup B11): re-read with `gh` at export time (02:48) for this export; the time is printed on the slide.
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
