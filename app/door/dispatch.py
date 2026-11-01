"""The door's workers: at most the grant's `parallel` attempts at once, across every worker and process (the claim
counts active reservations under the write lock).

Before each claim a worker asks whether the scorer is up (health, cached for a few seconds). While it is down nothing
is claimed: queued runs stay queued and the feed says "scorer down". An attempt already sent when the scorer fails
ends `failed` with an explicit reason (scorer_down, scorer_timeout, scorer_error, scorer_cutoff, grant_expired) and
its contract code. At launch the run is revalidated: the signed manifest and open admission, accepted terms, the
case, and the legality gate on the stored proposal. A window that has ended expires every queued run.

A score is checked against the selector before it is recorded: the door recomputes max_chiplet_centre_cell_mean_C
from the scorer's grid with gate zero's GRID_CENTER code, and the active-layer peak as the grid's maximum. A
disagreement over half the grid's 0.01 K print precision keeps the evaluation but carries binding_mismatch, which
withholds any candidate verdict.
"""
from __future__ import annotations

import logging
import threading

from .policy import CASE
from .scorer import BINDING_TOLERANCE_K, ScorerError, cpu_seconds

_logger = logging.getLogger(__name__)
FAILURE_CODE = {"scorer_down": "oracle_error", "scorer_timeout": "timeout", "scorer_error": "oracle_error",
                "scorer_cutoff": "stopped", "grant_expired": "grant_expired"}
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


def outcome_for(score, claimed: dict, checker) -> dict:
    """The settled outcome of a returned score: charged its measured CPU, its binding checked against the selector."""
    dies = claimed["proposal"]["dies"]
    grid = score.grid64
    selector = checker.selector(dies, grid)
    peak = max(max(row) for row in grid)
    bound = (abs(selector - score.max_chiplet_centre_cell_mean_C) <= BINDING_TOLERANCE_K
             and abs(peak - score.active_layer_peak_C) <= BINDING_TOLERANCE_K)
    reproduced = score.replay_fresh_process and score.replay_match
    replay_code = None if reproduced else (
        "fresh_process_required" if not score.replay_fresh_process else "reproduction_mismatch")
    envelope = claimed["envelope_cpu_s"]
    result = {"metric": score.metric, "max_chiplet_centre_cell_mean_C": score.max_chiplet_centre_cell_mean_C,
              "native_all_block_max_C": score.native_all_block_max_C,
              "active_layer_peak_C": score.active_layer_peak_C,
              "grid64": [list(row) for row in grid],
              "replay": {"fresh_process": score.replay_fresh_process, "match": score.replay_match},
              "binding": {"recomputed_max_chiplet_centre_cell_mean_C": selector,
                          "recomputed_active_layer_peak_C": peak, "ok": bound},
              "evaluator": {"binary_sha256": score.evaluator_binary_sha256, "grid": 64},
              "cpu_s": score.cpu_s, "overrun": score.cpu_s > envelope, "receipt": score.receipt}
    return {"kind": "scored", "charged_cpu_s": score.cpu_s, "usage": "measured" if score.cpu_s <= envelope else
            "measured_overrun", "qualifiers": [] if bound else ["binding_mismatch"], "reproduced": reproduced,
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
        request = {"run_id": claimed["run_id"], "manifest_id": claimed["manifest_id"],
                   "geometry_sha256": claimed["geometry_sha256"], "case": CASE,
                   "units": claimed["proposal"]["units"], "anchor": claimed["proposal"]["anchor"],
                   "dies": claimed["proposal"]["dies"], "reserve_cpu_s": claimed["envelope_cpu_s"]}
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
