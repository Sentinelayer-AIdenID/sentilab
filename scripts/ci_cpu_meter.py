#!/usr/bin/env python3
"""Enclose the entire dedicated Docker job and all daemon-created containers.

Requires a writable host cgroup-v2 root and cgroup.kill. No CPU fallback exists.
The Docker daemon uses cgroupfs and this same parent explicitly, because ancestry
of the docker CLI alone does not include BuildKit or runtime containers.
"""
import json
import math
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

# No site hooks or repository imports before containment. Only the parent can
# attach this child; EOF on the release pipe can never start the workload.
ENTER = ('import os,sys; fd=int(sys.argv[1]); ready=os.read(fd,1); os.close(fd); '
         'sys.exit(125) if ready != b"1" else os.execvpe(sys.argv[2],sys.argv[2:],os.environ)')


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
    release_read, release_write = None, None
    baseline, own, account = None, None, None
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
        release_read, release_write = os.pipe()
        process = subprocess.Popen([sys.executable, '-I', '-S', '-c', ENTER,
                                    str(release_read), *command], env=environment,
                                   pass_fds=(release_read,))
        os.close(release_read)
        release_read = None
        if stop:
            state, code = 'cancelled', 130
        elif time.time() >= EXPIRY:
            state, code = 'expired', 1
        else:
            (group / 'host' / 'cgroup.procs').write_text(str(process.pid))
            # Recheck after the potentially blocking attach, before release.
            if stop:
                state, code = 'cancelled', 130
            elif time.time() >= EXPIRY:
                state, code = 'expired', 1
            else:
                os.write(release_write, b'1')
                state, code = monitor(group, process, account, cancelled=lambda: bool(stop),
                                      violated=lambda: bool(ledger.summary()['direct_call_violations']))
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        print('CI allocation stopped:', str(exc), file=sys.stderr)
        state, code = 'inconclusive', 1
    finally:
        for fd in (release_read, release_write):
            if fd is not None:
                os.close(fd)
        errors = []
        helper_reaped, kill_within_reserve = process is None, group is None
        # Cancel the retained helper BEFORE draining. It cannot later attach
        # itself or release another workload, even when wait/kill fails.
        if process is not None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            except OSError as exc:
                errors.append(str(exc))
        if group is not None:
            try:
                kill_group(group)
                kill_within_reserve = True
            except (OSError, RuntimeError, ValueError, KeyError) as exc:
                errors.append(str(exc))
        if process is not None:
            try:
                process.wait(timeout=5)
                helper_reaped = True
            except (OSError, subprocess.TimeoutExpired) as exc:
                errors.append(str(exc))
        if broker is not None:
            broker.shutdown()
            broker.server_close()
        final_populated = None
        if group is not None:
            try:
                final_populated = populated(group)
                if final_populated:
                    errors.append('cgroup still populated after cleanup')
                # A late/failed kill must not discard an available CPU sample.
                group_end, own_end = read_cpu(group), supervisor_cpu()
                if (account is None or not all(math.isfinite(v) for v in (group_end, own_end))
                        or group_end < account.previous[0] or own_end < account.previous[1]):
                    raise RuntimeError('final CPU counter regressed')
                total = group_end - baseline + own_end - own
                final_cpu = {'cpu_seconds': total, 'measurement': 'cgroup-v2 plus supervisor rusage',
                             'cgroup_cpu_seconds': group_end - baseline,
                             'supervisor_cpu_seconds': own_end - own,
                             'charged_cpu_seconds': total, 'stop_reserve_seconds': 30,
                             'cgroup': str(group), 'cpu_max': '100000 100000',
                             'final_populated': final_populated}
                if total > CPU_CAP:
                    state, code = 'cpu_limit_violated', 1
            except (OSError, RuntimeError, ValueError, KeyError) as exc:
                errors.append(str(exc))
        final_cpu.update(final_populated=final_populated, helper_reaped=helper_reaped,
                         cleanup_complete=helper_reaped and final_populated is False,
                         kill_within_reserve=kill_within_reserve)
        if ledger.summary()['direct_call_violations']:
            state, code = 'launch_violation', 1
        if errors or state == 'inconclusive':
            if errors:
                print('CPU settlement inconclusive:', '; '.join(errors), file=sys.stderr)
            final_cpu.update(cleanup_errors=errors,
                             charged_cpu_seconds=max(CPU_CAP, final_cpu['charged_cpu_seconds']))
            state, code = 'inconclusive', 1
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
    group = root / ('ci-allocation-' + admission['identity']['run_id'])
    sample, final_populated, errors = None, None, []
    if group.exists():
        try:
            kill_group(group)
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            errors.append(str(exc))
        try:
            final_populated = populated(group)
            sample = read_cpu(group)
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            errors.append(str(exc))
        # Append cleanup evidence even for a terminal, conservatively charged
        # ledger. A finished event is not evidence that all descendants stopped.
        with ledger._locked() as (stream, events):
            ledger._append(stream, events, 'cleanup', final_populated=final_populated,
                           cleanup_complete=final_populated is False,
                           last_cgroup_cpu_seconds=sample, errors=errors)
    ledger.finish('interrupted', {'cpu_seconds': None, 'last_cgroup_cpu_seconds': sample,
                                  'measurement': 'supervisor lost; total unknown',
                                  'charged_cpu_seconds': CPU_CAP, 'final_populated': final_populated,
                                  'cleanup_complete': final_populated is False, 'cleanup_errors': errors})
    export(ledger, directory, admission)
    if errors or final_populated:
        raise RuntimeError('cgroup recovery incomplete or outside reserved kill overhead')


def main():
    directory = Path(sys.argv[2]).resolve()
    if sys.argv[1] == 'recover':
        recover(directory)
        return 0
    admission = json.loads((directory / 'admission.json').read_text())
    return run(directory, admission, sys.argv[3:])


if __name__ == '__main__':
    raise SystemExit(main())
