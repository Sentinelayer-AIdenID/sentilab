"""Append-only, fsync-before-launch CPU reservations under a cross-process file lock."""
from contextlib import contextmanager
import fcntl
import json
import math
from pathlib import Path
import uuid

RESERVE = 10
GLOBAL_CAP = 3600
TOKEN_CAP = 30
PARALLEL = 4


class Refused(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code


class Ledger:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def locked(self):
        with self.path.open('a+', encoding='utf-8') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.seek(0)
            records = {}
            for line in stream:
                row = json.loads(line)  # A torn/corrupt ledger fails closed, never silently forgets a charge.
                key = row['reservation_id']
                if row['phase'] == 'reserved' and key not in records:
                    if row['cpu_s'] != RESERVE:
                        raise ValueError('invalid reservation')
                    records[key] = row
                elif row['phase'] == 'settled' and key in records and records[key]['phase'] == 'reserved':
                    if not math.isfinite(row['cpu_s']) or row['cpu_s'] < 0:
                        raise ValueError('invalid settlement')
                    records[key] = {**records[key], **row}
                else:
                    raise ValueError('invalid ledger sequence')
            yield stream, records

    @staticmethod
    def append(stream, row):
        import os
        stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
        directory = os.open(Path(stream.name).parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def budget_left(self):
        with self.locked() as (_, records):
            return max(0.0, GLOBAL_CAP - sum(r['cpu_s'] for r in records.values()))

    def reserve(self, binding, operation, revalidate):
        with self.locked() as (stream, records):
            revalidate()  # includes current signature/admission and layout, after acquiring the dispatch lock
            rows = list(records.values())
            same_key = [r for r in rows if r['principal'] == binding['principal']
                        and r['manifest_id'] == binding['manifest_id'] and r['request_key'] == binding['request_key']]
            same_run = [r for r in rows if r['run_id'] == binding['run_id']]
            for row in same_key + same_run:
                if any(row[k] != v for k, v in binding.items()):
                    raise Refused(409, 'idempotency_conflict')
            prior = next((r for r in same_run if r['operation'] == 'score'), None)
            existing = next((r for r in same_run if r['operation'] == operation), None)
            if existing:
                if existing['phase'] == 'settled':
                    return None, existing['response'], None
                raise Refused(429, 'busy')
            if operation == 'replay' and (prior is None or prior.get('response', {}).get('state') != 'evaluated'):
                raise Refused(409, 'unknown_proposal')
            global_cpu = sum(r['cpu_s'] for r in rows)
            token_cpu = sum(r['cpu_s'] for r in rows if r['token_ref'] == binding['token_ref'])
            if global_cpu + RESERVE > GLOBAL_CAP or token_cpu + RESERVE > TOKEN_CAP:
                raise Refused(403, 'budget_exhausted')
            if sum(r['phase'] == 'reserved' for r in rows) >= PARALLEL:
                raise Refused(429, 'busy')
            row = {**binding, 'phase': 'reserved', 'operation': operation,
                   'reservation_id': str(uuid.uuid4()), 'cpu_s': RESERVE}
            self.append(stream, row)
            return row['reservation_id'], None, prior['response'] if prior else None

    def settle(self, reservation_id, cpu_s, response):
        with self.locked() as (stream, records):
            if records[reservation_id]['phase'] != 'reserved':
                raise ValueError('already settled')
            self.append(stream, {'reservation_id': reservation_id, 'phase': 'settled',
                                 'cpu_s': cpu_s, 'response': response})
