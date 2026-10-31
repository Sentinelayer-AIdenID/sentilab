"""Structural guarantees of the contract (meta tests over the schemas and files) and the rules the golden files
cannot express on their own: the seams, no echo, the caps, sealing (T15), the bearer handles, the separate check
limits and the label mirror.

    python -m unittest -q open_proposals.contract.test_rules
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from sentilab_core.envelope import MAX_ITEMS, RUN_ID, check_caps

from . import age_tools
from . import canonical as h
from . import make_vectors as mv
from .codes import FIELDS, GROUPS, MAX_VIOLATIONS, ORDER, REASON_CODES, RECORD_CODES, RULES, VOCABULARY
from .labels import LISTS, label_for, label_for_all
from .predicates import apply_suppression, evaluate_labels, record_diagnostic
from .schemas import NAMES, SCHEMA_DIR, SCHEMAS, VALIDATORS
from .states import CHARGED, LEDGER, LIFECYCLE, SUMMARY, ledger_lifecycle
from .test_golden import opener
from .validator import (Reply, Unopenable, check_codes_ok, is_attempt, validate_local, validate_record,
                        validate_reply)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "contracts" / "open-proposal-v1"
REGISTRY = {mv.ID[key]: manifest for key, manifest in mv.MANIFESTS.items()}
OPEN = {mv.ID["F"]: "open"}

# DESIGN rev 3 section 7.2, copied by hand: the 48 codes in their groups and order.
REV3_CODES = {
    "transport": ["oversize", "not_utf8", "edited_before_ingest", "unattributable", "private_requires_sealed",
                  "unsealable", "transport_key_mismatch"],
    "envelope": ["malformed_json", "duplicate_key", "nonfinite_number", "too_deep", "unknown_field", "schema_invalid"],
    "manifest": ["unknown_manifest", "manifest_mismatch", "manifest_closed", "not_open_yet", "terms_not_accepted"],
    "geometry": ["die_count", "die_order", "out_of_frame", "rotation_not_allowed", "lattice", "margin",
                 "halo_overlap", "min_spacing", "keepout", "geometry_hash_mismatch"],
    "revision": ["idempotency_conflict", "unknown_parent", "unknown_proposal"],
    "policy": ["participant_suspended", "participant_paused", "participant_removed", "rate_limited", "queue_full",
               "budget_exhausted"],
    "evaluation": ["timeout", "stopped", "oracle_error", "grant_expired", "interrupted", "binding_mismatch",
                   "router_timeout", "check_unfinished"],
    "reproduction": ["reproduction_mismatch", "fresh_process_required", "reproduction_failed"],
}
# Codes no golden case can reach yet: decided by the machinery of later tickets.
OWNED_LATER = {"participant_suspended": "OP-W3", "participant_paused": "OP-W3", "budget_exhausted": "OP-W1",
               "oracle_error": "OP-F4", "grant_expired": "OP-F4", "fresh_process_required": "OP-F4",
               "reproduction_failed": "OP-F4"}


def walk(node, path=()):
    yield path, node
    if isinstance(node, dict):
        for key, value in node.items():
            yield from walk(value, path + (key,))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk(value, path + (index,))


CONDITIONAL = {"if", "then", "else"}


def definitions(schema):
    """Schema nodes that define values: not the narrowing branches of an if/then/else, not a properties map."""
    for path, node in walk(schema):
        if isinstance(node, dict) and path[-1:] != ("properties",) and not CONDITIONAL & set(path):
            yield path, node


def is_object(node) -> bool:
    types = node.get("type", [])
    return "object" in ([types] if isinstance(types, str) else types)


# A known-good sample per pattern; the no-free-text test needs one for every pattern in the schemas.
SAMPLES = {
    r"^(/[A-Za-z0-9_]{1,64})*$": "/ab", r"^(0|[0-9]{1,2}\.[0-9]{2})$": "0.10",
    r"^([a-z0-9][a-z0-9_-]{0,63}|publish:[0-9a-f]{64})$": "ab", r"^(human|agent:[A-Za-z0-9][A-Za-z0-9._-]{0,119})$":
        "agent:ab",
    r"^(provisional|frozen)( \([A-Za-z0-9 ,/#-]{1,64}\))?$": "frozen", r"^Chiplet_[0-9]{1,2}$": "Chiplet_0",
    r"^P(?=[0-9])([0-9]{1,4}Y)?([0-9]{1,4}M)?([0-9]{1,5}D)?$": "P2Y",
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$": "2026-11-01T00:00:00Z",
    r"^[0-9a-f]{32}$": "0" * 32, r"^[0-9a-f]{40}$": "0" * 40, r"^[0-9a-f]{64}$": "0" * 64,
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$": mv.HUMAN,
    r"^[A-Za-z0-9._-]{1,32}$": "ab", r"^[A-Za-z0-9][A-Za-z0-9 .,:;()-]{0,127}$": "ab",
    r"^[A-Za-z0-9][A-Za-z0-9 .,:;()-]{0,511}$": "ab", r"^[A-Za-z0-9][A-Za-z0-9 .,:;()/+_-]{0,127}$": "ab",
    "^[A-Za-z0-9][A-Za-z0-9 .,:;()/+_" + chr(0x2026) + "-]{0,127}$": "ab",
    r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,31}$": "ab", r"^[A-Za-z0-9][A-Za-z0-9._+:=-]{0,319}$": "ab",
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$": "ab", r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$": "ab",
    r"^[A-Za-z0-9_][A-Za-z0-9_./-]{0,127}$": "ab", r"^[A-Za-z][A-Za-z0-9_]{0,31}$": "ab", r"^[A-Za-z]{1,32}$": "ab",
    r"^[a-z0-9][a-z0-9_-]{0,63}$": "ab", r"^[a-z0-9][a-z0-9_.-]{0,63}(/[a-z0-9][a-z0-9_.-]{0,63})?$": "ab",
    r"^[a-z0-9_-]{1,32}$": "ab", r"^age1[02-9ac-hj-np-z]{58}$": "age1" + "q" * 58,
    r"^open-[0-9a-f]{8}-[0-9a-f]{16}$": "open-" + "0" * 8 + "-" + "0" * 16,
    r"^position-[0-9]{1,2}-[xy]-(plus|minus)$": "position-0-x-plus",
    r"^sentilab-open-terms/[1-9][0-9]{0,5}@[0-9a-f]{64}$": "sentilab-open-terms/1@" + "0" * 64,
    r"^sha256:[0-9a-f]{64}$": "sha256:" + "0" * 64, r"^so1-[0-9a-f]{48}$": "so1-" + "0" * 48,
    r"^tap-chiplet-[0-9]{1,2}$": "tap-chiplet-0",
}
DANGEROUS = "<>&\"'`\\" + "".join(chr(code) for code in (0, 9, 10, 13, 0x7F, 0x2028))
# Maps keyed by data (q_r, CPU ceilings, example inputs) are closed by propertyNames instead; the measured-row mixin
# is closed by each row kind that includes it.
OPEN_BY_DESIGN = {("results", ("$defs", "measured"))}


def codes_in(node):
    """Every code named anywhere in a JSON value: violations as objects, or bare code strings in lists."""
    if isinstance(node, dict):
        if isinstance(node.get("code"), str):
            yield node["code"]
        for value in node.values():
            yield from codes_in(value)
    elif isinstance(node, list):
        for value in node:
            yield from codes_in(value)


class Schemas(unittest.TestCase):
    def test_every_schema_is_valid_2020_12_with_its_own_id(self):
        self.assertEqual(sorted(NAMES), sorted(path.name.removesuffix(".schema.json")
                                               for path in SCHEMA_DIR.glob("*.schema.json")))
        for name, schema in SCHEMAS.items():
            Draft202012Validator.check_schema(schema)
            self.assertEqual(f"https://sentilab.invalid/open-proposal/v1/{name}.schema.json", schema["$id"])

    def test_objects_are_closed_and_risky_keywords_absent(self):
        for name, schema in SCHEMAS.items():
            for path, node in definitions(schema):
                if is_object(node) and (name, path) not in OPEN_BY_DESIGN:
                    closed = node.get("additionalProperties") is False or "propertyNames" in node
                    self.assertTrue(closed, f"{name} {path}")
            for path, node in walk(schema):
                keyword = path[-1] if path and path[-2:-1] != ("properties",) else None
                if keyword in ("format", "patternProperties", "unevaluatedProperties", "$dynamicRef",
                               "dependentSchemas"):
                    self.fail(f"{name} {path} uses {keyword}")

    def test_no_free_text(self):
        """Every string is a const, an enum or an anchored pattern whose charset excludes markup and controls."""
        seen = set()
        for name, schema in SCHEMAS.items():
            for path, node in definitions(schema):
                types = node.get("type", [])
                types = [types] if isinstance(types, str) else types
                if "string" in types and not ({"const", "enum", "pattern", "$ref"} & set(node)):
                    self.fail(f"{name} {path}: a string with no const, enum or pattern")
                if "pattern" in node:
                    seen.add(node["pattern"])
        self.assertEqual(set(SAMPLES), seen, "add a sample for each new pattern")
        for pattern, sample in SAMPLES.items():
            self.assertTrue(pattern.startswith("^") and pattern.endswith("$"), pattern)
            self.assertTrue(re.fullmatch(pattern, sample), pattern)
            for char in DANGEROUS:
                self.assertIsNone(re.fullmatch(pattern, sample[:1] + char + sample[2:]), (pattern, char))

    def test_the_only_participant_text_is_the_team_name(self):
        """Section 5.1: no free text apart from the moderated team name; client is a short token."""
        posted = ("proposal", "check-request", "team", "publish")
        spaced = [(name, path) for name in posted for path, node in definitions(SCHEMAS[name])
                  if " " in node.get("pattern", "")]
        self.assertEqual([("team", ("properties", "name"))], spaced)

    def test_every_temperature_carries_its_evaluator_and_label(self):
        """SLAB-053: a results row or comparator with a temperature also carries an evaluator and its label state."""
        results = SCHEMAS["results"]
        for node in (results["$defs"]["measured"], results["properties"]["comparator"]):
            self.assertTrue({"evaluator", "temperature_label"} <= set(node["required"]))

    def test_integers_are_literals(self):
        value = copy.deepcopy(mv.P_PUB)
        value["dies"][0]["x_um"] = 3000.0
        self.assertFalse(VALIDATORS["proposal"].is_valid(value))
        value["dies"][0]["x_um"] = True
        self.assertFalse(VALIDATORS["proposal"].is_valid(value))
        self.assertTrue(VALIDATORS["proposal"].is_valid(mv.P_PUB))

    def test_the_proposal_fields_are_rev3s(self):
        """Section 5.1 exactly: visibility and salt required, client optional, no wire_track or lattice_um."""
        proposal = SCHEMAS["proposal"]
        self.assertEqual(set(proposal["properties"]), {"schema", "manifest_id", "terms", "proposal_key", "parent",
                                                       "visibility", "salt", "units", "anchor", "dies",
                                                       "geometry_sha256", "client"})
        self.assertEqual(set(proposal["required"]), set(proposal["properties"]) - {"client"})
        self.assertEqual(set(SCHEMAS["check-request"]["required"]), {
            "schema", "manifest_id", "request_key", "visibility", "salt", "units", "anchor", "dies",
            "geometry_sha256"})
        self.assertEqual(len(SCHEMAS["manifest"]["required"]), 31)


class Vocabulary(unittest.TestCase):
    def test_exactly_rev3s_48_codes_in_order(self):
        self.assertEqual({group: list(codes) for group, codes in GROUPS.items()}, REV3_CODES)
        self.assertEqual(list(REASON_CODES), [code for codes in REV3_CODES.values() for code in codes])
        self.assertEqual(48, len(REASON_CODES))
        self.assertEqual(SCHEMAS["common"]["$defs"]["reason_code"]["enum"], list(REASON_CODES))
        self.assertEqual([], validate_record("reason_codes", VOCABULARY))

    def test_record_codes_stay_apart(self):
        self.assertFalse(set(RECORD_CODES) & set(REASON_CODES))
        self.assertEqual(sorted(ORDER, key=ORDER.get), list(REASON_CODES) + list(RECORD_CODES))
        for rule in RULES:
            self.assertRegex(rule, r"^[a-z_]{1,32}\.[a-z_]{1,32}$")

    def test_every_code_is_exercised_or_owned_by_a_later_ticket(self):
        golden = CONTRACT / "golden"
        records = json.loads((golden / "records.json").read_bytes())["cases"]
        loaded = [json.loads((golden / "notes.json").read_bytes()),
                  [case for case in records if case["kind"] != "reason_codes"]]
        states = json.loads((golden / "states.json").read_bytes())
        revisions = json.loads((golden / "revisions.json").read_bytes())["cases"]
        seen = set(codes_in(loaded))
        seen |= {code for pair in states["pairs"] + states["guards"] for code in pair["payload"].get("codes", [])
                 if isinstance(code, str)}
        for case in revisions:
            expected = case["expect"]
            seen |= set(expected if isinstance(expected, list) else expected.get("codes", [])
                        if isinstance(expected, dict) else [])
        self.assertEqual(set(REASON_CODES), (seen & set(REASON_CODES)) | set(OWNED_LATER))
        self.assertFalse(seen & set(OWNED_LATER), "an owned code is exercised: drop it from OWNED_LATER")

    def test_the_vocabulary_declares_exactly_each_codes_fields(self):
        properties = SCHEMAS["common"]["$defs"]["violation"]["properties"]
        for code, fields in FIELDS.items():
            self.assertTrue(set(fields) <= set(properties) | {"rule"}, code)
        self.assertEqual(("limit",), FIELDS["check_unfinished"])
        self.assertEqual(("retry_after",), FIELDS["queue_full"])


class Files(unittest.TestCase):
    def test_every_contract_file_is_pinned(self):
        pins = {}
        for line in (ROOT / "contracts" / "HASHES.txt").read_text(encoding="utf-8").splitlines():
            digest, name = line.split("  ", 1)
            pins[name] = digest
        files = {path.relative_to(ROOT / "contracts").as_posix(): path for path in CONTRACT.rglob("*")
                 if path.is_file()}
        self.assertEqual(set(files), {name for name in pins if name.startswith("open-proposal-v1/")})
        for name, path in files.items():
            self.assertEqual(pins[name], hashlib.sha256(path.read_bytes()).hexdigest(), name)

    def test_no_control_bytes_and_no_carriage_returns(self):
        package = Path(__file__).parent
        files = [path for path in list(CONTRACT.rglob("*")) + list(package.glob("*.py")) if path.is_file()]
        self.assertGreater(len(files), 40)
        for path in files:
            data = path.read_bytes()
            self.assertEqual([], [index for index, byte in enumerate(data) if byte < 0x20 and byte != 0x0A], path)

    def test_handles_are_bearer_secrets_in_every_word(self):
        """The carry-forward correction (#56992): a salted handle is a bearer secret, never called authentication."""
        texts = [path.read_text(encoding="utf-8") for path in CONTRACT.rglob("*.json")]
        texts.append((CONTRACT / "CONTRACT.md").read_text(encoding="utf-8"))
        for text in texts:
            self.assertNotRegex(text.lower(), r"owner-only|authenticated handle|authenticates the")
        for name in ("proposal", "check-request", "status"):
            self.assertIn("bearer secret", SCHEMAS[name]["description"])


def note(value) -> bytes:
    return json.dumps(value).encode()


def reply_for(item, **edits) -> Reply:
    fields = {"room": mv.ROOM, "actor_user_id": mv.HUMAN, "actor_kind": "human", "actor_id": None,
              "idempotency_key": h.transport_key_for(item, room=mv.ROOM, account=mv.HUMAN, actor_kind="human",
                                                     actor_id=None) if item is not None else None,
              "message_revision": 1, "edited_at": None}
    return Reply(**fields | edits)


def intake(raw: bytes, item, **kwargs):
    return validate_reply(raw, reply=reply_for(item), manifests=REGISTRY, thread_manifest_id=mv.ID["F"],
                          admission=OPEN, **kwargs)


class Seams(unittest.TestCase):
    def test_the_layout_seam_contract(self):
        for found in ([{"code": "lattice", "dies": [0], "amount_um": 250}], [{"code": "margin", "dies": [0]}],
                      [{"code": "margin", "dies": [0], "amount_um": 0}],
                      [{"code": "margin", "dies": [0], "amount_um": 5, "message": "near the edge"}]):
            with self.subTest(found):
                with self.assertRaises(ValueError):
                    intake(note(mv.P_PUB), mv.P_PUB, layout_checker=lambda _item, _manifest: found)
        calls = []
        intake(note(mv.P_PUB), mv.P_PUB, layout_checker=lambda item, manifest: calls.append((item, manifest)) or [])
        self.assertEqual([(mv.P_PUB, mv.F)], calls)

    def test_an_opener_failure_is_a_code_and_any_other_fault_propagates(self):
        sealed = mv.sealed("private proposal")

        def broken(_armour, _manifest, _version):
            raise RuntimeError("a fault")

        with self.assertRaises(RuntimeError):
            intake(sealed, mv.P_PRIV, opener=broken)
        with self.assertRaises(TypeError):
            intake(sealed, mv.P_PRIV, opener=lambda *_: "a string")
        refused = intake(sealed, mv.P_PRIV, opener=lambda *_: (_ for _ in ()).throw(Unopenable()))
        self.assertEqual(["unsealable"], [item["code"] for item in refused.violations])

    def test_a_sealed_schema_that_is_not_a_string_is_unsealable(self):
        outcome = intake(mv.sealed("private proposal"), mv.P_PRIV, opener=lambda *_: b'{"schema": ["x"]}')
        self.assertEqual(["unsealable"], [item["code"] for item in outcome.violations])

    def test_the_opener_gets_the_header_key_version_and_the_armour(self):
        seen = []

        def spy(armour, manifest, version):
            seen.append((armour, manifest["version"], version))
            return opener(armour, manifest, version)

        sealed = mv.sealed("private proposal")
        self.assertEqual("contract_valid", intake(sealed, mv.P_PRIV, opener=spy).outcome)
        self.assertEqual([(mv.armour_of(sealed), 1, 1)], seen)

    def test_the_intake_refuses_missing_context(self):
        with self.assertRaises(TypeError):
            validate_reply(note(mv.P_PUB), reply=reply_for(mv.P_PUB), manifests=REGISTRY,
                           thread_manifest_id=mv.ID["F"], admission=None)
        with self.assertRaises(TypeError):
            validate_reply(note(mv.P_PUB), reply=None, manifests=REGISTRY, thread_manifest_id=mv.ID["F"],
                           admission=OPEN)
        with self.assertRaises(TypeError):
            intake(note(mv.P_PUB).decode(), mv.P_PUB)
        with self.assertRaises(ValueError):
            validate_record("usage", {})

    def test_attempt_detection(self):
        for raw, attempt in ((b"{", True), (b"```json", True), (b"sentilab-open-sealed/1", True),
                             (b"sentilab-open-sealed/2 x", False), (b" {", False), (b"", False), (b"[", False),
                             (b"Sentilab-open-sealed/1", False)):
            self.assertEqual(attempt, is_attempt(raw), raw)

    def test_nothing_submitted_is_ever_echoed(self):
        marker = "ZZMARKER"
        attempts = [{**mv.P_PUB, marker: "x"}, {**mv.P_PUB, "note": marker}, mv.changed(mv.P_PUB, proposal_key=marker),
                    mv.changed(mv.P_PUB, client={"name": marker + "<", "version": "1"}),
                    {**mv.P_PUB, "dies": [{**mv.TEST_LAYOUT[0], marker: 1}, mv.TEST_LAYOUT[1]]},
                    mv.changed(mv.TEAM, name=marker + "<script>")]
        for value in attempts:
            for outcome in (validate_local(note(value), manifests=REGISTRY, manifest_id=mv.ID["F"]),
                            intake(note(value), value)):
                self.assertEqual("rejected", outcome.outcome)
                self.assertNotIn(marker, json.dumps(list(outcome.violations)))
        raw = note(mv.P_PUB)[:-1] + b', "' + marker.encode() + b'": NaN}'
        self.assertNotIn(marker, json.dumps(list(intake(raw, mv.P_PUB).violations)))

    def test_violations_are_cut_at_the_envelope_cap_after_the_decision(self):
        manifest = copy.deepcopy(mv.F)
        manifest["dies"] = [{"die": index, "unit": f"Chiplet_{index}", "name": "d", "w_um": 100, "h_um": 100,
                             "power_w": 1, "halo_um": 0, "rot_deg": [0]} for index in range(32)]
        manifest_id = h.manifest_id(manifest)
        value = {**mv.P_PUB, "manifest_id": manifest_id,
                 "dies": [{"die": index, "x_um": 10750, "y_um": 250, "rot_deg": 0} for index in range(32)],
                 "geometry_sha256": "0" * 64}
        outcome = validate_local(note(value), manifests={manifest_id: manifest}, manifest_id=manifest_id)
        self.assertEqual("rejected", outcome.outcome)
        self.assertEqual(64, MAX_ITEMS)
        self.assertEqual(MAX_ITEMS, len(outcome.violations), "the envelope's per-list cap, not our own constant")
        self.assertEqual(MAX_ITEMS, MAX_VIOLATIONS)
        self.assertEqual(["out_of_frame", "out_of_frame"], [item["code"] for item in outcome.violations[:2]])
        self.assertNotIn("geometry_hash_mismatch", [item["code"] for item in outcome.violations], "cut, last in order")

    def test_maximal_records_fit_the_view_envelope(self):
        violation = {"code": "die_order", "dies": list(range(32))}
        receipt = mv.receipt(state="rejected", codes=[violation] * 64)
        receipt["values"]["geometry"] = receipt["values"]["geometry"] * 16
        self.assertTrue(VALIDATORS["receipt"].is_valid(receipt))
        check_caps(receipt)
        check = mv.check_record(router_status="not_routed", W_c_mm="UNKNOWN", q_r_nominal=mv.Q_UNKNOWN,
                                codes=[violation] * 64)
        self.assertTrue(VALIDATORS["check"].is_valid(check))
        check_caps(check)


class Sealing(unittest.TestCase):
    """T15: age vectors per key version, unsealable, no plaintext fallback, the caps, private status by handle."""

    def test_re_sealing_the_same_plaintext_retries_identically(self):
        first, second = mv.sealed("private proposal"), mv.sealed("private proposal, sealed again")
        self.assertNotEqual(h.body_sha256(first), h.body_sha256(second), "age encryption is randomised")
        outcomes = [intake(raw, mv.P_PRIV, opener=opener) for raw in (first, second)]
        self.assertEqual(["contract_valid"] * 2, [outcome.outcome for outcome in outcomes])
        self.assertEqual(outcomes[0].content_sha256, outcomes[1].content_sha256)
        self.assertEqual(h.proposal_sha256(mv.P_PRIV), outcomes[0].content_sha256)

    def test_the_caps(self):
        header = b"sentilab-open-sealed/1 " + mv.ID["F"].encode() + b" 1\n"
        exactly = header + b"-" * (8192 - len(header))
        self.assertNotIn("oversize", [item["code"] for item in intake(exactly, None).violations])
        over = intake(exactly + b"-", None)
        self.assertEqual([{"code": "oversize", "size_bytes": 8193}], list(over.violations))
        self.assertEqual(4096, mv.F["sealing"]["plaintext_max_bytes"])
        self.assertEqual(8192, mv.F["sealing"]["sealed_note_max_bytes"])

    def test_a_note_that_fails_to_open_is_never_read_as_plaintext(self):
        calls = []

        def refuse(armour, _manifest, _version):
            calls.append(armour)
            raise Unopenable()

        raw = b"sentilab-open-sealed/1 " + mv.ID["F"].encode() + b" 1\n" + mv.armour_of(mv.sealed("private proposal"))
        self.assertEqual(["unsealable"], [item["code"] for item in intake(raw, mv.P_PRIV, opener=refuse).violations])
        self.assertEqual(1, len(calls))

    def test_private_status_is_reachable_only_through_the_salted_handle(self):
        public, private = h.proposal_sha256(mv.P_PUB), h.proposal_sha256(mv.P_PRIV)
        self.assertEqual(mv.P_PUB["geometry_sha256"], mv.P_PRIV["geometry_sha256"], "the same layout")
        self.assertNotEqual(public, private)
        self.assertNotIn(private, (mv.P_PRIV["geometry_sha256"], mv.ID["F"]))
        resalted = mv.changed(mv.P_PRIV, salt=mv.SALTS[7])
        self.assertNotEqual(private, h.proposal_sha256(resalted), "a new salt is a new handle")
        self.assertNotEqual(h.request_sha256(mv.C_PRIV), h.request_sha256(mv.changed(mv.C_PRIV, salt=mv.SALTS[7])))
        status = SCHEMAS["status"]
        self.assertNotIn("geometry_sha256", json.dumps(status["properties"]))
        self.assertNotIn("dies", json.dumps(SCHEMAS["check"]["properties"]), "a check result carries no geometry")

    def test_the_age_vectors_parse_in_python_and_the_armour_refusals_are_refused(self):
        vectors = json.loads((CONTRACT / "vectors-canonical.json").read_bytes())
        for case in vectors["sealed_notes"]:
            manifest_id, version, age_file = age_tools.parse_note(case["note"])
            self.assertEqual((manifest_id, version), (case["manifest_id"], case["key_version"]))
            self.assertEqual(case["age_file_sha256"], hashlib.sha256(age_file).hexdigest())
        import base64
        for case in vectors["armour_refusals"]:
            with self.subTest(case["name"]):
                with self.assertRaises(ValueError):
                    age_tools.dearmor(base64.b64decode(case["armour_b64"]))


class Keys(unittest.TestCase):
    def test_transport_keys(self):
        key = h.transport_key_for(mv.P_PUB, room=mv.ROOM, account=mv.HUMAN, actor_kind="human", actor_id=None)
        self.assertRegex(key, r"^so1-[0-9a-f]{48}$")
        self.assertEqual(52, len(key))
        others = {h.transport_key_for(mv.P_PUB, room=mv.ROOM, account=mv.AGENT_ACCOUNT, actor_kind="agent",
                                      actor_id=mv.AGENT_ID),
                  h.transport_key_for(mv.P_PUB, room=mv.ROOM, account=mv.HUMAN, actor_kind="agent", actor_id="a"),
                  h.transport_key_for(mv.P_PUB, room=mv.OVERFLOW_ROOM, account=mv.HUMAN, actor_kind="human",
                                      actor_id=None),
                  h.transport_key_for(mv.changed(mv.P_PUB, salt=mv.SALTS[6]), room=mv.ROOM, account=mv.HUMAN,
                                      actor_kind="human", actor_id=None)}
        self.assertEqual(4, len(others))
        self.assertNotIn(key, others)
        self.assertEqual("publish:" + mv.PUBLISH["proposal_sha256"], h.logical_key(mv.PUBLISH))
        self.assertEqual("team", h.logical_key(mv.TEAM))
        with self.assertRaises(ValueError):
            h.actor_slot("human", "example-agent")
        with self.assertRaises(ValueError):
            h.logical_key({"schema": "sentilab-open-proposal/2"})

    def test_participant_ref_is_keyed_per_challenge(self):
        ref = h.participant_ref(mv.K_CHALLENGE, mv.HUMAN)
        self.assertNotEqual(ref, hashlib.sha256(mv.HUMAN.encode()).hexdigest())
        self.assertNotEqual(ref, h.participant_ref(hashlib.sha256(b"another challenge").digest(), mv.HUMAN))
        with self.assertRaises(ValueError):
            h.participant_ref(b"short", mv.HUMAN)

    def test_run_ids_and_headers(self):
        run = h.run_id(mv.ID["F"], h.proposal_sha256(mv.P_PUB))
        self.assertTrue(RUN_ID.fullmatch(run))
        self.assertEqual("open-" + mv.ID["F"][:8] + "-" + h.proposal_sha256(mv.P_PUB)[:16], run)
        with self.assertRaises(ValueError):
            h.run_id(mv.ID["F"][:8], h.proposal_sha256(mv.P_PUB))
        self.assertEqual("sentilab-open-sealed/1 " + mv.ID["F"] + " 1", h.sealed_header(mv.ID["F"], 1))
        for bad in (0, True, "1"):
            with self.assertRaises(ValueError):
                h.sealed_header(mv.ID["F"], bad)

    def test_q_r_is_exact(self):
        self.assertEqual(-2366.075, h.q_r(18155.8, 16417.5, "0.25"))
        self.assertEqual(96.55, h.q_r(18155.8, 16417.5, "0.10"))
        self.assertEqual(["0", "0.05", "0.10", "1.00"], [h.r_key(r) for r in (0, 0.05, 0.1, 1.0)])
        for bad in (0.125, -0.1, 0.001):
            with self.assertRaises(ValueError):
                h.r_key(bad)


class PythonVectors(unittest.TestCase):
    """T1, the Python side: the reference reproduces every vector (run-vectors.mjs checks the same in Node)."""

    def setUp(self):
        self.vectors = json.loads((CONTRACT / "vectors-canonical.json").read_bytes())
        self.manifests = json.loads((CONTRACT / "golden" / "manifests.json").read_bytes())["manifests"]

    def test_every_python_vector(self):
        import base64
        v, objects = self.vectors, self.vectors["objects"]
        for case in v["canonical"]:
            self.assertEqual(case["canonical"], h.canonical(case["value"]).decode())
        for case in v["manifest_id"]:
            self.assertEqual(case["manifest_id"], h.manifest_id(self.manifests[case["manifest"]]))
        for case in v["geometry"]:
            item, manifest = objects[case["object"]], self.manifests[case["manifest"]]
            self.assertEqual(case["preimage"], h.geometry_object(item, manifest))
            self.assertEqual(case["geometry_sha256"], h.geometry_sha256(item, manifest))
        for case in v["content"]:
            self.assertEqual(case["content_sha256"], h.content_sha256(objects[case["object"]]))
            self.assertEqual(case["logical_key"], h.logical_key(objects[case["object"]]))
        for case in v["body_sha256"]:
            self.assertEqual(case["body_sha256"], h.body_sha256(base64.b64decode(case["note_b64"])))
        for case in v["source_ref"]:
            self.assertEqual(case["source_ref"], h.source_ref(case["action_id"]))
        for case in v["participant_ref"]:
            self.assertEqual(case["participant_ref"], h.participant_ref(mv.K_CHALLENGE, case["account_id"]))
        for case in v["transport_key"]:
            item = objects[case["object"]]
            self.assertEqual(case["transport"], h.transport_key_for(
                item, room=case["room"], account=case["account"], actor_kind=case["actor_kind"],
                actor_id=case["actor_id"]))
            self.assertEqual(case["transport"], "so1-" + h.digest(case["preimage"])[:48])
        for case in v["run_id"]:
            self.assertEqual(case["run_id"], h.run_id(case["manifest_id"], case["proposal_sha256"]))
        for case in v["sealed_header"]:
            self.assertEqual(case["line"], h.sealed_header(case["manifest_id"], case["key_version"]))
        for case in v["r_key"]:
            self.assertEqual(case["key"], h.r_key(case["r"]))
        for case in v["q_r"]:
            self.assertEqual(case["q_r"], h.q_r(case["W_c_mm"], case["W_R_mm"], case["key"]))
        for case in v["conductor_geometry"]:
            self.assertEqual(case["values"], h.conductor_geometry(objects[case["object"]],
                                                                self.manifests[case["manifest"]]))
        for case in v["sealed_note_refusals"]:
            with self.subTest(case["name"]):
                with self.assertRaises(ValueError):
                    age_tools.parse_note(base64.b64decode(case["note_b64"]))

    def test_the_intake_reads_admission_and_sealing_strictly(self):
        outcome = validate_reply(note(mv.P_PUB), reply=reply_for(mv.P_PUB), manifests=REGISTRY,
                                 thread_manifest_id=mv.ID["F"], admission={})
        self.assertEqual(["not_open_yet"], [item["code"] for item in outcome.violations], "unlisted is not open")
        manifest = mv.edit(mv.F, "/sealing/recipient", None)
        manifest_id = h.manifest_id(manifest)
        sealed = mv.sealed("private proposal").replace(mv.ID["F"].encode(), manifest_id.encode(), 1)
        outcome = validate_reply(sealed, reply=reply_for(mv.P_PRIV), manifests={manifest_id: manifest},
                                 thread_manifest_id=manifest_id, admission={manifest_id: "open"},
                                 opener=lambda *_: h.canonical(mv.P_PRIV))
        self.assertEqual(["unsealable"], [item["code"] for item in outcome.violations], "no recipient, no seal")


class Handles(unittest.TestCase):
    """Root's review: a private handle is refused anywhere in a public record, not only as a whole string."""

    def test_every_spelling_and_place(self):
        import base64
        from .validator import exposes_handle
        handle = mv.PRIV_HANDLE
        raw = bytes.fromhex(handle)
        spellings = {"bare": handle, "prefix": "x:" + handle, "suffix": handle + ":x", "middle": "x" + handle + "x",
                     "upper case": handle.upper(), "mixed case": handle[:32].upper() + handle[32:],
                     "separators": "-".join(handle[index:index + 4] for index in range(0, 64, 4)),
                     "base64": base64.b64encode(raw).decode(), "base64 unpadded": base64.b64encode(raw).decode()
                     .rstrip("="), "base64url": "x" + base64.urlsafe_b64encode(raw).decode().rstrip("=") + "x"}
        for name, text in spellings.items():
            with self.subTest(name):
                self.assertTrue(exposes_handle({"value": text}, [handle]))
                self.assertTrue(exposes_handle({text: 1}, [handle]), "in a key")
                self.assertTrue(exposes_handle([{"deep": [text]}], [handle]), "nested")
        for text in (handle[:63], h.proposal_sha256(mv.P_PUB), "x" * 64, handle[1:]):
            self.assertFalse(exposes_handle({"value": text}, [handle]))
        with self.assertRaises(ValueError):
            exposes_handle({}, [handle.upper()])


class Limits(unittest.TestCase):
    def test_the_four_check_limits_are_separate_fields(self):
        """Section 6.2: the solver limit, the whole-check wall, the CPU reserve and the request quotas."""
        checks = SCHEMAS["manifest"]["properties"]["checks"]["properties"]
        self.assertTrue({"solver_time_limit_s", "check_wall_s", "cleanup_headroom_s", "cpu_reserve_s"} <= set(checks))
        self.assertTrue({"check_per_account_hour", "check_room_hour"} <= set(
            SCHEMAS["manifest"]["properties"]["limits"]["properties"]))
        self.assertEqual((2, 5), (mv.A["checks"]["solver_time_limit_s"], mv.A["checks"]["check_wall_s"]))
        for path, value in (("/checks/cpu_reserve_s", 1), ("/checks/cpu_reserve_s", 500),
                            ("/checks/cleanup_headroom_s", 30), ("/limits/check_room_hour", 1)):
            self.assertEqual([], validate_record("manifest", mv.edit(mv.F, path, value)), "none stands in for another")
        self.assertEqual(40, mv.F["limits"]["warden_call_policy_hour"])
        self.assertEqual([], validate_record("manifest", mv.edit(mv.F, "/limits/warden_call_policy_hour", 7)),
                         "the call backstop is a policy, not 600/15")

    def test_each_limit_keeps_its_own_finding(self):
        """A CPU reserve overrun is detected at settlement and recorded as itself, never as the wall's kill."""
        unfinished = [{"code": "check_unfinished", "limit": limit} for limit in
                      ("solver_time_limit_s", "check_wall_s", "cpu_reserve_s")]
        self.assertTrue(check_codes_ok("time_limit", unfinished[:1]))
        self.assertFalse(check_codes_ok("not_routed", unfinished[:1]))
        self.assertTrue(check_codes_ok("not_routed", unfinished[1:2]))
        self.assertTrue(check_codes_ok("not_routed", unfinished[2:]))
        self.assertFalse(check_codes_ok("time_limit", unfinished[2:]))
        self.assertTrue(check_codes_ok("not_routed", [{"code": "rate_limited", "retry_after": "2026-11-01T11:00:00Z"}]))


class States(unittest.TestCase):
    def test_every_state_is_mapped(self):
        for table in (SUMMARY, CHARGED):
            self.assertEqual(set(LIFECYCLE), set(table))
        self.assertEqual(set(LIFECYCLE) - {"rejected"}, set(LEDGER))
        self.assertEqual("rejected_constraints", ledger_lifecycle("rejected", ["lattice"]))
        self.assertEqual("rejected_schema", ledger_lifecycle("rejected", ["terms_not_accepted"]))
        self.assertEqual("independently verified", SUMMARY["reproduced"])
        self.assertNotIn("withdrawn", LIFECYCLE, "rev 3 hides; it never withdraws")


class Labels(unittest.TestCase):
    def test_the_label_mirror(self):
        withdrawn = "HotSpot-7:F18831E48CEF5D62580585CCA0D7FAB6C71BC3CC:binary_sha256:" + "0" * 64
        self.assertEqual("withdrawn", label_for(withdrawn), "every build of the withdrawn engine:commit")
        self.assertEqual("unvalidated", label_for("HotSpot-7:f18831e48cef5d62580585cca0d7fab6c71bc3cc+SLAB-049:x"),
                         "a variant is a different evaluator")
        self.assertEqual("illustrative", label_for("fixture-no-solver"))
        self.assertEqual("unvalidated", label_for("fixture-no-solver:grid:16x16"), "illustrative is exact")
        self.assertEqual("unvalidated", label_for(""))
        self.assertEqual("unvalidated", label_for(None))
        accepted = dict(LISTS, accepted=("HotSpot-6.0:x",))
        self.assertEqual("accepted", label_for("HotSpot-6.0:x", accepted))
        self.assertEqual("unvalidated", label_for("HotSpot-6.0:x:grid:32x32", accepted), "accepted is exact")
        self.assertEqual("unvalidated", label_for_all([]))
        self.assertEqual("withdrawn", label_for_all(["fixture-no-solver", withdrawn]))
        self.assertEqual("illustrative", label_for_all(["fixture-no-solver", "fixture-no-solver"]))
        self.assertEqual("unvalidated", label_for_all(["fixture-no-solver", "HotSpot-6.0:x"]))
        self.assertEqual("accepted", label_for_all(["HotSpot-6.0:x"], accepted))
        self.assertEqual("unvalidated", label_for_all(["HotSpot-6.0:x", "fixture-no-solver"], accepted))
        self.assertEqual("withdrawn", label_for(withdrawn, dict(LISTS, accepted=(withdrawn,))),
                         "withdrawn wins over any other list")
        self.assertEqual((), LISTS["accepted"], "ACCEPTED is empty")

    def test_a_high_wire_diagnostic_never_suppresses_a_temperature_label(self):
        """The carry-forward correction (#56992): a wire diagnostic (Fig. 6(b), +45% routed) is recorded beside the claims;
        the temperature target and the row's SLAB-053 label stay exactly as they were."""
        screen = [{"id": "nominal", "applies_to": "both", "grid": 64}]
        values = {"nominal": {"status": "observed", "T_c": 59.5, "T_R": 60.0, "W_c": 145.0, "W_R": 100.0}}
        policy = mv.F["policy"]
        labels = evaluate_labels(policy=policy, bounds=mv.F["bounds"], admission=True, screen=screen, values=values)
        self.assertEqual(["declared temperature target"], [label["id"] for label in labels])
        kept, record = record_diagnostic(labels, {"wire improvement with allowed thermal degradation": True},
                                         {"wire improvement with allowed thermal degradation": False})
        self.assertEqual(labels, kept)
        self.assertFalse(record["matched"])
        with self.assertRaises(ValueError):
            apply_suppression(labels, [{"by": "unexpected diagnostic"}])
        row = mv.outside(T_M=59.5, delta_T=-0.5, W_c_mm=145.0, q_r={key: h.q_r(145.0, 100.0, key) for key in mv.Q_F},
                         labels=kept)
        self.assertEqual([], validate_record("results", mv.results(row), manifest=mv.F))
        self.assertEqual("illustrative", row["temperature_label"])


if __name__ == "__main__":
    unittest.main()
