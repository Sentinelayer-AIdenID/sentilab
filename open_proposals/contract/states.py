"""The proposal state machine, the idempotency decisions and the submission order (DESIGN rev 3 sections 3.4, 7.1,
7.3 and 5.6). Pure: no I/O, no clock.

    reply -> rejected                                      terminal; codes; no quota charge
          -> queued -> evaluating -> evaluated -> replaying -> reproduced -> (optional) cross_checked
             queued <-> held       evaluating -> failed      replaying -> not_reproduced
                                   evaluated -> failed                    (charged; no automatic retry)
             queued | held -> cancelled | expired          before any reservation; no quota charge
    hidden: a public-view flag from moderation, with a reason; nothing is deleted
    publish: a private entry becomes public only through its participant's sealed publish command, after the terms
             and ownership checks pass; a refused publication changes nothing and is reported only privately

Every event that starts work needs a reservation id (reserved before launch); every event that ends an attempt
needs settled=True (settled on every exit). There is no retry edge: a failure is retained and never re-run.
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, replace
from datetime import datetime

from .codes import GROUPS, ORDER

LIFECYCLE = ("rejected", "queued", "held", "evaluating", "evaluated", "failed", "replaying", "reproduced",
             "not_reproduced", "cross_checked", "cancelled", "expired")
# The contract's four states (section 7.1). Rev 3 maps replaying and not_reproduced to none of them; both come after
# an evaluation, so they read "evaluated". cancelled and expired were never evaluated and map to none.
SUMMARY = {"rejected": "rejected",
           "queued": "queued", "held": "queued", "evaluating": "queued",
           "evaluated": "evaluated", "failed": "evaluated", "replaying": "evaluated", "not_reproduced": "evaluated",
           "reproduced": "independently verified", "cross_checked": "independently verified",
           "cancelled": None, "expired": None}
# Whether the entry counts against participant quotas (section 7.1). Sponsor CPU is recorded either way (intake).
CHARGED = {"rejected": False, "queued": False, "held": False, "evaluating": True, "evaluated": True, "failed": True,
           "replaying": True, "reproduced": True, "not_reproduced": True, "cross_checked": True, "cancelled": False,
           "expired": False}
# The ledger lifecycle each state records (section 7.1). A rejection is rejected_constraints for a geometry code and
# rejected_schema otherwise (rev 3 names both without the split).
LEDGER = {"queued": "new", "held": "new", "evaluating": "simulation_pending", "evaluated": "evaluated",
          "failed": "failed_run", "replaying": "reproduction_pending", "reproduced": "reproduced",
          "not_reproduced": "reproduction_failed", "cross_checked": "verify.add", "cancelled": "cancelled",
          "expired": "expired"}

REJECTION_CODES = frozenset(GROUPS["transport"] + GROUPS["envelope"] + GROUPS["manifest"] + GROUPS["geometry"]
                            + GROUPS["revision"] + GROUPS["policy"])
# failed: timeout, oracle_error, stopped, grant_expired or interrupted (section 7.1), exactly one.
FAILURE_CODES = frozenset({"timeout", "stopped", "oracle_error", "grant_expired", "interrupted"})
# An evaluation that stands with a qualification: W reads UNKNOWN, or the affected claims are suppressed.
QUALIFIER_CODES = frozenset({"router_timeout", "binding_mismatch"})
REPRODUCTION_CODES = frozenset(GROUPS["reproduction"])
POLICY_CODES = frozenset(GROUPS["policy"])
HIDE_REASONS = frozenset({"spam", "abuse", "not_a_layout"})
RESTORE_REASONS = frozenset({"reinstated"})
CROSS_TIERS = frozenset({"cross_build", "cross_arch"})

# event -> (states it may start from, state it leads to)
EVENTS = {
    "accept": ((None,), "queued"),
    "reject": ((None,), "rejected"),
    "hold": (("queued",), "held"),
    "release": (("held",), "queued"),
    "start": (("queued",), "evaluating"),
    "complete": (("evaluating",), "evaluated"),
    "fail": (("evaluating", "evaluated"), "failed"),
    "replay": (("evaluated",), "replaying"),
    "reproduced": (("replaying",), "reproduced"),
    "not_reproduced": (("replaying",), "not_reproduced"),
    "cross_checked": (("reproduced",), "cross_checked"),
    "cancel": (("queued", "held"), "cancelled"),
    "expire": (("queued", "held"), "expired"),
}
FLAG_EVENTS = ("hide", "restore", "publish")
STARTS_WORK = frozenset({"start", "replay"})
ENDS_ATTEMPT = frozenset({"complete", "fail", "reproduced", "not_reproduced", "cross_checked"})
OPERATOR_ONLY = frozenset({"hold", "release", "hide", "restore"})
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")


class TransitionRefused(ValueError):
    """A forbidden transition. The message is a fixed phrase, never input."""


@dataclass(frozen=True)
class Entry:
    state: str | None = None
    hidden: str | None = None       # the moderation reason while hidden from public views
    visibility: str = "private"     # the proposal's choice; private until a sealed publish command succeeds


def ledger_lifecycle(state: str, codes=()) -> str:
    if state == "rejected":
        return "rejected_constraints" if any(code in GROUPS["geometry"] for code in codes) else "rejected_schema"
    return LEDGER[state]


def _codes(payload) -> list | None:
    codes = payload.get("codes", [])
    if not isinstance(codes, (list, tuple)) or not all(isinstance(code, str) for code in codes):
        return None
    return list(codes)


def _one_of(value, allowed) -> bool:
    return isinstance(value, str) and value in allowed


def _guard(event: str, entry: Entry, payload: dict) -> str | None:
    """The refusal reason, or None when the guard passes."""
    if event in OPERATOR_ONLY and payload.get("operator") is not True:
        return "operator only"
    if event in STARTS_WORK:
        if not isinstance(payload.get("reservation_id"), str) or not UUID.match(payload["reservation_id"]):
            return "work needs a reservation before launch"
    if event in ENDS_ATTEMPT and payload.get("settled") is not True:
        return "an attempt is recorded only after it is settled"
    codes = _codes(payload)
    if codes is None:
        return "codes are a list of code names"
    if event == "reject" and (not codes or any(code not in REJECTION_CODES for code in codes)):
        return "a rejection needs rejection codes"
    if event == "fail" and (len(codes) != 1 or codes[0] not in FAILURE_CODES):
        return "a failure needs one failure code"
    if event == "complete" and any(code not in QUALIFIER_CODES for code in codes):
        return "an evaluation carries qualifier codes only"
    if event == "reproduced" and payload.get("fresh_process") is not True:
        return "reproduction needs a fresh process"
    if event == "not_reproduced" and (len(codes) != 1 or codes[0] not in REPRODUCTION_CODES):
        return "a failed reproduction needs one reproduction code"
    if event == "cross_checked" and not _one_of(payload.get("tier"), CROSS_TIERS):
        return "a cross-check needs a cross_build or cross_arch tier"
    if event == "cancel" and any(code not in POLICY_CODES for code in codes):
        return "a cancellation carries policy codes only"
    if event in ("accept", "hold", "release", "start", "replay", "reproduced", "cross_checked", "expire",
                 "hide", "restore") and codes:
        return "this event carries no codes"
    if event == "publish" and payload.get("sealed") is not True:
        return "publication is a sealed command"
    if event == "publish" and codes:
        return "a refused publication changes nothing"
    if event == "hide" and not _one_of(payload.get("reason"), HIDE_REASONS):
        return "hiding needs a moderation reason"
    if event == "restore" and not _one_of(payload.get("reason"), RESTORE_REASONS):
        return "restoring needs a moderation reason"
    return None


def transition(entry: Entry, event: str, payload: dict | None = None) -> Entry:
    """The entry after one event, or TransitionRefused. Never mutates its input."""
    payload = {} if payload is None else payload
    if not isinstance(entry, Entry) or not isinstance(payload, dict):
        raise TransitionRefused("invalid input")
    if event in EVENTS:
        sources, _target = EVENTS[event]
        if entry.state not in sources:
            raise TransitionRefused("not allowed from this state")
    elif event == "publish":
        if entry.state is None or entry.visibility != "private":
            raise TransitionRefused("not allowed from this state")
    elif event in FLAG_EVENTS:
        if entry.state is None or (event == "hide") != (entry.hidden is None):
            raise TransitionRefused("not allowed from this state")
    else:
        raise TransitionRefused("unknown event")
    refusal = _guard(event, entry, payload)
    if refusal:
        raise TransitionRefused(refusal)
    if event in EVENTS:
        return replace(entry, state=EVENTS[event][1])
    if event == "publish":
        return replace(entry, visibility="public")
    return replace(entry, hidden=payload["reason"] if event == "hide" else None)


# ── idempotency: the logical key is (account, manifest, kind, key); identical content is the same row ─────────────

@dataclass(frozen=True)
class Prior:
    """One of this account's earlier accepted rows in this manifest, in submission order."""
    kind: str                       # proposal | check_request | team | publish
    logical_key: str
    content_sha256: str
    geometry_sha256: str | None
    order: tuple


@dataclass(frozen=True)
class Decision:
    kind: str                       # "duplicate": the earlier row's receipt; "new": a new revision
    revision_index: int             # the duplicate's index, or the new revision's
    codes: tuple = ()               # the revision codes a new revision is rejected with


class OrderError(ValueError):
    """Rows must be decided in submission order."""


def _check_history(history, order) -> list:
    history = list(history)
    for index in range(1, len(history)):
        if not history[index - 1].order < history[index].order:
            raise OrderError("history is not in submission order")
    if history and not history[-1].order < order:
        raise OrderError("a row is decided after every earlier one")
    return history


def decide(history, *, kind: str, logical_key: str, content_sha256: str, parent: str | None = None,
           order: tuple) -> Decision:
    """Section 7.3. history: this account's earlier accepted rows in this manifest, in the section 3.4 order. A refused
    row (any rejection, a policy refusal with retry_after included) is not history and never owns its logical key.

    The same logical key with the same content is a duplicate of the earliest such row: no new record, the same
    receipt. The same logical key with other content is a new row rejected with idempotency_conflict: the earliest
    row wins, and the conflict is recorded, never an overwrite. A proposal's parent must be the geometry hash of one
    of the account's own earlier proposals in this manifest. Keys are compared within one kind, so a proposal_key
    never collides with a request_key or the team key. The revision index counts the account's distinct rows of
    that kind in this manifest.
    """
    history = _check_history(history, order)
    same_kind = [prior for prior in history if prior.kind == kind]
    for index, prior in enumerate(same_kind, start=1):
        if prior.logical_key == logical_key and prior.content_sha256 == content_sha256:
            return Decision("duplicate", index)
    codes = []
    if any(prior.logical_key == logical_key for prior in same_kind):
        codes.append("idempotency_conflict")
    proposals = [prior.geometry_sha256 for prior in history if prior.kind == "proposal"]
    if kind == "proposal" and parent is not None and parent not in proposals:
        codes.append("unknown_parent")
    return Decision("new", len(same_kind) + 1, tuple(sorted(codes, key=ORDER.__getitem__)))


def decide_publish(history, *, proposal_sha256: str, order: tuple) -> tuple:
    """Section 5.6: a publish reply names one of the same account's own earlier proposals in this manifest.
    Returns the codes it is rejected with: unknown_proposal, or none."""
    history = _check_history(history, order)
    own = {prior.content_sha256 for prior in history if prior.kind == "proposal"}
    return () if proposal_sha256 in own else ("unknown_proposal",)


# ── submission order: numeric createdAt, then the full action id, then the room id ──────────────────────────────

TIME = re.compile(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})\Z")


def created_at_ns(text: str) -> int:
    """Nanoseconds since the epoch, exactly. Senti writes isoformat(): the fraction is absent at whole seconds, so
    the strings don't sort as text."""
    match = TIME.match(text) if isinstance(text, str) else None
    if not match:
        raise ValueError("invalid createdAt")
    year, month, day, hour, minute, second = (int(part) for part in match.groups()[:6])
    datetime(year, month, day, hour, minute, second)        # refuses impossible dates and times
    fraction = int((match.group(7) or "").ljust(9, "0"))
    zone = match.group(8)
    offset = 0
    if zone != "Z":
        hours, minutes = int(zone[1:3]), int(zone[4:6])
        if hours > 23 or minutes > 59:
            raise ValueError("invalid createdAt")
        offset = (hours * 60 + minutes) * 60 * (1 if zone[0] == "+" else -1)
    seconds = calendar.timegm((year, month, day, hour, minute, second)) - offset
    return seconds * 1_000_000_000 + fraction


def order_key(row: dict) -> tuple:
    """One Senti reply row: (createdAt, id, sessionId). The target sequence orders nothing (section 3.4)."""
    return (created_at_ns(row["createdAt"]), row["id"], row["sessionId"])


def sort_replies(rows) -> list:
    return sorted(rows, key=order_key)
