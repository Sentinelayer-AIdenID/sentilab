"""Linux-only solve supervisor. Each invocation owns a fresh subreaper tree."""
from __future__ import annotations

import ctypes
import errno
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
CPU_LIMIT_S = 10
WALL_TIMEOUT_S = 30


def isolate():
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise RuntimeError('subreaper unavailable')
    if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
        raise RuntimeError('no_new_privs unavailable')
    seccomp = ctypes.CDLL('libseccomp.so.2', use_errno=True)
    seccomp.seccomp_init.argtypes = [ctypes.c_uint32]
    seccomp.seccomp_init.restype = ctypes.c_void_p
    seccomp.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    seccomp.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    seccomp.seccomp_load.argtypes = [ctypes.c_void_p]
    seccomp.seccomp_release.argtypes = [ctypes.c_void_p]
    context = seccomp.seccomp_init(0x7fff0000)  # allow except network creation/access and io_uring bypass
    if not context:
        raise RuntimeError('seccomp unavailable')
    try:
        for name in ('socket', 'socketpair', 'connect', 'bind', 'listen', 'accept', 'accept4',
                     'sendto', 'sendmsg', 'sendmmsg', 'recvfrom', 'recvmsg', 'recvmmsg', 'io_uring_setup'):
            number = seccomp.seccomp_syscall_resolve_name(name.encode())
            if number >= 0 and seccomp.seccomp_rule_add(context, 0x50000 | errno.EPERM, number, 0) != 0:
                raise RuntimeError('network filter rule failed')
        if seccomp.seccomp_load(context) != 0:
            raise RuntimeError('network filter failed')
    finally:
        seccomp.seccomp_release(context)
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_LIMIT_S, CPU_LIMIT_S))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024,) * 2)


def descendants():
    """PPID closure catches setsid descendants; subreaping retains orphans until we reap them."""
    rows = {}
    for entry in Path('/proc').iterdir():
        if entry.name.isdigit():
            try:
                fields = (entry / 'stat').read_text().rsplit(')', 1)[1].split()
                rows[int(entry.name)] = (int(fields[1]), int(fields[3]), fields[19],
                                        sum(int(fields[i]) for i in (11, 12, 13, 14)))
            except (OSError, ValueError, IndexError):
                continue
    owned = {os.getpid()}
    while True:
        more = {pid for pid, row in rows.items() if row[0] in owned}
        if more <= owned:
            break
        owned |= more
    return {pid: rows[pid] for pid in owned if pid != os.getpid()}


def supervise(engine, spec, directory, wall_timeout):
    isolate()  # fails before any generator/engine if containment is unavailable
    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    libc = ctypes.CDLL(None)
    parent = os.getppid()
    if libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0:  # clean up on service death too
        raise RuntimeError('parent death signal unavailable')
    if os.getppid() != parent or parent == 1:
        raise RuntimeError('service disappeared')
    start = time.monotonic()
    pid = os.fork()
    if pid == 0:
        try:
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            os.setsid()
            resource.setrlimit(resource.RLIMIT_CPU, (CPU_LIMIT_S, CPU_LIMIT_S))
            from thermal import stage
            from sundai_hotspot import slab049
            from sundai_hotspot.reference_validation import SOLVER_ENVIRONMENT
            hashes = stage(spec, directory)
            (directory / 'inputs.json').write_text(json.dumps(hashes))
            os.chdir(directory)
            with open('stdout.txt', 'wb') as out, open('stderr.txt', 'wb') as err:
                os.dup2(out.fileno(), 1)
                os.dup2(err.fileno(), 2)
            os.execve(engine, slab049.tap_argv(engine, 64), SOLVER_ENVIRONMENT)
        except BaseException:
            os._exit(125)
    leader_status = None
    reaped_cpu = 0.0
    killed = set()
    reason = None
    hz = os.sysconf('SC_CLK_TCK')
    while True:
        tree = descendants()
        own = resource.getrusage(resource.RUSAGE_SELF)
        live_cpu = sum(row[3] / hz for row in tree.values())
        if reason is None:
            if stopping:
                reason = 'interrupted'
            elif time.monotonic() - start >= wall_timeout or live_cpu + reaped_cpu + own.ru_utime + own.ru_stime >= CPU_LIMIT_S:
                reason = 'timeout'
        leader_exited = (leader_status is None and os.waitid(
            os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None)
        if reason or leader_status is not None or leader_exited:
            # Kill the leader's session/group, then every owned descendant including new sessions.
            if leader_status is None:  # Never signal a group after releasing its leader PID.
                try:
                    os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            for child in tree:
                try:
                    os.kill(child, signal.SIGKILL)
                    killed.add(child)
                except ProcessLookupError:
                    pass
        no_children = False
        while True:
            try:
                child, status, usage = os.wait4(-1, os.WNOHANG)
            except ChildProcessError:
                no_children = True
                break
            if not child:
                break
            reaped_cpu += usage.ru_utime + usage.ru_stime
            if child == pid:
                leader_status = os.waitstatus_to_exitcode(status)
                if leader_status in (-signal.SIGKILL, -signal.SIGXCPU) and reason is None:
                    reason = 'timeout'
        if no_children:
            break
        time.sleep(0.01)
    result = {'engine_pid': pid, 'cleanup_pids': sorted(killed), 'returncode': leader_status,
              'reason': reason or ('oracle_error' if leader_status else None)}
    hashes = directory / 'inputs.json'
    result['input_sha256'] = json.loads(hashes.read_text()) if hashes.exists() else {}
    from thermal import read_score, sha256
    result['output_sha256'] = {name: sha256(directory / name) for name in ('sample.steady', 'sample.grid.steady')
                               if (directory / name).is_file()}
    if result['reason'] is None:
        try:
            result['score'] = read_score(directory)
        except (ValueError, KeyError, OSError):
            result['reason'] = 'oracle_error'
    return result


if __name__ == '__main__':
    engine, directory, timeout = sys.argv[1:]
    directory = Path(directory)
    try:
        result = supervise(engine, json.load(sys.stdin), directory, float(timeout))
    except BaseException:
        # Never echo exception text, solver arguments, or request contents.
        # Keep the same cleanup guarantee for supervisor failures as for normal timeouts.
        while True:
            for child in descendants():
                try:
                    os.kill(child, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            try:
                child, _, _ = os.wait4(-1, os.WNOHANG)
            except ChildProcessError:
                break
            if not child:
                time.sleep(0.01)
        result = {'reason': 'oracle_error'}
    (directory / 'result.json').write_text(json.dumps(result, allow_nan=False))
