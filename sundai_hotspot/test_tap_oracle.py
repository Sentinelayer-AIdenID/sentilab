"""Contract tests for the isolated TAP/HotSpot controller oracle."""
from __future__ import annotations

import asyncio
from dataclasses import replace
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tap_oracle import (
    HOTSPOT_BINARY, REPO_ROOT, HotSpotOracle, HotSpotOracleError, HotSpotTimeoutError,
    TapLegalityError, _WarmWorkerPool, _run_worker, _sha256,
)
from tap_oracle_worker import _parse_grid


BASE_CENTERS = ((25, 25), (40, 40), (8, 9), (8, 25), (8, 41), (41, 15))


class HotSpotOracleTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        if not HOTSPOT_BINARY.is_file():
            raise unittest.SkipTest("build HotSpot before running oracle integration tests")
        cls.oracle = HotSpotOracle(16, 16)

    async def asyncTearDown(self):
        await self.oracle.aclose()

    async def test_illegal_off_grid_layout_is_rejected_before_worker_start(self):
        centers = [list(point) for point in BASE_CENTERS]
        centers[0][0] = 25.5
        design = self.oracle.design_from_centers(centers)
        with mock.patch("tap_oracle._run_worker", new_callable=mock.AsyncMock) as worker:
            with self.assertRaisesRegex(TapLegalityError, "placement grid"):
                await self.oracle(design)
        worker.assert_not_awaited()

    async def test_result_binds_candidate_problem_grid_heatmap_and_wire_proxy(self):
        design = self.oracle.design_from_centers(BASE_CENTERS)
        result = await self.oracle(design)

        self.assertEqual(result.candidate_hash, design.hash)
        self.assertEqual(result.problem_hash, self.oracle.problem_hash)
        self.assertEqual((result.grid_rows, result.grid_cols), (16, 16))
        self.assertEqual(len(result.heatmap_c), 16)
        self.assertTrue(all(len(row) == 16 for row in result.heatmap_c))
        self.assertEqual(result.maximum_temperature_c, max(max(row) for row in result.heatmap_c))
        self.assertTrue(math.isfinite(result.wirelength_mm))
        self.assertEqual(result.wire_metric,
                         "connectivity-weighted Manhattan center distance (mm); not routed CPLEX length")
        self.assertAlmostEqual(result.maximum_temperature_c, 118.36, delta=0.01)
        self.assertGreater(result.evaluation_seconds, 0)
        self.assertEqual({name for name, _ in result.input_sha256}, {
            "new_hotspot.config", "sampleL0_Substrate.flp", "sampleL1_C4Layer.flp",
            "sampleL2_Interposer.flp", "sampleL3_UbumpLayer.flp", "sampleL4_ChipLayer.flp",
            "sampleL5_TIM.flp", "samplelayers.lcf", "sample.ptrace", "sampleL3.flp",
            "sampleL4.flp", "samplesim.flp",
        })

    async def test_custom_hotspot_binary_is_bound_and_passed_to_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "hotspot-custom"
            binary.write_bytes(b"test-only executable placeholder")
            oracle = HotSpotOracle(16, 16, hotspot_binary=binary)
            design = oracle.design_from_centers(BASE_CENTERS)
            required_inputs = (
                "new_hotspot.config", "sampleL0_Substrate.flp", "sampleL1_C4Layer.flp",
                "sampleL2_Interposer.flp", "sampleL3_UbumpLayer.flp", "sampleL4_ChipLayer.flp",
                "sampleL5_TIM.flp", "samplelayers.lcf", "sample.ptrace",
            )
            response = {
                "candidate_hash": design.hash,
                "problem_hash": oracle.problem_hash,
                "binary_sha256": oracle.problem.hotspot_binary_sha256,
                "grid_rows": 16,
                "grid_cols": 16,
                "heatmap_c": [[118.36] * 16 for _ in range(16)],
                "maximum_temperature_c": 118.36,
                "all_layers_peak_c": 118.36,
                "solver_seconds": 0.1,
                "input_generation_seconds": 0.01,
                "input_sha256": {name: "a" * 64 for name in required_inputs},
            }
            with mock.patch("tap_oracle._run_worker", new_callable=mock.AsyncMock,
                            return_value=response) as worker:
                await oracle(design)

            request = worker.await_args.args[0]
            self.assertEqual(request["hotspot_binary"], str(binary.resolve()))
            self.assertEqual(request["expected_binary_sha256"], oracle.problem.hotspot_binary_sha256)
            await oracle.aclose()

    async def test_four_concurrent_evaluations_keep_inputs_isolated(self):
        centers_by_x = []
        for x in (25, 23, 21, 27):
            centers = [list(point) for point in BASE_CENTERS]
            centers[0][0] = x
            centers_by_x.append(centers)
        designs = [self.oracle.design_from_centers(centers) for centers in centers_by_x]

        results = await asyncio.gather(*(self.oracle(design) for design in designs))

        self.assertEqual([result.candidate_hash for result in results],
                         [design.hash for design in designs])
        floorplan_hashes = [dict(result.input_sha256)["sampleL4_ChipLayer.flp"] for result in results]
        self.assertEqual(len(set(floorplan_hashes)), 4)
        self.assertTrue(all(len(result.heatmap_c) == 16 for result in results))

    async def test_eight_way_warm_results_match_sequential_heatmaps_exactly(self):
        designs = []
        for x in range(20, 28):
            centers = [list(point) for point in BASE_CENTERS]
            centers[0][0] = x
            designs.append(self.oracle.design_from_centers(centers))

        sequential = [await self.oracle(design) for design in designs]
        sequential_evidence = [
            (result.heatmap_c, result.maximum_temperature_c, result.all_layers_peak_c)
            for result in sequential
        ]
        worker_pids = []
        original_evaluate = __import__("tap_oracle")._WarmWorker.evaluate

        async def track_worker(worker, request, *, worker_timeout_s):
            worker_pids.append(worker.pid)
            return await original_evaluate(worker, request, worker_timeout_s=worker_timeout_s)

        with mock.patch("tap_oracle._WarmWorker.evaluate", new=track_worker):
            concurrent = await asyncio.gather(*(self.oracle(design) for design in designs))

        concurrent_evidence = [
            (result.heatmap_c, result.maximum_temperature_c, result.all_layers_peak_c)
            for result in concurrent
        ]
        self.assertEqual(concurrent_evidence, sequential_evidence)
        self.assertEqual(len(worker_pids), 8)
        self.assertEqual(len(set(worker_pids)), 8, "concurrent calls shared a worker process")

    async def test_solver_timeout_is_reported_as_a_bounded_oracle_failure(self):
        oracle = HotSpotOracle(16, 16, solver_timeout_s=0.000001, worker_timeout_s=5)
        design = oracle.design_from_centers(BASE_CENTERS)
        try:
            with self.assertRaises(HotSpotTimeoutError):
                await oracle(design)
        finally:
            await oracle.aclose()

    @unittest.skipUnless(os.name == "posix", "process-group assertion uses /proc")
    async def test_worker_timeout_terminates_its_solver_descendant(self):
        with tempfile.TemporaryDirectory() as directory:
            pid_file = Path(directory) / "child.pid"
            workspace_file = Path(directory) / "workspace.path"
            worker = Path(directory) / "worker.py"
            worker.write_text(
                "import json, pathlib, signal, subprocess, sys, time\n"
                "request = json.loads(sys.stdin.readline())\n"
                "child = subprocess.Popen([sys.executable, '-c', "
                "'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)'])\n"
                "pathlib.Path(request['pid_file']).write_text(str(child.pid))\n"
                "pathlib.Path(request['workspace_file']).write_text(request['workspace_root'])\n"
                "time.sleep(60)\n",
                encoding="utf-8",
            )
            with mock.patch("tap_oracle.WORKER", worker):
                with self.assertRaises(HotSpotTimeoutError):
                    await _run_worker({"pid_file": str(pid_file), "workspace_file": str(workspace_file)},
                                       worker_timeout_s=0.2)

            child_pid = int(pid_file.read_text(encoding="utf-8"))
            workspace_path = Path(workspace_file.read_text(encoding="utf-8"))
            self.assertFalse(workspace_path.exists(), "worker timeout left its temporary workspace behind")
            child_status = Path(f"/proc/{child_pid}/stat")

            def child_is_stopped():
                try:
                    fields = child_status.read_text(encoding="utf-8").split()
                except FileNotFoundError:
                    return True
                return len(fields) > 2 and fields[2] == "Z"

            for _ in range(50):
                if child_is_stopped():
                    break
                await asyncio.sleep(0.02)
            self.assertTrue(
                child_is_stopped(),
                "worker timeout left the solver descendant running",
            )


def _fake_worker(directory: Path) -> Path:
    worker = directory / "worker.py"
    worker.write_text(
        "import json, os, pathlib, signal, subprocess, sys, tempfile, time\n"
        "for line in sys.stdin.buffer:\n"
        " request = json.loads(line)\n"
        " mode = request.get('mode', 'ok')\n"
        " pathlib.Path(request['workspace_file']).write_text(request['workspace_root']) if request.get('workspace_file') else None\n"
        " if mode == 'malformed': print('{broken json', flush=True); continue\n"
        " if mode == 'crash': os._exit(17)\n"
        " if mode in ('hang', 'cancel'):\n"
        "  child = subprocess.Popen([sys.executable, '-c', 'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)'])\n"
        "  pathlib.Path(request['pid_file']).write_text(str(child.pid))\n"
        "  time.sleep(60)\n"
        " with tempfile.TemporaryDirectory(prefix='call-', dir=request['workspace_root']) as work:\n"
        "  pathlib.Path(work, 'marker').write_text('ok')\n"
        "  result = {'pid': os.getpid(), 'cwd': os.getcwd(), 'workspace': request['workspace_root'], 'call_dir': work}\n"
        " print(json.dumps({'ok': True, 'result': result}), flush=True)\n",
        encoding="utf-8",
    )
    return worker


class WarmWorkerProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="tfl-warm-protocol-")
        self.root = Path(self.directory.name)
        self.worker_path = _fake_worker(self.root)
        self.pool = _WarmWorkerPool(max_workers=8)
        self.worker_patch = mock.patch("tap_oracle.WORKER", self.worker_path)
        self.worker_patch.start()

    async def asyncTearDown(self):
        await self.pool.close()
        self.worker_patch.stop()
        self.directory.cleanup()

    async def test_reuses_process_with_fresh_call_directories_and_stable_cwd(self):
        caller_cwd = Path.cwd()
        first = await _run_worker({"mode": "ok"}, worker_timeout_s=2, pool=self.pool)
        second = await _run_worker({"mode": "ok"}, worker_timeout_s=2, pool=self.pool)
        self.assertEqual(first["pid"], second["pid"], "sequential calls did not reuse the warm worker")
        self.assertEqual(first["cwd"], second["cwd"])
        self.assertNotEqual(first["call_dir"], second["call_dir"])
        self.assertEqual(Path(first["call_dir"]).parent, Path(first["workspace"]))
        self.assertFalse(Path(first["call_dir"]).exists())
        self.assertFalse(Path(second["call_dir"]).exists())
        self.assertTrue(Path(first["workspace"]).is_dir())
        self.assertEqual(len(self.pool._workers), 1)
        self.assertEqual(Path.cwd(), caller_cwd, "oracle changed the caller's process working directory")
        await self.pool.close()
        self.assertFalse(Path(first["workspace"]).exists(), "pool shutdown left its workspace behind")

    async def test_eight_overlapping_leases_use_distinct_worker_processes(self):
        async def request(index):
            async with self.pool.lease() as worker:
                response = await worker.evaluate({"mode": "ok", "index": index}, worker_timeout_s=3)
                return worker.pid, response

        results = await asyncio.gather(*(request(i) for i in range(8)))
        self.assertEqual(len({pid for pid, _ in results}), 8)
        self.assertEqual(len({response["workspace"] for _, response in results}), 8)
        self.assertEqual(len({response["call_dir"] for _, response in results}), 8)
        self.assertTrue(all(not Path(response["call_dir"]).exists() for _, response in results))

    async def test_malformed_and_crashed_worker_is_retired_then_replaced(self):
        for mode in ("malformed", "crash"):
            with self.subTest(mode=mode):
                with self.assertRaises(HotSpotOracleError):
                    await _run_worker({"mode": mode}, worker_timeout_s=2, pool=self.pool)
                self.assertEqual(len(self.pool._workers), 0)
                replacement = await _run_worker({"mode": "ok"}, worker_timeout_s=2, pool=self.pool)
                self.assertTrue(replacement["pid"] > 0)
                self.assertEqual(len(self.pool._workers), 1)

    async def test_bad_result_validation_retires_the_warm_worker(self):
        def reject(_response):
            raise HotSpotOracleError("synthetic invalid result")

        with self.assertRaisesRegex(HotSpotOracleError, "synthetic invalid result"):
            await _run_worker({"mode": "ok"}, worker_timeout_s=2, pool=self.pool, validator=reject)
        self.assertEqual(len(self.pool._workers), 0)
        replacement = await _run_worker({"mode": "ok"}, worker_timeout_s=2, pool=self.pool)
        self.assertGreater(replacement["pid"], 0)

    @unittest.skipUnless(os.name == "posix", "process-group assertion requires POSIX")
    async def test_timeout_and_cancel_kill_descendants_and_recover(self):
        for mode in ("hang", "cancel"):
            with self.subTest(mode=mode):
                pid_file = self.root / f"{mode}.pid"
                workspace_file = self.root / f"{mode}.workspace"
                call = asyncio.create_task(_run_worker(
                    {"mode": mode, "pid_file": str(pid_file), "workspace_file": str(workspace_file)},
                worker_timeout_s=(1.0 if mode == "hang" else 5), pool=self.pool))
                try:
                    for _ in range(100):
                        if pid_file.exists():
                            break
                        await asyncio.sleep(0.02)
                    self.assertTrue(pid_file.exists(), "fake HotSpot descendant did not start")
                    worker_pid = next(iter(self.pool._workers)).pid
                    if mode == "cancel":
                        call.cancel()
                        with self.assertRaises(asyncio.CancelledError):
                            await call
                    else:
                        with self.assertRaises(HotSpotTimeoutError):
                            await call
                finally:
                    if not call.done():
                        call.cancel()
                        await asyncio.gather(call, return_exceptions=True)
                child_pid = int(pid_file.read_text(encoding="utf-8"))
                workspace_path = Path(workspace_file.read_text(encoding="utf-8"))
                self.assertFalse(workspace_path.exists(), "retired worker workspace remained on disk")
                child_status = Path(f"/proc/{child_pid}/stat")
                for _ in range(100):
                    if not child_status.exists() or child_status.read_text(encoding="utf-8").split()[2] == "Z":
                        break
                    await asyncio.sleep(0.02)
                self.assertTrue(
                    not child_status.exists() or child_status.read_text(encoding="utf-8").split()[2] == "Z",
                    "worker cleanup left a solver descendant running",
                )
                self.assertEqual(len(self.pool._workers), 0)
                next_result = await _run_worker({"mode": "ok"}, worker_timeout_s=2, pool=self.pool)
                self.assertNotEqual(worker_pid, next_result["pid"], "failed worker was reused")


@unittest.skipUnless(os.name == "posix", "fake HotSpot executable uses a POSIX shebang")
class HotSpotIntegrityTests(unittest.IsolatedAsyncioTestCase):
    async def test_warm_worker_rechecks_binary_and_source_hashes_on_each_call(self):
        with tempfile.TemporaryDirectory(prefix="tfl-hotspot-fake-bin-") as directory:
            temp = Path(directory)
            binary = temp / "hotspot"
            invocations = temp / "invocations"
            binary.write_text(
                "#!/usr/bin/env python3\n"
                "import pathlib, sys\n"
                f"log = pathlib.Path({str(invocations)!r})\n"
                "log.write_text(str(int(log.read_text()) + 1) if log.exists() else '1')\n"
                "args = dict(zip(sys.argv[1::2], sys.argv[2::2]))\n"
                "rows, cols = int(args['-grid_rows']), int(args['-grid_cols'])\n"
                "grid = pathlib.Path(args['-grid_steady_file'])\n"
                "with grid.open('w') as out:\n"
                " for layer in range(8):\n"
                "  out.write(f'Layer {layer}:\\n')\n"
                "  for index in range(rows * cols): out.write(f'{index}\\t{300 + layer + index / 100:.2f}\\n')\n",
                encoding="utf-8",
            )
            binary.chmod(0o755)
            marker = REPO_ROOT / "sundai_tap" / f".warm-worker-integrity-{os.getpid()}"
            self.assertFalse(marker.exists())
            marker.write_text("original source\n", encoding="utf-8")
            oracle = None
            try:
                oracle = HotSpotOracle(2, 2, solver_timeout_s=3, worker_timeout_s=8, hotspot_binary=binary)
                marker_relative = marker.relative_to(REPO_ROOT).as_posix()
                oracle.problem = replace(
                    oracle.problem,
                    generator_sha256=oracle.problem.generator_sha256 + ((marker_relative, _sha256(marker)),),
                )
                design = oracle.design_from_centers(BASE_CENTERS)
                worker_pids = []
                original_evaluate = __import__("tap_oracle")._WarmWorker.evaluate

                async def track_worker(worker, request, *, worker_timeout_s):
                    worker_pids.append(worker.pid)
                    return await original_evaluate(worker, request, worker_timeout_s=worker_timeout_s)

                with mock.patch("tap_oracle._WarmWorker.evaluate", new=track_worker):
                    first = await oracle(design)
                    self.assertEqual(first.grid_rows, 2)
                    self.assertEqual(invocations.read_text(encoding="utf-8"), "1")
                    original_worker_pid = next(iter(oracle._worker_pool._workers)).pid

                    marker.write_text("modified source\n", encoding="utf-8")
                    with self.assertRaisesRegex(HotSpotOracleError, "source changed"):
                        await oracle(design)
                    self.assertEqual(worker_pids[:2], [original_worker_pid, original_worker_pid],
                                     "source check did not run in the already-warm worker")
                    self.assertEqual(invocations.read_text(encoding="utf-8"), "1", "solver ran after source tampering")
                    self.assertEqual(len(oracle._worker_pool._workers), 0)

                    marker.write_text("original source\n", encoding="utf-8")
                    await oracle(design)
                    replacement_worker_pid = next(iter(oracle._worker_pool._workers)).pid
                    self.assertNotEqual(original_worker_pid, replacement_worker_pid)
                    self.assertEqual(invocations.read_text(encoding="utf-8"), "2")

                    binary.write_text("#!/usr/bin/env python3\n# tampered binary\n", encoding="utf-8")
                    binary.chmod(0o755)
                    with self.assertRaisesRegex(HotSpotOracleError, "binary changed"):
                        await oracle(design)
                    self.assertEqual(worker_pids[-2:], [replacement_worker_pid, replacement_worker_pid],
                                     "binary check did not run in the already-warm worker")
                    self.assertEqual(invocations.read_text(encoding="utf-8"), "2", "solver ran after binary tampering")
            finally:
                if oracle is not None:
                    await oracle.aclose()
                marker.unlink(missing_ok=True)


class HotSpotGridParserTests(unittest.TestCase):
    def test_parser_returns_chip_layer_and_requires_complete_grid(self):
        with tempfile.TemporaryDirectory() as directory:
            grid = Path(directory) / "grid.steady"
            grid.write_text("".join(
                f"Layer {layer}:\n0\t{300 + layer}.0\n1\t301.0\n2\t302.0\n3\t303.0\n"
                for layer in range(8)
            ), encoding="utf-8")
            heatmap, all_peak = _parse_grid(grid, 2, 2)
            self.assertEqual(heatmap, ((304.0, 301.0), (302.0, 303.0)))
            self.assertEqual(all_peak, 307.0)

            grid.write_text("Layer 4:\n0\t304.0\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "all eight TAP layers"):
                _parse_grid(grid, 2, 2)

            complete_grid = "".join(
                f"Layer {layer}:\n0\t{300 + layer}.0\n1\t301.0\n2\t302.0\n3\t303.0\n"
                for layer in range(8)
            )
            grid.write_text(complete_grid.replace("0\t304.0", "0\t0.0", 1), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "positive Kelvin"):
                _parse_grid(grid, 2, 2)
            grid.write_text(complete_grid.replace("0\t304.0", "0\tnan", 1), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "finite number"):
                _parse_grid(grid, 2, 2)


if __name__ == "__main__":
    unittest.main()
