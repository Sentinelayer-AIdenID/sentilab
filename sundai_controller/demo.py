"""Deterministic proposal replay against the sibling synthetic thermal solver.

This is a controller/physics-adapter demonstration, NOT a model benchmark.
"""
import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from controller import Chiplet, Controller, Design, FlightRecord, thermal_plate_adapter


async def main():
    initial = Design(25, 25, 0.5,
                     tuple(Chiplet(n, s, s) for n, s in [("compute-a", 6), ("compute-b", 6), ("memory-a", 5), ("memory-b", 5)]),
                     ((2, 2), (9, 2), (2, 10), (9, 10)))
    controller = Controller(initial, thermal_plate_adapter(), max_oracle_calls=12, max_concurrency=2,
                             evaluation_ceiling_microdollars=1)
    key = Ed25519PrivateKey.generate()
    task_ids = [f"replay-{i}" for i in range(9)]
    controller.register("fixture-proposer", key, allowed_tasks=task_ids)
    await controller.initialize()
    baseline = controller.best_temperature
    operations = [
        ("move", {"chiplet": "compute-a", "x_mm": 9, "y_mm": 2}),  # overlap, deterministic rejection
        ("move", {"chiplet": "compute-a", "x_mm": 0, "y_mm": 0}),
        ("move", {"chiplet": "compute-b", "x_mm": 19, "y_mm": 0}),
        ("move", {"chiplet": "memory-a", "x_mm": 0, "y_mm": 20}),
        ("move", {"chiplet": "memory-b", "x_mm": 20, "y_mm": 20}),
        ("move", {"chiplet": "compute-a", "x_mm": 0, "y_mm": 7}),
        ("swap", {"a": "compute-a", "b": "compute-b"}),
    ]
    outcomes = []
    first = None
    for i, (op, args) in enumerate(operations):
        proposal = controller.proposal("fixture-proposer", key, task_ids[i], op, args,
                                      model_id="deterministic-replay-NO-MODEL-CALL", proposal_id=f"fixture-{i}")
        if first is None:
            first = proposal
        outcome = await controller.submit(proposal)
        outcomes.append(asdict(outcome))
    outcomes.append(asdict(await controller.submit(first)))
    await controller.stop("demonstrate STOP after replay")
    proposal = controller.proposal("fixture-proposer", key, task_ids[-1], "move",
                                  {"chiplet": "compute-a", "x_mm": 1, "y_mm": 1})
    outcomes.append(asdict(await controller.submit(proposal)))
    controller.log.close()
    report = {"kind": "deterministic replay controller demonstration; not a Jev/model benchmark",
              "thermal_scope": "synthetic steady-state conductive plate; not silicon junction sign-off",
              "baseline_c": baseline, "final_c": controller.best_temperature,
              "delta_c": controller.best_temperature - baseline,
              "oracle_calls_excluding_baseline": controller.actual_oracle_calls,
              "evaluation_admissions_excluding_baseline": controller.calls,
              "revision": controller.revision, "final_design": asdict(controller.design), "outcomes": outcomes,
              "receipt_public_key": controller.log.public_key,
              "receipt_chain_valid": FlightRecord.verify(controller.log.events, controller.log.public_key)}
    path = Path(__file__).parent
    (path / "demo_results.json").write_text(json.dumps(report, indent=2))
    (path / "demo_flight_record.json").write_text(json.dumps(controller.log.events, indent=2))
    print(json.dumps({k: report[k] for k in ("kind", "baseline_c", "final_c", "delta_c", "revision", "receipt_chain_valid")}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
