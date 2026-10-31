#!/usr/bin/env python3
"""Terminal workflow witness, also runs after runner loss or admission job failure.

Downloaded artifacts are parsed as data only. Never execute code from the run.
An absent/unreadable measurement remains unknown and charges the full reservation.
"""
import json
import os
import sys
from pathlib import Path

from scripts.ci_admit import GitHubRefs
from scripts.ci_allocation import CPU_CAP, LAUNCH_CAP


def reconcile(identity, conclusion, settlement=None):
    base = {'schema': 'ci-hotspot-terminal-v1', 'allocation_id': '56314',
            'identity': identity, 'workflow_conclusion': conclusion,
            'experiment_allowance_charged': 0}
    if settlement is not None:
        if settlement.get('identity') != identity or settlement.get('allocation_id') != '56314':
            raise ValueError('settlement identity does not match durable reservation')
        if (settlement.get('state') == 'in_progress'
                or settlement.get('launches_reserved') != settlement.get('launches_settled')):
            settlement = None
    if settlement is None:
        return dict(base, measurement='unknown: runner or settlement lost',
                    executions_started=None, cpu_seconds=None,
                    charged_launches=LAUNCH_CAP, charged_cpu_seconds=CPU_CAP)
    return dict(base, measurement='settlement artifact', settlement=settlement)


def main():
    directory = Path(sys.argv[1])
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())['workflow_run']
    run_id, attempt = str(event['id']), str(event['run_attempt'])
    repository = os.environ['GITHUB_REPOSITORY']
    witness = {'allocation_id': '56314', 'run_id': run_id, 'attempt': attempt,
               'workflow_conclusion': event['conclusion'], 'repository': repository,
               'measurement': 'durable admission unreadable; consumption unknown',
               'cpu_seconds': None, 'executions_started': None,
               'charged_cpu_seconds': CPU_CAP, 'charged_launches': LAUNCH_CAP}
    try:
        store = GitHubRefs(repository, os.environ['GH_TOKEN'])
        store.read_bootstrap()
        slots = store.read_slots()
        matches = [identity for identity in slots.values()
                   if identity['run_id'] == run_id and identity['attempt'] == attempt
                   and identity['repository'] == repository]
        if len(matches) > 1:
            raise ValueError('multiple durable admissions for one run')
        if matches:
            path = directory / 'download' / 'settlement.json'
            settlement = json.loads(path.read_text()) if path.exists() else None
            witness = reconcile(matches[0], event['conclusion'], settlement)
        else:
            witness.update(measurement='no durable admission; workload forbidden',
                           cpu_seconds=0, executions_started=0,
                           charged_cpu_seconds=0, charged_launches=0)
    except (OSError, RuntimeError, ValueError, TypeError, KeyError):
        # This witness does not unlock further admission and cannot replenish slots.
        pass
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'terminal.json').write_text(json.dumps(witness, indent=2) + '\n')
    print('Allocation terminal witness:', witness['measurement'])


if __name__ == '__main__':
    main()
