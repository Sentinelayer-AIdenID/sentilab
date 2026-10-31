"""Worker cleanup must not signal a numeric group after its owner is reaped."""
import asyncio
from pathlib import Path
import os
import select
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from sentilab_core.execution import recorded_call
from sentilab_core.operations import Context


class WorkerIdentityTests(unittest.IsolatedAsyncioTestCase):
    async def test_completed_workers_never_signal_a_reusable_process_group(self):
        with tempfile.TemporaryDirectory() as directory:
            context = Context(Path(directory), {})
            # Real workers exit and are reaped by communicate(). Their numeric
            # PID/PGID no longer proves ownership, regardless of result validity.
            with patch("sentilab_core.execution.os.killpg") as signal_group:
                result = await recorded_call(context, "chiplet.build", {"fixture": "plate"})
                self.assertEqual(result["fixture"], "plate")
                signal_group.assert_not_called()
            with patch("sentilab_core.execution.os.killpg") as signal_group:
                with self.assertRaises(ValueError):
                    await recorded_call(context, "chiplet.build", {"fixture": "unknown"})
                signal_group.assert_not_called()


class WholeJobCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_pidfd_setup_failure_reaps_worker_before_dispatch(self):
        real_popen = subprocess.Popen
        spawned = []

        def start(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            spawned.append(process)
            return process

        with tempfile.TemporaryDirectory() as directory, \
                patch("subprocess.Popen", side_effect=start), \
                patch("os.pidfd_open", side_effect=OSError("pidfd unavailable")):
            with self.assertRaises(OSError):
                await recorded_call(Context(Path(directory), {}), "chiplet.build", {"fixture": "plate"})
            self.assertEqual(len(spawned), 1)
            self.assertFalse(Path(f"/proc/{spawned[0].pid}").exists())
            self.assertTrue(spawned[0].stdin.closed)
            self.assertTrue(spawned[0].stdout.closed)

    async def exercise(self, *, closed_pipe=False, failure=False, cancel=False, delayed_reap=False):
        # Every descendant is finite, and the test keeps a pidfd for its own
        # teardown. No real broadcast signal, or unrelated victim, is needed.
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "child"
            go = Path(directory) / "go"
            natural_exit = Path(directory) / "natural-exit"
            code = "\n".join([
                "import json, os, sys, time",
                "json.load(sys.stdin)",
                "def await_pin():",
                "    deadline = time.monotonic() + 3",
                f"    while not os.path.exists({str(go)!r}):",
                "        if time.monotonic() >= deadline:",
                f"            open({str(natural_exit)!r}, 'w').close()",
                "            os._exit(3)",
                "        time.sleep(0.001)",
                "child = os.fork()",
                "if child == 0:",
                "    os.close(0)",
                f"    with open({str(marker)!r}, 'w') as ready: ready.write(str(os.getpid()))",
                "    await_pin()",
                "    os.close(1)" if closed_pipe else "    pass",
                "    time.sleep(4)",
                f"    open({str(natural_exit)!r}, 'w').close()",
                "    os._exit(0)",
                "await_pin()",
                "print('not-json', flush=True)" if failure else
                "print(json.dumps({'result': {'fixture': 'plate'}}), flush=True)",
                "os._exit(0)",
            ])
            real_popen = subprocess.Popen
            spawned = []

            def start(command, *args, **kwargs):
                if list(command[:3]) == [sys.executable, "-m", "sentilab_core.execution"]:
                    command = [sys.executable, "-c", code]
                process = real_popen(command, *args, **kwargs)
                spawned.append(process)
                return process

            # Hold the *cached* callback after CPython has done waitpid. This
            # is the actual reap-before-returncode window from the review.
            transport = asyncio.unix_events._UnixSubprocessTransport
            process_exited = transport._process_exited
            reaped = []

            def delayed_callback(instance, returncode):
                reaped.append(instance.get_pid())
                asyncio.get_running_loop().call_later(
                    0.7, process_exited, instance, returncode)

            callback = delayed_callback if delayed_reap else process_exited
            child_fd = None
            call = None
            real_signal = signal.pidfd_send_signal

            def signal_member(fd, signum):
                real_signal(fd, signum)
                if cancel and signum == signal.SIGSTOP:
                    # Cancellation can recur while the shielded cleanup yields.
                    asyncio.get_running_loop().call_soon(call.cancel)
            with patch("subprocess.Popen", side_effect=start), \
                    patch.object(transport, "_process_exited", callback), \
                    patch("os.killpg") as broadcast, patch("os.kill") as numeric_signal, \
                    patch("signal.pidfd_send_signal", side_effect=signal_member) as pinned_signal:
                try:
                    call = asyncio.create_task(recorded_call(
                        Context(Path(directory), {}), "chiplet.build", {"fixture": "plate"},
                        timeout=0.35 if not closed_pipe else 3))
                    async with asyncio.timeout(3):
                        while not marker.exists() or not marker.read_text():
                            await asyncio.sleep(0.005)
                    child = int(marker.read_text())
                    child_fd = os.pidfd_open(child)
                    # Both fixture processes wait for this release. In
                    # particular, closed-pipe completion cannot race the pin.
                    self.assertEqual(select.select([child_fd], [], [], 0)[0], [],
                                     "descendant must be alive before release")
                    go.touch()
                    if cancel:
                        # A zombie is deliberately still owned by the fixed
                        # implementation; the old watcher has already reaped it.
                        async with asyncio.timeout(3):
                            while True:
                                stat = Path(f"/proc/{spawned[0].pid}/stat")
                                if not stat.exists() or stat.read_text().rsplit(")", 1)[1].split()[0] == "Z":
                                    break
                                await asyncio.sleep(0.005)
                        await asyncio.sleep(0.02)
                        call.cancel()
                    if cancel:
                        with self.assertRaises(asyncio.CancelledError):
                            await call
                    elif not closed_pipe:
                        with self.assertRaises(TimeoutError):
                            await call
                    elif failure:
                        with self.assertRaises(ValueError):
                            await call
                    else:
                        self.assertEqual(await call, {"fixture": "plate"})
                    if delayed_reap:
                        # Any broadcast here is a signal to an unowned numeric
                        # PGID. Model that number as recycled; never signal it.
                        self.assertTrue(not reaped or spawned[0].pid in reaped)
                    broadcast.assert_not_called()
                    numeric_signal.assert_not_called()
                    self.assertFalse(natural_exit.exists(), "descendant exited naturally before cleanup")
                    self.assertEqual(select.select([child_fd], [], [], 0)[0], [child_fd],
                                     "worker returned with a surviving descendant")
                    self.assertTrue(pinned_signal.called, "cleanup must signal by pinned identity")
                    if cancel:
                        self.assertGreaterEqual(call.cancelling(), 2)
                finally:
                    if call is not None and not call.done():
                        call.cancel()
                        await asyncio.gather(call, return_exceptions=True)
                    if child_fd is not None:
                        try:
                            signal.pidfd_send_signal(child_fd, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        os.close(child_fd)

    async def test_reap_before_callback_timeout_never_signals_recycled_group(self):
        await self.exercise(delayed_reap=True)

    async def test_reap_before_callback_cancellation_never_signals_recycled_group(self):
        await self.exercise(delayed_reap=True, cancel=True)

    async def test_inherited_pipe_timeout_removes_descendants(self):
        await self.exercise()

    async def test_inherited_pipe_cancellation_removes_descendants(self):
        await self.exercise(cancel=True)

    async def test_closed_pipe_success_removes_descendants(self):
        await self.exercise(closed_pipe=True)

    async def test_closed_pipe_failure_removes_descendants(self):
        await self.exercise(closed_pipe=True, failure=True)


if __name__ == "__main__":
    unittest.main()
