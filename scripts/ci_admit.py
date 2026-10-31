#!/usr/bin/env python3
"""GitHub's atomic ref creation supplies durable allocation slots, not a run count."""
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request

from scripts.ci_allocation import ALLOCATION_ID, Identity, RefAdmission, RefConflict

PREFIX = 'tags/ci-allocation-' + ALLOCATION_ID + '/'


class GitHubRefs:
    def __init__(self, repository, credential, *, request=None):
        self.repository = repository
        self.credential = credential  # process memory only; never written or logged
        self.request = request or self._request
        self.bootstrap_sha = None
        self.tree = None

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
            raise RuntimeError('bootstrap must point to an owner-created commit')
        self.bootstrap_sha = ref['object']['sha']
        commit = self.request('GET', '/git/commits/' + self.bootstrap_sha)
        self.tree = commit['tree']['sha']
        return json.loads(commit['message'])

    def read_slots(self):
        # No pagination ambiguity: the namespace is bounded to 200 refs. The API
        # returns matching refs (not the Actions list's first/default page).
        refs = self.request('GET', '/git/matching-refs/' + PREFIX + 'slot-')
        if not isinstance(refs, list):
            raise RuntimeError('unreadable allocation counter')
        slots = {}
        for ref in refs:
            name = ref['ref'].removeprefix('refs/' + PREFIX + 'slot-')
            if not name.isdecimal() or ref['object']['type'] != 'commit':
                raise RuntimeError('invalid allocation ref')
            slot = int(name)
            commit = self.request('GET', '/git/commits/' + ref['object']['sha'])
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


def main():
    path = Path(sys.argv[1])
    identity = Identity.environment()
    try:
        receipt = RefAdmission(GitHubRefs(identity.repository, os.environ['GH_TOKEN'])).admit(identity)
        receipt['state'] = 'admitted'
        code = 0
    except (RuntimeError, ValueError, KeyError) as exc:
        from dataclasses import asdict
        receipt = {'allocation_id': ALLOCATION_ID, 'identity': asdict(identity),
                   'state': 'admission_refused', 'reason': str(exc),
                   'launches_reserved': 0, 'cpu_seconds': 0}
        code = 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2) + '\n')
    print('CI allocation:', receipt['state'])
    return code


if __name__ == '__main__':
    raise SystemExit(main())
