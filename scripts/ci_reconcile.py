#!/usr/bin/env python3
"""Terminal workflow witness, also runs after runner loss or admission job failure.

Downloaded artifacts are parsed as data only. Never execute code from the run.
An absent/unreadable measurement remains unknown and charges the full reservation.
"""
import hashlib
import json
import math
import os
import sys
from pathlib import Path

from scripts.ci_admit import GitHubRefs
from scripts.ci_allocation import CPU_CAP, EXPIRY, LAUNCH_CAP, Identity

STATES = {'success', 'failure', 'timeout', 'killed', 'launch_error', 'interrupted',
          'cancelled', 'expired', 'cpu_exhausted', 'launch_violation', 'cpu_limit_violated',
          'inconclusive'}


def nonnegative_finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def valid_settlement(value):
    if (not isinstance(value, dict) or value.get('schema') != 'ci-hotspot-settlement-v1'
            or not isinstance(value.get('state'), str) or value['state'] not in STATES
            or value.get('launch_limit') != LAUNCH_CAP or value.get('cpu_limit_seconds') != CPU_CAP
            or value.get('experiment_allowance_charged') != 0):
        return False
    counts = [value.get(key) for key in ('launches_reserved', 'launches_settled',
                                        'executions_started', 'direct_call_violations')]
    if not all(type(n) is int and n >= 0 for n in counts):
        return False
    reserved, settled, started, violations = counts
    if not (started <= reserved == settled <= LAUNCH_CAP):
        return False
    if value['state'] == 'success' and violations:
        return False
    cpu = value.get('cpu')
    if not isinstance(cpu, dict) or 'cpu_seconds' not in cpu:
        return False
    seconds = cpu['cpu_seconds']
    charge = cpu.get('charged_cpu_seconds', seconds)
    if not nonnegative_finite(charge):
        return False
    if seconds is None:
        measurement = cpu.get('measurement')
        if (value['state'] not in ('inconclusive', 'interrupted') or charge < CPU_CAP
                or not isinstance(measurement, str)
                or not (measurement == 'unavailable' or 'unknown' in measurement)):
            return False
    elif not nonnegative_finite(seconds) or charge < seconds:
        return False
    for key in ('cgroup_cpu_seconds', 'supervisor_cpu_seconds', 'last_cgroup_cpu_seconds',
                'helper_startup_cpu_seconds'):
        unknown_component = (key == 'last_cgroup_cpu_seconds'
                             or (key == 'helper_startup_cpu_seconds' and seconds is None))
        if (key in cpu and not (unknown_component and cpu[key] is None)
                and not nonnegative_finite(cpu[key])):
            return False
    if value['state'] in ('inconclusive', 'interrupted') and charge < CPU_CAP:
        return False
    over_cap = seconds is not None and seconds > CPU_CAP
    expected_violations = (['cpu_limit_violated'] if over_cap else []) + (
        ['launch_violation'] if violations else [])
    # Older artifacts did not have the list; both facts remain independently
    # supported by their counters. New lists must agree with those counters.
    if 'violations' in value and value['violations'] != expected_violations:
        return False
    if value['state'] == 'cpu_limit_violated' and not over_cap:
        return False
    if value['state'] == 'launch_violation' and not violations:
        return False
    if over_cap and value['state'] not in ('cpu_limit_violated', 'inconclusive', 'launch_violation'):
        return False
    try:
        # No nonstandard NaN/Infinity anywhere in forwarded artifact evidence.
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError, OverflowError):
        return False
    return True


def reconcile(identity, conclusion, settlement=None):
    base = {'schema': 'ci-hotspot-terminal-v1', 'allocation_id': '56314',
            'identity': identity, 'workflow_conclusion': conclusion,
            'experiment_allowance_charged': 0}
    if (isinstance(settlement, dict)
            and (settlement.get('identity') != identity or settlement.get('allocation_id') != '56314')):
        raise ValueError('settlement identity does not match durable reservation')
    if not valid_settlement(settlement):
        return dict(base, measurement='unknown: runner or settlement lost or invalid',
                    executions_started=None, cpu_seconds=None,
                    charged_launches=LAUNCH_CAP, charged_cpu_seconds=CPU_CAP)
    return dict(base, measurement='settlement artifact', settlement=settlement)


def authorized_bootstrap(raw, repository, event):
    """Owner repository variable, independently supplied to trusted workflow_run.

    Exact run identities reserve their full allowances even if their artifacts
    are lost. Retain authorization after expiry so terminal recovery can read it.
    """
    if not raw:
        return None
    value = json.loads(raw)
    if (not isinstance(value, dict) or value.get('schema') != 'ci-hotspot-bootstrap-authorization-v1'
            or value.get('allocation_id') != '56314' or value.get('repository') != repository
            or value.get('workflow_path') != '.github/workflows/ci.yml'
            or not isinstance(value.get('authorization_id'), str) or not value['authorization_id']
            or not isinstance(value.get('approved_by'), str) or not value['approved_by']
            or type(value.get('expires_at')) is not int or not 0 < value['expires_at'] <= EXPIRY
            or not isinstance(value.get('runs'), list) or not 1 <= len(value['runs']) <= 200):
        raise ValueError('invalid owner bootstrap authorization')
    seen, matched, matched_base, matched_context = set(), None, None, None
    for entry in value['runs']:
        if not isinstance(entry, dict) or set(entry) != {'identity', 'base_sha', 'context_json', 'context_sha256'}:
            raise ValueError('invalid owner rollout entry fields')
        identity = entry['identity']
        try:
            Identity(**identity)
        except (AttributeError, TypeError) as exc:
            raise ValueError('invalid bootstrap identity') from exc
        base = entry['base_sha']
        if (identity['repository'] != repository
                or identity['run_id'] in seen or not isinstance(base, str)
                or len(base) != 40 or any(c not in 'abcdef0123456789' for c in base)):
            raise ValueError('invalid or duplicate bootstrap run')
        seen.add(identity['run_id'])
        pinned_json = entry['context_json']
        pinned = json.loads(pinned_json)
        if (pinned_json != json.dumps(pinned, sort_keys=True, separators=(',', ':'))
                or hashlib.sha256(pinned_json.encode()).hexdigest() != entry['context_sha256']):
            raise ValueError('invalid pinned runtime context digest')
        previous = pinned['GITHUB_RUN_ATTEMPT']
        if (not isinstance(previous, str) or not previous.isdecimal() or int(previous) < 1
                or previous != str(int(previous)) or str(int(previous) + 1) != identity['attempt']):
            raise ValueError('pinned context must be the immediate predecessor attempt')
        ref = pinned['GITHUB_WORKFLOW_REF']
        bound = {'GITHUB_SHA': identity['build_sha'], 'GITHUB_RUN_ID': identity['run_id'],
                     'GITHUB_RUN_ATTEMPT': previous, 'GITHUB_REPOSITORY': identity['repository'],
                     'GITHUB_WORKFLOW_REF': ref, 'job': identity['job'], 'matrix': identity['matrix'],
                     'head_sha': identity['head_sha'], 'base_sha': base}
        if (pinned != bound or not isinstance(ref, str)
                or not ref.startswith(repository + '/.github/workflows/ci.yml@')):
            raise ValueError('pinned context conflicts with authorized source')
        if identity['run_id'] == str(event['id']) and identity['attempt'] == str(event['run_attempt']):
            if identity['head_sha'] != event.get('head_sha'):
                raise ValueError('bootstrap head identity mismatch')
            if event.get('event') == 'pull_request':
                pulls = event.get('pull_requests')
                if (not isinstance(pulls, list) or len(pulls) != 1
                        or pulls[0]['head']['sha'] != identity['head_sha']
                        or pulls[0]['base']['sha'] != base):
                    raise ValueError('bootstrap base identity mismatch')
            elif (event.get('event') != 'push' or base != identity['head_sha']
                  or identity['build_sha'] != identity['head_sha']):
                raise ValueError('bootstrap push identity mismatch')
            # workflow_run has no synthetic merge SHA. reconcile() requires the
            # settlement's full identity (including build/job/matrix) to match.
            matched = identity
            matched_base = base
            matched_context = entry
    if matched is None:
        return None
    if event.get('path') != value['workflow_path']:
        raise ValueError('bootstrap workflow identity mismatch')
    provenance = {key: value[key] for key in
                  ('authorization_id', 'approved_by', 'expires_at', 'workflow_path')}
    provenance.update(context_json=matched_context['context_json'], context_sha256=matched_context['context_sha256'],
        authorized_attempt=matched['attempt'], authorized_runs=len(value['runs']), sha256=hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest())
    live = dict(json.loads(matched_context['context_json']), GITHUB_RUN_ATTEMPT=matched['attempt'])
    live_json = json.dumps(live, sort_keys=True, separators=(',', ':'))
    return {'identity': matched, 'base_sha': matched_base, 'bootstrap_authorization': provenance,
            'runtime_context_json': live_json, 'runtime_context_sha256': hashlib.sha256(live_json.encode()).hexdigest(),
            'rollout_debit': {'run_id': matched['run_id'], 'attempt': matched['attempt'], 'charged_launches': LAUNCH_CAP,
                             'charged_cpu_seconds': CPU_CAP,
                             'scope': 'owner rollout; outside durable run counter'}}


def main():
    directory = Path(sys.argv[1])
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())['workflow_run']
    run_id, attempt = str(event['id']), str(event['run_attempt'])
    repository = os.environ['GITHUB_REPOSITORY']
    witness = {'schema': 'ci-hotspot-terminal-v1', 'allocation_id': '56314', 'run_id': run_id, 'attempt': attempt,
               'workflow_conclusion': event['conclusion'], 'repository': repository,
               'measurement': 'durable admission unreadable; consumption unknown',
               'cpu_seconds': None, 'executions_started': None,
               'charged_cpu_seconds': CPU_CAP, 'charged_launches': LAUNCH_CAP}
    try:
        bootstrap = authorized_bootstrap(os.environ.get('CI_BOOTSTRAP_AUTHORIZATION'), repository, event)
        if bootstrap is not None:
            # Owner provenance precedes the durable-slot lookup. A rollout run
            # intentionally has no slot, including when settlement was lost.
            identity = bootstrap.pop('identity')
            witness = dict(reconcile(identity, event['conclusion']), admission_mode='bootstrap', **bootstrap)
            admission = json.loads((directory / 'download' / 'admission.json').read_text())
            if (not isinstance(admission, dict) or admission.get('state') != 'admitted'
                    or admission.get('mode') != 'bootstrap' or admission.get('identity') != identity
                    or admission.get('base_sha') != bootstrap['base_sha']
                    or admission.get('runtime_context_json') != bootstrap['runtime_context_json']
                    or admission.get('runtime_context_sha256') != bootstrap['runtime_context_sha256']):
                raise ValueError('bootstrap admission identity mismatch')
            path = directory / 'download' / 'settlement.json'
            settlement = json.loads(path.read_text()) if path.exists() else None
            witness = dict(reconcile(identity, event['conclusion'], settlement),
                           admission_mode='bootstrap', **bootstrap)
            write_terminal(directory, witness)
            return
        store = GitHubRefs(repository, os.environ['GH_TOKEN'])
        store.read_bootstrap()
        slots = store.read_slots()
        matches = [identity for identity in slots.values()
                   if identity['run_id'] == run_id and identity['attempt'] == attempt
                   and identity['repository'] == repository]
        if len(matches) > 1:
            raise ValueError('multiple durable admissions for one run')
        if matches:
            witness = reconcile(matches[0], event['conclusion'])
            path = directory / 'download' / 'settlement.json'
            settlement = json.loads(path.read_text()) if path.exists() else None
            witness = reconcile(matches[0], event['conclusion'], settlement)
        else:
            witness.update(measurement='no independent admission evidence; consumption unknown')
    except (OSError, RuntimeError, ValueError, TypeError, KeyError):
        # This witness does not unlock further admission and cannot replenish slots.
        pass
    write_terminal(directory, witness)


def write_terminal(directory, witness):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'terminal.json').write_text(json.dumps(witness, indent=2, allow_nan=False) + '\n')
    print('Allocation terminal witness:', witness['measurement'])


if __name__ == '__main__':
    main()
