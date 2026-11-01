"""The door's workers: at most the grant's `parallel` attempts at once, across every worker and process (the claim
counts active reservations under the write lock).

Before each claim a worker asks whether the scorer is up (health, cached for a few seconds). While it is down nothing
is claimed: queued runs stay queued and the feed says "scorer down". An attempt already sent when the scorer fails
ends `failed` with an explicit reason (scorer_down, scorer_timeout, scorer_error, scorer_cutoff, grant_expired) and
its contract code. At launch the run is revalidated: the signed manifest and open admission, accepted terms, the
case, and the legality gate on the stored proposal. A window that has ended expires every queued run.

A score is checked against the selector before it is recorded. The metric must be the maximum of the eight chiplets'
centre-cell means the scorer reports; when the scorer also returns the 64 x 64 active-layer grid, the door recomputes
each chiplet's mean with gate zero's GRID_CENTER code and the active peak as the grid's maximum; and the scorer's wire
proxy must be the door's. A disagreement (over half the grid's 0.01 K print precision for temperatures) keeps the
evaluation but carries binding_mismatch, which withholds any candidate verdict.
"""
from __future__ import annotations

import logging
import threading

from .scorer import BINDING_TOLERANCE_K, ScorerError, cpu_seconds

_logger = logging.getLogger(__name__)
FAILURE_CODE = {"scorer_down": "oracle_error", "scorer_timeout": "timeout", "scorer_error": "oracle_error",
                "scorer_refused": "oracle_error", "scorer_cutoff": "stopped", "grant_expired": "grant_expired",
                "interrupted": "interrupted"}
DIE_NAMES = ("C0", "C1", "C2", "C3", "D0", "D1", "D2", "D3")
WIRE_TOLERANCE_MM = 1e-5
HEALTH_TTL_S = 5.0


class ScorerState:
    """The last known scorer health, shared by the workers and reported on the feeds."""

    def __init__(self):
        self.state, self.since, self.checked_at = "unknown", None, None
        self._lock = threading.Lock()

    def set(self, state: str, now: float, store) -> None:
        with self._lock:
            self.checked_at = now
            if state == self.state:
                return
            self.state, self.since = state, now
        store.scorer_event(state, now)

    def snapshot(self) -> dict:
        return {"state": self.state, "since": self.since}


def binding(score, dies, checker) -> dict:
    """How the score binds to the frozen selector and the layout; ok only when every available check agrees."""
    metric = score.max_chiplet_centre_cell_mean_C
    per_die_max = max(score.per_die_C.values())
    checks = {"per_die_max_C": per_die_max,
              "per_die_ok": abs(per_die_max - metric) <= BINDING_TOLERANCE_K}
    if score.grid64 is not None:
        means = checker.centre_means(dies, score.grid64)
        peak = max(max(row) for row in score.grid64)
        checks.update(grid_selector_C=max(means), grid_active_peak_C=peak,
                      grid_ok=(abs(max(means) - metric) <= BINDING_TOLERANCE_K
                               and abs(peak - score.active_layer_peak_C) <= BINDING_TOLERANCE_K
                               and all(abs(mean - score.per_die_C[name]) <= BINDING_TOLERANCE_K
                                       for mean, name in zip(means, DIE_NAMES))))
    if score.wire_proxy_mm is not None:
        checks.update(scorer_wire_proxy_mm=score.wire_proxy_mm,
                      wire_ok=abs(score.wire_proxy_mm - checker.wire_proxy_mm(dies)) <= WIRE_TOLERANCE_MM)
    checks["ok"] = all(value for name, value in checks.items() if name.endswith("_ok"))
    return checks


def outcome_for(score, claimed: dict, checker) -> dict:
    """The settled outcome of a returned score: charged its measured CPU, its binding checked against the selector."""
    dies = claimed["proposal"]["dies"]
    bound = binding(score, dies, checker)
    reproduced = score.replay_fresh_process and score.replay_match
    replay_code = None if reproduced else (score.replay_code or (
        "fresh_process_required" if not score.replay_fresh_process else "reproduction_mismatch"))
    envelope = claimed["envelope_cpu_s"]
    result = {"metric": score.metric, "max_chiplet_centre_cell_mean_C": score.max_chiplet_centre_cell_mean_C,
              "native_all_block_max_C": score.native_all_block_max_C,
              "active_layer_peak_C": score.active_layer_peak_C, "per_die_C": dict(score.per_die_C),
              "grid64": None if score.grid64 is None else [list(row) for row in score.grid64],
              "replay": {"fresh_process": score.replay_fresh_process, "match": score.replay_match},
              "binding": bound,
              "evaluator": {"binary_sha256": score.evaluator_binary_sha256, "grid": 64},
              "cpu_s": score.cpu_s, "overrun": score.cpu_s > envelope, "receipt": score.receipt}
    return {"kind": "scored", "charged_cpu_s": score.cpu_s, "usage": "measured" if score.cpu_s <= envelope else
            "measured_overrun", "qualifiers": [] if bound["ok"] else ["binding_mismatch"], "reproduced": reproduced,
            "replay_code": replay_code, "result": result, "metric_c": score.max_chiplet_centre_cell_mean_C}


def failure_for(error: ScorerError, envelope: float) -> dict:
    """Never began: charged 0. Ambiguous: the larger of the envelope and any CPU the scorer reported."""
    if error.began:
        reported = cpu_seconds(error.cpu_s)
        charged, usage = max(envelope, reported or 0.0), "unknown_charged_envelope"
    else:
        charged, usage = 0.0, "never_began"
    return {"kind": "failed", "code": FAILURE_CODE[error.reason], "reason": error.reason, "charged_cpu_s": charged,
            "usage": usage}


class Dispatcher:
    def __init__(self, door, *, poll_s: float = 0.25):
        self.door = door
        self.poll_s = poll_s
        self._stop = threading.Event()
        self._wake = threading.Condition()
        self._threads: list[threading.Thread] = []
        self._health_lock = threading.Lock()

    def start(self) -> None:
        door = self.door
        door.store.recover(door.policy.clock())
        if not door.policy.usable or door.scorer is None:
            return
        for index in range(door.policy.grant.parallel):
            thread = threading.Thread(target=self._loop, name=f"door-worker-{index}", daemon=True)
            thread.start()
            self._threads.append(thread)

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        self.wake()
        for thread in self._threads:
            thread.join(timeout)
        self._threads = []

    def wake(self) -> None:
        with self._wake:
            self._wake.notify_all()

    def _wait(self, seconds: float) -> None:
        with self._wake:
            self._wake.wait(seconds)

    def scorer_up(self, now: float) -> bool:
        state = self.door.scorer_state
        with self._health_lock:
            if state.checked_at is not None and now - state.checked_at < HEALTH_TTL_S and state.state != "unknown":
                return state.state == "up"
            try:
                healthy = bool(self.door.scorer.health())
            except Exception:  # noqa: BLE001 - a health probe that raises is a down scorer
                healthy = False
            state.set("up" if healthy else "down", now, self.door.store)
            return healthy

    def run_once(self) -> bool:
        """One claim and its attempt. Returns whether an attempt ran (the tests drive workers through this)."""
        door = self.door
        now = door.policy.clock()
        found, final = door.policy.admission(now)
        if found:
            if final:
                door.store.end_all_queued(("expire", "window_closed"), now)
            return False
        if not self.scorer_up(now):
            return False
        claimed = door.store.claim(check=door.launch_check, parallel=door.policy.grant.parallel, now=now)
        if claimed is None:
            return False
        request = {"run_id": claimed["run_id"], "token_ref": door.policy.participant_ref(claimed["principal"]),
                   "proposal": claimed["proposal"]}
        try:
            score = door.scorer.score(request)
        except ScorerError as error:
            if error.reason == "scorer_down":
                door.scorer_state.set("down", door.policy.clock(), door.store)
            outcome = failure_for(error, claimed["envelope_cpu_s"])
        except Exception:  # noqa: BLE001 - a scorer adapter fault is a failed attempt, never a crashed worker
            _logger.exception("scorer adapter fault")
            outcome = failure_for(ScorerError("scorer_error", began=True), claimed["envelope_cpu_s"])
        else:
            door.scorer_state.set("up", door.policy.clock(), door.store)
            outcome = outcome_for(score, claimed, door.policy.checker)
        door.store.settle(run_id=claimed["run_id"], reservation_id=claimed["reservation_id"], outcome=outcome,
                          now=door.policy.clock())
        return True

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                ran = self.run_once()
            except Exception:  # noqa: BLE001 - keep the worker alive; the fault is logged, never visitor text
                _logger.exception("door worker fault")
                ran = False
            if not ran:
                self._wait(self.poll_s if self.door.scorer_state.state != "down" else 1.0)
