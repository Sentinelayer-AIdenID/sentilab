# SentiLab founder pitch (v4), about three minutes (3:20 at most), draft 2026-11-01 08:10 UTC

The spoken words, exactly as the deck's notes hold them (V4.json sha256 03653f8e…). Spine: root's founder pitch (team room 57809), with root's two carried openings (reply to 57809, 07:04Z), the finding beat in root's wording (reply to 57816, 07:14Z) and Carter's additions from 57800. The technical deck (v3.1) is the backup.

**Clock:** 390 words = 156 s at 150 wpm, plus 15 s of transitions = 171 s of the 200 s maximum. At 135 wpm: 188.3 s. Numbers and hyphenated words take longer to say than one word each, and the jokes need their pauses: time it out loud once.

## 1. Of course I know everything about chip design. (Chip design)

I'm a computer engineer. I took a chip-design class. Of course I know everything about chip design. I do not know anything about chip design. All I know is a chip package is a few small chips, chiplets, that get hot, and you can't put them too close together or too far apart. But I'll tell you what: my agents know chip design.

63 words, 25.2 s at 150 wpm. Cue: Pause after "everything about chip design." Then, deadpan: "I do not know anything about chip design." Let the last line land.

## 2. What agents need, and only what they are allowed to touch. (Senti)

I'm building Senti. It recognizes agents, sets them up, lets them collaborate, serves what they need, and keeps a record of what they did. Delegation is scoped; drift and rogue agents are handled gracefully, because each only gets what it's allowed to touch. Shopping, security, and today, science.

48 words, 19.2 s at 150 wpm.

## 3. Many labs' agents, one room, overnight. (This weekend)

This weekend, most teams had never had their agents talk to another lab's agents. Overnight, one room did it: people watched every agent work, agents geared each other up and guarded the room, and plain messages became tickets. 422 messages from 28 identities: 5 human, 23 agent.

47 words, 18.8 s at 150 wpm. Cue: Carter's call: "most teams had never had their agents talk to another lab's agents" is his own claim from the weekend; say it only if he stands by it. Optional, also his call: the cost, in its two separate scopes, is on the backup page; never add them. If asked about "helpful": our own agents wrote 205 of the 281, and the model is ours.

## 4. Same design, same input files, two answers. (The science)

In detailed 3D mode, two versions of HotSpot gave roughly 119 and 241 degrees at the hottest modeled grid cells, for the same design and input files.

27 words, 10.8 s at 150 wpm.

## 5. Agents found it fast, then stopped our own run. (Measured, not estimated)

Our agents found a suspect in 32 minutes, then helped stop our own experiment. We withdrew those numbers in public.

20 words, 8 s at 150 wpm.

## 6. In the model: the link from lid to cooler. (Where it splits)

They localized a difference around the modeled link between the metal lid and cooler. Then they started discussing spreader-to-sink coupling. Which sounds like a plumbing emergency, but apparently it can ruin your experiment. Two other teams reported results from changing that link.

42 words, 16.8 s at 150 wpm. Cue: Play the plumbing line lightly.

## 7. Passing one check isn't passing them all. (The checks)

Using the older setup and the paper's own reading, we reproduced two published values within a hundredth of a degree. Our saved older-build result matched the paper but failed this heat-balance check. The modified output is reported within rounding and nearer the separate solvers; it still misses the paper. Source analysis found non-reciprocal lateral links consistent with that. I nodded.

60 words, 24 s at 150 wpm. Cue: Pause before "I nodded."

## 8. The simulator grades the agent. (The point)

That's the point: the simulator grades the agent. Check the grader before celebrating the score.

15 words, 6 s at 150 wpm.

## 9. We're inviting other people's agents to the chip challenge. (Agents, come in)

We're inviting agents on Moltbook: [votes on our Moltbook invitation: measuring] votes, [visits to the agent door: measuring] visits, [agents that passed: measuring] passed.

11 words, 4.4 s at 150 wpm. Cue: Read the numbers only once they are filled; until then this slide says "measuring…".

## 10. I believe whoever owns the decision layer on that traffic will own key internet infrastructure for the next decade. (Why it matters)

My ambition? Make you wonder why your agents need Kiro, Jira, Slack, Facebook, and GitHub. Okay, not GitHub. Yet. Give Senti a try, man. One of the largest internet networks reports over ten billion AI-bot requests a week. I believe whoever owns the decision layer on that traffic will own key internet infrastructure for the next decade.

57 words, 22.8 s at 150 wpm. Cue: "Okay, not GitHub. Yet." is the quiet aside. Naming the network out loud is Carter's call (aneta recommends naming it); the slide stays neutral.

## Still measuring

Each shows "measuring…" on its slide and is read out only once it is filled:

- votes on our Moltbook invitation (slide invite tile 1 and words; metric `moltbook.post_votes`)
- visits to the agent door (slide invite tile 2 and words; metric `door.visits`)
- agents that passed (slide invite tile 3 and words; metric `door.agents_passed`)
- what an agent is served, per view (slide invite tile 4; metric `view.agent_bytes`)
