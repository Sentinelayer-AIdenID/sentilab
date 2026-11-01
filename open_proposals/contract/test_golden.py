"""The golden examples (contracts/open-proposal-v1/golden), run through the reference: every outcome and code must
match the hand-written expectation. The files themselves must match their generator (make_vectors --check)."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import shutil
import subprocess
import unittest

from . import age_tools
from . import canonical as h
from .make_vectors import main as make_vectors_main
from .predicate_fixtures import cases as predicate_cases
from .schemas import CONTRACT_DIR
from .states import (CHARGED, EVENTS, FLAG_EVENTS, SUMMARY, Entry, OrderError, Prior, TransitionRefused, created_at_ns, decide,
                     decide_publish, sort_replies, transition)
from .validator import Reply, Unopenable, validate_local, validate_record, validate_reply

GOLDEN = CONTRACT_DIR / "golden"


def load(name: str):
    return json.loads((GOLDEN / name).read_bytes())


MANIFEST_FILE = load("manifests.json")
MANIFESTS = MANIFEST_FILE["manifests"]
VECTORS = json.loads((CONTRACT_DIR / "vectors-canonical.json").read_bytes())
OBJECTS = VECTORS["objects"]
AGE = json.loads((CONTRACT_DIR / "vectors-age.json").read_bytes())
SCALARS = {key["key_version"]: age_tools.identity_from_phrase(key["phrase"])[0] for key in AGE["keys"]}
K_CHALLENGE = hashlib.sha256(VECTORS["test_phrases"]["k_challenge"].encode()).digest()


def opener(armour: bytes, _manifest: dict, key_version: int) -> bytes:
    """The reference opener for the test identities, modelled on custody: it holds every key version, old ones
    included, and opens with the version it is given. Refusing a version the manifest does not pin is the
    validator's job, so this opener does not repeat it."""
    scalar = SCALARS.get(key_version)
    if scalar is None:
        raise Unopenable()
    try:
        return age_tools.reference_decrypt(age_tools.dearmor(armour), scalar)
    except ValueError:
        raise Unopenable() from None


def note_of(case) -> bytes:
    return case["note"].encode("utf-8") if "note" in case else base64.b64decode(case["note_b64"])


def stub(found):
    return None if found is None else (lambda _item, _manifest: copy.deepcopy(found))


def reply_of(row) -> Reply:
    """A golden row: Senti's idempotencyKey is stored as "idempotency" (no key-named field in the fixtures)."""
    fields = dict(row)
    fields["idempotency_key"] = fields.pop("idempotency")
    return Reply(**fields)


def run_note(case):
    manifests = {h.manifest_id(manifest): manifest for manifest in MANIFESTS.values()}
    target = MANIFEST_FILE["manifest_id"][case["manifest"]]
    kwargs = {"manifests": manifests, "layout_checker": stub(case["layout"]),
              "opener": opener if case["opener"] else None}
    if case["mode"] == "local":
        return validate_local(note_of(case), manifest_id=target, **kwargs)
    admission = {target: case["admission"]}
    return validate_reply(note_of(case), reply=reply_of(case["row"]), thread_manifest_id=target, admission=admission,
                          **kwargs)


def edit(value, path, new, delete=False):
    parts = path.strip("/").split("/")
    target = value
    for part in parts[:-1]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    last = int(parts[-1]) if isinstance(target, list) else parts[-1]
    if delete:
        del target[last]
    else:
        target[last] = new


def record_of(case):
    if "base" not in case:
        return case["record"]
    record = copy.deepcopy(MANIFESTS[case["base"]])
    for change in case["edits"]:
        edit(record, change["path"], change.get("value"), change.get("delete", False))
    return record


def context_of(case) -> dict:
    context = dict(case["context"])
    if "manifest" in context:
        context["manifest"] = MANIFESTS[context["manifest"]]
    if "item" in context:
        context["item"] = OBJECTS[context["item"]]
    if context.pop("k_challenge", False):
        context["k_challenge"] = K_CHALLENGE
    return context


class Files(unittest.TestCase):
    def test_the_files_match_their_generator(self):
        self.assertEqual(make_vectors_main(["--check"]), 0)

    @unittest.skipUnless(shutil.which("node"), "the JavaScript twin needs Node 20 or later")
    def test_the_javascript_twin_agrees(self):
        """T1: canonical.mjs reproduces every vector Python wrote (run-vectors.mjs)."""
        result = subprocess.run(["node", "run-vectors.mjs"], cwd=CONTRACT_DIR, capture_output=True, text=True,
                                check=False)
        self.assertEqual(0, result.returncode, result.stdout[-2000:] + result.stderr[-2000:])
        self.assertIn(" vectors passed, 0 failed", result.stdout)

    def test_the_predicate_fixtures_are_the_golden_ones(self):
        self.assertEqual(load("predicates.json")["cases"], json.loads(json.dumps(predicate_cases())))


class Notes(unittest.TestCase):
    def test_every_note(self):
        cases = load("notes.json")["cases"]
        self.assertGreaterEqual(len(cases), 90)
        for case in cases:
            with self.subTest(case["name"]):
                self.assertEqual(run_note(case).summary(), case["expect"])

    def test_every_reason_code_a_note_can_carry_is_exercised(self):
        seen = {code["code"] for case in load("notes.json")["cases"] for code in case["expect"]["codes"]}
        from_notes = {"oversize", "not_utf8", "edited_before_ingest", "unattributable", "private_requires_sealed",
                      "unsealable", "transport_key_mismatch", "malformed_json", "duplicate_key", "nonfinite_number",
                      "too_deep", "unknown_field", "schema_invalid", "unknown_manifest", "manifest_mismatch",
                      "manifest_closed", "not_open_yet", "terms_not_accepted", "die_count", "die_order",
                      "out_of_frame", "rotation_not_allowed", "lattice", "margin", "halo_overlap", "min_spacing",
                      "keepout", "geometry_hash_mismatch"}
        self.assertEqual(seen, from_notes)


class Records(unittest.TestCase):
    def test_every_record(self):
        for case in load("records.json")["cases"]:
            with self.subTest(case["kind"] + ": " + case["name"]):
                found = validate_record(case["kind"], record_of(case), **context_of(case))
                self.assertEqual(found, case["expect"])

    def test_every_record_rule_is_exercised(self):
        from .codes import RULES
        seen = {item["rule"] for case in load("records.json")["cases"] for item in case["expect"] if "rule" in item}
        self.assertEqual(seen, set(RULES))


class States(unittest.TestCase):
    def test_every_state_and_event(self):
        table = load("states.json")
        for pair in table["pairs"]:
            with self.subTest(f"{pair['state']} {pair['event']} hidden={pair['hidden']} {pair['visibility']}"):
                entry = Entry(pair["state"], pair["hidden"], pair["visibility"])
                if pair["expect"] is None:
                    with self.assertRaises(TransitionRefused):
                        transition(entry, pair["event"], pair["payload"])
                else:
                    after = transition(entry, pair["event"], pair["payload"])
                    self.assertEqual({"state": after.state, "hidden": after.hidden, "visibility": after.visibility},
                                     pair["expect"])
                    self.assertEqual(entry, Entry(pair["state"], pair["hidden"], pair["visibility"]))  # not mutated

    def test_the_table_covers_every_event(self):
        events = {pair["event"] for pair in load("states.json")["pairs"]}
        self.assertEqual(set(EVENTS) | set(FLAG_EVENTS), events)

    def test_every_guard_refuses(self):
        for guard in load("states.json")["guards"]:
            with self.subTest(guard["name"]):
                with self.assertRaises(TransitionRefused):
                    transition(Entry(guard["state"], guard["hidden"], guard["visibility"]), guard["event"],
                               guard["payload"])

    def test_the_contract_states_and_quota_charge(self):
        table = load("states.json")
        self.assertEqual(SUMMARY, table["summary"])
        self.assertEqual(CHARGED, table["charged"])


class Revisions(unittest.TestCase):
    def test_every_decision(self):
        for case in load("revisions.json")["cases"]:
            with self.subTest(case["name"]):
                history = [Prior(**prior | {"order": tuple(prior["order"])}) for prior in case["history"]]
                if case["decide"] == "publish":
                    found = decide_publish(history, proposal_sha256=case["proposal_sha256"],
                                           order=tuple(case["order"]))
                    self.assertEqual(list(found), case["expect"])
                    continue
                arguments = {"kind": case["kind"], "logical_key": case["logical_key"],
                             "content_sha256": case["content_sha256"], "parent": case["parent"],
                             "order": tuple(case["order"])}
                if case["expect"] == "order_error":
                    with self.assertRaises(OrderError):
                        decide(history, **arguments)
                    continue
                decision = decide(history, **arguments)
                self.assertEqual({"kind": decision.kind, "revision_index": decision.revision_index,
                                  "codes": list(decision.codes)}, case["expect"])


class Order(unittest.TestCase):
    def test_the_section_3_4_order(self):
        table = load("order.json")
        self.assertEqual([row["label"] for row in sort_replies(table["rows"])], table["expect_order"])
        for case in table["expect_ns"]:
            self.assertEqual(created_at_ns(case["createdAt"]), case["ns"])
        for text in table["invalid"]:
            with self.subTest(text):
                with self.assertRaises(ValueError):
                    created_at_ns(text)


class Sealed(unittest.TestCase):
    def test_every_golden_ciphertext_opens_as_planned(self):
        for entry in load("sealed-notes.json")["notes"]:
            with self.subTest(entry["label"]):
                manifest_id, key_version, age_file = age_tools.parse_note(entry["note"])
                self.assertEqual((manifest_id, key_version), (entry["manifest_id"], entry["header_key_version"]))
                plaintext = age_tools.reference_decrypt(age_file, SCALARS[entry["sealed_to_key_version"]])
                self.assertEqual(hashlib.sha256(plaintext).hexdigest(), entry["plaintext_sha256"])
                if entry["sealed_to_key_version"] != entry["header_key_version"]:
                    with self.assertRaises(ValueError):
                        age_tools.reference_decrypt(age_file, SCALARS[entry["header_key_version"]])


if __name__ == "__main__":
    unittest.main()
