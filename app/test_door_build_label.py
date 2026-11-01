"""The reproduction-tested build label at the door (contracts/open-proposal-v1/builds.json, app/door/evaluator.py).

Every scored result's evaluator is the full identity string its run attests: the signed manifest's engine commit,
grid and centre mapping; the bound receipt's binary and every configuration file hash; and the image tag the signed
binding names. It reads "reproduction_tested" only when all of them are the gate-zero build's; any single field off,
or no tag, is another string, which reads unvalidated. The broad alias still reads unvalidated. Hard rule: the label
changes nothing else. A result's own qualifiers (replay status, binding basis and mismatch, a missing grid, the guard,
the candidate verdict) stay exactly as its verification says.

The page side reads the same API output: web/test/door-api-build-label.json is this door's results body for a fixed
sequence (test_the_page_fixture_is_this_apis_output keeps it current; regenerate it with
`python -m app.test_door_build_label --write-fixture`), and web/test/door-build-label.test.mjs runs the page's label
rule over it.
"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

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


class EvaluatorIdentityTests(unittest.TestCase):
    """The identity a run attests, over the signed manifest, the bound evaluation receipt and the grant."""

    def setUp(self):
        self.manifest = tk.door_manifest()
        self.grant = Grant.parse(tk.grant(scorer_image_tag=TAG))
        self.receipt = {"binary_sha256": tk.EVALUATOR_BINARY_SHA256, "input_sha256": dict(tk.GATE0_INPUTS)}

    def test_the_complete_build_reads_reproduction_tested(self):
        self.assertEqual(BUILD["identity"], attested(BUILD, self.receipt, self.manifest, self.grant))
        self.assertEqual(BUILD["id"], evaluator_identity(self.receipt, self.manifest, self.grant))
        self.assertEqual("reproduction_tested", label_for(BUILD["id"]))

    def test_each_single_field_mismatch_is_another_string_and_reads_unvalidated(self):
        inputs = self.receipt["input_sha256"]
        manifest = tk.door_manifest
        other_binary = tk.fake("another binary")
        cases = {
            "no image tag in the binding": (self.receipt, self.manifest, Grant.parse(tk.grant())),
            "another image tag": (self.receipt, self.manifest,
                                  Grant.parse(tk.grant(scorer_image_tag="sentilab-gate0:0000000"))),
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
                text = evaluator_identity(*args)
                self.assertNotEqual(BUILD["id"], text)
                self.assertNotEqual(ALIAS, text, "the run's own identity, never a constant")
                self.assertEqual("unvalidated", label_for(text))
                self.assertTrue(EVALUATOR.match(text), text)
                seen.add(text)
        # No grant and a grant without a tag attest the same thing (no image); every other mismatch is its own string.
        self.assertEqual(evaluator_identity(*cases["no grant"]), evaluator_identity(*cases["no image tag in the binding"]))
        self.assertEqual(len(cases) - 1, len(seen))
        # The readable fields are what the run attests.
        self.assertIn(":binary_sha256:" + other_binary + ":", evaluator_identity(*cases["another binary"]))
        self.assertIn(":grid:32x32:", evaluator_identity(*cases["another grid"]))
        self.assertTrue(evaluator_identity(*cases["another engine commit"]).startswith("HotSpot-6.0:" + "0" * 40 + ":"))

    def test_a_layouts_own_files_are_not_part_of_the_identity(self):
        """A door layout stages its own power trace and die-layer floorplans; the build is the same build."""
        receipt = self.receipt | {"input_sha256": tk.GATE0_INPUTS | {name: tk.fake(name) for name in tk.PER_LAYOUT}}
        self.assertEqual(BUILD["id"], evaluator_identity(receipt, self.manifest, self.grant))

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

    def test_the_image_tag_is_optional_and_strict(self):
        self.assertIsNone(Grant.parse(tk.grant()).scorer_image_tag)
        self.assertEqual(TAG, Grant.parse(tk.grant(scorer_image_tag=TAG)).scorer_image_tag)
        for bad in ("", "sentilab-gate0", "Sentilab-Gate0:2d35e9c", "sentilab-gate0: 2d35e9c", "x:" + "y" * 200,
                    None, 7, ["sentilab-gate0:2d35e9c"]):
            with self.subTest(repr(bad)), self.assertRaises(ValueError):
                Grant.parse(tk.grant(scorer_image_tag=bad))
        with self.assertRaises(ValueError):
            Grant.parse(tk.grant(scorer_image_tags=TAG))


class DoorLabelTests(tk.DoorCase, unittest.TestCase):
    """Through the door: submit, score, settle and read the results feed, under a binding that names the image tag."""

    def policy_kwargs(self):
        return {"grant_value": tk.grant(scorer_image_tag=TAG)}

    def scored(self, layout: str, door=None, nonce=tk.NONCE) -> dict:
        door = door or self.door
        status, reply, _ = door.submit(json.dumps(self.body(layout, nonce_value=nonce)).encode())
        self.assertEqual(status, 202, reply)
        while door.dispatcher.run_once():
            pass
        items = {item["id"]: item for item in door.results(None, "20")[1]["items"]}
        return items[reply["run_id"]]

    def test_an_exact_run_reads_reproduction_tested(self):
        result = self.scored(moved(0))["result"]
        self.assertEqual((BUILD["id"], "reproduction_tested"), (result["evaluator"], result["temperature_label"]))

    def test_a_run_staging_another_package_file_reads_unvalidated(self):
        self.scorer.inputs = {"sampleL2_Interposer.flp": tk.fake("another interposer")}
        result = self.scored(moved(1))["result"]
        self.assertNotEqual(BUILD["id"], result["evaluator"])
        self.assertEqual("unvalidated", result["temperature_label"])
        self.assertEqual(BUILD["id"].split(":config_sha256:")[0], result["evaluator"].split(":config_sha256:")[0])

    def test_a_receipt_naming_another_binary_reads_unvalidated(self):
        self.scorer.binary_sha256 = tk.fake("another binary")
        result = self.scored(moved(2))["result"]
        self.assertIn(":binary_sha256:" + tk.fake("another binary") + ":", result["evaluator"])
        self.assertEqual("unvalidated", result["temperature_label"])

    def test_hard_rule_the_build_label_changes_nothing_else(self):
        """The same submissions scored the same way under two bindings, one naming the image tag and one not. Every
        field of every item is identical except result.evaluator and result.temperature_label. The runs cover a score
        without a grid (per-die and wire basis only), one with its grid, a replay that did not reproduce, one that was
        not a fresh process, a binding mismatch and a wire mismatch."""
        with tempfile.TemporaryDirectory() as folder:
            policy = tk.policy(clock=self.clock, grant_value=tk.grant())
            plain = Door(policy, Store(Path(folder) / "plain.sqlite3"), tk.FakeScorer(policy.checker))
            plain.start(workers=False)
            try:
                runs = (("ok", False), ("ok", True), ("mismatch", True), ("not_fresh", False),
                        ("bad_binding", True), ("bad_wire", False))
                tagged, untagged = [], []
                for index, (mode, with_grid) in enumerate(runs):
                    for door, out in ((self.door, tagged), (plain, untagged)):
                        door.scorer.mode, door.scorer.with_grid = mode, with_grid
                        out.append(self.scored(moved(4 + index), door, tk.nonce(20 + index)))
            finally:
                plain.stop()
        for item in tagged:
            self.assertEqual(("reproduction_tested", BUILD["id"]),
                             (item["result"]["temperature_label"], item["result"]["evaluator"]))
        for item in untagged:
            self.assertEqual("unvalidated", item["result"]["temperature_label"])
            self.assertNotEqual(BUILD["id"], item["result"]["evaluator"])

        def without_label(item):
            item = json.loads(json.dumps(item))
            del item["result"]["temperature_label"], item["result"]["evaluator"]
            return item

        self.assertEqual([without_label(item) for item in untagged], [without_label(item) for item in tagged])
        # And the qualifiers are really there, beside the build's label.
        by_mode = dict(zip((mode for mode, _grid in runs), tagged))
        self.assertEqual("reproduced", by_mode["ok"]["status"])
        self.assertEqual(("not_reproduced", "not_reproduced", None), (
            by_mode["mismatch"]["status"], by_mode["mismatch"]["result"]["verification"]["replay"],
            by_mode["mismatch"]["verdict"]))
        self.assertFalse(by_mode["not_fresh"]["result"]["verification"]["distinct_execution"])
        self.assertEqual((False, False), (by_mode["bad_binding"]["result"]["binding_ok"],
                                          by_mode["bad_binding"]["result"]["verification"]["candidate"]))
        self.assertFalse(by_mode["bad_wire"]["result"]["binding_ok"])
        self.assertIsNone(tagged[0]["result"]["grid64"])
        self.assertEqual(["per_die", "wire"], tagged[0]["result"]["verification"]["binding_basis"])
        self.assertEqual(["per_die", "grid", "wire"], tagged[1]["result"]["verification"]["binding_basis"])
        for item in tagged:
            self.assertEqual(["beat", "margin", "routed wire", "source acceptance"],
                             item["result"]["verification"]["not_claimed"])


def fixture_body() -> dict:
    """This door's results body for a fixed sequence under a binding naming the image tag: three runs of the
    gate-zero build (a reproduced score, a replay that did not reproduce, a binding mismatch), none with a grid, and
    one run whose receipt staged another package-layer file."""
    with tempfile.TemporaryDirectory() as folder:
        clock = tk.Clock()
        policy = tk.policy(clock=clock, grant_value=tk.grant(scorer_image_tag=TAG))
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


if __name__ == "__main__":
    if "--write-fixture" in sys.argv:
        FIXTURE.write_bytes(fixture_bytes())
        print(f"wrote {FIXTURE}")
    else:
        unittest.main()
