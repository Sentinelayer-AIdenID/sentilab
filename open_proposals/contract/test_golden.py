"""The shared contract tests: every golden case and every vector in contracts/open-proposal-v1, against the Python
reference. The JavaScript twin runs the same vectors (run-vectors.mjs); test_javascript_twin runs it from here too.

    python -m unittest -q open_proposals.contract.test_golden
"""
from __future__ import annotations

import base64
import hashlib
import json
import shutil
import subprocess
import unittest

from sentilab_core.envelope import canonical

from . import canonical as h
from . import make_vectors
from .schemas import CONTRACT_DIR
from .states import (SUMMARY, Entry, OrderError, Revision, TransitionRefused, created_at_ns, decide_revision,
                     order_key, sort_replies, transition)
from .validator import Reply, validate_check_note, validate_check_request, validate_record, validate_submission

GOLDEN = CONTRACT_DIR / "golden"


def load(name):
    return json.loads((GOLDEN / name).read_bytes())


MANIFESTS = load("manifests.json")
BY_KEY = MANIFESTS["manifests"]
REGISTRY = {MANIFESTS["manifest_id"][key]: manifest for key, manifest in BY_KEY.items()}
VECTORS = json.loads((CONTRACT_DIR / "vectors-canonical.json").read_bytes())
LIMITS = json.loads((CONTRACT_DIR / "limits.provisional.json").read_bytes())
PSEUDONYM_KEY = hashlib.sha256(VECTORS["test_phrases"]["pseudonym_key"].encode()).digest()
CLIENT_SECRET = hashlib.sha256(VECTORS["test_phrases"]["client_secret"].encode()).digest()


def note_bytes(case) -> bytes:
    return case["note"].encode("utf-8") if "note" in case else base64.b64decode(case["note_b64"])


def ids(name):
    return MANIFESTS["manifest_id"][name]


class GoldenNotes(unittest.TestCase):
    def test_every_note_case(self):
        cases = load("notes.json")["cases"]
        self.assertGreater(len(cases), 60)
        for case in cases:
            with self.subTest(case["name"]):
                if case["route"] == "intake":
                    reply = Reply(**case["reply"])
                    admission = {ids(key): state for key, state in case["admission"].items()}
                    outcome = validate_submission(note_bytes(case), reply=reply, manifests=REGISTRY,
                                                  thread_manifest_id=ids(case["thread_manifest"]),
                                                  admission=admission)
                else:
                    outcome = validate_check_note(note_bytes(case), manifests=REGISTRY,
                                                  manifest_id=ids(case["manifest"]))
                self.assertEqual(case["expect"]["outcome"], outcome.outcome)
                self.assertEqual(case["expect"]["codes"], list(outcome.violations))

    def test_the_check_and_the_intake_agree_on_every_shared_vector(self):
        """T12: the same bytes give the same codes at the check and the intake, admission and chat aside."""
        for case in load("notes.json")["cases"]:
            if case["route"] != "intake" or case["admission"] != {case["thread_manifest"]: "open"}:
                continue
            if case["reply"] != {"actor_user_id": make_vectors.HUMAN, "message_revision": 1, "edited_at": None}:
                continue
            if case["expect"]["outcome"] == "ignored" or {"not_open_yet", "manifest_closed"} & {
                    code["code"] for code in case["expect"]["codes"]}:
                continue
            with self.subTest(case["name"]):
                check = validate_check_note(note_bytes(case), manifests=REGISTRY,
                                            manifest_id=ids(case["thread_manifest"]))
                self.assertEqual(case["expect"]["outcome"], check.outcome)
                self.assertEqual(case["expect"]["codes"], list(check.violations))

    def test_valid_notes_in_every_framing_hash_the_same(self):
        cases = {case["name"]: case for case in load("notes.json")["cases"]}
        framings = ["valid proposal, bare JSON", "valid proposal in a json fence",
                    "valid proposal in a json fence with CRLF line ends", "valid proposal padded to exactly 4096 bytes"]
        hashes = set()
        for name in framings:
            outcome = validate_check_note(note_bytes(cases[name]), manifests=REGISTRY, manifest_id=ids("F"))
            hashes.add((outcome.proposal_sha256, outcome.geometry_sha256))
        self.assertEqual({(h.proposal_sha256(make_vectors.P_F), make_vectors.P_F["geometry_sha256"])}, hashes)
        bodies = {h.body_sha256(note_bytes(cases[name])) for name in framings}
        self.assertEqual(len(framings), len(bodies), "body_sha256 binds the exact bytes, framing included")


class GoldenCheckRequests(unittest.TestCase):
    def test_every_check_request(self):
        for case in load("check-requests.json")["cases"]:
            with self.subTest(case["name"]):
                outcome = validate_check_request(case["request"], manifests=REGISTRY)
                self.assertEqual(case["expect"]["outcome"], outcome.outcome)
                self.assertEqual(case["expect"]["codes"], list(outcome.violations))


class GoldenRecords(unittest.TestCase):
    def test_every_record(self):
        cases = load("records.json")["cases"]
        kinds = {case["kind"] for case in cases}
        self.assertEqual({"manifest", "geometry", "sealed", "check_request", "check", "receipt", "restricted_receipt",
                          "status", "results", "error", "limits", "usage", "cursor", "current", "private_request",
                          "reason_codes"}, kinds)
        for kind in kinds:
            outcomes = {bool(case["expect"]) for case in cases if case["kind"] == kind}
            self.assertEqual({True, False}, outcomes, f"{kind} needs valid and invalid examples")
        for case in cases:
            with self.subTest(f'{case["kind"]}: {case["name"]}'):
                context = case["context"]
                found = validate_record(case["kind"], case["record"],
                                        manifest=BY_KEY[context["manifest"]] if context["manifest"] else None,
                                        limits=LIMITS if context["limits"] else None,
                                        pseudonym_key=PSEUDONYM_KEY if context["pseudonym"] else None,
                                        audience=context["audience"])
                self.assertEqual(case["expect"], found)

    def test_the_draft_manifests_are_published_ids(self):
        for key, manifest in BY_KEY.items():
            self.assertEqual(ids(key), h.manifest_id(manifest))
        self.assertEqual({"A": "draft", "M": "draft", "F": "frozen"},
                         {key: manifest["status"] for key, manifest in BY_KEY.items()})


class GoldenStates(unittest.TestCase):
    TABLE = load("states.json")

    def entry(self, state):
        return Entry(None if state == "none" else state)

    def test_every_allowed_and_every_forbidden_lifecycle_transition(self):
        table, events = self.TABLE["allowed"], self.TABLE["good_payload"]
        lifecycle_events = [event for event in events if event not in ("withdraw", "restore", "hide", "unhide")]
        checked = 0
        for state, allowed in table.items():
            for event in lifecycle_events:
                with self.subTest(state=state, event=event):
                    payload = events[event]
                    if event in allowed:
                        self.assertEqual(Entry(allowed[event]), transition(self.entry(state), event, payload))
                    else:
                        with self.assertRaises(TransitionRefused):
                            transition(self.entry(state), event, payload)
                    checked += 1
        self.assertEqual(len(table) * len(lifecycle_events), checked)

    def test_every_guard(self):
        for case in self.TABLE["guards"]:
            with self.subTest(event=case["event"], payload=case["payload"]):
                start = self.entry(case["from"])
                good = self.TABLE["good_payload"][case["event"]]
                if case["event"] in ("restore",):
                    start = transition(start, "withdraw", {"operator": True})
                transition(start, case["event"], good)          # the good payload passes from this state
                with self.assertRaises(TransitionRefused):
                    transition(start, case["event"], case["payload"])

    def test_overlays(self):
        for case in self.TABLE["overlays"]:
            with self.subTest(case["name"]):
                entry = self.entry(case["from"])

                def run():
                    current = entry
                    for event, payload in case["events"]:
                        current = transition(current, event, payload)
                    return current
                if case["expect"] == "refused":
                    with self.assertRaises(TransitionRefused):
                        run()
                else:
                    result = run()
                    self.assertEqual(case["expect"], {"lifecycle": result.lifecycle, "withdrawn": result.withdrawn,
                                                      "hidden": result.hidden})

    def test_withdrawn_shows_publicly_and_restore_reveals_the_lifecycle(self):
        entry = transition(Entry("evaluating"), "withdraw", {"operator": True})
        self.assertEqual("withdrawn", entry.public_state)
        entry = transition(entry, "fail", {"settled": True, "code": "interrupted"})
        self.assertEqual("withdrawn", entry.public_state)
        self.assertEqual("failed", transition(entry, "restore", {"operator": True}).public_state)

    def test_the_four_contract_states(self):
        self.assertEqual(self.TABLE["summary"], SUMMARY)


class GoldenRevisions(unittest.TestCase):
    def test_every_revision_case(self):
        for case in load("revisions.json")["cases"]:
            with self.subTest(case["name"]):
                history = [Revision(item["index"], item["proposal_key"], item["proposal_sha256"],
                                    item["geometry_sha256"], tuple(item["order"])) for item in case["history"]]
                submission = dict(case["submission"], order=tuple(case["submission"]["order"]))
                if case["expect"] == "order_error":
                    with self.assertRaises(OrderError):
                        decide_revision(history, **submission)
                    continue
                decision = decide_revision(history, **submission)
                self.assertEqual(case["expect"], {"kind": decision.kind, "revision_index": decision.revision_index,
                                                  "codes": list(decision.codes)})


class GoldenOrder(unittest.TestCase):
    TABLE = load("order.json")

    def test_replies_sort_by_numeric_time_then_action_then_room(self):
        rows = self.TABLE["rows"]
        self.assertEqual(self.TABLE["expect_order"], [row["label"] for row in sort_replies(rows)])
        self.assertEqual(self.TABLE["expect_order"], [row["label"] for row in sort_replies(list(reversed(rows)))])
        self.assertNotEqual(self.TABLE["expect_order"], [row["label"] for row in sorted(rows, key=lambda row: (
            row["createdAt"], row["id"], row["sessionId"]))], "text order is the hazard this rule exists for")

    def test_exact_nanoseconds_and_refusals(self):
        for case in self.TABLE["expect_ns"]:
            self.assertEqual(case["ns"], created_at_ns(case["createdAt"]), case["createdAt"])
        for text in self.TABLE["invalid"]:
            with self.subTest(text):
                with self.assertRaises(ValueError):
                    created_at_ns(text)
        self.assertEqual((0, "a", "b"), order_key({"createdAt": "1970-01-01T00:00:00Z", "id": "a", "sessionId": "b"}))


class Vectors(unittest.TestCase):
    def test_canonical_bytes(self):
        for case in VECTORS["canonical"]:
            with self.subTest(case["name"]):
                self.assertEqual(case["canonical"].encode(), canonical(case["value"]))
                self.assertEqual(case["sha256"], hashlib.sha256(canonical(case["value"])).hexdigest())

    def test_hashes(self):
        for case in VECTORS["manifest_id"]:
            self.assertEqual(case["manifest_id"], h.manifest_id(BY_KEY[case["manifest"]]))
        for case in VECTORS["geometry"]:
            manifest = BY_KEY[case["manifest"]]
            self.assertEqual(case["object"], h.geometry_object(case["proposal"], manifest))
            self.assertEqual(case["canonical"].encode(), canonical(case["object"]))
            self.assertEqual(case["geometry_sha256"], h.geometry_sha256(case["proposal"], manifest))
            self.assertEqual(case["geometry_sha256"], case["proposal"]["geometry_sha256"])
        for case in VECTORS["proposal"]:
            self.assertEqual(case["canonical"].encode(), canonical(case["proposal"]))
            self.assertEqual(case["proposal_sha256"], h.proposal_sha256(case["proposal"]))
        for case in VECTORS["body_sha256"]:
            self.assertEqual(case["body_sha256"], h.body_sha256(base64.b64decode(case["note_b64"])))
        for case in VECTORS["source_ref"]:
            self.assertEqual(case["source_ref"], h.source_ref(case["action_id"]))
        for case in VECTORS["participant_ref"]:
            self.assertEqual(case["participant_ref"],
                             h.participant_ref(PSEUDONYM_KEY, case["challenge"], case["account_id"]))
        for case in VECTORS["transport_id"]:
            expected = case.pop("transport_id")
            self.assertEqual(expected, h.transport_id(**case))
            self.assertLessEqual(len(expected), h.TRANSPORT_MAX_LENGTH)
            case["transport_id"] = expected
        for case in VECTORS["run_id"]:
            self.assertEqual(case["run_id"], h.run_id(case["manifest_id"], case["participant_ref"]))
        for case in VECTORS["salt"]:
            self.assertEqual(case["salt"], h.derive_salt(CLIENT_SECRET, case["manifest_id"], case["proposal_key"]))
        for case in VECTORS["capability"]:
            self.assertEqual(case["capability"], h.capability(case["salt"], case["manifest_id"],
                                                              case["proposal_sha256"], case["epoch"]))
            self.assertEqual(case["capability_sha256"], h.capability_sha256(case["capability"]))
        for case in VECTORS["ciphertext_ref"]:
            self.assertEqual(case["ciphertext_ref"], h.ciphertext_ref(base64.b64decode(case["age_file_b64"])))
        for case in VECTORS["conductor_geometry"]:
            self.assertEqual(case["values"], h.conductor_geometry(case["proposal"], BY_KEY[case["manifest"]]))

    def test_the_salt_hides_the_plaintext_hash_but_not_the_geometry(self):
        public, sealed = VECTORS["proposal"][1], VECTORS["proposal"][2]
        self.assertNotEqual(public["proposal_sha256"], sealed["proposal_sha256"])
        geometry = {case["name"]: case["geometry_sha256"] for case in VECTORS["geometry"]}
        self.assertEqual(geometry["the two-die layout"], geometry["a sealed plaintext: same geometry, unsalted hash"])

    def test_no_age_ciphertext_is_claimed(self):
        self.assertEqual([], VECTORS["age"]["vectors"])
        self.assertIn("TODO", VECTORS["age"]["todo"].upper())


class Generated(unittest.TestCase):
    def test_committed_files_match_the_generator(self):
        self.assertEqual(0, make_vectors.main(["--check"]))

    def test_javascript_twin_runs_the_same_vectors(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "node is required: the contract is checked in Python and JavaScript")
        result = subprocess.run([node, "run-vectors.mjs"], cwd=CONTRACT_DIR, capture_output=True, text=True,
                                check=False)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("vectors passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
