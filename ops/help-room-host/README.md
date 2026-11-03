# Help-room host (running copy)

`greeter.mjs` is the one process that reads the hackathon help room (32a841e5-308b-411a-87f7-6454082d72fe) as `sentilab-host`. It runs on the coordinator's workstation; this directory is a byte-exact copy of what runs, committed so reviewers can bind to a SHA.

## What it does
1. **Welcomes** each newcomer once. People get a fixed-text top-level welcome when they join through a link (no model). An outside agent's first message gets one model answer that welcomes it and connects it to people and tickets while the responder is on; with the responder off (no key, or `PAUSE-RESPONDER`) it gets a fixed-text welcome instead.
2. **Answers** every participant message and reply that arrives after it started, under that exact message, with an @mention of the sender.
   - It first posts a `working_on` marker ("Host answering"), then asks a hosted model for a JSON answer, then posts the reply.
   - The message being answered goes to the model whole. Context lines are clipped and say so.
   - Model: Claude Opus 5.5 (`claude-opus-5-5`) on the team's Azure AI Foundry account, through the official `@anthropic-ai/foundry-sdk` (Carter, 20:25Z). Effort `medium`, retried at `low` on failure. Structured output (a JSON schema with action, reply and reason) keeps every answer schema-valid. The stable system prompt is marked for prompt caching. No other model is a fallback: a refusal, timeout or failure posts "I can't answer that right now; a teammate will follow up here." It has no tools: the model only returns text, and this process decides what is posted.
   - Outside agents get an answer on their first message (one model welcome that connects them to people and tickets, replacing the fixed agent welcome), then only on a top-level message that addresses the host or asks the room something. An agent's threaded replies are never answered, so two bots can't ping-pong.
   - Our own team is an explicit list of exact ids in `team-ids.txt`, re-read every tick; display names never decide.
   - Skipped: the host team's own posts, anything answered or claimed by the host team after it arrived, and senders over their hourly cap (15 per person, 3 per outside agent, 60 per hour overall, welcomes included).

3. **Does not file tickets** (Carter, #57131). The room's ticket keeper turns requests from people and outside agents into tickets. The host answers and points to the keeper.

## Output guard (everything the model writes passes this before it is posted)
- Links outside an allowlist become `[link removed]`. The allowlist covers our own domains, the public org on GitHub, doi.org, arxiv.org and Wikipedia.
- Anything shaped like a credential (JWT, API-key, private-key or token prefixes) blocks the post; a safe fallback line is posted instead.
- At most 3 @mentions besides the sender, and only of handles seen in the room. `@all`, `@everyone` and `@here` are stripped.
- The reply starts with the sender's handle and is capped at 3,000 characters.

## Running it
- Launch from an immutable copy: `SHA=$(sha256sum greeter.mjs | cut -c1-12); cp greeter.mjs launch/greeter-$SHA.mjs; chmod a-w launch/greeter-$SHA.mjs`, then run that copy. The `process_start` row records its argv, cwd, pid, start time and the sha256 of the bytes it loaded.
- Key: `FOUNDRY_KEY="$(az cognitiveservices account keys list -g rg-sentinelayer-agents -n sl-agents-foundry-eastus2 --query key1 -o tsv)" node greeter.mjs`. The key lives only in the process environment and is never printed or logged.
- `DRY=1` posts nothing to the room and uses a separate state file and logs. It still makes real model calls, so it is not a provider-free test.
- Kill switch: create `PAUSE-RESPONDER` next to the script. Model answers stop; welcomes continue.
- Logs:
  - `responder.jsonl` has one `started` and one `terminal` row per model call (attempt id, effort, status ok/http_error/parse_error/abort/network_error, HTTP status, token usage, latency), and one row per answer that references its attempt ids (key, sender, action, `receiveToClaimS`, `modelS`, `receiveToReplyS`). Nothing is shared between calls.
  - At start the process logs a `process_start` row: pid, start time, and the sha256 of the source file and facts it actually loaded.
  - The handled and pending marks are written to disk before the claim and before any model call. If the process dies mid-answer, the next start logs that event as `outcome: unknown` and never retries it.
  - Tickets the model drafts land in `ticket-queue.jsonl`, and the coordinator files them.
- State in `state.json`: last sequence, handled keys, per-sender times, and `responderSince`. The backlog before the first start is never answered.

## Measured
- First live answer (2026-10-31, message #57060): marker after 13.4 s and reply after 31.7 s, of which 17.0 s was the model (7,541 input and 730 output tokens).
- Dry run on three earlier messages: model time 5, 16 and 14 s.

## Not in this process
- Serving the GB10-trained adapter. See `TRANSPORT.md` for the proposed request/result transport. Nothing in it is implemented or enabled.
