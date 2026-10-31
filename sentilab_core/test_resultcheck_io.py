"""Bounded file intake and cancellation through actual CLI/MCP processes."""
import asyncio
import builtins
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from sentilab_core import resultcheck


ERROR = {"error": {"code": "file_unreadable"}}

# Gate only the OS/file-read dependency, not ResultCheck or its transports.
# Both the old buffered reader and the descriptor reader hit the same real lock.
READ_BARRIER = r'''
import builtins
import fcntl
import os
from pathlib import Path

target = os.environ["RC_TEST_FILE"]
original_open, original_read = builtins.open, os.read
def barrier():
    Path(os.environ["RC_TEST_MARKERS"], str(os.getpid())).touch()
    with original_open(os.environ["RC_TEST_LOCK"], "rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
def read(fd, count):
    if os.path.realpath("/proc/self/fd/" + str(fd)) == target:
        barrier()
    return original_read(fd, count)
class Stream:
    def __init__(self, stream):
        self.stream = stream
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return self.stream.__exit__(*args)
    def read(self, *args):
        barrier()
        return self.stream.read(*args)
    def __getattr__(self, name):
        return getattr(self.stream, name)
def opened(file, *args, **kwargs):
    stream = original_open(file, *args, **kwargs)
    return Stream(stream) if file == target else stream
builtins.open, os.read = opened, read
'''


class FileIntakeTests(unittest.TestCase):
    @contextmanager
    def file_reads(self, read):
        """Inject the same read behavior into descriptor and buffered intake."""
        original = builtins.open
        def opened(*args, **kwargs):
            stream = original(*args, **kwargs)
            stream.read = lambda count: read(stream.fileno(), count)
            return stream
        with patch.object(os, "read", side_effect=read), patch.object(builtins, "open", side_effect=opened):
            yield

    def test_descriptor_is_checked_even_when_path_names_a_regular_file(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "regular.json"
            file.write_bytes(b"[]")
            fifo = Path(directory) / "fifo"
            os.mkfifo(fifo)
            fd = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
            opened = os.dup(fd)
            try:
                with patch.object(os, "open", return_value=opened):
                    with self.assertRaises(OSError):
                        resultcheck.check_file(file)
                with self.assertRaises(OSError):
                    os.fstat(opened)  # rejected descriptors must be closed
            finally:
                os.close(fd)
                try:
                    os.close(opened)
                except OSError:
                    pass

    def test_read_budget_does_not_follow_a_growing_regular_file(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "growing.json"
            file.write_bytes(b"[]")
            original = os.read
            sizes = []
            def growing(fd, count):
                sizes.append(count)
                if len(sizes) > 3:
                    raise AssertionError("reader followed unbounded file growth")
                with file.open("ab") as writer:
                    writer.write(b" " * 65536)
                return original(fd, count)
            with self.file_reads(growing):
                with self.assertRaises(OSError):
                    resultcheck.check_file(file)
            self.assertEqual(sum(sizes), 3, "read at most the initial size plus one")

    def test_same_size_rewrite_is_not_sealed_as_a_stable_file(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "changed.json"
            file.write_bytes(b"[]")
            initial = file.stat()
            original = os.read
            def changed(fd, count):
                data = original(fd, count)
                os.utime(file, ns=(initial.st_atime_ns, initial.st_mtime_ns + 1000000))
                return data
            with self.file_reads(changed):
                with self.assertRaises(OSError):
                    resultcheck.check_file(file)


class FileStdioTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.file = self.root / "input.json"
        self.file.write_bytes(b"[]")
        self.process = None
        self.lock = None
        self.env = {**os.environ, "SENTILAB_LIVE_DIR": str(self.root / "live"),
                    "SENTILAB_RESULTCHECK_DIR": str(self.root),
                    "SENTILAB_VIEW_PUBLIC_KEYS": "{}"}
        self.env.pop("SENTILAB_SIGNER_FACTORY", None)
        self.markers = self.root / "workers"
        self.markers.mkdir()

    async def asyncTearDown(self):
        await self.close_host()
        if self.lock is not None:
            self.lock.close()
        self.temp.cleanup()

    async def close_host(self):
        if self.process is not None and self.process.returncode is None:
            self.process.stdin.close()
            try:
                await asyncio.wait_for(self.process.communicate(), 2)
            except TimeoutError:
                # Clean up our own worker processes before killing a broken
                # host, so even mutation failures do not leave child processes.
                for marker in self.markers.iterdir():
                    pid = int(marker.name)
                    if pid != self.process.pid:
                        try:
                            os.kill(pid, 9)
                        except ProcessLookupError:
                            pass
                try:
                    await asyncio.wait_for(self.process.communicate(), 1)
                except TimeoutError:
                    self.process.kill()
                    await self.process.communicate()

    async def start(self, *command):
        self.process = await asyncio.create_subprocess_exec(
            sys.executable, *(command or ("-m", "sentilab_mcp")), env=self.env,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE)
        await self.send({"id": "startup", "method": "ping"})
        self.assertEqual((await self.receive())["result"], {})

    async def send(self, request):
        self.process.stdin.write((json.dumps(request) + "\n").encode())
        await self.process.stdin.drain()

    async def call(self, id, file=None):
        await self.send({"id": id, "method": "tools/call", "params": {
            "name": "sentilab_resultcheck", "arguments": {"file": str(file or self.file)}}})

    async def receive(self, timeout=3):
        return json.loads(await asyncio.wait_for(self.process.stdout.readline(), timeout))

    def unsupported_files(self):
        fifo = self.root / "fifo"
        os.mkfifo(fifo)
        yield fifo
        fd = os.open(fifo, os.O_RDWR | os.O_NONBLOCK)
        try:
            yield fifo
        finally:
            os.close(fd)
        yield Path("/dev/zero")  # endless bytes, no EOF
        yield Path("/proc/self/maps")  # regular mode, zero stat size, nonempty stream
        yield self.root
        huge = self.root / "oversize.json"
        with huge.open("wb") as stream:
            stream.truncate(16 * 1024 * 1024 + 1)
        yield huge

    async def test_cli_rejects_fifo_unbounded_and_oversized_inputs(self):
        for index, file in enumerate(self.unsupported_files()):
            with self.subTest(input=index, file=str(file)):
                process = await asyncio.create_subprocess_exec(
                    sys.executable, "-m", "sentilab_cli", "resultcheck", str(file),
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                try:
                    stdout, stderr = await asyncio.wait_for(process.communicate(), 2)
                    self.assertEqual(process.returncode, 2)
                    self.assertEqual(json.loads(stdout), ERROR)
                    self.assertEqual(stderr, b"")
                finally:
                    if process.returncode is None:
                        process.kill()
                    await process.communicate()

    async def test_mcp_rejects_fifo_unbounded_and_oversized_inputs_and_stays_usable(self):
        for index, file in enumerate(self.unsupported_files()):
            with self.subTest(input=index, file=str(file)):
                await self.start()
                try:
                    await self.call(1, file)
                    await self.send({"id": 2, "method": "ping"})
                    responses = {r["id"]: r for r in [await self.receive(), await self.receive()]}
                    self.assertEqual(responses[2]["result"], {})
                    self.assertTrue(responses[1]["result"]["isError"])
                    self.assertEqual(json.loads(responses[1]["result"]["content"][0]["text"]), ERROR)
                finally:
                    await self.close_host()

    async def block_reader(self, count=1):
        hook = self.root / "hooks"
        hook.mkdir()
        (hook / "sitecustomize.py").write_text(READ_BARRIER)
        lockfile = self.root / "read.lock"
        self.lock = lockfile.open("wb")
        fcntl.flock(self.lock, fcntl.LOCK_EX)
        self.env.update(PYTHONPATH=str(hook), RC_TEST_FILE=str(self.file),
                        RC_TEST_LOCK=str(lockfile), RC_TEST_MARKERS=str(self.markers))
        await self.start()
        for id in range(1, count + 1):
            await self.call(id)
        async with asyncio.timeout(3):
            while len(list(self.markers.iterdir())) != count:
                await asyncio.sleep(0.01)
        return [int(marker.name) for marker in self.markers.iterdir()]

    def assert_reaped(self, pids):
        for pid in pids:
            self.assertFalse(Path(f"/proc/{pid}").exists(), f"worker {pid} must be reaped")

    async def test_cancel_reaps_reader_while_ping_status_and_stop_remain_responsive(self):
        pids = await self.block_reader()
        await self.send({"id": 2, "method": "ping"})
        self.assertEqual((await self.receive())["id"], 2)
        for id, operation in ((3, "status"), (4, "stop")):
            await self.send({"id": id, "method": "tools/call", "params": {
                "name": "sentilab_live_" + operation, "arguments": {"ai_off": True}}})
            response = await self.receive()
            self.assertEqual(response["id"], id)
            self.assertIn("result", response)
        self.assertTrue((self.root / "live" / "STOP").exists())
        for _ in range(2):
            await self.send({"method": "notifications/cancelled", "params": {"requestId": 1}})
        response = await self.receive()
        self.assertEqual(response["id"], 1)
        self.assertEqual(response["error"]["code"], -32800)
        self.assert_reaped(pids)
        self.lock.close()
        self.lock = None
        await self.call(5)
        receipt = (await self.receive())["result"]["content"][0]["text"]
        self.assertEqual(receipt, resultcheck.canonical(resultcheck.check_raw(b"[]")))

    async def test_eof_cancels_and_reaps_file_worker_before_host_exits(self):
        pids = await self.block_reader()
        self.process.stdin.close()
        stdout, stderr = await asyncio.wait_for(self.process.communicate(), 3)
        self.assertEqual(self.process.returncode, 0, stderr)
        response = json.loads(stdout)
        self.assertEqual(response["id"], 1)
        self.assertEqual(response["error"]["code"], -32800)
        self.assert_reaped(pids)

    async def test_deadline_reaps_file_worker_and_keeps_host_usable(self):
        pids = await self.block_reader()
        response = await self.receive(timeout=12)
        self.assertEqual(response["id"], 1)
        self.assertEqual(json.loads(response["result"]["content"][0]["text"]), ERROR)
        self.assertTrue(response["result"]["isError"])
        self.assert_reaped(pids)
        await self.send({"id": 2, "method": "ping"})
        self.assertEqual((await self.receive())["result"], {})

    async def test_worker_concurrency_is_bounded_and_eof_reaps_all(self):
        pids = await self.block_reader(count=8)
        await self.call(9)
        response = await self.receive()
        self.assertEqual(response["id"], 9)
        self.assertEqual(response["error"]["code"], -32000)
        self.assertEqual(len(list(self.markers.iterdir())), 8)
        self.process.stdin.close()
        stdout, stderr = await asyncio.wait_for(self.process.communicate(), 3)
        self.assertEqual(self.process.returncode, 0, stderr)
        responses = [json.loads(line) for line in stdout.splitlines()]
        self.assertEqual({r["id"] for r in responses}, set(range(1, 9)))
        self.assertTrue(all(r["error"]["code"] == -32800 for r in responses))
        self.assert_reaped(pids)

    async def test_cancel_during_worker_creation_drains_full_stdout_and_reaps(self):
        # A real large receipt fills the worker pipe before creation returns to
        # the tool. This also tests the cancellation/process-ownership boundary.
        request = dict(schema_version="resultcheck.request.v2", request_id="large-receipt",
                       metric=dict(name="latency", unit="ms", direction="lower_is_better"),
                       pairs=[dict(id=str(i) + "x" * 60, baseline=None, candidate=1) for i in range(6000)])
        self.file.write_text(json.dumps(request))
        created = self.root / "created"
        release = self.root / "release"
        script = r'''
import asyncio
from pathlib import Path
import sys
from sentilab_mcp import __main__ as host
original = asyncio.create_subprocess_exec
async def delayed(*args, **kwargs):
    process = await original(*args, **kwargs)
    while not process.stdout._paused:
        await asyncio.sleep(0.01)
    Path(sys.argv[1]).write_text(str(process.pid))
    while not Path(sys.argv[2]).exists():
        await asyncio.sleep(0.01)
    return process
asyncio.create_subprocess_exec = delayed
host.main()
'''
        await self.start("-c", script, str(created), str(release))
        await self.call(1)
        async with asyncio.timeout(3):
            while not created.exists():
                await asyncio.sleep(0.01)
        pid = int(created.read_text())
        (self.markers / str(pid)).touch()
        try:
            await self.send({"method": "notifications/cancelled", "params": {"requestId": 1}})
            await self.send({"id": 2, "method": "ping"})
            self.assertEqual((await self.receive())["id"], 2)
        finally:
            release.touch()
        response = await self.receive()
        self.assertEqual(response["id"], 1)
        self.assertEqual(response["error"]["code"], -32800)
        self.assert_reaped([pid])


if __name__ == "__main__":
    unittest.main()
