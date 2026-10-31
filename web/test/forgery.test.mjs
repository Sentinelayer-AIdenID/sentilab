import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { verifyDocument } from "../public/verify-core.js";

// Re-sign an edited best temperature and replace the embedded key, using the real writer.
const forged = execFileSync(process.env.PYTHON || "python3", ["-c", `
import json
from sundai_controller.controller import FlightRecord
original = FlightRecord()
original.append("lane_identity_bound", lane_id="random", agent_id="forgery:random")
original.append("baseline", thermal={"maximum_temperature_c":93.0})
original.close()
replacement = FlightRecord()
for entry in original.events[:-1]:
    payload = dict(entry["payload"])
    if entry["event"] == "baseline":
        payload["thermal"] = {"maximum_temperature_c":1.0}
    replacement.append(entry["event"], **payload)
replacement.close()
assert FlightRecord.verify(replacement.events, replacement.public_key)
print(json.dumps({"lane_id":"random", "run_id":"forgery", "record_public_key":replacement.public_key,
                  "events":replacement.events}))
`], { encoding: "utf8", cwd: new URL("../../", import.meta.url) });

test("a re-signed edited record with a swapped embedded key cannot authenticate", async () => {
  const report = await verifyDocument(forged);
  assert.equal(report.allValid, false, "self-consistency must never authenticate a replacement key");
});
