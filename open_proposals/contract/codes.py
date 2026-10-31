"""The fixed reason-code vocabulary (contracts/open-proposal-v1/reason-codes.json) and its canonical order."""
from __future__ import annotations

import json

from sentilab_core.envelope import canonical

from .schemas import CONTRACT_DIR

VOCABULARY = json.loads((CONTRACT_DIR / "reason-codes.json").read_bytes())
ORDER = {}
FIELDS = {}
GROUP = {}
for _group in VOCABULARY["groups"]:
    for _entry in _group["codes"]:
        ORDER[_entry["code"]] = len(ORDER)
        FIELDS[_entry["code"]] = tuple(_entry["fields"])
        GROUP[_entry["code"]] = _group["group"]
GROUPS = {group["group"]: tuple(entry["code"] for entry in group["codes"]) for group in VOCABULARY["groups"]}
RULES = tuple(VOCABULARY["rules"])
# At most 64 violations per list: the envelope's per-list cap (sentilab_core/envelope.py MAX_ITEMS). A rejection is
# decided before the list is cut, so the cap never changes an outcome.
MAX_VIOLATIONS = 64


def violation(code: str, **fields) -> dict:
    """One violation, with exactly the fields its code declares."""
    if code not in FIELDS:
        raise ValueError("unknown reason code")
    if set(fields) != set(FIELDS[code]):
        raise ValueError("a violation carries exactly its code's fields")
    return {"code": code, **fields}


def fields_ok(item) -> bool:
    return (isinstance(item, dict) and item.get("code") in FIELDS
            and set(item) - {"code"} == set(FIELDS[item["code"]]))


def sort_key(item: dict):
    return (ORDER[item["code"]], item.get("path", ""), item.get("dies", []), canonical(item))


def canonical_list(items) -> list:
    """Deduplicated, in canonical order (vocabulary order, then path, dies and bytes), cut to MAX_VIOLATIONS."""
    unique = {canonical(item): item for item in items}
    return sorted(unique.values(), key=sort_key)[:MAX_VIOLATIONS]
