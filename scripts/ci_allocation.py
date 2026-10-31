"""SLAB-046 policy and append-only accounting; stdlib only, no solver imports."""
import fcntl
import json
import math
import os
import re
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

ALLOCATION_ID = '56314'
EXPIRY = 1793556000  # 2026-11-01T18:00:00Z
RUN_CAP = 200
LAUNCH_CAP = 100
CPU_CAP = 900
STOP_RESERVE = 30
MAX_OBSERVATION_GAP = 2
TERMINAL = {'success', 'failure', 'timeout', 'killed', 'launch_error', 'interrupted'}


@dataclass(frozen=True)
class Identity:
    repository: str
    run_id: str
    attempt: str
    job: str
    matrix: dict
    head_sha: str
    build_sha: str

    def __post_init__(self):
        if (not re.fullmatch(r'[\w.-]+/[\w.-]+', self.repository)
                or not self.run_id.isdecimal() or not self.attempt.isdecimal()
                or self.job != 'container' or self.matrix != {}
                or not all(re.fullmatch(r'[a-f0-9]{40}', sha)
                           for sha in (self.head_sha, self.build_sha))):
            raise ValueError('invalid or unsupported allocation identity')

    @classmethod
    def environment(cls):
        return cls(os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_RUN_ID'],
                   os.environ['GITHUB_RUN_ATTEMPT'], 'container', {},
                   os.environ['PR_HEAD_SHA'], os.environ['GITHUB_SHA'])


class Ledger:
    """One journal, shared by every copied binary/worker; fsync BEFORE permission.

    An incomplete last write is corruption, never an invitation to reset a quota.
    A settlement cannot refund a reservation. Reopening validates the identity.
    """
    def __init__(self, path, identity):
        self.path = Path(path)
        self.identity = asdict(identity)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._locked() as (stream, events):
            if not events:
                self._append(stream, events, 'opened', allocation_id=ALLOCATION_ID,
                             identity=self.identity)

    @contextmanager
    def _locked(self):
        with self.path.open('a+', encoding='utf-8') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.seek(0)
            raw = stream.read()
            if raw and not raw.endswith('\n'):
                raise RuntimeError('corrupt allocation journal')
            try:
                events = [json.loads(line) for line in raw.splitlines()]
            except ValueError as exc:
                raise RuntimeError('corrupt allocation journal') from exc
            if events and (events[0].get('identity') != self.identity
                           or events[0].get('allocation_id') != ALLOCATION_ID
                           or any(row.get('sequence') != i for i, row in enumerate(events))):
                raise RuntimeError('allocation journal identity/sequence mismatch')
            yield stream, events

    @staticmethod
    def _append(stream, events, event, **fields):
        row = dict(sequence=len(events), event=event, at=time.time(), **fields)
        stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
        events.append(row)

    def events(self):
        with self._locked() as (_, events):
            return events

    def reserve(self, binary):
        with self._locked() as (stream, events):
            if any(row['event'] in ('finished', 'violation') for row in events):
                raise RuntimeError('allocation closed')
            count = sum(row['event'] == 'reserved' for row in events)
            if count >= LAUNCH_CAP:
                raise RuntimeError('launch cap exhausted')
            slot = count + 1
            self._append(stream, events, 'reserved', slot=slot, binary=binary)
            return slot

    def violation(self):
        with self._locked() as (stream, events):
            self._append(stream, events, 'violation', reason='unguarded HotSpot entry attempted')

    def started(self, slot, pid):
        with self._locked() as (stream, events):
            if (not any(row['event'] == 'reserved' and row['slot'] == slot for row in events)
                    or any(row['event'] in ('started', 'settled') and row.get('slot') == slot
                           for row in events)):
                raise RuntimeError('invalid launch start')
            self._append(stream, events, 'started', slot=slot, pid=pid)

    def settle(self, slot, state, returncode):
        if state not in TERMINAL:
            raise ValueError('invalid terminal state')
        with self._locked() as (stream, events):
            if not any(row['event'] == 'reserved' and row['slot'] == slot for row in events):
                raise RuntimeError('unreserved launch')
            if any(row['event'] == 'settled' and row['slot'] == slot for row in events):
                raise RuntimeError('launch already settled')
            self._append(stream, events, 'settled', slot=slot, state=state, returncode=returncode)

    def finish(self, state, cpu):
        with self._locked() as (stream, events):
            if any(row['event'] == 'finished' for row in events):
                return
            settled = {row['slot'] for row in events if row['event'] == 'settled'}
            for row in list(events):
                if row['event'] == 'reserved' and row['slot'] not in settled:
                    self._append(stream, events, 'settled', slot=row['slot'],
                                 state='interrupted', returncode=None)
            self._append(stream, events, 'finished', state=state, cpu=cpu)

    def summary(self):
        events = self.events()
        final = next((row for row in events if row['event'] == 'finished'), {})
        direct_calls = sum(row['event'] == 'violation' for row in events)
        seconds = (final.get('cpu') or {}).get('cpu_seconds')
        violations = []
        if seconds is not None and seconds > CPU_CAP:
            violations.append('cpu_limit_violated')
        if direct_calls:
            violations.append('launch_violation')
        return {'schema': 'ci-hotspot-settlement-v1', 'allocation_id': ALLOCATION_ID,
                'identity': self.identity, 'launch_limit': LAUNCH_CAP, 'cpu_limit_seconds': CPU_CAP,
                'launches_reserved': sum(row['event'] == 'reserved' for row in events),
                'launches_settled': sum(row['event'] == 'settled' for row in events),
                'executions_started': sum(row['event'] == 'started' for row in events),
                'direct_call_violations': direct_calls, 'violations': violations,
                'state': final.get('state', 'in_progress'), 'cpu': final.get('cpu'),
                'events': events, 'experiment_allowance_charged': 0,
                'historic_consumption': 'unknown; not reconstructed from visible run count'}


class CPUAccount:
    """cgroup CPU delta plus supervisor CPU delta and helper startup debit.

    The workload cgroup has cpu.max=100000/100000 (quota/period, with burst;
    neither a rolling-second bound nor a cumulative cap). The 30-second reserve
    covers observation (<=2 wall seconds), kill (<=5), quota burst and supervisor
    overhead. Missing/late/regressing observations fail closed, never use wall time
    as a CPU measurement. The final read is after cgroup.events populated=0.
    The caller adds the fixed helper startup debit to each supervisor sample.
    """
    def __init__(self, cgroup_cpu, supervisor_cpu, clock):
        self.start = cgroup_cpu, supervisor_cpu
        self.previous = cgroup_cpu, supervisor_cpu
        self.clock = clock
        self.used = 0

    def observe(self, cgroup_cpu, supervisor_cpu, clock):
        values = cgroup_cpu, supervisor_cpu, clock
        if (not all(math.isfinite(v) for v in values)
                or cgroup_cpu < self.previous[0] or supervisor_cpu < self.previous[1]
                or clock < self.clock or clock - self.clock > MAX_OBSERVATION_GAP):
            raise RuntimeError('CPU meter unavailable, regressed or observation overdue')
        self.used = cgroup_cpu - self.start[0] + supervisor_cpu - self.start[1]
        self.previous = cgroup_cpu, supervisor_cpu
        self.clock = clock
        return self.used >= CPU_CAP - STOP_RESERVE


def read_cpu(path):
    fields = dict(line.split() for line in (Path(path) / 'cpu.stat').read_text().splitlines())
    value = int(fields['usage_usec']) / 1_000_000
    if value < 0:
        raise RuntimeError('invalid cgroup CPU counter')
    return value


class RefConflict(RuntimeError):
    pass


class RefAdmission:
    """Immutable, atomic create-if-absent slots. Never count Actions run listings.

    Bootstrap is created by the allocation owner, not automatically on a miss.
    Each occupied slot is retained even after cancellation, failure or lost reply.
    """
    def __init__(self, store):
        self.store = store

    def admit(self, identity, *, now=None):
        if (time.time() if now is None else now) >= EXPIRY:
            raise RuntimeError('allocation expired')
        if identity.attempt != '1':
            raise RuntimeError('rerun attempt refused; create a new run')
        bootstrap = self.store.read_bootstrap()
        debit = bootstrap.get('historical_runs_debit')
        if (bootstrap.get('allocation_id') != ALLOCATION_ID or type(debit) is not int
                or not 0 <= debit <= RUN_CAP or not bootstrap.get('historical_consumption')):
            raise RuntimeError('invalid allocation bootstrap')
        for _ in range(RUN_CAP + 1):
            slots = self.store.read_slots()
            if any(type(slot) is not int or not debit < slot <= RUN_CAP for slot in slots):
                raise RuntimeError('invalid allocation slots')
            if any(row['repository'] == identity.repository and row['run_id'] == identity.run_id
                   for row in slots.values()):
                raise RuntimeError('run already admitted; refusing budget reset')
            available = next((n for n in range(debit + 1, RUN_CAP + 1) if n not in slots), None)
            if available is None:
                raise RuntimeError('global run cap exhausted')
            # Refresh the real clock on retries; fake time is explicit in unit tests.
            if (time.time() if now is None else now) >= EXPIRY:
                raise RuntimeError('allocation expired')
            try:
                self.store.claim(available, asdict(identity))
            except RefConflict:
                continue
            return {'allocation_id': ALLOCATION_ID, 'slot': available,
                    'identity': asdict(identity), 'bootstrap': bootstrap,
                    'launch_reservation': LAUNCH_CAP, 'cpu_reservation_seconds': CPU_CAP}
        raise RuntimeError('admission contention; refusing')
