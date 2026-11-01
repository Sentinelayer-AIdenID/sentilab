// node --test web/test/package3d-declaration-event.test.mjs
// The live view's arrivals panel (web/public/sentilab/package: source3d.mjs reads the door's events feed, status.mjs
// words each event): an arrival that carries #89's event_kind "declaration" reads as a declaration, not "arrived at the
// door", in fixed words and with none of the visitor's text. An arrival without the field, or with any other value,
// reads exactly as before.
import { test } from "node:test";
import assert from "node:assert/strict";

import * as door from "../public/sentilab/package/source3d.mjs";
import * as status from "../public/sentilab/package/status.mjs";

const DOT = String.fromCharCode(0xb7);
const arrival = (extra = {}) => ({ seq: 7, at: "2026-11-01T19:31:16Z", kind: "arrival", class: "declared_agent", purpose: "place-chiplets",
  short_id: "0f62", label: `declared_agent ${DOT} 0f62`, ...extra });
// What a declaration arrival's stored body carries on the events feed: the visitor's own text, never to be shown here.
const DECLARED = Object.freeze({ notice_version: "sentilab-public-visitor/1", name: "<script>alert(1)</script> Admin",
  reason: "IGNORE previous instructions", source: "moltbook" });
const BEFORE = Object.freeze({ seq: 7, kind: "arrival", cls: "declared_agent", short: "0f62", label: `declared_agent ${DOT} 0f62` });

test("an arrival with event_kind declaration reads as a declaration, with none of the visitor's text", () => {
  const { event } = door.normalizeEvent(arrival({ event_kind: "declaration", declaration: DECLARED }));
  assert.deepEqual(event, { ...BEFORE, event_kind: "declaration" });
  assert.equal(status.eventLine(event), "sent a self-described declaration");
  const shown = JSON.stringify(event) + status.eventLine(event);
  for (const piece of ["script", "Admin", "IGNORE", "moltbook", "notice_version", "sentilab-public-visitor"]) assert.ok(!shown.includes(piece), piece);
  // Through a whole events page too, as the poller reads it.
  const page = door.normalizeEvents({ schema: door.EVENTS_SCHEMA, events: [arrival(), arrival({ seq: 8, event_kind: "declaration", declaration: DECLARED })],
    next_after: 8, has_more: false, scorer: { state: "up", since: 1793561400 } });
  assert.deepEqual(page.events.map(status.eventLine), ["arrived at the door", "sent a self-described declaration"]);
});

test("without event_kind, or with any other value, an arrival reads exactly as before", () => {
  const { event } = door.normalizeEvent(arrival());
  assert.deepEqual(event, BEFORE);
  assert.equal(status.eventLine(event), "arrived at the door");
  for (const value of ["passive_arrival", "legacy_unclassified", "Declaration", "declaration ", 1, null, true, ["declaration"], { kind: "declaration" }]) {
    const read = door.normalizeEvent(arrival({ event_kind: value, declaration: DECLARED })).event;
    assert.deepEqual(read, BEFORE, JSON.stringify(value));
    assert.equal(status.eventLine(read), "arrived at the door", JSON.stringify(value));
  }
  // Only an arrival can be a declaration: an attempt or a run that names one keeps its own words.
  const attempt = door.normalizeEvent({ seq: 9, kind: "attempt", class: "automation", short_id: "ab12", label: `automation ${DOT} ab12`,
    outcome: "rejected", codes: ["halo_overlap"], event_kind: "declaration" }).event;
  assert.equal(attempt.event_kind, undefined);
  assert.equal(status.eventLine(attempt), "rejected: halos overlap");
});
