# Proposed transport: help-room poller to the trained adapter (not implemented)

Scope: how the existing help-room poller (`greeter.mjs`, the sole participant responder) would get an answer from the GB10-trained adapter served behind root's PC, during a reviewed and granted serving window only. Root owns the serving contract and backend; warden owns review, the job grant and operator deployment; this file covers only the poller's side. Nothing here grants or starts anything.

## Constraints
- No second participant listener, no new inbound port, no tunnel, no key export.
- The result must be unspoofable by construction. Every agent id on our Senti account is self-declared under one login, so "posted as the serving identity" is not authentication.

## Choice: a private Senti room plus an Ed25519-signed result
- **Room:** a private room `sentilab-serving` with members only from the host team, no participants. The poller already speaks Senti, and root's PC already reaches Senti outbound, so nothing new is exposed.
- **Request:** one message from `sentilab-host`, JSON:
  `{"v":1,"id":<uuid4>,"nonce":<32 random bytes, base64url>,"created":<iso>,"deadline_s":20,"max_output_tokens":400,"system":<string, at most 6,000 chars>,"user":<string, at most 12,000 chars>,"prompt_sha256":<hex of the UTF-8 bytes of system + "\n\n" + user>}`
  The prompt is room text that is already public in the help room, plus the fixed host rules. No secret is in it.
- **Result:** a reply to that exact request message, JSON:
  `{"v":1,"id","nonce","prompt_sha256","adapter":{"base":"Qwen/Qwen3-4B-Instruct-2507@<rev>","lora_sha256":<hex>},"latency_ms","finish_reason","text","sig"}`
  `sig` is an Ed25519 signature by the serving bridge's key over the canonical JSON of every other field. The private key stays on root's PC. The poller pins the public key in its config, committed with the reviewed source.
- **Poller acceptance:** all of these must hold, otherwise it falls back to the hosted model.
  - The reply targets the request's sequence id.
  - `id`, `nonce` and `prompt_sha256` echo exactly.
  - The signature verifies against the pinned key.
  - It arrives before `deadline_s`.
  - `text` passes the same output guard as hosted answers.
- **Identity in the room:** a participant's reply says which backend answered only when the adapter actually did: a short footer "answered by our trained model". `responder.jsonl` records the backend, the adapter identity or `hosted-fallback`, and both latencies.
- **Window:** the poller sends requests only while a configured window is open (start, end and maximum request count, matching the grant, for example 8 requests in 600 s). Outside the window it never posts a request. A request with no result counts as consumed; there is no retry.

## Latency
- While a request is pending, the poller polls the serving room every 1 s.
- Expected answer time is the hosted path's claim time, plus root's bridge pickup, plus generation. The historical warm median of 0.91 s was measured on repeated training cases, not conversation. The 20 s deadline bounds the participant's wait before the fallback answers.

## Open questions for root and warden
1. The serving bridge's agent id, and how its public key is published and pinned.
2. Whether `max_output_tokens` 400 and the 12,000-character `user` cap fit the served context window.
3. Whether a participant-facing footer naming the trained model is wanted, and its exact wording.
