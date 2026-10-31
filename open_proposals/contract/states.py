"""The proposal state machine, the revision (idempotency) decision and the submission order. Pure: no I/O, no clock.

Lifecycle (CONTRACT.md, "States"):

    (reply) -> rejected                                                  terminal; reason codes; nothing charged
            -> queued <-> held
               queued -> evaluating -> evaluated -> reproducing -> reproduced -> verifying -> verified
                                    -> failed                   -> not_reproduced           -> not_verified
               failed -> queued                                 operator requeue: a new attempt, both on record
               queued | held -> cancelled | expired             before any reservation; never charged

reproduced is a fresh-process replay on the pinned build ("reproduced under evaluator X"); verified is the stronger
cross-host or cross-build result. Two overlays sit on any state: withdrawn (moderation, restorable; no new work starts
while withdrawn, but in-flight work still settles) and hidden (visibility, with a logged reason). Every event that
starts work needs a reservation id (reserved before launch); every event that ends an attempt needs settled=True.
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, replace
from datetime import datetime

from .codes import GROUPS, ORDER

LIFECYCLE = ("rejected", "queued", "held", "evaluating", "evaluated", "failed", "reproducing", "reproduced",
             "not_reproduced", "verifying", "verified", "not_verified", "cancelled", "expired")
# The ticket's four contract states. cancelled and expired were never evaluated and map to none of them.
SUMMARY = {"rejected": "rejected",
           "queued": "queued", "held": "queued", "evaluating": "queued",
           "evaluated": "evaluated", "failed": "evaluated", "reproducing": "evaluated", "reproduced": "evaluated",
           "not_reproduced": "evaluated", "verifying": "evaluated", "not_verified": "evaluated",
           "verified": "independently_verified",
           "cancelled": None, "expired": None}

REJECTION_CODES = frozenset(GROUPS["transport"] + GROUPS["envelope"] + GROUPS["manifest"] + GROUPS["geometry"]
                            + GROUPS["revision"] + GROUPS["policy"])
# An attempt that ends without a result. router_timeout is not one: the evaluation stands, without a wire verdict.
FAILURE_CODES = frozenset(set(GROUPS["evaluation"]) - {"router_timeout"})
REPRODUCTION_CODES = frozenset(GROUPS["reproduction"])
VERIFICATION_CODES = frozenset(GROUPS["verification"])
POLICY_CODES = frozenset(GROUPS["policy"])
HIDE_REASONS = frozenset({"spam", "not_a_layout"})
UNHIDE_REASONS = frozenset({"reinstated"})
TIERS = frozenset({"cross_host", "cross_build"})

# event -> (states it may start from, state it leads to)
EVENTS = {
    "accept": ((None,), "queued"),
    "reject": ((None,), "rejected"),
    "hold": (("queued",), "held"),
    "release": (("held",), "queued"),
    "start": (("queued",), "evaluating"),
    "complete": (("evaluating",), "evaluated"),
    "fail": (("evaluating",), "failed"),
    "requeue": (("failed",), "queued"),
    "reproduce": (("evaluated",), "reproducing"),
    "reproduced": (("reproducing",), "reproduced"),
    "not_reproduced": (("reproducing",), "not_reproduced"),
    "verify": (("reproduced",), "verifying"),
    "verified": (("verifying",), "verified"),
    "not_verified": (("verifying",), "not_verified"),
    "cancel": (("queued", "held"), "cancelled"),
    "expire": (("queued", "held"), "expired"),
}
OVERLAY_EVENTS = ("withdraw", "restore", "hide", "unhide")
STARTS_WORK = frozenset({"start", "reproduce", "verify", "requeue"})
ENDS_ATTEMPT = frozenset({"complete", "fail", "reproduced", "not_reproduced", "verified", "not_verified"})
OPERATOR_ONLY = frozenset({"hold", "release", "requeue", "withdraw", "restore", "hide", "unhide"})
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")


class TransitionRefused(ValueError):
    """A forbidden transition. The message is a fixed phrase, never input."""


@dataclass(frozen=True)
class Entry:
    lifecycle: str | None = None
    withdrawn: bool = False
    hidden: str | None = None

    @property
    def public_state(self) -> str | None:
        return "withdrawn" if self.withdrawn else self.lifecycle


def _single_code(payload, allowed) -> bool:
    return payload.get("code") in allowed


def _guard(event: str, entry: Entry, payload: dict) -> str | None:
    """The refusal reason, or None when the guard passes."""
    if event in OPERATOR_ONLY and payload.get("operator") is not True:
        return "operator only"
    if event in STARTS_WORK and entry.withdrawn:
        return "withdrawn entries start no new work"
    if event in ("start", "reproduce", "verify"):
        if not isinstance(payload.get("reservation_id"), str) or not UUID.match(payload["reservation_id"]):
            return "work needs a reservation before launch"
    if event in ENDS_ATTEMPT and payload.get("settled") is not True:
        return "an attempt is recorded only after it is settled"
    if event == "reject":
        codes = payload.get("codes")
        if not isinstance(codes, (list, tuple)) or not codes or any(code not in REJECTION_CODES for code in codes):
            return "a rejection needs rejection codes"
    if event == "fail" and not _single_code(payload, FAILURE_CODES):
        return "a failure needs a failure code"
    if event == "reproduced" and payload.get("fresh_process") is not True:
        return "reproduction needs a fresh process"
    if event == "not_reproduced" and not _single_code(payload, REPRODUCTION_CODES):
        return "a failed reproduction needs a reproduction code"
    if event == "verified" and payload.get("tier") not in TIERS:
        return "verification needs a cross-host or cross-build tier"
    if event == "not_verified" and not _single_code(payload, VERIFICATION_CODES):
        return "a failed verification needs a verification code"
    if event == "cancel":
        codes = payload.get("codes", [])
        if not isinstance(codes, (list, tuple)) or any(code not in POLICY_CODES for code in codes):
            return "a cancellation carries policy codes only"
    if event == "hide" and payload.get("reason") not in HIDE_REASONS:
        return "hiding needs a visibility reason"
    if event == "unhide" and payload.get("reason") not in UNHIDE_REASONS:
        return "unhiding needs a visibility reason"
    return None


def transition(entry: Entry, event: str, payload: dict | None = None) -> Entry:
    """The entry after one event, or TransitionRefused. Never mutates its input."""
    payload = {} if payload is None else payload
    if not isinstance(entry, Entry) or not isinstance(payload, dict):
        raise TransitionRefused("invalid input")
    if event in EVENTS:
        sources, target = EVENTS[event]
        if entry.lifecycle not in sources:
            raise TransitionRefused("not allowed from this state")
    elif event in OVERLAY_EVENTS:
        if entry.lifecycle is None:
            raise TransitionRefused("not allowed from this state")
        if event == "withdraw" and entry.withdrawn or event == "restore" and not entry.withdrawn:
            raise TransitionRefused("not allowed from this state")
        if event == "hide" and entry.hidden is not None or event == "unhide" and entry.hidden is None:
            raise TransitionRefused("not allowed from this state")
    else:
        raise TransitionRefused("unknown event")
    refusal = _guard(event, entry, payload)
    if refusal:
        raise TransitionRefused(refusal)
    if event in EVENTS:
        return replace(entry, lifecycle=EVENTS[event][1])
    if event in ("withdraw", "restore"):
        return replace(entry, withdrawn=event == "withdraw")
    return replace(entry, hidden=payload["reason"] if event == "hide" else None)


# ── revisions: the logical key is (account, manifest, proposal_key); identical content is the same revision ──────

@dataclass(frozen=True)
class Revision:
    index: int
    proposal_key: str | None
    proposal_sha256: str | None
    geometry_sha256: str | None
    order: tuple


@dataclass(frozen=True)
class Decision:
    kind: str                       # "duplicate": no new record, same receipt; "new": a new revision
    revision_index: int
    codes: tuple = ()               # revision codes the new revision is rejected with


class OrderError(ValueError):
    """Submissions must be decided in submission order."""


def decide_revision(history, *, proposal_key, proposal_sha256, parent, order) -> Decision:
    """history: this principal's earlier revisions in this manifest, in submission order.

    The first submission of a logical key owns it for good, whatever its outcome. The same key with the same
    canonical content is a duplicate of the earliest such revision. The same key with other content is a new
    revision, rejected as revision_conflict: recorded, never an overwrite. A parent must be the geometry hash of one
    of the principal's own earlier revisions in this manifest.
    """
    history = list(history)
    for index, revision in enumerate(history, start=1):
        if revision.index != index or (index > 1 and not history[index - 2].order < revision.order):
            raise OrderError("history is not in submission order")
    if history and not history[-1].order < order:
        raise OrderError("a submission is decided after every earlier one")
    if proposal_key is not None and proposal_sha256 is not None:
        for revision in history:
            if revision.proposal_key == proposal_key and revision.proposal_sha256 == proposal_sha256:
                return Decision("duplicate", revision.index)
    codes = []
    if proposal_key is not None and any(revision.proposal_key == proposal_key for revision in history):
        codes.append("revision_conflict")
    if parent is not None and parent not in {revision.geometry_sha256 for revision in history}:
        codes.append("unknown_parent")
    return Decision("new", len(history) + 1, tuple(sorted(codes, key=ORDER.__getitem__)))


# ── submission order: numeric createdAt, then the full action id, then the room ─────────────────────────────────

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
    """One Senti reply row: (createdAt, id, sessionId). A reply has no sequence of its own."""
    return (created_at_ns(row["createdAt"]), row["id"], row["sessionId"])


def sort_replies(rows) -> list:
    return sorted(rows, key=order_key)
