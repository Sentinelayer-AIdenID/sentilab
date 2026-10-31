"""Linux process-tree accounting and CPU affinity for the dedicated headroom runner.

A subreaper owns orphaned grandchildren after a worker dies. /proc stat includes
both process threads and CPU of children already waited for; walking parents
before children avoids counting a reaped child twice. Final accounting happens
only after all descendants have been waited for, including the kill/reap interval.
"""
from __future__ import annotations

import asyncio
import ctypes
import os
from pathlib import Path
import signal

PROC = Path('/proc')
TICKS = os.sysconf('SC_CLK_TCK')


def _stat(pid):
    try:
        # comm can contain spaces and parentheses. Fields after its final ')'
        # start at field 3 (state); utime/stime/cutime/cstime are fields 14..17.
        fields = (PROC / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()
    except (FileNotFoundError, ProcessLookupError):
        return None
    return {'pid': pid, 'ppid': int(fields[1]), 'start': int(fields[19]),
            'ticks': sum(int(fields[i]) for i in (11, 12, 13, 14))}


def tree_snapshot(pid=None):
    """Return cumulative CPU and live/zombie descendants, including all threads."""
    root = os.getpid() if pid is None else pid
    pending, records = [(root, None)], {}
    while pending:
        current, parent = pending.pop(0)
        if current in records:
            continue
        stat = _stat(current)
        if stat is None or (parent is not None and stat['ppid'] != parent):
            # A stale children entry must not claim a reused PID. Reparented
            # descendants are discovered on the next snapshot under the subreaper.
            continue
        records[current] = stat
        # Linux children lists are per-thread, so inspect every creator thread.
        for path in (PROC / str(current) / 'task').glob('*/children'):
            try:
                pending.extend((int(child), current) for child in path.read_text().split())
            except (FileNotFoundError, ProcessLookupError):
                pass
    if root not in records:
        raise RuntimeError('cannot meter runner /proc stat')
    return sum(row['ticks'] for row in records.values()) / TICKS, {
        child: row for child, row in records.items() if child != root}


class ProcessTreeScope:
    """Exclusive runner scope: inherited Q-CPU mask, subreaper, confirmed cleanup.

    Refuse pre-existing children: this scope must never kill/reap unrelated work.
    Asyncio owns its direct worker until oracle.aclose() completes. Only then may
    reap() wait for adopted descendants. No success is returned before reap().
    """
    def __init__(self, rate):
        if type(rate) is not int or rate not in (1, 2, 8):
            raise ValueError('CPU rate Q must be 1, 2 or 8')
        self.rate = rate
        self.affinities = {}
        self.libc = ctypes.CDLL(None, use_errno=True)
        self.old_subreaper = ctypes.c_int()
        self.reaped_pids = []

    def _prctl(self, option, value):
        if self.libc.prctl(option, value, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), 'headroom requires Linux subreaper support')

    def start(self):
        if tree_snapshot()[1]:
            raise RuntimeError('headroom CPU scope requires no pre-existing children')
        available = os.sched_getaffinity(0)
        if len(available) < self.rate:
            raise RuntimeError('fewer available CPUs than declared Q')
        self.mask = set(sorted(available)[:self.rate])
        self._prctl(37, ctypes.byref(self.old_subreaper))  # PR_GET_CHILD_SUBREAPER
        self._prctl(36, 1)  # PR_SET_CHILD_SUBREAPER
        try:
            # Existing native-library threads also need confinement. New threads
            # and all worker descendants inherit the restricted mask.
            seen = set()
            while True:
                tids = {int(path.name) for path in (PROC / 'self/task').iterdir()}
                if tids <= seen:
                    break
                for tid in tids - seen:
                    try:
                        self.affinities[tid] = os.sched_getaffinity(tid)
                        os.sched_setaffinity(tid, self.mask)
                    except ProcessLookupError:
                        pass
                seen |= tids
        except BaseException:
            self.restore()
            raise

    async def reap(self):
        """Kill survivors and keep metering until every descendant is reaped."""
        while True:
            _, descendants = tree_snapshot()
            if not descendants:
                # Confirm with the kernel: a child may have been adopted while
                # /proc was being traversed. No children means no descendants.
                try:
                    reaped, _ = os.waitpid(-1, os.WNOHANG)
                except ChildProcessError:
                    return
                if reaped:
                    self.reaped_pids.append(reaped)
                await asyncio.sleep(0.001)
                continue
            for pid, row in descendants.items():
                current = _stat(pid)
                if current is None or current['start'] != row['start']:
                    continue
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                if current['ppid'] == os.getpid():
                    try:
                        reaped, _ = os.waitpid(pid, os.WNOHANG)
                    except ChildProcessError:
                        continue
                    if reaped:
                        self.reaped_pids.append(reaped)
            # No deadline escapes cleanup: outstanding children keep the ledger
            # reservation active and their CPU charged until reaping is confirmed.
            await asyncio.sleep(0.001)

    def restore(self):
        for tid, affinity in self.affinities.items():
            try:
                os.sched_setaffinity(tid, affinity)
            except ProcessLookupError:
                pass
        self._prctl(36, self.old_subreaper.value)
