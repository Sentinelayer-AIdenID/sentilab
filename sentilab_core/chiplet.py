"""CPU fixture entry points over the controller, ledger and browser view model.

Build validates geometry only. Render returns the existing browser panel model,
not a simulation or a screenshot. Replay/export require independently pinned
signatures and refuse any damaged history. No solver or device is invoked.
"""
import json
from pathlib import Path
import subprocess

from .conductor import design_record
from .ledger import replay as read_ledger


def build(context, *, fixture="plate", positions=None):
    from sundai_controller.experiment import plate_initial_design

    if fixture != "plate":
        raise ValueError("unsupported chiplet fixture")
    design = plate_initial_design()
    if positions is not None:
        design = design.apply("place", {"positions": positions})
    design.check()
    return {"fixture": fixture, "design": design_record(design), "design_hash": design.hash,
            "scope": "fixture geometry only; no simulation"}


def _verified(context, run_id):
    state = read_ledger(context.root, run_id, public_keys=context.public_keys)
    if state["error"] or not state["prefix"]:
        raise ValueError("chiplet history verification failed")
    return state


def replay(context, *, run_id):
    from .operations import verified_state

    state = _verified(context, run_id)
    result = verified_state(state, run_id)
    if not result["ok"]:
        raise ValueError("chiplet projection failed")
    return result


def render(context, *, run_id, cursor=None):
    state = _verified(context, run_id)
    source = """import { buildView } from './web/public/sentilab/lab-model.mjs';
let text=''; for await (const chunk of process.stdin) text+=chunk;
const {ordered, cursor}=JSON.parse(text);
const view=buildView({ordered,prefix:ordered.length},cursor ?? ordered.length);
if (view.projectionError || view.rejected.size) process.exit(2);
console.log(JSON.stringify({...view,rejected:[...view.rejected]}));"""
    result = subprocess.run(["node", "--input-type=module", "-e", source],
                            input=json.dumps({"ordered": state["prefix"], "cursor": cursor}),
                            text=True, capture_output=True, timeout=10,
                            cwd=Path(__file__).resolve().parents[1])
    if result.returncode:
        raise ValueError("chiplet view projection failed")
    return {"run_id": run_id, "head_hash": state["head_hash"],
            "format": "sentilab-browser-view/1", "view": json.loads(result.stdout)}


def export(context, *, run_id, output_dir=None, policy=None):
    from .dataset import export as export_dataset

    return export_dataset(context.root, [run_id], public_keys=context.public_keys,
                          output_dir=output_dir, policy=policy)
