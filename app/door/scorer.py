"""The scorer seam: score(request) -> Score, health() -> bool. The real scorer is warden's door-scorer (ticket
b6230a56): HotSpot 6.0 at gate zero's binary, grid 64, a score and a fresh-process replay, behind bearer auth. Its API
is not published yet, so HttpScorer is the only code that knows the wire format; everything else reads Score.

Proposed wire format (sentilab-door-score/1), to be matched to door-scorer's once published:

    POST {DOOR_SCORER_URL}/v1/score            Authorization: Bearer {DOOR_SCORER_TOKEN}
    {"schema": "sentilab-door-score-request/1", "run_id", "manifest_id", "geometry_sha256", "case": "cpu-dram",
     "units": "um", "anchor": "die-centre", "dies": [{die, x_um, y_um, rot_deg} x 8], "reserve_cpu_s"}
    200 {"schema": "sentilab-door-score/1", "status": "ok" | "cutoff" | "grant_expired",
         "metric": {"metric_id": "max_chiplet_centre_cell_mean_C", "definition", "unit": "C", "precision_K": 0.01,
                    "reference": {"layout": "raw", "value_C": 115.935}},
         "max_chiplet_centre_cell_mean_C", "native_all_block_max_C", "active_layer_peak_C",
         "grid64": 64 rows x 64 columns of the active layer in C, row 0 at the top (HotSpot's order),
         "replay": {"fresh_process": true, "match": true},
         "cpu_s": whole-container CPU for evaluate + replay + cleanup, measured after the reap,
         "evaluator": {"binary_sha256", "grid": 64}, "receipt": {...}}
    GET {DOOR_SCORER_URL}/v1/health            200 when it can take work

Charging (AGENT-DOOR Amendment 1; warden's whole-container cutoff, forge/slab049-followups d1e4bd3): the door reserves
the grant's run envelope before dispatch. A scored run is charged the CPU the scorer measured (an overrun is charged
and flagged). A call that never reached the scorer (the connection failed) is charged 0. Anything ambiguous (a
timeout after sending, an error status, an unreadable answer) is charged the larger of the envelope and any CPU it
reported.
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
MAX_RECEIPT_BYTES = 16 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024
SCORE_SCHEMA = "sentilab-door-score/1"
REQUEST_SCHEMA = "sentilab-door-score-request/1"
STATUSES = ("ok", "cutoff", "grant_expired")
REASONS = ("scorer_down", "scorer_timeout", "scorer_error", "scorer_cutoff", "grant_expired")


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
    grid64: tuple
    replay_fresh_process: bool
    replay_match: bool
    cpu_s: float
    evaluator_binary_sha256: str
    receipt: dict
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


def parse_score(payload, *, binary_sha256: str = EVALUATOR_BINARY_SHA256) -> Score:
    """The scorer's answer as a Score, or ScorerError. Strict: one metric, three separate statistics, the pinned
    binary, a 64 x 64 grid of finite temperatures, an explicit fresh-process replay and a bounded receipt."""
    if not isinstance(payload, dict) or payload.get("schema") != SCORE_SCHEMA or payload.get("status") not in STATUSES:
        raise ScorerError("scorer_error", began=True)
    cpu = cpu_seconds(payload.get("cpu_s"))
    if payload["status"] == "cutoff":
        raise ScorerError("scorer_cutoff", began=True, cpu_s=cpu)
    if payload["status"] == "grant_expired":
        raise ScorerError("grant_expired", began=True, cpu_s=cpu)
    try:
        if cpu is None or payload.get("metric") != METRIC:
            raise ValueError("metric")
        evaluator, replay, grid = payload["evaluator"], payload["replay"], payload["grid64"]
        if evaluator != {"binary_sha256": binary_sha256, "grid": GRID}:
            raise ValueError("evaluator")
        if (not isinstance(replay, dict) or set(replay) != {"fresh_process", "match"}
                or not all(isinstance(replay[name], bool) for name in replay)):
            raise ValueError("replay")
        if not isinstance(grid, list) or len(grid) != GRID or any(
                not isinstance(row, list) or len(row) != GRID for row in grid):
            raise ValueError("grid")
        rows = tuple(tuple(_temperature(value) for value in row) for row in grid)
        receipt = payload["receipt"]
        if not isinstance(receipt, dict) or len(canonical(receipt)) > MAX_RECEIPT_BYTES:
            raise ValueError("receipt")
        return Score(_temperature(payload[METRIC_ID]), _temperature(payload["native_all_block_max_C"]),
                     _temperature(payload["active_layer_peak_C"]), rows, replay["fresh_process"], replay["match"],
                     cpu, binary_sha256, receipt)
    except (KeyError, TypeError, ValueError):
        raise ScorerError("scorer_error", began=True, cpu_s=cpu) from None


class HttpScorer:
    """The door-scorer client. https only (http is accepted for a loopback test server)."""

    def __init__(self, url: str, token: str, *, timeout_s: float = 90.0, connect_timeout_s: float = 5.0,
                 binary_sha256: str = EVALUATOR_BINARY_SHA256):
        parts = urlsplit(url)
        loopback = parts.hostname in ("127.0.0.1", "localhost", "::1")
        if parts.scheme not in ("https", "http") or (parts.scheme == "http" and not loopback) or not parts.hostname:
            raise ValueError("the scorer URL must be https")
        if not token:
            raise ValueError("the scorer token is not configured")
        self._parts, self._token = parts, token
        self._timeout, self._connect_timeout, self._binary = timeout_s, connect_timeout_s, binary_sha256

    def _connection(self):
        port = self._parts.port
        if self._parts.scheme == "https":
            return http.client.HTTPSConnection(self._parts.hostname, port, timeout=self._connect_timeout,
                                               context=ssl.create_default_context())
        return http.client.HTTPConnection(self._parts.hostname, port, timeout=self._connect_timeout)

    def _path(self, tail: str) -> str:
        return (self._parts.path.rstrip("/") or "") + tail

    def _call(self, method: str, tail: str, body: bytes | None):
        """(status, payload bytes). Connection failures raise ScorerError(began=False); later ones began=True."""
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
                connection.request(method, self._path(tail), body=body, headers=headers)
                response = connection.getresponse()
                data = response.read(MAX_RESPONSE_BYTES + 1)
            except socket.timeout:
                raise ScorerError("scorer_timeout", began=True) from None
            except (OSError, http.client.HTTPException):
                raise ScorerError("scorer_error", began=True) from None
            if len(data) > MAX_RESPONSE_BYTES:
                raise ScorerError("scorer_error", began=True)
            return response.status, data
        finally:
            connection.close()

    def score(self, request: dict) -> Score:
        body = json.dumps({"schema": REQUEST_SCHEMA, **request}, separators=(",", ":"), allow_nan=False).encode()
        status, data = self._call("POST", "/v1/score", body)
        try:
            payload = json.loads(data, parse_constant=_refuse) if status == 200 else None
        except ValueError:
            payload = None
        if payload is None:
            raise ScorerError("scorer_error", began=True)
        return parse_score(payload, binary_sha256=self._binary)

    def health(self) -> bool:
        try:
            status, _ = self._call("GET", "/v1/health", None)
        except ScorerError:
            return False
        return status == 200


def _refuse(_name):
    raise ValueError("nonfinite JSON number")
