"""Signed local correction fixtures; no solver or model execution."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from sentilab_core.envelope import canonical
from sentilab_core.ledger import BrokenLedger, Ledger
from sentilab_core.memory import MemoryStore
from sentilab_core.projection import project
from sentilab_core.test_ledger import RuntimeSigner

FIXTURE = Path(__file__).resolve().parents[1] / "docs/sentilab/evidence/SLAB-010/memory-fixture.json"


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = json.loads(FIXTURE.read_text())
        self.scope = self.fixture["scope"]
        self.signer = RuntimeSigner()
        self.keys = {self.signer.key_id: self.signer.public_key}
        self.ledger = Ledger(self.root / "ledger", self.run_record(),
                             public_keys=self.keys, signer=self.signer)
        for index, event in enumerate(self.fixture["events"]):
            self.ledger.append(event["type"], event["body"], event_id=f"fixture-{index}")
        self.store = self.open_store()

    def run_record(self):
        return {"run_id": self.scope["run"], **{k: self.scope[k] for k in ("arm", "family", "seed")},
                "ticket_id": "23a5285a"}

    def open_store(self):
        return MemoryStore(self.root / "memory", ledger_root=self.root / "ledger", public_keys=self.keys,
                           tenant=self.scope["tenant"], held_out_families=self.fixture["held_out_families"])

    def write_fixture(self):
        return [self.store.write(self.scope, **memory) for memory in self.fixture["memories"]]

    def withdraw(self):
        correction = self.fixture["correction"]
        self.ledger.append(correction["type"], correction["body"], event_id="correction")

    def test_withdrawal_stale_and_alternative_support_preserve_audit(self):
        before = self.write_fixture()
        path = self.store._path(self.scope)
        original = path.read_bytes()
        self.assertEqual([r["item"]["id"] for r in self.store.recall(self.scope)], self.fixture["expected_before"])
        self.withdraw()
        self.assertEqual([r["item"]["id"] for r in self.store.recall(self.scope)], self.fixture["expected_after"])
        self.assertEqual({r["id"]: r["invalid_evidence"] for r in self.store.invalidate(self.scope)},
                         self.fixture["expected_invalid_evidence"])
        self.assertEqual(self.store.audit(self.scope), before)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.open_store().recall(self.scope), self.store.recall(self.scope))
        self.ledger.append("withdraw.retract", {"node": "measurement-a"}, event_id="retract")
        self.assertEqual(self.store.recall(self.scope), before)

    def test_every_scope_dimension_is_isolated_and_typed(self):
        expected = self.write_fixture()
        for field, value in {"tenant": "tenant-b", "run": "other-run", "arm": "other-arm",
                             "family": "other-family", "seed": 18}.items():
            scope = {**self.scope, field: value}
            with self.subTest(field=field):
                if field == "tenant":
                    with self.assertRaisesRegex(ValueError, "host tenant"):
                        self.store.recall(scope)
                    other = MemoryStore(self.root / "memory", ledger_root=self.root / "other-ledger",
                                        public_keys=self.keys, tenant=value, held_out_families=[])
                    self.assertEqual(other.recall(scope), [])
                    self.assertEqual(other.audit(scope), [])
                else:
                    self.assertEqual(self.store.recall(scope), [])
                    self.assertEqual(self.store.audit(scope), [])
        self.assertEqual(self.store.recall(self.scope), expected)
        for value in (True, 17.0, "17", -1, None, 9007199254740992):
            with self.assertRaises(ValueError):
                self.store.recall({**self.scope, "seed": value})

    def test_heldout_and_incomplete_scope_refused_before_creating_store(self):
        memory = self.fixture["memories"][0]
        for field in self.scope:
            scope = {k: v for k, v in self.scope.items() if k != field}
            with self.assertRaisesRegex(ValueError, "scope requires"):
                self.store.write(scope, **memory)
        with self.assertRaisesRegex(ValueError, "held-out"):
            self.store.write({**self.scope, "family": "evaluation-a"}, **memory)
        self.assertFalse((self.root / "memory").exists())

    def test_evidence_is_required_valid_and_bound_to_ledger_scope(self):
        self.ledger.append("node.create", {"id": "unsupported", "kind": "claim"}, event_id="unsupported")
        for refs in ([], ["missing"], ["unsupported"], ["measurement-a", "missing"],
                     ["measurement-a", "measurement-a"], "measurement-a"):
            with self.assertRaises(ValueError):
                self.store.write(self.scope, {"id": "probe"}, refs)
        for field, value in (("arm", "other"), ("family", "other"), ("seed", 18)):
            with self.assertRaisesRegex(ValueError, "ledger differs"):
                self.store.write({**self.scope, field: value}, {"id": "probe"}, ["measurement-a"])
        self.withdraw()
        with self.assertRaisesRegex(ValueError, "currently be valid"):
            self.store.write(self.scope, {"id": "probe"}, ["measurement-a"])

    def test_all_references_are_required_but_ledger_alternatives_are_honored(self):
        self.store.write(self.scope, {"id": "conjunction"}, ["measurement-b", "measurement-a"])
        self.withdraw()
        self.assertEqual(self.store.recall(self.scope), [])
        self.assertEqual(self.store.invalidate(self.scope)[0]["invalid_evidence"], {"measurement-a": "withdrawn"})

    def test_idempotency_immutable_inputs_and_literal_query(self):
        memory = copy.deepcopy(self.fixture["memories"][0])
        row = self.store.write(self.scope, **memory)
        self.assertEqual(self.store.write(self.scope, **memory), row)
        self.assertEqual(len(self.store.audit(self.scope)), 1)
        memory["item"]["text"] = "changed"
        with self.assertRaisesRegex(ValueError, "idempotency conflict"):
            self.store.write(self.scope, **memory)
        row["item"]["text"] = "also changed"
        self.assertEqual(len(self.store.recall(self.scope, "DIRECT FIXTURE")), 1)
        self.assertEqual(self.store.recall(self.scope, "changed"), [])
        with self.assertRaisesRegex(ValueError, "query must"):
            self.store.recall(self.scope, None)

    def test_corrupt_ledger_refuses_recall_but_audit_survives(self):
        expected = self.write_fixture()
        with self.ledger.path.open("ab") as handle:
            handle.write(b'{"broken":true}\n')
        with self.assertRaises(BrokenLedger):
            self.store.recall(self.scope)
        with self.assertRaises(BrokenLedger):
            self.store.write(self.scope, {"id": "new"}, ["measurement-a"])
        self.assertEqual(self.store.audit(self.scope), expected)

    def test_validly_resigned_replacement_history_cannot_revive_memory(self):
        self.write_fixture()
        self.ledger.path.unlink()
        self.ledger.head_path.unlink()
        for index, event in enumerate(self.fixture["events"]):
            self.ledger.append(event["type"], event["body"], event_id=f"different-{index}")
        with self.assertRaisesRegex(BrokenLedger, "history was replaced"):
            self.store.recall(self.scope)
        before = self.store.audit(self.scope)
        with self.assertRaisesRegex(BrokenLedger, "history was replaced"):
            self.store.write(self.scope, {"id": "new-history"}, ["measurement-a"])
        self.assertEqual(self.store.audit(self.scope), before)

    def test_correction_projection_matches_reviewed_contract_without_solves(self):
        self.write_fixture()
        for withdrawn in (False, True):
            if withdrawn:
                self.withdraw()
            prefix = self.ledger.read()["prefix"]
            process = subprocess.run(["node", str(Path(__file__).with_name("projection.mjs"))],
                                     input=canonical([row["event"] for row in prefix]),
                                     capture_output=True, check=True, timeout=30)
            self.assertEqual(json.loads(process.stdout), project(prefix))

    def test_scope_names_do_not_alias_and_path_escape_is_refused(self):
        a = {**self.scope, "arm": "a:b", "family": "c"}
        b = {**self.scope, "arm": "a", "family": "b:c"}
        self.assertNotEqual(self.store._path(a), self.store._path(b))
        self.assertNotEqual(self.store._path(a), self.store._path({**a, "arm": "A:B"}))
        with self.assertRaises(ValueError):
            self.store.audit({**self.scope, "run": "../escape"})
        self.store.root.mkdir()
        path = self.store._path(self.scope)
        path.symlink_to(self.root / "outside.jsonl")
        with self.assertRaisesRegex(ValueError, "escapes root"):
            self.store.audit(self.scope)

    def test_invalid_items_and_broken_audit_fail_closed(self):
        for item in (None, {}, {"id": ""}, {"id": "bad", "v": float("nan")}, {"id": "big", "v": "x" * 600}):
            with self.assertRaises(ValueError):
                self.store.write(self.scope, item, ["measurement-a"])
        rows = self.write_fixture()
        path = self.store._path(self.scope)
        path.write_bytes(canonical(rows[0]) + b"\n")
        with self.assertRaisesRegex(ValueError, "durable memory head"):
            self.store.audit(self.scope)
        path.write_bytes(b"".join(canonical(row) + b"\n" for row in rows) + b"partial")
        with self.assertRaisesRegex(ValueError, "invalid memory log row"):
            self.store.recall(self.scope)
        path.write_bytes(b"[" * 10000 + b"]" * 10000 + b"\n")
        with self.assertRaisesRegex(ValueError, "memory JSON nesting"):
            self.store.recall(self.scope)


if __name__ == "__main__":
    unittest.main()
