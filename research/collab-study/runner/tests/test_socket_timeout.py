"""Exercise ambiguous transport failures through an actual local socket."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import sys
import threading

import pytest


RUNNER = Path(__file__).resolve().parents[1] / "study_runner.py"
spec = importlib.util.spec_from_file_location("socket_timeout_runner", RUNNER)
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)


@pytest.fixture
def stalled_endpoint():
    received = []
    release = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(self.rfile.read(int(self.headers["Content-Length"])))
            release.wait(5)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/chat/completions", received
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_real_read_timeout_has_no_retry_and_retains_reserved_charge(stalled_endpoint, monkeypatch):
    endpoint, received = stalled_endpoint
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    real_post = runner.requests.Session.post
    transport_errors = []

    def post(session, url, **kwargs):
        # Keep the real socket read timeout shorter than the whole-call deadline.
        kwargs["timeout"] = (1, 0.05)
        try:
            return real_post(session, url, **kwargs)
        except runner.requests.ReadTimeout as error:
            transport_errors.append(type(error))
            raise

    monkeypatch.setattr(runner.requests.Session, "post", post)
    model = runner.HTTPModel("https://provider.invalid/chat/completions", "test-only")
    # The loopback fixture needs neither a provider nor TLS private-key files.
    model.endpoint = endpoint
    ledger = runner.Ledger("1", {"input": "1", "cached_input": "0.5", "output": "2"})
    agent = runner.AgentState(1, 1000, 100)
    sleeps, records = [], []
    engine = runner.RequestEngine(model, ledger, max_tokens_per_reply=50,
                                  clock=lambda: 0, sleep=sleeps.append)

    assert engine.request("timeout-job", agent, [{"role": "user", "content": "packet"}],
                          deadline=30, scope="study", record=records.append) is None

    assert transport_errors == [runner.requests.ReadTimeout]
    assert len(received) == 1
    assert json.loads(received[0])["max_tokens"] == 50
    assert sleeps == []
    assert agent.retried is False
    assert agent.stop_reason == "transport_unknown"
    assert agent.charged_tokens == 150
    assert agent.unknown_usage_attempts == 1
    report = ledger.report()
    assert len(report["attempts"]) == 1
    attempt = report["attempts"][0]
    assert attempt["state"] == "failed"
    assert attempt["usage"] is None
    assert attempt["unknown_usage"] is True
    assert attempt["charged_usd"] == attempt["reserved_usd"] == "0.0002"
    assert report["grand_total_usd"] == "0.0002"
    assert report["reserved_usd"] == "0"
    assert [row["event"] for row in records] == ["request", "failure"]
    assert records[-1]["failure"] == "transport_unknown"
