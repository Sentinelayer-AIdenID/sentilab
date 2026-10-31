#!/usr/bin/env python3
"""GitHub's atomic ref creation supplies durable allocation slots, not a run count."""
import argparse
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict
from pathlib import Path

from scripts.ci_allocation import (
    ALLOCATION_ID,
    CPU_CAP,
    EXPIRY,
    LAUNCH_CAP,
    RUN_CAP,
    Identity,
    RefAdmission,
    RefConflict,
)

PREFIX = 'tags/ci-allocation-' + ALLOCATION_ID + '/'


class GitHubRefs:
    def __init__(self, repository, credential, *, request=None):
        self.repository = repository
        self.credential = credential  # process memory only; never written or logged
        self.request = request or self._request
        self.bootstrap_sha = None
        self.tree = None
        self.commits = {}  # immutable objects; avoid rereading 200 commits per poll

    def _request(self, method, path, body=None):
        req = urllib.request.Request(
            'https://api.github.com/repos/' + self.repository + path,
            data=None if body is None else json.dumps(body).encode(), method=method,
            headers={'Authorization': 'Bearer ' + self.credential,
                     'Accept': 'application/vnd.github+json',
                     'X-GitHub-Api-Version': '2022-11-28', 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            # Do not render request headers or response bodies into artifacts/logs.
            if exc.code == 422 and method == 'POST' and path == '/git/refs':
                raise RefConflict('ref create conflict') from None
            raise RuntimeError(f'GitHub allocation store refused HTTP {exc.code}') from None
        except (OSError, ValueError):
            raise RuntimeError('GitHub allocation store unavailable') from None

    def read_bootstrap(self):
        ref = self.request('GET', '/git/ref/' + PREFIX + 'bootstrap')
        if ref['object']['type'] != 'commit':
            raise TypeError('bootstrap must point to an owner-created commit')
        self.bootstrap_sha = ref['object']['sha']
        commit = self.request('GET', '/git/commits/' + self.bootstrap_sha)
        self.tree = commit['tree']['sha']
        return json.loads(commit['message'])

    def read_slots(self):
        # No pagination ambiguity: the namespace is bounded to 200 refs. The API
        # returns matching refs (not the Actions list's first/default page).
        refs = self.request('GET', '/git/matching-refs/' + PREFIX + 'slot-')
        if not isinstance(refs, list):
            raise TypeError('unreadable allocation counter')
        slots = {}
        for ref in refs:
            name = ref['ref'].removeprefix('refs/' + PREFIX + 'slot-')
            if not name.isdecimal() or ref['object']['type'] != 'commit':
                raise RuntimeError('invalid allocation ref')
            slot = int(name)
            sha = ref['object']['sha']
            if sha not in self.commits:
                self.commits[sha] = self.request('GET', '/git/commits/' + sha)
            commit = self.commits[sha]
            record = json.loads(commit['message'])
            if (record['allocation_id'] != ALLOCATION_ID or record['slot'] != slot
                    or record['bootstrap_sha'] != self.bootstrap_sha or slot in slots):
                raise RuntimeError('invalid or changed allocation lineage')
            Identity(**record['identity'])
            slots[slot] = record['identity']
        return slots

    def claim(self, slot, identity):
        # A crash between commit creation and ref creation consumes no execution;
        # a lost response AFTER ref creation leaves the full reservation occupied.
        record = {'allocation_id': ALLOCATION_ID, 'slot': slot, 'identity': identity,
                  'bootstrap_sha': self.bootstrap_sha}
        commit = self.request('POST', '/git/commits', {
            'message': json.dumps(record, sort_keys=True), 'tree': self.tree,
            'parents': [self.bootstrap_sha]})
        self.request('POST', '/git/refs', {'ref': 'refs/' + PREFIX + f'slot-{slot:03}',
                                          'sha': commit['sha']})


def read_admission(store, identity, *, timeout=180, now=time.time,
                   clock=time.monotonic, sleep=time.sleep):
    """Read an independently created reservation; never claim or refund a slot."""
    if identity.attempt != '1':
        raise RuntimeError('rerun attempt refused; create a new run')
    deadline = clock() + timeout
    while True:
        if now() >= EXPIRY:
            raise RuntimeError('allocation expired')
        bootstrap = store.read_bootstrap()
        debit = bootstrap.get('historical_runs_debit')
        if (bootstrap.get('allocation_id') != ALLOCATION_ID or type(debit) is not int
                or not 0 <= debit <= RUN_CAP or not bootstrap.get('historical_consumption')):
            raise RuntimeError('invalid allocation bootstrap')
        slots = store.read_slots()
        if any(type(slot) is not int or not debit < slot <= RUN_CAP for slot in slots):
            raise RuntimeError('invalid allocation slots')
        matches = [(slot, row) for slot, row in slots.items()
                   if row['repository'] == identity.repository and row['run_id'] == identity.run_id]
        # An API call may have crossed either deadline, even when it found a slot.
        if now() >= EXPIRY or clock() >= deadline:
            raise RuntimeError('allocation expired or admission receipt timed out')
        if matches:
            if len(matches) != 1 or matches[0][1] != asdict(identity):
                raise RuntimeError('durable admission identity mismatch')
            return {'allocation_id': ALLOCATION_ID, 'slot': matches[0][0],
                    'identity': asdict(identity), 'bootstrap': bootstrap,
                    'launch_reservation': LAUNCH_CAP, 'cpu_reservation_seconds': CPU_CAP,
                    'mode': 'enforced', 'source': 'trusted workflow_run durable ref'}
        if len(slots) + debit >= RUN_CAP:
            raise RuntimeError('global run cap exhausted')
        sleep(min(5, max(0, deadline - clock())))


def workflow_identity(store, payload):
    """Resolve GitHub-authenticated upstream metadata, never PR-supplied code/data.

    The current merge may differ from an older queued run. The PR-side reader
    checks its actual GITHUB_SHA against this reservation and refuses any drift.
    """
    event = payload['workflow_run']
    repository = payload['repository']
    if (payload.get('action') != 'requested' or repository['full_name'] != store.repository
            or event['repository']['full_name'] != store.repository
            or event['path'] != '.github/workflows/ci.yml'
            or type(event['id']) is not int or event['id'] <= 0
            or type(event['run_attempt']) is not int or event['run_attempt'] != 1):
        raise ValueError('untrusted workflow or rerun request')
    # Recheck the upstream run: a delayed event cannot authorize an already
    # cancelled/completed run or a later attempt under its former identity.
    run = store.request('GET', '/actions/runs/' + str(event['id']))
    for key in ('id', 'run_attempt', 'workflow_id', 'head_sha', 'event', 'path'):
        if run[key] != event[key]:
            raise ValueError('upstream run identity changed')
    if run['status'] not in ('queued', 'in_progress', 'waiting', 'pending', 'requested'):
        raise ValueError('upstream run already terminal')
    head = event['head_sha']
    if event['event'] == 'push':
        if event['head_branch'] != repository['default_branch']:
            raise ValueError('only default-branch pushes may be admitted')
        build = head
    elif event['event'] == 'pull_request':
        pulls = event['pull_requests']
        if not isinstance(pulls, list) or len(pulls) != 1:
            raise ValueError('missing or ambiguous upstream pull request')
        number = pulls[0]['number']
        if type(number) is not int or number <= 0:
            raise ValueError('invalid upstream pull request')
        pull = store.request('GET', '/pulls/' + str(number))
        if (pull['state'] != 'open' or pull['head']['sha'] != head
                or pull['base']['repo']['full_name'] != store.repository
                or pull['base']['ref'] != repository['default_branch']):
            raise ValueError('pull request source or base changed')
        build = pull['merge_commit_sha']
        # Validate before interpolating an API path, including a pending merge.
        Identity(store.repository, str(event['id']), '1', 'container', {}, head, build)
        commit = store.request('GET', '/git/commits/' + build)
        if (commit['sha'] != build
                or [parent['sha'] for parent in commit['parents']] != [pull['base']['sha'], head]):
            raise ValueError('merge commit does not bind the expected base and head')
    else:
        raise ValueError('unsupported upstream event')
    return Identity(store.repository, str(event['id']), '1', 'container', {}, head, build)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--read-only', action='store_true')
    mode.add_argument('--workflow-run', action='store_true')
    parser.add_argument('path', type=Path)
    args = parser.parse_args()
    identity = None
    try:
        store = GitHubRefs(os.environ['GITHUB_REPOSITORY'], os.environ['GH_TOKEN'])
        if args.read_only:
            identity = Identity.environment()
            receipt = read_admission(store, identity)
        else:
            if os.environ['GITHUB_EVENT_NAME'] != 'workflow_run':
                raise ValueError('write admission requires the trusted workflow_run context')
            payload = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
            identity = workflow_identity(store, payload)
            receipt = RefAdmission(store).admit(identity)
        receipt['state'] = 'admitted'
        code = 0
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, AttributeError) as exc:
        receipt = {'allocation_id': ALLOCATION_ID,
                   'identity': None if identity is None else asdict(identity),
                   'state': 'admission_refused', 'reason': str(exc),
                   'launches_reserved': 0, 'cpu_seconds': 0}
        code = 1
    args.path.parent.mkdir(parents=True, exist_ok=True)
    args.path.write_text(json.dumps(receipt, indent=2) + '\n')
    print('CI allocation:', receipt['state'])
    return code


if __name__ == '__main__':
    raise SystemExit(main())
