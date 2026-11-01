"""Fixtures for the door's tests. Nothing in Door.from_env or the routes ever builds one of these.

- door_manifest(): the golden CPU-DRAM draft (contracts/open-proposal-v1/golden/manifests.json "M") made `signed`
  the way the contract's own signed test manifest is: every pin an obviously fake hash, except the evaluator's binary,
  which is the gate-zero HotSpot 6.0 hash the door pins.
- TEST_KEY: an Ed25519 key derived from a public phrase. It signs test bindings only; the door's pinned operator key
  is warden's, and a binding signed with this key never verifies against it.
- FakeScorer: a deterministic stand-in for door-scorer. Its grid is a smooth sum of bumps at the die centres printed
  to 0.01 K, and its selector is computed from that grid with the door's own GRID_CENTER code, so its binding holds
  unless a mode breaks it on purpose.
"""
from __future__ import annotations

import copy
import hashlib
import json
import threading
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from open_proposals.contract.schemas import CONTRACT_DIR
from sundai_hotspot import gate0_anchor

from .policy import FloodLimits, Policy
from .scorer import EVALUATOR_BINARY_SHA256, METRIC, ScorerError, Score

TEST_PHRASE = "sentilab agent door test operator key, public, not a secret"
TEST_KEY = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(TEST_PHRASE.encode()).digest())
TEST_PUBLIC = gate0_anchor.public_key_hex(TEST_KEY)
TERMS_TEXT = "sentilab agent door test terms text: a fixture, not the published terms"
TERMS = "sentilab-open-terms/1@" + hashlib.sha256(TERMS_TEXT.encode()).hexdigest()
OTHER_TERMS = "sentilab-open-terms/2@" + hashlib.sha256(b"door other terms").hexdigest()
K_CHALLENGE = hashlib.sha256(b"sentilab agent door test k_challenge, not a secret").digest()
GRANT_ID = "slab-demo-test"
OPENS, CLOSES = "2026-11-01T00:00:00Z", "2026-11-02T00:00:00Z"
NOW = 1793500000.0          # 2026-11-01T03:06:40Z, inside the window
# The legal 0.5 mm snap of the raw CPU-DRAM reference (docs/sentilab/references/micro150-tap25d-fig5a-snap0p5.json),
# in the compact l= format: wire proxy 9.5 mm.
SNAPPED = "36.35.0,54.35.0,54.55.0,36.55.0,17.35.0,73.35.0,73.55.0,17.55.0"


def fake(label: str) -> str:
    return hashlib.sha256(("sentilab agent door fake: " + label).encode()).hexdigest()


def door_manifest(**edits) -> dict:
    golden = json.loads((CONTRACT_DIR / "golden" / "manifests.json").read_bytes())
    manifest = copy.deepcopy(golden["manifests"]["M"])
    manifest.update({"status": "signed", "version": 1})
    manifest["fixture"]["package"]["hotspot_config_sha256"] = fake("hotspot config")
    manifest["references"]["file_sha256"] = fake("reference file")
    manifest["statistic"]["evaluator"].update({"binary_sha256": EVALUATOR_BINARY_SHA256,
                                               "gate_zero_record_sha256": fake("gate zero record"),
                                               "build": "sha256:" + fake("image"), "runtime": "door-test"})
    manifest["statistic"]["numerical_admission"] = "admitted"
    manifest["wire"]["router_sha256"] = fake("router")
    manifest["policy"].update({"status": "frozen; policy choices, not uncertainty; fixed before any candidate is "
                                         "scored", "D_K": 0.5, "r": 0.05, "B_T_K": 1.0, "B_W_mm": 2.0,
                               "T_limit_C": 85, "proposed_in_draft": None})
    manifest["screen"]["scenarios"] = [{"id": "nominal", "applies_to": "both", "grid": 64},
                                       {"id": "mesh-32", "applies_to": "both", "grid": 32},
                                       {"id": "position-0-x-plus", "applies_to": "R", "grid": 64}]
    manifest["evaluation_bundle"].update({"status": "frozen", "ceilings_cpu_s": {"native.evaluate": 15}})
    manifest["checks"].update({"cleanup_headroom_s": 1, "cpu_reserve_s": 6,
                               "cpu_enforcement_evidence_sha256": fake("live CPU enforcement evidence")})
    manifest["limits"]["status"] = "frozen (test)"
    manifest["terms"] = {"accepted_versions": [TERMS], "retention": "P2Y"}
    manifest["sealing"].update({"recipient": "age1" + "q" * 58, "key_version": 1})
    manifest["example"]["inputs"] = {"W_c_mm": 9.5}
    manifest["window"] = {"opens_at": OPENS, "closes_at": CLOSES}
    manifest["refs"] = {"grant": GRANT_ID, "claim_rules": "door-test-claim-rules", "checker_sha256": fake("checker")}
    for path, value in edits.items():
        target = manifest
        keys = path.split(".")
        for key in keys[:-1]:
            target = target[key]
        target[keys[-1]] = value
    return manifest


def grant(**edits) -> dict:
    value = {"grant": GRANT_ID, "cpu_cap_s": 3600, "token_cpu_s": 30, "parallel": 4, "run_reserve_cpu_s": 10,
             "not_before": OPENS, "not_after": CLOSES, "enforcement_evidence_sha256": fake("whole-container cutoff")}
    value.update(edits)
    return value


def binding(manifest: dict, grant_value: dict, key=TEST_KEY) -> dict:
    from open_proposals.contract import canonical as hashes

    return gate0_anchor.sign(key, {"schema": "sentilab-door-binding/1", "manifest_id": hashes.manifest_id(manifest),
                                   "grant": grant_value})


class Clock:
    def __init__(self, now: float = NOW):
        self.now = now
        self._lock = threading.Lock()

    def __call__(self) -> float:
        with self._lock:
            return self.now

    def advance(self, seconds: float) -> None:
        with self._lock:
            self.now += seconds


def policy(*, clock=None, manifest=None, grant_value=None, switch="open", flood=None, signed_by=TEST_KEY,
           **limits) -> Policy:
    manifest = door_manifest() if manifest is None else manifest
    for name, value in limits.items():
        manifest["limits"][name] = value
    grant_value = grant() if grant_value is None else grant_value
    return Policy(manifest=manifest, binding=binding(manifest, grant_value, signed_by), admission_switch=switch,
                  k_challenge=K_CHALLENGE, flood=flood or FloodLimits(nonce_per_min=1000, total_per_min=100000),
                  operator_public_key=TEST_PUBLIC, clock=clock or Clock())


def grid_for(dies, offset: float = 0.0) -> list:
    """A smooth, deterministic active-layer map (C, row 0 at the top), printed to 0.01 K; offset shifts it."""
    cell = 45.0 / 64
    rows = []
    for row in range(64):
        y = 45.0 - (row + 0.5) * cell
        values = []
        for col in range(64):
            x = (col + 0.5) * cell
            total = 45.0 + offset
            for die in dies:
                power = 150.0 if die["die"] < 4 else 20.0
                dx, dy = x - die["x_um"] / 1000, y - die["y_um"] / 1000
                total += power * 0.45 / (1 + (dx * dx + dy * dy) / 30.0)
            values.append(round(total, 2))
        rows.append(values)
    return rows


class FakeScorer:
    """mode: ok | down | timeout | error | cutoff | grant_expired | mismatch | not_fresh | bad_binding | raise."""

    def __init__(self, checker, *, mode="ok", healthy=True, cpu_s=2.5, delay_s=0.0, offset=-60.0):
        self.checker, self.mode, self.healthy, self.cpu_s, self.delay_s = checker, mode, healthy, cpu_s, delay_s
        self.offset = offset
        self.calls, self.health_calls = [], 0
        self.started = threading.Event()
        self.release = None          # a threading.Event a test may set to hold a score call open

    def health(self) -> bool:
        self.health_calls += 1
        return self.healthy

    def score(self, request: dict) -> Score:
        self.calls.append(request)
        self.started.set()
        if self.release is not None:
            self.release.wait(10)
        if self.delay_s:
            time.sleep(self.delay_s)
        if self.mode == "down":
            raise ScorerError("scorer_down", began=False)
        if self.mode == "timeout":
            raise ScorerError("scorer_timeout", began=True)
        if self.mode == "error":
            raise ScorerError("scorer_error", began=True, cpu_s=40.0)
        if self.mode == "cutoff":
            raise ScorerError("scorer_cutoff", began=True, cpu_s=self.cpu_s)
        if self.mode == "grant_expired":
            raise ScorerError("grant_expired", began=True, cpu_s=0.5)
        if self.mode == "raise":
            raise RuntimeError("adapter fault")
        dies = request["dies"]
        grid = grid_for(dies, self.offset)
        selector = self.checker.selector(dies, grid)
        if self.mode == "bad_binding":
            selector += 1.0
        peak = max(max(row) for row in grid)
        return Score(selector, selector - 0.01, peak, tuple(tuple(row) for row in grid),
                     self.mode != "not_fresh", self.mode != "mismatch", self.cpu_s, EVALUATOR_BINARY_SHA256,
                     {"run_id": request["run_id"], "fake": True}, dict(METRIC))


NONCE = "0123456789abcdef"
OTHER_NONCE = "fedcba9876543210"


def nonce(index: int) -> str:
    return f"{index:016x}"


class DoorCase:
    """A mixin for unittest.TestCase: a door on a temporary store, a fake scorer and a test clock; with http=True,
    the whole app (app.main, its origin-token middleware included) served by uvicorn on a loopback port."""
    http = False

    def policy_kwargs(self) -> dict:
        return {}

    def setUp(self):
        import tempfile
        from pathlib import Path

        from .routes import configure
        from .service import Door
        from .store import Store

        self.tmp = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.policy = policy(clock=self.clock, **self.policy_kwargs())
        self.store = Store(Path(self.tmp.name) / "door.sqlite3")
        self.scorer = FakeScorer(self.policy.checker)
        self.door = Door(self.policy, self.store, self.scorer)
        self.previous_door = configure(self.door)
        self.server = None
        if self.http:
            self._serve()

    def _serve(self):
        import socket

        import uvicorn

        from app.main import app

        self.socket = socket.socket()
        self.socket.bind(("127.0.0.1", 0))
        self.port = self.socket.getsockname()[1]
        self.server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off"))
        self.thread = threading.Thread(target=self.server.run, kwargs={"sockets": [self.socket]}, daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        if not self.server.started:
            raise RuntimeError("the test server did not start")

    def tearDown(self):
        from .routes import configure

        if self.server is not None:
            self.server.should_exit = True
            self.thread.join(10)
            self.socket.close()
        self.door.stop()
        configure(self.previous_door)
        self.tmp.cleanup()

    def body(self, layout=SNAPPED, *, nonce_value=NONCE, exp=None, **edits) -> dict:
        claims = {"purpose": "place-chiplets", "case": "cpu-dram", "nonce": nonce_value,
                  "exp": int(self.clock()) + 600 if exp is None else exp}
        value = {"token_claims": claims, "layout": layout, "terms": TERMS, "class": "declared_agent",
                 "operator": "openai"}
        value.update(edits)
        return value

    def request(self, method: str, path: str, data: bytes | None = None, headers=None) -> tuple:
        """(status, parsed JSON or None, response headers) over real HTTP."""
        import urllib.error
        import urllib.request

        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, method=method,
                                         headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw, status, got = response.read(), response.status, dict(response.headers)
        except urllib.error.HTTPError as error:
            raw, status, got = error.read(), error.code, dict(error.headers)
        return status, (json.loads(raw) if raw else None), {key.lower(): value for key, value in got.items()}

    def submit(self, value) -> tuple:
        """(status, body) through HTTP when serving, else through the service directly."""
        raw = value if isinstance(value, bytes) else json.dumps(value).encode("utf-8")
        if self.http:
            status, body, _headers = self.request("POST", "/api/open/v1/door/submit", raw,
                                                  {"content-type": "application/json"})
            return status, body
        status, body, _headers = self.door.submit(raw)
        return status, body

    def drain(self, limit: int = 100) -> int:
        """Run queued attempts on this thread until none is claimable."""
        count = 0
        while count < limit and self.door.dispatcher.run_once():
            count += 1
        return count

    def codes(self, body) -> list:
        return [item["code"] for item in body["codes"]]
