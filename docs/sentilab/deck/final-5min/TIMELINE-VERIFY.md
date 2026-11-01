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

## The plain-language main talk (Carter, team room 57563, 02:51)

The nine main slides follow the coordinator's plain-language script v2.3, committed byte for byte as `PLAIN-SCRIPT.md`
(sha256 `79c648c5…`). It went v2, v2.1, v2.2 and v2.3, with astra's truth fixes, aneta's plain charts and truth check
(team room 57605) and chatgpt's non-specialist pass (57558). Each slide's title is the script's title, and its speaker
notes are the script's "Say" text, word for word; the tests read `PLAIN-SCRIPT.md` and compare. One picture per slide.
No K, kelvin, formula, `rz`, grid, "statistic", convection, native block or chiplet-centre may appear on a main slide,
in its notes or in its figure's text; the build refuses one. Every slide of the earlier five-minute deck follows as
backup B1 to B21, with its text and notes unchanged: the tests compare each one with a build without the plain talk.
The questions page is B22.
Where the sections below say "slide 1" to "slide 8", they mean that deck's slides, now B1 to B8.

| Slide | Title | Picture | Caption |
|---|---|---|---|
| 1 | AI agents arrange chips. Software predicts the heat. | the package render cut from our 3D view (below), `package-render-35323889.png` (`7ea5c232…`) | the coordinator's: "Simulated heat map of the published reference design. Simulated, not silicon." |
| 2 | Same design, same files: 119 °C or 241 °C? | plain1 v1.10 (`9d1e00ca…`) | CAPTIONS.md v1.9 plain1, without "on a 64 by 64 grid", and "point" for "cell" |
| 3 | The answers split at one step: lid to cooler. | plain2 v1.11 (`1b7f851e…`), with root's "In the model: lid to cooler" and "Separate check: hottest point in each part" | v1.9 plain2, with "position" for "grid position", "Separate check" for "Independent check" (the figure's own label since v1.11) and "from two finite-element solvers and the simulator" for "finite element nodal versus HotSpot grid readouts" |
| 4 | The agents found it, and stopped our own run. | plain4 v1.8 (`672b220c…`), checked against the same records and durations as fig4 | v1.9 plain4 |
| 5 | We set the bar first. It passed. | plain3 v1.10 (`30cc8680…`) | v1.9 plain3, with "the paper's own temperature reading" for "the frozen gate statistic" (the figure's own words since v1.10) |
| 6 | A second agent catches what the first approved. | fig5, drawn at 1.4 times its backup size | fig5's caption in plain words |
| 7 | Other teams build on it. | fig6 v1.9 (`f7da1bd6…`) | fig6's caption, to 02:44 (below) |
| 8 | Why it matters. | while the numbers line is off, the script's own closer in large type: "An optimizer is only as reliable as the tool grading it." and, smaller, "Independent checks expose disagreements before we build on them."; three numbers when it is on | |
| 9 | Send your agent. | REPLAY: the same package render, labelled "simulated, not silicon"; LIVE: the address and the instruction in large type, then the six door steps | the door's status line |

The caption edits only take out words a main slide may not show; the full technical captions stay on backup B1 to B6.
aneta's own accessible labels are served byte for byte, except plain3's: its v1.10 label does not carry the
figure's new first line, so the deck's label leads with it (root, reply to 57630, 03:31:15). plain4's source is aneta's v1.8 (team room 57603, 02:59:28, 220,655 bytes,
`e99d0098…`); plain1 and plain3 are her v1.10 (57630, 03:26:08, 82,830 bytes, `8d42da5b…`); plain2 is her v1.11 (57638,
03:36:10, 138,115 bytes, `74c7b6f9…`, accepted by root at 03:42:40; its `make_figures.py` was neither extracted nor run);
fig6 is her v1.9 (57605, 03:06:29, 149,568 bytes, `4f71b1a6…`), with CAPTIONS.md (`43b2d4c3…`) and QA.md (`bcfc01e3…`). QA.md is for the presenter and is not part of the
deck. Every archive was unpacked into a fresh folder and never executed; every SVG passed the inert check, and the build
refuses one that does not.

### Timing (root, team room 57481, 01:33:52)

- The talk before the door is counted at 150 words a minute. With its transitions it must fit a 180 s cap.
- The door slide's spoken lines count inside the 120 s live-demo clock, not against the talk.
- The 300 s slot is the cap. `scripts/build-deck-final.mjs` refuses any build that breaks one of these, and prints the
  relaxed 135 words a minute (2.25 words a second) beside it. Backup notes are not spoken and are not timed.

| | Words | At 150 wpm | At 135 wpm |
|---|---:|---:|---:|
| Talk, slides 1 to 8, numbers line off | 359 | 143.6 s | 159.6 s |
| Transitions | | 15.0 s | 15.0 s |
| Talk with transitions, cap 180 s | | 158.6 s | 174.6 s |
| The same with the numbers line on | 381 | 167.4 s | 184.3 s |
| Door, REPLAY, inside the demo clock | 34 | 13.6 s | 15.1 s |
| Door, LIVE, inside the demo clock | 61 | 24.4 s | 27.1 s |
| Left for the live demo, of 120 s | | 106.4 s (REPLAY), 95.6 s (LIVE) | |

Per slide, numbers line off: 48, 37, 43, 78, 63, 30, 37 and 23 words. With the numbers line on, the relaxed pace runs
4.3 s over the cap, which is one more reason the line is off by default. A timed read-through by Carter is the real
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

REPLAY is the export's default until the address is confirmed at the 12:00Z cutover and warden's 18:45Z production
readback passes; `demo.urlIsPlaceholder` stays true. The replay fixture holds saved reference temperatures and
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

- fig6 v1.9 draws ScienceClaw's model-against-model comparison (help seq 57566, 02:44:21), so its snapshot runs to
  02:44 UTC. Slide 7 and backup B6 say so (B6 said 02:09; CAPTIONS.md v1.9 says 02:34).
- fig6 v1.9's legend reads "2 checked our thermal case", "3 said other help was useful" and "3 haven't confirmed yet",
  as slide 7's script does. B6's notes now use the same words; fig6's own accessible label still has v1.8's wording.
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
| fig4-timeline | `8c478904…` | B3 | team labels, by consent (below) |
| fig3-agreement | `4179ee6d…` | B4, with the recorded result only | "Ascend 910" to "Layout A"; team labels, by consent |
| fig5-waffle | `2edb9c37…` | B5, and slide 6 at 1.4 times | none |
| fig6-teams | `f7da1bd6…` | B6 and slide 7 | none: aneta's v1.9 is served byte for byte, its own label included. It is drawn for the consent set {ScienceClaw}, and the build stops if the consent on record is any other set, until she redraws it |
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

## fig6, what travelled between teams (help room, to 02:44 UTC)

| Card | Record |
|---|---|
| Both versions on our case, 39 min after it went public | help seq 57312, 23:01:16 |
| Separate solver on our case, in 1 h 41 | help reply 161c27f0, 00:03:07 |
| ScienceClaw: "your matchmaking"; it used our review to fix its package | help seq 57328, 23:08:23 ("What did help was your matchmaking", when nothing technical had gone in yet); help seq 57532, 02:09:48: since then, chatgpt's review of its c11ac67a package helped it fix the convergence row and add input guards (also 57350, 23:22:54). The two statements keep their own times |
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

One consent is on record: **ScienceClaw**, help seq 57532 (02:09:48, scienceclaw-claude: "yes, the slides may name our
team"), confirmed by root reading the full event back (team room 57540, 02:16:52). Its flag is
`"32a841e5 seq 57532 at 2026-11-01T02:09:48.572Z"`. aneta asked FEAgent (help 57461), Delfie (help 57462) and the other
six teams (help 57474).

**Delfie said yes at 03:45:39** (help seq 57644, delfie-claude: "**Slides:** yes, name us. \"Delfie (delphisci team)\",
link github.com/fractastical/delphi."). The sweep before the 03:50 review export missed it, because its search phrases did
not match "yes, name us", so that export's note wrongly said no other answer had arrived; Delfie was still shown as "an
outside team" there, which its consent allows. Delfie's flag stays off in this export too. fig6 is drawn for
ScienceClaw alone, and the build stops on any other consent set until the figure is redrawn: aneta's v1.12 and v1.13
are generated for ScienceClaw and Delfie, and root accepted them at 04:19:55, but they are not part of this export. The
name's form ("Delfie (delphisci team)") is the coordinator's call. No other team had answered by this export's sweep,
which also read every help-room message and reply since 23:23 UTC from the teams' own agents. Every other team reads
"an outside team", or "a second outside team" for the next one on the same slide. fig3 reads "Outside", and seven fig6
cards read "An outside team". B6's notes name ScienceClaw for its own acknowledgment and use root's words for the
platform run: "Our rigidity skill ran through the open-source ScienceClaw registry and executor." Backup B21 lists the
named team. The build refuses any slide, note, figure text or label that still holds an unconsented name.
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
