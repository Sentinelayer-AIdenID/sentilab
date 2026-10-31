"""Import the existing oracle and replace only its worker lifetime/transport.

Request construction, fixture legality, raw input generation, HotSpot execution
and response validation remain in sundai_hotspot. Each call uses a fresh worker.
"""
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import signal
import sys
import tempfile

from sundai_hotspot.tap_oracle import HotSpotOracle


INITIAL_CENTERS = ((25, 25), (40, 40), (8, 9), (8, 25), (8, 41), (41, 15))
ROOT = Path(__file__).resolve().parent.parent


class FreshProcessOracle(HotSpotOracle):
    def __init__(self, *, fixture="ascend910", grid=16):
        if fixture != "ascend910":
            raise ValueError("only ascend910 is released; other fixtures require their own frozen margin")
        super().__init__(grid, grid, max_workers=1)
        self.initial = self.design_from_centers(INITIAL_CENTERS)
        self.wire_cap_mm = self._wirelength_mm(self.centers_for(self.initial))
        self.reservation = None
        self.last_usage = None
        self.stop_file = None

    def _get_worker_pool(self):
        return self

    @asynccontextmanager
    async def lease(self):
        if self.reservation is None:
            raise RuntimeError("worker requires a durable budget reservation")
        yield self

    async def aclose(self):
        pass  # each evaluate call closes and reaps its entire worker group

    async def evaluate(self, request, *, worker_timeout_s):
        with tempfile.TemporaryDirectory(prefix="sentilab-fresh-worker-") as workspace:
            return await self._evaluate({**request, "workspace_root": workspace}, worker_timeout_s=worker_timeout_s)

    async def _evaluate(self, request, *, worker_timeout_s):
        reservation = self.reservation
        ceiling = reservation["ceiling_s"]
        if ceiling < 2:
            raise ValueError("worker reservation must allow at least two CPU seconds")
        request = {**request, "solver_timeout_s": max(0.01, ceiling - 2)}
        payload = json.dumps(request, separators=(",", ":"), allow_nan=False).encode() + b"\n"
        if len(payload) > 65537:
            raise ValueError("oversize worker request")
        environment = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "TMPDIR") if key in os.environ}
        environment.update({"OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1",
                            "MKL_NUM_THREADS": "1", "PYTHONUNBUFFERED": "1", "PYTHONPATH": str(ROOT)})
        if os.environ.get("CI_ALLOCATION") == "1":
            environment["CI_ALLOCATION"] = "1"
        # No signer is passed in argv, stdin or environment. This process invokes
        # the imported worker once and exits; it never receives a signing key.
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "sentilab_core.worker", str(ceiling), cwd=ROOT / "sundai_tap", env=environment,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, start_new_session=True,
            pass_fds=(reservation["lease_fd"],), limit=65536)
        exchange = asyncio.create_task(process.communicate(payload))
        deadline = asyncio.get_running_loop().time() + ceiling
        self.last_usage = None
        try:
            while not exchange.done():
                if self.stop_file is not None and self.stop_file.exists():
                    raise RuntimeError("STOP during solve")
                if asyncio.get_running_loop().time() >= deadline:
                    raise TimeoutError("worker CPU/wall reservation exhausted")
                await asyncio.wait({exchange}, timeout=0.05)
            stdout, stderr = await exchange
            if process.returncode != 0 or len(stdout) > 65536:
                raise RuntimeError(f"fresh HotSpot worker failed: exit {process.returncode}: {stderr[-300:].decode(errors='replace')}")
            response = json.loads(stdout)
            self.last_usage = {"cpu_s": response["cpu_s"],
                               "process_id": response["process_id"] + ":" + reservation["operation_id"]}
            return response["result"]
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()
            if not exchange.done():
                exchange.cancel()
            await asyncio.gather(exchange, return_exceptions=True)

    async def measure(self, candidate, reservation, stop_file):
        self.reservation, self.stop_file = reservation, stop_file
        try:
            result = await self(candidate)
            return result, self.last_usage
        finally:
            self.reservation = None
