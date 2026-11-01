# SentiLab founder pitch (v4-short), two minutes, then a one-minute demo, draft 2026-11-01 10:10 UTC

The spoken words, exactly as the deck's notes hold them (V4.json sha256 a1a65ab6…). Spine: root's founder pitch (team room 57809), with root's two carried openings (reply to 57809, 07:04Z), the finding beat in root's wording (reply to 57816, 07:14Z) and Carter's additions from 57800. The technical deck (v3.1) is the backup.

**Clock:** 247 words = 98.8 s at 150 wpm, plus 10 s of transitions = 108.8 s of the 120 s maximum. At 135 wpm: 119.8 s. Numbers and hyphenated words take longer to say than one word each, and the jokes need their pauses: time it out loud once.

**With the demo:** 60 s of demo makes 168.8 s (2:49) at 150 wpm, or 179.8 s (3:00) at 135. Before the talk, do one real timed rehearsal with the actual demo.

## 1. Of course I know everything about chip design. (Chip design)

I'm a computer engineer. I took a chip-design class. Of course I know everything about chip design. I do not know anything about chip design. All I know is a chip package is a few small chips, chiplets, that get hot, and you can't put them too close together or too far apart. But I'll tell you what: my agents know chip design.

63 words, 25.2 s at 150 wpm. Cue: Pause after "everything about chip design." Then, deadpan: "I do not know anything about chip design." Let the last line land. Before the talk: one real timed rehearsal with the actual demo.

## 2. Our agents and outside agents, one room, overnight. (This weekend)

This weekend, outside agents worked beside ours in one room: agents geared each other up and guarded the room. 422 messages from 28 identities: 5 human, 23 agent.

28 words, 11.2 s at 150 wpm. Cue: Carter's option, not a verified fact (keep it out of the narration unless he chooses it): "Most teams had never had their agents talk to another lab's agents." Also his call: the cost, in its two separate scopes, is on the backup page; never add them. If asked about "helpful": our own agents wrote 205 of the 281, and the model is ours.

## 3. Same design, same input files, two answers. (The science)

In detailed 3D mode, two versions of HotSpot gave roughly 119 and 241 degrees at the hottest modeled grid cells, for the same design and input files.

27 words, 10.8 s at 150 wpm.

## 4. Passing one check isn't passing them all. (The checks)

Our fixed reference test with the older setup reproduced two published values within a hundredth of a degree. But in a saved CPU-DRAM case, 1.39 percent more heat left the model than entered. The modified output is reported within rounding and nearer the separate solvers; it still misses the paper. Source analysis found non-reciprocal lateral links consistent with that. I nodded.

61 words, 24.4 s at 150 wpm. Cue: Pause before "I nodded."

## 5. We're inviting other people's agents to the chip challenge. (Agents, come in)

We're inviting agents on Moltbook: [votes on our Moltbook invitation: measuring] votes, [visits to the agent door: measuring] visits, [agents that passed: measuring] passed.

11 words, 4.4 s at 150 wpm. Cue: Read the numbers only once they are filled; until then this slide says "measuring…". Carter's option, not spoken unless he asks: the D1 layout line in the script's options (team-only staging run, diagnostic, not validated).

## 6. undefined (Why it matters)

My ambition? Make you wonder why your agents need Kiro, Jira, Slack, Facebook, and GitHub. Okay, not GitHub. Yet. Give Senti a try, man. One of the largest internet networks reports over ten billion AI-bot requests a week. I believe whoever owns the decision layer on that traffic will own key internet infrastructure for the next decade.

57 words, 22.8 s at 150 wpm. Cue: "Okay, not GitHub. Yet." is the quiet aside. Naming the network out loud is Carter's call (aneta recommends naming it); the slide stays neutral.

## Option, Carter's call: not spoken unless he asks (slide invite)

And one of our own agents has already found a layout that runs about 2.7 degrees cooler in this model. It's a diagnostic result, not a record.

Numbers: Centre metric 113.225 °C against the reconstructed reference's 115.935 °C, 2.71 °C lower; active-grid peak 115.70 °C against 119.07 °C; wire proxy 9.35 mm against 9.38487 mm. Qualifiers that travel with it: A team-only staging run, not external dogfood; a diagnostic simulation against our reconstructed reference; the wire is a proxy, not routed; not a paper beat and not validated; the HotSpot 6 heat-balance caveat still applies. Source: aneta's team layout D1, run on staging; chatgpt's arithmetic check in its addendum to team room 57781 at 09:01Z.

## Still measuring

Each shows "measuring…" on its slide and is read out only once it is filled:

- votes on our Moltbook invitation (slide invite tile 1 and words; metric `moltbook.post_votes`)
- visits to the agent door (slide invite tile 2 and words; metric `door.visits`)
- agents that passed (slide invite tile 3 and words; metric `door.agents_passed`)
- what an agent is served, per view (slide invite tile 4; metric `view.agent_bytes`)
