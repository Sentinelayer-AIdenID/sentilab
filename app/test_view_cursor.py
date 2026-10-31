"""Append-position paging must retain evidence independently of event sequence."""
import json
import hashlib
from urllib.error import HTTPError
from urllib.request import urlopen
import unittest

from app import test_view
from sentilab_core.envelope import MAX_BYTES, MAX_PAGE_BYTES, build, canonical
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
        boundaries = getattr(self, "boundaries", {})
        boundary = "&cursor_hash=" + boundaries[(name, cursor)] if cursor else ""
        with urlopen(f"http://127.0.0.1:{self.port}/api/view/events?run_id={name}"
                     f"&cursor={cursor}&limit={limit}{boundary}", timeout=10) as response:
            following = int(response.headers["x-next-cursor"])
            boundaries[(name, following)] = response.headers["x-cursor-hash"]
            self.boundaries = boundaries
            return (response.read(), following,
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
        diagnostic = self.get("/api/view/events?run_id=late&cursor=2&limit=1&cursor_hash="
                              + self.boundaries[("late", 2)])
        self.assertEqual(diagnostic["next_cursor"], 3)
        self.assertTrue(diagnostic["has_more"])
        self.assertEqual(diagnostic["prefix_end"], 0)

    def test_consumed_prefix_replacement_refuses_incremental_history(self):
        for atomic in (False, True):
            with self.subTest(atomic=atomic):
                rows = self.seed_run("replaced", 3)
                with urlopen(f"http://127.0.0.1:{self.port}/api/view/events?run_id=replaced"
                             "&cursor=0&limit=1", timeout=10) as response:
                    # This boundary is computable from the original physical row,
                    # so the regression also exercises the old cursor-only API.
                    boundary = hashlib.sha256(response.read()).hexdigest()
                changed = [self.conflicting_row(rows[0]), *rows[1:]]
                path = self.root / ("replacement.tmp" if atomic else "replaced.jsonl")
                path.write_bytes(b"".join(canonical(row) + b"\n" for row in changed))
                if atomic:
                    path.replace(self.root / "replaced.jsonl")
                with self.assertRaises(HTTPError) as caught:
                    self.get("/api/view/events?run_id=replaced&cursor=1&cursor_hash=" + boundary)
                self.assertEqual(caught.exception.code, 409)
                restarted = self.get("/api/view/events?run_id=replaced&cursor=0")
                self.assertEqual(restarted["next_cursor"], 3)
                self.assertIsNotNone(restarted["chain_error"])

    def test_cursor_caps_and_invalid_or_truncated_positions(self):
        rows = self.seed_run("caps", 257)
        _, cursor, more = self.page("caps", 0, 256)
        self.assertEqual((cursor, more), (256, True))
        self.root.joinpath("caps.jsonl").write_bytes(b"".join(
            canonical(row).ljust(65535, b" ") + b"\n" for row in rows[:65]))
        data, cursor, more = self.page("caps", 0, 256)
        self.assertEqual((len(data), cursor, more), (4 * 1024 * 1024, 64, True))
        self.assertEqual(self.page("caps", cursor, 256)[1:], (65, False))
        for query, code in (("cursor=-1", 400), ("cursor=256", 409), ("cursor=1&after=1", 422),
                            ("cursor=1", 409), ("cursor=1&cursor_hash=invalid", 422)):
            with self.assertRaises(HTTPError) as caught:
                self.get("/api/view/events?run_id=caps&" + query)
            self.assertEqual(caught.exception.code, code)

    def test_unfinished_tail_waits_for_lf_without_changing_cursor_hash(self):
        rows = self.seed_run("partial", 2)
        first, last = (canonical(row) + b"\n" for row in rows)
        path = self.root / "partial.jsonl"
        self.boundaries = {("partial", 1): hashlib.sha256(first).hexdigest()}
        for tail in (last[:25], last[:-1], b"x" * (MAX_BYTES + 5)):
            with self.subTest(tail_bytes=len(tail)):
                path.write_bytes(first + tail)
                self.assertEqual(self.page("partial", 0, 256), (first, 1, False))
                self.assertEqual(self.boundaries[("partial", 1)], hashlib.sha256(first).hexdigest())
                self.assertEqual(self.page("partial", 1), (b"", 1, False))
                # The legacy sequence feed must also wait for complete bytes.
                with urlopen(f"http://127.0.0.1:{self.port}/api/view/events?run_id=partial&after=1",
                             timeout=10) as response:
                    self.assertEqual(response.read(), b"")
        path.write_bytes(first + last[:-1])
        with path.open("ab") as handle:
            handle.write(b"\n")
        self.assertEqual(self.page("partial", 1), (last, 2, False))
        self.assertEqual(self.boundaries[("partial", 2)], hashlib.sha256(first + last).hexdigest())
        path.write_bytes(b"unfinished")
        self.assertEqual(self.page("partial", 0), (b"", 0, False))
        self.assertEqual(self.boundaries[("partial", 0)], hashlib.sha256(b"").hexdigest())

    def test_c12_unpageable_first_row_returns_empty_413_without_cursor_headers(self):
        first = canonical(self.seed_run("unpageable", 1)[0]) + b"\n"
        for prefix in (b"", first):
            self.root.joinpath("unpageable.jsonl").write_bytes(prefix + b"x" * 4_194_304 + b"\n")
            cursor = 1 if prefix else 0
            boundary = hashlib.sha256(prefix).hexdigest()
            for format_query in ("", "&format=jsonl", "&format=json"):
                with self.subTest(cursor=cursor, format=format_query):
                    with self.assertRaises(HTTPError) as caught:
                        urlopen(f"http://127.0.0.1:{self.port}/api/view/events?run_id=unpageable"
                                f"&cursor={cursor}&cursor_hash={boundary}{format_query}", timeout=10)
                    self.assertEqual(caught.exception.code, 413)
                    self.assertEqual(caught.exception.read(), b"")
                    for header in ("x-next-cursor", "x-cursor-hash", "x-has-more", "x-next-after"):
                        self.assertNotIn(header, caught.exception.headers)

    def test_c7_invalid_paging_ranges_return_400_without_echoing_input(self):
        self.seed_run("ranges", 1)
        for query in ("cursor=-1", "cursor=1.5", "cursor=9007199254740992",
                      "limit=0", "limit=257", "after=-1", "after=1.5",
                      "limit=invalid-range-marker", "cursor=invalid-range-marker",
                      "after=invalid-range-marker"):
            with self.subTest(query=query):
                with self.assertRaises(HTTPError) as caught:
                    urlopen(f"http://127.0.0.1:{self.port}/api/view/events?run_id=ranges&{query}",
                            timeout=10)
                self.assertEqual(caught.exception.code, 400)
                self.assertEqual(json.load(caught.exception), {"detail": "invalid paging range"})

    def test_oversize_rows_preserve_bytes_and_hash_at_each_page_boundary(self):
        rows = self.seed_run("oversize", 2)
        first, last = (canonical(row) + b"\n" for row in rows)
        for size in (MAX_BYTES + 1, MAX_PAGE_BYTES - 1, MAX_PAGE_BYTES + 1):
            with self.subTest(size=size):
                oversize = b"\xff" + b"x" * (size - 1) + b"\n"
                self.root.joinpath("oversize.jsonl").write_bytes(first + oversize + last)
                consumed = b""
                for cursor, raw in enumerate((first, oversize, last)):
                    if len(raw) > MAX_PAGE_BYTES:
                        with self.assertRaises(HTTPError) as caught:
                            self.page("oversize", cursor)
                        self.assertEqual(caught.exception.code, 413)
                        self.assertEqual(caught.exception.read(), b"")
                        self.assertNotIn("x-next-cursor", caught.exception.headers)
                        self.assertNotIn("x-cursor-hash", caught.exception.headers)
                        break
                    self.assertEqual(self.page("oversize", cursor), (raw, cursor + 1, cursor < 2))
                    consumed += raw
                    self.assertEqual(self.boundaries[("oversize", cursor + 1)],
                                     hashlib.sha256(consumed).hexdigest())
                if len(oversize) > MAX_PAGE_BYTES:
                    continue
                self.assertEqual(self.page("oversize", 3), (b"", 3, False))
                if size >= MAX_PAGE_BYTES - 1:
                    # An exactly full row goes alone even with a larger row limit.
                    self.assertEqual(self.page("oversize", 0, 256), (first, 1, True))
                    self.assertEqual(self.page("oversize", 1, 256), (oversize, 2, True))
                    self.assertEqual(self.page("oversize", 2, 256), (last, 3, False))

    def test_bad_cursor_parameters_are_retryable_validation_errors(self):
        self.seed_run("invalid", 1)
        for query in ("cursor=1&after=1", "cursor=0&after=1", "cursor=0&after=0",
                      "cursor_hash=" + "a" * 64,
                      "cursor=0&cursor_hash=", "cursor=1&cursor_hash=invalid",
                      "cursor=0&cursor_hash=" + "A" * 64):
            with self.subTest(query=query):
                with self.assertRaises(HTTPError) as caught:
                    self.get("/api/view/events?run_id=invalid&" + query)
                self.assertEqual(caught.exception.code, 422)


if __name__ == "__main__":
    unittest.main()
