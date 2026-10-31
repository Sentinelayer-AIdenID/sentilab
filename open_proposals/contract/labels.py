"""The SLAB-053 label rule, mirrored from web/public/temperature-label.mjs without importing it.

The state names and the three identity lists are data in contracts/open-proposal-v1/labels.json. One value from one
evaluator identity: withdrawn if the identity's engine:commit is on the withdrawn list (case-insensitive, every build);
illustrative if it is exactly the fixture identity; accepted if it is exactly on the accepted list (empty for now);
otherwise unvalidated. A value derived from several takes the most cautious state: withdrawn if any input is,
illustrative or accepted only if every input is, otherwise unvalidated (including no inputs at all).
"""
from __future__ import annotations

import json
from pathlib import Path

LABELS_PATH = Path(__file__).resolve().parents[2] / "contracts" / "open-proposal-v1" / "labels.json"


def load_lists(path: Path = LABELS_PATH) -> dict:
    data = json.loads(path.read_bytes())
    return {"withdrawn": tuple(data["withdrawn"]), "illustrative": tuple(data["illustrative"]),
            "accepted": tuple(data["accepted"])}


LISTS = load_lists()


def evaluator_key(identity: str) -> str:
    """The leading engine:commit of an identity, compared without case."""
    return ":".join(identity.strip().split(":")[:2]).lower()


def label_for(identity, lists: dict = LISTS) -> str:
    if not isinstance(identity, str) or identity.strip() == "":
        return "unvalidated"
    if evaluator_key(identity) in {item.lower() for item in lists["withdrawn"]}:
        return "withdrawn"
    if identity in lists["illustrative"]:
        return "illustrative"
    if identity in lists["accepted"]:
        return "accepted"
    return "unvalidated"


def label_for_all(identities, lists: dict = LISTS) -> str:
    labels = [label_for(identity, lists) for identity in identities]
    if "withdrawn" in labels:
        return "withdrawn"
    if labels and all(label == "illustrative" for label in labels):
        return "illustrative"
    if labels and all(label == "accepted" for label in labels):
        return "accepted"
    return "unvalidated"
