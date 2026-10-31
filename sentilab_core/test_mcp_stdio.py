"""Exercise dispatch and cancellation over a single real stdio connection."""
import asyncio
import json
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


if __name__ == "__main__":
    unittest.main()
