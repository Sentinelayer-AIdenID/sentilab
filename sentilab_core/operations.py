"""The shared live operations used by CLI, MCP and the service owner."""
from dataclasses import dataclass, field
import importlib
import json
import os
from pathlib import Path

from .conductor import Conductor, LABELS
from .envelope import validate_run_id
from .ledger import atomic_json, lock, replay
from .projection import board, project


@dataclass
class Context:
    root: Path
    public_keys: dict
    signer: object = None
    options: dict = field(default_factory=dict)


def require_ai_off(ai_off):
    if ai_off is not True:
        raise ValueError("this release requires --ai-off")


async def run(context, *, ai_off, run_id=None, duration=600, interval=15, renew=False, max_ticks=None):
    require_ai_off(ai_off)
    if context.signer is None:
        raise ValueError("only the service with an injected signer may run the conductor")
    conductor = Conductor(context.root, signer=context.signer, public_keys=context.public_keys, **context.options)
    return await conductor.run(run_id=run_id, duration=duration, interval=interval, renew=renew, max_ticks=max_ticks)


def verify(context, *, ai_off, run_id):
    require_ai_off(ai_off)
    state = replay(context.root, run_id, public_keys=context.public_keys)
    return verified_state(state, run_id)


def verified_state(state, run_id):
    try:
        projection = project(state["prefix"])
        current = board(state["prefix"], projection)
        projection_error = None
    except (KeyError, ValueError, TypeError, RecursionError) as exc:
        projection, current, projection_error = None, None, type(exc).__name__
    return {"run_id": run_id, "ok": state["error"] is None and projection_error is None,
            "prefix_end": state["last_seq"], "head_hash": state["head_hash"],
            "chain_error": state["error"], "projection_error": projection_error,
            "projection": projection, "board": current, **LABELS}


def status(context, *, ai_off, run_id=None):
    require_ai_off(ai_off)
    if run_id is not None:
        return verify(context, ai_off=True, run_id=run_id)
    rows = []
    if context.root.exists():
        for path in sorted(context.root.glob("*.jsonl")):
            try:
                validate_run_id(path.stem)
                state = replay(context.root, path.stem, public_keys=context.public_keys)
                meta_path = context.root / f"{path.stem}.meta.json"
                meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
                run_info = state["prefix"][0]["run"] if state["prefix"] else {"run_id": path.stem}
                rows.append({**run_info, "seq": state["last_seq"], "last_seq": state["last_seq"],
                             "status": meta.get("status", "unknown"), "chain_error": state["error"], **LABELS})
            except (ValueError, OSError):
                continue
    return {"runs": rows, "stopped": (context.root / "STOP").exists(), **LABELS}


def stop(context, *, ai_off):
    require_ai_off(ai_off)
    context.root.mkdir(parents=True, exist_ok=True)
    with lock(context.root / "admission.lock"):
        atomic_json(context.root / "STOP", {"stopped": True})
    return {"stopped": True, **LABELS}


def environment_context(*, ephemeral=False):
    root = Path(os.environ.get("SENTILAB_LIVE_DIR", "/tmp/sentilab-live"))
    # Operator configuration is the trust anchor, independent of ledger files
    # and /api/view/key. Public keys are not credentials.
    public_keys = {key: bytes.fromhex(value) for key, value in
                   json.loads(os.environ.get("SENTILAB_VIEW_PUBLIC_KEYS", "{}")).items()}
    signer = None
    factory = os.environ.get("SENTILAB_SIGNER_FACTORY")
    if factory:
        module, name = factory.split(":", 1)
        signer = getattr(importlib.import_module(module), name)()
        if public_keys.get(signer.key_id) != signer.public_key:
            raise ValueError("injected signer does not match operator trust pin")
    elif ephemeral:
        from .signing import ephemeral_signer
        signer = ephemeral_signer()
        public_keys = {signer.key_id: signer.public_key}
    return Context(root, public_keys, signer)
