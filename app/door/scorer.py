"""The scorer seam: score(request) -> Score and health() -> bool. The real scorer is warden's door-scorer (ticket
b6230a56; sentilab PR #79, research/agent-door/scorer at 78bc0d18). HttpScorer is the only code that knows its wire
format; everything else reads Score.

    GET  {DOOR_SCORER_URL}/v1/health   -> 200 {"ok": true, "binary_sha256", "grant_id", "image_digest", ...}
    POST {DOOR_SCORER_URL}/v1/score    {"run_id", "token_ref", "proposal"}
         -> 200 {"state": "evaluated", "metric_id", "max_chiplet_centre_mean_c", "native_all_block_max_C",
                 "active_layer_peak_C", "per_die_c", "wire_proxy_mm", "metric_precision", "references", "receipt"}
         -> 200 {"state": "failed", "codes": [timeout | interrupted | oracle_error], "receipt"}
    POST {DOOR_SCORER_URL}/v1/replay   the same body, after a successful score: a fresh supervisor, solver and directory
         -> 200 {"state": "reproduced" | "not_reproduced", "codes", "receipts": [score receipt, replay receipt], ...}
    4xx: refused before any reservation or solve (401, 403 budget_exhausted, 409, 422 rejected, 429 busy)
    Every call carries Authorization: Bearer {DOOR_SCORER_TOKEN}.

token_ref is the door's contract participant_ref, HMAC(DOOR_K_CHALLENGE, "anon-token/1:" + sha256(nonce)). The scorer
checks run_id == run_id(manifest_id, token_ref, proposal_sha256), so the run id is the same on both sides, and the
scorer keys its per-token CPU on a pseudonym it cannot link to a nonce.

The scorer returns each real chiplet's centre-cell mean (per_die_c) and no grid yet. The door checks the metric
against them (the maximum of the eight is the metric), and against the 64 x 64 active-layer grid as well whenever a
scorer returns one ("grid64", row 0 at the top), using gate zero's own GRID_CENTER code.

Charging (AGENT-DOOR Amendment 1; warden's whole-container cutoff): the door reserves the grant's run envelope before
dispatch. A scored run is charged the CPU the scorer measured for its score and its replay (an overrun is charged
and flagged). A call refused before any solve, or one that never connected, is charged 0. Anything ambiguous (a
timeout after sending, a 5xx, an unreadable answer) is charged the larger of the envelope and any CPU reported.
"""
from __future__ import annotations

import http.client
import json
import math
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
GRID = 64
DIES = ("C0", "C1", "C2", "C3", "D0", "D1", "D2", "D3")
MAX_RECEIPT_BYTES = 16 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024
REASONS = ("scorer_down", "scorer_timeout", "scorer_error", "scorer_refused", "scorer_cutoff", "grant_expired",
           "interrupted")
SCORER_FAILURE = {"timeout": "scorer_timeout", "interrupted": "interrupted", "oracle_error": "scorer_error",
                  "stopped": "scorer_cutoff", "grant_expired": "grant_expired"}
REPLAY_CODES = ("reproduction_mismatch", "reproduction_failed")


class ScorerError(Exception):
    """A call that produced no score. began says whether the scorer may have done work (so CPU is owed)."""

    def __init__(self, reason: str, *, began: bool, cpu_s: float | None = None):
        if reason not in REASONS:
            raise ValueError("unknown scorer failure")
        super().__init__(reason)
        self.reason, self.began, self.cpu_s = reason, began, cpu_s


@dataclass(frozen=True)
class Score:
    max_chiplet_centre_cell_mean_C: float
    native_all_block_max_C: float
    active_layer_peak_C: float
    per_die_C: dict                  # each real chiplet's centre-cell mean, C, keyed C0..C3, D0..D3
    grid64: tuple | None             # the 64 x 64 active-layer map (row 0 at the top), when the scorer returns one
    wire_proxy_mm: float | None      # the scorer's own proxy, checked against the door's
    replay_fresh_process: bool
    replay_match: bool
    replay_code: str | None          # reproduction_mismatch or reproduction_failed when not reproduced
    cpu_s: float                     # score plus replay, as the scorer measured them
    evaluator_binary_sha256: str
    receipt: dict                    # {"score": <receipt>, "replay": <receipt or None>}
    metric: dict = field(default_factory=lambda: dict(METRIC))

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


def _same(payload: dict, names: tuple):
    """The one value several aliases carry, or ValueError if they disagree or none is present."""
    values = [payload[name] for name in names if name in payload]
    if not values or any(value != values[0] for value in values):
        raise ValueError("missing or disagreeing aliases")
    return _temperature(values[0])


def _receipt(payload, binary_sha256: str) -> tuple:
    receipt = payload.get("receipt") if isinstance(payload, dict) else None
    if not isinstance(receipt, dict) or len(canonical(receipt)) > MAX_RECEIPT_BYTES:
        raise ValueError("receipt")
    if receipt.get("binary_sha256") != binary_sha256:
        raise ValueError("the receipt names another binary")
    cpu = cpu_seconds(receipt.get("cpu_s"))
    if cpu is None:
        raise ValueError("receipt CPU")
    return receipt, cpu


def parse_evaluation(payload, *, binary_sha256: str = EVALUATOR_BINARY_SHA256) -> dict:
    """The fields of an `evaluated` answer, or ValueError. Strict: the frozen metric and its reference, the three
    statistics apart (their aliases must agree), all eight chiplets, the pinned binary, a bounded receipt."""
    if not isinstance(payload, dict) or payload.get("state") != "evaluated" or payload.get("metric_id") != METRIC_ID:
        raise ValueError("not an evaluation of the frozen metric")
    precision = payload.get("metric_precision")
    if precision is not None and (not isinstance(precision, dict) or precision.get("grid_resolution_K") != 0.01):
        raise ValueError("metric precision")
    references = payload.get("references")
    if references is not None:
        raw = references.get("raw") if isinstance(references, dict) else None
        if not isinstance(raw, dict) or raw.get("max_chiplet_centre_mean_c") != METRIC["reference"]["value_C"]:
            raise ValueError("the raw reference binding")
    receipt, cpu = _receipt(payload, binary_sha256)
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
    if wire is not None and (isinstance(wire, bool) or not isinstance(wire, (int, float)) or not math.isfinite(wire)
                             or not 0 < wire < 1_000_000):
        raise ValueError("wire proxy")
    active = _same(payload, ("active_layer_peak_C", "active_grid_max_c"))
    if "hotspot_ok" in payload and payload["hotspot_ok"] is not (active < ACTIVE_GUARD_C):
        raise ValueError("the scorer's guard disagrees with its own peak")
    return {"metric": _same(payload, ("max_chiplet_centre_mean_c", "peak_c")),
            "native": _same(payload, ("native_all_block_max_C", "native_all_block_max_c")), "active": active,
            "per_die": values, "grid": grid, "wire": None if wire is None else float(wire), "receipt": receipt,
            "cpu": cpu}


def parse_replay(payload, *, binary_sha256: str = EVALUATOR_BINARY_SHA256) -> tuple:
    """(reproduced, code, replay receipt, replay CPU) of a replay answer, or ValueError."""
    if not isinstance(payload, dict) or payload.get("state") not in ("reproduced", "not_reproduced"):
        raise ValueError("not a replay answer")
    receipts = payload.get("receipts")
    if not isinstance(receipts, list) or len(receipts) != 2:
        raise ValueError("replay receipts")
    receipt, cpu = _receipt({"receipt": receipts[1]}, binary_sha256)
    codes = [item.get("code") for item in payload.get("codes", []) if isinstance(item, dict)]
    if payload["state"] == "reproduced":
        if codes:
            raise ValueError("a reproduction carries no codes")
        return True, None, receipt, cpu
    if len(codes) != 1 or codes[0] not in REPLAY_CODES:
        raise ValueError("a failed reproduction carries one reproduction code")
    return False, codes[0], receipt, cpu


class HttpScorer:
    """The door-scorer client. https only (http is accepted for a loopback test server)."""

    def __init__(self, url: str, token: str, *, timeout_s: float = 90.0, connect_timeout_s: float = 5.0,
                 binary_sha256: str = EVALUATOR_BINARY_SHA256, grant_id: str | None = None):
        parts = urlsplit(url)
        loopback = parts.hostname in ("127.0.0.1", "localhost", "::1")
        if parts.scheme not in ("https", "http") or (parts.scheme == "http" and not loopback) or not parts.hostname:
            raise ValueError("the scorer URL must be https")
        if not token or not token.isascii() or any(char.isspace() for char in token):
            raise ValueError("the scorer token is not configured")
        self._parts, self._token = parts, token
        self._timeout, self._connect_timeout = timeout_s, connect_timeout_s
        self._binary, self._grant = binary_sha256, grant_id

    def _connection(self):
        port = self._parts.port
        if self._parts.scheme == "https":
            return http.client.HTTPSConnection(self._parts.hostname, port, timeout=self._connect_timeout,
                                               context=ssl.create_default_context())
        return http.client.HTTPConnection(self._parts.hostname, port, timeout=self._connect_timeout)

    def _call(self, method: str, tail: str, body: bytes | None) -> tuple:
        """(status, payload or None). A failed connection is ScorerError(began=False); anything after the request
        is sent began=True."""
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
                raise ScorerError("scorer_timeout", began=True) from None
            except (OSError, http.client.HTTPException):
                raise ScorerError("scorer_error", began=True) from None
        finally:
            connection.close()
        try:
            payload = json.loads(data, parse_constant=_refuse) if len(data) <= MAX_RESPONSE_BYTES else None
        except ValueError:
            payload = None
        return response.status, payload

    def _post(self, tail: str, body: bytes) -> dict:
        status, payload = self._call("POST", tail, body)
        if 400 <= status < 500:
            raise ScorerError("scorer_refused", began=False)           # refused before any reservation or solve
        if status != 200 or not isinstance(payload, dict):
            raise ScorerError("scorer_error", began=True)
        return payload

    def score(self, request: dict) -> Score:
        body = json.dumps({"run_id": request["run_id"], "token_ref": request["token_ref"],
                           "proposal": request["proposal"]}, separators=(",", ":"), allow_nan=False).encode()
        payload = self._post("/v1/score", body)
        if payload.get("state") == "failed":
            codes = [item.get("code") for item in payload.get("codes", []) if isinstance(item, dict)]
            try:
                cpu = _receipt(payload, self._binary)[1]
            except ValueError:
                cpu = None
            reason = SCORER_FAILURE.get(codes[0]) if len(codes) == 1 else None
            raise ScorerError(reason or "scorer_error", began=True, cpu_s=cpu)
        try:
            evaluation = parse_evaluation(payload, binary_sha256=self._binary)
        except ValueError:
            raise ScorerError("scorer_error", began=True, cpu_s=_receipt_cpu(payload)) from None
        try:
            reproduced, code, replay_receipt, replay_cpu = parse_replay(self._post("/v1/replay", body),
                                                                        binary_sha256=self._binary)
        except ScorerError as error:
            # The evaluation stands; its replay could not be completed, so it is not reproduced.
            reproduced, code, replay_receipt = False, "reproduction_failed", None
            replay_cpu = 0.0 if not error.began else max(10.0, cpu_seconds(error.cpu_s) or 0.0)
        except ValueError:
            reproduced, code, replay_receipt, replay_cpu = False, "reproduction_failed", None, 10.0
        return Score(evaluation["metric"], evaluation["native"], evaluation["active"], evaluation["per_die"],
                     evaluation["grid"], evaluation["wire"], replay_receipt is not None, reproduced, code,
                     evaluation["cpu"] + replay_cpu, self._binary,
                     {"score": evaluation["receipt"], "replay": replay_receipt})

    def health(self) -> bool:
        """Up only when the scorer answers as the pinned binary (and, when given, the door's grant)."""
        try:
            status, payload = self._call("GET", "/v1/health", None)
        except ScorerError:
            return False
        return (status == 200 and isinstance(payload, dict) and payload.get("ok") is True
                and payload.get("binary_sha256") == self._binary
                and (self._grant is None or payload.get("grant_id") == self._grant))


def _receipt_cpu(payload):
    receipt = payload.get("receipt") if isinstance(payload, dict) else None
    return cpu_seconds(receipt.get("cpu_s")) if isinstance(receipt, dict) else None


def _refuse(_name):
    raise ValueError("nonfinite JSON number")
