import copy
import json
from pathlib import Path
import tempfile
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from sentilab_core.envelope import build, canonical, check_caps, genesis, verify
from sentilab_core.ledger import BrokenLedger, Ledger, read_prefix, replay


class RuntimeSigner:
    """Test key generated in memory, never serialized."""
    def __init__(self):
        self._key = Ed25519PrivateKey.generate()
        self.public_key = self._key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.key_id = "test-key"

    def sign(self, value):
        return self._key.sign(value)


def run_record(run_id="test-run"):
    return dict(run_id=run_id, arm="live", family="ai-off", seed=11, ticket_id="d72c9769")


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.signer = RuntimeSigner()
        self.keys = {self.signer.key_id: self.signer.public_key}
        self.ledger = Ledger(self.temp.name, run_record(), signer=self.signer, public_keys=self.keys)

    def append(self, count=3):
        return [self.ledger.append("node.create", {"id": f"node-{i}"}, event_id=f"event-{i}")
                for i in range(count)]

    def read(self):
        return replay(self.temp.name, "test-run", public_keys=self.keys)

    def test_signature_chain_roundtrip_and_idempotent_append(self):
        entries = self.append()
        self.assertEqual(entries[0]["prev_hash"], genesis("test-run"))
        self.assertEqual(self.read()["prefix"], entries)
        self.assertEqual(self.append(), entries)
        self.assertEqual(len(self.ledger.path.read_text().splitlines()), 3)
        with self.assertRaisesRegex(ValueError, "idempotency"):
            self.ledger.append("node.create", {"id": "changed"}, event_id="event-0")

    def test_tamper_drop_repeat_and_append_refusal_at_prefix(self):
        entries = self.append(4)
        changed = copy.deepcopy(entries)
        changed[1]["event"]["body"]["id"] = "tampered"
        for rows in (changed, entries[:1] + entries[2:]):
            with self.subTest(rows=len(rows)):
                self.ledger.path.write_bytes(b"".join(canonical(e) + b"\n" for e in rows))
                state = self.read()
                self.assertTrue(state["error"])
                self.assertLess(state["last_seq"], 4)
                self.assertTrue(all(not row["projectable"] for row in state["rows"][state["last_seq"]:]))
                with self.assertRaises(BrokenLedger):
                    self.ledger.append("node.create", {}, event_id="next")
                with self.assertRaises(BrokenLedger):
                    Ledger(self.temp.name, run_record(), public_keys=self.keys)

    def test_shuffled_rows_verify_but_wrong_run_and_unpinned_key_do_not(self):
        entries = self.append()
        self.ledger.path.write_bytes(b"".join(canonical(e) + b"\n" for e in reversed(entries)))
        self.assertEqual(self.read()["prefix"], entries)
        wrong_run = read_prefix(self.ledger.path, run_id="other-run", public_keys=self.keys)
        self.assertEqual(wrong_run["last_seq"], 0)
        forged = read_prefix(self.ledger.path, run_id="test-run",
                             public_keys={self.signer.key_id: RuntimeSigner().public_key})
        self.assertEqual(forged["last_seq"], 0)

    def test_partial_oversize_tail_and_path_escape(self):
        self.append(1)
        with self.ledger.path.open("ab") as handle:
            handle.write(b"x" * 66000 + b"\n")
        self.assertEqual(self.read()["last_seq"], 1)
        self.assertTrue(self.read()["error"])
        for name in ("../escape", "A", "/tmp/escape", "", None):
            with self.assertRaises(ValueError):
                Ledger(self.temp.name, run_record(name), public_keys=self.keys)

    def test_conflict_group_freezes_before_every_member_in_either_order(self):
        entries = self.append(2)
        for rows in ([entries[0], entries[0], entries[1]], [entries[1], entries[0], entries[0]]):
            self.ledger.path.write_bytes(b"".join(canonical(e) + b"\n" for e in rows))
            self.assertEqual(self.read()["last_seq"], 2)
        conflict = copy.deepcopy(entries[0])
        conflict["event"]["body"]["id"] = "different"
        for rows in ([entries[0], conflict, entries[1]], [conflict, entries[0], entries[1]]):
            self.ledger.path.write_bytes(b"".join(canonical(e) + b"\n" for e in rows))
            self.assertEqual(self.read()["last_seq"], 0)
        changed = copy.deepcopy(entries)
        changed[1]["event"]["event_id"] = changed[0]["event"]["event_id"]
        self.ledger.path.write_bytes(b"".join(canonical(e) + b"\n" for e in changed))
        self.assertEqual(self.read()["last_seq"], 0)

    def test_malformed_structure_and_depth_fail_before_recursive_hashing(self):
        for raw in (b'{"event":"bad"}\n', b'[' * 10000 + b']' * 10000 + b'\n',
                    b'{"event":{"seq":1},"event":{}}\n'):
            self.ledger.path.write_bytes(raw)
            self.assertEqual(self.read()["last_seq"], 0)
            self.assertIsNotNone(self.read()["error"])

    def test_general_append_cannot_claim_gate_authority(self):
        with self.assertRaises(TypeError):
            self.ledger.append("node.create", {}, event_id="caller", role="acceptance_gate")
        for outcome in ("accepted", "within_margin", "non_improving_current"):
            with self.assertRaisesRegex(ValueError, "core gate"):
                self.ledger.append("lifecycle.transition", {"node": "fake", "to": outcome}, event_id=outcome)

    def test_tail_loss_is_detected_against_durable_head(self):
        entries = self.append(3)
        self.ledger.path.write_bytes(b"".join(canonical(e) + b"\n" for e in entries[:2]))
        self.assertEqual(self.read()["last_seq"], 2)
        self.assertIn("head", self.read()["error"])
        with self.assertRaises(BrokenLedger):
            self.ledger.append("node.create", {"id": "next"}, event_id="next")

    def test_contract_depth_unicode_finite_and_collection_cap_vectors(self):
        root = Path(__file__).resolve().parent.parent
        vectors = json.loads((root / "contracts/view-envelope/vectors-view.json").read_text())
        for case in vectors["caps"]:
            if "build" in case:
                continue  # byte-boundary cases are constructed in the conformance job
            value = case.get("envelope", json.loads(case.get("raw", "null")))
            with self.subTest(name=case["name"]):
                if case["expect"]:
                    with self.assertRaises(ValueError):
                        check_caps(value)
                else:
                    check_caps(value)

    def test_all_size_caps_and_nonfinite_numbers(self):
        for value in ({"x": "a" * 513}, {"x" * 513: 1}, {"geometry": [{}] * 65},
                      {"center_temps": {str(i): 0 for i in range(65)}},
                      {"artifact_hashes": [""] * 65}, {"n": float("nan")},
                      {str(i): "x" * 512 for i in range(130)}):
            with self.subTest(value_type=type(value)), self.assertRaises(ValueError):
                check_caps(value)
        nested = 1
        for _ in range(9):
            nested = [nested]
        with self.assertRaises(ValueError):
            check_caps(nested)
        check_caps({"geometry": [{}] * 64, "emoji": "😀" * 512})
        with self.assertRaises(ValueError):
            self.ledger.append("node.create", {"too_big": "x" * 513}, event_id="oversize")
        self.assertFalse(self.ledger.path.exists())

    def test_invalid_structure_is_rejected_before_signer_is_called(self):
        calls = []
        sign = self.signer.sign
        self.signer.sign = lambda value: (calls.append(value), sign(value))[1]
        event = {"event_id": "new", "seq": 1, "type": "node.create",
                 "actor_role": "core", "body": {"id": "node"}}
        actor = {"agent_id": None, "life_id": None, "grant_id": None, "lab": "core"}
        for change in ({"seq": True}, {"body": []}, {"actor_role": "acceptance_gate"},
                       {"event_id": ""}, {"type": "lifecycle.transition", "body": {"to": "accepted"}}):
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    build(event=event | change, run=run_record(), actor=actor,
                          prev_hash=genesis("test-run"), signer=self.signer)
                self.assertEqual(calls, [])
        valid = build(event=event, run=run_record(), actor=actor,
                      prev_hash=genesis("test-run"), signer=self.signer)
        calls.clear()
        # The unsigned payload fits, but including hash/signature crosses 64 KiB.
        body = valid["event"]["body"]
        for i in range(130):
            body[f"padding-{i}"] = "x" * 480
        remaining = 65537 - len(canonical(valid))
        for key in list(body):
            if key.startswith("padding-"):
                add = min(remaining, 512 - len(body[key]))
                body[key] += "x" * add
                remaining -= add
        self.assertEqual(remaining, 0)
        self.assertEqual(len(canonical(valid)), 65537)
        with self.assertRaisesRegex(ValueError, "oversize"):
            build(event=valid["event"], run=valid["run"], actor=valid["actor"],
                  prev_hash=valid["prev_hash"], ts=valid["ts"], signer=self.signer)
        self.assertEqual(calls, [])

    def test_signed_envelope_does_not_alias_caller_inputs(self):
        body = {"id": "detached", "nested": {"value": 1}}
        entry = self.ledger.append("node.create", body, event_id="detached")
        body["nested"]["value"] = 2
        self.assertEqual(entry["event"]["body"]["nested"]["value"], 1)
        verify(entry, run_id="test-run", public_keys=self.keys)



if __name__ == "__main__":
    unittest.main()
