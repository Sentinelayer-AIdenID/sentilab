import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from sentilab_core.envelope import canonical, check_caps, digest, genesis
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
        for rows in (changed, entries[:1] + entries[2:], entries[:2] + entries[1:]):
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

    def test_canonical_matches_javascript_number_and_unicode_vectors(self):
        vectors = [{"z": 5.0, "a": 1e16, "😀": "\n\t", "\ue000": -0.0},
                   [1e-7, 1e-6, 1e20, 1e21, 1.2345678901234567, 333333333.33333329,
                    1.0, -5e-324, 0.00001230, 1.7976931348623157e308],
                   {"present": None}, {}, [True, False, "é", "𝄞"]]
        # This native JSON.stringify check is additional to the versioned aneta
        # contract vectors, which are tested when the contracts input is loaded.
        script = """let s=''; for await (const x of process.stdin) s+=x;
const c=x=>Array.isArray(x)?'['+x.map(c).join(',')+']':
x!==null&&typeof x==='object'?'{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+c(x[k])).join(',')+'}':JSON.stringify(x);
console.log(JSON.stringify(JSON.parse(s).map(c)));"""
        proc = subprocess.run(["node", "--input-type=module", "-e", script],
                              input=json.dumps(vectors), text=True, capture_output=True, check=True)
        self.assertEqual([canonical(v).decode() for v in vectors], json.loads(proc.stdout))
        self.assertNotEqual(digest({}), digest({"present": None}))
        for value in (float("inf"), 9007199254740993, "\ud800"):
            with self.assertRaises((ValueError, UnicodeError)):
                canonical(value)


if __name__ == "__main__":
    unittest.main()
