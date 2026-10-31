"""Real HTTP requests against the registered FastAPI view routes."""
import json
import socket
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen
from pathlib import Path

import uvicorn

from app.main import app
from app import view
from sentilab_core.envelope import build, canonical, genesis
from sentilab_core.operations import Context
from sentilab_core.test_ledger import RuntimeSigner, run_record


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
        with urlopen(f"http://127.0.0.1:{self.port}" + route, timeout=10) as response:
            return json.load(response)

    def test_routes_isolate_runs_page_by_seq_and_cap_at_500(self):
        self.seed_run("first", 501)
        self.seed_run("other", 2)
        listed = self.get("/api/view/runs")["runs"]
        self.assertEqual({r["run_id"] for r in listed}, {"first", "other"})
        first = self.get("/api/view/events?run_id=first&after=0")
        self.assertEqual(len(first["envelopes"]), 500)
        self.assertTrue(first["has_more"])
        self.assertEqual(first["next_after"], 500)
        last = self.get("/api/view/events?run_id=first&after=500")
        self.assertEqual([e["event"]["seq"] for e in last["envelopes"]], [501])
        self.assertTrue(all(e["run"]["run_id"] == "first" for e in first["envelopes"] + last["envelopes"]))
        for query, code in (("run_id=first&limit=501", 422), ("run_id=first&after=-1", 422),
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


if __name__ == "__main__":
    unittest.main()
