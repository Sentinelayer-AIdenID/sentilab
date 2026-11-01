"""The scorer seam: score(request) -> Score and health() -> bool. The real scorer is warden's door-scorer (ticket
b6230a56; sentilab PR #79, research/agent-door/scorer, +1 at 00a8a82a). HttpScorer is the only code that knows its
wire format; everything else reads Score.

    GET  {DOOR_SCORER_URL}/v1/health   -> 200 {"ok": true, "binary_sha256", "grant_id", "image_digest", ...}
    POST {DOOR_SCORER_URL}/v1/score    {"run_id", "token_ref", "proposal"}
         -> 200 {"run_id", "state": "evaluated", "metric_id", "max_chiplet_centre_mean_c", "native_all_block_max_C",
                 "active_layer_peak_C", "per_die_c", "wire_proxy_mm", "metric_precision", "references", "receipt"}
         -> 200 {"run_id", "state": "failed", "codes": [timeout | interrupted | oracle_error], "receipt"}
    POST {DOOR_SCORER_URL}/v1/replay   the same body, after a successful score: a fresh supervisor, solver and directory
         -> 200 {"run_id", "state": "reproduced" | "not_reproduced", "codes", "receipts": [score's, replay's], ...}
    4xx: refused before any reservation or solve (401, 403 budget_exhausted, 409, 422 rejected, 429 busy)
    Every call carries Authorization: Bearer {DOOR_SCORER_TOKEN}; retries of the same body are idempotent there.

token_ref is the door's contract participant_ref, HMAC(DOOR_K_CHALLENGE, "anon-token/1:" + sha256(nonce)). The scorer
checks run_id == run_id(manifest_id, token_ref, proposal_sha256), so the run id is the same on both sides, and the
scorer keys its per-token CPU on a pseudonym it cannot link to a nonce.

Every answer is bound to the request before it counts (root's review of #81, P1):
- the answer's run_id is the request's; every receipt names the request's manifest and geometry, the pinned binary,
  the door's grant and the scorer image the signed binding pins, a reservation, a workspace, the worker and engine
  processes, the input and output hashes, and its CPU;
- a replay counts only when its first receipt is exactly the accepted score's receipt and its second is a distinct
  execution (another reservation, workspace, worker and engine), and reproduction is the door's own finding: the
  same input and output hashes and the same numbers, never the reported state alone.

Outcomes. An attempt ends only on a definitive answer: a bound evaluation (whatever its replay found), the scorer's own
`failed` answer, an answer that cannot be bound (the scorer did answer), a refusal or a connection that never opened.
Anything ambiguous (a timeout or 5xx after the request was sent, an unreadable answer, a busy replay) is a ScorerError
with definitive=False: the attempt stays open, holding its slot and envelope, until a retry of the same request
resolves it. Reported CPU is kept as a lower bound wherever an answer carries one, and usage that was not fully
measured is never called measured.
"""
from __future__ import annotations

import http.client
import json
import math
import re
import socket
import ssl
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from sentilab_core.envelope import canonical

METRIC_ID = "max_chiplet_centre_cell_mean_C"
METRIC = {"metric_id": METRIC_ID,
          "definition": ("per real chiplet (Chiplet_0..7), the mean of its 1, 2 or 4 central HotSpot 6.0 grid-64 "
                         "cells (GRID_CENTER), then the maximum over the chiplets"),
          "unit": "C", "precision_K": 0.01,
          "reference": {"layout": "raw", "value_C": 115.935}}
ACTIVE_GUARD_C = 119.07
BINDING_TOLERANCE_K = 0.005          # half the grid's 0.01 K print precision
EVALUATOR_BINARY_SHA256 = "751b357f6b5af395a4447d6e3bfeef3a75eb447091798365a3db4f0e00618cc6"
REPLAY_RESERVE_CPU_S = 10.0          # door-scorer's reservation for one call (ledger.RESERVE)
GRID = 64
DIES = ("C0", "C1", "C2", "C3", "D0", "D1", "D2", "D3")
MAX_RECEIPT_BYTES = 16 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024
REASONS = ("scorer_down", "scorer_timeout", "scorer_error", "scorer_refused", "scorer_cutoff", "grant_expired",
           "interrupted")
SCORER_FAILURE = {"timeout": "scorer_timeout", "interrupted": "interrupted", "oracle_error": "scorer_error",
                  "stopped": "scorer_cutoff", "grant_expired": "grant_expired"}
REPLAY_CODES = ("reproduction_mismatch", "reproduction_failed")
# The numbers a reproduction must repeat exactly (door-scorer compares every field; these are the ones the door uses).
REPEATED = ("max_chiplet_centre_mean_c", "peak_c", "native_all_block_max_c", "native_all_block_max_C",
            "active_grid_max_c", "active_layer_peak_C", "per_die_c", "wire_proxy_mm", "grid64")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
IMAGE = re.compile(r"sha256:[0-9a-f]{64}\Z")


class ScorerError(Exception):
    """A call that produced no score. began: the scorer may have done work. definitive: the attempt is over (the
    scorer answered, refused, or was never reached); otherwise its outcome is unknown and the attempt stays open.
    cpu_s is a lower bound when an answer reported one; reply keeps a bounded copy of an answer for the record."""

    def __init__(self, reason: str, *, began: bool, cpu_s: float | None = None, definitive: bool = True,
                 reply=None):
        if reason not in REASONS:
            raise ValueError("unknown scorer failure")
        super().__init__(reason)
        self.reason, self.began, self.cpu_s, self.definitive, self.reply = reason, began, cpu_s, definitive, reply


@dataclass(frozen=True)
class Score:
    max_chiplet_centre_cell_mean_C: float
    native_all_block_max_C: float
    active_layer_peak_C: float
    per_die_C: dict                  # each real chiplet's centre-cell mean, C, keyed C0..C3, D0..D3
    grid64: tuple | None             # the 64 x 64 active-layer map (row 0 at the top), when the scorer returns one
    wire_proxy_mm: float | None      # the scorer's own proxy, checked against the door's
    replay_fresh_process: bool       # a distinct execution, by its receipts
    replay_match: bool               # the door found the same hashes and numbers, and the scorer said reproduced
    replay_code: str | None          # reproduction_mismatch, reproduction_failed or fresh_process_required
    cpu_s: float                     # score plus replay: measured, or a conservative lower bound (cpu_known False)
    evaluator_binary_sha256: str
    receipt: dict                    # {"score": <receipt>, "replay": <receipt or None>, "replay_reply": <raw or None>}
    metric: dict = field(default_factory=lambda: dict(METRIC))
    receipts_bound: bool = True      # the replay's receipts are bound to this request and the accepted score
    cpu_known: bool = True

    @property
    def metric_id(self) -> str:
        return self.metric["metric_id"]


def _temperature(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("a temperature is a finite number")
    if not -273.15 <= value <= 1000:
        raise ValueError("a temperature out of range")
    return float(value)


def cpu_seconds(value):
    """A CPU figure, or None when it is not a finite number in [0, 1e6]."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value) if 0 <= value <= 1_000_000 else None


def reported_cpu(payload):
    """The CPU an answer reports for its own call, read before any other check: a lower bound. That is its receipt
    and, for a replay, its last receipt (the first one is the score's, already counted)."""
    if not isinstance(payload, dict):
        return None
    receipts = [payload.get("receipt")]
    if isinstance(payload.get("receipts"), list) and payload["receipts"]:
        receipts.append(payload["receipts"][-1])
    values = [cpu_seconds(item.get("cpu_s")) for item in receipts if isinstance(item, dict)]
    values = [value for value in values if value is not None]
    return max(values) if values else None


def bounded(payload):
    """A copy of an answer small enough to keep."""
    try:
        return payload if len(canonical(payload)) <= MAX_RECEIPT_BYTES else {"oversize": True}
    except (TypeError, ValueError):
        return {"unserializable": True}


def _same(payload: dict, names: tuple):
    """The one value several aliases carry, or ValueError if they disagree or none is present."""
    values = [payload[name] for name in names if name in payload]
    if not values or any(value != values[0] for value in values):
        raise ValueError("missing or disagreeing aliases")
    return _temperature(values[0])


def _hashes(value) -> bool:
    return (isinstance(value, dict) and 0 < len(value) <= 64
            and all(isinstance(key, str) and isinstance(item, str) and HEX64.match(item)
                    for key, item in value.items()))


def bound_receipt(receipt, expected: dict) -> tuple:
    """(receipt, CPU) when the receipt is this request's, from the pinned producer, with full execution evidence."""
    if not isinstance(receipt, dict) or len(canonical(receipt)) > MAX_RECEIPT_BYTES:
        raise ValueError("receipt")
    if any(receipt.get(name) != value for name, value in expected.items()):
        raise ValueError("the receipt is not this request's")
    for name, limit in (("reservation_id", 128), ("workspace_id", 256)):
        if not isinstance(receipt.get(name), str) or not 0 < len(receipt[name]) <= limit:
            raise ValueError("execution evidence")
    for name in ("worker_pid", "engine_pid"):
        if isinstance(receipt.get(name), bool) or not isinstance(receipt.get(name), int) or receipt[name] <= 0:
            raise ValueError("execution evidence")
    if not _hashes(receipt.get("input_sha256")) or not _hashes(receipt.get("output_sha256")):
        raise ValueError("input and output hashes")
    cpu = cpu_seconds(receipt.get("cpu_s"))
    if cpu is None:
        raise ValueError("receipt CPU")
    return receipt, cpu


def parse_evaluation(payload, *, expected: dict, run_id: str) -> dict:
    """The fields of an `evaluated` answer to this request, or ValueError. Strict: this run, a bound receipt, the
    frozen metric and its reference, the three statistics apart (aliases must agree), all eight chiplets, the wire."""
    if (not isinstance(payload, dict) or payload.get("run_id") != run_id or payload.get("state") != "evaluated"
            or payload.get("metric_id") != METRIC_ID):
        raise ValueError("not an evaluation of this run's frozen metric")
    precision = payload.get("metric_precision")
    if precision is not None and (not isinstance(precision, dict) or precision.get("grid_resolution_K") != 0.01):
        raise ValueError("metric precision")
    references = payload.get("references")
    if references is not None:
        raw = references.get("raw") if isinstance(references, dict) else None
        if not isinstance(raw, dict) or raw.get("max_chiplet_centre_mean_c") != METRIC["reference"]["value_C"]:
            raise ValueError("the raw reference binding")
    receipt, cpu = bound_receipt(payload.get("receipt"), expected)
    per_die = payload.get("per_die_c")
    if not isinstance(per_die, dict) or set(per_die) != set(DIES):
        raise ValueError("per-die values")
    values = {name: _temperature(per_die[name]) for name in DIES}
    grid = payload.get("grid64")
    if grid is not None:
        if not isinstance(grid, list) or len(grid) != GRID or any(
                not isinstance(row, list) or len(row) != GRID for row in grid):
            raise ValueError("grid")
        grid = tuple(tuple(_temperature(value) for value in row) for row in grid)
    wire = payload.get("wire_proxy_mm")
    if isinstance(wire, bool) or not isinstance(wire, (int, float)) or not math.isfinite(wire) or not 0 < wire < 1e6:
        raise ValueError("wire proxy")
    active = _same(payload, ("active_layer_peak_C", "active_grid_max_c"))
    if "hotspot_ok" in payload and payload["hotspot_ok"] is not (active < ACTIVE_GUARD_C):
        raise ValueError("the scorer's guard disagrees with its own peak")
    return {"metric": _same(payload, ("max_chiplet_centre_mean_c", "peak_c")),
            "native": _same(payload, ("native_all_block_max_C", "native_all_block_max_c")), "active": active,
            "per_die": values, "grid": grid, "wire": float(wire), "receipt": receipt, "cpu": cpu, "raw": payload}


def judge_replay(payload, *, expected: dict, run_id: str, evaluation: dict) -> dict:
    """The door's own finding on a replay answer, or ValueError when the answer is malformed. Reproduced only when the
    answer is this run's, its first receipt is the accepted score's, its second is a bound and distinct execution, the
    input and output hashes and the numbers are the same, and the scorer said reproduced."""
    if not isinstance(payload, dict) or payload.get("state") not in ("reproduced", "not_reproduced"):
        raise ValueError("not a replay answer")
    codes = [item.get("code") if isinstance(item, dict) else None for item in payload.get("codes", [])]
    if payload["state"] == "reproduced" and codes:
        raise ValueError("a reproduction carries no codes")
    if payload["state"] == "not_reproduced" and (len(codes) != 1 or codes[0] not in REPLAY_CODES):
        raise ValueError("a failed reproduction carries one reproduction code")
    receipts = payload.get("receipts")
    if not isinstance(receipts, list) or len(receipts) != 2:
        raise ValueError("replay receipts")
    original, again = receipts
    finding = {"fresh": False, "match": False, "code": "reproduction_failed", "bound": False, "receipt": None,
               "cpu": cpu_seconds(again.get("cpu_s")) if isinstance(again, dict) else None}
    try:
        if payload.get("run_id") != run_id or canonical(original) != canonical(evaluation["receipt"]):
            raise ValueError("not this run's accepted score")
        again, cpu = bound_receipt(again, expected)
    except (ValueError, TypeError):
        return finding                                  # answered, but not about this evaluation
    finding.update(bound=True, receipt=again, cpu=cpu)
    finding["fresh"] = all(again[name] != original[name]
                           for name in ("reservation_id", "workspace_id", "worker_pid", "engine_pid"))
    if payload["state"] == "not_reproduced":
        finding["code"] = codes[0]
        return finding
    if not finding["fresh"]:
        finding["code"] = "fresh_process_required"
        return finding
    same = (again["input_sha256"] == original["input_sha256"] and again["output_sha256"] == original["output_sha256"]
            and all(payload.get(name) == evaluation["raw"].get(name) for name in REPEATED))
    finding.update(match=same, code=None if same else "reproduction_mismatch")
    return finding


class HttpScorer:
    """The door-scorer client. https only (http is accepted for a loopback test server). Every pin is required."""

    def __init__(self, url: str, token: str, *, grant_id: str | None = None, image_digest: str | None = None,
                 timeout_s: float = 90.0, connect_timeout_s: float = 5.0,
                 binary_sha256: str = EVALUATOR_BINARY_SHA256):
        parts = urlsplit(url)
        loopback = parts.hostname in ("127.0.0.1", "localhost", "::1")
        if parts.scheme not in ("https", "http") or (parts.scheme == "http" and not loopback) or not parts.hostname:
            raise ValueError("the scorer URL must be https")
        if not token or not token.isascii() or any(char.isspace() for char in token):
            raise ValueError("the scorer token is not configured")
        if not isinstance(grant_id, str) or not grant_id or not isinstance(image_digest, str) \
                or not IMAGE.match(image_digest) or not HEX64.match(binary_sha256 or ""):
            raise ValueError("the scorer's grant, image and binary pins are required")
        self._parts, self._token = parts, token
        self._timeout, self._connect_timeout = timeout_s, connect_timeout_s
        self._binary, self._grant, self._image = binary_sha256, grant_id, image_digest

    def _connection(self):
        port = self._parts.port
        if self._parts.scheme == "https":
            return http.client.HTTPSConnection(self._parts.hostname, port, timeout=self._connect_timeout,
                                               context=ssl.create_default_context())
        return http.client.HTTPConnection(self._parts.hostname, port, timeout=self._connect_timeout)

    def _call(self, method: str, tail: str, body: bytes | None) -> tuple:
        """(status, payload or None). A connection that never opened is definitive (nothing began); a timeout or a
        broken exchange after the request was sent is not."""
        connection = self._connection()
        try:
            try:
                connection.connect()
            except (OSError, socket.timeout):
                raise ScorerError("scorer_down", began=False) from None
            connection.sock.settimeout(self._timeout)
            headers = {"authorization": "Bearer " + self._token, "accept": "application/json"}
            if body is not None:
                headers["content-type"] = "application/json"
            try:
                connection.request(method, (self._parts.path.rstrip("/") or "") + tail, body=body, headers=headers)
                response = connection.getresponse()
                data = response.read(MAX_RESPONSE_BYTES + 1)
            except socket.timeout:
                raise ScorerError("scorer_timeout", began=True, definitive=False) from None
            except (OSError, http.client.HTTPException):
                raise ScorerError("scorer_error", began=True, definitive=False) from None
        finally:
            connection.close()
        try:
            payload = json.loads(data, parse_constant=_refuse) if len(data) <= MAX_RESPONSE_BYTES else None
        except ValueError:
            payload = None
        return response.status, payload

    def _post(self, tail: str, body: bytes) -> dict:
        status, payload = self._call("POST", tail, body)
        if status == 429:                                               # busy: nothing ran yet, try again later
            raise ScorerError("scorer_refused", began=False, definitive=False, reply=bounded(payload))
        if 400 <= status < 500:                                         # refused before any reservation or solve
            raise ScorerError("scorer_refused", began=False, reply=bounded(payload))
        if status != 200 or not isinstance(payload, dict):
            raise ScorerError("scorer_error", began=True, cpu_s=reported_cpu(payload), definitive=False,
                              reply=bounded(payload))
        return payload

    def score(self, request: dict) -> Score:
        run_id, proposal = request["run_id"], request["proposal"]
        expected = {"binary_sha256": self._binary, "grant_id": self._grant, "image_digest": self._image,
                    "manifest_id": proposal.get("manifest_id"), "geometry_sha256": proposal.get("geometry_sha256")}
        body = json.dumps({"run_id": run_id, "token_ref": request["token_ref"], "proposal": proposal},
                          separators=(",", ":"), allow_nan=False).encode()
        payload = self._post("/v1/score", body)
        lower = reported_cpu(payload)
        if payload.get("state") == "failed" and payload.get("run_id") == run_id:
            codes = [item.get("code") for item in payload.get("codes", []) if isinstance(item, dict)]
            reason = SCORER_FAILURE.get(codes[0]) if len(codes) == 1 else None
            raise ScorerError(reason or "scorer_error", began=True, cpu_s=lower, reply=bounded(payload))
        try:
            evaluation = parse_evaluation(payload, expected=expected, run_id=run_id)
        except (ValueError, TypeError):
            raise ScorerError("scorer_error", began=True, cpu_s=lower, reply=bounded(payload)) from None
        try:
            answer = self._post("/v1/replay", body)
        except ScorerError as error:
            if not error.definitive:                    # the replay may still run, or may yet: keep the attempt
                replay_lower = max(REPLAY_RESERVE_CPU_S, error.cpu_s or 0.0) if error.began else 0.0
                raise ScorerError(error.reason, began=True, definitive=False, reply=error.reply,
                                  cpu_s=evaluation["cpu"] + replay_lower) from None
            return self._score(evaluation, {"fresh": False, "match": False, "code": "reproduction_failed",
                                            "bound": False, "receipt": None, "cpu": 0.0}, True, error.reply)
        try:
            finding = judge_replay(answer, expected=expected, run_id=run_id, evaluation=evaluation)
        except (ValueError, TypeError):
            lower = reported_cpu(answer)
            finding = {"fresh": False, "match": False, "code": "reproduction_failed", "bound": False,
                       "receipt": None, "cpu": max(REPLAY_RESERVE_CPU_S, lower or 0.0)}
            return self._score(evaluation, finding, False, bounded(answer))
        known = finding["bound"] and finding["cpu"] is not None
        if not known:
            finding["cpu"] = max(REPLAY_RESERVE_CPU_S, finding["cpu"] or 0.0)
        return self._score(evaluation, finding, known, None if known else bounded(answer))

    def _score(self, evaluation: dict, finding: dict, cpu_known: bool, raw) -> Score:
        return Score(evaluation["metric"], evaluation["native"], evaluation["active"], evaluation["per_die"],
                     evaluation["grid"], evaluation["wire"], finding["fresh"], finding["match"], finding["code"],
                     evaluation["cpu"] + finding["cpu"], self._binary,
                     {"score": evaluation["receipt"], "replay": finding["receipt"], "replay_reply": raw},
                     receipts_bound=finding["bound"], cpu_known=cpu_known)

    def health(self) -> bool:
        """Up only when the scorer answers as the pinned binary and image under the door's grant."""
        try:
            status, payload = self._call("GET", "/v1/health", None)
        except ScorerError:
            return False
        return (status == 200 and isinstance(payload, dict) and payload.get("ok") is True
                and payload.get("binary_sha256") == self._binary and payload.get("image_digest") == self._image
                and payload.get("grant_id") == self._grant)


def _refuse(_name):
    raise ValueError("nonfinite JSON number")
