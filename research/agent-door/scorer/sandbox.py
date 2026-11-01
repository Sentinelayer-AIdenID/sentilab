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
CLEANUP_TIMEOUT_S = 2


def subreaper():
    if ctypes.CDLL(None).prctl(36, 1, 0, 0, 0) != 0:
        raise RuntimeError('subreaper unavailable')


def parent_death(signum, parent):
    if ctypes.CDLL(None).prctl(1, signum, 0, 0, 0) != 0:
        raise RuntimeError('parent death signal unavailable')
    if os.getppid() != parent or parent == 1:
        raise RuntimeError('parent disappeared')


def isolate():
    libc = ctypes.CDLL(None, use_errno=True)
    subreaper()
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
            except (FileNotFoundError, ProcessLookupError):
                continue
    owned = {os.getpid()}
    while True:
        more = {pid for pid, row in rows.items() if row[0] in owned}
        if more <= owned:
            break
        owned |= more
    return {pid: rows[pid] for pid in owned if pid != os.getpid()}


def kill_children():
    """A failed global scan must not disable cleanup of adopted children."""
    try:
        children = descendants()
    except Exception:
        try:
            children = [int(pid) for pid in Path(f'/proc/self/task/{os.getpid()}/children').read_text().split()]
        except (OSError, ValueError):
            children = []
    for child in children:
        try:
            os.kill(child, signal.SIGKILL)
        except OSError:
            pass


def cleanup_children():
    deadline = time.monotonic() + CLEANUP_TIMEOUT_S
    while time.monotonic() < deadline:
        kill_children()
        try:
            child, _, _ = os.wait4(-1, os.WNOHANG)
        except ChildProcessError:
            return True
        if not child:
            time.sleep(0.01)
    return False


def supervise(engine, spec, directory, wall_timeout, registration=None):
    isolate()  # fails before any generator/engine if containment is unavailable
    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    parent_death(signal.SIGTERM, os.getppid())
    start = time.monotonic()
    worker_pid = os.getpid()
    pid = os.fork()
    if pid == 0:
        try:
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            parent_death(signal.SIGKILL, worker_pid)
            os.setsid()
            if registration is not None:
                report, go = registration
                os.write(report, f'{os.getpid()}\n'.encode())
                os.close(report)
                if os.read(go, 1) != b'1':
                    os._exit(125)
                os.close(go)
            resource.setrlimit(resource.RLIMIT_CPU, (CPU_LIMIT_S, CPU_LIMIT_S))
            from thermal import check_config, stage
            from sundai_hotspot import slab049
            from sundai_hotspot.reference_validation import SOLVER_ENVIRONMENT
            hashes = stage(spec, directory)
            check_config(directory, spec['hotspot_config_sha256'])
            (directory / 'inputs.json').write_text(json.dumps(hashes))
            os.chdir(directory)
            with open('stdout.txt', 'wb') as out, open('stderr.txt', 'wb') as err:
                os.dup2(out.fileno(), 1)
                os.dup2(err.fileno(), 2)
            os.execve(engine, slab049.tap_argv(engine, 64), SOLVER_ENVIRONMENT)
        except BaseException:
            os._exit(125)
    if registration is not None:
        report, go = registration
        os.close(report)
        # Keep the engine PID unreaped until the guardian has opened its pidfd.
        if os.read(go, 1) != b'1':
            raise RuntimeError('owner disappeared before registration')
        os.close(go)
    leader_status = None
    reaped_cpu = 0.0
    killed = set()
    reason = None
    cleanup_deadline = None
    cleanup_complete = False
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
            if cleanup_deadline is None:
                cleanup_deadline = time.monotonic() + CLEANUP_TIMEOUT_S
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
            cleanup_complete = True
            break
        if cleanup_deadline is not None and time.monotonic() >= cleanup_deadline:
            reason = reason or 'oracle_error'
            break
        time.sleep(0.01)
    result = {'engine_pid': pid, 'cleanup_pids': sorted(killed), 'returncode': leader_status,
              'reason': reason or ('oracle_error' if leader_status else None),
              'usage_complete': cleanup_complete, 'cleanup_complete': cleanup_complete}
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


def guard(engine, spec, directory, wall_timeout):
    """Own one worker tree outside its CPU limit, including hard-death orphans."""
    subreaper()
    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    parent_death(signal.SIGTERM, os.getppid())
    report, send = os.pipe2(os.O_CLOEXEC)
    receive, go = os.pipe2(os.O_CLOEXEC)
    owner_pid = os.getpid()
    worker = os.fork()
    if worker == 0:
        os.close(report)
        os.close(go)
        try:
            parent_death(signal.SIGKILL, owner_pid)
            result = supervise(engine, spec, directory, wall_timeout, (send, receive))
        except BaseException:
            result = {'reason': 'oracle_error', 'usage_complete': False,
                      'cleanup_complete': cleanup_children()}
        try:
            (directory / 'worker-result.json').write_text(json.dumps(result, allow_nan=False))
        finally:
            os._exit(0)
    os.close(send)
    os.close(receive)
    os.set_blocking(report, False)
    deadline = time.monotonic() + wall_timeout
    cleanup_deadline = None
    worker_status = None
    engine_pid = engine_handle = None
    message = b''
    failure = None
    cleanup_complete = False
    killed = set()
    reaped = set()
    try:
        while True:
            if engine_handle is None and failure is None:
                try:
                    message += os.read(report, 64)
                    if b'\n' in message:
                        engine_pid = int(message)
                        if engine_pid in reaped:
                            raise ValueError('engine exited before registration')
                        engine_handle = os.pidfd_open(engine_pid)
                        os.write(go, b'11')  # Release engine execution and worker reaping only after ownership.
                except BlockingIOError:
                    pass
                except (OSError, ValueError):
                    failure = 'oracle_error'
            if stopping or time.monotonic() >= deadline:
                failure = failure or ('interrupted' if stopping else 'timeout')
            if failure or worker_status is not None:
                if cleanup_deadline is None:
                    cleanup_deadline = time.monotonic() + CLEANUP_TIMEOUT_S
                if worker_status is None:  # Its PID is still retained, independent of /proc availability.
                    os.kill(worker, signal.SIGKILL)
                if engine_handle is not None:
                    try:
                        signal.pidfd_send_signal(engine_handle, signal.SIGKILL)
                        killed.add(engine_pid)
                    except ProcessLookupError:
                        pass
                kill_children()
            no_children = False
            while True:
                try:
                    child, status, _ = os.wait4(-1, os.WNOHANG)
                except ChildProcessError:
                    no_children = True
                    break
                if not child:
                    break
                reaped.add(child)
                if child == worker:
                    worker_status = os.waitstatus_to_exitcode(status)
                    if worker_status != 0:
                        failure = failure or 'oracle_error'
                else:
                    killed.add(child)
            if no_children:
                cleanup_complete = True
                break
            if cleanup_deadline is not None and time.monotonic() >= cleanup_deadline:
                failure = failure or 'oracle_error'
                break
            time.sleep(0.01)
    except BaseException:
        failure = 'oracle_error'
        if worker_status is None:
            try:
                os.kill(worker, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if engine_handle is not None:
            try:
                signal.pidfd_send_signal(engine_handle, signal.SIGKILL)
            except OSError:
                pass
        cleanup_complete = cleanup_children()
    finally:
        for fd in (report, go, engine_handle):
            if fd is not None:
                os.close(fd)
    try:
        result = json.loads((directory / 'worker-result.json').read_bytes())
    except (OSError, ValueError):
        result = {'reason': 'oracle_error', 'usage_complete': False}
    result['usage_complete'] = bool(result.get('usage_complete') and not failure and cleanup_complete
                                    and worker_status == 0)
    result['cleanup_complete'] = cleanup_complete
    if failure:
        result['reason'] = failure
    result.update(worker_pid=worker, engine_pid=engine_pid,
                  cleanup_pids=sorted(set(result.get('cleanup_pids', [])) | killed))
    return result


def main():
    engine, directory, timeout = sys.argv[1:]
    directory = Path(directory)
    result = guard(engine, json.load(sys.stdin), directory, float(timeout))
    (directory / 'result.json').write_text(json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    main()
