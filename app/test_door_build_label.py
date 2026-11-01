"""The reproduction-tested build label at the door (contracts/open-proposal-v1/builds.json, app/door/evaluator.py).

Every scored result's evaluator is the full identity string its run attests: the signed manifest's engine commit,
grid and centre mapping; the bound receipt's binary and every configuration file hash; and the build's image, attested
by digest alone (the receipt's image_digest, the signed grant's scorer_image_digest and the signed manifest's
statistic.evaluator.build are each exactly the digest builds.json records for the build; never a tag). It reads
"reproduction_tested" only when all of them are the build's; any single field off is another string, which reads
unvalidated. builds.json records no digest for the gate-zero image, so the real door reads every result unvalidated:
the tests that need the build to match use a test-only registry (registry()), the build's identity with the test scorer
image's digest recorded, which the test manifest, grant and receipts all carry. The broad alias still reads
unvalidated. Hard rule:
the label changes nothing else. A result's own qualifiers (replay status, binding basis and mismatch, a missing grid,
the guard, the candidate verdict) stay exactly as its verification says.

The page side reads the same API output: web/test/door-api-build-label.json is this door's results body for a fixed
sequence under that test registry (test_the_page_fixture_is_this_apis_output keeps it current; regenerate it with
`python -m app.test_door_build_label --write-fixture`), and web/test/door-build-label.test.mjs runs the page's label
rule over it.
"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from open_proposals.contract import builds
from open_proposals.contract.labels import label_for
from open_proposals.contract.schemas import SCHEMAS
from sundai_hotspot import gate_zero

from app.door import testkit as tk
from app.door.evaluator import ALIAS, attested, evaluator_identity
from app.door.policy import Grant
from app.door.service import EVALUATOR_IDENTITY, Door
from app.door.store import Store
from app.test_door_dispatch import moved

BUILD = json.loads(builds.BUILDS_PATH.read_bytes())["builds"][0]      # as stored; the code under test loads it
TAG = BUILD["identity"]["image"]
EVALUATOR = re.compile(SCHEMAS["common"]["$defs"]["evaluator"]["pattern"])
FIXTURE = Path(__file__).resolve().parents[1] / "web" / "test" / "door-api-build-label.json"
# warden's P1 on #85 (at 3c7b3062): the image is attested by digest, never by tag.
D = tk.SCORER_IMAGE                     # the digest the test grant pins and FakeScorer's receipts name
OTHER = "sha256:" + tk.fake("another scorer image")
# The 5cedde1 runtime's image digest (root's decision on room 608657e4 #57792): another image than gate zero's. A grant
# pinning it, with the tag sentilab-gate0:2d35e9c, read reproduction_tested at 3c7b3062.
CDE9 = "sha256:cde9ce804130ba4dd2495f458c67acde74de9307291401e8e92f600812e4e1c7"
ABSENT = object()                       # a field left out altogether


def registry(digest, build=BUILD) -> tuple:
    """A test-only registry: builds.json's build, its identity (and so its id) unchanged, recording `digest` as its
    image digest. Never the real file, which records no digest for the gate-zero image."""
    return (dict(build, image_digest=digest),)


def scored(case, layout: str, door=None, nonce=tk.NONCE) -> dict:
    """Submit one layout to a test door, drive it to its outcome and return its results item."""
    door = door or case.door
    status, reply, _ = door.submit(json.dumps(case.body(layout, nonce_value=nonce)).encode())
    case.assertEqual(status, 202, reply)
    while door.dispatcher.run_once():
        pass
    return {item["id"]: item for item in door.results(None, "20")[1]["items"]}[reply["run_id"]]


class EvaluatorIdentityTests(unittest.TestCase):
    """The identity a run attests, over the signed manifest, the bound evaluation receipt and the grant, under the
    test registry (the build recording the test scorer image's digest)."""

    def setUp(self):
        self.manifest = tk.door_manifest()
        self.grant = Grant.parse(tk.grant())
        self.receipt = {"binary_sha256": tk.EVALUATOR_BINARY_SHA256, "image_digest": D,
                        "input_sha256": dict(tk.GATE0_INPUTS)}
        self.registered = registry(D)

    def identity(self, receipt, manifest, grant) -> str:
        return evaluator_identity(receipt, manifest, grant, registered=self.registered)

    def test_the_complete_build_reads_reproduction_tested(self):
        self.assertEqual(BUILD["identity"], attested(self.registered[0], self.receipt, self.manifest, self.grant))
        self.assertEqual(BUILD["id"], self.identity(self.receipt, self.manifest, self.grant))
        self.assertEqual("reproduction_tested", label_for(BUILD["id"]))
        # builds.json itself records no digest for the gate-zero image: there, the same run is not the build.
        self.assertIsNone(BUILD["image_digest"])
        self.assertNotEqual(BUILD["id"], evaluator_identity(self.receipt, self.manifest, self.grant))

    def test_each_single_field_mismatch_is_another_string_and_reads_unvalidated(self):
        inputs = self.receipt["input_sha256"]
        manifest = tk.door_manifest
        other_binary = tk.fake("another binary")
        cases = {
            "no image digest in the receipt": ({k: v for k, v in self.receipt.items() if k != "image_digest"},
                                               self.manifest, self.grant),
            "another image digest": (self.receipt | {"image_digest": OTHER}, self.manifest,
                                     Grant.parse(tk.grant(scorer_image_digest=OTHER))),
            "another manifest build": (self.receipt, manifest(**{"statistic.evaluator.build": OTHER}), self.grant),
            "another engine commit": (self.receipt, manifest(**{"statistic.evaluator.upstream": "0" * 40}),
                                      self.grant),
            "another engine": (self.receipt, manifest(**{"statistic.evaluator.kind": "hotspot7"}), self.grant),
            "another binary": (self.receipt | {"binary_sha256": other_binary}, self.manifest, self.grant),
            "another HotSpot config": (self.receipt | {"input_sha256": inputs | {
                "new_hotspot.config": tk.fake("another config")}}, self.manifest, self.grant),
            "another package layer": (self.receipt | {"input_sha256": inputs | {
                "sampleL1_C4Layer.flp": tk.fake("another C4 layer")}}, self.manifest, self.grant),
            "a package layer missing": (self.receipt | {"input_sha256": {
                name: value for name, value in inputs.items() if name != "samplelayers.lcf"}}, self.manifest,
                self.grant),
            "another grid": (self.receipt, manifest(**{"statistic.grid": 32}), self.grant),
            "another centre mapping": (self.receipt, manifest(**{"statistic.centre_mapping": "the native selector"}),
                                       self.grant),
            "no receipt": (None, self.manifest, self.grant),
            "a receipt without input hashes": ({"binary_sha256": tk.EVALUATOR_BINARY_SHA256}, self.manifest,
                                               self.grant),
            "no manifest": (self.receipt, None, self.grant),
            "no grant": (self.receipt, self.manifest, None),
        }
        seen = set()
        for name, args in cases.items():
            with self.subTest(name):
                text = self.identity(*args)
                self.assertNotEqual(BUILD["id"], text)
                self.assertNotEqual(ALIAS, text, "the run's own identity, never a constant")
                self.assertEqual("unvalidated", label_for(text))
                self.assertTrue(EVALUATOR.match(text), text)
                seen.add(text)
        # No grant, no receipt digest, another image and another manifest build all attest the same thing (no image);
        # every other mismatch is its own string.
        no_image = {self.identity(*cases[name]) for name in ("no grant", "no image digest in the receipt",
                                                             "another image digest", "another manifest build")}
        self.assertEqual(1, len(no_image))
        self.assertEqual(len(cases) - 3, len(seen))
        # The readable fields are what the run attests.
        self.assertIn(":binary_sha256:" + other_binary + ":", self.identity(*cases["another binary"]))
        self.assertIn(":grid:32x32:", self.identity(*cases["another grid"]))
        self.assertTrue(self.identity(*cases["another engine commit"]).startswith("HotSpot-6.0:" + "0" * 40 + ":"))

    def test_a_layouts_own_files_are_not_part_of_the_identity(self):
        """A door layout stages its own power trace and die-layer floorplans; the build is the same build."""
        receipt = self.receipt | {"input_sha256": tk.GATE0_INPUTS | {name: tk.fake(name) for name in tk.PER_LAYOUT}}
        self.assertEqual(BUILD["id"], self.identity(receipt, self.manifest, self.grant))

    def test_the_alias_keeps_its_meaning(self):
        self.assertEqual(EVALUATOR_IDENTITY, ALIAS)
        self.assertEqual(f"hotspot6:{tk.EVALUATOR_BINARY_SHA256}:grid:64x64", ALIAS)
        self.assertEqual("unvalidated", label_for(ALIAS))
        self.assertNotIn(ALIAS, [build["id"] for build in builds.registered()])
        self.assertEqual(ALIAS, evaluator_identity(self.receipt, self.manifest, self.grant, registered=()))

    def test_the_registry_agrees_with_gate_zero_and_the_door(self):
        """builds.py names gate zero's two raw references and the door's binary pin; their sources must agree."""
        self.assertEqual(set(builds.GATE0_CASES.values()), {Path(item.inputs).name for item in gate_zero.GATE_REFERENCES})
        self.assertEqual(BUILD["identity"]["binary_sha256"], tk.EVALUATOR_BINARY_SHA256)
        self.assertEqual(BUILD["identity"]["engine_commit"], gate_zero.HOTSPOT6_COMMIT)
        self.assertEqual(BUILD["identity"]["grid"], gate_zero.GRID)
        shared = BUILD["identity"]["config_sha256"]
        self.assertEqual(shared, {name: tk.GATE0_INPUTS[name] for name in shared})
        self.assertEqual(set(tk.GATE0_INPUTS) - set(shared), set(tk.PER_LAYOUT))

    def test_a_grant_names_its_image_by_digest_only(self):
        """The grant has exactly its fields, as on main: no image tag (warden's P1), and a strict digest."""
        self.assertFalse(hasattr(Grant.parse(tk.grant()), "scorer_image_tag"))
        for tag in (TAG, "sentilab-gate0:5cedde1", None):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                Grant.parse(tk.grant(scorer_image_tag=tag))
        hexits = D[len("sha256:"):]
        for bad in ("sha256:" + hexits.upper(), " " + D, D + "\n", hexits, "sha256:" + hexits[:-1], TAG, None):
            with self.subTest(digest=bad), self.assertRaises(ValueError):
                Grant.parse(tk.grant(scorer_image_digest=bad))


class ImageDigestTests(unittest.TestCase):
    """warden's P1 on #85 (at 3c7b3062) and root's (at ca3fc2be): the image a run attests is proved by digest, never by
    tag. A run is the build only when the bound evaluation receipt's image_digest, the signed grant's
    scorer_image_digest and the signed manifest's statistic.evaluator.build each equal, exactly, the well-formed
    (sha256: and 64 lower-case hex) image_digest builds.json records for that build. In every other case the attested
    image is absent: another string, which reads unvalidated. The test manifest's build is the test scorer image. The
    grants here are stand-ins shaped like P1's, each also carrying the tag that names the build, which must not help."""

    def setUp(self):
        self.manifest = tk.door_manifest()

    @staticmethod
    def receipt(digest=D) -> dict:
        receipt = {"binary_sha256": tk.EVALUATOR_BINARY_SHA256, "input_sha256": dict(tk.GATE0_INPUTS)}
        return receipt if digest is ABSENT else receipt | {"image_digest": digest}

    @staticmethod
    def grant(digest=D, tag=TAG):
        fields = {} if digest is ABSENT else {"scorer_image_digest": digest}
        return SimpleNamespace(**fields, **({} if tag is ABSENT else {"scorer_image_tag": tag}))

    @staticmethod
    def manifest_building(build) -> dict:
        """The test manifest with statistic.evaluator.build set to `build`, or without it (ABSENT)."""
        if build is ABSENT:
            manifest = tk.door_manifest()
            del manifest["statistic"]["evaluator"]["build"]
            return manifest
        return tk.door_manifest(**{"statistic.evaluator.build": build})

    def identity(self, receipt, grant, registered, manifest=None) -> str:
        text = evaluator_identity(receipt, self.manifest if manifest is None else manifest, grant,
                                  registered=registered)
        self.assertTrue(EVALUATOR.match(text), text)
        return text

    def assert_unvalidated(self, receipt, grant, registered, manifest=None):
        text = self.identity(receipt, grant, registered, manifest)
        self.assertNotEqual(BUILD["id"], text)
        self.assertEqual("unvalidated", label_for(text))

    def test_p1_another_images_digest_under_the_gate_zero_tag_reads_unvalidated(self):
        """warden's measured case: the 5cedde1 runtime's digest (cde9ce80...) with the tag sentilab-gate0:2d35e9c
        read reproduction_tested at 3c7b3062. It is another image: unvalidated under the real builds.json, under a
        registry recording the test digest and under one recording none, whether the signed manifest names the test
        image or, as the 5cedde1 deployment would sign it, cde9ce80 too (all three run-side digests agreeing)."""
        for name, registered in (("builds.json", None), ("a test digest", registry(D)), ("no digest", registry(None))):
            for manifest_build in (D, CDE9):
                with self.subTest(name, manifest_build=manifest_build):
                    self.assert_unvalidated(self.receipt(CDE9), self.grant(CDE9), registered,
                                            self.manifest_building(manifest_build))
        with self.assertRaises(ValueError, msg="a signed grant names no image tag"):
            Grant.parse(tk.grant(scorer_image_digest=CDE9, scorer_image_tag=TAG))

    def test_the_receipt_and_the_grant_must_name_the_same_digest(self):
        for receipt, grant in ((D, OTHER), (OTHER, D), (D, CDE9), (CDE9, D)):
            with self.subTest(receipt=receipt, grant=grant):
                self.assert_unvalidated(self.receipt(receipt), self.grant(grant), registry(D))

    def test_agreeing_is_not_enough_all_must_be_the_recorded_digest(self):
        """The receipt and the grant agreeing, or all three run-side digests agreeing (the manifest's build too), on a
        digest the registry does not record is another image."""
        for digest in (OTHER, CDE9):
            for manifest_build in (D, digest):
                with self.subTest(digest, manifest_build=manifest_build):
                    self.assert_unvalidated(self.receipt(digest), self.grant(digest), registry(D),
                                            self.manifest_building(manifest_build))

    def test_a_missing_or_malformed_digest_reads_unvalidated(self):
        hexits = D[len("sha256:"):]
        malformed = ["sha256:" + hexits.upper(), "SHA256:" + hexits, "Sha256:" + hexits, " " + D, D + " ", D + "\n",
                     "\t" + D, D + "\u200b", "sha256:" + hexits[:32] + "\u200b" + hexits[32:], "sha256: " + hexits,
                     "sha256:\uff10" + hexits[1:], hexits, "sha256:" + hexits[:-1], "sha256:" + hexits + "0",
                     "sha256:" + hexits[:-1] + "g", "sha512:" + hexits, "", None, 7, [D], D.encode()]
        cases = [("no image digest in the receipt", self.receipt(ABSENT), self.grant(D)),
                 ("no scorer image digest in the grant", self.receipt(D), self.grant(ABSENT)),
                 ("no grant", self.receipt(D), None),
                 ("no receipt", None, self.grant(D)),
                 ("neither has one", self.receipt(ABSENT), self.grant(ABSENT))]
        for bad in malformed:
            cases += [(f"receipt {bad!r}", self.receipt(bad), self.grant(D)),
                      (f"grant {bad!r}", self.receipt(D), self.grant(bad)),
                      (f"receipt and grant {bad!r}", self.receipt(bad), self.grant(bad))]
        for name, receipt, grant in cases:
            with self.subTest(name):
                self.assert_unvalidated(receipt, grant, registry(D))
        # A malformed digest is no digest, even as recorded: the same malformed value everywhere (receipt, grant,
        # manifest build and registry) never matches.
        for bad in malformed:
            with self.subTest(recorded=bad):
                self.assert_unvalidated(self.receipt(bad), self.grant(bad), registry(bad), self.manifest_building(bad))

    def test_a_build_with_no_recorded_digest_is_never_matched(self):
        """null never equals null here: a build whose image_digest is null, or not recorded at all, matches no run,
        not even one that carries no digest either."""
        no_field = ({key: value for key, value in BUILD.items() if key != "image_digest"},)
        runs = [("the run carries the test digest", self.receipt(D), self.grant(D)),
                ("the run carries cde9ce80", self.receipt(CDE9), self.grant(CDE9)),
                ("the receipt has none", self.receipt(ABSENT), self.grant(D)),
                ("neither has one", self.receipt(ABSENT), self.grant(ABSENT)),
                ("both are null", self.receipt(None), self.grant(None)),
                ("no grant and no receipt digest", self.receipt(ABSENT), None)]
        for registered_name, registered in (("builds.json", None), ("null", registry(None)), ("no field", no_field)):
            for name, receipt, grant in runs:
                with self.subTest(registry=registered_name, run=name):
                    self.assert_unvalidated(receipt, grant, registered)
            for build in (None, ABSENT):
                with self.subTest(registry=registered_name, run="no digest anywhere, the manifest's build too",
                                  manifest_build=build):
                    self.assert_unvalidated(self.receipt(None), self.grant(None), registered,
                                            self.manifest_building(build))

    def test_root_p1_the_signed_manifests_build_must_be_the_recorded_digest(self):
        """root's P1 on #85 (at ca3fc2be): the signed manifest's statistic.evaluator.build is the fourth digest. With
        receipt, grant and registry all D, a manifest build that is anything but exactly D reads unvalidated: another
        well-formed digest, null (a draft placeholder, never a match), absent, upper case, padded, a tag."""
        hexits = D[len("sha256:"):]
        builds_named = [("another image's digest", OTHER), ("the 5cedde1 runtime's digest", CDE9), ("null", None),
                        ("absent", ABSENT), ("upper-case hex", "sha256:" + hexits.upper()),
                        ("an upper-case prefix", "SHA256:" + hexits), ("a leading space", " " + D),
                        ("a trailing newline", D + "\n"), ("the gate-zero tag", TAG),
                        ("the 5cedde1 tag", "sentilab-gate0:5cedde1"), ("bare hex", hexits), ("empty", ""),
                        ("a list", [D])]
        for name, value in builds_named:
            with self.subTest(name):
                self.assert_unvalidated(self.receipt(D), self.grant(D), registry(D), self.manifest_building(value))
        # The same run with the manifest's build exactly D is the build: the fourth digest is the only change.
        text = self.identity(self.receipt(D), self.grant(D), registry(D), self.manifest_building(D))
        self.assertEqual((BUILD["id"], "reproduction_tested"), (text, label_for(text)))

    def test_positive_control_the_recorded_digest_on_both_sides_names_the_build(self):
        """With a test-only registry recording digest D for the build, a run whose receipt and signed grant both
        carry D is the build, whatever tag (if any) is about: the tag never decides."""
        signed = Grant.parse(tk.grant())
        self.assertEqual((D, D), (signed.scorer_image_digest, self.manifest["statistic"]["evaluator"]["build"]),
                         "the test grant and the test manifest pin the test scorer image")
        for grant in (signed, self.grant(D, tag=ABSENT), self.grant(D), self.grant(D, tag="sentilab-gate0:0000000"),
                      self.grant(D, tag=None)):
            with self.subTest(grant=grant):
                text = self.identity(self.receipt(D), grant, registry(D))
                self.assertEqual((BUILD["id"], "reproduction_tested"), (text, label_for(text)))
        self.assertEqual(BUILD["identity"], attested(registry(D)[0], self.receipt(D), self.manifest, signed))
        # The same run under the real builds.json, which records no digest for the gate-zero image: unvalidated.
        self.assert_unvalidated(self.receipt(D), signed, None)


class DoorImageDigestTests(tk.DoorCase, unittest.TestCase):
    """The same rule through the door: a signed binding pinning the test scorer image, the fake scorer's receipts
    naming an image, under a test registry recording the test image's digest for the build (builds.json records
    none)."""

    def setUp(self):
        patcher = mock.patch.object(builds, "registered", return_value=registry(D))
        patcher.start()
        self.addCleanup(patcher.stop)
        super().setUp()

    def test_positive_control_a_run_on_the_recorded_image_reads_reproduction_tested(self):
        result = scored(self, moved(30))["result"]
        self.assertEqual((BUILD["id"], "reproduction_tested"), (result["evaluator"], result["temperature_label"]))

    def test_the_real_registry_reads_the_same_run_unvalidated(self):
        with mock.patch.object(builds, "registered", return_value=builds.load()):
            result = scored(self, moved(31))["result"]
        self.assertNotEqual(BUILD["id"], result["evaluator"])
        self.assertEqual("unvalidated", result["temperature_label"])

    def test_a_receipt_naming_another_image_or_none_reads_unvalidated(self):
        """door-scorer's client refuses such a receipt before it counts; the label fails closed on its own too."""
        for index, digest in enumerate((OTHER, CDE9, None)):
            with self.subTest(digest):
                self.scorer.image_digest = digest
                result = scored(self, moved(32 + index), nonce=tk.nonce(60 + index))["result"]
                self.assertNotEqual(BUILD["id"], result["evaluator"])
                self.assertEqual("unvalidated", result["temperature_label"])


class DoorP1Tests(tk.DoorCase, unittest.TestCase):
    """warden's measured case through the door, as the 5cedde1 deployment would sign it: the manifest's build and the
    binding both pin the 5cedde1 runtime's digest and its receipts name it, so all three run-side digests agree. The
    run attests that image, not the gate-zero build's: unvalidated under any registry that does not record it."""

    def policy_kwargs(self):
        return {"grant_value": tk.grant(scorer_image_digest=CDE9),
                "manifest": tk.door_manifest(**{"statistic.evaluator.build": CDE9})}

    def test_the_5cedde1_runtime_reads_unvalidated(self):
        self.scorer.image_digest = CDE9
        for index, (name, registered) in enumerate((("builds.json", builds.load()), ("a test digest", registry(D)),
                                                    ("no digest", registry(None)))):
            with self.subTest(name), mock.patch.object(builds, "registered", return_value=registered):
                result = scored(self, moved(40 + index), nonce=tk.nonce(70 + index))["result"]
                self.assertNotEqual(BUILD["id"], result["evaluator"])
                self.assertEqual("unvalidated", result["temperature_label"])


class DoorManifestBuildTests(tk.DoorCase, unittest.TestCase):
    """root's P1 through the door: the signed manifest names another build (a well-formed digest, as a signed manifest
    must) while the binding pins, and the receipts name, the image the test registry records. Unvalidated."""

    def policy_kwargs(self):
        return {"manifest": tk.door_manifest(**{"statistic.evaluator.build": OTHER})}

    def setUp(self):
        patcher = mock.patch.object(builds, "registered", return_value=registry(D))
        patcher.start()
        self.addCleanup(patcher.stop)
        super().setUp()

    def test_a_manifest_naming_another_build_reads_unvalidated(self):
        self.assertTrue(self.policy.usable, self.policy.problems)
        result = scored(self, moved(50))["result"]
        self.assertNotEqual(BUILD["id"], result["evaluator"])
        self.assertEqual("unvalidated", result["temperature_label"])

    def test_a_manifest_whose_build_is_not_a_digest_keeps_the_door_closed(self):
        """A signed manifest pins its build as a sha256 digest (schema and record rules): null, upper case or a tag
        never reaches a run at all."""
        hexits = D[len("sha256:"):]
        for build in (None, "sha256:" + hexits.upper(), TAG, " " + D):
            with self.subTest(build=build):
                policy = tk.policy(clock=self.clock, manifest=tk.door_manifest(**{"statistic.evaluator.build": build}))
                self.assertFalse(policy.usable)
                self.assertIn("manifest fails the contract's record rules", policy.problems)


class DoorLabelTests(tk.DoorCase, unittest.TestCase):
    """Through the door: submit, score, settle and read the results feed, under the test registry, with the signed
    binding pinning the test scorer image and the fake scorer's receipts naming it."""

    def setUp(self):
        patcher = mock.patch.object(builds, "registered", return_value=registry(D))
        patcher.start()
        self.addCleanup(patcher.stop)
        super().setUp()

    def test_an_exact_run_reads_reproduction_tested(self):
        result = scored(self, moved(0))["result"]
        self.assertEqual((BUILD["id"], "reproduction_tested"), (result["evaluator"], result["temperature_label"]))

    def test_a_run_staging_another_package_file_reads_unvalidated(self):
        self.scorer.inputs = {"sampleL2_Interposer.flp": tk.fake("another interposer")}
        result = scored(self, moved(1))["result"]
        self.assertNotEqual(BUILD["id"], result["evaluator"])
        self.assertEqual("unvalidated", result["temperature_label"])
        self.assertEqual(BUILD["id"].split(":config_sha256:")[0], result["evaluator"].split(":config_sha256:")[0])

    def test_a_receipt_naming_another_binary_reads_unvalidated(self):
        self.scorer.binary_sha256 = tk.fake("another binary")
        result = scored(self, moved(2))["result"]
        self.assertIn(":binary_sha256:" + tk.fake("another binary") + ":", result["evaluator"])
        self.assertEqual("unvalidated", result["temperature_label"])

    def test_hard_rule_the_build_label_changes_nothing_else(self):
        """The same submissions scored the same way by two scorer images, each pinned by its door's binding and named
        by its receipts: the one the registry records for the build, and another. Every field of every item is
        identical except result.evaluator and result.temperature_label. The runs cover a score without a grid (per-die
        and wire basis only), one with its grid, a replay that did not reproduce, one that was not a fresh process, a
        binding mismatch and a wire mismatch."""
        with tempfile.TemporaryDirectory() as folder:
            policy = tk.policy(clock=self.clock, grant_value=tk.grant(scorer_image_digest=OTHER))
            other = Door(policy, Store(Path(folder) / "other.sqlite3"),
                         tk.FakeScorer(policy.checker, image_digest=OTHER))
            other.start(workers=False)
            try:
                runs = (("ok", False), ("ok", True), ("mismatch", True), ("not_fresh", False),
                        ("bad_binding", True), ("bad_wire", False))
                built, elsewhere = [], []
                for index, (mode, with_grid) in enumerate(runs):
                    for door, out in ((self.door, built), (other, elsewhere)):
                        door.scorer.mode, door.scorer.with_grid = mode, with_grid
                        out.append(scored(self, moved(4 + index), door, tk.nonce(20 + index)))
            finally:
                other.stop()
        for item in built:
            self.assertEqual(("reproduction_tested", BUILD["id"]),
                             (item["result"]["temperature_label"], item["result"]["evaluator"]))
        for item in elsewhere:
            self.assertEqual("unvalidated", item["result"]["temperature_label"])
            self.assertNotEqual(BUILD["id"], item["result"]["evaluator"])

        def without_label(item):
            item = json.loads(json.dumps(item))
            del item["result"]["temperature_label"], item["result"]["evaluator"]
            return item

        self.assertEqual([without_label(item) for item in elsewhere], [without_label(item) for item in built])
        # And the qualifiers are really there, beside the build's label.
        by_mode = dict(zip((mode for mode, _grid in runs), built))
        self.assertEqual("reproduced", by_mode["ok"]["status"])
        self.assertEqual(("not_reproduced", "not_reproduced", None), (
            by_mode["mismatch"]["status"], by_mode["mismatch"]["result"]["verification"]["replay"],
            by_mode["mismatch"]["verdict"]))
        self.assertFalse(by_mode["not_fresh"]["result"]["verification"]["distinct_execution"])
        self.assertEqual((False, False), (by_mode["bad_binding"]["result"]["binding_ok"],
                                          by_mode["bad_binding"]["result"]["verification"]["candidate"]))
        self.assertFalse(by_mode["bad_wire"]["result"]["binding_ok"])
        self.assertIsNone(built[0]["result"]["grid64"])
        self.assertEqual(["per_die", "wire"], built[0]["result"]["verification"]["binding_basis"])
        self.assertEqual(["per_die", "grid", "wire"], built[1]["result"]["verification"]["binding_basis"])
        for item in built:
            self.assertEqual(["beat", "margin", "routed wire", "source acceptance"],
                             item["result"]["verification"]["not_claimed"])


def fixture_body(registered=None) -> dict:
    """This door's results body for a fixed sequence under `registered`, by default the test registry (the build
    recording the test scorer image's digest, which the test binding pins and the fake scorer's receipts name): three
    runs of the gate-zero build (a reproduced score, a replay that did not reproduce, a binding mismatch), none with a
    grid, and one run whose receipt staged another package-layer file."""
    registered = registry(D) if registered is None else registered
    with tempfile.TemporaryDirectory() as folder, mock.patch.object(builds, "registered", return_value=registered):
        clock = tk.Clock()
        policy = tk.policy(clock=clock)
        door = Door(policy, Store(Path(folder) / "door.sqlite3"), tk.FakeScorer(policy.checker))
        door.start(workers=False)
        try:
            for index, (mode, inputs) in enumerate((
                    ("ok", {}), ("mismatch", {}), ("bad_binding", {}),
                    ("ok", {"sampleL2_Interposer.flp": tk.fake("another interposer")}))):
                door.scorer.mode, door.scorer.inputs = mode, inputs
                claims = {"purpose": "place-chiplets", "case": "cpu-dram", "nonce": tk.nonce(40 + index),
                          "exp": int(clock()) + 600}
                body = {"token_claims": claims, "layout": moved(10 + index), "terms": tk.TERMS,
                        "class": "declared_agent"}
                status, reply, _ = door.submit(json.dumps(body).encode())
                if status != 202:
                    raise RuntimeError(f"fixture submission refused: {reply}")
                while door.dispatcher.run_once():
                    pass
            return door.results(None, "20")[1]
        finally:
            door.stop()


def fixture_bytes() -> bytes:
    return (json.dumps(fixture_body(), indent=1, ensure_ascii=False) + "\n").encode("utf-8")


class PageFixtureTests(unittest.TestCase):
    def test_the_page_fixture_is_this_apis_output(self):
        """The page tests read the API's own output, so the seam cannot drift (--write-fixture regenerates it)."""
        self.assertEqual(fixture_bytes(), FIXTURE.read_bytes())

    def test_the_fixture_holds_what_the_page_tests_rely_on(self):
        items = json.loads(FIXTURE.read_bytes())["items"]
        self.assertEqual(["reproduction_tested"] * 3 + ["unvalidated"],
                         [item["result"]["temperature_label"] for item in items])
        self.assertEqual([BUILD["id"]] * 3, [item["result"]["evaluator"] for item in items[:3]])
        self.assertEqual(["reproduced", "not_reproduced", "reproduced", "reproduced"], [item["status"] for item in items])
        self.assertEqual([True, True, False, True], [item["result"]["binding_ok"] for item in items])
        self.assertEqual([None] * 4, [item["result"]["grid64"] for item in items])

    def test_under_builds_json_every_fixture_run_reads_unvalidated(self):
        """builds.json records no digest for the gate-zero image: under it, the same four runs all read unvalidated."""
        items = fixture_body(builds.load())["items"]
        self.assertEqual(["unvalidated"] * 4, [item["result"]["temperature_label"] for item in items])
        self.assertNotIn(BUILD["id"], [item["result"]["evaluator"] for item in items])


if __name__ == "__main__":
    if "--write-fixture" in sys.argv:
        FIXTURE.write_bytes(fixture_bytes())
        print(f"wrote {FIXTURE}")
    else:
        unittest.main()
