"""Builds contracts/open-proposal-v1/vectors-canonical.json and golden/*.json for DESIGN rev 3.

Every input, every expected outcome and every expected code below is written by hand. Hashes are computed with the
contract's functions and cross-checked independently by the JavaScript twin (run-vectors.mjs) and the tests.

    python -m open_proposals.contract.make_vectors           # rewrite the files
    python -m open_proposals.contract.make_vectors --check   # exit 1 if a committed file differs
    python -m open_proposals.contract.make_vectors --seal    # (re)seal the age ciphertexts the golden notes use

Fixture identities are obviously fake (00000000-0000-4000-8000-...). Test keys derive from public phrases at run time
(k_challenge here; the age identities in vectors-age.json); no key material is stored. Sealed notes are real age v1
ciphertexts, made once by --seal with pyrage or the age binary and kept in golden/sealed-notes.json (encryption is
randomised, so they are an input, not an output); the tests open every one with the reference opener.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import sys

from . import age_tools
from . import canonical as h
from .predicate_fixtures import cases as predicate_cases
from .schemas import CONTRACT_DIR
from .states import EVENTS, FLAG_EVENTS, LIFECYCLE

GOLDEN = CONTRACT_DIR / "golden"
SEALED_CACHE = GOLDEN / "sealed-notes.json"
AGE_VECTORS = json.loads((CONTRACT_DIR / "vectors-age.json").read_bytes())
K_PHRASE = "sentilab-open-proposal-v1 test k_challenge, not a secret"
K_CHALLENGE = hashlib.sha256(K_PHRASE.encode()).digest()
AGE_KEYS = {key["key_version"]: age_tools.identity_from_phrase(key["phrase"]) for key in AGE_VECTORS["keys"]}

# Obviously fake identities. Both participants are outside (non-staff) accounts: one posts as a person over REST,
# the other through its admitted agent.
HUMAN = "00000000-0000-4000-8000-00000000000a"
AGENT_ACCOUNT = "00000000-0000-4000-8000-00000000000b"
AGENT_ID = "example-agent"
ROOM = "00000000-0000-4000-8000-0000000000c1"
OVERFLOW_ROOM = "00000000-0000-4000-8000-0000000000c2"
ACTIONS = [f"00000000-0000-4000-8000-0000000000a{index}" for index in range(1, 10)]
RESERVATION = "00000000-0000-4000-8000-0000000000e1"
SALTS = [f"{index:032x}" for index in range(1, 9)]          # obviously fake: never use a fixed salt for real
HOTSPOT6 = "a7a3286e368867c26381e0a23e36b3e273bdeda9"
WITHDRAWN = "HotSpot-7:f18831e48cef5d62580585cca0d7fab6c71bc3cc:grid:64x64"
FIXTURE = "fixture-no-solver"
TERMS_TEXT = "sentilab-open-proposal-v1 test terms text: a fixture, not the published terms"
TERMS_VERSION = "sentilab-open-terms/1@" + hashlib.sha256(TERMS_TEXT.encode()).hexdigest()


def fake(label: str) -> str:
    """An obviously fake pin: the sha256 of a label."""
    return hashlib.sha256(("sentilab-open-proposal-v1 fake: " + label).encode()).hexdigest()


OTHER_TERMS = "sentilab-open-terms/2@" + fake("another terms text")

# ── manifests ───────────────────────────────────────────────────────────────────────────────────────────────────

COUNTING = {"routed": "each ordered pair with R[i][j]>0 is a directed net of R[i][j] wires",
            "proxy": "each unordered pair once"}
LEGALITY = {"units": "um", "anchor": "die-centre", "lattice_um": 500,
            "lattice_rationale": "declared finite engineering benchmark choice (A11)", "margin_um": 500,
            "min_die_gap_um": 100, "min_die_gap_rationale": "TAP-2.5D Eqn. (10)",
            "halo": "uniform ring per die; rotation-invariant", "keepouts": [], "rotation": "per_die_90"}
CLAIMS = {"display_order": ["declared temperature target", "strict-wire thermal tolerance",
                            "r-relaxed-wire thermal tolerance", "strict thermal improvement", "strict wire improvement",
                            "wire improvement with allowed thermal degradation", "robust dominance over R"],
          "suppressed_by": ["failed gate zero", "failed binding", "failed predicate fixture",
                            "failed required scenario"]}
NOMINAL = {"id": "nominal", "applies_to": "both", "grid": 64}
MESH = {"id": "mesh-32", "applies_to": "both", "grid": 32}
POSITION_TEMPLATE = {"id": "position-<die>-<axis>-<sign>", "applies_to": "R",
                     "cases": "raw-R inventory (A12): separately counted, profiled and granted"}
BUNDLE_ENTRY = [{"phase": "evaluate", "grid": 64, "suballocation": "native.evaluate"},
                {"phase": "replay", "grid": 64, "suballocation": "native.replay"},
                {"phase": "mesh", "grid": 32, "suballocation": "native.mesh"},
                {"phase": "route", "suballocation": "routing"}]
PROVISIONAL_POLICY = "provisional; policy choices, not uncertainty; fixed before any candidate is scored"
FROZEN_POLICY = "frozen; policy choices, not uncertainty; fixed before any candidate is scored"
SOURCES = ["TAP-2.5D paper PDF b209f51a…", "Fig. 6(a)-(c)", "Fig. 5(a)-(d)", "sys_ascend910_45mm.cfg",
           "sys_micro150_45mm.cfg"]


def unit(index: int) -> str:
    return f"Chiplet_{index}"


def manifest_shape(*, problem, fixture, dies, matrix, comparator, variants, targets, status="draft") -> dict:
    """The rev 3 section 4.11 draft, field for field: every <...> placeholder is null until decided. The draft states
    two check limits (2 s and 5 s) and every quota, so those are filled in, provisional."""
    signed = status == "signed"
    return {
        "schema": "sentilab-open-manifest/1", "version": 0,
        "status": "signed" if signed else "draft: provisional fields; not a signed manifest",
        "problem": problem, "fixture": fixture,
        "dies": dies,
        "netlist": {"matrix": matrix, "counting": COUNTING},
        "legality": copy.deepcopy(LEGALITY),
        "references": {"file_sha256": None, "comparator": comparator, "engineering_variants": variants,
                       "published_targets": targets},
        "statistic": {"id": "M", "definition": "max native GRID_CENTER value over the enumerated real chiplets",
                      "real_chiplets": [die["unit"] for die in dies],
                      "centre_mapping": "GRID_CENTER: mean of 1, 2 or 4 central cells (pinned)",
                      "record_field": "chiplet_centre_mapping.max_C", "grid": 64,
                      "retained_separately": ["active_layer_grid_peak",
                                              "historical_tap_stdout_selector.literal_on_stdout"],
                      "evaluator": {"kind": "hotspot6", "upstream": HOTSPOT6, "binary_sha256": None,
                                    "gate_zero_record_sha256": None, "build": None, "runtime": None},
                      "numerical_admission": "UNKNOWN"},
        "wire": {"metric": "routed", "router_sha256": None, "solver": "HiGHS MILP, mip_rel_gap 0",
                 "status_acceptance": "proven optimum within the solver limit", "proxy": "diagnostic only"},
        "policy": {"status": PROVISIONAL_POLICY, "D_K": None, "r": None, "B_T_K": None, "B_W_mm": None,
                   "B_W_basis": "W_R_mm", "T_limit_C": None,
                   "proposed_in_draft": {"D_K": 0.5, "r": 0.05, "B_T_K": 1.0, "B_W_fraction": 0.02, "T_limit_C": 85},
                   "tradeoff_budgets_r": [0.1, 0.25, 0.5, 1.0]},
        "bounds": {"u_T": "UNKNOWN", "u_q": "UNKNOWN", "u_abs": "UNKNOWN"},
        "claims": copy.deepcopy(CLAIMS),
        "screen": {"claim": "passes the listed sensitivity cases", "missing": "INCOMPLETE", "failed": "INCONCLUSIVE",
                   "scenarios": [NOMINAL, MESH, POSITION_TEMPLATE]},
        "evaluation_bundle": {"status": "provisional", "per_entry": BUNDLE_ENTRY, "per_manifest": "R's scenario cases",
                              "lifecycle_suballocation": "lifecycle", "intake_suballocation": "intake",
                              "ceilings_cpu_s": None},
        "checks": {"solver_time_limit_s": 2, "check_wall_s": 5, "cleanup_headroom_s": None, "cpu_reserve_s": None,
                   "cpu_enforcement": "live process-tree CPU, enforced while running",
                   "cpu_enforcement_evidence_sha256": None,
                   "cpu_overrun": "detected at settlement on measured process-tree CPU; charged",
                   "status_access": "salted request_sha256 handle or authorized access", "suballocation": "checks"},
        "ties": "ascending T_M, then geometry hash", "failures": "retained; no automatic retry",
        "limits": {"status": "provisional (OP-W1)", "eval_per_account_hour": 3, "eval_per_account_day": 12,
                   "eval_room_hour": 20, "eval_room_day": 120, "queue_max": 30, "warden_call_policy_hour": 40,
                   "code_cpu_s_per_hour_per_root": 600, "code_default_solve_reserve_cpu_s": 15,
                   "check_per_account_hour": 30, "check_room_hour": 600},
        "terms": {"accepted_versions": [], "retention": None},
        "intake": {"order": ["createdAt", "action_id", "room_id"],
                   "cursor": "auditWindow.nextCursor, saved after durable processing", "revision": "1 only"},
        "transport_key": {"schema": "sentilab-open-transport-key/1", "prefix": "so1-", "hex_chars": 48,
                          "fields": ["room", "account", "actor_slot", "manifest_id", "logical_key", "content_sha256"]},
        "disclosure": {"at_opening": ["reference geometry", "frozen SentiLab baseline"],
                       "entries": "public only by explicit choice; private sealed; revealed only by a logged "
                                  "publish choice"},
        "pseudonym": {"rule": "HMAC-SHA256(k_challenge, account_id)", "scope": "per challenge"},
        "exposure": {"sources": list(SOURCES),
                     "note": "exposed families: mark when building any future held-out split"},
        "sealing": {"format": "age X25519, ASCII armour", "recipient": None, "key_version": None,
                    "applies_to": ["private proposals", "private routed checks", "publish commands"],
                    "plaintext_max_bytes": 4096,
                    "sealed_note_max_bytes": 8192, "plaintext_fallback": False,
                    "rotation": "new key version and new manifest version; old keys kept in custody, never reused"},
        "example": {"label": "invented numbers", "inputs": None},
        "window": {"opens_at": None, "closes_at": None},
        "refs": {"grant": None, "claim_rules": None, "checker_sha256": None},
        "submission": {"threads": None}}


def draft_ascend() -> dict:
    """DESIGN rev 3 section 4.11, Ascend 910."""
    dies = ([{"die": 0, "unit": unit(0), "name": "compute", "w_um": 14500, "h_um": 31400, "power_w": 256,
              "halo_um": 90, "rot_deg": [0, 90]},
             {"die": 1, "unit": unit(1), "name": "io", "w_um": 10500, "h_um": 16000, "power_w": 14, "halo_um": 45,
              "rot_deg": [0, 90]}]
            + [{"die": index, "unit": unit(index), "name": "hbm", "w_um": 7750, "h_um": 11870, "power_w": 20,
                "halo_um": 45, "rot_deg": [0, 90]} for index in range(2, 6)])
    return manifest_shape(
        problem="ascend910",
        fixture={"id": "ascend910-45mm", "config": "sundai_tap/configs/sys_ascend910_45mm.cfg",
                 "config_sha256": "4a922560510ba0ab66d04030f137f80262891e7ac7afac3025a57f539e885a8c",
                 "frame_um": 45000, "origin": "frame lower-left", "ambient_c": 45, "link_type": "nppl",
                 "package": {"hotspot_config_sha256": None, "assumptions": "steady state, uniform power per die"}},
        dies=dies,
        matrix=[[0, 200, 256, 256, 256, 256], [200, 0, 0, 0, 0, 0]] + [[256, 0, 0, 0, 0, 0] for _ in range(4)],
        comparator={"id": "ascend910-tap25d-fig6a/raw", "continuous": True, "legal_on_fixture": False,
                    "content_sha256": "0046e17b3e33feef14e570eb6a2026e17c3eea5c232160a052be62c2ae8e470e",
                    "T_R": "UNKNOWN", "T_R_measurement_id": None, "W_R_mm": 16417.5},
        variants=[{"id": "ascend910-tap25d-fig6a-snap0p5", "role": "engineering baseline",
                   "content_sha256": "e0c7ce9eb641ee6aea7d2015e5bc0fc5e3f38f1759c2c2252f14ad5104af022a",
                   "design_hash": "224f2ea088fc50f5eb209a44f1a82fa3704c06037456dc6976657df105c6c9e0"},
                  {"id": "ascend910-tap25d-fig6a/snapped-1mm", "role": "history; superseded as baseline",
                   "content_sha256": "45b0f7e05b82a5eedad1679d751f5684e98ef35c936db54aeea9b475ae397703"}],
        targets={"source": "Ma et al., DATE 2021, Fig. 6(a)", "T_c": 75.48, "W_mm": 16426,
                 "use": "paper-target diagnostic only"})


def draft_micro150() -> dict:
    """The CPU-DRAM manifest: the same shape (DESIGN rev 3 section 4.11, last paragraph)."""
    dies = ([{"die": index, "unit": unit(index), "name": "cpu", "w_um": 8250, "h_um": 9000, "power_w": 150,
              "halo_um": 180, "rot_deg": [0, 90]} for index in range(4)]
            + [{"die": index, "unit": unit(index), "name": "dram", "w_um": 8750, "h_um": 8750, "power_w": 20,
                "halo_um": 135, "rot_deg": [0]} for index in range(4, 8)])
    return manifest_shape(
        problem="micro150",
        fixture={"id": "micro150-45mm", "config": "sundai_tap/configs/sys_micro150_45mm.cfg",
                 "config_sha256": "de6e3edbed848f1bd81758a92f72a1f0b6aa5ffa60aca3153a324cf7a78d9ffd",
                 "frame_um": 45000, "origin": "frame lower-left", "ambient_c": 45, "link_type": "nppl",
                 "package": {"hotspot_config_sha256": None, "assumptions": "steady state, uniform power per die"}},
        dies=dies,
        matrix=[[0, 256, 0, 256, 1024, 0, 0, 0], [256, 0, 256, 0, 0, 1024, 0, 0], [0, 256, 0, 256, 0, 0, 1024, 0],
                [256, 0, 256, 0, 0, 0, 0, 1024], [1024, 0, 0, 0, 0, 0, 0, 0], [0, 1024, 0, 0, 0, 0, 0, 0],
                [0, 0, 1024, 0, 0, 0, 0, 0], [0, 0, 0, 1024, 0, 0, 0, 0]],
        comparator={"id": "micro150-tap25d-fig5a/raw", "continuous": True, "legal_on_fixture": False,
                    "content_sha256": "6e541158ef9cec4e9e8eed469325490d7902e5175e7a41925bad72f900a5fce9",
                    "T_R": "UNKNOWN", "T_R_measurement_id": None, "W_R_mm": 67688.4},
        variants=[{"id": "micro150-tap25d-fig5a-snap0p5", "role": "engineering baseline",
                   "content_sha256": "ecfca7f46fd422f6c35ee35cf7c9ffc97f2a0a627907a69f03891910bc248be9",
                   "design_hash": "0f806acbd50c8847d27509e4e179453cd006444c5adcd7b36413115394d0807f"},
                  {"id": "micro150-tap25d-fig5a/snapped-1mm", "role": "history; superseded as baseline",
                   "content_sha256": "9fee13e0b37d830e3ae1e749cb0bc0d84679de1a6dea03e41ad2e5d8aeea6bbb"}],
        targets={"source": "Ma et al., DATE 2021, Fig. 5(a)", "T_c": 115.94, "W_mm": 67686,
                 "use": "paper-target diagnostic only"})


def signed_test(key_version: int = 1) -> dict:
    """An illustrative signed manifest: two dies on a 10 mm frame, every pin a fake, open in the golden notes."""
    dies = [{"die": 0, "unit": unit(0), "name": "a", "w_um": 2000, "h_um": 3000, "power_w": 10, "halo_um": 50,
             "rot_deg": [0, 90]},
            {"die": 1, "unit": unit(1), "name": "b", "w_um": 2000, "h_um": 2000, "power_w": 5, "halo_um": 50,
             "rot_deg": [0]}]
    manifest = manifest_shape(
        problem="test-two-die", status="signed",
        fixture={"id": "test-two-die-10mm", "config": "test/two-die-10mm.cfg", "config_sha256": fake("two-die config"),
                 "frame_um": 10000, "origin": "frame lower-left", "ambient_c": 45, "link_type": "nppl",
                 "package": {"hotspot_config_sha256": fake("hotspot config"),
                             "assumptions": "steady state, uniform power per die"}},
        dies=dies, matrix=[[0, 4], [4, 0]],
        comparator={"id": "test-two-die-ref/raw", "continuous": True, "legal_on_fixture": False,
                    "content_sha256": fake("raw reference"), "T_R": 60.0, "T_R_measurement_id": fake("T_R receipt"),
                    "W_R_mm": 100.0},
        variants=[{"id": "test-two-die-ref-snap0p5", "role": "engineering baseline",
                   "content_sha256": fake("snapped reference"), "design_hash": fake("snapped design")}],
        targets={"source": "illustrative fixture: no paper", "T_c": 60.5, "W_mm": 101,
                 "use": "paper-target diagnostic only"})
    scalar, recipient = AGE_KEYS[key_version]
    manifest.update({"version": key_version})
    manifest["references"]["file_sha256"] = fake("reference file")
    manifest["statistic"]["evaluator"].update({"binary_sha256": fake("binary"),
                                               "gate_zero_record_sha256": fake("gate zero record"),
                                               "build": "sha256:" + fake("image"), "runtime": FIXTURE})
    manifest["statistic"]["numerical_admission"] = "admitted"
    manifest["wire"]["router_sha256"] = fake("router")
    manifest["policy"].update({"status": FROZEN_POLICY, "D_K": 0.5, "r": 0.05, "B_T_K": 1.0, "B_W_mm": 2.0,
                               "T_limit_C": 85, "proposed_in_draft": None})
    manifest["screen"]["scenarios"] = [NOMINAL, MESH, {"id": "position-0-x-plus", "applies_to": "R", "grid": 64},
                                       {"id": "position-0-x-minus", "applies_to": "R", "grid": 64}]
    manifest["evaluation_bundle"].update({"status": "frozen", "ceilings_cpu_s": {
        "native.evaluate": 15, "native.replay": 15, "native.mesh": 15, "native.reference": 60, "routing": 5,
        "lifecycle": 2, "checks": 6, "intake": 1}})
    manifest["checks"].update({"cleanup_headroom_s": 1, "cpu_reserve_s": 6,
                               "cpu_enforcement_evidence_sha256": fake("live CPU enforcement evidence")})
    manifest["limits"]["status"] = "frozen (test)"
    manifest["terms"] = {"accepted_versions": [TERMS_VERSION], "retention": "P2Y"}
    manifest["exposure"]["sources"] = ["illustrative fixture: no paper"]
    manifest["sealing"].update({"recipient": recipient, "key_version": key_version})
    manifest["example"]["inputs"] = {"W_c_mm": 98.0}
    manifest["window"] = {"opens_at": "2026-11-01T00:00:00Z", "closes_at": "2026-11-08T00:00:00Z"}
    manifest["refs"] = {"grant": "test-grant", "claim_rules": "test-claim-rules", "checker_sha256": fake("checker")}
    return manifest


A, M, F, F2 = draft_ascend(), draft_micro150(), signed_test(1), signed_test(2)
MANIFESTS = {"A": A, "M": M, "F": F, "F2": F2}
ID = {key: h.manifest_id(value) for key, value in MANIFESTS.items()}
TERMS = {"schema": "sentilab-open-terms/1", "version": TERMS_VERSION, "path": h.terms_path(TERMS_VERSION),
         "text_sha256": hashlib.sha256(TERMS_TEXT.encode()).hexdigest(),
         "covers": ["evaluation", "retention of evidence", "display only if public"],
         "grants": {"training": False, "lab_memory": False, "study": False},
         "moderation": {"hide_reasons": ["spam", "abuse", "not_a_layout"],
                        "hidden": "hidden from public pages with the reason; nothing is deleted",
                        "pause": {"hidden_per_day": 3, "pause_hours": 24}},
         "retention": "P2Y"}

# ── the objects participants post ───────────────────────────────────────────────────────────────────────────────


def dies_from(rows) -> list:
    return [{"die": index, "x_um": x, "y_um": y, "rot_deg": rot} for index, (x, y, rot) in enumerate(rows)]


# Appendix A: the Ascend 910 snapped (1 mm) variant, a reference layout, used only to show the syntax.
APPENDIX_A = dies_from([(17000, 23000, 90), (39000, 23000, 0), (7000, 11000, 90), (21000, 11000, 90),
                        (7000, 35000, 90), (21000, 35000, 90)])
TEST_LAYOUT = dies_from([(3000, 5000, 0), (7000, 5000, 0)])
MOVED_LAYOUT = dies_from([(3000, 5500, 0), (7000, 5000, 0)])


def proposal(manifest_key: str, dies, *, key: str, visibility: str, salt: str, parent=None, client=True,
             terms=TERMS_VERSION) -> dict:
    value = {"schema": "sentilab-open-proposal/1", "manifest_id": ID[manifest_key], "terms": terms,
             "proposal_key": key, "parent": parent, "visibility": visibility, "salt": salt, "units": "um",
             "anchor": "die-centre", "dies": copy.deepcopy(dies), "geometry_sha256": ""}
    if client:
        value["client"] = {"name": "example-agent", "version": "0.1.0"}
    value["geometry_sha256"] = h.geometry_sha256(value, MANIFESTS[manifest_key])
    return value


def check_request(manifest_key: str, dies, *, key: str, visibility: str, salt: str) -> dict:
    value = {"schema": "sentilab-open-check-request/1", "manifest_id": ID[manifest_key], "request_key": key,
             "visibility": visibility, "salt": salt, "units": "um", "anchor": "die-centre",
             "dies": copy.deepcopy(dies), "geometry_sha256": ""}
    value["geometry_sha256"] = h.geometry_sha256(value, MANIFESTS[manifest_key])
    return value


P_A = proposal("A", APPENDIX_A, key="example-1", visibility="private", salt=SALTS[0])
P_A_PUBLIC = proposal("A", APPENDIX_A, key="example-1", visibility="public", salt=SALTS[0])
P_PUB = proposal("F", TEST_LAYOUT, key="t-1", visibility="public", salt=SALTS[1])
P_PRIV = proposal("F", TEST_LAYOUT, key="t-2", visibility="private", salt=SALTS[2], client=False)
P_CHILD = proposal("F", MOVED_LAYOUT, key="t-3", visibility="public", salt=SALTS[3], parent=P_PUB["geometry_sha256"])
P_PRIV_F2 = proposal("F2", TEST_LAYOUT, key="t-2", visibility="private", salt=SALTS[2], client=False)
C_PUB = check_request("F", TEST_LAYOUT, key="c-1", visibility="public", salt=SALTS[4])
C_PRIV = check_request("F", TEST_LAYOUT, key="c-2", visibility="private", salt=SALTS[5])
TEAM = {"schema": "sentilab-open-team/1", "manifest_id": ID["F"], "name": "Team Example 7"}
PUBLISH = {"schema": "sentilab-open-publish/1", "manifest_id": ID["F"], "terms": TERMS_VERSION,
           "proposal_sha256": h.proposal_sha256(P_PRIV)}
PRIV_HANDLE = h.proposal_sha256(P_PRIV)         # the private entry's read handle: a bearer secret
PRIV_B64URL = base64.urlsafe_b64encode(bytes.fromhex(PRIV_HANDLE)).decode().rstrip("=")


def changed(value: dict, **edits) -> dict:
    """A copy with fields replaced; a geometric object gets its geometry hash recomputed unless it is edited."""
    out = copy.deepcopy(value)
    out.update(copy.deepcopy(edits))
    manifest_key = next((key for key, manifest_id in ID.items() if manifest_id == out.get("manifest_id")), None)
    if "dies" in out and "geometry_sha256" not in edits and manifest_key is not None:
        out["geometry_sha256"] = h.geometry_sha256(out, MANIFESTS[manifest_key])
    return out


def with_dies(value: dict, rows) -> dict:
    return changed(value, dies=dies_from(rows))


def without(value: dict, field: str) -> dict:
    out = copy.deepcopy(value)
    del out[field]
    return out


def text(value) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode()


def fenced(value) -> bytes:
    return b"```json\n" + text(value) + b"\n```"


def raw_text(value: dict, old: str, new: str) -> bytes:
    body = text(value).decode()
    if body.count(old) != 1:
        raise AssertionError("raw_text needs exactly one match")
    return body.replace(old, new).encode()


def padded(value, size: int) -> bytes:
    body = text(value)
    return body + b" " * (size - len(body))


# ── sealed notes: real age ciphertexts, sealed once (--seal) and kept as an input ───────────────────────────────

SEAL_PLAN = [
    # label, plaintext, header manifest, header key version, sealed to key version
    ("private proposal", text(P_PRIV), "F", 1, 1),
    ("private proposal, sealed again", text(P_PRIV), "F", 1, 1),
    ("private check request", text(C_PRIV), "F", 1, 1),
    ("public proposal", text(P_PUB), "F", 1, 1),
    ("private proposal for the key-2 manifest", text(P_PRIV_F2), "F2", 2, 2),
    ("names key 1, sealed to key 2", text(P_PRIV), "F", 1, 2),
    ("names key 2 on the key-1 manifest", text(P_PRIV), "F", 2, 2),
    ("not JSON", b"a sealed note that is not JSON", "F", 1, 1),
    ("a fenced plaintext", fenced(P_PRIV), "F", 1, 1),
    ("a team object", text(TEAM), "F", 1, 1),
    ("a publish command", text(PUBLISH), "F", 1, 1),
    ("a publish command under terms not accepted", text(changed(PUBLISH, terms=OTHER_TERMS)), "F", 1, 1),
    ("a duplicate key", raw_text(P_PRIV, '"units": "um"', '"units": "um", "units": "um"'), "F", 1, 1),
    ("another manifest inside", text(changed(P_PRIV, manifest_id=ID["M"])), "F", 1, 1),
    ("4,097 plaintext bytes", padded(P_PRIV, 4097), "F", 1, 1),
    ("not UTF-8", bytes((0xFF,)) + text(P_PRIV), "F", 1, 1),
]


def load_sealed() -> dict:
    return json.loads(SEALED_CACHE.read_bytes()) if SEALED_CACHE.exists() else {"notes": []}


def _entry_ok(entry, plaintext, manifest_key, header_version, sealed_to) -> bool:
    return (entry["plaintext_sha256"] == hashlib.sha256(plaintext).hexdigest()
            and entry["manifest_id"] == ID[manifest_key] and entry["header_key_version"] == header_version
            and entry["sealed_to_key_version"] == sealed_to)


def seal_all() -> None:
    """Seal every planned note that is missing or stale; keep the rest byte for byte."""
    cache = {entry["label"]: entry for entry in load_sealed()["notes"]}
    notes = []
    for label, plaintext, manifest_key, header_version, sealed_to in SEAL_PLAN:
        entry = cache.get(label)
        if entry is None or not _entry_ok(entry, plaintext, manifest_key, header_version, sealed_to):
            recipient = AGE_KEYS[sealed_to][1]
            if len(plaintext) <= age_tools.PLAINTEXT_MAX_BYTES:
                note = age_tools.seal(plaintext, ID[manifest_key], header_version, recipient)
            else:                                   # seal() refuses oversize plaintexts; the intake must too
                name, implementation = age_tools._implementation()
                if name != "pyrage":
                    raise RuntimeError("the oversize vector needs pyrage")
                age_file = bytes(implementation.encrypt(plaintext, [implementation.x25519.Recipient.from_str(
                    recipient)]))
                note = f"{h.sealed_header(ID[manifest_key], header_version)}\n{age_tools.armor(age_file)}"
            entry = {"label": label, "plaintext_sha256": hashlib.sha256(plaintext).hexdigest(),
                     "manifest_id": ID[manifest_key], "header_key_version": header_version,
                     "sealed_to_key_version": sealed_to, "note": note}
        notes.append(entry)
    SEALED_CACHE.write_bytes(dump({"sealer": age_tools.sealer(), "notes": notes}))


def sealed_notes() -> dict:
    cache = {entry["label"]: entry for entry in load_sealed()["notes"]}
    out = {}
    for label, plaintext, manifest_key, header_version, sealed_to in SEAL_PLAN:
        entry = cache.get(label)
        if entry is None or not _entry_ok(entry, plaintext, manifest_key, header_version, sealed_to):
            raise SystemExit(f"golden/sealed-notes.json is stale for {label!r}: run make_vectors --seal")
        out[label] = entry["note"].encode("ascii")
    return out


SEALED = {}


def sealed(label: str) -> bytes:
    """A golden sealed note, read from the cache on first use (so --seal can run while it is stale)."""
    if not SEALED:
        SEALED.update(sealed_notes())
    return SEALED[label]


def armour_of(note: bytes) -> bytes:
    return note[note.index(b"\n") + 1:]


def flip_one(note: bytes) -> bytes:
    """One base64 character changed in the middle of the armour: still well-formed, no longer authentic."""
    lines = note.split(b"\n")
    middle = lines[len(lines) // 2]
    swapped = middle[:10] + (b"B" if middle[10:11] != b"B" else b"C") + middle[11:]
    return b"\n".join(lines[:len(lines) // 2] + [swapped] + lines[len(lines) // 2 + 1:])


# ── note cases: the intake (reply) and the offline checker (local) ─────────────────────────────────────────────

AUTO = object()


def C(code, **fields) -> dict:
    return {"code": code, **fields}


def row(item=None, *, account=HUMAN, kind="human", agent=None, room=ROOM, key=AUTO, revision=1, edited=None) -> dict:
    if key is AUTO:
        key = (h.transport_key_for(item, room=room, account=account, actor_kind=kind, actor_id=agent)
               if item is not None else None)
    return {"room": room, "actor_user_id": account, "actor_kind": kind, "actor_id": agent, "idempotency": key,
            "message_revision": revision, "edited_at": edited}


KINDS = {"sentilab-open-proposal/1": "proposal", "sentilab-open-check-request/1": "check-request",
         "sentilab-open-team/1": "team", "sentilab-open-publish/1": "publish"}


def expect(outcome, codes=(), *, parsed=None, stage="all", manifest="F", is_sealed=False) -> dict:
    """stage: how far the parsed object got: none, kind (the schema value), content (its hash) or all."""
    kind = KINDS.get(parsed.get("schema")) if parsed is not None and stage != "none" else None
    content = h.content_sha256(parsed) if kind is not None and stage in ("content", "all") else None
    geometry = (h.geometry_sha256(parsed, MANIFESTS[manifest])
                if kind in ("proposal", "check-request") and stage == "all" else None)
    return {"outcome": outcome, "codes": list(codes), "kind": kind, "content_sha256": content,
            "geometry_sha256": geometry, "sealed": is_sealed}


def note_entry(note: bytes) -> dict:
    try:
        return {"note": note.decode("utf-8")}
    except UnicodeDecodeError:
        return {"note_b64": base64.b64encode(note).decode()}


def reply(name, note, result, *, item=None, row_=None, manifest="F", admission="open", layout=None,
          opener=True) -> dict:
    return {"name": name, "mode": "reply", **note_entry(note), "row": row_ if row_ is not None else row(item),
            "manifest": manifest, "admission": admission, "layout": layout, "opener": opener, "expect": result}


def local(name, note, result, *, manifest="F", layout=None, opener=True) -> dict:
    return {"name": name, "mode": "local", **note_entry(note), "manifest": manifest, "layout": layout,
            "opener": opener, "expect": result}


def note_cases() -> list:
    P, N = P_PUB, text(P_PUB)
    ok = expect("contract_valid", parsed=P)
    BIG = b"sentilab-open-sealed/1 " + ID["F"].encode() + b" 1\n" + b"A" * 8200
    lattice_off = with_dies(P, [(3250, 5000, 0), (7000, 5000, 0)])
    cases = [
        # 0. what counts as an attempt (section 5.3): the note's first bytes
        reply("chat: plain text is ignored", b"hello, which manifest is open?", expect("ignored", stage="none")),
        reply("chat: a space before the brace", b" " + N, expect("ignored", stage="none"), item=P),
        reply("chat: a byte-order mark before the brace", bytes((0xEF, 0xBB, 0xBF)) + N,
              expect("ignored", stage="none"), item=P),
        reply("chat: the sealed marker later in the text", b"see sentilab-open-sealed/1 for private entries",
              expect("ignored", stage="none")),
        reply("chat: a JSON array is not an attempt", b"[1, 2]", expect("ignored", stage="none")),
        reply("a public proposal from an outside account, as a person", N, ok, item=P),
        reply("the same proposal from an outside account's agent", N, ok,
              row_=row(P, account=AGENT_ACCOUNT, kind="agent", agent=AGENT_ID)),
        reply("a fenced proposal", fenced(P), ok, item=P),
        reply("a parent: one of the account's own earlier geometry hashes", text(P_CHILD),
              expect("contract_valid", parsed=P_CHILD), item=P_CHILD),
        reply("without the optional client", text(without(P, "client")),
              expect("contract_valid", parsed=without(P, "client")), item=without(P, "client")),
        reply("a public check request", text(C_PUB), expect("contract_valid", parsed=C_PUB), item=C_PUB),
        reply("a team name", text(TEAM), expect("contract_valid", parsed=TEAM), item=TEAM),
        reply("a team name of 32 characters", text(changed(TEAM, name="A" * 32)),
              expect("contract_valid", parsed=changed(TEAM, name="A" * 32)), item=changed(TEAM, name="A" * 32)),
        reply("a sealed publish command", sealed("a publish command"),
              expect("contract_valid", parsed=PUBLISH, is_sealed=True), item=PUBLISH),
        reply("a plaintext publish names a private handle: private_requires_sealed, nothing else is read",
              text(PUBLISH), expect("rejected", [C("private_requires_sealed")], stage="none"), item=PUBLISH),
        # 1. transport
        reply("unattributable: no actorUserId", N, expect("rejected", [C("unattributable")], stage="none"),
              row_=row(P, account=None, key=None)),
        reply("unattributable: an agent row without its agent id", N,
              expect("rejected", [C("unattributable")], stage="none"), row_=row(P, kind="agent", key=None)),
        reply("edited before ingest: revision 2", N, expect("rejected", [C("edited_before_ingest")], stage="none"),
              row_=row(P, revision=2)),
        reply("edited before ingest: editedAt is set", N,
              expect("rejected", [C("edited_before_ingest")], stage="none"),
              row_=row(P, edited="2026-11-01T10:00:00Z")),
        reply("row failures report together", N,
              expect("rejected", [C("edited_before_ingest"), C("unattributable")], stage="none"),
              row_=row(P, account=None, key=None, revision=2)),
        reply("oversize: 4,097 plaintext bytes", padded(P, 4097),
              expect("rejected", [C("oversize", size_bytes=4097)], stage="none"), item=P),
        reply("4,096 plaintext bytes are within the limit", padded(P, 4096), ok, item=P),
        reply("not UTF-8", b'{"schema": "' + bytes((0xFF,)) + b'"}', expect("rejected", [C("not_utf8")], stage="none")),
        reply("a private plaintext: private_requires_sealed, nothing else is read", text(P_PRIV),
              expect("rejected", [C("private_requires_sealed")], stage="none"), item=P_PRIV),
        reply("a private plaintext with errors: still only private_requires_sealed",
              text(changed(P_PRIV, extra=1, dies=[])),
              expect("rejected", [C("private_requires_sealed")], stage="none"), item=P_PRIV),
        reply("transport key: the proposal_key itself is not the key", N,
              expect("rejected", [C("transport_key_mismatch")], parsed=P, stage="content"),
              row_=row(P, key="t-1")),
        reply("transport key: missing", N,
              expect("rejected", [C("transport_key_mismatch")], parsed=P, stage="content"), row_=row(P, key=None)),
        reply("transport key: derived for the human slot, posted by the agent", N,
              expect("rejected", [C("transport_key_mismatch")], parsed=P, stage="content"),
              row_=row(P, account=AGENT_ACCOUNT, kind="agent", agent=AGENT_ID,
                       key=h.transport_key_for(P, room=ROOM, account=AGENT_ACCOUNT, actor_kind="human",
                                               actor_id=None))),
        reply("transport key: derived for another room", N,
              expect("rejected", [C("transport_key_mismatch")], parsed=P, stage="content"),
              row_=row(P, key=h.transport_key_for(P, room=OVERFLOW_ROOM, account=HUMAN, actor_kind="human",
                                                  actor_id=None))),
        reply("transport key: derived for other content under the same logical key", N,
              expect("rejected", [C("transport_key_mismatch")], parsed=P, stage="content"),
              row_=row(P, key=h.transport_key_for(P_CHILD | {"proposal_key": "t-1"}, room=ROOM, account=HUMAN,
                                                  actor_kind="human", actor_id=None))),
        # 1. sealed notes (section 3.7): real age v1 ciphertexts
        reply("sealed private proposal, key version 1", sealed("private proposal"),
              expect("contract_valid", parsed=P_PRIV, is_sealed=True), item=P_PRIV),
        reply("the same plaintext sealed again: same content hash and transport key, other bytes",
              sealed("private proposal, sealed again"), expect("contract_valid", parsed=P_PRIV, is_sealed=True),
              item=P_PRIV),
        reply("sealed private check request", sealed("private check request"),
              expect("contract_valid", parsed=C_PRIV, is_sealed=True), item=C_PRIV),
        reply("a public proposal may also be sealed", sealed("public proposal"),
              expect("contract_valid", parsed=P_PUB, is_sealed=True), item=P_PUB),
        reply("sealed for the key-2 manifest (a rotation)", sealed("private proposal for the key-2 manifest"),
              expect("contract_valid", parsed=P_PRIV_F2, manifest="F2", is_sealed=True), item=P_PRIV_F2,
              manifest="F2"),
        reply("unsealable: the header names key version 2, the manifest pins 1",
              b"sentilab-open-sealed/1 " + ID["F"].encode() + b" 2\n" + armour_of(sealed("private proposal")),
              expect("rejected", [C("unsealable")], stage="none", is_sealed=True), item=P_PRIV),
        reply("unsealable: an older key version opens it, but the manifest pins another",
              sealed("names key 2 on the key-1 manifest"),
              expect("rejected", [C("unsealable")], stage="none", is_sealed=True), item=P_PRIV),
        reply("unsealable: the header names key 1, the ciphertext is for key 2", sealed("names key 1, sealed to key 2"),
              expect("rejected", [C("unsealable")], stage="none", is_sealed=True), item=P_PRIV),
        reply("unsealable: one armour character changed", flip_one(sealed("private proposal")),
              expect("rejected", [C("unsealable")], stage="none", is_sealed=True), item=P_PRIV),
        reply("unsealable: the plaintext is not JSON", sealed("not JSON"),
              expect("rejected", [C("unsealable")], stage="none", is_sealed=True)),
        reply("unsealable: a fence inside a seal", sealed("a fenced plaintext"),
              expect("rejected", [C("unsealable")], stage="none", is_sealed=True)),
        reply("unsealable: a team object is not sealable", sealed("a team object"),
              expect("rejected", [C("unsealable")], stage="none", is_sealed=True)),
        reply("unsealable: JSON after the header, no armour (never re-read as plaintext)",
              b"sentilab-open-sealed/1 " + ID["F"].encode() + b" 1\n" + N,
              expect("rejected", [C("unsealable")], stage="none", is_sealed=True), item=P),
        reply("unsealable: an upper-case manifest id in the header",
              b"sentilab-open-sealed/1 " + ID["F"].upper().encode() + b" 1\n" + armour_of(sealed("private proposal")),
              expect("rejected", [C("unsealable")], stage="none", is_sealed=True), item=P_PRIV),
        reply("unsealable: a key version with a leading zero",
              b"sentilab-open-sealed/1 " + ID["F"].encode() + b" 01\n" + armour_of(sealed("private proposal")),
              expect("rejected", [C("unsealable")], stage="none", is_sealed=True), item=P_PRIV),
        reply("unsealable: a draft manifest pins no recipient",
              b"sentilab-open-sealed/1 " + ID["A"].encode() + b" 1\n" + armour_of(sealed("private proposal")),
              expect("rejected", [C("unsealable")], stage="none", is_sealed=True), item=P_PRIV, manifest="A"),
        reply("sealed: the header names an unknown manifest",
              b"sentilab-open-sealed/1 " + b"e" * 64 + b" 1\n" + armour_of(sealed("private proposal")),
              expect("rejected", [C("unknown_manifest")], stage="none", is_sealed=True), item=P_PRIV),
        reply("sealed: the header names another manifest than the thread",
              b"sentilab-open-sealed/1 " + ID["M"].encode() + b" 1\n" + armour_of(sealed("private proposal")),
              expect("rejected", [C("manifest_mismatch", path="/manifest_id")], stage="none", is_sealed=True),
              item=P_PRIV),
        reply("sealed: the plaintext names another manifest than its header", sealed("another manifest inside"),
              expect("rejected", [C("manifest_mismatch", path="/manifest_id")],
                     parsed=changed(P_PRIV, manifest_id=ID["M"]), stage="content", is_sealed=True),
              item=changed(P_PRIV, manifest_id=ID["M"])),
        reply("sealed: a duplicate key in the plaintext", sealed("a duplicate key"),
              expect("rejected", [C("duplicate_key")], stage="none", is_sealed=True)),
        reply("sealed: 4,097 plaintext bytes", sealed("4,097 plaintext bytes"),
              expect("rejected", [C("oversize", size_bytes=4097)], stage="none", is_sealed=True), item=P_PRIV),
        reply("sealed: a note over 8,192 bytes", BIG,
              expect("rejected", [C("oversize", size_bytes=len(BIG))], stage="none", is_sealed=True)),
        reply("sealed, no opener: the header is valid, the note stays unopened", sealed("private proposal"),
              expect("sealed_unopened", stage="none", is_sealed=True), item=P_PRIV, opener=False),
        reply("no opener: JSON after the header is still unsealable",
              b"sentilab-open-sealed/1 " + ID["F"].encode() + b" 1\n" + N,
              expect("rejected", [C("unsealable")], stage="none", is_sealed=True), item=P, opener=False),
        reply("unsealable: the plaintext is not UTF-8", sealed("not UTF-8"),
              expect("rejected", [C("unsealable")], stage="none", is_sealed=True)),
        # 2. envelope and schema
        reply("malformed JSON", b'{"schema": ', expect("rejected", [C("malformed_json")], stage="none")),
        reply("a fence that never closes", b"```json\n" + N, expect("rejected", [C("malformed_json")], stage="none")),
        reply("only a json fence", b"```\n" + N + b"\n```", expect("rejected", [C("malformed_json")], stage="none")),
        reply("duplicate key", raw_text(P, '"units": "um"', '"units": "um", "units": "um"'),
              expect("rejected", [C("duplicate_key")], stage="none")),
        reply("NaN", raw_text(P, '"x_um": 3000', '"x_um": NaN'),
              expect("rejected", [C("nonfinite_number")], stage="none")),
        reply("an overflowing number", raw_text(P, '"x_um": 3000', '"x_um": 1e999'),
              expect("rejected", [C("nonfinite_number")], stage="none")),
        reply("too deep: five levels", b'{"schema": "sentilab-open-team/1", "a": {"b": {"c": {"d": {}}}}}',
              expect("rejected", [C("too_deep")], stage="none")),
        reply("a schema value that is not a string", b'{"schema": ["sentilab-open-proposal/1"]}',
              expect("rejected", [C("schema_invalid", path="/schema", keyword="enum")], stage="none")),
        reply("an unknown schema value", text(changed(P, schema="sentilab-open-proposal/2")),
              expect("rejected", [C("schema_invalid", path="/schema", keyword="enum")], stage="none")),
        reply("an unknown field", text(changed(P, note="please rank me first")),
              expect("rejected", [C("unknown_field", path="")], parsed=P, stage="kind")),
        reply("a revision-1 field: wire_track", text(changed(P, wire_track="strict")),
              expect("rejected", [C("unknown_field", path="")], parsed=P, stage="kind")),
        reply("a revision-2 field: lattice_um", text(changed(P, lattice_um=500)),
              expect("rejected", [C("unknown_field", path="")], parsed=P, stage="kind")),
        reply("visibility is required", text(without(P, "visibility")),
              expect("rejected", [C("schema_invalid", path="/visibility", keyword="required")], parsed=P,
                     stage="kind")),
        reply("visibility is public or private", text(changed(P, visibility="unlisted")),
              expect("rejected", [C("schema_invalid", path="/visibility", keyword="enum")], parsed=P, stage="kind")),
        reply("salt is required on a public proposal too", text(without(P, "salt")),
              expect("rejected", [C("schema_invalid", path="/salt", keyword="required")], parsed=P, stage="kind")),
        reply("salt is 32 lower-case hex characters", text(changed(P, salt=SALTS[1].upper().replace("0", "A"))),
              expect("rejected", [C("schema_invalid", path="/salt", keyword="pattern")], parsed=P, stage="kind")),
        reply("terms is required", text(without(P, "terms")),
              expect("rejected", [C("schema_invalid", path="/terms", keyword="required")], parsed=P, stage="kind")),
        reply("an integer is an integer literal", raw_text(P, '"x_um": 3000', '"x_um": 3000.0'),
              expect("rejected", [C("schema_invalid", path="/dies/0/x_um", keyword="type")], parsed=P,
                     stage="kind")),
        reply("rot_deg is 0 or 90", text(with_dies(P, [(3000, 5000, 180), (7000, 5000, 0)])),
              expect("rejected", [C("schema_invalid", path="/dies/0/rot_deg", keyword="enum")], parsed=P,
                     stage="kind")),
        reply("coordinates stay below 1,000,001 um", text(with_dies(P, [(1000001, 5000, 0), (7000, 5000, 0)])),
              expect("rejected", [C("schema_invalid", path="/dies/0/x_um", keyword="maximum")], parsed=P,
                     stage="kind")),
        reply("a salt of 64 hex characters is not 32", text(changed(P, salt="0" * 64)),
              expect("rejected", [C("schema_invalid", path="/salt", keyword="pattern")], parsed=P, stage="kind")),
        reply("the client name is at most 32 characters", text(changed(P, client={"name": "a" * 33, "version": "1"})),
              expect("rejected", [C("schema_invalid", path="/client/name", keyword="pattern")], parsed=P,
                     stage="kind")),
        reply("proposal_key is at most 64 characters", text(changed(P, proposal_key="a" * 65)),
              expect("rejected", [C("schema_invalid", path="/proposal_key", keyword="pattern")], parsed=P,
                     stage="kind")),
        reply("at most 32 dies, and die indices up to 31", text(changed(P, dies=dies_from([(500, 500, 0)] * 33))),
              expect("rejected", [C("schema_invalid", path="/dies", keyword="maxItems"),
                                  C("schema_invalid", path="/dies/32/die", keyword="maximum")], parsed=P,
                     stage="kind")),
        reply("the client name is a short token", text(changed(P, client={"name": "my agent", "version": "1"})),
              expect("rejected", [C("schema_invalid", path="/client/name", keyword="pattern")], parsed=P,
                     stage="kind")),
        reply("a trailing newline: proposal_key", text(changed(P, proposal_key="t-1\n")),
              expect("rejected", [C("schema_invalid", path="/proposal_key", keyword="pattern")], parsed=P,
                     stage="kind")),
        reply("a trailing CRLF: proposal_key", text(changed(P, proposal_key="t-1\r\n")),
              expect("rejected", [C("schema_invalid", path="/proposal_key", keyword="pattern")], parsed=P,
                     stage="kind")),
        reply("a trailing newline: a 33-character salt", text(changed(P, salt=SALTS[1] + "\n")),
              expect("rejected", [C("schema_invalid", path="/salt", keyword="pattern")], parsed=P, stage="kind")),
        reply("a trailing newline: client.name", text(changed(P, client={"name": "example-agent\n", "version": "1"})),
              expect("rejected", [C("schema_invalid", path="/client/name", keyword="pattern")], parsed=P,
                     stage="kind")),
        reply("a trailing newline: request_key", text(changed(C_PUB, request_key="c-1\n")),
              expect("rejected", [C("schema_invalid", path="/request_key", keyword="pattern")], parsed=C_PUB,
                     stage="kind")),
        reply("a trailing newline: a team name", text(changed(TEAM, name="Team Example 7\n")),
              expect("rejected", [C("schema_invalid", path="/name", keyword="pattern")], parsed=TEAM, stage="kind")),
        reply("proposal_key is lower case", text(changed(P, proposal_key="T-1")),
              expect("rejected", [C("schema_invalid", path="/proposal_key", keyword="pattern")], parsed=P,
                     stage="kind")),
        reply("a team name starts with a letter or digit", text(changed(TEAM, name=" Team")),
              expect("rejected", [C("schema_invalid", path="/name", keyword="pattern")], parsed=TEAM, stage="kind")),
        reply("a team name of 33 characters", text(changed(TEAM, name="A" * 33)),
              expect("rejected", [C("schema_invalid", path="/name", keyword="pattern")], parsed=TEAM, stage="kind")),
        reply("a check request carries no terms", text(changed(C_PUB, terms=TERMS_VERSION)),
              expect("rejected", [C("unknown_field", path="")], parsed=C_PUB, stage="kind")),
        # 3. manifest and terms
        reply("an unknown manifest", text(changed(P, manifest_id="e" * 64)),
              expect("rejected", [C("unknown_manifest")], parsed=changed(P, manifest_id="e" * 64),
                     stage="content"), item=changed(P, manifest_id="e" * 64)),
        reply("another manifest than the thread's", text(changed(P, manifest_id=ID["M"])),
              expect("rejected", [C("manifest_mismatch", path="/manifest_id")],
                     parsed=changed(P, manifest_id=ID["M"]), stage="content"), item=changed(P, manifest_id=ID["M"])),
        reply("not open yet", N, expect("rejected", [C("not_open_yet")], parsed=P), item=P, admission="not_open_yet"),
        reply("closed", N, expect("rejected", [C("manifest_closed")], parsed=P), item=P, admission="closed"),
        reply("a draft manifest is never open, and accepts no terms yet", text(P_A_PUBLIC),
              expect("rejected", [C("not_open_yet"), C("terms_not_accepted")], parsed=P_A_PUBLIC, manifest="A"),
              item=P_A_PUBLIC, manifest="A"),
        reply("terms not accepted", text(changed(P, terms=OTHER_TERMS)),
              expect("rejected", [C("terms_not_accepted")], parsed=changed(P, terms=OTHER_TERMS)),
              item=changed(P, terms=OTHER_TERMS)),
        reply("a sealed publish under terms not accepted is refused privately, nothing made public",
              sealed("a publish command under terms not accepted"),
              expect("rejected", [C("terms_not_accepted")], parsed=changed(PUBLISH, terms=OTHER_TERMS),
                     is_sealed=True), item=changed(PUBLISH, terms=OTHER_TERMS)),
        reply("every legality violation is reported together", text(changed(lattice_off, terms=OTHER_TERMS)),
              expect("rejected", [C("manifest_closed"), C("terms_not_accepted"),
                                  C("lattice", dies=[0], amount_um=250)],
                     parsed=changed(lattice_off, terms=OTHER_TERMS)),
              item=changed(lattice_off, terms=OTHER_TERMS), admission="closed"),
        # 4-6. geometry, exact integers
        reply("the geometry hash is recomputed", text(changed(P, geometry_sha256="0" * 64)),
              expect("rejected", [C("geometry_hash_mismatch")], parsed=changed(P, geometry_sha256="0" * 64)),
              item=changed(P, geometry_sha256="0" * 64)),
        reply("one die short", text(with_dies(P, [(3000, 5000, 0)])),
              expect("rejected", [C("die_count", count=1)], parsed=with_dies(P, [(3000, 5000, 0)])),
              item=with_dies(P, [(3000, 5000, 0)])),
        reply("dies out of order", text(changed(P, dies=[TEST_LAYOUT[1], TEST_LAYOUT[0]])),
              expect("rejected", [C("die_order", dies=[0, 1])],
                     parsed=changed(P, dies=[TEST_LAYOUT[1], TEST_LAYOUT[0]])),
              item=changed(P, dies=[TEST_LAYOUT[1], TEST_LAYOUT[0]])),
        reply("a square die does not turn", text(with_dies(P, [(3000, 5000, 0), (7000, 5000, 90)])),
              expect("rejected", [C("rotation_not_allowed", dies=[1])],
                     parsed=with_dies(P, [(3000, 5000, 0), (7000, 5000, 90)])),
              item=with_dies(P, [(3000, 5000, 0), (7000, 5000, 90)])),
        reply("a centre outside the frame", text(with_dies(P, [(10500, 5000, 0), (7000, 5000, 0)])),
              expect("rejected", [C("out_of_frame", dies=[0], amount_um=500)],
                     parsed=with_dies(P, [(10500, 5000, 0), (7000, 5000, 0)])),
              item=with_dies(P, [(10500, 5000, 0), (7000, 5000, 0)])),
        reply("a centre outside the frame in y", text(with_dies(P, [(3000, 10500, 0), (7000, 5000, 0)])),
              expect("rejected", [C("out_of_frame", dies=[0], amount_um=500)],
                     parsed=with_dies(P, [(3000, 10500, 0), (7000, 5000, 0)])),
              item=with_dies(P, [(3000, 10500, 0), (7000, 5000, 0)])),
        reply("a centre on the frame edge is in the frame (the layout checker judges margins)",
              text(with_dies(P, [(3000, 5000, 0), (10000, 5000, 0)])),
              expect("contract_valid", parsed=with_dies(P, [(3000, 5000, 0), (10000, 5000, 0)])),
              item=with_dies(P, [(3000, 5000, 0), (10000, 5000, 0)])),
        reply("off the 500 um lattice in x", text(lattice_off),
              expect("rejected", [C("lattice", dies=[0], amount_um=250)], parsed=lattice_off), item=lattice_off),
        reply("off the lattice in y, the nearer distance", text(with_dies(P, [(3000, 5400, 0), (7000, 5000, 0)])),
              expect("rejected", [C("lattice", dies=[0], amount_um=100)],
                     parsed=with_dies(P, [(3000, 5400, 0), (7000, 5000, 0)])),
              item=with_dies(P, [(3000, 5400, 0), (7000, 5000, 0)])),
        reply("several dies, several codes, in vocabulary order",
              text(with_dies(P, [(3100, 5000, 0), (10500, 5000, 90)])),
              expect("rejected", [C("out_of_frame", dies=[1], amount_um=500), C("rotation_not_allowed", dies=[1]),
                                  C("lattice", dies=[0], amount_um=100)],
                     parsed=with_dies(P, [(3100, 5000, 0), (10500, 5000, 90)])),
              item=with_dies(P, [(3100, 5000, 0), (10500, 5000, 90)])),
        reply("a check request off the lattice", text(with_dies(C_PUB, [(3250, 5000, 0), (7000, 5000, 0)])),
              expect("rejected", [C("lattice", dies=[0], amount_um=250)],
                     parsed=with_dies(C_PUB, [(3250, 5000, 0), (7000, 5000, 0)])),
              item=with_dies(C_PUB, [(3250, 5000, 0), (7000, 5000, 0)])),
        # 7. the layout seam (OP-F7)
        reply("the layout checker finds nothing: legal", N, expect("legal", parsed=P), item=P, layout=[]),
        reply("the layout checker's codes are reported", N,
              expect("rejected", [C("margin", dies=[0], amount_um=20)], parsed=P), item=P,
              layout=[C("margin", dies=[0], amount_um=20)]),
        reply("halo overlap, spacing and a keepout, together", N,
              expect("rejected", [C("halo_overlap", dies=[0, 1], amount_um=40), C("min_spacing", dies=[0, 1],
                                                                                    amount_um=60),
                                  C("keepout", dies=[1], amount_um=10)], parsed=P),
              item=P, layout=[C("keepout", dies=[1], amount_um=10), C("min_spacing", dies=[0, 1], amount_um=60),
                              C("halo_overlap", dies=[0, 1], amount_um=40)]),
        reply("the layout checker is not run when the dies do not map",
              text(changed(P, dies=[TEST_LAYOUT[1], TEST_LAYOUT[0]])),
              expect("rejected", [C("die_order", dies=[0, 1])],
                     parsed=changed(P, dies=[TEST_LAYOUT[1], TEST_LAYOUT[0]])),
              item=changed(P, dies=[TEST_LAYOUT[1], TEST_LAYOUT[0]]), layout=[C("margin", dies=[0], amount_um=20)]),
        reply("nor when a rotation is not allowed", text(with_dies(P, [(3000, 5000, 0), (7000, 5000, 90)])),
              expect("rejected", [C("rotation_not_allowed", dies=[1])],
                     parsed=with_dies(P, [(3000, 5000, 0), (7000, 5000, 90)])),
              item=with_dies(P, [(3000, 5000, 0), (7000, 5000, 90)]), layout=[C("margin", dies=[0], amount_um=20)]),
        # the offline checker (section 6.1): no row, no transport key, no admission
        local("local: anything but an attempt is malformed", b"hello", expect("rejected", [C("malformed_json")],
                                                                          stage="none")),
        local("local: a private plaintext before sealing", text(P_PRIV), expect("contract_valid", parsed=P_PRIV)),
        local("local: a sealed note opens", sealed("private proposal"),
              expect("contract_valid", parsed=P_PRIV, is_sealed=True)),
        local("local: Appendix A against the Ascend 910 draft: its terms are not accepted yet", text(P_A),
              expect("rejected", [C("terms_not_accepted")], parsed=P_A, manifest="A"), manifest="A"),
        local("local: Appendix A with the layout checker finding nothing", text(P_A),
              expect("rejected", [C("terms_not_accepted")], parsed=P_A, manifest="A"), manifest="A", layout=[]),
        local("local: legal with the layout checker", N, expect("legal", parsed=P), layout=[]),
        local("local: a publish command before sealing", text(PUBLISH), expect("contract_valid", parsed=PUBLISH)),
        local("local: a trailing newline in proposal_key", text(changed(P, proposal_key="t-1\n")),
              expect("rejected", [C("schema_invalid", path="/proposal_key", keyword="pattern")], parsed=P,
                     stage="kind")),
        local("local: a trailing newline in a team name", text(changed(TEAM, name="Team Example 7\n")),
              expect("rejected", [C("schema_invalid", path="/name", keyword="pattern")], parsed=TEAM, stage="kind")),
    ]
    return cases


# ── records ──────────────────────────────────────────────────────────────────────────────────────────────────────

DELETE = object()


def rec(kind, name, record, expect_=(), **context) -> dict:
    return {"kind": kind, "name": name, "record": record, "context": context, "expect": list(expect_)}


def edit(value, path, new):
    """A copy with one value at a /-separated path replaced (or deleted with DELETE)."""
    out = copy.deepcopy(value)
    parts = path.strip("/").split("/")
    target = out
    for part in parts[:-1]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    last = int(parts[-1]) if isinstance(target, list) else parts[-1]
    if new is DELETE:
        del target[last]
    else:
        target[last] = new
    return out


def R(rule, path, code="record_inconsistent") -> dict:
    return {"code": code, "path": path, "rule": rule}


def S(path, keyword) -> dict:
    return {"code": "schema_invalid", "path": path, "keyword": keyword}


def apply_edits(value, edits):
    """The record a golden manifest case describes: its base manifest with each (path, value) applied in order."""
    out = copy.deepcopy(value)
    for change in edits:
        out = edit(out, change["path"], DELETE if change.get("delete") else change["value"])
    return out


def mrec(name, base, edits=(), expect_=(), **context) -> dict:
    """A manifest case as its base and edits: the full record is applied by the tests (test_golden.record_of)."""
    changes = [{"path": path, "delete": True} if value is DELETE else {"path": path, "value": value}
               for path, value in edits]
    return {"kind": "manifest", "name": name, "base": base, "edits": changes, "context": context,
            "expect": list(expect_)}


def manifest_records() -> list:
    out = [mrec(f"valid: {name}", key) for key, name in
           (("A", "the Ascend 910 draft (rev 3 section 4.11)"), ("M", "the CPU-DRAM draft"),
            ("F", "a signed test manifest"), ("F2", "the same, rotated to key version 2"))]
    unknown = {"code": "unknown_field", "path": ""}
    bad = [
        ("die index", [("/dies/1/die", 0)], [R("manifest.die_index", "/dies/1")]),
        ("a square die may not turn", [("/dies/1/rot_deg", [0, 90])],
         [R("manifest.square_rotation", "/dies/1/rot_deg")]),
        ("a rectangular die turns", [("/dies/0/rot_deg", [0])], [R("manifest.square_rotation", "/dies/0/rot_deg")]),
        ("real chiplets are the dies' units", [("/statistic/real_chiplets", ["Chiplet_0"])],
         [R("manifest.real_chiplets", "/statistic/real_chiplets")]),
        ("netlist: one row per die", [("/netlist/matrix", [[0, 4]])], [R("manifest.netlist", "/netlist/matrix")]),
        ("netlist: no self links", [("/netlist/matrix", [[1, 4], [4, 0]])],
         [R("manifest.netlist", "/netlist/matrix")]),
        ("budgets ascend", [("/policy/tradeoff_budgets_r", [0.25, 0.1])],
         [R("manifest.r_values", "/policy/tradeoff_budgets_r")]),
        ("r has at most two decimals", [("/policy/r", 0.125)],
         [R("manifest.r_values", "/policy/tradeoff_budgets_r")]),
        ("the solve sits inside the wall", [("/checks/solver_time_limit_s", 5)],
         [R("manifest.check_limits", "/checks/solver_time_limit_s")]),
        ("a day allows at least an hour", [("/limits/eval_room_day", 19)], [R("manifest.quota_windows", "/limits")]),
        ("the window closes after it opens", [("/window/closes_at", "2026-10-31T00:00:00Z")],
         [R("manifest.window", "/window")]),
        ("scenario ids are unique", [("/screen/scenarios", [NOMINAL, NOMINAL])],
         [R("manifest.scenarios", "/screen/scenarios")]),
        ("the screen lists nominal", [("/screen/scenarios", [MESH])], [R("manifest.scenarios", "/screen/scenarios")]),
        ("signed: no recipient", [("/sealing/recipient", None)], [R("manifest.signed_pins", "/sealing/recipient")]),
        ("signed: provisional policy", [("/policy/status", PROVISIONAL_POLICY)],
         [R("manifest.signed_pins", "/policy/status")]),
        ("signed: the position inventory still a placeholder",
         [("/screen/scenarios", [NOMINAL, MESH, POSITION_TEMPLATE])], [R("manifest.signed_pins", "/screen/scenarios")]),
        ("signed: numerical admission unknown", [("/statistic/numerical_admission", "UNKNOWN")],
         [R("manifest.signed_pins", "/statistic/numerical_admission")]),
        ("signed: a check limit unset", [("/checks/cpu_reserve_s", None)],
         [R("manifest.signed_pins", "/checks/cpu_reserve_s")]),
        ("signed: no evidence of live CPU enforcement (an admission requirement)",
         [("/checks/cpu_enforcement_evidence_sha256", None)],
         [R("manifest.signed_pins", "/checks/cpu_enforcement_evidence_sha256")]),
        ("schema: live CPU enforcement is required, not optional", [("/checks/cpu_enforcement", "at settlement")],
         [S("/checks/cpu_enforcement", "const")]),
        ("schema: overrun detection is its own field", [("/checks/cpu_overrun", DELETE)],
         [S("/checks/cpu_overrun", "required")]),
        ("signed: no accepted terms", [("/terms/accepted_versions", [])],
         [R("manifest.signed_pins", "/terms/accepted_versions")]),
        ("schema: plaintext_fallback is false", [("/sealing/plaintext_fallback", True)],
         [S("/sealing/plaintext_fallback", "const")]),
        ("schema: the sealed-note cap is 8,192", [("/sealing/sealed_note_max_bytes", 16384)],
         [S("/sealing/sealed_note_max_bytes", "const")]),
        ("schema: the transport-key prefix is so1-", [("/transport_key/prefix", "open-tk1-")],
         [S("/transport_key/prefix", "const")]),
        ("schema: no bound defaults to zero", [("/bounds/u_T", 0)], [S("/bounds/u_T", "const")]),
        ("schema: a revision-1 field", [("/wire_tracks", [{"id": "strict"}])], [unknown]),
        ("schema: one check limit cannot stand in for the others", [("/checks/time_limit_s", 5)],
         [{"code": "unknown_field", "path": "/checks"}]),
        ("schema: the call backstop is a field of its own", [("/limits/warden_call_policy_hour", DELETE)],
         [S("/limits/warden_call_policy_hour", "required")]),
        ("schema: threads stay out of the hashed manifest", [("/submission/threads", [ROOM])],
         [S("/submission/threads", "type")]),
        ("schema: a lattice in micrometres, an integer", [("/legality/lattice_um", 500.0)],
         [S("/legality/lattice_um", "type")]),
    ]
    out += [mrec(name, "F", edits, expected) for name, edits, expected in bad]
    out.append(mrec("a private handle in a public manifest field, as base64url", "F",
                    [("/refs/grant", "grant-" + PRIV_B64URL)], [R("privacy.handle", "")],
                    private_handles=[PRIV_HANDLE]))
    return out


def terms_records() -> list:
    return [rec("terms", "valid: the fixture terms", TERMS),
            rec("terms", "the version names the text's hash", edit(TERMS, "/text_sha256", fake("other text")),
                [R("terms.version_hash", "/version")]),
            rec("terms", "no training grant, ever", edit(TERMS, "/grants/training", True),
                [S("/grants/training", "const")]),
            rec("terms", "display only if public", edit(TERMS, "/covers", ["evaluation", "retention of evidence"]),
                [S("/covers", "const")]),
            rec("terms", "the path is the version's canonical path", edit(TERMS, "/path",
                                                                          "/sentilab/open/terms/2@" + "0" * 64 + ".md"),
                [R("terms.path", "/path")]),
            rec("terms", "a retention period is a duration", edit(TERMS, "/retention", "two years"),
                [S("/retention", "pattern")])]


LABELS4 = ["routed wire only", "no thermal solve", "nominal", "not a score"]
Q_F = {"0": -2.0, "0.05": -7.0, "0.10": -12.0, "0.25": -27.0, "0.50": -52.0, "1.00": -102.0}
Q_UNKNOWN = {key: "UNKNOWN" for key in Q_F}


def check_record(**edits) -> dict:
    base = {"schema": "sentilab-open-check/1", "W_c_mm": 98.0, "router_status": "optimal", "q_r_nominal": Q_F,
            "labels": LABELS4, "codes": []}
    return copy.deepcopy(base | edits)          # never an alias of a shared module value


def check_records() -> list:
    rev3_example = {"schema": "sentilab-open-check/1", "W_c_mm": 18155.8, "router_status": "optimal",
                    "q_r_nominal": {"0": 1738.3, "0.10": 96.55, "0.25": -2366.1},
                    "labels": ["routed wire only", "nominal", "not a score"]}
    conformed = rev3_example | {"labels": LABELS4, "codes": [], "q_r_nominal": {
        "0": 1738.3, "0.10": 96.55, "0.25": -2366.075, "0.50": -6470.45, "1.00": -14679.2}}
    unfinished = {"router_status": "not_routed", "W_c_mm": "UNKNOWN", "q_r_nominal": Q_UNKNOWN}
    return [
        rec("check", "valid: routed (W_R 100 mm, so q_r = W - (1 + r) 100)", check_record(), manifest="F"),
        rec("check", "valid: the solver limit ended it", check_record(
            router_status="time_limit", W_c_mm="UNKNOWN", q_r_nominal=Q_UNKNOWN,
            codes=[C("check_unfinished", limit="solver_time_limit_s")]), manifest="F"),
        rec("check", "valid: the wall ended it", check_record(
            **unfinished, codes=[C("check_unfinished", limit="check_wall_s")]), manifest="F"),
        rec("check", "valid: the CPU reserve ended it", check_record(
            **unfinished, codes=[C("check_unfinished", limit="cpu_reserve_s")]), manifest="F"),
        rec("check", "valid: rejected before routing", check_record(
            **unfinished, codes=[C("lattice", dies=[0], amount_um=250)]), manifest="F"),
        rec("check", "valid: over the request quota", check_record(
            **unfinished, codes=[C("rate_limited", retry_after="2026-11-01T11:00:00Z")]), manifest="F"),
        rec("check", "the rev 3 section 10 example, verbatim: three labels and no codes", rev3_example,
            [S("/codes", "required"), S("/labels", "const")], manifest="A"),
        rec("check", "valid: the rev 3 example, conformed (q_0.25 exact: -2366.075)", conformed, manifest="A"),
        rec("check", "the example's rounded q_0.25 is not the exact value",
            conformed | {"q_r_nominal": conformed["q_r_nominal"] | {"0.25": -2366.1}},
            [R("check.q_r_values", "/q_r_nominal")], manifest="A"),
        rec("check", "q_r keys: r = 0, the tolerance and every budget",
            check_record(q_r_nominal={key: value for key, value in Q_F.items() if key != "0.05"}),
            [R("check.q_r_keys", "/q_r_nominal")], manifest="F"),
        rec("check", "q_r values follow W(c)", check_record(q_r_nominal=Q_F | {"0": -2.5}),
            [R("check.q_r_values", "/q_r_nominal")], manifest="F"),
        rec("check", "an unknown W gives unknown q_r", check_record(
            **unfinished | {"q_r_nominal": Q_F}, codes=[C("check_unfinished", limit="check_wall_s")]),
            [R("check.q_r_values", "/q_r_nominal")], manifest="F"),
        rec("check", "the solver limit is not the wall", check_record(
            router_status="time_limit", W_c_mm="UNKNOWN", q_r_nominal=Q_UNKNOWN,
            codes=[C("check_unfinished", limit="check_wall_s")]), [R("check.codes", "/codes")], manifest="F"),
        rec("check", "an unfinished check names one limit", check_record(
            **unfinished, codes=[C("check_unfinished", limit="check_wall_s"),
                                 C("check_unfinished", limit="cpu_reserve_s")]),
            [R("check.codes", "/codes")], manifest="F"),
        rec("check", "an evaluation code is not a check code", check_record(
            **unfinished, codes=[C("timeout")]), [R("check.codes", "/codes")], manifest="F"),
        rec("check", "a routed result has no codes", check_record(codes=[C("router_timeout")]),
            [S("/codes", "maxItems")], manifest="F"),
        rec("check", "no proven optimum, no number", check_record(router_status="time_limit",
                                                                   codes=[C("check_unfinished",
                                                                            limit="solver_time_limit_s")]),
            [S("/W_c_mm", "const")], manifest="F"),
        rec("check", "a code carries exactly its fields", check_record(
            **unfinished, codes=[C("lattice", dies=[0])]), [R("violation.fields", "/codes/0")], manifest="F"),
        rec("check", "no geometry in a check result", check_record(dies=TEST_LAYOUT),
            [{"code": "unknown_field", "path": ""}], manifest="F"),
    ]


BODY_PUB = h.body_sha256(text(P_PUB))
VALUES_PUB = h.conductor_geometry(P_PUB, F)
PREF_HUMAN = h.participant_ref(K_CHALLENGE, HUMAN)
PREF_AGENT = h.participant_ref(K_CHALLENGE, AGENT_ACCOUNT)


def receipt(**edits) -> dict:
    base = {"schema": "sentilab-open-receipt/1", "participant_ref": PREF_HUMAN, "source_ref": h.source_ref(ACTIONS[0]),
            "actor_kind": "human", "body_sha256": BODY_PUB, "proposal_sha256": h.proposal_sha256(P_PUB),
            "geometry_sha256": P_PUB["geometry_sha256"], "design_hash": None, "manifest_id": ID["F"],
            "terms": TERMS_VERSION, "visibility": "public", "proposal_key": "t-1", "revision_index": 1,
            "parent": None, "state": "queued", "codes": [], "values": VALUES_PUB}
    return copy.deepcopy(base | edits)          # never an alias of a shared module value


UNREAD = {"proposal_sha256": None, "geometry_sha256": None, "design_hash": None, "terms": None, "visibility": None,
          "proposal_key": None, "revision_index": None, "parent": None, "values": None}
CTX = {"manifest": "F", "item": "P_PUB", "action_id": ACTIONS[0], "account_id": HUMAN, "k_challenge": True}


def receipt_records() -> list:
    design = {"design_hash": fake("design")}
    valid = [
        ("queued", receipt()),
        ("evaluating", receipt(state="evaluating")),
        ("evaluated", receipt(state="evaluated", **design)),
        ("evaluated, W unknown", receipt(state="evaluated", codes=[C("router_timeout")], **design)),
        ("replaying", receipt(state="replaying", **design)),
        ("reproduced", receipt(state="reproduced", **design)),
        ("cross_checked", receipt(state="cross_checked", **design)),
        ("failed before a design hash", receipt(state="failed", codes=[C("timeout")])),
        ("failed after evaluation", receipt(state="failed", codes=[C("interrupted")], **design)),
        ("not_reproduced", receipt(state="not_reproduced", codes=[C("reproduction_mismatch")], **design)),
        ("rejected after parsing", receipt(state="rejected", codes=[C("lattice", dies=[0], amount_um=250)])),
        ("rejected before parsing: no proposal fields", receipt(state="rejected", codes=[C("malformed_json")],
                                                                **UNREAD)),
        ("cancelled: the participant was removed", receipt(state="cancelled", codes=[C("participant_removed")])),
        ("expired", receipt(state="expired")),
        ("as the agent stamped it", receipt(actor_kind="agent", participant_ref=PREF_AGENT,
                                            source_ref=h.source_ref(ACTIONS[1]))),
    ]
    out = [rec("receipt", "valid: " + name, record, manifest="F", item="P_PUB") for name, record in valid]
    out.append(rec("receipt", "valid: refs recomputed from the restricted row", receipt(), **CTX))
    bad = [
        ("a rejection names its codes", receipt(state="rejected"), [R("state.codes", "/codes")]),
        ("a failure has one failure code", receipt(state="failed", codes=[C("timeout"), C("stopped")]),
         [R("state.codes", "/codes")]),
        ("router_timeout is not a failure", receipt(state="failed", codes=[C("router_timeout")]),
         [R("state.codes", "/codes")]),
        ("an evaluation carries no rejection code", receipt(state="evaluated", codes=[C("lattice", dies=[0],
                                                                                        amount_um=250)], **design),
         [R("state.codes", "/codes")]),
        ("a queued entry has no codes", receipt(codes=[C("queue_full", retry_after="2026-11-01T11:00:00Z")]),
         [R("state.codes", "/codes")]),
        ("a cancellation carries policy codes only", receipt(state="cancelled", codes=[C("timeout")]),
         [R("state.codes", "/codes")]),
        ("unread fields stay null", receipt(state="rejected", codes=[C("malformed_json")], **UNREAD | {
            "terms": TERMS_VERSION}), [R("receipt.proposal_fields", "/terms")]),
        ("a parsed proposal names its terms", receipt(terms=None),
         [R("receipt.proposal_fields", "/terms"), R("ref.proposal", "/proposal_sha256", "ref_mismatch")]),
        ("only a rejection may lack its proposal", receipt(**UNREAD),
         [R("receipt.proposal_fields", "/proposal_sha256")]),
        ("an evaluated entry has a design hash", receipt(state="evaluated"), [R("receipt.design_hash", "/design_hash")]),
        ("a queued entry has none yet", receipt(**design), [R("receipt.design_hash", "/design_hash")]),
        ("a code carries exactly its fields", receipt(state="rejected", codes=[C("lattice", dies=[0])]),
         [R("violation.fields", "/codes/0")]),
        ("no label ever names a participant", receipt(label="Team Example 7"), [{"code": "unknown_field", "path": ""}]),
        ("no account id in a receipt", receipt(account_id=HUMAN), [{"code": "unknown_field", "path": ""}]),
    ]
    out += [rec("receipt", name, record, expected, manifest="F", item="P_PUB") for name, record, expected in bad]
    out += [
        rec("receipt", "the manifest id is the manifest's", receipt(manifest_id=ID["A"]),
            [R("record.manifest", "/manifest_id")], manifest="F", item="P_PUB"),
        rec("receipt", "the geometry hash is the proposal's", receipt(geometry_sha256=P_CHILD["geometry_sha256"]),
            [R("ref.geometry", "/geometry_sha256", "ref_mismatch")], manifest="F", item="P_PUB"),
        rec("receipt", "the proposal hash is the proposal's", receipt(proposal_sha256=h.proposal_sha256(P_CHILD)),
            [R("ref.proposal", "/proposal_sha256", "ref_mismatch")], manifest="F", item="P_PUB"),
        rec("receipt", "values.geometry is the conductor's", receipt(values=h.conductor_geometry(P_CHILD, F)),
            [R("ref.values", "/values", "ref_mismatch")], manifest="F", item="P_PUB"),
        rec("receipt", "source_ref is recomputed from the action id", receipt(source_ref=h.source_ref(ACTIONS[1])),
            [R("ref.source", "/source_ref", "ref_mismatch")], **CTX),
        rec("receipt", "participant_ref is keyed: an unkeyed hash is refused",
            receipt(participant_ref=hashlib.sha256(HUMAN.encode()).hexdigest()),
            [R("ref.participant", "/participant_ref", "ref_mismatch")], **CTX),
        rec("receipt", "a private entry's receipt carries its handle: never in a public record set",
            receipt(proposal_sha256=h.proposal_sha256(P_PRIV), visibility="private", proposal_key="t-2",
                    body_sha256=fake("ciphertext")),
            [R("privacy.handle", "")], private_handles=[h.proposal_sha256(P_PRIV)]),
    ]
    return out


def status_receipt(**edits) -> dict:
    base = {"participant_ref": PREF_HUMAN, "actor_kind": "human", "state": "queued",
            "queue": {"position": 3, "estimated_start": "2026-11-01T10:30:00Z"}, "receipt_hash": fake("receipt"),
            "run_id": h.run_id(ID["F"], PREF_HUMAN, h.proposal_sha256(P_PUB))}
    return copy.deepcopy(base | edits)          # never an alias of a shared module value


def status(*receipts) -> dict:
    return {"schema": "sentilab-open-status/1", "receipts": list(receipts)}


def status_records() -> list:
    ctx = {"manifest": "F", "proposal_sha256": h.proposal_sha256(P_PUB)}
    return [
        rec("status", "valid: queued, in the rev 3 section 10 shape", status(status_receipt()), **ctx),
        rec("status", "valid: no estimate yet", status(status_receipt(queue={"position": 1, "estimated_start": None})),
            **ctx),
        rec("status", "valid: evaluated, and as the agent", status(
            status_receipt(state="evaluated", queue=None),
            status_receipt(participant_ref=PREF_AGENT, actor_kind="agent", state="reproduced", queue=None,
                           run_id=h.run_id(ID["F"], PREF_AGENT, h.proposal_sha256(P_PUB)))), **ctx),
        rec("status", "the run id is the account's: the same bytes from another account have another run",
            status(status_receipt(participant_ref=PREF_AGENT, actor_kind="agent", state="evaluated", queue=None)),
            [R("ref.run_id", "/receipts/0/run_id", "ref_mismatch")], **ctx),
        rec("status", "a queue position only while queued", status(status_receipt(state="evaluating")),
            [R("status.queue", "/receipts/0/queue")], **ctx),
        rec("status", "a queued entry has its position", status(status_receipt(queue=None)),
            [R("status.queue", "/receipts/0/queue")], **ctx),
        rec("status", "the run id is the proposal's", status(status_receipt(
            run_id=h.run_id(ID["F"], PREF_HUMAN, h.proposal_sha256(P_CHILD)))), [R("ref.run_id", "/receipts/0/run_id",
                                                                         "ref_mismatch")], **ctx),
        rec("status", "the codes are in the receipt, not here", status(status_receipt(codes=[])),
            [{"code": "unknown_field", "path": "/receipts/0"}], **ctx),
    ]


def measured(**edits) -> dict:
    base = {"T_M": 59.5, "delta_T": -0.5, "W_c_mm": 98.0, "q_r": Q_F,
            "labels": [{"id": "declared temperature target", "r": None, "mode": PASSES},
                       {"id": "strict-wire thermal tolerance", "r": None, "mode": PASSES},
                       {"id": "r-relaxed-wire thermal tolerance", "r": 0.05, "mode": PASSES},
                       {"id": "strict wire improvement", "r": None, "mode": PASSES},
                       {"id": "wire improvement with allowed thermal degradation", "r": None, "mode": PASSES},
                       {"id": "robust dominance over R", "r": None, "mode": PASSES}],
            "suppressed": [], "sensitivities": {"mesh": 0.1, "position": "UNKNOWN", "replay": 0.0},
            "observables": {"active_layer_grid_peak": 60.1, "literal_on_stdout": 59.9, "W_proxy_mm": 5.2},
            "evaluator": FIXTURE, "temperature_label": "illustrative"}
    return copy.deepcopy(base | edits)          # never an alias of a shared module value


PASSES = "passes the listed sensitivity cases"
UNKNOWN_ROW = {"T_M": "UNKNOWN", "delta_T": "UNKNOWN", "W_c_mm": "UNKNOWN", "q_r": Q_UNKNOWN, "labels": [],
               "suppressed": [], "sensitivities": {"mesh": "UNKNOWN", "position": "UNKNOWN", "replay": "UNKNOWN"},
               "observables": {"active_layer_grid_peak": "UNKNOWN", "literal_on_stdout": "UNKNOWN",
                               "W_proxy_mm": "UNKNOWN"}, "evaluator": None, "temperature_label": None}


def outside(**edits) -> dict:
    return {"kind": "outside", "participant_ref": PREF_HUMAN, "actor_kind": "human", "state": "reproduced",
            **measured()} | copy.deepcopy(edits)


def results(*rows, comparator=None, private_entries=2) -> dict:
    return {"schema": "sentilab-open-results/1",
            "comparator": comparator or {"id": "test-two-die-ref/raw", "T_R": 60.0, "W_R_mm": 100.0,
                                         "evaluator": FIXTURE, "temperature_label": "illustrative"},
            "rows": list(rows), "private_entries": private_entries}


def results_records() -> list:
    target = {"kind": "published_target", "source": "illustrative fixture: no paper", "T_c": 60.5, "W_mm": 101,
              "use": "paper target, not our evaluation"}
    baseline = {"kind": "baseline", **measured()}
    variant = {"kind": "engineering_variant", "id": "test-two-die-ref-snap0p5", "content_sha256": fake("snapped reference"),
               "receipt_hash": fake("variant receipt"), **measured()}
    unknown_r = {"id": "test-two-die-ref/raw", "T_R": "UNKNOWN", "W_R_mm": 100.0, "evaluator": None,
                 "temperature_label": None}
    rev3_example = {"schema": "sentilab-open-results/1",
                    "comparator": {"id": "ascend910-tap25d-fig6a/raw", "T_R": "UNKNOWN", "W_R_mm": 16417.5},
                    "rows": [{"kind": "outside", "participant_ref": PREF_HUMAN, "state": "reproduced", "T_M": 75.2,
                              "delta_T": 0.1, "q_r": {"0": 1738.3},
                              "labels": [{"id": "r-relaxed-wire thermal tolerance", "r": 0.05, "mode": PASSES}],
                              "sensitivities": {"mesh": 0.2, "position": "UNKNOWN", "replay": 0.0}}]}
    relaxed_only = [{"id": "r-relaxed-wire thermal tolerance", "r": 0.05, "mode": PASSES}]
    return [
        rec("results", "valid: every row kind", results(target, baseline, variant, outside()), manifest="F"),
        rec("results", "valid: delta_T exact in decimal (59.7 - 60.0 = -0.3)", results(outside(T_M=59.7, delta_T=-0.3)),
            manifest="F"),
        rec("results", "valid: an entry still queued shows no values", results(outside(state="queued", **UNKNOWN_ROW)),
            manifest="F"),
        rec("results", "valid: T_R unknown leaves delta_T unknown and only the target claimable", results(outside(
            delta_T="UNKNOWN", labels=[{"id": "declared temperature target", "r": None, "mode": PASSES}]),
            comparator=unknown_r)),
        rec("results", "valid: claims beside a suppressed one", results(outside(
            labels=relaxed_only, suppressed=[{"id": "strict-wire thermal tolerance", "r": None,
                                              "by": "failed required scenario"}])), manifest="F"),
        rec("results", "valid: INCOMPLETE and UNKNOWN are shown with their values", results(outside(labels=[
            {"id": "declared temperature target", "r": None, "mode": "INCOMPLETE"},
            {"id": "robust dominance over R", "r": None, "mode": "UNKNOWN"}])), manifest="F"),
        rec("results", "the rev 3 section 10 example, filled in: our added fields are required", rev3_example,
            [S("/comparator/evaluator", "required"), S("/comparator/temperature_label", "required"),
             S("/private_entries", "required"), S("/rows/0", "oneOf")]),
        rec("results", "delta_T reads UNKNOWN while T_R does, never zero", results(outside(delta_T=0.0, labels=[]),
                                                                                 comparator=unknown_r),
            [R("results.delta_t", "/rows/0/delta_T")]),
        rec("results", "delta_T is T_M(c) - T_M(R), exactly", results(outside(delta_T=-0.4)),
            [R("results.delta_t", "/rows/0/delta_T")], manifest="F"),
        rec("results", "labels in display order", results(outside(labels=list(reversed(measured()["labels"])))),
            [R("results.label_set", "/rows/0/labels")], manifest="F"),
        rec("results", "a claim is shown or suppressed, not both", results(outside(
            labels=relaxed_only, suppressed=[{"id": "r-relaxed-wire thermal tolerance", "r": 0.05,
                                              "by": "failed binding"}])),
            [R("results.label_set", "/rows/0/labels")], manifest="F"),
        rec("results", "the relaxed label carries r", results(outside(labels=[
            {"id": "r-relaxed-wire thermal tolerance", "r": None, "mode": PASSES}])),
            [R("results.label_r", "/rows/0/labels")], manifest="F"),
        rec("results", "a strict label carries no r", results(outside(labels=[
            {"id": "strict-wire thermal tolerance", "r": 0.05, "mode": PASSES}])),
            [R("results.label_r", "/rows/0/labels")], manifest="F"),
        rec("results", "r is the manifest's tolerance", results(outside(labels=[
            {"id": "r-relaxed-wire thermal tolerance", "r": 0.1, "mode": PASSES}])),
            [R("results.label_r", "/rows/0/labels")], manifest="F"),
        rec("results", "no claim on an unknown wire", results(outside(W_c_mm="UNKNOWN", q_r=Q_UNKNOWN,
                                                                      labels=relaxed_only)),
            [R("results.unknown_claim", "/rows/0/labels")], manifest="F"),
        rec("results", "nothing is bounded while every bound is UNKNOWN", results(outside(labels=[
            {"id": "declared temperature target", "r": None, "mode": "bounded"}])),
            [R("results.bounded", "/rows/0/labels")], manifest="F"),
        rec("results", "a withdrawn temperature claims nothing", results(outside(
            evaluator=WITHDRAWN, temperature_label="withdrawn")),
            [R("label.withdrawn_claim", "/rows/0/labels", "label_mismatch")], manifest="F"),
        rec("results", "the label is the evaluator's (SLAB-053)", results(outside(temperature_label="accepted")),
            [R("label.temperature", "/rows/0/temperature_label", "label_mismatch")], manifest="F"),
        rec("results", "an unknown temperature has no label", results(outside(**UNKNOWN_ROW | {
            "temperature_label": "unvalidated", "state": "queued"})),
            [R("label.temperature", "/rows/0/temperature_label", "label_mismatch")], manifest="F"),
        rec("results", "a HotSpot 6.0 value reads unvalidated", results(outside(evaluator="hotspot6:" + HOTSPOT6)),
            [R("label.temperature", "/rows/0/temperature_label", "label_mismatch")], manifest="F"),
        rec("results", "the comparator is the manifest's", results(outside(), comparator={
            "id": "test-two-die-ref/raw", "T_R": 60.5, "W_R_mm": 100.0, "evaluator": FIXTURE,
            "temperature_label": "illustrative"}),
            [R("results.comparator", "/comparator"), R("results.delta_t", "/rows/0/delta_T")], manifest="F"),
        rec("results", "an entry not evaluated has no values", results(outside(state="queued")),
            [R("results.state", "/rows/0/state")], manifest="F"),
        *privacy_cases(),
        rec("results", "q_r follows W(c)", results(outside(q_r=Q_F | {"1.00": -100.0})),
            [R("results.q_r_values", "/rows/0/q_r")], manifest="F"),
        rec("results", "q_r keys: r = 0, the tolerance and every budget", results(outside(
            q_r={key: value for key, value in Q_F.items() if key != "1.00"})),
            [R("results.q_r_keys", "/rows/0/q_r")], manifest="F"),
        rec("results", "private entries are only counted", results(outside(), private_entries=-1),
            [S("/private_entries", "minimum")], manifest="F"),
        rec("results", "a published target is never our evaluation", results(target | {"use": "comparison"}),
            [S("/rows/0", "oneOf")]),
    ]


def privacy_cases() -> list:
    """A private handle hidden anywhere in a public string is refused (privacy.handle): behind a prefix, before a
    suffix, in the middle, in upper case, broken up by separators, or as base64url. The public entry's own hash in
    the same place is fine."""
    spelled = ":".join(PRIV_HANDLE[index:index + 2] for index in range(0, 64, 2))
    variants = [("behind a prefix", "hotspot6:" + PRIV_HANDLE), ("before a suffix", PRIV_HANDLE + ":grid:64"),
                ("in the middle", "hotspot6:" + PRIV_HANDLE + ":grid:64"),
                ("in upper case", "hotspot6:" + PRIV_HANDLE.upper()), ("broken up by separators", "hotspot6:" + spelled),
                ("as base64url", "hotspot6:" + PRIV_B64URL)]
    cases = [rec("results", f"a private handle {name} in a public string", results(outside(
        evaluator=evaluator, temperature_label="unvalidated")), [R("privacy.handle", "")], manifest="F",
        private_handles=[PRIV_HANDLE]) for name, evaluator in variants]
    cases.append(rec("results", "valid: a public entry's own hash in a public string", results(outside(
        evaluator="hotspot6:" + h.proposal_sha256(P_PUB), temperature_label="unvalidated")), manifest="F",
        private_handles=[PRIV_HANDLE]))
    return cases


def other_records() -> list:
    key_object = h.transport_key_object(room=ROOM, account=HUMAN, actor_slot="human", manifest_id=ID["F"],
                                        logical_key="t-1", content_sha256=h.proposal_sha256(P_PUB))
    return [
        rec("geometry", "valid: a geometry preimage", h.geometry_object(P_PUB, F)),
        rec("geometry", "no salt in the geometry", h.geometry_object(P_PUB, F) | {"salt": SALTS[1]},
            [{"code": "unknown_field", "path": ""}]),
        rec("geometry", "no lattice field (rev 3)", h.geometry_object(P_PUB, F) | {"lattice_um": 500},
            [{"code": "unknown_field", "path": ""}]),
        rec("transport_key", "valid: a transport-key preimage", key_object),
        rec("transport_key", "valid: a publish preimage", key_object | {"logical_key": h.logical_key(PUBLISH)}),
        rec("transport_key", "an agent slot names its agent", key_object | {"actor_slot": "agent:"},
            [S("/actor_slot", "pattern")]),
        rec("transport_key", "the logical key is a key", key_object | {"logical_key": "T-1"},
            [S("/logical_key", "pattern")]),
        rec("proposal", "valid: Appendix A's example", P_A),
        rec("proposal", "valid: a public proposal", P_PUB),
        rec("check_request", "valid: a check request", C_PUB),
        rec("team", "valid: a team name", TEAM),
        rec("publish", "valid: a publish choice", PUBLISH),
        rec("publish", "a publish names a proposal hash", PUBLISH | {"proposal_sha256": "t-2"},
            [S("/proposal_sha256", "pattern")]),
        rec("reason_codes", "valid: the 48 codes", json.loads((CONTRACT_DIR / "reason-codes.json").read_bytes())),
    ]


# ── the state machine, the idempotency decisions and the order ─────────────────────────────────────────────────

ALLOWED = {(None, "accept"): "queued", (None, "reject"): "rejected", ("queued", "hold"): "held",
           ("held", "release"): "queued", ("queued", "start"): "evaluating", ("evaluating", "complete"): "evaluated",
           ("evaluating", "fail"): "failed", ("evaluated", "fail"): "failed", ("evaluated", "replay"): "replaying",
           ("replaying", "reproduced"): "reproduced", ("replaying", "not_reproduced"): "not_reproduced",
           ("reproduced", "cross_checked"): "cross_checked", ("queued", "cancel"): "cancelled",
           ("held", "cancel"): "cancelled", ("queued", "expire"): "expired", ("held", "expire"): "expired"}
GOOD_PAYLOAD = {"accept": {}, "reject": {"codes": ["lattice"]}, "hold": {"operator": True},
                "release": {"operator": True}, "start": {"reservation_id": RESERVATION},
                "complete": {"settled": True}, "fail": {"settled": True, "codes": ["timeout"]},
                "replay": {"reservation_id": RESERVATION}, "reproduced": {"settled": True, "fresh_process": True},
                "not_reproduced": {"settled": True, "codes": ["reproduction_mismatch"]},
                "cross_checked": {"settled": True, "tier": "cross_build"}, "cancel": {"codes": ["participant_removed"]},
                "expire": {}, "hide": {"operator": True, "reason": "spam"},
                "restore": {"operator": True, "reason": "reinstated"}, "publish": {"sealed": True}}
SUMMARY_EXPECT = {"rejected": "rejected", "queued": "queued", "held": "queued", "evaluating": "queued",
                  "evaluated": "evaluated", "failed": "evaluated", "replaying": "evaluated",
                  "not_reproduced": "evaluated", "reproduced": "independently verified",
                  "cross_checked": "independently verified", "cancelled": None, "expired": None}
CHARGED_EXPECT = {"rejected": False, "queued": False, "held": False, "evaluating": True, "evaluated": True,
                  "failed": True, "replaying": True, "reproduced": True, "not_reproduced": True,
                  "cross_checked": True, "cancelled": False, "expired": False}


def state_table() -> dict:
    """Every state and event with a good payload. Moderation flags are tried hidden and not; publication is tried on a
    private and on a public entry: only a private entry, once ingested, can be published, and only once."""
    pairs = []
    for state in (None,) + LIFECYCLE:
        for event in tuple(EVENTS) + FLAG_EVENTS:
            if event == "publish":
                for visibility in ("private", "public"):
                    allowed = state is not None and visibility == "private"
                    pairs.append({"state": state, "hidden": None, "visibility": visibility, "event": event,
                                  "payload": GOOD_PAYLOAD[event],
                                  "expect": {"state": state, "hidden": None, "visibility": "public"} if allowed
                                  else None})
            elif event in FLAG_EVENTS:
                for hidden in (None, "spam"):
                    allowed = state is not None and (hidden is None) == (event == "hide")
                    after = ({"state": state, "hidden": "spam" if event == "hide" else None, "visibility": "private"}
                             if allowed else None)
                    pairs.append({"state": state, "hidden": hidden, "visibility": "private", "event": event,
                                  "payload": GOOD_PAYLOAD[event], "expect": after})
            else:
                target = ALLOWED.get((state, event))
                pairs.append({"state": state, "hidden": None, "visibility": "private", "event": event,
                              "payload": GOOD_PAYLOAD[event],
                              "expect": None if target is None else {"state": target, "hidden": None,
                                                                     "visibility": "private"}})
    guards = [
        ("hold needs an operator", "queued", "hold", {}),
        ("start needs a reservation", "queued", "start", {}),
        ("a reservation id is a UUID", "queued", "start", {"reservation_id": "r-1"}),
        ("replay needs a reservation", "evaluated", "replay", {}),
        ("complete needs settlement", "evaluating", "complete", {}),
        ("an evaluation carries qualifier codes only", "evaluating", "complete",
         {"settled": True, "codes": ["lattice"]}),
        ("a failure needs a code", "evaluating", "fail", {"settled": True}),
        ("a failure has one code", "evaluating", "fail", {"settled": True, "codes": ["timeout", "stopped"]}),
        ("router_timeout is not a failure", "evaluating", "fail", {"settled": True, "codes": ["router_timeout"]}),
        ("binding_mismatch is not a failure", "evaluated", "fail", {"settled": True, "codes": ["binding_mismatch"]}),
        ("check_unfinished is a check's code only", "evaluating", "fail",
         {"settled": True, "codes": ["check_unfinished"]}),
        ("a failure is settled", "evaluating", "fail", {"codes": ["timeout"]}),
        ("a rejection needs codes", None, "reject", {}),
        ("a rejection needs rejection codes", None, "reject", {"codes": ["timeout"]}),
        ("reproduction needs a fresh process", "replaying", "reproduced", {"settled": True}),
        ("a failed reproduction needs its code", "replaying", "not_reproduced", {"settled": True, "codes": ["timeout"]}),
        ("a cross-check is cross_build or cross_arch, never cross_solver", "reproduced", "cross_checked",
         {"settled": True, "tier": "cross_solver"}),
        ("replayed is not a cross-check", "reproduced", "cross_checked", {"settled": True, "tier": "replayed"}),
        ("a cancellation carries policy codes only", "queued", "cancel", {"codes": ["timeout"]}),
        ("accept carries no codes", None, "accept", {"codes": ["lattice"]}),
        ("codes are a list", None, "reject", {"codes": "lattice"}),
        ("codes are code names", None, "reject", {"codes": [{"code": "lattice"}]}),
        ("a tier is a name", "reproduced", "cross_checked", {"settled": True, "tier": ["cross_build"]}),
        ("a moderation reason is a name", "evaluated", "hide", {"operator": True, "reason": ["spam"]}),
        ("hiding needs a moderation reason", "evaluated", "hide", {"operator": True, "reason": "rude"}),
        ("restoring needs its reason", "evaluated", "restore", {"operator": True, "reason": "spam"}),
        ("hiding is an operator's", "evaluated", "hide", {"reason": "spam"}),
        ("an unknown event", "queued", "requeue", {"operator": True}),
        ("publication is a sealed command", "evaluated", "publish", {}),
        ("a publication refused for its terms changes nothing", "evaluated", "publish",
         {"sealed": True, "codes": ["terms_not_accepted"]}),
        ("a publication refused for ownership changes nothing", "reproduced", "publish",
         {"sealed": True, "codes": ["unknown_proposal"]}),
    ]
    return {"pairs": pairs,
            "guards": [{"name": name, "state": state, "hidden": "spam" if event == "restore" else None,
                        "visibility": "private", "event": event, "payload": payload}
                       for name, state, event, payload in guards],
            "summary": SUMMARY_EXPECT, "charged": CHARGED_EXPECT}


def prior(kind, key, item, order, geometry=None) -> dict:
    return {"kind": kind, "logical_key": key, "content_sha256": h.content_sha256(item),
            "geometry_sha256": geometry, "order": order}


def revisions() -> list:
    first = prior("proposal", "t-1", P_PUB, [1], P_PUB["geometry_sha256"])
    check = prior("check_request", "c-1", C_PUB, [2], C_PUB["geometry_sha256"])
    team = prior("team", "team", TEAM, [3])
    other = changed(P_PUB, salt=SALTS[6])
    cases = [
        ("the first proposal", [], "proposal", "t-1", P_PUB, None, [1], {"kind": "new", "revision_index": 1,
                                                                         "codes": []}),
        ("the same key and content: a duplicate, the same receipt", [first], "proposal", "t-1", P_PUB, None, [5],
         {"kind": "duplicate", "revision_index": 1, "codes": []}),
        ("the same key, other content: idempotency_conflict, the earliest wins", [first], "proposal", "t-1", other,
         None, [5], {"kind": "new", "revision_index": 2, "codes": ["idempotency_conflict"]}),
        ("another key: a new revision", [first], "proposal", "t-3", P_CHILD, P_PUB["geometry_sha256"], [5],
         {"kind": "new", "revision_index": 2, "codes": []}),
        ("a parent that is no earlier geometry of the account", [first], "proposal", "t-3", P_CHILD, "0" * 64, [5],
         {"kind": "new", "revision_index": 2, "codes": ["unknown_parent"]}),
        ("a check request's geometry is no parent", [check], "proposal", "t-3", P_CHILD, C_PUB["geometry_sha256"],
         [5], {"kind": "new", "revision_index": 1, "codes": ["unknown_parent"]}),
        ("a conflict and an unknown parent together", [first], "proposal", "t-1", other, "0" * 64, [5],
         {"kind": "new", "revision_index": 2, "codes": ["idempotency_conflict", "unknown_parent"]}),
        ("kinds do not collide: a request_key equal to a proposal_key", [first], "check_request", "t-1", C_PUB, None,
         [5], {"kind": "new", "revision_index": 1, "codes": []}),
        ("a check request's own conflict", [check], "check_request", "c-1", changed(C_PUB, salt=SALTS[7]), None, [5],
         {"kind": "new", "revision_index": 2, "codes": ["idempotency_conflict"]}),
        ("the same team name: a duplicate", [team], "team", "team", TEAM, None, [5],
         {"kind": "duplicate", "revision_index": 1, "codes": []}),
        ("a changed team name: idempotency_conflict", [team], "team", "team", changed(TEAM, name="Team Example 8"),
         None, [5], {"kind": "new", "revision_index": 2, "codes": ["idempotency_conflict"]}),
    ]
    out = [{"name": name, "decide": "revision", "history": history, "kind": kind, "logical_key": key,
            "content_sha256": h.content_sha256(item), "parent": parent, "order": order, "expect": expected}
           for name, history, kind, key, item, parent, order, expected in cases]
    out += [
        {"name": "history out of order", "decide": "revision", "history": [prior("proposal", "t-1", P_PUB, [3]),
                                                                           prior("proposal", "t-3", P_CHILD, [2])],
         "kind": "proposal", "logical_key": "t-4", "content_sha256": fake("content"), "parent": None, "order": [9],
         "expect": "order_error"},
        {"name": "a row decided before an earlier one", "decide": "revision", "history": [first], "kind": "proposal",
         "logical_key": "t-4", "content_sha256": fake("content"), "parent": None, "order": [0],
         "expect": "order_error"},
        {"name": "publish: one of the account's own proposals", "decide": "publish",
         "history": [prior("proposal", "t-2", P_PRIV, [1])], "proposal_sha256": h.proposal_sha256(P_PRIV),
         "order": [5], "expect": []},
        {"name": "publish: no such proposal of this account", "decide": "publish", "history": [first],
         "proposal_sha256": h.proposal_sha256(P_PRIV), "order": [5], "expect": ["unknown_proposal"]},
        {"name": "publish: a check request is not a proposal", "decide": "publish", "history": [check],
         "proposal_sha256": h.content_sha256(C_PUB), "order": [5], "expect": ["unknown_proposal"]},
    ]
    return out


def ordering() -> dict:
    rows = [("the same instant and action, overflow room", "2026-10-31T16:05:12Z", ACTIONS[2], OVERFLOW_ROOM),
            ("whole second", "2026-10-31T16:05:12+00:00", ACTIONS[1], ROOM),
            ("one microsecond later, but sorts first as text", "2026-10-31T16:05:12.000001+00:00", ACTIONS[0], ROOM),
            ("the same instant as Z, later action id", "2026-10-31T16:05:12Z", ACTIONS[2], ROOM),
            ("a second earlier, written in another zone", "2026-10-31T17:05:11+01:00", ACTIONS[3], ROOM)]
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


# ── canonical, hash, key and sealing vectors (T1) ───────────────────────────────────────────────────────────────

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
OBJECTS = {"P_A": P_A, "P_PUB": P_PUB, "P_PRIV": P_PRIV, "P_CHILD": P_CHILD, "P_PRIV_F2": P_PRIV_F2, "C_PUB": C_PUB,
           "C_PRIV": C_PRIV, "TEAM": TEAM, "PUBLISH": PUBLISH}
ARMOUR_REFUSALS = [
    ("CRLF line ends", lambda armour: armour.replace(b"\n", b"\r\n")),
    ("a missing END line", lambda armour: armour[:armour.rindex(b"-----END")]),
    ("text after END", lambda armour: armour + b"trailing\n"),
    ("two body lines joined", lambda armour: armour.replace(b"\n", b"", 2).replace(b"-----BEGIN AGE ENCRYPTED FILE-----",
                                                                            b"-----BEGIN AGE ENCRYPTED FILE-----\n",
                                                                            1)),
]


NOTE_REFUSALS = [
    ("a key version with a leading zero", lambda note: note.replace(b" 1\n", b" 01\n", 1)),
    ("an upper-case manifest id", lambda note: note[:23] + note[23:87].upper() + note[87:]),
    ("another schema", lambda note: note.replace(b"sentilab-open-sealed/1", b"sentilab-open-sealed/2", 1)),
    ("no line feed after the first line", lambda note: note.replace(b" 1\n", b" 1 ", 1)),
    ("a seven-digit key version", lambda note: note.replace(b" 1\n", b" 1000000\n", 1)),
]


RUN_CASES = [("one account, a public proposal", "P_PUB", PREF_HUMAN),
             ("the same bytes from another account: another run, the same evaluation cache key", "P_PUB", PREF_AGENT),
             ("one account, a private proposal", "P_PRIV", PREF_HUMAN)]


def run_id_refusals() -> list:
    """Inputs both the Python reference and the JavaScript twin refuse: every digest is checked in full."""
    proposal, manifest = h.proposal_sha256(P_PUB), ID["F"]
    return [("an upper-case manifest id", manifest.upper(), PREF_HUMAN, proposal),
            ("a 63-character proposal hash", manifest, PREF_HUMAN, proposal[:63]),
            ("a valid 16-hex prefix with a non-hex suffix", manifest, PREF_HUMAN, proposal[:16] + "z" * 48),
            ("a non-hex participant reference", manifest, "g" * 64, proposal),
            ("a 65-character manifest id", manifest + "0", PREF_HUMAN, proposal)]


def vectors() -> dict:
    transport_cases = [("P_PUB", ROOM, HUMAN, "human", None), ("P_PUB", ROOM, AGENT_ACCOUNT, "agent", AGENT_ID),
                       ("P_PUB", OVERFLOW_ROOM, HUMAN, "human", None), ("P_PRIV", ROOM, HUMAN, "human", None),
                       ("P_CHILD", ROOM, HUMAN, "human", None), ("C_PUB", ROOM, HUMAN, "human", None),
                       ("C_PRIV", ROOM, AGENT_ACCOUNT, "agent", AGENT_ID), ("TEAM", ROOM, HUMAN, "human", None),
                       ("PUBLISH", ROOM, HUMAN, "human", None)]
    sealed_cases = []
    for case in AGE_VECTORS["cases"]:
        note = case["note"].encode("ascii")
        manifest_id, key_version, age_file = age_tools.parse_note(note)
        sealed_cases.append({"id": case["id"], "note": case["note"], "manifest_id": manifest_id,
                             "key_version": key_version, "age_file_sha256": hashlib.sha256(age_file).hexdigest()})
    first = AGE_VECTORS["cases"][0]["note"].encode("ascii")
    armour = armour_of(first)
    return {
        "schema": "sentilab-open-vectors/1",
        "test_phrases": {"k_challenge": K_PHRASE, "derivation": "sha256 of the UTF-8 phrase gives the 32 bytes"},
        "canonical": [{"name": name, "value": value, "canonical": expected,
                       "sha256": hashlib.sha256(expected.encode()).hexdigest()} for name, value, expected in CANONICAL],
        "manifest_id": [{"manifest": key, "manifest_id": ID[key]} for key in MANIFESTS],
        "objects": OBJECTS,
        "geometry": [{"object": name, "manifest": key, "preimage": h.geometry_object(OBJECTS[name], MANIFESTS[key]),
                      "canonical": h.canonical(h.geometry_object(OBJECTS[name], MANIFESTS[key])).decode(),
                      "geometry_sha256": h.geometry_sha256(OBJECTS[name], MANIFESTS[key])}
                     for name, key in (("P_A", "A"), ("P_PUB", "F"), ("P_PRIV", "F"), ("C_PRIV", "F"))],
        "content": [{"object": name, "canonical": h.canonical(value).decode(), "content_sha256": h.content_sha256(value),
                     "logical_key": h.logical_key(value)} for name, value in OBJECTS.items()],
        "body_sha256": [{"note_b64": base64.b64encode(note).decode(), "body_sha256": h.body_sha256(note)}
                        for note in (text(P_PUB), text(P_PUB) + b"\n", fenced(P_PUB))],
        "source_ref": [{"action_id": action, "source_ref": h.source_ref(action)} for action in ACTIONS[:2]],
        "participant_ref": [{"account_id": account, "participant_ref": h.participant_ref(K_CHALLENGE, account)}
                            for account in (HUMAN, AGENT_ACCOUNT)],
        "actor_slot": [{"actor_kind": "human", "actor_id": None, "actor_slot": "human"},
                       {"actor_kind": "agent", "actor_id": AGENT_ID, "actor_slot": "agent:" + AGENT_ID}],
        "transport_key": [
            {"object": name, "room": room, "account": account, "actor_kind": kind, "actor_id": agent,
             "preimage": h.transport_key_object(room=room, account=account, actor_slot=h.actor_slot(kind, agent),
                                                manifest_id=OBJECTS[name]["manifest_id"],
                                                logical_key=h.logical_key(OBJECTS[name]),
                                                content_sha256=h.content_sha256(OBJECTS[name])),
             "transport": h.transport_key_for(OBJECTS[name], room=room, account=account, actor_kind=kind,
                                              actor_id=agent)}
            for name, room, account, kind, agent in transport_cases],
        "run_id": [{"case": case, "manifest_id": ID["F"], "participant_ref": ref,
                    "proposal_sha256": h.proposal_sha256(OBJECTS[name]),
                    "preimage": h.run_id_object(ID["F"], ref, h.proposal_sha256(OBJECTS[name])),
                    "run_id": h.run_id(ID["F"], ref, h.proposal_sha256(OBJECTS[name])),
                    "evaluation_cache_key": list(h.evaluation_cache_key(ID["F"], OBJECTS[name]["geometry_sha256"]))}
                   for case, name, ref in RUN_CASES],
        "run_id_refused": [{"name": name, "manifest_id": manifest_id, "participant_ref": ref,
                            "proposal_sha256": proposal_sha256}
                           for name, manifest_id, ref, proposal_sha256 in run_id_refusals()],
        "terms_path": [{"version": version, "path": h.terms_path(version)} for version in (TERMS_VERSION, OTHER_TERMS)],
        "terms_path_refused": ["sentilab-open-terms/0@" + "0" * 64, "sentilab-open-terms/1@" + "0" * 63,
                               "sentilab-open-terms/1", "open-terms/1@" + "0" * 64],
        "sealed_header": [{"manifest_id": ID[key], "key_version": version,
                           "line": h.sealed_header(ID[key], version)} for key, version in (("F", 1), ("F2", 2))],
        "sealed_notes": sealed_cases,
        "armour_refusals": [{"name": name, "armour_b64": base64.b64encode(change(armour)).decode()}
                            for name, change in ARMOUR_REFUSALS],
        "sealed_note_refusals": [{"name": name, "note_b64": base64.b64encode(change(first)).decode()}
                                 for name, change in NOTE_REFUSALS],
        "patterns": pattern_cases(),
        "r_key": [{"r": r, "key": h.r_key(r)} for r in (0, 0.05, 0.1, 0.25, 0.5, 1.0)],
        "r_key_refused": [0.125, -0.1],
        "q_r": [{"W_c_mm": 18155.8, "W_R_mm": 16417.5, "key": key, "q_r": h.q_r(18155.8, 16417.5, key)}
                for key in ("0", "0.10", "0.25", "0.50", "1.00")],
        "conductor_geometry": [{"object": name, "manifest": key,
                                "values": h.conductor_geometry(OBJECTS[name], MANIFESTS[key])}
                               for name, key in (("P_A", "A"), ("P_PUB", "F"))]}


# A known-good sample for every schema pattern: the meta tests and the cross-language pattern vectors use it.
PATTERN_SAMPLES = {
    r"^(/[A-Za-z0-9_]{1,64})*$": "/ab", r"^(0|[0-9]{1,2}\.[0-9]{2})$": "0.10",
    r"^([a-z0-9][a-z0-9_-]{0,63}|publish:[0-9a-f]{64})$": "ab", r"^(human|agent:[A-Za-z0-9][A-Za-z0-9._-]{0,119})$":
        "agent:ab",
    r"^(provisional|frozen)( \([A-Za-z0-9 ,/#-]{1,64}\))?$": "frozen", r"^Chiplet_[0-9]{1,2}$": "Chiplet_0",
    r"^P(?=[0-9])([0-9]{1,4}Y)?([0-9]{1,4}M)?([0-9]{1,5}D)?$": "P2Y",
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$": "2026-11-01T00:00:00Z",
    r"^[0-9a-f]{32}$": "0" * 32, r"^[0-9a-f]{40}$": "0" * 40, r"^[0-9a-f]{64}$": "0" * 64,
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$": HUMAN,
    r"^[A-Za-z0-9._-]{1,32}$": "ab", r"^[A-Za-z0-9][A-Za-z0-9 .,:;()-]{0,127}$": "ab",
    r"^[A-Za-z0-9][A-Za-z0-9 .,:;()-]{0,511}$": "ab", r"^[A-Za-z0-9][A-Za-z0-9 .,:;()/+_-]{0,127}$": "ab",
    "^[A-Za-z0-9][A-Za-z0-9 .,:;()/+_" + chr(0x2026) + "-]{0,127}$": "ab",
    r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,31}$": "ab", r"^[A-Za-z0-9][A-Za-z0-9._+:=-]{0,319}$": "ab",
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$": "ab", r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$": "ab",
    r"^[A-Za-z0-9_][A-Za-z0-9_./-]{0,127}$": "ab", r"^[A-Za-z][A-Za-z0-9_]{0,31}$": "ab", r"^[A-Za-z]{1,32}$": "ab",
    r"^[a-z0-9][a-z0-9_-]{0,63}$": "ab", r"^[a-z0-9][a-z0-9_.-]{0,63}(/[a-z0-9][a-z0-9_.-]{0,63})?$": "ab",
    r"^[a-z0-9_-]{1,32}$": "ab", r"^age1[02-9ac-hj-np-z]{58}$": "age1" + "q" * 58,
    r"^open-[0-9a-f]{8}-[0-9a-f]{32}$": "open-" + "0" * 8 + "-" + "0" * 32,
    r"^position-[0-9]{1,2}-[xy]-(plus|minus)$": "position-0-x-plus",
    r"^sentilab-open-terms/[1-9][0-9]{0,5}@[0-9a-f]{64}$": "sentilab-open-terms/1@" + "0" * 64,
    r"^sha256:[0-9a-f]{64}$": "sha256:" + "0" * 64, r"^so1-[0-9a-f]{48}$": "so1-" + "0" * 48,
    r"^tap-chiplet-[0-9]{1,2}$": "tap-chiplet-0",
    r"^/sentilab/open/terms/[1-9][0-9]{0,5}@[0-9a-f]{64}[.]md$": "/sentilab/open/terms/1@" + "0" * 64 + ".md",
}


def pattern_cases() -> list:
    """Each pattern with its sample (a match), and the sample with a line ending or separator at either end (never a
    match). JSON Schema patterns are ECMA-262: $ is the end of the input, as in schemas.ecma_pattern."""
    cases = []
    for pattern, sample in PATTERN_SAMPLES.items():
        cases.append({"pattern": pattern, "text": sample, "match": True})
        for text in (sample + "\n", sample + "\r\n", sample + "\r", sample + chr(0x2028), "\n" + sample):
            cases.append({"pattern": pattern, "text": text, "match": False})
    return cases


# ── output ──────────────────────────────────────────────────────────────────────────────────────────────────────

def dump(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=1) + "\n").encode()


def dump_cases(cases) -> bytes:
    """One compact case per line: still one JSON document, and a reviewable diff."""
    lines = (json.dumps(case, ensure_ascii=False, separators=(",", ":")) for case in cases)
    return ('{"cases": [\n' + ",\n".join(lines) + "\n]}\n").encode()


def outputs() -> dict:
    records = (manifest_records() + terms_records() + check_records() + receipt_records() + status_records()
               + results_records() + other_records())
    return {
        CONTRACT_DIR / "vectors-canonical.json": dump(vectors()),
        GOLDEN / "manifests.json": dump({"manifests": MANIFESTS, "manifest_id": ID, "terms": TERMS}),
        GOLDEN / "notes.json": dump_cases(note_cases()),
        GOLDEN / "records.json": dump_cases(records),
        GOLDEN / "states.json": dump(state_table()),
        GOLDEN / "revisions.json": dump_cases(revisions()),
        GOLDEN / "order.json": dump(ordering()),
        GOLDEN / "predicates.json": dump_cases(predicate_cases()),
    }


def main(argv) -> int:
    if "--seal" in argv:
        seal_all()
        return 0
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
