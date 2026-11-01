#!/usr/bin/env python3
"""Read-only bootstrap loader. Its bytes MUST be checked before executing it.

This file is self-contained stdlib so the workflow never imports unverified code.
Owner selection comes from the repository variable, never a PR artifact or input.
"""
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

FILES = {
    '.github/workflows/ci.yml', '.github/workflows/ci-allocation-admission.yml',
    '.github/workflows/ci-allocation-settlement.yml',
    'scripts/ci_policy.py', 'scripts/ci_owner_source.py', 'scripts/ci_transition.py',
    'scripts/ci_allocation.py', 'scripts/ci_admit.py', 'scripts/ci_cpu_meter.py',
    'scripts/ci_hotspot_gate.py', 'scripts/ci_reconcile.py', 'scripts/ci_container_job.sh',
}


def read_json(raw):
    def pairs(items):
        value = {}
        for k, v in items:
            if k in value:
                raise ValueError('duplicate owner key')
            value[k] = v
        return value
    def reject(_):
        raise ValueError('nonfinite owner value')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def matches(value, pattern):
    return type(value) is str and re.fullmatch(pattern, value) is not None


def materialize(chosen, repository, directory, api):
    """Only immutable owner-pinned bytes become executable; API is injectable for offline proof."""
    if (repository != 'Sentinelayer-AIdenID/sentilab' or type(chosen) is not dict
            or set(chosen) != {'schema', 'allocation_id', 'bootstrap_sha', 'grant_sha256',
                               'source_commit', 'loader_sha256', 'activation_sha'}
            or chosen['schema'] != 'ci-allocation-selection-v1'
            or chosen['allocation_id'] == '56314'
            or not matches(chosen['allocation_id'], '[a-z0-9][a-z0-9-]{0,63}')
            or any(not matches(chosen[k], '[a-f0-9]{40}') for k in ('source_commit', 'bootstrap_sha'))
            or any(not matches(chosen[k], '[a-f0-9]{64}') for k in ('grant_sha256', 'loader_sha256'))
            or (chosen['activation_sha'] is not None and not matches(chosen['activation_sha'], '[a-f0-9]{40}'))):
        raise ValueError('invalid owner source selection')
    ref = api('/git/ref/tags/ci-allocation-' + chosen['allocation_id'] + '/bootstrap')
    if ref['object']['type'] != 'commit':
        raise ValueError('owner grant must be a commit')
    if ref['object']['sha'] != chosen['bootstrap_sha']:
        raise ValueError('owner grant ref changed')
    commit = api('/git/commits/' + chosen['bootstrap_sha'])
    if commit['sha'] != chosen['bootstrap_sha']:
        raise ValueError('owner commit mismatch')
    grant = read_json(commit['message'])
    if digest(grant) != chosen['grant_sha256'] or grant.get('allocation_id') != chosen['allocation_id']:
        raise ValueError('owner grant digest mismatch')
    hashes = grant.get('source_files')
    if (type(hashes) is not dict or set(hashes) != FILES
            or any(not matches(v, '[a-f0-9]{64}') for v in hashes.values())
            or hashes['scripts/ci_owner_source.py'] != chosen.get('loader_sha256')
            or grant.get('transition', {}).get('head_sha') != chosen['source_commit']):
        raise ValueError('invalid approved source manifest')
    source = api('/git/commits/' + chosen['source_commit'])
    tree = api('/git/trees/' + source['tree']['sha'] + '?recursive=1')
    if source['sha'] != chosen['source_commit'] or tree.get('truncated') or tree['sha'] != source['tree']['sha']:
        raise ValueError('invalid source tree')
    entries = {f['path']: f for f in tree['tree']}
    if len(entries) != len(tree['tree']):
        raise ValueError('duplicate source tree path')
    verified = {}
    for name in sorted(FILES):
        f = entries[name]
        if f['type'] != 'blob' or f['mode'] not in ('100644', '100755'):
            raise ValueError('controller source is not a regular file')
        blob = api('/git/blobs/' + f['sha'])
        if blob['sha'] != f['sha'] or blob['encoding'] != 'base64':
            raise ValueError('invalid source blob')
        b = base64.b64decode(''.join(blob['content'].split()), validate=True)
        if len(b) != f['size'] or hashlib.sha256(b).hexdigest() != hashes[name]:
            raise ValueError('approved controller source mismatch')
        verified[name] = b
    # Complete verification precedes writes, imports and execution. Paths are a fixed allowlist.
    for name, b in verified.items():
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b)
    return grant


def main():
    mode, output = sys.argv[1:3]
    if mode not in ('read', 'validate', 'terminal'):
        raise ValueError('loader is read-only')
    chosen = read_json(os.environ['CI_ALLOCATION_SELECTION'])
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != chosen['loader_sha256']:
        raise ValueError('loader digest mismatch')
    repository = os.environ['GITHUB_REPOSITORY']
    def api(endpoint):
        request = urllib.request.Request('https://api.github.com/repos/' + repository + endpoint,
            headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json'})
        with urllib.request.urlopen(request, timeout=15) as response:
            return read_json(response.read())
    directory = Path(tempfile.mkdtemp(prefix='ci-owner-', dir=os.environ['RUNNER_TEMP']))
    materialize(chosen, repository, directory, api)
    code = subprocess.run([sys.executable, '-I', '-S', '-c',
        'import sys,runpy;sys.path.insert(0,sys.argv.pop(1));'
        'runpy.run_module("scripts.ci_transition",run_name="__main__")',
        str(directory), mode, str(Path(output).resolve())], cwd=directory, check=False).returncode
    if code == 0 and mode == 'validate':
        with open(os.environ['GITHUB_OUTPUT'], 'a') as output_file:
            output_file.write('controller-directory=' + str(directory) + '\n')
    return code


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, TypeError, OSError):
        print('Owner-pinned controller refused', file=sys.stderr)
        raise SystemExit(1)
