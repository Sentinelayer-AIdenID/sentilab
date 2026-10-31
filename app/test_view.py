"""Real HTTP requests against the registered FastAPI view routes."""
import json
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import errno
import fcntl
import os
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen
from pathlib import Path

import uvicorn

from app.main import app
from app import view
from sentilab_core.envelope import build, canonical, genesis
from sentilab_core.operations import Context
from sentilab_core.test_ledger import RuntimeSigner, run_record
from sentilab_core.test_history import signed_version
from sentilab_core.test_conductor import PlateOracle
from sentilab_core.budget import Limits
from sentilab_core.conductor import Conductor
from sentilab_core.ledger import lock


class ViewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.signer = RuntimeSigner()
        self.prior = view._context
        view.configure(Context(self.root, {self.signer.key_id: self.signer.public_key}))
        self.socket = socket.socket()
        self.socket.bind(("127.0.0.1", 0))
        self.port = self.socket.getsockname()[1]
        self.server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off"))
        self.thread = threading.Thread(target=self.server.run, kwargs={"sockets": [self.socket]}, daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 5
        while not self.server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(self.server.started)

    def tearDown(self):
        self.server.should_exit = True
        self.thread.join(5)
        self.socket.close()
        view.configure(self.prior)
        self.temp.cleanup()

    def seed_run(self, name, count):
        previous, rows = genesis(name), []
        for i in range(1, count + 1):
            envelope = build(event={"event_id": f"{name}-{i}", "seq": i, "type": "node.create",
                                    "actor_role": "core", "body": {"id": f"node-{i}", "kind": "source"}},
                             run=run_record(name), actor={"agent_id": None, "life_id": None,
                                                        "grant_id": None, "lab": "core"},
                             prev_hash=previous, signer=self.signer)
            rows.append(envelope)
            previous = envelope["hash"]
        (self.root / f"{name}.jsonl").write_bytes(b"".join(canonical(row) + b"\n" for row in rows))
        return rows

    def get(self, route):
        if route.startswith("/api/view/events?"):
            route += "&format=json"
        with urlopen(f"http://127.0.0.1:{self.port}" + route, timeout=10) as response:
            return json.load(response)

    def test_jsonl_is_default_and_pages_at_256_lines(self):
        self.seed_run("jsonl", 257)
        with urlopen(f"http://127.0.0.1:{self.port}/api/view/events?run_id=jsonl", timeout=10) as response:
            self.assertIn("application/x-ndjson", response.headers["content-type"])
            lines = response.read().splitlines()
            self.assertEqual(len(lines), 256)
            self.assertEqual(response.headers["x-next-after"], "256")
        self.assertEqual([json.loads(line)["event"]["seq"] for line in lines], list(range(1, 257)))
        with urlopen(f"http://127.0.0.1:{self.port}/api/view/events?run_id=jsonl&after=256", timeout=10) as response:
            self.assertEqual(json.loads(response.read())["event"]["seq"], 257)

    def test_jsonl_byte_cap_is_inclusive_and_sequence_conflicts_never_split(self):
        rows = self.seed_run("bytes", 66)
        self.root.joinpath("bytes.jsonl").write_bytes(b"".join(
            canonical(row).ljust(65535, b" ") + b"\n" for row in rows))
        with urlopen(f"http://127.0.0.1:{self.port}/api/view/events?run_id=bytes", timeout=10) as response:
            data = response.read()
            self.assertEqual(len(data), 4 * 1024 * 1024)
            self.assertEqual(len(data.splitlines()), 64)
            self.assertEqual(response.headers["x-next-after"], "64")
        rows = self.seed_run("conflict-page", 256)
        changed = json.loads(json.dumps(rows[-1]))
        changed["event"]["body"]["id"] = "conflicting-node"
        with self.root.joinpath("conflict-page.jsonl").open("ab") as handle:
            handle.write(canonical(changed) + b"\n")
        with urlopen(f"http://127.0.0.1:{self.port}/api/view/events?run_id=conflict-page", timeout=10) as response:
            self.assertEqual(len(response.read().splitlines()), 255)
            self.assertEqual(response.headers["x-next-after"], "255")
        with urlopen(f"http://127.0.0.1:{self.port}/api/view/events?run_id=conflict-page&after=256", timeout=10) as response:
            # The previously seen cursor rewinds to deliver both conflicting rows.
            self.assertEqual([json.loads(line)["event"]["seq"] for line in response.read().splitlines()], [256, 256])

    def test_routes_isolate_runs_page_by_seq_and_cap_at_256(self):
        self.seed_run("first", 257)
        self.seed_run("other", 2)
        listed = self.get("/api/view/runs")["runs"]
        self.assertEqual({r["run_id"] for r in listed}, {"first", "other"})
        first = self.get("/api/view/events?run_id=first&after=0")
        self.assertEqual(len(first["envelopes"]), 256)
        self.assertTrue(first["has_more"])
        self.assertEqual(first["next_after"], 256)
        last = self.get("/api/view/events?run_id=first&after=256")
        self.assertEqual([e["event"]["seq"] for e in last["envelopes"]], [257])
        self.assertTrue(all(e["run"]["run_id"] == "first" for e in first["envelopes"] + last["envelopes"]))
        for query, code in (("run_id=first&limit=257", 400), ("run_id=first&after=-1", 400),
                            ("run_id=missing", 404), ("run_id=..%2Foutside", 400)):
            with self.assertRaises(HTTPError) as caught:
                self.get("/api/view/events?" + query)
            self.assertEqual(caught.exception.code, code)

    def test_deleted_envelope_freezes_http_projection_at_prefix(self):
        rows = self.seed_run("broken", 10)
        (self.root / "broken.jsonl").write_bytes(b"".join(canonical(row) + b"\n" for row in rows[:6] + rows[7:]))
        response = self.get("/api/view/events?run_id=broken&after=0")
        self.assertEqual(response["prefix_end"], 6)
        self.assertIsNotNone(response["chain_error"])
        self.assertEqual(set(response["projection"]["nodes"]), {f"node-{i}" for i in range(1, 7)})
        self.assertEqual(len(response["envelopes"]), 9)

    def test_only_operator_pinned_key_verifies_and_malformed_rows_are_reported(self):
        self.seed_run("forged", 1)
        key = self.get("/api/view/key")["keys"][0]
        self.assertEqual(key["public_key"], self.signer.public_key.hex())
        view.configure(Context(self.root, {self.signer.key_id: RuntimeSigner().public_key}))
        response = self.get("/api/view/events?run_id=forged&after=0")
        self.assertEqual(response["prefix_end"], 0)
        self.assertIsNone(response["board"])
        self.assertIsNotNone(response["chain_error"])
        (self.root / "bad.jsonl").write_bytes(b"[" * 10000 + b"\n")
        response = self.get("/api/view/events?run_id=bad&after=0")
        self.assertEqual(response["unrenderable_rows"], 1)
        self.assertEqual(response["prefix_end"], 0)
        for number in ("NaN", "Infinity", "1e999"):
            (self.root / "bad.jsonl").write_text(
                '{"run":{"run_id":"bad"},"event":{"seq":1,"body":{"J":' + number + '}}}\n')
            response = self.get("/api/view/events?run_id=bad&after=0")
            self.assertEqual(response["unrenderable_rows"], 1)
            self.assertEqual(response["prefix_end"], 0)

    def test_unknown_version_and_bom_freeze_diagnostics_and_preserve_raw_feed(self):
        current = self.seed_run("profile", 1)[0]
        unknown = signed_version(current, "unrecognized/999", self.signer)
        for raw in (canonical(unknown) + b"\n", b"\xef\xbb\xbf" + canonical(current) + b"\n"):
            with self.subTest(bom=raw.startswith(b"\xef\xbb\xbf")):
                (self.root / "profile.jsonl").write_bytes(raw)
                diagnostic = self.get("/api/view/events?run_id=profile&cursor=0")
                self.assertEqual(diagnostic["prefix_end"], 0)
                self.assertIsNotNone(diagnostic["chain_error"])
                with urlopen(f"http://127.0.0.1:{self.port}/api/view/events?run_id=profile&cursor=0",
                             timeout=10) as response:
                    self.assertEqual(response.read(), raw)

    def test_service_starts_without_post_and_graceful_restart_keeps_progress(self):
        oracle = asyncio.run(PlateOracle().initialize())
        ctx = Context(self.root, {self.signer.key_id: self.signer.public_key}, self.signer,
                      {"oracle": oracle, "fixture": "synthetic-test", "limits": Limits(evals_per_run=12)})
        view.configure(ctx)
        old = os.environ.get("SENTILAB_LIVE_ENABLED")
        os.environ["SENTILAB_LIVE_ENABLED"] = "1"
        try:
            # Invoke the actual startup hook registered on the FastAPI router;
            # progress is observed over the real server's GET routes.
            view.start_live_service()
            deadline = time.monotonic() + 10
            first = None
            while time.monotonic() < deadline:
                runs = self.get("/api/view/runs")["runs"]
                if runs:
                    result = self.get("/api/view/events?run_id=" + runs[0]["run_id"])
                    if result["board"]:
                        first = result
                        break
                time.sleep(0.02)
            self.assertIsNotNone(first)
            view.stop_live_service()
            self.assertFalse((self.root / "STOP").exists(), "ordinary restart must not persist operator STOP")
            view.start_live_service()
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                result = self.get("/api/view/events?run_id=" + first["run_id"])
                if result["prefix_end"] > first["prefix_end"]:
                    break
                time.sleep(0.02)
            self.assertGreater(result["prefix_end"], first["prefix_end"])
        finally:
            view.stop_live_service()
            if old is None:
                os.environ.pop("SENTILAB_LIVE_ENABLED", None)
            else:
                os.environ["SENTILAB_LIVE_ENABLED"] = old

    @contextmanager
    def live_context(self):
        oracle = asyncio.run(PlateOracle().initialize())
        original_root = self.root
        # Independent failure scenarios must not resume a prior scenario's run
        # and wait for its normal 15-second proposal interval.
        with tempfile.TemporaryDirectory(dir=original_root) as directory:
            self.root = Path(directory)
            try:
                ctx = Context(self.root, {self.signer.key_id: self.signer.public_key}, self.signer,
                              {"oracle": oracle, "fixture": "synthetic-test", "limits": Limits(evals_per_run=12)})
                view.configure(ctx)
                with patch.dict(os.environ, SENTILAB_LIVE_ENABLED="1"), \
                        patch.object(view, "_failure", None), \
                        patch.object(view, "_last_failure_at", None, create=True):
                    try:
                        yield ctx
                    finally:
                        view.stop_live_service()
            finally:
                self.root = original_root

    def wait_for_board(self):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            listed = self.get("/api/view/runs")
            for run in listed["runs"]:
                result = self.get("/api/view/events?run_id=" + run["run_id"])
                if result["board"] and view.context().options["oracle"].calls >= 2:
                    return listed
            time.sleep(0.01)
        self.fail("service did not produce a board after retry")

    def test_service_recovers_from_cifs_owner_lock_contention(self):
        real_flock = fcntl.flock
        attempts = []
        contended = threading.Event()

        def cifs_flock(handle, flags):
            try:
                return real_flock(handle, flags)
            except BlockingIOError:
                if Path(handle.name) != self.root / "owner.lock" or not flags & fcntl.LOCK_NB:
                    raise
                attempts.append(flags)
                if len(attempts) >= 2:
                    contended.set()
                raise PermissionError(errno.EACCES, "simulated CIFS lock contention") from None

        with self.live_context(), patch("sentilab_core.ledger.fcntl.flock", side_effect=cifs_flock), \
                patch("random.uniform", return_value=0.01):
            with lock(self.root / "owner.lock"):
                view.start_live_service()
                self.assertTrue(contended.wait(2), "held CIFS lock was not retried")
                status = self.get("/api/view/runs")
                self.assertTrue(status["loop_alive"])
                self.assertIsNone(status["service_error"])
                self.assertIsNone(status["last_failure_at"])
                self.assertEqual(status["runs"], [])
            status = self.wait_for_board()
            self.assertTrue(status["loop_alive"])
            self.assertIsNone(status["service_error"])

    def test_service_records_and_retries_errors_inside_the_owner_lock(self):
        real_open_run = Conductor.open_run
        # EACCES/EAGAIN after acquisition must not be mistaken for contention.
        for error in (ValueError("unexpected run error"), PermissionError(errno.EACCES, "run denied"),
                      BlockingIOError(errno.EAGAIN, "unrelated operation busy")):
            with self.subTest(error=type(error).__name__), self.live_context(), \
                    patch("random.uniform", return_value=0.01):
                attempts = []

                def open_run(conductor, run_id=None):
                    attempts.append(run_id)
                    if len(attempts) == 1:
                        raise error
                    return real_open_run(conductor, run_id)

                before = datetime.now(timezone.utc)
                with patch.object(Conductor, "open_run", open_run):
                    view.start_live_service()
                    deadline = time.monotonic() + 2
                    while len(attempts) < 2 and time.monotonic() < deadline:
                        time.sleep(0.01)
                    self.assertGreaterEqual(len(attempts), 2, "unexpected failure was not retried")
                    status = self.wait_for_board()
                    self.assertEqual(status["service_error"], type(error).__name__)
                    self.assertTrue(status["loop_alive"])
                    failed_at = datetime.fromisoformat(status["last_failure_at"])
                    self.assertGreaterEqual(failed_at, before)
                    self.assertLessEqual(failed_at, datetime.now(timezone.utc))
                    view.stop_live_service()
                    self.assertFalse(self.get("/api/view/runs")["loop_alive"])

    def test_service_records_non_contention_errors_opening_or_acquiring_owner_lock(self):
        import builtins
        for target, original, error in (
                ("builtins.open", builtins.open, PermissionError(errno.EACCES, "cannot open lock file")),
                ("sentilab_core.ledger.fcntl.flock", fcntl.flock, OSError(errno.EIO, "lock I/O failure"))):
            with self.subTest(target=target), self.live_context(), patch("random.uniform", return_value=0.01):
                attempts = []

                def fail_once(first, *args, **kwargs):
                    path = first if target == "builtins.open" else first.name
                    if isinstance(path, (str, Path)) and Path(path) == self.root / "owner.lock":
                        attempts.append(path)
                        if len(attempts) == 1:
                            raise error
                    return original(first, *args, **kwargs)

                with patch(target, side_effect=fail_once):
                    view.start_live_service()
                    deadline = time.monotonic() + 2
                    while len(attempts) < 2 and time.monotonic() < deadline:
                        time.sleep(0.01)
                    self.assertGreaterEqual(len(attempts), 2, "storage failure was not retried")
                    status = self.wait_for_board()
                    self.assertEqual(status["service_error"], type(error).__name__)
                    self.assertIsNotNone(status["last_failure_at"])

    def test_service_backoff_is_bounded_and_stop_prevents_another_attempt(self):
        delays = []

        def fast_delay(low, high):
            delays.append((low, high))
            return 0.01

        async def failing_run(ctx, **kwargs):
            if len(delays) == 8:
                (ctx.root / "STOP").touch()
            raise RuntimeError("persistent failure")

        with self.live_context(), patch("app.view.operations.run", side_effect=failing_run) as run, \
                patch("random.uniform", side_effect=fast_delay):
            view.start_live_service()
            view._thread.join(2)
            self.assertFalse(view._thread.is_alive())
            self.assertEqual(run.call_count, 9)
            self.assertEqual(len(delays), 9)
            self.assertEqual(delays[0], (5, 5))
            self.assertEqual(delays[-1][1], 60)
            self.assertTrue(all(5 <= low <= high <= 60 for low, high in delays))
            self.assertGreater(delays[1][1], delays[0][1])
            self.assertLess(delays[-1][0], delays[-1][1], "jitter must remain at the cap")
            status = self.get("/api/view/runs")
            self.assertFalse(status["loop_alive"])
            self.assertEqual(status["service_error"], "RuntimeError")

    def test_service_shutdown_interrupts_lock_retry_wait(self):
        with self.live_context(), lock(self.root / "owner.lock"):
            view.start_live_service()
            time.sleep(0.1)
            self.assertTrue(view._thread.is_alive(), "lock contention killed the loop")
            before = time.monotonic()
            view.stop_live_service()
            self.assertLess(time.monotonic() - before, 2, "shutdown waited for the backoff")
            self.assertFalse(view._thread.is_alive())
            status = self.get("/api/view/runs")
            self.assertFalse(status["loop_alive"])
            self.assertIsNone(status["service_error"])
            self.assertEqual(status["runs"], [])


if __name__ == "__main__":
    unittest.main()
