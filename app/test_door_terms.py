"""The challenge terms at GET /api/open/v1/door/terms (aneta #57911 P1-2) and the feeds' summary words (P1-3).

Terms: the door serves only the text whose SHA-256 is the signed manifest's pin, sentilab-open-terms/<n>@<sha256>, of
its highest accepted version. The text is read once, when the door is built, from DOOR_TERMS_DIR (default: this tree's
web/public/sentilab/open/terms, which the API image carries), at the contract's canonical file name <n>@<sha256>.md.
Absent, unreadable, oversize or other bytes: 503 terms_unavailable, never another text.

Summary: what ran is the same pinned build replayed in a fresh process. That is reproduction, not independent
verification, and a failed run has no score."""
import hashlib
import importlib
import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from app.door import testkit as tk
from app.door.routes import configure
from app.test_door_dispatch import moved
from open_proposals.contract.states import LIFECYCLE, SUMMARY

REPO = Path(__file__).resolve().parents[1]
TERMS_DIR = REPO / "web" / "public" / "sentilab" / "open" / "terms"
PIN = "f11989175769a7a3410b26ecea46aac1756033ee562c792fe29a02af931899f7"
VERSION = "sentilab-open-terms/1@" + PIN
FILE_NAME = f"1@{PIN}.md"
UNAVAILABLE = {"error": "terms_unavailable"}


def version_for(number: int, text: bytes) -> tuple:
    """(version, canonical file name) of a terms text."""
    digest = hashlib.sha256(text).hexdigest()
    return f"sentilab-open-terms/{number}@{digest}", f"{number}@{digest}.md"


def manifest_with(*versions) -> dict:
    return tk.door_manifest(**{"terms.accepted_versions": list(versions)})


class TermsRouteTests(tk.DoorCase, unittest.TestCase):
    """The route over real HTTP (app.main and its middleware), on doors built the way the service builds them:
    Door.from_env, from files and environment."""
    http = True

    def door_from_env(self, manifest=None, *, terms_dir=None, binding=True):
        from app.door.service import Door

        work = Path(tempfile.mkdtemp(dir=self.tmp.name))
        env = {"DOOR_DATA_DIR": str(work / "data"), "DOOR_K_CHALLENGE": tk.K_CHALLENGE.hex(), "DOOR_ADMISSION": "open"}
        if manifest is not None:
            (work / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            env["DOOR_MANIFEST_PATH"] = str(work / "manifest.json")
            if binding:
                (work / "binding.json").write_text(json.dumps(tk.binding(manifest, tk.grant())), encoding="utf-8")
                env["DOOR_BINDING_PATH"] = str(work / "binding.json")
        if terms_dir is not None:
            env["DOOR_TERMS_DIR"] = str(terms_dir)
        door = Door.from_env(env)
        self.addCleanup(door.stop)
        configure(door)                                  # DoorCase.tearDown restores the door it replaced
        return door

    def get_raw(self, path: str) -> tuple:
        """(status, body bytes, lower-cased headers)."""
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method="GET")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw, status, got = response.read(), response.status, dict(response.headers)
        except urllib.error.HTTPError as error:
            raw, status, got = error.read(), error.code, dict(error.headers)
        return status, raw, {key.lower(): value for key, value in got.items()}

    def assert_unavailable(self, why: str, *texts: bytes):
        status, raw, headers = self.get_raw("/api/open/v1/door/terms")
        self.assertEqual(status, 503, why)
        self.assertEqual(json.loads(raw), UNAVAILABLE, why)
        self.assertEqual(headers.get("cache-control"), "no-store", why)
        self.assertNotIn("x-terms-version", headers, why)
        for text in texts:
            self.assertNotIn(text[:64], raw, why)

    def directory(self, files: dict) -> Path:
        path = Path(tempfile.mkdtemp(dir=self.tmp.name))
        for name, data in files.items():
            (path / name).write_bytes(data)
        return path

    def test_the_route_serves_exactly_the_bytes_the_signed_manifest_pins(self):
        committed = (TERMS_DIR / FILE_NAME).read_bytes()
        self.door_from_env(manifest_with(VERSION))       # DOOR_TERMS_DIR unset: the tree's own directory
        status, raw, headers = self.get_raw("/api/open/v1/door/terms")
        self.assertEqual(status, 200)
        self.assertEqual(raw, committed)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), PIN)
        self.assertEqual(headers["content-type"], "text/markdown; charset=utf-8")
        self.assertEqual(headers["cache-control"], "no-store")
        self.assertEqual(headers["x-terms-version"], VERSION)
        self.assertTrue(raw.startswith(b"# SentiLab open door: terms (version 1)\n"))

    def test_a_tampered_file_under_the_pinned_name_is_refused_and_never_served(self):
        committed = (TERMS_DIR / FILE_NAME).read_bytes()
        flipped = bytearray(committed)
        flipped[2] ^= 0x20                               # "SentiLab" -> "sentiLab": one byte, same length, same name
        tampered = bytes(flipped)
        self.assertNotEqual(hashlib.sha256(tampered).hexdigest(), PIN)
        door = self.door_from_env(manifest_with(VERSION), terms_dir=self.directory({FILE_NAME: tampered}))
        self.assertIsNone(door.terms)
        self.assert_unavailable("a tampered file", tampered)
        for path in ("/api/open/v1/door/board", "/api/open/v1/door/results", "/api/open/v1/door/events"):
            status, raw, _headers = self.get_raw(path)
            self.assertEqual(status, 200, path)
            self.assertNotIn(tampered[:64], raw, path)
        # A longer file that starts with the pinned bytes is not the pinned text either.
        self.door_from_env(manifest_with(VERSION), terms_dir=self.directory({FILE_NAME: committed + b"\nextra"}))
        self.assert_unavailable("pinned bytes plus more", committed + b"\nextra")

    def test_no_file_no_accepted_version_or_no_manifest_is_unavailable(self):
        self.door_from_env(manifest_with(VERSION), terms_dir=self.directory({}))
        self.assert_unavailable("no file under the pinned name")
        self.door_from_env(manifest_with(VERSION), terms_dir=self.directory({"other.md": b"other text"}))
        self.assert_unavailable("only other files", b"other text")
        self.door_from_env(None)
        self.assert_unavailable("no manifest")
        self.door_from_env(manifest_with())              # a signed manifest names at least one version
        self.assert_unavailable("no accepted version")
        terms = importlib.import_module("app.door.terms")
        self.assertIsNone(terms.load({"terms": {"accepted_versions": []}}, TERMS_DIR))
        self.assertIsNone(terms.load(None, TERMS_DIR))
        self.assertIsNone(terms.load({"terms": {"accepted_versions": ["sentilab-open-terms/1@" + PIN.upper()]}},
                                     TERMS_DIR), "an ill-formed version names nothing")
        self.assertIsNone(terms.load({"terms": {"accepted_versions": [VERSION + "\n"]}}, TERMS_DIR))
        self.assertIsNotNone(terms.load({"terms": {"accepted_versions": [VERSION]}}, TERMS_DIR))

    def test_an_oversize_file_is_refused(self):
        terms = importlib.import_module("app.door.terms")
        big = b"x" * (terms.MAX_BYTES + 1)
        version, name = version_for(1, big)
        self.assertIsNone(terms.load({"terms": {"accepted_versions": [version]}}, self.directory({name: big})))
        exact = b"y" * terms.MAX_BYTES
        version, name = version_for(1, exact)
        loaded = terms.load({"terms": {"accepted_versions": [version]}}, self.directory({name: exact}))
        self.assertEqual(loaded.data, exact)

    def test_DOOR_TERMS_DIR_overrides_the_default_and_never_falls_back(self):
        committed = (TERMS_DIR / FILE_NAME).read_bytes()
        door = self.door_from_env(manifest_with(VERSION), terms_dir=self.directory({FILE_NAME: committed}))
        self.assertEqual((door.terms.version, door.terms.sha256, door.terms.data), (VERSION, PIN, committed))
        status, raw, _headers = self.get_raw("/api/open/v1/door/terms")
        self.assertEqual((status, raw), (200, committed))
        # Configured elsewhere and missing there: unavailable, though the tree's own directory has the file.
        self.door_from_env(manifest_with(VERSION), terms_dir=self.directory({}))
        self.assert_unavailable("configured directory without the file")
        # Configured empty: the default.
        terms = importlib.import_module("app.door.terms")
        self.assertEqual(terms.from_env(manifest_with(VERSION), {"DOOR_TERMS_DIR": ""}).data, committed)
        self.assertEqual(terms.from_env(manifest_with(VERSION), {}).data, committed)

    def test_the_highest_accepted_version_wins_and_a_missing_one_is_not_replaced_by_a_lower(self):
        committed = (TERMS_DIR / FILE_NAME).read_bytes()
        nine_text, ten_text = b"terms text nine\n", b"terms text ten\n"
        nine, nine_name = version_for(9, nine_text)
        ten, ten_name = version_for(10, ten_text)
        both = self.directory({FILE_NAME: committed, nine_name: nine_text, ten_name: ten_text})
        for order in ([VERSION, nine, ten], [ten, nine, VERSION], [nine, ten, VERSION]):
            self.door_from_env(manifest_with(*order), terms_dir=both)
            status, raw, headers = self.get_raw("/api/open/v1/door/terms")
            self.assertEqual((status, raw, headers.get("x-terms-version")), (200, ten_text, ten), order)
        # The highest is absent: nothing is served, not the lower version the board no longer names first.
        self.door_from_env(manifest_with(VERSION, ten), terms_dir=self.directory({FILE_NAME: committed}))
        self.assert_unavailable("the highest version has no file", committed)
        # The highest is tampered: likewise.
        self.door_from_env(manifest_with(VERSION, ten), terms_dir=self.directory({FILE_NAME: committed,
                                                                                    ten_name: b"tampered ten\n"}))
        self.assert_unavailable("the highest version's file is tampered", committed, b"tampered ten\n")

    def test_the_board_and_the_route_name_the_same_version(self):
        self.door_from_env(manifest_with(VERSION))
        status, board, _headers = self.request("GET", "/api/open/v1/door/board")
        self.assertEqual(board["terms"]["accepted_versions"], [VERSION])
        status, raw, headers = self.get_raw("/api/open/v1/door/terms")
        self.assertEqual((status, headers["x-terms-version"]), (200, board["terms"]["accepted_versions"][0]))

    def test_only_get_and_head_and_head_carries_no_body(self):
        self.door_from_env(manifest_with(VERSION))
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/open/v1/door/terms", method="HEAD")
        with urllib.request.urlopen(request, timeout=30) as response:
            self.assertEqual((response.status, response.read()), (200, b""))
            self.assertEqual(response.headers["x-terms-version"], VERSION)
        for method in ("POST", "PUT", "DELETE"):
            request = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/open/v1/door/terms", data=b"{}",
                                             method=method)
            with self.assertRaises(urllib.error.HTTPError, msg=method) as caught:
                urllib.request.urlopen(request, timeout=30)
            self.assertEqual(caught.exception.code, 405, method)


class CommittedTermsTests(unittest.TestCase):
    """Run inside the API image by scripts/container_smoke.sh: there it also shows .dockerignore carries the files."""

    def test_the_default_directory_is_the_trees_and_each_file_is_named_by_its_bytes(self):
        terms = importlib.import_module("app.door.terms")
        self.assertEqual(terms.DEFAULT_DIR.resolve(), TERMS_DIR.resolve())
        files = sorted(TERMS_DIR.iterdir())
        self.assertIn(TERMS_DIR / FILE_NAME, files, "the text the signed manifest pins is committed")
        for path in files:
            name = terms.VERSION.fullmatch("sentilab-open-terms/" + path.name[:-len(".md")])
            self.assertTrue(path.name.endswith(".md") and name, path.name)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), name.group(2), path.name)
            self.assertLessEqual(path.stat().st_size, terms.MAX_BYTES, path.name)


class SummaryTests(tk.DoorCase, unittest.TestCase):
    http = True

    def summaries(self, run_id: str, nonce_value: str) -> dict:
        """The summary each open view gives one run: results, status and (when it ranks) the board."""
        found = {}
        status, page, _headers = self.request("GET", "/api/open/v1/door/results?limit=20")
        found["results"] = next(item["summary"] for item in page["items"] if item["id"] == run_id)
        status, item, _headers = self.request("GET", f"/api/open/v1/door/status/{run_id}",
                                              headers={"x-door-nonce": nonce_value})
        self.assertEqual(status, 200)
        found["status"] = item["summary"]
        status, board, _headers = self.request("GET", "/api/open/v1/door/board")
        ranked = [row["summary"] for row in board["top"] if row["id"] == run_id]
        if ranked:
            found["board"] = ranked[0]
        return found

    def test_a_reproduced_run_reads_reproduced_by_a_fresh_process_replay(self):
        status, reply = self.submit(self.body(moved(4), nonce_value=tk.nonce(40)))
        self.assertEqual(status, 202, reply)
        self.drain()
        self.assertEqual(self.store.run(reply["run_id"])[0]["state"], "reproduced")
        self.assertEqual(self.summaries(reply["run_id"], tk.nonce(40)),
                         {"results": "reproduced by a fresh-process replay",
                          "status": "reproduced by a fresh-process replay",
                          "board": "reproduced by a fresh-process replay"})

    def test_a_failed_run_reads_no_score(self):
        self.scorer.mode = "error"
        status, reply = self.submit(self.body(moved(5), nonce_value=tk.nonce(41)))
        self.assertEqual(status, 202, reply)
        self.drain()
        self.assertEqual(self.store.run(reply["run_id"])[0]["state"], "failed")
        self.assertEqual(self.summaries(reply["run_id"], tk.nonce(41)), {"results": "no score", "status": "no score"})

    def test_no_feed_summary_claims_independent_verification_and_the_rest_keep_the_contracts_words(self):
        service = importlib.import_module("app.door.service")
        words = service.FEED_SUMMARY
        self.assertEqual(set(words), set(LIFECYCLE))
        self.assertEqual({state: words[state] for state in ("reproduced", "cross_checked", "failed")},
                         {"reproduced": "reproduced by a fresh-process replay",
                          "cross_checked": "reproduced by a fresh-process replay", "failed": "no score"})
        for state in LIFECYCLE:
            self.assertNotIn("independent", str(words[state]).lower(), state)
            if state not in ("reproduced", "cross_checked", "failed"):
                self.assertEqual(words[state], SUMMARY[state], state)
        # The Package view reads exactly these words (web/public/sentilab/package/source3d.mjs SUMMARIES).
        self.assertEqual({word for word in words.values() if word is not None},
                         {"rejected", "queued", "evaluated", "reproduced by a fresh-process replay", "no score"})
        self.assertEqual(SUMMARY["reproduced"], "independently verified", "the contract itself is unchanged")


if __name__ == "__main__":
    unittest.main()
