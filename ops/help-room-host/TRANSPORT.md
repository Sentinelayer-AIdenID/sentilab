# Proposed transport: help-room poller to the trained adapter (not implemented)

Scope: how the existing help-room poller (`greeter.mjs`, the sole participant responder) would get an answer from the GB10-trained adapter served behind root's PC, during a reviewed and granted serving window only. Root owns the serving contract and backend; warden owns review, the job grant and operator deployment; this file covers only the poller's side. Nothing here grants or starts anything.

## Constraints
- No second participant listener, no new inbound port, no tunnel, no key export.
- Both directions must be unspoofable by construction. Every agent id on our Senti account is self-declared under one login, so posting under a name proves nothing. This applies to the request as well as the result: the result-signing key alone must not let another persona on the same account manufacture valid inference requests.

## Choice: a private Senti room, with both the request and the result signed (Ed25519)
- **Room:** a private room `sentilab-serving` with members only from the host team, no participants. The poller already speaks Senti, and root's PC already reaches Senti outbound, so nothing new is exposed.
- **Keys:**
  - The requester key belongs to the poller. Its private key is in the poller's environment only, and the bridge pins its public key.
  - The result key belongs to the serving bridge. Its private key stays on root's PC, and the poller pins its public key.
  - Both public keys are committed with the reviewed source and bound into the job grant.
- **Request:** one message from `sentilab-host`, the canonical JSON of:
  `{"v":1,"grant":<job/window id from warden's grant>,"requester_key":<key id>,"room":<help-room id>,"event":<help-room sequence id being answered>,"id":<uuid4>,"nonce":<32 random bytes, base64url>,"created":<iso>,"deadline_s":20,"limits":{"max_input_tokens":<from the grant>,"max_output_tokens":<from the grant>},"system":<string>,"user":<string>,"prompt_sha256":<hex of the UTF-8 bytes of system + "\n\n" + user>,"sig":<requester signature over every other field>}`
  The prompt is room text that is already public in the help room, plus the fixed host rules. No secret is in it.
- **Bridge-side checks** (root's implementation; listed so the two sides agree):
  - The requester signature verifies against the pinned key.
  - The grant is the active one, and `created` falls inside its window.
  - The request count is under the grant's cap.
  - `id` and `nonce` were never seen before. The bridge records them as consumed before any model call, and an unknown outcome stays consumed.
  - The input is within `max_input_tokens`, counted with the adapter's own tokenizer. Oversize input is refused before any call. The retained adapter's context is 1,024 tokens, so most participant messages won't fit, and the bridge refuses them.
- **Result:** a reply to that exact request message, the canonical JSON of:
  `{"v":1,"grant","id","nonce","prompt_sha256","event","adapter":{"base":"Qwen/Qwen3-4B-Instruct-2507@<rev>","lora_sha256":<hex>},"outcome":"served"|"refused"|"error","latency_ms","finish_reason","text","usage":{"input_tokens","output_tokens"},"sig":<bridge signature over every other field>}`
- **Cancellation:** after `deadline_s`, the poller posts a signed `{"cancel": id}`. The bridge treats a cancel as terminal. A late result is ignored, and the request still counts as consumed.
- **Poller acceptance:** all of these must hold.
  - The reply targets the request's sequence id.
  - `grant`, `id`, `nonce`, `event` and `prompt_sha256` echo exactly.
  - The bridge signature verifies.
  - `outcome` is `served` and the reply arrives before the deadline.
  - `text` passes the same output guard as hosted answers.

  Anything else, including refusal, error, timeout or a bad signature, falls back to the hosted model.
- **Poller pre-check:** before posting, it uses a conservative size bound (characters per token from the adapter's tokenizer, measured once and committed). Anything that can't fit goes straight to the hosted model, and no request is sent.
- **Window:** requests are sent only while the grant's window is open, up to its request cap. Outside the window the poller never posts a request.

## What participants see
- During a window, every answer carries a short host-generated label: "Answered by our trained model" when the adapter served it, or "Answered by our hosted model (the trained model couldn't take this one)" on fallback. Outside a window there is no label, as today.

## Accounting
- `responder.jsonl` gets one line per attempt:
  - grant, request id and event;
  - the backend that answered;
  - the adapter identity, or `hosted-fallback` with its own token usage;
  - the outcome and both latencies.
- Every attempt is kept, including refused, cancelled, timed-out and fallback calls. Nothing is dropped from the record.

## Latency
- While a request is pending, the poller polls the serving room every 1 s.
- The participant's wait is bounded by the 20 s deadline before the fallback answers. The historical warm median of 0.91 s was measured on repeated training cases, not conversation.

## Open questions
1. The serving bridge's agent id, and how both public keys are published and bound into the grant.
2. The grant's token limits, given the 1,024-token context.
3. The exact label wording.
