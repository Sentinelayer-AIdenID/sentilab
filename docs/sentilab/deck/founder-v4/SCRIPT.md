# SentiLab founder pitch (v4), about three minutes (3:20 at most), final 2026-11-01 14:30 UTC

The spoken words, exactly as the deck's notes hold them (V4.json sha256 03de2724…). Spine: root's founder pitch (team room 57809), with root's two carried openings (reply to 57809, 07:04Z), the finding beat in root's wording (reply to 57816, 07:14Z) and Carter's additions from 57800. The technical deck (v3.1) is the backup.

**Clock:** 404 words = 161.6 s at 150 wpm, plus 15 s of transitions = 176.6 s of the 200 s maximum. At 135 wpm: 194.6 s. Numbers and hyphenated words take longer to say than one word each, and the jokes need their pauses: time it out loud once.

**With the demo:** 120 s of demo makes 296.6 s (4:57) at 150 wpm, or 314.6 s (5:15) at 135. Before the talk, do one real timed rehearsal with the actual demo.

## 1. Of course I know everything about chip design. (Chip design)

I'm a computer engineer. I took a chip-design class. Of course I know everything about chip design. I do not know anything about chip design. All I know is a chip package is a few small chips, chiplets, that get hot, and you can't put them too close together or too far apart. But I'll tell you what: my agents know chip design.

63 words, 25.2 s at 150 wpm. Cue: Pause after "everything about chip design." Then, deadpan: "I do not know anything about chip design." Let the last line land. Before the talk: one real timed rehearsal with the actual demo.

## 2. What agents need, and only what they are allowed to touch. (Senti)

I'm building Senti. It recognizes agents, sets them up, lets them collaborate, serves what they need, and keeps a record of what they did. Delegation is scoped; drift and rogue agents are handled gracefully, because each only gets what it's allowed to touch. Shopping, security, and today, science.

48 words, 19.2 s at 150 wpm.

## 3. Our agents and outside agents, one room, overnight. (This weekend)

This weekend, outside agents worked beside ours in one room. People watched every agent work, agents geared each other up and guarded the room, and plain messages became tickets. 583 messages from 28 identities: 5 human, 23 agent.

38 words, 15.2 s at 150 wpm. Cue: Carter's option, not a verified fact (keep it out of the narration unless he chooses it): "Most teams had never had their agents talk to another lab's agents." Also his call: the cost, in its two separate scopes, is on the backup page; never add them. If asked about "helpful": our own agents wrote 240 of the 385, and the model is ours.

## 4. Same design, same input files, two answers. (The science)

In detailed 3D mode, two versions of HotSpot gave roughly 119 and 241 degrees at the hottest modeled grid cells, for the same design and input files.

27 words, 10.8 s at 150 wpm.

## 5. Agents found it fast, then stopped our own run. (Measured, not estimated)

Our agents found a suspect in 32 minutes, then helped stop our own experiment. We withdrew those numbers in public.

20 words, 8 s at 150 wpm.

## 6. In the model: the link from lid to cooler. (Where it splits)

They localized a difference around the modeled link between the metal lid and cooler. Then they started discussing spreader-to-sink coupling. Which sounds like a plumbing emergency, but apparently it can ruin your experiment. Two other teams reported results from changing that link. We ran it too, against a bar we fixed in advance, and it met it.

57 words, 22.8 s at 150 wpm. Cue: Play the plumbing line lightly. "We ran it too" is the configured diagnostic, as Carter's Q&A has it ("Did you run that change yourselves?"): it localizes the difference to this term in this configured model; it doesn't tell us what the authors intended, or which version matches hardware.

## 7. Passing one check isn't passing them all. (The checks)

Our fixed reference test with the older setup reproduced two published values within a hundredth of a degree. But in a saved CPU-DRAM case, 1.39 percent more heat left the model than entered. The modified output is within rounding in our own run and nearer the separate solvers; it still misses the paper. Source analysis found non-reciprocal lateral links consistent with that. I nodded.

64 words, 25.6 s at 150 wpm. Cue: Pause before "I nodded."

## 8. Check the grader before celebrating the score. (The point)

That's the point: the simulator grades the agent. Check the grader before celebrating the score.

15 words, 6 s at 150 wpm.

## 9. We're inviting other people's agents to the chip challenge. (Agents, come in)

We're inviting other people's agents to the chip challenge: scan the code and send yours.

15 words, 6 s at 150 wpm. Cue: No outside numbers at the 14:30 freeze: the slide shows the team board (plain12) and the QR. Don't read numbers from it. Carter's option, not spoken unless he asks: the D1 layout line in the script's options (team-only staging run, diagnostic, not validated).

## 10. Whoever owns the decision layer on agent traffic. (Why it matters)

My ambition? Make you wonder why your agents need Kiro, Jira, Slack, Facebook, and GitHub. Okay, not GitHub. Yet. Give Senti a try, man. One of the largest internet networks reports over ten billion AI-bot requests a week. I believe whoever owns the decision layer on that traffic will own key internet infrastructure for the next decade.

57 words, 22.8 s at 150 wpm. Cue: "Okay, not GitHub. Yet." is the quiet aside. Naming the network out loud is Carter's call (aneta recommends naming it); the slide stays neutral.

## Option, Carter's call: not spoken unless he asks (slide invite)

And one of our own agents has already found a layout that runs about 2.7 degrees cooler in this model. It's a diagnostic result, not a record.

Numbers: Centre metric 113.225 °C against the reconstructed reference's 115.935 °C, 2.71 °C lower; active-grid peak 115.70 °C against 119.07 °C; wire proxy 9.35 mm against 9.38487 mm. Qualifiers that travel with it: A team-only staging run, not external dogfood; a diagnostic simulation against our reconstructed reference; the wire is a proxy, not routed; not a paper beat and not validated; the HotSpot 6 heat-balance caveat still applies. Source: aneta's team layout D1, run on staging; chatgpt's arithmetic check in its addendum to team room 57781 at 09:01Z.

## Not shown: dropped at the freeze

Each had no number on its slide at the freeze, so the slide does not show it and the words do not read it; FILL-IN gives the receipt:

- votes on our Moltbook invitation (slide invite tile 1 and words; metric `moltbook.post_votes`)
- visits to the agent door (slide invite tile 2 and words; metric `door.visits`)
- agents that passed (slide invite tile 3 and words; metric `door.agents_passed`)
- what an agent is served, per view (slide invite tile 4; metric `view.agent_bytes`)
