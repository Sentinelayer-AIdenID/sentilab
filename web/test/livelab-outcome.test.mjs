// node --test test/livelab-outcome.test.mjs (from web/)
// Root's review of f9cc6ab (P2 #2): a run's outcome line shows the step from the run's own state. "Accepted" only
// once the required result check has finished; evaluated and replaying are re-checking, held is held, evaluating is
// simulating, queued is waiting in line; refused, failed and stopped read as before.
import { test } from "node:test";
import assert from "node:assert/strict";
import * as M from "../public/sentilab/live/live-model.mjs";
import { LABELS } from "../public/temperature-label.mjs";

const LABEL = Object.values(LABELS).find((l) => !l.notice) ?? LABELS.withdrawn;
const result = (replay) => ({ metric: { value: 113.23 }, label: LABEL, verification: { replay } });
const run = (status, extra = {}) => ({ status, codes: [], reason: null, position: null, result: null, ...extra });

test("outcome: every state reads its own step", () => {
  const cases = [
    [run("queued"), "waiting", /^Waiting in line$/],
    [run("queued", { position: 3 }), "waiting", /^Waiting in line · number 3$/],
    [run("evaluating"), "waiting", /^Simulating$/],
    [run("evaluated", { result: result(null) }), "waiting", /^Re-checking \(replay\) · highest chiplet-centre average .+ · simulated$/],
    [run("replaying", { result: result(null) }), "waiting", /^Re-checking \(replay\) · highest chiplet-centre average .+ · simulated$/],
    [run("replaying"), "waiting", /^Re-checking \(replay\)$/],
    [run("held"), "waiting", /^Held$/],
    [run("reproduced", { result: result("reproduced") }), "accepted", /^Accepted · highest chiplet-centre average .+ · simulated · replay matched$/],
    [run("rejected", { codes: ["placement_overlap"] }), "refused", /^Refused · /],
    [run("failed"), "refused", /^Could not be simulated · no reason given$/],
    [run("cancelled"), "refused", /^Stopped · cancelled$/],
    [run("expired"), "refused", /^Stopped · expired$/],
  ];
  for (const [L, kind, text] of cases) {
    const o = M.runOutcome(L);
    assert.equal(o.kind, kind, `${L.status}: kind`);
    assert.match(o.text, text, `${L.status}: ${o.text}`);
  }
});

test("outcome: nothing reads Accepted or replay matched before the result check has finished", () => {
  for (const status of ["queued", "evaluating", "evaluated", "replaying", "held"]) {
    const o = M.runOutcome(run(status, { result: result("reproduced") }));
    assert.equal(/Accepted|replay matched|replay pending/.test(o.text), false, `${status}: ${o.text}`);
  }
});
