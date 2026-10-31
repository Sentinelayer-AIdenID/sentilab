// Lab view signing-key pins (VIEW ENVELOPE v0.5, rule 6). This is the ONLY place the page learns which core
// key it trusts. Each entry is { key_id, key_sha256 }: key_sha256 is the lowercase hex sha256 of the raw
// 32-byte Ed25519 public key. More than one entry allows rotation.
//
// Filled at deploy with the core's key. An envelope verifies only if its sig.key_id is pinned here and the key the
// core serves (GET /api/view/key) hashes to that pin; otherwise it shows as unverified, with the reason. An empty
// list means nothing verifies.
//
// Never fill this from a replay file, its manifest, or the event API: a forged bundle would pin its own key.
// Test keys are never listed here. They exist only in the node tests and in the ?pins=test mode, which only a local
// server honours and which labels itself TEST KEYS on screen.
// Production core key, provisioned 2026-10-31 by the release reviewer. The seed lives only in the sentilab-api secret store.
export const VIEW_PINS = Object.freeze([
  Object.freeze({ key_id: "sha256:51b4fe3d8d0724f44555b6339924737014973b7ee15d1f25515256e562190dd8", key_sha256: "51b4fe3d8d0724f44555b6339924737014973b7ee15d1f25515256e562190dd8" }), // gitleaks:allow -- a PUBLIC key hash, not a secret
]);
