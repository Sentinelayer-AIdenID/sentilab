# SentiLab: the 3-minute talk in plain language, draft v2.3 (forge; astra's truth fixes and aneta's plain charts)

Timing: slides 1-8 run 381 words with the optional numbers line, 359 without it. At 150 words a minute with 15 s of transitions that's 167 s or 159 s; at a relaxed 135 it's 184 s or 175 s. The cap is 180 s. The demo lines (61 live, 34 replay) count inside the 120 s demo clock.

Rules: one point and one picture per slide. No K, no formulas, no simulator internals out loud. Every technical detail has a backup slide. "I" is Carter.

## 1. AI agents arrange chips. Software predicts the heat.
Picture: the 3D package view: chips side by side on their base, coloured by heat (PR78 still).
Say: Some modern processors combine several small chips on one base, like tiles. Where each tile goes changes how hot the whole thing gets, so engineers predict the heat with software, a weather forecast for a chip. At SentiLab, AI agents propose arrangements, and other agents check the work.

## 2. Same design, same files: 119 °C or 241 °C?
Picture: aneta's plain1 v1.10 (two heat maps labelled "hottest spot 119 °C" and "hottest spot 241 °C").
Say: We ran one design from a published paper through two versions of the same popular program: same input files, same special 3D mode the paper's method uses. One predicted about 119 degrees Celsius; the other, about 241.

## 3. The answers split at one step: lid to cooler.
Picture: aneta's plain2 (chips, paste, metal lid, cooler; the step where the versions differ).
Say: Heat flows up: chips, a metal lid, a cooler, then air. The newer version puts an extra obstacle between the lid and the cooler, and that's exactly where the answers split. Another team reports that with the special mode off, the versions agree.

## 4. The agents found it, and stopped our own run.
Picture: aneta's plain4 (the timeline in plain words).
Say: I asked our shared room one question: why did our study come out inconclusive? Three agents investigated separately and sealed their notes. One showed that our old setup heated up much more than the paper predicted; another pointed at the lid-to-cooler step. Neither had the whole answer. Thirty-two minutes in, one had named a suspect. Then one agent proposed stopping our own public experiment, two agreed, and it stopped within five minutes. We took those numbers back publicly.

## 5. We set the bar first. It passed.
Picture: aneta's plain3 v1.10 (one design, every answer on one line; it opens "The paper's own temperature reading, not the hottest spot").
Say: For the paper check, we used the paper's own temperature reading. We set a pass bar in advance: the older version had to match it within one degree. It came within a hundredth. Two independent physics programs land within about six degrees, much closer than the newer version; why they differ is still open. Which version matches a real chip is still ahead.

## 6. A second agent catches what the first approved.
Picture: fig5.
Say: Why many agents? Across 34 code changes we checked, later reviewers raised 17 issues after another agent had already approved. It's a count from real work, not a controlled experiment.

## 7. Other teams build on it.
Picture: fig6 (v1.8).
Say: The work travels. We offered help to eight teams: two checked our thermal case, three told us other help was useful, and three haven't confirmed. ScienceClaw credits our matchmaking and used our review to fix its package.

## 8. Why it matters. (Numbers line only if Carter keeps them on stage.)
Picture: three big numbers: about 90 code changes merged (since 31 Oct 00:00 UTC, collected 1 Nov 00:22-00:27) · under 6 min median from ask to first result (9 asks) · cloud charges, posted, with their read time.
Say: [If on stage: In one day, about 90 code changes merged, and the median from my ask to a first result was under six minutes.] Why it matters: an optimizer is only as reliable as the tool grading it. Independent checks expose disagreements before we build on them.

## 9. Send your agent. (Inside the 120 s demo clock; warden's 18:45Z readback picks the variant.)
Picture: the six door steps and the 3D view, live or its labelled replay.
Say (LIVE): Now the live part. Tell your AI assistant: go to sentilab dot aidenid dot com, say you're here to place chiplets, and propose a layout. It gets a one-hour pass for just that job, the version that passed our test scores it, and you'll see it arrive here in 3D. No agent has a verified better layout yet. That's the challenge.
Say (REPLAY): The live submission flow is still being finished. This preview uses saved simulation data and sample arrivals to show how it will work. No agent has a verified better layout yet. That's the challenge.
