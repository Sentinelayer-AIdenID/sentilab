// Lab view signing-key pins (VIEW ENVELOPE v0.2, rule 6). This is the ONLY place the page learns which core
// key it trusts. Each entry is { key_id, key_sha256 }: key_sha256 is the lowercase hex sha256 of the raw
// 32-byte Ed25519 public key. More than one entry allows rotation.
//
// The production list is EMPTY on purpose. The deploy fills it with the core's key once that key exists.
// Until then every envelope shows as unverified with the reason "no pinned key", which is the correct result.
//
// Never fill this from a replay file, its manifest, or the event API: a forged bundle would pin its own key.
// Test keys are never listed here. They exist only in the node tests and in the ?pins=test mode, which labels
// itself TEST KEYS on screen.
export const VIEW_PINS = Object.freeze([]);
