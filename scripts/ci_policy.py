"""Allocation policy data. No owner grant is installed or inferred by this module."""
import hashlib
import json
import re
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Policy:
    allocation_id: str
    expires_at: int
    run_cap: int
    launch_cap: int = 100
    cpu_cap: int = 900
    not_before: int = 0


LEGACY = Policy('56314', 1793556000, 200)
OWNER_VARIABLE = 'CI_ALLOCATION_SELECTION'
SOURCE_FILES = frozenset({
    '.github/workflows/ci.yml', '.github/workflows/ci-allocation-admission.yml',
    '.github/workflows/ci-allocation-settlement.yml',
    'scripts/ci_policy.py', 'scripts/ci_owner_source.py', 'scripts/ci_transition.py',
    'scripts/ci_allocation.py', 'scripts/ci_admit.py', 'scripts/ci_cpu_meter.py',
    'scripts/ci_hotspot_gate.py', 'scripts/ci_reconcile.py', 'scripts/ci_container_job.sh',
})


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate owner JSON key')
            result[key] = value
        return result
    def bad_constant(_):
        raise ValueError('nonfinite owner JSON')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad_constant)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def sha(value, length=40):
    return type(value) is str and re.fullmatch('[0-9a-f]{%d}' % length, value) is not None


def selection(raw):
    if not raw:
        return None
    value = strict_json(raw)
    keys = {'schema', 'allocation_id', 'bootstrap_sha', 'grant_sha256',
            'source_commit', 'loader_sha256', 'activation_sha'}
    if (type(value) is not dict or set(value) != keys
            or value['schema'] != 'ci-allocation-selection-v1'
            or type(value['allocation_id']) is not str
            or not re.fullmatch('[a-z0-9][a-z0-9-]{0,63}', value['allocation_id'])
            or value['allocation_id'] == LEGACY.allocation_id
            or not sha(value['bootstrap_sha']) or not sha(value['source_commit'])
            or not sha(value['grant_sha256'], 64) or not sha(value['loader_sha256'], 64)
            or (value['activation_sha'] is not None and not sha(value['activation_sha']))):
        raise ValueError('invalid owner allocation selection')
    return value


def grant_policy(grant, selected, *, now=None, admitting=True):
    if selected is None or type(grant) is not dict or digest(grant) != selected['grant_sha256']:
        raise ValueError('owner grant digest mismatch')
    expected = {'schema', 'allocation_id', 'repository', 'workflow_path',
                'authorization_id', 'approved_by', 'historical_runs_debit',
                'historical_consumption', 'predecessor', 'policy', 'transition', 'source_files', 'ruleset_id'}
    if (set(grant) != expected or grant['schema'] != 'ci-allocation-grant-v2'
            or grant['allocation_id'] != selected['allocation_id']
            or grant['repository'] != 'Sentinelayer-AIdenID/sentilab'
            or grant['workflow_path'] != '.github/workflows/ci.yml'
            or any(type(grant[k]) is not str or not grant[k].strip()
                   for k in ('authorization_id', 'approved_by', 'historical_consumption'))
            or type(grant['historical_runs_debit']) is not int
            or grant['historical_runs_debit'] != 0
            or type(grant['ruleset_id']) is not int or grant['ruleset_id'] <= 0):
        raise ValueError('invalid prospective owner grant')
    old = grant['predecessor']
    if (type(old) is not dict or set(old) != {'allocation_id', 'bootstrap_sha', 'accounted_runs', 'closure_sha256'}
            or old['allocation_id'] != LEGACY.allocation_id
            or old['bootstrap_sha'] != '898982800967ee76621112c61a8dfd6764ec9e8d'
            or type(old['accounted_runs']) is not int or old['accounted_runs'] != 200
            or not sha(old['closure_sha256'], 64)):
        raise ValueError('missing preserved predecessor accounting')
    p = grant['policy']
    if (type(p) is not dict or set(p) != {'not_before', 'expires_at', 'run_cap', 'launch_cap', 'cpu_cap'}
            or any(type(v) is not int for v in p.values())
            or not 0 < p['not_before'] < p['expires_at']
            or not 1 <= p['run_cap'] <= 150
            or p['launch_cap'] != 100 or p['cpu_cap'] != 900):
        raise ValueError('invalid renewal limits')
    current = time.time() if now is None else now
    if admitting and not p['not_before'] <= current < p['expires_at']:
        raise ValueError('renewal grant inactive or expired')
    transition = grant['transition']
    if (type(transition) is not dict or set(transition) != {'head_sha', 'base_sha', 'slot'}
            or transition['head_sha'] != selected['source_commit']
            or not sha(transition['base_sha']) or type(transition['slot']) is not int
            or transition['slot'] != 1):
        raise ValueError('invalid transition scope')
    files = grant['source_files']
    if (type(files) is not dict or set(files) != SOURCE_FILES
            or not all(sha(v, 64) for v in files.values())
            or files['scripts/ci_owner_source.py'] != selected['loader_sha256']):
        raise ValueError('incomplete approved controller source')
    return Policy(grant['allocation_id'], **p)


def receipt_policy(receipt, raw_selection, *, now=None, admitting=True):
    if receipt.get('allocation_id') == LEGACY.allocation_id:
        return LEGACY
    chosen = selection(raw_selection)
    policy = grant_policy(receipt.get('owner_grant'), chosen, now=now, admitting=admitting)
    if (receipt.get('allocation_id') != policy.allocation_id
            or receipt.get('bootstrap_sha') != chosen['bootstrap_sha']
            or receipt.get('owner_grant_sha256') != chosen['grant_sha256']):
        raise ValueError('receipt does not bind selected owner grant')
    return policy
