// SentiLab Package view: the playhead rule for a verification change. Pure (no DOM, no clock), so the node tests
// run exactly what the page runs.
//
// A verification can change at any time: a live poll adds envelopes, a late conflicting or tampered envelope
// shrinks the projectable prefix K, or a new replay is opened. On EVERY change, paused or playing, the page calls
// reconcile() and adopts its result:
//   - the playhead is clamped to K (following the live edge means sitting at K);
//   - the scene is rebuilt from the new prefix, at the clamped playhead;
//   - the frame (colour-scale extrema and footprint) is kept and widened only if the new prefix EXTENDS the old one
//     (the same envelopes, by stored hash, at every old seq). Otherwise it is recomputed from the new prefix alone,
//     so a value that left the prefix can't keep stretching the scale;
//   - `reset` tells the page to cut every animation (glides, ghosts, pulses) to the new scene: nothing in flight
//     from the old prefix may finish drawing.
import { runFrame, sceneAt } from "./scene.mjs";

// Does `next` keep every envelope of `prev`, in place? Compared by seq and the stored hash the signature covers.
export function extendsPrefix(prev, next) {
  if (!Array.isArray(prev) || !Array.isArray(next) || next.length < prev.length) return false;
  for (let i = 0; i < prev.length; i += 1) {
    if (prev[i]?.event?.seq !== next[i]?.event?.seq || prev[i]?.hash !== next[i]?.hash) return false;
  }
  return true;
}

const unionRect = (a, b) => ({ x0: Math.min(a.x0, b.x0), y0: Math.min(a.y0, b.y0), x1: Math.max(a.x1, b.x1), y1: Math.max(a.y1, b.y1) });

// A growing live run keeps its scale and footprint from shifting: they only widen. Only valid while the prefix grows.
export function widenFrame(old, fresh) {
  if (!old) return fresh;
  const scale = old.scale && fresh.scale ? { ...fresh.scale, min: Math.min(old.scale.min, fresh.scale.min), max: Math.max(old.scale.max, fresh.scale.max) } : fresh.scale ?? old.scale;
  const footprint = old.footprint && fresh.footprint ? {
    ...fresh.footprint,
    extent: unionRect(old.footprint.extent, fresh.footprint.extent),
    interposer: unionRect(old.footprint.interposer, fresh.footprint.interposer),
    substrate: unionRect(old.footprint.substrate, fresh.footprint.substrate),
  } : fresh.footprint ?? old.footprint;
  return { scale, footprint };
}

// view: what the page showed before { prefix (the old prefix envelopes), frame, cursor, following }.
// verification: the adapter's result (source.mjs verifyRun): prefixEnvelopes, prefixCount, projection.
// Returns { prefix, frame, cursor, scene, reset, grew, stepped }.
export function reconcile(view, verification, { widen = true } = {}) {
  const prefix = verification?.prefixEnvelopes ?? [];
  const K = verification?.prefixCount ?? 0;
  const before = view?.prefix ?? [];
  const grew = before.length > 0 && extendsPrefix(before, prefix);
  const fresh = runFrame(prefix, verification?.projection ?? null);
  const frame = grew && widen && view?.frame ? widenFrame(view.frame, fresh) : fresh;
  const oldCursor = Number.isSafeInteger(view?.cursor) ? Math.max(0, view.cursor) : 0;
  const cursor = view?.following ? K : Math.min(oldCursor, K);
  const scene = sceneAt(prefix, cursor, frame);
  // Animate only the ordinary live case: the prefix grew by exactly the one envelope the followed playhead moved to.
  const stepped = grew && Boolean(view?.following) && cursor === oldCursor + 1;
  return { prefix, frame, cursor, scene, grew, stepped, reset: !stepped };
}
