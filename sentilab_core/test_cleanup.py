"""Cancellation barriers around the real conductor and MCP host; no solves."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from sundai_controller.experiment import plate_initial_design
from sentilab_core.budget import BudgetHalt
from sentilab_core.conductor import Conductor
from sentilab_core.ledger import lock
from sentilab_core.signing import ephemeral_signer


class BarrierOracle:
    initial = plate_initial_design()
    problem_hash = "cleanup-test"
    solver_version = "no-solves"
    wire_cap_mm = 100.0

    def __init__(self):
        self.tick_started = asyncio.Event()
        self.stopped = asyncio.Event()
        self.close_started = asyncio.Event()
        self.release = asyncio.Event()
        self.close_calls = 0
        self.completed = False
        self.error = None
        self.run_task = None

    async def tick(self):
        self.run_task = asyncio.current_task()
        self.tick_started.set()
        await self.stopped.wait()
        raise BudgetHalt("STOP")

    async def aclose(self):
        self.close_calls += 1
        self.close_started.set()
        await self.release.wait()
        self.completed = True
        if self.error:
            raise self.error


class CleanupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.oracle = BarrierOracle()
        signer = ephemeral_signer()
        self.conductor = Conductor(self.temp.name, signer=signer,
                                   public_keys={signer.key_id: signer.public_key}, oracle=self.oracle)
        self.conductor.tick = self.oracle.tick
        self.task = asyncio.create_task(self.conductor.run(run_id="cleanup"))
        await asyncio.wait_for(self.oracle.tick_started.wait(), 5)

    async def asyncTearDown(self):
        self.oracle.stopped.set()
        self.oracle.release.set()
        await asyncio.wait_for(asyncio.gather(self.task, return_exceptions=True), 5)
        self.temp.cleanup()

    async def enter_cleanup(self, *, cancelled=False):
        if cancelled:
            self.task.cancel()
        else:
            self.oracle.stopped.set()
        await asyncio.wait_for(self.oracle.close_started.wait(), 5)

    async def cancel_while_closing(self):
        self.task.cancel()
        await asyncio.sleep(0)  # deliver this cancellation while the barrier stays closed
        self.assertFalse(self.task.done(), "run completed before cleanup was released")
        self.assertFalse(self.oracle.completed)
        self.assertEqual(self.oracle.close_calls, 1)
        with self.assertRaises(BlockingIOError), lock(self.conductor.root / "owner.lock", blocking=False):
            self.fail("ownership released before cleanup")

    async def assert_cancelled_after_cleanup(self):
        self.oracle.release.set()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(self.task, 5)
        self.assertTrue(self.oracle.completed)
        with lock(self.conductor.root / "owner.lock", blocking=False):
            pass

    async def test_cancel_before_cleanup_survives_another_cancel(self):
        await self.enter_cleanup(cancelled=True)
        await self.cancel_while_closing()
        await self.assert_cancelled_after_cleanup()

    async def test_cancel_during_normal_cleanup_retains_ownership(self):
        await self.enter_cleanup()
        await self.cancel_while_closing()
        await self.assert_cancelled_after_cleanup()

    async def test_repeated_cancellation_awaits_one_cleanup(self):
        await self.enter_cleanup()
        for _ in range(3):
            await self.cancel_while_closing()
        await self.assert_cancelled_after_cleanup()

    async def test_cleanup_failure_is_observed_despite_cancellation(self):
        await self.enter_cleanup()
        self.oracle.error = RuntimeError("cleanup failed")
        self.task.cancel()
        await asyncio.sleep(0)
        self.oracle.release.set()
        with self.assertRaisesRegex(RuntimeError, "cleanup failed"):
            await asyncio.wait_for(self.task, 5)
        self.assertTrue(self.oracle.completed)

    async def test_normal_cleanup_preserves_stop_result(self):
        await self.enter_cleanup()
        self.oracle.release.set()
        result = await asyncio.wait_for(self.task, 5)
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(result["spend"]["solves"], 0)
        self.assertTrue(self.oracle.completed)
        self.assertEqual(self.oracle.close_calls, 1)


HOST = r'''
import asyncio
import json
import os
from pathlib import Path
import sys
from sentilab_core.conductor import Conductor
from sentilab_core.operations import Context, stop
from sentilab_core.signing import ephemeral_signer
from sentilab_core.test_cleanup import BarrierOracle
from sentilab_mcp import __main__ as host

async def main():
    root = Path(sys.argv[1])
    oracle = BarrierOracle()
    if sys.argv[4] == "error":
        oracle.error = RuntimeError("cleanup failed")
    signer = ephemeral_signer()
    context = Context(root, {signer.key_id: signer.public_key}, signer, {"oracle": oracle})
    Conductor.tick = lambda self: oracle.tick()
    loop = asyncio.get_running_loop()
    release = asyncio.StreamReader()
    transport, _ = await loop.connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(release), os.fdopen(int(sys.argv[2]), "rb"))
    class ObservedTask(asyncio.Task):
        def cancel(self, *args, **kwargs):
            result = super().cancel(*args, **kwargs)
            if self is oracle.run_task:
                os.write(int(sys.argv[3]), b"c")
            return result
    loop.set_task_factory(lambda loop, coro, **kwargs: ObservedTask(coro, loop=loop, **kwargs))
    async def release_cleanup():
        await release.readexactly(1)
        oracle.release.set()
    async def status(context, **arguments):
        await oracle.tick_started.wait()
        return {"active": True}
    async def stopped(context, **arguments):
        result = stop(context, **arguments)
        oracle.stopped.set()
        await oracle.close_started.wait()
        return result
    async def closing(context, **arguments):
        await oracle.close_started.wait()
        return {"closing": True}
    host.TOOLS.update(sentilab_live_status=status, sentilab_live_stop=stopped,
                      sentilab_live_verify=closing)
    releasing = asyncio.create_task(release_cleanup())
    try:
        await host.serve(context)
    finally:
        (root / "cleanup.json").write_text(json.dumps(
            {"completed": oracle.completed, "calls": oracle.close_calls}))
        releasing.cancel()
        await asyncio.gather(releasing, return_exceptions=True)
        transport.close()
asyncio.run(main())
'''


class StdioCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def check_shutdown(self, *, cancel_first=False, error=False):
        with tempfile.TemporaryDirectory() as directory:
            release_read, release_write = os.pipe()
            notice_read, notice_write = os.pipe()
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-c", HOST, directory, str(release_read), str(notice_write),
                "error" if error else "ok", pass_fds=(release_read, notice_write),
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE)
            os.close(release_read)
            os.close(notice_write)
            notices = asyncio.StreamReader()
            transport, _ = await asyncio.get_running_loop().connect_read_pipe(
                lambda: asyncio.StreamReaderProtocol(notices), os.fdopen(notice_read, "rb"))

            async def send(request):
                process.stdin.write(json.dumps(request).encode() + b"\n")
                await process.stdin.drain()

            async def call(id, operation):
                arguments = {"ai_off": True}
                if operation == "verify":
                    arguments["run_id"] = "cleanup"
                await send({"id": id, "method": "tools/call", "params": {
                    "name": "sentilab_live_" + operation, "arguments": arguments}})

            async def receive():
                return json.loads(await asyncio.wait_for(process.stdout.readline(), 5))

            try:
                await call(1, "run")
                await call(2, "status")
                self.assertEqual((await receive())["id"], 2)
                cancellation = {"method": "notifications/cancelled", "params": {"requestId": 1}}
                if cancel_first:
                    await send(cancellation)
                    await asyncio.wait_for(notices.readexactly(1), 5)
                    await call(3, "verify")  # barrier: cancellation has entered cleanup
                else:
                    await call(3, "stop")  # barrier: normal completion has entered cleanup
                self.assertEqual((await receive())["id"], 3)
                if cancel_first:
                    await send(cancellation)
                    await send(cancellation)
                process.stdin.close()
                if not cancel_first:
                    # Observe the actual EOF cancellation before releasing cleanup.
                    await asyncio.wait_for(notices.readexactly(1), 5)
                os.write(release_write, b"r")
                response = await receive()
                self.assertEqual(response["id"], 1)
                self.assertEqual(response["error"]["code"], -32603 if error else -32800)
                await asyncio.wait_for(process.wait(), 5)
                stderr = (await process.stderr.read()).decode()
                self.assertEqual(process.returncode, 0, stderr)
                self.assertEqual(stderr, "")
                self.assertEqual(json.loads(Path(directory, "cleanup.json").read_text()),
                                 {"completed": True, "calls": 1})
            finally:
                os.close(release_write)
                transport.close()
                if process.returncode is None:
                    process.kill()
                await process.communicate()

    async def test_eof_during_normal_cleanup_waits_for_completion(self):
        await self.check_shutdown()

    async def test_cancel_before_cleanup_then_repeated_cancel_and_eof(self):
        await self.check_shutdown(cancel_first=True)

    async def test_cleanup_failure_after_eof_returns_internal_error(self):
        await self.check_shutdown(error=True)


if __name__ == "__main__":
    unittest.main()
