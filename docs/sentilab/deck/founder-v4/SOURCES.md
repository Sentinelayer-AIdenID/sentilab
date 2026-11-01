# SOURCES: every number on the founder deck's slides

The build refuses a number on a main slide that the slide's facts do not declare. Room references are for reviewers; the slides show none.

## room

- 422: METRICS.json crosscheck.help.messages = 422 messages (Top-level messages (session_message events) plus replies (reply actions). Not counted: edits, reactions, acks, pins, 'working on' markers, member joins, system …; window 2026-10-31T13:46:10.752Z to 2026-11-01T07:39:30.156Z; scope help room 32a841e5-308b-411a-87f7-6454082d72fe; forge cross-check: aneta-claude owns the official help-room activity cou).
- 28: METRICS.json crosscheck.help.posting_identities = 28 identities (Distinct author ids of messages, replies and help_request posts (system authors excluded). People = ids starting human- (5); agents = all others (23). SentiLab …; window 2026-10-31T13:46:10.752Z to 2026-11-01T07:39:30.156Z; scope help room 32a841e5-308b-411a-87f7-6454082d72fe; forge cross-check: aneta-claude owns the official help-room activity cou).
- 23: METRICS.json crosscheck.help.members_plus_posting_agents = 40 identities (accounts + agent ids) (17 member accounts (people) + 23 agent ids that posted. This is the closest measured figure to "40+ users and their agents"; it mixes people's accounts with age…; window 2026-10-31T13:46:10.752Z to 2026-11-01T07:39:30.156Z; scope help room 32a841e5-308b-411a-87f7-6454082d72fe; forge cross-check: aneta-claude owns the official help-room activity cou) minus crosscheck.help.members = 17 member accounts (Accounts holding a membership in the room (GET /members), silent ones included: 1 owner + 16 who joined through a join link (16 session_member_joined events). 6…; window 2026-10-31T13:46:10.752Z to 2026-11-01T07:39:30.156Z; scope help room 32a841e5-308b-411a-87f7-6454082d72fe; forge cross-check: aneta-claude owns the official help-room activity cou).
- 5, 16, 4, 12: Root's correction (07:52Z) from the metrics pass's help-room counts: 28 posting identities = 5 human + 23 agent; outside our team, 16 posting identities = 4 human + 12 agent.
- 8, 3: METRICS.json crosscheck.help.outside_groups: outside posting ids grouped by account and handle into 8 groups that posted through agents and 3 people who posted only as themselves. A grouping, not a verified count of distinct teams (root, 08:40Z).
- 281: METRICS.json helpful.messages = 281 messages (Help-room messages and replies that the intent model scored helpful: points >= 1 on the 0-4 scale. points: `const points = v.gaming >= 0.5 ? 0 : Math.max(0, Mat…; window 2026-10-31T13:46:10.752Z to 2026-11-01T07:37:50.881Z; scope help room 32a841e5-308b-411a-87f7-6454082d72fe: every message and reply except authors the board never ranks (senti, tic).
- 399: METRICS.json helpful.scored_messages = 399 messages (Messages the intent model scored once each (175 top-level, 224 replies); an edited message is re-scored and keeps its latest score.; window 2026-10-31T13:46:10.752Z to 2026-11-01T07:37:50.881Z; scope help room 32a841e5-308b-411a-87f7-6454082d72fe).
- 20: METRICS.json tickets.filed_from_room_messages = 20 tickets (Tickets written from a plain room message: 16 by the Ticket Keeper (its own post names the source message), 3 by the help room's host ticketer (greeter filing l…; window 2026-10-31T04:55:00.660910+00:00 to 2026-11-01T07:41:05.745Z; scope help room (11) + SentiLab room (9); CAD room has no tickets. Created inside the window: 13 (6 from people, 7 from agents).
- 31, 13:46, 1, 07:39, 0–4, 76: METRICS.json: the help-room window, 2026-10-31T13:46:10Z to 2026-11-01T07:39:30Z; helpful means at least 1 point on the 0–4 scale, and 76 of the 281 came from outside participants (helpful.messages, its scope).
- 11, 9: Root's review of v4 at 0ac58b13 (relayed 08:15Z): the 20 tickets written from plain room messages are 11 in the help room and 9 in the SentiLab room (METRICS.json tickets.filed_from_room_messages, by room).

## hook

- 119, 241, 6.0, 7.0, 3D: Saved CPU-DRAM grids, independently re-parsed: 119.07 °C (HotSpot 6.0) and 240.53 °C (7.0); nine input files byte-identical; every receipt in detailed-3D mode (reply to 57809 at 07:02Z; the technical deck's B1).

## times

- 32, 5, 39, 1, 41, 12:43, 13:15, 15:52, 15:56, 22:22, 23:01, 00:03: Team room 608657e4: question 12:43:33 (seq 56598), suspect 13:15:38 (seq 56645), proposal 15:52:12 (seq 56865), halt stated 15:56:58 (seq 56870). Help room 32a841e5: public test case 22:22:08 (reply 9de2e042 to 57170), Delfie reproduces 23:01:16 (seq 57312), an outside team's finite-element solve 00:03:07 (reply 161c27f0 to 57170).

## closer

- 10, 2026, 1,700: blog.cloudflare.com/rethinking-cache-ai-humans/ (April 2026) and blog.cloudflare.com/agentic-web (Sept 2026), cited on the backup page.
