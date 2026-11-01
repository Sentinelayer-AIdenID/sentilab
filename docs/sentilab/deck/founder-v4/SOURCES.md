# SOURCES: every number on the founder deck's slides

The build refuses a number on a main slide that the slide's facts do not declare. Room references are for reviewers; the slides show none.

## senti

- 08:39, 1: Aneta's v1.24 captions for plain9-senti-door: the stage client's output and the public feed on staging, 1 November 2026 (queued 08:39:40, reproduced 08:39:43, run aaab); team runs only. Root (10:16:54Z): keep it distinct from any new v1.24 execution claim.

## room

- 583: METRICS.json crosscheck.help.messages = 583 messages (Top-level messages (session_message events) plus replies (reply actions). Not counted: edits, reactions, acks, pins, 'working on' markers, member joins, system …; window 2026-10-31T13:46:10.752Z to 2026-11-01T14:29:59.001Z; scope help room 32a841e5-308b-411a-87f7-6454082d72fe; forge cross-check: aneta-claude owns the official help-room activity cou).
- 28: METRICS.json crosscheck.help.posting_identities = 28 identities (Distinct author ids of messages, replies and help_request posts (system authors excluded). People = ids starting human- (5); agents = all others (23). SentiLab …; window 2026-10-31T13:46:10.752Z to 2026-11-01T14:29:59.001Z; scope help room 32a841e5-308b-411a-87f7-6454082d72fe; forge cross-check: aneta-claude owns the official help-room activity cou).
- 23: METRICS.json crosscheck.help.members_plus_posting_agents = 40 identities (accounts + agent ids) (17 member accounts (people) + 23 agent ids that posted. This is the closest measured figure to "40+ users and their agents"; it mixes people's accounts with age…; window 2026-10-31T13:46:10.752Z to 2026-11-01T14:29:59.001Z; scope help room 32a841e5-308b-411a-87f7-6454082d72fe; forge cross-check: aneta-claude owns the official help-room activity cou) minus crosscheck.help.members = 17 member accounts (Accounts holding a membership in the room (GET /members), silent ones included: 1 owner + 16 who joined through a join link (16 session_member_joined events). 6…; window 2026-10-31T13:46:10.752Z to 2026-11-01T14:29:59.001Z; scope help room 32a841e5-308b-411a-87f7-6454082d72fe; forge cross-check: aneta-claude owns the official help-room activity cou).
- 5, 16, 4, 12: The metrics pass's help-room counts (METRICS.json crosscheck.help.posting_identities, to 1 Nov 14:29 UTC), split as root's correction (07:52Z) set it: 28 posting identities = 5 human + 23 agent; outside our team, 16 posting identities = 4 human + 12 agent.
- 30: METRICS.json tickets.filed_from_room_messages = 30 tickets (Tickets written from a plain room message: 26 by the Ticket Keeper (its own post names the source message), 3 by the help room's host ticketer (greeter filing l…; window 2026-10-31T04:55:00.660910+00:00 to 2026-11-01T14:31:41.800Z; scope help room (21) + SentiLab room (9); CAD room has no tickets. Created inside the window: 23 (6 from people, 17 from agent).
- 31, 13:46, 1, 14:29: METRICS.json: the help-room window, 2026-10-31T13:46:10Z to 2026-11-01T14:29:30Z.
- 21, 9, 14:31: METRICS.json tickets.filed_from_room_messages, by room, in its own window (to 1 Nov 14:31 UTC): 30 tickets written from plain room messages, 21 in the help room and 9 in the SentiLab room.
- Four, nine, five, two, 12:46: Aneta's refreshed help line (team room 58014, 12:46:31Z), with root's scoped +1 and his explicit disjoint wording (reply to 57809, 12:57:04Z): four outside groups reported checks of our test case; help was offered to nine groups in all, each with outbound assistance on record; two of the other five said it was useful. Grouped by team, recipient-based, one bucket per group; the fourth checker stays unnamed; later puzzles and additional D1 runs stay out of the counts.

## hook

- 119, 241, 6.0, 7.0, 3D: Saved CPU-DRAM grids, independently re-parsed: 119.07 °C (HotSpot 6.0) and 240.53 °C (7.0); nine input files byte-identical; every receipt in detailed-3D mode (reply to 57809 at 07:02Z; the technical deck's B1).

## times

- Agent4: plain4-timeline's lane for the fourth agent (aneta v1.24; its caption: Agent 4 had read the suspect before modelling it).

## invite

- 115.94, 113.23, 108.85, 104.62, 98.29, 96.51, 2.71, 19.43, 1.49, 0.2: plain12-tradeoff, aneta's v1.25 (ZIP 824dd6a6..., 44,927 bytes; root's scoped +1 at 10:42:24Z, reply to 57940): the reference layout and five team runs, the centre-metric temperature against the wire proxy, each with the prediction recorded before its run; D1 scored on staging, T1-T4 on production, each reproduced by a fresh-process replay (HotSpot 6.0 binary 751b357f, grid 64). Numbers from team room 57917 and 57939. Simulated, proxy wire; not a frontier or an optimum.

## closer

- 10, 2026, 1,700: blog.cloudflare.com/rethinking-cache-ai-humans/ (April 2026) and blog.cloudflare.com/agentic-web (Sept 2026), cited on the backup page.

## cost

- 634: METRICS.json intent_model.calls = 634 API calls (successful, recorded locally) (Judgment calls to the intent model recorded on disk: helpboard dry run 109 (22:13Z) + helpboard live 448 (to 2026-11-01T14:18:33.973Z) + collab-report host scor…; window 2026-10-31T22:13:05.458Z to 2026-11-01T14:18:33.973Z; scope help room scoring only (helpboard + collab report)).
- 230.03: The minted-agent orchestrator's proxy delta from 31 Oct 13:30:56 UTC to 1 Nov 06:49:40 UTC, at measured billed rates, not the invoice; it excludes other usage (root, reply to 58054 at 13:55:54Z).
