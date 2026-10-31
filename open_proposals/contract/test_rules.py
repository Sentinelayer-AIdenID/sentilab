"""Structural guarantees of the contract (meta tests over the schemas and files) and the seams the golden files
cannot express: the sealed opener, the OP-F7 layout checker, no echo, the violation cap and the label mirror.

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

from sentilab_core.envelope import MAX_ITEMS, check_caps

from . import canonical as h
from . import make_vectors as mv
from .codes import FIELDS, GROUPS, MAX_VIOLATIONS, ORDER, RULES
from .labels import LISTS, label_for, label_for_all
from .schemas import NAMES, SCHEMA_DIR, SCHEMAS, VALIDATORS
from .states import SUMMARY, Entry, TransitionRefused, transition
from .validator import (Reply, Unopenable, decode_param, is_chat, validate_check_note, validate_record,
                        validate_submission)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "contracts" / "open-proposal-v1"
REGISTRY = {mv.ID[key]: manifest for key, manifest in mv.MANIFESTS.items()}
HUMAN_REPLY = Reply(mv.HUMAN, 1, None)
OPEN = {mv.ID["F"]: "open"}


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
    "^[0-9a-f]{64}$": "0" * 64, "^[0-9a-f]{40}$": "0" * 40,
    "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$": mv.HUMAN,
    "^[a-z0-9][a-z0-9_-]{0,63}$": "ab", "^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$": "ab",
    "^[A-Za-z0-9][A-Za-z0-9._+:=-]{0,319}$": "ab", "^[A-Za-z0-9][A-Za-z0-9 ._:()/+-]{0,127}$": "ab",
    "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,9})?Z$": "2026-11-01T00:00:00Z",
    "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,9})?(Z|[+-][0-9]{2}:[0-9]{2})$":
        "2026-11-01T00:00:00+00:00",
    "^sentilab-open-terms/[1-9][0-9]{0,5}$": "sentilab-open-terms/1", "^([0-9a-f]{64}|sentilab)$": "sentilab",
    "^[A-Za-z0-9](?:[A-Za-z0-9 ._-]{0,30}[A-Za-z0-9])?$": "ab",
    "^open-[0-9a-f]{8}-([0-9a-f]{16}|sentilab)$": "open-00000000-sentilab",
    "^open-tk1-[0-9a-f]{64}$": "open-tk1-" + "0" * 64, "^opencap1-[0-9a-f]{64}$": mv.FAKE_CAPABILITY,
    "^age1[02-9ac-hj-np-z]{58}$": "age1" + "q" * 58,
    "^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$": "abcd",
    "^(/[A-Za-z0-9_]{1,64})*$": "/ab", "^[A-Za-z]{1,32}$": "ab", "^[a-z_]{1,32}\\.[a-z_]{1,32}$": "a.b",
    "^[A-Za-z0-9._-]{1,32}$": "ab", "^[A-Za-z0-9_-]+$": "ab", "^[A-Za-z0-9_][A-Za-z0-9_./-]{0,199}$": "ab",
    "^tap-chiplet-(0|[1-9][0-9]?)$": "tap-chiplet-0",
}
DANGEROUS = "<>&\"'`\\" + "".join(chr(code) for code in (0, 9, 10, 13, 0x7F, 0x2028))
MEASURED = {"T_M_c", "grid_peak_c", "tap_selector_c", "t_c", "routed_mm", "proxy_mm", "w_mm", "delta_T_k"}
INPUTS = {"ambient_c", "scenario_target_c", "D_k", "B_T_k", "of_reference_wire_mm"}


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
                if is_object(node):
                    self.assertIs(False, node.get("additionalProperties"), f"{name} {path}")
            for path, node in walk(schema):
                keyword = path[-1] if path and path[-2:-1] != ("properties",) else None
                if keyword in ("format", "patternProperties", "propertyNames", "unevaluatedProperties",
                               "$dynamicRef", "dependentSchemas"):
                    self.fail(f"{name} {path} uses {keyword}")
                if path and path[-1] == "additionalProperties" and path[-2:-1] != ("properties",):
                    self.assertIs(False, node, f"{name} {path}")

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

    def test_every_measured_value_carries_its_evaluator_and_a_label(self):
        """SLAB-053: wherever a temperature or wire value travels, its evaluator identity and label travel too."""
        for name, schema in SCHEMAS.items():
            for path, node in definitions(schema):
                if not is_object(node) or "properties" not in node:
                    continue
                names = set(node["properties"])
                for field in names:
                    if re.search(r"(_c|_k|_mm)$", field):
                        self.assertIn(field, MEASURED | INPUTS | {"q_mm"}, f"{name} {path}: classify {field}")
                if names & MEASURED:
                    required = set(node.get("required", ()))
                    self.assertIn("label", required, f"{name} {path}")
                    self.assertTrue({"evaluator", "evaluators"} & required, f"{name} {path}")
                    self.assertEqual({"$ref": "#/$defs/label_state"} if name == "common" else
                                     {"$ref": "common.schema.json#/$defs/label_state"}, node["properties"]["label"])
        common = SCHEMAS["common"]["$defs"]
        for parent, required in (("comparison", "evaluators"), ("diagnostic", "evaluator")):
            self.assertTrue({required, "label"} <= set(common[parent]["required"]))
        text = json.dumps(SCHEMAS)
        self.assertEqual(1, text.count('"q_mm": {'), "q_mm lives only in the labelled comparison")
        self.assertEqual(["withdrawn", "unvalidated", "illustrative", "accepted"], common["label_state"]["enum"])
        self.assertEqual(json.loads((CONTRACT / "labels.json").read_bytes())["states"], common["label_state"]["enum"])
        self.assertEqual((), LISTS["accepted"], "nothing is accepted yet (SLAB-053)")

    def test_only_a_private_request_can_carry_a_capability(self):
        for name, schema in SCHEMAS.items():
            refs = [node for path, node in walk(schema) if path[-1:] == ("$ref",) and node.endswith("/capability")]
            self.assertEqual(1 if name == "private-request" else 0, len(refs), name)

    def test_integers_are_literals(self):
        validator = VALIDATORS["geometry"]
        geometry = h.geometry_object(mv.P_F, mv.F)
        self.assertTrue(validator.is_valid(geometry))
        for bad in (3000.0, True, "3000"):
            self.assertFalse(validator.is_valid(mv.edit(geometry, ["dies", 0, "x_um"], bad)), bad)
        self.assertFalse(validator.is_valid(mv.edit(geometry, ["dies", 0, "rot_deg"], False)))

    def test_the_vocabulary_and_the_rules(self):
        self.assertEqual(list(ORDER), SCHEMAS["common"]["$defs"]["reason_code"]["enum"])
        self.assertEqual(len(ORDER), len(set(ORDER)))
        source = (Path(__file__).parent / "validator.py").read_text(encoding="utf-8")
        used = set(re.findall(r'"([a-z_]+\.[a-z_]+)"\)', source))
        self.assertEqual(set(RULES), used, "declared rule ids are exactly the ones the validator raises")
        golden = json.loads((CONTRACT / "golden" / "records.json").read_bytes())["cases"]
        exercised = {code["rule"] for case in golden for code in case["expect"] if "rule" in code}
        self.assertEqual({"results.scoring"}, set(RULES) - exercised, "results.scoring is a unit test below")

    def test_every_code_is_exercised_or_owned_by_a_later_ticket(self):
        golden = []
        for name in ("notes.json", "check-requests.json", "records.json"):
            for case in json.loads((CONTRACT / "golden" / name).read_bytes())["cases"]:
                expect = case["expect"] if isinstance(case["expect"], list) else case["expect"]["codes"]
                golden += [code["code"] for code in expect]
                record = case.get("record", {})
                golden += [code["code"] for _, node in walk(record) if isinstance(node, dict)
                           for code in [node] if isinstance(code.get("code"), str) and code["code"] in ORDER]
        golden += [code for case in json.loads((CONTRACT / "golden" / "revisions.json").read_bytes())["cases"]
                   if case["expect"] != "order_error" for code in case["expect"]["codes"]]
        later = {"participant_suspended": "OP-W3", "rate_limited": "OP-W1", "capacity_full": "OP-W1",
                 "budget_exhausted": "OP-W1", "timeout": "OP-F4", "stopped": "OP-F4", "oracle_error": "OP-F4",
                 "grant_expired": "OP-F4", "binding_mismatch": "OP-F4", "reproduction_mismatch": "OP-F4",
                 "fresh_process_required": "OP-F4", "reproduction_failed": "OP-F4",
                 "verification_mismatch": "OP-F4", "independence_required": "OP-F4", "verification_failed": "OP-F4",
                 "margin": "OP-F7", "halo_overlap": "OP-F7", "min_spacing": "OP-F7", "sealed_undecryptable": "OP-F3",
                 "salt_required": "OP-F3", "gate_failed": "OP-F4", "binding_failed": "OP-F4",
                 "predicate_failed": "OP-F4", "scenario_failed": "OP-F4", "reinstated": "OP-W3"}
        missing = set(ORDER) - set(golden) - set(later)
        self.assertEqual(set(), missing)

    def test_the_vocabulary_declares_exactly_each_codes_fields(self):
        self.assertEqual({"path", "rule"}, set(FIELDS["record_inconsistent"]))
        self.assertEqual(("retry_after",), FIELDS["queue_full"])
        self.assertEqual(set(GROUPS["sealing"]), {"sealed_format", "sealed_key_version", "sealed_undecryptable",
                                                  "salt_required", "salt_forbidden"})


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
        self.assertGreater(len(files), 30)
        for path in files:
            data = path.read_bytes()
            self.assertEqual([], [index for index, byte in enumerate(data) if byte < 0x20 and byte != 0x0A], path)


def note(value) -> bytes:
    return json.dumps(value).encode()


class Seams(unittest.TestCase):
    def sealed(self, plaintext: bytes, *, opener=None):
        def default(age_file, manifest):
            self.assertEqual(mv.AGE_HEADER_ONLY, age_file)
            self.assertEqual(mv.F, manifest)
            return plaintext
        return validate_submission(mv.NOTE_SEALED, reply=HUMAN_REPLY, manifests=REGISTRY,
                                   thread_manifest_id=mv.ID["F"], admission=OPEN, opener=opener or default)

    def test_a_sealed_proposal_opens_through_the_seam(self):
        # The opener is a test double for the recorder's age identity: it is not age, and no ciphertext is claimed.
        outcome = self.sealed(note(mv.P_SEALED))
        self.assertEqual(("contract_valid", True), (outcome.outcome, outcome.sealed))
        self.assertEqual(h.proposal_sha256(mv.P_SEALED), outcome.proposal_sha256)
        self.assertEqual(h.ciphertext_ref(mv.AGE_HEADER_ONLY), outcome.ciphertext_ref)
        self.assertEqual(mv.P_F["geometry_sha256"], outcome.geometry_sha256, "the geometry hash is never salted")

    def test_a_sealed_plaintext_needs_its_salt_and_its_manifest(self):
        self.assertEqual([{"code": "salt_required"}], list(self.sealed(note(mv.P_F)).violations))
        other = mv.changed(mv.P_SEALED, manifest_id=mv.ID["A"])
        self.assertEqual([{"code": "manifest_mismatch", "path": "/manifest_id"}],
                         list(self.sealed(note(other)).violations))
        self.assertEqual([{"code": "malformed_json"}], list(self.sealed(b"hello").violations))
        self.assertEqual([{"code": "oversize", "size_bytes": 4097}],
                         list(self.sealed(mv.padded(mv.P_SEALED, 4097)).violations))
        nested = self.sealed(mv.NOTE_SEALED)
        self.assertEqual("rejected", nested.outcome)
        self.assertNotIn("sealed_unopened", nested.outcome)

    def test_an_opener_failure_is_a_code_and_any_other_fault_propagates(self):
        def unopenable(_age_file, _manifest):
            raise Unopenable()

        def broken(_age_file, _manifest):
            raise RuntimeError("bug")
        self.assertEqual([{"code": "sealed_undecryptable"}], list(self.sealed(b"", opener=unopenable).violations))
        with self.assertRaises(RuntimeError):
            self.sealed(b"", opener=broken)
        with self.assertRaises(TypeError):
            self.sealed(b"", opener=lambda _a, _m: "not bytes")

    def test_the_layout_seam(self):
        calls = []

        def checker(proposal, manifest):
            calls.append(proposal["proposal_key"])
            return [{"code": "halo_overlap", "dies": [0, 1], "amount_um": 40}]
        off = mv.with_dies(mv.P_F, [(3250, 5000, 0), (7000, 5000, 0)])
        outcome = validate_check_note(note(off), manifests=REGISTRY, manifest_id=mv.ID["F"], layout_checker=checker)
        self.assertEqual([{"code": "lattice", "dies": [0], "amount_um": 250},
                          {"code": "halo_overlap", "dies": [0, 1], "amount_um": 40}], list(outcome.violations))
        clean = validate_check_note(note(mv.P_F), manifests=REGISTRY, manifest_id=mv.ID["F"],
                                    layout_checker=lambda _p, _m: [])
        self.assertEqual("legal", clean.outcome)
        calls.clear()
        validate_check_note(note(mv.with_dies(mv.P_F, [(3000, 5000, 0)])), manifests=REGISTRY,
                            manifest_id=mv.ID["F"], layout_checker=checker)
        self.assertEqual([], calls, "no layout check without a catalogue mapping")
        for bad in ([{"code": "lattice", "dies": [0], "amount_um": 1}], [{"code": "margin", "dies": [0]}],
                    [{"code": "margin", "dies": [0], "amount_um": -1}]):
            with self.assertRaises(ValueError):
                validate_check_note(note(mv.P_F), manifests=REGISTRY, manifest_id=mv.ID["F"],
                                    layout_checker=lambda _p, _m, bad=bad: bad)

    def test_nothing_submitted_is_ever_echoed(self):
        marker = "ZZMARKER"
        attempts = [{**mv.P_F, marker: "x"}, {**mv.P_F, "note": marker},
                    mv.changed(mv.P_F, proposal_key=marker), mv.changed(mv.P_F, client={"name": marker + "<",
                                                                                      "version": "1"}),
                    {**mv.P_F, "dies": [{**mv.TEST_LAYOUT[0], marker: 1}, mv.TEST_LAYOUT[1]]}]
        for value in attempts:
            for outcome in (validate_check_note(note(value), manifests=REGISTRY, manifest_id=mv.ID["F"]),
                            validate_submission(note(value), reply=HUMAN_REPLY, manifests=REGISTRY,
                                                thread_manifest_id=mv.ID["F"], admission=OPEN)):
                self.assertEqual("rejected", outcome.outcome)
                self.assertNotIn(marker, json.dumps(list(outcome.violations)))
        raw = note(mv.P_F)[:-1] + b', "' + marker.encode() + b'": NaN}'
        outcome = validate_check_note(raw, manifests=REGISTRY, manifest_id=mv.ID["F"])
        self.assertNotIn(marker, json.dumps(list(outcome.violations)))

    def test_violations_are_cut_at_the_envelope_cap_after_the_decision(self):
        manifest = copy.deepcopy(mv.F)
        manifest["dies"] = [{"die": index, "name": "d", "w_um": 100, "h_um": 100, "power_w": 1, "halo_um": 0,
                             "rot_deg": [0]} for index in range(32)]
        manifest["netlist"] = [[0] * 32 for _ in range(32)]
        manifest_id = h.manifest_id(manifest)
        value = {**mv.P_F, "manifest_id": manifest_id,
                 "dies": [{"die": index, "x_um": 10750, "y_um": 250, "rot_deg": 0} for index in range(32)],
                 "geometry_sha256": "0" * 64}
        outcome = validate_check_note(note(value), manifests={manifest_id: manifest}, manifest_id=manifest_id)
        self.assertEqual("rejected", outcome.outcome)
        self.assertEqual(64, MAX_ITEMS)
        self.assertEqual(MAX_ITEMS, len(outcome.violations), "the envelope's per-list cap, not our own constant")
        self.assertEqual(MAX_ITEMS, MAX_VIOLATIONS)
        self.assertEqual("out_of_frame", outcome.violations[0]["code"])

    def test_check_param_decoding_is_canonical_only(self):
        for raw in (b"", b"{", b"{}", b"{}x", bytes(range(256))):
            encoded = mv.b64url(raw)
            self.assertEqual(raw, decode_param(encoded))
        self.assertIsNone(decode_param("A"))
        self.assertIsNone(decode_param(mv.non_canonical(b"{}")))

    def test_chat_detection(self):
        self.assertFalse(is_chat(b" \r\n\t{"))
        self.assertFalse(is_chat(bytes((0xEF, 0xBB, 0xBF)) + b"{"))
        self.assertFalse(is_chat(b"```json"))
        self.assertTrue(is_chat(b"[1]"))
        self.assertTrue(is_chat(b""))
        self.assertTrue(is_chat(bytes((0xC2, 0xA0)) + b"{"), "only ASCII blanks are trimmed")

    def test_the_intake_and_records_refuse_missing_context(self):
        with self.assertRaises(TypeError):
            validate_submission(b"{}", reply=None, manifests=REGISTRY, thread_manifest_id=mv.ID["F"], admission=OPEN)
        with self.assertRaises(TypeError):
            validate_submission(b"{}", reply=HUMAN_REPLY, manifests=REGISTRY, thread_manifest_id=mv.ID["F"],
                                admission=None)
        with self.assertRaises(TypeError):
            validate_check_note("{}", manifests=REGISTRY, manifest_id=mv.ID["F"])
        with self.assertRaises(ValueError):
            validate_record("proposal", {})
        with self.assertRaises(ValueError):
            validate_record("receipt", {}, audience="internal")


class Rules(unittest.TestCase):
    def test_scoring_needs_a_measured_reference(self):
        manifest = mv.edit(mv.F, ["reference", "t_ref"], None)
        record = mv.results(mv.outside())
        record["manifest_id"] = h.manifest_id(manifest)
        self.assertEqual([{"code": "record_inconsistent", "path": "/rows/0", "rule": "results.scoring"}],
                         validate_record("results", record, manifest=manifest))

    def test_maximal_signed_records_fit_the_view_envelope(self):
        """The schemas bound every signed record inside sentilab_core/envelope.py's caps."""
        violation = {"code": "die_order", "dies": list(range(32))}
        receipt = mv.receipt(state="rejected", codes=[violation] * 64)
        receipt["values"]["geometry"] = receipt["values"]["geometry"] * 16
        self.assertTrue(VALIDATORS["receipt"].is_valid(receipt))
        check_caps(receipt)
        restricted = mv.restricted(intake={"account_id": mv.INTAKE["account_id"], "agent_id": "a" * 120},
                                   actor_kind="agent", actor_agent_id="b" * 120)
        self.assertTrue(VALIDATORS["restricted-receipt"].is_valid(restricted))
        check_caps(restricted)
        usage = mv.usage(codes=[violation] * 64)
        self.assertTrue(VALIDATORS["usage"].is_valid(usage))
        check_caps(usage)

    def test_derivations_refuse_weak_inputs(self):
        with self.assertRaises(ValueError):
            h.participant_ref(b"short", "c", mv.HUMAN)
        with self.assertRaises(ValueError):
            h.derive_salt(b"short", mv.ID["F"], "k")
        with self.assertRaises(ValueError):
            h.capability("00", mv.ID["F"], "0" * 64)
        for kind, agent in (("human", "a"), ("agent", None), ("agent", ""), ("robot", None)):
            with self.assertRaises(ValueError):
                h.actor_slot(kind, agent)
        with self.assertRaises(ValueError):
            h.run_id("Z" * 64, "sentilab")
        with self.assertRaises(TypeError):
            h.body_sha256("text")
        self.assertEqual("open-tk1-", h.transport_id(room=mv.ROOM, account_id=mv.HUMAN, actor_kind="human",
                                                     actor_agent_id=None, manifest_id="0" * 64, proposal_key="k",
                                                     proposal_sha256="0" * 64)[:9])

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
        both = dict(LISTS, accepted=(withdrawn,))
        self.assertEqual("withdrawn", label_for(withdrawn, both), "withdrawn wins over any other list")

    def test_a_wire_diagnostic_leaves_the_temperature_label_intact(self):
        """A high-wire diagnostic carries its own evaluator and label; the temperature keeps its own."""
        row = mv.outside(diagnostics=[mv.HIGH_WIRE])
        self.assertEqual("unvalidated", label_for(mv.HIGH_WIRE["evaluator"]))
        self.assertEqual("illustrative", row["temperature"]["label"])
        self.assertEqual("illustrative", label_for(row["temperature"]["evaluator"]))
        self.assertEqual([], validate_record("results", mv.results(row), manifest=mv.F))
        replaced = mv.edit(row, ["temperature", "label"], mv.HIGH_WIRE["label"])
        self.assertEqual([{"code": "label_mismatch", "path": "/rows/0/temperature", "rule": "label.single"}],
                         validate_record("results", mv.results(replaced), manifest=mv.F))
        self.assertEqual(row["claims"], mv.outside()["claims"], "a diagnostic suppresses no claim")

    def test_capability_epochs_rotate_and_bind(self):
        salt, sha = mv.SALT, h.proposal_sha256(mv.P_SEALED)
        first, second = h.capability(salt, mv.ID["F"], sha), h.capability(salt, mv.ID["F"], sha, 2)
        self.assertNotEqual(first, second)
        self.assertEqual(first, h.capability(salt, mv.ID["F"], sha, 1))
        for epoch in (0, -1, True, 1.0):
            with self.assertRaises(ValueError):
                h.capability(salt, mv.ID["F"], sha, epoch)

    def test_accepted_labels_would_decide_claims(self):
        """With an accepted identity (none exist yet) an unvalidated claim would become decidable."""
        identity = "HotSpot-6.0:" + mv.HOTSPOT6
        record = mv.results(mv.outside(claims=[mv.claim("strict_wire_thermal_tolerance", mv.PASSES,
                                                        evaluators=[identity], label="accepted")],
                                       comparison=None))
        self.assertEqual([{"code": "label_mismatch", "path": "/rows/0/claims/0", "rule": "label.derived"}],
                         validate_record("results", record))
        lists = dict(LISTS, accepted=(identity,))
        self.assertEqual([], validate_record("results", record, lists=lists))

    def test_the_summary_covers_every_lifecycle_state(self):
        self.assertEqual(set(SCHEMAS["common"]["$defs"]["lifecycle_state"]["enum"]), set(SUMMARY))
        with self.assertRaises(TransitionRefused):
            transition("queued", "start", {})


if __name__ == "__main__":
    unittest.main()
