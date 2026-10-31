"""Independent, best-effort whole-lifetime supervisor for prospective SLAB-039.

This is deliberately NOT advertised as a hard cumulative CPU cap. Ordinary
Linux cannot bound scheduler delay, /proc traversal, SIGKILL or reap latency.
The approved operating conditions require a container rate cap and measured
latency evidence. The shipped policy has no measurements and refuses runs.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import signal
import sys
import time
import uuid

from sundai_controller.process_budget import ProcessTreeScope, tree_snapshot, _stat, TICKS

PRIOR_ASCEND_CPU = 1440.294565
MAX_REMAINING_CPU = 2879.705435
DEADLINE = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
# Inherited only by the dedicated forked worker; no credential or disk token.
WORKER_CONTEXT = None


@dataclass(frozen=True)
class Policy:
    rate_q: int = 1
    poll_seconds: float = 0.01
    observation_delay_seconds: float = 0.25
    kill_seconds: float = 0.25
    reap_seconds: float = 0.25
    burst_cpu_seconds: float = 0.02
    settlement_tail_cpu_seconds: float = 0.25
    measured_observation_plus_kill_seconds: float | None = None

    def __post_init__(self):
        if type(self.rate_q) is not int or self.rate_q not in (1, 2, 8):
            raise ValueError('Q must be 1, 2 or 8')
        for key, value in asdict(self).items():
            if key == 'measured_observation_plus_kill_seconds' and value is None:
                continue  # Synthetic policies only; production admission refuses.
            if key != 'rate_q' and (type(value) not in (int, float) or
                                    not math.isfinite(value) or value <= 0):
                raise ValueError(f'{key} must be positive and finite')

    @property
    def reserve(self):
        if self.measured_observation_plus_kill_seconds is not None:
            return 2 * self.rate_q * self.measured_observation_plus_kill_seconds
        return (self.burst_cpu_seconds + self.settlement_tail_cpu_seconds +
                self.rate_q * (self.poll_seconds + self.observation_delay_seconds +
                               self.kill_seconds + self.reap_seconds))

    def conditional_overshoot(self, observation, kill, reap, tail):
        """Bound only if the declared rate/burst envelope holds at all times."""
        return max(0.0, self.burst_cpu_seconds + self.rate_q * (
            self.poll_seconds + observation + kill + reap) + tail - self.reserve)


def load_policy(path):
    admitted_bytes = Path(path).read_bytes()
    declaration = json.loads(admitted_bytes)
    policy = Policy(**declaration['limits'])
    if (declaration.get('status') != 'approved' or
            not isinstance(declaration.get('approved_by'), str) or
            not declaration['approved_by'].strip() or
            declaration.get('accept_unbounded_scheduler_and_cleanup_risk') is not True):
        raise RuntimeError('operational approval required: unconditional overshoot is unbounded')
    if (policy.measured_observation_plus_kill_seconds is None or
            not isinstance(declaration.get('latency_measurement_evidence'), str) or
            not declaration['latency_measurement_evidence'].strip()):
        raise RuntimeError('operational approval required: measured observation-plus-kill latency evidence')
    minimum = (policy.burst_cpu_seconds + policy.settlement_tail_cpu_seconds +
               policy.rate_q * (policy.poll_seconds + policy.observation_delay_seconds +
                                policy.kill_seconds + policy.reap_seconds))
    if policy.reserve < minimum:
        raise ValueError('measured H does not cover declared observation, kill, reap, burst and tail reserves')
    return policy, declaration, hashlib.sha256(admitted_bytes).hexdigest()


def verify_cpu_max(policy):
    """Require cpu.max quota/period = Q; this permits bursts, not a rolling cap."""
    entries = Path('/proc/self/cgroup').read_text().splitlines()
    groups = [entry[3:] for entry in entries if entry.startswith('0::/')]
    if len(groups) != 1:
        raise RuntimeError('container cgroup v2 cpu.max is required')
    root = Path('/sys/fs/cgroup').resolve()
    group = (root / groups[0].lstrip('/')).resolve()
    if not group.is_relative_to(root):
        raise RuntimeError('cannot locate container cpu.max')
    raw = (group / 'cpu.max').read_text().strip()
    fields = raw.split()
    if (len(fields) != 2 or not all(value.isdecimal() for value in fields) or
            int(fields[1]) <= 0 or int(fields[0]) != policy.rate_q * int(fields[1])):
        raise RuntimeError('container cpu.max must equal Q')
    return {'path': str(group / 'cpu.max'), 'value': raw, 'rate_q': policy.rate_q}


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w') as stream:
        json.dump(value, stream, sort_keys=True, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _lifetime_wall_seconds():
    # Linux starttime and CLOCK_MONOTONIC share the boot-relative time base.
    return max(0.0, time.monotonic() - _stat(os.getpid())['start'] / TICKS)


def remaining_cpu(state, prereg):
    """No replacement ledger or rounded-up micro150 allowance is admissible."""
    if state.get('allocation_halted'):
        raise RuntimeError('allocation halted pending human review')
    prior = state['fixtures'].get('ascend910', {})
    if (prior.get('cpu_seconds', 0) < PRIOR_ASCEND_CPU or prior.get('calls', 0) < 2650 or
            state['cpu_seconds'] < sum(v['cpu_seconds'] for v in state['fixtures'].values()) or
            state['total_calls'] < sum(v['calls'] for v in state['fixtures'].values()) or
            state.get('solving_wall_seconds', 0) < 1525.852038):
        raise ValueError('prior Ascend charges cannot be reset')
    if state.get('outer_active') or state.get('active'):
        raise RuntimeError('unreconciled lifetime/call reservation')
    allocation = prereg['allocation']
    micro = state['fixtures'].get('micro150', {}).get('cpu_seconds', 0)
    other = max(720, state.get('non_headroom', {}).get('cpu_seconds', 0))
    return min(MAX_REMAINING_CPU - micro,
               min(48, allocation['per_fixture']['cpu_minutes']) * 60 - micro,
               min(72, allocation['headroom_cpu_minutes']) * 60 - state['cpu_seconds'],
               min(84, allocation['aggregate_cpu_minutes']) * 60 - state['cpu_seconds'] - other)


class LinuxTree:
    """Dedicated parent; affinity and subreaping cover every worker phase.

    Inherited affinity enforces Q for this trusted runner (no task may widen its
    mask). The wall envelope also bounds CPU missed by a racing /proc snapshot.
    Neither that envelope nor affinity can bound a descheduled supervisor.
    """
    def __init__(self, policy):
        self.policy = policy
        self.scope = ProcessTreeScope(policy.rate_q)
        self.pid = None
        self.returncode = None
        self.highwater = 0.0

    def cpu(self):
        usage = resource.getrusage(resource.RUSAGE_SELF)
        children = resource.getrusage(resource.RUSAGE_CHILDREN)
        # No subtraction of supervisor startup/import CPU or previous children.
        precise = usage.ru_utime + usage.ru_stime + children.ru_utime + children.ru_stime
        self.highwater = max(self.highwater, precise, tree_snapshot()[0])
        return self.highwater

    def start(self, work):
        if len(list(Path('/proc/self/task').iterdir())) != 1:
            raise RuntimeError('supervisor requires a dedicated single-threaded parent')
        self.scope.start()
        try:
            self.pid = os.fork()
        except BaseException:
            self.scope.restore()
            raise
        if self.pid == 0:
            try:
                os.setsid()
                work()
                sys.stdout.flush()
                sys.stderr.flush()
            except BaseException:
                import traceback
                traceback.print_exc()
                os._exit(1)
            os._exit(0)

    def done(self):
        while True:
            try:
                pid, status = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                return True
            if not pid:
                return False
            self.scope.reaped_pids.append(pid)
            if pid == self.pid:
                self.returncode = os.waitstatus_to_exitcode(status)

    def kill(self):
        # Workers use their own sessions. A single killpg is insufficient;
        # enumerate descendants as well, and repeat after orphan adoption.
        # Once waitpid reaps the leader, its numeric PGID can be reused. Only
        # identity-checked descendants remain ours to signal after that point.
        if self.pid is not None and self.returncode is None:
            try:
                os.killpg(self.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        for pid, record in tree_snapshot()[1].items():
            current = _stat(pid)
            if current is not None and current['start'] == record['start']:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def restore(self):
        self.scope.restore()


def supervise(work, *, allowance, policy, backend, wall_allowance=float('inf'),
              clock=time.monotonic, sleep=time.sleep):
    """Testable synchronous parent loop, entirely independent of worker asyncio.

    The fixed wall envelope is intentionally conservative even when the worker
    is idle. CPU after the stop signal is still charged through confirmed reap.
    A late observation is a policy breach, never retrospective cap compliance.
    """
    origin = clock()
    initial_cpu = backend.cpu()
    work_wall = min((allowance - initial_cpu - policy.reserve) / policy.rate_q,
                    wall_allowance - policy.reserve / policy.rate_q)
    if work_wall <= 0:
        return {'status': 'refused_before_start', 'metered_cpu_seconds': initial_cpu,
                'reaping_confirmed': True, 'returncode': None, 'started': False}
    backend.start(work)
    stop_at = None
    stop_cpu = None
    max_observation = 0.0
    previous = origin
    status = 'completed'
    try:
        while True:
            done = backend.done()
            used = backend.cpu()
            now = clock()
            max_observation = max(max_observation, now - previous)
            previous = now
            if done:
                break
            breach = now - origin >= work_wall or used + policy.reserve >= allowance
            if stop_at is None and (breach or backend.returncode is not None):
                status = 'stopped' if breach else 'orphan_cleanup'
                stop_at, stop_cpu = now, used
            if stop_at is not None:
                backend.kill()
            # Fixed cadence relative to the preceding observation, not worker events.
            sleep(max(0.0, policy.poll_seconds - (clock() - previous)))
    except BaseException:
        # Never release the durable reservation while a descendant can run.
        while not backend.done():
            backend.kill()
            sleep(policy.poll_seconds)
        raise
    finally:
        backend.restore()
    final = backend.cpu()
    finished = clock()
    latency = 0.0 if stop_at is None else finished - stop_at
    assumptions_met = (max_observation <= policy.poll_seconds + policy.observation_delay_seconds and
                       latency <= policy.kill_seconds + policy.reap_seconds)
    return {'status': status, 'started': True, 'returncode': backend.returncode,
            'metered_cpu_seconds': final, 'reaping_confirmed': True,
            'cpu_after_stop_seconds': 0.0 if stop_cpu is None else final - stop_cpu,
            'kill_to_reap_wall_seconds': latency, 'max_observation_wall_seconds': max_observation,
            'latency_assumptions_met': assumptions_met,
            'charged_wall_seconds': finished - origin, 'work_wall_limit_seconds': work_wall}


def settle(state, before, receipt, policy, allowance):
    """Replace partial worker accounting with whole-parent lifetime plus tail reserve."""
    entry = state['fixtures'].setdefault('micro150', {'calls': 0, 'cpu_seconds': 0.0})
    old = before['fixtures'].get('micro150', {}).get('cpu_seconds', 0.0)
    charge = max(receipt['metered_cpu_seconds'] + policy.settlement_tail_cpu_seconds,
                 state['cpu_seconds'] - before['cpu_seconds'], entry['cpu_seconds'] - old)
    state['cpu_seconds'] = before['cpu_seconds'] + charge
    entry['cpu_seconds'] = old + charge
    state['solving_wall_seconds'] = max(state.get('solving_wall_seconds', 0),
        before['solving_wall_seconds'] + receipt.get('charged_wall_seconds', 0))
    state['aggregate_cpu_seconds_charged'] = state['cpu_seconds'] + max(
        720, state.get('non_headroom', {}).get('cpu_seconds', 0))
    accepted = (receipt['status'] == 'completed' and receipt['returncode'] == 0 and
                receipt.get('latency_assumptions_met', False) and charge <= allowance)
    receipt.update(charged_cpu_seconds=charge, tail_reserved_cpu_seconds=policy.settlement_tail_cpu_seconds,
                   allowance_cpu_seconds=allowance, overshoot_cpu_seconds=max(0.0, charge - allowance),
                   result_accepted=accepted, hard_cap=False, unconditional_overshoot_bound=None,
                   settlement_tail_measured=False,
                   policy=asdict(policy), reserve_h_cpu_seconds=policy.reserve)
    if receipt['overshoot_cpu_seconds'] > policy.reserve:
        state['allocation_halted'] = {
            'reason': 'single_lifetime_overshoot_exceeds_h',
            'overshoot_cpu_seconds': receipt['overshoot_cpu_seconds'],
            'reserve_h_cpu_seconds': policy.reserve,
            'reservation_id': receipt.get('reservation_id'),
            'requires_human_review': True}
    receipt['allocation_halted'] = bool(state.get('allocation_halted'))
    state['outer_active'] = None
    state.setdefault('overshoot', {})['lifetime_cpu_seconds'] = max(
        state.get('overshoot', {}).get('lifetime_cpu_seconds', 0), receipt['overshoot_cpu_seconds'])
    state.setdefault('lifetime_settlements', []).append(receipt)
    return receipt


def run(prereg_path, budget_path, output_dir, policy_path):
    """Only production entry point: unmet operating conditions refuse launch."""
    global WORKER_CONTEXT
    policy, declaration, policy_sha256 = load_policy(policy_path)
    # Parent lifetime CPU includes this parsing, validation and all final output.
    prereg_bytes = Path(prereg_path).read_bytes()
    prereg = json.loads(prereg_bytes)
    if prereg['fixture'] != 'micro150' or prereg['schema'] != 'slab-039-prereg-v4':
        raise ValueError('supervisor is for prospective micro150 v4 only')
    if policy.rate_q != prereg['cpu_enforcement']['rate_q']:
        raise ValueError('supervisor Q differs from preregistration')
    rate_cap = verify_cpu_max(policy)
    budget_path = Path(budget_path)
    with budget_path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        before = json.loads(budget_path.read_text())
        from sundai_controller.headroom_evidence import available_cpu, execution_identity, check_declared_calls
        allowance = available_cpu(prereg, before)
        from sundai_controller.evidence_profile import load_admission
        from sundai_hotspot.tap_oracle import HotSpotOracle
        identity = execution_identity(HotSpotOracle(prereg['grid'], prereg['grid'], fixture=prereg['fixture']))
        profile_admission = load_admission(prereg, prereg_path, allowance, identity=identity)
        check_declared_calls(prereg, before, profile_admission['declared_calls'])
        state = json.loads(json.dumps(before))
        deadline = min(DEADLINE, datetime.fromisoformat(prereg['clock']['deadline']))
        backend = LinuxTree(policy)
        reservation = {'id': uuid.uuid4().hex, 'reserved_cpu_seconds': allowance,
                       'policy': declaration, 'status': 'running',
                       'policy_sha256': policy_sha256,
                       'evidence_profile_admission': profile_admission,
                       'container_rate_cap': rate_cap,
                       'prereg_sha256': hashlib.sha256(prereg_bytes).hexdigest(),
                       'supervisor_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        state['outer_active'] = reservation
        _write(budget_path, state)
        WORKER_CONTEXT = {'lock': lock, 'policy': policy, 'reservation': reservation['id'],
                          'evidence_profile_admission': profile_admission,
                          'prereg_sha256': reservation['prereg_sha256']}
        def work():
            from sundai_controller.headroom import run_headroom
            asyncio.run(run_headroom('micro150', 0.79, prereg_path, output_dir, budget_path=budget_path))
        try:
            # Reservation I/O may block; recompute only after it finishes.
            wall_allowance = min((deadline - datetime.now(timezone.utc)).total_seconds(),
                min(5400, prereg['clock']['solving_wall_minutes'] * 60) -
                before['solving_wall_seconds'] - _lifetime_wall_seconds())
            receipt = supervise(work, allowance=allowance, policy=policy, backend=backend,
                                wall_allowance=wall_allowance)
        finally:
            WORKER_CONTEXT = None
        state = json.loads(budget_path.read_text())
        # A killed worker cannot run its finally block. Rebuild a durable
        # incomplete profile here after reap, before the final CPU sample.
        from sundai_controller.evidence_profile import build_profile
        try:
            records = []
            for attempt in state.get('attempts', [])[len(before.get('attempts', [])):]:
                directory = Path(attempt['artifact_directory']) / 'evaluations'
                for path in sorted(directory.glob('*.json')):
                    try:
                        records.append(json.loads(path.read_bytes()))
                    except (OSError, ValueError) as exc:
                        records.append({'status': 'incomplete', 'error': f'unreadable call receipt: {exc}',
                                        'artifact_directory': str(path)})
            if receipt.get('status') != 'completed' or receipt.get('returncode') != 0:
                records.append({'status': 'incomplete', 'error': 'supervisor interrupted run',
                                'charge_source': f"SETTLEMENT-{reservation['id']}.json"})
            profile = build_profile(records, identity)
            profile['supervisor_settlement'] = f"SETTLEMENT-{reservation['id']}.json"
            _write(Path(output_dir) / f"PHASE_PROFILE-{reservation['id']}.json", profile)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            # Evidence failure must still settle every charge and reject the run.
            receipt['status'] = 'evidence_failed'
            receipt['profile_error'] = f'{type(exc).__name__}: {exc}'
        # Includes startup, setup, all calls, serialization, persistence and reap.
        # Settlement writes/exit after this sample are conservatively charged T.
        receipt['metered_cpu_seconds'] = backend.cpu()
        receipt['charged_wall_seconds'] = _lifetime_wall_seconds()
        receipt['reservation_id'] = reservation['id']
        receipt['supervisor_sha256'] = reservation['supervisor_sha256']
        receipt['prereg_sha256'] = reservation['prereg_sha256']
        receipt['policy_sha256'] = reservation['policy_sha256']
        receipt['evidence_profile_admission'] = reservation['evidence_profile_admission']
        receipt['container_rate_cap'] = reservation['container_rate_cap']
        receipt = settle(state, before, receipt, policy, allowance)
        _write(budget_path, state)
        # Authoritative acceptance record lives outside the worker's provisional RESULT.
        _write(Path(output_dir) / f"SETTLEMENT-{reservation['id']}.json", receipt)
        return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prereg', type=Path, required=True)
    parser.add_argument('--budget', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--policy', type=Path, required=True)
    args = parser.parse_args()
    receipt = run(args.prereg, args.budget, args.out, args.policy)
    # Avoid an unreserved serialization phase after terminal settlement.
    raise SystemExit(0 if receipt['result_accepted'] else 2)


if __name__ == '__main__':
    # The worker imports the canonical name after fork; keep one context object.
    sys.modules['sundai_controller.headroom_supervisor'] = sys.modules[__name__]
    main()
