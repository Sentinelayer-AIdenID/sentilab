"""Write Python-signed four-lane runs for verify-core.test.mjs. Keys are ephemeral; nothing secret is written.

run_stdlib.json / run_fastapi.json: a valid run in both serializations. run_unequal.json: one lane signs one fewer
evaluation. run_pool.json: one lane signs a different starting pool. Each lane's record mirrors the controller's
shape: a baseline listing the shared pool, then one oracle_result per evaluation, then run_closed."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sundai_controller"))
from controller import FlightRecord  # noqa: E402

LANES = ("random", "simulated_annealing", "ucb1", "signal_portfolio")
POOL = ["ab" * 32, "cd" * 32, "ef" * 32]


def lane(lane_id, evaluations=3, pool=POOL, run_id="fixture"):
    record = FlightRecord()
    record.append("lane_identity_bound", lane_id=lane_id, agent_id=f"{run_id}:{lane_id}", public_key="ab" * 32)
    record.append("baseline", thermal={"maximum_temperature_c": 93.0, "tiny": 1e-05, "neg0": -0.0, "big": 1.5e16},
                  shared_initial_samples=[{"design_hash": h, "thermal": {"maximum_temperature_c": 93.0}} for h in pool],
                  design_hash=pool[0])
    record.append("lane_decision", note="café — \U0001F525 tab\there\nnew \x7f del", agent_id=lane_id)
    for i in range(evaluations):
        record.append("oracle_result", candidate_hash=f"{i:064x}", thermal={"maximum_temperature_c": 92.0 + i / 10})
    record.append("proposal_committed", lane_id=lane_id, proposal_id="p0", candidate_hash=f"{0:064x}", temperature_c=92.0)
    record.close()
    assert FlightRecord.verify(record.events, record.public_key)
    return {"agent_id": f"lane-{lane_id}", "record_public_key": record.public_key, "evaluation_count": evaluations,
            "best_temperature_c": 92.0, "record_valid": True, "record": record.events}


def run(lanes):
    return {"id": "fixture", "status": "done", "result": {"run_id": "fixture", "lane_results": lanes}}


out = Path(sys.argv[1])
valid = run({lane_id: lane(lane_id) for lane_id in LANES})
(out / "run_stdlib.json").write_text(json.dumps(valid), encoding="utf-8")
(out / "run_fastapi.json").write_text(json.dumps(valid, ensure_ascii=False, allow_nan=False, separators=(",", ":")),
                                      encoding="utf-8")
unequal = run({lane_id: lane(lane_id, evaluations=2 if lane_id == "ucb1" else 3) for lane_id in LANES})
(out / "run_unequal.json").write_text(json.dumps(unequal), encoding="utf-8")
other_pool = run({lane_id: lane(lane_id, pool=POOL if lane_id != "random" else POOL[:2] + ["99" * 32])
                  for lane_id in LANES})
(out / "run_pool.json").write_text(json.dumps(other_pool), encoding="utf-8")
(out / "run_raw.json").write_text(json.dumps(valid["result"]), encoding="utf-8")
spliced = run({lane_id: lane(lane_id) for lane_id in LANES})
spliced["result"]["lane_results"]["signal_portfolio"] = lane("signal_portfolio", run_id="fixture-b")
(out / "run_spliced.json").write_text(json.dumps(spliced, separators=(",", ":")), encoding="utf-8")
random_lane = valid["result"]["lane_results"]["random"]
artifact = {"benchmark": "plate", "grid": 16, "lane_id": "random", "run_id": "fixture:random", "seed": 1,
            "record_public_key": random_lane["record_public_key"], "events": random_lane["record"]}
(out / "lane_artifact.json").write_text(json.dumps(artifact, separators=(",", ":")), encoding="utf-8")
