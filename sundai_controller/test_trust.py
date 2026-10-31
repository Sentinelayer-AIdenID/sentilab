"""Exercise real signing, experiment entry points and trust verification with runtime keys."""
import asyncio
import base64
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

if __package__:
    from .controller import Chiplet, Design, FlightRecord, ThermalResult, canonical, public_hex
    from .experiment import run_four_lanes
    from .trust import certify_lane, inspect_record, key_id_for, load_service_key, verify_chain
else:
    from controller import Chiplet, Design, FlightRecord, ThermalResult, canonical, public_hex
    from experiment import run_four_lanes
    from trust import certify_lane, inspect_record, key_id_for, load_service_key, verify_chain

ROOT = Path(__file__).resolve().parents[1]


class Oracle:
    def __init__(self):
        self.calls = 0

    async def __call__(self, design):
        self.calls += 1
        return ThermalResult(design.hash, float(sum(x + y for x, y in design.positions)),
                             "NONPHYSICAL-trust-test", problem_hash="trust-test")


def design():
    return Design(20, 10, 1, (Chiplet("a", 2, 2), Chiplet("b", 2, 2)), ((4, 1), (12, 1)))


def fixtures():
    """Public-only artifacts for both verifiers; private material never leaves memory."""
    seed = os.urandom(32)
    service = Ed25519PrivateKey.from_private_bytes(seed)
    run = asyncio.run(run_four_lanes(design(), Oracle(), service_key=service, run_id="trust-run",
                                     evaluations_per_lane=1, shared_sample_count=0))
    lane = run["lane_results"]["random"]
    valid = {"run_id": run["run_id"], "lane_id": "random", "events": lane["record"],
             "record_public_key": lane["record_public_key"], "record_certificate": lane["record_certificate"]}
    cases = {}

    def changed(name):
        cases[name] = copy.deepcopy(valid)
        return cases[name]

    forged = changed("resigned-temperature")
    replacement = FlightRecord()
    for event in valid["events"][:-1]:
        payload = copy.deepcopy(event["payload"])
        if event["event"] == "baseline":
            payload["thermal"]["maximum_temperature_c"] = -100.0
        replacement.append(event["event"], **payload)
    replacement.close()
    forged.update(events=replacement.events, record_public_key=replacement.public_key)

    def recertify(name, *, root=service, run_id="trust-run", lane_id="random", expiry=None, public=None):
        doc = changed(name)
        doc["record_certificate"] = certify_lane(root, run_id, lane_id, public or lane["record_public_key"],
                                                 int(time.time()) + 3600 if expiry is None else expiry)
        return doc

    # Replacement issuer claims the trusted key_id: must fail the actual root signature check.
    other_root = Ed25519PrivateKey.from_private_bytes(os.urandom(32))
    cert = recertify("replacement-root", root=other_root)["record_certificate"]
    cert["key_id"] = key_id_for(public_hex(service))
    cert["signature"] = base64.b64encode(other_root.sign(canonical(
        {k: v for k, v in cert.items() if k != "signature"}))).decode()
    cert = changed("unknown-key-id")["record_certificate"]
    cert["key_id"] = "unknown-service"
    cert["signature"] = base64.b64encode(service.sign(canonical(
        {k: v for k, v in cert.items() if k != "signature"}))).decode()
    recertify("wrong-run", run_id="another-run")
    recertify("wrong-lane", lane_id="ucb1")
    recertify("expired", expiry=int(time.time()) - 1)
    recertify("identity-key-instead-of-record-key", public=lane["identity_public_key"])
    altered = changed("altered-payload")
    next(e for e in altered["events"] if e["event"] == "baseline")["payload"]["thermal"]["maximum_temperature_c"] = -100.0
    changed("altered-certificate")["record_certificate"]["run_id"] = "edited-run"
    changed("null-certificate")["record_certificate"] = None
    changed("extra-certificate-field")["record_certificate"]["root"] = public_hex(other_root)
    changed("boolean-expiry")["record_certificate"]["expires_at"] = True
    changed("unknown-version")["record_certificate"]["version"] = "unknown"
    changed("wrong-run-label")["run_id"] = "other-run"
    changed("wrong-lane-label")["lane_id"] = "ucb1"
    for name, corrupt in (
        ("leading-whitespace", lambda s: " " + s),
        ("interior-whitespace", lambda s: s[:8] + "\t" + s[8:]),
        ("trailing-newline", lambda s: s + "\n"),
        ("trailing-whitespace", lambda s: s + "\r\n"),
        ("missing-padding", lambda s: s.rstrip("=")),
        ("excess-padding", lambda s: s + "="),
        ("interior-padding", lambda s: s[:8] + "=" + s[8:]),
        ("non-alphabet", lambda s: "*" + s[1:]),
        ("non-ascii", lambda s: "\u00a0" + s),
        ("non-string", lambda s: None),
    ):
        for target in ("certificate", "event"):
            doc = changed(f"{target}-signature-{name}")
            signed = doc["record_certificate"] if target == "certificate" else doc["events"][0]
            signed["signature"] = corrupt(signed["signature"])
    legacy = copy.deepcopy(valid)
    del legacy["record_certificate"]
    unicode_keys = copy.deepcopy(valid)
    record = FlightRecord()
    for event in valid["events"][:-1]:
        payload = copy.deepcopy(event["payload"])
        if event["event"] == "baseline":
            payload["metadata"] = {"\U0001f600": "astral", "\ue000": "BMP",
                                   "prefix": {"a\U0001f600": 1, "a\ue000": 2, "a": 3}}
        record.append(event["event"], **payload)
    record.close()
    unicode_keys.update(events=record.events, record_public_key=record.public_key,
                        record_certificate=certify_lane(service, "trust-run", "random", record.public_key,
                                                        int(time.time()) + 3600))
    replays = {}
    for name, age in (("25-hours", 25 * 60 * 60), ("31-days", 31 * 24 * 60 * 60)):
        # Age the real producer and its signed events, then verify with the current clock.
        with patch("time.time", return_value=time.time() - age):
            replay = asyncio.run(run_four_lanes(design(), Oracle(), service_key=service, run_id="trust-run",
                                                evaluations_per_lane=1, shared_sample_count=0))
        lane = replay["lane_results"]["random"]
        replays[name] = {"run_id": replay["run_id"], "lane_id": "random", "events": lane["record"],
                         "record_public_key": lane["record_public_key"],
                         "record_certificate": lane["record_certificate"]}
    return {"pins": {key_id_for(public_hex(service)): public_hex(service)},
            "run": run, "valid": valid, "legacy": legacy, "cases": cases, "replays": replays,
            "unicode_keys": unicode_keys}


class TrustTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = fixtures()

    def inspect(self, doc, pins=None):
        return inspect_record(doc["events"], doc["record_public_key"], doc.get("record_certificate"),
                              self.data["pins"] if pins is None else pins,
                              run_id=doc["run_id"], lane_id=doc["lane_id"])

    def test_real_experiment_certifies_every_record_key(self):
        for lane_id, lane in self.data["run"]["lane_results"].items():
            with self.subTest(lane=lane_id):
                self.assertNotEqual(lane["identity_public_key"], lane["record_public_key"])
                self.assertEqual(lane["record_certificate"]["lane_public_key"], lane["record_public_key"])
                self.assertTrue(verify_chain(lane["record"], lane["record_certificate"], self.data["pins"],
                                             run_id="trust-run", lane_id=lane_id))
        self.assertEqual(self.inspect(self.data["valid"]), {"integrity": True, "authentic": True,
                                                          "origin": "authentic", "scientific_validity": "not checked"})

    def test_attacks_fail_in_shipped_verifier(self):
        for name, doc in self.data["cases"].items():
            with self.subTest(attack=name):
                self.assertFalse(self.inspect(doc)["authentic"])
                self.assertFalse(verify_chain(doc["events"], doc.get("record_certificate"), self.data["pins"],
                                              run_id=doc["run_id"], lane_id=doc["lane_id"]))
        self.assertTrue(self.inspect(self.data["cases"]["resigned-temperature"])["integrity"],
                        "forgery is correctly signed by an unauthorized replacement key")
        self.assertFalse(self.inspect(self.data["cases"]["altered-payload"])["integrity"])

    def test_unicode_metadata_keys_authenticate(self):
        self.assertTrue(self.inspect(self.data["unicode_keys"])["authentic"])

    def test_legacy_is_integrity_only(self):
        self.assertEqual(self.inspect(self.data["legacy"]), {"integrity": True, "authentic": False,
                                                           "origin": "unanchored", "scientific_validity": "not checked"})

    def test_pins_are_external_and_removal_revokes(self):
        doc = copy.deepcopy(self.data["valid"])
        doc["pinned_service_keys"] = self.data["pins"]
        self.assertFalse(verify_chain(doc["events"], doc["record_certificate"]))
        self.assertFalse(self.inspect(doc, {})["authentic"])
        self.assertTrue(self.inspect(doc)["authentic"])
        # Rotation supports multiple explicitly pinned issuers, never automatic trust from a file.
        other = Ed25519PrivateKey.from_private_bytes(os.urandom(32))
        pins = {**self.data["pins"], key_id_for(public_hex(other)): public_hex(other)}
        doc["record_certificate"] = certify_lane(other, "trust-run", "random", doc["record_public_key"],
                                                  int(time.time()) + 3600)
        self.assertTrue(self.inspect(doc, pins)["authentic"])
        self.assertFalse(self.inspect(doc)["authentic"])

    def test_expiry_boundary_uses_verifier_clock(self):
        doc = self.data["valid"]
        expiry = doc["record_certificate"]["expires_at"]
        self.assertTrue(verify_chain(doc["events"], doc["record_certificate"], self.data["pins"], now=expiry - 1))
        self.assertFalse(verify_chain(doc["events"], doc["record_certificate"], self.data["pins"], now=expiry))

    def test_25_hour_replay_remains_authentic(self):
        self.assertEqual(self.inspect(self.data["replays"]["25-hours"]),
                         {"integrity": True, "authentic": True, "origin": "authentic",
                          "scientific_validity": "not checked"})

    def test_31_day_replay_is_expired(self):
        self.assertEqual(self.inspect(self.data["replays"]["31-days"]),
                         {"integrity": True, "authentic": False, "origin": "invalid",
                          "scientific_validity": "not checked"})

    def test_library_takes_explicit_signer_without_environment(self):
        env = os.environ.copy()
        env.pop("FLIGHT_SIGNING_SEED_B64", None)
        oracle = Oracle()
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(ValueError, "service_key"):
                asyncio.run(run_four_lanes(design(), oracle, service_key=None))
            self.assertEqual(oracle.calls, 0)
            service = Ed25519PrivateKey.from_private_bytes(os.urandom(32))
            run = asyncio.run(run_four_lanes(design(), oracle, service_key=service, evaluations_per_lane=1,
                                            shared_sample_count=0))
            self.assertTrue(run["flight_records_valid"])

    def test_seed_loader_reuses_configured_service_key(self):
        seed = os.urandom(32)
        with patch.dict(os.environ, {"FLIGHT_SIGNING_SEED_B64": base64.b64encode(seed).decode()}):
            expected = public_hex(Ed25519PrivateKey.from_private_bytes(seed))
            self.assertEqual(public_hex(load_service_key()), expected)
            self.assertEqual(public_hex(load_service_key()), expected)

    def test_api_records_chain_to_configured_seed(self):
        from app import runs

        seed = os.urandom(32)
        encoded = base64.b64encode(seed).decode()
        public = public_hex(Ed25519PrivateKey.from_private_bytes(seed))
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"RUNS_DIR": directory, "FLIGHT_SIGNING_SEED_B64": encoded}):
                started = runs.start({"benchmark": "plate", "grid": 16, "proposals": 1})
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    text = runs.get(started["id"])
                    record = json.loads(text)
                    if record["status"] != "running":
                        break
                    time.sleep(0.01)
                self.assertEqual(record["status"], "done", record.get("error"))
                self.assertTrue(encoded not in text, "private signing material must not be persisted")
                for lane_id, lane in record["result"]["lane_results"].items():
                    self.assertTrue(verify_chain(lane["record"], lane["record_certificate"], public,
                                                 run_id=started["id"], lane_id=lane_id))

    def test_missing_or_malformed_seed_stops_real_entry_points(self):
        from app import runs

        for seed in (None, "", "not base64!", "non-ascii-ü", *(base64.b64encode(os.urandom(n)).decode() for n in (31, 33))):
            with self.subTest(case="missing" if seed is None else "malformed"):
                env = os.environ.copy()
                env.pop("FLIGHT_SIGNING_SEED_B64", None)
                if seed is not None:
                    env["FLIGHT_SIGNING_SEED_B64"] = seed
                with tempfile.TemporaryDirectory() as directory:
                    env["RUNS_DIR"] = directory
                    with patch.dict(os.environ, env, clear=True):
                        with self.assertRaisesRegex(ValueError, "FLIGHT_SIGNING_SEED_B64"):
                            runs.start({"benchmark": "plate"})
                    self.assertEqual(list(Path(directory).iterdir()), [])
                    for command in (["tfl05_smoke.py", "--benchmark", "plate"],
                                    ["tfl08_leaderboard.py", "--out", directory]):
                        result = subprocess.run([sys.executable, str(ROOT / "sundai_controller" / command[0]),
                                                 *command[1:]], cwd=directory, env=env,
                                                capture_output=True, text=True, timeout=30)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("FLIGHT_SIGNING_SEED_B64", result.stderr)
                        self.assertEqual(result.stdout, "")
                        self.assertEqual(list(Path(directory).iterdir()), [])



if __name__ == "__main__":
    if sys.argv[1:] == ["--fixtures"]:
        print(json.dumps(fixtures()))
    else:
        unittest.main()
