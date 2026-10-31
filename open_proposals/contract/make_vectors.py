"""Builds contracts/open-proposal-v1/vectors-canonical.json, limits.provisional.json and golden/*.json.

Every input, every expected outcome and every expected code below is written by hand. Hashes are computed with the
contract's functions and cross-checked independently by the JavaScript twin (run-vectors.mjs) and the tests.

    python -m open_proposals.contract.make_vectors           # rewrite the files
    python -m open_proposals.contract.make_vectors --check   # exit 1 if a committed file differs

Fixture identities are obviously fake (00000000-0000-4000-8000-...). The test keys derive from public phrases at run
time; no key material is stored. Sealed envelopes here are shape tests only: no age implementation was available
offline, so no age ciphertext is generated (see the "age" entry of the vectors).
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import sys
from pathlib import Path

from . import canonical as h
from .schemas import CONTRACT_DIR

GOLDEN = CONTRACT_DIR / "golden"
PSEUDONYM_PHRASE = "sentilab-open-proposal-v1 test pseudonym key, not a secret"
CLIENT_PHRASE = "sentilab-open-proposal-v1 test client secret, not a secret"
PSEUDONYM_KEY = hashlib.sha256(PSEUDONYM_PHRASE.encode()).digest()
CLIENT_SECRET = hashlib.sha256(CLIENT_PHRASE.encode()).digest()

# Obviously fake identities. The two participants are outside (non-staff) accounts: one human via REST, one agent.
HUMAN = "00000000-0000-4000-8000-00000000000a"
AGENT_ACCOUNT = "00000000-0000-4000-8000-00000000000b"
INTAKE = {"account_id": "00000000-0000-4000-8000-0000000000f0", "agent_id": "example-intake"}
ROOM = "00000000-0000-4000-8000-0000000000c1"
OVERFLOW_ROOM = "00000000-0000-4000-8000-0000000000c2"
ACTIONS = [f"00000000-0000-4000-8000-0000000000a{index}" for index in range(1, 10)]
RESERVATIONS = [f"00000000-0000-4000-8000-0000000000e{index}" for index in range(1, 6)]
FAKE_CAPABILITY = "opencap1-" + "0" * 63 + "1"
ROUTER_SHA256 = "bed6fa4ad0035cd67ea2b6bc2f498775767893a601ad2dea855e4f3a4a966568"   # PR #57 tap_router.py @063f659
HOTSPOT6 = "a7a3286e368867c26381e0a23e36b3e273bdeda9"
WITHDRAWN = "HotSpot-7:f18831e48cef5d62580585cca0d7fab6c71bc3cc:grid:64x64"
FIXTURE = "fixture-no-solver"
AGE_HEADER_ONLY = b"age-encryption.org/v1\n"      # the v1 header line alone: a shape test, never a ciphertext


def fake(label: str) -> str:
    """A stand-in digest for a pin of the illustrative test fixture."""
    return hashlib.sha256(("sentilab-open-proposal-v1 test pin: " + label).encode()).hexdigest()


TERMS = {"id": "sentilab-open-terms/1", "permits": ["evaluation", "evidence", "display"], "training": False}
LEGALITY = {"units": "um", "anchor": "die-centre", "origin": "frame lower-left", "lattice_um": 500,
            "lattice_basis": "engineering_benchmark", "margin_um": 500, "min_die_gap_um": 100,
            "rotation": "per_die_90"}
CASES = {"replay": {"id": "replay", "kind": "replay", "applies_to": "both", "grid": None, "die": None, "dx_um": None,
                    "dy_um": None},
         "grid32": {"id": "grid32", "kind": "mesh", "applies_to": "both", "grid": 32, "die": None, "dx_um": None,
                    "dy_um": None},
         "pos-a-x": {"id": "pos-a-x", "kind": "position", "applies_to": "reference", "grid": None, "die": 0,
                     "dx_um": 500, "dy_um": 0}}


def temperature(t_m, evaluator, label, *, peak=None, argmax=None, selector=None):
    return {"statistic": "chiplet-centre-max", "T_M_c": t_m, "grid_peak_c": peak, "grid_argmax": argmax,
            "tap_selector_c": selector, "evaluator": evaluator, "label": label}


def wire(routed, evaluator, label, *, proxy=None, status=None):
    return {"routed_mm": routed, "routed_status": status or ("optimal" if routed is not None else "timeout"),
            "proxy_mm": proxy, "evaluator": evaluator, "label": label}


def dies_from(rows):
    return [{"die": index, "x_um": x, "y_um": y, "rot_deg": rot} for index, (x, y, rot) in enumerate(rows)]


# The Ascend 910 snap0p5 engineering variant: the raw centres (PR #57 README) rounded to the 0.5 mm lattice.
ASCEND_SNAP0P5 = dies_from([(17000, 22500, 90), (38500, 22500, 0), (7500, 11000, 90), (21500, 11000, 90),
                            (7500, 34000, 90), (21500, 34000, 90)])
TEST_LAYOUT = dies_from([(3000, 5000, 0), (7000, 5000, 0)])


def draft_ascend() -> dict:
    manifest = {
        "schema": "sentilab-open-manifest/1", "version": 0, "status": "draft", "challenge": "sentilab-open-1",
        "problem": "ascend910", "terms": TERMS,
        "fixture": {"id": "ascend910-45mm", "config": "sundai_tap/configs/sys_ascend910_45mm.cfg",
                    "config_sha256": "4a922560510ba0ab66d04030f137f80262891e7ac7afac3025a57f539e885a8c",
                    "frame_um": 45000, "ambient_c": 45, "link_type": "nppl"},
        "dies": [{"die": 0, "name": "compute", "w_um": 14500, "h_um": 31400, "power_w": 256, "halo_um": 90,
                  "rot_deg": [0, 90]},
                 {"die": 1, "name": "io", "w_um": 10500, "h_um": 16000, "power_w": 14, "halo_um": 45,
                  "rot_deg": [0, 90]}]
                + [{"die": index, "name": "hbm", "w_um": 7750, "h_um": 11870, "power_w": 20, "halo_um": 45,
                    "rot_deg": [0, 90]} for index in range(2, 6)],
        "netlist": [[0, 200, 256, 256, 256, 256]] + [[200, 0, 0, 0, 0, 0]] + [[256, 0, 0, 0, 0, 0]] * 4,
        "legality": LEGALITY,
        "reference": {
            "id": "ascend910-tap25d-fig6a", "sha256": None, "track": "MATCH", "verdict_layout": "raw",
            "coordinate_model": "continuous", "legal": False, "t_ref": None,
            "w_ref": wire(16417.5, "tap-router:" + ROUTER_SHA256, "unvalidated", proxy=18.82),
            "paper": {"t_c": 75.48, "w_mm": 16426, "source": "TAP-2.5D paper Fig. 6(a): HotSpot 6.0 and CPLEX",
                      "evaluator": "paper:TAP-2.5D:HotSpot-6.0+CPLEX", "label": "unvalidated"},
            "engineering_variant": None},
        "temperature": {"statistic": "chiplet-centre-max", "grid": 64, "grid_map_mode": "center",
                        "evaluator": {"kind": "hotspot6", "upstream": HOTSPOT6, "binary_sha256": None,
                                      "gate_zero_record_sha256": None, "identity": None}},
        "wire": {"judged": "routed", "proxy": "diagnostic", "router_sha256": None, "time_limit_s": None,
                 "evaluator": None},
        "thresholds": {"status": "provisional", "D_k": 0.5, "B_T_k": 1.0,
                       "B_W": {"fraction": 0.02, "of_reference_wire_mm": 16417.5}, "scenario_target_c": 85,
                       "tradeoff_budgets": [0.1, 0.25, 0.5, 1.0]},
        "wire_tracks": [{"id": "strict", "factor": 1}, {"id": "relaxed", "factor": 1.05}],
        "sensitivity": {"status": "provisional", "cases": [CASES["replay"], CASES["grid32"]]},
        "discrimination_control": [
            {"id": "reference", "source_sha256": None,
             "expected": [{"type": "strict_wire_thermal_tolerance", "r": None, "outcome": "passes_listed_cases"},
                          {"type": "strict_thermal_improvement", "r": None, "outcome": "fails_listed_cases"}]},
            {"id": "fig6c", "source_sha256": None,
             "expected": [{"type": "relaxed_wire_thermal_tolerance", "r": 0.05, "outcome": "passes_listed_cases"},
                          {"type": "strict_thermal_improvement", "r": None, "outcome": "fails_listed_cases"}]},
            {"id": "fig6b", "source_sha256": None,
             "expected": [{"type": "relaxed_wire_thermal_tolerance", "r": 0.05, "outcome": "fails_listed_cases"}]}],
        "example": {"temperature": temperature(75.8, FIXTURE, "illustrative"),
                    "wire": wire(16700.0, FIXTURE, "illustrative")},
        "window": {"opens_at": None, "closes_at": None},
        "refs": {"grant": None, "claim_rules": None, "checker_sha256": None},
        "sealing": {"format": "age-encryption.org/v1", "recipient": None, "key_version": None,
                    "rotation": {"policy": "new_manifest_version", "not_after": None}}}
    variant = {"problem": "ascend910", "units": "um", "anchor": "die-centre", "lattice_um": 500,
               "dies": ASCEND_SNAP0P5}
    manifest["reference"]["engineering_variant"] = {
        "id": "ascend910-tap25d-fig6a-snap0p5", "grid_um": 500,
        "geometry_sha256": h.geometry_sha256(variant, manifest), "design_hash": None, "legal": True}
    return manifest


def draft_micro150() -> dict:
    manifest = draft_ascend()
    manifest.update({
        "problem": "micro150",
        "fixture": {"id": "micro150-45mm", "config": "sundai_tap/configs/sys_micro150_45mm.cfg",
                    "config_sha256": "da94828d683b0d16a243907d51927761892e82f9725f17bc96ab1c867563ed89",
                    "frame_um": 45000, "ambient_c": 45, "link_type": "nppl"},
        "dies": [{"die": index, "name": "cpu", "w_um": 8250, "h_um": 9000, "power_w": 150, "halo_um": 180,
                  "rot_deg": [0, 90]} for index in range(4)]
                + [{"die": index, "name": "dram", "w_um": 8750, "h_um": 8750, "power_w": 20, "halo_um": 135,
                    "rot_deg": [0]} for index in range(4, 8)],
        "netlist": [[0, 256, 0, 256, 1024, 0, 0, 0], [256, 0, 256, 0, 0, 1024, 0, 0],
                    [0, 256, 0, 256, 0, 0, 1024, 0], [256, 0, 256, 0, 0, 0, 0, 1024],
                    [1024, 0, 0, 0, 0, 0, 0, 0], [0, 1024, 0, 0, 0, 0, 0, 0],
                    [0, 0, 1024, 0, 0, 0, 0, 0], [0, 0, 0, 1024, 0, 0, 0, 0]],
        "discrimination_control": [
            {"id": "fig5c", "source_sha256": None,
             "expected": [{"type": "strict_thermal_improvement", "r": None, "outcome": "fails_listed_cases"}]},
            {"id": "fig5d", "source_sha256": None,
             "expected": [{"type": "strict_thermal_improvement", "r": None, "outcome": "fails_listed_cases"}]}],
        "example": None})
    manifest["reference"] = {
        "id": "micro150-tap25d-fig5a", "sha256": None, "track": "BEAT", "verdict_layout": "raw",
        "coordinate_model": "continuous", "legal": False, "t_ref": None,
        "w_ref": wire(67688.4, "tap-router:" + ROUTER_SHA256, "unvalidated", proxy=9.38),
        "paper": {"t_c": 115.94, "w_mm": 67686, "source": "TAP-2.5D paper Fig. 5(a): HotSpot 6.0 and CPLEX",
                  "evaluator": "paper:TAP-2.5D:HotSpot-6.0+CPLEX", "label": "unvalidated"},
        "engineering_variant": {"id": "micro150-tap25d-fig5a-snap0p5", "grid_um": 500, "geometry_sha256": None,
                                "design_hash": None, "legal": True}}
    manifest["thresholds"]["B_W"] = {"fraction": 0.02, "of_reference_wire_mm": 67688.4}
    return manifest


def frozen_test() -> dict:
    """An illustrative interface fixture: two dies, frozen, every value from the no-solver fixture identity."""
    manifest = {
        "schema": "sentilab-open-manifest/1", "version": 1, "status": "frozen", "challenge": "test-challenge",
        "problem": "test-two-die", "terms": TERMS,
        "fixture": {"id": "test-two-die-10mm", "config": "test/two-die-10mm.cfg",
                    "config_sha256": fake("two-die config"), "frame_um": 10000, "ambient_c": 45,
                    "link_type": "nppl"},
        "dies": [{"die": 0, "name": "a", "w_um": 2000, "h_um": 3000, "power_w": 10, "halo_um": 50,
                  "rot_deg": [0, 90]},
                 {"die": 1, "name": "b", "w_um": 2000, "h_um": 2000, "power_w": 5, "halo_um": 50, "rot_deg": [0]}],
        "netlist": [[0, 4], [4, 0]],
        "legality": LEGALITY,
        "reference": {
            "id": "test-two-die-ref", "sha256": fake("reference file"), "track": "MATCH", "verdict_layout": "raw",
            "coordinate_model": "continuous", "legal": False,
            "t_ref": temperature(60.0, FIXTURE, "illustrative", peak=60.4, argmax={"row": 31, "col": 30},
                                 selector=60.1),
            "w_ref": wire(100.0, FIXTURE, "illustrative", proxy=5.0),
            "paper": {"t_c": 60.5, "w_mm": 101, "source": "illustrative fixture: no paper", "evaluator": FIXTURE,
                      "label": "illustrative"},
            "engineering_variant": None},
        "temperature": {"statistic": "chiplet-centre-max", "grid": 64, "grid_map_mode": "center",
                        "evaluator": {"kind": "hotspot6", "upstream": HOTSPOT6, "binary_sha256": fake("binary"),
                                      "gate_zero_record_sha256": fake("gate zero record"), "identity": FIXTURE}},
        "wire": {"judged": "routed", "proxy": "diagnostic", "router_sha256": fake("router"), "time_limit_s": 1.5,
                 "evaluator": FIXTURE},
        "thresholds": {"status": "frozen", "D_k": 0.5, "B_T_k": 1.0,
                       "B_W": {"fraction": 0.02, "of_reference_wire_mm": 100.0}, "scenario_target_c": 85,
                       "tradeoff_budgets": [0.1, 0.25, 0.5, 1.0]},
        "wire_tracks": [{"id": "strict", "factor": 1}],
        "sensitivity": {"status": "frozen", "cases": [CASES["replay"], CASES["grid32"], CASES["pos-a-x"]]},
        "discrimination_control": [
            {"id": "test-control", "source_sha256": fake("control source"),
             "expected": [{"type": "strict_wire_thermal_tolerance", "r": None, "outcome": "passes_listed_cases"}]}],
        "example": {"temperature": temperature(60.3, FIXTURE, "illustrative"),
                    "wire": wire(98.0, FIXTURE, "illustrative")},
        "window": {"opens_at": "2026-11-01T00:00:00Z", "closes_at": "2026-11-08T00:00:00Z"},
        "refs": {"grant": "test-grant", "claim_rules": "test-claim-rules", "checker_sha256": fake("checker")},
        "sealing": {"format": "age-encryption.org/v1", "recipient": "age1" + "q" * 58, "key_version": 1,
                    "rotation": {"policy": "new_manifest_version", "not_after": "2026-11-08T00:00:00Z"}}}
    variant = {"problem": "test-two-die", "units": "um", "anchor": "die-centre", "lattice_um": 500,
               "dies": TEST_LAYOUT}
    manifest["reference"]["engineering_variant"] = {
        "id": "test-two-die-ref-snap0p5", "grid_um": 500, "geometry_sha256": h.geometry_sha256(variant, manifest),
        "design_hash": fake("variant design"), "legal": True}
    return manifest


A, M, F = draft_ascend(), draft_micro150(), frozen_test()
MANIFESTS = {"A": A, "M": M, "F": F}
ID = {key: h.manifest_id(value) for key, value in MANIFESTS.items()}


def proposal(manifest_key: str, dies, *, key="example-1", track=None, parent=None, client=True, salt=None) -> dict:
    manifest = MANIFESTS[manifest_key]
    value = {"schema": "sentilab-open-proposal/1", "manifest_id": ID[manifest_key], "problem": manifest["problem"],
             "reference_id": manifest["reference"]["id"],
             "wire_track": track or manifest["wire_tracks"][-1]["id"], "proposal_key": key, "parent": parent,
             "units": "um", "anchor": "die-centre", "lattice_um": manifest["legality"]["lattice_um"],
             "dies": copy.deepcopy(dies), "geometry_sha256": "", "terms": "sentilab-open-terms/1"}
    if salt is not None:
        value["salt"] = salt
    if client:
        value["client"] = {"name": "example-agent", "version": "0.1.0"}
    value["geometry_sha256"] = h.geometry_sha256(value, manifest)
    return value


P_A = proposal("A", ASCEND_SNAP0P5)
P_F = proposal("F", TEST_LAYOUT, key="t-1", track="strict")
SALT = h.derive_salt(CLIENT_SECRET, ID["F"], "t-2")
P_SEALED = proposal("F", TEST_LAYOUT, key="t-2", track="strict", salt=SALT)


def text(value) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode()


def fenced(value, newline=b"\n") -> bytes:
    return b"```json" + newline + text(value) + newline + b"```"


def padded(value, size: int) -> bytes:
    raw = text(value)
    return raw[:-1] + b" " * (size - len(raw)) + raw[-1:]


def note_entry(note: bytes) -> dict:
    try:
        decoded = note.decode("utf-8")
        if not note.startswith(bytes((0xEF, 0xBB, 0xBF))):
            return {"note": decoded}
    except UnicodeDecodeError:
        pass
    return {"note_b64": base64.b64encode(note).decode()}


def changed(value: dict, **edits) -> dict:
    """A copy of a proposal with fields replaced, its geometry hash recomputed unless set explicitly."""
    result = copy.deepcopy(value)
    result.update(edits)
    if "geometry_sha256" not in edits:
        manifest = next(m for k, m in MANIFESTS.items() if ID[k] == value["manifest_id"])
        result["geometry_sha256"] = h.geometry_sha256(result, manifest)
    return result


def with_dies(value: dict, rows) -> dict:
    return changed(value, dies=dies_from(rows))


def without(value: dict, field: str) -> dict:
    result = copy.deepcopy(value)
    del result[field]
    return result


def raw_text(value: dict, old: str, new: str) -> bytes:
    """The note's text with one literal replaced: for inputs a JSON encoder will not produce."""
    source = json.dumps(value)
    if source.count(old) != 1:
        raise ValueError("ambiguous replacement")
    return source.replace(old, new).encode()


def sealed_note(manifest_key: str, *, key_version=1, age_file=AGE_HEADER_ONLY, extra=None) -> bytes:
    envelope = {"schema": "sentilab-open-sealed/1", "manifest_id": ID[manifest_key], "key_version": key_version,
                "format": "age-encryption.org/v1", "ciphertext": base64.b64encode(age_file).decode()}
    envelope.update(extra or {})
    return text(envelope)


def C(code, **fields):
    return {"code": code, **fields}


def intake(name, note, expect_outcome, codes=(), *, manifest="F", admission="open", actor=HUMAN, revision=1,
           edited_at=None):
    entry = {"name": name, "route": "intake", "thread_manifest": manifest,
             "admission": {key: admission for key in (manifest,)},
             "reply": {"actor_user_id": actor, "message_revision": revision, "edited_at": edited_at}}
    entry.update(note_entry(note))
    entry["expect"] = {"outcome": expect_outcome, "codes": list(codes)}
    return entry


def check(name, note, expect_outcome, codes=(), *, manifest="A"):
    entry = {"name": name, "route": "check", "manifest": manifest}
    entry.update(note_entry(note))
    entry["expect"] = {"outcome": expect_outcome, "codes": list(codes)}
    return entry


def note_cases() -> list:
    deep_client = changed(P_F, client={"name": {"a": {"b": {}}}, "version": "1"})
    four_deep = changed(P_F, client={"name": {"a": {"b": 1}}, "version": "1"})
    cases = [
        intake("valid proposal, bare JSON", text(P_F), "contract_valid"),
        intake("valid proposal in a json fence", fenced(P_F), "contract_valid"),
        intake("valid proposal in a json fence with CRLF line ends", fenced(P_F, b"\r\n"), "contract_valid"),
        intake("valid proposal padded to exactly 4096 bytes", padded(P_F, 4096), "contract_valid"),
        intake("chat in the thread is ignored", b"Is this the right thread for proposals?", "ignored"),
        intake("an edited chat message is still ignored", b"thanks!", "ignored", revision=2),
        intake("4097 bytes", padded(P_F, 4097), "rejected", [C("oversize", size_bytes=4097)]),
        intake("a leading BOM", bytes((0xEF, 0xBB, 0xBF)) + text(P_F), "rejected", [C("not_utf8")]),
        intake("invalid UTF-8", text(P_F)[:-1] + b' "x": "\xff"}', "rejected", [C("not_utf8")]),
        intake("no actorUserId on the row", text(P_F), "rejected", [C("unattributable")], actor=None),
        intake("edited before ingest", text(P_F), "rejected", [C("edited_before_ingest")], revision=2),
        intake("editedAt set at revision 1", text(P_F), "rejected", [C("edited_before_ingest")],
               edited_at="2026-11-01T10:00:01+00:00"),
        intake("unattributable and edited", text(P_F), "rejected", [C("edited_before_ingest"), C("unattributable")],
               actor=None, revision=3),
        intake("a trailing comma", text(P_F)[:-1] + b",}", "rejected", [C("malformed_json")]),
        intake("trailing text after the object", text(P_F) + b" please evaluate", "rejected", [C("malformed_json")]),
        intake("a fence without the json tag", b"```\n" + text(P_F) + b"\n```", "rejected", [C("malformed_json")]),
        intake("a fence holding an array", b"```json\n[1, 2]\n```", "rejected", [C("malformed_json")]),
        intake("a duplicate key", raw_text(P_F, '"units": "um"', '"units": "um", "units": "um"'), "rejected",
               [C("duplicate_key")]),
        intake("NaN", raw_text(P_F, '"lattice_um": 500', '"lattice_um": NaN'), "rejected",
               [C("nonfinite_number")]),
        intake("a number that overflows to infinity", raw_text(P_F, '"lattice_um": 500', '"lattice_um": 1e400'),
               "rejected", [C("nonfinite_number")]),
        intake("a duplicate key and Infinity", raw_text(P_F, '"units": "um"', '"units": "um", "units": Infinity'),
               "rejected", [C("duplicate_key"), C("nonfinite_number")]),
        intake("five levels deep", text(deep_client), "rejected", [C("too_deep")]),
        intake("four levels deep reaches the schema", text(four_deep), "rejected",
               [C("schema_invalid", path="/client/name", keyword="type")]),
        intake("a note field is unknown and never echoed", text({**P_F, "note": "<b>please</b> evaluate"}),
               "rejected", [C("unknown_field", path="")]),
        intake("an unknown field inside a die", text(changed(P_F, dies=[{**TEST_LAYOUT[0], "power_w": 9},
                                                                         TEST_LAYOUT[1]])),
               "rejected", [C("unknown_field", path="/dies/0")]),
        intake("a fractional coordinate literal", raw_text(P_F, '"x_um": 3000', '"x_um": 3000.0'), "rejected",
               [C("schema_invalid", path="/dies/0/x_um", keyword="type")]),
        intake("an exponent coordinate literal", raw_text(P_F, '"x_um": 3000', '"x_um": 3e3'), "rejected",
               [C("schema_invalid", path="/dies/0/x_um", keyword="type")]),
        intake("rotation 45", text(with_dies(P_F, [(3000, 5000, 45), (7000, 5000, 0)])), "rejected",
               [C("schema_invalid", path="/dies/0/rot_deg", keyword="enum")]),
        intake("rotation true", raw_text(P_F, '"rot_deg": 0}, {"die": 1', '"rot_deg": true}, {"die": 1'),
               "rejected", [C("schema_invalid", path="/dies/0/rot_deg", keyword="enum"),
                            C("schema_invalid", path="/dies/0/rot_deg", keyword="type")]),
        intake("a proposal key of 64 characters", text(changed(P_F, proposal_key="k" * 64)), "contract_valid"),
        intake("a proposal key of 65 characters", text(changed(P_F, proposal_key="k" * 65)), "rejected",
               [C("schema_invalid", path="/proposal_key", keyword="pattern")]),
        intake("a client name of 33 characters", text(changed(P_F, client={"name": "n" * 33, "version": "1"})),
               "rejected", [C("schema_invalid", path="/client/name", keyword="pattern")]),
        intake("an uppercase proposal key", text(changed(P_F, proposal_key="Team-A")), "rejected",
               [C("schema_invalid", path="/proposal_key", keyword="pattern")]),
        intake("no geometry hash", text(without(P_F, "geometry_sha256")), "rejected",
               [C("schema_invalid", path="/geometry_sha256", keyword="required")]),
        intake("no terms reference", text(without(P_F, "terms")), "rejected",
               [C("schema_invalid", path="/terms", keyword="required")]),
        intake("no declared lattice", text(without(P_F, "lattice_um")), "rejected",
               [C("schema_invalid", path="/lattice_um", keyword="required")]),
        intake("33 dies", text(changed(P_F, dies=[TEST_LAYOUT[0]] * 33, geometry_sha256="0" * 64)), "rejected",
               [C("schema_invalid", path="/dies", keyword="maxItems")]),
        intake("a negative coordinate", text(with_dies(P_F, [(-500, 5000, 0), (7000, 5000, 0)])), "rejected",
               [C("schema_invalid", path="/dies/0/x_um", keyword="minimum")]),
        intake("a coordinate past the static bound", text(with_dies(P_F, [(1000500, 5000, 0), (7000, 5000, 0)])),
               "rejected", [C("schema_invalid", path="/dies/0/x_um", keyword="maximum")]),
        intake("another schema version", text(changed(P_F, schema="sentilab-open-proposal/2")), "rejected",
               [C("schema_invalid", path="/schema", keyword="const")]),
        intake("markup in the client name, never echoed",
               text(changed(P_F, client={"name": "<script>x</script>", "version": "1"})), "rejected",
               [C("schema_invalid", path="/client/name", keyword="pattern")]),
        intake("a parent that is not a hash", text(changed(P_F, parent="team-a-06")), "rejected",
               [C("schema_invalid", path="/parent", keyword="pattern")]),
        intake("a public proposal may not carry a salt", text(changed(P_F, salt=SALT)), "rejected",
               [C("salt_forbidden")]),
        intake("an unknown manifest", text(changed(P_F, manifest_id="1" * 64)), "rejected", [C("unknown_manifest")]),
        intake("another known manifest than the thread's", text(P_A), "rejected",
               [C("manifest_mismatch", path="/manifest_id")]),
        intake("problem and reference disagree with the manifest",
               text(changed(P_F, problem="ascend910", reference_id="ascend910-tap25d-fig6a")), "rejected",
               [C("manifest_mismatch", path="/problem"), C("manifest_mismatch", path="/reference_id")]),
        intake("a different declared lattice", text(changed(P_F, lattice_um=1000)), "rejected",
               [C("manifest_mismatch", path="/lattice_um")]),
        intake("a track this manifest does not admit", text(changed(P_F, wire_track="relaxed")), "rejected",
               [C("wire_track_not_admitted")]),
        intake("other submission terms", text(changed(P_F, terms="sentilab-open-terms/2")), "rejected",
               [C("terms_mismatch")]),
        intake("a closed manifest", text(P_F), "rejected", [C("manifest_closed")], admission="closed"),
        intake("a manifest not open yet", text(P_F), "rejected", [C("not_open_yet")], admission="not_open_yet"),
        intake("a draft manifest is never open, whatever admission says", text(P_A), "rejected",
               [C("not_open_yet")], manifest="A", admission="open"),
        intake("a wrong geometry hash", text(changed(P_F, geometry_sha256="0" * 64)), "rejected",
               [C("geometry_hash_mismatch")]),
        intake("one die short", text(with_dies(P_F, [(3000, 5000, 0)])), "rejected", [C("die_count", count=1)]),
        intake("dies out of order", text(changed(P_F, dies=[{**TEST_LAYOUT[1], "die": 1}, {**TEST_LAYOUT[0],
                                                                                           "die": 0}])),
               "rejected", [C("die_order", dies=[0, 1])]),
        intake("a turned square die", text(with_dies(P_F, [(3000, 5000, 0), (7000, 5000, 90)])), "rejected",
               [C("rotation_not_allowed", dies=[1])]),
        intake("a centre past the frame", text(with_dies(P_F, [(3000, 5000, 0), (10500, 5000, 0)])), "rejected",
               [C("out_of_frame", dies=[1], amount_um=500)]),
        intake("off the lattice", text(with_dies(P_F, [(3250, 5000, 0), (7000, 5000, 0)])), "rejected",
               [C("lattice", dies=[0], amount_um=250)]),
        intake("every geometry rule at once",
               text(changed(with_dies(P_F, [(3100, 5000, 0), (10750, 5000, 90)]), geometry_sha256="0" * 64)),
               "rejected", [C("out_of_frame", dies=[1], amount_um=750), C("rotation_not_allowed", dies=[1]),
                            C("lattice", dies=[0], amount_um=100), C("lattice", dies=[1], amount_um=250),
                            C("geometry_hash_mismatch")]),
        intake("a sealed envelope, not opened at intake", sealed_note("F"), "sealed_unopened"),
        intake("a sealed envelope for a key version the manifest does not hold", sealed_note("F", key_version=2),
               "rejected", [C("sealed_key_version")]),
        intake("a sealed envelope that is not age v1", sealed_note("F", age_file=b"age-encryption.org/v2\n"),
               "rejected", [C("sealed_format")]),
        intake("a sealed envelope with a plaintext fallback field",
               sealed_note("F", extra={"proposal": "plaintext"}), "rejected", [C("unknown_field", path="")]),
        intake("a sealed envelope to a manifest without a recipient", sealed_note("A"), "rejected",
               [C("sealed_key_version"), C("not_open_yet")], manifest="A", admission="open"),
        check("the Ascend snap0p5 copy, checked", text(P_A), "contract_valid"),
        check("the Ascend snap0p5 copy, fenced", fenced(P_A), "contract_valid"),
        check("die 0 moved 250 um off the lattice",
              text(with_dies(P_A, [(17250, 22500, 90)] + [(d["x_um"], d["y_um"], d["rot_deg"])
                                                          for d in ASCEND_SNAP0P5[1:]])),
              "rejected", [C("lattice", dies=[0], amount_um=250)]),
        check("chat is malformed at the check", b"what is the best layout?", "rejected", [C("malformed_json")]),
        check("4097 bytes at the check", padded(P_A, 4097), "rejected", [C("oversize", size_bytes=4097)]),
        check("a draft manifest is checked: admission is the intake's", text(P_A), "contract_valid"),
        check("a proposal for another manifest than m", text(P_F), "rejected",
              [C("manifest_mismatch", path="/manifest_id")]),
    ]
    return cases




def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def non_canonical(raw: bytes) -> str:
    """A base64url text of raw whose final character sets a padding bit: it decodes, but is not canonical."""
    while len(raw) % 3 != 1:
        raw += b" "
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    encoded = b64url(raw)
    return encoded[:-1] + alphabet[alphabet.index(encoded[-1]) | 1]


def needs_padding(raw: bytes) -> bytes:
    while len(raw) % 3 == 0:
        raw += b" "
    return raw


def check_requests() -> list:
    p = b64url(text(P_A))
    return [
        {"name": "a valid request", "request": {"m": ID["A"], "p": p},
         "expect": {"outcome": "contract_valid", "codes": []}},
        {"name": "an unknown m", "request": {"m": "2" * 64, "p": p},
         "expect": {"outcome": "rejected", "codes": [C("unknown_manifest")]}},
        {"name": "padding characters",
         "request": {"m": ID["A"], "p": base64.urlsafe_b64encode(needs_padding(text(P_A))).decode()},
         "expect": {"outcome": "refused", "codes": [C("schema_invalid", path="/p", keyword="pattern")]}},
        {"name": "non-canonical trailing bits", "request": {"m": ID["A"], "p": non_canonical(text(P_A))},
         "expect": {"outcome": "refused", "codes": [C("schema_invalid", path="/p", keyword="contentEncoding")]}},
        {"name": "standard base64 characters", "request": {"m": ID["A"], "p": p + "+/"},
         "expect": {"outcome": "refused", "codes": [C("schema_invalid", path="/p", keyword="pattern")]}},
        {"name": "an extra parameter", "request": {"m": ID["A"], "p": p, "grid": "128"},
         "expect": {"outcome": "refused", "codes": [C("unknown_field", path="")]}},
    ]


# ── records ─────────────────────────────────────────────────────────────────────────────────────────────────────

LIMITS = {
    "schema": "sentilab-open-limits/1", "version": 1, "status": "provisional",
    "requests": {"submissions_per_account_per_hour": None, "checks_per_account_per_hour": 30,
                 "checks_per_room_per_hour": 600, "checks_per_ip_per_hour": None},
    "evaluations": {"per_account_per_hour": 3, "per_account_per_day": 12, "per_room_per_hour": 20,
                    "per_room_per_day": 120},
    "calls": {"policy_per_hour": 40},
    "queue": {"max_waiting": 30, "max_waiting_per_account": None},
    "check": {"solver_elapsed_limit_s": 2, "wall_deadline_s": 5, "wall_clock_start": "on_admission",
              "queue_time_counted": False, "timeout_counts": True, "sponsored": True, "no_participant_charge": True},
    "cpu": {"evaluation_call": {"reservation_s": None, "enforcement_s": None, "cleanup_headroom_s": None},
            "check": {"reservation_s": None, "enforcement_s": None, "cleanup_headroom_s": None}, "debit": None},
    "moderation": {"flags_per_day_to_pause": 3, "pause_hours": 24}}

PREF_HUMAN = h.participant_ref(PSEUDONYM_KEY, F["challenge"], HUMAN)
PREF_AGENT = h.participant_ref(PSEUDONYM_KEY, F["challenge"], AGENT_ACCOUNT)
NOTE_F = text(P_F)
NOTE_SEALED = sealed_note("F")
LABELS = ["geometry only", "no thermal solve", "not a score"]
DELETE = object()


def rec(kind, name, record, expect=(), *, manifest=None, limits=False, pseudonym=False, audience="public"):
    return {"kind": kind, "name": name,
            "context": {"manifest": manifest, "limits": limits, "pseudonym": pseudonym, "audience": audience},
            "record": record, "expect": list(expect)}


def edit(value, path, new):
    """A deep copy with one value replaced; path is a list of keys and indices. new=DELETE removes the key."""
    result = copy.deepcopy(value)
    target = result
    for part in path[:-1]:
        target = target[part]
    if new is DELETE:
        del target[path[-1]]
    else:
        target[path[-1]] = new
    return result


def R(rule, path):
    code = {"label": "label_mismatch", "ref": "ref_mismatch"}.get(rule.split(".")[0], "record_inconsistent")
    return C(code, path=path, rule=rule)


def S(path, keyword):
    return C("schema_invalid", path=path, keyword=keyword)


def manifest_records() -> list:
    f = F
    out = [rec("manifest", "Ascend 910 draft v0 (provisional)", A),
           rec("manifest", "CPU-DRAM draft v0 (provisional)", M),
           rec("manifest", "two-die illustrative fixture, frozen", f)]
    paper_capability = edit(edit(f, ["reference", "paper", "evaluator"], FAKE_CAPABILITY),
                            ["reference", "paper", "label"], "unvalidated")
    snap_off_lattice = edit(edit(f, ["reference", "engineering_variant", "grid_um"], 750),
                            ["reference", "engineering_variant", "id"], "test-two-die-ref-snap0p75")
    bad = [
        ("a note field", edit(f, ["note"], "please read"), [C("unknown_field", path="")]),
        ("die indices out of order", edit(f, ["dies", 1, "die"], 0), [R("manifest.die_index", "/dies/1")]),
        ("a square die with two orientations", edit(f, ["dies", 1, "rot_deg"], [0, 90]),
         [R("manifest.square_rotation", "/dies/1/rot_deg")]),
        ("a turnable die with one orientation", edit(f, ["dies", 0, "rot_deg"], [0]),
         [R("manifest.square_rotation", "/dies/0/rot_deg")]),
        ("a netlist that is not square", edit(f, ["netlist"], [[0, 4]]), [R("manifest.netlist", "/netlist")]),
        ("a netlist with a self-connection", edit(f, ["netlist"], [[1, 4], [4, 0]]),
         [R("manifest.netlist", "/netlist")]),
        ("no strict track", edit(f, ["wire_tracks"], [{"id": "relaxed", "factor": 1.05}]),
         [R("manifest.tracks", "/wire_tracks")]),
        ("the strict track twice", edit(f, ["wire_tracks"], [{"id": "strict", "factor": 1}] * 2),
         [R("manifest.tracks", "/wire_tracks")]),
        ("a strict track with extra wire", edit(f, ["wire_tracks", 0, "factor"], 1.05),
         [S("/wire_tracks/0/factor", "const")]),
        ("a relaxed track with no extra wire",
         edit(f, ["wire_tracks"], [{"id": "strict", "factor": 1}, {"id": "relaxed", "factor": 1}]),
         [S("/wire_tracks/1/factor", "exclusiveMinimum")]),
        ("frozen with provisional thresholds", edit(f, ["thresholds", "status"], "provisional"),
         [R("manifest.frozen_pins", "/thresholds/status")]),
        ("frozen with an unfilled router pin", edit(f, ["wire", "router_sha256"], None),
         [R("manifest.frozen_pins", "/wire/router_sha256")]),
        ("frozen without a sealing recipient", edit(f, ["sealing", "recipient"], None),
         [R("manifest.frozen_pins", "/sealing/recipient")]),
        ("frozen without the variant's design hash",
         edit(f, ["reference", "engineering_variant", "design_hash"], None),
         [R("manifest.frozen_pins", "/reference/engineering_variant/design_hash")]),
        ("a reference temperature with the wrong label", edit(f, ["reference", "t_ref", "label"], "unvalidated"),
         [R("label.single", "/reference/t_ref")]),
        ("an accepted label while nothing is accepted", edit(A, ["reference", "w_ref", "label"], "accepted"),
         [R("label.single", "/reference/w_ref")]),
        ("a reference measured by another evaluator",
         edit(f, ["reference", "t_ref"], temperature(60.0, "HotSpot-6.0:" + HOTSPOT6, "unvalidated")),
         [R("manifest.same_evaluator", "/reference/t_ref")]),
        ("a withdrawn evaluator labelled unvalidated",
         edit(f, ["reference", "t_ref"], temperature(60.0, WITHDRAWN, "unvalidated")),
         [R("label.single", "/reference/t_ref"), R("manifest.same_evaluator", "/reference/t_ref")]),
        ("a variant id that does not bind its snap",
         edit(f, ["reference", "engineering_variant", "id"], "test-two-die-ref-snapped"),
         [R("manifest.variant", "/reference/engineering_variant")]),
        ("a variant snapped off the lattice", snap_off_lattice,
         [R("manifest.variant", "/reference/engineering_variant")]),
        ("a paper target without a label", edit(f, ["reference", "paper", "label"], DELETE),
         [S("/reference/paper/label", "required")]),
        ("an example temperature without an evaluator", edit(f, ["example", "temperature", "evaluator"], DELETE),
         [S("/example/temperature/evaluator", "required")]),
        ("a raw reference on a lattice", edit(f, ["reference", "coordinate_model"], "lattice"),
         [S("/reference/coordinate_model", "const")]),
        ("terms that permit training", edit(f, ["terms", "training"], True), [S("/terms/training", "const")]),
        ("another age format", edit(f, ["sealing", "format"], "age-encryption.org/v2"),
         [S("/sealing/format", "const")]),
        ("a free-text diagnostic", edit(f, ["temperature", "diagnostic"], "chip-layer grid peak"),
         [C("unknown_field", path="/temperature")]),
        ("a capability-shaped evaluator identity", paper_capability, [R("privacy.capability", "")]),
    ]
    out += [rec("manifest", name, record, expect) for name, record, expect in bad]
    return out


def check_records() -> list:
    def response(**edits):
        value = {"schema": "sentilab-open-check/1", "manifest_id": ID["F"],
                 "geometry_sha256": P_F["geometry_sha256"], "proposal_sha256": h.proposal_sha256(P_F),
                 "legal": True, "violations": [], "wire": wire(99.0, FIXTURE, "illustrative", proxy=4.0),
                 "fits_tracks": ["strict"], "no_participant_charge": True, "sealed": False, "labels": LABELS}
        value.update(edits)
        return value
    lattice = [C("lattice", dies=[0], amount_um=250)]
    illegal = response(legal=False, violations=lattice,
                       wire=wire(None, FIXTURE, "illustrative", proxy=4.1, status="skipped_illegal"), fits_tracks=[])
    good = [("legal, with routed wire inside the strict track", response()),
            ("legal at exactly W_ref: strict is inclusive",
             response(wire=wire(100.0, FIXTURE, "illustrative", proxy=4.0))),
            ("illegal: never routed", illegal),
            ("the router hit its time limit",
             response(wire=wire(None, FIXTURE, "illustrative", proxy=4.0), fits_tracks=[])),
            ("a sealed check, answered privately", response(sealed=True))]
    out = [rec("check", name, value, manifest="F", limits=True) for name, value in good]
    bad = [
        ("legal with a violation", response(violations=lattice), [R("check.legal", "/legal")]),
        ("illegal but not marked skipped", response(legal=False, violations=lattice,
                                                    wire=wire(None, FIXTURE, "illustrative", proxy=4.1),
                                                    fits_tracks=[]),
         [R("check.routed", "/wire/routed_status")]),
        ("legal but marked skipped",
         response(wire=wire(None, FIXTURE, "illustrative", status="skipped_illegal"), fits_tracks=[]),
         [R("check.routed", "/wire/routed_status")]),
        ("a track the wire fits, left out", response(fits_tracks=[]), [R("check.fits_tracks", "/fits_tracks")]),
        ("a track the wire misses, claimed", response(wire=wire(100.5, FIXTURE, "illustrative")),
         [R("check.fits_tracks", "/fits_tracks")]),
        ("a response for another manifest", response(manifest_id=ID["A"]), [R("record.manifest", "/manifest_id")]),
        ("no charge claimed while the limits say otherwise", response(no_participant_charge=False),
         [R("check.charge", "/no_participant_charge")]),
        ("wire labelled against its evaluator", response(wire=wire(99.0, FIXTURE, "unvalidated")),
         [R("label.single", "/wire")]),
        ("other labels", response(labels=["geometry only"]), [S("/labels", "const")]),
        ("a score", {**response(), "score": 1}, [C("unknown_field", path="")]),
        ("a violation with a field its code does not carry",
         response(legal=False, violations=[C("lattice", dies=[0], amount_um=250, path="/dies/0")],
                  wire=wire(None, FIXTURE, "illustrative", status="skipped_illegal"), fits_tracks=[]),
         [R("violation.fields", "/violations/0")]),
    ]
    out += [rec("check", name, value, expect, manifest="F", limits=True) for name, value, expect in bad]
    return out


def receipt(**edits):
    value = {"schema": "sentilab-open-receipt/1", "participant_ref": PREF_HUMAN,
             "source_ref": h.source_ref(ACTIONS[0]), "body_sha256": h.body_sha256(NOTE_F), "manifest_id": ID["F"],
             "proposal_sha256": h.proposal_sha256(P_F), "geometry_sha256": P_F["geometry_sha256"],
             "design_hash": None, "problem": "test-two-die", "reference_id": "test-two-die-ref",
             "wire_track": "strict", "proposal_key": "t-1", "parent": None, "terms": "sentilab-open-terms/1",
             "revision_index": 1, "state": "queued", "codes": [], "values": h.conductor_geometry(P_F, F),
             "sealed": False, "ciphertext_ref": None}
    value.update(edits)
    return value


NULL_PROPOSAL = {"proposal_sha256": None, "geometry_sha256": None, "problem": None, "reference_id": None,
                 "wire_track": None, "proposal_key": None, "terms": None, "values": None}


def receipt_records() -> list:
    rejected_json = receipt(state="rejected", codes=[C("malformed_json")], **NULL_PROPOSAL)
    off_lattice = with_dies(P_F, [(3250, 5000, 0), (7000, 5000, 0)])
    rejected_geometry = receipt(state="rejected", codes=[C("lattice", dies=[0], amount_um=250)],
                                proposal_sha256=h.proposal_sha256(off_lattice),
                                geometry_sha256=off_lattice["geometry_sha256"],
                                values=h.conductor_geometry(off_lattice, F))
    sealed = receipt(sealed=True, ciphertext_ref=h.ciphertext_ref(AGE_HEADER_ONLY))
    good = [("queued, from an outside account", receipt()),
            ("rejected before the schema: nothing echoed", rejected_json),
            ("rejected for the lattice, geometry kept", rejected_geometry),
            ("evaluated with no routed wire",
             receipt(state="evaluated", codes=[C("router_timeout")], design_hash=fake("design"))),
            ("failed with one failure code", receipt(state="failed", codes=[C("interrupted")])),
            ("cancelled when the participant was removed",
             receipt(state="cancelled", codes=[C("participant_removed")])),
            ("withdrawn", receipt(state="withdrawn"))]
    out = [rec("receipt", name, value, manifest="F") for name, value in good]
    out.append(rec("receipt", "a sealed receipt, served privately", sealed, manifest="F", audience="private"))
    unparsed_with_fields = receipt(state="rejected", codes=[C("malformed_json")], proposal_sha256=None,
                                   geometry_sha256=None, values=None)
    bad = [
        ("an account id is never public", {**receipt(), "actor_user_id": HUMAN}, [C("unknown_field", path="")]),
        ("rejected without a code", receipt(state="rejected", codes=[], **NULL_PROPOSAL),
         [R("state.codes", "/codes")]),
        ("queued with a code", receipt(codes=[C("lattice", dies=[0], amount_um=250)]), [R("state.codes", "/codes")]),
        ("failed with two codes", receipt(state="failed", codes=[C("timeout"), C("stopped")]),
         [R("state.codes", "/codes")]),
        ("not reproduced with a verification code",
         receipt(state="not_reproduced", codes=[C("verification_failed")]), [R("state.codes", "/codes")]),
        ("proposal fields without a proposal hash", unparsed_with_fields,
         [R("receipt.proposal_fields", "/" + name)
          for name in ("problem", "proposal_key", "reference_id", "terms", "wire_track")]),
        ("queued without its geometry", receipt(values=None), [R("receipt.proposal_fields", "/values")]),
        ("a sealed receipt published", sealed, [R("privacy.sealed", "/sealed")]),
        ("a code without its required field", receipt(state="rejected", codes=[C("queue_full")]),
         [R("violation.fields", "/codes/0")]),
        ("a code with a field it does not carry",
         receipt(state="rejected", codes=[C("lattice", dies=[0], amount_um=250, path="/dies")]),
         [R("violation.fields", "/codes/0")]),
        ("a receipt for another manifest", receipt(manifest_id=ID["A"]), [R("record.manifest", "/manifest_id")]),
    ]
    out += [rec("receipt", name, value, expect, manifest="F") for name, value, expect in bad]
    out.append(rec("receipt", "sealed without a ciphertext reference", receipt(sealed=True),
                   [R("receipt.sealed", "/ciphertext_ref")], manifest="F", audience="private"))
    return out


def restricted(**edits):
    value = {"schema": "sentilab-open-restricted-receipt/1", "participant_ref": PREF_HUMAN, "actor_user_id": HUMAN,
             "actor_kind": "human", "actor_agent_id": None, "intake": INTAKE, "room": ROOM, "action_id": ACTIONS[0],
             "created_at": "2026-11-01T10:00:00.123456+00:00", "target_sequence": 4242, "message_revision": 1,
             "source_ref": h.source_ref(ACTIONS[0]), "body_sha256": h.body_sha256(NOTE_F), "manifest_id": ID["F"],
             "proposal_key": "t-1", "proposal_sha256": h.proposal_sha256(P_F), "transport_id": "", "sealed": False,
             "capability_sha256": None, "capability_epoch": None, "capability_revoked": False}
    value.update(edits)
    if value["transport_id"] == "":
        value["transport_id"] = h.transport_id(
            room=value["room"], account_id=value["actor_user_id"], actor_kind=value["actor_kind"],
            actor_agent_id=value["actor_agent_id"], manifest_id=value["manifest_id"],
            proposal_key=value["proposal_key"], proposal_sha256=value["proposal_sha256"])
    return value


def restricted_records() -> list:
    agent = restricted(participant_ref=PREF_AGENT, actor_user_id=AGENT_ACCOUNT, actor_kind="agent",
                       actor_agent_id="example-agent", action_id=ACTIONS[1], source_ref=h.source_ref(ACTIONS[1]),
                       room=OVERFLOW_ROOM, created_at="2026-11-01T10:00:01Z")
    sealed_sha = h.proposal_sha256(P_SEALED)
    sealed = restricted(action_id=ACTIONS[2], source_ref=h.source_ref(ACTIONS[2]),
                        body_sha256=h.body_sha256(NOTE_SEALED), proposal_key="t-2", proposal_sha256=sealed_sha,
                        sealed=True, capability_sha256=h.capability_sha256(h.capability(SALT, ID["F"], sealed_sha)),
                        capability_epoch=1)
    rotated = {**sealed, "capability_epoch": 2,
               "capability_sha256": h.capability_sha256(h.capability(SALT, ID["F"], sealed_sha, 2))}
    unparsed = restricted(proposal_key=None, proposal_sha256=None, transport_id=None)
    good = (("an outside (non-staff) human, REST with an account token", restricted()),
            ("an outside (non-staff) account's admitted agent, MCP", agent),
            ("a sealed submission: capability hash only", sealed),
            ("a rotated capability, epoch 2", rotated),
            ("a revoked capability", {**rotated, "capability_revoked": True}),
            ("a reply that never parsed", unparsed))
    out = [rec("restricted_receipt", name, value, manifest="F", pseudonym=True) for name, value in good]
    other_ref = h.participant_ref(PSEUDONYM_KEY, "sentilab-open-1", HUMAN)
    other_content = h.transport_id(room=ROOM, account_id=HUMAN, actor_kind="human", actor_agent_id=None,
                                   manifest_id=ID["F"], proposal_key="t-1", proposal_sha256=h.proposal_sha256(P_SEALED))
    other_slot = h.transport_id(room=ROOM, account_id=HUMAN, actor_kind="agent", actor_agent_id="example-agent",
                                manifest_id=ID["F"], proposal_key="t-1", proposal_sha256=h.proposal_sha256(P_F))
    bad = [
        ("a source ref for another action", restricted(source_ref=h.source_ref(ACTIONS[3])),
         [R("ref.source", "/source_ref")]),
        ("a pseudonym from another challenge", restricted(participant_ref=other_ref),
         [R("ref.participant", "/participant_ref")]),
        ("the reserved principal from an account", restricted(participant_ref="sentilab"),
         [R("ref.participant", "/participant_ref")]),
        ("a transport id for other content", restricted(transport_id=other_content),
         [R("ref.transport", "/transport_id")]),
        ("a transport id for another actor slot", restricted(transport_id=other_slot),
         [R("ref.transport", "/transport_id")]),
        ("no transport id for a parsed proposal", restricted(transport_id=None),
         [R("ref.transport", "/transport_id")]),
        ("a human with an agent id", restricted(actor_agent_id="example-agent", transport_id=None),
         [S("/actor_agent_id", "type")]),
        ("an agent without an agent id", restricted(actor_kind="agent", transport_id=None),
         [S("/actor_agent_id", "type")]),
        ("a label is never authority", {**restricted(), "actor_label": "human-example"},
         [C("unknown_field", path="")]),
        ("sealed without a capability hash", restricted(sealed=True), [R("receipt.sealed", "/capability_sha256")]),
        ("sealed without a capability epoch", {**sealed, "capability_epoch": None},
         [R("receipt.sealed", "/capability_sha256")]),
        ("a revocation on a public submission", restricted(capability_revoked=True),
         [R("receipt.sealed", "/capability_sha256")]),
        ("a capability in place of its hash", {**restricted(), "capability": FAKE_CAPABILITY},
         [C("unknown_field", path="")]),
    ]
    out += [rec("restricted_receipt", name, value, expect, manifest="F", pseudonym=True)
            for name, value, expect in bad]
    return out


def status_receipt(**edits):
    value = {"participant_ref": PREF_HUMAN, "team_name": None, "state": "queued", "codes": [],
             "queue": {"position": 2, "estimated_start": "2026-11-01T10:05:00Z"}, "hidden": False,
             "hidden_reason": None, "receipt_hash": fake("receipt 1"), "run_id": h.run_id(ID["F"], PREF_HUMAN),
             "seq": 7, "sealed": False}
    value.update(edits)
    return value


def status(*receipts):
    return {"schema": "sentilab-open-status/1", "manifest_id": ID["F"], "proposal_sha256": h.proposal_sha256(P_F),
            "receipts": list(receipts)}


def status_records() -> list:
    spam = status_receipt(state="rejected", codes=[C("malformed_json")], queue=None, hidden=True,
                          hidden_reason="spam")
    agent = status_receipt(participant_ref=PREF_AGENT, run_id=h.run_id(ID["F"], PREF_AGENT), team_name="Team A-7",
                           state="reproduced", queue=None, receipt_hash=fake("receipt 2"), seq=9)
    good = [("queued, with its place in the queue", status(status_receipt())),
            ("hidden as spam, with its reason", status(spam)),
            ("two principals, one with a moderated team name", status(status_receipt(), agent)),
            ("withdrawn", status(status_receipt(state="withdrawn", queue=None)))]
    out = [rec("status", name, value, manifest="F") for name, value in good]
    wrong_codes = status_receipt(state="failed", queue=None, codes=[C("lattice", dies=[0], amount_um=250)])
    bad = [
        ("hidden without a reason", status(status_receipt(hidden=True)), [S("/receipts/0/hidden_reason", "type")]),
        ("a reason while visible", status(status_receipt(hidden_reason="spam")),
         [S("/receipts/0/hidden_reason", "type")]),
        ("a queue place once evaluated", status(status_receipt(state="evaluated")),
         [S("/receipts/0/queue", "type")]),
        ("queued without a place", status(status_receipt(queue=None)), [S("/receipts/0/queue", "type")]),
        ("a run of another manifest", status(status_receipt(run_id=h.run_id(ID["A"], PREF_HUMAN))),
         [R("ref.run_id", "/receipts/0/run_id")]),
        ("codes that do not fit the state", status(wrong_codes), [R("state.codes", "/receipts/0/codes")]),
        ("a sealed entry published", status(status_receipt(sealed=True)),
         [R("privacy.sealed", "/receipts/0/sealed")]),
        ("an account id is never public", status({**status_receipt(), "actor_user_id": HUMAN}),
         [C("unknown_field", path="/receipts/0")]),
        ("markup in a team name", status(status_receipt(team_name="<b>Team</b>")),
         [S("/receipts/0/team_name", "pattern")]),
    ]
    out += [rec("status", name, value, expect, manifest="F") for name, value, expect in bad]
    return out


def row(kind, **edits):
    value = {"kind": kind, "id": None, "participant_ref": None, "team_name": None, "proposal_sha256": None,
             "geometry_sha256": None, "receipt_hash": None, "legal": None, "state": None, "hidden": False,
             "hidden_reason": None, "sealed": False, "temperature": None, "wire": None, "paper": None,
             "comparison": None, "sensitivity": [], "claims": [], "diagnostics": [], "control": None}
    value.update(edits)
    return value


def claim(kind, outcome, *, r=None, evaluators=(FIXTURE,), label="illustrative", suppressed_by=None):
    return {"type": kind, "r": r, "outcome": outcome, "suppressed_by": suppressed_by, "evaluators": list(evaluators),
            "label": label}


def observed(case, value, status_="observed"):
    return {"case": case, "status": status_, "T_M_c": value if status_ == "observed" else None, "evaluator": FIXTURE,
            "label": "illustrative"}


SENSITIVITY = [observed("replay", 59.61), observed("grid32", 59.9), observed("pos-a-x", 59.7)]
FAILED_GRID = [SENSITIVITY[0], observed("grid32", None, "failed"), SENSITIVITY[2]]
COMPARISON = {"delta_T_k": -0.4, "q": [{"r": 0, "q_mm": -1.0}], "evaluators": [FIXTURE], "label": "illustrative"}
DIAGNOSTIC = {"id": "grid-peak-offset", "values": [{"name": "grid_peak_minus_t_m", "value": 0.4, "unit": "k"}],
              "evaluator": FIXTURE, "label": "illustrative"}
PASSES = "passes_listed_cases"
HIGH_WIRE = {"id": "wire-above-relaxed-budget", "values": [{"name": "q_relaxed_mm", "value": 812.5, "unit": "mm"}],
             "evaluator": "tap-router:" + ROUTER_SHA256, "label": "unvalidated"}


def outside(**edits):
    value = row("outside", participant_ref=PREF_HUMAN, proposal_sha256=h.proposal_sha256(P_F),
                geometry_sha256=P_F["geometry_sha256"], receipt_hash=fake("receipt 1"), legal=True,
                state="reproduced",
                temperature=temperature(59.6, FIXTURE, "illustrative", peak=60.0, argmax={"row": 20, "col": 12},
                                        selector=59.7),
                wire=wire(99.0, FIXTURE, "illustrative", proxy=4.0), comparison=COMPARISON,
                sensitivity=SENSITIVITY,
                claims=[claim("strict_wire_thermal_tolerance", PASSES), claim("nondominated", "unknown")],
                diagnostics=[DIAGNOSTIC])
    value.update(edits)
    return value


def control_row(**edits):
    value = row("control", id="test-control", legal=False,
                temperature=temperature(60.0, FIXTURE, "illustrative"), wire=wire(100.0, FIXTURE, "illustrative"),
                sensitivity=SENSITIVITY, claims=[claim("strict_wire_thermal_tolerance", PASSES)],
                control={"id": "test-control", "result": "control_match"})
    value.update(edits)
    return value


def results(*rows_, manifest_key="F", status_="frozen"):
    return {"schema": "sentilab-open-results/1", "manifest_id": ID[manifest_key], "manifest_status": status_,
            "rows": list(rows_)}


def results_records() -> list:
    ref_f = row("reference-raw", id="test-two-die-ref", legal=False, temperature=F["reference"]["t_ref"],
                wire=F["reference"]["w_ref"])
    draft = results(row("reference-raw", id="ascend910-tap25d-fig6a", legal=False, wire=A["reference"]["w_ref"]),
                    row("paper", paper=A["reference"]["paper"]),
                    row("reference-variant", id="ascend910-tap25d-fig6a-snap0p5", legal=True,
                        geometry_sha256=A["reference"]["engineering_variant"]["geometry_sha256"]),
                    row("outside", participant_ref=PREF_HUMAN, proposal_sha256=h.proposal_sha256(P_A),
                        geometry_sha256=P_A["geometry_sha256"], receipt_hash=fake("receipt 3"), legal=True,
                        state="queued"),
                    manifest_key="A", status_="draft")
    suppressed = outside(sensitivity=FAILED_GRID, claims=[claim("strict_wire_thermal_tolerance", "suppressed",
                                                                suppressed_by="scenario_failed")])
    incomplete_control = control_row(claims=[], control={"id": "test-control", "result": "incomplete"})
    good = [("a draft manifest: measurements only, nothing scored", draft, "A"),
            ("a frozen illustrative fixture: scored rows, claims and a control",
             results(ref_f, outside(), control_row()), "F"),
            ("a failed required case suppresses the claim", results(suppressed), "F"),
            ("a control with its claim missing is incomplete", results(incomplete_control), "F"),
            ("a hidden row keeps its reason", results(outside(hidden=True, hidden_reason="not_a_layout")), "F"),
            ("a high-wire diagnostic beside the temperature's own label", results(outside(diagnostics=[HIGH_WIRE])),
             "F")]
    out = [rec("results", name, value, manifest=key) for name, value, key in good]
    out.append(rec("results", "a sealed row, served privately", results(outside(sealed=True)), manifest="F",
                   audience="private"))
    hotspot6 = "HotSpot-6.0:" + HOTSPOT6
    bad = [
        ("a claim under a draft manifest",
         results(outside(comparison=None, claims=[claim("nondominated", "unknown")]), status_="draft"),
         [S("/rows/0/claims", "maxItems")], "F"),
        ("scoring against a manifest that is not frozen",
         results(outside(proposal_sha256=h.proposal_sha256(P_A)), manifest_key="A", status_="frozen"),
         [R("record.manifest", "/manifest_status"), C("manifest_not_frozen", path="/rows/0")], "A"),
        ("a decided claim labelled against its inputs",
         results(outside(claims=[claim("strict_wire_thermal_tolerance", PASSES, label="unvalidated")])),
         [R("label.claim_outcome", "/rows/0/claims/0"), R("label.derived", "/rows/0/claims/0")], "F"),
        ("an unvalidated claim decided",
         results(outside(claims=[claim("strict_wire_thermal_tolerance", PASSES, evaluators=[hotspot6],
                                       label="unvalidated")])),
         [R("label.claim_outcome", "/rows/0/claims/0")], "F"),
        ("a withdrawn temperature in a comparison",
         results(outside(temperature=temperature(59.6, WITHDRAWN, "withdrawn"))),
         [R("label.withdrawn_comparison", "/rows/0"), R("results.same_evaluator", "/rows/0")], "F"),
        ("a scored row routed by another router",
         results(outside(wire=wire(99.0, "tap-router:" + ROUTER_SHA256, "unvalidated", proxy=4.0))),
         [R("results.same_evaluator", "/rows/0")], "F"),
        ("a high-wire diagnostic replacing the temperature's label",
         results(outside(temperature=temperature(59.6, FIXTURE, "unvalidated"), diagnostics=[HIGH_WIRE])),
         [R("label.single", "/rows/0/temperature")], "F"),
        ("a scored row from another evaluator",
         results(outside(temperature=temperature(59.6, hotspot6, "unvalidated"))),
         [R("results.same_evaluator", "/rows/0")], "F"),
        ("a missing case cannot pass", results(outside(sensitivity=SENSITIVITY[:2])),
         [R("claim.cases", "/rows/0/claims/0")], "F"),
        ("a failed case cannot pass", results(outside(sensitivity=FAILED_GRID)),
         [R("claim.cases", "/rows/0/claims/0")], "F"),
        ("a failed case does not leave a claim incomplete",
         results(outside(sensitivity=FAILED_GRID, claims=[claim("strict_wire_thermal_tolerance", "incomplete")])),
         [R("claim.cases", "/rows/0/claims/0")], "F"),
        ("a case outside the predeclared list",
         results(outside(sensitivity=SENSITIVITY + [observed("pos-b-y", 59.8)])),
         [R("claim.cases", "/rows/0/sensitivity")], "F"),
        ("a control reported as a mismatch while its claims match",
         results(control_row(control={"id": "test-control", "result": "control_mismatch"})),
         [R("control.result", "/rows/0/control")], "F"),
        ("a control whose claim failed, reported as a match",
         results(control_row(claims=[claim("strict_wire_thermal_tolerance", "fails_listed_cases")])),
         [R("control.result", "/rows/0/control")], "F"),
        ("a control the manifest does not list",
         results(control_row(id="other-control", control={"id": "other-control", "result": "control_match"})),
         [R("control.result", "/rows/0/control")], "F"),
        ("suppressed without a reason code",
         results(outside(claims=[claim("strict_wire_thermal_tolerance", "suppressed")])),
         [S("/rows/0/claims/0/suppressed_by", "type")], "F"),
        ("a reason code on a claim that was not suppressed",
         results(outside(claims=[claim("strict_wire_thermal_tolerance", PASSES, suppressed_by="gate_failed")])),
         [S("/rows/0/claims/0/suppressed_by", "type")], "F"),
        ("a diagnostic labelled against its evaluator",
         results(outside(diagnostics=[{**DIAGNOSTIC, "label": "accepted"}])),
         [R("label.single", "/rows/0/diagnostics/0")], "F"),
        ("a comparison labelled against its inputs", results(outside(comparison={**COMPARISON,
                                                                                "label": "unvalidated"})),
         [R("label.derived", "/rows/0/comparison")], "F"),
        ("a relaxed claim without its r",
         results(outside(claims=[claim("relaxed_wire_thermal_tolerance", "unknown")])),
         [S("/rows/0/claims/0/r", "type")], "F"),
        ("an outside row under the reserved principal", results(outside(participant_ref="sentilab")),
         [S("/rows/0/participant_ref", "pattern")], "F"),
        ("the SentiLab row with a team name",
         results(row("sentilab", participant_ref="sentilab", team_name="SentiLab", proposal_sha256=fake("p"),
                     receipt_hash=fake("r"), state="queued")),
         [S("/rows/0/team_name", "type")], "F"),
        ("a paper row with a measured temperature",
         results(row("paper", paper=A["reference"]["paper"], temperature=F["reference"]["t_ref"])),
         [S("/rows/0/temperature", "type")], "F"),
        ("a sealed row published", results(outside(sealed=True)), [R("privacy.sealed", "/rows/0/sealed")], "F"),
        ("an account id is never public", results({**outside(), "actor_user_id": HUMAN}),
         [C("unknown_field", path="/rows/0")], "F"),
        ("a capability-shaped identity",
         results(outside(wire=wire(99.0, FAKE_CAPABILITY, "unvalidated"), comparison=None, claims=[])),
         [R("privacy.capability", "")], "F"),
    ]
    out += [rec("results", name, value, expect, manifest=key) for name, value, expect, key in bad]
    return out


def usage(**edits):
    value = {"schema": "sentilab-open-usage/1", "journal_seq": 31, "suballocation": "evaluate", "payer": "participant",
             "run_id": h.run_id(ID["F"], PREF_HUMAN), "participant_ref": PREF_HUMAN,
             "proposal_sha256": h.proposal_sha256(P_F), "call": 0, "reservation_id": RESERVATIONS[0],
             "reserved_cpu_s": 15, "enforced_cpu_s": 14, "cleanup_headroom_cpu_s": 1, "debited_cpu_s": 4.8,
             "measured_cpu_s": 4.8, "elapsed_s": 4.9, "enforcement": "not_triggered", "overrun": "none",
             "outcome": "settled", "codes": []}
    value.update(edits)
    return value


def error(*codes):
    return {"schema": "sentilab-open-error/1", "codes": list(codes)}


def cursor(after=None, seq=0, journal=None):
    return {"schema": "sentilab-open-cursor/1", "room": ROOM, "after": after, "journal_seq": seq,
            "journal_sha256": journal}


VOCABULARY = json.loads((CONTRACT_DIR / "reason-codes.json").read_bytes())
SEALED_ENVELOPE = json.loads(NOTE_SEALED)


def other_records() -> list:
    current = {"schema": "sentilab-open-current/1", "problem": "test-two-die", "version": 1, "manifest_id": ID["F"],
               "threads": [{"room": ROOM, "root_sequence": 4242}, {"room": OVERFLOW_ROOM, "root_sequence": 5150}]}
    good = [
        ("geometry", "the two-die layout's hash preimage", h.geometry_object(P_F, F), None),
        ("sealed", "envelope shape only: the ciphertext is the bare age v1 header line, not an age file",
         SEALED_ENVELOPE, None),
        ("check_request", "a check request", {"m": ID["A"], "p": b64url(text(P_A))}, None),
        ("error", "queue full, retry after", error(C("queue_full", retry_after="2026-11-01T11:00:00Z")), None),
        ("error", "check rate limited", error(C("check_rate_limited", retry_after="2026-11-01T10:01:00Z")), None),
        ("error", "check timed out", error(C("check_timeout")), None),
        ("error", "evaluations paused for 24 hours", error(C("participant_paused", retry_after="2026-11-02T10:00:00Z")),
         None),
        ("limits", "the provisional operational limits (OP-W1/W3)", LIMITS, None),
        ("usage", "an evaluate call, measured", usage(), None),
        ("usage", "an interrupted call debits its whole reservation",
         usage(call=1, reservation_id=RESERVATIONS[1], measured_cpu_s=None, debited_cpu_s=15, elapsed_s=None,
               overrun="unmeasured", outcome="interrupted", codes=[C("interrupted")]), None),
        ("usage", "stopped in flight by live enforcement", usage(
            call=2, reservation_id=RESERVATIONS[3], measured_cpu_s=14.2, debited_cpu_s=14.2, elapsed_s=14.4,
            enforcement="stopped_in_flight", outcome="failed", codes=[C("timeout")]), None),
        ("usage", "stopped in flight, and cleanup overran: detected at settlement, not prevented", usage(
            call=3, reservation_id=RESERVATIONS[4], measured_cpu_s=15.6, debited_cpu_s=15.6, elapsed_s=15.9,
            enforcement="stopped_in_flight", overrun="detected", outcome="failed", codes=[C("timeout")]), None),
        ("usage", "a sponsored check still spends sponsor CPU",
         usage(suballocation="check", payer="sponsor", run_id=None, participant_ref=None, proposal_sha256=None,
               reservation_id=RESERVATIONS[2], reserved_cpu_s=2.5, enforced_cpu_s=2, cleanup_headroom_cpu_s=0.5,
               debited_cpu_s=0.9, measured_cpu_s=0.9, elapsed_s=1.1), None),
        ("cursor", "a room's cursor before any reply", cursor(), None),
        ("cursor", "after one durably journalled reply",
         cursor({"created_at": "2026-11-01T10:00:00+00:00", "action_id": ACTIONS[0]}, 1, fake("journal 1")), None),
        ("current", "the open version and its threads", current, "F"),
        ("private_request", "a capability addresses one sealed submission", {"cap": FAKE_CAPABILITY}, None),
        ("reason_codes", "the vocabulary itself", VOCABULARY, None),
    ]
    out = [rec(kind, name, value, manifest=key, limits=kind == "limits") for kind, name, value, key in good]
    bad = [
        ("geometry", "a salt in the geometry", {**h.geometry_object(P_F, F), "salt": SALT},
         [C("unknown_field", path="")], None),
        ("sealed", "a plaintext fallback", {**SEALED_ENVELOPE, "proposal": P_F}, [C("unknown_field", path="")], None),
        ("sealed", "a ciphertext that is not base64", {**SEALED_ENVELOPE, "ciphertext": "not base64!"},
         [S("/ciphertext", "pattern")], None),
        ("sealed", "key version 0", {**SEALED_ENVELOPE, "key_version": 0}, [S("/key_version", "minimum")], None),
        ("check_request", "m is not a hash", {"m": "manifest", "p": "e30"}, [S("/m", "pattern")], None),
        ("error", "queue full without a retry_after", error(C("queue_full")), [R("violation.fields", "/codes/0")],
         None),
        ("error", "no code", error(), [S("/codes", "minItems")], None),
        ("error", "a code outside the vocabulary", error(C("try_later")), [S("/codes/0/code", "enum")], None),
        ("error", "free text beside a code", error({"code": "check_timeout", "message": "took too long"}),
         [C("unknown_field", path="/codes/0")], None),
        ("limits", "no participant charge without sponsorship", edit(LIMITS, ["check", "sponsored"], False),
         [R("limits.charge", "/check/no_participant_charge")], None),
        ("limits", "no participant charge without a solver limit",
         edit(LIMITS, ["check", "solver_elapsed_limit_s"], None),
         [R("limits.charge", "/check/no_participant_charge")], None),
        ("limits", "a solver limit past the whole-check deadline",
         edit(LIMITS, ["check", "solver_elapsed_limit_s"], 6),
         [R("limits.windows", "/check/solver_elapsed_limit_s")], None),
        ("limits", "a daily quota under the hourly one", edit(LIMITS, ["evaluations", "per_room_per_day"], 10),
         [R("limits.windows", "/evaluations/per_room_per_day")], None),
        ("limits", "a reservation that is not enforcement plus headroom",
         edit(LIMITS, ["cpu", "evaluation_call"], {"reservation_s": 15, "enforcement_s": 15,
                                                   "cleanup_headroom_s": 1}),
         [R("limits.cpu", "/cpu/evaluation_call")], None),
        ("limits", "a deadline clock that counts the queue", edit(LIMITS, ["check", "queue_time_counted"], True),
         [S("/check/queue_time_counted", "const")], None),
        ("limits", "an owner field beside the limits", {**LIMITS, "owner": "operations"},
         [C("unknown_field", path="")], None),
        ("limits", "a deadline clock started at the request",
         edit(LIMITS, ["check", "wall_clock_start"], "on_request"), [S("/check/wall_clock_start", "const")], None),
        ("usage", "an overrun reported as none", usage(measured_cpu_s=15.6, debited_cpu_s=15.6),
         [R("usage.overrun", "/overrun")], None),
        ("usage", "an overrun claimed without a measurement", usage(measured_cpu_s=None, debited_cpu_s=15,
                                                                   overrun="detected"),
         [R("usage.overrun", "/overrun")], None),
        ("usage", "stopped in flight but recorded as settled", usage(enforcement="stopped_in_flight"),
         [R("usage.enforcement", "/enforcement")], None),
        ("usage", "an unmeasured call debited less than its reservation", usage(measured_cpu_s=None,
                                                                                overrun="unmeasured"),
         [R("usage.charge", "/debited_cpu_s")], None),
        ("usage", "an interrupted call with a measurement", usage(outcome="interrupted", codes=[C("interrupted")]),
         [R("usage.charge", "/debited_cpu_s")], None),
        ("usage", "a reservation that is not enforcement plus headroom", usage(enforced_cpu_s=15),
         [R("usage.charge", "/debited_cpu_s")], None),
        ("usage", "a check debited to a participant", usage(suballocation="check", run_id=None),
         [S("/payer", "const")], None),
        ("usage", "an evaluation outside any run", usage(run_id=None), [S("/run_id", "type")], None),
        ("usage", "another principal's run", usage(run_id=h.run_id(ID["F"], PREF_AGENT)),
         [R("ref.run_id", "/run_id")], None),
        ("cursor", "a start that names a journal entry", cursor(None, 3), [S("/journal_seq", "const")], None),
        ("cursor", "an impossible date",
         cursor({"created_at": "2026-02-30T00:00:00Z", "action_id": ACTIONS[0]}, 1, fake("journal 1")),
         [R("cursor.created_at", "/after/created_at")], None),
        ("current", "a pointer to another manifest", {**current, "manifest_id": ID["A"]},
         [R("record.manifest", "/manifest_id")], "F"),
        ("private_request", "a capability of the wrong shape", {"cap": "opencap1-xyz"}, [S("/cap", "pattern")], None),
        ("reason_codes", "a field beside the vocabulary", {**VOCABULARY, "note": "x"}, [C("unknown_field", path="")],
         None),
    ]
    out += [rec(kind, name, value, expect, manifest=key, limits=kind == "limits")
            for kind, name, value, expect, key in bad]
    return out


# ── the state machine, revisions and submission order ───────────────────────────────────────────────────────────

ALLOWED = {
    "none": {"accept": "queued", "reject": "rejected"},
    "queued": {"hold": "held", "start": "evaluating", "cancel": "cancelled", "expire": "expired"},
    "held": {"release": "queued", "cancel": "cancelled", "expire": "expired"},
    "evaluating": {"complete": "evaluated", "fail": "failed"},
    "evaluated": {"reproduce": "reproducing"},
    "failed": {"requeue": "queued"},
    "reproducing": {"reproduced": "reproduced", "not_reproduced": "not_reproduced"},
    "reproduced": {"verify": "verifying"},
    "verifying": {"verified": "verified", "not_verified": "not_verified"},
    "rejected": {}, "not_reproduced": {}, "verified": {}, "not_verified": {}, "cancelled": {}, "expired": {}}
GOOD_PAYLOAD = {
    "accept": {}, "reject": {"codes": ["lattice"]}, "hold": {"operator": True}, "release": {"operator": True},
    "start": {"reservation_id": RESERVATIONS[0]}, "complete": {"settled": True},
    "fail": {"settled": True, "code": "timeout"}, "requeue": {"operator": True},
    "reproduce": {"reservation_id": RESERVATIONS[1]}, "reproduced": {"settled": True, "fresh_process": True},
    "not_reproduced": {"settled": True, "code": "reproduction_mismatch"},
    "verify": {"reservation_id": RESERVATIONS[2]}, "verified": {"settled": True, "tier": "cross_host"},
    "not_verified": {"settled": True, "code": "verification_failed"}, "cancel": {"codes": ["participant_removed"]},
    "expire": {}, "withdraw": {"operator": True}, "restore": {"operator": True},
    "hide": {"operator": True, "reason": "spam"}, "unhide": {"operator": True, "reason": "reinstated"}}
GUARDS = [
    ("reject", "none", {}), ("reject", "none", {"codes": []}), ("reject", "none", {"codes": ["timeout"]}),
    ("reject", "none", {"codes": ["lattice", "spam"]}),
    ("start", "queued", {}), ("start", "queued", {"reservation_id": "r-1"}),
    ("complete", "evaluating", {}), ("complete", "evaluating", {"settled": False}),
    ("fail", "evaluating", {"settled": True}), ("fail", "evaluating", {"settled": True, "code": "router_timeout"}),
    ("fail", "evaluating", {"code": "timeout"}),
    ("reproduce", "evaluated", {}),
    ("reproduced", "reproducing", {"settled": True}),
    ("reproduced", "reproducing", {"settled": True, "fresh_process": False}),
    ("reproduced", "reproducing", {"fresh_process": True}),
    ("not_reproduced", "reproducing", {"settled": True, "code": "timeout"}),
    ("verify", "reproduced", {}),
    ("verified", "verifying", {"settled": True, "tier": "replayed"}),
    ("verified", "verifying", {"tier": "cross_build"}),
    ("not_verified", "verifying", {"settled": True, "code": "reproduction_mismatch"}),
    ("cancel", "queued", {"codes": ["lattice"]}),
    ("hold", "queued", {}), ("release", "held", {"operator": False}), ("requeue", "failed", {}),
    ("withdraw", "queued", {}), ("restore", "queued", {}),
    ("hide", "queued", {"operator": True, "reason": "reinstated"}),
    ("hide", "queued", {"operator": True}), ("hide", "queued", {"reason": "spam"}),
]


def overlay(name, start, events, expect):
    return {"name": name, "from": start, "events": events,
            "expect": expect if expect == "refused" else dict(zip(("lifecycle", "withdrawn", "hidden"), expect))}


def state_table() -> dict:
    withdraw, restore = ["withdraw", {"operator": True}], ["restore", {"operator": True}]
    hide_spam = ["hide", {"operator": True, "reason": "spam"}]
    reinstate = ["unhide", {"operator": True, "reason": "reinstated"}]
    return {
        "lifecycle": [state for state in ALLOWED if state != "none"], "allowed": ALLOWED,
        "good_payload": GOOD_PAYLOAD,
        "guards": [{"event": event, "from": start, "payload": payload, "expect": "refused"}
                   for event, start, payload in GUARDS],
        "overlays": [
            overlay("withdraw then restore", "evaluated", [withdraw, restore], ("evaluated", False, None)),
            overlay("work in flight still settles while withdrawn", "evaluating",
                    [withdraw, ["complete", {"settled": True}]], ("evaluated", True, None)),
            overlay("no new work starts while withdrawn", "queued",
                    [withdraw, ["start", {"reservation_id": RESERVATIONS[0]}]], "refused"),
            overlay("no requeue while withdrawn", "failed", [withdraw, ["requeue", {"operator": True}]], "refused"),
            overlay("withdraw twice", "queued", [withdraw, withdraw], "refused"),
            overlay("restore without a withdrawal", "queued", [restore], "refused"),
            overlay("hide as spam, then reinstate", "rejected", [hide_spam, reinstate], ("rejected", False, None)),
            overlay("hidden entries keep evaluating", "queued",
                    [["hide", {"operator": True, "reason": "not_a_layout"}],
                     ["start", {"reservation_id": RESERVATIONS[0]}]], ("evaluating", False, "not_a_layout")),
            overlay("hide twice", "queued", [hide_spam, hide_spam], "refused"),
            overlay("unhide what is visible", "queued", [reinstate], "refused"),
            overlay("unhide with a hiding reason", "queued",
                    [hide_spam, ["unhide", {"operator": True, "reason": "spam"}]], "refused"),
            overlay("no overlay before ingest", "none", [withdraw], "refused"),
            overlay("an unknown event", "queued", [["evaluate", {}]], "refused")],
        "summary": {"rejected": "rejected", "queued": "queued", "held": "queued", "evaluating": "queued",
                    "evaluated": "evaluated", "failed": "evaluated", "reproducing": "evaluated",
                    "reproduced": "evaluated", "not_reproduced": "evaluated", "verifying": "evaluated",
                    "not_verified": "evaluated", "verified": "independently_verified", "cancelled": None,
                    "expired": None}}


K = {name: hashlib.sha256(("revision vector " + name).encode()).hexdigest() for name in "abcdefgh"}


def rev(index, key, content, geometry, order):
    return {"index": index, "proposal_key": key, "proposal_sha256": content, "geometry_sha256": geometry,
            "order": order}


def revisions() -> list:
    one = rev(1, "a-1", K["a"], K["b"], [1000, ACTIONS[0], ROOM])
    two = rev(2, "a-1", K["c"], K["d"], [2000, ACTIONS[1], ROOM])
    at = lambda ns, index: [ns, ACTIONS[index], ROOM]
    cases = [
        ("the first submission", [], ["a-1", K["a"], None, at(1000, 0)], ["new", 1, []]),
        ("the same content again: no new record", [one], ["a-1", K["a"], None, at(2000, 1)], ["duplicate", 1, []]),
        ("the same key with changed content: a recorded conflict", [one], ["a-1", K["c"], None, at(2000, 1)],
         ["new", 2, ["revision_conflict"]]),
        ("the conflicting content resent: the same conflict record", [one, two],
         ["a-1", K["c"], None, at(3000, 2)], ["duplicate", 2, []]),
        ("a new key on an earlier geometry", [one], ["a-2", K["e"], K["b"], at(2000, 1)], ["new", 2, []]),
        ("a parent that is not the principal's", [one], ["a-2", K["e"], K["f"], at(2000, 1)],
         ["new", 2, ["unknown_parent"]]),
        ("a conflict and an unknown parent", [one], ["a-1", K["g"], K["f"], at(2000, 1)],
         ["new", 2, ["revision_conflict", "unknown_parent"]]),
        ("a reply that never parsed still counts as a revision", [one], [None, None, None, at(2000, 1)],
         ["new", 2, []]),
        ("a key owned by a rejected first revision", [rev(1, "a-1", K["a"], None, at(1000, 0))],
         ["a-1", K["h"], None, at(2000, 1)], ["new", 2, ["revision_conflict"]]),
        ("out of order", [one], ["a-2", K["e"], None, at(500, 1)], "order_error"),
        ("a tie on time, decided by the action id", [one], ["a-2", K["e"], None, at(1000, 1)], ["new", 2, []]),
        ("history out of order", [one, rev(2, "a-2", K["c"], None, at(900, 1))], ["a-3", K["e"], None,
                                                                                  at(3000, 2)], "order_error"),
    ]
    return [{"name": name, "history": history,
             "submission": dict(zip(("proposal_key", "proposal_sha256", "parent", "order"), submission)),
             "expect": expect if expect == "order_error" else
             {"kind": expect[0], "revision_index": expect[1], "codes": expect[2]}}
            for name, history, submission, expect in cases]


def ordering() -> dict:
    rows = [("whole second", "2026-10-31T16:05:12+00:00", ACTIONS[1], ROOM),
            ("one microsecond later, but sorts first as text", "2026-10-31T16:05:12.000001+00:00", ACTIONS[0], ROOM),
            ("the same instant as Z, later action id", "2026-10-31T16:05:12Z", ACTIONS[2], ROOM),
            ("a second earlier, written in another zone", "2026-10-31T17:05:11+01:00", ACTIONS[3], ROOM),
            ("the same instant and action, overflow room", "2026-10-31T16:05:12Z", ACTIONS[2], OVERFLOW_ROOM)]
    return {"rows": [{"label": label, "createdAt": created, "id": action, "sessionId": room}
                     for label, created, action, room in rows],
            "expect_order": ["a second earlier, written in another zone", "whole second",
                             "the same instant as Z, later action id", "the same instant and action, overflow room",
                             "one microsecond later, but sorts first as text"],
            "expect_ns": [{"createdAt": "1970-01-01T00:00:00Z", "ns": 0},
                          {"createdAt": "1970-01-01T00:00:00.000000001Z", "ns": 1},
                          {"createdAt": "2026-10-31T16:05:12.5+00:00", "ns": 1793462712500000000},
                          {"createdAt": "2026-10-31T17:05:12.5+01:00", "ns": 1793462712500000000},
                          {"createdAt": "2026-10-31T11:05:12.5-05:00", "ns": 1793462712500000000}],
            "invalid": ["2026-02-30T00:00:00Z", "2026-10-31T16:05:12", "2026-10-31 16:05:12Z",
                        "2026-10-31T24:00:00Z", "2026-10-31T16:05:60Z", "2026-10-31T16:05:12+24:00",
                        "2026-10-31T16:05:12.1234567890Z", "2026-10-31T16:05:12z"]}


# ── canonical and hash vectors ──────────────────────────────────────────────────────────────────────────────────

BACKSLASH, QUOTE = chr(92), chr(34)
CONTROL_STRING = "say " + QUOTE + "hi" + QUOTE + " " + BACKSLASH + " é 😀" + chr(10) + chr(9) + chr(31)
CONTROL_CANONICAL = ("{" + QUOTE + "s" + QUOTE + ":" + QUOTE + "say " + BACKSLASH + QUOTE + "hi" + BACKSLASH + QUOTE
                     + " " + BACKSLASH + BACKSLASH + " é 😀" + BACKSLASH + "n" + BACKSLASH + "t" + BACKSLASH
                     + "u001f" + QUOTE + "}")
CANONICAL = [
    ("keys sort", {"b": 1, "a": 2}, '{"a":2,"b":1}'),
    ("nested objects and arrays keep array order", {"z": [3, {"y": None, "x": True}], "a": "s"},
     '{"a":"s","z":[3,{"x":true,"y":null}]}'),
    ("numbers in ECMAScript form", [0, -0.0, 1, -1, 1.5, 0.1, 16417.5, 75.48, 1e20, 1e21, 1e-6, 1e-7],
     "[0,0,1,-1,1.5,0.1,16417.5,75.48,100000000000000000000,1e+21,0.000001,1e-7]"),
    ("keys sort by UTF-16 code units, not code points", {"ﬁ": 1, "😀": 2, "z": 3}, '{"z":3,"😀":2,"ﬁ":1}'),
    ("strings escape only quote, backslash and control characters", {"s": CONTROL_STRING}, CONTROL_CANONICAL),
    ("an empty object differs from a null field", {"present": None}, '{"present":null}'),
]


def vectors() -> dict:
    sealed_sha = h.proposal_sha256(P_SEALED)
    geometry_cases = (("the Ascend 910 snap0p5 copy", "A", P_A), ("the two-die layout", "F", P_F),
                      ("a sealed plaintext: same geometry, unsalted hash", "F", P_SEALED))
    proposal_cases = (("the Ascend 910 snap0p5 copy", P_A), ("the two-die layout", P_F),
                      ("a sealed plaintext: salted, so its hash is unguessable", P_SEALED),
                      ("without the optional client", without(P_F, "client")))
    transport_cases = ((ROOM, HUMAN, "human", None, "t-1", P_F),
                       (ROOM, AGENT_ACCOUNT, "agent", "example-agent", "t-1", P_F),
                       (OVERFLOW_ROOM, HUMAN, "human", None, "t-1", P_F),
                       (ROOM, HUMAN, "human", None, "t-1", P_SEALED))
    return {
        "schema": "sentilab-open-vectors/1",
        "test_phrases": {"pseudonym_key": PSEUDONYM_PHRASE, "client_secret": CLIENT_PHRASE,
                         "derivation": "sha256 of the UTF-8 phrase gives the 32 bytes"},
        "canonical": [{"name": name, "value": value, "canonical": expected,
                       "sha256": hashlib.sha256(expected.encode()).hexdigest()}
                      for name, value, expected in CANONICAL],
        "manifest_id": [{"manifest": key, "manifest_id": ID[key]} for key in ("A", "M", "F")],
        "geometry": [{"name": name, "manifest": key, "proposal": value,
                      "object": h.geometry_object(value, MANIFESTS[key]),
                      "canonical": h.canonical(h.geometry_object(value, MANIFESTS[key])).decode(),
                      "geometry_sha256": h.geometry_sha256(value, MANIFESTS[key])}
                     for name, key, value in geometry_cases],
        "proposal": [{"name": name, "proposal": value, "canonical": h.canonical(value).decode(),
                      "proposal_sha256": h.proposal_sha256(value)} for name, value in proposal_cases],
        "body_sha256": [{"note_b64": base64.b64encode(note).decode(), "body_sha256": h.body_sha256(note)}
                        for note in (NOTE_F, NOTE_F + bytes((10,)), fenced(P_F), NOTE_SEALED)],
        "source_ref": [{"action_id": action, "source_ref": h.source_ref(action)} for action in ACTIONS[:2]],
        "participant_ref": [{"challenge": challenge, "account_id": account,
                             "participant_ref": h.participant_ref(PSEUDONYM_KEY, challenge, account)}
                            for challenge, account in (("test-challenge", HUMAN), ("test-challenge", AGENT_ACCOUNT),
                                                       ("sentilab-open-1", HUMAN))],
        "transport_id": [{"room": room, "account_id": account, "actor_kind": kind, "actor_agent_id": agent,
                          "manifest_id": ID["F"], "proposal_key": key, "proposal_sha256": h.proposal_sha256(value),
                          "transport_id": h.transport_id(room=room, account_id=account, actor_kind=kind,
                                                         actor_agent_id=agent, manifest_id=ID["F"],
                                                         proposal_key=key, proposal_sha256=h.proposal_sha256(value))}
                         for room, account, kind, agent, key, value in transport_cases],
        "run_id": [{"manifest_id": ID["F"], "participant_ref": ref, "run_id": h.run_id(ID["F"], ref)}
                   for ref in (PREF_HUMAN, "sentilab")],
        "salt": [{"manifest_id": ID["F"], "proposal_key": "t-2", "salt": SALT}],
        "capability": [{"salt": SALT, "manifest_id": ID["F"], "proposal_sha256": sealed_sha, "epoch": epoch,
                        "capability": h.capability(SALT, ID["F"], sealed_sha, epoch),
                        "capability_sha256": h.capability_sha256(h.capability(SALT, ID["F"], sealed_sha, epoch))}
                       for epoch in (1, 2)],
        "ciphertext_ref": [{"age_file_b64": base64.b64encode(AGE_HEADER_ONLY).decode(),
                            "ciphertext_ref": h.ciphertext_ref(AGE_HEADER_ONLY)}],
        "conductor_geometry": [{"manifest": key, "proposal": value,
                                "values": h.conductor_geometry(value, MANIFESTS[key])}
                               for key, value in (("A", P_A), ("F", P_F))],
        "age": {"format": "age-encryption.org/v1", "vectors": [],
                "todo": "TODO: no age implementation (age, rage or a library) was available offline, so no ciphertext "
                        "vector exists yet. Before sealed submissions are relied on (OP-F3, OP-F7), generate "
                        "(identity phrase, recipient, ciphertext, plaintext) vectors with age or rage and add them "
                        "here. Nothing in this contract is an age ciphertext."}}


# ── output ──────────────────────────────────────────────────────────────────────────────────────────────────────

def dump(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=1) + "\n").encode()


def dump_cases(cases) -> bytes:
    """One compact case per line: still one JSON document, and a reviewable diff."""
    lines = (json.dumps(case, ensure_ascii=False, separators=(",", ":")) for case in cases)
    return ('{"cases": [\n' + ",\n".join(lines) + "\n]}\n").encode()


def outputs() -> dict:
    records = (manifest_records() + check_records() + receipt_records() + restricted_records() + status_records()
               + results_records() + other_records())
    return {
        CONTRACT_DIR / "vectors-canonical.json": dump(vectors()),
        CONTRACT_DIR / "limits.provisional.json": dump(LIMITS),
        GOLDEN / "manifests.json": dump({"manifests": MANIFESTS, "manifest_id": ID}),
        GOLDEN / "notes.json": dump_cases(note_cases()),
        GOLDEN / "check-requests.json": dump_cases(check_requests()),
        GOLDEN / "records.json": dump_cases(records),
        GOLDEN / "states.json": dump(state_table()),
        GOLDEN / "revisions.json": dump_cases(revisions()),
        GOLDEN / "order.json": dump(ordering()),
    }


def main(argv) -> int:
    check_only = "--check" in argv
    stale = []
    for path, data in outputs().items():
        if check_only:
            if not path.exists() or path.read_bytes() != data:
                stale.append(path.relative_to(CONTRACT_DIR).as_posix())
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    if stale:
        print("stale: " + ", ".join(stale))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
