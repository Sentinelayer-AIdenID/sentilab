"""Print deterministic interface proof; signing material lives only in RAM."""
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from sentilab_core.envelope import digest
from sentilab_core.ledger import Ledger
from sentilab_core.memory import MemoryStore
from sentilab_core.routing import load_router_fixture
from sentilab_core.signing import ephemeral_signer


def reproduce():
    directory = Path(__file__).resolve().parent
    fixture = json.loads((directory / "memory-fixture.json").read_text())
    scope = fixture["scope"]
    signer = ephemeral_signer()
    public_keys = {signer.key_id: signer.public_key}
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        run = {"run_id": scope["run"], **{key: scope[key] for key in ("arm", "family", "seed")},
               "ticket_id": "23a5285a"}
        ledger = Ledger(root, run, public_keys=public_keys, signer=signer)
        for index, event in enumerate(fixture["events"]):
            ledger.append(event["type"], event["body"], event_id=f"fixture-{index}")
        store = MemoryStore(root / "memory", ledger_root=root, public_keys=public_keys,
                            tenant=scope["tenant"], held_out_families=fixture["held_out_families"])
        for memory in fixture["memories"]:
            store.write(scope, **memory)
        before = [row["item"]["id"] for row in store.recall(scope)]
        correction = fixture["correction"]
        ledger.append(correction["type"], correction["body"], event_id="correction")
        after = [row["item"]["id"] for row in store.recall(scope)]
        audit = [row["item"]["id"] for row in store.audit(scope)]
        assert before == fixture["expected_before"] and after == fixture["expected_after"]
        assert audit == before
        invalidated = store.invalidate(scope)
        assert {row["id"]: row["invalid_evidence"] for row in invalidated} == fixture["expected_invalid_evidence"]
        try:
            store.write({**scope, "family": "evaluation-a"}, {"id": "heldout"}, ["measurement-b"])
        except ValueError as exc:
            heldout_error = str(exc)
        else:
            raise AssertionError("held-out write succeeded")
        assert store.recall({**scope, "run": "other-run"}) == []
    router, heldout = load_router_fixture(directory / "routing-fixtures.json")
    try:
        router.route({"candidate": "unregistered", "score": 0})
    except ValueError as exc:
        unknown_error = str(exc)
    else:
        raise AssertionError("unknown route succeeded")
    return {"schema": "slab010-interface-proof/1", "model_calls": 0, "solves": 0,
            "memory_fixture_digest": digest(fixture),
            "routing_fixture_digest": digest(json.loads((directory / "routing-fixtures.json").read_text())),
            "memory": {"before": before, "after_withdrawal": after, "audit": audit,
                       "invalidated": invalidated, "heldout_write": heldout_error, "cross_run_recall": []},
            "unknown_route": unknown_error, "routing": router.calibrate(heldout)}


if __name__ == "__main__":
    print(json.dumps(reproduce(), indent=2, allow_nan=False))
