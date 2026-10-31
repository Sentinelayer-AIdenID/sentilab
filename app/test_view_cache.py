"""Verified-prefix reuse must preserve the real HTTP feed and its stale boundary."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import statistics
import threading
import time
import unittest
from unittest import mock
from urllib.error import HTTPError
from urllib.request import urlopen

from app import test_view, view
from sentilab_core import ledger
from sentilab_core.envelope import build, canonical


class CacheTests(unittest.TestCase):
    setUp = test_view.ViewTests.setUp
    tearDown = test_view.ViewTests.tearDown
    seed_run = test_view.ViewTests.seed_run

    def poll(self, query):
        try:
            response = urlopen(f"http://127.0.0.1:{self.port}/api/view/events?{query}", timeout=30)
        except HTTPError as error:
            response = error
        with response:
            return response.status, {k: v for k, v in response.headers.items()
                                     if k.lower() not in ("date", "server")}, response.read()

    def test_empty_polls_reuse_verification_and_only_complete_appends_are_verified(self):
        rows = self.seed_run("append", 4)
        raw = [canonical(row) + b"\n" for row in rows]
        path = self.root / "append.jsonl"
        path.write_bytes(b"".join(raw[:3]) + raw[3][:-1])
        query = "run_id=append&cursor=3&cursor_hash=" + hashlib.sha256(b"".join(raw[:3])).hexdigest()
        with mock.patch.object(ledger, "verify", wraps=ledger.verify) as verify:
            cold = self.poll(query)
            self.assertEqual(cold[0], 200)
            self.assertEqual(cold[2], b"")
            self.assertEqual(verify.call_count, 3)
            self.assertEqual(self.poll(query), cold)
            self.assertEqual(verify.call_count, 3, "empty poll reverified the cached prefix")
            with path.open("ab") as handle:
                handle.write(b"\n")
            appended = self.poll(query)
            self.assertEqual(appended[2], raw[3])
            self.assertEqual(verify.call_count, 4, "append reverified old rows")
            self.assertEqual(self.poll(query), appended)
            self.assertEqual(verify.call_count, 4)

    def test_rewrite_shrink_and_identity_change_invalidate_warm_cache(self):
        rows = self.seed_run("changed", 3)
        raw = [canonical(row) + b"\n" for row in rows]
        path = self.root / "changed.jsonl"
        original = b"".join(raw)
        boundary = hashlib.sha256(original).hexdigest()
        query = "run_id=changed&cursor=3&cursor_hash=" + boundary
        # Same-size mid-file edits, shrink, and atomic replacement must all be seen.
        for mode in ("rewrite", "shrink", "replace", "rewrite-and-append"):
            with self.subTest(mode=mode):
                path.write_bytes(original)
                self.assertEqual(self.poll(query)[0], 200)
                changed = original.replace(b"node-2", b"node-X")
                if mode == "shrink":
                    changed = b"".join(raw[:2])
                elif mode == "rewrite-and-append":
                    changed += b"null\n"
                if mode == "replace":
                    replacement = path.with_suffix(".tmp")
                    replacement.write_bytes(changed)
                    replacement.replace(path)
                else:
                    path.write_bytes(changed)
                with mock.patch.object(ledger, "verify", wraps=ledger.verify) as verify:
                    self.assertEqual(self.poll(query)[0], 409)
                    self.assertEqual(verify.call_count, 2 if mode == "shrink" else 3)
                warm = self.poll("run_id=changed&cursor=0&format=json")
                view.configure(view.context())
                self.assertEqual(self.poll("run_id=changed&cursor=0&format=json"), warm)

    def test_late_conflict_dedup_and_out_of_order_appends_match_cold_diagnostics(self):
        rows = self.seed_run("conflicts", 3)
        raw = [canonical(row) + b"\n" for row in rows]
        conflict = build(event={**rows[0]["event"], "body": {"id": "conflict", "kind": "source"}},
                         run=rows[0]["run"], actor=rows[0]["actor"],
                         prev_hash=rows[0]["prev_hash"], signer=self.signer)
        path = self.root / "conflicts.jsonl"
        for prefix, suffix in ((raw[0], raw[0] + raw[1]),
                               (raw[1], raw[0] + raw[2]),
                               (b"".join(raw), canonical(conflict) + b"\n"),
                               (b"".join(raw), b"null\n")):
            path.write_bytes(prefix)
            self.poll("run_id=conflicts&cursor=0")
            with path.open("ab") as handle:
                handle.write(suffix)
            for query in ("cursor=0", "after=2"):
                query = "run_id=conflicts&format=json&" + query
                warm = self.poll(query)
                view.configure(view.context())
                self.assertEqual(self.poll(query), warm)

    def test_head_and_trust_changes_cannot_reuse_stale_verdicts(self):
        rows = self.seed_run("trust", 2)
        query = "run_id=trust&cursor=0&format=json"
        self.assertIsNone(json.loads(self.poll(query)[2])["chain_error"])
        head = self.root / "trust.head.json"
        head.write_text(json.dumps({"seq": 2, "hash": rows[0]["hash"]}))
        self.assertIn("head", json.loads(self.poll(query)[2])["chain_error"])
        head.write_text(json.dumps({"seq": 2, "hash": rows[1]["hash"]}))
        self.assertIsNone(json.loads(self.poll(query)[2])["chain_error"])
        keys = view.context().public_keys
        saved = keys.copy()
        keys.clear()
        self.assertIsNotNone(json.loads(self.poll(query)[2])["chain_error"])
        keys.update(saved)
        self.assertIsNone(json.loads(self.poll(query)[2])["chain_error"])

    def test_shared_file_identity_does_not_share_run_authentication(self):
        self.seed_run("original", 2)
        (self.root / "alias.jsonl").symlink_to(self.root / "original.jsonl")
        self.assertIsNone(json.loads(self.poll("run_id=original&format=json")[2])["chain_error"])
        self.assertIsNotNone(json.loads(self.poll("run_id=alias&format=json")[2])["chain_error"])
        self.assertIsNone(json.loads(self.poll("run_id=original&format=json")[2])["chain_error"])

    def test_cache_evicts_old_runs_and_failed_lookups_within_bounds(self):
        cache = view._replay_cache = ledger.ReplayCache(max_runs=2, max_bytes=4096)
        for name in ("first", "second", "third"):
            self.seed_run(name, 1)
            self.assertEqual(self.poll("run_id=" + name)[0], 200)
        self.assertLessEqual(len(cache._entries), 2)
        self.assertEqual(self.poll("run_id=first")[0], 200)
        for i in range(5):
            self.assertEqual(self.poll(f"run_id=missing-{i}")[0], 404)
        self.assertLessEqual(len(cache._entries), 2)
        self.seed_run("large", 10)
        self.assertEqual(self.poll("run_id=large")[0], 200)
        self.assertLessEqual(sum(item.size for item in cache._entries.values()), 4096)

    def test_bytes_verified_and_served_come_from_one_snapshot(self):
        rows = self.seed_run("snapshot", 2)
        raw = [canonical(row) + b"\n" for row in rows]
        path = self.root / "snapshot.jsonl"
        path.write_bytes(raw[0])
        self.poll("run_id=snapshot&cursor=0")
        with path.open("ab") as handle:
            handle.write(raw[1])
        read_rows = ledger._read_rows

        def rewrite_after_snapshot(*args):
            path.write_bytes(b"null\n")
            return read_rows(*args)

        with mock.patch.object(ledger, "_read_rows", side_effect=rewrite_after_snapshot):
            status, headers, body = self.poll("run_id=snapshot&cursor=0")
        self.assertEqual((status, body), (200, b"".join(raw)))
        self.assertEqual(headers["x-cursor-hash"], hashlib.sha256(body).hexdigest())
        self.assertEqual(self.poll("run_id=snapshot&cursor=2&cursor_hash=" + headers["x-cursor-hash"])[0], 409)

    def test_benchmark_eight_concurrent_empty_polls_at_1000_rows(self):
        self.seed_run("benchmark", 1000)
        boundary = hashlib.sha256((self.root / "benchmark.jsonl").read_bytes()).hexdigest()
        query = "run_id=benchmark&cursor=1000&cursor_hash=" + boundary
        expected = self.poll(query)  # Populate the shared verified prefix first.
        self.assertEqual(expected[0], 200)
        self.assertEqual(expected[2], b"")
        barrier = threading.Barrier(8)

        def timed_poll(_):
            barrier.wait(timeout=10)
            start = time.perf_counter()
            actual = self.poll(query)
            elapsed = time.perf_counter() - start
            self.assertEqual(actual, expected)
            return elapsed

        with ThreadPoolExecutor(max_workers=8) as pool:
            samples = list(pool.map(timed_poll, range(8)))
        # Report the capacity target without a host-speed-dependent assertion.
        print(json.dumps({"benchmark": "8 concurrent empty HTTP polls", "rows": 1000,
                          "seconds": samples, "median_s": statistics.median(samples),
                          "target_s": 0.5}), flush=True)


if __name__ == "__main__":
    unittest.main()
