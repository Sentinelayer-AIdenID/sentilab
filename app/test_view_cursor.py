"""Append-position paging must retain evidence independently of event sequence."""
import json
from urllib.error import HTTPError
from urllib.request import urlopen
import unittest

from app import test_view
from sentilab_core.envelope import build, canonical
from sentilab_core.ledger import read_prefix


class CursorTests(unittest.TestCase):
    setUp = test_view.ViewTests.setUp
    tearDown = test_view.ViewTests.tearDown
    seed_run = test_view.ViewTests.seed_run
    get = test_view.ViewTests.get

    def conflicting_row(self, row):
        event = {**row["event"], "body": {"id": "conflict", "kind": "source"}}
        return build(event=event, run=row["run"], actor=row["actor"],
                     prev_hash=row["prev_hash"], signer=self.signer)

    def page(self, name, cursor, limit=1):
        with urlopen(f"http://127.0.0.1:{self.port}/api/view/events?run_id={name}"
                     f"&cursor={cursor}&limit={limit}", timeout=10) as response:
            return (response.read(), int(response.headers["x-next-cursor"]),
                    response.headers["x-has-more"] == "true")

    def test_one_row_pages_preserve_conflict_and_reference_prefix(self):
        rows = self.seed_run("conflict", 2)
        source = [rows[0], self.conflicting_row(rows[0]), rows[1]]
        self.root.joinpath("conflict.jsonl").write_bytes(b"".join(canonical(r) + b"\n" for r in source))
        pages, cursor = [], 0
        for more in (True, True, False):
            data, following, has_more = self.page("conflict", cursor)
            self.assertEqual(following, cursor + 1)
            self.assertEqual(has_more, more)
            pages.append(data)
            cursor = following
        self.assertEqual([json.loads(p)["event"]["seq"] for p in pages], [1, 1, 2])
        path = self.root / "download.jsonl"
        path.write_bytes(b"".join(pages))
        result = read_prefix(path, run_id="conflict", public_keys={self.signer.key_id: self.signer.public_key})
        self.assertEqual(result["last_seq"], 0)
        self.assertIsNotNone(result["error"])

    def test_late_conflict_duplicate_and_malformed_rows_advance_cursor(self):
        rows = self.seed_run("late", 2)
        initial, cursor, more = self.page("late", 0, 256)
        self.assertEqual((cursor, more), (2, False))
        appended = [canonical(rows[0]) + b"\n", b"null\n", canonical(self.conflicting_row(rows[0])) + b"\n"]
        with self.root.joinpath("late.jsonl").open("ab") as handle:
            handle.write(b"".join(appended))
        pages = []
        for raw in appended:
            data, following, _ = self.page("late", cursor)
            self.assertEqual(data, raw)
            self.assertEqual(following, cursor + 1)
            pages.append(data)
            cursor = following
        self.assertEqual(self.page("late", cursor), (b"", 5, False))
        downloaded = self.root / "download.jsonl"
        downloaded.write_bytes(initial + b"".join(pages))
        result = read_prefix(downloaded, run_id="late", public_keys={self.signer.key_id: self.signer.public_key})
        self.assertEqual(result["last_seq"], 0)
        diagnostic = self.get("/api/view/events?run_id=late&cursor=2&limit=1")
        self.assertEqual(diagnostic["next_cursor"], 3)
        self.assertTrue(diagnostic["has_more"])
        self.assertEqual(diagnostic["prefix_end"], 0)

    def test_cursor_caps_and_invalid_or_truncated_positions(self):
        rows = self.seed_run("caps", 257)
        _, cursor, more = self.page("caps", 0, 256)
        self.assertEqual((cursor, more), (256, True))
        self.root.joinpath("caps.jsonl").write_bytes(b"".join(
            canonical(row).ljust(65535, b" ") + b"\n" for row in rows[:65]))
        data, cursor, more = self.page("caps", 0, 256)
        self.assertEqual((len(data), cursor, more), (4 * 1024 * 1024, 64, True))
        self.assertEqual(self.page("caps", cursor, 256)[1:], (65, False))
        for query, code in (("cursor=-1", 422), ("cursor=256", 409), ("cursor=1&after=1", 400)):
            with self.assertRaises(HTTPError) as caught:
                self.get("/api/view/events?run_id=caps&" + query)
            self.assertEqual(caught.exception.code, code)


if __name__ == "__main__":
    unittest.main()
