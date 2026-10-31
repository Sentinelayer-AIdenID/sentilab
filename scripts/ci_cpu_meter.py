#!/usr/bin/env python3
"""Enclose the entire dedicated Docker job and all daemon-created containers.

Requires a writable host cgroup-v2 root and cgroup.kill. No CPU fallback exists.
The Docker daemon uses cgroupfs and this same parent explicitly, because ancestry
of the docker CLI alone does not include BuildKit or runtime containers.
"""
import json
import os
import re
import resource
import signal
import subprocess
import sys
import time
from pathlib import Path

from scripts.ci_allocation import (
    CPU_CAP,
    EXPIRY,
    CPUAccount,
    Identity,
    Ledger,
    read_cpu,
)
from scripts.ci_hotspot_gate import serve


def supervisor_cpu():
    value = resource.getrusage(resource.RUSAGE_SELF)
    return value.ru_utime + value.ru_stime


def populated(group):
    fields = dict(line.split() for line in (group / 'cgroup.events').read_text().splitlines())
    return fields['populated'] == '1'


def kill_group(group, *, clock=time.monotonic, sleep=time.sleep):
    deadline = clock() + 5
    (group / 'cgroup.kill').write_text('1')
    while True:
        active = populated(group)
        if clock() >= deadline:
            raise RuntimeError('cgroup failed to drain within reserved kill overhead')
        if not active:
            return
        sleep(.01)


def create_group(name, root=Path('/sys/fs/cgroup')):
    if 'cpu' not in (root / 'cgroup.controllers').read_text().split():
        raise RuntimeError('cgroup v2 CPU controller unavailable')
    (root / 'cgroup.subtree_control').write_text('+cpu')
    group = root / name
    group.mkdir()  # exclusive: never reset a prior group or counter
    (group / 'cgroup.subtree_control').write_text('+cpu')
    (group / 'cpu.max').write_text('100000 100000')
    if not (group / 'cgroup.kill').is_file():
        raise RuntimeError('cgroup.kill unavailable')
    # v2's no-internal-process rule: tasks go in a leaf; Docker creates siblings.
    (group / 'host').mkdir()
    read_cpu(group)
    return group


def export(ledger, directory, admission):
    target = directory / 'settlement.json'
    temporary = directory / 'settlement.tmp'
    temporary.write_text(json.dumps(dict(ledger.summary(), admission=admission), indent=2) + '\n')
    temporary.replace(target)


def monitor(group, process, account, *, cancelled, violated=lambda: False, cpu=read_cpu,
            own_cpu=supervisor_cpu, clock=time.monotonic, sleep=time.sleep, wall_clock=time.time):
    """Fake clocks/counters exercise the same loop used around the Docker job."""
    while True:
        if cancelled():
            return 'cancelled', 130
        if violated():
            return 'launch_violation', 1
        if wall_clock() >= EXPIRY:
            return 'expired', 1
        if account.observe(cpu(group), own_cpu(), clock()):
            return 'cpu_exhausted', 1
        code = process.poll()
        if code is not None:
            return ('success' if code == 0 else 'failure'), code
        sleep(.05)


def run(directory, admission, command):
    identity = Identity(**admission['identity'])
    if admission.get('state') != 'admitted' or identity.attempt != '1':
        raise RuntimeError('no valid admission')
    if (admission.get('launch_reservation') != 100
            or admission.get('cpu_reservation_seconds') != CPU_CAP
            or admission.get('allocation_id') != '56314'):
        raise RuntimeError('invalid admission bounds')
    mode = admission.get('mode', 'enforced')
    if mode == 'bootstrap':
        base = admission.get('base_sha', '')
        if (not isinstance(base, str) or not re.fullmatch(r'[a-f0-9]{40}', base)
                or admission.get('reason') != 'controller absent at base ' + base
                or admission.get('slot') is not None):
            raise RuntimeError('invalid base-controller bootstrap')
    elif (mode != 'enforced' or type(admission.get('slot')) is not int
          or not 1 <= admission['slot'] <= 200):
        raise RuntimeError('invalid admission bounds')
    ledger = Ledger(directory / 'events.jsonl', identity)
    # Reentry refuses even if the first process crashed before any solver launch.
    if (directory / 'meter-started').exists():
        raise RuntimeError('meter already started; refusing budget reset')
    (directory / 'meter-started').touch(exist_ok=False)
    export(ledger, directory, admission)
    group, broker, process = None, None, None
    state, code = 'inconclusive', 1
    final_cpu = {'cpu_seconds': None, 'measurement': 'unavailable',
                 'charged_cpu_seconds': CPU_CAP}
    stop = []
    old_handlers = {sig: signal.signal(sig, lambda *_: stop.append(True))
                    for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        if time.time() >= EXPIRY:
            raise RuntimeError('allocation expired before workload start')
        group = create_group('ci-allocation-' + identity.run_id)
        baseline, own = read_cpu(group), supervisor_cpu()
        account = CPUAccount(baseline, own, time.monotonic())
        broker = serve(ledger)
        environment = dict(os.environ, CI_ALLOCATION='1', CI_CGROUP=str(group),
                           CI_RUN_ID=identity.run_id, BUILD_SHA=identity.build_sha)
        # Authentication belongs to admission only, never Docker or child code.
        environment.pop('GH_TOKEN', None)
        environment.pop('GITHUB_TOKEN', None)
        process = subprocess.Popen([sys.executable, '-m', 'scripts.ci_cpu_meter',
                                    'enter', str(group), *command], env=environment)
        state, code = monitor(group, process, account, cancelled=lambda: bool(stop),
                              violated=lambda: bool(ledger.summary()['direct_call_violations']))
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        print('CI allocation stopped:', str(exc), file=sys.stderr)
        state, code = 'inconclusive', 1
    finally:
        if group is not None:
            try:
                kill_group(group)
                if process is not None:
                    process.wait(timeout=5)
                if broker is not None:
                    broker.shutdown()
                    broker.server_close()
                    broker = None
                group_end, own_end = read_cpu(group), supervisor_cpu()
                if group_end < account.previous[0] or own_end < account.previous[1]:
                    raise RuntimeError('final CPU counter regressed')
                total = group_end - baseline + own_end - own
                final_cpu = {'cpu_seconds': total, 'measurement': 'cgroup-v2 plus supervisor rusage',
                             'cgroup_cpu_seconds': group_end - baseline,
                             'supervisor_cpu_seconds': own_end - own,
                             'charged_cpu_seconds': total, 'stop_reserve_seconds': 30,
                             'cgroup': str(group), 'cpu_max': '100000 100000',
                             'final_populated': False}
                if total > CPU_CAP:
                    state, code = 'cpu_limit_violated', 1
            except (OSError, RuntimeError, ValueError, KeyError, subprocess.TimeoutExpired, UnboundLocalError) as exc:
                print('CPU settlement inconclusive:', str(exc), file=sys.stderr)
                state, code = 'inconclusive', 1
        if broker is not None:
            broker.shutdown()
            broker.server_close()
        if ledger.summary()['direct_call_violations']:
            state, code = 'launch_violation', 1
        ledger.finish(state, final_cpu)
        export(ledger, directory, admission)
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)
    print(json.dumps({'state': state, 'launches': ledger.summary()['launches_reserved'], 'cpu': final_cpu}))
    return code


def recover(directory, *, root=Path('/sys/fs/cgroup')):
    """Actions always() fallback after supervisor kill; never fabricates a sample."""
    admission = json.loads((directory / 'admission.json').read_text())
    if admission.get('state') != 'admitted':
        return
    ledger = Ledger(directory / 'events.jsonl', Identity(**admission['identity']))
    if ledger.summary()['state'] != 'in_progress':
        export(ledger, directory, admission)
        return
    group = root / ('ci-allocation-' + admission['identity']['run_id'])
    sample = None
    if group.exists():
        kill_group(group)
        sample = read_cpu(group)
    ledger.finish('interrupted', {'cpu_seconds': None, 'last_cgroup_cpu_seconds': sample,
                                  'measurement': 'supervisor lost; total unknown',
                                  'charged_cpu_seconds': CPU_CAP})
    export(ledger, directory, admission)


def main():
    directory = Path(sys.argv[2]).resolve()
    if sys.argv[1] == 'enter':
        (directory / 'host' / 'cgroup.procs').write_text(str(os.getpid()))
        os.execvpe(sys.argv[3], sys.argv[3:], os.environ)
    if sys.argv[1] == 'recover':
        recover(directory)
        return 0
    admission = json.loads((directory / 'admission.json').read_text())
    return run(directory, admission, sys.argv[3:])


if __name__ == '__main__':
    raise SystemExit(main())
