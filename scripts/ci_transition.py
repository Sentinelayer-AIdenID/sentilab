#!/usr/bin/env python3
"""Prospective owner-selected allocation; no grant or reservation is implicit.

reserve-transition is an OPERATOR command, never called by a PR workflow. All
other modes use read credentials. Source selection is supplied independently by
the owner, not taken from a downloaded admission or settlement artifact.
"""
import argparse
import base64
import hashlib
import json
import os
import time
from dataclasses import asdict
from pathlib import Path

from scripts.ci_admit import GitHubRefs, read_admission, workflow_identity
from scripts.ci_allocation import Identity, RefAdmission
from scripts.ci_policy import LEGACY, Policy, grant_policy, selection, sha, strict_json


def selected_store(repository, credential, chosen, *, request=None, now=None, admitting=True):
    if chosen is None:
        raise ValueError('owner allocation selection is absent')
    store = GitHubRefs(repository, credential, request=request,
                       policy=Policy(chosen['allocation_id'], 0, 0),
                       expected_bootstrap=chosen['bootstrap_sha'])
    grant = store.read_bootstrap()
    store.policy = grant_policy(grant, chosen, now=now, admitting=admitting)
    if repository != grant['repository']:
        raise ValueError('owner grant repository mismatch')
    return store, grant


def protection(store, grant):
    value = store.request('GET', '/rulesets/' + str(grant['ruleset_id']))
    if (value.get('id') != grant['ruleset_id'] or value.get('target') != 'tag'
            or value.get('enforcement') != 'active' or value.get('bypass_actors') != []
            or value.get('conditions') != {'ref_name': {'include': [
                'refs/tags/ci-allocation-' + store.policy.allocation_id + '/**'], 'exclude': []}}
            or not {'update', 'deletion', 'non_fast_forward'} <= {
                row['type'] for row in value.get('rules', [])}):
        raise ValueError('new owner namespace is not immutable without bypass')


def verify_local(grant, root=Path(__file__).resolve().parents[1]):
    for name, expected in grant['source_files'].items():
        path = root / name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('local controller differs from owner source')


def verify_tree(store, commit_sha, hashes):
    if not sha(commit_sha):
        raise ValueError('invalid source commit')
    commit = store.request('GET', '/git/commits/' + commit_sha)
    if commit['sha'] != commit_sha or not sha(commit['tree']['sha']):
        raise ValueError('source commit mismatch')
    tree = store.request('GET', '/git/trees/' + commit['tree']['sha'] + '?recursive=1')
    entries = {row['path']: row for row in tree['tree']}
    if (tree.get('truncated') or tree['sha'] != commit['tree']['sha']
            or len(entries) != len(tree['tree'])):
        raise ValueError('incomplete source tree')
    for name, expected in hashes.items():
        entry = entries[name]
        if (entry['type'] != 'blob' or entry['mode'] not in ('100644', '100755')
                or not sha(entry['sha'])):
            raise ValueError('controller source is not a regular blob')
        blob = store.request('GET', '/git/blobs/' + entry['sha'])
        if blob['sha'] != entry['sha'] or blob['encoding'] != 'base64':
            raise ValueError('invalid source blob')
        raw = base64.b64decode(''.join(blob['content'].split()), validate=True)
        if len(raw) != entry['size'] or hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('runtime workflow/controller differs from owner source')
    return commit


def active_run(store, run_id):
    if type(run_id) is not str or not run_id.isdecimal() or int(run_id) <= 0:
        raise ValueError('invalid run id')
    run = store.request('GET', '/actions/runs/' + run_id)
    if str(run['id']) != run_id:
        raise ValueError('run metadata mismatch')
    repo = store.request('GET', '')
    return workflow_identity(store, {'action': 'requested', 'repository': repo, 'workflow_run': run})


def predecessor_closed(store, identity):
    """Read the old namespace, never rewrite, refund or reserve from it."""
    old = GitHubRefs(store.repository, store.credential, request=store.request,
                     expected_bootstrap='898982800967ee76621112c61a8dfd6764ec9e8d')
    grant = old.read_bootstrap()
    debit = grant.get('historical_runs_debit')
    slots = old.read_slots()
    if (grant.get('allocation_id') != LEGACY.allocation_id or type(debit) is not int
            or not 0 <= debit <= LEGACY.run_cap or not grant.get('historical_consumption')
            or any(type(n) is not int or not debit < n <= LEGACY.run_cap for n in slots)
            or debit + len(slots) != LEGACY.run_cap):
        raise ValueError('predecessor accounting is not closed at 200')
    if any(row['run_id'] == identity.run_id for row in slots.values()):
        raise ValueError('run already charged in predecessor allocation')


def transition_scope(store, grant, identity):
    if identity.head_sha != grant['transition']['head_sha'] or identity.attempt != '1':
        raise ValueError('not the prospective transition source or first attempt')
    commit = verify_tree(store, identity.build_sha, grant['source_files'])
    if [p['sha'] for p in commit['parents']] != [grant['transition']['base_sha'], identity.head_sha]:
        raise ValueError('transition build does not bind exact base and head')


def activated(store, grant, chosen):
    activation = chosen['activation_sha']
    if activation is None:
        raise ValueError('ordinary admission awaits owner activation')
    repo = store.request('GET', '')
    if repo['full_name'] != store.repository or repo['default_branch'] != 'main':
        raise ValueError('unexpected activation repository or branch')
    tip = store.request('GET', '/git/ref/heads/main')['object']['sha']
    for base, head in ((chosen['source_commit'], activation), (activation, tip)):
        if not sha(head) or store.request('GET', '/compare/' + base + '...' + head)['status'] not in ('ahead', 'identical'):
            raise ValueError('activation does not contain approved source on main')
    verify_tree(store, activation, grant['source_files'])
    first = store.read_slots().get(1)
    if first is None:
        raise ValueError('owner transition slot is absent')
    transition_scope(store, grant, Identity(**first))
    run = store.request('GET', '/actions/runs/' + first['run_id'])
    if (run['id'] != int(first['run_id']) or run['run_attempt'] != 1
            or run['repository']['full_name'] != store.repository
            or run['path'] != grant['workflow_path'] or run['head_sha'] != first['head_sha']
            or run['status'] != 'completed' or run['conclusion'] != 'success'):
        raise ValueError('transition workflow did not complete successfully')
    jobs = store.request('GET', '/actions/runs/' + first['run_id'] + '/attempts/1/jobs?per_page=100')
    if type(jobs['total_count']) is not int or jobs['total_count'] != len(jobs['jobs']):
        raise ValueError('incomplete transition job evidence')
    for name in ('container', 'contracts', 'secret-scan'):
        matches = [job for job in jobs['jobs'] if job['name'] == name]
        if len(matches) != 1 or matches[0]['status'] != 'completed' or matches[0]['conclusion'] != 'success':
            raise ValueError('transition required gate did not pass')


def bind_receipt(receipt, store, grant, chosen):
    return dict(receipt, state='admitted', mode='enforced',
                bootstrap_sha=chosen['bootstrap_sha'], owner_grant=grant,
                owner_grant_sha256=chosen['grant_sha256'],
                source_commit=chosen['source_commit'],
                source='owner-pinned controller and immutable allocation ref')


def reserve_transition(store, grant, chosen, run_id, *, now=time.time):
    if chosen['activation_sha'] is not None:
        raise ValueError('transition reservation is closed after activation')
    protection(store, grant)
    identity = active_run(store, run_id)
    transition_scope(store, grant, identity)
    predecessor_closed(store, identity)
    # Slot 1 is the ENTIRE bridge. Conflicts/lost replies may never consume slot 2.
    if store.read_slots():
        raise ValueError('transition namespace already occupied; inspect retained record')
    grant_policy(grant, chosen, now=now())
    store.claim(1, asdict(identity))
    return bind_receipt(read_admission(store, identity, timeout=30, policy=store.policy, now=now),
                        store, grant, chosen)


def admit_activated(store, grant, chosen, payload):
    protection(store, grant)
    activated(store, grant, chosen)
    identity = workflow_identity(store, payload)
    verify_tree(store, identity.build_sha, grant['source_files'])
    predecessor_closed(store, identity)
    return bind_receipt(RefAdmission(store, store.policy).admit(identity), store, grant, chosen)


def reader(store, grant, chosen, identity, *, timeout=180, now=time.time):
    protection(store, grant)
    if active_run(store, identity.run_id) != identity:
        raise ValueError('live run identity differs from workflow environment')
    if identity.head_sha == chosen['source_commit']:
        transition_scope(store, grant, identity)
    else:
        activated(store, grant, chosen)
        verify_tree(store, identity.build_sha, grant['source_files'])
    receipt = read_admission(store, identity, timeout=timeout, now=now, policy=store.policy)
    if receipt['slot'] == 1:
        transition_scope(store, grant, identity)
    elif chosen['activation_sha'] is None:
        raise ValueError('non-transition reservation before activation')
    return bind_receipt(receipt, store, grant, chosen)


def validate(store, grant, chosen, receipt, identity):
    if os.environ.get('ADMISSION_RESULT') != 'success':
        raise ValueError('admission job did not succeed')
    expected = reader(store, grant, chosen, identity, timeout=30)
    # Full exact receipt comparison rechecks the independent owner grant and ref.
    if receipt != expected:
        raise ValueError('admission artifact differs from independent owner receipt')
    return expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('read', 'validate', 'terminal', 'reserve-transition'))
    parser.add_argument('output', type=Path)
    parser.add_argument('--run-id')
    args = parser.parse_args()
    chosen = None
    try:
        chosen = selection(os.environ.get('CI_ALLOCATION_SELECTION'))
        store, grant = selected_store(os.environ['GITHUB_REPOSITORY'], os.environ['GH_TOKEN'], chosen,
                                       admitting=args.mode != 'terminal')
        verify_local(grant)
        if args.mode == 'terminal':
            # This source is reviewed locally or materialized by the verified read-only loader.
            from scripts.ci_reconcile import main as terminal
            terminal(args.output)
            return 0
        if args.mode == 'reserve-transition':
            if os.environ.get('GITHUB_ACTIONS') == 'true':
                raise ValueError('transition reservation requires the separate operator process')
            receipt = reserve_transition(store, grant, chosen, args.run_id)
        else:
            identity = Identity.environment()
            if args.mode == 'read':
                receipt = reader(store, grant, chosen, identity)
            else:
                receipt = validate(store, grant, chosen, strict_json(args.output.read_text()), identity)
        code = 0
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, AttributeError):
        # Do not copy API exception bodies or credentials into public artifacts.
        receipt = {'allocation_id': None if chosen is None else chosen['allocation_id'],
                   'state': 'admission_refused', 'reason': 'owner-selected admission failed',
                   'reservation_state': 'unresolved; inspect immutable owner records',
                   'executions_started': None, 'cpu_seconds': None,
                   'charged_launches': 100, 'charged_cpu_seconds': 900}
        if args.mode == 'terminal':
            from scripts.ci_reconcile import write_terminal
            write_terminal(args.output, dict(receipt, schema='ci-hotspot-terminal-v1',
                measurement='owner-selected terminal source or grant unavailable; consumption unknown'))
            return 1
        code = 1
    if args.mode != 'validate' or code != 0:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2) + '\n')
    print('Owner-selected allocation:', receipt['state'])
    return code


if __name__ == '__main__':
    raise SystemExit(main())
