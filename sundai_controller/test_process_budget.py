"""Tiny synthetic process/thread tests only; never invokes HotSpot."""
import asyncio
import os
from pathlib import Path
import signal
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from sundai_controller import process_budget as p


class ProcessBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_q_bounds_one_two_and_eight_busy_threads(self):
        for q in (1, 2, 8):
            with self.subTest(q=q):
                scope = p.ProcessTreeScope(q)
                before_affinity = os.sched_getaffinity(0)
                expected_cpus = min(q, len(before_affinity))
                scope.start()
                try:
                    started_cpu = p.tree_snapshot()[0]
                    started_wall = time.monotonic()
                    process = await asyncio.create_subprocess_exec(
                        sys.executable, '-c',
                        'import hashlib,os,threading,time\n'
                        f'assert len(os.sched_getaffinity(0)) == {expected_cpus}\n'
                        'end=time.monotonic()+0.18\n'
                        'def busy():\n'
                        f' assert len(os.sched_getaffinity(0)) == {expected_cpus}\n'
                        ' while time.monotonic()<end: hashlib.sha256(b"x"*131072).digest()\n'
                        f'threads=[threading.Thread(target=busy) for _ in range({q})]\n'
                        '[t.start() for t in threads]\n[t.join() for t in threads]\n')
                    live_cpu = 0.0
                    while process.returncode is None:
                        cpu, children = p.tree_snapshot()
                        if children:
                            live_cpu = max(live_cpu, cpu - started_cpu)
                        await asyncio.sleep(0.01)
                    self.assertEqual(await process.wait(), 0)
                    await scope.reap()
                    used = p.tree_snapshot()[0] - started_cpu
                    wall = time.monotonic() - started_wall
                    self.assertGreater(live_cpu, 0.02)  # counts before child exit
                    self.assertGreater(used, 0.04)
                    self.assertLessEqual(used, q * wall + 1.0)  # reserve H, not p95
                    self.assertEqual(p.tree_snapshot()[1], {})
                finally:
                    await scope.reap()
                    scope.restore()
                self.assertEqual(os.sched_getaffinity(0), before_affinity)

    async def test_child_forks_grandchild_and_kill_cpu_is_counted_until_reap(self):
        # The direct child exits without waiting; subreaper must adopt the grandchild.
        scope = p.ProcessTreeScope(1)
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / 'grandchild.pid'
            scope.start()
            try:
                start = p.tree_snapshot()[0]
                child = await asyncio.create_subprocess_exec(sys.executable, '-c',
                    'import os,pathlib,time,signal\n'
                    'pid=os.fork()\n'
                    'if pid: os._exit(0)\n'
                    'os.setsid()\n'
                    'def stop(sig, frame):\n'
                    ' end=time.process_time()+0.04\n'
                    ' while time.process_time()<end: pass\n'
                    ' os._exit(0)\n'
                    'signal.signal(signal.SIGTERM, stop)\n'
                    f'pathlib.Path({str(marker)!r}).write_text(str(os.getpid()))\n'
                    'end=time.monotonic()+0.6\n'
                    'while time.monotonic()<end: pass\n')
                self.assertEqual(await child.wait(), 0)
                for _ in range(100):
                    if marker.exists():
                        break
                    await asyncio.sleep(0.01)
                grandchild = int(marker.read_text())
                await asyncio.sleep(0.04)
                before_kill, descendants = p.tree_snapshot()
                self.assertIn(grandchild, descendants)
                self.assertEqual(descendants[grandchild]['ppid'], os.getpid())
                # Substitute a graceful signal before SIGKILL. The synthetic
                # target burns CPU AFTER receiving that signal; final accounting
                # must retain it even though it exits before waitpid/reap.
                real_kill = os.kill
                killed = set()
                def delayed_kill(pid, sig):
                    if pid not in killed:
                        killed.add(pid)
                        real_kill(pid, signal.SIGTERM)
                        time.sleep(0.08)
                    real_kill(pid, sig)
                with patch.object(p.os, 'kill', side_effect=delayed_kill):
                    await scope.reap()
                final = p.tree_snapshot()[0]
                self.assertGreater(final - before_kill, 0.01)
                self.assertIn(grandchild, scope.reaped_pids)
                self.assertFalse(Path(f'/proc/{grandchild}').exists())
                self.assertEqual(p.tree_snapshot()[1], {})
                self.assertLessEqual(final - start, 1.0)  # entire tiny run < reserve
            finally:
                await scope.reap()
                scope.restore()

    async def test_preexisting_child_is_refused_and_not_killed(self):
        process = await asyncio.create_subprocess_exec(sys.executable, '-c', 'import time; time.sleep(5)')
        try:
            with self.assertRaisesRegex(RuntimeError, 'pre-existing children'):
                p.ProcessTreeScope(1).start()
            self.assertIsNone(process.returncode)
        finally:
            process.kill()
            await process.wait()

    def test_existing_runner_threads_are_confined_and_restored(self):
        ready, done = threading.Event(), threading.Event()
        tids = []
        def thread():
            tids.append(threading.get_native_id())
            ready.set()
            done.wait()
        worker = threading.Thread(target=thread)
        worker.start()
        ready.wait()
        before = os.sched_getaffinity(tids[0])
        scope = p.ProcessTreeScope(1)
        try:
            scope.start()
            self.assertEqual(os.sched_getaffinity(tids[0]), scope.mask)
            self.assertEqual(len(scope.mask), 1)
        finally:
            scope.restore()
            self.assertEqual(os.sched_getaffinity(tids[0]), before)
            done.set()
            worker.join()

    def test_stat_parses_comm_and_all_four_cpu_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '42').mkdir()
            fields = ['0'] * 50
            fields[0], fields[1], fields[19] = 'S', '7', '1234'
            for index, ticks in zip((11, 12, 13, 14), (10, 20, 30, 40)):
                fields[index] = str(ticks)
            (root / '42/stat').write_text('42 (worker (odd) name) ' + ' '.join(fields))
            with patch.object(p, 'PROC', root):
                self.assertEqual(p._stat(42), {'pid': 42, 'ppid': 7, 'start': 1234, 'ticks': 100})

    async def test_empty_proc_snapshot_still_requires_kernel_reap_confirmation(self):
        scope = p.ProcessTreeScope(1)
        with patch.object(p, 'tree_snapshot', return_value=(0, {})), patch.object(
                p.os, 'waitpid', side_effect=[(321, 0), ChildProcessError()]):
            await scope.reap()
        self.assertEqual(scope.reaped_pids, [321])

    def test_stale_children_entry_cannot_claim_a_reused_unrelated_pid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for pid, parent in ((42, 1), (43, 7)):
                directory = root / str(pid)
                directory.mkdir()
                fields = ['0'] * 50
                fields[0], fields[1], fields[11], fields[19] = 'S', str(parent), '10', '1234'
                (directory / 'stat').write_text(f'{pid} (worker) ' + ' '.join(fields))
            creator = root / '42/task/42'
            creator.mkdir(parents=True)
            (creator / 'children').write_text('43')
            with patch.object(p, 'PROC', root):
                cpu, descendants = p.tree_snapshot(42)
            self.assertEqual(descendants, {})
            self.assertEqual(cpu, 10 / p.TICKS)


if __name__ == '__main__':
    unittest.main()
