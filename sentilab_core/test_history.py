"""Signed history stays versioned and JSONL has one explicit UTF-8 boundary."""
import copy
import unittest

from sentilab_core.envelope import canonical, digest, verify
from sentilab_core.ledger import BrokenLedger, read_prefix
from sentilab_core import test_ledger


def signed_version(envelope, version, signer):
    value = copy.deepcopy(envelope)
    value["v"] = version
    value["hash"] = digest({k: v for k, v in value.items() if k not in ("hash", "sig")})
    value["sig"]["value"] = signer.sign(value["hash"].encode()).hex()
    return value


class HistoryTests(unittest.TestCase):
    setUp = test_ledger.LedgerTests.setUp
    append = test_ledger.LedgerTests.append

    def read(self, **options):
        return read_prefix(self.ledger.path, run_id="test-run", public_keys=self.keys, **options)

    def test_unknown_signed_versions_freeze_replay_and_refuse_append(self):
        current = self.append(1)[0]
        self.ledger.head_path.unlink()  # Imported history has no durable writer head.
        for version in ("unrecognized/999", "", "view-envelope/0.50", "view-envelope/0.6"):
            with self.subTest(version=version):
                value = signed_version(current, version, self.signer)
                self.ledger.path.write_bytes(canonical(value) + b"\n")
                state = self.read()
                self.assertEqual(state["last_seq"], 0)
                self.assertIn("version", state["error"])
                with self.assertRaisesRegex(ValueError, "version"):
                    verify(value, run_id="test-run", public_keys=self.keys)
                with self.assertRaises(BrokenLedger):
                    self.ledger.append("node.create", {"id": "next"}, event_id="next")

    def test_supported_history_profiles_preserve_signed_bytes(self):
        current = self.append(1)[0]
        for version in ("view-envelope/0.4", "view-envelope/0.5"):
            with self.subTest(version=version):
                value = signed_version(current, version, self.signer)
                raw = canonical(value) + b"\n"
                self.ledger.path.write_bytes(raw)
                self.assertEqual(self.read()["prefix"], [value])
                self.assertEqual(self.read(version=version)["prefix"], [value])
                other = "view-envelope/0.5" if version.endswith("0.4") else "view-envelope/0.4"
                self.assertEqual(self.read(version=other)["last_seq"], 0)
                with self.assertRaisesRegex(ValueError, "version"):
                    verify(value, run_id="test-run", public_keys=self.keys, version=other)
                self.assertEqual(self.ledger.path.read_bytes(), raw)
                relabeled = {**value, "v": other}
                with self.assertRaisesRegex(ValueError, "hash_mismatch"):
                    verify(relabeled, run_id="test-run", public_keys=self.keys)

    def test_raw_jsonl_rejects_bom_and_non_utf8_encodings(self):
        current = self.append(1)[0]
        text = canonical(current).decode("utf-8")
        for encoding in ("utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be"):
            with self.subTest(encoding=encoding):
                raw = text.encode(encoding) + b"\n"
                self.ledger.path.write_bytes(raw)
                state = self.read()
                self.assertEqual(state["last_seq"], 0)
                self.assertIsNotNone(state["error"])
                self.assertEqual(state["source_rows"][0]["raw"], raw)
                with self.assertRaises(BrokenLedger):
                    self.ledger.append("node.create", {"id": "next"}, event_id="next")

    def test_utf8_bom_character_inside_json_string_is_preserved(self):
        value = self.ledger.append("node.create", {"id": "é😀\ufeff"}, event_id="unicode")
        self.assertEqual(self.read()["prefix"], [value])


if __name__ == "__main__":
    unittest.main()
