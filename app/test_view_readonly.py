"""The public view must leave ledger storage unchanged, even without write access."""
from urllib.error import HTTPError
import unittest

from app import test_view
from sentilab_core.ledger import Ledger
from sentilab_core.test_ledger import run_record


class ReadOnlyTests(unittest.TestCase):
    setUp = test_view.ViewTests.setUp
    tearDown = test_view.ViewTests.tearDown
    seed_run = test_view.ViewTests.seed_run
    get = test_view.ViewTests.get

    def snapshot(self):
        return (self.root.stat().st_mtime_ns,
                {path.name: (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
                 for path in self.root.iterdir()})

    def check_reads(self):
        before = self.snapshot()
        with self.assertRaises(HTTPError) as caught:
            self.get("/api/view/events?run_id=unknown-public-run&cursor=0")
        self.assertEqual(caught.exception.code, 404)
        self.assertEqual(self.snapshot(), before)
        for name in ("archive", "writer"):
            result = self.get("/api/view/events?run_id=" + name + "&cursor=0")
            self.assertEqual(result["prefix_end"], 1)
            self.assertIsNone(result["chain_error"])
        self.get("/api/view/runs")
        self.get("/api/view/key")
        self.assertEqual(self.snapshot(), before)

    def seed(self):
        self.seed_run("archive", 1)  # copied history need not have a sidecar lock
        ledger = Ledger(self.root, run_record("writer"), signer=self.signer,
                        public_keys={self.signer.key_id: self.signer.public_key})
        ledger.append("node.create", {"id": "source", "kind": "source"}, event_id="source")
        self.assertTrue((self.root / "writer.lock").exists())

    def test_missing_and_existing_gets_do_not_create_or_modify_storage(self):
        self.seed()
        self.check_reads()

    def test_gets_succeed_with_readonly_directory_files_and_writer_lock(self):
        self.seed()
        for path in self.root.iterdir():
            path.chmod(0o444)
        self.root.chmod(0o555)
        try:
            self.check_reads()
        finally:
            self.root.chmod(0o755)
            for path in self.root.iterdir():
                path.chmod(0o644)


if __name__ == "__main__":
    unittest.main()
