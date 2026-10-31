"""Advisory lab wire protocol. No oracle, ledger, gate or signer reaches a lab."""
from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
import json
from pathlib import Path
from typing import Protocol

from jsonschema import Draft202012Validator, ValidationError

from sundai_controller.controller import Design
from .envelope import canonical, check_caps, digest

MAX_MESSAGE_BYTES = 16 * 1024
FAMILIES = ("openai", "claude", "grok", "kimi")
JUDGE_ROLES = ("constraint_auditor", "numerical_skeptic", "reproducibility_auditor")
KINDS = {"propose": "proposal", "review": "review", "repair": "repair"}


@dataclass(frozen=True)
class Request:
    """Immutable JSON context plus core-selected target bindings; never capabilities."""
    context: bytes = b"{}"
    ordinal: int = 0
    target_hash: str | None = None
    target_lab: str | None = None
    review_hash: str | None = None
    judge_role: str | None = None

    def wire(self):
        context = json.loads(self.context)
        check_caps(context)
        return {"context": context, "ordinal": self.ordinal, "target_hash": self.target_hash,
                "target_lab": self.target_lab, "review_hash": self.review_hash,
                "judge_role": self.judge_role}


class Lab(Protocol):
    async def propose(self, request: Request) -> dict: ...
    async def review(self, request: Request) -> dict: ...
    async def repair(self, request: Request) -> dict: ...


@lru_cache(maxsize=3)
def schema_validator(operation):
    kind = KINDS[operation]
    path = Path(__file__).resolve().parents[1] / "schemas" / f"lab-{kind}.json"
    schema = json.loads(path.read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_message(value, operation, lab_id, request, *, max_bytes=MAX_MESSAGE_BYTES):
    """Bound, validate and detach wire data before it becomes a core record."""
    if operation not in KINDS:
        raise ValueError("unknown operation")
    encoded = check_caps(value)
    if len(encoded) > min(max_bytes, MAX_MESSAGE_BYTES):
        raise ValueError("oversize lab message")
    try:
        schema_validator(operation).validate(value)
    except ValidationError as exc:
        raise ValueError("invalid lab schema") from exc
    if value["lab_id"] != lab_id:
        raise ValueError("lab identity mismatch")
    if operation != "propose" and value["target_hash"] != request.target_hash:
        raise ValueError("target envelope mismatch")
    if operation == "review" and value["judge_role"] != request.judge_role:
        raise ValueError("judge assignment mismatch")
    if operation == "repair" and value["review_hash"] != request.review_hash:
        raise ValueError("review envelope mismatch")
    return json.loads(encoded)


def materialize(message, initial: Design) -> Design:
    """A lab may place the fixed catalog, never resize the problem or chiplets."""
    geometry = message["geometry"]
    ids = [row["id"] for row in geometry]
    if len(set(ids)) != len(ids) or set(ids) != {c.id for c in initial.chiplets}:
        raise ValueError("lab geometry catalog mismatch")
    positions = {row["id"]: (row["x_mm"], row["y_mm"]) for row in geometry}
    return replace(initial, positions=tuple(positions[c.id] for c in initial.chiplets))


class ReplayLab:
    """Canned JSON templates; only hash/role bindings are filled from a request.

    Selection is ordinal-based so a restart never depends on a hidden cursor.
    This adapter does no network I/O and makes zero model calls.
    """
    def __init__(self, path):
        with Path(path).open("rb") as handle:
            raw = handle.read(128 * 1024 + 1)
        if len(raw) > 128 * 1024:
            raise ValueError("oversize replay fixture")
        data = json.loads(raw)
        if not isinstance(data, dict) or set(data) != set(KINDS):
            raise ValueError("fixture needs propose, review and repair")
        for messages in data.values():
            if not isinstance(messages, list) or not 1 <= len(messages) <= 16:
                raise ValueError("fixture needs bounded nonempty message lists")
            for message in messages:
                check_caps(message)
        # Store immutable bytes: external fixtures cannot mutate an active adapter.
        self._fixture = canonical(data)
        self.fixture_hash = digest(data)

    def _read(self, operation, request):
        messages = json.loads(self._fixture)[operation]
        message = messages[request.ordinal % len(messages)]
        for field in ("target_hash", "review_hash", "judge_role"):
            if message.get(field) == "$" + field:
                message[field] = getattr(request, field)
        return message

    async def propose(self, request):
        return self._read("propose", request)

    async def review(self, request):
        return self._read("review", request)

    async def repair(self, request):
        return self._read("repair", request)
