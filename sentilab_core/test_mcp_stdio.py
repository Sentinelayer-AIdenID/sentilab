"""Exercise dispatch and cancellation over a single real stdio connection."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


HOST = r'''
import asyncio
from pathlib import Path
import sys
from sentilab_mcp import __main__ as host

active = False
stopped = asyncio.Event()
async def run(context, **arguments):
    global active
    active = True
    try:
        await stopped.wait()
        return {"completed": True}
    finally:
        active = False
        Path(sys.argv[1]).write_text("cleaned")
def status(context, **arguments):
    return {"active": active}
def stop(context, **arguments):
    stopped.set()
    return {"stopped": True}
async def verify(context, **arguments):
    await stopped.wait()
    return {}
host.TOOLS.update(sentilab_live_run=run, sentilab_live_status=status,
                  sentilab_live_stop=stop, sentilab_live_verify=verify)
host.main()
'''


class StdioTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cleaned = Path(self.temp.name) / "cleanup"
        self.process = await asyncio.create_subprocess_exec(
            sys.executable, "-c", HOST, str(self.cleaned),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE)

    async def asyncTearDown(self):
        if self.process.returncode is None:
            self.process.kill()
        await self.process.communicate()
        self.temp.cleanup()

    async def send(self, request):
        self.process.stdin.write(json.dumps(request).encode() + b"\n")
        await self.process.stdin.drain()

    async def call(self, id, operation):
        await self.send({"jsonrpc": "2.0", "id": id, "method": "tools/call",
                         "params": {"name": "sentilab_live_" + operation,
                                    "arguments": {"ai_off": True}}})

    async def receive(self):
        return json.loads(await asyncio.wait_for(self.process.stdout.readline(), 5))

    async def start_run(self):
        await self.call(1, "run")
        await self.call(2, "status")
        response = await self.receive()
        self.assertEqual(response["id"], 2)
        self.assertEqual(json.loads(response["result"]["content"][0]["text"]), {"active": True})
        self.assertFalse(self.cleaned.exists(), "status must complete before the run")

    async def test_status_and_stop_complete_while_run_is_active(self):
        await self.start_run()
        await self.call(3, "stop")
        responses = [await self.receive(), await self.receive()]
        self.assertEqual({r["id"] for r in responses}, {1, 3})
        self.assertTrue(all("result" in r for r in responses))
        self.assertEqual(self.cleaned.read_text(), "cleaned")

    async def test_disconnect_cancels_run_and_awaits_cleanup(self):
        await self.start_run()
        self.process.stdin.close()
        await asyncio.wait_for(self.process.wait(), 5)
        self.assertEqual(self.process.returncode, 0, (await self.process.stderr.read()).decode())
        self.assertEqual(self.cleaned.read_text(), "cleaned")

    async def test_cancellation_cleans_run_and_keeps_connection_usable(self):
        await self.start_run()
        await self.send({"jsonrpc": "2.0", "method": "notifications/cancelled",
                         "params": {"requestId": 1}})
        response = await self.receive()
        self.assertEqual(response["id"], 1)
        self.assertEqual(response["error"]["code"], -32800)
        self.assertEqual(self.cleaned.read_text(), "cleaned")
        await self.call(3, "status")
        response = await self.receive()
        self.assertEqual(json.loads(response["result"]["content"][0]["text"]), {"active": False})

    async def test_dispatch_bound_rejects_excess_work_without_blocking_reader(self):
        for id in range(1, 10):
            await self.call(id, "verify")
        response = await self.receive()
        self.assertEqual(response["id"], 9)
        self.assertEqual(response["error"]["code"], -32000)
        await self.send({"method": "notifications/cancelled", "params": {"requestId": 1}})
        self.assertEqual((await self.receive())["error"]["code"], -32800)
        await self.call(10, "stop")
        responses = [await self.receive() for _ in range(8)]
        self.assertEqual({r["id"] for r in responses}, set(range(2, 9)) | {10})


class LazyContextTests(unittest.IsolatedAsyncioTestCase):
    send = StdioTests.send
    receive = StdioTests.receive
    call = StdioTests.call

    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.process = None
        self.file = Path(self.temp.name) / "result.json"
        self.file.write_bytes(b"[]")

    async def asyncTearDown(self):
        if self.process is not None:
            if self.process.returncode is None:
                self.process.kill()
            await self.process.communicate()
        self.temp.cleanup()

    async def start(self, *command, env=None):
        env = {**(os.environ if env is None else env), "SENTILAB_RESULTCHECK_DIR": self.temp.name}
        self.process = await asyncio.create_subprocess_exec(
            sys.executable, *command, env=env, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

    async def resultcheck(self, id):
        from sentilab_core.resultcheck import canonical, check_raw
        await self.send({"id": id, "method": "tools/call", "params": {
            "name": "sentilab_resultcheck", "arguments": {"file": str(self.file)}}})
        response = await self.receive()
        self.assertEqual(response["id"], id)
        self.assertEqual(response["result"]["content"][0]["text"], canonical(check_raw(b"[]")))

    async def test_real_stdio_offline_calls_survive_failed_live_initialization(self):
        env = {**os.environ, "PATH": self.temp.name,
               "SENTILAB_VIEW_PUBLIC_KEYS": "invalid", "SENTILAB_SIGNER_FACTORY": "missing:factory"}
        await self.start("-m", "sentilab_mcp", env=env)
        for id, method in enumerate(("initialize", "ping", "tools/list")):
            await self.send({"id": id, "method": method})
            response = await self.receive()
            self.assertEqual(response["id"], id)
            self.assertIn("result", response)
        await self.resultcheck(3)
        await self.call(4, "status")
        response = await self.receive()
        self.assertEqual(response["id"], 4)
        self.assertEqual(response["error"]["code"], -32602)
        await self.resultcheck(5)
        self.process.stdin.close()
        await asyncio.wait_for(self.process.wait(), 5)
        self.assertEqual(self.process.returncode, 0, (await self.process.stderr.read()).decode())

    async def test_stdio_live_context_is_created_lazily_and_shared(self):
        marker = Path(self.temp.name) / "context-count"
        script = r'''
import sys
from pathlib import Path
from sentilab_core import operations
from sentilab_mcp import __main__ as host
calls = 0
context = object()
def factory():
    global calls
    calls += 1
    Path(sys.argv[1]).write_text(str(calls))
    return context
def operation(received, **arguments):
    assert received is context
    return {"context_calls": calls}
operations.environment_context = factory
host.TOOLS.update(sentilab_live_status=operation, sentilab_live_stop=operation)
host.main()
'''
        await self.start("-c", script, str(marker))
        await self.resultcheck(1)
        self.assertFalse(marker.exists(), "offline tools must not initialize a live context")
        for id, operation in ((2, "status"), (3, "stop")):
            await self.call(id, operation)
            response = await self.receive()
            self.assertEqual(response["id"], id)
            self.assertEqual(json.loads(response["result"]["content"][0]["text"]), {"context_calls": 1})
            self.assertEqual(marker.read_text(), "1")


if __name__ == "__main__":
    unittest.main()
